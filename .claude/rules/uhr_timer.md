---
paths:
  - "**/*uhr*"
  - "**/*timer*"
  - "**/*fokus*"
  - "**/planpfeile.py"
  - "**/zeit_stellen.py"
  - "**/uebung_lauf.py"
---

# Uhr, Fokus und Timer

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

- **Uhr und Fokus beim Üben** (Ben, 8.11.2026 spät, Vertrag `docs/plan_uhr_fokus.md`, Stand §9):
  Die Uhr-Zeile ist `Uhr ▾ · Zeit · Takt · ▶` (`components/uhr.py`); **▶ öffnet den Fokus**
  (`AppState.fokus_auto`, Vorgabe an, Schalter rechts in der Zeile von „Gemacht“, in der Einzelübung im Kopf über dem ▶), „Uhr aus“
  heißt **„Ohne Uhr“** (`core.timer.ohne_uhr`: Stoppuhr, die nicht zählt). Das ⏱ öffnet das
  **Uhr-Blatt** mit Geltung Für jetzt · In „Plan“ · Übung (`components/uhr_blatt.py`; Ben,
  17.11.2026, §4.1: beim Üben ist **„Für jetzt“ vorbelegt**, dort steht **„Timer stellen …“ in
  der Liste hinter der Stoppuhr** — kein Knopf darunter; „Übernehmen“ ohne Änderung schreibt bei
  „Für jetzt“ nichts fest). Der Fokus
  hat die Karte **„Eintragen“** (`components/fokus_eintragen.py`, auch im Workout): Eingaben als
  `person/wdh|skala|auspraegung`, eingetragen erst mit dem Ende des Laufs; Wiederholungen mit
  den Knöpfen des Blocks — **jeder Tipp ein Satz dazu**, „−“ nimmt den letzten zurück
  (`person/wdh` mit `dazu`). Im laufenden Fokus nur, was gerade passiert: keine „Läufe heute“,
  Erklärungen im „i“ (Titelleiste), Takt · Zeit · Ebenen-Knopf in einer Zeile, die **beim
  Scrollen oben stehen bleibt** (`fokus.OBEN`) — direkt darunter, ebenfalls fest, die
  **Steuerzeile** (`fokus.steuerzeile`, Ben 10.11.2026, §9.4): ⏸ · Fertig · „Wiederholen“ · ⏭ ·
  ✕ in einer Zeile, Pause/Überspringen/Abbrechen nur als Symbol; **„Weiter: …“ und Wege erst
  nach der Übung, dann vorn** (Ben, 15./16.11.2026, §10: als Erstes unter der Steuerzeile; keine
  „danach“-Zeile), die **Sätze stehen unter „Eintragen“** (`fokus.saetze_karte` — `bauen` gibt
  sie nicht mehr zurück); Fokus-Ansichten (``data = FOKUS_ANSICHT``) bekommen **keine
  Laufleiste**. **Messung läuft weiter** ist Vorgabe (`Einheitslauf.stoppt_am_ende`): nach Timer,
  Übung, Workout und GPS-Training läuft eine mitgestartete Messung weiter — außer sie ist allein
  oder die Einheit begann als reine Messung (`beitreten`); die Strecke findet sie dann über die
  Einheit (`hrv_bezug`). Ein Timer-Abschnitt
  kann eine **Ausführung** tragen (`Abschnitt.ausfuehrung`, flach in `timer/abschnitt`) —
  eingetragen wird **je Ausführung ein Eintrag** (`core.timer_eintrag.nach_ausfuehrung`,
  `Eingaben`; beim Üben und im Workout). Pfeilzeile `components/planpfeile.py` im Plan und im
  Fokus; alle Timer unter Einstellungen → Timer und Takt → „Alle Timer“ (`views/alle_timer.py`,
  `core.uebung_timer.alle_timer`). **Timer-Editor** (Ben, 9.11.2026, `docs/plan_timer_editor.md`,
  Skizzen G1–G5): fest oben Name und Gesamtzeit, Reiter **Zeiten · Klänge** (Wischen: eine
  Scrollfläche, die Namen bleiben stehen, nur die rechte Spalte gleitet — feste Zeilenhöhen),
  je Abschnitt eine Zeile, Teile ⧉ kopieren, Abschnitte per langem Druck; die Felder halten
  Werte, nicht Controls (jeder Aufbau legt sie neu an). **Für jetzt mit Abschnitten**: das
  Zeit-Blatt hat „Mit Abschnitten …“ (`zeit_blatt(erweitert=)`), `…/bearbeiten/einmal` mit
  `views.uebung_timer.jetzt_profilziel` — `AppState.uhr_einmal` hält Profile, gespeichert wird nur
  per „Als Timer der Übung speichern …“.

