#!/usr/bin/env python3
"""run_daily.py – nightly job on top of the KillFeed core.

  1. Clip new recordings with kf_core (same settings + ledger as the tray app). Skipped when the tray app
     is running – it clips by itself, and two clippers on one ledger is a bad idea.
  2. yt_upload.py → shorts from <output>\\Publish as Shorts, recaps from <output>\\Recaps as normal videos.
  3. Cleanup: uploaded clips after N days, fully processed recordings after M days (config.cleanup).
  4. Log to run_daily.log; a message box only when something failed or the queue is empty.

Run manually: python run_daily.py [--no-upload] [--no-clip]
"""
import os, sys, json, glob, subprocess, datetime, argparse, time, re

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
LOG = os.path.join(HERE, "run_daily.log")

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-clip", action="store_true")
    A = ap.parse_args()
    import kf_bridge as B
    s = B.settings(); L = B.ledger(); C = B.C
    problems = []

    # ---- step 1: clip ----
    if A.no_clip:
        log("Step 1/3: clipping skipped (--no-clip).")
    elif B.app_running():
        log("Step 1/3: KillFeed app is running and clips by itself – skipping.")
    else:
        log(f"Step 1/3: clipping new recordings in {s['input_dir']} -> {s['output_dir']}")
        try:
            r = C.run_once(s, L, B.killclip, log=lambda m: log("  " + m))
            log(f"  {r['sources']} recording(s) processed: {len(r['publiser'])} to Publish, {len(r['andre'])} to Other, {r['duplicate']} duplicate(s)" + (", new recap" if r.get("montage") else ""))
        except Exception as e:
            log(f"  ERROR clipping: {e}"); problems.append(f"Clipping failed: {str(e)[:100]}")

    # ---- step 2: upload ----
    if not A.no_upload:
        log("Step 2/3: uploading to YouTube (shorts from Publish, recaps from Recaps) ...")
        pr = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "yt_upload.py")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        qualifying = None
        for line in pr.stdout:
            t = line.rstrip()
            log("  " + t)
            if "ERROR" in t or "WARNING" in t: problems.append(t.strip()[:120])
            m2 = re.match(r"\s*(\d+) short\(s\) qualify", t)
            if m2: qualifying = int(m2.group(1))
        pr.wait()
        if pr.returncode != 0: problems.append(f"yt_upload exit {pr.returncode}")
        if qualifying == 0: problems.append("The queue is empty – no multikill/vehicle clips left. Time to play!")
        log("Upload finished (exit %d)." % pr.returncode)

    # ---- step 3: cleanup ----
    try: state = json.load(open(os.path.join(HERE, "state.json"), encoding="utf-8"))
    except Exception: state = {}
    cl = cfg.get("cleanup", {}); now = time.time()
    def rm(path, why):
        try: os.remove(path); log(f"Cleanup: {os.path.basename(path)} ({why})")
        except Exception: pass
    d1 = cl.get("uploaded_clip_days", 7)
    done = set(state.get("uploaded", {})) | set(state.get("duplicate", {})) | set(state.get("expired", {}))
    for d in (B.publish_dir(s), B.recaps_dir(s)):
        for f in glob.glob(os.path.join(d, "*.mp4")):
            base = os.path.basename(f)
            why = "uploaded" if base in state.get("uploaded", {}) else ("duplicate/expired" if base in done else None)
            if why and now - os.path.getmtime(f) > d1 * 86400:
                rm(f, f"{why}, older than {d1} d")
                for ext in (".json", ".txt"): rm(os.path.splitext(f)[0] + ext, "sidecar")
    d2 = cl.get("source_days", 0)
    if d2:
        L = B.ledger()
        for f in C.source_files([s["input_dir"], s.get("vertical_dir") or ""] + list(s.get("extra_input_dirs") or []), skip_dir=s["output_dir"]):
            if os.path.basename(f) in L["processed"] and now - os.path.getmtime(f) > d2 * 86400:
                rm(f, f"fully clipped, older than {d2} d")

    # ---- notify: message box only when something is wrong or the queue is empty ----
    if problems and cfg.get("varsling", "msgbox") == "msgbox":
        msg = "KillFeed nightly job:\n\n" + "\n".join(problems[:8])
        ps = ("Add-Type -AssemblyName System.Windows.Forms;"
              "[System.Windows.Forms.MessageBox]::Show('%s','KillFeed nightly job')" % msg.replace("'", "''"))
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log(f"Message box shown: {len(problems)} item(s)")

if __name__ == "__main__":
    main()
