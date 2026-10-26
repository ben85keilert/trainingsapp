# Architektur

## Die eine Regel

> `core/`, `data/` und `devices/` importieren **niemals** `flet`.
> Nichts unter `trainingsapp/` importiert **jemals** `scipy`.

`tests/test_import_regel.py` erzwingt das. Zwei Gründe:

1. **Testbarkeit.** Die gesamte Domäne — Datenmodell, HRV-Mathematik, Regeln,
   Sensorprotokolle — läuft ohne Oberfläche. 81 Tests brauchen keinen Bildschirm.
2. **Flet-Versionswechsel bleiben lokal.** Flet hat seine API zwischen 0.28,
   0.80 und 1.0 mehrfach umgebaut und bietet mit `@ft.component` zusätzlich ein
   deklaratives Modell an. Steckt Logik in `ui/`, zieht sich jede Umstellung
   durch die halbe Anwendung. So bleibt sie lokal — beim Umstieg von 0.86 auf
   1.0 musste außerhalb von `ui/` und dem Lernpfad keine Zeile geändert werden.

`scipy` ist gesondert verboten, weil es auf Android und iOS schlicht nicht
existiert — `pypi.flet.dev` liefert numpy und pandas, aber kein scipy. Ein
`import scipy` fiele sonst erst beim Bauen der App auf.

---

## Aufbau

```
src/trainingsapp/
├─ config.py      Edition, Funktionsschalter, Speicherorte
├─ core/          Domäne — Modelle, Notation, Limit-Regeln, Einheiten
├─ data/          SQLite, Migrationen, Repositories, Seed-Daten
├─ devices/       Sensor-Port, Geräteprofile, Simulator, BLE
└─ ui/            Flet — dünn, keine Rechenlogik
../hrv-core/src/hrv_core/   HRV-Mathematik und das Austauschformat raw-v1 (Schwesterrepo)
```

**hrv-core** (github `ben85keilert/hrv-core`) ist seit dem 16.10.2026 die gemeinsame
HRV-Bibliothek von praxis_gui und trainingsapp: Konstanten, Artefaktkorrektur,
Zeit-/Frequenzbereich, nichtlineare Maße, Atmung, PPI-Zuordnung, Live-Fenster,
Aufnahme, Notizen, Abschnitte, Verlaufskurven — alles, was in beiden Apps dieselben
Zahlen liefern muss. Sie liegt als Schwesterordner `../hrv-core` und ist editierbar
eingebunden (`[tool.uv.sources]` für uv, `[tool.flet.dev_packages]` für `flet build`;
die CI checkt beide Repos nebeneinander aus). Golden-Tests und Algorithmendoku liegen
dort. In der App bleiben nur Anwendungsteile mit HRV-Bezug: `core/hrv_export.py`
(ZIP-Export, Diagnoseprotokoll), `core/hrv_training.py` (HRV je Kilometer, DFA-Überblick),
`core/hrv_ansicht.py`/`hrv_einstellungen.py`, `devices/messlauf.py`.

Abhängigkeiten zeigen **nur nach innen**:

```
ui  →  core, data, hrv_core, devices
devices  →  hrv_core, core      (core nur für GPS-Punkte: core.strecke)
data  →  core
core  →  (nur hrv_core)       (core/hrv_export.py, core/hrv_training.py)
hrv_core  →  (nur numpy)      (extern, Schwesterrepo hrv-core)
```

---

## Speicherung: die Datei ist die Wahrheit

HRV-Rohdaten liegen **nicht** in der Datenbank, sondern als `raw-v1`-JSON-Dateien —
byte-kompatibel zu praxis_gui. Die Datenbank hält nur den Verweis
(`hrv_recording.file_path`) und einen Kennzahlen-Cache (`hrv_metrics_cache`).

Der Grund ist nicht Größe. Eine Stunde bei 70 bpm sind rund 4200 Schläge; bei
20 Sitzungen im Monat wären das etwa eine Million Zeilen im Jahr — das schafft
SQLite mühelos. Ausschlaggebend ist:

- Der Kompatibilitätsvertrag hinge sonst an einer Übersetzungsschicht, die
  auseinanderdriften kann. So ist Export ein Dateikopiervorgang.
- Während der Live-Messung wäre es ein `INSERT` pro Herzschlag, gleichzeitig zu
  Rechnen und Zeichnen. Eine Datei alle 15 Sekunden atomar zu schreiben ist
  robuster gegen Absturz und leeren Akku.
