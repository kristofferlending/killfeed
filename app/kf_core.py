#!/usr/bin/env python3
"""kf_core.py – KillFeed-kjernen som deles av tray-appen og (senere) nattjobben.

Alt som ikke er GUI ligger her:
  * innstillinger i %APPDATA%\\KillFeed\\settings.json (engangs-veiviser fyller dem ut)
  * hovedbok (ledger.json): hvilke opptak som er klippet, hvilke klipp som finnes og hva de er
  * klokketid-dedup: samme kill fra OBS-replay + Aitum-backtrack -> ett klipp
  * utvalg: multikill/vehicle -> Publiser\\, resten -> Andre\\, reserve hvis en økt ikke gir noe
  * montasje: kronologisk 16:9-sammendrag (min–maks minutter) fra vanlige opptak, rene kutt,
    bygget av treffene som allerede ligger i -auto.json (ingen ny OCR)
  * rydding (valgfritt) av Andre\\ etter N dager – aldri brukerens egne opptak

Ingen opplasting her. Brukeren publiserer fra synkmappa (YouTube-appen på telefonen).
"""
import os, sys, re, json, glob, time, shutil, tempfile, subprocess, datetime

APP = "KillFeed"
VERSION = "0.2-alpha"
CF = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ------------------------------------------------------------------ stier
def appdata_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, APP)
    os.makedirs(d, exist_ok=True)
    return d

def work_dir():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, APP, "work")
    os.makedirs(d, exist_ok=True)
    return d

SETTINGS = os.path.join(appdata_dir(), "settings.json")
LEDGER = os.path.join(appdata_dir(), "ledger.json")
LOGFILE = os.path.join(appdata_dir(), "killfeed.log")
REPORTS = os.path.join(appdata_dir(), "reports")
os.makedirs(REPORTS, exist_ok=True)

def exe_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ logg
_log_hooks = []
def add_log_hook(fn): _log_hooks.append(fn)
def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass
    for h in list(_log_hooks):
        try: h(msg)
        except Exception: pass

# ------------------------------------------------------------------ json
def jload(p, default):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def jsave(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)

# ------------------------------------------------------------------ innstillinger
DEFAULTS = {
    "input_dir": "",                 # der OBS / Aitum / Instant Replay legger opptak
    "extra_input_dirs": [],          # flere opptaksmapper (f.eks. både backtracks og hele opptak)
    "output_dir": "",                # synkmappe: får Publiser\\, Andre\\, Montasje\\
    "style": "center",               # 9:16-stil for 16:9-opptak: center | blur
    "autostart": True,               # snarvei i Startup-mappa
    "watch_interval_s": 60,          # hvor ofte opptaksmappa sjekkes
    "min_file_age_s": 120,           # ikke rør filer som fortsatt skrives
    "pause_while_game_running": True,# ikke OCR mens spillet kjører (CPU)
    "game_process_hint": "wardogs",  # delstreng i prosessnavn
    "shorts": {"fps": 2, "pre": 12, "post": 4, "gap": 12, "min": 18, "max": 40,
               "min_kills": 2, "min_vehicles": 1, "fallback_single_when_empty": True},
    "dedup_seconds": 5,
    "montage": {"enabled": True, "min_minutes": 5, "max_minutes": 10, "pre": 5, "post": 2, "gap": 6,
                "clip_min": 6, "clip_max": 30, "min_kills": 1, "count_vehicles": True, "lookback_days": 14,
                "resolution": "1080p", "label": "recap", "title_prefix": "WARDOGS Daily Recap"},
    "cleanup": {"andre_days": 0},    # 0 = aldri slett noe (alfa-standard)
    "notify": True,
    "setup_done": False,
}

def _merge(d, s):
    out = dict(d)
    for k, v in s.items():
        out[k] = _merge(d[k], v) if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    return out

def load_settings():
    s = _merge(DEFAULTS, jload(SETTINGS, {}))
    if not s.get("setup_done"):
        # gammel alfa lagret innstillinger ved siden av exe-en – ta dem med
        old = jload(os.path.join(exe_dir(), "killfeed_settings.json"), {})
        if old:
            s["input_dir"] = s["input_dir"] or old.get("input_dir", "")
            s["output_dir"] = s["output_dir"] or old.get("output_dir", "")
            s["style"] = old.get("style", s["style"])
    return s

