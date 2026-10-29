-- Herzfrequenz-Auswertung je Aufzeichnung als Cache (Ben, 29.10.2026, Stufe 2;
-- hrv-research KONZEPT_HF_APP.md §7.2, Frage 4).
--
-- Die Datei bleibt die Wahrheit: alles hier ist aus Messdatei, Sidecar und Profil
-- nachrechenbar (`core/hf_auswertung.py`). `algo_version` ist die der Rechenvorschrift
-- (hrv_core), `profil_stand_json` das Profil, mit dem gerechnet wurde (Ruhe-HF, HFmax,
-- Grenzen). Weicht das heutige Profil ab, zeigt die Auswertung die **damaligen** Werte und
-- bietet das Nachrechnen an; gespeichert wird nur nach Rückfrage. Wochenlast, Testreihen
-- und der Forschungsexport lesen von hier.
CREATE TABLE hf_cache (
    recording_id TEXT PRIMARY KEY REFERENCES hrv_recording(id),
    algo_version INTEGER NOT NULL,
    profil_stand_json TEXT NOT NULL,
    werte_json TEXT NOT NULL,
    computed_at TEXT NOT NULL
);
