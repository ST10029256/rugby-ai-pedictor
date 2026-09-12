"""Killer V2 = A5 — frozen. Do not change architecture, features, or training recipe.

A5 development is finished. The 2,936-match historical benchmark is closed.
Live-forward vs V4 is the experiment.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

VERSION = "killer_v2"
ARCHITECTURE = (
    "v4_gru_attack_defence_opp_adj_mu0_residual_film_draw_prior"
)
FROZEN = True
FROZEN_ABLATION = "A5"
# Develop-val median alpha for A5. Do not retune on the 2,936 or on live residuals.
FROZEN_ALPHA = 0.65

SEQ_LEN = 12
GRU_HIDDEN = 48
EMB_DIM = 16
TRUNK_HIDDEN = 128
TRUNK_OUT = 64
DROPOUT = 0.15
LR = 1e-4
WEIGHT_DECAY = 1e-4
GRAD_CLIP = 1.0
MAX_EPOCHS = 40
PATIENCE = 6
BATCH_SIZE = 128
RESIDUAL_ANCHOR = 0.01
BLEND_ALPHA_MIN = 0.65
BLEND_ALPHA_MAX = 0.90
SEEDS: Tuple[int, ...] = (42, 1337, 9001)

UNK_TEAM_IDX = 0
UNK_LEAGUE_IDX = 0

ELO_K = 20.0
ELO_SCALE = 400.0
ELO_HOME_ADV = 40.0
ATTACK_K = 0.08
DEFENCE_K = 0.08
RATING_SHRINK_N0 = 8.0

ABLATIONS: Tuple[str, ...] = ("A0", "A1", "A2", "A3", "A4", "A5")

SEQ_DIM = {
    "A0": 11,
    "A1": 15,
    "A2": 16,
    "A3": 16,
    "A4": 16,
    "A5": 16,
}

DEFAULT_LEAGUE_IDS: List[int] = [
    4414, 4430, 4446, 4551, 4574, 4714, 4986, 5069, 5479, 5480,
]

LEAGUE_HOME_ADV_PRIOR: Dict[int, float] = {
    4551: 0.58, 4986: 0.56, 4446: 0.57, 4430: 0.60, 4414: 0.56,
    5069: 0.57, 4714: 0.54, 4574: 0.50, 5479: 0.52, 5480: 0.52,
}

ARTIFACT_DIR = "artifacts_killer_v1_rebuilt"
LIVE_ARTIFACT_DIR = "artifacts_killer_v2"
LEGACY_SPLIT_DIR = "artifacts_killer"
LIVE_LOCK_HORIZON_HOURS = 96
LIVE_CHECKPOINTS: Tuple[int, ...] = (100, 250, 500)

# Recorded once. Do not use these numbers to redesign A5.
HISTORICAL_BENCHMARK = {
    "label": "Killer V2 A5 — Fixed Historical Benchmark",
    "n": 2936,
    "accuracy": 0.7244550408719346,
    "brier": 0.37843093276023865,
    "log_loss": 0.6109812259674072,
    "ece": 0.015399108871776987,
    "home_mae": 9.225790977478027,
    "margin_mae": 12.727177619934082,
    "note": "Strong evidence, not final proof. Closed. Live-forward is the exam.",
}

FROZEN_KNOBS = {
    "ablation": FROZEN_ABLATION,
    "seq_len": SEQ_LEN,
    "seq_dim": SEQ_DIM[FROZEN_ABLATION],
    "gru_hidden": GRU_HIDDEN,
    "emb_dim": EMB_DIM,
    "trunk_hidden": TRUNK_HIDDEN,
    "trunk_out": TRUNK_OUT,
    "dropout": DROPOUT,
    "lr": LR,
    "weight_decay": WEIGHT_DECAY,
    "grad_clip": GRAD_CLIP,
    "max_epochs": MAX_EPOCHS,
    "patience": PATIENCE,
    "batch_size": BATCH_SIZE,
    "residual_anchor": RESIDUAL_ANCHOR,
    "blend_alpha": FROZEN_ALPHA,
    "blend_alpha_min": BLEND_ALPHA_MIN,
    "blend_alpha_max": BLEND_ALPHA_MAX,
    "seeds": list(SEEDS),
    "elo_k": ELO_K,
    "elo_scale": ELO_SCALE,
    "elo_home_adv": ELO_HOME_ADV,
    "attack_k": ATTACK_K,
    "defence_k": DEFENCE_K,
    "rating_shrink_n0": RATING_SHRINK_N0,
    "use_film": True,
    "residual_scores": True,
    "use_draw": True,
}
