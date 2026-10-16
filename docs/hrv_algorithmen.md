# HRV-Algorithmen — umgezogen nach hrv-core

Seit dem 16.10.2026 liegt die HRV-Mathematik in der gemeinsamen Bibliothek
**hrv-core** (Schwesterrepo `../hrv-core`, github `ben85keilert/hrv-core`), die
praxis_gui und trainingsapp teilen. Formeln, Konstanten und Fallstricke stehen dort:

- `hrv-core/docs/hrv_algorithmen.md` — Zeit-, Frequenzbereich (Lomb-Scargle, Welch),
  nichtlineare Maße (DFA α1, SampEn), Atmung, Bandpolitik, langer Weg
- `hrv-core/docs/korrektur.md` — automatische Artefaktkorrektur
- `hrv-core/docs/VERGLEICH.md`, `VERGLEICH_ZAHLEN.md` — Abweichungen zu praxis_gui
  und der Zahlenvergleich beim Umzug

Änderungen an der Rechenvorschrift gehören nach hrv-core, mit Golden-Test
(`hrv-core/tests/golden/`) und `ALGO_VERSION` in `hrv_core/constants.py`. Der
Kennzahlen-Cache der App (`hrv_metrics_cache.algo_version`) gilt bei einer
Änderung als veraltet und wird aus den Messdateien neu gerechnet.

Was in der App bleibt: `core/hrv_training.py` (HRV je Kilometer, DFA-Überblick
ohne Empfehlung — `docs/plan_gps.md`, Abschnitt 6) und `core/hrv_export.py`
(ZIP-Export, Diagnoseprotokoll — `docs/kompatibilitaet.md`).
