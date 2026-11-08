#!/usr/bin/env python3
"""run_daily.py – nightly job on top of the KillFeed core.

  1. Clip new recordings with kf_core (same settings + ledger as the tray app). Skipped when the tray app
     is running – it clips by itself, and two clippers on one ledger is a bad idea.
  2. yt_upload.py → shorts from <output>\\Publish as Shorts, recaps from <output>\\Recaps as normal videos.
  3. Cleanup: uploaded clips after N days, fully processed recordings after M days (config.cleanup).
  4. Log to run_daily.log; a toast (never a window that takes focus, never during a game) when something failed.

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
        # En tom ko er en status, ikke en feil. Den sto i "problems" og ga en meldingsboks HVER natt -
        # og en meldingsboks tar fokus fra det som er i forgrunnen, ogsaa et spill i fullskjerm.
        if qualifying == 0: log("  Nothing new to upload (the queue is empty).")
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
            ent = L["processed"].get(C.src_key(f)) or L["processed"].get(os.path.basename(f))
            # same two guards as the app: a full-path entry, and proof the text reading worked on this
            # file. A Tesseract that starts but cannot read makes every recording look empty.
            if ent and not ent.get("error") and ent.get("hits") and now - os.path.getmtime(f) > d2 * 86400:
                rm(f, f"fully clipped, older than {d2} d")

    # ---- notify: only real problems, never over a game, never a window that takes focus ----
    notify(problems, s, C)

def notify(problems, s, C):
    """Si fra om noe feilet - uten aa stjele fokus.

    Foer var dette en MessageBox fra PowerShell. Den ble laget da nattjobben gikk kl. 04 paa en PC
    ingen satt ved, men en MessageBox er et vindu som tar fokus: kom den mens et spill kjoerte, ble
    spillet tabbet ut. Det kostet 30 000 gull i en runde 08.11.2026. Naa:
      - ingenting vises mens spillet kjoerer - det staar i loggen, og kommer igjen neste natt
      - ellers en toast-varsling, som legger seg i hjoernet og aldri tar fokus
      - aldri en MessageBox"""
    if not problems:
        return
    if (cfg.get("varsling") or "toast") == "off":
        log(f"Not shown ({len(problems)} problem(s)): notifications are off."); return
    hint = s.get("game_process_hint", "wardogs")
    try:
        if C.game_running(hint) is not False:      # True eller ukjent: ikke forstyrr
            log(f"Not shown ({len(problems)} problem(s)): a game is (or may be) running ({hint}). See the lines above.")
            return
    except Exception:
        pass
    title = "KillFeed nightly job"
    body = "\n".join(p[:110] for p in problems[:3]) + (f"\n(+{len(problems)-3} more in run_daily.log)" if len(problems) > 3 else "")
    try:
        from winotify import Notification       # samme bibliotek som appen bruker, installert av byggeskriptet
        Notification(app_id="KillFeed", title=title, msg=body, duration="long").show()
        log(f"Notification shown: {len(problems)} problem(s)")
        return
    except Exception as e:
        log(f"  (winotify not available: {e}) - trying a Windows toast via PowerShell")
    # Reserve: Windows' egen toast-API. App-ID-en er PowerShells egen, fordi Windows forkaster stille
    # toasts fra en app-ID som ikke er registrert.
    def q(x): return x.replace("'", "''")
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
          "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
          "$x = $t.GetElementsByTagName('text');"
          "$x.Item(0).AppendChild($t.CreateTextNode('%s')) > $null;"
          "$x.Item(1).AppendChild($t.CreateTextNode('%s')) > $null;"
          "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($t))"
          ) % (q(title), q(body.replace("\n", " / ")))
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log(f"Toast shown: {len(problems)} problem(s)")
    except Exception as e:
        log(f"Could not show a notification ({e}). Problems: " + " | ".join(problems[:3]))

if __name__ == "__main__":
    main()
