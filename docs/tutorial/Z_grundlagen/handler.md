# Handler — wie Flet auf Ereignisse reagiert

Eine Flet-Oberfläche tut von sich aus nichts. Sie zeigt an, was man ihr gibt,
und wartet. Damit etwas passiert, wenn jemand tippt, klickt, wischt oder das
Fenster verkleinert, hängt man **Handler** an Controls: Funktionen, die Flet
aufruft, sobald das passende Ereignis eintritt. Jedes dieser Ereignisse hat
einen Namen, der mit `on_` beginnt — `on_click`, `on_change`, `on_submit`.

Dieser Text erklärt den Mechanismus dahinter, listet die Handler auf, die in
der App vorkommen werden, und zeigt an Beispielen, wie man sie schreibt.

Lauffähig: `uv run flet run -d docs/tutorial/Z_grundlagen/beispiel_handler.py`

Voraussetzung: L02 (Control, `update()`, Auto-Update). Hilfreich:
[asyncio.md](asyncio.md) für die async-Handler in Abschnitt 5.

---

## Glossar

**Ereignis (Event)** — Etwas, das passiert ist: ein Klick, eine Eingabe, ein
Routenwechsel. Flutter erkennt es auf der Bildschirmseite und schickt eine
Nachricht über die Brücke an Python: *„Control 17 hat `click` gemeldet."*

**Handler** — Die Python-Funktion, die zu einem Ereignis gehört. Man hängt sie
an ein Control, indem man sie einer `on_…`-Eigenschaft zuweist. Ohne Handler
wird das Ereignis verworfen; Flet meldet keinen Fehler, es passiert nur nichts.

**`on_…`-Eigenschaft** — Der Haken, an dem der Handler hängt. Jedes Control
hat eine feste Auswahl davon; `Button` kennt `on_click`, `TextField` kennt
`on_change` und `on_submit`, `Page` kennt `on_route_change`. Die Eigenschaft
ist ein ganz normales Attribut: `knopf.on_click = gedrueckt` und
`ft.Button(on_click=gedrueckt)` sind dasselbe.

**Event-Objekt `e`** — Das Argument, das Flet dem Handler übergibt. Es trägt
mindestens `e.control` (das auslösende Control), `e.name` (der Ereignisname
ohne `on_`) und `e.data` (Nutzdaten, oft leer). Für manche Ereignisse gibt es
Unterklassen mit weiteren Feldern, z. B. `ft.KeyboardEvent` mit `e.key`.

**Callback** — Allgemeiner Programmierbegriff für „eine Funktion, die man
übergibt, damit jemand anderes sie später aufruft". Ein Handler ist ein
Callback. Der Ausdruck „Flet ruft zurück" meint genau das.

**Auto-Update** — Nach jedem Handler ruft Flet `page.update()` selbst auf
(siehe L02, Abschnitt 2). Deshalb reicht es, in einem Handler Werte zu ändern.

---

## 1. Der Mechanismus: wer ruft wen?

Du schreibst nie `gedrueckt()` selbst. Du schreibst nur, *dass* diese Funktion
zum Knopf gehört. Den Aufruf übernimmt Flet.

```python
import flet as ft


def main(page: ft.Page) -> None:
    zaehler = ft.Text("0", size=40)

    def gedrueckt(e: ft.ControlEvent) -> None:
        zaehler.value = str(int(zaehler.value) + 1)

    page.add(zaehler, ft.Button("+1", on_click=gedrueckt))


ft.run(main)
```

Was passiert, wenn jemand auf den Knopf tippt:

```
Finger auf dem Knopf
  │
  ▼
Flutter (Bildschirmseite) erkennt den Tipp
  │   schickt über die Brücke: "Control <id> · click · (keine Daten)"
  ▼
Flet (Python-Seite) sucht das Control mit dieser id
  │   baut das Event-Objekt: e.control = der Knopf, e.name = "click"
  │   schaut nach: hat der Knopf ein on_click?  →  ja: gedrueckt
  ▼
gedrueckt(e) läuft                      ← dein Code
  │   zaehler.value = "1"                 (nur das Python-Objekt ändert sich)
  ▼
Auto-Update: page.update()              ← Flet, nicht du
  │   schickt die Änderung zurück über die Brücke
  ▼
Bildschirm zeigt "1"
```

Zwei Dinge sind daran wichtig:

- **Die Funktion wird ohne Klammern übergeben.** `on_click=gedrueckt` reicht
  die Funktion selbst weiter. `on_click=gedrueckt()` würde sie *sofort* beim
  Aufbau der Oberfläche aufrufen und ihr Ergebnis (`None`) an den Knopf hängen
  — der Knopf täte danach nichts. Das ist der häufigste Anfängerfehler.
- **Der Handler läuft auf dem Event Loop der Seite.** Alle Handler, alle
  Tasks, alles in `main()` laufen im selben Thread (siehe
  [asyncio.md](asyncio.md), Abschnitt 4). Ein Handler, der lange rechnet oder
  mit `time.sleep()` wartet, friert die ganze Oberfläche ein.

### Welche Signatur darf ein Handler haben?

Flet schaut sich die Funktion an, bevor es sie aufruft, und richtet sich
danach:

| Form | Flet ruft auf | wann sinnvoll |
|---|---|---|
| `def h(e)` | `h(e)` | Standard: man braucht `e.control` oder `e.data` |
| `def h()` | `h()` | man braucht nichts vom Ereignis |
| `async def h(e)` | `await h(e)` | im Handler muss `await` stehen (Abschnitt 5) |
| `lambda e: …` | `h(e)` | Einzeiler, meist um ein Argument einzufrieren (Abschnitt 4) |

Die Variante ohne Parameter ist mehr als Bequemlichkeit: Sie erlaubt es, den
Handler auch **von Hand** aufzurufen, ohne ein Event-Objekt erfinden zu müssen
— genau das tut L03 mit `route_gewechselt()` beim Start. Dann fehlt allerdings
das Auto-Update, und man schreibt `page.update()` selbst hinein.

### Was steht im Event-Objekt?

```python
def ausgewaehlt(e: ft.ControlEvent) -> None:
    e.control          # das Control, das das Ereignis ausgelöst hat
    e.control.value    # dessen aktueller Wert (TextField, Checkbox, Slider, …)
    e.control.data     # frei belegbares Feld — man hängt hier z. B. eine id an
    e.name             # "click", "change", "submit", …
    e.data             # Nutzdaten des Ereignisses; bei on_click leer
    e.page             # die Seite, zu der das Control gehört
```

`e.control` ist der wichtigste Eintrag. Er macht es möglich, **einen** Handler
an **viele** Controls zu hängen und trotzdem zu wissen, welches es war:

```python
def ausgewaehlt(e: ft.ControlEvent) -> None:
    print("gewählt:", e.control.data)


for uebung in uebungen:
    page.add(ft.ListTile(title=ft.Text(uebung.name), data=uebung.id, on_click=ausgewaehlt))
```

