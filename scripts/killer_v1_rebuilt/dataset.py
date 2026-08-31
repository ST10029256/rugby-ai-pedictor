"""Chronology-safe 11/16-d sequences + current-match scalars."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import LEAGUE_HOME_ADV_PRIOR, SEQ_DIM, SEQ_LEN, UNK_LEAGUE_IDX, UNK_TEAM_IDX
from .ratings import CausalRatings


def _tid(x) -> int:
    try:
        return int(x)
    except Exception:
        return -1


def build_idx_maps(df_train: pd.DataFrame) -> Tuple[Dict[int, int], Dict[int, int]]:
    teams = sorted({_tid(x) for x in df_train["home_team_id"]} | {_tid(x) for x in df_train["away_team_id"]})
    leagues = sorted({int(x) for x in df_train["league_id"].unique()})
    return {t: i + 1 for i, t in enumerate(teams)}, {l: i + 1 for i, l in enumerate(leagues)}


def _step(ablation: str, vec11: np.ndarray, extra4: np.ndarray, opp_adj: float) -> np.ndarray:
    dim = SEQ_DIM[ablation]
    if dim == 11:
        return vec11.astype(np.float32)
    if dim == 15:
        return np.concatenate([vec11, extra4], axis=0).astype(np.float32)
    return np.concatenate([vec11, extra4, np.array([opp_adj], dtype=np.float32)], axis=0)


@dataclass
class RebuiltBatch:
    event_ids: np.ndarray
    league_ids: np.ndarray
    dates: np.ndarray
    home_team_ids: np.ndarray
    away_team_ids: np.ndarray
    home_idx: np.ndarray
    away_idx: np.ndarray
    league_idx: np.ndarray
    home_seq: np.ndarray
    away_seq: np.ndarray
    scalars: np.ndarray  # elo_diff, exp_margin, att-def, def-att, rest, home_bias, mu0_h, mu0_a
    mu0: np.ndarray
    pi_draw: np.ndarray
    y_home: np.ndarray
    y_away: np.ndarray
    y_outcome: np.ndarray  # 0 away 1 draw 2 home
    y_home_win_nd: np.ndarray  # 1 if home>away else 0; draws unused in BCE
    is_draw: np.ndarray
    meta: dict


SCALAR_NAMES = [
    "elo_diff", "expected_margin", "home_att_minus_away_def", "away_att_minus_home_def",
    "rest_diff", "league_home_bias", "mu0_home", "mu0_away",
]


def build_batch(
    df: pd.DataFrame,
    ablation: str,
    *,
    team_to_idx: Optional[Dict[int, int]] = None,
    league_to_idx: Optional[Dict[int, int]] = None,
) -> RebuiltBatch:
    g = df.copy()
    g["date_event"] = pd.to_datetime(g["date_event"], errors="coerce")
    g = g.sort_values(["date_event", "event_id"]).reset_index(drop=True)
    n = len(g)
    dim = SEQ_DIM[ablation]
    home_seq = np.zeros((n, SEQ_LEN, dim), dtype=np.float32)
    away_seq = np.zeros((n, SEQ_LEN, dim), dtype=np.float32)
    scalars = np.zeros((n, 8), dtype=np.float32)
    mu0 = np.zeros((n, 2), dtype=np.float32)
    pi_draw = np.zeros(n, dtype=np.float32)
    y_home = np.zeros(n, dtype=np.float32)
    y_away = np.zeros(n, dtype=np.float32)
    y_outcome = np.zeros(n, dtype=np.int64)
    y_nd = np.zeros(n, dtype=np.float32)
    is_draw = np.zeros(n, dtype=np.float32)
    event_ids = np.zeros(n, dtype=np.int64)
    league_ids = np.zeros(n, dtype=np.int64)
    home_ids = np.zeros(n, dtype=np.int64)
    away_ids = np.zeros(n, dtype=np.int64)
    dates: List[str] = []

    hist: Dict[int, Deque[np.ndarray]] = defaultdict(lambda: deque(maxlen=SEQ_LEN))
    last_date: Dict[int, datetime] = {}
    engine = CausalRatings()
    pf_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))
    pa_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))
    vol_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))

    def fill(dest, steps: List[np.ndarray]) -> None:
        if not steps:
            return
        dest[-len(steps) :] = np.stack(steps, 0)

    def rest_days(tid, dtp) -> float:
        if tid not in last_date:
            return 14.0
        return float(np.clip((dtp - last_date[tid]).days, 0.0, 60.0))

    for i, r in g.iterrows():
        h, a, lid = _tid(r["home_team_id"]), _tid(r["away_team_id"]), int(r["league_id"])
        scored = pd.notna(r["home_score"]) and pd.notna(r["away_score"])
        hs = float(r["home_score"]) if scored else 0.0
        aw = float(r["away_score"]) if scored else 0.0
        dt = r["date_event"]
        if pd.isna(dt):
            dt = pd.Timestamp("1970-01-01")
        dtp = dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt

        hs_snap, as_ = engine.snapshot(h), engine.snapshot(a)
        mu_h, mu_a, exp_m = engine.mu0(h, a, lid)
        prior = float(LEAGUE_HOME_ADV_PRIOR.get(lid, 0.55))
        env = engine.leagues[lid]
        sd = 8.0
        vals = []
        if env.n_home:
            vals.extend([env.home_pf / env.n_home, env.home_pa / env.n_home])
        if vals:
            sd = max(6.0, float(np.std(vals) * 4 + 6.0))

        fill(home_seq[i], list(hist[h]))
        fill(away_seq[i], list(hist[a]))

        d_h, d_a = rest_days(h, dtp), rest_days(a, dtp)
        elo_adv = 40.0 * ((prior - 0.5) / 0.1)
        scalars[i] = np.array([
            (hs_snap.elo - as_.elo + elo_adv) / 200.0,
            exp_m / 10.0,
            hs_snap.attack - as_.defence,
            as_.attack - hs_snap.defence,
            (d_h - d_a) / 14.0,
            (prior - 0.5) / 0.1,
            mu_h / 30.0,
            mu_a / 30.0,
        ], dtype=np.float32)
        mu0[i] = [mu_h, mu_a]
        pi_draw[i] = env.draw_rate()

        event_ids[i] = int(r["event_id"])
        league_ids[i] = lid
        home_ids[i] = h
        away_ids[i] = a
        dates.append(str(r["date_event"]))
        y_home[i], y_away[i] = hs, aw
        if not scored:
            y_outcome[i], y_nd[i], is_draw[i] = 0, 0.0, 0.0
        elif hs > aw:
            y_outcome[i], y_nd[i], is_draw[i] = 2, 1.0, 0.0
        elif hs < aw:
            y_outcome[i], y_nd[i], is_draw[i] = 0, 0.0, 0.0
        else:
            y_outcome[i], y_nd[i], is_draw[i] = 1, 0.0, 1.0

        # Upcoming fixtures contribute features from history but must not
        # update ratings or sequences — there is no result yet.
        if not scored:
            continue

        # After snapshot: build steps from THIS result for future games
        vol_h = float(np.std(list(vol_hist[h])[-5:])) / 15.0 if len(vol_hist[h]) >= 2 else 0.0
        vol_h10 = float(np.std(list(vol_hist[h]))) / 15.0 if len(vol_hist[h]) >= 2 else 0.0
        vol_a = float(np.std(list(vol_hist[a])[-5:])) / 15.0 if len(vol_hist[a]) >= 2 else 0.0
        vol_a10 = float(np.std(list(vol_hist[a]))) / 15.0 if len(vol_hist[a]) >= 2 else 0.0
        rest_h = min(d_h, 42.0) / 14.0
        rest_a = min(d_a, 42.0) / 14.0
        vec_h = np.array([
            (hs - 22.0) / sd, (aw - 22.0) / sd, (hs - aw) / sd,
            1.0, (prior - 0.5) / 0.1, rest_h, vol_h, vol_h10,
            (hs_snap.elo - 1500.0) / 200.0, (as_.elo - 1500.0) / 200.0, exp_m / 10.0,
        ], dtype=np.float32)
        vec_a = np.array([
            (aw - 22.0) / sd, (hs - 22.0) / sd, (aw - hs) / sd,
            0.0, -(prior - 0.5) / 0.1, rest_a, vol_a, vol_a10,
            (as_.elo - 1500.0) / 200.0, (hs_snap.elo - 1500.0) / 200.0, -exp_m / 10.0,
        ], dtype=np.float32)
        extra_h = np.array([hs_snap.attack, hs_snap.defence, as_.attack, as_.defence], dtype=np.float32)
        extra_a = np.array([as_.attack, as_.defence, hs_snap.attack, hs_snap.defence], dtype=np.float32)
        opp_adj_h = ((hs - mu_h) - (aw - mu_a)) / 20.0
        opp_adj_a = ((aw - mu_a) - (hs - mu_h)) / 20.0
        hist[h].append(_step(ablation, vec_h, extra_h, opp_adj_h))
        hist[a].append(_step(ablation, vec_a, extra_a, opp_adj_a))
        vol_hist[h].append(hs - aw)
        vol_hist[a].append(aw - hs)
        pf_hist[h].append(hs)
        pa_hist[h].append(aw)
        pf_hist[a].append(aw)
        pa_hist[a].append(hs)
        engine.update(h, a, lid, hs, aw)
        last_date[h] = dtp
        last_date[a] = dtp

    if team_to_idx is None or league_to_idx is None:
        tmap, lmap = build_idx_maps(g)
        team_to_idx = team_to_idx or tmap
        league_to_idx = league_to_idx or lmap

    home_idx = np.array([team_to_idx.get(int(t), UNK_TEAM_IDX) for t in home_ids], dtype=np.int64)
    away_idx = np.array([team_to_idx.get(int(t), UNK_TEAM_IDX) for t in away_ids], dtype=np.int64)
    league_idx = np.array([league_to_idx.get(int(l), UNK_LEAGUE_IDX) for l in league_ids], dtype=np.int64)
    n_teams = max(max(team_to_idx.values(), default=0), UNK_TEAM_IDX) + 1
    n_leagues = max(max(league_to_idx.values(), default=0), UNK_LEAGUE_IDX) + 1
    return RebuiltBatch(
        event_ids=event_ids, league_ids=league_ids, dates=np.asarray(dates),
        home_team_ids=home_ids, away_team_ids=away_ids,
        home_idx=home_idx, away_idx=away_idx, league_idx=league_idx,
        home_seq=home_seq, away_seq=away_seq, scalars=scalars, mu0=mu0, pi_draw=pi_draw,
        y_home=y_home, y_away=y_away, y_outcome=y_outcome, y_home_win_nd=y_nd, is_draw=is_draw,
        meta={
            "team_to_idx": team_to_idx, "league_to_idx": league_to_idx,
            "n_teams": n_teams, "n_leagues": n_leagues, "seq_dim": dim, "ablation": ablation,
        },
    )


def filter_batch(batch: RebuiltBatch, allowed: Sequence[int]) -> RebuiltBatch:
    idset = set(int(x) for x in allowed)
    m = np.array([int(e) in idset for e in batch.event_ids], dtype=bool)
    if not np.any(m):
        raise ValueError("empty filter")

    def t(x):
        return x[m]

    return RebuiltBatch(
        event_ids=t(batch.event_ids), league_ids=t(batch.league_ids), dates=t(batch.dates),
        home_team_ids=t(batch.home_team_ids), away_team_ids=t(batch.away_team_ids),
        home_idx=t(batch.home_idx), away_idx=t(batch.away_idx), league_idx=t(batch.league_idx),
        home_seq=t(batch.home_seq), away_seq=t(batch.away_seq), scalars=t(batch.scalars),
        mu0=t(batch.mu0), pi_draw=t(batch.pi_draw),
        y_home=t(batch.y_home), y_away=t(batch.y_away), y_outcome=t(batch.y_outcome),
        y_home_win_nd=t(batch.y_home_win_nd), is_draw=t(batch.is_draw), meta=dict(batch.meta),
    )
