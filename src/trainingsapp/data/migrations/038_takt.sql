-- Taktgeber (Ben, 5.11.2026; docs/plan_taktgeber.md §2): `exercise.takt_json` ist der Takt der
-- Übung — `core.takt.Takt.als_dict` (`name`, `phasen[]` mit `name`, `dauer_s`, `art`, `klang`,
-- dazu `tempo`, `runden`, `animation`, `zaehlt`). `{}` = kein Takt (keine Phase). Reist im
-- Paket als `takt` (docs/uebungspakete.md). Ein Takt je Timer-Abschnitt liegt in `timer_json`
-- (`abschnitte[].takt`), nicht hier.
ALTER TABLE exercise ADD COLUMN takt_json TEXT NOT NULL DEFAULT '{}';
