@echo off
title KillFeed / auto-clips - 3: YouTube-innlogging (engang)
echo ============================================================
echo  KillFeed / auto-clips - 3: YouTube-innlogging (engang)
echo ============================================================
echo  Hva: aapner nettleseren for Google-innlogging og lagrer token.json.
echo  Krever client_secret.json i denne mappa.
echo  Velg ThatsBonkers-kanalen. Alt logges til auth.log. Laster IKKE opp noe.
echo.
cd /d "%~dp0"
echo ==== 3-auth-youtube %date% %time% ==== > auth.log
set PY=python
python --version >> auth.log 2>&1 || set PY=py -3
if not exist client_secret.json (
  echo Mangler client_secret.json i denne mappa. >> auth.log
  type auth.log
  pause
  exit /b 1
)
echo Starter innlogging - nettleseren skal aapne seg ... >> auth.log
%PY% yt_upload.py --auth --dry >> auth.log 2>&1
echo Ferdig, exit code %errorlevel% >> auth.log
type auth.log
echo.
echo (Alt over er ogsaa lagret i auth.log)
pause
