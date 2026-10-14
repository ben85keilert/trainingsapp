-- Titel einer HRV-Aufzeichnung (Ben, 14.10.2026)
--
-- Eine Messung hat drei Arten Notiz — wie in praxis_gui: Überschrift (`titel`),
-- Beschreibung (`notiz`) und die Notizen mit Zeitstempel (`ereignisse`). Die
-- Datei bleibt die Wahrheit; die Zeile hält eine Kopie des Titels (wie `note`
-- die der Beschreibung), damit die Liste keine Messdateien lesen muss.
ALTER TABLE hrv_recording ADD COLUMN title TEXT NOT NULL DEFAULT '';
