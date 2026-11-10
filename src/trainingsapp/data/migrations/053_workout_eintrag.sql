-- Workout-Eintrag (Ben, 10.11.2026; docs/plan_workout_eintrag.md).
-- Ein Durchlauf eines Workouts ist eine Einheit (Migration 018) — sie trägt den Verlauf in ihrer
-- Zeitleiste. `workout_entry` hält, was die Person zum Workout als Ganzem einträgt: zuerst die
-- Anstrengung (sRPE, 0–10) und eine Notiz. Gebaut wie `session_entry`: Ergebnis plus Kopie der
-- Felder, mit der es erfasst wurde; unveränderlich — eine Korrektur ist eine neue Zeile mit
-- `replaces_id`, es gilt die jüngste. Die Werte der Übungen bleiben in `session_entry`.
CREATE TABLE workout_entry (
    id                 TEXT PRIMARY KEY,
    einheit_id         TEXT NOT NULL REFERENCES einheit(id) ON DELETE CASCADE,
    result_json        TEXT NOT NULL DEFAULT '{}',
    spec_snapshot_json TEXT NOT NULL DEFAULT '{}',
    note               TEXT NOT NULL DEFAULT '',
    replaces_id        TEXT REFERENCES workout_entry(id) ON DELETE SET NULL,
    created_at         TEXT NOT NULL,
    origin_device_id   TEXT
);
CREATE INDEX idx_workout_entry_einheit ON workout_entry(einheit_id, created_at);
