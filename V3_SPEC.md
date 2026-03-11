# MAZ MAXED V3 Spec

MAZ MAXED V3 is a league-adaptive quant system designed to maximize stable win/lose performance while preserving score quality and reducing worst-league regressions.

## Core formula

- Base winner probability:
  - `p_base = alpha * p_classifier + (1 - alpha) * p_score_distribution`
- Residual correction in log-odds space:
  - `logit(p_raw) = logit(p_base) + shrink(n_league) * delta_league`
- Calibrated deployment probability:
  - `p_final = calibrate(p_raw, regime)`

## Components

- Global core winner/score models (cross-league)
- Dynamic attack/defense/home-adv rating features
- Score-distribution winner probability path
- League residual correction heads
- Regime-aware blending and calibration
- Guardrail-based promotion policy

## Artifacts

- `artifacts/maz_maxed_v3_report_<timestamp>.json`
- `artifacts/maz_v3_tuning_results.json`
- `artifacts/maz_v3_best_config.json`
- Optional per-league promoted model pickles

## Scripts

- `scripts/maz_boss_maxed_v3.py`
- `scripts/tune_maz_maxed_v3.py`

