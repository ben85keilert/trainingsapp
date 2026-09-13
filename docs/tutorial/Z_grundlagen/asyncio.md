# Generator, Coroutine, Task — was ist was?

Die drei Begriffe bauen aufeinander auf. Wer den Generator versteht, versteht
die Coroutine; wer die Coroutine versteht, versteht die Task. Deshalb in
dieser Reihenfolge.

Lauffähig: `uv run python docs/tutorial/Z_grundlagen/beispiel_asyncio.py`

---

## Glossar

Zum Nachschlagen, wenn ein Begriff im Text auftaucht. Die Abschnitte danach
erklären die Zusammenhänge.

**Prozess** — ein laufendes Programm mit eigenem Speicher. `uv run python …`
startet einen Prozess. Zwei Prozesse sehen die Variablen des jeweils anderen
nicht.

**Thread** — ein Ausführungsstrang *innerhalb* eines Prozesses. Ein Prozess hat
mindestens einen; mehrere Threads teilen sich den Speicher des Prozesses. Ein
Thread führt Code linear aus, eine Anweisung nach der anderen. Alles in diesem
Text spielt sich in **einem** Thread ab.

**Parallelität** — mehrere Dinge laufen wirklich gleichzeitig, auf mehreren
CPU-Kernen. Braucht mehrere Threads oder Prozesse. asyncio macht das **nicht**.

**Nebenläufigkeit** — mehrere Dinge sind gleichzeitig *unterwegs*, aber es
läuft immer nur eines; sie wechseln sich ab, sobald eines warten muss. Das ist,
was asyncio macht.

**Event Loop** — die Schleife, die das Abwechseln organisiert. Sie hält eine
Liste, wer weitermachen darf, und wartet auf Timer, Netzwerk, Bluetooth.
`asyncio.run(main())` startet sie und beendet sie, wenn `main()` fertig ist.

**Generator** — eine Funktion mit `yield`. Ihr Aufruf führt nichts aus, sondern
liefert ein Objekt, das man mit `next()` schrittweise laufen lässt; an jedem
`yield` hält es an und merkt sich den Zustand.
```python
def zaehler():
    yield 1
    yield 2
g = zaehler(); next(g)  # 1
```

**Coroutine** — eine Funktion mit `async def`. Ihr Aufruf führt ebenfalls
nichts aus, sondern liefert ein Objekt, das der Event Loop laufen lässt; an
jedem `await` hält es an und gibt die Kontrolle ab.
```python
async def kaffee():
    await asyncio.sleep(2)
    return "Kaffee"
c = kaffee()            # noch nichts passiert
```

**await** — „Führ das aus und warte, bis es fertig ist." Die Coroutine, in der
das `await` steht, hält so lange an. Nur innerhalb von `async def` erlaubt.
```python
ergebnis = await kaffee()   # "Kaffee", nach 2 Sekunden
```

**Task** — eine Coroutine, die beim Event Loop angemeldet ist und nebenbei
läuft. `asyncio.create_task()` erzeugt sie und gibt sofort zurück; die
aufrufende Coroutine läuft weiter. Die Task weiß, ob ihre Coroutine noch läuft,
fertig ist oder eine Exception geworfen hat.
```python
t = asyncio.create_task(kaffee())   # läuft ab jetzt nebenbei
...                                  # hier anderes tun
ergebnis = await t                   # erst jetzt wird gewartet
```

**Future** — ein Platzhalter für ein Ergebnis, das noch nicht da ist. Wer darauf
`await`et, wird geweckt, sobald jemand das Ergebnis einträgt. `asyncio.sleep`,
`queue.get()` und Tasks sind alle Futures oder liefern welche. Man baut selten
selbst eines, aber alles darüber läuft darauf hinaus.

---

## 1. Generator — eine Funktion, die pausieren kann

Eine normale Funktion läuft von oben nach unten durch und ist dann weg. Ein
Generator hat `yield` statt `return`: an dieser Stelle **hält er an, gibt einen
Wert heraus und merkt sich, wo er war.**

```python
def zaehler():
    print("start")
    yield 1
    print("weiter")
    yield 2
    print("ende")

g = zaehler()      # erzeugt nur das Generator-Objekt — es läuft noch NICHTS
next(g)            # druckt "start", liefert 1, hält bei yield an
next(g)            # druckt "weiter", liefert 2, hält wieder an
next(g)            # druckt "ende", dann StopIteration: der Generator ist fertig
```

Zwei Dinge sind hier wichtig:

