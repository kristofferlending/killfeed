# KillFeed 0.5.1-alpha

One fix, and it matters if you ever leave OBS recording for a long time.

**Download:** `KillFeed.exe` below (about 175 MB — ffmpeg and Tesseract are bundled). Windows 10/11.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*. The SHA-256 of
the exe is at the bottom of these notes.

Walkthrough: **https://killfeed.no/guide**

---

## Fixed: in recordings over 13.9 hours, clips were cut from the wrong place

KillFeed reads a recording two frames a second and saves each frame as a numbered picture. The number
*is* the time: picture 7,200 is one hour in. The numbers had five digits, so picture 100,000 — 13.9
hours in — got a sixth, and the list was sorted as text, not as numbers. As text, `100000` comes
between `10000` and `10001`. From that point every picture was shuffled into the wrong place in the
timeline, and everything after the first 1.4 hours of the recording got the wrong time.

A kill read at 00:33 was stamped as happening hours later. KillFeed then cut the clip at that later
time — after the game was closed — so the clip showed an empty room and a black screen, titled with
kills it did not contain. Kills read at the real time were never cut at all.

It only happens when a single recording runs past 13.9 hours, which is easy to do by leaving OBS
recording after you stop playing. Three recordings of 15–20 hours were hit on our test machine; every
shorter recording was fine.

**What 0.5.1 does:**

- Pictures are numbered with eight digits and sorted as numbers. Recordings can now run for weeks.
- If the numbering ever has a gap or is out of order, KillFeed stops reading that recording instead of
  guessing. A recording that stops gives no clips and is never deleted; a shifted clip gets published.
- **On first start, clips that were cut from the wrong place are moved to `Other\_wrong-place\`** and
  taken out of the queue, and so are the recap-bank pieces cut the same way. Nothing is deleted — you
  can look at them and delete them yourself. The log says how many were moved.

If your recordings were deleted after clipping, the kills in the affected part of them cannot be cut
again. If you still have the recordings, right-click one of their clips on the Dashboard and choose *Re-clip the recording it came from*.

---

Feedback: press *Send feedback* in the app. It puts a zip on your desktop with the log, your settings,
the clip list and the text KillFeed read — never video. It contains file paths with your Windows user
name and the names of players in your recordings, so look at it before you post it publicly; you can
also send it to us privately on [Discord](https://discord.gg/YSRt9t7gq).
