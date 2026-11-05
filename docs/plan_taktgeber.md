# Plan: Taktgeber — Phasen für Atmung und Bewegung in Uhr, Timer und Übung

Stand 5.11.2026: **angenommen**, Teil 1 (T1–T3) gebaut (Version 0.3.50, Abschnitt 9) (Ben: „So bauen“; Aufgabe A18, Ben 4.11.2026: „z. B. 3 min und dann Phasen setzen
können, diese optisch interessant gestalten … Animation/Visualisierung getakteter Übung mit
Geschwindigkeitsregler“; 5.11.2026: „Takt ist in der Uhr/Timer (beides). Dieser sollte doch direkt
(Uhr) oder über die Übung zugänglich sein? Evtl. Wiederholungszähler auch ohne Stoppuhr, aber mit
Phasen, auch mehr als 3. Entwirf ein gutes ausbaufähiges Konzept“; „Erstelle verschiedene
Animationen für 1–4 Phasen“). Verträge, die er berührt: `docs/plan_beschleunigung.md` §7.2/§7.6
(Soll-Phasen für die Atem-HRV), `docs/kompatibilitaet.md` §4 (Marke), §5 (`atmung` getaktet),
§15 (`atem-v1`), `docs/plan_einheit.md` §4/§7, `docs/plan_stoppuhr.md`, `docs/uebungspakete.md`.

## 0. Kurzfassung

Ein **Takt** ist eine Folge von **Phasen** mit Namen, Dauer und Klang — ein bis beliebig viele
(ein · halten · aus · halten; ab · halten · auf; ein Metronomschlag). Er hat ein **Tempo**
(Faktor, mit dem alle Dauern skalieren; der Geschwindigkeitsregler) und läuft als Schleife, solange
die Uhr läuft. Er hängt an drei Orten, die denselben Kern nutzen:

| Ort | Was | Gilt |
|---|---|---|
| **Übung** (`Exercise.takt`) | die Vorgabe der Übung („4-7-8-Atmung“, „Kniebeuge 2-1-2“) | überall, wo die Übung geübt wird; reist im Paket |
| **Timer-Abschnitt** (`Abschnitt.takt`) | ein Takt je Abschnitt eines Timer-Profils („3 min Atmen 4-6“, dann Pause ohne Takt) | in diesem Abschnitt; überschreibt die Vorgabe der Übung |
| **Uhr, für jetzt** (`AppState.uhr_takt`) | der Takt-Knopf neben der Uhr: Vorlage oder eigene Phasen, Tempo mit Regler | diese Sitzung, wie „zählt“ und der Einmal-Timer (P79) |

Die Anzeige ist eine **Animation nach Phasenzahl** (Kreis, Welle, Pendel, Balken) mit Farbe je
Phase, Restsekunden und Klang am Phasenwechsel. **Der Takt zählt** auf Wunsch: Jede volle Runde
ist eine Wiederholung — ein Zähler mit Phasen, auch ohne Sensor und ohne Stoppuhr-Zeit. In der
Messdatei steht der Takt als Protokoll (`atmung` getaktet), als eine Marke (`atemtakt`) und als
Soll-Phasen im Beiwerk `atem-v1`, damit die Auswertung Soll gegen Ist (Sensor) legen kann.

## 1. Begriffe

- **Phase:** Name (frei, Vorschläge „ein“, „halten“, „aus“, „ab“, „auf“), Dauer in Sekunden
  (auch Zehntel), Klang zu Beginn (aus `core.klang.KLAENGE`, leer = Vorgabe), **Art** als
  Kennung für die Auswertung: `ein`, `aus`, `halten`, `ab`, `auf`, `frei`. Die Art sagt, was die
  Phase bedeutet (Atmung oder Bewegung), der Name, was angezeigt wird.
- **Takt:** Liste von Phasen (mindestens eine), Name, Tempo (Faktor, Vorgabe 1,0), optional
  Rundenzahl (sonst endlos bis zum Ende des Abschnitts/der Uhr). Rundendauer = Summe der Dauern
  mal Tempo; „Rate pro Minute“ = 60 / Rundendauer (für Atmung die Atemfrequenz).
