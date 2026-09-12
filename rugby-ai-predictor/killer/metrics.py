"""Evaluation metrics for Killer sealed exam."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import CONFIDENCE_BUCKETS


@dataclass
class ExamMetrics:
    rows: int
    accuracy: float
    brier: float
    log_loss: float
    ece: float
    home_mae: float
    away_mae: float
    margin_mae: float
    draw_rate_pred: float
    draw_rate_true: float

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_log(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, 1e-7, 1.0))


def multiclass_brier(y_outcome: np.ndarray, p: np.ndarray) -> float:
    """y_outcome in {0,1,2}; p shape [N,3] away/draw/home."""
    n = len(y_outcome)
    if n == 0:
        return 0.0
    onehot = np.zeros_like(p)
    onehot[np.arange(n), y_outcome.astype(int)] = 1.0
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def multiclass_log_loss(y_outcome: np.ndarray, p: np.ndarray) -> float:
    n = len(y_outcome)
    if n == 0:
        return 0.0
    rows = _safe_log(p[np.arange(n), y_outcome.astype(int)])
    return float(-np.mean(rows))


def ece_multiclass(y_outcome: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Confidence = max prob; accuracy = whether argmax correct."""
    n = len(y_outcome)
    if n == 0:
        return 0.0
    conf = np.max(p, axis=1)
    pred = np.argmax(p, axis=1)
    correct = (pred == y_outcome.astype(int)).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi if i < bins - 1 else conf <= hi)
        if not np.any(m):
            continue
        out += float(np.mean(m)) * abs(float(np.mean(correct[m])) - float(np.mean(conf[m])))
    return float(out)


def compute_metrics(
    *,
    y_outcome: np.ndarray,
    p_hda: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    pred_home: np.ndarray,
    pred_away: np.ndarray,
) -> ExamMetrics:
    pred = np.argmax(p_hda, axis=1)
    acc = float(np.mean(pred == y_outcome.astype(int))) if len(y_outcome) else 0.0
    return ExamMetrics(
        rows=int(len(y_outcome)),
        accuracy=acc,
        brier=multiclass_brier(y_outcome, p_hda),
        log_loss=multiclass_log_loss(y_outcome, p_hda),
        ece=ece_multiclass(y_outcome, p_hda),
        home_mae=float(np.mean(np.abs(pred_home - y_home))) if len(y_home) else 0.0,
        away_mae=float(np.mean(np.abs(pred_away - y_away))) if len(y_away) else 0.0,
        margin_mae=float(np.mean(np.abs((pred_home - pred_away) - (y_home - y_away)))) if len(y_home) else 0.0,
        draw_rate_pred=float(np.mean(pred == 1)) if len(pred) else 0.0,
        draw_rate_true=float(np.mean(y_outcome == 1)) if len(y_outcome) else 0.0,
    )


def confidence_buckets(
    y_outcome: np.ndarray,
    p_hda: np.ndarray,
    thresholds: Sequence[float] = CONFIDENCE_BUCKETS,
) -> List[Dict[str, Any]]:
    conf = np.max(p_hda, axis=1)
    pred = np.argmax(p_hda, axis=1)
    correct = pred == y_outcome.astype(int)
    rows = []
    for t in thresholds:
        m = conf >= float(t)
        n = int(np.sum(m))
        rows.append(
            {
                "threshold": float(t),
                "n": n,
                "win_rate": float(np.mean(correct[m])) if n else None,
                "avg_confidence": float(np.mean(conf[m])) if n else None,
            }
        )
    return rows


def binary_home_probs(p_hda: np.ndarray) -> np.ndarray:
    """Collapse to home-win vs not for V4/V5-style comparisons when needed."""
    # P(home) / (P(home)+P(away)) ignoring draws in denominator optionally;
    # better: use p_home directly as home-win proxy and treat draws as non-home.
    return p_hda[:, 2]
