# KillFeed 0.4-alpha

Everything since 0.3-alpha. The detection got a lot more honest, the clip browser became the place you
actually work, and KillFeed can now clear the recordings off your disk once it is done with them — with
two guards that took an audit to get right.

If you are on 0.3: replace the exe, then run *Advanced → Maintenance → Reset and start over* so your
clips are rebuilt with the current rules. It takes hours. Let it run overnight.

**Download:** `KillFeed.exe` below (about 175 MB — ffmpeg and Tesseract are bundled). Windows 10/11.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*.

There is a full walkthrough at **https://killfeed.no/guide** now — setup to first posted short, every
setting, and what to do when something looks wrong.

---

## Fixed: clips with no kill in them

WARDOGS puts kill information in three places: the banner under your crosshair, the money HUD top right,
and the kill feed down the left side. Only the banner is about *you* — the other two show what everyone
on the server is doing, and both are outside the frame once a clip is cropped to 9:16.

Until now any text in any of the three counted as your kill. That produced shorts titled *"1 kill (216 m),
1 vehicle destroyed"* where nothing happens on screen: the kill was real, but it was someone else's, in a
corner the viewer never sees.

Only the banner can create an event now. The money HUD contributes the amount, the kill feed contributes
distance and victim, and neither can create anything on its own. A distance is attached only when the
banner fired within 2.5 s of that feed row, and an event has to be read in at least two frames within
1.5 seconds so a single misread frame is not enough.

## Fixed: two kills counted as one

Two kills in a row overlap on screen — the second banner replaces the first with no dark frame between
them, so the gap is a quarter of a second, and the counter only started a new kill after three seconds of
quiet. Both kills were found; they were just counted once.

The banner prints its own reward, and that is what tells them apart:

    8.50-12.75 s   KILL CONFIRMED  +$2,250  300XP
    13.00-17.25 s  KILL CONFIRMED  +$1,500  250XP

The amount is read from the banner itself, not the money HUD, so it survives the 9:16 crop and works the
same on a vertical recording. A new amount has to hold for two frames before it counts. Two kills with
the same reward back to back are still merged — rare, and deliberately preferred over inventing kills.

## Fixed: 15-second clips that were 1.4 GB

`-ss` and `-t` sat between the recording and the watermark in the ffmpeg command, so the duration was read
as an option for the watermark instead of the cut. Only the packaged build has a watermark, which is why
this never showed up when running from source: the exe wrote everything from the cut point to the end of
the recording.

## Fixed: the cleanup could have deleted your whole recording library

Found in an audit, before it ever ran with deletion switched on.

A Tesseract that starts but cannot work — tessdata moved by a Windows update, a corrupt language file, a
locked temp dir — exits with an error code and empty output. KillFeed ignored the exit code, so every
frame read as empty, every recording looked like a quiet session with no kills, and every recording became
eligible for deletion. One broken install would have walked the whole library and produced nothing.

Text reading now fails loudly and is recorded as an error on that file. On top of that, the cleanup
requires proof that text was actually read in that specific recording before it may delete it. A session
where genuinely nothing happened is kept — that is the cheap mistake to make.

A second one from the same audit: the ledger was keyed by file name. OBS and Aitum Vertical share a
naming scheme, so the same name routinely exists in both your full-format and your vertical folder. Keyed
by name they collapsed into one entry — the second was silently never clipped, and the cleanup could look
up the first one's entry and delete a recording it had never processed.

## New: the clip browser

**Browse clips** on the Dashboard builds a page of every clip and opens it in your browser. Sortable,
searchable, with thumbnails.

- **Hover to play.** The clip plays in place when you move the mouse over it. Nothing is downloaded
  before you hover, so a page with a few hundred clips stays light.
- **▲ and ▼ on every clip.** Marked ▲ jumps to the front of the queue. Marked ▼ is never uploaded by
  anything, ever. Two filters at the top show what you have decided.

Marks are saved straight back into KillFeed by a small server that listens only on your own machine.

This exists because of something worth being straight about: KillFeed cannot tell a good clip from a lucky
one. Measured against 17 uploads on a real channel, no weighting of kills, vehicles, distance or length
predicted views at all. The score sorts the queue and keeps the empty ones out. Which of the survivors is
worth posting is a judgement, and you are the one who can make it.

## New: lone kills are not clipped at all

**Advanced → Shorts → Skip a lone kill with nothing within N s** (15 s by default). Measured over six
sessions, 175 of 229 clips — 76 % — were a single kill with no other kill or vehicle within 15 seconds.
None of them could reach Publish anyway, so they only cost clipping time and disk.

A kill together with the vehicle it destroyed is one moment with two events and is kept. So is a vehicle
kill on its own.

## New: kills have to be a burst

