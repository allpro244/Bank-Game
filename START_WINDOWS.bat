@echo off
title Bank Game
cd /d "%~dp0"
echo Starting Bank Game...
echo.
py run.py
if errorlevel 1 python run.py
echo.
echo The game has stopped. Press any key to close this window.
pause >nul
