"""Was das Zählen mit dem Beschleunigungssensor ins Tagebuch gibt — aus der Zeitleiste.

Ben, 4.11.2026 (``docs/plan_beschleunigung.md`` §4.3, §5.3): Der Satzwert (Sensor plus Korrektur)
geht als Wiederholungen des Satzes in den offenen Eintrag (`SessionRepo.lauf_eintragen`, ein
Wert je Satz, angehängt wie die Haltezeit; ohne Sätze zählt die Summe). Wie
`core.timer_eintrag` für die Zeit der Uhr liest dieses Modul nur die Zeitleiste der Einheit
(`core.einheit`, Vertrag ``docs/plan_einheit.md`` §4):

- `zaehlungen`, `wiederholungen` — je Satz ``zaehlen/zaehlung`` (``wert`` = max(0, Sensor +
  Korrektur));
- `zaehl_ende`, `zaehl_abgebrochen` — ``zaehlen/zaehlen_ende``: eingetragen wird bei
  ``fertig`` und ``abgehakt``, die übrigen Gründe sind **abgebrochen** (der Lauf bleibt unter
  „Läufe heute“ und lässt sich dort eintragen);
- `zeiten_der_uhr`, `uhr_bis` — die Zeit der Uhr passend zu den Wiederholungen, auch nach
  einem Absturz mitten in einem zählenden Abschnitt (bis zum letzten Zwischenstand);
- `eingetragen` — welche Teile ``person/eintrag`` schon eingetragen hat (``teil`` = ``uhr``
  oder ``zaehlen``; ein altes ``person/eintrag`` ohne ``teil`` gilt für die Uhr): so wird nichts
  doppelt eingetragen, wenn Uhr und Zählen eine Einheit teilen;
- `zaehl_text`, `zaehl_texte`, `ende_text` — „Satz 1 · 12 Wdh. (Sensor 11, +1)“;
- `nicht_eingetragen_text` — die Meldung, wenn eine andere Übung startet und das Zählen
  abbricht: „Kniebeuge · 12 Wdh. nicht eingetragen“; endete es von selbst, mit dem Grund
  (`von_selbst_text`): „… nicht eingetragen — 60 s ohne Bewegung“.

Rein und ohne flet.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any, Final

from .einheit import Ereignis, ganzzahl_lesen
from .timer_eintrag import Gelaufen, gelaufene_zeiten
from .zaehlen import (
    EINGETRAGEN,
    ENDE_ABBRUCH,
    ENDE_ABGEHAKT,
    ENDE_ANDERE_UEBUNG,
    ENDE_FERTIG,
    ENDE_KEIN_ATEM,
    ENDE_KEINE_BEWEGUNG,
    KEIN_ATEM_S,
    KEINE_BEWEGUNG_S,
    ZAEHLART_WDH,
    mit_vorzeichen,
)

#: Welcher Teil eingetragen ist (``teil`` an ``person/eintrag``)
TEIL_UHR: Final = "uhr"
TEIL_ZAEHLEN: Final = "zaehlen"

#: Wie ein Ende in der Zeitleiste heißt („Kniebeuge: Zählen fertig“)
_ENDE_TEXT: Final[dict[str, str]] = {
    ENDE_FERTIG: "fertig",
    ENDE_ABGEHAKT: "abgehakt",
    ENDE_ABBRUCH: "abgebrochen",
    ENDE_ANDERE_UEBUNG: "abgebrochen (andere Übung)",
    ENDE_KEINE_BEWEGUNG: "abgebrochen (keine Bewegung)",
    ENDE_KEIN_ATEM: "abgebrochen (kein Atemzug)",
}


def ende_text(grund: str | None) -> str:
    """Das Ende in Worten.

    >>> ende_text("fertig"), ende_text("keine_bewegung"), ende_text(None)
    ('fertig', 'abgebrochen (keine Bewegung)', 'beendet')
    """
    return _ENDE_TEXT.get(grund or "", "beendet")


def zaehlungen(ereignisse: Iterable[Ereignis]) -> list[dict[str, Any]]:
    """Die Sätze des Zählens (``zaehlen/zaehlung``) nach ihrer Nummer — steht ein Satz zweimal
    da, gilt der letzte.

    >>> ev = [Ereignis(40.0, "zaehlen", "zaehlung", "", {"satz": 2, "wert": 10}),
    ...       Ereignis(20.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 12})]
    >>> [z["satz"] for z in zaehlungen(ev)]
    [1, 2]
    """
    je_satz: dict[int, dict[str, Any]] = {}
    for e in ereignisse:
        if e.quelle == "zaehlen" and e.art == "zaehlung":
            je_satz[ganzzahl_lesen(e.daten.get("satz"), len(je_satz) + 1)] = dict(e.daten)
    return [je_satz[k] for k in sorted(je_satz)]


def wiederholungen(ereignisse: Iterable[Ereignis], feld: str | None = None) -> list[int]:
    """Die Wiederholungen je Satz (``wert``: Sensor plus Korrektur) — ohne Sätze, in denen
    nichts gezählt wurde, und ohne die, die die Person von Hand eintrug (``von_hand``,
    Diagnosemodus); mit ``feld`` nur die für dieses Feld.

    >>> ev = [Ereignis(20.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 12, "feld": "reps"}),
    ...       Ereignis(50.0, "zaehlen", "zaehlung", "", {"satz": 2, "wert": 0}),
    ...       Ereignis(80.0, "zaehlen", "zaehlung", "", {"satz": 3, "wert": 11, "feld": "reps"}),
    ...       Ereignis(99.0, "zaehlen", "zaehlung", "", {"satz": 4, "wert": 9, "von_hand": True})]
    >>> wiederholungen(ev), wiederholungen(ev, "reps_2")
    ([12, 11], [])
    """
    out: list[int] = []
    for z in zaehlungen(ereignisse):
        if z.get("zaehlart", ZAEHLART_WDH) != ZAEHLART_WDH or z.get("von_hand"):
            continue
        if feld is not None and z.get("feld") not in (None, feld):
            continue
        wert = max(0, ganzzahl_lesen(z.get("wert")))
        if wert:
            out.append(wert)
    return out


def satz_zeiten(ereignisse: Iterable[Ereignis], feld: str | None = None) -> list[float]:
    """Wann die Sätze von `wiederholungen` endeten (``t_s`` ihrer ``zaehlung``, Achse der
    Einheit) — in derselben Folge, je Satz eine Zeit: Dort steht beim Eintragen die Notiz zum
    Satz in der Aufnahme (Plan §5.3, `ui.uebung_lauf`).

    >>> ev = [Ereignis(20.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 12, "feld": "reps"}),
    ...       Ereignis(50.0, "zaehlen", "zaehlung", "", {"satz": 2, "wert": 0}),
    ...       Ereignis(80.0, "zaehlen", "zaehlung", "", {"satz": 3, "wert": 11, "feld": "reps"})]
    >>> satz_zeiten(ev), satz_zeiten(ev, "reps_2")
    ([20.0, 80.0], [])
    """
    je_satz: dict[int, tuple[float, dict[str, Any]]] = {}
    for e in ereignisse:
        if e.quelle == "zaehlen" and e.art == "zaehlung":
            je_satz[ganzzahl_lesen(e.daten.get("satz"), len(je_satz) + 1)] = (e.t_s, e.daten)
    out: list[float] = []
    for k in sorted(je_satz):
        t_s, z = je_satz[k]
        if z.get("zaehlart", ZAEHLART_WDH) != ZAEHLART_WDH or z.get("von_hand"):
            continue
        if feld is not None and z.get("feld") not in (None, feld):
            continue
        if max(0, ganzzahl_lesen(z.get("wert"))):
            out.append(float(t_s))
    return out


def uhr_bis(ereignisse: Iterable[Ereignis]) -> float | None:
    """Starb die App mitten in einem zählenden Abschnitt der Uhr (kein ``timer/ende``), und
    steht dessen Satz schon als Zwischenstand da (``zaehlung`` nach dem Beginn des Abschnitts):
    die Stelle des letzten — bis dorthin zählt der Abschnitt. So passen Zeit und Wiederholungen
    zusammen, ein Stand für beide (sonst hätte der Satz Wiederholungen, aber keine Haltezeit).
    ``None``: Die Uhr endete, lief nicht, steht in einem Abschnitt, der nicht zählt, oder der
    offene Abschnitt hat noch keinen Zwischenstand (dann fehlt er in beiden). Endete das
    Zählen in diesem Abschnitt (``zaehlen_ende``: abgebrochen, keine Bewegung, getrennt) und
    die Uhr lief weiter, ist seine letzte ``zaehlung`` nur das Ende des Zählens, nicht das der
    Uhr — dann auch ``None``: lieber eine Lücke als eine zu kurze Zeit.

    >>> ab = lambda t, **d: Ereignis(t, "timer", "abschnitt", "", {"name": "Halten", **d})
    >>> satz = lambda t, n: Ereignis(t, "zaehlen", "zaehlung", "", {"satz": n, "wert": 9})
    >>> uhr_bis([ab(0.0), satz(30.0, 1), ab(30.0, zaehlt=False), ab(40.0), satz(55.0, 2)])
    55.0
    >>> uhr_bis([ab(0.0), satz(30.0, 1), ab(30.0, zaehlt=False)]) is None  # in der Pause
    True
    >>> uhr_bis([ab(0.0), satz(15.0, 1), Ereignis(20.0, "timer", "ende", "")]) is None
    True
    >>> abbruch = Ereignis(21.0, "zaehlen", "zaehlen_ende", "", {"grund": "abbruch"})
    >>> uhr_bis([ab(0.0), satz(15.0, 1), satz(21.0, 1), abbruch]) is None  # die Uhr lief weiter
    True
    """
    beginn: float | None = None
    bis: float | None = None
    for e in ereignisse:
        if e.quelle == "timer" and e.art == "ende":
            return None
        if e.quelle == "timer" and e.art == "abschnitt":
            beginn = e.t_s if e.daten.get("zaehlt") is not False else None
            bis = None
        elif beginn is not None and e.quelle == "zaehlen" and e.art == "zaehlung":
            if e.t_s > beginn:  # die ``zaehlung`` des Satzes davor steht an der Grenze
                bis = e.t_s if bis is None else max(bis, e.t_s)
        elif e.quelle == "zaehlen" and e.art == "zaehlen_ende":
            bis = None  # das Ende des Zählens — die Uhr lief weiter, wie lange, weiß niemand
    return bis


def zeiten_der_uhr(ereignisse: Iterable[Ereignis]) -> list[Gelaufen]:
    """Die gelaufenen Zeiten der Uhr (`core.timer_eintrag.gelaufene_zeiten`) — nach einem
    Absturz mitten in einem zählenden Abschnitt mit ihm bis zum letzten Zwischenstand
    (`uhr_bis`), passend zu dessen Wiederholungen. Nur, wenn beide zusammen eingetragen werden
    (sonst ist es nur eine untere Grenze der Zeit: dann fehlt der Abschnitt, wie ohne Zählen).

    >>> ab = lambda t, **d: Ereignis(t, "timer", "abschnitt", "", {"name": "Halten", **d})
    >>> satz = lambda t, n: Ereignis(t, "zaehlen", "zaehlung", "", {"satz": n, "wert": 9})
    >>> ev = [ab(0.0), satz(30.0, 1), ab(30.0, zaehlt=False), ab(40.0), satz(55.0, 2)]
    >>> [(z.name, z.sekunden, z.laeuft) for z in zeiten_der_uhr(ev) if z.zaehlt]
    [('Halten', 30.0, False), ('Halten', 15.0, False)]
    """
    ereignisse = list(ereignisse)
    bis = uhr_bis(ereignisse)
    if bis is None:
        return gelaufene_zeiten(ereignisse)
    bis_dahin = [e for e in ereignisse if e.t_s <= bis]
    # Er läuft nicht mehr — er endete mit der App, dort steht sein letzter Stand
    return [replace(z, laeuft=False) for z in gelaufene_zeiten(bis_dahin, jetzt_s=bis)]


def zaehl_ende(ereignisse: Iterable[Ereignis]) -> str | None:
    """Der Grund, mit dem das Zählen endete — ``None``: es endete nicht (läuft, oder die App
    starb mitten im Lauf).

    >>> zaehl_ende([Ereignis(9.0, "zaehlen", "zaehlen_ende", "", {"grund": "abbruch"})])
    'abbruch'
    >>> zaehl_ende([]) is None
    True
    """
    grund: str | None = None
    for e in ereignisse:
        if e.quelle == "zaehlen" and e.art == "zaehlen_ende":
            grund = str(e.daten.get("grund") or "") or None
    return grund


def zaehl_abgebrochen(ereignisse: Iterable[Ereignis]) -> bool:
    """Ob das Zählen abgebrochen endete — dann wird nichts eingetragen, der Lauf bleibt unter
    „Läufe heute“.

    >>> ende = lambda g: [Ereignis(9.0, "zaehlen", "zaehlen_ende", "", {"grund": g})]
    >>> [zaehl_abgebrochen(ende(g)) for g in ("fertig", "abgehakt", "abbruch", "keine_bewegung")]
    [False, False, True, True]
    >>> zaehl_abgebrochen([])
    False
    """
    grund = zaehl_ende(ereignisse)
    return grund is not None and grund not in EINGETRAGEN


def eingetragen(ereignisse: Iterable[Ereignis]) -> frozenset[str]:
    """Welche Teile schon eingetragen sind (``person/eintrag`` mit ``teil``) — ein Eintrag ohne
    ``teil`` (vor dem Zählen) gilt für die Uhr.

    >>> eingetragen([Ereignis(9.0, "person", "eintrag", "", {"eintrag": "e1"})])
    frozenset({'uhr'})
    >>> sorted(eingetragen([Ereignis(9.0, "person", "eintrag", "", {"teil": "zaehlen"}),
    ...                     Ereignis(9.5, "person", "eintrag", "", {"teil": "uhr"})]))
    ['uhr', 'zaehlen']
    """
    teile: set[str] = set()
    for e in ereignisse:
        if e.quelle == "person" and e.art == "eintrag":
            teile.add(str(e.daten.get("teil") or TEIL_UHR))
    return frozenset(teile)


def zaehl_text(z: Mapping[str, Any]) -> str:
    """Ein Satz für „Läufe heute“: der Wert, dahinter, was der Sensor zählte und wie
    korrigiert wurde.

    >>> zaehl_text({"satz": 1, "wert": 12, "sensor": 11, "korrektur": 1})
    'Satz 1 · 12 Wdh. (Sensor 11, +1)'
    >>> zaehl_text({"satz": 2, "wert": 10, "sensor": 10, "korrektur": 0})
    'Satz 2 · 10 Wdh. (Sensor)'
    >>> zaehl_text({"satz": 1, "wert": 2, "sensor": None, "korrektur": 2})
    'Satz 1 · 2 Wdh. (Sensor –, +2)'
    """
    satz = ganzzahl_lesen(z.get("satz"), 1)
    wert = max(0, ganzzahl_lesen(z.get("wert")))
    sensor = z.get("sensor")
    korrektur = ganzzahl_lesen(z.get("korrektur"))
    if not korrektur:
        return f"Satz {satz} · {wert} Wdh. (Sensor)"
    gezaehlt = "–" if sensor is None else str(ganzzahl_lesen(sensor))
    return f"Satz {satz} · {wert} Wdh. (Sensor {gezaehlt}, {mit_vorzeichen(korrektur)})"


def zaehl_texte(ereignisse: Iterable[Ereignis]) -> list[str]:
    """Je gezähltem Satz eine Zeile (`zaehl_text`) — nicht für einen Satz, in dem nichts
    gezählt wurde (er kommt auch nicht ins Tagebuch, `wiederholungen`), und nicht für einen,
    den die Person von Hand eintrug.

    >>> zaehl_texte([Ereignis(20.0, "zaehlen", "zaehlung", "",
    ...              {"satz": 1, "wert": 12, "sensor": 11, "korrektur": 1}),
    ...              Ereignis(40.0, "zaehlen", "zaehlung", "", {"satz": 2, "wert": 0})])
    ['Satz 1 · 12 Wdh. (Sensor 11, +1)']
    """
    return [
        zaehl_text(z)
        for z in zaehlungen(ereignisse)
        if z.get("zaehlart", ZAEHLART_WDH) == ZAEHLART_WDH
        and not z.get("von_hand")
        and max(0, ganzzahl_lesen(z.get("wert")))
    ]


def nicht_eingetragen_text(name: str, wdh: int, warum: str = "") -> str:
    """Die Meldung (5 s, mit „Eintragen“), wenn eine andere Übung startet und das Zählen
    dieser abbricht (``andere_uebung``, §4.3 Punkt 6) — oder wenn es von selbst endete, dann
    mit dem Grund (`von_selbst_text`).

    >>> nicht_eingetragen_text("Kniebeuge", 12)
    'Kniebeuge · 12 Wdh. nicht eingetragen'
    >>> nicht_eingetragen_text("Kniebeuge", 12, "60 s ohne Bewegung")
    'Kniebeuge · 12 Wdh. nicht eingetragen — 60 s ohne Bewegung'
    """
    text = f"{name} · {max(0, int(wdh))} Wdh. nicht eingetragen"
    return f"{text} — {warum}" if warum else text


def von_selbst_text(
    grund: str | None, *, getrennt: bool = False, ohne_daten: bool = False, zu_lang: bool = False
) -> str:
    """Warum das Zählen von selbst endete und abgebrochen bleibt — für die Meldung „… nicht
    eingetragen“: `KEINE_BEWEGUNG_S` ohne neue Wiederholung, `KEIN_ATEM_S` ohne Atemzug, das
    Gerät ist getrennt (``abbruch`` mit ``getrennt``, auch ein Funkabriss) oder es kam
    `KEINE_DATEN_S` lang keine Beschleunigung (``abbruch`` mit ``ohne_daten``), oder der Satz
    lief länger, als der Puffer der Beschleunigung hält (``abbruch`` mit ``zu_lang``). Leer,
    wenn es nicht von selbst endete (ein Tipp, die Uhr brach ab) oder eingetragen wird.

    >>> von_selbst_text("keine_bewegung"), von_selbst_text("kein_atem")
    ('60 s ohne Bewegung', '2 min kein Atemzug erkannt')
    >>> von_selbst_text("abbruch", getrennt=True), von_selbst_text("abbruch")
    ('Sensor getrennt', '')
    >>> von_selbst_text("abbruch", ohne_daten=True), von_selbst_text("abbruch", zu_lang=True)
    ('keine Daten vom Sensor', 'Satz zu lang für den Sensor')
    >>> von_selbst_text("fertig", getrennt=True), von_selbst_text(None)
    ('', '')
    """
    if grund == ENDE_KEINE_BEWEGUNG:
        return f"{KEINE_BEWEGUNG_S:.0f} s ohne Bewegung"
    if grund == ENDE_KEIN_ATEM:
        return f"{KEIN_ATEM_S / 60:.0f} min kein Atemzug erkannt"
    if grund == ENDE_ABBRUCH and getrennt:
        return "Sensor getrennt"
    if grund == ENDE_ABBRUCH and ohne_daten:
        return "keine Daten vom Sensor"
    if grund == ENDE_ABBRUCH and zu_lang:
        return "Satz zu lang für den Sensor"
    return ""


__all__ = [
    "TEIL_UHR",
    "TEIL_ZAEHLEN",
    "eingetragen",
    "ende_text",
    "nicht_eingetragen_text",
    "satz_zeiten",
    "uhr_bis",
    "von_selbst_text",
    "wiederholungen",
    "zaehl_abgebrochen",
    "zaehl_ende",
    "zaehl_text",
    "zaehl_texte",
    "zaehlungen",
    "zeiten_der_uhr",
]
