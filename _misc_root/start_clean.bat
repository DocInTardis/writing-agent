@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM One-click: stop old processes + start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_clean.ps1"
echo.
pause
