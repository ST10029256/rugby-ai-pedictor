from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple, cast

import pandas as pd


@dataclass
class FeatureConfig:
    elo_k: float = 20.0
    form_window: int = 5
    goaldiff_window: int = 5
    h2h_window: int = 5
    # Base Elo for teams with no history
    elo_base: float = 1500.0
    # Optional Elo priors: map of (league_id, team_id) -> starting Elo
    elo_priors: Dict[Tuple[int, int], float] | None = None
    # If True, compute features under neutral conditions (no home advantage)
    neutral_mode: bool = False
    # Elo home advantage offset added to home Elo before expected score
    home_advantage_elo: float = 60.0
    # Optional per-league overrides for base Elo K
    k_by_league: Dict[int, float] | None = None
    # Season-phase based K adjustments (0..1, where 0 ~ season start)
    k_season_phase_early: float = 0.30
    k_season_phase_late: float = 0.70
    # Multipliers applied to base K in early/late phases
    k_early_mult: float = 1.15
    k_late_mult: float = 0.85


def load_events_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
    SELECT e.id AS event_id,
           e.league_id,
           e.season,
           e.date_event,
           e.timestamp,
           e.home_team_id,
           e.away_team_id,
           e.home_score,
           e.away_score
    FROM event e
    WHERE e.home_team_id IS NOT NULL AND e.away_team_id IS NOT NULL AND e.date_event IS NOT NULL
    ORDER BY e.date_event ASC, e.timestamp ASC, e.id ASC;
    """
    df = pd.read_sql_query(query, conn, parse_dates=["date_event"])  # type: ignore[arg-type]
    # Normalize target - only compute for rows with both scores
    df["home_win"] = None
    mask = df["home_score"].notna() & df["away_score"].notna()
    df.loc[mask, "home_win"] = (df.loc[mask, "home_score"] > df.loc[mask, "away_score"]).astype("Int64")
    df["draw"] = (df["home_score"].notna() & (df["home_score"] == df["away_score"]))
    # Season phase [0,1] mapped from calendar month, approximate for both hemispheres
    # Shift so typical start (Aug) ~ 0.0; phase increases through year
    df["season_phase"] = ((df["date_event"].dt.month - 8) % 12) / 11.0
    return df


def _expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def add_elo_features(df: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    # Compute pre-match Elo for each team within each league independently
    elo_home_list: List[float] = []
    elo_away_list: List[float] = []

    # State: per-league dictionaries of team -> elo
    league_to_team_elo: Dict[int, Dict[int, float]] = {}
    base_elo = config.elo_base

    # Columns order: 0 event_id, 1 league_id, 2 season, 3 date_event, 4 timestamp, 5 home_team_id, 6 away_team_id, 7 home_score, 8 away_score
    for row in df.itertuples(index=False, name=None):
        league_val = row[1]
        home_val = row[5]
        away_val = row[6]
        home_score_val = row[7]
        away_score_val = row[8]

        league_id = int(league_val) if pd.notna(league_val) else -1
        home_id = int(home_val) if pd.notna(home_val) else -1
        away_id = int(away_val) if pd.notna(away_val) else -1

        team_elo = league_to_team_elo.setdefault(league_id, {})
        # Use configured priors if provided for this league/team; otherwise fall back to base
        if config.elo_priors is not None:
            default_home = config.elo_priors.get((league_id, home_id), base_elo)
            default_away = config.elo_priors.get((league_id, away_id), base_elo)
        else:
            default_home = base_elo
            default_away = base_elo
        home_elo = team_elo.get(home_id, default_home)
        away_elo = team_elo.get(away_id, default_away)

        elo_home_list.append(home_elo)
        elo_away_list.append(away_elo)

        # If match has result, update Elo
        if pd.notna(home_score_val) and pd.notna(away_score_val):
            home_score = int(home_score_val)
            away_score = int(away_score_val)
            if home_score > away_score:
                outcome_home = 1.0
                outcome_away = 0.0
            elif home_score < away_score:
                outcome_home = 0.0
                outcome_away = 1.0
            else:
                outcome_home = 0.5
                outcome_away = 0.5

            # Apply configurable home advantage to Elo when computing expectation
            adv = 0.0 if config.neutral_mode else config.home_advantage_elo
            expected_home = _expected_score(home_elo + adv, away_elo)
            expected_away = 1.0 - expected_home

            # Per-game K policy: start from per-league base, adjust by season phase
            base_k = (
                config.k_by_league.get(league_id, config.elo_k)
                if isinstance(config.k_by_league, dict)
                else config.elo_k
            )
            # Derive season phase (same mapping as load_events_dataframe)
            date_val = row[3]
            k = base_k
            if pd.notna(date_val):
                try:
                    month = pd.Timestamp(date_val).month
                    phase = ((month - 8) % 12) / 11.0
                    if phase < config.k_season_phase_early:
                        k = base_k * config.k_early_mult
                    elif phase > config.k_season_phase_late:
                        k = base_k * config.k_late_mult
                except Exception:
                    k = base_k
            new_home = home_elo + k * (outcome_home - expected_home)
            new_away = away_elo + k * (outcome_away - expected_away)

            team_elo[home_id] = new_home
            team_elo[away_id] = new_away

    df = df.copy()
    df["elo_home_pre"] = pd.Series(elo_home_list, index=df.index, dtype="float64")
    df["elo_away_pre"] = pd.Series(elo_away_list, index=df.index, dtype="float64")
    df["elo_diff"] = df["elo_home_pre"] - df["elo_away_pre"]
    return df


def add_form_features(df: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    # Rolling last-N win rate for home and away teams within each league
    df = df.copy()

    df.sort_values(["league_id", "date_event", "timestamp", "event_id"], inplace=True)

    # Prepare per team match results
    team_last_n_wins: Dict[Tuple[int, int], List[int]] = {}  # (league_id, team_id) -> results list 1/0
    home_form: List[float] = []
    away_form: List[float] = []

    window = config.form_window

    for row in df.itertuples(index=False, name=None):
        league_val = row[1]
        home_val = row[5]
        away_val = row[6]
        home_score_val = row[7]
        away_score_val = row[8]

        league_id = int(league_val) if pd.notna(league_val) else -1
        home_id = int(home_val) if pd.notna(home_val) else -1
        away_id = int(away_val) if pd.notna(away_val) else -1

        # Compute pre-match rolling win rate for each side
        home_hist = team_last_n_wins.get((league_id, home_id), [])
        away_hist = team_last_n_wins.get((league_id, away_id), [])
        home_form.append(sum(home_hist[-window:]) / window if len(home_hist) >= window else (sum(home_hist) / max(1, len(home_hist)) if home_hist else 0.0))
        away_form.append(sum(away_hist[-window:]) / window if len(away_hist) >= window else (sum(away_hist) / max(1, len(away_hist)) if away_hist else 0.0))

        # After match, update histories if we have results
        if pd.notna(home_score_val) and pd.notna(away_score_val):
            home_score = int(home_score_val)
            away_score = int(away_score_val)
            home_win = 1 if home_score > away_score else (0 if home_score < away_score else 0)
            team_last_n_wins.setdefault((league_id, home_id), []).append(home_win)
            team_last_n_wins.setdefault((league_id, away_id), []).append(1 - home_win if home_score != away_score else 0)

    df["home_form"] = pd.Series(home_form, index=df.index, dtype="float64")
    df["away_form"] = pd.Series(away_form, index=df.index, dtype="float64")
    df["form_diff"] = df["home_form"] - df["away_form"]
    return df


def add_rest_goal_h2h_features(df: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    df = df.copy()
    df.sort_values(["league_id", "date_event", "timestamp", "event_id"], inplace=True)

    # Rest days tracking
    last_match_date: Dict[Tuple[int, int], object] = {}
    home_rest: List[float] = []
    away_rest: List[float] = []

    # Goal diff tracking
    team_goal_diffs: Dict[Tuple[int, int], List[int]] = {}
    home_goal_diff_form: List[float] = []
    away_goal_diff_form: List[float] = []

    # Head-to-head tracking
    # Venue-aware series for backward compatibility
    h2h_results: Dict[Tuple[int, int, int], List[int]] = {}
    # Venue-neutral cumulative wins per pair, ignoring venue
    pair_wins: Dict[Tuple[int, int, int], Dict[int, int]] = {}
    h2h_home_rate: List[float] = []

    for row in df.itertuples(index=False, name=None):
        league_val = row[1]
        home_val = row[5]
        away_val = row[6]
        date_val = row[3]
        home_score_val = row[7]
        away_score_val = row[8]

        league_id = int(league_val) if pd.notna(league_val) else -1
        home_id = int(home_val) if pd.notna(home_val) else -1
        away_id = int(away_val) if pd.notna(away_val) else -1
        date_ev = pd.Timestamp(date_val) if pd.notna(date_val) else None

        # Rest days
        if date_ev is not None:
            prev_home = last_match_date.get((league_id, home_id))
            prev_away = last_match_date.get((league_id, away_id))
            home_rest.append((cast(pd.Timestamp, date_ev) - cast(pd.Timestamp, prev_home)) .days if isinstance(prev_home, pd.Timestamp) else 10.0)
            away_rest.append((cast(pd.Timestamp, date_ev) - cast(pd.Timestamp, prev_away)).days if isinstance(prev_away, pd.Timestamp) else 10.0)
        else:
            home_rest.append(10.0)
            away_rest.append(10.0)

        # Goal diff form
        home_gd_hist = team_goal_diffs.get((league_id, home_id), [])
        away_gd_hist = team_goal_diffs.get((league_id, away_id), [])
        w = config.goaldiff_window
        h_gd_form = sum(home_gd_hist[-w:]) / w if len(home_gd_hist) >= w else (sum(home_gd_hist) / max(1, len(home_gd_hist)) if home_gd_hist else 0.0)
        a_gd_form = sum(away_gd_hist[-w:]) / w if len(away_gd_hist) >= w else (sum(away_gd_hist) / max(1, len(away_gd_hist)) if away_gd_hist else 0.0)
        home_goal_diff_form.append(h_gd_form)
        away_goal_diff_form.append(a_gd_form)

        # Head-to-head
        if config.neutral_mode:
            # Venue-neutral rate: wins by current home team / total between teams
            key = (league_id, min(home_id, away_id), max(home_id, away_id))
            wins = pair_wins.get(key, {})
            total = sum(wins.values())
            rate = (wins.get(home_id, 0) / total) if total > 0 else 0.5
            h2h_home_rate.append(rate)
        else:
            # Venue-aware home perspective
            h2h_hist = h2h_results.get((league_id, home_id, away_id), [])
            if h2h_hist:
                h2h_home_rate.append(sum(h2h_hist[-config.h2h_window:]) / min(len(h2h_hist), config.h2h_window))
            else:
                h2h_home_rate.append(0.5)

        # After match, update histories if result available
        if pd.notna(home_score_val) and pd.notna(away_score_val) and (date_ev is not None):
            home_score = int(home_score_val)
            away_score = int(away_score_val)
            # Update last match date
            date_ev_cast = cast(pd.Timestamp, date_ev)
            last_match_date[(league_id, home_id)] = date_ev_cast
            last_match_date[(league_id, away_id)] = date_ev_cast
            # Update goal diff histories
            gd = home_score - away_score
            team_goal_diffs.setdefault((league_id, home_id), []).append(gd)
            team_goal_diffs.setdefault((league_id, away_id), []).append(-gd)
            # Update H2H
            home_win = 1 if home_score > away_score else (0 if home_score < away_score else 0)
            h2h_results.setdefault((league_id, home_id, away_id), []).append(home_win)
            # Update venue-neutral pair wins
            key = (league_id, min(home_id, away_id), max(home_id, away_id))
            wins = pair_wins.setdefault(key, {home_id: 0, away_id: 0})
            if home_score > away_score:
                wins[home_id] = wins.get(home_id, 0) + 1
            elif away_score > home_score:
                wins[away_id] = wins.get(away_id, 0) + 1

    df["home_rest_days"] = pd.Series(home_rest, index=df.index, dtype="float64")
    df["away_rest_days"] = pd.Series(away_rest, index=df.index, dtype="float64")
    df["rest_diff"] = df["home_rest_days"] - df["away_rest_days"]
    df["home_goal_diff_form"] = pd.Series(home_goal_diff_form, index=df.index, dtype="float64")
    df["away_goal_diff_form"] = pd.Series(away_goal_diff_form, index=df.index, dtype="float64")
    df["goal_diff_form_diff"] = df["home_goal_diff_form"] - df["away_goal_diff_form"]
    df["h2h_home_rate"] = pd.Series(h2h_home_rate, index=df.index, dtype="float64")
    return df


def add_win_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add home_wr_home and away_wr_away features"""
    df = df.copy()
    
    # Calculate historical win rates for home teams when playing home
    home_wr_dict = dict(df.groupby('home_team_id')['home_win'].mean())
    df['home_wr_home'] = df['home_team_id'].replace(home_wr_dict).fillna(0.5)
    
    # Calculate historical win rates for away teams when playing away  
    away_wr_dict = {}
    for team_id, group in df.groupby('away_team_id'):
        away_wins = (1 - group['home_win']).mean()  # Away team wins when home_win == 0
        away_wr_dict[team_id] = away_wins
    df['away_wr_away'] = df['away_team_id'].replace(away_wr_dict).fillna(0.5)
    
    return df

