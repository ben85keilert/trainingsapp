# L03 — Übung

## Aufgabe 1: Zustand beobachten

Starte `beispiel_03.py`, zähl beide Zähler auf 5, wechsle die Ansicht und komm
zurück.

**Fragen:**
1. Was steht jetzt in den beiden Zählern? Warum?
2. Die Ansicht wird bei jedem Wechsel neu gebaut. Wo genau geht der linke
   Zählerstand verloren?
3. Stell dir vor, eine HRV-Messung läuft. Warum darf sie nicht in der Ansicht
   liegen?

## Aufgabe 2: Auswahl merken

Erweitere `beispiel_03.py`: Nach dem Wechsel soll die Navigationsleiste den
richtigen Eintrag hervorheben. Zurzeit springt sie zurück auf 0, wenn die
Ansicht neu gebaut wird.

Tipp: `selected_index` gehört ebenfalls in den `AppState`.

## Aufgabe 3: Detailansicht mit Route

Erweitere `beispiel_02.py` um eine dritte Ebene: In der Detailansicht ein Knopf
„Video ansehen", der zu `/uebung/<key>/video` führt und eine Ansicht mit dem
Titel und einem Platzhalter zeigt.

**Frage:** Wie viele Ansichten liegen dann auf dem Stapel? Was passiert bei
zweimal Zurück?

## Aufgabe 4: Beides verbinden

Baue `mein_geruest.py` — die Struktur, die die App wirklich bekommt:

- `AppState` mit `subject_name`, `nav_index` und `uebungen` (aus dem Seed geladen)
- Navigationsleiste mit vier Zielen
- „Übungen" zeigt die Liste; ein Tipp öffnet über eine Route die Detailansicht
- die anderen drei Ansichten dürfen Platzhalter sein
- der Ansichtswechsel merkt sich die Auswahl

Das ist im Kern schon M1. Was du hier baust, wandert danach nach
`src/trainingsapp/ui/`.

## Zum Nachdenken

In `beispiel_03.py` steht der Zustand in einem `@dataclass`.

1. Warum nicht einfach globale Variablen?
2. Warum kein Dictionary?
3. Was spricht dagegen, den Zustand direkt an `page` zu hängen (`page.state = ...`)?

[Lösungen](loesung/)
