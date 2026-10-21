"""Eine Übung im Verlauf — Route `/verlauf/<kachel_id>` (Ben, 17.10.2026; Skizzen 2–4 zu P37).

Oben die **Kurve** einer Kennzahl, ein Punkt je Tag (dreimal 50 Liegestütze an einem Tag
sind ein Punkt bei 150), darunter drei Zahlen und die **Ergebnisse** je Tag mit Sätzen,
Varianten und Notizen — antippen öffnet den Tag. Ein Tipp auf einen Punkt markiert seine
Zeile.

- **Kennzahl** als Chips (eine Zeile, bricht um) nur, wenn die Übung mehrere hat
  (Wiederholungen je Tag, bester Satz, Haltezeit …, `core/verlauf.kennzahlen`); mit einer
  steht sie als Überschrift da.
- Ohne Werte, nur abgehakt: **wie oft** je Woche bzw. Monat als Säulen.
- **Zeitraum** 4 Wochen · 3 Monate · Jahr · alles; die Kurve beginnt beim ersten Wert darin.
- **Achse**: das Datum (Vorgabe) oder die Trainingsnummer (gleiche Abstände) — das Symbol
  rechts über der Kurve schaltet um.
- **Varianten** (Ben, 21.10.2026, Skizze B2): eine Linie je Variante — und je verwandter
  Übung, die sich die Kachel teilt —, jede mit fester Farbe (`core.verlauf.linien_ordnen`).
  Die Farbpunkte unter der Kurve blenden Linien aus; „Zusammen“ (gestrichelt) ist
  zuschaltbar und als Vorgabe aus. Die Trainingsnummer zählt über alle Linien.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import SessionEntry
from trainingsapp.core.tagesbilanz import kachel, kacheln
from trainingsapp.core.verlauf import (
    MODUS_NUMMER,
    MODUS_ZEIT,
    WOCHENTAGE,
    ZEITRAEUME,
    Kennzahl,
    Linie,
    haeufigkeit,
    kennzahlen,
    linie_name,
    linien,
    linien_ordnen,
    saetze_kurz,
    tageswert,
    tageswerte,
    ueberblick,
    zeitraum_beginn,
)
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlaufskurve import Reihe, saeulen
from trainingsapp.ui.components.verlaufskurve import linien as kurve_linien
from trainingsapp.ui.farben import FARBEN, REIHEN
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.verlauf import kurz_datum

#: Die Linie „Zusammen“ — gestrichelt in der Farbe der Nebentexte
ZUSAMMEN_FARBE = ft.Colors.ON_SURFACE_VARIANT


def _kachel_kurz(tag: date) -> str:
    return f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"


def verlauf_kachel_view(page: ft.Page, state: AppState, kachel_id: str) -> ft.View:
    heute = state.heute()
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    namen = {k: u.name for k, u in katalog.items()}
    mitglieder = [u for u in katalog.values() if kachel(u, u.id) == kachel_id]
    original = katalog.get(kachel_id)
    alle = state.sitzungen.eintraege_zwischen(
        state.profil.id, None, heute, exercise_ids=[u.id for u in mitglieder] or [kachel_id]
    )
    reihenfolge = var.namen(original.result_spec) if original else []

    def ordnen(liste: list[Linie]) -> list[Linie]:
        return linien_ordnen(liste, kachel_id, reihenfolge, namen)

    def name(linie: Linie) -> str:
        return linie_name(linie, namen, kachel_id)

    # -- Auswahl: Kennzahl, Zeitraum, Achse, Linien --------------------------------------

    optionen = kennzahlen([e for _, e in alle])
    gewaehlt = state.verlauf_kennzahlen.get(kachel_id)
    kennzahl = next((k for k in optionen if k.schluessel == gewaehlt), None)
    kennzahl = kennzahl or (optionen[0] if optionen else None)
    beginn = zeitraum_beginn(state.verlauf_zeitraum, heute)
    im_zeitraum = [(t, e) for t, e in alle if beginn is None or t >= beginn]
    werte = tageswerte(im_zeitraum, kennzahl) if kennzahl is not None else []
    trainingstage = sorted({t for t, _ in im_zeitraum})
    # Die Farbe hängt an der Linie, nicht am Zeitraum: vergeben über alle Einträge
    farben = {
        x.schluessel: FARBEN[REIHEN[i % len(REIHEN)]]
        for i, x in enumerate(ordnen(linien(alle, kennzahl) if kennzahl else []))
    }
    teile = ordnen(linien(im_zeitraum, kennzahl)) if kennzahl is not None else []
    mehrere = len(teile) > 1
    aus = state.verlauf_aus.get(kachel_id, set())
    zusammen = mehrere and kachel_id in state.verlauf_zusammen
    sichtbar = [x for x in teile if x.schluessel not in aus]
    if not sichtbar and not zusammen:
        sichtbar = teile  # nie eine leere Kurve, weil alles ausgeblendet ist

    def neu() -> None:
        state.neu_zeichnen()

    def kennzahl_waehler(schluessel: str) -> Callable[[object], None]:
        def waehlen(_e: object = None) -> None:
            state.verlauf_kennzahlen[kachel_id] = schluessel
            neu()

        return waehlen

    def linie_umschalter(schluessel: str) -> Callable[[object], None]:
        def umschalten(_e: object = None) -> None:
            versteckt = state.verlauf_aus.setdefault(kachel_id, set())
            if schluessel in versteckt:
                versteckt.discard(schluessel)
            elif len(sichtbar) > 1 or zusammen:
                versteckt.add(schluessel)
            else:
                return  # die letzte sichtbare Linie bleibt
            neu()

        return umschalten

    def zusammen_umschalten(_e: object = None) -> None:
        if zusammen:
            state.verlauf_zusammen.discard(kachel_id)
            if not [x for x in teile if x.schluessel not in aus]:
                state.verlauf_aus.pop(kachel_id, None)  # sonst bliebe nichts zu sehen
        else:
            state.verlauf_zusammen.add(kachel_id)
        neu()

    def zeitraum_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_zeitraum = str(e.control.selected[0])
            neu()

    def achse_wechseln() -> None:
        state.verlauf_modus = MODUS_NUMMER if state.verlauf_modus == MODUS_ZEIT else MODUS_ZEIT
        neu()

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    inhalt: list[ft.Control] = []
    verwandte = [u.name for u in mitglieder if u.id != kachel_id]
    if verwandte:
        inhalt.append(ft.Text("Mit Varianten: " + ", ".join(verwandte), size=12, opacity=0.7))
    if len(optionen) > 1 and kennzahl is not None:
        # Kennzahlen als Chips statt Dropdown (Ben, 19.10.2026): meist 1–5 Stück, der Platz
        # ist da — die Zeile bricht um, wenn es mehr werden
        inhalt.append(
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(k.label, size=13),
                        selected=k.schluessel == kennzahl.schluessel,
                        show_checkmark=False,
                        on_select=kennzahl_waehler(k.schluessel),
                    )
                    for k in optionen
                ],
            )
        )
    inhalt.append(
        ft.SegmentedButton(
            selected=[state.verlauf_zeitraum if state.verlauf_zeitraum in ZEITRAEUME else "3m"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=k, label=ft.Text(text)) for k, (text, _) in ZEITRAEUME.items()
            ],
            on_change=zeitraum_waehlen,
        )
    )

    # -- Kurve oder Säulen -----------------------------------------------------------

    ergebnisse = ft.Column(spacing=6)

    def markieren(tag: date) -> None:
        """Tipp auf einen Punkt: seine Zeile in den Ergebnissen hervorheben."""
        ergebnisse.controls = _ergebnisse(
            im_zeitraum, kennzahl, tag, heute, oeffner, kachel_id, ordnen, name
        )
        with contextlib.suppress(Exception):
            ergebnisse.update()

    zahlen: list[tuple[str, str, str]]
    if kennzahl is not None:
        zeit = state.verlauf_modus != MODUS_NUMMER
        titel = kennzahl.label + (f" · {kennzahl.einheit}" if kennzahl.einheit else "")
        reihen = [
            Reihe(x.werte, farben.get(x.schluessel, ft.Colors.PRIMARY), name(x)) for x in sichtbar
        ]
        if zusammen:
            reihen.append(Reihe(werte, ZUSAMMEN_FARBE, "Zusammen", gestrichelt=True))
        kurve = kurve_linien(
            reihen or [Reihe(werte)],
            kennzahl,
            modus=state.verlauf_modus,
            bis=heute,
            auf_tipp=markieren,
        )
        teile_der_karte: list[ft.Control] = [
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(titel, size=14, weight=ft.FontWeight.W_600, expand=True),
                    ft.IconButton(
                        ft.Icons.FORMAT_LIST_NUMBERED if zeit else ft.Icons.CALENDAR_MONTH,
                        tooltip="Gleiche Abstände (Training Nr.)" if zeit else "Zeitachse (Datum)",
                        icon_size=20,
                        on_click=achse_wechseln,
                    ),
                ],
            ),
            kurve,
        ]
        if mehrere:
            teile_der_karte.append(
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=6,
                    controls=[
                        *(
                            _legende(
                                name(x),
                                farben.get(x.schluessel, ft.Colors.PRIMARY),
                                x in sichtbar,
                                linie_umschalter(x.schluessel),
                            )
                            for x in teile
                        ),
                        _legende(
                            "Zusammen",
                            ZUSAMMEN_FARBE,
                            zusammen,
                            zusammen_umschalten,
                            gestrichelt=True,
                        ),
                    ],
                )
            )
        inhalt.append(karte(*teile_der_karte, abstand=4, padding=12))
        if mehrere:
            # Je sichtbarer Linie ihr höchster Wert (Skizze B2) — gezählt wird je Variante
            zahlen = [
                (f"Höchster · {name(x)}", kennzahl.text(h[1]), _kachel_kurz(h[0]))
                for x in sichtbar
                if (h := ueberblick(x.werte, 0, heute).hoechster) is not None
            ]
            if zusammen and (h := ueberblick(werte, 0, heute).hoechster) is not None:
                zahlen.append(("Höchster · Zusammen", kennzahl.text(h[1]), _kachel_kurz(h[0])))
            zahlen.append(("Trainings", str(len(trainingstage)), ""))
        else:
            u = ueberblick(werte, len(trainingstage), heute)
            zahlen = [
                (
                    "Höchster Wert",
                    kennzahl.text(u.hoechster[1]) if u.hoechster else "–",
                    _kachel_kurz(u.hoechster[0]) if u.hoechster else "",
                ),
                ("Ø 4 Wochen", kennzahl.text(u.mittel_4w) if u.mittel_4w is not None else "–", ""),
                ("Trainings", str(u.trainings), ""),
            ]
    else:
        einheit, je = haeufigkeit(
            trainingstage, trainingstage[0] if trainingstage else heute, heute
        )
        inhalt.append(
            karte(
                ft.Text(f"Wie oft je {einheit}", size=14, weight=ft.FontWeight.W_600),
                saeulen(je, einheit=einheit),
                abstand=4,
                padding=12,
            )
        )
        zahlen = [
            ("Trainings", str(len(trainingstage)), "im Zeitraum"),
            ("Zuletzt", kurz_datum(trainingstage[-1], heute) if trainingstage else "–", ""),
        ]
    if len(zahlen) <= 3:
        inhalt.append(ft.Row(spacing=8, controls=[_zahl(*z, expand=True) for z in zahlen]))
    else:  # viele Varianten: zwei je Zeile
        inhalt.append(
            ft.ResponsiveRow(spacing=8, run_spacing=8, controls=[_zahl(*z, col=6) for z in zahlen])
        )
    if kennzahl is None:
        inhalt.append(
            ft.Text(
                "Bisher nur abgehakt. Trägst du Wiederholungen oder Zeiten ein, entsteht hier "
                "die Kurve.",
                size=12,
                opacity=0.7,
            )
        )

    # -- Ergebnisse je Tag -------------------------------------------------------------

    ergebnisse.controls = _ergebnisse(
        im_zeitraum, kennzahl, None, heute, oeffner, kachel_id, ordnen, name
    )
    inhalt.append(
        ft.Text("ERGEBNISSE · NEUESTE ZUERST", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
    )
    inhalt.append(ergebnisse)

    return ft.View(
        route=f"/verlauf/{kachel_id}",
        appbar=ft.AppBar(title=ft.Text(original.name if original else "Verlauf")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=10, controls=inhalt), expand=False)],
    )


def _legende(
    text: str,
    farbe: str,
    an: bool,
    on_select: Callable[[object], None],
    *,
    gestrichelt: bool = False,
) -> ft.Control:
    """Ein Farbpunkt mit Namen unter der Kurve — antippen blendet die Linie aus und ein."""
    zeichen: ft.Control = (
        ft.Row(
            spacing=2,
            tight=True,
            controls=[ft.Container(width=4, height=2, bgcolor=farbe) for _ in range(3)],
        )
        if gestrichelt
        else ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe)
    )
    zeichen.opacity = 1 if an else 0.35
    return ft.Chip(
        label=ft.Text(text, size=13),
        leading=zeichen,
        selected=an,
        show_checkmark=False,
        on_select=on_select,
    )


def _zahl(name: str, wert: str, zusatz: str, *, expand: bool = False, col: int = 12) -> ft.Control:
    """Eine der Zahlen unter der Kurve: Name klein, Wert groß, Zusatz (Tag) klein."""
    return ft.Container(
        expand=expand,
        col=col,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Text(name, size=11, opacity=0.7),
                ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(wert, size=17, weight=ft.FontWeight.W_700),
                        ft.Text(zusatz, size=11, opacity=0.7),
                    ],
                ),
            ],
        ),
    )


def _saetze(liste: list[SessionEntry], kennzahl: Kennzahl | None) -> str:
    """„12 · 14“ — oder, ohne Sätze, was der Tag sonst war („abgehakt“)."""
    if kennzahl is not None and (saetze := saetze_kurz(liste, kennzahl)):
        return saetze
    (k,) = kacheln(liste, lambda _: "x")
    return k.zusammenfassung() or "abgehakt"


def _ergebnisse(
    eintraege: list[tuple[date, SessionEntry]],
    kennzahl: Kennzahl | None,
    markiert: date | None,
    heute: date,
    oeffner: Callable[[str], Callable[[], object]],
    kachel_id: str,
    ordnen: Callable[[list[Linie]], list[Linie]],
    name: Callable[[Linie], str],
) -> list[ft.Control]:
    """Je Tag eine Zeile, neueste zuerst: Sätze (oder „abgehakt“), Notizen und der Wert der
    Kennzahl; der markierte Tag (Tipp auf die Kurve) hervorgehoben. Waren mehrere Varianten
    dran, steht jede mit eigener Zahl darin (Ben, 21.10.2026: getrennt zählen); war nur eine
    dran, steht ihr Name dabei."""
    je_tag: dict[date, list[SessionEntry]] = {}
    for tag, e in eintraege:
        je_tag.setdefault(tag, []).append(e)
    if not je_tag:
        return [ft.Text("In diesem Zeitraum nichts eingetragen.", opacity=0.6)]
    zeilen: list[ft.Control] = []
    for tag in sorted(je_tag, reverse=True):
        liste = je_tag[tag]
        gruppen: dict[tuple[str, str], list[SessionEntry]] = {}
        for e in liste:
            gruppen.setdefault((e.exercise_id, var.von(e.result)), []).append(e)
        teile = ordnen([Linie(eid, v, ()) for eid, v in gruppen])
        mitte: list[ft.Control] = []
        wert = None
        if len(teile) > 1:
            for t in teile:
                teil = gruppen[(t.exercise_id, t.variante)]
                w = tageswert(teil, kennzahl) if kennzahl is not None else None
                mitte.append(
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Text(f"{name(t)} · {_saetze(teil, kennzahl)}", size=13, expand=True),
                            ft.Text(
                                kennzahl.text(w) if kennzahl is not None and w is not None else "",
                                size=13,
                                weight=ft.FontWeight.W_700,
                            ),
                        ],
                    )
                )
        else:
            wert = tageswert(liste, kennzahl) if kennzahl is not None else None
            mitte.append(ft.Text(_saetze(liste, kennzahl), size=13))
            (t,) = teile
            if t.exercise_id != kachel_id or t.variante:
                mitte.append(ft.Text(name(t), size=11, opacity=0.7))
        for e in liste:
            if e.note:
                mitte.append(
                    ft.Row(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Icon(ft.Icons.EDIT_NOTE, size=14, opacity=0.7),
                            ft.Text(e.note, size=11, opacity=0.7, expand=True),
                        ],
                    )
                )
        anfang = min((e.started_at for e in liste if e.started_at), default=None)
        zeilen.append(
            ft.Container(
                bgcolor=ft.Colors.SECONDARY_CONTAINER
                if tag == markiert
                else ft.Colors.SURFACE_CONTAINER_LOWEST,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=6, top=8, bottom=8),
                ink=True,
                on_click=oeffner(f"/tag/{tag.isoformat()}"),
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            tight=True,
                            width=72,
                            controls=[
                                ft.Text(
                                    kurz_datum(tag, heute), size=13, weight=ft.FontWeight.W_700
                                ),
                                ft.Text(
                                    anfang.astimezone().strftime("%H:%M") if anfang else "",
                                    size=11,
                                    opacity=0.7,
                                ),
                            ],
                        ),
                        ft.Column(spacing=1, tight=True, expand=True, controls=mitte),
                        ft.Text(
                            kennzahl.text(wert)
                            if kennzahl is not None and wert is not None
                            else "",
                            size=15,
                            weight=ft.FontWeight.W_700,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                    ],
                ),
            )
        )
    return zeilen


__all__ = ["verlauf_kachel_view"]
