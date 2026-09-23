"""Ende-til-ende-test av kf_core uten mini: syntetiske 16:9-opptak med ekte kill-tekst i ROI-sonen,
to filer som overlapper i klokketid (dedup), utvalg Publiser/Andre, reserve, recap-montasje."""
import os, sys, json, subprocess, shutil, time, datetime
T = os.path.dirname(os.path.abspath(__file__))
os.environ["APPDATA"] = os.path.join(T, "appdata"); os.environ["LOCALAPPDATA"] = os.path.join(T, "localappdata")
for d in ("appdata", "localappdata", "rec", "out"):
    shutil.rmtree(os.path.join(T, d), ignore_errors=True); os.makedirs(os.path.join(T, d))
sys.path.insert(0, os.path.join(T, "..", "app"))
import kf_core as C, killclip

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1920, 1080
x, y = int(W * 0.39) + 20, int(H * 0.71) + 20     # inne i sone 1 (16:9)

BANNER_XY = (x, y)                                       # sone 1: banneret under siktet (vaart eget)
MONEY_XY = (int(W * 0.80) + 10, int(H * 0.02) + 10)      # sone 2: penge-HUD oppe til hoyre
FEED_XY = (10, int(H * 0.43) + 20)                       # sone 3: kill-feeden til venstre (alle spillere)

def make(name, dur, events):
    """events: (t_start, t_end, tekst) eller (t_start, t_end, tekst, (x, y)). Hvit tekst paa moerk bakgrunn."""
    vf = "drawbox=x=0:y=0:w=iw:h=ih:color=0x202020:t=fill"
    for e in events:
        a, b, txt = e[0], e[1], e[2]
        px, py = e[3] if len(e) > 3 else BANNER_XY
        vf += f",drawtext=fontfile={FONT}:text='{txt}':fontcolor=white:fontsize=34:x={px}:y={py}:enable='between(t,{a},{b})'"
    out = os.path.join(T, "rec", name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate=30", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", str(dur), "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-shortest", out], check=True)
    return out

# Klokketid: "2026-09-12 10-00-00" = start (vanlig opptak). Replay har slutt-stempel.
# Opptak A: 90 s fra 10:00:00, kills ved 20 s (enkelt) og 60+62 s (dobbelt = multikill)
make("2026-09-12 10-00-00.mkv", 90, [(20, 22.5, "KILL CONFIRMED  +$300"), (60, 62.5, "KILL CONFIRMED  +$300"), (66, 68.5, "KILL CONFIRMED  +$650")])
# Replay B: 40 s som slutter 10:01:20 -> starter 10:00:40; multikillet ligger ved 20 s og 22.5 s her (samme klokketid som A)
make("Replay WARDOGS 2026-09-12 10-01-20.mkv", 40, [(20, 22.5, "KILL CONFIRMED  +$300"), (26, 28.5, "KILL CONFIRMED  +$650")])
# Opptak C: annen dag, bare vehicle
make("2026-09-13 20-00-00.mkv", 60, [(30, 33, "VEHICLE DESTROYED  +$1,200")])
# Opptak D: ingen egne kills. Teksten staar BARE i venstre kill-feed (andre spilleres drap) og i penge-HUD-en
# oppe til hoyre - begge er utenfor 9:16-utsnittet. Skal ikke gi ett eneste klipp. (Regresjon: DQkBYvQGW4E)
make("2026-09-14 20-00-00.mkv", 60,
     [(20, 30, "KILL CONFIRMED  VEHICLE DESTROYED", FEED_XY), (20, 30, "+$1,200  VEHICLE DESTROYED", MONEY_XY)])
for f in os.listdir(os.path.join(T, "rec")):
    os.utime(os.path.join(T, "rec", f), (time.time() - 600, time.time() - 600))   # gamle nok

s = C.load_settings()
s.update({"input_dir": os.path.join(T, "rec"), "output_dir": os.path.join(T, "out"), "setup_done": True, "min_file_age_s": 1, "pause_while_game_running": False})
s["montage"].update({"min_minutes": 0.2, "max_minutes": 1, "lookback_days": 3650})
C.save_settings(s)
L = C.load_ledger()

# første skann: størrelser registreres, ingenting er "stabilt" ennå -> 0 klare; andre skann -> alle 3
assert len(C.ready_sources(s, L)) == 4   # mtime-alder er hovedgjerdet; størrelse er ekstra sjekk ved neste skann
assert len(C.ready_sources(s, L)) == 4
r = C.run_once(s, L, killclip, log=print)
print("\nRESULTAT:", json.dumps({k: v for k, v in r.items()}, indent=1, ensure_ascii=False))
print("\nLEDGER clips:")
for k, v in L["clips"].items(): print(f"  {v['status']:9} {k}  kills={v.get('kills')} veh={v.get('vehicles')} of={v.get('of','')}")
pub = sorted(os.listdir(os.path.join(T, "out", "Publish"))); andre = sorted(os.listdir(os.path.join(T, "out", "Other")))
mont = sorted(os.listdir(os.path.join(T, "out", "Recaps")))
print("\nPubliser:", pub); print("Andre:", andre); print("Montasje:", mont)

assert not any("2026-09-14" in k for k in L["clips"]), \
    "tekst bare i venstre feed / penge-HUD skal ikke gi klipp: " + str([k for k in L["clips"] if "2026-09-14" in k])

st = [v["status"] for v in L["clips"].values()]
assert st.count("duplicate") >= 1, "replay-multikillet skulle vært duplikat av opptak A"
assert any(v["status"] == "publiser" and v["kills"] >= 2 for v in L["clips"].values()), "multikill skal i Publiser"
assert any(v["status"] == "publiser" and v["vehicles"] >= 1 for v in L["clips"].values()), "vehicle skal i Publiser"
assert any(v["status"] == "andre" for v in L["clips"].values()), "enkeltkill skal i Andre"
assert len(mont) == 2 and mont[0].endswith(".mp4") and mont[0].startswith("WARDOGS recap 2026-09-12"), mont
d = killclip.probe(os.path.join(T, "out", "Recaps", mont[0]))
print("montasje:", d)
assert d[1] == 1920 and d[2] == 1080 and 10 < d[0] < 61
print(open(os.path.join(T, "out", "Recaps", mont[1]), encoding="utf-8").read())
# andre runde: ingenting nytt, ingen ny montasje (alt er brukt)
r2 = C.run_once(s, L, killclip, log=print)
assert r2["sources"] == 0 and r2["montage"] is None
print("\nALT OK")
