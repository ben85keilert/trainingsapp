"""Stoppuhr und Timer in der Übung (Ben, 18.10.2026; `docs/plan_stoppuhr.md` §5).

Zwei Darstellungen, umschaltbar unter Einstellungen → Übungen
(`AppState.uhr_darstellung`, Vorgabe die Zeile):

- **Zeile** (Skizzen A1–A4): unter „Gemacht | Notiz“ steht links als Text, was startet —
  die Stoppuhr oder ein Timer der Übung, ▾ wählt um —, daneben die Zeit, rechts
  „Bereitstellen“ und ein einziger ▶. So liest sich ▶ nie als „Timer starten“, wenn die
  Stoppuhr gemeint ist.
- **Knöpfe** (Skizze B2): „Uhr“ und „Timer“ zwischen „Gemacht“ und „Notiz“.

Läuft die Uhr dieser Übung, zeigen beide dieselbe Anzeige: die Zeit, Anhalten bzw. Weiter
(„Pause pausiert und beendet nicht“), **Fertig** (trägt ein, wie die Übung zählt) und
**Abbrechen** — ohne Rückfrage, trägt nichts ein. Die Wahl im ▾ gilt für diese Sitzung der
App und ändert keine Einstellung (Ben: „wenn im Übungsfeld ein anderer Timer ausgewählt
wurde, ändert sich keine Einstellung“); gespeichert wird nur in Übung bzw. Planübung.
Ob die Uhr überhaupt dasteht, sagt `core.uebung_timer.uhr_an`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.timer import TimerProfil, dauer_text, stoppuhr
from trainingsapp.core.uebung_timer import profile_zur_wahl, timer_fuer
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein, UebungKontext
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.state import UHR_KNOEPFE

#: Eckenradius wie die Knöpfe im Plan
ECKEN = ft.RoundedRectangleBorder(radius=14)


@dataclass
class UhrTeile:
    """Was die Übung von der Uhr bekommt: Knöpfe für die Reihe mit „Gemacht“ (Darstellung
    „Knöpfe“) und eine eigene Zeile darunter (die Zeile oder die laufende Anzeige)."""

    knoepfe: list[ft.Control] = field(default_factory=list)
    zeile: ft.Control | None = None


def schluessel(uebung: Exercise, item: PlanItem | None) -> str:
    """Wofür die Wahl gilt — die Planübung, ohne Plan die Übung."""
    return item.id if item is not None else uebung.id


def angebot(uebung: Exercise, plan: Plan | None, item: PlanItem | None) -> list[TimerProfil]:
    """Zur Wahl: die Stoppuhr, dann die Timer der Planübung, der Übung und des Plans."""
    return profile_zur_wahl(uebung, plan, item, mit_stoppuhr=True)


def gesetzt(state: Any, uebung: Exercise, plan: Plan | None, item: PlanItem | None) -> TimerProfil:
    """Was ▶ startet: die in dieser Sitzung gewählte (oder zuletzt gestartete) Uhr — sonst
    wie eingestellt (Planübung > Plan > erster Timer der Übung), ohne Timer die Stoppuhr."""
    gewaehlt = state.uhr_wahl.get(schluessel(uebung, item))
    if gewaehlt:
        treffer = next((p for p in angebot(uebung, plan, item) if p.id == gewaehlt), None)
        if treffer is not None:
            return treffer
    return timer_fuer(uebung, plan, item) or stoppuhr()


def laufende(state: Any, uebung: Exercise, item: PlanItem | None) -> Einheitslauf | None:
    """Die Einheit, in der gerade die Uhr dieser Übung (dieser Planübung) läuft."""
    e = einheit_ui.laeuft(state)
    teil = e.teil("plan") if e is not None else None
    if not isinstance(teil, UebungBaustein) or teil.kontext.uebung_id != uebung.id:
        return None
    if item is not None and teil.kontext.item_id not in (None, item.id):
        return None
    return e


def uhr_teile(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan | None,
    item: PlanItem | None,
    timer_oeffnen: Callable[[], object],
) -> UhrTeile:
    """Knöpfe und Zeile der Uhr für eine Übung — ``plan``/``item`` ``None`` ohne Plan.

    ``uebung`` ist die Übung aus dem Katalog (die Planübung liest ``item``);
    ``timer_oeffnen`` führt zum Timer der Übung (Profile, „zählt“, Läufe heute). Der Lauf
    trägt die Ausführung ein, die der Block beim Start zeigt (Variante, Gewicht …).
    """
    e = laufende(state, uebung, item)
    if e is not None and e.timer is not None:
        return UhrTeile(zeile=_laufend(page, state, e))

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def kontext() -> UebungKontext:
        wahl = uebung_lauf.gewaehlte_ausfuehrung(state, uebung, item)
        return uebung_lauf.kontext_fuer(uebung, plan, item, auspraegung=wahl)

    def starten(profil: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            state.uhr_wahl[schluessel(uebung, item)] = profil.id  # zuletzt gestartet
            try:
                lauf = uebung_lauf.starten(page, state, kontext(), _kopie(profil))
            except RuntimeError as fehler:
                melden(str(fehler))
                return
            state.uebung_laeufe[uebung.id] = lauf.id
            state.neu_zeichnen()

        return handler

    def bereitstellen(profil: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            try:
                lauf = uebung_lauf.bereitstellen(page, state, kontext(), _kopie(profil))
            except RuntimeError as fehler:
                melden(str(fehler))
                return
            state.uebung_laeufe[uebung.id] = lauf.id
            melden(f"{uebung.name}: {profil.anzeigename} steht bereit — oben „Alle starten“")
            state.neu_zeichnen()

        return handler

    if state.uhr_darstellung() == UHR_KNOEPFE:
        return UhrTeile(knoepfe=_knoepfe(uebung, plan, item, starten, timer_oeffnen))
    profil = gesetzt(state, uebung, plan, item)

    def waehlen(p: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            state.uhr_wahl[schluessel(uebung, item)] = p.id  # nur für diese Sitzung
            state.neu_zeichnen()

        return handler

    menue = ft.PopupMenuButton(
        tooltip="Stoppuhr oder Timer wählen",
        content=ft.Container(
            padding=ft.Padding.only(left=10, right=6, top=6, bottom=6),
            border_radius=20,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            content=ft.Row(
                tight=True,
                spacing=6,
                controls=[
                    ft.Icon(_symbol(profil), size=18),
                    ft.Text(
                        profil.anzeigename,
                        weight=ft.FontWeight.W_600,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=20),
                ],
            ),
        ),
        items=[
            *(
                ft.PopupMenuItem(
                    icon=_symbol(p),
                    checked=p.id == profil.id,
                    content=ft.Column(
                        spacing=0,
                        tight=True,
                        controls=[
                            ft.Text(p.anzeigename, weight=ft.FontWeight.W_600),
                            ft.Text(p.kurztext(), size=12, opacity=0.7),
                        ],
                    ),
                    on_click=waehlen(p),
                )
                for p in angebot(uebung, plan, item)
            ),
            ft.PopupMenuItem(),  # Trennlinie
            ft.PopupMenuItem(
                icon=ft.Icons.TUNE,
                content=ft.Text("Timer der Übung …"),
                on_click=timer_oeffnen,
            ),
        ],
    )
    zeit = "0:00" if profil.ist_stoppuhr else dauer_text(profil.gesamt_s())
    zeile = ft.Container(
        padding=ft.Padding.only(left=8, right=6, top=6, bottom=6),
        border_radius=16,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
        content=ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(content=menue, expand=True, alignment=ft.Alignment.CENTER_LEFT),
                ft.Text(zeit, size=20, weight=ft.FontWeight.W_500),
                ft.IconButton(
                    ft.Icons.HOURGLASS_TOP,
                    tooltip="Bereitstellen — startet mit „Alle starten“",
                    on_click=bereitstellen(profil),
                ),
                ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    tooltip=f"{profil.anzeigename} starten",
                    icon_size=30,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY, color=ft.Colors.ON_PRIMARY),
                    on_click=starten(profil),
                ),
            ],
        ),
    )
    return UhrTeile(zeile=zeile)


def _knoepfe(
    uebung: Exercise,
    plan: Plan | None,
    item: PlanItem | None,
    starten: Callable[[TimerProfil], Callable[[], None]],
    timer_oeffnen: Callable[[], object],
) -> list[ft.Control]:
    """Darstellung „Knöpfe“ (Skizze B2): „Uhr“ startet die Stoppuhr; „Timer“ startet den
    Timer der Übung — bei mehreren mit Auswahl, ohne einen führt er zum Timer der Übung."""
    uhr = _knopf("Uhr", ft.Icons.PLAY_ARROW, starten(stoppuhr()))
    timer = [p for p in angebot(uebung, plan, item) if not p.ist_stoppuhr]
    if not timer:
        return [uhr, _knopf("Timer", ft.Icons.TIMER_OUTLINED, timer_oeffnen)]
    if len(timer) == 1:
        return [uhr, _knopf("Timer", ft.Icons.TIMER_OUTLINED, starten(timer[0]))]
    auswahl = ft.PopupMenuButton(
        tooltip="Timer wählen und starten",
        content=ft.Container(
            height=48,
            padding=ft.Padding.symmetric(horizontal=14),
            border_radius=14,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Row(
                tight=True,
                spacing=6,
                controls=[
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=18),
                    ft.Text("Timer"),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18),
                ],
            ),
        ),
        items=[
            *(
                ft.PopupMenuItem(
                    icon=ft.Icons.PLAY_ARROW,
                    content=ft.Column(
                        spacing=0,
                        tight=True,
                        controls=[
                            ft.Text(p.anzeigename, weight=ft.FontWeight.W_600),
                            ft.Text(p.kurztext(), size=12, opacity=0.7),
                        ],
                    ),
                    on_click=starten(p),
                )
                for p in timer
            ),
            ft.PopupMenuItem(),
            ft.PopupMenuItem(
                icon=ft.Icons.TUNE, content=ft.Text("Timer der Übung …"), on_click=timer_oeffnen
            ),
        ],
    )
    return [uhr, auswahl]


def _laufend(page: Any, state: Any, e: Einheitslauf) -> ft.Control:
    """Die laufende Uhr der Übung: Zeit, Anhalten bzw. Weiter, Fertig, Abbrechen — sie
    zählt im Takt des Tickers mit (`AppState.timer_beobachter`)."""
    assert e.timer is not None
    lauf = e.timer.lauf
    zeit = ft.Text(size=40, weight=ft.FontWeight.BOLD)
    oben = ft.Text(size=14, opacity=0.85, expand=True)
    pause = ft.OutlinedButton(height=48, style=ft.ButtonStyle(shape=ECKEN), expand=True)

    def beschriften() -> None:
        stand = lauf.stand()
        zeit.value = lauf.anzeige()
        name = lauf.profil.anzeigename
        if not lauf.vorwaerts and not stand.fertig:
            name = f"{name}: {lauf.abschnittsname(stand.nummer)}"  # „Halten (Runde 1/3)“
        if stand.fertig:
            oben.value = f"{lauf.profil.anzeigename} · fertig"
        else:
            oben.value = f"{name} läuft" if stand.laeuft else f"{name} · angehalten"
        laeuft = stand.laeuft
        pause.content = ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.PAUSE if laeuft else ft.Icons.PLAY_ARROW, size=18),
                ft.Text("Anhalten" if laeuft else "Weiter"),
            ],
        )

    def auffrischen() -> None:
        beschriften()
        with contextlib.suppress(Exception):
            anzeige.update()

    def anhalten_oder_weiter() -> None:
        einheit_ui.anhalten_oder_weiter(page, state)
        auffrischen()

    def fertig() -> None:
        lauf.fertig_machen()  # die Einheit endet im Takt danach und trägt ein
        auffrischen()

    def abbrechen() -> None:
        lauf.abbrechen()  # ohne Rückfrage (Ben, 18.10.2026) — trägt nichts ein
        auffrischen()

    pause.on_click = anhalten_oder_weiter
    beschriften()
    anzeige = ft.Container(
        padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
        border_radius=16,
        border=ft.Border.all(1.5, ft.Colors.PRIMARY),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        content=ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[ft.Icon(_symbol(lauf.profil), size=18, opacity=0.85), oben],
                ),
                zeit,
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        pause,
                        ft.FilledButton(
                            content=ft.Row(
                                tight=True,
                                spacing=6,
                                controls=[ft.Icon(ft.Icons.STOP, size=18), ft.Text("Fertig")],
                            ),
                            height=48,
                            expand=True,
                            style=ft.ButtonStyle(shape=ECKEN),
                            tooltip="Beenden und eintragen",
                            on_click=fertig,
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            tooltip="Abbrechen — trägt nichts ein",
                            on_click=abbrechen,
                        ),
                    ],
                ),
            ],
        ),
    )
    state.timer_beobachter["uhr_in_der_uebung"] = auffrischen
    return anzeige


def _knopf(text: str, icon: ft.IconData, on_click: Callable[[], object]) -> ft.Control:
    """Wie „Gemacht“ im Plan, nur nicht betont."""
    return ft.FilledTonalButton(
        content=ft.Row(tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text)]),
        height=48,
        style=ft.ButtonStyle(shape=ECKEN, padding=ft.Padding.symmetric(horizontal=14)),
        on_click=on_click,
    )


def _symbol(p: TimerProfil) -> ft.IconData:
    return ft.Icons.AV_TIMER if p.ist_stoppuhr else ft.Icons.TIMER_OUTLINED


def _kopie(p: TimerProfil) -> TimerProfil:
    """Eine eigene Kopie für den Lauf — das Profil der Übung bleibt, wie es ist."""
    neu = TimerProfil.aus_dict(p.als_dict())
    assert neu is not None
    return neu


__all__ = ["UhrTeile", "angebot", "gesetzt", "laufende", "schluessel", "uhr_teile"]
