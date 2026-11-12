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

**Stellungen** (Ben, 12.11.2026, P188): Parameter (samt Varianten und Chips), Ziel und Takt
sind die **Trainingsumgebung** einer Übung (`BUENDEL`) — sie lässt sich nicht zusammenlegen
(ein Ziel „3x15“ passt nur zu den Parametern, mit denen es geschrieben wurde). Statt „die
spätere gewinnt“ gibt es darum **einen Schalter**: Standard (das Grundpaket) oder eine
Erweiterung, die im Bündel etwas setzt (`stellungen`, `vorgabe`). `wirksam` bildet den
Paketstand für die gewählte Stellung: Beschreibung und Medien aus **allen** Erweiterungen,
die Timer aller Schichten in einer Liste (die der gewählten Stellung zuerst — das erste
Profil ist die Vorgabe der Übung), das Bündel nur aus der gewählten. Der Takt gehört ins
Bündel: Er ist ein einzelner Wert, und „Takt zählt“ zählt in ein Feld der Parameter.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from .abgleich import schluessel_abschnitte
from .beschreibung import Abschnitt, zusammen

#: Was eine Ergänzung an einer fremden Übung setzen darf
ERGAENZBAR: Final = ("description", "media", "result_spec", "default_target", "timer", "takt")
#: Felder, die eine Ergänzung ganz ersetzt
ERSETZT: Final = ("result_spec", "default_target", "timer", "takt")
#: Die Trainingsumgebung — gilt nur aus der gewählten Stellung (P188)
BUENDEL: Final = ("result_spec", "default_target", "takt")
#: Die Stellung des Grundpakets (sonst die ID des Pakets der Erweiterung)
STANDARD: Final = ""


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


def hat_buendel(daten: Mapping[str, Any]) -> bool:
    """Setzt die Ergänzung etwas an der Trainingsumgebung — ist sie eine **Stellung**?

    >>> hat_buendel({"default_target": {"reps": [8]}}), hat_buendel({"media": [], "timer": []})
    (True, False)
    """
    return any(feld in daten for feld in BUENDEL)


def stellungen(ergaenzungen: Iterable[tuple[str, Mapping[str, Any]]]) -> list[str]:
    """Die Pakete (IDs), die eine Stellung des Schalters sind — in der Reihenfolge ihrer
    Installation. „Standard“ (`STANDARD`) gibt es immer und steht nicht darin.

    >>> stellungen([("reha", {"result_spec": {}}), ("video", {"media": []}), ("qi", {"takt": {}})])
    ['reha', 'qi']
    """
    return [paket_id for paket_id, daten in ergaenzungen if hat_buendel(daten)]


def vorgabe(ergaenzungen: Iterable[tuple[str, Mapping[str, Any]]]) -> str:
    """Die Stellung, die gilt, solange niemand wählt: die zuletzt installierte Erweiterung
    mit Trainingsumgebung, sonst Standard.

    >>> vorgabe([("reha", {"result_spec": {}}), ("qi", {"takt": {}})]), vorgabe([("v", {})])
    ('qi', '')
    """
    liste = stellungen(ergaenzungen)
    return liste[-1] if liste else STANDARD


def aktive(ergaenzungen: Iterable[tuple[str, Mapping[str, Any]]], wahl: str | None) -> str:
    """Die geltende Stellung: die Wahl der Person, solange es sie gibt — sonst die Vorgabe.

    >>> ergs = [("reha", {"result_spec": {}}), ("qi", {"takt": {}})]
    >>> aktive(ergs, None), aktive(ergs, "reha"), aktive(ergs, ""), aktive(ergs, "weg")
    ('qi', 'reha', '', 'qi')
    """
    ergs = list(ergaenzungen)
    if wahl is not None and (wahl == STANDARD or wahl in stellungen(ergs)):
        return wahl
    return vorgabe(ergs)


def _kopie(wert: Any) -> Any:
    return json.loads(json.dumps(wert, ensure_ascii=False))


