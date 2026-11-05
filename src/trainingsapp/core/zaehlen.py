"""Wiederholungen zählen und Atmung erfassen mit dem Beschleunigungssensor — was die Übung
festlegt und wie die Zählzeile spricht.

Ben, 4.11.2026 (`docs/plan_beschleunigung.md` §3, §4, §12):

- `SensorWahl` — die Karte „Beschleunigungssensor“ an der Übung (Migration 037,
  ``exercise.acc_json``; Paketfeld ``beschleunigung``): ``wiederholungen`` und ``atmung``
  (``None`` = Vorgabe aus der Übung), ``vorlage`` (zuerst nur „Automatisch“, P126) und
  ``feld`` („Zählt in“ bei mehreren Wiederholungsfeldern). `wahl_pruefen` sagt, was
  `SensorWahl.aus_dict` still überläse (``trainingsapp-paket pruefen``).
- `wiederholungen_an`, `atmung_an` — ob an dieser Übung gezählt bzw. erfasst wird;
  `hat_wdh_feld`, `wdh_felder`, `zaehlt_in` — in welches Feld die Wiederholungen kommen.
  Gefragt wird nach der *Art* des Feldes (`core.result_spec.basis_key`), nie nach dem
  Schlüssel: ``reps_2`` ist auch ein Wiederholungsfeld (P106).
- `knopf_text`, `anzeige`, `korrektur_text`, `mit_vorzeichen` — Texte der Zählzeile. ±1 ist
  nur die Korrektur der Messung, kein Handzähler (P118). `rate_text`, `phase_pfeil`,
  `atem_text` — die Atmung in Worten („12/min ▲“, A3).
- `rate_waehlen` — die Rate, die das Zählen beim Gerät anfordert (P119b: Akku vor).
- Ende-Gründe ``ENDE_*`` (Zeitleiste, Art ``zaehlen_ende``) und die Grenzen
  ``KEINE_BEWEGUNG_S``, ``KEIN_ATEM_S``, ``KEINE_DATEN_S``, ``MIN_RATE_HZ``, ``BEREICH_G``.

Rein und ohne flet. Die Übung (`core.models.Exercise`) kennt das Modul nur als Typ: `models`
holt `SensorWahl` von hier, ein Import zur Laufzeit liefe im Kreis.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .result_spec import basis_key

if TYPE_CHECKING:
    from .models import Exercise, PlanItem

#: Bewegung „Automatisch“: die Hauptachse, wie der Prototyp in hrv-core heute zählt (P126).
#: Ein Schlüssel, den hrv-core (noch) nicht kennt, gilt beim Zählen als dieser.
VORLAGE_AUTO: Final = "auto"
#: Die Art eines Wiederholungsfeldes (``reps``, ``reps_2`` …)
WDH_ART: Final = "reps"
#: Der Typ, an dem „Atmung“ von selbst an ist
TYP_ATMUNG: Final = "Atmung"

#: Was gezählt wird (``zaehlart`` im Ereignis ``zaehlung``) — ``art`` ist schon ein Feld
#: des Ereignisses
ZAEHLART_WDH: Final = "wdh"
ZAEHLART_ATEM: Final = "atem"

#: Ende-Gründe des Zählens (``grund`` im Ereignis ``zaehlen_ende``, §4.3 Punkt 6)
ENDE_FERTIG: Final = "fertig"  # „Fertig“ am Zähler, Timer durch oder „Fertig“ der Uhr, ⏹
ENDE_ABGEHAKT: Final = "abgehakt"  # Übung abgehakt, „Gemacht“, „Wie geplant“
ENDE_ABBRUCH: Final = "abbruch"  # „Abbrechen“ am Zähler
ENDE_ANDERE_UEBUNG: Final = "andere_uebung"  # eine andere Übung startet Zählen oder Uhr
ENDE_KEINE_BEWEGUNG: Final = "keine_bewegung"  # KEINE_BEWEGUNG_S ohne neue Wiederholung
ENDE_KEIN_ATEM: Final = "kein_atem"  # nur Atmung: KEIN_ATEM_S ohne erkennbaren Atemzug
ENDE_GRUENDE: Final = (
    ENDE_FERTIG,
    ENDE_ABGEHAKT,
    ENDE_ABBRUCH,
    ENDE_ANDERE_UEBUNG,
    ENDE_KEINE_BEWEGUNG,
    ENDE_KEIN_ATEM,
)
#: Mit diesen Gründen kommt der Satzwert in den Eintrag; die übrigen sind **abgebrochen**
#: (nichts eingetragen, der Lauf bleibt unter „Läufe heute“ mit „Eintragen“).
EINGETRAGEN: Final = frozenset({ENDE_FERTIG, ENDE_ABGEHAKT})

#: So lange ohne neu gezählte Wiederholung, dann endet das Zählen (Startwert, Ben: „evtl. mit
#: Timer“ — reicht das bei langen Pausen im Satz nicht, wird er einstellbar)
KEINE_BEWEGUNG_S: Final = 60.0
#: Nur Atmung: so lange ohne erkennbaren Atemzug (abgelegt, verrutscht)
KEIN_ATEM_S: Final = 120.0
#: So lange ohne einen Rahmen der Beschleunigung (das Gerät liefert sie nicht — abgelehnt,
#: nicht erprobt —, oder der Strom bleibt aus), dann endet das Zählen als ``abbruch``: nicht
#: als „keine Bewegung“, denn bewegt hat sich vielleicht die Person, nur gemessen hat niemand
#: (Proben kommen ein bis zwei Sekunden nach dem Tipp, §4.3 Punkt 2)
KEINE_DATEN_S: Final = 15.0
#: Kleinste Rate, mit der gezählt wird (H10 50 Hz, Verity Sense 52 Hz)
MIN_RATE_HZ: Final = 50
#: Messbereich in g — Sprünge überschreiten 2 g
BEREICH_G: Final = 8


@dataclass(frozen=True)
class SensorWahl:
    """Die Karte „Beschleunigungssensor“ einer Übung (§3.1) — unveränderlich, weil
    `dataclasses.replace` beim Kopieren einer Übung nur flach kopiert.

    >>> w = SensorWahl(wiederholungen=False, atmung=True, feld="reps_2")
    >>> w.als_dict()
    {'wiederholungen': False, 'atmung': True, 'feld': 'reps_2'}
    >>> SensorWahl.aus_dict(w.als_dict()) == w
    True
    >>> SensorWahl().als_dict(), SensorWahl.aus_dict("kaputt") == SensorWahl()
    ({}, True)
    """

    #: Wiederholungen zählen — ``None``: an, wenn die Übung ein Feld der Art ``reps`` hat
    wiederholungen: bool | None = None
    #: Atmung erfassen — ``None``: an bei Typ „Atmung“
    atmung: bool | None = None
    #: Bewegung: Schlüssel einer Vorlage in hrv-core, zuerst nur ``auto`` (P126)
    vorlage: str = VORLAGE_AUTO
    #: „Zählt in“ (nur bei mehreren Wiederholungsfeldern) — ``None``: das erste
    feld: str | None = None

    def als_dict(self) -> dict[str, Any]:
        """Nur, was von der Vorgabe abweicht — nie ``None`` (TOML kennt es nicht).

        >>> SensorWahl(vorlage="auto", feld="").als_dict()
        {}
        >>> SensorWahl(vorlage="kniebeuge_x").als_dict()
        {'vorlage': 'kniebeuge_x'}
        """
        d: dict[str, Any] = {}
        if self.wiederholungen is not None:
            d["wiederholungen"] = self.wiederholungen
        if self.atmung is not None:
            d["atmung"] = self.atmung
        if self.vorlage and self.vorlage != VORLAGE_AUTO:
            d["vorlage"] = self.vorlage
        if self.feld:
            d["feld"] = self.feld
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> SensorWahl:
        """Defensiv: Unbrauchbares gilt als Vorgabe — Schalter nur als echte Wahrheitswerte,
        Texte nur als nicht leere Zeichenketten. Eine unbekannte Vorlage bleibt erhalten
        (neueres hrv-core), gezählt wird mit ihr wie mit „Automatisch“.

        >>> SensorWahl.aus_dict({"wiederholungen": "ja", "atmung": 1, "vorlage": 3, "feld": ""})
        SensorWahl(wiederholungen=None, atmung=None, vorlage='auto', feld=None)
        >>> SensorWahl.aus_dict({"atmung": False, "vorlage": " neigung_zy ", "x": 1})
        SensorWahl(wiederholungen=None, atmung=False, vorlage='neigung_zy', feld=None)
        """
        if not isinstance(d, dict):
            return cls()
        wdh, atem = d.get("wiederholungen"), d.get("atmung")
        vorlage, feld = d.get("vorlage"), d.get("feld")
        return cls(
            wiederholungen=wdh if isinstance(wdh, bool) else None,
            atmung=atem if isinstance(atem, bool) else None,
            vorlage=(vorlage.strip() or VORLAGE_AUTO) if isinstance(vorlage, str) else VORLAGE_AUTO,
            feld=(feld.strip() or None) if isinstance(feld, str) else None,
        )


#: Die Schlüssel der Karte im Paket (``beschleunigung``) und der Typ, den `SensorWahl.aus_dict`
#: annimmt — Wahrheitswerte nie als Zahl oder Text
SCHLUESSEL: Final[dict[str, type]] = {
    "wiederholungen": bool,
    "atmung": bool,
    "vorlage": str,
    "feld": str,
}
_TYPNAME: Final[dict[type, str]] = {bool: "true oder false", str: "ein Text in Anführungszeichen"}


def wahl_pruefen(roh: Any) -> tuple[list[str], list[str]]:
    """Was `SensorWahl.aus_dict` still als Vorgabe läse, in Worten — ``(Fehler, Hinweise)``
    für ``trainingsapp-paket pruefen``. Die App bleibt tolerant (das Paket bleibt lesbar), das
    Werkzeug sagt es vorher: Ein **falscher Typ** ist ein Fehler wie eine fehlende
    Beschreibung — die Wahl ginge beim Einlesen verloren. Ein **unbekannter Schlüssel** ist ein
    Hinweis wie ein Typ außerhalb des Standardpakets: ein Tippfehler, oder ein Feld einer
    neueren App.

    >>> wahl_pruefen({"wiederholungen": False, "vorlage": "auto", "feld": "reps_2"})
    ([], [])
    >>> fehler, hinweise = wahl_pruefen({"wiederholungen": "nein", "atmung": 1, "wdh": True})
    >>> for f in fehler: print(f)
    „wiederholungen“ muss true oder false sein, nicht "nein"
    „atmung“ muss true oder false sein, nicht 1
    >>> for h in hinweise: print(h)
    unbekannter Schlüssel „wdh“ — wird überlesen (bekannt: wiederholungen, atmung, vorlage, feld)
    >>> wahl_pruefen({"feld": 2})[0]
    ['„feld“ muss ein Text in Anführungszeichen sein, nicht 2']
    >>> wahl_pruefen(True)[0]
    ['keine Tabelle (etwa { wiederholungen = true }), sondern true — alles gilt als Vorgabe']
    """
    if not isinstance(roh, dict):
        return [
            f"keine Tabelle (etwa {{ wiederholungen = true }}), sondern {_wert_text(roh)} — "
            "alles gilt als Vorgabe"
        ], []
    fehler: list[str] = []
    hinweise: list[str] = []
    for schluessel, wert in roh.items():
        typ = SCHLUESSEL.get(str(schluessel))
        if typ is None:
            hinweise.append(
                f"unbekannter Schlüssel „{schluessel}“ — wird überlesen "
                f"(bekannt: {', '.join(SCHLUESSEL)})"
            )
        elif not isinstance(wert, typ):
            fehler.append(f"„{schluessel}“ muss {_TYPNAME[typ]} sein, nicht {_wert_text(wert)}")
    return fehler, hinweise


def _wert_text(wert: Any) -> str:
    """Ein Wert, wie er in TOML oder JSON steht: ``true``, ``"nein"``, ``1``."""
    try:
        return json.dumps(wert, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(wert)


# ---------------------------------------------------------------------------
# Was an der Übung gilt
# ---------------------------------------------------------------------------


def hat_wdh_feld(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Ob die Übung ein Feld der Art ``reps`` hat — ohne ist „Wiederholungen“ ausgegraut. Mit
    ``item``: ob diese Planübung eins anbietet (`wdh_felder`).

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> hat_wdh_feld(Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps_2")])))
    True
    >>> planke = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> hat_wdh_feld(planke), hat_wdh_feld(planke, PlanItem(felder=["hold", "reps"]))
    (False, True)
    """
    if item is not None:
        return bool(wdh_felder(uebung, item))
    return any(basis_key(f.key) == WDH_ART for f in uebung.result_spec.fields)


