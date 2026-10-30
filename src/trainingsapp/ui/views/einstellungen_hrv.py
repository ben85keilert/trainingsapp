"""Einstellungen → HRV-Messung — Route `/einstellungen/hrv`.

Alles, was sich an der Messung einstellen lässt, an einer Stelle — mit
sinnvollen Vorgaben und einem Knopf, der alles auf diese Vorgaben zurücksetzt.
Die kleinen Knöpfe in der Messansicht (Fensterbreite, „korrigiert", Regler,
Kurvenmenü) ändern dieselben Werte; was man dort einstellt, steht auch hier.

Zwei Teile (Ben, 14.10.2026): **normal** für alle, **Erweitert** (zugeklappt)
für Fachleute — langfristig werden das Profi-Einstellungen.

- Anzeige: Reiter „Messung" ein/aus — ohne Gerät spart das Platz.
- Kacheln über der Kurve, nach Bereichen gruppiert.
- Kurven: Live-Fenster, Live-Verlauf (wie weit der Puffer zurückreicht), „korrigiert",
  Kurvenansicht.
- Analyse: Frequenz und Nichtlinear anbieten (bei optischen Sensoren aus).
- Notizen: Übungen aus Plänen anbieten.
- Erweitert: Rechnen (Latenz vor dem Nachrechnen, Takt des Live-Spektrums),
  Kennzahlen (pNNx-Schwelle), automatische Korrektur (`hrv_core.regeln`).

Unter Namen gespeicherte Kurvenansichten bleiben beim Zurücksetzen erhalten.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft
from hrv_core.regeln import Korrekturregeln

from trainingsapp.core.hrv_ansicht import PNN_WAHL, Ansicht
from trainingsapp.core.hrv_einstellungen import (
    ACHSEN_NAMEN,
    ACHSEN_VORGABE,
    LIVE_SPEKTRUM_S,
    NACHRECHNEN_MS,
    NOTIZEN_ZEILEN,
    PUFFER_S,
    UEBERSICHT,
    HrvEinstellungen,
)
from trainingsapp.core.hrv_einstellungen import KACHELN as KACHELN_DARSTELLUNG
from trainingsapp.core.uhr_seiten import SEITE_HF as UHR_SEITE_HF
from trainingsapp.core.uhr_seiten import SEITEN as UHR_SEITEN
from trainingsapp.core.uhr_seiten import SEITEN_NAMEN as UHR_SEITEN_NAMEN
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.kacheln import GRUPPEN, KACHELN
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlauf import FARBEN
from trainingsapp.ui.components.zeitfenster import (
    BreiteFeld,
    BreitenSatz,
    breiten_auswahl,
    breiten_nachziehen,
    breiten_wahl,
)
from trainingsapp.ui.state import AppState


def regeln_text(r: Korrekturregeln) -> str:
    """Kurzfassung der Korrekturregeln für die Einstellungsseite.

    >>> for teil in regeln_text(Korrekturregeln()).split(" · "):
    ...     print(teil)
    Malik nach Sensor (EKG 20 %, optisch 30 %)
    250–2000 ms
    Sensor-Fehler über 50 ms
    dem Sensor folgen
    """
    teile = []
    if r.malik_an:
        teile.append(
            f"Malik {round(r.malik * 100)} %"
            if r.malik is not None
            else "Malik nach Sensor (EKG 20 %, optisch 30 %)"
        )
    else:
        teile.append("Malik aus")
    teile.append(f"{r.rr_min}–{r.rr_max} ms")
    if r.fehler_an:
        teile.append(f"Sensor-Fehler über {r.fehler_max_ms} ms")
    teile.append("Verworfenes selbst prüfen" if r.selbst_pruefen else "dem Sensor folgen")
    return " · ".join(teile)


def einstellungen_hrv(page: Any, state: AppState) -> ft.View:
    e = state.hrv_einstellungen()
    ansicht = state.ansicht()

    async def zu_ueberschriften() -> None:
        await page.push_route("/einstellungen/hrv/ueberschriften")

    def setzen(**werte: Any) -> None:
        for name, wert in werte.items():
            setattr(e, name, wert)
        state.hrv_einstellungen_setzen(e)

    schalter_je_name: dict[str, ft.Switch] = {}

    def schalter(name: str, label: str, untertitel: str = "", **extra: Any) -> ft.Control:
        # Kein Neuaufbau der Seite: der würde nach oben springen. Nur was vom
        # Schalter abhängt, wird nachgezogen.
        def handler(ev: ft.Event[ft.Switch]) -> None:
            setzen(**{name: bool(ev.control.value)})
            if name == "nichtlinear" and (optisch := schalter_je_name.get("nichtlinear_optisch")):
                optisch.disabled = not e.nichtlinear
                with contextlib.suppress(Exception):
                    optisch.update()

        knopf = ft.Switch(label=label, value=getattr(e, name), on_change=handler, **extra)
        schalter_je_name[name] = knopf
        return ft.Column(
            spacing=0,
            tight=True,
            controls=[
                knopf,
                ft.Container(
                    padding=ft.Padding.only(left=60, bottom=4),
                    content=hinweis(untertitel),
                    visible=bool(untertitel),
                ),
            ],
        )

    # -- Übersicht: welche Werte, Reihenfolge, groß --------------------------------
    # Ziehen ordnet um, der Stern hebt hervor, × entfernt, Chips fügen hinzu.
    # Geändert wird nur diese Karte — ein Neuaufbau der Seite spränge nach oben.

    ZEILE_PX = 52
    # Eigener Griff links: der eingebaute läge am Rechner über dem ×-Knopf
    auswahl_liste = ft.ReorderableListView(
        spacing=0, item_extent=ZEILE_PX, show_default_drag_handles=False
    )
    angebot = ft.Column(spacing=8, tight=True)

    def uebersicht_neu() -> None:
        auswahl_liste.controls = [zeile(k) for k in e.kacheln if k in KACHELN]
        auswahl_liste.height = max(len(auswahl_liste.controls), 1) * ZEILE_PX
        angebot.controls = []
        for gruppe, keys in GRUPPEN:
            frei = [k for k in keys if k not in e.kacheln]
            if frei:
                angebot.controls.append(
                    ft.Text(gruppe, size=12, weight=ft.FontWeight.W_600, opacity=0.8)
                )
                angebot.controls.append(
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[hinzu(k) for k in frei])
                )
        if not angebot.controls:
            angebot.controls.append(hinweis("Alle Werte sind gewählt."))
        with contextlib.suppress(Exception):
            auswahl_liste.update()
            angebot.update()

    def verschoben(ev: ft.OnReorderEvent) -> None:
        if ev.old_index is None or ev.new_index is None:
            return
        liste = [k for k in e.kacheln if k in KACHELN]
        neu_index = ev.new_index - (1 if ev.new_index > ev.old_index else 0)
        liste.insert(neu_index, liste.pop(ev.old_index))
        setzen(kacheln=liste)
        uebersicht_neu()

    auswahl_liste.on_reorder = verschoben

    def gross_umschalter(key: str) -> Callable[[], None]:
        def handler() -> None:
            setzen(gross=[k for k in e.kacheln if k in (set(e.gross) ^ {key})])
            uebersicht_neu()

        return handler

    def entferner(key: str) -> Callable[[], None]:
        def handler() -> None:
            setzen(kacheln=[k for k in e.kacheln if k != key])
            uebersicht_neu()

        return handler

    def hinzufueger(key: str) -> Callable[[], None]:
        def handler() -> None:
            setzen(kacheln=[*e.kacheln, key])
            uebersicht_neu()

        return handler

    def punkt(key: str) -> ft.Control:
        farbe = FARBEN.get(KACHELN[key].kennzahl or "")
        return ft.Container(
            width=10, height=10, border_radius=5, bgcolor=farbe or ft.Colors.TRANSPARENT
        )

    def zeile(key: str) -> ft.Control:
        art = KACHELN[key]
        gross = key in e.gross
        return ft.Container(
            # kein key=: Die Zeilen werden bei jeder Änderung ersetzt, und Flet 1.0 friert
            # ersetzte Controls mit key ein („Frozen controls cannot be updated“, N20)
            height=ZEILE_PX,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.ReorderableDragHandle(
                        content=ft.Icon(ft.Icons.DRAG_INDICATOR, opacity=0.5),
                        mouse_cursor=ft.MouseCursor.GRAB,
                    ),
                    punkt(key),
                    ft.Text(art.titel, expand=True, weight=ft.FontWeight.W_600 if gross else None),
                    ft.IconButton(
                        ft.Icons.STAR if gross else ft.Icons.STAR_BORDER,
                        tooltip="Groß hervorheben" if not gross else "Nicht mehr groß",
                        icon_color=ft.Colors.AMBER_600 if gross else None,
                        on_click=gross_umschalter(key),
                    ),
                    ft.IconButton(ft.Icons.CLOSE, tooltip="Entfernen", on_click=entferner(key)),
                ],
            ),
        )

    def hinzu(key: str) -> ft.Control:
        art = KACHELN[key]
        return ft.Chip(
            label=ft.Text(art.titel, size=12),
            leading=ft.Icon(ft.Icons.ADD, size=16),
            on_click=hinzufueger(key),
            tooltip=art.erklaerung or None,
        )

    def darstellung_gewaehlt(ev: ft.Event[ft.SegmentedButton]) -> None:
        if ev.control.selected:
            setzen(darstellung=str(ev.control.selected[0]))

    uebersicht_neu()

    # -- Kurven ----------------------------------------------------------------
    # Dieselben vier Knöpfe wie an der Kurve, jede andere Breite eingetippt (Ben, 21.10.2026)

    def breite_gewaehlt(breite_s: float) -> None:
        setzen(fenster_s=round(breite_s))
        breite_knoepfe.selected = breiten_auswahl(breite_s, e.breiten())
        breite_feld.anzeigen(breite_s)
        with contextlib.suppress(Exception):
            breite_knoepfe.update()

    breite_knoepfe = breiten_wahl(e.fenster_s, breite_gewaehlt, breiten=e.breiten())
    breite_feld = BreiteFeld(e.fenster_s, breite_gewaehlt, max_s=e.puffer_s)

    # Welche Knöpfe an den Kurven stehen (Ben, 30.10.2026): zwei Sätze oder eigene Breiten
    def satz_geaendert(neu: HrvEinstellungen) -> None:
        breiten_nachziehen(breite_knoepfe, neu.breiten(), e.fenster_s)

    def satz_speichern(neu: HrvEinstellungen) -> None:
        setzen(breiten_satz=neu.breiten_satz, breiten_eigen=list(neu.breiten_eigen))

    breiten_satz = BreitenSatz(lambda: e, satz_speichern, satz_geaendert)

    def puffer_text(sekunden: int) -> str:
        return f"{sekunden // 60} min" if sekunden < 3600 else f"{sekunden // 3600} h"

    def puffer_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        """Live-Verlauf (Ben, 26.10.2026): wie weit die Live-Kurven zurückreichen. Die
        Zeitachse darf nicht breiter sein als der Puffer."""
        if ev.control.value is None:
            return
        setzen(puffer_s=int(ev.control.value))
        breite_feld.max_setzen(e.puffer_s)
        if e.fenster_s > e.puffer_s:
            breite_gewaehlt(float(e.puffer_s))

    puffer_wahl = ft.Dropdown(
        label="Live-Verlauf behalten",
        value=str(e.puffer_s),
        options=[ft.DropdownOption(key=str(x), text=puffer_text(x)) for x in PUFFER_S],
        on_select=puffer_gewaehlt,
        dense=True,
        width=260,
    )

    # Standardwerte der festen Werteachsen (Ben, 30.10.2026): je Achse von–bis; das Blatt
    # „Fenster & Darstellung“ schaltet sie ein und stellt sie mit ↺ wieder her
    achsen_felder: dict[str, tuple[ft.TextField, ft.TextField]] = {}

    def achsen_zahl(text: str | None) -> float | None:
        try:
            return float((text or "").strip().replace(",", "."))
        except ValueError:
            return None

    def achse_uebernehmen(k: str) -> Callable[[Any], None]:
        def handler(_ev: Any = None) -> None:
            von, bis = achsen_felder[k]
            lo, hi = achsen_zahl(von.value), achsen_zahl(bis.value)
            if lo is None or hi is None or lo >= hi:
                von.error = "zwei Zahlen, von < bis"
            else:
                von.error = None
                if e.achsen_standard.get(k) != (lo, hi):
                    e.achsen_standard[k] = (lo, hi)
                    setzen(achsen_standard=dict(e.achsen_standard))
            with contextlib.suppress(Exception):
                von.update()

        return handler

    def achsen_zahl_text(wert: float) -> str:
        return f"{wert:g}".replace(".", ",")

    def achsen_feld(k: str, label: str, wert: float) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=achsen_zahl_text(wert),
            dense=True,
            width=96,
            border_radius=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT,
            on_submit=achse_uebernehmen(k),
            on_blur=achse_uebernehmen(k),
        )

    def achsen_zeile(k: str) -> ft.Control:
        name, einheit = ACHSEN_NAMEN[k]
        lo, hi = e.achse_standard(k) or ACHSEN_VORGABE[k]
        von, bis = achsen_feld(k, "von", lo), achsen_feld(k, "bis", hi)
        achsen_felder[k] = (von, bis)
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(name, size=13),
                        ft.Text(einheit, size=11, opacity=0.65, visible=bool(einheit)),
                    ],
                ),
                von,
                ft.Text("–"),
                bis,
            ],
        )

    def achsen_vorgabe() -> None:
        e.achsen_standard = dict(ACHSEN_VORGABE)
        setzen(achsen_standard=dict(e.achsen_standard))
        for k, (von, bis) in achsen_felder.items():
            lo, hi = ACHSEN_VORGABE[k]
            von.value, bis.value, von.error = achsen_zahl_text(lo), achsen_zahl_text(hi), None
            for f in (von, bis):
                with contextlib.suppress(Exception):
                    f.update()

    achsen_zeilen = [achsen_zeile(k) for k in ACHSEN_VORGABE]

    def notizen_zeilen_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        """Notizliste (Ben, 27.10.2026): ab so vielen Notizen rollt sie, die Kurve bleibt."""
        if ev.control.value is not None:
            setzen(notizen_zeilen=int(ev.control.value))

    notizen_zeilen_wahl = ft.Dropdown(
        label="Notizen in der Liste",
        value=str(e.notizen_zeilen),
        options=[
            ft.DropdownOption(key=str(x), text=f"{x} Zeilen, dann rollen" if x else "alle")
            for x in NOTIZEN_ZEILEN
        ],
        on_select=notizen_zeilen_gewaehlt,
        dense=True,
        width=260,
    )

    def pnn_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        a = state.ansicht()
        a.pnn_ms = int(ev.control.value or 50)
        state.ansicht_setzen(a)

    def kurven_zuruecksetzen() -> None:
        state.ansicht_setzen(Ansicht())
        page.show_dialog(ft.SnackBar(ft.Text("Kurven auf Standard zurückgesetzt.")))
        state.neu_zeichnen()

    def ansicht_loescher(name: str) -> Callable[[], None]:
        def handler() -> None:
            state.ansicht_loeschen(name)
            state.neu_zeichnen()

        return handler

    gespeichert = state.ansichten()
    ansichten_liste: list[ft.Control] = [
        ft.ListTile(
            dense=True,
            leading=ft.Icon(ft.Icons.DASHBOARD_CUSTOMIZE_OUTLINED),
            title=ft.Text(a.name),
            subtitle=ft.Text(f"{len(a.kurven)} Kurven", size=12),
            trailing=ft.IconButton(
                ft.Icons.DELETE_OUTLINE,
                tooltip="Ansicht löschen",
                on_click=ansicht_loescher(a.name),
            ),
            content_padding=ft.Padding.only(left=0, right=0),
        )
        for a in gespeichert
    ]

    # -- Korrektur -------------------------------------------------------------

    regeln_zeile = ft.Text(regeln_text(state.korrekturregeln()), size=12, opacity=0.75)

    def regeln_oeffnen() -> None:
        def aendern(r: Korrekturregeln) -> None:
            state.korrekturregeln_setzen(r)
            regeln_zeile.value = regeln_text(r)
            regeln_zeile.update()

        blatt = korrektur_blatt(
            state.korrekturregeln(), aendern, erweitert=True, schliessen=lambda: schliessen(blatt)
        )
        page.show_dialog(blatt)

    def regeln_zuruecksetzen() -> None:
        state.korrekturregeln_setzen(Korrekturregeln())
        regeln_zeile.value = regeln_text(Korrekturregeln())
        page.show_dialog(ft.SnackBar(ft.Text("Korrektur auf Vorgabe zurückgesetzt.")))
        page.update()

    # -- Alles zurücksetzen -------------------------------------------------------

    def fragen() -> None:
        nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (N19)
        dialog: ft.AlertDialog

        def alles_zuruecksetzen() -> None:
            state.hrv_zuruecksetzen()
            nachher.danach(
                lambda: page.show_dialog(
                    ft.SnackBar(ft.Text("HRV-Einstellungen auf Standard zurückgesetzt."))
                )
            )
            nachher.danach(state.neu_zeichnen)
            schliessen(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Alles zurücksetzen?"),
            content=ft.Text(
                "Kacheln, Fenster, Kurven, Analysebereiche und die automatische "
                "Korrektur gehen auf die Vorgaben zurück. Gespeicherte Ansichten und "
                "Messungen bleiben."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Zurücksetzen", on_click=alles_zuruecksetzen),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    # -- Erweitert (zugeklappt): Rechnen, Kennzahlen, Korrektur ------------------------

    def auswahl(
        name: str, label: str, werte: tuple[int, ...], text: Callable[[int], str]
    ) -> ft.Control:
        def gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            if ev.control.value is not None:
                setzen(**{name: int(ev.control.value)})

        return ft.Dropdown(
            label=label,
            value=str(getattr(e, name)),
            options=[ft.DropdownOption(key=str(x), text=text(x)) for x in werte],
            on_select=gewaehlt,
            dense=True,
            width=260,
        )

    def ms_text(ms: int) -> str:
        return "sofort" if ms == 0 else f"{ms / 1000:g} s".replace(".", ",")

    erweitert_teil = ft.Column(
        spacing=14,
        visible=state.hrv_erweitert_offen,
        controls=[
            karte(
                titel("Rechnen"),
                auswahl(
                    "nachrechnen_ms",
                    "Nachrechnen nach dem Loslassen",
                    NACHRECHNEN_MS,
                    ms_text,
                ),
                hinweis(
                    "Wie lange Spektrum und Poincaré nach dem Loslassen des Analysefensters "
                    "(oder live nach dem Wischen) warten, bevor sie rechnen — kommt in dieser "
                    f"Zeit noch eine Bewegung nach, wird erst danach gerechnet. Vorgabe "
                    f"{ms_text(HrvEinstellungen().nachrechnen_ms)}."
                ),
                auswahl(
                    "live_spektrum_s",
                    "Live-Spektrum neu rechnen alle",
                    LIVE_SPEKTRUM_S,
                    lambda s: f"{s} s",
                ),
                hinweis(
                    f"Vorgabe {HrvEinstellungen().live_spektrum_s} s — so genau braucht man "
                    "es selten. Kürzer kostet am Handy Rechenzeit, auch für den Empfang der "
                    "Messwerte."
                ),
            ),
            karte(
                titel("Kennzahlen"),
                ft.Dropdown(
                    label="Schwelle für pNNx",
                    value=str(ansicht.pnn_ms),
                    options=[ft.DropdownOption(key=str(x), text=f"{x} ms") for x in PNN_WAHL],
                    on_select=pnn_gewaehlt,
                    dense=True,
                    width=200,
                ),
                hinweis(
                    "Üblich ist pNN50: Anteil der Nachbarschläge, die mehr als 50 ms "
                    "auseinanderliegen."
                ),
            ),
            karte(
                titel("Automatische Korrektur"),
                regeln_zeile,
                ft.Row(
                    wrap=True,
                    spacing=8,
                    controls=[
                        ft.FilledTonalButton(
                            "Regeln …", icon=ft.Icons.TUNE, on_click=regeln_oeffnen
                        ),
                        ft.TextButton(
                            "Auf Vorgabe", icon=ft.Icons.RESTART_ALT, on_click=regeln_zuruecksetzen
                        ),
                    ],
                ),
                hinweis(
                    "Gilt live und für neue Aufzeichnungen. Eine Aufzeichnung öffnet mit den "
                    "Regeln, mit denen sie korrigiert wurde."
                ),
            ),
        ],
    )
    erweitert_pfeil = ft.Icon(
        ft.Icons.EXPAND_LESS if state.hrv_erweitert_offen else ft.Icons.EXPAND_MORE
    )

    def erweitert_umschalten() -> None:
        state.hrv_erweitert_offen = not state.hrv_erweitert_offen
        erweitert_teil.visible = state.hrv_erweitert_offen
        erweitert_pfeil.icon = (
            ft.Icons.EXPAND_LESS if state.hrv_erweitert_offen else ft.Icons.EXPAND_MORE
        )
        with contextlib.suppress(Exception):
            erweitert_teil.update()
            erweitert_pfeil.update()

    erweitert_kopf = ft.Container(
        on_click=lambda: erweitert_umschalten(),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=8, vertical=10),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.TUNE, opacity=0.7),
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text("Erweitert", size=16, weight=ft.FontWeight.W_600),
                        ft.Text(
                            "Für Fachleute: Rechenzeiten, Kennzahlen, automatische Korrektur",
                            size=12,
                            opacity=0.7,
                        ),
                    ],
                ),
                erweitert_pfeil,
            ],
        ),
    )

    # -- Uhr am Handgelenk: Zustand des Kanals und Testseite (Diagnose, 26.10.2026) ----
    uhr_status = ft.Text("", size=12)
    uhr_protokoll = ft.Text("", size=11, opacity=0.6, font_family="monospace", selectable=True)

    def uhr_status_neu(_ev: Any = None) -> None:
        kanal = state.uhr
        if kanal is None:
            uhr_status.value = "Kanal nicht verfügbar (nur in der Android-App)"
            uhr_protokoll.value = ""
        else:
            uhr_status.value = f"Kanal: {kanal.zustand}"
            uhr_protokoll.value = "\n".join(list(kanal.protokoll)[-12:])
        with contextlib.suppress(Exception):
            uhr_status.update()
            uhr_protokoll.update()

    async def uhr_testen(_ev: Any = None) -> None:
        if state.uhr is not None:
            await state.uhr.test()
        uhr_status_neu()

    uhr_status_neu()

    # Welche Seiten die Uhr bekommt (`core.uhr_seiten.SEITEN`; HF immer)
    def uhr_seite_setzen(key: str, an: bool) -> None:
        gewaehlt = set(e.uhr_seiten) | {UHR_SEITE_HF}
        gewaehlt = gewaehlt | {key} if an else gewaehlt - {key}
        setzen(uhr_seiten=[k for k in UHR_SEITEN if k in gewaehlt])

    uhr_seiten_box = ft.Column(
        spacing=0,
        tight=True,
        controls=[
            ft.Checkbox(
                label=UHR_SEITEN_NAMEN[k],
                value=k == UHR_SEITE_HF or k in e.uhr_seiten,
                disabled=k == UHR_SEITE_HF,
                on_change=lambda ev, k=k: uhr_seite_setzen(k, bool(ev.control.value)),
            )
            for k in UHR_SEITEN
        ],
    )

    standard = HrvEinstellungen()
    inhalt = ft.Column(
        spacing=14,
        controls=[
            karte(
                titel("Anzeige"),
                schalter(
                    "messung_anzeigen",
                    "Reiter „Messung“ anzeigen",
                    "Ohne Pulsgurt oder Sensor ausblenden — das spart Platz. Läuft eine "
                    "Messung, bleibt der Reiter sichtbar.",
                ),
            ),
            karte(
                titel("Übersicht über der Kurve"),
                ft.SegmentedButton(
                    selected=[e.darstellung],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=UEBERSICHT, label=ft.Text("Übersicht")),
                        ft.Segment(value=KACHELN_DARSTELLUNG, label=ft.Text("Kacheln")),
                    ],
                    on_change=darstellung_gewaehlt,
                ),
                hinweis(
                    "Ziehen ordnet um, der Stern hebt einen Wert groß hervor, × entfernt "
                    "ihn. Werte einer Kurve rechnen mit deren Fenster und tragen ihre Farbe."
                ),
                auswahl_liste,
                ft.Text("Hinzufügen", size=12, opacity=0.8),
                angebot,
            ),
            karte(
                titel("Atmung", hilfe_knopf(page, thema="atmung")),
                schalter(
                    "atemuebung",
                    "Atemübung (langsames Atmen)",
                    "Wertet auch Atmen unter 8 Atemzügen je Minute aus. Dort liegt auch die "
                    "Blutdruckwelle — aus dem Herzschlag allein nicht zu unterscheiden. Bei "
                    "einer Atemübung (z. B. 6/min) einschalten, sonst bleibt die "
                    "Atemfrequenz dort leer.",
                ),
            ),
            karte(
                titel("Kurven"),
                ft.Text("Knöpfe der Zeitachse (live und Aufzeichnung)", size=12, opacity=0.8),
                breiten_satz.control,
                ft.Text("Zeitfenster live", size=12, opacity=0.8),
                breite_knoepfe,
                breite_feld.control,
                puffer_wahl,
                hinweis(
                    "So weit lässt sich live zurückblättern, so lang darf die Zeitachse "
                    "höchstens sein, und bis dahin reichen nachgetragene Notizen in die "
                    "Kurve. Gilt ab der nächsten Verbindung; die Aufnahme selbst ist "
                    "unbegrenzt. Mehr Verlauf kostet am Handy Speicher und Rechenzeit."
                ),
                notizen_zeilen_wahl,
                hinweis(
                    "Mehr Notizen als Zeilen rollen in der Liste, die Kurve bleibt dabei im "
                    "Blick — unter der Hauptkurve und im Vollbild."
                ),
                schalter(
                    "korrigiert",
                    "Live die korrigierte Kurve zeigen",
                    "Artefakte überbrückt — nur die Anzeige; gespeichert werden immer "
                    "die Rohwerte.",
                ),
                hinweis(
                    "Welche Verlaufskurven mit welchem Fenster zu sehen sind, stellt man in "
                    "der Messung unter „Fenster & Darstellung“ ein (Regler an der Kurve) — "
                    "dort auch feste Werteachsen, z. B. RR 500 bis 1500 ms."
                ),
                ft.TextButton(
                    "Kurven auf Standard zurücksetzen",
                    icon=ft.Icons.RESTART_ALT,
                    on_click=kurven_zuruecksetzen,
                ),
                *(
                    [ft.Text("Gespeicherte Ansichten", size=12, opacity=0.8), *ansichten_liste]
                    if ansichten_liste
                    else []
                ),
            ),
            karte(
                titel("Werteachsen"),
                hinweis(
                    "Standardwerte, die den ganzen Bereich abdecken. Im Blatt „Fenster & "
                    "Darstellung“ schaltet man eine Achse fest, stellt sie nach oder setzt "
                    "mit ↺ diese Werte wieder ein. Welche Achse eine Kurve hat, steht dort."
                ),
                *achsen_zeilen,
                ft.TextButton(
                    "Auf Vorgabe",
                    icon=ft.Icons.RESTART_ALT,
                    on_click=lambda _=None: achsen_vorgabe(),
                ),
            ),
            karte(
                titel("Analyse unter der Kurve"),
                hinweis(
                    "Unter der Hauptkurve schaltet man zwischen Zeit, Frequenz und "
                    "Nichtlinear um. Was hier aus ist, erscheint dort nicht."
                ),
                schalter(
                    "frequenz",
                    "Frequenz (Spektrum, LF, HF)",
                    "Wie stark der Herzschlag langsam (LF) und atemgebunden (HF) schwankt.",
                ),
                schalter(
                    "nichtlinear",
                    "Nichtlinear (Poincaré, DFA α1)",
                    "Braucht genaue Schlagzeiten — mit dem Brustgurt als Trend lesbar.",
                ),
                schalter(
                    "nichtlinear_optisch",
                    "Nichtlinear auch bei optischen Sensoren",
                    "Nicht empfohlen: Pulsintervalle (Verity Sense) sind dafür zu ungenau.",
                    disabled=not e.nichtlinear,
                ),
            ),
            karte(
                titel("Notizen zur Messung"),
                schalter(
                    "notiz_uebungen",
                    "Übungen aus Plänen anbieten",
                    "In der Notiz die Übungen eines Plans als Namen zum Antippen einblenden.",
                ),
                ft.ListTile(
                    dense=True,
                    content_padding=ft.Padding.only(left=0, right=0),
                    leading=ft.Icon(ft.Icons.TITLE),
                    title=ft.Text("Überschriften"),
                    subtitle=ft.Text(
                        f"{len(state.hrv.titel_liste(state.profil.id))} gespeichert — zum "
                        "Antippen im Titel-Blatt; anlegen, anheften, löschen",
                        size=12,
                    ),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=zu_ueberschriften,
                ),
            ),
            karte(
                titel("Uhr am Handgelenk"),
                schalter(
                    "uhr_medien",
                    "Werte als Mediensteuerung senden",
                    "Für Bänder ohne eigene App (Galaxy Fit3): die Seiten unten stehen in der "
                    "Mediensteuerung, solange ein Gurt verbunden ist. ▶ blättert; ⏯ setzt eine "
                    "Marke, auf der Intervallseite beginnen Gipfel und Tal neu, auf der HRR-Seite "
                    "endet die Belastung. Die Gurt-Warnung kommt als Benachrichtigung — dafür "
                    "in Galaxy Wearable die Benachrichtigungen dieser App einschalten. "
                    "Es läuft kein Ton.",
                ),
                hinweis("Seiten am Band (HF immer):"),
                uhr_seiten_box,
                uhr_status,
                ft.Row(
                    spacing=8,
                    wrap=True,
                    controls=[
                        ft.OutlinedButton(
                            "Testseite 60 s senden",
                            icon=ft.Icons.WATCH,
                            on_click=uhr_testen,
                            disabled=state.uhr is None,
                        ),
                        ft.TextButton("Status aktualisieren", on_click=uhr_status_neu),
                    ],
                ),
                uhr_protokoll,
            ),
            karte(
                titel("EKG-Rohsignal (Polar H10)"),
                schalter(
                    "ekg_mitschreiben",
                    "EKG mitschreiben",
                    "Der H10 sendet zusätzlich sein EKG (130 Hz). Die App speichert es neben der "
                    "Messung als „…_ecg.json“ — nur gespeichert, nicht gerechnet; in der "
                    "Auswertung lässt es sich in kurzen Ausschnitten ansehen, beim Weitergeben "
                    "und im Forschungsexport ist es dabei. Kostet den Gurt spürbar Akku und "
                    "etwa 3 MB je Stunde; der Akkustand wird mitgeschrieben. Gilt ab der "
                    "nächsten Verbindung; nur mit diesem Gurt.",
                ),
            ),
            erweitert_kopf,
            erweitert_teil,
            ft.OutlinedButton(
                "Alles auf Standard zurücksetzen",
                icon=ft.Icons.SETTINGS_BACKUP_RESTORE,
                on_click=fragen,
                disabled=e == standard
                and state.korrekturregeln() == Korrekturregeln()
                and state.ansicht() == Ansicht(),
            ),
        ],
    )
    return ft.View(
        route="/einstellungen/hrv",
        appbar=ft.AppBar(title=ft.Text("HRV-Messung")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["einstellungen_hrv", "regeln_text"]
