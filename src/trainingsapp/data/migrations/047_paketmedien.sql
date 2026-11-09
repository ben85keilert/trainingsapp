-- Medien im Paket (U3, Ben 9.11.2026, docs/plan_paketinhalte.md §7, F3/F4).
--
-- Eine Übung bekommt Dateien aus ihrem Paket: Quelle 'paket' (Datei in der Ablage
-- Medien/Pakete/<sha256>.<endung>, uri = "medien/<sha256>.<endung>"), dazu die Arten
-- 'audio' (bisher nur an Kurskapiteln) und 'pdf' (Material, F6). SQLite ändert keine
-- CHECK-Bedingung — die Tabelle wird neu angelegt; niemand verweist auf sie.

CREATE TABLE exercise_media_neu (
    id           TEXT PRIMARY KEY,
    exercise_id  TEXT NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('video', 'image', 'audio', 'pdf')),
    -- 'url'   = online, wird bei Bedarf geladen und gecacht (Videos NICHT ins APK)
    -- 'asset' = mit der App ausgeliefert
    -- 'local' = vom Nutzer aufgenommen, app-privates Verzeichnis
    -- 'paket' = Datei aus einem Paket, Ablage Medien/Pakete/ (U3)
    source       TEXT NOT NULL CHECK (source IN ('url', 'asset', 'local', 'paket')),
    uri          TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    license      TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0
);

INSERT INTO exercise_media_neu (id, exercise_id, kind, source, uri, title, license, sort_order)
SELECT id, exercise_id, kind, source, uri, title, license, sort_order FROM exercise_media;

DROP TABLE exercise_media;
ALTER TABLE exercise_media_neu RENAME TO exercise_media;
CREATE INDEX idx_exercise_media ON exercise_media(exercise_id);
