# HRV-Algorithmen

Alle Konstanten stehen an einer Stelle: `src/trainingsapp/hrv_core/constants.py`.
Sie sind absichtlich identisch mit `praxis_gui/sensors/polar_h10/hrv_compute.py`.

> **Wer eine Konstante ändert, ändert die Vergleichbarkeit aller bisherigen
> Messungen.** Dann gehört `ALGO_VERSION` hochgezählt — der Kennzahlen-Cache
> gilt damit als veraltet und wird aus den Rohdateien neu berechnet.

---

## Warum wir nicht einfach praxis_gui benutzen

`praxis_gui` rechnet mit `scipy` (Lomb, Welch) und `neurokit2` (DFA, Kubios).
**Beides gibt es auf Android und iOS nicht.** `pypi.flet.dev` liefert vorgebaute
Wheels für numpy und pandas, aber nicht für scipy.

Der scipy-freie Rückfallpfad in praxis_gui ist ein nacktes rFFT-Periodogramm:
kein Hann-Fenster, keine Segmentmittelung, keine Einseitig-Verdopplung. Er
liefert **andere Zahlen** als der scipy-Pfad.

Deshalb `hrv_core`: ein Paket aus reinem numpy, das die Verfahren korrekt
nachbaut. Ziel ist **nicht** Bit-Gleichheit mit praxis_gui, sondern eine
gemeinsame Implementierung mit dokumentierten Toleranzen — geprüft gegen
Golden-Daten.

---

## Grundgrößen

| | Wert | Warum |
|---|---|---|
| `RR_MIN_MS` / `RR_MAX_MS` | 250 / 2000 | entspricht 30–240 bpm |
| `AUFNAHME_RR_MIN_MS` / `…_MAX_MS` | 300 / 2000 | Herzuhr `t_s` der Datei und Live-Markierung — so schreibt praxis_gui |
| `MIN_BEATS_TIME` | 2 | RMSSD braucht mindestens zwei Intervalle |
| `MIN_BEATS_NONLINEAR` | 30 | SD1/SD2 werden erst darüber stabil |
| `MIN_BEATS_FREQUENCY` | 60 (empfohlen 180) | ~1 min bei 60 bpm |
| `MIN_BEATS_DFA` | 200 | DFA α1 arbeitet schlagbasiert |
| `MIN_BEATS_SEGMENT` | 60 | kürzere Teilstücke gehen nicht ins Spektrum |

---

## Zeitbereich

Drei Details, bei denen andere Implementierungen abweichen:

```python
sdnn = arr.std(ddof=0)  # POPULATIONS-SD, nicht ddof=1
pnn50 = (np.abs(diffs) > 50).sum() / n * 100  # STRIKT größer, nicht >=
rmssd = np.sqrt((diffs**2).mean())  # diffs überspringen Nähte, s. u.
```

`compute_time_domain` liefert **`None`** statt Nullwerten, wenn zu wenige
Schläge vorliegen. Eine fehlende Messung ist keine Messung mit dem Wert null.

---

## Der Boundary-Skip

**Über eine Naht hinweg wird keine Schlag-zu-Schlag-Differenz gebildet.** Eine
Naht ist ein verworfener Wert oder eine Messlücke.

Ohne diese Regel entsteht eine „Differenz" zwischen zwei Schlägen, die in
Wirklichkeit Sekunden auseinanderlagen. Gemessen an einer realen einstündigen
Aufzeichnung mit 3,7 % Artefakten: **RMSSD 80,1 ms statt 63,4 ms — 21 % zu hoch.**

Betroffen sind alle Differenzmaße: RMSSD, pNN50, SD1.
SDNN und mean_RR sind differenzfrei und bleiben unberührt — das ist auch ein
guter Testanker (`tests/test_hrv_core.py`).

Implementierung: `hrv_core/segments.py::segment_diffs`.

### Vom Sensor verworfene Intervalle selbst prüfen (ALGO_VERSION 4)

Die Verity Sense markiert Intervalle als unbrauchbar (Blocker-Bit) — auch in
Ruhe viele brauchbare. Messung vom 13.10.2026, 15 min in Ruhe, 1140 Intervalle,
37 % verworfen:

| | behalten | verworfen |
|---|---|---|
| Fehlerschätzung des Sensors, Median | 11 ms | 12 ms |
| relative Nachbardifferenz, Median / 75 % / 90 % | 3,2 / 5,5 / 8,8 % | 3,5 / 5,9 / 10,6 % |
| relative Nachbardifferenz, 99 % | 16 % | 40 % |

Die Masse ist nicht zu unterscheiden; nur der Rand ist breiter — ein paar echte
Störungen (Einschwingen am Anfang mit 1625–2064 ms, eine Störung mit bis zu
500 ms Fehlerschätzung). Das kann das Programm selbst finden.

Mit `Korrekturregeln.sensor_verwerfung = "selbst"` (Vorgabe) rechnet die
Auswertung darum auf **allen** Intervallen (`ppi.ohne_verwerfung`,
`korrektur.analysebasis`): Zeilen der Rohdatei bleiben, wie sie sind;
wieder aufgenommene Intervalle bekommen die Wanduhr ihres Pakets nach
Vertrag 3a.4 (auf der Messung vom 13.10. für alle 719 Zeilen bit-gleich mit
dem Schreiber) und die Herzfrequenz der Zeile davor. Über sie urteilen
dieselben Regeln wie über jedes andere Intervall: Grenzen, Fehlerschätzung,
Malik, Ketten.

