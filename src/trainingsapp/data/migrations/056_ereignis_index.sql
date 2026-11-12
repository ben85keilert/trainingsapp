-- Durchsicht 10.11.2026, D24: Abfragen über alle Einheiten eines Profils suchen Ereignisse
-- nach Quelle und Art (plan/kante, plan/start, person/eintrag) — bisher über den ganzen
-- Bestand, der mit jedem Workout wächst. Nur ein Index, keine Daten.
CREATE INDEX IF NOT EXISTS idx_einheit_ereignis_art ON einheit_ereignis(quelle, art, einheit_id);
