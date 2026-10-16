# HRV-Inventar trainingsapp (Phase 1, Stand 2026-10-16)

Bestandsaufnahme nach der Arbeitsanweisung „HRV-Code nach hrv-core auslagern“. Nur Quellcode,
Doku und Tests gelesen; Messdateien nur unter `tests/golden/rr/`. Kein Code geändert.
Branch `main`, letzter Commit `372e8bf`; **19 Dateien uncommittet**, darunter HRV-relevant:
`hrv_core/aufnahme.py` (`backups_finden`, `backup_lesen`, Block `_wiederherstellung`),
`devices/messlauf.py` (`backup_wiederherstellen`, `backup_jetzt`), `docs/kompatibilitaet.md` §6a,
`docs/offene_fragen.md` (H16), `tests/test_hrv_aufnahme.py`, `tests/test_messlauf.py`.
Vor dem Branch `refactor/hrv-core` committen oder beiseitelegen.

Pfade relativ zu `src/trainingsapp/`.

**Leitsatz (Ben, 2026-10-16):** `hrv_core/` wird der Kern der gemeinsamen Bibliothek; praxis_gui
übernimmt dieselben Algorithmen. Die trainingsapp bedient standardmäßig vollautomatisch
(`Korrekturregeln`-Vorgaben), ein Expertenmodus (Schwellen sichtbar und einstellbar) wird
zugeschaltet. Zielgruppe: Therapeuten, Sportler, Leistungssportler, Laien.

## 1. Fundstellen und Einordnung

Kein Modul unter `hrv_core/` importiert `flet`, `scipy` oder etwas aus `ui`/`data`/`devices`;
nur numpy, stdlib und relative Importe. Rein stdlib: `constants`, `regeln`, `recording`,
`aufnahme`, `ereignisse`, `export`, `ppi`, `zeitachse`.

| Datei (Zeilen) | Inhalt | Einordnung |
|---|---|---|
| `hrv_core/constants.py` (207) | alle Konstanten, `ALGO_VERSION=7`, `malik_threshold()` (205) | Bibliothek |
| `hrv_core/artifacts.py` (86) | `gleitendes_mittel` (Rand `edge`), `clean_rr` (Malik zwei Durchläufe, lineare Interpolation) | Bibliothek |
| `hrv_core/time_domain.py` (71) | `compute_time_domain` (mean_rr, mean_bpm, SDNN, RMSSD, pNNx; Nähte übersprungen) | Bibliothek |
| `hrv_core/segments.py` (247) | `Segment`, `gueltig_maske`, `filter_rr`, `segment_diffs`, `luecken_finden`, `segmentieren`, `abdeckung` | Bibliothek |
| `hrv_core/frequency.py` (972) | Lomb/Welch/Periodogramm in numpy, Teilspektren, Bandpolitik, langer Weg, `fensterspektrum`, `vlf_fenster`, `ohne_nullen` | Bibliothek |
| `hrv_core/nonlinear.py` (207) | `compute_poincare`, `poincare_punkte`, `compute_dfa_alpha1`, `compute_sampen` | Bibliothek |
| `hrv_core/atmung.py` (510) | `atemfrequenz`, `Atmung`; RUHE/ATEMUEBUNG | Bibliothek — byteidentisch mit praxis_gui |
| `hrv_core/ppi.py` (360) | `ppi_zeilen`, `ppi_naehte`, `ppi_folge`, `schlagzeiten`, `messluecken`, `ohne_verwerfung`, `ppi_verworfen` | Bibliothek |
| `hrv_core/regeln.py` (166) | `Korrekturregeln` (Dataclass, defensives JSON, Grenzen) | Bibliothek — Träger des Automatik-/Expertenmodus |
| `hrv_core/korrektur.py` (986) | `automatisch`, `vorschlaege`, `analysebasis`, `vorauswahl`, `anwenden`, `zuschneiden`, `korr_zeiten`, `naehte`, `rohfolge`; Sidecar `analyse_speichern`/`analyse_laden`/`analyse_regeln` | Bibliothek + Format |
| `hrv_core/live.py` (385) | `LiveFenster` (Puffer 30 min, Artefaktmarkierung, Live-Kennzahlen, `_schwankung`) | Bibliothek (ohne UI) |
| `hrv_core/trends.py` (630) | `verlauf`, `aktuell`, `atmung_aktuell`, `treppe`, `reihe`; Katalog `KENNZAHLEN` (Titel, Achsen, Fenster, Erklärtexte) | gemischt: Rechnung → Bibliothek, Katalog UI-nah |
| `hrv_core/training.py` (197) | Werte je km, `dfa_verlauf`, `zeit_je_bereich`, `hf_je_zeit` | gemischt (numpy, aber App-Feature) |
| `hrv_core/zeitachse.py` (105) | `Kontinuitaetsuhr` (Anker Minimum über 60 Pakete, neu ab 3 s) | Bibliothek |
| `hrv_core/recording.py` (376) | `Beat`, `Recording`, `ist_messdatei`, `laden`, `speichern`, `json_atomar_schreiben`, `messordner` | Format |
| `hrv_core/aufnahme.py` (296) | `Aufnahme` (Schreibregeln je Schlag/PPI-Paket, Backup); `_wiederherstellung` (uncommittet) | Format; Wiederherstellung App |
| `hrv_core/ereignisse.py` (373) | Notiz-Anker (`anker_aus_*`, `achsen_position`, `Zeitbezug`), `metadaten_schreiben` | Format |
| `hrv_core/ausschnitte.py` (412) | `abschnitt_werte`, `abschnitt_spektrum`, Sidecar `active_crop`/`segments`, `achsen_umrechnung`, `FARBEN`, `einrasten` | gemischt |
| `hrv_core/export.py` (101) | ZIP-Export, Diagnoseprotokoll | App |
| `core/hrv_ansicht.py`, `core/hrv_einstellungen.py` | Ansicht der Verlaufskurven; Einstellungen (Kacheln, Fenster, Atemübung, `nichtlinear_optisch`) | App |
| `devices/messlauf.py` (434) | Quelle → `LiveFenster` + `Aufnahme`, Backup 15 s | App (BLE-Orchestrierung) |
| `devices/pmd.py` (439), `devices/base.py` | PMD/PPI-Parser „byteweise wie praxis_gui“; `rr_auf_zeitachse`, 0x2A37 | Protokoll; Kandidat zum Teilen |
| `data/migrations/001_init.sql`, `data/repositories.py:1594` | `hrv_recording` (nur Verweis/Metadaten), `hrv_metrics_cache` (**ohne Code**) | App (DB) |
| `ui/views/messung_detail.py` (2147) | Rechenlogik in der UI: `_Zustand` (2062), Atem-Median über ≤ 2000 Minutenfenster, SampEn-Deckel 3000 (393), DFA ganze Reihe (388) | gemischt — gehört in die Bibliothek (Befund H11) |

