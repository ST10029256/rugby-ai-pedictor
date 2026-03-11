"""
V5 runtime predictor for Cloud Functions inference.

Loads MAZ MAXED V5 seed checkpoints (.pt) plus league meta (.pkl)
and reuses the proven V4 runtime serving path around a stronger model.
"""

from __future__ import annotations

import logging
import pickle
from typing import Any, Dict, Tuple

import numpy as np
from prediction.sportdevs_client import SportDevsClient

from .v4_runtime import V4RuntimePredictor, _coerce_vector

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


def _safe_num_heads(hidden_dim: int, requested_heads: int) -> int:
    for heads in (requested_heads, 8, 4, 2, 1):
        if heads > 0 and hidden_dim % heads == 0:
            return heads
    return 1


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    w = mask.float().unsqueeze(-1)
    denom = torch.clamp(torch.sum(w, dim=1), min=1.0)
    return torch.sum(values * w, dim=1) / denom


class V5Model(nn.Module):
    """Runtime mirror of the V5 training architecture."""

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
            [h_repr, a_repr, torch.abs(h_repr - a_repr), h_repr * a_repr, ctx],
            dim=1,
        )
        expert_weights = torch.softmax(self.expert_gate(match_x), dim=1)
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


class V5RuntimePredictor(V4RuntimePredictor):
    """Serve V5 ensemble directly from .pt checkpoints."""

    def __init__(
        self,
        v5_assets: Dict[str, Any],
        db_path: str = "data.sqlite",
        sportdevs_api_key: str = "",
        **_: Any,
    ):
        if torch is None:
            raise RuntimeError(
                f"PyTorch is required for V5 runtime inference: {_TORCH_IMPORT_ERROR}"
            )
        self.db_path = db_path
        self.v5_assets = v5_assets
        self.sportdevs_client = SportDevsClient(sportdevs_api_key or "")

        with open(v5_assets["meta_path"], "rb") as f:
            self.meta: Dict[str, Any] = pickle.load(f)

        self.architecture = str(self.meta.get("architecture", "v5"))
        self.league_id = int(self.meta["league_id"])
        self.league_name = str(self.meta.get("league_name", f"League {self.league_id}"))
        self.team_to_idx = {
            int(k): int(v) for k, v in (self.meta.get("team_to_idx") or {}).items()
        }
        self.league_to_idx = {
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
        self.hidden_dim = int(cfg.get("hidden_dim", 80))
        self.seq_dim = int(cfg.get("seq_dim", 11))
        self.n_experts = int(cfg.get("n_experts", 4))
        self.adapter_dim = int(cfg.get("adapter_dim", 24))
        self.cross_heads = int(cfg.get("cross_heads", 4))
        self.rating_k = float(cfg.get("rating_k", 0.06))
        self.rating_home_adv = float(cfg.get("rating_home_adv", 2.0))
        self.rating_scale = float(cfg.get("rating_scale", 7.0))
        norm = self.meta.get("normalization_stats") or {}
        self.norm_mean = _coerce_vector(norm.get("mean"), self.seq_dim, 0.0)
        self.norm_std = _coerce_vector(norm.get("std"), self.seq_dim, 1.0)
        self.norm_std = np.where(self.norm_std < 1e-6, 1.0, self.norm_std)
        self.calibrator = self.meta.get("calibrator")
        self.probability_blender = self.meta.get("probability_blender")
        self.regime_name = str(self.meta.get("regime_name", "balanced_competitive"))
        self.regime_idx = int(self.meta.get("regime_idx", 1))
        self.regime_uncertainty_multiplier = float(
            self.meta.get("regime_uncertainty_multiplier", 1.0)
        )
        self.confidence_margin_variance_threshold = float(
            self.meta.get("confidence_margin_variance_threshold", 40.0)
        )
        self.confidence_prob_std_threshold = float(
            self.meta.get("confidence_prob_std_threshold", 0.06)
        )

        self.models = []
        for seed_path in v5_assets.get("seed_model_paths", []):
            model = V5Model(
                n_teams=max(1, len(self.team_to_idx)),
                n_leagues=max(1, len(self.league_to_idx)),
                emb_dim=self.emb_dim,
                seq_dim=self.seq_dim,
                hidden_dim=self.hidden_dim,
                n_experts=self.n_experts,
                adapter_dim=self.adapter_dim,
                cross_heads=self.cross_heads,
            )
            state = torch.load(seed_path, map_location="cpu")
            model.load_state_dict(state, strict=True)
            model.eval()
            self.models.append(model)
        if not self.models:
            raise RuntimeError(f"No V5 seed models loaded for league {self.league_id}")

        logger.info(
            "Loaded V5 runtime ensemble for league %s (%s) with %s seed models",
            self.league_id,
            self.league_name,
            len(self.models),
        )

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        league_id: int,
        match_date: str,
        match_id: Any = None,
    ) -> Dict[str, Any]:
        out = super().predict_match(
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            match_date=match_date,
            match_id=match_id,
        )
        out["model_type"] = "v5_runtime"
        out["model_family"] = "v5"
        metrics = dict(out.get("additional_metrics") or {})
        metrics["architecture"] = self.architecture
        out["additional_metrics"] = metrics
        return out
