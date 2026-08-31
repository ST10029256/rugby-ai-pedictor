#!/usr/bin/env python3
"""Repair team identity across the whole match history.

Ingestion used to resolve team names globally, ignoring the competition, so a
single `team.id` ended up standing for several different sides (Currie Cup
"Bulls" was filed under the URC Bulls) while other sides were split across
several ids (Harlequins / "Harlequins Football Club"). Both wreck the Elo,
embedding and form features, which are all keyed on `team.id`.

This rewrites `event.home_team_id` / `event.away_team_id` so every id means one
real team, removes the duplicate fixtures the rename variants created, and
retires the ids that were merged away.

    python scripts/fix_team_identity.py --dry-run
    python scripts/fix_team_identity.py --apply

The default is a dry run. `--apply` writes a timestamped backup next to the
database first.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.team_identity import (  # noqa: E402
    CANONICAL_TEAM_LEAGUES,
    CANONICAL_TEAM_NAMES,
    LEAGUE_SCOPED_TEAM_ID_REMAPS,
    TEAM_ID_MERGES,
    canonical_team_id,
    leagues_may_share_team,
)

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _team_names(conn: sqlite3.Connection) -> Dict[int, str]:
    return {int(r[0]): str(r[1]) for r in conn.execute("SELECT id, name FROM team")}


def _league_names(conn: sqlite3.Connection) -> Dict[int, str]:
    return {int(r[0]): str(r[1]) for r in conn.execute("SELECT id, name FROM league")}


def _event_counts(conn: sqlite3.Connection, team_id: int) -> Counter:
    counts: Counter = Counter()
    for lid, n in conn.execute(
        "SELECT league_id, COUNT(*) FROM event "
        "WHERE home_team_id = ? OR away_team_id = ? GROUP BY league_id",
        (team_id, team_id),
    ):
        counts[int(lid)] = int(n)
    return counts


def remap_events(conn: sqlite3.Connection) -> List[str]:
    """Point every fixture at the surviving id for its competition."""
    log: List[str] = []
    names = _team_names(conn)
    leagues = _league_names(conn)
    moved: Counter = Counter()

    rows = conn.execute(
        "SELECT id, league_id, home_team_id, away_team_id FROM event"
    ).fetchall()
    for event_id, league_id, home_id, away_id in rows:
        new_home = canonical_team_id(home_id, league_id)
        new_away = canonical_team_id(away_id, league_id)
        if new_home == home_id and new_away == away_id:
            continue
        conn.execute(
            "UPDATE event SET home_team_id = ?, away_team_id = ? WHERE id = ?",
            (new_home, new_away, event_id),
        )
        if new_home != home_id:
            moved[(int(league_id), int(home_id), int(new_home))] += 1
        if new_away != away_id:
            moved[(int(league_id), int(away_id), int(new_away))] += 1

    for (league_id, old_id, new_id), n in sorted(
        moved.items(), key=lambda kv: -kv[1]
    ):
        log.append(
            f"  {n:>5} fixtures  {leagues.get(league_id, league_id)}: "
            f"{names.get(old_id, old_id)!r} ({old_id}) -> "
            f"{CANONICAL_TEAM_NAMES.get(new_id) or names.get(new_id, new_id)!r} ({new_id})"
        )
    return log


def apply_canonical_metadata(conn: sqlite3.Connection) -> List[str]:
    """Give surviving rows the name and competition they should have had."""
    log: List[str] = []
    names = _team_names(conn)
    for team_id, name in CANONICAL_TEAM_NAMES.items():
        current = names.get(team_id)
        if current is None:
            log.append(f"  missing team row {team_id}, cannot rename to {name!r}")
            continue
        if current != name:
            conn.execute("UPDATE team SET name = ? WHERE id = ?", (name, team_id))
            log.append(f"  renamed {current!r} -> {name!r} (id {team_id})")
    for team_id, league_id in CANONICAL_TEAM_LEAGUES.items():
        conn.execute(
            "UPDATE team SET league_id = ? WHERE id = ? AND IFNULL(league_id, -1) != ?",
            (league_id, team_id, league_id),
        )
    return log


def dedupe_events(conn: sqlite3.Connection) -> List[str]:
    """Drop fixtures that became duplicates once the ids were unified."""
    log: List[str] = []
    names = _team_names(conn)
    leagues = _league_names(conn)

    groups = conn.execute(
        """
        SELECT league_id, DATE(date_event) AS d, home_team_id, away_team_id,
               COUNT(*) AS n, GROUP_CONCAT(id) AS ids
        FROM event
        GROUP BY league_id, DATE(date_event), home_team_id, away_team_id
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    removed = 0
    for league_id, day, home_id, away_id, _n, ids_csv in groups:
        ids = sorted(int(x) for x in str(ids_csv).split(","))
        best_id, best_score = ids[0], -1
        for eid in ids:
            hl, hs, aws = conn.execute(
                "SELECT highlightly_match_id, home_score, away_score "
                "FROM event WHERE id = ?",
                (eid,),
            ).fetchone()
            score = 0
            if hl is not None:
                score += 2
                if int(hl) == int(eid):
                    score += 2
            if hs is not None and aws is not None:
                score += 1
            if score > best_score:
                best_id, best_score = eid, score

        for eid in ids:
            if eid == best_id:
                continue
            # Snapshots are unique per (match, model, type), so a snapshot that
            # would collide with one already held by the surviving fixture is
            # dropped rather than moved.
            conn.execute(
                "UPDATE OR IGNORE prediction_snapshot SET match_id = ? WHERE match_id = ?",
                (best_id, eid),
            )
            conn.execute("DELETE FROM prediction_snapshot WHERE match_id = ?", (eid,))
            conn.execute("DELETE FROM event WHERE id = ?", (eid,))
            removed += 1
        log.append(
            f"  {leagues.get(league_id, league_id)} {day} "
            f"{names.get(home_id, home_id)!r} v {names.get(away_id, away_id)!r}: "
            f"kept {best_id}, removed {[i for i in ids if i != best_id]}"
        )

    if removed:
        log.append(f"  -> {removed} duplicate fixtures removed")
    return log


