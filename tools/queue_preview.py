"""Bygg Publiser-koen paa nytt fra rapportene, uten aa lese en eneste ramme video.

Hvorfor dette finnes: en ekte omskanning tar timer og krever opptakene. Men naar bare TELLINGEN og
Publiser-regelen endres - ikke klippevinduene - ligger alt som trengs i rapportene: `hits` er hvert
bilde der det sto tekst i banneret, og `reward` er beloepssummene som skiller to raske kills fra ett.
Da kan koen regnes om paa sekunder, og terskler kan proeves ut foer noe klippes.

    python tools/queue_preview.py <rapportmappe> [--settings fil] [--double 3] [--pace 5]
                                 [--need 3] [--vehicle-ticket] [--json ut.json] [--verbose]

Kjoerer hvor som helst - paa PC-en med den virkelige rapportmappa, eller et annet sted paa en kopi.
Skriver ingenting annet enn --json-fila: den roerer ikke hovedboka, klippene eller opptakene.

Med --apply gjoer den noe mer: da skriver den den nye tellingen inn i hovedboka for klippene du
ALLEREDE har, og flytter filene mellom Publish\ og Other\ etter den gjeldende regelen. Klippene
klippes ikke paa nytt - vinduene staar som de er, bare tallene, titlene, poengene og plasseringen
rettes. Det tar sekunder i stedet for en omskanning paa timer. KillFeed maa vaere avsluttet mens
den kjoerer: appen holder hovedboka i minnet og skriver den over igjen naar den lagrer.

    python tools/queue_preview.py %APPDATA%\KillFeed\reports --apply
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import killclip as K

DEF = {"pre": 8, "post": 3, "gap": 12, "min": 15, "max": 30}

def load_settings(path):
    sh = dict(DEF)
    if path and os.path.exists(path):
        try: sh.update(json.load(open(path, encoding="utf-8")).get("shorts", {}))
        except Exception as e: print(f"kunne ikke lese {path}: {e}", file=sys.stderr)
    return sh

# ----------------------------------------------------------------- fasit-rapport
def print_truth(L):
    """Treffsikkerhet maalt mot det du har sagt faktisk skjedde i klippene."""
    clips = L.get("clips") or {}
    seen = [(n, c) for n, c in clips.items() if c.get("truth")]
    print(f"\n--- fasit ---\n{len(seen)} av {len(clips)} klipp er sett paa")
    if not seen:
        print("  Ingenting aa maale mot enda. Aapne Browse clips og bruk +/- og \u2713 correct.")
        return
    rk = rv = rb = 0; over = []; under = []
    for n, c in seen:
        t = c["truth"]
        dk = int(c.get("solo_kills") if c.get("solo_kills") is not None else (c.get("kills") or 0))
        dv = int(c.get("vehicles") or 0)
        ok_k, ok_v = dk == t.get("kills"), dv == t.get("vehicles")
        rk += ok_k; rv += ok_v; rb += ok_k and ok_v
        if not (ok_k and ok_v):
            (over if (dk + dv) > (t.get("kills", 0) + t.get("vehicles", 0)) else under).append(
                (n, f"{dk}k/{dv}kjt", f"{t.get('kills')}k/{t.get('vehicles')}kjt"))
    n = len(seen)
    print(f"  kills riktig      {rk:4} av {n}  ({rk/n*100:.0f} %)")
    print(f"  kjoeretoey riktig {rv:4} av {n}  ({rv/n*100:.0f} %)")
    print(f"  begge riktig      {rb:4} av {n}  ({rb/n*100:.0f} %)")
    for lab, bad in (("teller FOR MYE", over), ("teller FOR LITE", under)):
        if bad:
            print(f"\n  {lab} ({len(bad)}):")
            for nm, d, t in bad[:10]: print(f"     {nm[:54]:56} sa {d:9} var {t}")
            if len(bad) > 10: print(f"     ... og {len(bad)-10} til")

# ----------------------------------------------------------------- --apply
# Klippnavnet BAERER vinduet: <opptak>-autoNN-<start>-<slutt>.mp4. Derfor kan tellingen gjoeres om
# over akkurat det vinduet klippet ble skaaret fra, uten aa klynge paa nytt - en ny klynging kunne
# gitt andre vinduer enn mp4-ene som alt ligger paa disk, og da ville tallene beskrevet noe annet
# enn det man ser i klippet.
CLIPNAME = re.compile(r"^(?P<base>.+)-auto(?P<i>\d+)-(?P<a>\d+(?:\.\d+)?)-(?P<b>\d+(?:\.\d+)?)\.mp4$", re.I)

def _report_index(reports_dir):
    out = {}
    for f in glob.glob(os.path.join(reports_dir, "*-auto.json")):
        nm = os.path.basename(f)
        out[nm[:-len("-auto.json")].lower()] = f
    return out

def _recount(path, cache={}):
    """(kill_starts, veh_starts, t0, har_reward) for en rapport - regnet en gang per rapport."""
    if path in cache: return cache[path]
    try: r = json.load(open(path, encoding="utf-8"))
    except Exception: cache[path] = None; return None
    hits = [(float(t), k) for t, k in (r.get("hits") or [])]
    rr = [float(t) for t, _ in (r.get("reward") or [])]
    ks = K.banner_starts(hits, lambda x: x.startswith("KILLCONFIRMED"), rr)
    vs = K.banner_starts(hits, lambda x: "DESTROYED" in x, rr)
    t0 = None
    try: t0 = K.file_start_epoch(r.get("input") or path, float(r.get("duration") or 0))
    except Exception: t0 = None     # opptaket er slettet og navnet mangler dato - se nedenfor
    cache[path] = (ks, vs, t0, bool(rr))
    return cache[path]

def _killfeed_running():
    if os.name != "nt": return False
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        return "killfeed.exe" in (r.stdout or "").lower()
    except Exception:
        return False

def apply_counts(A):
    """Skriv den nye tellingen inn i hovedboka for klippene som alt finnes, og sorter om."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    import kf_core as C
    if A.ledger: C.LEDGER = os.path.abspath(A.ledger)
    if _killfeed_running() and not A.force:
        print("KillFeed kjoerer. Avslutt appen foerst (Exit i systemkurven) - den holder hovedboka i",
              "\nminnet og skriver den over igjen naar den lagrer, saa rettingen ville forsvunnet.",
              "\n(--force kjoerer likevel, hvis du vet at appen ikke kommer til aa lagre.)", file=sys.stderr)
        return 3
    s = C.load_settings()
    L = C.load_ledger()
    clips = L.get("clips") or {}
    if not clips:
        print(f"ingen klipp i {C.LEDGER}", file=sys.stderr); return 2

    if not A.dry:
        bak = C.LEDGER + f".backup-{datetime.datetime.now():%Y%m%d-%H%M%S}"
        try: shutil.copy2(C.LEDGER, bak); print(f"sikkerhetskopi: {bak}")
        except Exception as e: print(f"ADVARSEL: fikk ikke laget sikkerhetskopi ({e})", file=sys.stderr)

    idx = _report_index(A.reports)
    changed = []; same = 0; norep = []; blind = 0
    for name, c in clips.items():
        if c.get("status") not in ("publiser", "andre"): continue
        m = CLIPNAME.match(name)
        rep = idx.get(m.group("base").lower()) if m else None
        got = _recount(rep) if rep else None
        if not got: norep.append(name); continue
        ks, vs, t0, has_rew = got
        if not has_rew: blind += 1
        a, b = float(m.group("a")), float(m.group("b"))
        kin = [t for t in ks if a <= t <= b]
        vin = [t for t in vs if a <= t <= b]
        paired = sum(1 for t in kin if any(abs(t - v) <= 1.5 for v in vin))
        solo = max(0, len(kin) - paired)
        rel = sorted(kin + vin)
        # abs_events er klokketid, og brukes til dedup mot andre klipp. Uten dato i opptaksnavnet
        # (og uten opptaket paa disk) kan ikke nullpunktet regnes ut - da legges de nye hendelsene
        # paa samme nullpunkt som de gamle, saa dedupen fortsatt stemmer.
        base0 = t0
        if base0 is None:
            old = sorted(c.get("abs_events") or [])
            base0 = (old[0] - rel[0]) if (old and rel) else 0.0
        ev = [round(base0 + t, 1) for t in rel]
        dist = c.get("max_dist_m", 0) or 0
        # Har du sagt hva som skjedde i klippet, er det DITT tall som skal staa i tittelen og
        # poengsummen. Den nye tellingen skrives likevel inn, saa fasit-rapporten fortsatt maaler
        # detektoren mot deg - ellers ville den maalt seg mot seg selv.
        t = c.get("truth") or {}
        tk = int(t.get("kills") or 0) if t else solo
        tv = int(t.get("vehicles") or 0) if t else len(vin)
        new = {"kills": len(kin), "solo_kills": solo, "vehicles": len(vin), "vehicle_kills": paired,
               "abs_events": ev,
               "title": K.auto_title(tk, 0, tv, 0, None, dist),
               "score": K.clip_score(tk, tv, dist, c.get("len", 0) or 0)}
        before = (c.get("solo_kills") if c.get("solo_kills") is not None else c.get("kills"),
                  c.get("vehicles"), c.get("score"))
        after = (solo, len(vin), new["score"])
        if before == after and c.get("title") == new["title"]: same += 1; continue
        c.update(new)
        changed.append((name, before, after))
        if not A.dry: _fix_sidecar(c.get("path"), new["title"])

    print(f"\n{len(changed)} klipp fikk nye tall, {same} var alt riktige"
          + (f", {len(norep)} mangler rapport" if norep else ""))
    if blind: print(f"ADVARSEL: {blind} av klippene kommer fra rapporter uten `reward` - raske dobbelkills"
                    "\n           kan ikke skilles der, saa de blir undervurdert.")
    for name, bf, af in changed[:25]:
        print(f"  {name[:56]:58} {bf[0]}k/{bf[1]}kjt -> {af[0]}k/{af[1]}kjt   poeng {bf[2]} -> {af[2]}")
    if len(changed) > 25: print(f"  ... og {len(changed)-25} til")
    if norep:
        print(f"\n  uten rapport (urort - rapporten er ryddet bort eller mappa er feil):")
        for n in norep[:8]: print(f"     {n}")
        if len(norep) > 8: print(f"     ... og {len(norep)-8} til")

    if A.dry:
        print("\n--dry: ingenting er skrevet."); print_truth(L); return 0

    C.save_ledger(L)
    pub, oth = C.resort_clips(s, L, log=lambda m: print("  " + m))
    now = sum(1 for c in clips.values() if c.get("status") == "publiser")
    print(f"skrev hovedboka. Flyttet {pub} til Publish og {oth} til Other - koen er naa {now} klipp.")
    print_truth(L)
    print("\nStart KillFeed igjen og aapne Browse clips: titlene og koen er oppdatert.")
    return 0

