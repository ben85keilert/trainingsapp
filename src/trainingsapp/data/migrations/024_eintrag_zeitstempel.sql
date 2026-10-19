-- Zeitstempel je Eintragszeile (Ben, 19.10.2026: offener Eintrag, docs/plan_eintraege_hrv.md).
--
-- Jede Korrektur ist eine eigene Zeile (`replaces_entry_id`); `created_at` sagt, wann sie
-- entstand. Daraus liest die App, wann an einem offenen Eintrag zuletzt etwas geschah —
-- liegt das länger als der Zeitabstand zurück, gilt er als geschlossen (`core.eintraege`).
-- Alte Zeilen bekommen das Ende, sonst den Anfang des Eintrags.
ALTER TABLE session_entry ADD COLUMN created_at TEXT;
UPDATE session_entry SET created_at = COALESCE(ended_at, started_at) WHERE created_at IS NULL;
