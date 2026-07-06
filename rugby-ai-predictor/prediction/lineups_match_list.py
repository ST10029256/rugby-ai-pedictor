"""List SportRadar fixtures that can expose lineups for a local league."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from prediction.sportradar_client import (
    SportRadarRugbyClient,
    candidate_season_years,
    competition_for_local_id,
)

logger = logging.getLogger(__name__)

COMPLETED_STATUSES: Set[str] = {
    "closed",
    "ended",
    "complete",
    "completed",
    "finished",
}


def _event_lineups_coverage(sport_event: Dict[str, Any]) -> Optional[bool]:
    """True/False if SR advertises lineups coverage; None if unknown."""
    coverage = sport_event.get("coverage")
    if not isinstance(coverage, dict):
        return None
    props = coverage.get("properties")
    if not isinstance(props, list):
        return None
    for prop in props:
        if isinstance(prop, dict) and str(prop.get("type") or "").lower() == "lineups":
            return bool(prop.get("value"))
    return None


def _format_match_label(
    *,
    home: Optional[str],
    away: Optional[str],
    start_time: Optional[str],
    round_name: Optional[str],
) -> str:
    home = (home or "Home").strip()
    away = (away or "Away").strip()
    base = f"{home} vs {away}"
    date_part = ""
    if start_time:
        try:
            dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
            date_part = dt.strftime("%d %b %Y")
        except ValueError:
            date_part = str(start_time)[:10]
    bits = [p for p in (date_part, base, round_name) if p]
    return " · ".join(bits)


def summary_item_to_match(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    sport_event = item.get("sport_event")
    if not isinstance(sport_event, dict):
        return None
    event_id = sport_event.get("id")
    if not event_id:
        return None

    status = item.get("sport_event_status") if isinstance(item.get("sport_event_status"), dict) else {}
    st = str(status.get("status") or status.get("match_status") or "").lower()

    competitors = sport_event.get("competitors")
    home_name = away_name = None
    if isinstance(competitors, list):
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            q = str(comp.get("qualifier") or "").lower()
            name = comp.get("name")
            if q == "home":
                home_name = name
            elif q == "away":
                away_name = name
        if home_name is None and len(competitors) >= 1:
            home_name = competitors[0].get("name")
        if away_name is None and len(competitors) >= 2:
            away_name = competitors[1].get("name")

    ctx = sport_event.get("sport_event_context") if isinstance(sport_event.get("sport_event_context"), dict) else {}
    round_info = ctx.get("round") if isinstance(ctx.get("round"), dict) else {}
    stage = ctx.get("stage") if isinstance(ctx.get("stage"), dict) else {}
    round_name = round_info.get("name") or stage.get("phase") or stage.get("type")
    season = ctx.get("season") if isinstance(ctx.get("season"), dict) else {}
    venue = sport_event.get("venue") if isinstance(sport_event.get("venue"), dict) else {}

    start_time = sport_event.get("start_time")
    lineups_coverage = _event_lineups_coverage(sport_event)

    return {
        "sport_event_id": str(event_id),
        "label": _format_match_label(
            home=home_name,
            away=away_name,
            start_time=start_time,
            round_name=str(round_name).strip() if round_name else None,
        ),
        "home_team": home_name,
        "away_team": away_name,
        "start_time": start_time,
        "round": round_name,
        "season": season.get("name") or season.get("year"),
        "venue": venue.get("name"),
        "status": st or None,
        "home_score": status.get("home_score"),
        "away_score": status.get("away_score"),
        "lineups_coverage": lineups_coverage,
    }


def list_league_lineup_matches(
    client: SportRadarRugbyClient,
    *,
    local_league_id: int,
    requested_season: Any = None,
    include_upcoming: bool = False,
    match_scope: str = "historic",
    max_matches: int = 80,
    max_pages: int = 3,
    page_size: int = 200,
) -> Dict[str, Any]:
    """
    Paginate SportRadar season summaries for lineup-capable fixtures.

    match_scope:
      - historic: completed fixtures only (default)
      - upcoming: not-started / scheduled fixtures only
    Returns { matches, season_years_tried, successful_season }.
    """
    scope = str(match_scope or ("upcoming" if include_upcoming else "historic")).strip().lower()
    if scope not in {"historic", "upcoming"}:
        scope = "historic"
    upcoming_only = scope == "upcoming"
    lid = int(local_league_id)
    competition_id = competition_for_local_id(lid)
    if not competition_id:
        return {
            "matches": [],
            "error": "Lineups are not mapped for this league yet.",
            "season_years_tried": [],
            "successful_season": None,
        }

    if not client.configured:
        return {
            "matches": [],
            "error": "SPORTRADAR_API_KEY not configured",
            "season_years_tried": [],
            "successful_season": None,
        }

    years = candidate_season_years(lid, requested_season=requested_season)
    # Keep the scan small — fallbacks resolve the active season without seasons.json.
    expanded: List[int] = []
    for y in years[:4]:
        if y not in expanded:
            expanded.append(y)
        if requested_season is not None:
            for offset in (1, 2):
                prev = y - offset
                if prev not in expanded:
                    expanded.append(prev)
    years = expanded

    seen_ids: Set[str] = set()
    seen_season_ids: Set[str] = set()
    matches: List[Dict[str, Any]] = []
    successful_season: Optional[int] = None
    tried: List[int] = []

    for year in years:
        if len(matches) >= max_matches:
            break
        tried.append(year)
        season_ids = client.resolve_season_ids_for_year(
            competition_id, year, local_league_id=lid
        )
        if not season_ids:
            continue

        season_added = 0
        for season_id in season_ids:
            if season_id in seen_season_ids:
                continue
            seen_season_ids.add(season_id)

            start = 0
            pages = 0
            while pages < max_pages and len(matches) < max_matches:
                raw = client.fetch_season_summaries_raw(season_id, start=start, limit=page_size)
                pages += 1
                if not raw:
                    break
                summaries = raw.get("summaries")
                if not isinstance(summaries, list) or not summaries:
                    break

                for item in summaries:
                    if not isinstance(item, dict):
                        continue
                    status = item.get("sport_event_status") if isinstance(item.get("sport_event_status"), dict) else {}
                    st = str(status.get("status") or status.get("match_status") or "").lower()
                    if st in COMPLETED_STATUSES:
                        if upcoming_only:
                            continue
                    elif st in ("not_started", "scheduled", "delayed"):
                        if not upcoming_only:
                            continue
                    else:
                        continue

                    sport_event = item.get("sport_event") if isinstance(item.get("sport_event"), dict) else {}
                    coverage = _event_lineups_coverage(sport_event)
                    if coverage is False:
                        continue

                    row = summary_item_to_match(item)
                    if not row:
                        continue
                    eid = row["sport_event_id"]
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    row["season_year"] = year
                    matches.append(row)
                    season_added += 1
                    if len(matches) >= max_matches:
                        break

                if len(summaries) < page_size:
                    break
                start += page_size

        if season_added and successful_season is None:
            successful_season = year
        if season_added >= min(30, max_matches):
            break

    matches.sort(
        key=lambda m: str(m.get("start_time") or ""),
        reverse=not upcoming_only,
    )

    return {
        "matches": matches,
        "season_years_tried": tried,
        "successful_season": successful_season,
        "competition_id": competition_id,
    }
