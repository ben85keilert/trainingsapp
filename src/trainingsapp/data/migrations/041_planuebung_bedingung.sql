-- Workout W2/W3 (Ben, 7.11.2026; docs/plan_workout.md §1, core/bedingung.py): je Planübung die
-- Bedingung fürs Weiterkommen und ihr Zweig.
-- `plan_item.bedingung_json`: `core.bedingung.Bedingung.als_dict` — Art (keine, zeit, wdh,
--   wdh_in_zeit, gemacht), n, sekunden, hart (Freischaltung), inhalt (text, url), zweig
--   (A = Hauptzweig, B, C, D), dann/sonst (Planübung, zu der es weitergeht). NULL = nichts
--   eingestellt (wie W1: Zeit ab oder „Weiter“ von Hand, Zweig A).
-- Eine eigene Spalte wie `acc_json`/`takt_json` (Migration 039): Die Bedingung gehört zur
-- Planübung, nicht zur Übung — dieselbe Übung kann in Plan X 15 Wdh. und in Plan Y Zeit ab haben.
ALTER TABLE plan_item ADD COLUMN bedingung_json TEXT;
