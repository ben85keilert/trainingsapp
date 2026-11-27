"""Das Blatt „Titelbild“ — an jedem Medium dasselbe (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §3.2 und §9 b, c: „überall einheitlich“ · „Man fährt durch
und klickt ein Bild, kann einen Text dazusetzen“).

Oben die Karte, wie sie aussehen wird. Darunter:

1. **Aus dem Video** (nur bei einer Videodatei): der Spieler mit Zeitleiste, „Anfang · Mitte ·
   Ende“ springen dorthin, **„Dieses Bild nehmen“** hält das Bild an der Stelle fest
   (`ui/standbild.py`).
2. **Eigenes Bild** — eine Bilddatei (auf dem Handy die Auswahl des Systems); bereinigt ohne
   Ortsangabe in die Ablage der Paketdateien wie jedes Stück.
3. **Text auf dem Bild** — liegt über dem Bild, nicht darin. **„Nur Text“** nimmt das Bild weg.
4. **Automatisch** — zurück zur Vorgabe.

Das Blatt ändert nichts selbst: „Übernehmen“ gibt ``(titelbild, titelbild_text)`` zurück, der
Aufrufer schreibt es in sein Formular. Ein neues Bild ist bis zum Speichern dort nur vorgemerkt
(`Paketablage.entwurf_merken`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import titelbild as tb
from trainingsapp.core import videoinfo
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.models import Media, MediaKind
from trainingsapp.core.paketmedien import art_fuer, ist_paketmedium
from trainingsapp.ui import paketdatei, standbild
from trainingsapp.ui.components import medienkarte
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.karte import hinweis

#: Was unter dem Knopf „Titelbild …“ steht — je Wahl
STAND = {tb.AUTO: "automatisch", tb.BILD: "gewähltes Bild", tb.TEXT: "nur Text"}


def stand_text(titelbild: str, text: str = "") -> str:
    """Ein Wort zum Stand, für die Zeile neben dem Knopf.

    >>> stand_text(""), stand_text("text"), stand_text("", "Hüfte hoch")
    ('automatisch', 'nur Text', 'automatisch, mit Text')
    """
    art = tb.wahl(Media(uri="x", titelbild=titelbild)).art
    return STAND[art] + (", mit Text" if text.strip() and art != tb.TEXT else "")


def oeffnen(
    page: Any,
    state: Any,
    medium: Media,
    uebernehmen: Callable[[str, str], Any],
) -> None:
    """Zeigt das Blatt für ``medium`` (mit seinem jetzigen Titelbild und Text). ``uebernehmen``
    bekommt ``(titelbild, titelbild_text)``."""
    entwurf = {"bild": medium.titelbild, "text": medium.titelbild_text}
    ablage = state.pakete.ablage
    pfad = ablage.pfad(medium.uri) if ablage is not None and ist_paketmedium(medium) else None
    ist_video = pfad is not None and pfad.is_file() and medium.kind == MediaKind.VIDEO
    dauer_s = 0.0
    if ist_video and pfad is not None:
        with contextlib.suppress(Exception):
            info = videoinfo.lesen(pfad)
            dauer_s = float(info.dauer_s or 0) if info is not None else 0.0
    breite = max(220.0, min(float(getattr(page, "width", 0) or 380.0), 560.0) - 48)
    hoehe = round(breite * 9 / 16)

    vorschau = ft.Container(
        height=hoehe,
        border_radius=12,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        data="titelbild_vorschau",
    )
    meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False, data="titelbild_meldung")
    arbeitet = ft.ProgressBar(visible=False)
    text_feld = ft.TextField(
        label="Text auf dem Bild (optional)",
        hint_text="z. B. Hüfte bleibt oben",
        value=entwurf["text"],
        dense=True,
        data="titelbild_text",
    )
    nur_text = ft.Switch(
        label="Nur Text — kein Bild",
        value=entwurf["bild"] == tb.NUR_TEXT,
        data="titelbild_nur_text",
    )

    def jetzt() -> Media:
        return replace(
            medium,
            titelbild=entwurf["bild"],
            titelbild_text=str(text_feld.value or "").strip(),
        )

    def zeichnen() -> None:
        vorschau.content = medienkarte.flaeche(state, jetzt(), mit_knopf=False)
        nur_text.value = entwurf["bild"] == tb.NUR_TEXT
        for c in (vorschau, nur_text):
            with contextlib.suppress(Exception):
                c.update()

    def melden(text: str) -> None:
        meldung.value, meldung.visible = text, bool(text)
        with contextlib.suppress(Exception):
            meldung.update()

    def wartet(an: bool) -> None:
        arbeitet.visible = an
        with contextlib.suppress(Exception):
            arbeitet.update()

    async def bild_ablegen(daten: bytes) -> None:
        try:
            name = await paketdatei.ablegen(state, daten, "jpg")
        except (NichtBereinigbar, OSError) as fehler:
            melden(f"Nicht übernommen: {fehler}")
            return
        if ablage is not None:
            ablage.entwurf_merken(name)  # bis das Formular gespeichert ist
        entwurf["bild"] = name
        melden("")
        zeichnen()

    spieler: Any = None
    video_teil: list[ft.Control] = []
    if ist_video and pfad is not None:
        with contextlib.suppress(ImportError):
            from trainingsapp.ui.components.videospieler import Videospieler

            spieler = Videospieler([str(pfad)], hoehe=hoehe, breite=breite, state=state)

        async def nehmen(_e: Any = None) -> None:
            stelle = (await spieler.position_s()) if spieler is not None else None
            wartet(True)
            daten = await standbild.aus_video(state, pfad, stelle or 0.0)
            wartet(False)
            if daten is None:
                melden("Das Bild ließ sich nicht aus dem Video nehmen.")
                return
            await bild_ablegen(daten)

        def springer(anteil: float) -> Callable[..., Any]:
            async def handler(_e: Any = None) -> None:
                if spieler is not None and dauer_s > 0:
                    with contextlib.suppress(Exception):
                        await spieler._zu(round(max(dauer_s * anteil - 0.5, 0) * 1000))

            return handler

        if spieler is not None and standbild.moeglich(state):
            video_teil = [
                ft.Text("AUS DEM VIDEO", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                spieler.control,
                ft.Row(
                    spacing=6,
                    wrap=True,
                    controls=[
                        *(
                            ft.OutlinedButton(
                                wort, on_click=springer(anteil), data=("titelbild_stelle", wort)
                            )
                            for wort, anteil in (("Anfang", 0.0), ("Mitte", 0.5), ("Ende", 1.0))
                            if dauer_s > 0
                        ),
                        ft.FilledTonalButton(
                            "Dieses Bild nehmen",
                            icon=ft.Icons.PHOTO_CAMERA_OUTLINED,
                            on_click=nehmen,
                            data="titelbild_nehmen",
                        ),
                    ],
                ),
            ]
        else:
            video_teil = [
                hinweis(
                    "Auf diesem Gerät lässt sich kein Bild aus dem Video nehmen — ein eigenes "
                    "Bild oder nur Text gehen."
                )
            ]

    async def eigenes(_e: Any = None) -> None:
        gewaehlt = await paketdatei.datei_waehlen(page)
        if gewaehlt is None:
            return
        if art_fuer(gewaehlt.suffix.lstrip(".")) != MediaKind.IMAGE:
            melden("Das Titelbild braucht eine Bilddatei (JPG oder PNG).")
            return
        wartet(True)
        try:
            name = await paketdatei.ablegen(state, gewaehlt, gewaehlt.suffix)
        except (NichtBereinigbar, OSError) as fehler:
            melden(f"Nicht übernommen: {fehler}")
            return
        finally:
            wartet(False)
        if ablage is not None:
            ablage.entwurf_merken(name)
        entwurf["bild"] = name
        melden("")
        zeichnen()

    def nur_text_umgestellt(_e: Any = None) -> None:
        entwurf["bild"] = tb.NUR_TEXT if nur_text.value else ""
        zeichnen()

    def automatisch(_e: Any = None) -> None:
        entwurf["bild"] = ""
        zeichnen()

    nur_text.on_change = nur_text_umgestellt
    text_feld.on_change = lambda _e=None: zeichnen()
    vorschau.content = medienkarte.flaeche(state, jetzt(), mit_knopf=False)
    blatt: ft.BottomSheet

    async def zu() -> None:
        if spieler is not None:
            with contextlib.suppress(Exception):
                await spieler.anhalten()
        schliessen(blatt)

    async def fertig(_e: Any = None) -> None:
        await zu()
        uebernehmen(entwurf["bild"], str(text_feld.value or "").strip())

    async def abbrechen(_e: Any = None) -> None:
        await zu()

    blatt = ft.BottomSheet(
        scrollable=True,
        data="titelbild_blatt",
        content=blatt_spalte(
            [
                ft.Text("Titelbild", size=18, weight=ft.FontWeight.W_600),
                vorschau,
                arbeitet,
                meldung,
                *video_teil,
                ft.Text("ODER", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                ft.Row(
                    spacing=6,
                    wrap=True,
                    controls=[
                        ft.OutlinedButton(
                            "Eigenes Bild …",
                            icon=ft.Icons.IMAGE_OUTLINED,
                            on_click=eigenes,
                            data="titelbild_eigenes",
                        ),
                        ft.OutlinedButton(
                            "Automatisch",
                            icon=ft.Icons.RESTART_ALT,
                            on_click=automatisch,
                            data="titelbild_auto",
                        ),
                    ],
                ),
                text_feld,
                nur_text,
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=abbrechen, data="titelbild_abbrechen"),
                        ft.FilledButton("Übernehmen", on_click=fertig, data="titelbild_fertig"),
                    ],
                )
            ],
        ),
    )
    page.show_dialog(blatt)


def fuer(
    page: Any, state: Any, medium: Callable[[], Media | None]
) -> Callable[[str, str, Callable[[str, str], None]], None]:
    """Der Öffner für `components.material_rolle.rollen_zeile` (``titelbild=``): ``medium``
    liefert das Stück, wie es gerade im Formular steht — ohne Adresse geht nichts auf."""

    def handler(bild: str, text: str, setzen: Callable[[str, str], None]) -> None:
        m = medium()
        if m is None or not m.uri:
            return
        oeffnen(page, state, replace(m, titelbild=bild, titelbild_text=text), setzen)

    return handler


__all__ = ["STAND", "fuer", "oeffnen", "stand_text"]
