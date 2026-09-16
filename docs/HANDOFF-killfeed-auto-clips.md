# KillFeed / WARDOGS auto-clips – overleveringsdokument

*Skrevet 16.09.2026 for å kunne fortsette arbeidet i en ny Cowork-samtale. Alt under er slik det faktisk står på mini nå.*

---

## 1. Hva dette er

En helautomatisk pipeline på Kristoffers PC **mini** som:

1. leser WARDOGS-opptak (Aitum-backtracks i 9:16 og/eller hele OBS-opptak i 16:9),
2. finner kills ved å OCR-lese kill-feeden («KILL CONFIRMED», «VEHICLE DESTROYED», «+$…»),
3. klipper 18–40 s shorts i 9:16 med automatisk tittel,
4. dedupper (samme kill fra to filer → bare det beste),
5. laster opp de beste multikill-/vehicle-klippene til YouTube-kanalen **ThatsBonkers** med planlagt offentlig publisering kl 17:00 og 21:00,
6. lærer av avspillingstall, rydder disken og varsler med msgbox bare når noe feiler.

Kristoffer skal bare trykke **Start Streaming** i OBS. Resten skjer om natta.

Samme motor (`killclip.py`) er pakket som alfa-exe **KillFeed** for kompiser (recon/assault-spillere) – se kap. 9.

Beslutningslogg (Supabase `claude-memory`, tabell `beslutninger`, prosjekt-slug `killfeed`, tidligere også `generelt`): rad #546–#564 + tre rader 16.09 (multikill-regel, dedup, selvgående pipeline). Bruk `/logg` for å hente dem.

---

## 2. Kontoer, ID-er og mapper

