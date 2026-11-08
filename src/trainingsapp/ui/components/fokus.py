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
from collections.abc import Callable
from typing import Any

import flet as ft
from hrv_core.trends import KENNZAHLEN, verlauf

from trainingsapp.core.hf_profil import bereich_von, bereiche_fuer
from trainingsapp.core.timer import Abschnitt, dauer_text
from trainingsapp.core.timer_eintrag import gelaufene_zeiten
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.bewegungsbild import Bildfolge, bewegung_im_fokus
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.takt_anzeige import TaktAnzeige
from trainingsapp.ui.components.takt_blatt import TempoRegler
from trainingsapp.ui.farben import FARBEN
from trainingsapp.ui.state import (
    FOKUS_BEWEGUNG,
    FOKUS_EBENEN,
    FOKUS_HF,
    FOKUS_KURVE,
    FOKUS_KURVEN,
    FOKUS_TAKT,
    AppState,
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
    ) -> None:
        """``neu_zeichnen``: der Aufrufer frischt seine Spalte auf (ein Chip hat eine Ebene
        umgeschaltet); ``key``: Schlüssel der Uhr für den Tempo-Regler (`uhr.schluessel`)."""
        self.page, self.state, self.uebung, self.item, self.key = page, state, uebung, item, key
        self.neu_zeichnen = neu_zeichnen
        self.zeit_text = ft.Text(
            size=72, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER
        )
        self.stand_text = ft.Text(size=15, opacity=0.8, text_align=ft.TextAlign.CENTER)
        self.balken_platz = ft.Container()
        self.takt_anzeige = TaktAnzeige(groesse=180)
        self.tempo_platz = ft.Container()
        self.saetze_spalte = ft.Column(spacing=0)
        #: Anhalten/Fortsetzen — der Aufrufer setzt ``on_click``
        self.halt_knopf = ft.FilledTonalButton(expand=True)
        self.ebenen = state.fokus_ebenen()
        self.kurven = state.fokus_kurven()
        self.bild_platz = ft.Container()
        self.bildfolge: Bildfolge | None = None
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
        self.takt_spalte = ft.Column(
            spacing=8, tight=True, controls=[self.takt_anzeige.control, self.tempo_platz]
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

    # -- Ebenen ----------------------------------------------------------------------------

    def ebenen_anwenden(self) -> None:
        self.takt_spalte.visible = FOKUS_TAKT in self.ebenen
        self.bild_platz.visible = (
            FOKUS_BEWEGUNG in self.ebenen and self.bild_platz.content is not None
        )
        self.hf_karte.visible = FOKUS_HF in self.ebenen
        self.kurven_karte.visible = FOKUS_KURVE in self.ebenen

    def _ebene_umschalten(self, name: str) -> Callable[[ft.Event[ft.Chip]], None]:
        def handler(_e: ft.Event[ft.Chip]) -> None:
            if name in self.ebenen:
                self.ebenen.discard(name)
            else:
                self.ebenen.add(name)
            self.state.fokus_ebenen_setzen(self.ebenen)
            self.ebenen_anwenden()
            if name == FOKUS_KURVE:
                self._kurven_zuletzt = 0.0
            self.neu_zeichnen()

        return handler

    def ebenen_chips(self) -> ft.Control:
        return ft.Row(
            spacing=6,
            wrap=True,
            controls=[
                ft.Chip(
                    label=ft.Text(text, size=12),
                    selected=name in self.ebenen,
                    show_checkmark=True,
                    tooltip=f"{text} im Fokus zeigen — gemerkt",
                    on_select=self._ebene_umschalten(name),
                )
                for name, text in FOKUS_EBENEN.items()
            ],
        )

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
        Balken, die Reihe Takt · Bewegung · HF, Kurven, Zählstand, Sätze."""
        from trainingsapp.ui.components import zaehlen
        from trainingsapp.ui.components.karte import karte

        self.tempo_platz.content = TempoRegler(self.state, self.key, lauf).control
        self._zonen_laden()
        bewegung = bewegung_im_fokus(self.state, self.uebung, self.item)
        self.bild_platz.content, self.bildfolge = bewegung if bewegung is not None else (None, None)
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
        return [
            self.ebenen_chips(),
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self.zeit_text]),
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self.stand_text]),
            self.balken_platz,
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
                spacing=12,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.takt_spalte, self.bild_platz, self.hf_karte],
            ),
            self.kurven_karte,
            *([karte(*zaehl, abstand=4, padding=10)] if zaehl else []),
            karte(self.saetze_spalte, abstand=0, padding=10),
        ]

    # -- Nachziehen ------------------------------------------------------------------------

    def nachziehen(self, e: Einheitslauf, lauf: Any) -> None:
        """Zeit, Stand, Balken, Takt, Bildfolge, HF, Kurven und Sätze — jede Abfrage."""
        stand = lauf.stand()
        folge = lauf.profil.folge()
        zaehlend = [n for n, (*_, a) in enumerate(folge) if a.zaehlt]
        ueber = lauf.ueber_s() if hasattr(lauf, "ueber_s") else 0.0
        if ueber > 0:
            # Weicher Übergang im Workout: nach Ablauf zählt die Zeit ins Minus weiter
            self.zeit_text.value = f"−{dauer_text(int(ueber))}"
            self.zeit_text.color = ft.Colors.TERTIARY
        else:
            self.zeit_text.value = lauf.anzeige()  # bei der Stoppuhr vorwärts (18.10.2026)
            self.zeit_text.color = None
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
        lage = lauf.takt_lage()
        self.takt_anzeige.nachziehen(lauf.takt_effektiv() if lage else None, lage)
        if isinstance(self.tempo_platz.content, ft.Row):
            self.tempo_platz.content.visible = lage is not None
        if self.bildfolge is not None:
            self.bildfolge.nachziehen(
                lauf.takt_effektiv() if lage else None, lage, stand.abschnitt_s - stand.rest_s
            )
        self._hf_nachziehen()
        self._kurven_nachziehen()
        self._saetze_nachziehen(e, lauf, stand, folge, zaehlend)
        self.halt_knopf.content = ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.PLAY_ARROW if not stand.laeuft else ft.Icons.PAUSE, size=18),
                ft.Text("Weiter" if not stand.laeuft else "Pause"),
            ],
        )
        self.halt_knopf.disabled = (stand.fertig and ueber <= 0) or lauf.abgebrochen
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
        Bereich — gedrosselt wie in der Messansicht, nur Information."""
        e = self._einst
        if e is None or not getattr(e, "alarm_an", False):
            return
        oben, unten = e.alarm_grenze(), e.ziel_unten()
        klang = None
        if oben is not None and hf > oben:
            klang = e.alarm_klang
        elif unten is not None and hf < unten:
            klang = e.alarm_klang_tief
        if klang is None:
            return
        jetzt = time.monotonic()
        if jetzt - self._ton_zuletzt < e.alarm_takt_s:
            return
        self._ton_zuletzt = jetzt
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
        fertig = {(z.name, z.runde): z for z in gelaufene_zeiten(e.ereignisse)}
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


__all__ = ["KURVEN_FENSTER_S", "Fokus", "balken", "kurven_einheit", "kurven_reihen"]
