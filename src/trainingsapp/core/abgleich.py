"""Drei-Wege-Abgleich je Abschnitt und je Medium (Ben, 9.11.2026, `docs/plan_paketinhalte.md` §6).

Ein Update einer Paketübung gleicht seit dem 16.10.2026 **je Feld** ab: Was die Person geändert
hat, bleibt — als ganzes Feld. Für die Beschreibung (seit P108 in Abschnitten, `core/
beschreibung.py`) und die Medien war das zu grob: Eine eigene Zeile hielt jede Textkorrektur
des Pakets fern, ein eigener Link jeden neuen Link. Hier geht es feiner:

- **Beschreibung je Abschnitt** (Schlüssel: der Name ohne Groß/klein, doppelte mit „#2“): Was
  die Person nicht angefasst hat, bekommt das Update; ein eigener Abschnitt bleibt; einer, den
  sie geändert oder gestrichen hat, bleibt so; was das Paket neu hat, kommt an seiner Stelle
  dazu; was es streicht und niemand angefasst hat, geht.
- **Medien je Eintrag** (Schlüssel: die Adresse) nach derselben Regel.
- **Hinweise**: Wo das Paket eine neue Fassung hat, die eigene aber blieb, entsteht ein
  `Hinweis` — die Übung zeigt ihn, „Paketfassung übernehmen“ holt sie (`uebernehmen`).

Unberührtes bleibt wörtlich: Ist ein Feld bei der Person wie im alten Paketstand, gilt der neue
Paketstand Zeichen für Zeichen; ist es beim Paket unverändert, die eigene Fassung. Erst wenn
beide geändert haben, zerlegt der Abgleich in Abschnitte (`zusammen` setzt dann neu zusammen).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .beschreibung import Abschnitt, abschnitte, zusammen

#: Felder, die je Teil abgeglichen werden
BESCHREIBUNG, MEDIEN = "description", "media"


@dataclass(frozen=True, slots=True)
class Hinweis:
    """Das Paket hat hier eine neue Fassung, die eigene blieb — ``teil``: der Abschnitt der
    Beschreibung (sein Schlüssel) bzw. die Adresse des Mediums; leer = das ganze Feld."""

    feld: str
    teil: str = ""

    def als_liste(self) -> list[str]:
        return [self.feld, self.teil]


@dataclass(frozen=True, slots=True)
class Unterschied:
    """Wo die eigene Fassung vom Paketstand abweicht — für den Vergleich in der Übung."""

    feld: str
    teil: str
    #: „Beschreibung › Ausführung“, „Videos › Erklärvideo“, „Timer“
    titel: str
    #: Was im Paket steht — leer, wenn es dort fehlt
    paket: str
    #: Was hier steht — leer, wenn es hier fehlt
    eigen: str
    #: Gibt es eine Paketfassung zum Übernehmen? (Ein eigener Abschnitt hat keine.)
    uebernehmbar: bool


def schluessel_abschnitte(text: str) -> list[tuple[str, Abschnitt]]:
    """Die Abschnitte mit Schlüssel — der Name ohne Groß/klein; ein zweiter gleichen Namens
    heißt „name#2“; der Abschnitt ohne Namen hat den Schlüssel „“.

    >>> [k for k, _ in schluessel_abschnitte("Vorweg\\n## Hinweis\\na\\n## hinweis\\nb")]
    ['', 'hinweis', 'hinweis#2']
    """
    gesehen: dict[str, int] = {}
    out: list[tuple[str, Abschnitt]] = []
    for a in abschnitte(text or ""):
        grund = a.name.strip().casefold()
        n = gesehen.get(grund, 0) + 1
        gesehen[grund] = n
        out.append((grund if n == 1 else f"{grund}#{n}", a))
    return out


def _gleicher_abschnitt(a: Abschnitt | None, b: Abschnitt | None) -> bool:
    if a is None or b is None:
        return a is b
    return a.name.strip() == b.name.strip() and a.text.strip() == b.text.strip()


def gleiche_abschnitte(a: str, b: str) -> bool:
    """Gleiche Abschnitte, nur anders gesetzt (Leerzeilen)?

    >>> gleiche_abschnitte("a\\n\\n## B\\nb", "a\\n## B\\nb\\n")
    True
    """
    ka, kb = schluessel_abschnitte(a), schluessel_abschnitte(b)
    return [k for k, _ in ka] == [k for k, _ in kb] and all(
        _gleicher_abschnitt(x, y) for (_, x), (_, y) in zip(ka, kb, strict=True)
    )


def liste_abgleichen[T](
    basis: Sequence[tuple[str, T]],
    nutzer: Sequence[tuple[str, T]],
    soll: Sequence[tuple[str, T]],
    gleich: Callable[[T | None, T | None], bool],
) -> tuple[list[tuple[str, T]], list[str]]:
    """Drei-Wege-Abgleich einer geordneten Liste mit Schlüsseln — ``(Ergebnis, Hinweise)``.

    Die Reihenfolge ist die der eigenen Fassung; was das Paket neu hat, steht hinter seinem
    Vorgänger aus dem Paket.

    >>> g = lambda a, b: a == b
    >>> b = [("a", 1), ("b", 2)]
    >>> liste_abgleichen(b, [("a", 1), ("b", 9), ("x", 5)], [("a", 3), ("b", 4), ("c", 6)], g)
    ([('a', 3), ('b', 9), ('c', 6), ('x', 5)], ['b'])

    Gestrichen — vom Paket (unberührt: geht) oder von der Person (bleibt weg):

    >>> liste_abgleichen(b, [("a", 1)], [("b", 2)], g)
    ([], [])
    """
    alt = dict(basis)
    eigen = dict(nutzer)
    neu = dict(soll)
    hinweise: list[str] = []
    ergebnis: list[tuple[str, T]] = []
    for k, n in nutzer:
        if k in alt:
            if gleich(n, alt[k]):  # nicht angefasst
                if k in neu:
                    ergebnis.append((k, neu[k]))
                continue  # vom Paket gestrichen
            ergebnis.append((k, n))  # selbst geändert — bleibt
            if k in neu and not gleich(neu[k], alt[k]) and not gleich(neu[k], n):
                hinweise.append(k)
        else:
            ergebnis.append((k, n))  # selbst dazu
            if k in neu and not gleich(neu[k], n):
                hinweise.append(k)
    da = {k for k, _ in ergebnis}
    for i, (k, s) in enumerate(soll):
        if k in da or k in eigen:
            continue
        if k in alt:  # die Person hat ihn gestrichen — bleibt weg
            if not gleich(s, alt[k]):
                hinweise.append(k)
            continue
        pos = 0
        for j in range(i - 1, -1, -1):
            stelle = next((x for x, (kk, _) in enumerate(ergebnis) if kk == soll[j][0]), None)
            if stelle is not None:
                pos = stelle + 1
                break
        ergebnis.insert(pos, (k, s))
        da.add(k)
    return ergebnis, hinweise


def beschreibung_abgleichen(basis: str, nutzer: str, soll: str) -> tuple[str, list[str]]:
    """Die Beschreibung je Abschnitt — ``(Text, Schlüssel der Abschnitte mit Hinweis)``.

    >>> alt = "Füße hüftbreit.\\n## Worauf achten\\nFersen am Boden."
    >>> mein = alt + "\\n## Für Ben\\nlangsam"
    >>> neu = "Füße hüftbreit, Arme vorn.\\n## Worauf achten\\nFersen am Boden."
    >>> text, hinweise = beschreibung_abgleichen(alt, mein, neu)
    >>> print(text)
    Füße hüftbreit, Arme vorn.
    ## Worauf achten
    Fersen am Boden.
    ## Für Ben
    langsam
    >>> hinweise
    []

    Unberührt bleibt der Text wörtlich (auch Leerzeilen):

    >>> beschreibung_abgleichen(alt, alt, neu + "\\n\\n")[0] == neu + "\\n\\n"
    True
    """
    if nutzer == basis or gleiche_abschnitte(nutzer, basis):
        return soll, []
    if soll == basis or gleiche_abschnitte(soll, basis):
        return nutzer, []
    teile, hinweise = liste_abgleichen(
        schluessel_abschnitte(basis),
        schluessel_abschnitte(nutzer),
        schluessel_abschnitte(soll),
        _gleicher_abschnitt,
    )
    return zusammen(a for _, a in teile), hinweise


def _medien_mit_schluessel(medien: Iterable[Mapping[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(m.get("uri", "")).strip(), dict(m)) for m in medien]


def medien_abgleichen(
    basis: Sequence[Mapping[str, Any]],
    nutzer: Sequence[Mapping[str, Any]],
    soll: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Die Medien je Eintrag (Schlüssel: die Adresse) — ``(Medien, Adressen mit Hinweis)``.

    >>> v = lambda uri, titel="": {"kind": "video", "source": "url", "uri": uri, "title": titel}
    >>> mein, hinweise = medien_abgleichen([v("a")], [v("a"), v("mein")], [v("a"), v("neu")])
    >>> [m["uri"] for m in mein], hinweise
    (['a', 'neu', 'mein'], [])
    """
    if list(nutzer) == list(basis):
        return [dict(m) for m in soll], []
    if list(soll) == list(basis):
        return [dict(m) for m in nutzer], []
    teile, hinweise = liste_abgleichen(
        _medien_mit_schluessel(basis),
        _medien_mit_schluessel(nutzer),
        _medien_mit_schluessel(soll),
        lambda a, b: a == b,
    )
    return [m for _, m in teile], hinweise


