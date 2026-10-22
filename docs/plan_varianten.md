# Plan: Varianten in der Übung, getrennt zählen, Einstellungen und Werte trennen

Stand 21.10.2026: **Gebaut** (Teile A–H), Gerätetest offen (T69).
- Entschieden: Reihe A ist abgenommen, mit einer Änderung bei A1 (nur das Symbol). Für
  die Trennung von Einstellungen und Werten ist **C1** gewählt. Ben, später am Tag:
  „D passt, B auch, P57 ja – bau es. P58: für die Parameterwahl, Variante ist ein eigener
  Bereich unterhalb der Parameter.“
- P58 gebaut als Abschnitt „Varianten in diesem Plan“ unter den Parametern (i-Seite und
  „Einstellen“) mit dem Schalter „Varianten beim Eintragen zeigen“; aus = `quick["variant"]
  == []` (`core.standards.varianten_schalten`). Seit 22.10.2026 (P79) nur noch in „Im Plan
  einstellen“ — die i-Seite gibt es nicht mehr.
- Weiter offen: Kurse (P59), Pakete (P60), Texte der alten Varianten (P61).

Skizzen: https://claude.ai/artifact/M37Kb79EDKgfcwDTHSkCnx

| Reihe | Bilder | Teile |
|---|---|---|
| A | A1–A6: Block, Blatt, Übungseinstellungen, Umbenennen, nachträglich | A–C, G |
| B | B1–B3: Tag, Kurve, Übungsliste | D–E |
| C | C0–C3: Einstellungen und Werte trennen; C1 gewählt | F |
| D | D1–D5: viele Varianten, Symbole, Kürzel, Beschreibung | H |

Anlass ist Bens Notiz „Übersicht und Kurven zu Übungen“ vom 21.10.:

> Varianten leichter ermöglichen als zusätzliche Tags. … Liegestützen: man kann kurze oder
> lange machen … in der Kurvenansicht im Verlauf werden kurze und lange getrennt
> dargestellt in der selben Kurve. … Es gibt Buttons die die Einstellungen bestimmten und
> solche, mit denen man Wiederholung+Zeit setzten kann. Das muss optisch getrennt werden.

Dazu seine Antworten vom selben Tag:

> Die Variante soll selbst gesetzt werden können oder wird über die Pakete geliefert. …
> lass die Pakete erstmal unberührt und konzentriere dich auf die Varianten.

> Varianten werden separat gezählt. Das ist vor allem im Tagebuch wichtig. Kurze
> Liegestützen lassen sich 400 in kurzer Zeit machen. 400 lange sind eine ganz andere
> Übung. … kurz+30, lang+15, kurz+30, dann wird kein zweiter Kurzeintrag angelegt, außer
> die Grundeinstellungen ändern sich. Gleiche Grundeinstellungen innerhalb einer
> bestimmten Zeit werden gesammelt, außer man klickt das irgendwie weiter.

**Pläne und Kurse ändern sich nur mit Bens Ja** (seine Setzung vom 21.10.).

- Freigegeben:
  - die Variantenzeile in **jeder Planübung**;
  - **Ablauf und Uhr** tragen die Variante ein;
  - das **Ziel** kann eine Variante vorgeben.
- Nicht freigegeben: die Variante aus der Parameterwahl der Planübung nehmen (P58).
- Kurse bleiben unverändert (P59).
- Pakete bleiben unverändert (P60).

| Teil | Was | Schicht |
|---|---|---|
| A | Variante = Ausprägungsfeld `variant` | `core/parameter`, `standards`, `tagesbilanz`, `plaene` |
| B | Variantenzeile, Knopf „Variante“ neben „Notiz“, Blatt, Übungseinstellungen | `ui/views/plan.py`, `uebung_bearbeiten.py`, `data/repositories` |
| C | Sammeln je Ausführung (mehrere offene Einträge) | `core/eintraege`, `SessionRepo`, `plan.py`, `ui/marken` |
| D | Getrennt zählen: Heute, Tag, Zeitleiste, Verlauf → Tage/Übungen, Tagebuch | `core/tag`, `core/verlauf`, Views |
| E | Verlauf: eine Kurve, eine Linie je Variante | `core/verlauf`, `verlaufskurve`, `verlauf_kachel`, `ui/farben` |
| F | Einstellungen und Werte trennen (C1 gewählt) | `ui/views/plan.py`, `spec_form` |
| G | Nachträglich, Uhr/Ablauf, Ziel | `leistungen`, `eintrag_formular`, `nachtragen`, `uebung_lauf`, `devices/einheit`, `plan_ablauf`, `plan_einstellen` |
| H | Viele Varianten: Symbol oder Kürzel, Beschreibung, Variantenzeile passt sich an (P62) | `core/parameter`, `core/result_spec`, neue `ui/components/variantenwahl.py`, `uebung_bearbeiten` |

