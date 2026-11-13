"""Material beim Üben (U2, Ben 9.11.2026, F6; `docs/plan_paketinhalte.md` §9).

„Wenn es Anweisungen gibt, dann in Fokus/Übung anzeigen, dass Material existiert (Video, Text,
PDF, …). Solange das Material angesehen wird, pausiert die Uhr, kann aber manuell wieder
gestartet werden.“

- **Knopf** (`material_knopf`): nur, wenn es Material gibt (`core.material.material_von`) — im
  Fokus neben den Ebenen, in der Übung des Plans neben dem „i“.
- **Rollen** (Ben, 12.11.2026, P200): Eine **Begleitung** läuft beim Üben mit — wer sie
  öffnet, lässt die Uhr weiterlaufen. Eine **Erklärung** sieht man an und hakt sie ab
  („gesehen“, je Profil auf dem Gerät, `data/material.py`); mit „von selbst zeigen“ öffnet
  sich das Blatt beim ersten ▶ statt der Uhr (`neu_zeigen`), bis sie abgehakt ist. Was die
  Planübung oder eine Ergänzung **ersetzt**, steht unten im Blatt.
- **Blatt** (`material_blatt`): die Abschnitte der Planübung, darunter Videos und Links. Beim
  Öffnen hält die Uhr **dieser** Übung an (`einheit_ui.uhr_fuer_material_anhalten`), „Uhr
  weiter“ startet sie von Hand; beim Schließen läuft sie weiter, wenn sie für das Material
  stand und niemand sie angefasst hat. Die HRV läuft immer weiter.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.material import Material, material_von
from trainingsapp.core.models import Exercise, Media, PlanItem
from trainingsapp.data.material import MaterialRepo
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.medienliste import medium_zeile


def gesehen(state: Any) -> set[str]:
    """Was das Profil abgehakt hat — ohne Datenbank (Attrappe im Test) nichts."""
    try:
        return MaterialRepo(state.con).gesehen(state.profil.id)
    except Exception:
        return set()


def gesehen_setzen(state: Any, uri: str, ja: bool = True) -> None:
    with contextlib.suppress(Exception):
        MaterialRepo(state.con).setzen(state.profil.id, uri, ja)


def _angeboten(state: Any) -> set[str]:
    """Was in dieser Sitzung schon von selbst gezeigt wurde — einmal reicht, sonst käme man
    ohne Haken nie zur Uhr."""
    werte = getattr(state, "material_angeboten", None)
    if not isinstance(werte, set):
        werte = set()
        with contextlib.suppress(Exception):
            state.material_angeboten = werte
    return werte


def neu_zeigen(page: Any, state: Any, uebung: Exercise, item: PlanItem | None) -> bool:
    """Vor dem ersten ▶: Gibt es eine Erklärung, die sich von selbst zeigt und noch nicht
    abgehakt ist, öffnet sich das Blatt — ``True``, die Uhr startet dann erst beim nächsten ▶."""
    m = material_von(uebung, item)
    schon = _angeboten(state)
    neu = [x for x in m.neu(gesehen(state)) if x.uri not in schon]
    if not neu:
        return False
    schon.update(x.uri for x in neu)
    page.show_dialog(material_blatt(page, state, uebung, item, m, neu=tuple(neu)))
    return True


def material_knopf(
    page: Any, state: Any, uebung: Exercise, item: PlanItem | None, *, text: bool = True
) -> ft.Control | None:
    """„Material“ — ``None`` ohne Material; ``text=False``: nur das Symbol (Fokus)."""
    m = material_von(uebung, item)
    if m.leer:
        return None
    hilfe = f"Material: {m.kurztext()} — die Uhr steht, solange du es ansiehst"
    neu = bool(m.neu(gesehen(state)))
    symbol = ft.Icons.MENU_BOOK if neu else ft.Icons.MENU_BOOK_OUTLINED
    farbe = ft.Colors.PRIMARY if neu else None
    if neu:
        hilfe = f"Neu — {hilfe}"

    def oeffnen(_e: Any = None) -> None:
        page.show_dialog(material_blatt(page, state, uebung, item, m))

    if not text:
        return ft.IconButton(
            symbol, icon_color=farbe, tooltip=hilfe, on_click=oeffnen, data="material"
        )
    return ft.TextButton(
        "Material · neu" if neu else "Material",
        icon=symbol,
        tooltip=hilfe,
        on_click=oeffnen,
        data="material",
    )


def material_blatt(
    page: Any,
    state: Any,
    uebung: Exercise,
    item: PlanItem | None,
    m: Material | None = None,
    *,
    neu: tuple[Media, ...] = (),
) -> ft.BottomSheet:
    """Das Blatt mit dem Material — hält die Uhr dieser Übung an, solange es offen ist.
    ``neu``: die Erklärungen, deretwegen es sich von selbst geöffnet hat (stehen oben)."""
    m = m if m is not None else material_von(uebung, item)
    angehalten = einheit_ui.uhr_fuer_material_anhalten(
        state, uebung.id, item.id if item is not None else None
    )
    stand = {"von_hand": False, "uebergeben": False}
    nachher = Nachher()
    uhr_text = ft.Text("Die Uhr steht, solange du hier bist.", size=13, expand=True)
    uhr_knopf = ft.TextButton("Uhr weiter", icon=ft.Icons.PLAY_ARROW, data="uhr_weiter")

    def uhr_weiter(_e: Any = None) -> None:
        if angehalten is not None and einheit_ui.uhr_fortsetzen(page, state, angehalten):
            stand["von_hand"] = True
            uhr_text.value = "Die Uhr läuft weiter."
            uhr_knopf.visible = False
            with contextlib.suppress(Exception):
                uhr_zeile.update()

    uhr_knopf.on_click = uhr_weiter
    uhr_zeile = ft.Container(
        visible=angehalten is not None,
        padding=ft.Padding.only(left=12, right=4, top=2, bottom=2),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Icon(ft.Icons.PAUSE_CIRCLE_OUTLINE, size=20), uhr_text, uhr_knopf],
        ),
    )

    def uebergeben(gehen: Callable[[], Awaitable[None]]) -> None:
        """Eine Paketdatei hat ihre eigene Ansicht (U3): erst das Blatt zu — Dialoge über einem
        Neuaufbau verwaisen —, die Uhr bleibt angehalten, bis man von dort zurückkommt."""
        stand["uebergeben"] = True
        if angehalten is not None and not stand["von_hand"]:
            state.material_lauf = angehalten
        nachher.danach(gehen)
        schliessen(blatt)

    inhalt: list[ft.Control] = [
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.MENU_BOOK_OUTLINED),
                ft.Text(
                    "Neu zu dieser Übung" if neu else "Material",
                    size=18,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
                ft.Text(uebung.name, size=13, opacity=0.7),
            ],
        ),
        uhr_zeile,
    ]
    for a in m.abschnitte:
        if a.name:
            inhalt.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        if a.text:
            inhalt.append(ft.Text(a.text, selectable=True))
    abgehakt = gesehen(state)

    def titel(text: str) -> ft.Control:
        return ft.Text(text, size=11, weight=ft.FontWeight.W_600, opacity=0.7)

    def erklaerung(x: Media) -> ft.Control:
        """Eine Erklärung mit ihrem Haken — öffnen hakt ab, der Haken lässt sich umstellen."""
        haken = ft.Checkbox(
            value=x.uri in abgehakt,
            tooltip="Gesehen — zeigt sich nicht mehr von selbst",
            data=("gesehen", x.uri),
        )

        def umstellen(e: ft.Event[ft.Checkbox]) -> None:
            gesehen_setzen(state, x.uri, bool(e.control.value))

        def geoeffnet() -> None:
            gesehen_setzen(state, x.uri, True)
            haken.value = True
            with contextlib.suppress(Exception):
                haken.update()

        haken.on_change = umstellen
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    content=medium_zeile(
                        page, state, x, uebergeben=uebergeben, beim_oeffnen=geoeffnet
                    ),
                ),
                haken,
            ],
        )

    def begleitung(x: Media) -> ft.Control:
        """Läuft beim Üben mit: Wer sie öffnet, lässt die Uhr weiterlaufen."""
        return medium_zeile(page, state, x, uebergeben=uebergeben, beim_oeffnen=uhr_weiter)

    oben = [x for x in m.erklaerungen if x in neu]
    rest = [x for x in m.erklaerungen if x not in neu]
    inhalt.extend(erklaerung(x) for x in oben)
    if m.begleitungen:
        inhalt.append(titel("BEGLEITUNG · LÄUFT BEIM ÜBEN MIT"))
        inhalt.extend(begleitung(x) for x in m.begleitungen)
    if rest:
        if oben or m.begleitungen:
            inhalt.append(titel("ERKLÄRUNG"))
        inhalt.extend(erklaerung(x) for x in rest)
    if m.ersetzt:
        inhalt.append(titel("AUS DER ÜBUNG · HIER ERSETZT"))
        inhalt.extend(
            ft.Container(opacity=0.75, content=medium_zeile(page, state, x, uebergeben=uebergeben))
            for x in m.ersetzt
        )

    async def beim_schliessen(_e: Any = None) -> None:
        """Die Uhr läuft weiter, wenn sie für das Material stand und niemand sie anfasste —
        außer eine Paketdatei ist jetzt offen (dann beim Zurückkommen von dort)."""
        if angehalten is not None and not stand["von_hand"] and not stand["uebergeben"]:
            einheit_ui.uhr_fortsetzen(page, state, angehalten)
        await nachher.bei_schliessen()

    blatt: ft.BottomSheet = ft.BottomSheet(
        scrollable=True,
        on_dismiss=beim_schliessen,
        content=blatt_spalte(
            inhalt,
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Schließen", on_click=lambda _e=None: schliessen(blatt))
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = ["gesehen", "gesehen_setzen", "material_blatt", "material_knopf", "neu_zeigen"]
