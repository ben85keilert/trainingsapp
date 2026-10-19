"""Eine Aufzeichnung — Route `/messung/<id>`: ansehen und korrigieren.

Die Rohdatei bleibt unangetastet. Korrekturen sind Vorschläge der Automatik
(`hrv_core.korrektur.vorschlaege`) als Ketten; was übernommen wird, landet in
`sensor_<ts>_analyzed.json` neben der Rohdatei — dieselbe Teilmenge von
`analysis-v1`, die praxis_gui liest, samt den Regeln, mit denen sie entstand.

Was „automatisch" heißt, stellt das Regler-Symbol neben „Korrektur" ein
(`Korrekturregeln`) — je Messung, auf Wunsch als Vorgabe gemerkt. Bei der
Verity Sense zählt standardmäßig nur, was der Sensor nicht verworfen hat; auf
Wunsch prüft das Programm das Verworfene selbst (`korrektur.analysebasis`).
Die Regeln und ihre Gründe: docs/korrektur.md.

Alle Kurven teilen ein Zeitfenster (Breite wählen, waagrecht wischen); die
Lupe an einer Kette zoomt auf ihre Stelle. Die Ansicht öffnet mit den ersten
2 Minuten (`START_BREITE_S`) — „Alles" rechnete beim Öffnen sofort über die
ganze Messung.

Spektrum, Poincaré und DFA gelten für das **Analysefenster**: die ganze
Messung (Vorgabe), einen Abschnitt oder ein Band fester Länge, das man in der
Rohkurve greift und schiebt. Gerechnet wird beim Loslassen, nach einer kurzen
Latenz (Einstellungen → Erweitert), falls noch eine Bewegung nachkommt
(`docs/plan_analyse_leistung.md`).

Aufbau wie live: Kacheln (Werte der ganzen Messung, korrigiert), Hauptkurve,
darunter die Analyse (Zeit ↔ Frequenz ↔ Nichtlinear) mit einer Zusammenfassung
der ganzen Messung je Bereich — Zeitbereich roh und korrigiert, Frequenzbänder
mit Sperrgrund (Task-Force-Mindestdauer), Poincaré, DFA α1 und SampEn.

**Vollbild (quer)** ist ein Modus derselben Ansicht (`components.vollbild`,
Ben 15./16.10.2026): zwei y-Achsen (links das Tachogramm, rechts eine
Verlaufskurve — beide wählbar), rechts eine Werkzeugleiste (Ablesen, Notiz,
Notizen, Abschnitte, Zuschneiden, Fenster & Darstellung) und daneben die
Seitenleiste mit denselben Feldern wie hochkant. Ein Tipp auf eine Notizmarke
oder einen Abschnittsbalken zeigt sein Etikett in der Kurve.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

import flet as ft
import numpy as np
from hrv_core.atmung import ATEMUEBUNG, RUHE, atemfrequenz, kurzgrund
from hrv_core.ausschnitte import FARBEN as ABSCHNITT_FARBEN
from hrv_core.ausschnitte import (
    Abschnitt,
    Grenze,
    abschnitt_spektrum,
    abschnitt_werte,
    achsen_umrechnung,
    aus_grenzen,
    einrasten,
    farben_nach_namen,
    zusatz_lesen,
    zusatz_speichern,
)
from hrv_core.constants import BAND_OK
from hrv_core.ereignisse import Zeitbezug, metadaten_schreiben
from hrv_core.frequency import Fensterspektrum, frequenzbereich
from hrv_core.korrektur import (
    Kette,
    Korrektur,
    Korrekturstand,
    Korrigiert,
    SidecarFehler,
    analyse_speichern,
    anwenden,
    korr_zeiten,
    korrektur_laden,
    korrekturstand,
    rohfolge,
    vorauswahl,
    zuschneiden,
)
from hrv_core.nonlinear import compute_dfa_alpha1, compute_poincare, compute_sampen
from hrv_core.ppi import ppi_verworfen, schlagzeiten
from hrv_core.regeln import Korrekturregeln
from hrv_core.segments import filter_rr
from hrv_core.time_domain import compute_time_domain
from hrv_core.trends import DFA_MIN_SCHLAEGE, KENNZAHLEN, reihe, titel

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.aufnahme_bezug import RAND_S, Bezug
from trainingsapp.core.hrv_ansicht import (
    HF_SPANNE_MIN_BPM,
    LINKS,
    RECHTS,
    ROH,
    ROH_MAX_MS,
    ROH_MIN_MS,
)
from trainingsapp.core.hrv_einstellungen import (
    ANALYSE_LAENGEN,
    EBENE_ABSCHNITTE,
    EBENE_LEISTUNGEN,
    EBENE_NOTIZEN,
    EBENEN,
)
from trainingsapp.core.hrv_export import export_zip, zugehoerige_dateien
from trainingsapp.core.laufend import minuten
from trainingsapp.core.models import HrvRecording
from trainingsapp.core.tagesbilanz import buendeln
from trainingsapp.core.timer import ENDE_MARKE
from trainingsapp.core.timer import name_aus_notiz as abschnittsname
from trainingsapp.ui import ausrichtung
from trainingsapp.ui.components.analyse import Analyse, Analysefenster, verlaufsdaten
from trainingsapp.ui.components.bereich import BereichEditor, band, schatten
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.forschung import forschung_fragen
from trainingsapp.ui.components.kacheln import (
    KACHELN,
    PULS_KACHELN,
    KachelWert,
    anzeige,
    ohne_intervalle,
    zahl,
)
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_knopf
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.titel import (
    geuebte_plaene,
    titel_blatt,
    titel_kopf,
    titel_vorschlaege,
)
from trainingsapp.ui.components.verlauf import FARBEN, darstellung_blatt, fenster_text, werte_bei
from trainingsapp.ui.components.vollbild import (
    ETIKETT_PX,
    LEISTE_PX,
    SEITE_PX,
    ZEITACHSE_PX,
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
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.components.zurueck import rueckfrage, zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import ohne_rr

QUALITAET = {
    "rr_ekg": "RR aus EKG (volle HRV)",
    "ppi_optisch": "Pulsintervalle optisch (Frequenzwerte mit Vorbehalt)",
    "bpm_only": "nur Herzfrequenz (keine HRV)",
}


#: Eine Schreibweise für alle Zeiten (N26)
_uhr = minuten


def _wert(d: dict | None, key: str, nachkomma: int = 1) -> str:
    if not d or d.get(key) is None:
        return "–"
    return zahl(d[key], nachkomma)


def _linie(
    paare: Iterable[tuple[float, float]],
    naht_vor: Iterable[int],
    unten: float = 0.0,
    oben: float = float("inf"),
    x_von: float = float("-inf"),
    x_bis: float = float("inf"),
) -> tuple[list[tuple[float, float]], list[int]]:
    """Punkte im Bereich ``(unten, oben)`` und die Nähte als Indizes in diese Liste.

    ``naht_vor`` zählt in ``paare``; fällt ein Punkt heraus, rutscht seine Naht
    auf den nächsten sichtbaren. ``x_von``/``x_bis``: sichtbares Zeitfenster —
    Flet schneidet nicht ab, Punkte daneben lägen über den Achsen.
    """
    vor = set(naht_vor)
    punkte: list[tuple[float, float]] = []
    idx: list[int] = []
    offen = False
    for i, (t, r) in enumerate(paare):
        offen = offen or i in vor
        if not (x_von <= t <= x_bis and unten < r < oben):
            continue
        if offen and punkte:
            idx.append(len(punkte))
        offen = False
        punkte.append((t, r))
    return punkte, idx


def _verworfen_text(rec_verworfen: tuple[int, int] | None) -> Sequence[str]:
    """Anteil der vom Sensor verworfenen Intervalle — leer ohne PPI-Rohdaten."""
    if not rec_verworfen or not rec_verworfen[1] or not rec_verworfen[0]:
        return []
    return [f"{round(100 * rec_verworfen[0] / rec_verworfen[1])} % vom Sensor verworfen"]


#: Breiten des Zeitfensters (s) — „Min“ hinten dran, vier Knöpfe über die volle Breite
#: (Ben, 19.10.2026, Plan F); die ganze Messung zeigt der Abschnitt-Chip „Ganze Messung“
BREITEN = [(60, "1 Min"), (120, "2 Min"), (300, "5 Min"), (600, "10 Min")]
#: Beschriftung der Ebenen-Chips über der Kurve (Plan D)
EBENEN_TEXT = {
    EBENE_NOTIZEN: "Notizen",
    EBENE_LEISTUNGEN: "Leistungen",
    EBENE_ABSCHNITTE: "Abschnitte",
}
UEBUNGEN_INFO = (
    "Hier stehen die **Tagebucheinträge**, die in dieser Aufnahme liegen — gefunden über die "
    "Zeitleiste der Einheit (jeder Satz bekam eine Marke) oder, bei älteren und nachgetragenen "
    "Einträgen, über die Uhr („zeitlich“).\n\n"
    "Ein Tipp **zoomt** auf den Ausschnitt des Eintrags und legt das Analysefenster darauf — "
    "die Aufnahme bleibt ein Stück; nichts wird zerschnitten.\n\n"
    "- **Blau** in der Kurve: Leistungen — „geleistet bis hierher“, die Tippzeit eines Satzes.\n"
    "- **Gelb:** Notizen."
)


def _ist_leistung(e: dict) -> bool:
    """Eine Notiz mit Marke der Person (`person/leistung`, `person/abschluss`) — sie gehört
    zur Ebene „Leistungen“, nicht in die Notizliste."""
    m = e.get("marke")
    return isinstance(m, dict) and m.get("quelle") == "person"


#: So breit öffnet die Aufzeichnung — am Anfang der Messung (Ben, 14.10.2026)
START_BREITE_S = 120

#: Analysefenster: wofür Spektrum, Poincaré und DFA gerechnet werden
AW_ALLES = "alles"
AW_ABSCHNITT = "abschnitt"
AW_BAND = "band"


CROP = "crop"
ABSCHNITT = "abschnitt"
#: Farbe des verschiebbaren Analysefensters in der Rohkurve
BAND_FARBE = ft.Colors.TERTIARY
#: Meldung nach dem Speichern der Korrektur — Knopf und Zurück (Autosave, 16.10.2026)
KORREKTUR_GESPEICHERT = "Korrektur gespeichert — die Rohdatei bleibt unverändert."


@dataclass
class _Analysewahl:
    """Das gewählte Analysefenster und, beim Band, ob es gerade gezogen wird."""

    art: str = AW_ALLES
    abschnitt_id: str | None = None
    laenge_s: int = 300
    #: Beginn des Bands auf der Kurvenachse — ``None`` = mitten im sichtbaren Ausschnitt
    von: float | None = None
    #: Band gegriffen: Abstand Finger − Beginn (s)
    griff: float | None = None
    #: Losgelassen, das Nachrechnen ist geplant
    wartet: bool = False
    #: Laufende Nummer des Nachrechnen-Auftrags — nur der letzte rechnet
    auftrag: int = 0


def _kurven_info(nur_puls: bool, verworfen: object) -> str:
    """Was hinter dem „i“ der Hauptkurve steht (Ben, 17.10.2026: vorher grauer Text).

    >>> _kurven_info(True, None).startswith("Diese Messung enthält nur die **Herzfrequenz**")
    True
    """
    if nur_puls:
        return (
            "Diese Messung enthält nur die **Herzfrequenz** (bpm) — das Gerät hat keine "
            "Abstände von Schlag zu Schlag gesendet. Die Kurve zeigt den Puls; HRV-Werte, "
            "Korrektur, Zuschneiden und Abschnitte gibt es dafür nicht.\n\n"
            "- **Gelb:** Notizen"
        )
    grau = "alle Intervalle des Sensors, auch verworfene" if verworfen else "Rohwerte"
    return (
        f"- **Grau:** {grau}\n"
        "- **Farbig:** gewertet (korrigiert)\n"
        "- **Rot:** auffällige Schläge\n"
        "- **Gelb:** Notizen\n\n"
        "Waagrecht wischen blättert, die Breite darüber wählt den Ausschnitt. "
        "Korrigiert wird unter „Korrektur“ — die Rohdatei bleibt unverändert."
    )


# Was hinter den „i“ der übrigen Karten steht — vorher grauer Text darin (Ben, 17.10.2026).
# Sichtbar bleibt, was die Zahlen einschränkt: gesperrte Bänder, optisch nicht belastbar.

ABSCHNITTE_INFO = (
    "Werte je Abschnitt — so lassen sich Belastung und Pause oder Übungen vergleichen.\n\n"
    "- **„+ Abschnitt“** wählt einen Bereich in der Kurve.\n"
    "- **Menü daneben:** Notizen werden zu Grenzen.\n"
    "- **Antippen** eines Abschnitts: Grenzen in der Kurve verschieben, umbenennen, löschen; "
    "nahe Notizen ziehen die Grenzen an.\n\n"
    "Notizen sind dafür nicht nötig. Mit dem Timer entstehen Abschnitte beim Speichern der "
    "Aufnahme von selbst."
)

KORREKTUR_INFO = (
    "Vorschläge der Automatik: **kurze Ketten** auffälliger Schläge werden interpoliert, "
    "**lange** ausgeschlossen.\n\n"
    "- **Antippen** übernimmt oder verwirft einen Vorschlag, die **Lupe** zeigt die Stelle "
    "in der Kurve.\n"
    "- **„Alle“ / „Keine“** übernimmt bzw. verwirft alle auf einmal.\n"
    "- **Regler:** die Regeln der Automatik für diese Messung ändern oder als Vorgabe merken.\n\n"
    "„Korrektur speichern“ legt sie neben die Messung — die Rohdatei bleibt unverändert."
)

#: Zur Karte „Verlauf“: was die Tabelle des Bereichs zusammenfasst
TABELLE_INFO = {
    "zeit": "**Tabelle:** die ganze Messung, roh und korrigiert. Über Nähte (Lücken, "
    "Ausschlüsse) wird keine Differenz gebildet.",
    "frequenz": "**Tabelle:** die ganze Messung (korrigiert), Lomb-Scargle je lückenfreiem "
    "Teilstück; bei langen Messungen LF/HF als Mittel von 5-min-Spektren, VLF von "
    "30-min-Spektren, ULF über die ganze Länge. „gesperrt“: Das Band lässt sich in dieser "
    "Messung nicht sicher bestimmen — warum, steht unter der Tabelle.",
    "nichtlinear": "**Tabelle:** die ganze Messung (korrigiert). Nichtlineare Werte brauchen "
    "genaue Schlagzeiten: beim 130-Hz-EKG des H10 als Trend lesbar, bei optischen "
    "Pulsintervallen nicht belastbar.",
}

FENSTER_INFO = (
    "**Analysefenster** (über Spektrum bzw. Poincaré): die ganze Messung, ein Abschnitt oder "
    "ein Fenster fester Länge. Das Fenster als Band in der Rohkurve greifen und schieben; "
    "die Pfeile rücken es um ein halbes weiter."
)


def _verlauf_info(bereich: str) -> str:
    """Was das „i“ der Karte „Verlauf“ in der Aufzeichnung zusätzlich erklärt.

    >>> "Analysefenster" in _verlauf_info("frequenz"), "Analysefenster" in _verlauf_info("zeit")
    (True, False)
    """
    teile = [TABELLE_INFO.get(bereich, "")]
    if bereich in ("frequenz", "nichtlinear"):
        teile.append(FENSTER_INFO)
    return "\n\n".join(t for t in teile if t)


@dataclass
class _Kurvenmodus:
    """Was Tippen und Ziehen in der Rohkurve gerade tun."""

    #: Bereich wählen — fürs Zuschneiden (``art`` = `CROP`) oder einen Abschnitt
    editor: BereichEditor | None = None
    art: str = ""
    #: Der bearbeitete Abschnitt (``None`` = ein neuer)
    abschnitt: Abschnitt | None = None
    name_feld: ft.TextField | None = None
    #: Ablesen: der Strich steht an ``strich`` (s), darunter alle Werte
    ablesen: bool = False
    strich: float | None = None
    #: Vollbild (quer): Kurven mit zwei Achsen und Werkzeuge, Fläche in gemessener Größe (px)
    vollbild: bool = False
    hoehe: float = 220.0
    breite: float = 800.0
    #: Vollbild: wählbare Kurven, Breite der rechten Achse, Stand der Kopfzeile
    angebot: list[str] = field(default_factory=list)
    rechts: float = 0.0
    kopf: tuple[Any, ...] = ()
    #: Vollbild: zuletzt gezeichnete Verlaufskurven (zum Ablesen)
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]] = field(default_factory=dict)
    #: Vollbild: Etikett in der Kurve — ``("notiz", Index)`` oder ``("abschnitt", ID)``
    etikett: tuple[str, Any] | None = None
    #: Vollbild: offene Seitenleiste — `NOTIZEN`, `ABSCHNITTE` oder ``None``
    seite: str | None = None
    #: Die Achse ist an diesen Abschnitt gebunden (Chip, Plan F): 0:00 ist sein Beginn,
    #: Wischen bleibt darin — ``None``: die ganze Messung
    bindung: Abschnitt | None = None


#: Seitenleisten des Vollbilds
NOTIZEN = "notizen"
ABSCHNITTE = "abschnitte"


def messung_detail_view(page: ft.Page, state: AppState, eintrag: HrvRecording) -> ft.View:
    """Die Auswertung einer Aufzeichnung.

    Die Ansicht steht sofort; Messdatei und Sidecar liest ein Thread (`_laden` — H39:
    eine 4-h-Datei hielt den Event-Loop sekundenlang an), danach baut `_aufbauen` den
    Inhalt — sofern die Ansicht noch die aktuelle ist (`state.route_nummer`).
    """
    route = f"/messung/{eintrag.id}"
    pfad = messungenverzeichnis() / eintrag.file_path
    inhalt = ft.Column(spacing=12)
    view = ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(_titel(eintrag))),
        scroll=ft.ScrollMode.AUTO,
        padding=12,
        controls=[sicher(inhalt, expand=False)],
    )
    if not pfad.exists():
        inhalt.controls = [
            ft.Text("Die Messdatei fehlt.", size=16, weight=ft.FontWeight.W_600),
            ft.Text(str(pfad), size=12, selectable=True, opacity=0.7),
        ]
        return view
    inhalt.controls = [
        ft.Row(
            spacing=10,
            controls=[
                ft.ProgressRing(width=20, height=20, stroke_width=2),
                ft.Text("Messdatei wird gelesen …", opacity=0.7),
            ],
        )
    ]
    vorgabe = state.korrekturregeln()  # Datenbank: im Loop, nicht im Thread
    ansicht_nummer = state.route_nummer

    async def fuellen() -> None:
        try:
            geladen = await asyncio.to_thread(_laden, pfad, vorgabe)
            if state.route_nummer != ansicht_nummer:
                return  # die Ansicht ist schon verlassen
            _aufbauen(page, state, eintrag, view, inhalt, geladen)
        except Exception as fehler:
            if state.route_nummer != ansicht_nummer:
                return
            logging.getLogger(__name__).exception("Messung %s nicht geöffnet", eintrag.id)
            inhalt.controls = [
                ft.Text(
                    "Die Messdatei ließ sich nicht lesen.", size=16, weight=ft.FontWeight.W_600
                ),
                ft.Text(str(fehler), size=12, selectable=True, opacity=0.7),
            ]
        with contextlib.suppress(Exception):
            page.update()

    page.run_task(fuellen)
    return view


def _titel(eintrag: HrvRecording) -> str:
    return f"Messung {eintrag.started_at.astimezone():%d.%m. %H:%M}"


@dataclass
class _Geladen:
    """Was die Ansicht aus Messdatei und Sidecar braucht — gelesen und gerechnet im Thread."""

    z: _Zustand
    gespeicherte_regeln: Korrekturregeln | None
    #: Das Sidecar gehört zu einer anderen oder veränderten Messdatei (hrv-core R16)
    sidecar_alt: bool
    #: Zeitachse der Zeilen der Rohdatei — Notizen hängen daran
    zeilen_achse: list[float]
    #: Kurvenachse → Herzuhr der Rohdatei (Sidecar)
    nach_datei: Callable[[float], float]
    #: Selbst markierte Abschnitte (Sidecar)
    eigene: list[Any]


def _laden(pfad: Path, vorgabe: Korrekturregeln) -> _Geladen:
    """Messdatei, Regeln, Sidecar, Vorschläge und Auswahl (`hrv_core.korrektur.korrektur_laden`),
    dazu Achsen und Abschnitte — nur Datei- und Rechenarbeit, darum im Thread (H39).

    Regeln sind die der gespeicherten Korrektur, sonst ``vorgabe`` (gerätelokal; optische
    Intervalle streuen mehr: Malik „nach Sensor" = 0.30, Vertrag Abschnitt 5). Passt die
    Prüfsumme im Sidecar nicht zur Messdatei, gehören Korrekturen und Abschnitte zu einer
    anderen oder veränderten Datei — per Index träfen sie falsche Schläge (hrv-core R16).
    Dann gilt die Vorauswahl, und die Ansicht sagt es (``sidecar_alt``).
    """
    stand = korrektur_laden(pfad, vorgabe)
    z = _Zustand(stand)
    rec = stand.rec
    sidecar_alt = stand.veraltet
    # Notizen hängen an den Zeilen der Rohdatei; die Kurve hat ihre eigene Zeitachse
    # (nur Puls: die Wanduhr, siehe `_Zustand`)
    zeilen_achse = (
        [float(b.t_wall_s or 0.0) for b in rec.beats] if z.nur_puls else schlagzeiten(rec)
    )
    # Crop und eigene Abschnitte stehen im Sidecar auf der Herzuhr der Rohdatei — die
    # hat eine reine Pulsmessung nicht, dort gibt es beides nicht
    nach_datei, nach_achse = achsen_umrechnung(zeilen_achse, [b.t_s for b in rec.beats])
    if z.nur_puls or sidecar_alt:
        eigene: list[Any] = []
    else:
        z.ausschnitt, eigene = zusatz_lesen(pfad, nach_achse)
    return _Geladen(z, stand.gespeicherte_regeln, sidecar_alt, zeilen_achse, nach_datei, eigene)


def _aufbauen(
    page: ft.Page,
    state: AppState,
    eintrag: HrvRecording,
    view: ft.View,
    inhalt: ft.Column,
    geladen: _Geladen,
) -> None:
    """Der Inhalt der Auswertung in ``view`` — alles, was Messdatei und Sidecar braucht."""
    route = f"/messung/{eintrag.id}"
    pfad = messungenverzeichnis() / eintrag.file_path
    #: Schreibvorgänge auf Messdatei und Sidecar laufen in Threads, der Reihe nach (H39):
    #: ein schnelles zweites Loslassen des Markenreglers überholt das erste nicht
    sperre = asyncio.Lock()
    ansicht_nummer = state.route_nummer

    def aktuell() -> bool:
        """Ist die Ansicht nach einem ``await`` noch die aktuelle?"""
        return state.route_nummer == ansicht_nummer

    #: Die Leiste der Ansicht — das Vollbild nimmt sie ab und gibt sie zurück
    leiste_oben: ft.AppBar | None = None
    #: Zuschneiden braucht Intervalle — eine reine Pulsmessung hat keine
    zuschneidbar = True
    #: Die Einheiten, an denen die Messung teilnahm (älteste zuerst) — für den
    #: Forschungsexport (Stufe 4, Katalog A14)
    einheiten = (
        [i for i, _ in state.einheiten.zur_datei("hrv", eintrag.file_path)]
        if state.einheiten is not None
        else []
    )

    #: Tagebucheinträge in dieser Aufnahme (Plan C) — über die Zeitleiste oder die Uhr
    bezuege_liste: list[Bezug] = (
        state.bezuege.zur_aufnahme(eintrag) if getattr(state, "bezuege", None) is not None else []
    )

    def ansicht(teile: list[ft.Control]) -> ft.View:
        nonlocal leiste_oben
        leiste_oben = ft.AppBar(
            title=ft.Text(_titel(eintrag)),
            actions=[
                ft.IconButton(
                    ft.Icons.CONTENT_CUT,
                    tooltip="Zuschneiden",
                    on_click=lambda: crop_oeffnen(),
                    visible=zuschneidbar,
                ),
                ft.IconButton(ft.Icons.SHARE, tooltip="Exportieren (ZIP)", on_click=exportieren),
                ft.IconButton(
                    ft.Icons.SCIENCE_OUTLINED,
                    tooltip="Für die Auswertung exportieren (ohne Ort)",
                    on_click=lambda: forschung_fragen(page, state, einheiten),
                    visible=bool(einheiten),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE, tooltip="Aus der Liste entfernen", on_click=fragen
                ),
            ],
        )
        view.appbar = leiste_oben
        inhalt.controls = teile
        return view

    # -- Exportieren -----------------------------------------------------------

    async def exportieren() -> None:
        """Rohdatei samt Korrektur und Diagnoseprotokoll als ZIP herausgeben."""
        dateien = zugehoerige_dateien(pfad)
        if not dateien:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Dateien zu dieser Messung gefunden.")))
            return
        daten = await asyncio.to_thread(export_zip, dateien, datenverzeichnis())
        await weitergeben(page, f"{pfad.stem}.zip", daten, "application/zip")

    # -- Entfernen -------------------------------------------------------------

    def fragen() -> None:
        page.show_dialog(dialog)

    nachher = Nachher()  # SnackBar und Routenwechsel erst, wenn der Dialog zu ist (N19)

    def abbrechen() -> None:
        schliessen(dialog)

    def entfernen() -> None:
        state.hrv.loeschen(eintrag.id)
        meldung = "Aus der Liste entfernt — die Datei bleibt."
        nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(meldung))))
        nachher.danach(lambda: page.push_route("/"))
        schliessen(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Aufzeichnung entfernen?"),
        content=ft.Text(
            "Sie verschwindet aus der Liste. Die Messdatei bleibt im Ordner "
            f"„{pfad.parent.name}“ liegen und lässt sich in praxis_gui weiter öffnen."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Entfernen", on_click=entfernen),
        ],
    )

    z = geladen.z
    rec = z.rec
    gespeicherte_regeln = geladen.gespeicherte_regeln
    sidecar_alt = geladen.sidecar_alt
    zeilen_achse, eigene = geladen.zeilen_achse, geladen.eigene
    nach_datei = geladen.nach_datei
    verworfen = ppi_verworfen(rec)
    verity = rec.ppi_pakete is not None
    einst = state.hrv_einstellungen()
    zuschneidbar = not z.nur_puls
    #: Auswahl und Regeln beim Öffnen bzw. beim letzten Speichern. Zurück speichert nur,
    #: was seither geändert wurde — ohne Sidecar gilt schon die Vorauswahl als
    #: ungespeichert, die schreibt Zurück nicht ungefragt.
    bezug = [(frozenset(z.uebernommen), z.regeln)]

    def ungespeichert_geaendert() -> bool:
        """Gibt es etwas, das Zurück speichern soll (Autosave, Ben 16.10.2026)?"""
        hier = (frozenset(z.uebernommen), z.regeln) != bezug[0]
        return hier and z.geaendert(gespeicherte_regeln)

    dauer = max((t for t, _ in (z.puls_punkte if z.nur_puls else z.roh_punkte)), default=0.0)
    start_breite = START_BREITE_S if dauer > START_BREITE_S else 0
    fenster = (
        Fenster(float(start_breite), float(start_breite))
        if start_breite
        else Fenster(dauer or 1.0, None)
    )
    zeitbezug = Zeitbezug(lambda: rec.beats, rec.start_utc, achse=lambda: zeilen_achse)

    kopf_text = ft.Text(size=13, opacity=0.8)
    hinweis_text = ft.Text(size=12, color=FARBEN["rot"])
    sidecar_text = ft.Text(
        "Die gespeicherten Korrekturen und Abschnitte gehören zu einer anderen oder "
        "nachträglich veränderten Messdatei — sie gelten hier nicht. Speichern ersetzt sie.",
        size=12,
        color=FARBEN["rot"],
        visible=sidecar_alt,
    )
    titel_box = ft.Container()
    # Die Datei ist die Wahrheit — die Zeile hält nur Kopien für die Liste
    if rec.titel != eintrag.title:
        state.hrv.titel_setzen(eintrag.id, rec.titel)
    beschreibung = rec.notiz or eintrag.note
    kacheln_box = ft.Container()
    rr_box = ft.Container()
    ketten_box = ft.Column(spacing=0)
    breite_wahl = ft.SegmentedButton(
        selected=[str(start_breite)],
        # Ein Abschnitt kann jede Breite haben — dann ist keine Taste gewählt
        allow_empty_selection=True,
        show_selected_icon=False,
        expand=True,
        segments=[ft.Segment(value=str(s), label=ft.Text(t)) for s, t in BREITEN],
    )
    breite_wahl_voll = ft.SegmentedButton(  # dieselbe Wahl in der Kopfzeile des Vollbilds
        selected=[str(start_breite)],
        allow_empty_selection=True,
        show_selected_icon=False,
        style=ft.ButtonStyle(
            visual_density=ft.VisualDensity.COMPACT, padding=ft.Padding.symmetric(horizontal=6)
        ),
        segments=[ft.Segment(value=str(s), label=ft.Text(t, size=12)) for s, t in BREITEN],
    )
    speichern_knopf = ft.FilledButton("Korrektur speichern", icon=ft.Icons.SAVE, disabled=True)
    #: Die fertige Ansicht — beim ersten `zeichnen` gibt es sie noch nicht
    gebaut: list[ft.View] = []

    # -- Kennzahlen der ganzen Messung (korrigiert) --------------------------------

    def zeitbereich(korrigiert: bool) -> dict[str, Any] | None:
        """Ø HF, Ø RR, RMSSD, SDNN, pNNx — roh oder korrigiert, Nähte übersprungen."""
        korr = z.analyse_korr(roh=not korrigiert)
        return compute_time_domain(
            korr.rr_ms, pnn_threshold_ms=state.ansicht().pnn_ms, breaks=korr.breaks
        )

    def frequenz() -> dict[str, Any] | None:
        korr = z.analyse_korr()
        return z.merken("frequenz", lambda: frequenzbereich(korr.rr_ms, korr.t_s, korr.breaks))

    def nichtlinear() -> dict[str, Any]:
        def rechnen() -> dict[str, Any]:
            korr = z.analyse_korr()
            valide = filter_rr(korr.rr_ms)
            poincare = compute_poincare(korr.rr_ms, korr.breaks) or {}
            dfa = (
                compute_dfa_alpha1(valide, window_n=int(valide.size))
                if valide.size >= DFA_MIN_SCHLAEGE
                else None
            )
            # SampEn ist quadratisch — über sehr lange Messungen zu teuer
            sampen = compute_sampen(valide) if valide.size <= 3000 else None
            return {
                **poincare,
                "dfa_alpha1": dfa["dfa_alpha1"] if dfa else None,
                "sampen": sampen,
                "n": int(valide.size),
            }

        return z.merken("nichtlinear", rechnen)

    def atmung() -> dict[str, Any]:
        """Atemfrequenz der ganzen Messung: Median der gültigen 60-s-Fenster."""

        def rechnen() -> dict[str, Any]:
            t, rr, _ = analyse_reihe()
            modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
            # Alle 15 s ein Minutenfenster — über Stunden höchstens 2000 Fenster
            schritt = max(15.0, float(t[-1] - t[0]) / 2000.0) if t.size else 15.0
            fenster = [
                atemfrequenz(t, rr, ende - 60.0, ende, modus=modus)
                for ende in (np.arange(t[0] + 60.0, t[-1] + 1e-9, schritt) if t.size else [])
            ]
            gueltig = [a for a in fenster if a.gueltig]
            gruende = Counter(g for a in fenster if not a.gueltig for g in a.gruende[:1])
            return {
                "rate": float(np.median([a.rate_pro_min for a in gueltig])) if gueltig else None,
                "rsa": float(np.median([a.rsa_bpm for a in gueltig])) if gueltig else None,
                "gueltig": len(gueltig),
                "fenster": len(fenster),
                "grund": kurzgrund([gruende.most_common(1)[0][0]]) if gruende else "",
            }

        return z.merken(
            "atmung" + ("_uebung" if state.hrv_einstellungen().atemuebung else ""), rechnen
        )

    def kachel_werte() -> list[KachelWert]:
        """Dieselben Werte wie live, für die ganze Messung."""
        a = state.ansicht()
        td = zeitbereich(True) or {}
        korr = z.korrigiert()
        gross = set(einst.gross)
        out: list[KachelWert] = []
        for key in einst.kacheln:
            art = KACHELN.get(key)
            if art is None or key == "schwankung":
                continue
            g = key in gross
            bisher = len(out)
            if key == "hf":
                mittel = td.get("mean_bpm")
                if mittel is None and z.puls_punkte:  # nur Puls: aus den Werten des Geräts
                    mittel = sum(h for _, h in z.puls_punkte) / len(z.puls_punkte)
                out.append(KachelWert("Ø Herzfrequenz", zahl(mittel), "bpm", gross=g))
            elif key == "rr":
                titel_rr = "Ø PPI" if verity else "Ø RR"
                out.append(KachelWert(titel_rr, zahl(td.get("mean_rr")), "ms", gross=g))
            elif key == "ulf":
                f = frequenz() or {}
                gesperrt = f.get("band_status", {}).get("ulf") not in (None, BAND_OK)
                out.append(
                    KachelWert(
                        art.titel,
                        zahl(f.get("ulf"), 0),
                        "ms²",
                        gross=g,
                        grund="braucht 4 h Messung" if gesperrt else "",
                    )
                )
            elif key == "artefakte":
                out.append(
                    KachelWert(
                        "Korrigiert",
                        str(korr.interpoliert + korr.entfernt),
                        zusatz=f"von {len(rec.beats)}",
                        gross=g,
                    )
                )
            elif key in ("atemfrequenz", "rsa"):
                at = atmung()
                kz = KENNZAHLEN[key]
                wert = at["rate"] if key == "atemfrequenz" else at["rsa"]
                hinweis_atmung = (
                    f"{at['gueltig']} von {at['fenster']} Minutenfenstern deutlich"
                    if at["gueltig"]
                    else at["grund"]
                )
                out.append(
                    KachelWert(
                        kz.titel,
                        zahl(wert, kz.nachkomma),
                        kz.einheit,
                        farbe=FARBEN[key],
                        gross=g,
                        grund=hinweis_atmung if key == "atemfrequenz" else "",
                    )
                )
            elif art.kennzahl is not None:
                k = art.kennzahl
                kz = KENNZAHLEN[k]
                out.append(
                    KachelWert(
                        titel(k, a.pnn_ms),
                        *_gesamtwert(k, td, frequenz, nichtlinear, kz.nachkomma),
                        farbe=FARBEN[k],
                        gross=g,
                    )
                )
            # Ohne Intervalle: der Grund statt „zu wenige gute Schläge“ (Ben, 17.10.2026)
            if z.nur_puls and key not in PULS_KACHELN and len(out) > bisher:
                out[-1] = ohne_intervalle(out[-1])
        return out

    def tabelle(bereich: str) -> ft.Control | None:
        if z.nur_puls:
            return None  # ohne Intervalle stünden dort nur Striche
        if bereich == "frequenz":
            return _frequenz_tabelle(frequenz())
        if bereich == "nichtlinear":
            return _nichtlinear_tabelle(nichtlinear(), verity)
        return _zeit_tabelle(zeitbereich(False), zeitbereich(True), state.ansicht().pnn_ms)

    def kopf() -> None:
        teile = [
            rec.geraet or eintrag.geraet,
            _uhr(dauer),
            QUALITAET.get(rec.effektive_qualitaet(), rec.effektive_qualitaet()),
            *_verworfen_text(verworfen),
        ]
        if z.basis.aufgenommen:
            teile.append(f"{z.basis.aufgenommen} davon selbst geprüft")
        if z.ausschnitt is not None:
            lo, hi = z.ausschnitt
            teile.append(f"zugeschnitten {_uhr(lo)}–{_uhr(hi)}")
        kopf_text.value = "  ·  ".join(t for t in teile if t)
        # Mehr als die Hälfte verworfen: Folgt man dem Sensor, bleiben Bruchstücke.
        viel = bool(verworfen and verworfen[1] and verworfen[0] * 2 > verworfen[1])
        hinweis_text.visible = viel
        hinweis_text.value = (
            "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung, auch "
            "bei festem Sitz. Sie sind wieder aufgenommen und nach den eigenen Regeln "
            "geprüft. Vorsicht: In Bewegung sind sie meist falsch, RMSSD liegt dann "
            "leicht um ein Mehrfaches zu hoch."
            if z.basis.aufgenommen
            else "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung, "
            "auch bei festem Sitz. Gewertet wird nur, was er sicher gemessen hat; "
            "die Kennzahlen beruhen auf Bruchstücken. Für HRV ruhig sitzen oder "
            "liegen — in Bewegung misst ein Brustgurt (H10) zuverlässig."
        )

    def analyse_reihe() -> tuple[Any, Any, Any]:
        korr = z.korrigiert()

        def rechnen() -> tuple[Any, Any, Any]:
            t, rr, naht = reihe(korr_zeiten(korr, z.achse), korr.rr_ms, korr.breaks)
            if z.ausschnitt is not None:  # Crop: Kurven nur im Ausschnitt
                im = (t >= z.ausschnitt[0]) & (t <= z.ausschnitt[1])
                t, rr, naht = t[im], rr[im], naht[im]
            return t, rr, naht

        return z.merken("reihe", rechnen)

    def hf_geraet() -> list[tuple[float, float]]:
        beats = z.basis.rec.beats
        return [(x, float(b.hf_bpm)) for x, b in zip(z.achse, beats, strict=True) if b.hf_bpm]

    def zeiten_korr() -> list[float]:
        """Zeit je korrigiertem Wert — einmal je Auswahl, nicht bei jedem Neuzeichnen."""
        return z.merken("korr_zeiten", lambda: korr_zeiten(z.korrigiert(), z.achse))

    # -- Modus der Rohkurve: normal · Bereich wählen · Ablesen --------------------
    # Normal blättert Ziehen die Kurve, ein Tipp gehört den Notizen („In Kurve").
    # Mit offenem Bereichseditor (Zuschneiden, Abschnitt) zieht der Finger die
    # Grenze; beim Ablesen den Strich, unter dem alle Werte stehen.

    m = _Kurvenmodus()
    editor_box = ft.Container(visible=False)
    ablese_box = ft.Container(visible=False)
    ablesen_knopf = ft.TextButton(
        "Ablesen",
        icon=ft.Icons.ADS_CLICK,
        tooltip="Werte an einer Stelle der Kurven ablesen",
        on_click=lambda: ablesen_umschalten(),
    )
    ablesen_knopf_voll = werkzeug(  # in der Werkzeugleiste des Vollbilds
        ft.Icons.ADS_CLICK, "Ablesen: Werte an einer Stelle", lambda: ablesen_umschalten()
    )

    def roh_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Das Tachogramm im Ausschnitt: Rohwerte grau, korrigiert farbig, auffällige rot."""
        korr = z.korrigiert()
        markiert = {v.beat_index for k in z.ketten for v in k.vorschlag}
        beats = z.basis.rec.beats
        art = [
            (z.achse[i], float(beats[i].rr_ms))
            for i in sorted(markiert)
            if i < len(beats)
            and ROH_MIN_MS < beats[i].rr_ms < ROH_MAX_MS
            and x_von <= z.achse[i] <= x_bis
        ]
        # Grau reißt nur an Messlücken ab; farbig auch an Nähten und Ausschlüssen —
        # dort gibt es keine Schlag-zu-Schlag-Differenz.
        sichtbar, sichtbar_naehte = _linie(
            z.roh_punkte, z.roh_naehte, ROH_MIN_MS, ROH_MAX_MS, x_von, x_bis
        )
        zeiten = zeiten_korr()
        korr_linie, korr_naehte = _linie(
            zip(zeiten, korr.rr_ms, strict=True), korr.breaks, x_von=x_von, x_bis=x_bis
        )
        return [
            Reihe(sichtbar, farbe=ft.Colors.OUTLINE, breite=1, naehte=sichtbar_naehte, skala=False),
            Reihe(korr_linie, farbe=ft.Colors.PRIMARY, naehte=korr_naehte),
            Reihe(art, farbe=FARBEN["rot"], nur_punkte=True, skala=False),
        ]

    def leistungs_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Die Leistungen der Person (Plan D): sanftes Blau, eigene Ebene."""
        xs = notizfeld.positionen(x_von, x_bis, _ist_leistung)
        return [senkrechte(xs, FARBEN["leistung"], 2.0, gestrichelt=False)] if xs else []

    def marken_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Notizen (gelb), Leistungen (blau), Grenzen des Editors und der Ablesestrich — über
        den Kurven; Notizen und Leistungen nur, wenn ihre Ebene eingeblendet ist."""
        strich = m.strich if m.ablesen else None
        return [
            *(notizfeld.marken(x_von, x_bis) if EBENE_NOTIZEN in einst.ebenen else []),
            *(leistungs_reihen(x_von, x_bis) if EBENE_LEISTUNGEN in einst.ebenen else []),
            *(m.editor.reihen(x_von, x_bis) if m.editor is not None else []),
            *(
                [senkrechte([strich], ft.Colors.ON_SURFACE, 1.2, gestrichelt=False)]
                if strich is not None and x_von <= strich <= x_bis
                else []
            ),
        ]

    def kurven(mit_analyse: bool = True) -> None:
        x_von, x_bis = sichtbar()
        hinten = [*bereich_reihen(x_von, x_bis), *band_reihen(x_von, x_bis)]
        if m.vollbild:
            vollbild_kurven(x_von, x_bis, hinten)
            return
        strich = m.strich if m.ablesen else None
        if z.nur_puls:
            puls = [(t, h) for t, h in z.puls_punkte if x_von <= t <= x_bis]
            rr_box.content = kurve(
                [*hinten, Reihe(puls, farbe=ft.Colors.PRIMARY), *marken_reihen(x_von, x_bis)],
                einheit="HF bpm",
                hoehe=220,
                x_von=x_von,
                x_bis=x_bis,
                y_spanne_min=HF_SPANNE_MIN_BPM,
                x_text=achse_text,
            )
        else:
            rr_box.content = kurve(
                [*hinten, *roh_reihen(x_von, x_bis), *marken_reihen(x_von, x_bis)],
                einheit="PPI ms" if verity else "RR ms",
                hoehe=220,
                x_von=x_von,
                x_bis=x_bis,
                y_spanne_min=RR_SPANNE_MIN_MS,
                x_text=achse_text,
            )
        if mit_analyse:
            analyse.zeichnen(x_von, x_bis, strich=strich)
            if strich is not None:
                ablesen_zeichnen()

    def ebenen() -> dict[str, int]:
        """Ebene je Abschnitt: übereinander, wo sie sich decken (0 = oben)."""
        out: dict[str, int] = {}
        enden: list[float] = []  # Ende des letzten Balkens je Ebene
        for a in sorted(eigene, key=lambda a: a.von_s):
            ebene = next((i for i, ende in enumerate(enden) if a.von_s >= ende), len(enden))
            if ebene == len(enden):
                enden.append(a.bis_s)
            enden[ebene] = a.bis_s
            out[a.id] = ebene
        return out

    def bereich_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Zuschnitt grau schattiert, Abschnitte als Balken oben — gestapelt, wo sie sich decken."""
        out: list[Reihe] = []
        if z.ausschnitt is not None and m.art != CROP:
            lo, hi = z.ausschnitt
            grau = ft.Colors.with_opacity(0.14, ft.Colors.ON_SURFACE)
            if lo > x_von:
                out.append(schatten(x_von, min(lo, x_bis), grau))
            if hi < x_bis:
                out.append(schatten(max(hi, x_von), x_bis, grau))
        bearbeitet = m.abschnitt.id if m.abschnitt is not None else None
        # Der Balken im Editor liegt oben — die übrigen rücken eine Ebene tiefer
        versatz = 1 if m.art == ABSCHNITT else 0
        lagen = ebenen()
        balken_an = EBENE_ABSCHNITTE in einst.ebenen or m.art == ABSCHNITT
        for a in sorted(eigene, key=lambda a: a.von_s):
            if a.id == bearbeitet or a.bis_s < x_von or a.von_s > x_bis:
                continue
            if not balken_an and (m.bindung is None or a.id != m.bindung.id):
                continue
            balken = band(max(a.von_s, x_von), min(a.bis_s, x_bis), a.farbe)
            balken.ebene = min(lagen[a.id] + versatz, 3)
            out.append(balken)
        return out

    def abschnitt_unter(x: float, y: float) -> Abschnitt | None:
        """Der Abschnittsbalken unter dem Finger (``y`` px von oben) — die Balken liegen oben."""
        flaeche = max(m.hoehe - ZEITACHSE_PX, 1.0)
        toleranz = max(14.0, 0.05 * flaeche)
        lagen = ebenen()
        treffer = [
            (abs(y - (0.04 + 0.06 * min(lagen[a.id], 3)) * flaeche), a)
            for a in eigene
            if a.von_s <= x <= a.bis_s
        ]
        nah = [(d, a) for d, a in treffer if d <= toleranz]
        return min(nah, key=lambda t: t[0])[1] if nah else None

    def kurve_tippen(x: float) -> None:
        if m.editor is not None:
            m.editor.tippen(x)
        elif m.ablesen:
            strich_setzen(x)
        else:
            notizfeld.tippen(x)

    def kurve_tippen_punkt(x: float, y: float) -> None:
        """Vollbild: Ein Tipp auf eine Marke oder einen Balken zeigt dessen Etikett."""
        if m.editor is not None or m.ablesen or notizfeld.waehlen:
            kurve_tippen(x)
            return
        i = notizfeld.bei(x)
        a = abschnitt_unter(x, y) if i is None else None
        m.etikett = ("notiz", i) if i is not None else ("abschnitt", a.id) if a else None
        nur_kurven(mit_analyse=False)

    def kurve_greifen(x: float) -> bool:
        if m.editor is not None:
            return m.editor.ziehen(x)
        if m.ablesen:
            strich_setzen(x, zeichnen=False)
            return True
        if notizfeld.greifen(x):  # eine Marke unterm Finger folgt ihm
            m.etikett = None  # die Liste ordnet sich gleich neu
            return True
        return band_greifen(x)

    def analyse_tippen(x: float) -> None:
        if m.ablesen:
            strich_setzen(x)

    def analyse_greifen(x: float) -> bool:
        if not m.ablesen:
            return False
        strich_setzen(x, zeichnen=False)
        return True

    # -- Ablesen ---------------------------------------------------------------------

    def ablesen_umschalten() -> None:
        m.ablesen = not m.ablesen
        m.etikett = None  # die Ablesewerte stehen, wo sonst das Etikett stünde
        if m.ablesen and m.strich is None:
            m.strich = sum(sichtbar()) / 2
        if m.ablesen:
            m.strich = schlag_bei(m.strich or 0.0)
        for knopf in (ablesen_knopf, ablesen_knopf_voll):
            knopf.style = (
                ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY))
                if m.ablesen
                else None
            )
        ablese_box.visible = m.ablesen
        nur_kurven()

    def naechster(zeiten: Sequence[float], x: float) -> int:
        """Index der Zeit, die ``x`` am nächsten liegt (``zeiten`` aufsteigend)."""
        i = bisect_left(zeiten, x)
        if i <= 0:
            return 0
        if i >= len(zeiten):
            return len(zeiten) - 1
        return i if zeiten[i] - x < x - zeiten[i - 1] else i - 1

    def schlag_bei(x: float) -> float:
        """Der korrigierte Schlag, der ``x`` am nächsten liegt — dort steht der Strich."""
        zeiten = zeiten_korr()
        if not zeiten:
            return x
        return float(zeiten[naechster(zeiten, x)])

    def strich_setzen(x: float, *, zeichnen: bool = True) -> None:
        m.strich = schlag_bei(min(max(x, 0.0), dauer))
        if zeichnen:
            nur_kurven()

    def strich_schritt(richtung: int) -> None:
        """Ein Schlag vor oder zurück; die Kurve rückt mit, wenn der Strich hinausläuft."""
        zeiten = zeiten_korr()
        jetzt = m.strich
        if not zeiten or jetzt is None:
            return
        i = naechster(zeiten, jetzt)
        m.strich = float(zeiten[min(max(i + richtung, 0), len(zeiten) - 1)])
        x_von, x_bis = sichtbar()
        if not x_von <= m.strich <= x_bis:
            zentrieren(m.strich)
        nur_kurven()

    def ablesen_zeichnen() -> None:
        """Die Werte am Strich — hochkant unter der Kurve, im Vollbild über ihr."""
        x = m.strich
        if x is None:
            return
        korr = z.korrigiert()
        zeiten = zeiten_korr()
        werte: list[tuple[str | None, str, str, str]] = []
        # Nur Puls: kein Intervall, das sich ablesen ließe — nur „HF Gerät“ (Ben, 17.10.)
        if zeiten and not z.nur_puls:
            i = naechster(zeiten, x)
            rr = korr.rr_ms[i]
            zusatz = " (interpoliert)" if korr.flag[i] != "orig" else ""
            werte.append(
                (ft.Colors.PRIMARY, "RR" if not verity else "PPI", zahl(rr), "ms" + zusatz)
            )
            werte.append((FARBEN["hf_rr"], "HF", zahl(60000 / rr if rr else None), "bpm"))
        roh = min(z.roh_punkte, key=lambda p: abs(p[0] - x), default=None)
        if roh is not None and abs(roh[0] - x) < 3 and not z.nur_puls:
            werte.append((ft.Colors.OUTLINE, "roh", zahl(roh[1]), "ms"))
        geraet = min(hf_geraet(), key=lambda p: abs(p[0] - x), default=None)
        if geraet is not None and abs(geraet[0] - x) < 3:
            werte.append((FARBEN["hf_geraet"], "HF Gerät", zahl(geraet[1]), "bpm"))
        for k, name, wert in werte_bei(m.gesehen if m.vollbild else analyse.gesehen, x):
            kz = KENNZAHLEN[k]
            stellen = 0 if abs(wert) >= 100 else 1 if abs(wert) >= 10 else 2
            werte.append((FARBEN.get(k), name, zahl(wert, stellen), kz.einheit))
        in_abschnitten = [a.name for a in eigene if a.von_s <= x <= a.bis_s]
        uhr = zeitbezug.uhr(zeitbezug.anker(x))
        kopfzeile = f"{_uhr(x)}" + (f" · {uhr} Uhr" if uhr else "")
        ablese_box.content = ablese_karte(
            kopfzeile,
            " · ".join(in_abschnitten),
            werte,
            schritt=strich_schritt,
            schliessen=ablesen_umschalten,
            schwebend=m.vollbild,
        )
        if m.vollbild:
            ablese_seite(ablese_box, x, *sichtbar(), m.rechts)

    # -- Abschnitte (Werte je Teil der Messung) ---------------------------------

    abschnitte_box = ft.Column(spacing=2)

    def notiz_punkte() -> list[tuple[float, str]]:
        punkte = []
        for e in rec.ereignisse:
            x = zeitbezug.x(e)
            if x is not None:
                punkte.append((x, str(e.get("text") or "Notiz")))
        return sorted(punkte)

    def grenzen() -> tuple[float, float]:
        return z.ausschnitt if z.ausschnitt is not None else (0.0, dauer)

    def werte_von(a: Abschnitt) -> dict[str, Any]:
        lo, hi = grenzen()
        von, bis = max(a.von_s, lo), min(a.bis_s, hi)
        korr = z.korrigiert()
        pnn_ms = state.ansicht().pnn_ms
        atem_modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
        return z.merken(
            f"abschnitt:{a.id}:{von:.3f}:{bis:.3f}:{pnn_ms:g}:{atem_modus}:{int(einst.frequenz)}",
            lambda: abschnitt_werte(
                korr,
                korr_zeiten(korr, z.achse),
                von,
                bis,
                pnn_ms=pnn_ms,
                frequenz=einst.frequenz,
                atem_modus=atem_modus,
            ),
        )

    def abschnitt_teile(a: Abschnitt) -> list[str]:
        """„Ø HF 72", „RMSSD 35" … — die Werte eines Abschnitts in Kurzform."""
        w = werte_von(a)
        teile = [f"Ø HF {zahl(w['mean_bpm'])}", f"RMSSD {zahl(w['rmssd'])}"]
        teile.append(f"SDNN {zahl(w['sdnn'])}")
        if w["atem"] is not None:
            teile.append(f"Atem {zahl(w['atem'], 1)}/min")
        if w["lf_hf"] is not None:
            teile.append(f"LF/HF {zahl(w['lf_hf'], 2)}")
        return teile

    def abschnitt_zeile(a: Abschnitt) -> ft.Control:
        teile = abschnitt_teile(a)
        return ft.Container(
            on_click=lambda: abschnitt_bearbeiten(a),
            border_radius=8,
            padding=ft.Padding.only(left=0, right=0, top=2, bottom=2),
            bgcolor=(
                ft.Colors.with_opacity(0.08, a.farbe)
                if m.abschnitt is not None and m.abschnitt.id == a.id
                else None
            ),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=4, height=36, border_radius=2, bgcolor=a.farbe),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, max_lines=1),
                            ft.Text(
                                f"{_uhr(a.von_s)}–{_uhr(a.bis_s)} ({_uhr(a.dauer_s)})  ·  "
                                + "  ·  ".join(teile),
                                size=12,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=18,
                        tooltip="Abschnitt löschen",
                        on_click=lambda: abschnitt_loeschen(a),
                    ),
                ],
            ),
        )

    def abschnitte_zeichnen() -> None:
        if eigene:
            abschnitte_box.controls = [
                abschnitt_zeile(a) for a in sorted(eigene, key=lambda a: a.von_s)
            ]
        else:
            abschnitte_box.controls = [hinweis("Noch keine Abschnitte.")]  # wie: hinter dem „i“
        chips_zeichnen()

    def zusatz_sichern() -> None:
        """Crop und Abschnitte ins Sidecar — ein Thread schreibt den Stand von jetzt (H39)."""
        ausschnitt, liste = z.ausschnitt, [replace(a) for a in eigene]

        async def schreiben() -> None:
            try:
                async with sperre:
                    await asyncio.to_thread(zusatz_speichern, pfad, ausschnitt, liste, nach_datei)
            except (OSError, SidecarFehler) as fehler:
                page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))

        page.run_task(schreiben)

    def abschnitt_loeschen(a: Abschnitt) -> None:
        vorher = list(eigene)
        eigene[:] = [b for b in eigene if b.id != a.id]
        if m.abschnitt is not None and m.abschnitt.id == a.id:
            editor_schliessen(zeichnen_=False)
        zusatz_sichern()
        zeichnen()

        def zurueck() -> None:
            eigene[:] = vorher
            zusatz_sichern()
            zeichnen()

        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"„{a.name}“ gelöscht"),
                action=ft.SnackBarAction("Rückgängig", on_click=zurueck),
            )
        )

    def alle_loeschen() -> None:
        if not eigene:
            return
        vorher = list(eigene)
        eigene.clear()
        editor_schliessen(zeichnen_=False)
        zusatz_sichern()
        zeichnen()

        def zurueck() -> None:
            eigene[:] = vorher
            zusatz_sichern()
            zeichnen()

        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    "1 Abschnitt gelöscht"
                    if len(vorher) == 1
                    else f"{len(vorher)} Abschnitte gelöscht"
                ),
                action=ft.SnackBarAction("Rückgängig", on_click=zurueck),
            )
        )

    def abschnitt_menue() -> ft.Control:
        """⋮ neben „+ Abschnitt": aus Notizen anlegen, alle löschen (hochkant und im Vollbild)."""
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            tooltip="Mehr",
            items=[
                ft.PopupMenuItem(
                    content="Aus Notizen …",
                    icon=ft.Icons.NOTES,
                    on_click=lambda: aus_notizen_oeffnen(),
                ),
                ft.PopupMenuItem(
                    content="Alle löschen",
                    icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                    on_click=lambda: alle_loeschen(),
                ),
            ],
        )

    def aus_notizen_oeffnen() -> None:
        """Notizen zu Abschnittsgrenzen machen — welche, entscheidet man selbst."""
        lo, hi = grenzen()
        notizen = [(x, t) for x, t in notiz_punkte() if lo <= x <= hi]
        if not notizen:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Notizen in der Messung.")))
            return
        haken = [ft.Checkbox(value=True) for _ in notizen]
        vorschau = ft.Text(size=13, weight=ft.FontWeight.W_600)

        def grenzen_aus_haken() -> list[Grenze]:
            return [
                Grenze(x, abschnittsname(t), schluss=t.strip() == ENDE_MARKE)
                for (x, t), h in zip(notizen, haken, strict=True)
                if h.value
            ]

        def vorschau_zeichnen() -> None:
            n = len(aus_grenzen(grenzen_aus_haken(), lo, hi))
            vorschau.value = f"Ergibt {n} {'Abschnitt' if n == 1 else 'Abschnitte'}"

        def umgeschaltet() -> None:
            vorschau_zeichnen()
            vorschau.update()

        def alle(an: bool) -> None:
            for h in haken:
                h.value = an
            vorschau_zeichnen()
            page.update()

        blatt: ft.BottomSheet

        def anlegen() -> None:
            neu = aus_grenzen(grenzen_aus_haken(), lo, hi)
            farben_nach_namen(neu, vergeben=len(eigene))
            eigene.extend(neu)
            zusatz_sichern()
            schliessen(blatt)  # nicht `pop_dialog`: eine Fehler-SnackBar läge sonst oben (N18)
            zeichnen()

        for h in haken:
            h.on_change = lambda _: umgeschaltet()
        vorschau_zeichnen()
        zeilen = [
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    h,
                    ft.Text(_uhr(x), size=12, opacity=0.7, width=44),
                    ft.Text(t, size=13, expand=True, max_lines=2),
                ],
            )
            for (x, t), h in zip(notizen, haken, strict=True)
        ]
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            content=ft.Container(
                padding=ft.Padding.only(left=16, right=16, bottom=16),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Text("Abschnitte aus Notizen", size=18, weight=ft.FontWeight.W_600),
                        ft.Text(
                            "Jede gewählte Notiz beginnt einen Abschnitt, benannt nach "
                            "ihr; er reicht bis zur nächsten gewählten. „Timer fertig“ "
                            "beendet nur. Notizen, die mitten in einer Übung stehen, "
                            "einfach abwählen.",
                            size=12,
                            opacity=0.7,
                        ),
                        ft.Row(
                            controls=[
                                ft.TextButton("Alle", on_click=lambda: alle(True)),
                                ft.TextButton("Keine", on_click=lambda: alle(False)),
                            ]
                        ),
                        *zeilen,
                        vorschau,
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
                                ft.FilledButton("Anlegen", icon=ft.Icons.ADD, on_click=anlegen),
                            ],
                        ),
                    ],
                ),
            ),
        )
        page.show_dialog(blatt)

    # -- Bereich wählen: Zuschneiden und Abschnitte ----------------------------------

    def editor_oeffnen(art: str, von: float, bis: float, abschnitt: Abschnitt | None) -> None:
        lo, hi = (0.0, dauer) if art == CROP else grenzen()
        farbe = (
            abschnitt.farbe
            if abschnitt is not None
            else (
                ft.Colors.PRIMARY
                if art == CROP
                else ABSCHNITT_FARBEN[len(eigene) % len(ABSCHNITT_FARBEN)]
            )
        )
        if m.ablesen:
            ablesen_umschalten()
        m.art, m.abschnitt = art, abschnitt
        m.editor = BereichEditor(
            von=von,
            bis=bis,
            anfang=lo,
            ende=hi,
            notizen=notiz_punkte,
            geaendert=lambda: nur_kurven(mit_analyse=False),
            zeigen=zentrieren_und_zeichnen,
            breite=lambda: fenster.breite_s,
            farbe=farbe,
            schattieren=art == CROP,
        )
        name = ft.TextField(
            label="Name",
            value=abschnitt.name if abschnitt is not None else name_vorschlag(von),
            dense=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )
        m.name_feld = name if art == ABSCHNITT else None
        if art == CROP:
            ueberschrift = "Zuschneiden"
            erklaerung = (
                "Anfang oder Ende wählen, dann in die Kurve tippen oder ziehen. Grau zählt "
                "nicht — für keine Kennzahl. Die Rohdatei bleibt unverändert; praxis_gui "
                "zeigt den Zuschnitt ebenso."
            )
            knoepfe: list[ft.Control] = [
                ft.TextButton("Ganze Messung", on_click=lambda: crop_setzen(None)),
                ft.TextButton("Abbrechen", on_click=lambda: editor_schliessen()),
                ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=crop_uebernehmen),
            ]
        else:
            ueberschrift = "Abschnitt" if abschnitt is not None else "Neuer Abschnitt"
            erklaerung = (
                "Anfang oder Ende wählen, dann in die Kurve tippen oder ziehen — Notizen "
                "ziehen die Grenze an, die Stecknadel setzt sie genau auf eine."
            )
            knoepfe = [
                *(
                    [
                        ft.TextButton(
                            "Löschen",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda: abschnitt_loeschen(abschnitt),
                        )
                    ]
                    if abschnitt is not None
                    else []
                ),
                ft.TextButton("Abbrechen", on_click=lambda: editor_schliessen()),
                ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=abschnitt_sichern),
            ]
        editor_box.content = ft.Container(
            border_radius=10,
            padding=ft.Padding.only(left=10, right=4, top=4, bottom=8),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, farbe)),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                ueberschrift.upper(),
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                opacity=0.7,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=18,
                                tooltip="Schließen",
                                on_click=lambda: editor_schliessen(),
                            ),
                        ],
                    ),
                    *([name] if art == ABSCHNITT else []),
                    m.editor.control,
                    ft.Text(erklaerung, size=12, opacity=0.65),
                    ft.Row(
                        spacing=4,
                        wrap=True,
                        alignment=ft.MainAxisAlignment.END,
                        controls=knoepfe,
                    ),
                ],
            ),
        )
        editor_box.visible = True
        zeichnen()

    def name_vorschlag(von: float) -> str:
        """Die Notiz an der Anfangsgrenze, sonst „Abschnitt n"."""
        notiz = next((t for x, t in notiz_punkte() if abs(x - von) < 0.5), "")
        return abschnittsname(notiz) if notiz else f"Abschnitt {len(eigene) + 1}"

    def editor_schliessen(*, zeichnen_: bool = True) -> None:
        m.editor, m.art, m.abschnitt, m.name_feld = None, "", None, None
        editor_box.visible = False
        editor_box.content = None
        if zeichnen_:
            zeichnen()

    def crop_oeffnen() -> None:
        """Zuschneiden in der Rohkurve — zeigt dafür die ganze Messung."""
        lo, hi = z.ausschnitt or (0.0, dauer)
        breite_setzen(0, zeichnen_=False)  # „Alles": beide Grenzen im Blick; der Editor zeichnet
        editor_oeffnen(CROP, lo, hi, None)

    def crop_setzen(neu: tuple[float, float] | None) -> None:
        z.ausschnitt = neu
        zusatz_sichern()
        editor_schliessen(zeichnen_=False)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    "Zugeschnitten — Kennzahlen nur aus diesem Bereich, die Rohdatei bleibt."
                    if neu
                    else "Wieder die ganze Messung."
                )
            )
        )
        zeichnen()

    def crop_uebernehmen() -> None:
        e = m.editor
        if e is None:
            return
        ganz = e.von <= 0.5 and e.bis >= dauer - 0.5
        crop_setzen(None if ganz or e.bis - e.von < 10 else (e.von, e.bis))

    def abschnitt_neu() -> None:
        """Neuer Abschnitt: der sichtbare Bereich, Grenzen rasten an nahen Notizen ein."""
        x_von, x_bis = sichtbar()
        lo, hi = grenzen()
        punkte = [x for x, _ in notiz_punkte()]
        rand = 0.1 * (x_bis - x_von)
        toleranz = max(2.0, 0.05 * (x_bis - x_von))
        von = max(einrasten(x_von + rand, punkte, toleranz), lo)
        bis = min(einrasten(x_bis - rand, punkte, toleranz), hi)
        if bis - von < 5:
            page.show_dialog(ft.SnackBar(ft.Text("Der sichtbare Bereich ist zu kurz.")))
            return
        editor_oeffnen(ABSCHNITT, von, bis, None)

    def abschnitt_bearbeiten(a: Abschnitt) -> None:
        breite_setzen(max(a.dauer_s * 1.4, 30.0), (a.von_s + a.bis_s) / 2)
        editor_oeffnen(ABSCHNITT, a.von_s, a.bis_s, a)

    def abschnitt_sichern() -> None:
        e = m.editor
        if e is None:
            return
        name = ((m.name_feld.value if m.name_feld else "") or "").strip()
        if m.abschnitt is not None:
            m.abschnitt.name = name or m.abschnitt.name
            m.abschnitt.von_s, m.abschnitt.bis_s = e.von, e.bis
        else:
            eigene.append(
                Abschnitt(name or f"Abschnitt {len(eigene) + 1}", e.von, e.bis, farbe=e.farbe)
            )
        zusatz_sichern()
        editor_schliessen()

    def zeichnen(aktualisieren: bool = True) -> None:
        kopf()
        abschnitte_zeichnen()
        kacheln_box.content = anzeige(kachel_werte(), einst.darstellung)
        analyse.aufbauen()
        kurven()
        ketten_box.controls = [ketten_zeile(i, k) for i, k in enumerate(z.ketten)] or [
            ft.Text("Keine Auffälligkeiten gefunden.", opacity=0.7)
        ]
        speichern_knopf.disabled = not z.geaendert(gespeicherte_regeln)
        zurueck_pruefen()
        if aktualisieren:
            page.update()

    def kann_zurueck() -> bool:
        """Nichts Ungespeichertes: keine geänderte Korrektur, kein offener Editor (H34)."""
        return not ungespeichert_geaendert() and m.editor is None

    def zurueck_pruefen() -> None:
        """Ungespeicherte Korrektur oder offener Editor: Zurück speichert erst
        (`zurueck_im_vollbild`)."""
        if gebaut and not m.vollbild:
            gebaut[0].can_pop = kann_zurueck()

    def nur_kurven(mit_analyse: bool = True) -> None:
        kurven(mit_analyse)
        page.update()

    def wisch_zeichnen(mit_analyse: bool = True) -> None:
        """Beim Wischen und Ziehen: nur Rohkurve und Analyse aktualisieren, nicht die Seite.

        Wird das Band gezogen, ändert sich an der Analyse nichts — sie rechnet
        erst nach dem Loslassen. Im Vollbild gibt es keine Analyse, dafür
        wandern Etikett und Ablesewerte mit.
        """
        mit_analyse = mit_analyse and aw.griff is None and not m.vollbild
        kurven(mit_analyse)
        geaendert: list[ft.Control] = [rr_box]
        if m.vollbild:
            geaendert += [etikett_box, ablese_box]
        elif mit_analyse:
            geaendert.append(analyse.control)
            if ablese_box.visible:
                geaendert.append(ablese_box)
        for c in geaendert:
            with contextlib.suppress(Exception):
                c.update()

    # -- Zeitfenster -------------------------------------------------------------
    # Die Achse ist entweder die ganze Messung oder an einen Abschnitt gebunden (Plan F):
    # dann beginnt sie bei seinem Anfang (mit Rand), endet an seinem Ende, und die
    # Beschriftung zählt ab Abschnittsbeginn.

    def achse_anfang() -> float:
        return max(m.bindung.von_s - RAND_S, 0.0) if m.bindung is not None else 0.0

    def achse_ende() -> float:
        return min(m.bindung.bis_s + RAND_S, dauer) if m.bindung is not None else dauer

    def sichtbar() -> tuple[float, float]:
        return fenster.bereich(achse_ende(), achse_anfang())

    def achse_text(sekunden: float) -> str:
        if m.bindung is None:
            return _uhr(sekunden) if sekunden >= 60 else f"{int(sekunden)}s"
        rel = sekunden - m.bindung.von_s
        text = _uhr(abs(rel)) if abs(rel) >= 60 else f"{int(abs(rel))}s"
        return f"-{text}" if rel < 0 else text

    def breite_setzen(
        breite_s: float, mitte: float | None = None, *, zeichnen_: bool = True
    ) -> None:
        fenster.breite_s = breite_s if breite_s > 0 else (dauer or 1.0)
        if mitte is None and m.editor is not None:
            mitte = m.editor.grenze  # im Editor zoomt man auf die gewählte Grenze
        if mitte is None:
            fenster.ende_s = None if breite_s <= 0 else fenster.ende_s
        else:
            fenster.ende_s = None
            fenster.verschieben(
                mitte + fenster.breite_s / 2 - achse_ende(), achse_ende(), achse_anfang()
            )
        for wahl in (breite_wahl, breite_wahl_voll):
            wahl.selected = [str(int(breite_s))] if breite_s in dict(BREITEN) else []
        if zeichnen_:
            nur_kurven()

    def zentrieren(x: float) -> None:
        """Die Kurve auf eine Zeit rücken (Notiz antippen); bei „Alles" bleibt sie."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - achse_ende(), achse_ende(), achse_anfang())

    def zoom_auf(von: float, bis: float, *, zeichnen_: bool = True) -> None:
        """Auf einen Ausschnitt zoomen (ein Eintrag, Plan E): das Fenster ist der Ausschnitt,
        das Analysefenster ein Band darauf — die Aufnahme bleibt ein Stück."""
        m.bindung = None
        lo, hi = grenzen()
        von, bis = max(von, lo), min(bis, hi) if hi > lo else bis
        if bis <= von:
            bis = von + 10.0
        fenster.breite_s = bis - von
        fenster.ende_s = None if bis >= dauer - 0.5 else bis
        for wahl in (breite_wahl, breite_wahl_voll):
            wahl.selected = []
        aw.art = AW_BAND
        aw.laenge_s = max(round(bis - von - 2 * RAND_S), 10)
        aw.von = von + RAND_S
        bindung_zeichnen()
        if zeichnen_:
            nachrechnen_planen()
            nur_kurven()

    def binden(a: Abschnitt | None) -> None:
        """Ein Abschnitt-Chip: die Achse an den Abschnitt binden (Plan F) — oder lösen."""
        m.bindung = a
        if a is not None:
            spanne = achse_ende() - achse_anfang()
            if fenster.breite_s >= spanne or fenster.breite_s not in dict(BREITEN):
                fenster.breite_s = spanne
            # am Anfang des Abschnitts beginnen
            fenster.ende_s = min(achse_anfang() + fenster.breite_s, achse_ende())
            if fenster.ende_s >= achse_ende() - 0.5:
                fenster.ende_s = None
            aw.art = AW_ABSCHNITT
            aw.abschnitt_id = a.id
        else:
            # „Ganze Messung“ ersetzt den Knopf „Alles“ (Ben, 19.10.2026): das Fenster ist
            # die ganze Messung, die Achse beginnt wieder bei 0
            fenster.breite_s = dauer or 1.0
            fenster.ende_s = None
            if aw.art == AW_ABSCHNITT:
                aw.art = AW_ALLES
        for wahl in (breite_wahl, breite_wahl_voll):
            wahl.selected = (
                [str(int(fenster.breite_s))] if fenster.breite_s in dict(BREITEN) else []
            )
        bindung_zeichnen()
        chips_zeichnen()
        nachrechnen_planen()
        nur_kurven()

    def blaettern(richtung: int) -> None:
        """‹ ›: um eine Fensterbreite — im gebundenen Abschnitt minutenweise."""
        fenster.verschieben(richtung * fenster.breite_s, achse_ende(), achse_anfang())
        nur_kurven()

    bindung_box = ft.Container(visible=False)
    bindung_voll = ft.Text(size=12, weight=ft.FontWeight.W_600, visible=False)
    chips_box = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)
    chips_voll = ft.Row(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    def bindung_zeichnen() -> None:
        """Die Zeile über der Kurve: welcher Abschnitt, wo das Fenster darin steht."""
        a = m.bindung
        bindung_box.visible = a is not None
        bindung_voll.visible = a is not None
        if a is None:
            bindung_box.content = None
            bindung_voll.value = ""
        else:
            von, bis = sichtbar()
            lage = f"{achse_text(von)}–{achse_text(bis)} von {_uhr(a.bis_s - a.von_s)}"
            bindung_voll.value = f"{a.name} · {lage}"
            bindung_box.content = ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        ft.Icons.CHEVRON_LEFT,
                        tooltip="Eine Fensterbreite zurück",
                        on_click=lambda: blaettern(-1),
                    ),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(a.name, size=13, weight=ft.FontWeight.W_700),
                            ft.Text(
                                f"{_uhr(a.von_s)}–{_uhr(a.bis_s)} · Fenster {lage}",
                                size=11,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.CHEVRON_RIGHT,
                        tooltip="Eine Fensterbreite weiter",
                        on_click=lambda: blaettern(1),
                    ),
                ],
            )
        for c in (bindung_box, bindung_voll):
            with contextlib.suppress(Exception):
                c.update()

    def abschnitt_chip(a: Abschnitt | None, *, klein: bool) -> ft.Control:
        gewaehlt = (
            (m.bindung is None) if a is None else (m.bindung is not None and m.bindung.id == a.id)
        )
        text = "Ganze Messung" if a is None else f"{a.name} {_uhr(a.von_s)}"
        inhalt: list[ft.Control] = []
        if a is not None:
            inhalt.append(ft.Container(width=8, height=8, border_radius=4, bgcolor=a.farbe))
        inhalt.append(
            ft.Text(
                text, size=11 if klein else 12, weight=ft.FontWeight.W_700 if gewaehlt else None
            )
        )
        return ft.Container(
            height=30 if klein else 36,
            padding=ft.Padding.symmetric(horizontal=10),
            border_radius=18,
            ink=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if gewaehlt
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(2, ft.Colors.PRIMARY) if gewaehlt else None,
            on_click=lambda _=None, a=a: binden(a),
            content=ft.Row(
                tight=True,
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=inhalt,
            ),
        )

    def chips_zeichnen() -> None:
        """Die Abschnitt-Chips (Plan F) — Übungen sind Abschnitte, keine Sonderform."""
        geordnet = sorted(eigene, key=lambda a: a.von_s)
        chips_box.controls = [
            abschnitt_chip(None, klein=False),
            *[abschnitt_chip(a, klein=False) for a in geordnet],
        ]
        chips_voll.controls = [
            abschnitt_chip(None, klein=True),
            *[abschnitt_chip(a, klein=True) for a in geordnet],
        ]
        if m.bindung is not None and all(a.id != m.bindung.id for a in eigene):
            m.bindung = None  # der gebundene Abschnitt ist weg
            bindung_zeichnen()
        for c in (chips_box, chips_voll):
            with contextlib.suppress(Exception):
                c.update()

    # -- Ebenen über der Kurve (Plan D) ------------------------------------------

    ebenen_box = ft.Container()
    ebenen_knoepfe_voll: dict[str, ft.IconButton] = {}

    def ebene_umschalten(name: str) -> None:
        aktiv = list(einst.ebenen)
        if name in aktiv:
            aktiv.remove(name)
        else:
            aktiv = [k for k in EBENEN if k in aktiv or k == name]
        einst.ebenen = aktiv
        gespeichert_ = state.hrv_einstellungen()
        gespeichert_.ebenen = list(aktiv)
        state.hrv_einstellungen_setzen(gespeichert_)
        ebenen_zeichnen()
        nur_kurven()

    def ebenen_zeichnen() -> None:
        farben = {
            EBENE_NOTIZEN: FARBEN["notiz"],
            EBENE_LEISTUNGEN: FARBEN["leistung"],
            EBENE_ABSCHNITTE: ft.Colors.PRIMARY,
        }
        chips: list[ft.Control] = []
        for name in EBENEN:
            an = name in einst.ebenen
            chips.append(
                ft.Container(
                    height=32,
                    padding=ft.Padding.symmetric(horizontal=10),
                    border_radius=8,
                    ink=True,
                    bgcolor=ft.Colors.with_opacity(0.25 if an else 0.0, farben[name]),
                    border=None if an else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    on_click=lambda _=None, n=name: ebene_umschalten(n),
                    content=ft.Row(
                        tight=True,
                        spacing=5,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.CHECK if an else ft.Icons.ADD, size=14),
                            ft.Text(
                                EBENEN_TEXT[name],
                                size=12,
                                weight=ft.FontWeight.W_600 if an else None,
                            ),
                        ],
                    ),
                )
            )
        ebenen_box.content = ft.Row(spacing=6, wrap=True, controls=chips)
        for name, knopf in ebenen_knoepfe_voll.items():
            markieren(knopf, name in einst.ebenen)
        for c in (ebenen_box, *ebenen_knoepfe_voll.values()):
            with contextlib.suppress(Exception):
                c.update()

    def zentrieren_und_zeichnen(x: float) -> None:
        """Im Editor: die Kurve zur gewählten Grenze rücken, wenn sie am Rand oder draußen liegt.

        Die Rohkurve zeichnet danach der Editor; die Verlaufskurven ziehen hier mit.
        """
        x_von, x_bis = sichtbar()
        if not x_von + 0.1 * (x_bis - x_von) <= x <= x_bis - 0.1 * (x_bis - x_von):
            zentrieren(x)
            if not m.vollbild:
                analyse.zeichnen(*sichtbar())

    # -- Notizen ---------------------------------------------------------------

    def notizen_speichern(liste: list[dict]) -> None:
        """Als Metadaten in die Messdatei — wie praxis_gui; die Messwerte bleiben.

        Die Ansicht übernimmt die Liste sofort (die nächste Änderung baut darauf auf);
        geschrieben wird in einem Thread, ein Vorgang nach dem anderen (`sperre`, H39).
        """
        rec.ereignisse = list(liste)
        kopie = [dict(e) for e in liste]

        async def schreiben() -> None:
            try:
                async with sperre:
                    sha1 = await asyncio.to_thread(metadaten_schreiben, pfad, ereignisse=kopie)
            except (OSError, ValueError) as fehler:
                page.show_dialog(ft.SnackBar(ft.Text(f"Notiz nicht gespeichert: {fehler}")))
                return
            state.hrv.sha1_setzen(eintrag.id, sha1)  # Datenbank: im Loop

        page.run_task(schreiben)

    def notizen_offen(offen: bool) -> None:
        state.notizen_offen = offen

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lambda: zeitbezug,
        ausblenden=_ist_leistung,
        ereignisse=lambda: list(rec.ereignisse),
        speichern=notizen_speichern,
        neu_zeichnen=nur_kurven,
        zeigen=zentrieren,
        mitte=lambda: sum(sichtbar()) / 2,
        offen=state.notizen_offen,
        offen_merken=notizen_offen,
        uebungen=(lambda: uebungsquellen(state)) if einst.notiz_uebungen else None,
        uebungen_offen=state.notiz_uebungen_offen,
        quelle=state.notiz_uebungen_quelle,
        uebungen_merken=uebungen_merken,
        katalog=(lambda: uebungs_katalog(state)) if einst.notiz_uebungen else None,
        breite=lambda: fenster.breite_s,
    )

    def breite_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            breite_setzen(float(e.control.selected[0]))

    breite_wahl.on_change = breite_gewaehlt
    breite_wahl_voll.on_change = breite_gewaehlt

    # -- Analysefenster: wofür Spektrum, Poincaré und DFA gelten --------------------
    # Die ganze Messung (Vorgabe), ein Abschnitt oder ein Band fester Länge. Das Band
    # greift man in der Rohkurve und schiebt es; gerechnet wird nach dem Loslassen,
    # wenn innerhalb der Latenz (Einstellungen → Erweitert) nichts nachkommt.

    aw = _Analysewahl(
        laenge_s=einst.analyse_laenge_s if einst.analyse_laenge_s in ANALYSE_LAENGEN else 300
    )

    def band_sichtbar() -> bool:
        return aw.art == AW_BAND and analyse.bereich in ("frequenz", "nichtlinear")

    def band_bereich() -> tuple[float, float]:
        lo, hi = grenzen()
        laenge = min(float(aw.laenge_s), hi - lo)
        if aw.von is None:
            aw.von = sum(sichtbar()) / 2 - laenge / 2
        aw.von = min(max(aw.von, lo), hi - laenge)
        return aw.von, aw.von + laenge

    def band_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Das Band in der Rohkurve: getönt, mit Kanten."""
        if not band_sichtbar():
            return []
        von, bis = band_bereich()
        if bis < x_von or von > x_bis:
            return []
        kanten = [x for x in (von, bis) if x_von <= x <= x_bis]
        return [
            schatten(max(von, x_von), min(bis, x_bis), ft.Colors.with_opacity(0.14, BAND_FARBE)),
            *([senkrechte(kanten, BAND_FARBE, 2.0, gestrichelt=False)] if kanten else []),
        ]

    def band_greifen(x: float) -> bool:
        """Ein Finger auf dem Band nimmt es mit; daneben blättert er die Kurve."""
        if not band_sichtbar():
            return False
        von, bis = band_bereich()
        if aw.griff is None:
            if not von <= x <= bis:
                return False
            aw.griff = x - von
            return True
        aw.von = x - aw.griff
        band_bereich()  # an die Grenzen der Messung
        return True

    def rr_losgelassen() -> None:
        notizfeld.loslassen()  # eine gezogene Marke bekommt ihren neuen Anker
        if aw.griff is not None:
            aw.griff = None
            nachrechnen_planen()
            if m.vollbild:
                return  # dort steht keine Analyse
            # Bis gerechnet ist: das letzte Ergebnis, blass, mit Hinweis
            analyse.zeichnen(*sichtbar(), strich=m.strich if m.ablesen else None)
            with contextlib.suppress(Exception):
                analyse.control.update()

    def nachrechnen_planen() -> None:
        """Nach der Latenz rechnen — kommt vorher noch eine Bewegung, gilt nur die letzte."""
        aw.wartet = True
        aw.auftrag += 1
        nummer = aw.auftrag
        route = state.route_nummer  # die Ansicht verlassen → nicht mehr für sie rechnen

        async def spaeter() -> None:
            await asyncio.sleep(state.hrv_einstellungen().nachrechnen_ms / 1000)
            if nummer != aw.auftrag or route != state.route_nummer:
                return
            aw.wartet = False
            if m.vollbild:
                return  # gerechnet wird beim Verlassen des Vollbilds
            analyse.zeichnen(*sichtbar(), strich=m.strich if m.ablesen else None)
            with contextlib.suppress(Exception):
                analyse.control.update()

        page.run_task(spaeter)

    def band_schieben(richtung: int) -> Callable[[], None]:
        def handler() -> None:
            von, bis = band_bereich()
            aw.von = von + richtung * (bis - von) / 2
            band_bereich()
            nachrechnen_planen()
            mitte = sum(band_bereich()) / 2
            x_von, x_bis = sichtbar()
            if not x_von <= mitte <= x_bis:
                zentrieren(mitte)
            nur_kurven()

        return handler

    def laenge_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        neu = int(e.control.value or aw.laenge_s)
        mitte = sum(band_bereich()) / 2
        aw.laenge_s = neu
        aw.von = mitte - neu / 2
        einst.analyse_laenge_s = neu
        gespeichert_ = state.hrv_einstellungen()
        gespeichert_.analyse_laenge_s = neu
        state.hrv_einstellungen_setzen(gespeichert_)
        nachrechnen_planen()
        nur_kurven()

    def art_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        aw.art = str(e.control.selected[0])
        if aw.art == AW_ABSCHNITT and not any(a.id == aw.abschnitt_id for a in eigene):
            aw.abschnitt_id = eigene[0].id if eigene else None
        if aw.art == AW_BAND:
            aw.von = None  # mitten in den sichtbaren Ausschnitt
        nur_kurven()

    def abschnitt_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        aw.abschnitt_id = e.control.value
        nur_kurven()

    def analysefenster() -> Analysefenster:
        if aw.art == AW_ABSCHNITT:
            a = next((a for a in eigene if a.id == aw.abschnitt_id), None)
            if a is not None:
                lo, hi = grenzen()
                von, bis = max(a.von_s, lo), min(a.bis_s, hi)
                korr = z.korrigiert()
                return Analysefenster(
                    f"abschnitt:{a.id}:{von:.3f}:{bis:.3f}",
                    von,
                    bis,
                    f"Abschnitt „{a.name}“ · {_uhr(von)}–{_uhr(bis)}",
                    # wie die Abschnittswerte in der Tabelle: Nähte und langer Weg
                    ganzes=lambda: abschnitt_spektrum(korr, korr_zeiten(korr, z.achse), von, bis),
                )
        if aw.art == AW_BAND:
            von, bis = band_bereich()
            return Analysefenster(
                f"band:{von:.2f}:{bis:.2f}",
                von,
                bis,
                f"{fenster_text(round(bis - von))} · {_uhr(von)}–{_uhr(bis)}",
            )
        lo, hi = grenzen()
        return Analysefenster(
            AW_ALLES,
            lo,
            hi,
            "Ganze Messung" if z.ausschnitt is None else f"Zuschnitt {_uhr(lo)}–{_uhr(hi)}",
            ganzes=lambda: Fensterspektrum.aus_frequenzbereich(frequenz()),
        )

    def fenster_kopf() -> ft.Control:
        """Wahl des Analysefensters über Spektrum bzw. Poincaré."""
        zeilen: list[ft.Control] = [
            ft.SegmentedButton(
                selected=[aw.art],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value=AW_ALLES, label=ft.Text("Alles")),
                    ft.Segment(value=AW_ABSCHNITT, label=ft.Text("Abschnitt")),
                    ft.Segment(value=AW_BAND, label=ft.Text("Fenster")),
                ],
                on_change=art_gewaehlt,
            )
        ]
        if aw.art == AW_ABSCHNITT:
            if eigene:
                zeilen.append(
                    ft.Dropdown(
                        label="Abschnitt",
                        value=aw.abschnitt_id,
                        dense=True,
                        options=[
                            ft.DropdownOption(
                                key=a.id, text=f"{a.name} · {_uhr(a.von_s)}–{_uhr(a.bis_s)}"
                            )
                            for a in eigene
                        ],
                        on_select=abschnitt_gewaehlt,
                    )
                )
            else:
                zeilen.append(hinweis("Noch keine Abschnitte — oben unter „Abschnitte“ anlegen."))
        elif aw.art == AW_BAND:
            zeilen.append(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Dropdown(
                            label="Länge",
                            value=str(aw.laenge_s),
                            dense=True,
                            width=120,
                            options=[
                                ft.DropdownOption(key=str(x), text=fenster_text(x))
                                for x in ANALYSE_LAENGEN
                            ],
                            on_select=laenge_gewaehlt,
                        ),
                        ft.IconButton(
                            ft.Icons.CHEVRON_LEFT,
                            tooltip="Fenster ein halbes zurück",
                            on_click=band_schieben(-1),
                        ),
                        ft.IconButton(
                            ft.Icons.CHEVRON_RIGHT,
                            tooltip="Fenster ein halbes weiter",
                            on_click=band_schieben(1),
                        ),
                    ],
                )
            )
        zeilen.append(ft.Text(analysefenster().titel, size=12, weight=ft.FontWeight.W_600))
        return ft.Column(spacing=6, tight=True, controls=zeilen)

    analyse = Analyse(
        page,
        state,
        bereiche=einst.bereiche(optisch=verity),
        reihe=analyse_reihe,
        hf_geraet=hf_geraet,
        ohne=lambda: [] if rec.hat_rr else ohne_rr(),
        neu_zeichnen=lambda: zeichnen(),
        wischen=lambda c: wischbar(
            c,
            fenster,
            achse_ende,
            wisch_zeichnen,
            anfang=achse_anfang,
            tippen=analyse_tippen,
            greifen=analyse_greifen,
        ),
        tabelle=tabelle,
        optisch=verity,
        hoehe=130,
        analysefenster=analysefenster,
        fenster_kopf=fenster_kopf,
        warten=lambda: aw.griff is not None or aw.wartet,
        info_zusatz=lambda bereich: "" if z.nur_puls else _verlauf_info(bereich),
    )

    # -- Korrektur ---------------------------------------------------------------

    def schalter(i: int) -> Callable[[], None]:
        def handler() -> None:
            z.uebernommen.symmetric_difference_update({i})
            zeichnen()

        return handler

    def hinsehen(i: int) -> Callable[[], None]:
        """Auf die Kette zoomen: eine Minute um ihre Mitte."""

        def handler() -> None:
            k = z.ketten[i]
            mitte = (z.achse[k.start] + z.achse[min(k.ende, len(z.achse) - 1)]) / 2
            breite_setzen(60, mitte)

        return handler

    def alle_uebernehmen() -> None:
        z.uebernommen.update(range(len(z.ketten)))
        zeichnen()

    def keine() -> None:
        z.uebernommen.clear()
        zeichnen()

    async def korrektur_sichern() -> str | None:
        """Korrektur ins Sidecar (Thread, H39) — ``None`` = gespeichert, sonst der Fehler.

        Geschrieben wird der Stand beim Aufruf; was die Person währenddessen ändert,
        bleibt ungespeichert und der Knopf dafür aktiv."""
        nonlocal gespeicherte_regeln
        korrekturen, regeln, basis = z.korrekturen(), z.regeln, z.basis
        auswahl = frozenset(z.uebernommen)
        try:
            async with sperre:
                await asyncio.to_thread(
                    analyse_speichern, pfad, rec, korrekturen, regeln=regeln, basis=basis
                )
        except (OSError, SidecarFehler) as fehler:
            return str(fehler)
        z.gespeichert = korrekturen
        gespeicherte_regeln = regeln
        bezug[0] = (auswahl, regeln)
        zurueck_pruefen()
        return None

    async def speichern() -> None:
        if (fehler := await korrektur_sichern()) is not None:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))
            return
        if not aktuell():
            return
        page.show_dialog(ft.SnackBar(ft.Text(KORREKTUR_GESPEICHERT)))
        zeichnen()

    speichern_knopf.on_click = speichern

    def regeln_oeffnen() -> None:
        auftrag = [0]

        def aendern(regeln: Korrekturregeln) -> None:
            """Neue Regeln: Basis, Vorschläge und Sidecar dazu rechnet ein Thread; kommt
            vorher die nächste Änderung, zählt nur die letzte (wie `nachrechnen_planen`)."""
            auftrag[0] += 1
            nummer = auftrag[0]

            async def rechnen() -> None:
                async with sperre:
                    if nummer != auftrag[0]:
                        return
                    stand = await asyncio.to_thread(korrekturstand, pfad, rec, regeln)
                if nummer != auftrag[0] or not aktuell():
                    return
                z.regeln_setzen(stand)
                zeichnen()

            page.run_task(rechnen)

        def merken(regeln: Korrekturregeln) -> None:
            state.korrekturregeln_setzen(regeln)
            page.show_dialog(
                ft.SnackBar(ft.Text("Als Vorgabe gemerkt — gilt für neue Aufzeichnungen und live."))
            )

        blatt = korrektur_blatt(
            z.regeln,
            aendern,
            erweitert=True,
            verity=verity,
            standard_merken=merken,
            schliessen=lambda: schliessen(blatt),  # „Fertig“ traf sonst die SnackBar (N18)
        )
        page.show_dialog(blatt)

    def ketten_zeile(i: int, k: Kette) -> ft.Control:
        an = i in z.uebernommen
        t = z.achse[k.start] if k.start < len(z.achse) else 0.0
        anzahl = k.ende - k.start + 1
        was = "interpolieren" if k.art == "interpolieren" else "ausschließen"
        zusatz = []
        if k.unsicher:
            zusatz.append("unsicher")
        vom_sensor = sum(1 for j in range(k.start, k.ende + 1) if z.basis.zeile[j] is None)
        if vom_sensor:
            zusatz.append(f"Sensor verwarf {vom_sensor}")
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(
                ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                color=ft.Colors.PRIMARY if an else None,
            ),
            title=ft.Text(f"{_uhr(t)} · {anzahl} {'Schlag' if anzahl == 1 else 'Schläge'} {was}"),
            subtitle=ft.Text(" · ".join([k.grund, *zusatz]), size=12),
            trailing=ft.IconButton(
                ft.Icons.ZOOM_IN, tooltip="In der Kurve zeigen", on_click=hinsehen(i)
            ),
            on_click=schalter(i),
            content_padding=ft.Padding.only(left=0, right=0),
        )

    # -- Titel und Beschreibung (``titel``/``notiz`` der Messdatei, wie praxis_gui) --

    def titel_zeichnen() -> None:
        titel_box.content = titel_kopf(rec.titel, beschreibung, titel_bearbeiten)

    def titel_speichern(titel: str, text: str) -> None:
        """In die Messdatei (Thread, H39); die Kopien in der Datenbank folgen, wenn sie steht."""
        nonlocal beschreibung
        if titel == rec.titel and text == (rec.notiz or ""):
            return
        rec.titel, rec.notiz, beschreibung = titel, text, text
        titel_zeichnen()
        page.update()

        async def schreiben() -> None:
            try:
                async with sperre:
                    sha1 = await asyncio.to_thread(
                        metadaten_schreiben, pfad, titel=titel, notiz=text
                    )
            except (OSError, ValueError) as fehler:
                page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))
                return
            state.hrv.titel_setzen(eintrag.id, titel)
            state.hrv.notiz_setzen(eintrag.id, text)
            state.hrv.sha1_setzen(eintrag.id, sha1)

        page.run_task(schreiben)

    def titel_bearbeiten() -> None:
        von = eintrag.started_at
        bis = von + timedelta(seconds=eintrag.duration_s or dauer)
        plaene = geuebte_plaene(state, von, bis)
        page.show_dialog(
            titel_blatt(
                rec.titel,
                beschreibung,
                titel_vorschlaege(state, von, bis, rec.ereignisse),
                titel_speichern,
                vorgabe=plaene[0] if plaene else "",
            )
        )

    # -- Vollbild (quer): Kurven mit zwei Achsen und Werkzeugen (Ben, 15./16.10.2026) ----
    #
    # Kein Neubau der Ansicht (der kostete Sekunden und den Editorzustand): dieselbe
    # View tauscht Leiste und Inhalt. Rohkurve, Ablesewerte und Editor wandern in
    # eigene Boxen des Vollbilds; `rr_box`, `ablese_box` und `editor_box` zeigen
    # jeweils auf die sichtbare, damit alle Zeichenwege weiter stimmen. Notizfeld
    # und Abschnittsliste ziehen in die Seitenleiste — dieselben Controls wie
    # hochkant, darum dieselben Funktionen.
    normal_boxen = (rr_box, ablese_box, editor_box)
    voll_boxen = (ft.Container(), ft.Container(visible=False), ft.Container(visible=False))
    notiz_platz = (ft.Container(content=notizfeld.control), ft.Container())
    abschnitte_platz = (ft.Container(content=abschnitte_box), ft.Container())
    etikett_box = ft.Container(visible=False)
    links_box, rechts_box = ft.Container(), ft.Container()
    roh_titel = "Herzfrequenz" if z.nur_puls else "PPI-Tachogramm" if verity else "RR-Tachogramm"
    #: Zwischenspeicher der Verlaufskurven im Vollbild (die Analyse hat ihren eigenen)
    vb_speicher: dict[Any, Any] = {}

    def kurvengeste(box: ft.Container, *, voll: bool = False) -> ft.Control:
        return wischbar(
            box,
            fenster,
            achse_ende,
            lambda: wisch_zeichnen(mit_analyse=m.editor is None),
            anfang=achse_anfang,
            tippen=kurve_tippen,
            greifen=kurve_greifen,
            losgelassen=rr_losgelassen,
            tippen_punkt=kurve_tippen_punkt if voll else None,
            rechts_px=(lambda: m.rechts) if voll else (lambda: 0.0),
        )

    def boxen_umhaengen(nach: tuple[ft.Container, ...]) -> None:
        nonlocal rr_box, ablese_box, editor_box
        for alt, neu in zip((rr_box, ablese_box, editor_box), nach, strict=True):
            neu.content, neu.visible = alt.content, alt.visible
            alt.content = None
        rr_box, ablese_box, editor_box = nach

    def umhaengen(paar: tuple[ft.Container, ft.Container], *, ins_vollbild: bool) -> None:
        von, nach = paar if ins_vollbild else paar[::-1]
        nach.content, von.content = von.content, None

    def kurven_angebot() -> list[str]:
        ohne = [] if rec.hat_rr else ohne_rr()
        return angebot(einst.bereiche(optisch=verity), ohne, roh=rec.hat_rr)

    def vollbild_kurven(x_von: float, x_bis: float, hinten: list[Reihe]) -> None:
        """Im Vollbild: beide Achsen, Etikett und Ablesewerte — keine Analyse darunter."""
        ansicht_ = state.ansicht()
        m.angebot = kurven_angebot()
        m.rechts = rechts_px(ansicht_, m.angebot)
        kopf_zeichnen()
        atem_modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
        daten = verlaufsdaten(
            analyse_reihe(), hf_geraet(), ansicht_, atem_modus, vb_speicher, x_von, x_bis
        )
        m.gesehen = {}
        rr_box.content = doppelkurve(
            ansicht_,
            daten,
            lambda: roh_reihen(x_von, x_bis),
            angebot=m.angebot,
            x_von=x_von,
            x_bis=x_bis,
            hoehe=int(m.hoehe),
            roh_einheit="PPI ms" if verity else "RR ms",
            marken=marken_reihen(x_von, x_bis),
            hinten=hinten,
            gesehen=m.gesehen,
        )
        etikett_zeichnen(x_von, x_bis)
        if m.ablesen and m.strich is not None:
            ablesen_zeichnen()
        seite_zeichnen()

    def kopf_zeichnen() -> None:
        """Die Wahl der Achsen — nur neu gebaut, wenn sich an ihr etwas ändert."""
        a = state.ansicht()
        schluessel = (
            tuple(a.links),
            tuple(a.rechts),
            tuple(m.angebot),
            a.pnn_ms,
            tuple(sorted(a.fenster.items())),
            tuple(sorted(a.modus.items())),
        )
        if schluessel == m.kopf:
            return
        m.kopf = schluessel
        links_box.content = seiten_wahl(state, LINKS, m.angebot, roh_titel, nur_kurven)
        rechts_box.content = seiten_wahl(state, RECHTS, m.angebot, roh_titel, nur_kurven)

    # Etikett: Zeit und Text einer Notiz bzw. Name und Werte eines Abschnitts

    def etikett_knopf(icon: ft.IconData, tooltip: str, aktion: Callable[[], None]) -> ft.Control:
        return ft.IconButton(icon, icon_size=20, tooltip=tooltip, on_click=lambda: aktion())

    def etikett_zeichnen(x_von: float, x_bis: float) -> None:
        inhalt: ft.Control | None = None
        x: float | None = None
        oben = 4.0
        if m.etikett is not None and m.etikett[0] == "notiz":
            i = int(m.etikett[1])
            info = notizfeld.etikett(i)
            if info is not None:
                x, zeit, text = info
                ereignis_ = notizfeld.ereignis(i)
                inhalt = etikett(
                    zeit,
                    text,
                    FARBEN["leistung"]
                    if ereignis_ and _ist_leistung(ereignis_)
                    else FARBEN["notiz"],
                    [
                        etikett_knopf(
                            ft.Icons.EDIT_OUTLINED, "Notiz bearbeiten", lambda: notiz_bearbeiten(i)
                        ),
                        etikett_knopf(
                            ft.Icons.DELETE_OUTLINE, "Notiz löschen", lambda: notiz_loeschen(i)
                        ),
                        etikett_knopf(ft.Icons.CLOSE, "Etikett schließen", etikett_schliessen),
                    ],
                )
        elif m.etikett is not None:
            a = next((a for a in eigene if a.id == m.etikett[1]), None)
            if a is not None:
                x = min(max((a.von_s + a.bis_s) / 2, x_von), x_bis)
                # gleich unter seinem Balken — die Kurve bleibt größtenteils frei
                ebene = min(ebenen().get(a.id, 0), 3)
                oben = (0.04 + 0.06 * (ebene + 1)) * max(m.hoehe - ZEITACHSE_PX, 1.0) + 4
                inhalt = etikett(
                    f"{_uhr(a.von_s)}–{_uhr(a.bis_s)} ({_uhr(a.dauer_s)})",
                    a.name,
                    a.farbe,
                    [
                        etikett_knopf(
                            ft.Icons.EDIT_OUTLINED,
                            "Abschnitt bearbeiten",
                            lambda: etikett_abschnitt_bearbeiten(a),
                        ),
                        etikett_knopf(
                            ft.Icons.DELETE_OUTLINE,
                            "Abschnitt löschen",
                            lambda: etikett_abschnitt_loeschen(a),
                        ),
                        etikett_knopf(ft.Icons.CLOSE, "Etikett schließen", etikett_schliessen),
                    ],
                    zeilen=[" · ".join(abschnitt_teile(a))],
                )
        sichtbar = inhalt is not None and x is not None and x_von <= x <= x_bis
        etikett_box.visible = sichtbar
        etikett_box.content = inhalt if sichtbar else None
        if sichtbar and x is not None:
            etikett_box.left = lage_px(x, x_von, x_bis, m.breite, m.rechts, ETIKETT_PX)
            etikett_box.top = oben

    def etikett_schliessen() -> None:
        m.etikett = None
        nur_kurven(mit_analyse=False)

    def notiz_bearbeiten(i: int) -> None:
        """✎ am Etikett: die Notiz in der Seitenleiste öffnen — Text, Zeit, Übungen."""
        m.etikett = None
        if m.editor is not None:
            editor_schliessen(zeichnen_=False)
        m.seite = NOTIZEN
        notizfeld.aufklappen()
        notizfeld.bearbeiten(i)

    def notiz_loeschen(i: int) -> None:
        m.etikett = None
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

    def etikett_abschnitt_bearbeiten(a: Abschnitt) -> None:
        m.etikett = None
        abschnitt_bearbeiten(a)

    def etikett_abschnitt_loeschen(a: Abschnitt) -> None:
        m.etikett = None
        abschnitt_loeschen(a)

    # Seitenleiste und Werkzeugleiste

    def seite_umschalten(welche: str) -> None:
        """Notizen oder Abschnitte neben der Kurve — ein zweiter Tipp schließt."""
        if m.editor is not None:
            editor_schliessen(zeichnen_=False)
        m.seite = None if m.seite == welche else welche
        m.etikett = None
        if m.seite == NOTIZEN:
            notizfeld.aufklappen()
        nur_kurven(mit_analyse=False)

    def seite_zeichnen() -> None:
        notiz_seite.visible = m.seite == NOTIZEN and m.editor is None
        abschnitt_seite.visible = m.seite == ABSCHNITTE and m.editor is None
        voll_seite.visible = m.editor is not None or m.seite is not None
        markieren(notizen_knopf, notiz_seite.visible)
        markieren(abschnitte_knopf, abschnitt_seite.visible)

    def vollbild_groesse(e: ft.LayoutSizeChangeEvent) -> None:
        """Die wirkliche Größe der Kurvenfläche — nach dem Drehen anders als geschätzt."""
        hoehe, breite = max(120.0, float(e.height)), float(e.width)
        if m.vollbild and (abs(hoehe - m.hoehe) >= 4 or abs(breite - m.breite) >= 4):
            m.hoehe, m.breite = hoehe, breite
            nur_kurven()

    def marke_setzen() -> None:
        """Notiz ohne Text — am Ablesestrich, sonst in der Fenstermitte; Text über „Notizen"."""
        x = m.strich if m.ablesen and m.strich is not None else sum(sichtbar()) / 2
        notizfeld.marke_setzen(x)

    def darstellung() -> None:
        a = state.ansicht()
        page.show_dialog(
            darstellung_blatt(
                page,
                state,
                lambda: nur_kurven(),
                kurven=[k for k in (*a.links, *a.rechts) if k != ROH],
            )
        )

    def vollbild_umschalten() -> None:
        m.vollbild = not m.vollbild
        m.etikett = None
        if m.vollbild:
            m.hoehe = max(160.0, float(page.height or 480) - 56)
            m.breite = max(320.0, float(page.width or 800) - LEISTE_PX - 8)
            m.kopf = ()
            boxen_umhaengen(voll_boxen)
            umhaengen(notiz_platz, ins_vollbild=True)
            umhaengen(abschnitte_platz, ins_vollbild=True)
            view.appbar = None
            view.scroll = None
            view.padding = ft.Padding.only(left=4, right=4)
            view.can_pop = False  # Zurück verlässt erst das Vollbild
            view.controls = [sicher(vollbild_inhalt)]
            ausrichtung.anwenden(page, state, ausrichtung.QUER)
        else:
            m.seite = None
            boxen_umhaengen(normal_boxen)
            umhaengen(notiz_platz, ins_vollbild=False)
            umhaengen(abschnitte_platz, ins_vollbild=False)
            view.appbar = leiste_oben
            view.scroll = ft.ScrollMode.AUTO
            view.padding = 12
            view.can_pop = kann_zurueck()  # sonst speichert Zurück erst
            view.controls = [sicher(normal_inhalt, expand=False)]
            ausrichtung.anwenden(page, state, ausrichtung.modus_fuer_route(route))
        zeichnen()

    async def zurueck_im_vollbild(e: ft.Event[ft.View]) -> None:
        """Zurück im Vollbild: nur das Vollbild schließen, die Messung bleibt.

        Außerhalb des Vollbilds kommt Zurück nur hierher, wenn die Korrektur ungespeichert
        ist (`zurueck_pruefen`): Dann speichert es sie (Ben, 16.10.2026: Autosave,
        `components/zurueck.py`) — scheitert das, fragt ein Dialog.
        """
        if m.vollbild:
            vollbild_umschalten()
            with contextlib.suppress(Exception):
                await view.confirm_pop(False)  # die Messung bleibt offen
            return
        if m.editor is not None:
            # Zurück speichert (CLAUDE.md): Abschnitt-Editor und Zuschnitt haben zwar einen
            # Knopf, aber Zurück verwarf die Änderung stumm (H34)
            if m.art == ABSCHNITT:
                abschnitt_sichern()
            else:
                crop_uebernehmen()
        if not ungespeichert_geaendert():
            with contextlib.suppress(Exception):
                await view.confirm_pop(True)  # nichts zu speichern: gewöhnliches Zurück
            return
        with contextlib.suppress(Exception):
            await view.confirm_pop(False)  # weiter geht es unten selbst
        ziel = zurueck_ziel(page, view)
        if (fehler := await korrektur_sichern()) is None:
            page.show_dialog(ft.SnackBar(ft.Text(KORREKTUR_GESPEICHERT)))
            await page.push_route(ziel)
            return

        async def verwerfen() -> None:
            await page.push_route(ziel)

        page.show_dialog(
            rueckfrage(f"Die Korrektur ließ sich nicht speichern: {fehler}", verwerfen)
        )

    notizen_knopf = werkzeug(
        ft.Icons.NOTES, "Notizen: Liste, Text, Zeit", lambda: seite_umschalten(NOTIZEN)
    )
    for _name, _icon in (
        (EBENE_NOTIZEN, ft.Icons.STICKY_NOTE_2_OUTLINED),
        (EBENE_LEISTUNGEN, ft.Icons.FITNESS_CENTER),
        (EBENE_ABSCHNITTE, ft.Icons.VIEW_TIMELINE_OUTLINED),
    ):
        ebenen_knoepfe_voll[_name] = werkzeug(
            _icon,
            f"Ebene „{EBENEN_TEXT[_name]}“ ein-/ausblenden",
            partial(ebene_umschalten, _name),
        )
    abschnitte_knopf = werkzeug(
        ft.Icons.VIEW_TIMELINE_OUTLINED,
        "Abschnitte: Liste, neu, aus Notizen",
        lambda: seite_umschalten(ABSCHNITTE),
    )
    notiz_seite = ft.Column(
        spacing=4,
        tight=True,
        visible=False,
        controls=[seitenkopf("Notizen", lambda: seite_umschalten(NOTIZEN)), notiz_platz[1]],
    )
    abschnitt_seite = ft.Column(
        spacing=4,
        tight=True,
        visible=False,
        controls=[
            seitenkopf("Abschnitte", lambda: seite_umschalten(ABSCHNITTE)),
            ft.Row(
                spacing=0,
                controls=[
                    ft.TextButton("Abschnitt", icon=ft.Icons.ADD, on_click=abschnitt_neu),
                    ft.Container(expand=True),
                    abschnitt_menue(),
                ],
            ),
            abschnitte_platz[1],
        ],
    )
    # Scrollt für sich: Editor und Listen sind höher als ein quer gehaltenes Handy
    voll_seite = ft.Container(
        visible=False,
        width=SEITE_PX,
        content=ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            controls=[voll_boxen[2], notiz_seite, abschnitt_seite],
        ),
    )
    vollbild_inhalt = ft.Column(
        spacing=4,
        expand=True,
        controls=[
            ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        ft.Icons.FULLSCREEN_EXIT,
                        tooltip="Vollbild verlassen",
                        on_click=lambda: vollbild_umschalten(),
                    ),
                    links_box,
                    breite_wahl_voll,
                    bindung_voll,
                    chips_voll,
                    rechts_box,
                ],
            ),
            ft.Row(
                expand=True,
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Container(
                        expand=True,
                        on_size_change=vollbild_groesse,
                        content=ft.Stack(
                            expand=True,
                            fit=ft.StackFit.EXPAND,
                            controls=[
                                kurvengeste(voll_boxen[0], voll=True),
                                etikett_box,
                                voll_boxen[1],
                            ],
                        ),
                    ),
                    voll_seite,
                    leiste(
                        ablesen_knopf_voll,
                        werkzeug(
                            ft.Icons.ADD_COMMENT_OUTLINED,
                            "Notiz ohne Text hier — Text über „Notizen“",
                            lambda: marke_setzen(),
                        ),
                        notizen_knopf,
                        abschnitte_knopf,
                        *ebenen_knoepfe_voll.values(),
                        *(
                            []
                            if z.nur_puls
                            else [
                                werkzeug(
                                    ft.Icons.CONTENT_CUT, "Zuschneiden", lambda: crop_oeffnen()
                                )
                            ]
                        ),
                        werkzeug(
                            ft.Icons.TUNE, "Fenster & Darstellung der Kurven", lambda: darstellung()
                        ),
                    ),
                ],
            ),
        ],
    )

    def nur_mit_intervallen(*inhalt: ft.Control) -> ft.Control:
        """Eine Karte, die es bei einer reinen Pulsmessung nicht gibt (Abschnitte, Korrektur)."""
        k = karte(*inhalt)
        k.visible = not z.nur_puls
        return k

    def uebungen_liste() -> ft.Control:
        """Je Eintrag eine Zeile (Skizze D1): Übung, Werte, von–bis; ein Tipp zoomt."""
        namen: dict[str, str] = {}
        zeilen: list[ft.Control] = []
        for b in bezuege_liste:
            e = b.eintrag
            if e.exercise_id not in namen:
                u = state.uebungen.laden(e.exercise_id)
                namen[e.exercise_id] = u.name if u is not None else "Übung"
            bd = buendeln([e])[0]
            kopf = " · ".join(t for t in (namen[e.exercise_id], bd.auspraegung_text()) if t)
            werte = bd.leistung_text() or bd.einzelwerte_text() or "abgehakt"
            unten = (
                f"{_uhr(b.von_s)}–{_uhr(b.bis_s)} · {werte}"
                + (" · zeitlich" if b.zeitlich else "")
                + (f" · „{e.note}“" if e.note else "")
            )
            zeilen.append(
                ft.Container(
                    border_radius=10,
                    ink=True,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    on_click=lambda _=None, b=b: zoom_auf(*b.fenster()),
                    content=ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=4,
                                height=34,
                                border_radius=2,
                                bgcolor=ft.Colors.OUTLINE if b.zeitlich else FARBEN["leistung"],
                            ),
                            ft.Column(
                                spacing=0,
                                expand=True,
                                controls=[
                                    ft.Text(kopf, size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(unten, size=12, opacity=0.75),
                                ],
                            ),
                            ft.Text(
                                "Zoom ›",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY,
                            ),
                        ],
                    ),
                )
            )
        return ft.Column(spacing=2, controls=zeilen)

    ebenen_zeichnen()
    zoom = getattr(state, "messung_zoom", None)
    if zoom is not None and zoom[0] == eintrag.id:
        state.messung_zoom = None
        zoom_auf(float(zoom[1]), float(zoom[2]), zeichnen_=False)
    titel_zeichnen()
    zeichnen(aktualisieren=False)
    normal_inhalt = ft.Column(
        spacing=12,
        controls=[
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=4),
                content=ft.Column(
                    spacing=4, controls=[titel_box, kopf_text, hinweis_text, sidecar_text]
                ),
            ),
            kacheln_box,
            karte(
                kartentitel(
                    roh_titel,
                    # Was die Farben heißen — vorher grauer Text unter den Notizen (Ben, 17.10.)
                    info_knopf(page, "So liest du die Kurve", _kurven_info(z.nur_puls, verworfen)),
                    ablesen_knopf,
                    ft.IconButton(
                        ft.Icons.FULLSCREEN,
                        tooltip="Vollbild (quer): zwei Achsen, Notizen und Abschnitte genau setzen",
                        on_click=lambda: vollbild_umschalten(),
                    ),
                ),
                ebenen_box,
                bindung_box,
                kurvengeste(rr_box),
                ft.Row(controls=[breite_wahl]),
                chips_box,
                ablese_box,
                editor_box,
                notiz_platz[0],
            ),
            *(
                [
                    karte(
                        kartentitel(
                            f"Übungen · {len(bezuege_liste)}",
                            info_knopf(page, "Einträge in dieser Aufnahme", UEBUNGEN_INFO),
                        ),
                        uebungen_liste(),
                    )
                ]
                if bezuege_liste
                else []
            ),
            nur_mit_intervallen(
                kartentitel(
                    "Abschnitte",
                    info_knopf(page, "So arbeitest du mit Abschnitten", ABSCHNITTE_INFO),
                    ft.TextButton("Abschnitt", icon=ft.Icons.ADD, on_click=abschnitt_neu),
                    abschnitt_menue(),
                ),
                abschnitte_platz[0],
            ),
            analyse.control,
            nur_mit_intervallen(
                kartentitel(
                    "Korrektur",
                    info_knopf(page, "So funktioniert die Korrektur", KORREKTUR_INFO),
                    regler_knopf(regeln_oeffnen, "Was automatische Korrektur heißt"),
                    ft.TextButton("Alle", on_click=alle_uebernehmen),
                    ft.TextButton("Keine", on_click=keine),
                ),
                ketten_box,
                speichern_knopf,
            ),
            ft.Text(f"Datei: {eintrag.file_path}", size=11, opacity=0.5, selectable=True),
        ],
    )
    ansicht([normal_inhalt])
    view.on_confirm_pop = zurueck_im_vollbild
    gebaut.append(view)
    zurueck_pruefen()


