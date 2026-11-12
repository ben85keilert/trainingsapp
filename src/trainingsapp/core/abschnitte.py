"""Eigene Abschnitte einer Messung — sie stehen im **Text** der Notizen (Ben, 12.11.2026).

Ein Abschnitt, den die Person setzt, ist eine **Gruppe** von Notizen mit demselben Namen::

    Radfahren: Start
    Radfahren: Marker (5 km)
    Radfahren: Ende

Start und Ende gehören zusammen; jeder Marker dazwischen teilt die Gruppe — ein Abschnitt
gilt von Grenze zu Grenze („Radfahren (1)“, „Radfahren (5 km)“). Wer einen Marker löscht,
nimmt diese eine Trennung weg. **Kopf** und **Endteil** (`kopf_s`, `endteil_s`: Sekunden
mit Vorzeichen, positiv = außerhalb, negativ = innerhalb) stehen ebenfalls im Text:
„Behandlung: Start (Kopf +5:00 · Endteil −2:00)“.

**Nichts gilt halb:** Ein Start ohne Ende, ein Ende ohne Start, ein Marker außerhalb
ergeben keinen Abschnitt — die Notiz ist **verwaist** (`verwaist`) und steht in der
Notizliste farbig. Einzige Ausnahme: live läuft ein begonnener Abschnitt, bis sein Ende
gesetzt wird (``laufend=True``).

Die **Marke** der Notiz (``person/abschnitt`` · ``person/ende`` mit ``spur`` = Kennung
``seg-…``, zugleich die ``id`` im Sidecar) ist nur noch **abgeleitet**: `marken_aus_text`
bildet sie bei jedem Speichern der Notizliste neu aus dem Text. Sie trägt nichts, was nicht
im Text steht — außer der Kennung, die Farbe und praxis_gui-Kennzahlen über Änderungen
hinweg zusammenhält. Die Abschnitte des Timers bleiben ihre Kette von Grenz-Notizen
(`raender_setzen`). Vertrag: `docs/plan_abschnitte.md`, `docs/kompatibilitaet.md` §4/§9b.

Ohne flet; Zeiten auf der Kurvenachse der App.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hrv_core.ausschnitte import (
    KENNUNG_PRAEFIX,
    MIN_ABSCHNITT_S,
    Abschnitt,
    Grenze,
    aus_grenzen,
    farben_nach_namen,
    grundname,
    neue_kennung,
)
from hrv_core.ereignisse import Zeitbezug, notiz

from trainingsapp.core.zeitangabe import dauer_lesen, dauer_text

QUELLE = "person"
ART_START = "abschnitt"
ART_ENDE = "ende"
#: Nur im Text: die Trennung innerhalb einer Gruppe (in der Marke beginnt auch sie einen
#: Abschnitt, `ART_START`)
ART_MARKER = "marker"
#: So nah muss der Anfang eines Sidecar-Abschnitts an einer Notiz mit Marke liegen, damit
#: er als Abschnitt eines Ablaufs gilt (Timer, Übung, km) — sonst ist er ein früher selbst
#: gesetzter ohne Notizpaar (`zusammenfuehren`)
RAST_S = 1.5

_WORT = {ART_START: "Start", ART_MARKER: "Marker", ART_ENDE: "Ende"}
_ART = {wort.lower(): art for art, wort in _WORT.items()}
#: „‹Name›: Start|Marker|Ende“, dahinter in Klammern der Zusatz — Groß- und
#: Kleinschreibung und Leerzeichen um den Doppelpunkt sind gleich
_GRENZE_TEXT = re.compile(
    r"^(.*\S)\s*:\s*(start|marker|ende)\s*(?:\((.*)\))?\s*$", re.IGNORECASE | re.DOTALL
)
_RAND = re.compile(r"^(kopf|endteil)\s+(\S.*)$", re.IGNORECASE)
_KLAMMER = re.compile(r"^(.*\S)\s*\(([^()]*)\)\s*$", re.DOTALL)


def rand_text(sekunden: float) -> str:
    """Kopf oder Endteil in Kurzform — mit Vorzeichen, „0“ für keinen.

    >>> rand_text(300), rand_text(-120), rand_text(0)
    ('+5:00', '−2:00', '0')
    """
    if not sekunden:
        return "0"
    return ("−" if sekunden < 0 else "+") + dauer_text(abs(sekunden))


def rand_lesen(text: str) -> float | None:
    """Ein getippter Rand: „−2:00“, „-120“, „5:00“, „+300“ — ``None``, wenn unlesbar.

    >>> rand_lesen("−2:00"), rand_lesen("-120"), rand_lesen("5:00"), rand_lesen("+300")
    (-120.0, -120.0, 300.0, 300.0)
    >>> rand_lesen("0"), rand_lesen("abc")
    (0.0, None)
    """
    t = text.strip().lstrip("+").strip()
    if t in ("0", "0:00"):
        return 0.0
    return dauer_lesen(t)  # kennt „−“ und „-“


@dataclass(frozen=True, slots=True)
class Getippt:
    """Was der Text einer Grenz-Notiz sagt: Name der Gruppe, Art (`ART_START`,
    `ART_MARKER`, `ART_ENDE`), Zusatz in Klammern (``label``), Kopf und Endteil."""

    name: str
    art: str
    label: str = ""
    kopf_s: float = 0.0
    endteil_s: float = 0.0


def grenze_im_text(text: str) -> Getippt | None:
    """Die getippte Grenze — ``None``, wenn der Text keine ist.

    >>> grenze_im_text("Behandlung: Start")
    Getippt(name='Behandlung', art='abschnitt', label='', kopf_s=0.0, endteil_s=0.0)
    >>> g = grenze_im_text("radfahren :marker (5 km · Kopf +0:30)"); g.art, g.label, g.kopf_s
    ('marker', '5 km', 30.0)
    >>> g = grenze_im_text("Behandlung: Start (Kopf −2:00, Endteil +5:00)"); g.kopf_s, g.endteil_s
    (-120.0, 300.0)
    >>> grenze_im_text("Start"), grenze_im_text(": Ende"), grenze_im_text("Start: 14 Uhr")
    (None, None, None)
    """
    m = _GRENZE_TEXT.match((text or "").strip())
    if m is None:
        return None
    kopf = endteil = 0.0
    label: list[str] = []
    for teil in re.split(r"[·,;]", m.group(3) or ""):
        teil = teil.strip()
        r = _RAND.match(teil)
        wert = rand_lesen(r.group(2)) if r is not None else None
        if r is not None and wert is not None:
            if r.group(1).lower() == "kopf":
                kopf = wert
            else:
                endteil = wert
        elif teil:
            label.append(teil)
    return Getippt(m.group(1).strip(), _ART[m.group(2).lower()], " · ".join(label), kopf, endteil)


def grenze_text(
    name: str, art: str, label: str = "", kopf_s: float = 0.0, endteil_s: float = 0.0
) -> str:
    """Der Text einer Grenz-Notiz — Umkehrung von `grenze_im_text`.

    >>> grenze_text("Behandlung", ART_START), grenze_text("Radfahren", ART_MARKER, "5 km")
    ('Behandlung: Start', 'Radfahren: Marker (5 km)')
    >>> grenze_text("Behandlung", ART_START, kopf_s=-120, endteil_s=300)
    'Behandlung: Start (Kopf −2:00 · Endteil +5:00)'
    """
    zusatz = [label.strip()] if label.strip() else []
    if kopf_s:
        zusatz.append(f"Kopf {rand_text(kopf_s)}")
    if endteil_s:
        zusatz.append(f"Endteil {rand_text(endteil_s)}")
    text = f"{name.strip() or 'Abschnitt'}: {_WORT[art]}"
    return f"{text} ({' · '.join(zusatz)})" if zusatz else text


def name_teilen(name: str) -> tuple[str, str]:
    """``(Gruppe, Zusatz)`` aus dem Namen eines Abschnitts.

    >>> name_teilen("Radfahren (5 km)"), name_teilen("Behandlung"), name_teilen("  ")
    (('Radfahren', '5 km'), ('Behandlung', ''), ('Abschnitt', ''))
    """
    name = name.strip()
    m = _KLAMMER.match(name)
    if m is not None:
        return m.group(1).strip(), m.group(2).strip()
    return name or "Abschnitt", ""


def start_text(name: str) -> str:
    """Text der Start-Notiz.

    >>> start_text("Behandlung")
    'Behandlung: Start'
    """
    return grenze_text(name, ART_START)


def ende_text(name: str) -> str:
    """Text der Ende-Notiz.

    >>> ende_text("Behandlung")
    'Behandlung: Ende'
    """
    return grenze_text(name, ART_ENDE)


def start_marke(kennung: str, name: str, kopf_s: float = 0.0, endteil_s: float = 0.0) -> dict:
    """Die Marke einer Notiz, die einen Abschnitt beginnt (Start oder Marker) — Kopf und
    Endteil nur, wenn gesetzt.

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
    """Gehört die Notiz zu einem eigenen Abschnitt (Start, Marker oder Ende)?

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


def _frei(e: Mapping[str, Any]) -> bool:
    """Eine Notiz der Person: ohne Marke oder mit der eines eigenen Abschnitts — nur sie
    kann eine getippte Grenze sein (Timer, Übung, Leistung bleiben, was sie sind)."""
    return not e.get("marke") or ist_grenze(e)


def verwaist(e: Mapping[str, Any]) -> bool:
    """Eine getippte Grenze ohne Gegenstück — nach `marken_aus_text` trägt sie keine
    Marke: Start ohne Ende, Ende ohne Start, Marker außerhalb.

    >>> verwaist({"text": "Ruhe: Ende"}), verwaist({"text": "frei"})
    (True, False)
    >>> verwaist({"text": "Ruhe: Ende", "marke": ende_marke("seg-1a2b3c4d", "Ruhe")})
    False
    """
    return not e.get("marke") and grenze_im_text(str(e.get("text") or "")) is not None


@dataclass(slots=True)
class _Gruppe:
    """Start, Marker … und (wenn geschlossen) Ende — als Stellen in der Notizliste."""

    name: str
    teile: list[int]
    ende: int | None = None


def _gruppen(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None] | None,
    laufend: bool,
) -> tuple[list[_Gruppe], dict[int, Getippt]]:
    """Die gültigen Gruppen in der Folge ihres Beginns und die getippten Grenzen je Stelle.
    ``laufend``: eine Gruppe ohne Ende gilt (live) — sonst nur geschlossene."""
    folge = list(range(len(ereignisse)))
    if x_von is not None:
        stellen = [x_von(dict(e)) for e in ereignisse]
        folge.sort(key=lambda i: (stellen[i] is None, stellen[i] or 0.0, i))
    getippt: dict[int, Getippt] = {}
    offen: dict[str, _Gruppe] = {}
    fertig: list[tuple[int, _Gruppe]] = []
    for rang, i in enumerate(folge):
        e = ereignisse[i]
        g = grenze_im_text(str(e.get("text") or "")) if _frei(e) else None
        if g is None:
            continue
        getippt[i] = g
        schluessel = g.name.casefold()
        if g.art == ART_START:
            offen[schluessel] = _Gruppe(g.name, [i])  # ein offener gleichen Namens verwaist
            fertig.append((rang, offen[schluessel]))
        elif schluessel in offen:
            if g.art == ART_MARKER:
                offen[schluessel].teile.append(i)
            else:
                offen.pop(schluessel).ende = i
    gueltig = [
        gr
        for _, gr in sorted(fertig, key=lambda p: p[0])
        if gr.ende is not None or (laufend and offen.get(gr.name.casefold()) is gr)
    ]
    return gueltig, getippt


def _stueck_name(gruppe: _Gruppe, k: int, getippt: Mapping[int, Getippt]) -> str:
    """Der Name des ``k``-ten Abschnitts der Gruppe: „Radfahren“ allein, mit Markern
    „Radfahren (1)“, „Radfahren (5 km)“ — der Zusatz der Notiz, sonst die Nummer."""
    label = getippt[gruppe.teile[k]].label or (str(k + 1) if len(gruppe.teile) > 1 else "")
    return f"{gruppe.name} ({label})" if label else gruppe.name


def _umbenennen(out: list[dict]) -> None:
    """Wer den Namen in der Start-Notiz ändert, benennt die Gruppe um: Die folgenden
    Notizen des alten Namens (Marker, Ende) ziehen mit, bis zu seinem Ende."""
    for i, e in enumerate(out):
        g = grenze_im_text(str(e.get("text") or ""))
        m = _marke(e)
        if g is None or g.art != ART_START or not ist_grenze(e) or m.get("art") != ART_START:
            continue
        alt = name_teilen(str(m.get("name") or ""))[0]
        if not alt or alt.casefold() == g.name.casefold():
            continue
        for f in out[i + 1 :]:
            h = grenze_im_text(str(f.get("text") or "")) if _frei(f) else None
            if h is None or h.name.casefold() != alt.casefold():
                continue
            if h.art == ART_START:
                break
            f["text"] = grenze_text(g.name, h.art, h.label, h.kopf_s, h.endteil_s)
            if h.art == ART_ENDE:
                break


def marken_aus_text(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None] | None = None,
    *,
    laufend: bool = False,
) -> list[dict]:
    """Die Liste, in der die Marken der eigenen Abschnitte dem **Text** folgen.

    - „X: Start“ … „X: Marker“ … „X: Ende“ (gleicher Name, Groß-/Kleinschreibung egal)
      sind eine Gruppe; jede Notiz, die einen Abschnitt beginnt, trägt danach
      ``person/abschnitt`` mit eigener Kennung, die Ende-Notiz ``person/ende``.
    - Was kein Gegenstück hat, **verliert** seine Marke (`verwaist`) — ebenso eine
      Grenz-Notiz, deren Text keine Grenze mehr ist. ``laufend``: live gilt eine Gruppe
      ohne Ende (sie läuft).
    - Eine Start-Notiz, deren Name geändert wurde, benennt ihre Gruppe um.

    Notizen mit einer anderen Marke (Timer, Übung, Leistung) bleiben, wie sie sind. Die
    Reihenfolge der Liste bleibt; ``x_von`` (wie `Zeitbezug.x`) ordnet die Notizen für
    die Zuordnung nach ihrer Stelle — ohne gilt die Reihenfolge der Liste.

    >>> liste = marken_aus_text([{"text": "Rad: Start"}, {"text": "frei"},
    ...     {"text": "rad: marker (5 km)"}, {"text": "Rad: Ende"}, {"text": "Ruhe: Ende"}])
    >>> [e.get("marke", {}).get("art") for e in liste]
    ['abschnitt', None, 'abschnitt', 'ende', None]
    >>> [e["marke"]["name"] for e in liste if "marke" in e]
    ['Rad (1)', 'Rad (5 km)', 'Rad']
    >>> liste[0]["marke"]["spur"] == liste[3]["marke"]["spur"] != liste[2]["marke"]["spur"]
    True
    >>> marken_aus_text(liste) == liste  # nichts mehr zu tun
    True
    >>> [verwaist(e) for e in marken_aus_text(liste[:3])]  # ohne Ende gilt nichts
    [True, False, True]
    >>> ["marke" in e for e in marken_aus_text(liste[:3], laufend=True)]  # live: läuft
    [True, False, True]
    >>> um = marken_aus_text([dict(liste[0], text="Lauf: Start"), *liste[1:]])
    >>> [e["text"] for e in um][2:4], um[0]["marke"]["spur"] == liste[0]["marke"]["spur"]
    (['Lauf: Marker (5 km)', 'Lauf: Ende'], True)
    >>> timer = {"text": "Takt A: Start", "marke": {"quelle": "timer", "art": "takt"}}
    >>> marken_aus_text([timer, {"text": "Takt A: Ende"}])[0] == timer
    True
    >>> spaet = marken_aus_text([{"text": "A: Ende", "x": 90}, {"text": "A: Start", "x": 10}],
    ...                         lambda e: e["x"])
    >>> [e["marke"]["art"] for e in spaet]
    ['ende', 'abschnitt']
    """
    out = [dict(e) for e in ereignisse]
    _umbenennen(out)
    gruppen, getippt = _gruppen(out, x_von, laufend)
    marken: dict[int, dict] = {}
    vergeben: set[str] = set()
    for gruppe in gruppen:
        erste = ""
        for k, i in enumerate(gruppe.teile):
            alt = _marke(out[i])
            kennung = str(alt.get("spur") or "")
            if not ist_grenze(out[i]) or alt.get("art") != ART_START or kennung in vergeben:
                kennung = neue_kennung()
            vergeben.add(kennung)
            erste = erste or kennung
            g = getippt[i]
            marken[i] = start_marke(
                kennung, _stueck_name(gruppe, k, getippt), g.kopf_s, g.endteil_s
            )
        if gruppe.ende is not None:
            marken[gruppe.ende] = ende_marke(erste, gruppe.name)
    for i, e in enumerate(out):
        if i in marken:
            e["marke"] = marken[i]
        elif ist_grenze(e):
            del e["marke"]
    return out


def raender_in_den_text(ereignisse: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Messungen von früher: Kopf und Endteil standen nur in der Marke der Start-Notiz —
    sie kommen in ihren Text, bevor `marken_aus_text` die Marke aus dem Text bildet. Nur
    beim Öffnen einer Datei zu rufen (danach stimmen Text und Marke immer überein).

    >>> alt = {"text": "Behandlung: Start", "marke": start_marke("seg-1a2b3c4d", "B", -120)}
    >>> raender_in_den_text([alt, {"text": "frei"}])[0]["text"]
    'Behandlung: Start (Kopf −2:00)'
    """
    out = [dict(e) for e in ereignisse]
    for e in out:
        m = _marke(e)
        g = grenze_im_text(str(e.get("text") or ""))
        if g is None or not ist_grenze(e) or g.art == ART_ENDE or g.kopf_s or g.endteil_s:
            continue
        kopf, endteil = _zahl(m.get("kopf_s")), _zahl(m.get("endteil_s"))
        if kopf or endteil:
            e["text"] = grenze_text(g.name, g.art, g.label, kopf, endteil)
    return out


