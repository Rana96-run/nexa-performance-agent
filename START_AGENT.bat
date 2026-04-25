@echo off
title Qoyod Performance Agent - Launcher
cd /d "%~dp0"

echo ============================================
echo   Qoyod Performance Agent - Starting Up
echo ============================================
echo.

echo [1/3] Starting Reporting Scheduler (BigQuery refresh every 6h)...
start "BQ Reporting Scheduler" cmd /k ".venv\Scripts\python.exe reporting_scheduler.py"
timeout /t 2 /nobreak >nul

echo [2/3] Starting Operational Scheduler (heavy analysis at 03:00 Riyadh)...
start "Operational Scheduler" cmd /k ".venv\Scripts\python.exe operational_scheduler.py"
timeout /t 2 /nobreak >nul

echo [3/3] Starting Slack Listener (@mention bot)...
start "Slack Listener" cmd /k ".venv\Scripts\python.exe slack_listener.py"
timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo   All 3 processes launched in their own windows.
echo ============================================
echo.
echo   Window 1: BQ Reporting Scheduler  (every 6h)
echo   Window 2: Operational Scheduler   (03:00 Riyadh nightly)
echo   Window 3: Slack Listener          (60s poll, @mention bot)
echo.
echo   On-demand run:   .venv\Scripts\python.exe main.py on_demand
echo   Past-due check:  mention @Claude past due in Slack
echo.
echo   This launcher window will close in 5 seconds.
timeout /t 5 /nobreak >nul
exit
