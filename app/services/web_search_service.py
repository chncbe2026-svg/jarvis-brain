"""
JARVIS Web Search Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fetches real information from the web using DuckDuckGo (free, no API key).
Results are returned as structured text ready to inject into the LLM prompt.
Can optionally store results into JARVIS memory so he "learns" from searches.
"""

import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search the web using DuckDuckGo.
    Returns a list of {title, url, snippet} dicts.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        logger.info(f"[WebSearch] ✅ Found {len(results)} results for: {query}")
        return results

    except ImportError:
        logger.error("[WebSearch] ❌ duckduckgo_search not installed. Run: pip install duckduckgo-search")
        return []
    except Exception as e:
        logger.error(f"[WebSearch] ❌ Search failed: {e}")
        return []


def format_results_for_llm(results: List[Dict], query: str) -> str:
    """
    Format search results into a clean context block for the LLM.
    """
    if not results:
        return f"Web search for '{query}' returned no results."

    lines = [f"WEB SEARCH RESULTS for: '{query}'\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    URL: {r['url']}")
        lines.append(f"    {r['snippet']}")
        lines.append("")

    return "\n".join(lines)


def is_web_search_query(text: str) -> bool:
    """
    Detect if the user is asking JARVIS to search the web.
    Matches phrases like:
    - "find X in web"
    - "search web for X"
    - "google X"
    - "look up X online"
    - "what is X" (when no local data exists)
    - "fetch X from internet"
    """
    patterns = [
        r"\b(search|find|look up|fetch|get|check)\b.{0,30}\b(web|internet|online|google)\b",
        r"\b(web|internet|online|google)\b.{0,30}\b(search|find|look up|fetch)\b",
        r"\b(google|bing|search)\s+(for\s+)?[\w\s]+",
        r"\bsearch\s+(the\s+)?(web|internet|online)\b",
        r"\blook\s+up\s+online\b",
        r"\bfind\s+.+\s+(in|on|from|via)\s+(web|internet|google)\b",
        r"\bfetch\s+.+\s+(from\s+)?(web|internet|online)\b",
        r"\bsearch\s+for\s+.+\s+online\b",
    ]
    text_lower = text.lower().strip()
    return any(re.search(p, text_lower) for p in patterns)


def extract_search_query(text: str) -> str:
    """
    Extract the actual search terms from a web search request.
    e.g. "find CHN technologies coimbatore details in web" → "CHN technologies coimbatore"
    """
    # Strip common command words
    remove_patterns = [
        r"^(please\s+)?(can you\s+)?(jarvis[,]?\s+)?",
        r"\b(search|find|look up|fetch|get|check|google|bing)\b",
        r"\b(the\s+)?(web|internet|online|google|bing)\b",
        r"\b(for|in|on|from|via|about|details|information|info)\b",
        r"\b(please|now|quickly|fast)\b",
        r"\s{2,}",
    ]
    cleaned = text.lower().strip()
    for pat in remove_patterns:
        cleaned = re.sub(pat, " ", cleaned)

    return cleaned.strip().rstrip("?.,!")
