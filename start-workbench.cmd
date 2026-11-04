@echo off
setlocal
cd /d "%~dp0"
python -m workbench.server --port 8768
if errorlevel 1 pause
