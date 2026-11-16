-- Der Kursplan: ein Plan, den ein Kurs mit der Person über die Kapitel baut (Ben, 16.11.2026,
-- docs/plan_kurs_ablauf.md §3.1 und §11.1).
--
-- `course.kursplan_json`: `core.kurse.Kursplan.als_dict` — Name, Wochentage und die Grundlage
--   des Plans (Schlüssel eines Paketplans oder eine Vorlage, die sonst nirgends erscheint).
--   NULL = der Kurs legt wie bisher je Kapitel eigene Pläne an (Kapitelpläne).
-- `plan.course_id`: der Kurs, dessen Kursplan dieser Plan ist — die Herkunft ist der Kurs, nicht
--   ein Kapitel (`course_chapter_id` bleibt bei ihm NULL). Der **laufende** Kursplan eines
--   Profils hat `course_run_ended_at IS NULL` (Migration 063); „Von vorn“ macht ihn zum
--   früheren Durchlauf. NULL = kein Kursplan.
-- `plan.course_state_json`: der Kurs-Stand — was der Kurs je Marke zuletzt gesetzt hat (Ziel,
--   Timer, Takt, Parameter, Wege) und welche Änderungen schon übernommen sind
--   (`core.kursplan`). Daran erkennt er, was die Person seither selbst geändert hat.
-- `plan_item.course_mark`: die Marke, an der der Kurs seine Planübung wiederfindet — die
--   Block-ID des Bausteins, bei einer Auswahl `<block>:<übung>`, in der Grundlage `g:<n>`;
--   leer = keine (eine Planübung, die die Person selbst hinzugefügt hat).
-- `course_id` und `course_state_json` sind gerätelokal wie `course_run_ended_at`:
-- `PlanRepo.speichern` fasst sie nicht an. Die Marke dagegen schreibt es mit — es ersetzt die
-- Übungsliste, sonst ginge sie bei jedem Speichern aus dem Plan-Editor verloren.
ALTER TABLE course ADD COLUMN kursplan_json TEXT;
ALTER TABLE plan ADD COLUMN course_id TEXT;
ALTER TABLE plan ADD COLUMN course_state_json TEXT;
ALTER TABLE plan_item ADD COLUMN course_mark TEXT NOT NULL DEFAULT '';
