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

**Der gestaltete Test** (Ben, 16.11.2026: „Der Test muss flexibel gestaltet werden können“ —
„Dinge mit Standardwerten versehen. Überschreiben ist möglich“): Ein Test läuft auch ohne
Vorgabe mit der Uhr, sobald er etwas gestaltet (`Block.laeuft`). Was dann gilt, steht hier:

- **Womit er läuft** (`uhr_fuer`): sein eigener Timer → sonst, „wie die Übung“, ihr Timer →
  sonst die Stoppuhr. Mit einem Timer endet der Lauf, wenn der Timer durch ist (`erreicht`);
  eine Vorgabe „Zeit“ gilt dann nicht — der Timer ist die Zeit (`vorgabe_fuer`). Als Zeit
  zählt, was in seinen zählenden Abschnitten lief (`gezaehlte_zeit`).
- **Der Takt** (`takt_fuer`): sein eigener → sonst, „wie die Übung“, ihrer → sonst keiner. Er
  **führt nur, er zählt nicht** (ein Soll ist keine Messung): Der Lauf endet nie mit ihm, und
  seine Runden (`takt_runden`, aus der Uhr gerechnet) stehen im Ergebnis als **Vorschlag**,
  den die Person bestätigt oder ändert (`am_ende`, `woher_wdh`, `takt_frage`).
- **Die Ausführung** (`ausfuehrung_fuer`): alles an der Übung, was der Lauf nicht misst —
  Variante, Seite, Gewicht, Winkel, Strecke (`ist_ausfuehrung`). Vorgegeben (`Block.ziel`)
  steht sie nur da, frei (`Block.felder`, „wie die Übung“ alle) wählt die Person sie vor dem
  Start, vorbelegt mit dem Standard der Übung. Sie kommt in den Eintrag (`eintrag`).

Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .kursbloecke import (
    ANTEIL,
    HAND,
    MENGE,
    SKALA,
    SKALA_MAX,
    WIE_PARAMETER,
    WIE_TAKT,
    WIE_UHR,
    ZEIT,
    Block,
    Planwert,
    Vorgabe,
    wert_im_test,
)
from .models import Exercise
from .result_spec import (
    FieldSpec,
    FieldType,
    ResultSpec,
    basis_key,
    geordnet,
    ist_leer,
    vorrat_feld,
)
from .tagesbilanz import menge_text
from .takt import Takt, rate_text, takt_waehlen
from .takt import dauer_text as takt_dauer
from .timer import TimerProfil, TimerStand, dauer_text, stoppuhr
from .timer_eintrag import ZEITFELDER
from .uebung_timer import (
    ausfuehrung_text,
    mit_zeitfeldern,
    takt_der_uebung,
    timer_fuer,
    zaehlt_als,
)
from .units import parse_dauer
from .varianten import LABEL as VARIANTE_NAME
from .varianten import VARIANTE, ist_variante
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
#: Die Frage in der Überschrift der Testkarte, wenn im Lauf keine Vorgabe gilt: „Käfer: was
#: schaffst du?“ (`karten_ueberschrift`)
OHNE_VORGABE: Final = "was schaffst du?"
#: So heißt ein Timer, dem niemand einen Namen gab (`core.timer.TimerProfil.name`) — das ist
#: kein Name, den man nennt (`timer_name`)
_TIMER_OHNE_NAMEN: Final = TimerProfil().name


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


def _mit_timer(profil: TimerProfil | None) -> TimerProfil | None:
    """Der Timer, mit dem ein Lauf läuft — ``None`` ohne Angabe und bei der Stoppuhr."""
    return None if profil is None or profil.ist_stoppuhr else profil


def _gilt(v: Vorgabe | None, timer: TimerProfil | None) -> Vorgabe | None:
    """Die Vorgabe, die im Lauf gilt: Mit einem Timer gibt es keine Vorgabe „Zeit“ — der
    Timer ist die Zeit (`vorgabe_fuer`)."""
    return None if v is not None and v.art == ZEIT and _mit_timer(timer) is not None else v


def anleitung(
    v: Vorgabe | None, *, zaehlt_wdh: bool = True, timer: TimerProfil | None = None
) -> str:
    """Der Satz unter der Vorgabe: was zu tun ist und was die App misst. ``zaehlt_wdh``: Die
    Übung hat Wiederholungen (eine Haltezeit hat keine). ``timer``: Der Lauf läuft mit diesem
    Timer statt mit der Stoppuhr (`uhr_fuer`); ``v`` ``None``: ein gestalteter Test ohne
    Vorgabe.

    >>> anleitung(Vorgabe(MENGE, 30))
    'Mach 30 am Stück. Die App misst die Zeit, du sagst danach, wie anstrengend es war.'
    >>> anleitung(Vorgabe(SKALA, 7))
    'Übe, bis es bei 7 von 10 liegt. Die App misst die Zeit; wie viele es waren, sagst du danach.'
    >>> anleitung(Vorgabe(ZEIT, 60), zaehlt_wdh=False)
    'Die Uhr läuft 1 Minute. Danach sagst du, wie anstrengend es war.'

    Ohne Vorgabe misst die Stoppuhr, bis die Person „Fertig“ sagt — oder der Timer läuft durch:

    >>> anleitung(None, zaehlt_wdh=False)
    'Die App misst die Zeit, bis du „Fertig“ tippst. Danach sagst du, wie anstrengend es war.'
    >>> from trainingsapp.core.timer import Abschnitt
    >>> tabata = TimerProfil(name="Tabata", abschnitte=[Abschnitt("Los", 20),
    ...                      Abschnitt("Pause", 10, zaehlt=False)], runden=8)
    >>> anleitung(None, timer=tabata)
    'Der Timer läuft 4 Minuten. Danach sagst du, wie viele es waren und wie anstrengend es war.'
    >>> anleitung(Vorgabe(ZEIT, 60), timer=tabata) == anleitung(None, timer=tabata)
    True
    >>> anleitung(Vorgabe(MENGE, 30), timer=tabata).endswith("Ist der Timer vorher durch "
    ...     "(4 Minuten), endet der Test.")
    True
    """
    lauf = _mit_timer(timer)
    v = _gilt(v, timer)
    danach = (
        "Danach sagst du, wie viele es waren und wie anstrengend es war."
        if zaehlt_wdh
        else "Danach sagst du, wie anstrengend es war."
    )
    if v is None:
        if lauf is not None:
            return f"Der Timer läuft {dauer_worte(lauf.gesamt_s())}. {danach}"
        return f"Die App misst die Zeit, bis du „Fertig“ tippst. {danach}"
    dazu = (
        f" Ist der Timer vorher durch ({dauer_worte(lauf.gesamt_s())}), endet der Test."
        if lauf is not None
        else ""
    )
    if v.art == MENGE:
        return (
            f"Mach {v.n} am Stück. Die App misst die Zeit, du sagst danach, wie anstrengend "
            f"es war.{dazu}"
        )
    if v.art == ZEIT:
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
    return f"{wann} {misst}{dazu}"


def knopf_text(v: Vorgabe | None, *, timer: TimerProfil | None = None) -> str:
    """Der große Knopf, der den Lauf beendet — bei einer Zeit keiner (sie endet von selbst),
    ebenso mit einem Timer ohne Vorgabe. Ohne Vorgabe und ohne Timer beendet „Fertig“.

    >>> knopf_text(Vorgabe(MENGE, 30)), knopf_text(Vorgabe(ZEIT, 60))
    ('Fertig — 30 gemacht', '')
    >>> knopf_text(Vorgabe(SKALA, 7)), knopf_text(Vorgabe(SKALA, bis=4))
    ('Bei 7 angekommen', 'Jetzt über 4')
    >>> knopf_text(Vorgabe(SKALA, 5, 7))
    'Nicht mehr zwischen 5 und 7'
    >>> from trainingsapp.core.timer import Abschnitt
    >>> knopf_text(None), knopf_text(None, timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    ('Fertig', '')
    """
    v = _gilt(v, timer)
    if v is None:
        return "" if _mit_timer(timer) is not None else "Fertig"
    if v.art == MENGE:
        return f"Fertig — {v.n} gemacht"
    if v.art == ZEIT:
        return ""
    if v.bis is None:
        return f"Bei {v.n} angekommen"
    if v.n <= 0:
        return f"Jetzt über {v.bis}"
    return f"Nicht mehr zwischen {v.n} und {v.bis}"


def vorher_knopf(v: Vorgabe | None, *, timer: TimerProfil | None = None) -> bool:
    """Gibt es „Vorher aufgehört …“? Immer, wenn etwas das Ende vorgibt (eine Vorgabe, ein
    Timer) — ohne beides ist „Fertig“ das Ende, und vorher gibt es nicht.

    >>> vorher_knopf(Vorgabe(MENGE, 30)), vorher_knopf(None)
    (True, False)
    >>> from trainingsapp.core.timer import Abschnitt
    >>> vorher_knopf(None, timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    True
    """
    return v is not None or _mit_timer(timer) is not None


