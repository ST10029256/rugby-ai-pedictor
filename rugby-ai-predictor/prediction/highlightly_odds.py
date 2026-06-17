"""Normalize Highlightly odds payloads for hybrid predictions."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from .highlightly_client import HighlightlyRugbyAPI
from .highlightly_leagues import (
    HIGHLIGHTLY_LEAGUE_MAPPINGS,
    ensure_highlightly_match_id_column,
    lookup_highlightly_match_id,
)

logger = logging.getLogger(__name__)

FT_MARKET_NAMES = (
    "full time result",
    "match winner",
    "home/away",
    "1x2",
    "winner",
)


def _normalize_team(name: str) -> str:
    return " ".join(str(name or "").lower().replace(" rugby", "").split())


def _teams_match(a: str, b: str) -> bool:
    na, nb = _normalize_team(a), _normalize_team(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def normalize_highlightly_odds(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Convert Highlightly /odds response into the schema expected by extract_odds_features().
    """
    if not payload or not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None

    entry = data[0] if isinstance(data[0], dict) else None
    if not entry:
        return None

    odds_list = entry.get("odds")
    if not isinstance(odds_list, list):
        return None

    # Group by bookmaker; pick best full-time market per bookmaker.
    by_bookmaker: Dict[str, Dict[str, Any]] = {}

    for market_row in odds_list:
        if not isinstance(market_row, dict):
            continue
        market_name = str(market_row.get("market") or "").strip().lower()
        if not any(x in market_name for x in FT_MARKET_NAMES):
            continue

        bk_name = str(market_row.get("bookmakerName") or "Unknown")
        values = market_row.get("values")
        if not isinstance(values, list):
            continue

        home = draw = away = None
        for v in values:
            if not isinstance(v, dict):
                continue
            label = str(v.get("value") or "").strip().lower()
            try:
                odd = float(v.get("odd"))
            except (TypeError, ValueError):
                continue
            if odd <= 0:
                continue
            if label in {"home", "1"}:
                home = odd
            elif label in {"draw", "x"}:
                draw = odd
            elif label in {"away", "2"}:
                away = odd

        if home is None and away is None:
            continue

        existing = by_bookmaker.get(bk_name)
        # Prefer markets that include draw (Full Time Result) over Home/Away only.
        if existing is None or (draw is not None and existing.get("draw") is None):
            by_bookmaker[bk_name] = {
                "bookmaker": bk_name,
                "home": home,
                "draw": draw,
                "away": away,
            }

    rows = list(by_bookmaker.values())
    if not rows:
        return None

    return {
        "source": "highlightly",
        "match_id": entry.get("matchId"),
        "periods": [
            {
                "period_type": "Full Time Result",
                "odds": rows,
            }
        ],
    }


def resolve_highlightly_match_id(
    api: HighlightlyRugbyAPI,
    league_id: Optional[int],
    match_date: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
) -> Optional[int]:
    """Find Highlightly matchId from local league id + date + team names."""
    if league_id is None or not home_team or not away_team:
        return None

    hl_id = HIGHLIGHTLY_LEAGUE_MAPPINGS.get(int(league_id), (None, None))[1]
    if not hl_id:
        return None

    target_date = str(match_date or "")[:10]
    if not target_date:
        return None

    try:
        year = int(target_date[:4])
    except ValueError:
        year = None

    params_list: List[Dict[str, Any]] = [{"date": target_date}]
    if year is not None:
        params_list.append({"season": year})

    for params in params_list:
        resp = api.get_matches(league_id=int(hl_id), limit=100, **params)
        for row in resp.get("data") or []:
            if not isinstance(row, dict):
                continue
            h = (row.get("homeTeam") or {}).get("name", "")
            a = (row.get("awayTeam") or {}).get("name", "")
            if _teams_match(h, home_team) and _teams_match(a, away_team):
                mid = row.get("id")
                if mid is not None:
                    return int(mid)

    return None


def lookup_highlightly_match_id_from_db(
    db_path: Optional[str],
    local_event_id: Optional[int],
) -> Optional[int]:
    """Load stored Highlightly match id for a local SQLite event id."""
    if not db_path or local_event_id is None:
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_highlightly_match_id_column(conn)
            return lookup_highlightly_match_id(conn, int(local_event_id))
    except Exception as exc:
        logger.debug("Highlightly match id DB lookup failed: %s", exc)
        return None


def fetch_highlightly_match_odds(
    api: HighlightlyRugbyAPI,
    match_id: Optional[int] = None,
    league_id: Optional[int] = None,
    match_date: Optional[str] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    highlightly_match_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch and normalize odds for a match (stored id, Highlightly id, or team/date lookup)."""
    hl_match_id = highlightly_match_id

    # Prefer stored mapping from SQLite (local event ids can be large too).
    if hl_match_id is None and db_path and match_id is not None:
        hl_match_id = lookup_highlightly_match_id_from_db(db_path, int(match_id))

    # Raw Highlightly ids are typically 8+ digits (e.g. 45411846).
    if hl_match_id is None and match_id is not None and int(match_id) >= 10_000_000:
        hl_match_id = int(match_id)

    if hl_match_id is None:
        hl_match_id = resolve_highlightly_match_id(
            api, league_id, match_date, home_team, away_team
        )

    if hl_match_id is None:
        return None

    payload = api.get_odds(match_id=int(hl_match_id), limit=5)
    return normalize_highlightly_odds(payload)