| Hva | Verdi |
|---|---|
| YouTube-kanal | ThatsBonkers, kanal-ID `UChakg7sXDIPLNuSv0TauWrg`, @ThatsBonkersClips |
| Google Cloud-prosjekt | `thatsbonkers-uploader` (153278979203), YouTube Data API v3 aktivert 16.09, OAuth Desktop-klient, consent External/Testing, testbruker kristofferlending@icloud.com |
| Studio | Avanserte funksjoner **aktivert** 16.09 (gyldig legitimasjon) → høyere daglig opplastingsgrense |
| Rotmappe på mini | `C:\Users\krist\Videos\Wardogs\` (Cowork-mappen er koblet hit) |
| Skript | `…\Wardogs\auto-clips\` |
| Aitum-backtracks (9:16) | `…\Wardogs\02-shorts\*.mkv` (`Backtrack WARDOGS YYYY-MM-DD HH-MM-SS.mkv`, tidsstempel = **lagringstidspunkt = slutt**) |
| OBS-helopptak (16:9) | `C:\Users\krist\Videos\WARDOGS\01-raw\*.mkv` (`YYYY-MM-DD HH-MM-SS.mkv`, tidsstempel = **start**), 2560×1440, HEVC NVENC, CQP 20, lydspor 1/3/4 |
| Ferdige klipp | `…\Wardogs\05-auto-clips\` (mp4 + .json + .txt per klipp, `<kilde>-auto.json` per kildefil) |
| Gamle klipp uten klokketid | `…\05-auto-clips\gamle-uten-dedup\` (flyttet av 7-klipp-alt-paa-nytt) |
| ffmpeg | `…\auto-clips\ffmpeg\ffmpeg-*-essentials_build\bin\` (gyan.dev essentials, ffmpeg 9) |
| Tesseract | `C:\Program Files\Tesseract-OCR\tesseract.exe` (UB-Mannheim via winget) |
| Python | 3.12 via winget (`python`, fallback `py -3`), pakker `google-api-python-client`, `google-auth-oauthlib` |
| Task Scheduler | Oppgave **«WARDOGS auto-clips»**: daglig 04:00 + 20 min etter innlogging, kjører `run_daily.py` |

**Aldri les, kopier eller send innholdet i `client_secret.json` eller `token.json`.**

---

## 3. Filene i `auto-clips\` og hva de gjør

### Kjerne (Python)

**`killclip.py`** – detektor og klipper. Kjøres per kildefil: `python killclip.py <video> <utmappe> [--fps 2 --pre 12 --post 4 --gap 12 --min 18 --max 40 --style center|blur]`.
- `_appdir()` → `sys._MEIPASS` når frosset (PyInstaller), ellers skriptmappa. `_find(exe)` leter etter ffmpeg/ffprobe i `ffmpeg\`-undermappe, PATH, winget-Links. `_tess()` finner tesseract.
- `probe()` → varighet, bredde, høyde via ffprobe.
- `rois_for(w,h)` → to crop-soner (relative, så både 9:16 og 16:9 virker): sone 1 under trådkorset (kill-feed), sone 2 øverst til høyre (HUD/penger). Verdier:
  - 9:16: `crop=w*0.65:h*0.16:w*0.175:h*0.69` og `crop=w*0.30:h*0.06:w*0.70:h*0.345`
  - 16:9: `crop=w*0.22:h*0.10:w*0.39:h*0.71` og `crop=w*0.19:h*0.09:w*0.80:h*0.02`
- `detect()` – én ffmpeg-kjøring med `split` som skriver PNG-er for begge soner ved 2 fps (terskel til svart/hvitt), Tesseract `--psm 6` per bilde (les output med `encoding="utf-8", errors="replace"`), regex for `KILLCONFIRMED|KILLASSIST|VEHICLEDESTROYED|HEADSHOT|KILL|ASSIST|\+\$\d+`. Bilder med bare penger ignoreres.
- `cluster(hits, dur, pre, post, gap, mn, mx)` – slår sammen treff med < `gap` s mellom, legger på `pre`/`post`, strekker til `min`, deler i biter på `max` (overlapp 3 s). **Fikset 16.09:** sammenslåingssteget etterpå slår bare sammen hvis resultatet ≤ `max` (før ble 40 s-biter limt tilbake til 80 s).
- `cut()` – 9:16 inn → passthrough-skalering; 16:9 inn → senter-crop (default) eller blurred background. Vannmerke (`watermark.png`) legges på **bare når frosset** (KillFeed.exe).
- `summarize()`/`auto_title()` → f.eks. `WARDOGS – 2 kills, 1 vehicle destroyed (+$4,625) #shorts`. Kills telles som «bølger» (treff < 3 s fra hverandre = samme kill).
- `file_start_epoch(path, dur)` **(nytt 16.09)** – klokketid for sekund 0: dato i filnavn; inneholder navnet «backtrack»/«replay» er stempelet slutt (ts − dur), ellers start; uten dato: mtime − dur.
- `_run()` skriver per klipp en sidecar-JSON: `file, source, source_res, start, end, len, events, kills, vehicles, money, score (kills*3+veh*4+$/1000), title, abs_start, abs_events (epoch per kill/vehicle), clamped_start (true når klippet startet på 0 uten plass til pre-roll → selve killet kan mangle)`. Loggtekst går til **stderr**, JSON-rapport til **stdout** (run_daily parser fra første `{`).

