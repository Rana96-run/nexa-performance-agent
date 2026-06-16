# BigQuery MCP — one-shot installer
# Run from PowerShell: .\install.ps1
# Or double-click install.bat in the same folder.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPath = Join-Path $ScriptDir "server.py"
$KeyPath    = "D:\Nexa Performance Agent\secrets\bigquery-key.json"
$ConfigPath = "$env:APPDATA\Claude\claude_desktop_config.json"

Write-Host "`n=== BigQuery MCP Installer ===" -ForegroundColor Cyan

# ── 1. Install Python dependencies ─────────────────────────────────────────
Write-Host "`n[1/2] Installing Python packages..." -ForegroundColor Yellow
pip install mcp google-cloud-bigquery google-auth db-dtypes --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed. Make sure Python is on your PATH."
    exit 1
}
Write-Host "      Packages installed." -ForegroundColor Green

# ── 2. Update claude_desktop_config.json ───────────────────────────────────
Write-Host "`n[2/2] Registering MCP in Claude config ($ConfigPath)..." -ForegroundColor Yellow

# Read existing config, or start fresh
if (Test-Path $ConfigPath) {
    $raw    = Get-Content $ConfigPath -Raw
    $config = $raw | ConvertFrom-Json
} else {
    $config = [PSCustomObject]@{}
}

# Ensure mcpServers key exists
if (-not ($config.PSObject.Properties.Name -contains "mcpServers")) {
    $config | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
}

# Add / overwrite bigquery_mcp entry
$entry = [PSCustomObject]@{
    command = "python"
    args    = @($ServerPath)
    env     = [PSCustomObject]@{
        GOOGLE_APPLICATION_CREDENTIALS = $KeyPath
        BQ_PROJECT_ID                  = "angular-axle-492812-q4"
        BQ_DATASET                     = "nexa_performance"
        BQ_LOCATION                    = "me-central1"
    }
}

$config.mcpServers | Add-Member -MemberType NoteProperty -Name "bigquery_mcp" -Value $entry -Force

# Write back
$config | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
Write-Host "      Registered as 'bigquery_mcp'." -ForegroundColor Green

Write-Host "`n=== Done! Restart Claude desktop to activate the BigQuery MCP. ===" -ForegroundColor Cyan
