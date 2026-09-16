#!/usr/bin/env python3
"""run_daily.py – nattjobb: klipp alle nye backtracks, last opp klippene som private shorts.

  1. Alle *.mkv i config.backtracks_dir som ikke står i processed.json → killclip.py → config.clips_dir
  2. yt_upload.py → laster opp nye klipp (private), fører state.json
  3. Logg til run_daily.log

Kjør manuelt: python run_daily.py [--no-upload] [--limit N]
"""
import os, sys, json, glob, subprocess, datetime, argparse, time, re

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
PROC = os.path.join(HERE, "processed.json")
LOG = os.path.join(HERE, "run_daily.log")

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--limit", type=int, default=cfg.get("max_backtracks_per_run", 60))
    A = ap.parse_args()
    try: proc = json.load(open(PROC, encoding="utf-8"))
    except Exception: proc = {}
    os.makedirs(cfg["clips_dir"], exist_ok=True)
    kc = cfg.get("killclip", {})
    dirs = [cfg["backtracks_dir"]] + [d for d in cfg.get("extra_source_dirs", []) if d and os.path.isdir(d)]
    files = []
    for d in dirs:
        for ext in ("*.mkv", "*.mp4", "*.mov"):
            files += glob.glob(os.path.join(d, ext))
    files = sorted(set(files))
    files = [f for f in files if os.path.basename(f) not in proc and time.time() - os.path.getmtime(f) > 300]
    log(f"Steg 1/2: {len(files)} nye opptak/backtracks i {', '.join(dirs)} skal klippes (1-2 min per backtrack, 10-30 min per helt game) -> {cfg['clips_dir']}")
    for f in files[:A.limit]:
        args = [sys.executable, os.path.join(HERE, "killclip.py"), f, cfg["clips_dir"]]
        for k in ("fps", "pre", "post", "gap", "min", "max"):
            if k in kc: args += [f"--{k}", str(kc[k])]
        t0 = time.time()
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"FEIL {os.path.basename(f)}: {r.stderr[-400:]}")
            proc[os.path.basename(f)] = {"error": r.stderr[-200:], "at": datetime.datetime.now().isoformat()}
        else:
            try: n = len(json.loads(r.stdout[r.stdout.index("{"):])["segments"])
            except Exception: n = -1
            log(f"OK   {os.path.basename(f)}: {n} klipp ({time.time()-t0:.0f} s)" + ("" if n else "  (ingen kill-tekst funnet)"))
            proc[os.path.basename(f)] = {"clips": n, "at": datetime.datetime.now().isoformat()}
        json.dump(proc, open(PROC, "w", encoding="utf-8"), indent=1)
    problems = []
    if not A.no_upload:
        log("Steg 2/2: laster opp nye klipp til YouTube som PRIVATE (beste score forst, maks per kjoring fra config) ...")
        pr = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "yt_upload.py")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        qualifying = None
        for line in pr.stdout:
            t = line.rstrip()
            log("  " + t)
            if "FEIL" in t or "ADVARSEL" in t: problems.append(t.strip()[:120])
            m2 = re.match(r"\s*(\d+) klipp kvalifiserer", t)
            if m2: qualifying = int(m2.group(1))
        pr.wait()
        if pr.returncode != 0: problems.append(f"yt_upload exit {pr.returncode}")
        if qualifying == 0: problems.append("Koen er tom - ingen multikill/vehicle-klipp igjen. Paa tide aa spille!")
        log("Opplasting ferdig (exit %d)." % pr.returncode)

    # ---- Steg 3/3: rydding - slett det som er ferdig brukt (styres av config.cleanup) ----
    try:
        state = json.load(open(os.path.join(HERE, "state.json"), encoding="utf-8"))
    except Exception:
        state = {}
    cl = cfg.get("cleanup", {})
    now = time.time()
    def rm(path, why):
        try:
            os.remove(path); log(f"Ryddet: {os.path.basename(path)} ({why})")
        except Exception: pass
    done = set(state.get("uploaded", {})) | set(state.get("duplicate", {})) | set(state.get("expired", {}))
    d1 = cl.get("uploaded_clip_days", 7)
    for f in glob.glob(os.path.join(cfg["clips_dir"], "*.mp4")):
        base = os.path.basename(f)
        why = "lastet opp" if base in state.get("uploaded", {}) else ("duplikat/utlopt" if base in done else None)
        if why and now - os.path.getmtime(f) > d1 * 86400:
            rm(f, why + f", eldre enn {d1} d")
            for ext in (".json", ".txt"): rm(os.path.splitext(f)[0] + ext, "sidecar")
    d2 = cl.get("source_days", 14)
    try:
        proc2 = json.load(open(PROC, encoding="utf-8"))
    except Exception:
        proc2 = {}
    src_dirs = [cfg["backtracks_dir"]] + [d for d in cfg.get("extra_source_dirs", []) if d and os.path.isdir(d)]
    for d in src_dirs:
        for ext in ("*.mkv", "*.mp4", "*.mov"):
            for f in glob.glob(os.path.join(d, ext)):
                if os.path.basename(f) in proc2 and now - os.path.getmtime(f) > d2 * 86400:
                    rm(f, f"ferdig klippet, eldre enn {d2} d")

    # ---- varsling: msgbox bare naar noe er galt eller koen er tom ----
    if problems and cfg.get("varsling", "msgbox") == "msgbox":
        msg = "KillFeed nattjobb:\n\n" + "\n".join(problems[:8])
        ps = ("Add-Type -AssemblyName System.Windows.Forms;"
              "[System.Windows.Forms.MessageBox]::Show('%s','KillFeed auto-clips')" % msg.replace("'", "''"))
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log(f"Varsel vist (msgbox): {len(problems)} punkt(er)")

if __name__ == "__main__":
    main()
