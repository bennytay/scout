"""Discord bot: Scout's whole interface.

1. Monitor: scan X every few hours, silently (only failures are posted). Once a day, post the news brief: the top
   7-10 stories as cards, each led by its X post (picture, likes) and linked to its paper / code / model.
   /scan runs a scan now and posts the brief of anything new.
2. Team links: any link posted in the links channel is ingested and answered in 4 bullets.
3. Ask: @Scout <question> (or /ask). Claude turns the question into search filters (author, topic, date, …),
   searches, and answers with numbered sources.
4. Look up, no LLM: /author (autocomplete), /topic, /recent ("what's stored?"), and /follow, /unfollow to edit the
   X radar.
"""
import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from .. import db, health
from .. import search as s
from ..brief import brief_when, lead_items, make_brief
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


class ScoutBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg = settings()
        self.tree = app_commands.CommandTree(self)
        self.reported_problems: set[str] = set()
        self.said_no_x = False
        self.scan_lock = asyncio.Lock()
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
        else:
            await self.cycle()
        problems = set(await health.problems())
        if new := problems - self.reported_problems:  # only say it once
            await self.feed("🩺 " + "\n🩺 ".join(sorted(new)))
        self.reported_problems = problems

    async def cycle(self) -> None:
        """Scan X if due (silently; failures are posted), the daily brief if due, maybe a radar suggestion."""
        if await due("x", self.cfg.x_every_hours) and not self.scan_lock.locked():
            await self.scan()
            if sug := await radar_suggestion():
                await self.feed(sug)
        if await brief_due(self.cfg.brief_hour, self.cfg.brief_tz):
            b = await make_brief()
            if b and b["stories"]:
                for msg in await brief_payload(b):
                    await self.feed_message(msg)

    async def scan(self):
        """One X scan at a time (the 2-hourly loop and /scan share this)."""
        async with self.scan_lock:
            try:
                st = await run_connector("x")
            except Exception as e:
                log.error("monitor.crashed", error=repr(e)[:300])
                await self.feed(fmt.source_failed("x", [repr(e)]))
                return None
        if st.errors:
            await self.feed(fmt.source_failed("x", st.errors))
        return st

    async def feed_message(self, msg: dict):
        if channel := self.get_channel(self.cfg.discord_feed_channel_id or 0):
            await channel.send(**to_discord(msg))

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


def brief_cutoff(now: datetime, hour: int, tz: str) -> datetime:
    """The most recent daily brief time (e.g. 9:00 Sydney) at or before `now`."""
    local = now.astimezone(ZoneInfo(tz))
    cut = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    return cut if cut <= local else cut - timedelta(days=1)


async def brief_due(hour: int, tz: str, now: datetime | None = None) -> bool:
    """Due once a day: no brief since today's brief time, and something was kept since the last brief."""
    now = now or datetime.now(ZoneInfo(tz))
    row = await db.fetchrow(
        """select coalesce(max(window_end), '-infinity') < %s as due,
                  exists (select 1 from items where ingested_at > coalesce((select max(window_end) from briefs),
                                                                             '-infinity')) as fresh
           from briefs""", brief_cutoff(now, hour, tz))
    return row["due"] and row["fresh"]


async def brief_payload(b: dict) -> list[dict]:
    return fmt.brief_messages(b, await lead_items(b), brief_when(b))


def to_discord(msg: dict) -> dict:
    out = {"embeds": [discord.Embed.from_dict(e) for e in msg["embeds"]]}
    if msg.get("content"):
        out["content"] = msg["content"]
    return out


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

    @tree.command(description="Scan X now and post a brief of anything new since the last one")
    async def scan(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        bot = interaction.client
        st = await bot.scan()
        if st is None:
            await interaction.followup.send("⚠️ The X scan failed. Details are in the feed channel.")
            return
        b = await make_brief()
        if not b or not b["stories"]:
            await interaction.followup.send(f"Nothing new worth a brief since the last one ({st.fetched} posts scanned).")
            return
        for msg in await brief_payload(b):
            await interaction.followup.send(**to_discord(msg))

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
