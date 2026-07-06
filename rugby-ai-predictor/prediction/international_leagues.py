"""
International rugby league cluster: shared training + prediction fallback.

Leagues in this cluster share national / representative teams. Nations Championship
(5480) can train on pooled history and borrow deployed models from sibling leagues
when its own checkpoint is not yet available.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

# Core international cluster (TheSportsDB / local league IDs).
RUGBY_CHAMPIONSHIP_ID = 4986
RUGBY_WORLD_CUP_ID = 4574
INTERNATIONAL_FRIENDLIES_ID = 5479
NATIONS_CHAMPIONSHIP_ID = 5480

INTERNATIONAL_RUGBY_CLUSTER: Dict[int, str] = {
    RUGBY_CHAMPIONSHIP_ID: "Rugby Championship",
    RUGBY_WORLD_CUP_ID: "Rugby World Cup",
    INTERNATIONAL_FRIENDLIES_ID: "Rugby Union International Friendlies",
    NATIONS_CHAMPIONSHIP_ID: "Nations Championship",
}

# Preferred fallback order when choosing a deployed model for Nations Championship.
LINKED_MODEL_PRIORITY: Tuple[int, ...] = (
    NATIONS_CHAMPIONSHIP_ID,
    INTERNATIONAL_FRIENDLIES_ID,
    RUGBY_CHAMPIONSHIP_ID,
    RUGBY_WORLD_CUP_ID,
)

# Normalized alias groups (each list is one logical side).
_INTERNATIONAL_ALIAS_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("argentina",),
    ("australia", "wallabies"),
    ("england",),
    ("fiji", "fijian drua", "fijidrua", "fijiandrua"),
    ("france", "lesbleus"),
    ("ireland",),
    ("italy", "azzurri"),
    ("japan", "braveblossoms"),
    ("newzealand", "allblacks"),
    ("scotland",),
    ("southafrica", "springboks"),
    ("wales",),
    ("georgia",),
    ("samoa",),
    ("tonga",),
    ("romania",),
    ("uruguay",),
    ("usa", "unitedstates", "eagles"),
)

_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _group in _INTERNATIONAL_ALIAS_GROUPS:
    canonical = _group[0]
    for alias in _group:
        _ALIAS_TO_CANONICAL[alias] = canonical


def normalize_international_team_name(name: str) -> str:
    """Collapse sponsor / franchise names to a stable international key."""
    txt = str(name or "").strip().lower()
    txt = re.sub(r"\bsuper rugby\b", " ", txt)
    txt = re.sub(r"\brugby\b", " ", txt)
    txt = re.sub(r"\bnew zealand\b", "new zealand", txt)
    txt = re.sub(r"\bsouth africa\b", "south africa", txt)
    compact = re.sub(r"[^a-z0-9]+", "", txt)
    return _ALIAS_TO_CANONICAL.get(compact, compact)


def is_international_rugby_league(league_id: int) -> bool:
    return int(league_id) in INTERNATIONAL_RUGBY_CLUSTER


def get_linked_league_ids(league_id: int) -> List[int]:
    """All cluster leagues that can share training data / models."""
    if not is_international_rugby_league(league_id):
        return [int(league_id)]
    return list(INTERNATIONAL_RUGBY_CLUSTER.keys())


def international_pool_enabled(league_id: int, explicit_flag: Optional[bool] = None) -> bool:
    if explicit_flag is not None:
        return bool(explicit_flag)
    return is_international_rugby_league(league_id)


def _teams_for_league(conn: sqlite3.Connection, league_id: int) -> Dict[int, str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT t.id, t.name
        FROM team t
        JOIN event e ON t.id IN (e.home_team_id, e.away_team_id)
        WHERE e.league_id = ?
        ORDER BY t.name
        """,
        (int(league_id),),
    )
    return {int(row[0]): str(row[1]) for row in cur.fetchall()}


def _canonical_teams_for_league(conn: sqlite3.Connection, league_id: int) -> Dict[str, Set[int]]:
    out: Dict[str, Set[int]] = {}
    for team_id, team_name in _teams_for_league(conn, league_id).items():
        key = normalize_international_team_name(team_name)
        if not key:
            continue
        out.setdefault(key, set()).add(team_id)
    return out


