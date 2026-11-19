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

Ein Entwurf (die Kopie vor „Übernehmen“) und ein laufendes „Erstellen“ überleben den Neuaufbau der
Ansicht (`_ENTWUERFE`, `_LAEUFE`): Wer zurückkommt, sieht den Balken oder das Ergebnis, und für
dieselbe Datei startet kein zweiter Lauf. Die Ablage lässt einen Entwurf liegen, solange die App
läuft (`Paketablage.entwurf_merken`), beim nächsten Start geht er; fehlt er doch, verschwindet er
hier und „Übernehmen“ ändert nichts. Nennt ein Paket das Original noch (Paketstand), bleibt es
auf dem Gerät — dann gibt es „Original wieder nehmen“, aber kein „Original löschen“.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import flet as ft

from trainingsapp.core import videoinfo
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.models import new_id
from trainingsapp.core.paketmedien import ORDNER, dateiname, groesse_text
from trainingsapp.core.verkleinern import (
    BILD,
    BILD_NAMEN,
    GANZ,
    TON,
    TON_NAMEN,
    VORGABE,
    VORLAGE_NAMEN,
    VORLAGEN,
    Schema,
    Ziel,
    ausschnitt,
    schnitt,
    wahl,
    zeit_lesen,
    zeit_text,
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


@dataclass(slots=True)
class Lauf:
    """Ein laufendes „Erstellen“ — gezeichnet von der Ansicht, die gerade zu sehen ist."""

    abbruch: threading.Event
    anteil: float = 0.0
    zeichnen: Callable[[], None] | None = None
    balken: Callable[[float], None] | None = None


#: Laufende „Erstellen“ je Original — wie die Entwürfe über den Neuaufbau der Ansicht hinweg
_LAEUFE: dict[str, Lauf] = {}


async def _auftrag(
    state: AppState, uri: str, pfad: Any, z: Ziel, info: videoinfo.Videoinfo, lauf: Lauf
) -> str | None:
    """Erstellt den Entwurf zu ``uri`` (`_ENTWUERFE`) — eine Meldung, wenn es nicht ging,
    sonst ``None`` (auch nach „Abbrechen“)."""
    ablage = state.pakete.ablage
    tmp = state.anhaenge.hochladen_ordner() / f"verkleinern_{new_id()}.mp4"

    def fortschritt(anteil: float) -> None:
        lauf.anteil = anteil

    auftrag = asyncio.ensure_future(
        weg_.ausfuehren(
            state, pfad, tmp, z, dauer_s=info.dauer_s, fortschritt=fortschritt, abbruch=lauf.abbruch
        )
    )
    while not auftrag.done():
        await asyncio.sleep(0.3)
        if lauf.balken is not None:
            lauf.balken(lauf.anteil)
    try:
        fertig = auftrag.result()
    except Exception as fehler:
        tmp.unlink(missing_ok=True)
        return f"Verkleinern ging nicht: {fehler}"
    if not fertig:
        tmp.unlink(missing_ok=True)
        return None
    try:
        name = await paketdatei.ablegen(state, tmp, "mp4")
    except (NichtBereinigbar, OSError) as fehler:
        return f"Nicht übernommen: {fehler}"
    finally:
        tmp.unlink(missing_ok=True)
    neu_pfad = None
    if ablage is not None:
        ablage.entwurf_merken(name)
        neu_pfad = ablage.pfad(name)
    neu_info = await asyncio.to_thread(videoinfo.lesen, neu_pfad) if neu_pfad else None
    n = neu_pfad.stat().st_size if neu_pfad is not None and neu_pfad.is_file() else 0
    _ENTWUERFE[uri] = Entwurf(name, z, n, neu_info)
    return None


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
    # Nennt ein Paketstand das Original, bliebe es auch nach „Original löschen“ liegen
    gebunden = original is not None and ablage is not None and ablage.original_gebunden(uri)
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
        "zeigen": "neu",
        #: Kürzen: Anfang und Ende in Sekunden (0 = von vorn bzw. bis zum Schluss)
        "von": 0.0,
        "bis": 0.0,
        #: Der Bildausschnitt (Anteile links, oben, rechts, unten) — nur am Rechner
        "bild": GANZ,
    }

    def mit_schnitt(z: Ziel) -> Ziel:
        """Das Ziel mit Anfang und Ende (Ben, 18.11.2026: „Anfang oder Ende wegschneiden“)."""
        von, bis = schnitt(stand["von"], stand["bis"], info.dauer_s if info else 0.0)
        return replace(z, von_s=von, bis_s=bis) if von or bis else z

    def jetzt() -> Ziel:
        return mit_schnitt(ziel(stand["schema"], info, groesse, stand["bild"]))

    def zu_gross(z: Ziel) -> bool:
        """Wäre nicht kleiner — gekürzt oder zugeschnitten ist es das immer."""
        return z.nicht_kleiner and not z.gekuerzt and not z.zugeschnitten

    def schaetzung(z: Ziel) -> str:
        if info is None or not info.dauer_s:
            return "Die Dauer steht nicht in der Datei — keine Schätzung."
        if zu_gross(z):
            return f"Wäre nicht kleiner als jetzt ({groesse_text(groesse)})."
        laenge = (
            f" · {zeit_text(z.dauer(info.dauer_s))} von {zeit_text(info.dauer_s)}"
            if z.gekuerzt
            else ""
        )
        return (
            f"Neu etwa {groesse_text(z.bytes(info.dauer_s))}{laenge} · "
            f"jetzt {groesse_text(groesse)}"
        )

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
        z = mit_schnitt(ziel(s, info, groesse, stand["bild"]))
        gewaehlt = stand["vorlage"] == key
        rechts = (
            "wäre nicht kleiner"
            if zu_gross(z)
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
            from trainingsapp.ui.components.videospieler import Videospieler

            # Knöpfe unter dem Bild, die stehen bleiben (Ben, 18.11.2026)
            return Videospieler([str(datei)], hoehe=220).control
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
                "Paket, gilt die neue Fassung als deine Änderung und bleibt bei Updates; das "
                "Original bleibt dann, solange das Paket es nennt.",
                size=12,
                opacity=0.65,
            ),
        ]

    def zeichnen() -> None:
        z = jetzt()
        lauf = _LAEUFE.get(uri)
        entwurf = _ENTWUERFE.get(uri)
        if entwurf is not None and ablage is not None and not ablage.vorhanden(entwurf.neu):
            _ENTWUERFE.pop(uri, None)  # weggeräumt — dann eben neu erstellen
            entwurf = None
        vorlagen_spalte.controls = [vorlage_zeile(k) for k in VORLAGEN]
        genauer_spalte.visible = bool(stand["genauer"])
        genauer_spalte.controls = genauer_teile() if stand["genauer"] else []
        genauer_knopf.content = "Weniger" if stand["genauer"] else "Genauer …"
        schaetzung_text.value = schaetzung(z)
        schaetzung_text.color = ft.Colors.ERROR if zu_gross(z) else None
        erstellen_knopf.disabled = (
            womit is None or not da or zu_gross(z) or lauf is not None or info is None
        )
        erstellen_knopf.content = (
            "Kürzen und erstellen"
            if z.gekuerzt
            else "Zuschneiden und erstellen"
            if z.zugeschnitten
            else "Erstellen"
        )
        ausschnitt_zeichnen()
        von_feld.value = zeit_text(z.von_s) if z.von_s else ""
        bis_feld.value = zeit_text(z.bis_s) if z.bis_s else ""
        ganz_knopf.visible = z.gekuerzt
        balken.visible = abbrechen_knopf.visible = lauf is not None
        balken.value = lauf.anteil if lauf is not None else 0
        einstellen_spalte.visible = entwurf is None
        ergebnis_spalte.visible = entwurf is not None
        ergebnis_spalte.controls = ergebnis_teile(entwurf) if entwurf is not None else []
        with contextlib.suppress(Exception):
            inhalt.update()

    # -- Kürzen: Anfang und Ende (Ben, 18./19.11.2026: „Crop wäre gut, also Anfang oder Ende
    # wegschneiden“ — „auch im Medieneditor (zum Komprimieren)“): im Original an die Stelle
    # spulen und „Anfang hier“ / „Ende hier“ tippen, oder die Zeit eintragen. Dieselbe Kopie
    # wie beim Verkleinern — das Original bleibt -------------------------------------------

    schnitt_spieler: Any = None
    schnitt_bild: ft.Control = ft.Container()
    if da and pfad is not None and info is not None and info.dauer_s:
        try:
            from trainingsapp.ui.components.videospieler import Videospieler

            schnitt_spieler = Videospieler([str(pfad)], hoehe=200)
            schnitt_bild = schnitt_spieler.control
        except ImportError:
            schnitt_bild = ft.Text(
                "Ohne Vorschau in diesem Build — die Zeiten von Hand eintragen.",
                size=12,
                opacity=0.7,
            )

    def marke_setzen(was: str, sekunden: float | None) -> None:
        if sekunden is None:
            melden("Das ist keine Zeit — etwa 0:12 oder 12,5.")
        else:
            stand[was] = round(sekunden, 1)
            stand["von"], stand["bis"] = schnitt(
                stand["von"], stand["bis"], info.dauer_s if info else 0.0
            )
        zeichnen()

    def feld_gelesen(was: str) -> Callable[[Any], None]:
        def handler(e: Any) -> None:
            marke_setzen(was, zeit_lesen(str(e.control.value or "")))

        return handler

    def hier(was: str) -> Callable[[Any], Any]:
        async def handler(_e: Any = None) -> None:
            stelle = await schnitt_spieler.position_s() if schnitt_spieler is not None else None
            if stelle is None:
                melden("Die Stelle ließ sich nicht lesen — die Zeit von Hand eintragen.")
                return
            marke_setzen(was, stelle)

        return handler

    def ganz(_e: Any = None) -> None:
        stand["von"], stand["bis"] = 0.0, 0.0
        zeichnen()

    von_feld = ft.TextField(
        label="Anfang",
        hint_text="0:00",
        dense=True,
        width=110,
        on_blur=feld_gelesen("von"),
        on_submit=feld_gelesen("von"),
        data="kuerzen_von",
    )
    bis_feld = ft.TextField(
        label="Ende",
        hint_text=zeit_text(info.dauer_s) if info is not None and info.dauer_s else "",
        dense=True,
        width=110,
        on_blur=feld_gelesen("bis"),
        on_submit=feld_gelesen("bis"),
        data="kuerzen_bis",
    )
    ganz_knopf = ft.TextButton("Ganze Länge", on_click=ganz, visible=False, data="kuerzen_ganz")
    kuerzen_teile: list[ft.Control] = (
        [
            ft.Text("KÜRZEN · ANFANG UND ENDE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            schnitt_bild,
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    von_feld,
                    ft.OutlinedButton(
                        "Anfang hier",
                        on_click=hier("von"),
                        visible=schnitt_spieler is not None,
                        data="kuerzen_von_hier",
                    ),
                    bis_feld,
                    ft.OutlinedButton(
                        "Ende hier",
                        on_click=hier("bis"),
                        visible=schnitt_spieler is not None,
                        data="kuerzen_bis_hier",
                    ),
                    ganz_knopf,
                ],
            ),
            ft.Text(
                "Zur Stelle spulen und „Anfang hier“ oder „Ende hier“ tippen — oder die Zeit "
                "eintragen (0:12). Leer heißt: von vorn bzw. bis zum Schluss.",
                size=12,
                opacity=0.65,
            ),
        ]
        if info is not None and info.dauer_s
        else []
    )

    # -- Bildausschnitt (Ben, 19.11.2026: „komprimiert und gecroppt“, `docs/
    # plan_medien_einheitlich.md` §2.6): zwei Regler wie beim Dokument (Breite, Höhe), daneben
    # das Bild als Schema — hell bleibt, dunkel fällt weg. Nur am Rechner: ffmpeg schneidet;
    # der Umwandler am Telefon kann es nicht -------------------------------------------------

    kann_schneiden = (
        womit == weg_.FFMPEG and info is not None and bool(info.breite) and bool(info.hoehe)
    )
    SCHEMA = 120.0  # längere Seite des Schemas
    seiten_b = float(info.breite) if info is not None and info.breite else 16.0
    seiten_h = float(info.hoehe) if info is not None and info.hoehe else 9.0
    schema_b = SCHEMA * min(1.0, seiten_b / seiten_h)
    schema_h = SCHEMA * min(1.0, seiten_h / seiten_b)
    schema_innen = ft.Container(bgcolor=ft.Colors.PRIMARY, border_radius=2, data="ausschnitt_innen")
    schema_bild = ft.Stack(
        width=schema_b,
        height=schema_h,
        controls=[
            ft.Container(
                width=schema_b,
                height=schema_h,
                bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.ON_SURFACE),
                border_radius=4,
            ),
            schema_innen,
        ],
    )
    ausschnitt_text = ft.Text("", size=12, opacity=0.75, data="ausschnitt_text")
    regler_breite = ft.RangeSlider(
        min=0, max=100, start_value=0, end_value=100, data="ausschnitt_breite"
    )
    regler_hoehe = ft.RangeSlider(
        min=0, max=100, start_value=0, end_value=100, data="ausschnitt_hoehe"
    )
    ganzes_bild = ft.TextButton("Ganzes Bild", visible=False, data="ausschnitt_ganz")

    def ausschnitt_zeichnen() -> None:
        li, ob, re, un = stand["bild"]
        schema_innen.left, schema_innen.top = schema_b * li, schema_h * ob
        schema_innen.width, schema_innen.height = schema_b * (re - li), schema_h * (un - ob)
        regler_breite.start_value, regler_breite.end_value = li * 100, re * 100
        regler_hoehe.start_value, regler_hoehe.end_value = ob * 100, un * 100
        ganzes_bild.visible = stand["bild"] != GANZ
        if info is not None and info.breite and info.hoehe:
            b, h = round(info.breite * (re - li)), round(info.hoehe * (un - ob))
            ausschnitt_text.value = (
                f"Ganzes Bild · {info.breite} × {info.hoehe}"
                if stand["bild"] == GANZ
                else f"Ausschnitt {b} × {h} von {info.breite} × {info.hoehe}"
            )

    def ausschnitt_geaendert(_e: Any = None) -> None:
        stand["bild"] = ausschnitt(
            float(regler_breite.start_value or 0) / 100,
            float(regler_hoehe.start_value or 0) / 100,
            float(regler_breite.end_value or 100) / 100,
            float(regler_hoehe.end_value or 100) / 100,
        )
        zeichnen()

    def ausschnitt_ganz(_e: Any = None) -> None:
        stand["bild"] = GANZ
        zeichnen()

    # erst beim Loslassen rechnen — jede Bewegung zeichnete sonst die ganze Seite neu
    regler_breite.on_change_end = ausschnitt_geaendert
    regler_hoehe.on_change_end = ausschnitt_geaendert
    # `on_change` ohne Arbeit: damit die Werte unterwegs schon bei Python ankommen
    regler_breite.on_change = lambda _e: None
    regler_hoehe.on_change = lambda _e: None
    ganzes_bild.on_click = ausschnitt_ganz
    ausschnitt_teile: list[ft.Control] = (
        [
            ft.Text("BILDAUSSCHNITT", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=SCHEMA, alignment=ft.Alignment.CENTER, content=schema_bild),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Text(name, size=12, width=44),
                                    ft.Container(expand=True, content=c),
                                ],
                            )
                            for name, c in (("Breite", regler_breite), ("Höhe", regler_hoehe))
                        ],
                    ),
                ],
            ),
            ft.Row(spacing=8, controls=[ausschnitt_text, ganzes_bild]),
        ]
        if kann_schneiden
        else []
    )

    def genauer_umschalten(_e: Any = None) -> None:
        stand["genauer"] = not stand["genauer"]
        zeichnen()

    genauer_knopf.on_click = genauer_umschalten

    def balken_zeigen(anteil: float) -> None:
        balken.value = anteil
        with contextlib.suppress(Exception):
            balken.update()

    async def erstellen(_e: Any = None) -> None:
        z = jetzt()
        if uri in _LAEUFE or womit is None or pfad is None or zu_gross(z) or info is None:
            return
        lauf = Lauf(threading.Event(), zeichnen=zeichnen, balken=balken_zeigen)
        _LAEUFE[uri] = lauf
        zeichnen()
        try:
            meldung = await _auftrag(state, uri, pfad, z, info, lauf)
        finally:
            _LAEUFE.pop(uri, None)
        stand["zeigen"] = "neu"
        if lauf.zeichnen is not None:
            lauf.zeichnen()  # die Ansicht, die jetzt zu sehen ist — vielleicht eine neue
        if meldung:
            melden(meldung)

    async def abbrechen(_e: Any = None) -> None:
        if (lauf := _LAEUFE.get(uri)) is not None:
            await weg_.abbrechen(state, lauf.abbruch)

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
        try:
            ablage.ersetzen(uri, entwurf.neu)
        except FileNotFoundError:  # weggeräumt — nichts hat sich geändert
            zeichnen()
            melden("Die neue Fassung ist nicht mehr da — bitte noch einmal erstellen.")
            return
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
            weg = ablage.original_vergessen(uri) if ablage is not None else False
            melden(
                "Original gelöscht."
                if weg
                else "Das Original bleibt — ein Paket oder eine Kursvorlage nennt es noch."
            )
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
        knoepfe: list[ft.Control] = [
            ft.TextButton(
                "Original wieder nehmen",
                icon=ft.Icons.UNDO,
                on_click=original_nehmen,
                data="verkleinern_original_nehmen",
            )
        ]
        if not gebunden:
            knoepfe.append(
                ft.TextButton(
                    "Original löschen",
                    icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    on_click=original_loeschen_fragen,
                    data="verkleinern_original_loeschen",
                )
            )
        kopf.append(
            karte(
                ft.Text(
                    f"Verkleinert aus einem Original ({groesse_text(ablage.groesse(original))}),"
                    " das noch auf dem Gerät liegt."
                    + (
                        " Ein Paket nennt es noch (für „Auf Paketstand“ und Updates) — es bleibt,"
                        " solange das so ist."
                        if gebunden
                        else ""
                    ),
                    size=13,
                    data="verkleinern_original_text",
                ),
                ft.Row(wrap=True, spacing=8, controls=knoepfe),
                padding=10,
                abstand=6,
            )
        )
    einstellen_spalte.controls = [
        *kuerzen_teile,
        *ausschnitt_teile,
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
    if (lauf := _LAEUFE.get(uri)) is not None:
        lauf.zeichnen, lauf.balken = zeichnen, balken_zeigen  # diese Ansicht zeigt den Lauf
    zeichnen()
    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Verkleinern")),
        controls=[sicher(ft.Container(padding=16, expand=True, content=inhalt))],
    )
    return ansicht


__all__ = ["SEGMENT", "verkleinern_route", "verkleinern_view"]