**`yt_upload.py`** – utvalg, dedup, kø og opplasting. `python yt_upload.py [--auth] [--dry] [--max N]`.
- `creds()` – token.json / client_secret.json, scopes `youtube.upload` + `youtube.readonly`. `--auth` åpner nettleser (engang).
- Kandidater: `*.mp4/mkv/mov` i `clips_dir` som ikke står i `state.uploaded`, eldre enn `min_age_seconds`.
- **Regel:** `kills ≥ min_kills (2)` **eller** `vehicles ≥ min_vehicles (1)`, og `score ≥ min_score (0)`. Klipp uten sidecar-json (manuelle) slipper alltid gjennom.
- **Dedup** (rekkefølge beste først): (a) filnavn-range `<kilde>-autoNN-AAA.A-BBB.B` overlapper noe i `state.uploaded` → duplikat (fanger gamle opplastinger uten abs_events); (b) `abs_events` innenfor `dedup_seconds` (5) av noe opplastet → duplikat; (c) samme mot et bedre klipp i denne runden → duplikat. Duplikater skrives til `state.duplicate` og hoppes over for alltid.
- **Utløp:** klipp eldre enn `queue_max_age_days` (21) som fortsatt ligger i kø → `state.expired`.
- **Tom kø:** ingen kvalifiserte → beste enkeltkill slippes gjennom som reserve (`fallback_single_when_empty`).
- **Læring:** hvis ≥ 6 opplastinger, hent `videos.list(part=statistics)`; snitt visninger vehicle-klipp / ikke-vehicle → `state.veh_weight` (klemt 2–8, default 4). Sortering: `kills*3 + vehicles*veh_weight + $/1000`, minus 3 hvis `clamped_start`.
- **Kø/planlegging:** `privacy: "public"` + `publish_times: ["17:00","21:00"]` → hvert klipp lastes opp `private` med `publishAt` (UTC) på neste ledige slot. `next_slots()` starter fra `max(nå+1t, state.last_publish_at)` så to netter aldri deler slot. Uten `publish_times` går det rett ut som `public`.
- Skriver ut hva YouTube faktisk svarte (`privacyStatus`, `publishAt`) og advarer hvis public ble overstyrt (uverifisert app-lås). **Verifisert 16.09: planlagt publisering fungerer** (`private + publishAt` godtas).
- `state.uploaded[filnavn] = {id, at, title, privacy, publishAt, abs_events}`; feil → `state.failed` (prøves igjen neste kjøring; `quota` i feilmelding → stopp).

**`run_daily.py`** – nattjobben. `python run_daily.py [--no-upload] [--limit N]`. Logger til `run_daily.log`.
- Steg 1: alle `*.mkv/mp4/mov` i `backtracks_dir` + `extra_source_dirs` som ikke står i `processed.json` og er > 5 min gamle → `killclip.py` med parametre fra `config.killclip`. Resultat (antall klipp/feil) til `processed.json`.
- Steg 2: streamer `yt_upload.py`-output linje for linje til loggen; fanger `FEIL`/`ADVARSEL`, exit-kode og «0 klipp kvalifiserer» (tom kø) som problemer.
- Steg 3 (rydding, `config.cleanup`): sletter klipp (+ .json/.txt) som er `uploaded`/`duplicate`/`expired` og eldre enn `uploaded_clip_days` (7); sletter kildefiler som står i `processed.json` og er eldre enn `source_days` (14).
- Varsling: finnes problemer og `varsling == "msgbox"` → PowerShell `MessageBox.Show(...)` startes **uten å vente** (blokkerer ikke oppgaven).

**`killfeed_app.py`** – Tkinter-GUI for alfaen (inn-/utmappe, stil, pre/post/min/max, Kjør, «Send tilbakemelding»-zip). Kaller `killclip.process()`.

### Cmd-filer (alle har forklarende header øverst, CRLF-linjeskift, `->` skrives `-^>` i echo)

