"""SportRadar competitor jersey colours for lineup display."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from prediction.sportradar_client import SportRadarRugbyClient

KIT_PRIORITY = ("home", "away", "third", "goalkeeper", "unknown")

# Teams with no $.jerseys in SportRadar profile — static spec ids (frontend mirrors this map).
COMPETITOR_KIT_FALLBACK_SPEC: Dict[str, str] = {
    "sr:competitor:92190": "boland",       # Boland Cavaliers
    "sr:competitor:393526": "chile",
    "sr:competitor:7956": "portugal",
    "sr:competitor:364712": "drua",        # Fijian Drua
    "sr:competitor:761406": "moana",      # Moana Pasifika
    "sr:competitor:154064": "england",    # International Friendlies England (not sr:competitor:4226)
    "sr:competitor:42525": "england",     # England A
    "sr:competitor:391538": "france",     # France XV
    "sr:competitor:200093": "ireland",    # Ireland XV
    "sr:competitor:950175": "japan",      # Japan XV
    "sr:competitor:180006": "maori",      # Maori All Blacks
    "sr:competitor:135744": "scotland",   # Scotland A
    "sr:competitor:263743": "south_africa",  # South Africa A
    "sr:competitor:186787": "zimbabwe",
    "sr:competitor:1325146": "italy",     # Italy XV — profile_fetch_failed
}

_profile_cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
_PROFILE_CACHE_TTL_S = 86400


def hex_colour(value: Any) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in v):
        return f"#{v.lower()}"
    return None


def summarize_kit(jerseys: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick best kit for display: prefer home, then away, then third."""
    if not jerseys:
        return None
    by_type = {str(j.get("type") or "").lower(): j for j in jerseys if isinstance(j, dict)}
    for kit_type in KIT_PRIORITY:
        if kit_type not in by_type:
            continue
        j = by_type[kit_type]
        base = hex_colour(j.get("base"))
        sleeve = hex_colour(j.get("sleeve"))
        number = hex_colour(j.get("number"))
        if base or sleeve or number:
            stripe_colour = hex_colour(j.get("horizontal_stripes_color"))
            return {
                "type": kit_type,
                "base": base,
                "sleeve": sleeve,
                "number": number,
                "horizontal_stripes": bool(j.get("horizontal_stripes")),
                "stripes": bool(j.get("stripes")),
                "horizontal_stripes_color": stripe_colour,
            }
    for j in jerseys:
        if not isinstance(j, dict):
            continue
        base = hex_colour(j.get("base"))
        if base:
            return {
                "type": str(j.get("type") or "unknown"),
                "base": base,
                "sleeve": hex_colour(j.get("sleeve")),
                "number": hex_colour(j.get("number")),
                "horizontal_stripes": bool(j.get("horizontal_stripes")),
                "stripes": bool(j.get("stripes")),
            }
    return None


def fetch_competitor_primary_kit(
    client: SportRadarRugbyClient,
    competitor_id: str,
    *,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return summarized home/away kit colours for a competitor, or None."""
    cid = str(competitor_id or "").strip()
    if not cid:
        return None

    if use_cache:
        cached = _profile_cache.get(cid)
        if cached and (time.time() - cached[0]) < _PROFILE_CACHE_TTL_S:
            return cached[1]

    from urllib.parse import quote

    enc = quote(cid, safe="")
    profile = client._get(f"competitors/{enc}/profile.json")  # noqa: SLF001
    primary: Optional[Dict[str, Any]] = None
    if isinstance(profile, dict):
        jerseys = profile.get("jerseys")
        if isinstance(jerseys, list):
            primary = summarize_kit([j for j in jerseys if isinstance(j, dict)])

    _profile_cache[cid] = (time.time(), primary)
    return primary


def enrich_lineup_teams_with_kits(
    client: SportRadarRugbyClient,
    teams: List[Dict[str, Any]],
) -> None:
    """Attach primary_kit and kit_fallback_spec to each lineup team (in-place)."""
    if not teams or not client.configured:
        return

    seen: set[str] = set()
    for team in teams:
        if not isinstance(team, dict):
            continue
        cid = str(team.get("id") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)

        fallback = COMPETITOR_KIT_FALLBACK_SPEC.get(cid)
        if fallback:
            team["kit_fallback_spec"] = fallback

        primary = fetch_competitor_primary_kit(client, cid)
        if primary:
            team["primary_kit"] = primary
            team["has_official_kit"] = True
        else:
            team["has_official_kit"] = False