Ergebnis am 13.10.: Die Automatik schlägt genau zwei Ausschlüsse vor (die
beiden Störungen); danach **1119 statt 719 Schläge, RMSSD 50,0 statt
47,6 ms**, SDNN 93,2 statt 92,4 ms. Golden-Test:
`tests/test_korrektur_regeln.py` (synthetisch, RMSSD 21,8946 ms über alle 299
Nachbardifferenzen, unabhängig nachgerechnet).

Live gilt dasselbe (`LiveFenster.regeln_setzen`): Gespeichert ist je Punkt das
Blocker-Bit, nicht das Urteil — Umschalten wirkt sofort auf den ganzen Puffer.

`"sensor"` stellt das Verhalten bis ALGO_VERSION 3 wieder her (wie praxis_gui).

### Einstellbare Korrektur (`hrv_core/regeln.py`)

`Korrekturregeln` bündelt, was „automatische Korrektur" heißt — praxis_gui
verteilt es auf `[hrv]`, `[hrv_gaps]` und `metric_params.malik`:

| Regel | Vorgabe | praxis_gui |
|---|---|---|
| `sensor_verwerfung` | `selbst` | — (folgt immer dem Sensor) |
| `malik_an`, `malik` | an, nach Intervallquelle (0.20 / 0.30) | Malik-Schwelle je Sitzung, 0.20 |
| `rr_min`, `rr_max` | 250 / 2000 ms | `[hrv] rr_min_ms`, `rr_max_ms` |
| `fehler_an`, `fehler_max_ms` | an, 50 ms | — |
| `nullen` | aus | `[hrv] interpolate_zeros` (an) |
| `merge_gap`, `auto_max`, `unsicher_max`, `max_luecke_s` | 2, 2, 5, 3 s | `[hrv_gaps]` |
| `vorauswahl` | `sicher` | — |

`vorauswahl` sagt, welche Vorschläge beim Öffnen einer Aufzeichnung ohne
gespeicherte Korrektur übernommen sind: `sicher` = alles außer unsicheren
Interpolationen. Ein Ausschluss erfindet nichts; eine Interpolation über 3–5
Schläge erfände Variabilität.

Gerätelokal liegt die Vorgabe in `app_setting` (`hrv_korrektur`); je Messung
stehen die Regeln im Sidecar (`corrections_meta.regeln`, Vertrag 9a) — eine
Aufzeichnung öffnet mit den Regeln, mit denen sie korrigiert wurde.

### Woher die Nähte kommen (`korrektur.naehte`, ALGO_VERSION 2)

Außer verworfenen Werten in der Reihe selbst gibt es zwei Nähte, die man der
Reihe nicht ansieht — beide gelten immer, auch in der Rohspalte ohne Korrektur:

- **Messlücken** (`ppi.messluecken`, nächster Abschnitt) — etwa ein
  Verbindungsabriss beim H10.
- **Vom Sensor verworfene Intervalle** (Verity Sense, Blocker-Bit). Sie stehen
  nicht in `messungen` (wie bei praxis_gui), ihre Nachbarn sind dort aber
  aufeinanderfolgende Zeilen. Wo verworfen wurde, verrät nur `ppi_pakete`
  (`hrv_core/ppi.py`). Ergibt der Block nicht genau die Folge der Zeilen
  (beschnittene, fremde Datei), wird nicht geraten.

Gemessen am 13.10.2026: eine kurze Ruhemessung (37 % verworfen) RMSSD 36,5 statt
41,8 ms; eine 15-min-Messung in Bewegung (80 % verworfen) roh 102 statt 158 ms.
Bis ALGO_VERSION 1 wurde über beide Nahtarten hinweg differenziert.

Live schreibt der `Messlauf` die verworfenen Intervalle mit ``verworfen=True``
ins `LiveFenster`: Sie trennen die Kennzahlen wie eine Naht, werden aber
gezeichnet.

**Kurven.** Grau steht alles, was der Sensor geliefert hat — bei der Verity
Sense **alle** Intervalle aus `ppi_pakete`, auch die verworfenen
(`korrektur.rohfolge`); die Linie reißt nur an Messlücken ab. Farbig steht, was
gewertet wird, und reißt an jeder Naht ab. Am 13.10.2026 verwarf die Verity
Sense in Ruhe 44 % der Intervalle — ohne die graue Linie bestand die Kurve aus
37 Bruchstücken. Gewertet werden sie trotzdem nicht: Differenzen, an denen ein
verworfenes Intervall beteiligt ist, hatten RMSSD 43 ms, die übrigen 20 ms.
Die Werteachse richtet sich nur nach der farbigen Linie; graue Ausreißer werden
am Rand abgeschnitten, statt die Kurve zu stauchen.

---

## Die zwei Uhren und die Lückenerkennung

