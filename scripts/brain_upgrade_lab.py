#!/usr/bin/env python3
"""
Brain Upgrade Lab

Purpose:
- Inspect the current "AI brain" quality using time-aware validation.
- Train/evaluate a stronger challenger brain.
- Report if challenger truly surpasses baseline per league.

This does NOT claim to create the "smartest AI in the world".
It creates a stronger rugby predictor in this project by measurable metrics.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

# Ensure local imports work when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
except Exception:
    print("XGBoost is required: pip install xgboost")
    raise

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table


@dataclass
class EvalResult:
    winner_accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    folds_used: int
    train_rows: int


def _default_db_path() -> Path:
    root = Path(__file__).parent.parent
    p1 = root / "data.sqlite"
    p2 = root / "rugby-ai-predictor" / "data.sqlite"
    return p1 if p1.exists() else p2


def _read_model_registry(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_league_df(conn: sqlite3.Connection, league_id: int) -> pd.DataFrame:
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


def _prepare_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
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


def _train_triplet(
    X_train: np.ndarray,
    y_winner_train: np.ndarray,
    y_home_train: np.ndarray,
    y_away_train: np.ndarray,
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
    clf.fit(X_train, y_winner_train)

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
    reg_home.fit(X_train, y_home_train)

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
    reg_away.fit(X_train, y_away_train)
    return clf, reg_home, reg_away


def evaluate_with_timeseries_cv(
    X: np.ndarray,
    y_winner: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    params: Dict[str, Any],
    n_splits: int,
) -> EvalResult:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    accs: List[float] = []
    home_maes: List[float] = []
    away_maes: List[float] = []

    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_w_train, y_w_test = y_winner[train_idx], y_winner[test_idx]
        y_h_train, y_h_test = y_home[train_idx], y_home[test_idx]
        y_a_train, y_a_test = y_away[train_idx], y_away[test_idx]

        # Skip folds with no class variance.
        if len(np.unique(y_w_train)) < 2:
            continue

        clf, reg_home, reg_away = _train_triplet(X_train, y_w_train, y_h_train, y_a_train, params)

        y_w_pred = clf.predict(X_test)
        y_h_pred = reg_home.predict(X_test)
        y_a_pred = reg_away.predict(X_test)

        accs.append(float(accuracy_score(y_w_test, y_w_pred)))
        home_maes.append(float(mean_absolute_error(y_h_test, y_h_pred)))
        away_maes.append(float(mean_absolute_error(y_a_test, y_a_pred)))

    if not accs:
        return EvalResult(0.0, 999.0, 999.0, 999.0, 0, len(X))

    home_mae = float(np.mean(home_maes))
    away_mae = float(np.mean(away_maes))
    return EvalResult(
        winner_accuracy=float(np.mean(accs)),
        home_mae=home_mae,
        away_mae=away_mae,
        overall_mae=(home_mae + away_mae) / 2.0,
        folds_used=len(accs),
        train_rows=len(X),
    )


def _train_full_and_save(
    X: np.ndarray,
    y_winner: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    feature_cols: List[str],
    params: Dict[str, Any],
    league_id: int,
    league_name: str,
    output_dir: Path,
) -> str:
    clf, reg_home, reg_away = _train_triplet(X, y_winner, y_home, y_away, params)
    payload = {
        "league_id": league_id,
        "league_name": league_name,
        "model_type": "xgboost_challenger",
        "trained_at": datetime.now().isoformat(),
        "feature_columns": feature_cols,
        "models": {
            "clf": clf,
            "reg_home": reg_home,
            "reg_away": reg_away,
        },
        "training_params": params,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"league_{league_id}_model_xgboost_challenger.pkl"
    import pickle

    with out.open("wb") as f:
        pickle.dump(payload, f)
    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate and upgrade rugby AI brain.")
    parser.add_argument("--db-path", default=None, help="SQLite path (default auto-detect).")
    parser.add_argument("--league-id", type=int, default=None, help="Single league id.")
    parser.add_argument("--all-leagues", action="store_true", help="Run all configured leagues.")
    parser.add_argument("--min-games", type=int, default=60, help="Minimum completed games per league.")
    parser.add_argument("--splits", type=int, default=5, help="TimeSeries CV splits.")
    parser.add_argument(
        "--save-challenger",
        action="store_true",
        help="Save challenger model only where it beats baseline.",
    )
    parser.add_argument(
        "--win-threshold",
        type=float,
        default=0.01,
        help="Required accuracy gain to count as superior (default 0.01 = +1%).",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    if args.league_id:
        leagues = {args.league_id: LEAGUE_MAPPINGS.get(args.league_id, f"League {args.league_id}")}
    elif args.all_leagues:
        leagues = LEAGUE_MAPPINGS
    else:
        raise SystemExit("Use --league-id <id> or --all-leagues")

    baseline_params = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.10,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1.0,
        "reg_lambda": 1.0,
    }
    challenger_params = {
        "n_estimators": 500,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "min_child_weight": 3.0,
        "reg_lambda": 2.0,
    }

    registry = _read_model_registry(Path("artifacts/model_registry.json"))
    print("=== Current Brain Snapshot ===")
    if registry.get("leagues"):
        print(f"Model registry has {len(registry.get('leagues', {}))} leagues.")
    else:
        print("Model registry missing/empty; running direct benchmark anyway.")

    conn = sqlite3.connect(str(db_path))
    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "db_path": str(db_path),
        "summary": {"tested": 0, "challenger_better": 0, "skipped": 0},
        "leagues": {},
    }

    for league_id, league_name in leagues.items():
        df = _load_league_df(conn, league_id)
        if len(df) < args.min_games:
            report["summary"]["skipped"] += 1
            report["leagues"][str(league_id)] = {
                "name": league_name,
                "status": "skipped",
                "reason": f"not enough games ({len(df)} < {args.min_games})",
            }
            continue

        X, y_w, y_h, y_a, feature_cols = _prepare_xy(df)
        base = evaluate_with_timeseries_cv(X, y_w, y_h, y_a, baseline_params, args.splits)
        ch = evaluate_with_timeseries_cv(X, y_w, y_h, y_a, challenger_params, args.splits)

        acc_gain = ch.winner_accuracy - base.winner_accuracy
        mae_gain = base.overall_mae - ch.overall_mae
        superior = (acc_gain >= args.win_threshold) and (mae_gain >= 0.0)

        row: Dict[str, Any] = {
            "name": league_name,
            "status": "tested",
            "games": len(df),
            "feature_count": len(feature_cols),
            "baseline": base.__dict__,
            "challenger": ch.__dict__,
            "accuracy_gain": acc_gain,
            "mae_reduction": mae_gain,
            "challenger_superior": superior,
        }

        if superior and args.save_challenger:
            saved_path = _train_full_and_save(
                X, y_w, y_h, y_a, feature_cols, challenger_params, league_id, league_name, Path("artifacts")
            )
            row["saved_challenger_model"] = saved_path

        report["leagues"][str(league_id)] = row
        report["summary"]["tested"] += 1
        if superior:
            report["summary"]["challenger_better"] += 1

        print(
            f"[{league_name}] base_acc={base.winner_accuracy:.3f} -> chal_acc={ch.winner_accuracy:.3f} "
            f"| base_mae={base.overall_mae:.3f} -> chal_mae={ch.overall_mae:.3f} | superior={superior}"
        )

    conn.close()

    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"brain_lab_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Brain Upgrade Verdict ===")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved: {out_path}")
    print(
        "\nWorld-smartest AI check: not realistic for a single project script. "
        "Building the best rugby predictor in your domain is realistic and measurable."
    )


if __name__ == "__main__":
    main()

