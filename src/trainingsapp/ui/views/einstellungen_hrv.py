"""Einstellungen → HRV-Messung — Route `/einstellungen/hrv`.

Alles, was sich an der Messung einstellen lässt, an einer Stelle — mit
sinnvollen Vorgaben und einem Knopf, der alles auf diese Vorgaben zurücksetzt.
Die kleinen Knöpfe in der Messansicht (Fensterbreite, „korrigiert", Regler,
Kurvenmenü) ändern dieselben Werte; was man dort einstellt, steht auch hier.

- Anzeige: Reiter „Messung" ein/aus — ohne Gerät spart das Platz.
- Kacheln über der Kurve, nach Bereichen gruppiert.
- Kurven: Live-Fenster, „korrigiert", pNNx-Schwelle, Kurvenansicht.
- Analyse: Frequenz und Nichtlinear anbieten (bei optischen Sensoren aus).
- Notizen: Übungen aus Plänen anbieten.
- Automatische Korrektur: die Regeln (`hrv_core.regeln`).

Unter Namen gespeicherte Kurvenansichten bleiben beim Zurücksetzen erhalten.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.hrv_ansicht import PNN_WAHL, Ansicht
from trainingsapp.core.hrv_einstellungen import LIVE_FENSTER, HrvEinstellungen
from trainingsapp.hrv_core.regeln import Korrekturregeln
from trainingsapp.ui.components.kacheln import GRUPPEN, KACHELN
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlauf import FARBEN, fenster_text
from trainingsapp.ui.state import AppState


def regeln_text(r: Korrekturregeln) -> str:
    """Kurzfassung der Korrekturregeln für die Einstellungsseite.

    >>> for teil in regeln_text(Korrekturregeln()).split(" · "):
    ...     print(teil)
    Malik nach Sensor (EKG 20 %, optisch 30 %)
    250–2000 ms
    Sensor-Fehler ab 50 ms
    Verworfenes selbst prüfen
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
        teile.append(f"Sensor-Fehler ab {r.fehler_max_ms} ms")
    teile.append("Verworfenes selbst prüfen" if r.selbst_pruefen else "dem Sensor folgen")
    return " · ".join(teile)


def einstellungen_hrv(page: Any, state: AppState) -> ft.View:
    e = state.hrv_einstellungen()
    ansicht = state.ansicht()

    def setzen(**werte: Any) -> None:
        for name, wert in werte.items():
            setattr(e, name, wert)
        state.hrv_einstellungen_setzen(e)

    def schalter(name: str, label: str, untertitel: str = "", **extra: Any) -> ft.Control:
        def handler(ev: ft.Event[ft.Switch]) -> None:
            setzen(**{name: bool(ev.control.value)})
            state.neu_zeichnen()  # Abhängiges (z. B. optisch) neu einblenden

        return ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Switch(label=label, value=getattr(e, name), on_change=handler, **extra),
                ft.Container(
                    padding=ft.Padding.only(left=60, bottom=4),
                    content=hinweis(untertitel),
                    visible=bool(untertitel),
                ),
            ],
        )

    # -- Kacheln ---------------------------------------------------------------

    def kachel_umschalter(key: str) -> Callable[[], None]:
        def handler() -> None:
            gewaehlt = set(e.kacheln) ^ {key}
            # Reihenfolge wie im Katalog: große Kacheln zuerst
            setzen(kacheln=[k for _, keys in GRUPPEN for k in keys if k in gewaehlt])
            state.neu_zeichnen()

        return handler

    def kachel_chip(key: str) -> ft.Control:
        art = KACHELN[key]
        farbe = FARBEN.get(art.kennzahl or "")
        return ft.Chip(
            label=ft.Text(art.titel, size=12),
            leading=ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe)
            if farbe
            else None,
            selected=key in e.kacheln,
            on_select=kachel_umschalter(key),
            show_checkmark=True,
            tooltip=art.erklaerung or None,
        )

    kachel_gruppen: list[ft.Control] = []
    for gruppe, keys in GRUPPEN:
        kachel_gruppen.append(ft.Text(gruppe, size=12, weight=ft.FontWeight.W_600, opacity=0.8))
        kachel_gruppen.append(
            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[kachel_chip(k) for k in keys])
        )

    # -- Kurven ----------------------------------------------------------------

    def fenster_gewaehlt(ev: ft.Event[ft.SegmentedButton]) -> None:
        if ev.control.selected:
            setzen(fenster_s=int(ev.control.selected[0]))

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

        page.show_dialog(
            korrektur_blatt(
                state.korrekturregeln(), aendern, erweitert=True, schliessen=page.pop_dialog
            )
        )

    def regeln_zuruecksetzen() -> None:
        state.korrekturregeln_setzen(Korrekturregeln())
        regeln_zeile.value = regeln_text(Korrekturregeln())
        page.show_dialog(ft.SnackBar(ft.Text("Korrektur auf Vorgabe zurückgesetzt.")))
        page.update()

    # -- Alles zurücksetzen -------------------------------------------------------

    def alles_zuruecksetzen() -> None:
        state.hrv_zuruecksetzen()
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text("HRV-Einstellungen auf Standard zurückgesetzt.")))
        state.neu_zeichnen()

    def fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Alles zurücksetzen?"),
                content=ft.Text(
                    "Kacheln, Fenster, Kurven, Analysebereiche und die automatische "
                    "Korrektur gehen auf die Vorgaben zurück. Gespeicherte Ansichten und "
                    "Messungen bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Zurücksetzen", on_click=alles_zuruecksetzen),
                ],
            )
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
                titel("Kacheln über der Kurve"),
                hinweis(
                    "Große Kacheln stehen zu zweit, die übrigen zu dritt. Kacheln einer "
                    "Kurve rechnen mit deren Fenster und tragen ihre Farbe."
                ),
                *kachel_gruppen,
            ),
            karte(
                titel("Kurven"),
                ft.Text("Zeitfenster live", size=12, opacity=0.8),
                ft.SegmentedButton(
                    selected=[str(e.fenster_s)],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=str(s), label=ft.Text(fenster_text(s)))
                        for s in LIVE_FENSTER
                    ],
                    on_change=fenster_gewaehlt,
                ),
                schalter(
                    "korrigiert",
                    "Live die korrigierte Kurve zeigen",
                    "Artefakte überbrückt — nur die Anzeige; gespeichert werden immer "
                    "die Rohwerte.",
                ),
                ft.Dropdown(
                    label="Schwelle für pNNx",
                    value=str(ansicht.pnn_ms),
                    options=[ft.DropdownOption(key=str(x), text=f"{x} ms") for x in PNN_WAHL],
                    on_select=pnn_gewaehlt,
                    dense=True,
                    width=200,
                ),
                hinweis(
                    "Welche Verlaufskurven mit welchem Fenster zu sehen sind, stellt man in "
                    "der Messung über das Kurvenmenü ein (Fenster, gleitend oder Blöcke)."
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
