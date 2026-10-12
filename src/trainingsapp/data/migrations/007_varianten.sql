-- Varianten: mehrere Übungen, eine Kachel im Verlauf
--
-- Wandsitz 90° und Wandsitz 45°, Liegestütz eng und weit: eigene Übungen mit
-- eigener Notation, im Verlauf aber eine Kachel, deren Mengen sich addieren
-- und deren Varianten einzeln ausgewiesen werden. `family_id` zeigt auf das
-- Original (die Übung, deren Kachel es ist); NULL heißt „eigene Kachel".
--
-- Eine Kopie ist zunächst immer Variante ihres Originals. Wer sie getrennt
-- führen will (Liegestütz einarmig), macht sie im Editor eigenständig.
ALTER TABLE exercise ADD COLUMN family_id TEXT REFERENCES exercise(id);
CREATE INDEX idx_exercise_familie ON exercise(family_id) WHERE family_id IS NOT NULL;