---

## A. Variante = Ausprägungsfeld `variant` (keine Migration)

Es gibt schon die **Ausprägung** (`core/parameter.py`): Gewicht, Winkel und Auswahl
(`side`). Sie wird vorher gewählt, nie addiert und **trennt** Einträge. Eine Variante ist
genau das, nur mit eigenen Namen.

- Die Varianten einer Übung sind die `quick`-Werte eines CHOICE-Felds **`variant`**
  („Variante“) in `exercise.result_spec`. Das Feld steht **nicht** im `FELDVORRAT`, darum
  erscheint es nicht in der allgemeinen Parameterliste des Editors.
- Ein Eintrag trägt `result["variant"]`. Die Spec-Kopie enthält das Feld, also stimmt die
  Anzeige auch später, wenn die Übung sich geändert hat.
- Was dadurch schon funktioniert:
  - Bündel und Kachel trennen und schlüsseln auf.
  - Der offene Eintrag merkt, wenn die Variante nicht passt (`passt`).
  - Die Vorbelegung ist „wie zuletzt“ (`auspraegung_vorgabe`).
  - Die HRV-Marke heißt „Liegestütz lang: 15“.
  - SpecForm zeigt das Feld als SegmentedButton; Speichern ist eine Korrektur, der Eintrag
    bleibt unveränderlich.
  - Ein Paket kann Varianten schon heute über `result_spec` liefern.
- `core/parameter.py`: `VARIANTE`, `VARIANTE_FELD`, `varianten(spec)`,
  `mit_varianten(spec, namen)` (Feld vorn, bei leerer Liste entfernt), mit Doctests.
  - `kontextfelder`: Die Variante steht **immer** drin und zuerst. Die übrigen
    Ausprägungen kommen nur hinzu, wenn die Übung Mengen hat.
  - `leistungsfelder`: Die Variante ist nie selbst die Leistung.
- `core/tagesbilanz.ist_leistung`: Eine Variante allein ergibt „abgehakt (lang)“.
- `core/standards.py`:
  - `aktive_felder`: Hat die Übung Varianten, ist die Variante immer dabei, egal was
    `item.felder` sagt.
  - `chips_fuer`: liefert für `variant` die Liste der Übung.
  - Ziel: `ziel_spec` lässt die Variante zu, `auspraegung_vorgabe` nimmt sie aus dem Ziel,
    und „Wie geplant“ nennt sie.
  - `waehlbare_felder` und `planbare_felder` bleiben unverändert (P58).

## B. Übungsblock und Übungseinstellungen (A1–A5)

- **Variantenzeile** oben im Eingabebereich: ein Segment je Variante in einer Zeile. Ein
  Tipp wählt; ein zweiter Tipp auf dieselbe heißt „ohne“.
- **Etikett-Symbol** (`Icons.SELL`) neben „Notiz“, **ohne Text** (Ben, 21.10.). Die
  Bedeutung erklärt die Hilfedatei, erreichbar über das „i“ in der Titelleiste (Katalog
  A3). Der Tooltip und die Bildschirmleser-Beschriftung lauten „Variante: lang“. Ist eine
  Variante gesetzt, ist das Symbol getönt. Ein Tipp öffnet ein Blatt mit:
  - ohne / vorhandene Varianten;
  - „Neue Variante“ (wird in der Übung gespeichert);
  - einem Link „Varianten der Übung bearbeiten“.

  Wie die Notiz gilt die Wahl für den markierten Eintrag (Korrektur über
  `SessionRepo.variante_setzen`) und für alles danach. Ohne markierten Eintrag gilt sie
  nur für den nächsten.
