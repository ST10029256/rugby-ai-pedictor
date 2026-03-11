"""
One-time backfill for V5 prediction snapshots across all completed matches.

Usage:
  python backfill_v5_predictions_all_games.py --db data.sqlite
  python backfill_v5_predictions_all_games.py --db data.sqlite --league-id 4446
"""

from __future__ import annotations

import os

from backfill_v4_predictions_all_games import main as _backfill_main


def main() -> None:
    os.environ["LIVE_MODEL_FAMILY"] = "v5"
    _backfill_main()


if __name__ == "__main__":
    main()
