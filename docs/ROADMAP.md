# KillFeed – veikart

Målet: kompisen dobbeltklikker én gang, og deretter dukker ferdige shorts og recaps opp i en mappe
uten at han rører noe. Hak av etter hvert. Oppdatert 16.09.2026.

## 1. Få alfaen til å virke hos Kristoffer

- [x] Kjerne (`kf_core.py`), tray-app, recap, dedup, veiviser
- [ ] Bygg `dist\KillFeed.exe`, start, gå gjennom veiviseren
- [ ] Test på 3–5 backtracks + 2 Replay-filer: Publiser/Andre riktig, duplikat fjernet, toast, «Lag recap nå»
- [ ] Verifiser 16:9-sonen på infantry (Replay 2026-09-12 10-10-10), juster ROI om nødvendig
- [ ] CPU-bruk mens spillet kjører = 0 (pausen virker); klipping starter innen 2 min etter spillet lukkes
- [ ] Autostart: restart PC, ikonet dukker opp uten vindu

## 2. Idiotsikker (før første kompis)

- [ ] Feilmeldinger som sier hva brukeren skal gjøre – aldri traceback
- [ ] Første-kjøring-sjekk: ffmpeg/Tesseract, skriverett, diskplass > 5 GB
- [ ] Synkmappe-låsing (OneDrive/iCloud): skriv til temp, flytt inn – test mot ekte OneDrive
- [ ] Logg-rotasjon (maks 5 MB), rydd `work\` ved oppstart
- [ ] Engelsk i GUI og LES_MEG
- [ ] Ordentlig ikon (.ico) på exe og i tray
- [ ] Auto-oppdatering: versjonssjekk mot GitHub Releases, «Ny versjon» i tray

## 3. Lukket alfa (2–3 personer, 1–2 uker)

- [ ] Kompis + fetter (infantry) får exe + LES_MEG via Discord; krav: tilbakemelding-zip etter første økt
- [ ] Samle oppløsning, opptaksverktøy, HUD-skala, treffsikkerhet; gjør ROI robust for 1080p/1440p/ultrawide
- [ ] Recap-kvalitet: 5 s før / 2 s etter riktig for infantry? Kronologisk uten musikk – fint eller kjedelig?
- [ ] Logg hva de faktisk publiserer → avgjør Pro-innhold

## 4. Klar for fremmede (åpen beta)

- [ ] Kodesignering (Azure Trusted Signing) – uten den skremmer SmartScreen bort folk
- [ ] Nettside, én side: video, last ned, pris, FAQ (killfeed.gg eller under leq.no)
- [ ] GitHub Releases som nedlastingssted; versjon synlig i tray
- [ ] Personvern-tekst: alt lokalt, ingenting sendes – skriv det tydelig
- [ ] Betaling: Lemon Squeezy, lisensnøkkel i appen (offline-signatur, ingen konto). Pro = uten vannmerke, 1440p, egen logo
- [ ] Avklar selger: ENK eller LEQ AS

## 5. Lansering

- [ ] Én demo-short + én recap på ThatsBonkers med «made with KillFeed»
- [ ] Innlegg på r/WarDogs og i PILOTS CHAT – manuelt, aldri automatisert
- [ ] Founder-pris første 2 uker (99 kr), så 199 kr
- [ ] Be Bulkhead om «community tool»-omtale

## 6. Etterpå, når det selger

- [ ] Beat-synk recap til lisensfri musikk (Pro)
- [ ] Flere spill – samme motor, nye soner
- [ ] Flytt nattjobben (`pipeline/`) over på `kf_core`
- [ ] YouTube-opplasting i appen – krever Google-verifisering, vent til det er etterspurt

## Konkurransebildet (16.09.2026)

Medal 9,99 $/mnd (10 M+ MAU, ~18 M$ ARR ≈ 2 % betaler), Eklipse 24,99 $/mnd, Outplayed freemium
med vannmerke, SteelSeries Moments og Insights gratis uten vannmerke. Ingen har hendelsesdeteksjon
for WARDOGS (2,42 M solgte, 428 k samtidige på topp). Vinduet er 3–6 måneder før noen av dem legger
det til gratis – da er det recap, ferdig 9:16 og «virker på gamle opptak» som er igjen å selge.
