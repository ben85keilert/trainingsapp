-- Paketmanager (Ben, 14.10.2026): Pakete lassen sich wieder entfernen, und jede
-- Übung eines Pakets kennt ihren Paketstand — „Auf Paketstand setzen“ holt ihn
-- zurück, wenn man die Übung geändert hat.
--
-- `exercise.package_standard_json`: die Übung, wie das Paket sie beim letzten
-- Import festlegte (`core/pakete.stand`: Beschreibung, Parameter samt Chips,
-- Ziel, Planparameter, Typen, Regionen, Videos). NULL bei eigenen Übungen.
-- `ExerciseRepo.speichern` lässt die Spalte stehen; sie schreibt nur der Import.
--
-- `package.removed_at`: entfernt. Die Übungen liegen dann im Papierkorb (wie
-- beim Löschen einzelner Übungen; Einträge bleiben). Ein neuer Import oder
-- „Wieder installieren“ holt sie zurück — auch, was inzwischen endgültig
-- gelöscht wurde.
ALTER TABLE exercise ADD COLUMN package_standard_json TEXT;
ALTER TABLE package ADD COLUMN removed_at TEXT;
