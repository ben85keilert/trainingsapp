-- Ausdauertraining mit GPS (Ben, 14.10.2026; docs/plan_gps.md)
--
-- Die Ortungen liegen als Datei unter Strecken/ (nie unter Messungen/), hier
-- steht nur Ortsfreies: Sportart, Zeiten, Strecke, Höhenmeter und die
-- Verknüpfung zur HRV-Aufnahme und zum Tagebucheintrag. Ohne GPS (Laufband,
-- Halle) bleibt `file_path` leer.
--
-- **Wird nie synchronisiert** (Regel 0: GPS-Daten werden nicht geteilt) —
-- darum ohne outbox, external_ref und origin_device_id.
CREATE TABLE strecke (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    sportart          TEXT NOT NULL CHECK (sportart IN ('gehen', 'laufen', 'rad')),
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    file_path         TEXT NOT NULL DEFAULT '',
    distanz_m         REAL NOT NULL DEFAULT 0,
    dauer_s           REAL NOT NULL DEFAULT 0,
    bewegt_s          REAL NOT NULL DEFAULT 0,
    hoehe_auf_m       REAL NOT NULL DEFAULT 0,
    hoehe_ab_m        REAL NOT NULL DEFAULT 0,
    hrv_recording_id  TEXT REFERENCES hrv_recording(id) ON DELETE SET NULL,
    session_entry_id  TEXT REFERENCES session_entry(id) ON DELETE SET NULL,
    title             TEXT NOT NULL DEFAULT '',
    deleted_at        TEXT
);
CREATE INDEX idx_strecke_zeit ON strecke(subject_id, started_at DESC);
