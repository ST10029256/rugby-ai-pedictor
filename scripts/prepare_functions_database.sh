#!/usr/bin/env bash
# Sync completed scores and copy data.sqlite into rugby-ai-predictor/ so the
# Firebase deploy always serves fresh results.
#
# This does NOT re-score finished games. Doing so after retraining asked a model
# about results it had just been fitted on, which is not a prediction. Forecasts
# are frozen before kickoff by the freeze inside enhanced_auto_update.py.
#
# Environment:
#   SYNC=true|false          Run Highlightly sync first (default: true)
#   BACKFILL=true|false      Re-score finished games (default: false; offline analysis only)
#   ONLY_MISSING=true|false  When BACKFILL=true, skip games that already have a snapshot (default: true)
#   DAYS_BACK=400            How far back incremental sync looks for results
#   LIVE_MODEL_FAMILY        Model family tag for snapshots (default: champion)
#   LIVE_MODEL_CHANNEL       Model channel tag for snapshots (default: prod_100)
#   HIGHLIGHTLY_API_KEY      Required when SYNC=true

set -Eeuo pipefail

ROOT_DB="${1:-data.sqlite}"
FUNCTIONS_DB="${2:-rugby-ai-predictor/data.sqlite}"
SYNC="${SYNC:-true}"
BACKFILL="${BACKFILL:-false}"
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

if [[ "$BACKFILL" == "true" ]]; then
  BACKFILL_ARGS=(--db "$ROOT_DB" --batch-size 500)
  if [[ "$ONLY_MISSING" == "true" ]]; then
    BACKFILL_ARGS+=(--only-missing)
    echo "Backfilling missing prediction snapshots only..."
  else
    echo "::warning::Rebuilding ALL prediction snapshots with the current model."
    echo "::warning::These are not forecasts: the model was trained on these results."
  fi
  python rugby-ai-predictor/backfill_v4_predictions_all_games.py "${BACKFILL_ARGS[@]}"
else
  echo "Skipping finished-game backfill (BACKFILL=false)."
  echo "Forecasts come from the pre-kickoff freeze, not from re-scoring played games."
fi

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
    frozen = conn.execute(
        """
        SELECT COUNT(*) FROM prediction_snapshot
        WHERE model_version = ? AND snapshot_type = 'pre_kickoff_live'
        """,
        (version,),
    ).fetchone()[0]
    upcoming = conn.execute(
        """
        SELECT COUNT(*) FROM event
        WHERE (home_score IS NULL OR away_score IS NULL)
          AND date(date_event) BETWEEN date('now') AND date('now', '+2 days')
        """
    ).fetchone()[0]

print(f"Latest completed match date: {latest}")
print(f"Prediction snapshots total: {total_snaps}")
print(f"Prediction snapshots for {version}: {version_snaps}")
print(f"Frozen pre-kickoff forecasts for {version}: {frozen}")

# Zero snapshots is expected right after the switch to pre-kickoff-only history,
# since forecasts accumulate one matchday at a time. What must not happen is
# fixtures kicking off within the freeze horizon that carry no forecast.
if upcoming and not frozen:
    sys.exit(
        f"{upcoming} fixture(s) kick off within 2 days but none have a frozen "
        f"forecast for {version}. The pre-kickoff freeze is not running."
    )
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
