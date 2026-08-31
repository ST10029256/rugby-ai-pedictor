"""Pick smallest ablation that earns its place on develop-val."""

from __future__ import annotations

from typing import Any, Dict, List


def select_ablation(rows: List[Dict[str, Any]]) -> str:
    """
    rows: [{ablation, brier, accuracy, home_mae, margin_mae}, ...] in A0..A5 order.
    Lowest Brier among those with home MAE no worse than A0 by >2%.
    If later steps don't beat the current winner by >0.002 Brier, keep the smaller one.
    """
    if not rows:
        return "A0"
    a0 = next(r for r in rows if r["ablation"] == "A0")
    mae_cap = float(a0["home_mae"]) * 1.02
    eligible = [r for r in rows if float(r["home_mae"]) <= mae_cap + 1e-9]
    if not eligible:
        eligible = [a0]
    eligible = sorted(eligible, key=lambda r: (float(r["brier"]), r["ablation"]))
    winner = eligible[0]
    # walk A0.. in order; only step up if Brier improves by >= 0.002
    order = ["A0", "A1", "A2", "A3", "A4", "A5"]
    by = {r["ablation"]: r for r in rows}
    chosen = "A0"
    best_brier = float(by["A0"]["brier"])
    for name in order[1:]:
        r = by.get(name)
        if r is None:
            continue
        if float(r["home_mae"]) > mae_cap:
            continue
        if float(r["brier"]) <= best_brier - 0.002:
            chosen = name
            best_brier = float(r["brier"])
    return chosen
