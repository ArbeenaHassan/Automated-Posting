"""Configuration loaded from environment variables."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    request_timeout: float = float(_env("REQUEST_TIMEOUT_SECONDS", "15"))

    mastodon_base_url: str = _env("MASTODON_BASE_URL", "https://mastodon.social").rstrip("/")
    mastodon_access_token: str = _env("MASTODON_ACCESS_TOKEN")

    bluesky_handle: str = _env("BLUESKY_HANDLE")
    bluesky_app_password: str = _env("BLUESKY_APP_PASSWORD")
    bluesky_pds: str = _env("BLUESKY_PDS", "https://bsky.social").rstrip("/")

    devto_api_key: str = _env("DEVTO_API_KEY")

    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN")
    telegram_channel_username: str = _env("TELEGRAM_CHANNEL_USERNAME")

    discord_webhook_url: str = _env("DISCORD_WEBHOOK_URL")

    groq_api_key: str = _env("GROQ_API_KEY")
    groq_model: str = _env("GROQ_MODEL", "openai/gpt-oss-20b")


settings = Settings()
