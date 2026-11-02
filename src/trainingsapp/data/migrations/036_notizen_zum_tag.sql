-- Notizen zum Tag: mehrere je Tag, mit Tags, Anhänge je Notiz (Ben, 2.11.2026:
-- „Füge den zum Tag Notizen Tags (Merkmale) hinzu … es sollen mehrere erstellbar sein mit
-- einem ‚+‘ … Tags lassen sich löschen, die Nachricht selbst bleibt dann aber, verliert
-- einfach den Tag. Der Tag Tagebuch lässt sich nicht löschen, aber deaktivieren.“ —
-- `docs/plan_tagesnotizen.md`).
--
-- 1. `day_note` verliert `UNIQUE (subject_id, date)` — SQLite kann einen Constraint nicht
--    fallen lassen, darum der Neubau wie in Migration 029. Entfernen ist jetzt weich
--    (`deleted_at`), nicht mehr `text = ''`: Eine Notiz unter mehreren muss verschwinden.
-- 2. `note_tag`: die Tags je Profil. `fest` = 1 ist „Tagebuch“ (nicht löschbar, nicht
--    umbenennbar, nur ausschaltbar), `active` = 0 ausgeschaltet (wird nicht mehr angeboten,
--    Notizen behalten ihn). Veränderlich wie `day_field` („letzter Schreiber gewinnt“).
-- 3. `day_note_tag`: welche Notiz welchen Tag trägt. Ein gelöschter Tag bleibt verknüpft,
--    aber unsichtbar (Abfragen nehmen `note_tag.deleted_at IS NULL`) — die Notiz „verliert
--    einfach den Tag“.
-- 4. `entry_media.day_note_id`: ein Anhang am Tag hängt an einer Notiz (P99: „der Anhang am
--    Notizfeld“); `subject_id` und `day` bleiben daneben für die Tagesabfragen.
-- 5. Bestand: je Profil ein Tag „Tagebuch“, jede bisherige Notiz mit Text bekommt ihn (die
--    eine Notiz je Tag war das Tagebuch). Anhänge am Tag kommen an die Notiz des Tags — gibt
--    es keine, entsteht eine ohne Text. Leere Notizen ohne Anhänge werden weich gelöscht.

-- 1. day_note ohne UNIQUE
CREATE TABLE day_note_neu (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    date              TEXT NOT NULL,
    text              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);
INSERT INTO day_note_neu (
    id, subject_id, date, text, created_at, updated_at, revision, origin_device_id, deleted_at
)
SELECT id, subject_id, date, text, created_at, updated_at, revision, origin_device_id, deleted_at
FROM day_note;
DROP TABLE day_note;
ALTER TABLE day_note_neu RENAME TO day_note;
CREATE INDEX idx_day_note_tag ON day_note(subject_id, date) WHERE deleted_at IS NULL;

-- 2. Tags je Profil
CREATE TABLE note_tag (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    name              TEXT NOT NULL,
    sort              INTEGER NOT NULL DEFAULT 0,
    fest              INTEGER NOT NULL DEFAULT 0,
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);
CREATE UNIQUE INDEX idx_note_tag_name ON note_tag(subject_id, name) WHERE deleted_at IS NULL;

-- 3. Notiz ↔ Tag
CREATE TABLE day_note_tag (
    note_id  TEXT NOT NULL REFERENCES day_note(id) ON DELETE CASCADE,
    tag_id   TEXT NOT NULL REFERENCES note_tag(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

-- 4. Anhang an der Notiz
ALTER TABLE entry_media ADD COLUMN day_note_id TEXT REFERENCES day_note(id);
CREATE INDEX idx_entry_media_notiz ON entry_media(day_note_id) WHERE day_note_id IS NOT NULL;

-- 5. Bestand
INSERT INTO note_tag (id, subject_id, name, sort, fest, active, created_at, updated_at)
SELECT lower(hex(randomblob(16))), id, 'Tagebuch', 0, 1, 1,
       strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'), strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
FROM subject;

INSERT INTO day_note_tag (note_id, tag_id)
SELECT n.id, t.id
FROM day_note n JOIN note_tag t ON t.subject_id = n.subject_id AND t.fest = 1
WHERE n.deleted_at IS NULL AND n.text != '';

-- Anhänge am Tag ohne Notiz an dem Tag: eine Notiz ohne Text, angelegt wie der erste Anhang
INSERT INTO day_note (id, subject_id, date, text, created_at, updated_at)
SELECT lower(hex(randomblob(16))), m.subject_id, m.day, '', MIN(m.recorded_at), MIN(m.recorded_at)
FROM entry_media m
WHERE m.day IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM day_note n
      WHERE n.subject_id = m.subject_id AND n.date = m.day AND n.deleted_at IS NULL
  )
GROUP BY m.subject_id, m.day;

UPDATE entry_media SET day_note_id = (
    SELECT n.id FROM day_note n
    WHERE n.subject_id = entry_media.subject_id AND n.date = entry_media.day
      AND n.deleted_at IS NULL
    ORDER BY n.created_at, n.rowid LIMIT 1
)
WHERE day IS NOT NULL;

-- Leer und ohne Anhang: weg (bisher stand `text = ''` für „entfernt“)
UPDATE day_note SET deleted_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
WHERE deleted_at IS NULL AND text = ''
  AND id NOT IN (SELECT day_note_id FROM entry_media WHERE day_note_id IS NOT NULL);
