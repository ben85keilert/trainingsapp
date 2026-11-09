"""Ergänzungen („Mods“) — ein Paket ergänzt die Übung eines anderen (U5, Ben 9.11.2026,
`docs/plan_paketinhalte.md` §8, F2: „auch Parameter, Ziel, Timer, Takt — hier wird
individualisiert“).

Eine Übung, wie man sie sieht, ist eine Folge von **Schichten**: das Grundpaket, darüber die
Ergänzungen anderer Pakete in der Reihenfolge ihrer Installation (die spätere gewinnt je Feld),
darüber das Eigene der Person. `mit_ergaenzungen` legt die Ergänzungen auf den Paketstand des
Grundpakets — das Ergebnis ist der **wirksame Paketstand**, gegen den der Drei-Wege-Abgleich
(U1) läuft: Kommt, ändert oder geht eine Ergänzung, bleibt Eigenes wie bei jedem Update.

Was eine Ergänzung darf (`ERGAENZBAR`, Felder wie in `core.pakete.stand`):

- ``description`` — **Abschnitte**: ein benannter Abschnitt ersetzt den gleichnamigen der
  Übung, sonst kommt er hinten dazu; Abschnitte ohne Namen kommen immer dazu.
- ``media`` — Videos, Links, Dateien: was die Übung (nach Adresse) noch nicht hat, kommt dazu.
- ``result_spec`` (Parameter), ``default_target`` (Ziel), ``timer``, ``takt`` — ersetzen.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .abgleich import schluessel_abschnitte
from .beschreibung import Abschnitt, zusammen

#: Was eine Ergänzung an einer fremden Übung setzen darf
ERGAENZBAR: Final = ("description", "media", "result_spec", "default_target", "timer", "takt")
#: Felder, die eine Ergänzung ganz ersetzt
ERSETZT: Final = ("result_spec", "default_target", "timer", "takt")


@dataclass(slots=True)
class Ergaenzung:
    """Was ein Paket an einer Übung eines anderen Pakets ergänzt."""

    paket_id: str
    uebung_id: str
    #: Felder wie in `core.pakete.stand` — nur `ERGAENZBAR`
    daten: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Der Eintrag in ``ergaenzungen[]`` der Paketdatei.

        >>> Ergaenzung("p", "u", {"default_target": {"reps": [10]}}).to_dict()
        {'uebung': 'u', 'default_target': {'reps': [10]}}
        """
        return {"uebung": self.uebung_id, **json.loads(json.dumps(self.daten, ensure_ascii=False))}


def _gleich(a: Abschnitt, b: Abschnitt) -> bool:
    return a.name.strip() == b.name.strip() and a.text.strip() == b.text.strip()


def abschnitte_ergaenzen(text: str, zusatz: str) -> str:
    """Die Abschnitte von ``zusatz`` auf ``text``: gleicher Name ersetzt, neuer kommt hinten
    dazu, ohne Namen immer dazu.

    >>> zusatz = "## Achtung\\nKnie raus.\\n## Reha\\nLangsam."
    >>> abschnitte_ergaenzen("Grund.\\n## Achtung\\nKnie weich.", zusatz)
    'Grund.\\n## Achtung\\nKnie raus.\\n## Reha\\nLangsam.'
    """
    ergebnis = list(schluessel_abschnitte(text))
    stelle = {k: i for i, (k, _) in enumerate(ergebnis)}
    for k, a in schluessel_abschnitte(zusatz):
        if a.leer:
            continue
        if a.name.strip() and k in stelle:
            ergebnis[stelle[k]] = (k, a)
        else:
            stelle[k or f"#{len(ergebnis)}"] = len(ergebnis)
            ergebnis.append((k, a))
    return zusammen(a for _, a in ergebnis)


