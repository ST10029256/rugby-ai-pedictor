#!/usr/bin/env python3
"""
MAZ Boss MAXED V2

Major upgrades vs V1:
- Full walk-forward mode (expanding window, unseen-by-time evaluation).
- 3-way outcome modeling (away/draw/home) + score regression.
- Optional odds-aware profit simulation when odds fields exist.
- Quantum-inspired candidate subset and blend weight optimization.

Notes:
- This is "maxed" for project constraints and data reality.
- True quantum hardware and giant transformers are not practical here
  without dedicated infra and materially different data.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
import logging
import math
import pickle
import random
import sqlite3
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
except Exception:
    print("XGBoost is required. Install with: pip install xgboost")
    raise

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table

LOG = logging.getLogger("maz_v2")


@dataclass
class Metrics:
    outcome_accuracy: float
    winner_accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    rows: int


@dataclass
class ProfitMetrics:
    has_odds: bool
    bets: int
    abstained: int
    hit_rate: float
    profit_units: float
    roi: float
    avg_edge: float
    residual_volatility: float


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


def _tail(values: List[float], window: int) -> List[float]:
    return values[-window:] if len(values) > window else values


def _mean_tail(values: List[float], window: int) -> float:
    if not values:
        return 0.0
    vv = _tail(values, window)
    return float(np.mean(vv))


def _std_tail(values: List[float], window: int) -> float:
    if len(values) < 2:
        return 0.0
    vv = _tail(values, window)
    if len(vv) < 2:
        return 0.0
    return float(np.std(vv))


def _winrate_tail(results: List[int], window: int) -> float:
    if not results:
        return 0.0
    vv = _tail([1 if r > 0 else 0 for r in results], window)
    return float(np.mean(vv)) if vv else 0.0


def _ewma(values: List[float], alpha: float, max_len: int = 50) -> float:
    if not values:
        return 0.0
    vv = _tail(values, max_len)
    x = float(vv[0])
    for z in vv[1:]:
        x = (alpha * float(z)) + ((1.0 - alpha) * x)
    return float(x)


def _team_stat_block(hist: List[Tuple[float, float, float, int]], prefix: str) -> Dict[str, float]:
    scored = [h[0] for h in hist]
    conceded = [h[1] for h in hist]
    margin = [h[2] for h in hist]
    result = [h[3] for h in hist]
    out = {
        f"{prefix}_games": float(len(hist)),
        f"{prefix}_avg_for_3": _mean_tail(scored, 3),
        f"{prefix}_avg_for_5": _mean_tail(scored, 5),
        f"{prefix}_avg_for_10": _mean_tail(scored, 10),
        f"{prefix}_avg_for_20": _mean_tail(scored, 20),
        f"{prefix}_avg_for_50": _mean_tail(scored, 50),
        f"{prefix}_avg_against_3": _mean_tail(conceded, 3),
        f"{prefix}_avg_against_5": _mean_tail(conceded, 5),
        f"{prefix}_avg_against_10": _mean_tail(conceded, 10),
        f"{prefix}_avg_against_20": _mean_tail(conceded, 20),
        f"{prefix}_avg_against_50": _mean_tail(conceded, 50),
        f"{prefix}_std_for_3": _std_tail(scored, 3),
        f"{prefix}_std_for_10": _std_tail(scored, 10),
        f"{prefix}_std_for_20": _std_tail(scored, 20),
        f"{prefix}_std_against_3": _std_tail(conceded, 3),
        f"{prefix}_std_against_10": _std_tail(conceded, 10),
        f"{prefix}_std_against_20": _std_tail(conceded, 20),
        f"{prefix}_winrate_5": _winrate_tail(result, 5),
        f"{prefix}_winrate_10": _winrate_tail(result, 10),
        f"{prefix}_winrate_20": _winrate_tail(result, 20),
        f"{prefix}_margin_5": _mean_tail(margin, 5),
        f"{prefix}_margin_10": _mean_tail(margin, 10),
        f"{prefix}_margin_20": _mean_tail(margin, 20),
        f"{prefix}_ewma_for_fast": _ewma(scored, 0.60),
        f"{prefix}_ewma_for_slow": _ewma(scored, 0.25),
        f"{prefix}_ewma_against_fast": _ewma(conceded, 0.60),
        f"{prefix}_ewma_against_slow": _ewma(conceded, 0.25),
    }
    out[f"{prefix}_momentum_for"] = out[f"{prefix}_avg_for_3"] - out[f"{prefix}_avg_for_10"]
    out[f"{prefix}_momentum_against"] = out[f"{prefix}_avg_against_3"] - out[f"{prefix}_avg_against_10"]
    return out


def _pagerank_from_edges(
    team_ids: Sequence[int],
    edges: Sequence[Tuple[int, int, float, int]],
    damping: float,
    iters: int,
    current_step: int,
    half_life_matches: float,
) -> Dict[int, float]:
    if not team_ids:
        return {}
    ids = [int(t) for t in team_ids]
    n = len(ids)
    base = (1.0 - damping) / float(max(1, n))
    out_sum: Dict[int, float] = defaultdict(float)
    for src, _, w, step_idx in edges:
        age = max(0, current_step - int(step_idx))
        decay = 0.5 ** (float(age) / max(1.0, float(half_life_matches)))
        out_sum[int(src)] += float(max(1e-6, w * decay))

    rank = {tid: 1.0 / float(n) for tid in ids}
    for _ in range(max(2, iters)):
        nxt = {tid: base for tid in ids}
        for src, dst, w, step_idx in edges:
            s = int(src)
            d = int(dst)
            age = max(0, current_step - int(step_idx))
            decay = 0.5 ** (float(age) / max(1.0, float(half_life_matches)))
            w_eff = float(w) * decay
            den = out_sum.get(s, 0.0)
            if den <= 0:
                continue
            nxt[d] += damping * rank.get(s, 0.0) * (w_eff / den)
        rank = nxt
    return rank


def augment_ultimate_features(
    df: pd.DataFrame,
    graph_window: int = 260,
    graph_iters: int = 14,
    graph_damping: float = 0.85,
    graph_half_life: float = 120.0,
) -> pd.DataFrame:
    """
    Time-safe feature augmentation:
    - Multi-lag dynamics for each team (overall + venue specific).
    - Head-to-head and momentum/rivalry effects.
    - Rolling graph power (PageRank-like strength transfer).
    """
    if df.empty:
        return df
    dff = df.copy()

    team_hist: Dict[int, List[Tuple[float, float, float, int]]] = defaultdict(list)
    team_home_hist: Dict[int, List[Tuple[float, float, float, int]]] = defaultdict(list)
    team_away_hist: Dict[int, List[Tuple[float, float, float, int]]] = defaultdict(list)
    h2h_hist: Dict[Tuple[int, int], List[float]] = defaultdict(list)  # margin from team=min(id) perspective
    graph_edges: Deque[Tuple[int, int, float, int]] = deque(maxlen=max(80, int(graph_window)))
    seen_teams: set[int] = set()

    rows: List[Dict[str, float]] = []
    for step_idx, row in enumerate(dff.itertuples(index=False)):
        home = int(row.home_team_id)
        away = int(row.away_team_id)
        hs = float(row.home_score)
        aws = float(row.away_score)
        seen_teams.add(home)
        seen_teams.add(away)

        h_all = _team_stat_block(team_hist[home], "h_all")
        a_all = _team_stat_block(team_hist[away], "a_all")
        h_home = _team_stat_block(team_home_hist[home], "h_home")
        a_away = _team_stat_block(team_away_hist[away], "a_away")

        key = (home, away) if home < away else (away, home)
        raw = h2h_hist[key]
        h2h_margin = raw if key[0] == home else [-m for m in raw]
        h2h = {
            "h2h_games": float(len(h2h_margin)),
            "h2h_margin_3": _mean_tail(h2h_margin, 3),
            "h2h_margin_5": _mean_tail(h2h_margin, 5),
            "h2h_margin_10": _mean_tail(h2h_margin, 10),
            "h2h_winrate_5": _winrate_tail([1 if m > 0 else 0 for m in h2h_margin], 5),
            "h2h_winrate_10": _winrate_tail([1 if m > 0 else 0 for m in h2h_margin], 10),
        }

        graph_rank = _pagerank_from_edges(
            list(seen_teams),
            list(graph_edges),
            graph_damping,
            graph_iters,
            current_step=step_idx,
            half_life_matches=graph_half_life,
        )
        h_pow = float(graph_rank.get(home, 0.0))
        a_pow = float(graph_rank.get(away, 0.0))

        rec: Dict[str, float] = {}
        rec.update(h_all)
        rec.update(a_all)
        rec.update(h_home)
        rec.update(a_away)
        rec.update(h2h)
        rec["graph_power_home"] = h_pow
        rec["graph_power_away"] = a_pow
        rec["graph_power_diff"] = h_pow - a_pow
        rec["diff_form_for_5"] = h_all["h_all_avg_for_5"] - a_all["a_all_avg_for_5"]
        rec["diff_form_against_5"] = h_all["h_all_avg_against_5"] - a_all["a_all_avg_against_5"]
        rec["diff_margin_10"] = h_all["h_all_margin_10"] - a_all["a_all_margin_10"]
        rec["diff_winrate_10"] = h_all["h_all_winrate_10"] - a_all["a_all_winrate_10"]
        rec["diff_momentum_for"] = h_all["h_all_momentum_for"] - a_all["a_all_momentum_for"]
        rec["diff_momentum_against"] = h_all["h_all_momentum_against"] - a_all["a_all_momentum_against"]
        rec["diff_ewma_for_fast"] = h_all["h_all_ewma_for_fast"] - a_all["a_all_ewma_for_fast"]
        rec["diff_ewma_against_fast"] = h_all["h_all_ewma_against_fast"] - a_all["a_all_ewma_against_fast"]
        rows.append(rec)

        margin = hs - aws
        h_res = 1 if margin > 0 else (0 if margin == 0 else -1)
        a_res = -h_res
        team_hist[home].append((hs, aws, margin, h_res))
        team_hist[away].append((aws, hs, -margin, a_res))
        team_home_hist[home].append((hs, aws, margin, h_res))
        team_away_hist[away].append((aws, hs, -margin, a_res))
        if key[0] == home:
            h2h_hist[key].append(margin)
        else:
            h2h_hist[key].append(-margin)

        # loser -> winner directed strength transfer
        w = 1.0 + (abs(margin) / 14.0)
        if margin > 0:
            graph_edges.append((away, home, w, step_idx))
        elif margin < 0:
            graph_edges.append((home, away, w, step_idx))
        else:
            graph_edges.append((home, away, 0.5, step_idx))
            graph_edges.append((away, home, 0.5, step_idx))

    feats = pd.DataFrame(rows, index=dff.index)
    return pd.concat([dff, feats], axis=1)


def outcome_from_scores(home: np.ndarray, away: np.ndarray) -> np.ndarray:
    # 0=away win, 1=draw, 2=home win
    out = np.where(home > away, 2, np.where(home == away, 1, 0))
    return out.astype(int)


def detect_odds_columns(df: pd.DataFrame) -> Optional[Tuple[str, str, str]]:
    candidate_triples = [
        ("odds_home", "odds_draw", "odds_away"),
        ("home_odds", "draw_odds", "away_odds"),
        ("odd_home", "odd_draw", "odd_away"),
        ("bookmaker_home_odds", "bookmaker_draw_odds", "bookmaker_away_odds"),
    ]
    cols = set(df.columns)
    for h, d, a in candidate_triples:
        if h in cols and d in cols and a in cols:
            return (h, d, a)
    return None


def prepare_xy(
    df: pd.DataFrame, odds_cols: Optional[Tuple[str, str, str]]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str], Optional[np.ndarray]]:
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
    if odds_cols:
        exclude.update(odds_cols)

    feature_cols = [c for c in df.columns if c not in exclude and not df[c].isna().all()]
    X = df[feature_cols].fillna(0).values
    y_outcome = outcome_from_scores(df["home_score"].values, df["away_score"].values)
    y_winner = (df["home_score"] > df["away_score"]).astype(int).values
    y_h = df["home_score"].values
    y_a = df["away_score"].values

    odds: Optional[np.ndarray] = None
    if odds_cols:
        odds = df[list(odds_cols)].values.astype(float)
    return X, y_outcome, y_winner, y_h, y_a, feature_cols, odds


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
        eval_metric="mlogloss",
        objective="multi:softprob",
        num_class=3,
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
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_h = RandomForestRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_a = RandomForestRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        return clf, reg_h, reg_a
    if fam == "et":
        clf = ExtraTreesClassifier(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_h = ExtraTreesRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        reg_a = ExtraTreesRegressor(
            n_estimators=p["n_estimators"],
            max_depth=p["max_depth"],
            min_samples_split=p["min_samples_split"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
            n_jobs=-1,
        )
        return clf, reg_h, reg_a
    if fam == "hgb":
        clf = HistGradientBoostingClassifier(
            learning_rate=p["learning_rate"],
            max_depth=p["max_depth"],
            max_iter=p["max_iter"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
        )
        reg_h = HistGradientBoostingRegressor(
            learning_rate=p["learning_rate"],
            max_depth=p["max_depth"],
            max_iter=p["max_iter"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
        )
        reg_a = HistGradientBoostingRegressor(
            learning_rate=p["learning_rate"],
            max_depth=p["max_depth"],
            max_iter=p["max_iter"],
            min_samples_leaf=p["min_samples_leaf"],
            random_state=seed,
        )
        return clf, reg_h, reg_a
    raise ValueError(f"Unknown family: {fam}")


def fit_outcome_classifier(clf: Any, X: np.ndarray, y_out: np.ndarray) -> Dict[str, Any]:
    """
    Fit outcome classifier with contiguous local labels, while preserving
    global 3-way class semantics (0=away,1=draw,2=home).
    This prevents failures when a training window contains only two classes,
    e.g. {0,2} and no draws.
    """
    classes = np.array(sorted(set(int(v) for v in y_out.tolist())), dtype=int)
    local_map = {int(c): i for i, c in enumerate(classes.tolist())}
    y_local = np.array([local_map[int(v)] for v in y_out.tolist()], dtype=int)
    clf.fit(X, y_local)
    return {"clf": clf, "classes": classes}


def predict_outcome_proba(clf_pack: Dict[str, Any], X: np.ndarray) -> np.ndarray:
    clf = clf_pack["clf"]
    classes = clf_pack["classes"]
    raw = clf.predict_proba(X)
    p3 = np.zeros((len(X), 3), dtype=float)
    for j, c in enumerate(classes.tolist()):
        p3[:, int(c)] = raw[:, j]
    s = np.sum(p3, axis=1, keepdims=True)
    s = np.where(s <= 0, 1.0, s)
    return p3 / s


def sample_candidates(seed: int, per_family: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    candidates: List[Dict[str, Any]] = []
    for _ in range(per_family):
        candidates.append(
            {
                "family": "xgb",
                "params": {
                    "n_estimators": rng.choice([180, 240, 320, 420]),
                    "max_depth": rng.choice([4, 5, 6, 7, 8]),
                    "learning_rate": rng.choice([0.03, 0.05, 0.07, 0.1]),
                    "subsample": rng.choice([0.7, 0.8, 0.9]),
                    "colsample_bytree": rng.choice([0.7, 0.8, 0.9]),
                    "min_child_weight": rng.choice([1.0, 2.0, 4.0]),
                    "reg_lambda": rng.choice([0.5, 1.0, 2.0, 4.0]),
                    "random_state": rng.randint(1, 20000),
                },
            }
        )
        candidates.append(
            {
                "family": "rf",
                "params": {
                    "n_estimators": rng.choice([220, 320, 420]),
                    "max_depth": rng.choice([6, 8, 10, None]),
                    "min_samples_split": rng.choice([2, 4, 6]),
                    "min_samples_leaf": rng.choice([1, 2, 3]),
                    "random_state": rng.randint(1, 20000),
                },
            }
        )
        candidates.append(
            {
                "family": "et",
                "params": {
                    "n_estimators": rng.choice([220, 320, 420]),
                    "max_depth": rng.choice([6, 8, 10, None]),
                    "min_samples_split": rng.choice([2, 4, 6]),
                    "min_samples_leaf": rng.choice([1, 2, 3]),
                    "random_state": rng.randint(1, 20000),
                },
            }
        )
        candidates.append(
            {
                "family": "hgb",
                "params": {
                    "learning_rate": rng.choice([0.03, 0.05, 0.08, 0.12]),
                    "max_depth": rng.choice([3, 4, 5, 6]),
                    "max_iter": rng.choice([180, 260, 340, 460]),
                    "min_samples_leaf": rng.choice([15, 25, 35]),
                    "random_state": rng.randint(1, 20000),
                },
            }
        )
    return candidates


def _family_of(row: Dict[str, Any]) -> str:
    return str(row.get("spec", {}).get("family", "unknown"))


def quantum_qubo_select_candidates(
    leaderboard: List[Dict[str, Any]],
    target_k: int,
    steps: int = 1200,
    seed: int = 42,
    diversity_penalty: float = 0.02,
) -> List[Dict[str, Any]]:
    if not leaderboard:
        return []
    n = len(leaderboard)
    target_k = max(1, min(target_k, n))
    rng = np.random.default_rng(seed)
    state = np.zeros(n, dtype=int)
    state[:target_k] = 1
    rng.shuffle(state)
    best = state.copy()

    def energy(mask: np.ndarray) -> float:
        selected = np.where(mask == 1)[0]
        if len(selected) == 0:
            return 1e9
        score = float(sum(leaderboard[i]["cv_score"] for i in selected))
        fams = [_family_of(leaderboard[i]) for i in selected]
        coll = len(fams) - len(set(fams))
        card_pen = abs(len(selected) - target_k) * 0.05
        return -(score - diversity_penalty * coll) + card_pen

    e_curr = energy(state)
    e_best = e_curr
    temp = 1.0
    for _ in range(max(200, steps)):
        i = int(rng.integers(0, n))
        j = int(rng.integers(0, n))
        if i == j:
            continue
        nxt = state.copy()
        nxt[i] = 1 - nxt[i]
        nxt[j] = 1 - nxt[j]
        e_nxt = energy(nxt)
        de = e_nxt - e_curr
        if de <= 0 or rng.random() < math.exp(-de / max(temp, 1e-9)):
            state = nxt
            e_curr = e_nxt
            if e_curr < e_best:
                best = state.copy()
                e_best = e_curr
        temp *= 0.996

    idx = np.where(best == 1)[0].tolist()
    if not idx:
        idx = list(range(min(target_k, n)))
    picked = [leaderboard[i] for i in idx]
    if len(picked) > target_k:
        picked = sorted(picked, key=lambda r: r["cv_score"], reverse=True)[:target_k]
    return picked


def quantum_optimize_blend_weights(
    prob_matrix: np.ndarray,
    y_true_homewin: np.ndarray,
    steps: int = 1200,
    seed: int = 42,
    temperature: float = 0.8,
    cool_rate: float = 0.996,
) -> np.ndarray:
    n_models = prob_matrix.shape[0]
    rng = np.random.default_rng(seed)
    w = np.ones(n_models, dtype=float) / n_models

    def loss(weights: np.ndarray) -> float:
        p = np.clip(np.sum(weights[:, None] * prob_matrix, axis=0), 1e-6, 1 - 1e-6)
        mse = float(np.mean((p - y_true_homewin) ** 2))
        ce = float(-np.mean(y_true_homewin * np.log(p) + (1 - y_true_homewin) * np.log(1 - p)))
        return 0.6 * ce + 0.4 * mse

    best_w = w.copy()
    best_l = loss(w)
    curr_w = w.copy()
    curr_l = best_l
    temp = float(max(1e-4, temperature))

    for _ in range(max(200, steps)):
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


def annealed_feature_subset(
    X: np.ndarray,
    y_binary: np.ndarray,
    max_features: int,
    steps: int,
    seed: int,
    redundancy_penalty: float,
) -> np.ndarray:
    n_samples, n_features = X.shape
    if max_features <= 0 or n_features <= max_features:
        return np.arange(n_features, dtype=int)

    yv = y_binary.astype(float)
    y_std = float(np.std(yv))
    if y_std <= 1e-9:
        return np.arange(min(max_features, n_features), dtype=int)
    yv = (yv - float(np.mean(yv))) / y_std

    Xc = X - np.mean(X, axis=0, keepdims=True)
    Xstd = np.std(Xc, axis=0) + 1e-9
    corr = np.abs(np.mean(Xc * yv[:, None], axis=0) / Xstd)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)

    pool_size = int(min(n_features, max(60, max_features * 4)))
    pool_idx = np.argsort(-corr)[:pool_size]
    Xp = X[:, pool_idx]
    Xpn = (Xp - np.mean(Xp, axis=0, keepdims=True)) / (np.std(Xp, axis=0, keepdims=True) + 1e-9)
    red = np.abs((Xpn.T @ Xpn) / float(max(1, n_samples - 1)))
    red = np.nan_to_num(red, nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(red, 0.0)
    score = corr[pool_idx]

    rng = np.random.default_rng(seed)
    k = int(min(max_features, pool_size))
    state = np.zeros(pool_size, dtype=int)
    state[:k] = 1
    rng.shuffle(state)
    best = state.copy()

    def energy(mask: np.ndarray) -> float:
        sel = np.where(mask == 1)[0]
        if len(sel) == 0:
            return 1e9
        gain = float(np.sum(score[sel]))
        if len(sel) > 1:
            rr = red[np.ix_(sel, sel)]
            redundancy = float(np.sum(rr) / (len(sel) * (len(sel) - 1)))
        else:
            redundancy = 0.0
        card_pen = abs(len(sel) - k) * 0.20
        return -(gain - (redundancy_penalty * redundancy)) + card_pen

    e_curr = energy(state)
    e_best = e_curr
    temp = 1.0
    for _ in range(max(200, steps)):
        i = int(rng.integers(0, pool_size))
        j = int(rng.integers(0, pool_size))
        if i == j:
            continue
        nxt = state.copy()
        nxt[i] = 1 - nxt[i]
        nxt[j] = 1 - nxt[j]
        e_nxt = energy(nxt)
        de = e_nxt - e_curr
        if de <= 0 or rng.random() < math.exp(-de / max(temp, 1e-9)):
            state = nxt
            e_curr = e_nxt
            if e_curr < e_best:
                best = state.copy()
                e_best = e_curr
        temp *= 0.996

    sel_pool = np.where(best == 1)[0].tolist()
    if not sel_pool:
        sel_pool = list(range(k))
    if len(sel_pool) > k:
        sel_pool = sorted(sel_pool, key=lambda i: score[i], reverse=True)[:k]
    return np.sort(pool_idx[sel_pool]).astype(int)


def evaluate_candidate_on_timeseries(
    spec: Dict[str, Any],
    X: np.ndarray,
    y_out: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    n_splits: int,
    cv_weight_outcome: float,
    cv_weight_winner: float,
    cv_weight_mae: float,
) -> Dict[str, Any]:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    out_accs: List[float] = []
    winner_accs: List[float] = []
    maes: List[float] = []

    for tr_idx, va_idx in tscv.split(X):
        X_tr, X_va = X[tr_idx], X[va_idx]
        y_out_tr, y_out_va = y_out[tr_idx], y_out[va_idx]
        y_w_va = y_w[va_idx]
        y_h_tr, y_h_va = y_h[tr_idx], y_h[va_idx]
        y_a_tr, y_a_va = y_a[tr_idx], y_a[va_idx]

        if len(np.unique(y_out_tr)) < 2:
            continue

        clf, reg_h, reg_a = instantiate_triplet(spec)
        clf_pack = fit_outcome_classifier(clf, X_tr, y_out_tr)
        reg_h.fit(X_tr, y_h_tr)
        reg_a.fit(X_tr, y_a_tr)

        p3 = predict_outcome_proba(clf_pack, X_va)
        y_out_pred = np.argmax(p3, axis=1)
        y_w_pred = (p3[:, 2] >= p3[:, 0]).astype(int)
        y_h_pred = reg_h.predict(X_va)
        y_a_pred = reg_a.predict(X_va)

        out_accs.append(float(accuracy_score(y_out_va, y_out_pred)))
        winner_accs.append(float(accuracy_score(y_w_va, y_w_pred)))
        mae_h = float(mean_absolute_error(y_h_va, y_h_pred))
        mae_a = float(mean_absolute_error(y_a_va, y_a_pred))
        maes.append((mae_h + mae_a) / 2.0)

    if not out_accs:
        return {"spec": spec, "cv_outcome_acc": 0.0, "cv_winner_acc": 0.0, "cv_mae": 999.0, "cv_score": -999.0}

    cv_out = float(np.mean(out_accs))
    cv_win = float(np.mean(winner_accs))
    cv_mae = float(np.mean(maes))
    cv_score = (cv_weight_outcome * cv_out) + (cv_weight_winner * cv_win) - (cv_weight_mae * cv_mae)
    return {
        "spec": spec,
        "cv_outcome_acc": cv_out,
        "cv_winner_acc": cv_win,
        "cv_mae": cv_mae,
        "cv_score": cv_score,
    }


def fit_models_from_specs(
    specs: List[Dict[str, Any]],
    X: np.ndarray,
    y_out: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
) -> List[Dict[str, Any]]:
    fitted: List[Dict[str, Any]] = []
    for s in specs:
        clf, reg_h, reg_a = instantiate_triplet(s)
        clf_pack = fit_outcome_classifier(clf, X, y_out)
        reg_h.fit(X, y_h)
        reg_a.fit(X, y_a)
        fitted.append({"spec": s, "clf_pack": clf_pack, "reg_h": reg_h, "reg_a": reg_a})
    return fitted


def blend_weights_from_leaderboard(
    top_rows: List[Dict[str, Any]],
    outcome_metric: str = "winner",
) -> Tuple[List[float], List[float]]:
    if outcome_metric == "outcome":
        out_signal = np.array([max(r["cv_outcome_acc"], 1e-6) for r in top_rows], dtype=float)
    elif outcome_metric == "hybrid":
        out_signal = np.array(
            [max(0.40 * r["cv_outcome_acc"] + 0.60 * r["cv_winner_acc"], 1e-6) for r in top_rows],
            dtype=float,
        )
    else:
        out_signal = np.array([max(r["cv_winner_acc"], 1e-6) for r in top_rows], dtype=float)
    inv_mae = np.array([1.0 / max(r["cv_mae"], 1e-6) for r in top_rows], dtype=float)
    w_outcome = (out_signal / out_signal.sum()).tolist()
    w_score = (inv_mae / inv_mae.sum()).tolist()
    return w_outcome, w_score


def aggregate_predictions(
    fitted: List[Dict[str, Any]],
    w_outcome: Sequence[float],
    w_score: Sequence[float],
    X_part: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    p3_parts = []
    h_parts = []
    a_parts = []
    for row in fitted:
        p3_parts.append(predict_outcome_proba(row["clf_pack"], X_part))
        h_parts.append(row["reg_h"].predict(X_part))
        a_parts.append(row["reg_a"].predict(X_part))

    p3 = np.zeros_like(p3_parts[0], dtype=float)
    for i in range(len(fitted)):
        p3 += float(w_outcome[i]) * p3_parts[i]
    h = np.zeros(len(X_part), dtype=float)
    a = np.zeros(len(X_part), dtype=float)
    for i in range(len(fitted)):
        h += float(w_score[i]) * h_parts[i]
        a += float(w_score[i]) * a_parts[i]
    return p3, h, a


def _poisson_pmf_trunc(mean_score: float, max_score: int) -> np.ndarray:
    lam = max(1e-6, float(mean_score))
    vals = np.zeros(max_score + 1, dtype=float)
    for k in range(max_score + 1):
        logp = (k * math.log(lam)) - lam - math.lgamma(k + 1.0)
        vals[k] = math.exp(logp)
    s = float(np.sum(vals))
    if s <= 0:
        vals[:] = 1.0 / float(max_score + 1)
    else:
        vals /= s
    return vals


def _rugby_sticky_mask(max_score: int) -> np.ndarray:
    reachable = np.zeros(max_score + 1, dtype=float)
    for k in range(max_score + 1):
        # Any combination of 3/5/7 (including 0) marks "rugby-plausible" totals.
        ok = False
        for a in range((k // 7) + 1):
            rem1 = k - (7 * a)
            for b in range((rem1 // 5) + 1):
                rem2 = rem1 - (5 * b)
                if rem2 % 3 == 0:
                    ok = True
                    break
            if ok:
                break
        reachable[k] = 1.0 if ok else 0.0
    return reachable


def build_rugby_score_density(
    pred_h: np.ndarray,
    pred_a: np.ndarray,
    max_score: int,
    sticky_boost: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build discrete per-match score PMFs for home/away and derive an uncertainty
    proxy from PMF entropy.
    """
    n = len(pred_h)
    max_score = int(max(10, max_score))
    sticky = _rugby_sticky_mask(max_score)
    sticky = 1.0 + (sticky_boost * sticky)

    pmf_h = np.zeros((n, max_score + 1), dtype=float)
    pmf_a = np.zeros((n, max_score + 1), dtype=float)
    entropy = np.zeros(n, dtype=float)
    denom = math.log(max_score + 1.0)
    denom = max(1e-6, denom)

    for i in range(n):
        ph = _poisson_pmf_trunc(float(max(0.0, pred_h[i])), max_score)
        pa = _poisson_pmf_trunc(float(max(0.0, pred_a[i])), max_score)
        ph = ph * sticky
        pa = pa * sticky
        ph /= max(1e-12, float(np.sum(ph)))
        pa /= max(1e-12, float(np.sum(pa)))
        pmf_h[i] = ph
        pmf_a[i] = pa

        h_ent = float(-np.sum(ph * np.log(np.clip(ph, 1e-12, 1.0))))
        a_ent = float(-np.sum(pa * np.log(np.clip(pa, 1e-12, 1.0))))
        entropy[i] = ((h_ent + a_ent) / 2.0) / denom
    return pmf_h, pmf_a, entropy


