#!/usr/bin/env python3
"""
Convenience wrapper for publishing V5 metrics to Firestore.
"""

import argparse

from publish_v4_metrics_to_firestore import publish


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish V5 metrics to Firestore")
    parser.add_argument("--report", default="artifacts/maz_maxed_v5_metrics_latest.json", help="Path to V5 walk-forward metrics report")
    parser.add_argument(
        "--prod-report",
        default="artifacts/maz_maxed_v5_prod_latest.json",
        help="Path to V5 production report for full trained game counts",
    )
    parser.add_argument("--project-id", default="rugby-ai-61fd0", help="Firebase project ID")
    parser.add_argument("--model-channel", default="eval_80_20", help="Model channel label")
    args = parser.parse_args()

    updated = publish(
        report_path=args.report,
        project_id=args.project_id,
        prod_report_path=args.prod_report,
        model_family="v5",
        model_type="v5",
        model_channel=args.model_channel,
    )
    print(f"[OK] Updated {updated} league_metrics docs from V5 report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
