-- Zwei Arten von Tags: Typ (Kräftigung, Dehnung, Kung-Fu, …) und Region
-- (Nacken, Schulter, …). Beide optional, beliebig viele je Übung — eine
-- HRV-Messung hat einen Typ, aber keine Region.
--
-- Ein Name gehört genau einer Art an (`tag.name` bleibt UNIQUE). Bisherige
-- Tags waren Regionen; was keine Region ist („Entspannung", „HRV", …) und die
-- bisherige `exercise.category` stellt `data/upgrade.py` (Schritt 4) auf Typ um.
-- `exercise.category` bleibt als Spalte: der erste Typ, für Altbestand und
-- einfache Abfragen.
ALTER TABLE tag ADD COLUMN kind TEXT NOT NULL DEFAULT 'region';
