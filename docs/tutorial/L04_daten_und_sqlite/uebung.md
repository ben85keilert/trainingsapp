# L04 — Übung

## Aufgabe 1: Schema lesen

Öffne `src/trainingsapp/data/migrations/001_init.sql` und beantworte:

1. Warum hat `session_entry` die Spalte `spec_snapshot_json`?
   (Der Kommentar im Schema hilft — aber formuliere es in eigenen Worten.)
2. Was bedeutet `replaces_entry_id`, und warum werden Einträge nicht einfach
   geändert?
3. Warum gibt es eine Tabelle `subject`, obwohl Edition A für eine Person gedacht ist?
4. In `tombstone` stehen nur ID und Zeitstempel. Warum ausdrücklich keine
   weiteren Daten?

## Aufgabe 2: Beispiele nachvollziehen

Führe alle drei Beispiele aus.

**Fragen zu Beispiel 2:**
Die Suche nach „schulter" findet auch die Nackendehnung. Warum? Ist das ein
Fehler oder gewollt? Wie würdest du es ändern, wenn nur Namen durchsucht werden
sollen?

**Frage zu Beispiel 3:**
Warum muss `PRAGMA foreign_keys = ON` bei *jeder* Verbindung gesetzt werden und
nicht einmal beim Anlegen der Datei?

## Aufgabe 3: Das echte Repository

Schreibe `src/trainingsapp/data/repositories.py` mit einer Klasse `ExerciseRepo`:

```python
class ExerciseRepo:
    def __init__(self, con: sqlite3.Connection) -> None: ...

    def speichern(self, uebung: Exercise) -> None: ...
    def laden(self, uebung_id: str) -> Exercise | None: ...
    def alle(self, kategorie: str | None = None) -> list[Exercise]: ...
    def suchen(self, text: str) -> list[Exercise]: ...
    def kategorien(self) -> list[str]: ...
    def archivieren(self, uebung_id: str) -> None: ...
```

Anforderungen:
- `speichern` legt an **oder** aktualisiert (`INSERT ... ON CONFLICT(id) DO UPDATE`)
- `archivieren` setzt `archived = 1`, löscht nicht
- `alle` und `suchen` überspringen archivierte und gelöschte Einträge
- alles über Platzhalter
- keine `flet`-Importe (der Importtest prüft es)

Und Tests in `tests/test_repositories.py`:
- speichern und wieder laden ergibt dasselbe Objekt
- `alle()` nach Kategorie filtern
- archivierte tauchen nicht in `alle()` auf
- eine unbekannte ID liefert `None`, keine Ausnahme
- eine Übung mit Apostroph im Namen funktioniert

## Aufgabe 4: Seed einspielen

Schreibe `src/trainingsapp/data/seed.py` mit `seed_einspielen(con)`:

- liest `data/seed/exercises.json`
- legt fehlende Übungen an
- lässt vorhandene **unangetastet** (der Nutzer könnte sie geändert haben)
- gibt zurück, wie viele neu angelegt wurden

Die Spezifikationen liegen im JSON als Kurzname (`"spec": "saetze_wdh"`). Bilde
sie auf die Vorlagen in `core/result_spec.py` ab.

Test: zweimaliges Einspielen legt beim zweiten Mal nichts an.

## Zum Nachdenken

`hrv_recording` speichert `file_path` und `sha1` statt der Herzschläge.

1. Was passiert, wenn jemand die Datei löscht, die Datenbank aber behält?
2. Wozu ist `sha1` gut?
3. Wann wäre eine Tabelle für einzelne Schläge doch die bessere Wahl?

[Lösungen](loesung/)