def _zahl(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def paare(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None],
    ende: float,
    *,
    laufend: bool = False,
) -> list[Abschnitt]:
    """Die eigenen Abschnitte aus den Notizen: je Gruppe von Grenze zu Grenze; ``x_von``
    wie `Zeitbezug.x`. Die Kennungen kommen aus den Marken (`marken_aus_text` zuerst).
    ``laufend``: eine Gruppe ohne Ende reicht bis ``ende`` (live) und zählt von der ersten
    Sekunde an; ein beendeter Abschnitt braucht `MIN_ABSCHNITT_S`.

    >>> liste = marken_aus_text([{"text": "Rad: Start", "x": 100},
    ...     {"text": "Rad: Marker (5 km · Kopf +0:30)", "x": 400}, {"text": "Rad: Ende", "x": 900},
    ...     {"text": "Ruhe: Start", "x": 950}])
    >>> [(a.name, a.von_s, a.bis_s, a.kopf_s) for a in paare(liste, lambda e: e["x"], 1000)]
    [('Rad (1)', 100, 400, 0.0), ('Rad (5 km)', 400, 900, 30.0)]
    >>> live = marken_aus_text(liste, laufend=True)
    >>> [(a.name, a.bis_s) for a in paare(live, lambda e: e["x"], 955, laufend=True)][-1]
    ('Ruhe', 955)
    """
    gruppen, getippt = _gruppen(ereignisse, x_von, laufend)
    out: list[Abschnitt] = []
    for gruppe in gruppen:
        grenzen: list[Grenze] = []
        for k, i in enumerate(gruppe.teile):
            x = x_von(dict(ereignisse[i]))
            if x is None:
                continue
            g = getippt[i]
            grenzen.append(
                Grenze(
                    x,
                    _stueck_name(gruppe, k, getippt),
                    id=kennung_von(ereignisse[i]),
                    kopf_s=g.kopf_s,
                    endteil_s=g.endteil_s,
                )
            )
        if not grenzen:
            continue
        schluss = x_von(dict(ereignisse[gruppe.ende])) if gruppe.ende is not None else None
        if schluss is not None:
            grenzen.append(Grenze(schluss, "", schluss=True))
        teile = aus_grenzen(grenzen, min(g.x for g in grenzen), max(ende, grenzen[-1].x))
        letzte = max(grenzen, key=lambda g: g.x)
        if schluss is None and gruppe.ende is None and ende - letzte.x < MIN_ABSCHNITT_S:
            # Der laufende steht von der ersten Sekunde an in Chip und Liste
            neu = Abschnitt(
                letzte.name,
                letzte.x,
                max(ende, letzte.x),
                kopf_s=letzte.kopf_s,
                endteil_s=letzte.endteil_s,
            )
            if letzte.id:
                neu.id = letzte.id
            teile.append(neu)
        out.extend(teile)
    out.sort(key=lambda a: (a.von_s, a.bis_s))
    farben_nach_namen(out)
    return out


