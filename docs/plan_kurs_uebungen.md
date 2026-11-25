# Planung: Übungen im Kurs — ausprobieren, testen, fragen, Medien an Stellen (23.11.2026)

Ben, 23.11.2026: „Die Kursgenerierung braucht eine dynamischere Gestaltung. Es geht um die Tests
und die Übung“ —

1. „Übungen sollen aus dem Kurs heraus gestartet werden, wenn diese nur einmalig gebraucht
   werden, um zu testen, wie sie gehen.“
2. „Eine gemachte Übung soll als Test laufen können oder als einfache Übung, der ein paar Fragen
   angehängt werden — der Kurs soll vor allem nachdenklich machen, kann sein, dass Dinge verlangt
   werden, die dann gar nicht gebraucht werden in einem Plan, aber trotzdem einmal dran kommen.“
3. „Eine Übung/Test soll wie bei Ablauf eine Übung die Möglichkeit haben, vorher/währenddessen/
   bei Ereignis/nachher ein bestimmtes Video abzuspielen. Hier bitte kohärenter Aufbau wie bei
   Ablauf.“
4. „Eine gemachte Übung kann einfach als Übung laufen, einfach um einen Eindruck zu geben. Oder
   sie kann als Test laufen, wo Werte den Plan modifizieren, entweder werden Werte übernommen,
   oder es werden Fragen gestellt, um z. B. Ziele zu bestimmen/zu verändern. Hierbei sind die
   eingegebenen Variablen Wdh/Zeit/Haltezeit/Skala/Ja-Nein usw. zu speichern und für später
   verfügbar zu machen.“