# ---------------------------------------------------------------------------
# Zusammenfassungen der ganzen Messung
# ---------------------------------------------------------------------------


def _gesamtwert(
    kennzahl: str,
    td: dict[str, Any],
    frequenz: Callable[[], dict[str, Any] | None],
    nichtlinear: Callable[[], dict[str, Any]],
    nachkomma: int,
) -> tuple[str, str, str]:
    """``(Wert, Einheit, Zusatz)`` einer Kachel über die ganze Messung."""
    einheit = KENNZAHLEN[kennzahl].einheit
    zeit = {
        "hf_rr": "mean_bpm",
        "mean_rr": "mean_rr",
        "rmssd": "rmssd",
        "sdnn": "sdnn",
        "pnnx": "pnn50",
    }
    if kennzahl in zeit:
        return zahl(td.get(zeit[kennzahl]), nachkomma), einheit, ""
    if kennzahl in ("lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power"):
        f = frequenz() or {}
        if kennzahl == "gipfel":
            g = f.get("gipfel_hz")
            return zahl(g * 60 if g else None, 1), einheit, ""
        band = {"lf_power": "lf", "hf_power": "hf", "lf_hf": "lf", "vlf_power": "vlf"}[kennzahl]
        wert = f.get(
            {"lf_power": "lf", "hf_power": "hf", "lf_hf": "lf_hf", "vlf_power": "vlf"}[kennzahl]
        )
        if wert is None and f.get("band_status", {}).get(band) not in (None, BAND_OK):
            return "gesperrt", "", _kurzgrund(f["band_reason"].get(band, ""))
        return zahl(wert, nachkomma), einheit, ""
    n = nichtlinear()
    return zahl(n.get(kennzahl), nachkomma), einheit, ""


