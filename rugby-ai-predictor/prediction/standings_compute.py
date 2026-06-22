"""Compute league standings from match results in the local SQLite database.

The Highlightly /standings feed is unreliable for rugby (stale, mislabeled by
season, missing recent seasons, and sometimes returned in an outdated grouped
format). The match/results feed, however, is accurate - so we derive the table
ourselves from completed matches.

Scoring uses the standard rugby union system that can be derived from final
scores only:

    Win  = 4 points
    Draw = 2 points
    Loss = 0 points
    Losing bonus = +1 when losing by 7 or fewer points

The try-scoring bonus (+1 for 4+ tries) cannot be computed because try counts
are not stored, so totals may be slightly lower than official tables. This is
called out via the ``note`` field on the response.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

# Competitions that are knockout tournaments or have multiple pools / no league
# table - a single computed table would be meaningless, so we skip them.
SKIP_COMPUTE_LEAGUE_IDS = {
    4574,  # Rugby World Cup (pools + knockout)
    5479,  # International Friendlies (no table)
    5480,  # Nations Championship (no standings)
}


def resolve_standings_db_path() -> str:
    """Resolve the SQLite path the way the history endpoint does."""
    env_path = os.getenv("DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # rugby-ai-predictor/
    candidate = os.path.join(pkg_parent, "data.sqlite")
    if os.path.exists(candidate):
        return candidate
    return os.path.join(pkg_parent, "..", "data.sqlite")


def _parse_date(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except Exception:
        return None


def _season_start_year(season_str: Any) -> Optional[int]:
    match = re.match(r"(\d{4})", str(season_str or ""))
    return int(match.group(1)) if match else None


def _pick_latest_season(conn: sqlite3.Connection, league_id: int) -> Optional[str]:
    rows = conn.execute(
        """
        SELECT season, MAX(date_event) AS mx
        FROM event
        WHERE league_id = ?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND season IS NOT NULL AND season != ''
        GROUP BY season
        """,
        (league_id,),
    ).fetchall()
    if not rows:
        return None
    rows = [r for r in rows if r[1]]
    if not rows:
        return None
    rows.sort(key=lambda r: str(r[1]), reverse=True)
    return rows[0][0]


def _resolve_season(conn: sqlite3.Connection, league_id: int, season: Any) -> Optional[str]:
    if season is None or str(season).strip() == "":
        return _pick_latest_season(conn, league_id)

    available = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT season FROM event WHERE league_id = ? AND season IS NOT NULL AND season != ''",
            (league_id,),
        ).fetchall()
    ]
    target = str(season).strip()
    if target in available:
        return target
    target_year = _season_start_year(target)
    if target_year is not None:
        for a in available:
            if _season_start_year(a) == target_year:
                return a
    return _pick_latest_season(conn, league_id)


def _exclude_trailing_playoffs(matches: List[tuple], gap_days: int = 4) -> List[tuple]:
    """Drop trailing knockout matchdays so the result is the league (regular
    season) table. Matches must be ordered by date ascending.

    A "matchday" is a cluster of matches within ``gap_days`` of each other.
    Knockout rounds at the end of a season are much smaller than a normal
    matchday (e.g. final=1, semis=2 vs a full round of 7-8), so trailing
    matchdays at most half the typical size are removed. Round-robin
    competitions (small, even matchdays throughout) are left untouched.
    """
    groups: List[List[tuple]] = []
    current: List[tuple] = []
    last: Optional[datetime] = None
    for m in matches:
        d = _parse_date(m[0])
        if d is None:
            current.append(m)
            continue
        if last is None or (d - last).days <= gap_days:
            current.append(m)
        else:
            groups.append(current)
            current = [m]
        last = d
    if current:
        groups.append(current)

    if len(groups) < 3:
        return [m for g in groups for m in g]

    sizes = sorted(len(g) for g in groups)
    median = sizes[len(sizes) // 2]
    if median <= 2:
        # Tiny / round-robin competition - no meaningful playoff structure.
        return [m for g in groups for m in g]

    threshold = median / 2.0
    end = len(groups)
    while end > 0 and len(groups[end - 1]) <= threshold:
        end -= 1
    kept = groups[:end] if end > 0 else groups
    return [m for g in kept for m in g]


def compute_standings_from_db(
    db_path: str,
    our_league_id: int,
    season: Any = None,
    *,
    win_points: int = 4,
    draw_points: int = 2,
    loss_points: int = 0,
    losing_bonus_margin: int = 7,
) -> Optional[Dict[str, Any]]:
    """Return a Highlightly-shaped standings dict computed from results, or None."""
    if int(our_league_id) in SKIP_COMPUTE_LEAGUE_IDS:
        return None
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    try:
        season_str = _resolve_season(conn, our_league_id, season)
        if not season_str:
            return None

        league_row = conn.execute(
            "SELECT name FROM league WHERE id = ?", (our_league_id,)
        ).fetchone()
        league_name = league_row[0] if league_row else None

        matches = conn.execute(
            """
            SELECT e.date_event, e.home_team_id, e.away_team_id,
                   e.home_score, e.away_score, th.name, ta.name
            FROM event e
            JOIN team th ON th.id = e.home_team_id
            JOIN team ta ON ta.id = e.away_team_id
            WHERE e.league_id = ? AND e.season = ?
              AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
            ORDER BY e.date_event ASC, e.id ASC
            """,
            (our_league_id, season_str),
        ).fetchall()
        if not matches:
            return None

        matches = _exclude_trailing_playoffs(matches)
        if not matches:
            return None

        stats: Dict[int, Dict[str, Any]] = {}

        def team(tid: int, name: str) -> Dict[str, Any]:
            if tid not in stats:
                stats[tid] = {
                    "id": tid, "name": name, "pl": 0, "w": 0, "d": 0,
                    "l": 0, "pf": 0, "pa": 0, "pts": 0, "bp": 0,
                }
            return stats[tid]

        for _date, hid, aid, hs, as_, hname, aname in matches:
            try:
                hs_i, as_i = int(hs), int(as_)
            except (TypeError, ValueError):
                continue
            home = team(hid, hname)
            away = team(aid, aname)
            home["pl"] += 1
            away["pl"] += 1
            home["pf"] += hs_i
            home["pa"] += as_i
            away["pf"] += as_i
            away["pa"] += hs_i

            if hs_i > as_i:
                home["w"] += 1
                away["l"] += 1
                home["pts"] += win_points
                away["pts"] += loss_points
                if hs_i - as_i <= losing_bonus_margin:
                    away["pts"] += 1
                    away["bp"] += 1
            elif as_i > hs_i:
                away["w"] += 1
                home["l"] += 1
                away["pts"] += win_points
                home["pts"] += loss_points
                if as_i - hs_i <= losing_bonus_margin:
                    home["pts"] += 1
                    home["bp"] += 1
            else:
                home["d"] += 1
                away["d"] += 1
                home["pts"] += draw_points
                away["pts"] += draw_points

        if not stats:
            return None

        rows = sorted(
            stats.values(),
            key=lambda r: (-r["pts"], -(r["pf"] - r["pa"]), -r["pf"], -r["w"], r["name"]),
        )

        standings_list: List[Dict[str, Any]] = []
        for idx, r in enumerate(rows):
            diff = r["pf"] - r["pa"]
            standings_list.append(
                {
                    "position": idx + 1,
                    "team": {"id": r["id"], "name": r["name"]},
                    "points": r["pts"],
                    "gamesPlayed": r["pl"],
                    "played": r["pl"],
                    "wins": r["w"],
                    "draws": r["d"],
                    "loses": r["l"],
                    "losses": r["l"],
                    "scoredPoints": r["pf"],
                    "pointsFor": r["pf"],
                    "receivedPoints": r["pa"],
                    "pointsAgainst": r["pa"],
                    "pointsDifference": diff,
                    "pointsDiff": diff,
                    "bonusPoints": r["bp"],
                }
            )

        start_year = _season_start_year(season_str)
        return {
            "league": {
                "id": our_league_id,
                "name": league_name,
                "season": start_year if start_year is not None else season_str,
                "season_label": season_str,
            },
            "groups": [{"name": None, "standings": standings_list}],
            "_computed": True,
            "_source": "match_results",
            "note": (
                "Computed from match results (win 4 / draw 2 / losing bonus for "
                "margin \u22647). Excludes try-scoring bonus points, which are not "
                "available in the data source."
            ),
        }
    finally:
        conn.close()
