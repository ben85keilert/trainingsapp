-- Durchsicht 11.11.2026 (Review der Datenschicht): „Welcher Tagebucheintrag kam aus welcher Einheit?“ (Heute, Plan, Leistungen-Blatt) suchte
-- den Eintrag im JSON jeder person/-Zeile. Ein Ausdrucksindex auf genau diesen Ausdruck —
-- die Abfragen in `data/einheiten.py` müssen ihn wörtlich so schreiben.
CREATE INDEX IF NOT EXISTS idx_einheit_ereignis_eintrag
    ON einheit_ereignis(json_extract(daten_json, '$.eintrag'))
    WHERE json_extract(daten_json, '$.eintrag') IS NOT NULL;
