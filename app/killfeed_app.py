#!/usr/bin/env python3
"""KillFeed – alpha. Autopilot for WARDOGS shorts and daily recaps.

First start: a short wizard (one folder: where your recordings are). After that KillFeed lives in the
system tray, looks for new recordings every minute, clips when the game is not running, puts multikills /
vehicle kills in <output>\\Publish, the rest in \\Other, and builds a recap in \\Recaps when enough is collected.
Shows a Windows notification only when something new is ready.

Command line: --tray (start straight into the tray, used by autostart), --run (one pass, no GUI, then exit).
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

# ------------------------------------------------------------------ DPI (sharp text on 125–200 % scaling)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ------------------------------------------------------------------ single instance
def single_instance():
    if os.name != "nt": return True
    try:
        ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KillFeedAlphaMutex")
        return ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        return True

# ------------------------------------------------------------------ autostart (Startup shortcut)
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
        C.log(f"autostart shortcut failed: {e}")

def desktop_dir():
    """The real Desktop folder – also when Windows has moved it into OneDrive."""
    if os.name == "nt":
        try:
            import ctypes.wintypes, uuid
            class GUID(ctypes.Structure): _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
            u = uuid.UUID("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"); g = GUID(); g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
            for i, x in enumerate(u.bytes[8:]): g.d[i] = x
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0 and out.value and os.path.isdir(out.value):
                return out.value
        except Exception: pass
    home = os.path.expanduser("~")
    for c in (os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"), os.path.join(home, "OneDrive", "Skrivebord"), os.path.join(home, "Skrivebord")):
        if os.path.isdir(c): return c
    return home

# ------------------------------------------------------------------ notifications
def toast(title, msg, folder=None):
    try:
        from winotify import Notification, audio
        n = Notification(app_id=APP, title=title, msg=msg, duration="long")
        n.set_audio(audio.Default, loop=False)
        if folder and os.path.isdir(folder): n.add_actions("Open folder", "file:///" + folder.replace("\\", "/"))
        n.show(); return
    except Exception:
        pass
    try:
        if App.instance and App.instance.icon: App.instance.icon.notify(msg, title)
    except Exception:
        pass

# ------------------------------------------------------------------ icons (tray states)
def icon_path(ext):
    base = getattr(sys, "_MEIPASS", HERE) if getattr(sys, "frozen", False) else HERE
    return os.path.join(base, f"killfeed.{ext}")

def _base_icon():
    from PIL import Image, ImageDraw
    p = icon_path("png")
    if os.path.exists(p):
        try: return Image.open(p).convert("RGBA")
        except Exception: pass
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((2, 2, 62, 62), fill=(18, 18, 18, 255), outline=(212, 175, 55, 255), width=4)
    d.rectangle((29, 14, 35, 50), fill=(212, 175, 55, 255)); d.rectangle((14, 29, 50, 35), fill=(212, 175, 55, 255))
    d.ellipse((26, 26, 38, 38), fill=(18, 18, 18, 255))
    return im

def tray_icons():
    """idle = gold, working = two frames that alternate, paused = grey."""
    from PIL import Image, ImageEnhance, ImageOps
    base = _base_icon()
    dim = ImageEnhance.Brightness(base).enhance(0.55)
    grey = ImageOps.grayscale(base).convert("RGBA"); grey.putalpha(base.getchannel("A"))
    return {"idle": base, "work0": base, "work1": dim, "paused": grey}

# ------------------------------------------------------------------ theme (dark + gold, same as killfeed.no)
BG, PANEL, FIELD, FG, MUTED, GOLD, GOLD_HI, RED, GREEN = "#0f0f10", "#18181b", "#232326", "#f2f2f2", "#9a9a9a", "#d4af37", "#e6c65a", "#c0392b", "#4caf50"
F, FB, FH, FBIG, FNUM, FMONO = ("Segoe UI", 10), ("Segoe UI", 10, "bold"), ("Segoe UI", 15, "bold"), ("Segoe UI", 12), ("Segoe UI", 24, "bold"), ("Consolas", 9)

def apply_theme(root):
    st = ttk.Style(root)
    try: st.theme_use("clam")
    except Exception: pass
    root.configure(bg=BG)
    st.configure(".", background=BG, foreground=FG, font=F, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
    st.configure("TFrame", background=BG); st.configure("Panel.TFrame", background=PANEL)
    st.configure("TLabel", background=BG, foreground=FG); st.configure("Panel.TLabel", background=PANEL, foreground=FG)
    st.configure("Muted.TLabel", foreground=MUTED); st.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    st.configure("H.TLabel", font=FH, foreground=FG); st.configure("Brand.TLabel", foreground=GOLD, font=("Segoe UI", 16, "bold"))
    st.configure("Big.TLabel", font=FBIG, background=PANEL, foreground=FG)
    st.configure("Num.TLabel", font=FNUM, background=PANEL, foreground=GOLD)
    st.configure("Group.TLabel", font=FB, foreground=GOLD)
    st.configure("TButton", background=FIELD, foreground=FG, padding=(14, 8), font=FB, borderwidth=0, focusthickness=0)
    st.map("TButton", background=[("active", "#2e2e33"), ("disabled", PANEL)], foreground=[("disabled", MUTED)])
    st.configure("Primary.TButton", background=GOLD, foreground="#111", padding=(22, 11), font=("Segoe UI", 11, "bold"))
    st.map("Primary.TButton", background=[("active", GOLD_HI), ("disabled", "#5a4d22")], foreground=[("disabled", "#333")])
    st.configure("Danger.TButton", background=BG, foreground="#d98c84", padding=(10, 5), font=F)
    st.map("Danger.TButton", background=[("active", RED)], foreground=[("active", "#fff")])
    st.configure("Link.TButton", background=BG, foreground=MUTED, padding=(8, 5), font=F)
    st.map("Link.TButton", background=[("active", PANEL)], foreground=[("active", FG)])
    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 9), font=FB, borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", GOLD)])
    st.configure("TCheckbutton", background=BG, foreground=FG); st.map("TCheckbutton", background=[("active", BG)])
    st.configure("TRadiobutton", background=BG, foreground=FG); st.map("TRadiobutton", background=[("active", BG)])
    st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, borderwidth=0, padding=6)
    st.configure("TSpinbox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, borderwidth=0, padding=4)
    st.configure("TCombobox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, borderwidth=0, padding=4)
    st.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    st.configure("TLabelframe", background=BG, foreground=MUTED, borderwidth=1, relief="solid")
    st.configure("TLabelframe.Label", background=BG, foreground=GOLD, font=FB)
    st.configure("Horizontal.TProgressbar", background=GOLD, troughcolor=FIELD, borderwidth=0, thickness=6)
    st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, borderwidth=0, rowheight=24, font=F)
    st.configure("Treeview.Heading", background=FIELD, foreground=MUTED, font=FB, borderwidth=0, relief="flat")
    st.map("Treeview", background=[("selected", "#3a3120")], foreground=[("selected", FG)])
    st.map("Treeview.Heading", background=[("active", FIELD)])
    st.configure("Vertical.TScrollbar", background=FIELD, troughcolor=BG, arrowcolor=MUTED, borderwidth=0)
    root.option_add("*TCombobox*Listbox.background", FIELD); root.option_add("*TCombobox*Listbox.foreground", FG)

class Tip:
    """Hover tooltip."""
    def __init__(self, w, text):
        self.w, self.text, self.tw = w, text, None
        w.bind("<Enter>", self._show, add="+"); w.bind("<Leave>", self._hide, add="+")
    def _show(self, _=None):
        if self.tw or not self.text: return
        x = self.w.winfo_rootx() + 12; y = self.w.winfo_rooty() + self.w.winfo_height() + 6
        self.tw = tk.Toplevel(self.w); self.tw.wm_overrideredirect(True); self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg="#2a2a2e", fg=FG, font=F, padx=10, pady=6, wraplength=380, justify="left").pack()
    def _hide(self, _=None):
        if self.tw: self.tw.destroy(); self.tw = None

def choose(parent, title, text, buttons):
    """Modal dialog with custom buttons: [(label, value), ...]. Returns the chosen value (None if closed)."""
    w = tk.Toplevel(parent); w.title(title); w.configure(bg=BG); w.resizable(False, False); w.grab_set(); w.transient(parent)
    out = {"v": None}
    ttk.Label(w, text=title, style="H.TLabel").pack(anchor="w", padx=20, pady=(16, 4))
    ttk.Label(w, text=text, wraplength=460, justify="left").pack(anchor="w", padx=20)
    r = ttk.Frame(w, padding=(20, 16, 20, 16)); r.pack(fill="x")
    for i, (lbl, val) in enumerate(buttons):
        def go(v=val): out["v"] = v; w.destroy()
        ttk.Button(r, text=lbl, command=go, style="Primary.TButton" if i == 0 else "TButton").pack(side="left", padx=(0, 8))
    w.protocol("WM_DELETE_WINDOW", w.destroy)
    w.update_idletasks(); x = parent.winfo_rootx() + (parent.winfo_width() - w.winfo_width()) // 2; y = parent.winfo_rooty() + 120
    w.geometry(f"+{max(0, x)}+{max(0, y)}")
    parent.wait_window(w); return out["v"]

def hint(parent, text, **kw):
    return ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=kw.pop("wraplength", 640), justify="left", **kw)

# ------------------------------------------------------------------ recording guide
def show_guide(parent):
    w = tk.Toplevel(parent); w.title(f"{APP} – recording guide"); w.geometry("760x600"); w.configure(bg=BG)
    t = tk.Text(w, wrap="word", font=F, padx=16, pady=12, bg=PANEL, fg=FG, insertbackground=FG, relief="flat"); t.pack(fill="both", expand=True, padx=12, pady=12)
    t.insert("1.0", C.RECORDING_GUIDE.strip()); t.configure(state="disabled")
    ttk.Button(w, text="Close", command=w.destroy).pack(pady=(0, 12))

# ------------------------------------------------------------------ wizard
def sync_folders():
    """Sync folders present on this PC (OneDrive, Google Drive, iCloud, Dropbox)."""
    home = os.path.expanduser("~"); out = []
    for c in ["OneDrive", "OneDrive - Personal", "Google Drive", "iCloudDrive", "Dropbox"]:
        p = os.path.join(home, c)
        if os.path.isdir(p): out.append(p)
    return out

def short_path(p, n=48):
    return p if len(p) <= n else p[:18] + "…" + p[-(n - 19):]

class Wizard(tk.Toplevel):
    """Four short pages: recordings -> what to make -> what is good enough -> where. Everything can be changed later in Settings."""
    def __init__(self, master, s):
        super().__init__(master); self.s = s; self.ok = False; self.page = 0
        self.title(f"{APP} – setup"); self.resizable(False, False); self.grab_set(); self.configure(bg=BG); self.minsize(680, 0)
        sh, m = s["shorts"], s["montage"]
        self.v_in = tk.StringVar(value=s.get("input_dir") or C.guess_input_dir())
        self.v_hasvert = tk.BooleanVar(value=bool(s.get("vertical_dir"))); self.v_vert = tk.StringVar(value=s.get("vertical_dir") or "")
        self.v_shorts = tk.BooleanVar(value=True); self.v_recap = tk.BooleanVar(value=m.get("enabled", True))
        self.v_rmin = tk.IntVar(value=m["min_minutes"]); self.v_rmax = tk.IntVar(value=m["max_minutes"])
        self.v_rauto = tk.StringVar(value="auto")
        rule = "multi_or_veh"
        if sh["min_kills"] <= 1: rule = "all"
        elif sh["min_vehicles"] > 10: rule = "multi_only"
        self.v_rule = tk.StringVar(value=rule); self.v_fallback = tk.BooleanVar(value=sh.get("fallback_single_when_empty", True))
        self.v_where = tk.StringVar(value="local"); self.v_sync = tk.StringVar(value=(sync_folders() or [""])[0])
        self.v_auto = tk.BooleanVar(value=s.get("autostart", True))
        head = ttk.Frame(self, padding=(20, 14, 20, 0)); head.pack(fill="x")
        ttk.Label(head, text="KILLFEED", style="Brand.TLabel").pack(side="left")
        ttk.Label(head, text="  first-time setup", style="Muted.TLabel").pack(side="left", pady=(6, 0))
        self.body = ttk.Frame(self, padding=20); self.body.pack(fill="both", expand=True)
        nav = ttk.Frame(self, padding=(20, 0, 20, 18)); nav.pack(fill="x")
        self.v_step = tk.StringVar(); ttk.Label(nav, textvariable=self.v_step, style="Muted.TLabel").pack(side="left")
        self.b_next = ttk.Button(nav, text="Next", command=self._next, style="Primary.TButton"); self.b_next.pack(side="right")
        self.b_back = ttk.Button(nav, text="Back", command=self._back); self.b_back.pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._render()

    def _render(self):
        for w in self.body.winfo_children(): w.destroy()
        f = self.body; pages = [self._p_input, self._p_what, self._p_rule, self._p_where]
        pages[self.page](f)
        self.v_step.set(f"Step {self.page + 1} of {len(pages)}")
        self.b_back.configure(state="normal" if self.page else "disabled")
        self.b_next.configure(text="Start KillFeed" if self.page == len(pages) - 1 else "Next")

    def _title(self, f, t, sub=None):
        ttk.Label(f, text=t, style="H.TLabel").pack(anchor="w")
        if sub: hint(f, sub).pack(anchor="w", pady=(2, 14))

    def _p_input(self, f):
        self._title(f, "Where are your recordings?", "Your main recording is the normal 16:9 one (OBS, NVIDIA Instant Replay, Medal …). Subfolders are included, so pointing at Videos\\ is fine.")
        ttk.Label(f, text="Main recordings (16:9)").pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=(2, 0))
        ttk.Entry(r, textvariable=self.v_in, width=62).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Browse…", command=lambda: self._pick(self.v_in)).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(f, text="I also record ready-made vertical 9:16 (Aitum Vertical or similar) – those become shorts without cropping",
                        variable=self.v_hasvert, command=self._render).pack(anchor="w", pady=(14, 0))
        if self.v_hasvert.get():
            ttk.Label(f, text="Folder with 9:16 recordings").pack(anchor="w", padx=(24, 0), pady=(6, 0))
            r2 = ttk.Frame(f); r2.pack(fill="x", padx=(24, 0), pady=(2, 0))
            ttk.Entry(r2, textvariable=self.v_vert, width=58).pack(side="left", fill="x", expand=True)
            ttk.Button(r2, text="Browse…", command=lambda: self._pick(self.v_vert)).pack(side="left", padx=(6, 0))
            hint(f, "Same kill in both: the 9:16 becomes the short, the 16:9 is used for the recap and for distance/victim in the title.", wraplength=600).pack(anchor="w", padx=(24, 0), pady=(4, 0))
        ttk.Button(f, text="No recordings yet? How to set up OBS / ShadowPlay / Medal", style="Link.TButton", command=lambda: show_guide(self)).pack(anchor="w", pady=(16, 0))

    def _p_what(self, f):
        self._title(f, "What should KillFeed make?", "Everything happens by itself after each session, once the game is closed.")
        ttk.Checkbutton(f, text="Shorts – vertical 9:16, 18–40 s, with a title. Ready for YouTube Shorts / TikTok / Reels", variable=self.v_shorts).pack(anchor="w", pady=3)
        ttk.Checkbutton(f, text="Recap – 16:9 chronological summary of the day's kills from your normal recordings", variable=self.v_recap, command=self._render).pack(anchor="w", pady=3)
        st = "normal" if self.v_recap.get() else "disabled"
        r = ttk.Frame(f); r.pack(anchor="w", padx=(24, 0), pady=(4, 6))
        ttk.Label(r, text="Recap length: from").pack(side="left")
        ttk.Spinbox(r, from_=1, to=60, textvariable=self.v_rmin, width=4, state=st).pack(side="left", padx=4)
        ttk.Label(r, text="to").pack(side="left")
        ttk.Spinbox(r, from_=1, to=120, textvariable=self.v_rmax, width=4, state=st).pack(side="left", padx=4)
        ttk.Label(r, text="minutes").pack(side="left")
        ttk.Radiobutton(f, text="Build the recap automatically when enough is collected (recommended)", variable=self.v_rauto, value="auto", state=st).pack(anchor="w", padx=(24, 0))
        ttk.Radiobutton(f, text="Only when I press “Make recap now”", variable=self.v_rauto, value="manual", state=st).pack(anchor="w", padx=(24, 0))

    def _p_rule(self, f):
        self._title(f, "What is good enough to publish?", "Clips that pass go to Publish\\, the rest go to Other\\ – nothing is thrown away.")
        ttk.Radiobutton(f, text="Multikill or vehicle destroyed (recommended – a single kill is rarely worth a short)", variable=self.v_rule, value="multi_or_veh").pack(anchor="w", pady=3)
        ttk.Radiobutton(f, text="Every kill – I'll pick myself afterwards", variable=self.v_rule, value="all").pack(anchor="w", pady=3)
        ttk.Radiobutton(f, text="Multikills only (2+ kills in the same clip)", variable=self.v_rule, value="multi_only").pack(anchor="w", pady=3)
        ttk.Checkbutton(f, text="If a session gives nothing: promote its best single kill to Publish anyway", variable=self.v_fallback).pack(anchor="w", pady=(14, 0))

    def _p_where(self, f):
        self._title(f, "Where should the finished clips go?", "KillFeed creates the folders Publish, Other and Recaps by itself when there is something to put in them.")
        loc = os.path.join(self.v_in.get().strip().rstrip("\\/"), APP)
        ttk.Radiobutton(f, text="Next to the recordings", variable=self.v_where, value="local").pack(anchor="w", pady=(2, 0))
        hint(f, loc).pack(anchor="w", padx=(24, 0))
        sf = sync_folders()
        ttk.Radiobutton(f, text="In a folder that syncs to your phone (so you can publish from the YouTube app)", variable=self.v_where, value="sync").pack(anchor="w", pady=(10, 0))
        r = ttk.Frame(f); r.pack(fill="x", padx=(24, 0), pady=(2, 0))
        cb = ttk.Combobox(r, textvariable=self.v_sync, values=[os.path.join(x, APP) for x in sf], width=58); cb.pack(side="left", fill="x", expand=True)
        if sf and not self.v_sync.get().endswith(APP): self.v_sync.set(os.path.join(sf[0], APP))
        ttk.Button(r, text="Browse…", command=lambda: self._pick(self.v_sync)).pack(side="left", padx=(6, 0))
        if not sf: hint(f, "No OneDrive / Google Drive / Dropbox folder found on this PC – pick one manually or use the first option.", wraplength=600).pack(anchor="w", padx=(24, 0), pady=(4, 0))
        ttk.Checkbutton(f, text="Start KillFeed with Windows (recommended)", variable=self.v_auto).pack(anchor="w", pady=(16, 0))
        ttk.Button(f, text="Test: how many recordings will it find?", style="Link.TButton", command=self._test).pack(anchor="w", pady=(12, 0))

    def _test(self):
        dirs = [self.v_in.get().strip()] + ([self.v_vert.get().strip()] if self.v_hasvert.get() else [])
        files = C.source_files(dirs)
        if not files:
            messagebox.showinfo(APP, "No recordings (.mkv / .mp4 / .mov) found in that folder or its subfolders.\nCheck the folder, or see the recording guide.", parent=self); return
        newest = max(files, key=os.path.getmtime)
        messagebox.showinfo(APP, f"Found {len(files)} recording(s).\nNewest: {os.path.basename(newest)}\n\nKillFeed will go through them one by one after you press Start (it takes 30–90 s per file).", parent=self)

    def _pick(self, var):
        d = filedialog.askdirectory(parent=self, initialdir=var.get() if os.path.isdir(var.get()) else os.path.expanduser("~"))
        if d: var.set(d.replace("/", "\\"))

    def _back(self):
        self.page -= 1; self._render()

    def _next(self):
        if self.page == 0 and not os.path.isdir(self.v_in.get().strip()):
            messagebox.showerror(APP, "That recordings folder does not exist.", parent=self); return
        if self.page == 0 and self.v_hasvert.get() and not os.path.isdir(self.v_vert.get().strip()):
            messagebox.showerror(APP, "The 9:16 folder does not exist (or untick the box).", parent=self); return
        if self.page == 3: self._done(); return
        self.page += 1; self._render()

    def _cancel(self):
        self.ok = False; self.destroy()

    def _done(self):
        s = self.s; sh, m = s["shorts"], s["montage"]
        s["input_dir"] = self.v_in.get().strip()
        s["vertical_dir"] = self.v_vert.get().strip() if self.v_hasvert.get() else ""
        s["prefer_vertical"] = True
        s["output_dir"] = self.v_sync.get().strip() if self.v_where.get() == "sync" and self.v_sync.get().strip() else os.path.join(s["input_dir"].rstrip("\\/"), APP)
        s["make_shorts"] = self.v_shorts.get()
        m["enabled"] = self.v_recap.get(); m["auto"] = self.v_rauto.get() == "auto"
        m["min_minutes"] = max(1, self.v_rmin.get()); m["max_minutes"] = max(m["min_minutes"], self.v_rmax.get())
        sh["min_kills"], sh["min_vehicles"] = {"multi_or_veh": (2, 1), "all": (1, 1), "multi_only": (2, 99)}[self.v_rule.get()]
        sh["fallback_single_when_empty"] = self.v_fallback.get()
        s["autostart"] = self.v_auto.get(); s["setup_done"] = True
        try: os.makedirs(s["output_dir"], exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP, f"Could not create {s['output_dir']}:\n{e}", parent=self); return
        C.save_settings(s); self.ok = True; self.destroy()

# ------------------------------------------------------------------ main window
class App(tk.Tk):
    instance = None

    def __init__(self, start_hidden=False):
        super().__init__(); App.instance = self
        self.withdraw(); apply_theme(self)
        try: self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        except Exception: pass
        self.title(f"{APP} {VERSION}"); self.geometry("940x720"); self.minsize(800, 560)
        self.s = C.load_settings(); self.L = C.load_ledger()
        self.icon = None; self.icons = None; self.busy = False; self.paused = False; self.stop_flag = False; self.stop_req = False
        self.lines = []; self._tray_state = None; self._spin_i = 0; self._stats_dirty = True; self._stop_clicks = 0; self._pending_action = None
        C.add_log_hook(self._log_hook)
        C.clean_work(); C.rotate_logs()
        if not self.s.get("setup_done"):
            w = Wizard(self, self.s); self.wait_window(w)
            if not w.ok: self.destroy(); return
            set_autostart(self.s.get("autostart", True))
            start_hidden = False
        self._build(); self._clip_signature = self._sig()
        try: self.iconphoto(True, tk.PhotoImage(file=icon_path("png")))
        except Exception: pass
        probs = C.preflight(self.s, killclip)
        for pr in probs: self.log("PROBLEM: " + pr)
        if probs: self.after(500, lambda: messagebox.showwarning(APP, "KillFeed cannot start clipping until this is fixed:\n\n• " + "\n• ".join(probs)))
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._start_tray()
        if not start_hidden: self.show()
        threading.Thread(target=self._watch_loop, daemon=True).start()
        self.after(300, self._pump)

    # ================================================================ GUI
    def _build(self):
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=(8, 10)); self.nb = nb; self._wheel = []
        self._build_dashboard(nb); self._build_settings(nb); self._build_advanced(nb); self._build_log(nb)
        self.bind_all("<MouseWheel>", self._on_wheel)

    # ---- dashboard
    def _build_dashboard(self, nb):
        d = ttk.Frame(nb, padding=(18, 14, 18, 12)); nb.add(d, text="Dashboard")
        top = ttk.Frame(d); top.pack(fill="x")
        ttk.Label(top, text="KILLFEED", style="Brand.TLabel").pack(side="left")
        ttk.Label(top, text=f"  {VERSION}", style="Muted.TLabel").pack(side="left", pady=(7, 0))
        self.v_badge = tk.StringVar(value="● watching"); self.l_badge = ttk.Label(top, textvariable=self.v_badge, foreground=GREEN, font=FB); self.l_badge.pack(side="right", pady=(6, 0))

        card = tk.Frame(d, bg=PANEL, padx=18, pady=14); card.pack(fill="x", pady=(12, 0))
        r = tk.Frame(card, bg=PANEL); r.pack(fill="x")
        self.v_spin = tk.StringVar(value=" ")
        tk.Label(r, textvariable=self.v_spin, font=("Segoe UI", 18, "bold"), fg=GOLD, bg=PANEL, width=2).pack(side="left")
        self.v_status = tk.StringVar(value="Ready.")
        ttk.Label(r, textvariable=self.v_status, style="Big.TLabel", wraplength=740).pack(side="left", fill="x", expand=True)
        self.v_sub = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.v_sub, style="PanelMuted.TLabel", wraplength=780).pack(anchor="w", padx=(34, 0))
        self.prog = ttk.Progressbar(card, mode="determinate"); self.prog.pack(fill="x", pady=(10, 0), padx=(34, 0))

        nums = ttk.Frame(d); nums.pack(fill="x", pady=(12, 0))
        self.v_nums = {}
        for i, (key, lbl) in enumerate((("today", "Shorts today"), ("week", "Last 7 days"), ("recaps", "Recaps"), ("sources", "Recordings scanned"))):
            f = tk.Frame(nums, bg=PANEL, padx=16, pady=8); f.grid(row=0, column=i, sticky="we", padx=(0 if i == 0 else 8, 0))
            v = tk.StringVar(value="0"); self.v_nums[key] = v
            ttk.Label(f, textvariable=v, style="Num.TLabel").pack(anchor="w")
            ttk.Label(f, text=lbl, style="PanelMuted.TLabel").pack(anchor="w")
            nums.columnconfigure(i, weight=1)

        row = ttk.Frame(d); row.pack(fill="x", pady=(14, 0))
        self.v_primary = tk.StringVar(value="▶   Run now")
        self.b_run = ttk.Button(row, textvariable=self.v_primary, command=self.primary_action, style="Primary.TButton"); self.b_run.pack(side="left")
        Tip(self.b_run, "KillFeed already checks for new recordings every minute. This just does it right now.")
        self.v_pausebtn = tk.StringVar(value="⏸   Pause")
        self.b_pause = ttk.Button(row, textvariable=self.v_pausebtn, command=self.toggle_pause); self.b_pause.pack(side="left", padx=8)
        Tip(self.b_pause, "Stop watching the folder until you press Resume. The current file finishes first.")
        self.b_recap = ttk.Button(row, text="Make recap now", command=self.montage_now); self.b_recap.pack(side="left")
        Tip(self.b_recap, "Build a recap from what is collected so far, even if it is shorter than the minimum.")
        b = ttk.Button(row, text="Open output folder", command=self.open_out); b.pack(side="right")

        lf = ttk.Frame(d); lf.pack(fill="both", expand=True, pady=(14, 0))
        hdr = ttk.Frame(lf); hdr.pack(fill="x")
        ttk.Label(hdr, text="Recent clips", style="Group.TLabel").pack(side="left")
        hint(hdr, "double-click to play · right-click for more").pack(side="right")
        self.v_filter = tk.StringVar(value="All"); self.v_search = tk.StringVar()
        fb = ttk.Combobox(hdr, textvariable=self.v_filter, values=("All", "Publish", "Other"), width=8, state="readonly"); fb.pack(side="right", padx=(0, 14))
        fb.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        se = ttk.Entry(hdr, textvariable=self.v_search, width=24); se.pack(side="right", padx=(0, 8))
        Tip(se, "Search in clip name, title, victim names and date. Example: 'Marcus', '12.09', 'vehicle'.")
        self.v_search.trace_add("write", lambda *a: self.refresh_stats())
        ttk.Label(hdr, text="Search", style="Muted.TLabel").pack(side="right", padx=(0, 6))
        cols = ("when", "clip", "kills", "veh", "dist", "where")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        for c, t, w, a in (("when", "When", 110, "w"), ("clip", "Clip", 380, "w"), ("kills", "Kills", 50, "center"), ("veh", "Vehicles", 70, "center"), ("dist", "Longest", 70, "center"), ("where", "Folder", 70, "center")):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor=a, stretch=(c == "clip"))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=(4, 0)); sb.pack(side="left", fill="y", pady=(4, 0))
        self.tree.tag_configure("pub", foreground=FG); self.tree.tag_configure("other", foreground=MUTED)
        self.tree.bind("<Double-1>", lambda e: self.clip_open())
        self.tree.bind("<Button-3>", self._tree_menu)
        self.menu = tk.Menu(self, tearoff=0, bg=FIELD, fg=FG, activebackground=GOLD, activeforeground="#111", font=F)
        self.menu.add_command(label="Play", command=self.clip_open)
        self.menu.add_command(label="Show in folder", command=self.clip_reveal)
        self.menu.add_command(label="Copy title", command=self.clip_copy_title)
        self.menu.add_separator()
        self.menu.add_command(label="Why is it in this folder?", command=self.clip_why)
        self.menu.add_command(label="Re-clip the recording it came from", command=self.clip_forget_source)
        self.rows = {}

        bar = ttk.Frame(d); bar.pack(fill="x", pady=(10, 0))
        for txt, cmd in (("Recording guide", lambda: show_guide(self)), ("Discord", self.open_discord), ("Send feedback", self.feedback)):
            ttk.Button(bar, text=txt, command=cmd, style="Link.TButton").pack(side="left")
        ttk.Button(bar, text="Quit KillFeed", command=self.quit_app, style="Danger.TButton").pack(side="right")
        ttk.Button(bar, text="Hide to tray", command=self.hide, style="Link.TButton").pack(side="right", padx=6)

    def _scroll_tab(self, nb, title):
        """A tab whose content scrolls vertically when the window is too small (mouse wheel works while the tab is selected)."""
        outer = ttk.Frame(nb); nb.add(outer, text=title)
        cv = tk.Canvas(outer, bg=BG, highlightthickness=0); sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv, padding=(18, 12, 18, 12)); inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=inner, anchor="nw"); cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set); cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self._wheel.append((outer, cv))
        return inner

    def _on_wheel(self, e):
        cur = self.nb.select()
        for outer, cv in self._wheel:
            if cur == str(outer): cv.yview_scroll(-int(e.delta / 120), "units")

    # ---- settings
    def _build_settings(self, nb):
        se = self._scroll_tab(nb, "Settings")
        s = self.s
        self.v_in = tk.StringVar(value=s["input_dir"]); self.v_out = tk.StringVar(value=s["output_dir"])
        self.v_extra = tk.StringVar(value="; ".join(s.get("extra_input_dirs") or []))
        self.v_vertdir = tk.StringVar(value=s.get("vertical_dir") or ""); self.v_prefv = tk.BooleanVar(value=s.get("prefer_vertical", True))
        self.v_auto = tk.BooleanVar(value=s.get("autostart", True)); self.v_pause = tk.BooleanVar(value=s.get("pause_while_game_running", True))
        self.v_notify = tk.BooleanVar(value=s.get("notify", True)); self.v_shorts = tk.BooleanVar(value=s.get("make_shorts", True))
        rule = "multi_or_veh"
        if s["shorts"]["min_kills"] <= 1: rule = "all"
        elif s["shorts"]["min_vehicles"] > 10: rule = "multi_only"
        self.v_rule = tk.StringVar(value=rule); self.v_fallback = tk.BooleanVar(value=s["shorts"].get("fallback_single_when_empty", True))
        self.v_style = tk.StringVar(value=s.get("style", "center"))
        self.v_menabled = tk.BooleanVar(value=s["montage"].get("enabled", True)); self.v_mauto = tk.BooleanVar(value=s["montage"].get("auto", True))
        self.v_mmin = tk.IntVar(value=s["montage"]["min_minutes"]); self.v_mmax = tk.IntVar(value=s["montage"]["max_minutes"])
        self.v_mlabel = tk.StringVar(value=s["montage"].get("label", "recap"))

        def group(title, sub=None):
            g = ttk.LabelFrame(se, text=title, padding=(12, 8, 12, 10)); g.pack(fill="x", pady=(0, 12))
            if sub: hint(g, sub).pack(anchor="w", pady=(0, 6))
            return g
        def path_row(g, label, var, tip=None):
            ttk.Label(g, text=label).pack(anchor="w", pady=(4, 0))
            r = ttk.Frame(g); r.pack(fill="x")
            e = ttk.Entry(r, textvariable=var); e.pack(side="left", fill="x", expand=True)
            ttk.Button(r, text="Browse…", command=lambda: self._pick(var)).pack(side="left", padx=(6, 0))
            if tip: hint(g, tip).pack(anchor="w")

        g = group("Recordings", "Where KillFeed looks for new video files. Subfolders are included; its own output is skipped.")
        path_row(g, "Main recordings (16:9)", self.v_in)
        path_row(g, "Ready-made 9:16 recordings (optional, e.g. Aitum Vertical)", self.v_vertdir, "Leave empty if you only record normal 16:9.")
        ttk.Checkbutton(g, text="When the same kill exists in both, use the 9:16 as the short (it is already formatted)", variable=self.v_prefv).pack(anchor="w", pady=(4, 0))
        path_row(g, "Extra folders (optional, separate with ; )", self.v_extra, "For example a second drive or a Medal folder.")

        g = group("Output", "Finished clips. Publish\\, Other\\ and Recaps\\ are created inside this folder when needed.")
        path_row(g, "Output folder", self.v_out, "Tip: a OneDrive / Google Drive / Dropbox folder syncs the clips to your phone, so you can publish from the YouTube app.")

        g = group("Shorts", "Vertical 9:16 clips, 18–40 s, one .txt with the title next to each.")
        ttk.Checkbutton(g, text="Make shorts", variable=self.v_shorts).pack(anchor="w")
        ttk.Label(g, text="Good enough for Publish\\:").pack(anchor="w", pady=(8, 0))
        for t, v in (("Multikill or vehicle destroyed (recommended)", "multi_or_veh"), ("Every kill – I'll pick myself", "all"), ("Multikills only", "multi_only")):
            ttk.Radiobutton(g, text=t, variable=self.v_rule, value=v).pack(anchor="w", padx=(18, 0))
        ttk.Checkbutton(g, text="If a session gives nothing for Publish, promote its best single kill anyway", variable=self.v_fallback).pack(anchor="w", pady=(6, 0))
        ttk.Label(g, text="How 16:9 recordings become 9:16:").pack(anchor="w", pady=(8, 0))
        r = ttk.Frame(g); r.pack(anchor="w", padx=(18, 0))
        ttk.Radiobutton(r, text="Centre crop (sharp, shows the crosshair area)", variable=self.v_style, value="center").pack(side="left")
        ttk.Radiobutton(r, text="Blurred background (whole picture, smaller)", variable=self.v_style, value="blur").pack(side="left", padx=(16, 0))

        g = group("Recap", "A 16:9 chronological summary of the day's kills, cut from your normal recordings. Saved as “WARDOGS <name> <date>.mp4” in Recaps\\.")
        ttk.Checkbutton(g, text="Make recaps", variable=self.v_menabled).pack(anchor="w")
        ttk.Checkbutton(g, text="Build automatically when enough is collected (otherwise only via “Make recap now”)", variable=self.v_mauto).pack(anchor="w")
        r = ttk.Frame(g); r.pack(anchor="w", pady=(8, 0))
        ttk.Label(r, text="Length: from").pack(side="left")
        ttk.Spinbox(r, from_=1, to=60, textvariable=self.v_mmin, width=4).pack(side="left", padx=4)
        ttk.Label(r, text="to").pack(side="left")
        ttk.Spinbox(r, from_=1, to=120, textvariable=self.v_mmax, width=4).pack(side="left", padx=4)
        ttk.Label(r, text="minutes").pack(side="left")
        ttk.Label(r, text="      Name in the file:").pack(side="left")
        ttk.Entry(r, textvariable=self.v_mlabel, width=12).pack(side="left", padx=4)

        g = group("Behaviour")
        ttk.Checkbutton(g, text="Start with Windows (hidden in the tray)", variable=self.v_auto).pack(anchor="w")
        ttk.Checkbutton(g, text="Wait while the game is running (saves CPU – clipping starts when you close WARDOGS)", variable=self.v_pause).pack(anchor="w")
        ttk.Checkbutton(g, text="Windows notification when new clips are ready", variable=self.v_notify).pack(anchor="w")

        r = ttk.Frame(se); r.pack(fill="x", pady=(4, 0))
        ttk.Button(r, text="Save", command=self.save_settings, style="Primary.TButton").pack(side="left")
        self.v_saved = tk.StringVar(value=""); ttk.Label(r, textvariable=self.v_saved, style="Muted.TLabel").pack(side="left", padx=12, pady=(4, 0))

    # ---- advanced
    def _build_advanced(self, nb):
        av = self._scroll_tab(nb, "Advanced")
        hint(av, "Timing and detection. The defaults are tuned for WARDOGS at 1080p/1440p – change them only if the clips consistently start too early or too late.", wraplength=820).pack(anchor="w", pady=(0, 8))
        self.adv = {}
        spec = [
            ("Shorts", [
                ("Seconds before the kill", ("shorts", "pre"), "How much lead-up the short keeps before the first kill."),
                ("Seconds after the last kill", ("shorts", "post"), "How long the short keeps rolling after the last kill."),
                ("Join kills closer than N s into one short", ("shorts", "gap"), "Two kills 8 s apart become one multikill short when this is 12."),
                ("Minimum short length, seconds", ("shorts", "min"), None),
                ("Maximum short length, seconds", ("shorts", "max"), "YouTube Shorts allow up to 60 s; 20–35 s performs best."),
            ]),
            ("Recap", [
                ("Seconds before each kill", ("montage", "pre"), None),
                ("Seconds after each kill", ("montage", "post"), None),
                ("Maximum seconds per clip", ("montage", "clip_max"), None),
                ("Minimum kills for a clip to be included", ("montage", "min_kills"), None),
                ("Use recordings from the last N days", ("montage", "lookback_days"), None),
            ]),
            ("Detection", [
                ("Treat kills within N s as the same kill", ("dedup_seconds",), "Removes duplicates when the same moment exists in a replay and a full recording."),
                ("Delete clips in Other\\ after N days (0 = never)", ("cleanup", "andre_days"), "Your own recordings are never touched."),
            ]),
        ]
        cols = ttk.Frame(av); cols.pack(fill="x")
        left = ttk.Frame(cols); left.grid(row=0, column=0, sticky="nw", padx=(0, 40)); right = ttk.Frame(cols); right.grid(row=0, column=1, sticky="nw")
        for parent, groups in ((left, spec[:1] + spec[2:]), (right, spec[1:2])):
            r = 0
            for title, items in groups:
                ttk.Label(parent, text=title, style="Group.TLabel").grid(row=r, column=0, sticky="w", pady=(6, 2), columnspan=2); r += 1
                for lbl, key, tip in items:
                    v = tk.IntVar(value=self._get(key)); self.adv[key] = v
                    l = ttk.Label(parent, text=lbl); l.grid(row=r, column=0, sticky="w", pady=1, padx=(12, 16))
                    sp = ttk.Spinbox(parent, from_=0, to=999, textvariable=v, width=6); sp.grid(row=r, column=1, sticky="w")
                    if tip: Tip(l, tip); Tip(sp, tip)
                    r += 1
        b = ttk.Frame(av); b.pack(fill="x", pady=(14, 0))
        ttk.Button(b, text="Save", command=self.save_settings, style="Primary.TButton").pack(side="left")
        ttk.Button(b, text="Reset to defaults", command=self.reset_defaults).pack(side="left", padx=8)

        ttk.Label(av, text="Maintenance", style="Group.TLabel").pack(anchor="w", pady=(22, 4))
        m = ttk.Frame(av); m.pack(fill="x")
        b1 = ttk.Button(m, text="Rescan everything", command=self.rescan_all); b1.pack(side="left")
        Tip(b1, "Clip every recording again – you choose whether the old clips are deleted first, kept, or only failed recordings are retried.")
        b2 = ttk.Button(m, text="Open settings folder", command=lambda: os.startfile(C.appdata_dir())); b2.pack(side="left", padx=8)
        Tip(b2, "settings.json, ledger.json, killfeed.log and the text reports live here.")
        b3 = ttk.Button(m, text="Check for updates", command=self.check_updates); b3.pack(side="left")
        Tip(b3, f"Opens the download page. You are running {VERSION}.")
        hint(av, f"{C.appdata_dir()}", wraplength=820).pack(anchor="w", pady=(6, 0))

    # ---- log
    def _build_log(self, nb):
        lg = ttk.Frame(nb, padding=(18, 12, 18, 12)); nb.add(lg, text="Log")
        hint(lg, "Everything KillFeed does, newest at the bottom. This is what “Send feedback” includes.").pack(anchor="w", pady=(0, 6))
        self.txt = tk.Text(lg, wrap="word", state="disabled", font=FMONO, bg=PANEL, fg=FG, relief="flat", padx=10, pady=8, insertbackground=FG)
        self.txt.pack(fill="both", expand=True)
        try:
            with open(C.LOGFILE, encoding="utf-8", errors="replace") as f: tail = f.read()[-20000:]
            self.txt.configure(state="normal"); self.txt.insert("end", tail); self.txt.see("end"); self.txt.configure(state="disabled")
        except Exception: pass

    # ================================================================ settings helpers
    def _get(self, key):
        d = self.s
        for k in key: d = d[k]
        return d

    def _pick(self, var):
        d = filedialog.askdirectory(initialdir=var.get() if os.path.isdir(var.get()) else os.path.expanduser("~"))
        if d: var.set(d.replace("/", "\\"))

    def save_settings(self):
        s = self.s
        s["input_dir"] = self.v_in.get().strip(); s["output_dir"] = self.v_out.get().strip()
        s["extra_input_dirs"] = [x.strip() for x in self.v_extra.get().split(";") if x.strip()]
        s["vertical_dir"] = self.v_vertdir.get().strip(); s["prefer_vertical"] = self.v_prefv.get()
        s["autostart"] = self.v_auto.get(); s["pause_while_game_running"] = self.v_pause.get(); s["notify"] = self.v_notify.get()
        s["style"] = self.v_style.get(); s["make_shorts"] = self.v_shorts.get()
        s["shorts"]["min_kills"], s["shorts"]["min_vehicles"] = {"multi_or_veh": (2, 1), "all": (1, 1), "multi_only": (2, 99)}[self.v_rule.get()]
        s["shorts"]["fallback_single_when_empty"] = self.v_fallback.get()
        s["montage"]["enabled"] = self.v_menabled.get(); s["montage"]["auto"] = self.v_mauto.get()
        s["montage"]["min_minutes"] = max(1, self.v_mmin.get()); s["montage"]["max_minutes"] = max(s["montage"]["min_minutes"], self.v_mmax.get())
        s["montage"]["label"] = self.v_mlabel.get().strip() or "recap"
        for key, v in self.adv.items():
            d = s
            for k in key[:-1]: d = d[k]
            try: d[key[-1]] = int(v.get())
            except Exception: pass
        before = self._clip_signature
        C.save_settings(s); set_autostart(s["autostart"])
        probs = C.preflight(self.s, killclip)
        self.log("Settings saved."); self.v_saved.set(f"Saved {datetime.datetime.now():%H:%M}" + ("" if not probs else " – but: " + probs[0]))
        self.status("Settings saved.", "")
        self._clip_signature = self._sig()
        if before != self._clip_signature and self.L["processed"]:
            self.rescan_all("You changed how clips are cut. Existing clips were made with the old values.")

    def _sig(self):
        return tuple(self._get(k) for k in sorted(C.CLIP_KEYS))

    def reset_defaults(self):
        if not messagebox.askyesno(APP, "Reset the timing and detection values to the defaults?"): return
        for key, v in self.adv.items():
            d = C.DEFAULTS
            for k in key: d = d[k]
            v.set(d)
        self.save_settings()

    def rescan_all(self, reason=None):
        """Stop whatever is running right now, ask how to rescan, then do it as soon as the current file has let go."""
        self.log(f"Rescan requested (busy={self.busy})."); self.show()
        if self.busy:
            self.stop_req = True; killclip.ABORT = True
            for pr in list(getattr(killclip, "_procs", [])):
                try: pr.kill()
                except Exception: pass
            self.status("Stopping…", "The file being clipped is left for next time.")
        nfail = C.failed_count(self.L)
        opts = [("Start fresh", "fresh"), ("Re-clip, keep clips", "keep")]
        if nfail: opts.append((f"Retry {nfail} failed", "retry"))
        opts.append(("Cancel", None))
        ans = choose(self, "Rescan recordings",
                     (reason + "\n\n" if reason else "") +
                     "Start fresh – deletes everything in Publish, Other and Recaps, then clips every recording again with the current settings.\n\n"
                     "Re-clip, keep clips – clips every recording again; a new clip with the same name replaces the old one, recaps get a (2) suffix.\n\n"
                     + (f"Retry failed – only the {nfail} recording(s) that ended in an error are tried again.\n\n" if nfail else "") +
                     "Your own recordings are never touched.", opts)
        if not ans:
            self.log("Rescan cancelled."); return
        self._pending_action = ans; self.nb.select(0)
        if self.busy: self.status("Stopping…", "Rescan starts as soon as the current file has been aborted.")
        else: self._apply_rescan()

    def _apply_rescan(self):
        ans, self._pending_action = self._pending_action, None
        if ans == "retry":
            n = C.retry_failed(self.L); self.log(f"Retrying {n} failed recording(s).")
        else:
            if ans == "fresh":
                n = C.delete_outputs(self.s); self.log(f"Deleted {n} old clip files from Publish/Other/Recaps.")
            C.reset_ledger(self.L); self.log("Ledger reset – all recordings will be clipped again.")
        self.refresh_stats(); self.run_now()

    # ================================================================ clip list
    def refresh_stats(self):
        st = C.ledger_stats(self.L)
        for k in ("today", "week", "recaps", "sources"): self.v_nums[k].set(str(st[k]))
        self.tree.delete(*self.tree.get_children()); self.rows = {}
        q = self.v_search.get().strip().lower(); flt = self.v_filter.get()
        for row in st["recent"]:
            if flt != "All" and row["where"] != flt: continue
            if q:
                title = self.L["clips"].get(row["name"], {}).get("title") or ""
                hay = " ".join([row["name"], title, " ".join(row["victims"]), f"{row['at']:%d.%m.%Y}", "vehicle" if row["vehicles"] else "", "multikill" if row["kills"] >= 2 else ""]).lower()
                if q not in hay: continue
            iid = self.tree.insert("", "end", values=(f"{row['at']:%d.%m %H:%M}" if row["at"].year > 2000 else "", row["name"], row["kills"], row["vehicles"] or "",
                                                       f"{row['dist']} m" if row["dist"] else "", row["where"]), tags=("pub" if row["where"] == "Publish" else "other",))
            self.rows[iid] = row
        self._stats_dirty = False

    def _sel(self):
        s = self.tree.selection()
        return self.rows.get(s[0]) if s else None

    def _tree_menu(self, e):
        iid = self.tree.identify_row(e.y)
        if iid: self.tree.selection_set(iid); self.menu.tk_popup(e.x_root, e.y_root)

    def clip_open(self):
        r = self._sel()
        if r and os.path.exists(r["path"]): os.startfile(r["path"])
        elif r: messagebox.showinfo(APP, "That file is no longer there (moved or deleted).")

    def clip_reveal(self):
        r = self._sel()
        if r and os.path.exists(r["path"]): subprocess.Popen(["explorer", "/select,", r["path"]])
        elif r: messagebox.showinfo(APP, "That file is no longer there (moved or deleted).")

    def clip_copy_title(self):
        r = self._sel()
        if not r: return
        t = self.L["clips"].get(r["name"], {}).get("title") or os.path.splitext(r["name"])[0]
        self.clipboard_clear(); self.clipboard_append(t); self.status("Title copied.", t)

    def clip_why(self):
        r = self._sel()
        if r: messagebox.showinfo(APP, C.why_text(r, self.s))

    def clip_forget_source(self):
        r = self._sel()
        if not r or not r["source"]: return
        src = os.path.basename(r["source"])
        if self.busy: messagebox.showinfo(APP, "Wait until the current run has finished."); return
        if not messagebox.askyesno(APP, f"Clip {src} again on the next run?\n\nThe clips it produced stay in their folders; new ones will be added next to them."): return
        n = C.forget_source(self.L, src); self.log(f"Forgot {src} ({n} entries) – it will be clipped again."); self._stats_dirty = True; self.run_now()

    # ================================================================ log / status
    def _log_hook(self, msg): self.lines.append(msg)
    def log(self, msg): C.log(msg)

    def _pump(self):
        if self.busy:
            self._spin_i = (self._spin_i + 1) % 4; self.v_spin.set("◐◓◑◒"[self._spin_i])
            self.v_primary.set("■   Stop after this file" if not self.stop_req else ("■   Stop now" if not killclip.ABORT else "Stopping…"))
            self.b_run.configure(state="disabled" if killclip.ABORT else "normal"); self.b_recap.configure(state="disabled")
        else:
            self.v_spin.set(" "); self.v_primary.set("▶   Run now"); self.b_run.configure(state="normal"); self.b_recap.configure(state="normal")
        badge, col = ("● paused", MUTED) if self.paused else (("● working", GOLD) if self.busy else ("● watching", GREEN))
        if self.v_badge.get() != badge: self.v_badge.set(badge); self.l_badge.configure(foreground=col)
        self._tray_update()
        if self.lines:
            self.txt.configure(state="normal")
            while self.lines: self.txt.insert("end", self.lines.pop(0) + "\n")
            self.txt.see("end"); self.txt.configure(state="disabled")
        if self._stats_dirty and not self.busy: self.refresh_stats()
        elif self.busy and time.time() - getattr(self, "_last_stats", 0) > 5: self.refresh_stats(); self._last_stats = time.time()
        if not self.busy and getattr(self, "_pending_action", None):      # rescan chosen while clipping: run it now that the file let go
            self._apply_rescan()
        self.after(300, self._pump)

    def status(self, msg, sub=None):
        def go():
            self.v_status.set(msg)
            if sub is not None: self.v_sub.set(sub)
        self.after(0, go)
    def progress(self, n, tot):
        self.after(0, lambda: self.prog.configure(maximum=max(1, tot), value=n))

    def show(self):
        self.deiconify(); self.lift(); self.focus_force()
    def hide(self):
        self.withdraw()
        if not self.s.get("tray_hint_shown"):
            self.s["tray_hint_shown"] = True; C.save_settings(self.s)
            toast(APP, "KillFeed keeps running in the tray (next to the clock). Right-click the icon to open or quit.")

    def open_out(self):
        d = self.s.get("output_dir")
        if d and os.path.isdir(d): os.startfile(d)
        else: messagebox.showinfo(APP, "The output folder does not exist yet – it is created with the first clip.")

    # ================================================================ tray
    def _start_tray(self):
        try:
            import pystray
            self.icons = tray_icons()
            menu = pystray.Menu(
                pystray.MenuItem("Open KillFeed", lambda: self.after(0, self.show), default=True),
                pystray.MenuItem(lambda i: "Working…" if self.busy else "Run now", lambda: self.after(0, self.run_now), enabled=lambda i: not self.busy),
                pystray.MenuItem("Make recap now", lambda: self.after(0, self.montage_now)),
                pystray.MenuItem("Open output folder", lambda: self.after(0, self.open_out)),
                pystray.MenuItem("Pause", lambda: self.after(0, self.toggle_pause), checked=lambda i: self.paused),
                pystray.MenuItem("Discord", lambda: self.after(0, self.open_discord)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda: self.after(0, self.quit_app)))
            self.icon = pystray.Icon(APP, self.icons["idle"], f"{APP} – watching recordings", menu)
            self.icon.run_detached()
            self.log("Tray icon active (Windows 11 hides it under ^ next to the clock until you drag it out). The close button hides the window; Quit is in the menu.")
        except Exception as e:
            self.icon = None; self.log(f"Tray icon could not be created ({e}). The window stays open; use Quit to stop.")
            self.protocol("WM_DELETE_WINDOW", self.quit_app); self.show()

    def _tray_update(self):
        if not self.icon or not self.icons: return
        st = "paused" if self.paused else (("work1" if self._spin_i % 2 else "work0") if self.busy else "idle")
        if st != self._tray_state:
            self._tray_state = st
            try:
                self.icon.icon = self.icons[st]
                self.icon.title = f"{APP} – " + ("paused" if self.paused else ("working" if self.busy else "watching recordings"))
            except Exception: pass

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.v_pausebtn.set("▶   Resume")
            self.status("Paused – not watching the folder.", "Finishing the file being clipped now, then stopping." if self.busy else "Press Resume to continue.")
        else:
            self.v_pausebtn.set("⏸   Pause"); self.status("Watching for new recordings.", self.s["input_dir"])
        if self.icon: self.icon.update_menu()

    def check_updates(self):
        import webbrowser
        url = self.s.get("update_url") or ""
        if url: webbrowser.open(url)
        else: messagebox.showinfo(APP, f"You are running {VERSION}. No update page is set yet.")

    def open_discord(self):
        import webbrowser
        url = self.s.get("discord_invite") or ""
        if url: webbrowser.open(url)
        else: messagebox.showinfo(APP, "No Discord link set (settings.json → discord_invite).")

    def quit_app(self):
        if self.busy and not messagebox.askyesno(APP, "KillFeed is clipping right now. Quit anyway? (The current file starts over next time.)"):
            return
        self.stop_flag = True
        try:
            if self.icon: self.icon.visible = False; self.icon.stop()
        except Exception: pass
        try:
            for pr in getattr(killclip, "_procs", []):      # kill ffmpeg/tesseract running now
                try: pr.kill()
                except Exception: pass
            n = C.clean_work()
            if n: C.log(f"Quit: removed {n} half-finished files.")
        except Exception: pass
        C.log("Quit by user.")
        try: self.destroy()
        finally: os._exit(0)

    # ================================================================ work
    def _watch_loop(self):
        time.sleep(3)
        while not self.stop_flag:
            try:
                if not self.paused and not self.busy:
                    if self.s.get("pause_while_game_running", True) and C.game_running(self.s.get("game_process_hint", "wardogs")):
                        self.status("WARDOGS is running – waiting.", "Clipping starts when you close the game.")
                    elif C.ready_sources(self.s, self.L):
                        self._do_run()
                    else:
                        self.status("Watching for new recordings.", f"{self.s['input_dir']} · nothing new at {datetime.datetime.now():%H:%M}")
            except Exception as e:
                self.log(f"ERROR in watcher: {e}")
            for _ in range(int(self.s.get("watch_interval_s", 60))):
                if self.stop_flag: return
                time.sleep(1)

    def primary_action(self):
        if self.busy:
            self.stop_req = True
            if self._stop_clicks:   # second click = abort the current file right now
                killclip.ABORT = True
                for pr in list(getattr(killclip, "_procs", [])):
                    try: pr.kill()
                    except Exception: pass
                self.status("Stopping now…", "The current file is left for next time.")
            else:
                self._stop_clicks = 1; self.status(self.v_status.get(), "Stopping after this file… (click again to stop right now)")
        else: self.run_now()

    def run_now(self):
        if self.busy: return
        threading.Thread(target=self._do_run, daemon=True).start()

    def montage_now(self):
        if self.busy: return
        ready, cands = C.montage_ready(self.s, self.L, killclip)
        if not cands:
            messagebox.showinfo(APP, "No qualifying clips for a recap yet.\nRecaps are built from kills in your normal 16:9 recordings."); return
        have = sum(c["len"] for c in cands) / 60
        q = (f"Only {have:.1f} min collected – the minimum is {self.s['montage']['min_minutes']} min.\nBuild a shorter recap anyway?" if not ready
             else f"Build a recap now from {len(cands)} clip(s), about {min(have, self.s['montage']['max_minutes']):.1f} min?\nIt lands in Recaps\\ and takes a minute or two.")
        if not messagebox.askyesno(APP, q): return
        self.nb.select(0)
        def go():
            self.busy = True; self.status("Building recap…", "Concatenating the collected clips.")
            try:
                out = C.build_montage(self.s, self.L, killclip, force=True, log=self.log)
                if out:
                    self.status("Recap ready.", os.path.basename(out))
                    if self.s.get("notify", True): toast("Recap ready", os.path.basename(out), os.path.dirname(out))
                else:
                    self.status("No qualifying clips for a recap yet.", "Recaps use kills from your normal 16:9 recordings.")
            finally:
                self.busy = False; self._stats_dirty = True
        threading.Thread(target=go, daemon=True).start()

    def _do_run(self):
        self.busy = True; self.stop_req = False; killclip.ABORT = False; self._stop_clicks = 0
        try:
            probs = C.preflight(self.s, killclip)
            if probs:
                self.status("Cannot clip yet.", probs[0]); self.log("PROBLEM: " + probs[0]); return
            def prog(n, tot, name):
                self.progress(n, tot); self.status(f"Clipping {n} of {tot}", name)
            self.status("Looking for new recordings…", "")
            r = C.run_once(self.s, self.L, killclip, log=self.log, progress=prog, stop=lambda: self.stop_flag or self.paused or self.stop_req)
            self.progress(0, 1)
            npub, nand = len(r["publiser"]), len(r["andre"])
            if r["sources"]:
                msg = f"{npub} ready to publish, {nand} in Other" + (f", {r['duplicate']} duplicate(s) removed" if r["duplicate"] else "")
                self.status("Done.", msg); self.log(f"Done: {msg}.")
                if self.s.get("notify", True) and (npub or r["montage"]):
                    parts = []
                    if npub: parts.append(f"{npub} short{'s' if npub != 1 else ''} ready in Publish")
                    if r["montage"]: parts.append("new recap in Recaps")
                    toast(APP, " · ".join(parts), os.path.join(self.s["output_dir"], "Publish" if npub else "Recaps"))
            else:
                self.status("Nothing new.", f"Checked at {datetime.datetime.now():%H:%M}")
        except Exception as e:
            self.log(f"ERROR: {e}"); self.status("Something went wrong.", f"{e} – see the Log tab, or press Send feedback.")
        finally:
            self.busy = False; self.stop_req = False; self._stats_dirty = True

    def feedback(self):
        out = os.path.join(desktop_dir(), f"killfeed-feedback-{datetime.datetime.now():%Y%m%d-%H%M}.zip")
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                for p in [C.LOGFILE, C.SETTINGS, C.LEDGER]:
                    if os.path.exists(p): z.write(p, os.path.basename(p))
                for j in glob.glob(os.path.join(C.REPORTS, "*.json")):
                    z.write(j, "reports/" + os.path.basename(j))
            messagebox.showinfo(APP, f"Feedback zip created:\n{out}\n\nDrag it into #feedback on Discord (opening now) and say what went wrong. It contains the log and text hits only – never video.")
            try: subprocess.Popen(["explorer", "/select,", out])
            except Exception: pass
            self.open_discord()
        except Exception as e:
            messagebox.showerror(APP, f"Could not create the zip: {e}")

# ------------------------------------------------------------------ start
def main():
    if "--run" in sys.argv:                       # one pass without GUI (debugging / task scheduler)
        s = C.load_settings(); L = C.load_ledger()
        r = C.run_once(s, L, killclip, log=lambda m: print(m, flush=True))
        print(r); return
    if not single_instance():
        return
    C.log(f"{APP} {VERSION} started")
    app = App(start_hidden="--tray" in sys.argv)
    try:
        app.mainloop()
    except tk.TclError:
        pass

if __name__ == "__main__":
    main()
