-- Ausgangsschema des Trainingsassistenten.
--
-- Grundsatz: Die HRV-Rohdaten liegen NICHT in dieser Datenbank, sondern als
-- raw-v1-JSON-Dateien (siehe docs/kompatibilitaet.md). Hier steht nur der
-- Verweis darauf plus ein Cache der abgeleiteten Kennzahlen. Das hält den
-- Export bei einem Dateikopiervorgang und macht Kompatibilität zu etwas, das
-- nicht kaputtgehen kann.
--
-- IDs sind UUIDv7 als TEXT: zeitsortiert, dadurch gute Index-Lokalität und
-- natürliche Sortierung ohne Zusatzspalte.
--
-- Die Synchronisationsfelder (origin_device_id, revision, deleted_at, outbox,
-- external_ref) existieren von Anfang an, obwohl Edition A sie nicht nutzt.
-- Sie später einzuführen wäre eine Migration über den gesamten Bestand.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Personen
-- ---------------------------------------------------------------------------
-- Auch Edition A braucht mehrere Profile: eine Familie teilt sich ein Gerät.
CREATE TABLE subject (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    birth_year        INTEGER,
    note              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);

-- ---------------------------------------------------------------------------
-- Übungen
-- ---------------------------------------------------------------------------
CREATE TABLE exercise (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    category           TEXT NOT NULL DEFAULT '',
    description        TEXT NOT NULL DEFAULT '',
    icon_key           TEXT,
    image_path         TEXT,
    is_builtin         INTEGER NOT NULL DEFAULT 0,
    -- Beschreibt die Eingabemaske (core/result_spec.py)
    result_spec_json   TEXT NOT NULL DEFAULT '{}',
    -- Beschreibt Timer, Zähler und Pulsregeln (core/limits.py)
    limit_spec_json    TEXT NOT NULL DEFAULT '{}',
    -- Vorgabe des Therapeuten bzw. Standardziel
    default_target_json TEXT NOT NULL DEFAULT '{}',
    archived           INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    revision           INTEGER NOT NULL DEFAULT 0,
    origin_device_id   TEXT,
    deleted_at         TEXT
);
CREATE INDEX idx_exercise_kategorie ON exercise(category) WHERE deleted_at IS NULL;
CREATE INDEX idx_exercise_name      ON exercise(name)     WHERE deleted_at IS NULL;

-- Unveränderliche Historie der Eingabespezifikation.
-- Wird gebraucht, weil alte Trainingseinträge sonst nach einer Änderung der
-- Übungsdefinition nicht mehr korrekt darstellbar wären.
CREATE TABLE exercise_spec_version (
    id                TEXT PRIMARY KEY,
    exercise_id       TEXT NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    version           INTEGER NOT NULL,
    result_spec_json  TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE (exercise_id, version)
);

CREATE TABLE exercise_media (
    id           TEXT PRIMARY KEY,
    exercise_id  TEXT NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('video', 'image')),
    -- 'url'   = online, wird bei Bedarf geladen und gecacht (Videos NICHT ins APK)
    -- 'asset' = mit der App ausgeliefert
    -- 'local' = vom Nutzer aufgenommen, app-privates Verzeichnis
    source       TEXT NOT NULL CHECK (source IN ('url', 'asset', 'local')),
    uri          TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    license      TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_exercise_media ON exercise_media(exercise_id);

