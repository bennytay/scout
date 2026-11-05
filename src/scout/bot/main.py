"""Discord bot: Scout's whole interface.

1. Monitor: scan X every few hours (one live status line, edited in place), then post the news brief: the top
   7-10 stories, each led by an X post and linked to its paper / code / model.
2. Team links: any link posted in the links channel is ingested and answered in 4 bullets.
3. Ask: @Scout <question> (or /ask). Claude turns the question into search filters (author, topic, date, …),
   searches, and answers with numbered sources.
4. Look up, no LLM: /author (autocomplete), /topic, /recent ("what's stored?"), and /follow, /unfollow to edit the
   X radar.
"""
import re

import discord
from discord import app_commands
from discord.ext import tasks

from .. import db, health
from .. import search as s
from ..brief import make_brief
from ..config import settings
from ..log import log
from ..models import TOPICS
from ..pipeline.run import ingest_url, run_connector
from ..urls import find_urls
from . import format as fmt

SKIP_HOSTS = ("discord.com", "discord.gg", "tenor.com", "giphy.com", "cdn.discordapp.com")
HANDLE = re.compile(r"^@?(\w{1,15})$")


async def due(name: str, hours: int) -> bool:
    """Restart-safe: decided from the last ingest run in the database, not in-memory state."""
    row = await db.fetchrow(
        """select count(*) = 0 as due from ingest_runs
           where connector = %s and started_at > now() - make_interval(hours => %s)""", name, hours)
    return row["due"]


def scan_line(st, done: bool) -> str:
    if not done:
        return "📡 Scanning X ⏳"
    judged = st.fetched - st.gated
    line = (f"📡 Scanned X: {st.fetched} posts → {judged} passed the filter → **{st.inserted} kept**"
            + (f" (+{st.expanded} papers/repos they link to)" if st.expanded else ""))
    return line + (" ⚠️" if st.errors else "")


class ScoutBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg = settings()
        self.tree = app_commands.CommandTree(self)
        self.reported_problems: set[str] = set()
        self.said_no_x = False
        register_commands(self.tree)

    async def setup_hook(self):
        self.monitor.start()

    async def on_ready(self):
        for guild in self.guilds:  # guild sync is instant; global sync can take an hour
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        log.info("bot.ready", user=str(self.user), guilds=len(self.guilds))

    async def feed(self, text: str):
        if channel := self.get_channel(self.cfg.discord_feed_channel_id or 0):
            await channel.send(text, suppress_embeds=True)

    # ---------- 1. monitoring ----------
    @tasks.loop(minutes=5)
    async def monitor(self):
        if not self.cfg.x_enabled:
            if not self.said_no_x:
                await self.feed("📡 X isn't configured (set X_API_KEY + X_API_SECRET), so I'm only reading team links.")
                self.said_no_x = True
        elif await due("x", self.cfg.x_every_hours):
            await self.cycle()
        problems = set(await health.problems())
        if new := problems - self.reported_problems:  # only say it once
            await self.feed("🩺 " + "\n🩺 ".join(sorted(new)))
        self.reported_problems = problems

    async def cycle(self) -> None:
        """Scan X (one status message, edited in place), post failures, the brief, and maybe a radar suggestion."""
        channel = self.get_channel(self.cfg.discord_feed_channel_id or 0)
        status = await channel.send(scan_line(None, False), suppress_embeds=True) if channel else None
        try:
            st = await run_connector("x")
        except Exception as e:
            log.error("monitor.crashed", error=repr(e)[:300])
            if status:
                await status.edit(content="📡 X scan crashed ⚠️")
            await self.feed(fmt.source_failed("x", [repr(e)]))
            return
        if status:
            await status.edit(content=scan_line(st, True))
        if st.errors:
            await self.feed(fmt.source_failed("x", st.errors))
        if await brief_due(self.cfg.brief_every_hours):
            b = await make_brief()
            if b and b["stories"]:
                for msg in fmt.render_brief(b, x_monitored=True):
                    await self.feed(msg)
        if sug := await radar_suggestion():
            await self.feed(sug)

    @monitor.before_loop
    async def _ready(self):
        await self.wait_until_ready()

    # ---------- 2. team links, 3. @Scout ----------
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        urls = [u for u in find_urls(message.content) if not any(h in u for h in SKIP_HOSTS)][:3]
        if message.channel.id == self.cfg.discord_links_channel_id and urls:
            await self.ingest_links(message, urls)
        elif self.user and self.user in message.mentions:
            question = re.sub(r"<@!?\d+>", "", message.content).strip()
            if not question:
                await message.reply("Ask me anything about what's stored, e.g. *who's working on visual "
                                    "relocalization, and is there code?*", mention_author=False)
                return
            async with message.channel.typing():
                text = await answer(question)
            await message.reply(text, suppress_embeds=True, mention_author=False)

    async def ingest_links(self, message: discord.Message, urls: list[str]):
        await message.add_reaction("⏳")
        for url in urls:
            result = await ingest_url(url, submitted_by=str(message.author))
            if result.item_id:
                item = await s.get_item(result.item_id)
                text = fmt.link_reply(item, duplicate=result.status == "duplicate")
            else:
                text = f"⚠️ Couldn't read <{url}>: {result.error or 'unknown error'}"
            await message.reply(text, suppress_embeds=True, mention_author=False)
        await message.remove_reaction("⏳", self.user)
        await message.add_reaction("✅")


