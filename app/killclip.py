#!/usr/bin/env python3
"""killclip.py – finner kill-feed-tekst i WARDOGS-backtracks (1080x1920, Aitum vertical) og klipper shorts.

Bruk: python killclip.py <backtrack.mkv> <utmappe> [--fps 2] [--pre 12] [--post 4] [--gap 12] [--min 18] [--max 40] [--dry]

Slik virker det:
  - Kill-feeden står på fast plass under siktet. Vi klipper ut det området (ROI) N ganger i sekundet,
    gjør det svart/hvitt og leser teksten med Tesseract.
  - Treff: KILL CONFIRMED / KILL ASSIST / VEHICLE DESTROYED / +$… / DELIVERED.
  - Hvert treff får --pre sekunder før og --post etter. Treff nærmere enn --gap slås sammen.
    Klipp under --min utvides, klipp over --max deles.
  - Ut: <navn>-autoNN-<start>-<slutt>.mp4 (H.264, lydspor 1) + sidecar .json med hendelser og auto-tittel,
    som yt_upload.py bruker.

Krever ffmpeg/ffprobe på PATH og Tesseract (Windows: https://github.com/UB-Mannheim/tesseract/wiki).
Sett miljøvariabel TESSERACT hvis den ikke ligger på standardstedet.
"""
import sys, os, re, subprocess, json, argparse, tempfile, glob, shutil
from concurrent.futures import ThreadPoolExecutor
CF = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # ingen konsollvindu-blink på Windows
# ffmpeg og tesseract kjoerer under normal prioritet. Windows gir dem da CPU bare naar ingen andre
# vil ha den, og lar dem likevel bruke alle kjerner naar maskinen staar stille. Det er bedre enn aa
# binde dem til faste kjerner, som ogsaa ville begrenset dem naar PC-en ikke gjoer noe annet.
# Prioriteten gjelder bare barneprosessene - selve vinduet blir liggende paa normal, saa GUI-et
# svarer like raskt midt i en kjoering.
# IDLE og ikke BELOW_NORMAL: paa Windows gir idle-klassen ogsaa LAV DISK-prioritet, og det er disken
# som gjoer vondt her. Aa lese et opptak paa 126 GB fyller koen til samme disk spillet streamer fra,
# og da hakker spillet og innputs henger selv om CPU-en har ledige kjerner. Naar maskinen ellers
# staar stille faar idle-prosesser alt, saa nattklippingen gaar like fort som foer.
CF |= getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)

# Hvor mange tesseract-prosesser som kjoerer samtidig. 0 = halvparten av de logiske CPU-ene.
# Foer sto det os.cpu_count(), altsaa ALLE: paa en i9 er det 24-32 parallelle OCR-prosesser, og det
# tok rundt 40 bilder i sekundet fra spillet. Tesseract skalerer dessuten daarlig over en viss
# bredde - disken og minnebaandbredden binder foer kjernene gjoer det - saa halvparten koster lite
# tid og gir maskinen tilbake til deg.
WORKERS = 0
def workers():
    n = os.cpu_count() or 4
    return max(2, int(WORKERS) if WORKERS else n // 2)

# Dekod opptaket paa GPU-en i stedet for paa CPU. NVDEC er en egen brikke, ikke de samme
# shaderne spillet bruker, saa det koster nesten ingen bilder - og software-HEVC-dekoding er det
# dyreste enkeltleddet i skanningen. Av som standard fordi det avhenger av driver og byggvariant:
# slaa den paa, kjoer ett opptak, og sammenlign antall klipp med en kjent fil foer du stoler paa den.
HWACCEL = ""

_FULL_MASK = 0
def parse_cores(spec, n=None):
    """"16-31", "8,9,10,11" eller "" -> bitmaske over logiske CPU-er. Tom streng = alle."""
    if not spec or not str(spec).strip(): return 0
    n = n or (os.cpu_count() or 64)
    mask = 0
    for part in str(spec).replace(" ", "").split(","):
        if not part: continue
        try:
            if "-" in part:
                a, b = part.split("-", 1); rng = range(int(a), int(b) + 1)
            else:
                rng = [int(part)]
        except ValueError:
            continue
        for i in rng:
            if 0 <= i < n: mask |= 1 << i
    return mask

def set_affinity(mask):
    """Bind denne prosessen - og dermed alle ffmpeg/tesseract den starter, som arver masken - til
    bestemte logiske CPU-er. mask 0 = tilbake til alle.

    Hvorfor paa oss selv og ikke paa hvert barn: tesseract startes titusenvis av ganger og lever
    noen titalls millisekunder hver gang. Aa sette masken ETTER at prosessen er startet rekker ikke
    aa bety noe for en saa kort prosess. Arv gjoer det, og koster ingenting.
    Returnerer True hvis masken ble satt."""
    global _FULL_MASK
    if os.name != "nt": return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        if not _FULL_MASK:
            proc = ctypes.c_size_t(); syst = ctypes.c_size_t()
            if k.GetProcessAffinityMask(k.GetCurrentProcess(), ctypes.byref(proc), ctypes.byref(syst)):
                _FULL_MASK = syst.value or proc.value
        want = mask or _FULL_MASK
        if not want: return False
        return bool(k.SetProcessAffinityMask(k.GetCurrentProcess(), ctypes.c_size_t(want)))
    except Exception:
        return False
_procs = []   # ffmpeg-prosesser som kjører nå (appen dreper dem ved avslutning)
ABORT = False  # appen setter True for aa avbryte fila som behandles naa (sjekkes mellom ffmpeg-kall og per OCR-bilde)
class Aborted(Exception): pass
def _check_abort():
    if ABORT: raise Aborted("aborted by user")
def _run_ffmpeg(cmd):
    require_tools()
    _check_abort()
    p = subprocess.Popen(cmd, creationflags=CF); _procs.append(p)
    try:
        rc = p.wait()
    finally:
        try: _procs.remove(p)
        except ValueError: pass
    if rc != 0: raise subprocess.CalledProcessError(rc, cmd)

def _appdir():
    """Der de innbakte verktøyene ligger: PyInstaller onefile pakker ut til sys._MEIPASS,
    onedir legger dem ved siden av exe-en, ellers ved siden av skriptet."""
    if getattr(sys, "frozen", False): return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _tess():
    for c in [os.environ.get("TESSERACT"), os.path.join(_appdir(), "tesseract", "tesseract.exe"),
              shutil.which("tesseract"), r"C:\Program Files\Tesseract-OCR\tesseract.exe"]:
        if c and os.path.exists(c): return c
    return "tesseract"
TESS = _tess()
if os.path.isdir(os.path.join(_appdir(), "tesseract", "tessdata")):
    os.environ["TESSDATA_PREFIX"] = os.path.join(_appdir(), "tesseract", "tessdata")

def _find(exe):
    """Finn ffmpeg/ffprobe: PATH, ellers winget-plasseringer (nytt cmd-vindu trengs etter installasjon)."""
    d = os.environ.get("FFMPEG_DIR")
    if d and os.path.exists(os.path.join(d, exe + ".exe")): return os.path.join(d, exe + ".exe")
    p = shutil.which(exe)
    if p: return p
    la = os.environ.get("LOCALAPPDATA", "")
    here = _appdir()
    cands = glob.glob(os.path.join(here, "ffmpeg", "**", exe + ".exe"), recursive=True)
    cands += glob.glob(os.path.join(here, "..", "tools", "ffmpeg", "**", exe + ".exe"), recursive=True)   # repo: tools\ffmpeg (gitignored)
    cands += [os.path.join(la, "Microsoft", "WinGet", "Links", exe + ".exe")]
    cands += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "ffmpeg-*", "bin", exe + ".exe"))
    cands += glob.glob(os.path.join("C:\\", "ffmpeg*", "bin", exe + ".exe")) + glob.glob(os.path.join("C:\\", "Program Files", "ffmpeg*", "bin", exe + ".exe"))
    for c in cands:
        if os.path.exists(c): return c
    la_pk = os.path.join(la, "Microsoft", "WinGet", "Packages")
    for root, dirs, files in os.walk(la_pk) if os.path.isdir(la_pk) else []:
        if exe + ".exe" in files: return os.path.join(root, exe + ".exe")
    return None      # ikke funnet. IKKE sys.exit her - se require_tools under.

