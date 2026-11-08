# Plan: Übung bearbeiten – aufgeräumt, Symbol oben, Parameter als Knöpfe, Ziel am Parameter

Stand 2.11.2026: **gebaut** (Teile A–H, 0.3.40; P106–P109 nach Bens Antworten in 0.3.41,
unten „Entschieden“). Anlass sind Bens sieben Punkte vom
2.11.2026 („Bald kommt eine neue Version. Vorher muss aber noch der Edit der Übungen verbessert
werden“):

> 1) Übersichtlicher, alles dort, wo es hingehört. Symbol ganz oben, mit Klick bearbeitbar
>    machen, auch Upload ermöglichen. Es braucht eine Symbol/Photoablage, aus welcher die
>    Symbole gelöscht werden können. Evtl. werden auch Photos als Symbol/Bild eingefügt.
> 2) Eine schönere Bearbeitbarkeit der Texte/Namen wäre gut. Was hast du als Angebot?
> 3) Parameter Aktivierung/Deaktivierung als Buttons. Unten drunter die Einstellungen,
>    übersichtlicher.
> 4) Nicht gebrauchte Chips sollen gelöscht werden können.
> 5) Erklärtexte (Varianten, Zählt als …) in das „i“, um die Übung weniger überladen zu halten.
> 6) Lass uns überlegen, ob es sich lohnt, die Logik der Parameter neu aufzusetzen. Es gibt
>    Einheiten (Zeit/s), die benannt werden können. Freitext und Seite würde zu Text mit
>    links/rechts werden. Wenn man Parameter hinzufügt, kann man diese hinzufügen: „+“ auf die
>    Einheit klicken, Namen geben, Chips verteilen und so weiter. Das ist erstmal komplizierter,
>    die Pakete werden ohnehin von mir erstellt. Die Spalte mit den vielen Buttons macht das
>    Ganze unübersichtlich. Was meinst du? Diskutiere.
> 7) Ziele müssten deutlicher kenntlich gemacht werden. Erklärung wieder ins „i“, und aus
>    allem Obigen müsste aus den Einstellungen + Leistungen ein Kombofeld entstehen, wie in
>    Übungen jetzt.

Vertrag bisher: `docs/plan_uebungen_einstellen.md` (P79: zwei Orte, ein Weg; C2: was die Übung
hat, bieten alle Pläne an) und `docs/plan_varianten.md` (Varianten als Feld `variant`). Beides
bleibt; hier geht es nur um die **Seite** `/uebung/<id>/bearbeiten` (`ui/views/uebung_bearbeiten.py`).

## Was heute steht (und stört)

Eine lange Spalte ohne Karten: Name, Beschreibung, Videos und Links, **Parameter** (zehn
Schalter untereinander, je Schalter darunter eingerückt die Chips und „Sätze“ — „die Spalte mit
den vielen Buttons“), Varianten, Uhr und Timer (mit vier wechselnden Erklärsätzen), **Vorgabe
für Pläne** (das Ziel, als eigenes Formular weit unten), Ordnen (Typ, Region, zuletzt das
Symbol als Kachelraster). Erklärtexte stehen inline unter jeder Überschrift. Ein eigenes Bild
gibt es nicht, obwohl `exercise.image_path` seit Migration 001 existiert (nie gesetzt, nie
gezeigt).

## Die neue Seite (von oben nach unten)

