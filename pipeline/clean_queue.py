#!/usr/bin/env python3
"""clean_queue.py – tidy state.json after deleting the private/scheduled videos in YouTube Studio.

  * removes uploads that were still private (not yet public) from state["uploaded"], so the same kills can
    come back in the new short format
  * keeps every public upload (the nightly job never re-uploads a kill that is already out)
  * clears the duplicate / expired / failed lists so every clip in Publish is judged afresh
  * resets the publishing queue so the next upload takes the next free slot from now
A backup state.json.bak-<time> is written first. Nothing is changed on YouTube.
"""
import os, json, datetime, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); STATE = os.path.join(HERE, "state.json")

def main():
    st = json.load(open(STATE, encoding="utf-8"))
    shutil.copy(STATE, STATE + f".bak-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    up = st.get("uploaded", {})
    # ask YouTube which of the uploads still exist and are public (read-only); deleted or still-private ones leave the ledger
    live = {}
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        c = Credentials.from_authorized_user_file(os.path.join(HERE, "token.json"))
        yt = build("youtube", "v3", credentials=c, cache_discovery=False)
        ids = [v["id"] for v in up.values() if isinstance(v, dict) and v.get("id")]
        for i in range(0, len(ids), 50):
            for it in yt.videos().list(part="status", id=",".join(ids[i:i + 50])).execute().get("items", []):
                live[it["id"]] = it["status"].get("privacyStatus")
        print(f"YouTube says: {sum(1 for v in live.values() if v == 'public')} public, {sum(1 for v in live.values() if v != 'public')} not public, {len(ids) - len(live)} deleted.")
        gone = [k for k, v in up.items() if isinstance(v, dict) and live.get(v.get("id")) != "public"]
    except Exception as e:
        print(f"(could not ask YouTube: {str(e)[:80]} – using the ledger's own privacy flag)")
        gone = [k for k, v in up.items() if isinstance(v, dict) and v.get("privacy") == "private"]
    for k in gone: up.pop(k)
    n_dup, n_exp, n_fail = len(st.get("duplicate", {})), len(st.get("expired", {})), len(st.get("failed", {}))
    st["duplicate"] = {}; st["expired"] = {}; st["failed"] = {}; st.pop("last_publish_at", None)
    json.dump(st, open(STATE, "w", encoding="utf-8"), indent=1)
    print(f"Removed {len(gone)} private/scheduled upload(s) from the ledger; {len(up)} public upload(s) kept.")
    print(f"Cleared {n_dup} duplicate, {n_exp} expired and {n_fail} failed entries. Publishing queue reset – next upload takes the next free slot.")
    for k in gone: print("  -", k)

if __name__ == "__main__":
    main()
