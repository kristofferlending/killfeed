# WARDOGS auto-clips – oppsett på mini

Pakka ligger i `Videos\Wardogs\auto-clips\`. Flyten hver natt kl. 04:00 (og 20 min etter pålogging):

1. `run_daily.py` finner nye backtracks i `02-shorts`
2. `killclip.py` leser kill-feeden med OCR og klipper 18–40 s shorts til `05-auto-clips` (+ en `.json` per klipp med hendelser og auto-tittel)
3. `yt_upload.py` laster opp klippene som **private** shorts – du ser gjennom og publiserer fra YouTube Studio-appen på iPad (velg alle → Offentlig)

## Status 13.09.2026
Alt er satt opp: Python 3.12, ffmpeg 9 (i `auto-clips\ffmpeg`), Tesseract 5.5, OAuth (`client_secret.json` + `token.json`), og den planlagte oppgaven «WARDOGS auto-clips» (04:00 daglig + 20 min etter pålogging). Klippetest OK.

## Filene du dobbeltklikker
- `1-installer-tesseract.cmd` – engangsinstallasjon (Python, ffmpeg, Tesseract). Ferdig.
- `2-test-klipping.cmd` – tester klipping på én backtrack.
- `3-auth-youtube.cmd` – YouTube-innlogging (logger til `auth.log`). Ferdig.
- `4-installer-nattjobb.cmd` – registrerer nattjobben (høyreklikk → Kjør som administrator hvis «Access is denied»). Ferdig.
- `5-kjor-naa.cmd` – kjør hele løypa nå (klipp + last opp). Bruk etter en spilleøkt.

## Engangsoppsett (gjort – kun for referanse)

1. **Tesseract** (OCR): installer fra https://github.com/UB-Mannheim/tesseract/wiki (standardsti `C:\Program Files\Tesseract-OCR`). Bare engelsk språkpakke trengs.
2. **ffmpeg** må ligge på PATH (det gjør den allerede for yt2ig).
3. Python-pakker: `pip install google-api-python-client google-auth-oauthlib`
4. **OAuth-klient** – i samme Google Cloud-prosjekt som yt2ig-API-nøkkelen:
   - APIs & Services → Credentials → Create credentials → OAuth client ID → *Desktop app*
   - Last ned JSON, lagre som `client_secret.json` i denne mappa. **Ikke del fila.**
   - OAuth consent screen: legg til Google-kontoen din som *Test user* (så slipper du verifisering).
5. Første innlogging: `python yt_upload.py --auth` – nettleseren åpnes, velg **ThatsBonkers-kanalen** (ikke den personlige) når Google spør. `token.json` lagres og fornyes automatisk.
6. Test uten å laste opp: `python run_daily.py --no-upload --limit 1` → se i `05-auto-clips`
7. Test opplasting: `python yt_upload.py --dry` (viser hva som ville gått opp) og deretter `python yt_upload.py --max 1`
8. Planlagt oppgave: `.\install_task.ps1` i PowerShell

## Viktig å vite

- **Private til du publiserer.** YouTube låser uansett API-opplastinger fra uverifiserte apper til privat, så `privacy` i config kan ikke settes høyere før appen er verifisert. Publisering fra iPad: YouTube Studio → Innhold → filter «Privat» → velg → Synlighet → Offentlig.
- **Kvote:** YouTube Data API gir 10 000 enheter/dag, en opplasting koster ~1 600 → **maks 6 opplastinger per dag** per prosjekt. `max_per_run` står på 10, men skriptet stopper selv ved kvotefeil og tar resten neste natt. Vil du ha mer, søk om økt kvote i Cloud Console (gratis, tar noen dager).
- **Hovedbøker:** `processed.json` (backtracks som er klippet), `state.json` (klipp som er lastet opp). Slett en linje der for å kjøre på nytt. `run_daily.log` viser hva som skjedde.
- **Justering:** `config.json` → `killclip`: `pre`/`post` sekunder rundt hendelser, `gap` for sammenslåing, `min`/`max` klipplengde. Standard: 12 s før, 4 s etter, 18–40 s.
- Titler er automatiske («WARDOGS Little Bird – 2 kills, 1 vehicle destroyed (+$4,625) #shorts»). Endre `title_prefix`/`description`/`tags` i config, eller rediger `.json`-fila ved siden av et klipp før opplasting.
- Klipp uten kills lages ikke. Landinger/leveringer fanges bare hvis spillet viser tekst i samme område (`DELIVERED` er med i mønsteret, men er ikke testet ennå).
- Backtracks som nettopp er skrevet (under 5 min gamle) hoppes over til neste kjøring.
