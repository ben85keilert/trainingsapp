# Generator, Coroutine, Task — was ist was?

Die drei Begriffe bauen aufeinander auf. Wer den Generator versteht, versteht
die Coroutine; wer die Coroutine versteht, versteht die Task. Deshalb in
dieser Reihenfolge.

Lauffähig: `uv run python docs/tutorial/Z_grundlagen/beispiel_asyncio.py`

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

---

## 2. Coroutine — ein Generator, der auf etwas *wartet*

`async def` erzeugt eine Coroutine. Technisch ist das ein Generator mit anderer
Schreibweise: `await` ist die Stelle, an der sie anhält (wie `yield`), aber mit
einer Bedeutung dazu: *„Ich warte auf dieses Ding. Mach in der Zeit etwas
anderes."*

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
**einer** am Herd. Das ist der wichtigste Punkt: asyncio ist **kein** Parallelismus.
Es füllt Wartezeiten, nicht CPU-Zeit.

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
