# KillFeed 0.4.1-alpha

Four fixes on top of 0.4-alpha. One of them is the worst bug this app has had, and it only shows up
when you combine two things that look harmless on their own.

**Download:** `KillFeed.exe` below (about 175 MB — ffmpeg and Tesseract are bundled). Windows 10/11.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*.

Walkthrough: **https://killfeed.no/guide**

---

## Fixed: a paused KillFeed said "Done" instead of "paused"

Pressing *Run now* while paused started a run that stopped on the first file and then reported
*"Done: 0 ready to publish, 0 in Other"* — which reads exactly like a finished run that found
nothing. The only clue was a bare *"Stopped."* line in the log.

Asking for work now lifts the pause instead of starting a run that cannot do anything, and it says
so. A run that was interrupted no longer borrows the word Done: it says how far it got — *"Stopped
before it finished — 3 of 16 recording(s) done, 13 left for next time."*

This mattered more than it sounds. *Reset and start over* deletes every clip first and clips again
afterwards, through the same path. Paused, it would delete everything and then quietly clip nothing,
leaving you with no clips, no recap and an empty recap bank — and an app reporting that it was done.
That is how it was found, on a real library of 223 clips. The recordings were untouched, so a single
run rebuilt all of it, but the half hour spent working out what had happened was not fun. That
combination is no longer reachable.

## Fixed: the dialog that deletes everything had Enter on the wrong button

Both dialogs put the gold primary style, the keyboard focus and the Enter key on the first button.
In *Reset and start over* that button is *Reset and start over*. Enter now belongs to Cancel in both,
and Escape closes them.

Saving a setting that changes how clips are cut no longer opens that dialog at all. It used to pop up
on Save with the destructive option under the cursor. Now it is a line of text: your existing clips
were cut with the old values, and *Rescan everything* redoes them when you want.

## Fixed: a vehicle kill was named and counted twice

Destroying an occupied vehicle fires KILL CONFIRMED and VEHICLE DESTROYED in the same instant. Both
counted as separate achievements, so a clip of two vehicle kills was titled *"2 kills, 2 vehicles
destroyed"* — four things for what the viewer saw happen twice.

It is named once now: that clip is *"2 vehicles destroyed"*. And it is worth 2 in the queue rather
than 3, so a three-kill streak outranks a single vehicle kill instead of tying with it. The Publish
rule still sees both banners, so vehicle clips qualify exactly as before.

## Fixed: wrong titles in the clip browser

The browser read the stored title out of the ledger, so clips cut before that fix kept showing the
old double-counted title — 13 of 223 on a real library. Title and score are now worked out from the
counts when the page is built, the same way the nightly upload does it, so they are right without
re-cutting anything.

---

Everything in **0.4-alpha** still applies: honest detection from the banner only, two kills in a row
counted as two, the clip browser with hover-to-play and ▲▼ marks, the recap bank, lone kills skipped,
and recordings deleted once they are clipped. Those notes are worth reading if you are coming from
0.3: https://github.com/kristofferlending/killfeed/releases/tag/v0.4-alpha

Feedback: press *Send feedback* in the app — it puts a zip (log + text hits, never video) on your
desktop. Drop it in **#feedback** on [Discord](https://discord.gg/YSRt9t7gq).
