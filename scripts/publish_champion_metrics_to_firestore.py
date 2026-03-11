#!/usr/bin/env python3
"""
Publish champion metrics into Firestore league_metrics.

This selects the winning family per league from the champion map and writes
the corresponding evaluation metrics so the UI matches the live prediction
routing policy.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from firebase_admin import firestore, get_app, initialize_app


def _ai_rating_from_accuracy(accuracy_pct: float) -> str:
    if accuracy_pct >= 80:
        return "9/10"
    if accuracy_pct >= 75:
        return "8/10"
    if accuracy_pct >= 70:
        return "7/10"
    if accuracy_pct >= 65:
        return "6/10"
    if accuracy_pct >= 60:
        return "5/10"
    return "4/10"


def _load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pick_entries(
    league_id: str,
    champions: Dict[str, Any],
    v4_eval: Dict[str, Any],
    v5_eval: Dict[str, Any],
    v4_prod: Dict[str, Any],
    v5_prod: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    chosen_family = str(
        (champions.get("model_family_by_league") or {}).get(str(league_id), "v5")
    ).strip().lower()
    if chosen_family == "v4":
        return chosen_family, (v4_eval.get("leagues") or {}).get(str(league_id), {}), (v4_prod.get("leagues") or {}).get(str(league_id), {})
    return chosen_family, (v5_eval.get("leagues") or {}).get(str(league_id), {}), (v5_prod.get("leagues") or {}).get(str(league_id), {})


def publish(
    *,
    champion_file: str,
    v4_report: str,
    v5_report: str,
    v4_prod_report: str,
    v5_prod_report: str,
    project_id: str,
    model_channel: str = "prod_100",
) -> int:
    champions = _load_json(champion_file)
    v4_eval = _load_json(v4_report)
    v5_eval = _load_json(v5_report)
    v4_prod = _load_json(v4_prod_report) if Path(v4_prod_report).exists() else {"leagues": {}}
    v5_prod = _load_json(v5_prod_report) if Path(v5_prod_report).exists() else {"leagues": {}}

    try:
        get_app(project_id)
    except ValueError:
        initialize_app(options={"projectId": project_id}, name=project_id)
    db = firestore.client(app=get_app(project_id))

    generated_at = datetime.utcnow().isoformat()
    updated = 0
    league_ids = sorted((champions.get("model_family_by_league") or {}).keys(), key=int)

    for league_id in league_ids:
        chosen_family, eval_entry, prod_entry = _pick_entries(
            league_id,
            champions,
            v4_eval,
            v5_eval,
            v4_prod,
            v5_prod,
        )
        if not eval_entry or eval_entry.get("status") != "tested":
            continue
        metrics = eval_entry.get("metrics") or {}
        winner_accuracy = float(metrics.get("winner_accuracy", 0.0))
        accuracy_pct = round(winner_accuracy * 100.0, 1)
        training_games = int(
            prod_entry.get("train_rows")
            or eval_entry.get("total_rows")
            or eval_entry.get("train_rows")
            or 0
        )
        overall_mae = float(metrics.get("overall_mae", 0.0))
        champion_detail = (champions.get("league_details") or {}).get(str(league_id), {})

        payload = {
            "league_id": int(league_id),
            "league_name": eval_entry.get("name", f"League {league_id}"),
            "accuracy": accuracy_pct,
            "training_games": training_games,
            "ai_rating": _ai_rating_from_accuracy(accuracy_pct),
            "overall_mae": round(overall_mae, 2),
            "trained_at": generated_at,
            "model_type": "champion",
            "model_family": "champion",
            "model_channel": model_channel,
            "performance": metrics,
            "champion_meta": {
                "chosen_family": chosen_family,
                "selection_basis": champions.get("selection_basis"),
                "default_model_family": champions.get("default_model_family"),
                "score": champion_detail.get("score"),
                "deltas": champion_detail.get("deltas"),
                "mode": eval_entry.get("mode", "walk_forward"),
                "eval_train_rows": eval_entry.get("train_rows"),
                "eval_test_rows": eval_entry.get("test_rows"),
                "ensemble_size": eval_entry.get("ensemble_size"),
                "global_pretrained": eval_entry.get("global_pretrained"),
                "source_eval_report": str(v4_report if chosen_family == "v4" else v5_report).replace("\\", "/"),
                "source_prod_report": str(v4_prod_report if chosen_family == "v4" else v5_prod_report).replace("\\", "/"),
                "champion_file": str(champion_file).replace("\\", "/"),
            },
            "last_updated": generated_at,
        }
        db.collection("league_metrics").document(str(league_id)).set(payload, merge=True)
        updated += 1

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish champion league metrics to Firestore")
    parser.add_argument("--champion-file", default="rugby-ai-predictor/league_model_champions.json")
    parser.add_argument("--v4-report", default="artifacts/maz_maxed_v4_metrics_latest.json")
    parser.add_argument("--v5-report", default="artifacts/maz_maxed_v5_metrics_latest.json")
    parser.add_argument("--v4-prod-report", default="artifacts/maz_maxed_v4_prod_latest.json")
    parser.add_argument("--v5-prod-report", default="artifacts/maz_maxed_v5_prod_latest.json")
    parser.add_argument("--project-id", default="rugby-ai-61fd0")
    parser.add_argument("--model-channel", default="prod_100")
    args = parser.parse_args()

    updated = publish(
        champion_file=args.champion_file,
        v4_report=args.v4_report,
        v5_report=args.v5_report,
        v4_prod_report=args.v4_prod_report,
        v5_prod_report=args.v5_prod_report,
        project_id=args.project_id,
        model_channel=args.model_channel,
    )
    print(f"[OK] Updated {updated} league_metrics docs from champion policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
