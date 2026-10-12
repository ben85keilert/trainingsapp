-- Tagesnotiz: die oberste Ebene des Tagebuchs.
--
-- Notizen gibt es auf drei Ebenen — Übung (session_entry.note), Training
-- (session.note) und Tag (hier). Das Tagebuch ist keine Tabelle, sondern eine
-- Abfrage über alle drei. Der Tag ist ein LOKALER Kalendertag ('YYYY-MM-DD'),
-- bestimmt über core.models.lokaler_tag(); Zeitstempel bleiben UTC.
--
-- Je Profil und Tag genau eine Notiz, veränderbar („letzter Schreiber gewinnt",
-- deshalb revision wie bei den anderen veränderlichen Metadaten).
CREATE TABLE day_note (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    date              TEXT NOT NULL,
    text              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT,
    UNIQUE (subject_id, date)
);

-- Tagesansicht und Kalender fragen Einträge nach Zeitpunkt ab, der Verlauf
-- nach Übung — beides über session_entry.started_at.
CREATE INDEX idx_entry_zeit ON session_entry(started_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_entry_uebung_zeit ON session_entry(exercise_id, started_at) WHERE deleted_at IS NULL;
