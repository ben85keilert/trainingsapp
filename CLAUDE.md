# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sprache

Code und Bezeichner englisch, wenn es die verbreitete Schreibweise ist; Kommentare,
Docstrings und Dokumentation deutsch. **Feldnamen des Austauschformats bleiben so,
wie `praxis_gui` sie schreibt** (`intervall_quelle`, `messungen`, …) — dort zählt
Kompatibilität, nicht Konsistenz. Neuer Text (Antworten, Commit-Messages) auf Deutsch.

## Befehle

Das Projekt wird mit [uv](https://docs.astral.sh/uv/) verwaltet (`uv.lock` ist die
Wahrheit, `.python-version` pinnt Python).

Die HRV-Bibliothek **hrv-core** (github `ben85keilert/hrv-core`) ist ein Schwesterrepo und
muss als `../hrv-core` neben diesem Ordner liegen — `pyproject.toml` bindet sie editierbar
ein (`[tool.uv.sources]`, `[tool.flet.dev_packages]`), die CI checkt beide Repos nebeneinander aus.

```bash
git clone https://github.com/ben85keilert/hrv-core.git ../hrv-core   # einmalig, Schwesterordner (öffentlich, AGPL-3.0)
uv sync --extra desktop                # Entwicklungsumgebung (desktop = bleak für BLE)

uv run flet run src/trainingsapp/ui/app.py    # Desktop-Vorschau der Oberfläche
uv run flet run --android src/trainingsapp/ui/app.py   # Vorschau auf dem Handy (Flet-App aus dem Play Store, gleiches WLAN, QR-Code)
uv run pytest                                  # alle Tests
uv run pytest tests/test_messlauf.py           # eine Datei
uv run pytest tests/test_messlauf.py::test_name -q   # ein einzelner Test
uv run pytest --doctest-modules src/trainingsapp/core src/trainingsapp/devices   # Doctests (laufen in CI)
uv run ruff check . && uv run ruff format --check .   # Linter + Formatprüfung
uv run mypy                                    # Typprüfung (Paket ist in pyproject konfiguriert)
```

Vor jedem Pull Request muss laufen:
`uv run ruff check . && uv run ruff format --check . && uv run pytest`.

**Flet-API nachschlagen:** `.mcp.json` registriert den MCP-Server `flet` (`uv run flet mcp`,
Paket `flet-mcp` in der Gruppe `flet-dev`). Er kennt die API der installierten Flet-Version —
vor dem Schreiben von `ui/`- oder Tutorial-Code dort prüfen statt aus dem Gedächtnis, denn
Flet hat zwischen 0.28, 0.80 und 1.0 viel umbenannt und entfernt. `flet-mcp` immer in
derselben Version wie `flet` halten.

`TRAININGSAPP_EDITION=praxis uv run pytest …` bzw. `TRAININGSAPP_DATA_DIR=…` setzen
Edition und Datenpfad zur Laufzeit (siehe `config.py`).

## Die eine Architekturregel

`core/`, `data/` und `devices/` importieren **niemals** `flet`; nichts unter
`trainingsapp/` importiert **jemals** `scipy`. `tests/test_import_regel.py` erzwingt beides
per AST-Scan — es ist kein Stilhinweis, sondern ein grüner Test, der brechen muss, wenn
man dagegen verstößt.

Gründe: Die Domäne bleibt ohne Bildschirm testbar, und Flet-Versionswechsel (zuletzt
0.86 → 1.0) oder ein Umstieg auf das deklarative Modell betreffen nur `ui/`. `scipy`
existiert auf Android/iOS nicht — darum implementiert hrv-core Welch, Lomb-Scargle,
DFA und SampEn selbst in reinem numpy.

**Die HRV-Mathematik ist seit dem 16.10.2026 die externe Bibliothek `hrv_core`**
(Schwesterrepo hrv-core, nur numpy; gemeinsam mit praxis_gui, damit beide Apps dieselben
Zahlen liefern). Algorithmen, Korrekturregeln, Live-Fenster, Aufnahme und das Austauschformat
raw-v1 werden **dort** geändert, nie hier nachgebaut. In der App bleiben nur Anwendungsteile:
`core/hrv_export.py` (ZIP, Diagnoseprotokoll), `core/hrv_training.py` (HRV je Kilometer,
DFA-Überblick), `devices/messlauf.py` (Orchestrierung), `ui/`.

