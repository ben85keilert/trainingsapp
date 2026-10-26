# Planung: GPS-Tracking für Ausdauersport (14.10.2026)

Bens Auftrag: Laufen (später Radfahren, Gehen) mit GPS aufzeichnen und auf einer
OpenStreetMap-Karte zeigen — **gleichzeitig mit der HRV-Messung**. Gründlich
planen, das **Herunterladen der Karte vorbereiten**, keine GPS-Daten teilen,
DFA α1 als Überblick (ohne Empfehlung), Strom sparen. Zielgerät: Pixel 10.

Stand 14.10.2026: **Phasen 0–4 gebaut** (Abschnitt 8); Phase 5 (Offline-Karte)
offen. Quellen am Ende (Abschnitt 11); was ich selbst gerechnet
oder geschätzt habe, steht kursiv.

---

## 0. Verbindliche Regel: GPS-Daten werden nicht geteilt

> **Werden später Daten geteilt — Synchronisation mit der Praxis-Edition,
> Export-ZIP, Teilen-Menü, Diagnose —, dann niemals GPS-Daten.**
> (Ben, 14.10.2026)

Was das für den Bau heißt:

- **Eigener Ordner.** Strecken liegen unter `<Datenverzeichnis>/Strecken/`, nie
  unter `Messungen/`. Grund: praxis_gui liest und synchronisiert die
  `Messungen`-Ordner, und der Export (`hrv_core/export.zugehoerige_dateien`)
  packt jede Datei mit dem Präfix `sensor_<ts>_` ins ZIP — eine
  `sensor_<ts>_gps.gpx` daneben ginge beim Teilen mit.
