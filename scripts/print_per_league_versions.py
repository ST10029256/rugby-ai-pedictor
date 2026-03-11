#!/usr/bin/env python3
"""
Print per-league win/lose accuracy and MAE for CURRENT, V2, V3, V4.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class M:
    win: Optional[float] = None
    mae: Optional[float] = None


def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _fmt(v: Optional[float], n: int = 3) -> str:
    if v is None:
        return "NA"
    return f"{v:.{n}f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "NA"
    return f"{round(float(v) * 100):d}%"


def _fmt_mae(v: Optional[float]) -> str:
    if v is None:
        return "NA"
    return f"{round(float(v), 1):.1f}"


def _load(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Report not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_v2(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid_s, payload in data.get("leagues", {}).items():
        if payload.get("status") != "tested":
            continue
        lid = int(lid_s)
        out[lid] = {
            "name": str(payload.get("name", f"League {lid}")),
            "current": M(
                win=_f(payload.get("current", {}).get("winner_accuracy")),
                mae=_f(payload.get("current", {}).get("overall_mae")),
            ),
            "v2": M(
                win=_f(payload.get("maz_maxed_v2", {}).get("winner_accuracy")),
                mae=_f(payload.get("maz_maxed_v2", {}).get("overall_mae")),
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
            "current": M(
                win=_f(payload.get("current", {}).get("winner_accuracy")),
                mae=_f(payload.get("current", {}).get("overall_mae")),
            ),
            "v3": M(
                win=_f(payload.get("maz_maxed_v3", {}).get("winner_accuracy")),
                mae=_f(payload.get("maz_maxed_v3", {}).get("overall_mae")),
            ),
        }
    return out


def _extract_v4(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for lid_s, payload in data.get("leagues", {}).items():
        if payload.get("status") != "tested":
            continue
        lid = int(lid_s)
        m = payload.get("metrics", {})
        out[lid] = {
            "name": str(payload.get("name", f"League {lid}")),
            "v4": M(
                win=_f(m.get("winner_accuracy")),
                mae=_f(m.get("overall_mae")),
            ),
        }
    return out


def _pick_current(
    lid: int,
    source: str,
    d2: Dict[int, Dict[str, Any]],
    d3: Dict[int, Dict[str, Any]],
) -> Optional[M]:
    if source == "v3":
        return d3.get(lid, {}).get("current")
    if source == "v2":
        return d2.get(lid, {}).get("current")
    return d3.get(lid, {}).get("current") or d2.get(lid, {}).get("current")


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-league win/lose + MAE for CURRENT/V2/V3/V4.")
    parser.add_argument("--v2-report", required=True)
    parser.add_argument("--v3-report", required=True)
    parser.add_argument("--v4-report", required=True)
    parser.add_argument("--current-source", choices=["auto", "v2", "v3"], default="v3")
    args = parser.parse_args()

    d2 = _extract_v2(_load(args.v2_report))
    d3 = _extract_v3(_load(args.v3_report))
    d4 = _extract_v4(_load(args.v4_report))

    lids = sorted(set(d2.keys()) | set(d3.keys()) | set(d4.keys()))
    if not lids:
        print("No tested leagues found.")
        return

    print(
        "league_id | league_name                       | "
        "CURRENT | V2 | V3 | V4"
    )
    print("-" * 104)

    for lid in lids:
        name = (
            d4.get(lid, {}).get("name")
            or d3.get(lid, {}).get("name")
            or d2.get(lid, {}).get("name")
            or f"League {lid}"
        )
        cur = _pick_current(lid, args.current_source, d2, d3) or M()
        v2 = d2.get(lid, {}).get("v2", M())
        v3 = d3.get(lid, {}).get("v3", M())
        v4 = d4.get(lid, {}).get("v4", M())
        print(
            f"{lid:7d} | {name[:32]:32s} | "
            f"{_fmt_pct(cur.win):>4s} / {_fmt_mae(cur.mae):>4s} MAE | "
            f"{_fmt_pct(v2.win):>4s} / {_fmt_mae(v2.mae):>4s} MAE | "
            f"{_fmt_pct(v3.win):>4s} / {_fmt_mae(v3.mae):>4s} MAE | "
            f"{_fmt_pct(v4.win):>4s} / {_fmt_mae(v4.mae):>4s} MAE"
        )


if __name__ == "__main__":
    main()

