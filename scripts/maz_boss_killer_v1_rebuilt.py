"""Killer V1 Rebuilt — closed A0–A5 develop / 2936 historical benchmark.

A5 is frozen as Killer V2. Do not rerun develop/exam to redesign the model.
Live-forward is scripts/maz_boss_killer_v2.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))
sys.path.insert(0, str(ROOT / "scripts"))

from prediction.config import LEAGUE_MAPPINGS  # noqa: E402
from prediction.features import FeatureConfig, build_feature_table  # noqa: E402

from killer.metrics import compute_metrics, confidence_buckets  # noqa: E402
from killer.splits import assert_no_leakage, build_split_bundle, load_split_bundle, sha256_ids  # noqa: E402

from killer_v1_rebuilt.config import (  # noqa: E402
    ABLATIONS,
    ARTIFACT_DIR,
    DEFAULT_LEAGUE_IDS,
    LEGACY_SPLIT_DIR,
    MAX_EPOCHS,
    SEEDS,
    SEQ_DIM,
    VERSION,
)
from killer_v1_rebuilt.dataset import build_batch, build_idx_maps, filter_batch  # noqa: E402
from killer_v1_rebuilt.select import select_ablation  # noqa: E402
from killer_v1_rebuilt.train import ensemble_predict, flags_for, train_one  # noqa: E402

LOG = logging.getLogger("killer_v1_rebuilt")


def load_df(db: Path, league_ids: List[int]) -> pd.DataFrame:
    conn = sqlite3.connect(str(db))
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False))
    conn.close()
    df = df[df["league_id"].isin(league_ids)].copy()
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    df.sort_values(["date_event", "event_id"], inplace=True)
    return df.reset_index(drop=True)


def load_splits(df, league_ids, out_dir: Path):
    legacy = ROOT / LEGACY_SPLIT_DIR / "KILLER_SPLITS.json"
    if legacy.exists():
        bundle = load_split_bundle(legacy)
        LOG.info("Reusing Killer V1 split fingerprints train=%s sealed=%s", bundle.fingerprint["train_ids.sha256"][:12], bundle.fingerprint["sealed_ids.sha256"][:12])
        return bundle
    bundle = build_split_bundle(df, league_ids)
    assert_no_leakage(bundle)
    LOG.warning("Legacy splits missing; rebuilt identical 75/25 from current DB")
    return bundle


def eval_batch(models, batch, device, alpha, use_draw) -> Dict[str, Any]:
    pred = ensemble_predict(models, batch, device, alpha, use_draw)
    met = compute_metrics(
        y_outcome=batch.y_outcome, p_hda=pred["p_hda"],
        y_home=batch.y_home, y_away=batch.y_away,
        pred_home=pred["mu"][:, 0], pred_away=pred["mu"][:, 1],
    )
    return {"metrics": met.as_dict(), "pred": pred, "buckets": confidence_buckets(batch.y_outcome, pred["p_hda"])}


def run_develop(df, bundle, out_dir: Path, device, seeds):
    df_train = df[df["event_id"].astype(int).isin(set(bundle.train_ids))].copy()
    team_to_idx, league_to_idx = build_idx_maps(df_train)
    ladder = []
    for ab in ABLATIONS:
        LOG.info("=== develop %s seq_dim=%s ===", ab, SEQ_DIM[ab])
        full = build_batch(df_train, ab, team_to_idx=team_to_idx, league_to_idx=league_to_idx)
        tr = filter_batch(full, bundle.develop_train_ids)
        va = filter_batch(full, bundle.develop_val_ids)
        models, alphas, hashes = [], [], []
        for seed in seeds:
            LOG.info("  %s seed=%s", ab, seed)
            m, info = train_one(
                ablation=ab,
                n_teams=full.meta["n_teams"],
                n_leagues=full.meta["n_leagues"],
                seq_dim=full.meta["seq_dim"],
                train=tr,
                val=va,
                seed=seed,
                device=device,
            )
            models.append(m)
            alphas.append(info["alpha"])
            hashes.append(info["checkpoint_hash"])
            (out_dir / f"develop_{ab}_seed_{seed}.pt").write_bytes(info["blob"])
        alpha = float(np.median(alphas))
        ev = eval_batch(models, va, device, alpha, flags_for(ab)["use_draw"])
        row = {"ablation": ab, "alpha": alpha, **ev["metrics"], "hashes": hashes}
        ladder.append(row)
        LOG.info(
            "  %s val acc=%.3f brier=%.3f home_mae=%.2f margin_mae=%.2f",
            ab, row["accuracy"], row["brier"], row["home_mae"], row["margin_mae"],
        )
    chosen = select_ablation(ladder)
    LOG.info("Selected ablation: %s", chosen)
    (out_dir / "DEVELOP_ABLATION_LADDER.json").write_text(json.dumps({"ladder": ladder, "chosen": chosen}, indent=2), encoding="utf-8")
    return chosen, ladder, team_to_idx, league_to_idx


def causal_train_ids(df, bundle, league_id: int):
    sealed = df[df["event_id"].astype(int).isin(set(bundle.leagues[league_id].sealed_ids))]
    t_l = pd.to_datetime(sealed["date_event"]).min()
    train = df[df["event_id"].astype(int).isin(set(bundle.train_ids))].copy()
    train["date_event"] = pd.to_datetime(train["date_event"])
    keep = train[train["date_event"] < t_l]["event_id"].astype(int).tolist()
    return keep, str(t_l)


def run_exam(df, bundle, ablation: str, out_dir: Path, device, seeds, team_to_idx, league_to_idx):
    from killer.exam_baselines import run_baseline_exam

    df_all = df[df["event_id"].astype(int).isin(set(bundle.train_ids) | set(bundle.sealed_ids))].copy()
    full = build_batch(df_all, ablation, team_to_idx=team_to_idx, league_to_idx=league_to_idx)
    use_draw = flags_for(ablation)["use_draw"]
    per_league = {}
    all_p, all_mu, all_y, all_yh, all_ya, all_ids = [], [], [], [], [], []

    for lid, sp in sorted(bundle.leagues.items()):
        ids, t_l = causal_train_ids(df, bundle, lid)
        LOG.info("Exam league %s T_L=%s causal_train=%s sealed=%s", lid, t_l, len(ids), len(sp.sealed_ids))
        (out_dir / f"{lid}_EFFECTIVE_TRAIN.sha256").write_text(sha256_ids(ids) + "\n", encoding="utf-8")
        if len(ids) < 20 or len(sp.sealed_ids) == 0:
            LOG.warning("skip league %s (too few rows)", lid)
            continue
        tr = filter_batch(full, ids)
        te = filter_batch(full, sp.sealed_ids)
        models, alphas = [], []
        for seed in seeds:
            m, info = train_one(
                ablation=ablation,
                n_teams=full.meta["n_teams"],
                n_leagues=full.meta["n_leagues"],
                seq_dim=full.meta["seq_dim"],
                train=tr,
                val=None,
                seed=seed,
                device=device,
                max_epochs=min(MAX_EPOCHS, 25),
                patience=10**9,
            )
            models.append(m)
            alphas.append(info["alpha"])
            (out_dir / f"exam_{ablation}_league_{lid}_seed_{seed}.pt").write_bytes(info["blob"])
        alpha = float(np.median(alphas)) if alphas else 0.8
        pred = ensemble_predict(models, te, device, alpha, use_draw)
        met = compute_metrics(
            y_outcome=te.y_outcome, p_hda=pred["p_hda"],
            y_home=te.y_home, y_away=te.y_away,
            pred_home=pred["mu"][:, 0], pred_away=pred["mu"][:, 1],
        )
        per_league[str(lid)] = {"name": LEAGUE_MAPPINGS.get(lid, str(lid)), "T_L": t_l, "n_train": len(ids), **met.as_dict()}
        all_p.append(pred["p_hda"])
        all_mu.append(pred["mu"])
        all_y.append(te.y_outcome)
        all_yh.append(te.y_home)
        all_ya.append(te.y_away)
        all_ids.append(te.event_ids)
        LOG.info("  rebuilt %s acc=%.3f brier=%.3f mae=%.2f", lid, met.accuracy, met.brier, met.home_mae)

    p = np.concatenate(all_p, 0)
    mu = np.concatenate(all_mu, 0)
    y = np.concatenate(all_y, 0)
    yh = np.concatenate(all_yh, 0)
    ya = np.concatenate(all_ya, 0)
    global_m = compute_metrics(y_outcome=y, p_hda=p, y_home=yh, y_away=ya, pred_home=mu[:, 0], pred_away=mu[:, 1])

    baselines = {}
    LOG.info("Fair exam V4/V5 on same causal pools (aggregated via original helper on full 75% for comparability)")
    try:
        for fam in ("v4", "v5"):
            base = run_baseline_exam(
                family=fam, df=df, train_ids=bundle.train_ids, sealed_ids=bundle.sealed_ids,
                device=device, seeds=seeds,
            )
            baselines[fam] = {"metrics": base["metrics"]}
            LOG.info("  %s acc=%.3f brier=%.3f", fam, base["metrics"]["accuracy"], base["metrics"]["brier"])
    except Exception as e:
        LOG.exception("baseline failed: %s", e)

    report = {
        "version": VERSION,
        "label": "Fixed Historical Benchmark (not a pristine holdout for rebuilt Killer)",
        "chosen_ablation": ablation,
        "killer_v1_rebuilt_global": global_m.as_dict(),
        "by_league": per_league,
        "baselines_exam_v4_v5": baselines,
        "confidence_buckets": confidence_buckets(y, p),
        "n_benchmark": int(len(y)),
    }
    (out_dir / "KILLER_V1_REBUILT_BENCHMARK.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    LOG.info("BENCHMARK rebuilt acc=%.4f brier=%.4f home_mae=%.2f", global_m.accuracy, global_m.brier, global_m.home_mae)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(ROOT / "data.sqlite"))
    p.add_argument("--out-dir", default=str(ROOT / ARTIFACT_DIR))
    p.add_argument("--phase", choices=["develop", "exam", "all"], default="all")
    p.add_argument("--ablation", default=None, help="Skip develop and use this ablation for exam")
    p.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    p.add_argument("--device", default="cpu")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.phase in ("develop", "exam", "all"):
        LOG.warning(
            "A5 is frozen as Killer V2. This historical develop/exam path is closed; "
            "do not use it to redesign the model. Live-forward: scripts/maz_boss_killer_v2.py"
        )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    device = torch.device(args.device)
    df = load_df(Path(args.db), DEFAULT_LEAGUE_IDS)
    bundle = load_splits(df, DEFAULT_LEAGUE_IDS, out_dir)

    chosen = args.ablation
    team_to_idx = league_to_idx = None
    if args.phase in ("develop", "all") and not args.ablation:
        chosen, _, team_to_idx, league_to_idx = run_develop(df, bundle, out_dir, device, seeds)
    if args.phase in ("exam", "all"):
        if team_to_idx is None:
            df_train = df[df["event_id"].astype(int).isin(set(bundle.train_ids))]
            team_to_idx, league_to_idx = build_idx_maps(df_train)
        if not chosen:
            ladder_path = out_dir / "DEVELOP_ABLATION_LADDER.json"
            chosen = json.loads(ladder_path.read_text(encoding="utf-8"))["chosen"] if ladder_path.exists() else "A3"
        LOG.info("Exam with frozen ablation %s", chosen)
        run_exam(df, bundle, chosen, out_dir, device, seeds, team_to_idx, league_to_idx)


if __name__ == "__main__":
    main()
