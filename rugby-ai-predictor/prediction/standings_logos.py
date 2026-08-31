"""Resolve team crest URLs via API-Sports /teams?search= with fallbacks."""

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

from prediction.config import STANDINGS_TEAM_OVERRIDES, STATIC_TEAM_LOGOS

logger = logging.getLogger(__name__)

APISPORTS_BASE = os.getenv("APISPORTS_RUGBY_BASE_URL", "https://v1.rugby.api-sports.io")

# Extra search terms when the standings name differs from API-Sports index.
SEARCH_ALIASES: Dict[str, List[str]] = {
    "bayonne": ["bayonnais", "aviron bayonnais"],
    "aviron bayonnais": ["bayonne", "bayonnais"],
    "newcastle falcons": ["newcastle red bulls", "newcastle"],
    "newcastle red bulls": ["newcastle falcons", "newcastle"],
    "exeter rc chiefs": ["exeter chiefs", "exeter"],
    "bath rugby": ["bath"],
    "saracens fc": ["saracens"],
    "gloucester rugby": ["gloucester"],
    "harlequins fc": ["harlequins"],
    "bristol bears": ["bristol bears", "bristol"],
    "stormers xxii": ["stormers", "dhl stormers"],
    "dhl stormers": ["stormers"],
    "vodacom bulls": ["bulls", "blue bulls"],
    "hollywoodbets sharks": ["sharks"],
    "cell c sharks": ["sharks"],
    "emirates lions": ["lions", "golden lions"],
    "fidelity securedrive lions": ["lions", "emirates lions"],
    "exeter chiefs": ["exeter"],
    "sale sharks": ["sharks"],
    "northampton saints": ["northampton"],
    "leicester tigers": ["leicester"],
    "bristol bears": ["bristol"],
    # French Top 14 (SportRadar long names)
    "stade toulousain": ["toulouse", "stade toulouse"],
    "montpellier herault rugby": ["montpellier", "montpellier herault"],
    "stade francais paris": ["stade francais", "stade français"],
    "agen": ["su agen"],
    "biarritz olympique": ["biarritz"],
    "ca brive": ["brive"],
    "grenoble fc": ["grenoble", "fc grenoble"],
    "union sportive oyonnax": ["oyonnax", "us oyonnax"],
    "us dax": ["dax"],
    "provence rugby": ["provence"],
    "cs bourgoin jallieu": ["bourgoin", "bourgoin jallieu"],
    "mont de marsan": ["stade montois"],
    "section paloise": ["pau", "section paloise bearne"],
    "stade rochelais": ["la rochelle", "rochelle"],
    "asm clermont auvergne": ["clermont", "asm clermont"],
    "union bordeaux begles": ["bordeaux begles", "bordeaux"],
    "rc toulonnais": ["toulon", "rc toulon"],
    "castres olympique": ["castres"],
    "lyon ou": ["lyon rugby", "lyon", "lou rugby"],
    "aviron bayonne": ["bayonne", "bayonnais", "aviron bayonnais"],
    "usa perpignan": ["perpignan", "usap"],
    "us montalbanaise": ["montauban", "us montauban"],
    # URC / Currie Cup name quirks
    "the sharks": ["sharks", "hollywoodbets sharks", "cell c sharks", "durban sharks"],
    "ford pumas": ["pumas", "mpumalanga pumas"],
    "sharks xv": ["sharks"],
    "stormers xxii": ["stormers", "dhl stormers", "western province"],
    "golden lions": ["lions"],
    "blue bulls": ["bulls"],
}

_memory_cache: Dict[str, tuple[float, Optional[str]]] = {}
_MEMORY_TTL_S = 86400


def _load_env() -> None:
    if load_dotenv is None:
        return
    from pathlib import Path

    here = Path(__file__).resolve()
    functions_root = here.parents[1]
    repo_root = functions_root.parent
    for p in (
        repo_root / ".env",
        functions_root / ".env",
        functions_root / ".env.local",
    ):
        if p.exists():
            load_dotenv(dotenv_path=p, override=p.name == ".env.local")


