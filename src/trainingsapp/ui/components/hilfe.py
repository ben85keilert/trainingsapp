"""Hilfefenster — überall derselbe Text je Thema.

- **Notation** (`NOTATION_MD`): steht auch in `docs/notation.md`; wer die
  Notation ändert, ändert beide Stellen.
- **Varianten und Pakete** (`UEBUNGEN_MD`): die allgemeine Erklärung, die
  früher in jeder Übung stand (Ben, 14.10.2026: dort redundant). Ausführlich
  in `docs/datenmodell.md` (Varianten) und `docs/uebungspakete.md`.
- **Atemfrequenz und Atemübung** (`ATMUNG_MD`, Ben 17.10.2026): was „unter 8/min“
  und der Knopf „Atemübung“ heißen. Kommt in die Hilfedatei (Katalog A3); die
  Rechenvorschrift steht in hrv-core (`hrv_core/atmung.py`).
- **Varianten** (`VARIANTEN_MD`, Ben 21.10.2026): was das Etikett neben „Notiz“ heißt —
  neben dem Symbol steht kein Wort, die Erklärung kommt in die Hilfedatei (Katalog A3).
- **Parameter, Uhr, Symbol** (`PARAMETER_MD`, `UHR_MD`, `SYMBOL_MD`, Ben 2.11.2026: „Erklärtexte
  in das i, um die Übung weniger überladen zu halten“): die Texte, die bis dahin unter jeder
  Überschrift von „Übung bearbeiten“ standen.
- **Beschleunigungssensor** (`BESCHLEUNIGUNG_MD`, Ben 4.11.2026, `docs/plan_beschleunigung.md`
  §3.4): was gemessen wird, welche Geräte es können, dass es ein Prototyp ist, dass im Alltag
  nur Ergebnisse gespeichert werden — und warum „Wiederholungen“ ausgegraut sein kann.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

NOTATION_MD = """\
**Je Satz** (Wiederholungen, Haltezeit)

| Eingabe | Bedeutung |
|---|---|
| `30` | ein Satz mit 30 |
| `3x15` | drei Sätze mit je 15 |
| `15/15/20` | drei Sätze, einzeln |
| `2x15/20` | zwei Sätze 15, dann ein Satz 20 |
| `+20` | einen Satz 20 anhängen |

Anzeige: `3x15`, `30` oder `15/15/20`, dazu die Summe.

**Im Plan** tippst du nur Zahlen: Chips wie `+15` hängen einen Satz an, darunter
**Sätze × Wert** (`3` × `15`) — leer bei Sätze heißt einer. Die Handy-Tastatur
für Zahlen hat kein „x“; beim Korrigieren eines Eintrags (Tafel „Heute
geleistet“ antippen) trennt dort das Komma die Sätze: `15,15,20`.

**Zeiten**: `30` = 30 s, `1:30` = 90 s, `2min`, `1:30:00` mit Stunden. Je Satz wie
oben: `3x30`, `45/60/30`. `0` oder leer = ohne Zeit — gemacht, aber kein Punkt auf der Kurve.

**Grenzen**: höchstens 100 Sätze, Zeiten bis 48 h, Werte bis 100 000 — darüber
meldet das Feld einen Fehler.

**Einzelwerte**: Gewicht `40` oder `40kg`, Strecke `500` (m) oder `2km`, Winkel `45`,
Skala `0` bis `10` — im Plan ein Schiebebalken (Loslassen trägt ein), im Formular
Regler oder Zahl mit dem Haken. Dezimal mit Punkt oder Komma (`12,5`); in Satzlisten
trennt das Komma Sätze, also dort `12.5`.

**Menge oder Ausprägung**: Wiederholungen und Zeiten werden addiert (3 × 50 = 150).
Winkel, Gewicht und Seite wählst du vorher aus — sie trennen: Wandsitz 45° ist
nicht Wandsitz 90°. „Gemacht“ ohne Werte zählt als *abgehakt* (leerer Haken).
Ja/Nein, Skala und Freitext gelten für den offenen Eintrag — sie trennen nicht.

