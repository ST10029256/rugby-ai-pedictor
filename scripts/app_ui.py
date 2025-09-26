from __future__ import annotations

import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from typing import Any, cast

import streamlit as st

# Add the project root to the Python path
# This allows Streamlit to find the 'prediction' package when run from the 'scripts' directory
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


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


def main() -> None:
    st.set_page_config(page_title="Rugby Predictions", layout="wide")
    st.title("Rugby Predictions Dashboard")
    # Updated: Database sync fix - 2025-09-26

    # Controls
    league_name_to_id = {
        "Rugby Championship": 4986,
        "United Rugby Championship": 4446,
        "Currie Cup": 5069,
        "Rugby World Cup": 4574,
    }
    league = st.sidebar.selectbox("League", list(league_name_to_id.keys()), index=1)
    league_id = league_name_to_id[league]
    # Neutral mode handled automatically by league (e.g., World Cup often neutralized)
    neutral_mode = (league_id in {4574})
    elo_k = 24  # handled automatically; no manual control in UI

    # Data and features
    # Force absolute path to ensure correct database file
    import os
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.sqlite")
    st.write(f"🔍 DEBUG: Using database: {db_path}")
    st.write(f"📁 Current working directory: {os.getcwd()}")
    st.write(f"📂 Files in current dir: {os.listdir('.')}")
    
    # Check if database file exists and its size
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        st.write(f"✅ Database exists, size: {file_size} bytes")
    else:
        st.error(f"❌ Database file not found at: {db_path}")
    
    # Force cache refresh by adding timestamp to database connection
    import time
    cache_buster = time.time()
    st.write(f"🔄 Cache buster: {cache_buster}")
    
    # Add refresh button to force reload
    st.write("**Cache Control:**")
    st.write("Buttons should appear below:")
    
    # Try different button approaches
    refresh_clicked = st.button("🔄 Force Refresh Data", key="refresh_btn")
    clear_clicked = st.button("🗑️ Clear All Caches", key="clear_btn")
    
    if refresh_clicked:
        st.write("🔄 Refresh button clicked!")
        st.cache_data.clear()
        st.rerun()
    
    if clear_clicked:
        st.write("🗑️ Clear button clicked!")
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    
    st.write("**Debug Info:**")
    st.write(f"Session state data_refresh: {st.session_state.get('data_refresh', 'Not set')}")
    st.write(f"Current cache buster: {cache_buster}")
    st.write(f"Refresh clicked: {refresh_clicked}")
    st.write(f"Clear clicked: {clear_clicked}")
    
    # Connect to database (SQLite doesn't support query parameters)
    conn = sqlite3.connect(db_path)
    
    # Force fresh data load by checking session state
    if 'data_refresh' not in st.session_state:
        st.session_state.data_refresh = cache_buster
    
    # If cache buster changed, force reload
    if st.session_state.data_refresh != cache_buster:
        st.session_state.data_refresh = cache_buster
        st.cache_data.clear()
    
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

    feature_cols = [
        "elo_diff", "form_diff", "elo_home_pre", "elo_away_pre",
        "home_form", "away_form", "home_rest_days", "away_rest_days",
        "rest_diff", "home_goal_diff_form", "away_goal_diff_form",
        "goal_diff_form_diff", "h2h_home_rate", "season_phase", "is_home"
    ]
    present_cols = [c for c in feature_cols if c in hist.columns]
    if len(hist) == 0 or len(present_cols) == 0:
        st.warning("Insufficient historical data for this league.")
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

    # Train simple ensemble on historical
    extra_cols = ["home_wr_home", "away_wr_away", "pair_elo_expectation"]
    home_wr = hist.groupby("home_team_id")["home_win"].mean().astype("float64")
    away_wr = hist.assign(away_win=lambda d: (1 - d["home_win"]).astype(float)).groupby("away_team_id")["away_win"].mean().astype("float64")
    hist = hist.copy()
    _home_wr_map = {safe_to_int(k): safe_to_float(v, default=float("nan")) for k, v in home_wr.items()}
    _away_wr_map = {safe_to_int(k): safe_to_float(v, default=float("nan")) for k, v in away_wr.items()}
    hist["home_wr_home"] = hist["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan")))
    hist["away_wr_away"] = hist["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan")))
    hist["pair_elo_expectation"] = 1.0 / (1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0))

    all_cols = present_cols + extra_cols
    X_hist = hist[all_cols].to_numpy()
    y_hist = hist["home_win"].astype(int).to_numpy()
    y_home = hist["home_score"].to_numpy()
    y_away = hist["away_score"].to_numpy()

    base_lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    calibrated = CalibratedClassifierCV(base_lr, method="isotonic", cv=5)
    clf = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), calibrated)
    clf.fit(X_hist, y_hist)
    gbdt_clf = HistGradientBoostingClassifier(random_state=42)
    gbdt_clf.fit(X_hist, y_hist)
    reg_home = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=1.0))
    reg_away = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=1.0))
    reg_home.fit(X_hist, y_home)
    reg_away.fit(X_hist, y_away)
    gbdt_home = HistGradientBoostingRegressor(random_state=42)
    gbdt_away = HistGradientBoostingRegressor(random_state=42)
    gbdt_home.fit(X_hist, y_home)
    gbdt_away.fit(X_hist, y_away)

    # Prepare upcoming rows
    if len(upc) == 0:
        st.info("No upcoming fixtures for this league.")
        return

    upc = upc.copy()
    for col in all_cols:
        if col not in upc.columns:
            upc[col] = np.nan
    upc["elo_diff"] = upc["elo_diff"].where(upc["elo_diff"].notna(), upc["elo_home_pre"] - upc["elo_away_pre"])
    if "home_form" in upc.columns and "away_form" in upc.columns:
        upc["form_diff"] = upc["form_diff"].where(upc["form_diff"].notna(), upc["home_form"] - upc["away_form"])
    if "home_rest_days" in upc.columns and "away_rest_days" in upc.columns:
        upc["rest_diff"] = upc["rest_diff"].where(upc["rest_diff"].notna(), upc["home_rest_days"] - upc["away_rest_days"])
    if "home_goal_diff_form" in upc.columns and "away_goal_diff_form" in upc.columns:
        upc["goal_diff_form_diff"] = upc["goal_diff_form_diff"].where(upc["goal_diff_form_diff"].notna(), upc["home_goal_diff_form"] - upc["away_goal_diff_form"])
    upc["pair_elo_expectation"] = upc["pair_elo_expectation"].where(
        upc["pair_elo_expectation"].notna(),
        1.0 / (1.0 + 10 ** ((upc["elo_away_pre"] - upc["elo_home_pre"]) / 400.0)),
    )
    upc["home_wr_home"] = upc["home_wr_home"].where(upc["home_wr_home"].notna(), upc["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan"))))
    upc["away_wr_away"] = upc["away_wr_away"].where(upc["away_wr_away"].notna(), upc["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan"))))

    X_upc = upc[all_cols].to_numpy()
    prob_lr = cast(np.ndarray, clf.predict_proba(X_upc))[:, 1]
    prob_gbdt = cast(np.ndarray, gbdt_clf.predict_proba(X_upc))[:, 1]
    prob_home = 0.5 * (prob_lr + prob_gbdt)
    prob_away = 1.0 - prob_home
    pred_home = 0.5 * cast(np.ndarray, reg_home.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_home.predict(X_upc))
    pred_away = 0.5 * cast(np.ndarray, reg_away.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_away.predict(X_upc))

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
        "pick": [(_name(h) if p >= 0.5 else _name(a)) for h, a, p in zip(upc["home_team_id"], upc["away_team_id"], prob_home)],
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


if __name__ == "__main__":
    main()


