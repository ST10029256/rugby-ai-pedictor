"""Train / select / predict Killer V1 Rebuilt."""

from __future__ import annotations

import copy
import hashlib
import io
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from .config import (
    BATCH_SIZE,
    BLEND_ALPHA_MAX,
    BLEND_ALPHA_MIN,
    GRAD_CLIP,
    LR,
    MAX_EPOCHS,
    PATIENCE,
    RESIDUAL_ANCHOR,
    WEIGHT_DECAY,
)
from .dataset import RebuiltBatch
from .model import RebuiltModel, blend_hda


def flags_for(ablation: str) -> Dict[str, bool]:
    return {
        "use_film": ablation in {"A4", "A5"},
        "residual_scores": ablation in {"A3", "A4", "A5"},
        "use_draw": ablation == "A5",
    }


def _loader(batch: RebuiltBatch, shuffle: bool, bs: int = BATCH_SIZE) -> DataLoader:
    ds = TensorDataset(
        torch.from_numpy(batch.home_idx),
        torch.from_numpy(batch.away_idx),
        torch.from_numpy(batch.league_idx),
        torch.from_numpy(batch.home_seq),
        torch.from_numpy(batch.away_seq),
        torch.from_numpy(batch.scalars),
        torch.from_numpy(batch.mu0.astype(np.float32)),
        torch.from_numpy(batch.pi_draw.astype(np.float32)),
        torch.from_numpy(batch.y_home),
        torch.from_numpy(batch.y_away),
        torch.from_numpy(batch.y_home_win_nd),
        torch.from_numpy(batch.is_draw),
        torch.from_numpy(batch.y_outcome),
    )
    return DataLoader(ds, batch_size=bs, shuffle=shuffle)


def _unpack(parts, device):
    keys = [
        "home_idx", "away_idx", "league_idx", "home_seq", "away_seq", "scalars",
        "mu0", "pi_draw", "y_home", "y_away", "y_nd", "is_draw", "y_outcome",
    ]
    d = {k: v.to(device) for k, v in zip(keys, parts)}
    d["home_idx"] = d["home_idx"].long()
    d["away_idx"] = d["away_idx"].long()
    d["league_idx"] = d["league_idx"].long()
    d["y_outcome"] = d["y_outcome"].long()
    return d


def _forward(model, d):
    return model(
        d["home_idx"], d["away_idx"], d["league_idx"],
        d["home_seq"], d["away_seq"], d["scalars"], d["mu0"], d["pi_draw"],
    )


def loss_fn(out, d, residual_scores: bool, alpha: float, use_draw: bool) -> torch.Tensor:
    nd = d["is_draw"] < 0.5
    bce = torch.tensor(0.0, device=d["y_nd"].device)
    if nd.any():
        bce = F.binary_cross_entropy_with_logits(out["win_logit"][nd], d["y_nd"][nd])
    sl = F.smooth_l1_loss(out["mu"][:, 0], d["y_home"]) + F.smooth_l1_loss(out["mu"][:, 1], d["y_away"])
    anc = (out["delta"] ** 2).mean() if residual_scores else out["delta"].new_zeros(())
    return bce + sl + RESIDUAL_ANCHOR * anc


@torch.no_grad()
def predict(model, batch: RebuiltBatch, device, alpha: float, use_draw: bool) -> Dict[str, np.ndarray]:
    model.eval()
    loader = _loader(batch, False, bs=512)
    ps, mus = [], []
    for parts in loader:
        d = _unpack(parts, device)
        out = _forward(model, d)
        p = blend_hda(out["p_direct"], out["p_score"], out["mu"], d["pi_draw"], out["draw_beta"], alpha=alpha, use_draw=use_draw)
        ps.append(p.cpu().numpy())
        mus.append(out["mu"].cpu().numpy())
    return {"p_hda": np.concatenate(ps, 0), "mu": np.concatenate(mus, 0)}


def choose_alpha(model, val: RebuiltBatch, device, use_draw: bool) -> float:
    from killer.metrics import compute_metrics

    best_a, best = 0.80, 1e9
    for a in np.linspace(BLEND_ALPHA_MIN, BLEND_ALPHA_MAX, 6):
        pred = predict(model, val, device, float(a), use_draw)
        m = compute_metrics(
            y_outcome=val.y_outcome, p_hda=pred["p_hda"],
            y_home=val.y_home, y_away=val.y_away,
            pred_home=pred["mu"][:, 0], pred_away=pred["mu"][:, 1],
        )
        if m.brier < best:
            best, best_a = m.brier, float(a)
    return best_a


def train_one(
    *,
    ablation: str,
    n_teams: int,
    n_leagues: int,
    seq_dim: int,
    train: RebuiltBatch,
    val: Optional[RebuiltBatch],
    seed: int,
    device: torch.device,
    max_epochs: int = MAX_EPOCHS,
    patience: int = PATIENCE,
) -> Tuple[RebuiltModel, Dict[str, Any]]:
    fl = flags_for(ablation)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = RebuiltModel(n_teams, n_leagues, seq_dim, **fl).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    loader = _loader(train, True)
    best_state = copy.deepcopy(model.state_dict())
    best_brier = 1e9
    best_mae = 1e9
    stale = 0
    alpha = 0.80
    from killer.metrics import compute_metrics

    for ep in range(max_epochs):
        model.train()
        for parts in loader:
            d = _unpack(parts, device)
            opt.zero_grad(set_to_none=True)
            out = _forward(model, d)
            loss_fn(out, d, fl["residual_scores"], alpha, fl["use_draw"]).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            opt.step()
        if val is None or len(val.event_ids) == 0:
            best_state = copy.deepcopy(model.state_dict())
            continue
        pred = predict(model, val, device, alpha, fl["use_draw"])
        met = compute_metrics(
            y_outcome=val.y_outcome, p_hda=pred["p_hda"],
            y_home=val.y_home, y_away=val.y_away,
            pred_home=pred["mu"][:, 0], pred_away=pred["mu"][:, 1],
        )
        # Brier primary; reject MAE collapse vs running best mae*1.15 early on
        improved = met.brier < best_brier - 1e-4
        mae_ok = met.home_mae <= max(best_mae * 1.05, met.home_mae) or best_mae > 50
        if improved and (best_mae > 1e8 or met.home_mae <= best_mae * 1.02 + 0.3):
            best_brier, best_mae = met.brier, met.home_mae
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    model.load_state_dict(best_state)
    if val is not None and len(val.event_ids):
        alpha = choose_alpha(model, val, device, fl["use_draw"])
    buf = io.BytesIO()
    torch.save({"model": model.state_dict(), "ablation": ablation, "seed": seed, "alpha": alpha, **fl}, buf)
    blob = buf.getvalue()
    return model, {
        "alpha": alpha,
        "best_brier": best_brier,
        "best_home_mae": best_mae,
        "checkpoint_hash": hashlib.sha256(blob).hexdigest(),
        "blob": blob,
        "ablation": ablation,
        "seed": seed,
    }


def ensemble_predict(models: Sequence[RebuiltModel], batch: RebuiltBatch, device, alpha: float, use_draw: bool) -> Dict[str, np.ndarray]:
    ps, mus = [], []
    for m in models:
        pr = predict(m, batch, device, alpha, use_draw)
        ps.append(pr["p_hda"])
        mus.append(pr["mu"])
    p = np.mean(np.stack(ps, 0), 0)
    mu = np.mean(np.stack(mus, 0), 0)
    p = p / p.sum(1, keepdims=True)
    return {"p_hda": p, "mu": mu}