| Fil | Gjør |
|---|---|
| `1-installer-tesseract.cmd` | winget: Python 3.12, Gyan.FFmpeg, UB-Mannheim Tesseract. Engang. |
| `2-test-klipping.cmd` | Sjekker ffmpeg/Tesseract (laster ned ffmpeg-zip til `auto-clips\ffmpeg` hvis mangler), pip-installerer Google-pakker, klipper én backtrack som test. |
| `3-auth-youtube.cmd` | `yt_upload.py --auth --dry`, alt til `auth.log`. Engang. |
| `4-installer-nattjobb.cmd` | Kjører `install_task.ps1` (Register-ScheduledTask med eksplisitt principal, schtasks-fallback). **Må kjøres som administrator.** |
| `5-kjor-naa.cmd` | Spør hvor mange backtracks, kjører `run_daily.py --limit N` (0 = hopp rett til dedup/opplasting). |
| `6-test-offentlig.cmd` | `yt_upload.py --max 1` – laster opp ett klipp og viser YouTube-svaret. |
| `7-klipp-alt-paa-nytt.cmd` | Flytter gamle klipp til `gamle-uten-dedup\`, nullstiller `processed.json`, klipper alt på nytt (`--no-upload --limit 500`). Kjørt 16.09 ca. 08:15. |
| `build_alpha.cmd` / `build_onefile.cmd` | PyInstaller onedir-zip / én `dist\KillFeed.exe` (`--add-data` ffmpeg, tesseract, watermark, killclip). |

### Konfig og tilstand

**`config.json`** (nøkler og nåverdier):
```
backtracks_dir   C:\Users\krist\Videos\Wardogs\02-shorts
extra_source_dirs ["C:\Users\krist\Videos\WARDOGS\01-raw"]
clips_dir        C:\Users\krist\Videos\Wardogs\05-auto-clips
title_prefix / description / tags / category_id 20
privacy          "public"          (sett "private" for manuell publisering fra iPad igjen)
publish_times    ["17:00","21:00"] (lokal tid)
max_per_run      6                 (YouTube-kvote 10 000/dag ≈ 1 600 per opplasting)
min_age_seconds  120
killclip         {fps 2, pre 12, post 4, gap 12, min 18, max 40}
min_score 0, min_kills 2, min_vehicles 1
dedup_seconds 5, queue_max_age_days 21, fallback_single_when_empty true, analytics_tuning true
varsling         "msgbox"
cleanup          {uploaded_clip_days 7, source_days 14}
_forklaring      fritekst som forklarer reglene
```

**`state.json`** – `uploaded{}`, `failed{}`, `duplicate{}`, `expired{}`, `last_publish_at`, `veh_weight`. 11 opplastinger per 16.09 (10 private fra natta + 1 planlagt til 16.09 17:00: `ZbFnWbVLzLc`, 5 kills/1 vehicle, men mangler åpningen – se kap. 6).
**`processed.json`** – kildefil → `{clips, at}` eller `{error, at}`. Nullstilt 16.09 av 7-klipp.
**`run_daily.log`**, **`auth.log`** – logger.

---

## 4. Hvordan filene lages og legges på mini fra Cowork

Dette har vært den største praktiske fallgruven, så følg det slavisk:

1. Kildene ligger i Cowork-scratchpad `…/scratchpad/pkg/` og kopieres til `/mnt/user-data/outputs/auto-clips/`. **Ny samtale har ikke disse** – hent gjeldende filer fra mini først: `device_stage_files` på `C:\Users\krist\Videos\Wardogs\auto-clips\<fil>` og les dem.
2. Rediger lokalt i Cowork (Python-patch-skript med `assert old in s` fungerte best; kjør `python3 -c "import ast; ast.parse(...)"` etterpå).
3. **Lever alltid med `SendUserFile` først**, ta `file_uuid`, og skriv til mini med `device_commit_files` med `fileUuid` (ikke `stagedPath` – den har skrevet gamle kopier flere ganger). Bruk `force: true`. Verifiser størrelse med `device_list_dir`.
4. Cmd-filer: `sed -i 's/$/\r/'` for CRLF; `>` i echo må være `^>`; unngå `for /r` uten jokertegn (falske treff) – bruk `dir /s /b`.
5. Kristoffer kjører cmd-filer selv (computer-use-terminaler på mini er klikk-only; device_bash-VM har ikke virket på mini). Han sender skjermbilder av vinduet.
6. Testing uten mini: `scratchpad/ddtest/` – falske klipp med sidecar-json + `yt_upload.py --dry` for å verifisere dedup/kø.

---

## 5. Viktige Windows/ffmpeg/YouTube-lærdommer

- ffmpeg 9 har fjernet `-vsync` → bruk `-fps_mode passthrough`.
- Tesseract-output må leses som UTF-8 med `errors="replace"` (cp1252-krasj ellers).
- killclip logger til stderr og skriver JSON til stdout – run_daily parser fra `stdout.index("{")` (ellers «-1 klipp»).
- `Register-ScheduledTask` ga Access denied uten eksplisitt `-User`/`-Principal` og admin.
- 403 `accessNotConfigured` = YouTube Data API ikke aktivert i prosjektet (tre netter feilet stille før 16.09).
- 400 `uploadLimitExceeded` = kanalens daglige grense (rullerende døgn); løst ved å aktivere avanserte funksjoner i Studio (legitimasjon).
- Uverifiserte OAuth-apper: Google kan låse API-opplastinger til privat – men `private + publishAt` (planlagt) gikk gjennom 16.09. Hold øye med at planlagte videoer faktisk går offentlig; hvis ikke → YouTube API Services audit-skjema (1–3 uker).
- Studio-innstillingen «standard synlighet» gjelder bare manuelle opplastinger, ikke API.
- Shorts-statistikk fra kanalen: 20–39 s klipp tar av, 45 s+ dør. Publiser 17:00 og 21:00.
- Enkeltkills er kjedelige (Kristoffers vurdering) → regelen multikill ELLER vehicle.
- Kill-feed-teksten henger noen sekunder etter selve killet; treff ved sekund 0 i en fil betyr at killet skjedde **før** fila startet.

---

## 6. Status og åpne punkter per 16.09 kl 08:30

**Kjører:** nattjobb 04:00; første planlagte offentlige short 16.09 kl 17:00 (`ZbFnWbVLzLc`). Kristoffer kan slette den i Studio før 17:00 hvis han vil bytte (mangler åpnings-multikillet fordi backtrack-bufferen startet for sent).

**Gjenstår hos Kristoffer:**
- OBS → Settings → General → **«Automatically record when streaming»** (Recording Path er allerede `01-raw`).
- Eventuelt lengre Aitum backtrack-buffer (3–5 min).
- La `7-klipp-alt-paa-nytt.cmd` bli ferdig (startet 16.09 ~08:15), deretter `5-kjor-naa` med 0 for å se dedup + kø.

**Neste utviklingsideer (ikke bestilt):**
- Kompilering: 3 enkeltkills → én short (forskes på; Kristoffer var positiv).
- Verifisere HUD-sonen for infantry (recon/assault) med et klipp fra kompis/fetter – trengs før KillFeed.exe sendes ut.
- Pilot-events («DELIVERED»), lyd-topper, statusside.
- Følge opp om planlagte videoer faktisk blir offentlige (ellers API-audit).

---

## 7. Playbook-rutinen (egen sak i samme samtale)

Planlagt Cowork-oppgave «WARDOGS playbook – daglig oppdatering (med Reddit via Chrome)» oppdaterer artefakten <https://claude.ai/code/artifact/bcd6e4f1-c638-4aea-8b8c-0b3b7229744b> (Duo-playbook, v16 publisert 13.09). Regler: Reddit **bare** via Chrome og **old.reddit.com** (`/r/WarDogs/top/?t=day` + search, `limit=100`; new reddit gir 3 innlegg; JS-output begrenses til ~1000 tegn → hent ID-er via regex). **Aldri** Discord-eksport/tokens/automatisering (Kristoffer ble bannet for det). Varsle med PushNotification bare når noe er nytt.

---

## 8. Kristoffers preferanser i denne typen arbeid

- Aldri `AskUserQuestion`-kortet; spør i klartekst med **a)**, **b)**, **c)** … + fritekst; binære spørsmål som én setning. Han svarer med bokstaver («abc» = flere).
- Norsk, kort, konkret. Han vil at cmd-filer forklarer seg selv øverst.
- Målet er «så smart og selvgående som mulig» – null manuelle steg.
- Bruk `/logg` (Supabase) ved start av arbeid og når noe landes.

---

## 9. KillFeed som produkt (alfa)

- Navn **KillFeed** (WDAC forkastet). Lukket alfa/beta til kompis + fetter (recon/assault, ikke heli). Ingen innlogging i appen; brukeren får 9:16-klipp i en mappe og laster opp selv.
- `build_onefile.cmd` → `dist\KillFeed.exe` (~130 MB, bundler ffmpeg + Tesseract + watermark). `KillFeed-alpha.zip` (onedir) finnes også. `LES_MEG_ALFA.txt` følger med.
- Støtter 16:9-input (senter-crop/blur) så Aitum-plugin ikke er nødvendig for brukerne.
- Salg senere via merchant of record (Lemon Squeezy/Paddle) med **LEQ AS**, ikke leq.no-butikken. Krever kodesigneringssertifikat + domene.
- Opplasting/planlegging holdes **utenfor** exe-en (krever Google-innlogging per bruker + app-verifisering).

---

## 10. Orienteringsguide for en ny Claude: slik forstår du alt på 10 minutter

Les i denne rekkefølgen. Hvert steg svarer på ett spørsmål, og du trenger ikke gå videre før spørsmålet er besvart.

### Steg 0 – Hva er bestemt før? (2 min)
Kjør `/logg` og hent radene med prosjekt `killfeed` (pluss `generelt`-rader med tag `wardogs`/`youtube`). Radene forteller *hvorfor* ting er som de er (multikill-regel, dedup via klokketid, planlagt publisering, ikke Discord-automatisering). Ikke foreslå noe loggen viser er forkastet uten å si at forutsetningene har endret seg.

### Steg 1 – Er mini tilgjengelig, og hva ligger der? (1 min)
`get_device_info` → bekreft at `C:\Users\krist\Videos\Wardogs` er koblet. Er den ikke, be Kristoffer trykke «Add folder» og velge den. Deretter `device_list_dir` på `…\Wardogs\auto-clips`. Sammenlign filstørrelser/mtime med tabellen i kap. 3 – avviker noe stort, er filene endret etter dette dokumentet, og du må lese dem før du rører dem.

### Steg 2 – Hva er *tilstanden* akkurat nå? (3 min)
Stage og les tre filer, i denne rekkefølgen:
1. **`config.json`** – reglene. Se spesielt `privacy`, `publish_times`, `max_per_run`, `min_kills/min_vehicles`, `extra_source_dirs`. `_forklaring` er skrevet for mennesker og oppsummerer alt.
2. **`state.json`** – hva som er gjort. `uploaded` = alt som ligger på YouTube (nøkkel = klippfilnavn, verdi har `id`, `publishAt`, `abs_events`). `duplicate`/`expired` = det som aldri skal lastes opp. `failed` = prøves igjen. `last_publish_at` = hvor køen står. `veh_weight` = hva læringen har landet på (default 4).
3. **`run_daily.log`** (de siste ~100 linjene) – hva som skjedde sist natt. Linjer å se etter: `Steg 1/2: N nye…`, `OK <fil>: n klipp`, `Dedup: …`, `Utlopt: …`, `Koen er tom`, `-> [score …]`, `OK https://youtube.com/shorts/… (YouTube svarte: …)`, `Ryddet: …`, `Varsel vist (msgbox)`. `FEIL`/`ADVARSEL` er alltid verdt å lese.