| Teil | Was | Dateien |
|---|---|---|
| A | **Kopf:** links das Symbol groß (72 px), ein Tipp öffnet das Symbol-Blatt; rechts der Name als große Zeile. Darunter die Beschreibung als Karte: gezeigt wie auf der Übungsseite, ein Tipp öffnet den Editor an Ort und Stelle (↶ ↷ Abbrechen Fertig, `components/notizeditor.Textnotiz` — gespeichert wird aber erst mit dem Formular, der Editor schreibt in den Formularstand). | `uebung_bearbeiten.py`, `components/notizeditor.py` |
| B | **Symbol-Blatt** (`components/symbol_blatt.py`): oben „Eigene Bilder“ — die Ablage: jedes hochgeladene oder fotografierte Bild als Kachel, Antippen wählt, Papierkorb löscht es aus der Ablage (Übungen, die es trugen, fallen auf ihr Symbol zurück); dazu „Foto hochladen“ (Fotoauswahl, verkleinert, ohne Ort — `erweiterungen/flet_hochladen`, am Rechner `ft.FilePicker`) und „Foto aufnehmen“ (Kamera). Darunter die kuratierten Symbole (`components/icons.AUSWAHL`) als Raster. | neu `components/symbol_blatt.py`, `data/uebungsbilder.py` |
| B2 | **Bild statt Symbol überall:** `components/uebungsbild.uebungsbild(uebung, groesse)` zeigt das Bild (rund, zugeschnitten), sonst das Symbol — Katalog, Plan, Nachtragen, Tagebuch, Verlauf, Tag, Übungsseite, Pakete, Papierkorb. | `components/uebungsbild.py` + Aufrufer |
| C | **Parameter als Knöpfe:** eine umbrechende Reihe aus Chips, ein Chip je Feld des Vorrats (Wiederholungen, Haltezeit, Gewicht, Strecke, Zeit, Winkel, Skala, Seite, Vollständig, Freitext) — an/aus mit einem Tipp. **Darunter je eingeschaltetem Parameter eine Karte**: Name (frei änderbar — die „Einheit benennen“ aus Punkt 6, denn `FieldSpec.label` gehört schon heute der Übung), Chips (ein Tipp bietet an; ein ungenutzter Chip trägt ✕ und lässt sich löschen, Punkt 4; „eigener“ + ergänzt), „Sätze“ bei Satzfeldern, Bereich bei der Skala — **und das Ziel** für diesen Parameter (Punkt 7: „Einstellungen + Leistungen ein Kombofeld“: das Ziel ist das, was beim Üben als „Wie geplant“ eingetragen wird; es steht nicht mehr als eigenes Formular ganz unten, sondern beim Parameter, mit Beschriftung „Ziel“ und einem Beispiel „3 × 15“). | `uebung_bearbeiten.py`, `components/chips_wahl.py`, `core/standards.ziel_spec` |
| D | **Varianten:** wie bisher (Liste, „Variante hinzufügen“), ohne Erklärtext — der steht im (i). | `uebung_bearbeiten.py` |
| E | **Uhr und Timer:** wie bisher, der lange Erklärsatz wird ein kurzer Stand („Jeder Lauf: ein Satz Haltezeit“) — der Rest im (i). | `uebung_bearbeiten.py`, `components/hilfe.py` |
| F | **Videos und Links** und **Ordnen** (Typ, Region) am Ende — selten, darum unten. | |
| G | **Erklärtexte ins (i):** jede Überschrift trägt rechts das (i) (`hilfe_knopf`), das das Hilfefenster zum Thema öffnet: `parameter` (mit Chips, Sätze, Ziel), `varianten`, `uhr` (Timerzeit zählt, zählt als), `symbol` (Ablage, Bild ohne Ort). Die inline-Texte fallen weg. | `components/hilfe.py` |
| H | Doku, Tests, `docs/plan_uebungen_einstellen.md` (Schritt 3 „aufräumen“ erledigt). | |

**Beim Bauen entschieden:** Das ✕ an einem Chip nimmt ihn aus der Wahl — ein eigener Chip
ist damit weg, ein Vorschlag des Vorrats (10, 15, 20) steht beim nächsten Öffnen wieder zur
Wahl (Ben, 18.10.2026: „leer heißt leer“ — die Vorschläge bleiben Vorschläge, gespeichert
wird nur, was gewählt ist). Das Zielfeld je Karte heißt „Ziel“ bzw. „Ziel je Satz“ — seit
8.11.2026 (Ben: „Ziel ist nur optional und für eine Standardübung eher selten“) ist es ohne
Wert **zu** und öffnet erst mit „Ziel setzen …“; die
Ziel-Variante steht unter den Varianten. Am Rechner nimmt „Foto hochladen“ den Dateidialog
(JPEG, ohne Verkleinern, Metadaten werden entfernt); am Handy die Fotoauswahl der App.