Two kills twenty seconds apart used to be chained into one 30-second short where nothing happens in
between. Kills now only count towards Publish when they land within **Advanced → Shorts → Kills must be
within N s of each other** (10 s by default). Changing it also re-sorts the clips you already have,
moving them between `Publish\` and `Other\`.

## New: a third way to fit 16:9 into 9:16

**Split** — the whole picture across the top so the HUD and kill feed stay readable, and a centre crop
about 1.8× below so the action is big. For when there is no vertical recording of a moment. The two old
choices, centre crop and blurred background, are unchanged.

## New: delete recordings once they are clipped

**Advanced → Disk space.** Off by default. A recording is tens of gigabytes; the clips it produces are
tens of megabytes.

This cannot be undone — a deleted recording does not go to the Recycle Bin — so read the section in the
walkthrough before turning it on. KillFeed will not delete a recording it failed to clip, and will not
delete one where it read no kill text at all.

The recap is cut from the recording itself, not from the finished shorts, so deleting recordings would
have quietly dropped those kills out of every future recap. That is what **RecapBank** is for: while
clipping, KillFeed also saves the recap-sized pieces as small separate files, well under a gigabyte per
session. Once a session is in the bank the recording is no longer needed for anything.

## New: Reset and start over

One button in **Advanced → Maintenance** that throws away every clip KillFeed has made and clips all your
recordings again with the current settings. Your own recordings are never touched.

## Fixed: a vehicle kill was named and counted twice

Destroying an occupied vehicle fires KILL CONFIRMED and VEHICLE DESTROYED in the same instant. Both were
counted as separate achievements, so a clip of two vehicle kills was titled *"2 kills, 2 vehicles
destroyed"* — four things for what the viewer saw happen twice.

It is named once now: that clip is *"2 vehicles destroyed"*. And it is worth 2 in the queue rather than
3, so a three-kill streak outranks a single vehicle kill instead of tying with it.

The Publish rule still sees both banners, so vehicle clips qualify exactly as before. Clips cut before
this change are re-titled and re-scored when they are clipped again.

## Changed: how the queue is ordered

`1 point a kill + 2 a vehicle + 1 per 100 m − half a point a second over 22`. An ordering you can do in
your head. The nightly job uses the same formula, so its queue matches what the browser shows.

The vehicle weight used to be tuned automatically from view counts each night. That is gone: over 17
uploads no weighting correlated with views (rank correlation between −0.36 and +0.09), so it was fitting
noise and quietly overriding the fixed weights.

## Fixed: a paused KillFeed said "Done" instead of "paused"

Pressing *Run now* while paused started a run that stopped on the first file and then reported
*"Done: 0 ready to publish, 0 in Other"* — which reads exactly like a finished run that found
nothing. The only clue was a bare *"Stopped."* line in the log.

Two changes. Asking for work now lifts the pause instead of starting a run that cannot do anything,
and it says so: *"Pause lifted — you asked for a run."* And a run that was interrupted no longer
borrows the word Done; it says how far it got — *"Stopped before it finished — 3 of 16 recording(s)
done, 13 left for next time."*

This mattered more than it sounds. *Reset and start over* deletes every clip first and clips again
afterwards, and it goes through the same Run now path. Paused, it would delete everything and then
quietly clip nothing — leaving you with no clips, no recap and an empty recap bank, and an app
reporting that it was done. That combination is no longer reachable.

## Fixed: the dialog that deletes everything had Enter on the wrong button

Both of the app's dialogs put the gold primary style, the keyboard focus and the Enter key on the
first button. In *Reset and start over* that button is *Reset and start over*. Enter now belongs to
Cancel in both dialogs, and Escape closes them.

Saving a setting that changes how clips are cut no longer opens that dialog at all. It used to pop
up on Save with the destructive option under the cursor. Now it is a line of text: your existing
clips were cut with the old values, and *Rescan everything* redoes them when you want.

## Fixed: wrong titles in the clip browser

The browser read the stored title out of the ledger, so clips cut before the vehicle fix kept
showing *"2 kills, 2 vehicles destroyed"* for two vehicle kills — 13 of 223 on one real library.
Title and score are now worked out from the counts when the page is built, the same way the nightly
upload does it, so they are right without re-cutting anything.

## Also

Recordings made with audio capture switched off no longer fail as "damaged". Rescan asks before killing
the file it is working on, instead of after. The clip browser opens in seconds during a run instead of
twenty minutes. Three status lines stopped printing the literal words "ok" and "warn" at you. A stopped run
no longer claims the recordings it never reached were checked.

## Known in this alpha

- WARDOGS only, Windows only, English only. Clips carry a small "KillFeed alpha" mark.
- Tuned on 1080p/1440p with the HUD at 100 %. Other HUD scales may miss kills — tell us.
- Turning on *delete the recording* applies to everything already clipped, not just new recordings.
  If you have months of footage, expect a large clear-out on the next run.
- Weapon and class are not detected yet — only kills, vehicles, distance and victim.
- Settings and log live in `%APPDATA%\KillFeed`. Delete that folder to run the setup again.

Feedback: press *Send feedback* in the app — it puts a zip (log + text hits, never video) on your desktop.
Drop it in **#feedback** on [Discord](https://discord.gg/YSRt9t7gq).
