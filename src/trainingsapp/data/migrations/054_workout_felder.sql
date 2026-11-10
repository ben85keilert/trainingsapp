-- Eigene Skalen am Workout (Ben, 10.11.2026; docs/plan_workout_eintrag.md §3).
-- `plan.workout_felder_json`: die Namen eigener Skalen (0–10), die neben der Anstrengung zu jedem
--   Durchlauf dieses Workouts eingetragen werden können — eine JSON-Liste von Texten, höchstens
--   vier (`core.workout_eintrag.felder_bereinigt`). Gesetzt auf der Seite des Workout-Eintrags
--   („Felder …“); die Werte stehen mit einer Kopie der Felder in `workout_entry` (Migration 053).
--   Gerätelokal wie `freischaltung_seit`: kein Paketfeld, `PlanRepo.speichern` fasst die Spalte
--   nicht an. Nur Eingetragenes, keine Bewertung.
ALTER TABLE plan ADD COLUMN workout_felder_json TEXT NOT NULL DEFAULT '[]';