- Jede Neuanalyse müsste 4200 Zeilen wieder zu einem numpy-Array zusammenbauen.

Der Cache trägt eine `algo_version`. Ändert sich die Rechenvorschrift, gilt er
als veraltet und wird aus den Dateien neu berechnet — die Rohdaten bleiben
unangetastet.

---

## Sensoren

`devices/base.py` definiert einen **pull-basierten** Port:

```python
async def scan(timeout) -> list[DeviceInfo]
async def connect(device_id) / async def disconnect()
def stream()  -> AsyncIterator[Messwert | PpiPaket]   # Messwerte (+ Verity-Rohpakete)
def status()  -> AsyncIterator[DeviceStatus]  # Batterie, Kontakt, Verbindung
```

Dahinter passen drei sehr verschiedene Dinge — bleak auf dem Desktop, eine
Flet-Extension auf Mobilgeräten, ein Simulator. Alle drei *pushen*; der Konsument
will *pullen*. Dazwischen liegt eine `asyncio.Queue` mit Obergrenze.

**Messwerte und Status laufen getrennt.** Batteriemeldungen dürfen den
RR-Strom nicht verstopfen.

### Der kritische Pfad: BLE auf Mobilgeräten

`bleak` deckt Windows, macOS und Linux ab. Sein Android-Backend setzt
`python-for-android` voraus — Flet baut aber mit `serious_python`. Auf iOS gibt
es gar nichts. Und eine fertige Flet-BLE-Extension existiert nicht.

Also bauen wir eine: die Flet-Extension `flet_ble` um `flutter_blue_plus`, die
auf Android und iOS läuft. Sie bleibt bewusst dumm — suchen, verbinden, koppeln,
Dienste, lesen, schreiben, abonnieren — und reicht nur **rohe Bytes** samt
Empfangszeit durch. Das Polar-Protokoll (0x2A37, PMD/PPI, Antwortprüfung,
Watchdog) wird **in Python geparst** (`devices/pmd.py`, `devices/polar.py`) und
ist so ohne Gerät testbar; die Naht dazwischen ist `devices/gatt.BleTransport`.
Dazu gehört der **Foreground Service** — ohne ihn beendet Android die Messung im
Hintergrund. `flet-permission-handler` deckt das nicht ab.

Das wird früh als Spike geprüft (L02b), nicht erst wenn viel darauf aufbaut.

### Töne: eine zweite, kleine Erweiterung