def save_settings(s):
    jsave(SETTINGS, s)

def guess_input_dir():
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Videos", "Wardogs", "02-shorts"), os.path.join(home, "Videos", "Wardogs"),
             os.path.join(home, "Videos", "WARDOGS"), os.path.join(home, "Videos", "NVIDIA", "WARDOGS"),
             os.path.join(home, "Videos", "Medal", "WARDOGS"), os.path.join(home, "Videos", "Captures"), os.path.join(home, "Videos")]
    for c in cands:
        if os.path.isdir(c) and any(glob.glob(os.path.join(c, e)) for e in ("*.mkv", "*.mp4")): return c
    return os.path.join(home, "Videos")

def guess_output_dir():
    home = os.path.expanduser("~")
    for c in ["OneDrive", "Google Drive", "iCloudDrive", "Dropbox"]:
        p = os.path.join(home, c)
        if os.path.isdir(p): return os.path.join(p, APP)
    return os.path.join(home, "Videos", APP)

# ------------------------------------------------------------------ hovedbok
def load_ledger():
    L = jload(LEDGER, {})
    L.setdefault("processed", {})   # kildefil -> {clips, at} | {error, at}
    L.setdefault("clips", {})       # klippnavn -> {status: publiser|andre|duplicate, abs_events, score, kills, vehicles, source, at, path}
    L.setdefault("montages", [])    # [{file, at, from, to, kills, vehicles, seconds, used: [abs_events...]}]
    L.setdefault("sizes", {})       # kildefil -> størrelse ved forrige skann (stabil-sjekk)
    return L

def save_ledger(L): jsave(LEDGER, L)

# ------------------------------------------------------------------ verktøy
def game_running(hint):
    if os.name != "nt" or not hint: return False
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CF, timeout=10)
        return hint.lower() in (r.stdout or "").lower()
    except Exception:
        return False

_CLIP_RE = re.compile(r"-auto\d\d-\d", re.I)
def source_files(dirs, skip_dir=None, depth=2):
    """Opptak i mappene og undermapper (2 nivaa). Hopper over utmappa og ferdige KillFeed-klipp,
    saa brukeren kan peke paa Videos\\ eller Videos\\Wardogs\\ og la den finne alt selv."""
    out = []; skip = os.path.normcase(os.path.abspath(skip_dir)) if skip_dir else None
    for d in dirs:
        if not d or not os.path.isdir(d): continue
        base_depth = os.path.abspath(d).rstrip(os.sep).count(os.sep)
        for root, subdirs, files in os.walk(d):
            r = os.path.normcase(os.path.abspath(root))
            if skip and (r == skip or r.startswith(skip + os.sep)):
                subdirs[:] = []; continue
            if root.count(os.sep) - base_depth >= depth: subdirs[:] = []
            subdirs[:] = [x for x in subdirs if not x.startswith(".") and x.lower() not in ("publiser", "andre", "montasje", "gamle-uten-dedup")]
            for f in files:
                if f.lower().endswith((".mkv", ".mp4", ".mov")) and not _CLIP_RE.search(f):
                    out.append(os.path.join(root, f))
    return sorted(set(out), key=os.path.getmtime)

def ready_sources(s, L):
    """Kildefiler som er nye, gamle nok og har stabil størrelse siden forrige skann."""
    files = source_files([s["input_dir"]] + list(s.get("extra_input_dirs") or []), skip_dir=s.get("output_dir"))
    now = time.time(); ready = []; sizes = L.setdefault("sizes", {})
    for f in files:
        b = os.path.basename(f)
        if b in L["processed"] or f in L["processed"]: continue
        try:
            st = os.stat(f)
        except OSError: continue
        if now - st.st_mtime < s["min_file_age_s"]: sizes[b] = st.st_size; continue
        if sizes.get(b) not in (None, st.st_size):
            sizes[b] = st.st_size; continue           # vokser fortsatt
        sizes[b] = st.st_size
        ready.append(f)
    return ready