def _fix_sidecar(path, title):
    """Foerste linja i <klipp>.txt er tittelen. Resten (offer og avstander) staar som den er."""
    if not path: return
    t = os.path.splitext(path)[0] + ".txt"
    try:
        if not os.path.exists(t): return
        lines = open(t, encoding="utf-8").read().split("\n")
        if lines and lines[0].strip() == title.strip(): return
        lines[0] = title
        open(t, "w", encoding="utf-8").write("\n".join(lines))
    except Exception: pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("reports")
    p.add_argument("--settings")
    p.add_argument("--double", type=float, default=3.0, help="to hendelser innenfor saa mange sekunder = dobbelkill")
    p.add_argument("--pace", type=float, default=5.0, help="tempo: ett kill hvert N sekund")
    p.add_argument("--need", type=int, default=3, help="hvor mange hendelser tempoet maa holdes over")
    p.add_argument("--vehicle-ticket", action="store_true", help="la et enslig kjoeretoey-kill passere alene")
    p.add_argument("--ledger", help="hovedboka: rapporter treffsikkerhet mot fasiten du har lagt inn i browseren")
    p.add_argument("--apply", action="store_true",
                   help="skriv den nye tellingen inn i hovedboka og sorter om filene (KillFeed maa vaere avsluttet)")
    p.add_argument("--dry", action="store_true", help="med --apply: vis hva som ville endret seg, skriv ingenting")
    p.add_argument("--force", action="store_true", help="med --apply: kjoer selv om KillFeed kjoerer")
    p.add_argument("--json")
    p.add_argument("--verbose", action="store_true")
    A = p.parse_args()
    if A.apply: return apply_counts(A)
    sh = load_settings(A.settings)

    files = sorted(glob.glob(os.path.join(A.reports, "*-auto.json")))
    if not files:
        print(f"ingen *-auto.json i {A.reports}", file=sys.stderr); return 2

    rows = []; blind = []; skipped = 0
    for f in files:
        try: r = json.load(open(f, encoding="utf-8"))
        except Exception as e: print(f"  hopper over {os.path.basename(f)}: {e}", file=sys.stderr); continue
        if not r.get("hits") or not r.get("duration"): skipped += 1; continue
        hits = [(float(t), k) for t, k in r["hits"]]
        rew = [(float(t), a) for t, a in (r.get("reward") or [])]
        if not rew: blind.append(os.path.basename(f))
        # rapportens `reward` ER allerede _reward_runs() - ett innslag per banner. Kjoeres den
        # gjennom en gang til blir lista tom, og hvert dobbelkill forsvinner i stillhet.
        rr = [t for t, _ in rew]
        ks = K.banner_starts(hits, lambda x: x.startswith("KILLCONFIRMED"), rr)
        vs = K.banner_starts(hits, lambda x: "DESTROYED" in x, rr)
        dur = float(r["duration"])
        src = os.path.basename(r.get("input") or f)
        for a, b, kinds in K.cluster(hits, dur, sh["pre"], sh["post"], sh["gap"], sh["min"], sh["max"]):
            kin = [t for t in ks if a <= t <= b]
            vin = [t for t in vs if a <= t <= b]
            paired = sum(1 for t in kin if any(abs(t - v) <= 1.5 for v in vin))
            solo = max(0, len(kin) - paired)
            # ett oeyeblikk = en hendelse: et okkupert kjoeretoey er ikke et dobbelkill
            ev = K.collapse_pairs(kin, vin)
            ok, tight, why = K.worth_posting(ev, A.double, A.pace, A.need)
            if not ok and A.vehicle_ticket and vin: ok, why = True, "vehicle"
            rows.append({"src": src, "a": round(a, 1), "b": round(b, 1), "len": round(b - a, 1),
                         "kills": len(kin), "solo_kills": solo, "vehicles": len(vin),
                         "tight": tight, "publish": ok, "why": why,
                         "title": K.auto_title(solo, 0, len(vin), 0, None, 0),
                         "score": K.clip_score(solo, len(vin), 0, b - a)})

    pub = [r for r in rows if r["publish"]]
    pub.sort(key=lambda r: -r["score"])
    sessions = len({r["src"] for r in rows}) or 1

    if blind:
        print("!" * 72)
        print(f"ADVARSEL: {len(blind)} av {len(files)} rapporter mangler `reward`.")
        print("Uten beloepssummene kan to kills innenfor tre sekunder ikke skilles fra ett - de")
        print("leses som ett sammenhengende banner. Tallene under UNDERVURDERER derfor antallet")
        print("dobbelkills, og 'dobbel'-regelen kan nesten ikke slaa til. Klipp opptakene paa nytt")
        print("med et bygg som lagrer reward foer du setter terskler ut fra dette.")
        print("!" * 72); print()

    print(f"regel: dobbel innen {A.double:g}s, eller {A.need} hendelser innen {A.pace*(A.need-1):g}s"
          + ("  + kjoeretoey alene passerer" if A.vehicle_ticket else ""))
    print(f"{len(rows)} segmenter fra {sessions} opptak" + (f", {skipped} rapporter uten hits" if skipped else ""))
    print(f"til Publish: {len(pub)}  ({len(pub)/max(1,len(rows))*100:.1f} %)   {len(pub)/sessions:.1f} per opptak")
    for w in ("double", "pace", "vehicle"):
        n = sum(1 for r in pub if r["why"] == w)
        if n: print(f"   fordi {w:8} {n}")
    if pub:
        print(f"\ntoppen av koen:\n{'poeng':>6} {'tetteste':>9} {'grunn':>8}  tittel")
        for r in pub[:12]:
            print(f"{r['score']:6.1f} {r['tight']:9} {r['why']:>8}  {r['title'][:52]}")
    if A.verbose:
        print(f"\nalle segmenter:\n{'opptak':22}{'vindu':>18}{'k':>3}{'kjt':>4}{'tett':>5}  publish")
        for r in rows:
            print(f"{r['src'][:21]:22}{r['a']:8.1f}-{r['b']:7.1f}{r['kills']:3}{r['vehicles']:4}"
                  f"{r['tight']:5}  {'JA ' + r['why'] if r['publish'] else 'nei'}")
    if A.ledger:
        try: _L = json.load(open(A.ledger, encoding="utf-8"))
        except Exception as e:
            print(f"kunne ikke lese {A.ledger}: {e}", file=sys.stderr); _L = {"clips": {}}
        print_truth(_L)

    if A.json:
        json.dump({"rule": {"double_s": A.double, "pace_s": A.pace, "need": A.need,
                            "vehicle_ticket": A.vehicle_ticket},
                   "blind_reports": blind, "segments": rows}, open(A.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\nskrev {A.json}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
