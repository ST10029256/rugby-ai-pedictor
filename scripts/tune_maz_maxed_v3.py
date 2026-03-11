#!/usr/bin/env python3
"""
Auto-tune MAZ MAXED V3.

Runs many V3 configs, ranks with win/lose-first objective + tail-aware penalties,
and writes best config map per league.
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
ARTIFACTS = ROOT / "artifacts"
V3_SCRIPT = ROOT / "scripts" / "maz_boss_maxed_v3.py"


@dataclass
class Attempt:
    league_id: int
    league_name: str
    config_name: str
    config_flags: Dict[str, Any]
    winner: str
    winner_gain: float
    outcome_gain: float
    mae_reduction: float
    brier_reduction: float
    objective_score: float
    report_path: str
    command: str


def _from_dict(row: Dict[str, Any]) -> Optional[Attempt]:
    try:
        return Attempt(
            league_id=int(row["league_id"]),
            league_name=str(row["league_name"]),
            config_name=str(row["config_name"]),
            config_flags=dict(row.get("config_flags", {})),
            winner=str(row["winner"]),
            winner_gain=float(row["winner_gain"]),
            outcome_gain=float(row["outcome_gain"]),
            mae_reduction=float(row["mae_reduction"]),
            brier_reduction=float(row["brier_reduction"]),
            objective_score=float(row["objective_score"]),
            report_path=str(row.get("report_path", "")),
            command=str(row.get("command", "")),
        )
    except Exception:
        return None


def _flags_to_cli(flags: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for k, v in flags.items():
        kk = f"--{k}"
        if isinstance(v, bool):
            if v:
                out.append(kk)
        else:
            out.extend([kk, str(v)])
    return out


def _profiles(profile: str) -> List[Dict[str, Any]]:
    quick = [
        {"name": "v3_q1_balanced", "alpha-stable": 0.65, "alpha-balanced": 0.55, "alpha-chaotic": 0.40, "residual-shrink-k": 140.0, "rating-k": 0.045, "rating-decay": 0.995},
        {"name": "v3_q2_winner", "alpha-stable": 0.72, "alpha-balanced": 0.62, "alpha-chaotic": 0.48, "residual-shrink-k": 160.0, "rating-k": 0.050, "rating-decay": 0.995},
        {"name": "v3_q3_dist", "alpha-stable": 0.58, "alpha-balanced": 0.48, "alpha-chaotic": 0.34, "residual-shrink-k": 130.0, "rating-k": 0.042, "rating-decay": 0.994},
        {"name": "v3_q4_shrink_strict", "alpha-stable": 0.68, "alpha-balanced": 0.58, "alpha-chaotic": 0.42, "residual-shrink-k": 220.0, "rating-k": 0.046, "rating-decay": 0.996},
    ]
    max_set = quick + [
        {"name": "v3_m1_aggr_win", "alpha-stable": 0.78, "alpha-balanced": 0.68, "alpha-chaotic": 0.52, "residual-shrink-k": 170.0, "rating-k": 0.052, "rating-decay": 0.996},
        {"name": "v3_m2_tail_safe", "alpha-stable": 0.62, "alpha-balanced": 0.52, "alpha-chaotic": 0.36, "residual-shrink-k": 260.0, "rating-k": 0.043, "rating-decay": 0.995},
        {"name": "v3_m3_mid", "alpha-stable": 0.70, "alpha-balanced": 0.60, "alpha-chaotic": 0.44, "residual-shrink-k": 180.0, "rating-k": 0.047, "rating-decay": 0.995},
        {"name": "v3_m4_dist_chaotic", "alpha-stable": 0.55, "alpha-balanced": 0.45, "alpha-chaotic": 0.30, "residual-shrink-k": 210.0, "rating-k": 0.040, "rating-decay": 0.994},
    ]
    return quick if profile == "quick" else max_set


def _base_flags(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "holdout-ratio": args.holdout_ratio,
        "min-games": args.min_games,
        "max-score": args.max_score,
        "min-isotonic-rows": args.min_isotonic_rows,
        "min-winner-gain": args.min_winner_gain,
        "max-mae-worsen": args.max_mae_worsen,
        "max-brier-worsen": args.max_brier_worsen,
        "save-v3-models": bool(args.save_models_during_tuning),
    }


def _league_ids(args: argparse.Namespace) -> List[int]:
    if args.league_ids:
        return sorted(set(args.league_ids))
    if not args.all_leagues:
        raise SystemExit("Use --all-leagues or --league-id")
    sys.path.insert(0, str(ROOT))
    from prediction.config import LEAGUE_MAPPINGS  # type: ignore

    return sorted(int(k) for k in LEAGUE_MAPPINGS.keys())


def _score(d: Dict[str, Any]) -> float:
    return (10000.0 * float(d["winner_accuracy_gain"])) + (1300.0 * float(d["outcome_accuracy_gain"])) + (25.0 * float(d["overall_mae_reduction"])) + (250.0 * float(d["brier_reduction"]))


def _run_once(python_exe: str, league_id: int, flags: Dict[str, Any]) -> Tuple[subprocess.CompletedProcess, Path]:
    cmd = [python_exe, str(V3_SCRIPT)] + _flags_to_cli(flags) + ["--league-id", str(league_id)]
    cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    reports = sorted(ARTIFACTS.glob("maz_maxed_v3_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        raise RuntimeError("No V3 report file produced")
    return cp, reports[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune MAZ MAXED V3")
    parser.add_argument("--league-id", dest="league_ids", action="append", type=int)
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--profile", choices=["quick", "max"], default="quick")
    parser.add_argument("--max-configs", type=int, default=0)
    parser.add_argument("--start-attempt", type=int, default=1)
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--save-models-during-tuning", action="store_true")
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--min-games", type=int, default=120)
    parser.add_argument("--max-score", type=int, default=70)
    parser.add_argument("--min-isotonic-rows", type=int, default=90)
    parser.add_argument("--min-winner-gain", type=float, default=0.003)
    parser.add_argument("--max-mae-worsen", type=float, default=0.12)
    parser.add_argument("--max-brier-worsen", type=float, default=0.01)
    args = parser.parse_args()

    ARTIFACTS.mkdir(exist_ok=True)
    leagues = _league_ids(args)
    cfgs = _profiles(args.profile)
    if args.max_configs > 0:
        cfgs = cfgs[: args.max_configs]
    if args.start_attempt < 1:
        raise SystemExit("--start-attempt must be >= 1")

    results_path = ARTIFACTS / "maz_v3_tuning_results.json"
    best_path = ARTIFACTS / "maz_v3_best_config.json"
    attempts: List[Attempt] = []
    best_by_league: Dict[int, Attempt] = {}
    if args.start_attempt > 1 and results_path.exists():
        try:
            prior = json.loads(results_path.read_text(encoding="utf-8")).get("attempts", [])
            for row in prior:
                if isinstance(row, dict):
                    a = _from_dict(row)
                    if a is None:
                        continue
                    attempts.append(a)
                    b = best_by_league.get(a.league_id)
                    if b is None or a.objective_score > b.objective_score:
                        best_by_league[a.league_id] = a
            print(f"Loaded {len(attempts)} prior attempts from {results_path}")
        except Exception:
            print("Could not load prior attempts. Starting fresh.")

    base = _base_flags(args)
    total = len(leagues) * len(cfgs)
    idx = 0
    for lid in leagues:
        for cfg in cfgs:
            idx += 1
            if idx < args.start_attempt:
                continue
            cfg_name = str(cfg["name"])
            flags = dict(base)
            flags.update({k: v for k, v in cfg.items() if k != "name"})
            print(f"[{idx}/{total}] league={lid} config={cfg_name}")
            cp, report_path = _run_once(args.python_exe, lid, flags)
            if cp.returncode != 0:
                print(f"  failed exit={cp.returncode}")
                if cp.stderr:
                    print(f"  stderr: {cp.stderr.strip()[:300]}")
                continue
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            lb = rep.get("leagues", {}).get(str(lid))
            if not isinstance(lb, dict) or lb.get("status") != "tested":
                print("  skipped")
                continue
            d = lb.get("deltas", {})
            score = _score(d)
            row = Attempt(
                league_id=lid,
                league_name=str(lb.get("name", f"League {lid}")),
                config_name=cfg_name,
                config_flags={k: v for k, v in cfg.items() if k != "name"},
                winner=str(lb.get("winner", "UNKNOWN")),
                winner_gain=float(d.get("winner_accuracy_gain", 0.0)),
                outcome_gain=float(d.get("outcome_accuracy_gain", 0.0)),
                mae_reduction=float(d.get("overall_mae_reduction", 0.0)),
                brier_reduction=float(d.get("brier_reduction", 0.0)),
                objective_score=score,
                report_path=str(report_path),
                command=" ".join([args.python_exe, str(V3_SCRIPT)] + _flags_to_cli(flags) + ["--league-id", str(lid)]),
            )
            attempts.append(row)
            prev = best_by_league.get(lid)
            if prev is None or row.objective_score > prev.objective_score:
                best_by_league[lid] = row
            print(
                "  "
                f"winner={row.winner} "
                f"win_gain={row.winner_gain:+.4f} "
                f"out_gain={row.outcome_gain:+.4f} "
                f"mae_red={row.mae_reduction:+.4f} "
                f"brier_red={row.brier_reduction:+.4f}"
            )

    results_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile": args.profile,
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
                "brier_reduction": v.brier_reduction,
                "objective_score": v.objective_score,
            }
            for k, v in sorted(best_by_league.items())
        },
    }
    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    best_path.write_text(json.dumps(best_payload, indent=2), encoding="utf-8")
    print("\n=== V3 Tuning Complete ===")
    print(f"Attempts recorded: {len(attempts)}")
    print(f"Best configs found for leagues: {len(best_by_league)}")
    print(f"Detailed results: {results_path}")
    print(f"Best config map: {best_path}")


if __name__ == "__main__":
    main()
