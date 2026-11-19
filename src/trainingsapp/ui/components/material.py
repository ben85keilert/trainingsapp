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
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.material import Lage, Material, material_von, plan_material
from trainingsapp.core.models import (
    BEGLEITUNG,
    BEI,
    IMMER,
    NACHHER,
    Exercise,
    Media,
    Plan,
    PlanItem,
)
from trainingsapp.data.material import MaterialRepo
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.medienliste import medium_zeile


def begleitvideos(
    state: Any, uebung: Exercise, item: PlanItem | None
) -> tuple[list[str], list[Media]]:
    """Die Begleitvideos der Übung für den Fokus (Ben, 18.11.2026): die Dateien, die auf dem
    Gerät liegen (Paketdateien, geladene Links), und die Videolinks, die erst geladen werden
    müssen — in der Web-Fassung keine Links (`config.WEB`: ``link_videos``)."""
    from trainingsapp.config import ist_aktiv
    from trainingsapp.core.paketmedien import ist_paketmedium

    ablage = getattr(getattr(state, "pakete", None), "ablage", None)
    if ablage is None:
        return [], []
    pfade: list[str] = []
    offen: list[Media] = []
    for m in material_von(uebung, item).begleitvideos:
        if ist_paketmedium(m):
            pfad = ablage.pfad(m.uri)
        elif ist_aktiv("link_videos"):
            name = ablage.link_datei(m.uri)
            if name is None:
                offen.append(m)
                continue
            pfad = ablage.pfad(name)
        else:
            continue
        if pfad is not None and pfad.is_file():
            pfade.append(str(pfad))
    return pfade, offen


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


def _neue(state: Any, stuecke: tuple[Media, ...], immer_wieder: bool) -> list[Media]:
    """Was jetzt von selbst aufgeht. Einmal je Sitzung reicht — außer bei „jedes Mal“
    (``oft = "immer"``): Das kommt bei jedem Start wieder. Wo ein Tipp erst das Blatt öffnet und
    der nächste startet (▶ der Übung, „Workout starten“), gilt es als gezeigt, bis dieser nächste
    Tipp gestartet hat; ``immer_wieder``: der Aufrufer fragt ohnehin nur einmal je Anlass (ein
    Schritt des Workouts, das Ende einer Übung) — dort kommt es bei jedem Aufruf."""
    schon = _angeboten(state)
    immer = {x.uri for x in stuecke if x.oft == IMMER}
    neu = [x for x in stuecke if x.uri not in schon or (immer_wieder and x.uri in immer)]
    if not neu:
        schon.difference_update(immer)  # beim nächsten Start wieder
        return []
    schon.update(x.uri for x in neu)
    return neu


def neu_zeigen(
    page: Any, state: Any, uebung: Exercise, item: PlanItem | None, *, immer_wieder: bool = False
) -> bool:
    """Vor dem ersten ▶: Gibt es eine Erklärung, die sich von selbst zeigt und noch nicht
    abgehakt ist (oder jedes Mal kommt), öffnet sich das Blatt — ``True``, die Uhr startet dann
    erst beim nächsten ▶."""
    m = material_von(uebung, item)
    neu = _neue(state, m.neu(gesehen(state)), immer_wieder)
    if not neu:
        return False
    page.show_dialog(material_blatt(page, state, uebung, item, m, neu=tuple(neu)))
    return True


def nachher_zeigen(page: Any, state: Any, uebung: Exercise, item: PlanItem | None) -> bool:
    """**Nach** der Übung (Ben, 18.11.2026: „am Ende“; `docs/plan_medien_zeitpunkte.md` §2):
    Hat sie eine Erklärung für nachher, die von selbst kommt, geht das Blatt auf — gerufen aus
    dem Tipp auf „Fertig“ bzw. dem Ende des Schritts, nie beim Aufbau einer Ansicht."""
    m = material_von(uebung, item)
    neu = _neue(state, m.nachher_neu(gesehen(state)), True)
    if not neu:
        return False
    page.show_dialog(
        material_blatt(page, state, uebung, item, m, neu=tuple(neu), titel="Nach der Übung")
    )
    return True


