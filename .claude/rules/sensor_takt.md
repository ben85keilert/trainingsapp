---
paths:
  - "**/*diagnose*"
  - "**/*mitschnitt*"
  - "**/*erkundung*"
  - "**/geraeteprobe.py"
  - "**/*zaehl*"
  - "**/*atem*"
  - "**/*takt*"
  - "**/*bewegungsbild*"
  - "**/*sensor*"
  - "**/marken_leiste.py"
  - "**/marken_stand.py"
  - "**/polar.py"
  - "**/pmd.py"
  - "**/messlauf.py"
  - "docs/plan_beschleunigung.md"
---

# Diagnosemodus, Beschleunigungssensor, Taktgeber

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

- **Diagnosemodus** (Ben, 4.11.2026, `docs/plan_diagnosemodus.md`, Vertrag §14): in den
  Einstellungen angeboten, je Messung gestartet (Sensorblatt mit Vorabtest), roter Punkt oben
  rechts im Overlay. Rohmitschnitt `mitschnitt-v1` aus hrv-core (`hrv_core.mitschnitt`) über
  `devices/mitschnitt.MitschnittTransport`, Beschleunigung in `PolarQuelle` (`acc=`,
  `stroeme_setzen`), Lebenszyklus im `Messlauf` (neben dem Backup, beim Speichern Beiwerk);
  **Marken** (Wdh/Atem/Störung, `core/diagnose.kontext_aus_notizen`) aus der Leiste im Overlay
  (`components/marken_leiste`, Tipp beim Aufsetzen) oder mit ⏯ an der Uhr (Seite „Diagnose“,
  Dart-Stempel) — **nie in den Notizen**, immer im Mitschnitt; nach dem Satz Marken · Sensor
  (Zähl-Teil, sonst `hrv_core.prototyp`; nur angezeigt) · Korrektur · eingetragen. Unbekannte Geräte: Geräteprobe ohne
  Messung (`devices/erkundung.py`, `/geraeteprobe`), nie schreiben, nie 0x2A25/0x2A23 lesen.
  Hinaus nur bereinigt (`hrv_core.deid.mitschnitt_zeilen`). In hochfrequenten Ereignissen
  immer `ohne_auto_update()` (V1).

