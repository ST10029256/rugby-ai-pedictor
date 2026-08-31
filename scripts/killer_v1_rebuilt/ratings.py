"""Causal Elo + attack/defence with shrinkage. Snapshot before update."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple

import numpy as np

from .config import (
    ATTACK_K,
    DEFENCE_K,
    ELO_HOME_ADV,
    ELO_K,
    ELO_SCALE,
    LEAGUE_HOME_ADV_PRIOR,
    RATING_SHRINK_N0,
)


def expected_elo(elo_h: float, elo_a: float, home_adv: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-((elo_h + home_adv - elo_a) / ELO_SCALE)))


@dataclass
class TeamRating:
    elo: float = 1500.0
    attack: float = 0.0
    defence: float = 0.0
    n: int = 0


@dataclass
class LeagueEnv:
    home_pf: float = 0.0
    home_pa: float = 0.0
    n_home: int = 0
    away_pf: float = 0.0
    away_pa: float = 0.0
    n_away: int = 0
    draws: int = 0
    games: int = 0

    def home_avg(self) -> Tuple[float, float]:
        if self.n_home <= 0:
            return 24.0, 20.0
        return self.home_pf / self.n_home, self.home_pa / self.n_home

    def away_avg(self) -> Tuple[float, float]:
        if self.n_away <= 0:
            return 20.0, 24.0
        return self.away_pf / self.n_away, self.away_pa / self.n_away

    def draw_rate(self, global_pi: float = 0.02) -> float:
        n = max(self.games, 0)
        raw = (self.draws / n) if n else global_pi
        w = n / (n + 40.0)
        return float(w * raw + (1.0 - w) * global_pi)


class CausalRatings:
    def __init__(self) -> None:
        self.teams: Dict[int, TeamRating] = defaultdict(TeamRating)
        self.leagues: Dict[int, LeagueEnv] = defaultdict(LeagueEnv)

    def snapshot(self, team_id: int) -> TeamRating:
        t = self.teams[team_id]
        shrink = t.n / (t.n + RATING_SHRINK_N0)
        return TeamRating(
            elo=t.elo,
            attack=t.attack * shrink,
            defence=t.defence * shrink,
            n=t.n,
        )

    def mu0(self, home_id: int, away_id: int, league_id: int) -> Tuple[float, float, float]:
        h = self.snapshot(home_id)
        a = self.snapshot(away_id)
        env = self.leagues[league_id]
        hp, ha = env.home_avg()
        ap, aa = env.away_avg()
        prior = float(LEAGUE_HOME_ADV_PRIOR.get(league_id, 0.55))
        home_adv_pts = 3.0 * ((prior - 0.5) / 0.1)
        mu_h = hp + 4.0 * (h.attack - a.defence) + home_adv_pts
        mu_a = ap + 4.0 * (a.attack - h.defence)
        mu_h = float(np.clip(mu_h, 3.0, 80.0))
        mu_a = float(np.clip(mu_a, 3.0, 80.0))
        elo_adv = ELO_HOME_ADV * ((prior - 0.5) / 0.1)
        exp_m = (h.elo - a.elo + elo_adv) / 30.0
        return mu_h, mu_a, exp_m

    def update(self, home_id: int, away_id: int, league_id: int, hs: float, aw: float) -> None:
        mu_h, mu_a, _ = self.mu0(home_id, away_id, league_id)
        h = self.teams[home_id]
        a = self.teams[away_id]
        env = self.leagues[league_id]
        prior = float(LEAGUE_HOME_ADV_PRIOR.get(league_id, 0.55))
        elo_adv = ELO_HOME_ADV * ((prior - 0.5) / 0.1)
        p_h = expected_elo(h.elo, a.elo, elo_adv)
        if hs > aw:
            s_h, s_a = 1.0, 0.0
        elif hs < aw:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5
        mf = min(1.5, np.sqrt(abs(hs - aw) / 10.0 + 1e-6))
        h.elo += ELO_K * mf * (s_h - p_h)
        a.elo += ELO_K * mf * (s_a - (1.0 - p_h))
        h.attack += ATTACK_K * ((hs - mu_h) / 15.0)
        a.attack += ATTACK_K * ((aw - mu_a) / 15.0)
        h.defence += DEFENCE_K * ((mu_a - aw) / 15.0)
        a.defence += DEFENCE_K * ((mu_h - hs) / 15.0)
        h.attack = float(np.clip(h.attack, -3.0, 3.0))
        a.attack = float(np.clip(a.attack, -3.0, 3.0))
        h.defence = float(np.clip(h.defence, -3.0, 3.0))
        a.defence = float(np.clip(a.defence, -3.0, 3.0))
        h.n += 1
        a.n += 1
        env.home_pf += hs
        env.home_pa += aw
        env.n_home += 1
        env.away_pf += aw
        env.away_pa += hs
        env.n_away += 1
        env.games += 1
        if hs == aw:
            env.draws += 1
        self.teams[home_id] = h
        self.teams[away_id] = a
        self.leagues[league_id] = env
