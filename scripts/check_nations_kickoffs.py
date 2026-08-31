"""Compare Nations Championship kickoff times: Highlightly vs DB vs SAST display."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rugby-ai-predictor"))

from prediction.highlightly_client import HighlightlyRugbyAPI
from prediction.kickoff_times import enrich_matches_kickoff, normalize_kickoff_iso

SAST = ZoneInfo("Africa/Johannesburg")
LEAGUE_ID = 5480
HL_ID = 124179


def to_sast(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local = dt.astimezone(SAST)
    return local.strftime("%Y-%m-%d %I:%M %p SAST").lstrip("0").replace(" 0", " ")


def main() -> None:
    api_key = os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY")
    if not api_key:
        print("Set HIGHLIGHTLY_API_KEY")
        sys.exit(1)

    api = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=False)
    hl_by_teams: dict[tuple[str, str, str], str] = {}
    for season in [2026, 2025]:
        offset = 0
        while offset < 200:
            resp = api.get_matches(league_id=HL_ID, season=season, limit=50, offset=offset)
            rows = resp.get("data") or []
            if not rows:
                break
            for row in rows:
                home = (row.get("homeTeam") or {}).get("name") or ""
                away = (row.get("awayTeam") or {}).get("name") or ""
                raw = row.get("date") or ""
                day = str(raw)[:10]
                hl_by_teams[(day, home, away)] = raw
            offset += len(rows)
            if len(rows) < 50:
                break

    import sqlite3

    db = os.path.join(ROOT, "rugby-ai-predictor", "data.sqlite")
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT e.id, e.date_event, e.timestamp, th.name, ta.name
        FROM event e
        JOIN team th ON th.id = e.home_team_id
        JOIN team ta ON ta.id = e.away_team_id
        WHERE e.league_id = ? AND date(e.date_event) >= date('now')
        ORDER BY e.timestamp
        LIMIT 12
        """,
        (LEAGUE_ID,),
    ).fetchall()
    conn.close()

    print("Nations Championship (5480) — kickoff verification\n")
    print(f"{'Fixture':<42} {'Highlightly UTC':<28} {'App SAST':<22}")
    print("-" * 95)

    for event_id, date_event, ts, home, away in rows:
        match = {
            "id": event_id,
            "home_team": home,
            "away_team": away,
            "date_event": date_event,
        }
        enrich_matches_kickoff([match])
        kickoff = match.get("kickoff_at") or ""
        sast = to_sast(kickoff) if kickoff else "—"
        hl_raw = hl_by_teams.get((date_event, home, away), hl_by_teams.get((str(date_event)[:10], home, away), "—"))
        fixture = f"{home} vs {away}"
        print(f"{fixture:<42} {str(hl_raw):<28} {sast:<22}")

    print("\nRound 1 Sat 4 Jul 2026 — expected SAST (UTC+2):")
    print("  NZ v France     07:10 UTC -> 9:10 AM SAST")
    print("  Japan v Italy   08:40 UTC -> 10:40 AM SAST")
    print("  Aus v Ireland   10:10 UTC -> 12:10 PM SAST")
    print("  SA v England    15:40 UTC -> 5:40 PM SAST")
    print("  Argentina v Sco 19:10 UTC -> 9:10 PM SAST")


if __name__ == "__main__":
    main()
