"""Einstellungen → Anhänge — Route `/einstellungen/anhaenge` (Ben, 19.10.2026;
`docs/plan_anhaenge.md`, Teil E).

Qualität der Aufnahmen (klein · mittel · groß, `core.anhaenge.Qualitaet`) und die längste
Videoaufnahme — beides gilt für künftige Aufnahmen (`app_setting`). Darunter der
**Überblick**: Gesamtgröße, Anzahl Fotos, Videos und Audioaufnahmen (auch die am Tag,
seit 22.10.2026), Monatsgruppen mit Größe, je Gruppe
aufklappbar zur Kachelreihe; Mehrfachauswahl (Kachel antippen) und „Löschen“ mit
Rückfrage „12 Aufnahmen, 180 MB — endgültig“. Schnellweg „Videos älter als 3 Monate“.
Aufräumen: verwaiste Dateien (Datei ohne Zeile) und fehlende Dateien (Zeile ohne Datei).

Ben: „Da sich viel ansammeln könnte, muss der Speicher geleert werden können bzw. die
Videos/Photos im Überblick bleiben.“ Löschen ist endgültig — ein Papierkorb hielte den
Speicher belegt, den man gerade leeren will (Plan G3).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    VIDEO_MAX_WAHL,
    Anhang,
    AnhangMitBezug,
    Monatsgruppe,
    Qualitaet,
    aufraeumen_vorschlag,
    fehlende,
    groesse_text,
    monatsgruppen,
    verwaiste,
    zusammenfassung,
)
from trainingsapp.data.anhaenge import (
    qualitaet_lesen,
    qualitaet_setzen,
    video_max_s,
    video_max_setzen,
)
from trainingsapp.ui.components.anhang_reihe import kachel
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang import anhang_route

ROUTE = "/einstellungen/anhaenge"
HINWEIS = (
    "Aufnahmen liegen nur auf diesem Gerät, im privaten Speicher der App (Ordner „Anhaenge“, "
    "nach Monaten). Sie gehen nie in Export, Backup oder Synchronisation — hinaus kommt eine "
    "Aufnahme nur, wenn du sie selbst in ihrer Ansicht teilst."
)


def _zahl(n: int, einzahl: str, mehrzahl: str) -> str:
    """„1 Aufnahme“, „3 Aufnahmen“.

    >>> _zahl(1, "Verweis", "Verweise"), _zahl(2, "Verweis", "Verweise")
    ('1 Verweis', '2 Verweise')
    """
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def einstellungen_anhaenge(page: Any, state: AppState) -> ft.View:
    repo = state.anhaenge
    einstellungen = state.einstellungen
    heute = state.heute()
    #: ausgewählte Anhang-IDs (Mehrfachauswahl) und aufgeklappte Monate — nur diese Ansicht
    auswahl: set[str] = set()
    offen: set[tuple[int, int]] = set()

    def neu() -> None:
        state.neu_zeichnen()

    # -- Qualität und Videolänge -----------------------------------------------------------

    def qualitaet_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            qualitaet_setzen(einstellungen, Qualitaet.lesen(str(e.control.selected[0])))
            neu()

    def video_max_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        with contextlib.suppress(ValueError, TypeError):
            video_max_setzen(einstellungen, int(e.control.value or 0))

    q = qualitaet_lesen(einstellungen)
    qualitaet_karte = karte(
        titel("Aufnahmen"),
        ft.SegmentedButton(
            selected=[q.value],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=x.value, label=ft.Text(x.label.split(" · ")[0])) for x in Qualitaet
            ],
            on_change=qualitaet_gewaehlt,
        ),
        hinweis(f"{q.label}: {q.richtwert}. Gilt für neue Aufnahmen; die mittlere Stufe reicht."),
        ft.Dropdown(
            label="Längste Videoaufnahme",
            value=str(video_max_s(einstellungen)),
            options=[
                ft.DropdownOption(key=str(s), text=text) for s, text in VIDEO_MAX_WAHL.items()
            ],
            on_select=video_max_gewaehlt,
            expand=True,
        ),
        hinweis(
            "Die Aufnahme endet von selbst, wenn die Zeit um ist. Ein Video liegt beim "
            "Speichern einmal ganz im Arbeitsspeicher — lange Aufnahmen werden auf älteren "
            "Geräten eng."
        ),
    )

    # -- Überblick -----------------------------------------------------------------------

    alle = repo.alle(state.profil.id)
    gruppen = monatsgruppen(alle)
    umfang = zusammenfassung(x.anhang for x in alle)
    katalog = {u.id: u.name for u in state.uebungen.alle(mit_geloeschten=True)}

    def oeffner(a: Anhang) -> Callable[[], Any]:
        def handler() -> None:
            if auswahl:  # im Auswahlmodus wählt ein Tipp
                umschalten(a.id)
                return
            page.run_task(page.push_route, anhang_route(ROUTE, a.id))

        return handler

    def umschalten(anhang_id: str) -> None:
        if anhang_id in auswahl:
            auswahl.discard(anhang_id)
        else:
            auswahl.add(anhang_id)
        zeichnen()

    def waehler(a: Anhang) -> Callable[[], None]:
        return lambda: umschalten(a.id)

    def gruppe_waehlen(g: Monatsgruppe) -> Callable[[], None]:
        def handler() -> None:
            ids = {x.anhang.id for x in g.anhaenge}
            if ids <= auswahl:
                auswahl.difference_update(ids)
            else:
                auswahl.update(ids)
            zeichnen()

        return handler

    def klappen(g: Monatsgruppe) -> Callable[[], None]:
        def handler() -> None:
            schluessel = (g.jahr, g.monat)
            if schluessel in offen:
                offen.discard(schluessel)
            else:
                offen.add(schluessel)
            zeichnen()

        return handler

    def kachel_mit_wahl(x: AnhangMitBezug) -> ft.Control:
        a = x.anhang
        gewaehlt = a.id in auswahl
        if a.zum_tag is not None:
            name = f"Zum Tag · {a.zum_tag:%d.%m.}"
        else:
            name = katalog.get(x.exercise_id or "", "Übung")
        if x.eintrag_geloescht:
            name += " (Eintrag gelöscht)"
        k = kachel(a, repo.bild(a), oeffner(a), unterschrift=f"{a.tag:%d.%m.}")
        return ft.GestureDetector(
            on_long_press_start=waehler(a),
            content=ft.Container(
                padding=2,
                border_radius=12,
                border=ft.Border.all(2, ft.Colors.PRIMARY if gewaehlt else ft.Colors.TRANSPARENT),
                bgcolor=ft.Colors.PRIMARY_CONTAINER if gewaehlt else None,
                tooltip=name + (f" · {a.note}" if a.note else ""),
                content=k,
            ),
        )

    def gruppen_zeile(g: Monatsgruppe) -> ft.Control:
        u = zusammenfassung(x.anhang for x in g.anhaenge)
        auf = (g.jahr, g.monat) in offen
        alle_gewaehlt = {x.anhang.id for x in g.anhaenge} <= auswahl
        kopf = ft.ListTile(
            leading=ft.Icon(ft.Icons.EXPAND_LESS if auf else ft.Icons.EXPAND_MORE, opacity=0.7),
            title=ft.Text(g.label),
            subtitle=ft.Text(f"{u.text} · {groesse_text(u.bytes)}", size=12),
            trailing=ft.IconButton(
                ft.Icons.CHECK_BOX if alle_gewaehlt else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                tooltip="Monat auswählen",
                on_click=gruppe_waehlen(g),
            ),
            on_click=klappen(g),
            content_padding=ft.Padding.only(left=0, right=0),
        )
        teile: list[ft.Control] = [kopf]
        if auf:
            teile.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[kachel_mit_wahl(x) for x in g.anhaenge],
                )
            )
        return ft.Column(spacing=4, tight=True, controls=teile)

    # -- Löschen -------------------------------------------------------------------------

    def loeschen_fragen(ids: list[str], warum: str) -> None:
        if not ids:
            return
        betroffen = zusammenfassung(x.anhang for x in alle if x.anhang.id in set(ids))
        nachher = Nachher()

        def loeschen() -> None:
            repo.loeschen_viele(ids)
            auswahl.clear()
            nachher.danach(
                lambda: page.show_dialog(
                    ft.SnackBar(
                        ft.Text(f"{len(ids)} Aufnahme{'n' if len(ids) != 1 else ''} gelöscht")
                    )
                )
            )
            nachher.danach(neu)
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{warum} löschen?"),
            content=ft.Text(
                f"{betroffen.text}, {groesse_text(betroffen.bytes)} — endgültig, es gibt "
                "keinen Papierkorb für Aufnahmen."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=loeschen),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    def auswahl_loeschen() -> None:
        loeschen_fragen(sorted(auswahl), "Ausgewählte Aufnahmen")

    def alte_videos() -> None:
        grenze = heute - timedelta(days=91)
        vorschlag = aufraeumen_vorschlag(alle, grenze)
        if not vorschlag:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Videos älter als 3 Monate.")))
            return
        loeschen_fragen([x.anhang.id for x in vorschlag], "Videos älter als 3 Monate")

    def auswahl_aufheben() -> None:
        auswahl.clear()
        zeichnen()

    # -- Aufräumen -----------------------------------------------------------------------

    try:
        dateien = repo.dateien()
    except OSError:
        dateien = []
    zeilen = repo.alle_zeilen()
    verwaist = verwaiste(dateien, zeilen)
    fehlend = fehlende(zeilen, dateien)

    def verwaiste_loeschen() -> None:
        n = 0
        for relativ in verwaist:
            with contextlib.suppress(OSError, ValueError):
                repo.datei_loeschen(relativ)
                n += 1
        page.show_dialog(
            ft.SnackBar(ft.Text(f"{n} verwaiste Datei{'en' if n != 1 else ''} gelöscht"))
        )
        neu()

    def fehlende_entfernen() -> None:
        for a in fehlend:
            repo.loeschen(a.id)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"{len(fehlend)} Verweis{'e' if len(fehlend) != 1 else ''} entfernt")
            )
        )
        neu()

    aufraeumen: list[ft.Control] = []
    if verwaist:
        groesse_verwaist = sum(
            (repo.wurzel / d).stat().st_size for d in verwaist if (repo.wurzel / d).is_file()
        )
        aufraeumen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.CLEANING_SERVICES_OUTLINED),
                title=ft.Text(
                    f"{len(verwaist)} verwaiste Datei{'en' if len(verwaist) != 1 else ''}"
                ),
                subtitle=ft.Text(
                    f"Ohne Eintrag (Abbruch beim Speichern) · {groesse_text(groesse_verwaist)}",
                    size=12,
                ),
                trailing=ft.TextButton("Löschen", on_click=verwaiste_loeschen),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )
    if fehlend:
        aufraeumen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED),
                title=ft.Text(
                    f"{len(fehlend)} Aufnahme{'n' if len(fehlend) != 1 else ''} ohne Datei"
                ),
                subtitle=ft.Text("Die Datei fehlt — der Verweis zeigt „fehlt“", size=12),
                trailing=ft.TextButton("Entfernen", on_click=fehlende_entfernen),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )
    if not aufraeumen:
        aufraeumen.append(hinweis("Nichts aufzuräumen — jede Datei hat ihren Eintrag."))

    # -- Zusammenbau ---------------------------------------------------------------------

    liste = ft.Column(spacing=4, tight=True)
    kopfzeile = ft.Row(spacing=8, wrap=True, run_spacing=6)

    def zeichnen() -> None:
        liste.controls = [gruppen_zeile(g) for g in gruppen] or [
            hinweis(
                "Noch keine Aufnahmen. Sie entstehen in den Leistungen einer Übung und an der "
                "Notiz zum Tag (Foto, Video, Audio)."
            )
        ]
        if auswahl:
            gewaehlt = zusammenfassung(x.anhang for x in alle if x.anhang.id in auswahl)
            kopfzeile.controls = [
                ft.Text(f"Ausgewählt: {gewaehlt.text} · {groesse_text(gewaehlt.bytes)}", size=13),
                ft.TextButton("Aufheben", on_click=auswahl_aufheben),
                ft.FilledTonalButton(
                    "Löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=auswahl_loeschen
                ),
            ]
        else:
            kopfzeile.controls = [
                ft.Text(
                    f"{umfang.text} · {groesse_text(umfang.bytes)}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                *(
                    [ft.TextButton("Videos älter als 3 Monate …", on_click=alte_videos)]
                    if umfang.videos
                    else []
                ),
            ]
        for c in (liste, kopfzeile):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    zeichnen()
    ansicht = ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Anhänge")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        qualitaet_karte,
                        karte(
                            titel("Überblick"),
                            kopfzeile,
                            hinweis(
                                "Monat antippen: aufklappen. Kachel lang drücken: auswählen — "
                                "dann wählt jeder Tipp dazu; Häkchen rechts: ganzer Monat."
                            ),
                            liste,
                        ),
                        karte(titel("Aufräumen"), *aufraeumen),
                        karte(titel("Wo liegen die Aufnahmen?"), hinweis(HINWEIS)),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return scroll_merken(page, state, ROUTE, ansicht)


__all__ = ["ROUTE", "einstellungen_anhaenge"]