def _kurzgrund(grund: str) -> str:
    """„kein Teilstück ≥ 5 min (…)" → „< 5 min" — passt in eine Kachel."""
    if "≥" in grund:
        return "< " + grund.split("≥", 1)[1].split("(")[0].strip()
    return grund[:24]


def _zeilen_tabelle(
    kopf: list[str], zeilen: list[tuple[str, list[str]]], hinweis_text: str = "", ecke: str = ""
) -> ft.Control:
    """Eine kleine Tabelle: erste Spalte Name, dann Werte (rechts fett).

    ``hinweis_text`` nur für das, was die Zahlen einschränkt — Erklärungen stehen hinter
    dem „i“ der Karte (`TABELLE_INFO`). ``ecke``: Text über der Namensspalte.
    """
    breit = len(kopf) > 1
    inhalt: list[ft.Control] = []
    if breit:
        inhalt.append(
            ft.Row(
                controls=[
                    ft.Text(ecke, size=12, opacity=0.6, expand=2),
                    *[ft.Text(k, size=12, opacity=0.6, expand=1) for k in kopf],
                ]
            )
        )
    for name, werte in zeilen:
        inhalt.append(
            ft.Row(
                controls=[
                    ft.Text(name, expand=2),
                    *[
                        ft.Text(
                            w,
                            expand=1,
                            weight=ft.FontWeight.BOLD if i == len(werte) - 1 else None,
                        )
                        for i, w in enumerate(werte)
                    ],
                ]
            )
        )
    if hinweis_text:
        inhalt.append(hinweis(hinweis_text))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column(spacing=4, tight=True, controls=inhalt),
    )


