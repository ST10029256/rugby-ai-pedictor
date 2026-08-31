# Full prediction snapshot rebuild + copy DB + Firestore sync + Firebase deploy.
# Matches the GitHub "Check for Game Updates" full_refresh path (without game sync).
#
# Usage:
#   .\scripts\full-backfill-and-deploy.ps1
#   .\scripts\full-backfill-and-deploy.ps1 -SkipBackfill   # copy + deploy only
#   .\scripts\full-backfill-and-deploy.ps1 -SkipDeploy     # backfill + copy only

param(
  [string]$DbPath = "data.sqlite",
  [string]$FunctionsDb = "rugby-ai-predictor/data.sqlite",
  [string]$ProjectId = "rugby-ai-61fd0",
  [switch]$SkipBackfill = $false,
  [switch]$SkipDeploy = $false,
  [switch]$SkipFirestore = $false
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:LIVE_MODEL_FAMILY = "champion"
$env:LIVE_MODEL_CHANNEL = "prod_100"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $DbPath)) {
  throw "Database not found: $DbPath"
}

if (-not $SkipBackfill) {
  Write-Host "1/4 Rebuilding ALL prediction snapshots (champion:prod_100)..." -ForegroundColor Cyan
  Write-Host "    ~11k matches, expect 6-15 minutes."
  python rugby-ai-predictor/backfill_v4_predictions_all_games.py `
    --db $DbPath `
    --batch-size 500
} else {
  Write-Host "1/4 Skipping backfill (-SkipBackfill)." -ForegroundColor Yellow
}

Write-Host "2/4 Validating DB and copying to Functions bundle..." -ForegroundColor Cyan
python -c @"
import os, sqlite3, sys
db = os.environ.get('DB_PATH', '$DbPath')
family = os.environ.get('LIVE_MODEL_FAMILY', 'champion')
channel = os.environ.get('LIVE_MODEL_CHANNEL', 'prod_100')
version = f'{family}:{channel}'
with sqlite3.connect(db) as conn:
    check = conn.execute('PRAGMA quick_check').fetchone()
    if not check or check[0] != 'ok':
        sys.exit(f'SQLite quick_check failed: {check}')
    latest = conn.execute('SELECT MAX(date_event) FROM event WHERE home_score IS NOT NULL AND away_score IS NOT NULL').fetchone()[0]
    snaps = conn.execute('SELECT COUNT(*) FROM prediction_snapshot WHERE model_version = ?', (version,)).fetchone()[0]
print(f'Latest completed match: {latest}')
print(f'Snapshots for {version}: {snaps}')
if snaps == 0:
    sys.exit(f'No snapshots for {version}')
"@

$destDir = Split-Path -Parent $FunctionsDb
if ($destDir -and -not (Test-Path $destDir)) {
  New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}
Copy-Item -Path $DbPath -Destination $FunctionsDb -Force
Write-Host "    Copied $DbPath -> $FunctionsDb ($((Get-Item $FunctionsDb).Length) bytes)"

$envFile = Join-Path $destDir ".env"
@"
LIVE_MODEL_FAMILY=champion
LIVE_MODEL_CHANNEL=prod_100
"@ | Set-Content -Path $envFile -Encoding utf8
Write-Host "    Wrote $envFile"

if (-not $SkipFirestore) {
  Write-Host "3/4 Syncing matches to Firestore..." -ForegroundColor Cyan
  python scripts/sync_to_firestore.py --db $DbPath --project-id $ProjectId
} else {
  Write-Host "3/4 Skipping Firestore sync (-SkipFirestore)." -ForegroundColor Yellow
}

if (-not $SkipDeploy) {
  Write-Host "4/4 Deploying Firebase Functions (history + predictions)..." -ForegroundColor Cyan
  firebase deploy `
    --project $ProjectId `
    --only "functions:rugby-ai-predictor:get_historical_predictions_http,functions:rugby-ai-predictor:get_historical_backtest_http,functions:rugby-ai-predictor:get_league_standings_http,functions:rugby-ai-predictor:predict_matches_batch_http" `
    --non-interactive
} else {
  Write-Host "4/4 Skipping Firebase deploy (-SkipDeploy)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. Live site should now serve predictions through latest completed matches." -ForegroundColor Green
