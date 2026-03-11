#!/usr/bin/env python3
import datetime
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, "rugby-ai-predictor")
from prediction.sportdevs_client import APISPORTS_LEAGUE_BY_LOCAL_ID, SportDevsClient  # noqa: E402


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

    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=30)

    print(f"Window: {today} -> {horizon}")
    print("=" * 120)
    print(
        f"{'League':<36}{'Upcoming':>10}{'StrictEq':>10}{'FuzzyOnly':>12}{'Unmatched':>11}"
    )
    print("-" * 120)

    detailed = defaultdict(list)

    for local_lid, league_name in LEAGUES:
        api_lid = APISPORTS_LEAGUE_BY_LOCAL_ID.get(local_lid, local_lid)
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
            (local_lid, today.isoformat(), horizon.isoformat()),
        )
        rows = cur.fetchall()

        strict_eq = 0
        fuzzy_only = 0
        unmatched = 0

        for _, date_event, home_local, away_local in rows:
            season = client._season_from_match_date(str(date_event), league_id=local_lid)  # diagnostic use
            if season is None:
                unmatched += 1
                detailed[league_name].append(
                    f"{date_event} | {home_local} vs {away_local} | could not derive season"
                )
                continue
            payload = client._make_apisports_request(  # intentional diagnostic use
                "games",
                params={"league": int(api_lid), "season": int(season), "date": str(date_event)[:10]},
            )
            games = (payload or {}).get("response") if isinstance(payload, dict) else None
            if not isinstance(games, list) or not games:
                unmatched += 1
                detailed[league_name].append(
                    f"{date_event} | {home_local} vs {away_local} | no API games on date"
                )
                continue

            hn = client._normalize_team_name(home_local)
            an = client._normalize_team_name(away_local)

            found_strict = False
            found_fuzzy = False
            best_api_pair = None

            for g in games:
                teams = (g or {}).get("teams") or {}
                api_home = str((teams.get("home") or {}).get("name") or "")
                api_away = str((teams.get("away") or {}).get("name") or "")
                h2 = client._normalize_team_name(api_home)
                a2 = client._normalize_team_name(api_away)
                if not best_api_pair:
                    best_api_pair = f"{api_home} vs {api_away}"

                strict_direct = hn == h2 and an == a2
                strict_swap = hn == a2 and an == h2
                if strict_direct or strict_swap:
                    found_strict = True
                    break

                fuzzy_direct = client._team_names_match(hn, h2) and client._team_names_match(an, a2)
                fuzzy_swap = client._team_names_match(hn, a2) and client._team_names_match(an, h2)
                if fuzzy_direct or fuzzy_swap:
                    found_fuzzy = True

            if found_strict:
                strict_eq += 1
            elif found_fuzzy:
                fuzzy_only += 1
                detailed[league_name].append(
                    f"{date_event} | {home_local} vs {away_local} | fuzzy-only match (api sample: {best_api_pair})"
                )
            else:
                unmatched += 1
                detailed[league_name].append(
                    f"{date_event} | {home_local} vs {away_local} | unmatched (api sample: {best_api_pair})"
                )

        print(f"{league_name:<36}{len(rows):>10}{strict_eq:>10}{fuzzy_only:>12}{unmatched:>11}")

    print("=" * 120)
    print("Potential naming conflicts (fuzzy-only/unmatched):")
    any_conflicts = False
    for league_name, issues in detailed.items():
        if not issues:
            continue
        any_conflicts = True
        print(f"\n[{league_name}]")
        for line in issues[:10]:
            print(" -", line)
        if len(issues) > 10:
            print(f" - ... and {len(issues) - 10} more")
    if not any_conflicts:
        print("None found in 30-day upcoming window.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
