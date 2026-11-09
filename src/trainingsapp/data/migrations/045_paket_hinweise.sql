-- Hinweise an Paketübungen (Ben, 9.11.2026; docs/plan_paketinhalte.md §6, U1).
-- `exercise.package_hints_json`: wo das Paket bei einem Update eine neue Fassung hatte, die
--   eigene aber blieb — JSON-Liste von [feld, teil] (`core.abgleich.Hinweis`; teil = Schlüssel
--   des Abschnitts der Beschreibung bzw. Adresse des Mediums, leer = das ganze Feld). Die
--   Übung zeigt sie, „Paketfassung übernehmen“ nimmt sie weg. NULL = keine.
ALTER TABLE exercise ADD COLUMN package_hints_json TEXT;
