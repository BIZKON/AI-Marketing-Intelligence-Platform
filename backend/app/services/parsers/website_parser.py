"""Website/blog parser using httpx + BeautifulSoup."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from hashlib import md5
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.parsers.base import BaseParser, ParsedPost

logger = logging.getLogger(__name__)

# Common selectors for blog post containers
_ARTICLE_SELECTORS = [
    "article",
    "[itemtype*='BlogPosting']",
    "[itemtype*='Article']",
    ".post",
    ".blog-post",
    ".entry",
    ".article",
]

_DATE_SELECTORS = [
    "time[datetime]",
    "[itemprop='datePublished']",
    ".date",
    ".published",
    ".post-date",
    ".entry-date",
]


class WebsiteParser(BaseParser):
    """Parser for websites and blogs via HTTP scraping."""

    @property
    def platform_name(self) -> str:
        return "website"

    async def fetch_posts(
        self,
        tracking_config: dict,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ParsedPost]:
        url = tracking_config.get("url", "")
        if not url:
            logger.warning("No URL in website tracking config")
            return []

        feed_url = tracking_config.get("rss_url", "")
        if feed_url:
            return await self._fetch_rss(feed_url, url, since, limit)

        return await self._fetch_html(url, since, limit)

    # ── RSS / Atom ───────────────────────────────────────────────────────────

    async def _fetch_rss(
        self,
        feed_url: str,
        site_url: str,
        since: datetime | None,
        limit: int,
    ) -> list[ParsedPost]:
        posts: list[ParsedPost] = []
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(feed_url, headers={"User-Agent": _UA})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item") or soup.find_all("entry")

            for item in items[:limit]:
                title = _text(item, "title")
                link = _text(item, "link") or (item.find("link") or {}).get("href", "")
                description = _text(item, "description") or _text(item, "summary") or _text(item, "content")
                pub_date = _parse_rss_date(_text(item, "pubDate") or _text(item, "published") or _text(item, "updated"))

                if since and pub_date and pub_date < since:
                    continue

                external_id = _make_external_id(site_url, link or title)
                posts.append(ParsedPost(
                    external_id=external_id,
                    platform="website",
                    title=title,
                    text_content=_strip_html(description),
                    url=link,
                    published_at=pub_date,
                    raw_data={"source": "rss", "feed_url": feed_url},
                ))

            logger.info("Website(RSS): fetched %d posts from %s", len(posts), feed_url)

        except Exception:
            logger.exception("Failed to fetch RSS from %s", feed_url)

        return posts

    # ── HTML scraping ────────────────────────────────────────────────────────

    async def _fetch_html(
        self,
        url: str,
        since: datetime | None,
        limit: int,
    ) -> list[ParsedPost]:
        posts: list[ParsedPost] = []
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": _UA})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            domain = urlparse(url).netloc

            # Try to find article blocks
            articles = _find_articles(soup)

            if not articles:
                # Fallback: treat the whole page as a single content block
                text = soup.get_text(separator="\n", strip=True)[:5000]
                if text:
                    posts.append(ParsedPost(
                        external_id=_make_external_id(domain, url),
                        platform="website",
                        title=_extract_title(soup),
                        text_content=text,
                        url=url,
                        published_at=_extract_date(soup),
                        raw_data={"source": "html_page", "url": url},
                    ))
                logger.info("Website(HTML): single page mode for %s", url)
                return posts

            for article in articles[:limit]:
                title = _extract_title(article)
                link = _extract_link(article, url)
                text = article.get_text(separator="\n", strip=True)[:3000]
                pub_date = _extract_date(article)

                if since and pub_date and pub_date < since:
                    continue

                images = [
                    urljoin(url, img["src"])
                    for img in article.find_all("img", src=True)[:5]
                ]

                external_id = _make_external_id(domain, link or title or text[:100])
                posts.append(ParsedPost(
                    external_id=external_id,
                    platform="website",
                    title=title,
                    text_content=text,
                    url=link or url,
                    media_urls=images,
                    published_at=pub_date,
                    raw_data={"source": "html_scrape", "url": url},
                ))

            logger.info("Website(HTML): fetched %d posts from %s", len(posts), url)

        except Exception:
            logger.exception("Failed to scrape %s", url)

        return posts


# ── Helpers ──────────────────────────────────────────────────────────────────

_UA = (
    "Mozilla/5.0 (compatible; MarketingIntelBot/1.0; +https://example.com/bot)"
)


def _text(tag, name: str) -> str:
    """Extract text from a child tag."""
    child = tag.find(name)
    return child.get_text(strip=True) if child else ""


def _strip_html(html: str) -> str:
    """Remove HTML tags from a string."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)


def _find_articles(soup: BeautifulSoup) -> list:
    """Try multiple selectors to find article-like blocks."""
    for selector in _ARTICLE_SELECTORS:
        articles = soup.select(selector)
        if len(articles) >= 2:
            return articles
    return []


def _extract_title(tag) -> str | None:
    """Pull a title from heading tags or common attributes."""
    for sel in ("h1", "h2", "h3", "[itemprop='headline']", ".title", ".entry-title"):
        el = tag.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return None


def _extract_link(tag, base_url: str) -> str | None:
    """Get the first link from a tag, resolved to absolute."""
    a = tag.find("a", href=True)
    if a:
        href = a["href"]
        if href.startswith("http"):
            return href
        return urljoin(base_url, href)
    return None


def _extract_date(tag) -> datetime | None:
    """Try to parse a date from common selectors."""
    for selector in _DATE_SELECTORS:
        el = tag.select_one(selector)
        if el:
            raw = el.get("datetime") or el.get("content") or el.get_text(strip=True)
            parsed = _parse_rss_date(raw)
            if parsed:
                return parsed
    return None


def _parse_rss_date(raw: str) -> datetime | None:
    """Parse common date formats from RSS/HTML."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",      # RFC 822
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",             # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _make_external_id(domain: str, content: str) -> str:
    """Create a deterministic external ID."""
    h = md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
    # Strip non-alnum from domain
    clean_domain = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    return f"web_{clean_domain}_{h}"
