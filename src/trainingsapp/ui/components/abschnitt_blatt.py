"""Das Blatt „Abschnitt“: Name und **zwei Zeiten** eintippen (Ben, 12.11.2026).

„Das Edit der Abschnitte muss schnell nachträglich möglich sein. Auch die Erstellung eines
Abschnittes mit zwei Zeiten, um z. B. Belastungen, die im Kalender rückverfolgbar sind.“ —
ein Blatt für live und Aufzeichnung: Name, Von und Bis, Schritte ±10 s / ±1 min, Kopf und
Endteil, Löschen. **Je Feld eine Schreibweise** (Ben, 19.11.2026): „Von“ als Uhrzeit („14:05“)
oder Dauer der Messung („12:30“) — der Knopf daneben schaltet um; „Bis“ dazu als **Länge** des
Abschnitts ab „Von“ („30:00“, `core.zeitangabe.LAENGE`) — Uhrzeit · Messdauer · Länge darunter.
Mit „Länge“ rückt das Ende mit, wenn sich „Von“ ändert. Was es speichert, sind die
Grenz-Notizen „‹Name›: Start“ / „‹Name›: Ende“ (`core.abschnitte`) — das Blatt rechnet
nichts, der Aufrufer bekommt Name, Grenzen und Ränder.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft
from hrv_core.ausschnitte import MIN_ABSCHNITT_S
from hrv_core.ereignisse import Zeitbezug

from trainingsapp.core.zeitangabe import (
    DAUER,
    LAENGE,
    UHR,
    bis_lesen,
    bis_text,
    dauer_text,
    stelle_lesen,
    stelle_text,
)
from trainingsapp.ui.components.abschnitte import rand_zeile
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.namenwahl import Namenwahl

#: Schritte an Von und Bis (Sekunden)
SCHRITTE_S: tuple[int, ...] = (-60, -10, 10, 60)
#: Was „Bis“ in der jeweiligen Schreibweise erwartet — der Hinweis bei Unlesbarem
BIS_BEISPIEL = {UHR: "z. B. 14:35", DAUER: "z. B. 42:30", LAENGE: "Länge, z. B. 30:00"}


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
    wahl: Namenwahl | None = None,
    sichern: Callable[[str, float, float | None, float, float], Any],
    loeschen: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt; ``sichern(name, von, bis, kopf_s, endteil_s)`` und ``loeschen()`` laufen,
    wenn es zu ist. Zeiten auf der Kurvenachse des Aufrufers; ``grenzen`` liefert Anfang
    und Ende der Messung (live: bis jetzt). ``bis=None``: Der Abschnitt läuft noch (live) —
    bleibt „Bis“ leer, läuft er weiter. ``uhr``: mit Uhrzeiten beginnen. ``wahl``: das
    Namensfeld mit den gemerkten Abschnittsnamen (`components.namenwahl`, Ben 19.11.2026 —
    wie die Überschrift im Titel-Blatt); ohne eins ein Feld ohne Liste. Leer gilt ``name``."""
    zb = zeitbezug
    laeuft = bis is None
    beginn = UHR if uhr and zb.start_utc is not None else DAUER
    stand: dict[str, Any] = {
        "von": float(von),
        "bis": None if bis is None else float(bis),
        "kopf": float(kopf_s),
        "endteil": float(endteil_s),
        # Je Feld eine Schreibweise (Ben, 19.11.2026): „Von“ Uhrzeit oder Dauer der Messung,
        # „Bis“ dazu die Länge des Abschnitts
        "modus_von": beginn,
        "modus_bis": beginn,
    }
    nachher = Nachher()
    blatt: ft.BottomSheet
    name_feld: ft.TextField
    von_feld: ft.TextField
    bis_feld: ft.TextField
    von_knopf: ft.TextButton
    dauer: ft.Text

    def text_von(x: float) -> str:
        return stelle_text(zb, x, live=live, modus=stand["modus_von"])

    def text_bis() -> str:
        return bis_text(zb, stand["von"], stand["bis"], live=live, modus=stand["modus_bis"])

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
            dauer.value = problem or f"Länge {dauer_text(b - v)}"
        dauer.color = ft.Colors.ERROR if problem else None

    def zeigen() -> None:
        von_feld.value, bis_feld.value = text_von(stand["von"]), text_bis()
        von_feld.error = bis_feld.error = None
        dauer_zeigen()
        auffrischen(von_feld, bis_feld, dauer)

    def von_setzen(x: float) -> None:
        """Mit „Länge“ rückt das Ende mit dem Anfang — die Länge bleibt, wie sie dasteht."""
        if stand["modus_bis"] == LAENGE and stand["bis"] is not None:
            stand["bis"] += x - stand["von"]
        stand["von"] = x

    def lesen_von() -> bool:
        """„Von“ in den Stand übernehmen — ``False``, wenn es sich nicht lesen lässt."""
        roh = (von_feld.value or "").strip()
        if roh == text_von(stand["von"]):
            return True
        x = stelle_lesen(zb, roh, live=live, modus=stand["modus_von"])
        if x is None:
            von_feld.error = "z. B. 14:05" if stand["modus_von"] == UHR else "z. B. 12:30"
            auffrischen(von_feld)
            return False
        von_setzen(x)
        return True

    def lesen_bis() -> bool:
        """„Bis“ in den Stand übernehmen — als Stelle oder als Länge ab „Von“."""
        roh = (bis_feld.value or "").strip()
        if not roh and laeuft:
            stand["bis"] = None
            bis_feld.error = None
            return True
        if roh == text_bis():
            return True
        x = bis_lesen(zb, roh, stand["von"], live=live, modus=stand["modus_bis"])
        if x is None:
            bis_feld.error = BIS_BEISPIEL[stand["modus_bis"]]
            auffrischen(bis_feld)
            return False
        stand["bis"] = x
        return True

    def lesen() -> bool:
        return lesen_von() and lesen_bis()  # erst „Von“ — eine Länge rechnet ab ihm

    def getippt(lesen_: Callable[[], bool]) -> None:
        if lesen_():
            zeigen()

    def schritt(schluessel: str, delta: int) -> Callable[[], None]:
        def handler() -> None:
            if not lesen():
                return
            lo, hi = grenzen()
            if schluessel == "von":
                von_setzen(min(max(stand["von"] + delta, lo), hi))
            else:
                basis = stand["bis"] if stand["bis"] is not None else hi
                stand["bis"] = min(max(basis + delta, lo), hi)
            zeigen()

        return handler

    def jetzt() -> None:
        stand["bis"] = grenzen()[1]
        zeigen()

    def von_knopf_zeigen() -> None:
        uhrzeit = stand["modus_von"] == UHR
        von_knopf.content = "Messdauer" if uhrzeit else "Uhrzeit"
        von_knopf.tooltip = "Als Dauer der Messung eingeben" if uhrzeit else "Als Uhrzeit eingeben"
        auffrischen(von_knopf)

    def von_umschalten() -> None:
        """Der Knopf neben „Von“: Uhrzeit ⇄ Dauer der Messung — erst in der alten lesen."""
        if not lesen_von():
            return
        stand["modus_von"] = DAUER if stand["modus_von"] == UHR else UHR
        von_knopf_zeigen()
        zeigen()

    def bis_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        """Uhrzeit · Messdauer · Länge für „Bis“ — erst in der alten Schreibweise lesen."""
        if not e.control.selected:
            return
        ok = lesen()
        stand["modus_bis"] = e.control.selected[0]
        if ok:
            zeigen()

    def fertig() -> None:
        if not lesen():
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
        von_, bis_ = stand["von"] - stand["kopf"], stand["bis"] + stand["endteil"]
        return f"rechnet {text_von(von_)}–{text_von(bis_)}"

    if wahl is None:
        wahl = Namenwahl(wert=name)
    name_feld = wahl.feld
    von_feld = ft.TextField(
        label="Von",
        dense=True,
        expand=True,
        keyboard_type=ft.KeyboardType.TEXT,
        on_blur=lambda _: getippt(lesen_von),
        on_submit=lambda _: getippt(lesen_von),
    )
    bis_feld = ft.TextField(
        label="Bis",
        dense=True,
        expand=True,
        hint_text="läuft noch" if laeuft else None,
        keyboard_type=ft.KeyboardType.TEXT,
        on_blur=lambda _: getippt(lesen),
        on_submit=lambda _: fertig(),
    )
    von_knopf = ft.TextButton(
        icon=ft.Icons.SWAP_HORIZ,
        on_click=lambda _e=None: von_umschalten(),
        visible=zb.start_utc is not None,
        data="von_schreibweise",
    )
    von_knopf_zeigen()
    dauer = ft.Text(size=13, opacity=0.8)
    von_feld.value, bis_feld.value = text_von(stand["von"]), text_bis()
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

    bis_wahl = ft.SegmentedButton(
        selected=[stand["modus_bis"]],
        show_selected_icon=False,
        segments=[
            *([ft.Segment(value=UHR, label=ft.Text("Uhrzeit"))] if zb.start_utc else []),
            ft.Segment(value=DAUER, label=ft.Text("Messdauer")),
            ft.Segment(value=LAENGE, label=ft.Text("Länge")),
        ],
        on_change=bis_gewaehlt,
        data="bis_schreibweise",
    )
    bis_zeile: list[ft.Control] = [bis_feld]
    if live:
        bis_zeile.append(ft.TextButton("Jetzt", on_click=jetzt))
    inhalt: list[ft.Control] = [
        ft.Text("Neuer Abschnitt" if neu else "Abschnitt", size=20, weight=ft.FontWeight.W_500),
        wahl.control,
        ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[von_feld, von_knopf]),
        schritte("von"),
        ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=bis_zeile),
        bis_wahl,
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
            "Die Grenzen stehen als Notizen „Name: Start“ und „Name: Ende“ in der Notizliste, "
            "Kopf und Endteil in ihrem Text — wer dort so eine Notiz tippt oder verschiebt, "
            "ändert den Abschnitt. „Name: Marker“ dazwischen teilt ihn.",
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


__all__ = ["BIS_BEISPIEL", "SCHRITTE_S", "abschnitt_blatt", "grenzen_pruefen", "schritt_text"]
