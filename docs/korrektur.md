# Automatische Korrektur: was zählt und warum

Stand 14.10.2026, `ALGO_VERSION` 6. Code: `hrv_core/regeln.py` (Vorgaben),
`hrv_core/korrektur.py` (Automatik), `hrv_core/ppi.py` (Verity Sense),
`hrv_core/live.py` (live). Formeln und Fallstricke: [hrv_algorithmen.md](hrv_algorithmen.md).

---

## Grundsatz

**Lieber eine Lücke als ein falscher Wert.** Eine Kennzahl aus weniger, aber
echten Herzschlägen stimmt. Eine aus vielen Schlägen, von denen ein Teil
geraten ist, stimmt nicht, und man sieht es ihr nicht an. Daraus folgen drei
Regeln:

1. **Gezählt wird nur, was der Sensor sicher gemessen hat.**
2. **Erfunden wird nur im Kleinen:** Höchstens 5 Schläge am Stück werden
   interpoliert, was länger ist, wird ausgeschlossen.
3. **Was die Automatik als Artefakt erkennt, bleibt nie roh stehen.**

Die Rohdatei bleibt immer unangetastet. Korrekturen stehen im Sidecar
(`sensor_<ts>_analyzed.json`, praxis_gui-kompatibel) und lassen sich je Kette
abwählen.

---

## Die Regeln der Reihe nach

### Erkennen

| # | Regel | Vorgabe | Folge |
|---|---|---|---|
| 1 | vom Sensor verworfen (Verity Sense, Blocker-Bit) | zählt nicht | grau gezeichnet, Naht |
| 2 | Grenzen | außerhalb 250–2000 ms (30–240/min) | Artefakt |
| 3 | Fehlerschätzung des Sensors (Verity Sense) | über 50 ms | Artefakt |
| 4 | Malik: Abweichung vom gleitenden Mittel über 5 Schläge, zwei Durchläufe | über 20 % (EKG) bzw. 30 % (optisch) | Artefakt |
| 5 | Zeile ohne RR (H10: in dieser Sekunde endete kein Schlag) | kein Artefakt | Naht, nie interpoliert |
| 6 | Messlücke (die Wanduhr läuft der Herzuhr davon, z. B. Verbindungsabriss) | – | Naht |

Die optische Malik-Schwelle ist weiter, weil die Pulswellenlaufzeit
physiologisch stärker schwankt als das EKG.

### Ketten planen

Artefakte, zwischen denen höchstens 2 gute Schläge liegen, bilden eine **Kette**:

| Kette | Vorschlag |
|---|---|
| 1–2 Schläge | interpolieren, linear zwischen den gültigen Nachbarn |
| 3–5 Schläge | interpolieren, als *unsicher* markiert |
| mehr als 5 Schläge, oder mehr als 3 s Wanduhrzeit, die kein Intervall füllt | ausschließen (Naht) |

Beim Öffnen einer Aufzeichnung sind **alle** Vorschläge übernommen. Wer eine
Kette abwählt, entscheidet sich bewusst dafür, dass dort der Rohwert zählt.

### Rechnen

Über eine **Naht** wird keine Schlag-zu-Schlag-Differenz gebildet. Das betrifft
RMSSD, pNN50 und SD1. SDNN und die mittlere Herzfrequenz zählen die Schläge
davor und danach trotzdem. Reicht es für eine Kennzahl nicht, steht „–“ statt 0.

**Live** gelten die Regeln 1–6. Erkannte Artefakte zählen dort nicht mit und
wirken wie eine Naht. Ketten plant erst die Aufzeichnung.

---

## Warum so: die Messungen dahinter

### 14.10.2026: Verity Sense, 73 min bei der Arbeit (Behandlung)

Der Sensor saß fest. Hautkontakt bestand die ganze Zeit (`kontakt = 1` bei
allen 5536 Intervallen), und die Übertragung hatte keine Lücke: Pakete kamen
alle ~5 s, nie mit mehr als 6 s Pause. Trotzdem verwarf der Sensor **62 %**
der Intervalle, je 10 Minuten zwischen 18 % und 97 %.

