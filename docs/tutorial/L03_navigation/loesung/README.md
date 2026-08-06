# L03 — Lösungen

## Aufgabe 1: Zustand

**1.** Links steht 0, rechts 5.

**2.** In `zaehler_ansicht()` steht `lokal = 0` direkt im Funktionsrumpf. Beim
Ansichtswechsel ruft `wechseln()` die Funktion erneut auf — die Variable
entsteht neu und beginnt bei 0. Die alte ist unerreichbar geworden und wird
weggeräumt.

Der `AppState` dagegen wird **einmal** in `main()` angelegt und nur
weitergereicht.

**3. Die HRV-Messung.**

Eine laufende Messung ist mehr als eine Zahl: eine BLE-Verbindung, eine
asyncio-Aufgabe, ein Ringpuffer mit tausenden RR-Intervallen. Läge das in der
Ansicht, würde beim Wechsel auf „Übungen"

- die Verbindung abbrechen,
- die Aufgabe verwaisen (und im Hintergrund weiterlaufen, ohne dass jemand
  zuhört),
- der Puffer verloren gehen — die Messung wäre unbrauchbar.

Deshalb: Messung im `AppState`, die Ansicht schaut ihr nur zu.

## Aufgabe 2: Auswahl merken

```python
@dataclass
class AppState:
    zaehler: int = 0
    nav_index: int = 0  # ← neu


def main(page):
    state = AppState()

    def wechseln(e):
        state.nav_index = e.control.selected_index  # merken
        koerper.content = ...
        page.update()

    nav = ft.NavigationBar(
        selected_index=state.nav_index,  # von dort lesen
        on_change=wechseln,
        destinations=[...],
    )
```

Dasselbe Muster wie beim Zähler — und aus demselben Grund.

## Aufgabe 3: Dritte Ebene

```python
def video(key: str) -> ft.View:
    u = UEBUNGEN[key]
    return ft.View(
        f"/uebung/{key}/video",
        [
            ft.AppBar(title=ft.Text(f"{u['name']} — Video")),
            ft.Container(
                expand=True,
                alignment=ft.alignment.center,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.PLAY_CIRCLE, size=64, opacity=0.4),
                        ft.Text("Videowiedergabe kommt in L09"),
                    ],
                ),
            ),
        ],
    )
```

Im Routen-Handler **vor** der Detail-Prüfung einordnen, sonst greift die
kürzere Route zuerst:

```python
page.views.append(liste())
if page.route.startswith("/uebung/"):
    teile = page.route.strip("/").split("/")  # ['uebung', key, ('video')]
    key = teile[1]
    if key in UEBUNGEN:
        page.views.append(detail(key))
        if len(teile) > 2 and teile[2] == "video":
            page.views.append(video(key))
```

**Frage:** Drei Ansichten liegen dann auf dem Stapel. Zweimal Zurück führt zur
Liste — jedes Zurück nimmt genau eine herunter. Wichtig ist, dass der Handler
den **ganzen** Stapel aufbaut und nicht nur die oberste Ansicht: sonst gäbe es
nach einem Neustart auf der Videoroute kein Zurück.

## Aufgabe 4: mein_geruest.py

```python
import json
from dataclasses import dataclass, field
from pathlib import Path

import flet as ft

SEED = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "trainingsapp"
    / "data"
    / "seed"
    / "exercises.json"
)


@dataclass
class AppState:
    subject_name: str = "Benjamin"
    nav_index: int = 0
    uebungen: list[dict] = field(default_factory=list)


def katalog(page: ft.Page, state: AppState) -> ft.Control:
    return ft.ListView(
        expand=True,
        controls=[
            ft.ListTile(
                title=ft.Text(u["name"]),
                subtitle=ft.Text(u["category"], size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                on_click=lambda e, k=u["key"]: page.go(f"/uebung/{k}"),
            )
            for u in state.uebungen
        ],
    )


def platzhalter(titel: str, lektion: str) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Text(titel, size=24, weight=ft.FontWeight.BOLD),
                ft.Text(f"entsteht in {lektion}", size=12, opacity=0.6),
            ],
        ),
    )


def main(page: ft.Page) -> None:
    page.title = "Trainingsassistent"
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    state = AppState(uebungen=json.loads(SEED.read_text(encoding="utf-8"))["exercises"])

    def inhalt() -> ft.Control:
        if state.nav_index == 0:
            return platzhalter(f"Hallo {state.subject_name}", "L05")
        if state.nav_index == 1:
            return katalog(page, state)
        if state.nav_index == 2:
            return platzhalter("Messung", "L11")
        return platzhalter("Verlauf", "L12")

    def haupt() -> ft.View:
        def wechseln(e):
            state.nav_index = e.control.selected_index
            page.go("/")  # Stapel neu aufbauen

        return ft.View(
            "/",
            [
                ft.AppBar(title=ft.Text("Trainingsassistent")),
                ft.Container(expand=True, content=inhalt()),
                ft.NavigationBar(
                    selected_index=state.nav_index,
                    on_change=wechseln,
                    destinations=[
                        ft.NavigationBarDestination(label="Heute", icon=ft.Icons.TODAY),
                        ft.NavigationBarDestination(label="Übungen", icon=ft.Icons.FITNESS_CENTER),
                        ft.NavigationBarDestination(label="Messung", icon=ft.Icons.MONITOR_HEART),
                        ft.NavigationBarDestination(label="Verlauf", icon=ft.Icons.SHOW_CHART),
                    ],
                ),
            ],
        )

    def detail(key: str) -> ft.View:
        u = next(x for x in state.uebungen if x["key"] == key)
        return ft.View(
            f"/uebung/{key}",
            [
                ft.AppBar(title=ft.Text(u["name"])),
                ft.Container(padding=20, content=ft.Text(u["description"])),
            ],
        )

    def route_gewechselt(e):
        page.views.clear()
        page.views.append(haupt())
        if page.route.startswith("/uebung/"):
            page.views.append(detail(page.route.rsplit("/", 1)[-1]))
        page.update()

    page.on_route_change = route_gewechselt
    page.on_view_pop = lambda e: (page.views.pop(), page.go(page.views[-1].route))
    page.go("/")


ft.app(target=main)
```

Beachte: `wechseln` ruft `page.go("/")` auf, statt den Inhalt direkt zu tauschen.
So läuft alles über **einen** Weg — den Routen-Handler. Das ist konsistenter und
verhindert, dass Leiste und Stapel auseinanderlaufen.

## Zum Nachdenken

**1. Warum keine globalen Variablen?**

- Nicht testbar: jeder Test würde den Zustand des vorigen erben
- Nicht zweimal instanziierbar — später vielleicht mehrere Profile
- Man sieht einer Funktion nicht an, was sie anfasst; bei `def f(state)` schon

**2. Warum kein Dictionary?**

`state["subjekt_name"]` (Tippfehler) legt stillschweigend einen neuen Schlüssel
an. Bei einem `@dataclass` ist es ein Fehler. Dazu kommen Autovervollständigung
und Typprüfung — bei einem Dictionary weiß niemand, was drinstehen darf.

**3. `page.state = ...`?**

Funktioniert, ist aber unsauber:

- `page` gehört Flet. Eigene Attribute daran können mit künftigen Versionen
  kollidieren — gerade bei Flet 1.0 ein reales Risiko.
- Der Zustand wäre an die Oberfläche gebunden. Genau das wollen wir nicht: er
  soll in Tests ohne `page` funktionieren.
- Typprüfer kennen `page.state` nicht und können nicht helfen.

Als Parameter durchreichen ist etwas mehr Schreibarbeit und deutlich klarer.