def gemessen(
    v: Vorgabe | None, *, zaehlt_wdh: bool = True, timer: TimerProfil | None = None
) -> tuple[str, ...]:
    """Die Größen, die der Lauf misst — alle außer der Vorgabe; mit einem Timer ohne Vorgabe
    alle außer der Zeit (der Timer ist die Zeit).

    >>> gemessen(Vorgabe(MENGE, 30)), gemessen(Vorgabe(SKALA, 7))
    (('zeit', 'skala'), ('wdh', 'zeit'))
    >>> gemessen(Vorgabe(ZEIT, 60), zaehlt_wdh=False)
    ('skala',)
    >>> from trainingsapp.core.timer import Abschnitt
    >>> gemessen(None), gemessen(None, timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    (('wdh', 'zeit', 'skala'), ('wdh', 'skala'))
    """
    v = _gilt(v, timer)
    if v is None:
        fest = DAUER if _mit_timer(timer) is not None else ""
    else:
        fest = {MENGE: WDH, ZEIT: DAUER, SKALA: ANSTRENGUNG}[v.art]
    return tuple(g for g in GROESSEN if g != fest and (g != WDH or zaehlt_wdh))


def erreicht(v: Vorgabe | None, *, wdh: int | None, gelaufen_s: float, durch: bool = False) -> bool:
    """Endet der Lauf von selbst? Eine Menge, sobald der Sensor sie gezählt hat, eine Zeit,
    sobald sie ab ist — eine Skala nie: Das sagt die Person. ``durch``: Der Timer des Laufs
    ist durch — dann endet er in jedem Fall. **Ein Takt beendet nie etwas** (er führt, er
    zählt nicht): ``wdh`` ist nur, was der Sensor zählte.

    >>> erreicht(Vorgabe(MENGE, 30), wdh=30, gelaufen_s=5), erreicht(Vorgabe(MENGE, 30),
    ...     wdh=None, gelaufen_s=500)
    (True, False)
    >>> erreicht(Vorgabe(ZEIT, 60), wdh=None, gelaufen_s=60.0)
    True
    >>> erreicht(Vorgabe(SKALA, 7), wdh=99, gelaufen_s=999)
    False
    >>> erreicht(None, wdh=99, gelaufen_s=999), erreicht(None, wdh=None, gelaufen_s=9, durch=True)
    (False, True)
    """
    if durch:
        return True
    if v is None:
        return False
    if v.art == MENGE:
        return wdh is not None and wdh >= v.n
    if v.art == ZEIT:
        return gelaufen_s >= v.n
    return False


def verfehlt(
    v: Vorgabe | None, *, vorher: bool, durch: bool, wdh: int | None, gelaufen_s: float
) -> bool:
    """Ist die Vorgabe **nicht erreicht**? Mit „Vorher aufgehört …“ (``vorher``) — oder wenn
    der Timer durch war (``durch``), bevor die Menge gezählt bzw. die Anstrengung gesagt war.
    Ohne Vorgabe gibt es nichts zu verfehlen: Der Timer ist dann einfach durch.

    >>> verfehlt(Vorgabe(SKALA, 7), vorher=True, durch=False, wdh=None, gelaufen_s=40)
    True
    >>> verfehlt(Vorgabe(SKALA, 7), vorher=False, durch=True, wdh=None, gelaufen_s=240)
    True
    >>> verfehlt(Vorgabe(MENGE, 30), vorher=False, durch=True, wdh=31, gelaufen_s=240)
    False
    >>> verfehlt(None, vorher=False, durch=True, wdh=None, gelaufen_s=240)
    False
    """
    if vorher:
        return True
    return durch and v is not None and not erreicht(v, wdh=wdh, gelaufen_s=gelaufen_s)


def skala_am_ende(v: Vorgabe | None) -> int | None:
    """Was der Knopf über die Skala schon sagt: „Bei 7 angekommen“ ist 7 — sonst nichts
    (danach fragen).

    >>> skala_am_ende(Vorgabe(SKALA, 7)), skala_am_ende(Vorgabe(SKALA, bis=4))
    (7, None)
    >>> skala_am_ende(Vorgabe(MENGE, 30)) is None, skala_am_ende(None) is None
    (True, True)
    """
    return v.n if v is not None and v.art == SKALA and v.bis is None else None


# -- Der gestaltete Test: Uhr, Takt, Ausführung (Ben, 16.11.2026) ---------------------------
#
# Vorgaben ohne Angabe: Stoppuhr, kein Takt, keine Ausführung — der Test, wie er war.


def uhr_fuer(block: Block, uebung: Exercise | None = None) -> TimerProfil:
    """**Womit der Test läuft:** sein eigener Timer (`Block.timer`) — sonst, „wie die Übung“
    (`WIE_UHR`), der Timer der Übung, wie sie gerade eingestellt ist
    (`core.uebung_timer.timer_fuer`: ihr erstes Profil, Verweise in die Timer-Bibliothek sind
    beim Laden der Übung schon aufgelöst) — sonst die Stoppuhr. Immer eine eigene Kopie. Eine
    Stoppuhr unter den Profilen der Übung ist die Stoppuhr; ohne ``uebung`` zählt nur der
    eigene Timer.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.timer import Abschnitt
    >>> halten = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("Halten", 60)])
    >>> planke = Exercise(name="Planke", timer=[halten.als_dict()])
    >>> uhr_fuer(Block(TEST, uebung="p"), planke).ist_stoppuhr
    True
    >>> uhr_fuer(Block(TEST, uebung="p", wie_uebung=["uhr"]), planke).name
    'Halten'
    >>> eigen = TimerProfil(id="e", name="Intervall", abschnitte=[Abschnitt("Los", 30)])
    >>> beides = Block(TEST, uebung="p", timer=eigen.als_dict(), wie_uebung=["uhr"])
    >>> uhr_fuer(beides, planke).name, uhr_fuer(beides).name  # der eigene geht vor
    ('Intervall', 'Intervall')
    >>> uhr_fuer(Block(TEST, uebung="k", wie_uebung=["uhr"]), Exercise()).ist_stoppuhr
    True
    """
    profil = TimerProfil.aus_dict(dict(block.timer)) if block.timer else None
    if profil is None and uebung is not None and WIE_UHR in block.wie_uebung:
        der_uebung = timer_fuer(uebung)
        profil = TimerProfil.aus_dict(der_uebung.als_dict()) if der_uebung is not None else None
    return profil if profil is not None and not profil.ist_stoppuhr else stoppuhr()


def vorgabe_fuer(block: Block, profil: TimerProfil | None = None) -> Vorgabe | None:
    """Die **Vorgabe, die im Lauf gilt**: die des Tests — außer einer „Zeit“, wenn der Lauf
    mit einem Timer läuft: Der Timer ist die Zeit (der Editor verhindert die Kombination, aus
    einem Paket kann sie kommen). Menge und Anstrengung gelten mit Timer weiter und können
    vorher beenden.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.timer import Abschnitt
    >>> timer = TimerProfil(abschnitte=[Abschnitt("Los", 90)])
    >>> zeit = Block(TEST, uebung="u", vorgabe=Vorgabe(ZEIT, 60))
    >>> vorgabe_fuer(zeit, stoppuhr()), vorgabe_fuer(zeit, timer)
    (Vorgabe(art='zeit', n=60, bis=None), None)
    >>> vorgabe_fuer(Block(TEST, uebung="u", vorgabe=Vorgabe(MENGE, 30)), timer)
    Vorgabe(art='menge', n=30, bis=None)
    >>> vorgabe_fuer(Block(TEST, uebung="u", wie_uebung=["uhr"]), timer) is None
    True
    """
    return _gilt(block.vorgabe, profil)


def takt_fuer(block: Block, uebung: Exercise | None = None) -> Takt | None:
    """**Der Takt des Tests:** sein eigener (`Block.takt`) — sonst, „wie die Übung“
    (`WIE_TAKT`), der Takt der Übung (`core.uebung_timer.takt_der_uebung`) — sonst keiner.
    Am Lauf ist er die Stufe „Übung“ (`TimerLauf.takt_uebung`): Ein Abschnitt des Timers mit
    eigenem Takt behält ihn. Er führt nur — auch ein Takt, der beim Üben zählt (`Takt.zaehlt`),
    zählt im Test nicht.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.takt import AUS, VORLAGEN
    >>> kniebeuge = Exercise(takt=VORLAGEN["kniebeuge_2_1_2"])
    >>> takt_fuer(Block(TEST, uebung="k"), kniebeuge) is None
    True
    >>> takt_fuer(Block(TEST, uebung="k", wie_uebung=["takt"]), kniebeuge).name
    'Kniebeuge 2-1-2'
    >>> eigen = Block(TEST, uebung="k", takt=VORLAGEN["metronom_1"], wie_uebung=["takt"])
    >>> takt_fuer(eigen, kniebeuge).name, takt_fuer(eigen).name
    ('Metronom 1 s', 'Metronom 1 s')
    >>> takt_fuer(Block(TEST, uebung="k", takt=AUS, wie_uebung=["takt"]), Exercise()) is None
    True
    """
    if block.takt is not None and not block.takt.leer:
        return block.takt
    if uebung is None or WIE_TAKT not in block.wie_uebung:
        return None
    der_uebung = takt_der_uebung(uebung)
    return der_uebung if der_uebung is not None and not der_uebung.leer else None


