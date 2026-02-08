"""Telegram message fetcher — iterates over channel/group messages via Telethon.

Handles pagination, rate limiting, and normalizes message data into
consistent dicts for downstream processing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import (
    Channel,
    Chat,
    Document,
    MessageMediaDocument,
    MessageMediaPhoto,
    PeerChannel,
    PeerChat,
    PeerUser,
    User,
)

logger = logging.getLogger(__name__)

# Rate-limiting constants
_MESSAGES_PER_SLEEP_BATCH = 100
_SLEEP_BETWEEN_BATCHES = 0.5


class MessageFetcher:
    """Fetch and normalize messages from Telegram entities via Telethon.

    The ``client`` must already be connected and authorized before
    being passed to the constructor.
    """

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    # ── Public API ────────────────────────────────────────────────────────

    async def fetch_messages(
        self,
        entity_id: int | str,
        limit: int = 500,
        offset_id: int = 0,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_reactions: int = 0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Iterate over messages for the given entity, yielding normalized dicts.

        Parameters
        ----------
        entity_id:
            Telegram entity ID or username (e.g. ``-1001234567890`` or ``"durov"``).
        limit:
            Maximum number of messages to yield.
        offset_id:
            Start iterating from this message ID (for incremental export).
        date_from / date_to:
            Optional datetime bounds (inclusive).
        min_reactions:
            Skip messages with fewer total reactions than this value.

        Yields
        ------
        dict
            Normalized message data including text, author info, metrics, and
            the original Telethon ``Message`` object under ``raw_message``.
        """
        entity = await self._client.get_entity(entity_id)
        logger.info(
            "Fetching messages from entity %s (limit=%d, offset_id=%d)",
            entity_id,
            limit,
            offset_id,
        )

        yielded = 0
        counter = 0

        async for message in self._client.iter_messages(
            entity,
            limit=limit,
            offset_id=offset_id,
            offset_date=date_to,
            reverse=False,
        ):
            counter += 1

            # Rate-limit: sleep periodically to avoid Telegram flood bans
            if counter % _MESSAGES_PER_SLEEP_BATCH == 0:
                logger.debug(
                    "Processed %d messages, sleeping %.1fs for rate limit",
                    counter,
                    _SLEEP_BETWEEN_BATCHES,
                )
                await asyncio.sleep(_SLEEP_BETWEEN_BATCHES)

            # Date bounds filtering
            msg_date = message.date
            if date_from and msg_date and msg_date < date_from:
                # Messages are newest-first; once we pass date_from we're done
                break
            if date_to and msg_date and msg_date > date_to:
                continue

            # Compute total reactions
            reactions_count = _sum_reactions(message)

            # Filter by minimum reactions
            if min_reactions and reactions_count < min_reactions:
                continue

            # Resolve author info
            author_id, author_username, author_name = await self._resolve_author(
                message,
            )

            # Detect media type
            has_media, media_type = _detect_media(message)

            record: dict[str, Any] = {
                "message_id": message.id,
                "text": message.text or "",
                "date": msg_date,
                "author_id": author_id,
                "author_username": author_username,
                "author_name": author_name,
                "views": getattr(message, "views", 0) or 0,
                "forwards": getattr(message, "forwards", 0) or 0,
                "reactions_count": reactions_count,
                "has_media": has_media,
                "media_type": media_type,
                "reply_to_msg_id": (
                    message.reply_to.reply_to_msg_id
                    if message.reply_to
                    else None
                ),
                "raw_message": message,
            }

            yield record
            yielded += 1

        logger.info(
            "Finished fetching from %s: yielded %d messages (scanned %d)",
            entity_id,
            yielded,
            counter,
        )

    async def get_entity_info(self, entity_id: int | str) -> dict[str, Any]:
        """Return basic information about a Telegram entity.

        Returns
        -------
        dict
            Keys: ``id``, ``type``, ``title``, ``username``, ``participants_count``.
        """
        entity = await self._client.get_entity(entity_id)

        entity_type = "chat"
        title = ""
        username = None
        participants_count = 0

        if isinstance(entity, Channel):
            entity_type = "channel" if entity.broadcast else "group"
            title = entity.title or ""
            username = entity.username
            participants_count = getattr(entity, "participants_count", 0) or 0
        elif isinstance(entity, Chat):
            entity_type = "group"
            title = entity.title or ""
            participants_count = getattr(entity, "participants_count", 0) or 0
        elif isinstance(entity, User):
            entity_type = "chat"
            title = " ".join(
                filter(None, [entity.first_name, entity.last_name]),
            )
            username = entity.username

        return {
            "id": entity.id,
            "type": entity_type,
            "title": title,
            "username": username,
            "participants_count": participants_count,
        }

    async def get_user_folders(self) -> list[dict[str, Any]]:
        """Return the authenticated user's dialog folders.

        Uses ``GetDialogFiltersRequest`` to retrieve Telegram folder list.

        Returns
        -------
        list[dict]
            Each dict contains: ``id``, ``title``, ``include_peers`` (count).
        """
        result = await self._client(GetDialogFiltersRequest())

        folders: list[dict[str, Any]] = []
        for dialog_filter in result:
            # DialogFilter objects have id, title, include_peers, etc.
            filter_id = getattr(dialog_filter, "id", None)
            filter_title = getattr(dialog_filter, "title", None)

            if filter_id is None or filter_title is None:
                # Skip built-in "All Chats" filter which may lack these
                continue

            include_peers = getattr(dialog_filter, "include_peers", []) or []
            folders.append({
                "id": filter_id,
                "title": filter_title,
                "include_peers": len(include_peers),
            })

        logger.info("Retrieved %d user folders", len(folders))
        return folders

    async def get_folder_dialogs(self, folder_id: int) -> list[dict[str, Any]]:
        """Retrieve dialogs (entities) belonging to a specific folder.

        Parameters
        ----------
        folder_id:
            The numeric ID of the Telegram folder.

        Returns
        -------
        list[dict]
            Entity info dicts (same shape as :meth:`get_entity_info`).
        """
        result = await self._client(GetDialogFiltersRequest())

        target_filter = None
        for dialog_filter in result:
            if getattr(dialog_filter, "id", None) == folder_id:
                target_filter = dialog_filter
                break

        if target_filter is None:
            logger.warning("Folder %d not found", folder_id)
            return []

        include_peers = getattr(target_filter, "include_peers", []) or []
        dialogs: list[dict[str, Any]] = []

        for input_peer in include_peers:
            peer = getattr(input_peer, "peer", input_peer)
            peer_id = _extract_peer_id(peer)
            if peer_id is None:
                continue

            try:
                info = await self.get_entity_info(peer_id)
                dialogs.append(info)
            except Exception:
                logger.warning(
                    "Could not resolve entity for peer %s in folder %d",
                    peer_id,
                    folder_id,
                    exc_info=True,
                )

        logger.info(
            "Folder %d (%s): resolved %d dialogs out of %d peers",
            folder_id,
            getattr(target_filter, "title", ""),
            len(dialogs),
            len(include_peers),
        )
        return dialogs

    # ── Private helpers ───────────────────────────────────────────────────

    async def _resolve_author(
        self,
        message: Any,
    ) -> tuple[int | None, str | None, str | None]:
        """Resolve author ID, username, and display name from a message."""
        sender = message.sender
        if sender is None:
            try:
                sender = await message.get_sender()
            except Exception:
                return None, None, None

        if sender is None:
            return None, None, None

        author_id = sender.id
        author_username = getattr(sender, "username", None)

        if isinstance(sender, User):
            first = sender.first_name or ""
            last = sender.last_name or ""
            author_name = f"{first} {last}".strip() or None
        elif isinstance(sender, (Channel, Chat)):
            author_name = getattr(sender, "title", None)
        else:
            author_name = None

        return author_id, author_username, author_name