def _zeit_tabelle(
    roh: dict[str, Any] | None, korr: dict[str, Any] | None, pnn_ms: int
) -> ft.Control:
    zeilen = [
        ("Ø Herzfrequenz", "mean_bpm", "bpm", 0),
        ("Ø RR", "mean_rr", "ms", 0),
        ("RMSSD", "rmssd", "ms", 1),
        ("SDNN", "sdnn", "ms", 1),
        (f"pNN{pnn_ms}", "pnn50", "%", 1),
        ("Schläge", "n", "", 0),
    ]
    return _zeilen_tabelle(
        ["roh", "korrigiert"],
        [
            (titel_, [f"{_wert(roh, k, n)} {e}".strip(), f"{_wert(korr, k, n)} {e}".strip()])
            for titel_, k, e, n in zeilen
        ],
        ecke="ganze Messung",
    )


def _frequenz_tabelle(f: dict[str, Any] | None) -> ft.Control:
    if f is None:
        return _zeilen_tabelle(
            [], [], "Für die Frequenzanalyse fehlen gute Schläge (mindestens 60)."
        )

    def band(key: str) -> str:
        if f.get(key) is not None:
            return f"{zahl(f[key])} ms²"
        return "gesperrt" if f["band_status"].get(key) != BAND_OK else "–"

    gipfel = f.get("gipfel_hz")
    zeilen = [
        ("ULF unter 0,003 Hz", [band("ulf")]),
        ("VLF 0,003–0,04 Hz", [band("vlf")]),
        ("LF 0,04–0,15 Hz", [band("lf")]),
        ("HF 0,15–0,40 Hz", [band("hf")]),
        ("LF/HF", [zahl(f.get("lf_hf"), 2)]),
        ("LF n.u. / HF n.u.", [f"{zahl(f.get('lf_n'))} / {zahl(f.get('hf_n'))} %"]),
        ("Gipfel", [f"{zahl(gipfel, 2)} Hz · {zahl(gipfel * 60)}/min" if gipfel else "–"]),
    ]
    gruende = [
        f"{b.upper()}: {f['band_reason'][b]}"
        for b in ("ulf", "vlf", "lf", "hf")
        if b in f["band_reason"]
    ]
    text = "Gesperrt — " + "; ".join(gruende) + "." if gruende else ""
    return _zeilen_tabelle(["ganze Messung"], zeilen, text)