- **Übungseinstellungen:** ein Abschnitt „Varianten“ nach den Parametern.
  - Chips mit ✕ entfernen eine Variante; die Einträge behalten sie.
  - „+ Variante“ legt eine an.
  - Tippen benennt um, mit dem Häkchen „auch die N bisherigen Einträge“. Das sind
    Korrekturen in einer Transaktion, ohne Häkchen bleibt der alte Name.
  - `stand()` nimmt die Liste auf (für „Zurück speichert“).
- Ohne Varianten ändert sich nichts: kein Chip, kein Segment (`test_ui_saetze.py`
  verlangt, dass im Plan kein `ft.Chip` steht).

## C. Sammeln je Ausführung (A3)

Ersetzt in `plan_eintraege_hrv.md` A2 die Zeile „Ausprägung geändert“, nach der der
nächste Wert den alten Eintrag schloss.

- **Mehrere** Einträge einer Übung können gleichzeitig offen sein, je **Ausführung**
  (Variante + Gewicht/Seite/Winkel) einer.
- **Markiert** ist der offene Eintrag mit der gewählten Ausführung. Ein Tipp geht dorthin;
  gibt es keinen, entsteht ein neuer. Die anderen offenen Einträge bleiben offen.
- „Abschließen“ schließt nur den markierten. Die übrigen schließen der Zeitabstand, der
  Tageswechsel oder ihr eigenes Abschließen.
- „Heute geleistet“ zeigt alle offenen Einträge. Ein Tipp auf einen nicht markierten
  wählt seine Ausführung. Im Kopf stehen die Summen je Variante.
- Betroffen:
  - `core/eintraege` (`offene`, `stand` je Ausführung);
  - `SessionRepo` (`offener_eintrag`, `ziel_eintrag`, `offene_schliessen`;
    `eintrag_fertig` schließt nur noch Einträge **derselben** Ausführung);
  - HRV-Abschnitte (`ui/marken`): Sie sollen sich nicht überlappen, ein Abschnitt gilt je
    Übung.
- Ob die Regel auch für Gewicht und Seite gilt (Vorschlag: ja, eine Regel), ist P57.

## D. Getrennt zählen (B1, B3)

- Wo ein Tag aufgelistet wird, hat jede Variante eine eigene Zeile mit eigener Zahl
  („Liegestütz · kurz 100“, „Liegestütz · lang 15“). Das betrifft `core/tag.gemacht`, die
  Zeitleiste, `core/verlauf.tageszeilen`, Verlauf → Tage und den Kartentitel im Tagebuch.
- Verlauf → Übungen: je Variante eine Zeile mit eigener Mini-Kurve und eigenem Trend; ein
  Tipp öffnet die Kurve (E).
- Gewicht und Seite bleiben wie heute in der Zeile („davon …“).

## E. Eine Kurve, eine Linie je Variante (B2)

- `/verlauf/<kachel>`: eine Linie je Teil (Übung + Variante); Einträge ohne Variante haben
  eine eigene Linie.
- Farbpunkt-Chips darunter blenden einzelne Linien aus. „Zusammen“, die bisherige
  Summenkurve, ist zuschaltbar und als Vorgabe aus.
- Das Dropdown „Variante“ (`state.verlauf_variante`) entfällt; verwandte Übungen werden
  ebenfalls Linien.
- „Training Nr.“ zählt über alle Linien gemeinsam.
- Umsetzung:
  - Kern `core/verlauf.linien(...)`;
  - `verlaufskurve.linie` nimmt mehrere Reihen;
  - Farben `linie_1..4` in `ui/farben.HELL/DUNKEL`, dabei gilt der Kontrasttest in
    `test_darstellung.py`.
- Die Kennzahlen oben gelten je Linie („Höchster · kurz“). Die Ergebnisse je Tag zeigen die
  Varianten untereinander.

## F. Einstellungen und Werte trennen (C0–C3): **C1 gewählt** (Ben, 21.10.)

