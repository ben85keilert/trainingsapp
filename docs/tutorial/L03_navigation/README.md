# L03 — Navigation und Zustand

**Ziel:** Mehrere Ansichten, Wechsel dazwischen, und ein Zustand, der die
Oberfläche überlebt. Danach bauen wir M1.

Zeit: ein bis zwei Stunden.

---

## Glossar

Die Begriffe, die in dieser Lektion auftauchen — jeweils mit einer kurzen
Definition und einem Beispiel aus den drei Beispielskripten.

**Ereignis (Event)** — Etwas, das *passiert*: ein Klick, ein Tastendruck, ein
Routenwechsel. Flet verpackt es in ein Objekt (`ft.ControlEvent`,
`ft.RouteChangeEvent`, `ft.ViewPopEvent`, …), das der Handler als Parameter
bekommt. `e.control` ist das Control, das das Ereignis ausgelöst hat.

**Handler (Ereignisbehandler)** — Eine Funktion, die **du nicht selbst
aufrufst**, sondern die Flet aufruft, sobald ein bestimmtes Ereignis eintritt.
Man hängt sie mit `on_<ereignis> = funktion` an ein Control oder an die Seite —
„wenn `<ereignis>` passiert, ruf bitte `funktion` auf." Das eigentliche Aufrufen
übernimmt die Ereignisschleife von Flet.

```python
def wechseln(e: ft.ControlEvent) -> None:  # der Handler
    koerper.content = inhalte[e.control.selected_index]


ft.NavigationBar(on_change=wechseln, ...)  # das Anhängen
```

Flet ruft den Handler mit **genau einem** Positionsargument auf — dem Ereignis.
Der erste Parameter fängt es, egal wie er heißt; `e` ist nur Konvention. Die
Typannotation `e: ft.ControlEvent` hilft beim Lesen und dem Type-Checker, sie
bindet nichts. Flet „weiß" also nicht, dass `e` das Ereignis ist — es steckt
es einfach in den ersten Parameter.

Ein Handler darf das Ereignis-Argument weglassen, wenn er es nicht braucht
(`def route_gewechselt() -> None`). Dann lässt er sich auch ganz normal von
Hand aufrufen — das nutzen wir beim Start von Beispiel 2.

**Ansicht** — Was der Nutzer gerade sieht. In dieser Lektion meint das zwei
verschiedene Dinge, je nach Weg: entweder ein beliebiges Control, das in einen
`Container` gesteckt wird (Beispiel 1 und 3), oder eine `ft.View` (Beispiel 2).

**`ft.View`** — Ein Control, das eine ganze Bildschirmseite beschreibt. Es hat
eine `route` (seine Adresse) und `controls` (seinen Inhalt, in der Regel mit
einer `AppBar` obenan). Views hängen nicht unter `page.add(...)`, sondern
liegen in `page.views`.

```python
ft.View(route="/uebung/kniebeuge", controls=[ft.AppBar(...), ft.Text(...)])
```

**`ft.AppBar`** — Die Titelleiste oben in einer View: Titel, optional Icons und
Aktionen. In der Regel das erste Control in `controls`. Liegt die View nicht
ganz unten auf dem Stapel, zeichnet Flet in ihrer `AppBar` von selbst den
Zurück-Pfeil — dafür ist nichts zu konfigurieren.

**`ft.ListView`** — Eine scrollbare Liste. `ft.Column` scrollt nicht und läuft
bei zu vielen Einträgen einfach über; `ListView` übernimmt das Scrollen selbst
und ist für lange, gleichförmige Listen gedacht. `expand=True` lässt sie den
Platz unter der `AppBar` ausfüllen.

**Route** — Eine Adresse für eine Ansicht, geschrieben wie ein Pfad: `/`,
`/uebung/kniebeuge`. Sie steht in `page.route`. Die Wurzel `/` ist so etwas wie
„Home". Beim Start steht `page.route` bereits auf `/` — die Route ist also
nie „leer".

