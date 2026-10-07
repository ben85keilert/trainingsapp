# L01 — Lösungen

## Aufgabe 2: Syntaxfehler bei Hot Reload

Flet zeigt den Fehler im Terminal und behält das letzte funktionierende Fenster.
Nach dem Reparieren und Speichern lädt es normal weiter — kein Neustart nötig.

Das ist der eigentliche Gewinn: Ausprobieren wird billig. Wenn jeder Versuch
einen Neustart kostet, probiert man weniger aus.

## Aufgabe 3: Die Importregel

Die Meldung sieht so aus:

```
AssertionError: core/ darf ['flet'] nicht importieren:
  core/units.py: flet
```

**Warum ein Test besser ist als eine Notiz:**

Eine Notiz in der Dokumentation liest man einmal. Ein Test meldet sich bei
*jedem* Lauf, auch in vier Monaten, auch wenn jemand anderes den Code anfasst,
auch wenn der Verstoß versehentlich passiert.

Solche Regeln erodieren sonst zuverlässig. Nicht aus Nachlässigkeit — sondern
weil in dem Moment, in dem man sie bricht, immer ein guter Grund vorliegt
(„nur schnell dieses eine Icon"). Der Test zwingt dazu, den guten Grund
auszusprechen statt ihn stillschweigend anzunehmen.

## Aufgabe 4: mein_erstes.py

```python
import flet as ft


def main(page: ft.Page) -> None:
    page.title = "Mein Trainingsassistent"
    page.padding = 30

    page.add(
        ft.Column(
            spacing=10,
            controls=[
                ft.Text("Benjamin", size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text("Schulter-Außenrotation"),
                ft.Text("Nackendehnung seitlich"),
                ft.Text("4-7-8-Atmung"),
            ],
        )
    )


ft.run(main)
```

Varianten, die genauso richtig sind: `ft.ListView` statt `Column` (scrollt bei
vielen Einträgen), oder eine Schleife über eine Liste statt drei einzelner
`ft.Text`.

## Zum Nachdenken

**1. Warum ist es wichtig, dass die Domäne ohne Oberfläche läuft?**

- **Tests.** 81 Tests laufen in 0,3 Sekunden. Mit Oberfläche bräuchten sie einen
  Bildschirm, wären langsam und unzuverlässig.
- **Flet ändert sich.** Zwischen den Versionen hat Flet seine API mehrfach
  umgebaut. Was in `ui/` steht, muss dann angefasst werden. Was in `core/` und
  `hrv_core/` steht, nicht.
- **Wiederverwendung.** `hrv_core` könnte später auch in `praxis_gui` laufen
  oder in einem Auswertungsskript — beide haben keine Flet-Oberfläche.
- **Denken.** Die Trennung zwingt zu der Frage „was ist hier eigentlich die
  Aufgabe?", getrennt von „wie sieht das aus?".

**2. Was wäre der Nachteil, wenn `compute_time_domain` in einer Ansicht stünde?**

Man könnte es nur testen, indem man die Ansicht aufbaut und die Anzeige ausliest.
Ein Fehler in der Formel wäre nicht von einem Anzeigefehler zu unterscheiden.
Und wollte man dieselbe Rechnung an zweiter Stelle (Export, Verlauf), müsste man
sie kopieren — womit sie zwangsläufig irgendwann auseinanderlaufen.
