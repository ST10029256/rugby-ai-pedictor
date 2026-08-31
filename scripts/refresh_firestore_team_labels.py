#!/usr/bin/env python3
"""Bring Firestore team labels and caches in line with the repaired database.

`fix_team_identity.py` gave each Currie Cup province its own identity, and
`sync_to_firestore.py` refreshed the `teams` and `matches` collections. Three
things it does not touch still carry the old franchise names:

* `predictions` - team names and the predicted winner are stored as strings.
* `standings_cache_v1` and `upcoming_prediction_cache_v1` - derived caches that
  rebuild themselves, so they are simply cleared.

    python scripts/refresh_firestore_team_labels.py --dry-run
    python scripts/refresh_firestore_team_labels.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from google.cloud import firestore  # noqa: E402

from prediction.team_display_names import (  # noqa: E402
    CURRIE_CUP_LEAGUE_ID,
    canonical_model_team_name,
)

NAME_FIELDS = ("home_team", "away_team", "predicted_winner", "winner")
CACHES_TO_CLEAR = ("standings_cache_v1", "upcoming_prediction_cache_v1")


def refresh_predictions(db: firestore.Client, apply: bool) -> int:
    """Rewrite stored team names that still use the franchise label."""
    changed = 0
    batch = db.batch()
    pending = 0

    for doc in db.collection("predictions").stream():
        data = doc.to_dict() or {}
        try:
            league_id = int(data.get("league_id") or 0)
        except (TypeError, ValueError):
            continue
        if league_id != CURRIE_CUP_LEAGUE_ID:
            continue

        patch = {}
        for field in NAME_FIELDS:
            value = data.get(field)
            if not isinstance(value, str) or value in ("Home", "Away", ""):
                continue
            corrected = canonical_model_team_name(value, league_id)
            if corrected != value:
                patch[field] = corrected

        if not patch:
            continue
        changed += 1
        print(f"  {doc.id}: {patch}")
        if apply:
            batch.update(doc.reference, patch)
            pending += 1
            if pending >= 400:
                batch.commit()
                batch = db.batch()
                pending = 0

    if apply and pending:
        batch.commit()
    return changed


def clear_caches(db: firestore.Client, apply: bool) -> int:
    """Drop derived caches keyed on the old names so they rebuild."""
    removed = 0
    for name in CACHES_TO_CLEAR:
        docs = list(db.collection(name).stream())
        print(f"  {name}: {len(docs)} docs")
        for doc in docs:
            if apply:
                doc.reference.delete()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default="rugby-ai-61fd0")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = firestore.Client(project=args.project_id)
    print(f"Project: {args.project_id}{'' if args.apply else '   (dry run)'}")

    print("\n--- predictions with stale team labels ---")
    changed = refresh_predictions(db, args.apply)
    print(f"  -> {changed} documents {'updated' if args.apply else 'would be updated'}")

    print("\n--- derived caches ---")
    removed = clear_caches(db, args.apply)
    print(f"  -> {removed} cache documents {'deleted' if args.apply else 'would be deleted'}")

    if not args.apply:
        print("\nNothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
