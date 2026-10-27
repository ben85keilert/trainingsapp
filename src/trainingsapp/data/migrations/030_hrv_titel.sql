-- Gespeicherte Überschriften der HRV-Messungen je Profil (Ben, 26.10.2026: „Die
-- Überschrift ist maßgeblich, um Orientierung zu geben, was der Sinn der Daten ist. Dazu
-- brauche ich die Möglichkeit, Überschriften abzuspeichern und damit vorzudefinieren und
-- auffindbar wieder abzurufen.“). Bisher kamen die Vorschläge im Titel-Blatt nur aus den
-- letzten fünf vergebenen Titeln (`HrvRepo.letzte_titel`) — als Chips, die bei zehn
-- Überschriften zur Wolke würden.
--
-- Jede vergebene Überschrift landet hier (`HrvRepo.titel_merken`), auch eine, die man vor
-- der ersten Messung anlegt. Löschen geht im Titel-Blatt (✕ rechts) und unter
-- Einstellungen → HRV-Messung → Überschriften; `pinned` hält eine Überschrift oben. Die
-- Messungen behalten ihren Titel — er steht in der Messdatei (raw-v1) und als Kopie in
-- `hrv_recording.title`, nie hier.
CREATE TABLE hrv_title (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT NOT NULL REFERENCES subject(id),
    name          TEXT NOT NULL,
    pinned        INTEGER NOT NULL DEFAULT 0,
    last_used_at  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT '',
    UNIQUE (subject_id, name)
);
CREATE INDEX idx_hrv_title_profil ON hrv_title(subject_id, pinned, last_used_at);

-- Was schon vergeben wurde, steht von Anfang an in der Liste — mit der jüngsten Messung
-- als „zuletzt verwendet“. Die Kennung ist hier zufällig (kein UUIDv7 in SQL), das stört
-- nicht: Sie reist nirgends hin.
INSERT INTO hrv_title (id, subject_id, name, last_used_at, created_at)
SELECT lower(hex(randomblob(16))), subject_id, TRIM(title), MAX(started_at), MAX(started_at)
FROM hrv_recording
WHERE TRIM(title) != '' AND deleted_at IS NULL
GROUP BY subject_id, TRIM(title);
