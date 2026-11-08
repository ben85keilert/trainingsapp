# Planblock: eine Übung je Bild und der Fokus

Ben, 7.11.2026 („Lass uns ersteinmal A anpassen. Der Sprung zu B ist logisch dann nicht mehr so
schwer“). Dieses Dokument ist der Vertrag für den **Modus Standard** (A) beim Üben im Plan und
für die **Trainingsansicht „Fokus“** (B) zur laufenden Uhr. Workouts (Abläufe von vorn bis
hinten, P83) kommen danach und bauen darauf auf.

Skizzen: https://claude.ai/artifact/THG2KrMi4jET9N2XkHRk3J (Reihe A, Reihe B).

## A. Modus Standard — eine Übung je Bild

Vorher standen alle Planübungen untereinander, mit drei umschaltbaren Darstellungen
(untereinander · ein Parameter · aufklappen) und einem grauen Erklärtext unter dem Kopf.
Jetzt (`ui/views/plan.py`, Üben-Zweig):

- **Eine Zeile** (Korrektur Ben, 7.11.2026 abends): die Pfeile, **benannt nach den Nachbarn**
  („‹ Nacken dehnen“ · **2/6 ▾** · „Kniebeuge ›“ — der Name der gezeigten Übung steht im
  Block selbst; abgeschnittene Nachbarnamen stören nicht), in der Mitte **2/6 ▾** — ein Tipp
  öffnet den **Gesamtplan** als Blatt (`ui/components/planblatt.py`: je Übung Bild, Name,
  Ziel, „k. Mal im Plan“, Haken wenn heute erledigt, Uhr- bzw. Sensor-Symbol wenn dort
  etwas läuft; die gezeigte ist markiert; ein Tipp wechselt nach dem Schließen; der Kopf
  nennt „x von n heute“). Kein eigener Kopf, kein i: die Legende der Knöpfe steht im „?“ oben
  (`components/hilfe.PLAN_MD` = `KNOPF_LEGENDE` + Notation). Kein Darstellungsmenü.
  Die Zeile **steht fest** über der Liste (Ben, 8.11.2026: „Die Pfeile links-rechts scrollen
  mit, so dass man von überall aus durch die Übungen kommt“) — nur der Block scrollt darunter
  (`pfeile_halter`, neu bei jedem Wechsel und Eintrag).
- **Ausprägungen** (Gewicht, Winkel): das gewählte Segment ist nur farbig, ohne Haken — der
  Haken brach „60°“ in drei Zeilen um. **Wischen**
  über den Block (`ft.GestureDetector`, nur `on_horizontal_drag_end`, Schwelle
  `WISCH_SCHWELLE` = 300 px/s wie im Verlauf; Slider und scrollende Variantenreihe gewinnen
  als Kinder). Kein Umlauf an den Enden.
- **Nach „Gemacht“ bleibt der Block stehen** — das Tempo bestimmt die Person (Modus A);
  der nächste Pfeil wird gefüllt (`FilledTonalButton`). Kein Weiter-Chip, kein Hinweis auf
  eine Uhr in einer anderen Übung: Was läuft, steht ohnehin in der Laufleiste, und eine
  zweite Uhr meldet die Einheit (Ben: „Dadurch ist das abgesichert“).
- **Welche Übung gezeigt wird:** `AppState.plan_ziel` (einmal — „Weiter mit …“ auf Heute,
  Ziele, Laufleiste) › `AppState.plan_gezeigt[plan_id]` (zuletzt gezeigt, Sitzung; überlebt
  `neu_zeichnen`, also Start der Uhr und Takt der Einheit) › erste heute offene › erste.
- **Ein Eintrag** baut nur den Block in derselben Liste neu (`auffrischen`), ein Wechsel
  der Übung rollt nach oben und löscht die gemerkte Scrollposition; die Beobachter der
  Uhrzeile des alten Blocks verfallen (`timer_beobachter["uhr_in_der_uebung"]`).
