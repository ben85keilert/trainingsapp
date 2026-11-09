-- Ergänzungen („Mods“, U5, Ben 9.11.2026, docs/plan_paketinhalte.md §8, F2).
--
-- Ein Paket ergänzt Übungen anderer Pakete: Abschnitte, Medien, Parameter, Ziel, Timer, Takt
-- (core/ergaenzungen.py). Gespeichert als eigene Schicht je Paket und Übung — nicht in die
-- Übung gemischt: Entfernen oder Deaktivieren des Pakets nimmt sie sauber weg, ein Update
-- ersetzt nur die eigenen. Fehlt die Übung (ihr Paket ist nicht da), wartet die Ergänzung —
-- darum kein Fremdschlüssel. `position` = Reihenfolge der Installation (die spätere gewinnt).
--
-- `exercise.package_base_json`: der Paketstand des Grundpakets, solange Ergänzungen wirken;
-- `package_standard_json` ist dann der wirksame Stand (Grundpaket + Ergänzungen), gegen den
-- der Drei-Wege-Abgleich läuft. NULL = keine Ergänzung, der Paketstand ist das Grundpaket.

CREATE TABLE exercise_addon (
    package_id   TEXT NOT NULL,
    exercise_id  TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    position     INTEGER NOT NULL,
    PRIMARY KEY (package_id, exercise_id)
);
CREATE INDEX idx_exercise_addon ON exercise_addon(exercise_id);

ALTER TABLE exercise ADD COLUMN package_base_json TEXT;
