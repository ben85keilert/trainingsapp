# L03 — Navigation und Zustand

**Ziel:** Mehrere Ansichten, Wechsel dazwischen, und ein Zustand, der die
Oberfläche überlebt. Danach bauen wir M1.

Zeit: ein bis zwei Stunden.

---

## 1. Zwei Wege, Ansichten zu wechseln

### Der einfache: Inhalt austauschen

```python
koerper = ft.Container(expand=True, content=heute_ansicht())


def wechseln(e):
    koerper.content = ANSICHTEN[e.control.selected_index]()
    page.update()


ft.NavigationBar(on_change=wechseln, destinations=[...])
```

Ein Container, dessen Inhalt ersetzt wird. Kein Verlauf, keine Adresse — für
eine Handy-App mit fester Leiste unten reicht das oft völlig.

### Der ausgebaute: Routing

```python
def route_wechsel(e: ft.RouteChangeEvent):
    page.views.clear()
    page.views.append(ft.View("/", [heute_ansicht()]))
    if page.route.startswith("/uebung/"):
        uebung_id = page.route.split("/")[-1]
        page.views.append(ft.View(page.route, [detail_ansicht(uebung_id)]))
    page.update()


page.on_route_change = route_wechsel
page.go("/uebung/abc123")
```

`page.views` ist ein **Stapel**. Die oberste Ansicht ist sichtbar, darunter
liegen die vorherigen. Der Zurück-Knopf nimmt die oberste herunter.

**Wir nehmen beides:** Die vier Hauptbereiche über die Leiste unten (einfacher
Weg), Detailansichten über Routen (Stapel). So funktioniert die
Zurück-Taste auf Android richtig.

---

## 2. Zustand gehört nicht in die Oberfläche

Der Fehler, der sich beim Ausprobieren einschleicht:

```python
# So NICHT
def katalog_ansicht(page):
    uebungen = lade_uebungen()  # bei jedem Ansichtswechsel neu geladen
    gewaehlt = None  # beim Wechsel verloren
    ...
```

Beim nächsten Wechsel ist alles weg — die Ansicht wurde ja neu gebaut.

Stattdessen ein Zustandsobjekt, das die Ansichten überlebt:

```python
@dataclass
class AppState:
    db: sqlite3.Connection
    subject_id: str
    uebungen: list[Exercise] = field(default_factory=list)
    gewaehlte_uebung: str | None = None


def katalog_ansicht(state: AppState) -> ft.Control:
    return ft.ListView(controls=[karte(u) for u in state.uebungen])
```

Der Zustand wird einmal aufgebaut und an die Ansichten übergeben. Sie **lesen**
daraus und **melden** Änderungen zurück — sie halten nichts Eigenes.

Warum das wichtig ist: Wenn eine Live-HRV-Messung läuft und du auf „Übungen"
wechselst, darf die Messung nicht abreißen. Sie hängt am Zustand, nicht an der
Ansicht.

---

## 3. Die Ansicht baut sich aus dem Zustand

Ein Muster, das sich in dieser App durchzieht:

```python
def zeichnen() -> None:
    """Leitet die gesamte Anzeige aus dem Zustand ab."""
    anzeige.value = str(state.reps)
    anzeige.color = ft.Colors.PRIMARY if state.reps >= state.ziel else None
    knopf.disabled = state.laeuft is False
    page.update()


def plus(e):
    state.reps += 1  # Zustand ändern
    zeichnen()  # Anzeige daraus ableiten
```

Die Handler ändern **nur den Zustand**. Eine einzige Funktion übersetzt Zustand
in Anzeige. Ohne diese Trennung muss jeder Handler alle Anzeigeregeln kennen —
und beim vierten vergisst man eine.

Das ist übrigens genau die Idee, die Flet 1.0 zum Standard macht. Wer schon
jetzt so schreibt, hat die Umstellung fast hinter sich.

---

## 4. Beispiele

```bash
flet run docs/tutorial/L03_navigation/beispiel_01.py   # Leiste unten
flet run -d docs/tutorial/L03_navigation/beispiel_02.py   # Routen und Stapel
flet run docs/tutorial/L03_navigation/beispiel_03.py   # Zustand überlebt
```

**Beispiel 3 ist das wichtigste.** Es zeigt zwei Zähler nebeneinander: einer
liegt in der Ansicht, einer im Zustand. Wechsle hin und her — nur einer
überlebt.

---

## Stolperfallen

**Nach `page.views.append(...)` passiert nichts** — `page.update()` fehlt.

**Der Zurück-Knopf erscheint nicht** — er kommt nur, wenn mehr als eine Ansicht
auf dem Stapel liegt. Die Wurzelansicht muss immer unten liegen bleiben.

**Zustand ist nach dem Wechsel weg** — er wurde in der Ansichtsfunktion angelegt
statt im `AppState`.

**Die Leiste unten springt zurück** — `selected_index` wird beim Neuaufbau nicht
mitgeführt. Er gehört ebenfalls in den Zustand.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L04: Datenmodell und SQLite**