def residual_volatility(pred_h: np.ndarray, pred_a: np.ndarray, y_h: np.ndarray, y_a: np.ndarray) -> float:
    err_h = np.abs(pred_h - y_h)
    err_a = np.abs(pred_a - y_a)
    errs = np.concatenate([err_h, err_a], axis=0)
    return float(np.var(errs))


def evaluate_from_predictions(
    p3: np.ndarray,
    pred_h: np.ndarray,
    pred_a: np.ndarray,
    y_out: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
) -> Metrics:
    y_out_pred = np.argmax(p3, axis=1)
    y_w_pred = (p3[:, 2] >= p3[:, 0]).astype(int)
    mae_h = float(mean_absolute_error(y_h, pred_h))
    mae_a = float(mean_absolute_error(y_a, pred_a))
    return Metrics(
        outcome_accuracy=float(accuracy_score(y_out, y_out_pred)),
        winner_accuracy=float(accuracy_score(y_w, y_w_pred)),
        home_mae=mae_h,
        away_mae=mae_a,
        overall_mae=(mae_h + mae_a) / 2.0,
        rows=len(y_out),
    )


def choose_winner_mode(
    current_m: Metrics,
    maz_m: Metrics,
    legacy_m: Optional[Metrics],
    min_winner_gain: float,
    min_outcome_gain: float,
    min_mae_reduction: float,
    max_mae_worsen_winner_head: float,
    max_winner_drop_score_head: float,
    max_winner_drop_vs_legacy: float,
    max_outcome_drop_vs_legacy: float,
    winner_first_mode: bool,
) -> str:
    # Guardrail: v2 must not materially regress vs best historical winner/outcome baseline.
    winner_floor = current_m.winner_accuracy
    outcome_floor = current_m.outcome_accuracy
    if legacy_m is not None:
        winner_floor = max(winner_floor, legacy_m.winner_accuracy)
        outcome_floor = max(outcome_floor, legacy_m.outcome_accuracy)
    if maz_m.winner_accuracy < (winner_floor - max_winner_drop_vs_legacy):
        return "CURRENT"
    if (not winner_first_mode) and maz_m.outcome_accuracy < (outcome_floor - max_outcome_drop_vs_legacy):
        return "CURRENT"

    winner_gain = maz_m.winner_accuracy - current_m.winner_accuracy
    outcome_gain = maz_m.outcome_accuracy - current_m.outcome_accuracy
    mae_reduction = current_m.overall_mae - maz_m.overall_mae

    if winner_gain >= min_winner_gain and (winner_first_mode or outcome_gain >= min_outcome_gain) and mae_reduction >= 0.0:
        return "MAZ_MAXED"
    if winner_gain >= min_winner_gain and (-mae_reduction) <= max_mae_worsen_winner_head:
        return "MAZ_WINNER_HEAD"
    if mae_reduction >= min_mae_reduction and (-winner_gain) <= max_winner_drop_score_head:
        return "MAZ_SCORE_HEAD"
    if (
        current_m.winner_accuracy > maz_m.winner_accuracy
        and current_m.outcome_accuracy >= maz_m.outcome_accuracy
        and current_m.overall_mae <= maz_m.overall_mae
    ):
        return "CURRENT"
    return "TIE_OR_TRADEOFF"


