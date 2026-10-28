# Plan: Tagesfeld „Messwert“ — Blutdruck und andere Zweier-/Dreierwerte (Ben, 28.10.2026)

Ben: „Von der Art gibt es Skala bis ‚nur Text‘. Ich bräuchte ein besonderes Eingabefeld,
z. B. für den Blutdruck, wo man zwei zusammengehörige Werte eintragen kann, die dann nicht
akkumuliert im Verlauf nebeneinander angezeigt werden. Systolisch/Diastolisch macht Sinn,
dass man mehrmals am Tag misst, aber nicht zusammengezählt wird. Gleichzeitig müssen die
Tageswerte editierbar sein, z. B. im Verlauf akkumulieren oder anderes. … Blutdruck sollte
aber Standardfeld sein. Dann gehe die Tagesfelder noch einmal Logikverbesserungen durch.“

Stand: **entschieden am 28.10.2026 abends (§7), im Bau.** Katalog P88. Grundlage: `docs/plan_tagesfelder.md`,
`core/tagesfelder.py`, `ui/components/tagesfeld_blatt.py`, `ui/views/verlauf_tagesfeld.py`.

## 1. Zwei Dinge stecken darin

1. **Eine siebte Art „Messwert“**: ein abgelesener Wert, der sich nicht addiert — mit
   einem bis drei **Teilen**, die zusammengehören (Blutdruck: systolisch / diastolisch,
   wahlweise Puls). Jede Messung ist ein Eintrag mit Uhrzeit; am Tag stehen die Messungen
   nebeneinander („08:10 128/82 · 19:30 124/80“), nie als Summe.
2. **Der Tageswert wird einstellbar** — je Feld, nicht je Art: Wie wird aus mehreren
   Einträgen eines Tages der eine Wert für Heute-Knopf, Tagebuchzeile, Verlaufskurve und
   Kacheln? Bisher ist das fest (Anzahl/Menge/Dauer: Summe; Skala: Mittel). Künftig:

   | Tageswert | Anzahl, Menge, Dauer | Skala | Messwert |
   |---|---|---|---|
   | Summe | **Vorgabe** | – | – |
   | Mittel | ja | **Vorgabe** | **Vorgabe** |
   | Höchster | ja | ja | ja |
   | Niedrigster | – | ja | ja |
   | Letzter des Tages | ja | ja | ja |

   Ja/Nein bleibt „ja, wenn einmal ja“, nur Text bleibt Text. Die Einstellung steht im
   Feld-Formular unter „Wie oft“ als Segment „Tageswert“ und wirkt überall gleich
   (`core.tagesfelder.tagesstand` → `_verdichtet(feld, werte)` statt `(art, werte)`).
   Ein Messwert mit Mittel zeigt „Ø 126/81“, mit Letzter „124/80“, mit Höchster je Teil das
   Maximum („128/82“ — Teile einzeln, nicht die Messung mit dem höchsten ersten Teil; so steht
   es auch dabei).

   *Falls Ben mit „Tageswerte editierbar“ das Ändern einzelner Werte meinte:* Das geht
   heute im Blatt (Eintrag antippen → Uhrzeit, Variante, Wert, Notiz), aber **nur bei
   „mehrmals“** — bei „einmal am Tag“ ändert man den Wert direkt, die Uhrzeit nicht. Siehe
   §5, Punkt 4.

## 2. Wo es ein „Messwert“ noch sein könnte

Alles, was man **abliest** statt zählt — und was mit „Menge, mehrmals“ heute falsch
summiert würde:

| Feld | Teile | Einheit | Wie oft | Tageswert |
|---|---|---|---|---|
| **Blutdruck** (Standard) | systolisch · diastolisch (· Puls) | mmHg (· bpm) | mehrmals | Mittel |
| Gewicht | 1 | kg | einmal | – |
| Temperatur | 1 | °C | mehrmals | Höchster |
| Blutzucker | 1 | mg/dl oder mmol/l | mehrmals | Mittel |
| Ruhepuls, SpO₂ | 1 | bpm, % | einmal oder mehrmals | Mittel |
| Peak-Flow | 1 | l/min | mehrmals | Höchster |
| Schritte (vom Handy abgelesen) | 1 | – | einmal | Letzter |
| Taille, Umfang | 1 | cm | einmal | – |
| Beweglichkeit links/rechts | 2 (links · rechts) | ° oder cm | einmal | – |

Ein Messwert mit **einem** Teil ist also der häufige Fall („Gewicht“ wäre heute „Menge,
einmal“ — das geht, aber „Menge“ trägt die falsche Bedeutung). Zwei und drei Teile sind
Blutdruck und Seitenvergleiche. Mehr als drei Teile braucht nichts aus der Liste; die
Grenze bleibt bei drei.

