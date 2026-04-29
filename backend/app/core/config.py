from pathlib import Path
import os
from urllib.parse import quote
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ENV = os.getenv("APP_ENV", "development").lower()
ENV_FILE = None if APP_ENV in ("production", "prod") else REPO_ROOT / ".env.dev"

print("ENV_FILE resolved to:", ENV_FILE)

if ENV_FILE and not ENV_FILE.exists():
    raise FileNotFoundError("❌ ENV FILE NOT FOUND: .env.dev")


model_config: dict = {"extra": "allow"}
if ENV_FILE:
    model_config["env_file"] = str(ENV_FILE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**model_config)

    # ---- BASE ----
    app_version: str = "1.0.0"
    app_name: str = "Project Backend"
    description: str = "Backend for Project application"
    app_env: str = "production"
    debug: bool = False
    debug_level: str = "INFO"
    auth_secret_key: str = "dev-auctions-auth-secret"
    auth_token_ttl_minutes: int = 60 * 24 * 7
    default_user_enabled: bool = APP_ENV not in ("production", "prod")
    default_user_name: str = "Default User"
    default_user_email: str = "demo@auctions.local"
    default_user_password: str | None = None

    # ---- DB ----
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str

    # ---- Redis / background sync ----
    redis_url: str = "redis://redis:6379/0"
    auction_events_stream: str = "auction:events"
    auction_sync_interval_seconds: int = 300
    auction_sync_limit: int = 0
    auction_sync_commit_chunk_size: int = 25
    auction_sync_progress_log_every: int = 25
    auction_detail_sync_enabled: bool = True
    auction_detail_sync_limit: int = 25
    auction_publication_sync_limit: int = 0
    auction_analysis_enabled: bool = True
    auction_analysis_interval_seconds: int = 180
    auction_analysis_batch_size: int = 500
    auction_analysis_commit_chunk_size: int = 25
    auction_analysis_event_chunk_size: int = 25
    auction_analysis_event_pause_seconds: float = 0.05

    # ---- TBankrot ----
    tbankrot_auth_enabled: bool = False
    tbankrot_login: str | None = None
    tbankrot_password: str | None = None
    tbankrot_pages: int = 3
    tbankrot_include_price_schedule: bool = True

    # ---- Database URL ----
    @property
    def database_url(self) -> str:
        user = quote(self.postgres_user)
        password = quote(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

def get_settings() -> Settings:
    return Settings()
