from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, Optional


def to_int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    # Leagues
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS league (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            sport TEXT,
            alternate_name TEXT,
            country TEXT
        );
        """
    )

    # Seasons
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS season (
            league_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            PRIMARY KEY (league_id, season),
            FOREIGN KEY (league_id) REFERENCES league(id) ON DELETE CASCADE
        );
        """
    )

    # Teams
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS team (
            id INTEGER PRIMARY KEY,
            league_id INTEGER,
            name TEXT NOT NULL,
            short_name TEXT,
            alternate_name TEXT,
            stadium TEXT,
            formed_year INTEGER,
            country TEXT,
            FOREIGN KEY (league_id) REFERENCES league(id) ON DELETE SET NULL
        );
        """
    )

    # Events (matches)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS event (
            id INTEGER PRIMARY KEY,
            league_id INTEGER NOT NULL,
            season TEXT,
            date_event TEXT,
            timestamp TEXT,
            round INTEGER,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            venue TEXT,
            status TEXT,
            FOREIGN KEY (league_id) REFERENCES league(id) ON DELETE CASCADE,
            FOREIGN KEY (home_team_id) REFERENCES team(id) ON DELETE SET NULL,
            FOREIGN KEY (away_team_id) REFERENCES team(id) ON DELETE SET NULL
        );
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_event_league_season ON event(league_id, season);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_event_date ON event(date_event);")

    conn.commit()


def upsert_league(conn: sqlite3.Connection, league: Dict[str, Any]) -> None:
    id_raw = league.get("idLeague")
    if id_raw is None:
        raise ValueError("league.idLeague is required")
    league_id = int(id_raw)
    conn.execute(
        """
        INSERT INTO league (id, name, sport, alternate_name, country)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            sport=excluded.sport,
            alternate_name=excluded.alternate_name,
            country=excluded.country;
        """,
        (
            league_id,
            league.get("strLeague"),
            league.get("strSport"),
            league.get("strLeagueAlternate"),
            league.get("strCountry"),
        ),
    )


def upsert_season(conn: sqlite3.Connection, league_id: int, season: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO season (league_id, season)
        VALUES (?, ?);
        """,
        (league_id, season),
    )


def upsert_team(conn: sqlite3.Connection, team: Dict[str, Any], league_id: Optional[int] = None) -> None:
    id_raw = team.get("idTeam")
    if id_raw is None:
        raise ValueError("team.idTeam is required")
    team_id = int(id_raw)
    league_id_value = league_id if league_id is not None else to_int_or_none(team.get("idLeague"))
    formed_year_val = to_int_or_none(team.get("intFormedYear"))
    conn.execute(
        """
        INSERT INTO team (id, league_id, name, short_name, alternate_name, stadium, formed_year, country)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            league_id=excluded.league_id,
            name=excluded.name,
            short_name=excluded.short_name,
            alternate_name=excluded.alternate_name,
            stadium=excluded.stadium,
            formed_year=excluded.formed_year,
            country=excluded.country;
        """,
        (
            team_id,
            league_id_value,
            team.get("strTeam") or team.get("strTeamBadge") or "Unknown",
            team.get("strTeamShort"),
            team.get("strAlternate"),
            team.get("strStadium"),
            formed_year_val,
            team.get("strCountry"),
        ),
    )


def team_exists(conn: sqlite3.Connection, team_id: int) -> bool:
    cur = conn.execute("SELECT 1 FROM team WHERE id = ? LIMIT 1;", (team_id,))
    return cur.fetchone() is not None


def upsert_event(conn: sqlite3.Connection, event: Dict[str, Any], override_league_id: Optional[int] = None) -> None:
    id_event_raw = event.get("idEvent")
    if id_event_raw is None:
        raise ValueError("event.idEvent is required")
    id_event_val = int(id_event_raw)
    league_id_val = override_league_id if override_league_id is not None else to_int_or_none(event.get("idLeague"))
    # Normalize date_event: prefer explicit, else derive from timestamp
    date_event_val = event.get("dateEvent") or event.get("dateEventLocal")
    if (not date_event_val) and event.get("strTimestamp"):
        ts = str(event.get("strTimestamp"))
        if len(ts) >= 10:
            date_event_val = ts[:10]
    round_val = to_int_or_none(event.get("intRound"))
    home_team_val = to_int_or_none(event.get("idHomeTeam"))
    away_team_val = to_int_or_none(event.get("idAwayTeam"))
    home_score_val = to_int_or_none(event.get("intHomeScore"))
    away_score_val = to_int_or_none(event.get("intAwayScore"))
    conn.execute(
        """
        INSERT INTO event (
            id, league_id, season, date_event, timestamp, round, home_team_id, away_team_id, home_score, away_score, venue, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            league_id=excluded.league_id,
            season=excluded.season,
            date_event=excluded.date_event,
            timestamp=excluded.timestamp,
            round=excluded.round,
            home_team_id=excluded.home_team_id,
            away_team_id=excluded.away_team_id,
            home_score=excluded.home_score,
            away_score=excluded.away_score,
            venue=excluded.venue,
            status=excluded.status;
        """,
        (
            id_event_val,
            league_id_val,
            event.get("strSeason"),
            date_event_val,
            event.get("strTimestamp"),
            round_val,
            home_team_val,
            away_team_val,
            home_score_val,
            away_score_val,
            event.get("strVenue"),
            event.get("strStatus") or event.get("strPostponed"),
        ),
    )


def bulk_upsert_events(conn: sqlite3.Connection, events: Iterable[Dict[str, Any]], override_league_id: Optional[int] = None) -> None:
    for ev in events:
        upsert_event(conn, ev, override_league_id=override_league_id)
    conn.commit()
