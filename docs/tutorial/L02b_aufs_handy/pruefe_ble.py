"""L02b — prüft, was auf diesem Gerät tatsächlich verfügbar ist.

Läuft auf zwei Wegen:

    python docs/tutorial/L02b_aufs_handy/pruefe_ble.py     (Terminal)
    flet run docs/tutorial/L02b_aufs_handy/pruefe_ble.py   (Fenster)

Für den Test auf dem Handy vorübergehend als src/trainingsapp/ui/app.py
einsetzen, `flet build apk` und installieren.

Die Frage, um die es geht: Kommt Python auf diesem Gerät an einen
Bluetooth-Sensor? Auf dem Desktop lautet die Antwort ja. Auf Android und iOS
erwarten wir ein Nein — und wollen wissen, *wie* genau es scheitert.
"""

from __future__ import annotations

import asyncio
import platform
import sys


async def pruefe() -> list[tuple[str, bool, str]]:
    """Liefert eine Liste aus (Prüfung, bestanden, Details)."""
    ergebnis: list[tuple[str, bool, str]] = []

    ergebnis.append(("Python", True, f"{sys.version.split()[0]} auf {platform.system()}"))

    # -- numpy: die einzige binäre Abhängigkeit, die wir brauchen ------------
    try:
        import numpy as np

        probe = float(np.std([800.0, 810.0, 790.0], ddof=0))
        ergebnis.append(("numpy", True, f"{np.__version__}, Rechenprobe {probe:.2f}"))
    except Exception as e:
        ergebnis.append(("numpy", False, f"{type(e).__name__}: {e}"))

    # -- scipy: erwartet FEHLEND. Deshalb rechnet hrv_core alles selbst. -----
    try:
        import scipy  # noqa: F401

        ergebnis.append(("scipy", True, "vorhanden — auf Mobilgeräten überraschend, bitte melden"))
    except ImportError:
        ergebnis.append(("scipy", False, "fehlt (erwartet) — hrv_core kommt ohne aus"))

    # -- unsere eigene Domäne ------------------------------------------------
    try:
        from trainingsapp.hrv_core import compute_time_domain

        werte = compute_time_domain([800, 812, 795, 820, 788])
        assert werte is not None
        ergebnis.append(("hrv_core", True, f"RMSSD {werte['rmssd']:.1f} ms"))
    except Exception as e:
        ergebnis.append(("hrv_core", False, f"{type(e).__name__}: {e}"))

    # -- der eigentliche Test ------------------------------------------------
    try:
        from bleak import BleakScanner
    except Exception as e:
        ergebnis.append(
            (
                "bleak (Import)",
                False,
                f"{type(e).__name__}: {e}  →  eigene Flet-Extension nötig",
            )
        )
        return ergebnis

    ergebnis.append(("bleak (Import)", True, "Bibliothek geladen"))

    try:
        geraete = await BleakScanner.discover(timeout=6.0)
        namen = [f"{d.name or '(namenlos)'} [{d.address}]" for d in geraete[:8]]
        ergebnis.append(
            (
                "BLE-Scan",
                True,
                f"{len(geraete)} Geräte gefunden"
                + (":\n    " + "\n    ".join(namen) if namen else ""),
            )
        )
    except Exception as e:
        ergebnis.append(("BLE-Scan", False, f"{type(e).__name__}: {e}"))

    return ergebnis


# ---------------------------------------------------------------------------
# Ausgabe im Terminal
# ---------------------------------------------------------------------------


def main_terminal() -> None:
    print("Prüfung der Laufzeitumgebung")
    print("=" * 60)
    for name, ok, details in asyncio.run(pruefe()):
        print(f"  {'✓' if ok else '✗'}  {name:16} {details}")
    print()
    print("Halte diese Ausgabe fest — sie entscheidet über den weiteren Aufbau")
    print("der Sensoranbindung (siehe docs/architektur.md).")


# ---------------------------------------------------------------------------
# Ausgabe als Flet-Fenster (auch auf dem Handy)
# ---------------------------------------------------------------------------


def main(page) -> None:  # type: ignore[no-untyped-def]
    import flet as ft

    page.title = "Umgebungsprüfung"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    liste = ft.Column(spacing=8)
    page.add(
        ft.Column(
            controls=[
                ft.Text("Was kann dieses Gerät?", size=22, weight=ft.FontWeight.BOLD),
                ft.Text("Prüfung läuft …", opacity=0.6),
                ft.Divider(),
                liste,
            ]
        )
    )

    async def laufen() -> None:
        for name, ok, details in await pruefe():
            liste.controls.append(
                ft.Container(
                    padding=10,
                    border_radius=8,
                    bgcolor=(ft.Colors.SECONDARY_CONTAINER if ok else ft.Colors.ERROR_CONTAINER),
                    content=ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL,
                                        size=18,
                                    ),
                                    ft.Text(name, weight=ft.FontWeight.BOLD),
                                ],
                            ),
                            ft.Text(details, size=12, selectable=True),
                        ],
                    ),
                )
            )
            page.update()

    page.run_task(laufen)


if __name__ == "__main__":
    main_terminal()
