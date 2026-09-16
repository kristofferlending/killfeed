#!/usr/bin/env python3
"""KillFeed – alfa. Autopilot for WARDOGS-shorts og daglige recaps.

Første start: en liten veiviser (opptaksmappe, synkmappe). Deretter ligger KillFeed i systemkurven,
ser etter nye opptak hvert minutt, klipper når spillet ikke kjører, legger multikills/vehicle-kills i
<synkmappe>\\Publiser, resten i \\Andre, og bygger en recap i \\Montasje når nok er samlet.
Varsler med en Windows-melding bare når noe nytt er klart.

Kommandolinje: --tray (start rett i kurven, brukes av autostart), --run (kjør én runde og avslutt).
"""
import os, sys, threading, time, datetime, glob, zipfile, subprocess, ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if getattr(sys, "frozen", False): sys.path.insert(0, getattr(sys, "_MEIPASS", HERE))
import kf_core as C          # noqa: E402
import killclip              # noqa: E402

APP, VERSION = C.APP, C.VERSION

# ------------------------------------------------------------------ bare én instans
def single_instance():
    if os.name != "nt": return True
    try:
        ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KillFeedAlphaMutex")
        return ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        return True

# ------------------------------------------------------------------ autostart (Startup-snarvei)
def startup_lnk():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "KillFeed.lnk")

def set_autostart(on):
    if os.name != "nt": return
    lnk = startup_lnk()
    if not on:
        try: os.remove(lnk)
        except OSError: pass
        return
    if getattr(sys, "frozen", False):
        target, args = sys.executable, "--tray"
    else:
        target, args = sys.executable, f'"{os.path.abspath(__file__)}" --tray'
    ps = (f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
          f'$s.TargetPath="{target}";$s.Arguments=\'{args}\';$s.WorkingDirectory="{os.path.dirname(target)}";$s.Save()')
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=C.CF, timeout=20, capture_output=True)
    except Exception as e:
        C.log(f"autostart-snarvei feilet: {e}")

# ------------------------------------------------------------------ varsling
def toast(title, msg, folder=None):
    try:
        from winotify import Notification, audio
        n = Notification(app_id=APP, title=title, msg=msg, duration="long")
        n.set_audio(audio.Default, loop=False)
        if folder and os.path.isdir(folder): n.add_actions("Åpne mappe", "file:///" + folder.replace("\\", "/"))
        n.show(); return
    except Exception:
        pass
    try:
        if App.instance and App.instance.icon: App.instance.icon.notify(msg, title)
    except Exception:
        pass

# ------------------------------------------------------------------ tray-ikon
def make_icon_image():
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, 62, 62), fill=(18, 18, 18, 255), outline=(212, 175, 55, 255), width=4)
    d.rectangle((29, 14, 35, 50), fill=(212, 175, 55, 255))      # sikte
    d.rectangle((14, 29, 50, 35), fill=(212, 175, 55, 255))
    d.ellipse((26, 26, 38, 38), fill=(18, 18, 18, 255))
    return im