**Varianten** (Liegestütz kurz und lang) stehen ganz oben in der Ausführung und werden
getrennt gezählt: kurz +30, lang +15, kurz +30 ergibt „kurz 60“ und „lang 15“. Das
**Etikett** neben „Notiz“ setzt die Variante des offenen Eintrags, auch nachträglich,
und legt eine neue an.
"""

VARIANTEN_MD = """\
**Varianten** sind Ausführungen derselben Übung — Liegestütz kurz und lang, Planke
Unterarm, gestreckt, seitlich. Sie gehören zur Übung und werden **getrennt gezählt**:
400 kurze sind etwas anderes als 400 lange. Im Tag und im Tagebuch hat jede Variante
ihre eigene Zeile, in der Kurve ihre eigene Linie; „Zusammen“ blendet die Summe dazu.

**Beim Üben** stehen die Varianten oben in der Ausführung, neben Gewicht und Seite. Die
gewählte gilt für jeden Eintrag, bis du umschaltest — je Ausführung sammelt sich ein
Eintrag, solange er offen ist. Das **Etikett** neben „Notiz“ setzt die Variante des
offenen Eintrags, auch nachträglich, und legt eine neue an. Uhr, Timer und
Plan-Ablauf tragen die gewählte Variante mit ein.

**In der Übung** (Bearbeiten → Varianten) bekommt jede Variante einen Namen, ein Symbol
oder ein Kürzel bis drei Zeichen und eine Beschreibung. Passen nicht alle Namen in eine
Zeile, zeigt die Ausführung nur die Symbole — Name und Beschreibung der gewählten stehen
darunter. Umbenennen kann die bisherigen Einträge mitnehmen; Entfernen lässt sie, wie
sie sind.

**Im Plan** steht die Zeile in jeder Planübung; unter „Im Plan einstellen“ schaltest du
sie für eine Planübung aus. Das Ziel der Übung kann eine Variante vorgeben („Ziel-Variante“
unter den Varianten).
"""


PARAMETER_MD = """\
**Parameter** sind, was du beim Üben als geleistet antippst — in jedem Plan (weniger stellst
du in „Im Plan einstellen“ ein). Oben die Knöpfe: ein Tipp schaltet einen Parameter ein oder
aus. Darunter je eingeschaltetem Parameter seine Karte.

**Name**: Jeder Parameter trägt in dieser Übung seinen eigenen Namen — „Haltezeit“ darf
„Hängen“ heißen, die Skala „Anstrengung“. Die Einheit bleibt.

**Chips** sind die Werte, die beim Üben als Knöpfe stehen (`+15`, `45°`). Angetippt =
angeboten; „eigener“ ergänzt einen Wert; ein nicht gewählter Chip hat ein ✕ und verschwindet
damit aus der Wahl — ein eigener für immer, ein Vorschlag des Vorrats (10, 15, 20) steht beim
nächsten Öffnen wieder da. Ohne gewählten Chip gibt es beim Üben nur das freie Feld.

**Sätze** (bei Wiederholungen und Haltezeit): an = Eingabe je Satz (3 × 15); aus = eine Zahl
je Eintrag („263 Liegestütze heute“), angezeigt wird die Summe.

**Menge oder Ausprägung**: Wiederholungen und Zeiten werden addiert (3 × 50 = 150). Winkel,
Gewicht und Seite wählst du vorher aus — sie trennen: Wandsitz 45° ist nicht Wandsitz 90°.
Ja/Nein, Skala und Freitext gelten für den offenen Eintrag — sie trennen nicht.

**Ziel**: Was auf der Karte unter „Ziel“ steht (3 × 15, 45 s), trägt „Wie geplant“ beim Üben
mit einem Tipp ein. Es gilt in jedem Plan, der kein eigenes hat — in „Im Plan einstellen“
kann ein Plan abweichen. Leer heißt: kein Ziel.
"""

UHR_MD = """\
**Uhr** heißt Stoppuhr (zählt vorwärts) oder Timer (zählt herunter, ein oder mehrere
Abschnitte). **Uhr beim Üben** aus: keine Uhr in der Übung — „Gemacht“ hakt nur ab.

**Zeit der Uhr zählt**: Jeder Lauf ist ein Satz im offenen Eintrag — als **Haltezeit** (je
Satz) oder als **Zeit** (gesamt), das stellst du unter „Zählt als“ ein, sobald die Übung
Haltezeit hat; ohne Haltezeit zählt die Uhr immer als Zeit. Beim Üben schaltest du „zählt“
in der Zeile für jetzt um. Aus: Läufe tragen nur „gemacht“ ein.

