#!/usr/bin/env python3
"""
MAZ Boss MAXED

A heavier benchmark pipeline to push beyond the current brain:
- Chronological unseen holdout (no leakage).
- Multi-family model search (XGBoost + tree ensembles + gradient boosting).
- Time-series inner validation for candidate scoring.
- Ensemble blending with data-driven weights.
- Probability calibration on validation split.
- Head-to-head report vs current baseline.

This script is "maxed" for practical project constraints, not a claim of
"best AI in the world".
"""

from __future__ import annotations

import argparse
import json
import pickle
import random
import math
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
except Exception:
    print("XGBoost is required. Install with: pip install xgboost")
    raise

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table


@dataclass
class Metrics:
    accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    rows: int


def default_db_path() -> Path:
    root = Path(__file__).parent.parent
    p_main = root / "data.sqlite"
    p_fn = root / "rugby-ai-predictor" / "data.sqlite"
    return p_main if p_main.exists() else p_fn


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
    exclude = {
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
    feature_cols = [c for c in df.columns if c not in exclude and not df[c].isna().all()]
    X = df[feature_cols].fillna(0).values
    y_w = (df["home_score"] > df["away_score"]).astype(int).values
    y_h = df["home_score"].values
    y_a = df["away_score"].values
    return X, y_w, y_h, y_a, feature_cols


def chrono_split(
    X: np.ndarray, y_w: np.ndarray, y_h: np.ndarray, y_a: np.ndarray, holdout_ratio: float
) -> Dict[str, np.ndarray]:
    n = len(X)
    idx = int(round(n * (1.0 - holdout_ratio)))
    idx = max(40, min(idx, n - 12))
    return {
        "X_train": X[:idx],
        "X_test": X[idx:],
        "y_w_train": y_w[:idx],
        "y_w_test": y_w[idx:],
        "y_h_train": y_h[:idx],
        "y_h_test": y_h[idx:],
        "y_a_train": y_a[:idx],
        "y_a_test": y_a[idx:],
    }


def baseline_xgb_triplet() -> Dict[str, Any]:
    return {
        "family": "xgb",
        "params": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.10,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1.0,
            "reg_lambda": 1.0,
        },
    }


def make_xgb_classifier(params: Dict[str, Any]) -> Any:
    return xgb.XGBClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=params.get("random_state", 42),
        eval_metric="logloss",
    )


def make_xgb_regressor(params: Dict[str, Any]) -> Any:
    return xgb.XGBRegressor(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=params.get("random_state", 42),
        eval_metric="mae",
    )