# ── Module-level helpers ──────────────────────────────────────────────────


def _sum_reactions(message: Any) -> int:
    """Sum all reaction counts on a message."""
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return 0
    results = getattr(reactions, "results", None)
    if not results:
        return 0
    return sum(r.count for r in results if hasattr(r, "count"))


def _detect_media(message: Any) -> tuple[bool, str | None]:
    """Detect whether a message has media and its type."""
    media = message.media
    if media is None:
        return False, None

    if isinstance(media, MessageMediaPhoto):
        return True, "photo"

    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if isinstance(doc, Document):
            for attr in doc.attributes:
                attr_name = type(attr).__name__
                if attr_name == "DocumentAttributeAudio":
                    if getattr(attr, "voice", False):
                        return True, "voice"
                    return True, "audio"
                if attr_name == "DocumentAttributeVideo":
                    if getattr(attr, "round_message", False):
                        return True, "video_note"
                    return True, "video"
            # Fallback for generic documents
            return True, "document"

    return True, "other"


def _extract_peer_id(peer: Any) -> int | None:
    """Extract the numeric ID from a Telethon Peer object."""
    if isinstance(peer, PeerChannel):
        return peer.channel_id
    if isinstance(peer, PeerChat):
        return peer.chat_id
    if isinstance(peer, PeerUser):
        return peer.user_id
    # Some InputPeer types expose the ID directly
    for attr in ("channel_id", "chat_id", "user_id"):
        val = getattr(peer, attr, None)
        if val is not None:
            return val
    return None
