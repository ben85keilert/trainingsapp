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

from trainingsapp.core.hrv_ansicht import LINKS, RECHTS, ROH
from trainingsapp.core.hrv_einstellungen import HrvEinstellungen
from trainingsapp.core.laufend import minuten
from trainingsapp.core.zeitangabe import DAUER, UHR
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.ui.components.analyse import verlaufsdaten
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.live_abschnitte import LiveAbschnitte
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.verlauf import FARBEN, Zeitachse, darstellung_blatt
from trainingsapp.ui.components.vollbild import (
    ETIKETT_PX,
    LEISTE_PX,
    SEITE_PX,
    ablese_karte,
    ablese_seite,
    angebot,
    doppelkurve,
    lage_px,
    leiste,
    markieren,
    notiz_etikett,
    rechts_px,
    seiten_wahl,
    seitenkopf,
    werkzeug,
    werteachsen,
)
from trainingsapp.ui.components.zeitachse import achse, achsen_knopf
from trainingsapp.ui.components.zeitfenster import (
    BreitenSatz,
    Fenster,
    breiten_auswahl,
    breiten_nachziehen,
    breiten_wahl,
    wischbar,
)
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import (
    ablese_kopf_live,
    ablese_werte_live,
    ohne_rr,
    schlag_bei_live,
    schlag_weiter_live,
    strich_anfang_live,
    tachogramm_reihen,
)

#: Platz über der Kurve (Kopfzeile) und Ränder — für die Schätzung vor der Messung (px)
_KOPF_PX = 56


