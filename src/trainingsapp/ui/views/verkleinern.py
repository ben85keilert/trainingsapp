"""„Verkleinern“ einer Videodatei (Ben, 17.11.2026, `docs/plan_medien_reiter.md` §5) — Route
``<basis>/verkleinern/<sha256>.<endung>``, über jede Ansicht gelegt wie ``…/paketmedium/…``.

- **Grobes Schema mit Größe vorher** (`core/verkleinern.py`): drei Vorlagen (Klein · Mittel ·
  Groß, Vorgabe Mittel), „Genauer …“ mit Auflösung, Bildrate, Bildqualität und Ton — die
  Schätzung läuft mit. Was größer wäre als das Original, steht nicht zur Wahl; was nicht
  kleiner würde, sagt es vorher.
- **Das Original bleibt** (Ben: „Das konvertierte Video wird erstmal kopiert, das ursprüngliche
  bleibt, damit man das neue anschauen kann und neu erstellen, falls es doch zu unscharf ist“):
  „Erstellen“ legt eine Kopie ab; Jetzt · Neu laufen im selben Spieler; „Anders erstellen …“
  und „Verwerfen“ werfen die Kopie weg, „Übernehmen“ lässt alle Stücke auf sie zeigen
  (`Paketablage.ersetzen`). Das Original bleibt danach auf dem Gerät — hier stehen dann
  „Original wieder nehmen“ und „Original löschen“.
- **Womit** (`ui/verkleinern.py`): ffmpeg am Rechner, der Umwandler auf Android; sonst fehlt
  „Erstellen“ mit einem Satz dazu (iPhone, Browser).

Ein Entwurf (die Kopie vor „Übernehmen“) überlebt den Neuaufbau der Ansicht (`_ENTWUERFE`); nennt
ihn nichts, räumt die Ablage ihn beim nächsten Start weg.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core import videoinfo
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.models import new_id
from trainingsapp.core.paketmedien import ORDNER, dateiname, groesse_text
from trainingsapp.core.verkleinern import (
    BILD,
    BILD_NAMEN,
    TON,
    TON_NAMEN,
    VORGABE,
    VORLAGE_NAMEN,
    VORLAGEN,
    Schema,
    Ziel,
    wahl,
    ziel,
)
from trainingsapp.ui import paketdatei
from trainingsapp.ui import verkleinern as weg_
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_ziel
from trainingsapp.ui.state import AppState

#: Das Segment der Route
SEGMENT = "verkleinern"


def verkleinern_route(basis: str, uri: str) -> str:
    """``<basis>/verkleinern/<sha256>.<endung>``.

    >>> verkleinern_route("/plaene/p/medien", "medien/" + "a" * 64 + ".mp4")[:30]
    '/plaene/p/medien/verkleinern/a'
    """
    return f"{basis.rstrip('/')}/{SEGMENT}/{dateiname(uri)}"


@dataclass(slots=True)
class Entwurf:
    """Die Kopie vor „Übernehmen“."""

    neu: str
    ziel: Ziel
    bytes: int
    info: videoinfo.Videoinfo | None


#: Entwürfe je Original — überleben den Neuaufbau der Ansicht
_ENTWUERFE: dict[str, Entwurf] = {}


def verkleinern_view(page: Any, state: AppState, basis: str, datei_name: str) -> ft.View:
    """Die Ansicht für die Paketdatei ``datei_name``."""
    uri = ORDNER + datei_name
    route = f"{basis.rstrip('/')}/{SEGMENT}/{datei_name}"
    ablage = state.pakete.ablage
    pfad = ablage.pfad(uri) if ablage is not None else None
    da = pfad is not None and pfad.is_file()
    groesse = pfad.stat().st_size if da and pfad is not None else 0
    info = videoinfo.lesen(pfad) if da and pfad is not None else None
    titel = state.paketmedium_titel.get(datei_name) or "Video"
    original = ablage.original(uri) if ablage is not None else None
    seiten, raten, hat_ton = wahl(info)
    womit = weg_.weg(state)

    def eingepasst(s: Schema) -> Schema:
        """Ein Schema in dem, was zur Wahl steht (nie über dem Original)."""
        return Schema(
            kurze_seite=max((x for x in seiten if x <= s.kurze_seite), default=seiten[0]),
            bildrate=max((x for x in raten if x <= s.bildrate), default=raten[0]),
            bild=s.bild,
            ton=s.ton if hat_ton else "ohne",
        )

    stand: dict[str, Any] = {
        "vorlage": VORGABE,
        "schema": eingepasst(VORLAGEN[VORGABE]),
        "genauer": False,
        "laeuft": False,
        "anteil": 0.0,
        "abbruch": None,
        "zeigen": "neu",
    }

    def jetzt() -> Ziel:
        return ziel(stand["schema"], info, groesse)

    def schaetzung(z: Ziel) -> str:
        if info is None or not info.dauer_s:
            return "Die Dauer steht nicht in der Datei — keine Schätzung."
        if z.nicht_kleiner:
            return f"Wäre nicht kleiner als jetzt ({groesse_text(groesse)})."
        return f"Neu etwa {groesse_text(z.bytes(info.dauer_s))} · jetzt {groesse_text(groesse)}"

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Teile, einmal gebaut; `zeichnen` tauscht nur Werte und Inhalte ----------------------

    vorlagen_spalte = ft.Column(spacing=6, tight=True)
    genauer_spalte = ft.Column(spacing=10, tight=True, visible=False)
    genauer_knopf = ft.TextButton("Genauer …", icon=ft.Icons.TUNE, data="verkleinern_genauer")
    schaetzung_text = ft.Text(
        "", size=15, weight=ft.FontWeight.W_600, data="verkleinern_schaetzung"
    )
    erstellen_knopf = ft.FilledButton(
        "Erstellen", icon=ft.Icons.COMPRESS, data="verkleinern_erstellen"
    )
    balken = ft.ProgressBar(value=0, visible=False)
    abbrechen_knopf = ft.TextButton("Abbrechen", visible=False, data="verkleinern_abbrechen")
    ergebnis_spalte = ft.Column(spacing=10, tight=True, visible=False)
    einstellen_spalte = ft.Column(spacing=10, tight=True)

    def segmente(
        werte: list[tuple[str, str]], gewaehlt: str, wechsel: Any, data: str
    ) -> ft.Control:
        return ft.SegmentedButton(
            selected=[gewaehlt],
            show_selected_icon=False,
            segments=[ft.Segment(value=w, label=ft.Text(t)) for w, t in werte],
            on_change=wechsel,
            data=data,
        )

    def schema_setzen(**neu: Any) -> None:
        s: Schema = stand["schema"]
        stand["schema"] = eingepasst(
            Schema(
                kurze_seite=int(neu.get("kurze_seite", s.kurze_seite)),
                bildrate=int(neu.get("bildrate", s.bildrate)),
                bild=str(neu.get("bild", s.bild)),
                ton=str(neu.get("ton", s.ton)),
            )
        )
        passend = [k for k, v in VORLAGEN.items() if eingepasst(v) == stand["schema"]]
        stand["vorlage"] = passend[0] if passend else None
        zeichnen()

    def vorlage_zeile(key: str) -> ft.Control:
        s = eingepasst(VORLAGEN[key])
        z = ziel(s, info, groesse)
        gewaehlt = stand["vorlage"] == key
        rechts = (
            "wäre nicht kleiner"
            if z.nicht_kleiner
            else (f"etwa {groesse_text(z.bytes(info.dauer_s))}" if info and info.dauer_s else "")
        )

        def waehlen(_e: Any = None) -> None:
            stand["vorlage"] = key
            stand["schema"] = s
            zeichnen()

        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            border=ft.Border.all(
                2 if gewaehlt else 1, ft.Colors.PRIMARY if gewaehlt else ft.Colors.OUTLINE_VARIANT
            ),
            on_click=waehlen,
            ink=True,
            data=("verkleinern_vorlage", key),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(
                        ft.Icons.RADIO_BUTTON_CHECKED if gewaehlt else ft.Icons.RADIO_BUTTON_OFF,
                        size=20,
                        color=ft.Colors.PRIMARY if gewaehlt else None,
                    ),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(VORLAGE_NAMEN[key], weight=ft.FontWeight.W_500),
                            ft.Text(z.text(), size=12, opacity=0.7),
                        ],
                    ),
                    ft.Text(rechts, size=13, opacity=0.8),
                ],
            ),
        )

    def genauer_teile() -> list[ft.Control]:
        s: Schema = stand["schema"]

        def zeile(name: str, steuer: ft.Control) -> ft.Control:
            return ft.Column(
                spacing=4,
                tight=True,
                controls=[ft.Text(name, size=12, opacity=0.7), steuer],
            )

        teile = [
            zeile(
                "Auflösung (kurze Seite)",
                segmente(
                    [(str(x), f"{x}p") for x in seiten],
                    str(s.kurze_seite),
                    lambda e: schema_setzen(kurze_seite=e.control.selected[0]),
                    "verkleinern_aufloesung",
                ),
            ),
            zeile(
                "Bilder je Sekunde",
                segmente(
                    [(str(x), str(x)) for x in raten],
                    str(s.bildrate),
                    lambda e: schema_setzen(bildrate=e.control.selected[0]),
                    "verkleinern_bildrate",
                ),
            ),
            zeile(
                "Bildqualität",
                segmente(
                    [(k, BILD_NAMEN[k]) for k in BILD],
                    s.bild,
                    lambda e: schema_setzen(bild=e.control.selected[0]),
                    "verkleinern_bild",
                ),
            ),
        ]
        if hat_ton:
            teile.append(
                zeile(
                    "Ton",
                    segmente(
                        [(k, TON_NAMEN[k]) for k in TON],
                        s.ton,
                        lambda e: schema_setzen(ton=e.control.selected[0]),
                        "verkleinern_ton",
                    ),
                )
            )
        teile.append(
            ft.Text(
                "dpi gibt es bei Videos nicht — ein Bildschirm zeigt Pixel; was dpi meint, ist "
                "hier die Auflösung.",
                size=12,
                opacity=0.65,
            )
        )
        return teile

    def spieler(name: str) -> ft.Control:
        """Original oder Neu im selben Spieler — wie die Ansicht einer Paketdatei."""
        datei = ablage.pfad(name) if ablage is not None else None
        if datei is None or not datei.is_file():
            return ft.Text("Die Datei fehlt.", opacity=0.7)
        try:
            import flet_video as fv

            return ft.Container(
                height=220,
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=fv.Video(
                    playlist=[fv.VideoMedia(str(datei))],
                    autoplay=False,
                    fit=ft.BoxFit.CONTAIN,
                    expand=True,
                ),
            )
        except ImportError:
            return ft.Text("Video-Erweiterung fehlt in diesem Build.", opacity=0.7)

    def ergebnis_teile(e: Entwurf) -> list[ft.Control]:
        neu_text = e.info.text() if e.info is not None and e.info.text() else e.ziel.text()
        gewaehlt = stand["zeigen"]

        def wechsel(ev: Any) -> None:
            stand["zeigen"] = ev.control.selected[0] if ev.control.selected else "neu"
            zeichnen()

        return [
            ft.Text("Neu", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            ft.Text(
                f"{neu_text} · {groesse_text(e.bytes)} (vorher {groesse_text(groesse)})",
                size=15,
                weight=ft.FontWeight.W_600,
                data="verkleinern_neu",
            ),
            segmente(
                [("original", "Jetzt"), ("neu", "Neu")], gewaehlt, wechsel, "verkleinern_zeigen"
            ),
            spieler(uri if gewaehlt == "original" else e.neu),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.TextButton(
                        "Anders erstellen …",
                        icon=ft.Icons.TUNE,
                        on_click=lambda _e=None: verwerfen(),
                        data="verkleinern_anders",
                    ),
                    ft.TextButton(
                        "Verwerfen",
                        icon=ft.Icons.DELETE_OUTLINE,
                        on_click=lambda _e=None: verwerfen(),
                        data="verkleinern_verwerfen",
                    ),
                    ft.FilledButton(
                        "Übernehmen",
                        icon=ft.Icons.CHECK,
                        on_click=uebernehmen,
                        data="verkleinern_uebernehmen",
                    ),
                ],
            ),
            ft.Text(
                "Übernommen zeigt jedes Stück, das dieses Video nennt, auf die neue Fassung. Das "
                "Original bleibt auf dem Gerät, reist aber nicht mit. Kommt die Übung aus einem "
                "Paket, gilt die neue Fassung als deine Änderung und bleibt bei Updates.",
                size=12,
                opacity=0.65,
            ),
        ]

    def zeichnen() -> None:
        z = jetzt()
        entwurf = _ENTWUERFE.get(uri)
        vorlagen_spalte.controls = [vorlage_zeile(k) for k in VORLAGEN]
        genauer_spalte.visible = bool(stand["genauer"])
        genauer_spalte.controls = genauer_teile() if stand["genauer"] else []
        genauer_knopf.content = "Weniger" if stand["genauer"] else "Genauer …"
        schaetzung_text.value = schaetzung(z)
        schaetzung_text.color = ft.Colors.ERROR if z.nicht_kleiner else None
        erstellen_knopf.disabled = (
            womit is None or not da or z.nicht_kleiner or bool(stand["laeuft"]) or info is None
        )
        balken.visible = abbrechen_knopf.visible = bool(stand["laeuft"])
        balken.value = stand["anteil"]
        einstellen_spalte.visible = entwurf is None
        ergebnis_spalte.visible = entwurf is not None
        ergebnis_spalte.controls = ergebnis_teile(entwurf) if entwurf is not None else []
        with contextlib.suppress(Exception):
            inhalt.update()

    def genauer_umschalten(_e: Any = None) -> None:
        stand["genauer"] = not stand["genauer"]
        zeichnen()

    genauer_knopf.on_click = genauer_umschalten

    async def erstellen(_e: Any = None) -> None:
        z = jetzt()
        if stand["laeuft"] or womit is None or pfad is None or z.nicht_kleiner or info is None:
            return
        ordner = state.anhaenge.hochladen_ordner()
        tmp = ordner / f"verkleinern_{new_id()}.mp4"
        abbruch = threading.Event()
        stand.update(laeuft=True, anteil=0.0, abbruch=abbruch)
        zeichnen()

        def fortschritt(anteil: float) -> None:
            stand["anteil"] = anteil

        auftrag = asyncio.ensure_future(
            weg_.ausfuehren(
                state,
                pfad,
                tmp,
                z,
                dauer_s=info.dauer_s,
                fortschritt=fortschritt,
                abbruch=abbruch,
            )
        )
        while not auftrag.done():
            await asyncio.sleep(0.3)
            balken.value = stand["anteil"]
            with contextlib.suppress(Exception):
                balken.update()
        stand["laeuft"] = False
        try:
            fertig = auftrag.result()
        except Exception as fehler:
            tmp.unlink(missing_ok=True)
            zeichnen()
            melden(f"Verkleinern ging nicht: {fehler}")
            return
        if not fertig:
            tmp.unlink(missing_ok=True)
            zeichnen()
            return
        try:
            name = await paketdatei.ablegen(state, tmp, "mp4")
        except (NichtBereinigbar, OSError) as fehler:
            zeichnen()
            melden(f"Nicht übernommen: {fehler}")
            return
        finally:
            tmp.unlink(missing_ok=True)
        neu_pfad = ablage.pfad(name) if ablage is not None else None
        neu_info = await asyncio.to_thread(videoinfo.lesen, neu_pfad) if neu_pfad else None
        n = neu_pfad.stat().st_size if neu_pfad is not None and neu_pfad.is_file() else 0
        _ENTWUERFE[uri] = Entwurf(name, z, n, neu_info)
        stand["zeigen"] = "neu"
        zeichnen()

    async def abbrechen(_e: Any = None) -> None:
        if stand["abbruch"] is not None:
            await weg_.abbrechen(state, stand["abbruch"])

    erstellen_knopf.on_click = erstellen
    abbrechen_knopf.on_click = abbrechen

    def verwerfen() -> None:
        """Die Kopie weg — zurück zum Schema (auch „Anders erstellen …“)."""
        entwurf = _ENTWUERFE.pop(uri, None)
        if entwurf is not None and ablage is not None:
            ablage.verwerfen(entwurf.neu)
        zeichnen()

    async def uebernehmen(_e: Any = None) -> None:
        entwurf = _ENTWUERFE.pop(uri, None)
        if entwurf is None or ablage is None:
            return
        ablage.ersetzen(uri, entwurf.neu)
        state.paketmedium_titel[dateiname(entwurf.neu) or ""] = titel
        melden("Übernommen — das Original bleibt auf dem Gerät.")
        await page.push_route(zurueck_ziel(page, ansicht))

    async def original_nehmen(_e: Any = None) -> None:
        if original is None or ablage is None:
            return
        ablage.ersetzen(uri, original, original_behalten=False)
        melden("Wieder das Original.")
        await page.push_route(zurueck_ziel(page, ansicht))

    def original_loeschen_fragen(_e: Any = None) -> None:
        nachher = Nachher()

        def ja(_e: Any = None) -> None:
            nachher.danach(lambda: loeschen_jetzt())
            schliessen(dialog)

        def loeschen_jetzt() -> None:
            if ablage is not None:
                ablage.original_vergessen(uri)
            melden("Original gelöscht.")
            page.run_task(page.push_route, zurueck_ziel(page, ansicht))

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Original löschen?"),
            content=ft.Text(
                "Es bleibt nur die verkleinerte Fassung. Zurückholen lässt sich das Original "
                "danach nicht."
            ),
            on_dismiss=nachher.bei_schliessen,
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                ft.TextButton("Löschen", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=ja),
            ],
        )
        page.show_dialog(dialog)

    kopf: list[ft.Control] = [
        ft.Text(titel, size=18, weight=ft.FontWeight.W_600),
        ft.Text(
            " · ".join(
                t for t in ("Jetzt", info.text() if info else "", groesse_text(groesse)) if t
            )
            if da
            else "Die Datei fehlt — das Paket neu importieren.",
            size=13,
            opacity=0.75,
            data="verkleinern_original",
        ),
    ]
    if original is not None and ablage is not None:
        kopf.append(
            karte(
                ft.Text(
                    f"Verkleinert aus einem Original ({groesse_text(ablage.groesse(original))}),"
                    " das noch auf dem Gerät liegt.",
                    size=13,
                ),
                ft.Row(
                    wrap=True,
                    spacing=8,
                    controls=[
                        ft.TextButton(
                            "Original wieder nehmen",
                            icon=ft.Icons.UNDO,
                            on_click=original_nehmen,
                            data="verkleinern_original_nehmen",
                        ),
                        ft.TextButton(
                            "Original löschen",
                            icon=ft.Icons.DELETE_OUTLINE,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            on_click=original_loeschen_fragen,
                            data="verkleinern_original_loeschen",
                        ),
                    ],
                ),
                padding=10,
                abstand=6,
            )
        )
    einstellen_spalte.controls = [
        ft.Text("VORLAGE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        vorlagen_spalte,
        genauer_knopf,
        genauer_spalte,
        schaetzung_text,
        ft.Text(
            weg_.WEG_TEXT.get(womit, "") + " Das Original bleibt, bis du übernimmst."
            if womit is not None
            else weg_.KEIN_WEG,
            size=12,
            opacity=0.7,
            data="verkleinern_weg",
        ),
        ft.Row(spacing=8, controls=[erstellen_knopf, abbrechen_knopf]),
        balken,
    ]
    inhalt = ft.Column(
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        controls=[*kopf, einstellen_spalte, ergebnis_spalte],
    )
    zeichnen()
    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Verkleinern")),
        controls=[sicher(ft.Container(padding=16, expand=True, content=inhalt))],
    )
    return ansicht


__all__ = ["SEGMENT", "verkleinern_route", "verkleinern_view"]
