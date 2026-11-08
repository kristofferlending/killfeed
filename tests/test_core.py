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
# Opptak E: to kills 18 s fra hverandre - kobles til ett langt klipp av gap=12 via mellomliggende treff,
# men er ikke en byge. Skal havne i Andre, ikke Publiser. (Regresjon: lange kjedelige klipp i Publish)
make("2026-09-15 20-00-00.mkv", 70,
     [(15, 17.5, "KILL CONFIRMED"), (25, 27.5, "+$300"), (33, 35.5, "KILL CONFIRMED")])
# Opptak D: ingen egne kills. Teksten staar BARE i venstre kill-feed (andre spilleres drap) og i penge-HUD-en
# oppe til hoyre - begge er utenfor 9:16-utsnittet. Skal ikke gi ett eneste klipp. (Regresjon: DQkBYvQGW4E)
make("2026-09-14 20-00-00.mkv", 60,
     [(20, 30, "KILL CONFIRMED  VEHICLE DESTROYED", FEED_XY), (20, 30, "+$1,200  VEHICLE DESTROYED", MONEY_XY)])
# --- enhetstest for tellingen og de tre 9:16-stilene (egen fil, ryddes bort for roerledningen under) ---
# To kills rett etter hverandre: det andre banneret erstatter det forste uten et eneste moerkt bilde
# mellom dem, saa tidsgapet er ~0. Belopet inne i banneret er det som skiller dem.
# (Regresjon: klipp merket "1 kill" der det var 2 - WARDOGS 2026-09-26 19-51-28-auto42)
os.makedirs(os.path.join(T, "unit"), exist_ok=True)
# belopet paa egen linje: hele banneret maa faa plass inne i ROI-en (422x108 px paa 1920x1080)
_AMT_XY = (BANNER_XY[0], BANNER_XY[1] + 42)
_ov = make("overlap.mkv", 24, [(8, 12.9, "KILL CONFIRMED"), (8, 12.9, "+$2,250", _AMT_XY),
                               (13, 18, "KILL CONFIRMED"), (13, 18, "+$1,500", _AMT_XY)])
_hits = killclip.detect(_ov, 4)
_runs = list(getattr(killclip.detect, "reward", []) or [])
assert len(_runs) == 2, f"banner-belopet ble ikke lest som to bannere: {_runs}"
_ts = [t for t, kk in _hits if any(x.startswith("KILLCONFIRMED") for x in kk)]
def _count(rr):
    n = 0; last = -99
    for t in _ts:
        if t - last > 3 or (last > -99 and any(last < r <= t for r in rr)): n += 1
        last = t
    return n
assert _count([]) == 1, "uten belopet skal den gamle regelen fortsatt slaa dem sammen"
assert _count([t for t, _ in _runs]) == 2, f"to kills skal telles som to, fikk {_count([t for t, _ in _runs])}"
print(f"telling: {len(_runs)} bannere, {_count([t for t, _ in _runs])} kills (gammel regel: {_count([])})")
# alle tre stilene skal levere 1080x1920 fra et 16:9-opptak
for _st in ("center", "blur", "stack"):
    _o = os.path.join(T, "unit", _st + ".mp4")
    killclip.cut(_ov, 8, 11, _o, W, H, _st)
    _d = killclip.probe(_o)
    assert (_d[1], _d[2]) == (1080, 1920), f"stil {_st} ga {_d[1]}x{_d[2]}"
print("stiler: center/blur/stack gir alle 1080x1920")

# Et kjoretoy-kill med forer fyrer av KILL CONFIRMED og VEHICLE DESTROYED i samme oyeblikk. Tellingen
# skal beholde begge (Publiser-regelen bygger paa dem), men tittelen skal nevne hendelsen EN gang.
assert killclip.auto_title(0, 0, 2, 0, None, 0) == "WARDOGS – 2 vehicles destroyed #shorts"
assert killclip.auto_title(1, 0, 1, 0, None, 0) == "WARDOGS – 1 kill, 1 vehicle destroyed #shorts"
assert killclip.auto_title(0, 0, 2, 0, None, 126) == "WARDOGS – 2 vehicles destroyed #shorts"
assert killclip.auto_title(3, 0, 0, 0, None, 420) == "WARDOGS – 3 kills #shorts"        # avstand staar ikke i navnet
assert killclip.auto_title(3, 0, 0, 0, None, 0) == "WARDOGS – 3 kills #shorts"
# Et kjoretoy-kill er verdt 2, ikke 3: teller vi KILL CONFIRMED-banneret i tillegg, blir ett
# kjoretoy-kill likt en 3-kill streak - og streaken er det bedre klippet.
_streak = killclip.clip_score(killclip.solo_kills_of({"kills": 3, "vehicles": 0, "abs_events": [1, 2, 3]}), 0, 0, 15)
_vkill  = killclip.clip_score(killclip.solo_kills_of({"kills": 1, "vehicles": 1, "abs_events": [1, 1]}), 1, 0, 15)
assert _streak > _vkill, f"3-kill streak ({_streak}) maa slaa ett kjoretoy-kill ({_vkill})"
# og et gammelt klipp uten solo_kills skal utledes fra de doble tidsstemplene, ikke telles som 3
assert killclip.solo_kills_of({"kills": 1, "vehicles": 1, "abs_events": [1, 1]}) == 0
assert killclip.solo_kills_of({"kills": 2, "vehicles": 1, "abs_events": [1, 1, 2]}) == 1
assert killclip.solo_kills_of({"kills": 3, "solo_kills": 3, "abs_events": [1, 2, 3]}) == 3
print(f"score: 3-kill streak {_streak} > kjoretoy-kill {_vkill}")

_vk = make("vehkill.mkv", 30, [(10, 12.5, "KILL CONFIRMED"), (10, 12.5, "VEHICLE DESTROYED", _AMT_XY),
                               (18, 20.5, "KILL CONFIRMED"), (18, 20.5, "VEHICLE DESTROYED", _AMT_XY)])
_vs = killclip.process(_vk, os.path.join(T, "unit"), fps=2, pre=4, post=3, gap=12, mn=8, mx=30, log=lambda *a: None)
assert _vs, "kjoretoy-killene skulle gitt et klipp"
_seg = _vs[0]
assert _seg["kills"] >= 1 and _seg["vehicles"] >= 1, _seg
assert _seg["solo_kills"] == 0, f"ingen av killene var rene infanteri-kill: {_seg}"
assert "kill" not in _seg["title"].split("vehicle")[0], f"tittelen teller kjoretoy-killet to ganger: {_seg['title']}"
print(f"kjoretoy-kill: kills={_seg['kills']} vehicles={_seg['vehicles']} solo={_seg['solo_kills']} -> {_seg['title']}")
os.remove(_vk)

