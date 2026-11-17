-- Variablen eines Kurses (Ben, 16.11.2026: „Testwert wird als Variable gespeichert und kann
-- irgendwo verwendet werden im Kurs/Planbau“ · „Die Übung hat erstmal ihren eigenen Wert. Wenn
-- man eine Übung macht, kann man diesen Wert weitergeben und übernehmen“;
-- docs/plan_kurs_ablauf.md §15.1).
--
-- Ein Test im Kurs **hinterlässt einen Wert**. Bisher las der Kurs ihn jedes Mal neu aus dem
-- jüngsten Eintrag der Übung — wer nach dem Test gewöhnlich weiterübte, hatte einen anderen
-- „Test“ (Katalog P214 a). Jetzt steht er hier:
--
-- `name`:     der Schlüssel des Tests — seine Block-ID, bei „die gewählte“ `<block>:<übung>`
--             (`core.kursbloecke.wert_schluessel`). So nennt ihn auch, wer ihn verwendet
--             (`ziel_aus` eines Bausteins, in jedem Kapitel des Kurses).
-- `value`:    der Wert im Feld des Tests, ohne Faktor — den rechnet, wer ihn verwendet.
-- `entry_id`: der Eintrag, aus dem er stammt (der Testlauf) — NULL, wenn es ihn nicht mehr gibt.
-- `set_at`:   wann er gesetzt wurde; „Nochmal“ überschreibt ihn.
--
-- Gesetzt wird er vom Testlauf („Eintragen“) und, für Tests ohne Lauf, beim Abschließen des
-- Kapitels aus dem jüngsten Eintrag der Übung (bis dahin gilt deren eigener Wert). „Von vorn
-- beginnen“ löscht die Variablen des Kurses.
--
-- Gerätelokal wie `course_progress`: je Profil, nicht in Paket, Export oder Sync.
CREATE TABLE course_variable (
    subject_id  TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    course_id   TEXT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    value       REAL NOT NULL,
    entry_id    TEXT REFERENCES session_entry(id) ON DELETE SET NULL,
    set_at      TEXT NOT NULL,
    PRIMARY KEY (subject_id, course_id, name)
);
