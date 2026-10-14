"""Hilfefenster — überall derselbe Text je Thema.

- **Notation** (`NOTATION_MD`): steht auch in `docs/notation.md`; wer die
  Notation ändert, ändert beide Stellen.
- **Varianten und Pakete** (`UEBUNGEN_MD`): die allgemeine Erklärung, die
  früher in jeder Übung stand (Ben, 14.10.2026: dort redundant). Ausführlich
  in `docs/datenmodell.md` (Varianten) und `docs/uebungspakete.md`.
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


UEBUNGEN_MD = """\
**Varianten** — Wandsitz 45° und Wandsitz 90°, Liegestütz eng und weit: eigene
Übungen mit eigener Eingabe, im Verlauf aber **eine Kachel**. Die Mengen werden
addiert, die Variante wird dazugeschrieben.

Eine Variante entsteht als Kopie (Knopf oben in den Übungsdetails) und gehört
zur Kachel ihres Originals. Im Editor unter „Verlauf“ machst du sie
eigenständig — sinnvoll, wenn sie stark abweicht (Liegestütz einarmig) — oder
hängst eine Übung an ein anderes Original.

**Pakete** — Übungen kommen über Pakete. Die mitgelieferten stehen im Paket
„Standard“, weitere (Qigong, Pilates, Yoga, eine Sammlung von jemand
anderem) importierst du im *Paketmanager* (Einstellungen oder unten im Katalog).
Aus welchem Paket eine Übung stammt, steht klein hinter ihrer Beschreibung.

Was du selbst anlegst oder kopierst, ist eine **eigene Übung** und gehört zu
keinem Paket — ein Import ändert sie nie.

Ein **Import** legt neue Übungen an und bringt die Übungen desselben Pakets auf
den Stand der Datei; was du an ihnen geändert hast, geht dabei verloren. Fehlende
Typen und Regionen kommen mit. Einträge im Verlauf bleiben immer, wie sie sind.

**Auf Paketstand setzen** — Jede Übung eines Pakets kennt ihren Stand aus dem
Paket. Hast du sie geändert, steht hinter der Beschreibung „geändert“; unten in
der Übung holst du den Paketstand zurück, im Paketmanager auch für alle.

**Entfernen** — Im Paketmanager entfernst du ein Paket wieder: Seine Übungen
kommen in den Papierkorb und verschwinden aus den Plänen, Einträge bleiben.
„Wieder installieren“ oder ein neuer Import holt alles zurück.

Ein **Export** schreibt ausgewählte Übungen in eine Paketdatei zum Teilen — ohne
Einträge, Messungen oder Strecken.
"""

#: Thema → (Titel, Text, Tooltip des Knopfs)
THEMEN: dict[str, tuple[str, str, str]] = {
    "notation": ("So wird eingegeben", NOTATION_MD, "Wie gebe ich ein?"),
    "uebungen": ("Varianten und Pakete", UEBUNGEN_MD, "Varianten und Pakete"),
}


def hilfe_dialog(thema: str = "notation") -> ft.AlertDialog:
    titel, text, _ = THEMEN[thema]
    return ft.AlertDialog(
        title=ft.Text(titel),
        content=ft.Container(width=420, content=ft.Markdown(text)),
        scrollable=True,
    )


def notation_dialog() -> ft.AlertDialog:
    return hilfe_dialog("notation")


def hilfe_knopf(page: ft.Page, groesse: int = 20, thema: str = "notation") -> ft.Control:
    """Ein Fragezeichen, das das Hilfefenster zum Thema öffnet."""
    return ft.IconButton(
        ft.Icons.HELP_OUTLINE,
        icon_size=groesse,
        tooltip=THEMEN[thema][2],
        on_click=hilfe_oeffner(page, thema),
    )


def hilfe_oeffner(page: ft.Page, thema: str = "notation") -> Callable[[], None]:
    def oeffnen() -> None:
        page.show_dialog(hilfe_dialog(thema))

    return oeffnen


__all__ = [
    "NOTATION_MD",
    "THEMEN",
    "UEBUNGEN_MD",
    "hilfe_dialog",
    "hilfe_knopf",
    "hilfe_oeffner",
    "notation_dialog",
]
