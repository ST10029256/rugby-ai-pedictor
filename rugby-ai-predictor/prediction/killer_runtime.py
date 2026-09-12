"""Killer V2 (A5) runtime for live match predictions.

Loads frozen ensemble weights and runs AI-only inference. Does not blend odds.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from prediction.team_identity import resolve_team_id

logger = logging.getLogger(__name__)


def _ensure_killer_imports() -> None:
    roots = [
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[2] / "scripts",
    ]
    for root in roots:
        if (root / "killer_v1_rebuilt").is_dir() and str(root) not in sys.path:
            sys.path.insert(0, str(root))


def _torch_load(source, map_location):
    import torch

    try:
        return torch.load(source, map_location=map_location, weights_only=False)
    except TypeError:
        return torch.load(source, map_location=map_location)


def _winner_from_scores(home: float, away: float) -> str:
    rh, ra = round(float(home)), round(float(away))
    if rh > ra:
        return "Home"
    if ra > rh:
        return "Away"
    return "Draw"


class KillerRuntimePredictor:
    """Global Killer V2 ensemble. One instance serves every league."""

    def __init__(self, killer_assets: Dict[str, Any], db_path: str):
        _ensure_killer_imports()
        import torch
        from killer_v1_rebuilt.config import FROZEN_ABLATION, FROZEN_ALPHA, SEQ_DIM
        from killer_v1_rebuilt.freeze import load_freeze_manifest
        from killer_v1_rebuilt.model import RebuiltModel
        from killer_v1_rebuilt.train import flags_for

        artifacts_dir = Path(str(killer_assets["artifacts_dir"]))
        manifest = load_freeze_manifest(artifacts_dir)
        device = torch.device("cpu")
        n_teams = int(manifest["n_teams"])
        n_leagues = int(manifest["n_leagues"])
        seq_dim = int(SEQ_DIM[FROZEN_ABLATION])
        flags = flags_for(FROZEN_ABLATION)
        seed_paths: List[str] = list(killer_assets.get("seed_model_paths") or [])
        if not seed_paths:
            from killer_v1_rebuilt.freeze import live_seed_paths

            seed_paths = [str(p) for p in live_seed_paths(artifacts_dir)]

        models = []
        for path in seed_paths:
            ckpt = _torch_load(path, map_location=device)
            model = RebuiltModel(n_teams, n_leagues, seq_dim, **flags).to(device)
            model.load_state_dict(ckpt["model"])
            model.eval()
            models.append(model)
        if not models:
            raise RuntimeError("Killer V2 freeze has no seed checkpoints")

        self.db_path = db_path
        self.artifacts_dir = artifacts_dir
        self.models = models
        self.device = device
        self.alpha = float(manifest.get("alpha", FROZEN_ALPHA))
        self.ablation = FROZEN_ABLATION
        self.use_draw = bool(flags["use_draw"])
        self.team_to_idx = {int(k): int(v) for k, v in (manifest.get("team_to_idx") or {}).items()}
        self.league_to_idx = {int(k): int(v) for k, v in (manifest.get("league_to_idx") or {}).items()}
        self.n_teams = n_teams
        self.n_leagues = n_leagues
        self._history_df: Optional[pd.DataFrame] = None
        logger.info(
            "Loaded Killer V2 runtime (%s seeds, n_teams=%s n_leagues=%s)",
            len(models),
            n_teams,
            n_leagues,
        )

    def _history(self) -> pd.DataFrame:
        if self._history_df is not None:
            return self._history_df
        self._history_df = self._load_scored_history_fallback()
        return self._history_df

    def _load_scored_history_fallback(self) -> pd.DataFrame:
        from killer_v1_rebuilt.config import DEFAULT_LEAGUE_IDS
        from prediction.features import FeatureConfig, build_feature_table

        conn = sqlite3.connect(self.db_path)
        try:
            df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False))
        finally:
            conn.close()
        df = df[df["league_id"].isin(DEFAULT_LEAGUE_IDS)].copy()
        df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
        df.sort_values(["date_event", "event_id"], inplace=True)
        return df.reset_index(drop=True)

    def _resolve_team_id(self, conn: sqlite3.Connection, name: str, league_id: int) -> int:
        team_id = resolve_team_id(conn, name, int(league_id), create=False)
        if team_id is None:
            raise ValueError(f"Unknown team for Killer V2: {name} (league {league_id})")
        return int(team_id)

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        league_id: int,
        match_date: str,
        match_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        _ensure_killer_imports()
        from killer_v1_rebuilt.dataset import build_batch, filter_batch
        from killer_v1_rebuilt.train import ensemble_predict

        conn = sqlite3.connect(self.db_path)
        try:
            home_team_id = self._resolve_team_id(conn, home_team, int(league_id))
            away_team_id = self._resolve_team_id(conn, away_team, int(league_id))
        finally:
            conn.close()

        event_id = int(match_id) if match_id is not None else None
        if event_id is None:
            event_id = 900_000_000 + (abs(hash((home_team_id, away_team_id, str(match_date)[:10]))) % 90_000_000)

        upcoming = pd.DataFrame(
            [
                {
                    "event_id": event_id,
                    "league_id": int(league_id),
                    "date_event": str(match_date)[:10],
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "home_score": np.nan,
                    "away_score": np.nan,
                }
            ]
        )
        history = self._history()
        keep = ["event_id", "league_id", "date_event", "home_team_id", "away_team_id", "home_score", "away_score"]
        hist_keep = [c for c in keep if c in history.columns]
        combined = pd.concat([history[hist_keep], upcoming[keep]], ignore_index=True)
        combined.sort_values(["date_event", "event_id"], inplace=True)
        full = build_batch(
            combined,
            self.ablation,
            team_to_idx=self.team_to_idx,
            league_to_idx=self.league_to_idx,
        )
        batch = filter_batch(full, [event_id])
        pred = ensemble_predict(self.models, batch, self.device, self.alpha, self.use_draw)
        p = pred["p_hda"][0]
        mu = pred["mu"][0]
        p_away = float(p[0])
        p_draw = float(p[1])
        p_home = float(p[2])
        predicted_home = float(max(0.0, mu[0]))
        predicted_away = float(max(0.0, mu[1]))
        predicted_winner = _winner_from_scores(predicted_home, predicted_away)
        confidence = float(max(p_home, p_away, p_draw))
        return {
            "predicted_winner": predicted_winner,
            "predicted_home_score": predicted_home,
            "predicted_away_score": predicted_away,
            "confidence": confidence,
            "home_win_prob": p_home,
            "away_win_prob": p_away,
            "draw_prob": p_draw,
            "prediction_type": "Killer V2 AI",
            "ai_home_win_prob": p_home,
            "hybrid_home_win_prob": p_home,
            "bookmaker_home_win_prob": None,
            "bookmaker_count": 0,
            "model_available": True,
            "show_scores": True,
            "model_type": "killer_v2",
            "model_family": "killer",
        }
