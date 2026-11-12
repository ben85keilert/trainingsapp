"""Das Abschnittsfeld der Live-Karte und des Live-Vollbilds (Ben, 27./28.10.2026).

Ein Objekt für beide Orte: „Abschnitt: Start“ / „‹Name› · Ende“, die Chip-Zeile (Ganze
Messung · je Abschnitt — ein Chip rückt das Fenster auf den Abschnitt), die Liste mit dem
laufenden Abschnitt, der im Sekundentakt mitzählt. Seit 12.11.2026 lässt sich ein eigener
Abschnitt auch live **nachtragen und ändern**: „+“ neben dem Startknopf und der Stift an der
Zeile öffnen das Blatt mit Name und zwei Zeiten (`components.abschnitt_blatt`); Abschnitte
eines Ablaufs (Timer, Übung) bleiben live, wie sie sind. Hochkant steht es als Klappfeld unter
der Hauptkurve (`views/messung.py`), quer als Seitenleiste neben der Kurve
(`views/live_vollbild.py`, Ben, 28.10.2026: „so wie für die Notizen braucht es auch den
Abschnitte-Editor im Querformat“; seit 12.11.2026 auch `views/hf_vollbild.py`). Vertrag:
`docs/plan_abschnitte.md`.

**In der Kurve bearbeiten** (P193, Ben 12.11.2026: „ein Abschnittsbearbeitungsmodus, wie er
in Aufzeichnungen ist … halte das einheitlich“): Der Stift hält die Kurve an, zeigt den
Abschnitt ganz und öffnet **denselben Bereichseditor wie in der Aufzeichnung**
(`components.bereich.BereichEditor`) — Anfang oder Ende wählen, in die Kurve tippen oder
ziehen, Notizen rasten ein; dazu Name, Kopf · Endteil, Löschen. Läuft der Abschnitt noch,
steht sein Ende auf „läuft“ und nur der Anfang lässt sich setzen. „Zeiten …“ im Editor
öffnet das Blatt mit zwei Zeiten. Gespeichert wird über `Messlauf.abschnitt_setzen`. Die
Ansicht fragt `reihen` (Grenzen in der Kurve), `tippen` und `greifen` (Gesten).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core import abschnitte as eigene_abschnitte
from trainingsapp.core.laufend import minuten
from trainingsapp.ui.components.abschnitt_blatt import abschnitt_blatt
from trainingsapp.ui.components.abschnitte import (
    Abschnittsfeld,
    abschnitt_chip,
    name_dialog,
    rand_zeile,
)
from trainingsapp.ui.components.bereich import BereichEditor
from trainingsapp.ui.components.dialoge import meldung
from trainingsapp.ui.components.kurve import Reihe

#: So weit vor jetzt beginnt der Vorschlag für einen nachgetragenen Abschnitt (s)
NACHTRAG_VORGABE_S = 300.0

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
        self.marker_knopf = ft.IconButton(
            ft.Icons.FLAG_OUTLINED,
            tooltip="Marker setzen — teilt den laufenden Abschnitt",
            visible=False,
            on_click=lambda _=None: self.marker(),
        )
        self.nachtrag_knopf = ft.IconButton(
            ft.Icons.ADD,
            tooltip="Abschnitt nachtragen (zwei Zeiten)",
            on_click=lambda _=None: self.nachtragen(),
        )
        self.feld = Abschnittsfeld(
            offen=state.abschnitte_offen if offen is None else offen,
            offen_merken=(lambda o: setattr(state, "abschnitte_offen", o))
            if offen is None
            else (lambda _o: None),
            knoepfe=[self.start_knopf, self.marker_knopf, self.nachtrag_knopf],
            zeilen=lambda: state.hrv_einstellungen().notizen_zeilen,
        )
        #: Der offene Editor in der Kurve (P193) — ``None``: keiner
        self.editor: BereichEditor | None = None
        self._editor_stand: dict[str, Any] = {}
        self.editor_box = ft.Container(visible=False, data="abschnitt_editor")
        self._control = ft.Column(
            spacing=6, tight=True, controls=[self.feld.control, self.editor_box]
        )

    @property
    def control(self) -> ft.Control:
        """Feld und Editor — der Editor steht direkt unter der Liste."""
        return self._control

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

    def marker(self) -> None:
        """„‹Name›: Marker“ bei jetzt — der laufende Abschnitt wird hier geteilt."""
        if self.lauf.abschnitt_marker():
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

    # -- Nachtragen und Ändern (Ben, 12.11.2026) ---------------------------------------

    def _blatt(self, a: Any | None, laeuft: bool) -> None:
        lauf, state, page = self.lauf, self.state, self.page
        zb = lauf.notiz_zeitbezug()
        anfang = float(zb.wand_versatz or 0.0)
        jetzt = lauf.jetzt_s()

        def sichern(
            name: str, von: float, bis: float | None, kopf_s: float, endteil_s: float
        ) -> None:
            lauf.abschnitt_setzen(
                a.id if a is not None else None, name, von, bis, kopf_s=kopf_s, endteil_s=endteil_s
            )
            self._zeichnen_und_melden()

        def loeschen() -> None:
            assert a is not None
            self._loeschen(a)

        page.show_dialog(
            abschnitt_blatt(
                page,
                zeitbezug=zb,
                live=True,
                grenzen=lambda: (anfang, lauf.jetzt_s()),
                name=a.name if a is not None else f"Abschnitt {len(lauf.abschnitte()) + 1}",
                von=a.von_s if a is not None else max(anfang, jetzt - NACHTRAG_VORGABE_S),
                bis=None if laeuft else (a.bis_s if a is not None else jetzt),
                kopf_s=a.kopf_s if a is not None else 0.0,
                endteil_s=a.endteil_s if a is not None else 0.0,
                neu=a is None,
                uhr=state.hrv_einstellungen().achse_uhrzeit,
                vorschlaege=[t.name for t in state.hrv.titel_liste(state.profil.id)],
                sichern=sichern,
                loeschen=loeschen if a is not None else None,
            )
        )

    # -- In der Kurve bearbeiten (P193) ------------------------------------------------

    def _notiz_punkte(self) -> list[tuple[float, str]]:
        """Rastpunkte des Editors: die Notizen der Aufnahme auf der Live-Achse."""
        zb = self.lauf.notiz_zeitbezug()
        if zb is None:
            return []
        aus: list[tuple[float, str]] = []
        for e in self.lauf.ereignisse():
            x = zb.x(e)
            if x is not None:
                aus.append((float(x), str(e.get("text") or "")))
        return aus

    def _zeigen(self, x: float) -> None:
        """Die Kurve auf eine Zeit rücken und dort halten."""
        fenster, jetzt = self.fenster, self.lauf.jetzt_s()
        fenster.ende_s = min(x + fenster.breite_s / 2, jetzt - 1.0)
        self.danach()

    def bearbeiten(self, a: Any, laeuft: bool) -> None:
        """Der Stift: Kurve anhalten, den Abschnitt ganz zeigen, Editor öffnen."""
        lauf, fenster = self.lauf, self.fenster
        zb = lauf.notiz_zeitbezug()
        if lauf.aufnahme is None or zb is None:
            return
        jetzt = lauf.jetzt_s()
        anfang = float(zb.wand_versatz or 0.0)
        bis = jetzt if laeuft else a.bis_s
        # Der ganze Abschnitt mit etwas Rand, angehalten (ein laufender bis kurz vor jetzt)
        fenster.breite_s = max(60.0, (bis - a.von_s) * 1.2)
        fenster.ende_s = min(bis + (bis - a.von_s) * 0.1, jetzt - 1.0)
        self.breite_gesetzt(fenster.breite_s)
        stand: dict[str, Any] = {"a": a, "laeuft": laeuft, "raender": (a.kopf_s, a.endteil_s)}
        self._editor_stand = stand
        self.editor = BereichEditor(
            von=a.von_s,
            bis=bis,
            anfang=anfang,
            ende=jetzt,
            notizen=self._notiz_punkte,
            geaendert=self.danach,
            zeigen=self._zeigen,
            breite=lambda: fenster.breite_s,
            farbe=a.farbe,
            nur_anfang=laeuft,
        )
        editor = self.editor
        name = ft.TextField(
            label="Name",
            value=a.name,
            dense=True,
            capitalization=ft.TextCapitalization.SENTENCES,
            data="abschnitt_name",
        )
        stand["name"] = name

        def rechen_text() -> str:
            kopf, endteil = stand["raender"]
            von, bis_ = editor.von - kopf, editor.bis + endteil
            return f"{_uhr(max(von, anfang))}–{_uhr(bis_)} · {_uhr(bis_ - max(von, anfang))}"

        def kopf_setzen(s: float) -> None:
            stand["raender"] = (s, stand["raender"][1])

        def endteil_setzen(s: float) -> None:
            stand["raender"] = (stand["raender"][0], s)

        rand_box = ft.Container(
            visible=any(stand["raender"]),
            content=rand_zeile(
                self.page,
                kopf=lambda: stand["raender"][0],
                endteil=lambda: stand["raender"][1],
                kopf_setzen=kopf_setzen,
                endteil_setzen=endteil_setzen,
                bereich_text=rechen_text,
            ),
        )

        def rand_umschalten() -> None:
            rand_box.visible = not rand_box.visible
            with contextlib.suppress(Exception):
                rand_box.update()

        def zeiten() -> None:
            self.editor_schliessen()
            self._blatt(a, laeuft)

        def loeschen() -> None:
            self.editor_schliessen(zeichnen=False)
            self._loeschen(a)

        self.editor_box.content = ft.Container(
            border_radius=10,
            padding=ft.Padding.only(left=10, right=4, top=4, bottom=8),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, a.farbe)),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                "ABSCHNITT",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                opacity=0.7,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=18,
                                tooltip="Schließen",
                                on_click=lambda _e=None: self.editor_schliessen(),
                            ),
                        ],
                    ),
                    name,
                    editor.control,
                    rand_box,
                    ft.Text(
                        "Anfang wählen, dann in die Kurve tippen oder ziehen — das Ende "
                        "setzt „‹Name› · Ende“."
                        if laeuft
                        else "Anfang oder Ende wählen, dann in die Kurve tippen oder ziehen — "
                        "Notizen ziehen die Grenze an, die Stecknadel setzt sie genau auf eine.",
                        size=12,
                        opacity=0.65,
                    ),
                    ft.Row(
                        spacing=4,
                        wrap=True,
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(
                                "Kopf · Endteil",
                                icon=ft.Icons.SWAP_HORIZ,
                                tooltip="Rechenbereich über die Grenzen hinaus (+) oder "
                                "innerhalb (−)",
                                on_click=lambda _e=None: rand_umschalten(),
                            ),
                            ft.TextButton(
                                "Zeiten …",
                                icon=ft.Icons.SCHEDULE,
                                tooltip="Name und zwei Zeiten eintippen",
                                on_click=lambda _e=None: zeiten(),
                            ),
                            ft.TextButton(
                                "Löschen",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=lambda _e=None: loeschen(),
                            ),
                            ft.TextButton(
                                "Abbrechen", on_click=lambda _e=None: self.editor_schliessen()
                            ),
                            ft.FilledButton(
                                "Speichern",
                                icon=ft.Icons.CHECK,
                                data="abschnitt_speichern",
                                on_click=lambda _e=None: self.editor_sichern(),
                            ),
                        ],
                    ),
                ],
            ),
        )
        self.editor_box.visible = True
        self.neu(erzwingen=True)
        self.danach()

    def editor_sichern(self) -> None:
        """Name, Grenzen, Kopf und Endteil in die Aufnahme — das Paar Grenz-Notizen rückt mit."""
        editor, stand = self.editor, self._editor_stand
        if editor is None:
            return
        a, laeuft = stand["a"], stand["laeuft"]
        kopf, endteil = stand["raender"]
        self.lauf.abschnitt_setzen(
            a.id,
            str(stand["name"].value or "").strip() or a.name,
            editor.von,
            None if laeuft else editor.bis,
            kopf_s=kopf,
            endteil_s=endteil,
        )
        self.editor_schliessen(zeichnen=False)
        self._zeichnen_und_melden()

    def editor_schliessen(self, *, zeichnen: bool = True) -> None:
        """Editor zu — die Kurve bleibt, wo sie steht („Live“ holt die Gegenwart zurück)."""
        self.editor, self._editor_stand = None, {}
        self.editor_box.visible = False
        self.editor_box.content = None
        if zeichnen:
            self.neu(erzwingen=True)
            self.danach()

    def reihen(self, x_von: float, x_bis: float) -> list[Reihe]:
        """Was der offene Editor in die Kurve zeichnet (Grenzen, Balken) — sonst nichts."""
        return self.editor.reihen(x_von, x_bis) if self.editor is not None else []

    def tippen(self, x: float) -> bool:
        """Ein Tipp in die Kurve: Mit offenem Editor setzt er die gewählte Grenze."""
        if self.editor is None:
            return False
        self.editor.tippen(x)
        return True

    def greifen(self, x: float) -> bool:
        """Ein Zug in der Kurve: Mit offenem Editor folgt die gewählte Grenze dem Finger."""
        return self.editor.ziehen(x) if self.editor is not None else False

    def _loeschen(self, a: Any) -> None:
        lauf = self.lauf
        vorher = lauf.abschnitt_loeschen(a.id)
        if self.stand["gebunden"] == a.id:
            self.stand["gebunden"] = None
        self._zeichnen_und_melden()

        def zurueck() -> None:
            lauf.ereignisse_setzen(vorher)
            self._zeichnen_und_melden()

        self.page.show_dialog(meldung(f"„{a.name}“ gelöscht", zurueck))

    def nachtragen(self) -> None:
        """„+“: ein Abschnitt mit zwei Zeiten, die schon vorbei sind."""
        if self.lauf.aufnahme is None:
            self.page.show_dialog(ft.SnackBar(ft.Text("Erst die Aufnahme starten.")))
            return
        self._blatt(None, False)

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

    def _zeile(self, a: Any, laeuft: bool, eigener: bool) -> ft.Control:
        zeit = ft.Text(self.zeit_text(a, laeuft), size=12, opacity=0.75)
        if laeuft:
            self.laufzeit[a.id] = zeit
        stift: list[ft.Control] = (
            [
                ft.Container(  # kein IconButton: der bräuchte 48 px, die Zeile hat 44
                    width=40,
                    height=40,
                    border_radius=20,
                    ink=True,
                    alignment=ft.Alignment.CENTER,
                    tooltip="Abschnitt in der Kurve bearbeiten",
                    data="abschnitt_stift",
                    on_click=lambda _=None: self.bearbeiten(a, laeuft),
                    content=ft.Icon(ft.Icons.EDIT_OUTLINED, size=18),
                )
            ]
            if eigener
            else []
        )
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
                    *stift,
                ],
            ),
        )

    def neu(self, erzwingen: bool = False) -> None:
        """Chips, Liste und Knopf aus den Abschnitten der Aufnahme — nur neu gebaut, wenn
        sich etwas ändert (im Sekundentakt gerufen); der laufende zählt seine Dauer mit."""
        lauf, start_knopf = self.lauf, self.start_knopf
        teile = lauf.abschnitte()
        offen = lauf.offener_abschnitt()
        laufend_id = (
            eigene_abschnitte.laufende_kennung(lauf.ereignisse(), lauf.notiz_zeitbezug().x)
            if offen
            else None
        )
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
        self.marker_knopf.visible = offen is not None
        self.nachtrag_knopf.disabled = lauf.aufnahme is None
        gebunden = self.stand["gebunden"]
        chips: list[ft.Control] = [
            abschnitt_chip(None, gewaehlt=gebunden is None, on_click=self._binder(None)),
            *[
                abschnitt_chip(a, gewaehlt=a.id == gebunden, on_click=self._binder(a))
                for a in teile
            ],
        ]
        eigene = set(eigene_abschnitte.kennungen(lauf.ereignisse()))
        zeilen = [self._zeile(a, a.id == laufend_id, a.id in eigene) for a in teile]
        if not teile:
            zeilen = [
                ft.Text(
                    "Noch keine Abschnitte — „Abschnitt: Start“ setzt die Grenze bei jetzt, „+“ "
                    "trägt einen mit zwei Zeiten nach, Notizen „Name: Start“ und „Name: Ende“ "
                    "ergeben einen („Name: Marker“ teilt ihn), der Timer setzt seine von selbst."
                    if lauf.aufnahme is not None
                    else "Abschnitte gibt es in der Aufnahme.",
                    size=12,
                    opacity=0.7,
                )
            ]
        self.feld.fuellen(chips, zeilen, len(teile))


__all__ = ["LiveAbschnitte"]
