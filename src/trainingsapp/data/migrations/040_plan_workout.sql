-- Workout (Ben, 7.11.2026; docs/plan_workout.md §3): ein Plan, der von vorn bis hinten
-- durchläuft — der zweite Trainingsmodus neben „Standard“ (eine Übung je Bild).
-- `plan.workout`: der Plan öffnet mit dem Start-Bild des Workouts (0/1; Vorgabe 0 — jeder
--   Plan lässt sich trotzdem für heute „Als Workout“ starten).
-- `plan.uebergang_hart`: Vorgabe des Übergangs — 1 = hart (nach dem Timer sofort weiter),
--   0 = weich (der Timer zählt ins Minus, „Weiter“ von Hand); vor dem Start umstellbar.
-- Eigene Spalten neben `auto_next`/`pause_no_timer` (Ablauf, Migrationen 020/021): Der
-- Übergang des Workouts ersetzt beim Workout deren Paar, der Ablauf behält es.
ALTER TABLE plan ADD COLUMN workout INTEGER NOT NULL DEFAULT 0;
ALTER TABLE plan ADD COLUMN uebergang_hart INTEGER NOT NULL DEFAULT 0;
