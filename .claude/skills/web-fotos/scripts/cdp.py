"""Chromium fernsteuern (Chrome-DevTools-Protokoll): Fotos, Klicks, Text.

Aufruf: ``python cdp.py <cdp-port> <befehl> [werte] [<befehl> …]`` — mehrere hintereinander:

- ``nav <url>``       Seite laden (wartet 12 s: Flutter braucht so lange). Beginnt eine neue
                      Flet-Sitzung — innerhalb der App lieber klicken.
- ``frisch <url>``    wie ``nav``, vorher den Speicher der Herkunft leeren (Flet-Web nähme
                      sonst die alte Sitzung wieder auf).
- ``klick <x> <y>``   Mauszeiger hin, drücken, loslassen, Zeiger an den Rand (kein Hover).
- ``lang <x> <y>``    gedrückt halten (0,9 s).
- ``ziehen <x1> <y1> <x2> <y2>``
- ``rollen <dy>``     Mausrad in der Bildmitte; ``rollen_bei <dy> <y>`` an der Höhe y.
- ``tippen <text>``   Text ins Feld mit Fokus (vorher anklicken).
- ``warten <s>``
- ``foto <datei>``    PNG; vorher ein Mausrad-Ereignis, sonst liefert Chromium das alte Bild.
- ``js <ausdruck>``   auswerten und drucken (z. B. ``window.innerWidth``).

Die Breite setzt **nur** ``halten.py`` — ein Aufruf hier, der sie setzte, höbe sie beim
Trennen wieder auf. Fotokoordinaten sind Klickkoordinaten.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import websockets


async def main(port: str, args: list[str]) -> None:
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

        async def maus(art: str, x: int, y: int, **mehr: object) -> None:
            await cmd("Input.dispatchMouseEvent", type=art, x=x, y=y, **mehr)

        async def druecken(x: int, y: int, halten: float = 0.0) -> None:
            await maus("mouseMoved", x, y)
            await maus("mousePressed", x, y, button="left", buttons=1, clickCount=1)
            await asyncio.sleep(halten)
            await maus("mouseReleased", x, y, button="left", buttons=0, clickCount=1)
            await maus("mouseMoved", 2, 2)
            await asyncio.sleep(1.5)

        i = 0
        while i < len(args):
            was = args[i]
            if was in ("nav", "frisch"):
                url = args[i + 1]
                if was == "frisch":
                    teile = urlsplit(url)
                    await cmd("Page.navigate", url="about:blank")
                    await cmd(
                        "Storage.clearDataForOrigin",
                        origin=f"{teile.scheme}://{teile.netloc}",
                        storageTypes="all",
                    )
                await cmd("Page.navigate", url=url)
                await asyncio.sleep(12)
                i += 2
            elif was in ("klick", "lang"):
                await druecken(int(args[i + 1]), int(args[i + 2]), 0.9 if was == "lang" else 0.0)
                i += 3
            elif was == "ziehen":
                x1, y1, x2, y2 = (int(v) for v in args[i + 1 : i + 5])
                await maus("mouseMoved", x1, y1)
                await maus("mousePressed", x1, y1, button="left", buttons=1, clickCount=1)
                for k in range(1, 9):
                    x, y = x1 + (x2 - x1) * k // 8, y1 + (y2 - y1) * k // 8
                    await maus("mouseMoved", x, y, button="left", buttons=1)
                    await asyncio.sleep(0.05)
                await maus("mouseReleased", x2, y2, button="left", buttons=0, clickCount=1)
                await asyncio.sleep(1.2)
                i += 5
            elif was in ("rollen", "rollen_bei"):
                y = int(args[i + 2]) if was == "rollen_bei" else 500
                await maus("mouseWheel", 200, y, deltaX=0, deltaY=int(args[i + 1]))
                await asyncio.sleep(1.2)
                i += 3 if was == "rollen_bei" else 2
            elif was == "tippen":
                await cmd("Input.insertText", text=args[i + 1])
                await asyncio.sleep(0.8)
                i += 2
            elif was == "warten":
                await asyncio.sleep(float(args[i + 1]))
                i += 2
            elif was == "foto":
                await maus("mouseWheel", 200, 500, deltaX=0, deltaY=1)
                await asyncio.sleep(0.8)
                bild = await cmd("Page.captureScreenshot", format="png")
                Path(args[i + 1]).write_bytes(base64.b64decode(bild["data"]))
                print(args[i + 1])
                i += 2
            elif was == "js":
                antwort = await cmd("Runtime.evaluate", expression=args[i + 1])
                print(antwort.get("result", {}).get("value"))
                i += 2
            else:
                sys.exit(f"unbekannter Befehl: {was}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
