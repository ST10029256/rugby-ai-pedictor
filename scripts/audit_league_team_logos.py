#!/usr/bin/env python3
"""
Audit team logos and duplicate team names across all 10 app leagues.

For each league (from SQLite event/team data):
  - Lists every distinct team side
  - Reports whether a static crest URL resolves (same fallbacks as the app)
  - Flags duplicate sides (e.g. "Portugal" + "Portugal Rugby" as separate team rows)

Usage:
  python scripts/audit_league_team_logos.py
  python scripts/audit_league_team_logos.py --db rugby-ai-predictor/data.sqlite
  python scripts/audit_league_team_logos.py --json
  python scripts/audit_league_team_logos.py --league-id 4574
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PREDICTOR_ROOT = PROJECT_ROOT / "rugby-ai-predictor"
for path in (PROJECT_ROOT, RUGBY_PREDICTOR_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prediction.config import STATIC_TEAM_LOGOS  # noqa: E402
from prediction.international_leagues import (  # noqa: E402
    is_international_rugby_league,
    normalize_international_team_name,
)
from prediction.standings_logos import (  # noqa: E402
    STANDINGS_TEAM_OVERRIDES,
    _norm_compact,
    _norm_name,
    _search_terms,
    _strip_club_suffix,
)

ALL_LEAGUES: Dict[int, str] = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
    5480: "Nations Championship",
}


def default_db_path() -> Path:
    for candidate in (
        PROJECT_ROOT / "data.sqlite",
        RUGBY_PREDICTOR_ROOT / "data.sqlite",
    ):
        if candidate.exists():
            return candidate
    return RUGBY_PREDICTOR_ROOT / "data.sqlite"


def teams_for_league(conn: sqlite3.Connection, league_id: int) -> Dict[int, str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT t.id, t.name
        FROM team t
        JOIN event e ON t.id IN (e.home_team_id, e.away_team_id)
        WHERE e.league_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (int(league_id),),
    )
    return {int(row[0]): str(row[1]) for row in cur.fetchall()}


def resolve_static_logo(team_name: str, league_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Return (logo_url, source_label) using offline static fallbacks only."""
    for term in _search_terms(team_name):
        key = _norm_name(term)
        url = STATIC_TEAM_LOGOS.get(key)
        if url:
            return url, f"static:{key}"

    if is_international_rugby_league(league_id):
        intl_key = normalize_international_team_name(team_name)
        url = STATIC_TEAM_LOGOS.get(intl_key)
        if url:
            return url, f"static_intl:{intl_key}"

    return None, None


def soft_duplicate_key(team_name: str, league_id: int) -> str:
    """Key used to spot duplicate sides (Portugal vs Portugal Rugby)."""
    if is_international_rugby_league(league_id):
        return normalize_international_team_name(team_name)
    stripped = _strip_club_suffix(team_name)
    return _norm_compact(stripped or team_name)


def find_duplicate_groups(
    teams: Dict[int, str], league_id: int
) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for team_id, team_name in teams.items():
        key = soft_duplicate_key(team_name, league_id)
        if not key:
            continue
        buckets[key].append({"team_id": team_id, "team_name": team_name})

    groups: List[Dict[str, Any]] = []
    for key, members in sorted(buckets.items(), key=lambda x: x[0]):
        unique_names = sorted({m["team_name"] for m in members})
        unique_ids = sorted({m["team_id"] for m in members})
        if len(unique_ids) <= 1:
            continue
        # Same side with accent/spelling variants only — UI dedupe handles these.
        norm_names = {_norm_name(n) for n in unique_names}
        if len(norm_names) == 1:
            continue
        groups.append(
            {
                "canonical_key": key,
                "team_ids": unique_ids,
                "team_names": unique_names,
                "members": sorted(members, key=lambda m: m["team_name"].lower()),
            }
        )
    return groups


