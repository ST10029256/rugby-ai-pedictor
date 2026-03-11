#!/usr/bin/env python3
"""
MAZ Boss MAXED V4 (Temporal + Interaction Intelligence Engine)

V4 research architecture:
- Learnable team embeddings
- Temporal sequence encoder (GRU) per team
- Team-vs-team interaction MLP
- Multi-head outputs: winner logit, score means, score variances, learned alpha
- Learned blend: alpha * p_classifier + (1-alpha) * p_score_dist
- Post-hoc calibration (isotonic/platt fallback)

This file is intentionally self-contained and does not replace V3.

Upgrades in this version:
- rating-aware temporal features
- recency-weighted training
- calibrated runtime-compatible probabilities
- confidence thresholds learned from train behavior
"""

from __future__ import annotations
# pyright: reportMissingImports=false

import argparse
import json
import logging
import math
import pickle
import sqlite3
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Set, Tuple

try:
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
    import torch.nn.functional as F  # type: ignore
except Exception as e:
    torch = None
    class _NNFallback:  # keeps class declarations import-safe without torch
        class Module:
            pass
    nn = _NNFallback()  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR = e

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error

sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import FeatureConfig, build_feature_table

V4_VERSION = "v4"
LOG = logging.getLogger("maz_v4")
FRIENDLIES_LEAGUE_ID = 5479
DEFAULT_PROB_STD_THRESHOLD = 0.06
SCORE_HUBER_MIX = 0.0
HOME_CONTEXT_RATE_SPAN = 0.18
CONTEXT_PLATT_MIN_ROWS = 800
ISOTONIC_MIN_ROWS = 1200
SMALL_SAMPLE_ROWS = 300
MEDIUM_SAMPLE_ROWS = 800
LOW_SAMPLE_SHRINK_MAX = 0.15
HIGH_SAMPLE_SHRINK_MAX = 0.35
LEAGUE_HOME_ADV_PRIOR: Dict[int, float] = {
    4551: 0.58,  # Super Rugby
    4986: 0.56,  # Rugby Championship
    4446: 0.57,  # United Rugby Championship
    4430: 0.60,  # French Top 14
    4414: 0.56,  # English Premiership
    5069: 0.57,  # Currie Cup
    4714: 0.54,  # Six Nations
    4574: 0.50,  # Rugby World Cup: conservative prior, let data override it
    5479: 0.52,  # Friendlies
}


@dataclass
class Metrics:
    winner_accuracy: float
    home_mae: float
    away_mae: float
    overall_mae: float
    brier_winner: float
    ece_winner: float
    rows: int


def _parse_int_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).split(","):
        p = part.strip()
        if not p:
            continue
        out.append(int(p))
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
    return df.reset_index(drop=True)


def _team_key(team_id: Any) -> int:
    try:
        return int(team_id)
    except Exception:
        return -1


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    # 0.5 * (1 + erf(x / sqrt(2)))
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def _ece_binary(y_true: np.ndarray, p_pred: np.ndarray, bins: int = 10) -> float:
    y = y_true.astype(float)
    p = np.clip(p_pred.astype(float), 1e-6, 1.0 - 1e-6)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = 0.0
    n = len(y)
    if n == 0:
        return 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if not np.any(m):
            continue
        conf = float(np.mean(p[m]))
        acc = float(np.mean(y[m]))
        w = float(np.mean(m))
        out += w * abs(acc - conf)
    return float(out)


def build_global_team_to_idx(df: pd.DataFrame) -> Dict[int, int]:
    ids: Set[int] = set()
    for _, r in df.iterrows():
        ids.add(_team_key(r["home_team_id"]))
        ids.add(_team_key(r["away_team_id"]))
    teams = sorted(ids)
    return {tid: i for i, tid in enumerate(teams)}


def build_global_league_to_idx(league_ids: Sequence[int]) -> Dict[int, int]:
    lids = sorted(int(x) for x in league_ids)
    return {lid: i for i, lid in enumerate(lids)}


def build_league_score_stats(df_train: pd.DataFrame) -> Dict[int, Tuple[float, float]]:
    out: Dict[int, Tuple[float, float]] = {}
    for lid, g in df_train.groupby("league_id"):
        vals = np.concatenate(
            [g["home_score"].astype(float).values, g["away_score"].astype(float).values],
            axis=0,
        )
        mu = float(np.mean(vals)) if len(vals) else 20.0
        sd = float(np.std(vals)) if len(vals) else 8.0
        if not np.isfinite(mu):
            mu = 20.0
        if not np.isfinite(sd) or sd < 1e-6:
            sd = 8.0
        out[int(lid)] = (mu, sd)
    return out


def build_league_environment_stats(
    df_train: pd.DataFrame,
    base_rating_home_adv: float,
) -> Dict[int, Dict[str, float]]:
    out: Dict[int, Dict[str, float]] = {}
    default_prior = 0.55
    for lid, g in df_train.groupby("league_id"):
        lid_i = int(lid)
        prior_home_prob = float(LEAGUE_HOME_ADV_PRIOR.get(lid_i, default_prior))
        n = len(g)
        empirical_home_prob = float(np.mean(g["home_score"].astype(float).values > g["away_score"].astype(float).values))
        blend_w = min(0.80, max(0.0, n / 400.0))
        blended_home_prob = ((blend_w * empirical_home_prob) + ((1.0 - blend_w) * prior_home_prob))
        # "Home" here is really listing/context advantage, not purely venue.
        # Some tournaments look neutral in theory but still have strong home-side signal in the data.
        home_strength = float(np.clip((blended_home_prob - 0.50) / HOME_CONTEXT_RATE_SPAN, 0.0, 1.0))
        # Keep the handcrafted rating update stable across leagues; let the neural features
        # learn league-specific home/listing context from `home_strength`.
        rating_home_adv = float(base_rating_home_adv)
        out[lid_i] = {
            "home_prob": blended_home_prob,
            "home_strength": home_strength,
            "rating_home_adv": rating_home_adv,
        }
    return out


def scale_score_targets(
    y_raw: np.ndarray,
    league_ids: np.ndarray,
    league_stats: Dict[int, Tuple[float, float]],
) -> np.ndarray:
    y_scaled = y_raw.copy()
    for i in range(len(y_scaled)):
        lid = int(league_ids[i])
        mu, sd = league_stats.get(lid, (20.0, 8.0))
        y_scaled[i, 1] = (y_scaled[i, 1] - mu) / sd
        y_scaled[i, 2] = (y_scaled[i, 2] - mu) / sd
    return y_scaled


def unscale_score_predictions(
    mu_scaled: np.ndarray,
    league_ids: np.ndarray,
    league_stats: Dict[int, Tuple[float, float]],
) -> np.ndarray:
    out = mu_scaled.copy()
    for i in range(len(out)):
        lid = int(league_ids[i])
        mu, sd = league_stats.get(lid, (20.0, 8.0))
        out[i, 0] = (out[i, 0] * sd) + mu
        out[i, 1] = (out[i, 1] * sd) + mu
    return out


def unscale_score_variances(
    var_scaled: np.ndarray,
    league_ids: np.ndarray,
    league_stats: Dict[int, Tuple[float, float]],
) -> np.ndarray:
    out = var_scaled.copy()
    for i in range(len(out)):
        lid = int(league_ids[i])
        _, sd = league_stats.get(lid, (20.0, 8.0))
        if not np.isfinite(sd) or sd < 1e-6:
            sd = 8.0
        scale = float(sd * sd)
        out[i, 0] = out[i, 0] * scale
        out[i, 1] = out[i, 1] * scale
    return out


def build_recency_weights(df: pd.DataFrame, half_life_days: float) -> np.ndarray:
    if len(df) == 0 or half_life_days <= 0:
        return np.ones(len(df), dtype=np.float32)
    dates = pd.to_datetime(df["date_event"], errors="coerce")
    if dates.isna().all():
        return np.ones(len(df), dtype=np.float32)
    last_dt = dates.max()
    ages = (last_dt - dates).dt.days.fillna(0).clip(lower=0).astype(float).to_numpy()
    weights = np.power(0.5, ages / max(1.0, float(half_life_days))).astype(np.float32)
    mean_w = float(np.mean(weights)) if len(weights) else 1.0
    if not np.isfinite(mean_w) or mean_w <= 1e-6:
        mean_w = 1.0
    return (weights / mean_w).astype(np.float32)


def weighted_mean(values: torch.Tensor, weights: Optional[torch.Tensor]) -> torch.Tensor:
    if weights is None or weights.numel() == 0:
        return torch.mean(values)
    w = weights / torch.clamp(torch.sum(weights), min=1e-6)
    return torch.sum(values * w)


def _quantile_or_fallback(values: np.ndarray, q: float, fallback: float) -> float:
    if len(values) == 0:
        return float(fallback)
    out = float(np.quantile(values.astype(float), q))
    if not np.isfinite(out):
        return float(fallback)
    return out


def _make_sequence_features(
    *,
    points_for_scaled: float,
    points_against_scaled: float,
    margin_scaled: float,
    is_home: float,
    venue_adv_context: float,
    rest_days_norm: float,
    margin_vol5_norm: float,
    margin_vol10_norm: float,
    team_rating_pre: float,
    opp_rating_pre: float,
    expected_margin_pre: float,
    score_sd: float,
) -> np.ndarray:
    sd = max(1.0, float(score_sd))
    return np.array(
        [
            points_for_scaled,
            points_against_scaled,
            margin_scaled,
            is_home,
            venue_adv_context,
            rest_days_norm,
            margin_vol5_norm,
            margin_vol10_norm,
            float(team_rating_pre) / sd,
            float(opp_rating_pre) / sd,
            float(expected_margin_pre) / sd,
        ],
        dtype=np.float32,
    )


def detect_regime(df_train: pd.DataFrame) -> Tuple[str, int, float]:
    if df_train.empty:
        return ("balanced_competitive", 1, 1.0)
    hs = df_train["home_score"].astype(float).values
    aw = df_train["away_score"].astype(float).values
    n = len(df_train)
    margins = hs - aw
    abs_margin = np.abs(margins)
    score_var = float(np.var(np.concatenate([hs, aw], axis=0)))
    upset_rate = float(np.mean(abs_margin <= np.percentile(abs_margin, 35.0))) if n > 10 else 0.0
    if n < 140:
        return ("chaotic_small_sample", 3, 1.25)
    if score_var > 140.0 or upset_rate > 0.42:
        return ("high_variance", 2, 1.20)
    if abs(float(np.mean(margins))) > 3.0:
        return ("stable_dominant", 0, 0.92)
    return ("balanced_competitive", 1, 1.00)


