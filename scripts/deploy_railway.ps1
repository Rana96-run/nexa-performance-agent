# deploy_railway.ps1
# Run this ONCE after upgrading Railway to Hobby plan.
# Creates the nexa-performance-agent project, two services,
# and pushes all environment variables.
#
# Usage: cd "D:\Nexa Performance Agent"; .\scripts\deploy_railway.ps1

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

Write-Host "=== Nexa Railway Deployment ===" -ForegroundColor Cyan

# ─── 1. Create project ────────────────────────────────────────────────────────
Write-Host "`n[1/6] Creating Railway project..." -ForegroundColor Yellow
$proj = railway init --name "nexa-performance-agent" 2>&1
Write-Host $proj

# ─── 2. Link to GitHub repo ───────────────────────────────────────────────────
Write-Host "`n[2/6] GitHub repo is already at https://github.com/Rana96-run/nexa-performance-agent" -ForegroundColor Yellow
Write-Host "      Link it in Railway Dashboard: New Service -> GitHub Repo -> Rana96-run/nexa-performance-agent"
Write-Host "      Create TWO services: nexa-web and nexa-worker"
Write-Host "      Press Enter when both services are created..." -ForegroundColor Cyan
Read-Host

# ─── 3. Build GOOGLE_APPLICATION_CREDENTIALS_JSON ────────────────────────────
Write-Host "`n[3/6] Reading BigQuery service account key..." -ForegroundColor Yellow
$bqKey = Get-Content "D:\Nexa Performance Agent\certs\bigquery-key.json" -Raw
$bqKey = $bqKey.Trim()
Write-Host "      BQ key loaded ($($bqKey.Length) chars)"

# ─── 4. Read .env file ────────────────────────────────────────────────────────
Write-Host "`n[4/6] Reading .env file..." -ForegroundColor Yellow
$envLines = Get-Content "D:\Nexa Performance Agent\.env" | Where-Object {
    $_ -notmatch "^\s*#" -and $_ -match "="
}
Write-Host "      Found $($envLines.Count) variables"

# ─── 5. Set vars on nexa-web ──────────────────────────────────────────────────
Write-Host "`n[5/6] Setting env vars on nexa-web service..." -ForegroundColor Yellow
Write-Host "      Link to nexa-web service first..."
railway service --service nexa-web 2>&1 | Write-Host

foreach ($line in $envLines) {
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        if ($val -and $val -notmatch "^\s*#") {
            railway variables set "$key=$val" --service nexa-web 2>&1 | Out-Null
            Write-Host "      SET $key" -ForegroundColor DarkGray
        }
    }
}
# Add the BQ JSON credential
railway variables set "GOOGLE_APPLICATION_CREDENTIALS_JSON=$bqKey" --service nexa-web 2>&1 | Out-Null
Write-Host "      SET GOOGLE_APPLICATION_CREDENTIALS_JSON" -ForegroundColor DarkGray

# ─── 6. Copy vars to nexa-worker ──────────────────────────────────────────────
Write-Host "`n[6/6] Setting env vars on nexa-worker service..." -ForegroundColor Yellow
railway service --service nexa-worker 2>&1 | Write-Host

foreach ($line in $envLines) {
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        if ($val -and $val -notmatch "^\s*#") {
            railway variables set "$key=$val" --service nexa-worker 2>&1 | Out-Null
        }
    }
}
railway variables set "GOOGLE_APPLICATION_CREDENTIALS_JSON=$bqKey" --service nexa-worker 2>&1 | Out-Null
Write-Host "      All vars set on nexa-worker" -ForegroundColor DarkGray

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Next steps in Railway Dashboard:" -ForegroundColor Cyan
Write-Host "  nexa-web    -> Start Command: gunicorn `"reports.app:app`" --bind 0.0.0.0:`$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -"
Write-Host "  nexa-worker -> Start Command: python worker.py"
Write-Host "  Trigger a deploy on both services."
Write-Host ""
Write-Host "Then set your HubSpot webhook URL to:"
Write-Host "  https://<your-railway-domain>/webhooks/hubspot"
