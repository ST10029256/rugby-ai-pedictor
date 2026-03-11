#!/usr/bin/env python3
"""
MAZ Boss MAXED V5

Global backbone + league adapters + cross-team interaction experts.
Built as a parallel path beside V4 so it can be trained, evaluated, and
deployed without destabilizing the existing V4 production stack.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import pickle
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
    import torch.nn.functional as F  # type: ignore
except Exception as e:
    torch = None

    class _NNFallback:
        class Module:
            pass

    nn = _NNFallback()  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR = e


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_v4_base() -> Any:
    base_path = SCRIPT_DIR / "maz_boss_maxed_v4.py"
    module_name = "_maz_v4_base"
    spec = importlib.util.spec_from_file_location(module_name, base_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load V4 base module from {base_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_V4 = _load_v4_base()

Metrics = _V4.Metrics
LEAGUE_MAPPINGS = _V4.LEAGUE_MAPPINGS
FRIENDLIES_LEAGUE_ID = _V4.FRIENDLIES_LEAGUE_ID
DEFAULT_PROB_STD_THRESHOLD = _V4.DEFAULT_PROB_STD_THRESHOLD

default_db_path = _V4.default_db_path
load_all_df = _V4.load_all_df
build_global_team_to_idx = _V4.build_global_team_to_idx
build_global_league_to_idx = _V4.build_global_league_to_idx
build_league_score_stats = _V4.build_league_score_stats
build_league_environment_stats = _V4.build_league_environment_stats
scale_score_targets = _V4.scale_score_targets
unscale_score_predictions = _V4.unscale_score_predictions
unscale_score_variances = _V4.unscale_score_variances
build_recency_weights = _V4.build_recency_weights
weighted_mean = _V4.weighted_mean
_quantile_or_fallback = _V4._quantile_or_fallback
build_temporal_sequences = _V4.build_temporal_sequences
normalize_sequences = _V4.normalize_sequences
detect_regime = _V4.detect_regime
detect_regime_map_by_league = _V4.detect_regime_map_by_league
fit_probability_blender = _V4.fit_probability_blender
apply_probability_blender = _V4.apply_probability_blender
fit_calibrator = _V4.fit_calibrator
apply_calibrator = _V4.apply_calibrator
evaluate = _V4.evaluate
_norm_cdf = _V4._norm_cdf
_parse_int_list = _V4._parse_int_list
_setup_logging = _V4._setup_logging


V5_VERSION = "v5"
V5_ARCHITECTURE = "global_backbone_league_adapters_cross_attention_moe_score_first"
LOG = logging.getLogger("maz_v5")


def _safe_num_heads(hidden_dim: int, requested_heads: int) -> int:
    for heads in (requested_heads, 8, 4, 2, 1):
        if heads > 0 and hidden_dim % heads == 0:
            return heads
    return 1


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    w = mask.float().unsqueeze(-1)
    denom = torch.clamp(torch.sum(w, dim=1), min=1.0)
    return torch.sum(values * w, dim=1) / denom


@dataclass
class SplitBundle:
    xh: torch.Tensor
    xa: torch.Tensor
    ih: torch.Tensor
    ia: torch.Tensor
    ioh: torch.Tensor
    ioa: torch.Tensor
    il: torch.Tensor
    ir: torch.Tensor
    y: torch.Tensor
    weights: Optional[torch.Tensor]

    @property
    def n_rows(self) -> int:
        return int(self.y.shape[0])


class V5Model(nn.Module):
    """
    Stronger than V4 along three axes:
    1. League/regime adapters rather than only scalar biases.
    2. Cross-team temporal interaction via attention over the encoded histories.
    3. Mixture-of-experts head and score-first winner residual.
    """

    def __init__(
        self,
        n_teams: int,
        n_leagues: int,
        emb_dim: int,
        seq_dim: int,
        hidden_dim: int,
        n_experts: int = 4,
        adapter_dim: int = 24,
        cross_heads: int = 4,
    ):
        super().__init__()
        self.n_experts = int(max(2, n_experts))
        self.team_emb = nn.Embedding(n_teams, emb_dim)
        self.league_home_bias = nn.Embedding(n_leagues, 1)
        self.regime_var_bias = nn.Embedding(4, 1)
        self.league_ctx_emb = nn.Embedding(n_leagues, adapter_dim)
        self.regime_ctx_emb = nn.Embedding(4, adapter_dim)
        self.opp_proj = nn.Linear(emb_dim, 16)
        self.seq_stat_proj = nn.Sequential(
            nn.Linear(seq_dim, 16),
            nn.LayerNorm(16),
            nn.ReLU(),
        )
        self.rnn = nn.GRU(
            input_size=seq_dim + 16,
            hidden_size=hidden_dim,
            num_layers=2,
            dropout=0.10,
            batch_first=True,
        )
        attn_heads = _safe_num_heads(hidden_dim, cross_heads)
        self.self_refiner = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=attn_heads,
            batch_first=True,
            dropout=0.10,
        )
        self.cross_attn = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=attn_heads,
            batch_first=True,
            dropout=0.10,
        )
        self.self_pool = nn.Linear(hidden_dim, 1)
        self.cross_pool = nn.Linear(hidden_dim, 1)
        self.cold_history = nn.Parameter(torch.zeros(hidden_dim))

        team_repr_dim = emb_dim + hidden_dim + hidden_dim + 16
        context_dim = adapter_dim * 2
        match_dim = (team_repr_dim * 4) + context_dim

        self.expert_gate = nn.Sequential(
            nn.Linear(match_dim, 128),
            nn.ReLU(),
            nn.Linear(128, self.n_experts),
        )
        self.experts = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(match_dim, 256),
                    nn.ReLU(),
                    nn.Dropout(0.15),
                    nn.Linear(256, 128),
                    nn.ReLU(),
                )
                for _ in range(self.n_experts)
            ]
        )
        self.adapter = nn.Sequential(
            nn.Linear(context_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
        )
        self.post = nn.Sequential(
            nn.LayerNorm(128),
            nn.Linear(128, 96),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(96, 64),
            nn.ReLU(),
        )
        self.score_head = nn.Linear(64, 2)
        self.var_head = nn.Linear(64, 2)
        self.cov_head = nn.Linear(64, 1)
        self.alpha_head = nn.Linear(64, 1)
        self.winner_residual_head = nn.Linear(64, 1)
        self.margin_scale = nn.Parameter(torch.tensor(1.0))

    def _ensure_history(self, seq_out: torch.Tensor, valid: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        has_hist = valid.any(dim=1)
        if torch.all(has_hist):
            return seq_out, valid
        seq_out = seq_out.clone()
        valid = valid.clone()
        seq_out[~has_hist, 0, :] = self.cold_history.unsqueeze(0)
        valid[~has_hist, 0] = True
        return seq_out, valid

    @staticmethod
    def _attention_pool(seq_out: torch.Tensor, valid: torch.Tensor, scorer: nn.Linear) -> torch.Tensor:
        logits = scorer(seq_out).squeeze(-1)
        logits = logits.masked_fill(~valid, -1e9)
        weights = torch.softmax(logits, dim=1)
        return torch.bmm(weights.unsqueeze(1), seq_out).squeeze(1)

    def encode_team(self, team_idx: torch.Tensor, seq_x: torch.Tensor, opp_idx_seq: torch.Tensor) -> Dict[str, torch.Tensor]:
        team_emb = self.team_emb(team_idx)
        opp_emb = self.team_emb(opp_idx_seq)
        opp_ctx = self.opp_proj(opp_emb)
        rnn_in = torch.cat([seq_x, opp_ctx], dim=2)
        seq_out, _ = self.rnn(rnn_in)
        valid = torch.abs(seq_x).sum(dim=2) > 1e-8
        seq_out, valid = self._ensure_history(seq_out, valid)
        refined, _ = self.self_refiner(seq_out, seq_out, seq_out, key_padding_mask=~valid)
        seq_out = seq_out + refined
        pooled = self._attention_pool(seq_out, valid, self.self_pool)
        seq_stats = self.seq_stat_proj(_masked_mean(seq_x, valid))
        return {
            "team_emb": team_emb,
            "seq_out": seq_out,
            "valid": valid,
            "pooled": pooled,
            "seq_stats": seq_stats,
        }

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
        h = self.encode_team(home_idx, home_seq, home_opp_idx)
        a = self.encode_team(away_idx, away_seq, away_opp_idx)

        h_cross_seq, _ = self.cross_attn(
            h["seq_out"], a["seq_out"], a["seq_out"], key_padding_mask=~a["valid"]
        )
        a_cross_seq, _ = self.cross_attn(
            a["seq_out"], h["seq_out"], h["seq_out"], key_padding_mask=~h["valid"]
        )
        h_cross = self._attention_pool(h_cross_seq, h["valid"], self.cross_pool)
        a_cross = self._attention_pool(a_cross_seq, a["valid"], self.cross_pool)

        h_repr = torch.cat([h["team_emb"], h["pooled"], h_cross, h["seq_stats"]], dim=1)
        a_repr = torch.cat([a["team_emb"], a["pooled"], a_cross, a["seq_stats"]], dim=1)
        ctx = torch.cat([self.league_ctx_emb(league_idx), self.regime_ctx_emb(regime_idx)], dim=1)

        match_x = torch.cat(
            [
                h_repr,
                a_repr,
                torch.abs(h_repr - a_repr),
                h_repr * a_repr,
                ctx,
            ],
            dim=1,
        )
        gate_logits = self.expert_gate(match_x)
        expert_weights = torch.softmax(gate_logits, dim=1)
        expert_stack = torch.stack([expert(match_x) for expert in self.experts], dim=1)
        z = torch.sum(expert_weights.unsqueeze(-1) * expert_stack, dim=1)

        adapter = self.adapter(ctx)
        scale, bias = torch.chunk(adapter, 2, dim=1)
        z = z * (1.0 + (0.15 * torch.tanh(scale))) + (0.15 * torch.tanh(bias))
        z = self.post(z)

        home_bias = self.league_home_bias(league_idx).squeeze(1)
        reg_var_bias = self.regime_var_bias(regime_idx).squeeze(1)
        score_mu = self.score_head(z)
        score_mu = torch.stack([score_mu[:, 0] + home_bias, score_mu[:, 1]], dim=1)
        score_logvar = self.var_head(z) + reg_var_bias.unsqueeze(1)
        margin_denom = torch.sqrt(
            torch.exp(score_logvar[:, 0]) + torch.exp(score_logvar[:, 1]) + 1e-6
        )
        margin_base = self.margin_scale * (score_mu[:, 0] - score_mu[:, 1]) / margin_denom
        winner_logit = margin_base + self.winner_residual_head(z).squeeze(1) + home_bias
        return {
            "winner_logit": winner_logit,
            "score_mu": score_mu,
            "score_logvar": score_logvar,
            "score_rho_logit": self.cov_head(z).squeeze(1),
            "alpha_logit": self.alpha_head(z).squeeze(1),
            "expert_weights": expert_weights,
        }


def _make_bundle(
    home_seq: np.ndarray,
    away_seq: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_opp_idx: np.ndarray,
    away_opp_idx: np.ndarray,
    league_idx: np.ndarray,
    regime_idx: np.ndarray,
    y_scaled: np.ndarray,
    weights: Optional[np.ndarray] = None,
) -> SplitBundle:
    return SplitBundle(
        xh=torch.tensor(home_seq, dtype=torch.float32),
        xa=torch.tensor(away_seq, dtype=torch.float32),
        ih=torch.tensor(home_idx, dtype=torch.long),
        ia=torch.tensor(away_idx, dtype=torch.long),
        ioh=torch.tensor(home_opp_idx, dtype=torch.long),
        ioa=torch.tensor(away_opp_idx, dtype=torch.long),
        il=torch.tensor(league_idx, dtype=torch.long),
        ir=torch.tensor(regime_idx, dtype=torch.long),
        y=torch.tensor(y_scaled, dtype=torch.float32),
        weights=(torch.tensor(weights, dtype=torch.float32) if weights is not None else None),
    )


def _model_forward(model: V5Model, bundle: SplitBundle, idx: Optional[torch.Tensor] = None) -> Dict[str, torch.Tensor]:
    if idx is None:
        return model(bundle.ih, bundle.ia, bundle.il, bundle.ir, bundle.xh, bundle.xa, bundle.ioh, bundle.ioa)
    return model(
        bundle.ih[idx],
        bundle.ia[idx],
        bundle.il[idx],
        bundle.ir[idx],
        bundle.xh[idx],
        bundle.xa[idx],
        bundle.ioh[idx],
        bundle.ioa[idx],
    )


def _loss_from_outputs(model: V5Model, out: Dict[str, torch.Tensor], y: torch.Tensor, weights: Optional[torch.Tensor], args: Any) -> torch.Tensor:
    y_w = y[:, 0]
    y_h = y[:, 1]
    y_a = y[:, 2]
    loss_w = weighted_mean(
        F.binary_cross_entropy_with_logits(out["winner_logit"], y_w, reduction="none"),
        weights,
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
    loss_s = weighted_mean(nll, weights)
    y_margin = y_h - y_a
    pred_margin = mu[:, 0] - mu[:, 1]
    m_non_draw = torch.abs(y_margin) > 1e-6
    if torch.any(m_non_draw):
        sign = torch.sign(y_margin[m_non_draw])
        rank_weights = weights[m_non_draw] if weights is not None else None
        loss_rank = weighted_mean(
            F.softplus(-(sign * pred_margin[m_non_draw])),
            rank_weights,
        )
    else:
        loss_rank = torch.tensor(0.0, dtype=loss_w.dtype, device=loss_w.device)
    var_reg = torch.mean(logvar ** 2)
    emb_reg = torch.mean(model.team_emb.weight ** 2)
    expert_usage = torch.mean(out["expert_weights"], dim=0)
    expert_target = torch.full_like(expert_usage, 1.0 / float(out["expert_weights"].shape[1]))
    expert_balance = torch.mean((expert_usage - expert_target) ** 2)
    return (
        (args.winner_loss_weight * loss_w)
        + (args.score_loss_weight * loss_s)
        + (args.ranking_loss_weight * loss_rank)
        + (args.var_reg_weight * var_reg)
        + (args.embedding_l2_weight * emb_reg)
        + (args.expert_balance_weight * expert_balance)
    )


def _train_model(model: V5Model, bundle: SplitBundle, epochs: int, batch_size: int, optimizer: torch.optim.Optimizer, args: Any) -> None:
    n_rows = bundle.n_rows
    for _ in range(max(1, int(epochs))):
        model.train()
        perm = torch.randperm(n_rows)
        for i in range(0, n_rows, max(1, batch_size)):
            idx = perm[i : i + batch_size]
            out = _model_forward(model, bundle, idx)
            loss = _loss_from_outputs(
                model,
                out,
                bundle.y[idx],
                (bundle.weights[idx] if bundle.weights is not None else None),
                args,
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()


def _predict_bundle(
    model: V5Model,
    bundle: SplitBundle,
    league_ids_row: np.ndarray,
    league_stats: Dict[int, Tuple[float, float]],
    regime_unc_mult: float,
) -> Dict[str, Any]:
    model.eval()
    with torch.no_grad():
        out = _model_forward(model, bundle)
        p_cls = torch.sigmoid(out["winner_logit"]).cpu().numpy()
        mu = out["score_mu"].cpu().numpy()
        var = np.exp(out["score_logvar"].clamp(-5.0, 4.0).cpu().numpy())
        rho = 0.95 * np.tanh(out["score_rho_logit"].cpu().numpy())
        alpha = torch.sigmoid(out["alpha_logit"]).cpu().numpy()
        expert_weights = out["expert_weights"].cpu().numpy()
        emb_weights = model.team_emb.weight.detach().cpu().numpy()

    mu = unscale_score_predictions(mu, league_ids_row, league_stats)
    var = unscale_score_variances(var, league_ids_row, league_stats)
    md = mu[:, 0] - mu[:, 1]
    margin_var = np.maximum(
        1e-6,
        (var[:, 0] + var[:, 1] - (2.0 * rho * np.sqrt(np.maximum(1e-6, var[:, 0] * var[:, 1]))))
        * float(regime_unc_mult),
    )
    p_sd = _norm_cdf(md / np.sqrt(margin_var))
    emb_norms = np.linalg.norm(emb_weights, axis=1)
    return {
        "p_cls": p_cls,
        "mu": mu,
        "var": var,
        "rho": rho,
        "alpha": alpha,
        "p_sd": p_sd,
        "margin_var": margin_var,
        "emb_norm_mean": float(np.mean(emb_norms)),
        "emb_norm_std": float(np.std(emb_norms)),
        "expert_usage": np.mean(expert_weights, axis=0).tolist(),
    }


def main() -> None:
    if torch is None:
        raise SystemExit(
            f"PyTorch is required for V5. Install with: pip install torch\nOriginal import error: {_TORCH_IMPORT_ERROR}"
        )

    parser = argparse.ArgumentParser(
        description="MAZ Boss MAXED V5 (global backbone + league adapters + experts)."
    )
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--league-id", type=int, default=None)
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--min-games", type=int, default=120)
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--train-all-completed", action="store_true")
    parser.add_argument("--wf-start-train", type=int, default=80)
    parser.add_argument("--wf-step", type=int, default=20)
    parser.add_argument("--seq-len", type=int, default=10)
    parser.add_argument("--emb-dim", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=80)
    parser.add_argument("--n-experts", type=int, default=4)
    parser.add_argument("--adapter-dim", type=int, default=24)
    parser.add_argument("--cross-heads", type=int, default=4)
    parser.add_argument("--rating-k", type=float, default=0.06)
    parser.add_argument("--rating-home-adv", type=float, default=2.0)
    parser.add_argument("--rating-scale", type=float, default=7.0)
    parser.add_argument("--epochs", type=int, default=32)
    parser.add_argument("--global-pretrain", action="store_true")
    parser.add_argument("--global-pretrain-epochs", type=int, default=24)
    parser.add_argument("--finetune-epochs", type=int, default=14)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--finetune-lr", type=float, default=3e-4)
    parser.add_argument("--ensemble-seeds", type=str, default="42,1337,9001")
    parser.add_argument("--winner-loss-weight", type=float, default=1.0)
    parser.add_argument("--score-loss-weight", type=float, default=0.30)
    parser.add_argument("--ranking-loss-weight", type=float, default=0.12)
    parser.add_argument("--embedding-l2-weight", type=float, default=0.0005)
    parser.add_argument("--var-reg-weight", type=float, default=0.002)
    parser.add_argument("--expert-balance-weight", type=float, default=0.01)
    parser.add_argument("--confidence-variance-threshold", type=float, default=40.0)
    parser.add_argument("--recency-half-life-days", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-v5-models", action="store_true")
    parser.add_argument("--save-global-pretrained", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=None)
    args = parser.parse_args()

    auto_log_file: Optional[str] = args.log_file
    if not auto_log_file:
        auto_log_file = f"artifacts/maz_maxed_v5_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _setup_logging(args.log_level, auto_log_file)
    LOG.info("Starting MAZ MAXED V5 run")
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
    if args.train_all_completed and args.all_leagues and FRIENDLIES_LEAGUE_ID in leagues and FRIENDLIES_LEAGUE_ID not in keep_ids:
        n_friendlies = int((df_all["league_id"] == FRIENDLIES_LEAGUE_ID).sum())
        if n_friendlies >= 60:
            keep_ids.append(FRIENDLIES_LEAGUE_ID)
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
        df_pre = pd.concat(pre_parts, axis=0).sort_values(["date_event", "event_id"]).reset_index(drop=True)
        if len(df_pre) >= 100:
            LOG.info(
                "[V5] Global pretraining start: rows=%s teams=%s epochs=%s seeds=%s",
                len(df_pre),
                len(global_team_to_idx),
                args.global_pretrain_epochs,
                len(args._ensemble_seeds),
            )
            league_stats_g = build_league_score_stats(df_pre)
            league_env_stats_g = build_league_environment_stats(df_pre, args.rating_home_adv)
            reg_map_g = detect_regime_map_by_league(df_pre)
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
            regime_idx_g = np.array(
                [reg_map_g.get(int(lid), ("balanced_competitive", 1, 1.0))[1] for lid in league_ids_g],
                dtype=np.int64,
            )
            bundle_g = _make_bundle(
                home_seq_g,
                away_seq_g,
                home_idx_g,
                away_idx_g,
                home_opp_g,
                away_opp_g,
                league_idx_g,
                regime_idx_g,
                y_g,
                build_recency_weights(df_pre, args.recency_half_life_days),
            )
            for s in args._ensemble_seeds:
                torch.manual_seed(int(s) + 7777)
                model_g = V5Model(
                    n_teams=len(global_team_to_idx),
                    n_leagues=len(global_league_to_idx),
                    emb_dim=args.emb_dim,
                    seq_dim=int(home_seq_g.shape[-1]),
                    hidden_dim=args.hidden_dim,
                    n_experts=args.n_experts,
                    adapter_dim=args.adapter_dim,
                    cross_heads=args.cross_heads,
                )
                opt_g = torch.optim.AdamW(model_g.parameters(), lr=args.lr, weight_decay=1e-4)
                _train_model(model_g, bundle_g, args.global_pretrain_epochs, args.batch_size, opt_g, args)
                pretrained_by_seed[int(s)] = model_g.state_dict()
                if args.save_global_pretrained:
                    out_dir = Path("artifacts")
                    out_dir.mkdir(exist_ok=True)
                    gp = out_dir / f"global_pretrained_v5_seed_{int(s)}.pt"
                    torch.save(model_g.state_dict(), gp)
                LOG.info("[V5] Global pretraining done for seed=%s", int(s))

    report: Dict[str, Any] = {
        "version": V5_VERSION,
        "generated_at": datetime.now().isoformat(),
        "config": {
            "architecture": V5_ARCHITECTURE,
            "min_games": args.min_games,
            "holdout_ratio": args.holdout_ratio,
            "walk_forward": bool(args.walk_forward),
            "train_all_completed": bool(args.train_all_completed),
            "wf_start_train": args.wf_start_train,
            "wf_step": args.wf_step,
            "seq_len": args.seq_len,
            "emb_dim": args.emb_dim,
            "hidden_dim": args.hidden_dim,
            "n_experts": args.n_experts,
            "adapter_dim": args.adapter_dim,
            "cross_heads": args.cross_heads,
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
            "ranking_loss_weight": args.ranking_loss_weight,
            "embedding_l2_weight": args.embedding_l2_weight,
            "var_reg_weight": args.var_reg_weight,
            "expert_balance_weight": args.expert_balance_weight,
            "confidence_variance_threshold": args.confidence_variance_threshold,
            "recency_half_life_days": args.recency_half_life_days,
            "save_v5_models": bool(args.save_v5_models),
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
        n_test = len(te_df)
        home_seq, away_seq, norm_stats = normalize_sequences(home_seq, away_seq, n_train)
        y_scaled = scale_score_targets(y_raw, league_ids_row, league_stats)
        regime_name, regime_idx, regime_unc_mult = detect_regime(tr_df)
        regime_idx_tr = np.full((n_train,), int(regime_idx), dtype=np.int64)
        regime_idx_te = np.full((n_test,), int(regime_idx), dtype=np.int64)
        train_bundle = _make_bundle(
            home_seq[:n_train],
            away_seq[:n_train],
            home_idx[:n_train],
            away_idx[:n_train],
            home_opp_idx[:n_train],
            away_opp_idx[:n_train],
            league_idx[:n_train],
            regime_idx_tr,
            y_scaled[:n_train],
            build_recency_weights(tr_df, args.recency_half_life_days),
        )
        test_bundle = _make_bundle(
            home_seq[n_train:],
            away_seq[n_train:],
            home_idx[n_train:],
            away_idx[n_train:],
            home_opp_idx[n_train:],
            away_opp_idx[n_train:],
            league_idx[n_train:],
            regime_idx_te,
            y_scaled[n_train:],
            None,
        )

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
        expert_usages: List[List[float]] = []
        saved_seed_models: List[str] = []

        for s in args._ensemble_seeds:
            torch.manual_seed(int(s) + int(lid))
            model = V5Model(
                n_teams=len(global_team_to_idx),
                n_leagues=len(global_league_to_idx),
                emb_dim=args.emb_dim,
                seq_dim=int(home_seq.shape[-1]),
                hidden_dim=args.hidden_dim,
                n_experts=args.n_experts,
                adapter_dim=args.adapter_dim,
                cross_heads=args.cross_heads,
            )
            if int(s) in pretrained_by_seed:
                model.load_state_dict(pretrained_by_seed[int(s)], strict=True)
            use_lr = float(args.finetune_lr if args.global_pretrain else args.lr)
            use_epochs = int(args.finetune_epochs if args.global_pretrain else args.epochs)
            opt = torch.optim.AdamW(model.parameters(), lr=use_lr, weight_decay=1e-4)
            _train_model(model, train_bundle, use_epochs, args.batch_size, opt, args)

            pred_tr = _predict_bundle(model, train_bundle, league_ids_row[:n_train], league_stats, regime_unc_mult)
            if n_test > 0:
                pred_te = _predict_bundle(model, test_bundle, league_ids_row[n_train:], league_stats, regime_unc_mult)
            else:
                pred_te = {
                    "p_cls": np.zeros((0,), dtype=float),
                    "mu": np.zeros((0, 2), dtype=float),
                    "var": np.zeros((0, 2), dtype=float),
                    "rho": np.zeros((0,), dtype=float),
                    "alpha": np.zeros((0,), dtype=float),
                    "p_sd": np.zeros((0,), dtype=float),
                    "margin_var": np.zeros((0,), dtype=float),
                    "emb_norm_mean": pred_tr["emb_norm_mean"],
                    "emb_norm_std": pred_tr["emb_norm_std"],
                    "expert_usage": pred_tr["expert_usage"],
                }
            ens_p_cls_tr.append(pred_tr["p_cls"])
            ens_p_cls_te.append(pred_te["p_cls"])
            ens_p_sd_tr.append(pred_tr["p_sd"])
            ens_p_sd_te.append(pred_te["p_sd"])
            ens_proxy_prob_tr.append(np.clip(0.5 * (pred_tr["p_cls"] + pred_tr["p_sd"]), 1e-6, 1.0 - 1e-6))
            ens_proxy_prob_te.append(np.clip(0.5 * (pred_te["p_cls"] + pred_te["p_sd"]), 1e-6, 1.0 - 1e-6) if n_test > 0 else np.zeros((0,), dtype=float))
            ens_mu_tr.append(pred_tr["mu"])
            ens_mu_te.append(pred_te["mu"])
            ens_var_tr.append(pred_tr["var"])
            ens_var_te.append(pred_te["var"])
            ens_margin_var_tr.append(pred_tr["margin_var"])
            ens_margin_var_te.append(pred_te["margin_var"])
            ens_alpha_tr.append(pred_tr["alpha"])
            ens_alpha_te.append(pred_te["alpha"])
            emb_norm_means.append(pred_tr["emb_norm_mean"])
            emb_norm_stds.append(pred_tr["emb_norm_std"])
            expert_usages.append(pred_tr["expert_usage"])
            if save_models and args.save_v5_models:
                out_dir = Path("artifacts")
                out_dir.mkdir(exist_ok=True)
                model_file = out_dir / f"league_{lid}_model_maz_maxed_v5_seed_{int(s)}.pt"
                torch.save(model.state_dict(), model_file)
                saved_seed_models.append(str(model_file))

        p_cls_tr = np.mean(np.vstack(ens_p_cls_tr), axis=0)
        p_cls_te = np.mean(np.vstack(ens_p_cls_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        p_sd_tr = np.mean(np.vstack(ens_p_sd_tr), axis=0)
        p_sd_te = np.mean(np.vstack(ens_p_sd_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        proxy_prob_tr = np.mean(np.vstack(ens_proxy_prob_tr), axis=0)
        proxy_prob_te = np.mean(np.vstack(ens_proxy_prob_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        prob_std_tr = np.std(np.vstack(ens_proxy_prob_tr), axis=0) if len(ens_proxy_prob_tr) > 1 else np.zeros_like(proxy_prob_tr)
        prob_std_te = (
            np.std(np.vstack(ens_proxy_prob_te), axis=0)
            if (n_test > 0 and len(ens_proxy_prob_te) > 1)
            else np.zeros_like(proxy_prob_te)
        )
        mu_tr = np.mean(np.stack(ens_mu_tr, axis=0), axis=0)
        mu_te = np.mean(np.stack(ens_mu_te, axis=0), axis=0) if n_test > 0 else np.zeros((0, 2), dtype=float)
        var_tr = np.mean(np.stack(ens_var_tr, axis=0), axis=0)
        var_te = np.mean(np.stack(ens_var_te, axis=0), axis=0) if n_test > 0 else np.zeros((0, 2), dtype=float)
        margin_var_tr = np.mean(np.vstack(ens_margin_var_tr), axis=0)
        margin_var_te = np.mean(np.vstack(ens_margin_var_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        a_tr = np.mean(np.vstack(ens_alpha_tr), axis=0)
        a_te = np.mean(np.vstack(ens_alpha_te), axis=0) if n_test > 0 else np.zeros((0,), dtype=float)
        margin_var_threshold = _quantile_or_fallback(margin_var_tr, 0.85, args.confidence_variance_threshold)
        prob_std_threshold = _quantile_or_fallback(prob_std_tr, 0.85, DEFAULT_PROB_STD_THRESHOLD)
        probability_blender = fit_probability_blender(p_cls_tr, p_sd_tr, y_raw[:n_train, 0].astype(int))
        p_blend_tr = apply_probability_blender(probability_blender, p_cls_tr, p_sd_tr)
        p_blend_te = apply_probability_blender(probability_blender, p_cls_te, p_sd_te) if n_test > 0 else np.zeros((0,), dtype=float)
        cal = fit_calibrator(
            p_blend_tr,
            y_raw[:n_train, 0].astype(int),
            prob_std=prob_std_tr,
            margin_var=margin_var_tr,
        )
        p_fin_tr = apply_calibrator(cal, p_blend_tr, prob_std_tr, margin_var_tr)
        p_fin_te = apply_calibrator(cal, p_blend_te, prob_std_te, margin_var_te) if n_test > 0 else np.zeros((0,), dtype=float)

        m_train = evaluate(
            p_fin_tr,
            mu_tr[:, 0],
            mu_tr[:, 1],
            y_raw[:n_train, 0].astype(int),
            y_raw[:n_train, 1],
            y_raw[:n_train, 2],
        )
        if n_test > 0:
            y_te_np = y_raw[n_train:]
            m = evaluate(
                p_fin_te,
                mu_te[:, 0],
                mu_te[:, 1],
                y_te_np[:, 0].astype(int),
                y_te_np[:, 1],
                y_te_np[:, 2],
            )
            low_conf_mask = (margin_var_te > margin_var_threshold) | (prob_std_te > prob_std_threshold)
            high_conf_mask = ~low_conf_mask
            hc_total = int(np.sum(high_conf_mask))
            hc_correct = int(
                np.sum(
                    (p_fin_te[high_conf_mask] >= 0.5).astype(int)
                    == y_te_np[:, 0].astype(int)[high_conf_mask]
                )
            ) if hc_total > 0 else 0
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
            "architecture": V5_ARCHITECTURE,
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
            "expert_usage_avg": np.mean(np.array(expert_usages, dtype=float), axis=0).tolist() if expert_usages else None,
            "saved_seed_models": saved_seed_models,
            "team_to_idx": team_to_idx,
            "league_stats": league_stats,
            "league_env_stats": league_env_stats,
            "normalization_stats": norm_stats,
        }
        if save_models and args.save_v5_models:
            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)
            meta_file = out_dir / f"league_{lid}_model_maz_maxed_v5_meta.pkl"
            with meta_file.open("wb") as f:
                pickle.dump(
                    {
                        "version": V5_VERSION,
                        "architecture": V5_ARCHITECTURE,
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
                            "seq_dim": int(home_seq.shape[-1]),
                            "n_experts": int(args.n_experts),
                            "adapter_dim": int(args.adapter_dim),
                            "cross_heads": int(args.cross_heads),
                            "rating_k": float(args.rating_k),
                            "rating_home_adv": float(args.rating_home_adv),
                            "rating_scale": float(args.rating_scale),
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
                        "expert_usage_avg": out["expert_usage_avg"],
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
                "architecture": out.get("architecture", V5_ARCHITECTURE),
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
                "expert_usage_avg": out.get("expert_usage_avg"),
                "train_metrics": out["train_metrics"].__dict__ if out.get("train_metrics") is not None else None,
            }
            if args.save_v5_models and out.get("saved_seed_models"):
                payload["saved_seed_models"] = out["saved_seed_models"]
                payload["saved_meta"] = out.get("saved_meta")
            report["leagues"][str(lid)] = payload
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
                    LOG.warning("[%s] chunk %s/%s skipped: %s", name, chunk_i, total_chunks, out.get("reason", "split failed"))
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
            if args.save_v5_models:
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
                "architecture": V5_ARCHITECTURE,
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
                "expert_usage_avg": last_ok[2].get("expert_usage_avg"),
                "metrics": m_agg.__dict__,
            }
            if args.save_v5_models and save_out.get("saved_seed_models"):
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
            m = out["metrics"]
            report["summary"]["tested"] += 1
            payload = {
                "name": name,
                "status": "tested",
                "mode": "single_holdout",
                "train_rows": int(out["train_rows"]),
                "test_rows": int(out["test_rows"]),
                "ensemble_size": int(len(args._ensemble_seeds)),
                "global_pretrained": bool(args.global_pretrain and len(pretrained_by_seed) > 0),
                "architecture": out.get("architecture", V5_ARCHITECTURE),
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
                "expert_usage_avg": out.get("expert_usage_avg"),
                "metrics": m.__dict__,
            }
            if args.save_v5_models and out.get("saved_seed_models"):
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

    LOG.info("=== MAZ MAXED V5 Summary ===")
    LOG.info("%s", json.dumps(report["summary"], indent=2))
    LOG.info("=== MAZ MAXED V5 Final League Recap ===")
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
        out_file = out_dir / f"maz_maxed_v5_{mode_tag}_{stamp}.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        LOG.info("Report saved: %s", out_file)
        if args.walk_forward:
            latest_eval = out_dir / "maz_maxed_v5_metrics_latest.json"
            latest_eval.write_text(json.dumps(report, indent=2), encoding="utf-8")
            LOG.info("Updated latest eval metrics: %s", latest_eval)
        if args.train_all_completed:
            latest_prod = out_dir / "maz_maxed_v5_prod_latest.json"
            latest_prod.write_text(json.dumps(report, indent=2), encoding="utf-8")
            LOG.info("Updated latest production report: %s", latest_prod)


if __name__ == "__main__":
    main()
