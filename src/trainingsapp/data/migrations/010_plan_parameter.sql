-- Parameter einer Planübung (Ben, 14.10.2026)
--
-- Statt der Eingabestufe „nur abhaken / Chips / frei" wählt der Plan, welche
-- Parameter der Übung er anbietet (Wiederholungen, Haltezeit, Skala …):
--   NULL  wie die Übung (ihr Standard, sonst alle)
--   '[]'  keiner → nur abhaken
--   '["reps","scale"]'  genau diese
-- Chips je Parameter stehen weiter in quick_json; eine leere Liste heißt dort
-- „keine Chips, nur das freie Feld". Das freie Feld gibt es in der Ausführung
-- bei jedem Messwert ohnehin.
--
-- input_mode bleibt für ältere Stände und die Synchronisation stehen und folgt
-- den Parametern: 'haken' bei '[]', sonst 'chips'. Die Übung bekommt denselben
-- Standard für neue Pläne (default_fields_json).
ALTER TABLE plan_item ADD COLUMN fields_json TEXT;
ALTER TABLE exercise ADD COLUMN default_fields_json TEXT;
UPDATE plan_item SET fields_json = '[]' WHERE input_mode = 'haken';
UPDATE exercise SET default_fields_json = '[]' WHERE default_input_mode = 'haken';
