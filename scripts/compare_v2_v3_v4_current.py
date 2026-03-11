#!/usr/bin/env python3
"""
Deep comparison of CURRENT vs V2 vs V3 vs V4 rugby model reports.

Designed for "max detail" diagnostics:
- Per-league metric matrix
- Deltas versus CURRENT for each model
- Weighted global averages
- "Best model by metric" counts
- Schema/mismatch diagnostics
- Optional CSV export of every parsed field
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PerfMetrics:
    winner_accuracy: Optional[float] = None
    outcome_accuracy: Optional[float] = None
    home_mae: Optional[float] = None
    away_mae: Optional[float] = None
    overall_mae: Optional[float] = None
    brier_winner: Optional[float] = None
    ece_winner: Optional[float] = None
    rows: Optional[int] = None


@dataclass
class ModelView:
    metrics: PerfMetrics
    calibration_method: Optional[str] = None
    alpha_avg_test: Optional[float] = None
    variance_avg_test: Optional[float] = None
    low_confidence_rate: Optional[float] = None
    high_confidence_win_accuracy: Optional[float] = None
    mode: Optional[str] = None
    train_rows: Optional[int] = None
    test_rows: Optional[int] = None
    raw_payload: Optional[Dict[str, Any]] = None


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _fmt(v: Optional[float], width: int = 7, prec: int = 3) -> str:
    if v is None:
        return " " * max(0, width - 2) + "NA"
    return f"{v:{width}.{prec}f}"


def _fmt_signed(v: Optional[float], width: int = 8, prec: int = 3) -> str:
    if v is None:
        return " " * max(0, width - 2) + "NA"
    return f"{v:+{width}.{prec}f}"


def _read_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Report not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_perf_metrics(d: Dict[str, Any]) -> PerfMetrics:
    return PerfMetrics(
        winner_accuracy=_to_float(d.get("winner_accuracy")),
        outcome_accuracy=_to_float(d.get("outcome_accuracy")),
        home_mae=_to_float(d.get("home_mae")),
        away_mae=_to_float(d.get("away_mae")),
        overall_mae=_to_float(d.get("overall_mae")),
        brier_winner=_to_float(d.get("brier_winner")),
        ece_winner=_to_float(d.get("ece_winner")),
        rows=_to_int(d.get("rows")),
    )


def _extract_v2(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid_s, payload in data.get("leagues", {}).items():
        if payload.get("status") != "tested":
            continue
        lid = int(lid_s)
        out[lid] = {
            "name": str(payload.get("name", f"League {lid}")),
            "current": ModelView(
                metrics=_extract_perf_metrics(payload.get("current", {})),
                mode=str(payload.get("mode")) if payload.get("mode") is not None else None,
                train_rows=_to_int(payload.get("train_rows")),
                test_rows=_to_int(payload.get("test_rows")),
                raw_payload=payload,
            ),
            "v2": ModelView(
                metrics=_extract_perf_metrics(payload.get("maz_maxed_v2", {})),
                mode=str(payload.get("mode")) if payload.get("mode") is not None else None,
                train_rows=_to_int(payload.get("train_rows")),
                test_rows=_to_int(payload.get("test_rows")),
                raw_payload=payload,
            ),
        }
    return out


def _extract_v3(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid_s, payload in data.get("leagues", {}).items():
        if payload.get("status") != "tested":
            continue
        lid = int(lid_s)
        out[lid] = {
            "name": str(payload.get("name", f"League {lid}")),
            "current": ModelView(
                metrics=_extract_perf_metrics(payload.get("current", {})),
                mode=str(payload.get("mode")) if payload.get("mode") is not None else None,
                train_rows=_to_int(payload.get("train_rows")),
                test_rows=_to_int(payload.get("test_rows")),
                raw_payload=payload,
            ),
            "v3": ModelView(
                metrics=_extract_perf_metrics(payload.get("maz_maxed_v3", {})),
                calibration_method=str(payload.get("calibration_method")) if payload.get("calibration_method") is not None else None,
                mode=str(payload.get("mode")) if payload.get("mode") is not None else None,
                train_rows=_to_int(payload.get("train_rows")),
                test_rows=_to_int(payload.get("test_rows")),
                raw_payload=payload,
            ),
        }
    return out


def _extract_v4(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid_s, payload in data.get("leagues", {}).items():
        if payload.get("status") != "tested":
            continue
        lid = int(lid_s)
        out[lid] = {
            "name": str(payload.get("name", f"League {lid}")),
            "v4": ModelView(
                metrics=_extract_perf_metrics(payload.get("metrics", {})),
                calibration_method=str(payload.get("calibration_method")) if payload.get("calibration_method") is not None else None,
                alpha_avg_test=_to_float(payload.get("alpha_avg_test")),
                variance_avg_test=_to_float(payload.get("variance_avg_test")),
                low_confidence_rate=_to_float(payload.get("low_confidence_rate")),
                high_confidence_win_accuracy=_to_float(payload.get("high_confidence_win_accuracy")),
                mode=str(payload.get("mode")) if payload.get("mode") is not None else None,
                train_rows=_to_int(payload.get("train_rows")),
                test_rows=_to_int(payload.get("test_rows")),
                raw_payload=payload,
            ),
        }
    return out


def _safe_delta(higher_is_better: bool, base: Optional[float], model: Optional[float]) -> Optional[float]:
    if base is None or model is None:
        return None
    return (model - base) if higher_is_better else (base - model)


def _weighted_avg(values: List[Tuple[Optional[float], Optional[int]]]) -> Optional[float]:
    num = 0.0
    den = 0
    for v, w in values:
        if v is None:
            continue
        ww = int(w) if w is not None else 1
        num += float(v) * ww
        den += ww
    if den <= 0:
        return None
    return num / den


def _merge_name(lid: int, d2: Dict[int, Dict[str, Any]], d3: Dict[int, Dict[str, Any]], d4: Dict[int, Dict[str, Any]]) -> str:
    return (
        d4.get(lid, {}).get("name")
        or d3.get(lid, {}).get("name")
        or d2.get(lid, {}).get("name")
        or f"League {lid}"
    )


def _pick_current(
    lid: int,
    current_source: str,
    d2: Dict[int, Dict[str, Any]],
    d3: Dict[int, Dict[str, Any]],
) -> Optional[ModelView]:
    if current_source == "v3":
        return d3.get(lid, {}).get("current")
    if current_source == "v2":
        return d2.get(lid, {}).get("current")
    # auto
    return d3.get(lid, {}).get("current") or d2.get(lid, {}).get("current")


def _print_core_matrix(rows: List[Dict[str, Any]]) -> None:
    print("\n=== CORE METRICS (per league) ===")
    print(
        "league_id | league_name                       | curr_win | v2_win | v3_win | v4_win | "
        "curr_out | v2_out | v3_out | v4_out | curr_mae | v2_mae | v3_mae | v4_mae"
    )
    print("-" * 178)
    for r in rows:
        c = r["current"].metrics if r["current"] else PerfMetrics()
        v2 = r["v2"].metrics if r["v2"] else PerfMetrics()
        v3 = r["v3"].metrics if r["v3"] else PerfMetrics()
        v4 = r["v4"].metrics if r["v4"] else PerfMetrics()
        print(
            f"{r['lid']:7d} | {r['name'][:32]:32s} | "
            f"{_fmt(c.winner_accuracy)} | {_fmt(v2.winner_accuracy)} | {_fmt(v3.winner_accuracy)} | {_fmt(v4.winner_accuracy)} | "
            f"{_fmt(c.outcome_accuracy)} | {_fmt(v2.outcome_accuracy)} | {_fmt(v3.outcome_accuracy)} | {_fmt(v4.outcome_accuracy)} | "
            f"{_fmt(c.overall_mae)} | {_fmt(v2.overall_mae)} | {_fmt(v3.overall_mae)} | {_fmt(v4.overall_mae)}"
        )


def _print_reliability_matrix(rows: List[Dict[str, Any]]) -> None:
    print("\n=== RELIABILITY / UNCERTAINTY (per league) ===")
    print(
        "league_id | league_name                       | curr_brier | v2_brier | v3_brier | v4_brier | "
        "curr_ece | v2_ece | v3_ece | v4_ece | v4_alpha | v4_var | v4_low_conf | v4_high_conf_win"
    )
    print("-" * 196)
    for r in rows:
        c = r["current"].metrics if r["current"] else PerfMetrics()
        v2 = r["v2"].metrics if r["v2"] else PerfMetrics()
        v3 = r["v3"].metrics if r["v3"] else PerfMetrics()
        v4m = r["v4"]
        v4 = v4m.metrics if v4m else PerfMetrics()
        print(
            f"{r['lid']:7d} | {r['name'][:32]:32s} | "
            f"{_fmt(c.brier_winner)} | {_fmt(v2.brier_winner)} | {_fmt(v3.brier_winner)} | {_fmt(v4.brier_winner)} | "
            f"{_fmt(c.ece_winner)} | {_fmt(v2.ece_winner)} | {_fmt(v3.ece_winner)} | {_fmt(v4.ece_winner)} | "
            f"{_fmt(v4m.alpha_avg_test if v4m else None)} | {_fmt(v4m.variance_avg_test if v4m else None)} | "
            f"{_fmt(v4m.low_confidence_rate if v4m else None)} | {_fmt(v4m.high_confidence_win_accuracy if v4m else None)}"
        )


def _print_delta_matrix(rows: List[Dict[str, Any]]) -> None:
    print("\n=== DELTAS vs CURRENT (positive is better) ===")
    print(
        "league_id | league_name                       | "
        "v2_win_d | v3_win_d | v4_win_d | "
        "v2_out_d | v3_out_d | v4_out_d | "
        "v2_mae_d | v3_mae_d | v4_mae_d | "
        "v2_brier_d | v3_brier_d | v4_brier_d | "
        "v2_ece_d | v3_ece_d | v4_ece_d"
    )
    print("-" * 236)
    for r in rows:
        c = r["current"].metrics if r["current"] else PerfMetrics()
        v2 = r["v2"].metrics if r["v2"] else PerfMetrics()
        v3 = r["v3"].metrics if r["v3"] else PerfMetrics()
        v4 = r["v4"].metrics if r["v4"] else PerfMetrics()
        print(
            f"{r['lid']:7d} | {r['name'][:32]:32s} | "
            f"{_fmt_signed(_safe_delta(True, c.winner_accuracy, v2.winner_accuracy))} | "
            f"{_fmt_signed(_safe_delta(True, c.winner_accuracy, v3.winner_accuracy))} | "
            f"{_fmt_signed(_safe_delta(True, c.winner_accuracy, v4.winner_accuracy))} | "
            f"{_fmt_signed(_safe_delta(True, c.outcome_accuracy, v2.outcome_accuracy))} | "
            f"{_fmt_signed(_safe_delta(True, c.outcome_accuracy, v3.outcome_accuracy))} | "
            f"{_fmt_signed(_safe_delta(True, c.outcome_accuracy, v4.outcome_accuracy))} | "
            f"{_fmt_signed(_safe_delta(False, c.overall_mae, v2.overall_mae))} | "
            f"{_fmt_signed(_safe_delta(False, c.overall_mae, v3.overall_mae))} | "
            f"{_fmt_signed(_safe_delta(False, c.overall_mae, v4.overall_mae))} | "
            f"{_fmt_signed(_safe_delta(False, c.brier_winner, v2.brier_winner))} | "
            f"{_fmt_signed(_safe_delta(False, c.brier_winner, v3.brier_winner))} | "
            f"{_fmt_signed(_safe_delta(False, c.brier_winner, v4.brier_winner))} | "
            f"{_fmt_signed(_safe_delta(False, c.ece_winner, v2.ece_winner))} | "
            f"{_fmt_signed(_safe_delta(False, c.ece_winner, v3.ece_winner))} | "
            f"{_fmt_signed(_safe_delta(False, c.ece_winner, v4.ece_winner))}"
        )


def _print_weighted_summary(rows: List[Dict[str, Any]]) -> None:
    print("\n=== WEIGHTED GLOBAL SUMMARY (weighted by CURRENT test_rows) ===")
    models = ["current", "v2", "v3", "v4"]
    metrics = [
        ("winner_accuracy", True),
        ("outcome_accuracy", True),
        ("overall_mae", False),
        ("brier_winner", False),
        ("ece_winner", False),
    ]
    for metric_name, higher_is_better in metrics:
        parts: List[str] = [f"{metric_name}:"]
        base_values: List[Tuple[Optional[float], Optional[int]]] = []
        by_model: Dict[str, Optional[float]] = {}
        for m in models:
            vw: List[Tuple[Optional[float], Optional[int]]] = []
            for r in rows:
                mv = r.get(m)
                w = r.get("weight_rows")
                if not mv:
                    continue
                v = getattr(mv.metrics, metric_name)
                vw.append((v, w))
                if m == "current":
                    base_values.append((v, w))
            by_model[m] = _weighted_avg(vw)
            parts.append(f"{m}={_fmt(by_model[m], width=7, prec=4)}")

        base_avg = _weighted_avg(base_values)
        if base_avg is not None:
            d_v2 = _safe_delta(higher_is_better, base_avg, by_model["v2"])
            d_v3 = _safe_delta(higher_is_better, base_avg, by_model["v3"])
            d_v4 = _safe_delta(higher_is_better, base_avg, by_model["v4"])
            parts.append(
                " | deltas(vs current): "
                f"v2={_fmt_signed(d_v2, width=8, prec=4)} "
                f"v3={_fmt_signed(d_v3, width=8, prec=4)} "
                f"v4={_fmt_signed(d_v4, width=8, prec=4)}"
            )
        print(" ".join(parts))


def _print_best_model_counts(rows: List[Dict[str, Any]]) -> None:
    print("\n=== BEST MODEL COUNTS (league-level winners) ===")
    metric_defs = [
        ("winner_accuracy", True),
        ("outcome_accuracy", True),
        ("overall_mae", False),
        ("brier_winner", False),
        ("ece_winner", False),
    ]
    models = ["current", "v2", "v3", "v4"]
    for metric_name, higher_is_better in metric_defs:
        counts = {m: 0 for m in models}
        ties = 0
        for r in rows:
            vals: Dict[str, Optional[float]] = {}
            for m in models:
                mv = r.get(m)
                vals[m] = getattr(mv.metrics, metric_name) if mv else None
            present = {k: v for k, v in vals.items() if v is not None}
            if not present:
                continue
            best_v = max(present.values()) if higher_is_better else min(present.values())
            winners = [k for k, v in present.items() if abs(float(v) - float(best_v)) <= 1e-12]
            if len(winners) == 1:
                counts[winners[0]] += 1
            else:
                ties += 1
        print(
            f"{metric_name}: current={counts['current']} v2={counts['v2']} "
            f"v3={counts['v3']} v4={counts['v4']} ties={ties}"
        )


def _print_mismatch_diagnostics(rows: List[Dict[str, Any]]) -> None:
    print("\n=== DATA CONSISTENCY DIAGNOSTICS ===")
    mismatch_count = 0
    for r in rows:
        c = r.get("current")
        v2 = r.get("v2")
        v3 = r.get("v3")
        v4 = r.get("v4")
        tests = [
            ("current", c.test_rows if c else None),
            ("v2", v2.test_rows if v2 else None),
            ("v3", v3.test_rows if v3 else None),
            ("v4", v4.test_rows if v4 else None),
        ]
        present = [(k, v) for k, v in tests if v is not None]
        if len(present) <= 1:
            continue
        vals = {v for _, v in present}
        if len(vals) > 1:
            mismatch_count += 1
            joined = ", ".join(f"{k}:{v}" for k, v in present)
            print(f"- test_rows mismatch league {r['lid']} ({r['name']}): {joined}")
    if mismatch_count == 0:
        print("- No test_rows mismatches across provided reports.")

    missing_count = 0
    for r in rows:
        missing = [m for m in ("current", "v2", "v3", "v4") if r.get(m) is None]
        if missing:
            missing_count += 1
            print(f"- missing models league {r['lid']} ({r['name']}): {', '.join(missing)}")
    if missing_count == 0:
        print("- No missing model entries across provided reports.")


def _export_csv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "league_id",
        "league_name",
        "weight_rows",
    ]
    models = ["current", "v2", "v3", "v4"]
    metric_fields = [
        "winner_accuracy",
        "outcome_accuracy",
        "home_mae",
        "away_mae",
        "overall_mae",
        "brier_winner",
        "ece_winner",
    ]
    extra_fields = [
        "calibration_method",
        "alpha_avg_test",
        "variance_avg_test",
        "low_confidence_rate",
        "high_confidence_win_accuracy",
        "mode",
        "train_rows",
        "test_rows",
    ]
    for m in models:
        for mf in metric_fields:
            fields.append(f"{m}_{mf}")
        for ef in extra_fields:
            fields.append(f"{m}_{ef}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            rec: Dict[str, Any] = {
                "league_id": r["lid"],
                "league_name": r["name"],
                "weight_rows": r["weight_rows"],
            }
            for m in models:
                mv: Optional[ModelView] = r.get(m)
                mm = mv.metrics if mv else PerfMetrics()
                for mf in metric_fields:
                    rec[f"{m}_{mf}"] = getattr(mm, mf)
                rec[f"{m}_calibration_method"] = (mv.calibration_method if mv else None)
                rec[f"{m}_alpha_avg_test"] = (mv.alpha_avg_test if mv else None)
                rec[f"{m}_variance_avg_test"] = (mv.variance_avg_test if mv else None)
                rec[f"{m}_low_confidence_rate"] = (mv.low_confidence_rate if mv else None)
                rec[f"{m}_high_confidence_win_accuracy"] = (mv.high_confidence_win_accuracy if mv else None)
                rec[f"{m}_mode"] = (mv.mode if mv else None)
                rec[f"{m}_train_rows"] = (mv.train_rows if mv else None)
                rec[f"{m}_test_rows"] = (mv.test_rows if mv else None)
            w.writerow(rec)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Max-detail comparison: CURRENT vs V2 vs V3 vs V4."
    )
    parser.add_argument("--v2-report", default=None, help="Path to maz_maxed_v2_report_*.json")
    parser.add_argument("--v3-report", default=None, help="Path to maz_maxed_v3_report_*.json")
    parser.add_argument("--v4-report", default=None, help="Path to maz_maxed_v4_report_*.json")
    parser.add_argument(
        "--current-source",
        choices=["auto", "v2", "v3"],
        default="auto",
        help="Where CURRENT baseline should come from (auto prefers v3 then v2).",
    )
    parser.add_argument(
        "--sort-by",
        choices=[
            "league_id",
            "v4_win_delta",
            "v4_mae_delta",
            "v4_brier_delta",
            "v4_ece_delta",
        ],
        default="v4_win_delta",
    )
    parser.add_argument("--ascending", action="store_true")
    parser.add_argument(
        "--export-csv",
        default=None,
        help="Optional output CSV path for full parsed matrix.",
    )
    args = parser.parse_args()

    if not args.v2_report and not args.v3_report and not args.v4_report:
        raise SystemExit(
            "Provide at least one report: --v2-report and/or --v3-report and/or --v4-report"
        )

    raw_v2 = _read_json(args.v2_report)
    raw_v3 = _read_json(args.v3_report)
    raw_v4 = _read_json(args.v4_report)
    d2 = _extract_v2(raw_v2) if raw_v2 else {}
    d3 = _extract_v3(raw_v3) if raw_v3 else {}
    d4 = _extract_v4(raw_v4) if raw_v4 else {}

    lids = sorted(set(d2.keys()) | set(d3.keys()) | set(d4.keys()))
    if not lids:
        print("No tested leagues found in supplied reports.")
        return

    rows: List[Dict[str, Any]] = []
    for lid in lids:
        name = _merge_name(lid, d2, d3, d4)
        current = _pick_current(lid, args.current_source, d2, d3)
        v2 = d2.get(lid, {}).get("v2")
        v3 = d3.get(lid, {}).get("v3")
        v4 = d4.get(lid, {}).get("v4")
        weight_rows = (
            (current.test_rows if current and current.test_rows is not None else None)
            or (v4.test_rows if v4 and v4.test_rows is not None else None)
            or (v3.test_rows if v3 and v3.test_rows is not None else None)
            or (v2.test_rows if v2 and v2.test_rows is not None else None)
            or 1
        )

        c_m = current.metrics if current else PerfMetrics()
        v4_m = v4.metrics if v4 else PerfMetrics()
        row = {
            "lid": lid,
            "name": name,
            "weight_rows": int(weight_rows),
            "current": current,
            "v2": v2,
            "v3": v3,
            "v4": v4,
            "v4_win_delta": _safe_delta(True, c_m.winner_accuracy, v4_m.winner_accuracy),
            "v4_mae_delta": _safe_delta(False, c_m.overall_mae, v4_m.overall_mae),
            "v4_brier_delta": _safe_delta(False, c_m.brier_winner, v4_m.brier_winner),
            "v4_ece_delta": _safe_delta(False, c_m.ece_winner, v4_m.ece_winner),
        }
        rows.append(row)

    if args.sort_by == "league_id":
        rows.sort(key=lambda r: r["lid"], reverse=not args.ascending)
    else:
        rows.sort(
            key=lambda r: (-10.0 if r[args.sort_by] is None else float(r[args.sort_by])),
            reverse=not args.ascending,
        )

    print("=== REPORT INPUTS ===")
    print(f"v2_report: {args.v2_report}")
    print(f"v3_report: {args.v3_report}")
    print(f"v4_report: {args.v4_report}")
    print(f"current_source: {args.current_source}")
    print(f"leagues_covered: {len(rows)}")

    _print_core_matrix(rows)
    _print_reliability_matrix(rows)
    _print_delta_matrix(rows)
    _print_weighted_summary(rows)
    _print_best_model_counts(rows)
    _print_mismatch_diagnostics(rows)

    if args.export_csv:
        out_csv = Path(args.export_csv)
        _export_csv(rows, out_csv)
        print(f"\nCSV exported: {out_csv}")


if __name__ == "__main__":
    main()

