"""Discord bot. Two jobs only:

1. Monitor: run every due connector (one live status line, edited in place), then post the news brief:
   the top 7-10 stories of the period, X-first, each with links to the supporting paper/code/model.
2. Team links: any link posted in the links channel is ingested and answered in 4 bullets.

Questions about the data go through MCP (any LLM client), not the bot.
"""
import discord
from discord.ext import tasks

from .. import db, health
from .. import search as s
from ..brief import make_brief
from ..config import settings
from ..connectors import REGISTRY
from ..log import log
from ..pipeline.run import ingest_url, run_connector
from ..urls import find_urls
from .format import LABEL, link_reply, render_brief, source_failed

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
        due_now = [n for n, c in REGISTRY.items()
                   if all(getattr(self.cfg, k) for k in c.needs) and await due(n)]
        if due_now:
            await self.cycle(due_now)
        problems = set(await health.problems())
        if new := problems - self.reported_problems:  # only say it once
            await self.feed("🩺 " + "\n🩺 ".join(sorted(new)))
        self.reported_problems = problems

    async def cycle(self, names: list[str]) -> None:
        """Run the due sources, showing progress in ONE message edited in place, then post the brief."""
        channel = self.get_channel(self.cfg.discord_feed_channel_id or 0)
        state = {n: "⏳" for n in names}

        def status_line(done: bool = False) -> str:
            parts = " · ".join(f"{LABEL.get(n, n)} {v}" for n, v in state.items())
            return f"📡 {'Scanned' if done else 'Scanning'}: {parts}"

        status = await channel.send(status_line(), suppress_embeds=True) if channel else None
        new_total, failures = 0, []
        for name in names:
            try:
                stats = await run_connector(name)
                state[name] = f"✓ {stats.inserted}" if not stats.errors else f"⚠️ {stats.inserted}"
                new_total += stats.inserted
                if stats.errors:
                    failures.append(source_failed(name, stats.errors))
            except Exception as e:
                log.error("monitor.crashed", connector=name, error=repr(e)[:300])
                state[name] = "⚠️"
                failures.append(source_failed(name, [repr(e)]))
            if status:
                await status.edit(content=status_line())
        if status:
            await status.edit(content=status_line(done=True) + f" → {new_total} new")
        for f in failures:
            await self.feed(f)
        if new_total:
            b = await make_brief()
            if b and b["stories"]:
                for msg in render_brief(b, x_monitored=bool(self.cfg.x_bearer_token)):
                    await self.feed(msg)

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