def add_elo_expectation_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add pair_elo_expectation feature"""
    df = df.copy()
    
    # Calculate expected win probability based on Elo difference
    df['pair_elo_expectation'] = 1.0 / (1.0 + 10 ** ((df['elo_away_pre'] - df['elo_home_pre']) / 400.0))
    
    return df

def add_advanced_features(df: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Add advanced features for better score prediction"""
    # IMPORTANT: Add the missing features that training expects
    df = add_win_rate_features(df)
    df = add_elo_expectation_features(df)
    
    # Elo ratio and sum
    df["elo_ratio"] = df["elo_home_pre"] / df["elo_away_pre"].replace(0, 1)
    df["elo_sum"] = df["elo_home_pre"] + df["elo_away_pre"]
    
    # Improved form calculation (longer window for better stability)
    df["form_diff_10"] = df["home_form"] - df["away_form"]  # More stable than 5-game
    
    # Recent head-to-head (better calculation)
    df["h2h_recent"] = df["h2h_home_rate"]  # Already calculated properly
    
    # Rest ratio (more sophisticated)
    df["rest_ratio"] = df["home_rest_days"] / df["away_rest_days"].replace(0, 7)
    
    # Dynamic home advantage based on league and historical performance
    league_home_advantage = {
        4986: 0.65,  # Rugby Championship - high home advantage
        4446: 0.58,  # United Rugby Championship - moderate
        5069: 0.62,  # Currie Cup - high (South African rugby)
        4574: 0.50   # Rugby World Cup - neutral venues
    }
    
    df["home_advantage"] = df["league_id"].replace(league_home_advantage).fillna(0.55)
    
    # Smart attack/defense strength based on historical performance
    df["home_attack_strength"] = df["home_form"]  # Use form as proxy
    df["away_attack_strength"] = df["away_form"]
    df["home_defense_strength"] = 1.0 - df["away_form"]  # Inversely related to opponent scoring
    df["away_defense_strength"] = 1.0 - df["home_form"]
    
    # Enhanced momentum (accounts for trend direction)
    df["home_momentum"] = df["home_form"] + (df["home_goal_diff_form"] / 10.0)
    df["away_momentum"] = df["away_form"] + (df["away_goal_diff_form"] / 10.0)
    df["momentum_diff"] = df["home_momentum"] - df["away_momentum"]
    
    # League strength based on historical competitiveness
    league_strength_map = {
        4986: 0.85,  # World-class Rugby Championship  
        4446: 0.75,  # Strong professional league
        5069: 0.70,  # Good domestic level
        4574: 0.95   # Elite tournament level
    }
    df["league_strength"] = df["league_id"].replace(league_strength_map).fillna(0.65)
    
    # League-specific form (adjusted for league strength)
    df["home_league_form"] = df["home_form"] * df["league_strength"]
    df["away_league_form"] = df["away_form"] * df["league_strength"]
    
    return df