def _same(ea, eb, tol):
    return any(abs(x - y) <= tol for x in ea for y in eb)

def _basename_noext(p): return os.path.splitext(os.path.basename(p))[0]

# ------------------------------------------------------------------ shorts: klipp én fil
def process_source(path, s, L, killclip, log=log):
    """Kjør killclip på én kildefil, flytt klippene til Publiser/Andre etter dedup og regler.
    Returnerer liste over (navn, status)."""
    sh = s["shorts"]; wd = work_dir()
    for junk in glob.glob(os.path.join(wd, "*")):
        try: os.remove(junk)
        except OSError: pass
    t0 = time.time()
    try:
        segs = killclip.process(path, wd, fps=sh["fps"], pre=sh["pre"], post=sh["post"], gap=sh["gap"],
                                mn=sh["min"], mx=sh["max"], style=s.get("style", "center"), log=log)
    except Exception as e:
        L["processed"][os.path.basename(path)] = {"error": str(e)[:200], "at": datetime.datetime.now().isoformat()}
        save_ledger(L); log(f"  FEIL {os.path.basename(path)}: {e}")
        return []
    # rapport (treff + segmenter) tas vare på – montasjen bygger på den
    rep = os.path.join(wd, _basename_noext(path) + "-auto.json")
    if os.path.exists(rep): shutil.move(rep, os.path.join(REPORTS, os.path.basename(rep)))
    results = place_clips(segs, wd, s, L, log, killclip)
    L["processed"][os.path.basename(path)] = {"clips": len(segs), "kept": len([r for r in results if r[1] != "duplicate"]),
                                              "at": datetime.datetime.now().isoformat(), "seconds": round(time.time() - t0)}
    save_ledger(L)
    return results

def enrich_from_reports(seg, killclip, tol):
    """Backtracks (9:16) mangler kill-feed-sonen. Finn avstand/offer i rapporter fra 16:9-opptak
    av samme oyeblikk (klokketid), og oppdater tittel/score."""
    if seg.get("kill_details") or not seg.get("abs_events"): return False
    found = []
    for rep in glob.glob(os.path.join(REPORTS, "*-auto.json")):
        for fe in jload(rep, {}).get("feed", []):
            if any(abs(fe["abs"] - e) <= tol for e in seg["abs_events"]) and fe not in found:
                found.append(fe)
    if not found: return False
    seg["kill_details"] = found; seg["max_dist_m"] = max(x["dist_m"] for x in found)
    seg["score"] = seg.get("score", 0) + seg["max_dist_m"] // 100
    seg["title"] = killclip.auto_title(seg.get("kills", 0), 0, seg.get("vehicles", 0), seg.get("money", 0), None, seg["max_dist_m"])
    return True

def qualifies(seg, sh):
    return seg.get("kills", 0) >= sh["min_kills"] or seg.get("vehicles", 0) >= sh["min_vehicles"]

