"""
Fair sealed-exam baselines: retrain simplified V4/V5-style models on the SAME 75% only.

Imports architecture pieces from maz_boss_maxed_v4 / v5 without modifying those files.
Uses Killer's sealed split and chronology-safe V4 sequence builders.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "rugby-ai-predictor") not in sys.path:
    sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_v4_module():
    return _load_module("maz_boss_maxed_v4_killer_exam", SCRIPTS / "maz_boss_maxed_v4.py")


def load_v5_module():
    return _load_module("maz_boss_maxed_v5_killer_exam", SCRIPTS / "maz_boss_maxed_v5.py")


def _outcome_to_home_win(y_outcome: np.ndarray) -> np.ndarray:
    return (y_outcome == 2).astype(np.float32)


def build_v4_arrays(v4, df: pd.DataFrame, train_ids: Sequence[int], eval_ids: Sequence[int]):
    """Fit stats on train_ids only; build sequences on train+eval chronological union."""
    id_set_train = set(int(x) for x in train_ids)
    id_set_eval = set(int(x) for x in eval_ids)
    g = df.sort_values(["date_event", "event_id"]).reset_index(drop=True)
    # Restrict to train+eval rows only (never other sealed? eval may BE sealed)
    keep = g["event_id"].astype(int).isin(id_set_train | id_set_eval)
    g = g.loc[keep].reset_index(drop=True)
    tr_df = g[g["event_id"].astype(int).isin(id_set_train)].copy()
    league_stats = v4.build_league_score_stats(tr_df)
    league_env = v4.build_league_environment_stats(tr_df, base_rating_home_adv=2.0)
    # Train-only identities. Sealed-only / future clubs map to UNK (0).
    # Do not allocate unique embeddings from future matches.
    from .config import UNK_LEAGUE_IDX, UNK_TEAM_IDX
    from .features import build_idx_maps_from_train

    team_to_idx, league_to_idx = build_idx_maps_from_train(tr_df)
    for _, r in g.iterrows():
        team_to_idx.setdefault(int(r["home_team_id"]), UNK_TEAM_IDX)
        team_to_idx.setdefault(int(r["away_team_id"]), UNK_TEAM_IDX)
        league_to_idx.setdefault(int(r["league_id"]), UNK_LEAGUE_IDX)

    home_seq, away_seq, home_idx, away_idx, home_opp, away_opp, league_idx, y, league_ids, team_to_idx, league_to_idx = v4.build_temporal_sequences(
        g,
        seq_len=12,
        team_to_idx=team_to_idx,
        league_to_idx=league_to_idx,
        league_stats=league_stats,
        league_env_stats=league_env,
    )
    # Normalize using train rows only
    train_mask = g["event_id"].astype(int).isin(id_set_train).values
    train_rows = int(np.sum(train_mask))
    # Reorder so train first for normalize helper? normalize_sequences uses first train_rows
    # Safer: manual normalize on train mask
    x_train = np.concatenate([home_seq[train_mask], away_seq[train_mask]], axis=0)
    mean = np.mean(x_train.reshape(-1, x_train.shape[-1]), axis=0)
    std = np.std(x_train.reshape(-1, x_train.shape[-1]), axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    home_seq = ((home_seq - mean) / std).astype(np.float32)
    away_seq = ((away_seq - mean) / std).astype(np.float32)

    eval_mask = g["event_id"].astype(int).isin(id_set_eval).values
    regime = np.zeros(len(g), dtype=np.int64)

    return {
        "home_seq": home_seq,
        "away_seq": away_seq,
        "home_idx": home_idx,
        "away_idx": away_idx,
        "home_opp": home_opp,
        "away_opp": away_opp,
        "league_idx": league_idx,
        "regime": regime,
        "y": y,
        "event_ids": g["event_id"].astype(int).values,
        "train_mask": train_mask,
        "eval_mask": eval_mask,
        "n_teams": int(max(team_to_idx.values(), default=0) + 1),
        "n_leagues": int(max(league_to_idx.values(), default=0) + 1),
        "league_stats": league_stats,
    }


def _train_torch_model(
    model: torch.nn.Module,
    arrays: Dict[str, Any],
    *,
    seed: int,
    device: torch.device,
    epochs: int = 25,
    lr: float = 1e-3,
    is_v5: bool = False,
) -> torch.nn.Module:
    torch.manual_seed(seed)
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    m = arrays["train_mask"]
    hs = torch.from_numpy(arrays["home_seq"][m]).to(device)
    aws = torch.from_numpy(arrays["away_seq"][m]).to(device)
    hi = torch.from_numpy(arrays["home_idx"][m]).long().to(device)
    ai = torch.from_numpy(arrays["away_idx"][m]).long().to(device)
    ho = torch.from_numpy(arrays["home_opp"][m]).long().to(device)
    ao = torch.from_numpy(arrays["away_opp"][m]).long().to(device)
    li = torch.from_numpy(arrays["league_idx"][m]).long().to(device)
    ri = torch.from_numpy(arrays["regime"][m]).long().to(device)
    y = torch.from_numpy(arrays["y"][m]).float().to(device)

    # Scale scores roughly
    y_h = y[:, 1] / 30.0
    y_a = y[:, 2] / 30.0
    y_w = y[:, 0]

    n = len(y_w)
    bs = min(128, max(16, n // 5))
    model.train()
    for _ in range(epochs):
        perm = torch.randperm(n, device=device)
        for i in range(0, n, bs):
            idx = perm[i : i + bs]
            opt.zero_grad(set_to_none=True)
            out = model(hi[idx], ai[idx], li[idx], ri[idx], hs[idx], aws[idx], ho[idx], ao[idx])
            # BCE on winner + score MSE (robust enough for baseline)
            if "winner_logit" in out:
                logit = out["winner_logit"]
            else:
                # v5 score-first: derive from margin
                mu = out["score_mu"]
                logit = (mu[:, 0] - mu[:, 1]) * 2.0
            bce = F.binary_cross_entropy_with_logits(logit, y_w[idx])
            mu = out["score_mu"]
            mse = F.smooth_l1_loss(mu[:, 0], y_h[idx]) + F.smooth_l1_loss(mu[:, 1], y_a[idx])
            loss = bce + mse
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    model.eval()
    return model


@torch.no_grad()
def _predict_home_probs(model: torch.nn.Module, arrays: Dict[str, Any], mask: np.ndarray, device: torch.device) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    hs = torch.from_numpy(arrays["home_seq"][mask]).to(device)
    aws = torch.from_numpy(arrays["away_seq"][mask]).to(device)
    hi = torch.from_numpy(arrays["home_idx"][mask]).long().to(device)
    ai = torch.from_numpy(arrays["away_idx"][mask]).long().to(device)
    ho = torch.from_numpy(arrays["home_opp"][mask]).long().to(device)
    ao = torch.from_numpy(arrays["away_opp"][mask]).long().to(device)
    li = torch.from_numpy(arrays["league_idx"][mask]).long().to(device)
    ri = torch.from_numpy(arrays["regime"][mask]).long().to(device)
    out = model(hi, ai, li, ri, hs, aws, ho, ao)
    mu = out["score_mu"].detach().cpu().numpy() * 30.0
    if "winner_logit" in out:
        p_home = torch.sigmoid(out["winner_logit"]).detach().cpu().numpy()
    else:
        margin = mu[:, 0] - mu[:, 1]
        p_home = 1.0 / (1.0 + np.exp(-margin / 8.0))
    # Expand to 3-class with small draw mass
    p_draw = np.full_like(p_home, 0.04)
    p_away = np.clip(1.0 - p_home - p_draw, 0.01, 0.98)
    p_home = np.clip(p_home, 0.01, 0.98)
    s = p_away + p_draw + p_home
    p = np.stack([p_away / s, p_draw / s, p_home / s], axis=1)
    return p, mu[:, 0], mu[:, 1]


def run_baseline_exam(
    *,
    family: str,
    df: pd.DataFrame,
    train_ids: Sequence[int],
    sealed_ids: Sequence[int],
    device: torch.device,
    seeds: Sequence[int] = (42, 1337, 9001),
) -> Dict[str, Any]:
    family = family.lower()
    if family == "v4":
        mod = load_v4_module()
        arrays = build_v4_arrays(mod, df, train_ids, sealed_ids)
        models = []
        for seed in seeds:
            m = mod.V4Model(arrays["n_teams"], arrays["n_leagues"], emb_dim=16, seq_dim=11, hidden_dim=48)
            models.append(_train_torch_model(m, arrays, seed=seed, device=device, is_v5=False))
    elif family == "v5":
        mod = load_v5_module()
        # V5 reuses v4 sequence builders via its base
        v4 = load_v4_module()
        arrays = build_v4_arrays(v4, df, train_ids, sealed_ids)
        models = []
        for seed in seeds:
            # Inspect V5Model signature
            m = mod.V5Model(arrays["n_teams"], arrays["n_leagues"], emb_dim=16, seq_dim=11, hidden_dim=48)
            models.append(_train_torch_model(m, arrays, seed=seed, device=device, is_v5=True))
    else:
        raise ValueError(family)

    ps, hs, aws = [], [], []
    for m in models:
        p, h, a = _predict_home_probs(m, arrays, arrays["eval_mask"], device)
        ps.append(p)
        hs.append(h)
        aws.append(a)
    p = np.mean(np.stack(ps, axis=0), axis=0)
    pred_h = np.mean(np.stack(hs, axis=0), axis=0)
    pred_a = np.mean(np.stack(aws, axis=0), axis=0)
    y = arrays["y"][arrays["eval_mask"]]
    # Map binary winner labels to 3-class outcomes (draws were labeled 0 in v4 y[:,0])
    # Recover draws from scores
    y_outcome = np.where(y[:, 1] > y[:, 2], 2, np.where(y[:, 1] < y[:, 2], 0, 1)).astype(np.int64)

    from .metrics import compute_metrics, confidence_buckets

    metrics = compute_metrics(
        y_outcome=y_outcome,
        p_hda=p,
        y_home=y[:, 1],
        y_away=y[:, 2],
        pred_home=pred_h,
        pred_away=pred_a,
    )
    return {
        "family": family,
        "metrics": metrics.as_dict(),
        "confidence_buckets": confidence_buckets(y_outcome, p),
        "event_ids": arrays["event_ids"][arrays["eval_mask"]].tolist(),
        "p_hda": p,
        "pred_home": pred_h,
        "pred_away": pred_a,
        "y_outcome": y_outcome,
        "y_home": y[:, 1],
        "y_away": y[:, 2],
    }
