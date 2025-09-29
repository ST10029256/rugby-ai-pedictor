from __future__ import annotations

import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from typing import Any, cast

import streamlit as st

# Add the project root to the Python path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig
from scripts.model_manager import ModelManager

def safe_to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return float(value)
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        v = float(value)
        if np.isnan(v):
            return default
        return v
    except Exception:
        return default

def safe_to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return int(value)
    try:
        return int(value)
    except Exception:
        return default

@st.cache_resource
def load_model_manager():
    """Load the model manager with caching"""
    return ModelManager()

def main() -> None:
    st.set_page_config(page_title="Rugby Predictions", layout="centered", initial_sidebar_state="collapsed")
    st.title("🏉 Rugby Predictions")
    st.caption("🤖 AI-powered predictions that update automatically")

    # Initialize model manager
    model_manager = load_model_manager()
    
    # Show model status
    with st.sidebar:
        st.subheader("Model Status")
        registry_summary = model_manager.get_registry_summary()
        
        if "error" not in registry_summary:
            st.write(f"**Last Updated:** {registry_summary.get('last_updated', 'Unknown')}")
            st.write(f"**Leagues:** {registry_summary.get('total_leagues', 0)}")
            
            # Show league-specific status
            for league_id, info in registry_summary.get("leagues", {}).items():
                league_name = info.get("name", f"League {league_id}")
                accuracy = info.get("winner_accuracy", 0)
                mae = info.get("overall_mae", 0)
                st.write(f"**{league_name}:** {accuracy:.1%} accuracy, {mae:.1f} MAE")
        else:
            st.warning("Model registry not available")

    # Controls
    league_name_to_id = {
        "Rugby Championship": 4986,
        "United Rugby Championship": 4446,
        "Currie Cup": 5069,
        "Rugby World Cup": 4574,
    }
    league = st.sidebar.selectbox("League", list(league_name_to_id.keys()), index=1)
    league_id = league_name_to_id[league]
    
    # Check if model is available
    if not model_manager.is_model_available(league_id):
        st.error(f"No trained model available for {league}. Please train models first.")
        st.info("Run `python scripts/train_models.py` to train models.")
        return

    # Load the trained model
    model_package = model_manager.load_model(league_id)
    if not model_package:
        st.error(f"Failed to load model for {league}")
        return

    # Show model info
    st.sidebar.subheader("Current Model Info")
    st.sidebar.write(f"**Trained:** {model_package.get('trained_at', 'Unknown')}")
    st.sidebar.write(f"**Training Games:** {model_package.get('training_games', 0)}")
    
    performance = model_package.get("performance", {})
    st.sidebar.write(f"**Winner Accuracy:** {performance.get('winner_accuracy', 0):.1%}")
    st.sidebar.write(f"**Score MAE:** {performance.get('overall_mae', 0):.1f}")

    # Neutral mode handled automatically by league
    neutral_mode = (league_id in {4574})
    elo_k = 24

    # Data and features
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.sqlite")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=float(elo_k), neutral_mode=bool(neutral_mode)))

    # Upcoming fixtures for selected league (future/today only)
    upcoming = df[df["home_win"].isna()].copy()
    upc = cast(pd.DataFrame, upcoming[upcoming["league_id"] == league_id].copy())
    if "date_event" in upc.columns:
        try:
            today = pd.Timestamp(pd.Timestamp.today().date())
            upc = upc.copy()
            upc["date_event"] = pd.to_datetime(upc["date_event"], errors="coerce")
            upc = cast(pd.DataFrame, upc[upc["date_event"] >= today])
        except Exception:
            pass

    # Historical data
    hist = cast(pd.DataFrame, df[(df["league_id"] == league_id) & df["home_win"].notna()].copy())

    # Get feature columns from the trained model
    feature_cols = model_package.get("feature_columns", [])
    if not feature_cols:
        st.error("No feature columns found in trained model")
        return

    # Team names for display
    team_name: dict[int, str] = {}
    try:
        rows_nm = conn.cursor().execute(
            """
            SELECT DISTINCT t.id, COALESCE(t.name, '')
            FROM team t
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = ?
            """,
            (league_id,),
        ).fetchall()
        for tid_raw, nm in rows_nm:
            tid = safe_to_int(tid_raw, default=-1)
            team_name[tid] = nm or f"Team {tid}"
    except Exception:
        pass

    # Prepare upcoming rows with the same features as training
    if len(upc) == 0:
        st.info("No upcoming fixtures for this league.")
        return

    upc = upc.copy()
    
    # Add missing columns with default values
    for col in feature_cols:
        if col not in upc.columns:
            upc[col] = np.nan

    # Calculate derived features
    upc["elo_diff"] = upc["elo_diff"].where(upc["elo_diff"].notna(), upc["elo_home_pre"] - upc["elo_away_pre"])
    if "home_form" in upc.columns and "away_form" in upc.columns:
        upc["form_diff"] = upc["form_diff"].where(upc["form_diff"].notna(), upc["home_form"] - upc["away_form"])
    if "home_rest_days" in upc.columns and "away_rest_days" in upc.columns:
        upc["rest_diff"] = upc["rest_diff"].where(upc["rest_diff"].notna(), upc["home_rest_days"] - upc["away_rest_days"])
    if "home_goal_diff_form" in upc.columns and "away_goal_diff_form" in upc.columns:
        upc["goal_diff_form_diff"] = upc["goal_diff_form_diff"].where(upc["goal_diff_form_diff"].notna(), upc["home_goal_diff_form"] - upc["away_goal_diff_form"])
    
    # Calculate pair elo expectation
    upc["pair_elo_expectation"] = upc["pair_elo_expectation"].where(
        upc["pair_elo_expectation"].notna(),
        1.0 / (1.0 + 10 ** ((upc["elo_away_pre"] - upc["elo_home_pre"]) / 400.0)),
    )
    
    # Get team mappings from the trained model
    team_mappings = model_package.get("team_mappings", {})
    _home_wr_map = team_mappings.get("home_wr_map", {})
    _away_wr_map = team_mappings.get("away_wr_map", {})
    
    upc["home_wr_home"] = upc["home_wr_home"].where(upc["home_wr_home"].notna(), upc["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan"))))
    upc["away_wr_away"] = upc["away_wr_away"].where(upc["away_wr_away"].notna(), upc["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan"))))

    # Prepare features for prediction
    X_upc = upc[feature_cols].to_numpy()
    
    # Make predictions using the trained models
    prob_home_list = []
    pred_home_list = []
    pred_away_list = []
    
    for i in range(len(X_upc)):
        features = X_upc[i]
        
        # Predict winner probability
        home_prob, away_prob = model_manager.predict_winner_probability(league_id, features)
        prob_home_list.append(home_prob)
        
        # Predict scores
        home_score, away_score = model_manager.predict_scores(league_id, features)
        pred_home_list.append(home_score)
        pred_away_list.append(away_score)

    prob_home = np.array(prob_home_list)
    pred_home = np.array(pred_home_list)
    pred_away = np.array(pred_away_list)

    # Display table
    def _name(tid: Any) -> str:
        return team_name.get(safe_to_int(tid, -1), str(safe_to_int(tid, -1)))

    if "date_event" in upc.columns:
        date_series = upc["date_event"].astype(str)
    else:
        date_series = pd.Series([""] * len(upc), dtype=str)
    
    disp = pd.DataFrame({
        "date": date_series,
        "home": upc["home_team_id"].apply(_name),
        "away": upc["away_team_id"].apply(_name),
        "home_win_prob": np.round(prob_home * 100.0, 1),
        "pred_home": np.round(pred_home, 1),
        "pred_away": np.round(pred_away, 1),
        "margin": np.round(pred_home - pred_away, 1),
        "pick": [(_name(h) if prob_home[i] >= 0.5 else _name(a)) for i, (h, a) in enumerate(zip(upc["home_team_id"], upc["away_team_id"]))],
    })
    disp = disp.sort_values(["date", "home"], ignore_index=True)

    st.subheader(f"Upcoming fixtures — {league}")
    st.dataframe(disp, use_container_width=True)

    # Per-fixture cards
    st.subheader("Summaries")
    for i in range(len(disp)):
        row = disp.iloc[i]
        winner = row["pick"]
        margin_line = f"{'Home' if row['margin'] >= 0 else 'Away'} by {abs(row['margin']):.1f}"
        st.markdown(f"**{row['home']} vs {row['away']}** — {row['date']}")
        st.markdown(
            f"Win prob: {float(row['home_win_prob']):.1f}% (home) | Predicted: {row['home']} {float(row['pred_home']):.1f} - {float(row['pred_away']):.1f} {row['away']} | Decision: {winner} | {margin_line}"
        )

    # Show retraining info
    st.sidebar.subheader("Auto-Retraining")
    st.sidebar.info("Models automatically retrain after each completed match and push updates to GitHub.")

    conn.close()

if __name__ == "__main__":
    main()
