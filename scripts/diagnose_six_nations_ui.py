#!/usr/bin/env python3
"""
Diagnose why Six Nations fixtures show incorrectly in the UI.

This script mirrors the frontend logic in:
- public/src/App.js
- public/src/utils/date.js

It fetches upcoming matches for league 4714, then prints:
1) per-match inclusion/exclusion reason
2) resolved kickoff used by UI
3) the "current fixture block" (e.g. 6/7 only, excluding 14)
4) anomalies where kickoff date/time likely causes wrong UI display
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


ENDPOINT = "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_upcoming_matches"
LEAGUE_ID = 4714


def get_local_yyyymmdd(now: Optional[dt.datetime] = None) -> str:
    d = now or dt.datetime.now()
    return d.date().isoformat()


def extract_match_date_iso(match: Dict[str, Any]) -> str:
    raw = str(
        match.get("date_event")
        or match.get("dateEvent")
        or match.get("kickoff_at")
        or match.get("kickoffAt")
        or match.get("timestamp")
        or ""
    ).strip()
    m = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else ""


def to_utc_date_from_iso(iso_date: str) -> Optional[dt.date]:
    try:
        y, m, d = [int(v) for v in str(iso_date).split("-")]
        return dt.date(y, m, d)
    except Exception:
        return None


def add_days_to_iso_date(iso_date: str, days: int) -> str:
    base = to_utc_date_from_iso(iso_date)
    if not base:
        return ""
    return (base + dt.timedelta(days=days)).isoformat()


def parse_datetime_maybe(s: Any) -> Optional[dt.datetime]:
    if not s:
        return None
    raw = str(s).strip()
    if not raw:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return dt.datetime.fromisoformat(raw + "T00:00:00+00:00")
    raw = raw.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(raw)
    except Exception:
        return None


def has_meaningful_time(date_like: Any) -> bool:
    if not date_like:
        return False
    s = str(date_like).strip()
    m = re.search(r"[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?", s) or re.match(
        r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s
    )
    if not m:
        return False
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3) or 0)
    return not (hh == 0 and mm == 0 and ss == 0)


def normalize_team_name_for_dedupe(name: Any) -> str:
    cleaned = str(name or "").lower()
    cleaned = re.sub(r"\bsuper rugby\b", "", cleaned)
    cleaned = re.sub(r"\brugby\b", "", cleaned)
    cleaned = re.sub(r"\bnew south wales\b", "", cleaned)
    cleaned = re.sub(r"\bwellington\b", "", cleaned)
    cleaned = re.sub(r"\botago\b", "", cleaned)
    cleaned = re.sub(r"\bqueensland\b", "", cleaned)
    cleaned = re.sub(r"\bact\b", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    aliases = {
        "newsouthwaleswaratahs": "waratahs",
        "wellingtonhurricanes": "hurricanes",
        "hurricanessuperrugby": "hurricanes",
        "otagohighlanders": "highlanders",
        "highlanderssuperrugby": "highlanders",
        "actbrumbies": "brumbies",
        "queenslandreds": "reds",
        "bluessuperrugby": "blues",
        "crusaderssuperrugby": "crusaders",
        "chiefssuperrugby": "chiefs",
    }
    key = re.sub(r"\s+", "", cleaned)
    return aliases.get(key, cleaned)


def get_yyyymmdd_from_any(date_like: Any) -> str:
    if not date_like:
        return ""
    raw = str(date_like).strip()
    m = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    if m:
        return m.group(0)
    d = parse_datetime_maybe(raw)
    if not d:
        return ""
    return d.date().isoformat()


def extract_time_hhmm(time_like: Any) -> str:
    if not time_like:
        return ""
    m = re.search(r"(\d{1,2}):(\d{2})", str(time_like).strip())
    if not m:
        return ""
    hh = m.group(1).zfill(2)
    mm = m.group(2)
    if hh == "00" and mm == "00":
        return ""
    return f"{hh}:{mm}"


def get_kickoff_at_from_match(match: Dict[str, Any], fallback_league_id: Optional[int] = None) -> Optional[str]:
    league_id = int(fallback_league_id or match.get("league_id") or 0)
    canonical_date = get_yyyymmdd_from_any(
        match.get("date_event") or match.get("dateEvent") or match.get("kickoff_at") or match.get("kickoffAt")
    )
    candidates: List[Tuple[Any, str]] = [
        (match.get("kickoff_at"), "kickoff_at"),
        (match.get("kickoffAt"), "kickoffAt"),
        (match.get("date_event"), "date_event"),
        (match.get("dateEvent"), "dateEvent"),
        (match.get("timestamp"), "timestamp"),
        (match.get("strTimestamp"), "strTimestamp"),
    ]
    for candidate, source in candidates:
        if not has_meaningful_time(candidate):
            continue
        raw = str(candidate).strip()
        has_tz = bool(re.search(r"([zZ]|[+\-]\d{2}:\d{2})$", raw))
        is_dt_no_tz = bool(
            re.match(r"^\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?$", raw)
        )
        normalized = raw
        if is_dt_no_tz and not has_tz:
            normalized_base = raw.replace(" ", "T")
            if league_id == LEAGUE_ID and source in ("timestamp", "strTimestamp"):
                normalized = f"{normalized_base}+02:00"
            else:
                normalized = f"{normalized_base}Z"

        if source in ("timestamp", "strTimestamp") and canonical_date:
            ts_date = get_yyyymmdd_from_any(normalized)
            within_one_day = ts_date in {
                canonical_date,
                add_days_to_iso_date(canonical_date, -1),
                add_days_to_iso_date(canonical_date, 1),
            }
            if not within_one_day:
                if league_id != LEAGUE_ID:
                    continue
                hhmm = extract_time_hhmm(normalized)
                if not hhmm:
                    continue
                return f"{canonical_date}T{hhmm}:00+02:00"
            if ts_date and ts_date != canonical_date:
                hhmm = extract_time_hhmm(normalized)
                if hhmm:
                    if league_id == LEAGUE_ID:
                        return f"{canonical_date}T{hhmm}:00+02:00"
                    return f"{canonical_date}T{hhmm}:00Z"
        return normalized
    return None


def has_meaningful_kickoff_for_match(match: Dict[str, Any], league_id: int) -> bool:
    kickoff = get_kickoff_at_from_match(match, league_id)
    if not kickoff:
        return False
    m = re.search(r"(\d{1,2}):(\d{2})", str(kickoff))
    if not m:
        return False
    hh = int(m.group(1))
    mm = int(m.group(2))
    return not (hh == 0 and mm == 0)


def get_match_kickoff_sort_ms(match: Dict[str, Any], league_id: int) -> int:
    kickoff = get_kickoff_at_from_match(match, league_id)
    if kickoff:
        parsed = parse_datetime_maybe(kickoff)
        if parsed:
            return int(parsed.timestamp() * 1000)
    iso = extract_match_date_iso(match)
    if iso:
        p = parse_datetime_maybe(f"{iso}T00:00:00+00:00")
        if p:
            return int(p.timestamp() * 1000)
    return 2**53 - 1


def dedupe_upcoming_matches(matches: List[Dict[str, Any]], league_id: int) -> List[Dict[str, Any]]:
    def side_identity(match: Dict[str, Any], side: str) -> str:
        tid = match.get("home_team_id") if side == "home" else match.get("away_team_id")
        name = match.get("home_team") if side == "home" else match.get("away_team")
        if tid is not None and str(tid).strip() != "":
            return f"id:{str(tid).strip()}"
        return f"name:{normalize_team_name_for_dedupe(name)}"

    def build_pair_key(match: Dict[str, Any]) -> str:
        home = normalize_team_name_for_dedupe(match.get("home_team"))
        away = normalize_team_name_for_dedupe(match.get("away_team"))
        return f"{home}|{away}" if home <= away else f"{away}|{home}"

    def quality(match: Dict[str, Any]) -> int:
        has_kickoff = has_meaningful_kickoff_for_match(match, league_id)
        has_ids = bool(match.get("home_team_id") and match.get("away_team_id"))
        has_event_id = bool(match.get("event_id") or match.get("id"))
        return (4 if has_kickoff else 0) + (2 if has_ids else 0) + (1 if has_event_id else 0)

    by_key: Dict[str, Dict[str, Any]] = {}
    for match in matches or []:
        date_iso = extract_match_date_iso(match) or get_local_yyyymmdd()
        home = side_identity(match, "home")
        away = side_identity(match, "away")
        key = f"{date_iso}|{home}|{away}"
        existing = by_key.get(key)
        if not existing:
            by_key[key] = match
            continue
        qe = quality(existing)
        qc = quality(match)
        if qc > qe:
            by_key[key] = match
        elif qc == qe:
            if get_match_kickoff_sort_ms(match, league_id) < get_match_kickoff_sort_ms(existing, league_id):
                by_key[key] = match

    exact = list(by_key.values())
    by_matchup: Dict[str, Dict[str, Any]] = {}
    max_near_dup_ms = 72 * 60 * 60 * 1000

    for match in exact:
        matchup_key = build_pair_key(match)
        kickoff_ms = get_match_kickoff_sort_ms(match, league_id)
        existing = by_matchup.get(matchup_key)
        if not existing:
            by_matchup[matchup_key] = match
            continue
        existing_ms = get_match_kickoff_sort_ms(existing, league_id)
        near_duplicate = (
            existing_ms < 2**53 - 1
            and kickoff_ms < 2**53 - 1
            and abs(existing_ms - kickoff_ms) <= max_near_dup_ms
        )
        if not near_duplicate:
            by_matchup[f"{matchup_key}|{kickoff_ms}"] = match
            continue
        qe = quality(existing)
        qc = quality(match)
        if qc > qe:
            by_matchup[matchup_key] = match
        elif qc == qe and kickoff_ms < existing_ms:
            by_matchup[matchup_key] = match

    return list(by_matchup.values())


def is_finished_match(match: Dict[str, Any]) -> bool:
    status_text = str(
        match.get("status")
        or match.get("match_status")
        or ((match.get("fixture") or {}).get("status") or {}).get("short")
        or ((match.get("fixture") or {}).get("status") or {}).get("long")
        or ""
    ).upper()
    if not status_text:
        return False
    tokens = ["FT", "AET", "PEN", "FINISHED", "FULL TIME", "COMPLETED"]
    return any(t in status_text for t in tokens)


def has_recorded_result(match: Dict[str, Any]) -> bool:
    hr = match.get("home_score")
    ar = match.get("away_score")
    if hr is None or ar is None:
        return False
    try:
        h = float(hr)
        a = float(ar)
    except Exception:
        return False
    return h > 0 or a > 0


def extract_iso_date_from_raw(raw_value: Any) -> str:
    raw = str(raw_value or "").strip()
    m = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else ""


def is_likely_stale_scored_fixture(match: Dict[str, Any]) -> bool:
    if not has_recorded_result(match):
        return False
    fixture_iso = extract_match_date_iso(match)
    ts_iso = extract_iso_date_from_raw(match.get("timestamp") or match.get("strTimestamp"))
    if not fixture_iso or not ts_iso:
        return False
    f = to_utc_date_from_iso(fixture_iso)
    t = to_utc_date_from_iso(ts_iso)
    if not f or not t:
        return False
    diff_days = abs((f - t).days)
    return diff_days > 2


def get_upcoming_exclusion_reason(match: Dict[str, Any], league_id: int, today_iso: str, now_dt: dt.datetime) -> Optional[str]:
    if not match:
        return "missing_match"
    if is_finished_match(match):
        return "finished_status"
    date_iso = extract_match_date_iso(match)
    is_today_fixture = bool(date_iso) and date_iso == today_iso
    stale_scored_future = is_likely_stale_scored_fixture(match) and bool(date_iso) and date_iso > today_iso
    if has_recorded_result(match) and (not stale_scored_future) and (not is_today_fixture):
        return "has_recorded_result"

    kickoff = get_kickoff_at_from_match(match, league_id)
    if kickoff:
        parsed = parse_datetime_maybe(kickoff)
        if parsed:
            kickoff_date_iso = extract_iso_date_from_raw(kickoff) or ""
            aligned = (not date_iso) or (not kickoff_date_iso) or kickoff_date_iso == date_iso
            if aligned:
                # Frontend rule: keep all same-day fixtures visible until local midnight.
                if date_iso and date_iso == today_iso:
                    return None
                # 5 minute grace
                if parsed.timestamp() * 1000 < (now_dt.timestamp() * 1000 - 5 * 60 * 1000):
                    return "kickoff_in_past"
                return None
    if not date_iso:
        return "missing_date"
    if date_iso < today_iso:
        return "fixture_date_in_past"
    return None


def get_next_match_week(matches: List[Dict[str, Any]], today_iso: str) -> List[Dict[str, Any]]:
    dated = [
        {"match": m, "dateIso": extract_match_date_iso(m)}
        for m in (matches or [])
        if extract_match_date_iso(m) and extract_match_date_iso(m) >= today_iso
    ]
    dated.sort(key=lambda x: x["dateIso"])
    if not dated:
        return []
    cluster = [dated[0]]
    last_iso = dated[0]["dateIso"]
    max_gap_days = 2
    for item in dated[1:]:
        curr_iso = item["dateIso"]
        prev = to_utc_date_from_iso(last_iso)
        curr = to_utc_date_from_iso(curr_iso)
        if not prev or not curr:
            break
        if (curr - prev).days > max_gap_days:
            break
        cluster.append(item)
        last_iso = curr_iso
    return [x["match"] for x in cluster]


@dataclass
class Row:
    id: str
    fixture_date: str
    kickoff_resolved: str
    kickoff_date: str
    home: str
    away: str
    score: str
    timestamp: str
    reason: str


def fetch_matches(league_id: int, limit: int) -> List[Dict[str, Any]]:
    resp = requests.post(ENDPOINT, json={"data": {"league_id": league_id, "limit": limit}}, timeout=30)
    resp.raise_for_status()
    payload = resp.json().get("result", {})
    return payload.get("matches", []) or []


def run(today: Optional[str], league_id: int, limit: int) -> int:
    now_dt = dt.datetime.now(dt.timezone.utc)
    today_iso = today or get_local_yyyymmdd()
    matches = fetch_matches(league_id, limit)
    deduped = dedupe_upcoming_matches(matches, league_id)

    rows: List[Row] = []
    for m in deduped:
        reason = get_upcoming_exclusion_reason(m, league_id, today_iso, now_dt) or "included"
        kickoff = get_kickoff_at_from_match(m, league_id) or ""
        rows.append(
            Row(
                id=str(m.get("id") or m.get("event_id") or ""),
                fixture_date=extract_match_date_iso(m),
                kickoff_resolved=kickoff,
                kickoff_date=extract_iso_date_from_raw(kickoff),
                home=str(m.get("home_team") or ""),
                away=str(m.get("away_team") or ""),
                score=f"{m.get('home_score') if m.get('home_score') is not None else '-'}-{m.get('away_score') if m.get('away_score') is not None else '-'}",
                timestamp=str(m.get("timestamp") or ""),
                reason=reason,
            )
        )

    kept = [r for r in rows if r.reason == "included"]
    block = get_next_match_week(
        [
            m
            for m in deduped
            if (get_upcoming_exclusion_reason(m, league_id, today_iso, now_dt) is None)
        ],
        today_iso,
    )
    block_ids = {str(m.get("id") or m.get("event_id") or "") for m in block}

    print(f"[diagnose] league={league_id} today={today_iso} raw={len(matches)} deduped={len(deduped)} kept={len(kept)} block={len(block)}")

    reason_counts: Dict[str, int] = {}
    for r in rows:
        reason_counts[r.reason] = reason_counts.get(r.reason, 0) + 1
    print("[diagnose] reason counts:", json.dumps(reason_counts, indent=2))

    print("\n[diagnose] matches on 6/7 with UI-derived fields")
    target_dates = {"2026-03-06", "2026-03-07"}
    for r in rows:
        if r.fixture_date not in target_dates:
            continue
        in_block = "yes" if r.id in block_ids else "no"
        kickoff_note = ""
        if r.kickoff_resolved and r.kickoff_date and r.kickoff_date != r.fixture_date:
            kickoff_note = " kickoff_date!=fixture_date"
        print(
            f"- {r.fixture_date} | {r.home} vs {r.away} | id={r.id} | score={r.score} | "
            f"timestamp={r.timestamp} | kickoff={r.kickoff_resolved or '-'} | "
            f"reason={r.reason} | in_block={in_block}{kickoff_note}"
        )

    print("\n[diagnose] full deduped table")
    for r in sorted(rows, key=lambda x: (x.fixture_date, x.home, x.away)):
        in_block = "yes" if r.id in block_ids else "no"
        print(
            f"{r.fixture_date:10} | {r.home[:22]:22} vs {r.away[:22]:22} | "
            f"score={r.score:7} | reason={r.reason:24} | in_block={in_block:3} | kickoff={r.kickoff_resolved or '-'}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Six Nations UI date/kickoff logic.")
    parser.add_argument("--today", default=None, help="Override local YYYY-MM-DD for deterministic analysis.")
    parser.add_argument("--league-id", type=int, default=LEAGUE_ID, help="League ID (default: 4714).")
    parser.add_argument("--limit", type=int, default=50, help="Fetch limit (default: 50).")
    args = parser.parse_args()
    return run(today=args.today, league_id=args.league_id, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())