**Im Plan einstellen** (`plan_einstellen.py`) bekommt dieselbe Ordnung in einem zweiten
Schritt (P107): Parameter als Chips, Karten mit Chips und Ziel, Schilde „wie die Übung“ / „nur
hier“ wie heute. Jetzt bleibt es, wie es ist — es hat schon Karten je Parameter.

## Punkt 2 — mein Angebot für Texte und Namen

- **Name** als große Zeile neben dem Symbol (Schriftgröße 20, ohne Rahmen, Hinweis „Name der
  Übung“) — das ist der Kopf der Seite, wie auf der Übungsseite.
- **Beschreibung** als Karte, die so aussieht wie auf der Übungsseite (Absätze, Zeilenumbrüche
  bleiben). Ein Tipp öffnet den Editor **an Ort und Stelle** — derselbe wie bei den Notizen:
  ↶ ↷ aus `core/textverlauf.py`, „Abbrechen“ = Text vom Antippen, „Fertig“ klappt wieder zur
  Karte. Diktieren geht über die Tastatur wie bei den Notizen. Keine Popups.
- **Variante, Timer** behalten ihr Blatt (Name, Symbol, Kürzel, Beschreibung) — das ist ein
  Formular mit mehreren Feldern, kein Fließtext.
- **Später, wenn gewünscht** (P108): gegliederte Beschreibung mit festen Abschnitten
  („Ausführung“, „Worauf achten“, „Häufige Fehler“) statt eines Textes — das wäre auch für
  Pakete nützlich, braucht aber ein Feld je Abschnitt im Paketformat.

## Punkt 6 — die Parameterlogik neu aufsetzen? Diskussion

**Was heute gilt.** Zehn feste Felder mit festen Schlüsseln (`reps`, `hold`, `weight`,
`distance`, `duration`, `angle`, `scale`, `side`, `done`, `note`). Eine Übung wählt eine
Teilmenge, gibt jedem Feld Chips, bei Satzfeldern „Sätze an/aus“ (neu dazu: aus, Ben 8.11.2026,
`docs/notation.md`), bei der Skala Name und
Bereich; der Name (`label`) ist schon heute je Übung frei. Die Schlüssel sind kein Zufall:
An ihnen hängt die ganze Rechnung dahinter —

- `reps`/`hold`/`duration` sind die **Mengen**, die addiert werden (Kurven, „Summe des Tages“,
  Kennzahlen je Kachel, Timer „zählt als“ Haltezeit oder Zeit);
- `angle`/`weight`/`side` sind **Ausprägungen**, die Einträge trennen (45° ≠ 90°, links ≠
  rechts) — darum ist „Seite“ eine Auswahl und kein Text;
- `scale`/`done`/`note` sind **Beiwerk** ohne Rechnung;
- Pläne (`fields_json`, `target_json`), Pakete, Kurse, Varianten, Nachtragen, Leistungen,
  Verlauf, praxis_gui und die Golden-Tests sprechen diese Schlüssel.

**Bens Entwurf.** Einheiten (Zeit/s, Wdh., kg, m, °, Skala, Text, Ja/Nein) als Bausteine;
„+“ auf eine Einheit legt einen Parameter an: Name, Chips, Sätze. Freitext und Seite werden
„Text mit links/rechts“. Vorteile: ein Mechanismus für alles, beliebig viele Parameter
derselben Einheit (zwei Zeiten, zwei Skalen), sprechende Namen, keine Spalte mit Schaltern.

**Was mich daran bremst.**

1. **Der Nutzen ist kleiner, als er aussieht.** Namen gibt es schon (`label`); nur das
   Umbenennen fehlte in der Oberfläche — das kommt jetzt (C). Die Spalte mit Schaltern
   verschwindet mit Punkt 3 ohnehin. Was wirklich fehlt, ist allein „zwei Parameter derselben
   Einheit“ (zwei Zeiten, zwei Skalen). Das brauchen wenige Übungen.