Der Grund ist Bewegung. Optisch misst der Sensor die Pulswelle im Gewebe, und
Muskelarbeit und Bewegung unter dem Sensor überdecken sie. Ein fester Sitz
hilft gegen Licht von außen, nicht gegen Bewegung.

**Taugen die verworfenen Intervalle trotzdem?** Nein. Jedes Intervall wurde mit
dem Median seiner sauberen Nachbarn verglichen (± 6 Intervalle,
Fehlerschätzung ≤ 20 ms):

| Fehlerschätzung | nicht verworfen: Abweichung über 20 % | verworfen: Abweichung über 20 % |
|---|---|---|
| bis 10 ms | 0,0 % | 1,1 % |
| 10–20 ms | 0,6 % | 5,5 % |
| 20–30 ms | 0,0 % | 19 % |
| 30–50 ms | 0,0 % (nur 8 mit sauberen Nachbarn) | 53 % |

Bei zwei benachbarten verworfenen Intervallen wich das eine in 17 % der Fälle
um mehr als 20 % vom anderen ab, bei nicht verworfenen in 0,5 %. RMSSD aus
Paaren echter Nachbarn:

| Paare | RMSSD |
|---|---|
| beide nicht verworfen, Fehlerschätzung ≤ 20 ms (1733 Paare) | **30 ms** |
| beide verworfen, Fehlerschätzung ≤ 20 ms (1869 Paare) | 98 ms |

Der Sensor hat also recht, auch dort, wo seine eigene Fehlerschätzung klein ist.

**Was die Regeln daraus machen:**

| Regeln | gewertet (Anteil der Zeit) | RMSSD | SDNN |
|---|---|---|---|
| dem Sensor folgen, alle Vorschläge (**Vorgabe ab 6**) | 37 % | 30 ms | 67 ms |
| dem Sensor folgen, unsichere Ketten roh | 38 % | 39 ms | 72 ms |
| selbst prüfen, unsichere Ketten roh (**Vorgabe 4–5**) | 82 % | 98 ms | 114 ms |
| selbst prüfen, alle Vorschläge | 81 % | 73 ms | 114 ms |

„Gewertet“ heißt: Originalwerte, weder interpoliert noch ausgeschlossen.

**Ist die Fehlerschwelle von 50 ms zu streng?** Nein, sie macht kaum einen
Unterschied:

| Schwelle | dem Sensor folgen: gewertet / RMSSD | selbst prüfen: gewertet / RMSSD |
|---|---|---|
| 30 ms | 36 % / 30 ms | 78 % / 66 ms |
| **50 ms** | **37 % / 30 ms** | 81 % / 73 ms |
| 150 ms | 38 % / 31 ms | 85 % / 72 ms |
| aus | 38 % / 31 ms | 92 % / 74 ms |

Intervalle mit mehr als 50 ms Fehlerschätzung liegen mitten in
Bewegungsphasen, wo auch die Nachbarn verworfen sind. Eine weitere Schwelle
gewinnt dort keine brauchbaren Schläge. Nicht verworfene Intervalle bis 30 ms
passen fast immer zu ihren Nachbarn. Zwischen 30 und 50 ms gibt es zu wenige,
um die Schwelle enger zu ziehen.

### 13.10.2026: Verity Sense in Ruhe

- 15 min, 37 % verworfen: Die Masse der verworfenen Intervalle war von den
  behaltenen nicht zu unterscheiden (Fehlerschätzung im Median 12 gegen 11 ms,
  Nachbardifferenz 3,5 gegen 3,2 %). Selbst geprüft ergab sich RMSSD 50,0
  statt 47,6 ms bei 1119 statt 719 Schlägen.
- 3½ min, 44 % verworfen: Differenzen, an denen ein verworfenes Intervall
  beteiligt war, hatten RMSSD 43 ms, die übrigen 20 ms.

In Ruhe bringt „selbst prüfen“ also mehr Schläge, ändert die Kennzahlen aber
kaum. In Bewegung verdreifacht es RMSSD. Darum folgt die Vorgabe dem Sensor.

