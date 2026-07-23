@echo off
REM Start the PROMETHEUS Discord bot (scoped two-way chat in its home channel; no admin).
cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
".\venv\Scripts\python.exe" -m bot.discord_bot
