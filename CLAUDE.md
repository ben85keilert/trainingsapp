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

```bash
uv sync --extra desktop                # Entwicklungsumgebung (desktop = bleak für BLE)

uv run flet run src/trainingsapp/ui/app.py    # Desktop-Vorschau der Oberfläche
uv run pytest                                  # alle Tests
uv run pytest tests/test_hrv_core.py           # eine Datei
uv run pytest tests/test_hrv_core.py::test_name -q   # ein einzelner Test
uv run pytest --doctest-modules src/trainingsapp/core src/trainingsapp/hrv_core   # Doctests (laufen in CI)
uv run ruff check . && uv run ruff format --check .   # Linter + Formatprüfung
uv run mypy                                    # Typprüfung (Paket ist in pyproject konfiguriert)
uv run python scripts/pruefe_flet_beispiele.py   # Flet-Skripte des Lernpfads ohne Bildschirm (CI)
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

`core/`, `data/`, `hrv_core/` und `devices/` importieren **niemals** `flet`;
`hrv_core/` zusätzlich **niemals** `scipy`. `tests/test_import_regel.py` erzwingt beides
per AST-Scan — es ist kein Stilhinweis, sondern ein grüner Test, der brechen muss, wenn
man dagegen verstößt.

Gründe: Die Domäne bleibt ohne Bildschirm testbar, und Flet-Versionswechsel (zuletzt
0.86 → 1.0) oder ein Umstieg auf das deklarative Modell betreffen nur `ui/`. `scipy`
existiert auf Android/iOS nicht — darum implementiert `hrv_core/` Welch, Lomb-Scargle,
DFA und SampEn selbst in reinem numpy.

Abhängigkeiten zeigen **nur nach innen**: `ui → core, data, hrv_core, devices`;
`devices → hrv_core`; `data → core`; `core → (nichts)`; `hrv_core → (nur numpy)`.
Keine Rechenlogik in `ui/` — Views rufen Funktionen aus den unteren Schichten auf.

## Aufbau

```
src/trainingsapp/
  config.py    Edition (solo/praxis), Funktionsschalter, Speicherorte
  core/        Domänenmodelle, ResultSpec (Notation), Limit-Regeln, Einheiten
  data/        SQLite (kein ORM), .sql-Migrationen, Seed-Daten
  hrv_core/    HRV-Mathematik + Austauschformat raw-v1
  devices/     Geräte-Port (BLE/Simulator), Geräteprofile
  ui/          Flet — dünn
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
  „30 s halten" sind derselbe Mechanismus. Jeder `SessionEntry` speichert eine Kopie der
  Spec, mit der er erfasst wurde (`spec_snapshot_json`); angezeigt wird **immer** mit der
  Kopie, nie mit der aktuellen Definition. Neuer `FieldType` → hier ergänzen und in
  `ui/components/spec_form.py` ein Widget registrieren.

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

Änderungen an der HRV-Mathematik brauchen einen **Golden-Test** (Referenzdaten unter
`tests/golden/rr/`). Formeln, Konstanten und Fallstricke stehen in
`docs/hrv_algorithmen.md`.

## Lernprojekt

Die App entsteht entlang eines Lernpfads (`docs/tutorial/`); `ui/` ist bewusst noch eine
Hülle mit Platzhalteransichten. Die Tutorial-Beispielskripte laufen in CI mit — wenn ein
Beispiel bricht, ist der Lernpfad kaputt. Flet-freie Beispiele stehen als Liste im Job
`test`; jedes Skript, das `flet` importiert, findet `scripts/pruefe_flet_beispiele.py` im
eigenen Job `flet-beispiele` selbst (Control-Baum mit `page`-Attrappe, `DeprecationWarning`
= Fehler). Ereignis-Handler und Code in `.md`-Dateien prüft es nicht.