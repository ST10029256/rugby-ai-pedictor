#!/usr/bin/env python3
"""Detect season start/end windows per league from historical matches.

Purpose:
- Compute actual season windows from match chronology (not fixed Sep-Jun logic).
- Cover all configured leagues by default (9 leagues in LEAGUE_MAPPINGS).
- Export a JSON artifact that can be consumed by UI/widget logic.

Season boundary rule:
- A new season starts when the gap between consecutive matches is >= gap-days.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prediction.config import LEAGUE_MAPPINGS  # noqa: E402


DEFAULT_GAP_DAYS = 90
DEFAULT_OUTPUT = ROOT / "artifacts" / "league_season_windows.json"
# League-specific overrides for offseason gap split behavior.
# Top 14 has shorter summer breaks than other leagues.
DEFAULT_LEAGUE_GAP_OVERRIDES: Dict[int, int] = {
    4430: 60,  # French Top 14
    4414: 70,  # English Premiership Rugby
}


@dataclass
class MatchRow:
    event_id: int
    league_id: int
    date_event: Optional[str]
    timestamp: Optional[str]
    dt_utc: datetime
    dt_source: str


def resolve_db_path(explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Database not found: {p}")
        return p

    candidates = [
        ROOT / "data.sqlite",
        ROOT / "rugby-ai-predictor" / "data.sqlite",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError("Could not find data.sqlite in expected locations.")


def parse_datetime_utc(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Date-only fallback.
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            dt = datetime.fromisoformat(f"{s}T00:00:00+00:00")
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    normalized = s.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    # If datetime has no explicit timezone, treat as UTC.
    has_tz = (
        normalized.endswith("+00:00")
        or normalized.endswith("-00:00")
        or ("+" in normalized[10:] or "-" in normalized[10:])
    )
    if "T" in normalized and not has_tz:
        normalized = normalized + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_matches(conn: sqlite3.Connection, league_id: int, scored_only: bool) -> List[MatchRow]:
    sql = """
        SELECT
            e.id,
            e.league_id,
            e.date_event,
            e.timestamp
        FROM event e
        WHERE e.league_id = ?
          AND e.date_event IS NOT NULL
    """
    params: List[Any] = [league_id]
    if scored_only:
        sql += " AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL"
    sql += " ORDER BY e.date_event ASC, e.id ASC"

    cur = conn.execute(sql, params)
    out: List[MatchRow] = []
    for event_id, lid, date_event, ts in cur.fetchall():
        dt_ts = parse_datetime_utc(ts)
        if dt_ts:
            out.append(
                MatchRow(
                    event_id=int(event_id),
                    league_id=int(lid),
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
                    dt_utc=dt_ts,
                    dt_source="timestamp",
                )
            )
            continue

        dt_date = parse_datetime_utc(date_event)
        if dt_date:
            out.append(
                MatchRow(
                    event_id=int(event_id),
                    league_id=int(lid),
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
                    dt_utc=dt_date,
                    dt_source="date_event",
                )
            )
    out.sort(key=lambda r: (r.dt_utc, r.event_id))
    return out


def split_seasons(matches: List[MatchRow], gap_days: int) -> List[List[MatchRow]]:
    if not matches:
        return []
    seasons: List[List[MatchRow]] = [[matches[0]]]
    for row in matches[1:]:
        prev = seasons[-1][-1]
        # Use calendar-day gap (not time-of-day) to avoid borderline 89.9-day merges.
        day_gap = (row.dt_utc.date() - prev.dt_utc.date()).days
        if day_gap >= gap_days:
            seasons.append([row])
        else:
            seasons[-1].append(row)
    return seasons


def to_iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_payload(
    league_id: int,
    league_name: str,
    matches: List[MatchRow],
    seasons: List[List[MatchRow]],
    gap_days: int,
) -> Dict[str, Any]:
    season_entries: List[Dict[str, Any]] = []
    for idx, season_rows in enumerate(seasons, start=1):
        first = season_rows[0]
        last = season_rows[-1]
        start_iso = to_iso_utc(first.dt_utc)
        end_iso = to_iso_utc(last.dt_utc)
        duration_days = int((last.dt_utc - first.dt_utc).total_seconds() // 86400)

        gap_from_prev_days: Optional[float] = None
        if idx > 1:
            prev_end = seasons[idx - 2][-1].dt_utc
            gap_from_prev_days = round((first.dt_utc - prev_end).total_seconds() / 86400.0, 2)

        season_entries.append(
            {
                "season_index": idx,
                "start_utc": start_iso,
                "end_utc": end_iso,
                "start_date": start_iso[:10],
                "end_date": end_iso[:10],
                "match_count": len(season_rows),
                "duration_days": duration_days,
                "gap_from_prev_days": gap_from_prev_days,
                "first_event_id": first.event_id,
                "last_event_id": last.event_id,
            }
        )

    return {
        "league_id": league_id,
        "league_name": league_name,
        "gap_days_rule": gap_days,
        "total_matches_considered": len(matches),
        "season_count": len(seasons),
        "seasons": season_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect real season start/end windows per league.")
    parser.add_argument("--db-path", default="", help="Optional explicit sqlite path.")
    parser.add_argument("--gap-days", type=int, default=DEFAULT_GAP_DAYS, help="Gap days that split seasons (default: 90).")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path.")
    parser.add_argument(
        "--include-unscored",
        action="store_true",
        help="Include matches without scores (default uses completed/scored matches only).",
    )
    args = parser.parse_args()

    if args.gap_days < 1:
        raise ValueError("--gap-days must be >= 1")
    for lid, override_gap in DEFAULT_LEAGUE_GAP_OVERRIDES.items():
        if override_gap < 1:
            raise ValueError(f"Invalid league gap override for league {lid}: {override_gap}")

    db_path = resolve_db_path(args.db_path or None)
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored_only = not args.include_unscored

    with sqlite3.connect(str(db_path)) as conn:
        all_results: List[Dict[str, Any]] = []
        for league_id, league_name in LEAGUE_MAPPINGS.items():
            effective_gap_days = DEFAULT_LEAGUE_GAP_OVERRIDES.get(int(league_id), args.gap_days)
            matches = load_matches(conn, league_id=league_id, scored_only=scored_only)
            seasons = split_seasons(matches, gap_days=effective_gap_days)
            all_results.append(
                build_payload(
                    league_id=league_id,
                    league_name=league_name,
                    matches=matches,
                    seasons=seasons,
                    gap_days=effective_gap_days,
                )
            )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path),
        "gap_days_rule": args.gap_days,
        "league_gap_overrides": {str(k): v for k, v in sorted(DEFAULT_LEAGUE_GAP_OVERRIDES.items())},
        "scored_only": scored_only,
        "league_count": len(all_results),
        "leagues": all_results,
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote season windows for {len(all_results)} leagues -> {output_path}")
    for league in all_results:
        if league["season_count"] == 0:
            print(f"- {league['league_id']} {league['league_name']}: no seasons found")
            continue
        first = league["seasons"][0]
        last = league["seasons"][-1]
        print(
            f"- {league['league_id']} {league['league_name']}: "
            f"{league['season_count']} seasons, "
            f"first {first['start_date']}->{first['end_date']}, "
            f"latest {last['start_date']}->{last['end_date']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

