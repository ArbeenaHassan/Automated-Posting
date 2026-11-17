"""Telegram Bot API - sendMessage  https://core.telegram.org/bots/api#sendmessage
Bot must be an admin of a PUBLIC channel for a public t.me link."""
import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class TelegramPlatform(BasePlatform):
    name = "Telegram"

    def is_configured(self) -> bool:
        return bool(settings.telegram_bot_token and settings.telegram_channel_username)

    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome:
        resp = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_channel_username, "text": message},
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("ok"):
            raise PlatformError(f"Telegram error: {data.get('description', resp.text[:200])}")
        msg = data["result"]
        username = msg.get("chat", {}).get("username")
        if not username:
            # Private channel: message exists but has no public link.
            return PublishOutcome(posted_url=None, public_access=False)
        return PublishOutcome(posted_url=f"https://t.me/{username}/{msg['message_id']}", public_access=True)