CREATE TABLE tag (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE exercise_tag (
    exercise_id  TEXT NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    tag_id       TEXT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (exercise_id, tag_id)
);

-- ---------------------------------------------------------------------------
-- Trainingspläne — Grundlage für Edition B (Therapeut stellt zusammen)
-- ---------------------------------------------------------------------------
CREATE TABLE plan (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    subject_id        TEXT REFERENCES subject(id) ON DELETE SET NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);

CREATE TABLE plan_item (
    id           TEXT PRIMARY KEY,
    plan_id      TEXT NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
    exercise_id  TEXT NOT NULL REFERENCES exercise(id),
    sort_order   INTEGER NOT NULL DEFAULT 0,
    target_json  TEXT NOT NULL DEFAULT '{}',
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_plan_item ON plan_item(plan_id, sort_order);

-- ---------------------------------------------------------------------------
-- Training
-- ---------------------------------------------------------------------------
CREATE TABLE session (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    plan_id           TEXT REFERENCES plan(id) ON DELETE SET NULL,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    note              TEXT NOT NULL DEFAULT '',
    mood              INTEGER,
    origin_device_id  TEXT,
    deleted_at        TEXT
);
CREATE INDEX idx_session_zeit ON session(subject_id, started_at DESC);

-- Trainingseinträge sind UNVERÄNDERLICH.
-- Eine Korrektur entsteht als neuer Eintrag, der den alten über
-- `replaces_entry_id` ersetzt. Dadurch sind Synchronisationskonflikte in
-- Edition B strukturell unmöglich — es gibt nichts, was zwei Geräte
-- gleichzeitig ändern könnten.
CREATE TABLE session_entry (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    exercise_id         TEXT NOT NULL REFERENCES exercise(id),
    sort_order          INTEGER NOT NULL DEFAULT 0,
    result_json         TEXT NOT NULL DEFAULT '{}',
    -- Kopie der ResultSpec zum Zeitpunkt der Erfassung. Ohne sie ist ein alter
    -- Eintrag nach einer Änderung der Übung nicht mehr interpretierbar.
    spec_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    note                TEXT NOT NULL DEFAULT '',
    started_at          TEXT,
    ended_at            TEXT,
    replaces_entry_id   TEXT REFERENCES session_entry(id),
    origin_device_id    TEXT,
    deleted_at          TEXT
);
CREATE INDEX idx_entry_session  ON session_entry(session_id, sort_order);
CREATE INDEX idx_entry_exercise ON session_entry(exercise_id);

CREATE TABLE entry_media (
    id                TEXT PRIMARY KEY,
    session_entry_id  TEXT NOT NULL REFERENCES session_entry(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL CHECK (kind IN ('video', 'image')),
    uri               TEXT NOT NULL,
    recorded_at       TEXT NOT NULL
);
CREATE INDEX idx_entry_media ON entry_media(session_entry_id);

-- ---------------------------------------------------------------------------
-- Messwerte — speisen alle Verlaufsdiagramme
-- ---------------------------------------------------------------------------
-- Entspricht in praxis_gui `Dokumentation_Skalen_Werte`. Hier landen sowohl
-- Übungsergebnisse (über ResultSpec.chart_metrics) als auch Benchmarks
-- ("wie lange kann ich die Luft anhalten") und HRV-Kennzahlen.
CREATE TABLE measurement (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    metric_key        TEXT NOT NULL,
    value             REAL NOT NULL,
    unit              TEXT NOT NULL DEFAULT '',
    recorded_at       TEXT NOT NULL,
    session_id        TEXT REFERENCES session(id) ON DELETE CASCADE,
    session_entry_id  TEXT REFERENCES session_entry(id) ON DELETE CASCADE,
    source            TEXT NOT NULL DEFAULT 'manual'
                      CHECK (source IN ('manual', 'exercise', 'hrv', 'import')),
    origin_device_id  TEXT,
    deleted_at        TEXT
);
CREATE INDEX idx_measurement_verlauf ON measurement(subject_id, metric_key, recorded_at);

-- ---------------------------------------------------------------------------
-- Sensoren
-- ---------------------------------------------------------------------------
CREATE TABLE device (
    id                TEXT PRIMARY KEY,
    address           TEXT NOT NULL UNIQUE,   -- BLE-Adresse; unter macOS eine System-UUID
    name              TEXT NOT NULL DEFAULT '',
    geraet_profil     TEXT NOT NULL DEFAULT 'ble_generic',
    -- Ergebnis des Sensor-Prüfstands: liefert das Gerät wirklich RR-Intervalle?
    -- NULL = noch nicht geprüft.
    rr_bestaetigt     INTEGER,
    rr_pro_paket      REAL,
    datenqualitaet    TEXT NOT NULL DEFAULT 'bpm_only',
    geprueft_at       TEXT,
    last_seen         TEXT
);

-- ---------------------------------------------------------------------------
-- HRV
-- ---------------------------------------------------------------------------
-- Die DATEI ist die Wahrheit. Diese Zeile ist nur der Index darauf.
-- `sha1` erkennt, wenn die Datei nachträglich geändert wurde und der
-- Kennzahlen-Cache damit ungültig ist.
CREATE TABLE hrv_recording (
    id                 TEXT PRIMARY KEY,
    subject_id         TEXT NOT NULL REFERENCES subject(id),
    file_path          TEXT NOT NULL,
    sha1               TEXT NOT NULL DEFAULT '',
    device_id          TEXT REFERENCES device(id) ON DELETE SET NULL,
    geraet             TEXT NOT NULL DEFAULT '',
    geraet_profil      TEXT NOT NULL DEFAULT 'ble_generic',
    intervall_quelle   TEXT NOT NULL DEFAULT 'ekg_rr'
                       CHECK (intervall_quelle IN ('ekg_rr', 'ppg_ppi')),
    datenqualitaet     TEXT NOT NULL DEFAULT 'rr_ekg'
                       CHECK (datenqualitaet IN ('rr_ekg', 'ppi_optisch', 'bpm_only')),
    started_at         TEXT NOT NULL,
    duration_s         REAL NOT NULL DEFAULT 0,
    coverage_pct       REAL NOT NULL DEFAULT 100,
    n_gaps             INTEGER NOT NULL DEFAULT 0,
    session_id         TEXT REFERENCES session(id) ON DELETE SET NULL,
    session_entry_id   TEXT REFERENCES session_entry(id) ON DELETE SET NULL,
    note               TEXT NOT NULL DEFAULT '',
    origin_device_id   TEXT,
    deleted_at         TEXT
);
CREATE INDEX idx_hrv_zeit ON hrv_recording(subject_id, started_at DESC);

-- Reiner Cache. Jederzeit aus der Datei neu berechenbar.
-- Steigt ALGO_VERSION in hrv_core/constants.py, gelten alle Einträge mit
-- kleinerer Version als veraltet.
CREATE TABLE hrv_metrics_cache (
    id             TEXT PRIMARY KEY,
    recording_id   TEXT NOT NULL REFERENCES hrv_recording(id) ON DELETE CASCADE,
    scope          TEXT NOT NULL DEFAULT 'global',  -- 'global' | 'region:<id>'
    params_json    TEXT NOT NULL DEFAULT '{}',      -- Fensterbreite, PSD-Methode …
    metrics_json   TEXT NOT NULL DEFAULT '{}',
    algo_version   INTEGER NOT NULL,
    computed_at    TEXT NOT NULL,
    UNIQUE (recording_id, scope, params_json)
);

-- ---------------------------------------------------------------------------
-- Synchronisation (Edition B) — in Edition A vorhanden, aber ungenutzt
-- ---------------------------------------------------------------------------
-- Zuordnung unserer UUIDs zu den INTEGER-Schlüsseln von praxis_gui.
-- Ohne diese Tabelle ist kein Round-Trip möglich.
CREATE TABLE external_ref (
    entity         TEXT NOT NULL,
    local_id       TEXT NOT NULL,
    remote_system  TEXT NOT NULL,
    remote_id      TEXT NOT NULL,
    synced_at      TEXT,
    PRIMARY KEY (entity, local_id, remote_system)
);
CREATE INDEX idx_external_remote ON external_ref(remote_system, entity, remote_id);

-- Ausgangswarteschlange statt eines dirty-Flags: reihenfolgetreu, Wiederholung
-- ist trivial, und es braucht keinen Full-Table-Scan, um Ausstehendes zu finden.
CREATE TABLE outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity       TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    op           TEXT NOT NULL CHECK (op IN ('create', 'update', 'delete')),
    payload      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT
);
CREATE INDEX idx_outbox_reihenfolge ON outbox(id);

-- Grabsteine für gelöschte Datensätze.
--
-- ACHTUNG, Zielkonflikt: DSGVO Art. 17 verlangt echtes Löschen, die
-- Synchronisation verlangt eine Spur des Gelöschten. Auflösung: hier stehen
-- ausschließlich ID und Zeitstempel — NIEMALS Gesundheitsdaten.
CREATE TABLE tombstone (
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (entity, entity_id)
);

-- Einwilligungen (Edition B)
CREATE TABLE consent (
    id           TEXT PRIMARY KEY,
    subject_id   TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    scope        TEXT NOT NULL,   -- z. B. 'hrv', 'medien', 'nachrichten'
    granted      INTEGER NOT NULL DEFAULT 0,
    granted_at   TEXT,
    revoked_at   TEXT,
    text_version TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_consent_subject ON consent(subject_id);

-- ---------------------------------------------------------------------------
PRAGMA user_version = 1;
