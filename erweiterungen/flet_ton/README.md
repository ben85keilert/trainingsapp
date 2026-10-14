# flet-ton

Flet-Erweiterung (Flet ≥ 1.0.3) für die trainingsapp: **kurze Signaltöne** (Timer:
Countdown, Abschnittswechsel, Ende) als Flet-Service über `audioplayers`.

Warum nicht `flet-audio`? Das nutzt den Audiokontext-Standard von audioplayers: Android
`AUDIOFOCUS_GAIN`, Nutzung „Medien". Jeder Piep nähme Musik-Apps den Audiofokus dauerhaft —
Spotify & Co. hielten beim ersten Signal an. `flet_ton` fordert den Fokus nur kurz und
duckend an (`AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK`, Nutzung „Sonifikation"): Laufende Musik
wird für den Ton leiser und spielt danach weiter.

- Flutter-Seite: `src/flutter/flet_ton` (Service `FletTonService`, Paket `audioplayers`)
- Python-Seite: `src/flet_ton` (`FletTon`, ein `ft.Service`)

```python
from flet_ton import FletTon, verfuegbar

if verfuegbar(page):                 # nur in der gebauten App (Android)
    ton = FletTon()                  # in main(page) anlegen, Referenz behalten!
    page.services.append(ton)
    await ton.laden("piep", wav_bytes)   # einmal: WAV als Bytes
    await ton.spielen("piep")            # beliebig oft, sofort (Quelle bleibt geladen)
    await ton.spielen("piep", 0.6, "wecker")   # 60 % der Weckerlautstärke
```

**Lautstärkeregler** (`quelle`, nur Android): `medien` (Vorgabe — Medienlautstärke, die
die Lautstärketasten in der App regeln; mit Kopfhörern kommt der Ton dort an), `wecker`
(Weckerlautstärke, immer auch über den Lautsprecher) oder `klingelton` (Nutzung
„Sonifikation" → Klingelton-/Systemlautstärke; bis 14.10.2026 die einzige Wahl). Der
Fokus bleibt in allen Fällen kurz und duckend. `lautstaerke` ist ein Anteil des Reglers.
iOS kennt für Apps nur einen Regler; dort gilt `ambient` (mischt mit Musik, schweigt bei
Stummschalter) — und die Erweiterung ist bisher nur für Android gebaut (`verfuegbar`).

Stolperfallen (wie bei flet_ble):

- **Referenz halten.** Flet entfernt Dienste, auf die in Python niemand mehr zeigt.
- **Nur in der gebauten App.** `flet run` (Desktop, Web, Flet-App am Handy) kennt den
  Dart-Teil nicht; Aufrufe scheitern dort nach einer Frist. `verfuegbar(page)` prüft das.
- Töne gehen als Base64 über die Brücke (WAV, wenige KB) und liegen danach im Spieler.
