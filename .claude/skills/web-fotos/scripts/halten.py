"""Die Halte-Verbindung: setzt die Handybreite und bleibt offen.

Aufruf: ``python halten.py <cdp-port> [breite] [hoehe] [dark|light]`` — Vorgabe 412 × 860.
Chromium hebt die Übersteuerung auf, sobald sich die Verbindung trennt, die sie gesetzt hat;
darum läuft dieses Skript im Hintergrund weiter, und ``cdp.py`` setzt selbst keine Breite.
Erst **nach** dem Laden der Seite starten.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request

import websockets


async def main(port: str, breite: int, hoehe: int, schema: str | None) -> None:
    ziele = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
    ws_url = next(t["webSocketDebuggerUrl"] for t in ziele if t["type"] == "page")
    async with websockets.connect(ws_url, max_size=2**26) as ws:
        masse = {"width": breite, "height": hoehe, "deviceScaleFactor": 1, "mobile": True}
        await ws.send(
            json.dumps({"id": 1, "method": "Emulation.setDeviceMetricsOverride", "params": masse})
        )
        if schema:
            medien = {"features": [{"name": "prefers-color-scheme", "value": schema}]}
            await ws.send(
                json.dumps({"id": 2, "method": "Emulation.setEmulatedMedia", "params": medien})
            )
        while True:
            await ws.recv()


if __name__ == "__main__":
    a = sys.argv[1:]
    asyncio.run(
        main(
            a[0],
            int(a[1]) if len(a) > 1 else 412,
            int(a[2]) if len(a) > 2 else 860,
            a[3] if len(a) > 3 else None,
        )
    )
