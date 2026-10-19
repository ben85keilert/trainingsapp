-- Indizes für die Eintragsabfragen (Befund D5, Durchsicht 19.10.2026).
--
-- `_GUELTIGE` (repositories.py) schließt jeden Eintrag aus, den ein anderer per
-- `replaces_entry_id` ersetzt hat — eine korrelierte Unterabfrage je Kandidatenzeile.
-- Ohne Index auf `replaces_entry_id` war das ein Vollscan über `session_entry` pro
-- Zeile (O(n²)); jedes „+Satz“ legt eine Korrekturzeile an, die Tabelle wächst also
-- schnell. `measurement.session_entry_id` wird bei jeder Korrektur gelöscht und neu
-- geschrieben — ebenfalls ohne Index ein Tabellenscan.
CREATE INDEX IF NOT EXISTS idx_session_entry_replaces ON session_entry(replaces_entry_id);
CREATE INDEX IF NOT EXISTS idx_measurement_entry ON measurement(session_entry_id);
