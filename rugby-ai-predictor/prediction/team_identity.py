"""Canonical team identity.

One `team.id` must mean exactly one real-world side. Two things break that:

* **Collision** - a name is reused by different sides in different
  competitions. "Bulls" is the URC/Super Rugby franchise, but in the Currie Cup
  it is the Blue Bulls, a separate provincial side that fields the union's
  second string. Resolving names globally merged them into one id, so Elo,
  embeddings and form features were blending two different teams.
* **Fragmentation** - one side arrives under several spellings over the years
  ("Harlequins" / "Harlequins Football Club", "Treviso" / "Benetton"), so its
  history is split across ids and every id sees only part of it.

This module is the single source of truth for both. `resolve_team_id` is the
ingestion-time resolver; the maps below also drive the one-off repair in
`scripts/fix_team_identity.py`.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Dict, Optional, Set, Tuple

CURRIE_CUP_LEAGUE_ID = 5069
URC_LEAGUE_ID = 4446
SUPER_RUGBY_LEAGUE_ID = 4551

# Competitions contested by national teams only.
NATION_LEAGUES: Set[int] = {4574, 4714, 4986, 5480}

# Friendlies mix nations, second national sides, clubs and invitational teams,
# so a team id appearing here tells us nothing about its home competition.
MIXED_LEAGUES: Set[int] = {5479}

# Club competitions that legitimately share a side. The South African
# franchises moved from Super Rugby to the URC, so "Bulls" is one continuous
# team across both. The Currie Cup is deliberately absent: its entries are
# separate provincial unions and must never collapse into a franchise.
CLUB_LEAGUE_GROUPS: Tuple[Set[int], ...] = ({URC_LEAGUE_ID, SUPER_RUGBY_LEAGUE_ID},)


# --------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------

# (league_id, wrong_team_id) -> correct_team_id.
# Events in that league only; the source id stays valid elsewhere.
LEAGUE_SCOPED_TEAM_ID_REMAPS: Dict[Tuple[int, int], int] = {
    # Currie Cup entries wrongly attached to the senior franchise.
    (CURRIE_CUP_LEAGUE_ID, 147370): 142062,  # Bulls          -> Blue Bulls
    (CURRIE_CUP_LEAGUE_ID, 147342): 142068,  # Lions          -> Golden Lions
    (CURRIE_CUP_LEAGUE_ID, 147423): 147341,  # Sharks         -> Sharks XV
    (CURRIE_CUP_LEAGUE_ID, 135920): 147357,  # Cheetahs       -> Free State Cheetahs
    (CURRIE_CUP_LEAGUE_ID, 147482): 147357,  # "Cheetahs 2"   -> Free State Cheetahs
    (CURRIE_CUP_LEAGUE_ID, 136670): 142075,  # Stormers       -> Western Province
    (CURRIE_CUP_LEAGUE_ID, 147521): 142075,  # Stormers Xxiii -> Western Province
    # Fiji and Fijian Drua are interchanged in both directions: the national
    # side is filed under the club's name, and Super Rugby carries the club's
    # whole record a second time under the nation's name.
    (4574, 137390): 147441,
    (5479, 137390): 147441,
    (5480, 137390): 147441,
    (SUPER_RUGBY_LEAGUE_ID, 147441): 137390,
    # Four 2010 Magners League fixtures filed under the New Zealand Blues.
    (URC_LEAGUE_ID, 147420): 147346,  # Blues -> Cardiff Blues
}

# from_team_id -> surviving_team_id, applied in every league.
# The survivor is the id whose name matches what the feed sends today, so
# future ingestion keeps landing on it.
TEAM_ID_MERGES: Dict[int, int] = {
    # --- one club, several spellings ---
    147466: 135202,  # Harlequins Football Club   -> Harlequins
    147371: 135205,  # Newcastle Red Bulls        -> Newcastle Falcons
    135504: 147468,  # Leeds Carnegie             -> Yorkshire
    147361: 147467,  # Bristol Bears              -> Bristol
    135740: 147467,  # Bristol Rugby              -> Bristol
    135199: 147363,  # Bath Rugby                 -> Bath
    147518: 135338,  # RC Toulon                  -> RC Toulonnais
    135337: 147424,  # Stade Français Paris       -> Stade Francais Paris
    147430: 135340,  # La Rochelle                -> Stade Rochelais
    147426: 147435,  # Montpellier Herault RC     -> Montpellier
    135334: 147435,  # Montpellier Hérault Rugby  -> Montpellier
    147434: 147436,  # Union Sportive Oyonnax     -> US Oyonnax
    135335: 147436,  # Oyonnax Rugby              -> US Oyonnax
    135332: 147427,  # ASM Clermont Auvergne      -> Clermont
    135336: 147429,  # Racing Métro 92            -> Racing 92
    135329: 147431,  # Union Bordeaux Bègles      -> Bordeaux Begles
    135341: 147432,  # Lyon OU                    -> Lyon
    135333: 147433,  # FC Grenoble                -> Grenoble FC
    137385: 147428,  # SU Agen Lot-et-Garonne     -> Agen
    141952: 147425,  # US Montauban               -> Montauban
    147421: 135595,  # Treviso                    -> Benetton
    147349: 135595,  # Benetton Treviso           -> Benetton
    147347: 135595,  # Benneton                   -> Benetton
    147346: 147339,  # Cardiff Blues              -> Cardiff Rugby
    147470: 137391,  # Force                      -> Western Force
    136657: 147476,  # Melbourne Rebels           -> Rebels
    147494: 147485,  # New Zealand Maori          -> Maori All Blacks
    # --- second national sides labelled "A" in one feed and "B" in another ---
    147506: 147512,  # Australia B    -> Australia A
    147504: 147508,  # New Zealand B  -> New Zealand A
    147519: 147513,  # Scotland B     -> Scotland A
    147498: 147514,  # Argentina B    -> Argentina A
    147503: 147520,  # South Africa B -> South Africa A
    # --- empty "<name> Rugby" placeholder rows from the original seed ---
    137123: 147446, 137124: 147445, 137125: 147447, 137126: 147454,
    137127: 147441, 137128: 147443, 137129: 147455, 137130: 147449,
    137131: 147444, 137132: 147442, 137133: 147437, 137134: 147456,
    137135: 147453, 137136: 147439, 137137: 147451, 137138: 147438,
    137139: 147457, 137140: 147450, 137141: 147452, 137175: 147448,
    141517: 147459, 141518: 147440, 141519: 147464, 145720: 147465,
    147338: 147461, 147375: 147463, 147376: 147460,
    147377: 147512, 147413: 147511,
    # --- empty "<name> Super Rugby" placeholder rows ---
    136661: 147420, 136666: 147370, 136662: 147472, 136663: 147471,
    136667: 147477, 136668: 147342, 147359: 147423, 136660: 147474,
    136664: 147469, 136658: 147475, 136665: 147473,
    # --- empty URC placeholder rows ---
    147368: 135597, 147369: 135598, 135600: 147355, 147364: 135599,
    147367: 135601, 147366: 135605, 147365: 135606, 136669: 147423,
    147352: 135602,
    # --- empty Currie Cup placeholder rows ---
    142071: 147478,  # Luiperds                    -> Leopards
    142065: 147479,  # Eastern Province Elephants  -> Eastern Province Kings
    142074: 147480,  # SWD Eagles                  -> Eagles
    142066: 147481,  # Valke                       -> Falcons
    147358: 147341,  # Sharks Currie Cup           -> Sharks XV
    142072: 147340,  # MRU. New Nation Pumas       -> Pumas
}

# Names to write onto surviving rows, so the database itself says which side a
# fixture involves instead of relying on a display-time translation.
CANONICAL_TEAM_NAMES: Dict[int, str] = {
    142062: "Blue Bulls",
    142068: "Golden Lions",
    147341: "Sharks XV",
    147357: "Free State Cheetahs",
    142075: "Western Province",
    147441: "Fiji",
    147339: "Cardiff Rugby",
}

# Home competition for rows we rebuilt, so the Teams panel groups them right.
CANONICAL_TEAM_LEAGUES: Dict[int, int] = {
    142062: CURRIE_CUP_LEAGUE_ID,
    142068: CURRIE_CUP_LEAGUE_ID,
    147341: CURRIE_CUP_LEAGUE_ID,
    147357: CURRIE_CUP_LEAGUE_ID,
    142075: CURRIE_CUP_LEAGUE_ID,
}


# --------------------------------------------------------------------------
# Ingestion-time aliases
# --------------------------------------------------------------------------

# (league_id, normalized feed name) -> team_id.
# Only names that cannot be resolved safely on their own belong here: those
# that collide with another competition, and historical spellings that no
# longer appear in the feed.
LEAGUE_TEAM_ALIASES: Dict[Tuple[int, str], int] = {}


def _register(league_id: int, team_id: int, *names: str) -> None:
    for name in names:
        LEAGUE_TEAM_ALIASES[(league_id, normalize_team_key(name))] = team_id


def normalize_team_key(name: object) -> str:
    """Lowercase, strip accents and punctuation, drop sponsor prefixes."""
    import unicodedata

    raw = unicodedata.normalize("NFD", str(name or ""))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


# Currie Cup: every provincial union, kept apart from the franchises.
_register(CURRIE_CUP_LEAGUE_ID, 142062, "Bulls", "Blue Bulls", "Bulls XV", "Vodacom Bulls", "Vodacom Blue Bulls")
_register(CURRIE_CUP_LEAGUE_ID, 142068, "Lions", "Golden Lions", "Lions XV", "Sigma Lions", "Emirates Lions")
_register(CURRIE_CUP_LEAGUE_ID, 147341, "Sharks", "Sharks XV", "The Sharks", "Sharks Currie Cup", "Hollywoodbets Sharks XV")
_register(CURRIE_CUP_LEAGUE_ID, 147357, "Cheetahs", "Cheetahs 2", "Free State Cheetahs", "Toyota Cheetahs")
_register(CURRIE_CUP_LEAGUE_ID, 142075, "Stormers", "Stormers XXIII", "Stormers Xxiii", "Stormers XIII",
          "Western Province", "DHL Western Province", "DHL Stormers")
_register(CURRIE_CUP_LEAGUE_ID, 147340, "Pumas", "MRU. New Nation Pumas", "New Nation Pumas", "Airlink Pumas")
_register(CURRIE_CUP_LEAGUE_ID, 142063, "Boland", "Boland Cavaliers", "Suzuki Boland")
_register(CURRIE_CUP_LEAGUE_ID, 142070, "Griquas", "Windhoek Draught Griquas", "Tafel Lager Griquas")
_register(CURRIE_CUP_LEAGUE_ID, 142069, "Griffons", "Valke Griffons")
_register(CURRIE_CUP_LEAGUE_ID, 147478, "Leopards", "Luiperds")
_register(CURRIE_CUP_LEAGUE_ID, 147480, "Eagles", "SWD Eagles")
_register(CURRIE_CUP_LEAGUE_ID, 147481, "Falcons", "Valke")
_register(CURRIE_CUP_LEAGUE_ID, 142064, "Border Bulldogs", "Border")
_register(CURRIE_CUP_LEAGUE_ID, 147479, "Eastern Province Kings", "Eastern Province Elephants", "EP Kings", "Elephants")
_register(CURRIE_CUP_LEAGUE_ID, 142310, "Welwitschias")

# Super Rugby and URC keep the senior franchises.
for _lid in (SUPER_RUGBY_LEAGUE_ID, URC_LEAGUE_ID):
    _register(_lid, 147370, "Bulls", "Vodacom Bulls")
    _register(_lid, 147342, "Lions", "Emirates Lions")
    _register(_lid, 147423, "Sharks", "The Sharks", "Hollywoodbets Sharks")
    _register(_lid, 135920, "Cheetahs", "Toyota Cheetahs")
    _register(_lid, 136670, "Stormers", "DHL Stormers")
_register(SUPER_RUGBY_LEAGUE_ID, 137390, "Fijian Drua", "Swire Shipping Fijian Drua", "Fiji")
_register(SUPER_RUGBY_LEAGUE_ID, 137391, "Western Force", "Force")
_register(SUPER_RUGBY_LEAGUE_ID, 147476, "Rebels", "Melbourne Rebels")
_register(SUPER_RUGBY_LEAGUE_ID, 147474, "Waratahs", "New South Wales Waratahs", "NSW Waratahs")
_register(SUPER_RUGBY_LEAGUE_ID, 147469, "Highlanders", "Otago Highlanders")
_register(SUPER_RUGBY_LEAGUE_ID, 147475, "Reds", "Queensland Reds")
_register(SUPER_RUGBY_LEAGUE_ID, 147473, "Hurricanes", "Wellington Hurricanes")
_register(SUPER_RUGBY_LEAGUE_ID, 147420, "Blues", "Auckland Blues", "Blues Super Rugby")
_register(SUPER_RUGBY_LEAGUE_ID, 147472, "Chiefs", "Chiefs Super Rugby")
_register(SUPER_RUGBY_LEAGUE_ID, 147471, "Crusaders", "Crusaders Super Rugby")
_register(SUPER_RUGBY_LEAGUE_ID, 147477, "Jaguares", "Jaguares Super Rugby")
_register(URC_LEAGUE_ID, 147339, "Cardiff", "Cardiff Rugby", "Cardiff Blues", "Blues")
_register(URC_LEAGUE_ID, 135595, "Benetton", "Treviso", "Benetton Treviso", "Benneton")
_register(URC_LEAGUE_ID, 135602, "Dragons", "Newport Gwent Dragons")
_register(URC_LEAGUE_ID, 147355, "Glasgow", "Glasgow Warriors")
_register(URC_LEAGUE_ID, 135606, "Zebre", "Zebre Rugby", "Zebre Parma")

# National-team competitions: the feed sometimes sends the Super Rugby club
# name for Fiji, and alternates "A"/"B" for second sides.
for _lid in NATION_LEAGUES | MIXED_LEAGUES:
    _register(_lid, 147441, "Fiji", "Fijian Drua")
    _register(_lid, 147512, "Australia A", "Australia B", "Australia A Rugby")
    _register(_lid, 147508, "New Zealand A", "New Zealand B")
    _register(_lid, 147513, "Scotland A", "Scotland B")
    _register(_lid, 147514, "Argentina A", "Argentina B")
    _register(_lid, 147520, "South Africa A", "South Africa B")
    _register(_lid, 147511, "England A", "England A Rugby")
    _register(_lid, 147485, "Maori All Blacks", "New Zealand Maori")
    # "Los Pumas" is Argentina; a bare "Pumas" in a friendly is the Mpumalanga
    # side, which tours (it beat Namibia 59-19 in Windhoek in June 2025).
    _register(_lid, 147445, "Los Pumas")
_register(5479, 147340, "Pumas", "Airlink Pumas", "MRU. New Nation Pumas", "New Nation Pumas")
_register(5479, 142310, "Welwitschias")

# Premiership and Top 14 renames.
_register(4414, 135202, "Harlequins", "Harlequins Football Club")
_register(4414, 135205, "Newcastle Falcons", "Newcastle Red Bulls")
_register(4414, 147467, "Bristol", "Bristol Bears", "Bristol Rugby")
_register(4414, 147363, "Bath", "Bath Rugby")
_register(4414, 147468, "Yorkshire", "Leeds Carnegie", "Yorkshire Carnegie")
_register(4430, 135338, "RC Toulonnais", "RC Toulon", "Toulon")
_register(4430, 147424, "Stade Francais Paris", "Stade Français Paris", "Stade Francais", "Stade Français")
_register(4430, 135340, "Stade Rochelais", "La Rochelle")
_register(4430, 147435, "Montpellier", "Montpellier Herault RC", "Montpellier Hérault Rugby")
_register(4430, 147436, "US Oyonnax", "Union Sportive Oyonnax", "Oyonnax", "Oyonnax Rugby")
_register(4430, 147427, "Clermont", "ASM Clermont Auvergne")
_register(4430, 147429, "Racing 92", "Racing Métro 92", "Racing Metro 92")
_register(4430, 147431, "Bordeaux Begles", "Union Bordeaux Bègles", "Union Bordeaux Begles")
_register(4430, 147432, "Lyon", "Lyon OU")
_register(4430, 147433, "Grenoble FC", "FC Grenoble", "Grenoble")
_register(4430, 147428, "Agen", "SU Agen", "SU Agen Lot-et-Garonne")
_register(4430, 147425, "Montauban", "US Montauban")


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def canonical_team_id(team_id: Optional[int], league_id: Optional[int] = None) -> Optional[int]:
    """Follow league-scoped remaps then merges to the surviving id."""
    if team_id is None:
        return None
    tid = int(team_id)
    if league_id is not None:
        tid = LEAGUE_SCOPED_TEAM_ID_REMAPS.get((int(league_id), tid), tid)
    seen = {tid}
    while tid in TEAM_ID_MERGES:
        tid = TEAM_ID_MERGES[tid]
        if tid in seen:  # defensive: a cycle in the map would hang ingestion
            break
        seen.add(tid)
    return tid


def leagues_may_share_team(league_a: Optional[int], league_b: Optional[int]) -> bool:
    """Whether one side can legitimately appear in both competitions."""
    if league_a is None or league_b is None:
        return True
    a, b = int(league_a), int(league_b)
    if a == b:
        return True
    if a in MIXED_LEAGUES or b in MIXED_LEAGUES:
        return True
    if a in NATION_LEAGUES and b in NATION_LEAGUES:
        return True
    return any(a in group and b in group for group in CLUB_LEAGUE_GROUPS)


class _Index:
    """Name and competition lookups for one connection.

    Resolution runs twice per fixture, so scanning `team` and `event` each time
    would make a full history rebuild crawl. Built once, then kept current as
    new sides are inserted.
    """

    __slots__ = ("by_name", "event_leagues")

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.by_name: Dict[str, list] = {}
        for tid, name, tleague in conn.execute("SELECT id, name, league_id FROM team"):
            entry = (int(tid), int(tleague) if tleague is not None else None)
            self.by_name.setdefault(normalize_team_key(name), []).append(entry)

        self.event_leagues: Dict[int, Set[int]] = {}
        for tid, lid in conn.execute(
            "SELECT tid, league_id FROM ("
            "  SELECT home_team_id AS tid, league_id FROM event"
            "  UNION SELECT away_team_id AS tid, league_id FROM event)"
        ):
            if tid is not None and lid is not None:
                self.event_leagues.setdefault(int(tid), set()).add(int(lid))

    def add_team(self, team_id: int, name: str, league_id: Optional[int]) -> None:
        self.by_name.setdefault(normalize_team_key(name), []).append((team_id, league_id))
        if league_id is not None:
            self.event_leagues.setdefault(team_id, set()).add(league_id)


_INDEXES: Dict[int, _Index] = {}


def _index(conn: sqlite3.Connection) -> _Index:
    idx = _INDEXES.get(id(conn))
    if idx is None:
        idx = _INDEXES[id(conn)] = _Index(conn)
    return idx


def reset_index(conn: Optional[sqlite3.Connection] = None) -> None:
    """Drop cached lookups, after the team table is changed behind our back."""
    if conn is None:
        _INDEXES.clear()
    else:
        _INDEXES.pop(id(conn), None)


def resolve_team_id(
    conn: sqlite3.Connection,
    team_name: str,
    league_id: Optional[int],
    create: bool = True,
) -> Optional[int]:
    """Resolve a feed team name within its competition.

    Never reuses an id from an unrelated competition: that is what merged the
    Currie Cup provinces into the URC franchises. When nothing suitable exists
    a new row is created, scoped to the league.
    """
    name = str(team_name or "").strip()
    if not name:
        return None
    key = normalize_team_key(name)
    lid = int(league_id) if league_id is not None else None

    if lid is not None:
        alias = LEAGUE_TEAM_ALIASES.get((lid, key))
        if alias is not None:
            return canonical_team_id(alias, lid)

    idx = _index(conn)
    candidates = idx.by_name.get(key, [])

    # Prefer a side already playing in this competition.
    if lid is not None:
        for tid, _ in candidates:
            if lid in idx.event_leagues.get(tid, ()):
                return canonical_team_id(tid, lid)
        for tid, tleague in candidates:
            if tleague == lid:
                return canonical_team_id(tid, lid)

    # Otherwise only reuse an id when the competitions may share a side.
    for tid, tleague in candidates:
        homes = idx.event_leagues.get(tid) or ({tleague} if tleague is not None else set())
        if not homes or all(leagues_may_share_team(lid, other) for other in homes):
            return canonical_team_id(tid, lid)

    if not create:
        return None

    cur = conn.cursor()
    cur.execute("INSERT INTO team (name, league_id) VALUES (?, ?)", (name, lid))
    team_id = int(cur.lastrowid)
    idx.add_team(team_id, name, lid)
    return team_id
