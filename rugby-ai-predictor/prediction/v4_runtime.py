"""
V4 runtime predictor for Cloud Functions inference.

Loads MAZ MAXED V4 seed checkpoints (.pt) plus league meta (.pkl)
and runs ensemble inference directly in Firebase Functions.
"""

from __future__ import annotations

import logging
import pickle
import re
import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
from prediction.sportdevs_client import SportDevsClient, extract_odds_features

try:
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
except Exception as e:
    torch = None

    class _NNFallback:
        class Module:
            pass

    nn = _NNFallback()  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR = e

logger = logging.getLogger(__name__)
DEFAULT_PROB_STD_THRESHOLD = 0.06

TEAM_NAME_ALIAS_BY_NORMALIZED: Dict[str, str] = {
    "newsouthwaleswaratahs": "waratahs",
    "wellingtonhurricanes": "hurricanes",
    "hurricanessuperrugby": "hurricanes",
    "otagohighlanders": "highlanders",
    "highlanderssuperrugby": "highlanders",
    "actbrumbies": "brumbies",
    "queenslandreds": "reds",
    "bluessuperrugby": "blues",
    "crusaderssuperrugby": "crusaders",
    "chiefssuperrugby": "chiefs",
}


def _team_key(team_id: Any) -> int:
    try:
        return int(team_id)
    except Exception:
        return -1


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    import math

    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def _build_calibration_features(
    p_raw: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
) -> np.ndarray:
    p = np.clip(p_raw.astype(float), 1e-6, 1.0 - 1e-6)
    prob_std_arr = np.array(prob_std if prob_std is not None else np.zeros_like(p), dtype=np.float32)
    margin_var_arr = np.array(margin_var if margin_var is not None else np.zeros_like(p), dtype=np.float32)
    logit = np.log(p / (1.0 - p))
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


def _apply_calibrator(
    cal: Optional[Dict[str, Any]],
    p_raw: np.ndarray,
    prob_std: Optional[np.ndarray] = None,
    margin_var: Optional[np.ndarray] = None,
) -> np.ndarray:
    p = np.clip(p_raw.astype(float), 1e-6, 1.0 - 1e-6)
    if not cal:
        return p
    method = str(cal.get("method", "")).lower()

    def _shrink(out: np.ndarray) -> np.ndarray:
        lam = float(np.clip(float(cal.get("shrink_lambda", 0.0)), 0.0, 0.5))
        return np.clip(0.5 + ((out - 0.5) * (1.0 - lam)), 1e-6, 1.0 - 1e-6)

    try:
        if method == "constant":
            out = np.full(
                len(p),
                float(np.clip(cal.get("p", 0.5), 1e-6, 1.0 - 1e-6)),
                dtype=float,
            )
            return _shrink(out)
        if method == "identity":
            return _shrink(p)
        if method == "isotonic" and cal.get("model") is not None:
            return _shrink(np.clip(cal["model"].predict(p), 1e-6, 1.0 - 1e-6))
        if method == "beta" and cal.get("model") is not None:
            x = np.column_stack([np.log(p), np.log(1.0 - p)])
            out = np.clip(cal["model"].predict_proba(x)[:, 1], 1e-6, 1.0 - 1e-6)
            return _shrink(out)
        if method == "context_platt" and cal.get("model") is not None:
            x = _build_calibration_features(p, prob_std, margin_var)
            mean = np.array(cal.get("feature_mean") or [0.0] * x.shape[1], dtype=np.float32)
            std = np.array(cal.get("feature_std") or [1.0] * x.shape[1], dtype=np.float32)
            std = np.where(std < 1e-6, 1.0, std)
            xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
            out = np.clip(cal["model"].predict_proba(xs)[:, 1], 1e-6, 1.0 - 1e-6)
            return _shrink(out)
        if method == "platt" and cal.get("model") is not None:
            x = np.log(p / (1.0 - p)).reshape(-1, 1)
            out = np.clip(cal["model"].predict_proba(x)[:, 1], 1e-6, 1.0 - 1e-6)
            return _shrink(out)
    except Exception as cal_error:
        logger.warning("Falling back to raw V4 probabilities after calibrator failure: %s", cal_error)
    return p