#: Eine Schreibweise für alle Zeiten (abgeschnitten, nicht gerundet — wie die Achse; N26)
_uhr = minuten
#: Die Seitenleisten
NOTIZEN = "notizen"
ABSCHNITTE = "abschnitte"


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
    #: Seitenleiste: „Notizen“, „Abschnitte“ oder zu (Ben, 28.10.2026)
    seite: str | None = None
    #: Womit die Kopfzeile gebaut ist — neu nur bei Änderung, sonst schlösse
    #: das Auffrischen eine offene Liste
    kopf: tuple[Any, ...] = ()
    #: Gibt es RR-Werte? Einmal gesehen, bleibt es so (`kennzahlen` ist nicht billig)
    mit_rr: bool = False
    #: Wählbare Kurven und Breite der rechten Achse — je Zeichnung einmal bestimmt
    angebot: list[str] = field(default_factory=list)
    rechts: float = 0.0
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]] = field(default_factory=dict)
    #: Woraus die Ablesewerte zuletzt gebaut wurden — gleich: nicht neu bauen (ein neuer
    #: Knopf verlöre einen Tipp, der gerade läuft)
    ablese_karte: tuple[Any, ...] | None = None


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
        zeit_modus=UHR if einst.achse_uhrzeit else DAUER,
        dialog=page.show_dialog,
        zeilen=lambda: state.hrv_einstellungen().notizen_zeilen,
    )
    # Abschnitte wie hochkant, als Seitenleiste (Ben, 28.10.2026; `components.live_abschnitte`)
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
        """Der Timer hat Abschnitte als Notizen in die Aufnahme geschrieben."""
        notizfeld.auffrischen()
        live_abschnitte.neu(erzwingen=True)
        aktualisieren(erzwingen=True)

    state.notiz_beobachter["live"] = timer_notizen

    def marke() -> None:
        if st.ablesen and st.strich is not None:
            x: float | None = st.strich
        else:
            x = None if fenster.ende_s is None else mitte()
        if not notizfeld.marke_setzen(x):
            page.show_dialog(ft.SnackBar(ft.Text("Hier lässt sich gerade keine Notiz setzen.")))

    def seite_umschalten(welche: str) -> None:
        """Notizen oder Abschnitte neben der Kurve — ein zweiter Tipp schließt."""
        st.seite = None if st.seite == welche else welche
        if st.seite == NOTIZEN:
            notizfeld.aufklappen()
        aktualisieren(erzwingen=True)

    def notiz_bearbeiten(i: int) -> None:
        st.etikett = None
        st.seite = NOTIZEN
        notizfeld.aufklappen()
        notizfeld.bearbeiten(i)

    def notiz_loeschen(i: int) -> None:
        """Löschen am Etikett — nach Rückfrage, mit „Rückgängig“ (Ben, 21.10.2026)."""
        st.etikett = None
        notizfeld.loeschen_fragen(i)
        aktualisieren(erzwingen=True)

    def etikett_schliessen() -> None:
        st.etikett = None
        aktualisieren(erzwingen=True)

    # -- Ablesen (wie hochkant: `messung.schlag_bei_live` …) ---------------------------------

    def ablesen_umschalten() -> None:
        st.ablesen = not st.ablesen
        if st.ablesen:
            st.etikett = None
            if fenster.ende_s is None:
                fenster.ende_s = lauf.jetzt_s()  # anhalten, damit man ablesen kann
            st.strich = strich_anfang_live(lauf, *fenster.bereich(lauf.jetzt_s(), anfang()))
        aktualisieren(erzwingen=True)

    def strich_setzen(x: float, *, zeichnen: bool = True) -> None:
        st.strich = schlag_bei_live(lauf, x)
        if zeichnen:
            aktualisieren(erzwingen=True)

    def strich_schritt(richtung: int) -> None:
        """Ein Schlag vor oder zurück; die Kurve rückt mit und bleibt angehalten."""
        jetzt = st.strich
        if jetzt is None:
            return
        neu = schlag_weiter_live(lauf, jetzt, richtung)
        st.strich = neu
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        if not x_von <= neu <= x_bis:
            zeigen(neu)
            fenster.ende_s = fenster.ende_s or lauf.jetzt_s()
        aktualisieren(erzwingen=True)

    def ablesen_zeichnen(x_von: float, x_bis: float) -> None:
        x = st.strich
        ablese_box.visible = st.ablesen and x is not None
        if not ablese_box.visible or x is None:
            ablese_box.content, st.ablese_karte = None, None
            return
        kopf_ = ablese_kopf_live(lauf, x)
        werte = ablese_werte_live(lauf, x, st.gesehen, korrigiert=einst.korrigiert, verity=verity)
        if (kopf_, werte) != st.ablese_karte:
            st.ablese_karte = (kopf_, werte)
            ablese_box.content = ablese_karte(
                kopf_,
                "",
                werte,
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
        x_text, x_null = achse(lauf.achse_utc, x_von, x_bis, uhrzeit=einst.achse_uhrzeit)
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
            x_text=x_text,
            x_null=x_null,
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
        etikett_box.content = notiz_etikett(
            zeit,
            text,
            FARBEN["notiz"],
            bearbeiten=lambda: notiz_bearbeiten(i),
            loeschen=lambda: notiz_loeschen(i),
            schliessen=etikett_schliessen,
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
        markieren(notizen_knopf, st.seite == NOTIZEN)
        markieren(abschnitte_knopf, st.seite == ABSCHNITTE)
        notiz_seite.visible = st.seite == NOTIZEN
        abschnitt_seite.visible = st.seite == ABSCHNITTE
        seite_box.visible = st.seite is not None
        live_abschnitte.neu()

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

    def breite_waehlen(breite_s: float) -> None:
        """Ein Breitenknopf oder die eingetippte Breite — dieselbe Einstellung wie hochkant;
        zurückgeblättert bleibt der linke Rand (Ben, 26.10.2026)."""
        fenster.breite_links(breite_s, lauf.jetzt_s(), anfang())
        aktuell = state.hrv_einstellungen()
        aktuell.fenster_s = round(breite_s)
        state.hrv_einstellungen_setzen(aktuell)
        breiten_knoepfe.selected = breiten_auswahl(breite_s, einst.breiten())
        aktualisieren(erzwingen=True)

    def achse_umschalten() -> None:
        """Zeitachse: Uhrzeit statt Dauer (Ben, 20.10.2026) — dieselbe Einstellung wie
        in der Karte und in der Aufzeichnung."""
        einst.achse_uhrzeit = not einst.achse_uhrzeit
        aktuell = state.hrv_einstellungen()
        aktuell.achse_uhrzeit = einst.achse_uhrzeit
        state.hrv_einstellungen_setzen(aktuell)
        aktualisieren(erzwingen=True)

    def darstellung() -> None:
        """Fenster & Darstellung der gezeigten Kurven — samt Zeitachse und Werteachsen."""
        a = state.ansicht()
        links, rechts = a.achsen(st.angebot)
        page.show_dialog(
            darstellung_blatt(
                page,
                state,
                lambda: aktualisieren(erzwingen=True),
                kurven=[k for k in (*a.links, *a.rechts) if k != ROH],
                achsen=werteachsen(a, [*links, *rechts], roh_titel),
                zeitachse=Zeitachse(
                    fenster.breite_s,
                    breite_waehlen,
                    max_s=lauf.live.max_s,
                    satz=breiten_satz().control,
                    uhrzeit=einst.achse_uhrzeit,
                    uhrzeit_setzen=achse_umschalten,
                ),
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
        ft.Icons.NOTES, "Notizen: Liste, Text, Zeit", lambda: seite_umschalten(NOTIZEN)
    )
    abschnitte_knopf = werkzeug(
        ft.Icons.VIEW_TIMELINE_OUTLINED,
        "Abschnitte: Start/Ende, Liste",
        lambda: seite_umschalten(ABSCHNITTE),
    )
    notiz_seite = ft.Column(
        spacing=4,
        tight=True,
        visible=False,
        controls=[seitenkopf("Notizen", lambda: seite_umschalten(NOTIZEN)), notizfeld.control],
    )
    abschnitt_seite = ft.Column(
        spacing=4,
        tight=True,
        visible=False,
        controls=[
            seitenkopf("Abschnitte", lambda: seite_umschalten(ABSCHNITTE)),
            live_abschnitte.control,
        ],
    )
    seite_box = ft.Container(
        visible=False,
        width=SEITE_PX,
        content=ft.Column(
            spacing=4, scroll=ft.ScrollMode.AUTO, controls=[notiz_seite, abschnitt_seite]
        ),
    )
    #: Dieselben Knöpfe wie hochkant und in der Aufzeichnung (Ben, 21.10.2026)
    breiten_knoepfe = breiten_wahl(
        fenster.breite_s, breite_waehlen, kompakt=True, breiten=einst.breiten()
    )

    def breiten_satz() -> BreitenSatz:
        def geaendert(neu: HrvEinstellungen) -> None:
            einst.breiten_satz, einst.breiten_eigen = neu.breiten_satz, list(neu.breiten_eigen)
            breiten_nachziehen(breiten_knoepfe, neu.breiten(), fenster.breite_s, kompakt=True)

        return BreitenSatz(state.hrv_einstellungen, state.hrv_einstellungen_setzen, geaendert)

    kopf = ft.Row(
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(ft.Icons.CLOSE, tooltip="Vollbild verlassen", on_click=schliessen),
            links_box,
            ft.Container(expand=True),
            lage_box,
            breiten_knoepfe,
            achsen_knopf(lambda: einst.achse_uhrzeit, achse_umschalten),
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
                abschnitte_knopf,
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
