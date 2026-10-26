# Planung: GPS-Daten im Export — Kopplung mit den HRV-Messungen (26.10.2026)

Bens Frage: „Unter Messungen → HRV lassen sich alle HRV-Daten exportieren. Wie ist das
mit den GPS-Daten? Gibt es auch dafür Exports? Bzw. lassen sich die HRV-Exports mit den
GPS-Daten koppeln, damit man später zusammen untersuchen kann, wie sich die HRV in Bezug
auf die Geschwindigkeit usw. geändert hat? Erstmal planen. Evtl. beim HRV-Export Checkbox,
ob GPS mit soll?“

Stand: **Plan, nichts gebaut.** Offene Entscheidungen in Abschnitt 6, Katalog P80.

---

## 1. Was es heute gibt (am Quelltext geprüft)

| Export | Wo | Inhalt | Ort dabei? |
|---|---|---|---|
| **Alle Messungen** | Messung → Aufzeichnungen → HRV → „Alle exportieren“ (`views/messung.py`, `_hrv_liste`) | ZIP mit jeder Messdatei samt Beiwerk (`core.hrv_export.export_zip`), Pfade `Messungen/<Gerät>/…`, ohne Bluetooth-Adresse | nein — keine Strecke, keine Bewegungsdaten |
| **Eine Messung** | Aufzeichnung → Menü ⋮ (`views/messung_detail.py`) | dasselbe für eine Messung | nein |
| **GPX je Training** | Auswertung eines Trainings → „GPX exportieren“ (`views/ausdauer.py`, `data.strecken.gpx`) | Strecke mit Höhe, Zeit und Herzfrequenz je Ortung (Garmin-Erweiterung), Sportart | **ja** — die einzige erlaubte Stelle (Regel 0) |
| **Forschungsexport je Einheit** | Auswertung eines Trainings oder einer Messung mit Einheit → „Für die Auswertung exportieren (ohne Ort)“ (`core/forschung.py`, `einheit-v1`) | Messdateien der Einheit, Zeitleiste (Timer, Kilometer, Übungen), **Tempo alle 5 s** | nein — Tempo ohne Koordinate, Richtung, Höhe |

**Die Kopplung HRV ↔ Geschwindigkeit gibt es also schon** — aber nur je Einheit, von Hand,
und nur für Trainings seit dem 17.10.2026 (ältere Trainings hängen nur über
`strecke.hrv_recording_id` an der Messung, ohne Einheit und Versatz). Was fehlt:

1. Der Sammelexport „Alle exportieren“ kennt die Trainings nicht. Wer alle Messungen eines
   Jahres untersuchen will, müsste jede Einheit einzeln exportieren.
2. Es gibt keinen Sammelexport der Strecken — GPX nur einzeln aus der Auswertung.
3. Die GPX-Datei enthält keine RR-Intervalle, und nichts im Messungs-ZIP sagt, welche
   Strecke zu welcher Messung gehört. Die Verknüpfung steht nur in der Datenbank
   (`strecke.hrv_recording_id`, `strecke.einheit_id`).

**Warum die Kopplung über die Zeit funktioniert:** Jede Ortung trägt die UTC-Zeit des
Empfängers (`Punkt.t`), jeder Herzschlag die Wanduhr seit `start_utc` der Messdatei
(`t_wall_s`, `docs/kompatibilitaet.md` §4). Damit liegen beide ohne weitere Angabe auf
einer Achse — auf die Sekunde, denn `start_utc` hat ganze Sekunden. Kennt die Einheit die
Versätze beider Teile (`docs/plan_einheit.md` §3), ist es genauer; beides soll in den Export.

---

## 2. Regel 0 und die Checkbox

Die Regel (`docs/plan_gps.md` §0, Ben 14.10.2026): Export-ZIP, Sync, Teilen, Diagnose —
**niemals GPS-Daten**; ortsfreie Werte (Distanz, Dauer, Tempo, Höhenmeter je km) dürfen
mit; die eigene Strecke geht nur als **ausdrückliche Handlung** heraus.

