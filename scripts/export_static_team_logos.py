#!/usr/bin/env python3
"""Export STATIC_TEAM_LOGOS from Python config to frontend JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PREDICTOR_ROOT = PROJECT_ROOT / "rugby-ai-predictor"
for path in (PROJECT_ROOT, RUGBY_PREDICTOR_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prediction.config import STATIC_TEAM_LOGOS  # noqa: E402

OUT = PROJECT_ROOT / "public" / "src" / "utils" / "staticTeamLogos.json"


def main() -> int:
    payload = dict(sorted(STATIC_TEAM_LOGOS.items(), key=lambda kv: kv[0]))
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload)} logos -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