**Standardfeld Blutdruck** — zwei Lesarten, Ben entscheidet (P88):
- (a) **Vorschlag** in der Auswahl beim Anlegen (wie „Schmerz“, „Trinken“): ein Tipp, alles
  ist eingestellt (Messwert, systolisch/diastolisch in mmHg, mehrmals, Mittel). Empfohlen —
  so wie alle anderen Vorschläge.
- (b) **Angelegt** in jedem Profil, zunächst ausgeschaltet (steht unter Einstellungen →
  Tagesfelder → Ausgeschaltet, ein Schalter holt es unter Heute). Mehr Nähe, aber ein Feld,
  das nicht jeder will; und das Seed müsste je Profil nachlegen.

Puls als dritter Teil: viele Heimgeräte zeigen ihn mit an. Vorschlag: Blutdruck mit
**zwei** Teilen; wer den Puls will, fügt im Feld den Teil „Puls (bpm)“ hinzu. Teile ab dem
zweiten dürfen beim Eintragen leer bleiben (dann steht „128/82“ ohne Puls).

## 3. Datenmodell

- **Spec** (keine neue Tabelle für die Art): `Layout.SINGLE`, je Teil ein `FieldSpec`
  mit den Schlüsseln `value`, `value_2`, `value_3`, Label = Name des Teils
  („systolisch“), `unit` je Teil, `min`/`max` als Plausibilitätsgrenze (Vorgabe Blutdruck
  30–300, Puls 20–250 — **nur** gegen Tippfehler, keine Bewertung). Die Art braucht eine
  eigene Markierung — `FieldSpec.optionen` taugt nicht (das sind Angaben je Schnellwert),
  und `FLOAT` heißt schon „Menge“. Vorschlag: ein neuer Feldtyp `FieldType.READING`
  (`"reading"`, Zahl mit Einheit, nicht summiert) in `core/result_spec.py` samt Widget in
  `spec_form.py` (ein Zahlenfeld — damit könnte auch eine Übung einen Messwert tragen,
  etwa „Gewicht“ an einer Waage-Übung; das entscheidet Ben getrennt). `art_von` bildet
  `READING → Messwert`; alte Spec-Kopien bleiben, was sie sind.
  `result` = `{"value": 128, "value_2": 82, "variant": …}`; `Tageswert.werte` liefert
  das Tupel, `Tageswert.wert` bleibt der erste Teil (alle heutigen Aufrufer).
- **Migration 032**: `day_field.tageswert TEXT NOT NULL DEFAULT ''` — leer = Vorgabe der
  Art (§1), sonst `summe` · `mittel` · `max` · `min` · `letzter`. `TagesfeldRepo` liest und
  schreibt es; die Spec-Kopie je Wert braucht es nicht (der Tageswert ist eine Ansicht,
  keine Erfassung — ändert man ihn, rechnen alte Tage neu, wie gewünscht).
- Varianten gibt es weiter (Blutdruck „liegend/sitzend“, Beweglichkeit „links/rechts“ als
  Varianten *oder* als Teile — beides geht; Teile stehen nebeneinander in einer Zeile,
  Varianten getrennt in Kurve und Stand).

## 4. Oberfläche

- **Formular** (`views/tagesfelder.py`): Art-Knopf „Messwert“ (7. Knopf, Reihe wird 4+3);
  Kasten „Teile“ mit 1–3 Zeilen (Name, Einheit, von–bis), „+ Teil“, ✕; Segment
  „Tageswert“ unter „Wie oft“ (Optionen nach Art, §1). Vorschlag „Blutdruck“ oben in der
  Auswahl; dazu „Gewicht“ (Messwert kg, einmal) — mehr Vorschläge nicht (Zweckbestimmung).
- **Blatt** (`tagesfeld_blatt.py`), neuer Zweig `messwert_teile()`: eine Zeile mit den
  Teilen als Zahlenfelder nebeneinander („sys“ · „dia“ · „Puls“, Einheit als Hinweis),
  Uhrzeit, „Eintragen“ (mehrmals) bzw. „Setzen“ (einmal, wie der freie Wert heute). Tippt
  man „128/82“ ins erste Feld, verteilt es sich auf die Teile (`messwert_lesen`). Der
  Bearbeiter eines Eintrags bekommt dieselbe Teile-Zeile statt des einen Wertfelds.
  Kein Schnellknopf — es gibt nichts zu addieren; der Knopf unter Heute öffnet das Blatt.
