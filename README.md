# KillFeed

Automatiske WARDOGS-shorts og daglige recaps – helt av seg selv.

KillFeed leser kill-feeden i opptakene dine (OCR på fast plass under siktet), klipper 18–40 s
shorts i 9:16 med tittel, deduper samme kill fra flere opptak, og bygger en kronologisk recap
(5–10 min, 16:9) når nok er samlet. Ingen konto, ingen opplasting – klippene havner i en mappe
du synker til telefonen og publiserer derfra.

Samme motor driver to ting:

| Mappe | Hva | Hvem |
|---|---|---|
| `app/` | **KillFeed.exe** – tray-app for venner/kunder (veiviser, overvåking, Publiser/Andre, recap, toast) | alle |
| `pipeline/` | **Nattjobben** på Kristoffers PC – klipper, velger, laster opp til YouTube med planlagt publisering | bare ThatsBonkers |

`app/killclip.py` er felles deteksjon og klipping. `app/kf_core.py` er alt som ikke er GUI
(innstillinger, hovedbok, dedup, utvalg, montasje). `pipeline/` bruker i dag sin egen kopi av
logikken i `yt_upload.py`; planen er å flytte den over på `kf_core` (se `docs/ROADMAP.md`).

## Bygge exe-en

Windows med Python 3.12, Tesseract (UB-Mannheim) i `C:\Program Files\Tesseract-OCR` og
ffmpeg-essentials (gyan.dev) pakket ut i `tools\ffmpeg\` (gitignored; eller i `..\auto-clips\ffmpeg`).

    build\build_onefile.cmd

Gir `dist\KillFeed.exe` (~130 MB, bundler ffmpeg + Tesseract + vannmerke). Første start 5–10 s.

## Kjøre fra kildekode

    pip install pystray pillow winotify
    python app\killfeed_app.py            # GUI + tray
    python app\killfeed_app.py --run      # én runde uten GUI (feilsøking)

Innstillinger, hovedbok og logg ligger i `%APPDATA%\KillFeed\`.

## Teste uten spillet

`tests\test_core.py` lager syntetiske opptak med ekte kill-tekst i sonen, og verifiserer OCR,
dedup, Publiser/Andre, reserve og recap. Trenger ffmpeg og tesseract på PATH (kjører på Linux).

    python tests\test_core.py

## Nattjobben (pipeline/)

Distribueres til `Videos\Wardogs\auto-clips\` sammen med `app\killclip.py`, `config.json`
(fra `config.example.json`), og OAuth-filene som **aldri** skal i git. Cmd-filene 1–7 forklarer
seg selv øverst. Detaljer: `docs/HANDOFF-killfeed-auto-clips.md`.

## Beslutninger

Alle valg (og hvorfor) ligger i beslutningsloggen (Supabase `claude-memory`, prosjekt `killfeed`).
Kortversjon: multikill ELLER vehicle for shorts, dedup på klokketid, planlagt publisering 17/21,
opplasting holdes utenfor exe-en, salg via merchant of record – ikke leq.no-butikken.
