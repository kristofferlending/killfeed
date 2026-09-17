"""kf_bridge.py – the nightly job's link to the KillFeed core.

The nightly job no longer has its own clipping logic: it uses kf_core (same settings, same ledger as the
tray app), uploads shorts from <output>\\Publish and recaps from <output>\\Recaps.
kf_core.py + killclip.py must be next to this file (deploy copy) or in ..\\app (repo).
"""
import os, sys, json, ctypes

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "..", "app")):
    if os.path.exists(os.path.join(p, "kf_core.py")) and p not in sys.path: sys.path.insert(0, p)
import kf_core as C          # noqa: E402
import killclip              # noqa: E402

def settings():
    s = C.load_settings()
    if not s.get("setup_done"):
        raise SystemExit("KillFeed is not set up yet – start KillFeed (dev-run.cmd / KillFeed.exe) and finish the wizard first.")
    return s

def ledger(): return C.load_ledger()

def publish_dir(s): return os.path.join(s["output_dir"], "Publish")
def recaps_dir(s): return os.path.join(s["output_dir"], "Recaps")

def app_running():
    """True if the KillFeed tray app holds its single-instance mutex (then it clips by itself)."""
    if os.name != "nt": return False
    try:
        h = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KillFeedAlphaMutex")
        running = ctypes.windll.kernel32.GetLastError() == 183
        if h: ctypes.windll.kernel32.CloseHandle(h)
        return running
    except Exception:
        return False

def _load(p):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return {}

def clip_meta(path, L):
    """kills/vehicles/money/score/abs_events/title/clamped_start for a short in Publish.
    Sources, in order: sidecar json next to the file, the copy in %APPDATA%\\KillFeed\\reports, the ledger."""
    name = os.path.basename(path); stem = os.path.splitext(name)[0]
    m = _load(os.path.splitext(path)[0] + ".json") or _load(os.path.join(C.REPORTS, stem + ".json"))
    led = L["clips"].get(name, {})
    out = dict(led); out.update({k: v for k, v in m.items() if v not in (None, "", [])})
    if not out.get("title"):
        txt = os.path.splitext(path)[0] + ".txt"
        try: out["title"] = open(txt, encoding="utf-8").readline().strip()
        except Exception: pass
    return out

def recap_meta(path, L):
    """Title + description lines for a recap in Recaps (from the .txt KillFeed wrote, else the ledger)."""
    name = os.path.basename(path); title, body = "", ""
    try:
        lines = open(os.path.splitext(path)[0] + ".txt", encoding="utf-8").read().splitlines()
        title = lines[0].strip() if lines else ""; body = "\n".join(lines[2:]).strip()
    except Exception: pass
    if not title:
        for mo in L.get("montages", []):
            if os.path.basename(mo.get("file", "")) == name: title = mo.get("title", ""); break
    return title or os.path.splitext(name)[0], body
