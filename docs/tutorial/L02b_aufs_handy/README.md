# L02b — Rauchtest: einmal aufs Handy bauen

**Ziel:** Herausfinden, ob die App auf einem echten Gerät läuft — **jetzt**,
solange nichts darauf aufbaut.

Zeit: ein bis zwei Stunden, davon viel Warten beim ersten Build.

---

## Warum das so früh kommt

Diese Lektion baut nichts Neues. Sie klärt eine Frage, deren Antwort viel
verändert, wenn sie „nein" lautet:

**Läuft unsere App überhaupt auf dem Handy — und kommt sie dort an einen
Bluetooth-Sensor?**

Der zweite Teil ist der kritische. Der Verdacht, den wir prüfen:

- `bleak` ist die naheliegende Python-Bibliothek für Bluetooth. Sie unterstützt
  Windows, macOS und Linux. Ihr Android-Rückgrat setzt `python-for-android`
  voraus — Flet baut aber mit `serious_python`. Auf iOS gibt es gar nichts.
- Eine fertige Flet-Bluetooth-Extension existiert nicht. Auch nicht in der
  offiziellen Sammlung `awesome-flet`.

Wenn sich das bestätigt, brauchen wir eine **eigene Flet-Extension** in Dart um
`flutter_blue_plus`. Das ist machbar, aber ein eigenes Vorhaben — und es
entscheidet mit, wie die Live-Messung aufgebaut wird.

Diese Antwort in vier Monaten zu bekommen, wäre teuer. Deshalb jetzt.

---

## 1. Was `flet build` tut

```
Dein Python-Code
      +
CPython-Laufzeit für Android (vorgebaut)
      +
Binäre Pakete als vorgebaute Wheels (numpy …)
      +
Flutter-Hülle
      ↓
    APK
```

Der entscheidende Punkt: **Jedes Paket mit kompiliertem Anteil braucht ein
vorgebautes Wheel für Android.** Flet betreibt dafür einen eigenen Index,
`pypi.flet.dev`.

| Paket | Android/iOS | Folge für uns |
|---|---|---|
| numpy | ✅ | HRV-Mathematik geht |
| pandas | ✅ | |
| cryptography | ✅ | wichtig für Edition B |
| Pillow | ✅ | |
| **scipy** | ❌ | **Welch und Lomb-Scargle selbst bauen** |
| **bleak** | ❌ | Wheel ist reines Python und installiert sich — aber das Android-Backend setzt python-for-android voraus. **Eigene Extension nötig** |

Reines Python (ohne kompilierten Anteil) läuft immer.

---

## 2. Voraussetzungen

```bash
flet doctor
```

Gebraucht werden **JDK 17** und das **Android SDK**. Fehlt etwas, installiert
Flet es beim ersten `flet build` selbst — das dauert dann entsprechend.

---

## 3. Bauen

`flet build` packt das Verzeichnis aus `[tool.flet.app] path` (in
`pyproject.toml`) in die App und startet dort eine `main.py`. Bei uns ist das
`src/` — so wandert das ganze Paket `trainingsapp` mitsamt Migrationen und
Seed-Daten in die APK. `src/main.py` ist nur ein Dreizeiler, der
`trainingsapp.ui.app.main` startet; die Oberfläche bleibt, wo sie ist.

```bash
uv run flet build apk --verbose
```

Der erste Lauf dauert lange (20–40 Minuten sind normal), spätere sind deutlich
schneller. Ergebnis liegt in `build/apk/`.

Kleiner und schneller wird es mit einer Architektur:

```bash
uv run flet build apk --split-per-abi
```

Erzeugt getrennte APKs für `arm64-v8a`, `armeabi-v7a` und `x86_64`. Für ein
modernes Gerät reicht `arm64-v8a`.

> **Seit Flet 0.86:** die 32-Bit-x86-Architektur wird nicht mehr unterstützt.
> Wer sie angibt, bekommt einen Build-Fehler.

---

## 4. Aufs Gerät

**Per Kabel:**

```bash
adb install -r build/apk/trainingsapp.apk
```

Mit `--split-per-abi` steht die Architektur im Dateinamen. Ist `adb` nicht im
PATH: es liegt im Android SDK unter `platform-tools/` (bei einem von Flet
installierten SDK `~/Android/sdk/platform-tools/adb`).

**Ohne Kabel:** APK auf das Handy kopieren, im Dateimanager antippen,
„Installation aus unbekannten Quellen" erlauben.

**Ohne Android-Gerät:** `flet build linux` bzw. `windows` / `macos`. Das prüft
zwar nicht den Mobilteil, aber immerhin das Paketieren.

---

## 5. Der eigentliche Test: Bluetooth

