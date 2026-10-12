-- Planübung: Wie wird eingegeben?
--
-- Die Übung legt fest, welche Felder es gibt und welche Chips Standard sind.
-- Der Plan wählt je Übung die Stufe:
--   'haken'  nur abhaken — ein Knopf „Gemacht"
--   'chips'  Vorauswahl — Chips der Übung, im Plan überschreibbar (quick_json)
--   'frei'   Freieingabe — Zahlenfeld
-- Der Eintrag selbst darf immer mehr (Stift → volles Formular).
ALTER TABLE plan_item ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'chips'
    CHECK (input_mode IN ('haken', 'chips', 'frei'));
ALTER TABLE plan_item ADD COLUMN quick_json TEXT NOT NULL DEFAULT '{}';
