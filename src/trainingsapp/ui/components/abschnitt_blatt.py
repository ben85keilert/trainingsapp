"""Das Blatt „Abschnitt“: Name und **zwei Zeiten** eintippen (Ben, 12.11.2026).

„Das Edit der Abschnitte muss schnell nachträglich möglich sein. Auch die Erstellung eines
Abschnittes mit zwei Zeiten, um z. B. Belastungen, die im Kalender rückverfolgbar sind.“ —
ein Blatt für live und Aufzeichnung: Name, Von und Bis als Dauer („12:30“) oder Uhrzeit
(„14:05“), Schritte ±10 s / ±1 min, Kopf und Endteil, Löschen. Was es speichert, sind die
Grenz-Notizen „‹Name›: Start“ / „‹Name›: Ende“ (`core.abschnitte`) — das Blatt rechnet
nichts, der Aufrufer bekommt Name, Grenzen und Ränder.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core.ausschnitte import MIN_ABSCHNITT_S
from hrv_core.ereignisse import Zeitbezug

from trainingsapp.core.zeitangabe import DAUER, UHR, dauer_text, stelle_lesen, stelle_text
from trainingsapp.ui.components.abschnitte import rand_zeile
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Schritte an Von und Bis (Sekunden)
SCHRITTE_S: tuple[int, ...] = (-60, -10, 10, 60)


def schritt_text(sekunden: int) -> str:
    """Beschriftung eines Schrittknopfs.

    >>> [schritt_text(s) for s in SCHRITTE_S]
    ['−1 min', '−10 s', '+10 s', '+1 min']
    """
    betrag = abs(sekunden)
    wert = f"{betrag // 60} min" if betrag % 60 == 0 else f"{betrag} s"
    return ("−" if sekunden < 0 else "+") + wert


def grenzen_pruefen(von: float, bis: float | None, lo: float, hi: float) -> str | None:
    """Warum sich der Bereich nicht speichern lässt — ``None``, wenn er passt.
    ``bis=None``: der Abschnitt läuft noch.

    >>> grenzen_pruefen(60, 600, 0, 900) is None, grenzen_pruefen(60, None, 0, 900) is None
    (True, True)
    >>> grenzen_pruefen(600, 60, 0, 900), grenzen_pruefen(60, 65, 0, 900)
    ('Das Ende liegt vor dem Anfang.', 'Ein Abschnitt braucht mindestens 10 s.')
    >>> grenzen_pruefen(-5, 60, 0, 900), grenzen_pruefen(60, 1000, 0, 900)
    ('Der Anfang liegt vor der Messung.', 'Das Ende liegt hinter der Messung.')
    """
    if von < lo - 0.5:
        return "Der Anfang liegt vor der Messung."
    if von > hi + 0.5:
        return "Der Anfang liegt hinter der Messung."
    if bis is None:
        return None
    if bis > hi + 0.5:
        return "Das Ende liegt hinter der Messung."
    if bis <= von:
        return "Das Ende liegt vor dem Anfang."
    if bis - von < MIN_ABSCHNITT_S:
        return f"Ein Abschnitt braucht mindestens {MIN_ABSCHNITT_S:g} s."
    return None


def abschnitt_blatt(
    page: Any,
    *,
    zeitbezug: Zeitbezug,
    live: bool,
    grenzen: Callable[[], tuple[float, float]],
    name: str,
    von: float,
    bis: float | None,
    kopf_s: float = 0.0,
    endteil_s: float = 0.0,
    neu: bool,
    uhr: bool,
    vorschlaege: Sequence[str] = (),
    sichern: Callable[[str, float, float | None, float, float], Any],
    loeschen: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt; ``sichern(name, von, bis, kopf_s, endteil_s)`` und ``loeschen()`` laufen,
    wenn es zu ist. Zeiten auf der Kurvenachse des Aufrufers; ``grenzen`` liefert Anfang
    und Ende der Messung (live: bis jetzt). ``bis=None``: Der Abschnitt läuft noch (live) —
    bleibt „Bis“ leer, läuft er weiter. ``uhr``: mit Uhrzeiten beginnen."""
    zb = zeitbezug
    laeuft = bis is None
    stand: dict[str, Any] = {
        "von": float(von),
        "bis": None if bis is None else float(bis),
        "kopf": float(kopf_s),
        "endteil": float(endteil_s),
        "modus": UHR if uhr and zb.start_utc is not None else DAUER,
    }
    nachher = Nachher()
    blatt: ft.BottomSheet
    name_feld: ft.TextField
    von_feld: ft.TextField
    bis_feld: ft.TextField
    dauer: ft.Text

    def text(x: float | None) -> str:
        return "" if x is None else stelle_text(zb, x, live=live, modus=stand["modus"])

    def auffrischen(*controls: ft.Control) -> None:
        for c in controls:
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                c.update()

    def dauer_zeigen() -> None:
        v, b = stand["von"], stand["bis"]
        problem = None
        if b is None:
            dauer.value = "läuft noch — „Bis“ leer lassen oder das Ende eintragen"
        else:
            problem = grenzen_pruefen(v, b, *grenzen())
            dauer.value = problem or f"Dauer {dauer_text(b - v)}"
        dauer.color = ft.Colors.ERROR if problem else None

    def zeigen() -> None:
        von_feld.value, bis_feld.value = text(stand["von"]), text(stand["bis"])
        von_feld.error = bis_feld.error = None
        dauer_zeigen()
        auffrischen(von_feld, bis_feld, dauer)

    def lesen(feld: ft.TextField, schluessel: str) -> bool:
        """Das Feld in den Stand übernehmen — ``False``, wenn es sich nicht lesen lässt."""
        roh = (feld.value or "").strip()
        if not roh and schluessel == "bis" and laeuft:
            stand["bis"] = None
            feld.error = None
            return True
        if roh == text(stand[schluessel]):
            return True
        x = stelle_lesen(zb, roh, live=live, modus=stand["modus"])
        if x is None:
            feld.error = "z. B. 14:05" if stand["modus"] == UHR else "z. B. 12:30"
            auffrischen(feld)
            return False
        stand[schluessel] = x
        return True

    def getippt(feld: ft.TextField, schluessel: str) -> None:
        if lesen(feld, schluessel):
            zeigen()

    def schritt(schluessel: str, delta: int) -> Callable[[], None]:
        def handler() -> None:
            feld = von_feld if schluessel == "von" else bis_feld
            if not lesen(feld, schluessel):
                return
            lo, hi = grenzen()
            basis = stand[schluessel] if stand[schluessel] is not None else hi
            stand[schluessel] = min(max(basis + delta, lo), hi)
            zeigen()

        return handler

    def jetzt() -> None:
        stand["bis"] = grenzen()[1]
        zeigen()

    def modus_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        ok = lesen(von_feld, "von") and lesen(bis_feld, "bis")  # erst im alten Modus lesen
        stand["modus"] = e.control.selected[0]
        if ok:
            zeigen()

    def waehlen(vorschlag: str) -> Callable[[], None]:
        def handler() -> None:
            name_feld.value = vorschlag
            auffrischen(name_feld)

        return handler

    def fertig() -> None:
        if not (lesen(von_feld, "von") and lesen(bis_feld, "bis")):
            return
        problem = grenzen_pruefen(stand["von"], stand["bis"], *grenzen())
        if problem is not None:
            zeigen()
            return
        titel_ = (name_feld.value or "").strip() or name
        werte = (titel_, stand["von"], stand["bis"], stand["kopf"], stand["endteil"])
        nachher.danach(lambda: sichern(*werte))
        schliessen(blatt)

    def weg() -> None:
        if loeschen is not None:
            nachher.danach(loeschen)
        schliessen(blatt)

    def bereich_text() -> str:
        if stand["bis"] is None:
            return "rechnet mit"
        return (
            f"rechnet {text(stand['von'] - stand['kopf'])}–{text(stand['bis'] + stand['endteil'])}"
        )

    name_feld = ft.TextField(
        label="Name",
        value=name,
        dense=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    von_feld = ft.TextField(
        label="Von",
        dense=True,
        expand=True,
        keyboard_type=ft.KeyboardType.TEXT,
        on_blur=lambda _: getippt(von_feld, "von"),
        on_submit=lambda _: getippt(von_feld, "von"),
    )
    bis_feld = ft.TextField(
        label="Bis",
        dense=True,
        expand=True,
        hint_text="läuft noch" if laeuft else None,
        keyboard_type=ft.KeyboardType.TEXT,
        on_blur=lambda _: getippt(bis_feld, "bis"),
        on_submit=lambda _: fertig(),
    )
    dauer = ft.Text(size=13, opacity=0.8)
    von_feld.value, bis_feld.value = text(stand["von"]), text(stand["bis"])
    dauer_zeigen()

    def schritte(schluessel: str) -> ft.Control:
        return ft.Row(
            spacing=4,
            controls=[
                ft.OutlinedButton(
                    schritt_text(s),
                    on_click=schritt(schluessel, s),
                    style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)),
                )
                for s in SCHRITTE_S
            ],
        )

    inhalt: list[ft.Control] = [
        ft.Text("Neuer Abschnitt" if neu else "Abschnitt", size=20, weight=ft.FontWeight.W_500),
        name_feld,
    ]
    knoepfe: list[ft.Control] = [
        ft.OutlinedButton(n, on_click=waehlen(n))
        for n in dict.fromkeys(v for v in vorschlaege if v.strip())
    ]
    if knoepfe:
        inhalt.append(ft.Row(wrap=True, spacing=6, run_spacing=6, controls=knoepfe))
    if zb.start_utc is not None:
        inhalt.append(
            ft.SegmentedButton(
                selected=[stand["modus"]],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value=UHR, label=ft.Text("Uhrzeit")),
                    ft.Segment(value=DAUER, label=ft.Text("Dauer")),
                ],
                on_change=modus_gewaehlt,
            )
        )
    bis_zeile: list[ft.Control] = [bis_feld]
    if live:
        bis_zeile.append(ft.TextButton("Jetzt", on_click=jetzt))
    inhalt += [
        ft.Row(controls=[von_feld]),
        schritte("von"),
        ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=bis_zeile),
        schritte("bis"),
        dauer,
        rand_zeile(
            page,
            kopf=lambda: stand["kopf"],
            endteil=lambda: stand["endteil"],
            kopf_setzen=lambda s: stand.__setitem__("kopf", s),
            endteil_setzen=lambda s: stand.__setitem__("endteil", s),
            bereich_text=bereich_text,
        ),
        ft.Text(
            "Die Grenzen stehen als Notizen „Name: Start“ und „Name: Ende“ in der Notizliste — "
            "wer dort so eine Notiz tippt oder verschiebt, ändert den Abschnitt.",
            size=12,
            opacity=0.7,
        ),
    ]
    fuss: list[ft.Control] = []
    if loeschen is not None:
        fuss.append(ft.TextButton("Löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=weg))
    fuss += [
        ft.Container(expand=True),
        ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
        ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=fertig),
    ]
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(inhalt, [ft.Row(controls=fuss)]),
    )
    return blatt


__all__ = ["SCHRITTE_S", "abschnitt_blatt", "grenzen_pruefen", "schritt_text"]
