"""Der **Testlauf** eines Kurses — ein Test mit Vorgabe (Ben, 16.11.2026,
`docs/plan_kurs_ablauf.md` §3.3 und §13).

Ein Test mit `core.kursbloecke.Vorgabe` ist ein Lauf der Übung mit der Uhr: **Eine Größe steht
fest und beendet den Lauf, die anderen werden gemessen.**

| Vorgabe | der Lauf endet, wenn … | gemessen |
|---|---|---|
| Menge | die Wiederholungen gemacht sind | Zeit, Anstrengung |
| Zeit | die Zeit ab ist | Wiederholungen, Anstrengung |
| Skala ab n · höchstens m · n bis m | die Person es sagt | Wiederholungen, Zeit |

Am Ende steht **ein gewöhnlicher Eintrag** bei der Übung (`eintrag`): Wiederholungen, Zeit und
Skala in ihren Feldern — bietet die Übung eines davon nicht an, bringt der Eintrag es in
seiner Kopie der Felder mit (wie die Uhr die Zeit, `core.uebung_timer.mit_zeitfeldern`). Der
Kurs liest daraus wie bisher den Wert seines Feldes (`core.kursbloecke.wert_im_test`); was
sonst gemessen wurde, steht nur dabei (`lauf_aus`, `neben_text`).

Die **Skala ist Selbstauskunft**: Die App misst sie nicht und deutet sie nicht — sie nennt
die Regel des Kurses („bis 7“) und das, was die Person eingetragen hat. Gerechnet wird nie aus
Messwerten (`docs/recht/00_zweckbestimmung.md`).

Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from .kursbloecke import MENGE, SKALA, SKALA_MAX, ZEIT, Block, Vorgabe, wert_im_test
from .models import Exercise
from .result_spec import FieldSpec, FieldType, ResultSpec, basis_key, vorrat_feld
from .timer import dauer_text
from .timer_eintrag import ZEITFELDER
from .uebung_timer import mit_zeitfeldern, zaehlt_als
from .zaehlen import zaehlt_in

#: Die Größen eines Laufs
WDH: Final = "wdh"
DAUER: Final = "zeit"
ANSTRENGUNG: Final = "skala"
GROESSEN: Final[dict[str, str]] = {
    WDH: "Wiederholungen",
    DAUER: "Zeit",
    ANSTRENGUNG: "Anstrengung",
}
#: So heißt die Skala, wenn die Übung keine eigene hat
SKALA_NAME: Final = "Anstrengung"
#: Feldschlüssel des Vorrats, wenn die Übung das Feld nicht anbietet
_WDH_FELD: Final = "reps"
_SKALA_FELD: Final = "scale"


# -- Texte der Vorgabe ----------------------------------------------------------------------


def dauer_worte(sekunden: float) -> str:
    """Eine Zeit als Vorgabe in Worten.

    >>> dauer_worte(45), dauer_worte(60), dauer_worte(120), dauer_worte(90)
    ('45 Sekunden', '1 Minute', '2 Minuten', '1:30 Minuten')
    """
    s = max(0, round(sekunden))
    if s < 60:
        return f"{s} Sekunden"
    if s % 60 == 0:
        return "1 Minute" if s == 60 else f"{s // 60} Minuten"
    return f"{dauer_text(s)} Minuten"


def vorgabe_text(v: Vorgabe, skala: str = SKALA_NAME, *, satzanfang: bool = True) -> str:
    """Die Vorgabe als Zeile — groß im Lauf, klein hinter dem Namen der Übung
    (``satzanfang=False``: „Käfer: bis Anstrengung 7“).

    >>> vorgabe_text(Vorgabe(MENGE, 30)), vorgabe_text(Vorgabe(ZEIT, 60))
    ('30 Wiederholungen', '1 Minute')
    >>> vorgabe_text(Vorgabe(SKALA, 7)), vorgabe_text(Vorgabe(SKALA, bis=4), satzanfang=False)
    ('Bis Anstrengung 7', 'solange höchstens Anstrengung 4')
    >>> vorgabe_text(Vorgabe(SKALA, 5, 7), "Schwere")
    'Zwischen Schwere 5 und 7'
    """
    if v.art == MENGE:
        return f"{v.n} Wiederholungen"
    if v.art == ZEIT:
        return dauer_worte(v.n)
    if v.bis is None:
        text = f"bis {skala} {v.n}"
    elif v.n <= 0:
        text = f"solange höchstens {skala} {v.bis}"
    else:
        text = f"zwischen {skala} {v.n} und {v.bis}"
    return text[0].upper() + text[1:] if satzanfang else text


def anleitung(v: Vorgabe, *, zaehlt_wdh: bool = True) -> str:
    """Der Satz unter der Vorgabe: was zu tun ist und was die App misst. ``zaehlt_wdh``: Die
    Übung hat Wiederholungen (eine Haltezeit hat keine).

    >>> anleitung(Vorgabe(MENGE, 30))
    'Mach 30 am Stück. Die App misst die Zeit, du sagst danach, wie anstrengend es war.'
    >>> anleitung(Vorgabe(SKALA, 7))
    'Übe, bis es bei 7 von 10 liegt. Die App misst die Zeit; wie viele es waren, sagst du danach.'
    >>> anleitung(Vorgabe(ZEIT, 60), zaehlt_wdh=False)
    'Die Uhr läuft 1 Minute. Danach sagst du, wie anstrengend es war.'
    """
    if v.art == MENGE:
        return (
            f"Mach {v.n} am Stück. Die App misst die Zeit, du sagst danach, wie anstrengend es war."
        )
    if v.art == ZEIT:
        danach = (
            "Danach sagst du, wie viele es waren und wie anstrengend es war."
            if zaehlt_wdh
            else "Danach sagst du, wie anstrengend es war."
        )
        return f"Die Uhr läuft {dauer_worte(v.n)}. {danach}"
    if v.bis is None:
        wann = f"Übe, bis es bei {v.n} von 10 liegt."
    elif v.n <= 0:
        wann = f"Übe, solange es bei höchstens {v.bis} von 10 liegt."
    else:
        wann = f"Übe, solange es zwischen {v.n} und {v.bis} von 10 liegt."
    misst = (
        "Die App misst die Zeit; wie viele es waren, sagst du danach."
        if zaehlt_wdh
        else "Die App misst die Zeit."
    )
    return f"{wann} {misst}"


def knopf_text(v: Vorgabe) -> str:
    """Der große Knopf, der den Lauf beendet — bei einer Zeit keiner (sie endet von selbst).

    >>> knopf_text(Vorgabe(MENGE, 30)), knopf_text(Vorgabe(ZEIT, 60))
    ('Fertig — 30 gemacht', '')
    >>> knopf_text(Vorgabe(SKALA, 7)), knopf_text(Vorgabe(SKALA, bis=4))
    ('Bei 7 angekommen', 'Jetzt über 4')
    >>> knopf_text(Vorgabe(SKALA, 5, 7))
    'Nicht mehr zwischen 5 und 7'
    """
    if v.art == MENGE:
        return f"Fertig — {v.n} gemacht"
    if v.art == ZEIT:
        return ""
    if v.bis is None:
        return f"Bei {v.n} angekommen"
    if v.n <= 0:
        return f"Jetzt über {v.bis}"
    return f"Nicht mehr zwischen {v.n} und {v.bis}"


def gemessen(v: Vorgabe, *, zaehlt_wdh: bool = True) -> tuple[str, ...]:
    """Die Größen, die der Lauf misst — alle außer der Vorgabe.

    >>> gemessen(Vorgabe(MENGE, 30)), gemessen(Vorgabe(SKALA, 7))
    (('zeit', 'skala'), ('wdh', 'zeit'))
    >>> gemessen(Vorgabe(ZEIT, 60), zaehlt_wdh=False)
    ('skala',)
    """
    fest = {MENGE: WDH, ZEIT: DAUER, SKALA: ANSTRENGUNG}[v.art]
    return tuple(g for g in GROESSEN if g != fest and (g != WDH or zaehlt_wdh))


def erreicht(v: Vorgabe, *, wdh: int | None, gelaufen_s: float) -> bool:
    """Endet der Lauf von selbst? Eine Menge, sobald jemand sie gezählt hat (Sensor, Takt),
    eine Zeit, sobald sie ab ist — eine Skala nie: Das sagt die Person.

    >>> erreicht(Vorgabe(MENGE, 30), wdh=30, gelaufen_s=5), erreicht(Vorgabe(MENGE, 30),
    ...     wdh=None, gelaufen_s=500)
    (True, False)
    >>> erreicht(Vorgabe(ZEIT, 60), wdh=None, gelaufen_s=60.0)
    True
    >>> erreicht(Vorgabe(SKALA, 7), wdh=99, gelaufen_s=999)
    False
    """
    if v.art == MENGE:
        return wdh is not None and wdh >= v.n
    if v.art == ZEIT:
        return gelaufen_s >= v.n
    return False


def skala_am_ende(v: Vorgabe) -> int | None:
    """Was der Knopf über die Skala schon sagt: „Bei 7 angekommen“ ist 7 — sonst nichts
    (danach fragen).

    >>> skala_am_ende(Vorgabe(SKALA, 7)), skala_am_ende(Vorgabe(SKALA, bis=4))
    (7, None)
    >>> skala_am_ende(Vorgabe(MENGE, 30)) is None
    True
    """
    return v.n if v.art == SKALA and v.bis is None else None


# -- Felder und Eintrag ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Felder:
    """In welchen Feldern des Eintrags die Größen eines Laufs stehen."""

    #: Wiederholungen — ``None``: Die Übung hat keine (eine Haltezeit)
    wdh: str | None
    zeit: str
    skala: str
    #: wie die Skala heißt (das Feld der Übung, sonst „Anstrengung“)
    skala_name: str = SKALA_NAME

    def von(self, groesse: str) -> str | None:
        return {WDH: self.wdh, DAUER: self.zeit, ANSTRENGUNG: self.skala}.get(groesse)


def _skala_feld(spec: ResultSpec | None) -> FieldSpec | None:
    return next((f for f in (spec.fields if spec else ()) if f.type == FieldType.SCALE), None)


def skala_name(spec: ResultSpec | None) -> str:
    """Wie die Skala der Übung heißt: ihr eigener Name — ohne Skala oder mit dem Namen des
    Vorrats („Skala 0–10“) „Anstrengung“.

    >>> skala_name(ResultSpec()), skala_name(ResultSpec(fields=[vorrat_feld("scale")]))
    ('Anstrengung', 'Anstrengung')
    >>> from dataclasses import replace
    >>> skala_name(ResultSpec(fields=[replace(vorrat_feld("scale"), label="Schwere")]))
    'Schwere'
    """
    feld = _skala_feld(spec)
    if feld is None:
        return SKALA_NAME
    vorlage = vorrat_feld(feld.key)
    return SKALA_NAME if vorlage is not None and feld.label == vorlage.label else feld.label


def felder(block: Block, uebung: Exercise) -> Felder:
    """Die Felder für den Lauf dieses Tests bei dieser Übung.

    - **Wiederholungen:** das Feld des Tests, wenn es eines ist, sonst das Wiederholungsfeld
      der Übung (`core.zaehlen.zaehlt_in`); gibt der Test eine Menge vor, in jedem Fall eines.
    - **Zeit:** das Feld des Tests, wenn es ein Zeitfeld ist, sonst wohin die Uhr bei dieser
      Übung zählt (`core.uebung_timer.zaehlt_als`: Haltezeit oder Zeit).
    - **Skala:** die Skala der Übung, sonst das Feld ``scale`` des Vorrats.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> kaefer = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> felder(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7)), kaefer)
    Felder(wdh='reps', zeit='duration', skala='scale', skala_name='Anstrengung')
    >>> planke = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> f = felder(Block(TEST, uebung="p", feld="hold", vorgabe=Vorgabe(ZEIT, 60)), planke)
    >>> f.wdh, f.zeit
    (None, 'hold')
    >>> felder(Block(TEST, uebung="p", feld="hold", vorgabe=Vorgabe(MENGE, 5)), planke).wdh
    'reps'
    """
    spec = uebung.result_spec
    if basis_key(block.feld) == _WDH_FELD:
        wdh: str | None = block.feld
    else:
        wdh = zaehlt_in(uebung)
        if wdh is None and block.vorgabe is not None and block.vorgabe.art == MENGE:
            wdh = _WDH_FELD
    if basis_key(block.feld) in ZEITFELDER:
        zeit = block.feld
    else:
        zeit = zaehlt_als([f.key for f in spec.fields], uebung)
    eigene = _skala_feld(spec)
    return Felder(
        wdh=wdh,
        zeit=zeit,
        skala=eigene.key if eigene is not None else _SKALA_FELD,
        skala_name=skala_name(spec),
    )


def _mit_feld(uebung: Exercise, key: str, label: str = "") -> Exercise:
    """Die Übung samt dem Feld ``key`` aus dem Vorrat — unverändert, wenn sie es schon hat."""
    spec = uebung.result_spec
    if spec.field_by_key(key) is not None or (vorlage := vorrat_feld(key)) is None:
        return uebung
    neu = FieldSpec.from_dict(vorlage.to_dict())  # eine Kopie, nicht das Feld des Vorrats
    if label:
        neu = replace(neu, label=label)
    return replace(uebung, result_spec=replace(spec, fields=[*spec.fields, neu]))


def eintrag(
    block: Block,
    uebung: Exercise,
    *,
    wdh: int | None,
    sekunden: float,
    skala: int | None,
) -> tuple[Exercise, dict[str, Any]]:
    """Was der Lauf einträgt: die Übung mit den Feldern, die der Eintrag braucht (seine Kopie
    der Spezifikation), und die Werte. Felder mit Sätzen bekommen **einen** Satz.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> kaefer = Exercise(name="Käfer", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> test = Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7))
    >>> u, werte = eintrag(test, kaefer, wdh=22, sekunden=72.4, skala=7)
    >>> werte
    {'reps': [22], 'duration': 72, 'scale': 7}
    >>> [(f.key, f.label) for f in u.result_spec.fields]
    [('reps', 'Wiederholungen'), ('duration', 'Zeit'), ('scale', 'Anstrengung')]
    >>> planke = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> eintrag(Block(TEST, uebung="p", vorgabe=Vorgabe(ZEIT, 60)), planke, wdh=None,
    ...         sekunden=60, skala=None)[1]
    {'hold': [60]}
    """
    f = felder(block, uebung)
    werte: dict[str, Any] = {}
    mit = uebung

    def setzen(key: str, wert: int, label: str = "") -> None:
        nonlocal mit
        mit = _mit_feld(mit, key, label)
        feld = mit.result_spec.field_by_key(key)
        je_satz = feld is not None and feld.type == FieldType.SET_LIST
        werte[key] = [wert] if je_satz else wert

    if wdh is not None and wdh > 0 and f.wdh:
        setzen(f.wdh, int(wdh))
    zeit = max(1, round(sekunden))
    werte[f.zeit] = zeit  # vorläufig — `mit_zeitfeldern` kennt das Feld, dann je Satz oder nicht
    mit = mit_zeitfeldern(mit, werte)
    setzen(f.zeit, zeit)
    if skala is not None:
        setzen(f.skala, int(skala), SKALA_NAME)
    # in der Reihenfolge Wiederholungen · Zeit · Skala, wie die Karte sie nennt
    return mit, {k: werte[k] for k in (f.wdh, f.zeit, f.skala) if k and k in werte}


# -- Zurücklesen -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lauf:
    """Was ein Eintrag über einen Testlauf sagt — jede Größe, die in ihm steht."""

    wdh: float | None = None
    sekunden: float | None = None
    skala: float | None = None
    skala_name: str = SKALA_NAME


def lauf_aus(block: Block, result: Mapping[str, Any], spec: ResultSpec | None) -> Lauf:
    """Die Größen eines Eintrags, gelesen mit **seiner** Kopie der Felder: das Feld des Tests
    und daneben das erste Wiederholungs-, Zeit- und Skalenfeld, das einen Wert hat. Sätze
    zählen mit ihrem besten (`wert_im_test`) — ein gewöhnlicher Eintrag geht darum auch.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> spec = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("duration"),
    ...                           vorrat_feld("scale")])
    >>> test = Block(TEST, uebung="k", feld="reps")
    >>> lauf_aus(test, {"reps": [22], "duration": 72, "scale": 7}, spec)
    Lauf(wdh=22.0, sekunden=72.0, skala=7.0, skala_name='Anstrengung')
    >>> lauf_aus(test, {"reps": [10, 12]}, None)
    Lauf(wdh=12.0, sekunden=None, skala=None, skala_name='Anstrengung')
    """

    def erstes(basen: tuple[str, ...]) -> float | None:
        schluessel = [block.feld, *result] if basis_key(block.feld) in basen else list(result)
        for k in schluessel:
            if basis_key(k) in basen and (w := wert_im_test(result, k)) is not None:
                return w
        return None

    skala_feld = _skala_feld(spec)
    skala_key = skala_feld.key if skala_feld is not None else _SKALA_FELD
    return Lauf(
        wdh=erstes((_WDH_FELD,)),
        sekunden=erstes(ZEITFELDER),
        skala=wert_im_test(result, skala_key),
        skala_name=skala_name(spec),
    )


def neben_text(block: Block, lauf: Lauf) -> str:
    """Was neben dem Wert des Tests steht: die anderen Größen des Laufs.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> neben_text(Block(TEST, uebung="k", feld="reps"), Lauf(22, 72, 7))
    'in 1:12 · Anstrengung 7'
    >>> neben_text(Block(TEST, uebung="k", feld="duration"), Lauf(30, 65, 6))
    '30 Wdh. · Anstrengung 6'
    >>> neben_text(Block(TEST, uebung="p", feld="hold"), Lauf(None, 48, None))
    ''
    """
    teile: list[str] = []
    feld_ist_zeit = basis_key(block.feld) in ZEITFELDER
    if not feld_ist_zeit and lauf.sekunden:
        teile.append(f"in {dauer_text(lauf.sekunden)}")
    if basis_key(block.feld) != _WDH_FELD and lauf.wdh:
        teile.append(f"{lauf.wdh:g} Wdh.")
    if lauf.skala is not None:
        teile.append(f"{lauf.skala_name} {lauf.skala:g}")
    return " · ".join(teile)


def anhang(v: Vorgabe, feld: str, skala: str = SKALA_NAME) -> str:
    """Die Vorgabe hinter dem Testwert in der Sammelkarte („22 Wdh. **bis Anstrengung 7**“) —
    leer, wenn der Wert die Vorgabe selbst ist (30 Wiederholungen bei Vorgabe Menge).

    >>> anhang(Vorgabe(SKALA, 7), "reps"), anhang(Vorgabe(ZEIT, 60), "reps")
    ('bis Anstrengung 7', 'in 1 Minute')
    >>> anhang(Vorgabe(MENGE, 30), "duration"), anhang(Vorgabe(MENGE, 30), "reps")
    ('für 30 Wdh.', '')
    >>> anhang(Vorgabe(SKALA, 5, 7), "hold"), anhang(Vorgabe(SKALA, bis=4), "hold")
    ('bei Anstrengung 5–7', 'bei höchstens Anstrengung 4')
    """
    basis = basis_key(feld)
    if v.art == MENGE:
        return "" if basis == _WDH_FELD else f"für {v.n} Wdh."
    if v.art == ZEIT:
        return "" if basis in ZEITFELDER else f"in {dauer_worte(v.n)}"
    if v.bis is None:
        return f"bis {skala} {v.n}"
    if v.n <= 0:
        return f"bei höchstens {skala} {v.bis}"
    return f"bei {skala} {v.n}–{v.bis}"


def herkunft(faktor: float, wert_text: str, v: Vorgabe | None, feld: str, skala: str = "") -> str:
    """Woher ein Ziel aus dem Test kommt — die **Regel des Kurses**, ohne Wertung: „aus deinem
    Test“, mit Faktor „80 % von deinem Test (…)“, mit Vorgabe der gemessene Wert dazu.

    >>> herkunft(1.0, "48 s", None, "hold")
    'aus deinem Test'
    >>> herkunft(0.8, "22 Wdh.", Vorgabe(SKALA, 7), "reps")
    '80 % von deinem Test (22 Wdh. bis Anstrengung 7)'
    >>> herkunft(1.0, "30 Wdh.", Vorgabe(MENGE, 30), "reps"), herkunft(0.8, "48 s", None, "hold")
    ('aus deinem Test (30 Wdh.)', '80 % von deinem Test (48 s)')
    """
    anteil = "aus deinem Test" if faktor == 1.0 else f"{round(faktor * 100)} % von deinem Test"
    if v is None and faktor == 1.0:
        return anteil
    dazu = anhang(v, feld, skala or SKALA_NAME) if v is not None else ""
    return f"{anteil} ({' '.join(t for t in (wert_text, dazu) if t)})"


# -- Der Lauf auf der Teilnehmer-Seite: Anzeige, Ende, Ergebnis (Stufe 2, 16.11.2026) ---------
#
# Die Ansicht `ui/views/kurs_testlauf.py` zeichnet nur; was sie zeigt und wann „Eintragen“ geht,
# steht hier.

#: Woher eine Größe im Ergebnis kommt (`woher_wdh`, `woher_zeit`) …
VORGEGEBEN: Final = "vorgabe"
VON_DER_UHR: Final = "uhr"
GEZAEHLT: Final = "gezaehlt"
GEFRAGT: Final = "gefragt"
#: … und wie das unter ihrem Namen steht („Wiederholungen — die Vorgabe“)
WOHER: Final[dict[str, str]] = {
    VORGEGEBEN: "die Vorgabe",
    VON_DER_UHR: "von der Uhr",
    GEZAEHLT: "gezählt",
    GEFRAGT: "sagst du",
}


def zeit_anzeige(v: Vorgabe, gelaufen_s: float) -> str:
    """Die große Zeit im Lauf: was gelaufen ist (abgerundet, wie die Stoppuhr) — bei einer
    Zeit als Vorgabe der Rest bis 0 (aufgerundet, wie der Timer).

    >>> zeit_anzeige(Vorgabe(MENGE, 30), 42.7), zeit_anzeige(Vorgabe(ZEIT, 60), 42.7)
    ('0:42', '0:18')
    >>> zeit_anzeige(Vorgabe(ZEIT, 60), 75), zeit_anzeige(Vorgabe(SKALA, 7), 72.0)
    ('0:00', '1:12')
    """
    if v.art == ZEIT:
        return dauer_text(math.ceil(max(v.n - gelaufen_s, 0.0)))
    return dauer_text(int(max(gelaufen_s, 0.0)))


def zeit_zeile(v: Vorgabe) -> str:
    """Die Zeile unter der großen Zeit: Die Zeit wird gemessen — oder sie ist die Vorgabe.

    >>> zeit_zeile(Vorgabe(MENGE, 30)), zeit_zeile(Vorgabe(ZEIT, 60))
    ('Zeit läuft · wird gemessen', 'Zeit läuft · endet von selbst')
    """
    return "Zeit läuft · endet von selbst" if v.art == ZEIT else "Zeit läuft · wird gemessen"


def zaehl_text(v: Vorgabe, wer: str = "") -> tuple[str, str]:
    """Die Karte „Wiederholungen“ im Lauf — wer zählt, und was daraus folgt. ``wer``: „Sensor“
    oder „Takt“ (`core.zaehlen.quelle_name`), leer = die Person.

    >>> zaehl_text(Vorgabe(MENGE, 30))
    ('Du zählst selbst', 'Bei 30 tippst du „Fertig“ — die Uhr hält an.')
    >>> zaehl_text(Vorgabe(MENGE, 30), "Sensor")
    ('Sensor zählt', 'Bei 30 hält die Uhr von selbst an.')
    >>> zaehl_text(Vorgabe(ZEIT, 60)), zaehl_text(Vorgabe(SKALA, 7), "Takt")
    (('Du zählst selbst', 'Wie viele es waren, sagst du danach.'), ('Takt zählt', ''))
    """
    if wer:
        return f"{wer} zählt", f"Bei {v.n} hält die Uhr von selbst an." if v.art == MENGE else ""
    if v.art == MENGE:
        return "Du zählst selbst", f"Bei {v.n} tippst du „Fertig“ — die Uhr hält an."
    return "Du zählst selbst", "Wie viele es waren, sagst du danach."


def unten_text(v: Vorgabe) -> str:
    """Der kleine Satz unter den Knöpfen im Lauf.

    >>> unten_text(Vorgabe(MENGE, 30)), unten_text(Vorgabe(SKALA, 7))
    ('„Vorher aufgehört“ fragt, wie viele es waren.', 'Ein Tipp hält die Uhr an.')
    >>> unten_text(Vorgabe(ZEIT, 60))
    'Bei 0 hält die Uhr von selbst an.'
    """
    if v.art == MENGE:
        return "„Vorher aufgehört“ fragt, wie viele es waren."
    if v.art == ZEIT:
        return "Bei 0 hält die Uhr von selbst an."
    return "Ein Tipp hält die Uhr an."


@dataclass(frozen=True, slots=True)
class Marke:
    """Die Marke auf dem Balken 1–10 der Anstrengung: die Stufen ``von`` bis ``bis`` und, was
    darunter steht."""

    von: int
    bis: int
    text: str


def marke(v: Vorgabe) -> Marke | None:
    """Wo die **Regel des Kurses** auf dem Balken der Anstrengung liegt — ``None``, wenn die
    Vorgabe keine Skala ist. Die App nennt die Regel; wie es sich anfühlt, sagt die Person.

    >>> marke(Vorgabe(SKALA, 7))
    Marke(von=7, bis=7, text='7 · hier ist Schluss')
    >>> marke(Vorgabe(SKALA, bis=4)), marke(Vorgabe(SKALA, 5, 7))
    (Marke(von=4, bis=4, text='4 · bis hier'), Marke(von=5, bis=7, text='5 bis 7 · dein Bereich'))
    >>> marke(Vorgabe(MENGE, 30)) is None
    True
    """
    if v.art != SKALA:
        return None
    if v.bis is None:
        return Marke(v.n, v.n, f"{v.n} · hier ist Schluss")
    if v.n <= 0:
        return Marke(v.bis, v.bis, f"{v.bis} · bis hier")
    return Marke(v.n, v.bis, f"{v.n} bis {v.bis} · dein Bereich")


def am_ende(
    v: Vorgabe,
    f: Felder,
    *,
    gelaufen_s: float,
    vorher: bool = False,
    gezaehlt: int | None = None,
) -> tuple[int | None, float, int | None]:
    """Was mit dem Ende des Laufs feststeht — Wiederholungen, Sekunden, Skala. ``None`` heißt:
    danach fragen (Wiederholungen nur, wenn die Übung welche hat, `Felder.wdh`). ``vorher``:
    „Vorher aufgehört“ — die Vorgabe ist dann nicht erreicht, es gilt, was gemessen wurde;
    ``gezaehlt``: was Sensor oder Takt zählten (dann fragt niemand).

    >>> kaefer = Felder("reps", "duration", "scale")
    >>> am_ende(Vorgabe(MENGE, 30), kaefer, gelaufen_s=65.2)
    (30, 65.2, None)
    >>> am_ende(Vorgabe(MENGE, 30), kaefer, gelaufen_s=40.0, vorher=True)
    (None, 40.0, None)
    >>> am_ende(Vorgabe(SKALA, 7), kaefer, gelaufen_s=72.0)
    (None, 72.0, 7)
    >>> am_ende(Vorgabe(SKALA, 7), kaefer, gelaufen_s=50.0, vorher=True)
    (None, 50.0, None)
    >>> am_ende(Vorgabe(ZEIT, 60), kaefer, gelaufen_s=60.2, gezaehlt=18)
    (18, 60.0, None)
    >>> am_ende(Vorgabe(ZEIT, 60), Felder(None, "hold", "scale"), gelaufen_s=31.0, vorher=True)
    (None, 31.0, None)
    """
    wdh: int | None = None
    if f.wdh is not None:
        if gezaehlt is not None:
            wdh = gezaehlt
        elif v.art == MENGE and not vorher:
            wdh = v.n
    sekunden = float(v.n) if v.art == ZEIT and not vorher else gelaufen_s
    return wdh, sekunden, None if vorher else skala_am_ende(v)


def woher_wdh(v: Vorgabe, f: Felder, *, vorher: bool = False, gezaehlt: bool = False) -> str | None:
    """Woher die Wiederholungen im Ergebnis kommen (`WOHER`) — ``None``: Die Übung hat keine,
    die Zeile fällt weg. `GEFRAGT` heißt: ein Zahlenfeld.

    >>> kaefer = Felder("reps", "duration", "scale")
    >>> woher_wdh(Vorgabe(MENGE, 30), kaefer), woher_wdh(Vorgabe(MENGE, 30), kaefer, vorher=True)
    ('vorgabe', 'gefragt')
    >>> woher_wdh(Vorgabe(SKALA, 7), kaefer), woher_wdh(Vorgabe(ZEIT, 60), kaefer, gezaehlt=True)
    ('gefragt', 'gezaehlt')
    >>> woher_wdh(Vorgabe(ZEIT, 60), Felder(None, "hold", "scale")) is None
    True
    """
    if f.wdh is None:
        return None
    if gezaehlt:
        return GEZAEHLT
    return VORGEGEBEN if v.art == MENGE and not vorher else GEFRAGT


def woher_zeit(v: Vorgabe, *, vorher: bool = False) -> str:
    """Woher die Zeit im Ergebnis kommt: von der Uhr — außer sie war die Vorgabe und ist
    abgelaufen.

    >>> woher_zeit(Vorgabe(ZEIT, 60)), woher_zeit(Vorgabe(ZEIT, 60), vorher=True)
    ('vorgabe', 'uhr')
    >>> woher_zeit(Vorgabe(MENGE, 30))
    'uhr'
    """
    return VORGEGEBEN if v.art == ZEIT and not vorher else VON_DER_UHR


def fehlt(
    block: Block, uebung: Exercise, *, wdh: int | None, sekunden: float, skala: int | None
) -> str:
    """Was dem Eintrag noch fehlt, damit der Test einen Wert hat: der Name des Feldes, das der
    Kurs liest (`Block.feld`; `KursRepo.testwerte` zählt nur Werte über 0) — leer, wenn nichts
    fehlt. Solange etwas fehlt, gibt es kein „Eintragen“.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> kaefer = Exercise(name="Käfer", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> test = Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7))
    >>> fehlt(test, kaefer, wdh=None, sekunden=72, skala=7), fehlt(test, kaefer, wdh=0,
    ...     sekunden=72, skala=7)
    ('Wiederholungen', 'Wiederholungen')
    >>> fehlt(test, kaefer, wdh=22, sekunden=72, skala=None)
    ''
    >>> zeit = Block(TEST, uebung="k", feld="duration", vorgabe=Vorgabe(MENGE, 30))
    >>> fehlt(zeit, kaefer, wdh=None, sekunden=65, skala=None)
    ''
    >>> wie_schwer = Block(TEST, uebung="k", feld="scale", vorgabe=Vorgabe(MENGE, 30))
    >>> fehlt(wie_schwer, kaefer, wdh=30, sekunden=65, skala=None)
    'Anstrengung'
    """
    _, werte = eintrag(block, uebung, wdh=wdh, sekunden=sekunden, skala=skala)
    wert = wert_im_test(werte, block.feld)
    if wert is not None and wert > 0:
        return ""
    f = felder(block, uebung)
    if block.feld == f.wdh:
        return GROESSEN[WDH]
    if block.feld == f.skala:
        return f.skala_name
    feld = uebung.result_spec.field_by_key(block.feld) or vorrat_feld(basis_key(block.feld))
    return feld.label if feld is not None else block.feld


def skala_stufen(spec: ResultSpec | None) -> range:
    """Die Stufen, die die Frage nach der Skala anbietet: die der Skala der Übung — ohne
    eigene, ohne Grenzen oder mit mehr als 21 Stufen 0 bis 10 (wie im Fokus).

    >>> skala_stufen(ResultSpec()), skala_stufen(ResultSpec(fields=[vorrat_feld("scale")]))
    (range(0, 11), range(0, 11))
    >>> from dataclasses import replace
    >>> skala_stufen(ResultSpec(fields=[replace(vorrat_feld("scale"), min=6, max=20)]))
    range(6, 21)
    >>> skala_stufen(ResultSpec(fields=[replace(vorrat_feld("scale"), min=0, max=100)]))
    range(0, 11)
    """
    feld = _skala_feld(spec)
    unten = int(feld.min) if feld is not None and feld.min is not None else 0
    oben = int(feld.max) if feld is not None and feld.max is not None else SKALA_MAX
    if oben < unten or oben - unten > 20:
        unten, oben = 0, SKALA_MAX
    return range(unten, oben + 1)


def skala_frage(name: str = SKALA_NAME, stufen: range | None = None) -> tuple[str, str]:
    """Die Frage nach der Skala im Ergebnis und die Zeile darunter — bei einer eigenen Skala
    der Übung mit ihrem Namen, ohne Deutung der Enden.

    >>> skala_frage()
    ('Wie anstrengend war es?', '0 = gar nicht · 10 = mehr geht nicht')
    >>> skala_frage("Schwere", range(1, 6))
    ('Schwere — wie war es?', '1 bis 5')
    """
    stufen = stufen if stufen is not None else range(0, SKALA_MAX + 1)
    if name == SKALA_NAME and (stufen.start, stufen.stop) == (0, SKALA_MAX + 1):
        return "Wie anstrengend war es?", "0 = gar nicht · 10 = mehr geht nicht"
    return f"{name} — wie war es?", f"{stufen.start} bis {stufen.stop - 1}"


__all__ = [
    "ANSTRENGUNG",
    "DAUER",
    "GEFRAGT",
    "GEZAEHLT",
    "GROESSEN",
    "SKALA_NAME",
    "VON_DER_UHR",
    "VORGEGEBEN",
    "WDH",
    "WOHER",
    "Felder",
    "Lauf",
    "Marke",
    "am_ende",
    "anhang",
    "anleitung",
    "dauer_worte",
    "eintrag",
    "erreicht",
    "fehlt",
    "felder",
    "gemessen",
    "herkunft",
    "knopf_text",
    "lauf_aus",
    "marke",
    "neben_text",
    "skala_am_ende",
    "skala_frage",
    "skala_name",
    "skala_stufen",
    "unten_text",
    "vorgabe_text",
    "woher_wdh",
    "woher_zeit",
    "zaehl_text",
    "zeit_anzeige",
    "zeit_zeile",
]
