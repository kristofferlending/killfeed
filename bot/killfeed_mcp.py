"""KillFeed Discord MCP-server. Kjorer lokalt paa mini, registrert i Claude-appen, saa Claude i Cowork kan lese og
skrive paa KillFeed-serveren via bot-tokenet (Discord REST, ingen gateway, ingen KI-kostnad).
Verktoy: list_channels, read_messages, post_message, edit_message, pin_message, read_attachment, analyse_feedback_zip.
Krever: pip install mcp   (3-installer-mcp.cmd gjor det og registrerer serveren i Claude-appen)
"""
import io, json, time, zipfile, urllib.request, urllib.error, collections, re
try:
    from mcp.server.fastmcp import FastMCP          # mcp 1.x
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP   # mcp 2.x (FastMCP ble MCPServer)
import kf_secrets

S = kf_secrets.load(); TOK, GID = S["DISCORD_BOT_TOKEN"], S["DISCORD_GUILD_ID"]
mcp = FastMCP("killfeed-discord")

def api(path, method="GET", body=None):
    req = urllib.request.Request("https://discord.com/api/v10" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bot " + TOK, "Content-Type": "application/json", "User-Agent": "KillFeedMCP/0.1"})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r) if r.status != 204 else {}
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(float(json.loads(e.read()).get("retry_after", 1)) + 0.2); continue
            raise RuntimeError(f"Discord {e.code} {method} {path}: {e.read().decode()[:300]}")
    raise RuntimeError("rate limited")

_chan_cache = {}
def chan_id(name_or_id: str) -> str:
    if name_or_id.isdigit(): return name_or_id
    if not _chan_cache:
        for c in api(f"/guilds/{GID}/channels"):
            if c["type"] == 0: _chan_cache[c["name"]] = c["id"]
    n = name_or_id.lstrip("#")
    if n not in _chan_cache: raise RuntimeError(f"Fant ikke kanal #{n}. Finnes: {', '.join(_chan_cache)}")
    return _chan_cache[n]

def fmt(m):
    a = m.get("author", {})
    att = [{"filename": x["filename"], "size": x["size"], "url": x["url"]} for x in m.get("attachments", [])]
    return {"id": m["id"], "at": m["timestamp"][:19], "author": a.get("global_name") or a.get("username"), "bot": a.get("bot", False),
            "content": m.get("content", ""), "attachments": att, "pinned": m.get("pinned", False)}

@mcp.tool()
def list_channels() -> list:
    """Tekstkanaler paa KillFeed-serveren med id og emne."""
    return [{"name": c["name"], "id": c["id"], "topic": c.get("topic")} for c in api(f"/guilds/{GID}/channels") if c["type"] == 0]

@mcp.tool()
def read_messages(channel: str, limit: int = 30, before_id: str = "") -> list:
    """Siste meldinger i en kanal (navn eller id), nyeste forst. before_id for aa bla bakover."""
    q = f"?limit={min(max(limit, 1), 100)}" + (f"&before={before_id}" if before_id else "")
    return [fmt(m) for m in api(f"/channels/{chan_id(channel)}/messages{q}")]

@mcp.tool()
def post_message(channel: str, text: str, reply_to_id: str = "") -> dict:
    """Skriv en melding som KillFeed Bot. reply_to_id svarer paa en bestemt melding."""
    body = {"content": text[:2000]}
    if reply_to_id: body["message_reference"] = {"message_id": reply_to_id}; body["allowed_mentions"] = {"parse": ["users"]}
    return fmt(api(f"/channels/{chan_id(channel)}/messages", "POST", body))

@mcp.tool()
def edit_message(channel: str, message_id: str, text: str) -> dict:
    """Rediger en melding boten selv har skrevet."""
    return fmt(api(f"/channels/{chan_id(channel)}/messages/{message_id}", "PATCH", {"content": text[:2000]}))

@mcp.tool()
def pin_message(channel: str, message_id: str) -> str:
    """Fest en melding i kanalen."""
    api(f"/channels/{chan_id(channel)}/pins/{message_id}", "PUT"); return "festet"

@mcp.tool()
def read_attachment(url: str, max_chars: int = 20000) -> str:
    """Les et tekstvedlegg (log/txt/json) fra en Discord-melding. Zip: bruk analyse_feedback_zip."""
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "KillFeedMCP/0.1"}), timeout=60) as r:
        return r.read().decode("utf-8", "replace")[:max_chars]

@mcp.tool()
def analyse_feedback_zip(url: str, include_log_tail: int = 60, include_reports: bool = True) -> dict:
    """Last ned en KillFeed feedback-zip fra Discord og returner logg-hale, innstillinger, hovedbok-tall og rapport-sammendrag."""
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "KillFeedMCP/0.1"}), timeout=120) as r:
        data = r.read()
    z = zipfile.ZipFile(io.BytesIO(data)); names = z.namelist(); out = {"files": names}
    for n in names:
        if n.endswith("killfeed.log"):
            lines = z.read(n).decode("utf-8", "replace").splitlines()
            out["log_tail"] = lines[-include_log_tail:]; out["log_problems"] = [l for l in lines if "PROBLEM" in l or "Hoppet over" in l or "FEIL" in l][-20:]
            v = re.findall(r"KillFeed (\S+) startet", "\n".join(lines)); out["version"] = v[-1] if v else None
        elif n.endswith("settings.json"):
            try: out["settings"] = json.loads(z.read(n).decode("utf-8", "replace"))
            except Exception: pass
        elif n.endswith("ledger.json"):
            try:
                L = json.loads(z.read(n).decode("utf-8", "replace"))
                st = collections.Counter(v.get("status") for v in L.get("clips", {}).values())
                out["ledger"] = {"processed": len(L.get("processed", {})), "errors": [k for k, v in L.get("processed", {}).items() if "error" in v][:10],
                                 "clips_by_status": dict(st), "montages": len(L.get("montages", []))}
            except Exception: pass
    reps = []
    for n in names:
        if n.startswith("reports/") and n.endswith("-auto.json"):
            try: r = json.loads(z.read(n).decode("utf-8", "replace"))
            except Exception: continue
            reps.append({"source": (r.get("input") or n).split("\\")[-1], "duration": r.get("duration"), "hits": len(r.get("hits", [])),
                         "feed": len(r.get("feed", [])), "segments": [{"len": s.get("len"), "kills": s.get("kills"), "vehicles": s.get("vehicles"),
                         "res": s.get("source_res"), "title": s.get("title")} for s in r.get("segments", [])]})
    out["reports_summary"] = {"count": len(reps), "no_hits": sum(1 for r in reps if r["hits"] == 0),
                              "resolutions": dict(collections.Counter(s["res"] for r in reps for s in r["segments"]))}
    if include_reports: out["reports"] = reps[:40]
    return out

if __name__ == "__main__":
    mcp.run()