Heute sind die Ausführungs-Chips (`auswahl_chip`) und die Wert-Chips („+10“) beide
`ft.Chip` in gleich umrandeten Kästen (`abschnitt`). „Eintragen“ hat dabei drei
Bedeutungen: Aufklappen, Abschicken und die Überschrift.

- **C1 Zwei Zonen** (Vorschlag):
  - Oben eine getönte Leiste „Ausführung“ mit Segmenten; ausgewählt heißt gefüllt mit
    Häkchen.
  - Darunter „Eintragen“ mit gefüllten „+“-Knöpfen (48 px) und Sätze × Wert.
  - „Abschließen“ wird umrandet.
- **C2 Eine Zeile mit ▾:** Die Einstellungen stehen als Auswahlknöpfe mit Menü in einer
  Zeile. Eine Variante wechselt man dann mit zwei Tipps statt einem. Der erste Knopf
  ersetzt den Knopf „Variante“.
- **C3 Nur Form:** Ordnung und Kästen bleiben. Die Auswahl wird zu Häkchen-Chips im
  getönten Kasten, die Werte zu gefüllten „+“-Knöpfen.
- Für alle drei:
  - Der Aufklapp-Knopf heißt „Werte ▾“.
  - Die Umschaltung Wiederholungen | Haltezeit wird ein Segment in der Ausführung.
  - Ja/Nein werden Wert-Knöpfe.