# Ensomme enkeltkill skal hoppes over, men et kill sammen med kjoretoyet det odela er ETT oyeblikk
# med to hendelser - de skal beholdes. (Paa kanalen er 1 kill + 1 kjoretoy de beste klippene.)
# ROI-en er bare 108 px hoy, saa det er plass til to linjer: banner + andrelinje inne i sona.
_lone = make("lonely.mkv", 40, [(6, 8.5, "KILL CONFIRMED"), (6, 8.5, "+$300", _AMT_XY),   # ensomt
                                (30, 32.5, "KILL CONFIRMED"),                              # sammen med...
                                (30, 32.5, "VEHICLE DESTROYED", _AMT_XY)])                 # ...et kjoretoy
_lh = killclip.detect(_lone, 2)
_lb = killclip.event_bursts(_lh)
assert _lb and len(_lb) == 2, f"forventet to oyeblikk, fikk {_lb}"
assert killclip.is_lonely_single(_lh, 2, 14, 1, 0, 15.0, _lb), "det ensomme killet ble ikke fanget"
assert not killclip.is_lonely_single(_lh, 26, 38, 1, 1, 15.0, _lb), "kill + kjoretoy skal ikke regnes som ensomt"
_segs = killclip.process(_lone, os.path.join(T, "unit"), fps=2, pre=4, post=3, gap=12, mn=8, mx=30,
                         lonely_gap=15, log=lambda *a: None)
_starts = sorted(round(x["start"]) for x in _segs)
assert _segs, "kill + kjoretoy skulle blitt klippet"
assert all(s_ > 14 for s_ in _starts), f"det ensomme killet ble klippet likevel: {_starts}"
print(f"ensomme enkeltkill: hoppet over, kill+kjoretoy beholdt ({len(_segs)} klipp, start {_starts})")
os.remove(_lone)
os.remove(_ov)

for f in os.listdir(os.path.join(T, "rec")):
    os.utime(os.path.join(T, "rec", f), (time.time() - 600, time.time() - 600))   # gamle nok

s = C.load_settings()
s.update({"input_dir": os.path.join(T, "rec"), "output_dir": os.path.join(T, "out"), "setup_done": True, "min_file_age_s": 1, "pause_while_game_running": False})
s["montage"].update({"min_minutes": 0.2, "max_minutes": 1, "lookback_days": 3650})
C.save_settings(s)
L = C.load_ledger()

# første skann: størrelser registreres, ingenting er "stabilt" ennå -> 0 klare; andre skann -> alle 3
assert len(C.ready_sources(s, L)) == 5   # mtime-alder er hovedgjerdet; størrelse er ekstra sjekk ved neste skann
assert len(C.ready_sources(s, L)) == 5
r = C.run_once(s, L, killclip, log=print)
print("\nRESULTAT:", json.dumps({k: v for k, v in r.items()}, indent=1, ensure_ascii=False))
print("\nLEDGER clips:")
for k, v in L["clips"].items(): print(f"  {v['status']:9} {k}  kills={v.get('kills')} veh={v.get('vehicles')} of={v.get('of','')}")
def _ls(*parts):   # Other\ finnes kanskje ikke: ensomme enkeltkill klippes ikke lenger i det hele tatt
    d = os.path.join(T, "out", *parts)
    return sorted(os.listdir(d)) if os.path.isdir(d) else []
pub = _ls("Publish"); andre = _ls("Other"); mont = _ls("Recaps")
print("\nPubliser:", pub); print("Andre:", andre); print("Montasje:", mont)

# Opptak E: to kills 18 s fra hverandre. Hver av dem er et ensomt enkeltkill (ingenting innen 15 s),
# saa med lonely_gap_s=15 blir de ikke klippet i det hele tatt - og havner dermed heller aldri i Publiser.
spread = {k: v for k, v in L["clips"].items() if "2026-09-15" in k}
assert not spread, "to spredte enkeltkill skal ikke gi klipp naar lonely_gap_s staar paa: " + str(spread)

assert not any("2026-09-14" in k for k in L["clips"]), \
    "tekst bare i venstre feed / penge-HUD skal ikke gi klipp: " + str([k for k in L["clips"] if "2026-09-14" in k])

st = [v["status"] for v in L["clips"].values()]
assert st.count("duplicate") >= 1, "replay-multikillet skulle vært duplikat av opptak A"
assert any(v["status"] == "publiser" and v["kills"] >= 2 for v in L["clips"].values()), "multikill skal i Publiser"
# Et ENSLIG kjoeretoey-kill er en hendelse og gaar ikke lenger til Publish av seg selv - det er
# shorts.publish.vehicle_qualifies, som staar av. Slaa den paa, og det samme klippet skal gjennom.
_veh = [v for v in L["clips"].values() if v.get("vehicles", 0) >= 1]
assert _veh, "testdataene skal inneholde minst ett kjoeretoey-kill"
_lone = [v for v in _veh if len(set(v.get("abs_events") or [])) <= 1]
if _lone:
    assert all(v["status"] != "publiser" for v in _lone), \
        "enslig kjoeretoey-kill skal ikke til Publish naar vehicle_qualifies staar av"
    _sh_on = dict(s["shorts"], publish=dict(s["shorts"]["publish"], vehicle_qualifies=True))
    assert C.qualifies(_lone[0], _sh_on), "med vehicle_qualifies paa skal det samme klippet gjennom"
    print("kjoeretoey: enslig kjoeretoey-kill styres av shorts.publish.vehicle_qualifies")
else:
    assert any(v["status"] == "publiser" for v in _veh), "kjoeretoey sammen med noe annet skal til Publish"
# Ingenting som er klippet skal vaere et ensomt enkeltkill - de skal vaere luket bort for de ble kuttet.
for _k, _v in L["clips"].items():
    if _v.get("status") in ("publiser", "andre"):
        assert (_v.get("kills") or 0) >= 2 or (_v.get("vehicles") or 0) >= 1, \
            f"{_k} er et ensomt enkeltkill og skulle aldri blitt klippet: {_v}"
