# Planung: HRV-Messung, Timer, Ordnung (13./14.10.2026)

Bens Auftrag vom 13.10. abends, sieben Punkte. Leitlinie: Die App ist für
Patienten und Kunden zur Selbstüberprüfung — nicht kompliziert, sinnvolle
Vorgaben, alles zurücksetzbar. Hier steht, was umgesetzt ist, welche
Entscheidungen dabei ohne Ben gefallen sind und was er entscheiden sollte.

Commits: `2e7a6b8` (Rechenkern), `a3b6e62` (Übungen), `75b7308` (Messung,
Einstellungen, Timer, Notizen), `2a50795` (Feinschliff).

---

## 1) Einstellungen der HRV-Messung — umgesetzt

**Einstellungen → HRV-Messung** (`ui/views/einstellungen_hrv.py`), gespeichert
gerätelokal (`core/hrv_einstellungen.py`, `app_setting: hrv_einstellungen`):

| Einstellung | Vorgabe |
|---|---|
| Reiter „Messung" anzeigen | an — ausgeblendet bleibt er, solange eine Messung läuft |
| Werte über der Kurve | **Übersicht** (seit 14.10.; Kacheln wählbar): Herzfrequenz und RR groß, darunter Atemfrequenz, RMSSD, SDNN, Schwankung, Artefakte |
| Zeitfenster live | 2 min |
| korrigierte Kurve live | an |
| pNNx-Schwelle | 50 ms |
| Analyse: Frequenz / Nichtlinear | aus / aus (seit 14.10. — für Laien uninteressant) |
| Atemübung (langsames Atmen auswerten) | aus |
| Nichtlinear bei optischen Sensoren | aus (nicht empfohlen) |
| Übungen in Notizen anbieten | an |
| Automatische Korrektur | Regeln wie bisher (`Korrekturregeln()`) |

