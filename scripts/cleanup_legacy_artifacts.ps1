param(
  [string]$ArtifactsDir = "artifacts",
  [switch]$DryRun = $false,
  [switch]$DeleteAllNonV4 = $false,
  [switch]$AlsoDeleteXgboost = $false
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ArtifactsDir)) {
  Write-Host "Artifacts directory not found: $ArtifactsDir"
  exit 1
}

$allFiles = Get-ChildItem -Path $ArtifactsDir -Recurse -File

if ($DeleteAllNonV4) {
  $toDelete = $allFiles | Where-Object {
    $_.Name.ToLowerInvariant() -notlike "*v4*"
  }
} else {
  # Legacy/current markers to remove while keeping V4 assets.
  # By default, KEEP xgboost for runtime safety unless explicitly requested.
  $toDelete = $allFiles | Where-Object {
    $n = $_.Name.ToLowerInvariant()
    $matchLegacy = (
      $n -like "*v2*" -or
      $n -like "*v3*" -or
      $n -like "*optimized*" -or
      $n -like "*model_registry*" -or
      $n -like "*current*"
    )
    $matchXgb = ($n -like "*xgboost*")
    (
      $matchLegacy -or
      ($AlsoDeleteXgboost -and $matchXgb)
    ) -and ($n -notlike "*v4*")
  }
}

if (-not $toDelete -or $toDelete.Count -eq 0) {
  Write-Host "No legacy artifacts found to delete."
  exit 0
}

$totalBytes = ($toDelete | Measure-Object -Property Length -Sum).Sum
$totalMb = [math]::Round(($totalBytes / 1MB), 2)

Write-Host "Found $($toDelete.Count) file(s) to delete ($totalMb MB):"
$toDelete | ForEach-Object { Write-Host " - $($_.FullName)" }

if ($DryRun) {
  Write-Host ""
  Write-Host "[DRY RUN] No files were deleted."
  exit 0
}

$deleted = 0
foreach ($f in $toDelete) {
  Remove-Item -Path $f.FullName -Force
  $deleted++
}

Write-Host ""
Write-Host "[OK] Deleted $deleted legacy artifact file(s)."
