#!/usr/bin/env python3
"""
Export pre-kickoff replay predictions to Excel (read-only — no DB writes).

For each completed match, runs the champion V4/V5 runtime as if the game has not
happened yet: team histories only include results strictly BEFORE match date
(same logic as backfill / live AI scores, without bookmaker odds).

Output: one workbook with a Summary sheet plus one sheet per league.

Usage (minimal deps — no scikit-learn 1.3.2 / no requirements.txt on Py 3.13):

  PowerShell:
    ./scripts/install-export-deps.ps1

  Or manually (must force sklearn WHEEL, not source build):
    pip install --only-binary scikit-learn "scikit-learn>=1.5.0"
    pip install pandas openpyxl "numpy<2" joblib requests torch

  Then:
    python scripts/export_pre_kickoff_replay_excel.py --db data.sqlite --output replay_predictions.xlsx

  DO NOT run: pip install -r requirements.txt  (sklearn==1.3.2 fails to compile on Python 3.13)

  # Quick test (one league, 20 games):
  python scripts/export_pre_kickoff_replay_excel.py --league-id 4446 --max-matches 20 --output test.xlsx
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PKG = PROJECT_ROOT / "rugby-ai-predictor"
sys.path.insert(0, str(RUGBY_PKG))

from prediction.db import connect  # noqa: E402
from prediction.sportdevs_client import SportDevsClient  # noqa: E402

# All target leagues (9). Same set as prediction/config.py + champion policy.
DEFAULT_LEAGUE_IDS = [4414, 4430, 4446, 4551, 4574, 4714, 4986, 5069, 5479]

LEAGUE_NAMES: Dict[int, str] = {
    4414: "English Premiership",
    4430: "French Top 14",
    4446: "URC",
    4551: "Super Rugby",
    4574: "Rugby World Cup",
    4714: "Six Nations",
    4986: "Rugby Championship",
    5069: "Currie Cup",
    5479: "Int Friendlies",
}


def _load_champion_map(path: Path) -> Dict[int, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("model_family_by_league") or {}
    return {int(k): str(v).strip().lower() for k, v in raw.items()}


def _load_local_runtime_assets(league_id: int, family: str, artifacts_dir: Path) -> Optional[Dict[str, Any]]:
    family = family.strip().lower()
    if family not in {"v4", "v5"}:
        return None
    meta = artifacts_dir / f"league_{league_id}_model_maz_maxed_{family}_meta.pkl"
    seeds = sorted(artifacts_dir.glob(f"league_{league_id}_model_maz_maxed_{family}_seed_*.pt"))
    if meta.is_file() and seeds:
        return {
            "league_id": league_id,
            "meta_path": str(meta),
            "seed_model_paths": [str(s) for s in seeds],
            "model_family": family,
        }
    return None


def _build_predictor(
    league_id: int,
    family: str,
    db_path: str,
    artifacts_dir: Path,
):
    assets = _load_local_runtime_assets(league_id, family, artifacts_dir)
    if assets is None:
        raise FileNotFoundError(
            f"No local {family.upper()} artifacts for league {league_id} under {artifacts_dir}"
        )
    if family == "v5":
        from prediction.v5_runtime import V5RuntimePredictor

        return V5RuntimePredictor(v5_assets=assets, db_path=db_path, sportdevs_api_key="")
    from prediction.v4_runtime import V4RuntimePredictor

    return V4RuntimePredictor(v4_assets=assets, db_path=db_path, sportdevs_api_key="")


def _disable_odds_on_predictor(predictor: Any) -> None:
    """AI-only replay: no live bookmaker lookups."""

    class _OfflineOddsClient:
        def get_match_odds(self, *args: Any, **kwargs: Any) -> dict:
            return {"data": []}

    predictor.sportdevs_client = _OfflineOddsClient()

    def _no_odds(_self: Any, _match_id: int) -> dict:
        return {
            "home_win_prob": 0.5,
            "away_win_prob": 0.5,
            "draw_prob": 0.0,
            "confidence": 0.5,
            "bookmaker_count": 0,
        }

    try:
        predictor.get_bookmaker_prediction = types.MethodType(_no_odds, predictor)
    except Exception:
        pass


def _actual_winner(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "Home"
    if away_score > home_score:
        return "Away"
    return "Draw"


def _winner_label(code: Optional[str], home_team: str, away_team: str) -> str:
    if code == "Home":
        return home_team
    if code == "Away":
        return away_team
    if code == "Draw":
        return "Draw"
    return ""


def _safe_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", "", name).strip() or "Sheet"
    return cleaned[:31]


def _fetch_completed_matches(
    conn: sqlite3.Connection,
    league_id: int,
    since: Optional[str],
    until: Optional[str],
    max_matches: int,
) -> List[Tuple[Any, ...]]:
    sql = """
        SELECT
            e.id,
            e.date_event,
            t1.name AS home_team,
            t2.name AS away_team,
            e.home_score,
            e.away_score
        FROM event e
        LEFT JOIN team t1 ON t1.id = e.home_team_id
        LEFT JOIN team t2 ON t2.id = e.away_team_id
        WHERE e.league_id = ?
          AND e.home_score IS NOT NULL
          AND e.away_score IS NOT NULL
          AND e.date_event IS NOT NULL
          AND date(e.date_event) <= date('now')
    """
    params: List[Any] = [league_id]
    if since:
        sql += " AND date(e.date_event) >= date(?)"
        params.append(since)
    if until:
        sql += " AND date(e.date_event) <= date(?)"
        params.append(until)
    sql += " ORDER BY e.date_event ASC, e.id ASC"
    if max_matches > 0:
        sql += " LIMIT ?"
        params.append(max_matches)
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def _summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in rows if r.get("prediction_ok")]
    failed = len(rows) - len(ok)
    if not ok:
        return {
            "matches": len(rows),
            "predicted": 0,
            "failed": failed,
            "winner_correct": 0,
            "winner_accuracy_pct": None,
            "avg_score_error": None,
            "avg_home_error": None,
            "avg_away_error": None,
            "avg_margin_error": None,
            "avg_predicted_margin": None,
            "avg_actual_margin": None,
        }

    correct = sum(1 for r in ok if r.get("winner_correct") is True)
    return {
        "matches": len(rows),
        "predicted": len(ok),
        "failed": failed,
        "winner_correct": correct,
        "winner_accuracy_pct": round(100.0 * correct / len(ok), 2),
        "avg_score_error": round(sum(r["score_error"] for r in ok) / len(ok), 2),
        "avg_home_error": round(sum(r["home_error"] for r in ok) / len(ok), 2),
        "avg_away_error": round(sum(r["away_error"] for r in ok) / len(ok), 2),
        "avg_margin_error": round(sum(r["margin_error"] for r in ok) / len(ok), 2),
        "avg_predicted_margin": round(sum(r["predicted_margin"] for r in ok) / len(ok), 2),
        "avg_actual_margin": round(sum(r["actual_margin"] for r in ok) / len(ok), 2),
    }


def _replay_league(
    conn: sqlite3.Connection,
    league_id: int,
    predictor: Any,
    since: Optional[str],
    until: Optional[str],
    max_matches: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows_out: List[Dict[str, Any]] = []
    matches = _fetch_completed_matches(conn, league_id, since, until, max_matches)

    for match_id, date_event, home_team, away_team, home_score, away_score in matches:
        base = {
            "match_id": match_id,
            "date": str(date_event)[:10],
            "home_team": home_team,
            "away_team": away_team,
            "actual_home": int(home_score),
            "actual_away": int(away_score),
            "actual_winner": _winner_label(_actual_winner(int(home_score), int(away_score)), home_team, away_team),
            "actual_margin": int(home_score) - int(away_score),
        }
        if not home_team or not away_team:
            rows_out.append({**base, "prediction_ok": False, "error": "missing team names"})
            continue
        try:
            pred = predictor.predict_match(
                home_team=str(home_team),
                away_team=str(away_team),
                league_id=int(league_id),
                match_date=str(date_event),
                match_id=None,
            )
            ph = float(pred.get("predicted_home_score"))
            pa = float(pred.get("predicted_away_score"))
            pw = str(pred.get("predicted_winner") or "")
            aw = _actual_winner(int(home_score), int(away_score))
            winner_correct = pw in {"Home", "Away", "Draw"} and pw == aw
            rows_out.append(
                {
                    **base,
                    "prediction_ok": True,
                    "pred_home": round(ph, 1),
                    "pred_away": round(pa, 1),
                    "pred_winner": _winner_label(pw, home_team, away_team),
                    "pred_winner_code": pw,
                    "confidence_pct": round(float(pred.get("confidence") or 0) * 100, 1),
                    "winner_correct": winner_correct,
                    "home_error": abs(ph - float(home_score)),
                    "away_error": abs(pa - float(away_score)),
                    "score_error": abs(ph - float(home_score)) + abs(pa - float(away_score)),
                    "predicted_margin": round(ph - pa, 1),
                    "margin_error": abs((ph - pa) - (float(home_score) - float(away_score))),
                    "model_family": str(pred.get("model_family") or pred.get("model_type") or ""),
                    "error": "",
                }
            )
        except Exception as exc:
            rows_out.append({**base, "prediction_ok": False, "error": str(exc)})

    return rows_out, _summarize_rows(rows_out)


def _summary_row(label: str, summary: Dict[str, Any], league_id: int, league_name: str) -> Dict[str, Any]:
    return {
        "league_id": league_id,
        "league": league_name,
        "metric": label,
        "matches": summary["matches"],
        "predicted": summary["predicted"],
        "failed": summary["failed"],
        "winner_correct": summary["winner_correct"],
        "winner_accuracy_pct": summary["winner_accuracy_pct"],
        "avg_score_error": summary["avg_score_error"],
        "avg_home_error": summary["avg_home_error"],
        "avg_away_error": summary["avg_away_error"],
        "avg_margin_error": summary["avg_margin_error"],
        "avg_predicted_margin": summary["avg_predicted_margin"],
        "avg_actual_margin": summary["avg_actual_margin"],
    }


def _write_league_sheet(writer: pd.ExcelWriter, sheet: str, summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    summary_lines = [
        {"section": "SUMMARY", "field": "matches", "value": summary["matches"]},
        {"section": "SUMMARY", "field": "predicted", "value": summary["predicted"]},
        {"section": "SUMMARY", "field": "failed", "value": summary["failed"]},
        {"section": "SUMMARY", "field": "winner_correct", "value": summary["winner_correct"]},
        {"section": "SUMMARY", "field": "winner_accuracy_pct", "value": summary["winner_accuracy_pct"]},
        {"section": "SUMMARY", "field": "avg_score_error", "value": summary["avg_score_error"]},
        {"section": "SUMMARY", "field": "avg_home_error", "value": summary["avg_home_error"]},
        {"section": "SUMMARY", "field": "avg_away_error", "value": summary["avg_away_error"]},
        {"section": "SUMMARY", "field": "avg_margin_error", "value": summary["avg_margin_error"]},
        {"section": "SUMMARY", "field": "avg_predicted_margin", "value": summary["avg_predicted_margin"]},
        {"section": "SUMMARY", "field": "avg_actual_margin", "value": summary["avg_actual_margin"]},
        {"section": "", "field": "", "value": ""},
    ]
    summary_df = pd.DataFrame(summary_lines)

    detail_cols = [
        "date",
        "home_team",
        "away_team",
        "actual_home",
        "actual_away",
        "actual_winner",
        "actual_margin",
        "pred_home",
        "pred_away",
        "pred_winner",
        "confidence_pct",
        "winner_correct",
        "home_error",
        "away_error",
        "score_error",
        "predicted_margin",
        "margin_error",
        "prediction_ok",
        "error",
    ]
    detail_df = pd.DataFrame(rows)
    for col in detail_cols:
        if col not in detail_df.columns:
            detail_df[col] = None
    detail_df = detail_df[detail_cols]

    start_row = 0
    summary_df.to_excel(writer, sheet_name=sheet, index=False, startrow=start_row)
    start_row += len(summary_df) + 2
    detail_df.to_excel(writer, sheet_name=sheet, index=False, startrow=start_row)


def _preflight_dependencies() -> None:
    missing: List[str] = []
    for mod, pip_name in (
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
        ("numpy", "numpy"),
        ("sklearn", "scikit-learn>=1.5.0"),
        ("torch", "torch"),
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        raise SystemExit(
            "Missing packages: "
            + ", ".join(missing)
            + "\nInstall with: pip install -r scripts/requirements-export.txt"
            + "\n(On Python 3.13 do NOT use requirements.txt — sklearn 1.3.2 will not build.)"
        )


def main() -> None:
    _preflight_dependencies()
    parser = argparse.ArgumentParser(description="Export pre-kickoff replay predictions to Excel (no DB writes).")
    parser.add_argument("--db", default="data.sqlite", help="Path to SQLite DB")
    parser.add_argument("--output", default="pre_kickoff_replay_export.xlsx", help="Output .xlsx path")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Local model artifacts directory")
    parser.add_argument(
        "--champions-file",
        default=str(RUGBY_PKG / "league_model_champions.json"),
        help="Champion model family map",
    )
    parser.add_argument("--league-id", type=int, action="append", default=None, help="Restrict to league id(s)")
    parser.add_argument("--since", default=None, help="Only matches on/after YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="Only matches on/before YYYY-MM-DD")
    parser.add_argument("--max-matches", type=int, default=0, help="Cap matches per league (0 = all)")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(f"Artifacts directory not found: {artifacts_dir}")

    champion_map = _load_champion_map(Path(args.champions_file))
    league_ids = args.league_id or DEFAULT_LEAGUE_IDS

    os.environ.setdefault("LIVE_MODEL_FAMILY", "champion")

    conn = connect(db_path)
    summary_rows: List[Dict[str, Any]] = []
    league_exports: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]]]] = []
    started = datetime.now(timezone.utc)

    try:
        for league_id in league_ids:
            league_name = LEAGUE_NAMES.get(league_id, f"League {league_id}")
            family = champion_map.get(league_id, "v5")
            print(f"[{league_id}] {league_name} — loading {family.upper()} model...")
            predictor = _build_predictor(league_id, family, db_path, artifacts_dir)
            _disable_odds_on_predictor(predictor)

            print(f"[{league_id}] Replaying completed matches...")
            rows, summary = _replay_league(
                conn,
                league_id,
                predictor,
                since=args.since,
                until=args.until,
                max_matches=args.max_matches,
            )
            league_exports.append((_safe_sheet_name(league_name), summary, rows))
            summary_rows.append(_summary_row("league_total", summary, league_id, league_name))
            acc = summary["winner_accuracy_pct"]
            acc_txt = f"{acc}%" if acc is not None else "N/A"
            print(
                f"[{league_id}] Done: {summary['predicted']}/{summary['matches']} predicted, "
                f"accuracy={acc_txt}, avg score error={summary['avg_score_error']}"
            )

        if not league_exports:
            raise SystemExit("No league results to export.")

        with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
            for sheet, summary, rows in league_exports:
                _write_league_sheet(writer, sheet, summary, rows)
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
    finally:
        conn.close()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"\nWrote {args.output} in {elapsed:.1f}s")
    print("Note: replay uses today's DB + today's model weights — not a frozen pre-kickoff moment.")


if __name__ == "__main__":
    main()
