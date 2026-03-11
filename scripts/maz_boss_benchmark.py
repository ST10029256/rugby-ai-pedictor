#!/usr/bin/env python3
"""
MAZ Boss Benchmark

Builds a stronger "MAZ" ensemble brain and benchmarks it against the current
brain config using strictly chronological unseen holdout data.

Goal:
- Real unseen comparison (train on past, test on future).
- Head-to-head winner by league and overall.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, mean_absolute_error

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
except Exception:
    print("XGBoost is required. Install with: pip install xgboost")
    raise

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table


@dataclass
class ModelMetrics:
    accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    rows: int


def default_db_path() -> Path:
    root = Path(__file__).parent.parent
    main_db = root / "data.sqlite"
    fn_db = root / "rugby-ai-predictor" / "data.sqlite"
    return main_db if main_db.exists() else fn_db


def load_league_df(conn: sqlite3.Connection, league_id: int) -> pd.DataFrame:
    cfg = FeatureConfig(
        elo_priors=None,
        elo_k=24.0,
        neutral_mode=(league_id in (4574, 4714)),
    )
    df = build_feature_table(conn, cfg)
    df = df[df["league_id"] == league_id].copy()
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    if df.empty:
        return df
    df.sort_values(["date_event", "event_id"], inplace=True)
    return df


def prepare_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    exclude_cols = {
        "event_id",
        "league_id",
        "season",
        "date_event",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "home_win",
        "draw",
    }
    feature_cols = [c for c in df.columns if c not in exclude_cols and not df[c].isna().all()]
    X = df[feature_cols].fillna(0).values
    y_winner = (df["home_score"] > df["away_score"]).astype(int).values
    y_home = df["home_score"].values
    y_away = df["away_score"].values
    return X, y_winner, y_home, y_away, feature_cols


def chronological_split(
    X: np.ndarray,
    y_winner: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    holdout_ratio: float,
) -> Dict[str, np.ndarray]:
    n = len(X)
    split_idx = int(round(n * (1.0 - holdout_ratio)))
    split_idx = max(30, min(split_idx, n - 10))
    return {
        "X_train": X[:split_idx],
        "X_test": X[split_idx:],
        "y_w_train": y_winner[:split_idx],
        "y_w_test": y_winner[split_idx:],
        "y_h_train": y_home[:split_idx],
        "y_h_test": y_home[split_idx:],
        "y_a_train": y_away[:split_idx],
        "y_a_test": y_away[split_idx:],
    }


def train_triplet(
    X_train: np.ndarray,
    y_w_train: np.ndarray,
    y_h_train: np.ndarray,
    y_a_train: np.ndarray,
    params: Dict[str, Any],
) -> Tuple[Any, Any, Any]:
    clf = xgb.XGBClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=42,
        eval_metric="logloss",
    )
    clf.fit(X_train, y_w_train)

    reg_home = xgb.XGBRegressor(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=42,
        eval_metric="mae",
    )
    reg_home.fit(X_train, y_h_train)

    reg_away = xgb.XGBRegressor(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=42,
        eval_metric="mae",
    )
    reg_away.fit(X_train, y_a_train)
    return clf, reg_home, reg_away


def eval_triplet(
    clf: Any,
    reg_home: Any,
    reg_away: Any,
    X_test: np.ndarray,
    y_w_test: np.ndarray,
    y_h_test: np.ndarray,
    y_a_test: np.ndarray,
) -> Tuple[ModelMetrics, Dict[str, np.ndarray]]:
    p_home = clf.predict_proba(X_test)[:, 1]
    y_w_pred = (p_home >= 0.5).astype(int)
    y_h_pred = reg_home.predict(X_test)
    y_a_pred = reg_away.predict(X_test)
    metrics = ModelMetrics(
        accuracy=float(accuracy_score(y_w_test, y_w_pred)),
        home_mae=float(mean_absolute_error(y_h_test, y_h_pred)),
        away_mae=float(mean_absolute_error(y_a_test, y_a_pred)),
        overall_mae=float((mean_absolute_error(y_h_test, y_h_pred) + mean_absolute_error(y_a_test, y_a_pred)) / 2.0),
        rows=len(X_test),
    )
    return metrics, {"p_home": p_home, "home_pred": y_h_pred, "away_pred": y_a_pred}


def make_maz_ensemble(
    train: Dict[str, np.ndarray],
    val_ratio: float = 0.2,
) -> Dict[str, Any]:
    # Split train into inner-train and inner-val chronologically.
    X = train["X_train"]
    y_w = train["y_w_train"]
    y_h = train["y_h_train"]
    y_a = train["y_a_train"]
    n = len(X)
    cut = int(round(n * (1.0 - val_ratio)))
    cut = max(25, min(cut, n - 10))

    X_in, X_val = X[:cut], X[cut:]
    y_w_in, y_w_val = y_w[:cut], y_w[cut:]
    y_h_in, y_h_val = y_h[:cut], y_h[cut:]
    y_a_in, y_a_val = y_a[:cut], y_a[cut:]

    params_a = {
        "n_estimators": 250,
        "max_depth": 6,
        "learning_rate": 0.08,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 1.0,
        "reg_lambda": 1.0,
    }
    params_b = {
        "n_estimators": 650,
        "max_depth": 4,
        "learning_rate": 0.04,
        "subsample": 0.95,
        "colsample_bytree": 0.95,
        "min_child_weight": 4.0,
        "reg_lambda": 2.5,
    }

    a_clf, a_h, a_a = train_triplet(X_in, y_w_in, y_h_in, y_a_in, params_a)
    b_clf, b_h, b_a = train_triplet(X_in, y_w_in, y_h_in, y_a_in, params_b)

    # Validation-derived weights.
    a_m, a_out = eval_triplet(a_clf, a_h, a_a, X_val, y_w_val, y_h_val, y_a_val)
    b_m, b_out = eval_triplet(b_clf, b_h, b_a, X_val, y_w_val, y_h_val, y_a_val)

    # Accuracy weights for winner probs.
    w_acc_a = max(a_m.accuracy, 1e-6)
    w_acc_b = max(b_m.accuracy, 1e-6)
    winner_w_sum = w_acc_a + w_acc_b
    winner_w = (w_acc_a / winner_w_sum, w_acc_b / winner_w_sum)

    # Inverse-MAE weights for scores.
    inv_mae_a = 1.0 / max(a_m.overall_mae, 1e-6)
    inv_mae_b = 1.0 / max(b_m.overall_mae, 1e-6)
    score_w_sum = inv_mae_a + inv_mae_b
    score_w = (inv_mae_a / score_w_sum, inv_mae_b / score_w_sum)

    # Retrain both members on full train.
    a_clf, a_h, a_a = train_triplet(X, y_w, y_h, y_a, params_a)
    b_clf, b_h, b_a = train_triplet(X, y_w, y_h, y_a, params_b)

    return {
        "members": {
            "A": {"clf": a_clf, "reg_home": a_h, "reg_away": a_a, "params": params_a},
            "B": {"clf": b_clf, "reg_home": b_h, "reg_away": b_a, "params": params_b},
        },
        "weights": {"winner": winner_w, "score": score_w},
        "validation": {
            "A": a_m.__dict__,
            "B": b_m.__dict__,
        },
    }


def eval_maz_ensemble(maz: Dict[str, Any], test: Dict[str, np.ndarray]) -> ModelMetrics:
    A = maz["members"]["A"]
    B = maz["members"]["B"]
    w_w_a, w_w_b = maz["weights"]["winner"]
    w_s_a, w_s_b = maz["weights"]["score"]

    X_test = test["X_test"]
    y_w_test = test["y_w_test"]
    y_h_test = test["y_h_test"]
    y_a_test = test["y_a_test"]

    p_a = A["clf"].predict_proba(X_test)[:, 1]
    p_b = B["clf"].predict_proba(X_test)[:, 1]
    p_home = w_w_a * p_a + w_w_b * p_b
    y_w_pred = (p_home >= 0.5).astype(int)

    h_a = A["reg_home"].predict(X_test)
    h_b = B["reg_home"].predict(X_test)
    a_a = A["reg_away"].predict(X_test)
    a_b = B["reg_away"].predict(X_test)
    y_h_pred = w_s_a * h_a + w_s_b * h_b
    y_a_pred = w_s_a * a_a + w_s_b * a_b

    return ModelMetrics(
        accuracy=float(accuracy_score(y_w_test, y_w_pred)),
        home_mae=float(mean_absolute_error(y_h_test, y_h_pred)),
        away_mae=float(mean_absolute_error(y_a_test, y_a_pred)),
        overall_mae=float((mean_absolute_error(y_h_test, y_h_pred) + mean_absolute_error(y_a_test, y_a_pred)) / 2.0),
        rows=len(X_test),
    )


def baseline_params() -> Dict[str, Any]:
    return {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.10,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1.0,
        "reg_lambda": 1.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MAZ Boss unseen benchmark vs current brain.")
    parser.add_argument("--db-path", default=None, help="SQLite path.")
    parser.add_argument("--league-id", type=int, default=None, help="Single league id.")
    parser.add_argument("--all-leagues", action="store_true", help="Run all leagues.")
    parser.add_argument("--holdout-ratio", type=float, default=0.2, help="Unseen holdout ratio.")
    parser.add_argument("--min-games", type=int, default=80, help="Min completed games to evaluate.")
    parser.add_argument("--save-maz-models", action="store_true", help="Save MAZ models when superior.")
    args = parser.parse_args()

    if not args.league_id and not args.all_leagues:
        raise SystemExit("Use --league-id <id> or --all-leagues")

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    leagues: Dict[int, str]
    if args.league_id:
        leagues = {args.league_id: LEAGUE_MAPPINGS.get(args.league_id, f"League {args.league_id}")}
    else:
        leagues = LEAGUE_MAPPINGS

    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "db_path": str(db_path),
        "config": {
            "holdout_ratio": args.holdout_ratio,
            "min_games": args.min_games,
        },
        "summary": {
            "tested": 0,
            "maz_wins": 0,
            "current_wins": 0,
            "ties": 0,
            "skipped": 0,
        },
        "leagues": {},
    }

    conn = sqlite3.connect(str(db_path))

    for league_id, league_name in leagues.items():
        df = load_league_df(conn, league_id)
        if len(df) < args.min_games:
            report["summary"]["skipped"] += 1
            report["leagues"][str(league_id)] = {
                "name": league_name,
                "status": "skipped",
                "reason": f"not enough games ({len(df)} < {args.min_games})",
            }
            continue

        X, y_w, y_h, y_a, feature_cols = prepare_xy(df)
        split = chronological_split(X, y_w, y_h, y_a, args.holdout_ratio)

        # Current brain baseline.
        b_clf, b_h, b_a = train_triplet(
            split["X_train"],
            split["y_w_train"],
            split["y_h_train"],
            split["y_a_train"],
            baseline_params(),
        )
        baseline_m, _ = eval_triplet(
            b_clf, b_h, b_a,
            split["X_test"], split["y_w_test"], split["y_h_test"], split["y_a_test"]
        )

        # MAZ brain.
        maz = make_maz_ensemble(split)
        maz_m = eval_maz_ensemble(maz, split)

        # Head-to-head rule:
        # - MAZ wins if accuracy improves and overall MAE does not worsen.
        # - Current wins if opposite.
        # - Else tie/trade-off.
        maz_better = (maz_m.accuracy > baseline_m.accuracy) and (maz_m.overall_mae <= baseline_m.overall_mae)
        current_better = (baseline_m.accuracy > maz_m.accuracy) and (baseline_m.overall_mae <= maz_m.overall_mae)

        if maz_better:
            winner = "MAZ"
            report["summary"]["maz_wins"] += 1
        elif current_better:
            winner = "CURRENT"
            report["summary"]["current_wins"] += 1
        else:
            winner = "TIE_OR_TRADEOFF"
            report["summary"]["ties"] += 1
        report["summary"]["tested"] += 1

        league_payload: Dict[str, Any] = {
            "name": league_name,
            "status": "tested",
            "games": len(df),
            "train_rows": int(len(split["X_train"])),
            "test_rows": int(len(split["X_test"])),
            "feature_count": len(feature_cols),
            "current": baseline_m.__dict__,
            "maz": maz_m.__dict__,
            "deltas": {
                "accuracy_gain": maz_m.accuracy - baseline_m.accuracy,
                "overall_mae_reduction": baseline_m.overall_mae - maz_m.overall_mae,
            },
            "winner": winner,
            "maz_validation_weights": maz["weights"],
        }

        if args.save_maz_models and winner == "MAZ":
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"league_{league_id}_model_maz_boss.pkl"
            payload = {
                "league_id": league_id,
                "league_name": league_name,
                "model_type": "maz_boss_ensemble",
                "trained_at": datetime.now().isoformat(),
                "feature_columns": feature_cols,
                "maz": maz,
                "baseline_metrics_unseen": baseline_m.__dict__,
                "maz_metrics_unseen": maz_m.__dict__,
            }
            with out_file.open("wb") as f:
                pickle.dump(payload, f)
            league_payload["saved_maz_model"] = str(out_file)

        report["leagues"][str(league_id)] = league_payload

        print(
            f"[{league_name}] current_acc={baseline_m.accuracy:.3f} maz_acc={maz_m.accuracy:.3f} | "
            f"current_mae={baseline_m.overall_mae:.3f} maz_mae={maz_m.overall_mae:.3f} | winner={winner}"
        )

    conn.close()

    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"maz_boss_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== MAZ Boss Head-to-Head Summary ===")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved: {out_path}")


if __name__ == "__main__":
    main()