- **Der Aufruf `zaehler()` führt nichts aus.** Er gibt ein Objekt zurück, das
  darauf wartet, angestoßen zu werden. Das ist anders als bei jeder normalen
  Funktion — und genau das Verhalten, das später bei `async def` verwirrt.
- **Zwischen zwei `next()` bleibt der Zustand erhalten.** Lokale Variablen,
  Position im Code — alles eingefroren. Das ist die Fähigkeit, die asyncio braucht.

### Woher weiß Python, dass es nichts ausführen soll?

Naheliegende Vermutung: Python fängt an, die Funktion auszuführen, merkt beim
`yield`, dass es ein Generator ist, und bricht ab. So ist es **nicht** — die
Entscheidung fällt viel früher.

Beim Einlesen der Datei übersetzt Python jede Funktion in Bytecode. Findet der
Compiler dabei irgendwo im Funktionskörper ein `yield`, setzt er am fertigen
Code-Objekt ein Flag: *„das ist ein Generator"*. Das gilt selbst dann, wenn das
`yield` nie erreicht würde — `if False: yield` reicht.

```python
import inspect
inspect.isgeneratorfunction(zaehler)   # True — steht fest, bevor je etwas läuft
```

Beim Aufruf `zaehler()` schaut Python auf dieses Flag und verzweigt:

- **Flag nicht gesetzt** → normaler Aufruf, der Körper wird sofort ausgeführt.
- **Flag gesetzt** → der Körper wird **gar nicht erst betreten**. Es wird nur
  ein Generator-Objekt gebaut, das den noch nicht gestarteten Funktionsrahmen
  in sich trägt. Erst `next(g)` setzt ihn in Gang.

