-- Wert für den Plan (Ben, 17.11.2026, W3: „Die Werteintragung kommt normal direkt nach einem
-- Test“ · „Wert wird genommen und kann ganz genommen werden – prozentual abgeändert – manuell
-- eingegeben (mit Klick und per Tastatur)“; docs/plan_kurs_ablauf.md §17).
--
-- Die Variable eines Tests (Migration 065) hält den **gemessenen** Wert (`value`). Dazu kommt
-- die Wahl der Person, wie er in den Plan geht:
--
-- `wie`:         leer = die Vorgabe des Kurses (er rechnet wie bisher: Testwert × Faktor) —
--                sonst `ganz`, `anteil` oder `hand` (`core.kursbloecke.Planwert`).
-- `plan_value`:  nur bei `hand`: die Zahl der Person, in der Einheit des Testfelds. Der Wert
--                für den Plan gilt statt Testwert × Faktor, überall, wo der Kurs sonst aus
--                diesem Test rechnet.
-- `anteil`:      nur bei `anteil`: der Anteil am Testwert (0,9 = 90 %).
-- `plan_set_at`: wann gewählt — der Stempel, an dem die Sammelkarte eine neue Wahl erkennt.
-- `floating`:    1 = die Zeile hält **nur die Wahl**: Der Wert des Tests schwebt noch — er
--                ist weiter der jüngste Eintrag der Übung. So bei einem Test ohne Lauf, dessen
--                Kapitel nicht abgeschlossen ist: Dort gibt es noch keine Variable, die Wahl
--                braucht aber einen Platz. `value` ist dann, was beim Wählen galt. Der
--                Abschluss des Kapitels hält den Wert fest (floating = 0), die Wahl bleibt.
--
-- „Ganz“ und „Anteil“ folgen dem Testwert, „von Hand“ bleibt die Zahl der Person. Ein neuer
-- Testlauf („Nochmal“) setzt die Wahl zurück — die Karte kommt gleich wieder. An den Plan
-- kommt die Zahl nur über „Plan anlegen“ bzw. die Sammelkarte, auf Tipp; der Eintrag des
-- Tests bleibt, wie er ist. Gerätelokal wie die Tabelle: nicht in Paket, Export oder Sync.
ALTER TABLE course_variable ADD COLUMN wie TEXT NOT NULL DEFAULT '';
ALTER TABLE course_variable ADD COLUMN plan_value REAL;
ALTER TABLE course_variable ADD COLUMN anteil REAL;
ALTER TABLE course_variable ADD COLUMN plan_set_at TEXT;
ALTER TABLE course_variable ADD COLUMN floating INTEGER NOT NULL DEFAULT 0;