assert len(mont) == 2 and mont[0].endswith(".mp4") and mont[0].startswith("WARDOGS recap 2026-09-12"), mont
d = killclip.probe(os.path.join(T, "out", "Recaps", mont[0]))
print("montasje:", d)
assert d[1] == 1920 and d[2] == 1080 and 10 < d[0] < 61
print(open(os.path.join(T, "out", "Recaps", mont[1]), encoding="utf-8").read())
# innstillingen: strammer vi shorts.publish.double_s helt inn, skal selv et ekte dobbelkill ut av
# Publiser - og filene skal faktisk flytte seg, ikke bare hovedboka. Slakker vi igjen, kommer det
# tilbake. (Et SPREDT 2-kill-klipp duger ikke til denne testen lenger: med tetthetsregelen naar det
# aldri Publish i utgangspunktet, saa det er ingenting aa flytte.)
# Terskelen i shorts.publish skal flytte BAADE hovedboka og filene, begge veier.
# Testen lager sitt eget klipp i stedet for aa lete etter et passende i fixturen: den skal maale
# knotten, ikke om testdataene tilfeldigvis inneholder et ekte dobbelkill. (Reserven maa ogsaa av -
# naar ingenting kvalifiserer forfremmer promote_fallback ett klipp, og resort_clips hopper over
# reserveklipp med vilje, saa Publish staar stille uansett terskel.)
_fb0 = s["shorts"].get("fallback_single_when_empty", True)
s["shorts"]["fallback_single_when_empty"] = False
_pub_dir = os.path.join(T, "out", "Publish"); _oth_dir = os.path.join(T, "out", "Other")
os.makedirs(_pub_dir, exist_ok=True); os.makedirs(_oth_dir, exist_ok=True)
_tn2 = "terskeltest-auto01-000.0-015.0.mp4"
_tp2 = os.path.join(_oth_dir, _tn2)
open(_tp2, "wb").write(b"\0" * 32)
open(os.path.splitext(_tp2)[0] + ".txt", "w", encoding="utf-8").write("WARDOGS - 2 kills #shorts\n")
_T2 = 1790000000.0
L["clips"][_tn2] = {"status": "andre", "path": _tp2, "kills": 2, "solo_kills": 2, "vehicles": 0,
                    "len": 15.0, "score": 2.0, "max_dist_m": 0, "at": "2026-10-09T10:00:00",
                    "abs_events": [_T2, _T2 + 4.0]}          # to kills, fire sekunder fra hverandre

s["shorts"]["publish"]["double_s"] = 6          # slakt nok: fire sekunder teller som en dobbel
np_, _ = C.resort_clips(s, L, log=print)
assert np_ >= 1, "slakk terskel skulle flyttet klippet til Publish"
assert L["clips"][_tn2]["status"] == "publiser"
assert os.path.exists(os.path.join(_pub_dir, _tn2)), "fila skulle fulgt med til Publish"
assert os.path.exists(os.path.join(_pub_dir, os.path.splitext(_tn2)[0] + ".txt")), "tittelfila ble ikke med"

s["shorts"]["publish"]["double_s"] = 2          # for stramt: fire sekunder er ikke lenger en dobbel
_, na_ = C.resort_clips(s, L, log=print)
assert na_ >= 1, "stram terskel skulle flyttet klippet tilbake til Other"
assert L["clips"][_tn2]["status"] == "andre"
assert os.path.exists(os.path.join(_oth_dir, _tn2)), "fila forsvant i stedet for aa bli flyttet"
assert not os.path.exists(os.path.join(_pub_dir, _tn2))
print(f"terskel: {np_} inn ved slakk double_s, {na_} ut ved stram - filene fulgte med begge veier")

s["shorts"]["publish"]["double_s"] = 3
L["clips"].pop(_tn2, None)
for _d in (_pub_dir, _oth_dir):
    for _e in (_tn2, os.path.splitext(_tn2)[0] + ".txt"):
        try: os.remove(os.path.join(_d, _e))
        except OSError: pass
s["shorts"]["fallback_single_when_empty"] = _fb0

# klipp-browseren: run_once skal ha skrevet clips.html med miniatyrbilder bakt inn i fila
page = os.path.join(T, "out", "clips.html")
assert os.path.exists(page), "clips.html ble ikke skrevet"
html = open(page, encoding="utf-8").read()
assert "data:image/jpeg;base64," in html, "miniatyrbildene ble ikke bakt inn"
assert "<title>KillFeed clips</title>" in html and "Most kills" in html
# hover-avspilling: videoen skal lages forst ved hover, og lenka skal peke paa selve klippet
assert "wireHover()" in html and 'data-src="' in html, "hover-avspilling mangler i sida"
assert "function clipUrl(c)" in html, "klipp-url-hjelperen mangler"
assert "<video" not in html, "videoelementene skal ikke ligge i sida fra start - de lages ved hover"
for nm in L["clips"]:
    if L["clips"][nm].get("status") in ("publiser", "andre"):
        assert nm.replace("\\", "/") in html or os.path.splitext(nm)[0] in html, f"{nm} mangler i clips.html"
import json as _json
_data = _json.loads(html.split("const CLIPS = ", 1)[1].split(";\n", 1)[0])
assert len(_data) == sum(1 for v in L["clips"].values() if v.get("status") in ("publiser", "andre")), _data
assert all(isinstance(r["kills"], int) and r["len"] > 0 for r in _data), _data
print(f"clips.html: {len(_data)} klipp, {len(html)//1024} KB")

# gamle, feilaktige titler i hovedboka skal ikke vises: sida regner tittel og poeng ut av
# tellingene selv. Et okkupert kjoretoy ble tidligere skrevet som bade kill og kjoretoy, saa
# lagret tittel sier "2 kills, 2 vehicles destroyed" der det skjedde to ting.
_nm = next(k for k, v in L["clips"].items() if v.get("status") in ("publiser", "andre"))
_bak = dict(L["clips"][_nm])
L["clips"][_nm].update({"title": "WARDOGS - 9 kills, 9 vehicles destroyed #shorts", "score": 99,
                        "kills": 2, "vehicles": 2, "solo_kills": 0, "max_dist_m": 0})