- **Timer zuordnen statt kopieren** (Ben, 10.11.2026, Vertrag `docs/plan_timer_zuordnen.md`,
  Stand §7, Skizzen Z1–Z4): Die **Timer-Bibliothek** ist die Tabelle `timer` (Migration 052,
  `TimerRepo`; vorher die Einstellung `timer_profile`, sie zieht beim ersten Lesen um). Übung
  (`exercise.timer_json`), Plan (`plan.timer_json`) und Planübung (`TimerWahl.eigen`) dürfen
  statt einer Kopie **verweisen**: gespeichert ``{"ref": "<id>"}``, geladen das Profil mit dem
  Vermerk `TimerProfil.bibliothek` (`core.timer.verweise_aufloesen`/`verweise_schreiben`, im
  Repo `_timer_lesen`/`_timer_json`). **Wer ein Profil mit Vermerk speichert, ändert den Timer
  überall** — die Oberfläche fragt ab zwei Stellen vorher „Überall ändern · Nur hier: Kopie
  anlegen“ (`components/timer_stellen.py`, auch bei Zurück); „nur hier“ heißt Vermerk weg und
  neue ID (`ui/timer_bibliothek.kopie`). Keine Zuordnungstabelle: wo ein Timer gilt, rechnet
  `core.uebung_timer.stellen`. Zuordnen unter Einstellungen → Timer und Takt → „Alle Timer“ → „Zuordnen …“
  (`views/timer_zuordnen.py`: Filter der Übungsauswahl, „Alle n ankreuzen“), „Gleiche
  zusammenlegen …“ nie still. Pakete und alles, was das Gerät verlässt: `ohne_verweise`
  (eingebettete Kopie). Im Plan-Editor **eine Timer-Zeile** (`components/timer_zeile.py`: Name ▾
  = Uhr-Blatt mit Für jetzt · In „Plan“ · Übung, ✎ = derselbe Editor wie beim Haupttimer in der
  Karte, `components/timer_editor.py`, darunter „Geändert gilt:“); „Für jetzt“ gibt es dort
  nur, solange geübt wird. **Unter „In „Plan““ stehen auch die Timer der anderen Planübungen
  dieses Plans** (Ben, 17.11.2026, §8; `core.uebung_timer.timer_im_plan`) — gewählt wird
  zugeordnet, nie kopiert: ein „nur hier“-Timer kommt dafür in die Bibliothek, erst mit
  „Übernehmen“; keiner mit Ausführung je Abschnitt (P174).

## Begleitvideo im Fokus (Ben, 18.11.2026, `docs/plan_medienrollen.md` M5)

- Eine Begleitung, die die App selbst abspielt (`core.material.Material.begleitvideos`), läuft im
  Fokus als Fläche (`Fokus.video_platz`) und **folgt der Uhr** — nur bei einem Wechsel
  (`_video_nachziehen`), damit ein ⏸ von Hand nicht je Tick überstimmt wird. Video und Bewegung
  teilen sich die Fläche, das Video geht vor; Ebene `FOKUS_VIDEO`, gespeichert „aus“ als
  `OHNE_VIDEO` (alte Listen ohne beides: an).
- Videos immer über `components/videospieler.Videospieler` (Knöpfe unter dem Bild, nicht die
  von media_kit, die nach 3 s gehen) — nie `on_position_change` abonnieren (ein Ereignis je Bild).
- **Spieler** (Ben, 20.11.2026): unter dem Bild Zeitleiste · Knöpfe (⟲ ▶ ⟳ · Schleife ·
  Lautstärke · Vollbild) · aufklappbare Lautstärke; die Zeitleiste fragt nur, solange das Video
  läuft (`TAKT_S`), gesprungen wird beim Loslassen. **Vollbild richtet sich nach dem Video**
  (`core.videoinfo.Videoinfo.hochkant`, Drehung aus `tkhd` eingerechnet;
  `ui.ausrichtung.fuer_video`/`nach_video`) — media_kit stellt sonst immer quer und gibt danach
  alle Richtungen frei. **Mit `state` aufbauen**: dann hält `ui.wach` (Grund „video“) den
  Bildschirm; media_kits eigener Wakelock nähme ihn sonst auch dem Timer weg.
- **Begleitung als Schleife**: Knopf im Spieler, gemerkt je Übung und Gerät
  (`AppState.video_schleife`); ohne Wahl läuft ein Ausschnitt (bis `videoinfo.AUSSCHNITT_S`)
  von selbst als Schleife. Das ✕ im Bild ist der Haken „Video“ des Ebenen-Menüs.
- Das Ebenen-Menü bleibt offen: Den Tipp bekommt ein Container im `PopupMenuItem`, nie der Eintrag
  (`on_click` am Eintrag schließt das Menü); der Haken ist ein `ft.Icon`, nicht `checked`.
