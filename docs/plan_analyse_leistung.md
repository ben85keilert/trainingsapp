# Plan: HRV-Analyse ohne Ruckeln

Stand 14.10.2026, umgesetzt (Abschnitt 4). Anlass (Ben): Die Analyse einer Aufzeichnung ist zäh,
besonders wenn man im 1-, 2- oder 10-min-Fenster mit dem Reiter „Frequenz“
durch die Messung wischt. Das Spektrum wird dabei laufend neu gerechnet.

Gemessen am Desktop (i5-8350U), ohne Codeänderung. Am Handy ist alles eher
langsamer. Daten: Bens Verity-Messung vom 14.10. (73 min, 62 % verworfen) und
eine synthetische H10-Messung (70 min, volle Abdeckung, der schlimmere Fall,
weil dort kein Spektrum mangels Abdeckung wegfällt).

---

## 1. Befunde, nach Gewicht

### 1.1 Ereignisflut und Auto-Update (größter Hebel, ohne Mathematik)

- `wischbar` setzt kein `drag_interval` (`ui/components/zeitfenster.py:118`).
  Flet schickt dann **jede** Fingerbewegung als Ereignis nach Python (Vorgabe 0).
- Nach jedem Handler, der selbst kein `update()` aufruft, aktualisiert Flet 1.0
  die ganze Seite (`flet/messaging/session.py`, `after_event` → `__auto_update`).
  Das ist ein Vergleich des ganzen Baums, auch wenn die Drossel gar nicht
  neu gezeichnet hat: 20–30 ms je Ereignis bei 5 min, 70–140 ms bei „Alles“.
- Eine Sekunde Wischen (60 Ereignisse, echte Drossel, Flet-Vergleich danach)
  braucht zum Abarbeiten:

| Messung, Reiter | 2 min | 5 min | „Alles“ |
|---|---|---|---|
| H10, Zeit | 1,4 s | 4,8 s | 18,8 s |
| H10, Frequenz | 1,7 s | 8,0 s | 129 s |
| Verity, Zeit / Frequenz | 0,6–0,7 s | 1,2–1,4 s | 12–15 s |

  Alles über 1 s staut sich: Die Ansicht läuft dem Finger hinterher.

### 1.2 Die Drossel versagt unter Last

`zeichnen_gedrosselt` (`zeitfenster.py:85–89`) merkt sich den **Beginn** des
letzten Neuzeichnens und fasst nichts zusammen. Dauert ein Neuzeichnen länger
als 125 ms, zeichnet jedes wartende Ereignis wieder neu — unter Last gibt es
keine Drossel. Genau das trifft die Startansicht: Die Aufzeichnung öffnet mit
„Alles“ (`ui/views/messung_detail.py:282`), und im Frequenz-Reiter (H10) kostet
dort jedes Neuzeichnen 2–3 s.

### 1.3 Achsenraster des Spektrums

`kurve.y_raster` → `_vielfache` (`ui/components/kurve.py:145–158`) baut für
jede Kandidaten-Schrittweite die **ganze Liste** aller Vielfachen, nur um sie
zu zählen. Beim Spektrum (Werte bis 2,5 Mio. ms²/Hz) sind das Millionen
Rundungen: 2 / 10 / 35 / 71 ms bei 1 / 2 / 5 / 10 min, **607 ms** bei 70 min —
teurer als das Spektrum selbst. Auch live der größte Einzelposten.

### 1.4 Fenster-Analysen bei jedem Neuzeichnen, ohne Zwischenspeicher

- Spektrum des sichtbaren Ausschnitts (`ui/components/analyse.py:226`,
  `fensterspektrum`): 0,4 / 0,8 / 4,4 / 17 ms bei 1 / 2 / 5 / 10 min,
  **1,1 s** bei 70 min (4891 Schläge × 2000 Stützstellen).
- Poincaré und DFA α1 des Ausschnitts (`analyse.py:234–242`, `275–281`): bis 20 ms.

### 1.5 Kurvenbau und Übertragung an Flutter

- Jedes Neuzeichnen baut neue `LineChart`-Objekte (`messung_detail.py:523`,
  `verlauf.py:124`); jeder Punkt ist ein eigenes Flet-Control, bis 1200 je
  Linie (`kurve.py:20`). Python-Bau 4–12 ms je Chart.
- Vergleich und Kodierung je Neuzeichnen: 12–25 ms (1 min), 45–110 ms (5 min),
  130–230 ms („Alles“), 11–190 KiB — bei 8 Hz bis ~1,5 MB/s.
- „Alles“: 2700–5200 Punkte in 4 Charts; bei der Verity 264 Linienstücke, weil
  jede Naht die Linie teilt. Flutter baut das alles je Neuzeichnen neu auf.
- `nur_kurven` schickt `page.update()` an die ganze Seite
  (`messung_detail.py:1160`) statt nur an Kurve und Analysekarte.
