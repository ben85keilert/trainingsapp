-- Herzfrequenz (Ben, 29.10.2026; hrv-research docs/KONZEPT_HF_APP.md, Entscheidungen 10–17).
--
-- subject.geschlecht: 'w' | 'm' | 'd' | NULL — nur für Formelwahl (Gulati) und
-- TRIMP-Gewichte; ohne Angabe oder bei 'd' gelten die Männer-Koeffizienten.
--
-- profil_wert: Ruhe-HF, HFmax, Schwellen — **jeder Wert mit Herkunft** (quelle, datum,
-- unsicherheit, geraet, Messung). Zeilen sind unveränderlich wie session_entry: eine
-- Korrektur ist eine neue Zeile mit replaces_id; gültig ist, was nicht gelöscht ist und
-- keine lebende Zeile ersetzt. `fest` = von der Person festgesetzt (schlägt jede Quelle,
-- Wertehierarchie in hrv_core.herzfrequenz). `herkunft_json`: aus welchen Messungen und
-- Fenstern eine Automatik den Wert nahm (Frage 5: „woraus entstanden“).
--
-- rechen_ausnahme: ein Tag, eine Einheit, eine Messung oder eine Strecke, die „nicht
-- mitgerechnet“ wird (Baseline, Median, Feldmaximum) — per langem Drücken gesetzt.
--
-- day_field.fest: feste Tagesfelder der App (Ruhepuls, Gewicht, Blutdruck, Anstrengung,
-- Störung): nicht löschbar, nur ausschaltbar; gekoppelt mit der HF-Messung, wo nötig.
-- Bisher gelöschte Standardfelder kommen ausgeschaltet zurück (ihre mitgelöschten Werte
-- bleiben gelöscht).
ALTER TABLE subject ADD COLUMN geschlecht TEXT;

CREATE TABLE profil_wert (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subject(id),
    groesse TEXT NOT NULL,
    wert REAL NOT NULL,
    einheit TEXT NOT NULL DEFAULT 'bpm',
    quelle TEXT NOT NULL,
    unsicherheit REAL,
    datum TEXT NOT NULL,
    fest INTEGER NOT NULL DEFAULT 0,
    geraet TEXT,
    hrv_recording_id TEXT,
    herkunft_json TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    replaces_id TEXT REFERENCES profil_wert(id),
    origin_device_id TEXT,
    deleted_at TEXT
);
CREATE INDEX idx_profil_wert ON profil_wert(subject_id, groesse);

CREATE TABLE rechen_ausnahme (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subject(id),
    ziel TEXT NOT NULL,
    ziel_id TEXT NOT NULL,
    grund TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE UNIQUE INDEX idx_rechen_ausnahme ON rechen_ausnahme(subject_id, ziel, ziel_id)
    WHERE deleted_at IS NULL;

ALTER TABLE day_field ADD COLUMN fest INTEGER NOT NULL DEFAULT 0;
UPDATE day_field SET active = 0 WHERE standard_key IS NOT NULL AND deleted_at IS NOT NULL;
UPDATE day_field SET fest = 1, deleted_at = NULL WHERE standard_key IS NOT NULL;