C.write_clip_page(s, L, killclip, log=print, make_thumbs=False)
_h2 = open(page, encoding="utf-8").read()
_d3 = _json.loads(_h2.split("const CLIPS = ", 1)[1].split(";\n", 1)[0])
_row = next(r for r in _d3 if r["name"] == _nm)
assert _row["title"] == killclip.auto_title(0, 0, 2, 0, None, 0), _row
assert "2 vehicles destroyed" in _row["title"] and "kills" not in _row["title"], _row
assert _row["kills"] == 0 and _row["veh"] == 2, _row
assert _row["score"] != 99, _row
print("tittel i browseren regnes ut av tellingene:", _row["title"], "| poeng", _row["score"])
L["clips"][_nm] = _bak
C.write_clip_page(s, L, killclip, log=print, make_thumbs=False)

# killclip skal kunne importeres paa en maskin UTEN ffmpeg. Foer sto det sys.exit() rett i _find, paa
# modulnivaa, saa alt som importerte modulen doede - ogsaa preflight(), som er laget for aa si fra om
# nettopp dette, og tools/queue_preview.py, som bare regner paa tall. ffmpeg ligger inne i exe-en.
assert hasattr(killclip, "require_tools"), "require_tools mangler"
_fm, _fp = killclip.FFMPEG, killclip.FFPROBE
killclip.FFMPEG = None
try:
    killclip.require_tools(); raise SystemExit("require_tools skulle kastet uten ffmpeg")
except RuntimeError as e:
    assert "ffmpeg" in str(e), e
killclip.FFMPEG = _fm
# og de rene funksjonene maa virke uten binaerfiler i det hele tatt
assert killclip.worth_posting([0, 1.5])[0] and killclip.banner_starts([(1.0, ["KILLCONFIRMED"])], lambda x: True) == [1.0]
print("import uten ffmpeg: modulen lever, require_tools sier fra naar noe skal kjoere")

# ---------------------------------------------------------------- fasit fra mennesket
# Hele terskeldiskusjonen var gjetning fordi ingen hadde verifisert hva som skjer i klippene.
# Browseren lar deg rette tellingen med +/- og bekrefte den med "correct", og forskjellen mellom
# "ikke sett paa" og "sett, og riktig" er poenget - uten den kan treffsikkerhet ikke maales.
_tn = next(iter(L["clips"]))
_tc = L["clips"][_tn]
assert C.set_truth(L, "finnes-ikke.mp4", kills=1) is False, "ukjent klipp skal avvises"
assert C.set_truth(L, _tn, confirm=True) and _tc["truth"]["confirmed"] is True
assert _tc["truth"]["kills"] == (_tc.get("solo_kills") if _tc.get("solo_kills") is not None else _tc.get("kills", 0)), \
    "confirm skal lagre det detektoren sa, ikke ingenting"
assert C.set_truth(L, _tn, kills=7) and _tc["truth"]["kills"] == 7
assert _tc["truth"]["confirmed"] is False, "en retting er ikke lenger en bekreftelse"
assert _tc["truth"]["vehicles"] == (_tc.get("vehicles") or 0), "kjoeretoey skal staa igjen uroert"
assert C.set_truth(L, _tn, vehicles=2) and _tc["truth"] == dict(_tc["truth"], kills=7, vehicles=2)
assert C.set_truth(L, _tn, kills=-3) and _tc["truth"]["kills"] == 0, "aldri negativt"
assert C.set_truth(L, _tn) and "truth" not in _tc, "undo skal ta klippet tilbake til ikke sett paa"
print("fasit: confirm, retting, gulv paa null og undo")

# ... og hver av dem maa staa PAA DISK med en gang, ikke bare i minnet. Den foerste versjonen
# glemte save_ledger, saa en time med gjennomsett klipping forsvant uten en lyd naar appen ble
# avsluttet. Testen leser hovedboka tilbake fra fil i stedet for aa tro paa objektet i minnet.
def _on_disk(name):
    return (C.jload(C.LEDGER, {}).get("clips", {}).get(name) or {}).get("truth")
C.save_ledger(L)
C.set_truth(L, _tn, confirm=True)
assert _on_disk(_tn) and _on_disk(_tn)["confirmed"] is True, "confirm ble ikke skrevet til disk"
C.set_truth(L, _tn, kills=9)
assert (_on_disk(_tn) or {}).get("kills") == 9, "rettingen ble ikke skrevet til disk"
C.set_truth(L, _tn)
assert _on_disk(_tn) is None, "undo ble ikke skrevet til disk"
print("fasit: alle tre handlingene staar paa disk med en gang")

# og sida maa faktisk ha knappene og ruta som lagrer dem
_pg = open(os.path.join(T, "out", "clips.html"), encoding="utf-8").read()
for _frag in ('class="row truth"', "function bump(", "function confirmTruth(", "function clearTruth(",
              '/truth', "correct"):
    assert _frag in _pg, f"mangler i clips.html: {_frag}"
assert '"truth":' in _pg or '"truth": null' in _pg or "truth" in _pg
print("fasit: browseren har tellerne og ruta som lagrer dem")

# ---------------------------------------------------------------- fasit overstyrer ALT
# Du har sett klippet, detektoren har ikke. Da skal ditt tall bestemme tittel, poeng og ko -
# ogsaa naar det gjoer klippet daarligere. Foer gjorde rettingen ingenting med klippet, og det
# var umulig aa se at den hadde noen virkning i det hele tatt.
_s2 = C.load_settings(); _s2["output_dir"] = os.path.join(T, "out")
_s2["shorts"] = dict(_s2["shorts"], publish={"double_s": 3, "pace_s": 5, "pace_need": 3,
                                             "vehicle_qualifies": False})
def _mkclip(name, status, ev, kills, veh=0):
    d = os.path.join(T, "out", "Publish" if status == "publiser" else "Other")
    os.makedirs(d, exist_ok=True)
    pth = os.path.join(d, name)
    open(pth, "w").write("x"); open(os.path.splitext(pth)[0] + ".txt", "w").write("gammel tittel\n\nfoo\n")
    L["clips"][name] = {"status": status, "abs_events": ev, "kills": kills, "solo_kills": kills,
                        "vehicles": veh, "score": 1.0, "title": "gammel tittel", "len": 20.0,
                        "max_dist_m": 0, "path": pth, "at": "2026-10-18T10:00:00"}
    return L["clips"][name]

