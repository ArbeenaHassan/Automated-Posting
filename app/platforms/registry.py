"""Platform selection is internal - the request never chooses platforms."""
from typing import List

from app.platforms.base import BasePlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.groq import GroqPlatform


def get_platforms() -> List[BasePlatform]:
    return [MastodonPlatform(), BlueskyPlatform(), DevToPlatform(), TelegramPlatform(), DiscordPlatform(), GroqPlatform()]
