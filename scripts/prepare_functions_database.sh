#!/usr/bin/env bash
# Sync completed scores, backfill prediction snapshots, and copy data.sqlite into
# rugby-ai-predictor/ so Firebase deploy always serves fresh history.
#
# Environment:
#   SYNC=true|false          Run Highlightly sync before backfill (default: true)
#   ONLY_MISSING=true|false  Backfill only games missing snapshots (default: true)
#   DAYS_BACK=400            How far back incremental sync looks for results
#   LIVE_MODEL_FAMILY        Model family tag for snapshots (default: champion)
#   LIVE_MODEL_CHANNEL       Model channel tag for snapshots (default: prod_100)
#   HIGHLIGHTLY_API_KEY      Required when SYNC=true

set -Eeuo pipefail

ROOT_DB="${1:-data.sqlite}"
FUNCTIONS_DB="${2:-rugby-ai-predictor/data.sqlite}"
SYNC="${SYNC:-true}"
ONLY_MISSING="${ONLY_MISSING:-true}"
DAYS_BACK="${DAYS_BACK:-400}"
LIVE_MODEL_FAMILY="${LIVE_MODEL_FAMILY:-champion}"
LIVE_MODEL_CHANNEL="${LIVE_MODEL_CHANNEL:-prod_100}"

test -f "$ROOT_DB" || {
  echo "::error::Database not found: $ROOT_DB"
  exit 1
}

if [[ "$SYNC" == "true" ]]; then
  if [[ -z "${HIGHLIGHTLY_API_KEY:-}" ]]; then
    echo "::warning::HIGHLIGHTLY_API_KEY is not set; skipping game data sync."
  else
    echo "Syncing completed scores and upcoming fixtures (days_back=$DAYS_BACK)..."
    for attempt in 1 2 3; do
      if python scripts/enhanced_auto_update.py \
        --db "$ROOT_DB" \
        --verbose \
        --days-ahead 365 \
        --days-back "$DAYS_BACK"; then
        break
      fi
      if [[ "$attempt" -eq 3 ]]; then
        echo "::error::Game data sync failed after 3 attempts."
        exit 1
      fi
      sleep $((attempt * 15))
    done
  fi
else
  echo "Skipping game data sync (SYNC=false)."
fi

python cleanup_duplicates_post_update.py "$ROOT_DB"

export LIVE_MODEL_FAMILY LIVE_MODEL_CHANNEL
export PREPARE_DB_PATH="$ROOT_DB"

BACKFILL_ARGS=(--db "$ROOT_DB" --batch-size 500)
if [[ "$ONLY_MISSING" == "true" ]]; then
  BACKFILL_ARGS+=(--only-missing)
  echo "Backfilling missing prediction snapshots only..."
else
  echo "Rebuilding all prediction snapshots for ${LIVE_MODEL_FAMILY}:${LIVE_MODEL_CHANNEL}..."
fi

python rugby-ai-predictor/backfill_v4_predictions_all_games.py "${BACKFILL_ARGS[@]}"

python - <<'PY'
import os
import sqlite3
import sys

db = os.environ["PREPARE_DB_PATH"]
family = os.environ.get("LIVE_MODEL_FAMILY", "champion")
channel = os.environ.get("LIVE_MODEL_CHANNEL", "prod_100")
version = f"{family}:{channel}"

with sqlite3.connect(db) as conn:
    check = conn.execute("PRAGMA quick_check").fetchone()
    if not check or check[0] != "ok":
        sys.exit(f"SQLite quick_check failed: {check}")

    latest = conn.execute(
        """
        SELECT MAX(date_event)
        FROM event
        WHERE home_score IS NOT NULL
          AND away_score IS NOT NULL
        """
    ).fetchone()[0]
    if not latest:
        sys.exit("No completed matches found after prepare.")

    total_snaps = conn.execute("SELECT COUNT(*) FROM prediction_snapshot").fetchone()[0]
    version_snaps = conn.execute(
        "SELECT COUNT(*) FROM prediction_snapshot WHERE model_version = ?",
        (version,),
    ).fetchone()[0]

print(f"Latest completed match date: {latest}")
print(f"Prediction snapshots total: {total_snaps}")
print(f"Prediction snapshots for {version}: {version_snaps}")

if version_snaps == 0:
    sys.exit(f"No prediction snapshots for live model version {version}.")
PY

mkdir -p "$(dirname "$FUNCTIONS_DB")"
cp "$ROOT_DB" "$FUNCTIONS_DB"
echo "Copied $ROOT_DB -> $FUNCTIONS_DB ($(wc -c < "$FUNCTIONS_DB") bytes)"

FUNCTIONS_ENV="$(dirname "$FUNCTIONS_DB")/.env"
cat > "$FUNCTIONS_ENV" <<EOF
LIVE_MODEL_FAMILY=${LIVE_MODEL_FAMILY}
LIVE_MODEL_CHANNEL=${LIVE_MODEL_CHANNEL}
EOF
echo "Wrote $FUNCTIONS_ENV"