2. **Seite ist keine Textfarbe.** „links/rechts“ trennt Einträge und Kurven (links 3 × 15,
   rechts 3 × 12 — zwei Zeilen im Verlauf). Als Text mit Zusatz ginge das verloren oder müsste
   neu erfunden werden. Freitext bleibt Beiwerk. Ich würde beides lassen, wie es ist.
3. **Der Preis liegt unten.** Freie Schlüssel heißen: Jede Stelle, die heute `reps` oder
   `hold` liest, braucht eine Zuordnung „welcher Parameter ist die Menge, welche die Zeit“ —
   Kurven, Kennzahlen, Timer-Zählen, Nachtragen, Leistungen, Pakete (Format 3), praxis_gui.
   Das sind zwei bis drei Tage und ein Migrationsrisiko für alle bestehenden Einträge, die
   mit ihrer `spec_snapshot_json` angezeigt werden.

**Mein Vorschlag — der Mittelweg, in zwei Stufen.**

- **Jetzt (dieser Plan):** Die Oberfläche denkt in Einheiten, der Kern bleibt. Die Chip-Reihe
  zeigt die zehn Arten; eine Karte je eingeschaltetem Parameter mit eigenem Namen, Chips,
  Sätzen, Ziel. Nichts im Datenmodell ändert sich, alle Pakete bleiben gültig.
- **Dann, wenn du eine Übung mit zwei Zeiten oder zwei Skalen wirklich brauchst (P106):** der
  Feldvorrat bekommt **Mehrfachfelder** nach dem Muster der Tagesfelder (`value`, `value_2`):
  „+“ an der Karte einer Art legt `hold_2`, `scale_2` an — gleicher Typ, eigener Name, eigene
  Chips. Die Rechnung dahinter versteht die Nummer (Summe über `hold*`, Kurve je Feld). Das
  ist der Teil von Bens Entwurf, der etwas bringt, ohne die Schlüssel aufzugeben — etwa ein
  Tag Arbeit, kein Umbau der Einträge.
- **Nicht:** Seite und Freitext zusammenlegen.

## Punkt 7 — Ziele deutlicher (meine Lesart)

„Ziel“ ist in dieser App zweierlei: die **Vorgabe fürs Üben** („Wie geplant“ trägt sie ein:
3 × 15, 45 s) — und die Zielsymbole der Navigation (`docs/plan_routing_ziele.md`), die bleiben
außen vor. Die Vorgabe stand als „Vorgabe für Pläne“ ganz unten, getrennt von den Parametern,
die sie betrifft. Lesart von „aus den Einstellungen + Leistungen ein Kombofeld, wie in
Übungen jetzt“: **je Parameter eine Karte mit Einstellung (Chips, Sätze) und Leistung (das
Ziel)** — so wie die Übungsseite je Parameter einen Block mit Chips und Beispiel zeigt. Das
baue ich (C). Beschriftung „Ziel“ mit Beispiel, Hinweis im (i): „gilt in jedem Plan ohne
eigenes; im Plan einstellen kann es abweichen.“ Falls du etwas anderes meintest (etwa die
Übungsseite oder das Leistungen-Blatt), sag es — die Karte lässt sich dorthin tragen.

## Datenmodell

- **Keine Migration.** `exercise.image_path` (seit 001) nimmt den relativen Pfad des eigenen
  Bilds unter `Medien/Symbole/` (`config.medienverzeichnis()`); gesetzt = Bild statt Symbol,
  `icon_key` bleibt als Rückfall. Bilder: JPEG, verkleinert auf 512 px Kante, ohne
  Ortsangabe (`core.anhaenge.jpeg_ohne_metadaten`), Name `symbol_<id>.jpg`.
- **Die Ablage** ist der Ordner: `data/uebungsbilder.py` listet die Dateien (mit den Übungen,
  die sie tragen — `SELECT id, name FROM exercise WHERE image_path = ?`), löscht Datei und
  setzt `image_path = NULL` bei den Übungen.
- Pakete: Bilder reisen nicht mit (wie `source = local`, `data/pakete.py`); das Backup nimmt
  `Medien/` wie bisher mit. Kein Export, kein Sync (wie Anhänge).