# ------------------------------------------------------------------ veiviser
class Wizard(tk.Toplevel):
    def __init__(self, master, s):
        super().__init__(master); self.s = s; self.ok = False
        self.title(f"{APP} – oppsett"); self.resizable(False, False); self.grab_set()
        f = ttk.Frame(self, padding=14); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Velkommen til KillFeed", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="To mapper, så er du ferdig. KillFeed gjør resten selv i bakgrunnen.", foreground="#666").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.v_in = tk.StringVar(value=s.get("input_dir") or C.guess_input_dir())
        self.v_out = tk.StringVar(value=s.get("output_dir") or C.guess_output_dir())
        self.v_auto = tk.BooleanVar(value=s.get("autostart", True))
        ttk.Label(f, text="Der opptakene dine havner (OBS / Aitum / Instant Replay / Medal):").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Entry(f, textvariable=self.v_in, width=64).grid(row=3, column=0, sticky="we")
        ttk.Button(f, text="Velg…", command=lambda: self._pick(self.v_in)).grid(row=3, column=1, padx=(6, 0))
        ttk.Label(f, text="Der ferdige shorts og recaps skal legges (helst en mappe som synkes til telefonen):").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Entry(f, textvariable=self.v_out, width=64).grid(row=5, column=0, sticky="we")
        ttk.Button(f, text="Velg…", command=lambda: self._pick(self.v_out)).grid(row=5, column=1, padx=(6, 0))
        ttk.Checkbutton(f, text="Start KillFeed automatisk når Windows starter (anbefalt)", variable=self.v_auto).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(f, text="Start KillFeed", command=self._done).grid(row=7, column=0, columnspan=2, pady=(14, 0))
        self.protocol("WM_DELETE_WINDOW", self._done)

    def _pick(self, var):
        d = filedialog.askdirectory(parent=self, initialdir=var.get() if os.path.isdir(var.get()) else os.path.expanduser("~"))
        if d: var.set(d)

    def _done(self):
        if not os.path.isdir(self.v_in.get()):
            messagebox.showerror(APP, "Opptaksmappa finnes ikke.", parent=self); return
        self.s["input_dir"] = self.v_in.get(); self.s["output_dir"] = self.v_out.get()
        self.s["autostart"] = self.v_auto.get(); self.s["setup_done"] = True
        C.save_settings(self.s); self.ok = True; self.destroy()