def abgleichen(
    basis: Mapping[str, Any],
    nutzer: Mapping[str, Any],
    soll: Mapping[str, Any],
    felder: Iterable[str],
) -> tuple[dict[str, Any], list[Hinweis]]:
    """Der Drei-Wege-Abgleich aller ``felder`` — ``(Ergebnis, Hinweise)``. Beschreibung und
    Medien je Teil, alle anderen je Feld.

    >>> basis = {"name": "Baum", "description": "Knie weich."}
    >>> nutzer = {"name": "Mein Baum", "description": "Knie weich.\\n## Für mich\\nlangsam"}
    >>> soll = {"name": "Baum stehen", "description": "Knie weich, Blick geradeaus."}
    >>> ergebnis, hinweise = abgleichen(basis, nutzer, soll, ["name", "description"])
    >>> ergebnis["name"], ergebnis["description"]
    ('Mein Baum', 'Knie weich, Blick geradeaus.\\n## Für mich\\nlangsam')
    >>> hinweise
    [Hinweis(feld='name', teil='')]
    """
    ergebnis: dict[str, Any] = {}
    hinweise: list[Hinweis] = []
    for feld in felder:
        b, n, s = basis.get(feld), nutzer.get(feld), soll.get(feld)
        wert: Any
        if feld == BESCHREIBUNG:
            wert, teile = beschreibung_abgleichen(b or "", n or "", s or "")
            hinweise += [Hinweis(feld, t) for t in teile]
            wert = wert or None
        elif feld == MEDIEN:
            wert, teile = medien_abgleichen(b or [], n or [], s or [])
            hinweise += [Hinweis(feld, t) for t in teile]
            wert = wert or None
        else:
            geaendert = n != b
            wert = n if geaendert else s
            if geaendert and s != b and s != n:
                hinweise.append(Hinweis(feld))
        if wert is not None:
            ergebnis[feld] = wert
    return ergebnis, hinweise