**Timer**: Der erste Timer der Übung ist die Vorgabe; ein Plan kann in „Im Plan einstellen“
oder im Uhrenplan (Plan bearbeiten → Uhren) einen anderen nehmen. Teile (Vorbereitung,
Training, Cooldown), „zählt“ und Takt je Abschnitt stellst du im Timer-Editor ein — er
speichert vorher die Übung. „Timer hinzufügen“ legt einen neuen an oder übernimmt eine
**Vorlage** aus dem Timer-Werkzeug (Pille „Timer“ oben) als Kopie.

**Zeit stellen**: Ein Tipp auf eine Zeit öffnet überall dasselbe Blatt — Räder für Minuten
und Sekunden, Tippfeld und die Schnellzeiten aus den Einstellungen.

**Knöpfe** einer laufenden Uhr, überall gleich: **Pause · Weiter** halten an und setzen fort,
**Nächster** springt zum nächsten Abschnitt, **Fertig** beendet und trägt ein, **Abbrechen**
beendet ohne Eintrag.
"""

TAKT_MD = """\
**Ein Takt** ist eine Folge von Phasen — jede mit Namen, Sekunden, Art und Klang — die als
Schleife läuft, solange die Uhr läuft: *ein · halten · aus · halten*, *ab · halten · auf* oder
ein einzelner Metronomschlag.

- **Art** sagt, was die Phase bedeutet: *Einatmen*, *Ausatmen*, *Halten* (Atmung) oder *Ab*,
  *Auf* (Bewegung), sonst *Frei*. Die Auswertung der Messung liest später die Soll-Phasen
  daraus; der Name ist nur die Anzeige.
- **Tempo** (0,5×–2×) dehnt oder rafft alle Phasen. Während die Uhr läuft, wirkt der Regler
  sofort und nur für jetzt — gespeichert wird über das Blatt („In die Übung“, „In den
  Abschnitt“, „In die Bibliothek“).
- **Wo er gilt:** an der Übung überall, wo sie geübt wird; an einem Timer-Abschnitt nur
  dort (vor der Übung); über den Takt-Knopf an der Uhr „für jetzt“ (geht vor allem anderen).
- **Takt zählt:** Ist der Schalter an (bei den Bewegungs-Vorlagen von Haus aus), ist jede
  volle Runde eine Wiederholung — auch ohne Sensor und ohne Stoppuhr-Zeit. Die Zahl steht als
  „Takt 12“ in der Zählzeile, ±1 korrigiert sie, „Fertig“ trägt sie ein; sie ist eine Vorgabe,
  keine Messung. Zählt der Sensor, zählt er — der Takt steht daneben („Takt 12 · Sensor 11“).
- **In der Messung:** Läuft eine Aufnahme, bekommt ein Atemtakt Beginn und Ende als Notiz,
  das Protokollfeld „Atmung“ wird „getaktet“, und die Soll-Phasen stehen neben den
  gemessenen im Beiwerk — die Auswertung zeigt Soll gegen Ist.
- **Bild der Bewegung:** Ein eigenes Bild (auch ein GIF) an der Übung läuft neben der
  Takt-Anzeige, als Schleife — nicht synchron zum Takt.

Die Vorlagen sind feste Zahlen ohne Wirkversprechen: Die App empfiehlt keine Rate aus
Messwerten.
"""

BESCHLEUNIGUNG_MD = """\
**Was gemessen wird:** Hat das verbundene Gerät einen Beschleunigungssensor, steht beim Üben
in der Karte „Eintragen“ der Knopf **„Wdh. zählen“**. Ab dem Tipp zählt der Sensor die
Wiederholungen aus der Bewegung — rückwirkend nichts, und erst ab dann läuft der Sensor (das
schont den Akku). **−1** und **+1** korrigieren, was er zählt; angezeigt und eingetragen wird
Sensor plus Korrektur. „Fertig“ und das Abhaken der Übung tragen die Zahl als Satz in den
offenen Eintrag; „Zählen abbrechen“, eine andere Übung oder eine Minute ohne Bewegung tragen
nichts ein — der Lauf steht dann unter „Läufe heute“ und lässt sich dort eintragen.

