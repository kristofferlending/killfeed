@echo off
rem Kjor KillFeed rett fra kildekoden (ingen bygging). Bruk denne under utvikling; build\build_onefile.cmd
rem bare naar en exe skal sendes til noen. Forste gang: pip-pakkene installeres automatisk.
rem ffmpeg: legges i tools\ffmpeg (gitignored). Finnes den ikke der, brukes Wardogs\KillFeed\schedules\ffmpeg.
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% -m pip install --quiet pystray pillow winotify
set FFMPEG_DIR=
for /f "delims=" %%f in ('dir /s /b "tools\ffmpeg\ffmpeg.exe" 2^>nul') do set FFMPEG_DIR=%%~dpf
if "%FFMPEG_DIR%"=="" for /f "delims=" %%f in ('dir /s /b "%USERPROFILE%\Videos\Wardogs\KillFeed\schedules\ffmpeg\ffmpeg.exe" 2^>nul') do set FFMPEG_DIR=%%~dpf
if "%FFMPEG_DIR%"=="" (echo FEIL: fant ikke ffmpeg.exe. Pakk ut gyan.dev-essentials i tools\ffmpeg & pause & exit /b 1)
echo ffmpeg: %FFMPEG_DIR%
%PY% app\killfeed_app.py
if errorlevel 1 pause
