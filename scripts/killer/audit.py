"""Frozen audit ledger + dataset fingerprints for Killer exam."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def checkpoint_hash_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def write_audit_row(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def write_exam_ledger(
    path: Path,
    rows: Sequence[Dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")


def make_prediction_audit(
    *,
    match_id: int,
    league_id: int,
    kickoff: str,
    home_team_id: int,
    away_team_id: int,
    model_version: str,
    checkpoint_hash: str,
    p_away: float,
    p_draw: float,
    p_home: float,
    expected_home: float,
    expected_away: float,
    margin: float,
    uncertainty: float,
    seed_std: float,
) -> Dict[str, Any]:
    return {
        "match_id": int(match_id),
        "league_id": int(league_id),
        "kickoff": kickoff,
        "home_team_id": int(home_team_id),
        "away_team_id": int(away_team_id),
        "model_version": model_version,
        "checkpoint_hash": checkpoint_hash,
        "P_away": float(p_away),
        "P_draw": float(p_draw),
        "P_home": float(p_home),
        "expected_home": float(expected_home),
        "expected_away": float(expected_away),
        "margin": float(margin),
        "uncertainty": float(uncertainty),
        "seed_disagreement_std": float(seed_std),
        "prediction_created_at": datetime.now(timezone.utc).isoformat(),
        "outcome_home": None,
        "outcome_away": None,
        "outcome_result": None,
    }


def attach_outcomes(ledger_path: Path, outcomes: Dict[int, Dict[str, Any]], out_path: Optional[Path] = None) -> Path:
    """Fill outcomes into an existing ledger after the exam."""
    out_path = out_path or ledger_path.with_name(ledger_path.stem + "_with_outcomes.jsonl")
    rows_out: List[Dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            oc = outcomes.get(int(row["match_id"]))
            if oc:
                row["outcome_home"] = oc.get("home")
                row["outcome_away"] = oc.get("away")
                hs, aw = oc.get("home"), oc.get("away")
                if hs is not None and aw is not None:
                    if hs > aw:
                        row["outcome_result"] = "home"
                    elif hs < aw:
                        row["outcome_result"] = "away"
                    else:
                        row["outcome_result"] = "draw"
            rows_out.append(row)
    write_exam_ledger(out_path, rows_out)
    return out_path


def write_fingerprint_manifest(out_dir: Path, manifest: Dict[str, str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "FINGERPRINTS.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def report_temporal_firewall(df, bundle) -> Dict[str, Any]:
    """
    Quantify two things:
    1) Feature-time causality is enforced by chronological iteration (asserted in features.py).
    2) Weight-time overlap: per-league 75% unions can include matches AFTER another
       league's sealed kickoff. That is inherent to per-league cuts + a shared backbone.
    """
    import pandas as pd

    g = df.copy()
    g["date_event"] = pd.to_datetime(g["date_event"], errors="coerce")
    train_set = set(int(x) for x in bundle.train_ids)
    sealed_set = set(int(x) for x in bundle.sealed_ids)
    per_league: Dict[str, Any] = {}
    first_sealed_by_league: Dict[int, Any] = {}
    for lid, sp in sorted(bundle.leagues.items()):
        sealed_g = g[g["event_id"].astype(int).isin(set(sp.sealed_ids))]
        train_g = g[g["event_id"].astype(int).isin(set(sp.train_ids))]
        first_sealed = sealed_g["date_event"].min() if len(sealed_g) else None
        last_train = train_g["date_event"].max() if len(train_g) else None
        first_sealed_by_league[int(lid)] = first_sealed
        per_league[str(lid)] = {
            "last_train_date": None if pd.isna(last_train) else str(last_train),
            "first_sealed_date": None if first_sealed is None or pd.isna(first_sealed) else str(first_sealed),
            "n_train": len(sp.train_ids),
            "n_sealed": len(sp.sealed_ids),
        }

    # Train rows (any league) that occur after some other league's first sealed kickoff
    train_rows = g[g["event_id"].astype(int).isin(train_set)].copy()
    sealed_rows = g[g["event_id"].astype(int).isin(sealed_set)].copy()
    overlap_after_any_sealed = 0
    earliest_sealed = sealed_rows["date_event"].min() if len(sealed_rows) else None
    if earliest_sealed is not None and not pd.isna(earliest_sealed):
        overlap_after_any_sealed = int((train_rows["date_event"] > earliest_sealed).sum())

    # Team-level: train match after a sealed kickoff involving the same team
    sealed_team_cutoff: Dict[int, Any] = {}
    for _, r in sealed_rows.iterrows():
        t = r["date_event"]
        for col in ("home_team_id", "away_team_id"):
            tid = int(r[col])
            prev = sealed_team_cutoff.get(tid)
            if prev is None or t < prev:
                sealed_team_cutoff[tid] = t
    team_future_train = 0
    for _, r in train_rows.iterrows():
        t = r["date_event"]
        for col in ("home_team_id", "away_team_id"):
            tid = int(r[col])
            cut = sealed_team_cutoff.get(tid)
            if cut is not None and t > cut:
                team_future_train += 1
                break

    causal_ids = causal_train_ids_for_exam(df, bundle)
    return {
        "feature_histories": "causal_global_date_order_snapshot_before_update",
        "unknown_teams": "unk_embedding_index_0_train_identities_only",
        "per_league_cutoffs": per_league,
        "n_train_after_global_first_sealed": overlap_after_any_sealed,
        "n_train_after_same_team_sealed_kickoff": team_future_train,
        "n_causal_train": len(causal_ids),
        "causal_train_ids.sha256": hashlib.sha256(
            ",".join(str(x) for x in causal_ids).encode("utf-8")
        ).hexdigest(),
        "note": (
            "Feature histories at kickoff T exclude every match with date > T, globally. "
            "Final Killer weights are fit only on train rows that do not occur after a "
            "sealed kickoff involving the same team (cross-league identity leak closed). "
            "Unknown teams use UNK embedding 0; no future-only team IDs are allocated."
        ),
    }


def causal_train_ids_for_exam(df, bundle) -> tuple:
    """Train IDs from the 75% that do not occur after a same-team sealed kickoff."""
    import pandas as pd

    g = df.copy()
    g["date_event"] = pd.to_datetime(g["date_event"], errors="coerce")
    train_set = set(int(x) for x in bundle.train_ids)
    sealed_set = set(int(x) for x in bundle.sealed_ids)
    sealed_rows = g[g["event_id"].astype(int).isin(sealed_set)]
    sealed_team_cutoff = {}
    for _, r in sealed_rows.iterrows():
        t = r["date_event"]
        for col in ("home_team_id", "away_team_id"):
            tid = int(r[col])
            prev = sealed_team_cutoff.get(tid)
            if prev is None or t < prev:
                sealed_team_cutoff[tid] = t
    keep = []
    train_rows = g[g["event_id"].astype(int).isin(train_set)].sort_values(["date_event", "event_id"])
    for _, r in train_rows.iterrows():
        t = r["date_event"]
        leak = False
        for col in ("home_team_id", "away_team_id"):
            cut = sealed_team_cutoff.get(int(r[col]))
            if cut is not None and t > cut:
                leak = True
                break
        if not leak:
            keep.append(int(r["event_id"]))
    return tuple(keep)
