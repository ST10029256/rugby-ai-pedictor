param(
  [string]$DbPath = "data.sqlite",
  [int]$DaysAhead = 365,
  [int]$DaysBack = 90,
  [switch]$IncludeHistory = $false,
  [switch]$SkipRetrain = $false,
  [switch]$SkipDeploy = $false
)

$ErrorActionPreference = "Stop"

# Ensure UTF-8 output (prevents UnicodeEncodeError in scheduled tasks)
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}
$env:PYTHONIOENCODING = "utf-8"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "1. Detecting completed matches (scores from API)..."
python scripts/detect_completed_matches.py --db $DbPath --verbose

Write-Host "2. Fetching new games and upcoming fixtures (all leagues)..."
Write-Host "   Days ahead: $DaysAhead | Days back: $DaysBack (captures current year completed games)"
$updateArgs = @("scripts/enhanced_auto_update.py", "--db", $DbPath, "--days-ahead", "$DaysAhead", "--days-back", "$DaysBack", "--verbose")
if ($IncludeHistory) { $updateArgs += "--include-history" }
python @updateArgs

Write-Host "3. Post-update duplicate cleanup..."
python cleanup_duplicates_post_update.py

Write-Host "4. Copying data.sqlite into rugby-ai-predictor/ for Cloud Functions (History)..."
Copy-Item -Path $DbPath -Destination "rugby-ai-predictor/data.sqlite" -Force

Write-Host "5. Syncing to Firestore (PWA matches)..."
python scripts/sync_to_firestore.py --db $DbPath --project-id rugby-ai-61fd0

if (-not $SkipRetrain) {
  Write-Host "6. Retraining V4 eval (80/20 walk-forward)..."
  python scripts/maz_boss_maxed_v4.py --all-leagues --walk-forward --wf-start-train 80 --wf-step 20 --min-games 100 --seq-len 10 --emb-dim 32 --hidden-dim 64 --rating-k 0.06 --rating-home-adv 2.0 --rating-scale 7.0 --ensemble-seeds "42,1337,9001" --global-pretrain --global-pretrain-epochs 20 --finetune-epochs 12 --lr 0.001 --finetune-lr 0.0003 --batch-size 128 --winner-loss-weight 1.0 --score-loss-weight 0.25 --ranking-loss-weight 0.10 --embedding-l2-weight 0.0005 --var-reg-weight 0.002 --confidence-variance-threshold 40 --save-v4-models --save-global-pretrained --save-report --log-level INFO

  Write-Host "7. Retraining V4 production brain (100% completed games)..."
  python scripts/maz_boss_maxed_v4.py --all-leagues --train-all-completed --min-games 100 --seq-len 10 --emb-dim 32 --hidden-dim 64 --rating-k 0.06 --rating-home-adv 2.0 --rating-scale 7.0 --ensemble-seeds "42,1337,9001" --global-pretrain --global-pretrain-epochs 20 --finetune-epochs 12 --lr 0.001 --finetune-lr 0.0003 --batch-size 128 --winner-loss-weight 1.0 --score-loss-weight 0.25 --ranking-loss-weight 0.10 --embedding-l2-weight 0.0005 --var-reg-weight 0.002 --save-v4-models --save-global-pretrained --save-report --log-level INFO

  Write-Host "8. Uploading V4 artifacts to Cloud Storage..."
  python scripts/upload_models_to_storage.py --bucket rugby-ai-61fd0.firebasestorage.app --models-dir artifacts

  Write-Host "9. Publishing V4 metrics to Firestore..."
  python scripts/publish_v4_metrics_to_firestore.py --report artifacts/maz_maxed_v4_metrics_latest.json --prod-report artifacts/maz_maxed_v4_prod_latest.json --project-id rugby-ai-61fd0
} else {
  Write-Host "6-9. Skipping V4 retrain/publish (-SkipRetrain)."
}

if (-not $SkipDeploy) {
  Write-Host "10. Deploying Firebase Functions (History + Predictions live for users)..."
  firebase deploy --project rugby-ai-61fd0 --only functions --non-interactive
} else {
  Write-Host "10. Skipping deploy (-SkipDeploy)."
}


