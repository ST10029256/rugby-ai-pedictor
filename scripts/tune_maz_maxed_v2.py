#!/usr/bin/env python3
"""
Auto-tune MAZ MAXED V2 by running multiple configs per league.

This tuner launches `scripts/maz_boss_maxed_v2.py` repeatedly, scores each run
with a win/lose-first objective, and writes:

- artifacts/maz_v2_tuning_results.json   (all attempts)
- artifacts/maz_v2_best_config.json      (best config per league)

Examples:
  python scripts/tune_maz_maxed_v2.py --all-leagues --profile quick
  python scripts/tune_maz_maxed_v2.py --league-id 5069 --profile max
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"
V2_SCRIPT = ROOT / "scripts" / "maz_boss_maxed_v2.py"


@dataclass
class AttemptResult:
    league_id: int
    league_name: str
    config_name: str
    config_flags: Dict[str, Any]
    winner: str
    current_winner_acc: float
    maz_winner_acc: float
    current_outcome_acc: float
    maz_outcome_acc: float
    current_mae: float
    maz_mae: float
    winner_gain: float
    outcome_gain: float
    mae_reduction: float
    objective_score: float
    report_path: str
    command: str


def _attempt_from_dict(row: Dict[str, Any]) -> Optional[AttemptResult]:
    try:
        return AttemptResult(
            league_id=int(row["league_id"]),
            league_name=str(row["league_name"]),
            config_name=str(row["config_name"]),
            config_flags=dict(row.get("config_flags", {})),
            winner=str(row.get("winner", "UNKNOWN")),
            current_winner_acc=float(row["current_winner_acc"]),
            maz_winner_acc=float(row["maz_winner_acc"]),
            current_outcome_acc=float(row["current_outcome_acc"]),
            maz_outcome_acc=float(row["maz_outcome_acc"]),
            current_mae=float(row["current_mae"]),
            maz_mae=float(row["maz_mae"]),
            winner_gain=float(row["winner_gain"]),
            outcome_gain=float(row["outcome_gain"]),
            mae_reduction=float(row["mae_reduction"]),
            objective_score=float(row["objective_score"]),
            report_path=str(row.get("report_path", "")),
            command=str(row.get("command", "")),
        )
    except Exception:
        return None


def _base_flags(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "walk-forward": True,
        "wf-start-train": args.wf_start_train,
        "wf-step": args.wf_step,
        "min-games": args.min_games,
        "feature-select-max": args.feature_select_max,
        "feature-select-steps": args.feature_select_steps,
        "graph-half-life": args.graph_half_life,
        "score-density-max": args.score_density_max,
        "score-density-sticky-boost": args.score_density_sticky_boost,
        "winner-first-mode": True,
        "max-winner-drop-score-head": 0.0,
        "max-winner-drop-vs-legacy": 0.0,
        "max-outcome-drop-vs-legacy": 0.0,
        "save-maz-models": bool(args.save_models_during_tuning),
        "quantum-mode": bool(not args.disable_quantum),
    }


def _profiles(profile: str) -> List[Dict[str, Any]]:
    quick = [
        {"name": "q1_balanced", "search-rounds": 14, "top-k": 8, "cv-splits": 6, "quantum-steps": 1800, "cv-weight-winner": 0.78, "cv-weight-outcome": 0.22, "cv-weight-mae": 0.004, "blend-outcome-metric": "winner"},
        {"name": "q2_win_hard", "search-rounds": 16, "top-k": 10, "cv-splits": 6, "quantum-steps": 2200, "cv-weight-winner": 0.86, "cv-weight-outcome": 0.14, "cv-weight-mae": 0.003, "blend-outcome-metric": "winner"},
        {"name": "q3_win_extreme", "search-rounds": 18, "top-k": 10, "cv-splits": 7, "quantum-steps": 2400, "cv-weight-winner": 0.92, "cv-weight-outcome": 0.08, "cv-weight-mae": 0.002, "blend-outcome-metric": "winner"},
        {"name": "q4_hybrid_guard", "search-rounds": 16, "top-k": 8, "cv-splits": 6, "quantum-steps": 2000, "cv-weight-winner": 0.84, "cv-weight-outcome": 0.16, "cv-weight-mae": 0.003, "blend-outcome-metric": "hybrid"},
    ]
    max_set = quick + [
        {"name": "m1_deep_win_1", "search-rounds": 24, "top-k": 12, "cv-splits": 7, "quantum-steps": 3200, "cv-weight-winner": 0.88, "cv-weight-outcome": 0.12, "cv-weight-mae": 0.003, "blend-outcome-metric": "winner"},
        {"name": "m2_deep_win_2", "search-rounds": 28, "top-k": 12, "cv-splits": 8, "quantum-steps": 3600, "cv-weight-winner": 0.90, "cv-weight-outcome": 0.10, "cv-weight-mae": 0.0025, "blend-outcome-metric": "winner"},
        {"name": "m3_deep_hybrid", "search-rounds": 26, "top-k": 14, "cv-splits": 7, "quantum-steps": 3400, "cv-weight-winner": 0.86, "cv-weight-outcome": 0.14, "cv-weight-mae": 0.0028, "blend-outcome-metric": "hybrid"},
        {"name": "m4_extreme_win", "search-rounds": 32, "top-k": 14, "cv-splits": 8, "quantum-steps": 4200, "cv-weight-winner": 0.94, "cv-weight-outcome": 0.06, "cv-weight-mae": 0.002, "blend-outcome-metric": "winner"},
    ]
    if profile == "quick":
        return quick
    return max_set


def _flags_to_cli(flags: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key, val in flags.items():
        k = f"--{key}"
        if isinstance(val, bool):
            if val:
                out.append(k)
        else:
            out.extend([k, str(val)])
    return out


def _objective_score(current: Dict[str, Any], maz: Dict[str, Any]) -> float:
    winner_gain = float(maz["winner_accuracy"]) - float(current["winner_accuracy"])
    outcome_gain = float(maz["outcome_accuracy"]) - float(current["outcome_accuracy"])
    mae_reduction = float(current["overall_mae"]) - float(maz["overall_mae"])
    # Win/lose-first objective; score quality secondary.
    return (10000.0 * winner_gain) + (1500.0 * outcome_gain) + (20.0 * mae_reduction)


def _load_report(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_single(
    python_exe: str,
    league_id: int,
    base_flags: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Tuple[subprocess.CompletedProcess, Path]:
    cfg_name = str(cfg.get("name", "unnamed"))
    cfg_flags = {k: v for k, v in cfg.items() if k != "name"}
    merged = dict(base_flags)
    merged.update(cfg_flags)
    merged["league-id"] = league_id

    cmd = [python_exe, str(V2_SCRIPT)] + _flags_to_cli(merged)
    cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)

    report_candidates = sorted(ARTIFACTS_DIR.glob("maz_maxed_v2_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not report_candidates:
        raise RuntimeError(f"[{cfg_name}] no v2 report file found after run")
    return cp, report_candidates[0]


def _league_ids_from_args(args: argparse.Namespace) -> List[int]:
    if args.league_ids:
        return sorted(set(args.league_ids))
    if not args.all_leagues:
        raise SystemExit("Use --all-leagues or one/more --league-id")
    sys.path.insert(0, str(ROOT))
    from prediction.config import LEAGUE_MAPPINGS  # type: ignore

    return sorted(int(k) for k in LEAGUE_MAPPINGS.keys())


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-tune MAZ MAXED V2 (win/lose-first).")
    parser.add_argument("--league-id", dest="league_ids", action="append", type=int, help="League id (repeatable).")
    parser.add_argument("--all-leagues", action="store_true", help="Tune all mapped leagues.")
    parser.add_argument("--profile", choices=["quick", "max"], default="quick", help="Search profile size.")
    parser.add_argument("--max-configs", type=int, default=0, help="Limit number of configs (0 = no limit).")
    parser.add_argument("--start-attempt", type=int, default=1, help="1-based attempt index to start from.")
    parser.add_argument("--python-exe", default=sys.executable, help="Python executable path.")
    parser.add_argument("--save-models-during-tuning", action="store_true", help="Save v2 model artifacts during every trial.")
    parser.add_argument("--disable-quantum", action="store_true", help="Turn off quantum mode for all attempts.")

    # Shared baseline config for every attempt.
    parser.add_argument("--wf-start-train", type=int, default=80)
    parser.add_argument("--wf-step", type=int, default=20)
    parser.add_argument("--min-games", type=int, default=90)
    parser.add_argument("--feature-select-max", type=int, default=140)
    parser.add_argument("--feature-select-steps", type=int, default=2600)
    parser.add_argument("--graph-half-life", type=float, default=120.0)
    parser.add_argument("--score-density-max", type=int, default=70)
    parser.add_argument("--score-density-sticky-boost", type=float, default=0.35)

    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    leagues = _league_ids_from_args(args)
    base = _base_flags(args)
    configs = _profiles(args.profile)
    if args.max_configs > 0:
        configs = configs[: args.max_configs]
    if not configs:
        raise SystemExit("No configs selected for tuning.")
    if args.start_attempt < 1:
        raise SystemExit("--start-attempt must be >= 1")

    results_path = ARTIFACTS_DIR / "maz_v2_tuning_results.json"
    attempts: List[AttemptResult] = []
    best_by_league: Dict[int, AttemptResult] = {}
    if args.start_attempt > 1 and results_path.exists():
        try:
            prev_payload = json.loads(results_path.read_text(encoding="utf-8"))
            prev_attempts = prev_payload.get("attempts", [])
            for row in prev_attempts:
                if not isinstance(row, dict):
                    continue
                parsed = _attempt_from_dict(row)
                if parsed is None:
                    continue
                attempts.append(parsed)
                prior = best_by_league.get(parsed.league_id)
                if prior is None or parsed.objective_score > prior.objective_score:
                    best_by_league[parsed.league_id] = parsed
            print(f"Loaded {len(attempts)} prior attempts from {results_path}")
        except Exception:
            print(f"Could not parse prior results at {results_path}; continuing without history.")

    total_runs = len(leagues) * len(configs)
    run_idx = 0
    for league_id in leagues:
        for cfg in configs:
            run_idx += 1
            if run_idx < args.start_attempt:
                continue
            cfg_name = str(cfg.get("name", "unnamed"))
            print(f"[{run_idx}/{total_runs}] league={league_id} config={cfg_name}")
            cp, report_path = _run_single(args.python_exe, league_id, base, cfg)
            if cp.returncode != 0:
                print(f"  failed (exit {cp.returncode})")
                if cp.stderr:
                    print(f"  stderr: {cp.stderr.strip()[:400]}")
                continue

            report = _load_report(report_path)
            league_blob = report.get("leagues", {}).get(str(league_id))
            if not isinstance(league_blob, dict) or league_blob.get("status") != "tested":
                print("  skipped in run report")
                continue

            current = league_blob.get("current", {})
            maz = league_blob.get("maz_maxed_v2", {})
            if not current or not maz:
                print("  missing metric blocks in report")
                continue

            winner_gain = float(maz["winner_accuracy"]) - float(current["winner_accuracy"])
            outcome_gain = float(maz["outcome_accuracy"]) - float(current["outcome_accuracy"])
            mae_reduction = float(current["overall_mae"]) - float(maz["overall_mae"])
            score = _objective_score(current, maz)

            row = AttemptResult(
                league_id=league_id,
                league_name=str(league_blob.get("name", f"League {league_id}")),
                config_name=cfg_name,
                config_flags={k: v for k, v in cfg.items() if k != "name"},
                winner=str(league_blob.get("winner", "UNKNOWN")),
                current_winner_acc=float(current["winner_accuracy"]),
                maz_winner_acc=float(maz["winner_accuracy"]),
                current_outcome_acc=float(current["outcome_accuracy"]),
                maz_outcome_acc=float(maz["outcome_accuracy"]),
                current_mae=float(current["overall_mae"]),
                maz_mae=float(maz["overall_mae"]),
                winner_gain=winner_gain,
                outcome_gain=outcome_gain,
                mae_reduction=mae_reduction,
                objective_score=score,
                report_path=str(report_path),
                command="",
            )
            # Keep a readable command with resolved flags for this specific attempt.
            merged = dict(base)
            merged.update(row.config_flags)
            merged["league-id"] = league_id
            row.command = " ".join([args.python_exe, str(V2_SCRIPT)] + _flags_to_cli(merged))

            attempts.append(row)
            prev = best_by_league.get(league_id)
            if prev is None or row.objective_score > prev.objective_score:
                best_by_league[league_id] = row

            print(
                "  "
                f"winner={row.winner} "
                f"win_gain={row.winner_gain:+.4f} "
                f"out_gain={row.outcome_gain:+.4f} "
                f"mae_red={row.mae_reduction:+.4f}"
            )

    results_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile": args.profile,
        "base_flags": base,
        "league_ids": leagues,
        "attempt_count": len(attempts),
        "attempts": [asdict(a) for a in attempts],
    }
    best_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile": args.profile,
        "league_best": {
            str(k): {
                "league_id": v.league_id,
                "league_name": v.league_name,
                "config_name": v.config_name,
                "config_flags": v.config_flags,
                "winner": v.winner,
                "winner_gain": v.winner_gain,
                "outcome_gain": v.outcome_gain,
                "mae_reduction": v.mae_reduction,
                "objective_score": v.objective_score,
            }
            for k, v in sorted(best_by_league.items())
        },
    }

    best_path = ARTIFACTS_DIR / "maz_v2_best_config.json"
    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    best_path.write_text(json.dumps(best_payload, indent=2), encoding="utf-8")

    print("\n=== Tuning Complete ===")
    print(f"Attempts recorded: {len(attempts)}")
    print(f"Best configs found for leagues: {len(best_by_league)}")
    print(f"Detailed results: {results_path}")
    print(f"Best config map: {best_path}")


if __name__ == "__main__":
    main()