def _nichtlinear_tabelle(n: dict[str, Any], optisch: bool) -> ft.Control:
    zeilen = [
        ("SD1", [f"{zahl(n.get('sd1'), 1)} ms"]),
        ("SD2", [f"{zahl(n.get('sd2'), 1)} ms"]),
        ("SD1/SD2", [zahl(n.get("sd1_sd2"), 2)]),
        ("DFA α1", [zahl(n.get("dfa_alpha1"), 2)]),
        ("SampEn", [zahl(n.get("sampen"), 2)]),
    ]
    text = "Bei optischen Pulsintervallen nicht belastbar." if optisch else ""
    return _zeilen_tabelle(["ganze Messung"], zeilen, text)


class _Zustand:
    """Was die Detailansicht über die Korrektur weiß — ohne Oberfläche.

    Regeln → Analysebasis → Vorschläge → Auswahl kommen als `Korrekturstand` aus
    hrv-core (`korrektur_laden`, `korrekturstand`); hier liegen Kurvenachsen,
    Zwischenergebnisse und die Auswahl, die die Person ändert. Ändern sich die
    Regeln, entsteht alles dahinter neu (`regeln_setzen`).
    """

    def __init__(self, stand: Korrekturstand) -> None:
        self.rec = stand.rec
        self.gespeichert: list[Korrektur] = []
        self.uebernommen: set[int] = set()
        #: Crop auf der Kurvenachse — ``None`` = die ganze Messung zählt
        self.ausschnitt: tuple[float, float] | None = None
        self._stand_uebernehmen(stand)

    def _stand_uebernehmen(self, stand: Korrekturstand) -> None:
        self._korr: tuple[frozenset[int], Korrigiert] | None = None
        self._gemerkt: dict[str, tuple[Any, Any]] = {}
        self.regeln = stand.regeln
        self.basis = stand.basis
        self.ketten: list[Kette] = stand.ketten
        self.gespeichert = stand.gespeichert
        self.uebernommen = set(stand.uebernommen)
        self._roh = anwenden(self.basis.rec, [])
        # Zeitachse: Herzuhr aller Intervalle — bei der Verity Sense samt der vom
        # Sensor verworfenen, sonst schrumpfte die Messung um deren Dauer.
        self.achse = schlagzeiten(self.basis.rec)
        self.roh_punkte, self.roh_naehte = rohfolge(self.basis.rec)
        # Nur Puls (Ben, 17.10.2026): Ohne ein einziges Intervall bleibt die Herzuhr der
        # Datei bei 0 — dann trägt die Wanduhr die Zeitachse, die Hauptkurve ist der Puls.
        # Ohne Wanduhr (ältere Dateien) wird keine Achse geraten.
        beats = self.basis.rec.beats
        self.nur_puls = (
            not self.basis.rec.hat_rr
            and any(b.hf_bpm > 0 for b in beats)
            and all(b.t_wall_s is not None for b in beats)
        )
        if self.nur_puls:
            self.achse = [float(b.t_wall_s or 0.0) for b in beats]
        self.puls_punkte = [
            (x, float(b.hf_bpm)) for x, b in zip(self.achse, beats, strict=True) if b.hf_bpm > 0
        ]

    def regeln_setzen(self, stand: Korrekturstand) -> None:
        """Neue Regeln (`korrekturstand`): neue Basis und Vorschläge, Auswahl nach der
        Vorauswahl der Regeln — nicht nach dem Sidecar."""
        self._stand_uebernehmen(stand)
        self.uebernommen = vorauswahl(self.ketten, stand.regeln.vorauswahl)

    def korrekturen(self) -> list[Korrektur]:
        return [v for i in sorted(self.uebernommen) for v in self.ketten[i].vorschlag]

    def korrigiert(self) -> Korrigiert:
        """Die korrigierte Reihe — zwischengespeichert, Wischen rechnet sie nicht neu."""
        schluessel = frozenset(self.uebernommen)
        if self._korr is None or self._korr[0] != schluessel:
            self._korr = (schluessel, anwenden(self.basis.rec, self.korrekturen()))
        return self._korr[1]

    def roh_korr(self) -> Korrigiert:
        """Die Reihe ohne jede Korrektur (nur die Nähte der Messung)."""
        return self._roh

    def analyse_korr(self, roh: bool = False) -> Korrigiert:
        """Die Reihe für Kennzahlen — bei Crop nur dessen Ausschnitt (`zuschneiden`)."""
        korr = self.roh_korr() if roh else self.korrigiert()
        if self.ausschnitt is None:
            return korr
        return zuschneiden(korr, korr_zeiten(korr, self.achse), *self.ausschnitt)

    def merken(self, name: str, rechnen: Callable[[], Any]) -> Any:
        """Ergebnis zu Auswahl und Crop — Spektrum und DFA nur bei Änderungen neu."""
        schluessel = (frozenset(self.uebernommen), self.ausschnitt)
        alt = self._gemerkt.get(name)
        if alt is None or alt[0] != schluessel:
            self._gemerkt[name] = (schluessel, rechnen())
        return self._gemerkt[name][1]

    def geaendert(self, gespeicherte_regeln: Korrekturregeln | None) -> bool:
        """Weicht die Auswahl oder die Regel vom Gespeicherten ab?"""

        def schluessel(ks: list[Korrektur]) -> list[tuple[str, int, int]]:
            return sorted((k.op, k.beat_index, k.span()[1]) for k in ks)

        if gespeicherte_regeln is not None and gespeicherte_regeln != self.regeln:
            return True
        return schluessel(self.korrekturen()) != schluessel(self.gespeichert)


__all__ = ["messung_detail_view"]
