"""Killer neural architecture — 4 experts + sparse router + score-first H/D/A."""

from __future__ import annotations

from typing import Dict

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception as e:  # pragma: no cover
    torch = None
    nn = None  # type: ignore
    F = None
    _TORCH_ERR = e

from .config import EMB_DIM, HIDDEN_DIM, N_EXPERTS, SEQ_DIM, STATE_DIM


def _require_torch() -> None:
    if torch is None or nn is None:
        raise ImportError(f"PyTorch required for Killer: {_TORCH_ERR}")


class TimescaleEncoder(nn.Module):
    """GRU encoder for a single timescale history."""

    def __init__(self, seq_dim: int, hidden: int):
        super().__init__()
        self.rnn = nn.GRU(seq_dim, hidden, batch_first=True)
        self.attn = nn.Linear(hidden, 1)

    def forward(self, seq: torch.Tensor) -> torch.Tensor:
        out, h = self.rnn(seq)
        logits = self.attn(out).squeeze(-1)
        valid = seq.abs().sum(dim=-1) > 1e-8
        logits = logits.masked_fill(~valid, -1e9)
        w = torch.softmax(logits, dim=1)
        ctx = torch.bmm(w.unsqueeze(1), out).squeeze(1)
        has = valid.any(dim=1).unsqueeze(1)
        return torch.where(has, ctx, h[-1])


class PatternEncoder(nn.Module):
    """Lightweight temporal self-attention (V5-pattern expert style)."""

    def __init__(self, seq_dim: int, hidden: int, n_heads: int = 4):
        super().__init__()
        self.proj = nn.Linear(seq_dim, hidden)
        self.attn = nn.MultiheadAttention(hidden, n_heads, batch_first=True, dropout=0.1)
        self.ff = nn.Sequential(
            nn.Linear(hidden, hidden * 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden * 2, hidden),
        )
        self.norm1 = nn.LayerNorm(hidden)
        self.norm2 = nn.LayerNorm(hidden)

    def forward(self, seq: torch.Tensor) -> torch.Tensor:
        x = self.proj(seq)
        key_padding = seq.abs().sum(dim=-1) <= 1e-8
        # If all padded, unmask one step to avoid NaNs
        all_pad = key_padding.all(dim=1)
        if all_pad.any():
            key_padding = key_padding.clone()
            key_padding[all_pad, -1] = False
        attn_out, _ = self.attn(x, x, x, key_padding_mask=key_padding)
        x = self.norm1(x + attn_out)
        x = self.norm2(x + self.ff(x))
        valid = ~key_padding
        w = valid.float()
        w = w / w.sum(dim=1, keepdim=True).clamp_min(1.0)
        return torch.bmm(w.unsqueeze(1), x).squeeze(1)


class CompetitionAdapter(nn.Module):
    def __init__(self, n_leagues: int, dim: int):
        super().__init__()
        self.scale = nn.Embedding(n_leagues, dim)
        self.shift = nn.Embedding(n_leagues, dim)
        nn.init.ones_(self.scale.weight)
        nn.init.zeros_(self.shift.weight)

    def forward(self, x: torch.Tensor, league_idx: torch.Tensor) -> torch.Tensor:
        return x * self.scale(league_idx) + self.shift(league_idx)


