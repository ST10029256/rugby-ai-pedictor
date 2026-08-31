#!/usr/bin/env python3
"""Check Nations Championship 2026 standings from SportRadar + Highlightly APIs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUGBY = ROOT / "rugby-ai-predictor"
sys.path.insert(0, str(RUGBY))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(RUGBY / ".env")
load_dotenv(RUGBY / ".env.local")

from prediction.highlightly_client import HighlightlyRugbyAPI
from prediction.sportradar_client import SportRadarRugbyClient, normalize_sportradar_standings

LOCAL_ID = 5480
HL_ID = 124179
SR_COMP = "sr:competition:51392"
SR_SEASON_2026 = "sr:season:141456"


def summarize_rows(standings: dict) -> tuple[int, int, list[str]]:
    groups = standings.get("groups") or []
    rows = []
    for g in groups:
        if isinstance(g, dict):
            rows.extend(g.get("standings") or g.get("teams") or [])
    max_played = 0
    sample = []
    for r in rows[:5]:
        t = (r.get("team") or {}).get("name") or r.get("name") or "?"
        played = int(r.get("played") or r.get("gamesPlayed") or 0)
        max_played = max(max_played, played)
        sample.append(f"  #{r.get('position')} {t} — Pld {played} Pts {r.get('points')}")
    for r in rows[5:]:
        played = int(r.get("played") or r.get("gamesPlayed") or 0)
        max_played = max(max_played, played)
    return len(rows), max_played, sample


def check_sportradar() -> None:
    print("=== SportRadar (Nations Championship 2026) ===")
    key = os.getenv("SPORTRADAR_API_KEY") or os.getenv("SPORTRADAR_RUGBY_API_KEY") or ""
    print(f"  Key configured: {bool(key)}")
    if not key:
        print("  SKIP — no SPORTRADAR_API_KEY")
        return

    client = SportRadarRugbyClient(api_key=key)
    raw = client.fetch_standings_raw(SR_SEASON_2026)
    if not raw:
        print(f"  standings.json for {SR_SEASON_2026}: NO RESPONSE (404 or rate-limited)")
        if getattr(client, "rate_limited", False):
            print("  Reason: rate limited (429)")
        return

    print(f"  Raw response keys: {list(raw.keys())}")
    norm = normalize_sportradar_standings(
        raw,
        league_name="Nations Championship",
        display_season=2026,
        competition_id=SR_COMP,
    )
    n, max_played, sample = summarize_rows(norm)
    print(f"  Normalized table: {n} teams, max games played = {max_played}")
    for line in sample:
        print(line)
    if n == 0:
        print("  Payload snippet:", json.dumps(raw, indent=2)[:1200])


def check_highlightly() -> None:
    print("\n=== Highlightly (league 124179, season 2026) ===")
    key = os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY") or ""
    print(f"  Key configured: {bool(key)}")
    if not key:
        print("  SKIP — no HIGHLIGHTLY_API_KEY")
        return

    api = HighlightlyRugbyAPI(api_key=key, use_rapidapi=bool(os.getenv("RAPIDAPI_KEY")))
    try:
        data = api.get_standings(HL_ID, 2026)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return

    if not data:
        print("  Empty response")
        return

    if isinstance(data, dict):
        err = data.get("error") or data.get("message")
        if err:
            print(f"  API message: {err}")
        n, max_played, sample = summarize_rows(data if "groups" in data else {"groups": data.get("data", [])})
        print(f"  Teams in response: {n}, max played = {max_played}")
        for line in sample:
            print(line)
        if n == 0:
            print("  Payload snippet:", json.dumps(data, indent=2)[:1200])


if __name__ == "__main__":
    check_sportradar()
    check_highlightly()
