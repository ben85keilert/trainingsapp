# L07–L12 — Gliederung

Diese Lektionen entstehen ausgearbeitet, wenn wir dort ankommen. Der Grund ist
nicht Bequemlichkeit: Eine Lektion, die den Code erklärt, den wir gerade
geschrieben haben, ist genauer als eine, die ihn vorwegnimmt.

Was hier steht, ist der Rahmen — Lernziele, Inhalte, und was danach in der App
entsteht.

---

## L07 — async in Flet

**Lernziele:** Nebenläufigkeit ohne die Oberfläche zu blockieren; Aufgaben sauber
beenden.

**Inhalte**
- `page.run_task()` und warum `time.sleep()` in einem Handler die App einfriert
- Ein Timer, der pausiert, weiterläuft und abgebrochen werden kann
- `asyncio.CancelledError` richtig behandeln — der Unterschied zwischen
  „abgebrochen" und „abgestürzt"
- `contextlib.AsyncExitStack` zum Aufräumen
- **Warum ein hängender Task die App am Beenden hindert**

**Danach:** Timer in der Planansicht — Übungen mit Haltezeit laufen ab, statt nur abgehakt zu werden.

> **Stand 14.10.2026:** Der Timer ist vorab entstanden — als Werkzeug über
> jeder Ansicht (`core/timer.py`, `ui/views/timer.py`). Er rechnet auf der
> monotonen Uhr statt Ticks zu zählen; die Anzeige frischt eine Aufgabe auf
> (`page.run_task`), die sich selbst beendet, wenn der Timer steht. Die Lektion
> erklärt diesen Code; die Kopplung an Planübungen ist der Übungsteil.

---

## L08 — HRV I: RR-Intervalle

**Lernziele:** Was RR-Intervalle sind, warum es zwei Uhren gibt, wie
Zeitbereichskennzahlen entstehen.

**Inhalte**
- RR, NN, und warum ein Wert unter 250 ms kein Herzschlag ist
- **Die zwei Uhren** (`t_s`, `t_wall_s`, `tw_src`) und die Lückenerkennung
- **Boundary-Skip**: warum eine Differenz über eine Naht 21 % Fehler bedeutet
- Malik-Korrektur in zwei Durchläufen, und die Falle mit der Nullpolsterung
- SDNN mit `ddof=0`, pNN50 strikt größer — warum Details hier zählen
- Golden-Tests gegen echte Dateien aus `praxis_gui/Data/RR/`

Der Code dazu steht bereits in `hrv_core/` — diese Lektion liest ihn und baut
Teile in der Übung nach.

**Danach:** Eine aufgezeichnete Messung auswerten.

---

## L09 — HRV II: Frequenz und Nichtlineares

**Lernziele:** Spektralanalyse ohne scipy; verstehen, wo die Fallstricke liegen.

**Inhalte**
- Warum HRV überhaupt ein Spektrum hat: Atmung, Blutdruckregulation
- Resampling **linear** auf 4 Hz — und warum nicht kubisch
- **Welch selbst bauen**: Hann-Fenster, Überlappung, die Skalierungsfalle
- **Lomb-Scargle**: kein Resampling nötig, `PSD = pgram · 2T/N`
- Frequenzraster gleichverteilt mit `df = 1/T` — Log-Raster verfehlt Atempeaks
- Bänder sperren statt raten
- DFA α1 und Sample Entropy, mit dem Vorbehalt zur Abtastrate
- Validierung gegen `praxis_gui/tools/generate_hrv_dataset.py --corpus`

**Danach:** M4 — vollständige HRV-Auswertung.

> **Stand 14.10.2026:** `hrv_core/frequency.py` und `nonlinear.py` sind
> umgesetzt und gegen praxis_gui geprüft (`tests/test_frequenz.py`,
> `tests/test_nichtlinear.py`). Die Lektion liest diesen Code und baut Lomb und
> Welch in der Übung nach.

---

## L10 — Geräte und BLE

**Lernziele:** Wie Bluetooth Low Energy funktioniert; einen Sensor anbinden.

**Inhalte**
- GATT: Services, Characteristics, Notifications
- Heart Rate Service `0x180D`, Characteristic `0x2A37`
- **Der Parser-Fallstrick**: mehrere RR-Werte pro Paket, die Schleife bis zum Ende
- Rückwärtsrekonstruktion der Wanduhr, `tw_src`
- Polar PMD für EKG und PPI — **funktioniert auch mit Polar-Uhren**
- `bleak` auf dem Desktop, Wiederverbindungslogik
- **Der Sensor-Prüfstand**: messen statt Datenblätter glauben
- Warum Garmin-Uhren keine RR-Intervalle senden und was das bedeutet

**Danach:** M5 — echte Sensoren auf dem Desktop.

---

## L11 — Live-Messung, Diagramme, Limits

**Lernziele:** Kontinuierliche Daten verarbeiten und darstellen; Regeln, die
Training steuern.

**Inhalte**
- Ringpuffer und gleitende Fenster, inkrementelle Neuberechnung
- Live-Diagramme mit `flet-charts`, und warum `control.update()` hier zählt
- Aufzeichnung ins `raw-v1`-Format, alle 15 Sekunden atomar gesichert
- Limit-Regeln als pure Funktionen, Auswertung auf **festem Takt** (4 Hz)
- Hysterese und Entprellung
- **Warum Puls-Regeln in Edition A nur anzeigen dürfen** —
  `docs/recht/00_zweckbestimmung.md`

**Danach:** M6 und M7 — Messung und Trainingssteuerung.

---

## L12 — Auswertung, Export, Packaging

**Lernziele:** Verläufe darstellen; die App ausliefern.

**Inhalte**
- Aggregation in SQL statt in Python
- Verlaufsdiagramme aus `measurement`
- Benchmarks: gleiche Bedingungen, sonst ist der Verlauf wertlos
- Export und Round-Trip gegen praxis_gui
- `flet build` für Android, iOS, Desktop; Signierung; Größe
- Berechtigungen und die Erklärungen für die App-Stores

**Danach:** M8 — die App ist auslieferbar.

---

## Ausblick A — Eigene Flet-Extension

Bluetooth auf Android und iOS. So viel Dart und Flutter wie nötig,
`flutter_blue_plus`, das Extension-Template, der Foreground Service.

Der Umfang hängt davon ab, was der Spike in L02b ergibt.

## Ausblick B — Edition B

Ports und Adapter, REST, Anmeldung, Verschlüsselung, Outbox-Synchronisation,
und die praktische Umsetzung von `docs/recht/`.

Voraussetzung: Die Dokumente in `docs/recht/` sind ausgefüllt und geprüft — vor
allem `00_zweckbestimmung.md`, `30_avv.md` und `50_dsfa.md`.
