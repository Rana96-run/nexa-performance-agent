# Slack MCP — one-shot installer
# Run from PowerShell: .\install.ps1
# Or double-click install.bat in the same folder.
#
# Reads SLACK_BOT_TOKEN and channel IDs from the project .env file,
# then registers the MCP server in Claude's desktop config.

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPath = Join-Path $ScriptDir "server.py"
$EnvFile    = "D:\Nexa Performance Agent\.env"
$ConfigPath = "$env:APPDATA\Claude\claude_desktop_config.json"

Write-Host "`n=== Slack MCP Installer ===" -ForegroundColor Cyan

# ── 1. Read tokens from .env ────────────────────────────────────────────────
Write-Host "`n[1/3] Reading credentials from .env..." -ForegroundColor Yellow

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at $EnvFile. Add your Slack tokens there first."
    exit 1
}

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -match "^([A-Z0-9_]+)=(.+)$") {
        $envVars[$Matches[1]] = $Matches[2].Trim()
    }
}

$BotToken       = $envVars["SLACK_BOT_TOKEN"]
$ChannelHealth  = $envVars["SLACK_CHANNEL_HEALTH"]
$ChannelApproval = $envVars["SLACK_CHANNEL_APPROVAL"]
$ChannelNotify  = $envVars["SLACK_CHANNEL_NOTIFY"]

if (-not $BotToken) {
    Write-Error "SLACK_BOT_TOKEN not found in .env. Please add it."
    exit 1
}

Write-Host "      SLACK_BOT_TOKEN found." -ForegroundColor Green
Write-Host "      SLACK_CHANNEL_HEALTH   = $ChannelHealth" -ForegroundColor Green
Write-Host "      SLACK_CHANNEL_APPROVAL = $ChannelApproval" -ForegroundColor Green
Write-Host "      SLACK_CHANNEL_NOTIFY   = $ChannelNotify" -ForegroundColor Green

# ── 2. Install Python dependencies ─────────────────────────────────────────
Write-Host "`n[2/3] Installing Python packages..." -ForegroundColor Yellow
pip install mcp httpx --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed. Make sure Python is on your PATH."
    exit 1
}
Write-Host "      Packages installed." -ForegroundColor Green

# ── 3. Update claude_desktop_config.json ───────────────────────────────────
Write-Host "`n[3/3] Registering MCP in Claude config ($ConfigPath)..." -ForegroundColor Yellow

if (Test-Path $ConfigPath) {
    $raw    = Get-Content $ConfigPath -Raw
    $config = $raw | ConvertFrom-Json
} else {
    $config = [PSCustomObject]@{}
}

if (-not ($config.PSObject.Properties.Name -contains "mcpServers")) {
    $config | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
}

$entry = [PSCustomObject]@{
    command = "python"
    args    = @($ServerPath)
    env     = [PSCustomObject]@{
        SLACK_BOT_TOKEN        = $BotToken
        SLACK_CHANNEL_HEALTH   = $ChannelHealth
        SLACK_CHANNEL_APPROVAL = $ChannelApproval
        SLACK_CHANNEL_NOTIFY   = $ChannelNotify
    }
}

$config.mcpServers | Add-Member -MemberType NoteProperty -Name "slack_mcp" -Value $entry -Force

$config | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
Write-Host "      Registered as 'slack_mcp'." -ForegroundColor Green

Write-Host "`n=== Done! Restart Claude desktop to activate the Slack MCP. ===" -ForegroundColor Cyan
