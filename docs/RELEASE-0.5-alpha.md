# KillFeed 0.5-alpha

This release is about trusting what KillFeed says about a clip. Publish is now decided by how close
together the kills are rather than how many there are, you can tell KillFeed what actually happened in
a clip and it believes you over its own reading, and the clip browser became a tool you can work
through a hundred clips in. Text reading is about three times faster, and two ways KillFeed could
disturb a game are gone.

**Download:** `KillFeed.exe` below (about 175 MB — ffmpeg and Tesseract are bundled). Windows 10/11.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*. The SHA-256 of
the exe is at the bottom of these notes, so you can check the file is the one published here.

Walkthrough: **https://killfeed.no/guide**

---

## Changed: what gets into Publish is now density, not a count

`min_kills` could not tell a double kill from three unrelated kills spread over a minute and a half,
because it only counted events in the window. A short called "3 kills" should show three kills that
belong together.

Publish now needs either two kills within three seconds of each other, or a run of three kills that
holds a pace of one every five seconds. One kill every five seconds is a good clip; three kills over
ninety seconds is not, whatever the count says. The thresholds are **`shorts.publish`** in
`settings.json` — `double_s`, `pace_s`, `pace_need`. Choosing *Multikill or vehicle destroyed* in setup
or Settings also lets a lone vehicle kill through on its own; *Multikills only* does not.

For anyone running from source: `tools/queue_preview.py` rebuilds the whole queue from the reports
without reading a frame of video, so a threshold can be tried out before anything is cut
(`--double 5 --need 4 --pace 7`).

## New: tell it what actually happened in a clip

The whole threshold discussion had been guesswork, because nobody had checked what the clips really
contain. *Browse clips* now has **+** and **−** on kills and vehicles and a **✓ correct** button, so
you can watch a clip and say what happened in it. That makes accuracy something measured rather than
argued about (`tools/queue_preview.py --ledger` reports how often the detector counts right and which
clips it misses).

Measured on 67 clips checked by hand: 48 counted exactly, 15 one kill short, 4 one too many. The
misses are mostly two kills inside one banner, where the banner shows a per-kill reward and a running
total in the same place and only one of them is legible. 0.5 starts saving both numbers raw, so the
counting can be improved against these checks without cutting anything again.

## Changed: your correction now overrides the detector

Saying what happened in a clip used to change nothing about the clip. It was ground truth for
measuring the detector and nothing else: the title stayed wrong, the score stayed wrong, and the clip
stayed in whichever folder the counting had put it in. There was no way to tell that a correction had
any effect at all, which is a strange thing to ask someone to do twenty-three times.

Now the clip follows what you said. The title, the score, the queue and the folder all take your
number — in both directions. Say three kills where it counted two and the clip is retitled and moved
to Publish. Say one kill where it counted two inside three seconds and the "double" was imagined, so
the clip is retitled and moved out of Publish. Press undo and the detector's own count comes back.

Publish needs timings, and a count has none, so a human-verified count of `pace_need` kills or more
counts as dense enough: you corrected it upwards because you saw a chain, not four kills spread over
a minute. Two kills plus a double the detector actually saw in time still qualifies as before.

The card now says what the correction did — "title is now ..., moved to Publish" — instead of
"saved", and shows what the detector had thought next to your number so the difference stays visible.
The detector's own count is kept untouched underneath, so the accuracy report still measures the
detector against you rather than against itself.

## Fixed: labels were lost when you quit

Saying what happened in a clip wrote the answer into the ledger in memory and never to disk, so a
labelling session survived only until the app closed. It saves on every answer now.

## Fixed: the window never came back from sleep

Going to sleep for the game hides the window. Waking up again did not bring it back — deliberately,
so it would not jump in front of a game — and the only trace of the app left was a tray icon Windows
11 hides under the chevron. From the outside it looked like KillFeed had vanished.

It did not even need you to be playing: WARDOGS stays in the process list for a few seconds after you
close it, so starting KillFeed right after a session was enough. One five-second sweep, and the window
was gone. Sleep now remembers whether it was the one that hid the window, and if so puts it back in the
taskbar — minimised, so it can never take focus from whatever you are doing. If you had put it in the
tray yourself, it stays there.

## Changed: text reading starts a few hundred processes instead of tens of thousands

Tesseract was started once per frame — around 130,000 times for a six-hour recording. It also takes a
list of images and reads them all in one process, writing the pages one after another, which is the
same work with a fraction of the overhead. A process start is not free on Windows: the Program
Compatibility Assistant attaches to every single one, and was sitting at 21 % CPU by itself during a
scan.

Frames are now read 200 at a time. Measured 3.2 times faster over 600 frames, with byte-identical
text. 200 and not "all of them in one go" because a batch cannot be interrupted part-way, and when a
game starts KillFeed has to let go of the machine at once — 200 frames is a few seconds. If a future
Tesseract version ever wrote the page breaks differently, every kill would land at the wrong time with
nothing looking wrong, so the page count is checked against the frame count and the batch is re-read
one frame at a time if they disagree.

## Fixed: the Publish choice in Settings did nothing

The three choices — *Multikill or vehicle destroyed*, *Every kill*, *Multikills only* — were saved in
Settings to two values nothing reads any more, and the screen showed the choice from those same values.
So it could say *Multikill or vehicle destroyed* while vehicle kills were being kept out of Publish, and
changing it moved nothing. Settings now shows the rule that is actually in effect and saves to it, and
the clips you already have are re-sorted when it changes. If you went through setup with an older
build, open Settings once and check the choice — it may show something other than you expected, and
that is the rule you have been running with.

## Fixed: KillFeed could wake up in the middle of a game

KillFeed asks Windows every five seconds whether the game is running. If Windows did not answer in
time — which happens under exactly the kind of load a game creates — the silence was read as "the game
has closed", and KillFeed woke up mid-round. Now an unanswered question means *don't know*, and KillFeed
stays asleep. Waking needs two "closed" answers in a row, ten seconds apart.

## Changed: titles say only what the viewer can see

Titles no longer carry the distance. It was read from the kill feed down the left of the screen, which
is cropped away in a 9:16 short — so "(161 m)" was a claim about something the viewer could not see.
The distance still sorts the clip browser (*Longest shot*).

## Fixed: the clip browser

- **Corrections showed nothing.** Pressing + saved every time, but the number on the card did not move,
  and the line under it read "[object Object]". Both fixed: the number moves as you press, and the card
  says in words what your correction did.
- **The list re-sorted under your finger.** Correcting a clip from two kills to three changes its score
  and often its folder, so the card jumped away after the first press. The order now stays put while
  you work. A **Re-sort** button lights up when your corrections have changed the order; the list
  rearranges when you press it, change view, search or sort.
- **Not checked.** A new view with only the clips you have not said anything about yet, and a count of
  how many are left.


---

Feedback: press *Send feedback* in the app. It puts a zip on your desktop with the log, your settings,
the clip list and the text KillFeed read — never video. It contains file paths with your Windows user
name and the names of players in your recordings, so look at it before you post it publicly; you can
also send it to us privately on [Discord](https://discord.gg/YSRt9t7gq).