def _kurz(wert: Any, laenge: int = 160) -> str:
    if wert is None:
        return ""
    if isinstance(wert, str):
        text = wert.strip()
    elif isinstance(wert, list | dict):
        text = str(len(wert)) + (" Einträge" if isinstance(wert, list) else " Angaben")
    else:
        text = str(wert)
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def unterschiede(
    nutzer: Mapping[str, Any], paket: Mapping[str, Any], felder: Mapping[str, str]
) -> list[Unterschied]:
    """Wo die eigene Fassung vom Paketstand abweicht — die Beschreibung je Abschnitt, Medien
    je Eintrag, sonst je Feld (``felder``: Schlüssel → Anzeigename).

    >>> felder = {"name": "Name", "description": "Beschreibung"}
    >>> paket = {"name": "Baum", "description": "Knie weich.\\n## Atmen\\nruhig"}
    >>> mein = {"name": "Baum", "description": "Knie weich.\\n## Atmen\\ntief\\n## Für mich\\nx"}
    >>> [(u.titel, u.uebernehmbar) for u in unterschiede(mein, paket, felder)]
    [('Beschreibung › Atmen', True), ('Beschreibung › Für mich', False)]
    """
    out: list[Unterschied] = []
    for feld, anzeige in felder.items():
        n, p = nutzer.get(feld), paket.get(feld)
        if n == p:
            continue
        if feld == BESCHREIBUNG:
            if gleiche_abschnitte(n or "", p or ""):
                continue
            eigen = dict(schluessel_abschnitte(n or ""))
            vom_paket = dict(schluessel_abschnitte(p or ""))
            for k in dict.fromkeys([*vom_paket, *eigen]):
                a, b = eigen.get(k), vom_paket.get(k)
                if _gleicher_abschnitt(a, b):
                    continue
                name = (a or b or Abschnitt()).name.strip() or "Anfang"
                out.append(
                    Unterschied(
                        feld,
                        k,
                        f"{anzeige} › {name}",
                        b.text.strip() if b is not None else "",
                        a.text.strip() if a is not None else "",
                        b is not None,
                    )
                )
        elif feld == MEDIEN:
            eigen_m = dict(_medien_mit_schluessel(n or []))
            vom_paket_m = dict(_medien_mit_schluessel(p or []))
            for k in dict.fromkeys([*vom_paket_m, *eigen_m]):
                a_m, b_m = eigen_m.get(k), vom_paket_m.get(k)
                if a_m == b_m:
                    continue
                titel = str((a_m or b_m or {}).get("title") or k)
                out.append(
                    Unterschied(
                        feld,
                        k,
                        f"{anzeige} › {titel}",
                        k if b_m is not None else "",
                        k if a_m is not None else "",
                        b_m is not None,
                    )
                )
        else:
            out.append(Unterschied(feld, "", anzeige, _kurz(p), _kurz(n), p is not None))
    return out


