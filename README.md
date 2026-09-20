# KillFeed

Automatic WARDOGS shorts and daily recaps – on your own PC, by themselves.

KillFeed reads the kill feed in your recordings (OCR on the HUD text), cuts every multikill and
vehicle kill into a ready-to-post 9:16 short with a title, merges the same kill from several
recordings into one clip, and builds a chronological 16:9 recap of the day when enough is collected.
No account, no upload – the clips land in a folder you sync to your phone and post from there.

**Website:** https://killfeed.no · **Download:** [latest release](https://github.com/kristofferlending/killfeed/releases/latest) · **Discord:** https://discord.gg/YSRt9t7gq

Free alpha, Windows 10/11. The exe is not code-signed yet, so SmartScreen warns once (*More info → Run anyway*).

## Layout

| Folder | What |
|---|---|
| `app/` | **KillFeed.exe** – the tray app (setup wizard, watching, Publish/Other, recap, notifications) |
| `app/killclip.py` | Kill-feed detection and clipping (shared) |
| `app/kf_core.py` | Everything that is not GUI: settings, ledger, dedup, selection, recap |
| `pipeline/` | Optional nightly job that clips with `kf_core` and uploads to YouTube with scheduled publishing – used for the [ThatsBonkers](https://www.youtube.com/@ThatsBonkers) channel |
| `bot/` | Discord bot + MCP server for the KillFeed server (needs its own `bot/secrets.txt`, never committed) |
| `site/` | killfeed.no (static, deployed by Vercel on push) |
| `docs/` | Release notes, roadmap, recording guide |
| `tests/` | Synthetic-recording tests for OCR, dedup, Publish/Other and recap |

## Run from source

Windows, Python 3.12, Tesseract (UB-Mannheim build) in `C:\Program Files\Tesseract-OCR`, and
ffmpeg essentials (gyan.dev) unpacked in `tools\ffmpeg\` (gitignored).

    dev-run.cmd                          # installs pystray/pillow/winotify, starts GUI + tray
    python app\killfeed_app.py --run     # one pass without GUI (debugging)

Settings, ledger and log live in `%APPDATA%\KillFeed\`. Delete that folder to run the setup again.

## Build the exe

    build\build_onefile.cmd

Produces `dist\KillFeed.exe` (~130 MB – ffmpeg, Tesseract and the watermark are bundled).
Releases are the exe plus `docs/RELEASE-<version>.md` as release notes.

## Tests

`tests\test_core.py` generates synthetic recordings with real kill-feed text in the zone and checks
OCR, dedup, Publish/Other, reserve and recap. Needs ffmpeg and tesseract on PATH (runs on Linux too).

    python tests\test_core.py

## Nightly job (pipeline/)

Not needed to use KillFeed. It runs on top of `kf_core` with the same settings and ledger as the app,
skips clipping while the app is running, uploads shorts from `Publish\` and recaps from `Recaps\`
with scheduled publish times, and cleans up. Copy `config.example.json` to `config.json`, put your
own Google OAuth `client_secret.json` next to it (never committed), run `3-auth-youtube.cmd` once,
then `4-installer-nattjobb.cmd` to register the scheduled task. `deploy.cmd` copies the current
files from the repo to the schedules folder.

## Feedback

Press *Send feedback* in the app – it puts a zip with the log and text hits (never video) on your
desktop. Drop it in #feedback on Discord with your resolution, recording tool and class.

## License

Source-available. You may read, build and modify KillFeed for your own use. Redistribution, resale or
offering it as a service is not permitted – see [LICENSE.md](LICENSE.md). © 2026 Lending Equipment.