def retire_merged_rows(conn: sqlite3.Connection) -> List[str]:
    """Delete ids that were merged away, once nothing points at them."""
    log: List[str] = []
    names = _team_names(conn)
    retired = 0
    for old_id in sorted(TEAM_ID_MERGES):
        still_used = conn.execute(
            "SELECT COUNT(*) FROM event WHERE home_team_id = ? OR away_team_id = ?",
            (old_id, old_id),
        ).fetchone()[0]
        if still_used:
            log.append(f"  kept {names.get(old_id, old_id)!r} ({old_id}): {still_used} fixtures remain")
            continue
        if conn.execute("SELECT 1 FROM team WHERE id = ?", (old_id,)).fetchone():
            conn.execute("DELETE FROM team WHERE id = ?", (old_id,))
            retired += 1
    log.append(f"  -> {retired} redundant team rows deleted")
    return log


def refresh_snapshot_labels(conn: sqlite3.Connection) -> List[str]:
    """Keep stored prediction labels in step with the corrected team names."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prediction_snapshot)")}
    if not {"match_id", "home_team", "away_team"} <= cols:
        return ["  prediction_snapshot has no team labels to refresh"]
    updated = conn.execute(
        """
        UPDATE prediction_snapshot
           SET home_team = (
                   SELECT t.name FROM event e JOIN team t ON t.id = e.home_team_id
                    WHERE e.id = prediction_snapshot.match_id),
               away_team = (
                   SELECT t.name FROM event e JOIN team t ON t.id = e.away_team_id
                    WHERE e.id = prediction_snapshot.match_id)
         WHERE EXISTS (SELECT 1 FROM event e WHERE e.id = prediction_snapshot.match_id)
        """
    ).rowcount
    return [f"  -> {max(updated, 0)} prediction snapshots relabelled"]


def backfill_team_leagues(conn: sqlite3.Connection) -> List[str]:
    """Fill in the missing home competition using each side's latest fixture."""
    filled = conn.execute(
        """
        UPDATE team SET league_id = (
            SELECT e.league_id FROM event e
             WHERE e.home_team_id = team.id OR e.away_team_id = team.id
             ORDER BY e.date_event DESC LIMIT 1)
        WHERE league_id IS NULL
          AND EXISTS (SELECT 1 FROM event e
                       WHERE e.home_team_id = team.id OR e.away_team_id = team.id)
        """
    ).rowcount
    return [f"  -> {max(filled, 0)} team rows given a home competition"]


def audit(conn: sqlite3.Connection) -> List[str]:
    """Report any id still shared by competitions that cannot share a side."""
    log: List[str] = []
    names = _team_names(conn)
    leagues = _league_names(conn)
    per_team: Dict[int, Counter] = defaultdict(Counter)
    for tid, lid, n in conn.execute(
        """
        SELECT tid, league_id, COUNT(*) FROM (
            SELECT home_team_id AS tid, league_id FROM event
            UNION ALL
            SELECT away_team_id AS tid, league_id FROM event
        ) GROUP BY tid, league_id
        """
    ):
        if tid is not None:
            per_team[int(tid)][int(lid)] = int(n)

    for tid, counts in sorted(per_team.items()):
        lids = list(counts)
        bad = [
            (a, b)
            for i, a in enumerate(lids)
            for b in lids[i + 1:]
            if not leagues_may_share_team(a, b)
        ]
        if bad:
            where = ", ".join(f"{leagues.get(l, l)}={counts[l]}" for l in lids)
            log.append(f"  STILL SHARED  {names.get(tid, tid)!r} ({tid}): {where}")
    if not log:
        log.append("  clean: no team id spans competitions that cannot share a side")
    return log


