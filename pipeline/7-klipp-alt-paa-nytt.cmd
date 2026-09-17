@echo off
title KillFeed / auto-clips - 7: Klipp alt paa nytt (med dedup)
echo ============================================================
echo  KillFeed / auto-clips - 7: Klipp alt paa nytt (med dedup)
echo ============================================================
echo  Hva: flytter gamle klipp i KillFeed\clips til undermappa gamle-uten-dedup,
echo       nullstiller processed.json og klipper ALLE backtracks paa nytt slik at
echo       hvert klipp faar klokketid (trengs for dedup). Laster IKKE opp.
echo  Tid: ca. 1-2 min per backtrack (79 stk = en drøy time). La vinduet staa.
echo  Etterpaa: nattjobben (eller 5-kjor-naa) planlegger de beste klippene.
echo  Allerede opplastede klipp faar samme filnavn og hoppes over.
echo.
cd /d "%~dp0"
set PY=python
python --version >nul 2>&1 || set PY=py -3
set CLIPS=..\clips
if not exist "%CLIPS%\gamle-uten-dedup" mkdir "%CLIPS%\gamle-uten-dedup"
move /y "%CLIPS%\*.mp4" "%CLIPS%\gamle-uten-dedup\" >nul 2>&1
move /y "%CLIPS%\*.json" "%CLIPS%\gamle-uten-dedup\" >nul 2>&1
move /y "%CLIPS%\*.txt" "%CLIPS%\gamle-uten-dedup\" >nul 2>&1
echo {} > processed.json
echo Gamle klipp flyttet. Starter klipping av alle backtracks ...
echo.
%PY% run_daily.py --no-upload --limit 500
echo.
echo Ferdig. Kjor 5-kjor-naa.cmd for aa planlegge opplasting naa, ellers tar nattjobben det kl 04:00.
pause
