"""Titel und Beschreibung einer HRV-Messung — zurückhaltend oben in der Ansicht.

Eine Messung hat drei Arten Notiz, wie in praxis_gui: **Überschrift**
(``titel``), **Beschreibung** (``notiz``) und die **Notizen mit Zeitstempel**
(``ereignisse``, `notizen.Notizfeld`). Die ersten beiden stehen hier: als
Kopfzeile, die man antippt, und als Blatt zum Bearbeiten — mit Vorschlägen,
allen voran dem Plan, der während der Messung geübt wurde.

Die Überschrift wählt man aus einer **gespeicherten Liste** (Ben, 26.10.2026:
„vordefinieren und auffindbar wieder abrufen“ — bei zehn Überschriften wären Chips
eine Wolke): Unter dem Titelfeld stehen die Überschriften des Profils
(`core.models.HrvTitel`, angeheftete zuerst, dann die zuletzt vergebene), Tippen
filtert sie, Antippen übernimmt, ✕ rechts nimmt eine aus der Liste (die Messungen
behalten ihren Titel). Höchstens `MAX_ZEILEN` Zeilen, der Rest steht als „+n weitere“;
die Liste hat ab dem Öffnen eine feste Höhe, damit das Titelfeld beim Tippen nicht
wandert (Ben, 26.10.2026). Was neu eingetippt ist, lässt sich mit „merken“ aufnehmen; jede
vergebene Überschrift kommt beim Speichern ohnehin hinein (`HrvRepo.titel_merken`).
Darüber stehen, abgesetzt, die Vorschläge aus dem Zusammenhang: der geübte Plan und das
Timerprofil (`titel_vorschlaege`). Pflegen lässt sich die Liste auch unter
Einstellungen → HRV-Messung → Überschriften.

Die Felder gehören in die Messdatei (`hrv_core.ereignisse.metadaten_schreiben`);
wohin gespeichert wird, entscheidet der Aufrufer (``speichern``): nachträglich
in die Datei, live in die laufende Aufnahme. Wischt man das Blatt weg oder tippt
daneben, gilt das wie „Speichern“ (Ben, 16.10.2026: Autosave); nur „Abbrechen“
verwirft.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

import flet as ft

from trainingsapp.core.models import HrvTitel
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen

#: So weit vor und nach der Messung zählen Planeinträge noch zu ihr
RAND = timedelta(minutes=10)
#: Höchstens so viele Vorschläge aus dem Zusammenhang (Pläne, Timer)
MAX_VORSCHLAEGE = 3
#: Höchstens so viele Zeilen zeigt die Liste im Blatt (Ben, 26.10.2026: „sonst wird die
#: Scrollbar zu groß“) — darüber hinaus filtert das Tippen
MAX_ZEILEN = 7
#: Höhe einer Zeile der Liste (dichte `ListTile`, px)
ZEILE = 48

_TIMER = re.compile(r"^Timer „(.+?)“")


def geuebte_plaene(state: Any, von: datetime, bis: datetime) -> list[str]:
    """Namen der Pläne, aus denen während der Messung (± `RAND`) eingetragen wurde.

    Die meisten Einträge zuerst — der erste ist „der Plan" der Messung.
    """
    namen = []
    for plan_id in state.sitzungen.plaene_waehrend(state.profil.id, von - RAND, bis + RAND):
        plan = state.plaene.laden(plan_id)
        if plan is not None:
            namen.append(plan.name)
    return namen


def titel_vorschlaege(
    state: Any,
    von: datetime,
    bis: datetime,
    ereignisse: Iterable[dict] = (),
) -> list[str]:
    """Namensvorschläge aus dem Zusammenhang: geübte Pläne, Timerprofil.

    ``state`` ist der `AppState`. Ein Plan zählt, wenn während der Messung
    (± `RAND`) etwas aus ihm eingetragen wurde — die meisten Einträge zuerst. Die
    gespeicherten Überschriften kommen getrennt dazu (`HrvRepo.titel_liste`).
    """
    namen = geuebte_plaene(state, von, bis)
    for e in ereignisse:
        if m := _TIMER.match(str(e.get("text") or "")):
            namen.append(m.group(1))
            break
    eindeutig = list(dict.fromkeys(n.strip() for n in namen if n and n.strip()))
    return eindeutig[:MAX_VORSCHLAEGE]


def passende(gespeicherte: Iterable[HrvTitel], suche: str) -> list[HrvTitel]:
    """Die Überschriften, in denen ``suche`` vorkommt — ohne Suche alle, Reihenfolge bleibt.

    >>> t = [HrvTitel(name="Intervalle Beine"), HrvTitel(name="Ruhe morgens")]
    >>> [x.name for x in passende(t, "")]
    ['Intervalle Beine', 'Ruhe morgens']
    >>> [x.name for x in passende(t, " bei")]
    ['Intervalle Beine']
    """
    s = suche.strip().casefold()
    return [t for t in gespeicherte if not s or s in t.name.casefold()]


def titel_kopf(
    titel: str,
    beschreibung: str,
    bearbeiten: Callable[[], object],
    *,
    klein: bool = False,
    offen: bool = False,
    umklappen: Callable[[], object] | None = None,
) -> ft.Control:
    """Kopfzeile: Titel (oder leise „Titel hinzufügen"), darunter die Beschreibung.

    Antippen öffnet das Blatt. ``klein``: kompakt für die Live-Ansicht — die
    Beschreibung als eine Zeile, die sich mit ``umklappen`` ganz aufklappen lässt
    (``offen``; Ben, 17.10.2026: „ausklappbar, damit es nicht überladen ist“).
    """
    titel, beschreibung = titel.strip(), beschreibung.strip()
    stift = ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, opacity=0.55)
    if titel:
        haupt: ft.Control = ft.Text(
            titel,
            size=15 if klein else 18,
            weight=ft.FontWeight.W_600,
            max_lines=1 if klein else 2,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
    else:
        haupt = ft.Text(
            "Titel hinzufügen" if klein else "Titel und Beschreibung hinzufügen",
            size=13,
            color=ft.Colors.PRIMARY,
            expand=True,
        )
    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[haupt, stift] if titel else [stift, haupt],
        )
    ]
    if beschreibung and not klein:
        zeilen.append(
            ft.Text(
                beschreibung,
                size=13,
                opacity=0.75,
                max_lines=3,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    elif beschreibung:
        auszug = ft.Text(
            beschreibung,
            size=12,
            opacity=0.75,
            max_lines=None if offen else 1,
            overflow=ft.TextOverflow.CLIP if offen else ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
        zeilen.append(
            ft.Row(
                spacing=0,
                # Zu: Pfeil neben der einen Zeile; auf: am Ende des Absatzes
                vertical_alignment=(
                    ft.CrossAxisAlignment.END if offen else ft.CrossAxisAlignment.CENTER
                ),
                controls=[
                    auszug,
                    ft.IconButton(
                        ft.Icons.EXPAND_LESS if offen else ft.Icons.EXPAND_MORE,
                        icon_size=18,
                        visual_density=ft.VisualDensity.COMPACT,
                        tooltip="Beschreibung zuklappen" if offen else "Ganze Beschreibung",
                        on_click=lambda: umklappen(),
                    ),
                ]
                if umklappen is not None
                else [auszug],
            )
        )
    return ft.Container(
        on_click=lambda: bearbeiten(),
        border_radius=8,
        padding=ft.Padding.symmetric(vertical=4),
        content=ft.Column(spacing=2, tight=True, controls=zeilen),
    )


def titel_blatt(
    titel: str,
    beschreibung: str,
    vorschlaege: Sequence[str],
    speichern: Callable[[str, str], None],
    *,
    vorgabe: str = "",
    gespeicherte: Sequence[HrvTitel] = (),
    merken: Callable[[str], HrvTitel | None] | None = None,
    entfernen: Callable[[HrvTitel], None] | None = None,
) -> ft.BottomSheet:
    """Blatt zum Bearbeiten — Titel mit der Liste zum Antippen, Beschreibung darunter.

    ``vorgabe`` steht im leeren Titelfeld: der Plan, der während der Messung geübt
    wurde (Ben: „der Plan gilt als Namensvorschlag"). ``gespeicherte``: die Überschriften
    des Profils; Tippen filtert sie, ✕ ruft ``entfernen``, „merken“ ruft ``merken`` mit
    dem neuen Text (ohne die beiden Rückrufe fehlen ✕ und „merken“). Das Blatt schließt
    sich selbst (`dialoge.schliessen`); weggewischt speichert es, was geändert wurde.
    """
    titel_feld = ft.TextField(
        label="Titel",
        value=titel or vorgabe,
        dense=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    beschreibung_feld = ft.TextField(
        label="Beschreibung",
        value=beschreibung,
        hint_text="Wie war es? Was war besonders?",
        multiline=True,
        min_lines=2,
        max_lines=6,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    vorrat: list[HrvTitel] = list(gespeicherte)
    # Feste Höhe ab dem Öffnen (Ben, 26.10.2026: „es irritiert, dass sich mit dem Tippen die
    # Größe des Fensters verändert“): so viele Zeilen, wie beim Öffnen da sind, höchstens
    # `MAX_ZEILEN` — wird die Liste beim Filtern kürzer, bleibt unten Luft; wird sie länger
    # („merken“), scrollt sie in sich. Das Blatt misst seine Höhe sonst bei jeder Änderung.
    anfangs = len(vorschlaege) + len(vorrat)
    zeilen_hoehe = max(1, min(MAX_ZEILEN, anfangs) + (1 if anfangs > MAX_ZEILEN else 0))
    liste = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=zeilen_hoehe * ZEILE)
    #: Der zuletzt übernommene Name: solange er im Feld steht, zeigt die Liste alles
    stand = {"gewaehlt": (titel_feld.value or "").strip()}

    def eingabe() -> tuple[str, str]:
        return (titel_feld.value or "").strip(), (beschreibung_feld.value or "").strip()

    def nehmen(name: str) -> Callable[[], None]:
        def handler() -> None:
            titel_feld.value = name
            stand["gewaehlt"] = name
            liste_zeichnen()
            with contextlib.suppress(Exception):
                titel_feld.update()

        return handler

    def entferner(t: HrvTitel) -> Callable[[], None]:
        def handler() -> None:
            if entfernen is not None:
                entfernen(t)
            vorrat[:] = [x for x in vorrat if x.id != t.id]
            liste_zeichnen()

        return handler

    def merker(name: str) -> Callable[[], None]:
        def handler() -> None:
            if merken is None:
                return
            t = merken(name)
            if t is not None and all(x.id != t.id for x in vorrat):
                vorrat.append(t)
            stand["gewaehlt"] = name
            liste_zeichnen()

        return handler

    def zeile(
        name: str, symbol: ft.IconData, tipp: str, *, rechts: ft.Control | None = None
    ) -> ft.Control:
        return ft.ListTile(
            dense=True,
            content_padding=ft.Padding.only(left=4, right=0),
            leading=ft.Icon(symbol, size=20, opacity=0.7, tooltip=tipp),
            title=ft.Text(name, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            trailing=rechts,
            on_click=nehmen(name),
        )

    def liste_zeichnen() -> None:
        text = (titel_feld.value or "").strip()
        suche = "" if text == stand["gewaehlt"] else text
        zeilen: list[ft.Control] = [
            zeile(n, ft.Icons.AUTO_AWESOME_OUTLINED, "Aus Plan oder Timer")
            for n in vorschlaege
            if not suche or suche.casefold() in n.casefold()
        ]
        treffer = passende(vorrat, suche)
        rest = len(zeilen) + len(treffer) - MAX_ZEILEN
        for t in treffer[: max(0, MAX_ZEILEN - len(zeilen))]:
            symbol = (
                ft.Icons.PUSH_PIN
                if t.angeheftet
                else ft.Icons.HISTORY
                if t.zuletzt is not None
                else ft.Icons.BOOKMARK_BORDER
            )
            tipp = "Angeheftet" if t.angeheftet else "Gespeicherte Überschrift"
            kreuz = (
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=18,
                    visual_density=ft.VisualDensity.COMPACT,
                    tooltip="Aus der Liste nehmen",
                    on_click=entferner(t),
                )
                if entfernen is not None
                else None
            )
            zeilen.append(zeile(t.name, symbol, tipp, rechts=kreuz))
        if rest > 0:
            zeilen.append(
                ft.Container(
                    height=ZEILE,
                    padding=ft.Padding.only(left=16),
                    alignment=ft.Alignment.CENTER_LEFT,
                    content=ft.Text(f"+{rest} weitere — zum Filtern tippen", size=12, opacity=0.65),
                )
            )
        bekannt = {n.casefold() for n in vorschlaege} | {t.name.casefold() for t in vorrat}
        if text and merken is not None and text.casefold() not in bekannt:
            zeilen.append(
                ft.ListTile(
                    dense=True,
                    content_padding=ft.Padding.only(left=4, right=0),
                    leading=ft.Icon(
                        ft.Icons.BOOKMARK_ADD_OUTLINED, size=20, color=ft.Colors.PRIMARY
                    ),
                    title=ft.Text(f"„{text}“ merken", size=14, color=ft.Colors.PRIMARY),
                    on_click=merker(text),
                )
            )
        if not zeilen and not vorrat and not vorschlaege:
            zeilen.append(
                ft.Text(
                    "Noch keine gespeicherten Überschriften — was du vergibst, steht beim "
                    "nächsten Mal hier.",
                    size=12,
                    opacity=0.65,
                )
            )
        liste.controls = zeilen
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    titel_feld.on_change = lambda _: liste_zeichnen()
    liste_zeichnen()

    anfang = eingabe()
    #: Gespeichert oder abgebrochen — das Schließen danach tut nichts mehr
    erledigt: list[bool] = []

    def sichern() -> None:
        erledigt.append(True)
        speichern(*eingabe())
        schliessen(blatt)

    def abbrechen() -> None:
        erledigt.append(True)
        schliessen(blatt)

    def geschlossen(_e: object = None) -> None:
        """Weggewischt oder daneben getippt: geändert heißt gespeichert."""
        if not erledigt and eingabe() != anfang:
            erledigt.append(True)
            speichern(*eingabe())

    titel_feld.on_submit = lambda _: sichern()
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=geschlossen,
        # Knöpfe fest über der Navigationsleiste, der Rest scrollt (`components/blatt.py`)
        content=blatt_spalte(
            [
                ft.Text("Titel und Beschreibung", size=18, weight=ft.FontWeight.W_600),
                titel_feld,
                liste,
                beschreibung_feld,
                ft.Text(
                    "Beides steht in der Messdatei — praxis_gui zeigt es ebenso. "
                    "Notizen mit Zeitpunkt stehen unter der Kurve.",
                    size=12,
                    opacity=0.65,
                ),
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=abbrechen),
                        ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=sichern),
                    ],
                )
            ],
            geschaetzt=360,
            abstand=10,
        ),
    )
    return blatt


__all__ = [
    "MAX_VORSCHLAEGE",
    "MAX_ZEILEN",
    "RAND",
    "ZEILE",
    "geuebte_plaene",
    "passende",
    "titel_blatt",
    "titel_kopf",
    "titel_vorschlaege",
]