Importe von `hrv_core`: `ui/` (18 Dateien, 44 Zeilen), `devices/` (relativ, 13), Tests (25
Dateien, 98 Zeilen), Tutorial (2). `data/` und `core/` importieren es nicht. Ein Paket `hrv_core`
ohne Präfix wird nirgends importiert — keine technische Kollision mit der neuen Bibliothek.

## 2. Datenformate

Kein eigenes Schema: die App schreibt `raw-v1` und eine Teilmenge von `analysis-v1` wie praxis_gui
(Vertrag `docs/kompatibilitaet.md`). Eigene Erweiterungen: `datenqualitaet`
(`rr_ekg`/`ppi_optisch`/`bpm_only`), `ereignisse[].uebungen`, `corrections_meta.regeln`,
`corrections_ppi[]`, Backup `_wiederherstellung` (uncommittet), `sensor_<ts>_diagnose.txt`.

| Datei | Schema | Code |
|---|---|---|
| `Messungen/<Geräteordner>/sensor_<UTC-Start>.json` | `raw-v1` | `recording.py:161-268`, `aufnahme.py` |
| `sensor_<ts>_analyzed.json` | `analysis-v1` (Teilmenge) | `korrektur.py:807-926`, `ausschnitte.py:256-343` |
| `.backup_<UTC-Start>.json` | raw-v1 kompakt + `_wiederherstellung` | `aufnahme.py:215-293` |
| DB `hrv_recording` | Verweis, Metadaten | `001_init.sql:218`, `repositories.py:1594` |

Abweichungen zu praxis_gui: Dateiname UTC-Start (dort lokale Stoppzeit); atomar mit fsync;
`t_wall_s`/`tw_src` fehlen, wenn `None`; fehlendes `tw_src` wird `"m"`; `__cNN` nicht gelistet;
Backup ohne `hrv`; Malik 0,30 bei PPI wirkt.

