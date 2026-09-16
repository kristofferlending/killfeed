@echo off
title KillFeed / auto-clips - 4: Registrer nattjobben
echo ============================================================
echo  KillFeed / auto-clips - 4: Registrer nattjobben
echo ============================================================
echo  Hva: lager planlagt oppgave "WARDOGS auto-clips" som kjorer run_daily.py
echo       hver natt kl. 04:00 og 20 min etter paalogging.
echo  Faar du Access is denied: hoyreklikk -^> Kjor som administrator.
echo.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File install_task.ps1
echo.
echo Sjekk: Oppgaveplanlegging skal naa ha "WARDOGS auto-clips" (04:00 daglig + 20 min etter paalogging).
pause
