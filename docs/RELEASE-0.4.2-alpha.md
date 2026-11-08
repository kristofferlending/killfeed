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

If you have clips from an earlier build, *Rescan everything* re-counts and re-sorts them.

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
