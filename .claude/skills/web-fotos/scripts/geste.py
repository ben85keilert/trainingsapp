"""Gesten mit Foto **mitten im Ziehen** (Chrome-DevTools-Protokoll) — ergänzt `cdp.py`: mit
Maus oder Finger (Touch-Ereignisse) ziehen, tippen, gedrückt halten. Der Reiter „Ablauf“ zeigt
die Ziele „Ende“/„zurück“ nur, während gezogen wird; das sieht man nur auf einem Foto vor dem
Loslassen (Ben, 17.11.2026: in den Skill übernommen).

Aufruf: ``python geste.py <cdp-port> <maus|finger> <x1> <y1> <x2> <y2> [<foto_mitte.png>
[<foto_danach.png>]]`` — zieht von (x1, y1) nach (x2, y2); das erste Foto entsteht kurz vor
dem Loslassen (der Zeiger steht schon über dem Ziel), das zweite danach.
``python geste.py <cdp-port> tipp <x> <y> [<foto.png>]`` — ein Fingertipp;
``python geste.py <cdp-port> halten <x> <y> [<foto.png>]`` — Finger 0,9 s halten.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path

import websockets


async def main(port: str, art: str, zahlen: list[int], fotos: list[str]) -> None:
    ziele = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
    ws_url = next(t["webSocketDebuggerUrl"] for t in ziele if t["type"] == "page")
    async with websockets.connect(ws_url, max_size=2**26) as ws:
        n = 0

        async def cmd(method: str, **params: object) -> dict:
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == n:
                    return m.get("result", {})

        async def foto(datei: str, rad: bool) -> None:
            if rad:
                # wie `cdp.py`: sonst liefert kopfloses Chromium das alte Bild
                await cmd(
                    "Input.dispatchMouseEvent", type="mouseWheel", x=2, y=2, deltaX=0, deltaY=0
                )
                await asyncio.sleep(0.8)
            bild = await cmd("Page.captureScreenshot", format="png")
            Path(datei).write_bytes(base64.b64decode(bild["data"]))
            print(datei)

        async def finger(was: str, x: int, y: int) -> None:
            punkte = [] if was == "touchEnd" else [{"x": x, "y": y, "id": 1}]
            await cmd("Input.dispatchTouchEvent", type=was, touchPoints=punkte)

        async def maus(was: str, x: int, y: int, **mehr: object) -> None:
            await cmd("Input.dispatchMouseEvent", type=was, x=x, y=y, **mehr)

        if art in ("tipp", "halten"):
            x, y = zahlen
            await finger("touchStart", x, y)
            await asyncio.sleep(0.9 if art == "halten" else 0.05)
            await finger("touchEnd", x, y)
            await asyncio.sleep(1.5)
            if fotos:
                await foto(fotos[0], True)
            return
        x1, y1, x2, y2 = zahlen
        schritte = 14
        if art == "finger":
            await finger("touchStart", x1, y1)
        else:
            await maus("mouseMoved", x1, y1)
            await maus("mousePressed", x1, y1, button="left", buttons=1, clickCount=1)
        await asyncio.sleep(0.08)
        for k in range(1, schritte + 1):
            x, y = x1 + (x2 - x1) * k // schritte, y1 + (y2 - y1) * k // schritte
            if art == "finger":
                await finger("touchMove", x, y)
            else:
                await maus("mouseMoved", x, y, button="left", buttons=1)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.8)
        if fotos:
            # ohne Mausrad: das Rad-Ereignis bräche das Ziehen ab — dafür ein Wackler am Ziel
            for d in (1, 0):
                if art == "finger":
                    await finger("touchMove", x2 + d, y2)
                else:
                    await maus("mouseMoved", x2 + d, y2, button="left", buttons=1)
                await asyncio.sleep(0.25)
            await foto(fotos[0], False)
        if art == "finger":
            await finger("touchEnd", x2, y2)
        else:
            await maus("mouseReleased", x2, y2, button="left", buttons=0, clickCount=1)
            await maus("mouseMoved", 2, 2)
        await asyncio.sleep(1.5)
        if len(fotos) > 1:
            await foto(fotos[1], True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 4:
        sys.exit(__doc__)
    anzahl = 2 if a[1] in ("tipp", "halten") else 4
    asyncio.run(main(a[0], a[1], [int(v) for v in a[2 : 2 + anzahl]], a[2 + anzahl :]))
