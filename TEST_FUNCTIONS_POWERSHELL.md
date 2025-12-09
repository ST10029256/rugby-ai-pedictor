# Testing Cloud Functions in PowerShell

## PowerShell Syntax (Not curl)

PowerShell uses `Invoke-WebRequest` or `Invoke-RestMethod` instead of curl.

## Test predict_match

```powershell
$body = @{
    home_team = "Leinster"
    away_team = "Munster"
    league_id = 4446
    match_date = "2025-11-25"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_match" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

## Test get_leagues

```powershell
Invoke-RestMethod -Uri "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_leagues" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{}"
```

## Test get_upcoming_matches

```powershell
$body = @{
    league_id = 4446
    limit = 10
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_upcoming_matches" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

## Alternative: Use curl.exe (Windows 10+)

If you have curl.exe installed, you can use it directly:

```powershell
curl.exe -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_match `
  -H "Content-Type: application/json" `
  -d '{\"home_team\": \"Leinster\", \"away_team\": \"Munster\", \"league_id\": 4446, \"match_date\": \"2025-11-25\"}'
```

## Quick Test Script

Save this as `test-functions.ps1`:

```powershell
# Test predict_match
Write-Host "Testing predict_match..." -ForegroundColor Cyan
$body = @{
    home_team = "Leinster"
    away_team = "Munster"
    league_id = 4446
    match_date = "2025-11-25"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_match" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body
    
    Write-Host "Success!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    $_.Exception.Response | Format-List
}
```

