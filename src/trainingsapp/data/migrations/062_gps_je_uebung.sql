-- GPS je Übung (Ben, 13.11.2026, docs/plan_gps.md §12).
--
-- 1. `exercise.gps_json`: die Karte „GPS“ der Übung, `core.gps_wahl.GpsWahl.als_dict` —
--    `{}` = GPS aus, sonst die Rechenart (gehen, laufen, rad) und, wenn gesetzt, vier
--    Tempo-Grenzen in km/h. Reist im Paket als `gps` (docs/uebungspakete.md). Bis hierher
--    hing GPS an einer festen Liste von Sportarten im Code.
ALTER TABLE exercise ADD COLUMN gps_json TEXT NOT NULL DEFAULT '{}';

-- 2. `strecke.exercise_id`: bei welcher Übung das Training eingetragen wurde — daher kommen
--    sein Name und seine Tempo-Grenzen. `sportart` bleibt die Rechenart. Wie die ganze
--    Tabelle nie synchronisiert (Migration 012). Vorhandene Trainings bekommen die Übung
--    ihres Tagebucheintrags; ohne Eintrag bleibt NULL, dann heißt es nach der Rechenart.
ALTER TABLE strecke ADD COLUMN exercise_id TEXT REFERENCES exercise(id) ON DELETE SET NULL;

UPDATE strecke
   SET exercise_id = (SELECT e.exercise_id FROM session_entry e
                       WHERE e.id = strecke.session_entry_id)
 WHERE session_entry_id IS NOT NULL
;
