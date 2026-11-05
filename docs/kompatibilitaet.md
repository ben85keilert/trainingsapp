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
| `sensor_*_ecg.json` | EKG-Rohsignal — von praxis_gui; seit 30.10.2026 auch von dieser App (Polar H10, nur mit Schalter „EKG mitschreiben“; `hrv_core.ekg`, Erweiterungen `frame_t_ns`, `gaps`, `t_wall_start_s`, `batterie`) |
| `sensor_*_ppg.json` | optisches Rohsignal (PPG) |
| `sensor_*_truth.json` | Wahrheitsdatei des Generators (`truth-v1`) |
| `sensor_*__c01.json` | korrigierte Fassung (`corrected-v1`) |
| `sensor_*_diagnose.txt` | Verbindungsprotokoll der trainingsapp (Text, nur zur Fehlersuche). Kein JSON, darum für praxis_gui unsichtbar — dort bleibt es beim Löschen einer Messung liegen |
| `sensor_*_mitschnitt.jsonl` | Rohmitschnitt des Diagnosemodus (`mitschnitt-v1`, seit 4.11.2026, Abschnitt 14): jedes Bluetooth-Paket, Marken, Kontext. JSON Lines, für praxis_gui unsichtbar |
| `sensor_*_atem.json` | Atemphasen aus dem Prototyp (`atem-v1`, seit 5.11.2026, Abschnitt 15): Beiwerk neben der Messdatei — Beginn von Ein- und Ausatmen, Rate je Prüffenster, erfasste Läufe, seit Teil 2 des Taktgebers dazu die Soll-Phasen des Takts (Feld `takt`); Zeiten auf der Wanduhr der Messung. Ergebnis, keine Rohdaten; für praxis_gui unbekanntes Beiwerk |
| `.backup_<start>_ecg.jsonl`, `.backup_<start>_mitschnitt.jsonl`, `.backup_<start>_atem.jsonl` | Begleit-Journale des Crash-Backups (Abschnitt 6a) |
| `Diagnose/<ts>_<gerät>/` | Rohmitschnitt **ohne** Messung (unbekanntes Gerät, Geräteprobe) — absichtlich nicht unter `Messungen/` |
| `.backup_<start>.json` | Crash-Backup, kein Analyse-Artefakt (Abschnitt 6a) |
| `*.json.tmp` | Zwischenstand eines atomaren Schreibvorgangs |
| `Messungen/Sitzungen/sitzung_*.json` | Mehrgeräte-Sitzung (`sitzung-v1`), nur lesen |

> ⚠️ Der Dateiname **muss** mit `sensor_` beginnen und auf `.json` enden.
> Sonst erkennt `analysis_io.is_measurement_file()` die Datei nicht, und sie
> taucht in praxis_gui schlicht nicht auf.

### Was `ist_messdatei()` ausschließt

`hrv_core.recording.ist_messdatei()` erkennt eine Messung, wenn der Name mit
`sensor_` beginnt und auf `.json` endet, **außer**:

- `_analyzed.json`, `_ecg.json`, `_ppg.json`, `_truth.json` und seit 5.11.2026 `_atem.json`
  (Beiwerk, `hrv_core.recording._KEINE_MESSDATEI`),
- `__c<NN>.json` (korrigierte Fassung — sie gehört zur Rohdatei, nicht daneben),
- `.backup_*`, `*.tmp` und `*.jsonl` (fallen schon durch Präfix bzw. Endung heraus —
  darum braucht der Mitschnitt keinen Eintrag in der Liste; `hrv_core.deid` kennt seine
  Endung trotzdem als Beiwerk, `BEIWERK_SUFFIXE`).

praxis_gui zählt `__cNN` als Messdatei mit; wir zeigen nur die Rohdatei.

### Export

Ein Export packt die Rohdatei mit allem, was an ihrem Stamm hängt
(`sensor_<ts>.json`, `sensor_<ts>_*`, `sensor_<ts>__c*`), in ein ZIP — Pfade
relativ zum Datenverzeichnis, also `Messungen/<Geräteordner>/…`. Ausgepackt in
einen Patientenordner liegt alles dort, wo praxis_gui es sucht. Die Dateien
werden kopiert, nicht neu gerechnet (`core.hrv_export`) — mit **einer** Ausnahme
(Ben, 20.10.2026, Sicherheitsdurchsicht S10): Die Kopie der Messdatei verliert den
Schlüssel `adresse` (Bluetooth-Adresse des Sensors), das Diagnoseprotokoll bekommt
maskierte Adressen (`E2:B4:CC:xx:xx:xx`, `0F1E2D3C-xxxx-…`). Die Kopie wird mit
denselben Parametern geschrieben wie das Original (`ensure_ascii=False, indent=2`)
und ist bis auf diese Zeile byteidentisch; Dateien ohne `adresse` bleiben
byteidentisch. Dasselbe gilt für den Forschungsexport einer Einheit
(`core.forschung`) und das Teilen des Protokolls aus der Live-Ansicht. Die
Originaldatei auf dem Gerät behält die Adresse. Der **Rohmitschnitt** (Abschnitt 14)
geht nur bereinigt hinaus: Zeile für Zeile durch `hrv_core.deid.mitschnitt_zeilen`
(Adressen maskiert, Gerätename auf das Modell gekürzt, Zeilen von Gerätename,
Systemkennung und Seriennummer entfernt, Unbekanntes entfernt).
Das **Atem-Beiwerk** `sensor_<ts>_atem.json` (Abschnitt 15, seit 5.11.2026) geht wie das
EKG-Beiwerk mit: Dateikopie am Stamm, byteidentisch; `hrv_core.deid` behält alle Felder
(`REGELN["atem-v1"]`) — die Datei trägt nur die Profil-ID des Geräts, nie Name, Adresse,
Seriennummer oder Ort.
Die übrigen Ausschlüsse sind deckungsgleich.

**Seit dem 26.10.2026 liegt neben `Messungen/` der Ordner `Bewegung/`** (Ben: „Für HRV
reicht die Entfernung — bitte keine GPS-Koordinaten … nimm die Höhe mit“): zu jedem
Training, das an einer exportierten Messung hängt, die Streckendatei als **Rohspur ohne
Ort** (Abschnitt 13). Die Messdateien bleiben unverändert; praxis_gui sieht den Ordner
nicht (es liest nur `Messungen/<Geräteordner>/`), `ist_messdatei()` ebenso wenig.
Koordinaten enthält kein Messungs-Export — die Strecke mit Koordinaten gibt es nur als
GPX auf ausdrückliche Handlung (`docs/plan_gps.md` §0, Eigenverantwortung).

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
(Abschnitt 5) steht direkt hinter `intervall_quelle`, unsere Erweiterung `atmung`
(Abschnitt 5, seit 5.11.2026) direkt hinter `datenqualitaet`. Unbekannte Felder einer
gelesenen Datei bleiben beim Schreiben erhalten und stehen am Ende.

### Kopffelder

