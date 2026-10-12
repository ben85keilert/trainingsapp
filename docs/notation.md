# Notation — so wird eingegeben

Die App hat eine Schreibweise für alles, was man je Satz einträgt, und eine
für Einzelwerte. Derselbe Text steht im Hilfefenster der App
(`ui/components/hilfe.py`); wer hier ändert, ändert dort mit.

## Je Satz (Wiederholungen, Haltezeit)

| Eingabe | Bedeutung |
|---|---|
| `30` | ein Satz mit 30 |
| `3x15` oder `3×15` | drei Sätze mit je 15 |
| `15/15/20` oder `15,15,20` | drei Sätze, einzeln |
| `2x15/20` | zwei Sätze 15, dann ein Satz 20 |
| `+20` | einen Satz mit 20 an den heutigen Eintrag anhängen |

Gespeichert wird immer eine Liste je Satz: `[15, 15, 20]`. Angezeigt wird
kompakt: gleiche Werte als `3x15`, ein Satz als `30`, sonst `15/15/20`.
Daneben die Summe, etwa „50 Wdh. in 3 Sätzen".

Im Verlauf gibt es je Satzfeld zwei Kennzahlen: **Summe** (Standard) und
**Maximum je Satz** (`<übung>:reps:sum`, `<übung>:reps:max`).

## Zeiten

`30` sind Sekunden, `1:30` sind 90 Sekunden, `2min` geht auch. Je Satz
dieselbe Schreibweise: `3x30`, `45/60/30`, `1:30/45s`.

Eine `0` oder ein leeres Feld heißt **ohne Zeit**: gemacht, aber kein Punkt
auf der Kurve.

## Einzelwerte

Gewicht `40` oder `40kg`, Strecke `500` (Meter) oder `2km`, Winkel `45`,
Skala `0` bis `10`. Dezimalzahlen mit Punkt oder Komma, `12,5` wird 12.5.
In Satzlisten trennt deshalb der Schrägstrich sicherer als das Komma.

## Das Plus im Plan

Jede Übung mit Satzfeld bekommt im Planblock Chips `+10` `+15` `+20` (aus den
Chips der Übung, im Plan überschreibbar) und ein Feld für eigene Werte. Jeder
Tipp hängt einen Satz an den heutigen Eintrag dieser Übung an oder legt ihn an.
Technisch ist jedes Plus eine Korrektur mit Verweis auf den vorherigen Stand
(`replaces_entry_id`); der Eintrag bleibt unveränderlich, die Historie zeigt
jeden Satz.

## Hierarchie

Die **Übung** legt fest, welche Felder es gibt (aus dem Feldvorrat in
`core/result_spec.py`) und welche Chips Standard sind. Der **Plan** übernimmt
das und wählt je Übung die Stufe — nur abhaken, Chips, Freieingabe — und darf
Chips und Ziel setzen. Der **Eintrag** übernimmt den Plan und darf im Formular
wieder abweichen. Was unten anders gemacht wurde, sieht man hinterher und kann
den Plan anpassen.
Plan und Übung tauschen sich nur ausdrücklich aus: „Als Standard der Übung
setzen“ und „Standard der Übung übernehmen“ in der Planübung (`core/standards.py`).

## Menge, Ausprägung, Bündeln

Jedes Feld hat eine Rolle (`core/parameter.py`):

| Rolle | Felder | Wirkung |
|---|---|---|
| **Menge** | Wiederholungen, Haltezeit, Zeit gesamt, Strecke | wird addiert: 3 × 50 Liegestütze = 150 |
| **Ausprägung** | Winkel, Gewicht, Seite | trennt: Wandsitz 45° ≠ Wandsitz 90° |
| **Beiwerk** | Skala, Freitext, Ja/Nein | wird mitgeschrieben, weder addiert noch trennend |

Im Plan wählt man Ausprägungen *vor* dem Eintragen (Chips „Winkel: 45° 90°“);
sie wandern in jeden Eintrag. Ein „+30“ bei 45° hängt nie an den 90°-Eintrag an.

Die Tagesansicht bündelt „Nach Plan“ und „Nach Übung“ je **Übung + Ausprägung**
und addiert die Mengen (`core/tagesbilanz.py`). Ein Eintrag ohne Menge ist
**abgehakt** (leerer Haken) und wird getrennt ausgewiesen: „150 Wdh. aus 3
Einträgen · zusätzlich abgehakt“. „Chronologisch“ zeigt jeden Eintrag einzeln.

**Varianten** (Migration 007): Eine Kopie einer Übung ist eine Variante
(`exercise.family_id`) und teilt sich im Verlauf die Kachel des Originals. Wer
eine Variante getrennt führen will (Liegestütz einarmig), macht sie im Editor
eigenständig.
