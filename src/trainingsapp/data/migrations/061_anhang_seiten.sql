-- Seitenzahl eines Dokuments (Ben, 13.11.2026, P206 (d): „offene Punkte aus P206 lösen“).
-- `entry_media.seiten`: wie viele Seiten ein in der App aufgenommenes Dokument hat — steht an
-- der Kachel und in der Ansicht. NULL bei allem anderen und bei gewählten PDF-Dateien (die
-- App liest fremde PDFs nicht).
ALTER TABLE entry_media ADD COLUMN seiten INTEGER;
