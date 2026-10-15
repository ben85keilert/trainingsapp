-- Kurse (Ben, 15.10.2026; docs/plan_kurse.md): Neben Übungen und Plänen eine
-- dritte Kategorie — Kapitel, die man von oben nach unten durcharbeitet.
-- Ein Kapitel hat Erklärtext (Markdown), Medien, Plan-Vorlagen und eine
-- Bedingung, die erfüllt sein muss, bevor das nächste Kapitel aufgeht
-- („100 Liegestützen, dann das nächste Video“). Überspringen geht je nach
-- Kurs frei, auf Rückfrage oder gar nicht (`unlock_mode`).
--
-- Kurse kommen wie Übungen über Pakete (`package_id`, Paketstand in
-- `package_standard_json`); NULL = eigener Kurs (Editor später).
-- Der Fortschritt ist je Profil (`course_progress`): wann ein Kapitel erreicht
-- und abgeschlossen wurde, und ob es übersprungen war. Er wird (noch) nicht
-- synchronisiert.
--
-- Pläne, die ein Kapitel anlegt, tragen `plan.course_chapter_id` — beim
-- Abschluss des Kapitels werden sie deaktiviert, nicht gelöscht: Einträge
-- bleiben, der Plan bleibt in der Planverwaltung wählbar.
CREATE TABLE course (
    id                     TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    unlock_mode            TEXT NOT NULL DEFAULT 'rueckfrage'
                           CHECK (unlock_mode IN ('frei', 'rueckfrage', 'streng')),
    package_id             TEXT REFERENCES package(id),
    package_standard_json  TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    revision               INTEGER NOT NULL DEFAULT 1,
    origin_device_id       TEXT,
    deleted_at             TEXT
);

CREATE TABLE course_chapter (
    id          TEXT PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    title       TEXT NOT NULL,
    body_md     TEXT NOT NULL DEFAULT '',
    -- Bedingung für den Abschluss (`core.kurse.Bedingung`): gelesen, summe, tage, messung
    gate_json   TEXT NOT NULL DEFAULT '{}',
    -- Plan-Vorlagen (`core.kurse.PlanVorlage`): beim Erreichen als echte Pläne angelegt
    plans_json  TEXT NOT NULL DEFAULT '[]',
    -- Medien wie `exercise_media`, zusätzlich `audio`; als JSON, weil Kapitel
    -- nur als Ganzes geschrieben werden (Paket, Editor)
    media_json  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX idx_course_chapter ON course_chapter(course_id, sort_order);

CREATE TABLE course_progress (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    course_id     TEXT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    chapter_id    TEXT NOT NULL REFERENCES course_chapter(id) ON DELETE CASCADE,
    reached_at    TEXT NOT NULL,
    completed_at  TEXT,
    skipped       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (subject_id, chapter_id)
);

ALTER TABLE plan ADD COLUMN course_chapter_id TEXT
    REFERENCES course_chapter(id) ON DELETE SET NULL;