def audit_league(conn: sqlite3.Connection, league_id: int, league_name: str) -> Dict[str, Any]:
    teams = teams_for_league(conn, league_id)
    duplicate_groups = find_duplicate_groups(teams, league_id)

    team_rows: List[Dict[str, Any]] = []
    logos_found = 0
    logos_missing = 0

    for team_id, team_name in sorted(teams.items(), key=lambda x: x[1].lower()):
        logo_url, logo_source = resolve_static_logo(team_name, league_id)
        has_logo = bool(logo_url)
        if has_logo:
            logos_found += 1
        else:
            logos_missing += 1
        team_rows.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "soft_key": soft_duplicate_key(team_name, league_id),
                "logo_found": has_logo,
                "logo_url": logo_url,
                "logo_source": logo_source,
            }
        )

    return {
        "league_id": league_id,
        "league_name": league_name,
        "team_count": len(teams),
        "logos_found": logos_found,
        "logos_missing": logos_missing,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "teams": team_rows,
    }


def print_report(reports: List[Dict[str, Any]]) -> None:
    total_teams = sum(r["team_count"] for r in reports)
    total_found = sum(r["logos_found"] for r in reports)
    total_missing = sum(r["logos_missing"] for r in reports)
    total_dupe_groups = sum(r["duplicate_group_count"] for r in reports)

    print("=" * 96)
    print("League team logo audit (all 10 leagues)")
    print("=" * 96)
    print(
        f"Totals: {total_teams} teams | logos found: {total_found} | "
        f"missing: {total_missing} | duplicate groups: {total_dupe_groups}"
    )
    print()
    print(
        f"{'League':<42} | {'ID':>4} | {'Teams':>5} | {'Logos':>5} | "
        f"{'Miss':>4} | {'Dupes':>5}"
    )
    print("-" * 96)
    for row in reports:
        print(
            f"{row['league_name']:<42} | {row['league_id']:>4} | "
            f"{row['team_count']:>5} | {row['logos_found']:>5} | "
            f"{row['logos_missing']:>4} | {row['duplicate_group_count']:>5}"
        )

    print()
    print("=" * 96)
    print("Duplicate team groups (same side, multiple DB rows / names)")
    print("=" * 96)
    any_dupes = False
    for row in reports:
        if not row["duplicate_groups"]:
            continue
        any_dupes = True
        print()
        print(f"[{row['league_id']}] {row['league_name']}")
        for group in row["duplicate_groups"]:
            names = " | ".join(group["team_names"])
            ids = ", ".join(str(i) for i in group["team_ids"])
            print(f"  key={group['canonical_key']!r}  ids=[{ids}]")
            print(f"    names: {names}")

    if not any_dupes:
        print("No duplicate groups detected.")

    print()
    print("=" * 96)
    print("Missing static logos (offline fallback would show letter avatar)")
    print("=" * 96)
    any_missing = False
    for row in reports:
        missing = [t for t in row["teams"] if not t["logo_found"]]
        if not missing:
            continue
        any_missing = True
        print()
        print(f"[{row['league_id']}] {row['league_name']} — {len(missing)} missing")
        for team in missing:
            print(f"  - {team['team_name']} (id={team['team_id']}, key={team['soft_key']!r})")

    if not any_missing:
        print("All teams resolve a static crest URL.")

    print()
    print(
        "Note: This audit uses STATIC_TEAM_LOGOS + search aliases only (no live API). "
        "Standings/API crests may still load in the app for some missing rows."
    )
    if STANDINGS_TEAM_OVERRIDES:
        print(f"Standings overrides loaded: {len(STANDINGS_TEAM_OVERRIDES)} entries.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit team logos and duplicate team names across all 10 leagues."
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database")
    parser.add_argument(
        "--league-id",
        type=int,
        action="append",
        dest="league_ids",
        help="Limit to one league id (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else default_db_path()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    league_ids = args.league_ids or list(ALL_LEAGUES.keys())
    conn = sqlite3.connect(str(db_path))
    try:
        reports = []
        for league_id in league_ids:
            name = ALL_LEAGUES.get(int(league_id), f"League {league_id}")
            reports.append(audit_league(conn, int(league_id), name))
    finally:
        conn.close()

    if args.json:
        print(json.dumps({"leagues": reports}, indent=2))
    else:
        print_report(reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
