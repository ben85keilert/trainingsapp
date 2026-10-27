"""Hilfefenster — überall derselbe Text je Thema.

- **Notation** (`NOTATION_MD`): steht auch in `docs/notation.md`; wer die
  Notation ändert, ändert beide Stellen.
- **Varianten und Pakete** (`UEBUNGEN_MD`): die allgemeine Erklärung, die
  früher in jeder Übung stand (Ben, 14.10.2026: dort redundant). Ausführlich
  in `docs/datenmodell.md` (Varianten) und `docs/uebungspakete.md`.
- **Atemfrequenz und Atemübung** (`ATMUNG_MD`, Ben 17.10.2026): was „unter 8/min“
  und der Knopf „Atemübung“ heißen. Kommt in die Hilfedatei (Katalog A3); die
  Rechenvorschrift steht in hrv-core (`hrv_core/atmung.py`).
- **Varianten** (`VARIANTEN_MD`, Ben 21.10.2026): was das Etikett neben „Notiz“ heißt —
  neben dem Symbol steht kein Wort, die Erklärung kommt in die Hilfedatei (Katalog A3).
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
für Zahlen hat kein „x“; beim Korrigieren eines Eintrags (Tafel „Heute
geleistet“ antippen) trennt dort das Komma die Sätze: `15,15,20`.

**Zeiten**: `30` = 30 s, `1:30` = 90 s, `2min`, `1:30:00` mit Stunden. Je Satz wie
oben: `3x30`, `45/60/30`. `0` oder leer = ohne Zeit — gemacht, aber kein Punkt auf der Kurve.

**Grenzen**: höchstens 100 Sätze, Zeiten bis 48 h, Werte bis 100 000 — darüber
meldet das Feld einen Fehler.

**Einzelwerte**: Gewicht `40` oder `40kg`, Strecke `500` (m) oder `2km`, Winkel `45`,
Skala `0` bis `10` — im Plan ein Schiebebalken (Loslassen trägt ein), im Formular
Regler oder Zahl mit dem Haken. Dezimal mit Punkt oder Komma (`12,5`); in Satzlisten
trennt das Komma Sätze, also dort `12.5`.

**Menge oder Ausprägung**: Wiederholungen und Zeiten werden addiert (3 × 50 = 150).
Winkel, Gewicht und Seite wählst du vorher aus — sie trennen: Wandsitz 45° ist
nicht Wandsitz 90°. „Gemacht“ ohne Werte zählt als *abgehakt* (leerer Haken).
Ja/Nein, Skala und Freitext gelten für den offenen Eintrag — sie trennen nicht.

**Varianten** (Liegestütz kurz und lang) stehen ganz oben in der Ausführung und werden
getrennt gezählt: kurz +30, lang +15, kurz +30 ergibt „kurz 60“ und „lang 15“. Das
**Etikett** neben „Notiz“ setzt die Variante des offenen Eintrags, auch nachträglich,
und legt eine neue an.
"""

VARIANTEN_MD = """\
**Varianten** sind Ausführungen derselben Übung — Liegestütz kurz und lang, Planke
Unterarm, gestreckt, seitlich. Sie gehören zur Übung und werden **getrennt gezählt**:
400 kurze sind etwas anderes als 400 lange. Im Tag und im Tagebuch hat jede Variante
ihre eigene Zeile, in der Kurve ihre eigene Linie; „Zusammen“ blendet die Summe dazu.

**Beim Üben** stehen die Varianten oben in der Ausführung, neben Gewicht und Seite. Die
gewählte gilt für jeden Eintrag, bis du umschaltest — je Ausführung sammelt sich ein
Eintrag, solange er offen ist. Das **Etikett** neben „Notiz“ setzt die Variante des
offenen Eintrags, auch nachträglich, und legt eine neue an. Uhr, Timer und
Plan-Ablauf tragen die gewählte Variante mit ein.

**In der Übung** (Bearbeiten → Varianten) bekommt jede Variante einen Namen, ein Symbol
oder ein Kürzel bis drei Zeichen und eine Beschreibung. Passen nicht alle Namen in eine
Zeile, zeigt die Ausführung nur die Symbole — Name und Beschreibung der gewählten stehen
darunter. Umbenennen kann die bisherigen Einträge mitnehmen; Entfernen lässt sie, wie
sie sind.

**Im Plan** steht die Zeile in jeder Planübung; unter „Einstellen“ und beim i schaltest
du sie für eine Planübung aus. Ein Ziel kann eine Variante vorgeben.
"""


