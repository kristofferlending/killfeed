"""Registrerer killfeed_mcp.py i Claude-appen (claude_desktop_config.json). Tar backup forst. Trygg aa kjore flere ganger."""
import os, sys, json, shutil, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude_desktop_config.json")
os.makedirs(os.path.dirname(cfg), exist_ok=True)
data = {}
if os.path.exists(cfg):
    shutil.copy(cfg, cfg + f".bak-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    try: data = json.load(open(cfg, encoding="utf-8"))
    except Exception: data = {}
py = sys.executable.replace("pythonw.exe", "python.exe")
data.setdefault("mcpServers", {})["killfeed-discord"] = {"command": py, "args": [os.path.join(HERE, "killfeed_mcp.py")]}
json.dump(data, open(cfg, "w", encoding="utf-8"), indent=2)
print("Registrert i", cfg)
print("Start Claude-appen paa nytt. Serveren heter killfeed-discord.")