MISSING_TOOL = ("FEIL: fant ikke {exe}.exe. Installer ffmpeg (winget install Gyan.FFmpeg) "
                "eller sett FFMPEG_DIR til bin-mappa.")

def require_tools():
    """Sjekk at ffmpeg finnes - foerst naar noe faktisk skal kjoere den.

    Foer sto det sys.exit() rett i _find, paa modulnivaa. Da doede ALT som importerte killclip paa
    en maskin uten ffmpeg paa PATH - inkludert preflight(), som er laget nettopp for aa si fra om
    dette paa en vennlig maate, og tools/queue_preview.py, som bare regner paa tall og ikke trenger
    ffmpeg i det hele tatt. ffmpeg ligger inne i exe-en, saa fra kildekode er det normalt aa ikke
    ha den."""
    for name, path in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)):
        if not path: raise RuntimeError(MISSING_TOOL.format(exe=name))

FFMPEG, FFPROBE = _find("ffmpeg"), _find("ffprobe")
# ROI-er er relative til bildestørrelsen, så de virker på 1080p/1440p/4K og på 9:16-backtracks.
# Under siktet (KILL CONFIRMED / VEHICLE DESTROYED / +$…): 16:9 → 22 % bredde, 10 % høyde fra (39 %, 71 %).
# I Aitum-vertikal 1080x1920 ligger spillet 1:1 i midten (y 660–1740), og feeden ved ca. (190,1330)-(890,1630).
def rois_for(w, h):
    """To soner: (1) feeden under siktet (cockpit/infanteri), (2) penge-feeden øverst til høyre (HUD, alle klasser)."""
    if h > w:   # 9:16-backtrack med spillet 1:1 i midten (Aitum)
        return [f"crop={int(w*0.65)}:{int(h*0.16)}:{int(w*0.175)}:{int(h*0.69)}",
                f"crop={int(w*0.30)}:{int(h*0.06)}:{int(w*0.70)}:{int(h*0.345)}"]
    return [f"crop={int(w*0.22)}:{int(h*0.10)}:{int(w*0.39)}:{int(h*0.71)}",
            f"crop={int(w*0.19)}:{int(h*0.09)}:{int(w*0.80)}:{int(h*0.02)}",
            f"crop={int(w*0.22)}:{int(h*0.19)}:0:{int(h*0.43)}"]   # (3) den ekte kill-feeden: egen rad er hvit -> "[25 m] Offer"
