"""Verlauf (Ben, 17.10.2026; Skizzen 1 und 5 zu P37: Variante A + B).

Drei Reiter:

- **Tage**: oben eine Woche (‹ ›, auch wischen), unter jedem Tag Punkte für die Zahl der
  Übungen, heute mit Ring. Ein Tipp auf einen Tag zeigt darunter den Tag **nach der Uhr**
  (Ben, 12.11.2026, `docs/plan_notizen_reiter.md` §3): Übungen (Wert, Sätze, Mini-Kurve, ihr
  Plan als Etikett), Tagesfelder „mehrmals“ an ihrer Uhrzeit, Workouts mit dem, was zu ihnen
  eingetragen ist. Nur Zahlen — Geschriebenes steht im Reiter „Notizen“; hier trägt die Zeile
  ein Notiz-Zeichen, und „n Notizen zum Tag“ springt dorthin. „Tag öffnen“ führt in die
  Tagesansicht.
- **Übungen**: alle Übungen, die zuletzt gemachten zuerst, mit Mini-Kurve, letztem Wert
  und Trend (Mittel der letzten vier Wochen gegen die vier davor); oben Suchfeld und
  Filter wie im Katalog (Typ · Region · Paket, `components/uebungsfilter.py` — Ben,
  12.11.2026: „einheitlich mit der übrigen Übungsauswahl“).

- **Notizen** (Ben, 18.10.2026 als „Tagebuch“, seit 12.11.2026 „Notizen“): alles Geschriebene
  nach Tagen, mit Suche, Filter und der Schnellwahl „Tagebuch“ (`views/tagebuch.py`).

Eine Übung antippen öffnet `/verlauf/<kachel_id>` (`verlauf_kachel.py`): ihre Kurve und
die Ergebnisse je Tag — jede Übung ist eine Kachel (`core/tagesbilanz`). Gerechnet wird in
`core/verlauf.py`; HRV-Messungen stehen bewusst nicht hier (Ben: ohne feste
Randbedingungen wenig aussagekräftig, P39).

**Einmal lesen, in der Spalte auffrischen** (N23, 19.10.2026): Die Einträge aller Tage
(`_Daten`) werden je Aufbau der Ansicht einmal gelesen und gehalten. Tag wählen, Woche
blättern, Suchen und Filtern und der Reiterwechsel ersetzen nur den Inhalt ihrer Spalte
(`control.update()`) — kein `neu_zeichnen`, keine neue Abfrage. Ändert sich der Bestand
(Nachtragen, Löschen, Leistungen-Blatt), geschieht das auf einer anderen Route oder in
einem Dialog, nach dem die App den Stapel ohnehin neu baut — dann wird neu gelesen.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core import varianten as var
from trainingsapp.core.models import Exercise, SessionEntry, lokaler_tag
from trainingsapp.core.uebungsfilter import paket_wahl
from trainingsapp.core.verlauf import (
    WOCHENTAGE,
    haeufigkeit,
    ist_neu,
    je_tag_der_woche,
    kennzahlen,
    kuerzlich,
    montag,
    tag_titel,
    tageswerte,
    tageszeilen,
    trend,
    wochen_titel,
)
from trainingsapp.core.workout_eintrag import WorkoutZeile
from trainingsapp.ui.components import ziele as zl
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.uebungsfilter import FilterLeiste
from trainingsapp.ui.components.uebungszeile import abschnitt, grosser_wert, uebungszeile
from trainingsapp.ui.components.varianten import etikett as varianten_etikett
from trainingsapp.ui.components.verlaufskurve import mini, mini_saeulen
from trainingsapp.ui.components.wochenleiste import tageszelle
from trainingsapp.ui.components.zeitstrahl import zeitpunkt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.tagebuch import tagebuch
from trainingsapp.ui.views.ziele import tagesfeld_ziele, ziele_fuer

#: So viele Werte zeigt eine Mini-Kurve
MINI_WERTE = 8
#: Die Reiter (`AppState.verlauf_tab`): 0 Tage, 1 Übungen, 2 Zum Tag (Tagesfelder, Ben
#: 21.10.2026: „E1 gut“ — eigener Reiter), 3 Notizen (bis 12.11.2026 „Tagebuch“)
ZUM_TAG, TAGEBUCH = 2, 3
#: „13× in 6 Wochen“ — so weit zählt die Liste der Übungen zurück
UEBUNGEN_WOCHEN = 6


@dataclass(slots=True)
class _Daten:
    """Alles, was beide Reiter brauchen — einmal je Aufbau gelesen."""

    heute: date
    katalog: dict[str, Exercise]
    namen: dict[str, str]
    #: alle gültigen Einträge bis heute, zeitlich sortiert, mit ihrem lokalen Tag
    eintraege: list[tuple[date, SessionEntry]]
    #: dieselben je Kachel (Varianten zusammen)
    je_kachel: dict[str, list[tuple[date, SessionEntry]]]
    #: Tagesfelder (auch ausgeschaltete und gelöschte) und alle ihre Werte bis heute
    felder: dict[str, tf.Tagesfeld] = field(default_factory=dict)
    werte: list[tf.Tageswert] = field(default_factory=list)
    #: Workouts, zu denen etwas eingetragen ist (Anstrengung, Skala, Notiz)
    workouts: list[WorkoutZeile] = field(default_factory=list)


def _daten(state: AppState) -> _Daten:
    heute = state.heute()
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    eintraege = state.sitzungen.eintraege_zwischen(state.profil.id, None, heute)
    daten = _Daten(
        heute,
        katalog,
        {k: u.name for k, u in katalog.items()},
        eintraege,
        {},
        {f.id: f for f in state.tagesfelder.alle(state.profil.id, mit_geloeschten=True)},
        state.tageswerte.zwischen(state.profil.id, None, heute),
        state.einheiten.workout_zeilen(state.profil.id, mit_leeren=True)
        if state.einheiten is not None
        else [],
    )
    for tag, e in eintraege:
        daten.je_kachel.setdefault(e.exercise_id, []).append((tag, e))
    return daten


def kurz_datum(tag: date, heute: date) -> str:
    """„heute“, „gestern“, sonst „Fr 16.10.“.

    >>> heute = date(2026, 10, 17)
    >>> kurz_datum(date(2026, 10, 16), heute), kurz_datum(date(2026, 10, 9), heute)
    ('gestern', 'Fr 09.10.')
    """
    if tag == heute:
        return "heute"
    if tag == heute - timedelta(days=1):
        return "gestern"
    return f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"


def _zeigen(control: ft.Control) -> None:
    """Ein Control neu zeichnen — außerhalb einer laufenden App (Tests) ohne Fehler."""
    with contextlib.suppress(Exception):
        control.update()


def verlauf(page: ft.Page, state: AppState) -> ft.Control:
    """Der Reiter „Verlauf“: Tage | Übungen | Zum Tag | Notizen."""
    #: die Daten dieses Aufbaus — gelesen beim ersten Bedarf, neu nur am nächsten Tag
    halter: list[_Daten] = []

    def daten() -> _Daten:
        if not halter or halter[0].heute != state.heute():
            halter[:] = [_daten(state)]
        return halter[0]

    inhalt = ft.Container(expand=True)

    def fuellen() -> None:
        if state.verlauf_tab == TAGEBUCH:
            inhalt.content = tagebuch(page, state)
        elif state.verlauf_tab == 0:
            inhalt.content = _tage(page, state, daten)
        elif state.verlauf_tab == ZUM_TAG:
            inhalt.content = _zum_tag(page, state, daten)
        else:
            inhalt.content = _uebungen(page, state, daten)

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.verlauf_tab = e.control.selected_index or 0
        fuellen()
        _zeigen(inhalt)

    fuellen()
    return ft.Tabs(
        length=4,
        selected_index=min(state.verlauf_tab, TAGEBUCH),
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    scrollable=False,
                    tabs=[
                        ft.Tab(label="Tage"),
                        ft.Tab(label="Übungen"),
                        ft.Tab(label="Zum Tag"),
                        ft.Tab(label="Notizen"),
                    ],
                ),
                inhalt,
            ],
        ),
    )


def _oeffner(page: ft.Page, pfad: str) -> Callable[[], object]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


# ---------------------------------------------------------------------------
# Reiter „Tage“: Woche und Tag
# ---------------------------------------------------------------------------


def _gewaehlter_tag(gewaehlt: date | None, woche: list[date], heute: date, mit: list[date]) -> date:
    """Der gezeigte Tag: der gewählte, sonst heute (wenn heute etwas eingetragen ist oder die
    Woche sonst leer), sonst der letzte Tag der Woche mit Einträgen.

    >>> w = [date(2026, 10, 12) + timedelta(days=i) for i in range(7)]
    >>> heute = date(2026, 10, 17)
    >>> _gewaehlter_tag(None, w, heute, [date(2026, 10, 12), date(2026, 10, 16)])
    datetime.date(2026, 10, 16)
    >>> _gewaehlter_tag(None, w, heute, []), _gewaehlter_tag(date(2026, 10, 13), w, heute, [])
    (datetime.date(2026, 10, 17), datetime.date(2026, 10, 13))
    """
    if gewaehlt is not None and gewaehlt in woche:
        return gewaehlt
    if heute in woche and (heute in mit or not mit):
        return heute
    return mit[-1] if mit else min(heute, woche[0])


def _tage(page: ft.Page, state: AppState, daten: Callable[[], _Daten]) -> ft.Control:
    """Die Spalte „Tage“ — ein Tipp füllt nur ihren Inhalt neu."""
    inhalt = ft.Column(spacing=8)

    def auffrischen() -> None:
        inhalt.controls = _tage_inhalt(page, state, daten(), auffrischen)
        _zeigen(inhalt)

    inhalt.controls = _tage_inhalt(page, state, daten(), auffrischen)
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=inhalt,
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_tage", spalte)


def _tage_inhalt(
    page: ft.Page, state: AppState, daten: _Daten, auffrischen: Callable[[], None]
) -> list[ft.Control]:
    """Wochenstreifen und die Übungen des gewählten Tages."""
    heute = daten.heute
    jetzt = montag(heute)
    beginn = state.verlauf_woche or jetzt
    woche = [beginn + timedelta(days=i) for i in range(7)]
    uebungen_je_tag = je_tag_der_woche(daten.eintraege, beginn)
    mit_werten = {w.tag for w in daten.werte if woche[0] <= w.tag <= woche[-1]}
    tag = _gewaehlter_tag(
        state.verlauf_tag, woche, heute, sorted(set(uebungen_je_tag) | mit_werten)
    )

    def woche_zeigen(neu: date) -> None:
        state.verlauf_woche = None if neu == jetzt else neu
        state.verlauf_tag = None
        auffrischen()

    def blaettern(schritt: int) -> Callable[[], None]:
        def handler() -> None:
            ziel = beginn + timedelta(days=7 * schritt)
            if ziel <= jetzt:
                woche_zeigen(ziel)

        return handler

    def gewischt(e: ft.DragEndEvent) -> None:
        geschwindigkeit = e.primary_velocity or 0
        if geschwindigkeit > 300:
            blaettern(-1)()
        elif geschwindigkeit < -300:
            blaettern(1)()

    def waehler(t: date) -> Callable[[], None]:
        def handler() -> None:
            state.verlauf_tag = t
            auffrischen()

        return handler

    def zelle(t: date) -> ft.Control:
        n = len(uebungen_je_tag.get(t, ()))
        return tageszelle(
            t,
            heute=heute,
            gewaehlt=t == tag,
            anzahl=n or int(t in mit_werten),
            punkte=min(n, 3),
            on_click=waehler(t),
            tooltip=f"{tag_titel(t)}: {n} Übungen" if n else None,
            heute_wort=True,
            raute=t in mit_werten,
        )

    trainingstage = len(uebungen_je_tag)
    unterzeile: list[ft.Control] = [
        ft.Text(
            f"Woche {beginn.isocalendar().week} · {trainingstage} "
            + ("Trainingstag" if trainingstage == 1 else "Trainingstage"),
            size=12,
            opacity=0.7,
        )
    ]
    if beginn != jetzt:
        unterzeile.append(
            ft.TextButton(
                "Heute",
                on_click=lambda: woche_zeigen(jetzt),
                style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
            )
        )
    streifen = ft.GestureDetector(
        on_horizontal_drag_end=gewischt,
        content=ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=18,
            padding=ft.Padding.only(left=6, right=6, top=6, bottom=10),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                ft.Icons.CHEVRON_LEFT,
                                tooltip="Vorige Woche",
                                on_click=blaettern(-1),
                            ),
                            ft.Column(
                                spacing=0,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        wochen_titel(beginn), size=16, weight=ft.FontWeight.W_700
                                    ),
                                    ft.Row(
                                        spacing=4,
                                        tight=True,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=unterzeile,
                                    ),
                                ],
                            ),
                            ft.IconButton(
                                ft.Icons.CHEVRON_RIGHT,
                                tooltip="Nächste Woche",
                                on_click=blaettern(1),
                                disabled=beginn >= jetzt,
                            ),
                        ],
                    ),
                    ft.Row(spacing=4, controls=[zelle(t) for t in woche]),
                ],
            ),
        ),
    )

    eintraege_des_tags = [e for t, e in daten.eintraege if t == tag]
    zeilen = tageszeilen(eintraege_des_tags, daten.namen)
    anzahl = f"{len(zeilen)} {'Übung' if len(zeilen) == 1 else 'Übungen'}"
    controls: list[ft.Control] = [
        streifen,
        abschnitt(
            f"{tag_titel(tag)} · {anzahl}",
            ft.TextButton("Tag öffnen", on_click=_oeffner(page, f"/tag/{tag.isoformat()}")),
        ),
    ]
    werte_des_tags = [w for w in daten.werte if w.tag == tag]
    workouts = [w for w in daten.workouts if lokaler_tag(w.beginn) == tag]
    notizen = sum(1 for n in state.tagesnotizen.zum_tag(state.profil.id, tag) if n.text.strip())
    if notizen:
        controls.append(_notizen_zeile(state, tag, notizen))
    # Ohne Uhrzeit oben: was „einmal am Tag“ gilt und die Texte der Felder
    controls.extend(_tageswerte(page, daten, werte_des_tags, mehrmals=False))
    if not zeilen and not werte_des_tags and not workouts and not notizen:
        controls.append(
            ft.Container(
                padding=ft.Padding.only(left=4, top=4),
                content=ft.Text("An diesem Tag ist nichts eingetragen.", opacity=0.7),
            )
        )
    #: der Tag nach der Uhr: (Zeit, Zeile) — Übungen, Tagesfelder „mehrmals“, Workouts
    nach_uhr: list[tuple[datetime | None, ft.Control]] = []
    plan_namen: dict[str, str] = {}

    def plan_von(e: SessionEntry) -> str:
        """Der Name des Plans, in dem der Eintrag gemacht wurde — leer ohne Plan."""
        if e.session_id not in plan_namen:
            session = state.sitzungen.session_laden(e.session_id)
            plan = (
                state.plaene.laden(session.plan_id, mit_geloeschten=True)
                if session is not None and session.plan_id
                else None
            )
            plan_namen[e.session_id] = plan.name if plan is not None else ""
        return plan_namen[e.session_id]

    for z in zeilen:
        uebung = daten.katalog.get(z.kachel_id)
        eigene = [
            e
            for e in eintraege_des_tags
            if e.exercise_id == z.kachel_id and var.von(e.result) == z.variante
        ]
        unter: list[ft.Control] = [ft.Text(z.zeile, size=12, opacity=0.75)]
        if z.zusatz:
            unter.append(ft.Text(z.zusatz, size=11, opacity=0.6))
        if any(e.note.strip() for e in eigene):
            unter.append(_notiz_zeichen("Notiz dazu im Reiter „Notizen“"))
        rechts: list[ft.Control] = []
        if z.kennzahl is not None and z.wert is not None:
            # Die Mini-Kurve dieser Variante — 400 kurze sind etwas anderes als 400 lange
            bisher = [
                (t, e)
                for t, e in daten.je_kachel.get(z.kachel_id, [])
                if t <= tag and var.von(e.result) == z.variante
            ]
            werte = [w for _, w in tageswerte(bisher, z.kennzahl)][-MINI_WERTE:]
            rechts = [grosser_wert(z.kennzahl.text(z.wert), z.kennzahl.einheit), mini(werte)]
        plaene = list(dict.fromkeys(name for e in eigene if (name := plan_von(e))))
        nach_uhr.append(
            (
                min((e.started_at for e in eigene if e.started_at), default=None),
                uebungszeile(
                    symbol_key=uebung.icon_key if uebung else None,
                    titel=uebung.name if uebung else "?",
                    unter=unter,
                    rechts=rechts,
                    on_click=None,
                    etiketten=plaene,
                    variante=_schild(uebung, z.variante),
                    # Tipp = Kurve; Symbol oder Gedrückthalten = alle Wege (Ben, 28.10.2026)
                    ziel=zl.Ziel(zl.VERLAUF, _oeffner(page, f"/verlauf/{z.kachel_id}")),
                    weitere=ziele_fuer(
                        page,
                        state,
                        z.kachel_id,
                        tag=tag,
                        hier={zl.VERLAUF},
                        danach=state.neu_zeichnen,  # das Blatt ändert Einträge: neu lesen
                    ),
                    page=page,
                    blatt_untertitel=f"{tag:%d.%m.%Y}",
                ),
            )
        )
    for _feld, eigene_werte, zeile in _feldzeilen(page, daten, werte_des_tags, mehrmals=True):
        karte = ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST, border_radius=14, content=zeile
        )
        nach_uhr.append((min(w.zeit for w in eigene_werte), karte))
    nach_uhr.extend((w.beginn, _workout_zeile(page, w)) for w in workouts)
    nach_uhr.sort(key=lambda x: (x[0] is None, x[0].timestamp() if x[0] else 0.0))
    controls.append(
        ft.Column(
            spacing=0,
            controls=[
                zeitpunkt(f"{zeit.astimezone():%H:%M}" if zeit is not None else "", zeile)
                for zeit, zeile in nach_uhr
            ],
        )
    )
    if any(z.kennzahl is not None for z in zeilen):
        controls.append(
            ft.Text(
                "Mini-Kurve: die letzten Male dieser Übung, der Punkt ist dieser Tag. "
                "Antippen öffnet die Kurve; das Symbol oder Gedrückthalten zeigt alle Wege.",
                size=11,
                opacity=0.6,
            )
        )
    return controls


def _notiz_zeichen(hinweis: str) -> ft.Control:
    """Das Zeichen „hierzu ist etwas geschrieben“ — der Text selbst steht in „Notizen“."""
    return ft.Icon(ft.Icons.EDIT_NOTE, size=16, opacity=0.6, tooltip=hinweis)


def _notizen_zeile(state: AppState, tag: date, anzahl: int) -> ft.Control:
    """„2 Notizen zum Tag“ — der Tipp öffnet den Reiter „Notizen“ an diesem Tag."""

    def oeffnen() -> None:
        state.verlauf_tab = TAGEBUCH
        state.tagebuch_filter.leeren()
        state.tagebuch_suche = ""
        state.tagebuch_sprung = tag
        state.neu_zeichnen()

    return ft.Container(
        ink=True,
        on_click=oeffnen,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.EDIT_NOTE, size=18, opacity=0.7),
                ft.Text(
                    "1 Notiz zum Tag" if anzahl == 1 else f"{anzahl} Notizen zum Tag",
                    size=13,
                    expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.6),
            ],
        ),
    )


def _workout_zeile(page: ft.Page, w: WorkoutZeile) -> ft.Control:
    """Ein Workout des Tags mit dem, was zu ihm eingetragen ist — der Tipp öffnet den
    Workout-Eintrag (dort „Alle Durchläufe“). Seit 12.11.2026 der Ort für Workouts ohne
    Notiz, die nicht mehr im Reiter „Notizen“ stehen. **Jedes Workout steht da, die
    Anstrengung dahinter** — „—“, solange keine eingetragen ist (Ben, 13.11.2026); seine
    Übungen bleiben eigene Zeilen, damit sie sich bei der Übung sammeln."""
    text = w.werte.werte_text()
    if w.werte.srpe is None:
        text = " · ".join(t for t in ("Anstrengung —", text) if t)
    teile: list[ft.Control] = [
        ft.Text(f"Workout {w.name}".strip(), size=15),
        ft.Text(text, size=12, opacity=0.75),
    ]
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        border_radius=14,
        ink=True,
        on_click=_oeffner(page, f"/workout/{w.einheit_id}"),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        content=ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.PLAYLIST_PLAY, size=22, opacity=0.8),
                ft.Column(spacing=0, tight=True, expand=True, controls=teile),
                *([_notiz_zeichen("Notiz zum Workout")] if w.werte.note.strip() else []),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.6),
            ],
        ),
    )


def _feldzeilen(
    page: ft.Page, daten: _Daten, werte: list[tf.Tageswert], *, mehrmals: bool
) -> list[tuple[tf.Tagesfeld, list[tf.Tageswert], ft.Control]]:
    """Je Tagesfeld mit Werten an diesem Tag eine Zeile (Feld, seine Werte, die Zeile);
    antippen öffnet das Feld im Verlauf. ``mehrmals``: die Felder mit Uhrzeit (stehen in der
    Liste nach der Uhr) — sonst die „einmal am Tag“ und die Texte (stehen oben)."""
    zeilen: list[tuple[tf.Tagesfeld, list[tf.Tageswert], ft.Control]] = []
    for feld in daten.felder.values():
        eigene = [w for w in werte if w.feld_id == feld.id]
        ist_text = feld.art == tf.TEXT
        if not eigene or (feld.mehrmals and not ist_text) != mehrmals:
            continue
        stand = tf.stand_text(feld, tf.tagesstand(feld, eigene))
        # Bis drei Uhrzeiten, sonst wie oft („6×“) — Trinken hat schnell ein Dutzend
        uhren = ""
        if feld.mehrmals and not ist_text:
            zeiten = sorted(w.zeit for w in eigene)
            uhren = (
                " · ".join(f"{z.astimezone():%H:%M}" for z in zeiten)
                if len(zeiten) <= 3
                else f"{len(zeiten)}×"
            )
            if len(zeiten) == 1:
                uhren = ""  # die eine Uhrzeit steht schon links am Zeitstrahl
        zeile = ft.Container(
            ink=True,
            on_click=_oeffner(page, f"/verlauf/tagesfeld/{feld.id}"),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(feld.name, size=14),
                            *(
                                [ft.Text(stand, size=12, opacity=0.75, max_lines=2)]
                                if ist_text
                                else []
                            ),
                        ],
                    ),
                    *([ft.Text(uhren, size=11, opacity=0.65)] if uhren else []),
                    *([] if ist_text else [ft.Text(stand, size=15, weight=ft.FontWeight.W_700)]),
                ],
            ),
        )
        zeilen.append((feld, eigene, zeile))
    return zeilen


def _tageswerte(
    page: ft.Page, daten: _Daten, werte: list[tf.Tageswert], *, mehrmals: bool
) -> list[ft.Control]:
    """Reiter „Tage“: die Tagesfelder ohne Uhrzeit als Block „Zum Tag“ über dem Tag (Skizze
    C1) — je Feld eine Zeile. Ein Feld mit Notiz am Wert trägt das Notiz-Zeichen nicht: Der
    Text der Felder steht hier schon in der Zeile."""
    zeilen = [zeile for *_, zeile in _feldzeilen(page, daten, werte, mehrmals=mehrmals)]
    if not zeilen:
        return []
    return [
        ft.Text("ZUM TAG", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border_radius=14,
            content=ft.Column(spacing=0, controls=zeilen),
        ),
    ]


# ---------------------------------------------------------------------------
# Reiter „Zum Tag“: die Tagesfelder mit Mini-Kurve (Skizze C2)
# ---------------------------------------------------------------------------


def _zum_tag(page: ft.Page, state: AppState, daten: Callable[[], _Daten]) -> ft.Control:
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=ft.Column(spacing=8, controls=_zum_tag_inhalt(page, state, daten())),
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_zum_tag", spalte)


def _zum_tag_inhalt(page: ft.Page, state: AppState, daten: _Daten) -> list[ft.Control]:
    """Je Tagesfeld eine Zeile: Stand des letzten Tags, Mini-Kurve bzw. -Säulen; darunter
    ausgeschaltete und gelöschte, deren Einträge geblieben sind."""
    heute = daten.heute
    je_feld: dict[str, list[tf.Tageswert]] = {}
    for w in daten.werte:
        je_feld.setdefault(w.feld_id, []).append(w)
    aktiv = [f for f in daten.felder.values() if f.aktiv and f.deleted_at is None]
    sonst = [
        f for f in daten.felder.values() if (not f.aktiv or f.deleted_at) and je_feld.get(f.id)
    ]
    if not aktiv and not sonst:
        return [
            ft.Text(
                "Noch keine Tagesfelder. Mit ihnen hältst du an jedem Tag fest, was dir wichtig "
                "ist — Schmerz auf einer Skala, Trinken, Einnahmen, Themen zum Schreiben.",
                opacity=0.75,
            ),
            ft.Row(
                controls=[
                    ft.FilledTonalButton(
                        "Tagesfelder anlegen",
                        icon=ft.Icons.ADD,
                        on_click=_oeffner(page, "/einstellungen/tagesfelder"),
                    )
                ]
            ),
        ]

    def zeile(feld: tf.Tagesfeld) -> ft.Control:
        werte = je_feld.get(feld.id, [])
        if werte:
            letzter = max(w.tag for w in werte)
            stand = tf.stand_text(feld, tf.tagesstand(feld, [w for w in werte if w.tag == letzter]))
            unter = (
                f"{stand} · {kurz_datum(letzter, heute)}"
                if feld.art != tf.TEXT
                else (
                    f"nur Text · {len(werte)} {'Eintrag' if len(werte) == 1 else 'Einträge'} · "
                    f"zuletzt {kurz_datum(letzter, heute)}"
                )
            )
        else:
            unter = "noch nichts eingetragen"
        if not feld.aktiv and feld.deleted_at is None:
            unter = f"ausgeschaltet · {unter}"
        elif feld.deleted_at is not None:
            unter = f"gelöscht, Einträge behalten · {unter}"
        rechts: list[ft.Control] = []
        if werte and feld.art in tf.SUMMIERT:
            tage = [heute - timedelta(days=i) for i in range(6, -1, -1)]
            summen = [
                sum(float(w.wert) for w in werte if w.tag == t and isinstance(w.wert, int | float))
                for t in tage
            ]
            rechts.append(mini_saeulen(summen, breite=84, hoehe=28))
        elif werte and feld.art == tf.SKALA:
            je_tag: dict[date, list[tf.Tageswert]] = {}
            for w in werte:
                je_tag.setdefault(w.tag, []).append(w)
            punkte = []
            for t in sorted(je_tag):
                zahlen = [float(w.wert) for w in je_tag[t] if isinstance(w.wert, int | float)]
                if zahlen:
                    punkte.append(sum(zahlen) / len(zahlen))
            rechts.append(mini(punkte[-MINI_WERTE:], breite=84, hoehe=28))
        haupt = zl.Ziel(zl.VERLAUF, _oeffner(page, f"/verlauf/tagesfeld/{feld.id}"))
        blatt = zl.blatt_oeffner(
            page,
            feld.name,
            "alle Tage",
            tagesfeld_ziele(
                page, state, feld, tag=None, hier={zl.VERLAUF}, danach=state.neu_zeichnen
            ),
            hauptziel=haupt,
        )
        rechts.append(zl.zielsymbol(haupt, on_click=blatt))
        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border_radius=14,
            padding=ft.Padding.only(left=14, right=6, top=8, bottom=8),
            ink=True,
            on_click=haupt.oeffnen,
            on_long_press=blatt,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                feld.name,
                                size=15,
                                weight=ft.FontWeight.W_600,
                                opacity=1 if feld in aktiv else 0.7,
                            ),
                            ft.Text(unter, size=12, opacity=0.75, max_lines=2),
                        ],
                    ),
                    *rechts,
                ],
            ),
        )

    controls: list[ft.Control] = [abschnitt("Tagesfelder")]
    controls.extend(zeile(f) for f in aktiv)
    if sonst:
        controls.append(abschnitt("Ausgeschaltet oder gelöscht"))
        controls.extend(zeile(f) for f in sonst)
    controls.append(
        ft.Text(
            "Säulen: die letzten 7 Tage. Linie: die letzten Tage mit Wert. Antippen öffnet "
            "das Feld mit allen Einträgen.",
            size=11,
            opacity=0.6,
        )
    )
    return controls


# ---------------------------------------------------------------------------
# Reiter „Übungen“: alle Übungen mit Mini-Kurve und Trend
# ---------------------------------------------------------------------------


def trend_text(anteil: float | None) -> str:
    """„+19 %“, „−4 %“, „± 0 %“ — leer ohne Trend. Ohne Pfeilzeichen: Die fehlen
    manchen Schriften (im Browser standen Kästchen).

    >>> trend_text(0.19), trend_text(-0.044), trend_text(0.001), trend_text(None)
    ('+19 %', '−4 %', '± 0 %', '')
    """
    if anteil is None:
        return ""
    prozent = round(anteil * 100)
    if prozent == 0:
        return "± 0 %"
    return f"{'+' if prozent > 0 else '−'}{abs(prozent)} %"


def _passt(state: AppState, uebung: Exercise | None) -> bool:
    """Ob eine Übung durch Suche und Filter des Reiters „Übungen“ kommt — gesucht wird wie im
    Katalog in Name und Beschreibung, ohne Groß und klein."""
    text = state.verlauf_suche.strip().casefold()
    if uebung is None:  # Eintrag ohne Übung im Katalog: nur ohne Suche und Filter
        return not text and state.verlauf_filter.leer
    if text and text not in f"{uebung.name}\n{uebung.description}".casefold():
        return False
    return state.verlauf_filter.passt(uebung)


def _uebungen(page: ft.Page, state: AppState, daten: Callable[[], _Daten]) -> ft.Control:
    """Die Spalte „Übungen“: Suchzeile mit Filterknopf, Labels, darunter die Liste — Suche
    und Filter füllen nur die Liste neu."""
    inhalt = ft.Column(spacing=8)
    #: zur Wahl steht, was an gemachten Übungen vorkommt — häufige Tags zuerst
    gemacht = [u for k in daten().je_kachel if (u := daten().katalog.get(k)) is not None]
    typen = Counter(t for u in gemacht for t in u.typen)
    regionen = Counter(r for u in gemacht for r in u.regionen)

    def fuellen() -> None:
        inhalt.controls = _uebungen_inhalt(page, state, daten())

    def gefiltert() -> None:
        fuellen()
        _zeigen(aussen)

    def suchen(e: ft.Event[ft.TextField]) -> None:
        state.verlauf_suche = e.control.value or ""
        fuellen()
        _zeigen(inhalt)

    leiste = FilterLeiste(
        page,
        state.verlauf_filter,
        [t for t, _ in typen.most_common()],
        [r for r, _ in regionen.most_common()],
        paket_wahl(gemacht, [p for p, _ in state.pakete.alle()]),
        on_change=gefiltert,
        zaehlen=lambda: sum(_passt(state, u) for u in gemacht),
    )
    fuellen()
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=2, bottom=24),
                content=inhalt,
            )
        ],
    )
    aussen = ft.Column(
        expand=True,
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=16, right=8, top=12),
                content=leiste.suchzeile(
                    ft.TextField(
                        value=state.verlauf_suche,
                        hint_text="Übung suchen",
                        prefix_icon=ft.Icons.SEARCH,
                        border=ft.OutlineInputBorder(border_radius=12),
                        on_change=suchen,
                    )
                ),
            ),
            leiste.labels,  # nur, wenn ein Filter wirkt
            scroll_merken(page, state, "verlauf_uebungen", spalte),
        ],
    )
    return aussen


def _uebungen_inhalt(page: ft.Page, state: AppState, daten: _Daten) -> list[ft.Control]:
    """Je Übung (und Variante) eine Zeile mit Mini-Kurve und Trend — was durch Suche und
    Filter kommt."""
    heute = daten.heute
    reihenfolge = sorted(daten.je_kachel, key=lambda k: daten.je_kachel[k][-1][0], reverse=True)
    controls: list[ft.Control] = []
    controls.append(abschnitt("Zuletzt gemacht"))
    gezeigt = 0
    # Je Übung und Variante eine Zeile (Ben, 21.10.2026, Skizze B3) — zuletzt Gemachtes zuerst
    reihen = [
        (kachel_id, variante, liste)
        for kachel_id in reihenfolge
        for variante, liste in _je_variante(daten.je_kachel[kachel_id])
    ]
    reihen.sort(key=lambda r: r[2][-1][0], reverse=True)
    for kachel_id, variante, eintraege in reihen:
        uebung = daten.katalog.get(kachel_id)
        if not _passt(state, uebung):
            continue
        tage = sorted({t for t, _ in eintraege})
        zuletzt = tage[-1]
        neulich = kuerzlich(tage, heute, UEBUNGEN_WOCHEN)
        unter = (
            f"{neulich}× in {UEBUNGEN_WOCHEN} Wochen · zuletzt {kurz_datum(zuletzt, heute)}"
            if neulich
            else f"zuletzt {kurz_datum(zuletzt, heute)}"
        )
        kz = kennzahlen([e for _, e in eintraege])
        rechts: list[ft.Control]
        if kz:
            werte = tageswerte(eintraege, kz[0])
            letzter = werte[-1][1] if werte else None
            anteil = trend(werte, heute)
            hinweis = trend_text(anteil)
            if not hinweis and ist_neu(werte, heute):
                hinweis = "neu"
            rechts = [
                ft.Row(
                    spacing=10,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        mini([w for _, w in werte][-MINI_WERTE:], breite=72, hoehe=28),
                        ft.Column(
                            spacing=0,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                grosser_wert(
                                    kz[0].text(letzter) if letzter is not None else "–",
                                    kz[0].einheit,
                                ),
                                ft.Text(hinweis, size=11, opacity=0.7),
                            ],
                        ),
                    ],
                )
            ]
        else:
            _, je_woche = haeufigkeit(tage, montag(heute) - timedelta(days=35), heute)
            rechts = [
                ft.Row(
                    spacing=10,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        mini_saeulen([n for *_, n in je_woche], breite=72, hoehe=28),
                        ft.Column(
                            spacing=0,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                grosser_wert(f"{je_woche[-1][2]}×", ""),
                                ft.Text("diese Woche", size=11, opacity=0.7),
                            ],
                        ),
                    ],
                )
            ]
        controls.append(
            uebungszeile(
                symbol_key=uebung.icon_key if uebung else None,
                titel=uebung.name if uebung else "?",
                unter=[ft.Text(unter, size=12, opacity=0.75)],
                rechts=rechts,
                on_click=None,
                variante=_schild(uebung, variante),
                ziel=zl.Ziel(zl.VERLAUF, _oeffner(page, f"/verlauf/{kachel_id}")),
                weitere=ziele_fuer(page, state, kachel_id, tag=None, hier={zl.VERLAUF}),
                page=page,
                blatt_untertitel="alle Tage",
            )
        )
        gezeigt += 1
    if not gezeigt:
        controls.append(
            ft.Text(
                "Keine Übung passt zu Suche und Filter."
                if reihen
                else "Noch nichts eingetragen — Übungen erscheinen hier, sobald du sie machst.",
                opacity=0.7,
            )
        )
    return controls


def _je_variante(
    eintraege: list[tuple[date, SessionEntry]],
) -> list[tuple[str, list[tuple[date, SessionEntry]]]]:
    """Die Einträge einer Kachel je Variante — leer = ohne (in der Reihenfolge des ersten)."""
    gruppen: dict[str, list[tuple[date, SessionEntry]]] = {}
    for tag, e in eintraege:
        gruppen.setdefault(var.von(e.result), []).append((tag, e))
    return list(gruppen.items())


def _schild(uebung: Exercise | None, variante: str) -> ft.Control | None:
    """Das Schild der Variante hinter dem Namen — mit Symbol, wenn die Übung eins kennt."""
    if not variante:
        return None
    return varianten_etikett(var.finden(uebung.result_spec if uebung else None, variante))


__all__ = ["kurz_datum", "trend_text", "verlauf"]