- **Vorlagen** (`core.takt.VORLAGEN`, feste Schlüssel): Atmung 4-6 (6/min), Box 4-4-4-4,
  4-7-8, Gleichtakt 5-5 (6/min), Gleichtakt 2,5-2,5 (12/min), Metronom 1 s, Kniebeuge 2-1-2
  (ab · halten · auf), Liegestütz 2-0-1 … Eigene Takte speichert die Person in der Bibliothek
  (`app_setting`, wie die Timer-Bibliothek) oder direkt an Übung/Abschnitt.
- **Taktlauf:** die Lage im Takt zu einem Zeitpunkt — Phase, Anteil in der Phase, Runde. Sie
  wird **aus der Uhr gerechnet**, nie mitgezählt: Zeit seit Beginn des Abschnitts (bzw. der
  Stoppuhr) modulo Rundendauer. Darum driftet nichts, und „Anhalten“ hält den Takt mit an.

## 2. Kern (ohne flet)

`core/takt.py`:

- `Phase(name, dauer_s, art="frei", klang="")`, `Takt(phasen, name="", tempo=1.0,
  runden=None)` mit `als_dict`/`aus_dict` (defensiv wie `TimerProfil`), `rundendauer_s`,
  `rate_pro_min`, `mit_tempo(faktor)`, `VORLAGEN`, `ist_atmung()` (nur Arten ein/aus/halten),
  `ist_bewegung()`.
- `lage(takt, t_s) -> Lage(phase_index, phase, anteil, runde, rest_s, t_runde_s)` — rein.
- `wechsel(alt: Lage, neu: Lage) -> list[Ereignis]` (Phasenwechsel, Rundenende) für Klang,
  Vibration, Zählung und Zeitleiste.
- `soll_phasen(takt, von_s, bis_s) -> list[(t_s, "ein"|"aus")]` für das Beiwerk `atem-v1`
  (nur Takte mit Atem-Arten; „halten“ verlängert die laufende Phase).
- Doctests; keine Bewertung, keine Empfehlung (ein Takt ist eine Vorgabe der Person, keine aus
  Messwerten — das Resonanzprotokoll, das eine Rate *wählt*, bleibt gesperrt wie in
  `docs/plan_beschleunigung.md` §10).

`core/timer.py`: `Abschnitt.takt: Takt | None` (im Dict nur, wenn gesetzt; `_abschnitte_lesen`
und `als_dict` nehmen ihn mit — Rundreisen in Kopie, Paketimport und Editor). `core/models.py`:
`Exercise.takt: Takt | None` (Migration 038 `exercise.takt_json TEXT NOT NULL DEFAULT '{}'`),
Paketfeld `takt` (`docs/uebungspakete.md`, Drei-Wege-Abgleich ein Feld, ältere Apps übergehen
es), `FELDNAMEN["takt"] = "Takt"`. `core/uebung_timer.takt_fuer(uebung, abschnitt, wahl)`:
Vorrang Uhr-für-jetzt > Abschnitt > Übung > keiner.

## 3. Lauf: Klang, Vibration, Zeitleiste

- `ui/timer_takt.py` (der 0,2-s-Ticker) rechnet je Tick die `Lage` aus dem `TimerLauf`
  (`stand.abschnitt_s − stand.rest_s`; bei der Stoppuhr die gelaufene Zeit) und spielt über
  `ton_spielen` den Klang der neuen Phase (Vorgabe: ein → Glocke hell, aus → Glocke tief, halten →
  Klangholz, ab/auf → Piep, frei → Klangschale), dazu eine kurze Vibration; der Abschnittsklang
  bleibt. Die Verzögerung von bis zu 200 ms ist hier schon bekannt (Timer-Signale).
- `devices/einheit.TimerBaustein` schreibt beim Start eines Abschnitts mit Takt ein Ereignis
  `timer/takt` (`name`, `wert` = Rate/min, `soll_s` = Rundendauer, `tempo`, `phasen_s`
  [Dauern], `arten` „ein/aus“ als Text) und bei einer Tempoänderung noch eins; Rundenenden
  nicht (zu viele). `core/einheit.ARTEN` += `takt`, `DATEN_SCHLUESSEL` += `tempo`, `phasen_s`,
  `arten`. Vertrag `docs/plan_einheit.md` §4 zuerst.
