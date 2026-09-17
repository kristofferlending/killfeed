#!/usr/bin/env python3
"""yt_upload.py – uploads KillFeed's finished clips to YouTube.

  Shorts:  <output>\\Publish\\*.mp4  -> uploaded as Shorts (9:16), best score first, max_per_run per night
  Recaps:  <output>\\Recaps\\*.mp4   -> uploaded as normal videos, max_recaps_per_run per night (default 1)
  <output> is KillFeed's output folder (settings.json, set by the tray app's wizard).
  Metadata (kills, vehicles, abs_events, title) comes from the ledger / report json; the recap title from its .txt.

With "privacy": "public" and "publish_times": ["17:00","21:00"] a clip is uploaded private with publishAt =
next free slot, so YouTube makes it public at the best time. Recaps use "recap_publish_time" (default 19:00).
Note: Google locks uploads from unverified API projects to private; the script prints what YouTube answered.

First time: python yt_upload.py --auth   (opens a browser, log in on the ThatsBonkers channel)
Then:       python yt_upload.py          (run by Task Scheduler via run_daily.py)
Requires: pip install google-api-python-client google-auth-oauthlib
OAuth client (Desktop app) saved as client_secret.json next to the script – NEVER share it.
"""
import os, sys, json, glob, time, argparse, datetime, re
import kf_bridge as B

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "config.json")
STATE = os.path.join(HERE, "state.json")
SECRET = os.path.join(HERE, "client_secret.json")
TOKEN = os.path.join(HERE, "token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly"]

def load(p, default):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default

def creds(interactive):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    c = None
    if os.path.exists(TOKEN):
        c = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if c and c.expired and c.refresh_token:
        c.refresh(Request()); open(TOKEN, "w").write(c.to_json())
    if not c or not c.valid:
        if not interactive:
            sys.exit("No valid token – run: python yt_upload.py --auth")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES)
        c = flow.run_local_server(port=0, prompt="consent")
        open(TOKEN, "w").write(c.to_json())
    return c

def meta_for(path, cfg, L):
    """Title/description/tags for a short: ledger + report json via kf_bridge, else a default title."""
    m = B.clip_meta(path, L)
    title = m.get("title")
    if not title:
        base = os.path.basename(path)
        d = re.search(r"(\d{4})-(\d{2})-(\d{2})", base)
        when = f"{d.group(3)}.{d.group(2)}" if d else ""
        kills, veh = m.get("kills", 0), m.get("vehicles", 0)
        bits = []
        if kills: bits.append(f"{kills} kill{'s' if kills>1 else ''}")
        if veh: bits.append(f"{veh} vehicle{'s' if veh>1 else ''} destroyed")
        title = cfg.get("title_prefix", "WARDOGS Little Bird") + (" – " + ", ".join(bits) if bits else "") + (f" ({when})" if when else "")
    title = re.sub(r"\s*\(\+\$[\d,]+\)", "", title).replace(" #shorts", "").strip()   # money = OCR noise, never in a title
    series = (cfg.get("series_tag") or "").strip()          # e.g. "Road to Havoc": a running hook across shorts and recaps
    if series and len(title) + len(series) + 12 <= 100: title = f"{title} | {series}"
    title = (title + " #shorts")[:100]
    desc = m.get("description") or cfg.get("description", "")
    if series: desc = f"{series} – " + desc
    tags = list(m.get("tags") or cfg.get("tags", [])) + ([series] if series else [])
    return title, desc, tags, m

