-- „Im Verlauf zusammen mit“ ausgebaut (Ben, 26.10.2026: „Vielleicht wird man später
-- Verläufe zusammenzählen können, aber noch ist das nicht geplant.“)
--
-- Migration 007 ließ Kopien die Kachel ihres Originals teilen (`family_id`). Jede Übung
-- hat jetzt im Verlauf ihre eigene Kachel; der Editor, die Kopie, der Paketimport
-- (`variante_von`) und die Kursbedingungen kennen die Zuordnung nicht mehr. Die Spalte
-- bleibt stehen — SQLite kann eine Spalte mit Fremdschlüssel nicht fallen lassen —,
-- wird aber geleert, damit ein späteres Zusammenzählen nicht auf alten Zuordnungen
-- aufsetzt, die niemand mehr sieht. Der Index geht.
DROP INDEX IF EXISTS idx_exercise_familie;
UPDATE exercise SET family_id = NULL WHERE family_id IS NOT NULL;
