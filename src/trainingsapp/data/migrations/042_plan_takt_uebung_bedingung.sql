-- Uhrenplan K3 (Ben, 8.11.2026; docs/plan_uhren.md §4.6, P105, P107).
-- `plan.takt_json`: „Takt für alle Übungen“ — `core.takt.Takt.als_dict`, NULL = keiner. Gilt
--   wie der Plan-Timer eine Stufe über der Übung: Uhr für jetzt > Timer-Abschnitt > Planübung
--   > Plan > Übung (`core.uebung_timer.takt_der_uebung`).
-- `exercise.bedingung_json`: „Weiter, wenn …“ an der Übung — `core.bedingung.Bedingung.als_dict`
--   ohne Zweig und Verweise; NULL = keine. Die Planübung folgt ihr (`plan_item.bedingung_json`
--   leer) und setzt nur Zweig, „erfüllt →“ und „nicht erfüllt →“ dazu, oder überschreibt sie
--   (`core.bedingung.wirksame`).
-- „Zeit zählt“ je Planübung (P104) liegt als Schlüssel `zaehlt` im Timer-JSON der Planübung
--   (`core.uebung_timer.TimerWahl`), ohne neue Spalte.
ALTER TABLE plan ADD COLUMN takt_json TEXT;
ALTER TABLE exercise ADD COLUMN bedingung_json TEXT;
