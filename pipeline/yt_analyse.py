#!/usr/bin/env python3
"""yt_analyse.py – pull every upload on the channel with its statistics and write analysis.json + analysis.txt
next to this script. Read-only (uses the same token as yt_upload.py). Then post analysis.txt in #feedback
or let Claude read analysis.json from the schedules folder.

Per video: id, title, published, duration, views, likes, comments, privacy, and – when the nightly job made it –
what we know from state.json (kills, vehicles, distance, clamped start) and the clip json in KillFeed\\clips
(old) or reports (new). Also tries the YouTube Analytics API (impressions, CTR, average view %) – that needs the
Analytics API enabled + scope; if it is not there, those columns stay empty.
"""
import os, sys, json, glob, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.path.join(HERE, "token.json"); STATE = os.path.join(HERE, "state.json")
OUT_JSON = os.path.join(HERE, "analysis.json"); OUT_TXT = os.path.join(HERE, "analysis.txt")

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def iso_dur(s):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m: return 0
    h, mi, se = (int(x) if x else 0 for x in m.groups()); return h * 3600 + mi * 60 + se

def main():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly"]
    c = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if c.expired and c.refresh_token: c.refresh(Request()); open(TOKEN, "w").write(c.to_json())
    yt = build("youtube", "v3", credentials=c, cache_discovery=False)
    ch = yt.channels().list(part="contentDetails,statistics,snippet", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Channel: {ch['snippet']['title']}  subscribers={ch['statistics'].get('subscriberCount')}  views={ch['statistics'].get('viewCount')}  videos={ch['statistics'].get('videoCount')}")
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=tok).execute()
        ids += [it["contentDetails"]["videoId"] for it in r["items"]]
        tok = r.get("nextPageToken")
        if not tok: break
    vids = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,statistics,contentDetails,status", id=",".join(ids[i:i + 50])).execute()
        vids += r["items"]
    # what the nightly job knows about each upload
    state = load(STATE, {}); by_id = {}
    for name, v in state.get("uploaded", {}).items():
        if isinstance(v, dict) and v.get("id"): by_id[v["id"]] = dict(v, file=name)
    metas = {}
    for p in glob.glob(os.path.join(HERE, "..", "clips", "*.json")) + glob.glob(os.path.join(os.environ.get("APPDATA", ""), "KillFeed", "reports", "*.json")):
        metas[os.path.splitext(os.path.basename(p))[0]] = load(p, {})
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for v in vids:
        sn, st, cd, ss = v["snippet"], v.get("statistics", {}), v.get("contentDetails", {}), v.get("status", {})
        pub = datetime.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        days = max(0.1, (now - pub).total_seconds() / 86400)
        info = by_id.get(v["id"], {}); m = metas.get(os.path.splitext(info.get("file", ""))[0], {})
        dur = iso_dur(cd.get("duration"))
        rows.append({"id": v["id"], "title": sn["title"], "published": pub.isoformat(), "days": round(days, 1), "weekday": pub.strftime("%a"),
                     "hour_utc": pub.hour, "duration_s": dur, "short": dur <= 60, "privacy": ss.get("privacyStatus"),
                     "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                     "views_per_day": round(int(st.get("viewCount", 0)) / days, 2), "auto": bool(info), "file": info.get("file"),
                     "kills": m.get("kills"), "vehicles": m.get("vehicles"), "money": m.get("money"), "max_dist_m": m.get("max_dist_m"),
                     "clamped_start": m.get("clamped_start"), "source_res": m.get("source_res"), "source": m.get("source"),
                     "tags": sn.get("tags", []), "desc_len": len(sn.get("description", ""))})
    # optional: YouTube Analytics (impressions / CTR / avg view %) – best effort
    try:
        ya = build("youtubeAnalytics", "v2", credentials=c, cache_discovery=False)
        start = (now - datetime.timedelta(days=365)).strftime("%Y-%m-%d"); end = now.strftime("%Y-%m-%d")
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="video",
                               metrics="views,averageViewPercentage,averageViewDuration,likes,shares,subscribersGained", maxResults=200, sort="-views").execute()
        cols = [h["name"] for h in r.get("columnHeaders", [])]
        amap = {row[0]: dict(zip(cols[1:], row[1:])) for row in r.get("rows", [])}
        for x in rows:
            a = amap.get(x["id"])
            if a: x.update({"avg_view_pct": a.get("averageViewPercentage"), "avg_view_s": a.get("averageViewDuration"), "shares": a.get("shares"), "subs_gained": a.get("subscribersGained")})
        print("Analytics API: ok")
    except Exception as e:
        print(f"Analytics API not available ({str(e)[:100]}) – views/likes only.")
    json.dump({"channel": {"title": ch["snippet"]["title"], "subs": ch["statistics"].get("subscriberCount"), "views": ch["statistics"].get("viewCount"), "videos": len(rows)},
               "generated": now.isoformat(), "videos": rows}, open(OUT_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    rows.sort(key=lambda x: -x["views"])
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(f"{ch['snippet']['title']} – {len(rows)} videos, {ch['statistics'].get('viewCount')} views total, {ch['statistics'].get('subscriberCount')} subs\n\n")
        f.write(f"{'views':>6} {'v/day':>6} {'likes':>5} {'len':>4} {'k':>2} {'veh':>3} {'dist':>5} {'day':>3} {'published':10}  title\n")
        for x in rows:
            f.write(f"{x['views']:6d} {x['views_per_day']:6.1f} {x['likes']:5d} {x['duration_s']:4d} {str(x['kills'] or ''):>2} {str(x['vehicles'] or ''):>3} {str(x['max_dist_m'] or ''):>5} {x['weekday']:>3} {x['published'][:10]}  {x['title'][:70]}\n")
    print(f"Wrote {OUT_JSON} and {OUT_TXT} ({len(rows)} videos).")

if __name__ == "__main__":
    main()
