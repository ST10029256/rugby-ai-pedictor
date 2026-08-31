"""Firestore cache for SportRadar lineup match lists."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

CACHE_VERSION = 1
DEFAULT_TTL_S = 6 * 3600
STALE_MAX_S = 7 * 86400


def lineups_cache_doc_id(local_league_id: int, match_scope: str, season: Optional[int] = None) -> str:
    yr = int(season) if season is not None else 0
    scope = str(match_scope or "historic").strip().lower()
    return f"ldb::{int(local_league_id)}::scope::{scope}::season::{yr}"


def load_lineups_match_cache(
    cache_collection: Any,
    *,
    local_league_id: int,
    match_scope: str,
    season: Optional[int] = None,
    allow_stale: bool = True,
) -> Optional[Tuple[List[Dict[str, Any]], int, bool]]:
    """Return (matches, season, fresh) or None."""
    if cache_collection is None:
        return None

    doc_id = lineups_cache_doc_id(local_league_id, match_scope, season)
    try:
        snap = cache_collection.document(doc_id).get()
        data = snap.to_dict() if getattr(snap, "exists", False) else None
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    if int(data.get("cache_version") or 0) != CACHE_VERSION:
        return None

    matches = data.get("matches")
    if not isinstance(matches, list) or not matches:
        return None

    fetched_at = data.get("fetched_at")
    is_fresh = False
    if isinstance(fetched_at, str):
        try:
            fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_s = (datetime.utcnow() - fetched_dt.replace(tzinfo=None)).total_seconds()
            is_fresh = age_s <= DEFAULT_TTL_S
            if not is_fresh and (not allow_stale or age_s > STALE_MAX_S):
                return None
        except Exception:
            if not allow_stale:
                return None

    cached_season = data.get("season")
    try:
        cached_season_int = int(cached_season) if cached_season is not None else 0
    except (TypeError, ValueError):
        cached_season_int = 0

    return matches, cached_season_int, is_fresh


def write_lineups_match_cache(
    cache_collection: Any,
    *,
    local_league_id: int,
    match_scope: str,
    season: Optional[int],
    matches: List[Dict[str, Any]],
    competition_id: Optional[str] = None,
) -> None:
    if cache_collection is None or not matches:
        return

    doc_id = lineups_cache_doc_id(local_league_id, match_scope, season)
    now = datetime.utcnow().replace(microsecond=0)
    payload = {
        "sportsdb_league_id": int(local_league_id),
        "match_scope": str(match_scope or "historic").strip().lower(),
        "season": int(season) if season is not None else None,
        "competition_id": competition_id,
        "matches": matches,
        "fetched_at": now.isoformat() + "Z",
        "expires_at": (now + timedelta(seconds=DEFAULT_TTL_S)).isoformat() + "Z",
        "cache_version": CACHE_VERSION,
    }
    try:
        cache_collection.document(doc_id).set(payload, merge=True)
    except Exception:
        pass