Jeder Schlag trägt `t_s` (Herzuhr, kumulierte RR) und `t_wall_s` (Wanduhr).
Die **Divergenz** `D(i) = t_wall_s − t_s` wächst genau dann, wenn Schläge fehlen.

Erkannt wird über ein Fenster von ±5 Schlägen, nicht über Einzeldifferenzen:
rekonstruierte Zeitstempel (`tw_src == "r"`) sind systematisch etwas zu früh und
erzeugen einzeln betrachtet eine Scheindrift von Minuten.

**Verity Sense (ALGO_VERSION 3).** `t_s` summiert nur die brauchbaren
Intervalle; die Divergenz wüchse mit jedem verworfenen, und ein Blocker-Lauf
von wenigen Sekunden sähe aus wie ein Verbindungsabriss (13.10.2026: 11
Scheinlücken in 3½ min Ruhe). `ppi.messluecken` rechnet darum auf der
**Herzuhr aller Intervalle** (`ppi.schlagzeiten`, die Summe aller Intervalle
aus `ppi_pakete`). Aus demselben Grund zieht die Kettenplanung der Automatik
die Dauer verworfener Intervalle von der „ungedeckten" Zeit ab — sonst schlug
sie Ketten über einen Blocker-Lauf zum Ausschluss vor statt zur Interpolation.
Dieselbe Herzuhr ist die x-Achse der Detailkurve: Die Messung dauert dort so
lange, wie sie gedauert hat.

Ohne Wanduhr ist keine Lückenerkennung möglich. `luecken_finden` gibt dann eine
leere Liste zurück, statt etwas zu erfinden.

---

## Artefaktkorrektur (Malik, zwei Durchläufe)

Ein Ausreißer verschiebt das lokale Mittel, an dem er gemessen wird. Deshalb:

1. Grobe Ausreißer gegen das rohe gleitende Mittel finden.
2. Diese überbrücken → saubere Referenz.
3. Endgültig gegen die saubere Referenz bewerten und interpolieren.

Schwellen: **0.20** für RR aus dem EKG, **0.30** für optische Puls-Intervalle —
die Pulswellenlaufzeit schwankt physiologisch stärker.

> **Der Randfall:** `np.convolve(..., mode="same")` polstert mit **Nullen**.
> Das drückt das lokale Mittel an Anfang und Ende nach unten und markiert dort
> völlig normale Schläge als Ausreißer. Deshalb `np.pad(..., mode="edge")`.

Die Indizes der korrigierten Stellen werden aufbewahrt — die Korrektur bleibt
nachvollziehbar und rücknehmbar.

