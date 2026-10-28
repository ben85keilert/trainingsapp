-- Pläne in Paketen und Datei-Links als Paketquelle (Ben, 28.10.2026,
-- docs/plan_import_links_plaene.md).
--
-- plan.package_id / package_key: der Plan kam aus einem Paket (je Profil angelegt, die ID
-- ist UUIDv5 aus Paket, Schlüssel und Profil). package_standard_json: der Stand aus dem
-- Paket — nur ein unveränderter Plan bekommt beim Update den neuen Stand.
-- package.plans_json: die Pläne des Pakets (zuletzt importiert) — damit ein später
-- aktives Profil sie nachbekommt und „Wieder installieren“ ohne Datei auskommt.
-- package.source_kind: 'index' (Paketquelle, ihr Index) oder 'datei' (ein direkter Link
-- auf die Paketdatei, beim Start auf eine neuere Version geprüft).
ALTER TABLE plan ADD COLUMN package_id TEXT;
ALTER TABLE plan ADD COLUMN package_key TEXT;
ALTER TABLE plan ADD COLUMN package_standard_json TEXT;
CREATE INDEX idx_plan_paket ON plan(package_id) WHERE package_id IS NOT NULL;
ALTER TABLE package ADD COLUMN plans_json TEXT;
ALTER TABLE package ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'index';