- **Keine Koordinaten** in raw-v1, im Sidecar `_analyzed.json`, in Notiztexten
  (auch nicht in den automatischen „km 3"-Notizen), im Diagnoseprotokoll, in
  synchronisierten Datenbankfeldern (`outbox`).
- **Ortsfreie Werte dürfen mit:** Distanz, Dauer, Tempo, Höhenmeter je km,
  Herzfrequenz je km — sie verraten keinen Ort. Start, Ziel und Route nicht.
- **Export der eigenen Strecke** ist erlaubt (Ben, 14.10.2026) — aber nur als
  ausdrückliche Handlung der Person („GPX exportieren"), nie automatisch, nie
  im Messungs-Export, in der Synchronisation oder im Diagnoseprotokoll.
  Formate: Abschnitt 5b.
- **Ein Test sichert es ab:** Export-ZIP und Sync-Outbox einer Messung mit
  Strecke enthalten keine Koordinate.
- **Zur Entscheidung (26.10.2026, P80):** Bewegungsdaten ohne Ort (Tempo, Distanz
  alle 5 s) im Messungs-Export immer dabei, die Strecke mit Koordinaten nur per Häkchen
  je Export — das wäre eine Lockerung dieser Regel. Plan: `docs/plan_export_gps.md`.
- **Forschungsexport einer Einheit** (17.10.2026, `docs/plan_einheit.md` §8):
  ausdrücklich ausgelöst; aus der Strecke nur das Tempo als 5-s-Mittel — keine
  Ortung, keine Richtung, keine Höhenreihe, nicht die Datei. Ebenfalls per Test.
- **Die Karte ist die eine Stelle, an der etwas nach außen geht** (Entscheidung 1,
  Online-Kacheln): Sie lädt Kacheln von `tile.openstreetmap.org`, und damit gehen
  grobe Kachelkoordinaten (bei Zoom 16/17 einige hundert Meter) an deren Server —
  jede Sekunde nachgeführt, solange die Karte zu sehen ist. Nicht die Strecke,
  nicht die genaue Position. Seit 15.10.2026: Schalter „Karte zeigen“ im Training
  (`AppState.ausdauer_karte`), ein **einmaliger** Hinweis beim ersten Training mit
  Karte (`SettingRepo.HINWEIS_KARTE`, nicht je Aufzeichnung — Ben), ausführlich
  später in der Hilfe, Kapitel GPS/Kartenaufzeichnung. Offline-Kacheln: Phase 5.

---

## 1. Was am Ende da sein soll

**Während des Laufs** (große Zahlen, wenig Text):

- Zeit, Distanz, Tempo (aktuell und Ø), Herzfrequenz, optional DFA α1
- kleine Karte mit Strecke und Position (antippen → groß)
- Signal je Kilometer (Ton über `flet_ton`, Vibration) und automatische Notiz
  „km 3" in der HRV-Aufnahme → daraus **Abschnitte je km** (gibt es schon)
- Auto-Pause bei Stillstand, Display darf aus sein
- eine Benachrichtigung „Training läuft · 5,2 km · 32:10 · HF 148"

**Danach** (Aufzeichnung):

- Karte mit Strecke (optional nach Herzfrequenz oder Tempo eingefärbt)
- Tabelle je km: Zeit, Tempo, Ø HF, DFA α1, Höhenmeter
- Kurven HF, Tempo, DFA α1 über die Zeit (die vorhandenen Verlaufskurven)
- **DFA-α1-Überblick** (Abschnitt 6) — beschreibend
- Eintrag im Trainingstagebuch: Übung „Laufen" mit Strecke und Dauer (Felder
  `distance`/`duration` gibt es im Feldvorrat) → Tagesansicht und Verlauf
  zeigen die Kilometer je Tag
- **Laufband/Halle:** dasselbe ohne GPS (nur Zeit und HRV) — kein Strom fürs GPS

---

## 2. Bausteine — was es schon gibt (am Quelltext geprüft)

| Baustein | Paket | Was es kann | Grenze |
|---|---|---|---|
| **Karte** | `flet-map` 1.0.4 (flutter_map 8.3, BSD-3) | Kachelschicht, Linien, Marker, Namensnennung, Kamera; seit flutter_map 8.2 **eingebauter Kachel-Zwischenspeicher** (an, ~1 GB, das System darf ihn leeren) | Kacheln nur per URL (`NetworkTileProvider` fest eingebaut) — **keine Vektorkacheln, kein echtes Offline** |
| **GPS** | `flet-geolocator` 1.0.4 (geolocator 14.0.2) | Positionsstrom; Android: Genauigkeit, **Intervall** (Vorgabe 5 s), Mindestabstand, Höhe über NN (EGM2008), eigene Vordergrund-Benachrichtigung | **keine Bündelung** (`setMaxUpdateDelayMillis`), kein Barometer |
| **Hintergrund** | unser `MessDienst` (flet_ble) | Vordergrunddienst mit Wake-Lock, Typ `connectedDevice` | für GPS zusätzlich Typ `location` |
| **HRV** | Messlauf, LiveFenster, DFA α1 je Fenster | alles da | DFA α1 nur mit EKG-Gurt |
| **Abschnitte** | `hrv_core/ausschnitte.py` | aus Notizen, Werte je Abschnitt | — |
| **Töne** | `flet_ton` | Signal je km | — |

**Größe:** flutter_map, latlong2 und geolocator sind Dart- bzw. kleine
Java-Pakete — *zusammen grob 2–4 MB*. Seit 14.10. baut die App nur für arm64
(Build 71: **85 statt 225 MB**); die Karte fällt daneben nicht ins Gewicht.
`flet-video` bleibt (Ben braucht es).

**Android-Regeln** (Android 14–16), am Plan ausgerichtet:

- Vordergrunddienst Typ `location` braucht die Berechtigung
  `FOREGROUND_SERVICE_LOCATION` im Manifest **— die tragen wir selbst ein**
  (geolocator_android 5.1.1 hat sie wieder entfernt) — und eine erteilte
  Standortberechtigung.
- Er muss starten, **während die App sichtbar ist** (Knopf „Start") — dann
  braucht es **kein** `ACCESS_BACKGROUND_LOCATION`: Der laufende Dienst behält
  den Zugriff, auch bei Display aus.
- Mehrere Typen in einem Dienst sind erlaubt (`connectedDevice|location`); der
  Typ beim Start muss eine Teilmenge des Manifests sein.
- Für den Play Store später: Typ-Erklärung mit Video; Training gehört dort
  unter `health` (braucht `ACTIVITY_RECOGNITION` bzw. ab Android 16 die
  Health-Berechtigung für die Herzfrequenz). Für die APK vorerst unwichtig.

---

## 3. Architektur

Die eine Regel gilt weiter: `core/`, `data/`, `hrv_core/`, `devices/` ohne
Flet. GPS-Rechnung ist reine Mathematik und gehört nach unten.

```
devices/gps.py          Port GpsQuelle (pull, wie HeartRateSource) + GpxWiedergabe
                        (Simulator: spielt eine Strecke ab — Tests, Web-Vorschau)
core/strecke.py         Punkt, Strecke, Filter, Distanz, Tempo, Splits, Auto-Pause,
                        Höhenmeter mit Hysterese — ohne Oberfläche, mit Doctests
data/strecken.py        Datei schreiben/lesen (GPX 1.1 + Crash-Backup .jsonl mit Kopfzeile),
                        Tabelle `strecke` (Migration), Ordner Strecken/
data/karten.py          Kartenquellen (URL, Namensnennung, User-Agent, ob offline
                        erlaubt, Höchstmenge je Download), Gebietsrechnung
                        (Kacheln für Ausschnitt oder Korridor, Größe) — Abschnitt 5
ui/geraete/flet_gps.py  Adapter flet-geolocator → GpsQuelle (wie FletBleTransport)
ui/views/ausdauer.py    Live-Ansicht und Auswertung (seit 26.10. direkt im Reiter
                        „Messung → GPS“, `ausdauer_inhalt`; die Seite /ausdauer bleibt
                        für die Startleiste — /training gehört dem Einzeltraining);
                        ui/components/karte_strecke.py
```

**Zeitbasis.** GPS-Punkte tragen UTC-Zeitstempel und die monotone
Empfangszeit; die HRV-Aufnahme hat `start_utc` + Wanduhr je Schlag. Beides
verbindet die Wanduhr — HF und DFA α1 je km entstehen so, ohne dass die
Strecke in die HRV-Datei muss (Regel 0).

**Verknüpfung.** Ein Training = Session im Tagebuch (Übung „Laufen") +
optional HRV-Aufnahme + optional Strecke; verbunden über IDs in der Datenbank,
nicht über Dateinamen im selben Ordner.

**Eine Benachrichtigung.** `MessDienst` bekommt
`foregroundServiceType="connectedDevice|location"` und startet mit den Typen,
die gerade laufen (Gurt, GPS oder beides). geolocator bekommt **keine** eigene
Benachrichtigung — sonst stünden zwei da. Die Android-Doku sagt, dass der
laufende Dienst den Standortzugriff erhält; die geolocator-Anleitung behauptet
anderes — **das klärt der Vorab-Test** (Abschnitt 8). Rückfall: die
Benachrichtigung von geolocator.

---

## 4. Rechnung (core/strecke.py)

Vorbild sind die Vorgaben von OpenTracks (Open Source, bewährt):

- **Genauigkeit:** Punkte mit geschätzter Genauigkeit schlechter als ~30 m
  verwerfen (OpenTracks: 50 m) — Startphase, Häuserschluchten.
- **Sprünge:** mehr als 200 m zwischen zwei Punkten → neues Teilstück (Naht),
  keine Strecke dazwischen.
- **Stillstand:** 10 s ohne Bewegung → Auto-Pause (Gesamtzeit läuft weiter,
  Bewegungszeit nicht).
- **Erst glätten, dann summieren** (gleitender Median über 3–5 Punkte oder ein
  einfacher Kalman-Filter) — sonst zählt das GPS-Zittern im Stand als Strecke;
  genau dieser Fehler stand im Changelog eines Flutter-Plugins. Beim **Gehen**
  (1,4 m/s) ist das Zittern so groß wie der Schritt je Sekunde: Im Simulator
  mit 3 m weißem Rauschen ergaben 36 m Weg roh 117 m, mit 5-m-Schritt 76 m, mit
  10-m-Schritt 36 m und aus dem Doppler-Tempo 35 m. Echtes GPS zittert
  zeitlich glatter — welche Variante trägt, zeigt der Vorabtest.
- **Distanz:** Haversine zwischen geglätteten Punkten.
- **Höhenmeter:** GPS-Höhe ist grob — nur Änderungen über eine Hysterese
  (3–5 m) zählen. Ein Barometer bräuchte eine eigene Erweiterung → später.
- **Splits:** je km (Rad: je 5 km), Tempo min/km, Ø HF und DFA α1 je Split
  über die Wanduhr der HRV-Aufnahme.

Alles testbar mit aufgezeichneten bzw. erzeugten Strecken (`GpxWiedergabe`).

---

## 5. Karte — online sofort, Offline-Download vorbereitet

### Online (Phase 2)

OSM-Standardkacheln (`tile.openstreetmap.org`) sind für unsere Nutzung
erlaubt, wenn wir uns an die Regeln halten:

- eigener, eindeutiger **User-Agent** (`user_agent_package_name =
  "de.praxisebert.trainingsassistent"`) — der Flet-Vorgabewert `unknown` wird
  blockiert;
- **Namensnennung sichtbar** auf der Karte (`SimpleAttribution`; die
  ausklappende `RichAttribution` versteckt sie — das verbietet die Regel);
- **Zwischenspeicher** nach den Cache-Headern des Servers — das erledigt der
  eingebaute Speicher von flutter_map; kein eigener Aufwand.

Ohne Netz zeigt die Karte, was zuletzt im Zwischenspeicher lag; die
**Aufzeichnung selbst braucht nie Netz** — die Strecke ist gespeichert und
erscheint auf der Karte, sobald Kacheln da sind.

### Offline — was erlaubt ist und was nicht

**Von `tile.openstreetmap.org` ist Offline-Nutzung ausdrücklich verboten**
(„Download city/country for offline use" — und auch das Bauen von
`.mbtiles`-Archiven). Wer es tut, wird ohne Warnung gesperrt. Es braucht also
eine andere Quelle:

| Quelle | Art | Offline erlaubt? | Kosten |
|---|---|---|---|
| **OpenFreeMap** | Vektor (OpenMapTiles) | ja, bis 3 000 Kacheln/50 MB je Download, ≤ 4 Anfragen gleichzeitig | kostenlos, auch kommerziell |
| **Protomaps** (PMTiles) | Vektor | ja — Planet-Datei (ODbL) frei, Ausschnitt per `pmtiles extract` | kostenlos; *eigenes Hosting eines Ausschnitts (z. B. Deutschland) wenige €/Monat* |
| Thunderforest | Raster | Zwischenspeicher fürs Gerät ja; Gebiets-Download erst im Business-Tarif | 255 $/Monat |
| Stadia | Raster/Vektor | nur mit Abo, ≤ 100 MB je Gerät; Gratis-Tarif nicht kommerziell | Abo |
| MapTiler Cloud | beides | nur vorübergehender Speicher, kein Massen-Download | — |

**Größe:** Vektorkacheln sind klein — ein Berliner Ausschnitt (~1 700 km²,
Zoom 0–15) hat 84 MB, *ein Gebiet von 20 × 20 km also grob 20 MB*. Raster wäre
für dasselbe Gebiet *100–400 MB* (Zoom 12–17; Stadtkacheln bis 50 KB).

**Der Haken:** flet-map kann keine Vektorkacheln. Dafür braucht es eine
**eigene Karten-Erweiterung** (wie `flet_ble`): flutter_map + `vector_map_tiles`
(BSD-3; für flutter_map 8 vorerst nur als Beta) + PMTiles-Leser
(`flutter_map_pmtiles`/`vector_map_tiles_pmtiles`, MIT). Die verbreitete
Offline-Bibliothek FMTC ist **GPL-3** — für die Solo-Edition (AGPL) möglich,
für die kommerzielle Praxis-Edition nur mit gekaufter Lizenz → meiden.

### Was jetzt schon vorbereitet wird (Phase 1, ohne Entscheidung)

- `data/karten.py`: **Kartenquelle** als Datensatz (URL-Vorlage, Art Raster
  oder Vektor, Namensnennung, User-Agent, `offline_erlaubt`, Höchstmenge je
  Download, Parallelität) — OSM eingetragen mit `offline_erlaubt=False`, damit
  der Download-Knopf dort gar nicht erst erscheint.
- **Gebietsrechnung**: Kacheln für einen Ausschnitt oder einen **Korridor um
  gelaufene Strecken** (±500 m — viel kleiner als ein Rechteck), Zahl und
  geschätzte Größe je Zoomstufe, Aufteilung in erlaubte Portionen (OpenFreeMap:
  ≤ 3 000 Kacheln je Download).
- **Speicherort** `<Datenverzeichnis>/Karten/` (getrennt von Strecken und
  Messungen; Karten enthalten keine persönlichen Daten, aber die Wahl des
  Gebiets verrät den Wohnort → ebenfalls nicht teilen).

So ist der Download später nur noch: Quelle wählen → Gebiet → laden → die
Karten-Erweiterung zeigt die Datei an.

### 5b. Export — Standardformate

| Format | Was drin steht | Wer es liest |
|---|---|---|
| **GPX 1.1** (gebaut) | Strecke, Höhe, Zeit; Herzfrequenz über Garmins `TrackPointExtension`; Sportart nur als freies Feld `<type>` | praktisch alle: Strava, Komoot, Garmin Connect, OsmAnd, Google Earth |
| TCX (Garmin Training Center) | dazu Runden und Sportart (nur Running/Biking/Other) | Strava, Garmin Connect, TrainingPeaks |
| FIT (Garmin, binär) | alles, auch **RR-Intervalle** | Garmin Connect, Strava, intervals.icu, Runalyze — die beiden letzten rechnen aus den RR-Intervallen DFA α1 |
| GeoJSON, KML | nur Geometrie | Karten- und GIS-Programme, nicht für Sport-Apps |

Vorgabe: **GPX 1.1 mit Herzfrequenz** — es deckt fast alles ab. FIT lohnt
sich später, wenn die RR-Intervalle mit sollen (Auswertung in intervals.icu
oder Runalyze). TCX bringt gegenüber GPX nur die Runden.

---

## 6. DFA α1 — Überblick ohne Empfehlung

**Was gezeigt wird** — wie in den bekannten Apps (FatMaxxer, alphaHRV,
Runalyze):

- DFA α1 als Verlaufskurve: 2-min-Fenster, alle 5 s neu gerechnet (die
  Kennzahl gibt es, Schrittweite anpassen);
- Wert je km/Abschnitt;
- **Artefaktanteil je Fenster**, Fenster mit **≥ 3 % korrigierten Schlägen
  grau** und ohne Wert in den Zusammenfassungen (ab 6 % verfälschen Artefakte
  α1 um bis zu 19 %);
- **Zeit je Wertebereich** (z. B. über 1,0 · 0,75–1,0 · 0,5–0,75 · unter
  0,5), neutral beschriftet — keine Begriffe wie „aerob/anaerob", keine
  Zielbereiche, keine Hinweise wie „langsamer laufen".

**Grenzen, die die App nennt** (Info-Text, beschreibend):

- Nur mit **EKG-Gurt** (H10). Für optische Pulsintervalle gibt es unter
  Belastung keine Validierung („basically no relationship" bei der Verity) —
  bei der Verity bleibt α1 aus.
- Auch der H10 streut bei hoher Belastung deutlich (Übereinstimmung mit dem
  EKG +58/−41 %); der Wert ist ein **Schätzwert**.
- Ermüdung verschiebt α1 (in Studien um ~12 bpm bei der zugehörigen HF).

In der Literatur werden α1 ≈ 0,75 und ≈ 0,5 mit den ventilatorischen
Schwellen in Verbindung gebracht — mit breiter Streuung (Übereinstimmung
±11–13 bpm, je nach Studie mehr). **Das steht in der Doku, nicht in der App**:
In der App wäre es der erste Schritt zur Empfehlung, und eine
Intensitätsempfehlung aus Messwerten ist `physiologische_steuerung` — in der
Solo-Edition gesperrt (`docs/recht/00_zweckbestimmung.md`). Die
Praxis-Edition kann Schwellen später freischalten.

---

## 7. Strom sparen — macht ein GPS-Intervall von 3–10 s einen Unterschied?

**Kurz: wenig — solange das Display an ist, fast gar nicht.**

- **Größenordnungen** (Googles Modellwerte fürs Pixel 9; fürs Pixel 10 nicht
  veröffentlicht): GPS 19–104 mW (starkes/schwaches Signal), Display
  0,36–2,1 W (minimale/maximale Helligkeit). *Das Display braucht 5- bis
  20-mal so viel wie das GPS.*
- **Unter ~10 s bleibt der GPS-Empfänger an** (Android schaltet erst ab 10 s
  Intervall zwischen den Ortungen ab; ein Neustart dauert ~5 s). 1 s → 3 s
  spart am GPS also wenig, nur etwas Prozessor- und Python-Arbeit.
- **Bündeln** (Ortungen sammeln, seltener aufwachen) bietet geolocator nicht an
  — und der H10 weckt den Prozessor ohnehin jede Sekunde.
- **Dual-Band-GPS** (L1+L5, Pixel 10) kostet am Chip ~2 mW mehr — vernachlässigbar.

**Was dagegen kostet — Genauigkeit:** *Bei 12 km/h (3,33 m/s) verliert eine
90°-Ecke bei 1 s 0,6 m, bei 5 s 3,1 m, bei 10 s 6,3 m; ein Bogen mit 20 m
Radius wird bei 5 s um 2,9 %, bei 10 s um 11 % zu kurz.* Studien fanden bei
1 Hz auf kurvigen Kursen bis 11 % zu wenig.

**Vorschlag:**

| Stufe | Intervall | für |
|---|---|---|
| **Genau (Vorgabe)** | 1 s | Laufen, Rad, Intervalle |
| Sparsam | 10 s | lange Wanderungen — der Empfänger darf zwischendurch schlafen |
| Ohne GPS | — | Laufband, Halle, Gymnastik |

**Die echten Hebel:** Display aus (die Benachrichtigung zeigt Zeit, Distanz,
HF; der km-Ton meldet sich), Karte nur zeichnen, wenn sie sichtbar ist,
Oberfläche höchstens 1×/s auffrischen, im Hintergrund gar nicht; dunkles Design
hilft nur bei hoher Helligkeit (−39 bis −47 % bei 100 %, bei 30–50 % nur
3–9 %). **Selbst messen** (Phase 0): 30 min mit 1 s gegen 10 s, Display aus —
eine aktuelle Messung „1 s gegen 5 s" hat die Recherche nicht gefunden.

---

## 8. Phasen und Aufwand

| Phase | Inhalt | Aufwand |
|---|---|---|
| 0 · Vorab-Test (APK) | **gebaut 14.10.:** Einstellungen → GPS-Test. Strecke (1/3/10 s, Karte, Bildschirm an/aus) und **Dauertest 30 min** (15 min 1 s, 15 min 3/5/10 s; Genauigkeit je 5 min, Strom aus dem Ladestandsmesser); Bericht ohne Orte; GPX-Export | ½–1 Tag + Ben am Pixel |
| 1 · Kern | **gebaut 14.10.:** `core/strecke.StreckenRechner` (10-m-Schritt, Sprünge, Auto-Pause, Splits, Höhe), `devices/gps.PunktWiedergabe`, Tabelle `strecke` (Migration 012), Ordner `Strecken/`, Regel-0-Test (`tests/test_ausdauer.py`), `data/karten.py` | 1½ Tage |
| 2 · Live | **gebaut 14.10.:** `/ausdauer` — Sportart, mit/ohne GPS, große Zahlen, Karte, Auto-Pause, km-Ton, Vibration und Notiz „km N" (wird Abschnitt), Benachrichtigung, HRV-Aufnahme läuft mit | 1½ Tage |
| 3 · Aufzeichnung | **gebaut 14.10.:** `/ausdauer/<id>` — Karte (eingepasst, Start/Ziel), km-Tabelle mit Ø HF und DFA α1, GPX-Export mit Herzfrequenz, Tagebucheintrag (Übung „Gehen"/„Laufen"/„Radfahren"), Liste unter Messung → Aufzeichnungen | 1 Tag |
| 4 · DFA-α1-Überblick | **gebaut 14.10.:** 2-min-Fenster alle 5 s, Fenster mit ≥ 3 % korrigierten Schlägen leer, Zeit je Wertebereich (neutral), Werte je km — nur mit EKG-Gurt | ½ Tag |
| 5 · Karte offline | eigene Karten-Erweiterung (Vektor, PMTiles), Gebiet laden | 3–5 Tage, nach Entscheidung |

Phasen 0–4: **etwa 5–6 Arbeitstage**. Phase 5 kommt dazu, wenn offline
gewünscht ist.

---

## 9. Entscheidungen

Ben, 14.10.2026:

1. **Karte:** vorerst nur der Zwischenspeicher von flutter_map (OSM online,
   gesehene Gegenden auch offline). Vektor-Erweiterung (Phase 5) später.
2. **Export:** ja — GPX 1.1 auf ausdrücklichen Knopfdruck (Abschnitt 0, 5b).
3. **Sportarten in dieser Reihenfolge:** **Gehen → Laufen → Rad.** Gehen zuerst
   heißt: Das GPS-Zittern ist so groß wie der Schritt — die Distanzrechnung
   (Mindestabstand oder Doppler-Tempo, Abschnitt 4) muss beim Gehen stimmen;
   der Vorabtest misst genau das.
4. **Ablauf:** erst der Vorabtest am Pixel, dann Phasen 1–4 in einem Zug.

Noch offen:

- **Eigene Kachelquelle** (Protomaps-Ausschnitt) — erst mit Phase 5.
- **DFA-α1-Wertebereiche** für die Übersicht (neutral) — die vorgeschlagenen?
- **Play Store** später: Vordergrunddienst als `health` statt `location`.

---

## 9a. Vorabtest: Ergebnisse

Berichte ohne Orte, von Ben am Pixel 10.

**1 · Strecke, Gehen, GPS 1 s, 14.10.2026 13:45** (5 min, Bildschirm an, 1 %
im Hintergrund; wahre Länge laut Karte **etwa 252 m**)

| | |
|---|---|
| Ortungen | 285, Abstand Median 1,0 s, 95 % 1,4 s, längste Lücke 2,1 s, keine Lücke |
| erste Ortung | nach 0,1 s, schon ≤ 20 m (Empfänger war warm) |
| Genauigkeit | Median 3,1 m, 90 % 4,3 m, nie über 30 m |
| Stand (2:08 min) | Zittern roh 4,7 m/min, mit 5-m-Schritt 0,0 m/min |
| Gehen (~2:51 min) | Tempo Median 1,37 m/s (4,9 km/h) |
| Distanz (wahr ~252 m) | roh 271 m (+8 %) · ≤ 30 m 271 m · 5-m-Schritt 258 m (+2 %) · **10-m-Schritt 251 m (±0 %)** · Doppler 224 m (−11 %) |
| Höhe | roh 2,9/3,4 m auf/ab, mit 3-m-Schwelle 0/0 m (flach) |
| Akku | 720 mA — das ganze Handy mit Bildschirm an und Karte, nicht das GPS allein |

**Befunde:**

- Echtes GPS zittert beim Gehen viel weniger als der Simulator (dort 3 m
  weißes Rauschen: roh 117 statt 36 m). Hier liegen die Positionsrechnungen
  dicht beieinander (271 → 258 → 251 m), und das Zittern im Stand
  verschwindet schon mit dem 5-m-Schritt.
- Gegen die wahre Länge (~252 m, auf der Karte nachgemessen) trifft der
  **10-m-Schritt** (251 m), der 5-m-Schritt liegt 2 % darüber, roh 8 %
  darüber. Die Tempo-Rechnung (Doppler) liegt 11 % darunter.
- **Vorläufig fürs Gehen:** Positionen mit 10-m-Schritt (wie OpenTracks),
  Ortungen über 30 m Ungenauigkeit verworfen. Ein einzelner, flacher Weg —
  der Gang mit ausgeschaltetem Bildschirm prüft es nach.

**2 · Akkutest, 14.10.2026 13:54** (4 × 15 min; Ben war unterwegs: je Phase
5–9 min Stand, sonst Gehen; die App 86–98 % im Hintergrund)

| | GPS 1 s | GPS 3 s | GPS 10 s | ohne GPS |
|---|---|---|---|---|
| Ortungen | 784 (87 %) | 282 | 89 | – |
| Abstand 95 % / längste Lücke | 1,9 s / 7,7 s (2 Lücken) | 4,6 s / 7,4 s | 14,6 s / 15,9 s | – |
| Genauigkeit Median / 90 % | 3,0 / 11,2 m | 3,4 / 7,4 m | **7,3** / 14,7 m | – |
| Distanz roh · 5 m · 10 m · Doppler | 830 · 736 · 674 · 649 m | 696 · 585 · 549 · 545 m | 743 · 646 · 586 · 633 m | – |
| Zittern im Stand roh / 5-m-Schritt | 7,9 / 6,0 m/min | 10,7 / 4,1 m/min | 10,8 / 11,0 m/min | – |
| Höhe auf/ab roh · 3 m · 5 m | 76/73 · 34/29 · 18/17 m | 15/18 · 0/3 · 0/0 m | 19/18 · 9/9 · 5/5 m | – |
| Strom (Ladestandsmesser) | 430 mA | 530 mA | 540 mA | 480 mA |

**Befunde:**

- **Strom: nicht auswertbar.** Ohne GPS zog das Handy 480 mA (rund 11 %/h);
  die Phasen mit GPS lagen 50 mA darunter bis 60 mA darüber. Was das GPS
  kostet (erwartet 5–25 mA), geht darin unter — die Nutzung des Handys
  bestimmt den Verbrauch. Offen: War der Bildschirm an? Wenn nicht, verbraucht
  die App im Hintergrund zu viel (prüfen, bevor Phase 2 steht).
- **Hintergrund geht:** mit dem Vordergrunddienst (Typ location) kamen bei 3 s
  und 10 s alle Ortungen, bei 1 s 87 % mit zwei Lücken bis 7,7 s.
- **10 s ist ungenauer:** Median 7,3 statt 3,0 m — der Empfänger schläft
  zwischen den Ortungen. Für Strecken taugt das nicht.
- **10-m-Schritt bestätigt:** Er liegt bei 1 s und 3 s auf 4 % beim
  Doppler-Tempo; roh liegt 20–27 % darüber. Im Stand (teils drinnen,
  90 % Genauigkeit bis 11 m) ließ der 5-m-Schritt noch 4–6 m/min Zittern durch.
- **Höhe nur in Bewegung zählen:** Im Stand kamen roh 76 m Anstieg in 15 min
  zusammen, mit 5-m-Schwelle noch 18 m. Höhenmeter also nur bei Bewegung und
  mit 5-m-Schwelle; besser später das Barometer des Pixel.

**Vorschlag:** GPS 1 s als einzige Stufe (plus „ohne GPS“); „Sparsam 10 s“
erst, wenn ein sauberer Akkutest einen Gewinn zeigt (Handy liegt still am
Fenster, Bildschirm aus, unbenutzt).

**Noch offen:** der Gang mit ausgeschaltetem Bildschirm (macht Ben selbst).

**Entschieden (Ben, 14.10.2026):** GPS im Sekundentakt — keine Sparstufe. Statt
eines weiteren Akkutests über eine Stunde gibt es den **Dauertest (30 min)**:
15 min 1 s, dann 15 min seltener, nebenher beim Laufen; er zeigt, ob die
Genauigkeit bei längerem GPS nachlässt (Median je 5 min), und den Strom.

**Nach dem Bau aufgefallen:**

- Die Höhe wird vor der 5-m-Schwelle über 15 Ortungen geglättet (Median) —
  simuliert, 10 min ebenerdig mit 3 m Rauschen: ohne Median 431 m „Anstieg",
  mit 15 keiner; ein echter Anstieg von 30 m bleibt 33 m.
- **Verity Sense beim Training:** Die App startet sie weiter im PPI-Modus — dort
  bleibt ihre Herzfrequenz bei Bewegung stehen. Die Ansicht rät deshalb zum
  H10. Ein HF-Modus ohne PPI fürs Training braucht einen Test am Gerät
  (PPI stoppen, danach wieder starten) — noch offen.

---

## 10. Was dabei sonst noch auffiel

- `flet-map` setzt `user_agent_package_name` standardmäßig auf `unknown` — wer
  es vergisst, bekommt von OSM Sperrkacheln.
- geolocator verlangt in seiner Anleitung `ACCESS_BACKGROUND_LOCATION`; die
  Android-Doku sagt, mit Vordergrunddienst nicht — wir folgen Android und
  prüfen es im Vorab-Test (die Hintergrund-Berechtigung ist im Play Store
  schwer zu bekommen).
- **Verity Sense beim Sport ohne PPI starten** (14.10., Polar SDK): Im
  PPI-Modus kommt ihre Herzfrequenz nur alle 5 s und bleibt bei Bewegung auf
  dem letzten verlässlichen Wert stehen. Der Messlauf startet bei der Verity
  heute immer PPI; für Gehen/Laufen/Rad braucht es den HF-Modus (nur
  `0x2A37`). Ohne Intervalle gibt es dann kein DFA α1, das bleibt ohnehin
  dem H10 vorbehalten (Abschnitt 6). Begründung: `docs/korrektur.md`.

---

## 10a. Nachträge aus der Durchsicht (15.10.2026)

- **Kopfzeile in der Streckendatei.** Die erste Zeile der `.jsonl` ist
  `{"kopf": {"schema": "strecke-v1", "sportart", "subject_id", "started_at"}}` —
  keine Koordinate. Grund: Die Zeile `strecke` entstand nur beim Stoppen; tötete
  Android den Prozess, lag die Datei verwaist. Jetzt findet `AppState.starten`
  solche Dateien (`data.strecken.verwaiste`), und die App bietet beim Start
  „Übernehmen“ (Strecke, Zeit, Tagebuch aus der Datei) oder „Löschen“ an
  (Ben: erkennen und anbieten, nicht still). Alte Dateien ohne Kopf bleiben lesbar.
- **Tempo 0 heißt „fehlt“.** flet_geolocator meldet ein nicht verfügbares Tempo
  als 0 (Android) oder negativ (iOS). Ein Tempo zählt nur mit positiver
  Tempogenauigkeit (`speed_accuracy`); ohne Tempo schätzt der Rechner Bewegung
  aus Weg je Zeit seit dem Bezugspunkt — die 10-m-Schritte zählen weiter, Stillstand
  zieht den Bezug dann nicht nach (Zittern bleibt unter 10 m). Vorher blieb die
  Strecke auf solchen Geräten für immer 0. Am Pixel 10 (liefert Tempo) ändert sich
  nichts; andere Geräte: am Gerät prüfen (Katalog T-Eintrag).
- **Fehler sind sichtbar.** GPS-Fehler (`quelle.meldung`), ein nicht gestarteter
  Vordergrunddienst und Schreibfehler stehen während des Trainings in roter Schrift
  unter den Zahlen (seit 17.10. `StreckeBaustein.warnung` bzw. die Warnung der
  Einheit); der Empfangs-Task stirbt nicht mehr still. Scheitert der Start, bleibt
  nichts zurück.
- **Als Einheit (17.10.2026, `docs/plan_einheit.md`, Stufe 2).** Das Training ist ein
  Teil der Einheit (`devices/strecke_baustein.StreckeBaustein`, flet-frei): bereitstellen
  — das GPS sucht schon Empfang —, mit Timer (Intervalle) und HRV gemeinsam starten.
  Die Kilometer stehen jetzt **zur Split-Zeit** in der Messung (vorher zur
  Verarbeitungszeit, bis zu einem Takt später) und auf eigener Spur `km`, die
  Timer-Abschnitte schneiden sie nicht. „km 1“ ist der erste Kilometer — vorher hieß
  der Abschnitt nach der Notiz „km 1“, also der zweite, schon „km 1“. Eine HRV, die
  schon lief, wird verknüpft und läuft weiter (`strecke.einheit_id`, Migration 019);
  die Auswertung legt Ortungen und Schläge über die Versätze der Einheit aufeinander.

## 11. Quellen

OSM-Regeln: https://operations.osmfoundation.org/policies/tiles/ ·
https://operations.osmfoundation.org/policies/vector/ ·
https://docs.fleaflet.dev/tile-servers/using-openstreetmap-direct ·
flutter_map-Cache: https://docs.fleaflet.dev/layers/tile-layer/caching ·
OpenFreeMap: https://openfreemap.org/tos/ · Protomaps:
https://docs.protomaps.com/basemaps/downloads ,
https://docs.protomaps.com/pmtiles/cli ,
https://pyviz-tutorial.readthedocs.io/en/latest/protomaps/extract.html ·
Thunderforest: https://www.thunderforest.com/terms/ · Stadia:
https://stadiamaps.com/pricing/ · MapTiler: https://www.maptiler.com/terms/cloud/ ·
FMTC: https://pub.dev/packages/flutter_map_tile_caching ·
Kachelgrößen: https://geofabrik.de/maps/tile-packages.html

Strom: https://developer.android.com/develop/sensors-and-location/location/battery ·
GnssLocationProvider (10-s-Schwelle):
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/location/gnss/GnssLocationProvider.java ·
Pixel-9-Modellwerte:
https://android.googlesource.com/device/google/caimito/+/refs/heads/main/tokay/overlay/frameworks/base/core/res/res/xml/power_profile.xml ·
Dual-Band: https://www.eenewseurope.com/en/7nm-gnss-receiver-for-wearables-cuts-power-by-5x/ ·
Dunkles Design: https://www.purdue.edu/newsroom/releases/2021/Q3/dark-mode-may-not-save-your-phones-battery-life-as-much-as-you-think,-but-there-are-a-few-silver-linings.html

Android-Hintergrund: https://developer.android.com/develop/background-work/services/fgs/service-types ·
https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start ·
https://developer.android.com/develop/sensors-and-location/location/permissions ·
https://developer.android.com/about/versions/14/changes/fgs-types-required ·
geolocator: https://github.com/Baseflow/flutter-geolocator/blob/main/geolocator_android/CHANGELOG.md

DFA α1: VT1 https://doi.org/10.3389/fphys.2020.596567 · VT2
https://doi.org/10.3390/jfmk6020038 · Frauen https://doi.org/10.1007/s00421-022-05050-x ·
Übersicht https://doi.org/10.1186/s40798-023-00607-2 · Ermüdung
https://doi.org/10.1080/02640414.2023.2277034 · Artefakte
https://doi.org/10.3390/s21030821 · H10 gegen EKG https://doi.org/10.3390/s22176536 ·
Optisch: http://www.muscleoxygentraining.com/2025/09/optical-ppg-and-dfa-a1-intriguing-look.html ·
Apps: https://doi.org/10.3389/fphys.2022.879071

GPS-Genauigkeit: https://doi.org/10.1123/ijspp.5.4.448 ·
https://arxiv.org/abs/1504.04504 · OpenTracks-Vorgaben:
https://github.com/OpenTracksApp/OpenTracks/blob/main/src/main/res/values/settings.xml
