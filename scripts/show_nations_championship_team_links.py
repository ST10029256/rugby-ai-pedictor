#!/usr/bin/env python3
"""
Show which Nations Championship teams also appear in the linked international leagues:
  - Rugby Championship (4986)
  - Rugby World Cup (4574)
  - Rugby Union International Friendlies (5479)

Usage:
  python scripts/show_nations_championship_team_links.py
  python scripts/show_nations_championship_team_links.py --db rugby-ai-predictor/data.sqlite
  python scripts/show_nations_championship_team_links.py --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PREDICTOR_ROOT = PROJECT_ROOT / "rugby-ai-predictor"
for path in (PROJECT_ROOT, RUGBY_PREDICTOR_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prediction.international_leagues import (  # noqa: E402
    INTERNATIONAL_RUGBY_CLUSTER,
    NATIONS_CHAMPIONSHIP_ID,
    build_nations_championship_team_link_report,
)


def default_db_path() -> Path:
    for candidate in (
        PROJECT_ROOT / "data.sqlite",
        RUGBY_PREDICTOR_ROOT / "data.sqlite",
    ):
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / "data.sqlite"


def _yes_no(flag: bool) -> str:
    return "YES" if flag else "no"


def print_report(report: dict) -> None:
    summary = report.get("summary") or {}
    print("=" * 88)
    print(
        f"Nations Championship team links ({report.get('nations_league_id')} - "
        f"{report.get('nations_league_name')})"
    )
    print("=" * 88)
    print(
        f"Teams: {summary.get('total_nations_teams', 0)} | "
        f"linked to all 3 sibling leagues: {summary.get('linked_all_three', 0)} | "
        f"partial links: {summary.get('linked_some', 0)} | "
        f"no sibling link: {summary.get('linked_none', 0)}"
    )
    print()

    sibling_names = list((report.get("sibling_leagues") or {}).values())
    header = (
        f"{'Nations team':<24} | {'Canonical':<16} | "
        f"{'RC':>3} | {'RWC':>3} | {'Intl Friendlies':>15} | Notes"
    )
    print(header)
    print("-" * len(header))

    rc_name = INTERNATIONAL_RUGBY_CLUSTER[4986]
    rwc_name = INTERNATIONAL_RUGBY_CLUSTER[4574]
    fr_name = INTERNATIONAL_RUGBY_CLUSTER[5479]

    for row in report.get("teams") or []:
        links = row.get("links") or {}
        rc = _yes_no((links.get(rc_name) or {}).get("linked"))
        rwc = _yes_no((links.get(rwc_name) or {}).get("linked"))
        fr = _yes_no((links.get(fr_name) or {}).get("linked"))
        notes = []
        if row.get("linked_league_count", 0) == 0:
            notes.append("not found in sibling leagues")
        elif row.get("linked_league_count", 0) < 3:
            missing = [name for name in sibling_names if not (links.get(name) or {}).get("linked")]
            notes.append("missing: " + ", ".join(missing))
        else:
            notes.append("full international coverage")
        print(
            f"{row.get('nations_team_name',''):<24} | "
            f"{row.get('canonical_key',''):<16} | "
            f"{rc:>3} | {rwc:>3} | {fr:>15} | "
            f"{'; '.join(notes)}"
        )

    print()
    print("Legend: RC=Rugby Championship, RWC=Rugby World Cup")
    print(
        "Teams marked 'no' can still receive predictions via linked models when both sides "
        "match in another league, or after Nations Championship-specific training."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map Nations Championship teams to linked international rugby leagues."
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database")
    parser.add_argument(
        "--league-id",
        type=int,
        default=NATIONS_CHAMPIONSHIP_ID,
        help="Nations Championship league id (default: 5480)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of table")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else default_db_path()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        report = build_nations_championship_team_link_report(conn, nations_league_id=int(args.league_id))
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