- **Einzelübung** (`/training/<id>`) und **Nachtrag** haben einen Block ohne Pfeile;
  **Bearbeiten** bleibt die ziehbare Liste aller Übungen.
- **Entfernt (P1 entschieden):** `PLAN_DARSTELLUNGEN`, `plan_offen`, `parameter_wahl`, das
  Setting `plan_darstellung` (bleibt ungelesen in `setting` liegen), das Dropdown „Übungen im
  Plan“ in den Einstellungen, der `ScrollKey`-Sprung.

Tests: `tests/test_ui_plan_navigation.py`.

## B. Fokus — die Trainingsansicht zur laufenden Uhr

**Name:** „Fokus“ (Arbeitstitel; Alternativen: „Bühne“, „Mitmachen“, „Trainingsbild“). Der
Fokus ist der Timer der Übung (`ui/views/uebung_timer.py`), solange ihre Uhr läuft — er zeigt
dann „Während“: große Zeit, Stand, Balken, **Takt-Animation** mit Tempo-Regler, **Bild der
Bewegung**, **HF-Kachel**, Zählstand des Sensors, Sätze, Anhalten/Weiter/Fertig/Abbrechen.
Titel „Fokus · Übung“.

- **Kein Zwang** (Ben): Die laufende Uhr bleibt in der Übung; dort steht oben rechts in der
  Uhr-Karte der Knopf **Fokus** (⤢, `components/uhr._laufend`). Zurück führt in die Übung.
  Einstellungen → Übungen: **„Fokus beim Start der Uhr öffnen“** (`SettingRepo.FOKUS_AUTO`,
  Vorgabe aus) — dann geht er mit dem Start auf.
- **Ebenen als Chips** oben: Takt · Bewegung · HF (`AppState.fokus_ebenen`, gemerkt je
  Gerät). „Sensor“ ist kein Chip: Der Zählstand erscheint, sobald der Sensor zählt, und
  „Sensor dazu“ in der Zählkarte startet ihn (P118: der Knopf ist die Messung).
- **HF-Kachel:** vorläufig die Herzfrequenz des Gurts (`Messlauf.live.kennzahlen().hf_bpm`),
  „kein Gurt“ ohne Messlauf. Später wählbar: Atemfrequenz, HRV-Kennzahlen, andere Sensoren
  (Ben: „Das kann man dann einstellen. Provisorisch geht HF“) → P-Katalog.
- **Bild der Bewegung** (`core/bewegungsbild.py`, `components/bewegungsbild.py`):
  - **Bildfolge:** ein PNG/JPEG, dessen Breite ein Vielfaches der Höhe ist, gilt als Folge
    quadratischer Bilder — der **Hinweg** (Stand → Hocke). Je Takt-Lage ein Bild
    (`bild_fuer_lage`): „ab“/„ein“ vorwärts, „auf“/„aus“ rückwärts, „halten“ am Ende der
    vorigen Phase, „frei“ als Pendel; ohne Takt ein Pendel über die Zeit (`bild_fuer_zeit`,
    1,5 s je Weg). `Bildfolge` ändert je Tick nur den Versatz des Streifens.
  - **GIF:** weiter als Schleife mit eigenem Tempo.
  - **Mitgeliefert:** die Folge **Kniebeuge** (`ui/assets/bewegung/kniebeuge.png`, 12 Bilder,
    aus `scripts/bewegung_kniebeuge.py` mit Pillow gezeichnet) — gilt für Übungen mit der
    Sensor-Vorlage „kniebeuge“ ohne eigenes Bild (`EINGEBAUT`). Teil des Pakets, kein Medium.
- **Tempo** (Nebenbei, Ben): Der Regler stellt jetzt die **Geschwindigkeit** (rechts
  schneller, 2× = halbe Dauern); gespeichert bleibt der Faktor auf die Dauern (`Takt.tempo`,
  Paketfeld, Zeitleiste), `core.takt.geschwindigkeit`/`faktor_von`; `tempo_text` zeigt die
  Geschwindigkeit.

