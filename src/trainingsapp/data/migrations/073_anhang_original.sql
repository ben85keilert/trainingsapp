-- Das Original zu einem verkleinerten Anhang (Ben, 19.11.2026: „Videos/Fotos sollen überall
-- komprimiert und gecroppt werden können“; Frage g in `docs/plan_medien_einheitlich.md` §4:
-- das Original eines Fotos oder Videos am Eintrag behalten, mit „Original löschen“).
--
-- `uri` nennt nach dem Verkleinern die Kopie, `original` die Datei von vorher (relativ zum
-- Ordner der Anhänge wie `uri`). Ihr Frontbild liegt daneben (`…_bild.jpg`). NULL: nichts
-- verkleinert, oder das Original ist gelöscht. Anhänge verlassen das Gerät nie — das gilt
-- für das Original genauso.
ALTER TABLE entry_media ADD COLUMN original TEXT;
