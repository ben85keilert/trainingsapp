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

---

## Die zwei Uhren und die Lückenerkennung

Jeder Schlag trägt `t_s` (Herzuhr, kumulierte RR) und `t_wall_s` (Wanduhr).
Die **Divergenz** `D(i) = t_wall_s − t_s` wächst genau dann, wenn Schläge fehlen.

Erkannt wird über ein Fenster von ±5 Schlägen, nicht über Einzeldifferenzen:
rekonstruierte Zeitstempel (`tw_src == "r"`) sind systematisch etwas zu früh und
erzeugen einzeln betrachtet eine Scheindrift von Minuten.

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
die letzten 300 s, markiert Artefakte und liefert eine interpolierte Kurve nur
für die Anzeige. Gespeichert wird immer der Rohwert.

| Wert | Rechnung |
|---|---|
| Artefakt | außerhalb 300–2000 ms (wie die Herzuhr der Aufnahme) oder Malik-Ausreißer im Fenster |
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

---

## Frequenzbereich

> Status: Gerüst, Implementierung in L09.

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

### DFA α1 (Gerüst, L09)

Skalen 4–16 Schläge, Fenster 200 Schläge, Boxen à 10 für das Detrending.

```
α1 ≈ 0.5     unkorreliertes Rauschen — starke Erschöpfung
α1 0.75–1.0  1/f-Rauschen, gesunde autonome Regulation in Ruhe
α1 > 1.0     Brownsche Bewegung, typisch unter Belastung
α1 < 0.75    wird als aerobe Schwelle zur Belastungssteuerung verwendet
```

praxis_gui korrigiert vorher mit dem Kubios-Verfahren aus neurokit2. Das gibt es
mobil nicht — wir nutzen die Malik-Korrektur und kennzeichnen das Ergebnis.

### Sample Entropy (Gerüst, L09)

`m = 2`, `r = 0.2 · SD`, Chebyshev-Abstand. **O(N²)** — bei 4000 Schlägen sind
das 1,6·10⁷ Paarvergleiche, als Vollmatrix nicht speicherbar. Blockweise rechnen
und live auf 500 Schläge begrenzen.

---

## Fachlicher Vorbehalt

Nichtlineare Kennzahlen setzen eine präzise R-Zacken-Erkennung voraus. Bei der
130-Hz-EKG-Ableitung des Polar H10 — und erst recht bei optischen
Puls-Intervallen — sind DFA und SampEn **nicht zuverlässig**; belastbar wären
≥ 500 Hz. Als Trend brauchbar, nicht als Absolutwert.

Das gehört in jede Darstellung dieser Werte, nicht nur in diese Datei.

---

## Golden-Tests

`tests/golden/rr/` enthält eine echte Messdatei aus `praxis_gui/Data/RR/`.

Für Kennzahlen liefert `praxis_gui/tools/generate_hrv_dataset.py --corpus`
15 Szenarien mit Wahrheitsdatei (`truth-v1`) — bekannte Sollwerte für LF, HF,
RMSSD und SDNN. Das ist die Referenz, gegen die `hrv_core` in L09 validiert wird.
