@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
python -m workbench.preflight
pause