# a) detektoren fant to spredte kills -> Other. Du sier tre: kjede, altsaa Publish.
_u = _mkclip("under.mp4", "andre", [1000.0, 1008.0], 2)
assert C.qualifies(_u, _s2["shorts"]) is False, "to spredte kills skal ikke til Publish av seg selv"
C.set_truth(L, "under.mp4", kills=3)
_r = C.apply_truth(_s2, L, "under.mp4", killclip, log=lambda m: None)
assert _u["status"] == "publiser", "fasit 3 kills skulle loeftet klippet til Publish"
assert _u["title"] == "WARDOGS \u2013 3 kills #shorts", f"tittelen foelger ikke fasit: {_u['title']}"
assert "Publish" in _r["did"] and "3 kills" in _r["title"]
assert os.path.exists(os.path.join(T, "out", "Publish", "under.mp4")), "fila ble ikke flyttet"
assert open(os.path.splitext(_u["path"])[0] + ".txt", encoding="utf-8").read().startswith(_u["title"]), \
    "txt-en ved klippet har fortsatt gammel tittel"

# b) detektoren saa en dobbel -> Publish. Du sier ett kill: da var dobbelen innbilt.
_o = _mkclip("over.mp4", "publiser", [2000.0, 2001.5], 2)
assert C.qualifies(_o, _s2["shorts"]) is True, "to kills innen 3 s er en dobbel"
C.set_truth(L, "over.mp4", kills=1)
_r2 = C.apply_truth(_s2, L, "over.mp4", killclip, log=lambda m: None)
assert _o["status"] == "andre", "ett kill skal ikke staa i Publish fordi OCR-en saa to"
assert _o["title"] == "WARDOGS \u2013 1 kill #shorts"
assert "Other" in _r2["did"]
assert os.path.exists(os.path.join(T, "out", "Other", "over.mp4"))

# c) angrer du, faller alt tilbake til detektorens eget tall
C.set_truth(L, "over.mp4")
_r3 = C.apply_truth(_s2, L, "over.mp4", killclip, log=lambda m: None)
assert _o["status"] == "publiser", "undo skal gi detektorens svar tilbake"
assert _o["title"] == "WARDOGS \u2013 2 kills #shorts"

# d) og browseren viser begge tallene, saa forskjellen er synlig
C.write_clip_page(_s2, L, killclip, log=lambda m: None, make_thumbs=False)
_pg2 = open(os.path.join(T, "out", "clips.html"), encoding="utf-8").read()
assert '"det_kills"' in _pg2, "kortet maa vite hva detektoren selv kom til"
assert "the detector said" in _pg2 and "lastDid" in _pg2
assert '"title": "WARDOGS \u2013 3 kills #shorts"' in _pg2 or "3 kills" in _pg2
print("fasit overstyrer: tittel, poeng, ko og fil - begge veier, og undo tilbake")
# e) svaret tilbake til sida maa ha tallene FLATT, og sida maa flytte tallet paa egen haand.
# Feilen dette fanger: apply_truth-ordboka ble pakket inn under "did", saa out.kills og out.title
# var undefined paa sida. Hvert trykk ble lagret, men tallet paa kortet sto bom stille - sytten
# trykk, sytten lagringer, ingen bevegelse. Ingenting i koden saa galt ut.
for _k in ("did", "title", "score", "kills", "veh", "where"):
    assert _k in _r, f"apply_truth mangler {_k} - sida leser dette feltet direkte"
_app = open(os.path.join(T, "..", "app", "killfeed_app.py"), encoding="utf-8").read()
assert 'out.update(did if isinstance(did, dict)' in _app, \
    "/truth maa legge apply_truth-feltene flatt i svaret, ikke under en nokkel"
_pg3 = open(os.path.join(T, "out", "clips.html"), encoding="utf-8").read()
assert "c.kills = c.truth.kills" in _pg3, \
    "sida maa oppdatere tallet fra sitt eget trykk, ikke stole paa at svaret har feltet"
print("fasit: svaret er flatt og telleren flytter seg uten hjelp fra svaret")
assert "if (b.dataset.w !== where) touched.clear();" in _pg3, \
    "bytter du visning skal 'Not checked' slutte aa vise klipp du nettopp svarte paa"

# rydd bort attrappene, ellers prover senere tester aa lage miniatyrbilde av en fil som ikke er video
for _n in ("under.mp4", "over.mp4"):
    _c = L["clips"].pop(_n, None)
    for _e in (".mp4", ".txt"):
        try: os.remove(os.path.splitext(_c["path"])[0] + _e)
        except (OSError, TypeError, KeyError): pass
C.save_ledger(L)

# ---------------------------------------------------------------- beloepet i banneret
# Ekte moenster fra WARDOGS 2026-09-28 17-11. Banneret staar oppe i aatte-ni sekunder, og
# detect.reward (= _reward_runs) har ett innslag per banner - men innslaget ligger som regel ETT
# TIL TRE SEKUNDER inne i banneret, ikke paa foerste bilde. Av 531 rader i fire opptak laa 51 paa
# starten og 144 inne i et banner som alt var talt. Spoer man "kom det en ny sum siden forrige
# bilde?" telles derfor hvert banner to ganger, og 274 kills blir til 415.
_kc = ["KILLCONFIRMED"]
_banner = [(t / 2, _kc) for t in range(4451, 4466)]        # 2225.5-2232.5, ETT sammenhengende banner
assert killclip.banner_starts(_banner, lambda x: True) == [2225.5], "uten beloep: ett banner, ett kill"
# en beloepsrad inne i banneret er bannerets egen - den skal ikke gi et kill til
_one = killclip.banner_starts(_banner, lambda x: True, [2228.0])
assert _one == [2225.5], f"ett beloep = ett kill, ikke to: {_one}"
# TO beloepsrader i samme banner = to kills. Det er det eneste som avsloerer to kills under
# sekundet, for banneret blir aldri moerkt mellom dem.
_two = killclip.banner_starts(_banner, lambda x: True, [2226.0, 2229.5])
assert _two == [2225.5, 2229.5], f"to beloep i ett banner er to kills: {_two}"
assert len(killclip.banner_starts(_banner, lambda x: True, [2226.0, 2228.0, 2231.0])) == 3
# et beloep som hoerer til et annet banner skal ikke telle her
assert killclip.banner_starts(_banner, lambda x: True, [2260.0]) == [2225.5]
# to bannere med pause imellom er to kills, ogsaa uten beloep
_gap2 = _banner + [(t / 2, _kc) for t in range(4480, 4490)]
assert len(killclip.banner_starts(_gap2, lambda x: True)) == 2
print("beloep i banner: ett innslag er bannerets eget, to er et dobbelkill")

