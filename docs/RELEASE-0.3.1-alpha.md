# KillFeed 0.3.1-alpha

A correctness release. Same features as 0.3, but the kill detection no longer trusts the wrong part of
the screen, the packaged build no longer writes enormous files, and a long short with two lonely kills
in it no longer lands in Publish. Two kills in a row are also counted as two.

If you are on 0.3: replace the exe, then run *Advanced → Maintenance → Rescan everything → Start fresh*
so your clips are rebuilt with the stricter rules.

**Download:** `KillFeed.exe` below (about 175 MB – ffmpeg and Tesseract are bundled). Windows 10/11 only.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*.

## Fixed: clips with no kill in them

WARDOGS puts kill information in three places: the banner under your crosshair, the money HUD in the top
right, and the kill feed down the left side. Only the banner is about *you* – the other two show what
everyone on the server is doing, and both are outside the frame once a clip is cropped to 9:16.

Until now any text in any of the three counted as your kill. That produced shorts titled *"1 kill (216 m),
1 vehicle destroyed"* where nothing at all happens on screen: the kill was real, but it was someone else's,
in a corner the viewer never sees.

- Only the banner under the crosshair can create a kill or a vehicle kill.
- The money HUD contributes the amount, the kill feed contributes distance and victim. Neither can create
  an event on its own.
- A distance is only attached when the banner fired within 2.5 s of that feed row.
- An event has to be read in at least two frames within 1.5 seconds, so a single misread frame is not enough.
- A bare "KILL", "DESTROYED" or "DELIVERED" no longer means a kill.

## Fixed: 15-second clips that were 1.4 GB

`-ss` and `-t` sat between the recording and the watermark in the ffmpeg command, so the duration was read
as an option for the watermark instead of the cut. Only the packaged build has a watermark, which is why
this never showed up when running from source: the exe wrote everything from the cut point to the end of
the recording. Two 15-second clips came out at 1.4 GB each.

## New: kills have to be a burst

Two kills twenty seconds apart used to be chained into one 30-second short where nothing happens in
between – the kind nobody finishes. Kills now only count towards Publish when they land within
**Advanced → Shorts → Kills must be within N s of each other** (10 s by default). A vehicle kill still
carries a clip on its own, and anything that does not make the cut goes to `Other\` as before.

Changing that setting also re-sorts the clips you already have, moving them between `Publish\` and
`Other\` so a stricter value cleans up the queue instead of only applying to the next thing clipped.

## Fixed: a clip labelled "1 kill" that had two in it

Two kills in a row overlap on screen. The second banner replaces the first with no dark frame between
them, so the gap between the two reads is a quarter of a second – and the counter only started a new kill
after three seconds of quiet. Both kills were found; they were just counted once.

The banner prints its own reward, and that is what tells them apart:

    8.50-12.75 s   KILL CONFIRMED  +$2,250  300XP
    13.00-17.25 s  KILL CONFIRMED  +$1,500  250XP

The amount is read from the banner itself, not the money HUD, so it survives the 9:16 crop and works the
same on an Aitum vertical recording. A new amount has to hold for two frames before it counts, so a single
misread digit cannot invent a kill. Two kills with the same reward back to back are still counted as one –
rare, and better than inventing kills that did not happen.

## New: a third way to fit 16:9 into 9:16

**Advanced → How 16:9 recordings become 9:16 → Split.** The whole picture across the top, so the HUD, the
kill feed and the banner stay readable, and a centre crop about 1.8x below, so the action is big. For when
there is no vertical recording of the moment. The two old choices are unchanged.

## New: delete the recording once it has been clipped

**Advanced → Disk space.** Off by default. A recording is tens of gigabytes and the clips it produces are
tens of megabytes, so this is most of your disk. It cannot be undone – the file is deleted, not moved to
the Recycle Bin – so there are two guards: a recording that failed to clip is always kept, and, while
*keep it until its kills have been used in a recap* is on, a recording the recap still needs is kept too.
That second one matters because the recap is cut from the recording itself, not from the finished shorts.

## Known in this alpha

- WARDOGS only, Windows only, English only. Clips carry a small "KillFeed alpha" mark.
- Tuned on 1080p/1440p with the HUD at 100 %. Other HUD scales may miss kills – tell us.
- Lead-in before the kill is 8 s by default (Advanced → Seconds before the kill). Infantry players: tell us
  if that is too short or too long.
- Weapon and class are not detected yet – only kills, vehicles, distance and victim.
- Settings and log live in `%APPDATA%\KillFeed`. Delete that folder to run the setup again.

Feedback: press *Send feedback* in the app – it puts a zip (log + text hits, never video) on your desktop.
Drop it in **#feedback** on [Discord](https://discord.gg/YSRt9t7gq).
