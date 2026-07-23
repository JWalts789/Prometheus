@echo off
REM Start the PROMETHEUS always-on loop (a cycle every PROM_INTERVAL_HOURS, default 6h).
REM This is what the Windows Task Scheduler task launches at logon.
cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PROM_INTERVAL_HOURS=0.5
".\venv\Scripts\python.exe" loop.py
