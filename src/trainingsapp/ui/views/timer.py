"""Timer als Werkzeug — Route `<irgendwo>/timer`, Profil bearbeiten `…/timer/bearbeiten[/<id>]`.

Der Timer ist von überall erreichbar (Symbol oben in der Leiste) und legt sich
über die aktuelle Ansicht: „Zurück" führt dorthin, wo man war — aus einem
Plan zurück in den Plan. Er läuft weiter, wenn man die Ansicht verlässt; die
Leiste zeigt dann die Restzeit (`timer_knopf`).

Ein **Profil** ist eine Folge benannter Abschnitte (``mm:ss``) und eine
Rundenzahl (`core.timer.TimerProfil`). Das zuletzt benutzte ist beim Öffnen
aktiv. Ohne eigene Profile gibt es zwei Vorlagen.

Der Ablauf rechnet auf der monotonen Uhr (`core.timer.TimerLauf`); diese
Ansicht fragt nur ab. Ein Abschnittswechsel vibriert (Android), das Ende
vibriert doppelt. Zwei Grenzen, die man kennen sollte:

- Töne gibt es noch nicht — dafür bräuchte die App das Paket ``flet-audio``.
- Schaltet Android bei dunklem Display die App schlafen, bleibt die Vibration
  aus; die Zeit stimmt beim Aufwachen trotzdem (Uhr statt gezählter Ticks).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.timer import (
    MAX_RUNDEN,
    Abschnitt,
    TimerLauf,
    TimerProfil,
    TimerStand,
    dauer_lesen,
    dauer_text,
    wechsel,
)
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

#: So oft je Sekunde wird die Anzeige aufgefrischt
TICK_S = 0.2


def timer_route(basis: str) -> str:
    """Die Timer-Route über einer Ansicht.

    >>> timer_route("/"), timer_route("/plan/abc")
    ('/timer', '/plan/abc/timer')
    """
    return basis.rstrip("/") + "/timer"


# ---------------------------------------------------------------------------
# Ablauf: Lauf holen, Ticker
# ---------------------------------------------------------------------------


def lauf_fuer(state: AppState, profil: TimerProfil) -> TimerLauf:
    """Der Lauf zum Profil — ein anderes Profil (oder ein geändertes) beginnt neu."""
    lauf: TimerLauf | None = state.timer
    if lauf is None or lauf.profil != profil:
        lauf = TimerLauf(profil)
        state.timer = lauf
    return lauf


async def _signal(state: AppState, ende: bool) -> None:
    """Vibrieren — nur, wo es geht (Android); sonst still."""
    haptik = getattr(state, "haptik", None)
    if haptik is None:
        return
    with contextlib.suppress(Exception):
        await haptik.vibrate()
        if ende:
            await asyncio.sleep(0.35)
            await haptik.vibrate()


def ticker_starten(page: Any, state: AppState) -> None:
    """Eine Aufgabe, die läuft, solange der Timer läuft — nie zwei zugleich."""
    if state.timer_aufgabe:
        return

    async def ticken() -> None:
        alt: TimerStand | None = None
        try:
            while state.timer is not None:
                stand = state.timer.stand()
                if wechsel(alt, stand):
                    await _signal(state, stand.fertig)
                alt = stand
                for beobachter in list(state.timer_beobachter.values()):
                    with contextlib.suppress(Exception):
                        beobachter()
                if not stand.laeuft:
                    break
                await asyncio.sleep(TICK_S)
        finally:
            state.timer_aufgabe = None

    state.timer_aufgabe = True
    page.run_task(ticken)


# ---------------------------------------------------------------------------
# Knopf in der Leiste
# ---------------------------------------------------------------------------


def timer_knopf(page: Any, state: AppState, name: str) -> ft.Control:
    """Timer-Symbol für eine AppBar; läuft der Timer, steht die Restzeit daneben.

    ``name`` unterscheidet die Leisten — jede trägt sich als Beobachter ein und
    ersetzt dabei ihren alten Eintrag.
    """
    restzeit = ft.Text("", size=13, weight=ft.FontWeight.W_600)

    def auffrischen() -> None:
        lauf: TimerLauf | None = state.timer
        stand = lauf.stand() if lauf is not None else None
        aktiv = stand is not None and lauf is not None and lauf.begonnen and not stand.fertig
        restzeit.value = dauer_text(stand.rest_s) if aktiv and stand else ""
        restzeit.visible = aktiv
        with contextlib.suppress(Exception):
            knopf.update()

    async def oeffnen() -> None:
        if "/timer" in page.route:
            return
        await page.push_route(timer_route(page.route))

    knopf = ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        border_radius=18,
        ink=True,
        tooltip="Timer",
        on_click=oeffnen,
        content=ft.Row(
            spacing=4,
            tight=True,
            controls=[ft.Icon(ft.Icons.TIMER_OUTLINED, size=22), restzeit],
        ),
    )
    state.timer_beobachter[name] = auffrischen
    restzeit.visible = False
    lauf: TimerLauf | None = state.timer
    if lauf is not None and lauf.begonnen and not lauf.fertig:
        stand = lauf.stand()
        restzeit.value, restzeit.visible = dauer_text(stand.rest_s), True
    return knopf


# ---------------------------------------------------------------------------
# Timer-Ansicht
# ---------------------------------------------------------------------------


def timer_view(page: Any, state: AppState, basis: str) -> ft.View:
    route = timer_route(basis)
    profile = state.timer_profile()
    profil = state.timer_profil()
    lauf = lauf_fuer(state, profil)

    abschnitt_text = ft.Text(size=24, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)
    zeit_text = ft.Text(size=84, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    fortschritt = ft.ProgressBar(value=0, bar_height=8, border_radius=4)
    stand_text = ft.Text(size=13, opacity=0.75, text_align=ft.TextAlign.CENTER)
    haupt_knopf = ft.FilledButton(
        height=56, style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=28))
    )
    ablauf = ft.Column(spacing=2)

    def ablauf_zeilen(stand: TimerStand) -> list[ft.Control]:
        zeilen: list[ft.Control] = []
        for i, a in enumerate(profil.abschnitte):
            jetzt = lauf.begonnen and not stand.fertig and i == stand.index
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY) if jetzt else None,
                    content=ft.Row(
                        controls=[
                            ft.Text(dauer_text(a.dauer_s), width=56, weight=ft.FontWeight.W_600),
                            ft.Text(a.name or f"Abschnitt {i + 1}", expand=True),
                            ft.Icon(ft.Icons.PLAY_ARROW, size=16, visible=jetzt),
                        ]
                    ),
                )
            )
        if profil.runden > 1:
            zeilen.append(
                ft.Text(
                    f"× {profil.runden} Runden · gesamt {dauer_text(profil.gesamt_s())}",
                    size=12,
                    opacity=0.7,
                )
            )
        return zeilen

    def anzeigen() -> None:
        stand = lauf.stand()
        if stand.fertig:
            abschnitt_text.value = "Fertig"
            zeit_text.value = "0:00"
            fortschritt.value = 1.0
            stand_text.value = f"{profil.name} · {dauer_text(profil.gesamt_s())}"
        else:
            abschnitt_text.value = stand.name or f"Abschnitt {stand.index + 1}"
            # Vor dem Start die volle Dauer, danach aufgerundet (0:01 bis zuletzt)
            zeit_text.value = dauer_text(-(-stand.rest_s // 1))
            fortschritt.value = stand.anteil
            teile = []
            if profil.runden > 1:
                teile.append(f"Runde {stand.runde} von {profil.runden}")
            if len(profil.abschnitte) > 1:
                teile.append(f"Abschnitt {stand.index + 1} von {len(profil.abschnitte)}")
            teile.append(f"gesamt noch {dauer_text(stand.gesamt_rest_s)}")
            stand_text.value = " · ".join(teile)
        if stand.laeuft:
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PAUSE, "Pause")
            haupt_knopf.on_click = anhalten
        else:
            text = "Nochmal" if stand.fertig else ("Weiter" if lauf.begonnen else "Start")
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PLAY_ARROW, text)
            haupt_knopf.on_click = starten
        ablauf.controls = ablauf_zeilen(stand)

    def auffrischen() -> None:
        anzeigen()
        with contextlib.suppress(Exception):
            inhalt.update()

    def starten() -> None:
        lauf.start()
        ticker_starten(page, state)
        auffrischen()

    def anhalten() -> None:
        lauf.pause()
        auffrischen()
        _leisten_auffrischen(state)

    def zuruecksetzen() -> None:
        lauf.zuruecksetzen()
        auffrischen()
        _leisten_auffrischen(state)

    def weiter() -> None:
        lauf.weiter()
        ticker_starten(page, state)
        auffrischen()

    def zurueck() -> None:
        lauf.zurueck()
        auffrischen()

    def waehler(profil_id: str) -> Callable[[], None]:
        def handler() -> None:
            if profil_id == profil.id:
                return
            if lauf.laeuft:
                lauf.pause()
            state.timer_profil_waehlen(profil_id)
            state.timer = None
            state.neu_zeichnen()

        return handler

    async def neu() -> None:
        await page.push_route(f"{route}/bearbeiten")

    async def bearbeiten() -> None:
        await page.push_route(f"{route}/bearbeiten/{profil.id}")

    profil_chips = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=8,
        controls=[
            ft.Chip(
                label=ft.Text(p.name),
                selected=p.id == profil.id,
                show_checkmark=False,
                on_select=waehler(p.id),
            )
            for p in profile
        ],
    )
    steuerung = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
        controls=[
            ft.IconButton(
                ft.Icons.REPLAY, tooltip="Zurücksetzen", icon_size=28, on_click=zuruecksetzen
            ),
            ft.IconButton(
                ft.Icons.SKIP_PREVIOUS, tooltip="Abschnitt zurück", icon_size=28, on_click=zurueck
            ),
            haupt_knopf,
            ft.IconButton(
                ft.Icons.SKIP_NEXT, tooltip="Nächster Abschnitt", icon_size=28, on_click=weiter
            ),
        ],
    )
    inhalt = ft.Column(
        spacing=14,
        controls=[
            kartentitel(
                "Profil",
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED, tooltip="Profil bearbeiten", on_click=bearbeiten
                ),
                ft.IconButton(ft.Icons.ADD, tooltip="Neues Profil", on_click=neu),
            ),
            profil_chips,
            karte(
                abschnitt_text,
                zeit_text,
                fortschritt,
                stand_text,
                ft.Container(height=4),
                steuerung,
                abstand=10,
            ),
            karte(kartentitel("Ablauf"), ablauf, abstand=6),
            hinweis(
                "Der Timer läuft weiter, wenn du die Ansicht verlässt — oben in der Leiste "
                "steht dann die Restzeit. Beim Wechsel eines Abschnitts vibriert das Handy."
            ),
        ],
    )
    anzeigen()
    state.timer_beobachter["ansicht"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Timer")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


def _knopf_inhalt(icon: ft.IconData, text: str) -> ft.Control:
    return ft.Row(
        tight=True,
        spacing=8,
        controls=[ft.Icon(icon, size=26), ft.Text(text, size=18, weight=ft.FontWeight.W_600)],
    )


def _leisten_auffrischen(state: AppState) -> None:
    for name, beobachter in list(state.timer_beobachter.items()):
        if name != "ansicht":
            with contextlib.suppress(Exception):
                beobachter()


# ---------------------------------------------------------------------------
# Profil bearbeiten
# ---------------------------------------------------------------------------


def timer_bearbeiten_view(page: Any, state: AppState, profil_id: str | None, basis: str) -> ft.View:
    """Name, Abschnitte (Name + mm:ss), Runden — anlegen oder ändern."""
    zurueck_route = timer_route(basis)
    profile = state.timer_profile()
    vorhanden = next((p for p in profile if p.id == profil_id), None)
    profil = vorhanden or TimerProfil(
        name="", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=1
    )
    route = f"{zurueck_route}/bearbeiten" + (f"/{vorhanden.id}" if vorhanden else "")

    name = ft.TextField(label="Name", value=profil.name, hint_text="z. B. Intervall, Planke")
    zeilen: list[tuple[ft.TextField, ft.TextField]] = []
    zeilen_spalte = ft.Column(spacing=8)
    runden = {"n": profil.runden}
    runden_text = ft.Text(
        str(profil.runden),
        size=18,
        weight=ft.FontWeight.W_600,
        width=36,
        text_align=ft.TextAlign.CENTER,
    )
    gesamt_text = ft.Text(size=13, opacity=0.75)

    def gesamt() -> None:
        summe = sum(dauer_lesen(d.value or "") or 0 for _, d in zeilen)
        gesamt_text.value = f"Gesamt {dauer_text(summe * runden['n'])}"

    def zeichnen() -> None:
        zeilen_spalte.controls = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(expand=True, content=n),
                    ft.Container(width=96, content=d),
                    ft.IconButton(
                        ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        tooltip="Abschnitt entfernen",
                        on_click=entferner(i),
                        disabled=len(zeilen) <= 1,
                    ),
                ],
            )
            for i, (n, d) in enumerate(zeilen)
        ]
        gesamt()

    def dauer_geaendert() -> None:
        gesamt()
        with contextlib.suppress(Exception):
            gesamt_text.update()

    def zeile(a: Abschnitt) -> tuple[ft.TextField, ft.TextField]:
        return (
            ft.TextField(label="Abschnitt", value=a.name, dense=True),
            ft.TextField(
                label="mm:ss",
                value=dauer_text(a.dauer_s),
                dense=True,
                keyboard_type=ft.KeyboardType.DATETIME,
                text_align=ft.TextAlign.END,
                on_change=lambda _: dauer_geaendert(),
            ),
        )

    def entferner(i: int) -> Callable[[], None]:
        def handler() -> None:
            if len(zeilen) > 1:
                del zeilen[i]
                zeichnen()
                page.update()

        return handler

    def hinzufuegen() -> None:
        zeilen.append(zeile(Abschnitt("", 60)))
        zeichnen()
        page.update()

    def runden_aendern(delta: int) -> Callable[[], None]:
        def handler() -> None:
            runden["n"] = min(max(runden["n"] + delta, 1), MAX_RUNDEN)
            runden_text.value = str(runden["n"])
            gesamt()
            page.update()

        return handler

    async def speichern() -> None:
        abschnitte: list[Abschnitt] = []
        fehler = False
        for n, d in zeilen:
            dauer = dauer_lesen(d.value or "")
            d.error = None if dauer else "z. B. 0:30"
            fehler = fehler or dauer is None
            if dauer:
                abschnitte.append(Abschnitt((n.value or "").strip(), dauer))
        if fehler or not abschnitte:
            page.update()
            return
        neu = TimerProfil(
            id=profil.id,
            name=(name.value or "").strip() or "Timer",
            abschnitte=abschnitte,
            runden=runden["n"],
        )
        andere = [p for p in state.timer_profile() if p.id != neu.id]
        if vorhanden is not None:
            liste = [neu if p.id == neu.id else p for p in state.timer_profile()]
        else:
            liste = [*andere, neu]
        state.timer_profile_setzen(liste)
        state.timer_profil_waehlen(neu.id)
        page.show_dialog(ft.SnackBar(ft.Text(f"„{neu.name}“ gespeichert")))
        await page.push_route(zurueck_route)

    async def loeschen() -> None:
        rest = [p for p in state.timer_profile() if p.id != profil.id]
        state.timer_profile_setzen(rest)
        if state.timer is not None and state.timer.profil.id == profil.id:
            state.timer = None
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{profil.name}“ gelöscht")))
        await page.push_route(zurueck_route)

    def loeschen_fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Profil löschen?"),
                content=ft.Text(
                    "Gibt es danach kein eigenes Profil mehr, kommen die zwei Vorlagen zurück."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Löschen", on_click=loeschen),
                ],
            )
        )

    async def abbrechen() -> None:
        await page.push_route(zurueck_route)

    zeilen.extend(zeile(a) for a in profil.abschnitte)
    zeichnen()

    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text("Timer-Profil" if vorhanden else "Neues Timer-Profil"),
            actions=[
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE, tooltip="Profil löschen", on_click=loeschen_fragen
                )
            ]
            if vorhanden
            else [],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=16,
                    controls=[
                        name,
                        karte(
                            kartentitel("Abschnitte"),
                            hinweis("Je Abschnitt ein Name und die Dauer in Minuten:Sekunden."),
                            zeilen_spalte,
                            ft.TextButton(
                                "Abschnitt hinzufügen", icon=ft.Icons.ADD, on_click=hinzufuegen
                            ),
                        ),
                        karte(
                            kartentitel("Runden"),
                            ft.Row(
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.IconButton(ft.Icons.REMOVE, on_click=runden_aendern(-1)),
                                    runden_text,
                                    ft.IconButton(ft.Icons.ADD, on_click=runden_aendern(1)),
                                    ft.Container(width=8),
                                    gesamt_text,
                                ],
                            ),
                            hinweis("Alle Abschnitte so oft nacheinander."),
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = [
    "lauf_fuer",
    "ticker_starten",
    "timer_bearbeiten_view",
    "timer_knopf",
    "timer_route",
    "timer_view",
]
