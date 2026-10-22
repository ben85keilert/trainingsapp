-- Anhänge auch als Audio und auch am Tag (Ben, 22.10.2026: „Auch eine Audioaufnahme soll
-- möglich sein + Photo + Video. Erweitere die Medien um Audio.“ — an der Notiz zum Tag).
--
-- Zwei Änderungen an `entry_media`, die SQLite nur über einen Neubau der Tabelle kann:
-- - `kind` erlaubt zusätzlich 'audio' (der CHECK aus Migration 001 kannte nur Video/Bild);
-- - ein Anhang hängt an einem Eintrag (`session_entry_id`) ODER am Tag eines Profils
--   (`subject_id` + `day`, lokaler Kalendertag 'YYYY-MM-DD' wie `day_note.date`) — genau
--   eins von beiden. Anhänge am Tag gehören nicht zur Notiz selbst: Ist ihr Text leer,
--   bleiben sie trotzdem am Tag.
--
-- Auf `entry_media` verweist keine andere Tabelle, darum geht der Neubau auch mit
-- foreign_keys=ON in der Transaktion der Migration. Die Zeilen bleiben, wie sie sind.
CREATE TABLE entry_media_neu (
    id                TEXT PRIMARY KEY,
    session_entry_id  TEXT REFERENCES session_entry(id) ON DELETE CASCADE,
    subject_id        TEXT REFERENCES subject(id),
    day               TEXT,
    kind              TEXT NOT NULL CHECK (kind IN ('video', 'image', 'audio')),
    uri               TEXT NOT NULL,
    recorded_at       TEXT NOT NULL,
    bytes             INTEGER NOT NULL DEFAULT 0,
    dauer_s           REAL,
    breite            INTEGER,
    hoehe             INTEGER,
    vorschau          TEXT,
    qualitaet         TEXT NOT NULL DEFAULT 'mittel',
    note              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT '',
    CHECK ((session_entry_id IS NULL) <> (day IS NULL)),
    CHECK (day IS NULL OR subject_id IS NOT NULL)
);
INSERT INTO entry_media_neu (
    id, session_entry_id, kind, uri, recorded_at, bytes, dauer_s, breite, hoehe, vorschau,
    qualitaet, note, created_at
)
SELECT id, session_entry_id, kind, uri, recorded_at, bytes, dauer_s, breite, hoehe, vorschau,
       qualitaet, note, created_at
FROM entry_media;
DROP TABLE entry_media;
ALTER TABLE entry_media_neu RENAME TO entry_media;
CREATE INDEX idx_entry_media ON entry_media(session_entry_id);
CREATE INDEX idx_entry_media_recorded ON entry_media(recorded_at);
CREATE INDEX idx_entry_media_tag ON entry_media(subject_id, day) WHERE day IS NOT NULL;
