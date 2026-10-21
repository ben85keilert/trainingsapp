-- Tagesfelder: Parameter und Tags an der Tagesnotiz (Ben, 21.10.2026,
-- docs/plan_tagesfelder.md).
--
-- Ein Tagesfeld ist ein frei benanntes Tag-Label je Profil — „Schmerz“ (Skala),
-- „Trinken“ (Menge), „Ibu“ (Anzahl mit Varianten), „Ernährung“ (nur Text). Bewusst
-- keine Übung: Pläne, Kurse, Pakete und Katalog lesen `exercise`/`session_entry` und
-- sollen Tagesfelder nie sehen.
--
-- `day_field` ist veränderlich („letzter Schreiber gewinnt“, revision wie day_note).
-- `active` = 0: ausgeschaltet (steht nicht unter Heute, alles bleibt).
-- `deleted_at`: gelöscht — die Werte bleiben, außer sie wurden mitgelöscht.
CREATE TABLE day_field (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    name              TEXT NOT NULL,
    -- ResultSpec: ein Wertfeld `value` (keins bei „nur Text“), wahlweise `variant`
    spec_json         TEXT NOT NULL DEFAULT '{}',
    -- 0 = einmal am Tag (ein Wert je Tag und Variante), 1 = mehrmals mit Uhrzeit
    mehrmals          INTEGER NOT NULL DEFAULT 0,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);
CREATE INDEX idx_day_field_profil ON day_field(subject_id, sort_order);

-- Ein Wert eines Tagesfelds. UNVERÄNDERLICH wie session_entry: eine Korrektur ist
-- eine neue Zeile, die die alte über `replaces_value_id` ersetzt. `date` ist der
-- lokale Kalendertag wie day_note.date, `recorded_at` der Zeitpunkt in UTC.
-- Bei „nur Text“ steht der Text in `note`.
CREATE TABLE day_value (
    id                  TEXT PRIMARY KEY,
    subject_id          TEXT NOT NULL REFERENCES subject(id),
    field_id            TEXT NOT NULL REFERENCES day_field(id),
    date                TEXT NOT NULL,
    recorded_at         TEXT NOT NULL,
    result_json         TEXT NOT NULL DEFAULT '{}',
    -- Kopie der Felddefinition beim Erfassen — angezeigt wird immer mit ihr
    spec_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    note                TEXT NOT NULL DEFAULT '',
    replaces_value_id   TEXT REFERENCES day_value(id),
    created_at          TEXT NOT NULL,
    origin_device_id    TEXT,
    deleted_at          TEXT
);
CREATE INDEX idx_day_value_tag ON day_value(subject_id, date) WHERE deleted_at IS NULL;
CREATE INDEX idx_day_value_feld ON day_value(field_id, date) WHERE deleted_at IS NULL;
CREATE INDEX idx_day_value_ersetzt ON day_value(replaces_value_id)
    WHERE replaces_value_id IS NOT NULL;
