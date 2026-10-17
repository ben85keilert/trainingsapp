-- Strecke ↔ Einheit (Ben, 17.10.2026; docs/plan_einheit.md, Stufe 2)
--
-- Ein Ausdauertraining läuft als Einheit. Über `einheit_id` findet die Auswertung die
-- HRV-Aufnahme auch dann, wenn sie schon vor dem Training lief und danach weiterlief —
-- `hrv_recording_id` bleibt dann leer, denn die Zeile der Aufnahme entsteht erst beim
-- Stopp. Die Versätze der Einheit (`einheit_baustein.versatz_s`) legen Ortungen und
-- Herzschläge aufeinander, genauer als die Startzeiten (die Messdatei kennt nur ganze
-- Sekunden). Ein nach einem Absturz nachgetragenes Training findet seine Einheit über
-- die Streckendatei (H16).
--
-- Wie die ganze Tabelle: nie synchronisiert (Regel 0, docs/plan_gps.md §0).
ALTER TABLE strecke ADD COLUMN einheit_id TEXT REFERENCES einheit(id) ON DELETE SET NULL;
CREATE INDEX idx_strecke_einheit ON strecke(einheit_id) WHERE einheit_id IS NOT NULL;