async def brief_due(hours: int) -> bool:
    """A brief is due if the last one is older than `hours` and something was kept since it."""
    row = await db.fetchrow(
        """select coalesce(max(window_end), '-infinity') < now() - make_interval(hours => %s) as due,
                  exists (select 1 from items where ingested_at > coalesce((select max(window_end) from briefs),
                                                                             '-infinity')) as fresh
           from briefs""", hours)
    return row["due"] and row["fresh"]


async def answer(question: str) -> str:
    try:
        return fmt.ask_reply(await s.ask(question))
    except Exception as e:
        log.error("ask.failed", error=repr(e)[:300])
        return "⚠️ Something went wrong answering that. Try again, or use /topic or /author."


async def radar_suggestion() -> str | None:
    """Learn step: one non-radar account whose posts keep surviving the judge."""
    row = await db.fetchrow(
        """select x.handle, x.kept, x.judged from x_accounts x
           where x.kept >= 3 and x.kept::float / x.judged >= 0.5 and x.suggested_at is null
             and not exists (select 1 from sources s where s.kind = 'x_account' and lower(s.value) = x.handle)
           order by x.kept desc limit 1""")
    if not row:
        return None
    await db.execute("update x_accounts set suggested_at = now() where handle = %s", row["handle"])
    return fmt.radar_suggestion(row["handle"], row["kept"], row["judged"])


async def follow(handle: str, on: bool) -> str:
    m = HANDLE.match(handle.strip())
    if not m:
        return f"⚠️ `{handle}` doesn't look like an X handle."
    h = m.group(1)
    if on:
        await db.execute(
            """insert into sources (kind, value, added_by, config) values ('x_account', %s, 'discord', '{"tier": "added"}')
               on conflict (kind, value) do update set enabled = true""", h)
        return f"✅ [@{h}](<https://x.com/{h}>) is on the radar. Their posts skip the filter from the next scan."
    row = await db.fetchrow(
        "update sources set enabled = false where kind = 'x_account' and lower(value) = lower(%s) returning value", h)
    return f"✅ [@{h}](<https://x.com/{h}>) removed from the radar." if row else f"@{h} wasn't on the radar."


def register_commands(tree: app_commands.CommandTree) -> None:
    topic_choices = [app_commands.Choice(name=t, value=t) for t in TOPICS]

    @tree.command(description="Ask anything about what Scout has stored")
    async def ask(interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(await answer(question), suppress_embeds=True)

    async def author_complete(_: discord.Interaction, current: str):
        rows = await s.authors_like(current)
        return [app_commands.Choice(name=f"{r['name']}{' @' + r['x_handle'] if r['x_handle'] else ''} ({r['n']})"[:100],
                                    value=r["name"][:100]) for r in rows]

    @tree.command(description="Everything stored from one person (fuzzy: 'hutter', '@svlevine')")
    @app_commands.autocomplete(name=author_complete)
    async def author(interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        p = await s.author_profile(name)
        await interaction.followup.send(fmt.author_reply(p) if p else f"No author matching **{name}** yet.",
                                        suppress_embeds=True)

    @tree.command(description="Latest stored items on a topic")
    @app_commands.choices(topic=topic_choices)
    async def topic(interaction: discord.Interaction, topic: app_commands.Choice[str], days: int = 14):
        await interaction.response.defer()
        items = await s.search(topic=topic.value, since=f"{days}d", limit=10)
        links = await s.linked([i["id"] for i in items])
        await interaction.followup.send(
            fmt.item_list(f"🏷️ **{topic.value}** · last {days} days", items, links), suppress_embeds=True)

    @tree.command(description="What's been stored lately: counts, then the top posts and what they link to")
    async def recent(interaction: discord.Interaction, days: int = 3):
        await interaction.response.defer()
        r = await s.recent(days)
        links = await s.linked([i["id"] for i in r["top"]])
        await interaction.followup.send(fmt.recent_reply(r, links), suppress_embeds=True)

    @tree.command(name="follow", description="Add an X account to the radar (trusted: skips the filter)")
    async def follow_cmd(interaction: discord.Interaction, handle: str):
        await interaction.response.send_message(await follow(handle, True), suppress_embeds=True)

    @tree.command(name="unfollow", description="Remove an X account from the radar")
    async def unfollow_cmd(interaction: discord.Interaction, handle: str):
        await interaction.response.send_message(await follow(handle, False), suppress_embeds=True)


def run() -> None:
    token = settings().discord_token
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set")
    ScoutBot().run(token, log_handler=None)