def wdh_felder(uebung: Exercise, item: PlanItem | None = None) -> list[str]:
    """Die Wiederholungsfelder (Schlüssel) — der Übung, oder mit ``item`` die, die diese
    Planübung anbietet (`core.standards.aktive_felder`: auch ein Feld, das nur der Plan hat).

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "reps_2")])
    >>> u = Exercise(result_spec=spec)
    >>> wdh_felder(u), wdh_felder(u, PlanItem(felder=["reps_2"]))
    (['reps', 'reps_2'], ['reps_2'])
    >>> wdh_felder(u, PlanItem(felder=[]))
    []
    """
    if item is None:
        felder = list(uebung.result_spec.fields)
    else:
        # Spät: `standards` holt `models`, und `models` holt dieses Modul.
        from .standards import aktive_felder

        felder = aktive_felder(item, uebung)
    return [f.key for f in felder if basis_key(f.key) == WDH_ART]


def wiederholungen_an(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Ob an der Übung Wiederholungen gezählt werden — nie ohne Wiederholungsfeld, sonst wie
    gewählt; ohne Wahl an. Mit ``item`` zählt, was die Planübung anbietet (P79: keiner = nur
    abhaken): ohne Wiederholungsfeld dort nie, mit einem, das nur der Plan hat, wie gewählt.

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> wdh = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("weight")])
    >>> wiederholungen_an(Exercise(result_spec=wdh))
    True
    >>> wiederholungen_an(Exercise(result_spec=wdh, beschleunigung=SensorWahl(False)))
    False
    >>> halten = ResultSpec(fields=[vorrat_feld("hold")])
    >>> wiederholungen_an(Exercise(result_spec=halten, beschleunigung=SensorWahl(True)))
    False
    >>> u = Exercise(result_spec=wdh)
    >>> wiederholungen_an(u, PlanItem(felder=["weight"])), wiederholungen_an(u, PlanItem(felder=[]))
    (False, False)
    >>> wiederholungen_an(Exercise(result_spec=halten), PlanItem(felder=["hold", "reps"]))
    True
    """
    return hat_wdh_feld(uebung, item) and uebung.beschleunigung.wiederholungen is not False


def atmung_an(uebung: Exercise) -> bool:
    """Ob an der Übung die Atmung erfasst wird — wie gewählt; ohne Wahl an bei Typ „Atmung“
    (groß/klein egal, wie Tags sonst auch).

    >>> from trainingsapp.core.models import Exercise
    >>> atmung_an(Exercise(typen=["Entspannung", "Atmung"])), atmung_an(Exercise(typen=["atmung"]))
    (True, True)
    >>> atmung_an(Exercise(typen=["Kräftigung"]))
    False
    >>> atmung_an(Exercise(typen=["Kräftigung"], beschleunigung=SensorWahl(atmung=True)))
    True
    >>> atmung_an(Exercise(typen=["Atmung"], beschleunigung=SensorWahl(atmung=False)))
    False
    """
    gewaehlt = uebung.beschleunigung.atmung
    if gewaehlt is not None:
        return gewaehlt
    return any(t.casefold() == TYP_ATMUNG.casefold() for t in uebung.typen)


def zaehlt_in(uebung: Exercise, item: PlanItem | None = None) -> str | None:
    """Das Feld, in das die Wiederholungen kommen: das gewählte, wenn es (in der Planübung)
    angeboten wird, sonst das erste Wiederholungsfeld — ``None`` ohne eins.

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("reps_2")])
    >>> u = Exercise(result_spec=spec, beschleunigung=SensorWahl(feld="reps_2"))
    >>> zaehlt_in(u), zaehlt_in(u, PlanItem(felder=["reps"])), zaehlt_in(Exercise(name="Planke"))
    ('reps_2', 'reps', None)
    """
    felder = wdh_felder(uebung, item)
    if not felder:
        return None
    gewaehlt = uebung.beschleunigung.feld
    return gewaehlt if gewaehlt in felder else felder[0]


# ---------------------------------------------------------------------------
# Texte der Zählzeile
# ---------------------------------------------------------------------------


def knopf_text(wdh: bool, atem: bool) -> str:
    """Der Knopf (§4.1) — nicht bloß „Zählen“: neben der Uhr steht schon „zählt“ (P79 D1).
    Leer, wenn beides aus ist: dann gibt es keinen Knopf.

    >>> knopf_text(True, False), knopf_text(False, True), knopf_text(True, True)
    ('Wdh. zählen', 'Atmung erfassen', 'Wdh. zählen · Atmung')
    >>> knopf_text(False, False)
    ''
    """
    if wdh and atem:
        return "Wdh. zählen · Atmung"
    if wdh:
        return "Wdh. zählen"
    if atem:
        return "Atmung erfassen"
    return ""


def anzeige(sensor: int | None, korrektur: int) -> int:
    """Was groß dasteht und eingetragen wird: Sensor plus Korrektur, nie weniger als 0.
    Ohne Zahl vom Sensor (noch keine Periode erkannt) zählt nur die Korrektur.

    >>> anzeige(11, 1), anzeige(2, -5), anzeige(None, 2)
    (12, 0, 2)
    """
    return max(0, (sensor or 0) + korrektur)


def mit_vorzeichen(n: int) -> str:
    """Eine Korrektur mit Vorzeichen — Minus als Rechenzeichen „−“ wie in der Zählzeile.

    >>> mit_vorzeichen(1), mit_vorzeichen(-2), mit_vorzeichen(0)
    ('+1', '−2', '±0')
    """
    if n > 0:
        return f"+{n}"
    if n < 0:
        return f"−{-n}"
    return "±0"


def korrektur_text(sensor: int | None, korrektur: int) -> str:
    """Die kleine Zeile unter der Zahl: was der Sensor zählte, dahinter die Korrektur, wenn
    es eine gibt. Ohne Zahl vom Sensor „…“.

    >>> korrektur_text(11, 1), korrektur_text(11, 0), korrektur_text(11, -2)
    ('Sensor 11 · +1', 'Sensor 11', 'Sensor 11 · −2')
    >>> korrektur_text(None, 1)
    'Sensor … · +1'
    """
    text = f"Sensor {'…' if sensor is None else sensor}"
    return f"{text} · {mit_vorzeichen(korrektur)}" if korrektur else text


#: Die Atemphase als Pfeil: Einatmen ▲, Ausatmen ▼ (Plan §4.5, §7.3)
PHASE_PFEILE: Final = {"ein": "▲", "aus": "▼"}


def rate_text(rate: float | None) -> str:
    """Die Atemrate je Minute — „–“, solange kein gültiges Fenster eine nannte.

    >>> rate_text(12.0), rate_text(5.96), rate_text(None)
    ('12/min', '6/min', '–')
    """
    return f"{rate:.0f}/min" if rate is not None else "–"


def phase_pfeil(phase: str | None) -> str:
    """▲ beim Einatmen, ▼ beim Ausatmen, leer, wenn der Prototyp es nicht weiß.

    >>> phase_pfeil("ein"), phase_pfeil("aus"), phase_pfeil(None), phase_pfeil("x")
    ('▲', '▼', '', '')
    """
    return PHASE_PFEILE.get(phase or "", "")


def atem_text(rate: float | None, phase: str | None) -> str:
    """Rate und Phase in einem: „12/min ▲“, ohne Phase „12/min“, ohne Rate „– ▼“.

    >>> atem_text(12.0, "ein"), atem_text(12.0, None), atem_text(None, "aus")
    ('12/min ▲', '12/min', '– ▼')
    """
    return f"{rate_text(rate)} {phase_pfeil(phase)}".rstrip()


def rate_waehlen(raten_hz: Iterable[int]) -> int:
    """Die Rate fürs Zählen: die kleinste ab `MIN_RATE_HZ`, die das Gerät anbietet
    (``hrv_core.geraete.treiber``: Strom ``acc``, ``raten_hz``) — ohne passende `MIN_RATE_HZ`.

    >>> rate_waehlen((25, 50, 100, 200)), rate_waehlen((52, 104, 208)), rate_waehlen(())
    (50, 52, 50)
    """
    passend = [int(r) for r in raten_hz if r >= MIN_RATE_HZ]
    return min(passend) if passend else MIN_RATE_HZ