- **Beschleunigungssensor in Übungen** (Ben, 4.11.2026, Vertrag `docs/plan_beschleunigung.md`):
  je Übung die Karte „Beschleunigungssensor“ (Wiederholungen, Atmung; `core/zaehlen.SensorWahl`,
  `exercise.acc_json`, Migration 037, Paketfeld `beschleunigung`). Hat das Gerät einen
  (`CAP_PMD_ACC`), ist **der Knopf die Messung** („Wdh. zählen“), **±1 nur ihre Korrektur** —
  ohne Sensor kein Knopf, kein Handzähler. Das Zählen ist der Einheit-Teil `zaehlen`
  (`devices/zaehlen.ZaehlBaustein`), **unabhängig von der Uhr** (mit der Uhr derselben Übung in
  einer Einheit), Strom erst ab dem Tipp, aus mit dem Ende (`Messlauf.acc_anfordern`/
  `acc_freigeben`). Ende: „Fertig“, Abhaken, Timer durch = eingetragen (`person/eintrag` mit
  `teil`, nie doppelt); Abbrechen, andere Übung, 60 s ohne Bewegung, Trennen = abgebrochen,
  nachtragbar unter „Läufe heute“; ein Wechsel der Ansicht beendet nichts. **Entweder zählt die
  Person oder der Sensor** (P122; beides nur im Diagnosemodus, A2). Im Alltag nur Ergebnisse
  (Zeitleiste `zaehlung`/`korrektur`/`zaehlen_ende`, `reps` im Eintrag), **nie Rohdaten der
  Beschleunigung** (P123). **Atmung** (A3, Ben 5.11.2026): dieselbe Einheit, die **Atem-Spur**
  neben den Sätzen (`hrv_core.prototyp.atemzuege.AtemLive`, Phasen ▲/▼ und Fenster ins Beiwerk
  `_atem.json` der laufenden Messung, Zeitleiste `zaehlung` mit `zaehlart` atem / `satz` 0) —
  sie läuft nebenbei (P133: Chips, Sätze, Anhalten berühren sie nicht), nur Atmung ±1 und
  `kein_atem`, **nie ins Tagebuch** (P120). **B1** (5.11.2026): die Auswertung zeigt das
  Beiwerk als Ebene „Atmung“ (Einatmen schattiert) und Karte „Atmung (Prototyp)“ mit dem
  Hinweis „Atmung < 9/min — liegt im LF-Band“ an HF-Power, LF/HF und DFA α1 (Startregel F6 in
  `core/atem_auswertung.py`, nichts gespeichert, keine Wertung), live liegt das Einatmen der
  letzten 60 s hinter den Kurven (`components/atem_live.py`), und die Messdatei bekommt das
  Protokollfeld `atmung` (`core/atem_protokoll.py`: Atemübung → `uebung`, keine Übung →
  `spontan`, sonst kein Feld; Vertrag §5). **B2** (5.11.2026, hrv-core 0.10.0): die Atem-HRV je
  Atemzug aus `hrv_core.prototyp.atem_hrv` — Atemspanne, **Phasenlage als Sekunden ab
  Einatembeginn** (P135), RR je Phase — rechnet `core/atem_auswertung.py` beim Anzeigen je
  Messung und Abschnitt (korrigierte Reihe, Wanduhr) und der `ZaehlBaustein` live („Spanne 58
  ms“, nur mit Aufnahme); Regel F6 nach P136 (Sensor ab 3 gültigen Fenstern und 25 %, sonst
  RR-Atmung im Modus aus dem Protokollfeld, `rr_modus`), nichts gespeichert. **A5** (5.11.2026,
  hrv-core 0.11.0): je Satz zählt der Live-Zähler `prototyp.wiederholungen.WdhLive` jede
  Wiederholung sofort, **Umkehrpunkt oben** (P143, `core.zaehlen.vorlage_waehlen` überschreibt
  den Katalogwert), halbe daneben, nie mitgezählt; Vorlagen in der Karte nur Automatisch ·
  Kniebeuge · Liegestütz (`VORLAGEN_ANGEBOT`), die Achsen eines anderen Geräts → Automatisch mit
  Grund; `zaehlen_fenster` nur noch als Rückfall im Diagnose-Vergleich ohne Zähl-Teil. **B2b**
  (5.11.2026, hrv-core 0.12.0, `ALGO_VERSION` bleibt 8): dieselbe Rate nach F6 geht an
  `frequenzbereich(atemrate_pro_min=)` — Kacheln „HF (Atemband)“/„LF/HF (Atemband)“, Tabelle und
  Bandleiste zeigen `hf_atem`/`lf_hf_atem` **neben** den festen Bändern (Fensterspektren über
  `core.atem_auswertung.mit_atemband`), kein Cache; die **Atemlage** (`hrv_core.atmung.atemlage`)
  steht unter DFA α1, und Schwellen aus α1 (`core/hf_auswertung`, `AUSWERTUNG_VERSION` 4) gelten
  nur bei spontaner Atmung ab 9/min oder unbekannter Lage — sonst Grund statt Schwelle.

