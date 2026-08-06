# Datenmodell

Schema: `src/trainingsapp/data/migrations/001_init.sql`.
Migrationen sind nummerierte `.sql`-Dateien, die Version steht in
`PRAGMA user_version`. Kein ORM — `sqlite3` reicht und zeigt, was passiert.

IDs sind **UUIDv7** als TEXT: zeitsortiert, dadurch gute Index-Lokalität und
natürliche Sortierung ohne Zusatzspalte (`core/models.py::new_id`).

## Überblick

```
subject ──┬── session ──── session_entry ──── entry_media
          │                      │
          │                      └──────────── measurement
          ├── hrv_recording ──── hrv_metrics_cache
          ├── plan ──────── plan_item
          └── consent

exercise ──┬── exercise_media
           ├── exercise_spec_version
           └── exercise_tag ──── tag

device        external_ref     outbox     tombstone
```

## Die wichtigen Entscheidungen

**Es gibt keine Tabelle für einzelne Herzschläge.** `hrv_recording` verweist mit
`file_path` auf eine `raw-v1`-Datei; `sha1` erkennt nachträgliche Änderungen.
Begründung in `docs/architektur.md`.

**`hrv_metrics_cache` ist reiner Cache.** Er trägt eine `algo_version` und ist
jederzeit aus den Dateien neu berechenbar.

**`session_entry.spec_snapshot_json`** speichert die Eingabespezifikation, mit
der ein Eintrag erfasst wurde. Ohne sie wäre ein alter Eintrag nach einer
Änderung der Übungsdefinition nicht mehr interpretierbar.

**`session_entry` und `hrv_recording` sind unveränderlich.** Eine Korrektur
entsteht als neuer Eintrag mit `replaces_entry_id`. Damit sind
Synchronisationskonflikte strukturell ausgeschlossen.

**`subject` gibt es von Anfang an**, auch in Edition A — eine Familie teilt sich
ein Gerät. Nachträglich einzuführen wäre eine Migration über alles.

**`measurement` ist normalisiert** (`metric_key`, `value`, `unit`,
`recorded_at`) und speist sämtliche Verlaufsdiagramme: Übungsergebnisse über
`ResultSpec.chart_metrics`, Benchmarks wie „Luft anhalten" und HRV-Kennzahlen.
Entspricht in praxis_gui `Dokumentation_Skalen_Werte`.

## Synchronisation (Edition B)

| Tabelle | Zweck |
|---|---|
| `external_ref` | ordnet unsere UUIDs den INTEGER-Schlüsseln von praxis_gui zu — ohne sie kein Round-Trip |
| `outbox` | reihenfolgetreue Ausgangswarteschlange statt eines `dirty`-Flags |
| `tombstone` | Grabsteine gelöschter Datensätze |
| `consent` | Einwilligungen je Datenart |

Dazu auf allen synchronisierten Tabellen: `origin_device_id` (Mehrgerätebetrieb),
`revision` (serverseitig vergeben), `deleted_at` (Soft-Delete).

> **Zielkonflikt, der bewusst aufgelöst ist:** DSGVO Art. 17 verlangt echtes
> Löschen, die Synchronisation verlangt eine Spur des Gelöschten. In `tombstone`
> stehen deshalb ausschließlich ID und Zeitstempel — **niemals Gesundheitsdaten**.

## Fremdschlüssel

SQLite prüft Fremdschlüssel **nur**, wenn `PRAGMA foreign_keys = ON` gesetzt ist.
`data/db.py::verbinden` tut das, und `tests/test_core.py` prüft, dass es wirkt.
