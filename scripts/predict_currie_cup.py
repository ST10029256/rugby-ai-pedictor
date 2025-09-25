from __future__ import annotations

import sqlite3
import json
import numpy as np
import pandas as pd
from typing import cast, Any
from datetime import datetime, timezone
import argparse
import math
from prediction.features import build_feature_table, FeatureConfig

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import cross_val_predict, cross_val_score
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


def safe_to_float(value: object, default: float = 0.0) -> float:
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
    preds = model.predict(X)
    residuals = y - preds
    return float(np.sqrt(np.mean(residuals**2)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Currie Cup predictions")
    try:
        bool_action = argparse.BooleanOptionalAction  # type: ignore[attr-defined]
    except Exception:
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

    with open("artifacts/per_league_best/registry.json", "r") as f:
        reg = json.load(f)

    conn = sqlite3.connect("data.sqlite")
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=float(args.elo_k), neutral_mode=bool(args.neutral_mode)))

    upcoming = df[df["home_win"].isna()].copy()
    l_league = cast(pd.DataFrame, upcoming[upcoming["league_id"] == 5069].copy())
    # Keep only future/today unless explicitly ignored
    if (not args.ignore_date) and ("date_event" in l_league.columns):
        try:
            today = pd.Timestamp(datetime.now(timezone.utc).date())
            l_league = cast(pd.DataFrame, l_league[l_league["date_event"] >= today])
        except Exception:
            pass

    preview_cols = ["home_team_id", "away_team_id", "elo_home_pre", "elo_away_pre", "h2h_home_rate"]
    try:
        print("\nUpcoming fixtures (selected features):")
        print(l_league.reindex(columns=preview_cols))
    except Exception:
        pass

    hist = cast(pd.DataFrame, df[(df["league_id"] == 5069) & df["home_win"].notna()].copy())

    feature_cols = [
        "elo_diff", "form_diff", "elo_home_pre", "elo_away_pre",
        "home_form", "away_form", "home_rest_days", "away_rest_days",
        "rest_diff", "home_goal_diff_form", "away_goal_diff_form",
        "goal_diff_form_diff", "h2h_home_rate", "season_phase", "is_home"
    ]

    present_cols = [c for c in feature_cols if c in hist.columns]
    if len(hist) == 0 or len(present_cols) == 0:
        print("Insufficient historical data to train models for league 5069.")
        return

    home_wr_series = (
        hist.dropna(subset=["home_win"]).groupby("home_team_id")["home_win"].mean()
    ).astype("float64")
    away_wr_series = (
        hist.dropna(subset=["home_win"]).assign(away_win=lambda df_: (1 - df_["home_win"]).astype(float)).groupby("away_team_id")["away_win"].mean()
    ).astype("float64")

    extra_cols = ["home_wr_home", "away_wr_away", "pair_elo_expectation"]
    hist = hist.copy()
    _home_wr_dict: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in home_wr_series.items()}
    _away_wr_dict: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in away_wr_series.items()}
    hist["home_wr_home"] = hist["home_team_id"].apply(lambda tid: _home_wr_dict.get(safe_to_int(tid, -1), float("nan")))
    hist["away_wr_away"] = hist["away_team_id"].apply(lambda tid: _away_wr_dict.get(safe_to_int(tid, -1), float("nan")))
    hist["pair_elo_expectation"] = 1.0 / (1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0))

    all_cols = present_cols + extra_cols

    team_alias: dict[int, int] = {}
    team_name: dict[int, str] = {}
    try:
        cur = conn.cursor()
        rows_nm = cur.execute(
            """
            SELECT DISTINCT t.id, COALESCE(t.name, '')
            FROM team t
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = 5069
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
        def _col_or_empty(df_: pd.DataFrame, col: str) -> pd.Series:
            return cast(pd.Series, df_[col]) if (isinstance(df_, pd.DataFrame) and (col in df_.columns)) else pd.Series(dtype='float64')
        def _to_id_set(series: pd.Series) -> set[int]:
            result: set[int] = set()
            if not isinstance(series, pd.Series):
                return result
            for val in series.tolist():
                if val is None:
                    continue
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
        upc_ids: set[int] = _to_id_set(_col_or_empty(l_league, 'home_team_id')) | _to_id_set(_col_or_empty(l_league, 'away_team_id'))
        for tid in upc_ids:
            if tid in hist_ids:
                team_alias[tid] = tid
                continue
            key = id_to_norm.get(tid)
            if key:
                candidates = [cid for cid in norm_to_ids.get(key, []) if cid in hist_ids]
                team_alias[tid] = candidates[0] if candidates else tid
            else:
                team_alias[tid] = tid
    except Exception:
        team_alias = {}

    X_hist = hist[all_cols].to_numpy()
    y_hist = hist["home_win"].astype(int).to_numpy()
    y_home = hist["home_score"].to_numpy()
    y_away = hist["away_score"].to_numpy()

    base_lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    if args.calibration != "none":
        calibrated = CalibratedClassifierCV(base_lr, method=str(args.calibration), cv=5)
        clf = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), calibrated)
    else:
        clf = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), base_lr)
    clf.fit(X_hist, y_hist)

    try:
        if "date_event" in hist.columns:
            max_dt = pd.to_datetime(hist["date_event"]).max()
            days = (pd.to_datetime(hist["date_event"]) - max_dt).dt.days.abs().astype(float)
            weights = np.exp(-days / 365.0).astype(float)
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

    reg_home = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=1.0))
    reg_away = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=1.0))
    reg_home.fit(X_hist, y_home_w, ridge__sample_weight=weights)
    reg_away.fit(X_hist, y_away_w, ridge__sample_weight=weights)

    # Summary metrics (use ensemble of calibrated LR and GBDT for OOF)
    prob_lr_oof = cast(np.ndarray, cross_val_predict(clf, X_hist, y_hist, cv=5, method="predict_proba"))[:, 1]
    prob_gbdt_oof = cast(np.ndarray, cross_val_predict(HistGradientBoostingClassifier(random_state=42), X_hist, y_hist, cv=5, method="predict_proba"))[:, 1]
    prob_preds = 0.5 * (prob_lr_oof + prob_gbdt_oof)
    y_pred_oof = (prob_preds >= 0.5).astype(int)
    cv_acc = float(np.mean(y_pred_oof == y_hist))
    brier = brier_score_loss(y_hist, prob_preds)
    ll = log_loss(y_hist, prob_preds)

    print("\n=== Currie Cup Predictions (Neutral Mode) ===")
    print(f"League: 5069 | Fixtures: {len(l_league)}")
    print(f"Cross-validated accuracy: {cv_acc:.2%}")
    print(f"Brier score: {brier:.4f}")
    print(f"Log-loss: {ll:.4f}")

    # Historical (OOF) listing for analysis
    try:
        reg_oof = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), Ridge(alpha=1.0))
        oof_home = cast(np.ndarray, cross_val_predict(reg_oof, X_hist, y_home, cv=5))
        oof_away = cast(np.ndarray, cross_val_predict(reg_oof, X_hist, y_away, cv=5))
        print("\nCurrie Cup historical (OOF predictions and score accuracy):")
        for i in range(len(hist)):
            row_h = hist.iloc[i]
            hid = safe_to_int(row_h.get("home_team_id"))
            aid = safe_to_int(row_h.get("away_team_id"))
            home_nm = team_name.get(hid, str(hid))
            away_nm = team_name.get(aid, str(aid))
            ph = float(np.clip(oof_home[i], 0.0, 80.0))
            pa = float(np.clip(oof_away[i], 0.0, 80.0))
            print(f"{row_h['date_event']} | {home_nm} vs {away_nm} | actual {int(row_h['home_score'])}-{int(row_h['away_score'])} | pred {ph:.1f}-{pa:.1f} | pred_winner={'Home' if y_pred_oof[i]==1 else 'Away'} (prob {prob_preds[i]:.1%}) | correct={bool(y_pred_oof[i]==y_hist[i])} | abs_err=({abs(ph-y_home[i]):.1f},{abs(pa-y_away[i]):.1f})")
    except Exception:
        pass

    gbdt_clf = HistGradientBoostingClassifier(random_state=42)
    gbdt_home = HistGradientBoostingRegressor(random_state=42)
    gbdt_away = HistGradientBoostingRegressor(random_state=42)
    gbdt_clf.fit(X_hist, y_hist, sample_weight=weights)
    gbdt_home.fit(X_hist, y_home_w, sample_weight=weights)
    gbdt_away.fit(X_hist, y_away_w, sample_weight=weights)

    std_home = compute_residual_std(reg_home, X_hist, y_home)
    std_away = compute_residual_std(reg_away, X_hist, y_away)
    _pred_home_hist = cast(np.ndarray, reg_home.predict(X_hist))
    _pred_away_hist = cast(np.ndarray, reg_away.predict(X_hist))
    _res_home_hist = y_home - _pred_home_hist
    _res_away_hist = y_away - _pred_away_hist
    _home_std_by_team = (
        pd.DataFrame({"team": hist["home_team_id"].to_numpy(), "res": _res_home_hist})
        .groupby("team")["res"].apply(lambda r: float(np.sqrt(np.mean(np.square(r)))))
    )
    _away_std_by_team = (
        pd.DataFrame({"team": hist["away_team_id"].to_numpy(), "res": _res_away_hist})
        .groupby("team")["res"].apply(lambda r: float(np.sqrt(np.mean(np.square(r)))))
    )
    home_std_map: dict[int, float] = {}
    away_std_map: dict[int, float] = {}
    for k, v in _home_std_by_team.items():
        val = safe_to_float(cast(Any, v), default=float("nan"))
        if not math.isnan(val):
            home_std_map[safe_to_int(cast(Any, k), -1)] = val
    for k, v in _away_std_by_team.items():
        val = safe_to_float(cast(Any, v), default=float("nan"))
        if not math.isnan(val):
            away_std_map[safe_to_int(cast(Any, k), -1)] = val

    # Carry forward Elo for upcoming with alias
    try:
        for _col in ["elo_home_pre", "elo_away_pre"]:
            if _col not in l_league.columns:
                l_league[_col] = np.nan
        hist_sorted = hist.sort_values("date_event") if "date_event" in hist.columns else hist
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
        home_elo_map: dict[int, float] = {safe_to_int(k): safe_to_float(v, default=1500.0) for k, v in latest_home_elo.items()}
        away_elo_map: dict[int, float] = {safe_to_int(k): safe_to_float(v, default=1500.0) for k, v in latest_away_elo.items()}
        mapped_home = l_league["home_team_id"].apply(lambda tid: home_elo_map.get(team_alias.get(safe_to_int(tid, default=-1), safe_to_int(tid, default=-1)), np.nan) if not is_missing(tid) else np.nan)
        mapped_away = l_league["away_team_id"].apply(lambda tid: away_elo_map.get(team_alias.get(safe_to_int(tid, default=-1), safe_to_int(tid, default=-1)), np.nan) if not is_missing(tid) else np.nan)
        l_league["elo_home_pre"] = cast(pd.Series, l_league["elo_home_pre"]).combine_first(cast(pd.Series, mapped_home)).fillna(1500.0)
        l_league["elo_away_pre"] = cast(pd.Series, l_league["elo_away_pre"]).combine_first(cast(pd.Series, mapped_away)).fillna(1500.0)
    except Exception:
        pass

    # Vectorized upcoming predictions
    if len(l_league) > 0:
        upc = l_league.copy()
        upc["home_alias"] = upc["home_team_id"].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))
        upc["away_alias"] = upc["away_team_id"].apply(lambda x: team_alias.get(safe_to_int(x, -1), safe_to_int(x, -1)))
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
        _home_wr_map: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in home_wr_series.items()}
        _away_wr_map: dict[int, float] = {safe_to_int(cast(Any, k)): safe_to_float(cast(Any, v), default=float("nan")) for k, v in away_wr_series.items()}
        upc["home_wr_home"] = upc["home_wr_home"].where(upc["home_wr_home"].notna(), upc["home_alias"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan"))))
        upc["away_wr_away"] = upc["away_wr_away"].where(upc["away_wr_away"].notna(), upc["away_alias"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan"))))

        X_upc = upc[all_cols].to_numpy()
        prob_lr = cast(np.ndarray, clf.predict_proba(X_upc))[:, 1]
        prob_gbdt = cast(np.ndarray, gbdt_clf.predict_proba(X_upc))[:, 1]
        prob_home_arr = 0.5 * (prob_lr + prob_gbdt)
        prob_away_arr = 1.0 - prob_home_arr
        pred_home_arr = 0.5 * cast(np.ndarray, reg_home.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_home.predict(X_upc))
        pred_away_arr = 0.5 * cast(np.ndarray, reg_away.predict(X_upc)) + 0.5 * cast(np.ndarray, gbdt_away.predict(X_upc))
        pred_home_arr = np.clip(pred_home_arr, 0.0, 80.0)
        pred_away_arr = np.clip(pred_away_arr, 0.0, 80.0)
        home_std_arr = upc["home_alias"].apply(lambda tid: home_std_map.get(safe_to_int(tid, -1), float(std_home))).to_numpy(dtype=float)
        away_std_arr = upc["away_alias"].apply(lambda tid: away_std_map.get(safe_to_int(tid, -1), float(std_away))).to_numpy(dtype=float)
        home_low = pred_home_arr - 1.96 * home_std_arr
        home_high = pred_home_arr + 1.96 * home_std_arr
        away_low = pred_away_arr - 1.96 * away_std_arr
        away_high = pred_away_arr + 1.96 * away_std_arr

        def _resolve_name(tid: int, fallback: str) -> str:
            return team_name.get(tid, fallback)
        home_names = [_resolve_name(int(t), "Home") for t in upc["home_alias"].to_numpy()]
        away_names = [_resolve_name(int(t), "Away") for t in upc["away_alias"].to_numpy()]

        for i in range(len(upc)):
            print("-" * 72)
            print(f"Match: {home_names[i]} vs {away_names[i]}")
            print(f"Date:  {upc.iloc[i]['date_event']} | Season: {upc.iloc[i].get('season', '')}")
            print(f"  Home win probability: {float(prob_home_arr[i]):.2%}")
            print(f"  Away win probability: {float(prob_away_arr[i]):.2%}")
            margin = float(pred_home_arr[i] - pred_away_arr[i])
            margin_line = f"{'Home' if margin >= 0 else 'Away'} by {abs(margin):.1f}"
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