**Wiederholungen** gibt es nur bei einer Übung mit einem Parameter der Art
„Wiederholungen“ — ohne ihn ist der Schalter ausgegraut: Der Sensor wüsste nicht, wohin mit
der Zahl. Hat die Übung mehrere, wählst du unter „Zählt in“, welches.

**Bewegung** ist die Vorlage, nach der der Sensor zählt: **Automatisch** nimmt die
Hauptachse der Bewegung und passt zu jedem Gerät; **Kniebeuge** nimmt die Neigung des
Rumpfs (geprüft nur mit dem Brustgurt — an einem anderen Gerät zählt die Übung automatisch
und sagt es in der kleinen Zeile); **Liegestütz** ist eine Erwartung ohne Messdaten. Gezählt
wird immer am **Umkehrpunkt oben**: Eine Wiederholung ist vollendet, wenn du in die
Ausgangslage zurückkommst — die Zahl springt dann, nicht schon am tiefsten Punkt. Eine
**halbe** Wiederholung (deutlich weniger Weg als sonst) steht klein daneben („2 halbe“) und
zählt nicht; eine Wiederholung, die der Sensor zu früh meldete, nimmt er zurück (die Zahl
sinkt einmal), deine Korrekturen bleiben.

**Atmung** geht in jeder Übung, denn jede kann eine Atemkomponente haben; von selbst an ist
sie bei Übungen vom Typ „Atmung“. Ein Prototyp (hrv-core, `prototyp.atemzuege`) erkennt aus
der Atemwelle des Gurts die Atemzüge und die Phase jetzt (▲ einatmen, ▼ ausatmen) und nennt
die Rate je Minute, sobald ein halbes Minutenfenster ruhig und gleichmäßig war. Die Atmung
läuft nebenbei — Sätze, Chips und die Uhr berühren sie nicht — und bleibt als Beiwerk neben
der laufenden Messung; ins Tagebuch kommt davon nichts. Erprobt ist das mit dem Brustgurt
sitzend und liegend; langsames **und** flaches Atmen zählt der Prototyp noch unsicher.

**Geräte:** heute Polar H10 (Brustgurt) und Polar Verity Sense — bei der Verity Sense ist der
erste gezählte Satz zugleich die Probe. Verbunden genügt, eine Aufnahme braucht es nicht.

**Prototyp:** Das Verfahren ist noch in Entwicklung (hrv-core, `prototyp.wiederholungen`);
es zählt jede Wiederholung, sobald sie geschieht, eingestellt bisher an wenigen Sätzen eines
Menschen mit dem Brustgurt. Gespeichert
werden nur Ergebnisse — Wiederholungen je Satz mit ihren Zeiten und deine Korrekturen —, nie
die Rohdaten der Beschleunigung; die gibt es nur im Diagnosemodus. Entweder zählst du oder der
Sensor: Beides zugleich ist nur zum Prüfen gedacht (Diagnosemodus).
"""

SYMBOL_MD = """\
**Symbol oder Bild**: Ein Tipp auf das Symbol oben öffnet die Auswahl — die Symbole, oder
ein eigenes Foto aus der Fotoauswahl (verkleinert, ohne Ortsangabe) oder aus der Kamera.
Ein Foto zeigt die Übung überall rund statt des Symbols.

**Die Ablage** oben in der Auswahl sind alle eigenen Bilder. Ein Tipp nimmt eines für diese
Übung; das ✕ löscht es aus der Ablage — Übungen, die es trugen, zeigen wieder ihr Symbol.
Bilder bleiben auf diesem Gerät: nie im Paket, im Export oder in der Sicherung über das Netz.
"""


UEBUNGEN_MD = """\
**Kopien** — Wandsitz 45° und Wandsitz 90°, Liegestütz eng und weit: Der Knopf
„Kopie anlegen“ oben in den Übungsdetails legt eine eigene Übung an, die du dann
anpasst. Jede Übung hat im Verlauf ihre eigene Kachel.

**Pakete** — Übungen kommen über Pakete. Die mitgelieferten stehen im Paket
„Standard“, weitere (Qigong, Pilates, Yoga, eine Sammlung von jemand
anderem) importierst du im *Paketmanager* (Einstellungen oder unten im Katalog).
Aus welchem Paket eine Übung stammt, steht klein hinter ihrer Beschreibung.

Was du selbst anlegst oder kopierst, ist eine **eigene Übung** und gehört zu
keinem Paket — ein Import ändert sie nie.