Das Skript `pruefe_ble.py` in diesem Ordner läuft auf Desktop **und** in der
App. Es versucht `bleak` zu importieren und einen Scan zu starten, und meldet
ehrlich, was dabei herauskommt.

Auf dem Desktop:

```bash
uv sync --extra desktop          # installiert zusätzlich bleak
uv run python docs/tutorial/L02b_aufs_handy/pruefe_ble.py
```

Erwartung: Es findet Geräte. Falls du einen Brustgurt oder eine Uhr hast —
Übertragung einschalten und schauen, ob sie auftaucht.

Für den Test auf dem Handy sind zwei Dinge vorübergehend nötig:

1. `pruefe_ble.py` als `src/main.py` einsetzen (das Original vorher
   beiseitelegen).
2. `bleak` in die APK bekommen. `flet build` packt nur `project.dependencies`
   und `tool.flet.<plattform>.dependencies` ein — das Extra `desktop` bleibt
   draußen. Ohne diesen Schritt meldet die App nur `ModuleNotFoundError`, und
   das sagt nichts über die Bibliothek aus. Also in `pyproject.toml`:

   ```toml
   # nur für diesen Test, danach wieder entfernen
   [tool.flet.android]
   dependencies = ["bleak>=0.22"]
   ```

Dann bauen, installieren, starten — die App zeigt das Ergebnis auf dem
Bildschirm.

```bash
mv src/main.py src/main.py.orig
cp docs/tutorial/L02b_aufs_handy/pruefe_ble.py src/main.py
uv run flet build apk --verbose
ls build/site-packages/arm64-v8a | grep bleak   # muss etwas ausgeben
mv src/main.py.orig src/main.py        # danach wieder zurück!
# … und den [tool.flet.android]-Eintrag aus pyproject.toml entfernen
```

**Erwartung: der Import gelingt, der Scan scheitert.** `bleak` ist reines
Python und lässt sich installieren. Sein Android-Backend schaltet es aber nur
frei, wenn die Umgebungsvariable `P4A_BOOTSTRAP` gesetzt ist — das tut
python-for-android, nicht serious_python. Es bleibt bei
`BleakError: Unsupported platform: Android`. Wichtig ist der genaue Wortlaut:
Er belegt, dass es an der Bibliothek liegt, nicht an Berechtigungen oder an
der Paketierung.

Gemessen am 2026-09-14 mit Flet 0.86.5 und Python 3.14.7 auf Android: genau
diese Meldung. numpy und `hrv_core` liefen dabei einwandfrei.

---

## 6. Was du festhalten solltest

Notiere für unser weiteres Vorgehen:

- [ ] APK ist gebaut — Größe? Bauzeit?
- [ ] App startet auf dem Gerät und zeigt die Navigation
- [ ] `import numpy` funktioniert in der App
- [ ] `import bleak` in der App — erwartet: geht (reines Python)
- [ ] `BleakScanner.discover` in der App — welche Meldung genau?
- [ ] BLE-Scan auf dem Desktop — werden Geräte gefunden?
- [ ] Falls vorhanden: taucht dein Sensor/deine Uhr auf?

---

## Stolperfallen

**„Packaging Python app…" hängt scheinbar** — beim ersten Mal normal. Mit
`--verbose` sieht man, dass es weitergeht.

**Kein Java gefunden** — JDK 17 nötig, neuere Versionen machen Probleme.

**„is not a valid Java package name"** — `org` in `pyproject.toml` wird zum
Android-Paketnamen; Bindestriche und andere Sonderzeichen sind dort verboten.

**Kotlin-Syntaxfehler in `build/flutter/…/MainActivity.kt` nach Änderung von
`org`** — Flet erzeugt das Flutter-Projekt in `build/flutter` neu, räumt alte
Dateien aber nicht weg. `rm -rf build/flutter` und neu bauen.

**APK installiert nicht** — „Unbekannte Quellen" erlauben. Bei einer vorher
installierten Version mit anderer Signatur: erst deinstallieren.

**App startet und schließt sofort** — `adb logcat | grep -i python` zeigt den
Python-Fehler.

**Titel liegt unter der Statusleiste** — `page.padding` kennt die Safe Area
des Geräts nicht. Den Inhalt in `ft.SafeArea(content=…)` legen; das kommt in
L03 beim Seitengerüst wieder.

**Berechtigungen fehlen** — Bluetooth-Berechtigungen stehen in `pyproject.toml`
unter `[tool.flet.android.permission]`. Ab Android 12 müssen sie zusätzlich
**zur Laufzeit** abgefragt werden; dafür ist `flet-permission-handler` da.

---

## Weiter

→ **L03: Navigation und Zustand**

Und dann bauen wir M1 — mit dem Wissen, was auf dem Gerät tatsächlich geht.
