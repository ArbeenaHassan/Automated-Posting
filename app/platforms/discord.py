"""Discord - Execute Webhook  https://discord.com/developers/docs/resources/webhook#execute-webhook
Discord messages are visible only to server members -> public_access=False."""
import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class DiscordPlatform(BasePlatform):
    name = "Discord"

    def is_configured(self) -> bool:
        return bool(settings.discord_webhook_url)

    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome:
        # wait=true makes Discord return the created message object.
        resp = await client.post(settings.discord_webhook_url, params={"wait": "true"}, json={"content": message})
        self.raise_for_status(resp)
        data = resp.json()
        guild_id, channel_id, msg_id = data.get("guild_id"), data.get("channel_id"), data.get("id")
        if not (channel_id and msg_id):
            raise PlatformError("Discord response did not include message identifiers.")
        posted = f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}" if guild_id else None
        return PublishOutcome(posted_url=posted, public_access=False)