- Fester Aufschlag je Neuzeichnen über die ganze Messung (`korr_zeiten`,
  zweimal `_linie`, `messung_detail.py:517–519`): 5–10 ms, egal wie breit das
  Fenster ist.

### 1.6 Öffnen einer Aufzeichnung

| | Zeit | Frequenz | Nichtlinear |
|---|---|---|---|
| Verity | 0,5–0,8 s | – | 0,9–1,3 s |
| H10 | – | **2,8 s** | 1,4 s |

Weil sie mit „Alles“ öffnet, rechnet sie sofort: Spektrum über 70 min (1,1 s)
samt Achsenraster (0,6 s), LF/HF-Verläufe über die ganze Messung (~420
Lomb-Fenster, 0,4 s), Atemfrequenz für die Kacheln (~280 Minutenfenster,
0,32 s), SampEn (0,27 s, `messung_detail.py:333`), DFA-Verlauf (114 Fenster,
0,33 s). Bei der Verity entstehen dieselben abgeleiteten Reihen (`ppi.py`:
`_intervalle`, `ppi_folge`, `schlagzeiten`) beim Öffnen 6- bis 18-mal neu,
zusammen ~0,27 s.

### 1.7 Live-Ansicht

`fuellen()` baut alle 0,5 s und bei jedem Wischen alles neu
(`ui/views/messung.py:741–750`, `491`): Kacheln, Hauptkurve, Spektrum,
Verläufe. Mit 15 min im Puffer im Frequenz-Reiter je Auffrischen: 25 / 39 /
89 / **166 ms** bei 1 / 2 / 5 / 10 min, dazu 48 ms Flet-Vergleich — bei 10 min
rund 40 % eines Kerns schon am Desktop, auf derselben Schleife wie die
Bluetooth-Daten. Größter Posten: das Achsenraster (1.3).

### 1.8 Was schon gut ist

Die Verlaufskurven (`trends.verlauf` mit Zwischenspeicher: 10-s-Raster bleibt
beim Zoomen gleich, beim Wischen kommen nur neue Rasterpunkte dazu) und die
Kennzahlen der ganzen Messung (`_Zustand.merken`).

---

## 2. Vorschlag

### Stufe 1 · Leitungen (ohne sichtbare Änderung)

1. `drag_interval` ~50–80 ms am GestureDetector.
2. In den Zieh-Handlern kein Auto-Update; nur die geänderten Container
   aktualisieren statt `page.update()`.
3. Drossel ab **Ende** des Neuzeichnens messen und zusammenfassen: nur die
   letzte Lage zeichnen, nie während eines laufenden Neuzeichnens.
4. `y_raster` rechnen statt aufzählen (Anzahl = ⌊oben/s⌋ − ⌈unten/s⌉ + 1).
5. Kurven auf ~300–400 Punkte je Chart ausdünnen (Min/Max je Bildpunkt),
   Linienstücke an Nähten zusammenlegen, Charts aktualisieren statt neu bauen.

Das beseitigt den Rückstau und senkt jede Zeichnung um ein Vielfaches. Es
ändert keine Zahl und kein Bild.

### Stufe 2 · Frequenz und Nichtlinear bewusst rechnen: das Analysefenster

Das Spektrum (ebenso Poincaré und DFA) folgt nicht mehr dem Zoom-Fenster beim
Wischen. Es gehört zu einem **Analysefenster**, das man bewusst wählt:

- **Ganze Messung** (bzw. der Zuschnitt): einmal gerechnet, gemerkt.
- **Ein Abschnitt**: je Abschnitt einmal gerechnet und gemerkt — so lassen
  sich „Ruhe“ und „Übung“ direkt vergleichen.
- **Gleitendes Fenster** fester Länge (1 / 2 / 5 / 10 min; 5 min ist der
  Standard für Kurzzeit-HRV): ein Band in der Rohkurve, das man wie einen
  Abschnitt links und rechts schiebt. Während des Schiebens bewegt sich nur
  das Band; gerechnet wird beim Loslassen — oder auf Knopfdruck, je nach
  Einstellung „Automatisch nach dem Loslassen“ / „Nur per Knopf“.

Die Zeitbereichswerte des sichtbaren Ausschnitts bleiben live — sie sind
billig, wenn Stufe 1 steht.

### Stufe 3 · Öffnen entlasten

- Mit dem zuletzt benutzten Zoom öffnen (Vorgabe 5 min) statt mit „Alles“.
- Nicht sichtbare Reiter, Kacheln und Verläufe erst rechnen, wenn sie
  sichtbar werden (SampEn, DFA, Atemfrequenz, LF/HF-Verläufe).
- Abgeleitete PPI-Reihen (`ppi_folge`, `schlagzeiten`) je Messung merken.
- Live: Spektrum nur alle 5 s statt alle 0,5 s neu (die Verity schickt
  ohnehin nur alle 5 s ein Paket).

