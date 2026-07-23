@echo off
REM Run a single PROMETHEUS self-edit cycle (study -> author -> grow -> eval -> gate -> log).
cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
".\venv\Scripts\python.exe" cycle.py
