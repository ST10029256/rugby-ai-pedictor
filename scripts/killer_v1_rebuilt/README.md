# Killer V2 = A5 — frozen

A5 development is finished. Do not change architecture, the 16-d feature schema,
rating equations, μ₀, residual scoring, GRU-48 / emb-16 / trunk 128→64, FiLM,
draw-prior, bounded blend, loss weights, seeds 42/1337/9001, calibration, or
the training recipe.

Original Killer V1 artifacts in `artifacts_killer/` are never altered.
Develop/exam artifacts in `artifacts_killer_v1_rebuilt/` are a closed record.

## Historical benchmark (closed)

Killer V2 A5 — Fixed Historical Benchmark: **72.45% accuracy, Brier 0.378, log loss 0.611, ECE 0.015, home MAE 9.23, margin MAE 12.73**.

Strong evidence, not final proof. **Do not use those 2,936 matches to improve A5.**
Currie Cup weakness, draws, Top 14, Six Nations, etc. are observational only.

## Live-forward (the real exam)

```powershell
python -u scripts/maz_boss_killer_v2.py --phase freeze
python -u scripts/maz_boss_killer_v2.py --phase live
python -u scripts/maz_boss_killer_v2.py --phase status
```

`freeze` trains one A5 ensemble on all completed matches before the freeze point
and writes `artifacts_killer_v2/FROZEN.json` plus `live_A5_seed_{42,1337,9001}.pt`.

`live` then, for each new fixture still before kickoff:

1. Predict with production V4 (AI-only, no odds)
2. Predict with frozen Killer V2
3. Save both rows with hashes and timestamp
4. Lock the row — never regenerate after the result is known
5. After the match, append actual scores only

Predetermined comparison checkpoints: **100, 250, 500** settled matches
(`LIVE_CHECKPOINT_{n}.json`). Do not redesign the model after a bad weekend.

Daily Highlightly sync also calls this ledger when freeze weights exist.
Production champion models (8×v5 / 2×v4) are unchanged.
