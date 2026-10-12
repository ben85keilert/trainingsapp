-- Papierkorb für Übungen und Pläne
--
-- `deleted_at` (seit 001) heißt jetzt: liegt im Papierkorb, wiederherstellbar.
-- `purged_at` heißt: endgültig gelöscht — aus jeder Liste verschwunden und in
-- der App nicht mehr wiederherstellbar. Die Zeile selbst bleibt als Grabstein:
-- Alte Einträge behalten so ihren Namen, und der Seed legt eine mitgelieferte
-- Übung nicht beim nächsten Start wieder an (er erkennt sie an der ID).
ALTER TABLE exercise ADD COLUMN purged_at TEXT;
ALTER TABLE plan ADD COLUMN purged_at TEXT;