Ein **Import** legt neue Übungen an und bringt die Übungen desselben Pakets auf
den Stand der Datei; was du an ihnen geändert hast, geht dabei verloren. Fehlende
Typen und Regionen kommen mit. Einträge im Verlauf bleiben immer, wie sie sind.

**Auf Paketstand setzen** — Jede Übung eines Pakets kennt ihren Stand aus dem
Paket. Hast du sie geändert, steht hinter der Beschreibung „geändert“; unten in
der Übung holst du den Paketstand zurück, im Paketmanager auch für alle.

**Entfernen** — Im Paketmanager entfernst du ein Paket wieder: Seine Übungen
kommen in den Papierkorb und verschwinden aus den Plänen, Einträge bleiben.
„Wieder installieren“ oder ein neuer Import holt alles zurück.

Ein **Export** schreibt ausgewählte Übungen in eine Paketdatei zum Teilen — ohne
Einträge, Messungen oder Strecken.
"""

ATMUNG_MD = """\
Die App liest die **Atemfrequenz aus dem Herzschlag**: Beim Einatmen schlägt das
Herz etwas schneller, beim Ausatmen langsamer (respiratorische Sinusarrhythmie,
RSA). Im Tachogramm ist das eine Welle — ihre Frequenz ist die Atemfrequenz, ihre
Höhe die Kachel „Atemschwankung“.

**Warum „unter 8/min“?** Im selben Signal steckt eine zweite Welle: die
Blutdruckregulation (Mayer-Welle) schwingt etwa alle 10 Sekunden — das sähe aus
wie 6 Atemzüge je Minute. Im Sitzen und besonders im Stehen ist sie oft stärker
als die Atemschwankung. Unter 8 Atemzügen je Minute ist aus dem Herzschlag allein
nicht zu unterscheiden, ob die Atmung oder der Blutdruck schwingt. Darum steht
dort normalerweise keine Zahl, sondern der Grund: „langsame Schwingung unter
8/min“.

**Atemübung an** heißt: Du sagst der App, dass du gerade bewusst langsam atmest —
etwa 6 Atemzüge je Minute (Resonanz- oder Kohärenzatmung). Dann zählt auch die
langsame Welle als Atmung, aber nur, wenn sie klar überwiegt (mindestens 70 % der
Schwankung liegen um ihren Gipfel) und der Herzschlag je Atemzug deutlich
schwankt (mindestens 50 ms zwischen kürzestem und längstem Abstand). Ist daneben
schnelleres Atmen deutlich zu sehen, gilt weiter das.

**Atemübung aus** (Vorgabe): Atemfrequenz nur ab 8/min.

Umschalten: live mit dem Knopf „Atemübung“, der bei langsamer Schwingung in der
Kachel Atemfrequenz erscheint, oder in den Einstellungen unter „HRV-Messung“ im
Abschnitt „Atmung“. Die Wahl gilt auch beim Ansehen von Aufzeichnungen.

**Wann gibt es keine Zahl?** Die App prüft, statt zu schätzen: genug saubere
Schläge, ein deutlicher Gipfel, einzelne Atemzüge von ähnlicher Länge, eine
spürbare Schwankung, mindestens drei Herzschläge je Atemzug und ein Puls unter
110 bpm. Passt etwas nicht, steht der Grund in der Kachel. Lieber keine Zahl als
eine falsche — die Werte beschreiben, sie bewerten nicht.
"""

HERZFREQUENZ_MD = """\
**Herzfrequenz-Sicht** (Ben, 29.10.2026). Die große Zahl ist die Herzfrequenz aus den
Schlagabständen — bei reinen Pulsgebern die des Geräts. Daneben der Anteil an deiner
**Herzfrequenzreserve**: Ruhe-HF = 0 %, HFmax = 100 %.

- **Ruhe-HF** kommt aus einem Eintrag, einer Morgenmessung (tiefstes 30-s-Mittel), einer
  Nacht (tiefstes 2-h-Mittel) oder dem Tagesfeld „Ruhepuls“. **HFmax** aus Ergometrie,
  Feld-Maximaltest, dem Feldmaximum deiner Aufzeichnungen (nach deiner Bestätigung) oder,
  als Startwert, aus der Formel 211 − 0,64 · Alter (Streuung ± 11 bpm). Welcher Wert gilt,
  entscheidet die genaueste vorhandene Quelle; „festsetzen“ pinnt einen Wert.
