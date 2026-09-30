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
assert any(v["status"] == "publiser" and v["vehicles"] >= 1 for v in L["clips"].values()), "vehicle skal i Publiser"
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
# innstillingen: strammer vi max_kill_span til 1 s, skal 2-kill-klippet flyttes ut av Publiser,
# og filene skal faktisk flytte seg - ikke bare hovedboka. Slakker vi den igjen, kommer det tilbake.
pub_before = sorted(x for x in os.listdir(os.path.join(T, "out", "Publish")) if x.endswith(".mp4"))
s["shorts"]["max_kill_span"] = 1
np_, na_ = C.resort_clips(s, L, log=print)
print("resort ->", np_, "til Publish,", na_, "til Other")
assert na_ >= 1, "det spredte 2-kill-klippet skulle blitt flyttet til Other"
pub_now = sorted(x for x in os.listdir(os.path.join(T, "out", "Publish")) if x.endswith(".mp4"))
assert len(pub_now) < len(pub_before), f"fila ligger fortsatt i Publish: {pub_now}"
moved = set(pub_before) - set(pub_now)
for m in moved:
    assert os.path.exists(os.path.join(T, "out", "Other", m)), f"{m} forsvant i stedet for å bli flyttet"
    assert os.path.exists(os.path.join(T, "out", "Other", os.path.splitext(m)[0] + ".txt")), "tittelfila ble ikke med"
s["shorts"]["max_kill_span"] = 10
np2, _ = C.resort_clips(s, L, log=print)
assert np2 >= 1, "klippet skulle kommet tilbake til Publish"
assert sorted(x for x in os.listdir(os.path.join(T, "out", "Publish")) if x.endswith(".mp4")) == pub_before

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
