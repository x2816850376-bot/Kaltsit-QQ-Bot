@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-semantic.ps1"
pause
