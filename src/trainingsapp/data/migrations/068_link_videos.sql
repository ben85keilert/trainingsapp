-- Videos hinter Links, auf dem Gerät gespeichert (Ben, 17.11.2026, docs/plan_rueckweg_handy.md
-- Stufe 7: „Videos speichern wäre gut, dafür ein Button (Download) und das wird in den Anhängen
-- entsprechend angezeigt, um Platz machen zu können … Dabei dürfen keine Leichen von alten
-- Dateien entstehen, falls Medien herausgenommen werden“).
--
-- Die Datei liegt in der Paketablage wie eine Paketdatei (`medien/<sha256>.<endung>`, Name =
-- Prüfsumme dessen, was geladen wurde). Eine Zeile je Adresse; nennt nichts in der Datenbank
-- die Adresse mehr (Übung, Planübung, Kapitel, Block, Paketstand), räumt `Paketablage.aufraeumen`
-- Zeile und Datei weg — nach jedem Import und beim Start.
CREATE TABLE link_download (
    url        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    bytes      INTEGER NOT NULL,
    loaded_at  TEXT NOT NULL
);