def mit_ergaenzungen(
    basis: Mapping[str, Any], ergaenzungen: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Der wirksame Paketstand: ``basis`` (Grundpaket) mit den Ergänzungen der Reihe nach.

    >>> b = {"name": "Kniebeuge", "description": "Tief.", "media": [{"uri": "https://a"}]}
    >>> e = {"description": "## Reha\\nLangsam.", "media": [{"uri": "https://a"}, {"uri": "https://b"}],
    ...      "default_target": {"reps": [8]}, "name": "Nicht erlaubt"}
    >>> w = mit_ergaenzungen(b, [e])
    >>> w["name"], w["description"], [m["uri"] for m in w["media"]], w["default_target"]
    ('Kniebeuge', 'Tief.\\n## Reha\\nLangsam.', ['https://a', 'https://b'], {'reps': [8]})
    >>> mit_ergaenzungen(b, []) == b
    True
    """
    ergebnis: dict[str, Any] = json.loads(json.dumps(dict(basis), ensure_ascii=False))
    for daten in ergaenzungen:
        for feld in ERGAENZBAR:
            if feld not in daten:
                continue
            wert = json.loads(json.dumps(daten[feld], ensure_ascii=False))
            if feld == "description":
                if isinstance(wert, str) and wert.strip():
                    ergebnis["description"] = abschnitte_ergaenzen(
                        str(ergebnis.get("description") or ""), wert
                    )
            elif feld == "media":
                vorhanden = {
                    m.get("uri") for m in ergebnis.get("media") or [] if isinstance(m, dict)
                }
                dazu = (
                    [m for m in wert if isinstance(m, dict) and m.get("uri") not in vorhanden]
                    if isinstance(wert, list)
                    else []
                )
                if dazu:
                    ergebnis["media"] = [*(ergebnis.get("media") or []), *dazu]
            else:
                ergebnis[feld] = wert
    return ergebnis


def herkunft(ergaenzungen: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, str]:
    """Welcher benannte Abschnitt aus welcher Ergänzung kommt — Schlüssel wie
    `core.abgleich.schluessel_abschnitte` → Paketname (die spätere gewinnt).

    >>> herkunft([("Knie-Reha", {"description": "## Reha\\nLangsam."})])
    {'reha': 'Knie-Reha'}
    """
    out: dict[str, str] = {}
    for name, daten in ergaenzungen:
        text = daten.get("description")
        if isinstance(text, str):
            for k, a in schluessel_abschnitte(text):
                if a.name.strip() and not a.leer:
                    out[k] = name
    return out


def ergaenzung_aus(basis: Mapping[str, Any], eigen: Mapping[str, Any]) -> dict[str, Any]:
    """Was ``eigen`` (der Stand einer fremden Übung hier) gegenüber ``basis`` (ihrem
    Paketstand) dazugeschrieben oder geändert hat — als Ergänzung für ein eigenes Paket (U4/U5:
    „eigene Änderungen an fremden Übungen als Ergänzung“). Weglassen lässt sich so nichts.

    >>> b = {"description": "Tief.\\n## Achtung\\nKnie weich.", "takt": None}
    >>> e = {"description": "Tief.\\n## Achtung\\nKnie raus.\\n## Für Anna\\nLangsam.",
    ...      "default_target": {"reps": [8]}, "media": [{"uri": "https://v"}]}
    >>> d = ergaenzung_aus(b, e)
    >>> d["description"], d["default_target"], [m["uri"] for m in d["media"]]
    ('## Achtung\\nKnie raus.\\n## Für Anna\\nLangsam.', {'reps': [8]}, ['https://v'])
    >>> ergaenzung_aus(b, b)
    {}
    """
    d: dict[str, Any] = {}
    alt = dict(schluessel_abschnitte(str(basis.get("description") or "")))
    neu = [
        a
        for k, a in schluessel_abschnitte(str(eigen.get("description") or ""))
        if not a.leer and (k not in alt or not _gleich(alt[k], a))
    ]
    if neu:
        d["description"] = zusammen(neu)
    vorhanden = {m.get("uri") for m in basis.get("media") or [] if isinstance(m, dict)}
    medien = [
        m for m in eigen.get("media") or [] if isinstance(m, dict) and m.get("uri") not in vorhanden
    ]
    if medien:
        d["media"] = medien
    for feld in ERSETZT:
        if feld in eigen and eigen.get(feld) != basis.get(feld):
            d[feld] = eigen[feld]
    return d


__all__ = [
    "ERGAENZBAR",
    "ERSETZT",
    "Ergaenzung",
    "abschnitte_ergaenzen",
    "ergaenzung_aus",
    "herkunft",
    "mit_ergaenzungen",
]
