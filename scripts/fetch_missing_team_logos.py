#!/usr/bin/env python3
"""Fetch missing rugby team logo URLs from API-Sports and print STATIC_TEAM_LOGOS entries."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PREDICTOR_ROOT = PROJECT_ROOT / "rugby-ai-predictor"
for path in (PROJECT_ROOT, RUGBY_PREDICTOR_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from prediction.config import STATIC_TEAM_LOGOS  # noqa: E402

SEARCH_TEAMS = [
    "canada",
    "usa",
    "united states",
    "spain",
    "belgium",
    "brazil",
    "russia",
    "zimbabwe",
    "kenya",
    "hong kong",
    "western province",
    "wasps",
    "london irish",
    "jaguares",
    "sunwolves",
    "southern kings",
    "treviso",
    "aironi",
    "border bulldogs",
    "griffons",
    "leopards",
    "welwitschias",
    "barbarians",
    "germany",
    "netherlands",
    "poland",
    "colombia",
    "worcester warriors",
    "london welsh",
    "jaguares",
    "la rochelle",
    "stade francais",
    "toulouse",
    "perpignan",
    "castres",
    "biarritz",
    "agen",
    "vannes",
    "provence rugby",
]


def norm_key(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_api_key() -> str | None:
    if load_dotenv:
        load_dotenv(RUGBY_PREDICTOR_ROOT / ".env")
        load_dotenv(RUGBY_PREDICTOR_ROOT / ".env.local")
    return os.getenv("APISPORTS_RUGBY_KEY") or os.getenv("APISPORTS_KEY")


def search_logo(api_key: str, term: str) -> tuple[str | None, str | None]:
    url = "https://v1.rugby.api-sports.io/teams"
    headers = {"x-apisports-key": api_key}
    try:
        resp = requests.get(url, params={"search": term}, headers=headers, timeout=20)
        resp.raise_for_status()
        rows = resp.json().get("response") or []
        if not rows:
            return None, None
        row = rows[0]
        logo = row.get("logo")
        name = row.get("name")
        if logo:
            return str(logo), str(name or term)
    except Exception as exc:
        print(f"  ! search failed for {term!r}: {exc}", file=sys.stderr)
    return None, None


def main() -> int:
    api_key = load_api_key()
    if not api_key:
        print("No APISPORTS_RUGBY_KEY in env", file=sys.stderr)
        return 1

    found: dict[str, str] = {}
    for term in SEARCH_TEAMS:
        key = norm_key(term)
        if key in STATIC_TEAM_LOGOS or key in found:
            continue
        logo, matched = search_logo(api_key, term)
        if logo:
            found[key] = logo
            print(f'    "{key}": "{logo}",  # {matched}')
        time.sleep(0.35)

    print(f"\n# Found {len(found)} new logos", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
