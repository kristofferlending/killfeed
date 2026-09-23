# KillFeed 0.3.1-alpha

A correctness release. Same features as 0.3, but the kill detection no longer trusts the wrong part
of the screen. If you are on 0.3, replace the exe and run *Advanced → Rescan everything → Start fresh*
so your clips are rebuilt with the stricter rules.

**Download:** `KillFeed.exe` below (about 130 MB – ffmpeg and Tesseract are bundled). Windows 10/11 only.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*.

## Fixed: clips with no kill in them

WARDOGS puts kill information in three places: the banner under your crosshair, the money HUD in the
top right, and the kill feed down the left side. Only the banner is about *you* – the other two show
what everyone on the server is doing, and both are outside the frame once a clip is cropped to 9:16.

Until now any text in any of the three counted as your kill. That produced shorts titled
*"1 kill (216 m), 1 vehicle destroyed"* where nothing at all happens on screen: the kill was real,
but it was someone else's, in a corner the viewer never sees.

From 0.3.1:

- Only the banner under the crosshair can create a kill or a vehicle kill.
- The money HUD contributes the amount, the kill feed contributes distance and victim. Neither can
  create an event on its own.
- A distance is only attached when the banner fired within 2.5 s of that feed row – otherwise the
  row belongs to another player.
- An event has to be read in at least two frames within 1.5 seconds, so a single misread frame is
  no longer enough.
- The loose patterns are gone: a bare "KILL", "DESTROYED" or "DELIVERED" no longer means a kill.

The test suite now includes a recording where the only text sits in the kill feed and the money HUD.
It must produce no clips at all.

## Known in this alpha

- WARDOGS only, Windows only, English only. Clips carry a small "KillFeed alpha" mark.
- Tuned on 1080p/1440p with the HUD at 100 %. Other HUD scales may miss kills – tell us.
- Lead-in before the kill is 8 s by default (Advanced → Seconds before the kill). Infantry players:
  tell us if that is too short or too long.
- Weapon and class are not detected yet – only kills, vehicles, distance and victim.
- Settings and log live in `%APPDATA%\KillFeed`. Delete that folder to run the setup again.

Feedback: press *Send feedback* in the app – it puts a zip (log + text hits, never video) on your
desktop. Drop it in **#feedback** on [Discord](https://discord.gg/YSRt9t7gq).
