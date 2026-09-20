# Nightly job (pipeline/)

Optional. Not needed to use KillFeed – this is the automation behind the ThatsBonkers channel, kept here
because it runs on the same core. It uses `kf_core` with the same settings and ledger as the tray app:

1. `run_daily.py` clips new recordings via `kf_core.run_once` – **skipped if the KillFeed app is running** (it clips by itself).
2. `yt_upload.py` uploads shorts from `<output>\Publish` as Shorts and recaps from `<output>\Recaps` as normal videos,
   with scheduled publish times (`publish_times`, `weekend_publish_times`, `max_per_run`, `max_recaps_per_run`,
   `recap_publish_time`, `series_tag` in `config.json`). Titles come from the clip metadata.
3. Cleanup per `config.cleanup` (uploaded clips after N days, fully processed recordings after M days).
4. Log to `run_daily.log`; a message box only when something failed or the queue is empty.

## Setup

1. Copy `config.example.json` → `config.json` and adjust.
2. Create a Google Cloud project with the YouTube Data API v3 (and YouTube Analytics API for `yt_analyse.py`),
   an OAuth desktop client, and save its JSON as `client_secret.json` in this folder. **Never commit it** – it is gitignored,
   as are `token.json`, `state.json` and `config.json`.
3. `1-installer-tesseract.cmd` once (Python packages, ffmpeg, Tesseract), then `3-auth-youtube.cmd` once
   (scopes: youtube.upload, youtube.readonly, yt-analytics.readonly – deliberately not full `youtube`).
4. `4-installer-nattjobb.cmd` as administrator registers the scheduled task (04:00 daily + 20 min after logon).
5. `deploy.cmd` copies the current files from the repo to the schedules folder whenever the code changes.

Other cmd files: `5-kjor-naa` runs the job now, `8-test-upload-dry` shows what would be uploaded,
`9-analyse-channel` dumps channel statistics to `analysis.json/txt`, `10-clean-queue` reconciles `state.json` with YouTube.