| Feld | Typ | Bedeutung |
|---|---|---|
| `behandlung_id` | int \| null | Verknüpfung zur Behandlung in praxis_gui |
| `patient_id` | int \| null | Verknüpfung zum Patienten |
| `datum` | str | `YYYY-MM-DD`, **lokales** Datum der Messung. Beim Lesen übernehmen, nicht aus `start_utc` neu ableiten |
| `geraet` | str | Anzeigename, i. d. R. der BLE-Gerätename; `Unbekannt`, wenn der Gurt keinen Namen meldet (nie die Adresse — Ben, 19.10.2026) |
| `geraet_profil` | str | Profil-ID, siehe Abschnitt 5 |
| `adresse` | str | **optional**, seit 19.10.2026: BLE-Adresse des Geräts (Android/Linux MAC, macOS/iOS UUID), nie bei Simulation. Pseudo-Identifikator — `hrv_core.deid` leert das Feld; praxis_gui erhält es als unbekanntes Feld. Dateien ohne Adresse haben den Schlüssel nicht. **Der Export entfernt das Feld** (seit 20.10.2026, S10): nur die Originaldatei auf dem Gerät trägt es, keine Kopie, die das Gerät verlässt (Abschnitt 2, „Export“) |
| `intervall_quelle` | str | **Pflicht** — `ekg_rr` oder `ppg_ppi` |
| `datenqualitaet` | str | **unsere Erweiterung**, direkt hinter `intervall_quelle`: `rr_ekg`, `ppi_optisch`, `bpm_only` (Abschnitt 5) |
| `atmung` | dict | **unsere Erweiterung**, seit 5.11.2026 (geschrieben seit 0.3.46): Protokollfeld „Atmung“ — wie geatmet wurde (`spontan`, `getaktet`, `uebung`), beim Schreiben der App direkt hinter `datenqualitaet`, nach `Recording.to_dict` (Zusammenfügen, Zuschneiden) am Ende; fehlt = unbekannt (Abschnitt 5) |
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
| `fehler_ms` | Fehlerschätzung des Geräts je Intervall in ms (Polar `errorEstimate`: erwarteter absoluter Fehler; unter 10 ms sehr genau, über 30 ms meist Bewegung) |
| `blocker` | `1` = vom Gerät als unbrauchbar markiert (Polar `blockerBit`: Bewegung erkannt) |
| `kontakt` | `1` = Hautkontakt erkannt — bei Verity Sense und OH1 laut Polar unzuverlässig |

Was die App aus den drei Spalten macht: [korrektur.md](korrektur.md).

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

### Unsere Erweiterung: `uebungen` im Ereignis (seit 14.10.2026)

Nennt eine Notiz Übungen aus dem Katalog der App (meist per Tipp eingesetzt),
steht hinter `text` die Liste ihrer **Kurzcodes**:

```json
{ "beat_index": 731, "dt_s": 0.35, "t_wall_s": 631.42, "t_s": 612.0,
  "wall_time": "10:42:11", "text": "Kniebeuge, dann Planke",
  "uebungen": ["7DQ2MA4K", "C3XN0PRT"] }
```

- **Kurzcode** = die ersten 40 Bit des SHA-1 der Übungs-ID (UUID in
  Kleinschrift, UTF-8) als **8 Zeichen** Crockford-Base32 (`core/kurzcode.py`).
  Die UUID selbst (36 Zeichen) wäre unnötig lang. Die App löst einen Code nur
  gegen den eigenen Katalog auf; mit 8 Zeichen liegt die Chance einer Doppelung
  bei 10 000 Übungen bei 0,005 % (6 Zeichen: 4,5 % — zu knapp für große
  Praxis-Kataloge). Die erste Fassung (14.10.2026, Build 70) schrieb 6 Zeichen;
  das sind die ersten 6 des heutigen Codes, sie werden weiter aufgelöst.