def _blend_logit_features(p: np.ndarray) -> np.ndarray:
    p2 = np.clip(p.astype(float), 1e-6, 1.0 - 1e-6)
    return np.log(p2 / (1.0 - p2))


def _build_blend_features(p_cls: np.ndarray, p_sd: np.ndarray) -> np.ndarray:
    cls_logit = _blend_logit_features(p_cls)
    sd_logit = _blend_logit_features(p_sd)
    return np.column_stack(
        [
            cls_logit,
            sd_logit,
            cls_logit - sd_logit,
            np.abs(cls_logit - sd_logit),
        ]
    ).astype(np.float32)


def _apply_probability_blender(
    blender: Optional[Dict[str, Any]],
    p_cls: np.ndarray,
    p_sd: np.ndarray,
) -> np.ndarray:
    p_cls = np.clip(p_cls.astype(float), 1e-6, 1.0 - 1e-6)
    p_sd = np.clip(p_sd.astype(float), 1e-6, 1.0 - 1e-6)
    if not blender:
        return np.clip(0.5 * (p_cls + p_sd), 1e-6, 1.0 - 1e-6)
    method = str(blender.get("method", "")).lower()
    try:
        if method == "constant":
            return np.full(
                len(p_cls),
                float(np.clip(blender.get("p", 0.5), 1e-6, 1.0 - 1e-6)),
                dtype=float,
            )
        if method == "alpha_grid":
            alpha = float(blender.get("alpha", 0.5))
            return np.clip((alpha * p_cls) + ((1.0 - alpha) * p_sd), 1e-6, 1.0 - 1e-6)
        if method == "logistic_meta" and blender.get("model") is not None:
            x = _build_blend_features(p_cls, p_sd)
            mean = np.array(blender.get("feature_mean") or [0.0] * x.shape[1], dtype=np.float32)
            std = np.array(blender.get("feature_std") or [1.0] * x.shape[1], dtype=np.float32)
            std = np.where(std < 1e-6, 1.0, std)
            xs = (x - mean.reshape(1, -1)) / std.reshape(1, -1)
            return np.clip(blender["model"].predict_proba(xs)[:, 1], 1e-6, 1.0 - 1e-6)
    except Exception as blend_error:
        logger.warning("Falling back to neutral V4 blend after blender failure: %s", blend_error)
    return np.clip(0.5 * (p_cls + p_sd), 1e-6, 1.0 - 1e-6)


def _coerce_vector(values: Any, size: int, fill_value: float) -> np.ndarray:
    arr = np.array([] if values is None else values, dtype=np.float32)
    if arr.shape[0] == size:
        return arr
    out = np.full((size,), fill_value, dtype=np.float32)
    take = min(size, int(arr.shape[0]))
    if take > 0:
        out[:take] = arr[:take]
    return out


def _confidence_penalty(value: float, threshold: float, cap: float) -> float:
    if threshold <= 1e-9 or value <= threshold:
        return 0.0
    return float(min(cap, cap * ((value / threshold) - 1.0)))


class V4Model(nn.Module):
    """Mirror of training architecture needed for state_dict inference."""

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
        self.score_head = nn.Linear(64, 2)
        self.var_head = nn.Linear(64, 2)
        self.cov_head = nn.Linear(64, 1)
        self.alpha_head = nn.Linear(64, 1)

    def encode_team(self, team_idx: torch.Tensor, seq_x: torch.Tensor, opp_idx_seq: torch.Tensor) -> torch.Tensor:
        emb = self.team_emb(team_idx)
        opp_emb = self.team_emb(opp_idx_seq)
        opp_ctx = self.opp_proj(opp_emb)
        rnn_in = torch.cat([seq_x, opp_ctx], dim=2)
        out, h = self.rnn(rnn_in)
        attn_logits = self.time_attn(out).squeeze(-1)
        valid = torch.abs(seq_x).sum(dim=2) > 1e-8
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


