-- Timer zuordnen statt kopieren (Ben, 10.11.2026; docs/plan_timer_zuordnen.md §4).
-- `timer`: die Timer-Bibliothek — vorher die Einstellung `timer_profile` (JSON-Liste, gerätelokal).
--   Die Zeilen ziehen beim ersten Lesen um (`TimerRepo.alle`), ihre IDs bleiben. Übung
--   (`exercise.timer_json`), Plan (`plan.timer_json`) und Planübung (`plan_item.timer_json`,
--   Schlüssel `eigen`) dürfen statt einer eingebetteten Kopie auf eine Zeile verweisen:
--   {"ref": "<id>"}. Keine Zuordnungstabelle — wo ein Timer gilt, rechnet die App aus den
--   Verweisen (`core.uebung_timer.stellen`). Sync-Felder wie überall.
CREATE TABLE timer (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    -- das Profil (`core.timer.TimerProfil.als_dict`)
    json             TEXT NOT NULL,
    -- Reihenfolge in der Bibliothek
    position         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    revision         INTEGER NOT NULL DEFAULT 0,
    origin_device_id TEXT,
    external_ref     TEXT,
    deleted_at       TEXT
);
