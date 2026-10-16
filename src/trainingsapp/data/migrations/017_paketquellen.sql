-- Paketmanager, zweite Stufe (Ben, 16.10.2026; docs/uebungspakete.md):
--
-- `package.disabled_at`: deaktiviert — Übungen und Kurse des Pakets verschwinden
--   aus Katalog, Suche, Tags, Kursliste und Planansichten, die Daten bleiben
--   (anders als Entfernen); Aktivieren stellt alles her. Für die Arbeit an
--   Inhalten am Rechner (TRAININGSAPP_PAKETE) und zum Aufräumen der Ansicht.
-- `package.update_mode`: 'auto' (Vorgabe) oder 'manuell' — ob ein Update aus einer
--   Paketquelle beim Start eingespielt oder nur vorgemerkt wird.
-- `package.source_url`, `available_*`, `checked_at`: woher das Paket zuletzt kam und
--   welcher Stand in der Quelle liegt (Version, Datei, Prüfsumme, Neuigkeiten).
-- `exercise.package_dropped_at`, `course.package_dropped_at`: beim Update nicht mehr
--   im Paket. Nichts wird gelöscht — die Person entscheidet im Dialog: als eigene
--   Übung übernehmen (gleiche ID, Verlauf und Pläne bleiben) oder löschen.
ALTER TABLE package ADD COLUMN disabled_at TEXT;
ALTER TABLE package ADD COLUMN update_mode TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE package ADD COLUMN source_url TEXT;
ALTER TABLE package ADD COLUMN available_version INTEGER;
ALTER TABLE package ADD COLUMN available_url TEXT;
ALTER TABLE package ADD COLUMN available_sha256 TEXT;
ALTER TABLE package ADD COLUMN available_news TEXT;
ALTER TABLE package ADD COLUMN checked_at TEXT;
ALTER TABLE exercise ADD COLUMN package_dropped_at TEXT;
ALTER TABLE course ADD COLUMN package_dropped_at TEXT;