- **Heute-Knopf, Tagebuch, Zeitleiste** (`stand_text`, `tageszeile`, `eintrag_text`):
  „128/82 mmHg“; mit mehreren Messungen und Tageswert Mittel „Ø 126/81 · 2×“, mit Letzter
  „124/80 · 2×“. Zeitleiste: jede Messung an ihrer Uhrzeit, wie heute bei „mehrmals“.
- **Verlauf** (`verlauf_tagesfeld.py`): je Teil **eine Linie** (systolisch, diastolisch
  — dieselbe Achse, dieselbe Einheit; ein Teil mit anderer Einheit wie Puls bekommt die
  zweite Achse, wie HF/Tempo in der Streckenansicht), je Variante eine Farbe, Teile
  durch Linienstärke/gestrichelt (`Reihe.gestrichelt`); der Punkt je Tag ist der
  eingestellte Tageswert. Kacheln: je Teil „Ø 126 / Ø 81 mmHg · an 12 Tagen“. Die Liste
  „Einträge · neueste zuerst“ nennt jede Messung mit Uhrzeit.
  **Später, wenn gewünscht:** „jeder Wert“ als Punkte an ihrer Uhrzeit (die Kurve bräuchte
  eine Tagesbruchteil-Achse; heute ist x der Tag).
- **Kurven aus `core.verlauf`** (die Brücke `als_eintraege`) tragen den Tageswert nicht
  (dort ist Summe/Mittel/Max je Feldtyp fest). Der Verlauf eines Tagesfelds rechnet seine
  Punkte künftig selbst in `core.tagesfelder.tageskurve(feld, werte)` — eine Rechnung für
  Säulen, Linien und Kacheln, statt wie heute drei (Säulen inline in der Ansicht, Linien
  über `core.verlauf`, Kacheln über `summen`). `als_eintraege` bleibt für `verlauf.py`
  (Reiter „Zum Tag“, Mini-Kurven), bis auch der auf `tageskurve` umgestellt ist.

## 5. Logik-Durchsicht der Tagesfelder (28.10.2026)

Beim Lesen für diesen Plan aufgefallen — mit Vorschlag; was Ben will, kommt in den
Katalog:

1. **Null ist kein Wert** (`wert_lesen`: `0 < x`). „Kaffee heute: 0“ oder „Ibu 0“ als
   bewusste Aussage lässt sich bei „einmal am Tag“ nicht eintragen („Diesen Wert verstehe
   ich nicht“). Vorschlag: `0 <= x` bei einmal; bei mehrmals bleibt 0 sinnlos → Hinweis
   „0 trägt nichts ein“.
2. **Drei Rechnungen für denselben Tageswert** (§4, letzter Punkt): Säulen in der Ansicht,
   Linien über `core.verlauf`, Kacheln über `summen` — ein Bruch, sobald der Tageswert
   einstellbar ist. Vorschlag: eine Funktion `tageskurve`.
3. **Skala, mehrmals, Kachel „Ø“** ist das Mittel der Tagesmittel (ungewichtet) — je Tag
   zählt gleich, egal wie oft gemessen. Das ist vertretbar, steht aber nirgends. Mit dem
   einstellbaren Tageswert gilt: Kachel = Mittel der Tageswerte; so in die Hilfe.
4. **Einmal am Tag: Uhrzeit nicht änderbar.** Der Wert hat eine Uhrzeit (`recorded_at`,
   steht in der Zeitleiste als „gesetzt um 08:10“), aber das Blatt zeigt bei „einmal“ keinen
   Bearbeiter. Vorschlag: auch bei „einmal“ die Zeile „heute eingetragen“ mit Uhrzeit und
   Bearbeiter zeigen (ein Eintrag je Variante), wie bei „mehrmals“.
5. **Wie-oft-Wechsel mit Werten**: Die Art ist gesperrt, sobald es Werte gibt; „einmal ↔
   mehrmals“ nicht. Von mehrmals auf einmal: Tage mit mehreren Einträgen behalten alle —
   der Stand zeigt die Verdichtung, das Blatt aber nur den jüngsten als „Wert des Tages“
   (`einmal_ziel`), die anderen sind unsichtbar, bis man zurückschaltet. Vorschlag: beim
   Umschalten sagen, wie viele Tage mehrere Einträge haben, und bei „einmal“ im Blatt alle
   Einträge des Tags zeigen (Punkt 4 löst das mit).
6. **Schnellknopf bei „einmal“ addiert still** (`plus`): „+250“ auf „Wert des Tages 750“ →
   1000, mit „Rückgängig“ in der Meldung. Richtig so; nur die Meldung sagt „Trinken +250“
   und nicht den neuen Stand. Vorschlag: „Trinken +250 → 1 l“.
