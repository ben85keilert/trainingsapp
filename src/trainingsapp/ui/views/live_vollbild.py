"""Live-Vollbild: die Kurven der laufenden Messung, quer, ohne Leisten.

Route ``/live`` (Ben, 15.10.2026). Der Knopf an der Tachogramm-Karte öffnet es,
`ui.ausrichtung` dreht den Bildschirm dabei ins Querformat; Zurück stellt
hochkant wieder her.

Seit dem 16.10.2026 (Ben) gebaut wie das Vollbild der Aufzeichnung
(`components.vollbild`):

- **Zwei y-Achsen:** links standardmäßig das Tachogramm, rechts RMSSD — je
  Achse ‹ Name ▾ › in der Kopfzeile; die Pfeile blättern, die Liste wählt
  (gleiche Skala kommt dazu, z. B. HF Gerät zu Ø HF). Hoch/runter wischen
  blättert nicht mehr: Es fuhr beim Zeitwischen dazwischen. Waagrecht wischen
  blättert in der Zeit (`zeitfenster.wischbar`).
- **Werkzeugleiste rechts:** Ablesen (hält die Kurve an, „Live" läuft wieder
  mit), Notiz ohne Text (jetzt, zurückgeblättert: Fenstermitte), Notizen in
  einer Seitenleiste mit denselben Feldern wie hochkant (Text, Zeit, Übungen)
  und Fenster & Darstellung der gezeigten Kurven.
- **Etikett:** Ein Tipp auf eine Notizmarke zeigt Zeit und Text in der Kurve,
  mit Bearbeiten und Löschen; jede Marke lässt sich mit dem Finger an ihre
  Stelle ziehen (`Notizfeld.greifen`).

Die Größe der Kurvenfläche wird gemessen (``on_size_change``), weil die Ansicht
noch hochkant gebaut wird und erst danach gedreht erscheint; bis dahin gilt
eine Schätzung aus ``page.height``.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft
from hrv_core.atmung import ATEMUEBUNG, RUHE
from hrv_core.trends import KENNZAHLEN

from trainingsapp.core.hrv_ansicht import LINKS, RECHTS, ROH
from trainingsapp.core.hrv_einstellungen import LIVE_FENSTER
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.ui.components.analyse import verlaufsdaten
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.verlauf import FARBEN, darstellung_blatt, fenster_text, werte_bei
from trainingsapp.ui.components.vollbild import (
    ETIKETT_PX,
    LEISTE_PX,
    SEITE_PX,
    ablese_karte,
    ablese_seite,
    angebot,
    doppelkurve,
    etikett,
    lage_px,
    leiste,
    markieren,
    rechts_px,
    seiten_wahl,
    seitenkopf,
    werkzeug,
)
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import ohne_rr, tachogramm_reihen

#: Platz über der Kurve (Kopfzeile) und Ränder — für die Schätzung vor der Messung (px)
_KOPF_PX = 56


def _uhr(sekunden: float) -> str:
    s = max(0, round(sekunden))
    return f"{s // 60}:{s % 60:02d}"


@dataclass
class _Stand:
    """Was das Vollbild über sich weiß — Größe, Ablesen, Etikett, Seitenleiste."""

    hoehe: float
    breite: float
    zuletzt: float = 0.0
    #: Ablesen: der Strich steht an ``strich`` (s); die Kurve steht dabei still
    ablesen: bool = False
    strich: float | None = None
    #: Notiz, deren Etikett in der Kurve steht (Index in den Ereignissen)
    etikett: int | None = None
    #: Seitenleiste „Notizen" offen
    notizen: bool = False
    #: Womit die Kopfzeile gebaut ist — neu nur bei Änderung, sonst schlösse
    #: das Auffrischen eine offene Liste
    kopf: tuple[Any, ...] = ()
    #: Gibt es RR-Werte? Einmal gesehen, bleibt es so (`kennzahlen` ist nicht billig)
    mit_rr: bool = False
    #: Wählbare Kurven und Breite der rechten Achse — je Zeichnung einmal bestimmt
    angebot: list[str] = field(default_factory=list)
    rechts: float = 0.0
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]] = field(default_factory=dict)


def live_vollbild_view(page: ft.Page, state: AppState) -> ft.View:
    """Die Ansicht hinter ``/live`` — ohne Gerät nur ein Hinweis mit Zurück."""
    lauf: Messlauf | None = state.messlauf

    async def schliessen() -> None:
        await page.push_route("/")

    if lauf is None or lauf.status.verbindung == Verbindung.GETRENNT:
        return ft.View(
            route="/live",
            padding=16,
            controls=[
                sicher(
                    ft.Column(
                        controls=[
                            ft.Text("Kein Gerät verbunden.", size=16),
                            ft.TextButton("Zurück", icon=ft.Icons.CLOSE, on_click=schliessen),
                        ]
                    )
                )
            ],
        )
    return _vollbild(page, state, lauf, schliessen)


def _vollbild(
    page: ft.Page, state: AppState, lauf: Messlauf, schliessen: Callable[[], Any]
) -> ft.View:
    state.live_ansicht += 1  # die Live-Ansicht darunter rechnet nicht mehr
    meine_nummer = state.live_ansicht
    einst = state.hrv_einstellungen()
    verity = bool(lauf.profil and lauf.profil.kann("pmd_ppi"))
    roh_titel = "PPI-Tachogramm" if verity else "RR-Tachogramm"
    fenster = Fenster(einst.fenster_s, state.messung_ende_s)
    speicher: dict[Any, Any] = {}
    kurven_box = ft.Container()
    lage_box = ft.Container()
    links_box = ft.Container()
    rechts_box = ft.Container()
    etikett_box = ft.Container(visible=False)
    ablese_box = ft.Container(visible=False)
    st = _Stand(
        hoehe=max(160.0, float(page.height or 480) - _KOPF_PX),
        breite=max(320.0, float(page.width or 800) - LEISTE_PX - 8),
    )

    def anfang() -> float:
        return max(0.0, lauf.jetzt_s() - lauf.live.max_s)

    def mitte() -> float:
        return sum(fenster.bereich(lauf.jetzt_s(), anfang())) / 2

    def kurven_angebot() -> list[str]:
        """Die wählbaren Kurven — ein reiner Pulsgeber hat nur „HF Gerät"."""
        st.mit_rr = st.mit_rr or bool(lauf.live.kennzahlen().rr_ms)
        ohne = [] if st.mit_rr else ohne_rr()
        return angebot(einst.bereiche(optisch=verity), ohne, roh=st.mit_rr)

    def stand_auffrischen() -> None:
        """Angebot und rechte Achse für diese Zeichnung — Wischen fragt sie dauernd."""
        st.angebot = kurven_angebot()
        st.rechts = rechts_px(state.ansicht(), st.angebot)

    # -- Notizen ------------------------------------------------------------------------

    def notizen_speichern(liste: list[dict]) -> None:
        # In der Aufnahme: mit Backup und Messdatei; vorher warten sie auf den Start
        # (Ben, 16.10.2026: Notizen schon vor der Aufnahme)
        lauf.ereignisse_setzen(liste)

    def zeigen(x: float) -> None:
        """Die Kurve auf eine Zeit rücken — nahe der Gegenwart folgt sie wieder."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - lauf.jetzt_s(), lauf.jetzt_s(), anfang())

    def notizen_offen(offen: bool) -> None:
        state.notizen_offen = offen

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lauf.notiz_zeitbezug,
        ereignisse=lauf.ereignisse,
        speichern=notizen_speichern,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        zeigen=zeigen,
        mitte=mitte,
        jetzt=lauf.jetzt_s,
        offen=state.notizen_offen,
        offen_merken=notizen_offen,
        uebungen=(lambda: uebungsquellen(state)) if einst.notiz_uebungen else None,
        uebungen_offen=state.notiz_uebungen_offen,
        quelle=state.notiz_uebungen_quelle,
        uebungen_merken=uebungen_merken,
        katalog=(lambda: uebungs_katalog(state)) if einst.notiz_uebungen else None,
        breite=lambda: fenster.breite_s,
    )

    def timer_notizen() -> None:
        """Der Timer hat Abschnitte als Notizen in die Aufnahme geschrieben."""
        notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    state.notiz_beobachter["live"] = timer_notizen

    def marke() -> None:
        if st.ablesen and st.strich is not None:
            x: float | None = st.strich
        else:
            x = None if fenster.ende_s is None else mitte()
        if not notizfeld.marke_setzen(x):
            page.show_dialog(ft.SnackBar(ft.Text("Hier lässt sich gerade keine Notiz setzen.")))

    def notizen_umschalten() -> None:
        st.notizen = not st.notizen
        if st.notizen:
            notizfeld.aufklappen()
        aktualisieren(erzwingen=True)

    def notiz_bearbeiten(i: int) -> None:
        st.etikett = None
        st.notizen = True
        notizfeld.aufklappen()
        notizfeld.bearbeiten(i)

    def notiz_loeschen(i: int) -> None:
        st.etikett = None
        weg = notizfeld.entfernen(i)
        if weg is None:
            return
        page.show_dialog(
            ft.SnackBar(
                ft.Text("Notiz gelöscht"),
                action=ft.SnackBarAction(
                    "Rückgängig", on_click=lambda: notizfeld.zurueckholen(weg)
                ),
            )
        )

    def etikett_schliessen() -> None:
        st.etikett = None
        aktualisieren(erzwingen=True)

    # -- Ablesen ----------------------------------------------------------------------------

    def schlaege_um(x: float) -> list[float]:
        return [p.t_s for p in lauf.live.punkte(seit_s=x - 10) if p.rr_ms > 0 and p.t_s <= x + 10]

    def schlag_bei(x: float) -> float:
        zeiten = schlaege_um(x)
        return min(zeiten, key=lambda t: abs(t - x)) if zeiten else x

    def ablesen_umschalten() -> None:
        st.ablesen = not st.ablesen
        if st.ablesen:
            st.etikett = None
            if fenster.ende_s is None:
                fenster.ende_s = lauf.jetzt_s()  # anhalten, damit man ablesen kann
            st.strich = schlag_bei(mitte())
        aktualisieren(erzwingen=True)

    def strich_setzen(x: float, *, zeichnen: bool = True) -> None:
        st.strich = schlag_bei(x)
        if zeichnen:
            aktualisieren(erzwingen=True)

    def strich_schritt(richtung: int) -> None:
        """Ein Schlag vor oder zurück; die Kurve rückt mit und bleibt angehalten."""
        jetzt = st.strich
        if jetzt is None:
            return
        weiter = [t for t in schlaege_um(jetzt) if (t - jetzt) * richtung > 1e-6]
        neu = min(weiter, key=lambda t: abs(t - jetzt)) if weiter else jetzt
        st.strich = neu
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        if not x_von <= neu <= x_bis:
            zeigen(neu)
            fenster.ende_s = fenster.ende_s or lauf.jetzt_s()
        aktualisieren(erzwingen=True)

    def ablese_werte(x: float) -> list[tuple[str | None, str, str, str]]:
        werte: list[tuple[str | None, str, str, str]] = []
        punkte = [p for p in lauf.live.punkte(seit_s=x - 3) if p.rr_ms > 0 and p.t_s <= x + 3]
        p = min(punkte, key=lambda q: abs(q.t_s - x), default=None)
        if p is not None:
            rr = p.rr_korr if einst.korrigiert and p.rr_korr else float(p.rr_ms)
            zusatz = " (verworfen)" if p.verworfen else " (auffällig)" if p.artefakt else ""
            werte.append((ft.Colors.PRIMARY, "PPI" if verity else "RR", zahl(rr), "ms" + zusatz))
            werte.append((FARBEN["hf_rr"], "HF", zahl(60000 / rr if rr else None), "bpm"))
        geraet = min(lauf.live.hf_reihe(), key=lambda q: abs(q[0] - x), default=None)
        if geraet is not None and abs(geraet[0] - x) < 3:
            werte.append((FARBEN["hf_geraet"], "HF Gerät", zahl(geraet[1]), "bpm"))
        for k, name, wert in werte_bei(st.gesehen, x):
            if k == "hf_geraet":
                continue  # steht schon da, aus dem Gerät
            stellen = 0 if abs(wert) >= 100 else 1 if abs(wert) >= 10 else 2
            werte.append((FARBEN.get(k), name, zahl(wert, stellen), KENNZAHLEN[k].einheit))
        return werte

    def ablesen_zeichnen(x_von: float, x_bis: float) -> None:
        x = st.strich
        ablese_box.visible = st.ablesen and x is not None
        if not ablese_box.visible or x is None:
            ablese_box.content = None
            return
        zb = lauf.notiz_zeitbezug()
        uhr = zb.uhr(zb.anker(x)) if zb is not None else ""
        ablese_box.content = ablese_karte(
            _uhr(x) + (f" · {uhr} Uhr" if uhr else ""),
            "",
            ablese_werte(x),
            schritt=strich_schritt,
            schliessen=ablesen_umschalten,
            schwebend=True,
        )
        ablese_seite(ablese_box, x, x_von, x_bis, st.rechts)

    # -- Gesten in der Kurve ----------------------------------------------------------------

    def kurve_tippen(x: float, _y: float) -> None:
        if st.ablesen:
            strich_setzen(x)
        elif notizfeld.waehlen:
            notizfeld.tippen(x)  # „In Kurve": der Tipp setzt die Zeit der Eingabe
        else:
            st.etikett = notizfeld.bei(x)
            aktualisieren(erzwingen=True)

    def kurve_greifen(x: float) -> bool:
        if st.ablesen:
            strich_setzen(x, zeichnen=False)
            return True
        return notizfeld.greifen(x)

    def losgelassen() -> None:
        notizfeld.loslassen()  # speichert eine gezogene Marke (zeichnet selbst neu)

    # -- Zeichnen ---------------------------------------------------------------------------

    def kurve_bauen(x_von: float, x_bis: float) -> ft.Control:
        ansicht = state.ansicht()
        atem_modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
        daten = verlaufsdaten(
            lauf.live.verlaufsreihe(),
            lauf.live.hf_reihe(),
            ansicht,
            atem_modus,
            speicher,
            x_von,
            x_bis,
        )
        marken = notizfeld.marken(x_von, x_bis)
        if st.ablesen and st.strich is not None and x_von <= st.strich <= x_bis:
            marken.append(senkrechte([st.strich], ft.Colors.ON_SURFACE, 1.2, gestrichelt=False))
        st.gesehen = {}
        return doppelkurve(
            ansicht,
            daten,
            lambda: tachogramm_reihen(lauf, x_von, x_bis, korrigiert=einst.korrigiert),
            angebot=st.angebot,
            x_von=x_von,
            x_bis=x_bis,
            hoehe=int(st.hoehe),
            roh_einheit="PPI ms" if verity else "RR ms",
            marken=marken,
            gesehen=st.gesehen,
        )

    def lage() -> ft.Control:
        if fenster.ende_s is None:
            return ft.Container()
        zurueck = lauf.jetzt_s() - fenster.bereich(lauf.jetzt_s(), anfang())[1]
        return ft.Row(
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(f"−{_uhr(zurueck)}", size=12, opacity=0.7),
                ft.TextButton("Live", icon=ft.Icons.SKIP_NEXT, on_click=zur_gegenwart),
            ],
        )

    def kopf_zeichnen() -> None:
        """Die Wahl der Achsen — nur neu gebaut, wenn sich etwas an ihr ändert."""
        a = state.ansicht()
        schluessel = (
            tuple(a.links),
            tuple(a.rechts),
            tuple(st.angebot),
            a.pnn_ms,
            tuple(sorted(a.fenster.items())),
            tuple(sorted(a.modus.items())),
        )
        if schluessel == st.kopf:
            return
        st.kopf = schluessel
        links_box.content = seiten_wahl(state, LINKS, st.angebot, roh_titel, kopf_geaendert)
        rechts_box.content = seiten_wahl(state, RECHTS, st.angebot, roh_titel, kopf_geaendert)

    def kopf_geaendert() -> None:
        kopf_zeichnen()
        aktualisieren(erzwingen=True)

    def etikett_zeichnen(x_von: float, x_bis: float) -> None:
        i = st.etikett
        info = notizfeld.etikett(i) if i is not None else None
        if i is None or info is None or not x_von <= info[0] <= x_bis:
            etikett_box.visible, etikett_box.content = False, None
            return
        x, zeit, text = info
        etikett_box.content = etikett(
            zeit,
            text,
            FARBEN["notiz"],
            [
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="Notiz bearbeiten",
                    on_click=lambda: notiz_bearbeiten(i),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Notiz löschen",
                    on_click=lambda: notiz_loeschen(i),
                ),
                ft.IconButton(
                    ft.Icons.CLOSE, tooltip="Etikett schließen", on_click=etikett_schliessen
                ),
            ],
        )
        etikett_box.left = lage_px(x, x_von, x_bis, st.breite, st.rechts, ETIKETT_PX)
        etikett_box.top = 4
        etikett_box.visible = True

    def fuellen() -> None:
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        stand_auffrischen()
        kopf_zeichnen()
        kurven_box.content = kurve_bauen(x_von, x_bis)
        lage_box.content = lage()
        etikett_zeichnen(x_von, x_bis)
        ablesen_zeichnen(x_von, x_bis)
        markieren(ablesen_knopf, st.ablesen)
        markieren(notizen_knopf, st.notizen)
        seite_box.visible = st.notizen

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
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        stand_auffrischen()
        kurven_box.content = kurve_bauen(x_von, x_bis)
        lage_box.content = lage()
        etikett_zeichnen(x_von, x_bis)
        ablesen_zeichnen(x_von, x_bis)
        for c in (kurven_box, lage_box, etikett_box, ablese_box):
            with contextlib.suppress(Exception):
                c.update()

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    def zur_gegenwart() -> None:
        fenster.ende_s = None
        st.ablesen = False  # „Live" heißt: wieder mitlaufen
        aktualisieren(erzwingen=True)

    def fenster_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        fenster.breite_s = int(e.control.selected[0])
        aktuell = state.hrv_einstellungen()
        aktuell.fenster_s = int(fenster.breite_s)
        state.hrv_einstellungen_setzen(aktuell)
        aktualisieren(erzwingen=True)

    def darstellung() -> None:
        a = state.ansicht()
        page.show_dialog(
            darstellung_blatt(
                page,
                state,
                lambda: aktualisieren(erzwingen=True),
                kurven=[k for k in (*a.links, *a.rechts) if k != ROH],
            )
        )

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        """Die wirkliche Größe der Kurvenfläche — nach dem Drehen anders als geschätzt."""
        hoehe, breite = max(120.0, float(e.height)), float(e.width)
        if abs(hoehe - st.hoehe) < 4 and abs(breite - st.breite) < 4:
            return
        st.hoehe, st.breite = hoehe, breite
        aktualisieren(erzwingen=True)

    ablesen_knopf = werkzeug(
        ft.Icons.ADS_CLICK, "Ablesen: Werte an einer Stelle", lambda: ablesen_umschalten()
    )
    notizen_knopf = werkzeug(
        ft.Icons.NOTES, "Notizen: Liste, Text, Zeit", lambda: notizen_umschalten()
    )
    seite_box = ft.Container(
        visible=False,
        width=SEITE_PX,
        content=ft.Column(
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            controls=[seitenkopf("Notizen", lambda: notizen_umschalten()), notizfeld.control],
        ),
    )
    kopf = ft.Row(
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(ft.Icons.CLOSE, tooltip="Vollbild verlassen", on_click=schliessen),
            links_box,
            ft.Container(expand=True),
            lage_box,
            ft.SegmentedButton(
                selected=[str(fenster.breite_s if fenster.breite_s in LIVE_FENSTER else 120)],
                show_selected_icon=False,
                style=ft.ButtonStyle(
                    visual_density=ft.VisualDensity.COMPACT,
                    padding=ft.Padding.symmetric(horizontal=6),
                ),
                segments=[
                    ft.Segment(value=str(s), label=ft.Text(fenster_text(s), size=12))
                    for s in LIVE_FENSTER
                ],
                on_change=fenster_wechseln,
            ),
            ft.Container(expand=True),
            rechts_box,
        ],
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
                    rechts_px=lambda: st.rechts,
                ),
                etikett_box,
                ablese_box,
            ],
        ),
    )
    koerper = ft.Row(
        expand=True,
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            flaeche,
            seite_box,
            leiste(
                ablesen_knopf,
                werkzeug(
                    ft.Icons.ADD_COMMENT_OUTLINED,
                    "Notiz ohne Text hier — Text über „Notizen“",
                    lambda: marke(),
                ),
                notizen_knopf,
                werkzeug(ft.Icons.TUNE, "Fenster & Darstellung der Kurven", lambda: darstellung()),
            ),
        ],
    )
    spalte = ft.Column(spacing=0, expand=True, controls=[kopf, koerper])
    fuellen()
    lauf.beobachter = beobachten
    return ft.View(
        route="/live",
        padding=ft.Padding.only(left=4, right=4, top=0, bottom=0),
        controls=[sicher(spalte)],
    )


__all__ = ["live_vollbild_view"]
