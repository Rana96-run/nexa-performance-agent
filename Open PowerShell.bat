@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM Open PowerShell — generic dev shell for one-off scripts.
REM
REM Opens a PowerShell window in this folder with the venv activated and
REM .env vars loaded, so commands like:
REM     python scripts/whatever.py
REM     python -m collectors.google_ads_bq
REM "just work" without re-configuring auth.
REM ─────────────────────────────────────────────────────────────────────────
TITLE Nexa Dev Shell

cd /d "%~dp0"

REM If a venv exists, build a startup command that activates it and loads .env;
REM then drop the user at an interactive prompt with `-NoExit`.
IF EXIST ".venv\Scripts\Activate.ps1" (
    powershell -NoExit -ExecutionPolicy Bypass -Command ^
        "& { . .\.venv\Scripts\Activate.ps1; if (Test-Path .env) { Get-Content .env | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { $kv = $_ -split '=', 2; if ($kv.Length -eq 2) { [Environment]::SetEnvironmentVariable($kv[0].Trim(), $kv[1].Trim(), 'Process') } } }; Write-Host 'Nexa dev shell ready. Run: python scripts\\whatever.py' -ForegroundColor Cyan }"
) ELSE (
    powershell -NoExit -ExecutionPolicy Bypass -Command ^
        "& { if (Test-Path .env) { Get-Content .env | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { $kv = $_ -split '=', 2; if ($kv.Length -eq 2) { [Environment]::SetEnvironmentVariable($kv[0].Trim(), $kv[1].Trim(), 'Process') } } }; Write-Host 'Nexa dev shell ready (no venv).' -ForegroundColor Yellow }"
)