def _timer_zusammen(listen: Iterable[Any]) -> list[dict[str, Any]]:
    """Die Timer mehrerer Schichten in einer Liste — gleiche ID (ohne ID: gleicher Inhalt)
    nur einmal, die frühere Liste gewinnt."""
    out: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    for liste in listen:
        for profil in liste if isinstance(liste, list) else []:
            if not isinstance(profil, dict):
                continue
            kennung = str(profil.get("id") or json.dumps(profil, sort_keys=True))
            if kennung not in gesehen:
                gesehen.add(kennung)
                out.append(_kopie(profil))
    return out


def wirksam(
    basis: Mapping[str, Any],
    ergaenzungen: Sequence[tuple[str, Mapping[str, Any]]],
    stellung: str,
) -> dict[str, Any]:
    """Der wirksame Paketstand in einer **Stellung** (P188): ``basis`` (Grundpaket), darauf
    Beschreibung und Medien **aller** Ergänzungen, die Timer aller Schichten in einer Liste
    (die der Stellung zuerst, dann die übrigen Erweiterungen — die spätere vorn —, dann die
    des Grundpakets) und die Trainingsumgebung (`BUENDEL`) **nur** aus der Stellung. Was
    die Stellung im Bündel nicht setzt, bleibt wie im Grundpaket.

    >>> b = {"name": "Kniebeuge", "description": "Tief.", "result_spec": {"f": "reps"},
    ...      "default_target": {"reps": [15]}, "timer": [{"id": "t0"}]}
    >>> reha = {"description": "## Reha\\nLangsam.", "default_target": {"reps": [8]},
    ...         "timer": [{"id": "t1"}]}
    >>> kraft = {"result_spec": {"f": "weight"}, "media": [{"uri": "https://v"}]}
    >>> ergs = [("reha", reha), ("kraft", kraft)]
    >>> w = wirksam(b, ergs, "reha")
    >>> w["result_spec"], w["default_target"], [t["id"] for t in w["timer"]]
    ({'f': 'reps'}, {'reps': [8]}, ['t1', 't0'])
    >>> w["description"], [m["uri"] for m in w["media"]]  # geteilt: aus allen
    ('Tief.\\n## Reha\\nLangsam.', ['https://v'])
    >>> w = wirksam(b, ergs, "kraft")
    >>> w["result_spec"], w["default_target"], [t["id"] for t in w["timer"]]
    ({'f': 'weight'}, {'reps': [15]}, ['t1', 't0'])
    >>> w = wirksam(b, ergs, STANDARD)
    >>> w["result_spec"], w["default_target"], [t["id"] for t in w["timer"]]
    ({'f': 'reps'}, {'reps': [15]}, ['t0', 't1'])
    >>> wirksam(b, [], STANDARD) == b
    True
    """
    geteilt = [
        {feld: daten[feld] for feld in ("description", "media") if feld in daten}
        for _paket, daten in ergaenzungen
    ]
    ergebnis = mit_ergaenzungen(basis, geteilt)
    gewaehlt: Mapping[str, Any] = next(
        (daten for paket_id, daten in ergaenzungen if paket_id == stellung), {}
    )
    if stellung != STANDARD:
        for feld in BUENDEL:
            if feld in gewaehlt:
                ergebnis[feld] = _kopie(gewaehlt[feld])
    uebrige = [
        daten.get("timer")
        for paket_id, daten in reversed(list(ergaenzungen))
        if paket_id != stellung
    ]
    if any(isinstance(daten.get("timer"), list) for _p, daten in ergaenzungen):
        reihen = (
            [basis.get("timer"), *uebrige]
            if stellung == STANDARD
            else [gewaehlt.get("timer"), *uebrige, basis.get("timer")]
        )
        if timer := _timer_zusammen(reihen):
            ergebnis["timer"] = timer
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
    "BUENDEL",
    "ERGAENZBAR",
    "ERSETZT",
    "STANDARD",
    "Ergaenzung",
    "abschnitte_ergaenzen",
    "aktive",
    "ergaenzung_aus",
    "hat_buendel",
    "herkunft",
    "mit_ergaenzungen",
    "stellungen",
    "vorgabe",
    "wirksam",
]