`data` ist ein Feld, das jedes Control hat und das Flet nie selbst benutzt. Es
ist dafür da, dass *du* etwas dranhängst. Damit ist der Handler eine Funktion
des Ereignisses, nicht des Knopfes — was in L03 („die Ansicht baut sich aus
dem Zustand") wichtig wird.

---

## 2. Die Handler, die man wirklich braucht

Flet kennt weit über hundert `on_…`-Eigenschaften, die meisten davon am
`GestureDetector` (Wischen, Zoomen, Drücken mit drei Fingern …). Für diese App
reicht ein Bruchteil. Die Tabelle nennt ihn, geordnet nach dem, was der
Benutzer tut.

### Antippen

| Handler | an | feuert wenn | in `e` |
|---|---|---|---|
| `on_click` | `Button`, `IconButton`, `TextButton`, `ListTile`, `Container`, `TextSpan`, `PopupMenuItem` | angetippt/geklickt | nichts Besonderes; `e.control.data` nutzen |
| `on_long_press` | dieselben | lange gedrückt | — |
| `on_hover` | `Button`, `Container` | Maus fährt hinein oder heraus | `e.data`: `True` hinein, `False` heraus |
| `on_tap` | `GestureDetector`, `SearchBar` | angetippt | `ft.TapEvent`: `local_position.x/.y`, `global_position.x/.y` |
| `on_double_tap` | `GestureDetector` | doppelt angetippt | — |

Faustregel: Alles, was wie ein Knopf aussieht, hat `on_click`. Wer eine
beliebige Fläche antippbar machen will, packt sie in einen `Container` mit
`on_click` — oder in einen `GestureDetector`, wenn er Koordinaten braucht.

### Eingeben und Auswählen

| Handler | an | feuert wenn | in `e` |
|---|---|---|---|
| `on_change` | `TextField`, `Checkbox`, `Switch`, `Slider`, `RadioGroup`, `Dropdown` (nur alte API), `SegmentedButton`, `DatePicker`, `ExpansionTile`, `Tabs`, `NavigationBar`, `NavigationRail` | der Wert sich ändert | `e.control.value` bzw. `e.control.selected_index` |
| `on_submit` | `TextField`, `SearchBar` | Enter gedrückt | `e.control.value` |
| `on_select` | `Dropdown`, `PopupMenuButton` | ein Eintrag gewählt | `e.control.value` |
| `on_change_start` / `on_change_end` | `Slider`, `RangeSlider` | Ziehen beginnt / endet | `e.control.value` |
| `on_focus` / `on_blur` | `TextField`, `Button`, `Checkbox`, `Switch`, `Slider`, `Dropdown` | Fokus kommt / geht | — |
| `on_tap_outside` | `TextField` | außerhalb getippt | — |

`on_change` bei `TextField` feuert **bei jedem Tastendruck**. Wer nur den
fertigen Wert will, nimmt `on_submit` (Enter) oder `on_blur` (Feld verlassen)
— oder liest `feld.value` erst, wenn ein Speichern-Knopf gedrückt wird. Bei
`Slider` gilt Entsprechendes: `on_change` feuert beim Ziehen viele Male pro
Sekunde, `on_change_end` einmal am Schluss.

### Navigieren (an `page`)

| Handler | feuert wenn | in `e` |
|---|---|---|
| `page.on_route_change` | `page.route` sich ändert (`push_route`, Browser-URL) | `ft.RouteChangeEvent`: `e.route` |
| `page.on_view_pop` | Zurück-Pfeil der `AppBar` oder Android-Zurück-Taste | `ft.ViewPopEvent`: `e.view` |
| `page.on_views_pop_until` | mehrere Views auf einmal abgebaut werden | `e.view` |

Diese drei bilden das Routing aus L03; dort steht das Zusammenspiel im Detail.

### Fenster, Tastatur, Lebenszyklus (an `page`)

| Handler | feuert wenn | in `e` |
|---|---|---|
| `page.on_resize` | Fenstergröße sich ändert | `ft.PageResizeEvent`: `e.width`, `e.height` |
| `page.on_keyboard_event` | Taste gedrückt (Desktop, Web) | `ft.KeyboardEvent`: `e.key`, `e.shift`, `e.ctrl`, `e.alt`, `e.meta` |
| `page.on_app_lifecycle_state_change` | App in den Hinter-/Vordergrund geht | `e.state` — für die Live-Messung auf dem Handy wichtig (L10/L11) |
| `page.on_platform_brightness_change` | System wechselt hell/dunkel | — |
| `page.on_close` | die Sitzung endet | — |

### Dialoge, Listen, Sonstiges

| Handler | an | feuert wenn |
|---|---|---|
| `on_dismiss` | `AlertDialog`, `BottomSheet`, `SnackBar`, `Banner` | geschlossen — egal wie |
| `on_action` | `SnackBar` | der Aktionsknopf gedrückt |
| `on_scroll` | `ListView`, `Column`, `Row` (mit `scroll=`) | gescrollt; `e.pixels`, `e.max_scroll_extent` |
| `on_animation_end` | jedes Control mit `animate_…` | eine Animation fertig |
| `on_accept` / `on_will_accept` / `on_leave` | `DragTarget` | Drag-and-drop |
| `on_pan_update`, `on_scale_update`, … | `GestureDetector` | Wischen, Zoomen |

Woher weiß man, welche `on_…` ein bestimmtes Control hat? Zwei Wege:

```bash
# Im Quelltext von Flet nachsehen (der Weg, der immer stimmt):
grep -n "^    on_" .venv/lib/python3.12/site-packages/flet/controls/material/textfield.py

# Oder in Python:
uv run python -c "import flet as ft; print([n for n in dir(ft.TextField) if n.startswith('on_')])"
```

---

## 3. Beispiele nach Ereignisart

### `on_click` — die Grundform

```python
def speichern(e: ft.ControlEvent) -> None:
    eintrag = SessionEntry(wiederholungen=int(feld.value))
    speicher.anlegen(eintrag)
    feld.value = ""
    status.value = "gespeichert"


ft.Button("Speichern", on_click=speichern)
```

Der Handler ändert Werte und hört auf. Kein `update()`, keine Rückgabe. Das
Auto-Update schickt beide Änderungen (`feld`, `status`) in einer Übertragung.

### `on_change` — auf jeden Tastendruck reagieren

```python
def gefiltert(e: ft.ControlEvent) -> None:
    suchtext = e.control.value.lower()
    liste.controls = [
        ft.ListTile(title=ft.Text(u.name)) for u in uebungen if suchtext in u.name.lower()
    ]


ft.TextField(label="Suchen", on_change=gefiltert)
```

Bei jedem Zeichen baut der Handler die Liste neu. Bei ein paar hundert
Übungen ist das problemlos; bei Tausenden würde man den Aufbau in einen Task
mit kurzer Wartezeit verschieben (L07).

### `on_submit` — nur der fertige Wert

```python
async def eingegeben(e: ft.ControlEvent) -> None:
    hinzufuegen(e.control.value)
    e.control.value = ""
    await e.control.focus()  # Cursor bleibt im Feld — bereit für den nächsten Eintrag


ft.TextField(label="Neuer Eintrag", on_submit=eingegeben)
```

`focus()` ist eine Coroutine (sie muss über die Brücke und auf Antwort
warten), darum ist der Handler `async def` — mehr dazu in Abschnitt 5. Ohne
das `await` würde die Zeile nur ein Coroutine-Objekt erzeugen und wegwerfen;
der Cursor bliebe, wo er war.

### `on_change` an `Checkbox`, `Switch`, `Slider`

Alle drei melden über `e.control.value` — `bool` bei den ersten beiden,
`float` beim Slider:

```python
def umgeschaltet(e: ft.ControlEvent) -> None:
    einstellungen.dunkelmodus = e.control.value


def gezogen(e: ft.ControlEvent) -> None:
    anzeige.value = f"{e.control.value:.0f} s"


ft.Switch(label="Dunkelmodus", on_change=umgeschaltet)
ft.Slider(min=10, max=120, value=30, on_change=gezogen)
```

### `on_change` an `NavigationBar` — welcher Reiter?

```python
def wechseln(e: ft.ControlEvent) -> None:
    koerper.content = inhalte[e.control.selected_index]


ft.NavigationBar(on_change=wechseln, destinations=[...])
```

Hier heißt der Wert `selected_index`, nicht `value`. Das ist L03, Beispiel 1.

### `on_keyboard_event` — Tastenkürzel am Desktop

```python
def taste(e: ft.KeyboardEvent) -> None:
    if e.ctrl and e.key == "S":
        speichern()
    elif e.key == "Escape":
        abbrechen()


page.on_keyboard_event = taste
```

Der Handler hängt an der Seite, nicht an einem Control — es gibt nur eine
Tastatur. `e` ist hier ein `ft.KeyboardEvent` mit eigenen Feldern.

### `on_dismiss` — aufräumen, wenn ein Dialog zugeht

```python
dialog = ft.AlertDialog(
    title=ft.Text("Messung verwerfen?"),
    actions=[ft.TextButton("Ja", on_click=lambda e: page.pop_dialog())],
    on_dismiss=lambda e: print("Dialog ist zu — egal ob per Knopf oder Tipp daneben"),
)
page.show_dialog(dialog)
```

`on_dismiss` ist die verlässliche Stelle für „danach": Sie feuert, ob der
Benutzer nun „Ja" gedrückt, daneben getippt oder Escape gedrückt hat.

### `on_app_lifecycle_state_change` — das Handy schaltet den Bildschirm ab

```python
def zustand(e: ft.AppLifecycleStateChangeEvent) -> None:
    if e.state == ft.AppLifecycleState.PAUSE:
        messung.pausieren_oder_weiterlaufen_lassen()


page.on_app_lifecycle_state_change = zustand
```

Für die Live-Messung ist das der wichtigste Seiten-Handler: Geht die App in
den Hintergrund, entscheidet er, was mit dem Sensorstrom passiert. Kommt in
L10/L11 und im Extension-Ausblick wieder.

---

## 4. Ein Handler, viele Controls: Argumente mitgeben

Ein Handler bekommt genau ein Argument, das Event. Was, wenn er mehr wissen
muss — etwa *welche* Übung ein Knopf in einer Liste meint? Drei Wege, vom
einfachsten zum flexibelsten:

**`data` am Control.** Der Wert reist im Control mit und kommt über
`e.control.data` wieder heraus.

```python
def oeffnen(e: ft.ControlEvent) -> None:
    zeige_detail(e.control.data)


for u in uebungen:
    ft.ListTile(title=ft.Text(u.name), data=u.key, on_click=oeffnen)
```

**Lambda mit Default-Argument.** Kürzer, wenn man das Control nicht anfassen
will. Der Default-Trick `k=key` friert den Wert ein — ohne ihn würden alle
Lambdas dieselbe Variable teilen und am Ende alle den letzten Wert sehen.

```python
for key in UEBUNGEN:
    ft.ListTile(on_click=lambda e, k=key: zeige_detail(k))
```

**Fabrik (Closure).** Eine Funktion, die den Handler baut und dabei den Wert
als Parameter festhält. Klarer lesbar als der Default-Trick, ein paar Zeilen
länger.

```python
def oeffnen(key: str):
    def handler(e: ft.ControlEvent) -> None:
        zeige_detail(key)

    return handler


for key in UEBUNGEN:
    ft.ListTile(on_click=oeffnen(key))
```

L03 erklärt Lambda und Closure im Detail; hier nur die Faustregel: `data` für
eine id, Lambda für einen Einzeiler, Fabrik sobald der Handler mehr als eine
Zeile hat.

---

## 5. Synchron oder `async` — wann welcher Handler?

Beide Formen sind erlaubt, und Flet erkennt selbst, welche vorliegt:

```python
def sync_handler(e):            # Flet ruft: sync_handler(e)
    zaehler.value = "1"

async def async_handler(e):     # Flet ruft: await async_handler(e)
    await page.push_route("/detail")
```

Man braucht `async def` genau dann, wenn im Handler ein `await` stehen muss —
weil man eine Coroutine aufruft (`page.push_route`, `asyncio.sleep`, ein
BLE-Aufruf) und auf ihr Ergebnis warten will. Sonst ist `def` die einfachere
Wahl.

Ein Missverständnis dabei: `async` macht einen Handler **nicht** schneller
oder „parallel". Er läuft auf demselben Thread wie alles andere. Der
Unterschied ist nur, dass er an einem `await` anhalten und den Loop
weiterarbeiten lassen kann. Während er anhält, feuern andere Handler; sobald
er weitermacht, blockiert er wieder wie jeder andere Code.

### Lambda kann kein `await`

`lambda e: await …` ist ein `SyntaxError`. Wer in einem Lambda eine Coroutine
anstoßen will, macht daraus einen Task:

```python
on_click=lambda e: page.run_task(page.push_route, "/uebung/abc")
```

`page.run_task(fn, *args)` nimmt die Coroutine-Funktion **ohne Klammern**
und die Argumente dahinter. Der Handler kehrt sofort zurück, die Route wechselt
gleich danach. Ausführlich in L03, Glossar.

### Lange Arbeit gehört nicht in den Handler

```python
def auswerten(e):
    ergebnis = hrv_core.kennzahlen(rr)     # 2 Sekunden reines Rechnen
    anzeige.value = str(ergebnis)          # Oberfläche steht 2 Sekunden still
```

Ob `def` oder `async def` — Rechnen blockiert. Der Ausweg ist, die Arbeit in
einen Thread zu geben und die Oberfläche danach von Hand zu aktualisieren:

```python
async def auswerten(e):
    knopf.disabled = True
    knopf.update()                                       # sofort sichtbar
    ergebnis = await asyncio.to_thread(hrv_core.kennzahlen, rr)
    anzeige.value = str(ergebnis)
    knopf.disabled = False                               # Auto-Update erledigt den Rest
```

Das `knopf.update()` in Zeile 3 ist absichtlich: Das Auto-Update kommt erst,
wenn der Handler *durch* ist — also nach dem `await`. Wer den Knopf schon
vorher grau sehen will, schickt ihn selbst. Der Rest kommt in L07.

### Der Generator-Trick

Eine Randnotiz, die hin und wieder praktisch ist: Ein Handler darf ein
Generator sein. Bei jedem `yield` macht Flet ein Zwischen-Update:

```python
def zaehlen(e):
    for i in range(1, 4):
        anzeige.value = str(i)
        yield                       # → Auto-Update, Bildschirm zeigt i
        time.sleep(0.5)             # blockiert! nur zur Demonstration
```

In echtem Code nimmt man dafür einen async-Handler mit `await asyncio.sleep`.
Der Trick zeigt aber gut, wann das Auto-Update greift: nach dem Handler — oder
an jeder Stelle, an der der Handler die Kontrolle abgibt.

---

## 6. Was passiert, wenn ein Handler abstürzt?

Wirft ein Handler eine Exception, fängt Flet sie ab: Der Traceback landet im
Terminal (`Unhandled error in 'on_click' handler`), und der Bildschirmseite
wird der Fehlertext gemeldet. Der Python-Prozess läuft weiter; der nächste
Klick wird wieder verarbeitet.

Was **nicht** passiert: das Auto-Update. Es kommt erst *nach* dem Handler,
und dorthin gelangt Flet nicht mehr. Änderungen, die der Handler vor dem
Absturz gemacht hat, bleiben auf der Python-Seite liegen und erscheinen erst
beim nächsten Ereignis — dasselbe Muster wie die „Änderung erscheint erst beim
nächsten Klick"-Stolperfalle aus L02. Wer also nach einem Klick eine halb
aktualisierte Oberfläche sieht, schaut zuerst ins Terminal.

Für die Entwicklung reicht das. Auf dem Handy gibt es kein Terminal; dort
fängt man Fehler, die man erwartet (Sensor weg, Datei nicht lesbar), im
Handler selbst mit `try`/`except` ab und zeigt sie dem Benutzer — etwa als
`SnackBar`.

---

## 7. Handler entfernen, ersetzen, abschalten

Ein Handler ist ein Attribut. Alles, was mit Attributen geht, geht auch hier:

```python
knopf.on_click = None          # abhängen — Klick tut nichts mehr
knopf.on_click = anderer       # ersetzen
knopf.disabled = True          # Control grau und tot — meist das, was man will
```

Wer einen Knopf nur *vorübergehend* stilllegen will (während eine Messung
läuft, während gespeichert wird), nimmt `disabled`. Das sieht der Benutzer;
ein abgehängter Handler sieht aus wie ein kaputter Knopf.

---

## Wo das in der App vorkommt

- **`ui/app.py`** — `on_change` an der `NavigationBar` wechselt den Inhalt.
  Das ist L03, Beispiel 1, mit anderen Ansichten.
- **Eingabemaske (L06)** — `ui/components/spec_form.py` erzeugt aus einer
  `ResultSpec` Felder mit `on_change`; das Speichern-`on_click` sammelt die
  Werte ein und baut den `SessionEntry`.
- **Live-Messung (L11)** — `on_click` startet und stoppt den Task, der den
  Sensorstrom liest; `on_app_lifecycle_state_change` entscheidet, was beim
  Wechsel in den Hintergrund passiert. Die Messwerte selbst kommen **nicht**
  über Handler herein, sondern über `async for` aus der Geräte-Queue — Handler
  sind für das, was der Benutzer tut, nicht für das, was das Gerät tut.

---

## Stolperfallen

- **`on_click=gedrueckt()`** mit Klammern — ruft die Funktion sofort auf und
  hängt `None` an den Knopf. Ohne Klammern übergeben.
- **Lambda in einer Schleife ohne `k=key`** — alle Knöpfe tun dasselbe, nämlich
  das des letzten Durchlaufs. Default-Argument oder Fabrik (Abschnitt 4).
- **`time.sleep()` oder schwere Rechnung im Handler** — Oberfläche friert.
  `await asyncio.sleep()` bzw. `asyncio.to_thread()` (Abschnitt 5).
- **`lambda e: await …`** — `SyntaxError`. `page.run_task(fn, args…)`.
- **Handler von Hand aufgerufen, Bildschirm ändert sich nicht** — kein
  Ereignis, kein Auto-Update. `page.update()` in den Handler schreiben oder
  danach aufrufen.
- **`on_change` am `TextField` feuert zu oft** — das ist so gedacht. Für den
  fertigen Wert `on_submit` oder `on_blur` nehmen.
- **Handler wirft Exception, danach fehlen Änderungen** — das Auto-Update
  fällt bei einer Exception aus. Terminal lesen, Fehler beheben.
- **Eine Control-Methode tut nichts** — `focus()`, `scroll_to()` und andere
  Methoden, die über die Brücke müssen, sind Coroutinen. Ohne `await` passiert
  nichts; der Handler muss dafür `async def` sein.
- **`e.data` ist leer** — bei `on_click` normal. Der Wert steht in
  `e.control.value`, `e.control.selected_index` oder `e.control.data`.
