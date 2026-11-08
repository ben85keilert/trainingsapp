-- Ablauf zeichnen (Ben, 8.11.2026 spät; docs/plan_verzweigungen.md §8, core/ablauf.py, G1).
-- `plan.ablauf_json`: der gezeichnete Ablauf des Plans — `core.ablauf.Ablauf.als_dict`: an
--   (der Reiter „Ablauf“ ist eingeschaltet; aus = der Plan läuft als Kette mit den Bedingungen
--   aus Migration 041), start (Startknoten), kanten[] (von, nach, ausloeser frei/zeit/wdh/skala,
--   n, bis, pflicht, ausfuehren, wiederholen, text, inhalt), fragen[] (Entscheidungsknoten:
--   id, text, min, max). NULL = kein Ablauf (Kette).
-- `plan_item.beiname`: unterscheidet zwei gleiche Übungen im Bild („2. Durchgang“); leer = keiner.
ALTER TABLE plan ADD COLUMN ablauf_json TEXT;
ALTER TABLE plan_item ADD COLUMN beiname TEXT NOT NULL DEFAULT '';