- **Taktgeber** (Ben, 5.11.2026, Vertrag `docs/plan_taktgeber.md`; Teil 1 T1–T3 gebaut): ein
  **Takt** ist eine Folge von Phasen (Name, Sekunden, Art `ein`/`aus`/`halten`/`ab`/`auf`/`frei`,
  Klang) mit Tempo, als Schleife, solange die Uhr läuft. Die Rechnung lebt **nur** in `core/takt.py`
  (`Takt`, `lage` aus der Uhr — nie mitgezählt —, `wechsel`, `TaktLauf` für Tempo ohne Sprung,
  `VORLAGEN`, `animation_fuer`, `soll_phasen`); `ui/` zeichnet nur. Drei Orte, Vorrang Uhr „für
  jetzt“ (`AppState.uhr_takt`, `takt.AUS` = keiner) > Timer-Abschnitt (`Abschnitt.takt`) > Übung
  (`Exercise.takt`, Migration 038 `takt_json`, Paketfeld `takt`, Drei-Wege-Abgleich ein Feld) —
  `core.uebung_timer.takt_fuer`, am Lauf `TimerLauf.takt_aktuell`/`takt_lage`. Der Ticker
  (`ui/timer_takt.py`) spielt je neuer Phase ihren Klang (Vorgabe je Art, `KLANG_VORGABE`) und
  vibriert kurz (Einstellungen → Timer und Takt, Vorgabe an, P140 offen); `TimerBaustein` schreibt
  `timer/takt` am Abschnittsbeginn und je Tempoänderung (`plan_einheit` §4). Takt-Blatt
  (`components/takt_blatt.py`, `blatt_spalte`) mit Vorschau und Tempo-Regler; der Regler **im
  Lauf** (`TempoRegler`) ist `TimerLauf.tempo_setzen` — für jetzt (P139). Die Animation
  (`components/takt_anzeige.TaktAnzeige`, nach Phasenzahl: Puls, Kreis, Kreis mit Halten, Box,
  Balken, Welle) wird **einmal gebaut**, `nachziehen` setzt je Tick nur Werte, `animate_scale` mit
  der Phasendauer (V1). **Teil 2** (5.11.2026, 0.3.51, `docs/plan_taktgeber.md` §10): der
  `TaktVerfolger` (`devices/takt_lauf.py`) sagt je Tick der Einheit, was im Takt geschah
  (Takt-Lauf begann/endete, Soll-Phasen, volle Runden) — die Einheit bringt es **nicht über die
  Zeitleiste**, sondern direkt zur HRV (`Messlauf.atem_takt_beginn/phase/ende`: Feld `takt` im
  Beiwerk `atem-v1`, ein Paar Notizen `timer/takt` … `timer/ende` auf der Spur `atemtakt` ohne
  Abschnittsgrenze und ohne 5-s-Regel, Protokollfeld `atmung` `getaktet` mit der Rate des
  längsten Laufs — nur Atemtakte) und zum Zähl-Teil (`ZaehlBaustein.takt_runden`). Die
  Auswertung legt Soll über Ist (feine Linien, Versatz-Median je Atemzug, Phasenlage gegen Ist
  und Soll, `core/atem_auswertung.soll_ist_versatz`/`soll_atem`), die Takt-Rate ist für F6 die
  **dritte** Quelle (ein Soll ist keine Messung). **Takt zählt** (P138): `Takt.zaehlt`
  (Schalter im Blatt, Bewegungs-Vorlagen an) → `uebung_lauf.takt_zaehlen_anbringen` lässt mit
  der Uhr der Übung einen Zähl-Teil mit `quelle="takt"` antreten, auch **ohne Gerät**
  (`messlauf=None`, `_OhneGeraet`); jede volle Runde eine Wiederholung, Zählzeile „Takt 12“ (nie
  „Prototyp“), mit Sensor zählt der Sensor und der Takt steht daneben (`zaehlung` mit `quelle`,
  `takt`, `takt_zeiten_s`; nur der Sensor im Eintrag). Das **Bild der Bewegung** ist ein Medium
  der Übung (`core/bewegungsbild.py`, Ablage `Medien/Bewegung/`, `BewegungsbildRepo`, Weg
  `bewegung/<id>`), läuft als `ft.Image`-Schleife neben der Takt-Anzeige im „Während“ — nie in
  Paket, Export oder Sync. **Planübung folgt der Übung auch hier** (A6, 5.11.2026):
  `PlanItem.acc`/`PlanItem.takt` (Migration 039, NULL = wie die Übung, `takt_json = '{}'` =
  keiner), aufgelöst nur in `core.zaehlen.wirksame_wahl` und `core.uebung_timer.takt_der_uebung`
  (Uhr für jetzt > Abschnitt > Planübung > Übung) — „Im Plan einstellen“ hat Karte und Takt-Zeile
  mit ↺, den Knopf „Wdh. zählen“ nur mit Wiederholungsfeld; Paketfeld je Planübung.