- **Bereiche** sind Stufen deiner Reserve — drei (an den Schwellen), fünf (Leitlinie),
  zehn (je 10 %) oder eigene. Helle Streifen an den Grenzen zeigen die Unsicherheit.
- **Zeit je Bereich** zählt für den Bezug Aufnahme, Abschnitt oder 5 min.
- **Erholung (HRR):** HF am Ende der Belastung minus HF nach 30 / 60 / 120 s. Woran und in
  welcher Haltung — nur gleiche Paare sind vergleichbar.
- **Schwellen** kommen aus Labor, Laktat, DFA α1 (EKG-Gurt: HF, bei der α1 in einer Rampe
  durch 0,75 bzw. 0,5 geht) oder dem Talk-Test — sonst geschätzt.

**Wann die App dir Werte vorschlägt — und wann nicht.** Nie beim Üben, nie als Dialog. Nach
einer Aufnahme stehen in ihrer Auswertung unter „Vorschläge fürs Profil“ nur Zeilen mit
Knopf: Ruhe-HF nach einer Messung von 4–20 min, Nacht-HF nach einer Nacht (≥ 4 h zwischen
20 und 10 Uhr), HFmax nach einem Feldmaximum, Schwellen nach Talk-Test oder α1-Rampe. Gesetzt
wird nur, was du antippst. Messwerte gelten 14 Tage (Ruhe-HF), Tests 90 Tage, Labor ein Jahr;
danach rechnet die App mit dem letzten Wert weiter und zeigt sein Datum. Ob Infekt, Urlaub
oder Pause die Ruhe-HF verschieben, siehst du im Verlauf an der 7-Tage-Baseline — die App
fragt nicht nach.

**Signal über einer Grenze:** Wenn du willst, spielt die App leise einen Klang (Vorgabe
Klangschale), solange deine Herzfrequenz über einer Grenze liegt, die du selbst setzt —
höchstens alle 3 bis 10 s. Einstellungen → Herzfrequenz oder das Blatt „Fenster &
Darstellung“ der Herzfrequenz-Sicht; Lautstärke und Regler wie bei den Timer-Signalen.

Die App zeigt, wo du bist und warst. Sie bewertet nichts und gibt keinen Rat; die Bereiche
und das Signal sind deine Werte wie ein Timer. Einstellungen → Herzfrequenz.
"""

#: Thema → (Titel, Text, Tooltip des Knopfs)
#: Was die Knöpfe einer Planübung tun — im „?“ des Plans und der Einzelübung (Ben,
#: 7.11.2026: nicht mehr als grauer Text, kein eigenes i)
KNOPF_LEGENDE = """\
- **Gemacht** hakt nur ab.
- **Wie geplant** übernimmt das Ziel der Übung (oder des Plans).
- **Uhr** (Stoppuhr, Timer) stoppt die Zeit; „zählt“ heißt, sie geht als Satz in den Eintrag.
- **+Zahl** hängt einen Satz an, **Eintragen** nimmt Sätze × Wert.
- **Notiz** schreibt einen Satz ins Tagebuch, das **Etikett** setzt die Variante.
- **i** öffnet die Übungsseite; die **Uhr** am Block die Uhr dieser Übung — die Pille
  **Timer** oben rechts ist das Werkzeug (Stoppuhr, Zeit, Vorlagen).
- **‹ ›** oder Wischen wechselt die Übung; **2/6** in der Mitte zeigt den Gesamtplan.
"""

PLAN_MD = KNOPF_LEGENDE + "\n**So wird eingegeben**\n\n" + NOTATION_MD

WORKOUT_MD = """\
**Workout** heißt: Der Plan läuft von vorn bis hinten durch, Übung für Übung mit ihrem Timer.

**Hart oder weich** — eine Haltung, vor dem Start wählbar, mit drei Folgen:
- **Hart**: Übungen folgen von selbst, Bedingungen gelten. Ist der Timer ab, beginnt sofort die
  nächste; eine verfehlte Bedingung führt in den Zweig oder zu „Noch einmal“.
- **Weich**: Du gibst das Tempo — der Timer zählt ins Minus („−0:23“), bis du tippst;
  Bedingungen sind Vorschläge („Trotzdem weiter“ steht offen). Eingetragen wird die
  tatsächliche Zeit.