„Alles auf Standard zurücksetzen" setzt Einstellungen, Kurvenansicht und
Korrekturregeln zurück; **unter Namen gespeicherte Ansichten bleiben** (das
ist Arbeit des Nutzers). Die kleinen Knöpfe in der Messung (Fensterbreite,
„korrigiert", Regler, Kurvenmenü) ändern dieselben Werte.

Kacheln stehen in fester Reihenfolge (Katalog: Grundwerte, Zeit, Frequenz,
Nichtlinear); Kacheln einer Kurve rechnen mit deren Fenster und tragen ihre
Farbe. In der Aufzeichnung zeigen dieselben Kacheln die Werte der ganzen
Messung.

**Zu entscheiden:** Soll man die Reihenfolge der Kacheln selbst bestimmen
können (Ziehen)? Bisher nicht — bewusst einfach.

## 2) Übungen in Notizen — umgesetzt

In der Notizeingabe blendet „Übungen" die Übungen eines Plans als kleine Namen
ein (heute anstehende Pläne zuerst, zuletzt „Alle Übungen"); ein Tipp setzt den
Namen in den Text, mehrere mit Komma. Der Zustand (offen, welcher Plan) bleibt.

**Entscheidung ohne Ben:** Gespeichert wird nur Text. Ein Verweis auf die
Übung (`uebung_id` im Ereignis) wäre für spätere Auswertungen schön, ist aber
eine Formatänderung von `raw-v1` und braucht zuerst einen Eintrag im Vertrag
(`docs/kompatibilitaet.md`). **Zu entscheiden:** Wollen wir das?

## 3) Timer als Werkzeug — umgesetzt (einfach)

Symbol oben in der Leiste (Hauptansicht und Planansicht), öffnet sich über der
aktuellen Ansicht (`<route>/timer`, „Zurück" führt dorthin zurück). Profile aus
benannten Abschnitten (`mm:ss`, auch `1,5` = 1,5 min) und Runden; das zuletzt
benutzte ist aktiv; zwei Vorlagen (Intervall 30/15, Halten 3 × 1 min), die nach
dem Löschen aller eigenen wiederkommen. Läuft er, steht die Restzeit in der
Leiste. Abschnittswechsel vibriert (Android), das Ende doppelt.

Der Ablauf rechnet auf der monotonen Uhr (`core/timer.py`), nicht mit
gezählten Ticks: Er driftet nicht und stimmt nach dem Aufwachen sofort.

**Zu entscheiden:**

- **Ton.** Für Training ohne Blick aufs Handy wichtig. Braucht das Paket
  `flet-audio` (Flutter `audioplayers`) — neue Abhängigkeit, APK-Build prüfen.
- **Hintergrund.** Bei dunklem Display kann Android die App schlafen legen;
  dann fehlt die Vibration (die Zeit stimmt trotzdem). Abhilfe wäre der
  Vordergrunddienst, den die HRV-Messung schon nutzt.
- **Kopplung mit HRV-Messung und Plan** — drei Wege, aufeinander aufbauend:
  - A: Läuft eine Aufnahme, setzt jeder Abschnittswechsel automatisch eine
    Notiz („Belastung", „Pause") in die Messung — ohne Formatänderung, sofort
    möglich. Dann zeigen Kurven und Blöcke (je Abschnitt!) den Verlauf.
  - B: Eine Planübung bekommt ein Timer-Profil (z. B. Planke „Halten 3 × 1 min");
    „Gemacht" mit dem Timer trägt die Haltezeiten ein. Braucht eine Tabelle
    statt `app_setting` (Sync, Praxis-Edition).
  - C: Ein Messprofil startet Timer und Aufnahme zusammen (z. B. „5 min Ruhe,
    3 min Atmung 6/min, 5 min Ruhe") — der Weg zu Benchmarks.

  Vorschlag: A zuerst (klein, sofort nützlich), B mit L07, C mit den Benchmarks (M8).

## 4) Frequenzanalyse — umgesetzt, live und nachträglich

`hrv_core/frequency.py` ist kein Gerüst mehr: Lomb-Scargle, Welch und
Periodogramm in numpy, Rechnung für Rechnung wie scipy und praxis_gui. Golden-
Tests auf drei Dateien stimmen auf wenige ppm (`tests/test_frequenz.py`).
Dazu DFA α1 (wie neurokit2) und SampEn (wie praxis_gui).

**Einbau:** Unter der Hauptkurve schaltet man **Zeit ↔ Frequenz ↔
Nichtlinear** um; die Hauptkurve läuft oben weiter. Frequenz zeigt das Spektrum
des *sichtbaren Ausschnitts* (zoomen und wischen ändern es) mit getönten
Bändern und dem stärksten Gipfel, dazu LF, HF, LF/HF und Gipfel als Zahlen und
als Verlaufskurven. Nichtlinear zeigt die Poincaré-Wolke, SD1, SD2, DFA α1. Die
Aufzeichnung fasst je Bereich die ganze Messung zusammen. Ein- und ausschalten:
Einstellungen → HRV-Messung → Analyse.

**Entscheidungen ohne Ben (mit Begründung):**

- **Lomb ist der Standard** (wie praxis_gui): kein Resampling, verträgt
  Lücken, trifft LF/HF am besten. Welch und Periodogramm sind gebaut und
  getestet, aber nicht wählbar — das wäre eine Einstellung für Fachleute.
- **Zwei Rechenwege.** Ganze Aufzeichnung wie praxis_gui (Teilspektren, Bänder
  unter ihrer Mindestdauer gesperrt: HF 3 min, LF 5 min, VLF 20 min). Fenster
  (Kurven, Live) als ein Lomb über alle guten Schläge mit echter Zeit — sonst
  fiele jedes 2-min-Fenster mit einem Artefakt aus. Live wird nicht gesperrt,
  aber auf die Mindestdauer hingewiesen (praxis_gui: „Vorläufig").
- **Nullen trennen das Spektrum nicht** (Abweichung von praxis_gui): Eine Null
  beim H10 ist „kein Schlag", keine Lücke. Als Naht zerlegten sie eine
  Ruhemessung unter 60 bpm — auf der Golden-Datei wären alle Bänder gesperrt.
- **„Gipfel" statt „Atemfrequenz".** Die Lage des stärksten Gipfels
  (0,04–0,4 Hz, auch je Minute) ist beschreibend; praxis_gui berechnet eine
  Atemfrequenz mit Konfidenz (`respiration.py`) — das ist mehr Arbeit und näher
  an einer Aussage.
- **Keine Bewertung**, keine Ampel, keine „Kohärenz" (Zweckbestimmung, solo).
- **Optische Sensoren (Verity):** Nichtlinear standardmäßig aus, in den
  Einstellungen freischaltbar; Frequenzwerte mit Vorbehalt. praxis_gui sperrt
  nichts, seine Doku stuft Bänder „mit Vorsicht", DFA als „nein" ein.
- **Lineare y-Achse** im Spektrum (praxis_gui: logarithmisch); VLF wird oben
  abgeschnitten, damit LF und HF sichtbar bleiben.

**Zu entscheiden:**

- Atemfrequenz und RSA-Amplitude wie praxis_gui (mit Konfidenz)? Für
  Atemübungen der natürliche nächste Schritt.
- Methode (Lomb/Welch) oder logarithmische Achse in den Einstellungen anbieten?
- LF/HF wird viel überinterpretiert (bei Atmung 6/min liegt der Gipfel im
  LF-Band, LF/HF wird groß, obwohl der Zustand vagal ist). Der Hinweis steht
  in der Ansicht; soll LF/HF für Laien ganz ausgeblendet sein?

## 5) Zeitanalyse — umgesetzt

- **Ø HF bis 3 s:** Ø HF und Ø RR haben Fenster 3, 5, 10, 15, 30, 60 s; ein
  Schlag im Fenster genügt.
- **Gleitend oder Blöcke** je Kurve (Kurvenmenü → Fenster & Darstellung).
  Blöcke: ein Wert je Fenster ohne Überlappung, als Stufe gezeichnet, nur
  vollständige Blöcke. Für alle gerechneten Kurven möglich, nicht für „HF Gerät".
- **Warum nur vier Kurven?** Das war meine eigene Festlegung vom 13.10. für
  kleine Bildschirme, keine fachliche. Sie ist weg: Je Bereich stehen nur
  dessen Kurven, und gleiche Achsen teilen sich ein Diagramm.
- **Ø RR** ist neu und hat eine eigene Achse (900 ms neben 40 ms RMSSD wäre eine
  flache Linie).
- **pNN50 → pNNx**, Schwelle 10–100 ms (Kurvenmenü oder Einstellungen), Titel
  passt sich an („pNN20").

## 6) Optik der Messung — umgesetzt

- Reiter oben **„Live | Aufzeichnungen (n)"** statt der Liste unter allem.
- Status mit **Aufnahmeknopf ganz oben** (bisher unter allen Kurven).
- **Kacheln als Raster:** groß zu zweit, sonst zu dritt, gleiche Höhe, Abstand,
  Farbstreifen der Kurve.
- **Karten** für Hauptkurve (mit Fensterwahl, „korrigiert", Notizen) und
  Analyse; Chips mit Farbpunkt und Abstand statt dichter Kästchen.

**Zu prüfen am Handy:** Größen, Farben, ob die Kacheln zu dritt bei kleinen
Bildschirmen passen (getestet in 412 px Breite im Browser).

## 7) Ordnung in der App — teilweise

- **Übungen:** Formular (Eintrag, Ziel) — jedes Feld in voller Breite, Chips
  darunter; Übung bearbeiten — Chip-Feld unter dem Schalter; Übungsdetail — je
  Parameter ein Block; Katalog — Einordnung und Notation in zwei Zeilen.
- **Einstellungen** in Karten; Notizfelder in voller Breite.
- **Offen:** „Heute" fasst Pläne doppelt zusammen (Bilanz oben, Plan darunter).
  Welche Stellen Ben noch als gedrängt empfindet, wäre am besten mit
  Bildschirmfotos zu klären.

---

## Nachtrag 14.10.: Bens Antworten, umgesetzt

- **Übersicht statt Kacheln** (Vorgabe): große Werte oben in einer Reihe,
  darunter eine ruhige Liste — Name links, Wert rechts, Farbpunkt der Kurve.
  Komplett einstellbar (Einstellungen → HRV-Messung): ziehen ordnet um, der
  Stern hebt groß hervor, × entfernt, „+" fügt hinzu; „Kacheln" bleibt wählbar.
- **Frequenz und Nichtlinear standardmäßig aus** — wer sie einschaltet, hat
  LF/HF als Wert und als Verlaufskurve (Vorgabe in der Kurvenansicht).
- **Atemfrequenz** nur bei deutlicher Atemschwankung, gemeinsam mit praxis_gui
  (`hrv_core/atmung.py`, byteidentisch; Messwerte in `docs/hrv_algorithmen.md`).
  Ohne deutliche Atmung steht der Grund in der Übersicht; bei langsamer
  Schwingung mit Knopf „Atemübung". praxis_gui ist umgestellt (Arbeitskopie,
  **noch nicht committet** — Bens Freigabe).
- **Timer-Ton** über die eigene Erweiterung `flet_ton` (Musik wird geduckt,
  nicht angehalten): Countdown 3-2-1, zwei Töne beim Wechsel, vier am Ende.
  Signale: Ton, Countdown, Vibration, Bildschirm anlassen, Abschnitte in die
  HRV-Messung — alles an, alles abschaltbar. Seit 14.10. auf eigener Seite
  (`…/timer/signale`): unter dem Timer steht knapp, was an ist, das Zahnrad
  öffnet die Schalter. Dort auch **Klang** (Piep, Glocke 1–3, Gong, Klangholz,
  Fanfare) und **Lautstärke**: Regler Medien (Vorgabe, statt bisher
  Klingelton/System), Wecker oder Klingelton, dazu ein Anteil 10–100 %. Im
  Timer-Profil hat jeder Abschnitt einen eigenen Klang, dazu einer für jede
  neue Runde und einer fürs Ende (`core.timer.klang_fuer`). Braucht eine neu
  gebaute App (Dart-Teil von `flet_ton`).
- **Abschnittswechsel als Notizen** (Weg A): Läuft eine Aufnahme, wird jeder
  Abschnittsanfang eine Notiz („Timer „Intervall 30/15“: Belastung (Runde 1/8)",
  … „Timer fertig") — an der Stelle, an der er wirklich war, auch wenn die App
  kurz schlief. Gewöhnliche Notizen: nachträglich umbenennen, verschieben,
  löschen.
- **Übungs-ID → Kurzcode:** 8 Zeichen (SHA-1 der UUID, 40 Bit, Crockford-
  Base32) im Feld `uebungen` der Notiz, aus den Namen im Text ermittelt
  (Vertrag Abschnitt 4). Im Text steht weiter nur der Name.

## Nachtrag 14.10., zweiter Teil: Bens Liste, umgesetzt

1. **Profile:** Auswahl vorn in den Einstellungen; anlegen, umbenennen, löschen
   (Rückfrage, das letzte bleibt) unter „Profile verwalten". PIN-Hinweis nur in
   der Praxis-Edition.
2. **Bluetooth:** „Brustgurt" nur, wenn es sicher ist (Name/Profil);
   Standardprofil heißt „Herzfrequenz-Sensor"; optische Armbänder eigenes
   Profil (PPG). Zuletzt verbundene Geräte: ein Tipp verbindet direkt.
3. **„Fenster & Darstellung"** blieb unsichtbar (nur der Bildschirm wurde dunkel)
   — jetzt ein Blatt von unten.
4. **Timer-Knopf** mit Beschriftung.
5. **Plan bearbeiten:** alles scrollt, nur die Leiste steht.
6./7. **Parameter statt Eingabestufe:** je Parameter ein Knopf, darunter seine
   Chips; keiner = nur abhaken, kein Chip = freies Feld (das es beim Üben immer
   gibt). Zurücksetzen wird bei Abweichung sofort aktiv. *Antwort auf die Frage
   nach „nur abhaken / Chips / frei":* Die drei Knöpfe waren redundant — „nur
   abhaken" heißt jetzt „kein Parameter", für lange Abhak-Pläne schaltet man
   die Parameter je Übung aus (oder im Übungsstandard „In Plänen nur abhaken").
8. **Zeiten:** „1:00s" wurde als 0 gelesen (daher „+60 → 0") — behoben; kein
   doppeltes „s" mehr.
9. **Leistungen beschriftet:** je Parameter eine Zeile („Skala 6 · 0 bis 10"),
   im Eintrag als Kacheln.
10. **Skala frei:** „0 - 10", „-5 - 5", „0.0 - 10.0".
11. **Crop:** Schere in der Aufzeichnung; Bereich wählen, alle Kennzahlen nur
   daraus; Rohdatei bleibt; praxis_gui-Feld `active_crop`.
12. **Abschnitte:** Werte je Abschnitt (Ø HF, RMSSD, SDNN, Atem, LF/HF);
   praxis_gui-Feld `segments`. Seit dem späten 14.10. **unabhängig von den
   Notizen** (Ben): Bereich in der Rohkurve wählen (Anfang/Ende ziehen oder
   tippen, ±1/±5 s, Stecknadel = auf eine Notiz), Notizen nur als Rastpunkte
   oder auf Wunsch als Grenzen („Aus Notizen …"); der Timer legt seine
   Abschnitte beim Speichern selbst an. Jeder Abschnitt lässt sich antippen,
   verschieben, umbenennen und löschen (mit Rückgängig). Crop genauso in der
   Kurve (grau = zählt nicht). Dazu **Ablesen** (Strich mit allen Werten) und
   **Titel/Beschreibung** (`titel`/`notiz` der Messdatei, Vorschlag: der Plan,
   der währenddessen geübt wurde).
13. **ULF/VLF bei langen Messungen** — dabei einen Fehler gefunden: Ab ~67 min
   lagen LF/HF um ein Vielfaches zu hoch (Rasterdeckel; **praxis_gui hat ihn
   auch**). Jetzt Spektrum in drei Teilen, bis 24 h geprüft, 24 h in 2,4 s.

---

## Ausprobieren

- Am Rechner: `uv run flet run src/trainingsapp/ui/app.py` → Messung → „Simulator
  wie H10" (atmet 6/min: Gipfel bei 0,1 Hz im Spektrum).
- Bluetooth nur in der APK (`uv run python scripts/apk_bauen.py`).
