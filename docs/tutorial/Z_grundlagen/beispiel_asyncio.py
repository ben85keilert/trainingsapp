"""Generator, Coroutine, Task — dieselbe Idee in drei Stufen.

Ausführen:  uv run python docs/tutorial/Z_grundlagen/beispiel_asyncio.py
Ausgabe lesen und mit dem Text in asyncio.md vergleichen.
"""

import asyncio
import time

# ---------------------------------------------------------------- 1. Generator


def zaehler():
    print("  generator: start")
    yield 1
    print("  generator: weiter")
    yield 2
    print("  generator: ende")


print("1. Generator")
g = zaehler()
print("  erzeugt — bisher ist nichts gedruckt worden")
print("  next ->", next(g))
print("  next ->", next(g))
try:
    next(g)
except StopIteration:
    print("  StopIteration: der Generator ist durch")


# --------------------------------------------------------- 2. + 3. Coroutine, Task


async def kaffee():
    print("  kaffee: wasser aufsetzen")
    await asyncio.sleep(0.3)
    print("  kaffee: fertig")
    return "Kaffee"


async def toast():
    print("  toast: rein damit")
    await asyncio.sleep(0.2)
    print("  toast: fertig")
    return "Toast"


async def main():
    print("\n2. Coroutine")
    c = kaffee()
    print("  erzeugt:", type(c).__name__, "— läuft noch nicht")
    print("  jetzt await:")
    ergebnis = await c
    print("  ergebnis:", ergebnis)

    print("\n3. Task — zwei Coroutinen nebeneinander")
    start = time.perf_counter()
    t1 = asyncio.create_task(kaffee())
    t2 = asyncio.create_task(toast())
    print("  beide eingeplant:", type(t1).__name__)
    print("  gesammelt:", await t1, "+", await t2)
    dauer = time.perf_counter() - start
    print(f"  dauer: {dauer:.2f} s — nicht 0.5, weil beide Wartezeiten überlappen")


asyncio.run(main())