def place_clips(segs, wd, s, L, log=log, killclip=None):
    """Dedup mot hovedboka og innbyrdes (beste først), så Publiser/Andre. Duplikater slettes fra disk."""
    sh = s["shorts"]; tol = s.get("dedup_seconds", 5)
    if killclip:
        for seg in segs:
            if enrich_from_reports(seg, killclip, tol):
                try:
                    with open(os.path.join(wd, os.path.splitext(seg["file"])[0] + ".txt"), "w", encoding="utf-8") as f:
                        f.write(seg["title"] + "\n\n" + ", ".join(f"{x['dist_m']} m {x['victim']}" for x in seg["kill_details"]) + "\n")
                except OSError: pass
    out_pub = os.path.join(s["output_dir"], "Publiser"); out_andre = os.path.join(s["output_dir"], "Andre")
    os.makedirs(out_pub, exist_ok=True); os.makedirs(out_andre, exist_ok=True)
    taken = [(k, v.get("abs_events") or []) for k, v in L["clips"].items() if v.get("status") in ("publiser", "andre") and v.get("abs_events")]
    results = []
    for seg in sorted(segs, key=lambda x: (x.get("score", 0), -x.get("clamped_start", False)), reverse=True):
        name = seg["file"]; src = os.path.join(wd, name)
        ev = seg.get("abs_events") or []
        dup_of = next((k for k, t in taken if ev and _same(ev, t, tol)), None)
        if dup_of:
            for ext in (".mp4", ".json", ".txt"):
                try: os.remove(os.path.splitext(src)[0] + ext)
                except OSError: pass
            L["clips"][name] = {"status": "duplicate", "of": dup_of, "abs_events": ev, "at": datetime.datetime.now().isoformat()}
            results.append((name, "duplicate")); log(f"  duplikat av {dup_of}: {name}")
            continue
        status = "publiser" if qualifies(seg, sh) else "andre"
        dest = os.path.join(out_pub if status == "publiser" else out_andre, name)
        try:
            shutil.move(src, dest)
            txt = os.path.splitext(src)[0] + ".txt"
            if os.path.exists(txt): shutil.move(txt, os.path.splitext(dest)[0] + ".txt")
            js = os.path.splitext(src)[0] + ".json"
            if os.path.exists(js): shutil.move(js, os.path.join(REPORTS, os.path.basename(js)))
        except Exception as e:
            log(f"  FEIL flytting {name}: {e}"); continue
        L["clips"][name] = {"status": status, "abs_events": ev, "score": seg.get("score", 0), "kills": seg.get("kills", 0),
                            "vehicles": seg.get("vehicles", 0), "money": seg.get("money", 0), "source": seg.get("source"),
                            "title": seg.get("title"), "max_dist_m": seg.get("max_dist_m", 0), "victims": [x["victim"] for x in seg.get("kill_details", [])],
                            "path": dest, "at": datetime.datetime.now().isoformat()}
        taken.append((name, ev)); results.append((name, status))
    return results

def promote_fallback(batch_results, s, L, log=log):
    """En økt uten et eneste Publiser-klipp: løft det beste enkeltkillet fra økta så det alltid kommer noe."""
    if not s["shorts"].get("fallback_single_when_empty", True): return None
    if any(st == "publiser" for _, st in batch_results): return None
    cands = [n for n, st in batch_results if st == "andre"]
    if not cands: return None
    best = max(cands, key=lambda n: L["clips"][n].get("score", 0))
    c = L["clips"][best]; dest = os.path.join(s["output_dir"], "Publiser", best)
    try:
        shutil.move(c["path"], dest)
        t = os.path.splitext(c["path"])[0] + ".txt"
        if os.path.exists(t): shutil.move(t, os.path.splitext(dest)[0] + ".txt")
        c["status"] = "publiser"; c["path"] = dest; c["fallback"] = True
        log(f"  ingen multikill i økta – reserve: {best} -> Publiser"); return best
    except Exception as e:
        log(f"  FEIL reserve {best}: {e}"); return None

# ------------------------------------------------------------------ montasje
def _waves(hits, a, b, pred):
    ts = [t for t, kk in hits if a <= t <= b and any(pred(x) for x in kk)]
    n = 0; last = -99
    for t in ts:
        if t - last > 3: n += 1
        last = t
    return n

def _money(hits, a, b):
    m = 0
    for t, kk in hits:
        if a <= t <= b:
            for x in kk:
                mm = re.match(r"\+\$([\d,]+)", x)
                if mm:
                    try: m = max(m, int(mm.group(1).replace(",", "")))
                    except ValueError: pass
    return m

