"""Discord bot for one links channel (+ an alerts channel).

- Any link posted in the links channel is ingested as priority; reply in a thread with summary, topics,
  why it matters to Auki, and related items.
- /ask, /follow, /track, /unfollow, /sources, /digest
- 👍/👎 on bot messages → feedback (boosts ranking). ✅/❌ on draft posts → approve/reject (never auto-posted).
- Background loops: high-relevance alerts, weekly digest + drafts (Mondays), health check.
"""
import asyncio
import datetime as dt
import re

import discord
import feedparser
from discord import app_commands
from discord.ext import tasks

from .. import db, health
from .. import digest as digest_mod
from .. import search as s
from ..config import settings
from ..connectors import http_client
from ..log import log
from ..pipeline.run import ingest_url
from ..urls import find_urls
from .format import item_embed

UP, DOWN, APPROVE, REJECT = "👍", "👎", "✅", "❌"
SKIP_HOSTS = ("discord.com", "discord.gg", "tenor.com", "giphy.com", "cdn.discordapp.com")


async def remember(message: discord.Message, kind: str, item_id: int | None = None, draft_id: int | None = None):
    await db.execute("insert into discord_messages values (%s, %s, %s, %s) on conflict do nothing",
                     str(message.id), item_id, draft_id, kind)


def parse_follow(target: str) -> tuple[str, str] | None:
    t = target.strip()
    if m := re.match(r"^(?:https?://)?(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/?$", t) or \
            re.match(r"^(?:@|x:)([A-Za-z0-9_]{1,15})$", t):
        return "x_account", m.group(1)
    if m := re.match(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+(?:/[\w.-]+)?)/?$", t) or \
            re.match(r"^(?:gh|github):([\w.-]+(?:/[\w.-]+)?)$", t):
        return "github_org", m.group(1)
    if t.startswith("http"):
        return "rss", t
    return None


class ScoutBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.cfg = settings()
        register_commands(self)

    async def setup_hook(self):
        if gid := self.cfg.discord_guild_id:
            guild = discord.Object(id=gid)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.alerts_loop.start()
        self.digest_loop.start()
        self.health_loop.start()

    async def on_ready(self):
        log.info("bot.ready", user=str(self.user))

    # ---------- link ingestion ----------
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != self.cfg.discord_links_channel_id:
            return
        urls = [u for u in find_urls(message.content) if not any(h in u for h in SKIP_HOSTS)][:3]
        if not urls:
            return
        await message.add_reaction("⏳")
        thread = None
        for url in urls:
            try:
                result = await ingest_url(url, submitted_by=str(message.author))
                if not result.item_id:
                    raise RuntimeError(result.error or "could not ingest")
                item = await s.get_item(result.item_id)
                header = "Already in Scout, added your sighting" if result.status == "duplicate" else \
                    f"Ingested · cost ${result.cost:.4f}"
                if thread is None:
                    thread = await message.create_thread(name=item["title"][:95] or "Scout", auto_archive_duration=1440)
                reply = await thread.send(embed=item_embed(item, header))
                await remember(reply, "ingest_reply", item_id=item["id"])
                await reply.add_reaction(UP)
                await reply.add_reaction(DOWN)
            except Exception as e:
                log.warning("bot.ingest_failed", url=url, error=repr(e)[:300])
                target = thread or message.channel
                await target.send(f"⚠️ Couldn't ingest <{url}>: `{str(e)[:180]}`")
        await message.remove_reaction("⏳", self.user)
        await message.add_reaction("✅")

    # ---------- reactions → feedback / draft approval ----------
    async def on_raw_reaction_add(self, p: discord.RawReactionActionEvent):
        await self._reaction(p, added=True)

    async def on_raw_reaction_remove(self, p: discord.RawReactionActionEvent):
        await self._reaction(p, added=False)

    async def _reaction(self, p: discord.RawReactionActionEvent, added: bool):
        if self.user and p.user_id == self.user.id:
            return
        emoji = str(p.emoji)
        row = await db.fetchrow("select * from discord_messages where message_id = %s", str(p.message_id))
        if not row:
            return
        if row["item_id"] and emoji in (UP, DOWN):
            if added:
                await db.execute(
                    """insert into feedback (item_id, user_id, signal) values (%s, %s, %s)
                       on conflict (item_id, user_id) do update set signal = excluded.signal, created_at = now()""",
                    row["item_id"], str(p.user_id), 1 if emoji == UP else -1)
            else:
                await db.execute("delete from feedback where item_id = %s and user_id = %s and signal = %s",
                                 row["item_id"], str(p.user_id), 1 if emoji == UP else -1)
        elif row["draft_id"] and emoji in (APPROVE, REJECT) and added:
            status = "approved" if emoji == APPROVE else "rejected"
            await db.execute("update post_drafts set status = %s, decided_by = %s where id = %s",
                             status, str(p.user_id), row["draft_id"])
            channel = self.get_channel(p.channel_id)
            if channel:
                await channel.send(f"Draft #{row['draft_id']} **{status}** by <@{p.user_id}>."
                                   + (" Copy it from above and post it from the Auki account." if status == "approved" else ""))

    # ---------- background loops ----------
    @tasks.loop(minutes=10)
    async def alerts_loop(self):
        channel = self.get_channel(self.cfg.discord_alerts_channel_id or 0)
        if not channel:
            return
        rows = await db.fetch(
            """update items set alerted_at = now()
               where id in (select id from items where alerted_at is null and submitted_by is null
                            and auki_relevance >= %s and ingested_at > now() - interval '2 days'
                            order by auki_relevance desc limit 5)
               returning id""", self.cfg.alert_min_relevance)
        for r in rows:
            item = await s.get_item(r["id"])
            msg = await channel.send(embed=item_embed(item, "🚨 High relevance for Auki"))
            await remember(msg, "alert", item_id=r["id"])
            await msg.add_reaction(UP)
            await msg.add_reaction(DOWN)

    @tasks.loop(time=dt.time(hour=8, minute=0, tzinfo=dt.UTC))
    async def digest_loop(self):
        if dt.datetime.now(dt.UTC).weekday() == 0:  # Mondays
            await self.post_digest()

    async def post_digest(self, channel=None):
        channel = channel or self.get_channel(self.cfg.discord_digest_channel_id or self.cfg.discord_alerts_channel_id or 0)
        if not channel:
            return
        d = await digest_mod.weekly()
        msg = await channel.send(f"📰 **Weekly robotics digest**\n{d['digest']}"[:2000])
        await remember(msg, "digest")
        for draft in d["drafts"]:
            m = await channel.send(f"✍️ **Draft X post #{draft['id']}** (react {APPROVE} approve / {REJECT} reject; "
                                   f"nothing is posted automatically)\n>>> {draft['body']}")
            await remember(m, "draft", item_id=draft["item_id"], draft_id=draft["id"])
            await m.add_reaction(APPROVE)
            await m.add_reaction(REJECT)

    @tasks.loop(hours=6)
    async def health_loop(self):
        lines = await health.problems()
        channel = self.get_channel(self.cfg.discord_alerts_channel_id or 0)
        if lines and channel:
            await channel.send("🩺 **Scout health check**\n" + "\n".join(f"• {l}" for l in lines)[:1900])

    @alerts_loop.before_loop
    @digest_loop.before_loop
    @health_loop.before_loop
    async def _wait_ready(self):
        await self.wait_until_ready()


