#!/usr/bin/env python3
"""
Select the best model family per league from evaluation reports.

The goal is not to blindly force one family everywhere, but to choose the
strongest champion per league based on unseen walk-forward performance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple


def _metric_value(league_entry: Dict[str, Any], metric: str) -> float:
    metrics = league_entry.get("metrics") or {}
    return float(metrics.get(metric, 0.0))


def _champion_score(v4_entry: Dict[str, Any], v5_entry: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    v4_win = _metric_value(v4_entry, "winner_accuracy")
    v5_win = _metric_value(v5_entry, "winner_accuracy")
    v4_mae = _metric_value(v4_entry, "overall_mae")
    v5_mae = _metric_value(v5_entry, "overall_mae")
    v4_brier = _metric_value(v4_entry, "brier_winner")
    v5_brier = _metric_value(v5_entry, "brier_winner")
    v4_ece = _metric_value(v4_entry, "ece_winner")
    v5_ece = _metric_value(v5_entry, "ece_winner")

    deltas = {
        "winner_accuracy": v5_win - v4_win,
        "overall_mae": v4_mae - v5_mae,
        "brier_winner": v4_brier - v5_brier,
        "ece_winner": v4_ece - v5_ece,
    }

    score = 0.0
    score += 4.0 * deltas["winner_accuracy"]
    score += 1.5 * deltas["overall_mae"]
    score += 1.0 * deltas["brier_winner"]
    score += 0.75 * deltas["ece_winner"]

    # Guardrails: do not choose V5 when probability quality regresses hard and
    # winner gain is tiny, or when accuracy clearly drops.
    if deltas["winner_accuracy"] < -0.01:
        chosen = "v4"
    elif deltas["winner_accuracy"] < 0.01 and (
        deltas["overall_mae"] < 0.0 or deltas["brier_winner"] < -0.01 or deltas["ece_winner"] < -0.01
    ):
        chosen = "v4"
    else:
        chosen = "v5" if score > 0.0 else "v4"

    return chosen, {
        "score": score,
        "deltas": deltas,
        "v4_metrics": v4_entry.get("metrics") or {},
        "v5_metrics": v5_entry.get("metrics") or {},
    }


def build_champions(v4_report: Dict[str, Any], v5_report: Dict[str, Any]) -> Dict[str, Any]:
    v4_leagues = v4_report.get("leagues") or {}
    v5_leagues = v5_report.get("leagues") or {}
    league_ids = sorted(set(v4_leagues) & set(v5_leagues), key=int)

    result: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat(),
        "default_model_family": "v5",
        "selection_basis": "walk_forward_unseen_games",
        "policy_notes": [
            "V5 is the default champion when it clearly improves unseen-game performance.",
            "Fallback to V4 for leagues where V5 regresses materially or only ties on accuracy while worsening probability quality.",
        ],
        "model_family_by_league": {},
        "league_details": {},
    }

    for lid in league_ids:
        v4_entry = v4_leagues.get(lid) or {}
        v5_entry = v5_leagues.get(lid) or {}
        if v4_entry.get("status") != "tested" or v5_entry.get("status") != "tested":
            continue
        chosen, details = _champion_score(v4_entry, v5_entry)
        result["model_family_by_league"][str(lid)] = chosen
        result["league_details"][str(lid)] = {
            "name": v5_entry.get("name") or v4_entry.get("name") or f"League {lid}",
            "chosen_family": chosen,
            **details,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Select the best model family per league")
    parser.add_argument("--v4-report", default="artifacts/maz_maxed_v4_metrics_latest.json", help="Path to V4 evaluation report")
    parser.add_argument("--v5-report", default="artifacts/maz_maxed_v5_metrics_latest.json", help="Path to V5 evaluation report")
    parser.add_argument(
        "--output",
        default="rugby-ai-predictor/league_model_champions.json",
        help="Path to save the league champion policy JSON",
    )
    parser.add_argument(
        "--artifacts-copy",
        default="artifacts/league_model_champions.json",
        help="Optional second output for artifacts/debugging",
    )
    args = parser.parse_args()

    v4 = json.loads(Path(args.v4_report).read_text(encoding="utf-8"))
    v5 = json.loads(Path(args.v5_report).read_text(encoding="utf-8"))
    champions = build_champions(v4, v5)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(champions, indent=2), encoding="utf-8")

    if args.artifacts_copy:
        artifacts_path = Path(args.artifacts_copy)
        artifacts_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts_path.write_text(json.dumps(champions, indent=2), encoding="utf-8")

    print(f"[OK] Wrote league champion policy to {output_path}")
    for lid, family in sorted(champions["model_family_by_league"].items(), key=lambda x: int(x[0])):
        name = champions["league_details"][lid]["name"]
        print(f"  {lid}: {name} -> {family}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
