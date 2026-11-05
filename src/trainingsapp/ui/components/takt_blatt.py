"""Das Takt-Blatt (`docs/plan_taktgeber.md` §5): Vorlagen als Chips, die Phasen des gewählten
Takts als Zeilen (Name, Sekunden, Art, Klang, ✕), „+ Phase“, der Tempo-Regler (0,5×–2× mit Rate
und Rundendauer), die Vorschau (die Animation läuft im Blatt) und die Knöpfe „Für jetzt“ /
„In die Übung“ / „In die Bibliothek“ — je nachdem, von wo es geöffnet wurde.

Von unten (`components/blatt.blatt_spalte`): der Inhalt scrollt, die Knöpfe stehen fest über
der Navigationsleiste. Die Zeilen werden beim Ändern der Phasenliste neu gebaut (nicht je
Tick); die Vorschau tickt in einer eigenen Aufgabe, solange das Blatt offen ist, und setzt nur
Werte (`TaktAnzeige.nachziehen`). Keine Rechenlogik: Lage, Rate, Tempo kommen aus `core.takt`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import flet as ft

from trainingsapp.core.klang import KLAENGE
from trainingsapp.core.takt import (
    ANIMATIONEN,
    ARTEN,
    AUS,
    KLANG_VORGABE,
    MAX_PHASEN,
    TEMPO_MAX,
    TEMPO_MIN,
    VORLAGEN,
    Phase,
    Takt,
    TaktLauf,
    dauer_lesen,
    dauer_text,
    in_bibliothek,
    rate_text,
    tempo_lesen,
    tempo_text,
)
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.takt_anzeige import TaktAnzeige

#: Symbol des Taktgebers — Material kennt kein Metronom; der Ausschlag steht für den Takt
SYMBOL = ft.Icons.GRAPHIC_EQ
#: So oft zieht die Vorschau nach (s)
VORSCHAU_S = 0.2


@dataclass
class _Zeile:
    """Eine Phase im Blatt."""

    name: ft.TextField
    dauer: ft.TextField
    art: ft.Dropdown
    klang: ft.Dropdown


def takt_blatt(
    page: Any,
    state: Any,
    *,
    takt: Takt | None,
    titel: str = "Takt",
    fuer_jetzt: Callable[[Takt | None], Any] | None = None,
    in_die_uebung: Callable[[Takt | None], Any] | None = None,
    in_den_abschnitt: Callable[[Takt | None], Any] | None = None,
    starten: Callable[[Takt], Any] | None = None,
    zuruecksetzen: Callable[[], Any] | None = None,
    uebung_name: str = "",
) -> ft.BottomSheet:
    """Das Blatt. ``takt`` ist der Ausgangspunkt (``None`` = die erste Vorlage); jeder Knopf
    bekommt den gebauten Takt — oder ``None`` für „kein Takt“ (✕ „Kein Takt“). ``fuer_jetzt``:
    nur für diese Sitzung (P139); ``in_die_uebung`` / ``in_den_abschnitt``: speichern dort;
    ``starten``: „Takt starten“ — eine Uhr mit diesem Takt für jetzt; ``zuruecksetzen``: „Wie
    eingestellt“ — die Wahl für jetzt fällt weg, Abschnitt und Übung gelten wieder."""
    nachher = Nachher()
    blatt: ft.BottomSheet
    zeilen: list[_Zeile] = []
    stand: dict[str, Any] = {
        "name": takt.name if takt is not None else "",
        "tempo": takt.tempo if takt is not None else 1.0,
        "runden": takt.runden if takt is not None else None,
        "animation": takt.animation if takt is not None else "",
        "zaehlt": takt.zaehlt if takt is not None else False,
        "vorlage": "",
        "laeuft": True,
    }
    eigene = state.takt_bibliothek() if hasattr(state, "takt_bibliothek") else []
    name_feld = ft.TextField(label="Name", dense=True, value=stand["name"], hint_text="z. B. 4-7-8")
    phasen_spalte = ft.Column(spacing=6, tight=True)
    tempo_text_ctl = ft.Text(size=13, weight=ft.FontWeight.W_600)
    rate_text_ctl = ft.Text(size=12, opacity=0.75)
    fehler_text = ft.Text(size=12, color=ft.Colors.ERROR, visible=False)
    anzeige = TaktAnzeige(groesse=150)

    def phasen_lesen() -> list[Phase] | None:
        """Die Phasen aus den Zeilen — ``None`` (Felder markiert), wenn eine Dauer unlesbar ist."""
        phasen: list[Phase] = []
        fehler = False
        for z in zeilen:
            dauer = dauer_lesen(z.dauer.value or "")
            z.dauer.error = None if dauer is not None else "0,1–600"
            fehler = fehler or dauer is None
            if dauer is not None:
                art = str(z.art.value or "frei")
                klang = str(z.klang.value or "")
                phasen.append(
                    Phase(
                        (z.name.value or "").strip(),
                        dauer,
                        art if art in ARTEN else "frei",
                        klang if klang in KLAENGE else "",
                    )
                )
        return None if fehler or not phasen else phasen

    def bauen() -> Takt | None:
        phasen = phasen_lesen()
        if phasen is None:
            return None
        return Takt(
            tuple(phasen),
            name=(name_feld.value or "").strip(),
            tempo=tempo_lesen(stand["tempo"]),
            runden=stand["runden"],
            animation=stand["animation"],
            zaehlt=bool(stand["zaehlt"]),
        )

    def auffrischen(*ctl: ft.Control) -> None:
        for c in ctl:
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                c.update()

    def tempo_zeigen() -> None:
        t = bauen()
        tempo_text_ctl.value = f"Tempo {tempo_text(stand['tempo'])}"
        if t is None:
            rate_text_ctl.value = ""
        else:
            rate_text_ctl.value = (
                f"{rate_text(t.rate_pro_min)} · Runde {dauer_text(t.rundendauer_s)} s"
                + (f" · {len(t.phasen)} Phasen" if len(t.phasen) != 1 else " · 1 Phase")
            )

    def geaendert(_e: object = None) -> None:
        """Ein Feld geändert: Rate neu, Vorschau neu — die Zeilen bleiben."""
        stand["vorlage"] = ""
        tempo_zeigen()
        vorschau_neu()
        auffrischen(tempo_text_ctl, rate_text_ctl, vorlagen)

    def art_gewaehlt(z: _Zeile) -> Callable[[Any], None]:
        def handler(_e: object = None) -> None:
            # Der Klang folgt der Art, solange keiner gewählt ist — die Vorgabe steht im Menü
            z.klang.options = _klang_optionen(str(z.art.value or "frei"))
            auffrischen(z.klang)
            geaendert()

        return handler

    def zeile(p: Phase) -> _Zeile:
        art = ft.Dropdown(
            value=p.art,
            options=[ft.DropdownOption(key=k, text=v) for k, v in ARTEN.items()],
            dense=True,
            expand=True,
            border_radius=8,
            text_size=13,
        )
        klang = ft.Dropdown(
            value=p.klang or "",
            options=_klang_optionen(p.art),
            dense=True,
            expand=True,
            border_radius=8,
            text_size=13,
        )
        z = _Zeile(
            ft.TextField(
                label="Phase",
                value=p.name,
                dense=True,
                expand=True,
                hint_text=ARTEN[p.art].lower(),
                on_change=geaendert,
            ),
            ft.TextField(
                label="s",
                value=dauer_text(p.dauer_s),
                dense=True,
                width=64,
                keyboard_type=ft.KeyboardType.NUMBER,
                text_align=ft.TextAlign.END,
                on_change=geaendert,
            ),
            art,
            klang,
        )
        art.on_select = art_gewaehlt(z)
        klang.on_select = geaendert
        return z

    def entferner(i: int) -> Callable[[], None]:
        def handler() -> None:
            if len(zeilen) > 1:
                del zeilen[i]
                zeichnen()
                geaendert()
                auffrischen(phasen_spalte)

        return handler

    def hinzufuegen() -> None:
        if len(zeilen) >= MAX_PHASEN:
            return
        letzte = zeilen[-1] if zeilen else None
        art = str(letzte.art.value) if letzte is not None else "frei"
        folge = {"ein": "aus", "aus": "ein", "ab": "auf", "auf": "ab"}
        zeilen.append(zeile(Phase("", 4, folge.get(art, art))))
        zeichnen()
        geaendert()
        auffrischen(phasen_spalte)

    def zeichnen() -> None:
        phasen_spalte.controls = [
            ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(f"{i + 1}.", size=12, opacity=0.6, width=18),
                            z.name,
                            z.dauer,
                            ft.IconButton(
                                ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                tooltip="Phase entfernen",
                                icon_size=20,
                                on_click=entferner(i),
                                disabled=len(zeilen) <= 1,
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[ft.Container(width=18), z.art, z.klang],
                    ),
                ],
            )
            for i, z in enumerate(zeilen)
        ]

    def uebernehmen(t: Takt) -> None:
        """Ein Takt (Vorlage, Bibliothek, Ausgangspunkt) in die Felder."""
        zeilen.clear()
        zeilen.extend(zeile(p) for p in t.phasen)
        name_feld.value = t.name
        stand["tempo"] = t.tempo
        stand["runden"] = t.runden
        stand["animation"] = t.animation
        stand["zaehlt"] = t.zaehlt
        zaehlt_schalter.value = t.zaehlt
        regler.value = t.tempo
        animation_wahl.value = t.animation
        zeichnen()
        tempo_zeigen()
        vorschau_neu()

    def vorlage_waehlen(schluessel: str, t: Takt) -> Callable[[], None]:
        def handler() -> None:
            uebernehmen(t)
            stand["vorlage"] = schluessel
            for chip in vorlagen.controls:
                if isinstance(chip, ft.Chip):
                    chip.selected = chip.data == schluessel
            auffrischen(blatt)

        return handler

    vorlagen = ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=6,
        controls=[
            *(
                ft.Chip(
                    label=ft.Text(t.name, size=12),
                    data=k,
                    show_checkmark=False,
                    on_click=vorlage_waehlen(k, t),
                )
                for k, t in VORLAGEN.items()
            ),
            *(
                ft.Chip(
                    label=ft.Text(t.name or t.phasen_text(), size=12),
                    leading=ft.Icon(ft.Icons.BOOKMARK_OUTLINE, size=16),
                    data=f"eigen:{t.name}",
                    show_checkmark=False,
                    on_click=vorlage_waehlen(f"eigen:{t.name}", t),
                )
                for t in eigene
            ),
        ],
    )

    def tempo_gezogen(e: ft.Event[ft.Slider]) -> None:
        ohne_auto_update()  # beim Ziehen dauernd — nur die Texte nachziehen (V1)
        stand["tempo"] = tempo_lesen(e.control.value)
        tempo_zeigen()
        vorschau_tempo()
        auffrischen(tempo_text_ctl, rate_text_ctl)

    regler = ft.Slider(
        min=TEMPO_MIN,
        max=TEMPO_MAX,
        divisions=int((TEMPO_MAX - TEMPO_MIN) / 0.05),
        value=stand["tempo"],
        round=2,
        expand=True,
        on_change=tempo_gezogen,
    )

    def zaehlt_geschaltet(e: ft.Event[ft.Switch]) -> None:
        stand["zaehlt"] = bool(e.control.value)

    # „Takt zählt“ (P138, Teil 2 T5): jede volle Runde eine Wiederholung — ein Zähl-Teil mit
    # Quelle „takt“, auch ohne Sensor; bei Atemtakten erlaubt (Atemzüge in ein
    # Wiederholungsfeld), von Haus aus nur bei den Bewegungs-Vorlagen an
    zaehlt_schalter = ft.Switch(
        label="Takt zählt Wiederholungen",
        value=bool(stand["zaehlt"]),
        label_position=ft.LabelPosition.LEFT,
        tooltip="Jede volle Runde eine Wiederholung — auch ohne Sensor (gekennzeichnet „Takt“)",
        on_change=zaehlt_geschaltet,
    )

    def animation_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        wert = str(e.control.value or "")
        stand["animation"] = wert if wert in ANIMATIONEN else ""
        vorschau_neu()

    animation_wahl = ft.Dropdown(
        label="Animation",
        value=stand["animation"],
        options=[
            ft.DropdownOption(key="", text="nach Phasenzahl"),
            *(ft.DropdownOption(key=k, text=v) for k, v in ANIMATIONEN.items()),
        ],
        dense=True,
        expand=True,
        border_radius=8,
        text_size=13,
        on_select=animation_gewaehlt,
    )

    # -- Vorschau: die Animation läuft im Blatt ----------------------------------------------

    vorschau: dict[str, Any] = {"lauf": None, "t0": time.monotonic()}

    def vorschau_neu() -> None:
        t = bauen()
        vorschau["lauf"] = TaktLauf(t) if t is not None else None
        vorschau["t0"] = time.monotonic()
        vorschau_ziehen()

    def vorschau_tempo() -> None:
        """Der Regler wirkt sofort, die Lage springt nicht (wie im Lauf)."""
        lauf = vorschau["lauf"]
        if lauf is None:
            vorschau_neu()
            return
        lauf.takt = replace(lauf.takt, tempo=1.0)
        lauf.tempo_setzen(time.monotonic() - vorschau["t0"], stand["tempo"])

    def vorschau_ziehen() -> None:
        lauf = vorschau["lauf"]
        if lauf is None:
            anzeige.nachziehen(None, None)
            return
        anzeige.nachziehen(lauf.effektiv, lauf.lage(time.monotonic() - vorschau["t0"]))

    async def vorschau_ticken() -> None:
        while stand["laeuft"]:
            vorschau_ziehen()
            auffrischen(anzeige.control)
            await asyncio.sleep(VORSCHAU_S)

    # -- Knöpfe -------------------------------------------------------------------------------

    def pruefen() -> Takt | None:
        t = bauen()
        fehler_text.visible = t is None
        fehler_text.value = "Eine Dauer ist unlesbar — Sekunden, auch 2,5." if t is None else ""
        auffrischen(fehler_text, phasen_spalte)
        return t

    def weg(aktion: Callable[[], Any]) -> None:
        stand["laeuft"] = False
        nachher.danach(aktion)
        schliessen(blatt)

    def mit_takt(ziel: Callable[[Takt | None], Any]) -> Callable[[], None]:
        def handler() -> None:
            t = pruefen()
            if t is None:
                return
            weg(lambda: ziel(t))

        return handler

    def kein_takt() -> None:
        ziel = fuer_jetzt or in_den_abschnitt or in_die_uebung
        if ziel is not None:
            weg(lambda: ziel(None))

    def in_bibliothek_legen() -> None:
        t = pruefen()
        if t is None:
            return
        if not t.name:
            name_feld.error = "Ein Name, bitte."
            auffrischen(name_feld)
            return
        name_feld.error = None
        state.takt_bibliothek_setzen(in_bibliothek(state.takt_bibliothek(), t))
        nachher.danach(
            lambda: page.show_dialog(ft.SnackBar(ft.Text(f"„{t.name}“ in der Takt-Bibliothek")))
        )
        stand["laeuft"] = False
        schliessen(blatt)

    def takt_starten() -> None:
        t = pruefen()
        if t is None or starten is None:
            return
        weg(lambda: starten(t))

    knoepfe: list[ft.Control] = []
    if starten is not None:
        knoepfe.append(
            ft.FilledButton("Takt starten", icon=ft.Icons.PLAY_ARROW, on_click=takt_starten)
        )
    if fuer_jetzt is not None:
        knoepfe.append(
            ft.FilledTonalButton(
                "Für jetzt",
                icon=ft.Icons.CHECK,
                tooltip="Gilt für diese Sitzung — die Übung bleibt, wie sie ist",
                on_click=mit_takt(fuer_jetzt),
            )
        )
    if in_den_abschnitt is not None:
        knoepfe.append(
            ft.FilledTonalButton(
                "In den Abschnitt", icon=ft.Icons.CHECK, on_click=mit_takt(in_den_abschnitt)
            )
        )
    if in_die_uebung is not None:
        knoepfe.append(
            ft.OutlinedButton(
                f"In die Übung{' „' + uebung_name + '“' if uebung_name else ''}",
                icon=ft.Icons.SAVE_OUTLINED,
                on_click=mit_takt(in_die_uebung),
            )
        )
    knoepfe.append(
        ft.OutlinedButton(
            "In die Bibliothek", icon=ft.Icons.BOOKMARK_ADD_OUTLINED, on_click=in_bibliothek_legen
        )
    )
    if fuer_jetzt is not None or in_den_abschnitt is not None or in_die_uebung is not None:
        knoepfe.append(
            ft.TextButton("Kein Takt", icon=ft.Icons.CLOSE, on_click=kein_takt, tooltip="Takt aus")
        )
    if zuruecksetzen is not None:
        knoepfe.append(
            ft.TextButton(
                "Wie eingestellt",
                icon=ft.Icons.UNDO,
                tooltip="Die Wahl für jetzt vergessen — Abschnitt und Übung gelten wieder",
                on_click=lambda: weg(zuruecksetzen),
            )
        )

    async def abgewiesen(e: Any) -> None:
        stand["laeuft"] = False
        await nachher.bei_schliessen(e)

    name_feld.on_change = geaendert
    uebernehmen(takt if takt is not None and not takt.leer else next(iter(VORLAGEN.values())))
    if takt is None or takt.leer:
        stand["vorlage"] = next(iter(VORLAGEN))
    else:  # eine Vorlage (oder ein eigener Takt) unverändert: ihr Chip ist gewählt
        stand["vorlage"] = next(
            (k for k, v in VORLAGEN.items() if v == takt),
            next((f"eigen:{v.name}" for v in eigene if v == takt), ""),
        )
    for chip in vorlagen.controls:
        if isinstance(chip, ft.Chip):
            chip.selected = chip.data == stand["vorlage"]
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=abgewiesen,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Icon(SYMBOL, size=22),
                        ft.Text(titel, size=20, weight=ft.FontWeight.W_500),
                        ft.Text("Phasen · Tempo · Klang", size=13, opacity=0.7),
                    ],
                ),
                vorlagen,
                ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[anzeige.control]),
                name_feld,
                phasen_spalte,
                ft.Row(
                    controls=[
                        ft.TextButton("Phase", icon=ft.Icons.ADD, on_click=hinzufuegen),
                        ft.Container(expand=True),
                        animation_wahl,
                    ]
                ),
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[ft.Icon(ft.Icons.SPEED, size=18), tempo_text_ctl, rate_text_ctl],
                ),
                regler,
                ft.Row(alignment=ft.MainAxisAlignment.END, controls=[zaehlt_schalter]),
                fehler_text,
            ],
            [ft.Row(wrap=True, spacing=6, run_spacing=6, controls=knoepfe)],
            geschaetzt=600,
        ),
    )
    with contextlib.suppress(Exception):  # ohne Seite (Tests): die Vorschau steht
        page.run_task(vorschau_ticken)
    return blatt


class TempoRegler:
    """Der Tempo-Regler **während des Laufs** (P139: sofort wirksam, nur für jetzt): setzt
    `TimerLauf.tempo_setzen` und merkt den Faktor für diese Sitzung (`AppState.uhr_tempo`).
    Die Lage springt nicht (`core.takt.TaktLauf`). Einmal gebaut; `nachziehen` zeigt ihn nur,
    solange ein Takt läuft."""

    def __init__(self, state: Any, key: str, lauf: Any) -> None:
        self.state, self.key, self.lauf = state, key, lauf
        self.text = ft.Text(size=12, weight=ft.FontWeight.W_600, width=52)
        self.regler = ft.Slider(
            min=TEMPO_MIN,
            max=TEMPO_MAX,
            divisions=int((TEMPO_MAX - TEMPO_MIN) / 0.05),
            value=tempo_lesen(getattr(lauf, "tempo_faktor", 1.0)),
            round=2,
            expand=True,
            on_change=self._gezogen,
        )
        self.control = ft.Row(
            spacing=4,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SPEED, size=18, opacity=0.8, tooltip="Tempo — für jetzt"),
                self.text,
                self.regler,
            ],
        )
        self._zeigen()

    def _zeigen(self, faktor: float | None = None) -> None:
        if faktor is None:
            faktor = tempo_lesen(self.regler.value or 1.0)
        self.text.value = tempo_text(faktor)

    def _gezogen(self, e: ft.Event[ft.Slider]) -> None:
        ohne_auto_update()  # beim Ziehen dauernd (V1) — nur der Text zieht nach
        faktor = tempo_lesen(e.control.value)
        self.lauf.tempo_setzen(faktor)
        with contextlib.suppress(Exception):
            self.state.uhr_tempo[self.key] = faktor
        self._zeigen(faktor)
        with contextlib.suppress(Exception):
            self.text.update()

    def nachziehen(self, laeuft_takt: bool) -> None:
        self.control.visible = laeuft_takt


def takt_anbringen(state: Any, lauf: Any, key: str, uebung_takt: Takt | None) -> None:
    """Die Wahl dieser Sitzung an einen Lauf hängen: Takt „für jetzt“, die Vorgabe der Übung,
    der Tempo-Faktor (`AppState.uhr_takt`, `uhr_tempo`)."""
    if lauf is None:
        return
    lauf.takt_uebung = uebung_takt
    lauf.takt_jetzt = state.uhr_takt.get(key)
    faktor = state.uhr_tempo.get(key, 1.0)
    if faktor != lauf.tempo_faktor:
        lauf.tempo_setzen(faktor)
        lauf.tempo_aenderungen.clear()  # vor dem Start: keine Änderung im Lauf


def takt_knopf(
    page: Any,
    state: Any,
    *,
    key: str,
    takt: Takt | None,
    lauf: Any = None,
    starten: Callable[[Takt], Any] | None = None,
    titel: str = "Takt",
    klein: bool = False,
) -> ft.Control:
    """Der Takt-Knopf an der Uhr (§5): öffnet das Blatt mit „Für jetzt“ — die Wahl gilt für
    diese Sitzung unter ``key`` und, läuft die Uhr schon, sofort im Lauf (``lauf``)."""
    gewaehlt = state.uhr_takt.get(key)
    aktiv = gewaehlt if gewaehlt is not None else takt

    def fuer_jetzt(neu: Takt | None) -> None:
        state.uhr_takt[key] = neu if neu is not None else AUS
        if lauf is not None:
            lauf.takt_jetzt = state.uhr_takt[key]
        state.neu_zeichnen()

    def wie_eingestellt() -> None:
        state.uhr_takt.pop(key, None)
        if lauf is not None:
            lauf.takt_jetzt = None
        state.neu_zeichnen()

    def oeffnen() -> None:
        page.show_dialog(
            takt_blatt(
                page,
                state,
                takt=aktiv,
                titel=titel,
                fuer_jetzt=fuer_jetzt,
                zuruecksetzen=wie_eingestellt if key in state.uhr_takt else None,
                starten=starten,
            )
        )

    tipp = (
        f"Takt: {aktiv.anzeigename} · {aktiv.kurztext()}"
        if aktiv is not None and not aktiv.leer
        else "Takt wählen"
    )
    an = aktiv is not None and not aktiv.leer
    return ft.IconButton(
        SYMBOL,
        tooltip=tipp,
        icon_size=20 if klein else 24,
        padding=ft.Padding.all(4) if klein else None,
        size_constraints=ft.BoxConstraints(min_width=36, min_height=36) if klein else None,
        style=ft.ButtonStyle(color=ft.Colors.PRIMARY) if an else None,
        on_click=oeffnen,
    )


def _klang_optionen(art: str) -> list[ft.DropdownOption]:
    vorgabe = KLAENGE.get(KLANG_VORGABE.get(art, "schale"), "Vorgabe")
    return [
        ft.DropdownOption(key="", text=f"Vorgabe · {vorgabe}"),
        *(ft.DropdownOption(key=k, text=v) for k, v in KLAENGE.items() if k != "ende"),
    ]


def takt_zeile_text(takt: Takt | None) -> str:
    """„Takt: 4-7-8 · 3,2/min“ bzw. „Takt: keiner“ — die Zeile in Formularen.

    >>> takt_zeile_text(None), takt_zeile_text(VORLAGEN["atmung_4_6"])
    ('Takt: keiner', 'Takt: Atmung 4-6 · 4-6 · 6,0/min')
    """
    if takt is None or takt.leer:
        return "Takt: keiner"
    name = f"{takt.name} · " if takt.name else ""
    return f"Takt: {name}{takt.kurztext()}"


def takt_zeile(
    takt: Takt | None, *, bearbeiten: Callable[[], Any], entfernen: Callable[[], Any]
) -> ft.Control:
    """Die Zeile „Takt: 4-7-8 · 4/min“ mit Stift und ✕ (Übung bearbeiten, Timer-Editor)."""
    return ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(SYMBOL, size=18, opacity=0.8),
            ft.Text(takt_zeile_text(takt), expand=True, size=13),
            ft.IconButton(
                ft.Icons.EDIT_OUTLINED,
                tooltip="Takt einstellen: Phasen, Tempo, Klang",
                icon_size=20,
                on_click=bearbeiten,
            ),
            ft.IconButton(
                ft.Icons.CLOSE,
                tooltip="Takt entfernen",
                icon_size=20,
                on_click=entfernen,
                visible=takt is not None and not takt.leer,
            ),
        ],
    )


def takt_fuer_jetzt(state: Any, key: str) -> Takt | None:
    """Die Wahl „für jetzt“ unter ``key`` — ``None``: keine Wahl (Abschnitt > Übung gilt)."""
    return state.uhr_takt.get(key)


def ist_aus(takt: Takt | None) -> bool:
    return takt is not None and takt.leer


__all__ = [
    "AUS",
    "SYMBOL",
    "TempoRegler",
    "ist_aus",
    "takt_anbringen",
    "takt_blatt",
    "takt_fuer_jetzt",
    "takt_knopf",
    "takt_zeile",
    "takt_zeile_text",
]
