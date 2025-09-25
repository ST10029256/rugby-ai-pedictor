from __future__ import annotations

import sqlite3
import json
import numpy as np
import pandas as pd
from typing import cast, Any
import argparse
import math
from datetime import datetime, timezone
from prediction.features import build_feature_table, FeatureConfig

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.model_selection import cross_val_predict, cross_val_score
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


def safe_to_float(value: object, default: float = 0.0) -> float:
    """Best-effort conversion to float with fallback default for missing/NaN."""
    if value is None:
        return default
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return float(value)
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        v = float(value)  # type: ignore[arg-type]
        if np.isnan(v):
            return default
        return v
    except Exception:
        return default


def safe_to_int(value: object, default: int = 0) -> int:
    """Best-effort conversion to int with sensible fallback for missing/NaN."""
    if value is None:
        return default
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return int(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (float, np.floating)):
        return bool(np.isnan(value))
    return False

def compute_residual_std(model, X, y) -> float:
    """Compute residual standard deviation for a fitted regression model."""
    preds = model.predict(X)
    residuals = y - preds
    return float(np.sqrt(np.mean(residuals**2)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Rugby Championship predictions")
    # Requires Python 3.9+: BooleanOptionalAction provides --neutral-mode/--no-neutral-mode
    try:
        bool_action = argparse.BooleanOptionalAction  # type: ignore[attr-defined]
    except Exception:
        # Fallback to store_true with default True (no --no-neutral-mode variant)
        bool_action = None  # type: ignore[assignment]
    if bool_action is not None:
        parser.add_argument("--neutral-mode", action=bool_action, default=True, help="Use neutral venue features (disable to include home advantage)")
    else:
        parser.add_argument("--neutral-mode", action="store_true", default=True, help="Use neutral venue features")
    parser.add_argument("--calibration", choices=["isotonic", "sigmoid", "none"], default="isotonic", help="Probability calibration method")
    parser.add_argument("--elo-k", type=float, default=24.0, help="Elo K factor for feature construction")
    parser.add_argument("--export-csv", action="store_true", help="Export historical evaluation CSVs to artifacts/")
    parser.add_argument("--ignore-date", action="store_true", help="Do not filter out past-dated fixtures; consider all with missing scores")
    args = parser.parse_args()
    # Load registry (kept for completeness)
    with open("artifacts/per_league_best/registry.json", "r") as f:
        reg = json.load(f)

    # Build feature table
    conn = sqlite3.connect("data.sqlite")
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=float(args.elo_k), neutral_mode=bool(args.neutral_mode)))

    # Rugby Championship fixtures
    upcoming = df[df["home_win"].isna()].copy()
    l4986 = cast(pd.DataFrame, upcoming[upcoming["league_id"] == 4986].copy())
    # Keep only future/today unless explicitly ignored
    if (not args.ignore_date) and ("date_event" in l4986.columns):
        try:
            today = pd.Timestamp(datetime.now(timezone.utc).date())
            l4986 = l4986.copy()
            l4986["date_event"] = pd.to_datetime(l4986["date_event"], errors="coerce")
            l4986 = cast(pd.DataFrame, l4986[l4986["date_event"] >= today])
        except Exception:
            pass

    # Preview key upcoming fixture features for Rugby Championship
    preview_cols = [
        "home_team_id",
        "away_team_id",
        "elo_home_pre",
        "elo_away_pre",
        "h2h_home_rate",
    ]
    try:
        print("\nUpcoming fixtures (selected features):")
        print(l4986.reindex(columns=preview_cols))
    except Exception:
        pass

    hist = cast(
        pd.DataFrame, df[(df["league_id"] == 4986) & df["home_win"].notna()].copy()
    )

    feature_cols = [
        "elo_diff", "form_diff", "elo_home_pre", "elo_away_pre",
        "home_form", "away_form", "home_rest_days", "away_rest_days",
        "rest_diff", "home_goal_diff_form", "away_goal_diff_form",
        "goal_diff_form_diff", "h2h_home_rate", "season_phase", "is_home"
    ]

    present_cols = [c for c in feature_cols if c in hist.columns]
    if len(hist) == 0 or len(present_cols) == 0:
        print("Insufficient historical data to train models for league 4986.")
        return

    # Team-level baselines to inject per-fixture variation
    # Home win rate when team plays at home
    home_wr_series = (
        hist.dropna(subset=["home_win"])
        .groupby("home_team_id")["home_win"]
        .mean()
    )
    # Away win rate when team plays away (1 - home_win for opponent)
    away_wr_series = (
        hist.dropna(subset=["home_win"])  
        .assign(away_win=lambda df_: (1 - df_["home_win"]).astype(float))
        .groupby("away_team_id")["away_win"]
        .mean()
    )
    # Ensure numeric types and use Series directly for mapping
    home_wr_series = home_wr_series.astype("float64")
    away_wr_series = away_wr_series.astype("float64")

    # Add extra columns to historical frame for training
    extra_cols = ["home_wr_home", "away_wr_away", "pair_elo_expectation"]
    hist = hist.copy()
    # Use dictionary mapping to avoid pandas dtype inference issues for type checkers
    home_wr_map: dict[int, float] = {}
    for k, v in home_wr_series.items():
        home_wr_map[safe_to_int(cast(Any, k))] = safe_to_float(cast(Any, v), default=float("nan"))
    away_wr_map: dict[int, float] = {}
    for k, v in away_wr_series.items():
        away_wr_map[safe_to_int(cast(Any, k))] = safe_to_float(cast(Any, v), default=float("nan"))
    def _map_home_wr(tid: object) -> float:
        if tid is None or (isinstance(tid, float) and np.isnan(tid)):
            return float("nan")
        return float(home_wr_map.get(safe_to_int(tid), float("nan")))
    def _map_away_wr(tid: object) -> float:
        if tid is None or (isinstance(tid, float) and np.isnan(tid)):
            return float("nan")
        return float(away_wr_map.get(safe_to_int(tid), float("nan")))
    hist["home_wr_home"] = hist["home_team_id"].apply(_map_home_wr)
    hist["away_wr_away"] = hist["away_team_id"].apply(_map_away_wr)
    # Elo-based pair expectation; let NaNs be imputed later
    hist["pair_elo_expectation"] = 1.0 / (
        1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0)
    )

    all_cols = present_cols + extra_cols

    # === Unify team ids across data sources by name (TheSportsDB vs API-Sports) ===
    # Build alias map: for each upcoming team id, if no history under that id,
    # map by normalized team name to an id that does have history.
    team_alias: dict[int, int] = {}
    team_name: dict[int, str] = {}
    try:
        cur = conn.cursor()
        rows_nm = cur.execute(
            """
            SELECT DISTINCT t.id, COALESCE(t.name, '')
            FROM team t
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = 4986
            """
        ).fetchall()
        def _norm(n: str) -> str:
            n2 = (n or '').strip().lower()
            if n2.endswith(' rugby'):
                n2 = n2[:-6].strip()
            return n2
        id_to_norm: dict[int, str] = {}
        norm_to_ids: dict[str, list[int]] = {}
        for tid_raw, nm in rows_nm:
            tid = safe_to_int(tid_raw, default=-1)
            team_name[tid] = nm or f"Team {tid}"
            key = _norm(nm or '')
            id_to_norm[tid] = key
            norm_to_ids.setdefault(key, []).append(tid)
        # Safe helpers for robust typing
        def _col_or_empty(df_: pd.DataFrame, col: str) -> pd.Series:
            return cast(pd.Series, df_[col]) if (isinstance(df_, pd.DataFrame) and (col in df_.columns)) else pd.Series(dtype='float64')
        def _to_id_set(series: pd.Series) -> set[int]:
            result: set[int] = set()
            if not isinstance(series, pd.Series):
                return result
            values = series.tolist()
            for val in values:
                if val is None:
                    continue
                # Handle numpy/pandas NaN separately
                if isinstance(val, (float, np.floating)):
                    if np.isnan(val):
                        continue
                    try:
                        result.add(int(val))
                    except Exception:
                        continue
                    continue
                if isinstance(val, (int, np.integer)):
                    result.add(int(val))
                    continue
                try:
                    result.add(int(str(val)))
                except Exception:
                    continue
            return result
        hist_ids: set[int] = _to_id_set(_col_or_empty(hist, 'home_team_id')) | _to_id_set(_col_or_empty(hist, 'away_team_id'))
        upc_ids: set[int] = _to_id_set(_col_or_empty(l4986, 'home_team_id')) | _to_id_set(_col_or_empty(l4986, 'away_team_id'))
        for tid in upc_ids:
            if tid in hist_ids:
                team_alias[tid] = tid
                continue
            key = id_to_norm.get(tid)
            if key:
                candidates = [cid for cid in norm_to_ids.get(key, []) if cid in hist_ids]
                if candidates:
                    team_alias[tid] = candidates[0]
                else:
                    team_alias[tid] = tid
            else:
                team_alias[tid] = tid
    except Exception:
        # Fallback: identity mapping
        team_alias = {}

    # Training sets (let pipelines impute missing values)
    X_hist = hist[all_cols].to_numpy()
    y_hist = hist["home_win"].astype(int).to_numpy()
    y_margin = (hist["home_score"] - hist["away_score"]).to_numpy()
    y_home = hist["home_score"].to_numpy()
    y_away = hist["away_score"].to_numpy()

    # Models
    base_lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    if args.calibration != "none":
        calibrated = CalibratedClassifierCV(
            base_lr,
            method=str(args.calibration),
            cv=5,
        )
        clf = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            calibrated,
        )
    else:
        clf = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            base_lr,
        )
    clf.fit(X_hist, y_hist)

    # === Time-decay weights and winsorized targets for robust regression ===
    weights = None
    try:
        if "date_event" in hist.columns:
            max_dt = pd.to_datetime(hist["date_event"]).max()
            days = (pd.to_datetime(hist["date_event"]) - max_dt).dt.days.abs().astype(float)
            half_life_days = 365.0
            weights = np.exp(-days / half_life_days).astype(float)
        else:
            weights = np.ones(len(hist), dtype=float)
    except Exception:
        weights = np.ones(len(hist), dtype=float)

    def _winsorize(arr: np.ndarray, low: float = 0.02, high: float = 0.98) -> np.ndarray:
        a = np.asarray(arr, dtype=float)
        lo = float(np.quantile(a, low)) if len(a) else 0.0
        hi = float(np.quantile(a, high)) if len(a) else 0.0
        return np.clip(a, lo, hi)

    y_home_w = _winsorize(y_home)
    y_away_w = _winsorize(y_away)
    y_margin_w = _winsorize(y_margin)

    reg_margin = make_pipeline(
        SimpleImputer(strategy="median"),
        RobustScaler(),
        Ridge(alpha=1.0),
    )
    reg_margin.fit(X_hist, y_margin_w, ridge__sample_weight=weights)

    reg_home = make_pipeline(
        SimpleImputer(strategy="median"),
        RobustScaler(),
        Ridge(alpha=1.0),
    )
    reg_home.fit(X_hist, y_home_w, ridge__sample_weight=weights)

    reg_away = make_pipeline(
        SimpleImputer(strategy="median"),
        RobustScaler(),
        Ridge(alpha=1.0),
    )
    reg_away.fit(X_hist, y_away_w, ridge__sample_weight=weights)

    # Gradient boosting models (time-decayed)
    gbdt_clf = HistGradientBoostingClassifier(random_state=42)
    gbdt_clf.fit(X_hist, y_hist, sample_weight=weights)
    gbdt_home = HistGradientBoostingRegressor(random_state=42)
    gbdt_home.fit(X_hist, y_home_w, sample_weight=weights)
    gbdt_away = HistGradientBoostingRegressor(random_state=42)
    gbdt_away.fit(X_hist, y_away_w, sample_weight=weights)
    gbdt_margin = HistGradientBoostingRegressor(random_state=42)
    gbdt_margin.fit(X_hist, y_margin_w, sample_weight=weights)

    # Residual std for intervals
    std_home = compute_residual_std(reg_home, X_hist, y_home)
    std_away = compute_residual_std(reg_away, X_hist, y_away)

    # Team-specific residual stds for tighter, matchup-aware intervals
    pred_home_hist = cast(np.ndarray, reg_home.predict(X_hist))
    pred_away_hist = cast(np.ndarray, reg_away.predict(X_hist))
    res_home_hist = y_home - pred_home_hist
    res_away_hist = y_away - pred_away_hist
    home_std_by_team = (
        pd.DataFrame({
            "team": hist["home_team_id"].to_numpy(),
            "res": res_home_hist,
        })
        .groupby("team")["res"]
        .apply(lambda r: float(np.sqrt(np.mean(np.square(r)))))
    )
    away_std_by_team = (
        pd.DataFrame({
            "team": hist["away_team_id"].to_numpy(),
            "res": res_away_hist,
        })
        .groupby("team")["res"]
        .apply(lambda r: float(np.sqrt(np.mean(np.square(r)))))
    )
    # Convert to plain dicts for precise typing and safe lookups
    home_std_map: dict[int, float] = {}
    for k, v in home_std_by_team.items():
        val = safe_to_float(cast(Any, v), default=float("nan"))
        if not math.isnan(val):
            home_std_map[safe_to_int(cast(Any, k))] = val
    away_std_map: dict[int, float] = {}
    for k, v in away_std_by_team.items():
        val = safe_to_float(cast(Any, v), default=float("nan"))
        if not math.isnan(val):
            away_std_map[safe_to_int(cast(Any, k))] = val

    # === Validation ===
    cv_acc = cross_val_score(clf, X_hist, y_hist, cv=5, scoring="accuracy").mean()
    prob_matrix = cast(
        np.ndarray,
        cross_val_predict(clf, X_hist, y_hist, cv=5, method="predict_proba"),
    )
    prob_preds = np.take(prob_matrix, indices=1, axis=1)
    brier = brier_score_loss(y_hist, prob_preds)
    ll = log_loss(y_hist, prob_preds)
    # Derive OOF class predictions for historical evaluation
    y_pred_oof = (prob_preds >= 0.5).astype(int)
    oof_acc = float(np.mean(y_pred_oof == y_hist))
    # Per-season summary (if available)
    season_summary: pd.DataFrame | None = None
    hist_pred_df: pd.DataFrame | None = None
    calib_df: pd.DataFrame | None = None
    if "season" in hist.columns:
        hist_eval_df = pd.DataFrame({
            "season": hist["season"].astype(str).fillna(""),
            "y": y_hist,
            "prob": prob_preds,
        })
        grouped = hist_eval_df.groupby("season", group_keys=False)[["y", "prob"]]
        season_summary_df = grouped.apply(
            lambda g: pd.Series({
                "n": int(len(g)),
                "acc": float(np.mean((g["prob"] >= 0.5).astype(int) == g["y"])),
                "brier": float(brier_score_loss(g["y"].to_numpy(), g["prob"].to_numpy())),
            })
        ).sort_index()
        # Ensure it's a DataFrame for the type checker
        season_summary = cast(pd.DataFrame, season_summary_df)

        # Historical predictions table (per match) for analysis/export
        hist_pred_df = pd.DataFrame({
            "date_event": hist["date_event"].astype(str),
            "season": hist["season"].astype(str).fillna(""),
            "league_id": hist["league_id"].astype(int),
            "home_team_id": hist["home_team_id"].astype(int),
            "away_team_id": hist["away_team_id"].astype(int),
            "home_score": hist["home_score"].astype(float),
            "away_score": hist["away_score"].astype(float),
            "y": y_hist,
            "prob_home": prob_preds,
            "prob_away": 1.0 - prob_preds,
        })
        # Derived columns: predicted class, confidence, margin
        hist_pred_df["pred_home_win"] = (hist_pred_df["prob_home"] >= 0.5).astype(int)
        hist_pred_df["confidence"] = np.maximum(hist_pred_df["prob_home"], hist_pred_df["prob_away"]).astype(float)
        hist_pred_df["actual_home_win"] = hist_pred_df["y"].astype(int)
        hist_pred_df["actual_margin"] = (hist_pred_df["home_score"] - hist_pred_df["away_score"]).astype(float)

        # Calibration curve for historical predictions
        frac_pos, mean_pred = calibration_curve(y_hist, prob_preds, n_bins=10, strategy="uniform")
        calib_df = pd.DataFrame({
            "mean_pred": mean_pred.astype(float),
            "frac_pos": frac_pos.astype(float),
        })

    print("\n=== Rugby Championship Predictions (Neutral Mode) ===")
    print(f"League: 4986 | Fixtures: {len(l4986)}")
    print(f"Cross-validated accuracy: {cv_acc:.2%}")
    print(f"OOF historical accuracy: {oof_acc:.2%}")
    print(f"Brier score: {brier:.4f}")
    print(f"Log-loss: {ll:.4f}")
    print("Note: classification (team to win) may differ from regression margin near 50% probs.")
    # Print compact per-season summary if available
    if season_summary is not None:
        print("\nPer-season OOF summary:")
        for idx, row_s in season_summary.reset_index().iterrows():
            print(f"  {row_s['season']}: n={int(row_s['n'])} | acc={float(row_s['acc']):.2%} | brier={float(row_s['brier']):.4f}")
        print("")

    # Optional: write CSV exports for deeper analysis
    if args.export_csv and season_summary is not None and hist_pred_df is not None and calib_df is not None:
        season_summary.to_csv("artifacts/rc_oof_per_season.csv", index=True)
        hist_pred_df.to_csv("artifacts/rc_oof_predictions.csv", index=False)
        calib_df.to_csv("artifacts/rc_calibration_curve.csv", index=False)

    team_names = {
        465: "New Zealand",
        461: "Australia",
        467: "South Africa",
        460: "Argentina",
    }

    # === Historical listing with OOF predictions and score accuracy ===
    try:
        # Cross-validated (OOF) regression predictions for scores (regularized)
        reg_oof_template = make_pipeline(
            SimpleImputer(strategy="median"),
            RobustScaler(),
            Ridge(alpha=1.0),
        )
        oof_home_scores = cast(np.ndarray, cross_val_predict(reg_oof_template, X_hist, y_home, cv=5))
        oof_away_scores = cast(np.ndarray, cross_val_predict(reg_oof_template, X_hist, y_away, cv=5))

        print("\nRugby Championship historical (OOF predictions and score accuracy):")
        # Print compact one-liners for all past games
        for i in range(len(hist)):
            row_h = hist.iloc[i]
            hid = safe_to_int(row_h.get("home_team_id"))
            aid = safe_to_int(row_h.get("away_team_id"))
            # Prefer DB names if available
            home_nm = team_name.get(hid, str(hid))
            away_nm = team_name.get(aid, str(aid))
            # Clip predictions for readability
            ph = float(np.clip(oof_home_scores[i], 0.0, 80.0))
            pa = float(np.clip(oof_away_scores[i], 0.0, 80.0))
            # Simple name placeholders; detailed mapping added below once team_names is defined
            print(f"{row_h['date_event']} | {home_nm} vs {away_nm} | actual {int(row_h['home_score'])}-{int(row_h['away_score'])} | pred {ph:.1f}-{pa:.1f} | pred_winner={'Home' if y_pred_oof[i]==1 else 'Away'} (prob {prob_preds[i]:.1%}) | correct={bool(y_pred_oof[i]==y_hist[i])} | abs_err=({abs(ph-y_home[i]):.1f},{abs(pa-y_away[i]):.1f})")
    except Exception:
        pass

    # === Team-specific aggregates for smarter imputation ===
    home_cols = [c for c in present_cols if c.startswith("home_") or c == "elo_home_pre"]
    away_cols = [c for c in present_cols if c.startswith("away_") or c == "elo_away_pre"]

    # Per-team means for home/away contexts
    home_means_df = hist.groupby("home_team_id")[home_cols].mean(numeric_only=True)
    away_means_df = hist.groupby("away_team_id")[away_cols].mean(numeric_only=True)

    # Carry forward latest Elo ratings from history for upcoming fixtures (apply alias)
    try:
        # Ensure target columns exist
        for _col in ["elo_home_pre", "elo_away_pre"]:
            if _col not in l4986.columns:
                l4986[_col] = np.nan
        # Sort by date to take latest historical Elo values
        hist_sorted = hist.sort_values("date_event") if "date_event" in hist.columns else hist
        # Map ids through alias before grouping
        hist_sorted_alias = hist_sorted.copy()
        if 'home_team_id' in hist_sorted_alias.columns:
            hist_sorted_alias['home_team_id'] = hist_sorted_alias['home_team_id'].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))
        if 'away_team_id' in hist_sorted_alias.columns:
            hist_sorted_alias['away_team_id'] = hist_sorted_alias['away_team_id'].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))
        home_pair_df = cast(pd.DataFrame, pd.DataFrame(hist_sorted_alias.loc[:, ["home_team_id", "elo_home_pre"]]))
        home_pair_df = home_pair_df.loc[home_pair_df["elo_home_pre"].notna(), :]
        latest_home_elo = cast(pd.Series, home_pair_df.groupby("home_team_id")["elo_home_pre"].last())
        away_pair_df = cast(pd.DataFrame, pd.DataFrame(hist_sorted_alias.loc[:, ["away_team_id", "elo_away_pre"]]))
        away_pair_df = away_pair_df.loc[away_pair_df["elo_away_pre"].notna(), :]
        latest_away_elo = cast(pd.Series, away_pair_df.groupby("away_team_id")["elo_away_pre"].last())
        # Convert to plain dicts for unambiguous mapping types
        home_elo_map: dict[int, float] = {safe_to_int(k): safe_to_float(v, default=1500.0) for k, v in latest_home_elo.items()}
        away_elo_map: dict[int, float] = {safe_to_int(k): safe_to_float(v, default=1500.0) for k, v in latest_away_elo.items()}
        mapped_home = l4986["home_team_id"].apply(lambda tid: home_elo_map.get(team_alias.get(safe_to_int(tid, default=-1), safe_to_int(tid, default=-1)), np.nan) if not is_missing(tid) else np.nan)
        mapped_away = l4986["away_team_id"].apply(lambda tid: away_elo_map.get(team_alias.get(safe_to_int(tid, default=-1), safe_to_int(tid, default=-1)), np.nan) if not is_missing(tid) else np.nan)
        l4986["elo_home_pre"] = cast(pd.Series, l4986["elo_home_pre"]).combine_first(cast(pd.Series, mapped_home)).fillna(1500.0)
        l4986["elo_away_pre"] = cast(pd.Series, l4986["elo_away_pre"]).combine_first(cast(pd.Series, mapped_away)).fillna(1500.0)
    except Exception:
        # Fall back silently if any schema mismatch occurs
        pass

    # Cache for neutral head-to-head rate
    pair_rate_cache: dict[tuple[int, int], float] = {}

    def neutral_h2h_rate(home_team_id: int, away_team_id: int) -> float:
        # Apply alias mapping for robust pair lookup
        home_team_id = team_alias.get(home_team_id, home_team_id)
        away_team_id = team_alias.get(away_team_id, away_team_id)
        a, b = sorted([home_team_id, away_team_id])
        key = (a, b)
        if key in pair_rate_cache:
            return pair_rate_cache[key]
        subset = hist[
            ((hist["home_team_id"] == a) & (hist["away_team_id"] == b))
            | ((hist["home_team_id"] == b) & (hist["away_team_id"] == a))
        ]
        if len(subset) == 0:
            pair_rate_cache[key] = 0.5
            return 0.5
        # Count wins for 'home_team_id' regardless of venue (vectorized)
        played_mask = subset[["home_score", "away_score"]].notna().all(axis=1)  # type: ignore[reportUnknownMemberType]
        subset_played = subset.loc[played_mask]
        if len(subset_played) == 0:
            pair_rate_cache[key] = 0.5
            return 0.5
        wins_as_home = (
            (subset_played["home_team_id"] == home_team_id)
            & (subset_played["home_score"] > subset_played["away_score"])
        )
        wins_as_away = (
            (subset_played["away_team_id"] == home_team_id)
            & (subset_played["away_score"] > subset_played["home_score"])
        )
        wins_for_home = int((wins_as_home | wins_as_away).sum())
        total = int(len(subset_played))
        rate = (wins_for_home / total) if total > 0 else 0.5
        pair_rate_cache[key] = rate
        return rate

    # Vectorized upcoming predictions
    if len(l4986) > 0:
        upc = l4986.copy()
        # Alias ids for robust mapping
        upc["home_alias"] = upc["home_team_id"].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))
        upc["away_alias"] = upc["away_team_id"].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))

        # Ensure required columns exist
        for col in all_cols:
            if col not in upc.columns:
                upc[col] = np.nan

        # Compose diffs where missing
        upc["elo_diff"] = upc["elo_diff"].where(upc["elo_diff"].notna(), upc["elo_home_pre"] - upc["elo_away_pre"])
        if "home_form" in upc.columns and "away_form" in upc.columns:
            upc["form_diff"] = upc["form_diff"].where(upc["form_diff"].notna(), upc["home_form"] - upc["away_form"])
        if "home_rest_days" in upc.columns and "away_rest_days" in upc.columns:
            upc["rest_diff"] = upc["rest_diff"].where(upc["rest_diff"].notna(), upc["home_rest_days"] - upc["away_rest_days"])
        if "home_goal_diff_form" in upc.columns and "away_goal_diff_form" in upc.columns:
            upc["goal_diff_form_diff"] = upc["goal_diff_form_diff"].where(upc["goal_diff_form_diff"].notna(), upc["home_goal_diff_form"] - upc["away_goal_diff_form"])
        # Pairwise Elo expectation
        upc["pair_elo_expectation"] = upc["pair_elo_expectation"].where(
            upc["pair_elo_expectation"].notna(),
            1.0 / (1.0 + 10 ** ((upc["elo_away_pre"] - upc["elo_home_pre"]) / 400.0)),
        )
        # Team win rates (map via plain dicts for clearer typing)
        home_wr_dict: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in home_wr_series.items()}
        away_wr_dict: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in away_wr_series.items()}
        upc["home_wr_home"] = upc["home_wr_home"].where(
            upc["home_wr_home"].notna(),
            upc["home_alias"].apply(lambda tid: home_wr_dict.get(int(tid) if not pd.isna(tid) else -1, float("nan")))
        )
        upc["away_wr_away"] = upc["away_wr_away"].where(
            upc["away_wr_away"].notna(),
            upc["away_alias"].apply(lambda tid: away_wr_dict.get(int(tid) if not pd.isna(tid) else -1, float("nan")))
        )
        # H2H neutral rate fallback
        if "h2h_home_rate" not in upc.columns:
            upc["h2h_home_rate"] = np.nan
        mask_h2h_na = upc["h2h_home_rate"].isna()
        if bool(mask_h2h_na.any()):
            rates = [neutral_h2h_rate(int(h), int(a)) for h, a in zip(upc.loc[mask_h2h_na, "home_alias"], upc.loc[mask_h2h_na, "away_alias"])]
            upc.loc[mask_h2h_na, "h2h_home_rate"] = rates
            # If still 0.5, fallback to Elo expectation
            mask_half = upc["h2h_home_rate"].between(0.5 - 1e-12, 0.5 + 1e-12)
            upc.loc[mask_half, "h2h_home_rate"] = 1.0 / (1.0 + 10 ** ((upc.loc[mask_half, "elo_away_pre"] - upc.loc[mask_half, "elo_home_pre"]) / 400.0))

        # Build feature matrix
        X_upc = upc[all_cols].to_numpy()

        # Ensemble probabilities
        prob_lr = cast(np.ndarray, clf.predict_proba(X_upc))[:, 1]
        prob_gbdt = cast(np.ndarray, gbdt_clf.predict_proba(X_upc))[:, 1]
        prob_home_arr = 0.5 * (prob_lr + prob_gbdt)
        prob_away_arr = 1.0 - prob_home_arr

        # Ensemble scores and margin
        pred_home_arr = 0.5 * cast(np.ndarray, reg_home.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_home.predict(X_upc))
        pred_away_arr = 0.5 * cast(np.ndarray, reg_away.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_away.predict(X_upc))
        pred_home_arr = np.clip(pred_home_arr, 0.0, 80.0)
        pred_away_arr = np.clip(pred_away_arr, 0.0, 80.0)
        exp_margin_arr = 0.5 * cast(np.ndarray, reg_margin.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_margin.predict(X_upc))

        # Intervals from per-team residual stds
        home_std_arr = upc["home_alias"].apply(lambda tid: home_std_map.get(int(tid) if not pd.isna(tid) else -1, float(std_home))).to_numpy(dtype=float)
        away_std_arr = upc["away_alias"].apply(lambda tid: away_std_map.get(int(tid) if not pd.isna(tid) else -1, float(std_away))).to_numpy(dtype=float)
        home_low = pred_home_arr - 1.96 * home_std_arr
        home_high = pred_home_arr + 1.96 * home_std_arr
        away_low = pred_away_arr - 1.96 * away_std_arr
        away_high = pred_away_arr + 1.96 * away_std_arr

        # Resolve team names via alias -> DB name -> fallback mapping
        def _resolve_name(tid: int, fallback: str) -> str:
            return team_name.get(tid, team_names.get(tid, fallback))
        home_names = [
            _resolve_name(int(tid), "Home") for tid in upc["home_alias"].to_numpy()
        ]
        away_names = [
            _resolve_name(int(tid), "Away") for tid in upc["away_alias"].to_numpy()
        ]

        # Print results
        for i in range(len(upc)):
            print("-" * 72)
            print(f"Match: {home_names[i]} vs {away_names[i]}")
            print(f"Date:  {upc.iloc[i]['date_event']} | Season: {upc.iloc[i].get('season', '')}")
            print(f"  Home win probability: {float(prob_home_arr[i]):.2%}")
            print(f"  Away win probability: {float(prob_away_arr[i]):.2%}")
            margin_line = f"{'Home' if float(exp_margin_arr[i]) >= 0 else 'Away'} by {abs(float(exp_margin_arr[i])):.1f}"
            scoreline = (
                f"{home_names[i]} {float(pred_home_arr[i]):.1f} "
                f"({float(home_low[i]):.1f}–{float(home_high[i]):.1f})"
                f" - {float(pred_away_arr[i]):.1f} "
                f"({float(away_low[i]):.1f}–{float(away_high[i]):.1f}) {away_names[i]}"
            )
            winner = home_names[i] if float(prob_home_arr[i]) >= 0.5 else away_names[i]
            conf = max(float(prob_home_arr[i]), float(prob_away_arr[i]))
            print(f"  Expected margin: {margin_line}")
            print(f"  Predicted scoreline: {scoreline}")
            print(f"  Decision: {winner} | Confidence {conf:.1%}")
            print(f"  Summary: {winner} to win, {margin_line} (win prob {conf:.1%})")
        print("-" * 72)


if __name__ == "__main__":
    main()