def offener(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None] | None = None,
) -> tuple[str, str] | None:
    """``(Kennung, Name)`` der Gruppe, die begonnen hat und noch kein Ende hat (live) —
    die zuletzt begonnene; ``None``, wenn keine läuft. Die Kennung ist die der Start-Notiz.

    >>> s = {"text": "Behandlung: Start", "marke": start_marke("seg-1a2b3c4d", "Behandlung")}
    >>> offener([s]), offener([s, {"text": "Behandlung: Ende"}])
    (('seg-1a2b3c4d', 'Behandlung'), None)
    >>> offener([]) is None
    True
    """
    gruppen, _ = _gruppen(ereignisse, x_von, True)
    for gruppe in reversed(gruppen):
        if gruppe.ende is None:
            return kennung_von(ereignisse[gruppe.teile[0]]) or "", gruppe.name
    return None


def laufende_kennung(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None] | None = None,
) -> str | None:
    """Die Kennung des Abschnitts, der gerade läuft (live): der letzte der offenen Gruppe —
    nach einem Marker der Abschnitt ab dem Marker.

    >>> liste = marken_aus_text([{"text": "Rad: Start"}, {"text": "Rad: Marker"}], laufend=True)
    >>> laufende_kennung(liste) == liste[1]["marke"]["spur"], laufende_kennung([]) is None
    (True, True)
    """
    gruppen, _ = _gruppen(ereignisse, x_von, True)
    for gruppe in reversed(gruppen):
        if gruppe.ende is None:
            return kennung_von(ereignisse[gruppe.teile[-1]])
    return None