- Läuft eine Aufnahme, bekommt sie **eine Marke** `quelle=timer, art=takt, spur=atemtakt`
  (Felder, die `hrv_core.ereignisse.MARKE_FELDER` schon kennt: `name`, `wert`, `soll_s`,
  `profil`) am Beginn und am Ende des Takts — nie eine je Phase (`MIN_MARKE_S` = 5 s). Vertrag
  `docs/kompatibilitaet.md` §4 zuerst (neuer `art`-Wert `takt`, neue `spur` `atemtakt`).
- Das Protokollfeld `atmung` wird `getaktet` mit `takt_pro_min`, wenn ein Atemtakt lief
  (`core.atem_protokoll`: Takt-Ereignisse vor der Übungsregel). Mit Bewegungstakt bleibt es
  wie bisher.
- Die **Soll-Phasen** gehen ins Beiwerk `atem-v1` als neues, optionales Feld
  `takt: {"name", "rate_pro_min", "phasen": [[t_s, "ein"|"aus"], …]}` (Vertrag §15 und
  hrv-core `atem.py`/`deid` zuerst; ältere Leser übergehen es). So legt die Auswertung Soll
  gegen Ist (Sensor) und die Atem-HRV rechnet die Phasenlage gegen beides
  (`docs/plan_beschleunigung.md` §7.2, Entscheidung 25 Frage 7).

## 4. Der Takt zählt (Wiederholungszähler mit Phasen)

- Hat der Takt Bewegungs-Arten (ab/auf) oder ist „Takt zählt“ an, ist jede volle Runde eine
  Wiederholung. Das läuft als **Zähl-Teil mit Quelle `takt`** über denselben Weg wie der
  Sensor (`devices/zaehlen.ZaehlBaustein`, Zeitleiste `zaehlung` mit `quelle`-Feld `takt`,
  Satz je zählendem Abschnitt, ±1, Eintrag in den offenen Eintrag beim Ende) — die Zählzeile
  zeigt „Takt 12“ statt „Sensor 12“. Ohne Sensor ist das der Handzähler, den P118 verwarf, **nur
  mit Takt**: Die Zahl kommt aus der Vorgabe, nicht aus einer Messung, und die Zählzeile sagt
  das („Takt · 12“, kein „Prototyp“).
- Mit Sensor **und** Takt zählt der Sensor; der Takt steht daneben („Takt 12 · Sensor 11“) —
  beide in der Zeitleiste, nur der Sensor im Eintrag (entweder Person/Takt oder Sensor, P122
  sinngemäß). Im Diagnosemodus ist der Takt eine dritte Spalte im Vergleich nach dem Satz.
- Ohne Stoppuhr: „Takt starten“ an der Übung startet einen Einmal-Timer ohne Ablauf mit diesem
  Takt (es gibt also immer eine Uhr; sie zählt nur, wenn „zählt“ an ist).

## 5. Anzeige und Bedienung

**Takt-Knopf an der Uhr** (Zeile und Knöpfe, `components/uhr.py`): ein Metronom-Symbol neben
„zählt“; der Tipp öffnet das **Takt-Blatt** (`components/takt_blatt.py`, `blatt_spalte`):
Vorlagen als Chips, darunter die Phasen des gewählten Takts als Zeilen (Name, Sekunden, Art,
Klang), „+ Phase“, „Phase entfernen“, der **Tempo-Regler** (0,5×–2×, mit Rate/min und
Rundendauer als Text), Vorschau (die Animation läuft im Blatt), „Für jetzt“ / „In die Übung“ /
„In die Bibliothek“. Während die Uhr läuft, wirkt der Tempo-Regler sofort (die Lage springt
nicht: die gelaufene Rundenzeit bleibt, die Phase wird neu skaliert).

**Animation** (`components/takt_anzeige.py`), gewählt nach Phasenzahl, umschaltbar:

| Phasen | Vorgabe | Bewegung |
|---|---|---|
| 1 | **Puls**: ein Ring füllt sich über die Phase und blitzt am Schlag (Metronom) | – |
| 2 | **Kreis**: wächst beim Einatmen, schrumpft beim Ausatmen (ab/auf: sinkt und steigt ein Pendel) | `animate_scale` je Phase, kein Neubau |
| 3 | **Kreis mit Halten**: wächst, bleibt (leuchtender Rand, Restsekunden), schrumpft | – |
| 4 | **Box**: Kreis wächst, hält, schrumpft, hält; die vier Phasen als Rahmenseiten mit Lauflicht | – |
| ≥ 5 | **Balken**: die Phasen als Segmente nebeneinander, der laufende Abschnitt füllt sich | – |
| alle | **Welle**: eine Sinuslinie, der Punkt wandert; **Balken** als Alternative | wählbar |

Farbe je Art (ein = kühl, aus = warm, halten = neutral, ab/auf = Übungsfarbe), Name der Phase
und Restsekunden in der Mitte, Runde und Rate darunter. Die Flutter-Animation läuft nativ über
die ganze Phase (`animate_scale`/`animate` mit der Phasendauer, `EASE_IN_OUT`); der Ticker setzt
nur am Phasenwechsel neue Zielwerte und die Texte — keine Knöpfe werden neu gebaut (V1-Regel).
Die Anzeige steht im Timer („Während“), in der laufenden Uhr (klein, antippen → groß) und im
Live-Vollbild der Messung (neben Phase ▲/▼ des Sensors: Soll und Ist).

**Übung bearbeiten:** in „Uhr und Timer“ die Zeile „Takt: 4-7-8-Atmung · 4/min“ mit Stift
(öffnet das Takt-Blatt) und ✕; im Timer-Editor je Abschnitt dieselbe Zeile. Das (i) erklärt
Takt, Tempo und „Takt zählt“.

**GIFs und Bilder der Bewegung** (Ben: „gehen auf die Übung, nicht den Timer“): ein Medium der
Art `bild`/`gif` an der Übung (`core/models.Media`, Ablage wie die eigenen Symbole unter
`Medien/`), gezeigt neben der Takt-Anzeige im „Während“; es läuft als Schleife, nicht
synchron zum Takt (ein GIF hat sein eigenes Tempo). Später: eine Bildfolge je Phase (ein Bild
je Phase der Bewegung), die der Takt schaltet — das ist dann synchron.

## 6. Recht

Ein Takt ist eine Vorgabe, die die Person wählt; die App bewertet nichts und empfiehlt keine
Rate aus Messwerten (`docs/recht/00_zweckbestimmung.md`; das Resonanzprotokoll bleibt wie in
`docs/plan_beschleunigung.md` §10). Vorlagen sind feste Zahlen ohne Wirkversprechen.

## 7. Stufen

| Stufe | Inhalt | Umfang |
|---|---|---|
| **T1** | Kern `core/takt.py`, `Abschnitt.takt`, `Exercise.takt` (Migration 038, Paketfeld), Vorlagen, Bibliothek; Takt-Blatt und Zeilen in „Übung bearbeiten“ und im Timer-Editor; Vertrag `docs/uebungspakete.md` | M |
| **T2** | Lauf: Lage aus der Uhr, Klang und Vibration je Phase, Takt-Knopf an der Uhr „für jetzt“, Tempo-Regler live, „Takt starten“ ohne Timer; Zeitleiste `timer/takt` (Vertrag `plan_einheit` §4) | M |
| **T3** | Animationen 1–4+ Phasen (Puls, Kreis, Kreis mit Halten, Box, Balken, Welle), Übungsfarbe, in Timer, Uhr und Live-Vollbild | M |
| **T4** | Messung: Marke `atemtakt` (Vertrag §4), `atmung` getaktet, Soll-Phasen in `atem-v1` (Vertrag §15, hrv-core), Auswertung Soll gegen Ist, Phasenlage gegen Soll/Ist (Entscheidung 25 Frage 7) | M |
| **T5** | „Takt zählt“: Zähl-Teil mit Quelle `takt`, Zählzeile „Takt 12“, neben dem Sensor, Diagnose-Vergleich | M |
| **T6** | GIF/Bild der Bewegung an der Übung, Bildfolge je Phase | S |

## 8. Entschieden (Ben, 5.11.2026)