def fuehrt_ein_takt(profil: TimerProfil, takt: Takt | None) -> bool:
    """Läuft in diesem Lauf irgendwo ein Takt mit — der des Tests (`takt_fuer`) oder der
    eines Abschnitts seines Timers? Dann zeigt der Lauf die Karte des Takts statt „Du zählst
    selbst“.

    >>> from trainingsapp.core.takt import VORLAGEN
    >>> from trainingsapp.core.timer import Abschnitt
    >>> k = VORLAGEN["kniebeuge_2_1_2"]
    >>> fuehrt_ein_takt(stoppuhr(), k), fuehrt_ein_takt(stoppuhr(), None)
    (True, False)
    >>> fuehrt_ein_takt(TimerProfil(abschnitte=[Abschnitt("Los", 20, takt=k)]), None)
    True
    """
    return any(takt_waehlen(None, a.takt, takt) is not None for a in profil.alle_abschnitte())


def gezaehlte_zeit(profil: TimerProfil, gelaufen_s: float) -> float:
    """Die **Zeit des Tests** nach ``gelaufen_s`` Sekunden Laufzeit: bei der Stoppuhr die
    Laufzeit — bei einem Timer, was in seinen **zählenden** Abschnitten lief (Vorbereitung
    und Pause zählen nicht, `core.timer.Abschnitt.zaehlt`).

    >>> from trainingsapp.core.timer import Abschnitt
    >>> p = TimerProfil(abschnitte=[Abschnitt("Vor", 10, zaehlt=False), Abschnitt("Los", 30)],
    ...                 runden=2)
    >>> gezaehlte_zeit(p, 25), gezaehlte_zeit(p, 80), gezaehlte_zeit(p, 999)
    (15.0, 60.0, 60.0)
    >>> gezaehlte_zeit(stoppuhr(), 72.4)
    72.4
    """
    if profil.ist_stoppuhr:
        return max(float(gelaufen_s), 0.0)
    summe, anfang = 0.0, 0.0
    for *_, a in profil.folge():
        if a.zaehlt:
            summe += min(max(gelaufen_s - anfang, 0.0), float(a.dauer_s))
        anfang += a.dauer_s
    return summe