# og tersklene skal ligge i settings, ikke i koden
_sh = C.DEFAULTS["shorts"]
assert "publish" in _sh and set(_sh["publish"]) == {"double_s", "pace_s", "pace_need", "vehicle_qualifies"}
_T = 1790000000
_q = lambda ev, veh=0, sh=_sh: C.qualifies({"abs_events": ev, "kills": len(ev), "vehicles": veh}, sh)
assert _q([_T, _T + 1.5]) and not _q([_T, _T + 30, _T + 60]) and not _q([_T])
assert _q([_T, _T, _T + 1.0]), "okkupert kjoeretoey og et kill ett sekund etter er en dobbel"
_veh_on = dict(_sh, publish=dict(_sh["publish"], vehicle_qualifies=True))
assert _q([_T], 1, _veh_on) and not _q([_T], 1), "kjoeretoey-billetten styres fra settings"
_slow = dict(_sh, publish=dict(_sh["publish"], double_s=8))
assert _q([_T, _T + 7], sh=_slow), "hevet double_s skal slippe gjennom mer"
print("terskler: shorts.publish styrer hva som slipper til Publish")

# ---------------------------------------------------------------- verdt aa poste
# "Vi boer egentlig bare poste bra. 1 kill hvert 5-sekund er ogsaa bra." Regelen er tetthet, ikke
# antall: min_kills telte bare hvor mange, og kunne derfor ikke skille et dobbelkill fra tre
# tilfeldige enkeltkills spredt over halvannet minutt.
# ett oeyeblikk = en hendelse. Et okkupert kjoeretoey fyrer kill og kjoeretoey samtidig, og uten
# dette leste tetthetsmaalet det som et dobbelkill - 28 av 28 "dobler" i seks oekter var dette.
assert killclip.collapse_pairs([10.0], [10.2]) == [10.2], "kill + kjoeretoey samtidig er EN hendelse"
assert killclip.collapse_pairs([10.0], [18.0]) == [10.0, 18.0], "atte sekunder unna er to hendelser"
assert killclip.collapse_pairs([10.0, 11.5], [11.6]) == [10.0, 11.6], "dobbel der det andre er et kjoeretoey"
assert killclip.collapse_pairs([], [5.0]) == [5.0] and killclip.collapse_pairs([5.0], []) == [5.0]
assert not killclip.worth_posting(killclip.collapse_pairs([10.0], [10.2]))[0], \
    "et okkupert kjoeretoey alene er ikke verdt aa poste"
print("hendelsespar: okkupert kjoeretoey teller som en hendelse, ikke to")

_ok = lambda ev: killclip.worth_posting(ev)[0]
assert _ok([0, 1.5]), "ekte dobbelkill skal publiseres"
assert _ok([0, 2, 4]), "tre kills paa fire sekunder"
assert _ok([0, 5, 10]), "ett kill hvert femte sekund"
assert _ok([0, 5, 10, 15, 20]), "en lang rekke i samme tempo"
assert _ok([0, 1, 30]), "dobbelen alene baerer klippet"
assert not _ok([0]), "ensomt kill"
assert not _ok([0, 7]), "to kills sju sekunder fra hverandre er ikke en dobbel"
assert not _ok([0, 30, 60]), "tre spredte enkeltkills skal IKKE publiseres"
assert not _ok([2711.0, 2730.5, 2750.0, 2765.0, 2780.0]), \
    "den ekte sekvensen fra 09-27: fem kills over 70 s, ingen to tett nok - skal ikke publiseres"
_o, _t, _w = killclip.worth_posting([0, 1.5, 3.0])
assert _o and _t == 3 and _w == "double", (_o, _t, _w)
assert killclip.worth_posting([0, 5, 10])[2] == "pace"
# grunnen skal vaere tom naar den ikke passerer, og tetteste skal fortsatt rapporteres til poengscoren
_o2, _t2, _w2 = killclip.worth_posting([0, 30, 60])
assert _o2 is False and _w2 == "" and _t2 >= 1, (_o2, _t2, _w2)
print("verdt aa poste: dobbel og tempo passerer, spredte enkeltkills gjoer det ikke")

# ---------------------------------------------------------------- bannerhalen
# Ekte tidsstempler fra WARDOGS 2026-09-27 21-00-31, klippet som ble lastet opp som "3 kills" og
# viste ett. Banneret under siktet staar paa i aatte-ni sekunder, saa et vindu som aapner midt i et
# banner saa halen av et kill som skjedde foer klippet begynte - og telte den som sitt eget kill.
# Killfeeden til venstre viste de to andre offrene, saa sporet var inne i bildet, bare ikke handlingen.
_kc = ["KILLCONFIRMED"]
_real = (  [(t/2, _kc) for t in range(5530, 5548)]      # 2765.0-2773.5: banner for killet paa 2765
         + [(t/2, _kc) for t in range(5560, 5569)])     # 2780.0-2784.0: banner for killet paa 2780
_starts = killclip.banner_starts(_real, lambda x: x.startswith("KILLCONFIRMED"))
assert _starts == [2765.0, 2780.0], f"to banner, to kill: {_starts}"
_a, _b = 2772.0, 2787.0                                  # vinduet som faktisk ble klippet
_inside = [t for t in _starts if _a <= t <= _b]
assert _inside == [2780.0], f"bare killet paa 2780 skjer inne i klippet: {_inside}"
# den gamle tellingen - bannerbilder i vinduet, nytt kill etter 3 s stille - ga 2
_old = 0; _last = -99
for _t, _ in [(t, k) for t, k in _real if _a <= t <= _b]:
    if _t - _last > 3: _old += 1
    _last = _t
assert _old == 2, f"gammel telling ga {_old}, testen er meningsloes hvis den ikke gjenskaper feilen"
print(f"bannerhale: gammel telling {_old} kill, ny telling {len(_inside)} - og klippet viser {len(_inside)}")
# et ekte dobbelkill inne i vinduet skal fortsatt telle som to
_two = [(t/2, _kc) for t in range(5560, 5569)] + [(t/2, _kc) for t in range(5580, 5589)]
_s2 = killclip.banner_starts(_two, lambda x: x.startswith("KILLCONFIRMED"))
assert len([t for t in _s2 if 2780.0 <= t <= 2800.0]) == 2, _s2
# to kill paa under sekundet: banneret blir ikke moerkt, saa beloepet maa skille dem.
# EN beloepsrad inne i et banner er bannerets egen avlesning - detect.reward har ett innslag per
# banner, og det ligger typisk et par sekunder inne i det. Det er den ANDRE raden som avsloerer at
# to kills delte samme banner.
_dense = [(t/2, _kc) for t in range(5560, 5578)]
assert killclip.banner_starts(_dense, lambda x: x.startswith("KILLCONFIRMED")) == [2780.0]
assert killclip.banner_starts(_dense, lambda x: x.startswith("KILLCONFIRMED"), rruns=[2784.0]) == [2780.0], \
    "en beloepsrad er bannerets egen, ikke et kill til"