UEBUNGEN_MD = """\
**Kopien** — Wandsitz 45° und Wandsitz 90°, Liegestütz eng und weit: Der Knopf
„Kopie anlegen“ oben in den Übungsdetails legt eine eigene Übung an, die du dann
anpasst. Jede Übung hat im Verlauf ihre eigene Kachel.

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

ATMUNG_MD = """\
Die App liest die **Atemfrequenz aus dem Herzschlag**: Beim Einatmen schlägt das
Herz etwas schneller, beim Ausatmen langsamer (respiratorische Sinusarrhythmie,
RSA). Im Tachogramm ist das eine Welle — ihre Frequenz ist die Atemfrequenz, ihre
Höhe die Kachel „Atemschwankung“.

**Warum „unter 8/min“?** Im selben Signal steckt eine zweite Welle: die
Blutdruckregulation (Mayer-Welle) schwingt etwa alle 10 Sekunden — das sähe aus
wie 6 Atemzüge je Minute. Im Sitzen und besonders im Stehen ist sie oft stärker
als die Atemschwankung. Unter 8 Atemzügen je Minute ist aus dem Herzschlag allein
nicht zu unterscheiden, ob die Atmung oder der Blutdruck schwingt. Darum steht
dort normalerweise keine Zahl, sondern der Grund: „langsame Schwingung unter
8/min“.

**Atemübung an** heißt: Du sagst der App, dass du gerade bewusst langsam atmest —
etwa 6 Atemzüge je Minute (Resonanz- oder Kohärenzatmung). Dann zählt auch die
langsame Welle als Atmung, aber nur, wenn sie klar überwiegt (mindestens 70 % der
Schwankung liegen um ihren Gipfel) und der Herzschlag je Atemzug deutlich
schwankt (mindestens 50 ms zwischen kürzestem und längstem Abstand). Ist daneben
schnelleres Atmen deutlich zu sehen, gilt weiter das.

**Atemübung aus** (Vorgabe): Atemfrequenz nur ab 8/min.

Umschalten: live mit dem Knopf „Atemübung“, der bei langsamer Schwingung in der
Kachel Atemfrequenz erscheint, oder in den Einstellungen unter „HRV-Messung“ im
Abschnitt „Atmung“. Die Wahl gilt auch beim Ansehen von Aufzeichnungen.

**Wann gibt es keine Zahl?** Die App prüft, statt zu schätzen: genug saubere
Schläge, ein deutlicher Gipfel, einzelne Atemzüge von ähnlicher Länge, eine
spürbare Schwankung, mindestens drei Herzschläge je Atemzug und ein Puls unter
110 bpm. Passt etwas nicht, steht der Grund in der Kachel. Lieber keine Zahl als
eine falsche — die Werte beschreiben, sie bewerten nicht.
"""

#: Thema → (Titel, Text, Tooltip des Knopfs)
THEMEN: dict[str, tuple[str, str, str]] = {
    "notation": ("So wird eingegeben", NOTATION_MD, "Wie gebe ich ein?"),
    "varianten": ("Varianten", VARIANTEN_MD, "Was sind Varianten?"),
    "uebungen": ("Varianten und Pakete", UEBUNGEN_MD, "Varianten und Pakete"),
    "atmung": ("Atemfrequenz und Atemübung", ATMUNG_MD, "Was heißt „Atemübung“?"),
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
    "ATMUNG_MD",
    "NOTATION_MD",
    "THEMEN",
    "UEBUNGEN_MD",
    "VARIANTEN_MD",
    "hilfe_dialog",
    "hilfe_knopf",
    "hilfe_oeffner",
    "notation_dialog",
]
