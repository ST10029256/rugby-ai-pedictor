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
from sklearn.linear_model import LogisticRegression, Ridge, ElasticNet
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestRegressor


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
    
    # === SMART OPTIMIZED REGRESSION MODELS ===
    # League-specific optimizations: apply optimizations only for Rugby Championship & URC
    league_id = hist["league_id"].iloc[0] if len(hist) > 0 else None
    use_optimized = league_id in [4986, 4446]  # Rugby Championship & URC
    
    if use_optimized:
        # Optimized time-decay weights (6-7 months for better leagues)
        weights = None
        try:
            if "date_event" in hist.columns:
                max_dt = pd.to_datetime(hist["date_event"]).max()
                days = (pd.to_datetime(hist["date_event"]) - max_dt).dt.days.abs().astype(float)
                half_life_days = 200.0  # 6-7 months
                weights = np.exp(-days / half_life_days).astype(float)
            else:
                weights = np.ones(len(hist), dtype=float)
        except Exception:
            weights = np.ones(len(hist), dtype=float)

        # Optimized winsorization (less aggressive)
        def _winsorize(arr: np.ndarray, low: float = 0.01, high: float = 0.99) -> np.ndarray:
            a = np.asarray(arr, dtype=float)
            lo = float(np.quantile(a, low)) if len(a) else 0.0
            hi = float(np.quantile(a, high)) if len(a) else 0.0
            return np.clip(a, lo, hi)

        y_home_w = _winsorize(y_home)
        y_away_w = _winsorize(y_away)

        # Optimized regression models (less regularization)
        reg_home = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=0.5))
        reg_away = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=0.5))
        reg_home.fit(X_hist, y_home_w, ridge__sample_weight=weights)
        reg_away.fit(X_hist, y_away_w, ridge__sample_weight=weights)
        
        # Optimized gradient boosting models
        gbdt_home = HistGradientBoostingRegressor(
            random_state=42,
            learning_rate=0.08,
            max_iter=180,
            max_depth=7,
            min_samples_leaf=8,
            max_features=0.95
        )
        gbdt_away = HistGradientBoostingRegressor(
            random_state=42,
            learning_rate=0.05,
            max_iter=150,
            max_depth=6,
            min_samples_leaf=12,
            max_features=0.85
        )
        gbdt_home.fit(X_hist, y_home_w, sample_weight=weights)
        gbdt_away.fit(X_hist, y_away_w, sample_weight=weights)
        
    else:
        # Current approach for Currie Cup & World Cup
        weights = None
        try:
            if "date_event" in hist.columns:
                max_dt = pd.to_datetime(hist["date_event"]).max()
                days = (pd.to_datetime(hist["date_event"]) - max_dt).dt.days.abs().astype(float)
                half_life_days = 200.0
                weights = np.exp(-days / half_life_days).astype(float)
            else:
                weights = np.ones(len(hist), dtype=float)
        except Exception:
            weights = np.ones(len(hist), dtype=float)

        # Improved winsorization (less aggressive)
        def _winsorize(arr: np.ndarray, low: float = 0.01, high: float = 0.99) -> np.ndarray:
            a = np.asarray(arr, dtype=float)
            lo = float(np.quantile(a, low)) if len(a) else 0.0
            hi = float(np.quantile(a, high)) if len(a) else 0.0
            return np.clip(a, lo, hi)

        y_home_w = _winsorize(y_home)
        y_away_w = _winsorize(y_away)

        # Improved regression models with better hyperparameters
        reg_home = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=0.5))
        reg_away = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=0.5))
        reg_home.fit(X_hist, y_home_w, ridge__sample_weight=weights)
        reg_away.fit(X_hist, y_away_w, ridge__sample_weight=weights)
        
        # Improved gradient boosting models with better hyperparameters
        gbdt_home = HistGradientBoostingRegressor(
            random_state=42,
            learning_rate=0.1,
            max_iter=200,
            max_depth=6,
            min_samples_leaf=5,
            max_features=0.8
        )
        gbdt_away = HistGradientBoostingRegressor(
            random_state=42,
            learning_rate=0.1,
            max_iter=200,
            max_depth=6,
            min_samples_leaf=5,
            max_features=0.8
        )
        gbdt_home.fit(X_hist, y_home_w, sample_weight=weights)
        gbdt_away.fit(X_hist, y_away_w, sample_weight=weights)

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
    
    # Use improved ensemble weights based on league
    if use_optimized:
        # Improved ensemble weights (30% Ridge, 70% GBDT for home; 30% Ridge, 70% GBDT for away)
        pred_home = 0.3 * cast(np.ndarray, reg_home.predict(X_upc)) + 0.7 * cast(np.ndarray, gbdt_home.predict(X_upc))
        pred_away = 0.3 * cast(np.ndarray, reg_away.predict(X_upc)) + 0.7 * cast(np.ndarray, gbdt_away.predict(X_upc))
    else:
        # Current ensemble weights (50% Ridge, 50% GBDT)
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
        "pick": [(_name(h) if pred_home[i] >= pred_away[i] else _name(a)) for i, (h, a) in enumerate(zip(upc["home_team_id"], upc["away_team_id"]))],
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