def _metrics_from_artifact_dict(obj: Dict[str, Any]) -> Optional[Metrics]:
    m = obj.get("metrics_unseen")
    if not isinstance(m, dict):
        return None
    winner = m.get("winner_accuracy", m.get("accuracy"))
    outcome = m.get("outcome_accuracy", m.get("accuracy"))
    home_mae = m.get("home_mae")
    away_mae = m.get("away_mae")
    overall_mae = m.get("overall_mae")
    rows = m.get("rows", 0)
    if winner is None or outcome is None or overall_mae is None:
        return None
    if home_mae is None:
        home_mae = overall_mae
    if away_mae is None:
        away_mae = overall_mae
    return Metrics(
        outcome_accuracy=float(outcome),
        winner_accuracy=float(winner),
        home_mae=float(home_mae),
        away_mae=float(away_mae),
        overall_mae=float(overall_mae),
        rows=int(rows),
    )


def load_legacy_maz_metrics(league_id: int) -> Optional[Metrics]:
    artifacts_dir = Path("artifacts")
    if not artifacts_dir.exists():
        return None
    pattern = f"league_{league_id}_model_maz_maxed*.pkl"
    files = [p for p in artifacts_dir.glob(pattern) if "_v2_" not in p.name]
    if not files:
        return None
    exact = [p for p in files if p.name.endswith("_model_maz_maxed.pkl")]
    candidates = exact if exact else sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in candidates:
        try:
            with fp.open("rb") as f:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=r".*If you are loading a serialized model.*",
                        category=UserWarning,
                    )
                    obj = pickle.load(f)
            if isinstance(obj, dict):
                m = _metrics_from_artifact_dict(obj)
                if m is not None:
                    return m
        except Exception:
            continue
    return None


