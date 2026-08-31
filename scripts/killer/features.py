"""Chronology-safe Killer feature engine (score-only, opponent-adjusted)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import (
    ATTACK_K,
    DEFENCE_K,
    ELO_HOME_ADV,
    ELO_K,
    FAST_WINDOW,
    LEAGUE_HOME_ADV_PRIOR,
    LONG_WINDOW,
    MEDIUM_WINDOW,
    RATING_SCALE,
    SEQ_DIM,
    UNK_LEAGUE_IDX,
    UNK_TEAM_IDX,
)


def _team_key(team_id: Any) -> int:
    try:
        return int(team_id)
    except Exception:
        return -1


def assert_globally_chronological(df: pd.DataFrame) -> None:
    """Fail if rows are not strictly non-decreasing in (date, event_id)."""
    if df.empty:
        return
    dates = pd.to_datetime(df["date_event"], errors="coerce")
    eids = df["event_id"].astype(int).values
    prev_d, prev_e = dates.iloc[0], int(eids[0])
    for i in range(1, len(df)):
        d, e = dates.iloc[i], int(eids[i])
        if pd.isna(d) or pd.isna(prev_d):
            continue
        if d < prev_d or (d == prev_d and e < prev_e):
            raise RuntimeError(
                f"TEMPORAL FIREWALL: dataframe is not chronological at row {i} "
                f"(event {e} date {d} precedes event {prev_e} date {prev_d})"
            )
        prev_d, prev_e = d, e


def build_idx_maps_from_train(
    df_train: pd.DataFrame,
) -> Tuple[Dict[int, int], Dict[int, int]]:
    """
    Reserve index 0 as UNK. Only teams/leagues observed in the allowed train
    window get unique embeddings. Future-only IDs must map to UNK.
    """
    teams = sorted({_team_key(x) for x in df_train["home_team_id"]} | {_team_key(x) for x in df_train["away_team_id"]})
    leagues = sorted({int(x) for x in df_train["league_id"].unique()})
    team_to_idx = {tid: i + 1 for i, tid in enumerate(teams)}  # 0 = UNK
    league_to_idx = {lid: i + 1 for i, lid in enumerate(leagues)}
    return team_to_idx, league_to_idx


def _rolling_mean(vals: Deque[float], n: int) -> float:
    if not vals:
        return 0.0
    arr = list(vals)[-n:]
    return float(np.mean(arr)) if arr else 0.0


def _rolling_std(vals: Deque[float], n: int) -> float:
    if len(vals) < 2:
        return 0.0
    arr = list(vals)[-n:]
    if len(arr) < 2:
        return 0.0
    return float(np.std(arr))


@dataclass
class TeamRatings:
    overall: float = 1500.0
    attack: float = 0.0
    defence: float = 0.0
    home: float = 0.0
    away: float = 0.0


def expected_score(elo_a: float, elo_b: float, home_adv: float = 0.0) -> float:
    return 1.0 / (1.0 + 10.0 ** (-((elo_a + home_adv - elo_b) / RATING_SCALE)))


def _step_features(
    *,
    pf_adj: float,
    pa_adj: float,
    margin_adj: float,
    is_home: float,
    rest_norm: float,
    opp_overall_z: float,
    opp_attack_z: float,
    opp_defence_z: float,
    team_attack_z: float,
    team_defence_z: float,
    form5: float,
    vol5: float,
    days_ago_norm: float,
) -> np.ndarray:
    # SEQ_DIM == 14
    return np.asarray(
        [
            pf_adj,
            pa_adj,
            margin_adj,
            is_home,
            rest_norm,
            opp_overall_z,
            opp_attack_z,
            opp_defence_z,
            team_attack_z,
            team_defence_z,
            form5,
            vol5,
            days_ago_norm,
            abs(margin_adj),
        ],
        dtype=np.float32,
    )


@dataclass
class KillerBatch:
    event_ids: np.ndarray
    league_ids: np.ndarray
    dates: np.ndarray
    home_team_ids: np.ndarray
    away_team_ids: np.ndarray
    home_idx: np.ndarray
    away_idx: np.ndarray
    league_idx: np.ndarray
    # Multi-timescale sequences [N, T, D]
    home_fast: np.ndarray
    away_fast: np.ndarray
    home_med: np.ndarray
    away_med: np.ndarray
    home_long: np.ndarray
    away_long: np.ndarray
    # Engineered rating vector for Expert C [N, R]
    rating_feats: np.ndarray
    # Score-dynamics engineered vector for Expert D [N, S]
    score_feats: np.ndarray
    # Rest vector [N, 4]
    rest_feats: np.ndarray
    # Labels
    y_home: np.ndarray
    y_away: np.ndarray
    y_margin: np.ndarray
    y_total: np.ndarray
    y_outcome: np.ndarray  # 0=away, 1=draw, 2=home
    y_home_win: np.ndarray  # 1 if home > away else 0 (compat)
    meta: Dict[str, Any]


RATING_FEAT_NAMES = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "attack_home",
    "attack_away",
    "defence_home",
    "defence_away",
    "home_rating_home",
    "away_rating_away",
    "elo_trend_home",
    "elo_trend_away",
    "sos_home",
    "sos_away",
    "h2h_margin",
    "h2h_n",
    "form5_home",
    "form5_away",
    "vol10_home",
    "vol10_away",
    "expected_margin",
]

SCORE_FEAT_NAMES = [
    "pf10_home",
    "pa10_home",
    "pf10_away",
    "pa10_away",
    "margin10_home",
    "margin10_away",
    "total10_home",
    "total10_away",
    "pf_trend_home",
    "pa_trend_home",
    "pf_trend_away",
    "pa_trend_away",
    "opp_adj_pf_home",
    "opp_adj_pa_home",
    "opp_adj_pf_away",
    "opp_adj_pa_away",
]


def build_killer_features(
    df: pd.DataFrame,
    *,
    team_to_idx: Optional[Dict[int, int]] = None,
    league_to_idx: Optional[Dict[int, int]] = None,
    league_score_mu_sd: Optional[Dict[int, Tuple[float, float]]] = None,
) -> KillerBatch:
    """
    Build features for every row using ONLY prior matches (chronology-safe).
    Pass the full chronological dataframe for the scope you allow
    (e.g. all leagues' train 75%, or develop-train only). Never include sealed rows
    when fitting stats that will be used before the exam.
    """
    g = df.copy()
    if "event_id" not in g.columns:
        g["event_id"] = np.arange(len(g))
    g = g.sort_values(["date_event", "event_id"]).reset_index(drop=True)
    assert_globally_chronological(g)
    n = len(g)
    if n == 0:
        raise ValueError("empty dataframe for Killer features")

    home_fast = np.zeros((n, FAST_WINDOW, SEQ_DIM), dtype=np.float32)
    away_fast = np.zeros((n, FAST_WINDOW, SEQ_DIM), dtype=np.float32)
    home_med = np.zeros((n, MEDIUM_WINDOW, SEQ_DIM), dtype=np.float32)
    away_med = np.zeros((n, MEDIUM_WINDOW, SEQ_DIM), dtype=np.float32)
    home_long = np.zeros((n, LONG_WINDOW, SEQ_DIM), dtype=np.float32)
    away_long = np.zeros((n, LONG_WINDOW, SEQ_DIM), dtype=np.float32)

    rating_feats = np.zeros((n, len(RATING_FEAT_NAMES)), dtype=np.float32)
    score_feats = np.zeros((n, len(SCORE_FEAT_NAMES)), dtype=np.float32)
    rest_feats = np.zeros((n, 4), dtype=np.float32)

    y_home = np.zeros(n, dtype=np.float32)
    y_away = np.zeros(n, dtype=np.float32)
    y_margin = np.zeros(n, dtype=np.float32)
    y_total = np.zeros(n, dtype=np.float32)
    y_outcome = np.zeros(n, dtype=np.int64)
    y_home_win = np.zeros(n, dtype=np.float32)

    event_ids = np.zeros(n, dtype=np.int64)
    league_ids = np.zeros(n, dtype=np.int64)
    home_team_ids = np.zeros(n, dtype=np.int64)
    away_team_ids = np.zeros(n, dtype=np.int64)
    dates: List[str] = []

    histories: Dict[int, Deque[np.ndarray]] = defaultdict(lambda: deque(maxlen=LONG_WINDOW))
    ratings: Dict[int, TeamRatings] = defaultdict(TeamRatings)
    elo_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))
    pf_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
    pa_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
    margin_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
    total_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
    opp_strength_hist: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
    last_date: Dict[int, datetime] = {}
    h2h_margin: Dict[Tuple[int, int], Deque[float]] = defaultdict(lambda: deque(maxlen=8))
    all_teams: set[int] = set()
    all_leagues: set[int] = set()

    # League scoring baselines for opponent-adjustment (expanding, chronology-safe).
    league_pf_sum: Dict[int, float] = defaultdict(float)
    league_pa_sum: Dict[int, float] = defaultdict(float)
    league_n: Dict[int, int] = defaultdict(int)

    def league_avgs(lid: int) -> Tuple[float, float]:
        nn = league_n[lid]
        if nn <= 0:
            if league_score_mu_sd and lid in league_score_mu_sd:
                mu, _ = league_score_mu_sd[lid]
                return float(mu), float(mu)
            return 22.0, 22.0
        return league_pf_sum[lid] / nn, league_pa_sum[lid] / nn

    def fill_seq(dest: np.ndarray, hist: List[np.ndarray]) -> None:
        if not hist:
            return
        stacked = np.stack(hist, axis=0)
        dest[-len(hist) :, :] = stacked

    for i, r in g.iterrows():
        h = _team_key(r["home_team_id"])
        a = _team_key(r["away_team_id"])
        lid = int(r["league_id"])
        hs = float(r["home_score"])
        aw = float(r["away_score"])
        dt = pd.to_datetime(r["date_event"], errors="coerce")
        if pd.isna(dt):
            dt = pd.Timestamp("1970-01-01")
        dtp = dt.to_pydatetime()
        for tid in (h, a):
            prev = last_date.get(tid)
            if prev is not None and prev > dtp:
                raise RuntimeError(
                    f"TEMPORAL FIREWALL: team {tid} history date {prev} is after kickoff {dtp} "
                    f"(event {int(r['event_id'])})"
                )

        all_teams.add(h)
        all_teams.add(a)
        all_leagues.add(lid)

        rh = ratings[h]
        ra = ratings[a]
        home_prior = float(LEAGUE_HOME_ADV_PRIOR.get(lid, 0.55))
        home_adv_elo = ELO_HOME_ADV * ((home_prior - 0.5) / 0.1)

        # --- snapshot histories BEFORE this match ---
        h_list = list(histories[h])
        a_list = list(histories[a])
        fill_seq(home_fast[i], h_list[-FAST_WINDOW:])
        fill_seq(away_fast[i], a_list[-FAST_WINDOW:])
        fill_seq(home_med[i], h_list[-MEDIUM_WINDOW:])
        fill_seq(away_med[i], a_list[-MEDIUM_WINDOW:])
        fill_seq(home_long[i], h_list[-LONG_WINDOW:])
        fill_seq(away_long[i], a_list[-LONG_WINDOW:])

        # Rest
        d_h = float((dtp - last_date[h]).days) if h in last_date else 14.0
        d_a = float((dtp - last_date[a]).days) if a in last_date else 14.0
        d_h = float(np.clip(d_h, 0.0, 60.0))
        d_a = float(np.clip(d_a, 0.0, 60.0))
        rest_diff = d_h - d_a
        short_turn = 1.0 if min(d_h, d_a) <= 5.0 else 0.0
        long_layoff = 1.0 if max(d_h, d_a) >= 21.0 else 0.0
        rest_feats[i] = np.array([d_h / 14.0, d_a / 14.0, rest_diff / 14.0, short_turn + long_layoff], dtype=np.float32)

        elo_diff = rh.overall - ra.overall + home_adv_elo
        exp_margin = elo_diff / 30.0
        pair = (min(h, a), max(h, a))
        h2h = list(h2h_margin[pair])
        h2h_m = float(np.mean(h2h)) if h2h else 0.0
        # Sign h2h from home perspective
        if h > a and h2h:
            h2h_m = -h2h_m

        rating_feats[i] = np.array(
            [
                (rh.overall - 1500.0) / 200.0,
                (ra.overall - 1500.0) / 200.0,
                elo_diff / 200.0,
                rh.attack,
                ra.attack,
                rh.defence,
                ra.defence,
                rh.home,
                ra.away,
                (_rolling_mean(elo_hist[h], 5) - rh.overall) / 50.0 if elo_hist[h] else 0.0,
                (_rolling_mean(elo_hist[a], 5) - ra.overall) / 50.0 if elo_hist[a] else 0.0,
                _rolling_mean(opp_strength_hist[h], 10) / 200.0,
                _rolling_mean(opp_strength_hist[a], 10) / 200.0,
                h2h_m / 20.0,
                float(len(h2h)) / 8.0,
                _rolling_mean(margin_hist[h], 5) / 20.0,
                _rolling_mean(margin_hist[a], 5) / 20.0,
                _rolling_std(margin_hist[h], 10) / 15.0,
                _rolling_std(margin_hist[a], 10) / 15.0,
                exp_margin / 10.0,
            ],
            dtype=np.float32,
        )

        pf_h = _rolling_mean(pf_hist[h], 10)
        pa_h = _rolling_mean(pa_hist[h], 10)
        pf_a = _rolling_mean(pf_hist[a], 10)
        pa_a = _rolling_mean(pa_hist[a], 10)
        score_feats[i] = np.array(
            [
                pf_h / 30.0,
                pa_h / 30.0,
                pf_a / 30.0,
                pa_a / 30.0,
                _rolling_mean(margin_hist[h], 10) / 20.0,
                _rolling_mean(margin_hist[a], 10) / 20.0,
                _rolling_mean(total_hist[h], 10) / 50.0,
                _rolling_mean(total_hist[a], 10) / 50.0,
                (_rolling_mean(pf_hist[h], 5) - _rolling_mean(pf_hist[h], 15)) / 15.0,
                (_rolling_mean(pa_hist[h], 5) - _rolling_mean(pa_hist[h], 15)) / 15.0,
                (_rolling_mean(pf_hist[a], 5) - _rolling_mean(pf_hist[a], 15)) / 15.0,
                (_rolling_mean(pa_hist[a], 5) - _rolling_mean(pa_hist[a], 15)) / 15.0,
                (pf_h - league_avgs(lid)[0]) / 15.0,
                (pa_h - league_avgs(lid)[1]) / 15.0,
                (pf_a - league_avgs(lid)[0]) / 15.0,
                (pa_a - league_avgs(lid)[1]) / 15.0,
            ],
            dtype=np.float32,
        )

        event_ids[i] = int(r["event_id"])
        league_ids[i] = lid
        home_team_ids[i] = h
        away_team_ids[i] = a
        dates.append(str(r["date_event"]))

        y_home[i] = hs
        y_away[i] = aw
        y_margin[i] = hs - aw
        y_total[i] = hs + aw
        if hs > aw:
            y_outcome[i] = 2
            y_home_win[i] = 1.0
        elif hs < aw:
            y_outcome[i] = 0
            y_home_win[i] = 0.0
        else:
            y_outcome[i] = 1
            y_home_win[i] = 0.0

        # --- update state AFTER snapshot ---
        avg_pf, avg_pa = league_avgs(lid)
        # Opponent-adjusted points: vs what this opponent usually allows/scores
        # Home PF adjusted by away defence tendency (pa of away ~ points they concede)
        away_concede = _rolling_mean(pa_hist[a], 10) if pa_hist[a] else avg_pa
        home_concede = _rolling_mean(pa_hist[h], 10) if pa_hist[h] else avg_pa
        away_score_rate = _rolling_mean(pf_hist[a], 10) if pf_hist[a] else avg_pf
        home_score_rate = _rolling_mean(pf_hist[h], 10) if pf_hist[h] else avg_pf

        pf_h_adj = (hs - away_concede) / 15.0
        pa_h_adj = (aw - away_score_rate) / 15.0
        pf_a_adj = (aw - home_concede) / 15.0
        pa_a_adj = (hs - home_score_rate) / 15.0

        rest_h = d_h / 14.0
        rest_a = d_a / 14.0
        step_h = _step_features(
            pf_adj=pf_h_adj,
            pa_adj=pa_h_adj,
            margin_adj=(hs - aw - (away_concede - away_score_rate)) / 20.0,
            is_home=1.0,
            rest_norm=rest_h,
            opp_overall_z=(ra.overall - 1500.0) / 200.0,
            opp_attack_z=ra.attack,
            opp_defence_z=ra.defence,
            team_attack_z=rh.attack,
            team_defence_z=rh.defence,
            form5=_rolling_mean(margin_hist[h], 5) / 20.0,
            vol5=_rolling_std(margin_hist[h], 5) / 15.0,
            days_ago_norm=0.0,
        )
        step_a = _step_features(
            pf_adj=pf_a_adj,
            pa_adj=pa_a_adj,
            margin_adj=(aw - hs - (home_concede - home_score_rate)) / 20.0,
            is_home=0.0,
            rest_norm=rest_a,
            opp_overall_z=(rh.overall - 1500.0) / 200.0,
            opp_attack_z=rh.attack,
            opp_defence_z=rh.defence,
            team_attack_z=ra.attack,
            team_defence_z=ra.defence,
            form5=_rolling_mean(margin_hist[a], 5) / 20.0,
            vol5=_rolling_std(margin_hist[a], 5) / 15.0,
            days_ago_norm=0.0,
        )
        histories[h].append(step_h)
        histories[a].append(step_a)

        # Elo / attack / defence updates
        exp_h = expected_score(rh.overall, ra.overall, home_adv=home_adv_elo)
        if hs > aw:
            score_h, score_a = 1.0, 0.0
        elif hs < aw:
            score_h, score_a = 0.0, 1.0
        else:
            score_h, score_a = 0.5, 0.5
        # Margin-adjusted K
        margin_factor = min(1.5, np.sqrt(abs(hs - aw) / 10.0 + 1e-6))
        k = ELO_K * margin_factor
        rh.overall += k * (score_h - exp_h)
        ra.overall += k * (score_a - (1.0 - exp_h))
        # Attack/defence residual vs league average
        rh.attack += ATTACK_K * ((hs - avg_pf) / 15.0)
        ra.attack += ATTACK_K * ((aw - avg_pf) / 15.0)
        rh.defence += DEFENCE_K * ((avg_pa - aw) / 15.0)
        ra.defence += DEFENCE_K * ((avg_pa - hs) / 15.0)
        rh.home += 0.05 * ((hs - aw) / 20.0)
        ra.away += 0.05 * ((aw - hs) / 20.0)
        # Soft clip latent ratings
        rh.attack = float(np.clip(rh.attack, -3.0, 3.0))
        ra.attack = float(np.clip(ra.attack, -3.0, 3.0))
        rh.defence = float(np.clip(rh.defence, -3.0, 3.0))
        ra.defence = float(np.clip(ra.defence, -3.0, 3.0))
        rh.home = float(np.clip(rh.home, -2.0, 2.0))
        ra.away = float(np.clip(ra.away, -2.0, 2.0))
        ratings[h] = rh
        ratings[a] = ra

        elo_hist[h].append(rh.overall)
        elo_hist[a].append(ra.overall)
        pf_hist[h].append(hs)
        pa_hist[h].append(aw)
        pf_hist[a].append(aw)
        pa_hist[a].append(hs)
        margin_hist[h].append(hs - aw)
        margin_hist[a].append(aw - hs)
        total_hist[h].append(hs + aw)
        total_hist[a].append(hs + aw)
        opp_strength_hist[h].append(ra.overall)
        opp_strength_hist[a].append(rh.overall)
        h2h_margin[pair].append(hs - aw if h < a else aw - hs)

        league_pf_sum[lid] += hs + aw
        league_pa_sum[lid] += hs + aw
        league_n[lid] += 2
        last_date[h] = dtp
        last_date[a] = dtp

    if team_to_idx is None or league_to_idx is None:
        auto_t, auto_l = build_idx_maps_from_train(g)
        if team_to_idx is None:
            team_to_idx = auto_t
        if league_to_idx is None:
            league_to_idx = auto_l

    home_idx = np.array([int(team_to_idx.get(int(t), UNK_TEAM_IDX)) for t in home_team_ids], dtype=np.int64)
    away_idx = np.array([int(team_to_idx.get(int(t), UNK_TEAM_IDX)) for t in away_team_ids], dtype=np.int64)
    league_idx = np.array([int(league_to_idx.get(int(l), UNK_LEAGUE_IDX)) for l in league_ids], dtype=np.int64)
    n_team_rows = max(max(team_to_idx.values(), default=0), UNK_TEAM_IDX) + 1
    n_league_rows = max(max(league_to_idx.values(), default=0), UNK_LEAGUE_IDX) + 1

    return KillerBatch(
        event_ids=event_ids,
        league_ids=league_ids,
        dates=np.asarray(dates),
        home_team_ids=home_team_ids,
        away_team_ids=away_team_ids,
        home_idx=home_idx,
        away_idx=away_idx,
        league_idx=league_idx,
        home_fast=home_fast,
        away_fast=away_fast,
        home_med=home_med,
        away_med=away_med,
        home_long=home_long,
        away_long=away_long,
        rating_feats=rating_feats,
        score_feats=score_feats,
        rest_feats=rest_feats,
        y_home=y_home,
        y_away=y_away,
        y_margin=y_margin,
        y_total=y_total,
        y_outcome=y_outcome,
        y_home_win=y_home_win,
        meta={
            "team_to_idx": team_to_idx,
            "league_to_idx": league_to_idx,
            "seq_dim": SEQ_DIM,
            "rating_feat_names": list(RATING_FEAT_NAMES),
            "score_feat_names": list(SCORE_FEAT_NAMES),
            "n_teams": int(n_team_rows),
            "n_leagues": int(n_league_rows),
            "unk_team_idx": UNK_TEAM_IDX,
            "unk_league_idx": UNK_LEAGUE_IDX,
        },
    )


def filter_batch(batch: KillerBatch, allowed_ids: Sequence[int]) -> KillerBatch:
    id_set = set(int(x) for x in allowed_ids)
    mask = np.array([int(e) in id_set for e in batch.event_ids], dtype=bool)
    if not np.any(mask):
        raise ValueError("filter_batch produced empty set")

    def take(x: np.ndarray) -> np.ndarray:
        return x[mask]

    return KillerBatch(
        event_ids=take(batch.event_ids),
        league_ids=take(batch.league_ids),
        dates=take(batch.dates),
        home_team_ids=take(batch.home_team_ids),
        away_team_ids=take(batch.away_team_ids),
        home_idx=take(batch.home_idx),
        away_idx=take(batch.away_idx),
        league_idx=take(batch.league_idx),
        home_fast=take(batch.home_fast),
        away_fast=take(batch.away_fast),
        home_med=take(batch.home_med),
        away_med=take(batch.away_med),
        home_long=take(batch.home_long),
        away_long=take(batch.away_long),
        rating_feats=take(batch.rating_feats),
        score_feats=take(batch.score_feats),
        rest_feats=take(batch.rest_feats),
        y_home=take(batch.y_home),
        y_away=take(batch.y_away),
        y_margin=take(batch.y_margin),
        y_total=take(batch.y_total),
        y_outcome=take(batch.y_outcome),
        y_home_win=take(batch.y_home_win),
        meta=dict(batch.meta),
    )