Es wird also nichts gestoppt oder zurückgenommen. Ein Aufruf einer
Generator-Funktion war nie ein Aufruf des Körpers — er war von Anfang an nur
das Bauen eines Objekts. Bei `async def` läuft dasselbe mit einem anderen Flag
(*„das ist eine Coroutine"*) und einem `coroutine`-Objekt statt `generator`.

---

## 2. Coroutine — ein Generator, der auf etwas *wartet*

`async def` erzeugt eine Coroutine. Sie beruht auf demselben Trick wie der
Generator — eine Funktion, die einfrieren und fortsetzen kann — und `await`
ist die Stelle, an der sie anhält (wie `yield`). Neu ist die Bedeutung:
*„Ich warte auf dieses Ding. Mach in der Zeit etwas anderes."*

```python
async def kaffee():
    print("Wasser aufsetzen")
    await asyncio.sleep(2)     # hier anhalten, Kontrolle abgeben
    print("Kaffee fertig")

c = kaffee()       # wie beim Generator: erzeugt nur das Objekt, läuft NICHT
```

Der Unterschied zum Generator: Beim Generator rufst *du* `next()` auf. Bei der
Coroutine tut das jemand anderes — der **Event Loop**. Du gibst die Coroutine
nur ab, mit einem von zwei Befehlen:

| Befehl | Bedeutung |
|---|---|
| `await kaffee()` | „Führ das aus und warte, bis es fertig ist." Die aufrufende Coroutine hält so lange an. |
| `asyncio.create_task(kaffee())` | „Führ das nebenbei aus." Die aufrufende Coroutine läuft sofort weiter. |

Vergisst du beides, passiert nichts — Python warnt dann mit
`RuntimeWarning: coroutine 'kaffee' was never awaited`.

### `await` oder `create_task` — wer hält an?

„Die aufrufende Coroutine hält an" meint die Funktion, in der das `await`
steht. Im Beispiel unten ist das `main()`. Es gibt keinen „Vordergrundprozess"
daneben — `main()` und `kaffee()` laufen im selben Thread, und der Loop
schaltet zwischen ihnen um.

```python
async def main():
    print("vorher")
    await kaffee()          # main() hält HIER an, bis kaffee() durch ist
    print("nachher")        # kommt garantiert nach "Kaffee fertig"
```

`kaffee()` wird nicht pausiert — es läuft gerade erst los. Pausiert wird
`main()`: sie kommt nicht über diese Zeile hinaus, bis `kaffee()` fertig ist.
`await` verhält sich also wie ein gewöhnlicher Funktionsaufruf, nur dass der
Loop in der Wartezeit *andere* Tasks bedienen darf.

```python
async def main():
    print("vorher")
    t = asyncio.create_task(kaffee())   # kaffee() angemeldet — main() läuft SOFORT weiter
    print("nachher")                     # kommt VOR "Kaffee fertig"
    await t                              # erst hier wartet main() wirklich
```

`create_task()` gibt sofort zurück. `main()` hält nicht an; `kaffee()` läuft
nebenbei als eigene Task. Warten passiert erst, wenn du `await t` schreibst —
und du entscheidest, wo das steht.

| | `await kaffee()` | `create_task(kaffee())` |
|---|---|---|
| `kaffee()` startet | sofort, an dieser Stelle | sofort, beim nächsten Loop-Durchlauf |
| `main()` währenddessen | hält an | läuft weiter |
| Ergebnis | Rückgabewert des `await` | später, per `await t` |

Deshalb laufen Kaffee und Toast in Abschnitt 3 gleichzeitig: beide werden per
`create_task` gestartet, *bevor* auf eines gewartet wird. Mit `await kaffee()`
gefolgt von `await toast()` liefen sie nacheinander — 2 + 3 statt 3 Sekunden.

### Sind Generator und Coroutine nun dasselbe oder nicht?

Weder noch: **gleicher Mechanismus, unterschiedlicher Vertrag.**

Vor Python 3.5 gab es `async`/`await` nicht. Coroutinen *waren* damals
Generatoren, per Konvention anders benutzt:

```python
@asyncio.coroutine          # so sah es bis Python 3.4 aus
def kaffee():
    yield from asyncio.sleep(2)
```

Dass Python die beiden dann zu getrennten Typen gemacht hat, liegt nicht an
der Technik darunter, sondern an der **Verwechslungsgefahr**. Ein Generator ist
zum Iterieren gedacht — viele Werte nacheinander. Eine Coroutine ist zum
einmaligen Warten gedacht — ein Ergebnis am Ende. Python sorgt dafür, dass man
das nicht durcheinanderbringt:

```python
for x in zaehler(): ...    # geht: Generatoren sind iterierbar
for x in kaffee():  ...    # TypeError: Coroutinen sind es nicht
```

| | Generator | Coroutine |
|---|---|---|
| hält an bei | `yield` | `await` |
| gedacht für | viele Werte liefern | auf ein Ergebnis warten |
| wer setzt fort | du, mit `next()` | der Event Loop |
| `for x in …` | ja | nein (`TypeError`) |
| darunter (CPython) | eingefrorener Funktionsrahmen | derselbe Mechanismus |

Die Trennung ist also eine bewusste Schutzmaßnahme der Sprache, keine zweite
Erfindung. Wer den Generator verstanden hat, muss für die Coroutine nur eines
dazulernen: Nicht du stößt sie an, sondern der Event Loop.

---

## 3. Task — die Coroutine, wenn sie beim Event Loop angemeldet ist

`create_task()` gibt ein **Task-Objekt** zurück. Das ist der Verwaltungsrahmen
um die Coroutine: Es weiß, ob sie noch läuft, fertig ist oder eine Exception
geworfen hat, und es sorgt dafür, dass der Event Loop sie nach jedem `await`
wieder anstößt.

Man kann es sich so vorstellen:

```
Coroutine  =  das Rezept (der Code, der pausieren kann)
Task       =  der Koch, der das Rezept gerade abarbeitet
Event Loop =  die Küche, die viele Köche im Wechsel bedient
```

Jeder Koch arbeitet, bis er warten muss (Wasser kocht, Ofen heizt) — dann tritt
er zurück, und die Küche gibt einem anderen Koch den Herd. Es steht immer nur
**einer** am Herd — warum das so ist und was es bedeutet, klärt Abschnitt 4.

```python
async def main():
    t1 = asyncio.create_task(kaffee())    # Koch 1 fängt an
    t2 = asyncio.create_task(toast())     # Koch 2 fängt an
    await t1                              # warten, bis Koch 1 fertig ist
    await t2

asyncio.run(main())                       # Küche öffnen, main() ausführen, Küche schließen
```

`asyncio.run()` startet den Event Loop, wickelt `main()` in eine Task und
lässt den Loop laufen, bis `main()` durch ist.

---

## 4. Nebenläufig, nicht parallel

Normalerweise läuft Python-Code linear von oben nach unten. Mit Coroutinen
sieht es aus, als liefen mehrere Dinge gleichzeitig. Was davon ist echt?

Zuerst die Begriffe sauber (siehe auch Glossar):

```
Prozess "python"                    eigener Speicher
└─ Thread 1                         führt Code linear aus, eine Anweisung nach der anderen
   └─ Event Loop
      ├─ Task main()                 ← es läuft immer nur EINE davon
      ├─ Task kaffee()
      └─ Task toast()
```

Alles, was in diesem Text passiert, spielt sich in **einem Thread** ab, auf
**einem CPU-Kern**. Das ist keine Parallelität. Es ist **Nebenläufigkeit**:
mehrere Tasks sind gleichzeitig *unterwegs*, aber zu jedem Zeitpunkt rechnet
genau eine. Die anderen stehen an einem `await` und warten.

Was asyncio also „simuliert", ist nicht, dass mehrere Dinge gleichzeitig
rechnen — sondern dass Wartezeit nicht verschwendet wird. Während `kaffee()`
bei `await asyncio.sleep(2)` steht, tut die CPU für diese Task nichts. Genau
diese Lücke bekommt `toast()`.

Das hat eine harte Grenze: Sobald eine Task wirklich rechnet statt zu warten,
steht alles andere still.

```python
async def auswerten():
    summe = sum(i * i for i in range(50_000_000))   # kein await — blockiert ALLE Tasks
    return summe
```

Hier gibt es keine Wartezeit, die der Loop füllen könnte. Für die Dauer der
Rechnung läuft weder `main()` noch irgendein Bluetooth-Callback — die
Oberfläche friert ein. Dafür gibt es zwei Auswege, beide kommen in L07:

- `asyncio.to_thread(rechnung)` — schiebt die Rechnung in einen zweiten
  Thread, der Loop läuft im ersten weiter. Für die HRV-Auswertung der Weg.
- `multiprocessing` — mehrere Prozesse, mehrere Kerne, echte Parallelität.
  Für diese App nicht nötig.

| | asyncio | Threads | Prozesse |
|---|---|---|---|
| gleichzeitig rechnen | nein | in Python meist nein (GIL) | ja |
| Wartezeit überbrücken | ja | ja | ja |
| gemeinsamer Speicher | ja | ja | nein |
| gut für | Netzwerk, BLE, Timer, UI | blockierende Bibliotheken | schwere Rechnung |

---

## Was passiert bei einem `await` genau?

1. Die Coroutine trifft auf `await asyncio.sleep(2)`. `sleep` gibt ein
   **Future** zurück — ein Platzhalter für „ein Ergebnis, das noch nicht da ist"
   — und registriert beim Loop einen Timer: *in 2 Sekunden dieses Future auf
   fertig setzen.*
2. Die Coroutine reicht das Future nach oben an ihre Task und **hält an**.
3. Die Task sagt dem Future: „Wenn du fertig bist, weck mich." Dann gibt sie
   die Kontrolle an den Event Loop zurück.
4. Der Loop bedient andere Tasks, prüft Timer, wartet auf Netzwerk/Bluetooth.
5. Der Timer läuft ab, das Future wird fertig, die Task wird geweckt.
6. Die Task ruft die Coroutine wieder auf — und die macht **genau an der
   `await`-Stelle** weiter, mit dem Ergebnis des Futures als Wert des Ausdrucks.

Es gibt keine Magie: der Loop ist eine `while True`-Schleife, die Callbacks
und Timer abarbeitet. `async`/`await` ist nur die Schreibweise, damit man
diese Callbacks nicht selbst verketten muss.

---

## Wo das in der App vorkommt

In `devices/` steht `async for messwert in quelle:`. Das ist im Kern ein
`await queue.get()` in einer Schleife. Solange kein Messwert in der Queue liegt,
ist die Konsumenten-Task angehalten (Schritt 3 oben); der Loop kann derweil
den nächsten Bluetooth-Callback verarbeiten, der per `queue.put()` einen Wert
einstellt — und das weckt die Konsumenten-Task. Zwei Beteiligte, ein Thread,
keine Locks.

Lektion L07 baut darauf auf: Timer in Flet, Tasks sauber abbrechen, was
passiert, wenn eine Task eine Exception wirft.

---

## Stolperfallen

- **`kaffee()` ohne `await`** — erzeugt nur das Objekt, führt nichts aus.
- **`time.sleep()` in einer Coroutine** — blockiert den ganzen Loop, weil es
  kein `await` ist. Immer `await asyncio.sleep()`.
- **Rechenlastiger Code** (z. B. HRV-Auswertung) blockiert den Loop genauso —
  dafür gibt es `asyncio.to_thread()`, kommt in L07.
- **Task-Referenz wegwerfen** — `asyncio.create_task(x)` ohne die Rückgabe zu
  behalten kann dazu führen, dass die Task vom Garbage Collector eingesammelt
  wird, bevor sie fertig ist. Die Referenz behalten (Liste, Set, Attribut).
