#!/usr/bin/env python3
import datetime
import sqlite3
import sys

sys.path.insert(0, "rugby-ai-predictor")
from prediction.sportdevs_client import SportDevsClient, extract_odds_features  # noqa: E402


LEAGUES = [
    (4986, "Rugby Championship"),
    (4446, "United Rugby Championship"),
    (5069, "Currie Cup"),
    (4574, "Rugby World Cup"),
    (4551, "Super Rugby"),
    (4430, "French Top 14"),
    (4414, "English Premiership Rugby"),
    (4714, "Six Nations Championship"),
    (5479, "Rugby Union International Friendlies"),
]


def main() -> int:
    client = SportDevsClient(api_key="")
    conn = sqlite3.connect("data.sqlite")
    cur = conn.cursor()

    start = datetime.date.today()
    end = start + datetime.timedelta(days=7)
    print(f"Window: {start} -> {end}")
    print("-" * 100)
    print(f"{'ID':<6}{'League':<36}{'Upcoming':>10}{'WithOdds':>10}{'Pct':>10}")
    print("-" * 100)

    for lid, name in LEAGUES:
        cur.execute(
            """
            SELECT e.id, e.date_event, ht.name, at.name
            FROM event e
            JOIN team ht ON ht.id = e.home_team_id
            JOIN team at ON at.id = e.away_team_id
            WHERE e.league_id = ?
              AND (e.home_score IS NULL OR e.away_score IS NULL)
              AND date(e.date_event) >= date(?)
              AND date(e.date_event) <= date(?)
            ORDER BY date(e.date_event) ASC
            """,
            (lid, start.isoformat(), end.isoformat()),
        )
        rows = cur.fetchall()
        with_odds = 0
        for mid, mdate, home, away in rows:
            odds = client.get_match_odds(
                match_id=int(mid),
                league_id=int(lid),
                match_date=str(mdate),
                home_team=str(home),
                away_team=str(away),
            )
            f = extract_odds_features(odds)
            if int(f.get("bookmaker_count", 0) or 0) > 0:
                with_odds += 1
        total = len(rows)
        pct = (100.0 * with_odds / total) if total else 0.0
        print(f"{lid:<6}{name:<36}{total:>10}{with_odds:>10}{pct:>9.1f}%")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