def register_commands(bot: ScoutBot):
    tree = bot.tree

    @tree.command(description="Ask Scout a question; answers cite the database.")
    async def ask(interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)
        r = await s.ask(question)
        srcs = "\n".join(f"[{x['n']}] [{x['title'][:90]}](<{x['url']}>)" for x in r["sources"])
        await interaction.followup.send(f"**Q: {question}**\n{r['answer']}\n\n{srcs}"[:2000])

    @tree.command(description="Follow an X account (@handle), GitHub org/repo (github:org) or RSS feed URL.")
    async def follow(interaction: discord.Interaction, target: str):
        parsed = parse_follow(target)
        if not parsed:
            await interaction.response.send_message(
                "Use `@handle`, `github:org`, `github:org/repo`, a github.com URL, or an RSS feed URL.", ephemeral=True)
            return
        kind, value = parsed
        if kind == "rss":
            async with http_client() as http:
                ok = False
                try:
                    r = await http.get(value)
                    ok = bool(feedparser.parse(r.content).entries)
                except Exception:
                    pass
            if not ok:
                await interaction.response.send_message(f"<{value}> doesn't look like an RSS/Atom feed.", ephemeral=True)
                return
        await db.execute("""insert into sources (kind, value, added_by) values (%s, %s, %s)
                            on conflict (kind, value) do update set enabled = true""", kind, value, str(interaction.user))
        note = " (needs `X_BEARER_TOKEN` to monitor; shared X links always work)" if kind == "x_account" and not bot.cfg.x_bearer_token else ""
        await interaction.response.send_message(f"Following `{kind}:{value}`{note}. Picked up on the next run.")

    @tree.command(description="Track a keyword across arXiv, Hacker News, GitHub and X.")
    async def track(interaction: discord.Interaction, keyword: str):
        kw = keyword.strip().replace('"', "")
        rows = [("arxiv_query", f'all:"{kw}" AND (cat:cs.RO OR cat:cs.CV OR cat:cs.LG OR cat:cs.AI)'),
                ("hn_query", kw), ("github_query", f'"{kw}" in:name,description'), ("x_query", kw)]
        for kind, value in rows:
            await db.execute("""insert into sources (kind, value, added_by) values (%s, %s, %s)
                                on conflict (kind, value) do update set enabled = true""", kind, value, str(interaction.user))
        await interaction.response.send_message(f"Tracking **{kw}** on arXiv, HN, GitHub and X.")

    @tree.command(description="Stop following an account/feed or tracking a keyword.")
    async def unfollow(interaction: discord.Interaction, target: str):
        parsed = parse_follow(target)
        value = parsed[1] if parsed else target.strip()
        rows = await db.fetch("""update sources set enabled = false
                                 where value = %s or value ilike %s returning kind, value""",
                              value, f'%"{target.strip()}"%')
        msg = "\n".join(f"• `{r['kind']}:{r['value']}`" for r in rows) or "Nothing matched."
        await interaction.response.send_message(f"Disabled:\n{msg}"[:2000])

    @tree.command(description="List tracked sources and their health.")
    async def sources(interaction: discord.Interaction):
        rows = await db.fetch("""select kind, value, consecutive_failures from sources where enabled
                                 order by kind, value""")
        lines = [f"{'🔴' if r['consecutive_failures'] >= 3 else '🟢'} `{r['kind']}` {r['value']}" for r in rows]
        await interaction.response.send_message("\n".join(lines)[:2000] or "No sources.", ephemeral=True)

    @tree.command(description="Post the weekly digest + draft X posts now.")
    async def digest(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await bot.post_digest(interaction.channel)
        await interaction.followup.send("Digest posted above.")


def run() -> None:
    token = settings().discord_token
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set")
    ScoutBot().run(token, log_handler=None)


if __name__ == "__main__":
    asyncio.run(db.migrate())
    run()