def kennungen(ereignisse: Sequence[Mapping[str, Any]]) -> list[str]:
    """Die Kennungen aller eigenen Abschnitte, die in den Notizen eine Grenze haben.

    >>> kennungen([{"marke": start_marke("seg-1a2b3c4d", "A")}, {"text": "frei"}])
    ['seg-1a2b3c4d']
    """
    return list(dict.fromkeys(k for e in ereignisse if (k := kennung_von(e)) is not None))


def gruppe_von(
    ereignisse: Sequence[Mapping[str, Any]],
    eintrag: Mapping[str, Any],
    x_von: Callable[[dict], float | None] | None = None,
) -> tuple[str, list[int], bool] | None:
    """``(Name, Stellen aller Notizen der Gruppe, ist Marker?)`` zur Grenz-Notiz
    ``eintrag`` — ``None``, wenn sie zu keiner gültigen Gruppe gehört.

    >>> liste = marken_aus_text([{"text": "Rad: Start"}, {"text": "Rad: Marker"},
    ...                          {"text": "frei"}, {"text": "Rad: Ende"}])
    >>> gruppe_von(liste, liste[1]), gruppe_von(liste, liste[3])
    (('Rad', [0, 1, 3], True), ('Rad', [0, 1, 3], False))
    >>> gruppe_von(liste, liste[2]) is None
    True
    """
    stelle = next((i for i, e in enumerate(ereignisse) if e == eintrag), None)
    if stelle is None:
        return None
    gruppen, getippt = _gruppen(ereignisse, x_von, True)
    for gruppe in gruppen:
        alle = [*gruppe.teile, *([gruppe.ende] if gruppe.ende is not None else [])]
        if stelle in alle:
            return gruppe.name, alle, getippt[stelle].art == ART_MARKER
    return None


