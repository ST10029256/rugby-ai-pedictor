#!/usr/bin/env python3
"""Diagnose English Premiership 2018-2019 season data and week detection.

Checks:
- What match data exists between Aug 2018 and 2019-06-01.
- Where long gaps occur (to explain season splitting behavior).
- Whether UI-style observed week detection reaches 22 weeks.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
LEAGUE_ID = 4414  # English Premiership Rugby
DEFAULT_START = "2018-08-01"
DEFAULT_END = "2019-06-01"
DEFAULT_GAP_DAYS = 90


@dataclass
class MatchRow:
    event_id: int
    date_event: Optional[str]
    timestamp: Optional[str]
    dt_utc: datetime


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

    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.fromisoformat(f"{s}T00:00:00+00:00").astimezone(timezone.utc)
        except ValueError:
            return None

    normalized = s.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    has_tz = (
        normalized.endswith("+00:00")
        or normalized.endswith("-00:00")
        or ("+" in normalized[10:] or "-" in normalized[10:])
    )
    if "T" in normalized and not has_tz:
        normalized += "+00:00"

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

    out: List[MatchRow] = []
    for event_id, date_event, ts in conn.execute(sql, params).fetchall():
        dt_ts = parse_datetime_utc(ts)
        if dt_ts:
            out.append(
                MatchRow(
                    event_id=int(event_id),
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
                    dt_utc=dt_ts,
                )
            )
            continue
        dt_date = parse_datetime_utc(date_event)
        if dt_date:
            out.append(
                MatchRow(
                    event_id=int(event_id),
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
                    dt_utc=dt_date,
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
        day_gap = (row.dt_utc.date() - prev.dt_utc.date()).days
        if day_gap >= gap_days:
            seasons.append([row])
        else:
            seasons[-1].append(row)
    return seasons


def analyze_ui_weeks(matches: List[MatchRow]) -> Dict[str, Any]:
    if not matches:
        return {"anchor_date": None, "raw_week_count": 0, "display_week_count": 0, "weeks": []}
    sorted_rows = sorted(matches, key=lambda r: (r.dt_utc, r.event_id))
    anchor = sorted_rows[0].dt_utc.date()
    by_raw_week: Dict[int, int] = {}
    for row in sorted_rows:
        day_diff = (row.dt_utc.date() - anchor).days
        raw_week = (day_diff // 7) + 1
        by_raw_week[raw_week] = by_raw_week.get(raw_week, 0) + 1
    ordered_raw = sorted(by_raw_week.keys())
    weeks = [{"raw_week": rw, "match_count": by_raw_week[rw], "display_week": idx + 1} for idx, rw in enumerate(ordered_raw)]
    return {
        "anchor_date": str(anchor),
        "raw_week_count": len(ordered_raw),
        "display_week_count": len(ordered_raw),
        "weeks": weeks,
    }


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def print_month_summary(matches: List[MatchRow]) -> None:
    counts: Dict[str, int] = {}
    for m in matches:
        key = month_key(m.dt_utc)
        counts[key] = counts.get(key, 0) + 1
    print("Matches by month:")
    if not counts:
        print("  - none")
        return
    for key in sorted(counts.keys()):
        print(f"  - {key}: {counts[key]}")


def print_largest_gaps(matches: List[MatchRow], limit: int = 10) -> None:
    gaps = []
    for i in range(1, len(matches)):
        prev = matches[i - 1]
        curr = matches[i]
        day_gap = (curr.dt_utc.date() - prev.dt_utc.date()).days
        gaps.append((day_gap, prev, curr))
    gaps.sort(key=lambda x: x[0], reverse=True)
    print(f"Largest {limit} consecutive gaps:")
    if not gaps:
        print("  - none")
        return
    for day_gap, prev, curr in gaps[:limit]:
        print(
            "  - "
            f"{day_gap:>3} days | "
            f"{prev.dt_utc.date()} (event {prev.event_id}) -> "
            f"{curr.dt_utc.date()} (event {curr.event_id})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze English Premiership 2018-2019 season behavior.")
    parser.add_argument("--db-path", default="", help="Optional explicit sqlite path.")
    parser.add_argument("--start-date", default=DEFAULT_START, help="Window start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", default=DEFAULT_END, help="Window end date (YYYY-MM-DD).")
    parser.add_argument("--gap-days", type=int, default=DEFAULT_GAP_DAYS, help="Gap days used for season split (default: 90).")
    parser.add_argument(
        "--include-unscored",
        action="store_true",
        help="Include matches without scores (default uses completed/scored only).",
    )
    parser.add_argument("--expected-weeks", type=int, default=22, help="Expected observed week count to check (default: 22).")
    args = parser.parse_args()

    if args.gap_days < 1:
        raise ValueError("--gap-days must be >= 1")

    start_date = datetime.fromisoformat(args.start_date).date()
    end_date = datetime.fromisoformat(args.end_date).date()
    if end_date < start_date:
        raise ValueError("--end-date must be on/after --start-date")

    db_path = resolve_db_path(args.db_path or None)
    scored_only = not args.include_unscored

    with sqlite3.connect(str(db_path)) as conn:
        all_matches = load_matches(conn, league_id=LEAGUE_ID, scored_only=scored_only)

    window_matches = [m for m in all_matches if start_date <= m.dt_utc.date() <= end_date]
    seasons = split_seasons(all_matches, gap_days=args.gap_days)
    overlapping_seasons = [
        s
        for s in seasons
        if not (s[-1].dt_utc.date() < start_date or s[0].dt_utc.date() > end_date)
    ]
    weeks = analyze_ui_weeks(window_matches)

    print("=== English Premiership 2018-2019 Diagnostic ===")
    print(f"League: {LEAGUE_ID} (English Premiership Rugby)")
    print(f"DB: {db_path}")
    print(f"Scored only: {scored_only}")
    print(f"Window: {start_date} -> {end_date}")
    print(f"Season split gap: >= {args.gap_days} days")
    print()

    print(f"All-time matches loaded: {len(all_matches)}")
    if all_matches:
        print(f"All-time range: {all_matches[0].dt_utc.date()} -> {all_matches[-1].dt_utc.date()}")
    print(f"Window matches: {len(window_matches)}")
    if window_matches:
        print(f"Window range: {window_matches[0].dt_utc.date()} -> {window_matches[-1].dt_utc.date()}")
    else:
        print("Window range: none")
    print()

    print_month_summary(window_matches)
    print()
    print_largest_gaps(window_matches, limit=10)
    print()

    print(f"Detected seasons overlapping window ({len(overlapping_seasons)}):")
    if not overlapping_seasons:
        print("  - none")
    else:
        for idx, season in enumerate(overlapping_seasons, start=1):
            print(
                "  - "
                f"{idx}. {season[0].dt_utc.date()} -> {season[-1].dt_utc.date()} | "
                f"{len(season)} matches | events {season[0].event_id} -> {season[-1].event_id}"
            )
    print()

    print("UI-style observed week detection in the requested window:")
    print(f"- Anchor date: {weeks['anchor_date']}")
    print(f"- Raw/observed week buckets: {weeks['raw_week_count']}")
    print(f"- Display week count after reindex: {weeks['display_week_count']}")
    print(f"- Expected week count: {args.expected_weeks}")
    if weeks["display_week_count"] == args.expected_weeks:
        print(f"- Result: PASS (detected {args.expected_weeks} weeks)")
    else:
        print(f"- Result: FAIL (detected {weeks['display_week_count']} weeks, expected {args.expected_weeks})")

    print()
    print("Observed week buckets:")
    if not weeks["weeks"]:
        print("  - none")
    else:
        for wk in weeks["weeks"]:
            print(
                "  - "
                f"raw {wk['raw_week']:>2} -> display {wk['display_week']:>2} | "
                f"{wk['match_count']} matches"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