**Unklarheiten:** `hrv_metrics_cache` nur in der Migration; `measurement.source='hrv'` nie
geschrieben; Golden-Datei 2026-05-23 ohne `geraet_profil`/`intervall_quelle` (Altformat);
`kompatibilitaet.md` 6a (uncommittet) sagt „praxis_gui liest Backups nicht“ — **falsch**,
`praxis_gui/main.py:2167/2286` stellt sie wieder her, samt `_wiederherstellung`; CLAUDE.md:139
nennt die `datenqualitaet`-Werte als `intervall_quelle`; Doku „live 300–2000 ms“, tatsächlich
250–2000 über `regeln_setzen`; `Aufnahme.schlag` lässt `tw_src="g"` zu.

## 3. Algorithmen und Parameter

| Thema | Wert | Fundstelle |
|---|---|---|
| Plausibilität | 250–2000 ms; Herzuhr 300–2000; DFA fest 300–2000 | `constants.py:54-63`, `segments.py:60`, `aufnahme.py:129`, `nonlinear.py:111` |
| Malik | Fenster 5, 0,20 EKG / 0,30 PPI, zwei Durchläufe, Rand `edge` | `constants.py:101-103`, `artifacts.py:29, 67-81` |
| Automatik-Kandidaten | 1 `rr==0` nur bei `nullen=True` (Vorgabe aus); 2 Grenzen; 3 `fehler_ms > 50`; 4 Malik auf überbrückter Reihe | `korrektur.py:277-305`, `constants.py:112` |
| Ketten | merge_gap 2, auto_max 2, unsicher_max 5, max_luecke 3,0 s; Rampe zwischen gültigen Ankern | `constants.py:121-124`, `korrektur.py:327-345, 495-526` |
| Regeln-Vorgaben | `sensor_verwerfung="sensor"`, `vorauswahl="alle"`, `nullen=False`; Lesen begrenzt (Malik 0,05–0,5, rr_min 100–500) | `regeln.py:54-99` |
| Nähte | Messlücken + Verwerfungen; Divergenz über 5 Schläge > 5 s | `korrektur.py:529-539`, `segments.py:154-163`, `constants.py:180` |
| Zeitbereich | SDNN ddof=0, pNNx strikt > (Vorgabe 50), Differenzen je Segment, ≥ 2 Schläge | `time_domain.py:53-57` |
| Lomb | wie scipy 1.18, Blöcke 256 Frequenzen, Intervallmitten, Mittelwertabzug, ·2T/N, Raster df=max(1/T, 0,5/2000) bis 0,5 Hz | `frequency.py:112, 176-212, 243-245, 436` |
| Welch (nur Golden-Tests) | 4 Hz linear, nperseg 256, Schritt n−n//2, Hann periodisch, 1/(fs·Σw²), einseitig; `WELCH_OVERLAP` ungenutzt | `frequency.py:128-152, 248-289`, `constants.py:144` |
| Bänder / Mindestdauer | ULF/VLF/LF/HF/TP wie praxis_gui; 14400/1200/300/180 s | `constants.py:78-93` |
| Bandpolitik | Deckung ≥ 50 %, MAX_GAP 300/60/10/2, MAX_MISSING 20/15/10/5 %, ≥ 60 Schläge | `constants.py:70-73, 182-187`, `frequency.py:601-666` |
| Langer Weg (≥ 4000 s) | LF/HF 5-min-Fenster halb überlappend (1/300 Hz); VLF 2-s-Mittel, 30 min, Hann; ULF 30-s-Mittel | `constants.py:134-142`, `frequency.py:516-563` |
| Fensterspektrum | ≥ 30 gute Schläge, ≥ 70 % Belegung; Gipfel 0,04–0,40 Hz | `frequency.py:115-120, 860-905` |
| DFA α1 | Skalen 4–16, Fenster 200, Boxen um s//2, linear; wie `nk.fractal_dfa` (1e-12); `DFA_DETREND_BOX` ungenutzt; Trends ≥ 100 Schläge | `constants.py:149-152`, `nonlinear.py:80-152`, `trends.py:72` |
| SampEn | m=2, r=0,2·SD (ddof=0), Chebyshev ≤ r, i<j; UI-Deckel 3000 | `nonlinear.py:155-199`, `messung_detail.py:393` |
| Atmung | wie praxis_gui (gemeinsames Modul), `ATEM_VERSION=1` | `atmung.py:59-111` |
| Abschnitte | Atem-Median 60-s-Fenster/15 s; LF/HF ab 120 s; < 10 s verworfen | `ausschnitte.py:73, 203-212` |
| Live | Puffer 1800 s; RMSSD 30 s, SDNN 60 s, HF-Mittel 60 s; Schwankung 6×10 s; ≥ 5 Schläge | `constants.py:170-175`, `live.py:131-151` |
| Kontinuitätsuhr | Anker = Minimum über 60 Pakete; neu ab 3 s | `zeitachse.py:36, 64` |
| Trends | Schritt Fenster/10 (1–10 s), ≤ 600 Punkte, Cache ab 20000 geleert | `trends.py:62-69, 277-303, 372` |
| Training | DFA-Fenster 120 s/5 s; Artefaktgrenze 3 %; Bereiche > 1,0 / 0,75–1,0 / 0,5–0,75 / < 0,5 | `training.py:30-40` |

