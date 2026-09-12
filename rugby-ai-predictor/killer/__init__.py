"""Killer — sealed 75/25 score-only rugby architecture.

Does not modify V4/V5. Pure historical scores only (no odds/lineups/DSG).
"""

from .config import KILLER_VERSION, KILLER_SEEDS, TRAIN_FRACTION, DEV_VAL_FRACTION

__all__ = [
    "KILLER_VERSION",
    "KILLER_SEEDS",
    "TRAIN_FRACTION",
    "DEV_VAL_FRACTION",
]