**Fehlerschätzung des Sensors.** Die Verity Sense schätzt je Intervall ihren
Fehler (`ppi_pakete[].fehler_ms`). In Ruhe liegt er bei 7–30 ms; in Bewegung
gab es Intervalle ohne Blocker-Bit mit 100–650 ms geschätztem Fehler. Ab
`PPI_FEHLER_MAX_MS` = 50 ms schlägt die Automatik ein Intervall zur Korrektur
vor („Sensor unsicher") — vor Malik, damit es dessen Mittel nicht verzieht.
Eigene Festlegung; praxis_gui wertet die Schätzung nicht aus.

---

### Nachträgliche Korrektur in Ketten (`hrv_core/korrektur.py`)

Vorlage ist die Workbench von praxis_gui; gespeichert wird im Sidecar
`sensor_<ts>_analyzed.json` (`analysis-v1`, Vertrag: `docs/kompatibilitaet.md`,
Abschnitt 9). Die Rohdatei bleibt unangetastet.

1. **Kandidaten:** `rr_ms = 0` (Paket ohne RR), Werte außerhalb 250–2000 ms und
   Malik-Ausreißer (Schwelle 0.20, optisch 0.30).
2. **Ketten:** Kandidaten, die höchstens zwei gute Schläge trennen, gehören
   zusammen. Vor einem Ausfall liegt oft eine Zerfallszone, deren Werte den
   Schwellenfilter noch passieren — ohne Verschmelzen würde sie interpoliert.
3. **Vorschlag:** bis 2 Schläge interpolieren, bis 5 interpolieren *unsicher*,
   länger — oder mehr als 3 s ungedeckte Wanduhrzeit (Spanne minus Summe der
   RR) — ausschließen. Interpoliert wird linear zwischen den nächsten
   **gültigen** Nachbarn, als Rampe, nie als Plateau.

Auf der Golden-Datei liefert das dieselben neun Ketten und Kennzahlen wie
praxis_gui (RMSSD 44,816 ms, SDNN 90,123 ms — `tests/test_korrektur.py`).

**Abweichung von praxis_gui:** Malik rechnet auf der Reihe, in der Nullen und
implausible Werte schon überbrückt sind. Auf der Rohreihe ist das gleitende
Mittel über einer Nullfolge selbst 0 — die Nullen in ihrer Mitte gelten dann als
unauffällig, gesunde Nachbarn dagegen als Ausreißer. Bei einzelnen Nullen ist
das Ergebnis identisch.

**Nullen sind keine Artefakte (Standard, Abweichung von praxis_gui).** Eine
Null beim H10 heißt „in dieser Sekunde endete kein Schlag" (Puls unter 60 bpm).
Sie zu interpolieren fügte einen Schlag ein, den es nicht gab — auf der
Golden-Datei wären es 9 erfundene Schläge bei 305 echten. Deshalb schlägt
`automatisch()` Nullen nicht vor, und Malik rechnet nur auf der Folge echter
Schläge; ein wirklicher Aussetzer zeigt sich am langen Folgeintervall.
`kennzahlen` verwirft Nullen ohnehin (als Naht). Das praxis_gui-Verhalten gibt
es mit `automatisch(..., nullen=True)`; der Golden-Test prüft beide Wege, und
`corrections_meta.interpolate_zeros` hält fest, welcher galt.

---

## Live-Kennzahlen (`hrv_core/live.py`)

Während der Messung wird **nichts an den Rohdaten verändert.** `LiveFenster` hält
die letzten 30 min (so weit lässt sich live zurückblättern), markiert Artefakte
und liefert eine interpolierte Kurve nur für die Anzeige. Gespeichert wird
immer der Rohwert. Grenzen, Malik, Fehlerschätzung und der Umgang mit
Verworfenem folgen den `Korrekturregeln` (live ohne Ketten).

| Wert | Rechnung |
|---|---|
| Artefakt | außerhalb der Grenzen (ohne Regeln 300–2000 ms wie die Herzuhr der Aufnahme), Fehlerschätzung über der Schwelle oder Malik-Ausreißer im Fenster |
| `rr_korr` | Rohwert, bei Artefakt linear aus den guten Nachbarn; `None` bei `rr = 0` |
| `rmssd_30s`, `sdnn_60s` | Rohwerte der letzten 30 / 60 s; Artefakte wirken als **Naht** (Boundary-Skip), nicht als interpolierter Wert |
| `hf_mittel_60s` | Mittel der vom Gerät gemeldeten Herzfrequenz |
| `schwankung_60s` | siehe unten |

Unter fünf guten Schlägen im Fenster ist ein Wert `None`. Am rechten Rand fehlen
Malik die Nachfolger — ein frischer Ausreißer wird oft erst ein, zwei Schläge
später markiert.

`rr = 0` ist kein Artefakt, sondern *kein Wert*: nicht markiert, keine Kurve,
in den Kennzahlen eine Naht.

Die Malik-Schwelle folgt der Intervallquelle des Geräts: 0.20 für EKG-RR,
0.30 für optische PPI (`constants.malik_threshold`) — live wie in der
nachträglichen Korrektur. Bis Oktober 2026 galt live und in der Detailansicht
für jedes Gerät 0.20; bei der Verity Sense wurden dadurch gesunde Schläge rot.

### Zeitachse gebündelter PPI-Pakete (`hrv_core/zeitachse.py`)

Die Verity Sense schickt alle ~5 s rund fünf Intervalle, mit 0–1 s Streuung in
der Zustellung. Aus der Ankunft zurückgerechnet (wie `t_wall_s` in der Datei)
liegen die Paketgrenzen um bis zu eine Sekunde daneben, und gelegentlich liegt
der erste Schlag eines Pakets **vor** dem letzten des vorigen. Live wurde er
dann auf 1 ms hinter den Vorgänger geschoben: senkrechte Zacken, die die Kurve
deutlich unruhiger aussehen ließen als beim H10, obwohl die Intervalle selbst
in Ordnung waren.

Die x-Achse der Live-Kurve nimmt darum die **Kontinuitätsuhr** aus praxis_gui:
Schlagzeit = laufende Summe aller Intervalle (auch blockierter) + Anker; Anker
= kleinstes (Ankunft − Summe) der letzten 60 Pakete, denn ein Schlag liegt nie
nach seiner Zustellung. Steigt (Ankunft − Summe) um mehr als 3 s, fehlen
Intervalle (Abriss) — dann wird neu verankert, damit die Lücke sichtbar bleibt.
Die Datei behält die Ankunftsachse; die Rohzutaten stehen in `ppi_pakete`.

### Verlaufskurven (`hrv_core/trends.py`)

Unter der Hauptkurve — live und in der Aufzeichnung — schaltet man zwischen drei
Bereichen um; je Bereich gibt es wählbare Verlaufskurven (Schlüssel wie
praxis_gui, Vertrag Abschnitt 10):

| Bereich | Kurven (Vorgabe-Fenster) | Mindestens gute Schläge im Fenster |
|---|---|---|
| Zeit | Ø HF (10 s), Ø RR (10 s), RMSSD (30 s), SDNN (60 s), pNNx (30 s), HF Gerät | 1 (Mittelwerte), sonst 5 |
| Frequenz | LF-Band, HF-Band, LF/HF, Gipfel /min (je 2 min) | 30, und 70 % der Fensterzeit belegt |
| Nichtlinear | SD1 (60 s), SD2 (3 min), DFA α1 (2 min) | 30 bzw. 100 (DFA) |

Je Rasterpunkt `t_e` gehen die Schläge mit `t_e − Fenster < t ≤ t_e` ein,
Definitionen wie `time_domain`; NaN und Nähte trennen, unter der Mindestzahl
bleibt eine Lücke. Live rechnen die Kurven auf den guten Rohwerten (Artefakte
als Naht, wie `kennzahlen`), in der Aufzeichnung auf der korrigierten Reihe.

- **Ø HF und Ø RR ab 3-s-Fenstern.** Für einen Mittelwert genügt ein Schlag im
  Fenster; die Fenster 3 und 5 s zeigen den Puls fast Schlag für Schlag
  (praxis_gui: ab 5 s).
- **pNNx** statt pNN50: Schwelle 10–100 ms, Vorgabe 50 (`Ansicht.pnn_ms`),
  gezählt strikt größer. Der Schlüssel älterer Ansichten (`pnn50`) wird beim
  Lesen auf `pnnx` abgebildet.
- **Gleitend oder in Blöcken.** Gleitend: Raster an Vielfachen eines Schritts
  (ein Zehntel des Fensters, 1–10 s). Blöcke: nicht überlappende Fenster an
  Vielfachen der Fensterlänge, ein Wert je Block, nur vollständige Blöcke — als
  Stufe gezeichnet (`treppe`), damit man sieht, wofür der Wert gilt (praxis_gui:
  „Block"). praxis_gui erzwingt bei Frequenzkurven Blöcke (Rechenaufwand);
  hier ist beides möglich, weil teure Fenster zwischengespeichert werden.
- **Frequenz im Fenster** ist ein Lomb über alle guten Schläge des Fensters
  (`frequency.fensterspektrum`); LF, HF, LF/HF und Gipfel teilen sich das
  Spektrum je Fenster. Die Mindestdauer je Band gilt nicht (das Fenster wählt
  der Anwender), die Ansicht weist aber darauf hin.
- **Zwischenspeicher.** Spektren und DFA je Fenster merkt sich die Ansicht über
  Zeichnungen hinweg; der Schlüssel enthält Grenzen, Zahl und Summe der guten
  Werte. Wird live ein Schlag nachträglich zum Artefakt, ändert sich die Summe,
  und das Fenster wird neu gerechnet.

**Ø HF aus RR statt gemeldeter Herzfrequenz.** Die Verity Sense meldet ihre
Herzfrequenz nur etwa alle 5 s neu und springt dabei (13.10.: Stufen zwischen
60 und 85 bpm, bei gleichmäßigen Intervallen). `60000 / Ø RR` folgt dem Puls
ruhig. praxis_gui bietet dasselbe als „Ø BPM" (30 s).

**Achsen statt Einheiten.** Kurven derselben Achse teilen sich ein Diagramm
(RMSSD, SDNN, SD1, SD2; LF und HF), verschiedene stehen untereinander mit
derselben Zeitachse — zwei y-Achsen sind am Handy nicht lesbar. Ø RR hat zwar
die Einheit ms, bekommt aber eine eigene Achse: bei 900 ms neben 40 ms wäre
RMSSD eine flache Linie. Eine Höchstzahl gleichzeitiger Kurven gibt es nicht
mehr (bis Oktober 2026 vier — eine eigene Festlegung für kleine Bildschirme).
Die Auswahl samt Fenstern ist eine `core.hrv_ansicht.Ansicht`, speicherbar
unter einem Namen (praxis_gui: „Vorlagen").

**Spektrum und Poincaré des Ausschnitts.** Im Bereich Frequenz steht über den
Kurven das Spektrum dessen, was die Hauptkurve gerade zeigt (zoomen und wischen
ändern es), mit getönten Bändern und dem stärksten Gipfel; die Höhe richtet sich
nach LF und HF. Im Bereich Nichtlinear die Poincaré-Wolke des Ausschnitts mit
SD1, SD2 und DFA α1. Keine Bewertung (kein „kohärent", keine Ampel) — wie
praxis_gui seit „Live-PSD ohne Urteil".

**Optische Sensoren.** Nichtlinear ist bei Pulsintervallen (Verity Sense)
standardmäßig ausgeblendet (`HrvEinstellungen.nichtlinear_optisch`); die
praxis_gui-Doku stuft DFA dort als „nein" ein. Frequenzwerte bekommen einen
Vorbehalt („mit Vorsicht").

### „Schwankung"

```
HF_i = 60000 / RR_i        (nur gute Schläge; ohne RR: gemeldete Herzfrequenz)
Teilfenster k = 0…5: die letzten 60 s in Stücken zu 10 s, vom jüngsten Punkt aus
schwankung_60s = Mittel über alle Teilfenster mit ≥ 3 Werten von (max HF − min HF)
                 — mindestens zwei solche Teilfenster, sonst None
```

Das ist eine **Näherung der RSA-Amplitude** (Peak-to-Trough der
Herzfrequenz): bei sechs Atemzügen pro Minute deckt ein Teilfenster genau einen
Atemzug ab. Auf einem Sinus `70 ± A bpm` mit 0,1 Hz liefert sie `2·A` auf 5 %
genau (`tests/test_korrektur.py`). Bei schnellerer Atmung enthält ein
Teilfenster mehrere Atemzüge — die Spannweite bleibt eine Spannweite.

Die vom Gerät gemeldete Herzfrequenz eignet sich dafür nicht: sie ist geglättet,
beim Verity Sense nur alle 5 s aktualisiert.

> **Keine Bewertung.** Die Schwankung ist ein beschreibender Wert wie die
> Herzfrequenz selbst. Eine Aussage wie „gut", „Kohärenz erreicht" oder eine
> Empfehlung daraus wäre eine Handlungsempfehlung aus Messwerten — der Schalter
> `physiologische_steuerung` bleibt in der Edition `solo` gesperrt
> (`docs/recht/00_zweckbestimmung.md`).

### Atemfrequenz (`hrv_core/atmung.py`, ATEM_VERSION 1)

**Gemeinsames Modul mit praxis_gui** — byteidentisch in beiden Projekten
(`praxislab/sensors/polar_h10/atmung.py`); je ein Test vergleicht die Bytes
(`PRAXIS_GUI_PFAD` hier, `TRAININGSAPP_PFAD` dort). Nur numpy.

**Prüfung statt Schätzung.** Der höchste Gipfel im Atemband ist im Sitzen oft
die Mayer-Welle der Blutdruckregulation (0,1 Hz ≙ 6/min). praxis_gui lag damit
auf seinem Generator-Korpus im Median 7–10/min daneben und nahm mit seiner
Konfidenz (Gipfel gegen Median) auch Vorhofflimmern an. Eine Rate gibt es
deshalb nur, wenn alles passt — sonst steht der Grund da:

| Prüfung | Schwelle | Grund, wenn nicht |
|---|---|---|
| gute Schläge, Dauer, Abdeckung, Lücken | ≥ 30, ≥ 30 s, ≥ 80 %, ≤ 3 s | „zu wenige gute Schläge", „Lücke im Fenster" … |
| Puls | ≤ 110 bpm | „Puls zu hoch" |
| Abtastung | ≥ 3 Schläge je Atemzug | „Atmung zu schnell für den Puls" |
| Glätte (Leistung unter der Atemgrenze / bis HF/2) | ≥ 0,92 | „unruhiger Herzrhythmus" (VHF, viele Extrasystolen) |
| Gipfelanteil am Atemband | ≥ 0,40 | „kein deutlicher Atemgipfel" |
| Zyklen im gefilterten Signal | ≥ 3, Rate ±1/min bzw. ±10 % zum Gipfel | „Atemzüge passen nicht zum Gipfel" |
| Gleichmäßigkeit der Zyklen | CV ≤ 0,30 | „unregelmäßige Atmung" |
| Atemschwankung (RSA, Spitze–Tal, Median) | ≥ 1 bpm | „Atemschwankung zu schwach" |

**Zwei Modi.** `RUHE` (Vorgabe): nur ab 8/min — eine langsamere, stärkere
Schwingung ist ein Grund („langsame Schwingung unter 8/min — Atmung oder
Blutdruckwelle"), keine Zahl. `ATEMUEBUNG` (Einstellungen → HRV → Atmung, oder
der Knopf „Atemübung" in der Übersicht): Langsames Atmen zählt, wenn sein Gipfel
klar dominiert (Anteil ≥ 0,70) und die Schwankung spürbar ist (≥ 50 ms
Spitze–Tal). Aus RR allein ist nicht zu unterscheiden, ob bei 6/min die Atmung
oder die Blutdruckwelle schwingt — das sagt nur der Zusammenhang.

**Wo es steht:** Wert der Übersicht (Fenster 60 s, wählbar 60/90/120 s),
Verlaufskurve „Atemfrequenz" (Lücken, wo keine Atmung deutlich ist) und
„Atemschwankung" (RSA in bpm), Aufzeichnung: Median der gültigen
Minutenfenster mit „n von m Minutenfenstern deutlich". praxis_gui: `rest` und
`auto` → RUHE, `deep` → ATEMUEBUNG; live die letzten 60 s.

**Gemessen** auf dem praxis_gui-Generator-Korpus (Wahrheit bekannt, 38
Aufnahmen, Fenster 60 s, Schritt 15 s; Fehler = Median |Rate − Wahrheit|):

| Szenario | gültige Fenster (Ruhe) | Fehler | Atemübung |
|---|---|---|---|
| Ruhe sitzend/liegend, HRV-arm, Seufzer, Apnoe-Episoden | 83–100 % | 0,18–0,29/min | gleich |
| BLE-Aussetzer/-Stau, Wiederverbinden, schlechter Gurtkontakt | 68–92 % | 0,21–0,23 | gleich |
| Belastung/Erholung, Orthostase | 67–98 % | 0,20–0,33 | Orthostase: Mayer-Welle teils als Atmung (bis 14 von 56 Fenstern daneben) |
| Kohärenzatmung 6/min | **0 %** (richtig: unter 8/min) | — | 100 %, 0,04–0,08 |
| Vorhofflimmern normofrequent/tachykard | 0–1 von 36 | (1 Fehlgriff) | gleich |
| häufige SVES / VES-Bigeminus / einzelne VES | 0 / 25 % / 11 % | 0,07–0,45 | gleich |
| periodische Atmung | 80 % | 1,07, 13 Fenster > 1,5/min | — |
| tiefe und flache Atmung im Wechsel | 0–10 % | 0,4–0,7 | im Modus Atemübung oft daneben (1,3–6/min) |

Auf reinem Rauschen nimmt die Prüfung 0,7 % der Fenster an; echte Atmung
(9–28/min, 20–80 ms) zu 97 %, mit 10 ms Rauschen zu 85 %. Grenzen:
periodische Atmung (wechselnde Rate) und der Modus Atemübung außerhalb einer
Atemübung — darum ist er aus und schaltet man ihn nur dafür ein.

> **Keine Bewertung.** Die Atemfrequenz beschreibt, wie man atmet; „gut" oder
> „zu schnell" sagt die App nicht (`physiologische_steuerung`, solo gesperrt).

---

## Frequenzbereich (`hrv_core/frequency.py`)

Umgesetzt am 2026-10-13 — Lomb-Scargle, Welch und Periodogramm in reinem numpy,
Rechnung für Rechnung wie scipy 1.18 und praxis_gui (`spectrum.py`,
`hrv_compute.compute_frequency_domain`, Strategie „subspectra"). Golden-Test
`tests/test_frequenz.py`: Bandwerte und Spektrum auf drei Dateien (echte
H10-Messung, zwei synthetische aus dem praxis_gui-Generator) stimmen mit
praxis_gui auf wenige ppm überein — die Abweichung ist deren Rundung auf drei
Nachkommastellen; die Spektralkurve stimmt auf alle Stellen.

**Zwei Rechenwege, eine Mathematik:**

| | ganze Aufzeichnung | Fenster (Kurven, Live) |
|---|---|---|
| Funktion | `frequenzbereich` → `compute_frequency_domain` | `fensterspektrum` |
| Zerlegung | Teilstücke an Nähten und unplausiblen Werten, je eines ab 60 Schlägen | keine — ein Lomb über alle guten Schläge des Fensters |
| Mittelung | nach Dauer gewichtet, je Band nur taugliche Teilstücke | — |
| Mindestdauer je Band | ja (sonst gesperrt) | nein, die Fensterlänge wählt der Anwender (`reif` sagt, ob sie reicht) |
| Mindestbelegung | Bandpolitik (≥ 50 % durch taugliche Teilstücke) | ≥ 30 gute Schläge und ≥ 70 % der Fensterzeit belegt |

Lomb braucht kein gleichmäßiges Raster: Im Fenster sind Artefakte und
fehlende Schläge fehlende Stützstellen; die Normierung `2T/N` mit dem echten
`N` hält die Bandleistung dabei stabil (`test_lomb_vertraegt_fehlende_schlaege`:
20 % fehlend, Abweichung < 8 %). praxis_gui rechnet gefensterte Kurven über
Teilstücke (je ≥ 60 Schläge) — bei Fenstern von 1–2 min fiele dort jedes
Fenster mit einem Artefakt aus.

**Nullen trennen nicht (Abweichung von praxis_gui).** Eine Null beim H10
heißt „in dieser Sekunde endete kein Schlag" — die Nachbarn sind echte
Nachbarn. Als Naht zerlegten Nullen eine Ruhemessung unter 60 bpm in kurze
Teilstücke: Auf der Golden-Datei (5 min, 9 Nullen) blieben 76 und 85 s, alle
Bänder gesperrt. `ohne_nullen` nimmt sie vor der Zerlegung heraus
(`nullen_trennen=True` rechnet wie praxis_gui ohne `interpolate_zeros`). Der
Zeitbereich behandelt Nullen weiter als Naht (unverändert, ALGO_VERSION 4).

**Kennzahlen** wie praxis_gui: ULF, VLF, LF, HF (ms²), `total_power` = Summe
der verfügbaren VLF + LF + HF, LF/HF, `lf_n`/`hf_n` = LF bzw. HF / (LF + HF).
Zusätzlich die Lage des stärksten Gipfels 0,04–0,40 Hz (`gipfel_hz`, je Band
`lf_gipfel_hz`/`hf_gipfel_hz`) — beschreibend: bei ruhiger, gleichmäßiger
Atmung meist die Atemfrequenz. Das Detrending ist, wie in praxis_gui, nur der
Mittelwertabzug.

### Bänder

```
ulf 0.0001–0.003 · vlf 0.003–0.04 · lf 0.04–0.15 · hf 0.15–0.40 · tp 0.003–0.40
```

Mindestmessdauer: lf ≥ 300 s, hf ≥ 180 s, vlf ≥ 1200 s, ulf ≥ 14400 s.

### Die drei Fallstricke

**1. Lomb-Normierung.**

```
PSD = pgram · 2·T / N        T = Zeitspanne, N = Anzahl Schläge
```

**Nicht** durch die Schrittweite des Zielrasters teilen. Dieser Fehler steckte
in praxis_gui und lag um **Faktor ~2000** daneben — das Ergebnis skalierte mit
der Bin-Zahl statt mit dem Signal.

**2. Frequenzraster gleichverteilt mit `df = 1/T`**, nicht logarithmisch.
Gemessen an einem 0,1-Hz-Atemsignal fand ein Log-Raster mit 200 Bins pro Dekade
nur **0,11–0,15×** der Bandleistung wieder. Erst bei 800 Bins/Dekade stimmte es.
Relevant, weil Atemübungen genau solche Schmalband-Peaks erzeugen.

**3. Resampling linear** (`np.interp`), nicht kubisch. praxis_gui rechnet linear;
kubisch ergäbe systematisch andere HF-Werte. Kubisch nur für die RSA-Hüllkurve,
auf einem eigenen 16-Hz-Tachogramm.

### Genauigkeit

Referenzsignal LF 1200 ms², HF 600 ms², Soll-LF/HF 2,00, 15 Minuten:

| Methode | LF | HF | LF/HF | Laufzeit |
|---|---|---|---|---|
| **`lomb`** | **0,96×** | **1,03×** | **1,87** | 91 ms |
| `welch` | 0,88× | 0,72× | 2,44 | 5 ms |

`lomb` ist Standard: kein Resampling nötig, verträgt Lücken. Das
4-Hz-Resampling für Welch dämpft HF messbar um rund 30 %.

### Lücken

Aufzeichnung an Lücken in Segmente teilen, Spektren je Segment auf einem
gemeinsamen Raster rechnen und **längengewichtet** mitteln:

```
∫Band gemittelt = Σ dauer_i · ∫Band P_i  /  Σ dauer_i
```

Gegenprobe in praxis_gui: eine lückenfreie 113-Minuten-Reihe künstlich in
2/4/8/16 Stücke zerlegt reproduziert die Bandwerte der Gesamtreihe auf 1–4 %.

### Bänder sperren statt raten

Reicht Messdauer oder Abdeckung nicht, liefert das Band **`None`** plus einen
Grund (`band_status`, `band_reason`) — nie eine erfundene Zahl.

```
min_coverage_pct  50
max_gap_s         ulf 300 · vlf 60 · lf 10 · hf 2
max_missing_pct   ulf 20 · vlf 15 · lf 10 · hf 5
```

### Umsetzungshinweise

- **Lomb ist der teure Teil**, O(N × Bins). Eine naive Umsetzung über `np.outer`
  alloziert bei 2000 Schlägen × 2000 Bins rund 32 MB je Zwischenergebnis,
  mehrfach. Über Frequenzblöcke chunken, Bin-Zahl auf 2000 deckeln.
- **Welch selbst bauen:** Hann-Fenster, 50 % Überlappung, Skalierung durch
  `fs · Σw²`, alle Bins außer DC und Nyquist verdoppeln.

---

## Nichtlineare Kennzahlen

### Poincaré (implementiert)

```
SD1 = RMSSD / √2
SD2 = √(2·SDNN² − SD1²)
```

Die zweite Formel kann durch Rundung minimal negativ werden — bei 0 abschneiden.

### DFA α1 (`nonlinear.compute_dfa_alpha1`)

Skalen 4–16 Schläge, Fenster 200 Schläge. Rechnung wie `neurokit2.fractal_dfa`
(das praxis_gui nutzt): Profil `cumsum(rr − mean)`, Boxen um `n // 2` versetzt
(50 % Überlappung), je Box eine Gerade abziehen, `F(n) = √(Mittel der
Varianzen)`, α1 = Steigung von `log₂ F` über `log₂ n`. Golden-Test gegen
neurokit2 auf 12 Stellen (`tests/test_nichtlinear.py`).

```
α1 ≈ 0.5     unkorreliertes Rauschen — starke Erschöpfung
α1 0.75–1.0  1/f-Rauschen, gesunde autonome Regulation in Ruhe
α1 > 1.0     Brownsche Bewegung, typisch unter Belastung
α1 < 0.75    wird als aerobe Schwelle zur Belastungssteuerung verwendet
```

praxis_gui korrigiert vorher mit dem Kubios-Verfahren aus neurokit2. Das gibt es
mobil nicht — wir nutzen die Malik-Korrektur und kennzeichnen das Ergebnis.

### Sample Entropy (`nonlinear.compute_sampen`)

`m = 2`, `r = 0.2 · SD` (`ddof=0`), Chebyshev-Abstand, wie praxis_gui: je
Dimension alle `n − dim + 1` Vorlagen, Paare `i < j`. **O(N²)** — zeilenweise
gerechnet statt als Vollmatrix, live auf 500 Schläge begrenzt.

---

## Fachlicher Vorbehalt

Nichtlineare Kennzahlen setzen eine präzise R-Zacken-Erkennung voraus. Bei der
130-Hz-EKG-Ableitung des Polar H10 — und erst recht bei optischen
Puls-Intervallen — sind DFA und SampEn **nicht zuverlässig**; belastbar wären
≥ 500 Hz. Als Trend brauchbar, nicht als Absolutwert.

Das gehört in jede Darstellung dieser Werte, nicht nur in diese Datei.

---

## Golden-Tests

`tests/golden/rr/` enthält eine echte Messdatei aus `praxis_gui/Data/RR/`, eine
synthetische Verity-Datei und zwei synthetische Messungen aus
`praxis_gui/tools/generate_hrv_dataset.py` (Ruhe sitzend, Kohärenzatmung 6/min)
mit bekannter Bandleistung. Frequenzbereich, DFA α1 und SampEn sind gegen
praxis_gui auf denselben Dateien geprüft (`tests/test_frequenz.py`,
`tests/test_nichtlinear.py`); den ganzen Korpus (15 Szenarien) liefert
`generate_hrv_dataset.py --corpus`.