**Routing** — Das Verfahren, aus der Route die passende Ansicht zu bauen: Route
lesen, Ansichtsstapel daraus zusammensetzen, anzeigen. Der Nutzer navigiert,
indem sich die Route ändert; die Oberfläche folgt der Route, nicht umgekehrt.

**Ansichtsstapel (`page.views`)** — Eine Liste von Views, die wie ein Stapel
funktioniert: Die **oberste** (letzte) View ist sichtbar, die darunter bleiben
erhalten. Liegt mehr als eine View auf dem Stapel, zeigt Flet automatisch einen
Zurück-Pfeil in der `AppBar`. Die Wurzelansicht bleibt immer ganz unten.

**`page.push_route(route)`** — Setzt `page.route` auf einen neuen Wert. Ist der
Wert ein anderer als bisher, löst das `on_route_change` aus. Ist er
**derselbe**, passiert nichts — Flet verwirft einen Wechsel auf die bereits
aktuelle Route. `push_route` ist eine Coroutine (siehe unten).

**`page.on_route_change`** — Der Handler für „die Route hat sich geändert".
Hier wird der Ansichtsstapel aus der neuen Route aufgebaut.

**`page.on_view_pop`** — Der Handler für „der Nutzer will eine Ansicht vom
Stapel nehmen": Zurück-Pfeil in der `AppBar` oder die Zurück-Taste auf Android.
Flet nimmt die View **nicht** selbst herunter — das tut der Handler, und er
setzt danach die Route auf die jetzt oberste View.

**Ereignisschleife (Event Loop)** — Der Motor von `asyncio` und damit von
Flet: eine Endlosschleife, die laufend prüft, welche Aufgabe gerade weiterkann,
und sie bis zu ihrem nächsten `await` laufen lässt. Es läuft immer nur ein
Stück Code gleichzeitig; Warten (auf Netzwerk, Gerät, einen Klick) blockiert
das Programm aber nicht, weil die Schleife währenddessen andere Aufgaben
bedient. Jede `page` hat ihre eigene.

**Coroutine** — Was der Aufruf einer `async def`-Funktion zurückgibt: ein noch
nicht gestartetes Rezept. `page.push_route("/")` ohne `await` tut **nichts** —
es erzeugt nur das Coroutine-Objekt, und Python warnt später: „coroutine was
never awaited". Erst `await` oder ein Task treiben es an.

**Task** — Eine Coroutine, die die Ereignisschleife eingeplant hat und von
selbst weiterlaufen lässt. `await task` heißt „warte, bis er fertig ist", nicht
„starte ihn" — gestartet ist er schon. Merksatz: Coroutine = Rezept, Task =
Rezept im Ofen.

**`page.run_task(fn, *args)`** — Macht aus einer Coroutine-Funktion und ihren
Argumenten einen Task auf der Ereignisschleife der Seite, intern etwa
`asyncio.create_task(fn(*args))`. Die Funktion wird **ohne** Klammern
übergeben, ihre Argumente folgen dahinter. Gedacht für synchrone Stellen, an
denen kein `await` möglich ist — allen voran Lambdas: Python kennt keine
async-Lambdas, `lambda e: await …` ist ein `SyntaxError`. Handler dürfen
dagegen selbst `async def` sein; dann plant Flet sie beim Ereignis von sich aus
als Task ein, und im Handler darf man awaiten.

```python
on_click=lambda e: page.run_task(page.push_route, "/uebung/abc")  # synchron → Task
async def zurueck(e): await page.push_route("/")                    # Coroutine → await
```

**Zustand (State)** — Alles, was die App sich merken muss: geladene Übungen,
der gewählte Eintrag, die laufende Messung, der Zähler. Lebt in einem eigenen
Objekt (`AppState`), das so lange existiert wie die App — nicht in einer
Ansichtsfunktion, die bei jedem Wechsel neu läuft.

**Auto-Update** — Nach `main()` und nach jedem Handler ruft Flet `page.update()`
selbst auf (siehe L02). Außerhalb davon — in Tasks, oder wenn man einen
Handler von Hand aufruft — muss man `page.update()` selbst schreiben.

---

## 1. Zwei Wege, Ansichten zu wechseln

