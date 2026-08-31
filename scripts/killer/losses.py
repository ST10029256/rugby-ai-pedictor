"""Robust multi-task losses for Killer."""

from __future__ import annotations

from typing import Dict, Optional

import torch
import torch.nn.functional as F


def bivariate_nll(
    y_h: torch.Tensor,
    y_a: torch.Tensor,
    mu: torch.Tensor,
    logvar: torch.Tensor,
    rho_logit: torch.Tensor,
) -> torch.Tensor:
    """Negative log-likelihood of bivariate Gaussian with correlation."""
    lv = logvar.clamp(-8.0, 8.0)
    var_h = lv[:, 0].exp()
    var_a = lv[:, 1].exp()
    sd_h = var_h.sqrt()
    sd_a = var_a.sqrt()
    rho = torch.tanh(rho_logit) * 0.95
    zh = (y_h - mu[:, 0]) / sd_h.clamp_min(1e-4)
    za = (y_a - mu[:, 1]) / sd_a.clamp_min(1e-4)
    z2 = zh.pow(2) + za.pow(2) - 2.0 * rho * zh * za
    one_r2 = (1.0 - rho.pow(2)).clamp_min(1e-4)
    log_det = lv[:, 0] + lv[:, 1] + one_r2.log()
    nll = 0.5 * (log_det + z2 / one_r2)
    # Huber-like soft dampening of extreme residuals (blowouts)
    damp = 1.0 / (1.0 + 0.05 * (zh.abs() + za.abs()))
    return (nll * damp).mean()


def consistency_loss(implied: torch.Tensor, direct: torch.Tensor) -> torch.Tensor:
    """Penalise disagreement between score-implied and direct H/D/A."""
    # Symmetric KL
    eps = 1e-6
    p = implied.clamp(eps, 1.0)
    q = direct.clamp(eps, 1.0)
    kl_pq = (p * (p.log() - q.log())).sum(dim=-1)
    kl_qp = (q * (q.log() - p.log())).sum(dim=-1)
    return (0.5 * (kl_pq + kl_qp)).mean()


def expert_balance_loss(gate: torch.Tensor) -> torch.Tensor:
    """Encourage all experts to be used on average (mild)."""
    usage = gate.mean(dim=0)
    target = torch.full_like(usage, 1.0 / gate.shape[1])
    return F.mse_loss(usage, target)


def killer_loss(
    outputs: Dict[str, torch.Tensor],
    y_home: torch.Tensor,
    y_away: torch.Tensor,
    y_outcome: torch.Tensor,
    *,
    w_score: float = 1.0,
    w_hda: float = 1.0,
    w_consistency: float = 0.25,
    w_balance: float = 0.05,
    w_margin: float = 0.15,
) -> Dict[str, torch.Tensor]:
    score_nll = bivariate_nll(
        y_home,
        y_away,
        outputs["score_mu"],
        outputs["score_logvar"],
        outputs["score_rho_logit"],
    )
    hda_ce = F.cross_entropy(outputs["hda_fused_logits"], y_outcome.long())
    cons = consistency_loss(outputs["hda_implied"], outputs["hda_direct"])
    bal = expert_balance_loss(outputs["gate"])
    margin_err = (outputs["margin_mu"] - (y_home - y_away)).abs()
    # Robust margin: log1p soft
    margin_l = torch.log1p(margin_err).mean()
    total = (
        w_score * score_nll
        + w_hda * hda_ce
        + w_consistency * cons
        + w_balance * bal
        + w_margin * margin_l
    )
    return {
        "loss": total,
        "score_nll": score_nll.detach(),
        "hda_ce": hda_ce.detach(),
        "consistency": cons.detach(),
        "balance": bal.detach(),
        "margin": margin_l.detach(),
    }


def ssl_next_score_loss(outputs: Dict[str, torch.Tensor], y_home: torch.Tensor, y_away: torch.Tensor) -> torch.Tensor:
    """Self-supervised style: just score NLL (used in pretrain phase)."""
    return bivariate_nll(
        y_home,
        y_away,
        outputs["score_mu"],
        outputs["score_logvar"],
        outputs["score_rho_logit"],
    )