Konzept angenommen („So bauen“: T1–T6 hintereinander, dann Prüfrunde).

| # | Frage | Entscheidung |
|---|---|---|
| P138 | „Takt zählt“ trägt Wiederholungen ohne Sensor ins Tagebuch ein (jede Runde eine) — gewollt, obwohl die Zahl eine Vorgabe ist, keine Messung? | **ja**, gekennzeichnet „Takt“; mit Sensor zählt der Sensor |
| P139 | Tempo-Regler während des Laufs: sofort wirksam und nur „für jetzt“ (nicht gespeichert), oder speichert er in Übung/Abschnitt? | **für jetzt**; speichern nur über das Blatt |
| P140 | Vibration am Phasenwechsel zusätzlich zum Klang? | offen (nicht gefragt) — Vorschlag: ja, kurz, abschaltbar |
| P141 | Soll-Phasen ins Beiwerk `atem-v1` (Feld `takt`, Format-Erweiterung) oder nur die Marke `atemtakt` in der Messdatei? | **ins Beiwerk** (Format-Erweiterung `atem-v1`, Vertrag §15 zuerst) |

## 9. Umsetzungsstand (5.11.2026, Version 0.3.50) — Teil 1: T1–T3

hrv-core bleibt 0.13.0 (`hrv-core.ref` unverändert); Teil 1 braucht nichts aus der Bibliothek.
Die Vibration am Phasenwechsel ist **so gebaut, Vorgabe an** (P140 offen, Schalter unter
Einstellungen → Übungen).