def material_knopf(
    page: Any, state: Any, uebung: Exercise, item: PlanItem | None, *, text: bool = True
) -> ft.Control | None:
    """„Medien“ (bis 17.11.2026 „Material“; Ben: „Medien überall“) — ``None`` ohne Material;
    ``text=False``: nur das Symbol (Fokus)."""
    m = material_von(uebung, item)
    if m.leer:
        return None
    hilfe = f"Medien: {m.kurztext()} — die Uhr steht, solange du sie ansiehst"
    # „neu“ ist, was noch abzuhaken ist — nicht, was ohnehin jedes Mal kommt
    neu = any(x.oft != IMMER for x in m.neu(gesehen(state)))
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
        "Medien · neu" if neu else "Medien",
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
    titel: str = "",
) -> ft.BottomSheet:
    """Das Blatt mit dem Material — hält die Uhr dieser Übung an, solange es offen ist.
    ``neu``: die Erklärungen, deretwegen es sich von selbst geöffnet hat (stehen oben);
    ``titel``: die Überschrift dazu (sonst „Neu zu dieser Übung“).

    **Ordnung** (Ben, 18.11.2026: „zugewiesen … und danach geordnet“): je Abschnitt der Text und
    darunter seine Stücke (`Material.nach_abschnitten`), dann die Stücke ohne Abschnitt —
    Begleitung, Erklärung, „nach der Übung“, „zu einem Ereignis“."""
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
                    (titel or "Neu zu dieser Übung") if neu else "Medien",
                    size=18,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
                ft.Text(uebung.name, size=13, opacity=0.7),
            ],
        ),
        uhr_zeile,
    ]
    abgehakt = gesehen(state)

    def gruppe(text: str) -> ft.Control:
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
        zeile = ft.Row(
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
        if x.wann == BEI and x.bei is not None:  # wozu es von selbst kommt
            return ft.Column(
                spacing=0,
                tight=True,
                controls=[zeile, ft.Text(f"kommt {x.bei.text()}", size=11, opacity=0.6)],
            )
        return zeile

    def begleitung(x: Media) -> ft.Control:
        """Läuft beim Üben mit: Wer sie öffnet, lässt die Uhr weiterlaufen."""
        return medium_zeile(page, state, x, uebergeben=uebergeben, beim_oeffnen=uhr_weiter)

    def stueck(x: Media) -> ft.Control:
        return begleitung(x) if x.rolle == BEGLEITUNG else erklaerung(x)

    oben = [x for x in m.erklaerungen if x in neu]
    inhalt.extend(erklaerung(x) for x in oben)
    je_abschnitt, ohne = m.nach_abschnitten(ohne=oben)
    for a, stuecke in je_abschnitt:
        if a.name:
            inhalt.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        if a.text:
            inhalt.append(ft.Text(a.text, selectable=True))
        inhalt.extend(stueck(x) for x in stuecke)
    begleitungen = [x for x in ohne if x.rolle == BEGLEITUNG]
    vorher = [x for x in ohne if x.rolle != BEGLEITUNG and not x.wann]
    spaeter = [x for x in ohne if x.rolle != BEGLEITUNG and x.wann == NACHHER]
    bei = [x for x in ohne if x.rolle != BEGLEITUNG and x.wann == BEI]
    if begleitungen:
        inhalt.append(gruppe("BEGLEITUNG · LÄUFT BEIM ÜBEN MIT"))
        inhalt.extend(begleitung(x) for x in begleitungen)
    if vorher:
        if oben or begleitungen or any(s for _, s in je_abschnitt):
            inhalt.append(gruppe("ERKLÄRUNG"))
        inhalt.extend(erklaerung(x) for x in vorher)
    if spaeter:
        inhalt.append(gruppe("NACH DER ÜBUNG"))
        inhalt.extend(erklaerung(x) for x in spaeter)
    if bei:
        inhalt.append(gruppe("ZU EINEM EREIGNIS"))
        inhalt.extend(erklaerung(x) for x in bei)
    if m.ersetzt:
        inhalt.append(gruppe("AUS DER ÜBUNG · HIER ERSETZT"))
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


# -- Medien des Plans selbst (Ben, 17.11.2026, `docs/plan_medien_reiter.md` §4) ---------------


def plan_neu_zeigen(page: Any, state: Any, plan: Plan) -> bool:
    """**Vor dem ersten Start** (erstes ▶ einer Übung, „Workout starten“): Hat der Plan eine
    Erklärung, die sich beim ersten Mal von selbst zeigt und noch nicht abgehakt ist (oder jedes
    Mal kommt), geht das Blatt auf — ``True``, gestartet wird erst beim nächsten Tipp (wie bei
    der Übung, P200). Nie beim Aufbau einer Ansicht (Geister-Dialog), nie im Lauf."""
    m = plan_material(plan)
    neu = _neue(state, m.neu(gesehen(state)), False)
    if not neu:
        return False
    page.show_dialog(plan_blatt(page, state, plan, m, neu=tuple(neu)))
    return True


def plan_nachher_zeigen(page: Any, state: Any, plan: Plan) -> bool:
    """**Am Ende des Plans** (Ben, 18.11.2026: „am Anfang des Planes, am Ende“): Was der Plan
    für nachher hat und von selbst kommt, geht auf — gerufen, wenn das Workout endet bzw. die
    letzte Übung der Liste fertig ist, nie beim Aufbau einer Ansicht."""
    m = plan_material(plan)
    neu = _neue(state, m.nachher_neu(gesehen(state)), True)
    if not neu:
        return False
    page.show_dialog(plan_blatt(page, state, plan, m, neu=tuple(neu), titel="Zum Abschluss"))
    return True


def plan_antwort_zeigen(page: Any, state: Any, plan: Plan, antworten: Sequence[str]) -> bool:
    """**Bei einer Antwort** auf eine Frage des Ablaufs (Ben: „wenn Wahl für hier und da … →
    Video“): Stücke des Plans mit diesem Ereignis gehen auf, ohne dass sich der Weg ändert —
    bis sie abgehakt sind oder jedes Mal (`Media.oft`)."""
    m = plan_material(plan)
    abgehakt = gesehen(state)
    neu = [
        x
        for x in m.faellig(Lage(antworten=tuple(antworten)))
        if x.oft == IMMER or x.uri not in abgehakt
    ]
    if not neu:
        return False
    page.show_dialog(plan_blatt(page, state, plan, m, neu=tuple(neu), titel="Zu deiner Antwort"))
    return True


def plan_knopf(page: Any, state: Any, plan: Plan) -> ft.Control | None:
    """Das Buch-Symbol am Kopf des Plans und im Start-Bild des Workouts — dezent, gefüllt und in
    der Akzentfarbe, solange etwas neu ist. ``None``, wenn der Plan selbst nichts hat."""
    m = plan_material(plan)
    if m.leer:
        return None
    neu = any(x.oft != IMMER for x in m.neu(gesehen(state)))
    hilfe = f"Medien zum Plan: {m.kurztext()}"
    return ft.IconButton(
        ft.Icons.MENU_BOOK if neu else ft.Icons.MENU_BOOK_OUTLINED,
        icon_color=ft.Colors.PRIMARY if neu else None,
        tooltip=f"Neu — {hilfe}" if neu else hilfe,
        on_click=lambda _e=None: page.show_dialog(plan_blatt(page, state, plan, m)),
        data="plan_medien",
    )


def plan_blatt(
    page: Any,
    state: Any,
    plan: Plan,
    m: Material | None = None,
    *,
    neu: tuple[Media, ...] = (),
    titel: str = "",
) -> ft.BottomSheet:
    """Das Blatt mit der Beschreibung und den Stücken des Plans — ohne Uhr (es läuft noch
    nichts). Eine Erklärung hakt sich beim Öffnen ab wie beim Üben; eine Paketdatei geht erst
    auf, wenn das Blatt zu ist (Dialoge über einem Neuaufbau verwaisen)."""
    m = m if m is not None else plan_material(plan)
    nachher = Nachher()

    def uebergeben(gehen: Callable[[], Awaitable[None]]) -> None:
        nachher.danach(gehen)
        schliessen(blatt)

    inhalt: list[ft.Control] = [
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.MENU_BOOK_OUTLINED),
                ft.Text(
                    (titel or "Neu zum Plan") if neu else "Medien zum Plan",
                    size=18,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
                ft.Text(plan.name, size=13, opacity=0.7),
            ],
        )
    ]
    abgehakt = gesehen(state)

    def stueck(x: Media) -> ft.Control:
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

    vorn = [x for x in m.medien if x in neu]
    inhalt.extend(stueck(x) for x in vorn)
    je_abschnitt, ohne = m.nach_abschnitten(ohne=vorn)
    for a, stuecke in je_abschnitt:
        if a.name:
            inhalt.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        if a.text:
            inhalt.append(ft.Text(a.text, selectable=True))
        inhalt.extend(stueck(x) for x in stuecke)

    def gruppe(text: str) -> ft.Control:
        return ft.Text(text, size=11, weight=ft.FontWeight.W_600, opacity=0.7)

    inhalt.extend(stueck(x) for x in ohne if not x.wann)
    if am_ende := [x for x in ohne if x.wann == NACHHER]:
        inhalt.append(gruppe("ZUM ABSCHLUSS"))
        inhalt.extend(stueck(x) for x in am_ende)
    if bei := [x for x in ohne if x.wann == BEI and x.bei is not None]:
        inhalt.append(gruppe("ZU EINER ANTWORT"))
        for x in bei:
            assert x.bei is not None
            inhalt.append(stueck(x))
            inhalt.append(ft.Text(f"kommt {x.bei.text()}", size=11, opacity=0.6))

    blatt: ft.BottomSheet = ft.BottomSheet(
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
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


__all__ = [
    "begleitvideos",
    "gesehen",
    "gesehen_setzen",
    "material_blatt",
    "material_knopf",
    "nachher_zeigen",
    "neu_zeigen",
    "plan_antwort_zeigen",
    "plan_blatt",
    "plan_knopf",
    "plan_nachher_zeigen",
    "plan_neu_zeigen",
]
