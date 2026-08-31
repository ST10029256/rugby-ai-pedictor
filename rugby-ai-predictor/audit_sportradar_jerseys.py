#!/usr/bin/env python3
"""Audit SportRadar Rugby API payloads for official jersey / kit colour fields.

Scans the app's 10 mapped leagues and looks for fields that could represent
official jerseys, kits, uniforms, colours, logos, or team images.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import quote

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore


BASE_URL = os.getenv(
    "SPORTRADAR_RUGBY_BASE_URL",
    "https://api.sportradar.com/rugby-union/trial/v3/en",
).rstrip("/")

LEAGUES: List[Tuple[str, int, str]] = [
    ("Rugby Championship", 4986, "sr:competition:789"),
    ("United Rugby Championship", 4446, "sr:competition:419"),
    ("Currie Cup", 5069, "sr:competition:796"),
    ("Rugby World Cup", 4574, "sr:competition:421"),
    ("Super Rugby", 4551, "sr:competition:422"),
    ("French Top 14", 4430, "sr:competition:420"),
    ("English Premiership", 4414, "sr:competition:424"),
    ("Six Nations", 4714, "sr:competition:423"),
    ("International Friendlies", 5479, "sr:competition:876"),
    ("Nations Championship", 5480, "sr:competition:51392"),
]

KEYWORDS = (
    "jersey",
    "kit",
    "uniform",
    "colour",
    "color",
    "shirt",
    "logo",
    "image",
    "crest",
    "emblem",
)

REQUEST_DELAY_S = 0.35


def load_env() -> None:
    if load_dotenv is None:
        return
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    for path in (repo_root / ".env", here.parent / ".env", here.parent / ".env.local"):
        if path.exists():
            load_dotenv(path, override=path.name == ".env.local")


def api_key() -> str:
    load_env()
    return (
        os.getenv("SPORTRADAR_API_KEY")
        or os.getenv("SPORTRADAR_RUGBY_API_KEY")
        or ""
    ).strip()


def get(session: requests.Session, path: str, params: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    time.sleep(REQUEST_DELAY_S)
    response = session.get(url, params=params or {}, timeout=30)
    try:
        payload = response.json()
    except Exception:
        payload = {}
    return response.status_code, payload if isinstance(payload, dict) else {}


def iter_matching_fields(obj: Any, path: str = "$") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"
            key_l = str(key).lower()
            if any(token in key_l for token in KEYWORDS):
                yield child_path, value
            yield from iter_matching_fields(value, child_path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from iter_matching_fields(item, f"{path}[{idx}]")


def compact_value(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 220 else f"{text[:220]}..."


def pick_season(seasons: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not seasons:
        return None
    # Prefer newest by start_date, then fall back to first.
    seasons = [s for s in seasons if isinstance(s, dict)]
    seasons.sort(key=lambda s: str(s.get("start_date") or s.get("year") or ""), reverse=True)
    return seasons[0] if seasons else None


def collect_competitors_from_summaries(summaries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in summaries:
        sport_event = item.get("sport_event") if isinstance(item, dict) else {}
        competitors = sport_event.get("competitors") if isinstance(sport_event, dict) else []
        if not isinstance(competitors, list):
            continue
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id")
            if cid:
                out[str(cid)] = comp
    return out


def audit_payload(label: str, payload: Dict[str, Any], hits: Dict[str, List[Tuple[str, str]]]) -> None:
    for field_path, value in iter_matching_fields(payload):
        hits[label].append((field_path, compact_value(value)))


def main() -> int:
    key = api_key()
    if not key:
        print("SPORTRADAR_API_KEY / SPORTRADAR_RUGBY_API_KEY not found.")
        print("Add it to rugby-ai-predictor/.env.local or export it before running.")
        return 2

    session = requests.Session()
    session.headers.update({"accept": "application/json", "x-api-key": key})

    total_hits: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    league_rows = []

    print(f"SportRadar jersey/kit audit against {BASE_URL}")
    print("=" * 80)

    for league_name, local_id, competition_id in LEAGUES:
        league_hits: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        print(f"\n## {league_name} ({local_id})")

        comp_enc = quote(competition_id, safe="")
        code, seasons_payload = get(session, f"competitions/{comp_enc}/seasons.json")
        print(f"seasons.json HTTP={code}")
        audit_payload(f"{league_name}: seasons", seasons_payload, league_hits)

        season = pick_season(seasons_payload.get("seasons") or [])
        if not season:
            print("No season found.")
            league_rows.append((league_name, 0, 0, 0))
            continue

        season_id = str(season.get("id") or "")
        print(f"Selected season: {season.get('name') or season.get('year')} ({season_id})")

        season_enc = quote(season_id, safe="")
        code, summaries_payload = get(session, f"seasons/{season_enc}/summaries.json", {"start": 0, "limit": 50})
        summaries = summaries_payload.get("summaries") if isinstance(summaries_payload, dict) else []
        summaries = summaries if isinstance(summaries, list) else []
        print(f"summaries.json HTTP={code} summaries={len(summaries)}")
        audit_payload(f"{league_name}: summaries", summaries_payload, league_hits)

        competitors = collect_competitors_from_summaries(summaries)
        print(f"competitors discovered={len(competitors)}")

        # Sample competitor profile payloads.
        profile_count = 0
        for cid, comp in list(competitors.items())[:12]:
            cid_enc = quote(cid, safe="")
            code, profile = get(session, f"competitors/{cid_enc}/profile.json")
            if code == 200:
                profile_count += 1
                audit_payload(f"{league_name}: competitor profile {comp.get('name') or cid}", profile, league_hits)

        # Sample one recent event summary and lineups payload.
        event_count = 0
        lineup_count = 0
        for item in summaries[:8]:
            sport_event = item.get("sport_event") if isinstance(item, dict) else {}
            event_id = sport_event.get("id") if isinstance(sport_event, dict) else None
            if not event_id:
                continue
            event_enc = quote(str(event_id), safe="")
            code, event_summary = get(session, f"sport_events/{event_enc}/summary.json")
            if code == 200:
                event_count += 1
                audit_payload(f"{league_name}: event summary {event_id}", event_summary, league_hits)
            code, lineups = get(session, f"sport_events/{event_enc}/lineups.json", {"live": "false"})
            if code == 200:
                lineup_count += 1
                audit_payload(f"{league_name}: lineups {event_id}", lineups, league_hits)
            break

        hit_count = sum(len(v) for v in league_hits.values())
        jersey_hits = [
            (label, path, value)
            for label, rows in league_hits.items()
            for path, value in rows
            if any(token in path.lower() for token in ("jersey", "kit", "uniform", "colour", "color", "shirt"))
        ]
        media_hits = hit_count - len(jersey_hits)
        print(f"profile payloads={profile_count}, event summaries={event_count}, lineup payloads={lineup_count}")
        print(f"kit/colour field hits={len(jersey_hits)}, logo/image-style hits={media_hits}")

        if jersey_hits:
            print("Possible jersey/kit fields:")
            for label, path, value in jersey_hits[:8]:
                print(f"  - {label} :: {path} = {value}")
        else:
            print("No jersey/kit/uniform/colour fields found in sampled payloads.")

        for label, rows in league_hits.items():
            total_hits[label].extend(rows)
        league_rows.append((league_name, len(jersey_hits), media_hits, hit_count))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for league_name, jersey_count, media_count, total in league_rows:
        print(f"{league_name:32} jersey/kit={jersey_count:3d} logo/image={media_count:3d} total={total:3d}")

    all_jersey_hits = [
        (label, path, value)
        for label, rows in total_hits.items()
        for path, value in rows
        if any(token in path.lower() for token in ("jersey", "kit", "uniform", "colour", "color", "shirt"))
    ]
    print("\nConclusion:")
    if all_jersey_hits:
        print("SportRadar exposed possible jersey/kit fields in the sampled payloads above.")
        print("Review those exact paths before wiring them into the app.")
    else:
        print("No official jersey colour / kit fields were found in sampled SportRadar Rugby payloads.")
        print("The API appears to expose competitors, lineups, scores, venue/context and sometimes media-like fields,")
        print("but not official home/away jersey colour data for rugby teams in these endpoints.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
