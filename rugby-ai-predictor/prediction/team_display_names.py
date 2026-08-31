"""League-scoped display labels so odds/UI match standings names.

The database now stores each Currie Cup province under its own identity
(see `team_identity`), so these are labels only. They still cover the short
URC-style names (Lions, Bulls) because odds feeds and older Firestore
documents keep sending them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

CURRIE_CUP_LEAGUE_ID = 5069

_CURRIE_CUP_DISPLAY = {
    "lions": "Golden Lions",
    "goldenlions": "Golden Lions",
    "bulls": "Blue Bulls",
    "bluebulls": "Blue Bulls",
    "sharks": "Sharks XV",
    "sharksxv": "Sharks XV",
    "sharkscurriecup": "Sharks XV",
    "stormers": "Western Province",
    "stormersxxiii": "Western Province",
    "stormersxiii": "Western Province",
    "westernprovince": "Western Province",
    "boland": "Boland",
    "bolandcavaliers": "Boland",
    "freestatecheetahs": "Cheetahs",
    "cheetahs": "Cheetahs",
    "pumas": "Pumas",
    "mrunewnationpumas": "Pumas",
    "newnationpumas": "Pumas",
    "griquas": "Griquas",
}


# Any label -> the name the database and model use for that province. A Currie
# Cup fixture must never reach the model as "Bulls" or "Sharks": those are the
# URC/Super Rugby franchises, which are now separate teams.
_CURRIE_CUP_CANONICAL = {
    "lions": "Golden Lions",
    "goldenlions": "Golden Lions",
    "bulls": "Blue Bulls",
    "bluebulls": "Blue Bulls",
    "sharks": "Sharks XV",
    "sharksxv": "Sharks XV",
    "sharkscurriecup": "Sharks XV",
    "cheetahs": "Free State Cheetahs",
    "freestatecheetahs": "Free State Cheetahs",
    "stormers": "Western Province",
    "stormersxxiii": "Western Province",
    "stormersxiii": "Western Province",
    "westernprovince": "Western Province",
    "boland": "Boland Cavaliers",
    "bolandcavaliers": "Boland Cavaliers",
}


def _norm_key(name: Any) -> str:
    raw = str(name or "").lower()
    return re.sub(r"[^a-z0-9]+", "", raw)


def _currie_cup_lookup(name: Any, league_id: Any, table: dict) -> str:
    raw = str(name or "").strip()
    if not raw:
        return raw
    try:
        lid = int(league_id) if league_id is not None else None
    except (TypeError, ValueError):
        lid = None
    if lid != CURRIE_CUP_LEAGUE_ID:
        return raw
    return table.get(_norm_key(raw), raw)


def display_team_name_for_league(name: Any, league_id: Any) -> str:
    """Label to show in the UI, matching the published standings."""
    return _currie_cup_lookup(name, league_id, _CURRIE_CUP_DISPLAY)


def canonical_model_team_name(name: Any, league_id: Any) -> str:
    """Name the database and model use, whatever label came in."""
    return _currie_cup_lookup(name, league_id, _CURRIE_CUP_CANONICAL)
