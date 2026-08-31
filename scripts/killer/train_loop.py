"""Killer training loops — sealed 25% never touched here."""

from __future__ import annotations

import copy
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from .calibrate import apply_calibrator, fit_calibrator_bundle
from .features import KillerBatch
from .losses import killer_loss, ssl_next_score_loss
from .metrics import compute_metrics
from .model import KillerModel


@dataclass
class TrainResult:
    model: KillerModel
    history: List[Dict[str, float]]
    best_val_loss: float
    checkpoint_bytes: bytes
    checkpoint_hash: str


def _batch_to_tensors(batch: KillerBatch, device: torch.device) -> Dict[str, torch.Tensor]:
    def t(x: np.ndarray, dtype=None) -> torch.Tensor:
        ten = torch.from_numpy(np.asarray(x))
        if dtype is not None:
            ten = ten.to(dtype)
        return ten.to(device)

    return {
        "home_idx": t(batch.home_idx, torch.long),
        "away_idx": t(batch.away_idx, torch.long),
        "league_idx": t(batch.league_idx, torch.long),
        "home_fast": t(batch.home_fast, torch.float32),
        "away_fast": t(batch.away_fast, torch.float32),
        "home_med": t(batch.home_med, torch.float32),
        "away_med": t(batch.away_med, torch.float32),
        "home_long": t(batch.home_long, torch.float32),
        "away_long": t(batch.away_long, torch.float32),
        "rating_feats": t(batch.rating_feats, torch.float32),
        "score_feats": t(batch.score_feats, torch.float32),
        "rest_feats": t(batch.rest_feats, torch.float32),
        "y_home": t(batch.y_home, torch.float32),
        "y_away": t(batch.y_away, torch.float32),
        "y_outcome": t(batch.y_outcome, torch.long),
    }


