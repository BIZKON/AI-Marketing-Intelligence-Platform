"""Base parser interface for all platform parsers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedPost:
    """Unified representation of a post from any platform."""

    external_id: str
    platform: str
    title: str | None = None
    text_content: str | None = None
    url: str | None = None
    media_urls: list[str] = field(default_factory=list)
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    published_at: datetime | None = None
    raw_data: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Combined text for embedding and deduplication."""
        parts = []
        if self.title:
            parts.append(self.title)
        if self.text_content:
            parts.append(self.text_content)
        return "\n".join(parts)


class BaseParser(abc.ABC):
    """Abstract base class for platform-specific parsers."""

    @abc.abstractmethod
    async def fetch_posts(
        self,
        tracking_config: dict,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ParsedPost]:
        """Fetch recent posts from the platform.

        Args:
            tracking_config: Platform-specific configuration
                e.g. {"channel": "@competitor"} for Telegram
            since: Only fetch posts after this timestamp
            limit: Maximum number of posts to fetch

        Returns:
            List of parsed posts in unified format
        """
        ...

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier string."""
        ...