def build_nations_championship_team_link_report(
    conn: sqlite3.Connection,
    nations_league_id: int = NATIONS_CHAMPIONSHIP_ID,
) -> Dict[str, Any]:
    """
    For each Nations Championship team, show whether the same side appears in
    Rugby Championship, Rugby World Cup, and International Friendlies.
    """
    sibling_ids = [
        RUGBY_CHAMPIONSHIP_ID,
        RUGBY_WORLD_CUP_ID,
        INTERNATIONAL_FRIENDLIES_ID,
    ]
    nc_teams = _teams_for_league(conn, nations_league_id)
    sibling_canonical: Dict[int, Dict[str, Set[int]]] = {
        lid: _canonical_teams_for_league(conn, lid) for lid in sibling_ids
    }

    rows: List[Dict[str, Any]] = []
    for team_id, team_name in sorted(nc_teams.items(), key=lambda x: x[1].lower()):
        canonical = normalize_international_team_name(team_name)
        links: Dict[str, Any] = {}
        for lid in sibling_ids:
            league_name = INTERNATIONAL_RUGBY_CLUSTER[lid]
            matches = sorted(sibling_canonical[lid].get(canonical, set()))
            if matches:
                sample_names = [
                    _teams_for_league(conn, lid).get(tid, str(tid)) for tid in matches[:3]
                ]
                links[league_name] = {
                    "linked": True,
                    "team_ids": matches,
                    "sample_names": sample_names,
                }
            else:
                links[league_name] = {"linked": False, "team_ids": [], "sample_names": []}

        rows.append(
            {
                "nations_team_id": team_id,
                "nations_team_name": team_name,
                "canonical_key": canonical,
                "links": links,
                "linked_league_count": sum(1 for v in links.values() if v["linked"]),
            }
        )

    linked_all_three = [r for r in rows if r["linked_league_count"] == 3]
    linked_some = [r for r in rows if 0 < r["linked_league_count"] < 3]
    linked_none = [r for r in rows if r["linked_league_count"] == 0]

    return {
        "nations_league_id": nations_league_id,
        "nations_league_name": INTERNATIONAL_RUGBY_CLUSTER[nations_league_id],
        "sibling_leagues": {lid: INTERNATIONAL_RUGBY_CLUSTER[lid] for lid in sibling_ids},
        "teams": rows,
        "summary": {
            "total_nations_teams": len(rows),
            "linked_all_three": len(linked_all_three),
            "linked_some": len(linked_some),
            "linked_none": len(linked_none),
        },
    }


def match_team_coverage(
    conn: sqlite3.Connection,
    league_id: int,
    home_team: str,
    away_team: str,
) -> int:
    """Return 0-2 for how many sides in the fixture exist in this league."""
    canonical = _canonical_teams_for_league(conn, league_id)
    home_key = normalize_international_team_name(home_team)
    away_key = normalize_international_team_name(away_team)
    score = 0
    if home_key and home_key in canonical:
        score += 1
    if away_key and away_key in canonical:
        score += 1
    return score


def resolve_prediction_source_league(
    target_league_id: int,
    home_team: str,
    away_team: str,
    conn: sqlite3.Connection,
    has_model: Callable[[int], bool],
) -> Tuple[int, Dict[str, Any]]:
    """
    Pick the league whose deployed model should serve this fixture.
    Prefers the target league, then linked cluster leagues with best team coverage.
    """
    target = int(target_league_id)
    meta: Dict[str, Any] = {
        "requested_league_id": target,
        "prediction_league_id": target,
        "link_source": "own",
    }

    if has_model(target):
        return target, meta

    if not is_international_rugby_league(target):
        meta["link_source"] = "none"
        return target, meta

    best_league: Optional[int] = None
    best_coverage = -1
    candidates: List[Dict[str, Any]] = []

    for lid in LINKED_MODEL_PRIORITY:
        if lid == target:
            continue
        if not has_model(lid):
            continue
        coverage = match_team_coverage(conn, lid, home_team, away_team)
        candidates.append({"league_id": lid, "coverage": coverage})
        if coverage > best_coverage:
            best_coverage = coverage
            best_league = lid

    meta["linked_candidates"] = candidates

    if best_league is not None and best_coverage > 0:
        meta.update(
            {
                "prediction_league_id": best_league,
                "link_source": "international_cluster",
                "linked_from_league_id": target,
                "linked_to_league_id": best_league,
                "team_coverage": best_coverage,
            }
        )
        return best_league, meta

    meta["link_source"] = "none"
    return target, meta


def has_own_or_linked_model(
    league_id: int,
    has_model: Callable[[int], bool],
) -> bool:
    target = int(league_id)
    if has_model(target):
        return True
    if not is_international_rugby_league(target):
        return False
    return any(has_model(lid) for lid in LINKED_MODEL_PRIORITY if lid != target)
