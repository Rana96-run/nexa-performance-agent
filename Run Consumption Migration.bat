@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM Run Consumption Migration
REM ─────────────────────────────────────────────────────────────────────────
REM One-off: extends agent_activity_log with tokens / cost / api_calls /
REM bq_bytes_scanned columns and creates v_agent_consumption_daily view.
REM Idempotent — safe to re-run.
REM
REM Loads .env from this folder so BQ_PROJECT_ID and
REM GOOGLE_APPLICATION_CREDENTIALS are picked up.
REM ─────────────────────────────────────────────────────────────────────────
TITLE Consumption Migration

REM Move to the directory where this .bat file lives (project root)
cd /d "%~dp0"

REM Activate venv if it exists (matches the pattern used by Start Agent)
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

REM Load .env into the current process so python sees the BQ creds
IF EXIST ".env" (
    FOR /F "usebackq tokens=1,* delims==" %%A IN (".env") DO (
        IF NOT "%%A"=="" IF NOT "%%A:~0,1"=="#" SET "%%A=%%B"
    )
)

echo.
echo ============================================================
echo   Running consumption-tracking migration...
echo ============================================================
echo.

python scripts\run_consumption_migration.py

echo.
echo ============================================================
echo   Done. Press any key to close this window.
echo ============================================================
pause >nul