## 4. Abhängigkeiten und Importregel

Laufzeit: `numpy>=2.1` als einzige binäre Abhängigkeit (`pyproject.toml:11-23`, scipy fehlt auf
Android/iOS). Regel in `CLAUDE.md:44-56`, `docs/architektur.md:3-44`, `hrv_core/__init__.py:3`,
`frequency.py:1-11`: `hrv_core → nur numpy`; `ui → core, data, hrv_core, devices`;
`devices → hrv_core, core`; `data → core`; `core → nichts`.

`tests/test_import_regel.py` prüft per AST (`core`, `data`, `devices` ohne flet; `hrv_core`
zusätzlich ohne scipy). **Lücke:** relative Importe werden übersprungen (41–43) und
`hrv_core → devices/data/core` ist nicht verboten. hrv-core bringt einen geschärften Test mit.

## 5. Tests

| Datei | Prüft |
|---|---|
| `test_hrv_core.py` (236) | Grenzen, Naht-Skip, ddof, pNN, Malik-Rand, Lücken, Poincaré |
| `test_frequenz.py` (294) | Golden gegen praxis_gui/scipy 1.18.1 (rel. 2e-5), Nullen, Normierung, Bandpolitik, langer Weg |
| `test_nichtlinear.py` (70) | DFA gegen neurokit2 (1e-12), SampEn gegen praxis_gui (5e-5) |
| `test_korrektur.py` (487) | 9 Golden-Ketten (RMSSD 44,816 / SDNN 90,123 wie praxis_gui), Sidecar-Roundtrip, Live |
| `test_korrektur_regeln.py` (448) | „selbst prüfen“ (RMSSD 21,8946), Regeln, `corrections_ppi` |
| `test_atmung.py` (203) | Signale, VHF, Mayer-Welle, Golden, Byte-Vergleich mit praxis_gui |
| `test_ausschnitte.py`, `test_trends.py`, `test_export.py`, `test_ppi_live/naehte/zeitachse.py`, `test_hrv_aufnahme.py`, `test_kompatibilitaet.py`, `test_import_regel.py` | je Modul |

Golden-Dateien `tests/golden/rr/` (4, siehe dortiges README). Testlauf 2026-10-15 ohne Cache:
`PYTHONDONTWRITEBYTECODE=1 PRAXIS_GUI_PFAD=… .venv/bin/python -m pytest -q -p no:cacheprovider
test_hrv_core test_frequenz test_nichtlinear test_atmung test_trends test_import_regel test_ppi_*`
→ **129 passed in 4,5 s** (Byte-Vergleich inklusive). Nicht gelaufen: `test_korrektur*`,
`test_ausschnitte`, `test_export`, `test_hrv_aufnahme`, `test_kompatibilitaet` (schreiben Dateien).

## 6. Hinweise auf Teilung mit praxis_gui

Bereits geteilt: `atmung.py`. Absichtlich gleich nachgebaut: `constants.py:3-6`,
`time_domain.py:3`, `frequency.py:1-11`, `nonlinear.py:3-6`, `korrektur.py:10-14`,
`ereignisse.py:3-4`, `zeitachse.py:3`, `devices/pmd.py:3-5`. Dokumentierte Abweichungen
(`docs/hrv_algorithmen.md`, `docs/korrektur.md`) stehen in `hrv-core/docs/VERGLEICH.md`.

Vor dem Umzug zu bereinigen: ungenutzte Konstanten `WELCH_OVERLAP`, `DFA_DETREND_BOX`,
`RECOMMENDED_BEATS_FREQUENCY`, `SAMPEN_MAX_BEATS_LIVE` (nur Docstring); Atem-Median doppelt
(`messung_detail.py` und `ausschnitte.py:192-198`, H11).

