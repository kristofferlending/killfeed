@echo off
title KillFeed / auto-clips - 2: Test klipping
echo ============================================================
echo  KillFeed / auto-clips - 2: Test klipping
echo ============================================================
echo  Hva: sjekker ffmpeg + Tesseract, installerer Google-pakker for Python,
echo       og klipper EN backtrack (01-15-03) til KillFeed\clips som test.
echo  Forventet: en JSON med "kills": 1 og en .mp4 i KillFeed\clips.
echo  Laster IKKE opp noe.
echo.
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PY=python
python --version >nul 2>&1 || set PY=py -3
%PY% --version || (echo FEIL: Python ikke funnet. Kjor 1-installer-tesseract.cmd forst, lukk vinduet og prov igjen. & pause & exit /b 1)

echo ==== Sjekker ffmpeg ====
set "FFMPEG_DIR="
where ffmpeg >nul 2>&1 && (echo ffmpeg funnet paa PATH & goto ffok)
for /f "delims=" %%f in ('dir /s /b "%~dp0ffmpeg\ffprobe.exe" 2^>nul') do (set "FFMPEG_DIR=%%~dpf" & goto ffshow)
for /f "delims=" %%f in ('dir /s /b "%LOCALAPPDATA%\Microsoft\WinGet\Packages\ffprobe.exe" 2^>nul') do (set "FFMPEG_DIR=%%~dpf" & goto ffshow)
echo ffmpeg ikke funnet - laster ned ffmpeg (ca. 100 MB) fra gyan.dev til mappa schedules\ffmpeg ...
if not exist "%~dp0ffmpeg" mkdir "%~dp0ffmpeg"
curl -L -# -o "%~dp0ffmpeg\ffmpeg.zip" https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
tar -xf "%~dp0ffmpeg\ffmpeg.zip" -C "%~dp0ffmpeg"
del "%~dp0ffmpeg\ffmpeg.zip" 2>nul
for /f "delims=" %%f in ('dir /s /b "%~dp0ffmpeg\ffprobe.exe" 2^>nul') do (set "FFMPEG_DIR=%%~dpf" & goto ffshow)
echo FEIL: ffmpeg mangler fortsatt. Last ned https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip manuelt og pakk ut i schedules\ffmpeg
pause
exit /b 1
:ffshow
echo ffmpeg funnet i !FFMPEG_DIR!
:ffok

echo ==== Sjekker Tesseract ====
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version 2>nul | findstr /i tesseract || (echo FEIL: Tesseract ikke funnet i C:\Program Files\Tesseract-OCR. Kjor 1-installer-tesseract.cmd. & pause & exit /b 1)

echo ==== Python-pakker for YouTube-opplasting ====
%PY% -m pip install --quiet google-api-python-client google-auth-oauthlib
echo.
echo ==== Tester klipping paa Backtrack 2026-09-11 01-15-03 (tar 1-3 min) ====
%PY% killclip.py "..\..\short-format\Backtrack WARDOGS 2026-09-11 01-15-03.mkv" "..\clips"
echo.
echo ==== Innhold i KillFeed\clips ====
dir /b "..\clips"
echo.
echo Ser du "kills": 1 over og en .mp4 i lista, virker alt. Neste steg: OAuth (se LES_MEG.md), saa 3-auth-youtube.cmd
pause