Abhängigkeiten zeigen **nur nach innen**: `ui → core, data, hrv_core, devices`;
`devices → hrv_core, core` (GPS-Punkte: `core.strecke`); `data → core`;
`core → (nur hrv_core)`; `hrv_core → (nur numpy)`.
Keine Rechenlogik in `ui/` — Views rufen Funktionen aus den unteren Schichten auf.

## Aufbau

```
src/trainingsapp/
  config.py    Edition (solo/praxis), Funktionsschalter, Speicherorte
  core/        Domänenmodelle, ResultSpec (Notation), Limit-Regeln, Einheiten
  data/        SQLite (kein ORM), .sql-Migrationen, Seed-Daten
  devices/     Geräte-Port (BLE/Simulator), Geräteprofile
  ui/          Flet — dünn
../hrv-core/src/hrv_core/   HRV-Mathematik + Austauschformat raw-v1 (Schwesterrepo, extern)
```

## Zentrale Entwurfsentscheidungen

Diese ergeben sich erst aus mehreren Dateien zusammen — hier verdichtet:

- **Die Datei ist die Wahrheit.** HRV-Rohdaten liegen als `raw-v1`-JSON-Dateien
  (byte-kompatibel zu `praxis_gui`), **nicht** in der Datenbank. Die DB hält nur den
  Verweis (`hrv_recording.file_path`) und einen Kennzahlen-Cache (`hrv_metrics_cache`)
  mit `algo_version`. Ändert sich die Rechenvorschrift (`ALGO_VERSION` in
  `hrv_core/constants.py`), gilt der Cache als veraltet und wird aus den Dateien neu
  berechnet — Rohdaten bleiben unangetastet. Export = Dateikopie. Vertrag:
  `docs/kompatibilitaet.md` — Formatänderungen brauchen dort zuerst einen Eintrag.
  Ausnahme wie in praxis_gui: Metadaten (`titel`, `notiz`, `ereignisse` = Notizen mit
  Anker) werden in die Messdatei zurückgeschrieben (`hrv_core.ereignisse`), nie die
  Messwerte.

- **GPS-Daten werden nie geteilt** (Ben, 14.10.2026): Sync, Export-ZIP,
  Teilen, Diagnose — keine Koordinaten. Strecken liegen getrennt von
  `Messungen/` (`config.streckenverzeichnis()`). Einzige Ausnahme: der
  GPX-Export, den die Person selbst auslöst (`docs/plan_gps.md`, Abschnitt 0).

- **Zwei Editionen aus einem Quelltext.** `config.ist_aktiv("funktion")` beantwortet
  „darf ich X?" statt „bin ich Edition B?". Ein Schalter je Fähigkeit, nicht je
  Bildschirm. `physiologische_steuerung` ist in `solo` **rechtlich** gesperrt (eine
  Handlungsempfehlung aus Messwerten wäre eine medizinische Aussage — siehe
  `docs/recht/00_zweckbestimmung.md`). Sync-Felder (`outbox`, `external_ref`,
  `origin_device_id`, `deleted_at`) existieren ab Migration 001, obwohl `solo` sie nicht
  nutzt.

- **Konflikte strukturell vermeiden.** `hrv_recording` und `session_entry` sind
  **unveränderlich** — eine Korrektur ist ein neuer Eintrag mit `replaces_entry_id`.
  Nur veränderliche Metadaten nutzen „letzter Schreiber gewinnt" mit serverseitiger
  Revision. Statt `dirty`-Flag eine reihenfolgetreue `outbox`.

- **ResultSpec = flexible Notation.** Jede Übung bringt eine `ResultSpec`
  (`core/result_spec.py`) mit, aus der die Eingabemaske erzeugt wird — „3x15", „45°",
  „30 s halten" sind derselbe Mechanismus. Felder kommen aus dem `FELDVORRAT`; das
  Satzfeld (`SET_LIST`) speichert eine Liste je Satz und nimmt die Notation aus
  `docs/notation.md` entgegen (`3x15`, `30`, `15/15/20`, `+20`). Hierarchie: Übung →
  Plan (`plan_item.felder` = angebotene Parameter, keiner = nur abhaken; Chips, Ziel) → Eintrag. Jeder `SessionEntry` speichert eine Kopie der
  Spec, mit der er erfasst wurde (`spec_snapshot_json`); angezeigt wird **immer** mit der
  Kopie, nie mit der aktuellen Definition. Neuer `FieldType` → hier ergänzen und in
  `ui/components/spec_form.py` ein Widget registrieren.

