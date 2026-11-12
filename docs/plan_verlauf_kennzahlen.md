# Plan: Kennzahlen im Verlauf — was getrennt, was addiert wird

**Stand 12.11.2026 abends:** gebaut ist die Ansicht im Verlauf nach dem zweiten und dritten
Nachtrag in §4 (Aufteilen, Filter, gespeicherte Ansichten je Übung); §2 und der Anfang von §4
(Zählweise als feste Einstellung) sind überholt, §5 und §6 offen.

Entwurf vom 12.11.2026 (Ben: „wir müssen genauer auseinanderhalten, wie die Kennzahlen
getrennt, summiert usw. werden … Entwirf einen guten Plan, wie man Werte statistisch gut
aufarbeiten kann im Hintergrund einer guten Übersicht, was man sinnvollerweise trainiert
hat“). Noch nichts gebaut; offene Punkte in §7, im Katalog P191.

## 1. Ausgangslage

Die Rechnung kennt drei Rollen (`core/parameter.py`): **Menge** (Wiederholungen, Zeit,
Strecke — addierbar), **Ausprägung** (Variante, Gewicht, Winkel, Auswahl wie die Seite —
beschreibt das Wie) und **Beiwerk** (Skala, Text, Ja/Nein). Heute trennen die Ebenen
verschieden:

| Ebene | trennt nach |
|---|---|
| offener Eintrag | jeder Ausprägung |
| Tag (`core/tagesbilanz.py`, Bündel) | jeder Ausprägung |
| Kurve (`core/verlauf.linien`) | nur der Variante — 10 kg und 20 kg werden addiert |

Fest steht (Ben, 12.11.2026): Die Zählung bündelt **unabhängig von Paketen**; sie hängt nur
an den Einstellungen des Eintrags (seiner Kopie der Parameter).

## 2. Grundsatz

Innerhalb einer Menge (etwa Wiederholungen) gilt: **Verschiedene Ausführung wird getrennt
gezählt und nur auf Wunsch addiert.** Liegestütze kurz und lang gehalten sind zwei Zahlen.
Eine Ausnahme sind Ausprägungen, die **Teile eines Ganzen** sind: 40 links und 30 rechts
sind 70 einarmige Liegestütze, mit der Aufteilung daneben.

Jede Ausprägung einer Übung hat darum eine von zwei **Zählweisen**:

- **trennt** — jede Wahl ist eine eigene Reihe, nie still addiert;
- **addiert** — die Wahlen sind Teile; die Reihe zeigt die Summe und die Aufteilung
  („70 · links 40 · rechts 30“).

Vorgaben nach der Art des Felds, je Übung änderbar (§4):

| Ausprägung | Vorgabe |
|---|---|
| Variante | trennt |
| Gewicht | trennt |
| Winkel | trennt |
| Seite (links · rechts · beide) | addiert |
| andere Auswahl | trennt |

## 3. Die Reihe — eine Regel für Tag und Kurve

Eine **Reihe** ist die Übung plus die Wahl in allen *trennenden* Ausprägungen:
„Liegestütz · kurz“, „Kniebeuge · 20 kg“. Tag und Kurve rechnen mit derselben Funktion
(`core`, neu: Reihenschlüssel eines Eintrags nach den Zählweisen der Übung):

- **Tag:** je Reihe eine Zeile mit Summe, Sätzen und — bei addierenden Ausprägungen — der
  Aufteilung. Heute ist jede Ausprägung ein eigenes Bündel; links und rechts fielen damit
  künftig in eine Zeile zusammen.
- **Kurve:** je Reihe eine Linie (heute nur je Variante). Je Kennzahl wie bisher: Summe des
  Tages, bester Satz, Mittel (Skala), höchster Wert (Gewicht, Winkel).
- **Offener Eintrag:** bleibt, wie er ist — eine andere Ausführung beginnt einen neuen
  Eintrag, auch die andere Seite.

Die Zählweise kommt aus der **aktuellen Übung**, nicht aus der Kopie im Eintrag: Sie ist
eine Frage der Darstellung, keine Eigenschaft des Eintrags. Die Werte selbst liest die
Rechnung weiter aus der Kopie.

**Viele Reihen** (fünf Gewichte): Die Kurve zeigt die zuletzt benutzten vier, die übrigen
als Chips zum Zuschalten; die Farben bleiben je Reihe fest.

## 4. Einstellen und von Hand addieren

- **Je Übung** in „Übung bearbeiten“, an der Karte der Ausprägung: „Im Verlauf: getrennt
  zählen · zusammenzählen“. Gespeichert am Feld (`FieldSpec`, neues Attribut); reist in
  Paketen mit.
