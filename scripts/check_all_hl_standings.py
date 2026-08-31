"""Check Highlightly standings availability for every app league."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rugby-ai-predictor"))

from prediction.highlightly_client import HighlightlyRugbyAPI
from prediction.standings_compute import (
    SKIP_COMPUTE_LEAGUE_IDS,
    compute_standings_from_db,
    highlightly_standings_usable,
    normalize_highlightly_standings,
    resolve_standings_db_path,
)

LEAGUES = {
    4986: (73119, "Rugby Championship"),
    4446: (65460, "United Rugby Championship"),
    5069: (32271, "Currie Cup"),
    4574: (59503, "Rugby World Cup"),
    4551: (61205, "Super Rugby"),
    4430: (14400, "French Top 14"),
    4414: (11847, "English Premiership Rugby"),
    4714: (44185, "Six Nations Championship"),
    5479: (72268, "International Friendlies"),
    5480: (124179, "Nations Championship"),
}

NO_STANDINGS_UI = {5479, 5480}
CROSS_YEAR = {65460, 11847, 14400}
RWC = 59503


def seasons_for(hl_id: int) -> list[int]:
    now = datetime.utcnow()
    year, month = now.year, now.month
    if hl_id == RWC:
        return [2023, 2019, 2015]
    if hl_id in CROSS_YEAR:
        primary = year - 1 if month <= 6 else year
        out: list[int] = []
        for s in [primary, primary - 1, primary + 1, year, year - 1]:
            if s not in out:
                out.append(s)
        return out
    out = []
    for s in [year, year - 1, year + 1, year - 2]:
        if s not in out:
            out.append(s)
    return out


def team_count(standings: dict) -> int:
    total = 0
    for g in standings.get("groups") or []:
        if isinstance(g, dict):
            total += len(g.get("standings") or g.get("teams") or [])
    return total


def main() -> None:
    api_key = os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY")
    if not api_key:
        print("Set HIGHLIGHTLY_API_KEY")
        sys.exit(1)

    api = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=False)
    db = resolve_standings_db_path()
    now = datetime.utcnow()
    print(f"UTC now: {now.isoformat()}\n")

    rows = []
    for our_id, (hl_id, name) in LEAGUES.items():
        hl_ok = False
        hl_teams = 0
        hl_season = None
        rate_limited = False

        for s in seasons_for(hl_id):
            resp = api.get_standings(hl_id, s)
            if resp.get("_rate_limited"):
                rate_limited = True
                break
            if highlightly_standings_usable(resp):
                norm = normalize_highlightly_standings(resp)
                hl_teams = team_count(norm)
                hl_season = s
                hl_ok = True
                break
            time.sleep(0.25)

        compute_teams = 0
        compute_ok = False
        if our_id not in SKIP_COMPUTE_LEAGUE_IDS and our_id not in NO_STANDINGS_UI:
            comp = compute_standings_from_db(db, our_id, season=seasons_for(hl_id)[0])
            if comp and comp.get("groups"):
                compute_teams = team_count(comp)
                compute_ok = True

        if rate_limited:
            source = "RATE LIMITED"
            fallback = "-"
        elif our_id in NO_STANDINGS_UI:
            source = "N/A (no table in app)"
            fallback = "-"
        elif hl_ok:
            source = "highlightly"
            fallback = f"{compute_teams} teams" if compute_ok else "none"
        elif compute_ok:
            source = "compute fallback"
            fallback = f"{compute_teams} teams"
        else:
            source = "NONE"
            fallback = "none"

        rows.append(
            {
                "name": name,
                "our_id": our_id,
                "hl_id": hl_id,
                "hl_ok": hl_ok,
                "teams": hl_teams if hl_ok else compute_teams,
                "season": hl_season,
                "source": source,
                "fallback": fallback,
            }
        )
        time.sleep(1.0)

    print(f"{'League':<34} {'Our':>5} {'HL':>6} {'Teams':>5} {'Season':>6}  Source / fallback")
    print("-" * 95)
    for r in rows:
        season = r["season"] if r["season"] else "-"
        teams = r["teams"] if r["teams"] else "-"
        print(
            f"{r['name']:<34} {r['our_id']:>5} {r['hl_id']:>6} {teams!s:>5} {season!s:>6}  "
            f"{r['source']} ({r['fallback']})"
        )

    hl_count = sum(1 for r in rows if r["source"] == "highlightly")
    fb_count = sum(1 for r in rows if r["source"] == "compute fallback")
    none_count = sum(1 for r in rows if r["source"] == "NONE")
    print(f"\nSummary: {hl_count} Highlightly, {fb_count} compute fallback, {none_count} no data")


if __name__ == "__main__":
    main()
