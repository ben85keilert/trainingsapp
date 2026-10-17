"""Tabellen und Schreibweisen des Ausdauertrainings — geteilt von der Ausdauer-Ansicht und
der Übersicht im Reiter „Einheit“ (Ben, 17.10.2026; Skizzen 6 und 19).

Ortsfrei: Strecken, Zeiten, Tempo und Herzwerte, nie ein Ort. Gerechnet wird in
`core.intervalle`; hier wird nur geschrieben und gezeichnet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import flet as ft

from trainingsapp.core.intervalle import (
    HerzQuelle,
    HfReihe,
    Intervall,
    KmZeile,
    intervalle,
    kilometer,
    strecke_auf_achse,
)
from trainingsapp.core.strecke import RAD
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.strecke_baustein import StreckeBaustein


def km_text(meter: float) -> str:
    """Kilometer mit zwei Stellen.

    >>> km_text(5212.4), km_text(820)
    ('5,21 km', '0,82 km')
    """
    return f"{meter / 1000:.2f} km".replace(".", ",")


def zeit_text(sekunden: float) -> str:
    """Minuten und Sekunden, ab einer Stunde mit Stunden.

    >>> zeit_text(1930), zeit_text(3725)
    ('32:10', '1:02:05')
    """
    s = max(0, round(sekunden))
    h, rest = divmod(s, 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60}:{rest % 60:02d}"


def tempo_text(sportart: str, s_pro_km: float | None) -> str:
    """Gehen und Laufen als min/km, Rad als km/h.

    >>> tempo_text("laufen", 312), tempo_text("rad", 150), tempo_text("gehen", None)
    ('5:12 /km', '24,0 km/h', '–')
    """
    if s_pro_km is None or s_pro_km <= 0:
        return "–"
    if sportart == RAD:
        return f"{3600 / s_pro_km:.1f} km/h".replace(".", ",")
    return f"{zeit_text(s_pro_km)} /km"


def zahl_text(x: float | None, stellen: int = 0) -> str:
    """Eine Zahl mit Komma, „–“ ohne Wert.

    >>> zahl_text(4.256, 2), zahl_text(None)
    ('4,26', '–')
    """
    if x is None:
        return "–"
    return f"{x:.{stellen}f}".replace(".", ",")


def _zelle(
    text: str, *, kopf: bool = False, fett: bool = False, links: bool = False, expand: int = 1
) -> ft.Text:
    """Eine Zelle wie in „Je Kilometer“: Zahlen rechts, der Kopf klein und blass."""
    return ft.Text(
        text,
        expand=expand,
        size=12 if kopf else 13,
        weight=ft.FontWeight.W_600 if kopf else ft.FontWeight.W_700 if fett else None,
        opacity=0.7 if kopf else 1.0,
        text_align=ft.TextAlign.LEFT if links else ft.TextAlign.RIGHT,
    )


def _tempo_kurz(sportart: str, s_pro_km: float | None) -> str:
    """Tempo ohne Einheit — die steht im Kopf („/km“, Rad „km/h“)."""
    return tempo_text(sportart, s_pro_km).removesuffix(" /km").removesuffix(" km/h")


def intervall_tabelle(
    zeilen: Sequence[Intervall], sportart: str, *, strecke: bool, hf: bool, dfa: bool = False
) -> ft.Control:
    """„Intervalle (vom Timer)“: je Abschnitt Runde, Name und gelaufene Zeit, dazu Strecke,
    Tempo, Ø HF (in der Auswertung auch DFA α1) — der Punkt in der Farbe der Messung, der
    laufende Abschnitt fett."""
    kopf: list[ft.Control] = [_zelle("Runde · Abschnitt", kopf=True, links=True, expand=3)]
    if strecke:
        kopf += [_zelle("km", kopf=True), _zelle("km/h" if sportart == RAD else "/km", kopf=True)]
    if hf:
        kopf.append(_zelle("Ø HF", kopf=True))
    if dfa:
        kopf.append(_zelle("DFA α1", kopf=True))
    reihen: list[ft.Control] = [ft.Row(spacing=4, controls=kopf)]
    for z in zeilen:
        name = f"{z.runde} {z.name}"
        text = f"{name} · läuft" if z.laeuft else f"{name} {zeit_text(z.sekunden)}"
        zellen: list[ft.Control] = [
            ft.Row(
                expand=3,
                spacing=6,
                controls=[
                    ft.Container(width=8, height=8, border_radius=4, bgcolor=z.farbe),
                    _zelle(text, fett=z.laeuft, links=True),
                ],
            )
        ]
        if strecke:
            km = z.distanz_m / 1000 if z.distanz_m is not None else None
            zellen += [
                _zelle(zahl_text(km, 2), fett=z.laeuft),
                _zelle(_tempo_kurz(sportart, z.tempo_s_pro_km), fett=z.laeuft),
            ]
        if hf:
            zellen.append(_zelle(zahl_text(z.herz.hf_bpm), fett=z.laeuft))
        if dfa:
            zellen.append(_zelle(zahl_text(z.herz.dfa_alpha1, 2), fett=z.laeuft))
        reihen.append(ft.Row(spacing=4, controls=zellen))
    return ft.Column(spacing=4, controls=reihen)


def km_tabelle_live(zeilen: Sequence[KmZeile], sportart: str, *, hf: bool) -> ft.Control:
    """„Kilometer (vom GPS)“ während des Trainings: je vollem Kilometer (Rad: fünf) Zeit,
    Tempo und Ø HF."""
    kopf: list[ft.Control] = [
        _zelle("km", kopf=True, links=True),
        _zelle("Zeit", kopf=True),
        _zelle("km/h" if sportart == RAD else "/km", kopf=True),
    ]
    if hf:
        kopf.append(_zelle("Ø HF", kopf=True))
    reihen: list[ft.Control] = [ft.Row(spacing=4, controls=kopf)]
    for z in zeilen:
        zellen: list[ft.Control] = [
            _zelle(f"km {z.km}", links=True),
            _zelle(zeit_text(z.sekunden)),
            _zelle(_tempo_kurz(sportart, z.tempo_s_pro_km)),
        ]
        if hf:
            zellen.append(_zelle(zahl_text(z.herz.hf_bpm)))
        reihen.append(ft.Row(spacing=4, controls=zellen))
    return ft.Column(spacing=4, controls=reihen)


def herz_live(e: Einheitslauf, reihe: HfReihe) -> HerzQuelle | None:
    """Ø HF je Zeitraum aus der laufenden Aufnahme — ``None`` ohne HRV."""
    hrv = e.hrv
    aufnahme = hrv.messlauf.aufnahme if hrv is not None else None
    beteiligung = hrv.beteiligung if hrv is not None else None
    if aufnahme is None or beteiligung is None or beteiligung.versatz_s is None:
        return None
    reihe.nachladen(aufnahme.beats, beteiligung.versatz_s, aufnahme)
    return reihe.herz


@dataclass(frozen=True, slots=True)
class LiveTabellen:
    """Was „Intervalle (vom Timer)“ und „Kilometer (vom GPS)“ einer laufenden Einheit
    zeigen — in der Ausdauer-Ansicht und in der Übersicht im Reiter „Einheit“."""

    runden: list[Intervall]
    km: list[KmZeile]
    #: mit Ø HF (eine HRV-Aufnahme läuft mit), mit Strecke (GPS)
    herz: bool
    strecke: bool

    def schluessel(self) -> tuple:
        """Neu gebaut wird nur, wenn sich eine angezeigte Zahl ändert."""
        return (
            self.herz,
            self.strecke,
            tuple(
                (
                    z.runde,
                    z.name,
                    z.laeuft,
                    None if z.laeuft else round(z.sekunden),
                    None if z.distanz_m is None else round(z.distanz_m / 10),
                    None if z.tempo_s_pro_km is None else round(z.tempo_s_pro_km),
                    None if z.herz.hf_bpm is None else round(z.herz.hf_bpm),
                )
                for z in self.runden
            ),
            tuple(
                (z.km, round(z.sekunden), None if z.herz.hf_bpm is None else round(z.herz.hf_bpm))
                for z in self.km
            ),
        )


def live_tabellen(e: Einheitslauf, reihe: HfReihe) -> LiveTabellen:
    """Die Abschnitte des Timers und die Kilometer bis jetzt — mit Strecke, wenn ein
    Training mit GPS läuft, mit Ø HF, wenn die HRV mitläuft."""
    herz = herz_live(e, reihe)
    teil = e.teil("gps")
    if not isinstance(teil, StreckeBaustein):
        runden = intervalle(e.ereignisse, jetzt_s=e.dauer_s(), herz=herz)
        return LiveTabellen(runden, [], herz is not None, False)
    versatz = teil.versatz_s if teil.mit_gps else None
    strecke = strecke_auf_achse(teil.rechner, versatz) if versatz is not None else None
    runden = intervalle(e.ereignisse, jetzt_s=e.dauer_s(), strecke=strecke, herz=herz)
    km = kilometer(teil.rechner.splits, versatz_s=versatz, herz=herz)
    return LiveTabellen(runden, km, herz is not None, strecke is not None)


__all__ = [
    "LiveTabellen",
    "herz_live",
    "intervall_tabelle",
    "km_tabelle_live",
    "km_text",
    "live_tabellen",
    "tempo_text",
    "zahl_text",
    "zeit_text",
]
