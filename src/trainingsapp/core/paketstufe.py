"""Wie groß ein Paket-Update ist — bestimmt aus dem **Unterschied**, nicht aus der Nummer (U6,
Ben 9.11.2026, F8 (c); `docs/plan_paketversionen.md` §2, §3, §6).

„Stufe aus dem Unterschied und Modus — *Alle* = Y und Z automatisch, X fragt; *Kleine* = nur Z;
*Manuell* = alles fragt; Eigenes bleibt.“ Die App vergleicht den gespeicherten Paketstand mit
der neuen Datei:

- **groß** (X): etwas fällt weg — eine Übung, ein Kurs, ein Kapitel, ein Plan, eine Ergänzung —,
  ein Kapitel wird dazwischengeschoben oder wandert, eine Kapitelbedingung oder die
  Freischaltung eines Kurses ändert sich (der Fortschritt hängt daran).
- **mittel** (Y): etwas kommt dazu (Übung, Kurs, Kapitel am Ende, Plan, Ergänzung), Texte,
  Medien, andere Felder der Eingabe, Pläne.
- **klein** (Z): nur Vorgaben — Chips und Grenzen der Eingabe, Ziel, Timer, Uhr, Symbol, Typen,
  Regionen, Sensor-Karte, Takt, Plan-Vorlagen eines Kapitels.

Die höchste Stufe zählt. Eine falsche Nummer richtet so nichts an; das Werkzeug hält sie
ehrlich (`version_reicht`, ``trainingsapp-paket pruefen --gegen``). Was die Person geändert
hat, bleibt bei jeder Stufe (Drei-Wege-Abgleich, U1).

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .eigenes_paket import GROSS, KLEIN, MITTEL, naechste_version
from .pakete import FELDNAMEN, Paketinhalt, kurs_stand, plan_stand, stand
from .paketversion import AUTO, MANUELL, version_teile, version_text

KEINE: Final = "keine"
#: Reihenfolge der Stufen — die höchste zählt
RANG: Final[dict[str, int]] = {KEINE: 0, KLEIN: 1, MITTEL: 2, GROSS: 3}
#: So heißen sie in der App
STUFE_TEXT: Final[dict[str, str]] = {
    KEINE: "unverändert",
    KLEIN: "kleine Änderung",
    MITTEL: "mittlere Änderung",
    GROSS: "große Änderung",
}
#: Felder einer Übung, deren Änderung mittel ist (Texte, Medien); die Eingabe gesondert
_MITTEL: Final = ("name", "description", "media")
#: … und klein (Vorgaben)
_KLEIN: Final = (
    "icon_key",
    "typen",
    "regionen",
    "default_target",
    "limit_spec",
    "timer",
    "uhr",
    "zaehlt_als",
    "beschleunigung",
    "takt",
    "gps",
)


@dataclass(slots=True)
class Stufe:
    """Die Stufe eines Updates und warum — je Grund eine Zeile für Menschen."""

    stufe: str = KEINE
    gruende: list[str] = field(default_factory=list)

    def dazu(self, stufe: str, grund: str) -> None:
        if RANG[stufe] > RANG[self.stufe]:
            self.stufe = stufe
        self.gruende.append(grund)

    @property
    def text(self) -> str:
        return STUFE_TEXT[self.stufe]


def _eingabe(spec: Any) -> list[tuple[Any, Any]]:
    """Schlüssel und Art der Felder einer Eingabe — ihre Änderung ist mittel."""
    felder = spec.get("fields") if isinstance(spec, Mapping) else None
    return [(f.get("key"), f.get("type")) for f in felder or [] if isinstance(f, Mapping)]


def uebung_stufe(alt: Mapping[str, Any], neu: Mapping[str, Any], name: str, s: Stufe) -> None:
    """Was sich an einer Übung geändert hat (Paketstände wie `core.pakete.stand`).

    >>> s = Stufe()
    >>> uebung_stufe({"name": "A", "timer": []}, {"name": "A", "timer": [{"x": 1}]}, "A", s)
    >>> s.stufe, s.gruende
    ('klein', ['„A“: Timer'])
    >>> uebung_stufe({"description": "a"}, {"description": "b"}, "A", s); s.stufe
    'mittel'
    """
    for feld in _MITTEL:
        if alt.get(feld) != neu.get(feld):
            s.dazu(MITTEL, f"„{name}“: {FELDNAMEN.get(feld, feld)}")
    alt_spec, neu_spec = alt.get("result_spec"), neu.get("result_spec")
    if _eingabe(alt_spec) != _eingabe(neu_spec):
        s.dazu(MITTEL, f"„{name}“: Felder der Eingabe")
    elif alt_spec != neu_spec:
        s.dazu(KLEIN, f"„{name}“: Chips und Vorgaben der Eingabe")
    for feld in _KLEIN:
        if alt.get(feld) != neu.get(feld):
            s.dazu(KLEIN, f"„{name}“: {FELDNAMEN.get(feld, feld)}")


def _kurs_stufe(alt: Mapping[str, Any], neu: Mapping[str, Any], s: Stufe) -> None:
    name = str(neu.get("name") or alt.get("name") or "Kurs")
    if alt.get("freischaltung") != neu.get("freischaltung"):
        s.dazu(GROSS, f"Kurs „{name}“: Freischaltung")
    alt_kap = {k["id"]: k for k in alt.get("kapitel") or []}
    neu_kap = {k["id"]: k for k in neu.get("kapitel") or []}
    alt_folge = [k for k in (x["id"] for x in alt.get("kapitel") or []) if k in neu_kap]
    neu_folge = [k for k in (x["id"] for x in neu.get("kapitel") or []) if k in alt_kap]
    for kid in alt_kap.keys() - neu_kap.keys():
        s.dazu(GROSS, f"Kurs „{name}“: Kapitel „{alt_kap[kid].get('titel')}“ fällt weg")
    if alt_folge != neu_folge:
        s.dazu(GROSS, f"Kurs „{name}“: Kapitel in anderer Reihenfolge")
    # Neue Kapitel: am Ende mittel, dazwischen groß (das erste offene wäre sonst ein anderes)
    letzte_alte = max(
        (i for i, k in enumerate(neu.get("kapitel") or []) if k["id"] in alt_kap), default=-1
    )
    for i, k in enumerate(neu.get("kapitel") or []):
        if k["id"] not in alt_kap:
            stufe = GROSS if i < letzte_alte else MITTEL
            s.dazu(stufe, f"Kurs „{name}“: Kapitel „{k.get('titel')}“ kommt dazu")
    for kid in alt_kap.keys() & neu_kap.keys():
        a, n = alt_kap[kid], neu_kap[kid]
        titel = n.get("titel") or a.get("titel")
        if a.get("bedingung") != n.get("bedingung"):
            s.dazu(GROSS, f"Kurs „{name}“, Kapitel „{titel}“: Bedingung")
        for feld, wort in (("titel", "Titel"), ("text", "Text"), ("media", "Medien")):
            if a.get(feld) != n.get(feld):
                s.dazu(MITTEL, f"Kurs „{name}“, Kapitel „{titel}“: {wort}")
        if a.get("plaene") != n.get("plaene"):
            s.dazu(KLEIN, f"Kurs „{name}“, Kapitel „{titel}“: Plan-Vorlagen")
    for feld, wort in (("name", "Name"), ("beschreibung", "Beschreibung")):
        if alt.get(feld) != neu.get(feld):
            s.dazu(MITTEL, f"Kurs „{name}“: {wort}")


def stufe(alt: Paketinhalt, neu: Paketinhalt) -> Stufe:
    """Die Stufe von ``alt`` (dem gespeicherten Paketstand) zu ``neu`` (der Datei).

    >>> from trainingsapp.core.pakete import paket_lesen
    >>> a = paket_lesen({"paket": {"name": "Q"}, "exercises": [{"key": "a", "name": "A"},
    ...                  {"key": "b", "name": "B"}]})
    >>> n = paket_lesen({"paket": {"name": "Q"}, "exercises": [{"key": "a", "name": "A"},
    ...                  {"key": "c", "name": "C"}]})
    >>> s = stufe(a, n)
    >>> s.stufe, s.gruende
    ('gross', ['„B“ fällt weg', '„C“ kommt dazu'])
    >>> stufe(a, a).stufe
    'keine'
    """
    s = Stufe()
    alt_u = {u.id: u for u in alt.uebungen}
    neu_u = {u.id: u for u in neu.uebungen}
    for uid in [u.id for u in alt.uebungen if u.id not in neu_u]:
        s.dazu(GROSS, f"„{alt_u[uid].name}“ fällt weg")
    for uid in [u.id for u in neu.uebungen if u.id not in alt_u]:
        s.dazu(MITTEL, f"„{neu_u[uid].name}“ kommt dazu")
    for uid in [u.id for u in neu.uebungen if u.id in alt_u]:
        uebung_stufe(stand(alt_u[uid]), stand(neu_u[uid]), neu_u[uid].name, s)
    alt_k = {k.id: k for k in alt.kurse}
    neu_k = {k.id: k for k in neu.kurse}
    for kid in alt_k.keys() - neu_k.keys():
        s.dazu(GROSS, f"Kurs „{alt_k[kid].name}“ fällt weg")
    for kid in neu_k.keys() - alt_k.keys():
        s.dazu(MITTEL, f"Kurs „{neu_k[kid].name}“ kommt dazu")
    for kid in alt_k.keys() & neu_k.keys():
        _kurs_stufe(kurs_stand(alt_k[kid]), kurs_stand(neu_k[kid]), s)
    alt_p = {p.key: p for p in alt.plaene}
    neu_p = {p.key: p for p in neu.plaene}
    for key in alt_p.keys() - neu_p.keys():
        s.dazu(GROSS, f"Plan „{alt_p[key].vorlage.name}“ fällt weg")
    for key in neu_p.keys() - alt_p.keys():
        s.dazu(MITTEL, f"Plan „{neu_p[key].vorlage.name}“ kommt dazu")
    for key in alt_p.keys() & neu_p.keys():
        if plan_stand(alt_p[key]) != plan_stand(neu_p[key]):
            s.dazu(MITTEL, f"Plan „{neu_p[key].vorlage.name}“ geändert")
    _ergaenzungen_stufe(alt, neu, s)
    return s


def _ergaenzungen_stufe(alt: Paketinhalt, neu: Paketinhalt, s: Stufe) -> None:
    alt_e = {e.uebung_id: e.daten for e in alt.ergaenzungen}
    neu_e = {e.uebung_id: e.daten for e in neu.ergaenzungen}
    for _ in alt_e.keys() - neu_e.keys():
        s.dazu(GROSS, "eine Ergänzung fällt weg")
    for _ in neu_e.keys() - alt_e.keys():
        s.dazu(MITTEL, "eine Ergänzung kommt dazu")
    for uid in alt_e.keys() & neu_e.keys():
        a, n = alt_e[uid], neu_e[uid]
        if any(a.get(f) != n.get(f) for f in ("description", "media")):
            s.dazu(MITTEL, "eine Ergänzung: Texte oder Medien")
        if any(a.get(f) != n.get(f) for f in ("result_spec", "default_target", "timer", "takt")):
            s.dazu(KLEIN, "eine Ergänzung: Vorgaben")


def automatisch(modus: str, s: str) -> bool:
    """Spielt die App ein Update dieser Stufe im ``modus`` von selbst ein (F8 c)?

    >>> [automatisch(AUTO, x) for x in (KEINE, KLEIN, MITTEL, GROSS)]
    [True, True, True, False]
    >>> from trainingsapp.core.paketversion import KLEIN as KLEINE
    >>> [automatisch(KLEINE, x) for x in (KEINE, KLEIN, MITTEL, GROSS)]
    [True, True, False, False]
    >>> automatisch(MANUELL, KLEIN)
    False
    """
    if modus == MANUELL:
        return False
    if modus == AUTO:
        return RANG[s] < RANG[GROSS]
    return RANG[s] <= RANG[KLEIN]  # „Kleine“


def version_reicht(alt: int | None, neu: int | None, s: str) -> bool:
    """Steigt die Nummer genug für die Stufe? Groß braucht X, mittel X oder Y, klein irgendeine.

    >>> version_reicht(10400, 10500, GROSS), version_reicht(10400, 20000, GROSS)
    (False, True)
    >>> version_reicht(10400, 10401, MITTEL), version_reicht(10400, 10500, MITTEL)
    (False, True)
    >>> version_reicht(10400, 10400, KLEIN), version_reicht(10400, 10400, KEINE)
    (False, True)
    """
    if s == KEINE or alt is None:
        return True
    if neu is None or neu <= alt:
        return False
    if s == GROSS:
        return version_teile(neu)[0] > version_teile(alt)[0]
    if s == MITTEL:
        return version_teile(neu)[:2] > version_teile(alt)[:2]
    return True


def mindestens(alt: int | None, s: str) -> str:
    """Die kleinste Version, die zur Stufe passt — für Meldungen.

    >>> mindestens(10400, GROSS), mindestens(10400, MITTEL), mindestens(10400, KLEIN)
    ('2.0.0', '1.5.0', '1.4.1')
    """
    return version_text(naechste_version(alt, s if s in (KLEIN, MITTEL, GROSS) else KLEIN))


def stufen_text(gruende: Iterable[str], hoechstens: int = 4) -> str:
    """Die ersten Gründe als eine Zeile.

    >>> stufen_text(["a", "b", "c"], 2)
    'a; b; … und 1 weitere'
    """
    alle = list(gruende)
    rest = len(alle) - hoechstens
    return "; ".join(alle[:hoechstens]) + (f"; … und {rest} weitere" if rest > 0 else "")


__all__ = [
    "GROSS",
    "KEINE",
    "KLEIN",
    "MITTEL",
    "RANG",
    "STUFE_TEXT",
    "Stufe",
    "automatisch",
    "mindestens",
    "stufe",
    "stufen_text",
    "uebung_stufe",
    "version_reicht",
]
