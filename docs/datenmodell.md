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

app_setting   (gerätelokal, Migration 002 — wird nie synchronisiert)
day_note      (Tagesnotiz je Profil und lokalem Tag, Migration 003)
```

**Eingabe ist dreistufig** (Migration 004): Die Übung legt in `result_spec_json`
ihre Felder und Standard-Chips fest (Feldvorrat in `core/result_spec.py`, Satzfeld
mit Notation `3x15`, `30`, `15/15/20` — siehe `docs/notation.md`). Der Plan wählt je
Übung in `plan_item.input_mode` die Stufe (`haken`, `chips`, `frei`), eigene Chips
(`quick_json`) und ein Ziel (`target_json`). Der Eintrag übernimmt den Plan und darf
im Formular abweichen. Ein „+20" im Plan ist eine Korrektur des heutigen Eintrags
(`replaces_entry_id`), der Eintrag selbst bleibt unveränderlich.

**Archiv, Papierkorb, endgültig** (Migration 005): `exercise.archived` nimmt eine
Übung aus dem Katalog, Pläne zeigen sie weiter. `deleted_at` heißt „im
Papierkorb": Die Übung verschwindet auch aus den Plänen (die Planübung bleibt
gespeichert und kehrt beim Wiederherstellen zurück). Nach 30 Tagen löscht die App
endgültig (`purged_at`, abschaltbar über `app_setting.papierkorb_auto`) — aber nur
Übungen **ohne** Einträge; bei Übungen mit Verlauf fragt sie, ob die Einträge
bleiben oder mitgehen. Die Zeile bleibt auch nach dem endgültigen Löschen als
Grabstein stehen, damit alte Einträge ihren Namen behalten und der Seed eine
mitgelieferte Übung nicht neu anlegt. Pläne funktionieren genauso.

**Der Tag ist die Bezugsgröße.** Zeitstempel sind UTC, aber „heute" ist ein
lokaler Kalendertag. `core.models.tagesgrenzen()` rechnet die lokale
Mitternacht nach UTC um; alle Tagesabfragen (Tagesansicht, Kalender,
„x von n heute") vergleichen `session_entry.started_at` mit diesen Grenzen.
`day_note.date` speichert den lokalen Tag als `YYYY-MM-DD`. Eine Session ist
„ein Plan an einem Tag" und entsteht beim ersten Eintrag automatisch.

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

**Nicht synchronisiert** wird `app_setting`: Schlüssel/Wert-Paare, die nur
dieses Gerät betreffen — das zuletzt aktive Profil, später Anzeige- und
Geräteeinstellungen. Was auf einem anderen Gerät wertlos wäre, gehört dorthin
und nirgends sonst.

Dazu auf allen synchronisierten Tabellen: `origin_device_id` (Mehrgerätebetrieb),
`revision` (serverseitig vergeben), `deleted_at` (Soft-Delete).

> **Zielkonflikt, der bewusst aufgelöst ist:** DSGVO Art. 17 verlangt echtes
> Löschen, die Synchronisation verlangt eine Spur des Gelöschten. In `tombstone`
> stehen deshalb ausschließlich ID und Zeitstempel — **niemals Gesundheitsdaten**.

## Fremdschlüssel

SQLite prüft Fremdschlüssel **nur**, wenn `PRAGMA foreign_keys = ON` gesetzt ist.
`data/db.py::verbinden` tut das, und `tests/test_core.py` prüft, dass es wirkt.