Nach der Umsetzung mit denselben Szenarien nachmessen (Wischen 1 s mit 60
Ereignissen, Öffnen, Live mit 15 min Puffer).

---

## 3. Entscheidungen (Ben, 14.10.2026)

1. **Analysefenster** zuerst „Alles“ (ganze Messung); dazu Abschnitt und
   verschiebbares Fenster.
2. **Neu rechnen beim Loslassen**, mit kurzer Latenz, falls noch etwas
   nachkommt. Die Latenz ist eine Einstellung unter **Erweitert** (Vorgabe
   0,5 s) — die Einstellungen teilen sich in normal und Erweitert; langfristig
   werden das Profi-Einstellungen.
3. **Live-Spektrum** nur alle **15 s** (Erweitert, 5–60 s): „So genau braucht
   man das nicht. Wer es genauer braucht, muss es nachstellen.“
4. **Startansicht der Aufzeichnung:** 2 min (live war schon 2 min).
5. Stufen 1–3 zusammen umsetzen.

---

## 4. Umgesetzt (14.10.2026)

- **Stufe 1:** `drag_interval` 50 ms; Auto-Update in den Ziehhandlern aus,
  beim Wischen aktualisieren nur Rohkurve und Analysekarte (live: Kurve, Lage,
  Analyse); Drossel ab dem Ende des Neuzeichnens; bewegt sich das Fenster
  nicht (Rand, „Alles“), wird nicht gezeichnet; Achsenraster gerechnet
  (`kurve._anzahl_vielfache`); höchstens 500 Punkte je Linie, je Abschnitt
  Minimum und Maximum (Ausreißer bleiben sichtbar); Nähte schmaler als ein
  Bildpunkt trennen die Linie nicht. Entscheidung „greifen oder blättern“
  einmal je Geste, am Anfang (`zeitfenster.wischbar`).
- **Stufe 2:** `analyse.Analysefenster` — „Alles“ zeigt das Spektrum der
  Zusammenfassung (`Fensterspektrum.aus_frequenzbereich`, keine zweite
  Rechnung), Abschnitt und Band werden einmal gerechnet und gemerkt (24
  Fenster). Das Band greift man in der Rohkurve; während des Ziehens ruht die
  Analyse, nach dem Loslassen steht das alte Ergebnis blass mit Hinweis da,
  bis nach der Latenz gerechnet ist — kommt vorher eine neue Bewegung, gilt
  nur der letzte Auftrag. ‹ › schieben um eine halbe Länge.
- **Stufe 3:** Start mit 2 min; abgeleitete PPI-Reihen je Messung gemerkt
  (`ppi._gemerkt`, 6–18 ms → unter 2 ms je Aufruf); korrigierte Zeiten je
  Auswahl gemerkt; Ablesen per Bisektion; live Spektrum und Poincaré im
  Takt (`HrvEinstellungen.live_spektrum_s`), nach dem Wischen erst nach der
  Latenz neu.
- **Einstellungen → HRV-Messung:** Teil „Erweitert“ (zugeklappt) mit Rechnen
  (Latenz, Live-Spektrum), Kennzahlen (pNNx) und automatischer Korrektur.

**Nachgemessen** (Desktop, dieselben Messungen; 1 s Wischen, jetzt 20 statt 60
Ereignisse, Flet vergleicht nur, was der Handler aktualisiert):

| Messung, Reiter | 2 min | 5 min | „Alles“ |
|---|---|---|---|
| H10 70 min, Zeit | 1,4 s → **0,08 s** | 4,8 s → **0,13 s** | 18,8 s → **0,37 s** |
| H10 70 min, Frequenz | 1,7 s → **0,07 s** | 8,0 s → **0,08 s** | 129 s → **0,59 s** |
| Verity 73 min, Zeit / Frequenz | 0,6–0,7 s → **0,04 s** | 1,2–1,4 s → **0,10 s** | 12–15 s → **0,23–0,26 s** |

Öffnen: H10 im Frequenz-Reiter 2,8 s → 0,52 s, im Zeit-Reiter 0,44 s; Verity
0,5–0,8 s → 0,16–0,22 s. Achsenraster eines Spektrums: bis 607 ms → 0,01 ms.

**Nachtrag 15.10.2026 — Wischweg:** Flets Drossel verwirft Zwischenereignisse ohne
Aufsummieren; `primary_delta` ist nur der letzte Touch-Frame (≈ ⅙ der Bewegung bei
120 Hz und 50 ms). Seitdem zählt `local_delta` (Weg seit dem letzten gesendeten
Ereignis) — eine Fingerbreite blättert eine Fensterbreite (`zeitfenster.wischbar`).

**Nicht umgesetzt:** Charts an Ort und Stelle aktualisieren statt neu bauen
(mit 500 Punkten je Linie kaum noch nötig); Kacheln der ganzen Messung
(Atemfrequenz über alle Minutenfenster, ~0,3 s bei 70 min) rechnen weiter
beim Öffnen.