7. **Variante entfernt, Werte bleiben**: `varianten_reihenfolge` hängt entfernte hinten
   an — gut. Im Blatt lässt sich eine entfernte Variante aber nicht mehr wählen, also ein
   alter Eintrag dieser Variante nicht korrigieren, ohne ihm eine andere zu geben
   (`Dropdown` nur aktuelle Varianten). Vorschlag: die Variante des Eintrags steht mit in der
   Liste, markiert „(entfernt)“.
8. **`menge_text` schaltet ab 1000 ml auf Liter** — auch in Eingabefeldern? Nein
   (`eingabe_text` bleibt bei ml): stimmig. Aber „1 l“ beim Schnellknopf „+1000“ hieße
   „+1 l“? `schnell_text` nimmt `zahl` → „+1000“. Kleinigkeit, einheitlich machen.
9. **Dauer: nackte Zahl = Minuten** (`dauer_lesen`) — im Bearbeiter zeigt `eingabe_text` für
   90 s „90 s“, für 10 min „10“. Beim Tippen von „90“ meint die App 90 min. Konsistent, aber
   die Hilfe im Feld („Minuten oder 1:30“) fehlt im Bearbeiter. Nachtragen.
10. **`WERT_MAX` 100 000** gilt für Anzahl und Menge gemeinsam — „Schritte 12 500“ passt,
    „Kalorien“ passt; „Menge in g“ für einen Tag passt. Keine Änderung, nur festhalten;
    beim Messwert kommen die Grenzen je Teil aus dem Feld (§3).
11. **Tagesgrenze**: `Tageswert.tag` ist der lokale Tag beim Eintragen, `recorded_at` UTC;
    Nachtragen um 23:30 für „gestern“ bekommt `tag = gestern` und `zeit = gestern 23:30`
    lokal → stimmig (`zeitpunkt`). Ein Eintrag „heute 00:10“, den die Person für „gestern
    spät“ hält, landet unter heute — wie bei den Übungen. Keine Änderung.
12. **Heute-Knopf mit Varianten** zeigt alle Varianten im Stand („400 × 2 · 800 × 1“), der
    Schnellknopf aber nur die gemerkte Variante — ohne sie zu nennen, wenn sie die einzige
    mit Wert ist. Vorschlag: der Schnellknopf trägt immer „+1 · 400“, wenn das Feld
    Varianten hat (heute nur, wenn `v` gesetzt ist — das ist es praktisch immer; prüfen).
13. **Recht (P68)**: Blutdruck ist ein Gesundheitsdatum wie Schmerz; Dokumentieren bleibt
    erlaubt, **keine** Einordnung („erhöht“, Ampel, Zielbereich), keine Erinnerung ans
    Messen. Die Plausibilitätsgrenzen (§3) sind Tippfehler-Schutz, keine Grenzwerte — so
    benennen. Nachtrag in `docs/recht/00_zweckbestimmung.md` (Tabelle: „Blutdruck 128/82,
    Linie über die Zeit“ erlaubt — „Blutdruck erhöht“, „Zielbereich“ nicht) und
    `10_verarbeitungsverzeichnis.md` (Kategorie Tagesfelder nennt Messwerte).

## 6. Aufwand und Reihenfolge

1. Kern: Art Messwert (`spec_bauen(teile=…)`, `art_von`, `werte`, `wert_text` „128/82 mmHg“,
   `messwert_lesen`), Tageswert-Einstellung (`_verdichtet(feld, …)`, `tageskurve`),
   Migration 031, Repo. Doctests, `tests/test_tagesfelder.py`.
2. Blatt und Bearbeiter (Teile-Zeile), Formular (Art, Teile, Tageswert), Vorschläge.
3. Verlauf auf `tageskurve` (Säulen, Linien, Kacheln), Messwert-Linien je Teil.
4. Durchsicht §5, Punkte 1, 4, 6, 7, 9 (klein) — 2 und 3 kommen mit Schritt 1 und 3.
5. Doku und Recht (§5, 13), Gerätetest.

Offen für Ben (P88): Standardfeld (a) oder (b); Puls als dritter Teil im Vorschlag oder
selbst hinzufügen; Tageswert-Optionen wie in §1; Punkte aus §5, die er will.

## 7. Entscheidungen (Ben, 28.10.2026 abends)

