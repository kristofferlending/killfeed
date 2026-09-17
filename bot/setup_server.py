"""Setter opp KillFeed-serveren: kanaler, emner og festede innlegg. Trygg aa kjore flere ganger
(lager bare det som mangler, oppdaterer emner og festede innlegg). Ren Discord REST, ingen boter online."""
import json, time, urllib.request, urllib.error
import kf_secrets

S = kf_secrets.load(); TOK, GID = S["DISCORD_BOT_TOKEN"], S["DISCORD_GUILD_ID"]
DISCORD_INVITE = "https://discord.gg/YSRt9t7gq"

def api(path, method="GET", body=None):
    req = urllib.request.Request("https://discord.com/api/v10" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bot " + TOK, "Content-Type": "application/json", "User-Agent": "KillFeedSetup/0.2"})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r) if r.status != 204 else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(json.loads(e.read()).get("retry_after", 1)) + 0.2); continue
            raise SystemExit(f"Discord-feil {e.code} paa {method} {path}: {e.read().decode()[:300]}")
    raise SystemExit("Ga opp etter rate limits")

TAG = "​"  # usynlig markor sa vi kjenner igjen vaare egne festede innlegg

# --------------------------------------------------------------------- innhold
CHANNELS = [
  ("announcements", "New KillFeed versions. One post per release.", [
    f"{TAG}**Welcome to KillFeed** – automatic WARDOGS shorts and daily recaps, all on your own PC.\n\n"
    "Download links and release notes are posted here. Read-only channel.\n"
    "Invite friends: " + DISCORD_INVITE]),
  ("setup-help", "Getting recordings into KillFeed: OBS, ShadowPlay, Medal, Aitum. Ask here.", [
    f"{TAG}**How to get recordings KillFeed can use**\n\n"
    "**OBS Studio (recommended, free)**\n"
    "• Settings → Output → Recording: pick a folder, MKV, NVENC/AMF, quality *High* or CQP 20\n"
    "• Settings → Output → Replay Buffer: on, 120 s. Hotkeys → *Save Replay*: F9. Press F9 after a good moment.\n"
    "• Whole session: Settings → General → *Automatically record when streaming*\n\n"
    "**NVIDIA App / ShadowPlay** – Alt+Z → Instant Replay on, 2 min. Alt+F10 saves. Folder: Videos.\n"
    "**Medal** – clips land in Videos\\Medal\\WARDOGS. Point KillFeed there.\n"
    "**Aitum Vertical** – ready-made 9:16 backtracks. Tick *I also record 9:16* in KillFeed.\n"
    "**Xbox Game Bar** – Win+Alt+G / Win+Alt+R. Folder: Videos\\Captures.\n\n"
    "**Common rules**: keep the HUD on (100 % scale), 1080p or 1440p at 60 fps. KillFeed waits until the game "
    "is closed and the file is 2 minutes old before it clips. Nothing is uploaded anywhere."]),
  ("feedback", "Drop the zip from *Send feedback* here, plus what went wrong. No video is ever included.", [
    f"{TAG}**How to report a problem**\n\n"
    "1. In KillFeed, press **Send feedback** – a zip lands on your desktop (log + text hits, never video).\n"
    "2. Drag the zip into this channel and write: resolution, recording tool, class (heli / infantry), "
    "and what you expected vs. what you got.\n"
    "3. If a clip missed the kill or cut wrong, the clip *filename* is enough – it contains the source and timestamps."]),
  ("showcase", "Shorts and recaps made with KillFeed. Post yours.", [
    f"{TAG}**Made with KillFeed?** Post the YouTube / TikTok link here. Best ones get pinned."]),
]

def main():
    me = api("/users/@me"); g = api(f"/guilds/{GID}")
    print(f"Bot: {me['username']}  Server: {g['name']}")
    existing = {c["name"]: c for c in api(f"/guilds/{GID}/channels") if c["type"] == 0}
    for name, topic, pins in CHANNELS:
        ch = existing.get(name)
        if not ch:
            ch = api(f"/guilds/{GID}/channels", "POST", {"name": name, "type": 0, "topic": topic}); print(f"  + #{name}")
        elif ch.get("topic") != topic:
            api(f"/channels/{ch['id']}", "PATCH", {"topic": topic}); print(f"  ~ #{name} (emne)")
        else:
            print(f"  = #{name}")
        # egne innlegg (festet eller ikke) med TAG, eldste forst - saa en ny kjoring ikke poster dobbelt
        hist = api(f"/channels/{ch['id']}/messages?limit=100")
        ours = sorted([m for m in hist if m.get("author", {}).get("id") == me["id"] and m.get("content", "").startswith(TAG)], key=lambda m: m["id"])
        for i, text in enumerate(pins):
            if i < len(ours):
                m = ours[i]
                if m["content"] != text: api(f"/channels/{ch['id']}/messages/{m['id']}", "PATCH", {"content": text}); print(f"    ~ innlegg oppdatert")
            else:
                m = api(f"/channels/{ch['id']}/messages", "POST", {"content": text}); print(f"    + innlegg")
            if not m.get("pinned"):
                try:
                    api(f"/channels/{ch['id']}/messages/pins/{m['id']}", "PUT"); print(f"    + festet")
                except RuntimeError as e:
                    print(f"    ! kunne ikke feste (gi boten 'Manage Messages' i Server Settings > Roles): {str(e)[:80]}")
    # announcements: bare admin/bot skal skrive
    ann = existing.get("announcements") or next(c for c in api(f"/guilds/{GID}/channels") if c["name"] == "announcements")
    try:
        api(f"/channels/{ann['id']}/permissions/{GID}", "PUT", {"type": 0, "deny": str(1 << 11)})   # SEND_MESSAGES for @everyone
    except RuntimeError as e:
        print("  ! kunne ikke laase #announcements (trenger 'Manage Roles'). Gjor det manuelt: kanal > Edit > Permissions > @everyone > Send Messages = X")
    print("Ferdig. Sjekk serveren.")

if __name__ == "__main__":
    main()
