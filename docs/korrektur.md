# Automatische Korrektur — umgezogen nach hrv-core

Die Regeln der automatischen Artefaktkorrektur und die Messungen dahinter stehen
seit dem 16.10.2026 in `hrv-core/docs/korrektur.md` (Schwesterrepo `../hrv-core`).
Der Grundsatz bleibt: **lieber eine Lücke als ein falscher Wert.** Wer eine
Vorgabe (`hrv_core/regeln.py`, `hrv_core/constants.py`) ändert, belegt es dort
und ergänzt einen Golden-Test.

In der App: Die Vorgaben der `Korrekturregeln` gelten als Automatikmodus; ein
Expertenmodus mit sichtbaren Schwellen ist als Zuschaltung geplant
(`docs/offene_fragen.md`, A7). Die Einstellungen liegen in
`core/hrv_einstellungen.py`, die Oberfläche in `ui/views/einstellungen_hrv.py`
und `ui/components/korrektur_blatt.py`.
