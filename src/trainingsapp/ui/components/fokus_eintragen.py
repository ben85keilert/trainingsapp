"""Die Karte „Eintragen“ im Fokus (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §1, Skizze F2).

Eine Karte für den Timer der Übung (`views/uebung_timer.py`) und das Workout
(`views/workout.py`): die **Ausprägungen** der (Plan-)Übung — Variante und Seite als Chips,
Gewicht und Winkel mit −/+ —, die **Wiederholungen** von Hand je Satz (nur, wo weder Sensor noch
Takt zählen, P122) und die **Skala**. Was eine Runde des Timers festlegt
(`core.timer.Abschnitt.ausfuehrung`), steht fest da („aus der Runde“).

Jede Eingabe geht als ``person/…`` in die Zeitleiste (``wdh``, ``skala``, ``auspraegung``);
eingetragen wird erst mit dem Ende des Laufs (P150, `ui.uebung_lauf._eintragen`), Abbrechen
verwirft. Die Wahl der Ausprägungen gilt auch im Block danach (`AppState.auspraegung_wahl`).

Welcher Satz läuft, welche Ausführung gilt und was schon eingegeben ist, rechnet
`core.timer_eintrag` (`stelle`, `satz_nummer`, `eingaben`); hier steht nur das Zeichnen. Die
Karte wird **einmal gebaut**; `nachziehen` baut sie nur neu, wenn sich Satz, Ausführung oder
eine Eingabe änderten (V1).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from trainingsapp.core import zaehlen as zl
from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.core.plaene import einzel_plan
from trainingsapp.core.result_spec import FieldSpec, FieldType, wert_text
from trainingsapp.core.standards import chips_fuer, mit_plan_spec, ziel_von
from trainingsapp.core.timer_eintrag import eingaben, gelaufene_zeiten, satz_nummer, stelle
from trainingsapp.core.uebung_timer import ausfuehrungsfelder
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.ui.components import zaehl_stand

#: Der Satz der Wiederholungen im Workout — der Text bleibt, wie die Tests ihn kennen
WDH_TITEL = "Wiederholungen — niemand zählt, trag sie hier ein"


#: Was im „i“ der Karte steht (Ben, 8.11.2026 spät: „Infotext unten kommt in ein i“)
INFO = (
    "**Eintragen im Fokus.** Jeder Knopf „+12“ trägt einen Satz ein — wie im Block; „−“ nimmt "
    "den letzten zurück, alles Weitere geht später unter „Heute geleistet“.\n\n"
    "Die Zeit kommt von der Uhr. Eingetragen wird mit „Fertig“ — „Abbrechen“ verwirft auch "
    "diese Eingaben."
)


def kopf(page: Any, titel: str = "EINTRAGEN") -> ft.Control:
    """Der Kopf der Karte: Titel in Großbuchstaben und das „i“."""
    from trainingsapp.ui.components.karte import info_knopf

    return ft.Row(
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(titel, size=11, weight=ft.FontWeight.W_700, opacity=0.65, expand=True),
            info_knopf(page, "Eintragen im Fokus", INFO),
        ],
    )


def karte(*zeilen: ft.Control, page: Any = None, titel: str = "EINTRAGEN") -> ft.Container:
    """Der Rahmen der Karte — Kopf (mit „i“, wenn ``page``), darunter die Zeilen."""
    oben: ft.Control = (
        kopf(page, titel)
        if page is not None
        else ft.Text(titel, size=11, weight=ft.FontWeight.W_700, opacity=0.65)
    )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column(spacing=8, controls=[oben, *zeilen]),
    )


def saetze_zeile(
    saetze: Sequence[int],
    werte: Sequence[int],
    dazu: Callable[[int], Callable[..., None]],
    weg: Callable[..., None],
    *,
    titel: str = WDH_TITEL,
) -> ft.Control:
    """Die Wiederholungen wie im Block (Ben, 8.11.2026 spät: „Einträge müssen erweitert werden
    können … Dort die Buttons rein, die man auch in der Normalansicht hat“): die Sätze bisher,
    „+N“-Knöpfe — jeder Tipp ein Satz dazu —, ein eigener Wert und „−“ für den letzten."""
    stand = " · ".join(str(w) for w in saetze) if saetze else "noch kein Satz"
    if len(saetze) > 1:
        stand += f"  = {sum(saetze)}"

    def eigen_eintragen(e: Any) -> None:
        text = str(getattr(e.control, "value", "") or "").strip()
        if text.isdigit() and int(text) > 0:
            dazu(int(text))()

    return ft.Column(
        spacing=6,
        controls=[
            ft.Text(titel, size=12, opacity=0.75),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(stand, size=18, weight=ft.FontWeight.W_600, expand=True),
                    ft.IconButton(
                        ft.Icons.REMOVE,
                        tooltip="Letzten Satz zurücknehmen",
                        disabled=not saetze,
                        on_click=weg,
                    ),
                ],
            ),
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *(
                        ft.FilledButton(
                            content=ft.Text(
                                f"+{w}", size=15, weight=ft.FontWeight.W_700, no_wrap=True
                            ),
                            height=44,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=22),
                                padding=ft.Padding.symmetric(horizontal=12),
                            ),
                            on_click=dazu(w),
                        )
                        for w in werte
                    ),
                    ft.TextField(
                        width=80,
                        height=44,
                        dense=True,
                        hint_text="Wert",
                        keyboard_type=ft.KeyboardType.NUMBER,
                        tooltip="Eigener Wert — Eingabe schickt ihn als Satz ab",
                        on_submit=eigen_eintragen,
                    ),
                ],
            ),
        ],
    )


def wdh_werte(planuebung: PlanItem, u: Exercise, feld: str | None, ziel: int | None) -> list[int]:
    """Die Knöpfe wie im Block (`core.standards.chips_fuer`) — ohne eigene die Vorgabe."""
    spec = next((f for f in u.result_spec.fields if f.key == feld), None)
    werte = (
        [int(w) for w in chips_fuer(planuebung, spec) if isinstance(w, int | float)] if spec else []
    )
    return werte or sorted({w for w in (ziel, 5, 10, 12, 15, 20) if w})


def _schritt(f: FieldSpec) -> float:
    """Schrittweite von −/+ — die des Felds, sonst 1 kg bzw. 5°."""
    return float(f.step) if f.step else (1.0 if f.type == FieldType.WEIGHT else 5.0)


def _zahl(x: float) -> int | float:
    return int(x) if float(x).is_integer() else round(x, 2)


def auspraegung_zeilen(
    felder: Sequence[FieldSpec],
    werte: Mapping[str, Any],
    fest: Mapping[str, Any],
    setzen: Callable[[str, Any], Callable[..., None]],
) -> list[ft.Control]:
    """Je Ausprägung eine Zeile: Chips (Variante, Seite) oder −/+ (Gewicht, Winkel). Was die
    Runde festlegt (``fest``), steht als Chip ohne Wahl da — „aus der Runde“."""
    zeilen: list[ft.Control] = []
    for f in felder:
        kopf = ft.Text(f.label, size=13, width=96)
        if f.key in fest:
            zeilen.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        kopf,
                        ft.Chip(
                            label=ft.Text(wert_text(f, fest[f.key]) or str(fest[f.key])),
                            selected=True,
                            show_checkmark=False,
                            disabled=True,
                        ),
                        ft.Text("aus der Runde", size=12, opacity=0.6),
                    ],
                )
            )
            continue
        wert = werte.get(f.key)
        if f.type == FieldType.CHOICE:
            zeilen.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        kopf,
                        ft.Row(
                            wrap=True,
                            spacing=4,
                            run_spacing=4,
                            expand=True,
                            controls=[
                                ft.Chip(
                                    label=ft.Text(str(o)),
                                    selected=wert == o,
                                    show_checkmark=False,
                                    tooltip="noch einmal tippen: ohne",
                                    on_select=setzen(f.key, None if wert == o else o),
                                )
                                for o in f.quick
                            ],
                        ),
                    ],
                )
            )
            continue
        schritt = _schritt(f)
        basis = float(wert) if isinstance(wert, int | float) else None
        zeilen.append(
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    kopf,
                    ft.IconButton(
                        ft.Icons.REMOVE,
                        tooltip=f"{f.label} weniger",
                        on_click=setzen(
                            f.key,
                            None
                            if basis is None or basis - schritt <= 0
                            else _zahl(basis - schritt),
                        ),
                    ),
                    ft.Text(
                        wert_text(f, wert) if basis is not None else "—",
                        size=16,
                        weight=ft.FontWeight.W_600,
                        width=72,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.IconButton(
                        ft.Icons.ADD,
                        tooltip=f"{f.label} mehr",
                        on_click=setzen(
                            f.key,
                            _zahl((basis or 0.0) + schritt)
                            if basis is not None
                            else _zahl(float(f.quick[0]) if f.quick else schritt),
                        ),
                    ),
                ],
            )
        )
    return zeilen


def skala_zeile(
    feld: FieldSpec, gewaehlt: Any, waehlen: Callable[[int], Callable[..., None]]
) -> ft.Control:
    """Die Skala der Übung als Chips (wie im Workout)."""
    lo = int(feld.min) if feld.min is not None else 0
    hi = int(feld.max) if feld.max is not None else 10
    if hi - lo > 20:
        lo, hi = 0, 10
    return ft.Column(
        spacing=4,
        controls=[
            ft.Text(feld.label or "Skala", size=13),
            ft.Row(
                wrap=True,
                spacing=4,
                run_spacing=4,
                controls=[
                    ft.Chip(
                        label=ft.Text(str(w)),
                        selected=gewaehlt is not None and str(gewaehlt) == str(w),
                        show_checkmark=False,
                        on_select=waehlen(w),
                    )
                    for w in range(lo, hi + 1)
                ],
            ),
        ],
    )


def wahl_schluessel(uebung: Exercise, item: PlanItem | None) -> str:
    """Unter welchem Schlüssel der Block die Ausprägungen merkt (`AppState.auspraegung_wahl`)."""
    return (item if item is not None else einzel_plan(uebung).items[0]).id


def ausfuehrung_waehlen(
    state: Any, uebung: Exercise, item: PlanItem | None, key: str, wert: Any
) -> dict[str, Any]:
    """Eine Ausprägung für die Übung wählen — wie im Block; gibt die ganze Wahl zurück."""
    from trainingsapp.ui.uebung_lauf import gewaehlte_ausfuehrung

    wahl = dict(gewaehlte_ausfuehrung(state, uebung, item))
    if wert is None:
        wahl.pop(key, None)
    else:
        wahl[key] = wert
    state.auspraegung_wahl[wahl_schluessel(uebung, item)] = wahl
    return wahl


class EintragenKarte:
    """Die Karte „Eintragen“ im Fokus des Übungs-Timers — einmal gebaut, `nachziehen` je Tick.

    ``aendern`` wird nach jeder Eingabe gerufen (die Ansicht frischt auf)."""

    def __init__(
        self,
        page: Any,
        state: Any,
        *,
        uebung: Exercise,
        item: PlanItem | None,
        aendern: Callable[[], None] | None = None,
    ) -> None:
        self.page = page
        self.state = state
        self.uebung = uebung
        self.item = item
        self.aendern = aendern
        planuebung = item if item is not None else einzel_plan(uebung).items[0]
        self.u = mit_plan_spec(planuebung, uebung)
        self.felder = ausfuehrungsfelder(self.u.result_spec)
        self.wdh_feld = zl.zaehlt_in(uebung, item)
        ziel = ziel_von(planuebung, self.u).get(self.wdh_feld or "")
        erstes = ziel[0] if isinstance(ziel, list) and ziel else ziel
        self.ziel: int | None = int(erstes) if isinstance(erstes, int | float) else None
        self.werte = wdh_werte(planuebung, self.u, self.wdh_feld, self.ziel)
        self.skala = next((f for f in self.u.result_spec.fields if f.type == FieldType.SCALE), None)
        self.spalte = ft.Column(spacing=8)
        self.control = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=self.spalte,
            visible=not self.leer,
        )
        self._stand: tuple[Any, ...] | None = None
        self._e: Einheitslauf | None = None

    @property
    def leer(self) -> bool:
        """Nichts einzutragen — die Übung hat weder Ausprägung noch Wiederholungen noch Skala."""
        return not (self.felder or self.wdh_feld or self.skala)

    # -- Lage ------------------------------------------------------------------------------

    def _jetzt_s(self, e: Einheitslauf) -> float:
        return max(0.0, e.uhr() - e.t0) if e.t0 is not None else 0.0

    def _lage(self, e: Einheitslauf) -> dict[str, Any]:
        """Satz, Ausführung der Runde und die Eingaben — aus der Zeitleiste."""
        jetzt = self._jetzt_s(e)
        zeiten = gelaufene_zeiten(e.ereignisse, min_s=0.0, jetzt_s=jetzt)
        i = stelle(zeiten, jetzt) if zeiten else 0
        eing = eingaben(e.ereignisse, zeiten)
        fest = dict(zeiten[i].ausfuehrung) if zeiten else {}
        from trainingsapp.ui.uebung_lauf import gewaehlte_ausfuehrung

        wahl = (
            eing.auspraegung
            if eing.auspraegung is not None
            else gewaehlte_ausfuehrung(self.state, self.uebung, self.item)
        )
        z = zaehl_stand.zaehl_teil(self.state, self.uebung.id, self.item.id if self.item else None)
        zaehlt = z is not None and bool(z.wdh)
        return {
            "stelle": i,
            "satz": satz_nummer(zeiten, i),
            "fest": fest,
            "wahl": {k: v for k, v in wahl.items() if k in AUSFUEHRUNG_SCHLUESSEL},
            # Die Sätze dieser Ausführung (je Runde), sonst alle des Laufs
            "saetze": tuple(
                eing.werte(zeiten, fest if any(z.ausfuehrung for z in zeiten) else None).get(
                    self.wdh_feld or "", []
                )
            ),
            "skala": eing.skala.get(self.skala.key, {}).get(i) if self.skala else None,
            "zaehlt": zaehlt,
        }

    # -- Schreiben -------------------------------------------------------------------------

    def _schreiben(self, art: str, text: str, daten: dict[str, Any]) -> None:
        e = self._e
        if e is None or e.t0 is None:
            return
        if self.item is not None:
            daten = {"planuebung": self.item.id, **daten}
        e.nachtragen(Ereignis(self._jetzt_s(e), "person", art, text, daten))
        self.nachziehen(e)
        if self.aendern is not None:
            self.aendern()

    def _wdh(self, n: int) -> Callable[..., None]:
        """„+N“: ein Satz dazu (Ben: erweitern statt ersetzen)."""

        def handler(_e: Any = None) -> None:
            self._schreiben(
                "wdh",
                f"{self.uebung.name}: +{n} Wdh.",
                {"feld": self.wdh_feld or "", "wert": max(0, n), "dazu": True},
            )

        return handler

    def _weg(self, _e: Any = None) -> None:
        """„−“: den letzten Satz zurücknehmen."""
        self._schreiben(
            "wdh",
            f"{self.uebung.name}: letzter Satz zurück",
            {"feld": self.wdh_feld or "", "wert": None, "dazu": True},
        )

    def _skala(self, wert: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            feld = self.skala.key if self.skala is not None else ""
            self._schreiben(
                "skala", f"{self.uebung.name}: Skala {wert}", {"feld": feld, "wert": wert}
            )

        return handler

    def _auspraegung(self, key: str, wert: Any) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            wahl = ausfuehrung_waehlen(self.state, self.uebung, self.item, key, wert)
            daten: dict[str, Any] = {k: wahl.get(k) for k in AUSFUEHRUNG_SCHLUESSEL}
            text = " · ".join(str(v) for v in wahl.values() if v not in (None, ""))
            self._schreiben("auspraegung", f"{self.uebung.name}: {text or 'ohne'}", daten)

        return handler

    # -- Zeichnen --------------------------------------------------------------------------

    def _zeilen(self, lage: Mapping[str, Any]) -> list[ft.Control]:
        zeilen: list[ft.Control] = [kopf(self.page)]
        zeilen.extend(
            auspraegung_zeilen(self.felder, lage["wahl"], lage["fest"], self._auspraegung)
        )
        if self.wdh_feld and not lage["zaehlt"]:
            zeilen.append(
                saetze_zeile(
                    list(lage["saetze"]),
                    self.werte,
                    self._wdh,
                    self._weg,
                    titel="Wiederholungen — niemand zählt",
                )
            )
        if self.skala is not None:
            zeilen.append(skala_zeile(self.skala, lage["skala"], self._skala))
        return zeilen

    def bauen(self, e: Einheitslauf) -> ft.Control:
        """Die Karte für diesen Lauf — einmal, dann `nachziehen`."""
        self._e = e
        self._stand = None
        self.nachziehen(e, aktualisieren=False)
        return self.control

    def nachziehen(self, e: Einheitslauf, *, aktualisieren: bool = True) -> None:
        """Je Tick: nur neu bauen, wenn sich Satz, Ausführung oder eine Eingabe änderte."""
        if self.leer:
            return
        self._e = e
        lage = self._lage(e)
        stand = tuple(
            (k, tuple(sorted(v.items())) if isinstance(v, dict) else v)
            for k, v in sorted(lage.items())
        )
        if stand == self._stand:
            return
        self._stand = stand
        self.spalte.controls = self._zeilen(lage)
        if aktualisieren:
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                self.control.update()


__all__ = [
    "WDH_TITEL",
    "EintragenKarte",
    "ausfuehrung_waehlen",
    "auspraegung_zeilen",
    "karte",
    "saetze_zeile",
    "skala_zeile",
    "wahl_schluessel",
    "wdh_werte",
]
