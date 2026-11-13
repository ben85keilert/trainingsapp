-- Dokumente als Anhang (Ben, 13.11.2026: „einen Dokumentenscan (mehrseitig) einbauen und das
-- Dokument herunterkomprimieren“ — `docs/plan_anhaenge.md`, Teil I).
--
-- `entry_media.kind` erlaubt zusätzlich 'document' (ein PDF: aus der Kamera Seite für Seite
-- gebaut oder als Datei gewählt). Den CHECK kann SQLite nur über einen Neubau der Tabelle
-- ändern, wie in Migration 029; auf `entry_media` verweist keine andere Tabelle. Die Zeilen
-- bleiben, wie sie sind.
CREATE TABLE entry_media_neu (
    id                TEXT PRIMARY KEY,
    session_entry_id  TEXT REFERENCES session_entry(id) ON DELETE CASCADE,
    subject_id        TEXT REFERENCES subject(id),
    day               TEXT,
    kind              TEXT NOT NULL CHECK (kind IN ('video', 'image', 'audio', 'document')),
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
    day_note_id       TEXT REFERENCES day_note(id),
    CHECK ((session_entry_id IS NULL) <> (day IS NULL)),
    CHECK (day IS NULL OR subject_id IS NOT NULL)
);
INSERT INTO entry_media_neu (
    id, session_entry_id, subject_id, day, kind, uri, recorded_at, bytes, dauer_s, breite,
    hoehe, vorschau, qualitaet, note, created_at, day_note_id
)
SELECT id, session_entry_id, subject_id, day, kind, uri, recorded_at, bytes, dauer_s, breite,
       hoehe, vorschau, qualitaet, note, created_at, day_note_id
FROM entry_media;
DROP TABLE entry_media;
ALTER TABLE entry_media_neu RENAME TO entry_media;
CREATE INDEX idx_entry_media ON entry_media(session_entry_id);
CREATE INDEX idx_entry_media_recorded ON entry_media(recorded_at);
CREATE INDEX idx_entry_media_tag ON entry_media(subject_id, day) WHERE day IS NOT NULL;
CREATE INDEX idx_entry_media_notiz ON entry_media(day_note_id) WHERE day_note_id IS NOT NULL;
