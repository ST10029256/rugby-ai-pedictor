from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class TransientHttpError(Exception):
    pass


class TheSportsDBClient:
    def __init__(self, base_url: str, api_key: str, rate_limit_rpm: int = 15, timeout_seconds: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

        # Simple leaky-bucket rate limiter
        self._lock = threading.Lock()
        self._min_interval = 60.0 / max(1, rate_limit_rpm)
        self._next_time = 0.0

    def _rate_limit_wait(self) -> None:
        with self._lock:
            now = time.time()
            if now < self._next_time:
                time.sleep(self._next_time - now)
            self._next_time = time.time() + self._min_interval

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(TransientHttpError))
    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._rate_limit_wait()
        url = f"{self.base_url}/{self.api_key}/{endpoint}.php"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise TransientHttpError(str(exc)) from exc

        if resp.status_code in (429, 500, 502, 503, 504):
            raise TransientHttpError(f"HTTP {resp.status_code} from TheSportsDB")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # High-level helpers
    def get_leagues_all(self) -> List[Dict[str, Any]]:
        data = self._request("all_leagues")
        return data.get("leagues") or []

    def find_rugby_league(self, target_name: str) -> Optional[Dict[str, Any]]:
        target_lower = target_name.strip().lower()

        # 1) Prefer all_leagues then filter by rugby and name
        for lg in self.get_leagues_all():
            if str(lg.get("strSport", "")).lower().startswith("rugby") and target_lower in str(lg.get("strLeague", "")).lower():
                return lg

        # 2) searchleagues by name (doc endpoint)
        data = self._request("searchleagues", {"l": target_name})
        leagues2 = data.get("countrys") or data.get("leagues") or []
        for lg in leagues2:
            if str(lg.get("strSport", "")).lower().startswith("rugby"):
                return lg

        # 3) Fallback: infer league id from teams listing by league name
        league_name_variants = [
            target_name,
            target_name.replace(" ", "_"),
            target_name.replace(" ", "%20"),
        ]
        for variant in league_name_variants:
            data = self._request("search_all_teams", {"l": variant})
            teams = data.get("teams") or []
            if teams:
                lg_id = teams[0].get("idLeague")
                lg_name = teams[0].get("strLeague")
                if lg_id:
                    return {"idLeague": lg_id, "strLeague": lg_name, "strSport": teams[0].get("strSport")}

        return None

    def get_seasons(self, league_id: str | int) -> List[str]:
        data = self._request("search_all_seasons", {"id": str(league_id)})
        seasons = data.get("seasons") or []
        result: List[str] = []
        for s in seasons:
            val = s.get("strSeason") or s.get("season")
            if val:
                result.append(val)
        return result

    def get_teams(self, league_id: str | int) -> List[Dict[str, Any]]:
        data = self._request("lookup_all_teams", {"id": str(league_id)})
        return data.get("teams") or []

    def lookup_team(self, team_id: str | int) -> Optional[Dict[str, Any]]:
        data = self._request("lookupteam", {"id": str(team_id)})
        teams = data.get("teams") or []
        return teams[0] if teams else None

    def get_events_for_season(self, league_id: str | int, season: str) -> List[Dict[str, Any]]:
        data = self._request("eventsseason", {"id": str(league_id), "s": season})
        return data.get("events") or []

    def get_events_for_day(self, date_iso: str, sport: Optional[str] = None, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"d": date_iso}
        if sport:
            params["s"] = sport
        if league_id is not None:
            params["l"] = str(league_id)
        data = self._request("eventsday", params)
        return data.get("events") or []


class APISportsRugbyClient:
    def __init__(self, base_url: str = "https://v1.rugby.api-sports.io", api_key: str = "", timeout_seconds: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        return {"x-apisports-key": self.api_key}

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(TransientHttpError))
    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.get(url, params=params or {}, headers=self._headers(), timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise TransientHttpError(str(exc)) from exc
        if resp.status_code in (429, 500, 502, 503, 504):
            raise TransientHttpError(f"HTTP {resp.status_code} from API-Sports")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def list_games(self, league_id: int, season: int, date: Optional[str] = None, timezone: str = "UTC") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"league": league_id, "season": season, "timezone": timezone}
        if date:
            params["date"] = date
        data = self._request("games", params)
        return data.get("response") or []

    def get_events_for_day(self, date_iso: str, sport: Optional[str] = None, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"d": date_iso}
        if sport:
            params["s"] = sport
        if league_id:
            params["l"] = str(league_id)
        data = self._request("eventsday", params)
        return data.get("events") or []