def grenzen_aus_notizen(
    ereignisse: Sequence[Mapping[str, Any]],
    x_von: Callable[[dict], float | None] | None = None,
) -> dict[str, list[tuple[dict, str, bool]]]:
    """Je **geschlossener** Gruppe eine Spur für `hrv_core.ausschnitte.spuren_speichern`:
    ``(Notiz, Name, False)`` je Start und Marker, ``(Ende-Notiz, "", True)``.

    >>> liste = marken_aus_text([{"text": "Rad: Start"}, {"text": "Rad: Marker"},
    ...                          {"text": "frei"}, {"text": "Rad: Ende"}, {"text": "X: Start"}])
    >>> (spur,) = grenzen_aus_notizen(liste).values()
    >>> [(n["text"], name, schluss) for n, name, schluss in spur]
    [('Rad: Start', 'Rad (1)', False), ('Rad: Marker', 'Rad (2)', False), ('Rad: Ende', '', True)]
    """
    gruppen, getippt = _gruppen(ereignisse, x_von, False)
    spuren: dict[str, list[tuple[dict, str, bool]]] = {}
    for gruppe in gruppen:
        if gruppe.ende is None:
            continue
        schluessel = kennung_von(ereignisse[gruppe.teile[0]]) or neue_kennung()
        spuren[schluessel] = [
            (dict(ereignisse[i]), _stueck_name(gruppe, k, getippt), False)
            for k, i in enumerate(gruppe.teile)
        ] + [(dict(ereignisse[gruppe.ende]), "", True)]
    return spuren


