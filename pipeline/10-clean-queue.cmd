@echo off
title KillFeed - clean the upload queue (state.json)
cd /d "%~dp0"
echo Run this AFTER deleting the private/scheduled videos in YouTube Studio.
echo It edits state.json only (backup is made). Nothing is changed on YouTube.
echo.
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% clean_queue.py
echo.
pause
