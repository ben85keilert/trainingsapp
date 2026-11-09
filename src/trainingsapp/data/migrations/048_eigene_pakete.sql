-- Eigene Pakete in der App bauen (U4, Ben 9.11.2026, docs/plan_paketinhalte.md §7, F5: „Ja,
-- Übungen, Pläne und Kurse sollen exportiert werden können“).
--
-- Ein eigenes Paket ist ein Entwurf mit fester ID (die sehen alle, die es bekommen — jede neue
-- Fassung ist ein Update desselben Pakets), Kopf und Auswahl. Exportiert wird eine Datei
-- (JSON oder ZIP, `core.paketdatei.export_schreiben`); die App merkt sich Version und
-- Prüfsumme des Inhalts der letzten Fassung, um die nächste Version vorzuschlagen.

CREATE TABLE own_package (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    news            TEXT NOT NULL DEFAULT '',
    -- Version der letzten exportierten Fassung (X·10000 + Y·100 + Z), NULL = noch keine
    version         INTEGER,
    exercises_json  TEXT NOT NULL DEFAULT '[]',
    plans_json      TEXT NOT NULL DEFAULT '[]',
    courses_json    TEXT NOT NULL DEFAULT '[]',
    exported_sha    TEXT,
    exported_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);
