from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    database_url: str = "postgresql://scout:scout@localhost:54329/scout"

    # Providers (swappable). llm_provider: anthropic | openai | fake. embedding_provider: local | openai | fake
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-5-5"
    llm_input_usd_per_mtok: float = 0.10
    llm_output_usd_per_mtok: float = 0.50
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"   # for openai: text-embedding-3-small
    embedding_usd_per_mtok: float = 0.0
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Sources
    github_token: str | None = None
    x_bearer_token: str | None = None       # official X API v2 (pay-per-use credits)
    x_max_results: int = 20                 # per tracked source per run (10-100); caps credit spend
    hf_token: str | None = None

    # Discord
    discord_token: str | None = None
    discord_links_channel_id: int | None = None
    discord_alerts_channel_id: int | None = None
    discord_digest_channel_id: int | None = None   # defaults to alerts channel
    discord_guild_id: int | None = None            # set for instant slash-command sync
    discord_alerts_webhook_url: str | None = None  # lets cron jobs post health alerts without the bot

    # MCP over HTTP
    mcp_bearer_token: str | None = None
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8765

    # Behaviour
    dedupe_similarity: float = 0.92
    alert_min_relevance: float = 0.75
    max_items_per_source: int = 100
    lookback_days: int = 2


@lru_cache
def settings() -> Settings:
    return Settings()
