@echo off
title KillFeed / auto-clips - 6: Test offentlig publisering
echo ============================================================
echo  KillFeed / auto-clips - 6: Test offentlig publisering
echo ============================================================
echo  Hva: laster opp ETT ferdig klipp (beste score) med innstillingene
echo       i config.json (privacy=public, planlagt kl 17:00/21:00).
echo  Hvorfor: Google laaser ofte opplastinger fra u-verifiserte apper
echo       til privat. Denne testen viser hva YouTube faktisk svarte.
echo  Sjekk etterpaa i YouTube Studio: staar det "Planlagt" er alt OK.
echo       Staar det "Privat" uten dato, maa vi soke om API-audit.
echo.
cd /d "%~dp0"
set PY=python
python --version >nul 2>&1 || set PY=py -3
%PY% yt_upload.py --max 1
echo.
pause