Nå vet du: hva som er regelen, hva som er lastet opp, og om siste kjøring gikk bra.

### Steg 3 – Hvordan henger koden sammen? (3 min)
Les i denne rekkefølgen, og bare så dypt som oppgaven krever:
1. `run_daily.py` (ca. 100 linjer) – orkestreringen. Etter denne vet du at alt er tre steg: klipp → last opp → rydd, og at problemer samles til én msgbox.
2. `yt_upload.py` `main()` – utvalget. Følg `files` gjennom filtrene i rekkefølge: ikke opplastet → gammel nok → regel (`ok()`) → dedup → utløp → fallback → læring/sortering → kø-slots → opplasting. Hvert filter skriver én linje til loggen, så loggen og koden leses parallelt.
3. `killclip.py` – bare hvis oppgaven gjelder *deteksjon eller klipping* (ROI-soner, cluster-parametre, tittel). Nøkkelfunksjoner: `rois_for`, `detect`, `cluster`, `cut`, `_run`.
4. `killfeed_app.py` / `build_*.cmd` – bare for KillFeed-alfaen.

### Steg 4 – Hva vil Kristoffer? (les kap. 8)
Han vil ha null manuelle steg. Når du foreslår noe, spør deg først: «gjør dette pipelinen mer selvgående, eller legger det til et trykk?» Spør med **a)/b)/c)**-lister i klartekst, aldri med spørsmålskort.

