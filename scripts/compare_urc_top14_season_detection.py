#!/usr/bin/env python3
"""Compare URC vs Top 14 season-gap behavior for detector debugging.

Purpose:
- Explain why automatic season detection splits URC but may merge Top 14.
- Use the same core gap rule as `detect_league_season_windows.py`.
- Print side-by-side diagnostics for both leagues.

Default leagues:
- URC: 4446
- Top 14: 4430
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_CANDIDATES = [
    ROOT / "data.sqlite",
    ROOT / "rugby-ai-predictor" / "data.sqlite",
]

DEFAULT_GAP_DAYS = 90
URC_ID = 4446
TOP14_ID = 4430


@dataclass
class MatchRow:
    event_id: int
    league_id: int
    dt_utc: datetime
    date_event: Optional[str]
    timestamp: Optional[str]
    dt_source: str


@dataclass
class GapRow:
    prev: MatchRow
    curr: MatchRow
    day_gap: int


def resolve_db_path(explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Database not found: {p}")
        return p
    for p in DEFAULT_DB_CANDIDATES:
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

    out: List[MatchRow] = []
    for event_id, lid, date_event, ts in conn.execute(sql, params).fetchall():
        dt_ts = parse_datetime_utc(ts)
        if dt_ts:
            out.append(
                MatchRow(
                    event_id=int(event_id),
                    league_id=int(lid),
                    dt_utc=dt_ts,
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
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
                    dt_utc=dt_date,
                    date_event=str(date_event) if date_event else None,
                    timestamp=str(ts) if ts else None,
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
        day_gap = (row.dt_utc.date() - prev.dt_utc.date()).days
        if day_gap >= gap_days:
            seasons.append([row])
        else:
            seasons[-1].append(row)
    return seasons


def compute_gaps(matches: List[MatchRow]) -> List[GapRow]:
    out: List[GapRow] = []
    for i in range(1, len(matches)):
        prev = matches[i - 1]
        curr = matches[i]
        out.append(GapRow(prev=prev, curr=curr, day_gap=(curr.dt_utc.date() - prev.dt_utc.date()).days))
    return out


def fmt_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def summarize_league(
    league_name: str,
    matches: List[MatchRow],
    gap_days: int,
    recent_start_year: int,
    top_n_gaps: int,
) -> Dict[str, Any]:
    seasons = split_seasons(matches, gap_days=gap_days)
    gaps = compute_gaps(matches)
    over_threshold = [g for g in gaps if g.day_gap >= gap_days]

    recent_matches = [m for m in matches if m.dt_utc.year >= recent_start_year]
    recent_gaps = compute_gaps(recent_matches)
    recent_over_threshold = [g for g in recent_gaps if g.day_gap >= gap_days]

    largest_gaps = sorted(gaps, key=lambda g: g.day_gap, reverse=True)[:top_n_gaps]
    largest_recent_gaps = sorted(recent_gaps, key=lambda g: g.day_gap, reverse=True)[:top_n_gaps]

    return {
        "league_name": league_name,
        "match_count": len(matches),
        "season_count": len(seasons),
        "first_match": fmt_date(matches[0].dt_utc) if matches else None,
        "last_match": fmt_date(matches[-1].dt_utc) if matches else None,
        "threshold_gaps_count": len(over_threshold),
        "recent_match_count": len(recent_matches),
        "recent_threshold_gaps_count": len(recent_over_threshold),
        "largest_gaps": largest_gaps,
        "largest_recent_gaps": largest_recent_gaps,
        "recent_threshold_gaps": recent_over_threshold,
        "seasons": seasons,
    }


def print_gap_list(title: str, gaps: List[GapRow], limit: int) -> None:
    print(title)
    if not gaps:
        print("  - none")
        return
    for g in gaps[:limit]:
        print(
            "  - "
            f"{g.day_gap:>3} days | "
            f"{fmt_date(g.prev.dt_utc)} (event {g.prev.event_id}) -> "
            f"{fmt_date(g.curr.dt_utc)} (event {g.curr.event_id})"
        )


def print_recent_seasons(title: str, seasons: List[List[MatchRow]], limit: int) -> None:
    print(title)
    if not seasons:
        print("  - none")
        return
    for season_rows in seasons[-limit:]:
        start = season_rows[0]
        end = season_rows[-1]
        print(
            "  - "
            f"{fmt_date(start.dt_utc)} -> {fmt_date(end.dt_utc)} | "
            f"{len(season_rows)} matches | "
            f"event {start.event_id} -> {end.event_id}"
        )


def compare(
    db_path: Path,
    gap_days: int,
    scored_only: bool,
    recent_start_year: int,
    top_n_gaps: int,
    recent_seasons_to_show: int,
) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        urc_matches = load_matches(conn, URC_ID, scored_only=scored_only)
        top14_matches = load_matches(conn, TOP14_ID, scored_only=scored_only)

    urc = summarize_league(
        league_name="URC",
        matches=urc_matches,
        gap_days=gap_days,
        recent_start_year=recent_start_year,
        top_n_gaps=top_n_gaps,
    )
    top14 = summarize_league(
        league_name="Top 14",
        matches=top14_matches,
        gap_days=gap_days,
        recent_start_year=recent_start_year,
        top_n_gaps=top_n_gaps,
    )

    print("=== Season Detection Comparison: URC vs Top 14 ===")
    print(f"DB: {db_path}")
    print(f"Gap rule: >= {gap_days} days | scored_only={scored_only} | recent_start_year={recent_start_year}")
    print()

    for summary in (urc, top14):
        print(f"[{summary['league_name']}]")
        print(
            f"- Matches: {summary['match_count']} "
            f"({summary['first_match']} -> {summary['last_match']})"
        )
        print(f"- Seasons detected (all-time): {summary['season_count']}")
        print(f"- Gaps >= {gap_days}d (all-time): {summary['threshold_gaps_count']}")
        print(
            f"- Recent matches (>= {recent_start_year}): {summary['recent_match_count']}; "
            f"recent gaps >= {gap_days}d: {summary['recent_threshold_gaps_count']}"
        )
        print_recent_seasons(
            title=f"- Last {recent_seasons_to_show} detected seasons:",
            seasons=summary["seasons"],
            limit=recent_seasons_to_show,
        )
        print_gap_list(
            title=f"- Largest {top_n_gaps} all-time gaps:",
            gaps=summary["largest_gaps"],
            limit=top_n_gaps,
        )
        print_gap_list(
            title=f"- Largest {top_n_gaps} recent gaps (>= {recent_start_year}):",
            gaps=summary["largest_recent_gaps"],
            limit=top_n_gaps,
        )
        print()

    urc_recent_split = urc["recent_threshold_gaps_count"]
    top14_recent_split = top14["recent_threshold_gaps_count"]
    print("=== Quick Read ===")
    if urc_recent_split > top14_recent_split:
        print(
            f"URC has more recent >= {gap_days} day offseason gaps than Top 14 "
            f"({urc_recent_split} vs {top14_recent_split}), which explains cleaner season splits."
        )
    elif urc_recent_split < top14_recent_split:
        print(
            f"Top 14 has more recent >= {gap_days} day gaps than URC "
            f"({top14_recent_split} vs {urc_recent_split}); investigate other factors."
        )
    else:
        print(
            f"Both leagues show the same count of recent >= {gap_days} day gaps "
            f"({urc_recent_split}); inspect exact gap locations above."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare URC vs Top 14 season-gap behavior.")
    parser.add_argument("--db-path", default="", help="Optional explicit sqlite path.")
    parser.add_argument("--gap-days", type=int, default=DEFAULT_GAP_DAYS, help="Gap days threshold (default: 90).")
    parser.add_argument(
        "--include-unscored",
        action="store_true",
        help="Include unscored matches (default uses completed/scored only).",
    )
    parser.add_argument(
        "--recent-start-year",
        type=int,
        default=2018,
        help="Lower bound year for recent diagnostics (default: 2018).",
    )
    parser.add_argument(
        "--top-n-gaps",
        type=int,
        default=10,
        help="How many largest gaps to print (default: 10).",
    )
    parser.add_argument(
        "--recent-seasons",
        type=int,
        default=5,
        help="How many most recent detected seasons to print (default: 5).",
    )
    args = parser.parse_args()

    if args.gap_days < 1:
        raise ValueError("--gap-days must be >= 1")
    if args.top_n_gaps < 1:
        raise ValueError("--top-n-gaps must be >= 1")
    if args.recent_seasons < 1:
        raise ValueError("--recent-seasons must be >= 1")

    db_path = resolve_db_path(args.db_path or None)
    scored_only = not args.include_unscored
    return compare(
        db_path=db_path,
        gap_days=args.gap_days,
        scored_only=scored_only,
        recent_start_year=args.recent_start_year,
        top_n_gaps=args.top_n_gaps,
        recent_seasons_to_show=args.recent_seasons,
    )


if __name__ == "__main__":
    raise SystemExit(main())

