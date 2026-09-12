"""Architecture freeze hashes for Killer V2 = A5.

Do not change model/feature/train files after freeze. Live-forward only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import (
    FROZEN,
    FROZEN_ABLATION,
    FROZEN_ALPHA,
    FROZEN_KNOBS,
    HISTORICAL_BENCHMARK,
    LIVE_ARTIFACT_DIR,
    LIVE_CHECKPOINTS,
    SEEDS,
    VERSION,
)

ROOT = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parent

FEATURE_SCHEMA_FILES = ("ratings.py", "dataset.py")
MODEL_CONFIG_FILES = ("config.py", "model.py", "train.py")


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha256_files(paths: Iterable[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def feature_schema_hash() -> str:
    return _sha256_files(PKG / name for name in FEATURE_SCHEMA_FILES)


def model_config_hash() -> str:
    knobs = json.dumps(FROZEN_KNOBS, sort_keys=True, separators=(",", ":")).encode("utf-8")
    h = hashlib.sha256()
    h.update(knobs)
    h.update(b"\n")
    for name in MODEL_CONFIG_FILES:
        h.update((PKG / name).read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def ensemble_checkpoint_hash(blobs: Iterable[bytes]) -> str:
    h = hashlib.sha256()
    for blob in blobs:
        h.update(blob)
    return h.hexdigest()


def live_seed_paths(out_dir: Path) -> List[Path]:
    return [out_dir / f"live_{FROZEN_ABLATION}_seed_{seed}.pt" for seed in SEEDS]


def hashes_from_live_dir(out_dir: Path) -> Dict[str, str]:
    blobs = [p.read_bytes() for p in live_seed_paths(out_dir)]
    return {
        "feature_schema_hash": feature_schema_hash(),
        "model_config_hash": model_config_hash(),
        "killer_checkpoint_hash": ensemble_checkpoint_hash(blobs),
        "seed_hashes": {p.name: _sha256_bytes(b) for p, b in zip(live_seed_paths(out_dir), blobs)},
    }


def freeze_manifest_path(out_dir: Path) -> Path:
    return out_dir / "FROZEN.json"


def write_freeze_manifest(out_dir: Path, extra: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": VERSION,
        "frozen": FROZEN,
        "ablation": FROZEN_ABLATION,
        "alpha": FROZEN_ALPHA,
        "seeds": list(SEEDS),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "do_not_change": [
            "architecture",
            "16-d feature schema",
            "rating equations",
            "mu0 statistical score baseline",
            "residual scoring logic",
            "GRU-48 / embedding-16 / trunk 128→64",
            "FiLM",
            "draw-prior logic",
            "bounded classifier/score blend",
            "loss weights",
            "seeds 42, 1337, 9001",
            "calibration procedure",
            "training recipe",
        ],
        "historical_benchmark": HISTORICAL_BENCHMARK,
        "live_checkpoints": list(LIVE_CHECKPOINTS),
        "rule": (
            "Do not use the 2,936 historical benchmark to improve A5. "
            "Never regenerate a locked prediction after its result is known. "
            "Compare V4 vs Killer V2 only at 100 / 250 / 500 settled live matches."
        ),
        "knobs": FROZEN_KNOBS,
        "feature_schema_hash": feature_schema_hash(),
        "model_config_hash": model_config_hash(),
        **extra,
    }
    path = freeze_manifest_path(out_dir)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def load_freeze_manifest(out_dir: Path) -> Dict[str, Any]:
    path = freeze_manifest_path(out_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Killer V2 freeze missing: {path}. Run --phase freeze first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_is_ready(out_dir: Path) -> bool:
    if not freeze_manifest_path(out_dir).exists():
        return False
    return all(p.exists() for p in live_seed_paths(out_dir))


def default_live_dir() -> Path:
    return ROOT / LIVE_ARTIFACT_DIR
