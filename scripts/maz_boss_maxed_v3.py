#!/usr/bin/env python3
"""
MAZ Boss MAXED V3

Production-oriented, league-adaptive system:
- Global winner/score core across leagues
- Dynamic attack/defense rating features
- Score-distribution winner probability
- League residual correction in log-odds space
- Regime-aware blending + calibration
- Guardrail-based promotion vs current baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import pickle
import sqlite3
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
try:
    from scipy.linalg import LinAlgWarning
except Exception:
    LinAlgWarning = Warning

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
except Exception:
    print("XGBoost is required. Install with: pip install xgboost")
    raise

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table


EPS = 1e-9
V3_VERSION = "v3"
LOG = logging.getLogger("maz_v3")


@dataclass
class Metrics:
    outcome_accuracy: float
    winner_accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    brier_winner: float
    rows: int


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _logit(p: np.ndarray) -> np.ndarray:
    p2 = np.clip(p, 1e-6, 1.0 - 1e-6)
    return np.log(p2 / (1.0 - p2))


def _parse_int_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).split(","):
        p = part.strip()
        if not p:
            continue
        out.append(int(p))
    return out


def _parse_float_list(text: str) -> List[float]:
    out: List[float] = []
    for part in str(text).split(","):
        p = part.strip()
        if not p:
            continue
        out.append(float(p))
    return out


def _setup_logging(log_level: str, log_file: Optional[str]) -> None:
    level = getattr(logging, str(log_level).upper(), logging.INFO)
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        lp = Path(log_file)
        lp.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(lp, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def prune_features_by_correlation(
    X: np.ndarray,
    feature_cols: List[str],
    threshold: float,
) -> Tuple[np.ndarray, List[str]]:
    if threshold <= 0 or X.shape[1] <= 1:
        return X, feature_cols
    # Drop zero-variance columns before correlation to avoid divide-by-zero warnings.
    std = np.std(X, axis=0)
    var_keep = std > 1e-12
    if not np.any(var_keep):
        return X, feature_cols
    X_work = X[:, var_keep]
    cols_work = [c for c, k in zip(feature_cols, var_keep) if bool(k)]

    # Correlation-based pruning on filtered matrix.
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.corrcoef(X_work, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    keep = np.ones(X_work.shape[1], dtype=bool)
    for i in range(X_work.shape[1]):
        if not keep[i]:
            continue
        for j in range(i + 1, X_work.shape[1]):
            if keep[j] and abs(float(corr[i, j])) >= threshold:
                keep[j] = False
    idx = np.where(keep)[0]
    cols = [cols_work[i] for i in idx]
    return X_work[:, idx], cols


def default_db_path() -> Path:
    root = Path(__file__).parent.parent
    p_main = root / "data.sqlite"
    p_fn = root / "rugby-ai-predictor" / "data.sqlite"
    return p_main if p_main.exists() else p_fn


def load_all_df(conn: sqlite3.Connection, league_ids: Sequence[int]) -> pd.DataFrame:
    cfg = FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False)
    df = build_feature_table(conn, cfg)
    df = df[df["league_id"].isin(list(league_ids))].copy()
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    if df.empty:
        return df
    df.sort_values(["date_event", "event_id"], inplace=True)
    return df


def _team_key(team_id: Any) -> int:
    try:
        return int(team_id)
    except Exception:
        return -1


def add_dynamic_ratings(
    df: pd.DataFrame,
    rating_k: float,
    rating_decay: float,
    home_adv_k: float,
) -> pd.DataFrame:
    out = df.copy()
    for c in [
        "v3_home_attack",
        "v3_home_defense",
        "v3_away_attack",
        "v3_away_defense",
        "v3_home_adv",
        "v3_expected_home",
        "v3_expected_away",
        "v3_rating_gap",
        "v3_rating_confidence",
    ]:
        out[c] = 0.0

    for league_id, gidx in out.groupby("league_id").groups.items():
        rows = list(gidx)
        att: Dict[int, float] = {}
        dfn: Dict[int, float] = {}
        hadv: Dict[int, float] = {}
        games: Dict[int, int] = {}
        league_mean = float(
            0.5
            * (
                out.loc[rows, "home_score"].astype(float).mean()
                + out.loc[rows, "away_score"].astype(float).mean()
            )
        )
        if not np.isfinite(league_mean):
            league_mean = 20.0

        for ridx in rows:
            h = _team_key(out.at[ridx, "home_team_id"])
            a = _team_key(out.at[ridx, "away_team_id"])
            hs = float(out.at[ridx, "home_score"])
            as_ = float(out.at[ridx, "away_score"])

            h_att = att.get(h, 0.0)
            h_def = dfn.get(h, 0.0)
            a_att = att.get(a, 0.0)
            a_def = dfn.get(a, 0.0)
            h_home_adv = hadv.get(h, 0.0)
            conf = min(1.0, (games.get(h, 0) + games.get(a, 0)) / 40.0)

            exp_h = league_mean + h_att - a_def + h_home_adv
            exp_a = league_mean + a_att - h_def

            out.at[ridx, "v3_home_attack"] = h_att
            out.at[ridx, "v3_home_defense"] = h_def
            out.at[ridx, "v3_away_attack"] = a_att
            out.at[ridx, "v3_away_defense"] = a_def
            out.at[ridx, "v3_home_adv"] = h_home_adv
            out.at[ridx, "v3_expected_home"] = exp_h
            out.at[ridx, "v3_expected_away"] = exp_a
            out.at[ridx, "v3_rating_gap"] = (h_att - a_def + h_home_adv) - (a_att - h_def)
            out.at[ridx, "v3_rating_confidence"] = conf

            # Decay
            att[h] = rating_decay * h_att
            att[a] = rating_decay * a_att
            dfn[h] = rating_decay * h_def
            dfn[a] = rating_decay * a_def
            hadv[h] = rating_decay * h_home_adv

            # Update
            err_h = hs - exp_h
            err_a = as_ - exp_a
            att[h] = att.get(h, 0.0) + (rating_k * err_h)
            att[a] = att.get(a, 0.0) + (rating_k * err_a)
            dfn[h] = dfn.get(h, 0.0) + (rating_k * (-err_a))
            dfn[a] = dfn.get(a, 0.0) + (rating_k * (-err_h))
            hadv[h] = hadv.get(h, 0.0) + (home_adv_k * err_h)
            games[h] = games.get(h, 0) + 1
            games[a] = games.get(a, 0) + 1
    return out


def league_regimes(df: pd.DataFrame) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid, g in df.groupby("league_id"):
        hs = g["home_score"].astype(float).values
        as_ = g["away_score"].astype(float).values
        n = len(g)
        if n == 0:
            continue
        margins = hs - as_
        winner = (margins > 0).astype(int)
        draw = (margins == 0).astype(int)
        abs_margin = np.abs(margins)
        upset = np.mean(abs_margin <= np.percentile(abs_margin, 35.0)) if n > 10 else 0.0
        home_adv = float(np.mean(margins))
        score_var = float(np.var(np.concatenate([hs, as_], axis=0)))
        draw_rate = float(np.mean(draw))
        upset_rate = float(upset)

        # Dominance proxy via team home-win concentration
        team_wins: Dict[int, int] = {}
        team_games: Dict[int, int] = {}
        for _, r in g.iterrows():
            h = _team_key(r["home_team_id"])
            a = _team_key(r["away_team_id"])
            hw = int(float(r["home_score"]) > float(r["away_score"]))
            aw = int(float(r["away_score"]) > float(r["home_score"]))
            team_wins[h] = team_wins.get(h, 0) + hw
            team_wins[a] = team_wins.get(a, 0) + aw
            team_games[h] = team_games.get(h, 0) + 1
            team_games[a] = team_games.get(a, 0) + 1
        rates = np.array(
            [team_wins[t] / max(1, team_games[t]) for t in team_games.keys()],
            dtype=float,
        )
        dominance = float(np.std(rates)) if len(rates) else 0.0

        if n < 140:
            regime = "chaotic_small_sample"
        elif score_var > 140.0 or upset_rate > 0.42:
            regime = "high_variance"
        elif dominance > 0.17 and abs(home_adv) > 3.0:
            regime = "stable_dominant"
        else:
            regime = "balanced_competitive"

        out[int(lid)] = {
            "regime": regime,
            "rows": n,
            "draw_rate": draw_rate,
            "upset_rate": upset_rate,
            "score_var": score_var,
            "home_adv": home_adv,
            "dominance": dominance,
        }
    return out


def add_regime_columns(df: pd.DataFrame, regime_map: Dict[int, Dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    out["v3_regime_code"] = 1.0
    out["v3_draw_rate"] = 0.0
    out["v3_upset_rate"] = 0.0
    out["v3_score_var"] = 0.0
    out["v3_home_adv_league"] = 0.0
    out["v3_dominance"] = 0.0
    mapper = {
        "stable_dominant": 0.0,
        "balanced_competitive": 1.0,
        "high_variance": 2.0,
        "chaotic_small_sample": 3.0,
    }
    for lid, meta in regime_map.items():
        m = out["league_id"] == lid
        out.loc[m, "v3_regime_code"] = mapper.get(meta["regime"], 1.0)
        out.loc[m, "v3_draw_rate"] = float(meta["draw_rate"])
        out.loc[m, "v3_upset_rate"] = float(meta["upset_rate"])
        out.loc[m, "v3_score_var"] = float(meta["score_var"])
        out.loc[m, "v3_home_adv_league"] = float(meta["home_adv"])
        out.loc[m, "v3_dominance"] = float(meta["dominance"])
    return out


def prepare_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    y_h = df["home_score"].astype(float).values
    y_a = df["away_score"].astype(float).values
    y_w = (y_h > y_a).astype(int)
    y_out = np.where(y_h > y_a, 2, np.where(y_h < y_a, 0, 1)).astype(int)
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
    cols = [c for c in df.columns if c not in exclude and not df[c].isna().all()]
    X = df[cols].fillna(0.0).astype(float).values
    return X, y_out, y_w, y_h, y_a, cols


def train_global_core(
    X: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    seed: int,
    depth: Optional[int] = None,
    lr_mult: float = 1.0,
) -> Dict[str, Any]:
    md = int(depth) if depth is not None else 6
    lr = float(0.05 * max(0.5, min(1.5, lr_mult)))
    clf = xgb.XGBClassifier(
        n_estimators=520,
        max_depth=md,
        learning_rate=lr,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=2.0,
        reg_lambda=2.0,
        random_state=seed,
        eval_metric="logloss",
    )
    reg_h = xgb.XGBRegressor(
        n_estimators=480,
        max_depth=md,
        learning_rate=lr,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=2.0,
        reg_lambda=2.0,
        random_state=seed + 1,
        eval_metric="mae",
    )
    reg_a = xgb.XGBRegressor(
        n_estimators=480,
        max_depth=md,
        learning_rate=lr,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=2.0,
        reg_lambda=2.0,
        random_state=seed + 2,
        eval_metric="mae",
    )
    clf.fit(X, y_w)
    reg_h.fit(X, y_h)
    reg_a.fit(X, y_a)
    return {"winner": clf, "home": reg_h, "away": reg_a}


def train_current_baseline(
    X: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    seed: int,
    depth: Optional[int] = None,
    lr_mult: float = 1.0,
) -> Dict[str, Any]:
    md = int(depth) if depth is not None else 6
    lr = float(0.08 * max(0.5, min(1.5, lr_mult)))
    clf = xgb.XGBClassifier(
        n_estimators=220,
        max_depth=md,
        learning_rate=lr,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=1.0,
        reg_lambda=1.0,
        random_state=seed,
        eval_metric="logloss",
    )
    reg_h = xgb.XGBRegressor(
        n_estimators=220,
        max_depth=md,
        learning_rate=lr,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=1.0,
        reg_lambda=1.0,
        random_state=seed + 1,
        eval_metric="mae",
    )
    reg_a = xgb.XGBRegressor(
        n_estimators=220,
        max_depth=md,
        learning_rate=lr,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=1.0,
        reg_lambda=1.0,
        random_state=seed + 2,
        eval_metric="mae",
    )
    clf.fit(X, y_w)
    reg_h.fit(X, y_h)
    reg_a.fit(X, y_a)
    return {"winner": clf, "home": reg_h, "away": reg_a}


def train_ensemble(
    trainer,
    X: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    seeds: Sequence[int],
    depths: Sequence[int],
    lr_mults: Sequence[float],
) -> List[Dict[str, Any]]:
    models: List[Dict[str, Any]] = []
    dflt_depth = int(depths[0]) if depths else 6
    dflt_lr = float(lr_mults[0]) if lr_mults else 1.0
    for i, s in enumerate(seeds):
        d = int(depths[i]) if i < len(depths) else dflt_depth
        lrm = float(lr_mults[i]) if i < len(lr_mults) else dflt_lr
        models.append(trainer(X, y_w, y_h, y_a, seed=int(s), depth=d, lr_mult=lrm))
    return models


def predict_ensemble(models: List[Dict[str, Any]], X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    p_parts = []
    h_parts = []
    a_parts = []
    for m in models:
        p_parts.append(np.clip(m["winner"].predict_proba(X)[:, 1], 1e-6, 1.0 - 1e-6))
        h_parts.append(m["home"].predict(X))
        a_parts.append(m["away"].predict(X))
    p_mat = np.vstack(p_parts)
    h_mat = np.vstack(h_parts)
    a_mat = np.vstack(a_parts)
    return np.mean(p_mat, axis=0), np.mean(h_mat, axis=0), np.mean(a_mat, axis=0), np.std(p_mat, axis=0)


def select_alpha_from_validation(
    p_cls_train: np.ndarray,
    p_home_sd_train: np.ndarray,
    y_w_train: np.ndarray,
    candidates: Sequence[float],
) -> Tuple[float, float, float]:
    n = len(y_w_train)
    cut = int(round(n * 0.8))
    cut = max(20, min(cut, n - 10))
    p_cls_val = p_cls_train[cut:]
    p_sd_val = p_home_sd_train[cut:]
    y_val = y_w_train[cut:]
    best_alpha = float(candidates[0]) if candidates else 0.5
    best_brier = float("inf")
    best_acc = -1.0
    for a in candidates:
        alpha = float(a)
        p = np.clip((alpha * p_cls_val) + ((1.0 - alpha) * p_sd_val), 1e-6, 1.0 - 1e-6)
        brier = float(np.mean((p - y_val) ** 2))
        acc = float(np.mean((p >= 0.5).astype(int) == y_val))
        if brier < best_brier - 1e-12 or (abs(brier - best_brier) <= 1e-12 and acc > best_acc):
            best_alpha = alpha
            best_brier = brier
            best_acc = acc
    return best_alpha, best_brier, best_acc


def select_alpha_rolling(
    p_cls_train: np.ndarray,
    p_home_sd_train: np.ndarray,
    y_w_train: np.ndarray,
    candidates: Sequence[float],
    step: int,
) -> Tuple[float, float, float]:
    n = len(y_w_train)
    if n < 50:
        return select_alpha_from_validation(p_cls_train, p_home_sd_train, y_w_train, candidates)
    s = max(5, int(step))
    start = max(40, int(round(n * 0.5)))
    windows: List[Tuple[int, int]] = []
    for cut in range(start, n - 4, s):
        end = min(n, cut + s)
        if end - cut >= 5:
            windows.append((cut, end))
    if not windows:
        return select_alpha_from_validation(p_cls_train, p_home_sd_train, y_w_train, candidates)
    best_alpha = float(candidates[0]) if candidates else 0.5
    best_brier = float("inf")
    best_acc = -1.0
    for a in candidates:
        alpha = float(a)
        briers = []
        accs = []
        for lo, hi in windows:
            p = np.clip((alpha * p_cls_train[lo:hi]) + ((1.0 - alpha) * p_home_sd_train[lo:hi]), 1e-6, 1.0 - 1e-6)
            y = y_w_train[lo:hi]
            briers.append(float(np.mean((p - y) ** 2)))
            accs.append(float(np.mean((p >= 0.5).astype(int) == y)))
        mb = float(np.mean(briers))
        ma = float(np.mean(accs))
        if mb < best_brier - 1e-12 or (abs(mb - best_brier) <= 1e-12 and ma > best_acc):
            best_alpha = alpha
            best_brier = mb
            best_acc = ma
    return best_alpha, best_brier, best_acc


def fit_meta_stacker(
    X_meta_train: np.ndarray,
    y_train: np.ndarray,
    X_meta_test: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    scaler = StandardScaler(with_mean=True, with_std=True)
    xtr = scaler.fit_transform(X_meta_train)
    xte = scaler.transform(X_meta_test)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        lr = LogisticRegression(max_iter=3000, solver="lbfgs")
        lr.fit(xtr, y_train)
    p_train = np.clip(lr.predict_proba(xtr)[:, 1], 1e-6, 1.0 - 1.0e-6)
    p_test = np.clip(lr.predict_proba(xte)[:, 1], 1e-6, 1.0 - 1.0e-6)
    return p_train, p_test


def _poisson_trunc(mu: float, max_score: int) -> np.ndarray:
    lam = max(1e-4, float(mu))
    k = np.arange(max_score + 1, dtype=float)
    logp = (k * np.log(lam)) - lam - np.array([math.lgamma(float(i) + 1.0) for i in k], dtype=float)
    p = np.exp(logp)
    s = np.sum(p)
    if s <= 0:
        return np.ones(max_score + 1, dtype=float) / float(max_score + 1)
    return p / s


def score_distribution_probs(mu_h: np.ndarray, mu_a: np.ndarray, max_score: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(mu_h)
    p_home = np.zeros(n, dtype=float)
    p_draw = np.zeros(n, dtype=float)
    p_away = np.zeros(n, dtype=float)
    for i in range(n):
        ph = _poisson_trunc(float(mu_h[i]), max_score)
        pa = _poisson_trunc(float(mu_a[i]), max_score)
        cdf_a = np.cumsum(pa)
        home_win = 0.0
        draw = 0.0
        for hs in range(max_score + 1):
            if hs > 0:
                home_win += ph[hs] * cdf_a[hs - 1]
            draw += ph[hs] * pa[hs]
        away = max(0.0, 1.0 - home_win - draw)
        z = max(EPS, home_win + draw + away)
        p_home[i] = home_win / z
        p_draw[i] = draw / z
        p_away[i] = away / z
    return p_home, p_draw, p_away


def regime_alpha(meta: Dict[str, Any], alpha_stable: float, alpha_balanced: float, alpha_chaotic: float) -> float:
    r = str(meta.get("regime", "balanced_competitive"))
    if r == "stable_dominant":
        return alpha_stable
    if r == "balanced_competitive":
        return alpha_balanced
    return alpha_chaotic


def fit_residual_heads(
    X_league: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    p_base: np.ndarray,
    mu_h: np.ndarray,
    mu_a: np.ndarray,
    ridge_alpha: float,
    ridge_solver: str,
    adaptive_ridge_alpha: bool,
    hard_example_quantile: float,
    ridge_alpha_grid: Sequence[float],
) -> Dict[str, Any]:
    if len(X_league) < 40:
        return {"delta_logit": None, "delta_h": None, "delta_a": None}
    scaler = StandardScaler(with_mean=True, with_std=True)
    X_scaled = scaler.fit_transform(X_league)
    # Convergence warnings are common on high-dimensional rugby features; scaling + higher iter stabilizes this.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        p_local = (
            LogisticRegression(max_iter=3000, solver="lbfgs")
            .fit(X_scaled, y_w)
            .predict_proba(X_scaled)[:, 1]
        )
    target_delta = np.clip(_logit(p_local) - _logit(p_base), -1.0, 1.0)
    x_aug = np.hstack([X_league, _logit(p_base).reshape(-1, 1)])
    mask = np.ones(len(X_league), dtype=bool)
    if hard_example_quantile > 0.0:
        q = min(0.95, max(0.0, float(hard_example_quantile)))
        thr = float(np.quantile(np.abs(target_delta), q))
        mask = np.abs(target_delta) >= thr
        # Ensure enough rows remain for stable fitting.
        if int(np.sum(mask)) < 30:
            mask[:] = True
    x_aug = x_aug[mask]
    x_league_fit = X_league[mask]
    target_delta = target_delta[mask]
    y_h_fit = y_h[mask]
    y_a_fit = y_a[mask]
    mu_h_fit = mu_h[mask]
    mu_a_fit = mu_a[mask]
    n_train = max(1, len(x_league_fit))
    alpha_mult = 1.0
    if adaptive_ridge_alpha:
        alpha_mult = float(1.0 + (20.0 / (20.0 + float(n_train))))
    candidate_alphas = [float(ridge_alpha)]
    if ridge_alpha_grid:
        candidate_alphas = [float(a) for a in ridge_alpha_grid if float(a) > 0.0]
    candidate_alphas = [float(a * alpha_mult) for a in candidate_alphas]

    # Standardize residual inputs before ridge fitting for numerical stability.
    scaler_logit = StandardScaler(with_mean=True, with_std=True)
    x_aug_scaled = scaler_logit.fit_transform(x_aug)
    scaler_score = StandardScaler(with_mean=True, with_std=True)
    x_score_scaled = scaler_score.fit_transform(x_league_fit)
    cut = int(round(len(x_aug_scaled) * 0.8))
    cut = max(20, min(cut, len(x_aug_scaled) - 10))
    xtr = x_aug_scaled[:cut]
    xva = x_aug_scaled[cut:]
    ytr = target_delta[:cut]
    yva = target_delta[cut:]
    best_alpha = candidate_alphas[0]
    best_mse = float("inf")
    for a in candidate_alphas:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=LinAlgWarning)
            m = Ridge(alpha=float(a), solver=ridge_solver, random_state=42)
            m.fit(xtr, ytr)
            pred = m.predict(xva)
        mse = float(mean_squared_error(yva, pred))
        if mse < best_mse:
            best_mse = mse
            best_alpha = float(a)
    eff_alpha = float(best_alpha)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=LinAlgWarning)
        dlogit = Ridge(alpha=eff_alpha, solver=ridge_solver, random_state=42)
        dlogit.fit(x_aug_scaled, target_delta)
        dh = Ridge(alpha=eff_alpha, solver=ridge_solver, random_state=42).fit(x_score_scaled, y_h_fit - mu_h_fit)
        da = Ridge(alpha=eff_alpha, solver=ridge_solver, random_state=42).fit(x_score_scaled, y_a_fit - mu_a_fit)
    return {
        "delta_logit": dlogit,
        "delta_h": dh,
        "delta_a": da,
        "scaler_logit": scaler_logit,
        "scaler_score": scaler_score,
        "effective_alpha": eff_alpha,
    }


def fit_calibrator(
    p_raw: np.ndarray,
    y_w: np.ndarray,
    regime: str,
    min_isotonic_rows: int,
) -> Dict[str, Any]:
    p2 = np.clip(p_raw, 1e-6, 1.0 - 1e-6)
    classes = np.unique(y_w)
    if len(classes) < 2:
        # Chronological calibration windows can be single-class in smaller/noisy chunks.
        # Use a constant calibrator rather than failing the full run.
        const_p = float(np.clip(np.mean(y_w), 1e-6, 1.0 - 1e-6))
        return {"method": "constant", "p": const_p}
    if len(p2) >= min_isotonic_rows and regime in {"stable_dominant", "balanced_competitive"}:
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(p2, y_w)
        return {"method": "isotonic", "model": iso}
    # Platt-style logistic on logit(p)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        lr = LogisticRegression(max_iter=3000, solver="lbfgs")
        lr.fit(_logit(p2).reshape(-1, 1), y_w)
    return {"method": "platt", "model": lr}


def apply_calibrator(cal: Dict[str, Any], p_raw: np.ndarray) -> np.ndarray:
    p2 = np.clip(p_raw, 1e-6, 1.0 - 1e-6)
    if cal["method"] == "constant":
        return np.full(len(p2), float(np.clip(cal["p"], 1e-6, 1.0 - 1e-6)), dtype=float)
    if cal["method"] == "isotonic":
        return np.clip(cal["model"].predict(p2), 1e-6, 1.0 - 1e-6)
    x = _logit(p2).reshape(-1, 1)
    return np.clip(cal["model"].predict_proba(x)[:, 1], 1e-6, 1.0 - 1e-6)


def evaluate(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    pred_h: np.ndarray,
    pred_a: np.ndarray,
    y_out: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
) -> Metrics:
    probs = np.vstack([p_away, p_draw, p_home]).T
    y_out_pred = np.argmax(probs, axis=1)
    y_w_pred = (p_home >= p_away).astype(int)
    mae_h = float(mean_absolute_error(y_h, pred_h))
    mae_a = float(mean_absolute_error(y_a, pred_a))
    brier = float(np.mean((p_home - y_w) ** 2))
    return Metrics(
        outcome_accuracy=float(accuracy_score(y_out, y_out_pred)),
        winner_accuracy=float(accuracy_score(y_w, y_w_pred)),
        home_mae=mae_h,
        away_mae=mae_a,
        overall_mae=(mae_h + mae_a) / 2.0,
        brier_winner=brier,
        rows=len(y_out),
    )


def choose_winner(
    current: Metrics,
    v3: Metrics,
    min_winner_gain: float,
    max_mae_worsen: float,
    max_brier_worsen: float,
) -> str:
    gain = v3.winner_accuracy - current.winner_accuracy
    mae_red = current.overall_mae - v3.overall_mae
    brier_red = current.brier_winner - v3.brier_winner
    if gain >= min_winner_gain and mae_red >= -max_mae_worsen and brier_red >= -max_brier_worsen:
        if mae_red >= 0 and brier_red >= 0:
            return "V3_MAXED"
        return "V3_WINNER_HEAD"
    if mae_red >= 0 and gain >= -0.001:
        return "V3_SCORE_HEAD"
    return "CURRENT"


def build_masks_for_league(
    df: pd.DataFrame,
    league_id: int,
    holdout_ratio: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    lg = df[df["league_id"] == league_id].copy()
    if lg.empty:
        return np.zeros(len(df), dtype=bool), np.zeros(len(df), dtype=bool), np.zeros(len(df), dtype=bool)
    n = len(lg)
    split = int(round(n * (1.0 - holdout_ratio)))
    split = max(50, min(split, n - 10))
    split_date = lg.iloc[split]["date_event"]
    league_train = (df["league_id"] == league_id) & (df["date_event"] < split_date)
    league_test = (df["league_id"] == league_id) & (df["date_event"] >= split_date)
    global_train = df["date_event"] < split_date
    return global_train.values, league_train.values, league_test.values


def run_split(
    X_all: np.ndarray,
    y_out_all: np.ndarray,
    y_w_all: np.ndarray,
    y_h_all: np.ndarray,
    y_a_all: np.ndarray,
    gmask: np.ndarray,
    ltrain_mask: np.ndarray,
    ltest_mask: np.ndarray,
    regimes: Dict[int, Dict[str, Any]],
    league_id: int,
    args: argparse.Namespace,
    feature_cols: List[str],
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    t_last = t0

    def _stage(label: str) -> None:
        nonlocal t_last
        now = time.perf_counter()
        LOG.info(
            "[league_id=%s] %s | +%.2fs (total %.2fs)",
            league_id,
            label,
            now - t_last,
            now - t0,
        )
        t_last = now

    n_train = int(np.sum(ltrain_mask))
    n_test = int(np.sum(ltest_mask))
    if n_train < 40 or n_test < 1:
        return {"ok": False, "reason": f"insufficient split rows train={n_train}, test={n_test}"}
    LOG.info("[league_id=%s] split start: train=%s test=%s", league_id, n_train, n_test)

    Xg, ywg, yhg, yag = X_all[gmask], y_w_all[gmask], y_h_all[gmask], y_a_all[gmask]
    Xlt, ywlt, yhlt, yalt = X_all[ltrain_mask], y_w_all[ltrain_mask], y_h_all[ltrain_mask], y_a_all[ltrain_mask]
    Xte = X_all[ltest_mask]
    yout_te, yw_te, yh_te, ya_te = y_out_all[ltest_mask], y_w_all[ltest_mask], y_h_all[ltest_mask], y_a_all[ltest_mask]
    if len(Xg) < 60:
        return {"ok": False, "reason": f"insufficient global train rows {len(Xg)}"}
    _stage(f"prepared arrays (global={len(Xg)}, local_train={len(Xlt)}, test={len(Xte)})")

    cur_seeds = [int(s + league_id) for s in args._ensemble_seeds]
    current_models = train_ensemble(
        train_current_baseline,
        Xlt,
        ywlt,
        yhlt,
        yalt,
        cur_seeds,
        args._ensemble_depths,
        args._ensemble_lr_mults,
    )
    _stage(f"trained CURRENT ensemble (seeds={len(cur_seeds)})")
    p_cur, pred_h_cur, pred_a_cur, cur_unc = predict_ensemble(current_models, Xte)
    draw_rate_train = float(np.mean(y_out_all[ltrain_mask] == 1))
    p_draw_cur = np.full(len(Xte), max(0.05, min(0.35, draw_rate_train)), dtype=float)
    rem_cur = np.clip(1.0 - p_draw_cur, 1e-6, 1.0)
    p_home_cur = rem_cur * p_cur
    p_away_cur = rem_cur * (1.0 - p_cur)
    _stage("predicted CURRENT baseline")

    core_seeds = [int(s + 991 + league_id) for s in args._ensemble_seeds]
    core_models = train_ensemble(
        train_global_core,
        Xg,
        ywg,
        yhg,
        yag,
        core_seeds,
        args._ensemble_depths,
        args._ensemble_lr_mults,
    )
    _stage(f"trained V3 core ensemble (seeds={len(core_seeds)})")
    fi_top: List[Dict[str, Any]] = []
    fi_stack = []
    for m in core_models:
        fi = getattr(m["winner"], "feature_importances_", None)
        if fi is not None and len(fi) == len(feature_cols):
            fi_stack.append(np.asarray(fi, dtype=float))
    core_cols = list(feature_cols)
    core_keep_idx = np.arange(len(feature_cols))
    if fi_stack:
        fi_mean = np.mean(np.vstack(fi_stack), axis=0)
        if args.global_importance_prune_pct > 0.0 and len(fi_mean) > 10:
            keep_frac = max(0.1, min(0.98, 1.0 - float(args.global_importance_prune_pct)))
            keep_n = max(10, int(round(len(fi_mean) * keep_frac)))
            core_keep_idx = np.argsort(fi_mean)[::-1][:keep_n]
            core_cols = [feature_cols[i] for i in core_keep_idx]
            Xg_core = Xg[:, core_keep_idx]
            Xlt_core = Xlt[:, core_keep_idx]
            Xte_core = Xte[:, core_keep_idx]
            core_models = train_ensemble(
                train_global_core,
                Xg_core,
                ywg,
                yhg,
                yag,
                core_seeds,
                args._ensemble_depths,
                args._ensemble_lr_mults,
            )
            fi_stack = []
            for m in core_models:
                fi2 = getattr(m["winner"], "feature_importances_", None)
                if fi2 is not None and len(fi2) == len(core_cols):
                    fi_stack.append(np.asarray(fi2, dtype=float))
            if fi_stack:
                fi_mean = np.mean(np.vstack(fi_stack), axis=0)
            _stage(f"retrained pruned core ensemble (features={len(core_cols)})")
        else:
            Xg_core = Xg
            Xlt_core = Xlt
            Xte_core = Xte
        idx = np.argsort(fi_mean)[::-1][:20]
        fi_top = [
            {"feature": str(core_cols[i]), "importance": float(fi_mean[i])}
            for i in idx
            if float(fi_mean[i]) > 0.0
        ]
    else:
        Xg_core = Xg
        Xlt_core = Xlt
        Xte_core = Xte
    _stage(f"feature-importance pass complete (core_features={len(core_cols)})")
    p_cls_train, mu_h_train, mu_a_train, cls_unc_train = predict_ensemble(core_models, Xlt_core)
    p_cls_test, mu_h_test, mu_a_test, cls_unc = predict_ensemble(core_models, Xte_core)

    p_home_sd_train, p_draw_sd_train, p_away_sd_train = score_distribution_probs(mu_h_train, mu_a_train, args.max_score)
    p_home_sd_test, p_draw_sd_test, p_away_sd_test = score_distribution_probs(mu_h_test, mu_a_test, args.max_score)
    _stage("computed score-distribution probabilities")

    regime_meta = regimes.get(league_id, {"regime": "balanced_competitive", "rows": n_train})
    alpha_source = "regime"
    alpha = regime_alpha(regime_meta, args.alpha_stable, args.alpha_balanced, args.alpha_chaotic)
    alpha_val_brier = None
    alpha_val_acc = None
    if args.auto_alpha_search and args._alpha_grid:
        alpha, alpha_val_brier, alpha_val_acc = select_alpha_rolling(
            p_cls_train, p_home_sd_train, ywlt, args._alpha_grid, args.alpha_rolling_step
        )
        alpha_source = "auto_search"
    _stage(f"alpha selected source={alpha_source} value={alpha:.3f}")
    p_base_train = np.clip((alpha * p_cls_train) + ((1.0 - alpha) * p_home_sd_train), 1e-6, 1 - 1e-6)
    p_base_test = np.clip((alpha * p_cls_test) + ((1.0 - alpha) * p_home_sd_test), 1e-6, 1 - 1e-6)

    residual = fit_residual_heads(
        Xlt,
        ywlt,
        yhlt,
        yalt,
        p_base_train,
        mu_h_train,
        mu_a_train,
        ridge_alpha=args.residual_ridge_alpha,
        ridge_solver=args.residual_ridge_solver,
        adaptive_ridge_alpha=bool(args.adaptive_residual_ridge_alpha),
        hard_example_quantile=args.residual_hard_example_quantile,
        ridge_alpha_grid=args._residual_alpha_grid,
    )
    _stage(
        "fitted residual heads "
        f"(effective_alpha={float(residual.get('effective_alpha', args.residual_ridge_alpha)):.3f})"
    )
    uncertainty_mean = float(np.mean(cls_unc_train)) if len(cls_unc_train) else 0.0
    shrink_k_eff = float(max(1.0, args.residual_shrink_k) * (1.0 + (args.uncertainty_shrink_factor * uncertainty_mean)))
    shrink = float(n_train / (n_train + shrink_k_eff))
    if residual["delta_logit"] is not None:
        aug_train = np.hstack([Xlt, _logit(p_base_train).reshape(-1, 1)])
        aug_test = np.hstack([Xte, _logit(p_base_test).reshape(-1, 1)])
        dlogit_train = residual["delta_logit"].predict(residual["scaler_logit"].transform(aug_train))
        dlogit_test = residual["delta_logit"].predict(residual["scaler_logit"].transform(aug_test))
    else:
        dlogit_train = np.zeros(len(Xlt), dtype=float)
        dlogit_test = np.zeros(len(Xte), dtype=float)

    p_raw_train = _sigmoid(_logit(p_base_train) + (shrink * dlogit_train))
    p_raw_test = _sigmoid(_logit(p_base_test) + (shrink * dlogit_test))
    _stage(f"applied residual correction shrink={shrink:.3f}")

    rating_gap_idx = feature_cols.index("v3_rating_gap") if "v3_rating_gap" in feature_cols else -1
    regime_code_idx = feature_cols.index("v3_regime_code") if "v3_regime_code" in feature_cols else -1
    rating_gap_train = Xlt[:, rating_gap_idx] if rating_gap_idx >= 0 else np.zeros(len(Xlt), dtype=float)
    rating_gap_test = Xte[:, rating_gap_idx] if rating_gap_idx >= 0 else np.zeros(len(Xte), dtype=float)
    regime_code_train = Xlt[:, regime_code_idx] if regime_code_idx >= 0 else np.zeros(len(Xlt), dtype=float)
    regime_code_test = Xte[:, regime_code_idx] if regime_code_idx >= 0 else np.zeros(len(Xte), dtype=float)
    meta_used = False
    if args.meta_stacking and len(Xlt) >= 40 and len(np.unique(ywlt)) >= 2:
        meta_x_train = np.column_stack(
            [p_cls_train, p_home_sd_train, p_raw_train, rating_gap_train, regime_code_train]
        )
        meta_x_test = np.column_stack(
            [p_cls_test, p_home_sd_test, p_raw_test, rating_gap_test, regime_code_test]
        )
        p_raw_train, p_raw_test = fit_meta_stacker(meta_x_train, ywlt, meta_x_test)
        meta_used = True
    _stage(f"meta-stacking {'enabled' if meta_used else 'skipped'}")

    cut = int(round(len(Xlt) * 0.8))
    cut = max(20, min(cut, len(Xlt) - 10))
    cal = fit_calibrator(
        p_raw_train[cut:],
        ywlt[cut:],
        regime=str(regime_meta.get("regime", "balanced_competitive")),
        min_isotonic_rows=args.min_isotonic_rows,
    )
    p_final = apply_calibrator(cal, p_raw_test)
    _stage(f"calibration method={cal['method']}")

    p_draw = np.clip(p_draw_sd_test, 0.03, 0.50)
    rem = np.clip(1.0 - p_draw, 1e-6, 1.0)
    p_home = rem * p_final
    p_away = rem * (1.0 - p_final)

    if residual["delta_h"] is not None and residual["delta_a"] is not None:
        x_score_test = residual["scaler_score"].transform(Xte)
        dh = residual["delta_h"].predict(x_score_test)
        da = residual["delta_a"].predict(x_score_test)
    else:
        dh = np.zeros(len(Xte), dtype=float)
        da = np.zeros(len(Xte), dtype=float)
    pred_h = mu_h_test + (shrink * dh)
    pred_a = mu_a_test + (shrink * da)
    _stage("final prediction assembly complete")

    return {
        "ok": True,
        "regime_meta": regime_meta,
        "alpha": alpha,
        "alpha_source": alpha_source,
        "alpha_val_brier": alpha_val_brier,
        "alpha_val_acc": alpha_val_acc,
        "shrink": shrink,
        "shrink_k_effective": shrink_k_eff,
        "meta_stacking_used": bool(meta_used),
        "core_feature_count_after_prune": int(len(core_cols)),
        "effective_alpha": float(residual.get("effective_alpha", args.residual_ridge_alpha)),
        "calibration_method": cal["method"],
        "train_rows": n_train,
        "test_rows": n_test,
        "uncertainty_current_avg": float(np.mean(cur_unc)) if len(cur_unc) else 0.0,
        "uncertainty_v3_classifier_avg": float(np.mean(cls_unc)) if len(cls_unc) else 0.0,
        "winner_feature_importance_top": fi_top,
        "current_parts": (p_home_cur, p_draw_cur, p_away_cur, pred_h_cur, pred_a_cur),
        "v3_parts": (p_home, p_draw, p_away, pred_h, pred_a),
        "truth": (yout_te, yw_te, yh_te, ya_te),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MAZ Boss MAXED V3 (adaptive global+residual system).")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--league-id", type=int, default=None)
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--wf-start-train", type=int, default=80)
    parser.add_argument("--wf-step", type=int, default=20)
    parser.add_argument("--min-games", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ensemble-seeds", type=str, default="42,1337,9001,2024,31415,27182,777")
    parser.add_argument("--ensemble-depths", type=str, default="5,6,7,6,5,7,6")
    parser.add_argument("--ensemble-lr-mults", type=str, default="0.90,1.00,1.10,0.95,1.05,0.92,1.08")
    parser.add_argument("--rating-k", type=float, default=0.045)
    parser.add_argument("--rating-decay", type=float, default=0.995)
    parser.add_argument("--home-adv-k", type=float, default=0.020)
    parser.add_argument("--alpha-stable", type=float, default=0.65)
    parser.add_argument("--alpha-balanced", type=float, default=0.55)
    parser.add_argument("--alpha-chaotic", type=float, default=0.40)
    parser.add_argument("--residual-shrink-k", type=float, default=120.0)
    parser.add_argument("--residual-ridge-alpha", type=float, default=20.0)
    parser.add_argument("--residual-ridge-solver", choices=["auto", "svd", "cholesky", "lsqr", "sparse_cg", "sag", "saga", "lbfgs"], default="svd")
    parser.add_argument("--adaptive-residual-ridge-alpha", action="store_true")
    parser.add_argument("--residual-alpha-grid", type=str, default="5,10,20,50")
    parser.add_argument("--residual-hard-example-quantile", type=float, default=0.0)
    parser.add_argument("--uncertainty-shrink-factor", type=float, default=0.0)
    parser.add_argument("--global-importance-prune-pct", type=float, default=0.15)
    parser.add_argument("--feature-corr-threshold", type=float, default=0.0)
    parser.add_argument("--auto-alpha-search", action="store_true")
    parser.add_argument("--alpha-grid", type=str, default="0.3,0.5,0.7")
    parser.add_argument("--alpha-rolling-step", type=int, default=20)
    parser.add_argument("--meta-stacking", dest="meta_stacking", action="store_true", default=True)
    parser.add_argument("--no-meta-stacking", dest="meta_stacking", action="store_false")
    parser.add_argument("--max-score", type=int, default=70)
    parser.add_argument("--min-isotonic-rows", type=int, default=90)
    parser.add_argument("--min-winner-gain", type=float, default=0.003)
    parser.add_argument("--max-mae-worsen", type=float, default=0.12)
    parser.add_argument("--max-brier-worsen", type=float, default=0.01)
    parser.add_argument("--save-v3-models", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=None, help="Optional run log file path.")
    args = parser.parse_args()
    auto_log_file: Optional[str] = args.log_file
    if not auto_log_file:
        auto_log_file = f"artifacts/maz_maxed_v3_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _setup_logging(args.log_level, auto_log_file)
    LOG.info("Starting MAZ MAXED V3 run")
    LOG.info("Logging to: %s", auto_log_file)
    args._ensemble_seeds = _parse_int_list(args.ensemble_seeds)
    if not args._ensemble_seeds:
        args._ensemble_seeds = [int(args.seed)]
    args._ensemble_depths = _parse_int_list(args.ensemble_depths)
    if not args._ensemble_depths:
        args._ensemble_depths = [6 for _ in args._ensemble_seeds]
    args._ensemble_lr_mults = _parse_float_list(args.ensemble_lr_mults)
    if not args._ensemble_lr_mults:
        args._ensemble_lr_mults = [1.0 for _ in args._ensemble_seeds]
    args._alpha_grid = _parse_float_list(args.alpha_grid)
    if not args._alpha_grid:
        args._alpha_grid = [float(args.alpha_balanced)]
    args._residual_alpha_grid = _parse_float_list(args.residual_alpha_grid)
    if not args._residual_alpha_grid:
        args._residual_alpha_grid = [float(args.residual_ridge_alpha)]

    if not args.league_id and not args.all_leagues:
        raise SystemExit("Use --league-id <id> or --all-leagues")

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    if args.league_id:
        leagues = {args.league_id: LEAGUE_MAPPINGS.get(args.league_id, f"League {args.league_id}")}
    else:
        leagues = LEAGUE_MAPPINGS

    conn = sqlite3.connect(str(db_path))
    df_all = load_all_df(conn, leagues.keys())
    conn.close()
    if df_all.empty:
        raise SystemExit("No completed games found for selected leagues.")

    # Pre-filter leagues with enough rows.
    keep_ids = []
    for lid in leagues.keys():
        if int((df_all["league_id"] == lid).sum()) >= args.min_games:
            keep_ids.append(lid)
    if not keep_ids:
        raise SystemExit("No leagues meet --min-games threshold.")
    df_all = df_all[df_all["league_id"].isin(keep_ids)].copy()
    leagues = {lid: leagues[lid] for lid in keep_ids}

    df_all = add_dynamic_ratings(df_all, args.rating_k, args.rating_decay, args.home_adv_k)
    regimes = league_regimes(df_all)
    df_all = add_regime_columns(df_all, regimes)
    df_all = df_all.reset_index(drop=True)
    X_all, y_out_all, y_w_all, y_h_all, y_a_all, feature_cols = prepare_xy(df_all)
    if args.feature_corr_threshold > 0.0:
        X_all, feature_cols = prune_features_by_correlation(X_all, feature_cols, args.feature_corr_threshold)

    report: Dict[str, Any] = {
        "version": V3_VERSION,
        "generated_at": datetime.now().isoformat(),
        "db_path": str(db_path),
        "model_type": "maz_maxed_v3_adaptive",
        "config": {
            "walk_forward": bool(args.walk_forward),
            "holdout_ratio": args.holdout_ratio,
            "wf_start_train": args.wf_start_train,
            "wf_step": args.wf_step,
            "min_games": args.min_games,
            "seed": args.seed,
            "ensemble_seeds": args._ensemble_seeds,
            "ensemble_depths": args._ensemble_depths,
            "ensemble_lr_mults": args._ensemble_lr_mults,
            "rating_k": args.rating_k,
            "rating_decay": args.rating_decay,
            "home_adv_k": args.home_adv_k,
            "alpha_stable": args.alpha_stable,
            "alpha_balanced": args.alpha_balanced,
            "alpha_chaotic": args.alpha_chaotic,
            "residual_shrink_k": args.residual_shrink_k,
            "residual_ridge_alpha": args.residual_ridge_alpha,
            "residual_ridge_solver": args.residual_ridge_solver,
            "adaptive_residual_ridge_alpha": bool(args.adaptive_residual_ridge_alpha),
            "residual_alpha_grid": args._residual_alpha_grid,
            "residual_hard_example_quantile": args.residual_hard_example_quantile,
            "uncertainty_shrink_factor": args.uncertainty_shrink_factor,
            "global_importance_prune_pct": args.global_importance_prune_pct,
            "feature_corr_threshold": args.feature_corr_threshold,
            "auto_alpha_search": bool(args.auto_alpha_search),
            "alpha_grid": args._alpha_grid,
            "alpha_rolling_step": args.alpha_rolling_step,
            "meta_stacking": bool(args.meta_stacking),
            "max_score": args.max_score,
            "min_isotonic_rows": args.min_isotonic_rows,
            "min_winner_gain": args.min_winner_gain,
            "max_mae_worsen": args.max_mae_worsen,
            "max_brier_worsen": args.max_brier_worsen,
            "log_level": args.log_level,
            "log_file": auto_log_file,
        },
        "summary": {
            "tested": 0,
            "v3_wins_strict": 0,
            "v3_wins_winner_head": 0,
            "v3_wins_score_head": 0,
            "current_wins": 0,
            "skipped": 0,
        },
        "leagues": {},
    }

    for league_id, league_name in leagues.items():
        LOG.info("[%s] starting evaluation", league_name)
        last_meta: Dict[str, Any] = {}
        if args.walk_forward:
            league_pos = np.where(df_all["league_id"].values == league_id)[0]
            n = len(league_pos)
            start = max(40, int(args.wf_start_train))
            step = max(1, int(args.wf_step))
            if start >= n - 1:
                report["summary"]["skipped"] += 1
                report["leagues"][str(league_id)] = {
                    "name": league_name,
                    "status": "skipped",
                    "reason": f"not enough rows for walk-forward n={n}, start={start}",
                }
                LOG.warning("[%s] skipped: not enough rows for walk-forward n=%s, start=%s", league_name, n, start)
                continue

            total_chunks = len(range(start, n, step))
            LOG.info("[%s] walk-forward start: rows=%s, chunks=%s, step=%s", league_name, n, total_chunks, step)
            cur_parts: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
            v3_parts: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
            youts: List[np.ndarray] = []
            yws: List[np.ndarray] = []
            yhs: List[np.ndarray] = []
            yas: List[np.ndarray] = []
            tested_rows = 0

            for chunk_i, cut in enumerate(range(start, n, step), start=1):
                nxt = min(n, cut + step)
                te_idx = league_pos[cut:nxt]
                if len(te_idx) == 0:
                    continue
                split_date = df_all.iloc[int(te_idx[0])]["date_event"]
                gmask = (df_all["date_event"] < split_date).values
                ltrain_mask = np.zeros(len(df_all), dtype=bool)
                ltest_mask = np.zeros(len(df_all), dtype=bool)
                ltrain_mask[league_pos[:cut]] = True
                ltest_mask[te_idx] = True
                out = run_split(
                    X_all,
                    y_out_all,
                    y_w_all,
                    y_h_all,
                    y_a_all,
                    gmask,
                    ltrain_mask,
                    ltest_mask,
                    regimes,
                    league_id,
                    args,
                    feature_cols,
                )
                if not out.get("ok"):
                    LOG.warning(
                        "[%s] chunk %s/%s skipped: %s",
                        league_name,
                        chunk_i,
                        total_chunks,
                        out.get("reason", "unknown"),
                    )
                    continue
                last_meta = out
                cur_parts.append(out["current_parts"])
                v3_parts.append(out["v3_parts"])
                yout_te, yw_te, yh_te, ya_te = out["truth"]
                youts.append(yout_te)
                yws.append(yw_te)
                yhs.append(yh_te)
                yas.append(ya_te)
                tested_rows += len(yout_te)
                LOG.info(
                    "[%s] chunk %s/%s done | train=%s test=%s",
                    league_name,
                    chunk_i,
                    total_chunks,
                    out.get("train_rows", 0),
                    out.get("test_rows", 0),
                )

            if tested_rows < 10 or not cur_parts or not v3_parts:
                report["summary"]["skipped"] += 1
                report["leagues"][str(league_id)] = {
                    "name": league_name,
                    "status": "skipped",
                    "reason": "walk-forward produced no valid test chunks",
                }
                LOG.warning("[%s] skipped: walk-forward produced no valid test chunks", league_name)
                continue

            p_home_cur = np.concatenate([p[0] for p in cur_parts], axis=0)
            p_draw_cur = np.concatenate([p[1] for p in cur_parts], axis=0)
            p_away_cur = np.concatenate([p[2] for p in cur_parts], axis=0)
            pred_h_cur = np.concatenate([p[3] for p in cur_parts], axis=0)
            pred_a_cur = np.concatenate([p[4] for p in cur_parts], axis=0)

            p_home = np.concatenate([p[0] for p in v3_parts], axis=0)
            p_draw = np.concatenate([p[1] for p in v3_parts], axis=0)
            p_away = np.concatenate([p[2] for p in v3_parts], axis=0)
            pred_h = np.concatenate([p[3] for p in v3_parts], axis=0)
            pred_a = np.concatenate([p[4] for p in v3_parts], axis=0)

            yout_te = np.concatenate(youts, axis=0)
            yw_te = np.concatenate(yws, axis=0)
            yh_te = np.concatenate(yhs, axis=0)
            ya_te = np.concatenate(yas, axis=0)

            cur_m = evaluate(p_home_cur, p_draw_cur, p_away_cur, pred_h_cur, pred_a_cur, yout_te, yw_te, yh_te, ya_te)
            v3_m = evaluate(p_home, p_draw, p_away, pred_h, pred_a, yout_te, yw_te, yh_te, ya_te)
            n_train = int(start)
            n_test = int(tested_rows)
            regime_meta = last_meta.get("regime_meta", regimes.get(league_id, {"regime": "balanced_competitive"}))
            alpha = float(last_meta.get("alpha", regime_alpha(regime_meta, args.alpha_stable, args.alpha_balanced, args.alpha_chaotic)))
            alpha_source = str(last_meta.get("alpha_source", "regime"))
            alpha_val_brier = last_meta.get("alpha_val_brier")
            alpha_val_acc = last_meta.get("alpha_val_acc")
            shrink = float(last_meta.get("shrink", 0.0))
            cal_method = str(last_meta.get("calibration_method", "unknown"))
        else:
            gmask, ltrain_mask, ltest_mask = build_masks_for_league(df_all, league_id, args.holdout_ratio)
            out = run_split(
                X_all,
                y_out_all,
                y_w_all,
                y_h_all,
                y_a_all,
                gmask,
                ltrain_mask,
                ltest_mask,
                regimes,
                league_id,
                args,
                feature_cols,
            )
            if not out.get("ok"):
                report["summary"]["skipped"] += 1
                report["leagues"][str(league_id)] = {
                    "name": league_name,
                    "status": "skipped",
                    "reason": str(out.get("reason", "split failed")),
                }
                LOG.warning("[%s] skipped: %s", league_name, str(out.get("reason", "split failed")))
                continue
            last_meta = out
            p_home_cur, p_draw_cur, p_away_cur, pred_h_cur, pred_a_cur = out["current_parts"]
            p_home, p_draw, p_away, pred_h, pred_a = out["v3_parts"]
            yout_te, yw_te, yh_te, ya_te = out["truth"]
            cur_m = evaluate(p_home_cur, p_draw_cur, p_away_cur, pred_h_cur, pred_a_cur, yout_te, yw_te, yh_te, ya_te)
            v3_m = evaluate(p_home, p_draw, p_away, pred_h, pred_a, yout_te, yw_te, yh_te, ya_te)
            n_train = int(out["train_rows"])
            n_test = int(out["test_rows"])
            regime_meta = out["regime_meta"]
            alpha = float(out["alpha"])
            alpha_source = str(out.get("alpha_source", "regime"))
            alpha_val_brier = out.get("alpha_val_brier")
            alpha_val_acc = out.get("alpha_val_acc")
            shrink = float(out["shrink"])
            cal_method = str(out["calibration_method"])
        winner = choose_winner(
            cur_m,
            v3_m,
            min_winner_gain=args.min_winner_gain,
            max_mae_worsen=args.max_mae_worsen,
            max_brier_worsen=args.max_brier_worsen,
        )
        report["summary"]["tested"] += 1
        if winner == "V3_MAXED":
            report["summary"]["v3_wins_strict"] += 1
        elif winner == "V3_WINNER_HEAD":
            report["summary"]["v3_wins_winner_head"] += 1
        elif winner == "V3_SCORE_HEAD":
            report["summary"]["v3_wins_score_head"] += 1
        else:
            report["summary"]["current_wins"] += 1

        payload: Dict[str, Any] = {
            "name": league_name,
            "status": "tested",
            "regime": regime_meta,
            "train_rows": n_train,
            "test_rows": n_test,
            "mode": "walk_forward" if args.walk_forward else "single_holdout",
            "feature_count": len(feature_cols),
            "alpha_classifier": alpha,
            "alpha_source": alpha_source,
            "alpha_validation_brier": alpha_val_brier,
            "alpha_validation_winner_acc": alpha_val_acc,
            "residual_shrink": shrink,
            "residual_shrink_k_effective": float(last_meta.get("shrink_k_effective", args.residual_shrink_k)),
            "meta_stacking_used": bool(last_meta.get("meta_stacking_used", False)),
            "core_feature_count_after_prune": int(last_meta.get("core_feature_count_after_prune", len(feature_cols))),
            "residual_effective_alpha": float(last_meta.get("effective_alpha", args.residual_ridge_alpha)),
            "calibration_method": cal_method,
            "uncertainty_current_avg": float(last_meta.get("uncertainty_current_avg", 0.0)),
            "uncertainty_v3_classifier_avg": float(last_meta.get("uncertainty_v3_classifier_avg", 0.0)),
            "winner_feature_importance_top": last_meta.get("winner_feature_importance_top", []),
            "current": cur_m.__dict__,
            "maz_maxed_v3": v3_m.__dict__,
            "deltas": {
                "winner_accuracy_gain": v3_m.winner_accuracy - cur_m.winner_accuracy,
                "outcome_accuracy_gain": v3_m.outcome_accuracy - cur_m.outcome_accuracy,
                "overall_mae_reduction": cur_m.overall_mae - v3_m.overall_mae,
                "brier_reduction": cur_m.brier_winner - v3_m.brier_winner,
            },
            "winner": winner,
        }

        if args.save_v3_models and winner.startswith("V3_"):
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"league_{league_id}_model_maz_maxed_v3_{winner.lower()}.pkl"
            with out_file.open("wb") as f:
                pickle.dump(
                    {
                        "version": V3_VERSION,
                        "league_id": league_id,
                        "league_name": league_name,
                        "model_type": "maz_maxed_v3_adaptive",
                        "trained_at": datetime.now().isoformat(),
                        "feature_columns": feature_cols,
                        "regime": regime_meta,
                        "alpha_classifier": alpha,
                        "alpha_source": alpha_source,
                        "alpha_validation_brier": alpha_val_brier,
                        "alpha_validation_winner_acc": alpha_val_acc,
                        "residual_shrink": shrink,
                        "residual_shrink_k_effective": float(last_meta.get("shrink_k_effective", args.residual_shrink_k)),
                        "meta_stacking_used": bool(last_meta.get("meta_stacking_used", False)),
                        "core_feature_count_after_prune": int(last_meta.get("core_feature_count_after_prune", len(feature_cols))),
                        "residual_effective_alpha": float(last_meta.get("effective_alpha", args.residual_ridge_alpha)),
                        "calibration_method": cal_method,
                        "uncertainty_current_avg": float(last_meta.get("uncertainty_current_avg", 0.0)),
                        "uncertainty_v3_classifier_avg": float(last_meta.get("uncertainty_v3_classifier_avg", 0.0)),
                        "winner_feature_importance_top": last_meta.get("winner_feature_importance_top", []),
                        "metrics_unseen": v3_m.__dict__,
                        "baseline_unseen": cur_m.__dict__,
                        "winner_mode": winner,
                    },
                    f,
                )
            payload["saved_model"] = str(out_file)

        report["leagues"][str(league_id)] = payload
        LOG.info(
            "[%s] curr_win_acc=%.3f v3_win_acc=%.3f | curr_out_acc=%.3f v3_out_acc=%.3f | "
            "curr_mae=%.3f v3_mae=%.3f | curr_brier=%.4f v3_brier=%.4f | winner=%s",
            league_name,
            cur_m.winner_accuracy,
            v3_m.winner_accuracy,
            cur_m.outcome_accuracy,
            v3_m.outcome_accuracy,
            cur_m.overall_mae,
            v3_m.overall_mae,
            cur_m.brier_winner,
            v3_m.brier_winner,
            winner,
        )

    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"maz_maxed_v3_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("=== MAZ MAXED V3 Summary ===")
    LOG.info("%s", json.dumps(report["summary"], indent=2))
    LOG.info("Report saved: %s", out_file)


if __name__ == "__main__":
    main()
