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
    cands += [os.path.join(la, "Microsoft", "WinGet", "Links", exe + ".exe")]
    cands += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "ffmpeg-*", "bin", exe + ".exe"))
    cands += glob.glob(os.path.join("C:\\", "ffmpeg*", "bin", exe + ".exe")) + glob.glob(os.path.join("C:\\", "Program Files", "ffmpeg*", "bin", exe + ".exe"))
    for c in cands:
        if os.path.exists(c): return c
    la_pk = os.path.join(la, "Microsoft", "WinGet", "Packages")
    for root, dirs, files in os.walk(la_pk) if os.path.isdir(la_pk) else []:
        if exe + ".exe" in files: return os.path.join(root, exe + ".exe")
    sys.exit(f"FEIL: fant ikke {exe}.exe. Installer ffmpeg (winget install Gyan.FFmpeg) eller sett FFMPEG_DIR til bin-mappa.")
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
PAT = re.compile(r"(KILL\s*CONFIRMED|KILL\s*ASSIST|VEHICLE\s*DESTROYED|VEH[A-Z]*\s*DESTR[A-Z]*|DESTROYED|DELIVERED|HEADSHOT|\bKILL\b|ASSIST|\+\$\s?[\d,]{3,})", re.I)

def ocr(png):
    r = subprocess.run([TESS, png, "-", "--psm", "6"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CF)
    return r.stdout or ""

def probe(path):
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
        cmd = [FFMPEG,"-v","error","-i",path,"-filter_complex",fc]
        for i in range(len(rois)):
            cmd += ["-map",f"[o{i}]","-fps_mode","passthrough",os.path.join(tmp,f"z{i}_%05d.png")]
        subprocess.run(cmd,check=True,creationflags=CF)
        texts = {}
        for i in range(len(rois)):
            frames = sorted(glob.glob(os.path.join(tmp,f"z{i}_*.png")))
            with ThreadPoolExecutor(max(2, os.cpu_count() or 4)) as ex:
                texts[i] = list(ex.map(ocr, frames))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n = max(len(v) for v in texts.values()) if texts else 0
    hits = []; feed = []
    for f in range(n):
        m = []
        for i in texts:
            if f < len(texts[i]): m += PAT.findall(texts[i][f])
        if 2 in texts and f < len(texts[2]):
            for d, v in FEED.findall(texts[2][f]):
                v = v.strip(" .,:;-_")
                if v and not any(x[2] == v and x[1] == int(d) and f/fps - x[0] < 15 for x in feed[-3:]):   # raden staar ~10 s
                    feed.append((f/fps, int(d), v))
        m = [x.upper().replace(" ","") for x in m]
        m = [("KILLCONFIRMED" if x == "KILL" else x) for x in m]   # HUD-feeden skriver bare KILL
        if any(not x.startswith("+$") for x in m):   # penger alene (sone-tick, tips) teller ikke som hendelse
            hits.append((f/fps, sorted(set(m))))
    detect.feed = feed   # (t, avstand_m, offer) fra kill-feeden - bare 16:9 har sonen
    return hits

def cluster(hits, dur, pre, post, gap, mn, mx):
    if not hits: return []
    segs=[]; s=hits[0][0]; e=hits[0][0]; kinds=set(hits[0][1])
    for t,k in hits[1:]:
        if t-e<=gap: e=t; kinds|=set(k)
        else: segs.append([s,e,kinds]); s=t; e=t; kinds=set(k)
    segs.append([s,e,kinds])
    out=[]
    for s,e,k in segs:
        a=max(0,s-pre); b=min(dur,e+post)
        if b-a<mn:
            need=mn-(b-a); a=max(0,a-need/2); b=min(dur,a+mn)
        while b-a>mx:
            out.append((round(a,2),round(a+mx,2),sorted(k))); a=a+mx-3
        out.append((round(a,2),round(b,2),sorted(k)))
    out.sort(); merged=[]
    for a,b,k in out:
        if merged and a<=merged[-1][1] and max(b,merged[-1][1])-merged[-1][0]<=mx:
            merged[-1]=(merged[-1][0],max(b,merged[-1][1]),sorted(set(merged[-1][2])|set(k)))
        else: merged.append((a,b,k))
    return merged

def cut(path, a, b, out, w=None, h=None, style="center"):
    """Klipper og leverer alltid 1080x1920. 9:16-input går rett gjennom; 16:9 får midtutsnitt
    (style=center) eller full bredde over uskarp bakgrunn (style=blur)."""
    if w is None: _, w, h = probe(path)
    if h > w:
        vf = "scale=1080:1920:flags=lanczos"
    elif style == "blur":
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.15[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    else:
        vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos"
    wm = os.path.join(_appdir(), "watermark.png")
    cmd = [FFMPEG,"-v","error","-y","-ss",str(a),"-i",path,"-t",str(b-a)]
    if os.path.exists(wm) and getattr(sys, "frozen", False):   # bare i den pakkede alfaen
        cmd += ["-i", wm, "-filter_complex", f"[0:v]{vf}[v];[v][1:v]overlay=W-w-24:H-h-140[vo]", "-map", "[vo]"]
    else:
        cmd += ["-map","0:v:0","-vf",vf]
    cmd += ["-map","0:a:0","-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",out]
    subprocess.run(cmd,check=True,creationflags=CF)

def summarize(events, hits_in_seg):
    """Teller hendelser og finner største $-beløp for auto-tittel."""
    kills = sum(1 for e in events if e.startswith("KILLCONFIRMED"))
    assists = sum(1 for e in events if "ASSIST" in e)
    veh = sum(1 for e in events if "DESTROYED" in e)
    money = 0
    for e in events:
        m = re.match(r"\+\$([\d,]+)", e)
        if m:
            try: money = max(money, int(m.group(1).replace(",","").rstrip(",") or 0))
            except ValueError: pass
    return kills, assists, veh, money

def auto_title(kills, assists, veh, money, when, maxd=0):
    bits=[]
    if kills: bits.append(f"{kills} kill{'s' if kills>1 else ''}" + (f" ({maxd} m)" if maxd >= 100 else ""))
    if veh: bits.append(f"{veh} vehicle{'s' if veh>1 else ''} destroyed")
    if assists and not kills: bits.append("kill assist")
    t = "WARDOGS" + (" – " + ", ".join(bits) if bits else "")
    if money: t += f" (+${money:,})"
    return (t + " #shorts")[:100]

def process(inp, outdir, fps=2, pre=12, post=4, gap=12, mn=18, mx=40, style="center", dry=False, log=print):
    """Kjør hele løypa på én fil. Returnerer liste over segment-dicts."""
    class A: pass
    A.inp, A.outdir, A.fps, A.pre, A.post, A.gap, A.min, A.max, A.style, A.dry = inp, outdir, fps, pre, post, gap, mn, mx, style, dry
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

def _run(A, log=print):
    dur,W,H=probe(A.inp); hits=detect(A.inp,A.fps,W,H)
    feed=getattr(detect,"feed",[]) or []
    t0abs=file_start_epoch(A.inp,dur)
    segs=cluster(hits,dur,A.pre,A.post,A.gap,A.min,A.max)
    base=os.path.splitext(os.path.basename(A.inp))[0]
    when = (re.search(r"(\d{4})-(\d{2})-(\d{2})", base) or [None,"","",""])
    os.makedirs(A.outdir,exist_ok=True)
    report={"input":A.inp,"duration":dur,"hits":[(t,k) for t,k in hits],
            "feed":[{"t":t,"abs":round(t0abs+t,1),"dist_m":d,"victim":v} for t,d,v in feed],"segments":[]}
    for i,(a,b,k) in enumerate(segs,1):
        name=f"{base}-auto{i:02d}-{a:05.1f}-{b:05.1f}.mp4"
        out=os.path.join(A.outdir,name)
        ev=[]
        for t,kk in hits:
            if a<=t<=b: ev+=kk
        kills,assists,veh,money=summarize(sorted(set(ev)),None)
        def waves(pred):
            ts=[t for t,kk in hits if a<=t<=b and any(pred(x) for x in kk)]
            n=0; last=-99; starts=[]
            for t in ts:
                if t-last>3: n+=1; starts.append(t)
                last=t
            return n, starts
        first_hit=min((t for t,_ in hits if a<=t<=b),default=a)
        clamped=a<=0.05 and first_hit<A.pre*0.75   # ville hatt pre-roll, men fila starter midt i action - selve killet kan mangle
        kills,kt=waves(lambda x: x.startswith("KILLCONFIRMED"))
        veh,vt=waves(lambda x: "DESTROYED" in x)
        details=[{"t":t,"abs":round(t0abs+t,1),"dist_m":d,"victim":v} for t,d,v in feed if a-3<=t<=b+3]
        maxd=max((x["dist_m"] for x in details),default=0)
        side={"file":name,"source":os.path.basename(A.inp),"source_res":f"{W}x{H}","start":a,"end":b,"len":round(b-a,1),
              "events":sorted(set(ev)),"kills":kills,"vehicles":veh,"money":money,
              "abs_start":round(t0abs+a,1),"abs_events":[round(t0abs+t,1) for t in sorted(kt+vt)],"clamped_start":clamped,
              "kill_details":details,"max_dist_m":maxd,
              "score":kills*3+veh*4+money//1000+maxd//100,
              "title":auto_title(kills,assists,veh,money,when,maxd)}
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
    ap.add_argument("--style",default="center",choices=["center","blur"],help="9:16-stil for 16:9-input")
    A=ap.parse_args()
    segs=_run(A, log=lambda m: print(m, file=sys.stderr))   # logg til stderr, JSON til stdout
    print(json.dumps({"segments":[{k:v for k,v in x.items() if k in('file','len','kills','vehicles','money','score','title')} for x in segs]},indent=1))
