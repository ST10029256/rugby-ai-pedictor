"""Killer V2 = A5 frozen. Live-forward vs V4.

Do not run develop/exam to redesign A5. The 2,936 historical benchmark is closed.

  python -u scripts/maz_boss_killer_v2.py --phase freeze
  python -u scripts/maz_boss_killer_v2.py --phase live
  python -u scripts/maz_boss_killer_v2.py --phase status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))
sys.path.insert(0, str(ROOT / "scripts"))

from killer_v1_rebuilt.config import LIVE_ARTIFACT_DIR  # noqa: E402
from killer_v1_rebuilt.freeze import freeze_is_ready  # noqa: E402
from killer_v1_rebuilt.live import (  # noqa: E402
    freeze_production,
    live_status,
    load_scored_history,
    settle_actuals,
    sync_live_ledger,
)
from killer_v1_rebuilt.config import DEFAULT_LEAGUE_IDS  # noqa: E402

LOG = logging.getLogger("killer_v2")


def main() -> None:
    p = argparse.ArgumentParser(description="Killer V2 frozen live-forward")
    p.add_argument("--db", default=str(ROOT / "data.sqlite"))
    p.add_argument("--out-dir", default=str(ROOT / LIVE_ARTIFACT_DIR))
    p.add_argument("--v4-artifacts", default=str(ROOT / "artifacts"))
    p.add_argument("--phase", choices=["freeze", "live", "lock", "settle", "status"], default="live")
    p.add_argument("--device", default="cpu")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    out_dir = Path(args.out_dir)
    db = Path(args.db)
    device = torch.device(args.device)

    if args.phase == "freeze":
        df = load_scored_history(db, DEFAULT_LEAGUE_IDS)
        manifest = freeze_production(df_scored=df, out_dir=out_dir, device=device)
        LOG.info(
            "Frozen Killer V2 A5 n_train=%s checkpoint=%s",
            manifest.get("n_train"),
            str(manifest.get("killer_checkpoint_hash", ""))[:12],
        )
        return

    if args.phase == "status":
        if not freeze_is_ready(out_dir):
            LOG.info("Freeze not ready at %s", out_dir)
            return
        print(json.dumps(live_status(out_dir), indent=2, default=str))
        return

    if args.phase == "settle":
        print(json.dumps(settle_actuals(db=db, out_dir=out_dir), indent=2))
        return

    # live / lock
    result = sync_live_ledger(
        db,
        out_dir,
        device=device,
        artifacts_v4=Path(args.v4_artifacts),
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
