"""Discord bot. Two jobs only:

1. Monitor: run every connector on its schedule and post one short message per source to the feed channel.
2. Team links: any link posted in the links channel is ingested and answered in 4 bullets.

Questions about the data go through MCP (any LLM client), not the bot.
"""
import discord
from discord.ext import tasks

from .. import db, health
from .. import search as s
from ..config import settings
from ..connectors import REGISTRY
from ..log import log
from ..pipeline.run import ingest_url, run_connector
from ..urls import find_urls
from .format import LABEL, link_reply, source_failed, source_update

SKIP_HOSTS = ("discord.com", "discord.gg", "tenor.com", "giphy.com", "cdn.discordapp.com")
EVERY_HOURS = {"x": 8}  # X reads cost credits: 3x/day. Everything else every 4h.
DEFAULT_HOURS = 4


async def due(name: str) -> bool:
    """Restart-safe: decided from the last ingest run in the database, not in-memory state."""
    row = await db.fetchrow(
        """select count(*) = 0 as due from ingest_runs
           where connector = %s and started_at > now() - make_interval(hours => %s)""",
        name, EVERY_HOURS.get(name, DEFAULT_HOURS))
    return row["due"]


class ScoutBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg = settings()
        self.reported_problems: set[str] = set()

    async def setup_hook(self):
        self.monitor.start()

    async def on_ready(self):
        log.info("bot.ready", user=str(self.user))

    async def feed(self, text: str):
        if channel := self.get_channel(self.cfg.discord_feed_channel_id or 0):
            await channel.send(text, suppress_embeds=True)

    # ---------- 1. monitoring ----------
    @tasks.loop(minutes=5)
    async def monitor(self):
        for name, connector in REGISTRY.items():
            if any(not getattr(self.cfg, k) for k in connector.needs) or not await due(name):
                continue
            try:
                stats = await run_connector(name)
            except Exception as e:
                log.error("monitor.crashed", connector=name, error=repr(e)[:300])
                await self.feed(source_failed(name, [repr(e)]))
                continue
            if stats.new_ids:
                await self.feed(source_update(name, await s.hydrate(stats.new_ids), self.cfg.alert_min_relevance))
            elif not stats.errors:
                await self.feed(f"📡 **{LABEL.get(name, name)}** · nothing new")  # proves the monitor is alive
            if stats.errors:
                await self.feed(source_failed(name, stats.errors))
        problems = set(await health.problems())
        if new := problems - self.reported_problems:  # only say it once
            await self.feed("🩺 " + "\n🩺 ".join(sorted(new)))
        self.reported_problems = problems

    @monitor.before_loop
    async def _ready(self):
        await self.wait_until_ready()

    # ---------- 2. team links ----------
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != self.cfg.discord_links_channel_id:
            return
        urls = [u for u in find_urls(message.content) if not any(h in u for h in SKIP_HOSTS)][:3]
        if not urls:
            return
        await message.add_reaction("⏳")
        for url in urls:
            result = await ingest_url(url, submitted_by=str(message.author))
            if result.item_id:
                item = await s.get_item(result.item_id)
                text = link_reply(item, duplicate=result.status == "duplicate")
            else:
                text = f"⚠️ Couldn't read <{url}>: {result.error or 'unknown error'}"
            await message.reply(text, suppress_embeds=True, mention_author=False)
        await message.remove_reaction("⏳", self.user)
        await message.add_reaction("✅")


def run() -> None:
    token = settings().discord_token
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set")
    ScoutBot().run(token, log_handler=None)
