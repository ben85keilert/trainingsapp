"""Das Hilfefenster zur Notation — überall dieselbe Tabelle.

Der Text ist Markdown und steht auch in `docs/notation.md`; wer die Notation
ändert, ändert beide Stellen.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

NOTATION_MD = """\
**Je Satz** (Wiederholungen, Haltezeit)

| Eingabe | Bedeutung |
|---|---|
| `30` | ein Satz mit 30 |
| `3x15` | drei Sätze mit je 15 |
| `15/15/20` | drei Sätze, einzeln |
| `2x15/20` | zwei Sätze 15, dann ein Satz 20 |
| `+20` | einen Satz 20 anhängen |

Anzeige: `3x15`, `30` oder `15/15/20`, dazu die Summe.

**Im Plan** tippst du nur Zahlen: Chips wie `+15` hängen einen Satz an, darunter
**Sätze × Wert** (`3` × `15`) — leer bei Sätze heißt einer. Die Handy-Tastatur
für Zahlen hat kein „x“; im Formular („Mehr …“) trennt dort das Komma die
Sätze: `15,15,20`.

**Zeiten**: `30` = 30 s, `1:30` = 90 s, `2min`. Je Satz wie oben: `3x30`, `45/60/30`.
`0` oder leer = ohne Zeit — gemacht, aber kein Punkt auf der Kurve.

**Einzelwerte**: Gewicht `40` oder `40kg`, Strecke `500` (m) oder `2km`, Winkel `45`,
Skala `0` bis `10` — Regler oder Zahl, abschicken mit dem Haken. Dezimal mit Punkt
oder Komma (`12,5`); in Satzlisten trennt das Komma Sätze, also dort `12.5`.

**Menge oder Ausprägung**: Wiederholungen und Zeiten werden addiert (3 × 50 = 150).
Winkel, Gewicht und Seite wählst du vorher aus — sie trennen: Wandsitz 45° ist
nicht Wandsitz 90°. „Gemacht“ ohne Werte zählt als *abgehakt* (leerer Haken).
"""


def notation_dialog() -> ft.AlertDialog:
    return ft.AlertDialog(
        title=ft.Text("So wird eingegeben"),
        content=ft.Container(width=420, content=ft.Markdown(NOTATION_MD)),
        scrollable=True,
    )


def hilfe_knopf(page: ft.Page, groesse: int = 20) -> ft.Control:
    """Ein Fragezeichen, das das Hilfefenster öffnet."""

    def oeffnen() -> None:
        page.show_dialog(notation_dialog())

    return ft.IconButton(
        ft.Icons.HELP_OUTLINE, icon_size=groesse, tooltip="Wie gebe ich ein?", on_click=oeffnen
    )


def hilfe_oeffner(page: ft.Page) -> Callable[[], None]:
    def oeffnen() -> None:
        page.show_dialog(notation_dialog())

    return oeffnen


__all__ = ["NOTATION_MD", "hilfe_knopf", "hilfe_oeffner", "notation_dialog"]