Der Timer piept (Countdown, Abschnittswechsel, Ende). `flet-audio` hätte das
gekonnt, übernimmt aber den Audiokontext-Standard von audioplayers: Android
`AUDIOFOCUS_GAIN`, Nutzung „Medien". Jeder Piep nähme Musik-Apps den Fokus
dauerhaft — wer zur Musik trainiert, hätte nach dem ersten Signal Stille.
`erweiterungen/flet_ton` (Dart, audioplayers) fordert den Fokus nur kurz und
duckend an (`AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK`, Nutzung „Sonifikation"): Die
Musik wird für den Ton leiser und spielt weiter. Die Klänge erzeugt
`core/klang.py` als WAV-Bytes — keine Asset-Dateien, die `flet run` und
`flet build` an verschiedenen Orten suchten. Wie `flet_ble` gibt es den Dienst
nur in der gebauten App; am Rechner bleibt der Timer still.


### Uhr am Handgelenk: Mediensteuerung aus dem Schwesterrepo hrv-watch

Die Galaxy Fit3 nimmt keine eigene App an, zeigt aber Titel, Interpret und Album einer
`MediaSession` des Handys (Befund hrv-watch/docs/TESTPLAN_fit3.md, 26.10.2026). Also werden
die drei Zeilen zum Textkanal: `core/uhr_seiten.py` baut aus `hrv_core.live.LiveKennzahlen`
und dem HF-Verlauf geräteunabhängige Seiten (HF mit Tendenz, RMSSD, Gipfel und Tal des
Intervalls, RR, DFA α1 aus `LiveFenster.dfa_a1` alle 5 s bei EKG-Gurten), `ui/geraete/flet_medien_kanal.py` schickt jede Sekunde die aktuelle Seite —
nur bei Änderung, denn jede setzt am Band die Laufschrift zurück — über die Flet-Erweiterung
`flet_medien` (Python + Dart + Java, `MediaSession` ohne androidx) aus `../hrv-watch`. Tasten
vom Band: ▶ ◀ blättern, ⏯ setzt eine Marke in die Aufnahme, **nie** startet oder stoppt es sie
(Ben, 26.10.2026). Schalter: Einstellungen → HRV-Messung → „Uhr am Handgelenk“.

Die trainingsapp kennt damit Kanäle, keine Uhren: Uhren-Apps (später Wear OS) und das
Gerätewissen liegen in hrv-watch (ENTSCHEIDUNGEN #6 dort). Eingebunden wie hrv-core als
Schwesterordner (`[tool.uv.sources]`, `[tool.flet.dev_packages]`, `hrv-watch.ref` für CI und APK).

### Der Sensor-Prüfstand

Ob ein Gerät RR-Intervalle sendet, steht in Bit 4 des Flags-Bytes — und ist bei
Uhren von Modell und Firmware abhängig, ohne verlässliche Dokumentation.

Statt Herstellerangaben zu glauben, misst die App nach: verbinden, zehn Sekunden
aufzeichnen, Flags auswerten, RR pro Paket zählen, Drift zwischen Herzuhr und
Wanduhr prüfen. Das Ergebnis stuft das Gerät ein (`profil_verfeinern`) und
landet in der Tabelle `device`.

So wächst die Kompatibilitätsliste empirisch mit jedem Patienten.

---

## Datenqualitätsstufen

Verfügbarkeit schlägt Präzision: die wenigsten Patienten haben einen Brustgurt.
Deshalb wird alles aufgezeichnet — aber gekennzeichnet.

| Stufe | Quelle | HRV |
|---|---|---|
| `rr_ekg` | Brustgurt (RR aus EKG) | vollständig |
| `ppi_optisch` | optischer Sensor, Polar-Uhr | vollständig, Schwelle 0.30, Frequenzwerte mit Vorbehalt |
| `bpm_only` | Uhr sendet nur Herzfrequenz | keine HRV, nur Pulsverlauf |

Die Stufe wird abgeleitet, wenn sie nicht ausdrücklich gesetzt ist
(`Recording.effektive_qualitaet()`) — enthält eine Messung keinen einzigen
RR-Wert, ist sie `bpm_only`, egal was das Geräteprofil versprochen hat.

---

## Zwei Editionen aus einem Quelltext

`config.py` kennt die Edition und beantwortet Fragen der Form
„darf ich synchronisieren?" statt „bin ich Edition B?".

| Funktion | solo | praxis |
|---|---|---|
| `hrv_rohdaten`, `export` | ✓ | ✓ |
| `sync`, `nachrichten`, `zugewiesene_plaene` | – | ✓ |
| `physiologische_steuerung` | – | ✓ |

Der letzte Punkt ist rechtlich begründet, nicht technisch: eine App, die aus
Messwerten eine Handlungsempfehlung ableitet, trifft eine medizinische Aussage.
Siehe `docs/recht/00_zweckbestimmung.md`.

Die Synchronisationsfelder (`outbox`, `external_ref`, `origin_device_id`,
`deleted_at`) existieren ab der ersten Migration, obwohl Edition A sie nicht
nutzt — sie nachträglich einzuführen wäre eine Migration über den gesamten
Bestand.

### Konflikte vermeiden statt auflösen

`hrv_recording` und `session_entry` sind **unveränderlich**. Eine Korrektur
entsteht als neuer Eintrag, der den alten über `replaces_entry_id` ersetzt.
Damit gibt es nichts, was zwei Geräte gleichzeitig ändern könnten — Konflikte
sind strukturell ausgeschlossen.

Nur veränderliche Metadaten (Notiz, Übungsdefinition) brauchen eine Auflösung.
Dort gilt „letzter Schreiber gewinnt" mit einer **serverseitig vergebenen**
Revision — Client-Zeitstempel taugen dafür nicht, weil Uhren auseinanderlaufen.

Statt eines `dirty`-Flags gibt es eine `outbox`: reihenfolgetreu, Wiederholung
ist trivial, und Ausstehendes findet sich ohne Full-Table-Scan.

---

## Medien

Erklärvideos werden **nicht** ins App-Paket gelegt. Google Play deckelt das
Basis-APK bei 150 MB; wenige Minuten Video sprengen das. Sie werden bei Bedarf
geladen und gecacht (`exercise_media.source = 'url'`).

Selbst aufgenommene Fotos und Videos liegen im app-privaten Verzeichnis
(Scoped Storage), erreichbar über `config.medienverzeichnis()`.
