#!/usr/bin/env python3
"""Thorough per-team SportRadar jersey audit across all 10 app leagues.

For every unique competitor in the selected season, fetches
competitors/{id}/profile.json and records whether official $.jerseys
colour data exists (home / away / third / other).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

# Allow running from rugby-ai-predictor/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prediction.sportradar_client import (  # noqa: E402
    BASE_URL,
    SportRadarRugbyClient,
    candidate_season_years,
    competition_for_local_id,
)

LEAGUES = [
    ("Rugby Championship", 4986),
    ("United Rugby Championship", 4446),
    ("Currie Cup", 5069),
    ("Rugby World Cup", 4574),
    ("Super Rugby", 4551),
    ("French Top 14", 4430),
    ("English Premiership", 4414),
    ("Six Nations", 4714),
    ("International Friendlies", 5479),
    ("Nations Championship", 5480),
]

KIT_PRIORITY = ("home", "away", "third", "alternate", "fourth")


@dataclass
class TeamJerseyResult:
    competitor_id: str
    name: str
    country: Optional[str] = None
    http_status: int = 0
    has_jerseys: bool = False
    kit_types: List[str] = field(default_factory=list)
    kits: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class LeagueJerseyReport:
    league_name: str
    local_league_id: int
    competition_id: str
    season_id: Optional[str] = None
    season_name: Optional[str] = None
    teams_total: int = 0
    teams_with_jerseys: int = 0
    teams_without_jerseys: int = 0
    teams_failed: int = 0
    teams: List[TeamJerseyResult] = field(default_factory=list)


def hex_colour(value: Any) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in v):
        return f"#{v.lower()}"
    return None


def summarize_kit(jerseys: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick best kit for display: prefer home, then away, then third."""
    if not jerseys:
        return {}
    by_type = {str(j.get("type") or "").lower(): j for j in jerseys if isinstance(j, dict)}
    for kit_type in KIT_PRIORITY:
        if kit_type in by_type:
            j = by_type[kit_type]
            base = hex_colour(j.get("base"))
            sleeve = hex_colour(j.get("sleeve"))
            number = hex_colour(j.get("number"))
            if base or sleeve or number:
                return {
                    "type": kit_type,
                    "base": base,
                    "sleeve": sleeve,
                    "number": number,
                    "horizontal_stripes": bool(j.get("horizontal_stripes")),
                    "stripes": bool(j.get("stripes")),
                }
    # Any kit with colour fields
    for j in jerseys:
        if not isinstance(j, dict):
            continue
        base = hex_colour(j.get("base"))
        if base:
            return {
                "type": str(j.get("type") or "unknown"),
                "base": base,
                "sleeve": hex_colour(j.get("sleeve")),
                "number": hex_colour(j.get("number")),
            }
    return {}


