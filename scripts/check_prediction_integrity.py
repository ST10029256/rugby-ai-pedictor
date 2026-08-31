#!/usr/bin/env python3
"""Assert that stored predictions are forecasts, not hindsight.

The app's credibility rests on one property: a prediction shown against a match
was produced before that match was played. Production training fits on every
completed game, so any prediction generated afterwards would be the model
recalling a result it was trained on - and it would look impressively accurate
while being worthless.

This checks the property directly against the database, and checks the rule that
enforces it. Run it in CI so a future change cannot quietly reintroduce the
back-dated predictions this codebase used to produce.

    python scripts/check_prediction_integrity.py --db data.sqlite
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.prediction_integrity import refuse_reason, utcnow  # noqa: E402

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def check_rule() -> list:
    """The guard itself: which situations may produce a stored forecast."""
    now = utcnow()
    cases = [
        ("kickoff 6h away", dict(kickoff_at=(now + timedelta(hours=6)).isoformat(), has_actual_score=False), True),
        ("kickoff 1min away", dict(kickoff_at=(now + timedelta(minutes=1)).isoformat(), has_actual_score=False), True),
        ("kicked off 1min ago", dict(kickoff_at=(now - timedelta(minutes=1)).isoformat(), has_actual_score=False), False),
        ("kicked off 6h ago", dict(kickoff_at=(now - timedelta(hours=6)).isoformat(), has_actual_score=False), False),
        ("final score known", dict(kickoff_at=(now + timedelta(hours=6)).isoformat(), has_actual_score=True), False),
        ("date-only, tomorrow", dict(kickoff_at=(now + timedelta(days=1)).date().isoformat(), has_actual_score=False), True),
        ("date-only, today", dict(kickoff_at=now.date().isoformat(), has_actual_score=False), False),
        ("date-only, yesterday", dict(kickoff_at=(now - timedelta(days=1)).date().isoformat(), has_actual_score=False), False),
        ("no kickoff recorded", dict(kickoff_at=None, has_actual_score=False), False),
    ]

    failures = []
    print("--- pre-kickoff rule ---")
    for label, kwargs, should_allow in cases:
        reason = refuse_reason(**kwargs)
        allowed = reason is None
        ok = allowed == should_allow
        if not ok:
            failures.append(f"rule: {label} -> {'allowed' if allowed else 'refused'}")
        print(f"  {'ok  ' if ok else 'FAIL'} {label:22} {'allow' if allowed else 'refuse'}")
    return failures


def check_stored_data(db_path: str) -> list:
    """Nothing already written may claim to predict a match that had started."""
    failures = []
    conn = sqlite3.connect(db_path)
    print("\n--- stored forecasts ---")

    total = conn.execute(
        "SELECT COUNT(*) FROM prediction_snapshot WHERE snapshot_type = 'pre_kickoff_live'"
    ).fetchone()[0]

    leaked = conn.execute(
        """
        SELECT COUNT(*) FROM prediction_snapshot
        WHERE snapshot_type = 'pre_kickoff_live'
          AND kickoff_at IS NOT NULL AND predicted_at IS NOT NULL
          AND length(kickoff_at) > 10
          AND predicted_at > kickoff_at
        """
    ).fetchone()[0]

    print(f"  frozen forecasts            : {total}")
    print(f"  recorded after kickoff      : {leaked}")
    if leaked:
        failures.append(f"{leaked} forecast(s) were recorded after their kickoff")

    # Fixtures that already have a forecast must not also carry a re-scored one
    # for the same model, which would give two different answers for one match.
    both = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT match_id, model_version
            FROM prediction_snapshot
            GROUP BY match_id, model_version
            HAVING COUNT(DISTINCT snapshot_type) > 1
        )
        """
    ).fetchone()[0]
    print(f"  matches with conflicting rows: {both}")
    if both:
        failures.append(f"{both} match(es) hold more than one prediction per model")

    conn.close()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data.sqlite"))
    args = parser.parse_args()

    failures = check_rule()
    if Path(args.db).exists():
        failures += check_stored_data(args.db)
    else:
        print(f"\n(skipping stored-data checks: {args.db} not found)")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nAll prediction integrity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
