-- Einheit: HRV, GPS, Timer und Plan gemeinsam (Ben, 17.10.2026; docs/plan_einheit.md)
--
-- Eine Einheit klammert, was zusammen lief. Ihre **Zeitleiste** ist die Provenienz
-- für „wann habe ich was gemacht“: unveränderliche Zeilen, sofort geschrieben —
-- ein Absturz verliert höchstens den letzten Takt. HRV-Rohdaten stehen weiter nur in
-- den Messdateien (die Datei ist die Wahrheit), Ortungen nur unter Strecken/.
--
-- `einheit`: `started_at` ist der Nullpunkt (t_s = 0, UTC); `ended_at` NULL heißt
--   „läuft“ — oder, beim nächsten Start der App, abgebrochen.
-- `einheit_baustein`: welcher Teil dabei war und wie seine Zeit auf die Achse der
--   Einheit kommt (`versatz_s`: Zeit des Teils + versatz_s = t_s). Verknüpft über den
--   **Dateipfad**, nicht über eine ID: Die Zeile `hrv_recording` entsteht erst beim
--   Stopp und ist unveränderlich, der Dateiname steht schon beim Aufnahmestart fest —
--   und eine HRV-Aufnahme kann über mehrere Einheiten laufen (N:M).
-- `einheit_ereignis`: was wann geschah, `t_s` Sekunden seit `started_at`, `nr`
--   fortlaufend je Einheit. `daten_json` nur ortsfrei (`core.einheit.DATEN_SCHLUESSEL`).
--
-- Synchronisation ist für Edition B vorgesehen (`origin_device_id`, `deleted_at`),
-- Ereignisse sind unveränderlich und damit konfliktfrei. **Nie mitgeschickt**: die
-- `datei` einer GPS-Beteiligung (Regel 0, docs/plan_gps.md §0).
CREATE TABLE einheit (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    titel             TEXT NOT NULL DEFAULT '',
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    session_id        TEXT REFERENCES session(id) ON DELETE SET NULL,
    origin_device_id  TEXT,
    deleted_at        TEXT
);
CREATE INDEX idx_einheit_zeit ON einheit(subject_id, started_at DESC);

CREATE TABLE einheit_baustein (
    id          TEXT PRIMARY KEY,
    einheit_id  TEXT NOT NULL REFERENCES einheit(id) ON DELETE CASCADE,
    art         TEXT NOT NULL CHECK (art IN ('hrv', 'timer', 'gps', 'plan')),
    rolle       TEXT NOT NULL CHECK (rolle IN ('mitstarten', 'laeuft_schon')),
    datei       TEXT NOT NULL DEFAULT '',
    versatz_s   REAL,
    von_s       REAL NOT NULL DEFAULT 0,
    bis_s       REAL,
    daten_json  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_einheit_baustein ON einheit_baustein(einheit_id);
CREATE INDEX idx_einheit_datei ON einheit_baustein(art, datei) WHERE datei != '';

CREATE TABLE einheit_ereignis (
    id          TEXT PRIMARY KEY,
    einheit_id  TEXT NOT NULL REFERENCES einheit(id) ON DELETE CASCADE,
    nr          INTEGER NOT NULL,
    t_s         REAL NOT NULL,
    quelle      TEXT NOT NULL,
    art         TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    daten_json  TEXT NOT NULL DEFAULT '{}',
    UNIQUE (einheit_id, nr)
);
CREATE INDEX idx_einheit_ereignis ON einheit_ereignis(einheit_id, t_s);
