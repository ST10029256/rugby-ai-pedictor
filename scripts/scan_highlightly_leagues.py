#!/usr/bin/env python3
"""
Scan Highlightly for all configured rugby leagues using the latest available season.

Uses leagueId + season pagination (NOT day-by-day scans) to minimise API calls.
Output is printed and written to artifacts/highlightly_scan_latest.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.highlightly_client import HighlightlyRugbyAPI  # noqa: E402
from prediction.highlightly_leagues import (  # noqa: E402
    HIGHLIGHTLY_LEAGUE_MAPPINGS,
    parse_api_key,
    scan_league_summary,
)

logger = logging.getLogger(__name__)


def _load_env() -> None:
    if load_dotenv is None:
        return
    for path in (
        ROOT / ".env",
        ROOT / "rugby-ai-predictor" / ".env",
        ROOT / "rugby-ai-predictor" / ".env.local",
    ):
        if path.exists():
            load_dotenv(path, override=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Highlightly leagues (latest season, low API usage)")
    parser.add_argument("--api-key", default=None, help="Highlightly API key (or HIGHLIGHTLY_API_KEY env)")
    parser.add_argument("--page-size", type=int, default=100, help="Pagination page size (default 100)")
    parser.add_argument("--sleep", type=float, default=0.35, help="Delay between API calls in seconds")
    parser.add_argument(
        "--output",
        default=str(ROOT / "artifacts" / "highlightly_scan_latest.json"),
        help="JSON output path",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    _load_env()
    api_key = parse_api_key(args.api_key)
    api = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=False)

    probe = api.get_leagues(limit=1)
    if not probe.get("data"):
        raise SystemExit(
            "Highlightly auth failed (no data returned). "
            "Check HIGHLIGHTLY_API_KEY in rugby-ai-predictor/.env."
        )

    today = datetime.now(timezone.utc)
    request_counter = [0]
    league_results = []

    print("=" * 88)
    print("Highlightly scan — latest season per league")
    print("=" * 88)

    for our_id, (name, hl_id) in sorted(HIGHLIGHTLY_LEAGUE_MAPPINGS.items(), key=lambda x: x[1][0]):
        logger.info("Scanning %s (our=%s hl=%s)", name, our_id, hl_id)
        league_result = scan_league_summary(
            api,
            our_id,
            name,
            hl_id,
            today,
            max(1, min(args.page_size, 100)),
            request_counter,
            max(0.0, args.sleep),
        )
        league_results.append(league_result)

        print(
            f"{name:40} season={league_result.get('selected_season')} "
            f"total={league_result.get('matches_total')} "
            f"upcoming={league_result.get('upcoming')} "
            f"completed={league_result.get('completed')}"
        )
        if league_result.get("error"):
            print(f"  ! {league_result['error']}")
        for m in (league_result.get("upcoming_matches") or [])[:5]:
            print(f"  - {m['date_only']} {m['home_team']} vs {m['away_team']}")
        if league_result.get("upcoming", 0) > 5:
            print(f"  ... +{league_result['upcoming'] - 5} more upcoming")
        print()

    payload = {
        "scanned_at": today.isoformat(),
        "provider": "highlightly",
        "api_requests": request_counter[0],
        "leagues": league_results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    total_upcoming = sum(int(r.get("upcoming") or 0) for r in league_results)
    print("=" * 88)
    print(f"API requests used: {request_counter[0]}")
    print(f"Total upcoming fixtures: {total_upcoming}")
    print(f"Saved: {out_path}")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
