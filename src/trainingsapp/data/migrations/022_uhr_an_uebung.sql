-- Die Uhr an der Übung (Ben, 18.10.2026; docs/plan_stoppuhr.md): „die Uhr kann mit dem
-- neuen System separat ein/abgeschalten werden. Ist die Uhr ein, hat man automatisch Zeit
-- mit dabei, auch ohne Chips/Kachel“.
--
-- `exercise.clock_on`: Stoppuhr und Timer stehen in der Übung bereit (1, Vorgabe) — aus (0)
--   etwa beim Dehnen ohne Zeit. Die Planübung kann abweichen (`plan_item.timer_json`, `uhr`).
-- `exercise.clock_counts_as`: „Zählt als“ — wohin die Zeit von Uhr und Timer kommt, wenn
--   die Übung Haltezeit anbietet: `hold` (Haltezeit, ein Satz je Lauf) oder `duration`
--   (Zeit); leer = Haltezeit. Ohne Haltezeit immer Zeit, auch ohne den Parameter Zeit.
--   Reist im Paket als `uhr` und `zaehlt_als` (docs/uebungspakete.md).
ALTER TABLE exercise ADD COLUMN clock_on INTEGER NOT NULL DEFAULT 1;
ALTER TABLE exercise ADD COLUMN clock_counts_as TEXT NOT NULL DEFAULT '';
