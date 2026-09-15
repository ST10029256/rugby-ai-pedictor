#!/usr/bin/env python3
"""Post-update database integrity cleanup.

Run after enhanced_auto_update.py. This makes the SQLite database internally
consistent so the app (history, standings labels, Firestore sync) is always
correct:

  1. Ensure every configured league has a row in the `league` table.
  2. Remove duplicate events (same league, date, and teams).
  3. Remove orphan events whose league_id is not a configured league (junk rows).
  4. Remove orphan league rows that are not configured and hold no events.
  5. Remove past fixtures that never received a score (holes, not results).
  6. Remove placeholder dumps (same team listed twice on one day).
  7. Drop prediction snapshots that no longer point at a real event.

Real upcoming fixtures (future date, no score yet) are kept.

The script is idempotent and exits 0 on success (cleanup is the goal, not an
error). It exits non-zero only on an actual failure.
"""

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
    5481: "Investec Champions Cup",
    5482: "EPCR Challenge Cup",
    5483: "Women's Rugby World Cup",
    5484: "Women's Six Nations",
    5485: "WXV 1",
    5486: "WXV 2",
    5487: "WXV 3",
}

SAST = timezone(timedelta(hours=2))


def _today_sast_iso() -> str:
    return datetime.now(SAST).date().isoformat()


def _table_exists(cursor: sqlite3.Cursor, name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _delete_event_ids(cursor: sqlite3.Cursor, event_ids: list[int]) -> int:
    deleted = 0
    for event_id in event_ids:
        cursor.execute("DELETE FROM event WHERE id = ?", (event_id,))
        deleted += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    return deleted


def _remove_past_unscored(cursor: sqlite3.Cursor, today_iso: str) -> int:
    rows = cursor.execute(
        """
        SELECT id FROM event
        WHERE date(date_event) < date(?)
          AND (home_score IS NULL OR away_score IS NULL)
        """,
        (today_iso,),
    ).fetchall()
    ids = [int(r[0]) for r in rows]
    return _delete_event_ids(cursor, ids)


def _remove_placeholder_unscored(cursor: sqlite3.Cursor) -> int:
    """Drop impossible schedules: a team cannot play two games on the same day."""
    rows = cursor.execute(
        """
        SELECT id, league_id, DATE(date_event), home_team_id, away_team_id
        FROM event
        WHERE home_score IS NULL OR away_score IS NULL
        """
    ).fetchall()
    by_league_date = defaultdict(list)
    for event_id, league_id, day, home_id, away_id in rows:
        if not day or home_id is None or away_id is None:
            continue
        by_league_date[(int(league_id), str(day))].append(
            (int(event_id), int(home_id), int(away_id))
        )

    drop: set[int] = set()
    for games in by_league_date.values():
        appearances: dict[int, set[int]] = defaultdict(set)
        for event_id, home_id, away_id in games:
            appearances[home_id].add(event_id)
            appearances[away_id].add(event_id)
        for event_ids in appearances.values():
            if len(event_ids) > 1:
                drop.update(event_ids)
    return _delete_event_ids(cursor, sorted(drop))


def _prune_orphan_snapshots(cursor: sqlite3.Cursor) -> int:
    if not _table_exists(cursor, "prediction_snapshot"):
        return 0
    cursor.execute(
        """
        DELETE FROM prediction_snapshot
        WHERE match_id NOT IN (SELECT id FROM event)
        """
    )
    return int(cursor.rowcount or 0)


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

    # 2. Remove duplicate events.
    #    a) Same Highlightly match id -> keep canonical id == highlightly_match_id when possible.
    #    b) Same league/date/teams -> prefer row with highlightly_match_id, else lowest id.
    dup_deleted = 0

    cursor.execute(
        """
        SELECT highlightly_match_id, COUNT(*) AS count, GROUP_CONCAT(id) AS ids
        FROM event
        WHERE highlightly_match_id IS NOT NULL
        GROUP BY highlightly_match_id
        HAVING COUNT(*) > 1
        """
    )
    for hl_id, _count, ids_csv in cursor.fetchall():
        ids = sorted(int(x) for x in str(ids_csv).split(","))
        keep = int(hl_id) if int(hl_id) in ids else ids[0]
        for del_id in ids:
            if del_id == keep:
                continue
            cursor.execute("DELETE FROM event WHERE id = ?", (del_id,))
            dup_deleted += 1

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
    for dup in duplicates:
        ids = sorted(int(x) for x in str(dup[5]).split(","))
        # Prefer a row whose highlightly_match_id is set (and ideally equals id).
        keep = ids[0]
        best_score = -1
        for eid in ids:
            row = cursor.execute(
                "SELECT highlightly_match_id FROM event WHERE id = ?",
                (eid,),
            ).fetchone()
            hl = row[0] if row else None
            score = 0
            if hl is not None:
                score += 2
                if int(hl) == int(eid):
                    score += 2
            if score > best_score:
                best_score = score
                keep = eid
        for del_id in ids:
            if del_id == keep:
                continue
            cursor.execute("DELETE FROM event WHERE id = ?", (del_id,))
            dup_deleted += 1

    if dup_deleted:
        print(f"Removed {dup_deleted} duplicate events")
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

    # 5. Past dates with no score are holes (cancelled, never ingested, or dummy).
    #    Keep future unscored rows — those are real upcoming fixtures.
    today_iso = _today_sast_iso()
    past_unscored = _remove_past_unscored(cursor, today_iso)
    if past_unscored:
        print(f"Removed {past_unscored} past events with no score")
    else:
        print("No past unscored events found")

    # 6. Placeholder tournament dumps (e.g. World Cup 2027 all dated one day,
    #    with the same nation listed two or three times).
    placeholders_removed = _remove_placeholder_unscored(cursor)
    if placeholders_removed:
        print(f"Removed {placeholders_removed} placeholder / impossible-schedule events")
    else:
        print("No placeholder schedule dumps found")

    # 7. Snapshots must not outlive the fixture they belong to.
    orphan_snaps = _prune_orphan_snapshots(cursor)
    if orphan_snaps:
        print(f"Removed {orphan_snaps} orphan prediction snapshots")
    else:
        print("No orphan prediction snapshots found")

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