def _forward(model: KillerModel, tensors: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    return model(
        tensors["home_idx"],
        tensors["away_idx"],
        tensors["league_idx"],
        tensors["home_fast"],
        tensors["away_fast"],
        tensors["home_med"],
        tensors["away_med"],
        tensors["home_long"],
        tensors["away_long"],
        tensors["rating_feats"],
        tensors["score_feats"],
        tensors["rest_feats"],
    )


def _make_loader(batch: KillerBatch, device: torch.device, bs: int, shuffle: bool) -> DataLoader:
    # Keep on CPU for DataLoader; move in loop for simplicity with variable device
    ds = TensorDataset(
        torch.from_numpy(batch.home_idx.astype(np.int64)),
        torch.from_numpy(batch.away_idx.astype(np.int64)),
        torch.from_numpy(batch.league_idx.astype(np.int64)),
        torch.from_numpy(batch.home_fast.astype(np.float32)),
        torch.from_numpy(batch.away_fast.astype(np.float32)),
        torch.from_numpy(batch.home_med.astype(np.float32)),
        torch.from_numpy(batch.away_med.astype(np.float32)),
        torch.from_numpy(batch.home_long.astype(np.float32)),
        torch.from_numpy(batch.away_long.astype(np.float32)),
        torch.from_numpy(batch.rating_feats.astype(np.float32)),
        torch.from_numpy(batch.score_feats.astype(np.float32)),
        torch.from_numpy(batch.rest_feats.astype(np.float32)),
        torch.from_numpy(batch.y_home.astype(np.float32)),
        torch.from_numpy(batch.y_away.astype(np.float32)),
        torch.from_numpy(batch.y_outcome.astype(np.int64)),
    )
    return DataLoader(ds, batch_size=bs, shuffle=shuffle, drop_last=False)


def _unpack_loader_batch(parts: Tuple[torch.Tensor, ...], device: torch.device) -> Dict[str, torch.Tensor]:
    keys = [
        "home_idx", "away_idx", "league_idx",
        "home_fast", "away_fast", "home_med", "away_med", "home_long", "away_long",
        "rating_feats", "score_feats", "rest_feats",
        "y_home", "y_away", "y_outcome",
    ]
    return {k: v.to(device) for k, v in zip(keys, parts)}


@torch.no_grad()
def predict_numpy(model: KillerModel, batch: KillerBatch, device: torch.device) -> Dict[str, np.ndarray]:
    model.eval()
    tensors = _batch_to_tensors(batch, device)
    out = _forward(model, tensors)
    p = out["hda_fused"].detach().cpu().numpy()
    logits = out["hda_fused_logits"].detach().cpu().numpy()
    mu = out["score_mu"].detach().cpu().numpy()
    gate = out["gate"].detach().cpu().numpy()
    return {
        "p_hda": p,
        "logits": logits,
        "pred_home": mu[:, 0],
        "pred_away": mu[:, 1],
        "gate": gate,
        "margin_sd": out["margin_sd"].detach().cpu().numpy(),
    }


def train_one_model(
    *,
    n_teams: int,
    n_leagues: int,
    train_batch: KillerBatch,
    val_batch: Optional[KillerBatch],
    seed: int,
    device: torch.device,
    epochs: int = 40,
    batch_size: int = 128,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    ssl_epochs: int = 5,
    patience: int = 8,
) -> TrainResult:
    torch.manual_seed(int(seed))
    np.random.seed(int(seed))

    model = KillerModel(
        n_teams=n_teams,
        n_leagues=n_leagues,
        rating_dim=train_batch.rating_feats.shape[1],
        score_dim=train_batch.score_feats.shape[1],
        rest_dim=train_batch.rest_feats.shape[1],
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    train_loader = _make_loader(train_batch, device, batch_size, shuffle=True)
    history: List[Dict[str, float]] = []

    # Controlled SSL pretrain on develop-train only (score NLL)
    for ep in range(int(ssl_epochs)):
        model.train()
        total = 0.0
        n = 0
        for parts in train_loader:
            tensors = _unpack_loader_batch(parts, device)
            opt.zero_grad(set_to_none=True)
            out = _forward(model, tensors)
            loss = ssl_next_score_loss(out, tensors["y_home"], tensors["y_away"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += float(loss.item()) * len(tensors["y_home"])
            n += len(tensors["y_home"])
        history.append({"phase": 0.0, "epoch": float(ep), "ssl_loss": total / max(1, n)})

    best_state = copy.deepcopy(model.state_dict())
    best_val = float("inf")
    stale = 0

    for ep in range(int(epochs)):
        model.train()
        total = 0.0
        n = 0
        for parts in train_loader:
            tensors = _unpack_loader_batch(parts, device)
            opt.zero_grad(set_to_none=True)
            out = _forward(model, tensors)
            parts_loss = killer_loss(out, tensors["y_home"], tensors["y_away"], tensors["y_outcome"])
            parts_loss["loss"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += float(parts_loss["loss"].item()) * len(tensors["y_home"])
            n += len(tensors["y_home"])
        train_loss = total / max(1, n)

        val_loss = train_loss
        if val_batch is not None and len(val_batch.event_ids) > 0:
            model.eval()
            with torch.no_grad():
                vt = _batch_to_tensors(val_batch, device)
                vout = _forward(model, vt)
                val_loss = float(
                    killer_loss(vout, vt["y_home"], vt["y_away"], vt["y_outcome"])["loss"].item()
                )
            if val_loss < best_val - 1e-4:
                best_val = val_loss
                best_state = copy.deepcopy(model.state_dict())
                stale = 0
            else:
                stale += 1
        else:
            best_state = copy.deepcopy(model.state_dict())
            best_val = train_loss

        history.append({"phase": 1.0, "epoch": float(ep), "train_loss": train_loss, "val_loss": val_loss})
        if val_batch is not None and stale >= patience:
            break

    model.load_state_dict(best_state)
    buf = io.BytesIO()
    torch.save({"model": model.state_dict(), "seed": seed, "n_teams": n_teams, "n_leagues": n_leagues}, buf)
    blob = buf.getvalue()
    import hashlib

    return TrainResult(
        model=model,
        history=history,
        best_val_loss=float(best_val),
        checkpoint_bytes=blob,
        checkpoint_hash=hashlib.sha256(blob).hexdigest(),
    )


def ensemble_predict(
    models: Sequence[KillerModel],
    batch: KillerBatch,
    device: torch.device,
    calibrator: Optional[Dict[str, Any]] = None,
) -> Dict[str, np.ndarray]:
    ps = []
    homes = []
    aways = []
    logits_l = []
    sds = []
    for m in models:
        pred = predict_numpy(m, batch, device)
        ps.append(pred["p_hda"])
        homes.append(pred["pred_home"])
        aways.append(pred["pred_away"])
        logits_l.append(pred["logits"])
        sds.append(pred["margin_sd"])
    p = np.mean(np.stack(ps, axis=0), axis=0)
    logits = np.mean(np.stack(logits_l, axis=0), axis=0)
    seed_std = np.std(np.stack(ps, axis=0)[:, :, 2], axis=0)  # std of P(home) across seeds
    if calibrator:
        p = apply_calibrator(p, temperature=float(calibrator.get("temperature", 1.0)), vector=calibrator.get("vector"), logits=logits)
    return {
        "p_hda": p,
        "logits": logits,
        "pred_home": np.mean(np.stack(homes, axis=0), axis=0),
        "pred_away": np.mean(np.stack(aways, axis=0), axis=0),
        "seed_std": seed_std,
        "margin_sd": np.mean(np.stack(sds, axis=0), axis=0),
        "uncertainty": np.mean(np.stack(sds, axis=0), axis=0) + seed_std,
    }


def fit_ensemble_calibrator(
    models: Sequence[KillerModel],
    val_batch: KillerBatch,
    device: torch.device,
) -> Dict[str, Any]:
    raw = ensemble_predict(models, val_batch, device, calibrator=None)
    return fit_calibrator_bundle(raw["logits"], raw["p_hda"], val_batch.y_outcome)


def eval_ensemble(
    models: Sequence[KillerModel],
    batch: KillerBatch,
    device: torch.device,
    calibrator: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, np.ndarray]]:
    pred = ensemble_predict(models, batch, device, calibrator=calibrator)
    metrics = compute_metrics(
        y_outcome=batch.y_outcome,
        p_hda=pred["p_hda"],
        y_home=batch.y_home,
        y_away=batch.y_away,
        pred_home=pred["pred_home"],
        pred_away=pred["pred_away"],
    )
    return metrics.as_dict(), pred
