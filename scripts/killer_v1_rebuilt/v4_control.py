"""AI-only production V4 predictions for the live ledger (no odds blend)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("killer_v2.v4")


def v4_asset_paths(artifacts_dir: Path, league_id: int) -> Optional[Dict[str, Any]]:
    meta = artifacts_dir / f"league_{league_id}_model_maz_maxed_v4_meta.pkl"
    seeds = [
        artifacts_dir / f"league_{league_id}_model_maz_maxed_v4_seed_42.pt",
        artifacts_dir / f"league_{league_id}_model_maz_maxed_v4_seed_1337.pt",
        artifacts_dir / f"league_{league_id}_model_maz_maxed_v4_seed_9001.pt",
    ]
    if not meta.exists() or not all(p.exists() for p in seeds):
        return None
    return {"meta_path": str(meta), "seed_model_paths": [str(p) for p in seeds]}


def v4_checkpoint_hash(assets: Dict[str, Any]) -> str:
    h = hashlib.sha256()
    for path in [assets["meta_path"], *assets["seed_model_paths"]]:
        h.update(Path(path).read_bytes())
    return h.hexdigest()


class V4Control:
    def __init__(self, db_path: Path, artifacts_dir: Path):
        self.db_path = str(db_path)
        self.artifacts_dir = artifacts_dir
        self._predictors: Dict[int, Any] = {}
        self._hashes: Dict[int, str] = {}

    def _get(self, league_id: int):
        if league_id in self._predictors:
            return self._predictors[league_id]
        assets = v4_asset_paths(self.artifacts_dir, league_id)
        if assets is None:
            self._predictors[league_id] = None
            return None
        from prediction.v4_runtime import V4RuntimePredictor

        pred = V4RuntimePredictor(
            v4_assets=assets,
            db_path=self.db_path,
            sportdevs_api_key="",
        )
        self._predictors[league_id] = pred
        self._hashes[league_id] = v4_checkpoint_hash(assets)
        return pred

    def predict(
        self,
        *,
        league_id: int,
        home_team: str,
        away_team: str,
        match_date: str,
    ) -> Optional[Tuple[Dict[str, float], str]]:
        pred = self._get(league_id)
        if pred is None:
            LOG.warning("No local V4 artifacts for league %s", league_id)
            return None
        out = pred.predict_match(
            home_team=home_team,
            away_team=away_team,
            league_id=int(league_id),
            match_date=str(match_date)[:10],
            match_id=None,
        )
        # Production V4 is binary; store an explicit zero draw mass.
        p_home = float(out["ai_home_win_prob"])
        p_draw = 0.0
        p_away = float(1.0 - p_home)
        row = {
            "p_home": p_home,
            "p_draw": p_draw,
            "p_away": p_away,
            "predicted_home_score": float(out["predicted_home_score"]),
            "predicted_away_score": float(out["predicted_away_score"]),
        }
        return row, self._hashes[league_id]