def evaluate_profit(
    p3: np.ndarray,
    y_out: np.ndarray,
    odds: Optional[np.ndarray],
    min_edge: float,
    uncertainty: Optional[np.ndarray],
    max_uncertainty: float,
    residual_vol: float,
) -> ProfitMetrics:
    if odds is None or len(odds) == 0:
        return ProfitMetrics(False, 0, 0, 0.0, 0.0, 0.0, 0.0, residual_vol)

    bets = 0
    abstained = 0
    wins = 0
    profit = 0.0
    edge_sum = 0.0

    for i in range(len(y_out)):
        o_home, o_draw, o_away = float(odds[i, 0]), float(odds[i, 1]), float(odds[i, 2])
        if not (o_home > 1.01 and o_draw > 1.01 and o_away > 1.01):
            continue

        p_home = float(p3[i, 2])
        p_draw = float(p3[i, 1])
        p_away = float(p3[i, 0])
        ev_home = p_home * o_home - 1.0
        ev_draw = p_draw * o_draw - 1.0
        ev_away = p_away * o_away - 1.0
        evs = [ev_home, ev_draw, ev_away]
        choice = int(np.argmax(evs))
        edge = float(evs[choice])
        if edge < min_edge:
            continue
        if uncertainty is not None and i < len(uncertainty) and float(uncertainty[i]) > max_uncertainty:
            abstained += 1
            continue

        bets += 1
        edge_sum += edge
        actual = int(y_out[i])
        mapped_choice = {0: 2, 1: 1, 2: 0}[choice]  # ev order h/d/a -> y_out order away/draw/home
        if actual == mapped_choice:
            wins += 1
            odds_taken = [o_home, o_draw, o_away][choice]
            profit += odds_taken - 1.0
        else:
            profit -= 1.0

    if bets == 0:
        return ProfitMetrics(True, 0, abstained, 0.0, 0.0, 0.0, 0.0, residual_vol)
    return ProfitMetrics(
        True,
        bets=bets,
        abstained=abstained,
        hit_rate=float(wins / bets),
        profit_units=float(profit),
        roi=float(profit / bets),
        avg_edge=float(edge_sum / bets),
        residual_volatility=residual_vol,
    )


