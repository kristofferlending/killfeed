"""Leser bot/secrets.txt (gitignored). Brukes av setup_server.py og killfeed_bot.py."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
def load():
    kv = {}
    p = os.path.join(HERE, "secrets.txt")
    if not os.path.exists(p):
        raise SystemExit("Mangler bot\\secrets.txt – se malen i repoet.")
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); kv[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID"):
        if not kv.get(k): raise SystemExit(f"{k} er tom i bot\\secrets.txt")
    return kv
