# V3 Freeze Contract

Version: `v3`

This document defines what is fixed versus tunable in MAZ Boss MAXED V3.

## 1) Immutable Architecture

The following components are frozen for V3 and must not be structurally changed:

- Global XGBoost core:
  - winner classifier
  - home score regressor
  - away score regressor
- Dynamic rating feature layer (attack/defense/home-advantage/time-evolving)
- Score distribution probability path (truncated Poisson engine)
- Residual correction in log-odds space
- Ridge residual heads with standardization
- Regime-aware alpha blending
- Calibration layer:
  - isotonic when sufficient data
  - Platt fallback
- Promotion guardrail policy (`V3_MAXED`, `V3_WINNER_HEAD`, `V3_SCORE_HEAD`, `CURRENT`)

Any structural change above requires a new major version (V4).

## 2) Tunable Parameters

Only these are intended to move during tuning/operations:

- `alpha_stable`, `alpha_balanced`, `alpha_chaotic`
- `residual_ridge_alpha`
- `residual_shrink_k`
- `adaptive_residual_ridge_alpha` toggle
- `min_isotonic_rows`
- `holdout_ratio`
- `wf_start_train`, `wf_step`
- Guardrail thresholds:
  - `min_winner_gain`
  - `max_mae_worsen`
  - `max_brier_worsen`

## 3) Stability Rules

Do not change without version bump:

- feature naming and injection order
- residual scaling and transform pipeline
- probability correction in log-odds space
- calibration fallback logic

## 4) Promotion Acceptance Criteria

A league can be promoted from `CURRENT` only if guardrails pass:

- Winner gain meets threshold, and
- MAE regression does not exceed limit, and
- Brier regression does not exceed limit

If criteria fail, league stays `CURRENT`.

## 5) Reporting and Traceability

V3 runs must emit:

- top-level `version`
- per-league `mode` (`single_holdout` or `walk_forward`)
- per-league regime metadata
- residual effective alpha
- calibration method
- winner feature importance top list
- baseline vs v3 metrics and deltas

## 6) Operational Policy

V3 architecture is frozen.

Future improvements should focus on:

- data quality and coverage
- feature quality
- regime threshold tuning
- parameter tuning automation

Avoid architecture expansion for V3 (no deep learning, no transformer stack, no new meta architecture).

---

## Elite Extension Roadmap (Optional)

You are already at a serious research-level system.

If you want to push V3 into elite / institutional tier, do not change the core structure. Add intelligence layers on top.

### 1) Ensemble of Multiple Training Seeds

- Train 3-7 models with different seeds per split/chunk.
- Average winner probabilities and score predictions.
- Benefits: lower variance, reduced overfitting, better Brier stability.

### 2) Meta-Learner for Final Probability

- Inputs: `p_classifier`, `p_score_dist`, rating gap, regime, home advantage, residual signals.
- Output: final winner probability.
- This replaces fixed alpha with learned blending behavior.

### 3) Temporal Decay Weighting

- Add recency sample weights: `weight = exp(-lambda * days_since_game)`.
- Train core models with `sample_weight`.
- Benefits: faster adaptation to form changes.

### 4) Regime Re-Evaluation by Walk-Forward Chunk

- Recompute regime on each training chunk, not once globally.
- Benefits: regime adapts with league evolution over time.

### 5) Bayesian-Style Score Uncertainty

- Model score mean plus uncertainty, sample score paths.
- Produce richer margin probabilities and confidence intervals.

### 6) Second Residual Boosting Layer

- Train a second-stage error model on post-calibration residuals.
- Apply as constrained correction to final probabilities.

### 7) Feature Selection Automation

- Use importance/SHAP-style pruning loops.
- Remove low-signal features and retrain for noise reduction.

### Top 3 Highest-Impact Additions

1. Ensemble across seeds
2. Learned blending via meta-model
3. Temporal decay weighting

### Institutional Mode Target

Combine:
- Ensemble
- Meta-learner
- Temporal weighting
- Residual stacking
- Chunk-level regime re-evaluation

This is your "V3 Pro Institutional Edition" roadmap.

---

## True Elite Upgrades (Current V3-Compatible)

These upgrades fit cleanly into current V3 without a full rewrite.

### 1) Ensemble per Layer (Top Priority)

- Replace single winner/global models with 3-5 seeded models.
- Aggregate:
  - winner probability = mean of model probabilities
  - score predictions = mean of model score outputs
- Benefits:
  - higher stability
  - lower variance
  - better out-of-time consistency

### 2) Feature Selection Before Core Training

- Add pre-train feature pruning:
  - correlation filter and/or
  - importance-based pruning and/or
  - L1-based selection
- Goal: remove noisy rugby features and improve generalization.

### 3) Residual Layer Targeting Upgrade

- Improve residual fit with:
  - cross-validated residual training and/or
  - hard-example residual fitting (focus on larger-error rows)
- Goal: make residual correction focus on known weak cases.

### 4) Uncertainty Output Layer

- Add uncertainty signals:
  - ensemble prediction std
  - confidence score per match
- Goal: distinguish high-confidence vs low-confidence predictions.

### 5) Automatic Alpha Optimization

- Instead of fixed manual alpha, optimize alpha on training validation.
- Example grid for each regime/league:
  - alpha in {0.3, 0.5, 0.7}
- Persist selected alpha per league.

### 6) Time-Based Retraining Strategy

- In walk-forward, support incremental-style updates:
  - extend with new chunk
  - warm-start/reuse where feasible
- Goal: improve runtime realism while preserving chronology-safe evaluation.

### Practical Summary

V3 is not missing a structural rewrite.

The highest-value improvements now are:

- ensemble stability
- automatic parameter tuning
- stronger residual targeting
- uncertainty-aware outputs

