# KillFeed – roadmap

The goal: you double-click once, and from then on finished shorts and recaps appear in a folder
without you touching anything. Updated 2026-09-30.

## Done (0.3-alpha)

- [x] Core (`kf_core.py`), tray app, setup wizard, Publish/Other, daily recap, dedup of the same kill across recordings
- [x] English GUI, DPI-aware, proper icon, tray icon shows state
- [x] Dashboard: Run / Stop after this file / Stop now, Pause, "Make recap now", clip list with search, Why, Re-clip
- [x] Rescan that stops immediately and offers Start fresh / Re-clip keep / Retry failed
- [x] Log rotation, cleanup of `work\` at start, feedback zip (log + text hits, never video)
- [x] Check for updates against GitHub Releases
- [x] Shorts tuned to what actually gets watched: 15–30 s, 8 s before / 3 s after the kill, long kill runs split at the widest pause
- [x] Website killfeed.no, Discord server, GitHub Releases as the download place

## Done (0.4-alpha)

- [x] Only the banner under the crosshair can create a kill – no more clips of someone else's kill
- [x] Two kills in a row counted as two, told apart by the reward printed in the banner
- [x] Lone kills with nothing near them are not cut at all – three quarters of the clipping work
- [x] Kills have to be a burst to reach Publish, and changing the rule re-sorts what you already have
- [x] Clip browser: hover to play, mark clips up or down, and the marks decide what gets uploaded
- [x] Split framing (whole picture on top, zoomed centre below) for when there is no vertical recording
- [x] RecapBank – recap pieces kept as small files, so recordings can be deleted without losing recaps
- [x] Delete recordings once clipped, with guards against deleting when the text reading is broken
- [x] Reset and start over, and a walkthrough at killfeed.no/guide

## Closed alpha (now)

- [ ] Feedback from 1080p / 1440p / ultrawide and from infantry players: does the lead-in fit, are kills missed
- [ ] Error messages that say what to do – never a traceback
- [ ] First-run check: ffmpeg/Tesseract present, write access, free disk > 5 GB
- [ ] Sync-folder safety (OneDrive/iCloud): write to temp, then move in
- [ ] Recap: is 5 s before / 2 s after right for infantry? Chronological without music – fine or boring?

## Open beta

- [ ] Code signing (no more SmartScreen warning)
- [ ] Pro version: no watermark, 1440p output, your own logo. License key in the app, no account
- [ ] Auto-update from the tray

## Later

- [ ] Weapon / class detection from the kill-feed icon → search for heli, weapon etc. in the clip list
- [ ] Beat-synced recap to license-free music (Pro)
- [ ] More games – same engine, new zones
- [ ] Upload from the app (needs Google verification – only when people ask for it)

## What the channel data says (analysed 2026-09-17)

Viewers watch 17–23 s regardless of clip length. Shorts ≤25 s: median 788 views / 82 % watched.
46 s and longer: median 60 views / 48 %. Kill count barely matters; a vehicle kill is a small plus.
That is why shorts are 15–30 s, long kill sequences are split at the biggest pause, the score penalises
seconds over 25, and money is kept out of titles.
