-- Planübungen folgen der Übung (Ben, 22.10.2026, P79; docs/plan_uebungen_einstellen.md).
--
-- Bisher kopierte eine Planübung beim Aufnehmen Ziel und Parameterwahl der Übung. Jetzt gilt
-- alles „wie die Übung“, bis man es im Plan ändert: `plan_item.target_json` = 'null' heißt
-- „Ziel wie die Übung“, `fields_json` NULL „alle Parameter der Übung“ (C2: „Was in der
-- Orginalübung steht wird überall angeboten, sonst muss Planübung geändert werden“). Damit sich
-- an bestehenden Plänen nichts ändert:

-- 1. Wer der Planvorgabe der Übung folgte (fields_json NULL), behält sie als eigene Parameter.
UPDATE plan_item
SET fields_json = (SELECT e.default_fields_json FROM exercise e WHERE e.id = plan_item.exercise_id)
WHERE fields_json IS NULL
  AND (SELECT e.default_fields_json FROM exercise e WHERE e.id = plan_item.exercise_id) IS NOT NULL;

-- 2. Die Planvorgabe der Parameter entfällt — was die Übung hat, bieten alle Pläne an.
UPDATE exercise SET default_fields_json = NULL;

-- 3. Ein Ziel, das wörtlich dem der Übung gleicht (beim Aufnehmen kopiert), folgt ihr künftig.
--    Ohne JSON-Funktionen: beide Seiten schrieb `json.dumps` — Abweichendes bleibt „nur hier“.
UPDATE plan_item
SET target_json = 'null'
WHERE target_json = (SELECT e.default_target_json FROM exercise e WHERE e.id = plan_item.exercise_id);

-- 4. „Timerzeit zählt“ an der Übung (D2) — Vorgabe an; aus = Läufe tragen nur „gemacht“ ein.
ALTER TABLE exercise ADD COLUMN clock_counts INTEGER NOT NULL DEFAULT 1;
