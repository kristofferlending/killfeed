# KillFeed 0.4.2-alpha

KillFeed took about 40 frames per second off the game — and the setting that was supposed to prevent
that only half worked. That is most of this release, and it turned out to have five
separate causes, from a check in the wrong loop to a window that would not stop redrawing itself.
There is also a counting fix that has nothing to do with performance and everything to do with
telling the truth in a title.

**Download:** `KillFeed.exe` below (about 175 MB — ffmpeg and Tesseract are bundled). Windows 10/11.
SmartScreen warns once because the alpha is not code-signed: *More info → Run anyway*.

Walkthrough: **https://killfeed.no/guide**

---

## Fixed: "pause while the game is running" did not pause a run already going

The setting lived in the loop that decides whether to *start* clipping. A run that was already
underway when you launched the game kept going — full tilt, for hours, through the whole session.
The name promised "pause while the game is running"; the code did "don't begin while the game is
running".

A separate watchdog now checks every five seconds, on its own thread, whether the game is up. If it
is and a run is going, ffmpeg is killed immediately rather than after the current file, which on a
126 GB recording could have been another twenty minutes. The interrupted recording is not written to
the ledger, so it is clipped again from the start next time: you lose a few minutes of clipping,
never a clip.

## Fixed: a clip titled "3 kills" that showed one

The banner under the crosshair stays on screen for eight or nine seconds. The kill counter looked at
banner frames inside the clip's window without asking whether the banner was already there when the
window opened — so the tail of a banner from a kill that happened *before* the clip starts counted as
a kill of its own. The kill feed down the left side lingers too, so the victims were visible in the
corner while the action itself was outside the clip entirely.

Found on a real upload: three kills at 2765, 2770 and 2780 seconds into a recording, cut as a clip
running 2772 to 2787. One kill inside the window, three in the title.

A kill now counts only if its banner *began* inside the window, and the start times are worked out
once over the whole recording rather than per clip. Measured over 649 segments from six sessions,
643 count exactly as before and six drop — all of them from two kills to one, and all six were only
in Publish because of the tail. A genuine double kill, and two kills inside the same second told
apart by the reward amount, both still count correctly.

If you have clips from an earlier build, you do not need to re-cut anything. The clip window is in
the file name, so the counting can be redone over exactly the window each clip was cut from, from the
reports alone — seconds instead of the seven hours a full rescan takes. Close KillFeed and run
`private\fix-counts.cmd`: it re-counts, rewrites the titles and scores, moves the files between
`Publish\` and `Other\`, and keeps a timestamped backup of the ledger. *Rescan everything* still
works and does the same thing the slow way.

## Fixed: KillFeed cost frames even when it was not clipping

Stopping the clipping was not enough. The window and the interface loop cost frames on their own,
and in hindsight that is not surprising: redrawing a window three times a second on top of a
fullscreen game keeps desktop composition running and takes the game out of exclusive fullscreen.

KillFeed now goes properly to sleep. When a game is detected the window is hidden to the tray and
the interface loop stops drawing entirely — it wakes every two seconds only to ask whether the game
is still there. Nothing is drawn, nothing is calculated, nothing is scanned. When you close the
game it wakes up again by itself, without jumping in front of whatever you are doing.

**`game_process_hint`** now takes several names with commas between them — `"wardogs, cs2,
premiere"` — so KillFeed can stand down for anything that wants the machine, not only WARDOGS.

## Fixed: text reading used every core on the machine

The OCR pool was `os.cpu_count()` wide — on an i9 that is 24 or 32 tesseract processes at once, and a
six-hour recording is roughly 130,000 of them. That is where most of those 40 frames went.

The default is now half the logical CPUs. Tesseract scales badly past a point anyway — disk and
memory bandwidth bind before the cores do — so half costs little time and gives you back half the
machine. **Advanced → settings.json → `cpu.workers`** if you want it tighter or wider.

## Changed: ffmpeg and tesseract now run at idle priority

They were at normal priority, competing with the game as equals. Idle priority on Windows also means
low *disk* priority, and that turned out to matter more than the CPU: reading a recording fills the
queue of the same disk the game streams from, which is why inputs hung rather than just the frame
rate dropping. When nothing else wants the machine, idle processes get all of it, so overnight
clipping is as fast as before.

## New: pin clipping to chosen cores

**`cpu.worker_cores`** in `settings.json`. Empty means every core, which is right for most people
now that clipping yields on its own. On a hybrid CPU — Intel 12th gen and newer — putting the work on
the E-cores leaves the P-cores to the game: `"16-31"`, or `"8,9,10,11"`. The mask is inherited by
every ffmpeg and tesseract the run starts.

## New, and off: decode the recording on the GPU

**`cpu.hwaccel: "cuda"`**. Software HEVC decoding is the most expensive single step in a scan, and
NVDEC is a separate block of silicon from the shaders a game uses, so moving it there costs almost no
frames. Potentially the largest win of the four.

It ships off because it depends on your driver and ffmpeg build, and a decode that fails quietly
would hand the text reading fewer frames and produce fewer clips without saying so. Turn it on, clip
one recording whose clip count you already know, and compare before trusting it.

## Changed: what gets into Publish is now density, not a count

`min_kills` could not tell a double kill from three unrelated kills spread over a minute and a half,
because it only counted events in the window. A short called "3 kills" should show three kills that
belong together.

Publish now needs either two kills within three seconds of each other, or a run of three kills that
holds a pace of one every five seconds. One kill every five seconds is a good clip; three kills over
ninety seconds is not, whatever the count says. The thresholds are **`shorts.publish`** in
`settings.json` — `double_s`, `pace_s`, `pace_need` — and `vehicle_qualifies`, off by default, lets a
lone vehicle kill through on its own.

`tools/queue_preview.py` rebuilds the whole queue from the reports without reading a frame of video,
so a threshold can be tried out before anything is cut: `private\queue-preview.cmd`, with
`--double 5 --need 4 --pace 7` or similar appended.

## New: tell it what actually happened in a clip

The whole threshold discussion had been guesswork, because nobody had checked what the clips really
contain. *Browse clips* now has **+** and **−** on kills and vehicles and a **✓ correct** button, so
you can watch a clip and say what happened in it. That makes accuracy something measured rather than
argued about: `queue-preview.cmd` ends with a report of how often the detector counts right and which
clips it misses.

The first twelve clips checked this way found the banner-tail bug above in the numbers rather than in
an argument: it counted one too many on eleven of twelve. With the fix, eleven of twelve are exact.
The twelfth is a limit of the signal, not a threshold — four kills landed inside one banner and only
two reward amounts were ever legible.

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
taskbar when the game closes — without taking focus, in case you have something else open. If you had
put it in the tray yourself, it stays there.

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


---

## Why this took four fixes and not one

Worth writing down, because the shape of the mistake is more useful than the mistake.

The pause check was in the GUI, and the GUI has no automated tests — Tkinter needs a display, and the
suite runs without one. So the whole app layer was verified by careful reading alone, which is how a
setting that checks the wrong moment survives an audit that did look at that very file. The decision
now lives in `kf_core.should_hold_for_game()`, where a test can reach it, and it has one. Anything
that answers a yes-or-no question belongs somewhere a test can get to it.

The conditions also only appeared now. The queue had always been empty by the time there was any
gaming, because clipping happened overnight. One reset put sixteen recordings — over a terabyte — in
the queue at six in the evening, and the bug had been sitting there the whole time waiting for that.

Feedback: press *Send feedback* in the app — it puts a zip (log + text hits, never video) on your
desktop. Drop it in **#feedback** on [Discord](https://discord.gg/YSRt9t7gq).
