#!/usr/bin/env python3
"""
Check whether the same teams appear across mapped rugby leagues.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS


def default_db_path() -> Path:
    root = Path(__file__).parent.parent
    p_main = root / "data.sqlite"
    p_fn = root / "rugby-ai-predictor" / "data.sqlite"
    return p_main if p_main.exists() else p_fn


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def canonical_team_name(name: str) -> str:
    n = str(name).strip()
    # Remove common source suffixes/qualifiers
    n = re.sub(r"\bSuper Rugby\b", "", n, flags=re.IGNORECASE).strip()
    n = re.sub(r"\bRugby\b", "", n, flags=re.IGNORECASE).strip()
    n = re.sub(r"\s+", " ", n).strip()
    nl = n.lower()
    # Alias normalization for common duplicates in this dataset
    alias_map = {
        "blue bulls": "Bulls",
        "bulls": "Bulls",
        "lions": "Lions",
        "the sharks": "Sharks",
        "sharks": "Sharks",
        "new nation pumas": "Pumas",
        "mru. new nation pumas": "Pumas",
    }
    if nl in alias_map:
        return alias_map[nl]
    return n


def canonical_team_token(name: str) -> str:
    c = canonical_team_name(name).strip().lower()
    c = re.sub(r"[^a-z0-9]+", "_", c)
    c = re.sub(r"_+", "_", c).strip("_")
    return c or "unknown_team"


def fetch_league_teams(
    conn: sqlite3.Connection,
    league_ids: List[int],
    since_date: Optional[str] = None,
) -> Tuple[Dict[int, Set[int]], Dict[Tuple[int, int], Tuple[str, str]]]:
    out: Dict[int, Set[int]] = {}
    team_meta: Dict[Tuple[int, int], Tuple[str, str]] = {}
    q = """
    SELECT league_id, home_team_id, away_team_id, date_event
    FROM event
    WHERE league_id = ?
      AND home_team_id IS NOT NULL
      AND away_team_id IS NOT NULL
      AND date_event IS NOT NULL
    """
    since_dt = _parse_date(since_date) if since_date else None
    for lid in league_ids:
        teams: Set[int] = set()
        for row in conn.execute(q, (int(lid),)):
            _, h, a, d = row
            dt = _parse_date(d)
            if since_dt and dt and dt < since_dt:
                continue
            for tid in (int(h), int(a)):
                teams.add(tid)
                k = (int(lid), tid)
                if dt:
                    if k not in team_meta:
                        ds = dt.strftime("%Y-%m-%d")
                        team_meta[k] = (ds, ds)
                    else:
                        lo, hi = team_meta[k]
                        ds = dt.strftime("%Y-%m-%d")
                        team_meta[k] = (min(lo, ds), max(hi, ds))
        out[int(lid)] = teams
    return out, team_meta


def fetch_team_names(conn: sqlite3.Connection, team_ids: Set[int]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    if not team_ids:
        return out

    # Try common schema variants.
    candidate_queries = [
        "SELECT id, name FROM team",
        "SELECT id, team_name FROM team",
        "SELECT team_id, name FROM team",
        "SELECT idTeam, strTeam FROM teams",
        "SELECT team_id, team_name FROM teams",
        "SELECT id, name FROM teams",
    ]
    for q in candidate_queries:
        try:
            rows = conn.execute(q).fetchall()
        except Exception:
            continue
        for r in rows:
            if len(r) < 2:
                continue
            try:
                tid = int(r[0])
            except Exception:
                continue
            if tid in team_ids and r[1] is not None:
                out[tid] = str(r[1])
        if out:
            break

    # Last-resort fallback: infer names from event table if present.
    if not out:
        fallback_queries = [
            "SELECT home_team_id, home_team_name FROM event WHERE home_team_name IS NOT NULL",
            "SELECT away_team_id, away_team_name FROM event WHERE away_team_name IS NOT NULL",
        ]
        for q in fallback_queries:
            try:
                rows = conn.execute(q).fetchall()
            except Exception:
                continue
            for r in rows:
                if len(r) < 2:
                    continue
                try:
                    tid = int(r[0])
                except Exception:
                    continue
                if tid in team_ids and r[1] is not None and tid not in out:
                    out[tid] = str(r[1])
    return out


def pairwise_overlap(team_sets: Dict[int, Set[int]]) -> List[Tuple[int, int, int, float, float]]:
    lids = sorted(team_sets.keys())
    rows: List[Tuple[int, int, int, float, float]] = []
    for i, a in enumerate(lids):
        for b in lids[i + 1 :]:
            sa = team_sets[a]
            sb = team_sets[b]
            inter = sa.intersection(sb)
            inter_n = len(inter)
            pct_a = (100.0 * inter_n / len(sa)) if sa else 0.0
            pct_b = (100.0 * inter_n / len(sb)) if sb else 0.0
            rows.append((a, b, inter_n, pct_a, pct_b))
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Check team overlap across leagues.")
    parser.add_argument("--db-path", default=None, help="Path to sqlite DB (optional).")
    parser.add_argument(
        "--only-positive",
        action="store_true",
        help="Only print league pairs where overlap > 0.",
    )
    parser.add_argument(
        "--show-shared-names",
        action="store_true",
        help="Print team names for each overlapping league pair.",
    )
    parser.add_argument(
        "--since-date",
        default=None,
        help="Optional date filter YYYY-MM-DD (only matches on/after this date).",
    )
    parser.add_argument(
        "--canonicalize-names",
        action="store_true",
        help="Normalize aliases (e.g., Blue Bulls/Bulls, Lions variants).",
    )
    parser.add_argument(
        "--merge-canonical",
        action="store_true",
        help="Merge duplicate provider IDs by canonical team name in overlap outputs.",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    league_ids = sorted(int(x) for x in LEAGUE_MAPPINGS.keys())
    conn = sqlite3.connect(str(db_path))
    team_sets, team_meta = fetch_league_teams(conn, league_ids, since_date=args.since_date)
    all_ids: Set[int] = set()
    for s in team_sets.values():
        all_ids.update(s)
    team_names = fetch_team_names(conn, all_ids)
    conn.close()

    print("=== Team Counts By League ===")
    if args.since_date:
        print(f"(filtered since {args.since_date})")
    for lid in league_ids:
        name = LEAGUE_MAPPINGS.get(lid, f"League {lid}")
        print(f"{lid} | {name} | teams={len(team_sets.get(lid, set()))}")

    if args.merge_canonical:
        league_tokens: Dict[int, Set[str]] = {}
        token_to_ids: Dict[str, Set[int]] = defaultdict(set)
        for lid, s in team_sets.items():
            toks: Set[str] = set()
            for tid in s:
                raw = team_names.get(tid, "UNKNOWN_TEAM")
                tok = canonical_team_token(raw if args.canonicalize_names else str(raw))
                toks.add(tok)
                token_to_ids[tok].add(int(tid))
            league_tokens[lid] = toks
        token_to_leagues: Dict[str, List[int]] = defaultdict(list)
        for lid, toks in league_tokens.items():
            for tok in toks:
                token_to_leagues[tok].append(lid)
        multi_tokens = {tok: sorted(lids) for tok, lids in token_to_leagues.items() if len(lids) > 1}
    else:
        team_to_leagues: Dict[int, List[int]] = defaultdict(list)
        for lid, s in team_sets.items():
            for tid in s:
                team_to_leagues[tid].append(lid)
        multi = {tid: sorted(lids) for tid, lids in team_to_leagues.items() if len(lids) > 1}

    print("\n=== Teams Appearing In Multiple Leagues ===")
    if args.merge_canonical:
        print(f"count={len(multi_tokens)} (merged canonical)")
        for tok, lids in sorted(multi_tokens.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True):
            league_names = ", ".join(f"{x}:{LEAGUE_MAPPINGS.get(x, x)}" for x in lids)
            ids = sorted(token_to_ids.get(tok, set()))
            display = tok.replace("_", " ").title()
            print(f"team={display} | canonical={tok} | source_ids={ids} | leagues={league_names}")
    else:
        print(f"count={len(multi)}")
        if multi:
            for tid, lids in sorted(multi.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True):
                league_names = ", ".join(f"{x}:{LEAGUE_MAPPINGS.get(x, x)}" for x in lids)
                tname_raw = team_names.get(tid, "UNKNOWN_TEAM")
                tname = canonical_team_name(tname_raw) if args.canonicalize_names else tname_raw
                ranges = []
                for lid in lids:
                    lo_hi = team_meta.get((lid, tid))
                    if lo_hi:
                        ranges.append(f"{lid}:{lo_hi[0]}..{lo_hi[1]}")
                rtxt = f" | active_ranges={', '.join(ranges)}" if ranges else ""
                print(f"team_id={tid} | team_name={tname} | leagues={league_names}{rtxt}")

    print("\n=== Pairwise League Overlap ===")
    print("league_a | league_b | shared_teams | %of_a | %of_b")
    if args.merge_canonical:
        for i, a in enumerate(league_ids):
            for b in league_ids[i + 1 :]:
                sa = league_tokens[a]
                sb = league_tokens[b]
                inter = sorted(sa.intersection(sb))
                inter_n = len(inter)
                if args.only_positive and inter_n == 0:
                    continue
                pct_a = (100.0 * inter_n / len(sa)) if sa else 0.0
                pct_b = (100.0 * inter_n / len(sb)) if sb else 0.0
                print(f"{a:7d} | {b:7d} | {inter_n:12d} | {pct_a:5.1f}% | {pct_b:5.1f}%")
                if args.show_shared_names and inter_n > 0:
                    pretty = [x.replace("_", " ").title() for x in inter]
                    print("  shared:", ", ".join(pretty))
    else:
        for a, b, inter_n, pct_a, pct_b in pairwise_overlap(team_sets):
            if args.only_positive and inter_n == 0:
                continue
            print(f"{a:7d} | {b:7d} | {inter_n:12d} | {pct_a:5.1f}% | {pct_b:5.1f}%")
            if args.show_shared_names and inter_n > 0:
                shared_ids = sorted(team_sets[a].intersection(team_sets[b]))
                shared_names = []
                for tid in shared_ids:
                    raw = team_names.get(tid, f"team_{tid}")
                    nm = canonical_team_name(raw) if args.canonicalize_names else raw
                    shared_names.append(f"{nm} (id:{tid})")
                print("  shared:", ", ".join(shared_names))


if __name__ == "__main__":
    main()