def run_single_holdout(
    X: np.ndarray,
    y_out: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    odds: Optional[np.ndarray],
    args: argparse.Namespace,
    league_seed: int,
) -> Dict[str, Any]:
    n = len(X)
    idx = int(round(n * (1.0 - args.holdout_ratio)))
    idx = max(args.wf_start_train, min(idx, n - 12))
    X_tr, X_te = X[:idx], X[idx:]
    y_out_tr, y_out_te = y_out[:idx], y_out[idx:]
    y_w_tr, y_w_te = y_w[:idx], y_w[idx:]
    y_h_tr, y_h_te = y_h[:idx], y_h[idx:]
    y_a_tr, y_a_te = y_a[:idx], y_a[idx:]
    odds_te = odds[idx:] if odds is not None else None
    selected_idx = np.arange(X.shape[1], dtype=int)
    if not args.disable_feature_selection:
        selected_idx = annealed_feature_subset(
            X_tr,
            y_w_tr,
            max_features=args.feature_select_max,
            steps=args.feature_select_steps,
            seed=league_seed + 91,
            redundancy_penalty=args.feature_select_penalty,
        )
        X_tr = X_tr[:, selected_idx]
        X_te = X_te[:, selected_idx]

    baseline_spec = {
        "family": "xgb",
        "params": {
            "n_estimators": 220,
            "max_depth": 6,
            "learning_rate": 0.08,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1.0,
            "reg_lambda": 1.0,
            "random_state": league_seed + 1,
        },
    }
    b_clf, b_h, b_a = instantiate_triplet(baseline_spec)
    b_clf_pack = fit_outcome_classifier(b_clf, X_tr, y_out_tr)
    b_h.fit(X_tr, y_h_tr)
    b_a.fit(X_tr, y_a_tr)
    b_p3 = predict_outcome_proba(b_clf_pack, X_te)
    b_ph = b_h.predict(X_te)
    b_pa = b_a.predict(X_te)
    _, _, b_score_entropy = build_rugby_score_density(
        b_ph,
        b_pa,
        max_score=args.score_density_max,
        sticky_boost=args.score_density_sticky_boost,
    )
    b_out_entropy = -np.sum(b_p3 * np.log(np.clip(b_p3, 1e-12, 1.0)), axis=1) / math.log(3.0)
    b_unc = 0.5 * b_out_entropy + 0.5 * b_score_entropy
    b_res_vol = residual_volatility(b_ph, b_pa, y_h_te, y_a_te)
    current_m = evaluate_from_predictions(b_p3, b_ph, b_pa, y_out_te, y_w_te, y_h_te, y_a_te)
    current_profit = evaluate_profit(
        b_p3,
        y_out_te,
        odds_te,
        args.min_bet_edge,
        uncertainty=b_unc,
        max_uncertainty=args.max_bet_uncertainty,
        residual_vol=b_res_vol,
    )

    candidates = sample_candidates(seed=league_seed + 42, per_family=args.search_rounds)
    leaderboard: List[Dict[str, Any]] = []
    for s in candidates:
        row = evaluate_candidate_on_timeseries(
            s,
            X_tr,
            y_out_tr,
            y_w_tr,
            y_h_tr,
            y_a_tr,
            args.cv_splits,
            cv_weight_outcome=args.cv_weight_outcome,
            cv_weight_winner=args.cv_weight_winner,
            cv_weight_mae=args.cv_weight_mae,
        )
        leaderboard.append(row)
    leaderboard.sort(key=lambda r: r["cv_score"], reverse=True)

    if args.quantum_mode:
        top_rows = quantum_qubo_select_candidates(leaderboard, target_k=args.top_k, steps=args.quantum_steps, seed=league_seed)
        top_rows = sorted(top_rows, key=lambda r: r["cv_score"], reverse=True)
    else:
        top_rows = leaderboard[: args.top_k]
    final_specs = [r["spec"] for r in top_rows]
    fitted = fit_models_from_specs(final_specs, X_tr, y_out_tr, y_h_tr, y_a_tr)
    w_out, w_score = blend_weights_from_leaderboard(top_rows, outcome_metric=args.blend_outcome_metric)

    if args.quantum_mode and len(fitted) >= 2:
        pm = np.array([predict_outcome_proba(m["clf_pack"], X_tr)[:, 2] for m in fitted], dtype=float)
        qw = quantum_optimize_blend_weights(
            pm,
            y_w_tr,
            steps=args.quantum_steps,
            seed=league_seed + 1234,
        )
        w_out = qw.tolist()

    p3, ph, pa = aggregate_predictions(fitted, w_out, w_score, X_te)
    _, _, m_score_entropy = build_rugby_score_density(
        ph,
        pa,
        max_score=args.score_density_max,
        sticky_boost=args.score_density_sticky_boost,
    )
    m_out_entropy = -np.sum(p3 * np.log(np.clip(p3, 1e-12, 1.0)), axis=1) / math.log(3.0)
    m_unc = 0.5 * m_out_entropy + 0.5 * m_score_entropy
    m_res_vol = residual_volatility(ph, pa, y_h_te, y_a_te)
    maz_m = evaluate_from_predictions(p3, ph, pa, y_out_te, y_w_te, y_h_te, y_a_te)
    maz_profit = evaluate_profit(
        p3,
        y_out_te,
        odds_te,
        args.min_bet_edge,
        uncertainty=m_unc,
        max_uncertainty=args.max_bet_uncertainty,
        residual_vol=m_res_vol,
    )

    return {
        "current": current_m,
        "maz": maz_m,
        "current_profit": current_profit,
        "maz_profit": maz_profit,
        "train_rows": int(len(X_tr)),
        "test_rows": int(len(X_te)),
        "top_rows": top_rows,
        "final_specs": final_specs,
        "blend_weights": {"outcome": w_out, "score": w_score},
        "selected_indices": selected_idx.tolist(),
        "uncertainty_avg_current": float(np.mean(b_unc)) if len(b_unc) else 0.0,
        "uncertainty_avg_maz": float(np.mean(m_unc)) if len(m_unc) else 0.0,
    }