**Nachgezogen 21.10.2026 abends** (P70, P71; Skizzen
https://claude.ai/artifact/7JzRndHG41e3ZfeCm7huCH):
- „Eintragen“ ist **eine** weiße Karte für alle Mengen, je Feld eine Zeile (E2): kurzer
  Name („Wdh.“, „Haltezeit“) mit „je Satz“ darunter, bis zu drei „+“-Knöpfe, „…“ klappt
  Sätze × Wert auf. Ab vier Knöpfen stehen sie zu dritt in einer eigenen Reihe; ohne
  Chips steht das Zahlenfeld gleich in der Zeile.
- Ja/Nein, Skala und Freitext werden **keine** Wert-Knöpfe (anders als oben „für alle
  drei“): Sie stehen in der Ausführung unter „gilt für den offenen Eintrag“, zeigen und
  ändern dessen Wert und trennen keine Einträge. Die Skala ist der Schiebebalken der
  Tagesfelder (`ui/components/skala_regler.py`).

## G. Nachträglich, Uhr/Ablauf, Ziel (A6)

- **Nachtragen ist der Trainingsblock** (Ben, 21.10.2026, P72, Skizze G1): oben Wann
  (heute „Jetzt“ oder „Früher heute“, an einem vergangenen Tag die Uhrzeit; Vorlage ist
  die alte Zeit, sonst 12:00, `core.plaene.nachtrag_uhrzeit`) und Plan, darunter der
  Block ohne Uhr und HRV-Marken. `SessionRepo.zur_zeit` lässt alles um die gewählte Zeit
  beginnen und sammelt dort; offen ist dabei nur, was genau dann begann. „Fertig“,
  Zurück, eine andere Zeit oder ein anderer Plan schließen ab; wer die Seite anders
  verlässt (App beendet), dem schließt der Zeitabstand.
- Im Leistungen-Blatt und in der Korrektur bekommt SpecForm die
  Spec-Kopie, ergänzt um die heutigen Varianten der Übung (`spec_mit_varianten`). Auch ein
  Eintrag von vor der Variante lässt sich so noch setzen.
- `UebungKontext` bekommt `auspraegung`, also die Ausführung beim Start.
  `uebung_lauf._eintragen` und `lauf_eintragen` übernehmen sie (über die
  Beteiligungsdaten), ebenso `plan_ablauf.nach_der_uebung`. Damit kommen auch Gewicht und
  Seite an, die dort heute fehlen.

## H. Viele Varianten: Symbole, Kürzel, Beschreibung (D1–D5, P62)

Ben fragte am 21.10.: „Was, wenn z. B. 4+ Varianten bestehen: Planke Unterarm – Arme
gestreckt – Seitlich – diagonal … Kann man anstatt des Labels auch Symbole einfügen?
Symbol hat einen Namen, je nach Ort wird Label weggelassen … Beschreibung in den
Übungseinstellungen?“

**Platz:** In C1 hat die Variantenzeile bei 390 px etwa 300 px. Die vier Namen brauchen
als Segmente etwa 420 px, drei kurze Namen („kurz · lang · weit“) passen.

**Regel für die Variantenzeile** (eine Funktion im Kern mit Doctests; die Breite schätzt
sie aus der Zeichenzahl gegen `page.width`):
1. Passen die Namen in eine Zeile → Segmente mit Namen, ein gesetztes Symbol steht davor.
2. Passen sie nicht und **jede** Variante hat ein Symbol oder Kürzel → eine Zeile nur mit
   Symbolen. Name und Beschreibung der gewählten Variante stehen darunter. Langes Drücken
   oder der Tooltip nennt den Namen (D1).
3. Sonst → Namen in zwei Spalten, so viele Reihen wie nötig. Auch das ist ein Tipp (D2).

**Wo der Name wegfällt:** nur in der Variantenzeile. Überall sonst stehen Symbol und
Name: Heute geleistet, Tagebuch, Tag, Verlauf, Leistungen-Blatt, das Blatt hinter dem
Etikett.

**Je Variante** (D3/D4):
- **Name** (Pflicht);
- **Symbol** aus einer kleinen eigenen Auswahl (Pfeile, Formen, Person; ähnlich
  `ui/components/icons.AUSWAHL`) **oder** ein **Kürzel** mit bis zu 3 Zeichen („UA“);
- **Beschreibung** (optional).

Die Reihenfolge in den Übungseinstellungen bestimmt die Reihenfolge der Knöpfe; ordnen
geht über einen Griff. Die Beschreibung erscheint an drei Stellen: im Blatt hinter dem
Etikett (D5), unter der Variantenzeile bei der gewählten (D1) und in der Übungsinfo
(„i“).

**Speicherung ohne Migration:** Symbol, Kürzel und Beschreibung hängen als optionale
Angabe je Option am Feld `variant` in `result_spec` (z. B. `FieldSpec.optionen`:
Name → Symbol/Kürzel/Text). `FieldSpec.to_dict` schreibt sie nur, wenn es welche gibt.
Ältere App-Stände lesen nur `quick` und übersehen den Rest. Beim Umbenennen wandern die
Angaben mit. Die Spec-Kopie im Eintrag trägt sie mit, also bleibt das Symbol im Verlauf
so, wie es war.

**Leistungen-Blatt, Nachtragen, Korrektur:** Sie nutzen dieselbe Variantenwahl wie der
Block, als eigene Komponente statt des SegmentedButton von SpecForm, der vier lange Namen
nicht fasst.

**Kurve (B2):** Bei vielen Varianten sind anfangs die drei mit den meisten Einträgen im
Zeitraum sichtbar; die Chips blenden die übrigen ein.

## Offen (Katalog)

- P56: Abnahme der Reihe B.
- P62: viele Varianten (Reihe D).
- P57: Sammeln je Ausführung auch für Gewicht/Seite.
- P58: Variante in der Parameterwahl der Planübung.
- P59: Kurs-Bedingung mit Variante.
- P60: eigene Varianten an Paketübungen und der Drei-Wege-Abgleich.
- P61: Texte der alten „Varianten“ (Kopien mit gemeinsamer Kachel).

## Prüfung

- Doctests in `core/parameter`, `standards`, `tagesbilanz`, `eintraege` und `verlauf`.
- Repo-Tests: `variante_setzen`, Umbenennen mit und ohne Einträge, mehrere offene Einträge
  (kurz +30, lang +15, kurz +30 → zwei Einträge).
- UI-Tests: Variantenzeile, Blatt, Editorabschnitt, mehrere Linien. Anzupassen sind
  `test_ui_smoke.py` (`verlauf_variante`) und `test_ui_verlauf.py` (eine Linie bleibt der
  Fall ohne Varianten).
- `uv run ruff check . && uv run ruff format --check . && uv run pytest`, dazu die Doctests
  aus der CI, `uv run mypy` und das flet-freie CI-venv.
- Bildschirmfotos über Flet-Web; Gerätetest T-Zeile nach dem Bau.