assert killclip.banner_starts(_dense, lambda x: x.startswith("KILLCONFIRMED"), rruns=[2780.5, 2784.0]) == [2780.0, 2784.0], \
    "to beloepssummer i samme banner er to kills"
print("bannerhale: ekte dobbelkill og to-paa-sekundet teller fortsatt riktig")

# OCR-arbeidere: standarden maa vaere halvparten av kjernene, aldri alle. Alle var det som tok
# ~40 fps fra spillet. Og aldri under 2, uansett hva som staar i innstillingene.
_w0 = killclip.WORKERS
import os as _os
_n = _os.cpu_count() or 4
killclip.WORKERS = 0
assert killclip.workers() == max(2, _n // 2), f"standard skal vaere halvparten av {_n}, ble {killclip.workers()}"
assert killclip.workers() <= max(2, _n), "aldri mer enn maskinen har"
killclip.WORKERS = 8; assert killclip.workers() == 8
killclip.WORKERS = 1; assert killclip.workers() == 2, "minst 2, ellers staar skanningen nesten stille"
killclip.WORKERS = _w0
# hwaccel maa vaere av som standard, og -hwaccel maa ligge foer -i naar den er paa (det er et
# inngangsvalg - bak -i blir det lydloest ignorert, akkurat som -ss/-t-feilen i 0.3)
assert killclip.HWACCEL == "", "GPU-dekoding skal vaere av til den er testet"
print(f"ocr-arbeidere: standard {killclip.workers()} av {_n} logiske cpu-er, gulv paa 2")

# flere programnavn i game_process_hint. Paa Linux svarer game_running alltid False, saa her
# testes parsingen av lista gjennom should_hold_for_game, som er den som faktisk avgjoer.
assert C.game_running("") is False and C.game_running(None) is False
assert C.game_running("  ,  ") is False, "bare komma og mellomrom skal ikke telle som et spill"

# Ukjent er ikke "lukket": en tasklist som henger under last skal aldri se ut som at spillet ble
# avsluttet, for da vaakner appen midt i en runde.
import unittest.mock as _um
with _um.patch.object(C.os, "name", "nt"), \
     _um.patch.object(C.subprocess, "run", side_effect=subprocess.TimeoutExpired("tasklist", 10)):
    assert C.game_running("wardogs") is None, "feil fra tasklist skal gi None (ukjent), ikke False"
print("spillvakt: ukjent svar fra tasklist regnes ikke som at spillet er lukket")

# Vekking: tilbake i oppgavelinja MINIMERT. deiconify kan aktivere vinduet og ta fokus fra spillet.
_appsrc = open(os.path.join(T, "..", "app", "killfeed_app.py"), encoding="utf-8").read()
_wake = _appsrc[_appsrc.index("def _wake_after_game"):_appsrc.index("def _watch_loop")]
assert "self.iconify()" in _wake and "self.deiconify()" not in _wake, "vekking maa ikke aktivere vinduet"
assert "gone >= 2" in _appsrc, "vekking skal kreve to nei paa rad"
print("spillvakt: vekker minimert, og bare etter to nei paa rad")

# Nattjobben: aldri et vindu som tar fokus, aldri under spill, og tom ko er ikke en feil.
# En MessageBox herfra tabbet ut et spill 08.11.2026 og kostet en runde.
import tempfile as _tf, types as _ty, importlib.util as _iu
_rd = open(os.path.join(T, "..", "pipeline", "run_daily.py"), encoding="utf-8").read()
assert "MessageBox]::Show" not in _rd and "System.Windows.Forms" not in _rd, \
    "run_daily skal ikke kunne vise en MessageBox"
assert 'problems.append("The queue is empty' not in _rd, "tom ko er en status, ikke et problem"
_d = _tf.mkdtemp(); open(os.path.join(_d, "config.json"), "w").write('{"varsling": "msgbox"}')
shutil.copy(os.path.join(T, "..", "pipeline", "run_daily.py"), _d)
_sp = _iu.spec_from_file_location("run_daily_t", os.path.join(_d, "run_daily.py")); RD = _iu.module_from_spec(_sp); _sp.loader.exec_module(RD)
RD.log = lambda m: None
_shown = []
_fake = _ty.ModuleType("winotify")
class _N:
    def __init__(self, **k): self.k = k
    def show(self): _shown.append(self.k["title"])
_fake.Notification = _N
class _G:
    state = True
    @classmethod
    def game_running(cls, h): return cls.state
with _um.patch.dict(sys.modules, {"winotify": _fake}), _um.patch.object(RD.subprocess, "Popen", side_effect=AssertionError("ingen PowerShell her")):
    _G.state = True;  RD.notify(["yt_upload exit 1"], {"game_process_hint": "wardogs"}, _G); assert _shown == [], "vist under spill"
    _G.state = None;  RD.notify(["yt_upload exit 1"], {"game_process_hint": "wardogs"}, _G); assert _shown == [], "vist da spillet kanskje kjoerte"
    _G.state = False; RD.notify([], {"game_process_hint": "wardogs"}, _G); assert _shown == [], "vist uten problemer"
    _G.state = False; RD.notify(["yt_upload exit 1"], {"game_process_hint": "wardogs"}, _G); assert _shown == ["KillFeed nightly job"]
print("nattjobb: aldri MessageBox, aldri under spill, bare toast ved ekte feil")

# spillet skal vinne ogsaa midt i en kjoering. Dette er feilen som hakket spillet og laaste innputs:
# pause-innstillingen satt bare i vaktloekka, saa en kjoering som alt var i gang klippet videre.
_son = {"pause_while_game_running": True}
_soff = {"pause_while_game_running": False}
assert C.should_hold_for_game(_son, busy=True, game_on=True) is True, "en kjoering i gang maa stoppe naar spillet starter"
assert C.should_hold_for_game(_son, busy=False, game_on=True) is False, "ingenting aa stoppe"
assert C.should_hold_for_game(_son, busy=True, game_on=False) is False, "ingen spill, klipp i fred"
assert C.should_hold_for_game(_son, busy=True, game_on=True, already_held=True) is False, "skal bare stoppe en gang"
assert C.should_hold_for_game(_soff, busy=True, game_on=True) is False, "av er av"
assert C.should_hold_for_game({}, busy=True, game_on=True) is True, "paa som standard"
print("spillvakt: en kjoering i gang stoppes naar spillet starter, og bare en gang")

# CPU-valg: "16-31" skal bli en maske, soel skal ikke velte noe, og tom streng skal bety alle
# kjerner (maske 0) - ikke "ingen kjerner", som ville stoppet all klipping.
assert killclip.parse_cores("16-31", 32) == sum(1 << i for i in range(16, 32))
assert killclip.parse_cores("8,9,10,11", 32) == 0xF00
assert killclip.parse_cores("", 32) == 0 and killclip.parse_cores(None, 32) == 0
assert killclip.parse_cores("  ", 32) == 0, "bare mellomrom maa bety alle kjerner"
assert killclip.parse_cores("bogus", 32) == 0 and killclip.parse_cores("3-", 32) == 0
assert killclip.parse_cores("30-40", 32) == 0xC0000000, "kjerner utenfor maskinen skal klippes bort"
assert killclip.parse_cores("4", 32) == 0x10
assert killclip.set_affinity(0) in (True, False), "set_affinity maa aldri kaste"
print("cpu-valg: masker regnet riktig, soel og utenfor-rekkevidde haandtert")

# en stoppet kjoering maa aldri se ut som en ferdig kjoering. Dette er feilen som gjorde at en
# pauset app svarte "Done: 0 ready to publish" paa Run now - rett etter en Reset som hadde slettet
# alt. Kjoeres her mens opptakene fortsatt ligger der, med en tom hovedbok, og hovedboka paa disk
# skrives tilbake etterpaa siden run_once lagrer den.
_L2 = {"processed": {}, "clips": {}, "montages": [], "sizes": {}}
_rs = C.run_once(s, _L2, killclip, log=lambda *a: None, stop=lambda: True)
C.save_ledger(L)
assert _rs["sources"] > 0, "testen er meningsloes uten opptak aa stoppe foran"
assert _rs["stopped"] is True, _rs
assert _rs["done"] == 0, _rs
assert not _rs["publiser"] and not _rs["andre"], _rs
print(f"stoppet kjoering: {_rs['done']} av {_rs['sources']} gjort, stopped=True - ikke rapportert som ferdig")

# andre runde: ingenting nytt, ingen ny montasje (alt er brukt)
r2 = C.run_once(s, L, killclip, log=print)
assert r2["sources"] == 0 and r2["montage"] is None
# --- recap-banken: bitene skal ligge som egne smaa filer, og recapen skal kunne bygges
# etter at selve opptaket er slettet. Det er dette som gjor det trygt aa frigjore disk.
bankd = os.path.join(T, "out", "RecapBank")
assert os.path.isdir(bankd), "RecapBank ble ikke laget"
bfiles = sorted(x for x in os.listdir(bankd) if x.endswith(".mp4"))
assert bfiles, "ingen recap-biter havnet i banken"
import glob as _glob
_reps = [_json.load(open(x, encoding="utf-8")) for x in _glob.glob(os.path.join(C.REPORTS, "*-auto.json"))]
assert any(r.get("bank") for r in _reps), "rapporten fikk ingen bank-liste"
_mb = sum(os.path.getsize(os.path.join(bankd, x)) for x in bfiles) / 2**20
print(f"recap bank: {len(bfiles)} biter, {_mb:.1f} MB")

# slett opptakene og bygg recap paa nytt: banken alene skal holde
for _f in os.listdir(os.path.join(T, "rec")):
    os.remove(os.path.join(T, "rec", _f))
L["montages"] = []
_m2 = C.build_montage(s, L, killclip, force=True, log=print)
assert _m2 and os.path.exists(_m2), "recapen kunne ikke bygges etter at opptakene var slettet"
_d2 = killclip.probe(_m2)
assert _d2[1] == 1920 and _d2[2] == 1080, f"recap fra banken ble {_d2[1]}x{_d2[2]}"
print(f"recap uten opptak: {os.path.basename(_m2)}, {_d2[0]:.0f}s {_d2[1]}x{_d2[2]}")

# og sletting av opptak skal ikke lenger holdes tilbake naar alt er banket
s["cleanup"]["delete_source_after_clip"] = True
_n, _fr = C.delete_clipped_sources(s, L, killclip, log=print)
print(f"sletting: {_n} opptak (alt var allerede borte i denne testen)")

# --- sletting av opptak: de to sperrene som skiller "stille opptak" fra "OCR er odelagt" ---
# Et opptak der teksten ikke ble lest (hits=0) skal ALDRI slettes, selv om alt annet ser greit ut.
# Det er den ene feilen som ikke kan angres: en odelagt Tesseract leser hvert bilde som tomt, og det
# ser ut nøyaktig som en økt uten kills.
_fake = os.path.join(T, "rec", "slettetest.mkv")
open(_fake, "wb").write(b"not really a video")
s["cleanup"]["delete_source_after_clip"] = True
s["cleanup"]["keep_source_for_recap"] = False
L["processed"][C.src_key(_fake)] = {"file": "slettetest.mkv", "clips": 0, "hits": 0,
                                    "at": datetime.datetime.now().isoformat()}
C.delete_clipped_sources(s, L, killclip, log=lambda *a: None)
assert os.path.exists(_fake), "et opptak uten leste treff ble slettet - det er den farlige feilen"

# og med treff skal det slettes
L["processed"][C.src_key(_fake)]["hits"] = 12
C.delete_clipped_sources(s, L, killclip, log=lambda *a: None)
assert not os.path.exists(_fake), "et ferdig klippet opptak med treff skulle blitt slettet"

# en gammel oppforing pa filnavn alene gir ikke lov til a slette - den kan tilhore en annen fil
_fake2 = os.path.join(T, "rec", "slettetest2.mkv")
open(_fake2, "wb").write(b"not really a video")
L["processed"]["slettetest2.mkv"] = {"clips": 3, "hits": 9, "at": datetime.datetime.now().isoformat()}
C.delete_clipped_sources(s, L, killclip, log=lambda *a: None)
assert os.path.exists(_fake2), "en oppforing pa filnavn alene skal ikke kunne autorisere sletting"
os.remove(_fake2)
print("sletting: stille opptak beholdt, klippet opptak slettet, filnavn-oppforing avvist")

print("\nALT OK")