def roi_for(w, h): return rois_for(w, h)[0]
PRE = "scale=2100:-1,format=gray,lutyuv=y='if(gt(val,170),255,0)'"
FEED = re.compile(r"\[\s*(\d{1,4})\s*m\s*\]\s*([A-Za-z0-9'\u2019\-_.]+(?:\s+[A-Za-z0-9'\u2019\-_.]+)*)")
# Only the personal banner under the crosshair may create an event. The money HUD and the kill feed on the
# left show everyone's kills and are cropped away in the 9:16 short, so text there is enrichment, never proof:
# before 0.3.1 a stranger's row in the left feed produced a "kill" the viewer could not see (clip DQkBYvQGW4E).
BANNER = re.compile(r"(KILL\s*C[O0]NF[I1L|]RM[A-Z]*|KILL\s*ASS[I1|]ST|VEH[I1|][A-Z]*\s*DESTR[A-Z]*|HEADSH[O0]T)", re.I)
MONEY = re.compile(r"\+\s?\$\s?([\d,]{3,})")
MIN_FRAMES = 2      # a banner stays up for seconds; a single OCR frame is noise
HOLD_S = 1.5        # ... and those frames must be this close together

def _norm(tok):
    t = re.sub(r"[^A-Z]", "", tok.upper())
    if t.startswith("KILLC"): return "KILLCONFIRMED"
    if t.startswith("KILLASS"): return "KILLASSIST"
    if t.startswith("VEH"): return "VEHICLEDESTROYED"
    if t.startswith("HEADSH"): return "HEADSHOT"
    return t

def _reward_runs(rewards):
    """One entry per banner that appeared, from the reward printed inside the banner itself.
    Two kills in a row often overlap - the second banner replaces the first with no dark frame between
    them - so a change in the amount is what tells them apart. A new amount has to hold for MIN_FRAMES
    frames before we believe it, otherwise a single misread digit would invent a kill."""
    seq = []                       # one amount per frame, the last read of that frame wins
    for t, a in rewards:
        if seq and seq[-1][0] == t: seq[-1] = (t, a)
        else: seq.append((t, a))
    out = []; cur = None; cand = None; cnt = 0; cstart = None
    for t, a in seq:
        if a == cur:               # still the banner we are already counting
            cand = None; cnt = 0; continue
        if a == cand: cnt += 1
        else: cand = a; cnt = 1; cstart = t
        if cnt >= MIN_FRAMES:
            out.append((cstart, a)); cur = a; cand = None; cnt = 0
    return out

def _persist(raw):
    """Keep a kind only where it was read in >= MIN_FRAMES frames no more than HOLD_S apart."""
    by = {}
    for t, kinds in raw:
        for k in kinds: by.setdefault(k, []).append(t)
    keep = set()
    for k, ts in by.items():
        run = [ts[0]]
        for t in ts[1:]:
            if t - run[-1] <= HOLD_S: run.append(t)
            else:
                if len(run) >= MIN_FRAMES: keep |= {(x, k) for x in run}
                run = [t]
        if len(run) >= MIN_FRAMES: keep |= {(x, k) for x in run}
    out = {}
    for t, k in keep: out.setdefault(t, set()).add(k)
    return [(t, sorted(out[t])) for t in sorted(out)]

class TesseractFailed(RuntimeError): pass

