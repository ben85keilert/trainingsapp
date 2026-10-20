"""Kurse — Reiter „Übungen“ → „Kurse“, Routen `/kurse/<id>` und `/kurse/<id>/<kapitel>`.

Ein Kurs (Ben, 15.10.2026; `core/kurse.py`, `docs/plan_kurse.md`) ist eine
Folge von Kapiteln, die man von oben nach unten durcharbeitet:

- **Kursliste**: jeder Kurs mit seinem Stand („noch nicht begonnen“,
  „Kapitel 3 von 7“, „abgeschlossen“).
- **Kurs**: die Kapitel untereinander — fertig ✓, übersprungen, aktuell,
  gesperrt. Antippen öffnet ein Kapitel; „Kurs beginnen“ das erste.
- **Kapitel**: Erklärtext (Markdown), Medien als Liste (öffnen im Browser wie
  bei Übungen), die Pläne des Kapitels mit „Trainieren“, der Stand der
  Bedingung („60 von 100 Wdh.“) und unten „Weiter“ — oder „Trotzdem
  freischalten“, das einmal nachfragt (`components/dialoge.Nachher`).

Ein Kapitel gilt als **erreicht**, sobald man es öffnet (das legt seine Pläne
an); **abgeschlossen** mit „Weiter“. Was man dabei übersprungen hat, bleibt als
„übersprungen“ sichtbar. Alles Rechnen steht in `core/kurse.py` und
`data/kurse.py`; hier wird nur gezeigt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

import flet as ft

from trainingsapp.core.kapiteltext import bilder_zu_links
from trainingsapp.core.kurse import (
    AKTUELL,
    FERTIG,
    FREI,
    GELESEN,
    GESPERRT,
    OFFEN,
    STRENG,
    UEBERSPRUNGEN,
    Kapitel,
    Kapitelstand,
    Kurs,
    Stand,
    bedingung_text,
    begonnen,
    fehlt_text,
    fortschritt_text,
    naechstes,
    stand_text,
    status,
)
from trainingsapp.core.models import Exercise, Media, MediaKind, Plan
from trainingsapp.core.plaene import erledigte, tage_text
from trainingsapp.ui.components.dialoge import Nachher
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.katalog import trainieren_knopf

#: Symbol und Beschriftung je Status eines Kapitels
_STATUS: dict[str, tuple[ft.IconData, str]] = {
    FERTIG: (ft.Icons.CHECK_CIRCLE, "fertig"),
    UEBERSPRUNGEN: (ft.Icons.REDO, "übersprungen"),
    AKTUELL: (ft.Icons.PLAY_CIRCLE_OUTLINE, "jetzt dran"),
    OFFEN: (ft.Icons.CIRCLE_OUTLINED, "offen"),
    GESPERRT: (ft.Icons.LOCK_OUTLINE, "gesperrt"),
}

_MEDIEN_SYMBOL: dict[MediaKind, ft.IconData] = {
    MediaKind.VIDEO: ft.Icons.PLAY_CIRCLE_OUTLINE,
    MediaKind.IMAGE: ft.Icons.IMAGE_OUTLINED,
    MediaKind.AUDIO: ft.Icons.HEADPHONES_OUTLINED,
}


def kapitel_zahl(n: int) -> str:
    """„kein Kapitel“, „1 Kapitel“, „7 Kapitel“.

    >>> [kapitel_zahl(n) for n in (0, 1, 7)]
    ['kein Kapitel', '1 Kapitel', '7 Kapitel']
    """
    return "kein Kapitel" if n == 0 else f"{n} Kapitel"


def _datum(zeit: datetime | None) -> str:
    return f"{zeit.astimezone():%d.%m.%Y}" if zeit is not None else ""


def _oeffner(page: ft.Page, pfad: str) -> Callable[[], Awaitable[None]]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


# ---------------------------------------------------------------------------
# Kursliste (im Reiter)
# ---------------------------------------------------------------------------


def kurse_liste(page: ft.Page, state: AppState) -> ft.Control:
    """Alle Kurse mit ihrem Stand — antippen öffnet den Kurs."""
    kurse = state.kurse.alle()
    staende = state.kurse.alle_staende(state.profil.id)

    def zeile(kurs: Kurs) -> ft.Control:
        stand = fortschritt_text(kurs, staende.get(kurs.id, {}))
        fertig = stand == "abgeschlossen"
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.SCHOOL if fertig else ft.Icons.SCHOOL_OUTLINED,
                color=ft.Colors.PRIMARY if fertig else None,
            ),
            title=ft.Text(kurs.name),
            subtitle=ft.Text(f"{kapitel_zahl(len(kurs.kapitel))}  ·  {stand}", size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            on_click=_oeffner(page, f"/kurse/{kurs.id}"),
        )

    if not kurse:
        return ft.Container(
            padding=24,
            content=ft.Text(
                "Noch kein Kurs. Kurse kommen mit Übungspaketen — ein Kurs führt dich "
                "Kapitel für Kapitel durch ein Thema.",
                opacity=0.7,
            ),
        )
    erklaerung = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=4),
        content=ft.Text(
            "Ein Kurs führt Kapitel für Kapitel durch ein Thema: lesen, üben, weiter. "
            "Das nächste Kapitel öffnet sich, wenn das davor geschafft ist.",
            size=12,
            opacity=0.6,
        ),
    )
    return ft.ListView(
        expand=True,
        padding=ft.Padding.only(bottom=88),
        controls=[erklaerung, *[zeile(k) for k in kurse]],
    )


# ---------------------------------------------------------------------------
# Ein Kurs
# ---------------------------------------------------------------------------


def kurs_view(page: ft.Page, state: AppState, kurs: Kurs) -> ft.View:
    """Die Kapitel untereinander mit Status; „Kurs beginnen“, Menü „Von vorn beginnen“."""
    route = f"/kurse/{kurs.id}"
    staende = state.kurse.staende(state.profil.id, kurs.id)
    stati = status(kurs, staende)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    nachher = Nachher()

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def kapitel_oeffner(kapitel: Kapitel) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            if stati[kapitel.id] == GESPERRT:
                melden("Erst das Kapitel davor abschließen — oder dort „Freischalten“ wählen.")
                return
            await page.push_route(f"{route}/{kapitel.id}")

        return handler

    async def beginnen() -> None:
        erstes = state.kurse.starten(kurs, state.profil.id)
        if erstes is not None:
            await page.push_route(f"{route}/{erstes.id}")

    def zuruecksetzen_fragen() -> None:
        def ausfuehren() -> None:
            state.kurse.zuruecksetzen(kurs, state.profil.id)
            nachher.danach(state.neu_zeichnen)
            page.pop_dialog()
            melden(f"„{kurs.name}“ beginnt von vorn")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Kurs von vorn beginnen?"),
                content=ft.Text(
                    "Dein Fortschritt in diesem Kurs wird gelöscht und die Pläne des Kurses "
                    "werden deaktiviert. Einträge im Verlauf bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Von vorn", on_click=ausfuehren),
                ],
            )
        )

    def zeile(nr: int, kapitel: Kapitel) -> ft.Control:
        s = stati[kapitel.id]
        symbol, wort = _STATUS[s]
        teile = [wort]
        if kapitel.bedingung.art != GELESEN:
            uebung = katalog.get(kapitel.bedingung.exercise_id)
            teile.append(bedingung_text(kapitel.bedingung, uebung))
        if kapitel.plaene:
            teile.append(f"{len(kapitel.plaene)} Plan" if len(kapitel.plaene) == 1 else "Pläne")
        stand = staende.get(kapitel.id)
        if stand is not None and stand.abgeschlossen is not None:
            teile.append(_datum(stand.abgeschlossen))
        gedimmt = s == GESPERRT
        return ft.ListTile(
            leading=ft.Icon(
                symbol,
                color=ft.Colors.PRIMARY if s in (FERTIG, AKTUELL) else None,
                opacity=0.45 if gedimmt else 1,
            ),
            title=ft.Text(f"{nr}. {kapitel.titel}", opacity=0.6 if gedimmt else 1),
            subtitle=ft.Text("  ·  ".join(teile), size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4) if not gedimmt else None,
            on_click=kapitel_oeffner(kapitel),
        )

    kopf: list[ft.Control] = []
    if kurs.beschreibung:
        kopf.append(ft.Text(kurs.beschreibung))
    kopf.append(
        ft.Text(
            f"{kapitel_zahl(len(kurs.kapitel))}  ·  {fortschritt_text(kurs, staende)}",
            size=12,
            opacity=0.7,
        )
    )
    if not begonnen(staende) and kurs.kapitel:
        kopf.append(ft.FilledButton("Kurs beginnen", icon=ft.Icons.PLAY_ARROW, on_click=beginnen))
    if kurs.freischaltung == STRENG:
        kopf.append(hinweis("In diesem Kurs lässt sich kein Kapitel überspringen."))
    elif kurs.freischaltung == FREI:
        kopf.append(hinweis("Alle Kapitel sind offen — die Reihenfolge ist ein Vorschlag."))

    aktionen: list[ft.Control] = []
    if begonnen(staende):
        aktionen.append(
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                items=[
                    ft.PopupMenuItem(
                        content="Von vorn beginnen",
                        icon=ft.Icons.RESTART_ALT,
                        on_click=zuruecksetzen_fragen,
                    )
                ],
            )
        )

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(kurs.name), actions=aktionen),
        scroll=ft.ScrollMode.AUTO,
        padding=ft.Padding.only(top=8, bottom=24),
        controls=[
            sicher(
                ft.Column(
                    spacing=6,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(spacing=10, controls=kopf),
                        ),
                        *[zeile(nr, k) for nr, k in enumerate(kurs.kapitel, start=1)],
                    ],
                )
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Kapitel
# ---------------------------------------------------------------------------


def kapitel_view(
    page: ft.Page, state: AppState, kurs: Kurs, kapitel: Kapitel, browser: ft.UrlLauncher
) -> ft.View:
    """Text, Medien, Pläne, Stand der Bedingung und „Weiter“ bzw. „Freischalten“.

    Öffnen heißt erreichen: Ist das Kapitel dran (oder offen), merkt die App
    das und legt seine Pläne an. ``browser`` ist der Flet-Dienst aus `main()`.
    """
    from trainingsapp.ui.views.uebungen import heute_trainieren  # Kreis: uebungen → kurse

    basis = f"/kurse/{kurs.id}"
    route = f"{basis}/{kapitel.id}"
    profil = state.profil.id
    staende = state.kurse.staende(profil, kurs.id)
    s = status(kurs, staende)[kapitel.id]
    if s in (AKTUELL, OFFEN) and kapitel.id not in staende:
        state.kurse.kapitel_erreichen(kurs, kapitel, profil)
        staende = state.kurse.staende(profil, kurs.id)
    stand_hier: Kapitelstand | None = staende.get(kapitel.id)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    uebung: Exercise | None = katalog.get(kapitel.bedingung.exercise_id)
    bedingung = kapitel.bedingung
    stand: Stand = state.kurse.stand(kapitel, profil, staende)
    folgend = naechstes(kurs, kapitel)
    nummer = kurs.kapitel.index(kapitel) + 1
    nachher = Nachher()

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    async def abschliessen(uebersprungen: bool) -> None:
        weiter = state.kurse.kapitel_abschliessen(kurs, kapitel, profil, uebersprungen)
        if weiter is not None:
            await page.push_route(f"{basis}/{weiter.id}")
        else:
            melden(f"„{kurs.name}“ abgeschlossen")
            await page.push_route(basis)

    async def weiter() -> None:
        # „frei“: kein Tor — wer weitergeht, ohne die Bedingung zu erfüllen, gilt als übersprungen
        await abschliessen(uebersprungen=not stand.erfuellt)

    def freischalten_fragen() -> None:
        """Die eine Rückfrage (Ben, 15.10.2026): was fehlt, und trotzdem?"""

        def ausfuehren() -> None:
            nachher.danach(lambda: abschliessen(uebersprungen=True))
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Trotzdem freischalten?"),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Text(
                            f"{fehlt_text(bedingung, stand, uebung)} bis „{kapitel.titel}“ "
                            "geschafft ist."
                        ),
                        ft.Text(
                            "Du kannst das nächste Kapitel trotzdem öffnen. Dieses gilt dann als "
                            "übersprungen — die Übungen laufen weiter, nichts geht verloren.",
                            size=13,
                            opacity=0.8,
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Freischalten", on_click=ausfuehren),
                ],
            )
        )

    def medium_oeffner(medium: Media) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await link_oeffnen(page, browser, medium.uri)

        return handler

    async def link(e: ft.Event[ft.Markdown]) -> None:
        """Markdown-Link im Kapiteltext — ``e.data`` ist die Adresse aus dem Paket (S1)."""
        ziel = str(getattr(e, "data", "") or "")
        if ziel:
            await link_oeffnen(page, browser, ziel)

    # -- Aufbau ---------------------------------------------------------------

    bloecke: list[ft.Control] = [
        ft.Text(f"Kapitel {nummer} von {len(kurs.kapitel)}", size=12, opacity=0.6),
        ft.Text(kapitel.titel, size=22, weight=ft.FontWeight.BOLD),
    ]
    if kapitel.text.strip():
        # Bilder laden erst nach Einschalten (S2) — bis dahin sind sie Links
        text = kapitel.text if state.kapitel_bilder() else bilder_zu_links(kapitel.text)
        bloecke.append(ft.Markdown(text, selectable=True, on_tap_link=link))

    if medien := [m for m in kapitel.media if m.uri]:
        bloecke.append(
            karte(
                titel("Zum Ansehen und Anhören"),
                *[
                    ft.ListTile(
                        leading=ft.Icon(_MEDIEN_SYMBOL.get(m.kind, ft.Icons.LINK)),
                        title=ft.Text(m.title or m.uri),
                        subtitle=ft.Text(m.uri, size=11, opacity=0.6) if m.title else None,
                        trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
                        on_click=medium_oeffner(m),
                        content_padding=ft.Padding.only(left=0, right=0),
                    )
                    for m in medien
                ],
            )
        )

    if kapitel.plaene:
        plaene: list[Plan] = state.kurse.kapitel_plaene(kapitel.id, profil)
        heute = state.heute()
        anzahl = state.sitzungen.anzahl_am_tag(profil, heute)
        zeilen: list[ft.Control] = []
        for plan in plaene:
            gemacht = len(erledigte(plan.items, anzahl))
            teile = [tage_text(plan.wochentage) if plan.aktiv else "deaktiviert"]
            if gemacht:
                teile.append(f"{gemacht} von {len(plan.items)} heute")
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(plan.name),
                    subtitle=ft.Text("  ·  ".join(teile), size=12),
                    trailing=trainieren_knopf(
                        heute_trainieren(page, state, plan.id), "Heute trainieren"
                    )
                    if s in (AKTUELL, OFFEN)
                    else None,
                    on_click=_oeffner(page, f"/plaene/{plan.id}"),
                    content_padding=ft.Padding.only(left=0, right=0),
                )
            )
        if not plaene:  # noch nicht erreicht (gesperrt): nur die Namen
            zeilen = [ft.Text("  ·  ".join(v.name for v in kapitel.plaene), opacity=0.7)]
        bloecke.append(
            karte(
                titel("Pläne dieses Kapitels"),
                hinweis(
                    "Die Pläne stehen auf „Heute“, solange das Kapitel dran ist; danach "
                    "bleiben sie deaktiviert in der Planverwaltung."
                ),
                *zeilen,
            )
        )

    if bedingung.art != GELESEN:
        fortschritt: list[ft.Control] = [
            titel("Weiter geht es, wenn"),
            ft.Text(bedingung_text(bedingung, uebung), weight=ft.FontWeight.W_600),
        ]
        if stand_hier is not None:
            fortschritt.append(
                ft.Text(
                    f"{stand_text(bedingung, stand, uebung)}  ·  "
                    f"seit {_datum(stand_hier.erreicht)}",
                    size=13,
                )
            )
            if stand.soll > 0:
                fortschritt.append(
                    ft.ProgressBar(value=min(stand.ist / stand.soll, 1.0), bar_height=6)
                )
        else:
            fortschritt.append(
                hinweis("Gezählt wird ab dem Tag, an dem du dieses Kapitel öffnest.")
            )
        bloecke.append(karte(*fortschritt))

    unten: list[ft.Control] = []
    if s in (FERTIG, UEBERSPRUNGEN):
        wann = _datum(stand_hier.abgeschlossen) if stand_hier is not None else ""
        wort = "Übersprungen" if s == UEBERSPRUNGEN else "Abgeschlossen"
        unten.append(ft.Text(f"{wort} am {wann}", opacity=0.7))
        if folgend is not None:
            unten.append(
                ft.FilledTonalButton(
                    "Nächstes Kapitel",
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=_oeffner(page, f"{basis}/{folgend.id}"),
                )
            )
    elif s == GESPERRT:
        unten.append(hinweis("Dieses Kapitel ist noch gesperrt — erst das davor abschließen."))
    elif stand.erfuellt or kurs.freischaltung == FREI:
        beschriftung = "Weiter" if folgend is not None else "Kurs abschließen"
        unten.append(ft.FilledButton(beschriftung, icon=ft.Icons.ARROW_FORWARD, on_click=weiter))
    elif kurs.freischaltung == STRENG:
        unten.append(
            ft.FilledButton("Weiter", icon=ft.Icons.ARROW_FORWARD, disabled=True),
        )
        unten.append(hinweis("Dieser Kurs lässt kein Überspringen zu."))
    else:
        unten.append(
            ft.FilledTonalButton(
                "Trotzdem freischalten", icon=ft.Icons.LOCK_OPEN, on_click=freischalten_fragen
            )
        )
    bloecke.append(ft.Row(wrap=True, spacing=10, run_spacing=8, controls=unten))

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(kurs.name)),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=14, controls=bloecke))],
    )


__all__ = ["kapitel_view", "kapitel_zahl", "kurs_view", "kurse_liste"]
