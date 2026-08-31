"""Calibration fitted ONLY on develop-val (inside 75%). Never on sealed 25%."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """
    Simple temperature scaling for 3-class logits via grid search on NLL.
    logits: [N,3], y: [N] int
    """
    best_t, best_nll = 1.0, 1e9
    for t in np.linspace(0.5, 3.0, 26):
        p = _softmax(logits / t)
        nll = -np.mean(np.log(np.clip(p[np.arange(len(y)), y.astype(int)], 1e-7, 1.0)))
        if nll < best_nll:
            best_nll = float(nll)
            best_t = float(t)
    return best_t


def fit_vector_scaler(p: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """Optional multinomial logistic on logit features (Platt-style)."""
    x = _logit(p)
    try:
        clf = LogisticRegression(max_iter=500, multi_class="multinomial", C=1.0)
        clf.fit(x, y.astype(int))
        return {"type": "vector_platt", "coef": clf.coef_.tolist(), "intercept": clf.intercept_.tolist(), "classes": clf.classes_.tolist()}
    except Exception:
        return {"type": "identity"}


def apply_calibrator(
    p: np.ndarray,
    *,
    temperature: float = 1.0,
    vector: Optional[Dict[str, Any]] = None,
    logits: Optional[np.ndarray] = None,
) -> np.ndarray:
    if logits is not None and temperature != 1.0:
        p = _softmax(logits / float(temperature))
    if vector and vector.get("type") == "vector_platt":
        coef = np.asarray(vector["coef"], dtype=float)
        intercept = np.asarray(vector["intercept"], dtype=float)
        x = _logit(p)
        scores = x @ coef.T + intercept
        p = _softmax(scores)
    # renormalize
    p = np.clip(p, 1e-7, 1.0)
    p = p / p.sum(axis=1, keepdims=True)
    return p.astype(np.float64)


def fit_calibrator_bundle(logits: np.ndarray, p: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    t = fit_temperature(logits, y)
    p_t = _softmax(logits / t)
    # Prefer temperature if it improves NLL over raw; optionally add vector if helpful
    raw_nll = -np.mean(np.log(np.clip(p[np.arange(len(y)), y.astype(int)], 1e-7, 1.0)))
    t_nll = -np.mean(np.log(np.clip(p_t[np.arange(len(y)), y.astype(int)], 1e-7, 1.0)))
    bundle: Dict[str, Any] = {"temperature": t if t_nll <= raw_nll else 1.0, "vector": {"type": "identity"}}
    if len(y) >= 80:
        vec = fit_vector_scaler(p_t if t_nll <= raw_nll else p, y)
        # Keep vector only if it doesn't explode class collapse
        trial = apply_calibrator(p, temperature=bundle["temperature"], vector=vec, logits=logits)
        trial_nll = -np.mean(np.log(np.clip(trial[np.arange(len(y)), y.astype(int)], 1e-7, 1.0)))
        base_nll = min(raw_nll, t_nll)
        if trial_nll <= base_nll + 0.01:
            bundle["vector"] = vec
    return bundle


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - np.max(z, axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    return np.log(p)