def run_walkforward(
    X: np.ndarray,
    y_out: np.ndarray,
    y_w: np.ndarray,
    y_h: np.ndarray,
    y_a: np.ndarray,
    odds: Optional[np.ndarray],
    args: argparse.Namespace,
    league_seed: int,
) -> Dict[str, Any]:
    n = len(X)
    start = max(args.wf_start_train, 40)
    if start >= n - 1:
        raise ValueError(f"Not enough rows for walk-forward: n={n}, wf_start_train={start}")
    total_chunks = len(range(start, n, max(1, args.wf_step)))
    LOG.info(
        "[league_seed=%s] walk-forward start: rows=%s, chunks=%s, step=%s",
        league_seed,
        n,
        total_chunks,
        max(1, args.wf_step),
    )

    # Select candidate specs once on initial window, then refit through time.
    X_init = X[:start]
    y_out_init = y_out[:start]
    y_w_init = y_w[:start]
    y_h_init = y_h[:start]
    y_a_init = y_a[:start]
    selected_idx = np.arange(X.shape[1], dtype=int)
    if not args.disable_feature_selection:
        LOG.info(
            "[league_seed=%s] feature selection start: rows=%s cols=%s target_max=%s steps=%s",
            league_seed,
            X_init.shape[0],
            X_init.shape[1],
            args.feature_select_max,
            args.feature_select_steps,
        )
        selected_idx = annealed_feature_subset(
            X_init,
            y_w_init,
            max_features=args.feature_select_max,
            steps=args.feature_select_steps,
            seed=league_seed + 91,
            redundancy_penalty=args.feature_select_penalty,
        )
        LOG.info(
            "[league_seed=%s] feature selection done: kept=%s dropped=%s",
            league_seed,
            len(selected_idx),
            X_init.shape[1] - len(selected_idx),
        )
    else:
        LOG.info(
            "[league_seed=%s] feature selection skipped: using all %s features",
            league_seed,
            X_init.shape[1],
        )
    X_init_sel = X_init[:, selected_idx]

    candidates = sample_candidates(seed=league_seed + 42, per_family=args.search_rounds)
    LOG.info(
        "[league_seed=%s] candidate search start: candidates=%s cv_splits=%s",
        league_seed,
        len(candidates),
        max(2, args.cv_splits - 1),
    )
    leaderboard: List[Dict[str, Any]] = []
    total_candidates = len(candidates)
    for i, s in enumerate(candidates, start=1):
        row = evaluate_candidate_on_timeseries(
            s,
            X_init_sel,
            y_out_init,
            y_w_init,
            y_h_init,
            y_a_init,
            max(2, args.cv_splits - 1),
            cv_weight_outcome=args.cv_weight_outcome,
            cv_weight_winner=args.cv_weight_winner,
            cv_weight_mae=args.cv_weight_mae,
        )
        leaderboard.append(row)
        if i % 10 == 0 or i == total_candidates:
            LOG.info(
                "[league_seed=%s] candidate eval progress: %s/%s",
                league_seed,
                i,
                total_candidates,
            )
    leaderboard.sort(key=lambda r: r["cv_score"], reverse=True)
    if args.quantum_mode:
        LOG.info(
            "[league_seed=%s] quantum candidate select start: top_k=%s steps=%s",
            league_seed,
            args.top_k,
            args.quantum_steps,
        )
        top_rows = quantum_qubo_select_candidates(leaderboard, target_k=args.top_k, steps=args.quantum_steps, seed=league_seed)
        top_rows = sorted(top_rows, key=lambda r: r["cv_score"], reverse=True)
    else:
        top_rows = leaderboard[: args.top_k]
    LOG.info(
        "[league_seed=%s] candidate search done: selected_top_k=%s",
        league_seed,
        len(top_rows),
    )
    final_specs = [r["spec"] for r in top_rows]

    all_b_p3: List[np.ndarray] = []
    all_b_h: List[np.ndarray] = []
    all_b_a: List[np.ndarray] = []
    all_m_p3: List[np.ndarray] = []
    all_m_h: List[np.ndarray] = []
    all_m_a: List[np.ndarray] = []
    all_b_unc: List[np.ndarray] = []
    all_m_unc: List[np.ndarray] = []
    y_out_eval: List[np.ndarray] = []
    y_w_eval: List[np.ndarray] = []
    y_h_eval: List[np.ndarray] = []
    y_a_eval: List[np.ndarray] = []
    odds_eval: List[np.ndarray] = []

    baseline_spec = {
        "family": "xgb",
        "params": {
            "n_estimators": 220,
            "max_depth": 6,
            "learning_rate": 0.08,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1.0,
            "reg_lambda": 1.0,
            "random_state": league_seed + 1,
        },
    }

    step = max(1, args.wf_step)
    for chunk_i, cut in enumerate(range(start, n, step), start=1):
        nxt = min(n, cut + step)
        X_tr = X[:cut][:, selected_idx]
        X_te = X[cut:nxt][:, selected_idx]
        y_out_tr = y_out[:cut]
        y_h_tr = y_h[:cut]
        y_a_tr = y_a[:cut]
        y_out_te = y_out[cut:nxt]
        y_w_te = y_w[cut:nxt]
        y_h_te = y_h[cut:nxt]
        y_a_te = y_a[cut:nxt]
        odds_te = odds[cut:nxt] if odds is not None else None

        # Current baseline
        b_clf, b_h, b_a = instantiate_triplet(baseline_spec)
        b_clf_pack = fit_outcome_classifier(b_clf, X_tr, y_out_tr)
        b_h.fit(X_tr, y_h_tr)
        b_a.fit(X_tr, y_a_tr)
        b_p3 = predict_outcome_proba(b_clf_pack, X_te)
        b_ph = b_h.predict(X_te)
        b_pa = b_a.predict(X_te)
        _, _, b_score_entropy = build_rugby_score_density(
            b_ph,
            b_pa,
            max_score=args.score_density_max,
            sticky_boost=args.score_density_sticky_boost,
        )
        b_out_entropy = -np.sum(b_p3 * np.log(np.clip(b_p3, 1e-12, 1.0)), axis=1) / math.log(3.0)
        b_unc = 0.5 * b_out_entropy + 0.5 * b_score_entropy

        # MAZ ensemble
        fitted = fit_models_from_specs(final_specs, X_tr, y_out_tr, y_h_tr, y_a_tr)
        w_out, w_score = blend_weights_from_leaderboard(top_rows, outcome_metric=args.blend_outcome_metric)
        if args.quantum_mode and len(fitted) >= 2:
            pm = np.array([predict_outcome_proba(m["clf_pack"], X_tr)[:, 2] for m in fitted], dtype=float)
            qw = quantum_optimize_blend_weights(
                pm,
                (y_h_tr > y_a_tr).astype(int),
                steps=max(300, args.quantum_steps // 2),
                seed=league_seed + 777 + cut,
            )
            w_out = qw.tolist()
        m_p3, m_ph, m_pa = aggregate_predictions(fitted, w_out, w_score, X_te)
        _, _, m_score_entropy = build_rugby_score_density(
            m_ph,
            m_pa,
            max_score=args.score_density_max,
            sticky_boost=args.score_density_sticky_boost,
        )
        m_out_entropy = -np.sum(m_p3 * np.log(np.clip(m_p3, 1e-12, 1.0)), axis=1) / math.log(3.0)
        m_unc = 0.5 * m_out_entropy + 0.5 * m_score_entropy

        all_b_p3.append(b_p3)
        all_b_h.append(b_ph)
        all_b_a.append(b_pa)
        all_b_unc.append(b_unc)
        all_m_p3.append(m_p3)
        all_m_h.append(m_ph)
        all_m_a.append(m_pa)
        all_m_unc.append(m_unc)
        y_out_eval.append(y_out_te)
        y_w_eval.append(y_w_te)
        y_h_eval.append(y_h_te)
        y_a_eval.append(y_a_te)
        if odds_te is not None:
            odds_eval.append(odds_te)
        LOG.info(
            "[league_seed=%s] chunk %s/%s done | train=%s test=%s",
            league_seed,
            chunk_i,
            total_chunks,
            len(X_tr),
            len(X_te),
        )

    b_p3_all = np.concatenate(all_b_p3, axis=0)
    b_h_all = np.concatenate(all_b_h, axis=0)
    b_a_all = np.concatenate(all_b_a, axis=0)
    m_p3_all = np.concatenate(all_m_p3, axis=0)
    m_h_all = np.concatenate(all_m_h, axis=0)
    m_a_all = np.concatenate(all_m_a, axis=0)
    y_out_all = np.concatenate(y_out_eval, axis=0)
    y_w_all = np.concatenate(y_w_eval, axis=0)
    y_h_all = np.concatenate(y_h_eval, axis=0)
    y_a_all = np.concatenate(y_a_eval, axis=0)
    odds_all = np.concatenate(odds_eval, axis=0) if odds_eval else None
    b_unc_all = np.concatenate(all_b_unc, axis=0)
    m_unc_all = np.concatenate(all_m_unc, axis=0)

    current_m = evaluate_from_predictions(b_p3_all, b_h_all, b_a_all, y_out_all, y_w_all, y_h_all, y_a_all)
    maz_m = evaluate_from_predictions(m_p3_all, m_h_all, m_a_all, y_out_all, y_w_all, y_h_all, y_a_all)
    b_res_vol = residual_volatility(b_h_all, b_a_all, y_h_all, y_a_all)
    m_res_vol = residual_volatility(m_h_all, m_a_all, y_h_all, y_a_all)
    current_profit = evaluate_profit(
        b_p3_all,
        y_out_all,
        odds_all,
        args.min_bet_edge,
        uncertainty=b_unc_all,
        max_uncertainty=args.max_bet_uncertainty,
        residual_vol=b_res_vol,
    )
    maz_profit = evaluate_profit(
        m_p3_all,
        y_out_all,
        odds_all,
        args.min_bet_edge,
        uncertainty=m_unc_all,
        max_uncertainty=args.max_bet_uncertainty,
        residual_vol=m_res_vol,
    )

    return {
        "current": current_m,
        "maz": maz_m,
        "current_profit": current_profit,
        "maz_profit": maz_profit,
        "train_rows": int(start),
        "test_rows": int(len(y_out_all)),
        "top_rows": top_rows,
        "final_specs": final_specs,
        "blend_weights": {"outcome": [], "score": []},  # dynamic in walk-forward
        "selected_indices": selected_idx.tolist(),
        "uncertainty_avg_current": float(np.mean(b_unc_all)) if len(b_unc_all) else 0.0,
        "uncertainty_avg_maz": float(np.mean(m_unc_all)) if len(m_unc_all) else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MAZ Boss MAXED V2 (walk-forward, 3-way, profit-aware).")
    parser.add_argument("--db-path", default=None, help="SQLite path (auto-detect by default).")
    parser.add_argument("--league-id", type=int, default=None, help="Single league id.")
    parser.add_argument("--all-leagues", action="store_true", help="Run all leagues.")
    parser.add_argument("--walk-forward", action="store_true", help="Use full walk-forward unseen evaluation.")
    parser.add_argument("--holdout-ratio", type=float, default=0.2, help="Used when --walk-forward is off.")
    parser.add_argument("--wf-start-train", type=int, default=120, help="Initial train rows for walk-forward.")
    parser.add_argument("--wf-step", type=int, default=20, help="Walk-forward chunk size.")
    parser.add_argument("--min-games", type=int, default=120, help="Minimum completed games per league.")
    parser.add_argument("--search-rounds", type=int, default=6, help="Candidate rounds per family.")
    parser.add_argument("--top-k", type=int, default=6, help="Top candidates to blend.")
    parser.add_argument("--cv-splits", type=int, default=5, help="Inner time-series CV splits.")
    parser.add_argument("--save-maz-models", action="store_true", help="Save winning MAZ models.")
    parser.add_argument(
        "--winner-first-mode",
        action="store_true",
        help="Prioritize binary winner performance over 3-way outcome during model selection.",
    )
    parser.add_argument(
        "--cv-weight-outcome",
        type=float,
        default=0.22,
        help="CV ranking weight for 3-way outcome accuracy.",
    )
    parser.add_argument(
        "--cv-weight-winner",
        type=float,
        default=0.78,
        help="CV ranking weight for binary winner accuracy.",
    )
    parser.add_argument(
        "--cv-weight-mae",
        type=float,
        default=0.004,
        help="CV ranking penalty weight on MAE (lower is better).",
    )
    parser.add_argument(
        "--blend-outcome-metric",
        choices=["winner", "hybrid", "outcome"],
        default="winner",
        help="Signal used for ensemble outcome blending weights.",
    )
    parser.add_argument("--min-winner-gain", type=float, default=0.005, help="Meaningful winner accuracy gain.")
    parser.add_argument("--min-outcome-gain", type=float, default=0.0, help="Meaningful 3-way outcome accuracy gain.")
    parser.add_argument("--min-mae-reduction", type=float, default=0.05, help="Meaningful MAE reduction.")
    parser.add_argument("--max-mae-worsen-winner-head", type=float, default=0.20, help="Allowed MAE worsen when winner gain is strong.")
    parser.add_argument("--max-winner-drop-score-head", type=float, default=0.0, help="Allowed winner-acc drop when MAE gain is strong.")
    parser.add_argument(
        "--max-winner-drop-vs-legacy",
        type=float,
        default=0.0,
        help="Allowed winner-acc drop vs best of CURRENT and legacy maz_maxed.",
    )
    parser.add_argument(
        "--max-outcome-drop-vs-legacy",
        type=float,
        default=0.0,
        help="Allowed outcome-acc drop vs best of CURRENT and legacy maz_maxed.",
    )
    parser.add_argument("--profit-aware", action="store_true", help="Print odds-aware profit deltas when odds exist.")
    parser.add_argument("--min-bet-edge", type=float, default=0.03, help="Minimum EV edge per bet for profit simulation.")
    parser.add_argument("--quantum-mode", action="store_true", help="Enable quantum-inspired selection and weighting.")
    parser.add_argument("--quantum-steps", type=int, default=1800, help="Annealing steps.")
    parser.add_argument("--no-ultimate-features", action="store_true", help="Disable multi-lag + graph power feature augmentation.")
    parser.add_argument("--graph-window", type=int, default=260, help="Rolling graph edge window for power features.")
    parser.add_argument("--graph-iters", type=int, default=14, help="PageRank iterations for graph power features.")
    parser.add_argument("--graph-half-life", type=float, default=120.0, help="Half-life in matches for graph edge time decay.")
    parser.add_argument("--disable-feature-selection", action="store_true", help="Disable annealed feature subset selection.")
    parser.add_argument("--feature-select-max", type=int, default=180, help="Target max feature count after selection.")
    parser.add_argument("--feature-select-steps", type=int, default=1400, help="Annealing steps for feature subset search.")
    parser.add_argument("--feature-select-penalty", type=float, default=0.12, help="Redundancy penalty in annealed feature selection.")
    parser.add_argument("--score-density-max", type=int, default=70, help="Maximum discrete score for rugby score-density head.")
    parser.add_argument("--score-density-sticky-boost", type=float, default=0.35, help="Extra mass for rugby-plausible totals in score density.")
    parser.add_argument("--max-bet-uncertainty", type=float, default=0.72, help="Abstain betting above this uncertainty score (0..1).")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=None, help="Optional run log file path.")
    args = parser.parse_args()
    auto_log_file: Optional[str] = args.log_file
    if not auto_log_file:
        auto_log_file = f"artifacts/maz_maxed_v2_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _setup_logging(args.log_level, auto_log_file)
    LOG.info("Starting MAZ MAXED V2 run")
    LOG.info("Logging to: %s", auto_log_file)

    if args.cv_weight_outcome < 0 or args.cv_weight_winner < 0 or args.cv_weight_mae < 0:
        raise SystemExit("CV weights must be non-negative.")
    if (args.cv_weight_outcome + args.cv_weight_winner) <= 0:
        raise SystemExit("At least one of --cv-weight-outcome or --cv-weight-winner must be > 0.")
    # Normalize ranking accuracy weights for stable scoring scale.
    acc_sum = args.cv_weight_outcome + args.cv_weight_winner
    args.cv_weight_outcome = float(args.cv_weight_outcome / acc_sum)
    args.cv_weight_winner = float(args.cv_weight_winner / acc_sum)

    if not args.league_id and not args.all_leagues:
        raise SystemExit("Use --league-id <id> or --all-leagues")

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    if args.league_id:
        leagues = {args.league_id: LEAGUE_MAPPINGS.get(args.league_id, f"League {args.league_id}")}
    else:
        leagues = LEAGUE_MAPPINGS

    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "db_path": str(db_path),
        "config": {
            "walk_forward": bool(args.walk_forward),
            "holdout_ratio": args.holdout_ratio,
            "wf_start_train": args.wf_start_train,
            "wf_step": args.wf_step,
            "min_games": args.min_games,
            "search_rounds": args.search_rounds,
            "top_k": args.top_k,
            "cv_splits": args.cv_splits,
            "winner_first_mode": bool(args.winner_first_mode),
            "cv_weight_outcome": args.cv_weight_outcome,
            "cv_weight_winner": args.cv_weight_winner,
            "cv_weight_mae": args.cv_weight_mae,
            "blend_outcome_metric": args.blend_outcome_metric,
            "min_winner_gain": args.min_winner_gain,
            "min_outcome_gain": args.min_outcome_gain,
            "min_mae_reduction": args.min_mae_reduction,
            "max_mae_worsen_winner_head": args.max_mae_worsen_winner_head,
            "max_winner_drop_score_head": args.max_winner_drop_score_head,
            "max_winner_drop_vs_legacy": args.max_winner_drop_vs_legacy,
            "max_outcome_drop_vs_legacy": args.max_outcome_drop_vs_legacy,
            "profit_aware": bool(args.profit_aware),
            "min_bet_edge": args.min_bet_edge,
            "quantum_mode": bool(args.quantum_mode),
            "quantum_steps": args.quantum_steps,
            "ultimate_features": bool(not args.no_ultimate_features),
            "graph_window": args.graph_window,
            "graph_iters": args.graph_iters,
            "graph_half_life": args.graph_half_life,
            "feature_selection": bool(not args.disable_feature_selection),
            "feature_select_max": args.feature_select_max,
            "feature_select_steps": args.feature_select_steps,
            "feature_select_penalty": args.feature_select_penalty,
            "score_density_max": args.score_density_max,
            "score_density_sticky_boost": args.score_density_sticky_boost,
            "max_bet_uncertainty": args.max_bet_uncertainty,
            "log_level": args.log_level,
            "log_file": auto_log_file,
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
        LOG.info("[%s] starting evaluation", league_name)
        df = load_league_df(conn, league_id)
        if len(df) < args.min_games:
            report["summary"]["skipped"] += 1
            report["leagues"][str(league_id)] = {
                "name": league_name,
                "status": "skipped",
                "reason": f"not enough games ({len(df)} < {args.min_games})",
            }
            LOG.warning("[%s] skipped: not enough games (%s < %s)", league_name, len(df), args.min_games)
            continue

        if not args.no_ultimate_features:
            df_model = augment_ultimate_features(
                df,
                graph_window=args.graph_window,
                graph_iters=args.graph_iters,
                graph_half_life=args.graph_half_life,
            )
        else:
            df_model = df

        odds_cols = detect_odds_columns(df_model)
        X, y_out, y_w, y_h, y_a, feature_cols, odds = prepare_xy(df_model, odds_cols)

        try:
            if args.walk_forward:
                run = run_walkforward(X, y_out, y_w, y_h, y_a, odds, args, league_seed=league_id)
            else:
                run = run_single_holdout(X, y_out, y_w, y_h, y_a, odds, args, league_seed=league_id)
        except Exception as ex:
            report["summary"]["skipped"] += 1
            report["leagues"][str(league_id)] = {
                "name": league_name,
                "status": "skipped",
                "reason": f"runtime error: {ex}",
            }
            LOG.warning("[%s] skipped due to runtime error: %s", league_name, ex)
            continue

        current_m: Metrics = run["current"]
        maz_m: Metrics = run["maz"]
        current_profit: ProfitMetrics = run["current_profit"]
        maz_profit: ProfitMetrics = run["maz_profit"]
        legacy_m = load_legacy_maz_metrics(league_id)
        selected_indices = run.get("selected_indices", list(range(len(feature_cols))))
        selected_feature_cols = [feature_cols[i] for i in selected_indices if 0 <= i < len(feature_cols)]

        winner = choose_winner_mode(
            current_m,
            maz_m,
            legacy_m,
            min_winner_gain=args.min_winner_gain,
            min_outcome_gain=args.min_outcome_gain,
            min_mae_reduction=args.min_mae_reduction,
            max_mae_worsen_winner_head=args.max_mae_worsen_winner_head,
            max_winner_drop_score_head=args.max_winner_drop_score_head,
            max_winner_drop_vs_legacy=args.max_winner_drop_vs_legacy,
            max_outcome_drop_vs_legacy=args.max_outcome_drop_vs_legacy,
            winner_first_mode=bool(args.winner_first_mode),
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
            "games": int(len(df)),
            "train_rows": run["train_rows"],
            "test_rows": run["test_rows"],
            "raw_feature_count": len(feature_cols),
            "feature_count": len(selected_feature_cols),
            "selected_feature_columns": selected_feature_cols,
            "odds_columns": list(odds_cols) if odds_cols else None,
            "mode": "walk_forward" if args.walk_forward else "single_holdout",
            "current": current_m.__dict__,
            "legacy_maz_maxed": legacy_m.__dict__ if legacy_m is not None else None,
            "maz_maxed_v2": maz_m.__dict__,
            "profit_current": current_profit.__dict__,
            "profit_maz": maz_profit.__dict__,
            "uncertainty": {
                "current_avg": run.get("uncertainty_avg_current", 0.0),
                "maz_avg": run.get("uncertainty_avg_maz", 0.0),
                "abstain_threshold": args.max_bet_uncertainty,
            },
            "deltas": {
                "winner_accuracy_gain": maz_m.winner_accuracy - current_m.winner_accuracy,
                "outcome_accuracy_gain": maz_m.outcome_accuracy - current_m.outcome_accuracy,
                "overall_mae_reduction": current_m.overall_mae - maz_m.overall_mae,
                "winner_accuracy_vs_legacy": (
                    (maz_m.winner_accuracy - legacy_m.winner_accuracy) if legacy_m is not None else None
                ),
                "outcome_accuracy_vs_legacy": (
                    (maz_m.outcome_accuracy - legacy_m.outcome_accuracy) if legacy_m is not None else None
                ),
                "roi_gain": (maz_profit.roi - current_profit.roi) if maz_profit.has_odds and current_profit.has_odds else None,
                "residual_volatility_reduction": current_profit.residual_volatility - maz_profit.residual_volatility,
            },
            "winner": winner,
            "top_candidate_cv": run["top_rows"],
            "final_member_count": len(run["final_specs"]),
            "blend_weights": run["blend_weights"],
        }

        if args.save_maz_models and winner.startswith("MAZ_"):
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"league_{league_id}_model_maz_maxed_v2_{winner.lower()}.pkl"
            with out_file.open("wb") as f:
                pickle.dump(
                    {
                        "league_id": league_id,
                        "league_name": league_name,
                        "model_type": "maz_maxed_v2_ensemble",
                        "trained_at": datetime.now().isoformat(),
                        "feature_columns_all": feature_cols,
                        "feature_columns_selected": selected_feature_cols,
                        "selected_feature_indices": selected_indices,
                        "specs": run["final_specs"],
                        "blend_weights": run["blend_weights"],
                        "metrics_unseen": maz_m.__dict__,
                        "baseline_unseen": current_m.__dict__,
                        "winner_mode": winner,
                        "walk_forward": bool(args.walk_forward),
                        "odds_columns": list(odds_cols) if odds_cols else None,
                    },
                    f,
                )
            payload["saved_model"] = str(out_file)

        report["leagues"][str(league_id)] = payload

        line = (
            f"[{league_name}] curr_win_acc={current_m.winner_accuracy:.3f} maz_win_acc={maz_m.winner_accuracy:.3f} | "
            f"curr_out_acc={current_m.outcome_accuracy:.3f} maz_out_acc={maz_m.outcome_accuracy:.3f} | "
            f"curr_mae={current_m.overall_mae:.3f} maz_mae={maz_m.overall_mae:.3f} | winner={winner}"
        )
        if args.profit_aware and maz_profit.has_odds and current_profit.has_odds:
            line += (
                f" | curr_roi={current_profit.roi:.3f} maz_roi={maz_profit.roi:.3f} "
                f"(bets {current_profit.bets}/{maz_profit.bets})"
            )
        LOG.info("%s", line)

    conn.close()

    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"maz_maxed_v2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("=== MAZ MAXED V2 Summary ===")
    LOG.info("%s", json.dumps(report["summary"], indent=2))
    LOG.info("Report saved: %s", out_file)


if __name__ == "__main__":
    main()

