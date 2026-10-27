"""Eigene Abschnitte einer Messung als Paar Grenz-Notizen (Ben, 27.10.2026).

Ein Abschnitt, den die Person setzt — live mit „Abschnitt: Start“ / „… Ende“ oder
nachträglich mit „+ Abschnitt“ —, ist **ein Paar Notizen mit Marke** in der Messdatei:
``person/abschnitt`` (Start) und ``person/ende`` mit derselben ``spur``, seiner Kennung
(``seg-…``, zugleich die ``id`` im Sidecar). Name, **Kopf** und **Endteil** (`kopf_s`,
`endteil_s`: Sekunden mit Vorzeichen, positiv = außerhalb, negativ = innerhalb) hängen an
der Start-Notiz; das Sidecar wird daraus abgeleitet (`hrv_core.ausschnitte`). Die
Abschnitte des Timers bleiben ihre Kette von Grenz-Notizen — auch sie bekommen Kopf und
Endteil an ihrer Start-Notiz (`raender_setzen`). Vertrag: `docs/plan_abschnitte.md`,
`docs/kompatibilitaet.md` §4/§9b.

Ohne flet; Zeiten auf der Kurvenachse der App.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from hrv_core.ausschnitte import KENNUNG_PRAEFIX, Abschnitt, neue_kennung, paare_aus_notizen
from hrv_core.ereignisse import Zeitbezug, notiz

QUELLE = "person"
ART_START = "abschnitt"
ART_ENDE = "ende"
#: So nah muss der Anfang eines Sidecar-Abschnitts an einer Notiz mit Marke liegen, damit
#: er als Abschnitt eines Ablaufs gilt (Timer, Übung, km) — sonst ist er ein früher selbst
#: gesetzter ohne Notizpaar (`zusammenfuehren`)
RAST_S = 1.5


def start_text(name: str) -> str:
    """Text der Start-Notiz.

    >>> start_text("Behandlung")
    'Behandlung: Start'
    """
    return f"{name.strip() or 'Abschnitt'}: Start"


def ende_text(name: str) -> str:
    """Text der Ende-Notiz.

    >>> ende_text("Behandlung")
    'Behandlung: Ende'
    """
    return f"{name.strip() or 'Abschnitt'}: Ende"


def start_marke(kennung: str, name: str, kopf_s: float = 0.0, endteil_s: float = 0.0) -> dict:
    """Die Marke der Start-Notiz — Kopf und Endteil nur, wenn gesetzt.

    >>> start_marke("seg-1a2b3c4d", "Behandlung")
    {'quelle': 'person', 'art': 'abschnitt', 'spur': 'seg-1a2b3c4d', 'name': 'Behandlung'}
    >>> start_marke("seg-1a2b3c4d", "Behandlung", -120, 300)["kopf_s"]
    -120
    """
    marke: dict[str, Any] = {"quelle": QUELLE, "art": ART_START, "spur": kennung, "name": name}
    if kopf_s:
        marke["kopf_s"] = kopf_s
    if endteil_s:
        marke["endteil_s"] = endteil_s
    return marke


def ende_marke(kennung: str, name: str) -> dict:
    """Die Marke der Ende-Notiz.

    >>> ende_marke("seg-1a2b3c4d", "Behandlung")["art"]
    'ende'
    """
    return {"quelle": QUELLE, "art": ART_ENDE, "spur": kennung, "name": name}


def _marke(e: Mapping[str, Any]) -> Mapping[str, Any]:
    m = e.get("marke")
    return m if isinstance(m, Mapping) else {}


def ist_grenze(e: Mapping[str, Any]) -> bool:
    """Gehört die Notiz zu einem eigenen Abschnitt (Start oder Ende)?

    >>> ist_grenze({"marke": start_marke("seg-1a2b3c4d", "A")}), ist_grenze({"text": "frei"})
    (True, False)
    >>> ist_grenze({"marke": {"quelle": "timer", "art": "abschnitt", "spur": "timer"}})
    False
    """
    m = _marke(e)
    return m.get("quelle") == QUELLE and str(m.get("spur") or "").startswith(KENNUNG_PRAEFIX)


def kennung_von(e: Mapping[str, Any]) -> str | None:
    """Die Kennung, wenn die Notiz eine Grenze eines eigenen Abschnitts ist."""
    return str(_marke(e).get("spur")) if ist_grenze(e) else None


def offener(ereignisse: Sequence[Mapping[str, Any]]) -> tuple[str, str] | None:
    """``(Kennung, Name)`` des eigenen Abschnitts, der begonnen hat und noch kein Ende hat —
    der zuletzt begonnene; ``None``, wenn keiner läuft.

    >>> s = {"marke": start_marke("seg-1a2b3c4d", "Behandlung")}
    >>> offener([s]), offener([s, {"marke": ende_marke("seg-1a2b3c4d", "Behandlung")}])
    (('seg-1a2b3c4d', 'Behandlung'), None)
    >>> offener([]) is None
    True
    """
    starts: dict[str, str] = {}
    for e in ereignisse:
        k = kennung_von(e)
        if k is None:
            continue
        if _marke(e).get("art") == ART_START:
            starts[k] = str(_marke(e).get("name") or e.get("text") or "Abschnitt")
        elif _marke(e).get("art") == ART_ENDE:
            starts.pop(k, None)
    if not starts:
        return None
    k = next(reversed(starts))
    return k, starts[k]


def grenzen_aus_notizen(
    ereignisse: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[dict, str, bool]]]:
    """Je eigenem Abschnitt eine Spur für `hrv_core.ausschnitte.spuren_speichern`:
    ``(Start-Notiz, Name, False)`` und ``(Ende-Notiz, "", True)``.

    >>> s = {"marke": start_marke("seg-1a2b3c4d", "Behandlung")}
    >>> e = {"marke": ende_marke("seg-1a2b3c4d", "Behandlung")}
    >>> {k: [(n == s or n == e, name, schluss) for n, name, schluss in v]
    ...  for k, v in grenzen_aus_notizen([s, {"text": "frei"}, e]).items()}
    {'seg-1a2b3c4d': [(True, 'Behandlung', False), (True, '', True)]}
    """
    spuren: dict[str, list[tuple[dict, str, bool]]] = {}
    for e in ereignisse:
        k = kennung_von(e)
        if k is None:
            continue
        m = _marke(e)
        if m.get("art") == ART_START and k not in spuren:
            spuren[k] = [(dict(e), str(m.get("name") or e.get("text") or "Abschnitt"), False)]
        elif m.get("art") == ART_ENDE and k in spuren and len(spuren[k]) == 1:
            spuren[k].append((dict(e), "", True))
    return spuren


def zusammenfuehren(
    sidecar: Sequence[Abschnitt], paare: Sequence[Abschnitt], marken_x: Sequence[float]
) -> tuple[list[Abschnitt], list[Abschnitt]]:
    """Die Abschnitte einer Messung aus Sidecar und Notizpaaren — ``(alle, nachzutragen)``.

    Ein Paar (Kennung = ``id``) gilt vor dem Sidecar-Segment (Name, Grenzen, Kopf, Endteil
    aus den Notizen; die Farbe bleibt). Ein Segment ohne Paar, dessen Anfang auf einer
    Notiz mit Marke liegt (``marken_x``), ist ein Abschnitt eines Ablaufs — bleibt. Eines,
    das auf keiner liegt, ist ein früher selbst gesetzter: Es bleibt und steht in
    ``nachzutragen``, damit die Ansicht ihm einmalig sein Paar Notizen gibt
    (`grenznotizen`). Paare ohne Segment (Sidecar veraltet oder verloren) kommen dazu.

    >>> alt = Abschnitt("Alt", 100, 200, id="seg-00000001", farbe="#111111")
    >>> timer = Abschnitt("Belastung", 300, 360, id="seg-00000002")
    >>> paar = Abschnitt("Behandlung", 400, 900, id="seg-00000003", kopf_s=-60)
    >>> sidecar_paar = Abschnitt("Behandlung alt", 410, 890, id="seg-00000003", farbe="#222222")
    >>> neu = Abschnitt("Live", 950, 1000, id="seg-00000004")
    >>> alle, nachtragen = zusammenfuehren([alt, timer, sidecar_paar], [paar, neu], [300.0])
    >>> [(a.id[-1], a.name, a.von_s) for a in alle]
    [('1', 'Alt', 100), ('2', 'Belastung', 300), ('3', 'Behandlung', 400), ('4', 'Live', 950)]
    >>> alle[2].kopf_s  # aus dem Paar, nicht aus dem Sidecar
    -60
    >>> alle[0].farbe, alle[2].farbe  # Farben bleiben die des Sidecars
    ('#111111', '#222222')
    >>> [a.id for a in nachtragen]
    ['seg-00000001']
    """
    nach_id = {p.id: p for p in paare}
    alle: list[Abschnitt] = []
    nachzutragen: list[Abschnitt] = []
    for s in sidecar:
        p = nach_id.pop(s.id, None)
        if p is not None:
            p.farbe = s.farbe
            alle.append(p)
        elif any(abs(s.von_s - x) <= RAST_S for x in marken_x):
            alle.append(s)
        else:
            alle.append(s)
            nachzutragen.append(s)
    alle.extend(nach_id.values())
    alle.sort(key=lambda a: (a.von_s, a.bis_s))
    return alle, nachzutragen


def paare(
    ereignisse: Sequence[Mapping[str, Any]], x_von: Callable[[dict], float | None], ende: float
) -> list[Abschnitt]:
    """Die eigenen Abschnitte aus den Notizen (`hrv_core.ausschnitte.paare_aus_notizen`);
    ``x_von`` wie `Zeitbezug.x`."""
    return paare_aus_notizen(ereignisse, lambda e: x_von(dict(e)), ende)


def grenznotizen(a: Abschnitt, zb: Zeitbezug) -> tuple[dict, dict]:
    """Das Paar Grenz-Notizen zu einem Abschnitt — für einen, der noch keins hat."""
    start = notiz(
        start_text(a.name),
        zb.anker(a.von_s),
        zb.start_utc,
        marke=start_marke(a.id, a.name, a.kopf_s, a.endteil_s),
    )
    ende = notiz(ende_text(a.name), zb.anker(a.bis_s), zb.start_utc, marke=ende_marke(a.id, a.name))
    return start, ende


def notizen_aktualisieren(
    ereignisse: Sequence[Mapping[str, Any]], a: Abschnitt, zb: Zeitbezug
) -> list[dict]:
    """Die Liste mit dem Paar zu ``a`` — bestehende Grenz-Notizen rücken auf seine Grenzen
    und tragen Name, Kopf und Endteil; fehlende entstehen. Ein Text, den die Person selbst
    änderte, bleibt (nur der automatische „Name: Start“ folgt dem Namen).

    >>> from datetime import UTC, datetime
    >>> beats = []
    >>> zb = Zeitbezug(lambda: beats, datetime(2026, 10, 27, 9, 0, tzinfo=UTC), achse=lambda: [])
    >>> a = Abschnitt("Behandlung", 600, 1800, id="seg-1a2b3c4d", kopf_s=-120)
    >>> liste = notizen_aktualisieren([{"text": "frei"}], a, zb)
    >>> [(e.get("text"), e.get("marke", {}).get("art")) for e in liste]
    [('frei', None), ('Behandlung: Start', 'abschnitt'), ('Behandlung: Ende', 'ende')]
    >>> liste[1]["marke"]["kopf_s"]
    -120
    >>> a.name = "Rücken"
    >>> [e["text"] for e in notizen_aktualisieren(liste, a, zb)][1:]
    ['Rücken: Start', 'Rücken: Ende']
    """
    out: list[dict] = []
    start_alt = ende_alt = None
    for e in ereignisse:
        if kennung_von(e) == a.id:
            if _marke(e).get("art") == ART_START and start_alt is None:
                start_alt = dict(e)
            elif _marke(e).get("art") == ART_ENDE and ende_alt is None:
                ende_alt = dict(e)
            continue
        out.append(dict(e))
    alter_name = str(_marke(start_alt or {}).get("name") or "") if start_alt else ""

    def text_fuer(alt: dict | None, neu: str, automatisch: str) -> str:
        if alt is None or not str(alt.get("text") or "").strip():
            return neu
        return neu if alt.get("text") == automatisch else str(alt["text"])

    start = notiz(
        text_fuer(start_alt, start_text(a.name), start_text(alter_name)),
        zb.anker(a.von_s),
        zb.start_utc,
        alt=start_alt,
        marke=start_marke(a.id, a.name, a.kopf_s, a.endteil_s),
    )
    ende = notiz(
        text_fuer(ende_alt, ende_text(a.name), ende_text(alter_name)),
        zb.anker(a.bis_s),
        zb.start_utc,
        alt=ende_alt,
        marke=ende_marke(a.id, a.name),
    )
    out.extend([start, ende])
    return out


def notizen_entfernen(ereignisse: Sequence[Mapping[str, Any]], kennung: str) -> list[dict]:
    """Die Liste ohne das Paar des Abschnitts ``kennung``.

    >>> s = {"marke": start_marke("seg-1a2b3c4d", "A")}
    >>> notizen_entfernen([s, {"text": "frei"}], "seg-1a2b3c4d")
    [{'text': 'frei'}]
    """
    return [dict(e) for e in ereignisse if kennung_von(e) != kennung]


def raender_setzen(
    ereignisse: Sequence[Mapping[str, Any]], a: Abschnitt, x_von: Callable[[dict], float | None]
) -> list[dict] | None:
    """Kopf und Endteil an die Start-Notiz eines Ablauf-Abschnitts (Timer, Übung): die
    Notiz mit Marke, die auf seinem Anfang liegt. ``None``: keine solche Notiz.

    >>> t = {"text": "Belastung", "marke": {"quelle": "timer", "art": "abschnitt", "spur": "timer"}}
    >>> a = Abschnitt("Belastung", 60, 90, kopf_s=30)
    >>> neu = raender_setzen([t, {"text": "frei"}], a, lambda e: 60.0 if "marke" in e else None)
    >>> neu[0]["marke"]["kopf_s"], "endteil_s" in neu[0]["marke"]
    (30, False)
    >>> raender_setzen([{"text": "frei"}], a, lambda e: None) is None
    True
    """
    out: list[dict] = []
    getroffen = False
    for e in ereignisse:
        kopie = dict(e)
        m = _marke(e)
        if not getroffen and m and (x := x_von(kopie)) is not None and abs(x - a.von_s) <= RAST_S:
            marke = {k: v for k, v in m.items() if k not in ("kopf_s", "endteil_s")}
            if a.kopf_s:
                marke["kopf_s"] = a.kopf_s
            if a.endteil_s:
                marke["endteil_s"] = a.endteil_s
            kopie["marke"] = marke
            getroffen = True
        out.append(kopie)
    return out if getroffen else None


__all__ = [
    "ART_ENDE",
    "ART_START",
    "QUELLE",
    "RAST_S",
    "ende_marke",
    "ende_text",
    "grenzen_aus_notizen",
    "grenznotizen",
    "ist_grenze",
    "kennung_von",
    "neue_kennung",
    "notizen_aktualisieren",
    "notizen_entfernen",
    "offener",
    "paare",
    "raender_setzen",
    "start_marke",
    "start_text",
    "zusammenfuehren",
]
