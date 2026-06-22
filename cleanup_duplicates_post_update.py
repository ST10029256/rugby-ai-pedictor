#!/usr/bin/env python3
"""Post-update database integrity cleanup.

Run after enhanced_auto_update.py. This makes the SQLite database internally
consistent so the app (history, standings labels, Firestore sync) is always
correct:

  1. Ensure every configured league has a row in the `league` table.
  2. Remove duplicate events (same league, date, and teams).
  3. Remove orphan events whose league_id is not a configured league (junk rows).
  4. Remove orphan league rows that are not configured and hold no events.

The script is idempotent and exits 0 on success (cleanup is the goal, not an
error). It exits non-zero only on an actual failure.
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.db import ensure_configured_leagues

# Canonical configured leagues. Mirrors rugby-ai-predictor/prediction/config.py
# (LEAGUE_MAPPINGS). Imported from config when its deps are available, otherwise
# this hardcoded copy keeps the cleanup usable in lightweight environments.
_FALLBACK_LEAGUE_NAMES = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
    5480: "Nations Championship",
}


def _configured_league_names() -> dict:
    try:
        from prediction.config import LEAGUE_MAPPINGS  # type: ignore

        if LEAGUE_MAPPINGS:
            return dict(LEAGUE_MAPPINGS)
    except Exception:
        pass
    return dict(_FALLBACK_LEAGUE_NAMES)


def cleanup_database(db_path: str = "data.sqlite") -> int:
    league_names = _configured_league_names()
    configured_ids = set(league_names.keys())

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Running post-update integrity cleanup on {db_path} ...")

    # 1. Ensure every configured league row exists (fixes orphaned matches that
    #    show up with a NULL league name in history).
    ensured = ensure_configured_leagues(conn, league_names)
    print(f"Ensured {ensured} configured league rows exist")

    # 2. Remove duplicate events (same league, date, teams) - keep the lowest id.
    cursor.execute(
        """
        SELECT league_id, DATE(date_event), home_team_id, away_team_id,
               COUNT(*) AS count, GROUP_CONCAT(id) AS ids
        FROM event
        GROUP BY league_id, DATE(date_event), home_team_id, away_team_id
        HAVING COUNT(*) > 1
        """
    )
    duplicates = cursor.fetchall()
    dup_deleted = 0
    for dup in duplicates:
        ids = sorted(int(x) for x in str(dup[5]).split(","))
        for del_id in ids[1:]:
            cursor.execute("DELETE FROM event WHERE id = ?", (del_id,))
            dup_deleted += 1
    if dup_deleted:
        print(f"Removed {dup_deleted} duplicate events (from {len(duplicates)} groups)")
    else:
        print("No duplicate events found")

    # 3. Remove junk events that belong to a league we do not configure
    #    (e.g. stray test rows). Uses a placeholder list to stay parameterized.
    placeholders = ",".join("?" for _ in configured_ids)
    cursor.execute(
        f"SELECT COUNT(*) FROM event WHERE league_id NOT IN ({placeholders})",
        tuple(configured_ids),
    )
    junk_events = int((cursor.fetchone() or [0])[0] or 0)
    if junk_events:
        cursor.execute(
            f"DELETE FROM event WHERE league_id NOT IN ({placeholders})",
            tuple(configured_ids),
        )
        print(f"Removed {junk_events} events from non-configured leagues")
    else:
        print("No non-configured-league events found")

    # 4. Remove orphan league rows that are not configured and hold no events.
    cursor.execute(
        f"""
        DELETE FROM league
        WHERE id NOT IN ({placeholders})
          AND id NOT IN (SELECT DISTINCT league_id FROM event)
        """,
        tuple(configured_ids),
    )
    orphan_leagues = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    if orphan_leagues:
        print(f"Removed {orphan_leagues} orphan league rows")
    else:
        print("No orphan league rows found")

    conn.commit()

    # Final integrity report.
    cursor.execute("PRAGMA quick_check")
    check = cursor.fetchone()
    league_count = cursor.execute("SELECT COUNT(*) FROM league").fetchone()[0]
    cursor.execute(
        f"SELECT COUNT(DISTINCT league_id) FROM event WHERE league_id IN ({placeholders})",
        tuple(configured_ids),
    )
    leagues_with_events = int((cursor.fetchone() or [0])[0] or 0)
    print(
        f"Cleanup complete. quick_check={check[0] if check else 'n/a'}, "
        f"league_rows={league_count}, configured_leagues_with_events={leagues_with_events}"
    )

    conn.close()
    return 0


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "data.sqlite"
    sys.exit(cleanup_database(db))
