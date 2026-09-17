@echo off
rem Installerer MCP-biblioteket og registrerer KillFeed-Discord-serveren i Claude-appen.
rem Etterpaa: start Claude-appen paa nytt. Claude i Cowork faar da verktoy for aa lese/skrive paa Discord-serveren.
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% -m pip install --quiet "mcp[cli]"
%PY% -c "import kf_secrets; kf_secrets.load(); print('secrets.txt OK')"
%PY% install_mcp.py
pause
