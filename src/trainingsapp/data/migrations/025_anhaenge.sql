-- Anhänge an Einträgen: Fotos und Videos der eigenen Übungsausführung (Ben, 19.10.2026;
-- docs/plan_anhaenge.md). `entry_media` gibt es seit Migration 001 (id, session_entry_id,
-- kind video|image, uri, recorded_at) — bisher schrieb und las sie niemand. Hier kommen
-- additiv die Kennzahlen dazu; `uri` hält den Pfad relativ zu `Anhaenge/`
-- (config.anhaengeverzeichnis). Die Datei ist die Wahrheit, die Zeile der Verweis.
ALTER TABLE entry_media ADD COLUMN bytes      INTEGER NOT NULL DEFAULT 0;
ALTER TABLE entry_media ADD COLUMN dauer_s    REAL;             -- nur Video
ALTER TABLE entry_media ADD COLUMN breite     INTEGER;
ALTER TABLE entry_media ADD COLUMN hoehe      INTEGER;
ALTER TABLE entry_media ADD COLUMN vorschau   TEXT;             -- Frontbild eines Videos, relativ
ALTER TABLE entry_media ADD COLUMN qualitaet  TEXT NOT NULL DEFAULT 'mittel';
ALTER TABLE entry_media ADD COLUMN note       TEXT NOT NULL DEFAULT '';
ALTER TABLE entry_media ADD COLUMN created_at TEXT NOT NULL DEFAULT '';
CREATE INDEX idx_entry_media_recorded ON entry_media(recorded_at);
