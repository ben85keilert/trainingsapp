-- Typen und Regionen selbst verwalten (Ben, 14.10.2026): Einstellungen →
-- Typen und Regionen. Dort legt man neue an (sie stehen oben in der Liste)
-- und löscht, was man nicht braucht — gelöschte verschwinden auch aus den
-- Übungen. Später bringen importierte Übungspakete fehlende Tags mit.
--
-- `sort`: neue Tags bekommen den höchsten Wert und stehen oben; was es schon
-- gibt, steht danach alphabetisch.
ALTER TABLE tag ADD COLUMN sort INTEGER NOT NULL DEFAULT 0;

-- Die bisherigen Vorschläge werden echte Tags, damit man sie löschen kann
-- (ohne „Kung-Fu“ — das kommt später mit einem Übungspaket). Was es unter
-- dem Namen schon gibt, bleibt, wie es ist.
INSERT OR IGNORE INTO tag (id, name, kind) VALUES
    (lower(hex(randomblob(16))), 'Dehnung', 'typ'),
    (lower(hex(randomblob(16))), 'Kräftigung', 'typ'),
    (lower(hex(randomblob(16))), 'Ausdauer', 'typ'),
    (lower(hex(randomblob(16))), 'Gleichgewicht', 'typ'),
    (lower(hex(randomblob(16))), 'Atmung', 'typ'),
    (lower(hex(randomblob(16))), 'Benchmark', 'typ'),
    (lower(hex(randomblob(16))), 'Messung', 'typ'),
    (lower(hex(randomblob(16))), 'Nacken', 'region'),
    (lower(hex(randomblob(16))), 'Schulter', 'region'),
    (lower(hex(randomblob(16))), 'Arm', 'region'),
    (lower(hex(randomblob(16))), 'Hand', 'region'),
    (lower(hex(randomblob(16))), 'Rumpf', 'region'),
    (lower(hex(randomblob(16))), 'Rücken', 'region'),
    (lower(hex(randomblob(16))), 'Hüfte', 'region'),
    (lower(hex(randomblob(16))), 'Bein', 'region'),
    (lower(hex(randomblob(16))), 'Fuß', 'region');
