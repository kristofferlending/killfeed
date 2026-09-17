@echo off
rem Starter KillFeed-boten (velkomst, /setup /faq /download /roadmap, feedback-zip-analyse). La vinduet staa aapent.
rem Forste gang installeres discord.py. Krever bot\secrets.txt.
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% -m pip install --quiet discord.py
%PY% killfeed_bot.py
pause
