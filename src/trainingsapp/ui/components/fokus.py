"""Der **Fokus** — die Trainingsansicht zur laufenden Uhr einer Übung (Ben, 7.11.2026,
`docs/plan_planblock.md` §B, `docs/plan_workout.md` §2 C2).

Eine Komponente für den Timer der Übung (`views/uebung_timer.py`) und das Workout
(`views/workout.py`): große Zeit (in der Überzeit „−0:23“), Stand, Balken der Abschnitte,
Takt-Animation mit Tempo-Regler, Bild der Bewegung (Bildfolge im Takt), HF-Kachel, die
**Kurven-Einblendung** (Live-Reihen der letzten `KURVEN_FENSTER_S` Sekunden — HF, RR, RMSSD,
SDNN, Atemfrequenz, RSA; nur Anzeige, `ui.state.FOKUS_KURVEN`), Zählstand des Sensors, Sätze.
Die Ebenen Takt · Bewegung · HF · Kurve stehen als Chips oben, gemerkt je Gerät.

**Einmal gebaut** (`bauen`), je Tick zieht `nachziehen` nur Werte nach (V1); die Kurven
werden höchstens einmal je Sekunde neu gezeichnet — `kurve()` baut je Aufruf ein Diagramm.
Die Reihen rechnet `hrv_core.trends.verlauf` aus dem Live-Fenster des Messlaufs; hier steht
keine Rechnung, nur die Auswahl und das Zeichnen.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core.trends import KENNZAHLEN, verlauf

from trainingsapp.core.hf_profil import bereich_von, bereiche_fuer
from trainingsapp.core.models import IMMER, Media
from trainingsapp.core.timer import Abschnitt, dauer_text
from trainingsapp.core.timer_eintrag import gelaufene_zeiten
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.bewegungsbild import Bewegungswahl, bewegung_im_fokus
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.takt_anzeige import ZeitMitTakt, takt_gross
from trainingsapp.ui.components.takt_blatt import TempoRegler
from trainingsapp.ui.components.videospieler import Videospieler
from trainingsapp.ui.farben import FARBEN
from trainingsapp.ui.state import (
    FOKUS_BEWEGUNG,
    FOKUS_EBENEN,
    FOKUS_HF,
    FOKUS_KURVE,
    FOKUS_KURVEN,
    FOKUS_TAKT,
    FOKUS_VIDEO,
    AppState,
)

#: Kennung einer Fokus-Ansicht (``ft.View.data``): Dort setzt die App keine Laufleiste ein —
#: der Fokus zeigt, was jetzt wichtig ist (Ben, 8.11.2026 spät: „Die übergeordneten Läufe
#: braucht es nicht, die kommen nach dem Fokus wieder rein“)
FOKUS_ANSICHT = "fokus"
#: So viele Controls vorn in `Fokus.bauen` gehören in den festen Kopf: die Zeile Takt · Zeit ·
#: Ebenen und der Balken — sie scrollen nicht mit (Ben: „beim Runterscrollen soll die Uhr oben
#: fixiert bleiben“). Direkt darunter setzt der Aufrufer seine `steuerzeile`, ebenfalls fest
OBEN = 2


def steuerzeile(*knoepfe: ft.Control | None) -> ft.Control:
    """Die Zeile mit den Knöpfen des Laufs — Pause · Fertig · Überspringen · Abbrechen … —
    **eine** Zeile direkt unter der Zeit; sie steht mit ihr fest oben (Ben, 10.11.2026: „Die
    Zeile mit den Steuerungsbuttons … kommt unter die Zeit und fixiert ebenfalls beim
    Scrollen“). ``None`` fällt weg."""
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[k for k in knoepfe if k is not None],
        data="steuerzeile",
    )


def abbrechen_knopf(on_click: Callable[..., Any], tooltip: str = "") -> ft.Control:
    """„Abbrechen“ als Symbol — klein, rot, am Ende der Steuerzeile."""
    return ft.IconButton(
        ft.Icons.CLOSE,
        icon_color=ft.Colors.ERROR,
        tooltip=tooltip or "Abbrechen — beenden ohne Eintrag",
        on_click=on_click,
        data="abbrechen",
    )


#: Die Kurven zeigen die letzten zwei Minuten
KURVEN_FENSTER_S = 120.0
#: Raster der gerechneten Reihen (s) — fein genug für zwei Minuten, billig je Sekunde
KURVEN_SCHRITT_S = 2.0
#: Nicht öfter als einmal je Sekunde zeichnen (der Timer-Ticker läuft alle 0,2 s)
KURVEN_TAKT_S = 1.0
#: Höhe eines Kurvenstreifens
KURVEN_HOEHE = 72


def balken(folge: list[tuple[Abschnitt, float]], hoehe: int = 10) -> ft.Control:
    """Farbige Leiste: je Abschnitt ein Stück nach seiner Dauer — gefüllt, wenn er zählt.

    ``folge``: Abschnitt und wie viel von ihm vorbei ist (0…1); -1 = noch nicht dran.
    """
    stuecke: list[ft.Control] = []
    for a, anteil in folge:
        farbe = ft.Colors.PRIMARY if a.zaehlt else ft.Colors.OUTLINE
        rahmen = ft.Border.all(1.5, farbe)
        if anteil < 0:  # noch nicht dran: nur der Umriss
            stuecke.append(
                ft.Container(expand=a.dauer_s, height=hoehe, border=rahmen, border_radius=3)
            )
        elif anteil >= 1:
            voll = farbe if a.zaehlt else ft.Colors.with_opacity(0.35, farbe)
            stuecke.append(
                ft.Container(expand=a.dauer_s, height=hoehe, bgcolor=voll, border_radius=3)
            )
        else:  # läuft: zum Teil gefüllt
            gelaufen = max(round(anteil * 1000), 1)
            stuecke.append(
                ft.Container(
                    expand=a.dauer_s,
                    height=hoehe,
                    border=rahmen,
                    border_radius=3,
                    content=ft.Row(
                        spacing=0,
                        controls=[
                            ft.Container(expand=gelaufen, height=hoehe, bgcolor=farbe),
                            ft.Container(expand=max(1000 - gelaufen, 1), height=hoehe),
                        ],
                    ),
                )
            )
    return ft.Row(spacing=3, controls=stuecke)


def kurven_reihen(
    live: Any, jetzt_s: float, schluessel: list[str], speicher: dict[Any, Any]
) -> dict[str, list[tuple[float, float]]]:
    """Die Punkte je gewählter Reihe für die letzten `KURVEN_FENSTER_S` Sekunden — aus dem
    Live-Fenster (`hrv_core.live.LiveFenster`): ``hf`` und ``rr`` roh, alles andere über
    `hrv_core.trends.verlauf`. Leere Liste, wenn nichts da ist; nie eine Ausnahme nach außen
    (der Fokus darf die Uhr nicht aufhalten)."""
    von = jetzt_s - KURVEN_FENSTER_S
    out: dict[str, list[tuple[float, float]]] = {}
    try:
        t, rr, naht = live.verlaufsreihe()
    except Exception:
        return {k: [] for k in schluessel}
    for k in schluessel:
        try:
            if k == "hf":
                punkte = [(float(a), float(b)) for a, b in live.hf_reihe() if a >= von]
            elif k == "rr":
                punkte = [
                    (float(a), float(b))
                    for a, b in zip(t, rr, strict=False)
                    if a >= von and not math.isnan(float(b))
                ]
            else:
                kz = KENNZAHLEN[k]
                punkte = [
                    (float(a), float(b))
                    for a, b in verlauf(
                        t,
                        rr,
                        naht,
                        k,
                        kz.fenster_s,
                        von=von,
                        bis=jetzt_s,
                        schritt_s=KURVEN_SCHRITT_S,
                        zwischenspeicher=speicher,
                    )
                    if not math.isnan(float(b))
                ]
        except Exception:
            punkte = []
        out[k] = punkte
    return out


def kurven_einheit(k: str) -> tuple[str, str, float]:
    """(Titel, Einheit, kleinste Spanne) einer Reihe der Einblendung."""
    if k == "hf":
        return "HF", "bpm", 20.0
    if k == "rr":
        return "RR", "ms", 100.0
    kz = KENNZAHLEN[k]
    return FOKUS_KURVEN.get(k, kz.titel), kz.einheit, kz.spanne_min


class Fokus:
    """Die Trainingsansicht einer laufenden Uhr — Controls einmal, Werte je Tick."""

    def __init__(
        self,
        page: Any,
        state: AppState,
        *,
        uebung: Any,
        item: Any,
        key: str,
        neu_zeichnen: Callable[[], None],
        material_item: Any = None,
    ) -> None:
        """``neu_zeichnen``: der Aufrufer frischt seine Spalte auf (ein Chip hat eine Ebene
        umgeschaltet); ``key``: Schlüssel der Uhr für den Tempo-Regler (`uhr.schluessel`).

        ``material_item``: woher das **Material** kommt, wenn nicht von ``item`` — der Lauf
        einer Übung im Kurs bringt eigene Medien mit (`core.kursbloecke.Block.medien`), ohne
        eine Planübung zu sein: Zählen, Bewegung und Tempo gelten weiter der Übung (``item``),
        Begleitung, „bei …“ und der Material-Knopf nehmen diese Stücke dazu."""
        self.page, self.state, self.uebung, self.item, self.key = page, state, uebung, item, key
        self.mat_item = material_item if material_item is not None else item
        self.neu_zeichnen = neu_zeichnen
        # Zeit und Takt in einer Zeile (Ben, 8.11.2026 spät) — die Zeit etwas kleiner als auf
        # der Timer-Seite, der Takt etwas kleiner als die Zeit, dieselbe Form wie dort und in der
        # laufenden Uhr der Übung (Ben, 9.11.2026: `ZeitMitTakt`); antippen → groß
        self.uhr = ZeitMitTakt(64, on_takt=self._takt_gross)
        self.zeit_text = self.uhr.zeit_text
        self.stand_text = ft.Text(size=15, opacity=0.8, text_align=ft.TextAlign.CENTER)
        self.balken_platz = ft.Container()
        self.takt_platz = self.uhr.takt_platz
        #: Der Lauf der letzten Abfrage — für den großen Takt
        self._lauf: Any = None
        #: Die Ebenen als Menü neben der Zeit (statt vier Chips) — je Eintrag ein Haken
        self._ebenen_eintraege: dict[str, ft.PopupMenuItem] = {}
        self.tempo_platz = ft.Container()
        self.saetze_spalte = ft.Column(spacing=0)
        #: Der Überblick über die Sätze als Karte — `bauen` legt sie an, gibt sie aber **nicht**
        #: in seiner Liste zurück: Der Aufrufer setzt sie hinter „Eintragen“ (Ben, 15.11.2026:
        #: „Der Überblick über die Sätze muss unter die Eintragefenster“ — bei sechs Sätzen schob
        #: sie die Karte aus dem Blick)
        self.saetze_karte: ft.Control = ft.Container(content=self.saetze_spalte)
        #: Anhalten/Fortsetzen — nur das Symbol (Ben, 10.11.2026); der Aufrufer setzt ``on_click``
        self.halt_knopf = ft.FilledTonalIconButton(icon=ft.Icons.PAUSE, tooltip="Pause")
        self.ebenen = state.fokus_ebenen()
        self.kurven = state.fokus_kurven()
        self.bild_platz = ft.Container()
        self.bildfolge: Bewegungswahl | None = None
        #: Das Begleitvideo (Ben, 18.11.2026: „sollte automatisch abgespielt sein, nicht in
        #: voller Bildbreite, aber groß genug … mit Steuerungsbuttons“) — dieselbe Fläche wie die
        #: Bewegung, es geht ihr vor („entweder oder“); läuft und steht mit der Uhr
        self.video_platz = ft.Container()
        self.spieler: Videospieler | None = None
        #: Lief die Uhr beim letzten Nachziehen — das Video folgt nur einem Wechsel
        self._uhr_lief: bool | None = None
        #: Die Person hat das Video mit ⏸ angehalten — die Uhr startet es dann nicht wieder
        self._video_von_hand_aus = False
        #: Die Haken im Ebenen-Menü
        self._haken: dict[str, ft.Icon] = {}
        #: Stücke „bei …“ (Ben, 18.11.2026: „zu bestimmten Ereignissen … wenn Wdh oder Zeit
        #: soundso → Video“): Tritt ihr Ereignis ein, steht ein Hinweis unter der Uhr — die Uhr
        #: läuft weiter, ein Tipp öffnet das Blatt (`_ereignisse_nachziehen`)
        self.ereignis_platz = ft.Column(spacing=6, tight=True, visible=False)
        self._material: Any = None
        self._bei_schon: set[str] = set()
        self.hf_wert = ft.Text("—", size=28, weight=ft.FontWeight.W_600)
        self.hf_unten = ft.Text("kein Gurt", size=11, opacity=0.65)
        self.hf_karte = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Text("HF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    ft.Row(
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[self.hf_wert, ft.Text("bpm", size=12, opacity=0.65)],
                    ),
                    self.hf_unten,
                ],
            ),
        )
        #: Die Kurven-Einblendung: Auswahl der Reihen und je Reihe ein Streifen
        self.kurven_platz = ft.Column(spacing=6, tight=True)
        self.kurven_karte = ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=6, tight=True, controls=[self._kurven_chips(), self.kurven_platz]
            ),
        )
        self._kurven_zuletzt = 0.0
        self._kurven_speicher: dict[Any, Any] = {}
        self._saetze_schluessel: Any = None
        #: HF-Zonen (W4, nur Anzeige): Bereiche und Profil einmal beim Bauen, Zeit je Zone
        self._bereiche: list[Any] = []
        self._profil: Any = None
        self._einst: Any = None
        self._zone_sekunden: dict[str, float] = {}
        self._zone_zuletzt: float | None = None
        self._ton_zuletzt = 0.0

    def _takt_gross(self) -> None:
        if self._lauf is not None:
            takt_gross(self.page, self.state, self._lauf)

    # -- Ebenen ----------------------------------------------------------------------------

    def ebenen_anwenden(self) -> None:
        self.takt_platz.visible = FOKUS_TAKT in self.ebenen
        self.tempo_platz.visible = FOKUS_TAKT in self.ebenen
        for name, haken in self._haken.items():
            an = name in self.ebenen
            haken.icon = ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK
        # Video und Bewegung teilen sich die Fläche — das Video geht vor (Ben, 18.11.2026:
        # „eigentlich entweder oder?“); wer die Bewegung sehen will, wählt „Video“ ab
        self.video_platz.visible = (
            FOKUS_VIDEO in self.ebenen and self.video_platz.content is not None
        )
        self.bild_platz.visible = (
            FOKUS_BEWEGUNG in self.ebenen
            and self.bild_platz.content is not None
            and not (self.video_platz.visible and self.spieler is not None)
        )
        self.hf_karte.visible = FOKUS_HF in self.ebenen
        self.kurven_karte.visible = FOKUS_KURVE in self.ebenen

    def _ebene_umschalten(self, name: str) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            if name in self.ebenen:
                self.ebenen.discard(name)
            else:
                self.ebenen.add(name)
            self.state.fokus_ebenen_setzen(self.ebenen)
            if name == FOKUS_VIDEO and self.spieler is not None:
                # Unsichtbar fällt der Spieler aus dem Bild (Flutter baut ihn ab) — sichtbar
                # beginnt er neu: mit der Uhr, außer die Person hatte ihn angehalten
                self.spieler.neu_beginnen(
                    FOKUS_VIDEO in self.ebenen
                    and bool(self._uhr_lief)
                    and not self._video_von_hand_aus
                )
            self.ebenen_anwenden()
            if name == FOKUS_KURVE:
                self._kurven_zuletzt = 0.0
            self.neu_zeichnen()

        return handler

    def _ebene_eintrag(self, name: str, text: str) -> ft.PopupMenuItem:
        """Ein Eintrag des Ebenen-Menüs, der das Menü **offen lässt** (Ben, 18.11.2026: „Das
        Menü … nicht schließen nach dem ersten Klick“). Flutter schließt ein Menü, wenn der
        Eintrag selbst den Tipp bekommt (`PopupMenuItem.handleTap`; Flet setzt nur dessen
        ``onTap``, `flet/lib/src/utils/popup_menu.dart`). Hier fängt ein Container mit eigenem
        Tipp ihn vorher ab — er füllt den Eintrag, der Eintrag hat keinen Rand. Der Haken ist ein
        Symbol, das der Tipp umstellt: Das offene Menü zeichnet seine Controls nach, den
        ``checked`` eines Eintrags dagegen nur beim Öffnen."""
        haken = ft.Icon(
            ft.Icons.CHECK_BOX if name in self.ebenen else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            color=ft.Colors.PRIMARY,
            size=22,
        )
        self._haken[name] = haken
        return ft.PopupMenuItem(
            padding=ft.Padding.all(0),
            content=ft.Container(
                width=200,
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                on_click=self._ebene_umschalten(name),
                content=ft.Row(spacing=12, controls=[haken, ft.Text(text)]),
                data=("ebene", name),
            ),
        )

    def ebenen_knopf(self) -> ft.Control:
        """Was der Fokus zeigt — Takt · Bewegung · Video · HF · Kurve — als ein Knopf neben der
        Zeit (Ben, 8.11.2026 spät: „Die Buttons Takt-Bewegung … in einen Button auslagern, der in
        die gleiche Zeile wie die Zeit kommt“); gemerkt je Gerät. „Video“ nur, wenn die Übung ein
        Begleitvideo hat. Das Menü bleibt beim Umschalten offen (`_ebene_eintrag`)."""
        self._haken = {}
        self._ebenen_eintraege = {
            name: self._ebene_eintrag(name, text)
            for name, text in FOKUS_EBENEN.items()
            if name != FOKUS_VIDEO or self.video_platz.content is not None
        }
        return ft.PopupMenuButton(
            icon=ft.Icons.LAYERS_OUTLINED,
            tooltip="Was der Fokus zeigt: "
            + " · ".join(FOKUS_EBENEN[n] for n in self._ebenen_eintraege),
            items=list(self._ebenen_eintraege.values()),
        )

    # -- Begleitvideo ------------------------------------------------------------------------

    def _video_einsetzen(self, pfade: list[str], spielen: bool) -> None:
        """Den Spieler in die Fläche — 320 × 180, nicht über die ganze Breite (Ben)."""
        try:
            self.spieler = Videospieler(
                pfade,
                autoplay=spielen,
                hoehe=180,
                breite=320,
                schleife=self._video_schleife(pfade),
                beim_spielen=self._video_getippt,
                beim_schliessen=self._video_weg,
                bei_schleife=self._video_schleife_gestellt,
                state=self.state,
            )
        except ImportError:  # ein Build ohne flet-video: das Video bleibt im Blatt
            self.spieler = None
            return
        self.video_platz.content = self.spieler.control

    def _video_getippt(self, spielt: bool) -> None:
        self._video_von_hand_aus = not spielt

    def _video_schleife(self, pfade: list[str]) -> bool:
        """Endlosschleife (Ben, 20.11.2026: „wenn die Begleitung kein Ganzvideo ist, sondern nur
        ein Ausschnitt, der sich wiederholt“): Was die Person an dieser Übung gestellt hat,
        gilt; sonst läuft ein kurzes Video (`core.videoinfo.ist_ausschnitt`) von selbst als
        Schleife, ein langes einmal durch."""
        from pathlib import Path

        from trainingsapp.core import videoinfo

        wahl = None
        with contextlib.suppress(Exception):
            wahl = self.state.video_schleife(self.uebung.id)
        if wahl is not None:
            return bool(wahl)
        dauer = 0.0
        for p in pfade:
            info = videoinfo.lesen(Path(p))
            if info is None or not info.dauer_s:
                return False
            dauer += info.dauer_s
        return videoinfo.ist_ausschnitt(dauer)

    def _video_schleife_gestellt(self, an: bool) -> None:
        with contextlib.suppress(Exception):
            self.state.video_schleife_setzen(self.uebung.id, an)

    def _video_weg(self) -> None:
        """Das ✕ im Bild (Ben, 20.11.2026: „direkt weggeklickt … zusätzlich zur Checkbox im
        Menü“) — dasselbe wie der Haken „Video“ im Ebenen-Menü, dort kommt es auch wieder."""
        if FOKUS_VIDEO in self.ebenen:
            self._ebene_umschalten(FOKUS_VIDEO)(None)

    def _video_laden_zeile(self, offen: list[Media]) -> ft.Control:
        """Ein Begleitvideo hinter einem Link, das noch nicht auf dem Gerät liegt: ein Knopf
        lädt es (WLAN, Rückfrage je Server wie überall, `components/linkvideo.py`), danach
        steht der Spieler an seiner Stelle."""
        from trainingsapp.core.linkvideos import server
        from trainingsapp.ui.components.linkvideo import link_laden

        medium = offen[0]

        async def danach(_name: str) -> None:
            from trainingsapp.ui.components.material import begleitvideos

            pfade, _ = begleitvideos(self.state, self.uebung, self.mat_item)
            if not pfade:
                return
            self._video_einsetzen(pfade, bool(self._uhr_lief))
            self.ebenen_anwenden()
            self.neu_zeichnen()

        async def laden(_e: Any = None) -> None:
            await link_laden(self.page, self.state, medium, danach)

        return ft.Container(
            width=320,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE),
                    ft.Text(
                        f"{medium.title or 'Begleitvideo'} · von {server(medium.uri)}",
                        size=13,
                        expand=True,
                    ),
                    ft.TextButton("Laden", icon=ft.Icons.DOWNLOAD, on_click=laden),
                ],
            ),
            data="video_laden",
        )

    def _ereignisse_nachziehen(
        self, e: Einheitslauf, lauf: Any, stand: Any, zaehlend: list[int]
    ) -> None:
        """Stücke „bei …“: Ist ihr Ereignis eingetreten (`core.material.Material.faellig` —
        aus Uhr, Zählung, nie aus Messwerten), kommt je Stück ein Hinweis unter die Uhr; je Lauf
        einmal, und nur, solange es nicht abgehakt ist oder „jedes Mal“ kommen soll."""
        from trainingsapp.core.material import Lage, material_von
        from trainingsapp.ui.components.material import gesehen

        if self._material is None:
            self._material = material_von(self.uebung, self.mat_item)
        m = self._material
        if not m.bei or not lauf.begonnen:
            return
        gezaehlt = e.teil("zaehlen")
        lage = Lage(
            abschnitt=str(stand.name or ""),
            satz=zaehlend.index(stand.nummer) + 1 if stand.nummer in zaehlend else 0,
            gelaufen_s=float(lauf.vergangen_s()),
            wdh=int(gezaehlt.summe) if isinstance(gezaehlt, ZaehlBaustein) else None,
        )
        neu = m.faellig(lage, self._bei_schon)
        if not neu:
            return
        self._bei_schon.update(x.uri for x in neu)
        abgehakt = gesehen(self.state)
        for x in neu:
            if x.oft == IMMER or x.uri not in abgehakt:
                self.ereignis_platz.controls.append(self._ereignis_hinweis(m, x))
        self.ereignis_platz.visible = bool(self.ereignis_platz.controls)

    def _ereignis_hinweis(self, m: Any, x: Media) -> ft.Control:
        from trainingsapp.ui.components.material import faellig_blatt

        def weg(_e: Any = None) -> None:
            self.ereignis_platz.controls.remove(zeile)
            self.ereignis_platz.visible = bool(self.ereignis_platz.controls)
            self.neu_zeichnen()

        def ansehen(_e: Any = None) -> None:
            weg()
            # das Stück selbst, nicht die Liste (Ben, 19.11.2026)
            self.page.show_dialog(
                faellig_blatt(
                    self.page, self.state, self.uebung, self.mat_item, (x,), titel="Jetzt"
                )
            )

        zeile = ft.Container(
            padding=ft.Padding.only(left=12, right=4, top=2, bottom=2),
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.MENU_BOOK, size=20),
                    ft.Text(x.title or "Medium", size=13, expand=True),
                    ft.TextButton("Ansehen", on_click=ansehen, data=("ereignis_ansehen", x.uri)),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Später", on_click=weg),
                ],
            ),
            data=("ereignis", x.uri),
        )
        return zeile

    def _video_nachziehen(self, laeuft: bool) -> None:
        """Das Video läuft mit der Uhr (Ben: „automatisch abgespielt“) und steht mit ihr — nur
        bei einem Wechsel, damit ein ⏸ von Hand nicht je Tick überstimmt wird."""
        if laeuft == self._uhr_lief:
            return
        self._uhr_lief = laeuft
        spieler = self.spieler
        if spieler is None or not self.video_platz.visible:
            return
        if laeuft and self._video_von_hand_aus:
            return
        with contextlib.suppress(Exception):  # ohne Ereignisschleife (Test): nichts
            self.page.run_task(spieler.spielen if laeuft else spieler.anhalten)

    def _kurve_umschalten(self, k: str) -> Callable[[ft.Event[ft.Chip]], None]:
        def handler(_e: ft.Event[ft.Chip]) -> None:
            gewaehlt = set(self.kurven)
            if k in gewaehlt:
                gewaehlt.discard(k)
            else:
                gewaehlt.add(k)
            self.kurven = [s for s in FOKUS_KURVEN if s in gewaehlt]
            self.state.fokus_kurven_setzen(gewaehlt)
            self._kurven_zuletzt = 0.0
            self.neu_zeichnen()

        return handler

    def _kurven_chips(self) -> ft.Control:
        return ft.Row(
            spacing=4,
            wrap=True,
            controls=[
                ft.Chip(
                    label=ft.Text(text, size=11),
                    selected=k in self.kurven,
                    show_checkmark=False,
                    tooltip=f"{text} der letzten 2 Minuten — nur Anzeige",
                    on_select=self._kurve_umschalten(k),
                )
                for k, text in FOKUS_KURVEN.items()
            ],
        )

    # -- Bauen -----------------------------------------------------------------------------

    def bauen(self, e: Einheitslauf, lauf: Any) -> list[ft.Control]:
        """Die Controls des Fokus (ohne Knöpfe — die gehören dem Aufrufer): Chips, Zeit, Stand,
        Balken, die Reihe Takt · Bewegung · HF, Kurven, Zählstand. Die Sätze stehen danach in
        `saetze_karte` — der Aufrufer setzt sie hinter seine Karte „Eintragen“."""
        from trainingsapp.ui.components import zaehlen
        from trainingsapp.ui.components.karte import karte
        from trainingsapp.ui.components.material import begleitvideos, material_knopf

        self.tempo_platz.content = TempoRegler(self.state, self.key, lauf).control
        self._zonen_laden()
        bewegung = bewegung_im_fokus(self.state, self.uebung, self.item)
        self.bild_platz.content, self.bildfolge = bewegung if bewegung is not None else (None, None)
        if self.spieler is None and self.video_platz.content is None:
            # Das Begleitvideo startet mit der Uhr (Ben, 18.11.2026) — nicht, wenn sie steht
            pfade, offen = begleitvideos(self.state, self.uebung, self.mat_item)
            self._uhr_lief = _uhr_laeuft(lauf)
            if pfade:
                self._video_einsetzen(pfade, self._uhr_lief and FOKUS_VIDEO in self.ebenen)
            elif offen:
                self.video_platz.content = self._video_laden_zeile(offen)
        self.ebenen_anwenden()
        self.nachziehen(e, lauf)
        zaehl = zaehlen.neben_der_uhr(
            self.page,
            self.state,
            e,
            self.uebung.id,
            self.item.id if self.item is not None else None,
            name="timer",
        )
        knopf = self.ebenen_knopf()
        # Material (U2, F6): nur, wenn es welches gibt — ansehen hält die Uhr an
        # beim Üben nur, was schon dran war (Ben, 19.11.2026) — nichts von „nachher“ und „bei …“
        material = material_knopf(
            self.page,
            self.state,
            self.uebung,
            self.mat_item,
            text=False,
            dran=lambda: set(self._bei_schon),
        )
        self.ebenen_anwenden()
        self.saetze_karte = karte(self.saetze_spalte, abstand=0, padding=10)
        #: Material-Knopf und Ebenen-Menü — für Aufrufer, die die Zeile der Uhr selbst zeichnen
        #: (der Lauf im Kurs, `views/kurs_testlauf.py`)
        self.material_control: ft.Control | None = material
        self.ebenen_control: ft.Control = knopf
        return [
            # Takt · Zeit (mit Stand) · Material · Ebenen — eine Zeile (8.11.2026 spät)
            self.uhr.zeile(
                unter=[self.stand_text],
                rechts=[*([material] if material is not None else []), knopf],
            ),
            self.balken_platz,
            self.ereignis_platz,
            self.tempo_platz,
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
                spacing=12,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.video_platz, self.bild_platz, self.hf_karte],
            ),
            self.kurven_karte,
            *([karte(*zaehl, abstand=4, padding=10)] if zaehl else []),
        ]

    # -- Nachziehen ------------------------------------------------------------------------

    def nachziehen(self, e: Einheitslauf, lauf: Any) -> None:
        """Zeit, Stand, Balken, Takt, Bildfolge, HF, Kurven und Sätze — jede Abfrage."""
        self._lauf = lauf
        stand = lauf.stand()
        folge = lauf.profil.folge()
        zaehlend = [n for n, (*_, a) in enumerate(folge) if a.zaehlt]
        ueber = lauf.ueber_s() if hasattr(lauf, "ueber_s") else 0.0
        lage = lauf.takt_lage()
        # Weicher Übergang im Workout: nach Ablauf zählt die Zeit ins Minus weiter; sonst
        # vorwärts bei der Stoppuhr (18.10.2026)
        self.uhr.nachziehen(
            f"−{dauer_text(int(ueber))}" if ueber > 0 else lauf.anzeige(),
            lauf.takt_effektiv() if lage else None,
            lage,
        )
        self.zeit_text.color = ft.Colors.TERTIARY if ueber > 0 else None
        teile = ["über der Zeit"] if ueber > 0 else [stand.name or "Abschnitt"]
        if stand.nummer in zaehlend:
            teile.append(f"Satz {zaehlend.index(stand.nummer) + 1} von {len(zaehlend)}")
        teile.append("zählt" if stand.zaehlt else "zählt nicht")
        if lauf.begonnen and not stand.laeuft and not stand.fertig:
            teile.append("angehalten")
        self.stand_text.value = " · ".join(teile)
        anteile: list[tuple[Abschnitt, float]] = []
        for n, (*_, a) in enumerate(folge):
            if n < stand.nummer:
                anteile.append((a, 1.0))
            elif n == stand.nummer and not stand.fertig:
                anteile.append((a, stand.anteil))
            else:
                anteile.append((a, -1.0 if not stand.fertig else 1.0))
        self.balken_platz.content = None if lauf.vorwaerts else balken(anteile, hoehe=12)
        if isinstance(self.tempo_platz.content, ft.Row):
            self.tempo_platz.content.visible = lage is not None
        if self.bildfolge is not None:
            self.bildfolge.nachziehen(
                lauf.takt_effektiv() if lage else None, lage, stand.abschnitt_s - stand.rest_s
            )
        self._hf_nachziehen()
        self._kurven_nachziehen()
        self._saetze_nachziehen(e, lauf, stand, folge, zaehlend)
        self.halt_knopf.icon = ft.Icons.PLAY_ARROW if not stand.laeuft else ft.Icons.PAUSE
        self.halt_knopf.tooltip = "Weiter" if not stand.laeuft else "Pause"
        self.halt_knopf.disabled = (stand.fertig and ueber <= 0) or lauf.abgebrochen
        self._video_nachziehen(_uhr_laeuft(lauf))
        self._ereignisse_nachziehen(e, lauf, stand, zaehlend)
        # „Ohne Uhr — nur Fokus“ (P146): keine Zeit, keine Pause — Kurven und Eintragen bleiben
        ohne = bool(getattr(lauf.profil, "ohne_uhr", False))
        self.zeit_text.visible = not ohne
        self.halt_knopf.visible = not ohne
        if ohne:
            self.stand_text.value = "Ohne Uhr — keine Zeit im Tagebuch"

    def _live(self) -> tuple[Any, float] | None:
        lauf_hrv: Any = getattr(self.state, "messlauf", None)
        if lauf_hrv is None:
            return None
        live = getattr(lauf_hrv, "live", None)
        if live is None:
            return None
        try:
            return live, float(lauf_hrv.jetzt_s())
        except Exception:
            return None

    def _zonen_laden(self) -> None:
        """Profil und Bereiche einmal (die Datenbank fragt man nicht je Tick)."""
        try:
            self._profil = self.state.hf_profil()
            self._einst = self.state.hf_einstellungen()
            self._bereiche = list(bereiche_fuer(self._profil, self._einst))
        except Exception:
            self._profil, self._einst, self._bereiche = None, None, []

    def _hf_nachziehen(self) -> None:
        paar = self._live()
        kennzahlen = None
        if paar is not None:
            with contextlib.suppress(Exception):
                kennzahlen = paar[0].kennzahlen()
        hf = getattr(kennzahlen, "hf_bpm", None) if kennzahlen is not None else None
        self.hf_wert.value = str(hf) if hf is not None else "—"
        if hf is None:
            self.hf_unten.value = "verbindet …" if paar is not None else "kein Gurt"
            self._zone_zuletzt = None
            return
        self.hf_unten.value = self._zonen_text(float(hf))
        self._ton_pruefen(float(hf))

    def _zonen_text(self, hf: float) -> str:
        """„Zone 3 · 72 % · 1:40“ — die Zone (Einstellungen → Herzfrequenz), der Anteil der
        Herzfrequenzreserve und die Zeit in dieser Zone seit dem Aufbau. Nur Anzeige (W4)."""
        jetzt = time.monotonic()
        bereich = bereich_von(hf, self._bereiche) if self._bereiche else None
        if bereich is None:
            self._zone_zuletzt = jetzt
            return "Gurt"
        if self._zone_zuletzt is not None:
            dt = min(max(jetzt - self._zone_zuletzt, 0.0), 5.0)
            self._zone_sekunden[bereich.name] = self._zone_sekunden.get(bereich.name, 0.0) + dt
        self._zone_zuletzt = jetzt
        teile = [bereich.name]
        prozent = self._profil.prozent(hf) if self._profil is not None else None
        if prozent is not None:
            teile.append(f"{prozent:.0f} %")
        teile.append(dauer_text(int(self._zone_sekunden.get(bereich.name, 0.0))))
        return " · ".join(teile)

    def _ton_pruefen(self, hf: float) -> None:
        """Zielbereich-Ton (Entscheidung C): hoch über, tief unter dem selbst gesetzten
        Bereich, die Tonfolge wie eingestellt (nach Abstand oder fest) — dieselbe Regel und
        dieselbe Uhr wie in der Messansicht (`core.hf_ziel.Zielton`), nur Information."""
        e = self._einst
        if e is None or not getattr(e, "alarm_an", False):
            return
        from trainingsapp.core.hf_ziel import Zielton, messung_kennung

        zielton = getattr(self.state, "hf_zielton", None)
        if zielton is None:
            zielton = Zielton()
            with contextlib.suppress(Exception):
                self.state.hf_zielton = zielton
        stumm = getattr(self.state, "hf_stumm", None)
        jetzt = time.monotonic()
        # Stumm gilt je Messung (wie `ui.hf_live.HfLive.stumm`): „stumm bis Messende“ aus
        # einer früheren Messung schwiege hier sonst für immer (H101)
        lauf = getattr(self.state, "messlauf", None)
        kennung = messung_kennung(lauf)
        still = stumm is not None and hasattr(stumm, "gilt") and stumm.gilt(jetzt, kennung)
        klang = zielton.faellig(hf, e, jetzt, stumm=still)
        if klang is None:
            return
        if hasattr(self.page, "run_task"):
            from trainingsapp.ui.timer_takt import ton_spielen

            with contextlib.suppress(Exception):
                self.page.run_task(ton_spielen, self.state, klang)

    def _kurven_nachziehen(self) -> None:
        if FOKUS_KURVE not in self.ebenen:
            return
        jetzt = time.monotonic()
        if jetzt - self._kurven_zuletzt < KURVEN_TAKT_S:
            return
        self._kurven_zuletzt = jetzt
        paar = self._live()
        if paar is None:
            self.kurven_platz.controls = [hinweis("Kein Gurt verbunden — keine Kurven.")]
        elif not self.kurven:
            self.kurven_platz.controls = [hinweis("Keine Reihe gewählt.")]
        else:
            live, jetzt_s = paar
            reihen = kurven_reihen(live, jetzt_s, self.kurven, self._kurven_speicher)
            self.kurven_platz.controls = [
                self._streifen(k, punkte, jetzt_s) for k, punkte in reihen.items()
            ]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.kurven_platz.update()

    def _streifen(self, k: str, punkte: list[tuple[float, float]], jetzt_s: float) -> ft.Control:
        titel, einheit, spanne = kurven_einheit(k)
        letzter = f"{punkte[-1][1]:.0f} {einheit}" if punkte else "—"
        farbe = FARBEN.get(
            k if k not in ("hf", "rr") else ("hf_geraet" if k == "hf" else "mean_rr")
        )
        kopf = ft.Row(
            spacing=6,
            controls=[
                ft.Text(titel, size=11, weight=ft.FontWeight.BOLD, opacity=0.7, expand=True),
                ft.Text(letzter, size=11, weight=ft.FontWeight.W_600),
            ],
        )
        if not punkte:
            return ft.Column(spacing=2, tight=True, controls=[kopf, hinweis("noch keine Werte")])
        diagramm = kurve(
            [Reihe(punkte, farbe=farbe or ft.Colors.PRIMARY, breite=1.8)],
            einheit=einheit,
            hoehe=KURVEN_HOEHE,
            x_von=jetzt_s - KURVEN_FENSTER_S,
            x_bis=jetzt_s,
            y_spanne_min=spanne,
        )
        return ft.Column(spacing=2, tight=True, controls=[kopf, diagramm])

    def _saetze_nachziehen(
        self, e: Einheitslauf, lauf: Any, stand: Any, folge: Any, zaehlend: list[int]
    ) -> None:
        """Sätze: was zählt, mit der gelaufenen Zeit aus der Zeitleiste — und, zählt der Sensor
        mit, den Wiederholungen je Satz (4.11.2026)."""
        fertig = {(z.name, z.runde): z for z in gelaufene_zeiten(_seit_dem_schritt(e.ereignisse))}
        gezaehlt = e.teil("zaehlen")
        zaehl = gezaehlt if isinstance(gezaehlt, ZaehlBaustein) and gezaehlt.wdh else None
        zeilen: list[ft.Control] = []
        for k, n in enumerate(zaehlend):
            _, runde, _, a = folge[n]
            wdh: int | None = None
            if n < stand.nummer or stand.fertig:
                g = fertig.get((a.name, runde))
                wert = dauer_text(g.sekunden if g is not None else 0)
                if g is not None:
                    wdh = zaehl_stand.wdh_im_abschnitt(zaehl, g.von_s, g.bis_s)
                text, fett = f"Satz {k + 1}", False
            elif n == stand.nummer:
                wert = dauer_text(stand.abschnitt_s - stand.rest_s)
                satz = zaehl.satz if zaehl is not None else None
                if satz is not None and satz.bis_s is None:
                    wdh = satz.wert  # der laufende Satz des Zählens
                text, fett = f"Satz {k + 1} · läuft", True
            else:
                wert, text, fett = "–", f"Satz {k + 1}", False
            if wdh is not None:
                wert = f"{wert} · {wdh} Wdh."
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=4, vertical=8),
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                text,
                                expand=True,
                                weight=ft.FontWeight.W_700 if fett else None,
                                color=ft.Colors.PRIMARY if fett else None,
                            ),
                            ft.Text(wert, weight=ft.FontWeight.W_600),
                        ]
                    ),
                )
            )
        self.saetze_spalte.controls = zeilen or [
            hinweis("Kein Abschnitt zählt — eingetragen wird „gemacht“.")
        ]


def _uhr_laeuft(lauf: Any) -> bool:
    """Läuft die Uhr — auch in der Überzeit des Workouts (man trainiert nach): Dann läuft das
    Begleitvideo mit."""
    stand = lauf.stand()
    ueber = lauf.ueber_s() if hasattr(lauf, "ueber_s") else 0.0
    return (bool(stand.laeuft) and not stand.fertig) or ueber > 0


def _seit_dem_schritt(ereignisse: Sequence[Any]) -> Sequence[Any]:
    """Die Ereignisse ab dem laufenden Workout-Schritt (dem letzten ``plan/uebung_start``) —
    ohne Workout alle. `gelaufene_zeiten` hört beim ersten ``timer/ende`` auf; mit der ganzen
    Einheit zeigte die Satzliste ab dem zweiten Schritt die Zeiten des ersten (N61)."""
    for n in range(len(ereignisse) - 1, -1, -1):
        e = ereignisse[n]
        if getattr(e, "quelle", "") == "plan" and getattr(e, "art", "") == "uebung_start":
            return ereignisse[n:]
    return ereignisse


__all__ = [
    "KURVEN_FENSTER_S",
    "Fokus",
    "abbrechen_knopf",
    "balken",
    "kurven_einheit",
    "kurven_reihen",
    "steuerzeile",
]
