"""Ein Name aus einer gemerkten Liste — für die Überschrift einer Messung und für Abschnitte.

Ein Baustein für beide (Ben, 19.11.2026: „Nimm das alte Muster für beide“ — das Verhalten
des Titel-Blatts, Ben 26.10.2026: „vordefinieren und auffindbar wieder abrufen“ — bei zehn
Namen wären Knöpfe eine Wolke):

- Das **Feld** steht mit dem Vorschlag da (Titel: der geübte Plan; Abschnitt: „Abschnitt 3“).
- Darunter die **Liste**: zuerst die Vorschläge aus dem Zusammenhang (✨, Titel: Plan und
  Timer), dann die gemerkten Namen — angeheftete zuerst (📌), dann die zuletzt vergebenen
  (🕘), dann die vorab angelegten (🔖). **Tippen filtert** („enthält“), Antippen übernimmt
  und zeigt wieder alles, ✕ nimmt einen Namen aus der Liste, „„…“ merken“ nimmt Neues auf.
- Höchstens `MAX_ZEILEN` Zeilen, der Rest als „+n weitere“; die Liste hat ab dem Öffnen eine
  **feste Höhe** — das Feld wandert beim Tippen nicht (Ben, 26.10.2026).
- **Angeheftet** wird nur in den Einstellungen (HRV-Messung → Überschriften bzw.
  Abschnittsnamen, `views/einstellungen_hrv_titel.py`).

Die Namen gehören dem Profil: Überschriften in `hrv_title` (Migration 030), Abschnittsnamen in
einer eigenen Liste `hrv_section_name` (Migration 072, Ben 19.11.2026). Jeder vergebene Name
kommt von selbst hinein (`HrvRepo.titel_merken`, `name_merken` für Abschnitte).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Any, Protocol

import flet as ft

from trainingsapp.core.abschnitte import merkenswert

#: Höchstens so viele Zeilen zeigt die Liste (Ben, 26.10.2026: „sonst wird die Scrollbar zu
#: groß“) — darüber hinaus filtert das Tippen
MAX_ZEILEN = 7
#: Höhe einer Zeile der Liste (dichte `ListTile`, px)
ZEILE = 48


class Gemerkt(Protocol):
    """Ein gemerkter Name — `core.models.HrvTitel` oder `core.models.AbschnittName`."""

    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def angeheftet(self) -> bool: ...

    @property
    def zuletzt(self) -> datetime | None: ...


def passende[G: Gemerkt](gespeicherte: Iterable[G], suche: str) -> list[G]:
    """Die Namen, in denen ``suche`` vorkommt — ohne Suche alle, Reihenfolge bleibt.

    >>> from trainingsapp.core.models import HrvTitel
    >>> t = [HrvTitel(name="Intervalle Beine"), HrvTitel(name="Ruhe morgens")]
    >>> [x.name for x in passende(t, "")]
    ['Intervalle Beine', 'Ruhe morgens']
    >>> [x.name for x in passende(t, " bei")]
    ['Intervalle Beine']
    """
    s = suche.strip().casefold()
    return [t for t in gespeicherte if not s or s in t.name.casefold()]


class Namenwahl:
    """Feld und Liste der gemerkten Namen.

    Args:
        label: Beschriftung des Felds („Titel“, „Name“).
        wert: was beim Öffnen im Feld steht.
        vorschlaege: Namen aus dem Zusammenhang (✨), vor den gemerkten.
        gespeicherte: die gemerkten Namen (angeheftete zuerst, dann die zuletzt vergebenen).
        merken: einen neuen Namen aufnehmen — ohne fehlt die Zeile „„…“ merken“.
        entfernen: einen Namen aus der Liste nehmen — ohne fehlt das ✕.
        art: wie ein gemerkter Name heißt („Überschrift“, „Abschnittsname“) — im Hinweis.
        leer: der Hinweis, solange die Liste leer ist.
        merkbar: ob ein getippter Text die Zeile „merken“ bekommt (Abschnitt: nicht die bloße
            Vorgabe „Abschnitt 3“).
    """

    def __init__(
        self,
        *,
        label: str = "Name",
        wert: str = "",
        vorschlaege: Sequence[str] = (),
        gespeicherte: Sequence[Gemerkt] = (),
        merken: Callable[[str], Gemerkt | None] | None = None,
        entfernen: Callable[[Any], None] | None = None,
        art: str = "Gespeicherter Name",
        leer: str = "",
        merkbar: Callable[[str], bool] = lambda _t: True,
    ) -> None:
        self.vorschlaege = list(vorschlaege)
        self.vorrat: list[Gemerkt] = list(gespeicherte)
        self._merken, self._entfernen = merken, entfernen
        self._art, self._leer, self._merkbar = art, leer, merkbar
        self.feld = ft.TextField(
            label=label,
            value=wert,
            dense=True,
            capitalization=ft.TextCapitalization.SENTENCES,
            on_change=lambda _e: self.zeichnen(),
        )
        # Feste Höhe ab dem Öffnen (Ben, 26.10.2026: „es irritiert, dass sich mit dem Tippen
        # die Größe des Fensters verändert“): so viele Zeilen, wie beim Öffnen da sind,
        # höchstens `MAX_ZEILEN` — wird die Liste beim Filtern kürzer, bleibt unten Luft; wird
        # sie länger („merken“), scrollt sie in sich. Ein Blatt misst seine Höhe sonst bei
        # jeder Änderung.
        anfangs = len(self.vorschlaege) + len(self.vorrat)
        zeilen = max(1, min(MAX_ZEILEN, anfangs) + (1 if anfangs > MAX_ZEILEN else 0))
        self.liste = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=zeilen * ZEILE)
        # Ohne Liste und ohne Hinweis (ein schlichtes Feld): keine leere Fläche
        self.liste.visible = bool(anfangs or merken is not None or leer)
        #: Der zuletzt übernommene Name: solange er im Feld steht, zeigt die Liste alles
        self._gewaehlt = (self.feld.value or "").strip()
        self.control = ft.Column(spacing=8, tight=True, controls=[self.feld, self.liste])
        self.zeichnen()

    @property
    def text(self) -> str:
        """Was im Feld steht."""
        return (self.feld.value or "").strip()

    # -- Bedienung -----------------------------------------------------------------------

    def nehmen(self, name: str) -> None:
        self.feld.value = name
        self._gewaehlt = name
        self.zeichnen()
        with contextlib.suppress(Exception):
            self.feld.update()

    def entfernen(self, t: Gemerkt) -> None:
        if self._entfernen is not None:
            self._entfernen(t)
        self.vorrat = [x for x in self.vorrat if x.id != t.id]
        self.zeichnen()

    def merken(self, name: str) -> None:
        if self._merken is None:
            return
        t = self._merken(name)
        if t is not None and all(x.id != t.id for x in self.vorrat):
            self.vorrat.append(t)
        self._gewaehlt = name
        self.zeichnen()

    # -- Zeichnen ------------------------------------------------------------------------

    def _zeile(
        self, name: str, symbol: ft.IconData, tipp: str, *, rechts: ft.Control | None = None
    ) -> ft.Control:
        return ft.ListTile(
            dense=True,
            content_padding=ft.Padding.only(left=4, right=0),
            leading=ft.Icon(symbol, size=20, opacity=0.7, tooltip=tipp),
            title=ft.Text(name, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            trailing=rechts,
            on_click=lambda _e=None: self.nehmen(name),
        )

    def zeichnen(self) -> None:
        text = self.text
        suche = "" if text == self._gewaehlt else text
        zeilen: list[ft.Control] = [
            self._zeile(n, ft.Icons.AUTO_AWESOME_OUTLINED, "Aus Plan oder Timer")
            for n in self.vorschlaege
            if not suche or suche.casefold() in n.casefold()
        ]
        treffer = passende(self.vorrat, suche)
        rest = len(zeilen) + len(treffer) - MAX_ZEILEN
        for t in treffer[: max(0, MAX_ZEILEN - len(zeilen))]:
            symbol = (
                ft.Icons.PUSH_PIN
                if t.angeheftet
                else ft.Icons.HISTORY
                if t.zuletzt is not None
                else ft.Icons.BOOKMARK_BORDER
            )
            tipp = "Angeheftet" if t.angeheftet else self._art
            kreuz = (
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=18,
                    visual_density=ft.VisualDensity.COMPACT,
                    tooltip="Aus der Liste nehmen",
                    on_click=lambda _e=None, t=t: self.entfernen(t),
                )
                if self._entfernen is not None
                else None
            )
            zeilen.append(self._zeile(t.name, symbol, tipp, rechts=kreuz))
        if rest > 0:
            zeilen.append(
                ft.Container(
                    height=ZEILE,
                    padding=ft.Padding.only(left=16),
                    alignment=ft.Alignment.CENTER_LEFT,
                    content=ft.Text(f"+{rest} weitere — zum Filtern tippen", size=12, opacity=0.65),
                )
            )
        bekannt = {n.casefold() for n in self.vorschlaege} | {
            t.name.casefold() for t in self.vorrat
        }
        if (
            text
            and self._merken is not None
            and text.casefold() not in bekannt
            and self._merkbar(text)
        ):
            zeilen.append(
                ft.ListTile(
                    dense=True,
                    content_padding=ft.Padding.only(left=4, right=0),
                    leading=ft.Icon(
                        ft.Icons.BOOKMARK_ADD_OUTLINED, size=20, color=ft.Colors.PRIMARY
                    ),
                    title=ft.Text(f"„{text}“ merken", size=14, color=ft.Colors.PRIMARY),
                    on_click=lambda _e=None, text=text: self.merken(text),
                )
            )
        if not zeilen and not self.vorrat and not self.vorschlaege and self._leer:
            zeilen.append(ft.Text(self._leer, size=12, opacity=0.65))
        self.liste.controls = zeilen
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.liste.update()


def namenwahl(state: Any, *, wert: str) -> Namenwahl:
    """Die `Namenwahl` für einen Abschnitt — mit den gemerkten Abschnittsnamen des Profils."""
    hrv, profil = state.hrv, state.profil.id
    return Namenwahl(
        label="Name",
        wert=wert,
        gespeicherte=hrv.abschnittnamen(profil),
        merken=lambda name: hrv.abschnittname_merken(profil, name, verwendet=False),
        entfernen=lambda t: hrv.abschnittname_entfernen(t.id),
        art="Gemerkter Abschnittsname",
        leer="Noch keine gemerkten Namen — was du vergibst, steht beim nächsten Mal hier.",
        merkbar=lambda text: merkenswert(text) is not None,
    )


def name_merken(state: Any, name: str) -> None:
    """Den vergebenen Abschnittsnamen merken — den der Gruppe, nie die bloße Vorgabe
    („Abschnitt 3“); ein Fehler dabei hält nichts auf."""
    gemerkt = merkenswert(name)
    if gemerkt is None:
        return
    with contextlib.suppress(Exception):
        state.hrv.abschnittname_merken(state.profil.id, gemerkt)


__all__ = ["MAX_ZEILEN", "ZEILE", "Gemerkt", "Namenwahl", "name_merken", "namenwahl", "passende"]
