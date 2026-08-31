# L02 — Das Flet-Modell

**Ziel:** Du verstehst, wie eine Flet-Oberfläche aufgebaut ist und wann sie sich
aktualisiert. Danach bauen wir die Hülle der App.

Zeit: ein bis zwei Stunden.

---

## 1. Alles ist ein Control

Eine Flet-Oberfläche ist ein **Baum aus Controls**. Ein Control ist ein
Python-Objekt, das ein Flutter-Widget beschreibt.

```python
ft.Column(
    controls=[
        ft.Text("Schulter-Außenrotation"),
        ft.Row(
            controls=[
                ft.Text("3x15"),
                ft.IconButton(ft.Icons.EDIT),
            ]
        ),
    ]
)
```

Der Baum:

```
Column
├── Text("Schulter-Außenrotation")
└── Row
    ├── Text("3x15")
    └── IconButton
```

`page` ist die Wurzel. `page.add(...)` hängt etwas hinein.

Es gibt vier Sorten, und mehr braucht man am Anfang nicht:

| Sorte | Beispiele | wofür |
|---|---|---|
| **Anzeige** | `Text`, `Icon`, `Image`, `ProgressBar` | zeigt etwas |
| **Eingabe** | `TextField`, `Checkbox`, `Slider`, `Dropdown` | nimmt etwas entgegen |
| **Aktion** | `ElevatedButton`, `IconButton`, `FloatingActionButton` | löst etwas aus |
| **Anordnung** | `Column`, `Row`, `Container`, `Stack`, `ListView` | ordnet andere an |

---

## 2. Die Sache mit `page.update()`

Das ist **die** Stolperfalle. Sie kostet fast jeden Flet-Anfänger einen
verlorenen Nachmittag.

```python
text = ft.Text("alt")
page.add(text)

text.value = "neu"     # ← ändert nur das Python-Objekt.
                       #   Auf dem Bildschirm steht weiterhin "alt".
page.update()          # ← JETZT geht die Änderung über die Brücke
```

**Warum ist das so?** Zwischen Python und Flutter liegt eine Brücke. Jede
Übertragung kostet. Würde Flet bei jeder Zuweisung sofort übertragen, wäre das
Ändern von zehn Werten zehn Übertragungen. So sammelst du die Änderungen und
schickst sie in einer.

Bei Ereignis-Handlern gilt: **am Ende `page.update()`.** Wenn du eine Änderung
siehst, aber nicht auf dem Bildschirm — das ist es fast immer.

Feiner geht es auch: `text.update()` aktualisiert nur dieses eine Control. Bei
langen Listen macht das einen spürbaren Unterschied.

---

## 3. Ereignisse

```python
def gedrueckt(e: ft.ControlEvent) -> None:
    zaehler.value = str(int(zaehler.value) + 1)
    page.update()  # nicht vergessen


ft.ElevatedButton("Wiederholung", on_click=gedrueckt)
```

`e` ist das Ereignis. `e.control` ist das Control, das es ausgelöst hat — sehr
nützlich, wenn mehrere Knöpfe denselben Handler benutzen:

```python
def ausgewaehlt(e: ft.ControlEvent) -> None:
    print("gewählt:", e.control.data)  # `data` ist frei belegbar


for uebung in uebungen:
    ft.ListTile(title=ft.Text(uebung.name), data=uebung.id, on_click=ausgewaehlt)
```

---

## 4. Anordnen

**`Column`** stapelt untereinander, **`Row`** nebeneinander.

```python
ft.Column(
    controls=[...],
    spacing=10,  # Abstand zwischen Kindern
    alignment=ft.MainAxisAlignment.CENTER,  # entlang der Achse (vertikal)
    horizontal_alignment=ft.CrossAxisAlignment.CENTER,  # quer dazu
)
```

Merkhilfe: Bei `Column` ist die Hauptachse senkrecht, bei `Row` waagerecht.
`alignment` betrifft immer die Hauptachse.

**`Container`** ist die Verpackung für ein einzelnes Control — Rand, Abstand,
Hintergrund, Ecken:

```python
ft.Container(
    content=ft.Text("3x15"),
    padding=12,  # innen
    margin=8,  # außen
    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    border_radius=8,
)
```

**`expand`** verteilt den übrigen Platz:

```python
ft.Row(
    controls=[
        ft.Text("links"),
        ft.Container(expand=True),  # frisst den Rest → schiebt auseinander
        ft.Text("rechts"),
    ]
)
```

---

## 5. Farben und Theme

Nie feste Farbwerte in die Controls schreiben. Stattdessen aus dem Theme:

```python
ft.Colors.PRIMARY  # Hauptfarbe
ft.Colors.ON_PRIMARY  # Text darauf
ft.Colors.SURFACE  # Hintergrund
ft.Colors.ON_SURFACE  # Text darauf
ft.Colors.ERROR
```

Diese Namen passen sich hellem und dunklem Modus automatisch an. Ein festes
`"#333333"` sieht im Dunkelmodus falsch aus.

Das Theme entsteht aus **einer** Grundfarbe:

```python
page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)
page.theme_mode = ft.ThemeMode.SYSTEM  # SYSTEM | LIGHT | DARK
```

Flet leitet daraus ein vollständiges, in sich stimmiges Schema ab — siehe
`src/trainingsapp/ui/theme.py`.

---

## 6. Beispiele

```bash
uv run flet run docs/tutorial/L02_flet_modell/beispiel_01.py   # Control-Baum
uv run flet run -d docs/tutorial/L02_flet_modell/beispiel_02.py   # update() sichtbar gemacht
uv run flet run docs/tutorial/L02_flet_modell/beispiel_03.py   # eine Übungskarte
```

**Beispiel 2 ist das wichtigste.** Es zeigt nebeneinander, was mit und ohne
`update()` passiert. Wenn dir das einmal klar ist, verlierst du den Nachmittag nicht.

---

## Stolperfallen

**Die Änderung erscheint nicht** — `page.update()` fehlt. Zu 90 % ist es das.

**`AssertionError: Control must be added to the page first`** — du rufst
`control.update()` auf, bevor es im Baum hängt. Erst `page.add(...)`, dann updaten.

**`expand=True` bewirkt nichts** — der Elternteil hat selbst keine feste Größe.
`expand` verteilt vorhandenen Platz; wo keiner ist, gibt es nichts zu verteilen.

**Feste Farbwerte** sehen im Dunkelmodus falsch aus. `ft.Colors.*` benutzen.

**Text wird abgeschnitten statt umgebrochen** — `ft.Text(..., max_lines=2,
overflow=ft.TextOverflow.ELLIPSIS)` oder in einen `Container` mit fester Breite.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L02b: Aufs Handy bauen**
