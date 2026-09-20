# KillFeed 0.3-alpha

Automatic WARDOGS shorts and daily recaps – all on your own PC. No account, no upload, nothing leaves your machine.

**Download:** `KillFeed.exe` below (about 130 MB – ffmpeg and Tesseract are bundled). Windows 10/11 only.
Windows SmartScreen will warn because the alpha is not code-signed yet: *More info → Run anyway*.

## What it does

Point it at your recordings folder once. It then sits in the tray, and after every session (once the game is closed) it reads the kill feed from the video and makes:

- **Publish\\** – vertical 9:16 shorts (15–30 s) with a multikill or a vehicle kill, ready for YouTube Shorts / TikTok / Reels, with a title in a .txt next to each
- **Other\\** – single kills, kept in case you want them
- **Recaps\\** – a chronological 16:9 recap of the day's kills, built automatically when enough is collected

The same kill from two recordings (replay + backtrack) becomes one clip. Ready-made 9:16 recordings (Aitum Vertical) are used as-is; 16:9 recordings get a centre crop.

## Getting started

1. Run `KillFeed.exe`. The setup asks four things: where your recordings are, what to make, what is good enough to publish, and where the clips should go (a OneDrive / Google Drive / Dropbox folder syncs them to your phone).
2. Press *Start KillFeed*. Done – it starts with Windows from now on.
3. Play. Check the Dashboard or the output folder after a session.

Recording setup for OBS, ShadowPlay, Medal and Aitum: *Recording guide* in the app, or #setup-help on Discord.

## Feedback

Press *Send feedback* in the app – it puts a zip (log + text hits, never video) on your desktop. Drop it in **#feedback** on the Discord server together with your resolution, recording tool and class (heli / infantry). If a clip missed or cut wrong, the clip filename is enough.

## Known in this alpha

- WARDOGS only, Windows only, English only. Clips carry a small "KillFeed alpha" mark.
- Tuned on 1080p/1440p with the HUD at 100 %. Other HUD scales may miss kills – tell us.
- Lead-in before the kill is 8 s by default (Advanced → Seconds before the kill). Infantry players: tell us if that is too short or too long.
- Weapon and class are not detected yet – only kills, vehicles, distance and victim.
- Settings and log live in `%APPDATA%\KillFeed`. Delete that folder to run the setup again.
