from app.services.parsers.base import BaseParser
from app.services.parsers.telegram_parser import TelegramParser
from app.services.parsers.youtube_parser import YouTubeParser
from app.services.parsers.vk_parser import VKParser
from app.services.parsers.website_parser import WebsiteParser

PARSER_MAP: dict[str, type[BaseParser]] = {
    "telegram": TelegramParser,
    "youtube": YouTubeParser,
    "vk": VKParser,
    "website": WebsiteParser,
}


def get_parser(platform: str) -> BaseParser:
    parser_class = PARSER_MAP.get(platform)
    if not parser_class:
        raise ValueError(f"Unknown platform: {platform}")
    return parser_class()


__all__ = [
    "BaseParser",
    "TelegramParser",
    "YouTubeParser",
    "VKParser",
    "WebsiteParser",
    "get_parser",
    "PARSER_MAP",
]