- Ziel und Parameter: unverändert (`Exercise.default_target`, `result_spec`).

## Offene Fragen

| # | Frage | Vorschlag |
|---|---|---|
| P106 | Mehrfachfelder einer Art (`hold_2`, `scale_2`) — jetzt oder erst bei Bedarf? | erst bei Bedarf; der Mittelweg oben |
| P107 | „Im Plan einstellen“ in dieselbe Ordnung bringen (Chips oben, Ziel am Parameter)? | ja, zweiter Schritt nach der Version |
| P108 | Gegliederte Beschreibung (Ausführung, Worauf achten, Fehler) — Paketformat 3? | später, wenn gewünscht |
| P109 | Fotos als Symbol: rund zugeschnitten überall, oder nur auf der Übungsseite groß und sonst das Symbol? | überall rund (B2) |

## Entschieden (Ben, 2.11.2026) und gebaut (0.3.41)

- **P106 — ja, Mehrfachfelder sofort.** Ben: „Zeitfelder können der Stoppuhr zugeordnet
  werden. Mehrere Skalen machen eh Sinn. Freitext und Textfeld getrennt, klar.
  Migrationsrisiko müssen wir einfach mehrfach gegenchecken. … Gewichte kann man Hanteln
  direkt schreiben usw.“ Gebaut nach dem Mittelweg: Die Schlüssel des Vorrats bleiben die
  Art, ein weiteres Feld heißt ``hold_2``, ``scale_2`` … (`core.result_spec.basis_key`,
  `vorrat_feld`, `naechster_key`, `instanzen`). Auf der Karte legt „+“ das nächste Feld an
  (eigener Name, eigene Chips, eigener Bereich), ✕ nimmt es weg. **Zählt als** bietet jedes
  Zeitfeld der Übung an (`core.uebung_timer.zaehlt_als`, auch ``hold_2``; Timer und
  Stoppuhr tragen dort ein, `core.timer_eintrag.ergebnis`). Keine Migration: alte Übungen
  tragen nur Grundschlüssel; Pakete dürfen ``hold_2`` tragen (`_zaehlt_als_lesen`). Was
  nach der Art fragt (Haltezeit je Satz, Zeit, Summen, Kurven) nimmt `basis_key`. Ben will
  die Praktikabilität selbst herausfinden (etwa Liegestütz kurz/lang als zwei
  Wiederholungsfelder statt Varianten).
- **P107 — ja, gleich mit in die Version.** „Im Plan einstellen“ in derselben Ordnung:
  Parameter als Chips (die der Übung; darunter „Weitere Parameter holen“ mit den Chips des
  Vorrats), je eingeschaltetem eine Karte mit Chips und dem Ziel dieses Parameters, Schilde
  „wie die Übung“ / „nur hier“ mit ↺ an Chips, Ziel und den Knöpfen; Ziel-Variante unter den
  Varianten; die Hilfe-Themen `parameter`, `varianten`, `uhr`.
- **P108 — Beschreibung als Abschnitte „Name“ + „Inhalt“** in eigener Reihenfolge (Ben:
  „z. B. die Beschreibung vom Paket, individueller Text für einen Patienten, eigener Text“).
  Gespeichert bleibt ein Text mit ``## Name``-Zeilen (`core/beschreibung.py`) — Pakete,
  praxis_gui und ältere Stände lesen ihn weiter als Text, der Drei-Wege-Abgleich sieht ein
  Feld. Im Formular je Abschnitt eine Karte (Name, Editor an Ort und Stelle, ↑, ✕),
  „Abschnitt hinzufügen“; die Übungsseite zeigt die Abschnitte mit Namen.
- **P109 — quadratisch mit runden Ecken** (Ben: „lässt einfachere Symbolerstellung zu. Ein
  rundes PNG gerne rund“): `components/uebungsbild.ECKE` = 22 % der Kante, PNG erlaubt (ein
  rundes oder freigestelltes PNG zeigt seine Form). Die Symbole und Bilder werden später ein
  eigenes Kapitel.
