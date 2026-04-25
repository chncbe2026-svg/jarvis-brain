import feedparser
import hashlib
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Optional

from app.services.rag_service import get_rag_service
from app.services.qdrant_client import get_qdrant_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Feed configuration ─────────────────────────────────────────────────────────
RSS_FEEDS: List[Dict] = [
    {
        "url": "https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml",
        "vendor": "Cisco",
        "feed_type": "advisory",
    },
    {
        "url": "https://blog.talosintelligence.com/rss/",
        "vendor": "Cisco",
        "feed_type": "blog",
    },
    {
        "url": "https://msrc.microsoft.com/blog/feed",
        "vendor": "Microsoft",
        "feed_type": "advisory",
    },
    {
        "url": "https://www.microsoft.com/en-us/security/blog/feed/",
        "vendor": "Microsoft",
        "feed_type": "blog",
    },
]

# ─── Severity heuristics ────────────────────────────────────────────────────────
_SEVERITY_KEYWORDS = {
    "Critical": ["critical", "rce", "remote code execution", "zero-day", "0day"],
    "High":     ["high", "privilege escalation", "authentication bypass", "sql injection"],
    "Medium":   ["medium", "xss", "csrf", "information disclosure"],
    "Low":      ["low", "denial of service"],
}

def _infer_severity(text: str) -> str:
    lower = text.lower()
    for severity, keywords in _SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return severity
    return "Informational"

def _strip_html(html_text: str) -> str:
    return BeautifulSoup(html_text or "", "html.parser").get_text(separator=" ").strip()

def _normalise_date(entry) -> str:
    """Return ISO-8601 date string from feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _dedupe_hash(link: str, title: str) -> str:
    """Generate a stable deduplication hash for an article."""
    return hashlib.md5(f"{link}::{title}".encode()).hexdigest()


class RSSService:
    def __init__(self):
        self._seen_hashes: set = set()

    def _already_indexed(self, dedup_hash: str) -> bool:
        """Check if entry exists in Qdrant by searching the vendor_news collection."""
        if dedup_hash in self._seen_hashes:
            return True

        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        qdrant = get_qdrant_client()
        try:
            results, _ = qdrant.scroll(
                collection_name=settings.COLLECTION_VENDOR,
                scroll_filter=Filter(
                    must=[FieldCondition(key="dedup_hash", match=MatchValue(value=dedup_hash))]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            found = len(results) > 0
            if found:
                self._seen_hashes.add(dedup_hash)
            return found
        except Exception:
            return False

    async def sync_feeds(self) -> int:
        rag = get_rag_service()
        total_ingested = 0

        for feed_cfg in RSS_FEEDS:
            url = feed_cfg["url"]
            vendor = feed_cfg["vendor"]
            feed_type = feed_cfg["feed_type"]

            logger.info(f"[RSS] Fetching {vendor} feed: {url}")
            try:
                feed = feedparser.parse(url)
            except Exception as e:
                logger.error(f"[RSS] Failed to parse {url}: {e}")
                continue

            for entry in feed.entries[:10]:  # latest 10 per feed
                try:
                    title = entry.get("title", "Untitled")
                    link = entry.get("link", "")
                    summary_html = entry.get("summary", entry.get("content", [{}])[0].get("value", ""))
                    summary = _strip_html(summary_html)
                    published = _normalise_date(entry)

                    # Skip if already indexed
                    dedup_hash = _dedupe_hash(link, title)
                    if self._already_indexed(dedup_hash):
                        logger.debug(f"[RSS] Skipping duplicate: {title}")
                        continue

                    # Compose content for embedding
                    content = f"Title: {title}\nVendor: {vendor}\nDate: {published}\n\n{summary}"

                    severity = _infer_severity(content)

                    metadata = {
                        "vendor": vendor,
                        "feed_type": feed_type,
                        "severity": severity,
                        "published": published,
                        "title": title,
                        "link": link,
                        "source": url,
                        "type": "rss_news",
                        "dedup_hash": dedup_hash,
                    }

                    await rag.ingest_text(content, metadata, settings.COLLECTION_VENDOR)
                    self._seen_hashes.add(dedup_hash)
                    total_ingested += 1
                    logger.info(f"[RSS] Ingested [{severity}] {vendor}: {title}")

                except Exception as e:
                    logger.error(f"[RSS] Entry error ({vendor}): {e}")

        logger.info(f"[RSS] Sync complete. Total new items: {total_ingested}")
        return total_ingested


rss_service = RSSService()

def get_rss_service() -> RSSService:
    return rss_service
