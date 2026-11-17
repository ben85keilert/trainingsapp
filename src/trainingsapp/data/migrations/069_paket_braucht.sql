-- Was ein Paket braucht (`paket.braucht`, V3/V4 in docs/plan_paketverweise.md, Ben 17.11.2026:
-- „wenn eine Übung fehlt, wird diese nachgeladen“ — und Kapitelpläne vervollständigen sich „von
-- selbst“, wenn das Paket später kommt).
--
-- Bisher las die App `braucht` nur in der Rückfrage des Imports. Gemerkt am installierten Paket
-- kann sie später noch sagen, woher die Übungen kämen, die in seinen Plänen und Kapiteln fehlen
-- („wartet auf „Standard““, mit „Laden“, wenn die Voraussetzung eine Adresse nennt). Eine Liste
-- wie im Paketkopf (`Voraussetzung.als_dict`); NULL = keine (oder ein Paket von davor).
ALTER TABLE package ADD COLUMN requires_json TEXT;
