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
VERSION = "0.4-alpha"
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

def clean_work():
    """Tøm arbeidsmappa (halvferdige klipp/rapporter). Kalles ved avslutning og ved start."""
    n = 0
    for f in glob.glob(os.path.join(work_dir(), "*")):
        try: os.remove(f); n += 1
        except OSError: pass
    return n

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
    "vertical_dir": "",              # valgfri: mappe med ferdig 9:16-opptak (Aitum Vertical o.l.)
    "prefer_vertical": True,         # samme kill i 9:16 og 16:9 -> behold 9:16 som short (ferdig formatert)
    "output_dir": "",                # synkmappe: får Publish\\, Other\\, Recaps\\
    "style": "center",               # 9:16-stil for 16:9-opptak: center | blur
    "autostart": True,               # snarvei i Startup-mappa
    "watch_interval_s": 60,          # hvor ofte opptaksmappa sjekkes
    "min_file_age_s": 120,           # ikke rør filer som fortsatt skrives
    "pause_while_game_running": True,# ikke OCR mens spillet kjører (CPU)
    "game_process_hint": "wardogs",  # delstreng i prosessnavn
    "shorts": {"fps": 2, "pre": 8, "post": 3, "gap": 12, "min": 15, "max": 30,   # analysis 17.09: viewers watch ~17-23 s whatever the length -> keep shorts short
               "min_kills": 2, "min_vehicles": 1, "max_kill_span": 10, "fallback_single_when_empty": True,
               "lonely_gap_s": 15},   # hopp over klipp med ett ensomt kill og ingenting innen N sek (0 = av)
    "dedup_seconds": 5,
    "make_shorts": True,             # lag shorts i det hele tatt (recap-only er mulig)
    "montage": {"enabled": True, "auto": True, "min_minutes": 5, "max_minutes": 10, "pre": 5, "post": 2, "gap": 6,
                "clip_min": 6, "clip_max": 30, "min_kills": 1, "count_vehicles": True, "lookback_days": 14,
                "resolution": "1080p", "label": "recap", "title_prefix": "WARDOGS Daily Recap"},
    "cleanup": {"andre_days": 0,                 # 0 = aldri slett noe i Other\\ (alfa-standard)
                "delete_source_after_clip": False,  # slett selve opptaket naar det er ferdig klippet
                "keep_source_for_recap": True,      # ... men vent til killene er brukt i en recap
                "recap_bank": True},                # ... eller: ta vare paa recap-bitene, saa trengs ikke opptaket
    "clip_browser": True,            # skriv clips.html i utmappa (bla gjennom klippene i nettleseren)
    "notify": True,
    "discord_invite": "https://discord.gg/YSRt9t7gq",   # KillFeed-serveren: #feedback, #showcase, #setup-help
    "update_url": "https://github.com/kristofferlending/killfeed/releases",   # "Check for updates" i Advanced
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
    cands = [os.path.join(home, "Videos", "Wardogs"), os.path.join(home, "Videos", "WARDOGS"),
             os.path.join(home, "Videos", "WARDOGS"), os.path.join(home, "Videos", "NVIDIA", "WARDOGS"),
             os.path.join(home, "Videos", "Medal", "WARDOGS"), os.path.join(home, "Videos", "Captures"), os.path.join(home, "Videos")]
    for c in cands:
        if os.path.isdir(c) and source_files([c]): return c
    return os.path.join(home, "Videos")

def guess_output_dir():
    home = os.path.expanduser("~")
    for c in ["OneDrive", "Google Drive", "iCloudDrive", "Dropbox"]:
        p = os.path.join(home, c)
        if os.path.isdir(p): return os.path.join(p, APP)
    w = os.path.join(home, "Videos", "Wardogs")
    return os.path.join(w if os.path.isdir(w) else os.path.join(home, "Videos"), APP)

# ------------------------------------------------------------------ første-kjøring-sjekk
def preflight(s, killclip):
    """Returnerer liste med problemer i klartekst (tom = alt ok)."""
    probs = []
    for exe, what in ((getattr(killclip, "FFMPEG", ""), "ffmpeg"), (getattr(killclip, "FFPROBE", ""), "ffprobe"), (getattr(killclip, "TESS", ""), "Tesseract")):
        if not exe or (os.sep in str(exe) and not os.path.exists(exe)):
            probs.append(f"{what} was not found. The built exe bundles it – please download KillFeed again. (Running from source: see dev-run.cmd.)")
    if not s.get("input_dir") or not os.path.isdir(s["input_dir"]):
        probs.append(f"Recordings folder does not exist: {s.get('input_dir')}. Pick the right folder under Settings.")
    out = s.get("output_dir") or ""
    try:
        os.makedirs(out, exist_ok=True)
        t = os.path.join(out, ".killfeed-write-test"); open(t, "w").write("ok"); os.remove(t)
    except Exception as e:
        probs.append(f"Cannot write to the output folder {out}: {e}. Pick another folder under Settings.")
    try:
        free = shutil.disk_usage(out if os.path.isdir(out) else os.path.expanduser("~")).free
        if free < 5 * 1024**3: probs.append(f"Low disk space: {free/1024**3:.1f} GB free. KillFeed needs at least 5 GB for clips and work files.")
    except Exception: pass
    return probs

