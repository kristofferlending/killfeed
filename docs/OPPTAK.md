# Opptaksguide

```
Slik faar du opptak som KillFeed kan bruke

Du trenger ETT av disse. KillFeed leser kill-feeden fra bildet, saa alt som gir en videofil av spillet virker.

OBS Studio (anbefalt, gratis)
  1. Settings -> Output -> Recording: velg mappe (f.eks. Videos\Wardogs\full-format), format MKV,
     encoder NVENC/AMF/QuickSync, kvalitet "High Quality" eller CQP 20.
  2. Settings -> Output -> Replay Buffer: paa, 120 sekunder. Settings -> Hotkeys -> "Save Replay": F9.
     Trykk F9 rett etter et bra oyeblikk -> fila "Replay ... .mkv" havner i mappa.
  3. Vil du ha hele okta: Settings -> General -> "Automatically record when streaming", eller Start Recording.
  Tips: la kill-feeden og HUD-en vaere paa. Ikke skaler ned HUD-en under 100 %.

NVIDIA App / ShadowPlay (Instant Replay)
  Alt+Z -> Instant Replay -> paa, 2 min. Alt+F10 lagrer. Mappe: Videos\Wardogs. Fungerer rett ut av boksen.

Medal
  Medal lagrer klipp i Videos\Medal\WARDOGS. Pek KillFeed dit.

Aitum Vertical (OBS-plugin, 9:16 direkte)
  Gir loddrette backtracks som blir shorts uten beskjaering. Se etter at spillet ligger i 1:1-feltet
  og at kill-teksten under siktet er synlig. NB: den ekte kill-feeden (venstre side) ligger utenfor
  utsnittet, saa avstand/offer hentes fra 16:9-opptak av samme oyeblikk hvis du ogsaa har det.

Steam / Xbox Game Bar
  Win+Alt+G (siste 30 s) eller Win+Alt+R. Mappe: Videos\Captures. Pek KillFeed paa Videos\.

Felles
  - 1080p eller 1440p, 60 fps. 16:9 blir midtutsnitt i shorts; 9:16 gaar rett gjennom.
  - KillFeed venter til spillet er lukket for den klipper (sparer CPU), og til fila er 2 min gammel.
  - Ingenting sendes noe sted. Klippene dine ligger bare hos deg.
```
