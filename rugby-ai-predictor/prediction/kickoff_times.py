"""Resolve kickoff timestamps from Highlightly / SQLite for upcoming fixtures."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from prediction.standings_compute import resolve_standings_db_path


def has_meaningful_kickoff_time(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, str):
        m = re.search(r"[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?", value.strip())
        if not m:
            m = re.search(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", value.strip())
        if not m:
            return False
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        return not (hh == 0 and mm == 0 and ss == 0)
    if isinstance(value, datetime):
        return not (
            value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0
        )
    return False


def normalize_kickoff_iso(value: Any) -> Optional[str]:
    """Normalize to UTC ISO string (Highlightly dates are UTC with Z)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    raw = str(value).strip()
    if not raw:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return None
    try:
        text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def pick_kickoff_from_match(match: Dict[str, Any]) -> Optional[str]:
    """Return normalized kickoff ISO from match dict fields, if meaningful."""
    for key in ("kickoff_at", "kickoffAt", "timestamp", "date_event", "dateEvent"):
        val = match.get(key)
        if not has_meaningful_kickoff_time(val):
            continue
        iso = normalize_kickoff_iso(val)
        if iso:
            return iso
    return None


def _norm_team(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def _date_key(value: Any) -> str:
    raw = str(value or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else ""


def _load_sqlite_kickoffs(event_ids: List[int], db_path: str) -> Dict[int, str]:
    if not event_ids or not db_path or not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" * len(event_ids))
        rows = conn.execute(
            f"""
            SELECT id, timestamp, date_event
            FROM event
            WHERE id IN ({placeholders})
            """,
            event_ids,
        ).fetchall()
    finally:
        conn.close()

    out: Dict[int, str] = {}
    for event_id, ts, date_event in rows:
        for candidate in (ts, date_event):
            if has_meaningful_kickoff_time(candidate):
                iso = normalize_kickoff_iso(candidate)
                if iso:
                    out[int(event_id)] = iso
                    break
    return out


def _highlightly_league_id(our_league_id: Optional[int]) -> Optional[int]:
    if not our_league_id:
        return None
    try:
        from prediction.highlightly_leagues import HIGHLIGHTLY_LEAGUE_MAPPINGS

        mapping = HIGHLIGHTLY_LEAGUE_MAPPINGS.get(int(our_league_id))
        if mapping:
            return int(mapping[1])
    except Exception:
        return None
    return None


def _fetch_highlightly_kickoffs(
    our_league_id: Optional[int],
    *,
    api_key: Optional[str] = None,
) -> Dict[Tuple[str, str, str], str]:
    """Map (date, home_norm, away_norm) -> kickoff ISO from Highlightly."""
    hl_id = _highlightly_league_id(our_league_id)
    key = (api_key or os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip()
    if not hl_id or not key:
        return {}

    try:
        from prediction.highlightly_client import HighlightlyRugbyAPI
    except Exception:
        return {}

    api = HighlightlyRugbyAPI(api_key=key, use_rapidapi=bool(os.getenv("RAPIDAPI_KEY")))
    year = datetime.now(timezone.utc).year
    out: Dict[Tuple[str, str, str], str] = {}
    for season in (year, year - 1):
        offset = 0
        while offset < 250:
            resp = api.get_matches(league_id=hl_id, season=season, limit=50, offset=offset)
            rows = resp.get("data") or []
            if not rows:
                break
            for row in rows:
                raw = row.get("date") or ""
                if not has_meaningful_kickoff_time(raw):
                    continue
                iso = normalize_kickoff_iso(raw)
                if not iso:
                    continue
                day = _date_key(raw)
                home = _norm_team((row.get("homeTeam") or {}).get("name"))
                away = _norm_team((row.get("awayTeam") or {}).get("name"))
                if day and home and away:
                    out[(day, home, away)] = iso
            offset += len(rows)
            if len(rows) < 50:
                break
    return out


def enrich_matches_kickoff(
    matches: List[Dict[str, Any]],
    *,
    db_path: Optional[str] = None,
    league_id: Optional[int] = None,
    api_key: Optional[str] = None,
    allow_highlightly: bool = True,
) -> List[Dict[str, Any]]:
    """Attach kickoff_at + timestamp (UTC ISO) on each match for SAST UI rendering."""
    if not matches:
        return matches

    db_path = db_path or resolve_standings_db_path()
    missing_ids: List[int] = []
    for match in matches:
        if pick_kickoff_from_match(match):
            continue
        try:
            event_id = int(match.get("id") or match.get("event_id") or 0)
        except (TypeError, ValueError):
            event_id = 0
        if event_id:
            missing_ids.append(event_id)

    sqlite_kickoffs = _load_sqlite_kickoffs(missing_ids, db_path)

    for match in matches:
        kickoff = pick_kickoff_from_match(match)
        if not kickoff:
            try:
                event_id = int(match.get("id") or match.get("event_id") or 0)
            except (TypeError, ValueError):
                event_id = 0
            kickoff = sqlite_kickoffs.get(event_id)
        if kickoff:
            match["kickoff_at"] = kickoff
            match["timestamp"] = kickoff

    still_missing = [m for m in matches if not pick_kickoff_from_match(m)]
    if still_missing and allow_highlightly:
        resolved_league = league_id
        if not resolved_league:
            try:
                resolved_league = int(still_missing[0].get("league_id") or 0) or None
            except (TypeError, ValueError):
                resolved_league = None
        hl_map = _fetch_highlightly_kickoffs(resolved_league, api_key=api_key)
        if hl_map:
            for match in still_missing:
                day = _date_key(
                    match.get("date_event")
                    or match.get("dateEvent")
                    or match.get("kickoff_at")
                    or match.get("timestamp")
                )
                home = _norm_team(match.get("home_team") or match.get("home_team_name"))
                away = _norm_team(match.get("away_team") or match.get("away_team_name"))
                kickoff = hl_map.get((day, home, away))
                if kickoff:
                    match["kickoff_at"] = kickoff
                    match["timestamp"] = kickoff
    return matches