def montage_candidates(s, L, killclip):
    """Segmenter fra 16:9-opptak (rapporter i REPORTS) som ikke er brukt i en montasje før. Kronologisk."""
    m = s["montage"]; tol = s.get("dedup_seconds", 5)
    used = [ev for mg in L["montages"] for ev in mg.get("used", [])]
    cutoff = time.time() - m["lookback_days"] * 86400
    cands = []
    for rep in glob.glob(os.path.join(REPORTS, "*-auto.json")):
        r = jload(rep, {})
        src = r.get("input"); hits = [(float(t), k) for t, k in r.get("hits", [])]
        if not src or not os.path.exists(src) or not hits: continue
        try:
            dur, W, H = killclip.probe(src)
        except Exception: continue
        if H > W: continue                                # bare vanlige 16:9-opptak i montasjen
        t0 = killclip.file_start_epoch(src, dur)
        if t0 < cutoff: continue
        for a, b, kinds in killclip.cluster(hits, dur, m["pre"], m["post"], m["gap"], m["clip_min"], m["clip_max"]):
            kills = _waves(hits, a, b, lambda x: x.startswith("KILLCONFIRMED"))
            veh = _waves(hits, a, b, lambda x: "DESTROYED" in x)
            if kills < m["min_kills"] and not (m.get("count_vehicles", True) and veh): continue
            ev = [round(t0 + t, 1) for t, kk in hits if a <= t <= b]
            if any(_same(ev, u, tol) for u in used): continue
            cands.append({"src": src, "a": a, "b": b, "len": round(b - a, 1), "kills": kills, "vehicles": veh,
                          "money": _money(hits, a, b), "abs": round(t0 + a, 1), "abs_events": ev})
    cands.sort(key=lambda c: c["abs"])
    # innbyrdes dedup (replay + hele opptak av samme øyeblikk): behold den med flest kills
    keep = []
    for c in cands:
        j = next((i for i, k in enumerate(keep) if _same(c["abs_events"], k["abs_events"], tol)), None)
        if j is None: keep.append(c)
        elif (c["kills"], c["vehicles"]) > (keep[j]["kills"], keep[j]["vehicles"]): keep[j] = c
    return keep

def montage_ready(s, L, killclip):
    """True + kandidater hvis det er samlet nok til minst min_minutes."""
    c = montage_candidates(s, L, killclip)
    return sum(x["len"] for x in c) >= s["montage"]["min_minutes"] * 60, c

def build_montage(s, L, killclip, force=False, log=log):
    """Sett sammen kronologisk montasje innenfor min–maks. force=True bygger med det som finnes."""
    m = s["montage"]
    ready, cands = montage_ready(s, L, killclip)
    if not cands: log("Montasje: ingen kvalifiserte klipp ennå."); return None
    if not ready and not force:
        log(f"Montasje: {sum(c['len'] for c in cands)/60:.1f} av {m['min_minutes']} min samlet – venter."); return None
    chosen, total = [], 0.0
    for c in cands:
        if total + c["len"] > m["max_minutes"] * 60: break
        chosen.append(c); total += c["len"]
    if not chosen: return None
    out_dir = os.path.join(s["output_dir"], "Montasje"); os.makedirs(out_dir, exist_ok=True)
    d0 = datetime.datetime.fromtimestamp(chosen[0]["abs"]); d1 = datetime.datetime.fromtimestamp(chosen[-1]["abs"])
    kills = sum(c["kills"] for c in chosen); veh = sum(c["vehicles"] for c in chosen)
    span = f"{d0:%d.%m}" if d0.date() == d1.date() else f"{d0:%d.%m}–{d1:%d.%m}"
    fspan = f"{d0:%Y-%m-%d}" if d0.date() == d1.date() else f"{d0:%Y-%m-%d} til {d1:%m-%d}"
    mm, ss = divmod(int(total), 60)
    label = m.get("label", "recap").strip() or "recap"
    name = f"WARDOGS {label} {fspan}.mp4"
    out = os.path.join(out_dir, name); k = 2
    while os.path.exists(out):                          # to samme dag -> (2), (3) …
        out = os.path.join(out_dir, f"WARDOGS {label} {fspan} ({k}).mp4"); k += 1
    name = os.path.basename(out)
    res = {"1440p": (2560, 1440)}.get(m.get("resolution", "1080p"), (1920, 1080))
    log(f"Montasje: {len(chosen)} klipp, {mm}m{ss:02d}s, {kills} kills, {veh} vehicles -> {name}")
    try:
        _concat(chosen, out, res, killclip)
    except Exception as e:
        log(f"  FEIL montasje: {e}"); return None
    bits = [f"{kills} kill{'s' if kills != 1 else ''}"] + ([f"{veh} vehicle{'s' if veh != 1 else ''} destroyed"] if veh else [])
    title = f"{m.get('title_prefix', 'WARDOGS Daily Recap')} {span} – {', '.join(bits)}"[:100]
    with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as f:
        f.write(title + f"\n\nLengde {mm}:{ss:02d} · {len(chosen)} klipp · {kills} kills · {veh} vehicles\n\n" + "\n".join(f"{datetime.datetime.fromtimestamp(c['abs']):%d.%m %H:%M}  {c['kills']} kills  {os.path.basename(c['src'])}  {c['a']:.0f}-{c['b']:.0f}s" for c in chosen) + "\n")
    L["montages"].append({"file": out, "at": datetime.datetime.now().isoformat(), "from": d0.isoformat(), "to": d1.isoformat(),
                          "kills": kills, "vehicles": veh, "seconds": round(total), "title": title,
                          "used": [c["abs_events"] for c in chosen]})
    save_ledger(L)
    return out

