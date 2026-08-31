"""Killer V2 live-forward ledger.

Lock V4 + Killer V2 predictions before kickoff. Append actuals after the match.
Never regenerate a locked prediction.
"""

from __future__ import annotations

import io
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch

from killer.metrics import compute_metrics

from .config import (
    DEFAULT_LEAGUE_IDS,
    FROZEN_ABLATION,
    FROZEN_ALPHA,
    LIVE_CHECKPOINTS,
    LIVE_LOCK_HORIZON_HOURS,
    MAX_EPOCHS,
    SEEDS,
    SEQ_DIM,
    VERSION,
)
from .dataset import build_batch, build_idx_maps, filter_batch
from .freeze import (
    freeze_is_ready,
    hashes_from_live_dir,
    live_seed_paths,
    load_freeze_manifest,
    write_freeze_manifest,
)
from .model import RebuiltModel
from .train import ensemble_predict, flags_for, train_one
from .v4_control import V4Control

LOG = logging.getLogger("killer_v2.live")
LEDGER_NAME = "KILLER_V2_LIVE_LEDGER.jsonl"


def _torch_load(source, map_location):
    try:
        return torch.load(source, map_location=map_location, weights_only=False)
    except TypeError:
        return torch.load(source, map_location=map_location)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kickoff(date_event: Any, timestamp: Any) -> Optional[datetime]:
    raw = timestamp or date_event
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    if not text or text.lower() == "none":
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ledger_path(out_dir: Path) -> Path:
    return out_dir / LEDGER_NAME


def read_ledger(out_dir: Path) -> List[Dict[str, Any]]:
    path = ledger_path(out_dir)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_ledger(out_dir: Path, rows: List[Dict[str, Any]]) -> None:
    path = ledger_path(out_dir)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
    tmp.replace(path)


def locked_ids(rows: Iterable[Dict[str, Any]]) -> set:
    return {int(r["match_id"]) for r in rows}


def _norm_name(name: Any) -> str:
    return " ".join(str(name or "").strip().lower().split())


def fixture_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    kickoff = str(row.get("kickoff") or "")[:10]
    return (_norm_name(row.get("home_team")), _norm_name(row.get("away_team")), kickoff)


def locked_fixture_keys(rows: Iterable[Dict[str, Any]]) -> set:
    return {fixture_key(r) for r in rows}


def load_scored_history(db: Path, league_ids: List[int]) -> pd.DataFrame:
    from prediction.features import FeatureConfig, build_feature_table

    conn = sqlite3.connect(str(db))
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False))
    conn.close()
    df = df[df["league_id"].isin(league_ids)].copy()
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    df.sort_values(["date_event", "event_id"], inplace=True)
    return df.reset_index(drop=True)


def load_upcoming_rows(db: Path, league_ids: List[int]) -> pd.DataFrame:
    placeholders = ",".join("?" * len(league_ids))
    conn = sqlite3.connect(str(db))
    df = pd.read_sql_query(
        f"""
        SELECT e.id AS event_id, e.league_id, e.date_event, e.timestamp,
               e.home_team_id, e.away_team_id, e.home_score, e.away_score,
               ht.name AS home_team, at.name AS away_team
        FROM event e
        JOIN team ht ON ht.id = e.home_team_id
        JOIN team at ON at.id = e.away_team_id
        WHERE e.league_id IN ({placeholders})
          AND e.home_score IS NULL AND e.away_score IS NULL
        ORDER BY e.date_event ASC, e.id ASC
        """,
        conn,
        params=list(league_ids),
    )
    conn.close()
    return df


def load_completed_lookup(db: Path, match_ids: List[int]) -> Dict[int, Tuple[int, int]]:
    if not match_ids:
        return {}
    placeholders = ",".join("?" * len(match_ids))
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        f"""
        SELECT id, home_score, away_score
        FROM event
        WHERE id IN ({placeholders})
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        """,
        match_ids,
    )
    out = {int(r[0]): (int(r[1]), int(r[2])) for r in cur.fetchall()}
    conn.close()
    return out


def load_completed_by_fixture(
    db: Path, league_ids: List[int]
) -> Dict[Tuple[str, str, str], Tuple[int, int]]:
    placeholders = ",".join("?" * len(league_ids))
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        f"""
        SELECT e.timestamp, e.date_event, e.home_score, e.away_score,
               ht.name AS home_team, at.name AS away_team
        FROM event e
        JOIN team ht ON ht.id = e.home_team_id
        JOIN team at ON at.id = e.away_team_id
        WHERE e.league_id IN ({placeholders})
          AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
        """,
        list(league_ids),
    )
    out: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
    for ts, date_event, hs, aw, home, away in cur.fetchall():
        kickoff = _parse_kickoff(date_event, ts)
        day = kickoff.date().isoformat() if kickoff else str(date_event or "")[:10]
        out[(_norm_name(home), _norm_name(away), day)] = (int(hs), int(aw))
    conn.close()
    return out