Daraus folgen zwei Stufen, die man getrennt entscheiden kann:

| Stufe | Was mitgeht | Verhältnis zu Regel 0 |
|---|---|---|
| **A — Bewegung ohne Ort** | je Training eine Datei `bewegung-v1` (Abschnitt 3): Tempo und zurückgelegte Strecke alle 5 s, Kennzahlen des Trainings, Verweis auf die Messdatei(en) und der Zeitversatz | **innerhalb** der Regel — das ist genau die Liste der erlaubten ortsfreien Werte, dieselbe Rechnung wie im Forschungsexport (`core.forschung.tempo_reihe`) |
| **B — Strecke mit Ort** | dazu je Training die GPX-Datei (wie „GPX exportieren“) | **Lockerung** der Regel: „nie im Messungs-Export“ wird zu „nur mit Häkchen, je Export neu gesetzt, Vorgabe aus“. Das Häkchen ist eine ausdrückliche Handlung — aber die Regel muss an allen Stellen umformuliert werden (§0, `CLAUDE.md`, `docs/recht/40_toms.md`, der Test `test_regel_0_…`) |

Vorschlag: **A ohne Häkchen immer**, sobald eine exportierte Messung ein Training hat (die
Datei ist klein und ortsfrei; praxis_gui ignoriert sie, weil sie nicht unter `Messungen/`
liegt). **B als Häkchen**, Vorgabe aus, nicht gemerkt, mit einer Zeile darunter: „Mit
Koordinaten. Die Strecke verrät, wo du läufst — nur weitergeben, wenn du das willst.“

Für Bens Auswertung (HRV gegen Geschwindigkeit) reicht Stufe A. Stufe B braucht man erst,
wenn man Steigung, Untergrund oder Wiederholungen derselben Runde untersuchen will.

**Steigung** (Höhendifferenz je Fenster) wäre für HRV gegen Tempo wertvoll — bergauf bei
gleichem Tempo ist eine andere Belastung. Sie ist aber eine Höhenreihe mit anderem
Vorzeichen, und die Regel sagt bisher „keine Höhenreihe“ (`docs/plan_einheit.md` §8): Ein
Höhenprofil lässt sich gegen Geländemodelle abgleichen. Vorschlag: in Stufe A nur
`hoehe_auf_m`/`hoehe_ab_m` je Training (schon erlaubt); die Steigung je Fenster erst mit
Stufe B — dann ist der Ort ohnehin dabei. Frage F3.

---

## 3. Format `bewegung-v1` (Stufe A)

Eine JSON-Datei je Training, im ZIP unter `Bewegung/<name der Streckendatei>.json`
(z. B. `Bewegung/strecke_2026-10-18_090507.json`) — ein eigener Ordner neben `Messungen/`,
damit weder praxis_gui noch `ist_messdatei()` sie je anfassen. Die Messdateien selbst
bleiben byteidentisch (Kompatibilitätsvertrag).

| Feld | Bedeutung |
|---|---|
| `format` | `"bewegung-v1"` |
| `app` | wie `einheit-v1` (`"trainingsapp 0.3.18 (Build …)"`) |
| `training` | `id`, `sportart`, `titel`, `start_utc`, `ende_utc`, `distanz_m`, `dauer_s`, `bewegt_s`, `hoehe_auf_m`, `hoehe_ab_m` — die Zeile aus `strecke` |
| `einheit_id` | `null` bei älteren Trainings |
| `messungen[]` | je verknüpfter Messung `datei` (Pfad im ZIP, `Messungen/<Gerät>/sensor_….json`), `recording_id`, `versatz_s` — Ortungszeit (UTC) + `versatz_s` = `t_wall_s` dieser Messdatei; aus der Einheit, wenn sie beide Versätze kennt, sonst `-start_utc` der Messdatei (Genauigkeit ±1 s) mit `quelle: "uhr"` statt `"einheit"` |
| `schritt_s` | 5 (wie `TEMPO_SCHRITT_S`) |
| `reihe` | `[[t_utc, tempo_ms, distanz_m], …]` je Fenster: Mittel des Doppler-Tempos (ohne Doppler Weg je Zeit), kumulierte Distanz am Fensterende; `tempo_ms` `null` ohne Ortung (Tunnel); Ortungen über 30 m Genauigkeit zählen nicht — dieselben Regeln wie `tempo_reihe` |
| `ereignisse[]` | die Kilometer- und Pausenmarken (`t_utc`, `art`, `text`) — ortsfrei, wie sie schon als Notizen in der Messdatei stehen; hier einmal gesammelt |