def build_feature_table(conn: sqlite3.Connection, config: FeatureConfig) -> pd.DataFrame:
    df = load_events_dataframe(conn)
    df = add_elo_features(df, config)
    df = add_form_features(df, config)
    df = add_rest_goal_h2h_features(df, config)
    # Home binary; set to 0 in neutral mode
    df["is_home"] = 0 if config.neutral_mode else 1
    # Add advanced features for better score prediction
    df = add_advanced_features(df, config)
    
    # Keep essential columns
    cols = [
        "event_id",
        "league_id",
        "season",
        "date_event",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "home_win",
        "elo_diff",
        "form_diff",
        "elo_home_pre",
        "elo_away_pre",
        "home_form",
        "away_form",
        "home_rest_days",
        "away_rest_days",
        "rest_diff",
        "home_goal_diff_form",
        "away_goal_diff_form",
        "goal_diff_form_diff",
        "h2h_home_rate",
        "season_phase",
        "is_home",
        # Advanced features
        "elo_ratio",
        "elo_sum",
        "form_diff_10",
        "h2h_recent",
        "rest_ratio",
        "home_advantage",
        "home_attack_strength",
        "away_attack_strength",
        "home_defense_strength",
        "away_defense_strength",
        "home_momentum",
        "away_momentum",
        "momentum_diff",
        "league_strength",
        "home_league_form",
        "away_league_form",
        # Critical missing features
        "home_wr_home",
        "away_wr_away", 
        "pair_elo_expectation",
    ]
    # Ensure DataFrame return
    return df.loc[:, cols].copy()