> - Standardfeld Blutdruck ja
> - Standardfelder lassen sich aber löschen, in den Einstellungen kann man es wieder
>   herstellen. Ein Programmupdate respektiert die gelöschten Tagesfelder, dort kann man
>   diese aber wieder zurücksetzen
> - Blutdruck in drei Teilen mit Puls optional … Wenn ja, dann rein.
> - Gewicht, Blutzucker, SpO2 sind sicherlich sinnvolle Daten. So werden die Vorschläge aber
>   schnell viel. Lässt sich das mit den Vorschlägen für die Überschriften irgendwie besser
>   sortieren und organisieren
> - Wenn man auf Art klickt, öffnet sich die Tastatur … man soll die Buttons bei Art
>   durchklicken können, ohne dass man immer die Tastatur wegklicken muss
> - Zu §5: 1. … ermögliche auch das Eintragen der 0, bei einmalig oder mehrmals … Die App ist
>   ein Tagebuch. 9: Immer Einheiten mit angeben, ja. Der Rest ist gut.

### 7.1 Standardfelder (Lesart b, mit Löschen und Wiederherstellen)

- `STANDARDFELDER` in `core/tagesfelder.py`: je ein Schlüssel (`blutdruck`), die
  Definition wie ein Vorschlag. Erstes und einziges: **Blutdruck** — Messwert, drei Teile
  systolisch · diastolisch (mmHg) · Puls (bpm, darf leer bleiben), mehrmals mit Uhrzeit,
  Tageswert Mittel.
- `day_field.standard_key TEXT` (Migration 032): das Feld stammt aus dem Standard. Beim Start
  (`AppState.starten`) und beim Anlegen eines Profils legt `tagesfelder_standard_einspielen`
  je Profil an, was fehlt — **nie, was gelöscht wurde** (die gelöschte Zeile bleibt als
  Grabstein mit `standard_key`; der Start sieht sie und lässt es). Ein Update der App mit
  neuen Standardfeldern legt nur die neuen an.
- Einstellungen → Tagesfelder: unten der Abschnitt **„Standardfelder“** mit denen, die
  gelöscht sind — „Wiederherstellen“ holt die Zeile zurück (`deleted_at` weg, die Werte
  mit, falls sie mitgelöscht waren: `loeschen_rueckgaengig` ohne Frist) bzw. legt sie neu an,
  wenn es nie eine gab. Steht nichts darin, fehlt der Abschnitt.
- Name, Teile, Tageswert und „wie oft“ eines Standardfelds darf die Person ändern wie bei
  jedem Feld; „Wiederherstellen“ setzt nichts zurück, was es noch gibt.

### 7.2 Blutdruck mit Puls

Drei Teile, der dritte optional: Das Blatt zeigt drei Zahlenfelder nebeneinander, „Puls“ mit
Hinweis „optional“; leer gelassen fehlt er im Eintrag („128/82“ statt „128/82 · 72“). Im
Verlauf hat der Puls seine eigene Einheit (bpm) und darum die rechte Achse. Intuitiv genug,
weil Heimgeräte genau so anzeigen.

### 7.3 Vorschläge wie die Überschriften

Statt der Chip-Wolke ein **Blatt „Vorlage wählen“** (`components/tagesfeld_vorlagen.py`), wie
`components/titel.titel_blatt`: ein Suchfeld oben, darunter die Vorlagen in **Gruppen** mit
Überschrift — Beschwerden (Schmerz, Stimmung), Messwerte (Blutdruck, Gewicht, Blutzucker,
SpO₂, Temperatur, Ruhepuls), Einnahmen (Medikament, Trinken), Alltag (Schlaf, Spazieren,
Meditation, Ernährung). Tippen filtert über alle Gruppen, Antippen füllt das Formular. Im
Formular steht oben nur noch ein Knopf „Vorlage wählen …“ und der Name der gewählten
Vorlage. Die Liste bleibt Daten (`VORLAGEN` mit `gruppe`), keine Bewertung.

### 7.4 Tastatur

`autofocus=neu` am Namensfeld galt für jeden Neuaufbau des Formulars — jeder Tipp auf eine
Art baute neu und holte die Tastatur. Jetzt nur beim ersten Aufbau (`erster_aufbau`), danach
nie wieder.

### 7.5 §5 umgesetzt

1 (Null als Wert, einmal und mehrmals; „0“ ist ein Eintrag wie jeder), 2 (`tageskurve`),
3 (Hilfe), 4 (Uhrzeit und Bearbeiter auch bei „einmal“), 5 (Hinweis beim Wechsel, alle
Einträge im Blatt), 6 (Meldung mit neuem Stand), 7 (entfernte Variante „(entfernt)“ im
Bearbeiter), 8 und 9 (Einheiten überall: Schnellknöpfe, Bearbeiter, Hilfe), 12 (Schnellknopf
nennt die Variante), 13 (Recht).