def detect_regime_map_by_league(df_train: pd.DataFrame) -> Dict[int, Tuple[str, int, float]]:
    out: Dict[int, Tuple[str, int, float]] = {}
    for lid, g in df_train.groupby("league_id"):
        out[int(lid)] = detect_regime(g)
    return out


def _rolling_std(vals: Deque[float], n: int) -> float:
    if not vals:
        return 0.0
    arr = np.array(list(vals)[-n:], dtype=float)
    if len(arr) <= 1:
        return 0.0
    return float(np.std(arr))


def build_temporal_sequences(
    df: pd.DataFrame,
    seq_len: int,
    team_to_idx: Dict[int, int] | None = None,
    league_to_idx: Dict[int, int] | None = None,
    league_stats: Dict[int, Tuple[float, float]] | None = None,
    league_env_stats: Dict[int, Dict[str, float]] | None = None,
    rating_k: float = 0.06,
    rating_home_adv: float = 2.0,
    rating_scale: float = 7.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[int, int], Dict[int, int]]:
    """
    Build chronology-safe team sequences from raw scores.
    Each sequence step uses:
    [points_for_scaled, points_against_scaled, margin_scaled, is_home, venue_adv_context,
     rest_days_norm, margin_vol5_norm, margin_vol10_norm,
     team_rating_pre_scaled, opp_rating_pre_scaled, expected_margin_pre_scaled]
    Opponent identity at each step is carried separately as sequence ids.
    """
    seq_dim = 11
    n = len(df)
    home_seq = np.zeros((n, seq_len, seq_dim), dtype=np.float32)
    away_seq = np.zeros((n, seq_len, seq_dim), dtype=np.float32)
    home_opp_raw = np.full((n, seq_len), -1, dtype=np.int64)
    away_opp_raw = np.full((n, seq_len), -1, dtype=np.int64)
    home_id = np.zeros(n, dtype=np.int64)
    away_id = np.zeros(n, dtype=np.int64)
    league_id_arr = np.zeros(n, dtype=np.int64)
    y = np.zeros((n, 3), dtype=np.float32)  # winner, home_score, away_score

    histories: Dict[int, Deque[Tuple[np.ndarray, int]]] = defaultdict(lambda: deque(maxlen=seq_len))
    all_team_ids: set[int] = set()
    all_league_ids: set[int] = set()
    team_last_date: Dict[int, datetime] = {}
    team_rating: Dict[int, float] = defaultdict(float)
    team_margin_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))

    for i, r in df.iterrows():
        h = _team_key(r["home_team_id"])
        a = _team_key(r["away_team_id"])
        lid = int(r["league_id"])
        hs = float(r["home_score"])
        aw = float(r["away_score"])
        dt = pd.to_datetime(r["date_event"], errors="coerce")
        if pd.isna(dt):
            dt = pd.Timestamp("1970-01-01")
        all_team_ids.add(h)
        all_team_ids.add(a)
        all_league_ids.add(lid)

        h_hist = list(histories[h])
        a_hist = list(histories[a])
        if h_hist:
            home_seq[i, -len(h_hist) :, :] = np.stack([x[0] for x in h_hist], axis=0)
            home_opp_raw[i, -len(h_hist) :] = np.array([x[1] for x in h_hist], dtype=np.int64)
        if a_hist:
            away_seq[i, -len(a_hist) :, :] = np.stack([x[0] for x in a_hist], axis=0)
            away_opp_raw[i, -len(a_hist) :] = np.array([x[1] for x in a_hist], dtype=np.int64)

        home_id[i] = h
        away_id[i] = a
        league_id_arr[i] = lid
        y[i, 0] = 1.0 if hs > aw else 0.0
        y[i, 1] = hs
        y[i, 2] = aw

        # Update history after consuming this row (chronology-safe).
        mu_l, sd_l = (league_stats.get(lid, (20.0, 8.0)) if league_stats else (20.0, 8.0))
        env = (league_env_stats.get(lid) if league_env_stats else None) or {}
        home_strength = float(env.get("home_strength", 1.0))
        rating_home_adv_l = float(env.get("rating_home_adv", rating_home_adv))
        d_h = float((dt.to_pydatetime() - team_last_date[h]).days) if h in team_last_date else 7.0
        d_a = float((dt.to_pydatetime() - team_last_date[a]).days) if a in team_last_date else 7.0
        rest_h = max(0.0, min(d_h, 42.0)) / 14.0
        rest_a = max(0.0, min(d_a, 42.0)) / 14.0
        vol5_h = _rolling_std(team_margin_hist[h], 5) / max(1.0, sd_l)
        vol10_h = _rolling_std(team_margin_hist[h], 10) / max(1.0, sd_l)
        vol5_a = _rolling_std(team_margin_hist[a], 5) / max(1.0, sd_l)
        vol10_a = _rolling_std(team_margin_hist[a], 10) / max(1.0, sd_l)
        hs_s = (hs - mu_l) / sd_l
        aw_s = (aw - mu_l) / sd_l
        m_h_s = (hs - aw) / sd_l
        m_a_s = (aw - hs) / sd_l
        rating_h_pre = float(team_rating.get(h, 0.0))
        rating_a_pre = float(team_rating.get(a, 0.0))
        exp_margin_h = (rating_h_pre - rating_a_pre + rating_home_adv_l) / max(1.0, rating_scale)
        exp_margin_a = -exp_margin_h
        histories[h].append(
            (
                _make_sequence_features(
                    points_for_scaled=hs_s,
                    points_against_scaled=aw_s,
                    margin_scaled=m_h_s,
                    is_home=1.0,
                    venue_adv_context=home_strength,
                    rest_days_norm=rest_h,
                    margin_vol5_norm=vol5_h,
                    margin_vol10_norm=vol10_h,
                    team_rating_pre=rating_h_pre,
                    opp_rating_pre=rating_a_pre,
                    expected_margin_pre=exp_margin_h,
                    score_sd=sd_l,
                ),
                a,
            )
        )
        histories[a].append(
            (
                _make_sequence_features(
                    points_for_scaled=aw_s,
                    points_against_scaled=hs_s,
                    margin_scaled=m_a_s,
                    is_home=0.0,
                    venue_adv_context=-home_strength,
                    rest_days_norm=rest_a,
                    margin_vol5_norm=vol5_a,
                    margin_vol10_norm=vol10_a,
                    team_rating_pre=rating_a_pre,
                    opp_rating_pre=rating_h_pre,
                    expected_margin_pre=exp_margin_a,
                    score_sd=sd_l,
                ),
                h,
            )
        )
        team_margin_hist[h].append(hs - aw)
        team_margin_hist[a].append(aw - hs)
        # ELO-like margin rating update.
        exp_h = (team_rating.get(h, 0.0) - team_rating.get(a, 0.0) + rating_home_adv_l) / max(1.0, rating_scale)
        err = (hs - aw) - exp_h
        team_rating[h] = team_rating.get(h, 0.0) + (rating_k * err)
        team_rating[a] = team_rating.get(a, 0.0) - (rating_k * err)
        team_last_date[h] = dt.to_pydatetime()
        team_last_date[a] = dt.to_pydatetime()

    # Remap sparse/negative team ids into compact embedding ids.
    if team_to_idx is None:
        team_list = sorted(all_team_ids)
        team_to_idx = {tid: i for i, tid in enumerate(team_list)}
    if league_to_idx is None:
        league_to_idx = {lid2: i for i, lid2 in enumerate(sorted(all_league_ids))}
    home_idx = np.array([team_to_idx[int(t)] for t in home_id], dtype=np.int64)
    away_idx = np.array([team_to_idx[int(t)] for t in away_id], dtype=np.int64)
    league_idx = np.array([league_to_idx[int(l)] for l in league_id_arr], dtype=np.int64)
    home_flat = home_opp_raw.reshape(-1)
    away_flat = away_opp_raw.reshape(-1)
    home_opp_idx = np.array(
        [team_to_idx.get(int(x), 0) if int(x) >= 0 else 0 for x in home_flat],
        dtype=np.int64,
    ).reshape(home_opp_raw.shape)
    away_opp_idx = np.array(
        [team_to_idx.get(int(x), 0) if int(x) >= 0 else 0 for x in away_flat],
        dtype=np.int64,
    ).reshape(away_opp_raw.shape)
    return home_seq, away_seq, home_idx, away_idx, home_opp_idx, away_opp_idx, league_idx, y, league_id_arr, team_to_idx, league_to_idx


