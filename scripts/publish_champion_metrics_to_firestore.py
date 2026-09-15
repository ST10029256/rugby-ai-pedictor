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
import sqlite3
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


def _completed_games_by_league(db_path: str) -> Dict[str, int]:
    path = Path(db_path)
    if not path.exists():
        return {}
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            """
            SELECT league_id, COUNT(*)
            FROM event
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
            GROUP BY league_id
            """
        ).fetchall()
    finally:
        conn.close()
    return {str(int(league_id)): int(count) for league_id, count in rows}


def _model_meta_exists(league_id: str, family: str) -> bool:
    return Path(f"artifacts/league_{league_id}_model_maz_maxed_{family}_meta.pkl").exists()


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
    completed_games = _completed_games_by_league("data.sqlite")
    if not completed_games:
        completed_games = _completed_games_by_league("rugby-ai-predictor/data.sqlite")

    for league_id in league_ids:
        chosen_family, eval_entry, prod_entry = _pick_entries(
            league_id,
            champions,
            v4_eval,
            v5_eval,
            v4_prod,
            v5_prod,
        )
        tested = bool(eval_entry and eval_entry.get("status") == "tested")
        trained_only = bool(prod_entry and prod_entry.get("status") == "trained_only")
        if not tested and not trained_only and not _model_meta_exists(league_id, chosen_family):
            continue
        metrics = (eval_entry.get("metrics") or {}) if tested else {}
        winner_accuracy = float(metrics.get("winner_accuracy", 0.0))
        accuracy_pct = round(winner_accuracy * 100.0, 1) if tested else 0.0
        own_completed = int(completed_games.get(str(league_id), 0))
        training_games = int(
            own_completed
            or prod_entry.get("train_rows")
            or eval_entry.get("total_rows")
            or eval_entry.get("train_rows")
            or 0
        )
        if training_games <= 0:
            continue
        overall_mae = float(metrics.get("overall_mae", 0.0)) if tested else 0.0
        champion_detail = (champions.get("league_details") or {}).get(str(league_id), {})
        source_entry = eval_entry if tested else (prod_entry or {})
        league_name = (
            source_entry.get("name")
            or champion_detail.get("name")
            or {
                "5481": "Investec Champions Cup",
                "5482": "EPCR Challenge Cup",
                "5483": "Women's Rugby World Cup",
                "5484": "Women's Six Nations",
                "5485": "WXV 1",
                "5486": "WXV 2",
                "5487": "WXV 3",
            }.get(str(league_id), f"League {league_id}")
        )

        payload = {
            "league_id": int(league_id),
            "league_name": league_name,
            "training_games": training_games,
            "trained_at": generated_at,
            "model_type": "champion",
            "model_family": "champion",
            "model_channel": model_channel,
            "champion_meta": {
                "chosen_family": chosen_family,
                "selection_basis": champions.get("selection_basis"),
                "default_model_family": champions.get("default_model_family"),
                "score": champion_detail.get("score"),
                "deltas": champion_detail.get("deltas"),
                "mode": source_entry.get("mode") or ("walk_forward" if tested else "train_all_completed"),
                "eval_train_rows": eval_entry.get("train_rows"),
                "eval_test_rows": eval_entry.get("test_rows"),
                "own_completed_games": own_completed,
                "ensemble_size": source_entry.get("ensemble_size"),
                "global_pretrained": source_entry.get("global_pretrained"),
                "source_eval_report": str(v4_report if chosen_family == "v4" else v5_report).replace("\\", "/"),
                "source_prod_report": str(v4_prod_report if chosen_family == "v4" else v5_prod_report).replace("\\", "/"),
                "champion_file": str(champion_file).replace("\\", "/"),
            },
            "last_updated": generated_at,
        }
        if tested:
            payload["accuracy"] = accuracy_pct
            payload["ai_rating"] = _ai_rating_from_accuracy(accuracy_pct)
            payload["overall_mae"] = round(overall_mae, 2)
            payload["performance"] = metrics
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