- **Von Hand addieren** im Verlauf: ein Schalter „Zusammen“ an der Kurve legt die gewählten
  Reihen zu einer Summe (für den Blick, nichts wird gespeichert). Am Tag steht unter mehreren
  Reihen einer Übung auf Wunsch „zusammen 110“.

**Nachtrag 12.11.2026 (Ben):** Die Seite war nur ein Beispiel — keine Vorgabe „addiert“ aus
der Art des Felds; alles trennt, bis man es in der Übung anders einstellt. Der Bereich heißt
**„Verlauf · Was zählt zusammen?“** (Skizzen „Zählung 1/2“): je Ausprägung „Getrennt ·
Zusammen“, darunter sofort die Reihen, die daraus entstehen. Dazu je **Menge** ein Schalter
**„Gesamt über alles“** (Ben: „egal wie sie ausgeführt wurde … wie die Haltezeit oder die
Übungsgesamtzeit steht“): eine zusätzliche Zeile und Linie mit der Summe über alle Reihen —
für Zeiten Vorgabe an, für Wiederholungen aus.

**Zweiter Nachtrag 12.11.2026 (Ben, Beispiel Einbeinstand: Variante blind/offen, dabei
Seite, Gewicht, Winkel):** Keine feste Einstellung je Übung, sondern eine **Ansicht im
Verlauf**: Grundausgabe ist alles getrennt (jede Kombination eine Zeile), dazu immer die
Zeile „Gesamt“. Eine Chipzeile **„Aufteilen nach“** nennt die Variante zuerst, dann die
Einstellungen (Seite · Gewicht · Winkel); ein abgewählter Chip summiert über diese
Einstellung. Nur „Winkel“ gewählt heißt: je Winkel eine Zeile, alles andere zusammen. Je
Zeile Summe **und** Anzahl („wie oft“). Die letzte Wahl merkt sich die App je Übung. Die
Abschnitte 2 und 4 (Zählweise als Einstellung der Übung) sind damit überholt, falls Ben das
so bestätigt.

**Dritter Nachtrag 12.11.2026 (Ben):** „Summiert nach bestimmten Filterkriterien. Diese sind
mehrfaktoriell einstellbar“ — in der Übung **und** im Verlauf; dazu **gespeicherte Ansichten**
für oft gebrauchte Kombinationen, auch in den Übungseinstellungen abgelegt. Skizzen „Verlauf
1–3“: Chips der Ansichten über „Aufteilen nach“, Blatt „Filter“ (je Einstellung die Werte,
die zählen) mit „Als Ansicht speichern …“, Karte „Verlauf · Ansichten“ in „Übung bearbeiten“
(umbenennen, löschen, welche beim Öffnen gilt). Die Rechnung dazu steht schon in
`core/verlauf.py` (`Aufteilung`, `dimensionen`, `linien(…, aufteilung)`), die Ablage der
letzten Wahl in `AppState.verlauf_aufteilung` — die Oberfläche wartet auf Bens Wort zu den
Skizzen.

## 5. Abgeleitete Zahl

**Volumen** (Wiederholungen × Gewicht, je Tag summiert) als weitere Kennzahl für Übungen mit
beidem. Sie macht Reihen verschiedener Gewichte vergleichbar, ohne Wiederholungen zu
addieren, die nicht zusammengehören. Nur eine Zahl, keine Wertung.

## 6. Übersicht: was habe ich trainiert

Über Übungen hinweg lassen sich Wiederholungen nicht addieren. Übergreifend zählbar sind nur
**Tage, Einträge und Zeit**. Die Übersicht (Verlauf, Woche) zeigt darum

- je **Typ und Region** (Kräftigung · Rumpf): an wie vielen Tagen, wie viele Einträge, wie
  viel Zeit — diese und die Vorwoche nebeneinander;
- je **Übung** die Reihen der Woche mit ihrer Summe.

Keine Bewertung, kein Soll, keine Empfehlung (`docs/recht/00_zweckbestimmung.md`).

## 7. Absicherung und offene Punkte

- **Einheit im Schlüssel der Kennzahl:** dasselbe Feld mit anderer Einheit (oder ohne
  Sätze) wird eine eigene Kennzahl statt still gemischt.
- **Offen (Ben):** Vorgaben in §2 so? · „beide“ bei der Seite: zählt als eigener Teil der
  Summe oder doppelt? · Volumen gewünscht? · Übersicht nach Typ/Region in diesem Umfang?
  · Zählweise je Übung oder zusätzlich je Planübung?

## 8. Stufen

1. Reihenregel in `core` (Zählweisen mit Vorgaben), Tag und Kurve darauf; Einheit im
   Schlüssel.
2. Einstellung in „Übung bearbeiten“, Paketfeld.
3. „Zusammen“ an Kurve und Tag, Begrenzung auf vier Linien.
4. Volumen.
5. Übersicht nach Typ und Region.