### Der einfache: Inhalt austauschen (Beispiel 1)

```python
koerper = ft.Container(expand=True, content=inhalte[0])


def wechseln(e: ft.ControlEvent) -> None:
    koerper.content = inhalte[e.control.selected_index]
    page.update()


page.add(
    ft.Column(
        expand=True,
        controls=[
            koerper,
            ft.NavigationBar(selected_index=0, on_change=wechseln, destinations=[...]),
        ],
    )
)
```

Was hier passiert, Schritt für Schritt:

1. `ansicht(titel, text)` ist eine kleine Fabrik: Sie baut einen `Container` mit
   Überschrift und Text und gibt ihn zurück. `inhalte` ist eine Liste aus vier
   solchen Containern — sie werden **einmal** gebaut und danach wiederverwendet.
2. `koerper` ist ein Container, der den gerade sichtbaren Inhalt hält. Am
   Anfang `inhalte[0]`.
3. `ft.NavigationBar` ist die Leiste unten. `destinations` sind ihre Einträge,
   `selected_index` der aktive. Ändert der Nutzer die Auswahl, feuert
   `on_change`.
4. Der Handler `wechseln` liest aus `e.control` (der NavigationBar) den neuen
   `selected_index`, holt den passenden Container aus `inhalte` und steckt ihn
   in `koerper.content`. `page.update()` schickt die Änderung an den Bildschirm.

Ein Container, dessen Inhalt ersetzt wird. Kein Verlauf, keine Adresse — für
eine Handy-App mit fester Leiste unten reicht das oft völlig. Genau so ist die
Hülle unserer App aufgebaut.

### Der ausgebaute: Routing (Beispiel 2)

Hier gibt es kein `page.add(...)`. Stattdessen werden Views auf `page.views`
gelegt, und ein Handler baut diesen Stapel aus der Route.

**Die beiden View-Fabriken.** `liste()` baut die Wurzelansicht mit Route `/`:
eine `AppBar` und eine `ListView` mit einem `ListTile` je Übung. `detail(key)`
baut die Detailansicht einer Übung mit Route `/uebung/<key>`. Beide geben bei
jedem Aufruf eine **neue** `ft.View` zurück.

```python
ft.ListTile(
    title=ft.Text(u["name"]),
    on_click=lambda e, k=key: page.run_task(page.push_route, f"/uebung/{k}"),
)
```

Der Klick auf einen Eintrag tut nur eines: die Route setzen. Was daraus wird,
entscheidet der Routen-Handler. Die Lambda-Zeile ist trotzdem die dichteste
der ganzen Lektion — drei Dinge stecken darin.

**`e`** ist das Ereignis. Flet ruft den Handler mit genau einem
Positionsargument auf, der erste Parameter fängt es. Hier wird es nicht einmal
benutzt — es muss nur da sein, damit der Aufruf passt.

**`k=key`** kommt **nicht** von Flet, sondern ist ein gewöhnlicher
Python-Default. Das Lambda steht in einer Schleife (`for key, u in
UEBUNGEN.items()`), und eine Closure schlägt Namen aus ihrer Umgebung erst beim
**Aufruf** nach — „späte Bindung". Beim Klick ist die Schleife längst durch,
`key` zeigt für jeden Eintrag auf den letzten Wert. `k=key` wertet `key`
dagegen sofort bei der **Definition** aus und speichert das Ergebnis als
Default: Jedes Lambda bekommt sein eigenes `k`. Und weil `k` einen Default
hat, stört es nicht, dass Flet nur ein Argument liefert.

```python
handler = [lambda e: print(i) for i in range(3)]       # späte Bindung
[h(None) for h in handler]                               # 2 2 2

handler = [lambda e, i=i: print(i) for i in range(3)]  # eingefroren
[h(None) for h in handler]                               # 0 1 2
```

**`page.run_task(page.push_route, f"/uebung/{k}")`** — `push_route` ist eine
Coroutine, und ein Lambda kann nicht awaiten. `run_task` bekommt die Funktion
(ohne Klammern) und ihr Argument getrennt, baut daraus die Coroutine und
startet sie als Task. Der f-String wird beim Klick ausgewertet, mit dem
eingefrorenen `k`.

