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

**Stand: Plan, nichts gebaut.** Verhalten von Kursen ändert sich erst auf Bens Wort (§8 Fragen,
Katalog P229). Skizzen als Handy-Bilder folgen nach den Antworten, vor dem Bau.

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

## 8. Fragen an Ben (Katalog P229)

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