def ocr(png):
    """Read one frame. A non-zero exit is raised, never swallowed.

    This matters more than it looks: if Tesseract starts but cannot work - tessdata moved, eng.traineddata
    corrupt, temp dir locked - it exits non-zero with empty output. Returning "" for every frame would look
    exactly like a recording with no kills in it, and a recording with no kills is one the cleanup is
    allowed to delete. A broken install would quietly eat the whole library."""
    if ABORT: return ""
    r = subprocess.run([TESS, png, "-", "--psm", "6"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CF)
    if r.returncode != 0:
        msg = (r.stderr or "").strip().splitlines()
        raise TesseractFailed(f"tesseract exited {r.returncode}: {msg[-1] if msg else 'no message'}")
    return r.stdout or ""

# Hvor mange bilder som leses av EN tesseract-prosess. Tesseract tar en fillist i stedet for ett
# bilde, og skriver sidene etter hverandre med sideskift mellom. Det gjoer at prosessen startes
# noen hundre ganger i stedet for titusener per opptak - og en prosessoppstart er ikke gratis paa
# Windows: Program Compatibility Assistant hekter seg paa hver eneste en, og laa paa 21 % CPU for
# seg selv under en skanning. Maalt 2,7 ganger raskere OCR av samme opptak.
# 200 og ikke "alt i en bunt": en bunt som kjoerer kan ikke avbrytes midt i, og naar spillet starter
# skal KillFeed slippe maskinen med en gang. 200 bilder er noen sekunder.
OCR_BATCH = 200

def _ocr_batch(frames):
    """Les en bunt bilder med en prosess. Returnerer en tekst per bilde, i samme rekkefoelge."""
    if ABORT or not frames: return [""] * len(frames)
    lst = frames[0] + ".list"
    try:
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(frames) + "\n")
        p = subprocess.Popen([TESS, lst, "-", "--psm", "6"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, creationflags=CF)
        _procs.append(p)                      # saa spillvakten kan drepe den sammen med ffmpeg
        try: out, err = p.communicate()
        finally:
            try: _procs.remove(p)
            except ValueError: pass
        if ABORT: return [""] * len(frames)
        if p.returncode != 0:
            msg = (err or b"").decode("utf-8", "replace").strip().splitlines()
            raise TesseractFailed(f"tesseract exited {p.returncode}: {msg[-1] if msg else 'no message'}")
        pages = (out or b"").decode("utf-8", "replace").split("\f")
        if len(pages) != len(frames):
            # Antallet MAA stemme: side nr. n ER bilde nr. n, og bildenummeret er tidspunktet
            # hendelsen faar. Skulle en annen tesseract-versjon skrive sideskiftene annerledes,
            # ville alle kills blitt forskjoevet i tid uten at noe saa galt ut. Da leser vi heller
            # bunten bilde for bilde: tregere, men aldri forskjoevet.
            return [ocr(x) for x in frames]
        return pages
    finally:
        try: os.remove(lst)
        except OSError: pass

def probe(path):
    require_tools()
    r = subprocess.run([FFPROBE,"-v","error","-select_streams","v:0","-show_entries","stream=width,height:format=duration","-of","json",path],capture_output=True,text=True,encoding="utf-8",errors="replace",creationflags=CF)
    j = json.loads(r.stdout); st = j["streams"][0]
    return float(j["format"]["duration"]), int(st["width"]), int(st["height"])

def duration(path):
    return probe(path)[0]

def detect(path, fps, w=None, h=None):
    if w is None: _, w, h = probe(path)
    rois = rois_for(w, h)
    tmp = tempfile.mkdtemp()
    try:
        # én ffmpeg-kjøring, to utganger (én per sone)
        fc = f"[0:v]fps={fps},split={len(rois)}" + "".join(f"[s{i}]" for i in range(len(rois))) + ";" + \
             ";".join(f"[s{i}]{r},{PRE}[o{i}]" for i, r in enumerate(rois))
        # -hwaccel maa staa FOER -i: det er et inngangsvalg. Uten -hwaccel_output_format lastes
        # bildene ned til vanlig minne etterpaa, saa filterkjeden under virker uendret.
        cmd = [FFMPEG,"-v","error"] + (["-hwaccel",HWACCEL] if HWACCEL else []) + ["-i",path,"-filter_complex",fc]
        for i in range(len(rois)):
            cmd += ["-map",f"[o{i}]","-fps_mode","passthrough",os.path.join(tmp,f"z{i}_%05d.png")]
        _run_ffmpeg(cmd)
        texts = {}
        for i in range(len(rois)):
            frames = sorted(glob.glob(os.path.join(tmp,f"z{i}_*.png")))
            batches = [frames[j:j+OCR_BATCH] for j in range(0, len(frames), OCR_BATCH)]
            with ThreadPoolExecutor(workers()) as ex:
                texts[i] = [t for part in ex.map(_ocr_batch, batches) for t in part]
            _check_abort()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n = max(len(v) for v in texts.values()) if texts else 0
    raw = []; feed = []; money = []; reward = []
    for f in range(n):
        t = f / fps
        # zone 0 = the personal banner under the crosshair. It alone decides whether something happened.
        kinds = set()
        if 0 in texts and f < len(texts[0]):
            kinds = {_norm(x) for x in BANNER.findall(texts[0][f])}
            # the banner prints its own reward (+$2,250). We keep it per frame because a change in the
            # amount is the only reliable sign that a second kill landed while the first banner was still up.
            for a in MONEY.findall(texts[0][f]):
                try: reward.append((t, int(a.replace(",", ""))))
                except ValueError: pass
        # zone 1 = money HUD (top right): the amount only, never an event
        if 1 in texts and f < len(texts[1]):
            for a in MONEY.findall(texts[1][f]):
                try: money.append((t, int(a.replace(",", ""))))
                except ValueError: pass
        # zone 2 = the kill feed on the left (16:9 only): distance and victim, never an event - it lists
        # every player's kills, and it is outside the 9:16 crop, so the viewer never sees it
        if 2 in texts and f < len(texts[2]):
            for d, v in FEED.findall(texts[2][f]):
                v = v.strip(" .,:;-_")
                if v and not any(x[2] == v and x[1] == int(d) and t - x[0] < 15 for x in feed[-3:]):   # raden staar ~10 s
                    feed.append((t, int(d), v))
        if kinds: raw.append((t, kinds))
    detect.feed = feed     # (t, avstand_m, offer) - bare 16:9 har sonen
    detect.money = money   # (t, belop) - HUD oeverst til hoeyre
    detect.reward = _reward_runs(reward)   # (t, belop) - ett innslag per banner som dukket opp
    detect.reward_raw = reward             # (t, belop) raatt, ett per ramme - se rapporten under
    return _persist(raw)

def cluster(hits, dur, pre, post, gap, mn, mx):
    """Group hits into clips. A group that would be longer than mx is split at its widest gap between hits
    (recursively) so every short is one kill wave with its own lead-in, instead of a fixed slice that may
    start mid-action or contain no kill at all."""
    if not hits: return []
    groups=[]; s=hits[0][0]; e=hits[0][0]; kinds=set(hits[0][1]); ts=[hits[0][0]]
    for t,k in hits[1:]:
        if t-e<=gap: e=t; kinds|=set(k); ts.append(t)
        else: groups.append((ts,kinds)); ts=[t]; kinds=set(k); e=t
    groups.append((ts,kinds))
    def split(ts):
        if len(ts)<2 or (ts[-1]-ts[0])+pre+post<=mx: return [ts]
        gaps=[(ts[i+1]-ts[i],i) for i in range(len(ts)-1)]
        g,i=max(gaps)
        if g<3: # kills too dense to split cleanly: cut at mx like before
            out=[]; a=ts[0]
            while ts and ts[-1]-a+pre+post>mx:
                part=[t for t in ts if t-a+pre+post<=mx] or ts[:1]; out.append(part); ts=ts[len(part):]; a=ts[0] if ts else a
            if ts: out.append(ts)
            return out
        return split(ts[:i+1])+split(ts[i+1:])
    out=[]
    for ts,k in groups:
        for part in split(ts):
            a=max(0,part[0]-pre); b=min(dur,part[-1]+post)
            if b-a<mn:
                need=mn-(b-a); a=max(0,a-need/2); b=min(dur,a+mn)
            out.append((round(a,2),round(b,2),sorted(k)))
    out.sort(); merged=[]
    for a,b,k in out:
        if merged and a<=merged[-1][1] and max(b,merged[-1][1])-merged[-1][0]<=mx:
            merged[-1]=(merged[-1][0],max(b,merged[-1][1]),sorted(set(merged[-1][2])|set(k)))
        else: merged.append((a,b,k))
    return merged

# style=stack: the whole 16:9 picture across the top (so the HUD and the kill banner are readable)
# and a zoomed centre crop below (so the action is big). 1080x1920 = 608 top + 1312 bottom.
STACK_TOP_H = 608                      # 1080 wide at 16:9
STACK_BOT_H = 1920 - STACK_TOP_H       # 1312
STACK_ZOOM_H = 0.674                   # how much of the source height the bottom crop covers -> ~1.8x
_SZW = STACK_ZOOM_H * 1080.0 / STACK_BOT_H     # matching width fraction, so nothing is squashed

def cut(path, a, b, out, w=None, h=None, style="center"):
    """Klipper og leverer alltid 1080x1920. 9:16-input går rett gjennom; 16:9 får midtutsnitt
    (style=center), full bredde over uskarp bakgrunn (style=blur) eller delt bilde (style=stack)."""
    if w is None: _, w, h = probe(path)
    if h > w:
        vf = "scale=1080:1920:flags=lanczos"
    elif style == "blur":
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.15[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    elif style == "stack":
        vf = (f"split[t][z];"
              f"[t]scale=1080:{STACK_TOP_H}:force_original_aspect_ratio=decrease,"
              f"pad=1080:{STACK_TOP_H}:(ow-iw)/2:(oh-ih)/2:black[top];"
              f"[z]crop=ih*{_SZW:.4f}:ih*{STACK_ZOOM_H}:(iw-ih*{_SZW:.4f})/2:(ih-ih*{STACK_ZOOM_H})/2,"
              f"scale=1080:{STACK_BOT_H}:flags=lanczos[bot];"
              f"[top][bot]vstack,drawbox=x=0:y={STACK_TOP_H-2}:w=1080:h=4:color=black@0.55:t=fill")
    else:
        vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos"
    wm = os.path.join(_appdir(), "watermark.png")
    # -ss and -t both belong to the INPUT. Putting -t after -i but before the watermark -i made it an
    # option for the watermark instead, so the packaged build (the only one with a watermark) wrote
    # everything from the cut point to the end of the recording - 15-second clips of 1.4 GB.
    cmd = [FFMPEG,"-v","error","-y","-ss",str(a),"-t",str(b-a),"-i",path]
    if os.path.exists(wm) and getattr(sys, "frozen", False):   # bare i den pakkede alfaen
        cmd += ["-i", wm, "-filter_complex", f"[0:v]{vf}[v];[v][1:v]overlay=W-w-24:H-h-140[vo]", "-map", "[vo]"]
    else:
        cmd += ["-map","0:v:0","-vf",vf]
    cmd += ["-map","0:a:0?","-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart","-t",str(b-a),out]
    _run_ffmpeg(cmd)

def cut_plain(path, a, b, out):
    """Klipp ut et stykke slik det er - samme bildeformat, ingen 9:16-omforming og ingen vannmerke.
    Brukes til recap-banken: smaa 16:9-biter som recapen limes av etter at opptaket er slettet.
    Samme -ss/-t-rekkefolge som cut(): begge hoerer til inngangen."""
    cmd = [FFMPEG, "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", path,
           "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
           "-t", str(b - a), out]
    _run_ffmpeg(cmd)

def summarize(events, hits_in_seg):
    """Teller hendelser fra banneret. Penger kommer fra penge-sonen, ikke herfra."""
    kills = sum(1 for e in events if e.startswith("KILLCONFIRMED"))
    assists = sum(1 for e in events if "ASSIST" in e)
    veh = sum(1 for e in events if "DESTROYED" in e)
    return kills, assists, veh, 0

def banner_starts(hits, pred, rruns=(), gap=3.0):
    """Naar hvert kill SKJEDDE, regnet over hele opptaket - ikke per klippvindu.

    To feller, og begge er maalt paa ekte opptak:

    1) Banneret staar paa i aatte-ni sekunder. Teller man bannerbilder inne i et klippvindu, teller
       man ogsaa halen av et banner som alt sto der da vinduet aapnet - og det killet skjedde foer
       klippet begynte. Det ga en short med tittelen "3 kills" der tilskueren ser ett.
    2) `rruns` (= detect.reward, som allerede er _reward_runs) har ett innslag per banner, og det
       innslaget ligger som regel ETT TIL TRE SEKUNDER inne i banneret, ikke paa foerste bilde: av
       531 rader laa 51 paa starten og 144 inne i et banner som alt var talt. Spoer man "kom det en
       ny beloepssum mellom forrige bilde og dette?" blir hvert banner derfor talt to ganger - 274
       kills blir til 415.

    Saa: del bildene i sammenhengende bannere (hull stoerre enn `gap` = nytt banner). Hvert banner
    er ett kill. Har ETT banner flere beloepsrader i seg, er hver ekstra rad et kill til - det er
    det eneste som avsloerer to kills under sekundet, for banneret blir aldri moerkt mellom dem.
    Maalt paa fire opptak: 16 av 313 bannere har flere beloep, og det er de ekte dobbelkillene."""
    ts = sorted(t for t, kk in hits if any(pred(x) for x in kk))
    if not ts: return []
    rr = sorted(float(r) for r in (rruns or []))
    runs = []
    for t in ts:
        if runs and t - runs[-1][-1] <= gap: runs[-1].append(t)
        else: runs.append([t])
    out = []
    for run in runs:
        a, b = run[0], run[-1]
        out.append(a)                                        # selve banneret
        inside = [r for r in rr if a - 0.5 <= r <= b + 0.5]
        out.extend(inside[1:])                               # beloep nr. 2 og utover = flere kills
    return sorted(out)

def pace_ok(ev, per=5.0, need=3):
    """Er dette tett nok til aa vaere verdt aa poste?

    En regel, to maater aa snakke om den: "en dobbel pluss noe" og "ett kill hvert femte sekund" er
    det samme kravet. `need` hendelser teller som tette hvis de ligger innenfor per*(need-1)
    sekunder - tre kills innen ti sekunder, fire innen femten. Et dobbelkill pluss ett mer passerer,
    tre spredte kills over nitti sekunder gjoer det ikke.

    ev er tidspunkt for kills og kjoeretoey-kills i klippet, sortert. Returnerer (ok, tetteste).
    `tetteste` er flest hendelser funnet innenfor vinduet, slik at den kan brukes i poengscoren."""
    ev = sorted(ev)
    if len(ev) < need: return False, len(ev)
    win = per * (need - 1)
    best = 0
    for i in range(len(ev)):
        n = sum(1 for x in ev[i:] if x <= ev[i] + win)
        best = max(best, n)
    return best >= need, best

def collapse_pairs(kill_starts, veh_starts, within=1.5):
    """Hendelseslista slik tilskueren ser den: ett oeyeblikk = en hendelse.

    Et okkupert kjoeretoey fyrer KILL CONFIRMED og VEHICLE DESTROYED i samme sekund. Det er EN ting
    som skjer, men to bannere - og et tetthetsmaal som teller bannere leser det som et dobbelkill.
    Det er samme feil som ga titler paa "2 kills, 2 vehicles destroyed", bare flyttet inn i
    Publiser-regelen. Her slaas paret sammen til en hendelse foer tettheten maales."""
    out = list(veh_starts)
    for t in kill_starts:
        if not any(abs(t - v) <= within for v in veh_starts): out.append(t)
    return sorted(out)

def worth_posting(ev, double_s=3.0, pace_s=5.0, pace_need=3):
    """Publiser-regelen: enten et ekte dobbelkill, eller et tempo paa ett kill hvert pace_s sekund.

    To ting, fordi de er to forskjellige gode oeyeblikk:
      * to hendelser innenfor double_s - banneret rekker ikke bli moerkt, det ser ut som ett sloss
      * pace_need hendelser innenfor pace_s*(pace_need-1) - en rekke som holder tempoet oppe
    Tre spredte enkeltkills passerer ingen av dem, uansett hvor mange de er. Det var hele poenget:
    en short som heter "3 kills" skal vise tre kills som hoerer sammen, ikke tre tilfeldige.

    Returnerer (ok, tetteste, hvorfor)."""
    ev = sorted(ev)
    dbl, dn = pace_ok(ev, per=double_s, need=2)
    pac, pn = pace_ok(ev, per=pace_s, need=pace_need)
    if dbl: return True, max(dn, pn), "double"
    if pac: return True, max(dn, pn), "pace"
    return False, max(dn, pn), ""

def event_bursts(hits, within=3.0):
    """The moments something happened, grouped. A kill and the vehicle it destroyed fire together and are
    one moment, not two. Returns the start time of each burst."""
    ev = sorted({t for t, kk in hits if any(x.startswith(("KILLCONFIRMED", "VEHICLE")) for x in kk)})
    out = []
    for t in ev:
        if out and t - out[-1][-1] <= within: out[-1].append(t)
        else: out.append([t])
    return [b[0] for b in out]

def is_lonely_single(hits, a, b, kills, veh, gap_s=15.0, bursts=None):
    """True when this stretch is one lone kill with nothing else near it.

    Measured over six sessions, 76 % of every clip cut was exactly this: a single kill with no other kill
    or vehicle inside 15 s. None of them ever reached Publish - the rules need two kills or a vehicle - so
    they only ever cost clipping time and disk. A kill together with the vehicle it destroyed is two events
    in one moment and is NOT lonely, which matters: those are among the best-performing clips on the channel.

    A vehicle kill on its own is never lonely either. It carries a clip by itself under the Publish rules
    (min_vehicles), so dropping it here would throw away something the next step wanted to post."""
    if (veh or 0) >= 1: return False
    if (kills or 0) != 1: return False
    if bursts is None: bursts = event_bursts(hits)
    inside = [c for c in bursts if a <= c <= b]
    if len(inside) != 1: return False
    c = inside[0]
    return not any(x != c and abs(x - c) <= gap_s for x in bursts)

SCORE_FREE_S = 22      # seconds a clip may run before length starts costing it

def solo_kills_of(m):
    """Kills in this clip that were not a vehicle kill.

    Clips cut before solo_kills existed do not carry it, but the number is recoverable: a kill and the
    vehicle it destroyed land on the same instant, so they appear as a repeated timestamp in abs_events.
    Deriving it keeps an old clip and a new one ranked on the same scale in the same queue."""
    s = m.get("solo_kills")
    if s is not None: return int(s)
    ev = m.get("abs_events") or []
    paired = len(ev) - len(set(ev))
    return max(0, int(m.get("kills") or 0) - paired)

def clip_score(kills, veh, maxd=0, length=0):
    """Ranking for the upload queue: one point a kill, two a vehicle, one per 100 m, minus half a point
    for every second over SCORE_FREE_S.

    `kills` is kills that were NOT a vehicle kill (see solo_kills_of). A vehicle kill is worth 2, not 3:
    counting its KILL CONFIRMED banner as well would make one vehicle kill tie with a three-kill streak,
    and a three-kill streak is the better clip.

    It is an ordering you can do in your head, not a prediction. Measured against 17 uploads on the
    ThatsBonkers channel (28.09.2026) no weighting of kills, vehicles or distance correlated with views
    at all - every candidate landed between -0.36 and +0.09 rank correlation, which is noise at that
    sample size. So the score's job is to keep the obviously weak out and sort the rest legibly; picking
    what is actually worth posting is a judgement call, not a formula. Length is the one term with a
    plausible mechanism behind it: viewers watch ~17-23 s whatever the clip's length."""
    return round(kills * 1 + veh * 2 + (maxd // 100) - max(0.0, (length or 0) - SCORE_FREE_S) * 0.5, 1)

def auto_title(kills, assists, veh, money, when, maxd=0):
    """`kills` here means kills that were NOT a vehicle kill - see solo_kills in _run.

    Destroying an occupied vehicle fires KILL CONFIRMED and VEHICLE DESTROYED in the same instant.
    Listing both made a clip of two vehicle kills read as "2 kills, 2 vehicles destroyed" - four
    achievements for something the viewer saw happen twice.

    `maxd` is kept in the signature and in the clip's data, but no longer appears in the title. The
    distance came from the kill feed down the left side, which is cropped away in a 9:16 short - so a
    title said "(161 m)" about something the viewer cannot see, and nothing on screen confirms it.
    It still sorts the browser (Longest shot) and still counts in the score."""
    bits=[]
    if kills: bits.append(f"{kills} kill{'s' if kills>1 else ''}")
    if veh: bits.append(f"{veh} vehicle{'s' if veh>1 else ''} destroyed")
    if assists and not kills and not veh: bits.append("kill assist")
    t = "WARDOGS" + (" – " + ", ".join(bits) if bits else "")
    return (t + " #shorts")[:100]

def process(inp, outdir, fps=2, pre=12, post=4, gap=12, mn=18, mx=40, style="center", dry=False,
            lonely_gap=0.0, log=print):
    """Kjør hele løypa på én fil. Returnerer liste over segment-dicts.
    lonely_gap > 0 hopper over klipp som bare inneholder ett ensomt kill (se is_lonely_single)."""
    class A: pass
    A.inp, A.outdir, A.fps, A.pre, A.post, A.gap, A.min, A.max, A.style, A.dry = inp, outdir, fps, pre, post, gap, mn, mx, style, dry
    A.lonely_gap = lonely_gap
    return _run(A, log)

def file_start_epoch(path, dur):
    """Klokketid (epoch) for sekund 0 i fila. Aitum/OBS-backtracks har lagringstidspunkt (= slutt) i navnet,
    vanlige OBS-opptak har starttidspunkt i navnet. Uten dato i navnet: mtime = slutt."""
    import datetime as _dt
    base=os.path.basename(path)
    m=re.search(r"(\d{4})-(\d{2})-(\d{2})[ _T-](\d{2})[-.:](\d{2})[-.:](\d{2})", base)
    if m:
        ts=_dt.datetime(*map(int,m.groups())).timestamp()
        return ts-dur if ("backtrack" in base.lower() or "replay" in base.lower()) else ts
    return os.path.getmtime(path)-dur

_last_hits = []    # what the last detect() found - the cleanup uses it as proof that OCR actually worked

def _run(A, log=print):
    global _last_hits
    dur,W,H=probe(A.inp); hits=detect(A.inp,A.fps,W,H); _last_hits=hits
    feed=getattr(detect,"feed",[]) or []
    cash=getattr(detect,"money",[]) or []
    t0abs=file_start_epoch(A.inp,dur)
    segs=cluster(hits,dur,A.pre,A.post,A.gap,A.min,A.max)
    # Naar hvert kill skjedde, regnet EN gang over hele opptaket. Maa gjoeres her og ikke per vindu:
    # et banner som alt sto paa skjermen da vinduet aapnet hoerer til klippet foer, ikke dette.
    _rr_all=[t for t,_ in (getattr(detect,"reward",None) or [])]
    _kill_starts=banner_starts(hits, lambda x: x.startswith("KILLCONFIRMED"), _rr_all)
    _veh_starts=banner_starts(hits, lambda x: "DESTROYED" in x, _rr_all)
    bursts=event_bursts(hits)
    base=os.path.splitext(os.path.basename(A.inp))[0]
    when = (re.search(r"(\d{4})-(\d{2})-(\d{2})", base) or [None,"","",""])
    os.makedirs(A.outdir,exist_ok=True)
    # reward MAA ligge i rapporten. Beloepssummen i banneret er det eneste som skiller to raske kills
    # fra ett - banneret blir aldri moerkt mellom dem - og uten den i rapporten kan ingenting
    # etterpaa se et dobbelkill. Det gjorde at minste maalte avstand mellom to kill i seks oekter
    # var 6,5 sekunder, som er en egenskap ved metoden og ikke ved spillingen.
    # reward_raw og money ER tellingen vi ikke har hatt. `reward` er ferdig behandlet - ett innslag
    # per banner - og den behandlingen kaster nettopp det som skiller to kills: banneret viser TO tall
    # paa samme sted, beloepet for killet og en loepende sum, og summen stiger for hvert kill uansett
    # hva killet var verdt. Uten raatallene kan ingen regne om tellingen etterpaa, og uten pengeteller-
    # en oeverst til hoeyre (`money`, som ble lest og kastet) finnes ingen uavhengig kontroll. Begge
    # koster noen kilobyte i rapporten og sparer en omskanning paa timer hver gang regelen skal proeves.
    report={"input":A.inp,"duration":dur,"width":W,"height":H,"hits":[(t,k) for t,k in hits],
            "reward":[(t,a) for t,a in (getattr(detect,"reward",None) or [])],
            "reward_raw":[(t,a) for t,a in (getattr(detect,"reward_raw",None) or [])],
            "money":[(t,a) for t,a in cash],
            "feed":[{"t":t,"abs":round(t0abs+t,1),"dist_m":d,"victim":v} for t,d,v in feed],"segments":[]}
    for i,(a,b,k) in enumerate(segs,1):
        name=f"{base}-auto{i:02d}-{a:05.1f}-{b:05.1f}.mp4"
        out=os.path.join(A.outdir,name)
        ev=[]
        for t,kk in hits:
            if a<=t<=b: ev+=kk
        kills,assists,veh,_=summarize(sorted(set(ev)),None)
        money=max((c for t,c in cash if a<=t<=b), default=0)
        def waves(pred, allstarts):
            """Bare kills som BEGYNTE inne i vinduet. Startene er regnet over hele opptaket, saa et
            banner som alt sto paa skjermen da vinduet aapnet teller ikke her - det killet hoerer til
            klippet foer dette."""
            starts=[t for t in allstarts if a<=t<=b]
            return len(starts), starts
        first_hit=min((t for t,_ in hits if a<=t<=b),default=a)
        clamped=a<=0.05 and first_hit<A.pre*0.75   # ville hatt pre-roll, men fila starter midt i action - selve killet kan mangle
        kills,kt=waves(lambda x: x.startswith("KILLCONFIRMED"), _kill_starts)
        veh,vt=waves(lambda x: "DESTROYED" in x, _veh_starts)
        # kills and veh stay as the raw banner counts - the Publish rule (min_kills / min_vehicles) is
        # built on them, and narrowing them here would drop the vehicle clips out of Publish entirely.
        # The title uses solo_kills instead, so one vehicle kill is named once rather than twice.
        paired = sum(1 for k in kt if any(abs(k - v) <= 1.5 for v in vt))
        solo_kills = max(0, kills - paired)
        if A.lonely_gap and is_lonely_single(hits, a, b, kills, veh, A.lonely_gap, bursts):
            log(f"  hoppet over {a:.1f}-{b:.1f}s: ensomt enkeltkill (ingenting innen {A.lonely_gap:.0f} s)")
            continue
        # a feed row is only ours when the banner fired at about the same moment - the feed lists everyone
        ktimes=[t for t,kk in hits if a<=t<=b and any(x.startswith(("KILLCONFIRMED","VEHICLE")) for x in kk)]
        details=[{"t":t,"abs":round(t0abs+t,1),"dist_m":d,"victim":v} for t,d,v in feed
                 if a-3<=t<=b+3 and any(abs(t-k)<=2.5 for k in ktimes)]
        maxd=max((x["dist_m"] for x in details),default=0)
        side={"file":name,"source":os.path.basename(A.inp),"source_res":f"{W}x{H}","start":a,"end":b,"len":round(b-a,1),
              "events":sorted(set(ev)),"kills":kills,"vehicles":veh,"money":money,
              "abs_start":round(t0abs+a,1),"abs_events":[round(t0abs+t,1) for t in sorted(kt+vt)],"clamped_start":clamped,
              "kill_details":details,"max_dist_m":maxd,
              "score":clip_score(solo_kills,veh,maxd,b-a),
              "solo_kills":solo_kills,"vehicle_kills":paired,
              "title":auto_title(solo_kills,assists,veh,money,when,maxd)}
        report["segments"].append(side)
        if not A.dry:
            cut(A.inp,a,b,out,W,H,A.style)
            json.dump(side,open(os.path.splitext(out)[0]+".json","w",encoding="utf-8"),indent=1)
            open(os.path.splitext(out)[0]+".txt","w",encoding="utf-8").write(side["title"]+"\n\n"+", ".join(side["events"])+"\n")
        log(f"  klipp {i}: {a:.1f}-{b:.1f}s ({b-a:.0f}s) {side['title']}")
    json.dump(report,open(os.path.join(A.outdir,base+"-auto.json"),"w",encoding="utf-8"),indent=1)
    return report["segments"]

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("outdir")
    ap.add_argument("--fps",type=float,default=2); ap.add_argument("--pre",type=float,default=12)
    ap.add_argument("--post",type=float,default=4); ap.add_argument("--gap",type=float,default=12)
    ap.add_argument("--min",type=float,default=18); ap.add_argument("--max",type=float,default=40)
    ap.add_argument("--dry",action="store_true")
    ap.add_argument("--style",default="center",choices=["center","blur","stack"],help="9:16-stil for 16:9-input")
    ap.add_argument("--lonely-gap",dest="lonely_gap",type=float,default=0.0,
                    help="hopp over klipp med ett ensomt kill og ingenting innen N sekunder (0 = av)")
    A=ap.parse_args()
    segs=_run(A, log=lambda m: print(m, file=sys.stderr))   # logg til stderr, JSON til stdout
    print(json.dumps({"segments":[{k:v for k,v in x.items() if k in('file','len','kills','vehicles','money','score','title')} for x in segs]},indent=1))
