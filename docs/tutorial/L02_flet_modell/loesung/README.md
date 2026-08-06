# L02 — Lösungen

## Aufgabe 1: update()

**1. Was ist passiert?**

`stand_ohne` wurde erhöht, und `anzeige_ohne.value` wurde auf den neuen Wert
gesetzt. In Python ist alles korrekt. Nur wurde die Änderung nie über die Brücke
zu Flutter geschickt — und Flutter zeichnet, was es zuletzt gehört hat.

Deshalb der Knopf „Wahrheit zeigen": er beweist, dass der Wert stimmt.

**2. Warum dieses Verhalten?**

Jede Übertragung über die Brücke kostet. Ohne Sammeln wäre das hier vier
Übertragungen:

```python
titel.value = "..."
untertitel.value = "..."
fortschritt.value = 0.5
knopf.disabled = True
page.update()  # so: eine einzige
```

Bei einer Liste mit 200 Einträgen ist der Unterschied nicht mehr theoretisch.

**3. `page.update()` oder `control.update()`?**

- `page.update()` — der Normalfall. Prüft den ganzen Baum auf Änderungen.
  Bequem und für kleine Oberflächen völlig ausreichend.
- `control.update()` — wenn sich genau ein Element ändert und der Baum groß ist.
  Etwa der Pulswert während einer Live-Messung: er ändert sich jede Sekunde,
  der Rest des Bildschirms nicht.

Faustregel: `page.update()`, bis es spürbar langsam wird. Vorzeitige
Optimierung kostet Lesbarkeit ohne Gegenwert.

## Aufgabe 2: Die Karte

**1. Warum `expand=True` auf der mittleren Column?**

Ohne sie wäre die Column nur so breit wie ihr Inhalt. Das Chevron rechts würde
direkt am Text kleben statt am rechten Rand. Mit `expand=True` nimmt sie allen
Platz zwischen Icon und Chevron ein und drückt das Chevron nach außen.

**2. Ohne `expand`:** Die Karte schrumpft auf Inhaltsbreite, das Chevron rutscht
nach links. Bei unterschiedlich langen Namen sind die Chevrons dann nicht mehr
untereinander — unruhig.

**3. `max_lines` und `overflow`:** Ohne sie wächst die Karte an einer langen
Beschreibung in die Höhe, und die Liste wird unregelmäßig. `max_lines=2` deckelt
die Höhe, `ELLIPSIS` hängt „…" an statt hart abzuschneiden.

## Aufgabe 3: Kategorie-Markierung

```python
def kategorie_chip(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.padding.symmetric(2, 8),
        border_radius=10,
        bgcolor=ft.Colors.TERTIARY_CONTAINER,
        content=ft.Text(text, size=10, color=ft.Colors.ON_TERTIARY_CONTAINER),
    )
```

Und in der Karte, in der mittleren `Column`:

```python
(
    ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(uebung["name"], weight=ft.FontWeight.BOLD, size=15),
            kategorie_chip(uebung["category"]),
        ],
    ),
)
```

`TERTIARY_CONTAINER` mit `ON_TERTIARY_CONTAINER` als Textfarbe — das Paar
funktioniert in beiden Modi. Eine feste Farbe wie `"#E0E0E0"` wäre im
Dunkelmodus eine grelle helle Fläche.

## Aufgabe 4: Wiederholungszähler

```python
import flet as ft

ZIEL = 15


def main(page: ft.Page) -> None:
    page.title = "Wiederholungen"
    page.padding = 40
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    stand = 0
    anzeige = ft.Text("0", size=96, weight=ft.FontWeight.BOLD)
    ziel_text = ft.Text(f"von {ZIEL}", size=16, opacity=0.6)

    def zeichnen() -> None:
        anzeige.value = str(stand)
        anzeige.color = ft.Colors.PRIMARY if stand >= ZIEL else None
        ziel_text.value = "geschafft!" if stand >= ZIEL else f"von {ZIEL}"
        page.update()

    def plus(e):
        nonlocal stand
        stand += 1
        zeichnen()

    def minus(e):
        nonlocal stand
        stand = max(0, stand - 1)  # nicht ins Negative
        zeichnen()

    def reset(e):
        nonlocal stand
        stand = 0
        zeichnen()

    page.add(
        ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            controls=[
                anzeige,
                ziel_text,
                ft.Container(height=20),
                # Groß, weil er beim Training getroffen werden muss.
                ft.ElevatedButton(
                    "+1",
                    on_click=plus,
                    height=72,
                    width=220,
                    style=ft.ButtonStyle(text_style=ft.TextStyle(size=24)),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        ft.TextButton("−1", on_click=minus),
                        ft.TextButton("Zurücksetzen", on_click=reset),
                    ],
                ),
            ],
        )
    )


ft.app(target=main)
```

**Zwei Dinge, die hier bewusst so sind:**

`zeichnen()` als eigene Funktion. Die drei Handler ändern nur den Zustand und
rufen dann eine Stelle auf, die die Anzeige daraus ableitet. Ohne das müsste
jeder Handler alle Anzeigeregeln kennen — und beim vierten vergisst man eine.

`max(0, stand - 1)` verhindert negative Wiederholungen. Kleinigkeit, aber genau
solche Kleinigkeiten fallen später als „Fehler" auf.

## Zum Nachdenken

**1. `page.update()` bei 200 Einträgen**

Flet vergleicht dann den gesamten Baum mit dem letzten Stand. Bei einem Zähler,
der sich jede Sekunde ändert, wäre das 200 Vergleiche pro Sekunde für eine
Änderung. Deshalb bei Live-Anzeigen `control.update()`.

**2. Warum `ListView` statt `Column`?**

`Column` baut **alle** Kinder auf, auch die außerhalb des Bildschirms.
`ListView` baut nur das auf, was sichtbar ist, und ergänzt beim Scrollen —
und scrollt überhaupt erst von selbst.

Bei 13 Übungen ist das egal. Bei 200 nicht mehr. Und da wir wissen, wohin es
geht, nehmen wir gleich das Richtige.
