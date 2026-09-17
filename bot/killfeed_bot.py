"""KillFeed Discord-bot – uten KI, null kostnad. Kjorer paa mini.
- Onsker nye velkommen i #setup-help
- /setup, /faq, /download, /roadmap – faste svar
- Leser feedback-zip i #feedback: pakker opp, teller treff/feil fra logg og rapporter, svarer med tall og tagger eier
Krever: pip install discord.py   (2-start-bot.cmd gjor det)
"""
import io, os, re, json, zipfile, collections
import discord
from discord import app_commands
import kf_secrets

S = kf_secrets.load()
GID = int(S["DISCORD_GUILD_ID"]); OWNER = S.get("OWNER_USER_ID") or ""
DOWNLOAD_URL = "https://github.com/kristofferlending/killfeed/releases"
INVITE = "https://discord.gg/YSRt9t7gq"

intents = discord.Intents.default(); intents.members = True; intents.message_content = True
bot = discord.Client(intents=intents); tree = app_commands.CommandTree(bot)

FAQ = {
    "no clips": "KillFeed found no kill text. Check: HUD on and at 100 % scale, the recording is the actual game (not desktop), "
                "1080p/1440p, and that the file is at least 2 minutes old. Still nothing? Press *Send feedback* and drop the zip in #feedback.",
    "wrong cut": "Clips start 12 s before the kill text and end 4 s after (18–40 s). If the kill happened before the file started "
                 "(replay buffer too short), the clip is marked *clamped* and ranked lower. Make the replay buffer 120 s+.",
    "9:16": "Aitum Vertical or any 9:16 recording is used as-is. 16:9 recordings get a center crop. If you have both, "
            "tick *I also record 9:16* in KillFeed and the vertical version wins.",
    "recap": "Recaps are 16:9, chronological, 5–10 min, built automatically when enough kills are collected from 16:9 recordings. "
             "Press *Make recap now* to force one.",
    "privacy": "Nothing leaves your PC. KillFeed has no account, no upload. The feedback zip contains log + text hits only, never video.",
    "cpu": "KillFeed waits until the game is closed before it clips, so it never competes with WARDOGS for CPU.",
}

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GID))
    print(f"Online som {bot.user}")

@bot.event
async def on_member_join(member):
    ch = discord.utils.get(member.guild.text_channels, name="setup-help")
    if ch:
        await ch.send(f"Welcome {member.mention}! Download KillFeed here: {DOWNLOAD_URL}. "
                      f"Recording setup is pinned above – ask here if anything is unclear.")

def _guild(): return discord.Object(id=GID)

@tree.command(name="download", description="Latest KillFeed download", guild=_guild())
async def cmd_download(i: discord.Interaction):
    await i.response.send_message(f"Latest KillFeed: {DOWNLOAD_URL}\nWindows only. SmartScreen: *More info → Run anyway* (alpha is unsigned).")

@tree.command(name="setup", description="How to get recordings KillFeed can use", guild=_guild())
async def cmd_setup(i: discord.Interaction):
    await i.response.send_message("Recording setup (OBS / ShadowPlay / Medal / Aitum) is pinned in #setup-help. Short version: "
                                  "OBS Replay Buffer 120 s on F9, HUD on, 1080p+ – then point KillFeed at your Videos folder.")

@tree.command(name="faq", description="Common questions", guild=_guild())
@app_commands.describe(topic="no clips | wrong cut | 9:16 | recap | privacy | cpu")
async def cmd_faq(i: discord.Interaction, topic: str = ""):
    t = topic.lower().strip()
    if t in FAQ: await i.response.send_message(f"**{t}** – {FAQ[t]}"); return
    await i.response.send_message("Topics: " + ", ".join(f"`{k}`" for k in FAQ) + "\n" + "\n".join(f"**{k}** – {v}" for k, v in FAQ.items()))

@tree.command(name="roadmap", description="What is coming", guild=_guild())
async def cmd_roadmap(i: discord.Interaction):
    await i.response.send_message("Next: signed installer (no SmartScreen), English UI, auto-update, weapon in titles, beat-synced recaps (Pro). "
                                  "Full list lives in the repo's docs/ROADMAP.md.")

# ---------------------------------------------------------------- feedback-zip
def analyse_zip(data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist(); out = []
    log = ""
    for n in names:
        if n.endswith("killfeed.log"): log = z.read(n).decode("utf-8", "replace")
    settings = {}
    for n in names:
        if n.endswith("settings.json"):
            try: settings = json.loads(z.read(n).decode("utf-8", "replace"))
            except Exception: pass
    reports = [n for n in names if n.startswith("reports/") and n.endswith("-auto.json")]
    tot_src = len(reports); no_hits = 0; res = collections.Counter(); kills = 0; veh = 0; feed = 0; clips = 0
    for n in reports:
        try: r = json.loads(z.read(n).decode("utf-8", "replace"))
        except Exception: continue
        if not r.get("hits"): no_hits += 1
        for sgm in r.get("segments", []):
            clips += 1; kills += sgm.get("kills", 0); veh += sgm.get("vehicles", 0); res[sgm.get("source_res", "?")] += 1
        feed += len(r.get("feed", []))
    problems = [l for l in log.splitlines() if "PROBLEM" in l or "Hoppet over" in l or "FEIL" in l][-5:]
    ver = re.findall(r"KillFeed (\S+) startet", log); ver = ver[-1] if ver else "?"
    out.append(f"**KillFeed {ver}** · {tot_src} recordings analysed · {clips} clips · {kills} kills · {veh} vehicles · {feed} kill-feed reads")
    if tot_src: out.append(f"Recordings with **no kill text at all**: {no_hits}/{tot_src}" + (" ← HUD/zone problem likely" if no_hits > tot_src / 2 else ""))
    if res: out.append("Resolutions: " + ", ".join(f"{k} ({v})" for k, v in res.most_common(3)))
    if settings:
        m = settings.get("montage", {}); sh = settings.get("shorts", {})
        out.append(f"Settings: shorts {'on' if settings.get('make_shorts', True) else 'off'}, recap {'on' if m.get('enabled') else 'off'} "
                   f"({m.get('min_minutes')}–{m.get('max_minutes')} min), rule kills≥{sh.get('min_kills')} or vehicles≥{sh.get('min_vehicles')}, "
                   f"9:16 folder {'set' if settings.get('vertical_dir') else 'not set'}")
    if problems: out.append("Last problems in log:\n" + "\n".join("• " + p[:160] for p in problems))
    return "\n".join(out)

@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot or not msg.guild or msg.channel.name != "feedback": return
    for a in msg.attachments:
        if a.filename.lower().endswith(".zip") and a.size < 25 * 1024 * 1024:
            try:
                data = await a.read(); summary = analyse_zip(data)
            except Exception as e:
                summary = f"Could not read the zip: {e}"
            mention = f"<@{OWNER}> " if OWNER else ""
            await msg.reply(f"{mention}Thanks {msg.author.mention} – quick read of `{a.filename}`:\n{summary}", mention_author=False)

if __name__ == "__main__":
    bot.run(S["DISCORD_BOT_TOKEN"])
