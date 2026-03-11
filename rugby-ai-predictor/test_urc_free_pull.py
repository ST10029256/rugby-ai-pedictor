"""
Free URC proof-of-concept fetch (no X API needed).

Pulls:
- 1 general URC news item
- 1 lineup-related URC item

Usage (PowerShell):
  python rugby-ai-predictor\test_urc_free_pull.py
"""

from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests


def _google_news_rss_url(query: str) -> str:
    encoded = quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-ZA&gl=ZA&ceid=ZA:en"


def _parse_rss_items(xml_text: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: List[Dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        published_at: Optional[str] = None
        if pub_date_raw:
            try:
                published_at = parsedate_to_datetime(pub_date_raw).isoformat()
            except Exception:
                published_at = pub_date_raw

        items.append(
            {
                "title": title,
                "url": link,
                "published_at": published_at,
                "summary": description,
                "source": "Google News RSS",
            }
        )
    return items


def _fetch_one(query: str) -> Optional[Dict[str, Any]]:
    url = _google_news_rss_url(query)
    resp = requests.get(url, timeout=25)
    resp.raise_for_status()
    items = _parse_rss_items(resp.text)
    return items[0] if items else None


def main() -> None:
    general_query = '"Vodacom United Rugby Championship" OR "United Rugby Championship"'
    lineup_query = (
        '"Vodacom United Rugby Championship" (lineup OR "starting xv" OR "team news" OR "squad announcement")'
    )

    general_item: Optional[Dict[str, Any]] = None
    lineup_item: Optional[Dict[str, Any]] = None
    errors: List[str] = []

    try:
        general_item = _fetch_one(general_query)
    except Exception as e:
        errors.append(f"General news fetch failed: {e}")

    try:
        lineup_item = _fetch_one(lineup_query)
    except Exception as e:
        errors.append(f"Lineup news fetch failed: {e}")

    payload = {
        "mode": "free_rss_fallback",
        "competition": "Vodacom United Rugby Championship",
        "news_item": general_item,
        "lineup_item": lineup_item,
        "lineup_found": lineup_item is not None,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