_load_env()


def get_apisports_key() -> str:
    return (
        os.getenv("APISPORTS_RUGBY_KEY")
        or os.getenv("APISPORTS_API_KEY")
        or ""
    ).strip()


def _norm_name(value: str) -> str:
    s = (value or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _norm_name(value))


def _strip_club_suffix(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\b(rugby union|rugby|rfc|fc|rc|ps)\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def _search_terms(team_name: str) -> List[str]:
    key = _norm_name(team_name)
    terms: List[str] = [team_name.strip()]
    stripped = _strip_club_suffix(team_name)
    if stripped and stripped not in terms:
        terms.append(stripped)
    if key:
        terms.append(key)
    for alias in STANDINGS_TEAM_OVERRIDES.get(key, []):
        terms.append(alias)
    for alias in SEARCH_ALIASES.get(key, []):
        terms.append(alias)
    # SportRadar often appends "RC" / "FC" / "Rugby" that API-Sports omits.
    parts = stripped.split() if stripped else []
    if len(parts) >= 2:
        terms.append(" ".join(parts[:2]))
        terms.append(parts[0])
    # Drop duplicate normalized terms, preserve order.
    seen: Set[str] = set()
    out: List[str] = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        nk = _norm_name(t)
        if nk in seen:
            continue
        seen.add(nk)
        out.append(t)
    return out


def _is_noise_team(name: str) -> bool:
    low = name.lower()
    for token in (" 7s", " xv", " ps", " w", " u20", " academy", " limpopo"):
        if token in low:
            return True
    return False


def _score_match(query: str, candidate_name: str) -> int:
    q = _norm_compact(query)
    c = _norm_compact(candidate_name)
    if not q or not c:
        return -1
    if q == c:
        return 100
    if q in c or c in q:
        return 80
    q_tokens = set(_norm_name(query).split())
    c_tokens = set(_norm_name(candidate_name).split())
    overlap = len(q_tokens & c_tokens)
    if overlap >= 2:
        return 60 + overlap
    if overlap == 1 and len(q_tokens) == 1:
        return 40
    return -1


def _lookup_logo_in_index(index: Dict[str, str], team_name: str) -> Optional[str]:
    """Match a team name against a normalized-name -> logo index."""
    if not index or not team_name:
        return None
    for term in _search_terms(team_name):
        hit = index.get(_norm_name(term))
        if hit:
            return hit
    best_url: Optional[str] = None
    best_score = -1
    for candidate_name, url in index.items():
        score = _score_match(team_name, candidate_name)
        if score > best_score:
            best_score = score
            best_url = url
    return best_url if best_score >= 60 else None


class HighlightlyTeamLogoResolver:
    """Build a league team-name index from Highlightly match payloads."""

    _memory_indexes: Dict[int, tuple[float, Dict[str, str]]] = {}
    _INDEX_TTL_S = 86400

    def __init__(
        self,
        highlightly_league_id: Optional[int],
        *,
        firestore_client: Any = None,
    ) -> None:
        self.league_id = int(highlightly_league_id) if highlightly_league_id is not None else None
        self.firestore = firestore_client
        self._index: Optional[Dict[str, str]] = None

    @property
    def configured(self) -> bool:
        return self.league_id is not None

    def _load_index(self) -> Dict[str, str]:
        if self._index is not None:
            return self._index
        if self.league_id is None:
            self._index = {}
            return self._index

        mem = self._memory_indexes.get(self.league_id)
        if mem and time.time() < mem[0]:
            self._index = mem[1]
            return self._index

        if self.firestore is not None:
            try:
                doc = self.firestore.collection("team_logo_cache").document(
                    f"highlightly_index::{self.league_id}"
                ).get()
                data = doc.to_dict() if getattr(doc, "exists", False) else None
                if isinstance(data, dict) and isinstance(data.get("index"), dict):
                    index = {str(k): str(v) for k, v in data["index"].items() if v}
                    if index:
                        self._index = index
                        self._memory_indexes[self.league_id] = (time.time() + self._INDEX_TTL_S, index)
                        return self._index
            except Exception:
                pass

        index = self._fetch_index_from_api()
        self._index = index
        self._memory_indexes[self.league_id] = (time.time() + self._INDEX_TTL_S, index)
        if self.firestore is not None and index:
            try:
                self.firestore.collection("team_logo_cache").document(
                    f"highlightly_index::{self.league_id}"
                ).set(
                    {
                        "highlightly_league_id": self.league_id,
                        "index": index,
                        "source": "highlightly_matches",
                        "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    },
                    merge=True,
                )
            except Exception as exc:
                logger.debug("Highlightly logo index cache write failed: %s", exc)
        return self._index

    def _fetch_index_from_api(self) -> Dict[str, str]:
        import os

        api_key = (os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip()
        if not api_key or self.league_id is None:
            return {}
        try:
            from prediction.highlightly_client import HighlightlyRugbyAPI

            api = HighlightlyRugbyAPI(api_key)
        except Exception as exc:
            logger.debug("Highlightly logo resolver init failed: %s", exc)
            return {}

        index: Dict[str, str] = {}
        for season in (2026, 2025, 2024):
            try:
                resp = api.get_matches(league_id=self.league_id, season=season, limit=100)
                rows = resp.get("data") if isinstance(resp, dict) else []
                if not isinstance(rows, list):
                    rows = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    for side in ("homeTeam", "awayTeam"):
                        team = row.get(side)
                        if not isinstance(team, dict):
                            continue
                        name = str(team.get("name") or "").strip()
                        tid = team.get("id")
                        logo = str(team.get("logo") or "").strip()
                        if not name:
                            continue
                        if not logo and tid is not None:
                            logo = f"https://highlightly.net/rugby/images/teams/{int(tid)}.png"
                        if logo:
                            index[_norm_name(name)] = logo
                if len(index) >= 8:
                    break
            except Exception as exc:
                logger.debug("Highlightly logo index fetch failed league=%s season=%s: %s", self.league_id, season, exc)
        return index

    def search_logo(self, team_name: str) -> Optional[str]:
        return _lookup_logo_in_index(self._load_index(), team_name)


class ApiSportsTeamLogoResolver:
    def __init__(self, api_key: Optional[str] = None, firestore_client: Any = None) -> None:
        self.api_key = (api_key or get_apisports_key()).strip()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {"x-apisports-key": self.api_key, "Accept": "application/json"}
            )
        self.firestore = firestore_client
        self._cache_collection = None
        if firestore_client is not None:
            try:
                self._cache_collection = firestore_client.collection("team_logo_cache")
            except Exception:
                self._cache_collection = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _cache_get(self, norm_key: str) -> Optional[str]:
        mem = _memory_cache.get(norm_key)
        if mem and time.time() < mem[0]:
            return mem[1]

        if self._cache_collection is not None:
            try:
                doc = self._cache_collection.document(f"apisports_v2::{norm_key}").get()
                data = doc.to_dict() if getattr(doc, "exists", False) else None
                if isinstance(data, dict):
                    logo = data.get("logo")
                    if logo:
                        _memory_cache[norm_key] = (time.time() + _MEMORY_TTL_S, str(logo))
                        return str(logo)
                    if data.get("miss"):
                        _memory_cache[norm_key] = (time.time() + 3600, None)
                        return None
            except Exception:
                pass
        return "MISS"

    def _cache_set(self, norm_key: str, logo: Optional[str]) -> None:
        _memory_cache[norm_key] = (time.time() + _MEMORY_TTL_S, logo)
        if self._cache_collection is None:
            return
        try:
            payload = {
                "norm_name": norm_key,
                "logo": logo,
                "miss": logo is None,
                "source": "apisports_search",
                "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            }
            self._cache_collection.document(f"apisports_v2::{norm_key}").set(payload, merge=True)
        except Exception as exc:
            logger.debug("API-Sports logo cache write failed: %s", exc)

    def search_logo(self, team_name: str) -> Optional[str]:
        norm_key = _norm_name(team_name)
        if not norm_key:
            return None

        cached = self._cache_get(norm_key)
        if cached != "MISS":
            return cached

        if not self.configured:
            self._cache_set(norm_key, None)
            return None

        best_logo: Optional[str] = None
        best_score = -1
        rate_limited = False
        for term in _search_terms(team_name):
            try:
                time.sleep(0.08)
                resp = self.session.get(
                    f"{APISPORTS_BASE.rstrip('/')}/teams",
                    params={"search": term},
                    timeout=15,
                )
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict):
                    errors = payload.get("errors")
                    if isinstance(errors, dict) and errors:
                        if any("limit" in str(v).lower() for v in errors.values()):
                            rate_limited = True
                            break
                rows = payload.get("response") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name") or "")
                    logo = row.get("logo")
                    if not logo or not name or _is_noise_team(name):
                        continue
                    score = _score_match(team_name, name)
                    if score > best_score:
                        best_score = score
                        best_logo = str(logo)
                if best_score >= 80:
                    break
            except requests.RequestException as exc:
                logger.debug("API-Sports team search failed for %s: %s", term, exc)

        if not best_logo and not rate_limited:
            for term in _search_terms(team_name):
                static = STATIC_TEAM_LOGOS.get(_norm_name(term))
                if static:
                    best_logo = static
                    break

        if not rate_limited:
            self._cache_set(norm_key, best_logo)
        return best_logo


def apply_static_standings_logos(standings: Dict[str, Any]) -> int:
    """Fast offline crest fill from STATIC_TEAM_LOGOS only (no API calls)."""
    if not isinstance(standings, dict):
        return 0
    groups = standings.get("groups")
    if not isinstance(groups, list):
        return 0

    applied = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        for list_key in ("standings", "teams"):
            rows = group.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                if (team_obj and team_obj.get("logo")) or row.get("logo"):
                    continue
                name = None
                if team_obj:
                    name = team_obj.get("name") or team_obj.get("team_name")
                if not name:
                    name = row.get("name") or row.get("team_name")
                if not name:
                    continue
                logo = None
                for term in _search_terms(str(name)):
                    logo = STATIC_TEAM_LOGOS.get(_norm_name(term))
                    if logo:
                        break
                if not logo:
                    continue
                if team_obj is not None:
                    team_obj["logo"] = logo
                    team_obj["badge"] = logo
                row["logo"] = logo
                row["badge"] = logo
                applied += 1
    return applied


def enrich_standings_logos(
    standings: Dict[str, Any],
    *,
    sportsdb_league_id: Optional[int] = None,
    highlightly_league_id: Optional[int] = None,
    firestore_client: Any = None,
    sportsdb_client: Any = None,
) -> int:
    """
    Fill team.logo / team.badge on a standings payload.
    Primary: API-Sports /teams?search=
    Fallback: TheSportsDB search, then STATIC_TEAM_LOGOS.
    Returns count of logos applied.
    """
    if not isinstance(standings, dict):
        return 0

    groups = standings.get("groups")
    if not isinstance(groups, list):
        return 0

    league_obj = standings.get("league")
    if not isinstance(league_obj, dict):
        league_obj = {}
        standings["league"] = league_obj

    if highlightly_league_id is not None:
        try:
            hl_logo = f"https://highlightly.net/rugby/images/leagues/{int(highlightly_league_id)}.png"
            league_obj.setdefault("logo", hl_logo)
            league_obj.setdefault("badge", hl_logo)
        except (TypeError, ValueError):
            pass

    resolver = ApiSportsTeamLogoResolver(firestore_client=firestore_client)
    hl_resolver = HighlightlyTeamLogoResolver(
        highlightly_league_id,
        firestore_client=firestore_client,
    )
    applied = 0
    missed: List[str] = []

    for group in groups:
        if not isinstance(group, dict):
            continue
        for list_key in ("standings", "teams"):
            rows = group.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                if (team_obj and team_obj.get("logo")) or row.get("logo"):
                    continue
                name = None
                if team_obj:
                    name = team_obj.get("name") or team_obj.get("team_name")
                if not name:
                    name = row.get("name") or row.get("team_name")
                if not name:
                    continue

                logo = resolver.search_logo(str(name))
                if not logo and hl_resolver.configured:
                    logo = hl_resolver.search_logo(str(name))
                if logo:
                    if team_obj is not None:
                        team_obj["logo"] = logo
                        team_obj["badge"] = logo
                    row["logo"] = logo
                    row["badge"] = logo
                    applied += 1
                else:
                    missed.append(str(name))

    if missed and hl_resolver.configured:
        for nm in list(missed):
            logo = hl_resolver.search_logo(nm)
            if not logo:
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for list_key in ("standings", "teams"):
                    rows = group.get(list_key)
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                        if (team_obj and team_obj.get("logo")) or row.get("logo"):
                            continue
                        rn = (team_obj or {}).get("name") or row.get("name") or ""
                        if rn and _norm_name(rn) == _norm_name(nm):
                            if team_obj is not None:
                                team_obj["logo"] = logo
                                team_obj["badge"] = logo
                            row["logo"] = logo
                            row["badge"] = logo
                            applied += 1
            missed = [n for n in missed if _norm_name(n) != _norm_name(nm)]

    if missed and sportsdb_client is not None:
        for nm in missed:
            try:
                searched = sportsdb_client.search_teams(nm)
                for t in searched[:3]:
                    badge = t.get("strTeamBadge") or t.get("strTeamLogo") or ""
                    if not badge:
                        continue
                    ts_name = t.get("strTeam") or ""
                    if _norm_compact(nm) not in _norm_compact(ts_name) and _norm_compact(ts_name) not in _norm_compact(nm):
                        continue
                    for group in groups:
                        if not isinstance(group, dict):
                            continue
                        for list_key in ("standings", "teams"):
                            rows = group.get(list_key)
                            if not isinstance(rows, list):
                                continue
                            for row in rows:
                                if not isinstance(row, dict):
                                    continue
                                team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                                if (team_obj and team_obj.get("logo")) or row.get("logo"):
                                    continue
                                rn = (team_obj or {}).get("name") or row.get("name") or ""
                                if rn and _norm_name(rn) == _norm_name(nm):
                                    if team_obj is not None:
                                        team_obj["logo"] = badge
                                        team_obj["badge"] = badge
                                    row["logo"] = badge
                                    row["badge"] = badge
                                    applied += 1
                    break
            except Exception:
                continue

    # Final static pass for anything still missing.
    for group in groups:
        if not isinstance(group, dict):
            continue
        for list_key in ("standings", "teams"):
            rows = group.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                if (team_obj and team_obj.get("logo")) or row.get("logo"):
                    continue
                nm = (team_obj or {}).get("name") or row.get("name") or ""
                url = STATIC_TEAM_LOGOS.get(_norm_name(str(nm)))
                if url:
                    if team_obj is not None:
                        team_obj["logo"] = url
                        team_obj["badge"] = url
                    row["logo"] = url
                    row["badge"] = url
                    applied += 1

    logger.info(
        "Standings logo enrichment applied=%s league=%s apisports=%s",
        applied,
        sportsdb_league_id,
        resolver.configured,
    )
    return applied
