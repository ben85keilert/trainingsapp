"""Filter der Übungsauswahl: Knopf in der Suchzeile, Labels, Blatt (Ben, 9.11.2026).

„Am besten kommt der Filterbutton in die Zeile von ‚Übung suchen‘ und die ausgewählten Filter
stehen als hübsche Labels in der Zeile, wo jetzt die Filter sind — das spart Platz und zeigt,
was wirkt. Das Filtermenü muss dann umgebaut werden mit den drei Bereichen + ‚Alles leeren‘.“
Katalog und „Übung hinzufügen“ im Plan nutzen dieselbe `FilterLeiste`; die Tag-Kästen im
Übungs-Editor bleiben `tagwahl.TagWahl` (dort wird zugeordnet, nicht gefiltert).

- ``suchzeile(feld)``: das Suchfeld, rechts daneben der Knopf — mit der Zahl der wirkenden
  Filter und farbig, sobald einer wirkt.
- ``labels``: je wirkendem Filter ein Label, Bereich an Symbol und Farbe erkennbar (`ART`);
  ✕ nimmt ihn heraus, ein Tipp öffnet das Blatt. Ohne Filter ist die Zeile weg.
- Das Blatt: Typ · Region · Paket als Chips, mehrere je Bereich. **Die Wahl wirkt sofort**
  (Ben, 15.10.2026): Die Liste dahinter zieht beim Antippen nach, oben steht, wie viele
  Übungen passen. „Alles leeren“ und „Fertig“ stehen fest unten. Ein Blatt ist modal — der
  Tipp daneben schließt es und wählt keine Übung (Ben, 22.10.2026), ohne den Schirm, den die
  aufklappenden Kästen dafür brauchten.

Was passt, was wegfällt und was im Bereich Paket steht, rechnet `core/uebungsfilter.py`. Die
Ansicht zeichnet bei jeder Änderung nur ihre Liste neu (``on_change``) — Suchzeile, Labels und
Blatt zieht die Leiste selbst nach. Die Mechanik steht seit 12.11.2026 in
`components/filterblatt.py` (auch der Reiter „Notizen“ nutzt sie); hier nur die drei Bereiche.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import flet as ft

from trainingsapp.core.uebungsfilter import Uebungsfilter
from trainingsapp.ui.components.filterblatt import Bereich, Filterblatt, treffer_text

TYP, REGION, PAKET = "Typ", "Region", "Paket"
BEREICHE = (TYP, REGION, PAKET)
#: Bereich → (Symbol, Farbe seiner Labels): so sieht man auf einen Blick, was wofür steht
ART: dict[str, tuple[ft.IconData, str]] = {
    TYP: (ft.Icons.CATEGORY_OUTLINED, ft.Colors.SECONDARY_CONTAINER),
    REGION: (ft.Icons.ACCESSIBILITY_NEW, ft.Colors.TERTIARY_CONTAINER),
    PAKET: (ft.Icons.INVENTORY_2_OUTLINED, ft.Colors.PRIMARY_CONTAINER),
}


class FilterLeiste(Filterblatt):
    """Die Filterleiste der Übungsauswahl: Typ · Region · Paket.

    ``typen``/``regionen`` sind Namen, ``pakete`` Paare ``(ID, Name)`` — ``None`` für die
    eigenen Übungen (`core.uebungsfilter.paket_wahl`). Gewähltes, das nicht mehr zur Wahl
    steht, fällt aus ``filter_`` heraus. ``on_change`` zeichnet die Liste neu (samt
    ``page.update``), ``zaehlen`` sagt, wie viele Übungen gerade passen.
    """

    def __init__(
        self,
        page: ft.Page,
        filter_: Uebungsfilter,
        typen: Iterable[str],
        regionen: Iterable[str],
        pakete: Iterable[tuple[str | None, str]],
        *,
        on_change: Callable[[], None],
        zaehlen: Callable[[], int],
    ) -> None:
        self.filter = filter_
        super().__init__(
            page,
            [
                Bereich(TYP, *ART[TYP], [(t, t) for t in dict.fromkeys(typen)], filter_.typen),
                Bereich(
                    REGION,
                    *ART[REGION],
                    [(r, r) for r in dict.fromkeys(regionen)],
                    filter_.regionen,
                ),
                Bereich(PAKET, *ART[PAKET], list(dict.fromkeys(pakete)), filter_.pakete),
            ],
            on_change=on_change,
            zaehlen=zaehlen,
        )


__all__ = ["ART", "BEREICHE", "PAKET", "REGION", "TYP", "FilterLeiste", "treffer_text"]
