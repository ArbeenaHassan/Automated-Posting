"""Mastodon - POST /api/v1/statuses  https://docs.joinmastodon.org/methods/statuses/"""
import hashlib

import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class MastodonPlatform(BasePlatform):
    name = "Mastodon"

    def is_configured(self) -> bool:
        return bool(settings.mastodon_base_url and settings.mastodon_access_token)

    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome:
        resp = await client.post(
            f"{settings.mastodon_base_url}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {settings.mastodon_access_token}",
                # Prevents duplicate posts if the same message is retried within 1 hour.
                "Idempotency-Key": hashlib.sha256(message.encode()).hexdigest(),
            },
            data={"status": message, "visibility": "public"},
        )
        self.raise_for_status(resp)
        data = resp.json()
        if not data.get("url"):
            raise PlatformError("Mastodon response did not include a post URL.")
        return PublishOutcome(posted_url=data["url"], public_access=data.get("visibility") == "public")
