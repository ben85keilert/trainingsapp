"""HF-Vollbild: die Herzfrequenz der laufenden Messung, quer, ohne Leisten (Ben, 10.11.2026,
A22; Skizzen H1–H3, Vertrag `docs/plan_hf_vollbild.md`).

Dieselbe Route wie das HRV-Vollbild (``/live``): `views.live_vollbild` zeigt dieses Bild, wenn
die Sicht „Herzfrequenz“ gilt oder das Gerät nur den Puls sendet; „⇄ HRV“ wechselt.

- **Links** die große Zahl mit Bereich, Reserve und Trend, darunter Werte des Bezugs.
- **Mitte** die Kurve über den Bereichen als Stufen einer Farbe; der **Zielbereich** als zwei
  Linien mit Griffen am rechten Rand (ziehen), Notizen als Marken.
- **Rechts** die Leiste: „Sprechen wird schwer“, „Belastung endet jetzt“, Notiz, Ton,
  Intervall, Fenster & Achse.
- **Erholung** (nach „Belastung endet jetzt“): die Fenster 30 · 60 · 120 · X als Marken, eine
  Karte, in der sich die Werte füllen, blass dahinter die vorige Erholung.
- **Intervall**: Anfang und Ende setzen (ziehen oder tippen), dazwischen HF an beiden
  Stellen mit Δ, HF-Max, HF-Min und die Erholung ab Spitze oder Anfang
  (`hrv_core.herzfrequenz.intervall_erholung`).

Die Herzfrequenz ist der Träger, nicht das Urteil (`docs/recht/00_zweckbestimmung.md`): nur
Zahlen, ein Ton zu selbst gesetzten Linien, keine Steuerung und kein Rat.

Gebaut wird jedes Control **einmal**; je Tick werden Werte gesetzt und nur die Kurve neu
gezeichnet (wie im HRV-Vollbild).
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_einstellungen import MESSEN_BIS_S
from trainingsapp.core.hf_profil import bereich_von
from trainingsapp.core.hf_training import BEZUEGE, BEZUG_ABSCHNITT, BEZUG_NAMEN
from trainingsapp.core.hf_ziel import (
    intervall_notiz,
    lage_text,
    trend_text,
    wertebereich,
    zeit_im_ziel,
    ziel_anteil_text,
    ziel_grenzen,
    ziel_text,
)
from trainingsapp.core.hrv_ansicht import HF_SPANNE_MIN_BPM
from trainingsapp.core.hrv_einstellungen import HF_MITTEL_S, HrvEinstellungen
from trainingsapp.core.laufend import minuten
from trainingsapp.core.zeitangabe import DAUER, UHR
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.atem_live import einatem_schatten
from trainingsapp.ui.components.hf_sicht import (
    HALTUNG_NAMEN,
    INTERVALL_PX,
    KONTEXT_NAMEN,
    ZIEL_FARBE,
    erholung_gruppe,
    erholung_karte,
    hf_baender,
    intervall_karte,
    prozent_text,
    wertebereich_gruppe,
    ziel_seite,
)
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.kurve import Reihe, kurve, y_grenzen
from trainingsapp.ui.components.layout import ohne_auto_update, sicher
from trainingsapp.ui.components.live_abschnitte import LiveAbschnitte
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.verlauf import FARBEN, Zeitachse, darstellung_blatt
from trainingsapp.ui.components.vollbild import SEITE_PX, ZEITACHSE_PX, seitenkopf
from trainingsapp.ui.components.zeitachse import achse
from trainingsapp.ui.components.zeitfenster import (
    BreitenSatz,
    Fenster,
    breiten_auswahl,
    breiten_nachziehen,
    breiten_wahl,
    wischbar,
)
from trainingsapp.ui.hf_live import HfLive, stumm_knoepfe_zeiten
from trainingsapp.ui.state import AppState

#: Breite der Wertespalte links, der Leiste rechts und der Seite „Zielbereich und Ton“ (px)
WERTE_PX = 150
LEISTE_PX = 108
ZIEL_SEITE_PX = 300
_KOPF_PX = 56
#: Breite der Bereichsnamen an der rechten Achse (`kurve._band_achse`) — für die Zeit unter
#: dem Finger zählt sie nicht zur Zeichenfläche
_BAND_ACHSE_PX = 52.0
#: Platz der Werteachse links der Zeichenfläche (px) — dort beginnt die Karte des Intervalls
_ACHSE_LINKS_PX = 56.0
#: Höhe eines Griffs am Zielbereich (px)
_GRIFF_PX = 24
#: So nah (Anteil der Fensterbreite) muss der Finger an einer Intervall-Linie sein, um sie
#: zu greifen — sonst blättert die Geste
_GREIF_ANTEIL = 0.06
#: Seitenleisten
ZIEL = "ziel"
NOTIZEN = "notizen"
ABSCHNITTE = "abschnitte"


@dataclass
class _Stand:
    hoehe: float
    breite: float
    zuletzt: float = 0.0
    seite: str | None = None
    #: Die Werteachse der letzten Zeichnung ``(unten, oben)`` — für die Griffe
    y: tuple[float, float] | None = None
    #: Griff, der gerade gezogen wird: ``(seite, bpm)``
    zug: tuple[str, float] | None = None
    #: Intervall-Linie, die die laufende Geste hält (``"von"``/``"bis"``)
    greift: str | None = None
    #: Woraus die Karten zuletzt gebaut wurden — gleich: nicht neu bauen (ein neuer Knopf
    #: verlöre einen Tipp, der gerade läuft)
    intervall_karte: tuple[Any, ...] | None = None
    erholung_karte: tuple[Any, ...] | None = None
    seite_gebaut: str | None = None
    #: Die Kurve der letzten Zeichnung (Zeit im Zielbereich)
    punkte: list[tuple[float, float]] | None = None


def griff_oben_px(wert: float, y: tuple[float, float], hoehe: float) -> float:
    """Oberkante (px) eines Griffs an der Stelle ``wert`` der Werteachse ``y`` einer Kurve der
    Höhe ``hoehe`` — mittig auf der Linie, im Bild gehalten.

    >>> griff_oben_px(150.0, (50.0, 150.0), 322.0), griff_oben_px(100.0, (50.0, 150.0), 322.0)
    (0.0, 138.0)
    """
    flaeche = max(hoehe - ZEITACHSE_PX, 1.0)
    lage = (y[1] - wert) / max(y[1] - y[0], 1e-9) * flaeche
    return float(min(max(lage - _GRIFF_PX / 2, 0.0), flaeche - _GRIFF_PX))


def hf_vollbild(
    page: ft.Page,
    state: AppState,
    lauf: Messlauf,
    schliessen: Callable[[], Any],
    *,
    zur_hrv: Callable[[], None] | None,
) -> ft.View:
    """Die Ansicht hinter ``/live`` in der Sicht „Herzfrequenz“. ``zur_hrv``: wechselt ins
    HRV-Vollbild — None, wenn das Gerät nur den Puls sendet."""
    state.live_ansicht += 1  # die Live-Ansicht darunter rechnet nicht mehr
    meine_nummer = state.live_ansicht
    hl = HfLive(page, state, lauf)
    einst = state.hrv_einstellungen()
    fenster = Fenster(einst.fenster_s, state.messung_ende_s)
    st = _Stand(
        hoehe=max(160.0, float(page.height or 480) - _KOPF_PX),
        breite=max(320.0, float(page.width or 800) - WERTE_PX - LEISTE_PX - 8),
    )
    kurven_box = ft.Container()

    def anfang() -> float:
        return max(0.0, lauf.jetzt_s() - lauf.live.max_s)

    def bereich() -> tuple[float, float]:
        return fenster.bereich(lauf.jetzt_s(), anfang())

    def mitte() -> float:
        return sum(bereich()) / 2

    def zeit_text(x_von: float, x_bis: float) -> Callable[[float], str]:
        x_text, _ = achse(lauf.achse_utc, x_von, x_bis, uhrzeit=einst.achse_uhrzeit)
        return x_text or minuten

    # -- Notizen (wie im HRV-Vollbild, als Seitenleiste) ------------------------------------

    def zeigen(x: float) -> None:
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - lauf.jetzt_s(), lauf.jetzt_s(), anfang())

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lauf.notiz_zeitbezug,
        ereignisse=lauf.ereignisse,
        speichern=lauf.ereignisse_setzen,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        zeigen=zeigen,
        mitte=mitte,
        jetzt=lauf.jetzt_s,
        offen=True,
        offen_merken=lambda offen: setattr(state, "notizen_offen", offen),
        uebungen=(lambda: uebungsquellen(state)) if einst.notiz_uebungen else None,
        uebungen_offen=state.notiz_uebungen_offen,
        quelle=state.notiz_uebungen_quelle,
        uebungen_merken=uebungen_merken,
        katalog=(lambda: uebungs_katalog(state)) if einst.notiz_uebungen else None,
        breite=lambda: fenster.breite_s,
        zeit_modus=UHR if einst.achse_uhrzeit else DAUER,
        dialog=page.show_dialog,
        zeilen=lambda: state.hrv_einstellungen().notizen_zeilen,
    )

    # Abschnitte wie im HRV-Vollbild und hochkant (Ben, 12.11.2026: „halte das
    # einheitlich“): dasselbe Feld als Seitenleiste — Start/Ende, Marker, Nachtragen, Liste
    live_abschnitte = LiveAbschnitte(
        page,
        state,
        lauf,
        fenster=fenster,
        anfang=anfang,
        breite_gesetzt=lambda b: setattr(
            breiten_knoepfe, "selected", breiten_auswahl(b, einst.breiten())
        ),
        notizen_auffrischen=lambda: notizfeld.auffrischen(),
        danach=lambda: aktualisieren(erzwingen=True),
        offen=True,
    )

    def timer_notizen() -> None:
        notizfeld.auffrischen()
        live_abschnitte.neu(erzwingen=True)
        aktualisieren(erzwingen=True)

    state.notiz_beobachter["live"] = timer_notizen

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Knöpfe der Leiste --------------------------------------------------------------

    def talk() -> None:
        if not hl.talk_marke():
            melden("Erst eine Aufnahme starten.")
            return
        notizfeld.auffrischen()
        melden("Marke gesetzt — die Auswertung bietet die HF davor als Schwelle 1 an.")
        aktualisieren(erzwingen=True)

    def belastung_endet() -> None:
        hl.erholung_starten()
        notizfeld.auffrischen()
        fenster.ende_s = None  # die Erholung läuft in der Gegenwart
        aktualisieren(erzwingen=True)

    def erholung_beenden() -> None:
        hl.erholung_beenden()
        aktualisieren(erzwingen=True)

    def neue_belastung() -> None:
        """Die Erholung endet, weil es weitergeht — in der Aufnahme als schlichte Notiz."""
        hl.erholung_beenden()
        if hl.notiz("Belastung beginnt"):
            notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    def seite_umschalten(welche: str) -> None:
        st.seite = None if st.seite == welche else welche
        if st.seite == NOTIZEN:
            notizfeld.aufklappen()
        aktualisieren(erzwingen=True)

    def ton_tippen() -> None:
        """Der Knopf „Ton“: stumm hebt er das Schweigen auf, sonst öffnet er die Seite."""
        if hl.stumm() is not None:
            hl.stumm_setzen(None)
            aktualisieren(erzwingen=True)
        else:
            seite_umschalten(ZIEL)

    # -- Intervall ----------------------------------------------------------------------

    def intervall_umschalten() -> None:
        if state.hf_intervall is not None:
            state.hf_intervall = None
            aktualisieren(erzwingen=True)
            return
        if fenster.ende_s is None:
            fenster.ende_s = lauf.jetzt_s()  # anhalten, damit man ablesen kann
        x_von, x_bis = bereich()
        breite = x_bis - x_von
        t0 = hl.letztes_belastungsende()
        von = t0 if t0 is not None and x_von <= t0 < x_bis - 5 else x_von + breite / 3
        bis = min(lauf.jetzt_s(), x_bis) - 2.5
        if bis <= von + 5:
            bis = min(von + max(breite / 3, 10.0), x_bis)
        state.hf_intervall = {"von": von, "bis": bis, "bezug": hz.BEZUG_SPITZE}
        aktualisieren(erzwingen=True)

    def intervall_naechste(x: float) -> str:
        iv = state.hf_intervall or {}
        return "von" if abs(x - iv["von"]) <= abs(x - iv["bis"]) else "bis"

    def intervall_setzen(welche: str, x: float) -> None:
        iv = state.hf_intervall
        if iv is None:
            return
        x = min(max(x, anfang()), lauf.jetzt_s())
        if welche == "von":
            iv["von"] = min(x, iv["bis"] - 1.0)
        else:
            iv["bis"] = max(x, iv["von"] + 1.0)

    def intervall_bezug(bezug: str) -> None:
        if state.hf_intervall is not None:
            state.hf_intervall["bezug"] = bezug
            aktualisieren(erzwingen=True)

    def intervall_ende_aufs_tal() -> None:
        iv = state.hf_intervall
        if iv is None:
            return
        erg = hl.intervall(iv["von"], iv["bis"], iv["bezug"])
        if erg.tal_t is not None:
            iv["bis"] = max(erg.tal_t, iv["von"] + 1.0)
            aktualisieren(erzwingen=True)

    def intervall_als_notiz() -> None:
        iv = state.hf_intervall
        if iv is None:
            return
        erg = hl.intervall(iv["von"], iv["bis"], iv["bezug"])
        text = intervall_notiz(erg.hrr, erg.x_s, erg.bezug_hf, erg.hf_bis, erg.bezug)
        if hl.notiz(text, erg.bis):
            notizfeld.auffrischen()
            melden("Als Notiz am Ende des Intervalls festgehalten.")
        else:
            melden("Erst eine Aufnahme starten — Notizen leben in der Messdatei.")
        aktualisieren(erzwingen=True)

    def intervall_zeichnen(x_von: float, x_bis: float) -> None:
        iv = state.hf_intervall
        # Die Live-Achse hat neu bei 0 begonnen (Aufnahme gestartet, neu verbunden): Ein
        # Intervall von vorher liegt an Stellen, die es nicht mehr gibt (H103)
        if iv is not None and iv["von"] > lauf.jetzt_s():
            state.hf_intervall = iv = None
        intervall_box.visible = iv is not None
        if iv is None:
            intervall_box.content, st.intervall_karte = None, None
            return
        erg = hl.intervall(iv["von"], iv["bis"], iv["bezug"])
        schluessel = (
            *(
                None if w is None else (w if isinstance(w, str) else round(w, 1))
                for w in erg.als_dict().values()
            ),
            einst.achse_uhrzeit,
            lauf.aufnahme is not None,
        )
        if schluessel != st.intervall_karte:
            st.intervall_karte = schluessel
            intervall_box.content = intervall_karte(
                erg,
                zeit_text(x_von, x_bis),
                bezug_setzen=intervall_bezug,
                ende_aufs_tal=intervall_ende_aufs_tal,
                als_notiz=intervall_als_notiz,
                schliessen=intervall_umschalten,
            )
        # Die Karte weicht dem Intervall aus: links, wenn es in der rechten Hälfte liegt
        rechts = (iv["von"] + iv["bis"]) / 2 < (x_von + x_bis) / 2
        intervall_box.left = (
            max(st.breite - _BAND_ACHSE_PX - INTERVALL_PX - 4, 0.0) if rechts else _ACHSE_LINKS_PX
        )
        intervall_box.top = 4

    # -- Gesten in der Kurve ----------------------------------------------------------------

    def kurve_tippen(x: float, _y: float) -> None:
        if live_abschnitte.tippen(x):  # offener Abschnitts-Editor: die Grenze (P193)
            return
        if state.hf_intervall is not None:
            intervall_setzen(intervall_naechste(x), x)
            aktualisieren(erzwingen=True)
        elif notizfeld.waehlen:
            notizfeld.tippen(x)

    def kurve_greifen(x: float) -> bool:
        if live_abschnitte.greifen(x):
            return True
        iv = state.hf_intervall
        if iv is None:
            return notizfeld.greifen(x)
        if st.greift is None:
            welche = intervall_naechste(x)
            if abs(x - iv[welche]) > fenster.breite_s * _GREIF_ANTEIL:
                return False
            st.greift = welche
        intervall_setzen(st.greift, x)
        return True

    def losgelassen() -> None:
        if st.greift is not None:
            st.greift = None
            aktualisieren(erzwingen=True)
        else:
            notizfeld.loslassen()

    # -- Zielbereich: Griffe am rechten Rand ------------------------------------------------

    def griff(seite: str) -> tuple[ft.Container, ft.Text]:
        text = ft.Text(size=11, weight=ft.FontWeight.W_600, color=ft.Colors.BLACK)

        def start(_e: object) -> None:
            ohne_auto_update()
            oben, unten = ziel_grenzen(hl.einst())
            wert = oben if seite == "oben" else unten
            if wert is not None:
                st.zug = (seite, wert)

        def zug(e: ft.DragUpdateEvent) -> None:
            ohne_auto_update()
            if st.zug is None or st.y is None:
                return
            je_px = (st.y[1] - st.y[0]) / max(st.hoehe - ZEITACHSE_PX, 1.0)
            wert = st.zug[1] - float(e.primary_delta or 0.0) * je_px
            st.zug = (seite, wert)
            text.value = f"{wert:.0f} ↕"
            box.top = griff_oben_px(wert, st.y, st.hoehe)
            with contextlib.suppress(Exception):
                box.update()

        def ende(_e: object) -> None:
            if st.zug is None:
                return
            wert = st.zug[1]
            st.zug = None
            if seite == "oben":
                hl.ziel_aendern(oben=wert)
            else:
                hl.ziel_aendern(unten=wert)
            aktualisieren(erzwingen=True)

        box = ft.Container(
            visible=False,
            right=0,
            height=_GRIFF_PX,
            content=ft.GestureDetector(
                drag_interval=40,
                on_vertical_drag_start=start,
                on_vertical_drag_update=zug,
                on_vertical_drag_end=ende,
                on_tap=lambda _e: seite_umschalten(ZIEL) if st.seite != ZIEL else None,
                content=ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=8,
                    bgcolor=ZIEL_FARBE,
                    tooltip=f"Zielbereich {seite}: ziehen",
                    content=text,
                ),
            ),
        )
        return box, text

    griff_oben, griff_oben_text = griff("oben")
    griff_unten, griff_unten_text = griff("unten")

    def griffe_setzen() -> None:
        oben, unten = ziel_grenzen(hl.einst())
        for seite, wert, box, text in (
            ("oben", oben, griff_oben, griff_oben_text),
            ("unten", unten, griff_unten, griff_unten_text),
        ):
            if st.zug is not None and st.zug[0] == seite:
                continue  # folgt gerade dem Finger
            sichtbar = wert is not None and st.y is not None and st.y[0] <= wert <= st.y[1]
            box.visible = bool(sichtbar)
            if sichtbar and wert is not None and st.y is not None:
                text.value = f"{wert:.0f} ↕"
                box.top = griff_oben_px(wert, st.y, st.hoehe)

    # -- Zeichnen ---------------------------------------------------------------------------

    def kurve_bauen(x_von: float, x_bis: float, erg: hz.Erholung | None) -> ft.Control:
        aktuell = state.hrv_einstellungen()
        e = hl.einst()
        punkte = hl.kurvenpunkte(x_von, x_bis, float(aktuell.hf_mittel_s))
        st.punkte = punkte
        werte = [w for _, w in punkte]
        y_von, y_bis = wertebereich(e, hl.profil.ruhe_bpm, hl.profil.hfmax_bpm, werte)
        haupt = Reihe(punkte, farbe=ft.Colors.PRIMARY)
        st.y = y_grenzen([haupt], y_von=y_von, y_bis=y_bis, y_spanne_min=HF_SPANNE_MIN_BPM)
        reihen: list[Reihe] = [*einatem_schatten(state, lauf.jetzt_s(), x_von, x_bis)]
        marken = [*notizfeld.marken(x_von, x_bis), *live_abschnitte.reihen(x_von, x_bis)]
        if erg is not None:
            # Die vorige Erholung blass dahinter, auf das jetzige Belastungsende geschoben
            vorige = hl.fruehere_erholungen()
            if vorige:
                versatz = erg.t0 - vorige[-1].t0
                blass = [
                    (t + versatz, w)
                    for t, w in hl.kurvenpunkte(
                        vorige[-1].t0, vorige[-1].t0 + e.messen_bis(), float(aktuell.hf_mittel_s)
                    )
                    if x_von <= t + versatz <= x_bis
                ]
                if blass:
                    reihen.append(Reihe(blass, farbe=ft.Colors.OUTLINE, breite=1.5, skala=False))
            marken.append(senkrechte([erg.t0], ft.Colors.PRIMARY, 1.5, gestrichelt=False))
            fenster_x = [erg.t0 + f for f in erg.hrr if x_von <= erg.t0 + f <= x_bis]
            if fenster_x:
                marken.append(senkrechte(fenster_x, ft.Colors.OUTLINE, 1.0, gestrichelt=True))
        reihen.append(haupt)
        if st.y is not None:
            oben, unten = ziel_grenzen(e)
            hf = werte[-1] if werte else None
            for wert, aktiv in (
                (oben, hf is not None and oben is not None and hf > oben),
                (unten, hf is not None and unten is not None and hf < unten),
            ):
                if wert is not None and st.y[0] < wert < st.y[1]:
                    reihen.append(
                        Reihe(
                            [(x_von, wert), (x_bis, wert)],
                            farbe=ZIEL_FARBE,
                            breite=2.0 if aktiv else 1.5,
                            gestrichelt=not aktiv,
                            skala=False,
                        )
                    )
        iv = state.hf_intervall
        if iv is not None:
            im_bild = [x for x in (iv["von"], iv["bis"]) if x_von <= x <= x_bis]
            if im_bild:
                marken.append(senkrechte(im_bild, ft.Colors.ON_SURFACE, 1.6, gestrichelt=False))
        x_text, x_null = achse(lauf.achse_utc, x_von, x_bis, uhrzeit=einst.achse_uhrzeit)
        return kurve(
            [*reihen, *marken],
            einheit="HF bpm",
            hoehe=int(st.hoehe),
            x_von=x_von,
            x_bis=x_bis,
            y_von=y_von,
            y_bis=y_bis,
            y_spanne_min=HF_SPANNE_MIN_BPM,
            x_text=x_text,
            x_null=x_null,
            baender=hf_baender(hl.bereiche),
        )

    def werte_setzen(hf: float | None, zus: dict[str, Any] | None, erg: hz.Erholung | None) -> None:
        e = hl.einst()
        zahl_text.value = zahl(hf)
        b = bereich_von(hf, list(hl.bereiche))
        teile = [b.name] if b is not None else []
        if hl.profil.vollstaendig and hf is not None:
            teile.append(f"{prozent_text(hl.profil.prozent(hf))} Reserve")
        bereich_text.value = " · ".join(teile)
        z = zus or {}
        if erg is not None:
            seit = None if hf is None or erg.hf_ende is None else hf - erg.hf_ende
            trend.value = (
                "" if seit is None else f"{'↘ −' if seit <= 0 else '↗ +'}{abs(seit):.0f} seit Ende"
            )
            zeilen = [("HF am Ende", zahl(erg.hf_ende)), ("", ""), ("", ""), ("", ""), ("", "")]
        else:
            trend.value = trend_text(hl.trend())
            oben, unten = ziel_grenzen(e)
            drin, gesamt = zeit_im_ziel(st.punkte or [], oben, unten)
            drift = hl.drift()
            dfa = hl.dfa_a1() if zur_hrv is not None else None
            zeilen = [
                ("Ø " + bezug_name_kurz(), zahl(z.get("mittel_bpm"))),
                ("Gipfel", zahl(z.get("gipfel_bpm"))),
                (
                    "Im Zielbereich",
                    ziel_anteil_text(drin, gesamt) if (oben or unten) else "–",
                ),
                ("Drift", "–" if drift is None else f"{drift:+.0f} bpm".replace("-", "−")),
                ("DFA α1", "–" if dfa is None else f"{dfa:.2f}".replace(".", ",")),
            ]
        for (name, wert), (name_t, wert_t) in zip(zeilen, wert_zeilen, strict=True):
            name_t.value, wert_t.value = name, wert
        haltung_wahl.visible = kontext_wahl.visible = erg is not None
        if erg is not None and state.hf_erholung is not None:
            haltung_wahl.value = state.hf_erholung.get("haltung", "steht")
            kontext_wahl.value = state.hf_erholung.get("kontext", "dauer")

    def bezug_name_kurz() -> str:
        return BEZUG_NAMEN.get(state.hf_bezug, "")

    def kopf_setzen(hf: float | None, erg: hz.Erholung | None, abschnitt_laeuft: bool) -> None:
        e = hl.einst()
        titel.value = "Erholung" if erg is not None else "Herzfrequenz"
        if erg is not None:
            seit = max(0.0, lauf.jetzt_s() - erg.t0)
            chip_text.value = f"seit Belastungsende {minuten(seit)}"
            chip2_text.value = f"Messen bis {minuten(e.messen_bis_anzeige())}"
            chip2.visible = True
            chip.tooltip = None
        else:
            bezug = state.hf_bezug if state.hf_bezug in BEZUG_NAMEN else BEZUEGE[0]
            if bezug == BEZUG_ABSCHNITT and not abschnitt_laeuft:
                bezug = BEZUEGE[0]
            chip_text.value = f"Bezug: {BEZUG_NAMEN[bezug]}"
            chip.tooltip = "Bezug der Werte wechseln: Aufnahme · Abschnitt · 5 min"
            chip2.visible = False
        lage = lage_text(hf, e) if e.alarm_an else ""
        lage_tag_text.value = lage
        lage_tag.visible = bool(lage)
        if fenster.ende_s is None:
            zurueck_box.visible = False
        else:
            zurueck = lauf.jetzt_s() - bereich()[1]
            zurueck_text.value = f"−{minuten(zurueck)}"
            zurueck_box.visible = True

    def leiste_setzen(erg: hz.Erholung | None) -> None:
        e = hl.einst()
        laeuft = erg is not None
        knopf1_text.value = "Erholung beenden" if laeuft else "Sprechen wird schwer"
        knopf2_text.value = "Neue Belastung beginnt" if laeuft else "Belastung endet jetzt"
        stumm = hl.stumm()
        ziel = ziel_text(e)
        if stumm is not None:
            ton_text.value = "Ton " + stumm.text(time.monotonic())
        elif e.alarm_an:
            ton_text.value = f"Ton an · {ziel}" if ziel else "Ton an"
        else:
            ton_text.value = f"Ton aus · {ziel}" if ziel else "Zielbereich"
        for knopf, aktiv in (
            (ton_knopf, st.seite == ZIEL),
            (notiz_knopf, st.seite == NOTIZEN),
            (abschnitte_knopf, st.seite == ABSCHNITTE),
            (intervall_knopf, state.hf_intervall is not None),
        ):
            knopf.bgcolor = ft.Colors.with_opacity(
                0.30 if aktiv else 0.10, ft.Colors.PRIMARY if aktiv else ft.Colors.ON_SURFACE
            )

    def erholung_zeichnen(erg: hz.Erholung | None, rest: dict[int, float]) -> None:
        erholung_box.visible = erg is not None and state.hf_intervall is None
        if erg is None:
            erholung_box.content, st.erholung_karte = None, None
            return
        vorige = hl.fruehere_erholungen()
        schluessel = (
            erg.t0,
            tuple((f, None if w is None else round(w)) for f, w in erg.hrr.items()),
            tuple(int(r) for r in rest.values()),
            len(vorige),
        )
        if schluessel != st.erholung_karte:
            st.erholung_karte = schluessel
            erholung_box.content = erholung_karte(
                erg,
                rest,
                vorige[-1] if vorige else None,
                x_s=hl.einst().erholung_x_s,
                x_bearbeiten=darstellung,
            )

    def seite_setzen() -> None:
        seite_box.visible = st.seite is not None
        seite_box.width = ZIEL_SEITE_PX if st.seite == ZIEL else SEITE_PX
        if st.seite == st.seite_gebaut:
            return
        st.seite_gebaut = st.seite
        if st.seite == ZIEL:
            seite_inhalt.controls = [
                seitenkopf("Zielbereich und Ton", lambda: seite_umschalten(ZIEL)),
                ziel_seite(
                    hl,
                    lambda: aktualisieren(erzwingen=True),
                    stumm_knoepfe=stumm_knoepfe_zeiten(),
                ),
            ]
        elif st.seite == NOTIZEN:
            seite_inhalt.controls = [
                seitenkopf("Notizen", lambda: seite_umschalten(NOTIZEN)),
                notizfeld.control,
            ]
        elif st.seite == ABSCHNITTE:
            seite_inhalt.controls = [
                seitenkopf("Abschnitte", lambda: seite_umschalten(ABSCHNITTE)),
                live_abschnitte.control,
            ]
        else:
            seite_inhalt.controls = []

    def fuellen() -> None:
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = bereich()
        hf, zus, _, abschnitt_laeuft = hl.live_werte()
        hl.ton_pruefen(hf)
        erg, rest = hl.erholung_live()
        kurven_box.content = kurve_bauen(x_von, x_bis, erg)
        griffe_setzen()
        werte_setzen(hf, zus, erg)
        kopf_setzen(hf, erg, abschnitt_laeuft)
        atem_text.value = zaehl_stand.atem_kopf_text(state)
        atem_text.visible = bool(atem_text.value)
        leiste_setzen(erg)
        erholung_zeichnen(erg, rest)
        intervall_zeichnen(x_von, x_bis)
        live_abschnitte.neu()
        seite_setzen()

    def aktualisieren(erzwingen: bool = False) -> None:
        if state.live_ansicht != meine_nummer:
            return
        jetzt = time.monotonic()
        if not erzwingen and jetzt - st.zuletzt < 0.5:
            return
        st.zuletzt = jetzt
        fuellen()
        notizfeld.tick()
        with contextlib.suppress(Exception):
            spalte.update()

    def gewischt() -> None:
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = bereich()
        erg, _ = hl.erholung_live()
        kurven_box.content = kurve_bauen(x_von, x_bis, erg)
        griffe_setzen()
        intervall_zeichnen(x_von, x_bis)
        for c in (kurven_box, griff_oben, griff_unten, intervall_box):
            with contextlib.suppress(Exception):
                c.update()

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    def zur_gegenwart(_e: object = None) -> None:
        fenster.ende_s = None
        aktualisieren(erzwingen=True)

    def breite_waehlen(breite_s: float) -> None:
        fenster.breite_links(breite_s, lauf.jetzt_s(), anfang())
        aktuell = state.hrv_einstellungen()
        aktuell.fenster_s = round(breite_s)
        state.hrv_einstellungen_setzen(aktuell)
        breiten_knoepfe.selected = breiten_auswahl(breite_s, einst.breiten())
        aktualisieren(erzwingen=True)

    def achse_umschalten() -> None:
        einst.achse_uhrzeit = not einst.achse_uhrzeit
        aktuell = state.hrv_einstellungen()
        aktuell.achse_uhrzeit = einst.achse_uhrzeit
        state.hrv_einstellungen_setzen(aktuell)
        aktualisieren(erzwingen=True)

    def breiten_satz() -> BreitenSatz:
        def geaendert(neu: HrvEinstellungen) -> None:
            einst.breiten_satz, einst.breiten_eigen = neu.breiten_satz, list(neu.breiten_eigen)
            breiten_nachziehen(breiten_knoepfe, neu.breiten(), fenster.breite_s, kompakt=True)

        return BreitenSatz(state.hrv_einstellungen, state.hrv_einstellungen_setzen, geaendert)

    def darstellung() -> None:
        """„Fenster & Achse“: Zeitachse, Mittel der Kurve, Wertebereich je Seite, Erholung."""

        def geaendert() -> None:
            aktualisieren(erzwingen=True)

        def mittel_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            if e.control.value is not None:
                aktuell = state.hrv_einstellungen()
                aktuell.hf_mittel_s = int(e.control.value)
                state.hrv_einstellungen_setzen(aktuell)
                geaendert()

        page.show_dialog(
            darstellung_blatt(
                page,
                state,
                geaendert,
                zeitachse=Zeitachse(
                    fenster.breite_s,
                    breite_waehlen,
                    max_s=lauf.live.max_s,
                    satz=breiten_satz().control,
                    uhrzeit=einst.achse_uhrzeit,
                    uhrzeit_setzen=achse_umschalten,
                ),
                kurven_teil=False,
                gruppen_vor=[
                    wertebereich_gruppe(hl, geaendert),
                    (
                        "Herzfrequenz",
                        [
                            ft.Dropdown(
                                label="Kurve als Mittel über",
                                value=str(state.hrv_einstellungen().hf_mittel_s),
                                options=[
                                    ft.DropdownOption(key=str(x), text=f"{x} s")
                                    for x in HF_MITTEL_S
                                ],
                                on_select=mittel_gewaehlt,
                                dense=True,
                                border=ft.OutlineInputBorder(border_radius=8),
                            )
                        ],
                    ),
                ],
                gruppen_nach=[erholung_gruppe(hl, geaendert)],
            )
        )

    def bezug_weiter(_e: object = None) -> None:
        """Der Chip „Bezug“: Aufnahme → Abschnitt → 5 min (ohne Menü — ein Menü reichte den
        Tipp, der es schließt, an die Kurve weiter)."""
        if state.hf_erholung is not None:
            return
        i = BEZUEGE.index(state.hf_bezug) if state.hf_bezug in BEZUEGE else 0
        for _ in BEZUEGE:
            i = (i + 1) % len(BEZUEGE)
            if BEZUEGE[i] != BEZUG_ABSCHNITT or (
                lauf.aufnahme is not None and lauf.offener_abschnitt() is not None
            ):
                break
        state.hf_bezug = BEZUEGE[i]
        aktualisieren(erzwingen=True)

    def messen_bis_weiter(_e: object = None) -> None:
        e = hl.einst(frisch=True)
        groesser = [s for s in MESSEN_BIS_S if s > e.messen_bis_anzeige()]
        e.messen_bis_s = groesser[0] if groesser else MESSEN_BIS_S[0]
        hl.einst_speichern(e)
        aktualisieren(erzwingen=True)

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        hoehe, breite = max(120.0, float(e.height)), float(e.width)
        if abs(hoehe - st.hoehe) < 4 and abs(breite - st.breite) < 4:
            return
        st.hoehe, st.breite = hoehe, breite
        aktualisieren(erzwingen=True)

    # -- Controls: einmal gebaut ----------------------------------------------------------

    def chip_(text: ft.Text, tipp: Callable[[object], None]) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=14,
            ink=True,
            on_click=tipp,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE),
            content=text,
        )

    titel = ft.Text("Herzfrequenz", size=15, weight=ft.FontWeight.W_600)
    chip_text = ft.Text(size=12)
    chip = chip_(chip_text, bezug_weiter)
    chip2_text = ft.Text(size=12)
    chip2 = chip_(chip2_text, messen_bis_weiter)
    chip2.tooltip = "Messen bis: nächste Dauer"
    chip2.visible = False
    lage_tag_text = ft.Text(size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLACK)
    lage_tag = ft.Container(
        visible=False,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=8,
        bgcolor=ZIEL_FARBE,
        content=lage_tag_text,
    )
    #: Rate und Phase der Atmung, solange ein Zähl-Teil sie erfasst — wie im HRV-Vollbild
    atem_text = ft.Text(
        size=12,
        weight=ft.FontWeight.W_600,
        color=FARBEN["atemfrequenz"],
        visible=False,
        tooltip="Atmung aus dem Beschleunigungssensor: Rate, Phase (▲ ein, ▼ aus) und die "
        "Atemspanne des letzten Atemzugs (Prototyp)",
    )
    zurueck_text = ft.Text(size=12, opacity=0.7)
    zurueck_box = ft.Row(
        spacing=2,
        tight=True,
        visible=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            zurueck_text,
            ft.TextButton("Live", icon=ft.Icons.SKIP_NEXT, on_click=zur_gegenwart),
        ],
    )
    breiten_knoepfe = breiten_wahl(
        fenster.breite_s, breite_waehlen, kompakt=True, breiten=einst.breiten()
    )
    kopf = ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(ft.Icons.CLOSE, tooltip="Vollbild verlassen", on_click=schliessen),
            titel,
            chip,
            chip2,
            ft.Container(expand=True),
            atem_text,
            lage_tag,
            zurueck_box,
            breiten_knoepfe,
            ft.OutlinedButton(
                "HRV",
                icon=ft.Icons.SWAP_HORIZ,
                tooltip="Zur HRV-Ansicht wechseln",
                visible=zur_hrv is not None,
                on_click=lambda _=None: zur_hrv() if zur_hrv is not None else None,
            ),
        ],
    )

    zahl_text = ft.Text("–", size=58, weight=ft.FontWeight.W_600)
    bereich_text = ft.Text(size=13, weight=ft.FontWeight.W_600)
    trend = ft.Text(size=12, color=ft.Colors.PRIMARY)
    wert_zeilen = [
        (ft.Text(size=12, opacity=0.7, expand=True), ft.Text(size=12, weight=ft.FontWeight.W_600))
        for _ in range(5)
    ]

    def wahl(label: str, namen: dict[str, str], setzen: Callable[[str], None]) -> ft.Dropdown:
        def gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            w = str(e.control.value or "")
            if w in namen:
                setzen(w)
                aktualisieren(erzwingen=True)

        return ft.Dropdown(
            label=label,
            options=[ft.DropdownOption(key=k, text=v) for k, v in namen.items()],
            on_select=gewaehlt,
            dense=True,
            text_size=12,
            visible=False,
            border=ft.OutlineInputBorder(border_radius=8),
        )

    haltung_wahl = wahl("Haltung", HALTUNG_NAMEN, lambda w: hl.erholung_setzen(haltung=w))
    kontext_wahl = wahl("Woran", KONTEXT_NAMEN, lambda w: hl.erholung_setzen(kontext=w))
    dfa_zeile = ft.Container(
        ink=zur_hrv is not None,
        on_click=(lambda _=None: zur_hrv()) if zur_hrv is not None else None,
        tooltip="DFA α1 der letzten zwei Minuten — zur HRV-Ansicht" if zur_hrv else None,
        content=ft.Row(spacing=4, controls=list(wert_zeilen[4])),
    )
    werte_spalte = ft.Container(
        width=WERTE_PX,
        padding=ft.Padding.only(left=10, right=6, bottom=6),
        content=ft.Column(
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[zahl_text, ft.Text("bpm", size=12, opacity=0.7)],
                ),
                bereich_text,
                trend,
                ft.Divider(height=8),
                *(ft.Row(spacing=4, controls=list(z)) for z in wert_zeilen[:4]),
                dfa_zeile,
                haltung_wahl,
                kontext_wahl,
            ],
        ),
    )

    def leistenknopf(
        text: ft.Text, tipp: Callable[[], None], *, betont: bool = False, tooltip: str = ""
    ) -> ft.Container:
        return ft.Container(
            height=46,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=6),
            border_radius=10,
            ink=True,
            tooltip=tooltip or None,
            on_click=lambda _=None: tipp(),
            bgcolor=ft.Colors.with_opacity(
                0.22 if betont else 0.10, ft.Colors.PRIMARY if betont else ft.Colors.ON_SURFACE
            ),
            content=text,
        )

    def knopftext(wert: str = "") -> ft.Text:
        return ft.Text(wert, size=12, text_align=ft.TextAlign.CENTER, max_lines=2)

    knopf1_text, knopf2_text, ton_text = knopftext(), knopftext(), knopftext()
    ton_knopf = leistenknopf(ton_text, ton_tippen, tooltip="Zielbereich und Ton")
    notiz_knopf = leistenknopf(
        knopftext("Notiz"), lambda: seite_umschalten(NOTIZEN), tooltip="Notizen: Liste, Text, Zeit"
    )
    abschnitte_knopf = leistenknopf(
        knopftext("Abschnitte"),
        lambda: seite_umschalten(ABSCHNITTE),
        tooltip="Abschnitte: Start/Ende, Liste",
    )
    intervall_knopf = leistenknopf(
        knopftext("Intervall"),
        intervall_umschalten,
        tooltip="Ablesen zwischen zwei Zeitpunkten: HF-Max, HF-Min, Erholung",
    )
    leiste_ = ft.Container(
        width=LEISTE_PX,
        padding=ft.Padding.only(left=2, right=2, bottom=4),
        content=ft.Column(
            spacing=5,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                leistenknopf(
                    knopf1_text,
                    lambda: erholung_beenden() if state.hf_erholung is not None else talk(),
                    betont=True,
                ),
                leistenknopf(
                    knopf2_text,
                    lambda: (
                        neue_belastung() if state.hf_erholung is not None else belastung_endet()
                    ),
                    betont=True,
                ),
                notiz_knopf,
                abschnitte_knopf,
                ton_knopf,
                intervall_knopf,
                leistenknopf(
                    knopftext("Fenster & Achse"), darstellung, tooltip="Fenster und Darstellung"
                ),
            ],
        ),
    )
    erholung_box = ft.Container(visible=False, right=_BAND_ACHSE_PX + 4, top=4)
    intervall_box = ft.Container(visible=False, left=_ACHSE_LINKS_PX, top=4)
    seite_inhalt = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, controls=[])
    seite_box = ft.Container(
        visible=False,
        width=ZIEL_SEITE_PX,
        padding=ft.Padding.only(left=10, right=6, bottom=6),
        border_radius=ft.BorderRadius.only(top_left=16),
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        content=seite_inhalt,
    )
    flaeche = ft.Container(
        expand=True,
        on_size_change=groesse,
        content=ft.Stack(
            expand=True,
            fit=ft.StackFit.EXPAND,
            controls=[
                wischbar(
                    kurven_box,
                    fenster,
                    lauf.jetzt_s,
                    gewischt,
                    anfang=anfang,
                    greifen=kurve_greifen,
                    losgelassen=losgelassen,
                    tippen_punkt=kurve_tippen,
                    rechts_px=lambda: _BAND_ACHSE_PX if hl.bereiche else 0.0,
                ),
                griff_oben,
                griff_unten,
                erholung_box,
                intervall_box,
            ],
        ),
    )
    koerper = ft.Row(
        expand=True,
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[werte_spalte, flaeche, seite_box, leiste_],
    )
    spalte = ft.Column(spacing=0, expand=True, controls=[kopf, koerper])
    fuellen()
    lauf.beobachter = beobachten
    state.einheit_beobachter["live_vollbild"] = lambda: aktualisieren()
    return ft.View(
        route="/live",
        padding=ft.Padding.only(left=4, right=4, top=0, bottom=0),
        controls=[sicher(spalte)],
    )


__all__ = ["griff_oben_px", "hf_vollbild"]
