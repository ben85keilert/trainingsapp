"""Der Filter der Übungsauswahl: Typ, Region und Paket (Ben, 9.11.2026).

Katalog und „Übung hinzufügen“ filtern gleich (`ui/components/uebungsfilter.py`): ein Knopf
in der Suchzeile, die wirkenden Filter als Labels darunter, ein Blatt mit den drei Bereichen
und „Alles leeren“. Innerhalb eines Bereichs genügt ein Treffer (oder), zwischen den
Bereichen müssen alle passen (und); ein leerer Bereich lässt alles durch.

**Paket** heißt Herkunft (`Exercise.package_id`): ``None`` (`EIGENE`) steht für die eigenen
Übungen — ohne Paket, auch Kopien aus einem Paket. Ergänzungen (U5) ändern die Herkunft
nicht: Eine Übung aus „Standard“, die ein anderes Paket ergänzt, bleibt bei „Standard“.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from trainingsapp.core.models import Exercise, passt_zum_filter
from trainingsapp.core.pakete import Paket

#: Die eigenen Übungen in der Paketwahl — Übungen ohne Paket
EIGENE: str | None = None
EIGENE_TEXT = "Eigene Übungen"


@dataclass(slots=True)
class Uebungsfilter:
    """Die drei Bereiche; leer = kein Filter. Liegt im `AppState`, damit die Wahl den
    Wechsel der Ansicht übersteht — je Ort ein eigener (Katalog, „Übung hinzufügen“).

    >>> f = Uebungsfilter(typen={"Kräftigung"}, pakete={EIGENE})
    >>> f.passt(Exercise(typen=["Kräftigung"]))
    True
    >>> f.passt(Exercise(typen=["Kräftigung"], package_id="standard"))
    False
    >>> f.anzahl, f.leer
    (2, False)
    >>> f.leeren()
    >>> f.leer, f.passt(Exercise(package_id="standard"))
    (True, True)
    """

    typen: set[str] = field(default_factory=set)
    regionen: set[str] = field(default_factory=set)
    pakete: set[str | None] = field(default_factory=set)

    @property
    def leer(self) -> bool:
        """Kein Bereich schränkt ein."""
        return not (self.typen or self.regionen or self.pakete)

    @property
    def anzahl(self) -> int:
        """Wie viele Filter wirken — die Zahl am Knopf."""
        return len(self.typen) + len(self.regionen) + len(self.pakete)

    def passt(self, uebung: Exercise) -> bool:
        """Typ und Region wie `passt_zum_filter`, dazu die Herkunft."""
        return passt_zum_filter(uebung, self.typen, self.regionen) and (
            not self.pakete or uebung.package_id in self.pakete
        )

    def leeren(self) -> None:
        """„Alles leeren“ — alle drei Bereiche."""
        self.typen.clear()
        self.regionen.clear()
        self.pakete.clear()

    def bereinigen(
        self, typen: Iterable[str], regionen: Iterable[str], pakete: Iterable[str | None]
    ) -> None:
        """Was es nicht mehr gibt, fällt weg — ein gelöschter Tag, ein entferntes oder
        deaktiviertes Paket, die letzte eigene Übung. Sonst filterte ein unsichtbarer Wert.

        >>> f = Uebungsfilter(typen={"Atmung", "weg"}, pakete={"alt", EIGENE})
        >>> f.bereinigen(["Atmung", "Dehnung"], [], ["standard", EIGENE])
        >>> sorted(f.typen), f.pakete
        (['Atmung'], {None})
        """
        self.typen &= set(typen)
        self.regionen &= set(regionen)
        self.pakete &= set(pakete)


def paket_wahl(
    uebungen: Iterable[Exercise], pakete: Iterable[Paket]
) -> list[tuple[str | None, str]]:
    """Was im Bereich „Paket“ steht: jedes Paket, das Übungen im Katalog hat, in der
    Reihenfolge von ``pakete`` (wie im Paketmanager: nach Installation), dann „Eigene
    Übungen“, wenn es welche gibt. Ein Paket ohne Übung im Katalog (nur Ergänzungen,
    deaktiviert, alles archiviert) fehlt — der Filter fände nichts.

    >>> u = [Exercise(package_id="qi"), Exercise(package_id="std"), Exercise()]
    >>> paket_wahl(u, [Paket(id="std", name="Standard"), Paket(id="qi", name="Qigong"),
    ...                Paket(id="leer", name="Nur Ergänzungen")])
    [('std', 'Standard'), ('qi', 'Qigong'), (None, 'Eigene Übungen')]
    >>> paket_wahl([Exercise(package_id="std")], [Paket(id="std", name="Standard")])
    [('std', 'Standard')]
    """
    da = {u.package_id for u in uebungen}
    wahl: list[tuple[str | None, str]] = [(p.id, p.name) for p in pakete if p.id in da]
    bekannt = {pid for pid, _ in wahl}
    # Herkunft ohne Eintrag in der Paketliste (sollte es nicht geben): trotzdem wählbar
    wahl += [(pid, "Paket ohne Namen") for pid in sorted(da - bekannt - {EIGENE}, key=str)]
    if EIGENE in da:
        wahl.append((EIGENE, EIGENE_TEXT))
    return wahl


__all__ = ["EIGENE", "EIGENE_TEXT", "Uebungsfilter", "paket_wahl"]
