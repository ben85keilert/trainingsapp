-- Material mit Rollen (Ben, 12.11.2026, P200, core/material.py).
--
-- Je Stück an einer Übung: wozu es dient (`rolle`: '' = Erklärung, 'begleitung' = läuft beim
-- Üben mit), ob eine Erklärung beim ersten Mal von selbst gezeigt wird (`zeigen`) und welches
-- andere Stück es ersetzt (`ersetzt` = dessen Adresse, aus einer Ergänzung). Planübungen und
-- Kurskapitel tragen dasselbe in ihrem `media_json`.
--
-- `media_seen`: was ein Profil als gesehen abgehakt hat — nach der Adresse des Stücks (die
-- IDs der Medien wechseln mit jedem Speichern und jedem Paket-Update). Gerätelokal: nie in
-- Paket, Export oder Sync.

ALTER TABLE exercise_media ADD COLUMN rolle TEXT NOT NULL DEFAULT '';
ALTER TABLE exercise_media ADD COLUMN zeigen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE exercise_media ADD COLUMN ersetzt TEXT NOT NULL DEFAULT '';

CREATE TABLE media_seen (
    subject_id TEXT NOT NULL,
    uri        TEXT NOT NULL,
    seen_at    TEXT NOT NULL,
    PRIMARY KEY (subject_id, uri)
);

-- Kurskapitel als Folge von Blöcken (Ben, 12.11.2026, core/kursbloecke.py): Text, Medium,
-- Frage, Test, Auswahl — JSON-Liste; '[]' = Text und Medien des Kapitels wie bisher.
ALTER TABLE course_chapter ADD COLUMN blocks_json TEXT NOT NULL DEFAULT '[]';

-- Vorschlag nach der Belastung (Ben, 12.11.2026, core/anpassung.py): die Regel, nach der ein
-- Workout nach dem Durchlauf ein anderes Ziel vorschlägt — NULL = keine. Kommt aus dem Kurs
-- oder Paket; geändert wird nie von selbst, nur auf Tipp.
ALTER TABLE plan ADD COLUMN anpassung_json TEXT;