def _concat(chosen, out, res, killclip):
    """Én ffmpeg-kjøring: hvert klipp trimmes (-ss/-t), skaleres til samme størrelse og limes med concat-filteret.
    Bruker faststart så fila kan spilles mens den synkes."""
    W, H = res
    cmd = [killclip.FFMPEG, "-v", "error", "-y"]
    for c in chosen:
        cmd += ["-ss", f"{c['a']:.2f}", "-t", f"{c['len']:.2f}", "-i", c["src"]]
    parts = []
    for i in range(len(chosen)):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60,format=yuv420p[v{i}];"
                     f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    fc = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(len(chosen))) + f"concat=n={len(chosen)}:v=1:a=1[v][a]"
    wm = os.path.join(killclip._appdir(), "watermark.png")
    if os.path.exists(wm) and getattr(sys, "frozen", False):
        cmd += ["-i", wm]; fc += f";[v][{len(chosen)}:v]overlay=W-w-24:H-h-24[vo]"; vmap = "[vo]"
    else:
        vmap = "[v]"
    cmd += ["-filter_complex", fc, "-map", vmap, "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True, creationflags=CF)

# ------------------------------------------------------------------ rydding
def cleanup(s, L, log=log):
    days = s.get("cleanup", {}).get("andre_days", 0)
    if not days: return 0
    n = 0; cutoff = time.time() - days * 86400
    for name, c in list(L["clips"].items()):
        if c.get("status") == "andre" and c.get("path") and os.path.exists(c["path"]) and os.path.getmtime(c["path"]) < cutoff:
            for ext in (".mp4", ".txt"):
                try: os.remove(os.path.splitext(c["path"])[0] + ext); n += 1
                except OSError: pass
            c["status"] = "ryddet"
    if n: log(f"Rydding: fjernet {n} filer fra Andre\\ eldre enn {days} dager."); save_ledger(L)
    return n

# ------------------------------------------------------------------ én full runde
def run_once(s, L, killclip, log=log, progress=None, stop=None):
    """Klipp alt som er klart, dedup, plasser, reserve, montasje. Returnerer oppsummering."""
    files = ready_sources(s, L); save_ledger(L)
    summary = {"sources": len(files), "publiser": [], "andre": [], "duplicate": 0, "montage": None}
    if files: log(f"{len(files)} nye opptak å gå gjennom")
    batch = []
    for n, f in enumerate(files, 1):
        if stop and stop(): log("Stoppet."); break
        if progress: progress(n, len(files), os.path.basename(f))
        log(f"[{n}/{len(files)}] {os.path.basename(f)}")
        for name, st in process_source(f, s, L, killclip, log):
            batch.append((name, st))
    fb = promote_fallback(batch, s, L, log)
    for name, st in batch:
        if name == fb: st = "publiser"
        if st == "publiser": summary["publiser"].append(name)
        elif st == "andre": summary["andre"].append(name)
        else: summary["duplicate"] += 1
    if s["montage"].get("enabled", True):
        summary["montage"] = build_montage(s, L, killclip, log=log)
    cleanup(s, L, log)
    save_ledger(L)
    return summary
