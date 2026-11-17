"""Common adapter interface. Each platform returns a normalized PlatformResult."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx


class PlatformError(Exception):
    """Raised by adapters with a human-readable reason."""


class NotConfiguredError(PlatformError):
    pass


@dataclass
class PublishOutcome:
    posted_url: Optional[str]
    public_access: bool


class BasePlatform(ABC):
    name: str = "Base"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def publish(self, client: httpx.AsyncClient, message: str, url: str) -> PublishOutcome: ...

    @staticmethod
    def raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        detail = resp.text[:200]
        if resp.status_code in (401, 403):
            raise PlatformError(f"Authentication failed (HTTP {resp.status_code}): {detail}")
        if resp.status_code == 429:
            raise PlatformError("Rate limit exceeded (HTTP 429).")
        raise PlatformError(f"HTTP {resp.status_code}: {detail}")
