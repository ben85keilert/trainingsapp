# Kompatibilität mit `praxis_gui`

> **Dieses Dokument ist der Vertrag.** Alles, was Messdateien schreibt oder liest,
> hält sich daran. Änderungen am Format brauchen zuerst einen Eintrag hier —
> danach den Code.

Referenz: [`ben85keilert/praxis_gui`](https://github.com/ben85keilert/praxis_gui),
Verzeichnis `sensors/`. Dort ist der Schreiber `sensors/polar_h10/widget.py`
(`_save_recording`, ab Zeile ~6745) maßgeblich.

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

Der Patientenordner wird von `praxis_gui` abgeleitet, nicht gespeichert:

```
<patienten_root>/<ID>_<Nachname>__<Vorname>/
```

### Dateinamensmuster

| Muster | Bedeutung |
|---|---|
| `sensor_*.json` | Messdatei (`raw-v1`) — **das ist unser Ziel** |
| `sensor_*_analyzed.json` | Analyse-Sidecar (`analysis-v1`), von praxis_gui erzeugt |
| `sensor_*_ecg.json` | EKG-Rohsignal |
| `sensor_*_truth.json` | Wahrheitsdatei des Generators (`truth-v1`) |
| `sensor_*__c01.json` | korrigierte Fassung (`corrected-v1`) |
| `.backup_*.json` | Crash-Backup, kein Analyse-Artefakt |

> ⚠️ Der Dateiname **muss** mit `sensor_` beginnen und auf `.json` enden.
> Sonst erkennt `analysis_io.is_measurement_file()` die Datei nicht, und sie
> taucht in praxis_gui schlicht nicht auf.

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
  "titel": "Ruhemessung morgens",
  "notiz": "",
  "ereignisse": [],
  "messungen": [
    { "t_s": 0.949, "t_wall_s": 0.135, "tw_src": "m", "hf_bpm": 66, "rr_ms": 949 }
  ]
}
```

### Kopffelder

| Feld | Typ | Bedeutung |
|---|---|---|
| `behandlung_id` | int \| null | Verknüpfung zur Behandlung in praxis_gui |
| `patient_id` | int \| null | Verknüpfung zum Patienten |
| `datum` | str | `YYYY-MM-DD` |
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
| `titel`, `notiz` | str | frei |
| `ereignisse` | list | Notizanker, siehe Abschnitt 4 |
| `messungen` | list | die Messwerte |

### Ein Messwert

| Feld | Typ | Einheit | Bedeutung |
|---|---|---|---|
| `t_s` | float | **Sekunden** | **Herzuhr** — kumulierte gültige RR. Kennt keine Lücken. |
| `t_wall_s` | float | **Sekunden** | **Wanduhr** seit Aufnahmestart. **Kann negativ sein.** |
| `tw_src` | `"m"` \| `"r"` | — | `m` = gemessene Paketankunft, `r` = rückwärts rekonstruiert |
| `hf_bpm` | int | bpm | vom Gerät gemeldete (geglättete) Herzfrequenz |
| `rr_ms` | int | **Millisekunden** | das RR-/PP-Intervall. `0`, wenn das Paket keine RR enthielt. |

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

---

## 5. Geräteprofile

| ID | Name | `intervall_quelle` | Ordner | Ausreißerschwelle |
|---|---|---|---|---|
| `polar_h10` | Polar H10 | `ekg_rr` | `PolarH10` | 0.20 |
| `polar_h9` | Polar H9 | `ekg_rr` | `PolarH9` | 0.20 |
| `verity_sense` | Polar Verity Sense | `ppg_ppi` | `VeritySense` | **0.30** |
| `ble_generic` | Brustgurt (Standardprofil) | `ekg_rr` | `Brustgurt` | 0.20 |

Wir ergänzen weitere Profile (Polar-Uhren, Uhren-Broadcast) — sie ordnen sich
denselben beiden `intervall_quelle`-Werten unter. Optische Sensoren sind immer
`ppg_ppi`.

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

## 7. Regeln beim Lesen

Fremde und ältere Dateien sind unvollständig. Immer defensiv:

- `schema` kann **fehlen** (Legacy) — dann ist es eine Altdatei mit `hrv`- und
  `quality`-Block im Kopf.
- `data.get("hrv") or {}` statt `data["hrv"]`.
- `t_wall_s` kann fehlen (in `corrected-v1` ist es nicht enthalten) → Rückfall auf `t_s`.
- `t_wall_s` kann **negativ** sein.
- `intervall_quelle` kann fehlen → `ekg_rr` annehmen.
- Frequenz-Schlüssel doppelt behandeln: die Rechenfunktion liefert `lf`/`hf`,
  Live-History und alte Sidecars nutzen `lf_power`/`hf_power`.
- `lf_n`/`hf_n` liegen in Altdateien als **Bruch** vor, im aktuellen Code als **Prozent**.

---

## 8. Weitere Schemata (wir lesen sie, schreiben sie aber nicht)

| Schema | Datei | Inhalt |
|---|---|---|
| `analysis-v1` | `sensor_*_analyzed.json` | Sidecar: `derived_metrics`, `frequency_summary`, `nonlinear_summary`, `rolling_metrics`, `neurokit2_hrv_rr`, `respiration*`; dazu `source_file_sha1` zur Veraltungserkennung |
| `corrected-v1` | `sensor_*__c01.json` | korrigierte RR-Reihe; `messungen` **ohne** `t_wall_s`/`tw_src` |
| `analysis-v3` | `sensor_*/meta.json` + CSVs | Regionen, Korrekturen, `compute_log`, Zeitreihen als `t_s,value` |
| `truth-v1` | `sensor_*_truth.json` | Sollwerte des Generators — ideal für Golden-Tests |
| — | `sensor_*_ecg.json` | `sample_rate_hz`, `uv[]` (Mikrovolt), `frame_offsets`, `frame_sample_counts` |

---

## 9. Metrik-Schlüssel

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

## 10. Verlaufswerte: `Dokumentation_Skalen`

Unsere `measurement`-Tabelle (`metric_key`, `value`, `unit`, `recorded_at`)
entspricht in praxis_gui den Tabellen `Dokumentation_Skalen` (Definition der
Skala) und `Dokumentation_Skalen_Werte` (Messwerte). Beim Sync in Edition B
werden unsere `metric_key` auf Skalen-IDs abgebildet; die Zuordnung liegt in
`external_ref`.

---

## 11. Golden-Tests

`tests/golden/rr/` enthält eine echte Messdatei aus `praxis_gui/Data/RR/`.
`tests/test_kompatibilitaet.py` prüft:

1. **Lesen** — Datei einlesen, Felder und Typen gegen dieses Dokument prüfen.
2. **Round-Trip** — einlesen, schreiben, erneut einlesen; die Daten müssen
   identisch sein.
3. **Kopftreue** — eine selbst erzeugte Datei enthält alle Pflichtfelder in
   den richtigen Typen.

Für HRV-Kennzahlen liefert `praxis_gui/tools/generate_hrv_dataset.py --corpus`
15 Szenarien mit Wahrheitsdatei (`truth-v1`) — die Referenz für `hrv_core`.