- **Übungen kommen über Pakete** (Ben, 14.10.2026). Der mitgelieferte Katalog ist
  das Paket „Standard“ (`data/seed/standard.toml` — TOML, weil von Hand gepflegt; IDs per UUIDv5
  aus dem Schlüssel); weitere kommen per Import, der Export schreibt nur Übungen.
  `exercise.package_id` = Herkunft, `NULL` = eigene Übung (auch Kopien). Ein Import
  aktualisiert nur die Übungen desselben Pakets — Änderungen daran gehen verloren
  (gewollt); eigene Übungen ändert er nie. Paketmanager: Jede Paketübung trägt ihren
  Paketstand (`package_standard_json`) für „Auf Paketstand setzen“; Entfernen legt die
  Übungen in den Papierkorb, „Wieder installieren“ holt sie zurück. Vertrag:
  `docs/uebungspakete.md`.

- **Kurse** (Ben, 15.10.2026): dritte Kategorie neben Übungen und Plänen —
  Kapitel linear, je Kapitel eine Bedingung (`gelesen`, `summe`, `tage`, `messung`),
  Plan-Vorlagen werden beim Erreichen zu echten Plänen (`plan.course_chapter_id`,
  beim Abschluss deaktiviert, nie gelöscht), Überspringen nur auf Rückfrage.
  Bedingungen rechnen aus Einträgen und Messdauer, **nie aus Messwerten**
  (rechtlich wie `physiologische_steuerung`). Kurse reisen in Paketen
  (`kurse[]`, Formatversion 2). Vertrag: `docs/plan_kurse.md`.

- **Geräte-Port pull-basiert.** `devices/base.py`: alle Quellen (bleak/Desktop,
  spätere Flet-Extension/Mobil, Simulator) *pushen*; der Konsument *pullt* per `async for`
  über eine begrenzte `asyncio.Queue`. Messwerte und Status laufen getrennt — Batterie
  darf den RR-Strom nicht verstopfen; bei Überlauf verfällt Status, nie ein Messwert.
  `parse_hr_measurement` liest **alle** RR-Werte eines Pakets (mehrere pro Notification
  bei >60 bpm) — nur den ersten zu lesen verlöre die Hälfte.

- **Datenqualitätsstufen** (`intervall_quelle`): `rr_ekg` (Brustgurt, volle HRV),
  `ppi_optisch` (optisch, Frequenzwerte mit Vorbehalt), `bpm_only` (keine HRV). Enthält
  eine Messung keinen RR-Wert, ist sie `bpm_only` — egal was das Geräteprofil versprach
  (`Recording.effektive_qualitaet()`).

## Datenbank-Konventionen

SQLite über `sqlite3`, kein ORM. Migrationen sind nummerierte `.sql`-Dateien in
`data/migrations/`; Version über `PRAGMA user_version` (keine Verwaltungstabelle). Jede
Migration läuft in eigener Transaktion. Verbindungen über `data.db.oeffnen()` — setzt
`foreign_keys=ON`, `journal_mode=WAL`. **SQL immer mit Platzhaltern (`?`)**, nie
String-Interpolation.

## HRV-Änderungen

Die HRV-Mathematik lebt in hrv-core — Änderungen dort, mit **Golden-Test**
(`hrv-core/tests/golden/`, Toleranz 1e-9 gegen den Stand beim Umzug) und Eintrag in
`hrv-core/docs/hrv_algorithmen.md` bzw. `korrektur.md` (Grundsatz der Korrektur:
**lieber eine Lücke als ein falscher Wert**). `docs/hrv_algorithmen.md` und
`docs/korrektur.md` hier sind nur noch Verweise. `tests/golden/rr/` bleibt für die
App-Tests (Notizen, Export, UI), die eine echte Messdatei brauchen.

## Lernprojekt

Die App entsteht entlang eines Lernpfads (`docs/tutorial/`); `ui/` ist bewusst noch eine
Hülle mit Platzhalteransichten. Die Tutorial-Beispielskripte laufen in CI mit — wenn ein
Beispiel bricht, ist der Lernpfad kaputt.