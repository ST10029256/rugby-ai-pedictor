$ErrorActionPreference = "Stop"

# Ensure UTF-8 output (prevents UnicodeEncodeError in scheduled tasks)
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}
$env:PYTHONIOENCODING = "utf-8"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

param(
  [string]$DbPath = "data.sqlite",
  [int]$DaysAhead = 365,
  [int]$DaysBack = 14,
  [switch]$IncludeHistory = $false
)

Write-Host "Running enhanced_auto_update..."
Write-Host "Note: Round scanning is now automatic for all leagues - no flag needed"
$updateArgs = @("scripts/enhanced_auto_update.py", "--db", $DbPath, "--days-ahead", "$DaysAhead", "--days-back", "$DaysBack")
if ($IncludeHistory) { $updateArgs += "--include-history" }
python @updateArgs

Write-Host "Running sync_to_firestore..."
python scripts/sync_to_firestore.py


