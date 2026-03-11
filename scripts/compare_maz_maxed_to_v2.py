#!/usr/bin/env python3
"""
Compare original MAZ MAXED artifacts to MAZ MAXED V2 artifacts.

Usage:
  python scripts/compare_maz_maxed_to_v2.py
  python scripts/compare_maz_maxed_to_v2.py --league-id 5069
  python scripts/compare_maz_maxed_to_v2.py --save-json artifacts/maz_vs_v2_compare.json
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


LEAGUE_FILE_RE = re.compile(r"^league_(\d+)_model_maz_maxed(?:_v2)?(?:_.*)?\.pkl$")


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _load_pickle(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("rb") as f:
            # Suppress known XGBoost legacy serialization warning while loading historic artifacts.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*If you are loading a serialized model.*",
                    category=UserWarning,
                )
                obj = pickle.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_metrics(obj: Dict[str, Any]) -> Dict[str, Optional[float]]:
    m = obj.get("metrics_unseen", {}) or {}
    b = obj.get("baseline_unseen", {}) or {}

    winner_acc = _safe_float(m.get("winner_accuracy", m.get("accuracy")))
    outcome_acc = _safe_float(m.get("outcome_accuracy", m.get("accuracy")))
    overall_mae = _safe_float(m.get("overall_mae"))
    rows = _safe_float(m.get("rows"))

    base_winner = _safe_float(b.get("winner_accuracy", b.get("accuracy")))
    base_outcome = _safe_float(b.get("outcome_accuracy", b.get("accuracy")))
    base_overall_mae = _safe_float(b.get("overall_mae"))

    return {
        "winner_accuracy": winner_acc,
        "outcome_accuracy": outcome_acc,
        "overall_mae": overall_mae,
        "rows": rows,
        "vs_baseline_winner_accuracy": (
            None if winner_acc is None or base_winner is None else winner_acc - base_winner
        ),
        "vs_baseline_outcome_accuracy": (
            None if outcome_acc is None or base_outcome is None else outcome_acc - base_outcome
        ),
        "vs_baseline_overall_mae": (
            None if overall_mae is None or base_overall_mae is None else overall_mae - base_overall_mae
        ),
    }


def _pick_original(files: List[Path]) -> Optional[Path]:
    if not files:
        return None
    exact = [p for p in files if p.name.endswith("_model_maz_maxed.pkl")]
    if exact:
        return sorted(exact, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _pick_v2(files: List[Path]) -> Optional[Path]:
    if not files:
        return None
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _format(value: Optional[float], pct: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3%}" if pct else f"{value:.4f}"


def _delta(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None:
        return None
    return new - old


def _discover_pairs(artifacts_dir: Path) -> Dict[int, Tuple[Optional[Path], Optional[Path]]]:
    originals: Dict[int, List[Path]] = {}
    v2s: Dict[int, List[Path]] = {}

    for p in artifacts_dir.glob("league_*_model_maz_maxed*.pkl"):
        m = LEAGUE_FILE_RE.match(p.name)
        if not m:
            continue
        league_id = int(m.group(1))
        if "_v2_" in p.name:
            v2s.setdefault(league_id, []).append(p)
        else:
            originals.setdefault(league_id, []).append(p)

    all_ids = sorted(set(originals) | set(v2s))
    pairs: Dict[int, Tuple[Optional[Path], Optional[Path]]] = {}
    for league_id in all_ids:
        pairs[league_id] = (_pick_original(originals.get(league_id, [])), _pick_v2(v2s.get(league_id, [])))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare MAZ MAXED original vs V2 artifacts.")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts directory path.")
    parser.add_argument("--league-id", type=int, help="Only compare one league id.")
    parser.add_argument("--save-json", help="Optional path to save full comparison JSON.")
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.exists():
        raise SystemExit(f"Artifacts directory not found: {artifacts_dir}")

    pairs = _discover_pairs(artifacts_dir)
    if args.league_id is not None:
        pairs = {args.league_id: pairs.get(args.league_id, (None, None))}

    results: List[Dict[str, Any]] = []
    print("\n=== MAZ MAXED vs MAZ MAXED V2 ===")
    for league_id, (orig_path, v2_path) in pairs.items():
        if orig_path is None or v2_path is None:
            missing = "original" if orig_path is None else "v2"
            print(f"[league {league_id}] skipped (missing {missing} artifact)")
            continue

        orig_obj = _load_pickle(orig_path)
        v2_obj = _load_pickle(v2_path)
        if orig_obj is None or v2_obj is None:
            print(f"[league {league_id}] skipped (failed to read one or both pickle files)")
            continue

        league_name = str(v2_obj.get("league_name") or orig_obj.get("league_name") or f"League {league_id}")
        orig_metrics = _extract_metrics(orig_obj)
        v2_metrics = _extract_metrics(v2_obj)

        winner_delta = _delta(v2_metrics["winner_accuracy"], orig_metrics["winner_accuracy"])
        outcome_delta = _delta(v2_metrics["outcome_accuracy"], orig_metrics["outcome_accuracy"])
        mae_delta = _delta(v2_metrics["overall_mae"], orig_metrics["overall_mae"])

        print(
            f"[{league_name}] "
            f"orig_win={_format(orig_metrics['winner_accuracy'], pct=True)} "
            f"v2_win={_format(v2_metrics['winner_accuracy'], pct=True)} "
            f"delta={_format(winner_delta, pct=True)} | "
            f"orig_out={_format(orig_metrics['outcome_accuracy'], pct=True)} "
            f"v2_out={_format(v2_metrics['outcome_accuracy'], pct=True)} "
            f"delta={_format(outcome_delta, pct=True)} | "
            f"orig_mae={_format(orig_metrics['overall_mae'])} "
            f"v2_mae={_format(v2_metrics['overall_mae'])} "
            f"delta={_format(mae_delta)}"
        )

        results.append(
            {
                "league_id": league_id,
                "league_name": league_name,
                "original_file": str(orig_path),
                "v2_file": str(v2_path),
                "original_model_type": orig_obj.get("model_type"),
                "v2_model_type": v2_obj.get("model_type"),
                "original_winner_mode": orig_obj.get("winner_mode"),
                "v2_winner_mode": v2_obj.get("winner_mode"),
                "original_metrics": orig_metrics,
                "v2_metrics": v2_metrics,
                "delta": {
                    "winner_accuracy": winner_delta,
                    "outcome_accuracy": outcome_delta,
                    "overall_mae": mae_delta,
                },
            }
        )

    if not results:
        print("No valid original/v2 pairs found.")
        return

    avg_win_delta = sum(r["delta"]["winner_accuracy"] for r in results if r["delta"]["winner_accuracy"] is not None)
    cnt_win = sum(1 for r in results if r["delta"]["winner_accuracy"] is not None)
    avg_mae_delta = sum(r["delta"]["overall_mae"] for r in results if r["delta"]["overall_mae"] is not None)
    cnt_mae = sum(1 for r in results if r["delta"]["overall_mae"] is not None)
    v2_better_win = sum(
        1
        for r in results
        if r["delta"]["winner_accuracy"] is not None and r["delta"]["winner_accuracy"] > 0
    )
    v2_better_mae = sum(
        1 for r in results if r["delta"]["overall_mae"] is not None and r["delta"]["overall_mae"] < 0
    )

    print("\n=== Summary ===")
    print(f"Compared leagues: {len(results)}")
    print(f"V2 better winner accuracy: {v2_better_win}/{cnt_win}")
    print(f"V2 better overall MAE: {v2_better_mae}/{cnt_mae} (lower is better)")
    if cnt_win:
        print(f"Average winner accuracy delta (v2-orig): {_format(avg_win_delta / cnt_win, pct=True)}")
    if cnt_mae:
        print(f"Average overall MAE delta (v2-orig): {_format(avg_mae_delta / cnt_mae)}")

    if args.save_json:
        out_path = Path(args.save_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z", "results": results}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved JSON: {out_path}")


if __name__ == "__main__":
    main()
