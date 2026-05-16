@echo off
:: BLACK Launcher for Windows
cd /d "%~dp0"

:: Load .env if present
if exist .env (
  for /f "tokens=1,2 delims==" %%a in (.env) do (
    set %%a=%%b
  )
)

echo Starting BLACK...
python black.py
pause
