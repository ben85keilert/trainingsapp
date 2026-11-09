-- Durcharbeiten (Ben, 9.11.2026, P166–P168; docs/plan_verzweigungen.md §8.10).
-- `plan.freischaltung_seit`: ab wann die Freischaltungen eines Plans mit Ablauf zählen — was in
--   der Liste frei ist, liest die App aus den genommenen Kanten (`plan/kante`) aller Einheiten,
--   die ab hier begannen (`EinheitRepo.tore_offen`). „Freischaltungen zurücksetzen“ im Reiter
--   „Ablauf“ setzt es auf jetzt; NULL = alle Einheiten zählen. Keine Messwerte, kein Paketfeld.
ALTER TABLE plan ADD COLUMN freischaltung_seit TEXT;