def zusammenfuehren(
    sidecar: Sequence[Abschnitt], paare: Sequence[Abschnitt], marken_x: Sequence[float]
) -> tuple[list[Abschnitt], list[Abschnitt]]:
    """Die Abschnitte einer Messung aus Sidecar und Notizen — ``(alle, nachzutragen)``.

    Ein Abschnitt aus den Notizen (Kennung = ``id``) gilt vor dem Sidecar-Segment (Name,
    Grenzen, Kopf, Endteil aus den Notizen; die Farbe bleibt). Ein Segment ohne Notizen,
    dessen Anfang auf einer Notiz liegt (``marken_x``), ist ein Abschnitt eines Ablaufs —
    bleibt. Eines, das auf keiner liegt, ist ein früher selbst gesetzter: Es bleibt und
    steht in ``nachzutragen``, damit die Ansicht ihm einmalig seine Notizen gibt
    (`grenznotizen`). Abschnitte ohne Segment (Sidecar veraltet oder verloren) kommen dazu.

    >>> alt = Abschnitt("Alt", 100, 200, id="seg-00000001", farbe="#111111")
    >>> timer = Abschnitt("Belastung", 300, 360, id="seg-00000002")
    >>> paar = Abschnitt("Behandlung", 400, 900, id="seg-00000003", kopf_s=-60)
    >>> sidecar_paar = Abschnitt("Behandlung alt", 410, 890, id="seg-00000003", farbe="#222222")
    >>> neu = Abschnitt("Live", 950, 1000, id="seg-00000004")
    >>> alle, nachtragen = zusammenfuehren([alt, timer, sidecar_paar], [paar, neu], [300.0])
    >>> [(a.id[-1], a.name, a.von_s) for a in alle]
    [('1', 'Alt', 100), ('2', 'Belastung', 300), ('3', 'Behandlung', 400), ('4', 'Live', 950)]
    >>> alle[2].kopf_s  # aus den Notizen, nicht aus dem Sidecar
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


def abgleichen(
    abschnitte: Sequence[Abschnitt], paare: Sequence[Abschnitt], vorher: Sequence[str]
) -> list[Abschnitt]:
    """Die Abschnitte einer offenen Ansicht nach einer Notizänderung (Ben, 12.11.2026).

    Ein Abschnitt, den die Notizen ergeben (``paare``, Kennung = ``id``), nimmt Name,
    Grenzen, Kopf und Endteil aus ihnen — **am selben Objekt** (ein offener Editor hält
    es), die Farbe bleibt. Einer, den es ``vorher`` in den Notizen gab (Kennungen der
    Grenz-Notizen vor der Änderung) und jetzt nicht mehr, fällt weg; die übrigen (Timer,
    Übung) bleiben. Neue kommen dazu.

    >>> timer = Abschnitt("Belastung", 300, 360, id="seg-00000002")
    >>> alt = Abschnitt("Behandlung", 400, 900, id="seg-00000003", farbe="#222222")
    >>> weg = Abschnitt("Weg", 10, 90, id="seg-00000005")
    >>> paar = Abschnitt("Rücken", 420, 900, id="seg-00000003", kopf_s=-60)
    >>> neu = Abschnitt("Getippt", 950, 1000, id="seg-00000004")
    >>> alle = abgleichen([timer, alt, weg], [paar, neu], ["seg-00000003", "seg-00000005"])
    >>> [(a.id[-1], a.name, a.von_s, a.farbe == "#222222") for a in alle]
    [('2', 'Belastung', 300, False), ('3', 'Rücken', 420, True), ('4', 'Getippt', 950, False)]
    >>> alle[1] is alt, alt.kopf_s
    (True, -60)
    """
    nach_id = {p.id: p for p in paare}
    hatte_paar = set(vorher)
    out: list[Abschnitt] = []
    for a in abschnitte:
        p = nach_id.pop(a.id, None)
        if p is not None:
            a.name, a.von_s, a.bis_s = p.name, p.von_s, p.bis_s
            a.kopf_s, a.endteil_s = p.kopf_s, p.endteil_s
            out.append(a)
        elif a.id not in hatte_paar:
            out.append(a)
    out.extend(nach_id.values())
    out.sort(key=lambda a: (a.von_s, a.bis_s))
    return out


def grenznotizen(a: Abschnitt, zb: Zeitbezug) -> tuple[dict, dict]:
    """Start- und Ende-Notiz zu einem Abschnitt — für einen, der noch keine hat."""
    name, label = name_teilen(a.name)
    start = notiz(
        grenze_text(name, ART_START, label, a.kopf_s, a.endteil_s),
        zb.anker(a.von_s),
        zb.start_utc,
        marke=start_marke(a.id, a.name, a.kopf_s, a.endteil_s),
    )
    ende = notiz(ende_text(name), zb.anker(a.bis_s), zb.start_utc, marke=ende_marke(a.id, name))
    return start, ende


def _stueck(
    ereignisse: Sequence[Mapping[str, Any]],
    kennung: str,
    x_von: Callable[[dict], float | None] | None,
) -> tuple[_Gruppe, int, dict[int, Getippt]] | None:
    """Gruppe und Nummer des Abschnitts mit dieser Kennung."""
    gruppen, getippt = _gruppen(ereignisse, x_von, True)
    for gruppe in gruppen:
        for k, i in enumerate(gruppe.teile):
            if kennung_von(ereignisse[i]) == kennung:
                return gruppe, k, getippt
    return None


def notizen_aktualisieren(
    ereignisse: Sequence[Mapping[str, Any]], a: Abschnitt, zb: Zeitbezug, *, laeuft: bool = False
) -> list[dict]:
    """Die Liste, in der die Notizen den Abschnitt ``a`` beschreiben (Editor, Blatt).

    Gibt es ihn schon (eine Notiz mit seiner Kennung beginnt ihn), rückt sie auf seinen
    Anfang und die nächste Grenze der Gruppe (Marker oder Ende) auf sein Ende; Zusatz, Kopf
    und Endteil stehen danach in ihrem Text, ein neuer Name benennt die ganze Gruppe um.
    Sonst entsteht eine neue Gruppe aus Start- und Ende-Notiz. ``laeuft``: live ohne Ende —
    nur der Anfang.

    >>> from datetime import UTC, datetime
    >>> beats = []
    >>> zb = Zeitbezug(lambda: beats, datetime(2026, 10, 27, 9, 0, tzinfo=UTC), achse=lambda: [])
    >>> a = Abschnitt("Behandlung", 600, 1800, id="seg-1a2b3c4d", kopf_s=-120)
    >>> liste = notizen_aktualisieren([{"text": "frei"}], a, zb)
    >>> [(e.get("text"), e.get("marke", {}).get("art")) for e in liste]
    [('frei', None), ('Behandlung: Start (Kopf −2:00)', 'abschnitt'), ('Behandlung: Ende', 'ende')]
    >>> a.name, a.kopf_s = "Rücken (links)", 0
    >>> [e["text"] for e in notizen_aktualisieren(liste, a, zb)][1:]
    ['Rücken: Start (links)', 'Rücken: Ende']
    >>> [e["text"] for e in notizen_aktualisieren([], a, zb, laeuft=True)]
    ['Rücken: Start (links)']
    """
    out = [dict(e) for e in ereignisse]
    name, label = name_teilen(a.name)
    fund = _stueck(out, a.id, zb.x)
    if fund is None:
        out.append(
            notiz(
                grenze_text(name, ART_START, label, a.kopf_s, a.endteil_s),
                zb.anker(a.von_s),
                zb.start_utc,
                marke=start_marke(a.id, a.name, a.kopf_s, a.endteil_s),
            )
        )
        if not laeuft:
            out.append(
                notiz(
                    ende_text(name), zb.anker(a.bis_s), zb.start_utc, marke=ende_marke(a.id, name)
                )
            )
        return out
    gruppe, k, getippt = fund
    alle = [*gruppe.teile, *([gruppe.ende] if gruppe.ende is not None else [])]
    if label == str(k + 1) and not getippt[gruppe.teile[k]].label:
        label = ""  # die Nummer ist nur die Anzeige, kein Zusatz
    for i in alle:
        g = getippt[i]
        text = grenze_text(name, g.art, g.label, g.kopf_s, g.endteil_s)
        anker = None
        if i == gruppe.teile[k]:
            text = grenze_text(name, g.art, label, a.kopf_s, a.endteil_s)
            anker = zb.anker(a.von_s)
        elif not laeuft and alle.index(i) == k + 1:
            anker = zb.anker(a.bis_s)
        if anker is not None:
            out[i] = notiz(text, anker, zb.start_utc, alt=out[i])
        else:
            out[i]["text"] = text
    return out


def notizen_entfernen(
    ereignisse: Sequence[Mapping[str, Any]],
    kennung: str,
    x_von: Callable[[dict], float | None] | None = None,
) -> list[dict]:
    """Die Liste ohne den Abschnitt ``kennung`` — nie bleibt eine halbe Gruppe zurück:

    - der einzige Abschnitt seiner Gruppe: Start und Ende gehen;
    - der erste von mehreren: die Start-Notiz geht, der erste Marker wird der Start;
    - der letzte: die Ende-Notiz geht, der letzte Marker wird das Ende;
    - einer in der Mitte: sein Marker geht — er fällt mit dem davor zusammen.

    >>> liste = marken_aus_text([{"text": "Rad: Start"}, {"text": "Rad: Marker (5 km)"},
    ...     {"text": "Rad: Marker"}, {"text": "frei"}, {"text": "Rad: Ende"}])
    >>> k = [e["marke"]["spur"] for e in liste if "marke" in e]
    >>> [e["text"] for e in notizen_entfernen(liste, k[0])]
    ['Rad: Start (5 km)', 'Rad: Marker', 'frei', 'Rad: Ende']
    >>> [e["text"] for e in notizen_entfernen(liste, k[1])]
    ['Rad: Start', 'Rad: Marker', 'frei', 'Rad: Ende']
    >>> [e["text"] for e in notizen_entfernen(liste, k[2])]
    ['Rad: Start', 'Rad: Marker (5 km)', 'Rad: Ende', 'frei']
    >>> einer = marken_aus_text([{"text": "A: Start"}, {"text": "frei"}, {"text": "A: Ende"}])
    >>> notizen_entfernen(einer, einer[0]["marke"]["spur"])
    [{'text': 'frei'}]
    """
    out = [dict(e) for e in ereignisse]
    fund = _stueck(out, kennung, x_von)
    if fund is None:  # keine gültige Gruppe: was die Kennung trägt, geht
        return [e for e in out if kennung_von(e) != kennung]
    gruppe, k, getippt = fund
    n = len(gruppe.teile)
    weg: set[int] = set()

    def wird(i: int, art: str) -> None:
        g = getippt[i]
        label = g.label if art == ART_START else ""
        out[i]["text"] = grenze_text(gruppe.name, art, label, g.kopf_s, g.endteil_s)

    if n == 1:
        weg = {gruppe.teile[0], *([gruppe.ende] if gruppe.ende is not None else [])}
    elif k == 0:
        weg = {gruppe.teile[0]}
        wird(gruppe.teile[1], ART_START)
    elif k == n - 1 and gruppe.ende is not None:
        weg = {gruppe.ende}
        wird(gruppe.teile[k], ART_ENDE)
    else:
        weg = {gruppe.teile[k]}
    return [e for i, e in enumerate(out) if i not in weg]


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
    "ART_MARKER",
    "ART_START",
    "QUELLE",
    "RAST_S",
    "Getippt",
    "abgleichen",
    "ende_marke",
    "ende_text",
    "grenze_im_text",
    "grenze_text",
    "grenzen_aus_notizen",
    "grenznotizen",
    "grundname",
    "gruppe_von",
    "ist_grenze",
    "kennung_von",
    "kennungen",
    "laufende_kennung",
    "marken_aus_text",
    "name_teilen",
    "neue_kennung",
    "notizen_aktualisieren",
    "notizen_entfernen",
    "offener",
    "paare",
    "raender_in_den_text",
    "raender_setzen",
    "rand_lesen",
    "rand_text",
    "start_marke",
    "start_text",
    "verwaist",
    "zusammenfuehren",
]