### Steg 5 – Slik verifiserer du at pipelinen er frisk (uten å endre noe)
- `state.uploaded` har fått nye poster siden forrige natt **eller** loggen sier «Koen er tom».
- Siste `publishAt` i `state.uploaded` ligger i framtida og slottene er 17:00/21:00 lokal tid (15:00Z/19:00Z sommertid, 16:00Z/20:00Z vintertid).
- Ingen `FEIL` i loggen fra siste kjøring. `failed` i state er tom eller bare gamle poster.
- Studio → Innhold: planlagte videoer står som «Planlagt», og de som har passert publiseringstiden står som «Offentlig». Står de fortsatt som «Privat» etter tida → uverifisert-app-låsen slo inn → API-audit (kap. 5).
- `05-auto-clips` vokser ikke ubegrenset (ryddingen kjører), og `01-raw`/`02-shorts` ryddes 14 dager etter klipping.

### Steg 6 – Slik gjør du en endring trygt
1. Stage og les **gjeldende** fil fra mini (ikke stol på gamle kopier).
2. Patch med Python (`assert old in s` før `replace`) og syntaks-sjekk med `ast.parse`.
3. Test logikk uten mini der det går: lag en `ddtest/`-mappe med falske klipp + sidecar-json og kjør `yt_upload.py --dry` (config med `clips_dir` mot testmappa, `min_age_seconds: 0`).
4. `SendUserFile` → `device_commit_files` med `fileUuid` og `force: true` → `device_list_dir` for å bekrefte størrelse.
5. Be Kristoffer kjøre riktig cmd (kap. 3-tabellen) og sende skjermbilde; les feilmeldingen bokstavelig – de tre vanligste er listet i kap. 5.
6. Logg beslutningen med `/logg` (prosjekt `killfeed`).

### Steg 7 – Vanlige spørsmål og hvor svaret ligger
| Spørsmål | Se |
|---|---|
| «Hvorfor ble ikke klipp X lastet opp?» | `state.duplicate`/`expired`, deretter sidecar-json (`kills`, `vehicles`, `clamped_start`), deretter loggens `Dedup:`/`Utlopt:`-linjer |
| «Hvorfor er klippet feil sted / for kort / for langt?» | `killclip.cluster` + `config.killclip`; `clamped_start` = fila startet midt i action |
| «Hvorfor gikk det ikke offentlig?» | `state.uploaded[x].privacy/publishAt`, loggens «YouTube svarte», kap. 5 om uverifisert app |
| «Ingen kills funnet i en fil» | ROI-sonene i `rois_for` passer ikke oppløsning/HUD – test med `killclip.py <fil> <ut> --dry` og se på `<fil>-auto.json` (`hits`) |
| «Nattjobben kjørte ikke» | Task Scheduler «WARDOGS auto-clips» (historikk), `run_daily.log` mangler dato; 4-installer-nattjobb som admin |
| «Hva skal kompisen få?» | Kap. 9, `build_onefile.cmd`, `LES_MEG_ALFA.txt` |
