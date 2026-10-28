"""Das Abschnittsfeld der Live-Karte und des Live-Vollbilds (Ben, 27./28.10.2026).

Ein Objekt für beide Orte: „Abschnitt: Start“ / „‹Name› · Ende“, die Chip-Zeile (Ganze
Messung · je Abschnitt — ein Chip rückt das Fenster auf den Abschnitt), die Liste mit dem
laufenden Abschnitt, der im Sekundentakt mitzählt. Hochkant steht es als Klappfeld unter
der Hauptkurve (`views/messung.py`), quer als Seitenleiste neben der Kurve
(`views/live_vollbild.py`, Ben, 28.10.2026: „so wie für die Notizen braucht es auch den
Abschnitte-Editor im Querformat“). Vertrag: `docs/plan_abschnitte.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.laufend import minuten
from trainingsapp.ui.components.abschnitte import Abschnittsfeld, abschnitt_chip, name_dialog

_uhr = minuten


class LiveAbschnitte:
    """Start/Ende, Chips und Liste der Abschnitte einer laufenden Messung.

    Args:
        fenster: das Zeitfenster der Kurve (`components.zeitfenster.Fenster`).
        anfang: der linke Rand des Puffers (s auf der Live-Achse).
        breite_gesetzt: bekommt die neue Fensterbreite, wenn ein Chip sie setzt
            (die Breitenknöpfe des Aufrufers folgen).
        notizen_auffrischen: das Notizfeld nach Start/Ende neu füllen.
        danach: die Ansicht neu zeichnen (``aktualisieren(erzwingen=True)``).
        offen: Klappzustand — ``None``: aus ``state.abschnitte_offen`` (Live-Karte);
            ``True``: immer offen (Seitenleiste im Vollbild).
    """

    def __init__(
        self,
        page: Any,
        state: Any,
        lauf: Any,
        *,
        fenster: Any,
        anfang: Callable[[], float],
        breite_gesetzt: Callable[[float], None],
        notizen_auffrischen: Callable[[], None],
        danach: Callable[[], None],
        offen: bool | None = None,
    ) -> None:
        self.page, self.state, self.lauf = page, state, lauf
        self.fenster, self.anfang = fenster, anfang
        self.breite_gesetzt = breite_gesetzt
        self.notizen_auffrischen, self.danach = notizen_auffrischen, danach
        self.stand: dict[str, Any] = {"schluessel": None, "gebunden": None}
        #: Die Zeitzeile des laufenden Abschnitts — sie zählt im Sekundentakt mit
        self.laufzeit: dict[str, ft.Text] = {}
        self.start_knopf = ft.TextButton("Abschnitt: Start", icon=ft.Icons.PLAY_ARROW)
        self.start_knopf.on_click = lambda _=None: self.knopf()
        self.feld = Abschnittsfeld(
            offen=state.abschnitte_offen if offen is None else offen,
            offen_merken=(lambda o: setattr(state, "abschnitte_offen", o))
            if offen is None
            else (lambda _o: None),
            knoepfe=[self.start_knopf],
            zeilen=lambda: state.hrv_einstellungen().notizen_zeilen,
        )

    @property
    def control(self) -> ft.Control:
        return self.feld.control

    @property
    def gebunden(self) -> str | None:
        """Die Kennung des Abschnitts, auf den das Fenster gerückt ist — ``None``: ganze."""
        return self.stand["gebunden"]

    def _zeichnen_und_melden(self) -> None:
        self.neu(erzwingen=True)
        self.notizen_auffrischen()
        self.danach()

    def starten(self, name: str) -> None:
        self.lauf.abschnitt_starten(name)
        self._zeichnen_und_melden()

    def knopf(self) -> None:
        """„Abschnitt: Start“ fragt den Namen; „‹Name› · Ende“ beendet ihn."""
        lauf, state, page = self.lauf, self.state, self.page
        if lauf.aufnahme is None:
            page.show_dialog(ft.SnackBar(ft.Text("Erst die Aufnahme starten.")))
            return
        if lauf.offener_abschnitt() is not None:
            lauf.abschnitt_beenden()
            self._zeichnen_und_melden()
            return
        page.show_dialog(
            name_dialog(
                page,
                vorschlaege=[t.name for t in state.hrv.titel_liste(state.profil.id)],
                vorgabe=f"Abschnitt {len(lauf.abschnitte()) + 1}",
                starten=self.starten,
            )
        )

    def binden(self, a: Any) -> None:
        """Ein Chip rückt das Fenster auf den Abschnitt (Breite = Dauer, mindestens 1 min);
        „Ganze Messung“ zeigt den ganzen Puffer. Ein laufender folgt der Gegenwart."""
        fenster, jetzt = self.fenster, self.lauf.jetzt_s()
        if a is None:
            fenster.breite_s = max(60.0, jetzt - self.anfang())
            fenster.ende_s = None
            self.stand["gebunden"] = None
        else:
            fenster.breite_s = max(60.0, a.dauer_s)
            fenster.ende_s = None if a.bis_s >= jetzt - 1.0 else a.bis_s
            self.stand["gebunden"] = a.id
        self.breite_gesetzt(fenster.breite_s)
        self.neu(erzwingen=True)
        self.danach()

    @staticmethod
    def zeit_text(a: Any, laeuft: bool) -> str:
        if laeuft:
            return f"seit {_uhr(a.von_s)} · läuft ({_uhr(a.dauer_s)})"
        return f"{_uhr(a.von_s)}–{_uhr(a.bis_s)} ({_uhr(a.dauer_s)})"

    def _binder(self, a: Any) -> Callable[[], None]:
        return lambda: self.binden(a)

    def _zeile(self, a: Any, laeuft: bool) -> ft.Control:
        zeit = ft.Text(self.zeit_text(a, laeuft), size=12, opacity=0.75)
        if laeuft:
            self.laufzeit[a.id] = zeit
        return ft.Container(
            height=44,
            padding=ft.Padding.only(top=2, bottom=2),
            on_click=lambda _=None: self.binden(a),
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
                            zeit,
                        ],
                    ),
                ],
            ),
        )

    def neu(self, erzwingen: bool = False) -> None:
        """Chips, Liste und Knopf aus den Abschnitten der Aufnahme — nur neu gebaut, wenn
        sich etwas ändert (im Sekundentakt gerufen); der laufende zählt seine Dauer mit."""
        lauf, start_knopf = self.lauf, self.start_knopf
        teile = lauf.abschnitte()
        offen = lauf.offener_abschnitt()
        laufend_id = offen[0] if offen else None
        schluessel = (
            tuple(
                (a.id, a.name, round(a.von_s), None if a.id == laufend_id else round(a.bis_s))
                for a in teile
            ),
            laufend_id,
            self.stand["gebunden"],
            lauf.aufnahme is not None,
        )
        if not erzwingen and schluessel == self.stand["schluessel"]:
            for a in teile:  # nur die laufende Dauer zählt mit
                if a.id == laufend_id and (zeit := self.laufzeit.get(a.id)) is not None:
                    zeit.value = self.zeit_text(a, True)
            return
        self.stand["schluessel"] = schluessel
        self.laufzeit.clear()
        if offen is not None:
            start_knopf.content = f"{offen[1]} · Ende"
            start_knopf.icon = ft.Icons.STOP
        else:
            start_knopf.content = "Abschnitt: Start"
            start_knopf.icon = ft.Icons.PLAY_ARROW
        start_knopf.disabled = lauf.aufnahme is None
        gebunden = self.stand["gebunden"]
        chips: list[ft.Control] = [
            abschnitt_chip(None, gewaehlt=gebunden is None, on_click=self._binder(None)),
            *[
                abschnitt_chip(a, gewaehlt=a.id == gebunden, on_click=self._binder(a))
                for a in teile
            ],
        ]
        zeilen = [self._zeile(a, a.id == laufend_id) for a in teile]
        if not teile:
            zeilen = [
                ft.Text(
                    "Noch keine Abschnitte — „Abschnitt: Start“ setzt die Grenze bei jetzt, "
                    "der Timer seine Abschnitte von selbst."
                    if lauf.aufnahme is not None
                    else "Abschnitte gibt es in der Aufnahme.",
                    size=12,
                    opacity=0.7,
                )
            ]
        self.feld.fuellen(chips, zeilen, len(teile))


__all__ = ["LiveAbschnitte"]
