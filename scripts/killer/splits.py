"""Immutable chronological 75/25 splits + dataset fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .config import DEV_VAL_FRACTION, TRAIN_FRACTION


@dataclass(frozen=True)
class LeagueSplit:
    league_id: int
    train_ids: Tuple[int, ...]
    sealed_ids: Tuple[int, ...]
    develop_train_ids: Tuple[int, ...]
    develop_val_ids: Tuple[int, ...]


@dataclass(frozen=True)
class SplitBundle:
    leagues: Dict[int, LeagueSplit]
    train_ids: Tuple[int, ...]
    sealed_ids: Tuple[int, ...]
    develop_train_ids: Tuple[int, ...]
    develop_val_ids: Tuple[int, ...]
    fingerprint: Dict[str, str]


def _event_id(row: pd.Series) -> int:
    if "event_id" in row and pd.notna(row["event_id"]):
        return int(row["event_id"])
    if "id" in row and pd.notna(row["id"]):
        return int(row["id"])
    # Stable surrogate if needed
    return int(hash((int(row["league_id"]), str(row["date_event"]), int(row["home_team_id"]), int(row["away_team_id"]))) % (10**12))


def sha256_ids(ids: Sequence[int]) -> str:
    payload = ",".join(str(int(x)) for x in ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_json(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def chronological_cut_indices(n: int, train_fraction: float = TRAIN_FRACTION) -> Tuple[int, int]:
    """Return (train_end, n) with train_end = floor(n * train_fraction), sealed = rest."""
    if n < 4:
        # Tiny leagues: keep at least 1 sealed if possible
        train_end = max(1, n - 1) if n >= 2 else n
        return train_end, n
    train_end = int(n * float(train_fraction))
    train_end = max(1, min(train_end, n - 1))
    return train_end, n


def develop_cut_indices(train_n: int, val_fraction: float = DEV_VAL_FRACTION) -> Tuple[int, int]:
    """Inside the 75%: develop-train / develop-val chronological cut."""
    if train_n < 5:
        return max(1, train_n - 1), train_n
    val_n = max(1, int(round(train_n * float(val_fraction))))
    train_dev = train_n - val_n
    train_dev = max(1, train_dev)
    return train_dev, train_n


def build_league_split(df_league: pd.DataFrame, league_id: int) -> LeagueSplit:
    g = df_league.sort_values(["date_event", "event_id"]).reset_index(drop=True)
    ids = [_event_id(r) for _, r in g.iterrows()]
    n = len(ids)
    train_end, _ = chronological_cut_indices(n, TRAIN_FRACTION)
    train_ids = tuple(ids[:train_end])
    sealed_ids = tuple(ids[train_end:])
    dev_end, _ = develop_cut_indices(len(train_ids), DEV_VAL_FRACTION)
    return LeagueSplit(
        league_id=int(league_id),
        train_ids=train_ids,
        sealed_ids=sealed_ids,
        develop_train_ids=tuple(train_ids[:dev_end]),
        develop_val_ids=tuple(train_ids[dev_end:]),
    )


def build_split_bundle(df: pd.DataFrame, league_ids: Sequence[int]) -> SplitBundle:
    leagues: Dict[int, LeagueSplit] = {}
    train: List[int] = []
    sealed: List[int] = []
    dtrain: List[int] = []
    dval: List[int] = []
    for lid in league_ids:
        g = df[df["league_id"] == int(lid)]
        if g.empty:
            continue
        sp = build_league_split(g, int(lid))
        leagues[int(lid)] = sp
        train.extend(sp.train_ids)
        sealed.extend(sp.sealed_ids)
        dtrain.extend(sp.develop_train_ids)
        dval.extend(sp.develop_val_ids)

    train_t = tuple(train)
    sealed_t = tuple(sealed)
    dtrain_t = tuple(dtrain)
    dval_t = tuple(dval)
    fingerprint = {
        "train_ids.sha256": sha256_ids(train_t),
        "sealed_ids.sha256": sha256_ids(sealed_t),
        "develop_train_ids.sha256": sha256_ids(dtrain_t),
        "develop_val_ids.sha256": sha256_ids(dval_t),
        "train_fraction": str(TRAIN_FRACTION),
        "dev_val_fraction": str(DEV_VAL_FRACTION),
        "n_train": str(len(train_t)),
        "n_sealed": str(len(sealed_t)),
        "n_develop_train": str(len(dtrain_t)),
        "n_develop_val": str(len(dval_t)),
        "leagues": ",".join(str(x) for x in sorted(leagues.keys())),
    }
    return SplitBundle(
        leagues=leagues,
        train_ids=train_t,
        sealed_ids=sealed_t,
        develop_train_ids=dtrain_t,
        develop_val_ids=dval_t,
        fingerprint=fingerprint,
    )


def assert_no_leakage(bundle: SplitBundle) -> None:
    train_set = set(bundle.train_ids)
    sealed_set = set(bundle.sealed_ids)
    overlap = train_set & sealed_set
    if overlap:
        raise RuntimeError(f"FATAL: train/sealed overlap ({len(overlap)} ids)")
    if set(bundle.develop_train_ids) & set(bundle.develop_val_ids):
        raise RuntimeError("FATAL: develop train/val overlap")
    if not set(bundle.develop_train_ids).issubset(train_set):
        raise RuntimeError("FATAL: develop_train not subset of train")
    if not set(bundle.develop_val_ids).issubset(train_set):
        raise RuntimeError("FATAL: develop_val not subset of train")
    if set(bundle.develop_val_ids) & sealed_set:
        raise RuntimeError("FATAL: develop_val leaked into sealed")


def save_split_bundle(bundle: SplitBundle, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    assert_no_leakage(bundle)
    payload = {
        "fingerprint": bundle.fingerprint,
        "leagues": {
            str(lid): {
                "league_id": sp.league_id,
                "train_ids": list(sp.train_ids),
                "sealed_ids": list(sp.sealed_ids),
                "develop_train_ids": list(sp.develop_train_ids),
                "develop_val_ids": list(sp.develop_val_ids),
                "n_train": len(sp.train_ids),
                "n_sealed": len(sp.sealed_ids),
            }
            for lid, sp in sorted(bundle.leagues.items())
        },
        "train_ids": list(bundle.train_ids),
        "sealed_ids": list(bundle.sealed_ids),
        "develop_train_ids": list(bundle.develop_train_ids),
        "develop_val_ids": list(bundle.develop_val_ids),
    }
    path = out_dir / "KILLER_SPLITS.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "TRAIN_IDS.sha256").write_text(bundle.fingerprint["train_ids.sha256"] + "\n", encoding="utf-8")
    (out_dir / "TEST_IDS.sha256").write_text(bundle.fingerprint["sealed_ids.sha256"] + "\n", encoding="utf-8")
    return path


def load_split_bundle(path: Path) -> SplitBundle:
    data = json.loads(path.read_text(encoding="utf-8"))
    leagues: Dict[int, LeagueSplit] = {}
    for lid_s, sp in (data.get("leagues") or {}).items():
        leagues[int(lid_s)] = LeagueSplit(
            league_id=int(sp["league_id"]),
            train_ids=tuple(int(x) for x in sp["train_ids"]),
            sealed_ids=tuple(int(x) for x in sp["sealed_ids"]),
            develop_train_ids=tuple(int(x) for x in sp["develop_train_ids"]),
            develop_val_ids=tuple(int(x) for x in sp["develop_val_ids"]),
        )
    return SplitBundle(
        leagues=leagues,
        train_ids=tuple(int(x) for x in data["train_ids"]),
        sealed_ids=tuple(int(x) for x in data["sealed_ids"]),
        develop_train_ids=tuple(int(x) for x in data["develop_train_ids"]),
        develop_val_ids=tuple(int(x) for x in data["develop_val_ids"]),
        fingerprint=dict(data.get("fingerprint") or {}),
    )


def mask_dataframe(df: pd.DataFrame, allowed_ids: Sequence[int]) -> pd.DataFrame:
    """Return chronological subset restricted to allowed event ids."""
    id_set = set(int(x) for x in allowed_ids)
    if "event_id" not in df.columns:
        raise ValueError("dataframe missing event_id")
    out = df[df["event_id"].astype(int).isin(id_set)].copy()
    return out.sort_values(["date_event", "event_id"]).reset_index(drop=True)


def split_summary(bundle: SplitBundle, league_names: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    rows = []
    for lid, sp in sorted(bundle.leagues.items()):
        name = (league_names or {}).get(lid, str(lid))
        n = len(sp.train_ids) + len(sp.sealed_ids)
        rows.append(
            {
                "league_id": lid,
                "name": name,
                "n_total": n,
                "n_train_75": len(sp.train_ids),
                "n_sealed_25": len(sp.sealed_ids),
                "n_develop_train": len(sp.develop_train_ids),
                "n_develop_val": len(sp.develop_val_ids),
                "train_pct": round(100.0 * len(sp.train_ids) / max(1, n), 1),
            }
        )
    return rows
