"""Verlaufskurven unter der Hauptkurve — live und in der Aufzeichnung.

Die Ansicht (`core.hrv_ansicht.Ansicht`) sagt, welche Kurven zu sehen sind,
mit welchem Fenster und ob gleitend oder in Blöcken. Je Analysebereich (Zeit,
Frequenz, Nichtlinear) stehen nur dessen Chips und Kurven da. Antippen eines
Chips zeigt oder verbirgt eine Kurve; gleiche Achsen teilen sich ein Diagramm,
verschiedene stehen untereinander — alle mit derselben Zeitachse wie die
Hauptkurve, sodass ein Wischen alle zugleich verschiebt. Gerechnet wird nichts
hier: die Werte liefert der Aufrufer (`daten`), aus `hrv_core.trends`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.hrv_ansicht import BLOCK, GLEITEND, PNN_WAHL, Ansicht
from trainingsapp.hrv_core.trends import KENNZAHLEN, im_bereich, titel, treppe
from trainingsapp.ui.components.kurve import Reihe, kurve

#: Feste Farbe je Kurve — in Diagrammen, Legende, Chips und Kacheln dieselbe
FARBEN: dict[str, str] = {
    "hf_rr": ft.Colors.TERTIARY,
    "hf_geraet": ft.Colors.BLUE_GREY_300,
    "mean_rr": ft.Colors.CYAN_400,
    "rmssd": ft.Colors.AMBER_400,
    "sdnn": ft.Colors.PURPLE_300,
    "pnnx": ft.Colors.LIGHT_GREEN_400,
    "atemfrequenz": ft.Colors.BLUE_400,
    "vlf_power": ft.Colors.BLUE_GREY_400,
    "rsa": ft.Colors.LIGHT_BLUE_300,
    "lf_power": ft.Colors.ORANGE_400,
    "hf_power": ft.Colors.TEAL_400,
    "lf_hf": ft.Colors.PINK_300,
    "gipfel": ft.Colors.INDIGO_300,
    "sd1": ft.Colors.DEEP_ORANGE_300,
    "sd2": ft.Colors.BROWN_300,
    "dfa_alpha1": ft.Colors.LIME_600,
}

BEREICH_TITEL = {"zeit": "Zeit", "frequenz": "Frequenz", "nichtlinear": "Nichtlinear"}

#: (Kennzahl, Fenster, Block?) → Punkte
Daten = Callable[[str, int, bool], Sequence[tuple[float, float]]]


def _achse(kennzahl: str) -> str | None:
    k = KENNZAHLEN.get(kennzahl)
    return k.achse_schluessel if k else None


def fenster_text(sekunden: float) -> str:
    """„30 s", „2 min".

    >>> fenster_text(30), fenster_text(120), fenster_text(90)
    ('30 s', '2 min', '90 s')
    """
    s = int(sekunden)
    return f"{s // 60} min" if s >= 120 and s % 60 == 0 else f"{s} s"


def bezeichnung(kennzahl: str, ansicht: Ansicht) -> str:
    """„RMSSD 30 s" — mit Fenster, wo gerechnet wird; Blöcke „je 30 s".

    >>> bezeichnung("rmssd", Ansicht()), bezeichnung("hf_geraet", Ansicht())
    ('RMSSD 30 s', 'HF Gerät')
    >>> bezeichnung("pnnx", Ansicht(pnn_ms=20, modus={"pnnx": "block"}))
    'pNN20 je 30 s'
    """
    k = KENNZAHLEN[kennzahl]
    name = titel(kennzahl, ansicht.pnn_ms)
    if not k.rechnet:
        return name
    fenster = fenster_text(ansicht.fenster_fuer(kennzahl, k.fenster_s))
    return f"{name} je {fenster}" if ansicht.modus_fuer(kennzahl) == BLOCK else f"{name} {fenster}"


def schritt_min(kennzahlen: Sequence[str]) -> float:
    """Feinster Achsenschritt: Kennzahlen um 1 (DFA α1, LF/HF) brauchen Zehntel."""
    return 0.01 if min(KENNZAHLEN[k].spanne_min for k in kennzahlen) < 4 else 1.0


def diagramme(
    ansicht: Ansicht,
    daten: Daten,
    *,
    x_von: float,
    x_bis: float,
    hoehe: int = 120,
    ohne: Sequence[str] = (),
    bereich: str | None = None,
) -> list[ft.Control]:
    """Je Gruppe gleicher Achse ein Diagramm, darüber die Legende.

    ``ohne``: Kurven, die es für diese Messung nicht gibt (z. B. ``hf_rr`` bei
    einem reinen Pulsgeber) — sie bleiben gewählt, werden aber nicht gezeichnet.
    ``bereich``: nur die Kurven dieses Analysebereichs.
    """
    nur = [k for k in (im_bereich(bereich) if bereich else KENNZAHLEN) if k not in ohne]
    out: list[ft.Control] = []
    for gruppe in ansicht.gruppen(_achse, nur=nur):
        reihen = []
        legende: list[ft.Control] = []
        for k in gruppe:
            kz = KENNZAHLEN[k]
            fenster = ansicht.fenster_fuer(k, kz.fenster_s)
            block = kz.rechnet and ansicht.modus_fuer(k) == BLOCK
            punkte = list(daten(k, fenster, block))
            naehte: list[int] = []
            if block:
                punkte, naehte = treppe(punkte, fenster, x_von, x_bis)
            reihen.append(Reihe(punkte, farbe=FARBEN[k], naehte=naehte))
            legende.append(_legende(bezeichnung(k, ansicht), FARBEN[k]))
        out.append(ft.Row(spacing=14, run_spacing=4, wrap=True, controls=legende))
        out.append(
            kurve(
                reihen,
                einheit=KENNZAHLEN[gruppe[0]].einheit or KENNZAHLEN[gruppe[0]].titel,
                hoehe=hoehe,
                x_von=x_von,
                x_bis=x_bis,
                y_spanne_min=max(KENNZAHLEN[k].spanne_min for k in gruppe),
                y_schritt_min=schritt_min(gruppe),
            )
        )
    return out


def _legende(text: str, farbe: str) -> ft.Control:
    return ft.Row(
        spacing=5,
        tight=True,
        controls=[
            ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe),
            ft.Text(text, size=11, opacity=0.85),
        ],
    )


def chips(
    ansicht: Ansicht,
    umschalten: Callable[[str], None],
    bereich: str = "zeit",
    ohne: Sequence[str] = (),
) -> ft.Control:
    """Ein Chip je Kurve des Bereichs, mit Farbpunkt; gewählte sind getönt."""

    def handler(k: str) -> Callable[[], None]:
        return lambda: umschalten(k)

    return ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=8,
        controls=[
            ft.Chip(
                label=ft.Text(titel(k, ansicht.pnn_ms), size=12),
                leading=ft.Container(width=10, height=10, border_radius=5, bgcolor=FARBEN[k]),
                selected=k in ansicht.kurven,
                on_select=handler(k),
                show_checkmark=False,
                selected_color=ft.Colors.with_opacity(0.22, FARBEN[k]),
                visual_density=ft.VisualDensity.COMPACT,
            )
            for k in im_bereich(bereich)
            if k not in ohne
        ],
    )


def bereich_wahl(
    bereiche: Sequence[str], aktiv: str, wechseln: Callable[[str], None]
) -> ft.Control:
    """Zeit | Frequenz | Nichtlinear — nur die angebotenen."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            wechseln(str(e.control.selected[0]))

    return ft.SegmentedButton(
        selected=[aktiv if aktiv in bereiche else bereiche[0]],
        show_selected_icon=False,
        segments=[ft.Segment(value=b, label=ft.Text(BEREICH_TITEL[b])) for b in bereiche],
        on_change=gewaehlt,
    )


