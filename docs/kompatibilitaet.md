# Kompatibilität mit `praxis_gui`

> **Dieses Dokument ist der Vertrag.** Alles, was Messdateien schreibt oder liest,
> hält sich daran. Änderungen am Format brauchen zuerst einen Eintrag hier —
> danach den Code.

Referenz: [`ben85keilert/praxis_gui`](https://github.com/ben85keilert/praxis_gui),
Verzeichnis `src/praxislab/sensors/`. Maßgebliche Stellen (Stand 2026-10-12):

| Was | Wo in praxis_gui |
|---|---|
| Schreiber der Messdatei | `polar_h10/widget.py`, `_save_recording` (Z. 8374) |
| Crash-Backup | `polar_h10/widget.py`, `_start_backup`/`_write_backup` (Z. 8049–8135) |
| Aufnahmepfad je Schlag (`t_s`, `t_wall_s`, `tw_src`) | `polar_h10/widget.py`, `_on_hr_received` (Z. 4163–4250) |
| BLE-Empfang 0x2A37 und PMD/PPI | `polar_h10/widget.py`, Z. 1495–1597; `devices/pmd.py` |
| Rückrechnung mehrerer RR je Paket | `polar_h10/virtual_worker.py`, `iter_packet_beats` (Z. 74–90) |
| `ppi_pakete` | `polar_h10/widget.py`, `_ppi_paket_eintrag` (Z. 7355), `_ppi_block` (Z. 7366) |
| Dateierkennung | `polar_h10/analysis_io.py`, `is_measurement_file` (Z. 147) |
| Korrekturen, Sidecar `analysis-v1` | `polar_h10/analysis_session.py` (`Correction` Z. 61–142, `_apply` Z. 262, `to_sidecar_dict` Z. 1743), `analysis_io.py`, `write_sidecar_minimal` (Z. 605) |

---

## 1. Grundprinzip: die Datei ist die Wahrheit

`praxis_gui` speichert **keine einzige HRV-Zahl in der Datenbank.** Die Tabelle
`Polar_Messungen` enthält nur:

```sql
Polar_Messungen(ID_Messung, ID_Patient, Datum, Dateipfad, Titel)
```

Die Messwerte liegen in JSON-Dateien im Patientenordner. Die Messungslisten der
Oberfläche entstehen sogar aus einem Dateisystem-Scan, nicht aus der Datenbank.

**Konsequenz für uns:** Wir schreiben direkt das Zielformat. Damit ist der Export
ein Dateikopiervorgang und keine Übersetzungsschicht, die auseinanderdriften kann.
Unsere SQLite-Datenbank hält Pfad, Metadaten und einen Kennzahlen-Cache — nie die
Rohdaten selbst.

---

## 2. Ablage und Dateinamen

```
<Patientenordner>/Messungen/<Geräteordner>/sensor_<YYYY-MM-DD>_<HHMMSS>.json
```

Geräteordner: `PolarH10`, `PolarH9`, `VeritySense`, `Brustgurt`, `Generator`.
praxis_gui durchsucht **nur** diese Ordner (`profiles.ordner_aller_profile()`
plus `Generator`). Eine Datei in einem anderen Ordner ist dort unsichtbar.

Der Patientenordner wird von `praxis_gui` abgeleitet, nicht gespeichert:

```
<patienten_root>/<ID>_<Nachname>__<Vorname>/
```

**Zeitstempel im Namen.** praxis_gui nimmt die *lokale* Uhrzeit beim *Stoppen*
(`datetime.now()`), das Crash-Backup dagegen die UTC-Startzeit. Wir benennen
Messdatei und Backup einheitlich nach der **UTC-Startzeit** (`Recording.dateiname()`).
Erkannt wird eine Messung ausschließlich am Muster, nicht am Zeitpunkt — die
Abweichung ist für praxis_gui folgenlos.

### Dateinamensmuster

| Muster | Bedeutung |
|---|---|
| `sensor_*.json` | Messdatei (`raw-v1`) — **das ist unser Ziel** |
| `sensor_*_analyzed.json` | Analyse-Sidecar (`analysis-v1`) — wir schreiben eine Teilmenge (Abschnitt 9) |
| `sensor_*/meta.json` | Analyse-Ordner (`analysis-v3`) von praxis_gui — wir lesen und schreiben ihn nicht |
| `sensor_*_ecg.json` | EKG-Rohsignal |
| `sensor_*_ppg.json` | optisches Rohsignal (PPG) |
| `sensor_*_truth.json` | Wahrheitsdatei des Generators (`truth-v1`) |
| `sensor_*__c01.json` | korrigierte Fassung (`corrected-v1`) |
| `sensor_*_diagnose.txt` | Verbindungsprotokoll der trainingsapp (Text, nur zur Fehlersuche). Kein JSON, darum für praxis_gui unsichtbar — dort bleibt es beim Löschen einer Messung liegen |
| `.backup_<start>.json` | Crash-Backup, kein Analyse-Artefakt (Abschnitt 6a) |
| `*.json.tmp` | Zwischenstand eines atomaren Schreibvorgangs |
| `Messungen/Sitzungen/sitzung_*.json` | Mehrgeräte-Sitzung (`sitzung-v1`), nur lesen |

> ⚠️ Der Dateiname **muss** mit `sensor_` beginnen und auf `.json` enden.
> Sonst erkennt `analysis_io.is_measurement_file()` die Datei nicht, und sie
> taucht in praxis_gui schlicht nicht auf.

### Was `ist_messdatei()` ausschließt

`hrv_core.recording.ist_messdatei()` erkennt eine Messung, wenn der Name mit
`sensor_` beginnt und auf `.json` endet, **außer**:

- `_analyzed.json`, `_ecg.json`, `_ppg.json`, `_truth.json` (Beiwerk),
- `__c<NN>.json` (korrigierte Fassung — sie gehört zur Rohdatei, nicht daneben),
- `.backup_*` und `*.tmp` (fallen schon durch Präfix bzw. Endung heraus).

praxis_gui zählt `__cNN` als Messdatei mit; wir zeigen nur die Rohdatei.

### Export

Ein Export packt die Rohdatei mit allem, was an ihrem Stamm hängt
(`sensor_<ts>.json`, `sensor_<ts>_*`, `sensor_<ts>__c*`), in ein ZIP — Pfade
relativ zum Datenverzeichnis, also `Messungen/<Geräteordner>/…`. Ausgepackt in
einen Patientenordner liegt alles dort, wo praxis_gui es sucht. Die Dateien
werden byte-genau kopiert, nicht neu geschrieben (`hrv_core.export`).
Die übrigen Ausschlüsse sind deckungsgleich.

---

## 3. Schema `raw-v1` — die Messdatei

Feldreihenfolge wie im Original-Schreiber. `json.dump(..., ensure_ascii=False, indent=2)`.

```json
{
  "behandlung_id": null,
  "patient_id": 105,
  "datum": "2026-08-06",
  "geraet": "Polar H10",
  "geraet_profil": "polar_h10",
  "intervall_quelle": "ekg_rr",
  "simulation": false,
  "generator_config": null,
  "schema": "raw-v1",
  "analyzed": false,
  "start_utc": "2026-08-06T08:15:00Z",
  "batterie_prozent": 92,
  "ecg_aufzeichnung": false,
  "ppg_aufzeichnung": false,
  "titel": "Ruhemessung morgens",
  "notiz": "",
  "ereignisse": [],
  "messungen": [
    { "t_s": 0.949, "t_wall_s": 0.135, "tw_src": "m", "hf_bpm": 66, "rr_ms": 949 }
  ]
}
```

Bei Geräten mit PPI (Verity Sense) steht zwischen `ppg_aufzeichnung` und `titel`
zusätzlich `ppi_pakete` (Abschnitt 3b). Unsere Erweiterung `datenqualitaet`
(Abschnitt 5) steht direkt hinter `intervall_quelle`. Unbekannte Felder einer
gelesenen Datei bleiben beim Schreiben erhalten und stehen am Ende.

### Kopffelder

| Feld | Typ | Bedeutung |
|---|---|---|
| `behandlung_id` | int \| null | Verknüpfung zur Behandlung in praxis_gui |
| `patient_id` | int \| null | Verknüpfung zum Patienten |
| `datum` | str | `YYYY-MM-DD`, **lokales** Datum der Messung. Beim Lesen übernehmen, nicht aus `start_utc` neu ableiten |
| `geraet` | str | Anzeigename, i. d. R. der BLE-Gerätename |
| `geraet_profil` | str | Profil-ID, siehe Abschnitt 5 |
| `intervall_quelle` | str | **Pflicht** — `ekg_rr` oder `ppg_ppi` |
| `simulation` | bool | `true` ⇒ Ablage unter `Messungen/Generator/` |
| `generator_config` | dict \| null | Syntheseparameter, nur bei Simulation |
| `schema` | str | `"raw-v1"` |
| `analyzed` | bool | beim Schreiben immer `false` |
| `start_utc` | str | `%Y-%m-%dT%H:%M:%SZ` |
| `batterie_prozent` | int \| null | |
| `ecg_aufzeichnung` | bool | ob parallel EKG aufgezeichnet wurde |
| `ppg_aufzeichnung` | bool | ob parallel PPG-Rohsignal aufgezeichnet wurde. praxis_gui schreibt es immer; wir schreiben `false` |
| `ppi_pakete` | list | **nur** bei Geräten mit PPI, Abschnitt 3b. Eine H10-Datei hat den Schlüssel nicht |
| `sitzung_id` | str | nur im Mehrgerätebetrieb von praxis_gui; wir lesen und erhalten ihn, schreiben ihn nicht |
| `titel`, `notiz` | str | frei |
| `ereignisse` | list | Notizanker, siehe Abschnitt 4 |
| `messungen` | list | die Messwerte |

### Ein Messwert

| Feld | Typ | Einheit | Bedeutung |
|---|---|---|---|
| `t_s` | float | **Sekunden** | **Herzuhr** — kumulierte gültige RR (Regel in 3a). Kennt keine Lücken. |
| `t_wall_s` | float | **Sekunden** | **Wanduhr** seit Aufnahmestart. **Kann negativ sein.** |
| `tw_src` | `"m"` \| `"r"` \| `"g"` | — | `m` = gemessene Paketankunft, `r` = rückwärts rekonstruiert, `g` = Generator (nur lesen) |
| `hf_bpm` | int | bpm | vom Gerät gemeldete (geglättete) Herzfrequenz |
| `rr_ms` | int | **Millisekunden** | das RR-/PP-Intervall. `0`, wenn das Paket keine RR enthielt. |

Reihenfolge innerhalb eines Messwerts: `t_s, t_wall_s, tw_src, hf_bpm, rr_ms`.
Zeiten auf 3 Nachkommastellen gerundet.

### 3a. Schreibregeln je Schlag (Verhalten von praxis_gui, übernommen)

1. **Jede Zeile wird geschrieben** — auch `rr_ms = 0` und implausible Werte,
   immer mit dem Rohwert. Korrigiert wird nie in der Rohdatei.
2. **Herzuhr:** `t_s` wächst nur, wenn `300 ≤ rr_ms ≤ 2000`. Sonst bleibt
   `t_s` stehen (die Zeile trägt den unveränderten Wert des Vorgängers).
   Gerechnet wird in ganzen Millisekunden, `t_s = round(summe_ms / 1000, 3)`.
   > ⚠️ Die Rechenfunktionen filtern dagegen mit **250**–2000 ms
   > (`RR_MIN_MS`). Das ist in praxis_gui genauso uneinheitlich — für die
   > Datei gilt 300, damit `t_s` byte-gleich entsteht.
3. **Wanduhr:** `t_wall_s = round(t_capture − t_start, 3)`, beide aus derselben
   monotonen Uhr (`time.monotonic()`), nie aus `datetime.now()`.
4. **Mehrere RR in einem Paket:** der letzte Schlag bekommt die Ankunftszeit
   (`tw_src = "m"`), frühere `t_capture − Σ nachfolgende RR` (`tw_src = "r"`).
5. **Brustgurt (H10), Paket ohne RR:** eine Zeile mit `rr_ms = 0`,
   `tw_src = "m"`, `t_s` unverändert.
6. **Optischer Sensor (Verity Sense):**
   - Das Standardprofil 0x2A37 trägt dort **keine** Intervalle. Solche Pakete
     sind nur Lebenszeichen und erzeugen **keine** Zeile.
   - Die Intervalle kommen aus dem PMD-PPI-Strom, rund fünf je Paket. Die
     Rückrechnung läuft über **alle** Intervalle des Pakets (auch die vom
     Gerät verworfenen — sie haben gedauert); erst danach fallen Intervalle
     mit Blocker-Bit oder `ppi_ms = 0` heraus.
   - `hf_bpm` jeder Zeile eines Pakets = Herzfrequenz-Byte der **letzten
     brauchbaren** Probe dieses Pakets.

### 3b. `ppi_pakete` (nur Geräte mit PPI)

Jedes PMD-PPI-Paket roh, einschließlich der vom Gerät verworfenen Intervalle —
die Zutaten, aus denen praxis_gui später die „Kontinuitätsuhr" rekonstruiert
(`devices/zeitachse.py`). Spaltenweise, alle Listen gleich lang:

```json
"ppi_pakete": [
  { "t_wall_s": 31.204, "ppi_ms": [812, 830, 845, 0, 820],
    "fehler_ms": [6, 7, 9, 0, 6], "blocker": [0, 0, 1, 1, 0], "kontakt": [1, 1, 1, 1, 1] }
]
```

| Spalte | Bedeutung |
|---|---|
| `t_wall_s` | Paketankunft, gleicher Nullpunkt wie `messungen[].t_wall_s`, 3 Nachkommastellen |
| `ppi_ms` | alle Intervalle des Pakets in ms |
| `fehler_ms` | Fehlerschätzung des Geräts je Intervall in ms |
| `blocker` | `1` = vom Gerät als unbrauchbar markiert |
| `kontakt` | `1` = Hautkontakt erkannt |

Bei einem PPI-Gerät steht der Schlüssel auch dann in der Datei, wenn kein
einziges Paket ankam (`[]`). Fehlt er in einer Datei, gilt die Ankunftsachse.

---

## 4. Die zwei Uhren — das wichtigste Designdetail

Jeder Messpunkt trägt zwei Zeitachsen:

- **`t_s` — Herzuhr.** Summe aller bisherigen gültigen RR-Intervalle. Sie
  „überspringt" Lücken, weil fehlende Schläge nicht mitgezählt werden.
- **`t_wall_s` — Wanduhr.** Reale Zeit seit Aufnahmestart, aus `time.monotonic()`.

**Die Differenz beider zeigt Verbindungslücken.** Ohne `t_wall_s` verschwindet
eine Messlücke spurlos und ihre Ränder werden stillschweigend linear überbrückt.

`tw_src` unterscheidet, woher der Wanduhrwert stammt. Eine BLE-Notification kann
mehrere RR-Werte enthalten; der Ankunftszeitpunkt gehört zum **letzten**.
Die vorherigen werden rückwärts rekonstruiert:

```python
offset_s = sum(rr[i + 1 :]) / 1000.0
t_wall = t_capture - offset_s  # tw_src = "r"
```

> ⚠️ Rekonstruierte Zeitstempel sind systematisch etwas zu früh. Sie dürfen
> **nie** als Stützstellen der Spektralanalyse dienen — das hebt HF um 9–10 %.
> Die Lückenerkennung arbeitet deshalb auf der kumulativen Divergenz über ein
> Fenster von ±5 Schlägen, nicht auf Einzeldifferenzen.

Am Verity Sense ist die Paketankunft **nicht** der Schlagzeitpunkt: das Armband
stellt rund alle 5 s gebündelt und rund 5 s verzögert zu. `tw_src = "m"` heißt
dort nur „letzter Schlag des Pakets". RMSSD und SDNN sind davon nicht betroffen,
Lückenerkennung und Frequenzanalyse schon.

### Ereignisse (Notizanker)

Neues Format:

```json
{ "beat_index": 731, "dt_s": 0.35, "t_wall_s": 631.42, "t_s": 612.0,
  "wall_time": "10:42:11", "text": "Atemübung Start" }
```

`beat_index` ist die Wahrheit (Index in `messungen`, `null` = vor dem ersten
Schlag), `dt_s` der Versatz zum Ankerschlag, `t_s` **abgeleitet** — nie manuell
setzen.

Altes Format (nur lesen): `{"t_s": …, "chart_x": …, "wall_time": …, "text": …}`.

**Wir schreiben Ereignisse** im neuen Format, Feldfolge
`beat_index, dt_s, t_wall_s, t_s, wall_time, text` (`hrv_core/ereignisse.py`,
Portierung von praxis_gui `event_anchor.py`; gegen das Original auf den
Golden-Dateien und einer echten Verity-Messung geprüft, 36 000 Fälle
identisch):

- `dt_s` ist auf das folgende Schlagintervall der **Herzuhr der Datei**
  begrenzt — eine Notiz rutscht nie über den nächsten Schlag hinaus; in einer
  Lücke landet sie an deren Beginn, `t_wall_s` behält den echten Zeitpunkt.
- **Live** ankert „jetzt" über die Wanduhr (`anker_aus_wand`) auf den bisher
  geschriebenen Zeilen; die Ereignisse stehen in Backup und Messdatei.
- **Nachträglich** (Tippen in die Kurve, Verschieben) ankert die Position auf
  der Zeitachse der Kurve (`anker_aus_achse`; bei der Verity Sense die
  Herzuhr aller Intervalle, `ppi.schlagzeiten`) über dieselbe Rechnung.
- `wall_time` ist die lokale Uhrzeit aus `start_utc + t_wall_s`; unbekannte
  Felder eines Ereignisses aus praxis_gui bleiben beim Bearbeiten erhalten.

---

## 5. Geräteprofile

| ID | Name | `intervall_quelle` | Ordner | Ausreißerschwelle |
|---|---|---|---|---|
| `polar_h10` | Polar H10 | `ekg_rr` | `PolarH10` | 0.20 |
| `polar_h9` | Polar H9 | `ekg_rr` | `PolarH9` | 0.20 |
| `verity_sense` | Polar Verity Sense | `ppg_ppi` | `VeritySense` | **0.30** |
| `ble_generic` | Brustgurt (Standardprofil) | `ekg_rr` | `Brustgurt` | 0.20 |

> ⚠️ In praxis_gui steht die 0.30 zwar im Profil, wird aber von keiner
> Codestelle gelesen — dort wird überall mit 0.20 gerechnet. Bei uns wirkt
> die Schwelle tatsächlich. Kennzahlen optischer Messungen nach Korrektur
> können deshalb leicht von praxis_gui abweichen.

Wir ergänzen weitere Profile (Polar-Uhren, Uhren-Broadcast) — sie ordnen sich
denselben beiden `intervall_quelle`-Werten unter. Optische Sensoren sind immer
`ppg_ppi`. Unbekannte Profil-IDs behandelt praxis_gui wie `ble_generic`.

### Unsere Erweiterung: `datenqualitaet`

Zusätzlicher Schlüssel im Kopf. `praxis_gui` liest defensiv und ignoriert
unbekannte Felder — der Vertrag bleibt unverletzt.

| Wert | Quelle | HRV-Analyse |
|---|---|---|
| `rr_ekg` | Brustgurt, RR aus EKG | vollständig |
| `ppi_optisch` | optischer Sensor mit PPI/RR | vollständig, Schwelle 0.30, Frequenzwerte mit Vorbehalt |
| `bpm_only` | Gerät sendet nur BPM | **keine HRV** — nur Pulsverlauf |

Für `bpm_only` passt `raw-v1` bereits: `rr_ms = 0`, wie praxis_gui es bei
Notifications ohne RR-Feld selbst schreibt.

---

## 6. Regeln beim Schreiben

1. Dateiname `sensor_<YYYY-MM-DD>_<HHMMSS>.json`.
2. `intervall_quelle` **immer** setzen. Fehlt sie, nimmt praxis_gui `ekg_rr` an —
   und eine PPG-Messung landet unbemerkt in einer EKG-Kurve.
3. `rr_ms` als **int in Millisekunden**, `t_s`/`t_wall_s` als float in Sekunden.
4. `t_wall_s` **und** `tw_src` mitliefern, sonst ist keine Lückenerkennung möglich.
5. `analyzed: false` und **keinen** `hrv`-Block schreiben. Die Nachberechnung
   gehört praxis_gui; sie setzt `analyzed` und legt das Sidecar an.
6. Bei Simulation/Testdaten `"simulation": true` **und** Ablage unter
   `Messungen/Generator/`. Sonst landet Synthetik in einer Patientenakte.
7. `ppg_aufzeichnung` immer schreiben (bei uns `false`); `ppi_pakete` genau
   dann, wenn das Gerät PPI liefert.
8. **Atomar schreiben:** erst `<ziel>.tmp`, dann `os.replace`. Ein Absturz
   mitten im Schreiben hinterlässt so nie eine halbe Messdatei. (praxis_gui
   schreibt die endgültige Datei nicht atomar — für den Leser ist das gleich.)
9. Die Schreibregeln je Schlag aus Abschnitt 3a gelten ohne Ausnahme.
10. **Nachträglich nur Metadaten.** `titel`, `notiz` und `ereignisse` dürfen
    in einer gespeicherten Messdatei geändert werden — wie praxis_gui
    (`workbench._write_raw_metadata`). Die Datei wird als JSON gelesen und mit
    unveränderter Schlüsselfolge zurückgeschrieben (`indent=2`,
    `ensure_ascii=False`, atomar); `messungen`, `ppi_pakete` und alle übrigen
    Felder bleiben Wert für Wert. Danach bekommt ein vorhandenes Sidecar die
    neue Prüfsumme (`source_file_sha1`, wie `analysis_io.refresh_sidecar_sha1`),
    und `hrv_recording.sha1` wird nachgeführt. Alles andere bleibt
    unveränderlich (`hrv_core.ereignisse.metadaten_schreiben` weist es ab).

### 6a. Crash-Backup `.backup_<start>.json`

Während der Aufnahme legt praxis_gui **alle 15 s** eine Sicherung im selben
Ordner ab wie die spätere Messdatei:

```
Messungen/<Geräteordner>/.backup_<YYYY-MM-DD>_<HHMMSS>.json     # UTC-Startzeit
```

- Inhalt: derselbe `raw-v1`-Kopf und dieselben `messungen`/`ppi_pakete` wie die
  Messdatei, kompakt geschrieben (`separators=(",", ":")`), atomar über `.tmp`.
- praxis_gui legt zusätzlich einen `hrv`-Block mit Live-Werten hinein
  (`"_scope": "live_window"`). **Wir nicht** — ein Backup ist Rohdatenrettung,
  keine Analyse.
- Nach erfolgreichem Speichern der Messdatei wird das Backup gelöscht. Bleibt
  eines liegen, war die Aufnahme nicht ordentlich beendet.
- Der Punkt am Anfang hält es aus jeder Messungsliste heraus.

## 7. Regeln beim Lesen

Fremde und ältere Dateien sind unvollständig. Immer defensiv:

- `schema` kann **fehlen** (Legacy) — dann ist es eine Altdatei mit `hrv`- und
  `quality`-Block im Kopf.
- `data.get("hrv") or {}` statt `data["hrv"]`.
- `t_wall_s` kann fehlen (in `corrected-v1` ist es nicht enthalten) → Rückfall auf `t_s`.
- `t_wall_s` kann **negativ** sein.
- `intervall_quelle` kann fehlen → `ekg_rr` annehmen.
- `datum` aus der Datei übernehmen, auch wenn es nicht zum UTC-Datum von
  `start_utc` passt (Messung kurz nach Mitternacht Ortszeit).
- Frequenz-Schlüssel doppelt behandeln: die Rechenfunktion liefert `lf`/`hf`,
  Live-History und alte Sidecars nutzen `lf_power`/`hf_power`.
- `lf_n`/`hf_n` liegen in Altdateien als **Bruch** vor, im aktuellen Code als **Prozent**.

---

## 8. Weitere Schemata (wir lesen sie, schreiben sie aber nicht)

| Schema | Datei | Inhalt |
|---|---|---|
| `analysis-v1` | `sensor_*_analyzed.json` | Sidecar: `derived_metrics`, `frequency_summary`, `nonlinear_summary`, `rolling_metrics`, `neurokit2_hrv_rr`, `respiration*`; dazu `source_file_sha1` zur Veraltungserkennung. **Teilmenge schreiben wir**, Abschnitt 9 |
| `corrected-v1` | `sensor_*__c01.json` | korrigierte RR-Reihe; `messungen` **ohne** `t_wall_s`/`tw_src` |
| `analysis-v3` | `sensor_*/meta.json` + CSVs | Regionen, Korrekturen (`rr_corrections`), `compute_log`, Zeitreihen als `t_s,value` |
| `sitzung-v1` | `Messungen/Sitzungen/sitzung_*.json` | Mehrgeräte-Aufnahme: `teilnehmer[]` mit `geraet`, `adresse`, `geraet_profil`, `intervall_quelle`, `ordner`, `datei`, `n_schlaege` |
| `truth-v1` | `sensor_*_truth.json` | Sollwerte des Generators — ideal für Golden-Tests |
| — | `sensor_*_ecg.json` | `sample_rate_hz`, `uv[]` (Mikrovolt), `frame_offsets`, `frame_sample_counts` |
| — | `sensor_*_ppg.json` | `sample_rate_hz`, `kanaele`, `kanal_namen`, `werte[]`, `frame_offsets`, `frame_sample_counts` |

> ⚠️ `frame_offsets` zählt in praxis_gui die **empfangenen** Samples, nicht den
> Geräte-Zeitstempel. Lücken im EKG lassen sich daraus nicht erkennen.

---

## 9. `analysis-v1`-Teilmenge, die wir schreiben

Nachträgliche RR-Korrekturen speichern wir dort, wo praxis_gui sie beim Öffnen
einer Messung liest (`workbench.py:2047` → `AnalysisSession.load_sidecar`):
`sensor_<ts>_analyzed.json` neben der Rohdatei. **Die Rohdatei bleibt
unangetastet.**

```json
{
  "schema": "analysis-v1",
  "source_file": "sensor_2026-05-23_125422.json",
  "corrections": [
    { "op": "interpolate", "beat_index": 123, "t_s": 98.765, "original_value_ms": 1650.0 },
    { "op": "interpolate", "beat_index": 124, "t_s": 99.6, "original_value_ms": 0.0, "unsicher": true },
    { "op": "exclude_range", "beat_index": 200, "t_s": 170.2, "original_value_ms": 0.0, "beat_index_end": 212 }
  ],
  "corrections_meta": {
    "malik_threshold": 0.2, "corrections_total": 3,
    "corrections_by_op": { "interpolate": 2, "exclude_range": 1 },
    "rr_min_ms": 250, "rr_max_ms": 2000, "interpolate_zeros": true
  },
  "rr_corrected": [ { "t_s": 0.976, "rr_ms": 976, "flag": "orig" } ],
  "source_file_sha1": "…",
  "updated_utc": "2026-10-12T08:00:00Z"
}
```

| Feld | Regel |
|---|---|
| `corrections[]` | sortiert nach `beat_index` (Index im **rohen** `messungen`-Array; Erweiterung für die Folge aller PPI-Intervalle: Abschnitt 9a). Wir erzeugen `interpolate`, `delete`, `exclude_range`; gelesen und angewendet werden auch praxis_gui-Einträge `set_value` (`value_ms`), `split` (`n_parts`), `merge` (`with_next`) |
| `t_s` | 3 Nachkommastellen; `original_value_ms` 1 Nachkommastelle, fehlt bei praxis_gui-`exclude_range` |
| `unsicher` | nur geschrieben, wenn `true` |
| `beat_index_end` | nur bei `exclude_range`, einschließlich |
| `rr_corrected[]` | die korrigierte Reihe: `t_s` = Onset + kumulierte korrigierte RR (4 Stellen), `rr_ms` gerundet, `flag ∈ orig, interp, set, split, merge` |
| `source_file_sha1` | SHA1 der Rohdatei — daran erkennt praxis_gui ein veraltetes Sidecar |

### 9a. Unsere Erweiterung: Regeln und `corrections_ppi`

Zwei zusätzliche Schlüssel, die praxis_gui nicht kennt (und als unbekannte
Felder übergeht):

| Feld | Regel |
|---|---|
| `corrections_meta.regeln` | die `Korrekturregeln`, mit denen die Korrektur entstand (`hrv_core/regeln.py`): `sensor_verwerfung` (`selbst`/`sensor`), `malik_an`, `malik` (`null` = nach Intervallquelle), `rr_min`, `rr_max`, `fehler_an`, `fehler_max_ms`, `nullen`, `merge_gap`, `auto_max`, `unsicher_max`, `max_luecke_s`, `vorauswahl`. `malik_threshold`, `rr_min_ms`, `rr_max_ms`, `interpolate_zeros` stehen weiterhin daneben — mit den daraus wirksamen Werten |
| `corrections_ppi[]` | nur bei `sensor_verwerfung = "selbst"` mit wieder aufgenommenen Intervallen: dieselben Einträge wie `corrections`, aber `beat_index` zählt in der Folge **aller** Intervalle aus `ppi_pakete` mit `ppi_ms > 0` (auch der vom Gerät verworfenen) |

Ist `corrections_ppi` geschrieben, steht unter `corrections` (und
`rr_corrected`) seine Abbildung auf die Zeilen von `messungen`
(`korrektur.auf_zeilen`): Korrekturen nur an verworfenen Intervallen entfallen
dort, ein Ausschluss schrumpft auf die enthaltenen Zeilen. praxis_gui sieht
also eine gültige, vollständige Korrektur seiner eigenen Reihe.

Beim Lesen gilt `corrections_ppi` nur, solange seine Abbildung genau
`corrections` ergibt. Hat praxis_gui die Korrekturen inzwischen geändert,
gelten dessen `corrections`, übertragen auf die Folge aller Intervalle
(`korrektur.von_zeilen`). Ein Sidecar ohne `regeln` (praxis_gui, ältere
Fassungen) liefert Malik-Schwelle, Grenzen und Nullen aus `corrections_meta`.

**Bestehende Sidecars werden fortgeschrieben, nicht ersetzt:** alle Felder, die
wir nicht kennen (`segments`, `metric_params`, `derived_metrics`,
`frequency_summary`, `active_crop` …), bleiben erhalten. Abgeleitete Werte von
praxis_gui können danach zu alten Korrekturen gehören — praxis_gui hält es beim
eigenen Speichern genauso.

---

## 10. Metrik-Schlüssel

Für Serialisierung und Anzeige verwendet praxis_gui:

```
Gerät:      bpm (bpm) · rr (ms) · bpm_rr (bpm)
Berechnet:  rmssd (ms) · sdnn (ms) · pnn50 (%) · mean_rr (ms) · mean_bpm (bpm)
            hf_power (ms²) · lf_power (ms²) · vlf (ms²) · lf_hf (–) · total_power (ms²)
            sd1 (ms) · sd2 (ms) · sd1_sd2 (–) · dfa_alpha1 (–)
Zeitgesteuert: sampen (–) · resp_rate (1/min) · rsa_amp (ms)
```

Diese Schlüssel gelten auch in unserem `hrv_metrics_cache` und in `measurement`.

---

## 11. Verlaufswerte: `Dokumentation_Skalen`

Unsere `measurement`-Tabelle (`metric_key`, `value`, `unit`, `recorded_at`)
entspricht in praxis_gui den Tabellen `Dokumentation_Skalen` (Definition der
Skala) und `Dokumentation_Skalen_Werte` (Messwerte). Beim Sync in Edition B
werden unsere `metric_key` auf Skalen-IDs abgebildet; die Zuordnung liegt in
`external_ref`.

---

## 12. Golden-Tests

`tests/golden/rr/` enthält eine echte Messdatei aus `praxis_gui/Data/RR/`.
`tests/test_kompatibilitaet.py` prüft:

1. **Lesen** — Datei einlesen, Felder und Typen gegen dieses Dokument prüfen.
2. **Round-Trip** — einlesen, schreiben, erneut einlesen; die Daten müssen
   identisch sein.
3. **Kopftreue** — eine selbst erzeugte Datei enthält alle Pflichtfelder in
   den richtigen Typen.

`tests/test_hrv_aufnahme.py` hält die Schreibregeln aus 3a/3b und das Backup
fest, `tests/test_korrektur.py` die automatische Korrektur und das Sidecar aus
Abschnitt 9 — dort mit festgehaltenen Kennzahlen der Golden-Datei.

Für HRV-Kennzahlen liefert `praxis_gui/tools/generate_hrv_dataset.py --corpus`
15 Szenarien mit Wahrheitsdatei (`truth-v1`) — die Referenz für `hrv_core`.
