#!/usr/bin/env python3
"""
Print a league-by-league delta table from a MAZ MAXED V3 report JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def load_rows(report_path: Path) -> List[Tuple[int, str, float, float, float, str]]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    leagues: Dict[str, Any] = data.get("leagues", {})
    rows: List[Tuple[int, str, float, float, float, str]] = []
    for lid_s, payload in leagues.items():
        if payload.get("status") != "tested":
            continue
        deltas = payload.get("deltas", {})
        rows.append(
            (
                int(lid_s),
                str(payload.get("name", "")),
                _as_float(deltas.get("winner_accuracy_gain")),
                _as_float(deltas.get("overall_mae_reduction")),
                _as_float(deltas.get("brier_reduction")),
                str(payload.get("winner", "")),
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Print V3 per-league deltas table.")
    parser.add_argument(
        "--report",
        required=True,
        help="Path to maz_maxed_v3_report_*.json",
    )
    parser.add_argument(
        "--sort-by",
        choices=["winner_gain", "mae_reduction", "brier_reduction", "league_id"],
        default="winner_gain",
    )
    parser.add_argument("--ascending", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")

    rows = load_rows(report_path)
    if not rows:
        print("No tested leagues found in report.")
        return

    key_map = {
        "winner_gain": 2,
        "mae_reduction": 3,
        "brier_reduction": 4,
        "league_id": 0,
    }
    rows.sort(key=lambda r: r[key_map[args.sort_by]], reverse=not args.ascending)

    print("league_id | league_name                       | win_gain | mae_reduction | brier_reduction | winner_mode")
    print("-" * 108)
    for lid, name, win_gain, mae_red, brier_red, mode in rows:
        print(
            f"{lid:7d} | {name[:32]:32s} | "
            f"{win_gain:+.4f} | {mae_red:+.4f} | {brier_red:+.4f} | {mode}"
        )

    avg_win = sum(r[2] for r in rows) / len(rows)
    avg_mae = sum(r[3] for r in rows) / len(rows)
    avg_brier = sum(r[4] for r in rows) / len(rows)
    print("-" * 108)
    print(
        f"{'AVG':>7s} | {'ALL':32s} | "
        f"{avg_win:+.4f} | {avg_mae:+.4f} | {avg_brier:+.4f} |"
    )


if __name__ == "__main__":
    main()

