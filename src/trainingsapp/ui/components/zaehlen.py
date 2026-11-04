"""Die Zählzeile — „Wdh. zählen“ in der Karte „Eintragen“ (Ben, 4.11.2026,
``docs/plan_beschleunigung.md`` §4.1–4.3).

„Wenn ein Gerät einen Beschleunigungssensor hat, soll die Wiederholung damit gemessen werden.
Das ist der Knopf. +/-1 ist die Korrektur dafür.“

- **Vor dem Start** ein Knopf (`core.zaehlen.knopf_text`: „Wdh. zählen“, „Atmung erfassen“,
  „Wdh. zählen · Atmung“) direkt unter der Zeile der Uhr — nur ohne Nachtrag, wenn an der
  (Plan-)Übung ein Schalter der Karte „Beschleunigungssensor“ an ist (Wiederholungen nur mit
  einem Wiederholungsfeld der Planübung) und ein Gerät mit Beschleunigungssensor verbunden ist
  (`components.zaehl_stand.sichtbar`, P118). Darunter die Zählläufe von heute, deren
  Wiederholungen noch fehlen, mit „Eintragen“ (`components.laeufe_heute`) — auch an einer
  Übung ohne Uhr, und auch, wenn das Gerät nicht mehr verbunden ist.
- **Während gezählt wird** groß die Zahl, links **−1**, rechts **+1** als große Flächen (beim
  Liegestütz liegt das Handy am Boden), klein darunter „Sensor 11 · +1 · Prototyp“ bzw.
  „Sensor startet …“ und „…“. **Fertig** trägt ein, **Zählen abbrechen** nicht (der Lauf
  bleibt unter „Läufe heute“). Ein Wechsel der Ansicht beendet nichts; im zugeklappten Block
  steht die Zeile weiter da (`views/plan.py`).
- **Uhr und Zählen zugleich** (eine Einheit, `ui.uebung_lauf`): die laufende Uhr
  (`components.uhr`) und der Timer („Während“) zeigen die Zahl mit ±1 (`zahl_reihe`); die
  Zählzeile wiederholt sie dann nicht. „Fertig“ der Uhr beendet beides. Endet nur das Zählen,
  bleibt die Zahl ohne ±1 stehen.
- **Eine andere Übung** beendet ein Zählen ohne Uhr: 5 s die Meldung „Kniebeuge · 12 Wdh. nicht
  eingetragen“ mit „Eintragen“ (`meldung_zeigen`) — nie über einem offenen Dialog. Endet es von
  selbst (60 s ohne Bewegung, getrennt), kommt dieselbe Meldung mit Grund beim nächsten Aufbau
  der Ansicht („… — 60 s ohne Bewegung“, `ui.einheit._von_selbst_melden`).

Nachgezogen werden nur Texte (`components.zaehl_stand.nachziehen`, im Takt der Einheit): Ein
Tipp auf ±1 ginge verloren, entstünden die Knöpfe im Sekundentakt neu. Vor ±1 läuft
``ohne_auto_update`` (V1). Starten, Beenden und Eintragen führt `ui.uebung_lauf`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.zaehlen import ENDE_ABBRUCH, ENDE_FERTIG, knopf_text
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.dialoge import dialog_offen
from trainingsapp.ui.components.dialoge import meldung as snackbar
from trainingsapp.ui.components.laeufe_heute import zaehllaeufe_offen
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.einheit import ZaehlMeldung

#: Eckenradius wie die Knöpfe der Uhr
ECKEN = ft.RoundedRectangleBorder(radius=14)
#: Höhe der Flächen −1/+1 in der Zählzeile bzw. in Uhr und Timer (px)
FLAECHE_PX = 72
FLAECHE_KOMPAKT_PX = 52


def _schluessel(uebung: Exercise, item: PlanItem | None) -> str:
    """Wofür die Zeile steht — die Planübung, ohne Plan die Übung (wie `components.uhr`)."""
    return item.id if item is not None else uebung.id


def laeuft_hier(state: Any, uebung: Exercise, item: PlanItem | None) -> bool:
    """Zählt der Sensor gerade bei dieser (Plan-)Übung? Dann bleibt die Zeile auch im
    zugeklappten Block stehen."""
    item_id = item.id if item is not None else None
    return zaehl_stand.zaehl_teil(state, uebung.id, item_id, nur_aktiv=True) is not None


def _melden(page: Any, text: str) -> None:
    with contextlib.suppress(Exception):
        page.show_dialog(ft.SnackBar(ft.Text(text)))


def meldung_zeigen(page: Any, state: Any, meldung: ZaehlMeldung | None = None) -> bool:
    """„Kniebeuge · 12 Wdh. nicht eingetragen“ mit „Eintragen“, 5 s (`dialoge.meldung`) —
    ``meldung`` oder die, die ein Start eben hinterließ (`ui.uebung_lauf.meldung_abholen`).

    Nie über einem offenen Dialog (`page.pop_dialog` träfe sonst die Meldung): dann bleibt
    sie liegen, und der nächste Aufbau der Ansicht zeigt sie (`ui.app`). ``True``: gezeigt."""
    if meldung is None:
        meldung = uebung_lauf.meldung_abholen(state)
    if meldung is None:
        return False
    if dialog_offen(page):
        state.zaehl_meldung = meldung
        return False
    gemeldet = meldung

    def eintragen() -> None:
        eintrag = uebung_lauf.lauf_eintragen(state, gemeldet.einheit_id)
        _melden(
            page,
            f"{gemeldet.name}: {eintrag.shorthand() or 'gemacht'}"
            if eintrag is not None
            else "Schon eingetragen.",
        )
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    with contextlib.suppress(Exception):
        page.show_dialog(snackbar(gemeldet.text, eintragen, aktion="Eintragen"))
        return True
    return False


def _flaeche(delta: int, hoehe: int, on_click: Callable[[], None]) -> ft.Control:
    """Eine große Fläche −1 bzw. +1 — man trifft sie auch vom Boden aus."""
    return ft.Container(
        expand=True,
        height=hoehe,
        border_radius=14,
        ink=True,
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        alignment=ft.Alignment.CENTER,
        tooltip="Eine Wiederholung mehr" if delta > 0 else "Eine Wiederholung weniger",
        content=ft.Text(
            "+1" if delta > 0 else "−1",
            size=26 if hoehe >= FLAECHE_PX else 20,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
        ),
        on_click=on_click,
    )


def _korrigierer(state: Any, uebung_id: str, item_id: str | None, delta: int) -> Callable[[], None]:
    def handler() -> None:
        ohne_auto_update()  # V1: nur die Zahl zeichnet sich neu, nicht die Seite
        zaehl_stand.korrigieren(state, uebung_id, item_id, delta)

    return handler


def zahl_reihe(
    page: Any,
    state: Any,
    z: ZaehlBaustein,
    uebung_id: str,
    item_id: str | None,
    *,
    name: str,
    kompakt: bool = True,
) -> ft.Control:
    """Die Zahl mit −1/+1 und der kleinen Zeile — in der laufenden Uhr und im Timer
    (``kompakt``) und in der Zählzeile. Angemeldet unter ``name`` (`zaehl_stand.anmelden`):
    die Einheit zieht Zahl und Zeile nach, die Flächen bleiben. Zählt der Sensor nicht mehr
    (abgebrochen, keine Bewegung — die Uhr läuft weiter), gibt es keine Flächen: ±1 ginge ins
    Leere (`zaehl_stand.korrigieren` korrigiert nur, solange gezählt wird)."""
    zahl = ft.Text(
        zaehl_stand.zahl_text(z),
        size=34 if kompakt else 56,
        weight=ft.FontWeight.BOLD,
        text_align=ft.TextAlign.CENTER,
        visible=z.wdh,  # nur Atmung: in A1 ohne Zahl (Prototyp folgt)
    )
    klein = ft.Text(
        zaehl_stand.klein_text(z),
        size=11 if kompakt else 12,
        opacity=0.8,
        text_align=ft.TextAlign.CENTER,
    )
    zaehl_stand.anmelden(state, name, zaehl_stand.ZaehlAnzeige(uebung_id, item_id, zahl, klein))
    mitte = ft.Column(
        spacing=0,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[zahl, klein],
    )
    if not z.wdh or not z.aktiv:
        return ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[mitte])
    hoehe = FLAECHE_KOMPAKT_PX if kompakt else FLAECHE_PX
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            _flaeche(-1, hoehe, _korrigierer(state, uebung_id, item_id, -1)),
            ft.Container(expand=True, alignment=ft.Alignment.CENTER, content=mitte),
            _flaeche(+1, hoehe, _korrigierer(state, uebung_id, item_id, +1)),
        ],
    )


def neben_der_uhr(
    page: Any, state: Any, e: Any, uebung_id: str, item_id: str | None, *, name: str
) -> list[ft.Control]:
    """Für die laufende Uhr und den Timer: Zählt in ihrer Einheit der Sensor dieselbe Übung,
    die Zahl mit ±1 und „Zählen abbrechen“ (die Uhr läuft weiter); endete das Zählen schon,
    nur noch die Zahl und warum — sonst nichts."""
    z = e.teil("zaehlen") if e is not None else None
    if not isinstance(z, ZaehlBaustein) or not zaehl_stand.passt(z.kontext, uebung_id, item_id):
        return []
    reihe = zahl_reihe(page, state, z, uebung_id, item_id, name=name, kompakt=True)
    if not z.aktiv:
        return [reihe]

    def abbrechen() -> None:
        uebung_lauf.zaehlen_beenden(state, uebung_id, item_id, ENDE_ABBRUCH)
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    return [
        reihe,
        ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[
                ft.TextButton(
                    "Zählen abbrechen",
                    icon=ft.Icons.DO_NOT_DISTURB_ON_OUTLINED,
                    tooltip="Nur das Zählen beenden — die Uhr läuft weiter, die Wiederholungen "
                    "lassen sich später eintragen",
                    on_click=abbrechen,
                )
            ],
        ),
    ]


def _laufend(
    page: Any, state: Any, uebung: Exercise, item_id: str | None, z: ZaehlBaustein, name: str
) -> ft.Control:
    """Die laufende Zählzeile: Kopf mit „Prototyp“, Zahl mit ±1, „Fertig“, „Zählen abbrechen“."""

    def beenden(grund: str) -> Callable[[], None]:
        def handler() -> None:
            uebung_lauf.zaehlen_beenden(state, uebung.id, item_id, grund)
            with contextlib.suppress(Exception):
                state.neu_zeichnen()

        return handler

    return ft.Container(
        padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
        border_radius=16,
        border=ft.Border.all(1.5, ft.Colors.PRIMARY),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.SENSORS, size=18, opacity=0.85),
                        ft.Text(knopf_text(z.wdh, z.atem), size=14, opacity=0.85, expand=True),
                        ft.Text("Prototyp", size=11, italic=True, opacity=0.7),
                    ],
                ),
                zahl_reihe(page, state, z, uebung.id, item_id, name=name, kompakt=False),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledButton(
                            content=ft.Row(
                                tight=True,
                                spacing=6,
                                controls=[ft.Icon(ft.Icons.CHECK, size=18), ft.Text("Fertig")],
                            ),
                            height=48,
                            expand=True,
                            style=ft.ButtonStyle(shape=ECKEN),
                            tooltip="Zählen beenden und eintragen",
                            on_click=beenden(ENDE_FERTIG),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                tight=True,
                                spacing=6,
                                controls=[
                                    ft.Icon(ft.Icons.DO_NOT_DISTURB_ON_OUTLINED, size=18),
                                    ft.Text("Zählen abbrechen"),
                                ],
                            ),
                            height=48,
                            expand=True,
                            style=ft.ButtonStyle(shape=ECKEN),
                            tooltip="Zählen beenden — trägt nichts ein, bleibt unter „Läufe heute“",
                            on_click=beenden(ENDE_ABBRUCH),
                        ),
                    ],
                ),
            ],
        ),
    )


def _vorher(
    page: Any, state: Any, uebung: Exercise, plan: Plan | None, item: PlanItem | None
) -> ft.Control:
    """Der Knopf — und was heute abgebrochen und noch nicht eingetragen ist."""
    key = _schluessel(uebung, item)

    def kontext() -> Any:
        wahl = uebung_lauf.gewaehlte_ausfuehrung(state, uebung, item)
        zaehlt = state.uhr_zaehlt.get(key, uebung.zeit_zaehlt)
        return uebung_lauf.kontext_fuer(uebung, plan, item, zeit_eintragen=zaehlt, auspraegung=wahl)

    def los() -> None:
        try:
            _, meldung = uebung_lauf.zaehlen_starten(
                page, state, kontext(), uebung=uebung, item=item
            )
        except RuntimeError as fehler:
            _melden(page, str(fehler))
            return
        meldung_zeigen(page, state, meldung)

    knopf = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.OutlinedButton(
                content=ft.Row(
                    tight=True,
                    spacing=6,
                    controls=[
                        ft.Icon(ft.Icons.SENSORS, size=18),
                        ft.Text(zaehl_stand.knopf(uebung, item)),
                    ],
                ),
                height=44,
                expand=True,
                style=ft.ButtonStyle(shape=ECKEN),
                tooltip="Der Beschleunigungssensor zählt ab jetzt — ±1 korrigiert",
                on_click=los,
            ),
            ft.Text("Prototyp", size=11, italic=True, opacity=0.7),
        ],
    )
    offen = zaehllaeufe_offen(page, state, uebung, _neu_zeichnen(state))
    if not offen:
        return knopf
    return ft.Column(spacing=6, tight=True, controls=[knopf, *offen])


def _neu_zeichnen(state: Any) -> Callable[[], None]:
    def handler() -> None:
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    return handler


def _nur_offene(page: Any, state: Any, uebung: Exercise) -> ft.Control | None:
    """Ohne Gerät mit Beschleunigungssensor kein Knopf — aber die Zählläufe von heute, deren
    Wiederholungen noch fehlen, lassen sich weiter eintragen (der Gurt ist ab, getrennt oder
    leer; an einer Übung ohne Uhr gibt es keinen anderen Ort dafür)."""
    offen = zaehllaeufe_offen(page, state, uebung, _neu_zeichnen(state))
    if not offen:
        return None
    return ft.Column(spacing=6, tight=True, controls=offen)


def zaehl_zeile(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan | None,
    item: PlanItem | None,
    nachtrag: Any = None,
    neben_uhr: bool = False,
) -> ft.Control | None:
    """Die Zählzeile einer (Plan-)Übung — ``None``, wenn es sie hier nicht gibt.

    ``uebung`` ist die Übung aus dem Katalog (die Planübung liest ``item``, ohne Plan
    ``None``). ``neben_uhr``: Die Karte zeigt gerade die laufende Uhr dieser Übung — zählt der
    Sensor in ihrer Einheit, steht die Zahl dort (`neben_der_uhr`), nicht noch einmal hier.
    """
    if nachtrag is not None:
        return None
    item_id = item.id if item is not None else None
    name = f"eintragen:{_schluessel(uebung, item)}"
    z = zaehl_stand.zaehl_teil(state, uebung.id, item_id)
    if z is not None:
        e = einheit_ui.laeuft(state)
        if neben_uhr and e is not None and e.timer is not None:
            zaehl_stand.abmelden(state, name)
            return None
        if z.aktiv:
            return _laufend(page, state, uebung, item_id, z, name)
        # Das Zählen ist vorbei, die Uhr der Einheit läuft weiter: ein zweites gibt es in
        # diesem Lauf nicht (`ui.uebung_lauf.zaehlen_starten`)
        zaehl_stand.abmelden(state, name)
        return ft.Text(zaehl_stand.klein_text(z), size=12, opacity=0.75)
    zaehl_stand.abmelden(state, name)
    if not zaehl_stand.sichtbar(state, uebung, item=item):
        # Nur wo gezählt werden kann, wird nachgesehen (ein Blick in die Zeitleiste je Block)
        return _nur_offene(page, state, uebung) if zaehl_stand.zaehlen_an(uebung, item) else None
    return _vorher(page, state, uebung, plan, item)


__all__ = [
    "laeuft_hier",
    "meldung_zeigen",
    "neben_der_uhr",
    "zaehl_zeile",
    "zahl_reihe",
]
