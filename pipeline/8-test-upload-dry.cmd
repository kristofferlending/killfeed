@echo off
title KillFeed - dry run: what would be uploaded tonight?
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% yt_upload.py --dry
echo.
echo Nothing was uploaded - this only shows the queue (shorts from Publish, recaps from Recaps).
pause