| Stufe | Gebaut | Wo |
|---|---|---|
| T1 Kern | `core/takt.py` (flet-frei, Doctests): `Phase(name, dauer_s, art, klang)`, `ART_*`, `Takt(phasen, name, tempo, runden, animation, zaehlt)` — unveränderlich wie `SensorWahl`, `als_dict`/`aus_dict` defensiv (unbrauchbare Phasen fallen weg, Unbekanntes wird Vorgabe, nie eine Ausnahme), `rundendauer_s`, `rate_pro_min`, `mit_tempo` (Faktor 0,5–2, `tempo_lesen` begrenzt), `ist_atmung`, `ist_bewegung`, `kurztext` („4-7-8 · 3,2/min“); `AUS` = der leere Takt („für jetzt keiner“); `VORLAGEN` (acht feste Schlüssel; Liegestütz 2-0-1 als `liegestuetz_2_1`, eine Phase von 0 s gibt es nicht); `animation_fuer` (Puls 1, Kreis 2, Kreis mit Halten 3, Box 4, Balken ≥ 5; `Takt.animation` überschreibt, etwa Welle); `lage(takt, t_s)` rein aus der Uhr (mit `fertig` bei erreichter Rundenzahl), `wechsel(alt, neu)` → `TaktEreignis` (`phase`, `runde`, `ende`), `soll_phasen` (nur Atemtakte, „halten“ verlängert), `TaktLauf` (Tempoänderung ohne Sprung: gelaufene Runden samt Anteil bleiben), `takt_pruefen` fürs Werkzeug, Bibliothek `takte_lesen`/`takte_schreiben`/`in_bibliothek`, `takt_waehlen` (für jetzt > Abschnitt > Übung) | `core/takt.py` |
| T1 Modell | `Abschnitt.takt` (im Dict nur gesetzt; `_abschnitte_lesen` tolerant — Rundreise in Kopie, Paket und Editor), `Exercise.takt` (Migration 038 `exercise.takt_json TEXT NOT NULL DEFAULT '{}'`, `ExerciseRepo`), Paketfeld `takt` (`_uebung_lesen` tolerant, `stand()` nur gesetzt, `FELDNAMEN["takt"] = "Takt"` nach `beschleunigung`; `trainingsapp-paket pruefen` meldet falsche Typen als Fehler, unbekannte Art/Klang/Schlüssel als Hinweis), `core.uebung_timer.takt_fuer(uebung, abschnitt, wahl)`, Bibliothek eigener Takte in `app_setting` (`takt_bibliothek`), Schalter `takt_vibration` | `core/timer.py`, `core/models.py`, `data/migrations/038_takt.sql`, `data/repositories.py`, `core/pakete.py`, `paket_werkzeug.py`, `core/uebung_timer.py`, `ui/state.py` |
| T1 Blatt und Zeilen | `components/takt_blatt.py` (`blatt_spalte`): Vorlagen und eigene Takte als Chips, Name, Phasen-Zeilen (Name, Sekunden mit Zehnteln, Art, Klang mit der Vorgabe je Art im Menü, ✕), „+ Phase“ (Art wechselt ein ↔ aus, ab ↔ auf), Animation wählbar, Tempo-Regler 0,5×–2× mit Rate, Rundendauer und Phasenzahl, die **Vorschau** läuft im Blatt (eigene Aufgabe, endet mit dem Blatt), Knöpfe nach Herkunft: „Takt starten“, „Für jetzt“, „In den Abschnitt“, „In die Übung „…““, „In die Bibliothek“ (braucht einen Namen; gleicher Name ersetzt), „Kein Takt“, „Wie eingestellt“ (nimmt die Wahl für jetzt zurück). „Übung bearbeiten“ → Uhr und Timer: die Zeile „Takt: 4-7-8 · 4-7-8 · 3,2/min“ mit Stift, ✕ und (i) (`hilfe.THEMEN["takt"]`), im Formular gehalten, Zurück speichert; Timer-Editor: dieselbe Zeile je Abschnitt (`_Zeile.takt`); die Übungsseite nennt den Takt unter „Uhr und Timer“ | `components/takt_blatt.py`, `components/hilfe.py`, `views/uebung_bearbeiten.py`, `views/timer.py`, `views/uebung_detail.py` |
| T2 Lauf | `TimerLauf.takt_jetzt`/`takt_uebung`/`tempo_faktor`, `takt_aktuell(nummer)`, `takt_lage()` (Zeit im Abschnitt = `abschnitt_s − rest_s`, Stoppuhr: gelaufene Zeit; angehalten steht sie; je Abschnitt ein `TaktLauf`), `tempo_setzen` (P139, für jetzt; `tempo_aenderungen` für die Zeitleiste). Der Ticker (`ui/timer_takt.py`) rechnet je Tick die Lage, `wechsel` → `takt_melden`: Klang der neuen Phase (eigener, sonst Vorgabe je Art: ein Glocke 1, aus Glocke 3, halten Klangholz, ab/auf Piep, frei Klangschale) über `ton_spielen` mit Regler und Lautstärke der Signale, Vibration kurz (Schalter, Vorgabe an); nicht über ein Timer-Signal desselben Takts (der Abschnittsklang bleibt), nach „Weiter“ tönt die laufende Phase nicht erneut (`_lage_beim_start`). `TimerBaustein._takt_melden`: `timer/takt` am Abschnittsbeginn mit Takt (zur Zeit der Marke) und je Tempoänderung (`core.einheit.ARTEN` += `takt`, `DATEN_SCHLUESSEL` += `tempo`, `phasen_s`, `arten`; Vertrag `docs/plan_einheit.md` §4). Takt-Knopf an der Uhr (`takt_knopf`, Zeile und Knöpfe neben „zählt“; im Timer der Übung über den Chips; im Reiter „Timer“ in der Steuerung, Schlüssel `timer`): „Für jetzt“ → `AppState.uhr_takt[key]` (`AUS` = keiner), „Takt starten“ startet die gesetzte Uhr (ohne Timer die Stoppuhr; im Timer der Übung ein Timer ohne Ablauf) mit diesem Takt; `takt_anbringen` hängt Wahl, Vorgabe der Übung und `uhr_tempo` beim Start und Bereitstellen an den Lauf; der **Tempo-Regler live** (`TempoRegler`) steht in der laufenden Uhr, im Timer der Übung und im Reiter „Timer“, solange ein Takt läuft — sofort wirksam, nur für jetzt | `core/timer.py`, `ui/timer_takt.py`, `devices/einheit.py`, `core/einheit.py`, `components/takt_blatt.py`, `components/uhr.py`, `views/uebung_timer.py`, `views/timer.py` |
| T3 Animation | `components/takt_anzeige.TaktAnzeige(groesse, klein, on_click)`: Puls (Ring füllt sich, die Mitte blitzt am Schlag), Kreis (`animate_scale` mit der Phasendauer, `EASE_IN_OUT`: ein/auf groß, aus/ab klein, halten bleibt mit leuchtendem Rand, frei wechselt), Box (dazu vier Rahmenseiten mit Lauflicht), Balken (Segmente nach Dauer, der laufende füllt sich), Welle (32 Stützstellen einer Sinuslinie, der Punkt wandert); Farbe je Art (ein kühl, aus warm, halten neutral, ab/auf Primärfarbe), Name und Restsekunden in der Mitte, Runde, Rate und Tempo darunter. **Einmal gebaut**, `nachziehen(takt, lage)` setzt je Tick nur Werte, baut nur beim Wechsel von Takt oder Animation neu (V1). Steht im Reiter „Timer“ unter der Zeit, im Timer der Übung („Während“) unter der Leiste, in der laufenden Uhr klein (antippen → groß, `takt_gross`, ein Dialog am Ticker) und im Live-Vollbild als Kopfzeile „Soll ▲ ein 3 s“ neben der Atmung des Sensors (`takt_kopf_text`) | `components/takt_anzeige.py`, `views/timer.py`, `views/uebung_timer.py`, `components/uhr.py`, `views/live_vollbild.py` |

