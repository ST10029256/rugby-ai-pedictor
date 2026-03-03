#!/usr/bin/env python3
"""
Publish V4 evaluation metrics into Firestore league_metrics.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

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


def publish(report_path: str, project_id: str, prod_report_path: str) -> int:
    report_file = Path(report_path)
    if not report_file.exists():
        raise FileNotFoundError(f"V4 report not found: {report_file}")

    try:
        get_app(project_id)
    except ValueError:
        initialize_app(options={"projectId": project_id}, name=project_id)

    db = firestore.client(app=get_app(project_id))
    report = json.loads(report_file.read_text(encoding="utf-8"))
    leagues: Dict[str, Dict[str, Any]] = report.get("leagues", {})
    prod_leagues: Dict[str, Dict[str, Any]] = {}
    prod_file = Path(prod_report_path)
    if prod_file.exists():
        try:
            prod_report = json.loads(prod_file.read_text(encoding="utf-8"))
            prod_leagues = prod_report.get("leagues", {}) or {}
        except Exception:
            prod_leagues = {}

    updated = 0
    generated_at = report.get("generated_at") or datetime.utcnow().isoformat()
    source_report = str(report_file).replace("\\", "/")

    for league_id, league_data in leagues.items():
        if league_data.get("status") != "tested":
            continue

        metrics = league_data.get("metrics", {})
        winner_accuracy = float(metrics.get("winner_accuracy", 0.0))
        accuracy_pct = round(winner_accuracy * 100.0, 1)
        # Keep eval metrics honest (80/20), but display full production trained rows
        # when available so UI doesn't misleadingly show "80 games trained".
        prod_entry = prod_leagues.get(str(league_id), {}) if prod_leagues else {}
        training_games = int(
            prod_entry.get("train_rows")
            or league_data.get("total_rows")
            or league_data.get("train_rows")
            or 0
        )
        overall_mae = float(metrics.get("overall_mae", 0.0))

        payload = {
            "league_id": int(league_id),
            "league_name": league_data.get("name", f"League {league_id}"),
            "accuracy": accuracy_pct,
            "training_games": training_games,
            "ai_rating": _ai_rating_from_accuracy(accuracy_pct),
            "overall_mae": round(overall_mae, 2),
            "trained_at": generated_at,
            "model_type": "v4",
            "model_family": "v4",
            "model_channel": "eval_80_20",
            "performance": metrics,
            "v4_meta": {
                "mode": league_data.get("mode", "walk_forward"),
                "eval_train_rows": league_data.get("train_rows"),
                "eval_test_rows": league_data.get("test_rows"),
                "ensemble_size": league_data.get("ensemble_size"),
                "global_pretrained": league_data.get("global_pretrained"),
                "source_report": source_report,
                "source_prod_report": str(prod_file).replace("\\", "/") if prod_file.exists() else None,
            },
            "last_updated": generated_at,
        }
        db.collection("league_metrics").document(str(league_id)).set(payload, merge=True)
        updated += 1

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish V4 metrics to Firestore")
    parser.add_argument("--report", default="artifacts/maz_maxed_v4_metrics_latest.json", help="Path to V4 walk-forward metrics report")
    parser.add_argument(
        "--prod-report",
        default="artifacts/maz_maxed_v4_prod_latest.json",
        help="Path to V4 production report for full trained game counts",
    )
    parser.add_argument("--project-id", default="rugby-ai-61fd0", help="Firebase project ID")
    args = parser.parse_args()

    updated = publish(args.report, args.project_id, args.prod_report)
    print(f"[OK] Updated {updated} league_metrics docs from V4 report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

