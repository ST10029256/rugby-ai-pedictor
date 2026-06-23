#!/usr/bin/env python3
"""
Build persistent logo assets for every team + league.

For each of the configured leagues this script:
  1. Resolves the best available logo for every team
     (Highlightly match data first, then the curated STATIC_TEAM_LOGOS map).
  2. Resolves the league logo (Highlightly deterministic URL).
  3. Uploads each image ONCE to Firebase Storage (immutable, CDN-cached) so the
     frontend loads logos straight from the CDN -- never through Cloud Functions
     and never hotlinked from third parties at request time.
  4. Persists the resulting public URLs into `team_logo` / `league_logo` tables
     in the SQLite DB, so they ship inside data.sqlite with every deploy and the
     standings function only has to read a column.

Idempotent: an image that already exists in Storage is not re-uploaded unless
`--force` is given, so daily pipeline runs are cheap.

Usage (pipeline):
    python scripts/build_logo_assets.py --db data.sqlite \
        --project-id rugby-ai-61fd0 --bucket rugby-ai-61fd0.firebasestorage.app

Usage (local, no Storage creds -- stores source URLs directly for testing):
    python scripts/build_logo_assets.py --db data.sqlite --no-upload
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests

# --- make project imports work regardless of CWD ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
for p in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "rugby-ai-predictor")):
    if p not in sys.path:
        sys.path.insert(0, p)

from prediction.config import STATIC_TEAM_LOGOS  # noqa: E402
from prediction.highlightly_client import HighlightlyRugbyAPI  # noqa: E402
from prediction.highlightly_leagues import (  # noqa: E402
    HIGHLIGHTLY_LEAGUE_MAPPINGS,
    season_candidates,
)

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("build_logo_assets")

UA = "Mozilla/5.0 (rugby-ai logo fetcher)"
CACHE_CONTROL = "public, max-age=31536000, immutable"

CONTENT_TYPE_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/svg+xml": "svg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _norm(s: str) -> str:
    s2 = (s or "").strip().lower()
    s2 = re.sub(r"[^a-z0-9]+", " ", s2)
    return re.sub(r"\s+", " ", s2).strip()


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_logo (
            highlightly_team_id INTEGER PRIMARY KEY,
            name TEXT,
            league_id INTEGER,
            logo_url TEXT,
            source TEXT,
            source_url TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_logo (
            highlightly_league_id INTEGER PRIMARY KEY,
            our_league_id INTEGER,
            name TEXT,
            logo_url TEXT,
            source_url TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()


def download(url: str) -> Optional[Tuple[bytes, str]]:
    """Return (bytes, content_type) or None."""
    try:
        resp = requests.get(url, headers={"User-Agent": UA, "Referer": "https://highlightly.net/"}, timeout=25)
        if resp.status_code == 200 and resp.content and resp.headers.get("Content-Type", "").startswith("image"):
            return resp.content, resp.headers["Content-Type"].split(";")[0].strip()
        logger.warning("Download skipped (%s, ct=%s): %s", resp.status_code, resp.headers.get("Content-Type"), url)
    except Exception as exc:
        logger.warning("Download failed for %s: %s", url, exc)
    return None


class Uploader:
    """Wraps Firebase Storage upload; falls back to source URLs when --no-upload."""

    def __init__(self, project_id: str, bucket_name: str, enabled: bool, force: bool):
        self.enabled = enabled
        self.force = force
        self.bucket_name = bucket_name
        self.bucket = None
        if enabled:
            from google.cloud import storage  # type: ignore

            client = storage.Client(project=project_id)
            self.bucket = client.bucket(bucket_name)

    def public_url(self, path: str) -> str:
        enc = urllib.parse.quote(path, safe="")
        return f"https://firebasestorage.googleapis.com/v0/b/{self.bucket_name}/o/{enc}?alt=media"

    def upload(self, path_no_ext: str, source_url: str) -> Optional[str]:
        """Upload the image at source_url to <path_no_ext>.<ext>; return public URL."""
        if not self.enabled:
            # Local/testing mode: persist the source URL directly so standings still works.
            return source_url

        # Determine extension cheaply from the source URL suffix; fall back after download.
        suffix = os.path.splitext(urllib.parse.urlparse(source_url).path)[1].lstrip(".").lower()
        guessed_ext = suffix if suffix in {"png", "jpg", "jpeg", "svg", "webp", "gif"} else None

        if guessed_ext and not self.force:
            existing = self.bucket.blob(f"{path_no_ext}.{guessed_ext}")
            if existing.exists():
                return self.public_url(existing.name)

        fetched = download(source_url)
        if not fetched:
            return None
        data, content_type = fetched
        ext = CONTENT_TYPE_EXT.get(content_type, guessed_ext or "png")
        blob_path = f"{path_no_ext}.{ext}"
        blob = self.bucket.blob(blob_path)
        if blob.exists() and not self.force:
            return self.public_url(blob_path)
        blob.cache_control = CACHE_CONTROL
        blob.upload_from_string(data, content_type=content_type)
        logger.info("Uploaded %s (%d bytes)", blob_path, len(data))
        return self.public_url(blob_path)


def collect_teams(api: HighlightlyRugbyAPI, hl_id: int, our_id: int) -> Dict[int, Tuple[str, Optional[str]]]:
    """{highlightly_team_id: (name, highlightly_logo_url_or_None)} across recent seasons."""
    teams: Dict[int, Tuple[str, Optional[str]]] = {}
    today = datetime.now(timezone.utc)
    seasons = season_candidates(today, our_id, include_history=True)[:4]
    for season in seasons:
        offset = 0
        for _ in range(8):  # up to 800 matches/season
            try:
                resp = api.get_matches(league_id=hl_id, season=int(season), limit=100, offset=offset)
            except Exception as exc:
                logger.warning("get_matches failed (league=%s season=%s): %s", hl_id, season, exc)
                break
            rows = (resp or {}).get("data") or []
            if not rows:
                break
            for row in rows:
                for side in ("homeTeam", "awayTeam"):
                    t = row.get(side) or {}
                    tid = t.get("id")
                    if tid is None:
                        continue
                    name, existing_logo = teams.get(tid, ("", None))
                    name = name or (t.get("name") or "")
                    logo = existing_logo or (t.get("logo") or None)
                    teams[tid] = (name, logo)
            if len(rows) < 100:
                break
            offset += 100
    return teams


def main() -> int:
    ap = argparse.ArgumentParser(description="Build team/league logo assets into Storage + SQLite")
    ap.add_argument("--db", default="data.sqlite")
    ap.add_argument("--project-id", default="rugby-ai-61fd0")
    ap.add_argument("--bucket", default="rugby-ai-61fd0.firebasestorage.app")
    ap.add_argument("--no-upload", action="store_true", help="Skip Storage upload; store source URLs (local testing)")
    ap.add_argument("--force", action="store_true", help="Re-upload even if the blob already exists")
    args = ap.parse_args()

    api_key = (os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip()
    if not api_key:
        logger.error("HIGHLIGHTLY_API_KEY is required")
        return 2
    if not os.path.exists(args.db):
        logger.error("DB not found: %s", args.db)
        return 2

    api = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=False)
    uploader = Uploader(args.project_id, args.bucket, enabled=not args.no_upload, force=args.force)
    conn = sqlite3.connect(args.db)
    ensure_tables(conn)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    league_rows = team_rows = team_missing = 0

    for our_id, (league_name, hl_id) in HIGHLIGHTLY_LEAGUE_MAPPINGS.items():
        logger.info("=== %s (our=%s hl=%s) ===", league_name, our_id, hl_id)

        # --- league logo (deterministic Highlightly URL) ---
        league_src = f"https://highlightly.net/rugby/images/leagues/{hl_id}.png"
        league_url = uploader.upload(f"logos/leagues/{hl_id}", league_src)
        if league_url:
            conn.execute(
                """
                INSERT INTO league_logo (highlightly_league_id, our_league_id, name, logo_url, source_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(highlightly_league_id) DO UPDATE SET
                    our_league_id=excluded.our_league_id, name=excluded.name,
                    logo_url=excluded.logo_url, source_url=excluded.source_url, updated_at=excluded.updated_at
                """,
                (hl_id, our_id, league_name, league_url, league_src, now),
            )
            league_rows += 1

        # --- team logos ---
        teams = collect_teams(api, hl_id, our_id)
        for tid, (name, hl_logo) in teams.items():
            src = hl_logo
            source = "highlightly"
            if not src:
                src = STATIC_TEAM_LOGOS.get(_norm(name))
                source = "static"
            if not src:
                team_missing += 1
                logger.info("  no logo for team '%s' (id=%s) -- will fall back at runtime", name, tid)
                continue
            public = uploader.upload(f"logos/teams/{tid}", src)
            if not public:
                team_missing += 1
                continue
            conn.execute(
                """
                INSERT INTO team_logo (highlightly_team_id, name, league_id, logo_url, source, source_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(highlightly_team_id) DO UPDATE SET
                    name=excluded.name, league_id=excluded.league_id, logo_url=excluded.logo_url,
                    source=excluded.source, source_url=excluded.source_url, updated_at=excluded.updated_at
                """,
                (tid, name, our_id, public, source, src, now),
            )
            team_rows += 1
        conn.commit()

    conn.commit()
    conn.close()
    logger.info("DONE: league_logos=%d team_logos=%d teams_without_logo=%d", league_rows, team_rows, team_missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
