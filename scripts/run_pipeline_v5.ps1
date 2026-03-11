param(
  [string]$DbPath = "data.sqlite",
  [int]$DaysAhead = 365,
  [int]$DaysBack = 90,
  [switch]$IncludeHistory = $false,
  [switch]$SkipRetrain = $false,
  [switch]$SkipDeploy = $false
)

$ErrorActionPreference = "Stop"

try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}
$env:PYTHONIOENCODING = "utf-8"
$env:LIVE_MODEL_FAMILY = "champion"

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

Write-Host "4. Copying data.sqlite into rugby-ai-predictor/ for Cloud Functions..."
Copy-Item -Path $DbPath -Destination "rugby-ai-predictor/data.sqlite" -Force

Write-Host "5. Syncing to Firestore (PWA matches)..."
python scripts/sync_to_firestore.py --db $DbPath --project-id rugby-ai-61fd0

if (-not $SkipRetrain) {
  Write-Host "6. Retraining V5 eval (80/20 walk-forward)..."
  python scripts/maz_boss_maxed_v5.py --all-leagues --walk-forward --wf-start-train 80 --wf-step 20 --min-games 100 --seq-len 10 --emb-dim 32 --hidden-dim 80 --n-experts 4 --adapter-dim 24 --cross-heads 4 --rating-k 0.06 --rating-home-adv 2.0 --rating-scale 7.0 --ensemble-seeds "42,1337,9001" --global-pretrain --global-pretrain-epochs 24 --finetune-epochs 14 --lr 0.001 --finetune-lr 0.0003 --batch-size 128 --winner-loss-weight 1.0 --score-loss-weight 0.30 --ranking-loss-weight 0.12 --embedding-l2-weight 0.0005 --var-reg-weight 0.002 --expert-balance-weight 0.01 --confidence-variance-threshold 40 --save-v5-models --save-global-pretrained --save-report --log-level INFO

  Write-Host "7. Retraining V5 production brain (100% completed games)..."
  python scripts/maz_boss_maxed_v5.py --all-leagues --train-all-completed --min-games 100 --seq-len 10 --emb-dim 32 --hidden-dim 80 --n-experts 4 --adapter-dim 24 --cross-heads 4 --rating-k 0.06 --rating-home-adv 2.0 --rating-scale 7.0 --ensemble-seeds "42,1337,9001" --global-pretrain --global-pretrain-epochs 24 --finetune-epochs 14 --lr 0.001 --finetune-lr 0.0003 --batch-size 128 --winner-loss-weight 1.0 --score-loss-weight 0.30 --ranking-loss-weight 0.12 --embedding-l2-weight 0.0005 --var-reg-weight 0.002 --expert-balance-weight 0.01 --save-v5-models --save-global-pretrained --save-report --log-level INFO

  Write-Host "8. Uploading V5 artifacts to Cloud Storage..."
  python scripts/upload_models_to_storage.py --bucket rugby-ai-61fd0.firebasestorage.app --models-dir artifacts --family-filter v5

  Write-Host "9. Publishing V5 metrics to Firestore..."
  python scripts/publish_v5_metrics_to_firestore.py --report artifacts/maz_maxed_v5_metrics_latest.json --prod-report artifacts/maz_maxed_v5_prod_latest.json --project-id rugby-ai-61fd0

  Write-Host "9b. Building league champion policy from V4 vs V5 eval reports..."
  python scripts/select_league_champions.py --v4-report artifacts/maz_maxed_v4_metrics_latest.json --v5-report artifacts/maz_maxed_v5_metrics_latest.json --output rugby-ai-predictor/league_model_champions.json --artifacts-copy artifacts/league_model_champions.json
} else {
  Write-Host "6-9b. Skipping V5 retrain/publish (-SkipRetrain)."
}

if (-not $SkipDeploy) {
  Write-Host "10. Deploying Firebase Functions..."
  Write-Host "    Note: make sure the deployed Functions runtime is configured with LIVE_MODEL_FAMILY=champion."
  firebase deploy --project rugby-ai-61fd0 --only functions --non-interactive
} else {
  Write-Host "10. Skipping deploy (-SkipDeploy)."
}
