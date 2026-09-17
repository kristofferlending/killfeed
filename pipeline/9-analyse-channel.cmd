@echo off
title KillFeed - analyse the YouTube channel (read-only)
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% yt_analyse.py
echo.
echo analysis.txt and analysis.json are next to this file. Nothing was changed on YouTube.
pause
