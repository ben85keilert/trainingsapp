-- Gerätelokale Einstellungen.
--
-- Schlüssel/Wert-Paare, die nur dieses Gerät betreffen und deshalb NICHT
-- synchronisiert werden: das zuletzt aktive Profil, Anzeigeeinstellungen,
-- später die Geräte-Zuordnung. Alles, was zum Datenbestand gehört, hat eine
-- eigene Tabelle — hier liegt nur, was beim Wechsel des Geräts wertlos wäre.
--
-- Werte sind Text. Wer eine Zahl braucht, wandelt beim Lesen um; für eine
-- Handvoll Einträge lohnt kein Typsystem.
CREATE TABLE app_setting (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
