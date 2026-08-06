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

## Was noch fehlt

Für die HRV-Kennzahlen in L09 brauchen wir Sollwerte. Die liefert
`praxis_gui/tools/generate_hrv_dataset.py --corpus`: 15 synthetische Szenarien
mit Wahrheitsdatei (`truth-v1`), also bekannten LF-, HF-, RMSSD- und
SDNN-Werten. Synthetisch erzeugt, damit ohne jeden Personenbezug.
