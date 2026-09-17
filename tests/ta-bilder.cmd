@echo off
setlocal enabledelayedexpansion
title KillFeed - ta enkeltbilder rundt kills (for aa kalibrere kill-feed-sonen)
rem Hva denne gjor: plukker ut PNG-bilder ved gitte sekunder fra to opptak (Replay 16:9 og Backtrack 9:16)
rem og legger dem i killfeed\tests\frames\. Claude henter bildene og finner hvor den ekte kill-feeden
rem (vaapen, avstand, navn) ligger paa skjermen. Sletter ingenting.
cd /d "%~dp0"
set OUT=frames
if not exist "%OUT%" mkdir "%OUT%"
set FF=
for /f "delims=" %%f in ('dir /s /b "..\tools\ffmpeg\ffmpeg.exe" 2^>nul') do set FF=%%f
if "%FF%"=="" for /f "delims=" %%f in ('dir /s /b "C:\Users\krist\Videos\Wardogs\KillFeed\schedules\ffmpeg\ffmpeg.exe" 2^>nul') do set FF=%%f
if "%FF%"=="" (echo FEIL: fant ikke ffmpeg.exe & pause & exit /b 1)

set R=C:\Users\krist\Videos\Wardogs\full-format\Replay WARDOGS 2026-09-12 10-10-10.mkv
set B=C:\Users\krist\Videos\Wardogs\short-format\Backtrack WARDOGS 2026-09-12 10-10-10.mkv
rem Kill 1 ca 59 s, kill 2 ca 111.5 s (fra OCR paa backtracken). Tar bilder litt for og etter.
for %%t in (57 58 59 60 61 62 110 111 112 113 114) do (
  echo Replay    %%t s
  "%FF%" -v error -y -ss %%t -i "%R%" -frames:v 1 "%OUT%\replay-%%t.png"
  echo Backtrack %%t s
  "%FF%" -v error -y -ss %%t -i "%B%" -frames:v 1 "%OUT%\backtrack-%%t.png"
)
echo.
echo Ferdig. Bildene ligger i %CD%\%OUT%  - si fra til Claude.
pause
