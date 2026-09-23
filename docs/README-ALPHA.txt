KillFeed 0.3.1-alpha -  automatic WARDOGS shorts and daily recaps, all by itself
================================================================================

What it does
  Sits in the system tray (next to the clock) and looks for new recordings every minute. When the
  game is not running it reads the kill feed (KILL CONFIRMED, VEHICLE DESTROYED, +$...) and makes:
    Publish\   finished 1080x1920 shorts with a multikill or a vehicle kill  + the title in a .txt
    Other\     single kills (kept, use them if you want)
    Recaps\    "WARDOGS recap <date>.mp4": a chronological 16:9 summary (5-10 min) of your normal
               recordings, built automatically when enough is collected
  The same kill from two recordings (replay + backtrack) becomes one clip.
  You get a Windows notification when something new is ready. Otherwise it is silent.
  No account, no login, nothing is sent anywhere.

Getting started (once)
  1. Double-click KillFeed.exe. Windows SmartScreen: "More info" -> "Run anyway"
     (the alpha is not signed yet). First start takes 5-10 s.
  2. The setup asks four things: where your recordings are (Videos\ is fine), what to make,
     what is good enough to publish, and where the clips should go (a OneDrive / Google Drive /
     Dropbox folder syncs them to your phone: YouTube app -> + -> pick -> paste the title -> Publish).
  3. Press "Start KillFeed". Done. It starts with Windows from now on.

Daily use
  None. Play. The clips show up in the output folder after the session (it waits until the game
  is closed). The Dashboard shows what it is doing, how many shorts you got, and the recent clips:
  double-click plays one, right-click explains why it landed in Publish or Other.
  The X button hides the window - KillFeed keeps running in the tray. "Quit KillFeed" stops it.

Tips
  - 20-35 seconds is the sweet spot for Shorts. Default is 8 s before / 3 s after the kill.
  - 1440p recordings give a sharper centre crop than 1080p.
  - Recording backtracks and full sessions in different folders: add the second one under
    Settings -> Extra folders. Recaps are only built from 16:9 recordings.
  - No clips? Then it found no kill text. Check that the HUD is on and the recording is the game
    itself (not the desktop). Press Send feedback and we will look at it.

Feedback
  "Send feedback" puts a zip on your desktop with the log and text hits (never video).
  Drop it in #feedback on the Discord server (the button opens it), together with:
  resolution, recording tool, class (heli / infantry) and whether the clips hit right.

Known in the alpha
  - WARDOGS only. Windows only. Clips carry a small "KillFeed alpha" mark.
  - Settings and log live in %APPDATA%\KillFeed. Delete that folder and the setup runs again.
