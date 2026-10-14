-- Übungspakete (Ben, 14.10.2026): Übungen kommen über Pakete. Die
-- mitgelieferten stehen im Paket „Grundausstattung" (data/seed/exercises.json),
-- weitere — Qigong, Pilates, Yoga, eine Sammlung von jemand anderem — kommen
-- per Import dazu und gehen per Export hinaus. Format: core/pakete.py,
-- Regeln beim Import: data/pakete.py, beides in docs/uebungspakete.md.
--
-- `exercise.package_id`: aus welchem Paket die Übung auf dieses Gerät kam.
-- NULL = eigene Übung (hier angelegt oder kopiert) — eine solche ändert kein
-- Import, ein Paket „Eigene" gibt es nicht. Bearbeiten ändert die Herkunft
-- nicht; die mitgelieferten Übungen trägt `data/seed.py` beim Start nach.
--
-- `version` setzt, wer ein Paket schreibt (ganze Zahl, optional). Steigt sie
-- bei der Grundausstattung, aktualisiert der nächste Start deren Übungen.
CREATE TABLE package (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    version       INTEGER,
    installed_at  TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

ALTER TABLE exercise ADD COLUMN package_id TEXT REFERENCES package(id);
CREATE INDEX idx_exercise_paket ON exercise(package_id) WHERE package_id IS NOT NULL;
