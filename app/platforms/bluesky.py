"""Bluesky (AT Protocol) - https://docs.bsky.app/docs/advanced-guides/posts
Links need a 'facet' with UTF-8 BYTE offsets to be clickable."""
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


def build_link_facet(text: str, url: str) -> list:
    char_start = text.find(url)
    if char_start < 0:
        return []
    byte_start = len(text[:char_start].encode("utf-8"))
    byte_end = byte_start + len(url.encode("utf-8"))
    return [{
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
    }]


class BlueskyPlatform(BasePlatform):
    name = "Bluesky"

    def is_configured(self) -> bool:
        return bool(settings.bluesky_handle and settings.bluesky_app_password)

    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome:
        pds = settings.bluesky_pds
        session = await client.post(
            f"{pds}/xrpc/com.atproto.server.createSession",
            json={"identifier": settings.bluesky_handle, "password": settings.bluesky_app_password},
        )
        self.raise_for_status(session)
        s = session.json()
        did, jwt = s["did"], s["accessJwt"]
        handle = s.get("handle", settings.bluesky_handle)

        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "facets": build_link_facet(message, url),
        }
        resp = await client.post(
            f"{pds}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        )
        self.raise_for_status(resp)
        uri = resp.json().get("uri", "")  # at://did/app.bsky.feed.post/<rkey>
        if not uri:
            raise PlatformError("Bluesky response did not include a record URI.")
        rkey = uri.rsplit("/", 1)[-1]
        return PublishOutcome(posted_url=f"https://bsky.app/profile/{handle}/post/{rkey}", public_access=True)