class KillerModel(nn.Module):
    """
    Global rugby backbone + multi-timescale team state + 4 experts + sparse router
    + competition adapter + score distribution + 3-way H/D/A + consistency fusion.
    """

    def __init__(
        self,
        n_teams: int,
        n_leagues: int,
        *,
        emb_dim: int = EMB_DIM,
        state_dim: int = STATE_DIM,
        hidden_dim: int = HIDDEN_DIM,
        seq_dim: int = SEQ_DIM,
        rating_dim: int = 20,
        score_dim: int = 16,
        rest_dim: int = 4,
        dropout: float = 0.15,
    ):
        _require_torch()
        super().__init__()
        self.n_experts = N_EXPERTS
        self.team_emb = nn.Embedding(n_teams, emb_dim, padding_idx=0)
        self.league_emb = nn.Embedding(n_leagues, emb_dim, padding_idx=0)

        self.fast_enc = TimescaleEncoder(seq_dim, hidden_dim)
        self.med_enc = TimescaleEncoder(seq_dim, hidden_dim)
        self.slow_enc = TimescaleEncoder(seq_dim, hidden_dim)
        self.state_fuse = nn.Sequential(
            nn.Linear(hidden_dim * 3 + emb_dim, state_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(state_dim, state_dim),
        )

        # Cross-team reasoning
        self.cross_q = nn.Linear(state_dim, state_dim)
        self.cross_k = nn.Linear(state_dim, state_dim)
        self.cross_v = nn.Linear(state_dim, state_dim)
        self.matchup_mlp = nn.Sequential(
            nn.Linear(state_dim * 4 + rest_dim + emb_dim, state_dim * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(state_dim * 2, state_dim),
        )

        # Expert A — V4 stability (GRU path already in timescales; compress matchup)
        self.expert_stability = nn.Sequential(
            nn.Linear(state_dim, state_dim),
            nn.GELU(),
            nn.Linear(state_dim, state_dim),
        )
        # Expert B — V5 pattern on medium history concat
        self.pattern_home = PatternEncoder(seq_dim, hidden_dim)
        self.pattern_away = PatternEncoder(seq_dim, hidden_dim)
        self.expert_pattern = nn.Sequential(
            nn.Linear(hidden_dim * 2 + state_dim, state_dim),
            nn.GELU(),
            nn.Linear(state_dim, state_dim),
        )
        # Expert C — rating intelligence
        self.expert_rating = nn.Sequential(
            nn.Linear(rating_dim + state_dim, state_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(state_dim, state_dim),
        )
        # Expert D — score dynamics
        self.expert_score = nn.Sequential(
            nn.Linear(score_dim + state_dim, state_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(state_dim, state_dim),
        )

        self.router = nn.Sequential(
            nn.Linear(state_dim + emb_dim, state_dim),
            nn.GELU(),
            nn.Linear(state_dim, N_EXPERTS),
        )
        self.adapter = CompetitionAdapter(n_leagues, state_dim)

        # Score distribution (bivariate Gaussian params)
        self.score_mu = nn.Linear(state_dim, 2)
        self.score_logvar = nn.Linear(state_dim, 2)
        self.score_rho = nn.Linear(state_dim, 1)
        # Direct H/D/A
        self.hda_head = nn.Linear(state_dim, 3)
        # Consistency fusion: combine implied-from-scores + direct
        self.fuse = nn.Sequential(
            nn.Linear(6, 16),
            nn.GELU(),
            nn.Linear(16, 3),
        )
        self.league_home_bias = nn.Embedding(n_leagues, 1)

    def _team_state(
        self,
        team_idx: torch.Tensor,
        fast: torch.Tensor,
        med: torch.Tensor,
        slow: torch.Tensor,
    ) -> torch.Tensor:
        emb = self.team_emb(team_idx)
        f = self.fast_enc(fast)
        m = self.med_enc(med)
        s = self.slow_enc(slow)
        return self.state_fuse(torch.cat([f, m, s, emb], dim=-1))

    def _cross(self, home: torch.Tensor, away: torch.Tensor) -> torch.Tensor:
        q = self.cross_q(home)
        k = self.cross_k(away)
        v = self.cross_v(away)
        scale = (home.shape[-1] ** 0.5)
        attn = torch.softmax((q * k).sum(-1, keepdim=True) / scale, dim=-1)
        # Scalar attention is degenerate; use bilinear style interaction instead
        interact = torch.sigmoid((q * k).sum(-1, keepdim=True) / scale) * v
        # Also reverse direction
        q2 = self.cross_q(away)
        k2 = self.cross_k(home)
        v2 = self.cross_v(home)
        interact2 = torch.sigmoid((q2 * k2).sum(-1, keepdim=True) / scale) * v2
        return torch.cat([home, away, interact, interact2], dim=-1)

    def forward(
        self,
        home_idx: torch.Tensor,
        away_idx: torch.Tensor,
        league_idx: torch.Tensor,
        home_fast: torch.Tensor,
        away_fast: torch.Tensor,
        home_med: torch.Tensor,
        away_med: torch.Tensor,
        home_long: torch.Tensor,
        away_long: torch.Tensor,
        rating_feats: torch.Tensor,
        score_feats: torch.Tensor,
        rest_feats: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        h_state = self._team_state(home_idx, home_fast, home_med, home_long)
        a_state = self._team_state(away_idx, away_fast, away_med, away_long)
        cross = self._cross(h_state, a_state)
        leg = self.league_emb(league_idx)
        matchup = self.matchup_mlp(torch.cat([cross, rest_feats, leg], dim=-1))

        e0 = self.expert_stability(matchup)
        ph = self.pattern_home(home_med)
        pa = self.pattern_away(away_med)
        e1 = self.expert_pattern(torch.cat([ph, pa, matchup], dim=-1))
        e2 = self.expert_rating(torch.cat([rating_feats, matchup], dim=-1))
        e3 = self.expert_score(torch.cat([score_feats, matchup], dim=-1))
        experts = torch.stack([e0, e1, e2, e3], dim=1)  # [B, 4, D]

        gate_logits = self.router(torch.cat([matchup, leg], dim=-1))
        gate = torch.softmax(gate_logits, dim=-1)  # [B, 4]
        mixed = (experts * gate.unsqueeze(-1)).sum(dim=1)
        z = self.adapter(mixed, league_idx)

        bias = self.league_home_bias(league_idx).squeeze(-1)
        mu = self.score_mu(z)
        mu = torch.stack([mu[:, 0] + bias, mu[:, 1]], dim=1)
        logvar = self.score_logvar(z)
        rho_logit = self.score_rho(z).squeeze(-1)
        hda_logits = self.hda_head(z)
        hda_logits = hda_logits.clone()
        hda_logits[:, 2] = hda_logits[:, 2] + bias  # home class

        # Implied H/D/A from margin distribution (independent approx)
        margin_mu = mu[:, 0] - mu[:, 1]
        margin_var = logvar[:, 0].exp() + logvar[:, 1].exp()
        margin_sd = margin_var.clamp_min(1e-4).sqrt()
        # P(home win) ≈ Φ(margin_mu / sd); draw band ±0.5 roughly via density mass
        z_home = margin_mu / margin_sd
        z_draw_lo = (margin_mu - 0.5) / margin_sd
        z_draw_hi = (margin_mu + 0.5) / margin_sd
        # Use sigmoid surrogates for differentiability
        p_home_impl = torch.sigmoid(z_home)
        p_draw_impl = (torch.sigmoid(z_draw_hi) - torch.sigmoid(z_draw_lo)).clamp(0.01, 0.3)
        p_away_impl = (1.0 - p_home_impl - 0.5 * p_draw_impl).clamp(0.01, 0.98)
        # Renormalize implied
        impl = torch.stack([p_away_impl, p_draw_impl, p_home_impl], dim=-1)
        impl = impl / impl.sum(dim=-1, keepdim=True).clamp_min(1e-6)
        direct = torch.softmax(hda_logits, dim=-1)
        fused_logits = self.fuse(torch.cat([impl, direct], dim=-1))
        fused = torch.softmax(fused_logits, dim=-1)

        return {
            "score_mu": mu,
            "score_logvar": logvar,
            "score_rho_logit": rho_logit,
            "hda_logits": hda_logits,
            "hda_direct": direct,
            "hda_implied": impl,
            "hda_fused": fused,
            "hda_fused_logits": fused_logits,
            "gate": gate,
            "gate_logits": gate_logits,
            "margin_mu": margin_mu,
            "margin_sd": margin_sd,
            "latent": z,
        }
