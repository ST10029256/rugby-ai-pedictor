# Killer (sealed 75/25)

Score-only rugby model. Does **not** modify V4/V5.

## Run

```bash
python scripts/maz_boss_killer.py --db data.sqlite --out-dir artifacts_killer
```

Useful flags:
- `--develop-only` — train/calibrate inside 75%, never open sealed 25%
- `--skip-baselines` — Killer exam only (no fair V4/V5 retrain)
- `--epochs 35 --ssl-epochs 4 --seeds 42,1337,9001,2026,7777`

## Protocol

1. Per-league chronological **75% train / 25% sealed**
2. Develop inside 75% (~80/20) for early stopping + calibration
3. Discard develop weights; retrain on full 75%
4. Open sealed 25%; compare Killer vs V4/V5 trained on the **same** 75%
5. Write ledger + fingerprints (no odds)

## Artifacts

- `KILLER_SPLITS.json`, `TRAIN_IDS.sha256`, `TEST_IDS.sha256`
- `killer_seed_*.pt`, `calibrator.json`
- `KILLER_SEALED_EXAM_REPORT.json`, `KILLER_EXAM_LEDGER.jsonl`
- `FINGERPRINTS.json`