def collect_competitors_from_summaries(summaries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        sport_event = item.get("sport_event") or {}
        competitors = sport_event.get("competitors") or []
        if not isinstance(competitors, list):
            continue
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id")
            if cid:
                out[str(cid)] = comp
    return out


def collect_competitors_from_standings(standings_raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    groups = standings_raw.get("groups") if isinstance(standings_raw, dict) else []
    if not isinstance(groups, list):
        return out
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key in ("standings", "teams"):
            rows = group.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                comp = row.get("competitor") if isinstance(row.get("competitor"), dict) else row
                cid = comp.get("id") if isinstance(comp, dict) else None
                if cid:
                    out[str(cid)] = comp
    return out


def fetch_all_summaries(client: SportRadarRugbyClient, season_id: str) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    start = 0
    page_size = 200
    while True:
        raw = client.fetch_season_summaries_raw(season_id, start=start, limit=page_size)
        if not raw:
            break
        batch = raw.get("summaries")
        if not isinstance(batch, list) or not batch:
            break
        all_items.extend([b for b in batch if isinstance(b, dict)])
        if len(batch) < page_size:
            break
        start += page_size
    return all_items


def fetch_profile_with_retry(
    client: SportRadarRugbyClient,
    competitor_id: str,
    *,
    max_attempts: int = 5,
) -> tuple[int, Dict[str, Any]]:
    enc = quote(competitor_id, safe="")
    path = f"competitors/{enc}/profile.json"
    for attempt in range(max_attempts):
        raw = client._get(path)  # noqa: SLF001 — audit script
        if raw is not None:
            return 200, raw
        # _get returns None on 404 and after retries on failure; check rate limit via delay
        time.sleep(1.5 * (attempt + 1))
    return 0, {}


def resolve_season(client: SportRadarRugbyClient, local_id: int, competition_id: str) -> Optional[Dict[str, Any]]:
    seasons = client.list_seasons(competition_id)
    if not seasons:
        return None
    years = candidate_season_years(local_id)
    for year in years:
        sid = client.resolve_season_id(competition_id, year)
        if not sid:
            continue
        for s in seasons:
            if str(s.get("id")) == str(sid):
                return s
    # fallback newest
    seasons = [s for s in seasons if isinstance(s, dict)]
    seasons.sort(key=lambda s: str(s.get("start_date") or ""), reverse=True)
    return seasons[0] if seasons else None


def audit_league(client: SportRadarRugbyClient, league_name: str, local_id: int) -> LeagueJerseyReport:
    competition_id = competition_for_local_id(local_id) or ""
    report = LeagueJerseyReport(
        league_name=league_name,
        local_league_id=local_id,
        competition_id=competition_id,
    )

    season = resolve_season(client, local_id, competition_id)
    if not season:
        report.error = "no_season"
        return report

    season_id = str(season.get("id") or "")
    report.season_id = season_id
    report.season_name = str(season.get("name") or season.get("year") or "")

    competitors: Dict[str, Dict[str, Any]] = {}

    summaries = fetch_all_summaries(client, season_id)
    competitors.update(collect_competitors_from_summaries(summaries))

    standings_raw = client.fetch_standings_raw(season_id)
    if standings_raw:
        competitors.update(collect_competitors_from_standings(standings_raw))

    report.teams_total = len(competitors)

    for cid, comp in sorted(competitors.items(), key=lambda kv: (kv[1].get("name") or "").lower()):
        name = str(comp.get("name") or cid)
        country = comp.get("country") or comp.get("country_code")
        status, profile = fetch_profile_with_retry(client, cid)

        row = TeamJerseyResult(
            competitor_id=cid,
            name=name,
            country=str(country) if country else None,
            http_status=status,
        )

        if status != 200 or not profile:
            row.error = "profile_fetch_failed"
            report.teams_failed += 1
            report.teams.append(row)
            continue

        jerseys = profile.get("jerseys")
        if isinstance(jerseys, list) and jerseys:
            valid = [j for j in jerseys if isinstance(j, dict) and hex_colour(j.get("base"))]
            if valid:
                row.has_jerseys = True
                row.kits = valid
                row.kit_types = sorted({str(j.get("type") or "unknown").lower() for j in valid})
                report.teams_with_jerseys += 1
            else:
                report.teams_without_jerseys += 1
        else:
            report.teams_without_jerseys += 1

        report.teams.append(row)

    return report


def print_league_report(report: LeagueJerseyReport) -> None:
    print(f"\n{'=' * 80}")
    print(f"{report.league_name} (id={report.local_league_id})")
    print(f"Season: {report.season_name} ({report.season_id})")
    print(f"Teams: {report.teams_total} | with jerseys: {report.teams_with_jerseys} | without: {report.teams_without_jerseys} | failed: {report.teams_failed}")

    if report.teams_total:
        pct = 100.0 * report.teams_with_jerseys / report.teams_total
        print(f"Coverage: {pct:.1f}%")

    print("\nTeam-by-team:")
    for t in report.teams:
        if t.has_jerseys:
            summary = summarize_kit(t.kits)
            types = ",".join(t.kit_types)
            colours = f"base={summary.get('base')} sleeve={summary.get('sleeve')} number={summary.get('number')}"
            print(f"  OK  {t.name:36} [{types:20}] {colours}")
        elif t.error:
            print(f"  ERR {t.name:36} HTTP={t.http_status} {t.error}")
        else:
            print(f"  MISS {t.name:36} no $.jerseys colour data")


def main() -> int:
    client = SportRadarRugbyClient()
    if not client.configured:
        print("SPORTRADAR_API_KEY not configured.")
        return 2

    print(f"Full per-team jersey audit — {len(LEAGUES)} leagues")
    print(f"Base URL: {BASE_URL}")

    reports: List[LeagueJerseyReport] = []
    for league_name, local_id in LEAGUES:
        print(f"\nScanning {league_name}...")
        report = audit_league(client, league_name, local_id)
        reports.append(report)
        print_league_report(report)

    print(f"\n{'=' * 80}")
    print("GRAND SUMMARY")
    print(f"{'=' * 80}")
    total_teams = sum(r.teams_total for r in reports)
    total_ok = sum(r.teams_with_jerseys for r in reports)
    total_miss = sum(r.teams_without_jerseys for r in reports)
    total_fail = sum(r.teams_failed for r in reports)

    for r in reports:
        pct = (100.0 * r.teams_with_jerseys / r.teams_total) if r.teams_total else 0.0
        print(
            f"{r.league_name:32} teams={r.teams_total:3d}  "
            f"with_kit={r.teams_with_jerseys:3d}  miss={r.teams_without_jerseys:3d}  "
            f"fail={r.teams_failed:3d}  ({pct:5.1f}%)"
        )

    overall_pct = (100.0 * total_ok / total_teams) if total_teams else 0.0
    print(f"\nTOTAL: {total_teams} teams | {total_ok} with official jersey colours | {total_miss} missing | {total_fail} failed")
    print(f"Overall coverage: {overall_pct:.1f}%")

    out_path = Path(__file__).resolve().parent / "audit_sportradar_jerseys_all_teams.json"
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "teams_total": total_teams,
            "teams_with_jerseys": total_ok,
            "teams_without_jerseys": total_miss,
            "teams_failed": total_fail,
            "coverage_pct": round(overall_pct, 2),
        },
        "leagues": [
            {
                **{k: v for k, v in asdict(r).items() if k != "teams"},
                "teams": [
                    {
                        **asdict(t),
                        "primary_kit": summarize_kit(t.kits) if t.kits else None,
                    }
                    for t in r.teams
                ],
            }
            for r in reports
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nFull JSON report written to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
