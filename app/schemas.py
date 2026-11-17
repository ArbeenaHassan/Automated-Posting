"""Request/response models and input validation."""
import re
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_LENGTH = 200
# Any token that looks like a link: scheme-based or www-based.
URL_CANDIDATE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
HOST_PATTERN = re.compile(
    r"^(localhost|(\d{1,3}\.){3}\d{1,3}|([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})$",
    re.IGNORECASE,
)
TRAILING_PUNCT = ".,;:!?)]}'\""


def extract_urls(text: str) -> List[str]:
    return [m.rstrip(TRAILING_PUNCT) for m in URL_CANDIDATE.findall(text)]


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return bool(HOST_PATTERN.match(parsed.hostname))


class PostRequest(BaseModel):
    message: str = Field(
        ...,
        description="Max 200 characters, exactly one http(s) CTA link.",
        examples=["Check out our latest business platform and grow your online visibility. https://example.com"],
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty.")
        if len(value) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message must not exceed {MAX_MESSAGE_LENGTH} characters (got {len(value)}).")
        urls = extract_urls(value)
        if len(urls) == 0:
            raise ValueError("Message must contain exactly one CTA link; none found.")
        if len(urls) > 1:
            raise ValueError(f"Message must contain exactly one CTA link; found {len(urls)}.")
        if not is_valid_url(urls[0]):
            raise ValueError(f"Invalid URL '{urls[0]}'. Use a full http:// or https:// link with a valid domain.")
        return value

    @property
    def cta_url(self) -> str:
        return extract_urls(self.message)[0]


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: Optional[str] = None
    public_access: bool = False
    date: Optional[str] = None
    time: Optional[str] = None
    error: Optional[str] = None


class PostResponse(BaseModel):
    success: bool = Field(..., description="True if at least one publishing platform succeeded; Groq processing alone does not count.")
    results: List[PlatformResult]
