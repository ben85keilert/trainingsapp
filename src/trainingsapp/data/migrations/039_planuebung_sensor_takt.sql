-- Planübung folgt der Übung auch beim Beschleunigungssensor und beim Takt (Ben, 5.11.2026,
-- A6; docs/plan_beschleunigung.md §13, docs/plan_taktgeber.md §5, docs/plan_uebungen_einstellen.md).
--
-- Eigene Spalten wie `timer_json` (Migration 020), nicht im Timer-JSON versteckt: Die Karte
-- und der Takt sind keine Timer-Wahl, und „wie die Übung“ braucht ein eigenes NULL.
-- `plan_item.acc_json`: `core.zaehlen.SensorWahl.als_dict` der Planübung — NULL = wie die
--   Übung (`exercise.acc_json`), sonst gilt nur hier, was darin steht (auch `{}`: eine
--   eigene Wahl mit den Vorgaben).
-- `plan_item.takt_json`: `core.takt.Takt.als_dict` der Planübung — NULL = wie die Übung
--   (`exercise.takt_json`), `{}` = ausdrücklich kein Takt, sonst dieser Takt nur hier.
-- Vorrang beim Üben: Uhr für jetzt > Timer-Abschnitt > Planübung > Übung.
ALTER TABLE plan_item ADD COLUMN acc_json TEXT;
ALTER TABLE plan_item ADD COLUMN takt_json TEXT;