Ohne Lambda ginge es auch: eine Fabrik, die je Übung einen `async`-Handler
baut, den Flet dann selbst einplant.

```python
def oeffnen(k: str):
    async def handler(e):
        await page.push_route(f"/uebung/{k}")

    return handler


ft.ListTile(..., on_click=oeffnen(key))
```

Die Fabrik friert `k` als Parameter ein — dasselbe Prinzip wie `k=key`, nur
ohne Default-Trick. Beispiel 2 nimmt das Lambda, weil es kürzer ist; wer die
Fabrik klarer findet, nimmt die.

**Der Routen-Handler.**

```python
def route_gewechselt() -> None:
    page.views.clear()
    page.views.append(liste())  # Wurzel bleibt immer unten
    if page.route.startswith("/uebung/"):
        key = page.route.rsplit("/", 1)[-1]
        if key in UEBUNGEN:
            page.views.append(detail(key))
    page.update()


page.on_route_change = route_gewechselt
```

Er baut den Stapel jedes Mal **komplett neu** aus `page.route`: Stapel leeren,
Wurzel drauflegen, und falls die Route `/uebung/<key>` ist und der Schlüssel
bekannt, die Detailansicht obenauf. Damit ist der Stapel immer eine reine
Funktion der Route — es gibt keinen zweiten Ort, an dem man ihn pflegen müsste.

**Der Zurück-Handler.**

```python
async def zurueck(e: ft.ViewPopEvent) -> None:
    page.views.pop()
    await page.push_route(page.views[-1].route)


page.on_view_pop = zurueck
```

Zurück-Pfeil oder Android-Zurück-Taste lösen `on_view_pop` aus. Der Handler
nimmt die oberste View herunter und setzt die Route auf die der nun obersten
View (`/`). Das wiederum feuert `on_route_change`, und `route_gewechselt` baut
den Stapel passend zur Route neu auf. Route und Stapel bleiben so immer
synchron.

**Der Start.**

```python
page.on_route_change = route_gewechselt
page.on_view_pop = zurueck
route_gewechselt()  # einmal von Hand
```

Beim Start steht `page.route` schon auf `/`, aber `page.views` ist leer. Man
könnte meinen, `push_route("/")` löse den Handler aus — tut es aber nicht:
Flet vergleicht alte und neue Route, findet `/ == /` und verwirft den Wechsel
als „keine Änderung". Also ruft man den Handler einmal **direkt** auf. Darum
ist er ohne Ereignis-Parameter definiert, und darum steht in ihm ein
`page.update()` — beim direkten Aufruf greift kein Auto-Update.

**Der Ablauf im Ganzen:**

| Wann | Was passiert |
|---|---|
| Start | `route_gewechselt()` von Hand → Stapel = `[liste]` |
| Tipp auf Übung | `push_route("/uebung/x")` → Route ändert sich → `on_route_change` → Stapel = `[liste, detail(x)]` → Zurück-Pfeil erscheint |
| Zurück | `on_view_pop` → `views.pop()` → `push_route("/")` → `on_route_change` → Stapel = `[liste]` |

Zwei Flet-0.86-Eigenheiten: Bei `ft.View` ist `controls` das erste
Positionsargument, nicht `route` — deshalb beide als Schlüsselwort, sonst zeigt
die Ansicht stillschweigend nichts an. Und `push_route` ist eine Coroutine;
aus einem Lambda oder einem synchronen Handler heraus startet man sie mit
`page.run_task(page.push_route, "/…")`.

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

**Beispiel 3 macht das sichtbar.** `zaehler_ansicht(page, state)` hält zwei
Zähler: `lokal` ist eine Variable *in der Funktion*, `state.zaehler` ein Feld
des `AppState`, der in `main()` genau einmal angelegt wird. Der Handler
`wechseln` ruft `zaehler_ansicht(...)` bei jedem Wechsel **neu** auf — damit
beginnt `lokal` wieder bei 0, während `state.zaehler` seinen Wert behält, weil
`state` außerhalb der Ansicht lebt.