### Unsichere Ketten

Bis ALGO_VERSION 5 blieben unsichere Ketten (3–5 Schläge) beim Öffnen roh.
Ein Ausreißer, den die Automatik gefunden hatte, zählte also trotzdem mit,
sobald seine Nachbarn ebenfalls auffielen. Am 14.10. hob das RMSSD von 30 auf
39 ms. Interpolieren (30,4 ms) und Ausschließen (30,1 ms) liegen dagegen
gleichauf. Die Vorgabe interpoliert, wie praxis_gui, und markiert die Kette als
unsicher.

---

## Für Messungen heißt das

- **Optisch (Verity Sense) HRV nur in Ruhe:** sitzen oder liegen, den Arm
  ruhig halten. Bei der Arbeit und im Training misst der Brustgurt (H10, EKG)
  zuverlässig.
- Verwirft der Sensor mehr als die Hälfte der Intervalle, zeigt die
  Aufzeichnung einen Hinweis. Die Kennzahlen beruhen dann auf Bruchstücken,
  sind aber nicht verfälscht.

---

## Einstellen

Das Regler-Symbol neben „Korrektur“ stellt die Regeln je Aufzeichnung ein
(„Als Vorgabe merken“), dasselbe geht unter Einstellungen → HRV-Messung.
„Standardwerte“ stellt die Vorgaben wieder her.

| Regel (`Korrekturregeln`) | Vorgabe | praxis_gui |
|---|---|---|
| `sensor_verwerfung` | `sensor` (dem Sensor folgen) | – (folgt immer dem Sensor) |
| `malik_an`, `malik` | an, nach Intervallquelle (0,20 / 0,30) | Malik-Schwelle je Sitzung, 0,20 |
| `rr_min`, `rr_max` | 250 / 2000 ms | `[hrv] rr_min_ms`, `rr_max_ms` |
| `fehler_an`, `fehler_max_ms` | an, über 50 ms | – |
| `nullen` | aus | `[hrv] interpolate_zeros` (an) |
| `merge_gap`, `auto_max`, `unsicher_max`, `max_luecke_s` | 2, 2, 5, 3 s | `[hrv_gaps]` |
| `vorauswahl` | `alle` | – (`auto_correct_runs` wendet auch unsichere an) |

**„Verworfene Intervalle selbst prüfen“** ist nur für Ruhemessungen gedacht,
wenn eine durchgehende Reihe gebraucht wird (Spektrum, DFA α1). Danach lohnt
ein Blick, ob RMSSD plausibel geblieben ist.

**Gespeichert** werden die Regeln je Aufzeichnung im Sidecar
(`corrections_meta.regeln`, Vertrag 9a). Eine Aufzeichnung öffnet mit den
Regeln, mit denen sie korrigiert wurde. Die gemerkte Vorgabe liegt gerätelokal
in `app_setting` (`hrv_korrektur`) und bleibt, bis man „Standardwerte“ tippt.
Eine neue Werksvorgabe erreicht ein Gerät mit gemerkter Vorgabe darum nicht von
selbst.

---

## Verlauf

| ALGO_VERSION | Änderung |
|---|---|
| 2 (13.10.) | Nähte an vom Sensor verworfenen Intervallen und an Messlücken |
| 3 (13.10.) | Messlücken bei PPI auf der Herzuhr aller Intervalle |
| 4 (13.10.) | verworfene Intervalle selbst prüfen (Vorgabe), einstellbare Regeln, Vorauswahl „sicher“ |
| 6 (14.10.) | wieder dem Sensor folgen; Vorauswahl „alle“ |

---

## Offen

**Eichung gegen das EKG.** Alle Zahlen oben vergleichen den Sensor mit sich
selbst. Eine gleichzeitige Messung mit H10 und Verity Sense, in Ruhe und in
Bewegung, würde zeigen, ob verworfene Intervalle in Ruhe doch zählen dürfen
und wo die Fehlerschwelle am besten liegt.