- Übungen ohne Timer warten in beiden Fällen auf „Fertig“.

**Weiter, wenn …** steht an der Übung („Übung bearbeiten“) und je Plan („Im Plan einstellen“,
Uhrenplan): *Zeit ab*, *Wiederholungen* (Sensor oder Takt zählen), *Wiederholungen in einer
Zeit* oder *Abhaken*. **Pflicht** heißt: „Weiter“ erst, wenn erfüllt — ein Inhalt (Text, Link)
erscheint erst dann. Abbrechen geht immer.

**Zweige:** Jeder Schritt gehört zu einem Zweig (A = Hauptzweig, B, C, D). „Erfüllt →“ führt
zur nächsten Übung im Zweig oder zu einer gewählten; „nicht erfüllt →“ bietet eine andere an —
zurück nach A, weiter in B, wohin du willst.

Läuft eine Aufnahme, wird das Workout ein Abschnitt in ihr — die Übungen liegen darin.
"""

THEMEN: dict[str, tuple[str, str, str]] = {
    "workout": ("Workout", WORKOUT_MD, "Workout: Übergang, Bedingungen, Zweige"),
    "notation": ("So wird eingegeben", NOTATION_MD, "Wie gebe ich ein?"),
    "plan": ("Üben im Plan", PLAN_MD, "Knöpfe und Eingabe"),
    "varianten": ("Varianten", VARIANTEN_MD, "Was sind Varianten?"),
    "parameter": ("Parameter, Chips und Ziel", PARAMETER_MD, "Parameter, Chips und Ziel"),
    "uhr": ("Uhr", UHR_MD, "Uhr: Stoppuhr, Timer, zählt, Zeit stellen"),
    "takt": ("Takt", TAKT_MD, "Takt, Tempo und „Takt zählt“"),
    "beschleunigung": (
        "Beschleunigungssensor",
        BESCHLEUNIGUNG_MD,
        "Was misst der Beschleunigungssensor?",
    ),
    "symbol": ("Symbol oder Bild", SYMBOL_MD, "Symbol oder eigenes Bild"),
    "uebungen": ("Varianten und Pakete", UEBUNGEN_MD, "Varianten und Pakete"),
    "atmung": ("Atemfrequenz und Atemübung", ATMUNG_MD, "Was heißt „Atemübung“?"),
    "herzfrequenz": ("Herzfrequenz-Sicht", HERZFREQUENZ_MD, "Was zeigt die Herzfrequenz-Sicht?"),
}


def hilfe_dialog(thema: str = "notation") -> ft.AlertDialog:
    titel, text, _ = THEMEN[thema]
    return text_dialog(titel, text)


def text_dialog(titel: str, text: str) -> ft.AlertDialog:
    """Ein Hilfefenster mit Markdown — für Themen (`hilfe_dialog`) und Texte, die eine Seite
    selbst zusammenstellt (das „i“ der Übungsseite)."""
    return ft.AlertDialog(
        title=ft.Text(titel),
        content=ft.Container(width=420, content=ft.Markdown(text)),
        scrollable=True,
    )


def notation_dialog() -> ft.AlertDialog:
    return hilfe_dialog("notation")


def hilfe_knopf(page: ft.Page, groesse: int = 20, thema: str = "notation") -> ft.Control:
    """Ein Fragezeichen, das das Hilfefenster zum Thema öffnet."""
    return ft.IconButton(
        ft.Icons.HELP_OUTLINE,
        icon_size=groesse,
        tooltip=THEMEN[thema][2],
        on_click=hilfe_oeffner(page, thema),
    )


def hilfe_oeffner(page: ft.Page, thema: str = "notation") -> Callable[[], None]:
    def oeffnen() -> None:
        page.show_dialog(hilfe_dialog(thema))

    return oeffnen


__all__ = [
    "ATMUNG_MD",
    "BESCHLEUNIGUNG_MD",
    "NOTATION_MD",
    "TAKT_MD",
    "THEMEN",
    "UEBUNGEN_MD",
    "VARIANTEN_MD",
    "WORKOUT_MD",
    "hilfe_dialog",
    "hilfe_knopf",
    "hilfe_oeffner",
    "notation_dialog",
    "text_dialog",
]
