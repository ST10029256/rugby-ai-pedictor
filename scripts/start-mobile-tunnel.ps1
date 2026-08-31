# Free HTTPS tunnel for mobile testing (Face ID / biometrics need HTTPS).
# Requires npm start running on port 3000 in another terminal.
$toolsDir = Join-Path $PSScriptRoot "..\tools"
$cloudflared = Join-Path $toolsDir "cloudflared.exe"

if (-not (Test-Path $cloudflared)) {
  Write-Host "Downloading cloudflared..."
  New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
  Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflared -UseBasicParsing
}

Write-Host ""
Write-Host "Starting HTTPS tunnel to http://localhost:3000"
Write-Host "Open the https://....trycloudflare.com URL on your phone (Safari/Chrome)."
Write-Host ""
& $cloudflared tunnel --url http://localhost:3000
