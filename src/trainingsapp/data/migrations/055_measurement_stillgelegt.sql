-- Tabelle `measurement` stillgelegt (Ben, 11.11.2026; Durchsicht 10.11.2026, D26).
-- Sie hielt je Eintrag die Kennzahlen (`chart_metrics`: Summe, Maximum), wurde bei jedem
-- Eintrag und jeder Korrektur gelöscht und neu geschrieben — und nirgends gelesen: Verlauf und
-- Kurven rechnen aus `session_entry` (`core.verlauf`). Ab jetzt schreibt niemand mehr hinein.
-- Die Tabelle bleibt (Migrationen sind additiv, Migration 001 gehört zum Schema), ihre Zeilen
-- gehen: Sie wären sonst ein veralteter zweiter Stand neben den Einträgen.
DELETE FROM measurement;