def next_slots(times, n, start=None):
    """Neste n publiseringstidspunkter (lokal tid) fra lista times, f.eks. ["17:00","21:00"]. Hopper over tider som er < 1 t fram."""
    now = start or datetime.datetime.now().astimezone()
    out, day = [], 0
    while len(out) < n and day < 60:
        for t in sorted(times):
            hh, mm = map(int, t.split(":"))
            cand = (now + datetime.timedelta(days=day)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand > now + datetime.timedelta(hours=1):
                out.append(cand)
                if len(out) == n: break
        day += 1
    return out

def upload(yt, path, title, desc, tags, cfg, publish_at=None):
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    status = {"privacyStatus": cfg.get("privacy", "private"), "selfDeclaredMadeForKids": False}
    if publish_at is not None:
        # planlagt publisering: maa lastes opp privat + publishAt (UTC), YouTube gjor den offentlig selv
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": cfg.get("category_id", "20")},
        "status": status,
    }
    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, retry = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status: print(f"  {int(status.progress()*100)} %", flush=True)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < 5:
                retry += 1; time.sleep(2 ** retry); continue
            raise
    return resp["id"], resp.get("status", {})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", action="store_true", help="interactive login the first time")
    ap.add_argument("--dry", action="store_true", help="show what would be uploaded")
    ap.add_argument("--max", type=int, default=None, help="max shorts per run (overrides config)")
    A = ap.parse_args()
    cfg = load(CFG, {})
    if not cfg: sys.exit("Missing config.json")
    state = load(STATE, {"uploaded": {}})
    S = B.settings(); L = B.ledger()
    clips_dir = B.publish_dir(S); recaps_dir = B.recaps_dir(S)
    META = {}
    def meta(f):
        if f not in META: META[f] = B.clip_meta(f, L)
        return META[f]
    yt = None
    if A.auth or not A.dry:
        c = creds(A.auth)
        if A.auth: print("Login OK, token saved.")
    if not A.dry:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=c, cache_discovery=False)

    files = []
    for ext in ("*.mp4", "*.mkv", "*.mov"):
        files += glob.glob(os.path.join(clips_dir, ext))
    files = [f for f in files if os.path.basename(f) not in state["uploaded"]]
    min_age = cfg.get("min_age_seconds", 120)   # ikke ta filer som fortsatt skrives
    files = [f for f in files if time.time() - os.path.getmtime(f) > min_age]
    # score fra sidecar-json (killclip): kills*3 + vehicles*4 + $/1000. Beste først, under terskel blir liggende lokalt.
    def score_of(f):
        m = meta(f)
        return B.killclip.clip_score(m.get("kills", 0), m.get("vehicles", 0), m.get("max_dist_m", 0) or 0, m.get("len", 0) or 0)
    min_score = cfg.get("min_score", 0)
    min_kills = cfg.get("min_kills", 2)          # multikill ...
    min_vehicles = cfg.get("min_vehicles", 1)    # ... eller kjoretoy
    def ok(f):
        m = meta(f)
        if not m: return True                     # manual clip without metadata: let it through
        return score_of(f) >= min_score and (m.get("kills", 0) >= min_kills or m.get("vehicles", 0) >= min_vehicles)
    skipped = [f for f in files if not ok(f)]
    files = sorted((f for f in files if ok(f)), key=score_of, reverse=True)

    # ---- dedup: samme kill (klokketid) fra to backtracks/opptak -> behold beste, de andre merkes for alltid ----
    tol = cfg.get("dedup_seconds", 5)
    def abs_ev(f):
        return meta(f).get("abs_events", [])
    def same(ea, eb):
        return any(abs(x - y) <= tol for x in ea for y in eb)
    taken = [e["abs_events"] for e in state["uploaded"].values() if isinstance(e, dict) and e.get("abs_events")]
    # gamle opplastinger mangler abs_events - bruk kilde+tidsrom fra filnavnet ("<kilde>-autoNN-AAA.A-BBB.B") som fallback
    def fname_range(name):
        m = re.match(r"(.+)-auto\d+-(\d+\.\d)-(\d+\.\d)", os.path.splitext(name)[0])
        return (m.group(1), float(m.group(2)), float(m.group(3))) if m else None
    taken_rng = [r for r in (fname_range(k) for k in state["uploaded"]) if r]
    dups = state.setdefault("duplicate", {})
    files = [f for f in files if os.path.basename(f) not in dups]
    keep = []
    for f in files:                                  # files er sortert beste forst
        ev = abs_ev(f)
        r = fname_range(os.path.basename(f))
        if r and any(r[0] == t[0] and r[1] < t[2] and t[1] < r[2] for t in taken_rng):
            dups[os.path.basename(f)] = {"of": "already uploaded (same source/time range)", "at": datetime.datetime.now().isoformat()}
            continue
        if ev and any(same(ev, t) for t in taken):
            dups[os.path.basename(f)] = {"of": "already uploaded", "at": datetime.datetime.now().isoformat()}
            continue
        if ev and any(same(ev, abs_ev(k)) for k in keep):
            dups[os.path.basename(f)] = {"of": next(os.path.basename(k) for k in keep if same(ev, abs_ev(k))), "at": datetime.datetime.now().isoformat()}
            continue
        keep.append(f)
    if len(keep) != len(files):
        print(f"Dedup: {len(files)-len(keep)} clip(s) are the same kill as a better clip / already uploaded – skipped for good.")
    files = keep

    # ---- utlop: klipp som har ligget i ko lenger enn queue_max_age_days uten aa naa opp, pensjoneres (rydding sletter dem senere) ----
    max_age = cfg.get("queue_max_age_days", 21) * 86400
    expired = state.setdefault("expired", {})
    fresh = []
    for f in files:
        if time.time() - os.path.getmtime(f) > max_age:
            expired[os.path.basename(f)] = {"at": datetime.datetime.now().isoformat(), "score": score_of(f)}
        else:
            fresh.append(f)
    if len(fresh) != len(files):
        print(f"Expired: {len(files)-len(fresh)} clip(s) waited > {cfg.get('queue_max_age_days',21)} days and are retired.")
    files = fresh

    # ---- tom ko: slipp gjennom det beste enkeltkillet saa kanalen aldri staar stille ----
    if not files and skipped and cfg.get("fallback_single_when_empty", True):
        cand = [f for f in skipped if os.path.basename(f) not in dups and os.path.basename(f) not in expired]
        if cand:
            best = max(cand, key=score_of)
            print(f"Queue is empty – letting the best single kill through as fallback: {os.path.basename(best)}")
            files = [best]
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
    limit = A.max if A.max is not None else cfg.get("max_per_run", 10)
    # ---- laering: hent avspillinger for tidligere opplastinger og juster vehicle-vekten ----
    if yt is not None and cfg.get("analytics_tuning", True):
        try:
            up = {k: v for k, v in state["uploaded"].items() if isinstance(v, dict) and v.get("id")}
            ids = [v["id"] for v in up.values()][-50:]
            if len(ids) >= 6:
                r = yt.videos().list(part="statistics", id=",".join(ids)).execute()
                views = {it["id"]: int(it.get("statistics", {}).get("viewCount", 0)) for it in r.get("items", [])}
                for k, v in up.items():
                    m = B.clip_meta(os.path.join(clips_dir, k), L)
                    v["_veh"] = m.get("vehicles", 0) > 0
                    v["_views"] = views.get(v["id"], 0)
                a = [v["_views"] for v in up.values() if v.get("_veh")]
                b = [v["_views"] for v in up.values() if not v.get("_veh")]
                if len(a) >= 3 and len(b) >= 3 and sum(b):
                    ratio = (sum(a) / len(a)) / max(1, sum(b) / len(b))
                    w = max(2, min(6, round(3 * ratio)))
                    if w != state.get("veh_weight", 4):
                        print(f"Learning: vehicle clips get {ratio:.1f}x views on average -> vehicle weight {state.get('veh_weight',4)} -> {w}")
                    state["veh_weight"] = w
        except Exception as e:
            print(f"(analytics skipped: {str(e)[:120]})")
    vw = max(2, min(6, int(state.get("veh_weight", 3))))
    def rank(f):
        m = meta(f)
        r = m.get("kills",0)*2 + m.get("vehicles",0)*vw + (m.get("max_dist_m",0) or 0)//100 - max(0.0, (m.get("len",0) or 0) - 25) * 0.5
        if m.get("clamped_start"): r -= 3   # file started mid-action - the kill itself may be missing, rank down
        return r
    files = sorted(files, key=rank, reverse=True)

    privacy = cfg.get("privacy", "private")
    times = cfg.get("publish_times") or []
    # planlagte tider fortsetter etter siste planlagte video (state.last_publish_at), saa to netter aldri deler samme slot
    start = None
    if state.get("last_publish_at"):
        try: start = max(datetime.datetime.fromisoformat(state["last_publish_at"]), datetime.datetime.now().astimezone())
        except Exception: start = None
    slots = next_slots(times, limit, start) if (privacy == "public" and times) else []
    print(f"{len(files)} short(s) qualify (>= {min_kills} kills or >= {min_vehicles} vehicles, score >= {min_score}); {len(skipped)} single kills stay local. Uploading up to {limit}, best first.")
    print(f"Visibility: {privacy}" + (f", scheduled at {', '.join(times)}" if slots else ""))
    for i, f in enumerate(files[:limit]):
        title, desc, tags, _ = meta_for(f, cfg, L)
        when = slots[i] if i < len(slots) else None
        print(f"-> [rank {rank(f):.1f}] {os.path.basename(f)}\n   {title}" + (f"\n   goes public {when:%a %d.%m %H:%M}" if when else ""))
        if A.dry: continue
        try:
            vid, st = upload(yt, f, title, desc, tags, cfg, when)
        except Exception as e:
            print(f"   ERROR: {e}")
            state.setdefault("failed", {})[os.path.basename(f)] = {"at": datetime.datetime.now().isoformat(), "err": str(e)[:300]}
            json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
            if "quota" in str(e).lower(): print("Quota used up – trying again next run"); break
            continue
        got = st.get("privacyStatus", "?")
        state.get("failed", {}).pop(os.path.basename(f), None)
        state["uploaded"][os.path.basename(f)] = {"id": vid, "at": datetime.datetime.now().isoformat(), "title": title, "kind": "short",
                                                  "privacy": got, "publishAt": st.get("publishAt"), "abs_events": abs_ev(f)}
        json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
        print(f"   OK  https://youtube.com/shorts/{vid}  (YouTube answered: {got}" + (f", publishAt {st['publishAt']}" if st.get("publishAt") else "") + ")")
        if when is not None: state["last_publish_at"] = when.isoformat()
        if privacy == "public" and got != "public" and not st.get("publishAt"):
            print("   WARNING: asked for public, but YouTube set", got, "– unverified API projects are locked to private. Check Studio / apply for an API audit.")

    # ---- recaps: normal 16:9 videos, oldest first, max_recaps_per_run per night ----
    recaps = sorted((f for f in glob.glob(os.path.join(recaps_dir, "*.mp4"))
                     if os.path.basename(f) not in state["uploaded"] and time.time() - os.path.getmtime(f) > min_age), key=os.path.getmtime)
    rlimit = cfg.get("max_recaps_per_run", 1)
    if recaps:
        print(f"{len(recaps)} recap(s) waiting in Recaps. Uploading up to {rlimit} as normal video(s).")
    rtime = cfg.get("recap_publish_time", "19:00")
    for f in recaps[:rlimit]:
        title, body = B.recap_meta(f, L)
        series = (cfg.get("series_tag") or "").strip()
        if series:
            n = int(state.get("series_n", 0)) + 1
            title = f"{series} #{n} – {title}"
        desc = (cfg.get("recap_description") or cfg.get("description", "")).strip()
        if body: desc = desc + "\n\n" + body
        tags = [t for t in cfg.get("tags", []) if t.lower() != "shorts"] + ["recap"]
        when = next_slots([rtime], 1)[0] if (privacy == "public" and rtime) else None
        print(f"-> recap {os.path.basename(f)}\n   {title}" + (f"\n   goes public {when:%a %d.%m %H:%M}" if when else ""))
        if A.dry: continue
        try:
            vid, st = upload(yt, f, title[:100], desc, tags, cfg, when)
        except Exception as e:
            print(f"   ERROR: {e}")
            state.setdefault("failed", {})[os.path.basename(f)] = {"at": datetime.datetime.now().isoformat(), "err": str(e)[:300]}
            json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
            if "quota" in str(e).lower(): print("Quota used up – trying again next run"); break
            continue
        state.get("failed", {}).pop(os.path.basename(f), None)
        if series: state["series_n"] = int(state.get("series_n", 0)) + 1
        state["uploaded"][os.path.basename(f)] = {"id": vid, "at": datetime.datetime.now().isoformat(), "title": title, "kind": "recap",
                                                  "privacy": st.get("privacyStatus"), "publishAt": st.get("publishAt")}
        json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
        print(f"   OK  https://youtu.be/{vid}  (YouTube answered: {st.get('privacyStatus','?')})")

if __name__ == "__main__":
    main()