def ansicht_menue(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.Control:
    """Menü „Ansichten": Fenster und Darstellung, speichern, laden, löschen, zurücksetzen.

    ``state`` ist der `AppState` (Speicherort: ``app_setting``); ``geaendert``
    baut die Kurven neu.
    """
    aktuell = state.ansicht()
    gespeichert = state.ansichten()

    def laden(a: Ansicht) -> Callable[[], None]:
        def handler() -> None:
            a.bereich = state.ansicht().bereich  # der Bereich bleibt, wo man ist
            state.ansicht_setzen(a)
            geaendert()

        return handler

    def zuruecksetzen() -> None:
        state.ansicht_setzen(Ansicht(bereich=state.ansicht().bereich))
        geaendert()

    def loeschen() -> None:
        state.ansicht_loeschen(aktuell.name)
        page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht „{aktuell.name}“ gelöscht.")))
        geaendert()

    eintraege: list[ft.PopupMenuItem] = [
        ft.PopupMenuItem(
            content="Fenster & Darstellung …",
            icon=ft.Icons.TUNE,
            on_click=lambda: page.show_dialog(darstellung_blatt(page, state, geaendert)),
        ),
        ft.PopupMenuItem(
            content="Als Ansicht speichern …",
            icon=ft.Icons.SAVE_OUTLINED,
            on_click=lambda: page.show_dialog(speichern_dialog(page, state, geaendert)),
        ),
    ]
    if gespeichert:
        eintraege.append(ft.PopupMenuItem())  # Trennlinie
        eintraege += [
            ft.PopupMenuItem(
                content=a.name,
                checked=a.name == aktuell.name,
                on_click=laden(a),
            )
            for a in gespeichert
        ]
    eintraege.append(ft.PopupMenuItem())
    if any(a.name == aktuell.name for a in gespeichert):
        eintraege.append(
            ft.PopupMenuItem(
                content=f"„{aktuell.name}“ löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=loeschen
            )
        )
    eintraege.append(
        ft.PopupMenuItem(
            content="Kurven auf Standard zurücksetzen",
            icon=ft.Icons.RESTART_ALT,
            on_click=zuruecksetzen,
        )
    )
    return ft.PopupMenuButton(
        icon=ft.Icons.DASHBOARD_CUSTOMIZE_OUTLINED,
        tooltip=f"Ansicht: {aktuell.name}",
        items=eintraege,
    )


def darstellung_blatt(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.BottomSheet:
    """Je gewählter Kurve des Bereichs: Fenster, gleitend oder Blöcke; pNNx-Schwelle.

    Ein Blatt von unten, kein Dialog: Ein ``AlertDialog`` misst seinen Inhalt
    vorab (intrinsische Größe), und das können Auswahllisten (``Dropdown``) nicht
    — der Dialog blieb unsichtbar, nur der Bildschirm wurde dunkel (14.10.).
    """
    ansicht = state.ansicht()
    gewaehlt = [
        k for k in im_bereich(ansicht.bereich) if k in ansicht.kurven and KENNZAHLEN[k].rechnet
    ]

    def speichern() -> None:
        state.ansicht_setzen(ansicht)
        geaendert()

    def fenster_setzen(k: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(e: ft.Event[ft.Dropdown]) -> None:
            with contextlib.suppress(TypeError, ValueError):
                ansicht.fenster[k] = int(e.control.value or 0)
                speichern()

        return handler

    def modus_setzen(k: str) -> Callable[[ft.Event[ft.SegmentedButton]], None]:
        def handler(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                if e.control.selected[0] == BLOCK:
                    ansicht.modus[k] = BLOCK
                else:
                    ansicht.modus.pop(k, None)
                speichern()

        return handler

    def pnn_setzen(e: ft.Event[ft.Dropdown]) -> None:
        with contextlib.suppress(TypeError, ValueError):
            ansicht.pnn_ms = int(e.control.value or 50)
            speichern()

    def gemeinsam(e: ft.Event[ft.Switch]) -> None:
        ansicht.gemeinsam = bool(e.control.value)
        speichern()

    zeilen: list[ft.Control] = []
    for k in gewaehlt:
        kz = KENNZAHLEN[k]
        zeilen.append(
            ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Container(width=10, height=10, border_radius=5, bgcolor=FARBEN[k]),
                            ft.Text(titel(k, ansicht.pnn_ms), weight=ft.FontWeight.W_600),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        run_spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Dropdown(
                                value=str(ansicht.fenster_fuer(k, kz.fenster_s)),
                                options=[
                                    ft.DropdownOption(key=str(s), text=fenster_text(s))
                                    for s in kz.fenster_wahl
                                ],
                                on_select=fenster_setzen(k),
                                dense=True,
                                width=110,
                            ),
                            ft.SegmentedButton(
                                selected=[ansicht.modus_fuer(k)],
                                show_selected_icon=False,
                                segments=[
                                    ft.Segment(value=GLEITEND, label=ft.Text("gleitend")),
                                    ft.Segment(value=BLOCK, label=ft.Text("Blöcke")),
                                ],
                                on_change=modus_setzen(k),
                            ),
                        ],
                    ),
                ],
            )
        )
    if "pnnx" in gewaehlt:
        zeilen.append(
            ft.Dropdown(
                label="Schwelle für pNNx",
                value=str(ansicht.pnn_ms),
                options=[ft.DropdownOption(key=str(x), text=f"{x} ms") for x in PNN_WAHL],
                on_select=pnn_setzen,
                dense=True,
            )
        )
    if not zeilen:
        zeilen.append(ft.Text("Keine gewählte Kurve hat ein Fenster.", size=12, opacity=0.7))
    zeilen += [
        ft.Switch(
            label="Gleiche Achse in einem Diagramm", value=ansicht.gemeinsam, on_change=gemeinsam
        ),
        ft.Text(
            "Gleitend: Je länger das Fenster, desto ruhiger die Kurve und desto "
            "später zeigt sie eine Änderung. Blöcke: ein Wert je Fenster, ohne "
            "Überlappung — gut zum Vergleichen von Abschnitten.",
            size=11,
            opacity=0.65,
        ),
    ]
    kopf = ft.Row(
        controls=[
            ft.Text("Fenster & Darstellung", size=18, weight=ft.FontWeight.W_600, expand=True),
            ft.TextButton("Fertig", on_click=lambda: page.pop_dialog()),
        ]
    )
    return ft.BottomSheet(
        content=ft.Container(
            padding=ft.Padding.only(left=16, top=4, right=16, bottom=16),
            content=ft.Column(
                spacing=16, tight=True, scroll=ft.ScrollMode.AUTO, controls=[kopf, *zeilen]
            ),
        ),
        scrollable=True,
        show_drag_handle=True,
    )


def speichern_dialog(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.AlertDialog:
    """Die aktuelle Ansicht unter einem Namen ablegen — gleicher Name ersetzt."""
    ansicht = state.ansicht()
    name = ft.TextField(
        label="Name",
        value="" if ansicht.name == "Standard" else ansicht.name,
        hint_text="z. B. Atemübung, Ruhe morgens",
        autofocus=True,
    )

    def speichern() -> None:
        text = (name.value or "").strip()
        if not text:
            return
        ansicht.name = text
        state.ansicht_speichern(ansicht)
        state.ansicht_setzen(ansicht)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht „{text}“ gespeichert.")))
        geaendert()

    return ft.AlertDialog(
        title=ft.Text("Ansicht speichern"),
        content=name,
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
            ft.FilledButton("Speichern", on_click=speichern),
        ],
    )


__all__ = [
    "BEREICH_TITEL",
    "FARBEN",
    "ansicht_menue",
    "bereich_wahl",
    "bezeichnung",
    "chips",
    "darstellung_blatt",
    "diagramme",
    "fenster_text",
    "speichern_dialog",
]