def instantiate_triplet(spec: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    fam = spec["family"]
    p = spec["params"]
    seed = p.get("random_state", 42)
    if fam == "xgb":
        return make_xgb_classifier(p), make_xgb_regressor(p), make_xgb_regressor(p)
    if fam == "rf":
        clf = RandomForestClassifier(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_h = RandomForestRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_a = RandomForestRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        return clf, reg_h, reg_a
    if fam == "et":
        clf = ExtraTreesClassifier(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_h = ExtraTreesRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_a = ExtraTreesRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        return clf, reg_h, reg_a
    if fam == "hgb":
        clf = HistGradientBoostingClassifier(
            max_depth=p["max_depth"],
            learning_rate=p["learning_rate"],
            max_iter=p["max_iter"],
            random_state=seed,
        )
        reg_h = HistGradientBoostingRegressor(
            max_depth=p["max_depth"],
            learning_rate=p["learning_rate"],
            max_iter=p["max_iter"],
            random_state=seed,
        )
        reg_a = HistGradientBoostingRegressor(
            max_depth=p["max_depth"],
            learning_rate=p["learning_rate"],
            max_iter=p["max_iter"],
            random_state=seed,
        )
        return clf, reg_h, reg_a
    raise ValueError(f"Unknown family: {fam}")


def sample_candidates(seed: int, per_family: int) -> List[Dict[str, Any]]:
    rnd = random.Random(seed)
    candidates: List[Dict[str, Any]] = []
    for _ in range(per_family):
        candidates.append(
            {
                "family": "xgb",
                "params": {
                    "n_estimators": rnd.choice([180, 260, 350, 500, 700]),
                    "max_depth": rnd.choice([3, 4, 5, 6, 7]),
                    "learning_rate": rnd.choice([0.03, 0.05, 0.08, 0.10, 0.12]),
                    "subsample": rnd.choice([0.75, 0.85, 0.95]),
                    "colsample_bytree": rnd.choice([0.75, 0.85, 0.95]),
                    "min_child_weight": rnd.choice([1.0, 2.0, 4.0, 6.0]),
                    "reg_lambda": rnd.choice([1.0, 1.5, 2.0, 3.0]),
                    "random_state": rnd.randint(1, 10000),
                },
            }
        )
        candidates.append(
            {
                "family": "rf",
                "params": {
                    "n_estimators": rnd.choice([250, 400, 600]),
                    "max_depth": rnd.choice([6, 8, 10, None]),
                    "min_samples_leaf": rnd.choice([1, 2, 3, 4]),
                    "random_state": rnd.randint(1, 10000),
                },
            }
        )
        candidates.append(
            {
                "family": "et",
                "params": {
                    "n_estimators": rnd.choice([250, 400, 600]),
                    "max_depth": rnd.choice([6, 8, 10, None]),
                    "min_samples_leaf": rnd.choice([1, 2, 3, 4]),
                    "random_state": rnd.randint(1, 10000),
                },
            }
        )
        candidates.append(
            {
                "family": "hgb",
                "params": {
                    "max_depth": rnd.choice([3, 4, 5, 6]),
                    "learning_rate": rnd.choice([0.03, 0.05, 0.08, 0.10]),
                    "max_iter": rnd.choice([200, 350, 500]),
                    "random_state": rnd.randint(1, 10000),
                },
            }
        )
    return candidates


def _family_of(row: Dict[str, Any]) -> str:
    return str(row.get("spec", {}).get("family", "unknown"))


def quantum_qubo_select_candidates(
    leaderboard: List[Dict[str, Any]],
    k: int,
    steps: int = 800,
    temperature: float = 1.2,
    cool_rate: float = 0.996,
    diversity_penalty: float = 0.015,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Quantum-inspired QUBO-style candidate selector (simulated annealing).
    Objective:
      maximize sum(cv_score) - diversity_penalty * family_collisions
    with hard constraint: choose exactly k items.
    """
    if not leaderboard:
        return []
    n = len(leaderboard)
    k = max(1, min(k, n))
    rng = random.Random(seed)

    # Start from greedy top-k by cv_score.
    ranked = sorted(range(n), key=lambda i: leaderboard[i]["cv_score"], reverse=True)
    state = [0] * n
    for i in ranked[:k]:
        state[i] = 1

    def energy(bits: List[int]) -> float:
        selected = [i for i, b in enumerate(bits) if b == 1]
        # Hard-cardinality penalty.
        card_pen = 5.0 * abs(len(selected) - k)
        score = sum(float(leaderboard[i]["cv_score"]) for i in selected)
        fams = [_family_of(leaderboard[i]) for i in selected]
        # Penalize duplicate families to diversify ensemble members.
        coll = len(fams) - len(set(fams))
        return -(score - diversity_penalty * coll) + card_pen

    best = state[:]
    best_e = energy(best)
    curr = state[:]
    curr_e = best_e
    temp = float(max(1e-4, temperature))

    for _ in range(max(100, steps)):
        # Swap move (keep cardinality close to k): turn one on->off and one off->on.
        on_idx = [i for i, b in enumerate(curr) if b == 1]
        off_idx = [i for i, b in enumerate(curr) if b == 0]
        if not on_idx or not off_idx:
            break
        i_off = rng.choice(on_idx)
        i_on = rng.choice(off_idx)
        nxt = curr[:]
        nxt[i_off] = 0
        nxt[i_on] = 1
        nxt_e = energy(nxt)
        de = nxt_e - curr_e
        if de <= 0 or rng.random() < math.exp(-de / max(temp, 1e-9)):
            curr, curr_e = nxt, nxt_e
            if curr_e < best_e:
                best, best_e = curr[:], curr_e
        temp *= cool_rate

    picked = [leaderboard[i] for i, b in enumerate(best) if b == 1]
    # Safety fallback.
    if len(picked) != k:
        picked = sorted(leaderboard, key=lambda r: r["cv_score"], reverse=True)[:k]
    return picked


def quantum_optimize_blend_weights(
    prob_matrix: np.ndarray,  # shape [n_models, n_samples]
    y_true: np.ndarray,
    steps: int = 1500,
    temperature: float = 1.0,
    cool_rate: float = 0.997,
    seed: int = 42,
) -> np.ndarray:
    """
    Quantum-inspired annealing optimizer over simplex weights for classification probs.
    Loss: logloss-like proxy (MSE on probabilities) + Brier-style term.
    """
    n_models = prob_matrix.shape[0]
    rng = np.random.default_rng(seed)
    w = np.ones(n_models, dtype=float) / n_models

    def loss(weights: np.ndarray) -> float:
        p = np.clip(np.sum(weights[:, None] * prob_matrix, axis=0), 1e-6, 1 - 1e-6)
        # Robust smooth loss.
        mse = float(np.mean((p - y_true) ** 2))
        ce = float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))
        return 0.6 * ce + 0.4 * mse

    best_w = w.copy()
    best_l = loss(w)
    curr_w = w.copy()
    curr_l = best_l
    temp = float(max(1e-4, temperature))

    for _ in range(max(200, steps)):
        # Propose random direction, project to simplex.
        delta = rng.normal(0.0, 0.08, size=n_models)
        nxt = np.clip(curr_w + delta, 1e-8, None)
        nxt = nxt / np.sum(nxt)
        nxt_l = loss(nxt)
        de = nxt_l - curr_l
        if de <= 0 or rng.random() < math.exp(-de / max(temp, 1e-9)):
            curr_w, curr_l = nxt, nxt_l
            if curr_l < best_l:
                best_w, best_l = curr_w.copy(), curr_l
        temp *= cool_rate
    return best_w


def expand_specs_with_seed_bagging(specs: List[Dict[str, Any]], seeds_per_spec: int, seed_base: int) -> List[Dict[str, Any]]:
    """
    Duplicate top specs across multiple seeds for variance reduction.
    This is a cheap way to "push harder" without huge architecture changes.
    """
    expanded: List[Dict[str, Any]] = []
    for i, spec in enumerate(specs):
        for j in range(max(1, seeds_per_spec)):
            cp = {
                "family": spec["family"],
                "params": dict(spec["params"]),
            }
            cp["params"]["random_state"] = int(seed_base + i * 97 + j * 17)
            expanded.append(cp)
    return expanded


def evaluate_candidate_on_timeseries(
    spec: Dict[str, Any],
    X: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    n_splits: int,
) -> Dict[str, Any]:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    accs: List[float] = []
    maes: List[float] = []

    for tr_idx, va_idx in tscv.split(X):
        X_tr, X_va = X[tr_idx], X[va_idx]
        y_w_tr, y_w_va = y_w[tr_idx], y_w[va_idx]
        y_h_tr, y_h_va = y_h[tr_idx], y_h[va_idx]
        y_a_tr, y_a_va = y_a[tr_idx], y_a[va_idx]

        if len(np.unique(y_w_tr)) < 2:
            continue

        clf, reg_h, reg_a = instantiate_triplet(spec)
        clf.fit(X_tr, y_w_tr)
        reg_h.fit(X_tr, y_h_tr)
        reg_a.fit(X_tr, y_a_tr)

        p_home = clf.predict_proba(X_va)[:, 1]
        y_w_pred = (p_home >= 0.5).astype(int)
        y_h_pred = reg_h.predict(X_va)
        y_a_pred = reg_a.predict(X_va)

        accs.append(float(accuracy_score(y_w_va, y_w_pred)))
        mae_h = float(mean_absolute_error(y_h_va, y_h_pred))
        mae_a = float(mean_absolute_error(y_a_va, y_a_pred))
        maes.append((mae_h + mae_a) / 2.0)

    if not accs:
        return {"spec": spec, "cv_acc": 0.0, "cv_mae": 999.0, "cv_score": -999.0}

    cv_acc = float(np.mean(accs))
    cv_mae = float(np.mean(maes))
    # Composite score rewards accuracy, penalizes MAE.
    cv_score = cv_acc - (cv_mae * 0.01)
    return {"spec": spec, "cv_acc": cv_acc, "cv_mae": cv_mae, "cv_score": cv_score}


def fit_models_from_specs(specs: List[Dict[str, Any]], X: np.ndarray, y_w: np.ndarray, y_h: np.ndarray, y_a: np.ndarray) -> List[Dict[str, Any]]:
    fitted: List[Dict[str, Any]] = []
    for s in specs:
        clf, reg_h, reg_a = instantiate_triplet(s)
        clf.fit(X, y_w)
        reg_h.fit(X, y_h)
        reg_a.fit(X, y_a)
        fitted.append({"spec": s, "clf": clf, "reg_h": reg_h, "reg_a": reg_a})
    return fitted


def blend_weights_from_leaderboard(top_rows: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    # Winner weights from cv accuracy; score weights from inverse cv MAE.
    accs = np.array([max(r["cv_acc"], 1e-6) for r in top_rows], dtype=float)
    inv_mae = np.array([1.0 / max(r["cv_mae"], 1e-6) for r in top_rows], dtype=float)
    w_prob = (accs / accs.sum()).tolist()
    w_score = (inv_mae / inv_mae.sum()).tolist()
    return w_prob, w_score


def calibrate_probs(raw_probs: np.ndarray, y_true: np.ndarray) -> IsotonicRegression:
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_probs, y_true)
    return iso


def evaluate_fitted_ensemble(
    fitted: List[Dict[str, Any]],
    w_prob: List[float],
    w_score: List[float],
    calibrator: IsotonicRegression | None,
    X_test: np.ndarray,
    y_w_test: np.ndarray,
    y_h_test: np.ndarray,
    y_a_test: np.ndarray,
) -> Metrics:
    p_parts = []
    h_parts = []
    a_parts = []
    for row in fitted:
        p_parts.append(row["clf"].predict_proba(X_test)[:, 1])
        h_parts.append(row["reg_h"].predict(X_test))
        a_parts.append(row["reg_a"].predict(X_test))

    p_blend = np.sum([w_prob[i] * p_parts[i] for i in range(len(fitted))], axis=0)
    if calibrator is not None:
        p_blend = calibrator.transform(p_blend)
    y_w_pred = (p_blend >= 0.5).astype(int)

    h_blend = np.sum([w_score[i] * h_parts[i] for i in range(len(fitted))], axis=0)
    a_blend = np.sum([w_score[i] * a_parts[i] for i in range(len(fitted))], axis=0)

    mae_h = float(mean_absolute_error(y_h_test, h_blend))
    mae_a = float(mean_absolute_error(y_a_test, a_blend))
    return Metrics(
        accuracy=float(accuracy_score(y_w_test, y_w_pred)),
        home_mae=mae_h,
        away_mae=mae_a,
        overall_mae=(mae_h + mae_a) / 2.0,
        rows=len(X_test),
    )


def choose_winner_mode(
    current_m: Metrics,
    maz_m: Metrics,
    min_acc_gain: float,
    min_mae_reduction: float,
    max_mae_worsen_for_winner_head: float,
    max_acc_drop_for_score_head: float,
) -> str:
    """
    Multi-mode promotion logic:
    - MAZ_MAXED: strict better (accuracy up and MAE not worse)
    - MAZ_WINNER_HEAD: clear accuracy gain, MAE worsen is small/tolerable
    - MAZ_SCORE_HEAD: clear MAE gain, accuracy drop is small/tolerable
    - CURRENT / TIE_OR_TRADEOFF
    """
    acc_gain = maz_m.accuracy - current_m.accuracy
    mae_reduction = current_m.overall_mae - maz_m.overall_mae

    if acc_gain >= min_acc_gain and mae_reduction >= 0.0:
        return "MAZ_MAXED"

    if acc_gain >= min_acc_gain and (-mae_reduction) <= max_mae_worsen_for_winner_head:
        return "MAZ_WINNER_HEAD"

    if mae_reduction >= min_mae_reduction and (-acc_gain) <= max_acc_drop_for_score_head:
        return "MAZ_SCORE_HEAD"

    current_better = (current_m.accuracy > maz_m.accuracy) and (current_m.overall_mae <= maz_m.overall_mae)
    if current_better:
        return "CURRENT"

    return "TIE_OR_TRADEOFF"


def train_baseline(
    X_train: np.ndarray, y_w_train: np.ndarray, y_h_train: np.ndarray, y_a_train: np.ndarray
) -> Tuple[Any, Any, Any]:
    b = baseline_xgb_triplet()
    clf, reg_h, reg_a = instantiate_triplet(b)
    clf.fit(X_train, y_w_train)
    reg_h.fit(X_train, y_h_train)
    reg_a.fit(X_train, y_a_train)
    return clf, reg_h, reg_a


def eval_triplet(clf: Any, reg_h: Any, reg_a: Any, X_test: np.ndarray, y_w_test: np.ndarray, y_h_test: np.ndarray, y_a_test: np.ndarray) -> Metrics:
    p_home = clf.predict_proba(X_test)[:, 1]
    y_w_pred = (p_home >= 0.5).astype(int)
    y_h_pred = reg_h.predict(X_test)
    y_a_pred = reg_a.predict(X_test)
    mae_h = float(mean_absolute_error(y_h_test, y_h_pred))
    mae_a = float(mean_absolute_error(y_a_test, y_a_pred))
    return Metrics(
        accuracy=float(accuracy_score(y_w_test, y_w_pred)),
        home_mae=mae_h,
        away_mae=mae_a,
        overall_mae=(mae_h + mae_a) / 2.0,
        rows=len(X_test),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MAZ Boss MAXED unseen benchmark vs current brain.")
    parser.add_argument("--db-path", default=None, help="SQLite path (auto-detect by default).")
    parser.add_argument("--league-id", type=int, default=None, help="Single league id.")
    parser.add_argument("--all-leagues", action="store_true", help="Run all leagues.")
    parser.add_argument("--holdout-ratio", type=float, default=0.2, help="Chronological unseen holdout ratio.")
    parser.add_argument("--min-games", type=int, default=90, help="Minimum completed games per league.")
    parser.add_argument("--search-rounds", type=int, default=3, help="Candidate rounds per family.")
    parser.add_argument("--top-k", type=int, default=4, help="Top candidates to blend.")
    parser.add_argument("--cv-splits", type=int, default=4, help="Inner time-series CV splits.")
    parser.add_argument("--save-maz-models", action="store_true", help="Save winning MAZ models.")
    parser.add_argument("--seed-bagging", type=int, default=2, help="Seed replicas per top spec in final ensemble.")
    parser.add_argument("--min-acc-gain", type=float, default=0.005, help="Minimum accuracy gain to treat as meaningful.")
    parser.add_argument("--min-mae-reduction", type=float, default=0.05, help="Minimum MAE reduction to treat as meaningful.")
    parser.add_argument("--max-mae-worsen-winner-head", type=float, default=0.20, help="Allowed MAE worsen when winner accuracy is clearly better.")
    parser.add_argument("--max-acc-drop-score-head", type=float, default=0.02, help="Allowed accuracy drop when MAE is clearly better.")
    parser.add_argument("--quantum-mode", action="store_true", help="Enable quantum-inspired QUBO selection and annealed blend optimization.")
    parser.add_argument("--quantum-steps", type=int, default=1200, help="Annealing steps for quantum-inspired optimizers.")
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
            "search_rounds": args.search_rounds,
            "top_k": args.top_k,
            "cv_splits": args.cv_splits,
            "seed_bagging": args.seed_bagging,
            "min_acc_gain": args.min_acc_gain,
            "min_mae_reduction": args.min_mae_reduction,
            "max_mae_worsen_winner_head": args.max_mae_worsen_winner_head,
            "max_acc_drop_score_head": args.max_acc_drop_score_head,
            "quantum_mode": bool(args.quantum_mode),
            "quantum_steps": args.quantum_steps,
        },
        "summary": {
            "tested": 0,
            "maz_wins_strict": 0,
            "maz_wins_winner_head": 0,
            "maz_wins_score_head": 0,
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
        split = chrono_split(X, y_w, y_h, y_a, args.holdout_ratio)

        # Current brain baseline.
        b_clf, b_h, b_a = train_baseline(
            split["X_train"], split["y_w_train"], split["y_h_train"], split["y_a_train"]
        )
        current_m = eval_triplet(
            b_clf, b_h, b_a,
            split["X_test"], split["y_w_test"], split["y_h_test"], split["y_a_test"]
        )

        # Inner calibration split from train.
        X_tr = split["X_train"]
        y_w_tr = split["y_w_train"]
        y_h_tr = split["y_h_train"]
        y_a_tr = split["y_a_train"]
        cut = int(round(len(X_tr) * 0.85))
        cut = max(40, min(cut, len(X_tr) - 10))

        X_fit, X_val = X_tr[:cut], X_tr[cut:]
        y_w_fit, y_w_val = y_w_tr[:cut], y_w_tr[cut:]
        y_h_fit, y_h_val = y_h_tr[:cut], y_h_tr[cut:]
        y_a_fit, y_a_val = y_a_tr[:cut], y_a_tr[cut:]

        # Candidate search.
        candidates = sample_candidates(seed=league_id + 42, per_family=args.search_rounds)
        leaderboard: List[Dict[str, Any]] = []
        for spec in candidates:
            row = evaluate_candidate_on_timeseries(
                spec, X_fit, y_w_fit, y_h_fit, y_a_fit, n_splits=args.cv_splits
            )
            leaderboard.append(row)
        leaderboard.sort(key=lambda r: r["cv_score"], reverse=True)
        if args.quantum_mode:
            top_rows = quantum_qubo_select_candidates(
                leaderboard,
                k=max(1, args.top_k),
                steps=args.quantum_steps,
                seed=league_id * 13 + 42,
            )
        else:
            top_rows = leaderboard[: max(1, args.top_k)]
        top_specs = [r["spec"] for r in top_rows]
        final_specs = expand_specs_with_seed_bagging(
            top_specs,
            seeds_per_spec=args.seed_bagging,
            seed_base=league_id * 101 + 7,
        )

        # Fit top ensemble on fit split.
        fitted = fit_models_from_specs(final_specs, X_fit, y_w_fit, y_h_fit, y_a_fit)
        w_prob, w_score = blend_weights_from_leaderboard(top_rows)
        # Expand blend weights to seed-bagged members (same base weight per replicated spec).
        if len(final_specs) != len(top_rows):
            rep = max(1, args.seed_bagging)
            w_prob = [x / rep for x in w_prob for _ in range(rep)]
            w_score = [x / rep for x in w_score for _ in range(rep)]

        # Quantum-inspired blend optimization on validation probabilities.
        if args.quantum_mode and len(fitted) > 1:
            prob_mat = np.array([row["clf"].predict_proba(X_val)[:, 1] for row in fitted], dtype=float)
            q_w = quantum_optimize_blend_weights(
                prob_mat,
                y_w_val.astype(float),
                steps=args.quantum_steps,
                seed=league_id * 19 + 7,
            )
            w_prob = q_w.tolist()

        # Calibrate on validation probabilities.
        val_probs = []
        for i, row in enumerate(fitted):
            p = row["clf"].predict_proba(X_val)[:, 1]
            val_probs.append(w_prob[i] * p)
        val_blend = np.sum(val_probs, axis=0)
        calibrator = calibrate_probs(val_blend, y_w_val) if len(np.unique(y_w_val)) > 1 else None

        # Refit top specs on full training split.
        fitted_full = fit_models_from_specs(final_specs, X_tr, y_w_tr, y_h_tr, y_a_tr)
        maz_m = evaluate_fitted_ensemble(
            fitted_full,
            w_prob,
            w_score,
            calibrator,
            split["X_test"],
            split["y_w_test"],
            split["y_h_test"],
            split["y_a_test"],
        )

        winner = choose_winner_mode(
            current_m,
            maz_m,
            min_acc_gain=args.min_acc_gain,
            min_mae_reduction=args.min_mae_reduction,
            max_mae_worsen_for_winner_head=args.max_mae_worsen_winner_head,
            max_acc_drop_for_score_head=args.max_acc_drop_score_head,
        )
        if winner == "MAZ_MAXED":
            report["summary"]["maz_wins_strict"] += 1
        elif winner == "MAZ_WINNER_HEAD":
            report["summary"]["maz_wins_winner_head"] += 1
        elif winner == "MAZ_SCORE_HEAD":
            report["summary"]["maz_wins_score_head"] += 1
        elif winner == "CURRENT":
            report["summary"]["current_wins"] += 1
        else:
            report["summary"]["ties"] += 1
        report["summary"]["tested"] += 1

        payload: Dict[str, Any] = {
            "name": league_name,
            "status": "tested",
            "games": len(df),
            "train_rows": int(len(split["X_train"])),
            "test_rows": int(len(split["X_test"])),
            "feature_count": len(feature_cols),
            "current": current_m.__dict__,
            "maz_maxed": maz_m.__dict__,
            "deltas": {
                "accuracy_gain": maz_m.accuracy - current_m.accuracy,
                "overall_mae_reduction": current_m.overall_mae - maz_m.overall_mae,
            },
            "winner": winner,
            "top_candidate_cv": top_rows,
            "final_member_count": len(final_specs),
            "blend_weights": {"winner": w_prob, "score": w_score},
            "calibrated": calibrator is not None,
        }

        if args.save_maz_models and winner.startswith("MAZ_"):
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"league_{league_id}_model_maz_maxed_{winner.lower()}.pkl"
            with out_file.open("wb") as f:
                pickle.dump(
                    {
                        "league_id": league_id,
                        "league_name": league_name,
                        "model_type": "maz_maxed_ensemble",
                        "trained_at": datetime.now().isoformat(),
                        "feature_columns": feature_cols,
                        "specs": final_specs,
                        "blend_weights": {"winner": w_prob, "score": w_score},
                        "calibrator": calibrator,
                        "models": fitted_full,
                        "metrics_unseen": maz_m.__dict__,
                        "baseline_unseen": current_m.__dict__,
                        "winner_mode": winner,
                    },
                    f,
                )
            payload["saved_model"] = str(out_file)

        report["leagues"][str(league_id)] = payload
        print(
            f"[{league_name}] current_acc={current_m.accuracy:.3f} maz_acc={maz_m.accuracy:.3f} | "
            f"current_mae={current_m.overall_mae:.3f} maz_mae={maz_m.overall_mae:.3f} | winner={winner}"
        )

    conn.close()

    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"maz_maxed_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== MAZ MAXED Summary ===")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved: {out_file}")


if __name__ == "__main__":
    main()

