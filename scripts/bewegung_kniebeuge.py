"""Beispiel-Bildfolge „Kniebeuge“ (Ben, 7.11.2026: „Mache exemplarisch ein Gif oder so für
Kniebeugen. Vermutlich reicht der Hinweg und dann wird die Bewegung vorwärts/rückwärts
animiert“).

Zeichnet den **Hinweg** (Stand → tiefe Hocke) als Strichfigur von der Seite, `N` quadratische
Bilder nebeneinander in **einer** PNG-Datei (`core.bewegungsbild`: Bildfolge = Breite ist ein
Vielfaches der Höhe). Die App spielt sie im Takt vor (Phase „ab“) und zurück („auf“), ohne Takt
als Pendel. Dazu ein GIF als Pendel zum Anschauen.

Nur zum Entwickeln (braucht Pillow, nicht in der App):
    uv run --with pillow python scripts/bewegung_kniebeuge.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

N = 12
KANTE = 256
ZIEL = Path("src/trainingsapp/ui/assets/bewegung")


def figur(t: float) -> Image.Image:
    """Ein Bild für die Tiefe ``t`` (0 = Stand, 1 = Hocke) — Seitenansicht, nach links schauend."""
    s = 4  # Überabtastung gegen Treppen
    k = KANTE * s
    bild = Image.new("RGBA", (k, k), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)
    strich = 11 * s
    farbe = (46, 125, 110, 255)  # Petrol der App
    akzent = (209, 73, 91, 255)
    boden = k * 0.88
    # Beinlängen (Oberschenkel, Unterschenkel), Rumpf, Kopf
    ober, unter, rumpf, kopf = k * 0.24, k * 0.24, k * 0.26, k * 0.055
    # Knie- und Hüftwinkel aus der Tiefe: Hocke = Knie 95°, Hüfte vorgebeugt
    knie = math.radians(180 - 85 * t)  # Innenwinkel am Knie
    neigung = math.radians(0 + 38 * t)  # Rumpf nach vorn
    fuss_x = k * 0.52
    knoechel = (fuss_x, boden - 6 * s)
    # Unterschenkel kippt leicht nach vorn (Knie über die Zehen)
    us = math.radians(90 - 28 * t)
    kniepunkt = (knoechel[0] - unter * math.cos(us), knoechel[1] - unter * math.sin(us))
    # Oberschenkel: Winkel zum Unterschenkel
    os_winkel = us + math.pi - knie
    huefte = (kniepunkt[0] - ober * math.cos(os_winkel), kniepunkt[1] - ober * math.sin(os_winkel))
    schulter = (huefte[0] - rumpf * math.sin(neigung), huefte[1] - rumpf * math.cos(neigung))
    kopfmitte = (
        schulter[0] - (kopf * 1.6) * math.sin(neigung),
        schulter[1] - (kopf * 1.6) * math.cos(neigung),
    )
    # Arme nach vorn gestreckt, beim Absinken waagerecht
    arm = k * 0.22
    arm_winkel = math.radians(70 - 70 * t)  # vom Rumpf weg nach vorn
    hand = (
        schulter[0] - arm * math.cos(arm_winkel),
        schulter[1] + arm * math.sin(arm_winkel) * (1 - t) - arm * 0.02,
    )
    # Fuß und Boden
    d.line([(k * 0.12, boden), (k * 0.88, boden)], fill=(120, 140, 135, 255), width=5 * s)
    d.line(
        [(fuss_x - k * 0.11, knoechel[1] + 4 * s), (fuss_x + k * 0.05, knoechel[1] + 4 * s)],
        fill=farbe,
        width=strich,
    )
    for a, b in ((knoechel, kniepunkt), (kniepunkt, huefte), (huefte, schulter)):
        d.line([a, b], fill=farbe, width=strich)
    d.line([schulter, hand], fill=akzent, width=strich)
    for p in (knoechel, kniepunkt, huefte, schulter, hand):
        r = strich / 2
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=akzent if p is hand else farbe)
    r = kopf
    d.ellipse([kopfmitte[0] - r, kopfmitte[1] - r, kopfmitte[0] + r, kopfmitte[1] + r], fill=farbe)
    return bild.resize((KANTE, KANTE), Image.LANCZOS)


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    frames = [figur(i / (N - 1)) for i in range(N)]
    streifen = Image.new("RGBA", (KANTE * N, KANTE), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        streifen.paste(f, (i * KANTE, 0))
    streifen.save(ZIEL / "kniebeuge.png", optimize=True)
    # Pendel-GIF zum Anschauen (vor und zurück), 1,2 s je Richtung
    pendel = frames + frames[-2:0:-1]
    hell = [
        Image.alpha_composite(Image.new("RGBA", f.size, (242, 248, 246, 255)), f).convert(
            "P", palette=Image.ADAPTIVE
        )
        for f in pendel
    ]
    hell[0].save(
        ZIEL / "kniebeuge_vorschau.gif",
        save_all=True,
        append_images=hell[1:],
        duration=int(1200 / (N - 1)),
        loop=0,
        optimize=True,
    )
    print(
        ZIEL / "kniebeuge.png",
        (ZIEL / "kniebeuge.png").stat().st_size,
        "Bytes;",
        ZIEL / "kniebeuge_vorschau.gif",
    )


if __name__ == "__main__":
    sys.exit(main())
