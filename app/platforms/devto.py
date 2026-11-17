"""Dev.to (Forem) - POST /api/articles  https://developers.forem.com/api/v1"""
import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.schemas import extract_urls


def make_title(message: str) -> str:
    text = message
    for u in extract_urls(message):
        text = text.replace(u, "")
    text = " ".join(text.split()).strip(" -:")
    return (text[:80] or "Update").rstrip()


class DevToPlatform(BasePlatform):
    name = "Dev.to"

    def __init__(self, title: str | None = None) -> None:
        self.title = title

    def is_configured(self) -> bool:
        return bool(settings.devto_api_key)

    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome:
        resp = await client.post(
            "https://dev.to/api/articles",
            headers={
                "api-key": settings.devto_api_key,
                "Accept": "application/vnd.forem.api-v1+json",
                "User-Agent": "automated-posting/1.0",
            },
            json={"article": {"title": self.title or make_title(message), "body_markdown": message, "published": True}},
        )
        self.raise_for_status(resp)
        data = resp.json()
        if not data.get("url"):
            raise PlatformError("Dev.to response did not include an article URL.")
        return PublishOutcome(posted_url=data["url"], public_access=bool(data.get("published", True)))