Nicht enthalten: Koordinaten, Richtung, Höhe je Ortung, Genauigkeit je Ortung, der
Dateiname der Streckendatei (er steht in `training.id`-Form nur als Zeitstempel).
`core.einheit.daten_pruefen` läuft über alles, was aus Ereignissen kommt.

**Für die Auswertung in hrv-research:** Ein Herzschlag auf die Tempoachse: `t_utc` =
`start_utc` + `t_wall_s` − 0 bzw. mit dem Versatz aus `messungen[]`. Eine Lesefunktion
(`hrv_research.bewegung`: Messdatei + `bewegung-v1` → DataFrame je 5 s mit RMSSD, HF,
DFA α1, Tempo) gehört in den Plan, sonst ist das Format nur eine Datei.

**Stufe B** legt daneben `Strecken/<name>.gpx` — Pfad relativ zum Datenverzeichnis wie bei
den Messungen, so dass ein ausgepacktes ZIP die Ordnerstruktur des Geräts hat. Der Inhalt
ist die bestehende `data.strecken.gpx`-Ausgabe (mit Herzfrequenz). Die rohe `.jsonl` (mit
Genauigkeit, Richtung, Empfangszeit) geht nicht mit — sie ist das Arbeitsformat der App,
GPX das Austauschformat (Frage F5).

---

## 4. Oberfläche

**Ein Dialog vor dem Export**, wie `components/forschung.forschung_fragen`: Er sagt, was
ins ZIP kommt, und bietet die Häkchen. Derselbe Dialog an beiden Stellen (alle Messungen,
eine Messung); erscheint nur, wenn mindestens eine der Messungen ein Training hat — sonst
geht es wie heute direkt zum Teilen-Menü.

```
Messungen exportieren
───────────────────────────────
12 Aufzeichnungen, davon 4 mit Training.

Ins ZIP kommen die Messdateien mit Korrekturen
und Notizen, ohne Bluetooth-Adresse. Zu jedem
Training Tempo und Distanz alle 5 Sekunden —
ohne Ort.

☐ GPS-Strecken mit Koordinaten (GPX)
  Die Strecke verrät, wo du läufst. Nur
  weitergeben, wenn du das willst.

              Abbrechen   Exportieren
```

Das Häkchen ist nach jedem Export wieder aus (nicht in `app_setting`). Ein Export mit
Häkchen schreibt eine Zeile ins Diagnoseprotokoll? — nein: Das Protokoll gehört zur
Messung und reist mit; eine Zeile „Strecke exportiert am …“ im Export selbst wäre
Selbstauskunft ohne Nutzen. Nichts loggen.

**Aufzeichnungen → Laufen**: optional „Alle exportieren“ für die Trainings (nur GPX +
`bewegung-v1`, ohne Messdateien) — Frage F4. Nicht nötig für Bens Zweck; die Messungen
sind der Anker.

---

## 5. Umsetzung

