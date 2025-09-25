from __future__ import annotations

import argparse
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import hashlib

import pandas as pd

from prediction.db import connect, init_db, upsert_league, upsert_team, bulk_upsert_events
from prediction.sportsdb_client import APISportsRugbyClient


def _to_int(val: Any) -> Optional[int]:
	try:
		return int(val)  # type: ignore[arg-type]
	except Exception:
		return None


def _stable_id(seed: str, modulo: int = 10_000_000) -> int:
	"""Deterministic positive compact integer id from an arbitrary seed string."""
	digest = hashlib.sha1(seed.encode("utf-8")).digest()
	value = int.from_bytes(digest[:8], byteorder="big", signed=False)
	return (value % (modulo - 1)) + 1


def _has_time_info(game: Dict[str, Any]) -> bool:
	fixture = game.get("fixture", {})
	return bool(fixture.get("date") or fixture.get("timestamp"))


def map_game_to_event(game: Dict[str, Any], league_id: int) -> Dict[str, Any]:
	fixture = game.get("fixture", {})
	teams = game.get("teams", {})
	scores = game.get("scores", {})
	league = game.get("league", {})

	date_iso = fixture.get("date")
	# Fallback: some games may lack ISO date but have epoch timestamp
	if not date_iso:
		ts_epoch = fixture.get("timestamp")
		if ts_epoch is not None:
			try:
				# Normalize to UTC ISO8601
				date_iso = datetime.fromtimestamp(int(ts_epoch), tz=timezone.utc).isoformat()
			except Exception:
				date_iso = None

	venue = (fixture.get("venue") or {}).get("name")
	status = (fixture.get("status") or {}).get("long")

	home = teams.get("home") or {}
	away = teams.get("away") or {}

	sh = scores.get("home")
	sa = scores.get("away")

	# Create deterministic synthetic IDs for teams and events if not provided
	_id_ev_raw = fixture.get("id")
	id_event = _to_int(_id_ev_raw)
	if id_event is None:
		seed_ev = f"ev:{league_id}:{date_iso}:{(home.get('name') or '').strip()}:{(away.get('name') or '').strip()}:{venue or ''}"
		id_event = _stable_id(seed_ev)

	_id_home_raw = home.get("id")
	id_home = _to_int(_id_home_raw)
	if id_home is None:
		seed_home = f"team:home:{league_id}:{(home.get('name') or '').strip()}"
		id_home = _stable_id(seed_home)

	_id_away_raw = away.get("id")
	id_away = _to_int(_id_away_raw)
	if id_away is None:
		seed_away = f"team:away:{league_id}:{(away.get('name') or '').strip()}"
		id_away = _stable_id(seed_away)

	return {
		"idEvent": id_event,
		"idLeague": league_id,
		"strSeason": str(league.get("season") or ""),
		"dateEvent": pd.to_datetime(date_iso).date().isoformat() if date_iso else None,
        # Ensure timestamp is ISO string so `fix_dates` can derive date when needed
        "strTimestamp": date_iso,
		"intRound": None,
		"idHomeTeam": id_home,
		"idAwayTeam": id_away,
		"intHomeScore": int(sh) if sh is not None else None,
		"intAwayScore": int(sa) if sa is not None else None,
		"strVenue": venue,
		"strStatus": status,
	}


def main() -> None:
	parser = argparse.ArgumentParser(description="Import Rugby Championship from API-Sports into local DB")
	parser.add_argument("--db", default="data.sqlite", help="SQLite DB path")
	parser.add_argument("--api-key", required=True, help="API-Sports key for rugby endpoints")
	parser.add_argument("--league-id", type=int, default=85, help="API-Sports league id (Rugby Championship=85)")
	parser.add_argument("--seasons", nargs="*", type=int, default=[2012,2013,2014,2015,2016,2017,2018,2020,2021,2022,2023,2024,2025], help="Seasons to import")
	parser.add_argument("--allow-missing-dates", action="store_true", default=False, help="Insert events even if date/timestamp is missing")
	args = parser.parse_args()

	conn = connect(args.db)
	init_db(conn)

	client = APISportsRugbyClient(api_key=args.api_key)

	# Minimal league upsert stub
	upsert_league(conn, {"idLeague": args.league_id, "strLeague": "Rugby Championship", "strSport": "Rugby", "strLeagueAlternate": None, "strCountry": "World"})

	for season in args.seasons:
		games = client.list_games(args.league_id, season)
		if not games:
			continue
		# Ensure teams exist
		seen: List[int] = []
		for g in games:
			teams = g.get("teams", {})
			for side in ("home", "away"):
				info = teams.get(side) or {}
				tid = info.get("id")
				name = info.get("name") or f"Unknown-{side}"
				if tid is None:
					# derive deterministic synthetic id
					tid = _stable_id(f"team:{args.league_id}:{season}:{side}:{name}")
				if tid in seen:
					continue
				seen.append(tid)
				upsert_team(conn, {"idTeam": tid, "idLeague": args.league_id, "strTeam": name, "strTeamShort": None, "strAlternate": None, "strStadium": None, "intFormedYear": None, "strCountry": None}, league_id=args.league_id)
		conn.commit()

		# Upsert events; include missing dates if flag is set
		events = [map_game_to_event(g, args.league_id) for g in games if (_has_time_info(g) or args.allow_missing_dates)]
		bulk_upsert_events(conn, events, override_league_id=args.league_id)

	print("API-Sports import complete.")


if __name__ == "__main__":
	main()


