@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Keep the window open on double-click so users can see errors.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0_misc_root\\start.ps1"
echo.
pause
