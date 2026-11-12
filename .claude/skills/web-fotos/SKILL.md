---
name: web-fotos
description: >-
  Bildschirmfotos und Klicks der trainingsapp ohne Handy — die App läuft als Flet-Web-Server mit eigener Test-Datenbank, ein kopfloses Chromium in Handybreite (412 × 860) fotografiert und klickt über das DevTools-Protokoll. Für alles, was man sehen muss statt rechnen: passt eine Zeile in die Breite, wie sieht ein Blatt aus, was zeigt eine Ansicht nach einem Tipp. Auslöser: „Bildschirmfoto“, „Web-Foto“, „schau dir die Ansicht an“, „passt das in die Breite?“, „prüfe am Bildschirm“, „/web-fotos“ — und von selbst nach Layoutänderungen in `ui/`, bevor „passt“ behauptet wird. Ersetzt keinen Gerätetest (Tastatur, Gesten, Bluetooth, GPS, Kamera).
---

# Web-Fotos der App

Layoutfehler (eine zu breite Knopfzeile, ein abgeschnittenes Blatt) sieht kein Test. Statt zu
überschlagen: die App im Browser rendern, fotografieren, das Bild ansehen. Am 12.11.2026 war
eine Kopfzeile zu breit, die Korrektur wurde erst nur gerechnet — mit diesem Skill ist die
Prüfung ein Befehl.

Alle Skripte liegen in `.claude/skills/web-fotos/scripts/`. Arbeitsordner ist ein Ordner im
**Scratchpad der Sitzung** (hier `$W`), nie im Projekt.

## Ablauf

1. **Testdaten** (vor dem Start, eigene Datenbank — nie Bens echte):
   `uv run python .claude/skills/web-fotos/scripts/daten_beispiel.py $W/daten`
   legt Plan, Einträge mit Notizen, Notizen zum Tag und Tagesfelder an. Für anderes die Datei
   ins Scratchpad kopieren und zuschneiden (`AppState.starten()` mit
   `TRAININGSAPP_DATA_DIR=$W/daten`, dann die Repositories wie in den Tests).
2. **Starten:** `.claude/skills/web-fotos/scripts/starten.sh $W [app-port] [cdp-port]`
   (Vorgabe 8591/9391; bei „Port belegt“ andere nehmen — eine zweite Sitzung fotografiert
   vielleicht gerade). Meldet `bereit: … Breite 412`. Steht dort eine andere Breite, ist die
   Halte-Verbindung nicht da — nicht fotografieren, neu starten.
3. **Fotografieren und klicken** — mehrere Befehle in einem Aufruf:
   `uv run python .claude/skills/web-fotos/scripts/cdp.py <cdp-port> klick 360 810 foto $W/1.png`
   Befehle: `nav`, `frisch`, `klick`, `lang`, `ziehen`, `rollen`, `rollen_bei`, `tippen`,
   `warten`, `foto`, `js` (Kopf von `cdp.py`). **Das Foto mit Read ansehen**, dann erst den
   nächsten Klick setzen: Fotokoordinaten sind Klickkoordinaten, und sie verschieben sich mit
   jedem Layout.
4. **Nach jeder Codeänderung:** `beenden.sh $W`, dann `starten.sh $W` — der Server lädt Code
   nicht neu, alte Fotos zeigten alten Code.
5. **Am Ende:** `.claude/skills/web-fotos/scripts/beenden.sh $W`.

Wegmarken bei 412 × 860: Navigationsleiste unten bei y ≈ 810 (Heute 50, Übungen 154,
Messung 257, Verlauf 360); Reiter einer Ansicht bei y ≈ 78; Zahnrad oben rechts (392, 28).

## Fallen (alle schon einmal passiert)

- **Nie `pkill -f`/`pgrep -f`** mit einem Muster, das in der eigenen Befehlszeile steht — es
  trifft die eigene Shell (Exit 144). Beenden nur über die Ports (`beenden.sh`, `fuser -k`).
- **Breite nur über `halten.py`.** Setzt ein einzelner Aufruf die Breite und trennt sich, hebt
  Chromium sie auf — Flutter layoutet dann auf 500 px, Klicks liegen daneben.
- **`nav` beginnt eine neue Flet-Sitzung** (laufende Einheit weg); `frisch` leert dazu den
  Speicher. Innerhalb der App klicken, wenn der Zustand zählen soll.
- **Nie „zum Neuzeichnen“ irgendwohin tippen** — der Tipp öffnet, was darunter liegt. `foto`
  schickt selbst ein Mausrad-Ereignis, weil kopfloses Chromium sonst das alte Bild liefert;
  im Zweifel zwei Fotos vergleichen (`md5sum`).
- **Hover:** Nach einem Klick stellt `cdp.py` den Zeiger an den Rand; ein Knopf unter dem
  Zeiger sähe sonst „gewählt“ aus.
- **Text tippen:** erst das Feld anklicken, dann `tippen`.
- **FastAPI:** `starten.sh` nimmt `uv run --with "fastapi==0.143.2"` — die neueste verträgt
  flet-web 1.0.3 nicht („openapi_prefix“). Nichts ins `.venv` installieren.
- **Reagiert die Seite nicht mehr** („Receive loop error“ in `$W/server.log`): ein Invoke
  traf ein ersetztes Control — das ist ein Befund an der App, nicht am Werkzeug
  (`ui/flet_absicherung.py`).
- **Schrift** kann kopflos leicht anders umbrechen als am Handy; Dateipfade zeigt `ft.Image`
  im Browser nicht (Bytes schon). Kamera: Chromium läuft mit Fake-Kamera.
- **Eigene Erweiterungen** (flet_ble, flet_hochladen, …) gibt es im Browser nicht — dafür im
  Scratchpad ein eigenes Startskript nach dem Muster von `server.py`, das den Dienst im
  `AppState` durch einen Nachbau ersetzt.

## Was der Skill nicht ersetzt

Bildschirmtastatur (verdeckt sie Felder?), Wischgesten, Zurück-Geste, Android-Leisten,
Bluetooth, GPS, Benachrichtigungen — das bleibt Gerätetest (`docs/offene_fragen.md`,
Abschnitt 2). Im Bericht steht, was am Foto geprüft wurde und was nur am Gerät geht.
