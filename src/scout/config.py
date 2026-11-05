from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore", env_ignore_empty=True)

    database_url: str = "postgresql://scout:scout@localhost:54329/scout"

    # Providers. llm_provider: anthropic | fake. embedding_provider: local | fake
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-5-5"        # per-item enrichment: cheap, high volume
    brief_model: str = "claude-opus-5-5"       # the news brief: one editorial reasoning call per cycle
    llm_input_usd_per_mtok: float = 0.10
    llm_output_usd_per_mtok: float = 0.50
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_usd_per_mtok: float = 0.0
    anthropic_api_key: str | None = None

    # Sources
    github_token: str | None = None
    # X: the newsroom. Auth with a bearer token, or the app's consumer key + secret (exchanged for one).
    x_bearer_token: str | None = None
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_max_results: int = 100                # max posts read per query per scan (caps credit spend)
    x_every_hours: int = 2                  # how often the bot scans X
    brief_hour: int = 9                     # the daily brief posts at this hour (local time below); /scan any time
    brief_tz: str = "Australia/Sydney"
    x_discovery_delay_hours: int = 6        # discovery reads posts at least this old, so likes have accrued
    # the gate (discovery posts only; radar accounts are trusted and go straight to the judge)
    x_min_likes: int = 10
    x_viral_likes: int = 50                 # this many likes overrides the reputation rules
    x_min_followers: int = 200
    x_min_account_age_days: int = 90
    x_news_min_likes: int = 50              # general-news discovery (no research link required)
    x_news_min_followers: int = 1000
    x_max_per_author: int = 3               # per scan
    x_max_per_radar_author: int = 10
    hf_token: str | None = None

    # Discord: the bot watches one links channel and posts the monitoring feed to another
    discord_token: str | None = None
    discord_links_channel_id: int | None = None
    discord_feed_channel_id: int | None = Field(
        None, validation_alias=AliasChoices("discord_feed_channel_id", "discord_alerts_channel_id"))
    discord_alerts_webhook_url: str | None = None  # lets a cron job post health problems without the bot


    # MCP over HTTP
    mcp_bearer_token: str | None = None
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8765

    # Behaviour
    dedupe_similarity: float = 0.92
    alert_min_relevance: float = 0.75   # 🔥 highlight + reason line in the feed
    max_items_per_source: int = 100
    lookback_days: int = 2

    @property
    def x_enabled(self) -> bool:
        return bool(self.x_bearer_token or (self.x_api_key and self.x_api_secret))


@lru_cache
def settings() -> Settings:
    return Settings()
