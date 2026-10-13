"""Verlaufskurven unter dem RR-Tachogramm — live und in der Aufzeichnung.

Die Ansicht (`core.hrv_ansicht.Ansicht`) sagt, welche Kurven zu sehen sind.
Antippen eines Chips zeigt oder verbirgt eine Kurve; gleiche Einheiten teilen
sich ein Diagramm, verschiedene stehen untereinander — alle mit derselben
Zeitachse wie das Tachogramm, sodass ein Wischen alle zugleich verschiebt.
Gerechnet wird nichts hier: die Werte liefert der Aufrufer (`daten`), aus
`hrv_core.trends`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.hrv_ansicht import MAX_KURVEN, Ansicht
from trainingsapp.hrv_core.trends import FENSTER_WAHL, KENNZAHLEN
from trainingsapp.ui.components.kurve import Reihe, kurve

#: Feste Farbe je Kurve — in allen Diagrammen und in der Legende dieselbe
FARBEN: dict[str, str] = {
    "hf_rr": ft.Colors.TERTIARY,
    "hf_geraet": ft.Colors.BLUE_GREY_300,
    "rmssd": ft.Colors.AMBER_400,
    "sdnn": ft.Colors.PURPLE_300,
    "pnn50": ft.Colors.LIGHT_GREEN_400,
}

#: (Kennzahl, Fenster) → Punkte
Daten = Callable[[str, int], Sequence[tuple[float, float]]]


def _einheit(kennzahl: str) -> str | None:
    k = KENNZAHLEN.get(kennzahl)
    return k.einheit if k else None


def bezeichnung(kennzahl: str, ansicht: Ansicht) -> str:
    """„RMSSD 30 s" — mit Fenster, wo gerechnet wird.

    >>> bezeichnung("rmssd", Ansicht()), bezeichnung("hf_geraet", Ansicht())
    ('RMSSD 30 s', 'HF Gerät')
    """
    k = KENNZAHLEN[kennzahl]
    if not k.fenster_s:
        return k.titel
    return f"{k.titel} {ansicht.fenster_fuer(kennzahl, k.fenster_s)} s"


def diagramme(
    ansicht: Ansicht,
    daten: Daten,
    *,
    x_von: float,
    x_bis: float,
    hoehe: int = 120,
    ohne: Sequence[str] = (),
) -> list[ft.Control]:
    """Je Gruppe gleicher Einheit ein Diagramm, darüber die Legende.

    ``ohne``: Kurven, die es für diese Messung nicht gibt (z. B. ``hf_rr`` bei
    einem reinen Pulsgeber) — sie bleiben gewählt, werden aber nicht gezeichnet.
    """
    out: list[ft.Control] = []
    for gruppe in ansicht.gruppen(_einheit):
        gruppe = [k for k in gruppe if k not in ohne]
        if not gruppe:
            continue
        reihen = []
        legende: list[ft.Control] = []
        for k in gruppe:
            fenster = ansicht.fenster_fuer(k, KENNZAHLEN[k].fenster_s)
            reihen.append(Reihe(list(daten(k, fenster)), farbe=FARBEN[k]))
            legende.append(_legende(bezeichnung(k, ansicht), FARBEN[k]))
        einheit = KENNZAHLEN[gruppe[0]].einheit
        out.append(ft.Row(spacing=12, wrap=True, controls=legende))
        out.append(
            kurve(
                reihen,
                einheit=einheit,
                hoehe=hoehe,
                x_von=x_von,
                x_bis=x_bis,
                y_spanne_min=max(KENNZAHLEN[k].spanne_min for k in gruppe),
            )
        )
    return out


def _legende(text: str, farbe: str) -> ft.Control:
    return ft.Row(
        spacing=4,
        tight=True,
        controls=[
            ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe),
            ft.Text(text, size=11, opacity=0.8),
        ],
    )


def chips(ansicht: Ansicht, umschalten: Callable[[str], None]) -> ft.Control:
    """Ein Chip je Kurve; gewählte sind markiert. Mehr als `MAX_KURVEN` geht nicht."""

    def handler(k: str) -> Callable[[], None]:
        return lambda: umschalten(k)

    voll = len(ansicht.kurven) >= MAX_KURVEN
    return ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=0,
        controls=[
            ft.Chip(
                label=ft.Text(KENNZAHLEN[k].titel, size=12),
                selected=k in ansicht.kurven,
                on_select=handler(k),
                show_checkmark=False,
                selected_color=ft.Colors.with_opacity(0.25, FARBEN[k]),
                disabled=voll and k not in ansicht.kurven,
                visual_density=ft.VisualDensity.COMPACT,
            )
            for k in KENNZAHLEN
        ],
    )


def ansicht_menue(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.Control:
    """Menü „Ansichten": Fenster einstellen, speichern, laden, löschen, zurücksetzen.

    ``state`` ist der `AppState` (Speicherort: ``app_setting``); ``geaendert``
    baut die Kurven neu.
    """
    aktuell = state.ansicht()
    gespeichert = state.ansichten()

    def laden(a: Ansicht) -> Callable[[], None]:
        def handler() -> None:
            state.ansicht_setzen(a)
            geaendert()

        return handler

    def zuruecksetzen() -> None:
        state.ansicht_setzen(Ansicht())
        geaendert()

    def loeschen() -> None:
        state.ansicht_loeschen(aktuell.name)
        page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht „{aktuell.name}“ gelöscht.")))
        geaendert()

    eintraege: list[ft.PopupMenuItem] = [
        ft.PopupMenuItem(
            content="Fenster & Darstellung …",
            icon=ft.Icons.TUNE,
            on_click=lambda: page.show_dialog(darstellung_dialog(page, state, geaendert)),
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
            content="Auf Standard zurücksetzen", icon=ft.Icons.RESTART_ALT, on_click=zuruecksetzen
        )
    )
    return ft.PopupMenuButton(
        icon=ft.Icons.DASHBOARD_CUSTOMIZE_OUTLINED,
        tooltip=f"Ansicht: {aktuell.name}",
        items=eintraege,
    )


def darstellung_dialog(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.AlertDialog:
    """Fenster je gewählter Kurve und ob gleiche Einheiten zusammen stehen."""
    ansicht = state.ansicht()

    def fenster_setzen(k: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(e: ft.Event[ft.Dropdown]) -> None:
            with contextlib.suppress(TypeError, ValueError):
                ansicht.fenster[k] = int(e.control.value or 0)
                state.ansicht_setzen(ansicht)
                geaendert()

        return handler

    def gemeinsam(e: ft.Event[ft.Switch]) -> None:
        ansicht.gemeinsam = bool(e.control.value)
        state.ansicht_setzen(ansicht)
        geaendert()

    zeilen: list[ft.Control] = [
        ft.Dropdown(
            label=KENNZAHLEN[k].titel,
            value=str(ansicht.fenster_fuer(k, KENNZAHLEN[k].fenster_s)),
            options=[ft.DropdownOption(key=str(s), text=f"{s} s") for s in FENSTER_WAHL],
            on_select=fenster_setzen(k),
            dense=True,
        )
        for k in ansicht.kurven
        if k in KENNZAHLEN and KENNZAHLEN[k].fenster_s
    ]
    if not zeilen:
        zeilen.append(ft.Text("Keine gewählte Kurve hat ein Fenster.", size=12, opacity=0.7))
    zeilen += [
        ft.Switch(
            label="Gleiche Einheit in einem Diagramm", value=ansicht.gemeinsam, on_change=gemeinsam
        ),
        ft.Text(
            "Gleitendes Fenster: Je länger, desto ruhiger die Kurve und desto "
            "später zeigt sie eine Änderung.",
            size=11,
            opacity=0.65,
        ),
    ]
    return ft.AlertDialog(
        title=ft.Text("Fenster & Darstellung"),
        content=ft.Column(spacing=10, tight=True, controls=zeilen),
        actions=[ft.TextButton("Fertig", on_click=lambda: page.pop_dialog())],
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
    "FARBEN",
    "ansicht_menue",
    "bezeichnung",
    "chips",
    "darstellung_dialog",
    "diagramme",
    "speichern_dialog",
]
