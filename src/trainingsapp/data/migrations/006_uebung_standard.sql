-- Standard einer Übung für Pläne
--
-- Nimmt ein Plan eine Übung auf, übernimmt die Planübung den Standard der
-- Übung: Ziel (`default_target_json`, seit 001), Eingabestufe (hier neu) und
-- Chips (in `result_spec_json` je Feld). Danach sind beide unabhängig — eine
-- Änderung im Plan wandert nur per Knopf („Als Standard der Übung setzen")
-- zurück, und umgekehrt („Standard der Übung übernehmen"). Siehe
-- `core/standards.py`.
ALTER TABLE exercise ADD COLUMN default_input_mode TEXT NOT NULL DEFAULT 'chips'
    CHECK (default_input_mode IN ('haken', 'chips', 'frei'));
