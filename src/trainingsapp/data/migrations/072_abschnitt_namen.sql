-- Gemerkte Namen für Abschnitte je Profil (Ben, 19.11.2026: „das Setzen eines neuen
-- Abschnittes mit ‚+‘ braucht ein besseres Namensmenü. Die vielen Vorschläge als Buttons
-- sind viel zu viel. Am besten einfach gemerkte Ausdrücke, die vorgeschlagen werden beim
-- Tippen. Dabei sollen wenige als Buttons gesetzt werden können, das werden dann so 4–5
-- Buttons. Der Rest ist gemerkt als Lesezeichen, also Favoritenfunktion“). Bisher zeigten
-- „Abschnitt: Start“ und das Blatt „Abschnitt“ alle Überschriften der Messungen
-- (`hrv_title`, Migration 030) als Knöpfe; Abschnittsnamen selbst wurden nicht gemerkt.
-- Ben wählte eine eigene Liste, getrennt von den Überschriften, und für beide dasselbe
-- Verhalten wie im Titel-Blatt („Nimm das alte Muster für beide“): eine Liste zum Antippen,
-- Tippen filtert, `pinned` hält einen Namen oben (angeheftet wird in den Einstellungen).
--
-- Jeder vergebene Name kommt hierher (`HrvRepo.abschnittname_merken`, nur der Name der
-- Gruppe: „Radfahren“, nicht „Radfahren (5 km)“). Die Messungen behalten ihre Abschnitte —
-- die stehen in den Notizen der Messdatei, nie hier.
CREATE TABLE hrv_section_name (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT NOT NULL REFERENCES subject(id),
    name          TEXT NOT NULL,
    pinned        INTEGER NOT NULL DEFAULT 0,
    last_used_at  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT '',
    UNIQUE (subject_id, name)
);
CREATE INDEX idx_hrv_section_name_profil ON hrv_section_name(subject_id, pinned, last_used_at);

-- Was bisher vorgeschlagen wurde (die gespeicherten Überschriften), bleibt beim Tippen
-- auffindbar — als gemerkter Name, nicht angeheftet, noch nie als Abschnitt vergeben.
INSERT INTO hrv_section_name (id, subject_id, name, created_at)
SELECT lower(hex(randomblob(16))), subject_id, name, created_at
FROM hrv_title;