Tests: `tests/test_takt.py` (flet-frei, in `test_import_regel` geführt: Vorlagen, Lage, Wechsel,
Tempo ohne Sprung, Soll-Phasen, Rundreise, Prüfung, Vorrang, Paket, Werkzeug, Lage aus der
Uhr, Zeitleiste, `takt_melden`, Ticker), `tests/test_ui_takt.py` (Blatt, Bibliothek, Formular,
Timer-Editor, Anzeige ohne Neubau je Tick, Takt-Knopf, laufende Uhr, Reiter „Timer“,
Einstellung, Vollbild), `tests/test_repositories.py` (Rundreise, Migration 038), Doctests.

**Beim Bauen entschieden:** (1) Der Tempo-Regler im Lauf ist ein eigener Faktor am
`TimerLauf` (`tempo_faktor`, Takt-Tempo × Regler, begrenzt auf 0,5–2) — der gespeicherte Takt
behält sein Tempo; im Blatt stellt der Regler das Tempo des Takts, das mitgespeichert wird.
(2) „Kein Takt“ für jetzt ist `takt.AUS` in `uhr_takt` (schaltet auch Abschnitt und Übung ab);
„Wie eingestellt“ nimmt die Wahl zurück — ohne diesen dritten Zustand käme man nicht zur
Vorgabe zurück. (3) `timer/takt` schreibt die Dauern **mit Tempo** (`phasen_s`, `soll_s`), dazu
`tempo` — so ist das Ereignis für sich lesbar. (4) Die Animation ist am Takt gespeichert
(`Takt.animation`, auch im Paket); leer heißt nach Phasenzahl. (5) `Takt.zaehlt` ist im Format
schon da (Paketfeld, Dict), aber ohne Wirkung und ohne Schalter — T5 nimmt es. (6) Die Stoppuhr
mit Takt rechnet ab ihrem Start; ein Abschnitt ohne Takt (Pause) beendet den Takt (`ende`), die
nächste Runde beginnt ihn von vorn. (7) Material kennt kein Metronom-Symbol — `GRAPHIC_EQ`
steht für den Takt.

**Noch nicht (Teil 2, T4–T6):** Marke `atemtakt` und `atmung` `getaktet` in der Messdatei,
Soll-Phasen ins Beiwerk `atem-v1` (`Messlauf.atem_takt_*`), Auswertung Soll gegen Ist, „Takt
zählt“ (Zähl-Teil mit Quelle `takt`), GIF/Bild der Bewegung an der Übung. Offen aus Teil 1:
P140 (Vibration am Phasenwechsel — gebaut mit Schalter, Vorgabe an; nicht entschieden); die
Zeile in „Im Plan einstellen“ (ein Takt je Planübung) ist nicht gebaut — der Vertrag sieht
Übung, Abschnitt und Uhr für jetzt vor; das Querformat/Live-Vollbild zeigt den Takt nur als
Kopfzeile, nicht als Animation (Platz).
