-- Timer an Übung, Planübung und Plan (Ben, 17.10.2026; docs/plan_einheit.md, Stufe 3)
--
-- `exercise.timer_json`: die Timer-Profile der Übung (Liste von `TimerProfil.als_dict`,
--   Einzeltimer oder Folge Vorbereitung–Training–Cooldown). Reist im Paket als Feld
--   `timer` (docs/uebungspakete.md). Leer: Hat die Übung eine Timer-Regel im
--   `limit_spec` (Paket „Standard“), gilt sie als Einzeltimer (`core/uebung_timer.py`).
-- `plan.timer_json`: „Timer für alle Übungen“ — ein Profil oder NULL.
-- `plan.auto_next`: Nach dem Timer einer Übung automatisch zur nächsten (1) oder auf
--   einen Tipp warten (0, Vorgabe).
-- `plan_item.timer_json`: die Wahl der Planübung (`core/uebung_timer.TimerWahl`) — ein
--   Profil der Übung (per ID) oder eine eigene Kopie, dazu das gemerkte Zeitfeld und ob
--   die Zeit eingetragen wird. Leer: Vorrang Plan-Timer > erstes Profil der Übung.
ALTER TABLE exercise ADD COLUMN timer_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE plan ADD COLUMN timer_json TEXT;
ALTER TABLE plan ADD COLUMN auto_next INTEGER NOT NULL DEFAULT 0;
ALTER TABLE plan_item ADD COLUMN timer_json TEXT NOT NULL DEFAULT '{}';
