-- Tagesfelder: Art „Messwert“ mit bis zu drei Teilen (Blutdruck), einstellbarer
-- Tageswert und Standardfelder (Ben, 28.10.2026, docs/plan_tagesfelder_messwert.md).
--
-- `tageswert`: wie aus mehreren Einträgen eines Tages der eine Wert wird — '' = Vorgabe
-- der Art (Anzahl/Menge/Dauer: Summe, Skala/Messwert: Mittel), sonst
-- 'summe' | 'mittel' | 'max' | 'min' | 'letzter'. Eine Ansicht, keine Erfassung: Die
-- Spec-Kopie je Wert braucht sie nicht.
-- `standard_key`: das Feld stammt aus den Standardfeldern der App (etwa 'blutdruck').
-- Gelöscht bleibt gelöscht — der Start legt ein Standardfeld nur an, wenn es im Profil
-- keine Zeile mit diesem Schlüssel gibt; „Wiederherstellen“ holt die gelöschte zurück.
ALTER TABLE day_field ADD COLUMN tageswert TEXT NOT NULL DEFAULT '';
ALTER TABLE day_field ADD COLUMN standard_key TEXT;
CREATE INDEX idx_day_field_standard ON day_field(subject_id, standard_key)
    WHERE standard_key IS NOT NULL;
