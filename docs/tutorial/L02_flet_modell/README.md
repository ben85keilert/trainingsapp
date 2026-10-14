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
| **Aktion** | `Button`, `IconButton`, `FloatingActionButton` | löst etwas aus |
| **Anordnung** | `Column`, `Row`, `Container`, `Stack`, `ListView` | ordnet andere an |

---

## 2. Die Sache mit `update()`

Zwischen Python und Flutter liegt eine Brücke. Eine Zuweisung wie
`text.value = "neu"` ändert **nur das Python-Objekt** — sichtbar wird sie erst,
wenn die Änderung über die Brücke geschickt wird. Das erledigt `update()`:

```python
text = ft.Text("alt")
page.add(text)

text.value = "neu"     # ← ändert nur das Python-Objekt
page.update()          # ← schickt alle gesammelten Änderungen über die Brücke
```

**Warum wird gesammelt?** Jede Übertragung kostet. Würde Flet bei jeder
Zuweisung sofort übertragen, wäre das Ändern von zehn Werten zehn
Übertragungen. So gehen sie in einer.

**Die gute Nachricht:** In den beiden häufigsten Fällen ruft Flet `update()`
inzwischen selbst auf — nach `main()` und nach jedem Ereignis-Handler
(„Auto-Update", Standard seit der neuen Flet-Generation, im Projekt 1.0).
Der Klassiker aus älteren Flet-Tutorials — „Wert geändert, Bildschirm bleibt
alt, halber Nachmittag weg" — tritt in Handlern deshalb nicht mehr auf.

**Wo du `update()` weiterhin selbst brauchst:** überall, wo Code *außerhalb*
eines Ereignis-Handlers läuft — Hintergrund-Tasks (`page.run_task`), Threads
(`page.run_thread`), alles, was kontinuierlich Daten schiebt. Flet weiß dort
nicht, wann du „fertig" bist. Genau das ist unser wichtigster Fall: die
Live-Messung, bei der jede Sekunde ein Pulswert eintrifft.

Drei Dinge dazu im Kopf behalten:

- `control.update()` schickt nur dieses eine Control über die Brücke —
  bei einem Live-Wert in einem großen Baum der richtige Griff.
- Ein explizites `page.update()` im Handler schadet nicht; Flet merkt sich
  dann, dass du selbst übertragen hast, und lässt das Auto-Update aus.
  Bestehender Code mit `page.update()` bleibt also korrekt.
- Wer das alte, rein manuelle Verhalten will:
  `ft.context.disable_auto_update()`.

---

## 3. Ereignisse

```python
def gedrueckt(e: ft.ControlEvent) -> None:
    zaehler.value = str(int(zaehler.value) + 1)
    # kein update() nötig — nach dem Handler übernimmt das Auto-Update


ft.Button("Wiederholung", on_click=gedrueckt)
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

Flet leitet daraus ein vollständiges, in sich stimmiges Schema ab. Die App
geht einen Schritt weiter: Jedes Farbprofil (`src/trainingsapp/core/darstellung.py`)
ersetzt die Flächenstufen durch eigene, getönte — `src/trainingsapp/ui/theme.py`
zeigt, wie man dazu `ft.ColorScheme` und einen Verlauf als `View.decoration` setzt.

---

## 6. Beispiele

```bash
uv run flet run docs/tutorial/L02_flet_modell/beispiel_01.py   # Control-Baum
uv run flet run -d docs/tutorial/L02_flet_modell/beispiel_02.py   # update() sichtbar gemacht
uv run flet run docs/tutorial/L02_flet_modell/beispiel_03.py   # eine Übungskarte
```

**Beispiel 2 ist das wichtigste.** Es zeigt beides: einen Handler, der ganz
ohne `update()` funktioniert (Auto-Update) — und einen Hintergrund-Task, in dem
dieselbe Zuweisung ohne `update()` einfriert. Wenn dir dieser Unterschied
einmal klar ist, verlierst du bei der Live-Messung keinen Nachmittag.

---

## Stolperfallen

**Die Änderung aus einem Hintergrund-Task erscheint nicht** — dort fehlt
`update()`; das Auto-Update greift nur nach `main()` und nach Ereignis-Handlern.

**Die Änderung erscheint erst beim nächsten Klick** — dasselbe Problem, anders
verkleidet: Die liegengebliebene Änderung wird vom Auto-Update des *nächsten*
Ereignisses mitgespült. Wenn sich deine Oberfläche „erst beim Klicken"
aktualisiert, fehlt in einem Task ein `update()`.

**`RuntimeError: Control must be added to the page first`** — du rufst
`control.update()` auf, bevor es im Baum hängt. Erst `page.add(...)`, dann updaten.

**`expand=True` bewirkt nichts** — der Elternteil hat selbst keine feste Größe.
`expand` verteilt vorhandenen Platz; wo keiner ist, gibt es nichts zu verteilen.

**Feste Farbwerte** sehen im Dunkelmodus falsch aus. `ft.Colors.*` benutzen.

**Text wird abgeschnitten statt umgebrochen** — `ft.Text(..., max_lines=2,
overflow=ft.TextOverflow.ELLIPSIS)` oder in einen `Container` mit fester Breite.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L02b: Aufs Handy bauen**
