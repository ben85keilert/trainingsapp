"""Die Herzfrequenz-Sicht der Auswertung `/messung/<id>` (Stufe 2, Ben 29.10.2026).

Derselbe Umschalter wie live (`hf_sicht.sicht_wahl`), dahinter: Kacheln der ganzen Aufnahme,
die HF-Kurve mit Grenzen und Abschnitten, die **Abschnittstabelle mit HF-Spalten**, die
Erholungen aus den Marken, die **Kandidaten** (Ruhe-HF einer Morgenmessung, HFmax als
höchstes 30-s-Mittel, Talk-Test-Marker, Nacht-HF eines Schlafabschnitts oder des
Nachtfensters 20–10 Uhr) — je als Vorschlag
mit „übernehmen“, nie von selbst gesetzt —, die **vorgeschlagenen Abschnitte** aus der HF,
das Tagesprofil, HF je Tempo (mit Strecke), die sRPE-Zeile und „nicht mitrechnen“.

Gerechnet wird in `core.hf_auswertung.auswerten` (im Thread), gemerkt in `data.hf_cache`
mit dem Profilstand von damals (Frage 4): Weicht das heutige Profil ab, zeigt die Sicht die
damaligen Werte und bietet „mit heutigem Profil nachrechnen“ an; gespeichert wird erst nach
Rückfrage.

Die Ansicht liefert nur Zahlen und Vorschläge — kein Urteil (`docs/recht`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz
from hrv_core.ausschnitte import FARBEN as ABSCHNITT_FARBEN
from hrv_core.recording import Recording

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.hf_auswertung import (
    NACHT_FENSTER,
    AbschnittWand,
    HfAuswertung,
    auswerten,
    phase_name,
    profil_stand,
    uhrzeit,
)
from trainingsapp.core.hf_profil import (
    GROESSEN,
    QUELLEN,
    HfProfil,
    Profilwert,
    bereiche_fuer,
    grenzen_bpm,
)
from trainingsapp.core.hrv_ansicht import HF_SPANNE_MIN_BPM
from trainingsapp.core.laufend import minuten
from trainingsapp.core.models import HrvRecording
from trainingsapp.data.hf_profil import RechenAusnahmeRepo
from trainingsapp.ui.components.hf_sicht import (
    HALTUNG_NAMEN,
    KONTEXT_NAMEN,
    prozent_text,
    stufenfarbe,
    zeit_je_bereich,
)
from trainingsapp.ui.components.kacheln import KachelWert, anzeige, zahl
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kurve import Reihe, ausduennen, kurve
from trainingsapp.ui.components.srpe import srpe_zeile

_log = logging.getLogger(__name__)


@dataclass
class HfKontext:
    """Was die Sicht von der Auswertungsansicht braucht — Callbacks statt Zugriff auf deren
    Innenleben (`views/messung_detail.py`)."""

    page: Any
    state: Any
    eintrag: HrvRecording
    rec: Recording
    #: Artefaktmaske je Zeile der Datei (aus der Korrektur)
    artefakt: Callable[[], list[bool]]
    #: Die Abschnitte auf der Wanduhr
    abschnitte_wand: Callable[[], list[AbschnittWand]]
    #: Einen eigenen Abschnitt anlegen (Name, von, bis auf der Wanduhr) — Notizpaar + Sidecar
    abschnitt_anlegen: Callable[[str, float, float], None]
    #: Tempo (m/s) auf der Wanduhr der Datei, wenn eine Strecke dazugehört
    tempo: Callable[[], tuple[list[float], list[float]] | None] = lambda: None
    #: Abschnitte lassen sich anlegen (nicht bei reinem Puls ohne Herzuhr)
    abschnitte_moeglich: bool = True


@dataclass
class _Stand:
    auswertung: HfAuswertung | None = None
    #: der Stand aus dem Cache — None, wenn frisch gerechnet
    cache_profil: dict[str, Any] | None = None
    #: frisch mit heutigem Profil gerechnet, aber nicht gespeichert
    ungespeichert: bool = False
    tempo: dict[str, Any] = field(default_factory=dict)
    laedt: bool = False
    veraltet: bool = True


class HfAuswertungSicht:
    """Baut und pflegt den HF-Teil der Auswertung; `control` hängt in der Hauptspalte."""

    def __init__(self, k: HfKontext) -> None:
        self.k = k
        self.control = ft.Column(spacing=12, visible=False)
        self.stand = _Stand()
        self.tag: date = k.eintrag.started_at.astimezone().date()

    # -- Sichtbarkeit und Laden -----------------------------------------------------

    def zeigen(self, sichtbar: bool) -> None:
        self.control.visible = sichtbar
        if sichtbar and self.stand.veraltet and not self.stand.laedt:
            self.k.page.run_task(self.laden)

    def auffrischen(self) -> None:
        """Abschnitte oder Korrektur haben sich geändert: beim nächsten Zeigen neu rechnen."""
        self.stand.veraltet = True
        if self.control.visible and not self.stand.laedt:
            self.k.page.run_task(self.laden)

    def _profil_heute(self) -> tuple[HfProfil, list[hz.Bereich]]:
        profil = self.k.state.hf_profil(self.tag)
        return profil, bereiche_fuer(profil, self.k.state.hf_einstellungen())

    def _rechnen(self, profil: HfProfil, bereiche: list[hz.Bereich]) -> HfAuswertung:
        return auswerten(
            self.k.rec,
            profil=profil,
            bereiche=bereiche,
            abschnitte=self.k.abschnitte_wand(),
            artefakt=self.k.artefakt(),
        )

    def _tempo_lesen(self) -> tuple[list[float], list[float]] | None:
        """Die Strecke zur Aufnahme — im Loop (Datenbank), nie im Thread."""
        try:
            return self.k.tempo()
        except Exception:
            _log.exception("Tempo der Strecke nicht lesbar")
            return None

    def _tempo_rechnen(
        self, a: HfAuswertung, t: tuple[list[float], list[float]] | None
    ) -> dict[str, Any]:
        """HF je Tempo und Entkopplung — nur mit Strecke und Reihe."""
        if t is None or a.reihe is None or a.reihe.n == 0 or not t[0]:
            return {}
        leistung = hz.auf_raster(t[0], t[1], a.reihe)
        out: dict[str, Any] = {}
        ende = float(a.reihe.t[-1] + a.reihe.raster_s)
        d = hz.drift(a.reihe, 0.0, ende, leistung=leistung)
        if d.entkopplung_prozent is not None:
            out["gesamt"] = {
                "entkopplung": d.entkopplung_prozent,
                "erste": d.erste_haelfte,
                "zweite": d.zweite_haelfte,
            }
        for ab in a.abschnitte:
            if ab["rechen_bis_s"] - ab["rechen_von_s"] >= 1200:
                da = hz.drift(a.reihe, ab["rechen_von_s"], ab["rechen_bis_s"], leistung=leistung)
                if da.entkopplung_prozent is not None:
                    out[ab["id"]] = {"entkopplung": da.entkopplung_prozent}
        return out

    async def laden_heute(self) -> None:
        """„Mit heutigem Profil nachrechnen“ — rechnen, nicht speichern."""
        await self.laden(heutiges_profil=True)

    async def laden(self, *, heutiges_profil: bool = False) -> None:
        """Cache lesen oder rechnen (im Thread). ``heutiges_profil``: rechnen, ohne zu
        speichern — „Speichern“ fragt dann."""
        if self.stand.laedt:
            return
        self.stand.laedt = True
        self._zeige_laden()
        try:
            profil, bereiche = self._profil_heute()
            cache = None if heutiges_profil else self.k.state.hf_cache.lesen(self.k.eintrag.id)
            # Der Cache gilt beim ersten Öffnen; nach einer Änderung (Abschnitte,
            # Korrektur) wird neu gerechnet
            if cache is not None and not cache.veraltet() and self.stand.auswertung is None:
                a = cache.auswertung
                a.reihe = await asyncio.to_thread(
                    hz.reihe_aus_beats, self.k.rec.beats, artefakt=self.k.artefakt()
                )
                self.stand.cache_profil = cache.profil_stand
                self.stand.ungespeichert = False
            else:
                a = await asyncio.to_thread(self._rechnen, profil, bereiche)
                if heutiges_profil:
                    self.stand.cache_profil = None
                    self.stand.ungespeichert = True
                else:
                    self.k.state.hf_cache.schreiben(self.k.eintrag.id, a)
                    self.stand.cache_profil = a.profil_stand
                    self.stand.ungespeichert = False
            self.stand.auswertung = a
            tempo = self._tempo_lesen()
            self.stand.tempo = await asyncio.to_thread(self._tempo_rechnen, a, tempo)
            self.stand.veraltet = False
        except Exception as fehler:
            _log.exception("HF-Auswertung %s", self.k.eintrag.id)
            self.control.controls = [ft.Text(f"HF-Auswertung nicht möglich: {fehler}", size=12)]
            self.stand.laedt = False
            self._update()
            return
        self.stand.laedt = False
        self.bauen()

    def _zeige_laden(self) -> None:
        if not self.control.controls:
            self.control.controls = [
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.ProgressRing(width=18, height=18, stroke_width=2),
                        ft.Text("Herzfrequenz wird gerechnet …", opacity=0.7),
                    ],
                )
            ]
            self._update()

    def _update(self) -> None:
        with contextlib.suppress(Exception):
            self.control.update()
        with contextlib.suppress(Exception):
            self.k.page.update()

    # -- Aktionen ----------------------------------------------------------------------

    def _melden(self, text: str) -> None:
        self.k.page.show_dialog(ft.SnackBar(ft.Text(text)))

    def _profilwert(
        self,
        groesse: str,
        wert: float,
        quelle: str,
        *,
        unsicherheit: float | None,
        herkunft: dict[str, Any],
    ) -> None:
        self.k.state.profilwerte.hinzufuegen(
            Profilwert(
                self.k.state.profil.id,
                groesse,
                round(float(wert), 1),
                quelle,
                self.tag,
                unsicherheit=unsicherheit,
                geraet=self.k.rec.geraet or None,
                hrv_recording_id=self.k.eintrag.id,
                herkunft={"messung": self.k.eintrag.id, **herkunft},
            )
        )
        self._melden(
            f"{GROESSEN.get(groesse, groesse)} {wert:.0f} bpm übernommen "
            f"({QUELLEN.get(quelle, quelle)})."
        )
        self.bauen()

    def _tagesfeld_ruhepuls(self, wert: float) -> None:
        feld = tf.standardfeld(
            self.k.state.tagesfelder.alle(self.k.state.profil.id), tf.STANDARD_RUHEPULS
        )
        if feld is None:
            self._melden("Das Tagesfeld „Ruhepuls“ fehlt.")
            return
        self.k.state.tageswerte.einmal_setzen(feld, self.tag, wert=(round(wert),))
        self._melden(f"Ruhepuls {wert:.0f} ins Tagesfeld vom {self.tag:%d.%m.} eingetragen.")
        self.bauen()

    def _speichern_fragen(self) -> None:
        a = self.stand.auswertung
        if a is None:
            return

        def ja(_e: object = None) -> None:
            self.k.state.hf_cache.schreiben(self.k.eintrag.id, a)
            self.stand.cache_profil, self.stand.ungespeichert = a.profil_stand, False
            self.k.page.pop_dialog()
            self._melden("Mit dem heutigen Profil gespeichert.")
            self.bauen()

        self.k.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Nachrechnung speichern?"),
                content=ft.Text(
                    "Die Werte dieser Aufnahme werden mit dem heutigen Profil (Ruhe-HF, HFmax, "
                    "Grenzen) gespeichert. Der bisherige Stand wird ersetzt — die Messdatei "
                    "bleibt, wie sie ist."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda _=None: self.k.page.pop_dialog()),
                    ft.FilledButton("Speichern", on_click=ja),
                ],
            )
        )

    def _vorschlag_uebernehmen(self, v: dict[str, Any]) -> None:
        name = phase_name(str(v.get("art")), self.k.rec, float(v["von_s"]), float(v["bis_s"]))
        self.k.abschnitt_anlegen(name, float(v["von_s"]), float(v["bis_s"]))
        self._melden(f"Abschnitt „{name}“ angelegt.")
        self.auffrischen()

    # -- Bauen -----------------------------------------------------------------------

    def bauen(self) -> None:
        a = self.stand.auswertung
        if a is None:
            return
        profil, bereiche = self._profil_heute()
        heute_stand = profil_stand(profil, bereiche)
        teile: list[ft.Control] = [
            self._stand_karte(a, heute_stand),
            anzeige(self._kacheln(a, bereiche), self.k.state.hrv_einstellungen().darstellung),
            self._kurven_karte(a, bereiche),
        ]
        if a.abschnitte:
            teile.append(self._abschnitte_karte(a))
        if a.erholungen:
            teile.append(self._erholungen_karte(a))
        kandidaten = self._kandidaten_karte(a, profil)
        if kandidaten is not None:
            teile.append(kandidaten)
        if a.vorschlaege and self.k.abschnitte_moeglich:
            teile.append(self._vorschlaege_karte(a))
        if a.aktivitaet and a.aktivitaet.get("gueltig"):
            teile.append(self._aktivitaet_karte(a, bereiche))
        teile.append(self._tag_karte())
        self.control.controls = teile
        self._update()

    def _stand_karte(self, a: HfAuswertung, heute: dict[str, Any]) -> ft.Control:
        p = a.profil_stand
        if p.get("ruhe") is None or p.get("hfmax") is None:
            text = "Gerechnet ohne Ruhe-HF/HFmax — keine Reserve, keine Bereiche."
        else:
            text = (
                f"Gerechnet mit Ruhe {p['ruhe']:.0f} "
                f"({QUELLEN.get(p.get('ruhe_quelle') or '', '–')}) · "
                f"HFmax {p['hfmax']:.0f} ({QUELLEN.get(p.get('hfmax_quelle') or '', '–')})"
            )
        zeilen: list[ft.Control] = [ft.Text(text, size=12, opacity=0.75)]
        anders = heute != p
        if anders and not self.stand.ungespeichert:
            zeilen.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Dein Profil ist seither anders.", size=12, expand=True),
                        ft.TextButton(
                            "Mit heutigem Profil nachrechnen",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda _=None: self.k.page.run_task(self.laden_heute),
                        ),
                    ],
                )
            )
        if self.stand.ungespeichert:
            zeilen.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Nachgerechnet, nicht gespeichert.", size=12, expand=True),
                        ft.TextButton(
                            "Speichern",
                            icon=ft.Icons.SAVE_OUTLINED,
                            on_click=lambda _=None: self._speichern_fragen(),
                        ),
                        ft.TextButton(
                            "Verwerfen",
                            on_click=lambda _=None: self.k.page.run_task(self._verwerfen),
                        ),
                    ],
                )
            )
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=4),
            content=ft.Column(spacing=2, tight=True, controls=zeilen),
        )

    async def _verwerfen(self) -> None:
        self.stand.ungespeichert = False
        self.stand.veraltet = True
        await self.laden()

    def _kacheln(self, a: HfAuswertung, bereiche: Sequence[hz.Bereich]) -> list[KachelWert]:
        g = a.gesamt
        out = [
            KachelWert("Ø Herzfrequenz", zahl(g.get("mittel_bpm")), "bpm", gross=True),
            KachelWert("Gipfel", zahl(g.get("gipfel_bpm")), "bpm", zusatz="5-s-Mittel", gross=True),
            KachelWert("Minimum", zahl(g.get("minimum_bpm")), "bpm"),
            KachelWert(
                "Gültige Zeit",
                minuten(g.get("gueltig_s") or 0),
                zusatz=f"von {minuten(g.get('dauer_s') or 0)}",
            ),
        ]
        if g.get("mittel_prozent") is not None:
            out.append(KachelWert("Ø Reserve", prozent_text(g.get("mittel_prozent"))))
            out.append(KachelWert("TRIMP", zahl(g.get("trimp"), 1), zusatz="Banister, Konvention"))
        t = self.stand.tempo.get("gesamt")
        if t is not None:
            out.append(
                KachelWert(
                    "HF je Tempo",
                    f"{t['entkopplung']:+.1f}",
                    "%",
                    zusatz="zweite gegen erste Hälfte",
                )
            )
        return out

    def _kurven_karte(self, a: HfAuswertung, bereiche: Sequence[hz.Bereich]) -> ft.Control:
        reihe = a.reihe
        if reihe is None or reihe.n == 0:
            return karte(titel("Herzfrequenz"), hinweis("Keine Herzfrequenz in der Datei."))
        glatt = hz.rollmittel(reihe.hf, 5.0, min_anteil=0.5)
        punkte = ausduennen(
            [(float(t), float(w)) for t, w in zip(reihe.t, glatt, strict=True) if w == w]
        )
        x0, x1 = float(reihe.t[0]), float(reihe.t[-1] + reihe.raster_s)
        reihen = [Reihe(punkte, farbe=ft.Colors.PRIMARY)]
        for g in grenzen_bpm(list(bereiche)):
            reihen.append(
                Reihe(
                    [(x0, g), (x1, g)],
                    farbe=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    breite=1.0,
                    gestrichelt=True,
                )
            )
        for i, ab in enumerate(a.abschnitte):
            reihen.append(
                Reihe(
                    [(ab["von_s"], 0.0), (ab["bis_s"], 0.0)],
                    farbe=ABSCHNITT_FARBEN[i % len(ABSCHNITT_FARBEN)],
                    band=True,
                    ebene=i % 3,
                )
            )
        grenz_namen = (
            " · ".join(f"{b.name} ab {b.von_bpm:.0f}" for b in bereiche[1:]) if bereiche else ""
        )
        return karte(
            titel("Herzfrequenz · ganze Aufnahme"),
            kurve(
                reihen,
                einheit="HF bpm",
                hoehe=200,
                x_von=x0,
                x_bis=x1,
                y_spanne_min=HF_SPANNE_MIN_BPM,
            ),
            zeit_je_bereich(a.gesamt.get("sekunden_je_bereich") if bereiche else None, bereiche),
            *([hinweis(f"Grenzen: {grenz_namen}")] if grenz_namen else []),
        )

    def _abschnitte_karte(self, a: HfAuswertung) -> ft.Control:
        kopf = ft.Row(
            spacing=6,
            controls=[
                ft.Text("Abschnitt", size=11, opacity=0.6, expand=True),
                ft.Text("Ø", size=11, opacity=0.6, width=36, text_align=ft.TextAlign.RIGHT),
                ft.Text("Gipfel", size=11, opacity=0.6, width=44, text_align=ft.TextAlign.RIGHT),
                ft.Text("Res.", size=11, opacity=0.6, width=40, text_align=ft.TextAlign.RIGHT),
                ft.Text("HRR60", size=11, opacity=0.6, width=46, text_align=ft.TextAlign.RIGHT),
            ],
        )
        zeilen: list[ft.Control] = [kopf]
        for i, ab in enumerate(a.abschnitte):
            w = ab["werte"]
            e = ab.get("erholung") or {}
            hrr60 = (e.get("hrr") or {}).get("60")
            drift = ab.get("drift") or {}
            tempo = self.stand.tempo.get(ab["id"])
            unter = [minuten(w.get("gueltig_s") or 0)]
            if drift.get("differenz_bpm") is not None:
                unter.append(f"Drift {drift['differenz_bpm']:+.0f} bpm")
            if tempo is not None:
                unter.append(f"HF je Tempo {tempo['entkopplung']:+.1f} %")
            zeilen.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=4,
                            height=30,
                            bgcolor=ABSCHNITT_FARBEN[i % len(ABSCHNITT_FARBEN)],
                            border_radius=2,
                        ),
                        ft.Column(
                            spacing=0,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    ab["name"],
                                    size=13,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(" · ".join(unter), size=11, opacity=0.6),
                            ],
                        ),
                        ft.Text(
                            zahl(w.get("mittel_bpm")),
                            size=13,
                            width=36,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            zahl(w.get("gipfel_bpm")),
                            size=13,
                            width=44,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            prozent_text(w.get("mittel_prozent"))
                            if w.get("mittel_prozent") is not None
                            else "–",
                            size=13,
                            width=40,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            f"−{hrr60:.0f}" if hrr60 is not None else "–",
                            size=13,
                            width=46,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ],
                )
            )
        return karte(
            titel(f"Abschnitte · {len(a.abschnitte)}"),
            *zeilen,
            hinweis(
                "Res. = Ø Anteil an der Reserve. HRR60 nur, wenn die HF nach dem Ende fällt "
                "und 60 s Daten folgen."
            ),
        )

    def _erholungen_karte(self, a: HfAuswertung) -> ft.Control:
        zeilen: list[ft.Control] = []
        for e in a.erholungen:
            hrr = e.get("hrr") or {}
            teile = [f"HF {zahl(e.get('hf_ende'))}"]
            for f in ("30", "60", "120"):
                w = hrr.get(f)
                teile.append(f"HRR{f} {'−' + f'{w:.0f}' if w is not None else '–'}")
            zeilen.append(
                ft.Text(
                    f"{uhrzeit(self.k.rec, float(e['t0']))} · "
                    f"{KONTEXT_NAMEN.get(e.get('kontext') or '', e.get('kontext') or '–')} · "
                    f"{HALTUNG_NAMEN.get(e.get('haltung') or '', e.get('haltung') or '–')} · "
                    + " · ".join(teile),
                    size=12,
                )
            )
        return karte(
            titel(f"Erholungen · {len(a.erholungen)}"),
            *zeilen,
            hinweis("Vergleichbar sind nur Erholungen mit gleichem „Woran“ und gleicher Haltung."),
        )

    def _kandidaten_karte(self, a: HfAuswertung, profil: HfProfil) -> ft.Control | None:
        zeilen: list[ft.Control] = []

        def zeile(text: str, *knoepfe: ft.Control) -> ft.Control:
            return ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(text, size=12),
                    ft.Row(spacing=4, wrap=True, controls=list(knoepfe)),
                ],
            )

        r = a.ruhe_kandidat
        if r and r.get("wert") is not None:
            w = float(r["wert"])
            grund = "" if r.get("gueltig") else " · " + "; ".join(r.get("gruende") or [])
            zeilen.append(
                zeile(
                    f"Ruhe-HF dieser Messung: {w:.0f} bpm (tiefstes 30-s-Mittel{grund})",
                    ft.TextButton(
                        "Als Ruhe-HF übernehmen",
                        icon=ft.Icons.PERSON_OUTLINE,
                        disabled=not r.get("gueltig"),
                        on_click=lambda _=None, w=w, r=r: self._profilwert(
                            hz.GROESSE_RUHE,
                            w,
                            str(r.get("quelle") or "messung_morgen_5"),
                            unsicherheit=None,
                            herkunft={
                                "fenster": [r.get("t_von"), r.get("t_bis")],
                                "artefaktanteil": r.get("artefaktanteil"),
                            },
                        ),
                    ),
                    ft.TextButton(
                        "Ins Tagesfeld Ruhepuls",
                        icon=ft.Icons.TODAY,
                        on_click=lambda _=None, w=w: self._tagesfeld_ruhepuls(w),
                    ),
                )
            )
        m = a.hfmax_kandidat
        if m and m.get("wert") is not None and m.get("gueltig"):
            w = float(m["wert"])
            jetzt = profil.hfmax_bpm
            vergleich = ""
            if jetzt is not None:
                vergleich = f" — deine HFmax ist {jetzt:.0f}" + (
                    " (geschätzt)" if profil.hfmax_geschaetzt else ""
                )
            t_von = m.get("t_von")
            zeilen.append(
                zeile(
                    f"Höchstes 30-s-Mittel: {w:.0f} bpm um "
                    f"{uhrzeit(self.k.rec, float(t_von or 0))}{vergleich}",
                    ft.TextButton(
                        "Als HFmax übernehmen",
                        icon=ft.Icons.NORTH,
                        on_click=lambda _=None, w=w, m=m: self._profilwert(
                            hz.GROESSE_MAX,
                            w,
                            "feldmaximum",
                            unsicherheit=None,
                            herkunft={
                                "fenster": [m.get("t_von"), m.get("t_bis")],
                                "artefaktanteil": m.get("artefaktanteil"),
                            },
                        ),
                    ),
                )
            )
        t = a.talk
        if t and t.get("wert") is not None:
            w = float(t["wert"])
            p = t.get("prozent")
            zeilen.append(
                zeile(
                    f"Talk-Test: HF vor „Sprechen wird schwer“ {w:.0f} bpm"
                    + (f" ({p:.0f} % der Reserve)" if p is not None else ""),
                    ft.TextButton(
                        "Als Schwelle 1 übernehmen",
                        icon=ft.Icons.RECORD_VOICE_OVER,
                        on_click=lambda _=None, w=w, t=t: self._profilwert(
                            hz.GROESSE_VT1,
                            w,
                            "talk_test",
                            unsicherheit=None,
                            herkunft={"t_wall_s": t.get("t_wall_s")},
                        ),
                    ),
                )
            )
        n = a.nacht
        if n and n.get("wert") is not None:
            w = float(n["wert"])
            grund = "" if n.get("gueltig") else " · " + "; ".join(n.get("gruende") or [])
            wo = (
                "im Schlafabschnitt"
                if n.get("grundlage") != NACHT_FENSTER
                else f"zwischen {uhrzeit(self.k.rec, float(n.get('von_s') or 0))} und "
                f"{uhrzeit(self.k.rec, float(n.get('bis_s') or 0))}, ohne Schlafabschnitt"
            )
            zeilen.append(
                zeile(
                    f"Nacht-HF (tiefstes 2-h-Mittel {wo}): {w:.0f} bpm{grund}",
                    ft.TextButton(
                        "Als Nacht-HF übernehmen",
                        icon=ft.Icons.BEDTIME_OUTLINED,
                        disabled=not n.get("gueltig"),
                        on_click=lambda _=None, w=w, n=n: self._profilwert(
                            hz.GROESSE_RUHE,
                            w,
                            "nacht",
                            unsicherheit=None,
                            herkunft={
                                "fenster": [n.get("t_von"), n.get("t_bis")],
                                "abschnitt": n.get("abschnitt_id"),
                                "grundlage": n.get("grundlage"),
                            },
                        ),
                    ),
                )
            )
        if not zeilen:
            return None
        return karte(
            titel("Vorschläge fürs Profil"),
            *zeilen,
            hinweis(
                "Vorschläge aus dieser Aufnahme — gesetzt wird nur, was du übernimmst. Quelle, "
                "Datum und Messung stehen dann im Profil."
            ),
        )

    def _vorschlaege_karte(self, a: HfAuswertung) -> ft.Control:
        namen = {hz.ART_BELASTUNG: "Belastung", hz.ART_RUHE: "Ruhe", hz.ART_SCHLAF: "Schlaf"}
        zeilen: list[ft.Control] = []
        for v in a.vorschlaege[:12]:
            von, bis = float(v["von_s"]), float(v["bis_s"])
            zeilen.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"{namen.get(v['art'], v['art'])} {uhrzeit(self.k.rec, von)}–"
                            f"{uhrzeit(self.k.rec, bis)} · "
                            f"{minuten(bis - von)} · Ø {zahl(v.get('mittel_bpm'))} bpm",
                            size=12,
                            expand=True,
                        ),
                        ft.TextButton(
                            "Übernehmen",
                            icon=ft.Icons.ADD,
                            on_click=lambda _=None, vv=v: self._vorschlag_uebernehmen(vv),
                        ),
                    ],
                )
            )
        return karte(
            titel("Vorgeschlagene Abschnitte"),
            *zeilen,
            hinweis(
                "Aus der Herzfrequenz erkannt (Belastung ab 40 % der Reserve über 3 min, Ruhe, "
                "Schlaf ≥ 4 h) — ein Abschnitt entsteht erst, wenn du ihn übernimmst."
            ),
        )

    def _aktivitaet_karte(self, a: HfAuswertung, bereiche: Sequence[hz.Bereich]) -> ft.Control:
        ak = a.aktivitaet or {}
        sek = ak.get("sekunden_je_cluster") or []
        gesamt = sum(sek) or 1.0
        zeilen = [
            ft.Row(
                spacing=8,
                controls=[
                    ft.Container(width=10, height=10, bgcolor=stufenfarbe(i, 10), border_radius=2),
                    ft.Text(f"{i * 10}–{i * 10 + 10} %", size=12, width=70),
                    ft.Text(minuten(s), size=12, width=60),
                    ft.Text(f"{s / gesamt * 100:.0f} %", size=12, opacity=0.65),
                ],
            )
            for i, s in enumerate(sek)
        ]
        return karte(
            titel("Tagesprofil · Zeit je 10 % der Reserve"),
            *zeilen,
            hinweis(f"Gültiger Tag ab 16 h Daten ({minuten(ak.get('gueltig_s') or 0)} vorhanden)."),
        )

    def _tag_karte(self) -> ft.Control:
        state = self.k.state
        ist_aus = state.ausnahmen.ist(
            state.profil.id, RechenAusnahmeRepo.MESSUNG, self.k.eintrag.id
        )

        def umschalten(e: ft.Event[ft.Switch]) -> None:
            if bool(e.control.value):
                state.ausnahmen.setzen(
                    state.profil.id, RechenAusnahmeRepo.MESSUNG, self.k.eintrag.id
                )
            else:
                state.ausnahmen.loesen(
                    state.profil.id, RechenAusnahmeRepo.MESSUNG, self.k.eintrag.id
                )

        teile: list[ft.Control] = []
        srpe = srpe_zeile(self.k.page, state, self.tag)
        if srpe is not None:
            teile.append(srpe)
        teile.append(
            ft.Switch(
                label="Diese Messung nicht mitrechnen",
                value=ist_aus,
                on_change=umschalten,
            )
        )
        teile.append(
            hinweis(
                "Nicht mitgerechnet heißt: zählt nicht für Mittelwerte, Baseline, Wochenlast "
                "und Feldmaximum."
            )
        )
        return karte(titel(f"Zum Tag · {self.tag:%d.%m.%Y}"), *teile)


__all__ = ["HfAuswertungSicht", "HfKontext"]