**Stand: gebaut am 23.11.2026 (§12), ergänzt am 25.11.2026 (§13: der Lauf ist der
Fokus-Bildschirm, Bewegungssensor als Startbedingung — §13 geht §12.2 vor).**
Davor: Bens Antworten vom 23.11.2026 stehen in **§10 und §11 — sie gehen den
Abschnitten §2–§9 vor**, wo sie sich widersprechen. Skizzen als Handy-Bilder: Design-Artifact
„Übungen im Kurs — Skizzen“ (Reihen A–C, zwölf Bilder; privat bei Ben:
https://claude.ai/artifact/36d4wbyy6sWDu31itDw21E); gebaut wird auf Bens Wort. Die Reste aus §10.4 sind beantwortet (§11); die Skizzen B2 und B3
zeigen noch die alte Laufansicht statt des Fokus (§11.1).

## 0. Wonach gesucht, was gelesen wurde

- Katalog: `grep -n "^| P" docs/offene_fragen.md | grep -i "kurs.*test\|test.*kurs\|probier\|kursplan\|fragearten\|kurs.*frage"`
  — ganz gelesen: P207, P213, P214, P219, P221; nur gefunden: P90, P200, P204, P205, P211,
  P212, P217.
- Vertrag `docs/plan_kurs_ablauf.md`: Gliederung, ganz gelesen §4, §7, §15, §16; nicht gelesen
  §1–§3, §5–§6, §8–§14, §17 (außer über P219).
- Code gelesen: `core/kursbloecke.py` (bis `Block`, `fertig`), Kopf und Gliederung von
  `core/kurstest.py`, `core/medien_stellen.py`, `core/material.py` (`Lage`, `Material`),
  `core/models.py` (`Media`, `Ereignis`), `core/ablauf.py` (`Frage`), Kopf von
  `ui/views/kurs_testlauf.py`, `ui/components/fokus.py` (Fälliges, Zeile 490–508), Migrationen
  065/066. **Nicht gelesen:** `ui/views/kurs_bearbeiten.py`, `core/kursbau.py`,
  `core/kursplan.py`, `data/kurse.py` (nur Funktionsnamen) — die Stufen unten nennen dort nur
  die Stelle, nicht den Umfang.
- **Nicht neu gelesen:** `docs/recht/00_zweckbestimmung.md` — die Einordnung in §7 stützt sich
  auf das, was `plan_kurs_ablauf.md` §16.2 und die Modul-Docstrings daraus festhalten.

## 1. Was es gibt — und wo es heute endet

| Wunsch | heute | Lücke |
|---|---|---|
| Übung aus dem Kurs starten | Der Block `test` startet einen **Lauf der Übung** aus dem Kapitel, ohne dass sie in einem Plan steht (`ui/views/kurs_testlauf.py`, Route `/kurse/<kurs>/<kapitel>/test/<block>/<übung>`); gestaltbar mit Uhr, Takt, Ausführung, Hinweis (`plan_kurs_ablauf.md` §15.2). | Jeder Lauf **ist** ein Test: Er muss einen Wert liefern, sonst gibt es kein „Plan anlegen“ (`core.kursbloecke.fertig`), und er zeigt „Wert für den Plan“. „Nur ausprobieren“ gibt es nicht. |
| Fragen an der Übung | Im Lauf nur die Skala der Anstrengung (Feld `scale`). Der Block `frage` steht für sich: „erklärt, prüft nicht — nichts wird gespeichert“ (`core/kursbloecke.py`, Docstring). Im Ablauf eines Workouts kennt `core.ablauf.Frage` Skala · Ja/Nein · Auswahl (einfach, mehrfach). | Keine Fragen am Lauf; im Kurs nur Antworten zum Antippen mit Hinweis, keine Skala, kein Ja/Nein; **keine Antwort wird gespeichert** (Stufe 3 von `plan_kurs_ablauf.md` §7 ist nicht gebaut, eine Tabelle `course_answer` gibt es nicht). |
| Medien vorher · dabei · bei … · nachher | An Übung, Planübung und Plan: `Media.wann`/`oft`/`bei`/`rolle`, Stellen aus `core/medien_stellen.py`, fällig nach `core.material.Lage`; der Fokus blendet Fälliges ein (`ui/components/fokus.py:490`). | **Der Testlauf zeigt gar kein Material** (`grep -n "material\|faellig" ui/views/kurs_testlauf.py`: kein Treffer) — auch nicht das der Übung. Der Block `test` hat keine Medien; im Kapitel gibt es nur den Block `medium` davor oder danach. |
| Werte speichern, später verwenden | Der Eintrag des Laufs hält alles (Wdh., Zeit, Skala, Ausführung). Als **Variable** (`course_variable`, Migration 065/066) bleibt nur **ein** Wert: der des Felds `Block.feld`; einziger Abnehmer ist das Ziel einer Planübung (`ziel_aus` × `faktor`, mit „Wert für den Plan“ ganz · Anteil · von Hand). | Die anderen Werte des Laufs sind im Kurs nicht benennbar; Ja/Nein und Auswahl passen nicht in `value REAL`; Antworten gibt es als Variable nicht; die Person sieht ihre Werte nirgends gesammelt. |

## 2. Leitidee: ein Baustein „Übung machen“, vier Einstellungen

Kein neuer Lauf, keine zweite Ansicht: Der gestaltete Test wird zu **„Übung machen“** — derselbe
Lauf, dieselbe Route, derselbe Eintrag. Neu sind vier Einstellungen, jede mit Vorgabe, jede
überschreibbar (Leitbild §16 des Vertrags: Eingänge, Ausgang, Vorgaben).

| Einstellung | Vorgabe | Wahl |
|---|---|---|
| **Wozu** (`zweck`) | `test` — bestehende Kurse bleiben, wie sie sind | `eindruck`: nur ausprobieren |
| **Medien** (`medien`, `wie_uebung` + `material`) | keine (wie heute) | eigene Stücke an vier Stellen · „wie die Übung“ |
| **Fragen** (`fragen`) | keine | Fragen vorher oder nachher, Arten wie im Ablauf |
| **Was weitergeht** | alle Werte und Antworten werden Variablen; verwendet wird nur, was ein Baustein nennt | — |

**Eindruck oder Test** unterscheidet nur, was *nach* dem Lauf geschieht:

| | Eindruck | Test |
|---|---|---|
| Lauf, Uhr, Takt, Ausführung, Medien, Fragen | gleich | gleich |
| Eintrag bei der Übung | ja (Frage 2) | ja, wie heute |
| Werte und Antworten als Variablen | ja | ja |
| Karte „Wert für den Plan“ | nein | ja, wie heute |
| hält „Plan anlegen“ auf, bis gemacht | nein — freiwillig (Frage 3) | ja, wie heute |
| Ergebnis-Seite | „Eintragen und zurück“, „Nochmal“, „Verwerfen“ | wie heute |

Im Paket bleibt `art = "test"` (kein Kurs von heute ändert sich, alte Apps lesen bestehende
Pakete weiter); der Editor nennt den Block „Übung machen“ mit dem Schalter „Nur ausprobieren ·
Als Test“. Ein Block mit `zweck = "eindruck"` braucht kein `feld`.

## 3. Medien am Lauf — dieselben vier Stellen wie im Ablauf

- **Daten:** `Block.medien: list[Media]` am Block `test` — dasselbe `Media` wie an der Planübung,
  also `wann` (leer = vorher · `nachher` · `bei`), `rolle` (Begleitung = dabei), `oft`, `bei`
  (`Ereignis`: Abschnitt · Satz · Zeit · Wdh. · Antwort), `abschnitte`. Dazu in `wie_uebung` der
  Wert `material`: Der Lauf zeigt das Material der Übung, wie sie eingestellt ist. Eigene Stücke
  kommen dazu (wie die Planübung zur Übung, `core.material.material_von`).
- **Rechnung** (flet-frei): `core.medien_stellen.block_stellen(block, uebung)` neben
  `stellen_von`/`plan_stellen` — gleiche Namen („Vorher · Dabei · Bei … · Nachher“), gleiche
  Ordnung; `core.material` bekommt den Weg „Material eines Blocks“. Fällig rechnet weiter nur
  `Material.faellig(Lage)` — aus Uhr, Zählung und Wahl, nie aus Messwerten.
- **Im Lauf** (`ui/views/kurs_testlauf.py`), je Zustand eine Stelle:
  - *bereit* — „Vorher“: Erklärungen stehen auf der Seite vor dem Start; was `zeigen`/`oft` von
    selbst öffnet, öffnet sich auf den Tipp „Übung starten“ im Kapitel — nie beim Aufbau der
    Ansicht (Geister-Dialog). Ein Lauf mit Medien „vorher“ zeigt darum immer erst *bereit*.
  - *läuft* — „Dabei“: Begleitung wie im Fokus; „Bei …“: Fälliges wird eingeblendet, Späteres
    bleibt verborgen. Das Stück Code, das im Fokus die `Lage` baut und Fälliges einblendet
    (`fokus.py:490–508`), wird dafür herausgelöst und von beiden benutzt.
  - *Ergebnis* — „Nachher“: nach „Eintragen“, wenn die Ansicht neu steht (wie
    `ui/einheit._medien_nachher`); „bei der Antwort …“ nach der Antwort auf eine Frage des Laufs.
- **Editor:** im Dialog des Blocks eine Zeile „Medien“ mit den vier Stellen und ihrer Anzahl;
  Tipp öffnet das Blatt „Medien an dieser Stelle“ und das eine Menü „Medium hinzufügen“
  (`components/medium_dazu.py`) — dieselben Teile wie im Reiter „Ablauf“. Der Block `medium`
  bleibt für Medien, die im Kapiteltext stehen.
- **Regeln bleiben:** Medien aus Dateien reisen nur bereinigt im Paket; Verkleinern, „gesehen“
  nur auf dem Gerät; kein Video außerhalb seiner Ansicht.

## 4. Fragen am Lauf — und im Kapitel — mit denselben Arten wie im Ablauf

- **Arten:** Skala (von–bis) · Ja/Nein · Auswahl mit einer · Auswahl mit mehreren Antworten —
  die drei Arten von `core.ablauf.Frage` (P221), dieselben Bedienteile wie im Workout. Eine
  Auswahl ohne eigene Antworten ist ein Hinweis mit „Weiter“. Eine Zahl wird nicht erfragt: Die
  Zahl für den Plan nennt die Person in „Wert für den Plan → Von Hand“.
- **Am Lauf:** `Block.fragen`, je Frage `wann` = `vorher` (auf der Seite *bereit*) oder `nachher`
  (im Ergebnis, vor „Eintragen“; Vorgabe). Die Skala der Anstrengung bleibt, was sie ist — ein
  Feld des Eintrags.
- **Im Kapitel:** Der Block `frage` bekommt dieselben Arten; die heutige Form (Antworten mit
  `richtig`/`hinweis`) bleibt gültig und unverändert in der Anzeige.
- **Gespeichert** wird jede Antwort als Variable des Kurses (§5) — Selbstauskunft, nur auf dem
  Gerät, nicht in Paket, Export oder Sync. Das ist Stufe 3 des Vertrags (Ben, 16.11.2026: ja).
  Die Zeile „nichts wird gespeichert“ im Docstring und in `plan_kurse.md` §7 gilt dann nicht mehr.
- **Nachdenklich machen** heißt: Eine Antwort **darf** etwas zeigen (§6, `wenn`), sie muss
  nichts bewirken. Bewertet wird nichts.

## 5. Variablen: alles, was eingegeben wurde, bleibt benennbar

- **Namen.** Heute: `<block>` (bei „die gewählte“ `<block>:<übung>`) = der Wert des einen Felds.
  Das bleibt als „der Wert des Tests“. Dazu je Lauf:
  `<block>.<feld>` für jedes Feld des Eintrags (Wdh., Zeit, Haltezeit, Skala, Ja/Nein,
  Gewicht, Variante, Seite …) und `<block>.f:<frage>` für jede Antwort; bei „die gewählte“ mit
  `:<übung>` wie heute. Ein Block `frage` im Kapitel: `<block>`.
- **Werte.** Zahlen wie heute (`value`; je Feld die eine Zahl, die `wert_im_test` daraus liest);
  Ja/Nein als 1/0; Auswahl, Variante, Seite als Text — neue Spalte `text` (mehrere Antworten als
  JSON-Liste). **Migration** (nächste freie Nummer, heute 074; vor dem Zusammenführen gegen
  `main` prüfen): `ALTER TABLE course_variable ADD COLUMN text`, keine zweite Tabelle — eine
  Antwort ist ein Ausgang wie der Testwert (§16.2 Punkt 4 des Vertrags). Gerätelokal wie bisher.
- **Gesetzt** beim „Eintragen“ aus dem Eintrag des Laufs (alle Felder auf einmal), bei einer
  Frage mit der Antwort; „Nochmal“ überschreibt, „Von vorn beginnen“ löscht — wie heute.
- **Sichtbar für die Person:** auf der Kursseite eine Karte „Deine Werte“ — je Kapitel, was
  gemacht und geantwortet wurde, mit Datum; Tipp führt zum Eintrag. Nur Zahlen und eigene
  Worte, keine Wertung.
- **Sichtbar im Editor:** bei „Ziel aus …“ und bei `wenn` die Liste der Variablen des Kurses mit
  Baustein und Kapitel (Stufe V Punkt 5 des Vertrags, Skizzen W1/W2 stehen noch aus).

## 6. Was eine Variable bewirken kann

Nichts ändert sich am Plan ohne Tipp — alles hier läuft über „Plan anlegen“ bzw. die
Sammelkarte „Das ändert sich an deinem Plan“.

1. **Werte übernehmen** (gebaut für ein Feld): `ziel_aus` nennt künftig auch ein Feld
   (`<block>.<feld>`), ein Baustein darf mehrere Felder auf einmal setzen (`ziel_aus` als
   Zuordnung Feld → Variable) — „Wdh. und Gewicht aus dem Test“. `faktor` und „Wert für den
   Plan“ gelten je Zahl wie heute; Text (Variante, Seite) wird ganz übernommen.
2. **Eine Frage bestimmt das Ziel:** Am Test darf eine Frage „den Anteil bestimmen“ — je Antwort
   ein Anteil („leicht“ 100 % · „mittel“ 80 % · „schwer“ 60 %; bei einer Skala je Bereich). Die
   Antwort **wählt nur vor**, was die Karte „Wert für den Plan“ zeigt; die Person sieht die Zahl
   („Der Plan nimmt 18 Wdh.“) und kann sie ändern (W3). Keine neue Mechanik am Plan.
3. **`wenn` an jedem Block und Baustein** (ersetzt die drei Folgen `zeige`/`baustein`/`weg` aus
   §4 des Vertrags durch einen Mechanismus): „Antwort A der Frage F“ · „Übung U gewählt in
   Auswahl W“ · „Variable ab/bis w“. Ein Text oder Medium mit `wenn` erscheint erst dann; ein
   Baustein mit `wenn` steht nur dann in der Sammelkarte. Mehrere Bedingungen gelten zusammen.
   Rechnung flet-frei in `core/kursbloecke.py` (`sichtbar(block, variablen, wahl)`).
4. **Später** (Stufe V des Vertrags, unverändert offen): Auslöser eines Wegs und Dauer eines
   Timers aus einer Variable.

## 7. Regeln und Recht

- **Nie aus Messwerten.** Variablen kommen aus Einträgen, Selbstauskunft und eigener Wahl;
  keine Variable aus Herzfrequenz oder HRV (wie §16.2 des Vertrags).
- **Warnung zu §6 Punkt 2 und 3** (Einschätzung Claude; `docs/recht/00_zweckbestimmung.md` in
  dieser Sitzung nicht neu gelesen, ungeprüft): Eine Frage nach **Beschwerden** („Schmerz 0–10“),
  deren Antwort das Ziel senkt oder „lieber weglassen“ einblendet, ist näher an einer
  Handlungsempfehlung als eine Frage nach der Anstrengung. Im Rahmen bleibt es, solange die
  Antwort nur vorwählt, die Person die Zahl sieht und selbst bestätigt, und die App nichts
  deutet — der Wortlaut der Frage gehört der Kursautorin. Der Editor sollte an einer Frage, die
  ein Ziel bestimmt, einen Satz dazu zeigen. Vor dem Bau von Stufe 4 die Zweckbestimmung lesen.
- **Paket:** neue Felder (`zweck`, `medien`, `fragen`, `wenn`, `ziel_aus` mit Feld) brauchen
  die nächste Formatversion (heute `FORMAT_VERSION = 7`, `core/pakete.py:93`) — nur für Pakete,
  die sie nutzen; `trainingsapp-paket pruefen` meldet Unbekanntes, `wenn` auf etwas, das erst
  später entsteht, und Medien mit Ortsangaben. Update-Stufe: P211 gilt mit.
- **Web-Fassung:** keine neue Abzweigung erwartet; kommt eine, gehört sie ins Register
  `docs/web_abzweigungen.toml`.

## 8. Fragen an Ben (Katalog P229) — beantwortet am 23.11.2026, siehe §10

1. **Ein Baustein statt zwei?** „Übung machen“ mit dem Schalter „Nur ausprobieren · Als Test“
   (§2) — oder ein eigener Block „Übung ausprobieren“ neben „Test“? Empfehlung: ein Baustein.
2. **Zählt „ausprobiert“ als gewöhnlicher Eintrag** (Tagesbilanz, Verlauf der Übung, „heute
   gemacht“)? Empfehlung: ja — gemacht ist gemacht, „Werte gehören der Übung“; „Verwerfen“
   bleibt. Alternative: nur als Variable des Kurses, ohne Eintrag.
3. **Freiwillig oder Pflicht?** Hält ein „Eindruck“ das Kapitel auf, bis er gemacht ist?
   Empfehlung: Vorgabe freiwillig, Schalter „muss gemacht sein“ am Block.
4. **Antworten ins Tagebuch?** Empfehlung: nein — nur „Deine Werte“ im Kurs (§5); wer etwas
   festhalten will, schreibt eine Notiz.
5. **Ziel aus einer Frage** über die Vorwahl in „Wert für den Plan“ (§6 Punkt 2) — reicht das,
   oder soll eine Antwort auch ein festes Ziel setzen können („schwer → 8 Wdh.“)?
6. **`wenn` als einziger Mechanismus** (§6 Punkt 3) statt der drei Folgen aus §4 des Vertrags?
7. **Reihenfolge** (§9): Empfehlung U1 → U2 → U3 → U4; U2 (Medien) ist unabhängig und kann
   zuerst kommen, wenn das drängt.

## 9. Stufen (gebaut wird auf Bens Wort, große Stufen im eigenen Worktree)

| Stufe | Inhalt | Stellen | Prüfung |
|---|---|---|---|
| U1 | **Ausprobieren + alle Werte als Variablen:** `zweck`, `fertig` ohne Eindruck, Ergebnis-Seite ohne „Wert für den Plan“; Migration `text`; Variablen je Feld; Karte „Deine Werte“ | `core/kursbloecke.py`, `core/kurstest.py`, `data/kurse.py`, `ui/views/kurs_testlauf.py`, `ui/views/kurse.py`, `ui/components/kursblock.py`, Editor (`core/kursbau.py`, `ui/views/kurs_bearbeiten.py`) | Doctests, `tests/test_kurse.py`, `tests/test_ui_kursbloecke.py`, `tests/test_migrationen.py`; Web-Fotos |
| U2 | **Medien an vier Stellen im Lauf:** `Block.medien`, `material` in `wie_uebung`, `block_stellen`, Fälliges aus dem Fokus herausgelöst, Editor-Zeile „Medien“ | `core/medien_stellen.py`, `core/material.py`, `ui/components/fokus.py`, `ui/components/material.py`, `ui/views/kurs_testlauf.py`, Editor, `core/pakete.py`, Paketwerkzeug | Doctests, Tests des Fokus bleiben grün, Web-Fotos; Gerätetest (Video im Lauf) |
| U3 | **Fragen:** Arten wie im Ablauf am Block `frage` und am Lauf (vorher/nachher), Antworten als Variablen, Medium „bei der Antwort“ | `core/kursbloecke.py`, gemeinsames Bedienteil mit dem Workout, `ui/views/kurs_testlauf.py`, `ui/components/kursblock.py`, Editor | Doctests, UI-Tests; Web-Fotos |
| U4 | **Folgen:** `wenn`, Frage bestimmt den Anteil, `ziel_aus` mit Feld und mehreren Feldern, Variablenliste im Editor | `core/kursbloecke.py`, `core/kursplan.py`, `core/kursvorschau.py`, Editor, Paketwerkzeug | Doctests, `tests/test_kurse.py`; vorher Zweckbestimmung lesen (§7) |

Je Stufe: Tests zuerst für die flet-freie Rechnung, dann die Ansicht, Web-Fotos, Gerätetest im
Katalog, Vertrag (`plan_kurs_ablauf.md` §7, `plan_kurse.md` §7, `uebungspakete.md`) nachführen.
Voller Testlauf vor dem Zusammenführen (Migration, Modelle in `core/`).

## 10. Bens Antworten (23.11.2026) und was daraus folgt

### 10.1 Antworten auf §8

| Frage | Antwort | Folge für den Plan |
|---|---|---|
| 1 Ein Baustein? | **Ein Baustein.** Die Übung wird vorher eingestellt (Parameter, Varianten, Medien …); vorher ist benannt, welche Variablen mitgehen, welche Fragen kommen, welche Auswirkung auf den Plan. „Je weniger zusätzliche Einstellungen nötig sind, desto besser.“ | Der Dialog des Bausteins zeigt drei Zeilen, die sich **aus dem Kurs ergeben** statt eingestellt zu werden: „Geht mit“ (alle Werte, ohne Wahl), „Fragen“, „Wirkt auf den Plan“ (welche Bausteine ihn verwenden). Kein Schalter `zweck` — siehe 3. |
| 2 Eintrag? | Ergebnisse einer Übung kommen ins Tagebuch (aus Antwort 4). Bei „Nochmal“ mehrere Einträge. | Jeder Lauf ist ein gewöhnlicher Eintrag; die Variable hält den jüngsten. |
| 3 Freiwillig oder Pflicht? | **Freiwillig als Vorgabe. Pflicht, wenn der Wert gebraucht wird** — „Planke → Haltezeit messen. Das wird ganz / anteilig / manuell der neue Zielwert.“ | **Abgeleitet, nicht eingestellt:** Nennt ein Baustein den Wert (`ziel_aus`), ist der Lauf ein Test — Pflicht vor „Plan anlegen“, mit der Karte „Wert für den Plan“ (Ganz · Anteil · Von Hand, wie heute). Sonst ist er ein Eindruck. `zweck` aus §2 entfällt als Feld; Rechnung `core.kursbloecke.gebraucht(block, bloecke)`. Offen: 10.4 Punkt 1. |
| 4 Antworten ins Tagebuch? | Antworten in den Kurs; Ergebnisse der Übung ins Tagebuch. | wie §5: Karte „Deine Werte“ im Kurs. |
| 5 Ziel aus einer Frage | „Eine Antwort soll ein festes Ziel setzen können, aber manuell.“ | Gelesen als: Die Autorin trägt je Antwort einen festen Wert ein; die Person sieht ihn in „Wert für den Plan“ **vorgewählt unter „Von Hand“** und kann ihn ändern — nichts ohne Tipp. Offen, ob so gemeint: 10.4 Punkt 2. |
| 6 `wenn` als einziger Mechanismus | „Wenn es sich lohnt, ja.“ | Es lohnt sich — 10.3. |
| 7 Reihenfolge | aus den Antworten ermitteln | 10.5. |

### 10.2 Antworten auf die Nachfragen

- **Fragen mit Folge, ganz allgemein** (auch nach Beschwerden): „Es wird etwas gefragt, das hat
  eine Folge. Plan ändern, Medium abspielen usw.“ Die App kennt keine Beschwerde-Frage, nur
  Frage → Antwort → Folge. **Einordnung** (`docs/recht/00_zweckbestimmung.md`, Zeilen 114–127
  und 156–169, am 23.11.2026 gelesen): Den Rahmen gibt es schon — „Vorschlag an einer Frage im
  Workout“ (17.11.2026): nur Selbstauskunft, die App nennt die Regel und deutet nichts, Frage
  und Antworten sind Worte der Autorin, der Plan ändert sich nur auf Tipp. Im selben Rahmen
  bleibt die Kurs-Frage, wenn (a) die Folge in der Sammelkarte als Zeile mit ihrem Grund steht
  („weil du ‚schwer‘ geantwortet hast“) und einzeln abwählbar ist, (b) die App die Antwort
  nirgends bewertet. **Warnung bleibt** für das Umfeld (Zeile 156–169): Ein Kurs, der sich an
  Beschwerden richtet und aus der Antwort das Training senkt, rückt die App als Ganzes näher an
  eine medizinische Zweckbestimmung — das entscheidet der Kurstext, nicht dieser Mechanismus.
- **Mehrfachauswahl:** Jede Antwort darf ihre eigene Folge haben; sind mehrere gewählt, gelten
  die Folgen aller gewählten („A ist dabei“).
- **„Katalog an Ereignissen, mit denen sich der Plan steuern lässt“ — gibt es schon, es fehlt
  nur die Bedingung.** Die Bausteine am Kursplan (`core/kursbloecke.py:64–66`, Zeilen der
  Sammelkarte `core/kursplan.py:91–98`) können heute: Übung hinzufügen (fest oder „die
  gewählte“, hinter einer Marke) · Ziel setzen (fest oder aus einem Test × Faktor) · Parameter
  wählen · Timer · Takt · Übergang hart/weich · Pause ohne Timer · Weg zwischen zwei Übungen.
  **Es fehlt:** (a) die Bedingung `wenn` an Block und Baustein, (b) Übung **herausnehmen** oder
  **tauschen**, (c) Variante setzen als eigene Zeile (`grep -n variant core/kursplan.py
  core/kursbloecke.py`: kein Treffer; ob sie über `ziel` mitgeht, ist nicht nachgestellt).
- **Mehrere Einträge bei Wiederholung:** ja. **„Von vorn beginnen“:** Variablen weg, Läufe bleiben.
- **Einmalige Übung im Katalog:** erst einmal ja, wie jede andere.
- **Backup:** Die Werte **sind** in der Datenbank (`course_variable`, Migration 065), und das
  Geräte-Backup nimmt die ganze Datenbank mit (`core/sicherung.py`, Android Auto Backup,
  Vorgabe aus, einschaltbar). „Gerätelokal“ heißt nur: nicht in Paket, Export oder Sync. Die
  Nachfrage war unbegründet — nichts zu tun.
- **Formatversion:** Ein Paket mit den neuen Feldern trägt die nächste Formatversion; eine
  ältere App lehnt es ab, der Kurs muss aktualisiert werden (App-Update).

### 10.3 `wenn` — ein Mechanismus, geschrieben von der Frage aus

Gespeichert wird die Bedingung am Block oder Baustein, der von ihr abhängt (`wenn`, §6 Punkt 3).
**Im Editor** legt die Autorin sie von der Frage aus an: an jeder Antwort „+ Folge“ →
„Text oder Medium zeigen“ · „Plan ändern“ (ein Baustein aus dem Katalog oben) · „Ziel
vorschlagen“. So braucht es keine eigene Einstellung „Bedingung“; wer einen Baustein öffnet,
sieht oben „nur wenn: Frage … = …“ und kann es dort lösen.

**Fehlt die Antwort** (die Frage hängt an einem freiwilligen Lauf, den die Person ausgelassen
hat): Beispiel — Kapitel 2 lässt den Seitstütz ausprobieren und fragt danach „Wie war das? leicht
· mittel · schwer“; Kapitel 3 bringt den Seitstütz nur bei „leicht“ in den Plan. Wer den Lauf
ausließ, hat keine Antwort. Vorschlag: Die Zeile steht in der Sammelkarte als **offen** („Probier
zuerst den Seitstütz aus“, Stand `OFFEN`, den es für fehlende Wahl und fehlenden Test schon
gibt) — nicht verborgen, nicht Pflicht. Texte und Medien mit `wenn` bleiben verborgen.

### 10.4 Was offen war — beantwortet in §11.3

1. **Test = „wird gebraucht“** (10.1 Antwort 3): Ein Test eines bestehenden Kurses, dessen Wert
   kein Baustein nennt, würde vom Pflicht-Test zum freiwilligen Eindruck. Ob es das in den
   Kursen von `trainingsapp-inhalte` gibt, ist nicht nachgesehen. Ausweg: am Baustein der
   Schalter „muss gemacht sein“ (Vorgabe aus), den der Import für solche Tests setzt.
2. **Festes Ziel je Antwort** (Antwort 5): als Vorwahl „Von Hand“ richtig gelesen?
3. **Übung herausnehmen / tauschen, Variante setzen** als Folge — gebraucht? (Neue Bausteine,
   eigene Stufe U5.)
4. **Seite „bereit“:** erst Medien „vorher“, dann Fragen „vorher“, dann „Starten“ (Skizze B1).
5. **Fehlende Antwort** als „offen“ in der Sammelkarte (10.3).

### 10.5 Reihenfolge (überholt durch §11.4)

**U1 → U3 → U4 → U2** (statt U1 → U2 → U3 → U4):

- **U1** zuerst: Lauf ohne Testpflicht, alle Werte als Variablen, „Deine Werte“ — darauf baut alles.
- **U3** (Fragen, Antworten als Variablen) und gleich danach **U4** (Folgen: `wenn`, „+ Folge“
  an der Antwort, Ziel aus Antwort, `ziel_aus` mit Feld): Das ist der Kern von Bens Antworten —
  „es wird etwas gefragt, das hat eine Folge“. U3 allein fragt, ohne dass etwas folgt.
- **U2** (Medien an vier Stellen im Lauf) zuletzt: Nichts anderes hängt daran, es löst Code aus
  dem Fokus heraus (das größte Risiko für Bestehendes) und braucht einen Gerätetest. Das
  Medium „bei der Antwort“ im Lauf wandert von U3 nach U2; im Kapitel geht es schon mit U4
  (Block `medium` mit `wenn`). Drängen die Videos im Lauf, kann U2 ohne Umbau vorgezogen werden.
- **U5** nur bei Ja zu 10.4 Punkt 3.

## 11. Zweite Runde (Ben, 23.11.2026, nach den Skizzen)

### 11.1 Der Lauf ist der Fokus

Ben: „Übungen (als nur Üben oder Test) sollen im Fokusmodus laufen. Man kann also einstellen,
ob nebenbei die Sensoren laufen. Ein Sensor soll auch als notwendige Startbedingung gesetzt
werden können.“ · „Parameter, Uhr, Medien werden voreingestellt und am besten wird die gleiche
Übungsumgebung gewählt wie der Fokusmodus, einfach um Vertrautheit zu schaffen.“

- **Heute:** Der Testlauf ist eine eigene Ansicht (`ui/views/kurs_testlauf.py`), die vom Fokus
  nur die Abschnittsleiste und die Ausprägungszeilen nimmt (Zeilen 128–129). Die Komponente
  Fokus (`ui/components/fokus.py`: große Zeit, Takt, Bild der Bewegung, HF-Kachel, Kurven,
  Zählstand des Sensors, Medien) benutzen nur der Timer der Übung und das Workout.
- **Künftig:** Der Lauf aus dem Kurs — ausprobieren wie Test — läuft **in derselben
  Fokus-Komponente** wie die Übung sonst: dieselben Ebenen (Takt · Bewegung · HF · Kurve),
  dieselben Knöpfe, dieselbe Eingabe am Ende. Damit ersetzt das den Weg aus §3 („Fälliges aus
  dem Fokus herauslösen“): Die Medien an den vier Stellen zeigt der Fokus selbst, der Kurs
  reicht ihm nur das Material des Blocks. Aus dem Kurs kommen dazu nur die Seite *bereit*
  (Hinweis, Medien und Fragen vorher) und das *Ergebnis* (Fragen nachher, „Wert für den Plan“).
- **Voreingestellt** aus dem Baustein, wie heute: Parameter, Uhr, Takt, Medien — Vorgabe „wie
  die Übung eingestellt ist“ (`wie_uebung`), eine eigene Angabe im Baustein geht vor.
- **Sensoren nebenbei:** Am Baustein eine Zeile „Sensoren“ mit der Vorgabe „wie sonst“ — läuft
  eine Messung, läuft sie weiter und der Fokus zeigt sie (HF, Kurven, Zählstand), wie beim Üben
  außerhalb des Kurses. Kein neuer Schalter für die Person.
- **Sensor als Startbedingung:** `Block.braucht` — eine Liste aus Herzfrequenz · RR-Intervalle ·
  Bewegungssensor (zählen). Fehlt einer, zeigt die Seite *bereit* „Dafür brauchst du … —
  verbinden“ und „Starten“ bleibt aus. Vorgabe: leer.
- **Grenze bleibt** (§7): Der Sensor läuft mit und zeichnet auf; **Variablen des Kurses kommen
  weiter nur aus dem Eintrag** (auch gezählte Wiederholungen, die der Sensor statt der Person
  zählt — das ist der Wert des Eintrags), nie aus Herzfrequenz oder HRV, und keine Folge hängt
  an einem Messwert. Eine Startbedingung „Sensor verbunden“ ist keine Rechnung aus Messwerten.
- **Nicht gelesen:** `ui/views/uebung_timer.py` und wie der Fokus dort gebaut und beendet wird,
  `ui/views/kurs_testlauf.py` im Ganzen. Ob der Kurslauf die Fokus-Komponente selbst einbaut
  oder die Ansicht „Timer der Übung“ mit einem Kurs-Kontext öffnet, entscheidet sich beim Lesen
  — vor dem Bau der Stufe F, mit Bericht an Ben.

### 11.2 Medien je Antwort

- Ein Medium darf an **mehreren Antworten** hängen: `wenn` nennt eine Liste von Antworten,
  eine davon genügt („leicht“ oder „mittel“ → Video 1; „schwer“ → Video 2). Im Editor: an der
  Folge „Medium zeigen“ die Antworten als Chips zum An- und Abwählen.
- **Eine Antwort ohne Folge ist der Normalfall** — der Tipp ist dann nur „ich mache mir die
  Anstrengung bewusst“; gespeichert wird sie trotzdem (§5).
- Ein Medium für alle braucht keine Bedingung: Es steht als Block `medium` im Kapitel darunter.

### 11.3 Antworten auf §10.4

1. **Test ohne Abnehmer:** kein Schalter. Der Editor **markiert** ihn nur („Kein Baustein
   verwendet diesen Wert“). Gelesen als: Der Lauf ist dann freiwillig wie jeder, dessen Wert
   nicht gebraucht wird — ob bestehende Kurse so einen Test haben, ist weiter nicht nachgesehen;
   vor Stufe U1 in `trainingsapp-inhalte` nachsehen und Ben das Ergebnis nennen.
2. **Festes Ziel je Antwort:** ja — vorgewählt unter „Von Hand“, änderbar.
3. **Übung herausnehmen, tauschen, Variante setzen:** gelesen als ja („alles, was irgendwie
   einen Plan modifizieren kann“, erste Runde) — neue Bausteine, Stufe U5.
4. **Seite „bereit“:** erst Medien, dann Fragen, dann „Starten“ — ja.
5. **Fehlende Antwort** steht als „offen“ mit dem Weg zum Ausprobieren in der Sammelkarte — ja.

### 11.4 Reihenfolge

| Stufe | Inhalt | hängt an |
|---|---|---|
| U1 | Ausprobieren ohne Testpflicht (abgeleitet), alle Werte als Variablen, Migration `text`, Karte „Deine Werte“, Markierung „kein Baustein verwendet diesen Wert“ | — |
| F | **Lauf im Fokus** (11.1): dieselbe Umgebung, Sensoren nebenbei, `braucht` als Startbedingung, Medien an vier Stellen am Baustein (ersetzt U2) | U1; vorher `uebung_timer.py` und `kurs_testlauf.py` lesen |
| U3 | Fragen vorher/nachher und im Kapitel, Antworten als Variablen | U1 |
| U4 | Folgen: `wenn` (auch mehrere Antworten), „+ Folge“ an der Antwort, festes Ziel je Antwort, `ziel_aus` mit Feld, „offen“ bei fehlender Antwort | U3 |
| U5 | Neue Bausteine: Übung herausnehmen, tauschen, Variante setzen | U4 |

F kommt vor den Fragen, weil Bens Vorgabe „dieselbe Umgebung“ die Ansicht festlegt, in die U3
seine Fragen und U4 seine Medien „bei der Antwort“ einbauen — sonst würden beide zweimal gebaut.
U1 bleibt davor: Es ändert nur die Ergebnis-Seite und die Daten, nicht den Lauf.

## 12. Gebaut (23.11.2026) — das gilt

Ben, 23.11.2026: „Setze den ganzen Plan um.“ Gebaut im Worktree `claude/kurs-uebungen`, Stufen
U1 · F · U3 · U4 · U5 — hier steht, was der Code tut. Wo es von §2–§11 abweicht, gilt dieser
Abschnitt.

### 12.1 Übung machen (U1)

- Der Block `test` heißt **„Übung machen“** (`core.kursbloecke.ARTEN`). Kein Feld `zweck`:
  Ein Lauf ist ein **Test**, wenn aus seinem Wert ein Ziel wird (`wert_wird_ziel` — ein
  Baustein nennt ihn in `ziel_aus`, oder das Kapitel hat Plan-Vorlagen); sonst „nur
  ausprobieren“: Karte „Übung machen · freiwillig“, Knopf „Übung starten“, Ansicht
  „Ausprobieren · …“, keine Karte „Wert für den Plan“, und „Plan anlegen“ wartet nicht auf ihn
  (`fertig(…, ziel_tests)`). Der Editor zeigt unter dem Baustein „Ergibt sich aus dem Kurs“
  (`abnehmer`): wie viele Bausteine den Wert nehmen — oder „Kein Baustein verwendet diesen
  Wert“. In `trainingsapp-inhalte` gibt es keinen Kurs mit einem Test
  (`grep -rn 'art = "test"' --include=*.toml`: kein Treffer) — kein Bestand ändert sich.
- **Alle Werte als Variablen** (Migration 074, Spalte `text`): mit „Eintragen“ je Feld des
  Eintrags `<test>.<feld>` (`KursRepo.feldwerte_setzen`, `core.kursbloecke.feldwerte`: Zahlen,
  bei Sätzen der beste, Ja/Nein als 1/0, Text als Text). Ein Test ohne Lauf hinterlässt sie
  beim Abschließen des Kapitels. „Nochmal“ ersetzt, „Von vorn beginnen“ löscht — die Einträge
  bleiben.
- **„Deine Werte“** auf der Kursseite (`core/kurswerte.py`, `views/kurse._deine_werte`): je
  Kapitel die Läufe mit ihren Feldern, bei einem Test der Wert für den Plan, darunter die
  Antworten. Der Tipp auf einen Lauf führt zu **seinem Tag** (`/tag/<datum>`), nicht zu einem
  einzelnen Eintrag.

### 12.2 Der Lauf (F)

- **Ebenen des Fokus im Lauf** — nicht der ganze Fokus-Bildschirm: Der Lauf behält seine Uhr,
  seine Vorgabe und seine Knöpfe (Skizzen T1–T4 vom 16.11.2026, 60 Tests hängen daran) und
  zeigt darunter aus **derselben Komponente** (`components/fokus.Fokus`) das Ebenen-Menü, das
  Bild der Bewegung, das Begleitvideo, die Herzfrequenz-Kachel, die Kurven und die Hinweise
  „bei …“. Sensoren laufen mit, wie sonst (der Lauf startet über `ui.uebung_lauf.starten`).
  **Überholt (25.11.2026): Der Lauf ist jetzt der Fokus-Bildschirm — §13.1.**
- **Sensor als Startbedingung:** `Block.braucht = ["messung"]` — „Herzfrequenz — ein Sensor
  ist verbunden“ (`Messlauf.verbunden`). Fehlt er, ist „Start“ aus und die Seite sagt, was
  fehlt (`kurs_testlauf.sensor_fehlt`). **Überholt (25.11.2026):** Der Satz „ob ein Gerät den
  Bewegungssensor liefert, lässt sich vor dem Start nicht sicher sagen“ stimmte nicht — das
  Geräteprofil sagt es (`components.zaehl_stand.geraet_kann_zaehlen`); §13.2.
- **Medien am Lauf:** `Block.medien` — vier Stellen wie an der Planübung (`core.kursbau`:
  `MEDIEN_STELLEN`, `medium_stelle`, `medium_an_stelle`): vorher (Zeilen auf der Seite
  „bereit“) · dabei (Begleitung im Lauf) · bei … Sekunden / Wiederholungen (Hinweis unter der
  Uhr) · nachher (Zeilen im Ergebnis). Sie kommen zu den Medien der Übung dazu
  (`material_item`, `Fokus(material_item=…)`). Kein Schalter „Material wie die Übung“ — die
  Medien der Übung zeigt der Lauf immer. „Bei Abschnitt/Satz“ stellt der Editor nicht ein
  (das Paket kann es: dasselbe `Media.bei`). Kein Medium öffnet sich von selbst.
- Ein Lauf mit Medien, Fragen oder Sensor ist immer ein **Lauf mit der Uhr** und öffnet sich
  „bereit“ (`Block.gestaltet`).

### 12.3 Fragen (U3)

- **Im Kapitel:** Der Block `frage` hat neben der Verständnisfrage (Antworten mit `*` und
  Hinweis, speichert nichts) die Arten des Ablaufs — Skala · Ja/Nein · Auswahl mit einer oder
  mehreren Antworten (`Block.frage`, `components/kursfrage.frage_karte`). Die Antwort wird
  gespeichert (`KursRepo.antwort_setzen`, Variable unter der Block-ID), die Ansicht zeichnet
  neu.
- **Am Lauf:** `Block.fragen`, je Frage vorher (Seite „bereit“, nach den Medien) oder nachher
  (im Ergebnis, vor „Wert für den Plan“). Gespeichert werden sie **mit dem Eintrag**
  (`<test>.f:<frage>`); „Verwerfen“ verwirft sie mit.
- Antworten stehen in „Deine Werte“, nirgends sonst — nicht im Tagebuch, nicht in Paket,
  Export oder Sync.

### 12.4 Folgen (U4)

- **`wenn`** an jedem Block und Baustein (`core.kursbloecke.Wenn`, `wenn_stand`): Frage,
  Antworten (eine genügt; bei mehreren Angekreuzten: eine ist dabei) oder Bereich einer Skala
  (`ab`/`bis`). Mehrere Bedingungen gelten zusammen. Auch ein Feld eines Laufs geht
  (`t.scale` ab 7) — der Editor bietet nur Fragen an.
  - Text, Medium, Frage, Übung machen, Auswahl: stehen im Kapitel nur, wenn die Bedingung
    gilt; fehlt die Antwort, bleiben sie verborgen.
  - Bausteine: bei der passenden Antwort eine Zeile der Sammelkarte mit ihrem Grund („… ·
    weil du ‚leicht‘ geantwortet hast“), bei einer anderen keine, ohne Antwort **offen** mit
    dem Weg dorthin („Dazu fehlt deine Antwort — probier zuerst … aus.“).
  - Was schon übernommen ist, bleibt im Plan, auch wenn die Antwort später anders lautet.
- **Festes Ziel je Antwort:** `Block.ziele` (im Editor „Antwort = 30“). Im Ergebnis wählt die
  Antwort „Wert für den Plan → Von Hand“ mit dieser Zahl vor, mit dem Satz „Vorgewählt, weil
  du … geantwortet hast“; die Person kann ändern. Nur an einem Lauf, dessen Wert gebraucht
  wird, und nur bei Ja/Nein und Auswahl mit einer Antwort.
- **`ziel_aus` mit Feld:** `ziel_aus = "<test>.<feld>"` nimmt die Zahl aus diesem Feld des
  Laufs und setzt das Ziel in diesem Feld. Mehrere Felder = mehrere Bausteine (keine
  Zuordnung an einem Baustein). Der Editor bietet es nicht an — nur das Paket.
- **Im Editor:** „Nur wenn“ an jedem Block und Baustein (`components/wenn_form.py`); „+
  Folge“ an einer Frage legt einen Text, ein Medium oder (im Kurs mit Kursplan) einen Baustein
  an, der die Bedingung auf die Frage schon trägt — bei welcher Antwort, wählt man in seinem
  Formular. **Abweichung von §10.3:** „+ Folge“ steht an der Frage, nicht an jeder Antwort.

### 12.5 Neue Bausteine (U5)

`plan_entfernen` (eine Planübung geht aus dem Plan; ihr Baustein bringt sie danach nicht
wieder) und `plan_tauschen` (die Planübung wird eine andere Übung, Ziel und Parameter beginnen
neu). **Variante setzen** ist kein eigener Baustein: Sie geht über „Einstellen → Ziel“, wenn
die Übung ein Feld Variante hat — nicht nachgestellt. **Überholt (25.11.2026): Es ging nicht;
jetzt geht es — §13.3.**

### 12.6 Paket, Recht, Prüfung

- **Formatversion 8** (`core.pakete.nutzt_uebung_machen`) nur für Pakete, die das Neue
  nutzen; eine ältere App lehnt sie ab. `trainingsapp-paket pruefen` meldet `wenn` ins Leere
  und unvollständige neue Bausteine als Fehler (`docs/uebungspakete.md`).
- **Recht:** `docs/recht/00_zweckbestimmung.md`, „Frage mit Folge im Kurs“ — Selbstauskunft,
  nichts ohne Tipp, die App deutet nichts; *nicht anwaltlich geprüft*.
- **Tests:** `tests/test_ui_kurs_fragen.py`, `tests/test_ui_kurs_test.py` (Lauf mit Fragen,
  Sensor, Ziel aus Antwort), `tests/test_kurse.py`, `tests/test_paket_kursplan.py`, Doctests
  in `core/kursbloecke.py`, `core/kursplan.py`, `core/kursbau.py`, `core/kurswerte.py`.
- **Web-Fotos** (412 × 860, 23.11.2026): Kapitel mit Frage, eingeblendetem Text und
  Sammelkarte mit Grund · Seite „bereit“ mit Medium und Frage vorher · Lauf mit den Ebenen
  des Fokus · Ergebnis · „Deine Werte“ · Dialog „Übung machen“ im Editor (dort zwei
  Layoutfehler gefunden und behoben: abgeschnittene Sensor-Zeile, überlaufendes Label).
  **Nicht am Foto geprüft:** Lauf mit verbundenem Sensor und Kurven, Begleitvideo, „bei …“,
  Ziel aus einer Antwort, die Blätter der neuen Bausteine, „Was soll folgen?“ — und nichts
  davon am Gerät (T156).

## 13. Dritte Runde (Ben, 25.11.2026) — das gilt

Bens Antworten auf die vier offenen Punkte aus §12: (1) Lauf ganz auf den Fokus-Bildschirm —
„ja“; (2) Bewegungssensor als Startbedingung — „ja. Wenn das verbundene Gerät keinen
Bewegungssensor bietet, soll eine Hinweismeldung das angeben“; (3) „+ Folge“ an der Frage statt
an jeder Antwort — „ok“; (4) Gerätetest T156 — „kommt später“.

**Durchsicht des Plans vor dem Bau** (gegen den Code, nicht gegen die Abschnitte): §2–§11 sind
Entwurf und Verlauf, §12 beschreibt den Stand vom 23.11. richtig bis auf die zwei in §12.2
markierten Stellen. Seit dem 23.11. gab es auf `main` keine Commits, die Kurs, Lauf oder Fokus
berühren (`git log 09ce162..` leer).

### 13.1 Der Lauf ist der Fokus-Bildschirm

`views/kurs_testlauf.py`, Zustand „läuft“ — gebaut wie der Fokus der Übung
(`views/uebung_timer.py`), aus derselben Komponente (`components/fokus.Fokus`):

- **Fest oben:** Takt · Zeit · Material · Ebenen in einer Zeile (`ZeitMitTakt`), der Balken
  der Abschnitte eines Timers, darunter die **Steuerzeile**: ⏸ (neu im Lauf des Kurses) · der
  Knopf, der den Lauf beendet („Fertig — 30 gemacht“, „Bei 7 angekommen“ …) · ✕. Endet der
  Lauf von selbst (Zeit, Timer), steht an der Stelle des Knopfs „Vorher aufgehört …“; sonst
  steht es als Erstes darunter. In der Titelleiste steht im Lauf der Pfeil zurück ins Kapitel
  (der Lauf läuft weiter), das ✕ nur noch im Ergebnis.
- **Worte des Laufs in der Uhr:** Mit der Stoppuhr zeigt die Zeit, was gelaufen ist (Vorgabe
  Zeit: den Rest), darunter „Zeit läuft · …“; mit einem Timer den Rest des Abschnitts und
  „Los · Runde 1 von 2“. Angehalten steht „· angehalten“ dabei.
- **Darunter, rollend:** die Vorgabe des Kurses (und wie die Übung gemacht wird), mit Timer
  „danach …“ und die Laufzeit, die Karte „Takt“ (nur der Text — die Anzeige steht neben der
  Zeit), die Marke der Anstrengung, „Sensor zählt“ mit der Zahl, dann die Ebenen des Fokus
  (Hinweise „bei …“, Video · Bewegung · Herzfrequenz, Kurven, Zählzeile mit ±1), die Karte
  **„Eintragen“** und — mit einem Timer — die Sätze.
- **„Eintragen“ im Lauf** (`components/fokus_eintragen.EintragenKarte`): Sätze („+10“, eigener
  Wert, „−“) und die Skala, wie im Fokus der Übung. Was dort getippt ist, **steht im Ergebnis
  schon da** (`anhalten`: Summe der Sätze, letzte Skala) und lässt sich dort ändern;
  eingetragen wird weiter **ein** Eintrag mit „Eintragen“ im Ergebnis. Nicht angeboten, was
  der Lauf festlegt: die Ausführung (steht mit dem Start), die Wiederholungen bei einer Menge
  als Vorgabe, die Skala bei einer Anstrengung als Vorgabe. Was der Sensor zählte, geht vor.
  Die Skala steht auch bei einer Übung ohne eigenes Skalenfeld da — das Ergebnis fragt sie
  ebenso.
- **Tempo-Regler** (Ben, 25.11.2026: „sollte immer dabei sein“): wie im Fokus der Übung,
  solange ein Takt läuft. Die Runden des Takts — der Vorschlag für die Wiederholungen —
  rechnen mit seinem Faktor am Ende des Laufs (`core.kurstest.takt_runden(…, tempo)`); wurde
  er mittendrin verstellt, ist die Zahl genähert, sie bleibt ein Vorschlag.
- **Nicht übernommen:** „Nächster“ (ein Abschnitt lässt sich im Lauf des Kurses nicht
  überspringen).
- Das Ergebnis und die Seite „bereit“ sind unverändert.

### 13.2 Bewegungssensor als Startbedingung

- `Block.braucht` kennt neben `messung` jetzt **`bewegung`** (`core.kursbloecke.BRAUCHT`):
  ein verbundenes Gerät mit Beschleunigungssensor (heute Polar H10 und Verity Sense;
  `geraet_kann_zaehlen` — verbunden genügt). Fehlt es, ist „Start“ aus und die Seite nennt,
  was fehlt.
- **Hinweis** (`kurs_testlauf.sensor_hinweis`): Ist ein Gerät verbunden, das keinen
  Bewegungssensor hat, steht über „Start“: „Dein verbundenes Gerät (‹Name›) hat keinen
  Bewegungssensor — damit lässt sich dieser Lauf nicht starten. Verbinde unter „Messung“ ein
  Gerät, das Wiederholungen zählen kann.“ Derselbe Satz kommt als Meldung, wenn der Start
  anderswo versucht wird.
- **Nur Startbedingung:** Der Lauf startet das Zählen nicht von selbst; zählt bei der Übung
  schon der Sensor, tritt die Uhr dem bei, wie bisher.
- **Vermerk (Ben, 25.11.2026): „Bewegungssensor muss ich erst testen, wie es funktioniert.“**
  Die Startbedingung ist gebaut, aber von Ben am Gerät noch nicht erprobt; ob sie so bleibt
  und ob der Lauf das Zählen selbst starten soll, entscheidet sich nach seinem Test (T156 i).
- **Editor:** zweiter Haken „Sensor nötig: Bewegungssensor“ im Dialog „Übung machen“.
- **Paket: Formatversion 9** (`core.pakete.nutzt_bewegungssensor`) nur für Pakete mit
  `braucht = ["bewegung"]` — eine App mit Version 8 ließe die Bedingung still fallen, darum
  lehnt sie die Datei ab.

### 13.3 Variante am Baustein

Ben, 25.11.2026: „Variante als Parameter muss mit gesetzt werden können.“ (§12.5 sagte „geht
über Einstellen → Ziel, nicht nachgestellt“ — nachgestellt: Es ging nicht, `Kurssicht.ziel_spec`
ließ die Variante immer weg.)

- **Festes Ziel:** Bei genau einer Übung gehört die Variante zu den Zielfeldern der Bausteine
  „Übung in den Plan“ und „Einstellen“. Bei einer Auswahl aus mehreren Übungen nicht — jede hat
  ihre eigenen Varianten.
- **Neben dem Ziel aus einem Test:** Unter „Ziel aus dem Test“ steht die „Ziel-Variante“
  (`Kurssicht.variante_spec`). Der Baustein trägt dann `ziel_aus` **und** `ziel = {variant = …}`;
  die Sammelkarte zeigt eine Zeile („Ziel für Käfer: auf Knien · 24 Wiederholungen“), ein Tipp
  setzt beides (`core.kursplan._ziel_aus_test`).
- **Paket:** `ziel` neben `ziel_aus` wird jetzt gelesen und geschrieben (bis 0.3.101 fiel
  `ziel` dann weg) — **Formatversion 9** (`core.pakete.nutzt_ziel_neben_test`). Im Paket darf
  dort jedes Zielfeld stehen, der Editor bietet nur die Variante an.

### 13.4 Prüfung

- Tests: `tests/test_ui_kurs_test.py` (Fokus-Bildschirm mit Steuerzeile, „Eintragen“ im Lauf
  steht im Ergebnis und ergibt einen Eintrag, ⏸, Bewegungssensor mit Hinweis),
  `tests/test_ui_kurs_fragen.py` (Editor), Doctests in `core/pakete.py`.
- Web-Fotos (412 × 860, 25.11.2026): Seite „bereit“ mit fehlendem Bewegungssensor · Lauf mit
  Vorgabe Zeit als Fokus-Bildschirm (Kopf, Steuerzeile, Vorgabe, HF-Kachel, Kurven,
  „Eintragen“); der Abstand unter der Steuerzeile danach behoben, nicht neu fotografiert.
  **Nicht am Foto geprüft:** die Ziel-Variante im Baustein-Blatt, der Tempo-Regler im Lauf, Lauf mit Timer (Balken, Sätze), mit Takt, mit
  Begleitvideo, der Hinweis bei verbundenem Gerät ohne Bewegungssensor (im Browser gibt es
  kein Bluetooth) — und nichts davon am Gerät (T156).