def uebernehmen(
    nutzer: Mapping[str, Any], paket: Mapping[str, Any], feld: str, teil: str = ""
) -> dict[str, Any]:
    """Die Paketfassung eines Feldes — bei der Beschreibung eines Abschnitts, bei den Medien
    eines Eintrags — in die eigene Fassung holen. Der Rest bleibt.

    >>> paket = {"description": "Knie weich.\\n## Atmen\\nruhig"}
    >>> mein = {"description": "Knie weich.\\n## Atmen\\ntief\\n## Für mich\\nx"}
    >>> print(uebernehmen(mein, paket, "description", "atmen")["description"])
    Knie weich.
    ## Atmen
    ruhig
    ## Für mich
    x

    Sind danach alle Abschnitte wie im Paket, gilt dessen Text wörtlich:

    >>> uebernehmen({"description": "a"}, {"description": "b\\n"}, "description", "")
    {'description': 'b\\n'}
    """
    ergebnis = dict(nutzer)
    p = paket.get(feld)
    if feld == BESCHREIBUNG and teil != "*":
        eigen = schluessel_abschnitte(nutzer.get(feld) or "")
        vom_paket = schluessel_abschnitte(p or "")
        neu_teil = dict(vom_paket).get(teil)
        if neu_teil is None:  # im Paket gibt es ihn nicht mehr: herausnehmen
            teile = [(k, a) for k, a in eigen if k != teil]
        elif any(k == teil for k, _ in eigen):
            teile = [(k, neu_teil if k == teil else a) for k, a in eigen]
        else:  # fehlt hier: an seiner Stelle aus dem Paket einfügen
            vorher = [k for k, _ in vom_paket[: [k for k, _ in vom_paket].index(teil)]]
            stelle = max((i + 1 for i, (k, _) in enumerate(eigen) if k in vorher), default=0)
            teile = [*eigen[:stelle], (teil, neu_teil), *eigen[stelle:]]
        text = zusammen(a for _, a in teile)
        if gleiche_abschnitte(text, p or ""):
            text = p or ""
        if text:
            ergebnis[feld] = text
        else:
            ergebnis.pop(feld, None)
        return ergebnis
    if feld == MEDIEN and teil:
        eigen_m = _medien_mit_schluessel(nutzer.get(feld) or [])
        vom_paket_m = _medien_mit_schluessel(p or [])
        neu_m = dict(vom_paket_m).get(teil)
        if neu_m is None:
            medien = [m for k, m in eigen_m if k != teil]
        elif any(k == teil for k, _ in eigen_m):
            medien = [neu_m if k == teil else m for k, m in eigen_m]
        else:
            medien = [m for _, m in eigen_m] + [neu_m]
        if [m for _, m in vom_paket_m] == medien:
            medien = list(p or [])
        if medien:
            ergebnis[feld] = medien
        else:
            ergebnis.pop(feld, None)
        return ergebnis
    if p is None:
        ergebnis.pop(feld, None)
    else:
        ergebnis[feld] = p
    return ergebnis


def hinweise_lesen(roh: Any) -> list[Hinweis]:
    """Gespeicherte Hinweise (JSON-Liste von ``[feld, teil]``) — Unbrauchbares fällt weg.

    >>> hinweise_lesen([["description", "atmen"], ["timer", ""], "kaputt"])
    [Hinweis(feld='description', teil='atmen'), Hinweis(feld='timer', teil='')]
    """
    out: list[Hinweis] = []
    for h in roh if isinstance(roh, list) else []:
        if isinstance(h, list) and len(h) == 2 and all(isinstance(x, str) for x in h):
            out.append(Hinweis(h[0], h[1]))
    return out


__all__ = [
    "BESCHREIBUNG",
    "MEDIEN",
    "Hinweis",
    "Unterschied",
    "abgleichen",
    "beschreibung_abgleichen",
    "gleiche_abschnitte",
    "hinweise_lesen",
    "liste_abgleichen",
    "medien_abgleichen",
    "schluessel_abschnitte",
    "uebernehmen",
    "unterschiede",
]
