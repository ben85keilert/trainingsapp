-- Quellenbindung (Sicherheitsdurchsicht S3, Ben, 20.10.2026; docs/uebungspakete.md,
-- „Paketquellen“):
--
-- `package.source_url` hält ab jetzt die Adresse der Quelle (ihren Index), nicht mehr
-- die der Paketdatei. Ein Paket bekommt Updates nur noch aus der Quelle, die es zuletzt
-- lieferte; „Standard“ ohne Bindung nur aus der Vorgabequelle, andere Pakete ohne
-- Bindung (per Datei geholt) aus keiner. Die alten Werte (Dateiadresse, seit 16.10.2026)
-- passen zu keiner Quelle und verfallen samt Vormerkung — die nächste Prüfung bindet neu.
UPDATE package
SET source_url = NULL, available_version = NULL, available_url = NULL,
    available_sha256 = NULL, available_news = NULL
WHERE source_url IS NOT NULL;