def find_residual_splits(conn: sqlite3.Connection) -> List[str]:
    """Flag sides that still look split across two ids.

    Two fixtures on the same day in the same competition with the same score
    and one team in common are the same match, so the differing team is one
    side recorded under two ids.
    """
    names = _team_names(conn)
    leagues = _league_names(conn)
    suspects: Counter = Counter()

    rows = conn.execute(
        """
        SELECT league_id, DATE(date_event), home_team_id, away_team_id,
               home_score, away_score
          FROM event
         WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """
    ).fetchall()

    by_day: Dict[Tuple, List[Tuple[int, int]]] = defaultdict(list)
    for league_id, day, home_id, away_id, hs, aws in rows:
        by_day[(league_id, day, hs, aws)].append((home_id, away_id))

    for fixtures in by_day.values():
        for i, (h1, a1) in enumerate(fixtures):
            for h2, a2 in fixtures[i + 1:]:
                if h1 == h2 and a1 != a2:
                    suspects[tuple(sorted((a1, a2)))] += 1
                elif a1 == a2 and h1 != h2:
                    suspects[tuple(sorted((h1, h2)))] += 1

    log: List[str] = []
    for (left, right), n in suspects.most_common():
        if n < 2:  # a single coincidence is usually just two identical scorelines
            continue
        where = conn.execute(
            "SELECT DISTINCT league_id FROM event "
            "WHERE home_team_id IN (?,?) OR away_team_id IN (?,?)",
            (left, right, left, right),
        ).fetchall()
        comps = ", ".join(leagues.get(int(r[0]), str(r[0])) for r in where)
        log.append(
            f"  {n:>3} matched scorelines: {names.get(left, left)!r} ({left}) "
            f"vs {names.get(right, right)!r} ({right})  [{comps}]"
        )
    if not log:
        log.append("  none: no side appears to be recorded under two ids")
    return log


def summarise_currie_cup(conn: sqlite3.Connection) -> List[str]:
    log: List[str] = []
    for tid, name, n in conn.execute(
        """
        SELECT t.id, t.name, COUNT(*) AS n
          FROM event e JOIN team t
            ON t.id = e.home_team_id OR t.id = e.away_team_id
         WHERE e.league_id = 5069
         GROUP BY t.id, t.name
         ORDER BY n DESC
        """
    ):
        other = sum(
            c for l, c in _event_counts(conn, int(tid)).items() if l != 5069
        )
        tail = f"   (+{other} elsewhere)" if other else ""
        log.append(f"  {int(n):>4}  {name!r} ({tid}){tail}")
    return log


def run(db_path: Path, apply_changes: bool) -> int:
    if not db_path.exists():
        print(f"database not found: {db_path}")
        return 1

    if apply_changes:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_name(f"{db_path.stem}.backup_{stamp}{db_path.suffix}")
        shutil.copy2(db_path, backup)
        print(f"Backup written to {backup}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    print(f"\n=== {db_path} ===")
    print(f"teams={conn.execute('SELECT COUNT(*) FROM team').fetchone()[0]}  "
          f"events={conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]}")

    print(f"\nRules: {len(LEAGUE_SCOPED_TEAM_ID_REMAPS)} competition-scoped remaps, "
          f"{len(TEAM_ID_MERGES)} merges")

    sections = [
        ("Reassigned fixtures", remap_events),
        ("Corrected team records", apply_canonical_metadata),
        ("Duplicate fixtures", dedupe_events),
        ("Retired team rows", retire_merged_rows),
        ("Prediction snapshots", refresh_snapshot_labels),
        ("Home competitions", backfill_team_leagues),
    ]
    for title, fn in sections:
        print(f"\n--- {title} ---")
        lines = fn(conn)
        print("\n".join(lines) if lines else "  (nothing to do)")

    print("\n--- Currie Cup after repair ---")
    print("\n".join(summarise_currie_cup(conn)))

    print("\n--- Cross-competition audit ---")
    print("\n".join(audit(conn)))

    print("\n--- Sides possibly still split across two ids ---")
    print("\n".join(find_residual_splits(conn)))

    print(f"\nteams={conn.execute('SELECT COUNT(*) FROM team').fetchone()[0]}  "
          f"events={conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]}")

    if apply_changes:
        conn.commit()
        conn.execute("VACUUM")
        print("\nChanges committed.")
    else:
        conn.rollback()
        print("\nDry run: nothing written. Re-run with --apply to commit.")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data.sqlite"))
    parser.add_argument("--apply", action="store_true", help="commit the repair")
    parser.add_argument("--dry-run", action="store_true", help="default; preview only")
    args = parser.parse_args()
    return run(Path(args.db), apply_changes=args.apply and not args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