def normalize_sequences(
    home_seq: np.ndarray,
    away_seq: np.ndarray,
    train_rows: int,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    # Fit normalization on train windows only (chronology-safe).
    x_train = np.concatenate([home_seq[:train_rows], away_seq[:train_rows]], axis=0)
    mean = np.mean(x_train.reshape(-1, x_train.shape[-1]), axis=0)
    std = np.std(x_train.reshape(-1, x_train.shape[-1]), axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    h = (home_seq - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
    a = (away_seq - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
    stats = {"mean": mean.tolist(), "std": std.tolist(), "seq_dim": int(home_seq.shape[-1])}
    return h.astype(np.float32), a.astype(np.float32), stats


class V4Model(nn.Module):
    def __init__(self, n_teams: int, n_leagues: int, emb_dim: int, seq_dim: int, hidden_dim: int):
        super().__init__()
        self.team_emb = nn.Embedding(n_teams, emb_dim)
        self.league_home_bias = nn.Embedding(n_leagues, 1)
        self.regime_emb = nn.Embedding(4, 8)
        self.regime_var_bias = nn.Embedding(4, 1)
        self.opp_proj = nn.Linear(emb_dim, 8)
        self.rnn = nn.GRU(input_size=seq_dim + 8, hidden_size=hidden_dim, batch_first=True)
        self.time_attn = nn.Linear(hidden_dim, 1)
        inter_in = (emb_dim + hidden_dim) * 2 + 2 + 8
        self.inter_mlp = nn.Sequential(
            nn.Linear(inter_in, 128),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(128, 64),
            nn.ReLU(),
        )
        self.winner_head = nn.Linear(64, 1)
        self.score_head = nn.Linear(64, 2)   # mu_home, mu_away
        self.var_head = nn.Linear(64, 2)     # log_var_home, log_var_away
        self.cov_head = nn.Linear(64, 1)     # correlation logit
        self.alpha_head = nn.Linear(64, 1)   # learned blending alpha

    def encode_team(self, team_idx: torch.Tensor, seq_x: torch.Tensor, opp_idx_seq: torch.Tensor) -> torch.Tensor:
        emb = self.team_emb(team_idx)
        opp_emb = self.team_emb(opp_idx_seq)
        opp_ctx = self.opp_proj(opp_emb)
        rnn_in = torch.cat([seq_x, opp_ctx], dim=2)
        out, h = self.rnn(rnn_in)
        # Attention pooling over sequence (falls back to final state for empty history rows).
        attn_logits = self.time_attn(out).squeeze(-1)
        valid = (torch.abs(seq_x).sum(dim=2) > 1e-8)
        attn_logits = attn_logits.masked_fill(~valid, -1e9)
        attn_w = torch.softmax(attn_logits, dim=1)
        ctx = torch.bmm(attn_w.unsqueeze(1), out).squeeze(1)
        has_hist = valid.any(dim=1).unsqueeze(1)
        team_state = torch.where(has_hist, ctx, h[-1])
        return torch.cat([emb, team_state], dim=1)

    def forward(
        self,
        home_idx: torch.Tensor,
        away_idx: torch.Tensor,
        league_idx: torch.Tensor,
        regime_idx: torch.Tensor,
        home_seq: torch.Tensor,
        away_seq: torch.Tensor,
        home_opp_idx: torch.Tensor,
        away_opp_idx: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        h_repr = self.encode_team(home_idx, home_seq, home_opp_idx)
        a_repr = self.encode_team(away_idx, away_seq, away_opp_idx)
        gap = (h_repr - a_repr).norm(dim=1, keepdim=True)
        dot = (h_repr * a_repr).sum(dim=1, keepdim=True)
        reg = self.regime_emb(regime_idx)
        x = torch.cat([h_repr, a_repr, gap, dot, reg], dim=1)
        z = self.inter_mlp(x)
        home_bias = self.league_home_bias(league_idx).squeeze(1)
        reg_var_bias = self.regime_var_bias(regime_idx).squeeze(1)
        score_mu = self.score_head(z)
        score_mu = torch.stack([score_mu[:, 0] + home_bias, score_mu[:, 1]], dim=1)
        score_logvar = self.var_head(z) + reg_var_bias.unsqueeze(1)
        return {
            "winner_logit": self.winner_head(z).squeeze(1) + home_bias,
            "score_mu": score_mu,
            "score_logvar": score_logvar,
            "score_rho_logit": self.cov_head(z).squeeze(1),
            "alpha_logit": self.alpha_head(z).squeeze(1),
        }


def _prob_brier(y_w: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.clip(p, 1e-6, 1.0 - 1e-6) - y_w.astype(float)) ** 2))


def _shrink_probabilities(p: np.ndarray, shrink_lambda: float) -> np.ndarray:
    lam = float(np.clip(shrink_lambda, 0.0, 0.5))
    return np.clip(0.5 + ((np.clip(p, 1e-6, 1.0 - 1e-6) - 0.5) * (1.0 - lam)), 1e-6, 1.0 - 1e-6)


def _prob_quality_score(y_w: np.ndarray, p: np.ndarray) -> float:
    p2 = np.clip(p, 1e-6, 1.0 - 1e-6)
    brier = _prob_brier(y_w, p2)
    ece = _ece_binary(y_w.astype(int), p2, bins=10)
    balance = float(abs(np.mean(y_w.astype(float)) - np.mean(p2)))
    return float(brier + (0.35 * ece) + (0.15 * balance))


def _build_calibration_features(
    p_raw: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
) -> np.ndarray:
    p2 = np.clip(p_raw.astype(float), 1e-6, 1.0 - 1e-6)
    prob_std_arr = np.array(prob_std if prob_std is not None else np.zeros_like(p2), dtype=np.float32)
    margin_var_arr = np.array(margin_var if margin_var is not None else np.zeros_like(p2), dtype=np.float32)
    logit = _logit_features(p2)
    log_margin_var = np.log(np.clip(margin_var_arr, 1e-6, None))
    return np.column_stack(
        [
            logit,
            prob_std_arr,
            log_margin_var,
            np.abs(logit) * prob_std_arr,
            prob_std_arr * np.tanh(log_margin_var / 5.0),
        ]
    ).astype(np.float32)


def _chronology_validation_split(
    n_rows: int,
    min_fit_rows: int,
    min_val_rows: int,
    val_ratio: float = 0.2,
) -> Optional[int]:
    if n_rows < (min_fit_rows + min_val_rows):
        return None
    val_rows = max(min_val_rows, int(round(n_rows * val_ratio)))
    val_rows = min(val_rows, n_rows - min_fit_rows)
    if val_rows < min_val_rows:
        return None
    return int(n_rows - val_rows)


def _fit_calibrator_method(
    method: str,
    p_raw: np.ndarray,
    y_w: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    p2 = np.clip(p_raw.astype(float), 1e-6, 1.0 - 1e-6)
    y = y_w.astype(int)
    if len(np.unique(y)) < 2:
        return {"method": "constant", "p": float(np.mean(y))}
    method_l = str(method).lower()
    if method_l == "identity":
        return {"method": "identity"}
    if method_l == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(p2, y)
        return {"method": "isotonic", "model": iso}
    if method_l == "beta":
        lr = LogisticRegression(max_iter=2000, solver="lbfgs")
        x = np.column_stack([np.log(p2), np.log(1.0 - p2)])
        lr.fit(x, y)
        return {"method": "beta", "model": lr}
    if method_l == "context_platt":
        x = _build_calibration_features(p2, prob_std, margin_var)
        mean = np.mean(x, axis=0)
        std = np.std(x, axis=0)
        std = np.where(std < 1e-6, 1.0, std)
        xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
        lr = LogisticRegression(C=0.50, max_iter=2000, solver="lbfgs")
        lr.fit(xs, y)
        return {
            "method": "context_platt",
            "model": lr,
            "feature_mean": mean.tolist(),
            "feature_std": std.tolist(),
        }
    lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    lr.fit(np.log(p2 / (1.0 - p2)).reshape(-1, 1), y)
    return {"method": "platt", "model": lr}


def fit_calibrator(
    p_raw: np.ndarray,
    y_w: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
    allow_context_platt: bool = True,
    allow_isotonic: bool = True,
    max_shrink_lambda: float = HIGH_SAMPLE_SHRINK_MAX,
) -> Dict[str, Any]:
    p2 = np.clip(p_raw.astype(float), 1e-6, 1.0 - 1e-6)
    y = y_w.astype(int)
    if len(np.unique(y)) < 2:
        return {"method": "constant", "p": float(np.mean(y))}

    split_idx = _chronology_validation_split(len(y), min_fit_rows=60, min_val_rows=40, val_ratio=0.2)
    if split_idx is not None:
        p_fit, p_val = p2[:split_idx], p2[split_idx:]
        y_fit, y_val = y[:split_idx], y[split_idx:]
        ps_fit = (prob_std[:split_idx] if prob_std is not None else None)
        ps_val = (prob_std[split_idx:] if prob_std is not None else None)
        mv_fit = (margin_var[:split_idx] if margin_var is not None else None)
        mv_val = (margin_var[split_idx:] if margin_var is not None else None)
        candidates = ["identity", "platt", "beta"]
        if allow_context_platt and prob_std is not None and margin_var is not None and len(y_fit) >= 120:
            candidates.append("context_platt")
        if allow_isotonic and len(y_fit) >= 120:
            candidates.append("isotonic")
        best_method = "identity"
        best_shrink = 0.0
        best_score = (float("inf"), float("inf"), float("inf"))
        shrink_cap = float(np.clip(max_shrink_lambda, 0.0, 0.5))
        shrink_grid = np.array([0.0], dtype=float) if shrink_cap <= 1e-9 else np.linspace(0.0, shrink_cap, 8)
        for method in candidates:
            candidate = _fit_calibrator_method(method, p_fit, y_fit, ps_fit, mv_fit)
            for shrink in shrink_grid:
                trial = dict(candidate)
                trial["shrink_lambda"] = float(shrink)
                p_candidate = apply_calibrator(trial, p_val, ps_val, mv_val)
                score = (
                    _prob_quality_score(y_val, p_candidate),
                    _prob_brier(y_val, p_candidate),
                    _ece_binary(y_val, p_candidate, bins=10),
                )
                if score < best_score:
                    best_score = score
                    best_method = method
                    best_shrink = float(shrink)
        out = _fit_calibrator_method(best_method, p2, y, prob_std, margin_var)
        if best_shrink > 1e-9:
            out["shrink_lambda"] = float(best_shrink)
        return out

    if allow_isotonic and len(y) >= 120:
        return _fit_calibrator_method("isotonic", p2, y, prob_std, margin_var)
    return _fit_calibrator_method("platt", p2, y, prob_std, margin_var)


def apply_calibrator(
    cal: Dict[str, Any],
    p_raw: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
) -> np.ndarray:
    p = np.clip(p_raw, 1e-6, 1.0 - 1e-6)
    if cal["method"] == "constant":
        out = np.full(len(p), float(np.clip(cal["p"], 1e-6, 1.0 - 1e-6)), dtype=float)
        return _shrink_probabilities(out, float(cal.get("shrink_lambda", 0.0)))
    if cal["method"] == "identity":
        return _shrink_probabilities(p, float(cal.get("shrink_lambda", 0.0)))
    if cal["method"] == "isotonic":
        out = np.clip(cal["model"].predict(p), 1e-6, 1.0 - 1e-6)
        return _shrink_probabilities(out, float(cal.get("shrink_lambda", 0.0)))
    if cal["method"] == "beta":
        x = np.column_stack([np.log(p), np.log(1.0 - p)])
        out = np.clip(cal["model"].predict_proba(x)[:, 1], 1e-6, 1.0 - 1e-6)
        return _shrink_probabilities(out, float(cal.get("shrink_lambda", 0.0)))
    if cal["method"] == "context_platt":
        x = _build_calibration_features(p, prob_std, margin_var)
        mean = np.array(cal.get("feature_mean") or [0.0] * x.shape[1], dtype=np.float32)
        std = np.array(cal.get("feature_std") or [1.0] * x.shape[1], dtype=np.float32)
        std = np.where(std < 1e-6, 1.0, std)
        xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
        out = np.clip(cal["model"].predict_proba(xs)[:, 1], 1e-6, 1.0 - 1e-6)
        return _shrink_probabilities(out, float(cal.get("shrink_lambda", 0.0)))
    x = np.log(p / (1.0 - p)).reshape(-1, 1)
    out = np.clip(cal["model"].predict_proba(x)[:, 1], 1e-6, 1.0 - 1e-6)
    return _shrink_probabilities(out, float(cal.get("shrink_lambda", 0.0)))


def _logit_features(p: np.ndarray) -> np.ndarray:
    p2 = np.clip(p.astype(float), 1e-6, 1.0 - 1e-6)
    return np.log(p2 / (1.0 - p2))


def _build_blend_features(p_cls: np.ndarray, p_sd: np.ndarray) -> np.ndarray:
    cls_logit = _logit_features(p_cls)
    sd_logit = _logit_features(p_sd)
    return np.column_stack(
        [
            cls_logit,
            sd_logit,
            cls_logit - sd_logit,
            np.abs(cls_logit - sd_logit),
        ]
    ).astype(np.float32)


def _fit_alpha_grid_blender(p_cls: np.ndarray, p_sd: np.ndarray, y_w: np.ndarray) -> Dict[str, Any]:
    best_alpha = 0.5
    best_brier = float("inf")
    for alpha in np.linspace(0.0, 1.0, 41):
        p = np.clip((alpha * p_cls) + ((1.0 - alpha) * p_sd), 1e-6, 1.0 - 1e-6)
        brier = float(np.mean((p - y_w) ** 2))
        if brier < best_brier:
            best_brier = brier
            best_alpha = float(alpha)
    return {
        "method": "alpha_grid",
        "alpha": float(best_alpha),
        "train_brier": float(best_brier),
    }


def _fit_logistic_meta_blender(p_cls: np.ndarray, p_sd: np.ndarray, y_w: np.ndarray) -> Dict[str, Any]:
    x = _build_blend_features(p_cls, p_sd)
    mean = np.mean(x, axis=0)
    std = np.std(x, axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
    lr = LogisticRegression(C=0.35, max_iter=2000, solver="lbfgs")
    lr.fit(xs, y_w.astype(int))
    p_meta = np.clip(lr.predict_proba(xs)[:, 1], 1e-6, 1.0 - 1e-6)
    return {
        "method": "logistic_meta",
        "model": lr,
        "feature_mean": mean.tolist(),
        "feature_std": std.tolist(),
        "train_brier": _prob_brier(y_w.astype(int), p_meta),
    }


def fit_probability_blender(p_cls: np.ndarray, p_sd: np.ndarray, y_w: np.ndarray) -> Dict[str, Any]:
    p_cls = np.clip(p_cls.astype(float), 1e-6, 1.0 - 1e-6)
    p_sd = np.clip(p_sd.astype(float), 1e-6, 1.0 - 1e-6)
    y = y_w.astype(int)
    if len(np.unique(y)) < 2:
        return {"method": "constant", "p": float(np.mean(y))}

    split_idx = _chronology_validation_split(len(y), min_fit_rows=80, min_val_rows=40, val_ratio=0.2)
    if split_idx is not None:
        p_cls_fit, p_cls_val = p_cls[:split_idx], p_cls[split_idx:]
        p_sd_fit, p_sd_val = p_sd[:split_idx], p_sd[split_idx:]
        y_fit, y_val = y[:split_idx], y[split_idx:]

        alpha_fit = _fit_alpha_grid_blender(p_cls_fit, p_sd_fit, y_fit)
        alpha_val = apply_probability_blender(alpha_fit, p_cls_val, p_sd_val)
        best_method = "alpha_grid"
        best_score = (_prob_brier(y_val, alpha_val), _ece_binary(y_val, alpha_val, bins=10))

        if len(y_fit) >= 220:
            meta_fit = _fit_logistic_meta_blender(p_cls_fit, p_sd_fit, y_fit)
            meta_val = apply_probability_blender(meta_fit, p_cls_val, p_sd_val)
            meta_score = (_prob_brier(y_val, meta_val), _ece_binary(y_val, meta_val, bins=10))
            if meta_score < best_score:
                best_method = "logistic_meta"

        if best_method == "logistic_meta":
            out = _fit_logistic_meta_blender(p_cls, p_sd, y)
            out["fallback_alpha"] = float(_fit_alpha_grid_blender(p_cls, p_sd, y)["alpha"])
            return out
        return _fit_alpha_grid_blender(p_cls, p_sd, y)

    return _fit_alpha_grid_blender(p_cls, p_sd, y)


def apply_probability_blender(blender: Dict[str, Any], p_cls: np.ndarray, p_sd: np.ndarray) -> np.ndarray:
    p_cls = np.clip(p_cls.astype(float), 1e-6, 1.0 - 1e-6)
    p_sd = np.clip(p_sd.astype(float), 1e-6, 1.0 - 1e-6)
    method = str(blender.get("method", "")).lower()
    if method == "constant":
        return np.full(len(p_cls), float(np.clip(blender.get("p", 0.5), 1e-6, 1.0 - 1e-6)), dtype=float)
    if method == "alpha_grid":
        alpha = float(blender.get("alpha", 0.5))
        return np.clip((alpha * p_cls) + ((1.0 - alpha) * p_sd), 1e-6, 1.0 - 1e-6)
    x = _build_blend_features(p_cls, p_sd)
    mean = np.array(blender.get("feature_mean") or [0.0] * x.shape[1], dtype=np.float32)
    std = np.array(blender.get("feature_std") or [1.0] * x.shape[1], dtype=np.float32)
    std = np.where(std < 1e-6, 1.0, std)
    xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
    return np.clip(blender["model"].predict_proba(xs)[:, 1], 1e-6, 1.0 - 1e-6)


def evaluate(p_home: np.ndarray, pred_h: np.ndarray, pred_a: np.ndarray, y_w: np.ndarray, y_h: np.ndarray, y_a: np.ndarray) -> Metrics:
    y_w_pred = (p_home >= 0.5).astype(int)
    mae_h = float(mean_absolute_error(y_h, pred_h))
    mae_a = float(mean_absolute_error(y_a, pred_a))
    return Metrics(
        winner_accuracy=float(accuracy_score(y_w, y_w_pred)),
        home_mae=mae_h,
        away_mae=mae_a,
        overall_mae=(mae_h + mae_a) / 2.0,
        brier_winner=float(np.mean((p_home - y_w) ** 2)),
        ece_winner=_ece_binary(y_w, p_home, bins=10),
        rows=len(y_w),
    )


def main() -> None:
    if torch is None:
        raise SystemExit(f"PyTorch is required for V4. Install with: pip install torch\nOriginal import error: {_TORCH_IMPORT_ERROR}")

    parser = argparse.ArgumentParser(description="MAZ Boss MAXED V4 (temporal + interaction intelligence).")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--league-id", type=int, default=None)
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--min-games", type=int, default=120)
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument(
        "--train-all-completed",
        action="store_true",
        help="Train on all completed games per league (no holdout/test split).",
    )
    parser.add_argument("--wf-start-train", type=int, default=80)
    parser.add_argument("--wf-step", type=int, default=20)
    parser.add_argument("--seq-len", type=int, default=8)
    parser.add_argument("--emb-dim", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--rating-k", type=float, default=0.06)
    parser.add_argument("--rating-home-adv", type=float, default=2.0)
    parser.add_argument("--rating-scale", type=float, default=7.0)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--global-pretrain", action="store_true")
    parser.add_argument("--global-pretrain-epochs", type=int, default=20)
    parser.add_argument("--finetune-epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--finetune-lr", type=float, default=3e-4)
    parser.add_argument("--ensemble-seeds", type=str, default="42,1337,9001")
    parser.add_argument("--winner-loss-weight", type=float, default=1.0)
    parser.add_argument("--score-loss-weight", type=float, default=0.25)
    parser.add_argument("--ranking-loss-weight", type=float, default=0.10)
    parser.add_argument("--embedding-l2-weight", type=float, default=0.0005)
    parser.add_argument("--var-reg-weight", type=float, default=0.002)
    parser.add_argument("--confidence-variance-threshold", type=float, default=40.0)
    parser.add_argument("--recency-half-life-days", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-v4-models", action="store_true")
    parser.add_argument("--save-global-pretrained", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=None, help="Optional run log file path.")
    args = parser.parse_args()
    auto_log_file: Optional[str] = args.log_file
    if not auto_log_file:
        auto_log_file = f"artifacts/maz_maxed_v4_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _setup_logging(args.log_level, auto_log_file)
    LOG.info("Starting MAZ MAXED V4 run")
    LOG.info("Logging to: %s", auto_log_file)
    args._ensemble_seeds = _parse_int_list(args.ensemble_seeds)
    if not args._ensemble_seeds:
        args._ensemble_seeds = [int(args.seed)]

    if not args.league_id and not args.all_leagues:
        raise SystemExit("Use --league-id <id> or --all-leagues")
    if args.walk_forward and args.train_all_completed:
        raise SystemExit("Use either --walk-forward or --train-all-completed, not both.")

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    leagues = {args.league_id: LEAGUE_MAPPINGS.get(args.league_id, f"League {args.league_id}")} if args.league_id else LEAGUE_MAPPINGS
    conn = sqlite3.connect(str(db_path))
    df_all = load_all_df(conn, leagues.keys())
    conn.close()
    if df_all.empty:
        raise SystemExit("No completed games found for selected leagues.")

    keep_ids = [lid for lid in leagues.keys() if int((df_all["league_id"] == lid).sum()) >= args.min_games]
    # In full-train mode, include international friendlies if enough completed rows to train.
    if args.train_all_completed and args.all_leagues and FRIENDLIES_LEAGUE_ID in leagues and FRIENDLIES_LEAGUE_ID not in keep_ids:
        n_friendlies = int((df_all["league_id"] == FRIENDLIES_LEAGUE_ID).sum())
        if n_friendlies >= 60:
            keep_ids.append(FRIENDLIES_LEAGUE_ID)
            LOG.info(
                "[%s] included in full-train mode with %s completed rows (below --min-games=%s)",
                leagues[FRIENDLIES_LEAGUE_ID],
                n_friendlies,
                args.min_games,
            )
    if not keep_ids:
        raise SystemExit("No leagues meet --min-games threshold.")
    df_all = (
        df_all[df_all["league_id"].isin(keep_ids)]
        .copy()
        .sort_values(["date_event", "event_id"])
        .reset_index(drop=True)
    )
    global_team_to_idx = build_global_team_to_idx(df_all)
    global_league_to_idx = build_global_league_to_idx(keep_ids)

    pretrained_by_seed: Dict[int, Dict[str, torch.Tensor]] = {}
    if args.global_pretrain:
        pre_parts = []
        for lid in keep_ids:
            g_l = (
                df_all[df_all["league_id"] == lid]
                .copy()
                .sort_values(["date_event", "event_id"])
                .reset_index(drop=True)
            )
            n_l = len(g_l)
            split_l = int(round(n_l * (1.0 - args.holdout_ratio)))
            split_l = max(60, min(split_l, n_l - 10))
            pre_parts.append(g_l.iloc[:split_l].copy())
        df_pre = (
            pd.concat(pre_parts, axis=0)
            .sort_values(["date_event", "event_id"])
            .reset_index(drop=True)
        )
        if len(df_pre) >= 100:
            LOG.info(
                "[V4] Global pretraining start: rows=%s teams=%s epochs=%s seeds=%s",
                len(df_pre),
                len(global_team_to_idx),
                args.global_pretrain_epochs,
                len(args._ensemble_seeds),
            )
            for s in args._ensemble_seeds:
                league_stats_g = build_league_score_stats(df_pre)
                league_env_stats_g = build_league_environment_stats(df_pre, args.rating_home_adv)
                home_seq_g, away_seq_g, home_idx_g, away_idx_g, home_opp_g, away_opp_g, league_idx_g, y_g_raw, league_ids_g, _, _ = build_temporal_sequences(
                    df_pre,
                    seq_len=args.seq_len,
                    team_to_idx=global_team_to_idx,
                    league_to_idx=global_league_to_idx,
                    league_stats=league_stats_g,
                    league_env_stats=league_env_stats_g,
                    rating_k=args.rating_k,
                    rating_home_adv=args.rating_home_adv,
                    rating_scale=args.rating_scale,
                )
                n_train_g = len(df_pre)
                home_seq_g, away_seq_g, _ = normalize_sequences(home_seq_g, away_seq_g, n_train_g)
                y_g = scale_score_targets(y_g_raw, league_ids_g, league_stats_g)
                w_g = torch.tensor(
                    build_recency_weights(df_pre, args.recency_half_life_days),
                    dtype=torch.float32,
                )
                xh_g = torch.tensor(home_seq_g, dtype=torch.float32)
                xa_g = torch.tensor(away_seq_g, dtype=torch.float32)
                ih_g = torch.tensor(home_idx_g, dtype=torch.long)
                ia_g = torch.tensor(away_idx_g, dtype=torch.long)
                ioh_g = torch.tensor(home_opp_g, dtype=torch.long)
                ioa_g = torch.tensor(away_opp_g, dtype=torch.long)
                il_g = torch.tensor(league_idx_g, dtype=torch.long)
                reg_map_g = detect_regime_map_by_league(df_pre)
                regime_idx_g = np.array([reg_map_g.get(int(lid), ("balanced_competitive", 1, 1.0))[1] for lid in league_ids_g], dtype=np.int64)
                ir_g = torch.tensor(regime_idx_g, dtype=torch.long)
                y_g_t = torch.tensor(y_g, dtype=torch.float32)
                torch.manual_seed(int(s) + 7777)
                model_g = V4Model(
                    n_teams=len(global_team_to_idx),
                    n_leagues=len(global_league_to_idx),
                    emb_dim=args.emb_dim,
                    seq_dim=int(home_seq_g.shape[-1]),
                    hidden_dim=args.hidden_dim,
                )
                opt_g = torch.optim.AdamW(model_g.parameters(), lr=args.lr, weight_decay=1e-4)
                for _ in range(max(1, int(args.global_pretrain_epochs))):
                    model_g.train()
                    perm = torch.randperm(n_train_g)
                    for i in range(0, n_train_g, max(1, args.batch_size)):
                        idx = perm[i : i + args.batch_size]
                        out = model_g(ih_g[idx], ia_g[idx], il_g[idx], ir_g[idx], xh_g[idx], xa_g[idx], ioh_g[idx], ioa_g[idx])
                        y_w = y_g_t[idx, 0]
                        y_h = y_g_t[idx, 1]
                        y_a = y_g_t[idx, 2]
                        batch_w = w_g[idx]
                        loss_w = weighted_mean(
                            F.binary_cross_entropy_with_logits(out["winner_logit"], y_w, reduction="none"),
                            batch_w,
                        )
                        mu = out["score_mu"]
                        logvar = out["score_logvar"].clamp(-5.0, 4.0)
                        var = torch.exp(logvar)
                        rho = 0.95 * torch.tanh(out["score_rho_logit"])
                        zh = (y_h - mu[:, 0]) / torch.sqrt(var[:, 0] + 1e-6)
                        za = (y_a - mu[:, 1]) / torch.sqrt(var[:, 1] + 1e-6)
                        den = torch.clamp(1.0 - (rho * rho), min=1e-4)
                        nll = 0.5 * (
                            logvar[:, 0]
                            + logvar[:, 1]
                            + torch.log(den)
                            + ((zh * zh) + (za * za) - (2.0 * rho * zh * za)) / den
                        )
                        score_huber = F.huber_loss(
                            mu,
                            torch.stack([y_h, y_a], dim=1),
                            reduction="none",
                        ).mean(dim=1)
                        loss_s = ((1.0 - SCORE_HUBER_MIX) * weighted_mean(nll, batch_w)) + (
                            SCORE_HUBER_MIX * weighted_mean(score_huber, batch_w)
                        )
                        y_margin = y_h - y_a
                        pred_margin = mu[:, 0] - mu[:, 1]
                        m_non_draw = torch.abs(y_margin) > 1e-6
                        if torch.any(m_non_draw):
                            sign = torch.sign(y_margin[m_non_draw])
                            loss_rank = weighted_mean(
                                F.softplus(-(sign * pred_margin[m_non_draw])),
                                batch_w[m_non_draw],
                            )
                        else:
                            loss_rank = torch.tensor(0.0, dtype=loss_w.dtype, device=loss_w.device)
                        var_reg = torch.mean(out["score_logvar"].clamp(-5.0, 4.0) ** 2)
                        emb_reg = torch.mean(model_g.team_emb.weight**2)
                        loss = (
                            (args.winner_loss_weight * loss_w)
                            + (args.score_loss_weight * loss_s)
                            + (args.ranking_loss_weight * loss_rank)
                            + (args.var_reg_weight * var_reg)
                            + (args.embedding_l2_weight * emb_reg)
                        )
                        opt_g.zero_grad()
                        loss.backward()
                        torch.nn.utils.clip_grad_norm_(model_g.parameters(), 1.0)
                        opt_g.step()
                pretrained_by_seed[int(s)] = model_g.state_dict()
                if args.save_global_pretrained:
                    out_dir = Path("artifacts")
                    out_dir.mkdir(exist_ok=True)
                    gp = out_dir / f"global_pretrained_v4_seed_{int(s)}.pt"
                    torch.save(model_g.state_dict(), gp)
                LOG.info("[V4] Global pretraining done for seed=%s", int(s))

    report: Dict[str, Any] = {
        "version": V4_VERSION,
        "generated_at": datetime.now().isoformat(),
        "config": {
            "min_games": args.min_games,
            "holdout_ratio": args.holdout_ratio,
            "walk_forward": bool(args.walk_forward),
            "train_all_completed": bool(args.train_all_completed),
            "wf_start_train": args.wf_start_train,
            "wf_step": args.wf_step,
            "seq_len": args.seq_len,
            "emb_dim": args.emb_dim,
            "hidden_dim": args.hidden_dim,
            "rating_k": args.rating_k,
            "rating_home_adv": args.rating_home_adv,
            "rating_scale": args.rating_scale,
            "epochs": args.epochs,
            "global_pretrain": bool(args.global_pretrain),
            "global_pretrain_epochs": args.global_pretrain_epochs,
            "finetune_epochs": args.finetune_epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "finetune_lr": args.finetune_lr,
            "ensemble_seeds": args._ensemble_seeds,
            "winner_loss_weight": args.winner_loss_weight,
            "score_loss_weight": args.score_loss_weight,
            "score_huber_mix": SCORE_HUBER_MIX,
            "ranking_loss_weight": args.ranking_loss_weight,
            "embedding_l2_weight": args.embedding_l2_weight,
            "var_reg_weight": args.var_reg_weight,
            "confidence_variance_threshold": args.confidence_variance_threshold,
            "recency_half_life_days": args.recency_half_life_days,
            "save_v4_models": bool(args.save_v4_models),
            "save_global_pretrained": bool(args.save_global_pretrained),
            "log_level": args.log_level,
            "log_file": auto_log_file,
            "global_team_index_size": len(global_team_to_idx),
            "global_league_index_size": len(global_league_to_idx),
            "sequence_feature_names": [
                "points_for_scaled",
                "points_against_scaled",
                "margin_scaled",
                "is_home",
                "venue_adv_context",
                "rest_days_norm",
                "margin_vol5_norm",
                "margin_vol10_norm",
                "team_rating_pre_scaled",
                "opp_rating_pre_scaled",
                "expected_margin_pre_scaled",
            ],
            "sequence_context_ids": ["opponent_team_id_sequence"],
        },
        "leagues": {},
        "summary": {"tested": 0, "skipped": 0},
    }

    def _run_split(
        lid: int,
        name: str,
        tr_df: pd.DataFrame,
        te_df: pd.DataFrame,
        save_models: bool,
        train_all_mode: bool = False,
    ) -> Dict[str, Any]:
        if len(tr_df) < 60 or (len(te_df) < 1 and not train_all_mode):
            return {"ok": False, "reason": "insufficient split rows"}
        league_stats = build_league_score_stats(tr_df)
        league_env_stats = build_league_environment_stats(tr_df, args.rating_home_adv)
        home_seq, away_seq, home_idx, away_idx, home_opp_idx, away_opp_idx, league_idx, y_raw, league_ids_row, team_to_idx, _ = build_temporal_sequences(
            pd.concat([tr_df, te_df], axis=0).reset_index(drop=True),
            seq_len=args.seq_len,
            team_to_idx=global_team_to_idx,
            league_to_idx=global_league_to_idx,
            league_stats=league_stats,
            league_env_stats=league_env_stats,
            rating_k=args.rating_k,
            rating_home_adv=args.rating_home_adv,
            rating_scale=args.rating_scale,
        )
        n_train = len(tr_df)
        home_seq, away_seq, norm_stats = normalize_sequences(home_seq, away_seq, n_train)
        y_scaled = scale_score_targets(y_raw, league_ids_row, league_stats)
        w_tr = torch.tensor(
            build_recency_weights(tr_df, args.recency_half_life_days),
            dtype=torch.float32,
        )
        seq_dim = int(home_seq.shape[-1])
        xh_tr = torch.tensor(home_seq[:n_train], dtype=torch.float32)
        xa_tr = torch.tensor(away_seq[:n_train], dtype=torch.float32)
        ih_tr = torch.tensor(home_idx[:n_train], dtype=torch.long)
        ia_tr = torch.tensor(away_idx[:n_train], dtype=torch.long)
        ioh_tr = torch.tensor(home_opp_idx[:n_train], dtype=torch.long)
        ioa_tr = torch.tensor(away_opp_idx[:n_train], dtype=torch.long)
        il_tr = torch.tensor(league_idx[:n_train], dtype=torch.long)
        regime_name, regime_idx, regime_unc_mult = detect_regime(tr_df)
        allow_context_platt = bool(
            len(tr_df) >= CONTEXT_PLATT_MIN_ROWS
            and regime_name in {"stable_dominant", "balanced_competitive"}
        )
        allow_isotonic = bool(
            len(tr_df) >= ISOTONIC_MIN_ROWS
            or (
                len(tr_df) >= MEDIUM_SAMPLE_ROWS
                and regime_name in {"stable_dominant", "balanced_competitive"}
            )
        )
        calibrator_shrink_max = float(
            LOW_SAMPLE_SHRINK_MAX if len(tr_df) < SMALL_SAMPLE_ROWS else HIGH_SAMPLE_SHRINK_MAX
        )
        ir_tr = torch.full((n_train,), int(regime_idx), dtype=torch.long)
        y_tr = torch.tensor(y_scaled[:n_train], dtype=torch.float32)
        xh_te = torch.tensor(home_seq[n_train:], dtype=torch.float32)
        xa_te = torch.tensor(away_seq[n_train:], dtype=torch.float32)
        ih_te = torch.tensor(home_idx[n_train:], dtype=torch.long)
        ia_te = torch.tensor(away_idx[n_train:], dtype=torch.long)
        ioh_te = torch.tensor(home_opp_idx[n_train:], dtype=torch.long)
        ioa_te = torch.tensor(away_opp_idx[n_train:], dtype=torch.long)
        il_te = torch.tensor(league_idx[n_train:], dtype=torch.long)
        ir_te = torch.full((len(te_df),), int(regime_idx), dtype=torch.long)
        y_te_np = y_raw[n_train:]
        n_test = len(te_df)

        ens_p_cls_tr: List[np.ndarray] = []
        ens_p_cls_te: List[np.ndarray] = []
        ens_p_sd_tr: List[np.ndarray] = []
        ens_p_sd_te: List[np.ndarray] = []
        ens_proxy_prob_tr: List[np.ndarray] = []
        ens_proxy_prob_te: List[np.ndarray] = []
        ens_mu_tr: List[np.ndarray] = []
        ens_mu_te: List[np.ndarray] = []
        ens_var_tr: List[np.ndarray] = []
        ens_var_te: List[np.ndarray] = []
        ens_margin_var_tr: List[np.ndarray] = []
        ens_margin_var_te: List[np.ndarray] = []
        ens_alpha_tr: List[np.ndarray] = []
        ens_alpha_te: List[np.ndarray] = []
        emb_norm_means: List[float] = []
        emb_norm_stds: List[float] = []
        saved_seed_models: List[str] = []

        for s in args._ensemble_seeds:
            torch.manual_seed(int(s) + int(lid))
            model = V4Model(
                n_teams=len(global_team_to_idx),
                n_leagues=len(global_league_to_idx),
                emb_dim=args.emb_dim,
                seq_dim=seq_dim,
                hidden_dim=args.hidden_dim,
            )
            if int(s) in pretrained_by_seed:
                model.load_state_dict(pretrained_by_seed[int(s)], strict=True)
            use_lr = float(args.finetune_lr if args.global_pretrain else args.lr)
            use_epochs = int(args.finetune_epochs if args.global_pretrain else args.epochs)
            if args.global_pretrain:
                if len(tr_df) < SMALL_SAMPLE_ROWS:
                    use_lr *= 0.75
                    use_epochs = max(4, min(use_epochs, 6))
                elif len(tr_df) < MEDIUM_SAMPLE_ROWS:
                    use_lr *= 0.90
                    use_epochs = max(6, min(use_epochs, 9))
            opt = torch.optim.AdamW(model.parameters(), lr=use_lr, weight_decay=1e-4)

            for _ in range(max(1, use_epochs)):
                model.train()
                perm = torch.randperm(n_train)
                for i in range(0, n_train, max(1, args.batch_size)):
                    idx = perm[i : i + args.batch_size]
                    out = model(
                        ih_tr[idx],
                        ia_tr[idx],
                        il_tr[idx],
                        ir_tr[idx],
                        xh_tr[idx],
                        xa_tr[idx],
                        ioh_tr[idx],
                        ioa_tr[idx],
                    )
                    y_w = y_tr[idx, 0]
                    y_h = y_tr[idx, 1]
                    y_a = y_tr[idx, 2]
                    batch_w = w_tr[idx]
                    loss_w = weighted_mean(
                        F.binary_cross_entropy_with_logits(out["winner_logit"], y_w, reduction="none"),
                        batch_w,
                    )
                    mu = out["score_mu"]
                    logvar = out["score_logvar"].clamp(-5.0, 4.0)
                    var = torch.exp(logvar)
                    rho = 0.95 * torch.tanh(out["score_rho_logit"])
                    zh = (y_h - mu[:, 0]) / torch.sqrt(var[:, 0] + 1e-6)
                    za = (y_a - mu[:, 1]) / torch.sqrt(var[:, 1] + 1e-6)
                    den = torch.clamp(1.0 - (rho * rho), min=1e-4)
                    nll = 0.5 * (
                        logvar[:, 0]
                        + logvar[:, 1]
                        + torch.log(den)
                        + ((zh * zh) + (za * za) - (2.0 * rho * zh * za)) / den
                    )
                    score_huber = F.huber_loss(
                        mu,
                        torch.stack([y_h, y_a], dim=1),
                        reduction="none",
                    ).mean(dim=1)
                    loss_s = ((1.0 - SCORE_HUBER_MIX) * weighted_mean(nll, batch_w)) + (
                        SCORE_HUBER_MIX * weighted_mean(score_huber, batch_w)
                    )
                    var_reg = torch.mean(out["score_logvar"].clamp(-5.0, 4.0) ** 2)
                    emb_reg = torch.mean(model.team_emb.weight**2)
                    y_margin = y_h - y_a
                    pred_margin = mu[:, 0] - mu[:, 1]
                    m_non_draw = torch.abs(y_margin) > 1e-6
                    if torch.any(m_non_draw):
                        sign = torch.sign(y_margin[m_non_draw])
                        loss_rank = weighted_mean(
                            F.softplus(-(sign * pred_margin[m_non_draw])),
                            batch_w[m_non_draw],
                        )
                    else:
                        loss_rank = torch.tensor(0.0, dtype=loss_w.dtype, device=loss_w.device)
                    loss = (
                        (args.winner_loss_weight * loss_w)
                        + (args.score_loss_weight * loss_s)
                        + (args.ranking_loss_weight * loss_rank)
                        + (args.var_reg_weight * var_reg)
                        + (args.embedding_l2_weight * emb_reg)
                    )
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    opt.step()

            model.eval()
            with torch.no_grad():
                out_tr = model(ih_tr, ia_tr, il_tr, ir_tr, xh_tr, xa_tr, ioh_tr, ioa_tr)
                p_cls_tr = torch.sigmoid(out_tr["winner_logit"]).cpu().numpy()
                mu_tr = out_tr["score_mu"].cpu().numpy()
                var_tr = np.exp(out_tr["score_logvar"].clamp(-5.0, 4.0).cpu().numpy())
                rho_tr = 0.95 * np.tanh(out_tr["score_rho_logit"].cpu().numpy())
                a_tr = torch.sigmoid(out_tr["alpha_logit"]).cpu().numpy()
                emb_weights = model.team_emb.weight.detach().cpu().numpy()
                if n_test > 0:
                    out_te = model(ih_te, ia_te, il_te, ir_te, xh_te, xa_te, ioh_te, ioa_te)
                    p_cls_te = torch.sigmoid(out_te["winner_logit"]).cpu().numpy()
                    mu_te = out_te["score_mu"].cpu().numpy()
                    var_te = np.exp(out_te["score_logvar"].clamp(-5.0, 4.0).cpu().numpy())
                    rho_te = 0.95 * np.tanh(out_te["score_rho_logit"].cpu().numpy())
                    a_te = torch.sigmoid(out_te["alpha_logit"]).cpu().numpy()
                else:
                    p_cls_te = np.zeros((0,), dtype=float)
                    mu_te = np.zeros((0, 2), dtype=float)
                    var_te = np.zeros((0, 2), dtype=float)
                    rho_te = np.zeros((0,), dtype=float)
                    a_te = np.zeros((0,), dtype=float)

            mu_tr = unscale_score_predictions(mu_tr, league_ids_row[:n_train], league_stats)
            var_tr = unscale_score_variances(var_tr, league_ids_row[:n_train], league_stats)
            if n_test > 0:
                mu_te = unscale_score_predictions(mu_te, league_ids_row[n_train:], league_stats)
                var_te = unscale_score_variances(var_te, league_ids_row[n_train:], league_stats)
            md_tr = mu_tr[:, 0] - mu_tr[:, 1]
            vd_tr = np.maximum(
                1e-6,
                (var_tr[:, 0] + var_tr[:, 1] - (2.0 * rho_tr * np.sqrt(np.maximum(1e-6, var_tr[:, 0] * var_tr[:, 1]))))
                * float(regime_unc_mult),
            )
            p_sd_tr = _norm_cdf(md_tr / np.sqrt(vd_tr))
            if n_test > 0:
                md_te = mu_te[:, 0] - mu_te[:, 1]
                vd_te = np.maximum(
                    1e-6,
                    (var_te[:, 0] + var_te[:, 1] - (2.0 * rho_te * np.sqrt(np.maximum(1e-6, var_te[:, 0] * var_te[:, 1]))))
                    * float(regime_unc_mult),
                )
                p_sd_te = _norm_cdf(md_te / np.sqrt(vd_te))
            else:
                p_sd_te = np.zeros((0,), dtype=float)
            ens_p_cls_tr.append(p_cls_tr)
            ens_p_cls_te.append(p_cls_te)
            ens_p_sd_tr.append(p_sd_tr)
            ens_p_sd_te.append(p_sd_te)
            ens_proxy_prob_tr.append(np.clip(0.5 * (p_cls_tr + p_sd_tr), 1e-6, 1.0 - 1e-6))
            ens_proxy_prob_te.append(
                np.clip(0.5 * (p_cls_te + p_sd_te), 1e-6, 1.0 - 1e-6)
                if n_test > 0
                else np.zeros((0,), dtype=float)
            )
            ens_mu_tr.append(mu_tr)
            ens_mu_te.append(mu_te)
            ens_var_tr.append(var_tr)
            ens_var_te.append(var_te)
            ens_margin_var_tr.append(vd_tr)
            ens_margin_var_te.append(vd_te if n_test > 0 else np.zeros((0,), dtype=float))
            ens_alpha_tr.append(a_tr)
            ens_alpha_te.append(a_te)
            emb_norms = np.linalg.norm(emb_weights, axis=1)
            emb_norm_means.append(float(np.mean(emb_norms)))
            emb_norm_stds.append(float(np.std(emb_norms)))
            if save_models and args.save_v4_models:
                out_dir = Path("artifacts")
                out_dir.mkdir(exist_ok=True)
                model_file = out_dir / f"league_{lid}_model_maz_maxed_v4_seed_{int(s)}.pt"
                torch.save(model.state_dict(), model_file)
                saved_seed_models.append(str(model_file))

        p_cls_tr = np.mean(np.vstack(ens_p_cls_tr), axis=0)
        p_cls_te = np.mean(np.vstack(ens_p_cls_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        p_sd_tr = np.mean(np.vstack(ens_p_sd_tr), axis=0)
        p_sd_te = np.mean(np.vstack(ens_p_sd_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        proxy_prob_tr = np.mean(np.vstack(ens_proxy_prob_tr), axis=0)
        proxy_prob_te = (
            np.mean(np.vstack(ens_proxy_prob_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        )
        prob_std_tr = np.std(np.vstack(ens_proxy_prob_tr), axis=0) if len(ens_proxy_prob_tr) > 1 else np.zeros_like(proxy_prob_tr)
        prob_std_te = (
            np.std(np.vstack(ens_proxy_prob_te), axis=0)
            if (n_test > 0 and len(ens_proxy_prob_te) > 1)
            else np.zeros((0,), dtype=float)
        )
        mu_tr = np.mean(np.stack(ens_mu_tr, axis=0), axis=0)
        mu_te = np.mean(np.stack(ens_mu_te, axis=0), axis=0) if n_test > 0 else np.zeros((0, 2), dtype=float)
        var_tr = np.mean(np.stack(ens_var_tr, axis=0), axis=0)
        var_te = np.mean(np.stack(ens_var_te, axis=0), axis=0) if n_test > 0 else np.zeros((0, 2), dtype=float)
        margin_var_tr = np.mean(np.vstack(ens_margin_var_tr), axis=0)
        margin_var_te = (
            np.mean(np.vstack(ens_margin_var_te), axis=0)
            if (n_test > 0 and len(ens_margin_var_te) > 0)
            else np.zeros((0,), dtype=float)
        )
        a_tr = np.mean(np.vstack(ens_alpha_tr), axis=0)
        a_te = np.mean(np.vstack(ens_alpha_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        margin_var_threshold = _quantile_or_fallback(margin_var_tr, 0.85, args.confidence_variance_threshold)
        prob_std_threshold = _quantile_or_fallback(prob_std_tr, 0.85, DEFAULT_PROB_STD_THRESHOLD)
        probability_blender = fit_probability_blender(
            p_cls_tr,
            p_sd_tr,
            y_raw[:n_train, 0].astype(int),
        )
        p_blend_tr = apply_probability_blender(probability_blender, p_cls_tr, p_sd_tr)
        p_blend_te = (
            apply_probability_blender(probability_blender, p_cls_te, p_sd_te)
            if n_test > 0
            else np.zeros((0,), dtype=float)
        )
        cal = fit_calibrator(
            p_blend_tr,
            y_raw[:n_train, 0].astype(int),
            prob_std=prob_std_tr,
            margin_var=margin_var_tr,
            allow_context_platt=allow_context_platt,
            allow_isotonic=allow_isotonic,
            max_shrink_lambda=calibrator_shrink_max,
        )
        p_fin_tr = apply_calibrator(cal, p_blend_tr, prob_std_tr, margin_var_tr)
        p_fin_te = (
            apply_calibrator(cal, p_blend_te, prob_std_te, margin_var_te)
            if n_test > 0
            else np.zeros((0,), dtype=float)
        )
        m_train = evaluate(
            p_fin_tr,
            mu_tr[:, 0],
            mu_tr[:, 1],
            y_raw[:n_train, 0].astype(int),
            y_raw[:n_train, 1],
            y_raw[:n_train, 2],
        )
        if n_test > 0:
            m = evaluate(p_fin_te, mu_te[:, 0], mu_te[:, 1], y_te_np[:, 0].astype(int), y_te_np[:, 1], y_te_np[:, 2])
            low_conf_mask = (margin_var_te > margin_var_threshold) | (prob_std_te > prob_std_threshold)
            high_conf_mask = ~low_conf_mask
            hc_total = int(np.sum(high_conf_mask))
            hc_correct = int(np.sum((p_fin_te[high_conf_mask] >= 0.5).astype(int) == y_te_np[:, 0].astype(int)[high_conf_mask])) if hc_total > 0 else 0
        else:
            m = None
            low_conf_mask = np.zeros((0,), dtype=bool)
            hc_total = 0
            hc_correct = 0
        out: Dict[str, Any] = {
            "ok": True,
            "metrics": m,
            "trained_only": bool(n_test == 0),
            "train_metrics": m_train,
            "rows": int(len(te_df)),
            "train_rows": int(len(tr_df)),
            "test_rows": int(len(te_df)),
            "calibration_method": cal["method"],
            "calibrator": cal,
            "blend_method": str(probability_blender.get("method", "unknown")),
            "blend_alpha": (
                float(probability_blender["alpha"])
                if probability_blender.get("method") == "alpha_grid"
                else None
            ),
            "regime": regime_name,
            "regime_idx": int(regime_idx),
            "regime_uncertainty_multiplier": float(regime_unc_mult),
            "alpha_avg_train": float(np.mean(a_tr)),
            "alpha_avg_test": float(np.mean(a_te)) if len(a_te) else None,
            "variance_avg_train": float(np.mean(var_tr)),
            "variance_avg_test": float(np.mean(var_te)) if len(var_te) else None,
            "ensemble_prob_std_avg_train": float(np.mean(prob_std_tr)),
            "ensemble_prob_std_avg_test": float(np.mean(prob_std_te)) if len(prob_std_te) else None,
            "confidence_margin_variance_threshold": float(margin_var_threshold),
            "confidence_prob_std_threshold": float(prob_std_threshold),
            "embedding_norm_mean": float(np.mean(emb_norm_means)),
            "embedding_norm_std": float(np.mean(emb_norm_stds)),
            "low_confidence_rate": float(np.mean(low_conf_mask)) if len(low_conf_mask) else None,
            "high_confidence_total": hc_total,
            "high_confidence_correct": hc_correct,
            "saved_seed_models": saved_seed_models,
            "team_to_idx": team_to_idx,
            "league_stats": league_stats,
            "league_env_stats": league_env_stats,
            "normalization_stats": norm_stats,
        }
        if save_models and args.save_v4_models:
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            meta_file = out_dir / f"league_{lid}_model_maz_maxed_v4_meta.pkl"
            with meta_file.open("wb") as f:
                pickle.dump(
                    {
                        "version": V4_VERSION,
                        "league_id": int(lid),
                        "league_name": name,
                        "team_to_idx": team_to_idx,
                        "league_to_idx": global_league_to_idx,
                        "league_score_stats_train": {int(k): (float(v[0]), float(v[1])) for k, v in league_stats.items()},
                        "league_env_stats_train": {
                            int(k): {
                                "home_prob": float(v.get("home_prob", 0.55)),
                                "home_strength": float(v.get("home_strength", 1.0)),
                                "rating_home_adv": float(v.get("rating_home_adv", args.rating_home_adv)),
                            }
                            for k, v in league_env_stats.items()
                        },
                        "normalization_stats": norm_stats,
                        "config": {
                            "seq_len": int(args.seq_len),
                            "emb_dim": int(args.emb_dim),
                            "hidden_dim": int(args.hidden_dim),
                            "seq_dim": seq_dim,
                            "rating_k": float(args.rating_k),
                            "rating_home_adv": float(args.rating_home_adv),
                            "rating_scale": float(args.rating_scale),
                            "score_huber_mix": SCORE_HUBER_MIX,
                        },
                        "calibration_method": cal["method"],
                        "calibrator": cal,
                        "probability_blender": probability_blender,
                        "regime_name": regime_name,
                        "regime_idx": int(regime_idx),
                        "regime_uncertainty_multiplier": float(regime_unc_mult),
                        "confidence_margin_variance_threshold": float(margin_var_threshold),
                        "confidence_prob_std_threshold": float(prob_std_threshold),
                        "alpha_avg_test": float(np.mean(a_te)) if len(a_te) else None,
                        "ensemble_seeds": args._ensemble_seeds,
                        "saved_seed_models": saved_seed_models,
                    },
                    f,
                )
            out["saved_meta"] = str(meta_file)
        return out

    for lid in keep_ids:
        name = leagues[lid]
        g = (
            df_all[df_all["league_id"] == lid]
            .copy()
            .sort_values(["date_event", "event_id"])
            .reset_index(drop=True)
        )
        n = len(g)
        if args.train_all_completed:
            LOG.info("[%s] full-train mode: using all completed games (n=%s)", name, n)
            te_empty = g.iloc[0:0].copy()
            out = _run_split(lid, name, g, te_empty, save_models=True, train_all_mode=True)
            if not out.get("ok"):
                report["summary"]["skipped"] += 1
                report["leagues"][str(lid)] = {"name": name, "status": "skipped", "reason": str(out.get("reason", "train failed"))}
                LOG.warning("[%s] full-train skipped: %s", name, str(out.get("reason", "train failed")))
                continue
            report["summary"]["tested"] += 1
            payload = {
                "name": name,
                "status": "trained_only",
                "mode": "train_all_completed",
                "train_rows": int(out["train_rows"]),
                "test_rows": 0,
                "ensemble_size": int(len(args._ensemble_seeds)),
                "global_pretrained": bool(args.global_pretrain and len(pretrained_by_seed) > 0),
                "calibration_method": out.get("calibration_method"),
                "blend_method": out.get("blend_method"),
                "blend_alpha": out.get("blend_alpha"),
                "regime": out.get("regime"),
                "regime_idx": out.get("regime_idx"),
                "regime_uncertainty_multiplier": out.get("regime_uncertainty_multiplier"),
                "alpha_avg_train": out.get("alpha_avg_train"),
                "variance_avg_train": out.get("variance_avg_train"),
                "ensemble_prob_std_avg_train": out.get("ensemble_prob_std_avg_train"),
                "confidence_margin_variance_threshold": out.get("confidence_margin_variance_threshold"),
                "confidence_prob_std_threshold": out.get("confidence_prob_std_threshold"),
                "embedding_norm_mean": out.get("embedding_norm_mean"),
                "embedding_norm_std": out.get("embedding_norm_std"),
                "train_metrics": out["train_metrics"].__dict__ if out.get("train_metrics") is not None else None,
            }
            if args.save_v4_models and out.get("saved_seed_models"):
                payload["saved_seed_models"] = out["saved_seed_models"]
                payload["saved_meta"] = out.get("saved_meta")
            report["leagues"][str(lid)] = payload
            tm = out.get("train_metrics")
            if tm is not None:
                LOG.info(
                    "[%s] full-train complete | train_rows=%s train_win_acc=%.3f train_mae=%.3f",
                    name,
                    int(out["train_rows"]),
                    float(tm.winner_accuracy),
                    float(tm.overall_mae),
                )
            else:
                LOG.info("[%s] full-train complete | train_rows=%s", name, int(out["train_rows"]))
        elif args.walk_forward:
            start = max(60, int(args.wf_start_train))
            step = max(1, int(args.wf_step))
            if start >= n - 1:
                report["summary"]["skipped"] += 1
                report["leagues"][str(lid)] = {"name": name, "status": "skipped", "reason": f"not enough rows for walk-forward n={n}, start={start}"}
                continue
            total_chunks = len(range(start, n, step))
            LOG.info("[%s] walk-forward start: rows=%s, chunks=%s, step=%s", name, n, total_chunks, step)
            rows_total = 0
            win_sum = mae_h_sum = mae_a_sum = brier_sum = ece_sum = 0.0
            alpha_tr_sum = alpha_te_sum = var_tr_sum = var_te_sum = 0.0
            emb_mean_sum = emb_std_sum = low_conf_sum = 0.0
            hc_total = 0
            hc_correct = 0
            last_ok: Optional[Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]] = None
            for chunk_i, cut in enumerate(range(start, n, step), start=1):
                nxt = min(n, cut + step)
                tr = g.iloc[:cut].copy()
                te = g.iloc[cut:nxt].copy()
                out = _run_split(lid, name, tr, te, save_models=False)
                if not out.get("ok"):
                    LOG.warning(
                        "[%s] chunk %s/%s skipped: %s",
                        name,
                        chunk_i,
                        total_chunks,
                        out.get("reason", "split failed"),
                    )
                    continue
                m: Metrics = out["metrics"]
                r = int(m.rows)
                rows_total += r
                win_sum += m.winner_accuracy * r
                mae_h_sum += m.home_mae * r
                mae_a_sum += m.away_mae * r
                brier_sum += m.brier_winner * r
                ece_sum += m.ece_winner * r
                alpha_tr_sum += float(out["alpha_avg_train"]) * r
                alpha_te_sum += float(out["alpha_avg_test"]) * r
                var_tr_sum += float(out["variance_avg_train"]) * r
                var_te_sum += float(out["variance_avg_test"]) * r
                emb_mean_sum += float(out["embedding_norm_mean"]) * r
                emb_std_sum += float(out["embedding_norm_std"]) * r
                low_conf_sum += float(out["low_confidence_rate"]) * r
                hc_total += int(out["high_confidence_total"])
                hc_correct += int(out["high_confidence_correct"])
                last_ok = (tr, te, out)
                LOG.info("[%s] chunk %s/%s done | train=%s test=%s", name, chunk_i, total_chunks, len(tr), len(te))

            if rows_total < 10 or last_ok is None:
                report["summary"]["skipped"] += 1
                report["leagues"][str(lid)] = {"name": name, "status": "skipped", "reason": "walk-forward produced no valid chunks"}
                continue
            if args.save_v4_models:
                tr_last, te_last, _ = last_ok
                save_out = _run_split(lid, name, tr_last, te_last, save_models=True)
            else:
                save_out = {}
            m_agg = Metrics(
                winner_accuracy=win_sum / rows_total,
                home_mae=mae_h_sum / rows_total,
                away_mae=mae_a_sum / rows_total,
                overall_mae=((mae_h_sum / rows_total) + (mae_a_sum / rows_total)) / 2.0,
                brier_winner=brier_sum / rows_total,
                ece_winner=ece_sum / rows_total,
                rows=rows_total,
            )
            payload = {
                "name": name,
                "status": "tested",
                "mode": "walk_forward",
                "train_rows": int(start),
                "test_rows": int(rows_total),
                "ensemble_size": int(len(args._ensemble_seeds)),
                "global_pretrained": bool(args.global_pretrain and len(pretrained_by_seed) > 0),
                "calibration_method": str(last_ok[2]["calibration_method"]),
                "blend_method": str(last_ok[2]["blend_method"]),
                "blend_alpha": last_ok[2]["blend_alpha"],
                "regime": str(last_ok[2]["regime"]),
                "regime_idx": int(last_ok[2]["regime_idx"]),
                "regime_uncertainty_multiplier": float(last_ok[2]["regime_uncertainty_multiplier"]),
                "alpha_avg_train": alpha_tr_sum / rows_total,
                "alpha_avg_test": alpha_te_sum / rows_total,
                "variance_avg_train": var_tr_sum / rows_total,
                "variance_avg_test": var_te_sum / rows_total,
                "ensemble_prob_std_avg_train": float(last_ok[2]["ensemble_prob_std_avg_train"]),
                "ensemble_prob_std_avg_test": float(last_ok[2]["ensemble_prob_std_avg_test"]),
                "confidence_margin_variance_threshold": float(last_ok[2]["confidence_margin_variance_threshold"]),
                "confidence_prob_std_threshold": float(last_ok[2]["confidence_prob_std_threshold"]),
                "embedding_norm_mean": emb_mean_sum / rows_total,
                "embedding_norm_std": emb_std_sum / rows_total,
                "low_confidence_rate": low_conf_sum / rows_total,
                "high_confidence_win_accuracy": (float(hc_correct / hc_total) if hc_total > 0 else None),
                "metrics": m_agg.__dict__,
            }
            if args.save_v4_models and save_out.get("saved_seed_models"):
                payload["saved_seed_models"] = save_out["saved_seed_models"]
                payload["saved_meta"] = save_out.get("saved_meta")
            report["summary"]["tested"] += 1
            report["leagues"][str(lid)] = payload
            LOG.info(
                "[%s] win_acc=%.3f mae=%.3f brier=%.4f ece=%.4f alpha_test_avg=%.3f low_conf_rate=%.3f",
                name,
                m_agg.winner_accuracy,
                m_agg.overall_mae,
                m_agg.brier_winner,
                m_agg.ece_winner,
                float(payload["alpha_avg_test"]),
                float(payload["low_confidence_rate"]),
            )
        else:
            split = int(round(n * (1.0 - args.holdout_ratio)))
            split = max(60, min(split, n - 10))
            tr = g.iloc[:split].copy()
            te = g.iloc[split:].copy()
            out = _run_split(lid, name, tr, te, save_models=True)
            if not out.get("ok"):
                report["summary"]["skipped"] += 1
                report["leagues"][str(lid)] = {"name": name, "status": "skipped", "reason": str(out.get("reason", "split failed"))}
                continue
            m: Metrics = out["metrics"]
            report["summary"]["tested"] += 1
            payload = {
                "name": name,
                "status": "tested",
                "mode": "single_holdout",
                "train_rows": int(out["train_rows"]),
                "test_rows": int(out["test_rows"]),
                "ensemble_size": int(len(args._ensemble_seeds)),
                "global_pretrained": bool(args.global_pretrain and len(pretrained_by_seed) > 0),
                "calibration_method": out["calibration_method"],
                "blend_method": out["blend_method"],
                "blend_alpha": out["blend_alpha"],
                "regime": out["regime"],
                "regime_idx": out["regime_idx"],
                "regime_uncertainty_multiplier": out["regime_uncertainty_multiplier"],
                "alpha_avg_train": out["alpha_avg_train"],
                "alpha_avg_test": out["alpha_avg_test"],
                "variance_avg_train": out["variance_avg_train"],
                "variance_avg_test": out["variance_avg_test"],
                "ensemble_prob_std_avg_train": out["ensemble_prob_std_avg_train"],
                "ensemble_prob_std_avg_test": out["ensemble_prob_std_avg_test"],
                "confidence_margin_variance_threshold": out["confidence_margin_variance_threshold"],
                "confidence_prob_std_threshold": out["confidence_prob_std_threshold"],
                "embedding_norm_mean": out["embedding_norm_mean"],
                "embedding_norm_std": out["embedding_norm_std"],
                "low_confidence_rate": out["low_confidence_rate"],
                "high_confidence_win_accuracy": (float(out["high_confidence_correct"] / out["high_confidence_total"]) if out["high_confidence_total"] > 0 else None),
                "metrics": m.__dict__,
            }
            if args.save_v4_models and out.get("saved_seed_models"):
                payload["saved_seed_models"] = out["saved_seed_models"]
                payload["saved_meta"] = out.get("saved_meta")
            report["leagues"][str(lid)] = payload
            LOG.info(
                "[%s] win_acc=%.3f mae=%.3f brier=%.4f ece=%.4f alpha_test_avg=%.3f low_conf_rate=%.3f",
                name,
                m.winner_accuracy,
                m.overall_mae,
                m.brier_winner,
                m.ece_winner,
                float(out["alpha_avg_test"]),
                float(out["low_confidence_rate"]),
            )

    LOG.info("=== MAZ MAXED V4 Summary ===")
    LOG.info("%s", json.dumps(report["summary"], indent=2))
    LOG.info("=== MAZ MAXED V4 Final League Recap ===")
    for lid_s, payload in report["leagues"].items():
        name = str(payload.get("name", f"League {lid_s}"))
        status = str(payload.get("status", "unknown"))
        if status == "tested":
            m = payload.get("metrics", {})
            LOG.info(
                "[%s] status=tested | win_acc=%.3f mae=%.3f",
                name,
                float(m.get("winner_accuracy", 0.0)),
                float(m.get("overall_mae", 0.0)),
            )
        elif status == "trained_only":
            tm = payload.get("train_metrics") or {}
            if tm:
                LOG.info(
                    "[%s] status=trained_only | train_win_acc=%.3f train_mae=%.3f",
                    name,
                    float(tm.get("winner_accuracy", 0.0)),
                    float(tm.get("overall_mae", 0.0)),
                )
            else:
                LOG.info("[%s] status=trained_only", name)
        else:
            LOG.info("[%s] status=%s", name, status)
    if args.save_report:
        out_dir = Path("artifacts")
        out_dir.mkdir(exist_ok=True)
        if args.walk_forward:
            mode_tag = "walk_forward_eval"
        elif args.train_all_completed:
            mode_tag = "train_all_prod"
        else:
            mode_tag = "single_holdout_eval"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = out_dir / f"maz_maxed_v4_{mode_tag}_{stamp}.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        LOG.info("Report saved: %s", out_file)
        # Stable pointers for downstream consumers (UI/automation).
        if args.walk_forward:
            latest_eval = out_dir / "maz_maxed_v4_metrics_latest.json"
            latest_eval.write_text(json.dumps(report, indent=2), encoding="utf-8")
            LOG.info("Updated latest eval metrics: %s", latest_eval)
        if args.train_all_completed:
            latest_prod = out_dir / "maz_maxed_v4_prod_latest.json"
            latest_prod.write_text(json.dumps(report, indent=2), encoding="utf-8")
            LOG.info("Updated latest production report: %s", latest_prod)


if __name__ == "__main__":
    main()