## C. Medien einer Übung — Kategorien (Vorschlag, noch nicht gebaut)

Ben: „überlege, welche Kategorien an Medien man für eine Übung hinterlegen kann … und wie man
diese in die Ausführung einbindet“. Vorschlag für `core.models.Media` ein Feld **`rolle`**
(Paketfeld `medien[].rolle`, fehlt = `erklaerung`), statt eines zweiten Mechanismus je Art:

| Rolle | Was | Woher | Wo in der Ausführung |
|---|---|---|---|
| `symbol` | Bild der Übung (Katalog, Kopf) | Symbolvorrat, eigenes Foto (`Medien/Symbole/`) | schon gebaut (`uebungsbild`) |
| `bewegung` | Bildfolge oder GIF der Bewegung | Ablage `Medien/Bewegung/`, mitgeliefert je Vorlage, **später im Paket** (Bildfolge als Datei neben der TOML) | Fokus, im Takt (gebaut) |
| `erklaerung` | Erklärvideo oder Bildergalerie | Link (öffnet im Browser), später lokale Datei | Übungsseite „Videos und Links“; im Fokus **vor** dem Start als Knopf „Anleitung“ |
| `mitmachen` | Video zum Mitmachen (Yoga, Qigong) | lokale Datei (flet-video), Link | Fokus: das Video **ist** die Fläche, die Uhr läuft daneben; Vorschlag: Timer-Abschnitt „wie das Video“ (Dauer aus dem Video) |
| `ansage` | Audio: gesprochene Anleitung, Zählansage | Aufnahme (flet-audio-recorder), Datei | Fokus/Uhr: spielt beim Start bzw. je Phase (Klang des Takts) |
| `hinweis` | Text/Bild „Worauf achten“ | Beschreibung in Abschnitten (gebaut) | Übungsseite; im Fokus als eine Zeile unter dem Stand |

Regeln: Eigene Dateien bleiben app-privat (nie Export, Backup, Sync — wie Anhänge);
**Paket-Medien** reisen nur, wenn sie frei lizenziert sind (`license` am Medium, schon da).
Im Fokus zeigt ein Chip je vorhandener Rolle (Bewegung · Video · Ansage) — dieselbe Mechanik
wie Takt · HF. Offen: Video-Download (P14), Sicherheit von Medien aus Paketen (K1).

## Offen

- P1 (entschieden): eine Übung je Bild, drei Darstellungen entfernt.
- P93: HF-Kachel wählbar (Atemfrequenz, RMSSD, andere Sensoren).
- P94: Medienrollen (Tabelle C) und Paket-Medien.
- P95: Fokus-Name endgültig („Fokus“ · „Bühne“ · „Mitmachen“).
- Workouts (P83, Modell nach Bens Antworten 7.11.2026, Vertrag folgt als
  `docs/plan_workout.md`): Start per Schalter am Plan **und** ▶ für heute; Übergang vor dem
  Start **hart** (rauscht durch) oder **weich** (Timer zählt ins Minus, „Weiter“ von Hand);
  Bedingungen `keine | zeit | wdh(n) | wdh_in_zeit(n, s) | gemacht`, Härte = Freischaltung von
  Inhalten (Abbrechen immer); benannte Zweige A/B/C mit „erfüllt →“ / „nicht erfüllt →“
  auf jeden Schritt; Workout-Abschnitt in der HRV mit den Übungen darin; HF-Zone nur als
  Anzeige (Zeit in Zone), Zielbereich-Ton nach Entscheidung C — nie als Bedingung
  (`docs/recht/00_zweckbestimmung.md`). Stufen W1 Grundmodus · W2 Bedingungen · W3 Zweige ·
  W4 Zonen-Anzeige/Ton. Skizzen Reihe C auf Kommando.
- Gerätetest T94: Pfeile, Wischen, Gesamtplan, Fokus-Knopf, Auto-Fokus, Kniebeuge-Bildfolge
  im Takt (Vorlage Kniebeuge, Takt ab/auf), Tempo-Regler rechts = schneller.
