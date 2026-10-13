# Golden-Daten

Referenzdateien für die Kompatibilitätstests.

## `sensor_2026-05-23_125422.json`

Eine **anonymisierte** Kopie einer echten Aufzeichnung aus
`praxis_gui/Data/RR/`. Sie ist die Referenz dafür, dass unser
`raw-v1`-Leser und -Schreiber genau das Format trifft, das die Praxissoftware
erwartet — ein selbst erfundenes Beispiel würde nur unsere eigenen Annahmen
bestätigen.

**Entfernt wurden:** `patient_id`, `behandlung_id`, `notiz`, `ereignisse`.
Die RR-Werte sind unverändert; ohne Zuordnung sind sie kein personenbezogenes
Datum.

> **Regel für dieses Verzeichnis:** Hier landen ausschließlich anonymisierte
> Daten. Eine Messdatei mit Patientenkennung gehört niemals in ein
> Git-Repository — auch nicht in ein privates. Siehe `docs/recht/40_toms.md`.

Die `.gitignore` sperrt `sensor_*.json` generell und lässt nur dieses
Verzeichnis zu. Das ist Absicht: Der Normalfall ist „nicht committen".

## `sensor_2026-10-13_000000.json`

**Synthetisch**, ohne Personenbezug: aufgebaut wie eine Verity-Sense-Aufnahme
(`ppg_ppi`, mit `ppi_pakete`) aus 300 Intervallen `850 + 50·sin(2π·i/10)` ms,
fünf je Paket, Ankunft mit 2 s Latenz und 0–0,3 s Streuung. Geschrieben mit
`hrv_core.aufnahme.Aufnahme` und `devices.pmd.ppi_messwerte`, wie in der App.

- Vom Sensor verworfen (Blocker): Intervalle 3–5, 40, 100–119 (zugleich eine
  Messlücke von ~17 s), 200–201 — 26 von 300.
- Fehlerschätzung 10 ms, nur Intervall 150 und 151: 120 ms (ohne Blocker).

Sollwerte (`tests/test_ppi_naehte.py`, dort unabhängig aus `ppi_pakete`
nachgerechnet): RMSSD **21,7432 ms** über 269 echte Nachbardifferenzen;
über die verworfenen Intervalle hinweg wären es 22,9058 ms (ALGO_VERSION 1).
Ein echter Verity-Datensatz fehlt noch — er braucht eine anonymisierte Kopie.

Seit ALGO_VERSION 4 werden die verworfenen Intervalle standardmäßig wieder
aufgenommen und selbst geprüft (`tests/test_korrektur_regeln.py`): Die
Automatik schlägt nur 150/151 (Fehlerschätzung) zur Interpolation vor; RMSSD
**21,8946 ms** über alle 299 Nachbardifferenzen. Dem Sensor folgend bleiben es
21,7432 ms.

## `sensor_synth_ruhe_sitzend_11.json`, `sensor_synth_kohaerente_atmung_7.json`

**Synthetisch**, ohne Personenbezug, erzeugt am 2026-10-13 mit
`praxis_gui/tools/generate_hrv_dataset.py -s ruhe_sitzend -m 6 --seed 11` bzw.
`-s kohaerente_atmung -m 6 --seed 7`: je 6 min H10-artige RR-Reihe ohne Lücken.
Die Wahrheitsdateien (`truth-v1`) liegen nicht im Repo; ihre Bandleistungen
stehen in `tests/test_frequenz.py` (Ruhe: LF 832,3 / HF 285,7 ms²;
Kohärenzatmung 6/min: LF 4718,9 / HF 65,5 ms², Gipfel bei 0,1 Hz).

Sollwerte für Frequenzbereich, DFA α1 und SampEn hat praxis_gui auf denselben
Dateien gerechnet (scipy 1.18.1, neurokit2 0.2.12) — `tests/test_frequenz.py`,
`tests/test_nichtlinear.py`.