## 7. Zu erledigen in Phase 3 (trainingsapp, Branch `refactor/hrv-core`, eigene Sitzung)

- `.gitignore`: `.backup_*.json` ergänzen.
- `src/trainingsapp/hrv_core/` löschen, 140 Importzeilen auf `hrv_core` umstellen; `test_import_regel`
  anpassen (hrv-core bringt seinen eigenen Test mit).
- `[tool.uv.sources] hrv-core = { path = "../hrv-core", editable = true }` und
  `[tool.flet.dev_packages] hrv-core = "../hrv-core"` — prüfen, ob `flet build` Pfade außerhalb
  des Projekts nimmt (sonst Kopie/Symlink unter `erweiterungen/`).
- Rechenlogik aus `messung_detail.py` (`_Zustand`, Atem-Median, SampEn-Deckel) in die Bibliothek.
- Automatikmodus bleibt Vorgabe; Expertenmodus (Korrekturregeln sichtbar) als Zuschaltung.

## 8. Übergabe an die Phase-3-Sitzung in trainingsapp (Stand 2026-10-16, hrv-core v0.1.0)

hrv-core liegt unter `../hrv-core` (github ben85keilert/hrv-core, Tag `v0.1.0`, 299 Tests grün).
Es enthält genau diese 17 Module, unverändert: constants, artifacts, time_domain, segments,
frequency, nonlinear, atmung, ppi, regeln, korrektur, live, trends, zeitachse, recording, aufnahme,
ereignisse, ausschnitte — Importpfad `hrv_core.<modul>` statt `trainingsapp.hrv_core.<modul>`.

Schritte auf dem Branch `refactor/hrv-core` (steht schon, ein Commit mit `scripts/export_referenz.py`):
1. `pyproject.toml`: `"hrv-core"` in `dependencies`; `[tool.uv.sources] hrv-core = { path = "../hrv-core", editable = true }`;
   `[tool.flet.dev_packages] hrv-core = "../hrv-core"` — prüfen, ob `flet build` Pfade außerhalb des
   Projekts nimmt (sonst Symlink/Kopie unter `erweiterungen/`); `uv sync`.
2. `src/trainingsapp/hrv_core/export.py` → `devices/` oder `core/` (Diagnose, ZIP), `training.py` →
   `core/` (GPX); beide importieren dann `from hrv_core...`. Danach `src/trainingsapp/hrv_core/` löschen.
3. 140 Importzeilen `trainingsapp.hrv_core` → `hrv_core` (ui/, devices/ relativ `..hrv_core`, Tests,
   docs/tutorial). Doctests: `uv run pytest --doctest-modules src/trainingsapp/core`.
4. Tests, die jetzt in hrv-core liegen, hier löschen: test_hrv_core, test_frequenz, test_nichtlinear,
   test_korrektur, test_atmung, test_ausschnitte, test_trends, test_ppi_naehte, test_ppi_zeitachse,
   test_kompatibilitaet, test_hrv_aufnahme. Bleiben (App): test_ppi_live, test_korrektur_regeln,
   test_export, test_notizen, test_analyse_leistung, test_messlauf, UI-Tests. `tests/golden/rr/` darf
   bleiben, solange ein Test es liest (hrv-core hat Kopien unter tests/fixtures/trainingsapp).
5. `tests/test_import_regel.py`: `hrv_core` aus der Ordnerliste nehmen; neue Regel „`trainingsapp.*`
   importiert nie scipy“ bleibt sinnvoll. `scripts/export_referenz.py` löschen (ersetzt durch
   `hrv-core/scripts/golden_erneuern.py`).
6. `docs/hrv_algorithmen.md`, `docs/korrektur.md`: durch Verweis auf hrv-core ersetzen (Kopien liegen
   dort); CLAUDE.md und `docs/architektur.md` (Importregel: `hrv_core` ist jetzt extern, numpy-only).
7. Referenzvergleich: `uv run pytest` hier grün, und in hrv-core `uv run pytest` (Golden 1e-9).
8. Eigene Messung live aufzeichnen, speichern, auswerten; Merge erst nach Bens Freigabe.

Entscheidungen Ben 2026-10-16: EKG-Auswertung entfällt (kein NK2); Dateinamen bleiben UTC-Start
(praxis_gui zieht nach); Automatik bleibt Vorgabe, Expertenmodus zuschaltbar; Kurseditor in der App
kommt nach der Umstellung beider Apps in die Planung (Inhalte später im privaten Repo
`trainingsapp-inhalte`).