| Schritt | Wo | Bemerkung |
|---|---|---|
| `core/bewegung.py`: `dokument(strecke, punkte, messungen, …)` → dict; `reihe` aus `forschung.tempo_reihe` erweitert um die Distanz (kumuliert aus `core.strecke.abstand_m` mit demselben Genauigkeitsfilter) | core, flet-frei, Doctests | Versatzlogik wie `ui/training.hrv_bezug` — die dort in `ui/` liegende Rechnung wandert mit nach `core` (G15 ähnlich) |
| `core/hrv_export.export_zip(dateien, basis, *, zusatz: Mapping[str, bytes])` | core | erzeugte Dateien (JSON, GPX) unter frei gewähltem ZIP-Pfad |
| `ui/training.py`: `bewegung_dateien(state, aufnahmen, *, mit_ort)` → `{zip_pfad: bytes}` — findet je Messung die Trainings (`StreckeRepo.zur_hrv`, plus Einheit), liest `.jsonl`, baut `bewegung-v1`, bei `mit_ort` zusätzlich GPX | ui (flet-frei, wie heute `forschung_export`) | Lesen der Streckendateien in `asyncio.to_thread` |
| `ui/components/export_wahl.py`: der Dialog aus Abschnitt 4 | ui | nutzt `dialoge.Nachher`/`schliessen`, `weitergeben` |
| `views/messung.py` `alle_exportieren`, `views/messung_detail.py` Export | ui | rufen den Dialog, wenn Trainings dabei sind |
| Tests: `test_regel_0_…` bleibt (ohne Häkchen keine Koordinate, auch nicht in `Bewegung/`); neu: mit Häkchen Koordinaten **nur** unter `Strecken/*.gpx`; `bewegung-v1` ohne `lat`/`lon`/`hoehe`; Versatz aus Einheit vs. Uhr; Training ohne Messung → keine Datei | tests | |
| Doku: `docs/kompatibilitaet.md` §2 „Export“ (neue Ordner `Bewegung/`, `Strecken/`, Messdateien unverändert) + neues §13 `bewegung-v1`; `docs/plan_gps.md` §0 und §5b; `CLAUDE.md` (Regel GPS); `docs/recht/40_toms.md` (Standortdaten: „oder mit Häkchen im Messungs-Export“); `docs/offene_fragen.md` §5 Inventar, Entschieden | docs | Formatänderung braucht zuerst den Eintrag in `kompatibilitaet.md` |
| hrv-research: `hrv_research/bewegung.py` (Leser + Verschnitt mit `hrv_core`-Kennzahlen je 5-s-Fenster), Notebook-Vorlage | privates Repo | Daten nur Bens eigene (`daten/selbst/`) |

*Aufwand (geschätzt): App ein Tag, hrv-research ein halber. Keine Migration, keine
Änderung an hrv-core.*

---

## 6. Offene Fragen an Ben (Katalog P80)

| # | Frage | Vorschlag |
|---|---|---|
| F1 | Regel 0 für den Messungs-Export lockern: Strecke mit Koordinaten per Häkchen (Vorgabe aus, je Export neu)? | Ja — es ist eine ausdrückliche Handlung wie „GPX exportieren“; Text der Regel an vier Stellen anpassen. |
| F2 | Stufe A (Tempo und Distanz ohne Ort) **immer** mit, ohne Häkchen? | Ja — ortsfrei, klein, und ohne sie fehlt dem ZIP die Kopplung. |
| F3 | Steigung je Fenster in Stufe A? | Nein, erst mit Stufe B (Höhenprofil ≈ Ort). In A nur Höhenmeter je Training. |
| F4 | „Alle exportieren“ auch unter Aufzeichnungen → Laufen (GPX + Bewegung aller Trainings)? | Später, wenn gebraucht; die Messungen sind der Anker. |
| F5 | Mit Ort: nur GPX, oder auch die rohe `.jsonl` (Genauigkeit, Richtung, Empfangszeit)? | Nur GPX; Doppler-Tempo steht ohnehin in `bewegung-v1`. |
| F6 | Soll der Forschungsexport je Einheit (`einheit-v1`) bleiben oder in den neuen Dialog aufgehen? | Bleibt — er trägt die Zeitleiste der Einheit (Timer, Übungen), die `bewegung-v1` nicht hat. Später zusammenlegen, wenn beide genutzt werden. |