class V4RuntimePredictor:
    """Serve V4 ensemble directly from .pt checkpoints."""

    def __init__(
        self,
        v4_assets: Dict[str, Any],
        db_path: str = "data.sqlite",
        sportdevs_api_key: str = "",
        **_: Any,
    ):
        if torch is None:
            raise RuntimeError(
                f"PyTorch is required for V4 runtime inference: {_TORCH_IMPORT_ERROR}"
            )
        self.db_path = db_path
        self.v4_assets = v4_assets
        self.sportdevs_client = SportDevsClient(sportdevs_api_key or "")

        with open(v4_assets["meta_path"], "rb") as f:
            self.meta: Dict[str, Any] = pickle.load(f)

        self.league_id = int(self.meta["league_id"])
        self.league_name = str(self.meta.get("league_name", f"League {self.league_id}"))
        self.team_to_idx: Dict[int, int] = {
            int(k): int(v) for k, v in (self.meta.get("team_to_idx") or {}).items()
        }
        self.league_to_idx: Dict[int, int] = {
            int(k): int(v) for k, v in (self.meta.get("league_to_idx") or {}).items()
        }
        self.league_score_stats = {
            int(k): (float(v[0]), float(v[1]))
            for k, v in (self.meta.get("league_score_stats_train") or {}).items()
        }
        self.league_env_stats = {
            int(k): {
                "home_prob": float((v or {}).get("home_prob", 0.55)),
                "home_strength": float((v or {}).get("home_strength", 1.0)),
                "rating_home_adv": float((v or {}).get("rating_home_adv", 2.0)),
            }
            for k, v in (self.meta.get("league_env_stats_train") or {}).items()
        }
        cfg = self.meta.get("config") or {}
        self.seq_len = int(cfg.get("seq_len", 10))
        self.emb_dim = int(cfg.get("emb_dim", 32))
        self.hidden_dim = int(cfg.get("hidden_dim", 64))
        self.seq_dim = int(cfg.get("seq_dim", 7))
        self.rating_k = float(cfg.get("rating_k", 0.06))
        self.rating_home_adv = float(cfg.get("rating_home_adv", 2.0))
        self.rating_scale = float(cfg.get("rating_scale", 7.0))
        norm = self.meta.get("normalization_stats") or {}
        self.norm_mean = _coerce_vector(norm.get("mean"), self.seq_dim, 0.0)
        self.norm_std = _coerce_vector(norm.get("std"), self.seq_dim, 1.0)
        self.norm_std = np.where(self.norm_std < 1e-6, 1.0, self.norm_std)
        self.calibrator: Optional[Dict[str, Any]] = self.meta.get("calibrator")
        self.probability_blender: Optional[Dict[str, Any]] = self.meta.get("probability_blender")
        self.regime_name = str(self.meta.get("regime_name", "balanced_competitive"))
        self.regime_idx = int(self.meta.get("regime_idx", 1))
        self.regime_uncertainty_multiplier = float(
            self.meta.get("regime_uncertainty_multiplier", 1.0)
        )
        self.confidence_margin_variance_threshold = float(
            self.meta.get("confidence_margin_variance_threshold", 40.0)
        )
        self.confidence_prob_std_threshold = float(
            self.meta.get("confidence_prob_std_threshold", DEFAULT_PROB_STD_THRESHOLD)
        )

        self.models: List[V4Model] = []
        for seed_path in v4_assets.get("seed_model_paths", []):
            model = V4Model(
                n_teams=max(1, len(self.team_to_idx)),
                n_leagues=max(1, len(self.league_to_idx)),
                emb_dim=self.emb_dim,
                seq_dim=self.seq_dim,
                hidden_dim=self.hidden_dim,
            )
            state = torch.load(seed_path, map_location="cpu")
            model.load_state_dict(state, strict=True)
            model.eval()
            self.models.append(model)
        if not self.models:
            raise RuntimeError(f"No V4 seed models loaded for league {self.league_id}")

        logger.info(
            "Loaded V4 runtime ensemble for league %s (%s) with %s seed models",
            self.league_id,
            self.league_name,
            len(self.models),
        )

    @staticmethod
    def _normalize_team_name(name: str) -> str:
        txt = str(name or "").strip().lower()
        txt = re.sub(r"\bsuper rugby\b", " ", txt)
        txt = re.sub(r"\brugby\b", " ", txt)
        normalized = re.sub(r"[^a-z0-9]+", "", txt)
        return TEAM_NAME_ALIAS_BY_NORMALIZED.get(normalized, normalized)

    def _resolve_team_id(self, conn: sqlite3.Connection, team_name: str) -> int:
        target_norm = self._normalize_team_name(team_name)
        cur = conn.cursor()

        # 1) Exact/raw matches first, but prefer IDs present in training mapping.
        cur.execute("SELECT id, name FROM team WHERE LOWER(name)=LOWER(?)", (team_name,))
        exact_rows = cur.fetchall() or []
        exact_ids = [int(r[0]) for r in exact_rows]
        for tid in exact_ids:
            if tid in self.team_to_idx:
                return tid
        if exact_ids:
            return exact_ids[0]

        # 2) Normalized matching across all teams; again prefer known training IDs.
        cur.execute("SELECT id, name FROM team")
        rows = cur.fetchall() or []
        norm_exact_known: List[int] = []
        norm_exact_any: List[int] = []
        norm_fuzzy_known: List[int] = []
        norm_fuzzy_any: List[int] = []
        for row in rows:
            tid = int(row[0])
            name = str(row[1] or "")
            name_norm = self._normalize_team_name(name)
            if not name_norm:
                continue
            is_known = tid in self.team_to_idx
            if name_norm == target_norm:
                if is_known:
                    norm_exact_known.append(tid)
                else:
                    norm_exact_any.append(tid)
            elif target_norm and (target_norm in name_norm or name_norm in target_norm):
                if is_known:
                    norm_fuzzy_known.append(tid)
                else:
                    norm_fuzzy_any.append(tid)

        for bucket in (norm_exact_known, norm_exact_any, norm_fuzzy_known, norm_fuzzy_any):
            if bucket:
                return bucket[0]

        # 3) Last resort: old LIKE behavior (kept for backward compatibility).
        cur.execute("SELECT id FROM team WHERE LOWER(name) LIKE LOWER(?) LIMIT 1", (f"%{team_name}%",))
        row = cur.fetchone()
        if row:
            return int(row[0])

        raise ValueError(f"Team '{team_name}' not found in database")

    def _history_features(
        self,
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
        feats: List[float] = [
            points_for_scaled,
            points_against_scaled,
            margin_scaled,
            is_home,
        ]
        if self.seq_dim >= 11:
            feats.append(venue_adv_context)
        feats.extend(
            [
                rest_days_norm,
                margin_vol5_norm,
                margin_vol10_norm,
            ]
        )
        if self.seq_dim >= 10:
            sd = max(1.0, float(score_sd))
            feats.extend(
                [
                    float(team_rating_pre) / sd,
                    float(opp_rating_pre) / sd,
                    float(expected_margin_pre) / sd,
                ]
            )
        if len(feats) < self.seq_dim:
            feats.extend([0.0] * (self.seq_dim - len(feats)))
        return np.array(feats[: self.seq_dim], dtype=np.float32)

    def _build_team_histories(self, conn: sqlite3.Connection, match_date: str) -> Dict[int, Deque[Tuple[np.ndarray, int]]]:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date_event, home_team_id, away_team_id, home_score, away_score
            FROM event
            WHERE league_id = ?
              AND date_event IS NOT NULL
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND date(date_event) < date(?)
            ORDER BY date_event ASC, id ASC
            """,
            (self.league_id, match_date),
        )
        rows = cur.fetchall()

        histories: Dict[int, Deque[Tuple[np.ndarray, int]]] = defaultdict(
            lambda: deque(maxlen=self.seq_len)
        )
        team_last_date: Dict[int, datetime] = {}
        team_margin_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))
        team_rating: Dict[int, float] = defaultdict(float)
        mu_l, sd_l = self.league_score_stats.get(self.league_id, (20.0, 8.0))
        sd_l = sd_l if sd_l > 1e-6 else 8.0
        league_env = self.league_env_stats.get(self.league_id) or {}
        home_strength = float(league_env.get("home_strength", 1.0))
        rating_home_adv = float(league_env.get("rating_home_adv", self.rating_home_adv))

        for date_event, home_team_id, away_team_id, home_score, away_score in rows:
            h = _team_key(home_team_id)
            a = _team_key(away_team_id)
            hs = float(home_score)
            aw = float(away_score)
            try:
                dt = datetime.strptime(str(date_event)[:10], "%Y-%m-%d")
            except Exception:
                continue

            d_h = float((dt - team_last_date[h]).days) if h in team_last_date else 7.0
            d_a = float((dt - team_last_date[a]).days) if a in team_last_date else 7.0
            rest_h = max(0.0, min(d_h, 42.0)) / 14.0
            rest_a = max(0.0, min(d_a, 42.0)) / 14.0

            def _roll_std(vals: Deque[float], n: int) -> float:
                if not vals:
                    return 0.0
                arr = np.array(list(vals)[-n:], dtype=float)
                return float(np.std(arr)) if len(arr) > 1 else 0.0

            vol5_h = _roll_std(team_margin_hist[h], 5) / max(1.0, sd_l)
            vol10_h = _roll_std(team_margin_hist[h], 10) / max(1.0, sd_l)
            vol5_a = _roll_std(team_margin_hist[a], 5) / max(1.0, sd_l)
            vol10_a = _roll_std(team_margin_hist[a], 10) / max(1.0, sd_l)

            hs_s = (hs - mu_l) / sd_l
            aw_s = (aw - mu_l) / sd_l
            m_h_s = (hs - aw) / sd_l
            m_a_s = (aw - hs) / sd_l
            rating_h_pre = float(team_rating.get(h, 0.0))
            rating_a_pre = float(team_rating.get(a, 0.0))
            exp_margin_h = (rating_h_pre - rating_a_pre + rating_home_adv) / max(
                1.0,
                self.rating_scale,
            )
            exp_margin_a = -exp_margin_h
            histories[h].append(
                (
                    self._history_features(
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
                    self._history_features(
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
            exp_h = (team_rating.get(h, 0.0) - team_rating.get(a, 0.0) + rating_home_adv) / max(
                1.0,
                self.rating_scale,
            )
            err = (hs - aw) - exp_h
            team_rating[h] = team_rating.get(h, 0.0) + (self.rating_k * err)
            team_rating[a] = team_rating.get(a, 0.0) - (self.rating_k * err)
            team_last_date[h] = dt
            team_last_date[a] = dt
        return histories

    def _build_single_input(self, conn: sqlite3.Connection, home_team_id: int, away_team_id: int, match_date: str):
        histories = self._build_team_histories(conn, match_date)

        def _seq_for(team_id: int) -> Tuple[np.ndarray, np.ndarray]:
            seq = np.zeros((self.seq_len, self.seq_dim), dtype=np.float32)
            opp = np.zeros((self.seq_len,), dtype=np.int64)
            hist = list(histories.get(team_id, []))
            if hist:
                arr = np.stack([x[0] for x in hist], axis=0)
                opp_raw = [x[1] for x in hist]
                seq[-len(hist) :, :] = arr
                opp[-len(hist) :] = np.array(
                    [self.team_to_idx.get(int(o), 0) for o in opp_raw], dtype=np.int64
                )
            seq = (seq - self.norm_mean.reshape(1, -1)) / self.norm_std.reshape(1, -1)
            return seq.astype(np.float32), opp

        h_seq, h_opp = _seq_for(home_team_id)
        a_seq, a_opp = _seq_for(away_team_id)

        h_idx = np.array([self.team_to_idx.get(int(home_team_id), 0)], dtype=np.int64)
        a_idx = np.array([self.team_to_idx.get(int(away_team_id), 0)], dtype=np.int64)
        l_idx = np.array([self.league_to_idx.get(int(self.league_id), 0)], dtype=np.int64)
        r_idx = np.array([self.regime_idx], dtype=np.int64)

        return (
            torch.tensor(h_idx, dtype=torch.long),
            torch.tensor(a_idx, dtype=torch.long),
            torch.tensor(l_idx, dtype=torch.long),
            torch.tensor(r_idx, dtype=torch.long),
            torch.tensor(h_seq[None, :, :], dtype=torch.float32),
            torch.tensor(a_seq[None, :, :], dtype=torch.float32),
            torch.tensor(h_opp[None, :], dtype=torch.long),
            torch.tensor(a_opp[None, :], dtype=torch.long),
        )

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        league_id: int,
        match_date: str,
        match_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if int(league_id) != int(self.league_id):
            raise ValueError(
                f"League ID mismatch: V4 predictor for {self.league_id}, requested {league_id}"
            )

        conn = sqlite3.connect(self.db_path)
        try:
            home_team_id = self._resolve_team_id(conn, home_team)
            away_team_id = self._resolve_team_id(conn, away_team)
            tensors = self._build_single_input(conn, home_team_id, away_team_id, match_date)
        finally:
            conn.close()

        raw_probs: List[float] = []
        cls_probs: List[float] = []
        sd_probs: List[float] = []
        proxy_probs: List[float] = []
        pred_home_scores: List[float] = []
        pred_away_scores: List[float] = []
        margin_variances: List[float] = []
        mu_l, sd_l = self.league_score_stats.get(self.league_id, (20.0, 8.0))
        sd_l = sd_l if sd_l > 1e-6 else 8.0

        with torch.no_grad():
            for model in self.models:
                out = model(*tensors)
                p_cls = float(torch.sigmoid(out["winner_logit"]).cpu().numpy()[0])
                mu_scaled = out["score_mu"].cpu().numpy()[0]
                var_scaled = np.exp(out["score_logvar"].clamp(-5.0, 4.0).cpu().numpy()[0])
                var = var_scaled * float(sd_l * sd_l)
                rho = float(0.95 * np.tanh(out["score_rho_logit"].cpu().numpy()[0]))
                alpha = float(torch.sigmoid(out["alpha_logit"]).cpu().numpy()[0])

                mu_home = float((mu_scaled[0] * sd_l) + mu_l)
                mu_away = float((mu_scaled[1] * sd_l) + mu_l)
                margin = mu_home - mu_away
                var_d = max(
                    1e-6,
                    float(
                        var[0]
                        + var[1]
                        - (2.0 * rho * np.sqrt(max(1e-6, float(var[0] * var[1]))))
                    )
                    * self.regime_uncertainty_multiplier,
                )
                p_sd = float(_norm_cdf(np.array([margin / np.sqrt(var_d)], dtype=float))[0])
                p_raw = float(np.clip((alpha * p_cls) + ((1.0 - alpha) * p_sd), 1e-6, 1.0 - 1e-6))

                cls_probs.append(p_cls)
                sd_probs.append(p_sd)
                raw_probs.append(p_raw)
                proxy_probs.append(float(np.clip(0.5 * (p_cls + p_sd), 1e-6, 1.0 - 1e-6)))
                pred_home_scores.append(mu_home)
                pred_away_scores.append(mu_away)
                margin_variances.append(var_d)

        if self.probability_blender:
            ai_home_win_prob_raw = float(
                _apply_probability_blender(
                    self.probability_blender,
                    np.array([float(np.mean(cls_probs))], dtype=float),
                    np.array([float(np.mean(sd_probs))], dtype=float),
                )[0]
            )
        else:
            ai_home_win_prob_raw = float(np.mean(raw_probs))
        avg_margin_var = float(np.mean(margin_variances)) if margin_variances else 0.0
        ensemble_prob_std = float(np.std(proxy_probs)) if len(proxy_probs) > 1 else 0.0
        ai_home_win_prob = float(
            _apply_calibrator(
                self.calibrator,
                np.array([ai_home_win_prob_raw], dtype=float),
                np.array([ensemble_prob_std], dtype=float),
                np.array([avg_margin_var], dtype=float),
            )[0]
        )
        predicted_home_score = float(np.mean(pred_home_scores))
        predicted_away_score = float(np.mean(pred_away_scores))
        is_low_confidence = bool(
            (avg_margin_var > self.confidence_margin_variance_threshold)
            or (ensemble_prob_std > self.confidence_prob_std_threshold)
        )

        bookmaker_odds = self.sportdevs_client.get_match_odds(
            match_id=int(match_id) if match_id is not None else None,
            league_id=int(league_id) if league_id is not None else None,
            match_date=str(match_date),
            home_team=str(home_team),
            away_team=str(away_team),
        )
        odds_features = extract_odds_features(bookmaker_odds)
        bookmaker_count = int(odds_features.get("bookmaker_count", 0) or 0)
        bookmaker_home_prob = float(odds_features.get("home_win_probability", 0.5))
        bookmaker_confidence = float(odds_features.get("odds_confidence", 0.5))

        if bookmaker_count > 0:
            agreement = 1.0 - abs(ai_home_win_prob - bookmaker_home_prob)
            if agreement > 0.8:
                ai_weight = 0.5
                odds_weight = 0.5
            elif agreement > 0.6:
                ai_weight = 0.4
                odds_weight = 0.6
            else:
                ai_weight = 0.25
                odds_weight = 0.75
            if bookmaker_count > 5:
                odds_weight = min(0.8, odds_weight + 0.1)
                ai_weight = 1.0 - odds_weight
            home_win_prob = (ai_weight * ai_home_win_prob) + (odds_weight * bookmaker_home_prob)
            prediction_type = "Hybrid AI + Live Odds"
            confidence = (ai_weight * max(ai_home_win_prob, 1.0 - ai_home_win_prob)) + (
                odds_weight * bookmaker_confidence
            )
        else:
            home_win_prob = ai_home_win_prob
            prediction_type = "AI Only (No Odds)"
            confidence = max(home_win_prob, 1.0 - home_win_prob)
        confidence -= _confidence_penalty(
            avg_margin_var,
            self.confidence_margin_variance_threshold,
            0.08,
        )
        confidence -= _confidence_penalty(
            ensemble_prob_std,
            self.confidence_prob_std_threshold,
            0.10,
        )
        if is_low_confidence:
            confidence = min(confidence, 0.68)
        confidence = float(np.clip(confidence, 0.5, 0.97))

        predicted_winner = "Home" if home_win_prob >= 0.5 else "Away"
        return {
            "predicted_winner": predicted_winner,
            "predicted_home_score": float(max(0.0, predicted_home_score)),
            "predicted_away_score": float(max(0.0, predicted_away_score)),
            "confidence": float(confidence),
            "home_win_prob": float(home_win_prob),
            "away_win_prob": float(1.0 - home_win_prob),
            "prediction_type": prediction_type,
            "ai_home_win_prob": float(ai_home_win_prob),
            "ai_home_win_prob_raw": float(ai_home_win_prob_raw),
            "hybrid_home_win_prob": float(home_win_prob),
            "bookmaker_home_win_prob": float(bookmaker_home_prob),
            "bookmaker_count": bookmaker_count,
            "bookmaker_confidence": bookmaker_confidence,
            "model_type": "v4_runtime",
            "model_family": "v4",
            "additional_metrics": {
                "home_advantage": 0.0,
                "form_difference": 0.0,
                "elo_difference": 0.0,
                "regime": self.regime_name,
                "regime_idx": int(self.regime_idx),
                "margin_variance": float(avg_margin_var),
                "ensemble_prob_std": float(ensemble_prob_std),
                "blend_method": (
                    str(self.probability_blender.get("method", "alpha_head"))
                    if self.probability_blender
                    else "alpha_head"
                ),
                "confidence_margin_variance_threshold": float(
                    self.confidence_margin_variance_threshold
                ),
                "confidence_prob_std_threshold": float(self.confidence_prob_std_threshold),
                "is_low_confidence": is_low_confidence,
            },
        }

