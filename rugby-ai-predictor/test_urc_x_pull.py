"""
One-shot X (Twitter) API pull for URC:
- 1 general news post
- 1 lineup-related post

Usage (PowerShell):
  $env:TWITTER_BEARER_TOKEN="YOUR_TOKEN"
  python test_urc_x_pull.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.twitter.com/2"
GENERAL_QUERY = '"Vodacom United Rugby Championship" lang:en -is:retweet'
LINEUP_QUERY = (
    '"Vodacom United Rugby Championship" '
    '(lineup OR "starting xv" OR "team news" OR "matchday squad" OR "team announcement") '
    "lang:en -is:retweet"
)


def _headers() -> Dict[str, str]:
    token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TWITTER_BEARER_TOKEN is not set.")
    return {"Authorization": f"Bearer {token}"}


def _search_recent(query: str, max_results: int = 10) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    url = f"{BASE_URL}/tweets/search/recent"
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "created_at,text,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }
    resp = requests.get(url, headers=_headers(), params=params, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    tweets = body.get("data", [])
    users = body.get("includes", {}).get("users", [])
    author_map = {u.get("id"): u.get("username") for u in users if u.get("id") and u.get("username")}
    return tweets, author_map


def _to_output(tweet: Dict[str, Any], author_map: Dict[str, str]) -> Dict[str, Any]:
    tweet_id = tweet.get("id")
    author_id = tweet.get("author_id")
    username = author_map.get(author_id)
    if username and tweet_id:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif tweet_id:
        url = f"https://x.com/i/web/status/{tweet_id}"
    else:
        url = None
    return {
        "id": tweet_id,
        "created_at": tweet.get("created_at"),
        "text": tweet.get("text", ""),
        "author_username": username,
        "url": url,
        "metrics": tweet.get("public_metrics", {}),
    }


def main() -> None:
    # 1) One general URC post.
    general_posts, general_authors = _search_recent(GENERAL_QUERY, max_results=10)
    if not general_posts:
        raise RuntimeError("No recent URC posts found for the general query.")
    one_news = _to_output(general_posts[0], general_authors)

    # 2) One lineup-related URC post.
    lineup_posts, lineup_authors = _search_recent(LINEUP_QUERY, max_results=10)
    one_lineup = _to_output(lineup_posts[0], lineup_authors) if lineup_posts else None

    payload = {
        "mode": "x_api_two_requests",
        "request_count": 2,
        "general_query": GENERAL_QUERY,
        "lineup_query": LINEUP_QUERY,
        "news_post": one_news,
        "lineup_post": one_lineup,
        "lineup_found": one_lineup is not None,
    }

    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