def rotate_logs(max_bytes=5_000_000, report_days=60):
    """Hold loggen under max_bytes (beholder siste halvdel) og fjern rapporter eldre enn report_days."""
    try:
        if os.path.exists(LOGFILE) and os.path.getsize(LOGFILE) > max_bytes:
            with open(LOGFILE, "rb") as f: f.seek(-max_bytes // 2, 2); tail = f.read()
            with open(LOGFILE, "wb") as f: f.write(b"... (log rotated)\n" + tail)
    except Exception: pass
    cutoff = time.time() - report_days * 86400
    for rep in glob.glob(os.path.join(REPORTS, "*.json")):
        try:
            if os.path.getmtime(rep) < cutoff: os.remove(rep)
        except OSError: pass

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
            subdirs[:] = [x for x in subdirs if not x.startswith(".") and x.lower() not in ("publish", "other", "recaps", "clips", "schedules", "publiser", "andre", "montasje", "gamle-uten-dedup")]
            for f in files:
                if f.lower().endswith((".mkv", ".mp4", ".mov")) and not _CLIP_RE.search(f):
                    out.append(os.path.join(root, f))
    return sorted(set(out), key=os.path.getmtime)

def src_key(path):
    """The ledger key for a recording. Full path, not the file name: OBS and Aitum Vertical use the same
    naming scheme, so "2026-09-28 20-15-01.mkv" routinely exists in both the full-format and the vertical
    folder. Keyed by name they collapse into one entry - the second is never clipped, and the cleanup
    would look up the wrong entry and delete a recording it never processed."""
    return os.path.normcase(os.path.abspath(path))

def ready_sources(s, L):
    """Kildefiler som er nye, gamle nok og har stabil størrelse siden forrige skann."""
    files = source_files([s["input_dir"], s.get("vertical_dir") or ""] + list(s.get("extra_input_dirs") or []), skip_dir=s.get("output_dir"))
    now = time.time(); ready = []; sizes = L.setdefault("sizes", {})
    for f in files:
        b = os.path.basename(f)
        # b is the old key shape - honoured so an existing ledger is not re-clipped from scratch
        if src_key(f) in L["processed"] or b in L["processed"] or f in L["processed"]: continue
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
def process_source(path, s, L, killclip, log=log, stop=None):
    """Kjør killclip på én kildefil, flytt klippene til Publiser/Andre etter dedup og regler.
    Returnerer liste over (navn, status)."""
    sh = s["shorts"]; wd = work_dir()
    for junk in glob.glob(os.path.join(wd, "*")):
        try: os.remove(junk)
        except OSError: pass
    t0 = time.time()
    try:
        segs = killclip.process(path, wd, fps=sh["fps"], pre=sh["pre"], post=sh["post"], gap=sh["gap"],
                                mn=sh["min"], mx=sh["max"], style=s.get("style", "center"),
                                lonely_gap=sh.get("lonely_gap_s", 0) or 0, log=log)
    except Exception as e:
        if stop and stop():                       # aborted by the user: not an error, leave the file for next time
            log(f"  Aborted {os.path.basename(path)} – will be clipped next time."); return []
        msg = str(e)
        if "CalledProcessError" in type(e).__name__ or "ffmpeg" in msg.lower():
            hint = "ffmpeg could not read the file – is the recording finished writing, or damaged? Try playing it."
        elif "tesseract" in msg.lower():
            hint = "Tesseract (text reading) failed – the built exe bundles it; please download KillFeed again."
        elif "No space left" in msg or "ENOSPC" in msg:
            hint = "The disk is full."
        else:
            hint = msg[:160]
        L["processed"][src_key(path)] = {"file": os.path.basename(path), "error": hint,
                                         "at": datetime.datetime.now().isoformat()}
        save_ledger(L); log(f"  Skipped {os.path.basename(path)}: {hint}")
        return []
    # rapport (treff + segmenter) tas vare på – montasjen bygger på den
    rep = os.path.join(wd, _basename_noext(path) + "-auto.json")
    if os.path.exists(rep):
        filed = os.path.join(REPORTS, os.path.basename(rep))
        shutil.move(rep, filed)
        # recap-banken: smaa 16:9-biter, saa recapen overlever at opptaket slettes
        if s.get("cleanup", {}).get("recap_bank", True) and s["montage"].get("enabled", True):
            try: bank_segments(s, filed, killclip, log)
            except Exception as e: log(f"  recap bank failed: {e}")
    junk = [x for x in segs if not x.get("kills") and not x.get("vehicles")]       # bare assist/penger: ikke verdt en short
    for seg in junk:
        for ext in (".mp4", ".json", ".txt"):
            try: os.remove(os.path.join(wd, os.path.splitext(seg["file"])[0] + ext))
            except OSError: pass
    if junk: log(f"  {len(junk)} clip(s) without a kill/vehicle dropped (assist only)")
    segs = [x for x in segs if x not in junk]
    if not s.get("make_shorts", True):
        for seg in segs:                                  # recap-only: rapporten er tatt vare paa, selve shortsene kastes
            for ext in (".mp4", ".json", ".txt"):
                try: os.remove(os.path.join(wd, os.path.splitext(seg["file"])[0] + ext))
                except OSError: pass
        segs = []
    results = place_clips(segs, wd, s, L, log, killclip)
    L["processed"][src_key(path)] = {"file": os.path.basename(path), "hits": len(getattr(killclip, "_last_hits", []) or []),
                                     "clips": len(segs), "kept": len([r for r in results if r[1] != "duplicate"]),
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
    seg["title"] = killclip.auto_title(seg.get("solo_kills", seg.get("kills", 0)), 0, seg.get("vehicles", 0), seg.get("money", 0), None, seg["max_dist_m"])
    return True

def _merge_into_kept(kept, seg, killclip, log=log):
    """A duplicate carries information the kept clip may lack (the 16:9 sees the kill feed and often the vehicle
    text that the 9:16 crop misses). Take the richer counts, distance and victims, and rewrite the kept title/.txt."""
    if not kept or not killclip: return False
    changed = False
    for k in ("kills", "vehicles", "money", "max_dist_m"):
        if seg.get(k, 0) > kept.get(k, 0): kept[k] = seg[k]; changed = True
    vic = [x["victim"] for x in seg.get("kill_details", []) if x.get("victim")]
    if vic and len(vic) > len(kept.get("victims") or []): kept["victims"] = vic; changed = True
    if not changed: return False
    kept["title"] = killclip.auto_title(kept.get("solo_kills", kept.get("kills", 0)), 0, kept.get("vehicles", 0), kept.get("money", 0), None, kept.get("max_dist_m", 0))
    kept["score"] = killclip.clip_score(killclip.solo_kills_of(kept), kept.get("vehicles", 0), kept.get("max_dist_m", 0), kept.get("len", 0))
    p = kept.get("path", "")
    if p:
        try:
            with open(os.path.splitext(p)[0] + ".txt", "w", encoding="utf-8") as f:
                f.write(kept["title"] + "\n\n" + ", ".join(f"{x} " for x in kept.get("victims", [])).strip() + "\n")
        except OSError: pass
    log(f"  kept clip updated from duplicate: {kept['title']}"); return True

def qualifies(seg, sh):
    """A vehicle kill carries a clip on its own. Kills have to be a burst: two kills half a minute
    apart make a long clip where nothing happens in between, which is the kind nobody watches."""
    if seg.get("vehicles", 0) >= sh["min_vehicles"]: return True
    if seg.get("kills", 0) < sh["min_kills"]: return False
    ev = sorted(seg.get("abs_events") or [])
    span = (ev[-1] - ev[0]) if len(ev) > 1 else 0
    return span <= sh.get("max_kill_span", 10)


# ---------------------------------------------------------------- clip browser
API_BASE = ""      # the app sets this to http://127.0.0.1:<port> while its clip server is running
THUMB_DIR = "thumbs"          # inside the output folder; cached, cheap to rebuild
CLIP_PAGE = "clips.html"

def _thumb_for(path, dst, killclip, log=log, cache_only=False):
    """One frame from a third of the way into the clip, 320 px wide. Cached: made once per clip.

    cache_only returns what is already on disk and makes nothing new. Each thumbnail is an ffmpeg call,
    and while a clipping run is going those calls queue behind it - measured at about four seconds each
    instead of a fraction of one. With a few hundred clips that turns opening the browser into a
    twenty-minute wait, so during a run we show the page immediately with the pictures we have."""
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(path): return True
    if cache_only: return False
    try:
        dur = killclip.duration(path)
    except Exception:
        dur = 6.0
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run([killclip.FFMPEG, "-v", "error", "-y", "-ss", str(round(dur / 3.0, 2)), "-i", path,
                        "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "7", dst],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        return os.path.exists(dst)
    except Exception as e:
        log(f"  no thumbnail for {os.path.basename(path)}: {e}"); return False

def clip_page_path(s):
    return os.path.join(s["output_dir"], CLIP_PAGE)

def set_rating(L, name, rating):
    """Remember what you thought of a clip: 1 keep, -1 never post, 0 undecided.

    This is the only judgement in the whole pipeline that is not a formula. Measured against the channel,
    no weighting of kills, vehicles, distance or length predicted views, so the score can order the queue
    but cannot pick what is worth posting. You can."""
    c = L.get("clips", {}).get(name)
    if c is None: return False
    r = int(rating or 0)
    if r: c["rating"] = max(-1, min(1, r))
    else: c.pop("rating", None)
    save_ledger(L)
    return True

def write_clip_page(s, L, killclip, log=log, limit=400, make_thumbs=True):
    """Write a self-contained page listing the clips: picture, title, kills, distance, length.
    Thumbnails are embedded in the file, so it still works after syncing to a phone."""
    import base64
    out = s["output_dir"]
    if not out or not os.path.isdir(out): return None
    rows = []; missing = 0
    snapshot = list(L.get("clips", {}).items())     # a run may be adding clips while we read
    items = [(k, v) for k, v in snapshot
             if v.get("status") in ("publiser", "andre") and v.get("path") and os.path.exists(v["path"])]
    items.sort(key=lambda kv: kv[1].get("at", ""), reverse=True)
    for name, c in items[:limit]:
        p = c["path"]
        th = os.path.join(out, THUMB_DIR, os.path.splitext(name)[0] + ".jpg")
        img = ""
        if _thumb_for(p, th, killclip, log, cache_only=not make_thumbs):
            try: img = "data:image/jpeg;base64," + base64.b64encode(open(th, "rb").read()).decode("ascii")
            except OSError: img = ""
        # Title and score are derived from the counts, never read back from the ledger: clips cut by
        # an older build have a stored title that counted an occupied vehicle twice ("2 kills, 2
        # vehicles destroyed" for two vehicle kills). The counts themselves are right, so deriving
        # here shows the truth without re-cutting anything. Same formula as the nightly upload uses.
        solo = killclip.solo_kills_of(c)
        veh = c.get("vehicles") or 0
        dist = c.get("max_dist_m") or 0
        length = round(float(c.get("len") or 0), 1)
        if c.get("kills") is not None:
            title = killclip.auto_title(solo, 0, veh, 0, None, dist)
            score = killclip.clip_score(solo, veh, dist, length)
        else:
            title = c.get("title") or ""
            score = c.get("score") or 0
        if not title:
            t = os.path.splitext(p)[0] + ".txt"
            try: title = open(t, encoding="utf-8").read().split("\n")[0]
            except OSError: title = os.path.splitext(name)[0]
        if not img: missing += 1
        rows.append({"name": name, "title": title, "img": img,
                     "rel": os.path.relpath(p, out).replace("\\", "/"),
                     "kills": solo, "veh": veh,
                     "dist": dist, "len": length,
                     "score": score, "at": (c.get("at") or "")[:16].replace("T", " "),
                     "rating": int(c.get("rating") or 0),
                     "where": "Publish" if c["status"] == "publiser" else "Other"})
    page = _CLIP_PAGE_HTML.replace("__DATA__", json.dumps(rows, ensure_ascii=False)) \
                          .replace("__API__", API_BASE) \
                          .replace("__MADE__", datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
    dst = clip_page_path(s)
    try:
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: f.write(page)
        os.replace(tmp, dst)
    except OSError as e:
        log(f"Could not write the clip browser: {e}"); return None
    log(f"Clip browser: {len(rows)} clips -> {dst}"
        + (f" ({missing} without a picture yet - they get one when the run is done)" if missing else ""))
    return dst

_CLIP_PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KillFeed clips</title>
<style>
:root{--bg:#0f0f10;--panel:#18181b;--field:#232326;--fg:#f2f2f2;--muted:#9a9a9a;--gold:#d4af37;--line:#2a2a2e}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif}
a{color:inherit;text-decoration:none}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px 48px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;padding:20px 0 6px}
h1{font-size:20px;letter-spacing:.08em;margin:0;font-weight:800}
h1 span{color:var(--gold)}
.made{color:var(--muted);font-size:13px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0 12px;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=search],select{background:var(--field);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit}
input[type=search]{flex:1;min-width:180px}
.seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:var(--field);color:var(--muted);border:0;padding:8px 14px;font:inherit;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--gold);color:#111;font-weight:700}
.count{color:var(--muted);font-size:13px;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;padding-top:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.card.up{border-color:var(--gold)}
.card.down{opacity:.42}
.rate{display:flex;gap:6px}
.rate button{flex:0 0 auto;min-width:38px;font-size:15px;line-height:1}
.rate button[aria-pressed=true]{background:var(--gold);color:#101010;border-color:var(--gold);font-weight:700}
.saved{color:var(--muted);font-size:12px;margin-left:auto;align-self:center}
.saved.bad{color:#e0736d}
.card a.shot{display:block;position:relative;aspect-ratio:9/16;background:#000}
.card a.shot video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .12s}
.card a.shot.playing video{opacity:1}
.card a.shot.playing img{opacity:0}
.card a.shot .hint{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,.6);border-radius:999px;padding:6px 12px;font-size:12px;color:#fff;opacity:0;transition:opacity .12s;pointer-events:none}
.card a.shot:hover .hint{opacity:1}
.card a.shot.playing .hint{opacity:0}
.card img{width:100%;height:100%;object-fit:cover;display:block}
.noimg{display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:13px}
.tag{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.72);border:1px solid var(--line);border-radius:999px;padding:3px 9px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.tag.pub{border-color:var(--gold);color:var(--gold)}
.len{position:absolute;bottom:8px;right:8px;background:rgba(0,0,0,.72);border-radius:6px;padding:2px 7px;font-size:12px;color:var(--fg)}
.meta{padding:10px 12px 12px;display:flex;flex-direction:column;gap:8px;flex:1}
.t{font-size:14px;line-height:1.35}
.nums{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:auto}
.nums b{color:var(--gold)}
.row{display:flex;gap:8px}
.row button{flex:1;background:var(--field);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:7px;font:inherit;font-size:13px;cursor:pointer}
.row button:hover{border-color:var(--gold);color:var(--gold)}
.empty{color:var(--muted);padding:40px 0;text-align:center}
@media(max-width:560px){.grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}.t{font-size:13px}}
</style>
</head>
<body>
<div class="wrap">
<header><h1>KILL<span>FEED</span> clips</h1><div class="made">built __MADE__</div></header>

<div class="bar">
  <input type="search" id="q" placeholder="Search title or file…" autocomplete="off">
  <select id="sort">
    <option value="kills">Most kills</option>
    <option value="dist">Longest shot</option>
    <option value="score">Best score</option>
    <option value="at">Newest</option>
    <option value="len">Shortest</option>
  </select>
  <div class="seg" id="where">
    <button data-w="Publish" aria-pressed="true">Publish</button>
    <button data-w="Other" aria-pressed="false">Other</button>
    <button data-w="all" aria-pressed="false">All</button>
    <button data-w="up" aria-pressed="false">Marked &#9650;</button>
    <button data-w="down" aria-pressed="false">Marked &#9660;</button>
  </div>
  <div class="count" id="count"></div>
</div>

<div class="grid" id="grid"></div>
<div class="empty" id="empty" hidden>Nothing here. Try All, or clear the search.</div>
</div>

<script>
const CLIPS = __DATA__;
const API = "__API__";          // filled in while KillFeed is running; empty in a synced copy of this file
const $ = s => document.querySelector(s);
let where = "Publish";

// Marking a clip writes straight back to KillFeed's ledger, so the nightly job sees it: a clip marked
// down is never uploaded, one marked up goes to the front of the queue.
async function rate(btn, name, val){
  const row = btn.closest(".rate"), note = row.querySelector(".saved");
  const clip = CLIPS.find(c => c.name === name);
  const next = clip.rating === val ? 0 : val;
  if (!API){ note.textContent = "open via Browse clips in the app to save"; note.className = "saved bad"; return; }
  note.textContent = "saving…"; note.className = "saved";
  try {
    const r = await fetch(API + "/rate", {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify({name: name, rating: next})});
    if (!r.ok) throw new Error(r.status);
    clip.rating = next;
    render();
  } catch (e) {
    note.textContent = "could not save – is KillFeed still running?"; note.className = "saved bad";
  }
}

function num(c, k){ return k === "len" ? -c.len : (k === "at" ? c.at : c[k]); }

function render(){
  const q = $("#q").value.trim().toLowerCase();
  const key = $("#sort").value;
  const inSet = c => where === "all" ? true
                   : where === "up" ? c.rating === 1
                   : where === "down" ? c.rating === -1
                   : c.where === where;
  let list = CLIPS.filter(c => inSet(c)
    && (!q || (c.title + " " + c.name).toLowerCase().includes(q)));
  list.sort((a, b) => {
    const x = num(b, key), y = num(a, key);
    if (x > y) return 1; if (x < y) return -1;
    return a.at < b.at ? 1 : -1;
  });
  $("#count").textContent = list.length + " clip" + (list.length === 1 ? "" : "s");
  $("#empty").hidden = list.length > 0;
  $("#grid").innerHTML = list.map(card).join("");
  wireHover();
}

function card(c){
  const shot = c.img ? `<img loading="lazy" src="${c.img}" alt="">` : `<div class="noimg">no preview</div>`;
  const bits = [];
  if (c.kills) bits.push(`<span><b>${c.kills}</b> kill${c.kills > 1 ? "s" : ""}</span>`);
  if (c.veh) bits.push(`<span><b>${c.veh}</b> vehicle${c.veh > 1 ? "s" : ""}</span>`);
  if (c.dist) bits.push(`<span><b>${c.dist}</b> m</span>`);
  bits.push(`<span>${c.at}</span>`);
  const cls = c.rating === 1 ? " up" : (c.rating === -1 ? " down" : "");
  const url = clipUrl(c);
  return `<div class="card${cls}">
    <a class="shot" href="${url}" target="_blank" rel="noopener" data-src="${url}">${shot}<span class="hint">hover to play</span>
      <span class="tag ${c.where === "Publish" ? "pub" : ""}">${c.where}</span>
      <span class="len">${c.len}s</span>
    </a>
    <div class="meta">
      <div class="t">${esc(c.title)}</div>
      <div class="nums">${bits.join("")}</div>
      <div class="row rate">
        <button title="Worth posting" aria-pressed="${c.rating === 1}" onclick="rate(this, ${JSON.stringify(c.name).replace(/"/g, "&quot;")}, 1)">&#9650;</button>
        <button title="Never post this" aria-pressed="${c.rating === -1}" onclick="rate(this, ${JSON.stringify(c.name).replace(/"/g, "&quot;")}, -1)">&#9660;</button>
        <button onclick="copyTitle(this, ${JSON.stringify(c.title).replace(/"/g, "&quot;")})">Copy title</button>
        <span class="saved"></span>
      </div>
    </div>
  </div>`;
}

// Served by KillFeed when it is running, straight off disk otherwise. Both work for playing a clip.
function clipUrl(c){ return (API ? API + "/clip/" : "") + encodeURI(c.rel); }

// Hover to play. The video element is only made on the first hover and nothing is fetched before that,
// so a page with a few hundred clips on it stays light until you actually look at one.
function wireHover(){
  document.querySelectorAll(".card a.shot").forEach(a => {
    if (a.dataset.wired) return;
    a.dataset.wired = "1";
    let v = null;
    a.addEventListener("mouseenter", () => {
      if (!v){
        v = document.createElement("video");
        v.muted = true; v.loop = true; v.playsInline = true; v.preload = "none";
        v.src = a.dataset.src;
        a.appendChild(v);
      }
      try { v.currentTime = 0; } catch (e) {}
      // Say so when it cannot play rather than doing nothing: a browser without H.264 fails silently
      // otherwise, and the card just sits there looking broken.
      v.onerror = () => { const h = a.querySelector(".hint"); if (h) h.textContent = "click to open"; };
      v.play().then(() => a.classList.add("playing"))
              .catch(() => { const h = a.querySelector(".hint"); if (h) h.textContent = "click to open"; });
    });
    a.addEventListener("mouseleave", () => {
      if (!v) return;
      v.pause(); a.classList.remove("playing");
    });
  });
}

function esc(s){ const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function copyTitle(btn, text){
  const done = () => { const old = btn.textContent; btn.textContent = "Copied"; setTimeout(() => btn.textContent = old, 1200); };
  try {
    navigator.clipboard.writeText(text).then(done, () => fallback(text, done));
  } catch (e) { fallback(text, done); }
}
function fallback(text, done){
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { prompt("Copy the title:", text); }
  ta.remove();
}

$("#q").addEventListener("input", render);
$("#sort").addEventListener("change", render);
$("#where").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  where = b.dataset.w;
  [...$("#where").children].forEach(x => x.setAttribute("aria-pressed", x === b));
  render();
});
render();
</script>
</body>
</html>
"""

def resort_clips(s, L, log=log):
    """Re-apply the Publish/Other rule to clips we already have, moving the files to match.
    Used when the rule itself changes, so a stricter setting cleans up the existing queue
    instead of only applying to whatever gets clipped next. Returns (to_publish, to_other)."""
    sh = s["shorts"]
    out_pub = os.path.join(s["output_dir"], "Publish"); out_andre = os.path.join(s["output_dir"], "Other")
    moved_pub = moved_other = 0
    for name, c in L.get("clips", {}).items():
        if c.get("status") not in ("publiser", "andre"): continue
        if c.get("fallback"): continue                      # the queue-is-empty pick stays where it is
        want = "publiser" if qualifies(c, sh) else "andre"
        if want == c["status"]: continue
        src = c.get("path") or ""
        dst_dir = out_pub if want == "publiser" else out_andre
        if not src or not os.path.exists(src):
            c["status"] = want; continue                    # file already gone - just fix the ledger
        try:
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, os.path.basename(src))
            shutil.move(src, dst)
            for ext in (".txt", ".json"):
                t = os.path.splitext(src)[0] + ext
                if os.path.exists(t): shutil.move(t, os.path.splitext(dst)[0] + ext)
            c["path"] = dst; c["status"] = want
            if want == "publiser": moved_pub += 1
            else: moved_other += 1
        except OSError as e:
            log(f"  could not move {name}: {e}")
    if moved_pub or moved_other:
        save_ledger(L)
        log(f"Re-sorted with the current rule: {moved_pub} to Publish, {moved_other} to Other.")
    return moved_pub, moved_other

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
    out_pub = os.path.join(s["output_dir"], "Publish"); out_andre = os.path.join(s["output_dir"], "Other")   # lages ved første klipp
    taken = [(k, v.get("abs_events") or []) for k, v in L["clips"].items() if v.get("status") in ("publiser", "andre") and v.get("abs_events")]
    pv = s.get("prefer_vertical", True)
    def is_vert(seg):
        try: w, h = map(int, str(seg.get("source_res", "0x0")).split("x")); return h > w
        except Exception: return False
    results = []
    for seg in sorted(segs, key=lambda x: ((is_vert(x) if pv else 0), x.get("score", 0), -x.get("clamped_start", False)), reverse=True):
        name = seg["file"]; src = os.path.join(wd, name)
        ev = seg.get("abs_events") or []
        dup_of = next((k for k, t in taken if ev and _same(ev, t, tol)), None)
        if dup_of and pv and is_vert(seg) and not L["clips"].get(dup_of, {}).get("vertical"):
            # 9:16 kom etter 16:9-versjonen av samme kill: bytt - den loddrette er ferdig formatert
            old = L["clips"][dup_of]
            for ext in (".mp4", ".txt"):
                try: os.remove(os.path.splitext(old.get("path", ""))[0] + ext)
                except OSError: pass
            old["status"] = "duplicate"; old["of"] = name
            taken = [(k, t) for k, t in taken if k != dup_of]
            log(f"  9:16 replaces the 16:9 crop of the same kill: {dup_of}")
            dup_of = None
        if dup_of:
            if _merge_into_kept(L["clips"].get(dup_of, {}), seg, killclip, log):
                kept = L["clips"][dup_of]
                if kept.get("status") == "andre" and qualifies(kept, sh) and kept.get("path") and os.path.exists(kept["path"]):
                    try:                                  # the duplicate proved it is a multikill/vehicle kill: promote to Publish
                        os.makedirs(out_pub, exist_ok=True); newp = os.path.join(out_pub, os.path.basename(kept["path"]))
                        shutil.move(kept["path"], newp)
                        t = os.path.splitext(kept["path"])[0] + ".txt"
                        if os.path.exists(t): shutil.move(t, os.path.splitext(newp)[0] + ".txt")
                        kept["path"] = newp; kept["status"] = "publiser"; log(f"  promoted to Publish: {dup_of}")
                    except OSError as e: log(f"  could not promote {dup_of}: {e}")
            for ext in (".mp4", ".json", ".txt"):
                try: os.remove(os.path.splitext(src)[0] + ext)
                except OSError: pass
            L["clips"][name] = {"status": "duplicate", "of": dup_of, "abs_events": ev, "at": datetime.datetime.now().isoformat()}
            results.append((name, "duplicate")); log(f"  duplicate of {dup_of}: {name}")
            continue
        status = "publiser" if qualifies(seg, sh) else "andre"
        dest = os.path.join(out_pub if status == "publiser" else out_andre, name)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            txt = os.path.splitext(src)[0] + ".txt"
            if os.path.exists(txt): shutil.move(txt, os.path.splitext(dest)[0] + ".txt")
            js = os.path.splitext(src)[0] + ".json"
            if os.path.exists(js): shutil.move(js, os.path.join(REPORTS, os.path.basename(js)))
        except Exception as e:
            log(f"  ERROR moving {name}: {e}"); continue
        L["clips"][name] = {"status": status, "abs_events": ev, "score": seg.get("score", 0), "kills": seg.get("kills", 0),
                            "vehicles": seg.get("vehicles", 0), "money": seg.get("money", 0), "source": seg.get("source"),
                            "title": seg.get("title"), "max_dist_m": seg.get("max_dist_m", 0), "victims": [x["victim"] for x in seg.get("kill_details", [])],
                            "vertical": is_vert(seg), "len": seg.get("len", 0), "clamped_start": seg.get("clamped_start", False),
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
    c = L["clips"][best]; dest = os.path.join(s["output_dir"], "Publish", best)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(c["path"], dest)
        t = os.path.splitext(c["path"])[0] + ".txt"
        if os.path.exists(t): shutil.move(t, os.path.splitext(dest)[0] + ".txt")
        c["status"] = "publiser"; c["path"] = dest; c["fallback"] = True
        log(f"  no multikill this session – fallback: {best} -> Publish"); return best
    except Exception as e:
        log(f"  ERROR fallback {best}: {e}"); return None

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

BANK = "RecapBank"

def bank_dir(s):
    return os.path.join(s["output_dir"], BANK)

def bank_segments(s, rep_path, killclip, log=log):
    """Klipp ut recap-bitene av et opptak som egne smaa filer, og skriv dem inn i rapporten.

    Recapen klippes fra selve opptaket. Et opptak er titalls GB, recap-bitene til sammen under en GB,
    saa naar bitene ligger trygt kan opptaket slettes uten at recapen mister noe.

    Vi tar vare paa alt som har et kill eller et kjoeretoey i seg - ikke bare det montage.min_kills
    slipper gjennom naa - for terskelen kan senkes senere, og da er opptaket kanskje borte.
    Returnerer antall biter som ble lagt i banken."""
    r = jload(rep_path, {})
    src = r.get("input")
    if not src or not os.path.exists(src): return 0
    if r.get("bank"): return 0                            # allerede banket
    hits = [(float(t), k) for t, k in r.get("hits", [])]
    if not hits: return 0
    m = s["montage"]
    try:
        dur, W, H = float(r["duration"]), int(r["width"]), int(r["height"])
    except (KeyError, TypeError, ValueError):
        try: dur, W, H = killclip.probe(src)
        except Exception as e: log(f"  recap bank: could not read {os.path.basename(src)}: {e}"); return 0
    if H > W: return 0                                    # recapen bruker bare vanlige 16:9-opptak
    t0 = killclip.file_start_epoch(src, dur)
    d = bank_dir(s); os.makedirs(d, exist_ok=True)
    bursts = killclip.event_bursts(hits)
    base = _basename_noext(src); out = []
    for i, (a, b, kinds) in enumerate(killclip.cluster(hits, dur, m["pre"], m["post"], m["gap"], m["clip_min"], m["clip_max"]), 1):
        kills = _waves(hits, a, b, lambda x: x.startswith("KILLCONFIRMED"))
        veh = _waves(hits, a, b, lambda x: "DESTROYED" in x)
        if not kills and not veh: continue                # ren assist: ikke verdt plass i banken
        # samme regel som for shorts: et ensomt enkeltkill uten noe rundt seg bankes heller ikke
        lg = s["shorts"].get("lonely_gap_s", 0) or 0
        if lg and killclip.is_lonely_single(hits, a, b, kills, veh, lg, bursts): continue
        f = os.path.join(d, f"{base}-recap{i:02d}.mp4")
        if not os.path.exists(f):
            try:
                killclip.cut_plain(src, a, b, f)
            except Exception as e:
                log(f"  recap bank: {os.path.basename(f)} failed: {e}"); continue
        out.append({"file": f, "len": round(b - a, 1), "kills": kills, "vehicles": veh,
                    "money": _money(hits, a, b), "abs": round(t0 + a, 1),
                    "abs_events": [round(t0 + t, 1) for t, kk in hits if a <= t <= b]})
    if out:
        r["bank"] = out; jsave(rep_path, r)
        mb = sum(os.path.getsize(x["file"]) for x in out if os.path.exists(x["file"])) / 2**20
        log(f"  recap bank: {len(out)} segment(s), {mb:.0f} MB - the recording is no longer needed for the recap")
    return len(out)

def montage_candidates(s, L, killclip):
    """Segmenter fra 16:9-opptak (rapporter i REPORTS) som ikke er brukt i en montasje før. Kronologisk."""
    m = s["montage"]; tol = s.get("dedup_seconds", 5)
    used = [ev for mg in L["montages"] for ev in mg.get("used", [])]
    cutoff = time.time() - m["lookback_days"] * 86400
    cands = []
    for rep in glob.glob(os.path.join(REPORTS, "*-auto.json")):
        r = jload(rep, {})
        src = r.get("input"); hits = [(float(t), k) for t, k in r.get("hits", [])]
        # banken foerst: da spiller det ingen rolle om selve opptaket er slettet
        bank = [x for x in (r.get("bank") or []) if os.path.exists(x.get("file", ""))]
        if bank:
            for x in bank:
                if x["abs"] < cutoff: continue
                if x["kills"] < m["min_kills"] and not (m.get("count_vehicles", True) and x["vehicles"]): continue
                if any(_same(x["abs_events"], u, tol) for u in used): continue
                cands.append({"src": x["file"], "a": 0.0, "b": x["len"], "len": x["len"], "kills": x["kills"],
                              "vehicles": x["vehicles"], "money": x.get("money", 0), "abs": x["abs"],
                              "abs_events": x["abs_events"]})
            continue
        if not src or not os.path.exists(src) or not hits: continue
        if r.get("width") and r.get("height") and r.get("duration"):
            dur, W, H = float(r["duration"]), int(r["width"]), int(r["height"])
        else:                                             # older report: probe once and remember it
            try:
                dur, W, H = killclip.probe(src); r.update({"duration": dur, "width": W, "height": H}); jsave(rep, r)
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
    if not cands: log("Recap: no qualifying clips yet."); return None
    if not ready and not force:
        log(f"Recap: {sum(c['len'] for c in cands)/60:.1f} of {m['min_minutes']} min collected – waiting."); return None
    chosen, total = [], 0.0
    for c in cands:
        if total + c["len"] > m["max_minutes"] * 60: break
        chosen.append(c); total += c["len"]
    if not chosen: return None
    out_dir = os.path.join(s["output_dir"], "Recaps"); os.makedirs(out_dir, exist_ok=True)
    d0 = datetime.datetime.fromtimestamp(chosen[0]["abs"]); d1 = datetime.datetime.fromtimestamp(chosen[-1]["abs"])
    kills = sum(c["kills"] for c in chosen); veh = sum(c["vehicles"] for c in chosen)
    span = f"{d0:%d.%m}" if d0.date() == d1.date() else f"{d0:%d.%m}–{d1:%d.%m}"
    fspan = f"{d0:%Y-%m-%d}" if d0.date() == d1.date() else f"{d0:%Y-%m-%d} to {d1:%m-%d}"
    mm, ss = divmod(int(total), 60)
    label = m.get("label", "recap").strip() or "recap"
    name = f"WARDOGS {label} {fspan}.mp4"
    out = os.path.join(out_dir, name); k = 2
    while os.path.exists(out):                          # to samme dag -> (2), (3) …
        out = os.path.join(out_dir, f"WARDOGS {label} {fspan} ({k}).mp4"); k += 1
    name = os.path.basename(out)
    res = {"1440p": (2560, 1440)}.get(m.get("resolution", "1080p"), (1920, 1080))
    log(f"Recap: {len(chosen)} clips, {mm}m{ss:02d}s, {kills} kills, {veh} vehicles -> {name}")
    try:
        _concat(chosen, out, res, killclip)
    except Exception as e:
        log(f"  ERROR recap: {e}"); return None
    bits = [f"{kills} kill{'s' if kills != 1 else ''}"] + ([f"{veh} vehicle{'s' if veh != 1 else ''} destroyed"] if veh else [])
    title = f"{m.get('title_prefix', 'WARDOGS Daily Recap')} {span} – {', '.join(bits)}"[:100]
    with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as f:
        f.write(title + f"\n\nLength {mm}:{ss:02d} · {len(chosen)} clips · {kills} kills · {veh} vehicles\n\n" + "\n".join(f"{datetime.datetime.fromtimestamp(c['abs']):%d.%m %H:%M}  {c['kills']} kills  {os.path.basename(c['src'])}  {c['a']:.0f}-{c['b']:.0f}s" for c in chosen) + "\n")
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

# ------------------------------------------------------------------ opptaksguide (vises i appen)
RECORDING_GUIDE = """How to get recordings KillFeed can use

You need ONE of these. KillFeed reads the kill feed from the picture, so anything that produces a video file of the game works.

OBS Studio (recommended, free)
  1. Settings -> Output -> Recording: pick a folder (e.g. Videos\\Wardogs\\full-format), format MKV,
     encoder NVENC/AMF/QuickSync, quality "High Quality" or CQP 20.
  2. Settings -> Output -> Replay Buffer: on, 120 seconds. Settings -> Hotkeys -> "Save Replay": F9.
     Press F9 right after a good moment -> the file "Replay ... .mkv" lands in the folder.
  3. Want the whole session: Settings -> General -> "Automatically record when streaming", or Start Recording.
  Tip: keep the kill feed and HUD on. Do not scale the HUD below 100 %.

NVIDIA App / ShadowPlay (Instant Replay)
  Alt+Z -> Instant Replay -> on, 2 min. Alt+F10 saves. Folder: Videos\\Wardogs. Works out of the box.

Medal
  Medal saves clips in Videos\\Medal\\WARDOGS. Point KillFeed there.

Aitum Vertical (OBS plugin, 9:16 directly)
  Gives vertical backtracks that become shorts without cropping. Make sure the game sits in the 1:1 area
  and the kill text below the crosshair is visible. Note: the real kill feed (left side) is outside the crop,
  so distance/victim is taken from a 16:9 recording of the same moment if you also have one.

Steam / Xbox Game Bar
  Win+Alt+G (last 30 s) or Win+Alt+R. Folder: Videos\\Captures. Point KillFeed at Videos\\.

Common
  - 1080p or 1440p, 60 fps. 16:9 becomes a centre crop in shorts; 9:16 goes straight through.
  - KillFeed waits until the game is closed before it clips (saves CPU), and until the file is 2 min old.
  - Nothing is sent anywhere. Your clips stay with you.
"""


# ------------------------------------------------------------------ dashboard helpers
def ledger_stats(L):
    """Numbers for the dashboard: shorts today / last 7 days, recaps, and the most recent clips (newest first)."""
    now = datetime.datetime.now(); today = now.date(); week = now - datetime.timedelta(days=7)
    def when(v):
        try: return datetime.datetime.fromisoformat(v.get("at", ""))
        except Exception: return datetime.datetime.min
    clips = [(k, v) for k, v in L["clips"].items() if v.get("status") in ("publiser", "andre")]
    today_n = sum(1 for _, v in clips if v.get("status") == "publiser" and when(v).date() == today)
    week_n = sum(1 for _, v in clips if v.get("status") == "publiser" and when(v) >= week)
    recent = sorted(clips, key=lambda kv: when(kv[1]), reverse=True)[:200]
    rows = []
    for k, v in recent:
        rows.append({"name": k, "at": when(v), "kills": v.get("kills", 0), "vehicles": v.get("vehicles", 0),
                     "dist": v.get("max_dist_m", 0), "where": "Publish" if v.get("status") == "publiser" else "Other",
                     "path": v.get("path", ""), "source": v.get("source", ""), "score": v.get("score", 0),
                     "fallback": v.get("fallback", False), "vertical": v.get("vertical", False), "victims": v.get("victims", [])})
    return {"today": today_n, "week": week_n, "recaps": len(L.get("montages", [])), "total": len(clips),
            "sources": len(L.get("processed", {})), "recent": rows}

def why_text(row, s):
    """One-paragraph explanation of why a clip landed where it did."""
    sh = s["shorts"]; k, v = row["kills"], row["vehicles"]
    parts = [f"{k} kill{'s' if k != 1 else ''}" + (f", {v} vehicle{'s' if v != 1 else ''} destroyed" if v else "")]
    if row["dist"]: parts.append(f"longest {row['dist']} m")
    if row["victims"]: parts.append("victims: " + ", ".join(row["victims"]))
    rule = (f"Publish needs {sh['min_kills']}+ kills within {sh.get('max_kill_span', 10)} s of each other, "
            f"or {sh['min_vehicles']}+ vehicle kill.")
    if row["where"] == "Publish":
        verdict = "Fallback: best single kill of a session that had no multikill." if row["fallback"] else "Met the rule."
    else:
        verdict = "Did not meet the rule, so it went to Other (nothing is thrown away)."
    return "; ".join(parts) + ".\n" + rule + "\n" + verdict

def forget_source(L, name):
    """Make KillFeed treat this recording as new on the next run. Existing clips from it are kept in the folders.
    `name` is a file name; entries are keyed by full path now, so drop every entry whose file matches."""
    n = 0
    if L["processed"].pop(name, None) is not None: n += 1          # an old basename-keyed entry
    for k, v in list(L["processed"].items()):
        if (v.get("file") or os.path.basename(k)) == name:
            L["processed"].pop(k, None); L["sizes"].pop(k, None); n += 1
    L["sizes"].pop(name, None)
    for k, v in list(L["clips"].items()):
        if v.get("source") and os.path.basename(v["source"]) == name:
            L["clips"].pop(k); n += 1
    save_ledger(L); return n

def delete_outputs(s):
    """Delete every KillFeed-made file in Publish/Other/Recaps/RecapBank (mp4 + txt).
    Never touches the user's recordings."""
    out = s.get("output_dir") or ""
    if not out or not os.path.isdir(out):
        log(f"Not deleting anything: the output folder is not set up ({out!r}).")
        return 0
    n = 0
    for sub in ("Publish", "Other", "Recaps", BANK):
        d = os.path.join(out, sub)
        for f in glob.glob(os.path.join(d, "*")):
            if f.lower().endswith((".mp4", ".txt")):
                try: os.remove(f); n += 1
                except OSError: pass
    return n

CLIP_KEYS = {("shorts", "pre"), ("shorts", "post"), ("shorts", "gap"), ("shorts", "min"), ("shorts", "max"), ("style",), ("dedup_seconds",)}

def retry_failed(L):
    """Forget only the recordings that ended in an error/skip, so they are tried again next run. Returns how many."""
    bad = [k for k, v in L["processed"].items() if v.get("error")]
    for k in bad: L["processed"].pop(k, None); L["sizes"].pop(k, None)
    save_ledger(L); return len(bad)

def failed_count(L):
    return sum(1 for v in L["processed"].values() if v.get("error"))

def reset_ledger(L):
    """Forget everything: every recording is scanned again next run. Files already in Publish/Other/Recaps are left alone."""
    for k in ("processed", "clips", "sizes"): L[k] = {}
    L["montages"] = []
    # the recap bank is filled once per report and skipped if it is already there, so a report that keeps
    # its bank list would never be re-cut - drop the lists so the rescan fills the bank again
    for rep in glob.glob(os.path.join(REPORTS, "*-auto.json")):
        r = jload(rep, {})
        if r.pop("bank", None) is not None: jsave(rep, r)
    save_ledger(L)

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
    if n: log(f"Cleanup: removed {n} files from Other\\ older than {days} days."); save_ledger(L)
    return n

def delete_clipped_sources(s, L, killclip, log=log):
    """Slett opptak som er ferdig klippet, hvis brukeren har bedt om det. Frigjor mye: et opptak er
    titalls GB, klippene er titalls MB.

    To sperrer, fordi dette ikke kan angres:
      * bare filer som star i hovedboka UTEN feil - en fil som feilet, eller som ble avbrutt, blir liggende
      * recapen klipper fra selve opptaket, ikke fra shortsene. Saa lenge keep_source_for_recap star paa,
        beholdes et opptak til killene er brukt i en recap - ellers ville de forsvunnet ut av recapen.
    Returnerer (antall, frigjorte bytes)."""
    c = s.get("cleanup", {})
    if not c.get("delete_source_after_clip"): return 0, 0
    pending = set()
    if c.get("keep_source_for_recap", True):
        try:
            # kandidater som allerede kommer fra banken peker paa bank-fila, ikke paa opptaket,
            # saa et banket opptak havner ikke her og kan slettes med en gang
            pending = {os.path.normcase(os.path.abspath(x["src"])) for x in montage_candidates(s, L, killclip)}
        except Exception as e:
            log(f"Cleanup: could not check what the recap still needs ({e}) - keeping every recording."); return 0, 0
    n = 0; freed = 0; kept_blind = 0
    dirs = [s["input_dir"], s.get("vertical_dir") or ""] + list(s.get("extra_input_dirs") or [])
    for f in source_files(dirs, skip_dir=s["output_dir"]):
        # only an entry keyed by full path may authorise a delete. An old basename-keyed entry could
        # belong to a different recording of the same name in another folder.
        ent = L["processed"].get(src_key(f))
        if not ent or ent.get("error") or "clips" not in ent: continue      # never clipped, or clipped with an error
        # Proof that the text reading actually worked on THIS file. A broken Tesseract reads every frame
        # as empty, which is indistinguishable from a quiet recording - and a quiet recording is exactly
        # what this function is allowed to delete. So: no hits, no delete. A genuinely uneventful
        # recording is kept, which is the cheap mistake to make.
        if not ent.get("hits"):
            kept_blind += 1; continue
        if os.path.normcase(os.path.abspath(f)) in pending: continue        # a recap still wants this one
        try:
            sz = os.path.getsize(f); os.remove(f)
            ent["source_deleted"] = datetime.datetime.now().isoformat(); ent["source_bytes"] = sz
            n += 1; freed += sz
            log(f"  deleted the recording {os.path.basename(f)} ({sz/2**30:.1f} GB)")
        except OSError as e:
            log(f"  could not delete {os.path.basename(f)}: {e}")
    if kept_blind:
        log(f"Cleanup: {kept_blind} recording(s) kept - no kill text was read in them. If that is every "
            f"recording, the text reading is broken rather than the sessions being quiet.")
    if n: save_ledger(L); log(f"Cleanup: {n} recording(s) deleted, {freed/2**30:.1f} GB freed.")
    return n, freed

# ------------------------------------------------------------------ én full runde
def run_once(s, L, killclip, log=log, progress=None, stop=None):
    """Klipp alt som er klart, dedup, plasser, reserve, montasje. Returnerer oppsummering."""
    files = ready_sources(s, L); save_ledger(L)
    summary = {"sources": len(files), "publiser": [], "andre": [], "duplicate": 0, "montage": None,
               "stopped": False, "done": 0}
    if files: log(f"{len(files)} new recording(s) to go through")
    batch = []
    n_done = 0
    for n, f in enumerate(files, 1):
        if stop and stop():
            # Say WHY, and say what is left. "Stopped." on its own after 0 of 16 files looked
            # like a finished run, which is how a paused app came to report "Done: 0 ready".
            log(f"Stopped after {n_done} of {len(files)} recording(s) - the rest are clipped next time.")
            break
        if progress: progress(n, len(files), os.path.basename(f))
        log(f"[{n}/{len(files)}] {os.path.basename(f)}")
        for name, st in process_source(f, s, L, killclip, log, stop=stop):
            batch.append((name, st))
        n_done += 1
    stopped = bool(stop and stop())
    summary["stopped"] = stopped
    summary["done"] = n_done
    fb = promote_fallback(batch, s, L, log)
    for name, st in batch:
        if name == fb: st = "publiser"
        if st == "publiser": summary["publiser"].append(name)
        elif st == "andre": summary["andre"].append(name)
        else: summary["duplicate"] += 1
    if not stopped and s["montage"].get("enabled", True) and s["montage"].get("auto", True):
        summary["montage"] = build_montage(s, L, killclip, log=log)
    if not stopped:
        cleanup(s, L, log)
        try: delete_clipped_sources(s, L, killclip, log)
        except Exception as e: log(f"Cleanup of recordings failed: {e}")
    save_ledger(L)
    if s.get("clip_browser", True):
        try: write_clip_page(s, L, killclip, log=log)
        except Exception as e: log(f"Clip browser failed: {e}")
    return summary
