@echo off
setlocal
title KillFeed - bygg en-fils alfa (0.2: tray, autopilot, recap)
cd /d "%~dp0.."
rem Kjores fra repoets build\-mappe; jobber fra repo-roten. Kildekode i app\, ffmpeg hentes fra
rem tools\ffmpeg hvis den finnes (gitignored), ellers fra Kristoffers Wardogs\KillFeed\schedules\ffmpeg.
set FFSRC=tools\ffmpeg
if not exist "%FFSRC%" set FFSRC=C:\Users\krist\Videos\Wardogs\KillFeed\schedules\ffmpeg
set PY=python
python --version 1>nul 2>nul || set PY=py -3

echo ==== 1/3 PyInstaller ====
%PY% -m pip install --quiet pyinstaller pystray pillow winotify

echo ==== 2/3 Samler ffmpeg og Tesseract i build\tools ====
if exist build\tools rmdir /s /q build\tools
mkdir build\tools\ffmpeg
for /f "delims=" %%f in ('dir /s /b "%FFSRC%\ffmpeg.exe" 2^>nul') do copy /y "%%f" "build\tools\ffmpeg\" >nul
for /f "delims=" %%f in ('dir /s /b "%FFSRC%\ffprobe.exe" 2^>nul') do copy /y "%%f" "build\tools\ffmpeg\" >nul
if not exist "build\tools\ffmpeg\ffmpeg.exe" (echo FEIL: fant ikke ffmpeg.exe i %FFSRC% - legg gyan.dev-essentials i tools\ffmpeg & pause & exit /b 1)
xcopy /e /i /q /y "C:\Program Files\Tesseract-OCR" "build\tools\tesseract" >nul
if not exist "build\tools\tesseract\tesseract.exe" (echo FEIL: fant ikke Tesseract & pause & exit /b 1)
rem dropp det vi ikke trenger (holder exe-en mindre)
if exist "build\tools\tesseract\doc" rmdir /s /q "build\tools\tesseract\doc"
if exist "build\tools\tesseract\uninstall.exe" del /q "build\tools\tesseract\uninstall.exe"
for %%f in ("build\tools\tesseract\tessdata\*.traineddata") do (
  if /i not "%%~nxf"=="eng.traineddata" if /i not "%%~nxf"=="osd.traineddata" del /q "%%f"
)

echo ==== 3/3 Bygger KillFeed.exe (en fil, tar 2-5 min) ====
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name KillFeed ^
  --add-data "build\tools\ffmpeg;ffmpeg" --add-data "build\tools\tesseract;tesseract" ^
  --add-data "app\watermark.png;." --add-data "app\killclip.py;." --add-data "app\kf_core.py;." --add-data "app\killfeed.png;." --icon "app\killfeed.ico" ^
  --hidden-import pystray._win32 --hidden-import PIL.Image --hidden-import winotify --paths app app\killfeed_app.py
if errorlevel 1 (echo FEIL under bygging & pause & exit /b 1)
copy /y docs\README-ALPHA.txt dist\README.txt >nul
for %%A in (dist\KillFeed.exe) do echo Ferdig: %%~fA (%%~zA byte)
echo Send dist\KillFeed.exe (+ gjerne LES_MEG.txt). Forste start tar 5-10 s (pakker ut i temp).
pause