def load_live_ensemble(out_dir: Path, device: torch.device):
    manifest = load_freeze_manifest(out_dir)
    n_teams = int(manifest["n_teams"])
    n_leagues = int(manifest["n_leagues"])
    seq_dim = int(SEQ_DIM[FROZEN_ABLATION])
    fl = flags_for(FROZEN_ABLATION)
    models = []
    for path in live_seed_paths(out_dir):
        ckpt = _torch_load(path, map_location=device)
        model = RebuiltModel(n_teams, n_leagues, seq_dim, **fl).to(device)
        model.load_state_dict(ckpt["model"])
        model.eval()
        models.append(model)
    team_to_idx = {int(k): int(v) for k, v in manifest["team_to_idx"].items()}
    league_to_idx = {int(k): int(v) for k, v in manifest["league_to_idx"].items()}
    alpha = float(manifest.get("alpha", FROZEN_ALPHA))
    return models, alpha, team_to_idx, league_to_idx, manifest


def freeze_production(
    *,
    df_scored: pd.DataFrame,
    out_dir: Path,
    device: torch.device,
    freeze_cutoff: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Train one A5 ensemble on all completed matches before freeze. Idempotent."""
    if freeze_is_ready(out_dir):
        LOG.info("Killer V2 freeze already present at %s", out_dir)
        return load_freeze_manifest(out_dir)

    cutoff = freeze_cutoff or _utc_now()
    df = df_scored.copy()
    df["date_event"] = pd.to_datetime(df["date_event"], utc=True, errors="coerce")
    df = df[df["date_event"] < cutoff].copy()
    if len(df) < 100:
        raise RuntimeError(f"Not enough completed matches to freeze ({len(df)})")

    team_to_idx, league_to_idx = build_idx_maps(df)
    full = build_batch(df, FROZEN_ABLATION, team_to_idx=team_to_idx, league_to_idx=league_to_idx)
    blobs = []
    seed_hashes = {}
    for seed in SEEDS:
        LOG.info("Freeze train A5 seed=%s n=%s", seed, len(df))
        model, info = train_one(
            ablation=FROZEN_ABLATION,
            n_teams=full.meta["n_teams"],
            n_leagues=full.meta["n_leagues"],
            seq_dim=full.meta["seq_dim"],
            train=full,
            val=None,
            seed=seed,
            device=device,
            max_epochs=MAX_EPOCHS,
            patience=10**9,
        )
        ckpt = _torch_load(io.BytesIO(info["blob"]), map_location="cpu")
        ckpt["alpha"] = FROZEN_ALPHA
        buf = io.BytesIO()
        torch.save(ckpt, buf)
        blob = buf.getvalue()
        path = out_dir / f"live_{FROZEN_ABLATION}_seed_{seed}.pt"
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        blobs.append(blob)
        seed_hashes[path.name] = info["checkpoint_hash"]
        del model

    extra = {
        **hashes_from_live_dir(out_dir),
        "n_train": int(len(df)),
        "n_teams": int(full.meta["n_teams"]),
        "n_leagues": int(full.meta["n_leagues"]),
        "freeze_cutoff": cutoff.isoformat(),
        "team_to_idx": {str(k): int(v) for k, v in team_to_idx.items()},
        "league_to_idx": {str(k): int(v) for k, v in league_to_idx.items()},
        "seed_hashes_pre_alpha_stamp": seed_hashes,
    }
    path = write_freeze_manifest(out_dir, extra)
    LOG.info("Wrote freeze manifest %s", path)
    return json.loads(path.read_text(encoding="utf-8"))


def _winner_from_scores(home: int, away: int) -> str:
    if home > away:
        return "H"
    if away > home:
        return "A"
    return "D"


def lock_upcoming(
    *,
    db: Path,
    out_dir: Path,
    device: torch.device,
    artifacts_v4: Path,
    horizon_hours: int = LIVE_LOCK_HORIZON_HOURS,
) -> Dict[str, int]:
    stats = {"scanned": 0, "locked": 0, "skipped_existing": 0, "skipped_window": 0, "skipped_v4": 0, "errors": 0}
    if not freeze_is_ready(out_dir):
        raise FileNotFoundError("Killer V2 freeze weights missing; run --phase freeze")

    rows = read_ledger(out_dir)
    have_ids = locked_ids(rows)
    have_keys = locked_fixture_keys(rows)
    upcoming = load_upcoming_rows(db, DEFAULT_LEAGUE_IDS)
    now = _utc_now()
    horizon = now + timedelta(hours=int(horizon_hours))

    candidates = []
    for rec in upcoming.to_dict("records"):
        stats["scanned"] += 1
        kickoff = _parse_kickoff(rec.get("date_event"), rec.get("timestamp"))
        if kickoff is None or not (now < kickoff <= horizon):
            stats["skipped_window"] += 1
            continue
        key = (_norm_name(rec.get("home_team")), _norm_name(rec.get("away_team")), kickoff.date().isoformat())
        # Highlightly reuses event IDs. Skip only the same fixture, not a recycled id.
        if key in have_keys:
            stats["skipped_existing"] += 1
            continue
        candidates.append((rec, kickoff))

    if not candidates:
        return stats

    models, alpha, team_to_idx, league_to_idx, manifest = load_live_ensemble(out_dir, device)
    history = load_scored_history(db, DEFAULT_LEAGUE_IDS)
    up_df = pd.DataFrame([c[0] for c in candidates])
    hist_keep = ["event_id", "league_id", "date_event", "home_team_id", "away_team_id", "home_score", "away_score"]
    combined = pd.concat(
        [history[hist_keep], up_df[hist_keep]],
        ignore_index=True,
    )
    combined.sort_values(["date_event", "event_id"], inplace=True)
    full = build_batch(
        combined,
        FROZEN_ABLATION,
        team_to_idx=team_to_idx,
        league_to_idx=league_to_idx,
    )
    cand_ids = [int(c[0]["event_id"]) for c in candidates]
    te = filter_batch(full, cand_ids)
    pred = ensemble_predict(models, te, device, alpha, flags_for(FROZEN_ABLATION)["use_draw"])
    by_id = {int(eid): i for i, eid in enumerate(te.event_ids)}

    v4 = V4Control(db, artifacts_v4)
    hashes = {
        "killer_checkpoint_hash": manifest["killer_checkpoint_hash"],
        "feature_schema_hash": manifest["feature_schema_hash"],
        "model_config_hash": manifest["model_config_hash"],
    }
    from prediction.config import LEAGUE_MAPPINGS

    new_rows = []
    for rec, kickoff in candidates:
        eid = int(rec["event_id"])
        idx = by_id.get(eid)
        if idx is None:
            stats["errors"] += 1
            continue
        try:
            v4_out = v4.predict(
                league_id=int(rec["league_id"]),
                home_team=str(rec["home_team"]),
                away_team=str(rec["away_team"]),
                match_date=str(rec.get("date_event") or kickoff.date()),
            )
        except Exception:
            LOG.exception("V4 predict failed for match %s", eid)
            v4_out = None
        if v4_out is None:
            stats["skipped_v4"] += 1
            continue
        v4_pred, v4_hash = v4_out
        p = pred["p_hda"][idx]
        mu = pred["mu"][idx]
        lid = int(rec["league_id"])
        row = {
            "match_id": eid,
            "league_id": lid,
            "league": LEAGUE_MAPPINGS.get(lid, str(lid)),
            "kickoff": kickoff.isoformat(),
            "home_team": rec["home_team"],
            "away_team": rec["away_team"],
            "prediction_timestamp": now.isoformat(),
            "locked": True,
            "V4": v4_pred,
            "Killer_V2": {
                "p_home": float(p[2]),
                "p_draw": float(p[1]),
                "p_away": float(p[0]),
                "predicted_home_score": float(mu[0]),
                "predicted_away_score": float(mu[1]),
            },
            "killer_checkpoint_hash": hashes["killer_checkpoint_hash"],
            "feature_schema_hash": hashes["feature_schema_hash"],
            "model_config_hash": hashes["model_config_hash"],
            "v4_checkpoint_hash": v4_hash,
            "model_version": VERSION,
            "actual_home_score": None,
            "actual_away_score": None,
            "actual_result": None,
        }
        new_rows.append(row)
        have_ids.add(eid)
        have_keys.add(
            (_norm_name(rec.get("home_team")), _norm_name(rec.get("away_team")), kickoff.date().isoformat())
        )
        stats["locked"] += 1

    if new_rows:
        _write_ledger(out_dir, rows + new_rows)
        LOG.info("Locked %s Killer V2 live rows", len(new_rows))
    return stats


def settle_actuals(*, db: Path, out_dir: Path) -> Dict[str, int]:
    rows = read_ledger(out_dir)
    pending_rows = [r for r in rows if r.get("actual_home_score") is None]
    by_fx = load_completed_by_fixture(db, DEFAULT_LEAGUE_IDS)
    filled = 0
    for row in rows:
        if row.get("actual_home_score") is not None:
            continue
        got = by_fx.get(fixture_key(row))
        if got is None:
            continue
        hs, aw = got
        # Predictions are immutable. Only actuals may be written.
        row["actual_home_score"] = hs
        row["actual_away_score"] = aw
        row["actual_result"] = _winner_from_scores(hs, aw)
        filled += 1
    if filled:
        _write_ledger(out_dir, rows)
        LOG.info("Settled %s Killer V2 live rows", filled)
    maybe_write_checkpoints(out_dir, rows)
    return {"pending": len(pending_rows), "settled": filled, "ledger": len(rows)}


def _metrics_for(side: str, settled: List[Dict[str, Any]]) -> Dict[str, Any]:
    y = []
    p = []
    yh, ya, ph, pa = [], [], [], []
    for r in settled:
        hs, aw = int(r["actual_home_score"]), int(r["actual_away_score"])
        if hs > aw:
            y.append(2)
        elif hs < aw:
            y.append(0)
        else:
            y.append(1)
        block = r[side]
        p.append([block["p_away"], block["p_draw"], block["p_home"]])
        yh.append(hs)
        ya.append(aw)
        ph.append(block["predicted_home_score"])
        pa.append(block["predicted_away_score"])
    met = compute_metrics(
        y_outcome=np.asarray(y, dtype=np.int64),
        p_hda=np.asarray(p, dtype=np.float32),
        y_home=np.asarray(yh, dtype=np.float32),
        y_away=np.asarray(ya, dtype=np.float32),
        pred_home=np.asarray(ph, dtype=np.float32),
        pred_away=np.asarray(pa, dtype=np.float32),
    )
    return met.as_dict()


def settled_by_kickoff(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    done = [r for r in rows if r.get("actual_home_score") is not None]
    done.sort(key=lambda r: (str(r.get("kickoff") or ""), int(r["match_id"])))
    return done


def maybe_write_checkpoints(out_dir: Path, rows: Optional[List[Dict[str, Any]]] = None) -> List[Path]:
    rows = rows if rows is not None else read_ledger(out_dir)
    done = settled_by_kickoff(rows)
    written: List[Path] = []
    for n in LIVE_CHECKPOINTS:
        path = out_dir / f"LIVE_CHECKPOINT_{n}.json"
        if path.exists() or len(done) < n:
            continue
        slice_n = done[:n]
        report = {
            "checkpoint": n,
            "written_at": _utc_now().isoformat(),
            "n": n,
            "first_kickoff": slice_n[0]["kickoff"],
            "last_kickoff": slice_n[-1]["kickoff"],
            "V4": _metrics_for("V4", slice_n),
            "Killer_V2": _metrics_for("Killer_V2", slice_n),
            "note": (
                "Predetermined live-forward checkpoint. Do not redesign A5 from this. "
                "Success requires Killer V2 to beat V4 on accuracy and Brier/calibration/MAE."
            ),
        }
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        written.append(path)
        LOG.info("Wrote live checkpoint %s", path)
    return written


def live_status(out_dir: Path) -> Dict[str, Any]:
    rows = read_ledger(out_dir)
    done = settled_by_kickoff(rows)
    pending = [r for r in rows if r.get("actual_home_score") is None]
    status = {
        "locked": len(rows),
        "settled": len(done),
        "pending_result": len(pending),
        "next_checkpoint": next((n for n in LIVE_CHECKPOINTS if len(done) < n), None),
        "checkpoints_written": [
            n for n in LIVE_CHECKPOINTS if (out_dir / f"LIVE_CHECKPOINT_{n}.json").exists()
        ],
    }
    if done:
        status["V4"] = _metrics_for("V4", done)
        status["Killer_V2"] = _metrics_for("Killer_V2", done)
        status["interim_only"] = True
        status["note"] = "Interim settled counts are observational. Decisions wait for 100 / 250 / 500."
    return status


def sync_live_ledger(
    db: Path,
    out_dir: Path,
    *,
    device: Optional[torch.device] = None,
    artifacts_v4: Optional[Path] = None,
) -> Dict[str, Any]:
    """Lock new fixtures then settle completed ones. Safe no-op if freeze is missing."""
    if not freeze_is_ready(out_dir):
        return {"skipped": True, "reason": "freeze_not_ready"}
    device = device or torch.device("cpu")
    artifacts_v4 = artifacts_v4 or (Path(__file__).resolve().parents[2] / "artifacts")
    lock_stats = lock_upcoming(db=db, out_dir=out_dir, device=device, artifacts_v4=artifacts_v4)
    settle_stats = settle_actuals(db=db, out_dir=out_dir)
    return {"skipped": False, "lock": lock_stats, "settle": settle_stats, "status": live_status(out_dir)}
