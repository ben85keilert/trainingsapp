-- Pause nach Übungen ohne Timer (Ben, 18.10.2026: „bisher wird ohne Timer immer eine Pause
-- gesetzt. Lässt sich das irgendwie einstellen, ob Pause drankommt oder nicht?“)
--
-- `plan.pause_no_timer`: Im Plan-Ablauf nach einer Übung ohne Timer auf „Weiter“ warten (1,
--   Vorgabe — so war es bisher) oder gleich die nächste beginnen (0); „Gemacht“ war ja schon
--   der Tipp. Gilt nur, wenn `plan.auto_next` aus ist (sonst geht es immer gleich weiter).
ALTER TABLE plan ADD COLUMN pause_no_timer INTEGER NOT NULL DEFAULT 1;
