"""Frozen Killer experiment constants."""

from __future__ import annotations

from typing import Dict, List, Tuple

KILLER_VERSION = "killer_v1"
KILLER_ARCHITECTURE = (
    "global_backbone_competition_adapters_multiscale_"
    "four_experts_sparse_router_score_first_hda"
)

# Immutable chronological firewall
TRAIN_FRACTION = 0.75
SEALED_TEST_FRACTION = 0.25
# Inside the 75%: ~80% develop-train / ~20% develop-val
# → ~60% / ~15% / ~25% of the original league timeline
DEV_VAL_FRACTION = 0.20

KILLER_SEEDS: Tuple[int, ...] = (42, 1337, 9001, 2026, 7777)

FAST_WINDOW = 5
MEDIUM_WINDOW = 20
LONG_WINDOW = 40

SEQ_DIM = 14  # opp-adjusted multi-feature step
STATE_DIM = 64
HIDDEN_DIM = 96
EMB_DIM = 32
N_EXPERTS = 4
EXPERT_NAMES = ("v4_stability", "v5_pattern", "rating_intelligence", "score_dynamics")
UNK_TEAM_IDX = 0
UNK_LEAGUE_IDX = 0

# Rating dynamics (score-only, chronology-safe)
ELO_K = 20.0
ELO_HOME_ADV = 40.0
ATTACK_K = 0.08
DEFENCE_K = 0.08
RATING_SCALE = 400.0

DEFAULT_LEAGUE_IDS: List[int] = [
    4414,  # Premiership
    4430,  # Top 14
    4446,  # URC
    4551,  # Super Rugby
    4574,  # World Cup
    4714,  # Six Nations
    4986,  # Rugby Championship
    5069,  # Currie Cup
    5479,  # Internationals
    5480,  # Nations Championship
]

LEAGUE_HOME_ADV_PRIOR: Dict[int, float] = {
    4551: 0.58,
    4986: 0.56,
    4446: 0.57,
    4430: 0.60,
    4414: 0.56,
    5069: 0.57,
    4714: 0.54,
    4574: 0.50,
    5479: 0.52,
    5480: 0.52,
}

CONFIDENCE_BUCKETS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)

ARTIFACT_DIR_NAME = "artifacts_killer"
