-- Stellungen einer Paketübung (Ben, 12.11.2026, P188, core/ergaenzungen.py).
--
-- Parameter, Ziel und Takt (die „Trainingsumgebung“) gelten nicht mehr aus allen
-- Erweiterungen übereinander („die spätere gewinnt“), sondern aus EINER gewählten Stellung:
-- Standard (das Grundpaket) oder eine Erweiterung, die dort etwas setzt.
--
-- `exercise.addon_choice`: die Wahl der Person — NULL = Vorgabe (zuletzt installierte
-- Erweiterung mit Trainingsumgebung, sonst Standard), '' = Standard, sonst die Paket-ID.
-- `exercise.addon_active`: die Stellung, für die der wirksame Paketstand
-- (`package_standard_json`) gerade gebildet ist — NULL = Altbestand, noch nie gebildet.
--
-- `exercise_addon_state`: was die Person in einer Stellung geändert hat, die gerade nicht
-- gilt (`own_json`), und der Paketstand dieser Stellung beim Weglegen (`base_json`) — damit
-- beim Zurückschalten wie bei einem Update abgeglichen wird. `package_id` '' = Standard.
-- Übungen gelten je Gerät (kein Profilbezug), die Stellung darum auch.

ALTER TABLE exercise ADD COLUMN addon_choice TEXT;
ALTER TABLE exercise ADD COLUMN addon_active TEXT;

CREATE TABLE exercise_addon_state (
    exercise_id  TEXT NOT NULL,
    package_id   TEXT NOT NULL,
    own_json     TEXT NOT NULL,
    base_json    TEXT NOT NULL,
    PRIMARY KEY (exercise_id, package_id)
);
