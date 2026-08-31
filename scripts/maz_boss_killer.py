#!/usr/bin/env python3
"""
KILLER — sealed 75/25 score-only rugby model.

Phases:
  1) Build immutable chronological splits + fingerprints (per league 75/25)
  2) Develop inside 75% (develop-train / develop-val) — early stopping / calibration only
  3) Discard develop weights; retrain frozen architecture on full 75%
  4) Open sealed 25% exam for Killer (+ optional fair V4/V5 baselines on SAME split)
  5) Write audit ledger, metrics, confidence buckets

No odds. No lineups. No DSG. Does not modify V4/V5 source files.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))
sys.path.insert(0, str(ROOT / "scripts"))

from prediction.config import LEAGUE_MAPPINGS  # noqa: E402
from prediction.features import FeatureConfig, build_feature_table  # noqa: E402

from killer.audit import (  # noqa: E402
    causal_train_ids_for_exam,
    make_prediction_audit,
    report_temporal_firewall,
    write_exam_ledger,
    write_fingerprint_manifest,
)
from killer.config import (  # noqa: E402
    ARTIFACT_DIR_NAME,
    DEFAULT_LEAGUE_IDS,
    KILLER_ARCHITECTURE,
    KILLER_SEEDS,
    KILLER_VERSION,
)
from killer.features import build_idx_maps_from_train, build_killer_features, filter_batch  # noqa: E402
from killer.metrics import confidence_buckets  # noqa: E402
from killer.splits import (  # noqa: E402
    assert_no_leakage,
    build_split_bundle,
    save_split_bundle,
    sha256_json,
    split_summary,
)
from killer.train_loop import (  # noqa: E402
    eval_ensemble,
    fit_ensemble_calibrator,
    train_one_model,
)

LOG = logging.getLogger("killer")


def default_db_path() -> Path:
    p_main = ROOT / "data.sqlite"
    p_fn = ROOT / "rugby-ai-predictor" / "data.sqlite"
    return p_main if p_main.exists() else p_fn


def load_completed_df(conn: sqlite3.Connection, league_ids: List[int]) -> pd.DataFrame:
    cfg = FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False)
    df = build_feature_table(conn, cfg)
    df = df[df["league_id"].isin(list(league_ids))].copy()
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    if df.empty:
        return df
    if "event_id" not in df.columns and "id" in df.columns:
        df = df.rename(columns={"id": "event_id"})
    df.sort_values(["date_event", "event_id"], inplace=True)
    return df.reset_index(drop=True)


def per_league_metrics(batch, pred: Dict[str, np.ndarray], league_names: Dict[int, str]) -> Dict[str, Any]:
    from killer.metrics import compute_metrics

    out: Dict[str, Any] = {}
    for lid in sorted(set(int(x) for x in batch.league_ids)):
        m = batch.league_ids == lid
        if not np.any(m):
            continue
        met = compute_metrics(
            y_outcome=batch.y_outcome[m],
            p_hda=pred["p_hda"][m],
            y_home=batch.y_home[m],
            y_away=batch.y_away[m],
            pred_home=pred["pred_home"][m],
            pred_away=pred["pred_away"][m],
        )
        out[str(lid)] = {"name": league_names.get(lid, str(lid)), **met.as_dict()}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Killer sealed 75/25 rugby model")
    parser.add_argument("--db", type=str, default=str(default_db_path()))
    parser.add_argument("--out-dir", type=str, default=str(ROOT / ARTIFACT_DIR_NAME))
    parser.add_argument("--leagues", type=str, default=",".join(str(x) for x in DEFAULT_LEAGUE_IDS))
    parser.add_argument("--seeds", type=str, default=",".join(str(x) for x in KILLER_SEEDS))
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--ssl-epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--skip-baselines", action="store_true", help="Skip fair V4/V5 sealed exam")
    parser.add_argument("--develop-only", action="store_true", help="Stop after develop phase (do NOT open sealed)")
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    league_ids = [int(x.strip()) for x in args.leagues.split(",") if x.strip()]
    seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")

    LOG.info("=== KILLER %s ===", KILLER_VERSION)
    LOG.info("architecture=%s", KILLER_ARCHITECTURE)
    LOG.info("db=%s device=%s seeds=%s", args.db, device, seeds)

    conn = sqlite3.connect(args.db)
    df = load_completed_df(conn, league_ids)
    conn.close()
    if df.empty:
        raise SystemExit("No completed games found")

    # --- Immutable splits ---
    bundle = build_split_bundle(df, league_ids)
    assert_no_leakage(bundle)
    save_split_bundle(bundle, out_dir)
    summary = split_summary(bundle, LEAGUE_MAPPINGS)
    (out_dir / "split_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    LOG.info("Split fingerprint train=%s sealed=%s", bundle.fingerprint["train_ids.sha256"][:12], bundle.fingerprint["sealed_ids.sha256"][:12])
    for row in summary:
        LOG.info(
            "  %s (%s): total=%s train75=%s sealed25=%s",
            row["name"],
            row["league_id"],
            row["n_total"],
            row["n_train_75"],
            row["n_sealed_25"],
        )

    # Feature build on TRAIN 75% ONLY for index/stats scope used before exam.
    # For sealed predictions we rebuild features on train+sealed chronology but
    # model weights / calibrator never saw sealed labels.
    df_train = df[df["event_id"].astype(int).isin(set(bundle.train_ids))].copy().reset_index(drop=True)
    team_to_idx, league_to_idx = build_idx_maps_from_train(df_train)
    train_feat_all = build_killer_features(
        df_train,
        team_to_idx=team_to_idx,
        league_to_idx=league_to_idx,
    )
    n_teams = int(train_feat_all.meta["n_teams"])
    n_leagues = int(train_feat_all.meta["n_leagues"])
    firewall = report_temporal_firewall(df, bundle)
    (out_dir / "TEMPORAL_FIREWALL.json").write_text(json.dumps(firewall, indent=2, default=str), encoding="utf-8")
    LOG.info(
        "Temporal firewall: train-after-global-first-sealed=%s same-team-future-train=%s",
        firewall["n_train_after_global_first_sealed"],
        firewall["n_train_after_same_team_sealed_kickoff"],
    )

    develop_train = filter_batch(train_feat_all, bundle.develop_train_ids)
    develop_val = filter_batch(train_feat_all, bundle.develop_val_ids)
    LOG.info("Develop sizes: train=%s val=%s", len(develop_train.event_ids), len(develop_val.event_ids))

    model_config = {
        "version": KILLER_VERSION,
        "architecture": KILLER_ARCHITECTURE,
        "n_teams": n_teams,
        "n_leagues": n_leagues,
        "seeds": seeds,
        "epochs": args.epochs,
        "ssl_epochs": args.ssl_epochs,
        "no_odds": True,
        "no_lineups": True,
        "train_fraction": 0.75,
    }
    (out_dir / "MODEL_CONFIG.json").write_text(json.dumps(model_config, indent=2), encoding="utf-8")

    # --- Phase A: develop (for early stopping + calibration protocol only) ---
    LOG.info("Phase A: develop training inside 75% (sealed untouched)")
    develop_models = []
    for seed in seeds:
        LOG.info("  develop seed=%s", seed)
        tr = train_one_model(
            n_teams=n_teams,
            n_leagues=n_leagues,
            train_batch=develop_train,
            val_batch=develop_val,
            seed=seed,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            ssl_epochs=args.ssl_epochs,
        )
        develop_models.append(tr)
        (out_dir / f"develop_seed_{seed}.pt").write_bytes(tr.checkpoint_bytes)

    develop_cal = fit_ensemble_calibrator([t.model for t in develop_models], develop_val, device)
    develop_metrics, _ = eval_ensemble([t.model for t in develop_models], develop_val, device, calibrator=develop_cal)
    (out_dir / "develop_val_metrics.json").write_text(json.dumps({"metrics": develop_metrics, "calibrator": develop_cal}, indent=2), encoding="utf-8")
    LOG.info("Develop-val accuracy=%.3f brier=%.3f logloss=%.3f", develop_metrics["accuracy"], develop_metrics["brier"], develop_metrics["log_loss"])

    if args.develop_only:
        LOG.warning("Stopping before sealed exam (--develop-only). Sealed 25% remains untouched.")
        return

    # --- Phase B: throw away develop weights; retrain on causal 75% ---
    LOG.info("Phase B: discard develop weights; retrain on first 75% with same-team causal filter")
    causal_ids = causal_train_ids_for_exam(df, bundle)
    LOG.info("Causal train rows=%s / 75%% train=%s (dropped same-team post-sealed)", len(causal_ids), len(bundle.train_ids))
    final_train_batch = filter_batch(train_feat_all, causal_ids)
    final_models = []
    hashes = []
    for seed in seeds:
        LOG.info("  final seed=%s", seed)
        tr = train_one_model(
            n_teams=n_teams,
            n_leagues=n_leagues,
            train_batch=final_train_batch,
            val_batch=None,  # no peeking at sealed; no re-tuning
            seed=seed,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            ssl_epochs=args.ssl_epochs,
            patience=10**9,
        )
        final_models.append(tr)
        hashes.append(tr.checkpoint_hash)
        (out_dir / f"killer_seed_{seed}.pt").write_bytes(tr.checkpoint_bytes)

    # Calibration protocol frozen from develop-val fit (NOT refit on sealed)
    calibrator = develop_cal
    (out_dir / "calibrator.json").write_text(json.dumps(calibrator, indent=2), encoding="utf-8")

    # --- Phase C: open sealed 25% ---
    LOG.info("Phase C: opening sealed 25% exam")
    # Build features with train+sealed chronology so histories are correct at sealed kickoffs,
    # but indices/stats come from train-fitted maps.
    df_exam_scope = df[df["event_id"].astype(int).isin(set(bundle.train_ids) | set(bundle.sealed_ids))].copy().reset_index(drop=True)
    feat_exam_scope = build_killer_features(
        df_exam_scope,
        team_to_idx=team_to_idx,
        league_to_idx=league_to_idx,
    )
    sealed_batch = filter_batch(feat_exam_scope, bundle.sealed_ids)
    LOG.info("Sealed rows=%s", len(sealed_batch.event_ids))

    killer_metrics, killer_pred = eval_ensemble(
        [t.model for t in final_models],
        sealed_batch,
        device,
        calibrator=calibrator,
    )
    killer_by_league = per_league_metrics(sealed_batch, killer_pred, LEAGUE_MAPPINGS)
    killer_buckets = confidence_buckets(sealed_batch.y_outcome, killer_pred["p_hda"])

    # Audit ledger
    ledger_rows = []
    ck_hash = sha256_json(hashes)
    for i in range(len(sealed_batch.event_ids)):
        p = killer_pred["p_hda"][i]
        row = make_prediction_audit(
            match_id=int(sealed_batch.event_ids[i]),
            league_id=int(sealed_batch.league_ids[i]),
            kickoff=str(sealed_batch.dates[i]),
            home_team_id=int(sealed_batch.home_team_ids[i]),
            away_team_id=int(sealed_batch.away_team_ids[i]),
            model_version=KILLER_VERSION,
            checkpoint_hash=ck_hash,
            p_away=float(p[0]),
            p_draw=float(p[1]),
            p_home=float(p[2]),
            expected_home=float(killer_pred["pred_home"][i]),
            expected_away=float(killer_pred["pred_away"][i]),
            margin=float(killer_pred["pred_home"][i] - killer_pred["pred_away"][i]),
            uncertainty=float(killer_pred["uncertainty"][i]),
            seed_std=float(killer_pred["seed_std"][i]),
        )
        # Attach outcomes for the exam report (predictions were created without using them for training)
        hs = float(sealed_batch.y_home[i])
        aw = float(sealed_batch.y_away[i])
        row["outcome_home"] = hs
        row["outcome_away"] = aw
        row["outcome_result"] = "home" if hs > aw else ("away" if hs < aw else "draw")
        ledger_rows.append(row)
    write_exam_ledger(out_dir / "KILLER_EXAM_LEDGER.jsonl", ledger_rows)

    report: Dict[str, Any] = {
        "version": KILLER_VERSION,
        "architecture": KILLER_ARCHITECTURE,
        "fingerprint": bundle.fingerprint,
        "temporal_firewall": firewall,
        "checkpoint_hashes": hashes,
        "ensemble_checkpoint_hash": ck_hash,
        "calibrator": calibrator,
        "killer_global": killer_metrics,
        "killer_by_league": killer_by_league,
        "killer_confidence_buckets": killer_buckets,
        "baselines": {},
    }

    if not args.skip_baselines:
        LOG.info("Fair baselines: retrain V4/V5 on same 75%%, exam on same 25%%")
        from killer.exam_baselines import run_baseline_exam

        for fam in ("v4", "v5"):
            try:
                base = run_baseline_exam(
                    family=fam,
                    df=df,
                    train_ids=causal_ids,
                    sealed_ids=bundle.sealed_ids,
                    device=device,
                    seeds=seeds[:3],
                )
                report["baselines"][fam] = {
                    "metrics": base["metrics"],
                    "confidence_buckets": base["confidence_buckets"],
                }
                LOG.info(
                    "  %s sealed acc=%.3f brier=%.3f logloss=%.3f",
                    fam.upper(),
                    base["metrics"]["accuracy"],
                    base["metrics"]["brier"],
                    base["metrics"]["log_loss"],
                )
            except Exception as e:
                LOG.exception("Baseline %s failed: %s", fam, e)
                report["baselines"][fam] = {"error": str(e)}

    # Scoreboard
    scoreboard = {
        "metric": ["accuracy", "brier", "log_loss", "ece", "home_mae", "away_mae", "margin_mae"],
        "killer": [killer_metrics.get(m) for m in ["accuracy", "brier", "log_loss", "ece", "home_mae", "away_mae", "margin_mae"]],
        "v4": [report["baselines"].get("v4", {}).get("metrics", {}).get(m) for m in ["accuracy", "brier", "log_loss", "ece", "home_mae", "away_mae", "margin_mae"]],
        "v5": [report["baselines"].get("v5", {}).get("metrics", {}).get(m) for m in ["accuracy", "brier", "log_loss", "ece", "home_mae", "away_mae", "margin_mae"]],
    }
    report["scoreboard"] = scoreboard
    (out_dir / "KILLER_SEALED_EXAM_REPORT.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    write_fingerprint_manifest(
        out_dir,
        {
            **bundle.fingerprint,
            "FEATURE_SCHEMA.sha256": sha256_json(train_feat_all.meta.get("rating_feat_names")),
            "MODEL_CONFIG.sha256": sha256_json(model_config),
            "CHECKPOINT.sha256": ck_hash,
        },
    )

    LOG.info("=== SEALED EXAM SCOREBOARD ===")
    LOG.info("Killer  acc=%.4f brier=%.4f logloss=%.4f ece=%.4f", killer_metrics["accuracy"], killer_metrics["brier"], killer_metrics["log_loss"], killer_metrics["ece"])
    if report["baselines"].get("v4", {}).get("metrics"):
        m = report["baselines"]["v4"]["metrics"]
        LOG.info("V4      acc=%.4f brier=%.4f logloss=%.4f ece=%.4f", m["accuracy"], m["brier"], m["log_loss"], m["ece"])
    if report["baselines"].get("v5", {}).get("metrics"):
        m = report["baselines"]["v5"]["metrics"]
        LOG.info("V5      acc=%.4f brier=%.4f logloss=%.4f ece=%.4f", m["accuracy"], m["brier"], m["log_loss"], m["ece"])
    LOG.info("Artifacts written to %s", out_dir)


if __name__ == "__main__":
    main()
