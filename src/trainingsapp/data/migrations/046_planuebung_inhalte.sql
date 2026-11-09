-- Eigene Inhalte der Planübung (Ben, 9.11.2026; docs/plan_paketinhalte.md §9, U2).
-- `plan_item.description`: Abschnitte wie die Beschreibung der Übung (`## Name`-Zeilen,
--   `core/beschreibung.py`) — Anweisungen für diesen Plan, aus dem Paketplan oder selbst
--   geschrieben. Leer = keine.
-- `plan_item.media_json`: Medien der Planübung — JSON-Liste wie im Paket
--   (`core.models.Media.als_dict`: kind, source, uri, title, license). NULL = keine.
ALTER TABLE plan_item ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE plan_item ADD COLUMN media_json TEXT;
