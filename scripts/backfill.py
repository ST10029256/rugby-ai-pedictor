from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from typing import List, Optional, Any

from prediction.config import load_config
from prediction.sportsdb_client import TheSportsDBClient
from prediction.db import connect, init_db, upsert_league, upsert_season, upsert_team, bulk_upsert_events, team_exists


RUGBY_SPORT_NAME = "Rugby Union"
RWC_LEAGUE_ID = 4574
RWC_OFFICIAL_YEARS = {1987, 1991, 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Backfill rugby data into SQLite from TheSportsDB")
	parser.add_argument("--db", default="data.sqlite", help="SQLite DB path")
	parser.add_argument("--leagues", nargs="*", default=["United Rugby Championship", "Currie Cup"], help="League names to backfill")
	parser.add_argument("--league-ids", nargs="*", type=int, default=[], help="Explicit TheSportsDB league IDs (bypass name lookup)")
	parser.add_argument("--max-seasons", type=int, default=0, help="Limit to last N seasons; 0 = all")
	parser.add_argument("--through-year", type=int, default=2025, help="Force-attempt seasons through this year if missing")
	parser.add_argument("--api-key", default=None, help="Optional override TheSportsDB API key just for this run")
	return parser.parse_args()


def ensure_teams_for_events(conn, events: List[dict], league_id: int) -> None:
	seen: set[int] = set()
	for ev in events:
		pairs = (
			("idHomeTeam", "strHomeTeam"),
			("idAwayTeam", "strAwayTeam"),
		)
		for id_key, name_key in pairs:
			raw = ev.get(id_key)
			if not raw:
				continue
			try:
				tid = int(raw)
			except Exception:
				continue
			if tid in seen or team_exists(conn, tid):
				seen.add(tid)
				continue
			seen.add(tid)
			team_stub = {
				"idTeam": tid,
				"idLeague": league_id,
				"strTeam": ev.get(name_key) or f"Unknown {tid}",
				"strTeamShort": None,
				"strAlternate": None,
				"strStadium": None,
				"intFormedYear": None,
				"strCountry": None,
			}
			upsert_team(conn, team_stub, league_id=league_id)
	conn.commit()


def sanitize_event_team_refs(conn, events: List[dict]) -> None:
	for ev in events:
		for key in ("idHomeTeam", "idAwayTeam"):
			raw = ev.get(key)
			if not raw:
				continue
			try:
				tid = int(raw)
			except Exception:
				ev[key] = None
				continue
			if not team_exists(conn, tid):
				ev[key] = None


def generate_missing_seasons(existing: List[str], through_year: int) -> List[str]:
	rng = re.compile(r"^(\d{4})-(\d{4})$")
	numeric = re.compile(r"^(\d{4})$")
	range_years = []
	single_years = []
	for s in existing:
		m = rng.match(s)
		if m:
			range_years.append((int(m.group(1)), int(m.group(2))))
			continue
		m2 = numeric.match(s)
		if m2:
			single_years.append(int(m2.group(1)))
	to_attempt: List[str] = []
	if range_years:
		max_second = max(y2 for _, y2 in range_years)
		start = max_second + 1
		for y2 in range(start, through_year + 1):
			y1 = y2 - 1
			to_attempt.append(f"{y1}-{y2}")
	if single_years:
		max_year = max(single_years)
		for y in range(max_year + 1, through_year + 1):
			to_attempt.append(str(y))
	return to_attempt


def season_date_bounds(season: str) -> tuple[str, str, bool]:
	# Returns (start_iso, end_iso, is_range_style)
	if re.match(r"^\d{4}-\d{4}$", season):
		y1, y2 = map(int, season.split("-"))
		# URC typical window Aug->May
		start = f"{y1}-08-01"
		end = f"{y2}-05-31"
		return start, end, True
	if re.match(r"^\d{4}$", season):
		y = int(season)
		# Currie Cup typical window May->Nov
		return f"{y}-05-01", f"{y}-11-30", False
	# Fallback full year
	return "2000-01-01", "2030-12-31", False


def fetch_season_events_with_gaps(client: Any, league_id: int, season: str) -> List[dict]:
	events = client.get_events_for_season(league_id, season)
	if events:
		return events
	# Special-case Rugby World Cup: only scan official tournament years
	if re.match(r"^\d{4}$", season) and league_id == RWC_LEAGUE_ID:
		y = int(season)
		if y not in RWC_OFFICIAL_YEARS:
			return []
	# Gap fill by day (optimize to Fri–Sun only)
	start_str, end_str, is_range = season_date_bounds(season)
	start = datetime.fromisoformat(start_str)
	end = datetime.fromisoformat(end_str)
	cur = start
	merged: dict[str, dict] = {}
	current_month = None
	while cur <= end:
		if current_month != (cur.year, cur.month):
			current_month = (cur.year, cur.month)
			print(f"    Scanning {cur.year}-{cur.month:02d} (Fri–Sun)", flush=True)
		weekday = cur.weekday()  # Mon=0 .. Sun=6
		if weekday in (4, 5, 6):  # Fri, Sat, Sun
			day_iso = cur.date().isoformat()
			day_events = client.get_events_for_day(day_iso, sport=RUGBY_SPORT_NAME, league_id=league_id)
			for ev in day_events:
				ev_id = ev.get("idEvent")
				if ev_id:
					merged[ev_id] = ev
		cur += timedelta(days=1)
	return list(merged.values())


def fetch_and_store_league(conn, client: TheSportsDBClient, league_id: int, league_label: Optional[str] = None, max_seasons: int = 0, through_year: int = 2025) -> None:
	print(f"Processing league id={league_id} ({league_label or 'unknown name'})", flush=True)

	seasons = client.get_seasons(league_id) or []
	seasons_sorted = sorted(seasons)
	forced = generate_missing_seasons(seasons_sorted, through_year)
	if forced:
		print(f"  Attempting extra seasons not listed: {', '.join(forced)}", flush=True)
		seasons_sorted.extend(forced)
	seasons_sorted = sorted(set(seasons_sorted))

	if not seasons_sorted:
		print(f"No seasons for league {league_id}", flush=True)
		return

	if max_seasons and max_seasons > 0:
		seasons_sorted = seasons_sorted[-max_seasons :]

	teams = client.get_teams(league_id)
	for t in teams:
		upsert_team(conn, t, league_id=league_id)
	conn.commit()

	for s in seasons_sorted:
		print(f"  Fetching season {s} for league {league_id}", flush=True)
		upsert_season(conn, league_id, s)
		events = fetch_season_events_with_gaps(client, league_id, s)
		if not events:
			print(f"  No events for season {s}", flush=True)
			continue
		ensure_teams_for_events(conn, events, league_id)
		sanitize_event_team_refs(conn, events)
		bulk_upsert_events(conn, events, override_league_id=league_id)


def main() -> None:
	args = parse_args()
	cfg = load_config()
	api_key = args.api_key if args.api_key else cfg.api_key
	client = TheSportsDBClient(base_url=cfg.base_url, api_key=api_key, rate_limit_rpm=cfg.rate_limit_rpm)

	conn = connect(args.db)
	init_db(conn)

	for lid in args.league_ids:
		fetch_and_store_league(conn, client, lid, league_label=f"id {lid}", max_seasons=args.max_seasons, through_year=args.through_year)

	for league_name in args.leagues:
		print(f"Searching league: {league_name}", flush=True)
		lg = client.find_rugby_league(league_name)
		if not lg:
			print(f"Not found: {league_name}. If you know the TheSportsDB idLeague, pass --league-ids <id>.", flush=True)
			continue
		league_id = int(lg["idLeague"])
		upsert_league(conn, lg)
		print(f"Found league {league_name} -> id {league_id}", flush=True)
		fetch_and_store_league(conn, client, league_id, league_label=league_name, max_seasons=args.max_seasons, through_year=args.through_year)

	print("Backfill complete.", flush=True)


if __name__ == "__main__":
	main()
