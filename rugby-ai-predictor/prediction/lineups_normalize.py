"""Normalize SportRadar sport event lineups for the frontend."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

JERSEY_POSITION_LABELS: Dict[int, str] = {
    1: "Loosehead Prop",
    2: "Hooker",
    3: "Tighthead Prop",
    4: "Lock",
    5: "Lock",
    6: "Blindside Flanker",
    7: "Openside Flanker",
    8: "Number Eight",
    9: "Scrum-half",
    10: "Fly-half",
    11: "Left Wing",
    12: "Inside Centre",
    13: "Outside Centre",
    14: "Right Wing",
    15: "Fullback",
}

POSITION_CODE_LABELS: Dict[str, str] = {
    "PR": "Prop",
    "HO": "Hooker",
    "FB": "Prop",
    "L": "Lock",
    "FL": "Flanker",
    "BR": "Back Row",
    "SH": "Scrum-half",
    "FH": "Fly-half",
    "C": "Centre",
    "W": "Wing",
    "UB": "Utility Back",
}


def _format_player_name(raw: str) -> str:
    text = (raw or "").strip()
    if "," in text:
        last, first = text.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return text


def _player_age(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        born = datetime.strptime(str(dob)[:10], "%Y-%m-%d").date()
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return age if age >= 0 else None
    except ValueError:
        return None


def _normalize_player(raw: Dict[str, Any]) -> Dict[str, Any]:
    jersey = raw.get("jersey_number")
    try:
        jersey_num = int(jersey) if jersey is not None else None
    except (TypeError, ValueError):
        jersey_num = None

    pos_code = str(raw.get("type") or "").strip().upper()
    position_label = JERSEY_POSITION_LABELS.get(jersey_num or 0) or POSITION_CODE_LABELS.get(
        pos_code, pos_code or "—"
    )

    return {
        "id": raw.get("id"),
        "name": _format_player_name(str(raw.get("name") or "")),
        "raw_name": raw.get("name"),
        "jersey_number": jersey_num,
        "position_code": pos_code or None,
        "position_label": position_label,
        "nationality": raw.get("nationality"),
        "country_code": raw.get("country_code"),
        "height_cm": raw.get("height"),
        "weight_kg": raw.get("weight"),
        "date_of_birth": raw.get("date_of_birth"),
        "age": _player_age(raw.get("date_of_birth")),
        "starter": bool(raw.get("starter")),
        "played": bool(raw.get("played")),
        "nickname": raw.get("nickname"),
    }


def _squad_summary(players: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_jersey: Dict[int, Dict[str, Any]] = {}
    unlisted: List[Dict[str, Any]] = []
    for player in players:
        jersey = player.get("jersey_number")
        try:
            num = int(jersey) if jersey is not None else None
        except (TypeError, ValueError):
            num = None
        if num is None or num < 1 or num > 23:
            unlisted.append(player)
            continue
        if num in by_jersey:
            unlisted.append(player)
        else:
            by_jersey[num] = player
    missing = [j for j in range(1, 24) if j not in by_jersey]
    return {
        "total_rows": len(players),
        "slots_filled": len(by_jersey),
        "expected_slots": 23,
        "missing_jerseys": missing,
        "unlisted_count": len(unlisted),
        "is_complete": len(by_jersey) >= 23 and not unlisted,
    }


def normalize_sportradar_lineups(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert SportRadar lineups.json into app-friendly match + teams payload."""
    sport_event = raw.get("sport_event") if isinstance(raw.get("sport_event"), dict) else {}
    status = raw.get("sport_event_status") if isinstance(raw.get("sport_event_status"), dict) else {}
    ctx = sport_event.get("sport_event_context") if isinstance(sport_event.get("sport_event_context"), dict) else {}
    competition = ctx.get("competition") if isinstance(ctx.get("competition"), dict) else {}
    season = ctx.get("season") if isinstance(ctx.get("season"), dict) else {}
    stage = ctx.get("stage") if isinstance(ctx.get("stage"), dict) else {}
    round_info = ctx.get("round") if isinstance(ctx.get("round"), dict) else {}
    venue = sport_event.get("venue") if isinstance(sport_event.get("venue"), dict) else {}

    lineups_block = raw.get("lineups")
    team_blocks: List[Dict[str, Any]] = []
    if isinstance(lineups_block, dict):
        maybe = lineups_block.get("competitors")
        if isinstance(maybe, list):
            team_blocks = [b for b in maybe if isinstance(b, dict)]
    elif isinstance(lineups_block, list):
        team_blocks = [b for b in lineups_block if isinstance(b, dict)]

    teams_out: List[Dict[str, Any]] = []
    for block in team_blocks:
        players_raw = block.get("players")
        players: List[Dict[str, Any]] = []
        if isinstance(players_raw, list):
            players = [_normalize_player(p) for p in players_raw if isinstance(p, dict)]
        teams_out.append(
            {
                "id": block.get("id"),
                "name": block.get("name"),
                "abbreviation": block.get("abbreviation"),
                "qualifier": block.get("qualifier"),
                "players": players,
                "squad_summary": _squad_summary(players),
            }
        )

    competitors_meta = sport_event.get("competitors")
    if isinstance(competitors_meta, list):
        for comp in competitors_meta:
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id")
            for team in teams_out:
                if team.get("id") == cid:
                    team.setdefault("name", comp.get("name"))
                    team.setdefault("abbreviation", comp.get("abbreviation"))
                    team.setdefault("qualifier", comp.get("qualifier"))

    return {
        "match": {
            "id": sport_event.get("id"),
            "start_time": sport_event.get("start_time"),
            "competition": competition.get("name"),
            "competition_id": competition.get("id"),
            "season": season.get("name") or season.get("year"),
            "stage": stage.get("phase") or stage.get("type"),
            "round": round_info.get("name"),
            "venue": venue.get("name"),
            "city": venue.get("city_name"),
            "country": venue.get("country_name"),
            "status": status.get("status") or status.get("match_status"),
            "home_score": status.get("home_score"),
            "away_score": status.get("away_score"),
        },
        "teams": teams_out,
        "_source": "sportradar",
    }
