"""„Medium hinzufügen“ — überall dasselbe Menü (Ben, 19.11.2026,
`docs/plan_medien_einheitlich.md` §2.1: „wenn Medien hinzugefügt werden, sollen alle Typen
gleichermaßen angeboten werden, Links, Fotos, Videos, ‚aus der Fotoauswahl‘, Datei wählen“).

Bis dahin baute jede Stelle ihr eigenes Menü (Übung, Planübung, Plan, Weg, Kurs) — mit
verschiedenen Reihen. Hier steht die **eine Reihe**:

    Link · Foto aufnehmen · Video aufnehmen · Aus der Fotoauswahl · Datei wählen ·
    Audio aufnehmen · Aus vorhandenen Medien …

Was das Gerät nicht kann, fehlt (Kamera: Android, iOS, Web; Fotoauswahl: mit `flet_hochladen`);
was die Stelle nicht kann, lässt sie in `Wege` weg. *Wie* ein Stück an seine Stelle kommt (ins
Formular, sofort in die Datenbank, über die Ablage), entscheidet die Stelle — sie gibt die
Rückrufe.

„Aus vorhandenen Medien …“ (`vorhandene_blatt`): ein Verweis auf dieselbe Datei bzw. Adresse,
keine Kopie (`core/medien_vorrat.py`).
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import AUDIO, BILD, DOKUMENT, VIDEO
from trainingsapp.core.medien_vorrat import Vorhanden, passt, uebernommen, vorrat
from trainingsapp.core.models import Media
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.medienliste import SYMBOLE

#: Die Aufnahme-Arten — **eine** Tabelle für Namen und Symbole, auch für die Anhänge an Notiz
#: und Eintrag (`components/tagesnotiz.py`, `views/leistungen.py`): Art → (kurz, lang, Symbol)
AUFNAHME: dict[str, tuple[str, str, ft.IconData]] = {
    BILD: ("Foto", "Foto aufnehmen", ft.Icons.CAMERA_ALT_OUTLINED),
    VIDEO: ("Video", "Video aufnehmen", ft.Icons.VIDEOCAM_OUTLINED),
    AUDIO: ("Audio", "Audio aufnehmen", ft.Icons.MIC_NONE),
    DOKUMENT: ("Dokument", "Dokument aufnehmen", ft.Icons.DOCUMENT_SCANNER_OUTLINED),
}
#: … und die Fotoauswahl: (kurz, lang, Symbol)
FOTOAUSWAHL: tuple[str, str, ft.IconData] = (
    "Hochladen",
    "Aus der Fotoauswahl",
    ft.Icons.PHOTO_LIBRARY_OUTLINED,
)
#: So viele Stücke zeigt das Blatt höchstens — darüber hilft die Suche
DECKEL = 40


@dataclass(frozen=True, slots=True)
class Wege:
    """Was die Stelle kann — ein Rückruf je Weg, ``None`` = gibt es hier nicht.

    ``link``: eine leere Linkzeile bzw. das Link-Blatt; ``datei``: Datei vom Gerät wählen;
    ``aufnehmen``: Kamera bzw. Rekorder mit der Art (`core.anhaenge.BILD` · ``VIDEO`` ·
    ``AUDIO``); ``fotoauswahl``: aus der Fotoauswahl; ``vorhandenes``: bekommt das gewählte
    Stück (schon als Verweis für die neue Stelle, `core.medien_vorrat.uebernommen`).
    Rückrufe dürfen ``async`` sein."""

    link: Callable[[], Any] | None = None
    datei: Callable[[], Any] | None = None
    aufnehmen: Callable[[str], Any] | None = None
    fotoauswahl: Callable[[], Any] | None = None
    vorhandenes: Callable[[Media], Any] | None = None


def _rufen(page: Any, f: Callable[..., Any], *args: Any) -> None:
    if inspect.iscoroutinefunction(f):
        page.run_task(f, *args)
    else:
        f(*args)


def eintraege(
    page: Any,
    state: Any,
    wege: Wege,
    *,
    vorhandene: Callable[[], list[Vorhanden]] | None = None,
) -> list[tuple[str, str, ft.IconData, Callable[[Any], None]]]:
    """Die Reihe als (Kennung, Text, Symbol, Handler) — immer in derselben Ordnung."""
    from trainingsapp.ui.views.anhang_aufnahme import kamera_moeglich

    reihe: list[tuple[str, str, ft.IconData, Callable[[Any], None]]] = []

    def dazu(kennung: str, text: str, symbol: ft.IconData, f: Callable[..., Any], *a: Any) -> None:
        def handler(_e: Any = None) -> None:
            _rufen(page, f, *a)

        reihe.append((kennung, text, symbol, handler))

    if wege.link is not None:
        dazu("link", "Link …", ft.Icons.ADD_LINK, wege.link)
    if wege.aufnehmen is not None and kamera_moeglich(page):
        dazu("foto", AUFNAHME[BILD][1], AUFNAHME[BILD][2], wege.aufnehmen, BILD)
        dazu("video", AUFNAHME[VIDEO][1], AUFNAHME[VIDEO][2], wege.aufnehmen, VIDEO)
    if wege.fotoauswahl is not None and getattr(state, "hochladen", None) is not None:
        dazu("fotoauswahl", FOTOAUSWAHL[1], FOTOAUSWAHL[2], wege.fotoauswahl)
    if wege.datei is not None:
        dazu("datei", "Datei wählen …", ft.Icons.FOLDER_OPEN_OUTLINED, wege.datei)
    if wege.aufnehmen is not None:
        dazu("ton", AUFNAHME[AUDIO][1], AUFNAHME[AUDIO][2], wege.aufnehmen, AUDIO)
    if wege.vorhandenes is not None and vorhandene is not None:
        waehlen = wege.vorhandenes

        def oeffnen() -> None:
            page.show_dialog(vorhandene_blatt(page, vorhandene(), waehlen))

        dazu("vorhandenes", "Aus vorhandenen Medien …", ft.Icons.PERM_MEDIA_OUTLINED, oeffnen)
    return reihe


def menue(
    page: Any,
    state: Any,
    wege: Wege,
    *,
    text: str = "Medium hinzufügen",
    tooltip: str = "Link, Foto, Video, Ton oder Datei — oder eines, das es schon gibt",
    vorhandene: Callable[[], list[Vorhanden]] | None = None,
    kennung: str = "medium_dazu",
) -> ft.PopupMenuButton:
    """Der Knopf „Medium hinzufügen“ mit der einen Reihe. Die Einträge tragen
    ``data = (kennung, <weg>)`` — ``<weg>``: link · foto · video · fotoauswahl · datei · ton ·
    vorhandenes."""
    return ft.PopupMenuButton(
        content=ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.ADD, size=18, color=ft.Colors.PRIMARY),
                ft.Text(text, color=ft.Colors.PRIMARY),
            ],
        ),
        tooltip=tooltip,
        items=[
            ft.PopupMenuItem(content=titel, icon=symbol, on_click=handler, data=(kennung, weg))
            for weg, titel, symbol, handler in eintraege(page, state, wege, vorhandene=vorhandene)
        ],
        data=kennung,
    )


def vorrat_von(
    state: Any, *, zuerst: Iterable[tuple[Media, str]] = (), ohne: Collection[str] = ()
) -> list[Vorhanden]:
    """Der Vorrat aus der Datenbank: Übungen des Katalogs und Pläne des Profils — ``zuerst``
    vorn (die Stücke der Stelle, an der man arbeitet)."""
    try:
        uebungen = state.uebungen.alle()
        plaene = state.plaene.alle(state.profil.id)
    except Exception:
        uebungen, plaene = [], []
    return vorrat(uebungen, plaene, zuerst=zuerst, ohne=ohne)


def vorhandene_blatt(
    page: Any, stuecke: list[Vorhanden], waehlen: Callable[[Media], Any]
) -> ft.BottomSheet:
    """Das Blatt „Aus vorhandenen Medien“: Suche, je Stück eine Zeile (Art, Titel, wo es schon
    steht); ein Tipp übernimmt es als Verweis und schließt."""
    liste = ft.Column(spacing=0, tight=True)
    suche = ft.TextField(
        hint_text="Suchen …",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        data="vorhandene_suche",
    )

    def gewaehlt(v: Vorhanden) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            schliessen(blatt)
            _rufen(page, waehlen, uebernommen(v.medium))

        return handler

    def zeichnen(_e: Any = None) -> None:
        treffer = [v for v in stuecke if passt(v, suche.value or "")]
        zeilen: list[ft.Control] = [
            ft.ListTile(
                leading=ft.Icon(SYMBOLE.get(v.medium.kind, ft.Icons.PLAY_CIRCLE_OUTLINE)),
                title=ft.Text(v.medium.title or v.medium.uri, max_lines=1),
                subtitle=ft.Text(v.wo_text, size=11, opacity=0.6, max_lines=1),
                on_click=gewaehlt(v),
                content_padding=ft.Padding.only(left=0, right=0),
                dense=True,
                data=("vorhandenes", v.medium.uri),
            )
            for v in treffer[:DECKEL]
        ]
        if not treffer:
            zeilen.append(
                ft.Text(
                    "Noch keine Medien — erst eines aufnehmen, wählen oder verlinken."
                    if not stuecke
                    else "Nichts gefunden.",
                    opacity=0.7,
                )
            )
        elif len(treffer) > DECKEL:
            zeilen.append(
                ft.Text(f"… und {len(treffer) - DECKEL} weitere — suchen", size=12, opacity=0.6)
            )
        liste.controls = zeilen
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    suche.on_change = zeichnen
    zeichnen()
    blatt: ft.BottomSheet = ft.BottomSheet(
        scrollable=True,
        content=blatt_spalte(
            [
                ft.Text("Aus vorhandenen Medien", size=18, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Dieselbe Datei, keine Kopie — Zeitpunkt und Rolle stellst du hier neu ein.",
                    size=12,
                    opacity=0.7,
                ),
                suche,
                liste,
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(blatt))
                    ],
                )
            ],
        ),
        data="vorhandene_blatt",
    )
    return blatt


__all__ = [
    "AUFNAHME",
    "DECKEL",
    "FOTOAUSWAHL",
    "Wege",
    "eintraege",
    "menue",
    "vorhandene_blatt",
    "vorrat_von",
]
