@echo off
title KillFeed / auto-clips - 5: Kjor hele loypa NAA
echo ============================================================
echo  KillFeed / auto-clips - 5: Kjor hele loypa NAA
echo ============================================================
echo  Steg 1: klipper nye backtracks i 02-shorts -^> 05-auto-clips (1-2 min per stk).
echo  Steg 2: laster opp nye klipp til YouTube som PRIVATE, beste score forst,
echo          maks 6 per kjoring (kvote). Klipp under score-terskel blir liggende.
echo  Etterpaa: YouTube Studio -^> Innhold -^> filter Privat -^> publiser/planlegg.
echo.
cd /d "%~dp0"
title WARDOGS auto-clips - kjor naa
set PY=python
python --version 1>nul 2>nul || set PY=py -3
set N=
set /p N="Hvor mange backtracks skal klippes naa? (Enter = alle, ca. 2 min per stk): "
if "%N%"=="" (
  %PY% run_daily.py
) else (
  %PY% run_daily.py --limit %N%
)
echo.
echo Ferdig. Se run_daily.log for detaljer, og 05-auto-clips for klippene.
pause
