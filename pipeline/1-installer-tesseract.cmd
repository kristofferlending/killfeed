@echo off
title KillFeed / auto-clips - 1: Engangsinstallasjon
echo ============================================================
echo  KillFeed / auto-clips - 1: Engangsinstallasjon
echo ============================================================
echo  Hva: installerer Python 3.12, ffmpeg og Tesseract OCR via winget.
echo  Hvorfor: killclip.py trenger ffmpeg (video) og Tesseract (lese kill-feeden).
echo  Naar: bare forste gang. Er alt installert fra for, hopper winget over.
echo  Svar Ja paa UAC-sporsmaal. Lukk vinduet etterpaa og kjor 2-test-klipping.
echo.
setlocal
echo ==== 1/4  Python 3.12 (hopper over hvis den finnes) ====
winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --override "/passive PrependPath=1 Include_launcher=1 Include_test=0"
echo.
echo ==== 2/4  ffmpeg (Gyan.FFmpeg via winget) ====
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
echo.
echo ==== 3/4  Tesseract OCR (svar Ja paa UAC-sporsmaalet) ====
winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
echo.
echo ==== 4/4  Sjekk ====
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version 2>nul | findstr /i tesseract || echo FEIL: Tesseract ikke funnet - installer manuelt fra https://github.com/UB-Mannheim/tesseract/wiki
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (echo ffmpeg OK) else (where ffmpeg >nul 2>&1 && echo ffmpeg OK || echo FEIL: ffmpeg ikke funnet)
echo.
echo VIKTIG: Lukk dette vinduet, og kjor deretter 2-test-klipping.cmd (nytt vindu trengs for at PATH skal oppdateres).
pause
