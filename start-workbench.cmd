@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\desktop_launcher.py
) else (
    where py.exe >nul 2>nul
    if errorlevel 1 (
        python scripts\desktop_launcher.py
    ) else (
        py -3 scripts\desktop_launcher.py
    )
)
if errorlevel 1 (
    pause
    exit /b 1
)
