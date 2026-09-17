@echo off
title KillFeed - deploy nightly job
rem Copies the nightly job + core from the repo to the schedules folder (keeps config.json, state.json, secrets).
set DST=%USERPROFILE%\Videos\Wardogs\KillFeed\schedules
if not exist "%DST%" mkdir "%DST%"
cd /d "%~dp0"
for %%f in (run_daily.py yt_upload.py kf_bridge.py install_task.ps1 config.example.json 8-test-upload-dry.cmd yt_analyse.py 9-analyse-channel.cmd clean_queue.py 10-clean-queue.cmd) do copy /y "%%f" "%DST%\" >nul
for %%f in (kf_core.py killclip.py) do copy /y "..\app\%%f" "%DST%\" >nul
if not exist "%DST%\config.json" copy /y config.example.json "%DST%\config.json" >nul
echo Deployed to %DST%
echo Old keys in config.json (backtracks_dir, clips_dir, extra_source_dirs, killclip) are ignored now - see config.example.json.
pause