# ------------------------------------------------------------------ hovedvindu
class App(tk.Tk):
    instance = None

    def __init__(self, start_hidden=False):
        super().__init__(); App.instance = self
        self.withdraw()
        self.title(f"{APP} {VERSION}"); self.geometry("720x520"); self.minsize(600, 420)
        self.s = C.load_settings(); self.L = C.load_ledger()
        self.icon = None; self.busy = False; self.paused = False; self.stop_flag = False
        self.lines = []
        C.add_log_hook(self._log_hook)
        if not self.s.get("setup_done"):
            w = Wizard(self, self.s); self.wait_window(w)
            if not w.ok: self.destroy(); return
            set_autostart(self.s.get("autostart", True))
            start_hidden = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._start_tray()
        if not start_hidden: self.show()
        threading.Thread(target=self._watch_loop, daemon=True).start()
        self.after(300, self._pump)

    # ---- GUI
    def _build(self):
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=8, pady=8); self.nb = nb
        st = ttk.Frame(nb, padding=8); nb.add(st, text="Status")
        self.v_status = tk.StringVar(value="Klar.")
        ttk.Label(st, textvariable=self.v_status, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        b = ttk.Frame(st); b.pack(fill="x", pady=6)
        ttk.Button(b, text="Kjør nå", command=self.run_now).pack(side="left")
        ttk.Button(b, text="Lag recap nå", command=self.montage_now).pack(side="left", padx=6)
        ttk.Button(b, text="Åpne utmappe", command=self.open_out).pack(side="left")
        ttk.Button(b, text="Send tilbakemelding", command=self.feedback).pack(side="left", padx=6)
        ttk.Button(b, text="Skjul til systemkurven", command=self.hide).pack(side="right")
        self.prog = ttk.Progressbar(st, mode="determinate"); self.prog.pack(fill="x", pady=(0, 6))
        self.txt = tk.Text(st, wrap="word", state="disabled", font=("Consolas", 9)); self.txt.pack(fill="both", expand=True)

        se = ttk.Frame(nb, padding=8); nb.add(se, text="Innstillinger")
        s = self.s
        self.v_in = tk.StringVar(value=s["input_dir"]); self.v_out = tk.StringVar(value=s["output_dir"])
        self.v_extra = tk.StringVar(value="; ".join(s.get("extra_input_dirs") or []))
        self.v_auto = tk.BooleanVar(value=s.get("autostart", True)); self.v_pause = tk.BooleanVar(value=s.get("pause_while_game_running", True))
        self.v_notify = tk.BooleanVar(value=s.get("notify", True))
        self.v_menabled = tk.BooleanVar(value=s["montage"].get("enabled", True))
        self.v_mmin = tk.IntVar(value=s["montage"]["min_minutes"]); self.v_mmax = tk.IntVar(value=s["montage"]["max_minutes"])
        self.v_mlabel = tk.StringVar(value=s["montage"].get("label", "recap"))
        r = 0
        def row(lbl, var, w=60, pick=False):
            nonlocal r
            ttk.Label(se, text=lbl).grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1
            ttk.Entry(se, textvariable=var, width=w).grid(row=r, column=0, sticky="we")
            if pick: ttk.Button(se, text="Velg…", command=lambda: self._pick(var)).grid(row=r, column=1, padx=6)
            r += 1
        row("Opptaksmappe:", self.v_in, pick=True)
        row("Flere opptaksmapper (valgfritt, skill med ; ):", self.v_extra)
        row("Utmappe (synkmappe):", self.v_out, pick=True)
        ttk.Checkbutton(se, text="Start med Windows", variable=self.v_auto).grid(row=r, column=0, sticky="w", pady=(10, 0)); r += 1
        ttk.Checkbutton(se, text="Vent med klipping mens spillet kjører (sparer CPU)", variable=self.v_pause).grid(row=r, column=0, sticky="w"); r += 1
        ttk.Checkbutton(se, text="Windows-melding når nye klipp er klare", variable=self.v_notify).grid(row=r, column=0, sticky="w"); r += 1
        mf = ttk.LabelFrame(se, text="Recap (kronologisk sammendrag fra vanlige 16:9-opptak)", padding=6); mf.grid(row=r, column=0, columnspan=2, sticky="we", pady=(12, 0)); r += 1
        ttk.Checkbutton(mf, text="Lag recap automatisk når nok er samlet", variable=self.v_menabled).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(mf, text="Lengde, minutter: fra").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(mf, from_=1, to=60, textvariable=self.v_mmin, width=4).grid(row=1, column=1, sticky="w")
        ttk.Label(mf, text="til").grid(row=1, column=2, sticky="w", padx=4)
        ttk.Spinbox(mf, from_=1, to=120, textvariable=self.v_mmax, width=4).grid(row=1, column=3, sticky="w")
        ttk.Label(mf, text="Navn på fila («WARDOGS <ord> <dato>.mp4»):").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Entry(mf, textvariable=self.v_mlabel, width=14).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(se, text="Lagre", command=self.save_settings).grid(row=r, column=0, sticky="w", pady=(14, 0)); r += 1
        se.columnconfigure(0, weight=1)

        av = ttk.Frame(nb, padding=8); nb.add(av, text="Avansert")

        self.v_style = tk.StringVar(value=s.get("style", "center"))
        ttk.Label(av, text="9:16-stil for 16:9-opptak:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(av, text="Midtutsnitt", variable=self.v_style, value="center").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(av, text="Uskarp bakgrunn", variable=self.v_style, value="blur").grid(row=0, column=2, sticky="w")
        self.adv = {}
        spec = [("Shorts: sek. før", ("shorts", "pre")), ("Shorts: sek. etter", ("shorts", "post")), ("Shorts: min. lengde", ("shorts", "min")),
                ("Shorts: maks lengde", ("shorts", "max")), ("Shorts: min. kills for Publiser", ("shorts", "min_kills")),
                ("Shorts: min. vehicles for Publiser", ("shorts", "min_vehicles")),
                ("Recap: sek. før", ("montage", "pre")), ("Recap: sek. etter", ("montage", "post")), ("Recap: maks sek. per klipp", ("montage", "clip_max")),
                ("Recap: min. kills per klipp", ("montage", "min_kills")), ("Recap: bruk opptak fra siste N dager", ("montage", "lookback_days")),
                ("Dedup-toleranse, sek.", ("dedup_seconds",)), ("Rydd Andre\\ etter N dager (0 = aldri)", ("cleanup", "andre_days"))]
        for i, (lbl, key) in enumerate(spec, 1):
            v = tk.IntVar(value=self._get(key)); self.adv[key] = v
            ttk.Label(av, text=lbl).grid(row=i, column=0, sticky="w", pady=1)
            ttk.Spinbox(av, from_=0, to=999, textvariable=v, width=6).grid(row=i, column=1, sticky="w")
        ttk.Label(av, text=f"Innstillinger og logg ligger i {C.appdata_dir()}", foreground="#777").grid(row=len(spec) + 1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(av, text="Lagre", command=self.save_settings).grid(row=len(spec) + 2, column=0, sticky="w", pady=(8, 0))

    def _get(self, key):
        d = self.s
        for k in key: d = d[k]
        return d

    def _pick(self, var):
        d = filedialog.askdirectory(initialdir=var.get() if os.path.isdir(var.get()) else os.path.expanduser("~"))
        if d: var.set(d)

    def save_settings(self):
        s = self.s
        s["input_dir"] = self.v_in.get().strip(); s["output_dir"] = self.v_out.get().strip()
        s["extra_input_dirs"] = [x.strip() for x in self.v_extra.get().split(";") if x.strip()]
        s["autostart"] = self.v_auto.get(); s["pause_while_game_running"] = self.v_pause.get(); s["notify"] = self.v_notify.get()
        s["style"] = self.v_style.get()
        s["montage"]["enabled"] = self.v_menabled.get(); s["montage"]["min_minutes"] = max(1, self.v_mmin.get())
        s["montage"]["max_minutes"] = max(s["montage"]["min_minutes"], self.v_mmax.get())
        s["montage"]["label"] = self.v_mlabel.get().strip() or "recap"
        for key, v in self.adv.items():
            d = s
            for k in key[:-1]: d = d[k]
            try: d[key[-1]] = int(v.get())
            except Exception: pass
        C.save_settings(s); set_autostart(s["autostart"])
        self.log("Innstillinger lagret."); self.v_status.set("Innstillinger lagret.")

    # ---- logg/status
    def _log_hook(self, msg): self.lines.append(msg)
    def log(self, msg): C.log(msg)
    def _pump(self):
        if self.lines:
            self.txt.configure(state="normal")
            while self.lines: self.txt.insert("end", self.lines.pop(0) + "\n")
            self.txt.see("end"); self.txt.configure(state="disabled")
        self.after(300, self._pump)

    def status(self, msg):
        self.after(0, lambda: self.v_status.set(msg))
    def progress(self, n, tot):
        self.after(0, lambda: self.prog.configure(maximum=max(1, tot), value=n))

    def show(self):
        self.deiconify(); self.lift(); self.focus_force()
    def hide(self):
        self.withdraw()

    def open_out(self):
        d = self.s.get("output_dir")
        if d and os.path.isdir(d): os.startfile(d)
        else: messagebox.showinfo(APP, "Utmappa finnes ikke ennå – den lages ved første klipp.")

    # ---- tray
    def _start_tray(self):
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("Åpne KillFeed", lambda: self.after(0, self.show), default=True),
                pystray.MenuItem("Kjør nå", lambda: self.after(0, self.run_now)),
                pystray.MenuItem("Lag recap nå", lambda: self.after(0, self.montage_now)),
                pystray.MenuItem("Åpne utmappe", lambda: self.after(0, self.open_out)),
                pystray.MenuItem("Pause overvåking", lambda: self.after(0, self.toggle_pause), checked=lambda i: self.paused),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Avslutt", lambda: self.after(0, self.quit_app)))
            self.icon = pystray.Icon(APP, make_icon_image(), f"{APP} – overvåker opptak", menu)
            self.icon.run_detached()
        except Exception as e:
            self.icon = None; self.log(f"(tray-ikon utilgjengelig: {e}) – vinduet holdes åpent")
            self.protocol("WM_DELETE_WINDOW", self.quit_app); self.show()

    def toggle_pause(self):
        self.paused = not self.paused
        self.v_status.set("Overvåking satt på pause." if self.paused else "Overvåker opptaksmappa.")
        if self.icon: self.icon.update_menu()

    def quit_app(self):
        self.stop_flag = True
        try:
            if self.icon: self.icon.stop()
        except Exception: pass
        self.destroy()

    # ---- arbeid
    def _watch_loop(self):
        time.sleep(3)
        while not self.stop_flag:
            try:
                if not self.paused and not self.busy:
                    if self.s.get("pause_while_game_running", True) and C.game_running(self.s.get("game_process_hint", "wardogs")):
                        self.status("Spillet kjører – venter med klipping.")
                    elif C.ready_sources(self.s, self.L):
                        self._do_run()
                    else:
                        self.status(f"Overvåker {self.s['input_dir']} – ingenting nytt ({datetime.datetime.now():%H:%M}).")
            except Exception as e:
                self.log(f"FEIL i overvåking: {e}")
            for _ in range(int(self.s.get("watch_interval_s", 60))):
                if self.stop_flag: return
                time.sleep(1)

    def run_now(self):
        if self.busy: return
        threading.Thread(target=self._do_run, daemon=True).start()

    def montage_now(self):
        if self.busy: return
        def go():
            self.busy = True; self.status("Bygger recap …")
            try:
                out = C.build_montage(self.s, self.L, killclip, force=True, log=self.log)
                if out:
                    self.status(f"Recap klar: {os.path.basename(out)}")
                    if self.s.get("notify", True): toast("Recap klar", os.path.basename(out), os.path.dirname(out))
                else:
                    self.status("Ingen kvalifiserte klipp til recap ennå.")
            finally:
                self.busy = False
        threading.Thread(target=go, daemon=True).start()

    def _do_run(self):
        self.busy = True
        try:
            if not os.path.isdir(self.s.get("input_dir", "")):
                self.status("Opptaksmappa finnes ikke – sjekk Innstillinger."); return
            def prog(n, tot, name):
                self.progress(n, tot); self.status(f"Klipper {n}/{tot}: {name}")
            r = C.run_once(self.s, self.L, killclip, log=self.log, progress=prog, stop=lambda: self.stop_flag)
            self.progress(0, 1)
            npub, nand = len(r["publiser"]), len(r["andre"])
            if r["sources"]:
                msg = f"{npub} klare til publisering, {nand} andre" + (f", {r['duplicate']} duplikater" if r["duplicate"] else "")
                self.status(f"Ferdig: {msg}."); self.log(f"Ferdig: {msg}.")
                if self.s.get("notify", True) and (npub or r["montage"]):
                    parts = []
                    if npub: parts.append(f"{npub} short{'s' if npub != 1 else ''} klar{'e' if npub != 1 else ''} i Publiser")
                    if r["montage"]: parts.append("ny recap i Montasje")
                    toast(APP, " · ".join(parts), os.path.join(self.s["output_dir"], "Publiser" if npub else "Montasje"))
            else:
                self.status(f"Ingenting nytt ({datetime.datetime.now():%H:%M}).")
        except Exception as e:
            self.log(f"FEIL: {e}"); self.status(f"Feil: {e}")
        finally:
            self.busy = False

    def feedback(self):
        out = os.path.join(os.path.expanduser("~"), "Desktop", f"killfeed-feedback-{datetime.datetime.now():%Y%m%d-%H%M}.zip")
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                for p in [C.LOGFILE, C.SETTINGS, C.LEDGER]:
                    if os.path.exists(p): z.write(p, os.path.basename(p))
                for j in glob.glob(os.path.join(C.REPORTS, "*.json")):
                    z.write(j, "reports/" + os.path.basename(j))
            messagebox.showinfo(APP, f"Lagt på skrivebordet:\n{out}\n\nSend den til Kristoffer (Discord). Ingen video er med – bare logg og tekst-treff.")
        except Exception as e:
            messagebox.showerror(APP, f"Klarte ikke lage zip: {e}")

# ------------------------------------------------------------------ start
def main():
    if "--run" in sys.argv:                       # én runde uten GUI (feilsøking / oppgaveplanlegger)
        s = C.load_settings(); L = C.load_ledger()
        r = C.run_once(s, L, killclip, log=lambda m: print(m, flush=True))
        print(r); return
    if not single_instance():
        return
    C.log(f"{APP} {VERSION} startet")
    app = App(start_hidden="--tray" in sys.argv)
    try:
        app.mainloop()
    except tk.TclError:
        pass

if __name__ == "__main__":
    main()