def takt_runden(profil: TimerProfil, takt: Takt | None, gelaufen_s: float) -> int:
    """Wie viele **volle Runden** der Takt in ``gelaufen_s`` Sekunden Laufzeit lief — aus der
    Uhr gerechnet, nie mitgezählt (`core.takt.lage`): je zählendem Abschnitt des Timers von
    vorn (dort beginnt der Takt neu; ein Abschnitt mit eigenem Takt nimmt seinen), bei der
    Stoppuhr über die ganze Laufzeit. Eine Pause übt niemand — dort läuft der Takt, aber seine
    Runden zählen nicht in den Vorschlag. Das Ergebnis ist ein **Vorschlag** für die
    Wiederholungen, keine Messung (`takt_frage`).

    >>> from trainingsapp.core.takt import VORLAGEN
    >>> from trainingsapp.core.timer import Abschnitt
    >>> k = VORLAGEN["kniebeuge_2_1_2"]  # eine Runde dauert 5 s
    >>> takt_runden(stoppuhr(), k, 92.0), takt_runden(stoppuhr(), None, 92.0)
    (18, 0)
    >>> p = TimerProfil(abschnitte=[Abschnitt("Los", 20), Abschnitt("Pause", 10, zaehlt=False)],
    ...                 runden=2)
    >>> takt_runden(p, k, 60.0), takt_runden(p, k, 27.0)
    (8, 4)
    >>> from dataclasses import replace
    >>> takt_runden(stoppuhr(), replace(k, runden=10), 92.0)  # der Takt hört nach 10 auf
    10
    >>> schnell = TimerProfil(abschnitte=[Abschnitt("Los", 20, takt=VORLAGEN["metronom_1"])])
    >>> takt_runden(schnell, k, 20.0)  # der Abschnitt hat seinen eigenen Takt
    20
    """
    runden, anfang = 0, 0.0
    for *_, a in profil.folge():
        im_abschnitt = min(max(gelaufen_s - anfang, 0.0), float(a.dauer_s))
        anfang += a.dauer_s
        gilt = takt_waehlen(None, a.takt, takt)
        if gilt is None or not a.zaehlt or im_abschnitt <= 0:
            continue
        dauer = gilt.rundendauer_s
        if dauer <= 0:
            continue
        voll = int((im_abschnitt + 1e-6) // dauer)
        runden += min(voll, gilt.runden) if gilt.runden is not None else voll
    return runden


#: Was ein Lauf misst oder nur mitschreibt, gehört nie zur Ausführung — nach der **Art** des
#: Felds (`core.result_spec.basis_key`: auch ``hold_2``, ``scale_3``), nie nach dem Schlüssel …
_NICHT_AUSFUEHRUNG: Final[frozenset[str]] = frozenset(
    {"reps", "hold", "duration", "scale", "note", "done"}
)
#: … und, für Felder außerhalb des Vorrats (``seconds`` der Vorlage „Zeit als Benchmark“),
#: nach dem Typ: Sätze, Zeit, Skala, Text und Ja/Nein
_NICHT_AUSFUEHRUNG_TYPEN: Final[frozenset[FieldType]] = frozenset(
    {FieldType.SET_LIST, FieldType.DURATION, FieldType.SCALE, FieldType.TEXT, FieldType.BOOL}
)


def ist_ausfuehrung(feld: FieldSpec) -> bool:
    """Gehört das Feld zur **Ausführung** — sagt es, *wie* geübt wird, statt etwas zu messen?
    Alles außer Wiederholungen, Halte- und Zeitfeldern, Skala, Freitext und „Vollständig“:
    Variante, Seite, Winkel, Gewicht, Strecke.

    >>> [ist_ausfuehrung(vorrat_feld(k)) for k in ("side", "weight_2", "angle", "distance")]
    [True, True, True, True]
    >>> [ist_ausfuehrung(vorrat_feld(k)) for k in ("reps", "hold_2", "duration", "scale_3",
    ...                                            "note", "done")]
    [False, False, False, False, False, False]
    >>> ist_ausfuehrung(FieldSpec("seconds", FieldType.DURATION, "Zeit"))
    False
    """
    return (
        basis_key(feld.key) not in _NICHT_AUSFUEHRUNG and feld.type not in _NICHT_AUSFUEHRUNG_TYPEN
    )


def ausfuehrungsfelder(uebung: Exercise) -> list[FieldSpec]:
    """Die Felder der Übung, die ihre Ausführung beschreiben (`ist_ausfuehrung`) — die
    Variante zuerst, dann in der Ordnung des Vorrats (`core.result_spec.geordnet`).

    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "side", "scale")])
    >>> u = Exercise(result_spec=mit_varianten(spec, [Variante("auf Knien"), Variante("lang")]))
    >>> [f.key for f in ausfuehrungsfelder(u)]
    ['variant', 'side', 'weight']
    """
    felder = [f for f in uebung.result_spec.fields if ist_ausfuehrung(f)]
    return [
        *(f for f in felder if ist_variante(f)),
        *geordnet([f for f in felder if not ist_variante(f)]),
    ]


def _feld_der_ausfuehrung(uebung: Exercise, key: str, wert: Any = None) -> FieldSpec | None:
    """Das Feld ``key`` der Ausführung: wie die Übung es nennt — bietet sie es nicht an, aus
    dem Vorrat (eine Kopie; so macht es `eintrag` schon für Zeit und Skala), die Variante als
    Auswahl mit ``wert``. ``None``: kein Feld der Ausführung, oder niemand kennt es."""
    feld = uebung.result_spec.field_by_key(key)
    if feld is None and key == VARIANTE:
        feld = FieldSpec(
            VARIANTE, FieldType.CHOICE, VARIANTE_NAME, quick=[] if ist_leer(wert) else [wert]
        )
    elif feld is None and (vorlage := vorrat_feld(key)) is not None:
        feld = FieldSpec.from_dict(vorlage.to_dict())  # eine Kopie, nicht das Feld des Vorrats
    return feld if feld is not None and ist_ausfuehrung(feld) else None


@dataclass(frozen=True, slots=True)
class Ausfuehrung:
    """Die **Ausführung eines Tests** (`ausfuehrung_fuer`): was feststeht und was die Person
    vor dem Start wählt."""

    #: vorgegeben — Feld und Wert, vor dem Start nur zum Lesen
    fest: tuple[tuple[FieldSpec, Any], ...] = ()
    #: frei — die Felder, die die Person vor dem Start wählt …
    frei: tuple[FieldSpec, ...] = ()
    #: … und womit sie vorbelegt sind (der Standard der Übung): Feldschlüssel → Wert
    vorbelegt: Mapping[str, Any] = field(default_factory=dict)

    @property
    def leer(self) -> bool:
        """Der Test legt keine Ausführung fest und fragt keine."""
        return not self.fest and not self.frei

    @property
    def felder(self) -> list[FieldSpec]:
        """Alle Felder der Ausführung — erst die vorgegebenen, dann die freien."""
        return [*(f for f, _ in self.fest), *self.frei]

    def werte(self, wahl: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Die Ausführung, wie sie in den Eintrag kommt: das Vorgegebene, dazu in den freien
        Feldern die Wahl der Person (``None``: die Vorbelegung) — ohne Leeres."""
        gewaehlt = self.vorbelegt if wahl is None else wahl
        werte = {f.key: wert for f, wert in self.fest}
        for f in self.frei:
            if not ist_leer(wert := gewaehlt.get(f.key)):
                werte[f.key] = wert
        return werte

    def text(self, wahl: Mapping[str, Any] | None = None) -> str:
        """„auf Knien · beide · 10 kg“ — leer ohne Ausführung."""
        return ausfuehrung_text(self.werte(wahl), self.felder)


def ausfuehrung_fuer(block: Block, uebung: Exercise) -> Ausfuehrung:
    """Die Ausführung dieses Tests bei dieser Übung.

    - **Vorgegeben** ist `Block.ziel` — soweit es Felder der Ausführung nennt
      (`ist_ausfuehrung`) und einen Wert hat. Ein Feld, das die Übung nicht anbietet, kommt
      aus dem Vorrat; was weder sie noch der Vorrat kennt, fällt weg.
    - **Frei** sind `Block.felder` und, „wie die Übung“ (`WIE_PARAMETER`), alle Felder ihrer
      Ausführung — ohne die vorgegebenen (eine eigene Angabe im Test geht vor). Die Variante
      nur, wenn die Übung Varianten hat.
    - **Vorbelegt** sind die freien mit dem Standard der Übung: ihrem Ziel
      (`Exercise.default_target`), sonst der Vorgabe des Felds — eine Auswahl nur mit einem
      Wert, den sie anbietet.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "side")])
    >>> spec = mit_varianten(spec, [Variante("auf Knien"), Variante("gestreckt")])
    >>> kaefer = Exercise(name="Käfer", result_spec=spec, default_target={"weight": 10})
    >>> a = ausfuehrung_fuer(Block(TEST, uebung="k", ziel={"side": "links", "reps": [12]},
    ...                            felder=["weight"]), kaefer)
    >>> [(f.key, w) for f, w in a.fest], [f.key for f in a.frei], dict(a.vorbelegt)
    ([('side', 'links')], ['weight'], {'weight': 10})
    >>> a.werte(), a.werte({"weight": 12.5})
    ({'side': 'links', 'weight': 10}, {'side': 'links', 'weight': 12.5})
    >>> a.werte({}), a.text()  # ausdrücklich nichts gewählt: nur das Vorgegebene
    ({'side': 'links'}, 'links · 10 kg')
    >>> alle = ausfuehrung_fuer(Block(TEST, uebung="k", ziel={"side": "beide"},
    ...                               wie_uebung=["parameter"]), kaefer)
    >>> [f.key for f in alle.frei]  # „wie die Übung“: alles, was nicht vorgegeben ist
    ['variant', 'weight']

    Ein Feld, das die Übung nicht hat, kommt aus dem Vorrat — die Übung ändert sich nicht:

    >>> planke = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> b = ausfuehrung_fuer(Block(TEST, uebung="p", ziel={"angle": 90, "tanz": 3},
    ...                            felder=["side", "variant"]), planke)
    >>> [(f.label, w) for f, w in b.fest], [(f.key, f.quick) for f in b.frei], b.text()
    ([('Winkel', 90)], [('side', ['links', 'rechts', 'beide'])], '90°')
    >>> ausfuehrung_fuer(Block(TEST, uebung="p", vorgabe=Vorgabe(ZEIT, 60)), planke).leer
    True
    """
    fest: list[tuple[FieldSpec, Any]] = []
    for key, wert in block.ziel.items():
        feld = _feld_der_ausfuehrung(uebung, key, wert)
        if feld is not None and not ist_leer(wert) and not isinstance(wert, list | dict):
            fest.append((feld, wert))
    vorgegeben = {f.key for f, _ in fest}
    schluessel = list(block.felder or [])
    if WIE_PARAMETER in block.wie_uebung:
        schluessel += [f.key for f in ausfuehrungsfelder(uebung)]
    frei: list[FieldSpec] = []
    for key in dict.fromkeys(schluessel):
        if key in vorgegeben:
            continue
        if key == VARIANTE and uebung.result_spec.field_by_key(key) is None:
            continue  # ohne Varianten der Übung gibt es nichts zu wählen
        if (feld := _feld_der_ausfuehrung(uebung, key)) is not None:
            frei.append(feld)
    frei = [
        *(f for f in frei if ist_variante(f)),
        *geordnet([f for f in frei if not ist_variante(f)]),
    ]
    vorbelegt: dict[str, Any] = {}
    for f in frei:
        wert = uebung.default_target.get(f.key)
        if ist_leer(wert):
            wert = f.default
        if ist_leer(wert) or isinstance(wert, list | dict):
            continue
        if f.type == FieldType.CHOICE and wert not in f.quick:
            continue
        vorbelegt[f.key] = wert
    return Ausfuehrung(tuple(fest), tuple(frei), vorbelegt)


def timer_name(profil: TimerProfil) -> str:
    """Der **eigene** Name eines Timers — leer, wenn er nur den Standardnamen „Timer“ trägt
    (so heißt im Kurs-Editor jeder Timer, dem niemand einen Namen gab): Den nennt kein Text.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> timer_name(TimerProfil(name="Tabata", abschnitte=[Abschnitt("Los", 20)]))
    'Tabata'
    >>> timer_name(TimerProfil(abschnitte=[Abschnitt("Los", 20)])), timer_name(stoppuhr())
    ('', '')
    """
    name = profil.name.strip()
    return "" if name == _TIMER_OHNE_NAMEN else name


def timer_text(profil: TimerProfil) -> str:
    """Der Timer in einer Zeile: sein Name und wie lange er läuft — ohne eigenen Namen
    (`timer_name`) nur die Zeit.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> abschnitte = [Abschnitt("Los", 20), Abschnitt("Pause", 10)]
    >>> timer_text(TimerProfil(name="Tabata", abschnitte=abschnitte, runden=8))
    'Tabata · 4:00'
    >>> timer_text(TimerProfil(abschnitte=abschnitte, runden=8))
    '4:00'
    """
    zeit = dauer_text(profil.gesamt_s())
    return f"{name} · {zeit}" if (name := timer_name(profil)) else zeit


def takt_text(takt: Takt) -> str:
    """Der Takt in einer Zeile: seine Rate und seine Phasen mit ihren Sekunden.

    >>> from trainingsapp.core.takt import VORLAGEN
    >>> takt_text(VORLAGEN["kniebeuge_2_1_2"]), takt_text(VORLAGEN["metronom_1"])
    ('12,0/min · 2 s ab, 1 s halten, 2 s auf', '60,0/min · 1 s Schlag')
    """
    phasen = ", ".join(
        f"{takt_dauer(takt.dauer_s(k))} s {p.anzeigename}" for k, p in enumerate(takt.phasen)
    )
    return f"{rate_text(takt.rate_pro_min)} · {phasen}"


def takt_frage(runden: int) -> str:
    """Der Vorschlag aus dem Takt im Ergebnis — eine Frage, keine Messung: Die Person
    bestätigt die Zahl oder ändert sie.

    >>> takt_frage(23), takt_frage(1)
    ('Der Takt lief 23 Runden. Stimmt die Zahl?', 'Der Takt lief 1 Runde. Stimmt die Zahl?')
    """
    return f"Der Takt lief {runden} {'Runde' if runden == 1 else 'Runden'}. Stimmt die Zahl?"


def karten_ueberschrift(
    block: Block, name: str, uebung: Exercise | None = None, skala: str = ""
) -> str:
    """Die **Überschrift der Testkarte** eines Tests, der als Lauf gemacht wird und keine
    eigene Aufforderung hat (`Block.titel`): „Käfer: bis Anstrengung 7“ — mit der Vorgabe, die
    im Lauf **gilt** (`vorgabe_fuer`: neben einem Timer keine „Zeit“). Gilt keine, die Frage
    wie beim Test ohne Lauf: „Käfer: was schaffst du?“ (`OHNE_VORGABE`). Eine Stelle für die
    Karte im Kapitel (`ui/components/kursblock.py`) und die Vorschau im Kurs-Editor.

    ``name``: was vor dem Doppelpunkt steht — die Übung, „Deine Auswahl“, „Übung fehlt“.
    ``uebung``: die eine Übung des Tests, wenn es sie gibt — ihr Timer entscheidet mit („wie
    die Übung“), ihre Skala gibt den Namen. ``skala``: wie die Skala heißt, wenn nicht wie
    die der Übung (mehrere Übungen).

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.timer import Abschnitt
    >>> karten_ueberschrift(Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, 7)), "Käfer")
    'Käfer: bis Anstrengung 7'
    >>> karten_ueberschrift(Block(TEST, aus="a", ziel={"side": "links"}), "Deine Auswahl")
    'Deine Auswahl: was schaffst du?'
    >>> timer = TimerProfil(abschnitte=[Abschnitt("Los", 90)])
    >>> zeit = Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60))
    >>> karten_ueberschrift(zeit, "Käfer"), karten_ueberschrift(zeit, "Käfer", skala="Schwere")
    ('Käfer: 1 Minute', 'Käfer: 1 Minute')
    >>> karten_ueberschrift(Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60),
    ...                           timer=timer.als_dict()), "Käfer")  # der Timer ist die Zeit
    'Käfer: was schaffst du?'
    >>> mit_timer = Exercise(timer=[timer.als_dict()])
    >>> wie_uebung = Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60), wie_uebung=["uhr"])
    >>> karten_ueberschrift(wie_uebung, "Käfer", mit_timer), karten_ueberschrift(wie_uebung, "?")
    ('Käfer: was schaffst du?', '?: 1 Minute')
    >>> schwer = Exercise(result_spec=ResultSpec(fields=[replace(vorrat_feld("scale"),
    ...                                                           label="Schwere")]))
    >>> karten_ueberschrift(Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, 7)), "Käfer", schwer)
    'Käfer: bis Schwere 7'
    """
    vorgabe = vorgabe_fuer(block, uhr_fuer(block, uebung))
    if vorgabe is None:
        return f"{name}: {OHNE_VORGABE}"
    wie = skala or (skala_name(uebung.result_spec) if uebung is not None else SKALA_NAME)
    return f"{name}: {vorgabe_text(vorgabe, wie, satzanfang=False)}"


def _aufzaehlung(namen: list[str]) -> str:
    """„Seite“, „Seite und Gewicht“, „Variante, Seite und Gewicht“."""
    return namen[0] if len(namen) == 1 else f"{', '.join(namen[:-1])} und {namen[-1]}"


def lauf_satz(block: Block, uebung: Exercise | None = None) -> str:
    """**Wie der Test läuft** — für die Testkarte im Kapitel: womit (Timer), in welchem Takt,
    in welcher Ausführung und was die Person vor dem Start wählt. Leer, wenn der Test nichts
    davon gestaltet (Stoppuhr, kein Takt, keine Ausführung). Ohne ``uebung`` (ein Test „der
    gewählten“ vor der Wahl, oder mit mehreren Gewählten) steht, was erst die Übung sagt, als
    „… der Übung“.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> from trainingsapp.core.takt import VORLAGEN
    >>> from trainingsapp.core.timer import Abschnitt
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "side")])
    >>> kaefer = Exercise(name="Käfer", result_spec=spec, takt=VORLAGEN["kniebeuge_2_1_2"])
    >>> lauf_satz(Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, 7)), kaefer)
    ''
    >>> timer = TimerProfil(name="Tabata", abschnitte=[Abschnitt("Los", 20),
    ...                     Abschnitt("Pause", 10)], runden=8)
    >>> test = Block(TEST, uebung="k", timer=timer.als_dict(), wie_uebung=["takt"],
    ...              ziel={"side": "links"}, felder=["weight"])
    >>> lauf_satz(test, kaefer)  # doctest: +NORMALIZE_WHITESPACE
    'Läuft mit dem Timer „Tabata“ (4:00) und im Takt Kniebeuge 2-1-2. Ausführung: links.
     Gewicht wählst du vor dem Start.'
    >>> lauf_satz(Block(TEST, aus="wahl", wie_uebung=["uhr", "takt", "parameter"]))
    'Läuft mit dem Timer der Übung und in ihrem Takt. Die Ausführung wählst du vor dem Start.'

    Ein Timer ohne eigenen Namen (`timer_name`) wird nicht beim Namen genannt — nur seine Zeit:

    >>> lauf_satz(Block(TEST, uebung="k", timer={**timer.als_dict(), "name": "Timer"}), kaefer)
    'Läuft mit einem Timer (4:00).'
    """
    wie: list[str] = []
    profil = uhr_fuer(block, uebung)
    if not profil.ist_stoppuhr:
        zeit = dauer_text(profil.gesamt_s())
        name = timer_name(profil)
        wie.append(f"mit dem Timer „{name}“ ({zeit})" if name else f"mit einem Timer ({zeit})")
    elif uebung is None and WIE_UHR in block.wie_uebung:
        wie.append("mit dem Timer der Übung")
    takt = takt_fuer(block, uebung)
    if takt is not None:
        wie.append(f"im Takt {takt.anzeigename}")
    elif uebung is None and WIE_TAKT in block.wie_uebung:
        wie.append("in ihrem Takt" if wie and "der Übung" in wie[0] else "im Takt der Übung")
    saetze = [f"Läuft {' und '.join(wie)}."] if wie else []
    aus = ausfuehrung_fuer(block, uebung if uebung is not None else Exercise())
    if aus.fest:
        saetze.append(f"Ausführung: {ausfuehrung_text(dict(aus.werte({})), aus.felder)}.")
    if aus.frei:
        saetze.append(f"{_aufzaehlung([f.label for f in aus.frei])} wählst du vor dem Start.")
    elif uebung is None and WIE_PARAMETER in block.wie_uebung:
        saetze.append("Die Ausführung wählst du vor dem Start.")
    return " ".join(saetze)


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
    ausfuehrung: Mapping[str, Any] | None = None,
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

    ``ausfuehrung``: wie der Test gemacht wurde (`Ausfuehrung.werte`) — sie steht im Eintrag
    hinter dem Gemessenen; ein Feld, das die Übung nicht anbietet, bringt der Eintrag mit:

    >>> u, werte = eintrag(test, kaefer, wdh=22, sekunden=72, skala=None,
    ...                    ausfuehrung={"side": "links", "weight": 10, "reps": [5], "tanz": 1})
    >>> werte
    {'reps': [22], 'duration': 72, 'side': 'links', 'weight': 10}
    >>> [f.key for f in u.result_spec.fields]
    ['reps', 'duration', 'side', 'weight']
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
    # Die Ausführung: nur ihre Felder, und nichts, was der Lauf selbst misst
    wie: dict[str, Any] = {}
    for key, wert in (ausfuehrung or {}).items():
        if key in werte or ist_leer(wert):
            continue
        feld = _feld_der_ausfuehrung(mit, key, wert)
        if feld is None:
            continue
        if mit.result_spec.field_by_key(key) is None:
            spec = mit.result_spec
            mit = replace(mit, result_spec=replace(spec, fields=[*spec.fields, feld]))
        wie[key] = wert
    # in der Reihenfolge Wiederholungen · Zeit · Skala, wie die Karte sie nennt — dann, wie
    return mit, {**{k: werte[k] for k in (f.wdh, f.zeit, f.skala) if k and k in werte}, **wie}


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


def ausfuehrung_aus(result: Mapping[str, Any], spec: ResultSpec | None) -> str:
    """Wie ein Test gemacht wurde — die Ausführung aus seinem Eintrag, gelesen mit **seiner**
    Kopie der Felder (`ist_ausfuehrung`): „links · 10 kg“; leer ohne.

    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "side", "scale")])
    >>> ausfuehrung_aus({"reps": [22], "side": "links", "weight": 10, "scale": 7}, spec)
    'links · 10 kg'
    >>> ausfuehrung_aus({"reps": [22]}, spec), ausfuehrung_aus({"side": "links"}, None)
    ('', '')
    """
    felder = [
        *(f for f in (spec.fields if spec else ()) if ist_variante(f)),
        *geordnet([f for f in (spec.fields if spec else ()) if not ist_variante(f)]),
    ]
    felder = [f for f in felder if ist_ausfuehrung(f) and not ist_leer(result.get(f.key))]
    return ausfuehrung_text({f.key: result[f.key] for f in felder}, felder)


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


def herkunft(
    faktor: float,
    wert_text: str,
    v: Vorgabe | None,
    feld: str,
    skala: str = "",
    ausfuehrung: str = "",
    *,
    gewaehlt: Planwert | None = None,
    gewaehlt_text: str = "",
) -> str:
    """Woher ein Ziel aus dem Test kommt — die **Regel des Kurses**, ohne Wertung: „aus deinem
    Test“, mit Faktor „80 % von deinem Test (…)“, mit Vorgabe der gemessene Wert dazu.
    ``ausfuehrung``: wie der Test gemacht wurde (`ausfuehrung_aus`) — steht dahinter, damit
    der Wert nicht ohne sie gelesen wird (22 Wiederholungen **mit 10 kg**; Skizze F4).

    ``gewaehlt``: Die Person hat den **Wert für den Plan** selbst gewählt (W3, Ben
    17.11.2026) — dann nennt der Satz ihre Wahl statt der Regel des Kurses, der Test steht
    dahinter. ``gewaehlt_text``: ihr Wert in Worten („20 Wdh.“), nur für „von Hand“.

    >>> herkunft(1.0, "48 s", None, "hold")
    'aus deinem Test'
    >>> herkunft(0.8, "22 Wdh.", Vorgabe(SKALA, 7), "reps")
    '80 % von deinem Test (22 Wdh. bis Anstrengung 7)'
    >>> herkunft(1.0, "30 Wdh.", Vorgabe(MENGE, 30), "reps"), herkunft(0.8, "48 s", None, "hold")
    ('aus deinem Test (30 Wdh.)', '80 % von deinem Test (48 s)')
    >>> herkunft(0.8, "22 Wdh.", Vorgabe(SKALA, 7), "reps", ausfuehrung="links · 10 kg")
    '80 % von deinem Test (22 Wdh. bis Anstrengung 7 · links · 10 kg)'
    >>> herkunft(1.0, "48 s", None, "hold", ausfuehrung="links")
    'aus deinem Test (48 s · links)'

    Mit der Wahl der Person — von Hand, ein anderer Anteil, ganz:

    >>> from trainingsapp.core.kursbloecke import GANZ, planwert
    >>> bis7 = Vorgabe(SKALA, 7)
    >>> herkunft(0.8, "22 Wdh.", bis7, "reps", ausfuehrung="links · 10 kg",
    ...          gewaehlt=planwert(HAND, 22, hand=20), gewaehlt_text="20 Wdh.")
    'dein Wert von Hand (20 Wdh.) — Test: 22 Wdh. bis Anstrengung 7 · links · 10 kg'
    >>> herkunft(0.8, "22 Wdh.", bis7, "reps", gewaehlt=planwert(ANTEIL, 22, anteil=0.9))
    '90 % von deinem Test (22 Wdh. bis Anstrengung 7)'
    >>> herkunft(0.8, "22 Wdh.", None, "reps", gewaehlt=planwert(GANZ, 22))
    'dein Test, ganz (22 Wdh.)'
    """
    dazu = anhang(v, feld, skala or SKALA_NAME) if v is not None else ""
    kern = " ".join(t for t in (wert_text, dazu) if t)
    klammer = " · ".join(t for t in (kern, ausfuehrung) if t)
    if gewaehlt is not None:
        if gewaehlt.wie == HAND:
            return f"dein Wert von Hand ({gewaehlt_text or f'{gewaehlt.wert:g}'}) — Test: {klammer}"
        if gewaehlt.wie == ANTEIL:
            return f"{round((gewaehlt.anteil or 1.0) * 100)} % von deinem Test ({klammer})"
        return f"dein Test, ganz ({klammer})"
    anteil = "aus deinem Test" if faktor == 1.0 else f"{round(faktor * 100)} % von deinem Test"
    if v is None and faktor == 1.0 and not ausfuehrung:
        return anteil
    return f"{anteil} ({klammer})"


# -- Wert für den Plan (W3, Ben 17.11.2026; `docs/plan_kurs_ablauf.md` §17) --------------------
#
# Die Karte „Wert für den Plan“ (`ui/components/planwert.py`) zeichnet nur: Schritt, Text im
# Feld, Lesen der Eingabe und die Sätze stehen hier; was aus der Wahl wird, rechnet
# `core.kursbloecke.planwert`.


def zeitfeld(feld: FieldSpec) -> bool:
    """Hält das Feld eine Zeit (Sekunden)? Dann wird sie als „1:30“ getippt und gezeigt.

    >>> zeitfeld(vorrat_feld("hold")), zeitfeld(vorrat_feld("reps"))
    (True, False)
    """
    return feld.unit == "s" or feld.type == FieldType.DURATION


def hand_schritt(feld: FieldSpec) -> int:
    """Der Schritt von − und + bei „Von Hand“: eine Zeit in 5 Sekunden, sonst 1.

    >>> hand_schritt(vorrat_feld("reps")), hand_schritt(vorrat_feld("hold"))
    (1, 5)
    """
    return 5 if zeitfeld(feld) else 1


def hand_weiter(feld: FieldSpec, wert: float, richtung: int) -> float:
    """Die nächste Zahl mit − oder + bei „Von Hand“: auf das Raster des Schritts, nie unter
    einem Schritt.

    >>> reps, hold = vorrat_feld("reps"), vorrat_feld("hold")
    >>> hand_weiter(reps, 18, 1), hand_weiter(reps, 1, -1)
    (19.0, 1.0)
    >>> hand_weiter(hold, 47, 1), hand_weiter(hold, 47, -1), hand_weiter(hold, 45, -1)
    (50.0, 45.0, 40.0)
    """
    schritt = hand_schritt(feld)
    stufe = wert / schritt
    naechste = math.floor(stufe) + 1 if richtung > 0 else math.ceil(stufe) - 1
    return float(max(naechste, 1) * schritt)


def hand_text(feld: FieldSpec, wert: float) -> str:
    """Die Zahl, wie sie im Feld „Von Hand“ steht — eine Zeit als ``m:ss`` (nur Ziffern und
    Doppelpunkt: so lässt sie sich mit der Zahlentastatur ändern), sonst die Zahl. `hand_lesen`
    liest sie zurück.

    >>> hand_text(vorrat_feld("reps"), 18.0), hand_text(vorrat_feld("hold"), 90)
    ('18', '1:30')
    >>> hand_text(vorrat_feld("hold"), 40), hand_lesen(vorrat_feld("hold"), "0:40")
    ('0:40', 40.0)
    """
    return dauer_text(wert) if zeitfeld(feld) else f"{wert:g}"


def hand_lesen(feld: FieldSpec, text: str) -> float | None:
    """Die Eingabe im Feld „Von Hand“ als Zahl in der Einheit des Felds — ``None``, wenn sie
    sich nicht lesen lässt oder nicht über 0 liegt. Eine Zeit wie überall (`parse_dauer`:
    „45“, „1:30“, „90s“), sonst eine Zahl (auch mit Komma), auf ganze Einheiten.

    >>> reps, hold = vorrat_feld("reps"), vorrat_feld("hold")
    >>> hand_lesen(reps, " 20 "), hand_lesen(reps, "7,6"), hand_lesen(hold, "1:30")
    (20.0, 8.0, 90.0)
    >>> hand_lesen(reps, ""), hand_lesen(reps, "0"), hand_lesen(reps, "viel"), hand_lesen(hold, "x")
    (None, None, None, None)
    """
    roh = text.strip()
    if zeitfeld(feld):
        wert = parse_dauer(roh)
    else:
        try:
            wert = float(roh.replace(",", "."))
        except ValueError:
            return None
    if wert is None or not math.isfinite(wert) or round(wert) < 1 or wert > 99999:
        return None
    return float(round(wert))


def hand_einheit(feld: FieldSpec) -> str:
    """Was hinter dem Feld „Von Hand“ steht: die Einheit — bei einer Zeit der Name des Felds.

    >>> hand_einheit(vorrat_feld("reps")), hand_einheit(vorrat_feld("hold"))
    ('Wdh.', 'Haltezeit')
    """
    return feld.label if zeitfeld(feld) else (feld.unit or feld.label)


def planwert_satz(feld: FieldSpec, wert: float) -> str:
    """Der eine Satz der Karte: welche Zahl der Plan nimmt — ohne Wertung.

    >>> planwert_satz(vorrat_feld("reps"), 18), planwert_satz(vorrat_feld("hold"), 90)
    ('Der Plan nimmt 18 Wdh.', 'Der Plan nimmt 1:30 Haltezeit.')
    """
    text = menge_text(feld, wert)
    return f"Der Plan nimmt {text}" if text.endswith(".") else f"Der Plan nimmt {text}."


def wahl_text(gewaehlt: Planwert) -> str:
    """Die Wahl in einem Wort — hinter dem Wert für den Plan in der Testkarte.

    >>> from trainingsapp.core.kursbloecke import GANZ, planwert
    >>> [wahl_text(planwert(w, 22, anteil=0.9, hand=20)) for w in (GANZ, ANTEIL, HAND)]
    ['ganz', '90 %', 'von Hand']
    """
    if gewaehlt.wie == HAND:
        return "von Hand"
    if gewaehlt.wie == ANTEIL:
        return f"{round((gewaehlt.anteil or 1.0) * 100)} %"
    return "ganz"


def wert_jetzt(
    block: Block, uebung: Exercise, *, wdh: int | None, sekunden: float, skala: int | None
) -> float | None:
    """Der Wert, den der Test hinterließe, wenn jetzt eingetragen würde — das Feld des Tests
    im Eintrag (`eintrag`); ``None``, solange er fehlt (`fehlt`). Die Ergebnis-Seite rechnet
    damit den Wert für den Plan, bevor „Eintragen“ gedrückt ist.

    >>> from trainingsapp.core.kursbloecke import TEST
    >>> kaefer = Exercise(name="Käfer", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> test = Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7))
    >>> wert_jetzt(test, kaefer, wdh=22, sekunden=72, skala=7)
    22.0
    >>> wert_jetzt(test, kaefer, wdh=None, sekunden=72, skala=7) is None
    True
    """
    _, werte = eintrag(block, uebung, wdh=wdh, sekunden=sekunden, skala=skala)
    wert = wert_im_test(werte, block.feld)
    return float(wert) if wert is not None and wert > 0 else None


# -- Der Lauf auf der Teilnehmer-Seite: Anzeige, Ende, Ergebnis (Stufe 2, 16.11.2026) ---------
#
# Die Ansicht `ui/views/kurs_testlauf.py` zeichnet nur; was sie zeigt und wann „Eintragen“ geht,
# steht hier.

#: Woher eine Größe im Ergebnis kommt (`woher_wdh`, `woher_zeit`) …
VORGEGEBEN: Final = "vorgabe"
VON_DER_UHR: Final = "uhr"
VOM_TIMER: Final = "timer"
GEZAEHLT: Final = "gezaehlt"
GEFRAGT: Final = "gefragt"
#: Die Runden des Takts als Vorschlag — gefragt wie `GEFRAGT`, nur vorbelegt (`takt_frage`)
VOM_TAKT: Final = "takt"
#: … und wie das unter ihrem Namen steht („Wiederholungen — die Vorgabe“)
WOHER: Final[dict[str, str]] = {
    VORGEGEBEN: "die Vorgabe",
    VON_DER_UHR: "von der Uhr",
    VOM_TIMER: "vom Timer",
    GEZAEHLT: "gezählt",
    GEFRAGT: "sagst du",
    VOM_TAKT: "Vorschlag aus dem Takt",
}


def kopf(
    v: Vorgabe | None, timer: TimerProfil | None = None, skala: str = SKALA_NAME
) -> tuple[str, str]:
    """Was über dem Lauf steht: klein, was es ist, und groß der Inhalt — die Vorgabe, ohne
    sie der Timer, ohne beides die Aufforderung der Testkarte.

    >>> kopf(Vorgabe(SKALA, 7)), kopf(None)
    (('Vorgabe', 'Bis Anstrengung 7'), ('Test', 'Was schaffst du?'))
    >>> from trainingsapp.core.timer import Abschnitt
    >>> tabata = TimerProfil(name="Tabata", abschnitte=[Abschnitt("Los", 240)])
    >>> kopf(None, tabata), kopf(Vorgabe(ZEIT, 60), tabata), kopf(Vorgabe(MENGE, 30), tabata)
    (('Timer', 'Tabata · 4:00'), ('Timer', 'Tabata · 4:00'), ('Vorgabe', '30 Wiederholungen'))
    >>> kopf(None, TimerProfil(abschnitte=[Abschnitt("Los", 240)]))  # ohne eigenen Namen
    ('Timer', '4:00')
    """
    v = _gilt(v, timer)
    if v is not None:
        return "Vorgabe", vorgabe_text(v, skala)
    lauf = _mit_timer(timer)
    if lauf is not None:
        return "Timer", timer_text(lauf)
    return "Test", OHNE_VORGABE[0].upper() + OHNE_VORGABE[1:]


def zeit_anzeige(v: Vorgabe | None, gelaufen_s: float) -> str:
    """Die große Zeit im Lauf mit der Stoppuhr: was gelaufen ist (abgerundet, wie die
    Stoppuhr) — bei einer Zeit als Vorgabe der Rest bis 0 (aufgerundet, wie der Timer). Läuft
    der Test mit einem Timer, zeigt der seine Zeit selbst (`TimerLauf.anzeige`).

    >>> zeit_anzeige(Vorgabe(MENGE, 30), 42.7), zeit_anzeige(Vorgabe(ZEIT, 60), 42.7)
    ('0:42', '0:18')
    >>> zeit_anzeige(Vorgabe(ZEIT, 60), 75), zeit_anzeige(Vorgabe(SKALA, 7), 72.0)
    ('0:00', '1:12')
    >>> zeit_anzeige(None, 72.9)
    '1:12'
    """
    if v is not None and v.art == ZEIT:
        return dauer_text(math.ceil(max(v.n - gelaufen_s, 0.0)))
    return dauer_text(int(max(gelaufen_s, 0.0)))


def zeit_zeile(v: Vorgabe | None, *, timer: TimerProfil | None = None) -> str:
    """Die Zeile unter der großen Zeit: Die Zeit wird gemessen — oder sie ist die Vorgabe
    bzw. die des Timers und endet von selbst.

    >>> zeit_zeile(Vorgabe(MENGE, 30)), zeit_zeile(Vorgabe(ZEIT, 60)), zeit_zeile(None)
    ('Zeit läuft · wird gemessen', 'Zeit läuft · endet von selbst', 'Zeit läuft · wird gemessen')
    >>> from trainingsapp.core.timer import Abschnitt
    >>> zeit_zeile(Vorgabe(SKALA, 7), timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    'Timer läuft · endet von selbst'
    """
    if _mit_timer(timer) is not None:
        return "Timer läuft · endet von selbst"
    if v is not None and v.art == ZEIT:
        return "Zeit läuft · endet von selbst"
    return "Zeit läuft · wird gemessen"


def abschnitt_text(stand: TimerStand) -> str:
    """Wo der Timer des Tests steht: der Abschnitt, bei mehreren Runden die Runde, und ob er
    nicht zählt.

    >>> abschnitt_text(TimerStand(2, 0, "Los", 20, 12.0, 100.0, True, False, runden=8))
    'Los · Runde 2 von 8'
    >>> abschnitt_text(TimerStand(1, 1, "Pause", 10, 4.0, 4.0, True, False, zaehlt=False))
    'Pause · zählt nicht'
    >>> abschnitt_text(TimerStand(1, 0, "Los", 20, 0.0, 0.0, False, True))
    'Timer durch'
    """
    if stand.fertig:
        return "Timer durch"
    teile = [stand.name or f"Abschnitt {stand.index + 1}"]
    if stand.runden > 1:
        teile.append(f"Runde {stand.runde} von {stand.runden}")
    if not stand.zaehlt:
        teile.append("zählt nicht")
    return " · ".join(teile)


def danach_text(profil: TimerProfil, nummer: int) -> str:
    """Was nach dem Abschnitt mit der laufenden Nummer ``nummer`` kommt (`TimerStand.nummer`)
    — leer nach dem letzten.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> p = TimerProfil(abschnitte=[Abschnitt("Los", 20), Abschnitt("Pause", 10)], runden=2)
    >>> danach_text(p, 0), danach_text(p, 1), danach_text(p, 3), danach_text(p, 4)
    ('danach Pause 0:10', 'danach Los 0:20', '', '')
    """
    folge = profil.folge()
    if not 0 <= nummer + 1 < len(folge):
        return ""
    naechster = folge[nummer + 1][3]
    return f"danach {naechster.name or 'Abschnitt'} {dauer_text(naechster.dauer_s)}"


def zaehl_text(v: Vorgabe | None, wer: str = "") -> tuple[str, str]:
    """Die Karte „Wiederholungen“ im Lauf — wer zählt, und was daraus folgt. ``wer``: „Sensor“
    (`core.zaehlen.quelle_name`), leer = die Person. Ein Takt zählt im Test nie — er hat seine
    eigene Karte.

    >>> zaehl_text(Vorgabe(MENGE, 30))
    ('Du zählst selbst', 'Bei 30 tippst du „Fertig“ — die Uhr hält an.')
    >>> zaehl_text(Vorgabe(MENGE, 30), "Sensor")
    ('Sensor zählt', 'Bei 30 hält die Uhr von selbst an.')
    >>> zaehl_text(Vorgabe(ZEIT, 60)), zaehl_text(Vorgabe(SKALA, 7), "Sensor")
    (('Du zählst selbst', 'Wie viele es waren, sagst du danach.'), ('Sensor zählt', ''))
    >>> zaehl_text(None)
    ('Du zählst selbst', 'Wie viele es waren, sagst du danach.')
    """
    menge = v.n if v is not None and v.art == MENGE else None
    if wer:
        return f"{wer} zählt", f"Bei {menge} hält die Uhr von selbst an." if menge else ""
    if menge:
        return "Du zählst selbst", f"Bei {menge} tippst du „Fertig“ — die Uhr hält an."
    return "Du zählst selbst", "Wie viele es waren, sagst du danach."


def unten_text(v: Vorgabe | None, *, timer: TimerProfil | None = None, takt: bool = False) -> str:
    """Der kleine Satz unter den Knöpfen im Lauf. ``takt``: Ein Takt läuft mit — er hält mit
    der Uhr an.

    >>> unten_text(Vorgabe(MENGE, 30)), unten_text(Vorgabe(SKALA, 7))
    ('„Vorher aufgehört“ fragt, wie viele es waren.', 'Ein Tipp hält die Uhr an.')
    >>> unten_text(Vorgabe(ZEIT, 60)), unten_text(None)
    ('Bei 0 hält die Uhr von selbst an.', 'Ein Tipp hält die Uhr an.')
    >>> unten_text(Vorgabe(SKALA, 7), takt=True)
    'Ein Tipp hält Uhr und Takt an. Danach sagst du, wie viele es waren.'
    >>> from trainingsapp.core.timer import Abschnitt
    >>> unten_text(None, timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    'Ist der Timer durch, hält die Uhr von selbst an.'
    """
    v = _gilt(v, timer)
    if v is not None and v.art == MENGE:
        return "„Vorher aufgehört“ fragt, wie viele es waren."
    if v is not None and v.art == ZEIT:
        return "Bei 0 hält die Uhr von selbst an."
    if v is None and _mit_timer(timer) is not None:
        return "Ist der Timer durch, hält die Uhr von selbst an."
    if takt:
        return "Ein Tipp hält Uhr und Takt an. Danach sagst du, wie viele es waren."
    return "Ein Tipp hält die Uhr an."


@dataclass(frozen=True, slots=True)
class Marke:
    """Die Marke auf dem Balken 1–10 der Anstrengung: die Stufen ``von`` bis ``bis`` und, was
    darunter steht."""

    von: int
    bis: int
    text: str


def marke(v: Vorgabe | None) -> Marke | None:
    """Wo die **Regel des Kurses** auf dem Balken der Anstrengung liegt — ``None``, wenn die
    Vorgabe keine Skala ist. Die App nennt die Regel; wie es sich anfühlt, sagt die Person.

    >>> marke(Vorgabe(SKALA, 7))
    Marke(von=7, bis=7, text='7 · hier ist Schluss')
    >>> marke(Vorgabe(SKALA, bis=4)), marke(Vorgabe(SKALA, 5, 7))
    (Marke(von=4, bis=4, text='4 · bis hier'), Marke(von=5, bis=7, text='5 bis 7 · dein Bereich'))
    >>> marke(Vorgabe(MENGE, 30)) is None, marke(None) is None
    (True, True)
    """
    if v is None or v.art != SKALA:
        return None
    if v.bis is None:
        return Marke(v.n, v.n, f"{v.n} · hier ist Schluss")
    if v.n <= 0:
        return Marke(v.bis, v.bis, f"{v.bis} · bis hier")
    return Marke(v.n, v.bis, f"{v.n} bis {v.bis} · dein Bereich")


def am_ende(
    v: Vorgabe | None,
    f: Felder,
    *,
    gelaufen_s: float,
    vorher: bool = False,
    gezaehlt: int | None = None,
    takt_runden: int | None = None,
) -> tuple[int | None, float, int | None]:
    """Was mit dem Ende des Laufs feststeht — Wiederholungen, Sekunden, Skala. ``None`` heißt:
    danach fragen (Wiederholungen nur, wenn die Übung welche hat, `Felder.wdh`). ``vorher``:
    die Vorgabe ist nicht erreicht („Vorher aufgehört“, oder der Timer war eher durch) — es
    gilt, was gemessen wurde; ``gezaehlt``: was der Sensor zählte (dann fragt niemand);
    ``gelaufen_s``: die Zeit des Tests (`gezaehlte_zeit`).

    ``takt_runden``: Ein Takt lief mit (`takt_runden`). Hat niemand gezählt und gibt die
    Vorgabe die Wiederholungen nicht her, stehen seine Runden als **Vorschlag** da — die
    Person bestätigt oder ändert sie (`woher_wdh` → `VOM_TAKT`); gemessen ist damit nichts.

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
    >>> am_ende(None, kaefer, gelaufen_s=48.0), am_ende(None, kaefer, gelaufen_s=48.0, gezaehlt=9)
    ((None, 48.0, None), (9, 48.0, None))
    >>> am_ende(Vorgabe(SKALA, 7), kaefer, gelaufen_s=92.0, takt_runden=23)
    (23, 92.0, 7)
    >>> am_ende(Vorgabe(MENGE, 30), kaefer, gelaufen_s=92.0, takt_runden=23)  # die Vorgabe gilt
    (30, 92.0, None)
    >>> am_ende(Vorgabe(SKALA, 7), kaefer, gelaufen_s=92.0, gezaehlt=21, takt_runden=23)
    (21, 92.0, 7)
    >>> am_ende(None, Felder(None, "hold", "scale"), gelaufen_s=3.0, takt_runden=0)
    (None, 3.0, None)
    """
    wdh: int | None = None
    if f.wdh is not None:
        if gezaehlt is not None:
            wdh = gezaehlt
        elif v is not None and v.art == MENGE and not vorher:
            wdh = v.n
        elif takt_runden:
            wdh = takt_runden
    sekunden = float(v.n) if v is not None and v.art == ZEIT and not vorher else gelaufen_s
    return wdh, sekunden, None if vorher else skala_am_ende(v)


def woher_wdh(
    v: Vorgabe | None,
    f: Felder,
    *,
    vorher: bool = False,
    gezaehlt: bool = False,
    takt: bool = False,
) -> str | None:
    """Woher die Wiederholungen im Ergebnis kommen (`WOHER`) — ``None``: Die Übung hat keine,
    die Zeile fällt weg. `GEFRAGT` heißt: ein Zahlenfeld; `VOM_TAKT`: dasselbe, vorbelegt mit
    den Runden des Takts (``takt``: er lief mindestens eine Runde).

    >>> kaefer = Felder("reps", "duration", "scale")
    >>> woher_wdh(Vorgabe(MENGE, 30), kaefer), woher_wdh(Vorgabe(MENGE, 30), kaefer, vorher=True)
    ('vorgabe', 'gefragt')
    >>> woher_wdh(Vorgabe(SKALA, 7), kaefer), woher_wdh(Vorgabe(ZEIT, 60), kaefer, gezaehlt=True)
    ('gefragt', 'gezaehlt')
    >>> woher_wdh(Vorgabe(ZEIT, 60), Felder(None, "hold", "scale")) is None
    True
    >>> woher_wdh(None, kaefer), woher_wdh(Vorgabe(SKALA, 7), kaefer, takt=True)
    ('gefragt', 'takt')
    >>> woher_wdh(Vorgabe(MENGE, 30), kaefer, takt=True), woher_wdh(None, kaefer, gezaehlt=True,
    ...                                                             takt=True)
    ('vorgabe', 'gezaehlt')
    """
    if f.wdh is None:
        return None
    if gezaehlt:
        return GEZAEHLT
    if v is not None and v.art == MENGE and not vorher:
        return VORGEGEBEN
    return VOM_TAKT if takt else GEFRAGT


def woher_zeit(v: Vorgabe | None, *, vorher: bool = False, timer: TimerProfil | None = None) -> str:
    """Woher die Zeit im Ergebnis kommt: von der Uhr — außer sie war die Vorgabe und ist
    abgelaufen. Mit einem Timer ist es seine Zeit (was in seinen zählenden Abschnitten lief).

    >>> woher_zeit(Vorgabe(ZEIT, 60)), woher_zeit(Vorgabe(ZEIT, 60), vorher=True)
    ('vorgabe', 'uhr')
    >>> woher_zeit(Vorgabe(MENGE, 30)), woher_zeit(None)
    ('uhr', 'uhr')
    >>> from trainingsapp.core.timer import Abschnitt
    >>> woher_zeit(None, timer=TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    'timer'
    """
    if _mit_timer(timer) is not None:
        return VOM_TIMER
    return VORGEGEBEN if v is not None and v.art == ZEIT and not vorher else VON_DER_UHR


def ende_text(v: Vorgabe | None, *, vorher: bool = False, durch: bool = False) -> str:
    """Wie der Lauf endete — die Zeile über dem Ergebnis. ``durch``: Der Timer lief durch;
    ``vorher``: die Vorgabe ist nicht erreicht.

    >>> ende_text(Vorgabe(SKALA, 7)), ende_text(Vorgabe(MENGE, 30)), ende_text(Vorgabe(ZEIT, 60))
    ('Bei 7 angekommen', '30 gemacht', 'Die Zeit ist ab')
    >>> ende_text(Vorgabe(SKALA, 7), vorher=True), ende_text(None), ende_text(None, durch=True)
    ('Vorher aufgehört', 'Fertig', 'Der Timer ist durch')
    >>> ende_text(Vorgabe(MENGE, 30), vorher=True, durch=True)
    'Der Timer ist durch'
    """
    if durch:
        return "Der Timer ist durch"
    if vorher:
        return "Vorher aufgehört"
    if v is None:
        return "Fertig"
    if v.art == MENGE:
        return f"{v.n} gemacht"
    if v.art == ZEIT:
        return "Die Zeit ist ab"
    return knopf_text(v)


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
    "OHNE_VORGABE",
    "SKALA_NAME",
    "VOM_TAKT",
    "VOM_TIMER",
    "VON_DER_UHR",
    "VORGEGEBEN",
    "WDH",
    "WOHER",
    "Ausfuehrung",
    "Felder",
    "Lauf",
    "Marke",
    "abschnitt_text",
    "am_ende",
    "anhang",
    "anleitung",
    "ausfuehrung_aus",
    "ausfuehrung_fuer",
    "ausfuehrungsfelder",
    "danach_text",
    "dauer_worte",
    "eintrag",
    "ende_text",
    "erreicht",
    "fehlt",
    "felder",
    "fuehrt_ein_takt",
    "gemessen",
    "gezaehlte_zeit",
    "hand_einheit",
    "hand_lesen",
    "hand_schritt",
    "hand_text",
    "hand_weiter",
    "herkunft",
    "ist_ausfuehrung",
    "karten_ueberschrift",
    "knopf_text",
    "kopf",
    "lauf_aus",
    "lauf_satz",
    "marke",
    "neben_text",
    "planwert_satz",
    "skala_am_ende",
    "skala_frage",
    "skala_name",
    "skala_stufen",
    "takt_frage",
    "takt_fuer",
    "takt_runden",
    "takt_text",
    "timer_name",
    "timer_text",
    "uhr_fuer",
    "unten_text",
    "verfehlt",
    "vorgabe_fuer",
    "vorgabe_text",
    "vorher_knopf",
    "wahl_text",
    "wert_jetzt",
    "woher_wdh",
    "woher_zeit",
    "zaehl_text",
    "zeit_anzeige",
    "zeit_zeile",
    "zeitfeld",
]