- **Welche Übungen** eine Notiz nennt, ergibt sich beim Speichern aus dem Text:
  ganze Namen des Katalogs, längere zuerst („Kniebeuge einbeinig" vor
  „Kniebeuge"), in der Reihenfolge im Text. Wer den Namen löscht, löscht den
  Verweis. Ist „Übungen in Notizen" ausgeschaltet, bleibt ein vorhandenes Feld
  unverändert.
- Nennt die Notiz keine Übung, **fehlt** das Feld.
- **praxis_gui** liest das Feld nicht und behält es beim Bearbeiten
  (`events_widget._on_save` kopiert das ganze Ereignis) — der Vertrag bleibt
  unverletzt.

### Unsere Erweiterung: `marke` im Ereignis (seit 17.10.2026)

Setzt nicht die Person eine Notiz, sondern ein Ablauf der App (Timer, Plan-Ablauf,
GPS-Training), sagt `marke` maschinenlesbar, **wer** sie setzte und **was** sie
bedeutet (Ben, 17.10.2026: „typisiert“ — für spätere Auswertungen, z. B. DFA α1
gegen RMSSD je Belastung). Die Marke steht hinter `text` bzw. `uebungen`:

```json
{ "beat_index": 731, "dt_s": 0.35, "t_wall_s": 631.42, "t_s": 612.0,
  "wall_time": "10:42:11", "text": "Planke (Runde 2/3)", "uebungen": ["C3XN0PRT"],
  "marke": { "quelle": "timer", "art": "abschnitt", "spur": "timer",
             "einheit": "0193b6a2-…", "name": "Planke", "runde": 2, "von": 3,
             "zaehlt": true, "soll_s": 60, "profil": "7KQ4M2XA" } }
```

| Feld | Werte | Bedeutung |
|---|---|---|
| `quelle` | `einheit`, `timer`, `plan`, `gps`, `person`, `uhr` | wer die Marke setzte — `person`: ein Tipp in der Übungsausführung (seit 19.10.2026); `uhr`: ⏯ am Band (hrv-watch, seit 4.11.2026, P113) |
| `art` | `start`, `ende`, `abschnitt`, `pause`, `weiter`, `uebung_start`, `uebung_ende`, `km`, `leistung`, `abschluss`, `erholung`, `marke`, `takt` | was sie bedeutet — `takt`: ein Atemtakt des Taktgebers beginnt (seit 5.11.2026, Spur `atemtakt`, unten) — `marke`: eine bloße Marke ohne Text (⏯ am Band, `uhr/marke`; vorher eine leere Notiz ohne `marke`, nicht von anderen zu unterscheiden) — `leistung`: „geleistet bis hierher“ (die **Tippzeit**, nie der Beginn des Satzes), `abschluss`: der Eintrag ist fertig, `erholung`: Ende einer Belastung, ab hier zählt die HF-Erholung; `talk`: Talk-Test, „Sprechen wird schwer“ — die HF der 30 s davor ist der Marker für Schwelle 1 (beide seit 29.10.2026, `docs/plan_herzfrequenz.md`) |
| `spur` | `timer`, `uebung`, `km`, `atemtakt` | die Abschnittsspur, die sie teilt (Abschnitt 9b) — `atemtakt`: der Atemtakt des Taktgebers (keine Abschnittsgrenze, nur ein Paar Notizen, unten) |
| `einheit` | Text (UUID) | der gemeinsame Ablauf in der App, dessen Zeitleiste die Marke kommt (`docs/plan_einheit.md`) |
| `name` | Text | Abschnittsname ohne Zusatz („Belastung“, „Planke“) |
| `runde`, `von` | Zahl | Runde r von n |
| `zaehlt` | Ja/Nein | der Abschnitt zählt als Übungszeit (im Timer einstellbar) |
| `soll_s` | Zahl | die geplante Dauer des Abschnitts in Sekunden — ein „Weiter“ kürzt ihn, Soll gegen Ist zeigt es; fehlt bei der Stoppuhr (seit 18.10.2026) |
| `profil` | Text | welcher Ablauf lief: der Kurzcode der Profil-ID (8 Zeichen wie bei Übungen), die Stoppuhr `stoppuhr`, der Einmal-Timer `einmal` (seit 19.10.2026) — derselbe Ablauf über Tage, auch nach Umbenennen (seit 18.10.2026) |
| `feld`, `wert` | Text, Zahl | bei `person/leistung`: das Feld der Übung (`reps`, `hold`, …) und der eingetragene Wert (seit 19.10.2026) — die Ausprägung (Gewicht, Seite) steht im Text („Kniebeuge 20 kg: 10“); bei `timer/takt` ist `wert` die **Rate des Takts je Minute** (60 / Rundendauer, mit Tempo) |
| `kopf_s`, `endteil_s` | Zahl (s, mit Vorzeichen) | an der **Start-Notiz** eines Abschnitts (seit 27.10.2026): Kopf und Endteil — der Rechenbereich reicht so weit über die getippten Grenzen hinaus (positiv: davor bzw. danach) oder beginnt dahinter (negativ: innerhalb); `hrv_core.ausschnitte.Abschnitt.rechenbereich`. Fehlt = 0 |
| `kontext`, `haltung` | Text | bei `person/erholung` (seit 29.10.2026, `docs/plan_herzfrequenz.md`): woran die Person sich erholt (`dauer`, `intervall`, `sprint`, `satz`, `test_submaximal`, `test_maximal`) und in welcher Haltung (`steht`, `sitzt`, `liegt`, `geht`). HRR-Werte sind nur innerhalb gleicher Paare vergleichbar (`hrv_core.herzfrequenz.hrr_erholung`); die Person darf beides nachträglich ändern — die Marke wird fortgeschrieben |

- Nur diese Felder, nur Zahl, Text oder Ja/Nein — `hrv_core.ereignisse.marke_bereinigen`
  wirft alles andere weg. **Nie ein Ort** (Abschnitt 0 in `docs/plan_gps.md`): eine
  km-Marke trägt den Kilometer, keine Koordinate.
- Was die Person selbst notiert, hat **keine** Marke. Wer eine automatische Notiz
  bearbeitet (Text, Stelle), behält die Marke; löschen löscht sie mit.
- **Leistungen der Person** (Ben, 19.10.2026, `docs/plan_eintraege_hrv.md` Teil B): Jeder
  Tipp, der eine Menge einträgt, wird eine Notiz mit Marke `person/leistung` (`feld`,
  `wert`, `uebungen`), „Abschließen“ eine mit `person/abschluss`. Der erste Satz eines
  Eintrags beginnt den Abschnitt der Übung auf der Spur `uebung`, das Abschließen beendet
  ihn — außer die Uhr der Übung läuft schon (dann nur Notizen). Diese Notizen unterliegen
  **nicht** der 5-s-Regel (zwei Sätze in drei Sekunden sind zwei Sätze). praxis_gui zeigt
  sie als normale Notizen; Nachträge und Korrekturen bekommen keine Marke.
- Abschnitte unter 5 s bekommen keine Marke (versehentliches „Weiter“).
- **Atemtakt des Taktgebers** (Ben, 5.11.2026, `docs/plan_taktgeber.md` §3, Teil 2 T4): Läuft
  während der Aufnahme ein **Atemtakt** (Arten ein/aus/halten — ein Bewegungstakt setzt nichts),
  bekommt die Messdatei ein **Paar Notizen** mit Marke auf der Spur `atemtakt`: am Beginn
  `quelle=timer, art=takt` mit `name` (Name des Takts, etwa „Atmung 4-6“), `wert` (Rate je
  Minute), `soll_s` (Rundendauer in s, mit Tempo) und `profil` (der Ablauf, wie beim Abschnitt;
  Text „Takt Atmung 4-6: Start“), am Ende `quelle=timer, art=ende, spur=atemtakt` mit `name`
  („Takt Atmung 4-6: Ende“). **Keine Abschnittsgrenze** (die Takt-Läufe stehen vollständig im
  Beiwerk `atem-v1`, Abschnitt 15; eine weitere Spur mit Abschnitten füllte die Abschnittsliste
  mit jedem Tempowechsel) und darum **nicht der 5-s-Regel unterworfen**: Beide Notizen kommen
  sofort — so weiß das Protokollfeld `atmung` (Abschnitt 5) schon im Crash-Backup, dass getaktet
  wurde. Eine **Tempoänderung** ist Ende plus neuer Beginn mit der neuen Rate (wie `timer/takt`
  in der Zeitleiste und `takt.laeufe` im Beiwerk). Beginnt die Aufnahme mitten in einem Takt
  (zweite Aufnahme, Teil 2 nach dem Teilen), steht der Beginn bei 0 s; endet sie mitten im Takt,
  fehlt die Ende-Notiz (die Aufnahme ist zu Ende, das sagt genug). Nie eine Notiz je Phase
  (`MIN_MARKE_S` ist dafür nicht der Grund — es wären hunderte). Ohne Aufnahme nichts.
  `hrv_core.ereignisse.MARKE_FELDER` kennt alle Felder schon; praxis_gui zeigt die Notizen wie
  jede andere.
- **Marken einer Übung** (Ben, 18.10.2026, P54): Läuft eine Übung (Timer der Übung, Stoppuhr,
  Plan-Ablauf), tragen **alle** ihre Marken den Kurzcode in `uebungen`, auch die Abschnitte des
  Timers — die Auswertung muss nichts über die Zeit zuordnen. Der Text nennt dann den Timer
  nicht mehr („Halten (Runde 1/3)“ statt „Timer „Halten 3 × 1 min“: …“); läuft er allein,
  bleibt der Name, er ist dann der einzige Hinweis. „Timer fertig“ fällt in einer Übung als
  Notiz weg — „Planke: Ende“ sagt dasselbe; die Abschnittsgrenze bleibt (still). Anhalten
  und Weiter des Timers heißen in der Übung „Planke: Pause“ / „Planke: weiter“.
- **Einzelne Übung ohne Spur „einheit“** (Ben, 19.10.2026): Läuft eine einzelne Übung mit
  ihrem Timer in einer schon laufenden Aufnahme, fehlen „Start: …“ und „Ende der Einheit“ —
  „Planke: Start“ und „Planke: Ende“ klammern sie schon. Ein Plan-Ablauf behält die Spur.
  Ältere Dateien behalten ihre Notizen („Planke beginnt“ / „Planke fertig“).
- **Eigene Abschnitte der Person** (Ben, 27.10.2026, `docs/plan_abschnitte.md`): Ein
  Abschnitt, den die Person setzt — live mit „Abschnitt: Start“ / „… Ende“ oder nachträglich
  mit „+ Abschnitt“ —, ist ein **Paar Notizen** `person/abschnitt` (Start) und `person/ende`
  mit derselben `spur` = seiner Kennung `seg-…` (zugleich die `id` des Segments im Sidecar,
  Abschnitt 9b). Name, `kopf_s` und `endteil_s` stehen an der Start-Notiz; Text „Name:
  Start“ / „Name: Ende“. Die Abschnitte des Timers bleiben ihre Kette (`art=abschnitt` je
  Grenze); auch ihre Start-Notiz darf `kopf_s`/`endteil_s` tragen.
  `hrv_core.ausschnitte.paare_aus_notizen`, `trainingsapp.core.abschnitte`.
- **praxis_gui** liest das Feld nicht und behält es beim Bearbeiten wie `uebungen`.
- Keine neue Schema-Version: ein zusätzliches, optionales Feld wie `uebungen`; ältere
  Leser übergehen es.

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

Wir ergänzen weitere Profile (Polar-Uhren, Uhren-Broadcast, optische
Armbänder) — sie ordnen sich denselben beiden `intervall_quelle`-Werten unter.
Optische Sensoren sind immer `ppg_ppi`. Unbekannte Profil-IDs behandelt
praxis_gui wie `ble_generic`.

| ID (unsere) | Name | `intervall_quelle` | Ordner | Schwelle |
|---|---|---|---|---|
| `polar_watch` | Polar-Uhr (PMD) | `ppg_ppi` | `VeritySense` | 0.30 |
| `ble_optisch` | Optischer Sensor (Armband): TICKR FIT, Scosche Rhythm, Polar OH1, Coospo HW807 … (seit 14.10.2026) | `ppg_ppi` | `VeritySense` | 0.30 |
| `watch_broadcast` | Uhr (Herzfrequenz-Übertragung) | `ppg_ppi` | `Uhr` ⚠️ | 0.30 |

`ble_generic` heißt in der App seit 14.10.2026 **„Herzfrequenz-Sensor
(Standardprofil)"**: Hierher fällt jedes Gerät mit Herzfrequenz-Dienst, dessen
Namen wir nicht kennen — ob es ein Gurt ist, wissen wir nicht. ID, Ordner und
`ekg_rr` bleiben wie in praxis_gui. Als „Brustgurt" bezeichnet die Oberfläche
ein Gerät nur, wenn Profil oder Name es sicher sagen (`profiles.geraeteart`).
⚠️ `Uhr` gehört nicht zu den Ordnern, die praxis_gui durchsucht (Abschnitt 2) —
Messungen reiner Pulsuhren erscheinen dort nicht.

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

### Unsere Erweiterung: `atmung` (seit 5.11.2026)

Das **Protokollfeld „Atmung“** (`docs/plan_beschleunigung.md` §7.4, P125): zusätzlicher
Schlüssel im Kopf, beim Schreiben der App direkt hinter `datenqualitaet`
(`core.atem_protokoll.einordnen`); schreibt `hrv_core.recording.Recording.to_dict` die Datei
neu (Zusammenfügen, Zuschneiden, Notizen), steht es als unbekanntes Feld am Ende — lesbar
bleibt es an jeder Stelle. Es sagt, **wie** während der Messung
geatmet wurde — nicht wann (das steht im Beiwerk `atem-v1`, Abschnitt 15). `praxis_gui`
liest defensiv, behält das Feld als unbekanntes Feld (`extra`) und schreibt es unverändert
zurück — der Vertrag bleibt unverletzt.

```json
"atmung": {"art": "getaktet", "takt_pro_min": 6.0}
```

| Feld | Typ | Bedeutung |
|---|---|---|
| `art` | str | `spontan` (frei geatmet), `getaktet` (nach dem Taktgeber), `uebung` (die Messung lief während einer Atemübung) |
| `takt_pro_min` | float | **nur** bei `getaktet`: Atemzüge je Minute, die der Taktgeber vorgab |
| `uebung` | str | **nur** bei `uebung`: Kurzcode der Übung |

- **Automatisch**, nie von Hand: die App setzt es aus der Übung der Einheit und dem Taktgeber
  der Uhr (`docs/plan_taktgeber.md`). **Der Takt geht vor** (seit 5.11.2026, Teil 2 T4): Lief
  während der Aufnahme ein Atemtakt — die Messdatei trägt ein Paar Notizen `timer/takt` …
  `timer/ende` auf der Spur `atemtakt` (Abschnitt 4) —, ist die Art `getaktet` mit
  `takt_pro_min` = der Rate des **längsten** Takt-Laufs (nach einer Tempoänderung gibt es
  mehrere; ein beim Ende der Aufnahme offener Lauf reicht bis dorthin); erst sonst gilt die
  Übungsregel (Atemübung → `uebung`, keine Übung → `spontan`, nur andere Übungen → kein
  Feld). Ein Bewegungstakt (ab/auf) setzt keine Marke und kein `getaktet`. Eine Bewertung ist
  es nicht — es beschreibt die Bedingung der Messung.
- **Fehlt = unbekannt.** Altdateien, Dateien aus praxis_gui und Messungen ohne Einheit haben
  den Schlüssel nicht; der Leser setzt keinen Standardwert und rät nicht aus den Daten.
- `hrv_core.deid` behält das Feld als Ganzes (`RAW_REGELN`): es enthält nichts über die
  Person, nur über die Messung.
- **Warum:** Ohne die Angabe sind HF-Power, LF/HF und DFA α1 zwischen Messungen nicht
  vergleichbar — Atmung unter 9/min (0,15 Hz) liegt im LF-Band, dann treiben schon die
  Atemzüge LF/HF (Plan §7.1); getaktet und spontan werden darum getrennt verglichen.
- Reihenfolge wie immer: zuerst dieser Eintrag, dann hrv-core (`docs/formate.md`,
  `deid.REGELN`), dann der Code in der App. **Seit 0.3.46 geschrieben** (B1,
  `core/atem_protokoll.py`): der `Messlauf` bestimmt das Feld im Loop aus den Kurzcodes in
  den Ereignissen (Haken `atmung_protokoll`, belegt von der Oberfläche mit dem Katalog), das
  Backup trägt es im Block `_wiederherstellung`, beim Speichern und Wiederherstellen kommt es
  an seinen Platz hinter `datenqualitaet`. Die Auswertung zeigt es in der Karte „Atmung“.

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

- Inhalt bei praxis_gui: derselbe `raw-v1`-Kopf und dieselben `messungen`/`ppi_pakete` wie
  die Messdatei, kompakt geschrieben (`separators=(",", ":")`), atomar über `.tmp`.
  **Wir seit 28.10.2026 (hrv-core 0.3, lange Aufnahmen): Kopf und Journal** — der Kopf
  `.backup_<start>.json` ohne `messungen` (mit `_journal`), die Schläge und PPI-Pakete
  Zeile für Zeile angehängt in `.backup_<start>.jsonl`; `hrv_core.aufnahme.backup_lesen`
  setzt beides zusammen und liest auch Köpfe mit `messungen` (alte Backups, praxis_gui).
  So kostet das 15-s-Backup nach 36 h dasselbe wie nach einer Minute (vorher 11 MB je
  Backup). Vertrag in hrv-core: `docs/formate.md`.
- praxis_gui legt zusätzlich einen `hrv`-Block mit Live-Werten hinein
  (`"_scope": "live_window"`). **Wir nicht** — ein Backup ist Rohdatenrettung,
  keine Analyse.
- Nach erfolgreichem Speichern der Messdatei wird das Backup gelöscht. Bleibt
  eines liegen, war die Aufnahme nicht ordentlich beendet.
- Der Punkt am Anfang hält es aus jeder Messungsliste heraus.
- **Unser Zusatz** (15.10.2026): ein Top-Level-Block `_wiederherstellung`, nur im
  Backup, nie in der Messdatei:
  ```json
  "_wiederherstellung": {"subject_id": "<Profil-ID>", "grenzen": [[<Notiz>, "<Name>", false], …]}
  ```
  `subject_id` ist das Profil beim Start der Aufnahme, `grenzen` sind die
  Abschnittsgrenzen des Timers (Notiz, Abschnittsname, nur Ende?), die sonst nur
  im Speicher lägen. `hrv_core.aufnahme.backup_lesen` nimmt den Block vor
  `Recording.from_dict` heraus, damit er nicht über `extra` in die Messdatei
  gerät. praxis_gui liest Backups nicht; ein Backup ohne den Block (älter oder
  aus praxis_gui) wird dem aktiven Profil zugeordnet.
  Seit 17.10.2026 kommen die **anderen Spuren** (§9b: km, Übung, Einheit) als
  `"spuren": {"km": [[<Notiz>, "<Name>", false], …], …}` dazu — nur wenn es welche
  gibt; `grenzen` bleibt die Spur des Timers, so lesen auch ältere App-Stände das
  Backup. Eine Grenze kann „still“ sein: ihre Notiz steht dann nur hier, nicht in
  `ereignisse` (das Ende einer Spur).
- **Wiederherstellung** (ab 15.10.2026): Beim App-Start sucht
  `hrv_core.aufnahme.backups_finden` unter `Messungen/*/` nach Backups; der Dialog
  „Unvollständige Messung gefunden" bietet je Datei Wiederherstellen oder Löschen.
  `devices.messlauf.backup_wiederherstellen` schreibt `sensor_<start>.json` neben
  das Backup (gleicher Zeitstempel), trägt die Abschnitte ins Sidecar ein und
  löscht das Backup erst danach. Liegt die Messdatei schon da, bleibt sie, wie
  sie ist. Das Diagnoseprotokoll (`_diagnose.txt`) entsteht dabei nicht.
- Zusätzlich zum 15-s-Takt sichert die App, sobald sie in den Hintergrund geht
  (`page.on_app_lifecycle_state_change` → `Messlauf.backup_jetzt`).
- **Begleit-Journale** am Stamm des Kopfs: `.backup_<start>_ecg.jsonl` (EKG-Rohsignal,
  seit 30.10.2026, `hrv_core.ekg`), `.backup_<start>_mitschnitt.jsonl` (Rohmitschnitt
  des Diagnosemodus, seit 4.11.2026, Abschnitt 14) und `.backup_<start>_atem.jsonl`
  (Atemphasen aus dem Prototyp, seit 5.11.2026, `hrv_core.atem`, Abschnitt 15). Beim
  Speichern und beim Wiederherstellen werden sie zum Beiwerk der Messdatei
  (`sensor_<start>_ecg.json`, `sensor_<start>_mitschnitt.jsonl`, `sensor_<start>_atem.json`);
  „Löschen“ im Dialog löscht sie mit (`hrv_core.aufnahme.backup_entfernen`, seit hrv-core
  0.6.0). Alle drei werden nur angehängt, mit `fsync`; eine halbe letzte Zeile nach einem
  Absturz übergeht der Leser. Das Atem-Journal hängt der `Messlauf` im selben Takt an wie
  das EKG-Journal (`backup_jetzt`); ein beim Absturz offener Lauf (`bis_s = null`) wird beim
  Wiederherstellen geschlossen.

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

### 9b. Crop und Abschnitte (seit 14.10.2026)

Zuschneiden und eigene Abschnitte einer fertigen Messung schreiben wir in die
Felder, die praxis_gui selbst dafür nutzt (`hrv_core/ausschnitte.py`):

```json
"active_crop": { "t_start_s": 65.152, "t_end_s": 358.835 },
"segments": [
  { "id": "seg-bd39a79e", "name": "Pause (Runde 1/3)", "t_start_s": 84.848,
    "t_end_s": 134.848, "color": "#e67e22", "metrics": null,
    "computed_utc": null, "active": true, "visible": true }
]
```

- **Zeitbasis wie praxis_gui:** Sekunden auf der Herzuhr der Rohdatei; Abschnitte
  bei aktivem Crop **relativ zu dessen Anfang**. Die App rechnet auf ihrer
  Kurvenachse und rechnet um (`achsen_umrechnung` — beim Brustgurt gleich, bei
  der Verity Sense über die Zeilen der Rohdatei).
- `metrics: null` — die Werte rechnen beide Programme selbst. Den Abschnitt
  „gesamt", den praxis_gui anlegt, lassen wir stehen.
- **Abschnitte sind eigenständig** (seit 14.10.2026, vorher bildete die App sie
  bei jedem Öffnen aus allen Notizen): Jeder Abschnitt steht in `segments`, auch
  die des Timers — die schreibt die App beim Speichern der Aufnahme
  (`ausschnitte.grenzen_speichern`). Notizen sind nur Rastpunkte für Grenzen;
  „Aus Notizen …" macht ausgewählte Notizen zu Grenzen und speichert die
  Abschnitte. Gleiche Grundnamen („Pause (Runde 2/8)" → „Pause") bekommen
  gleiche Farben.
- **Spuren** (seit 17.10.2026): Laufen mehrere Abläufe zugleich — Timer,
  Übungen eines Plan-Ablaufs, Kilometer —, bildet jeder seine Abschnitte für sich
  (`ausschnitte.spuren_speichern`, ein Schreibvorgang für alle). Eine km-Grenze
  teilt keinen Timer-Abschnitt; Abschnitte verschiedener Spuren **überlappen** sich
  (praxis_gui führt Abschnitte als unabhängige Bereiche). Die Spur selbst steht
  nicht im Sidecar — praxis_gui würde ein eigenes Feld beim Speichern verwerfen —,
  sondern in der `marke` der Notiz, die den Abschnitt begann (Abschnitt 4).
- **Eigene Abschnitte sind Notizpaare** (seit 27.10.2026, Abschnitt 4): Ihr Segment trägt
  als `id` die Kennung der Grenz-Notizen (`spur`); die App leitet das Sidecar aus den
  Notizen ab (beim Speichern der Aufnahme und bei jeder Änderung in der Auswertung). Kopf
  und Endteil stehen zusätzlich als `rand: {"kopf_s", "endteil_s"}` am Segment — nur wenn
  gesetzt; praxis_gui behält das Feld beim eigenen Speichern nicht, die Wahrheit ist die
  Marke der Start-Notiz. `t_start_s`/`t_end_s` bleiben die **getippten** Grenzen. Ein
  Segment ohne Notizpaar, dessen Anfang auf keiner Notiz liegt (früher selbst gesetzt),
  bekommt beim Öffnen der Auswertung einmalig sein Paar.
- Gibt es noch kein Sidecar, entsteht ein knappes (`schema`, `source_file`,
  `source_file_sha1`, die beiden Felder, `updated_utc`).
- Achtung, umgekehrt: praxis_gui schreibt das Sidecar beim Speichern aus seiner
  Sitzung neu und behält nur ihm bekannte Felder — `active_crop` und `segments`
  gehören dazu, unsere Erweiterungen aus 9a (`corrections_ppi`,
  `corrections_meta.regeln`) **nicht**.

**Bestehende Sidecars werden fortgeschrieben, nicht ersetzt:** alle Felder, die
wir nicht kennen (`metric_params`, `derived_metrics`, `frequency_summary` …),
bleiben erhalten. Abgeleitete Werte von
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

Die Felder des **Atembands** aus hrv-core 0.12.0 (`hf_atem`, `lf_atem`, `lf_hf_atem`,
`atem_band_hz`; hrv-core `docs/formate.md`, „Kennzahlen-Schlüssel“) sind **keine**
Cache-Schlüssel: Die App rechnet sie beim Anzeigen mit der Atemrate nach Regel F6
(`docs/plan_beschleunigung.md` §13, B2b) und speichert sie nirgends — `hrv_metrics_cache`
wird bisher nicht befüllt (`docs/offene_fragen.md` H7). `ALGO_VERSION` blieb bei 8, ein Cache
ohne die Felder wäre unvollständig, nicht veraltet (die Apps ergänzen ihn beim Anzeigen).

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

---

## 13. `spur-ohne-ort-v1` — die Rohspur eines Trainings ohne Ort (seit 26.10.2026)

Eine Datei je Training im Export-ZIP (`Bewegung/<Name der Streckendatei>`, z. B.
`Bewegung/strecke_2026-10-18_090507.jsonl`), geschrieben von
`data.strecken.spur_ohne_ort`, Kopf aus `core.bewegung.kopf`. Dasselbe Zeilenformat wie
die Streckendatei unter `Strecken/` (eine Zeile JSON je Ortung, fehlende Werte fehlen):
eine **Dateikopie** ohne die Felder `lat`, `lon`, `richtung_grad`, dafür mit `ds_m`.
Nur praxis-unabhängig: praxis_gui kennt das Format nicht und muss es nicht kennen.

**Kopfzeile** `{"kopf": {…}}`:

| Feld | Bedeutung |
|---|---|
| `schema` | `"spur-ohne-ort-v1"` |
| `app` | `"trainingsapp 0.3.18 (Build …)"` |
| `sportart`, `titel`, `start_utc`, `ende_utc` | wie die Zeile `strecke` |
| `strecke_id`, `einheit_id` | Kennungen; `einheit_id` `null` bei Trainings vor dem 17.10.2026 |
| `hoehe_bezug` | `"msl"` (über dem Meeresspiegel, EGM2008 — seit 26.10.2026) oder `"ellipsoid"` (ältere Dateien ohne Angabe im Kopf, WGS 84) |
| `kennzahlen` | `distanz_m`, `dauer_s`, `bewegt_s`, `hoehe_auf_m`, `hoehe_ab_m` — wie die App sie zeigt, als Komfort markiert; die Zeilen sind die Wahrheit |
| `messungen[]` | je verknüpfter Messung `datei` (Pfad im ZIP), `recording_id`, `versatz_s`, `versatz_quelle`: **Ortungszeit `t` + `versatz_s` = `t_wall_s` dieser Messdatei** (Abschnitt 4). `versatz_quelle` `"einheit"`: aus den Versätzen beider Teile der Einheit; `"uhr"`: `−start_utc` der Messdatei (ganze Sekunden, ±1 s) |
| `felder` | was in den Zeilen stehen kann |
| `entfernt` | `["lat", "lon", "richtung_grad"]` |

**Eine Zeile je Ortung:**

| Feld | roh? | Bedeutung |
|---|---|---|
| `t` | roh | UTC-Sekunden des Empfängers |
| `ds_m` | abgeleitet | Abstand zum vorigen Fix in Metern (`core.strecke.abstand_m`, Haversine, ungefiltert, jede Ortung); fehlt in der ersten Zeile |
| `tempo_ms` | roh | Doppler-Tempo des Empfängers |
| `genauigkeit_m` | roh | horizontaler Fehler — der Leser filtert selbst (die App nimmt 30 m) |
| `hoehe_m`, `hoehe_genauigkeit_m` | roh | Höhe im Bezug des Kopfs |
| `t_empfang` | roh | monotone Uhr der App beim Eintreffen |
| `simuliert` | roh | Ortung aus einer Test-App |

Die **Richtung fehlt mit Absicht**: Abstand plus Richtung je Sekunde wäre Koppelnavigation,
daraus ließe sich die Strecke bis auf Drehung und Verschiebung zurückrechnen. Alle
Ableitungen (Genauigkeitsfilter, Auto-Pause, Steigung, Kilometer, Tempo je Fenster) rechnet
der Leser nach — mit demselben Code wie die App (`core/strecke.py`) oder dem Leser in
hrv-research (`hrv_research.bewegung`). Dieselbe Datei liegt im Forschungsexport einer
Einheit (`einheit-v1`, `docs/plan_einheit.md` §8), dort nennt sie die GPS-Beteiligung.
Tests: `tests/test_ausdauer.py::test_regel_0_keine_koordinate_in_hrv_export_tagebuch_und_sync`,
`tests/test_strecke.py::test_rohspur_ohne_ort_ist_eine_dateikopie_mit_abstand`.

---

## 14. `mitschnitt-v1` — Rohmitschnitt des Diagnosemodus (seit 4.11.2026)

Plan: `docs/plan_diagnosemodus.md`; Format, Schreiber und Leser in hrv-core
(`hrv_core.mitschnitt`, Feldliste in `hrv-core/docs/formate.md`), gemeinsam mit der
Brustgurt-Diagnose in hrv-research (P116: gleiche Grundlage, verschiedene Eingänge).
Nur trainingsapp-intern und für die Auswertung: praxis_gui kennt das Format nicht und muss
es nicht kennen.

- **Datei:** `Messungen/<Geräteordner>/sensor_<start>_mitschnitt.jsonl` neben der
  Messdatei, während der Aufnahme `.backup_<start>_mitschnitt.jsonl` (Abschnitt 6a); ohne
  Messung `Diagnose/<ts>_<gerät>/mitschnitt.jsonl`. JSON Lines, nur angehängt.
- **Zeilen:** `{"art": …, "t": …}` mit `t` = monotone Uhr der App in ns — dieselbe Uhr wie
  `t_capture` der Messwerte; die Wanduhr der Messung (`t_wall_s`) folgt über die Uhrpaare.
  Arten: `kopf`, `n` (Benachrichtigung, Hex), `w` (Kommando), `r` (Lesen), `v` (Verbindung
  und Protokoll), `uhr` (alle 10 s monotone Uhr ↔ UTC), `probe` (Akku, Verzug), `marke`,
  `marke_weg`, `kontext`.
- **Marken** stehen hier, **nicht** in `ereignisse` der Messdatei (Plan §3.4): hunderte je
  Messung würden die Notizliste und praxis_gui fluten. Eine Marke hat `id`, `typ` (`wdh`,
  `atem`, `stoerung`, `marke`), `quelle` (`handy`, `uhr`), `nr` im Satz und `kontext`;
  `marke_weg` nimmt eine zurück, gelöscht wird nie.
- **Kontext** (`was`): die automatischen Notizen (Übung, Timer, eingetragener Satz),
  `diagnose_start`/`diagnose_ende` und `zaehler` (was der Sensor im Satz zählte, `wert`,
  `satz`, `feld`, `phase` = `prototyp`). Seit 4.11.2026 aus dem Zählen mit dem
  Beschleunigungssensor (`docs/plan_beschleunigung.md` §5.3, §6) dazu `zaehlung` (`wert` =
  Sensor plus Korrektur, `satz`, `feld`, `dauer_s`), `korrektur` (`wert` = ±1, `satz`,
  `feld`) und `zaehlen_ende` (`phase` = Grund) — nur Felder, die die Weißliste in
  `hrv_core.deid` schon kennt, nie ein Feld `art`; `t` ist immer der Zeitstempel. Den
  eingetragenen Satz eines gezählten Satzes (`satz`, hier mit der Nummer `satz`) schreibt der
  Vergleich an seinem Ende, vor `uebung_ende` (seit 5.11.2026; die Notiz zum Satz kommt erst
  nach dem Ende der Einheit und schreibt keine zweite) — die k-te `satz`-Zeile nach
  `uebung_start` bleibt Satz k. Darum bekommt **jeder** gezählte Satz eine, ein nicht
  eingetragener (Sensor 0, abgebrochen) ohne `feld`/`wert` — „eingetragen –“; wird er später
  doch eingetragen, bleibt es bei dieser Zeile. Ein Satz von Hand neben dem Zählen kommt nach
  den gezählten Sätzen davor; seine Zeile trägt die Nummer ebenfalls (`satz`, wenn die Übung
  die des letzten `uebung_start` ist), und die Marken tragen dieselbe (`kontext.satz`).
- **Nie im Mitschnitt:** GPS (Regel 0 in `docs/plan_gps.md`), die Seriennummer (0x2A25) und
  die Systemkennung (0x2A23) — die App liest beide nie. Die Bluetooth-Adresse steht nur in
  der Datei auf dem Gerät; hinaus geht der Mitschnitt nur bereinigt (Abschnitt 2, Export).
- **Geräteprobe ohne Messung** (Stufe 6): `Diagnose/<UTC-Start>_<Modell>/mitschnitt.jsonl`
  (Kopf mit `geraet.art = unbekannt` und dem Abbild der Dienste) und `probe.json`
  (`format: geraeteprobe-v1` — `geraet` {`name`, `modell`}, `formular` {`hersteller`, `was`,
  `vergleich`}, `dienste`, `gelesen`, `abonniert`, `fehler`, `zusammenfassung`). Nie
  geschrieben wird auf das Gerät; Seriennummer und Systemkennung liest die App nie. Geteilt als
  ZIP mit bereinigtem Mitschnitt (`devices.erkundung.probe_zip`).
- **Messdatei unverändert:** raw-v1 bekommt kein neues Feld; die Messung ist auch ohne den
  Mitschnitt vollständig. Löschen des Mitschnitts („Diagnose löschen“) lässt die Messung
  stehen; Löschen der Messung nimmt ihr Beiwerk mit.

---

## 15. `atem-v1` — Atemphasen neben der Messdatei (seit 5.11.2026)

Plan: `docs/plan_beschleunigung.md` §7.4 (Ablage) und §8 (Ergebnisse statt Rohdaten,
P123); Format, Schreiber und Leser in hrv-core (`hrv_core.atem`, Feldliste in
`hrv-core/docs/formate.md`). `hrv_core.atem` ist ein **stabiles Modul, kein Prototyp**: das
Dateiformat steht fest; was darin steht, stammt aus dem Prototyp `hrv_core.prototyp.atemzuege`
und sagt das selbst (`art`, `prototyp`, `hrv_core`). Nur trainingsapp-intern und für die
Auswertung: praxis_gui kennt das Format nicht und muss es nicht kennen; weil Leser und
Schreiber in hrv-core liegen, kann es die Datei später ohne eigene Übersetzung lesen.

- **Datei:** `Messungen/<Geräteordner>/sensor_<start>_atem.json` neben der Messdatei
  (`hrv_core.atem.atem_pfad(messdatei)`), während der Aufnahme
  `.backup_<start>_atem.jsonl` (Abschnitt 6a, `atem_journal_pfad(backup)`). Sie entsteht
  nur, wenn „Atmung erfassen“ in einer Einheit an war, während eine Aufnahme lief; ohne
  einen Atem-Lauf gibt es keine Datei (`AtemSammler.leer`). Geschrieben wird atomar
  (`.tmp`, `os.replace`), kompakt (`ensure_ascii=False`, ohne Einrückung — die Phasenliste wird lang).
- **Felder** (Reihenfolge wie hier):

  | Feld | Typ | Bedeutung |
  |---|---|---|
  | `schema` | str | `"atem-v1"` |
  | `art` | str | `"prototyp"` — das Verfahren hat keinen `ALGO_VERSION` und keinen Golden Master (`hrv_core.prototyp`) |
  | `prototyp` | str | Modul, das die Phasen fand: `"hrv_core.prototyp.atemzuege"` |
  | `hrv_core` | str | Version der Bibliothek beim Schreiben (`hrv_core.__version__`) |
  | `quelle` | str | `"sensor"` (Beschleunigung des Gurts); `"takt"`, wenn **nur** der Taktgeber schrieb (Soll-Phasen ohne Sensor, Feld `takt` — `erfasst`, `phasen` und `fenster` sind dann leer, `prototyp` leer); mit Sensor **und** Takt bleibt es `"sensor"`, der Takt steht im Feld `takt` |
  | `geraet` | str | Profil-ID (`polar_h10`, `verity_sense`, Abschnitt 5) — nie Name, Adresse oder Seriennummer |
  | `rate_hz` | int \| float \| null | Abtastrate der Beschleunigung, aus der gerechnet wurde (nur zur Einordnung; Proben enthält die Datei nicht): ganzzahlig als int, sonst float, `null` ohne Rate |
  | `erfasst` | list | Läufe von „Atmung erfassen“: `[[von_s, bis_s], …]`, ein Eintrag je Lauf, beim Schreiben alle geschlossen. Ein Lauf beginnt mit der **ersten Probe** des Sensors (nicht mit dem Tipp — die Anlaufzeit ist nicht erfasst; ohne eine Probe kein Lauf) bzw. bei 0, wenn die Aufnahme während der laufenden Erfassung beginnt (auch eine zweite Aufnahme, auch Teil 2 nach dem Teilen); er endet mit dem Ende der Erfassung, am Stopp der Aufnahme oder an der Naht beim Teilen |
  | `phasen` | list | `[[t_s, "ein"], [t_s, "aus"], …]` — Beginn von Ein- bzw. Ausatmen, zeitlich sortiert; nie vor 0 (eine Phase, deren Ansatz vor dem Start der Aufnahme lag, gehört nicht in diese Datei) |
  | `takt` | dict | **optional** (P141, Taktgeber Teil 2 T4, 5.11.2026; hrv-core 0.13.0 `hrv_core.atem.Takt`): die **Soll-Phasen des Taktgebers** — `{"name", "rate_pro_min", "phasen", "laeufe"}`: `phasen` `[[t_s, "ein" \| "aus"], …]` wie oben (Wanduhr, 3 Nachkommastellen, zeitlich sortiert, **alle** Takt-Läufe in einer Liste; „halten“ verlängert die laufende Phase, `core.takt.soll_phasen`), `laeufe` `[[von_s, bis_s, name, rate_pro_min], …]` je Takt-Lauf (ein neuer je Start eines Abschnitts mit Atemtakt und je Tempoänderung; ohne Lauf ist eine Lücke „kein Takt“, wie `erfasst`), `name` und `rate_pro_min` die des **letzten** Laufs. Nur Atemtakte (`Takt.ist_atmung`), nie Bewegungstakte. Steht nur in der Datei, wenn es Soll-Phasen gibt; alte Dateien ohne das Feld lesen sich unverändert (`Atem.takt = None`), ältere Leser übergehen es. Gespeist vom `Messlauf` (`atem_takt_beginn`/`atem_takt_phase`/`atem_takt_ende`, Quelluhr → Wanduhr wie `atem_phase`; ohne Aufnahme nichts; beginnt die Aufnahme mitten im Takt, beginnt der Lauf bei 0) aus dem `TaktVerfolger` des Timer-Teils (`devices/takt_lauf.py`) — die Lage je Tick der Einheit, ohne Oberfläche |
  | `fenster` | list | `[[t_ende_s, rate_pro_min, gueltig, grund], …]` — laufende Rate je Prüffenster (alle 5 s, 30 s lang, Zeit = Fensterende); `rate_pro_min` `null`, wenn ungültig; `gueltig` bool; `grund` leer oder ein snake_case-Code des Prototyps — der **erste** Grund seiner Prüfreihenfolge (`hrv_core.prototyp.atemzuege`): `bewegung` → `amplitude_klein` → `kein_gipfel` / `gipfel_undeutlich` → `zu_wenig_zyklen` → `ungleichmaessig` / `zyklen_passen_nicht` (`devices/zaehlen.py` schreibt `gruende[0]`) |

  Alle Zeiten in **Sekunden auf der Wanduhr der Messung** (`t_wall_s` wie die Schläge,
  Abschnitt 4), 3 Nachkommastellen — so legt die Auswertung Phasen und RR-Abstände ohne
  Umrechnung übereinander. Der Leser `atem_laden` ist tolerant: fehlende Listen gelten als
  leer, Unbekanntes bleibt liegen.
- **Journal** `.backup_<start>_atem.jsonl` (JSON Lines, nur angehängt, jede Zeile für sich
  abgeschlossen, `fsync` wie das EKG-Journal): `["k", {Kopf ohne die Listen}]` einmal am
  Anfang, `["e", von_s]` Lauf auf, `["x", bis_s]` Lauf zu, `["p", t_s, "ein" | "aus"]`
  Phase, `["f", t_ende_s, rate_pro_min, gueltig, grund]` Fenster; Taktgeber (seit hrv-core
  0.13.0): `["t", t_s, name, rate_pro_min]` Takt-Lauf auf, `["q", t_s, "ein" | "aus"]`
  Soll-Phase, `["u", t_s]` Takt-Lauf zu. `journal_anhaengen`
  schreibt nur, was seit dem letzten Mal dazukam (wie `hrv_core.ekg`); `aus_journal` setzt
  die Datei wieder zusammen und übergeht eine halbe letzte Zeile; ein offener Lauf
  (`bis_s = null`) wird beim Schreiben geschlossen. Beim Speichern der Messdatei wird das
  Journal zur Datei und gelöscht; beim Wiederherstellen eines Backups ebenso.
- **Regeln:**
  - **Ergebnisse statt Rohdaten** (P123): keine Rohproben der Beschleunigung, nichts aus dem
    Puffer — nur Phasen, Fenster und Läufe. Rohdaten gibt es ausschließlich im Mitschnitt des
    Diagnosemodus (Abschnitt 14).
  - **Prototyp gekennzeichnet:** `art`, `prototyp` und `hrv_core` sagen, womit gerechnet
    wurde. Wird der Prototyp besser, behalten alte Messungen ihre alten Phasen (Plan §7.4,
    bewusst so); neu rechnen lässt sich nur, was im Diagnosemodus mit Rohdaten aufgenommen
    wurde. Nichts aus dieser Datei wird je als Kennzahl in den Cache (`hrv_metrics_cache`)
    geschrieben.
  - **Soll gegen Ist** (T4): Die Auswertung legt `takt.phasen` als feine Linien über den
    Ist-Schatten (nur innerhalb der Takt-Läufe), nennt je Atemzug den Versatz des Ist-„ein“ zum
    nächsten Soll-„ein“ (Median, `core.atem_auswertung.soll_ist_versatz`) und rechnet die
    Atem-HRV einmal gegen Ist und einmal gegen Soll (Entscheidung 25 Frage 7: beides zeigen).
    Für die Regel F6 ist die Takt-Rate die **dritte Quelle**, wenn Sensor und RR-Atmung fehlen.
    Die Takt-Rate der ganzen Messung ist dabei die des **längsten** Laufs aus `takt.laeufe`
    (wie `takt_pro_min` im Protokollfeld, §5; `core.atem_auswertung.takt_rate`), je Bereich die
    des Laufs, der ihn am längsten abdeckt — `name`/`rate_pro_min` im Feld bleiben die des
    letzten Laufs (Prüfrunde 1, 0.3.52). Nichts davon wird gespeichert.
  - **`erfasst` unterscheidet gemessen von Lücke:** Ohne einen Lauf, der eine Zeit abdeckt,
    heißt „keine Phase“ *nicht gemessen*, nicht *kein Atemzug*. Die Auswertung zeigt
    außerhalb der Läufe nichts, auch keine Rate, und paart Phasen nur innerhalb eines Laufs
    (`core.atem_auswertung.je_lauf`): kein Atemzug und kein Schatten über die Pause zwischen
    zwei Läufen.
  - **Keine Korrekturen:** Die Datei wird nach dem Schreiben nicht verändert, keine ±1, kein
    Verschieben einer Phase. Was die Person am Zählen korrigiert, steht in der Zeitleiste
    der Einheit (`korrektur`, `docs/plan_beschleunigung.md` §5.3), nie hier.
  - **Nie Ort, nie Magnetometer:** keine Koordinaten (Regel 0, `docs/plan_gps.md`), nichts
    zur Richtung; `geraet` ist nur die Profil-ID, die Bluetooth-Adresse steht nirgends.
- **deid und Export:** `hrv_core.deid` kennt die Endung als Beiwerk (`BEIWERK_SUFFIXE`),
  erkennt das Format am `schema` und am Suffix (`format_erkennen`) und behält alle Felder
  (`REGELN["atem-v1"]`, Listen als Ganzes) — es gibt nichts zu bereinigen; die deid-Kopie ist
  inhaltlich gleich, aber eingerückt geschrieben (wie beim EKG), die Export-Kopie byteidentisch
  (Dateikopie). Export-ZIP,
  Forschungsexport einer Einheit und Teilen nehmen die Datei als **Dateikopie** am Stamm mit
  (Abschnitt 2, Export; `core.hrv_export.zugehoerige_dateien`), wie das EKG-Beiwerk.
- **Messdatei unverändert:** `raw-v1` bekommt für die Phasen kein neues Feld; die Messung ist
  auch ohne das Beiwerk vollständig. Das Protokollfeld `atmung` (Abschnitt 5) ist davon
  unabhängig: es sagt, *wie* geatmet wurde, die Datei hier, *wann*. Die Datenbank hält keinen
  Verweis auf das Beiwerk (`hrv_recording` ohne Beiwerk-Spalte) — es hängt am Stamm der
  Messdatei; Löschen der Messung nimmt es mit.