```python
def zaehler_ansicht(page: ft.Page, state: AppState) -> ft.Control:
    lokal = 0  # entsteht bei JEDEM Aufbau neu
    ...
    def plus_lokal(e):
        nonlocal lokal
        lokal += 1
    def plus_state(e):
        state.zaehler += 1  # überlebt, weil `state` außerhalb lebt
```

(`nonlocal lokal` ist nötig, weil `plus_lokal` sonst eine eigene, neue Variable
`lokal` anlegen würde, statt die der umschließenden Funktion zu verändern.)

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

Das ist dieselbe Idee wie beim Routing in Abschnitt 1: Dort ist die Route der
Zustand, und `route_gewechselt` ist das `zeichnen()`, das den Stapel daraus
ableitet.

Das ist übrigens genau die Idee, die Flet 1.0 zum Standard macht. Wer schon
jetzt so schreibt, hat die Umstellung fast hinter sich.

---

## 4. Beispiele

```bash
uv run flet run docs/tutorial/L03_navigation/beispiel_01.py   # Leiste unten
uv run flet run -d docs/tutorial/L03_navigation/beispiel_02.py   # Routen und Stapel
uv run flet run docs/tutorial/L03_navigation/beispiel_03.py   # Zustand überlebt
```

**Beispiel 3 ist das wichtigste.** Es zeigt zwei Zähler nebeneinander: einer
liegt in der Ansicht, einer im Zustand. Wechsle hin und her — nur einer
überlebt.

---

## Stolperfallen

**Der Bildschirm bleibt beim Start leer** — `on_route_change` ist gesetzt,
aber der Handler wurde beim Start nicht direkt aufgerufen. `push_route("/")`
hilft nicht, weil die Route schon `/` ist und Flet den Wechsel verwirft.

**Nach `page.views.append(...)` passiert nichts** — der Code läuft außerhalb
eines Ereignis-Handlers (z. B. in einem Task oder beim direkten Aufruf), und
dort fehlt `page.update()`. In Handlern übernimmt das Auto-Update (siehe L02).

**Der Zurück-Knopf erscheint nicht** — er kommt nur, wenn mehr als eine Ansicht
auf dem Stapel liegt. Die Wurzelansicht muss immer unten liegen bleiben.

**`ft.View("/", [...])` zeigt nichts an** — seit Flet 0.80 ist `controls` das
erste Positionsargument. `route=` und `controls=` immer als Schlüsselwort.

**`RuntimeWarning: coroutine 'push_route' was never awaited`** — `push_route`
wurde aus einem synchronen Handler wie eine normale Funktion aufgerufen. Das
erzeugt nur das Coroutine-Objekt; niemand führt es aus, die Route bleibt, wie
sie war. Dort `page.run_task(page.push_route, "/…")` verwenden oder den Handler
`async` machen und `await` schreiben.

**`SyntaxError: 'await' outside async function`** — `await` steht in einem
Lambda oder einem synchronen Handler. Python kennt keine async-Lambdas.
Entweder `page.run_task(...)` nehmen oder den Handler als `async def`
schreiben — mit Lambda geht das nicht, dann eine Fabrik-Funktion (Abschnitt 1).

**`TypeError: … missing 1 required positional argument`** — der Handler hat
zwei Pflichtparameter (`lambda e, k: …`), Flet liefert aber nur einen. Der
zweite braucht einen Default: `lambda e, k=key: …`.

**Alle Listeneinträge öffnen dieselbe Übung** — im Lambda fehlt `k=key`; die
Schleifenvariable wird erst beim Klick ausgewertet und hat dann für alle
Einträge den letzten Wert (späte Bindung, Abschnitt 1).

**Zustand ist nach dem Wechsel weg** — er wurde in der Ansichtsfunktion angelegt
statt im `AppState`.

**Die Leiste unten springt zurück** — `selected_index` wird beim Neuaufbau nicht
mitgeführt. Er gehört ebenfalls in den Zustand.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L04: Datenmodell und SQLite**
