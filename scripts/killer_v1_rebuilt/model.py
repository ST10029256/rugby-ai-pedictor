"""V4-shaped GRU + optional FiLM + residual score head."""

from __future__ import annotations

from typing import Dict

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import DROPOUT, EMB_DIM, GRU_HIDDEN, TRUNK_HIDDEN, TRUNK_OUT


class RebuiltModel(nn.Module):
    def __init__(
        self,
        n_teams: int,
        n_leagues: int,
        seq_dim: int,
        *,
        use_film: bool,
        residual_scores: bool,
        use_draw: bool,
    ):
        super().__init__()
        self.use_film = use_film
        self.residual_scores = residual_scores
        self.use_draw = use_draw
        self.team_emb = nn.Embedding(n_teams, EMB_DIM, padding_idx=0)
        self.rnn = nn.GRU(seq_dim, GRU_HIDDEN, batch_first=True)
        self.attn = nn.Linear(GRU_HIDDEN, 1)
        match_in = (GRU_HIDDEN + EMB_DIM) * 4 + 1 + 8  # H,A,|H-A|,H*A,dot,scalars
        self.mlp = nn.Sequential(
            nn.Linear(match_in, TRUNK_HIDDEN),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(TRUNK_HIDDEN, TRUNK_OUT),
            nn.GELU(),
        )
        if use_film:
            self.gamma = nn.Embedding(n_leagues, TRUNK_OUT)
            self.beta = nn.Embedding(n_leagues, TRUNK_OUT)
            nn.init.ones_(self.gamma.weight)
            nn.init.zeros_(self.beta.weight)
        self.winner = nn.Linear(TRUNK_OUT, 1)
        self.score = nn.Linear(TRUNK_OUT, 2)
        nn.init.zeros_(self.score.weight)
        if residual_scores:
            nn.init.zeros_(self.score.bias)
        else:
            self.score.bias.data = torch.tensor([24.0, 20.0])
        self.home_bias = nn.Embedding(n_leagues, 1)
        if use_draw:
            self.draw_beta = nn.Parameter(torch.zeros(1))

    def encode(self, idx: torch.Tensor, seq: torch.Tensor) -> torch.Tensor:
        out, h = self.rnn(seq)
        logits = self.attn(out).squeeze(-1)
        valid = seq.abs().sum(-1) > 1e-8
        logits = logits.masked_fill(~valid, -1e9)
        w = torch.softmax(logits, dim=1)
        ctx = torch.bmm(w.unsqueeze(1), out).squeeze(1)
        has = valid.any(1, keepdim=True)
        temporal = torch.where(has, ctx, h[-1])
        return torch.cat([temporal, self.team_emb(idx)], dim=-1)

    def forward(
        self,
        home_idx, away_idx, league_idx,
        home_seq, away_seq, scalars, mu0, pi_draw,
    ) -> Dict[str, torch.Tensor]:
        H = self.encode(home_idx, home_seq)
        A = self.encode(away_idx, away_seq)
        x = torch.cat([H, A, (H - A).abs(), H * A, (H * A).sum(-1, keepdim=True), scalars], dim=-1)
        z = self.mlp(x)
        if self.use_film:
            z = z * self.gamma(league_idx) + self.beta(league_idx)
        bias = self.home_bias(league_idx).squeeze(-1)
        win_logit = self.winner(z).squeeze(-1) + bias
        delta = self.score(z)
        if self.residual_scores:
            mu = mu0 + delta
        else:
            mu = delta
        p_nd = torch.sigmoid(win_logit)
        # score-implied non-draw home from margin / 8 (fixed residual scale)
        p_sc = torch.sigmoid((mu[:, 0] - mu[:, 1]) / 8.0)
        return {
            "win_logit": win_logit,
            "p_direct": p_nd,
            "p_score": p_sc,
            "mu": mu,
            "delta": delta,
            "draw_beta": self.draw_beta if self.use_draw else win_logit.new_zeros(1),
            "pi_draw": pi_draw,
        }


def blend_hda(
    p_direct: torch.Tensor,
    p_score: torch.Tensor,
    mu: torch.Tensor,
    pi_draw: torch.Tensor,
    draw_beta: torch.Tensor,
    *,
    alpha: float,
    use_draw: bool,
) -> torch.Tensor:
    a = float(min(0.90, max(0.65, alpha)))
    p_home_nd = a * p_direct + (1.0 - a) * p_score
    if use_draw:
        closeness = -(mu[:, 0] - mu[:, 1]).abs() / 10.0
        logit_pi = torch.logit(pi_draw.clamp(1e-4, 0.3))
        p_draw = torch.sigmoid(logit_pi + draw_beta.to(mu.device) * closeness).clamp(0.002, 0.25)
    else:
        p_draw = torch.zeros_like(p_home_nd)
    p_home = (1.0 - p_draw) * p_home_nd
    p_away = (1.0 - p_draw) * (1.0 - p_home_nd)
    p = torch.stack([p_away, p_draw, p_home], dim=-1)
    return p / p.sum(-1, keepdim=True).clamp_min(1e-8)
