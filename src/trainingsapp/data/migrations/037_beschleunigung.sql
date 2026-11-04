-- Beschleunigungssensor in Übungen: Wiederholungen zählen, Atmung erfassen (Ben, 4.11.2026;
-- docs/plan_beschleunigung.md §3.3, §5.2, §5.3).
--
-- 1. `exercise.acc_json`: die Karte „Beschleunigungssensor“ der Übung,
--    `core.zaehlen.SensorWahl.als_dict` (`wiederholungen`, `atmung`, `vorlage`, `feld`) — nur,
--    was von der Vorgabe abweicht. `{}` = Wiederholungen an, wenn die Übung ein Feld der Art
--    `reps` hat; Atmung an bei Typ „Atmung“; Bewegung „Automatisch“; zählt ins erste
--    Wiederholungsfeld. Reist im Paket als `beschleunigung` (docs/uebungspakete.md).
-- 2. `einheit_baustein.art` erlaubt zusätzlich 'zaehlen': Der Zähl-Dienst ist ein Teil der
--    Einheit wie HRV, Timer und GPS (`devices/zaehlen.py`). Den CHECK aus Migration 018 ändert
--    SQLite nur über einen Neubau der Tabelle, wie in Migration 029. Auf `einheit_baustein`
--    verweist keine andere Tabelle, darum geht er auch mit foreign_keys=ON in der Transaktion
--    der Migration. Die Zeilen bleiben, wie sie sind — samt `rowid`, denn die Beteiligungen
--    einer Einheit werden nach `von_s, rowid` gelesen (`data/einheiten.py`).
ALTER TABLE exercise ADD COLUMN acc_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE einheit_baustein_neu (
    id          TEXT PRIMARY KEY,
    einheit_id  TEXT NOT NULL REFERENCES einheit(id) ON DELETE CASCADE,
    art         TEXT NOT NULL CHECK (art IN ('hrv', 'timer', 'gps', 'plan', 'zaehlen')),
    rolle       TEXT NOT NULL CHECK (rolle IN ('mitstarten', 'laeuft_schon')),
    datei       TEXT NOT NULL DEFAULT '',
    versatz_s   REAL,
    von_s       REAL NOT NULL DEFAULT 0,
    bis_s       REAL,
    daten_json  TEXT NOT NULL DEFAULT '{}'
);
INSERT INTO einheit_baustein_neu (
    rowid, id, einheit_id, art, rolle, datei, versatz_s, von_s, bis_s, daten_json
)
SELECT rowid, id, einheit_id, art, rolle, datei, versatz_s, von_s, bis_s, daten_json
FROM einheit_baustein;
DROP TABLE einheit_baustein;
ALTER TABLE einheit_baustein_neu RENAME TO einheit_baustein;
CREATE INDEX idx_einheit_baustein ON einheit_baustein(einheit_id);
CREATE INDEX idx_einheit_datei ON einheit_baustein(art, datei) WHERE datei != '';
