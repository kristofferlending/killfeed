@echo off
rem Setter opp kanaler og festede innlegg paa KillFeed-serveren. Trygg aa kjore flere ganger.
rem Krever bot\secrets.txt med DISCORD_BOT_TOKEN og DISCORD_GUILD_ID, og at boten er invitert med Manage Channels.
cd /d "%~dp0"
set PY=python
python --version 1>nul 2>nul || set PY=py -3
%PY% setup_server.py
pause
