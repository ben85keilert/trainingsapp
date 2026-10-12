-- Wann ein Plan ansteht
--
-- `active` = 0 nimmt einen Plan aus „Heute", ohne ihn zu löschen.
-- `weekdays_json` listet die Wochentage, an denen er ansteht (0 = Montag …
-- 6 = Sonntag); Standard ist jeder Tag. Ein Plan, der nicht ansteht, lässt
-- sich trotzdem für einen Tag aufnehmen („Heute trainieren"): Dafür reicht
-- eine Session dieses Plans an diesem Tag — keine eigene Tabelle.
ALTER TABLE plan ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE plan ADD COLUMN weekdays_json TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]';
