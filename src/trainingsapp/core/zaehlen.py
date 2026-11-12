"""Wiederholungen zählen und Atmung erfassen mit dem Beschleunigungssensor — was die Übung
festlegt und wie die Zählzeile spricht.

Ben, 4.11.2026 (`docs/plan_beschleunigung.md` §3, §4, §12):

- `SensorWahl` — die Karte „Beschleunigungssensor“ an der Übung (Migration 037,
  ``exercise.acc_json``; Paketfeld ``beschleunigung``): ``wiederholungen`` und ``atmung``
  (``None`` = Vorgabe aus der Übung), ``vorlage`` (die Bewegung, A5) und ``feld`` („Zählt in“
  bei mehreren Wiederholungsfeldern). `wahl_pruefen` sagt, was `SensorWahl.aus_dict` still
  überläse (``trainingsapp-paket pruefen``).
- **Vorlagen** (A5, Ben 5.11.2026): Der Katalog liegt in hrv-core
  (``prototyp.wiederholungen.VORLAGEN``); die App bietet `VORLAGEN_ANGEBOT` an — Automatisch,
  Kniebeuge, Liegestütz (`vorlagen_angebot`, Hinweis je Vorlage) — und speichert nur den
  Schlüssel. `vorlage_waehlen` sagt, womit ein Gerät zählt: eine Vorlage, die Achsen eines
  anderen Geräts meint (``Vorlage.geraet`` ≠ Profil, etwa Kniebeuge an der Verity Sense am
  Arm), fällt auf Automatisch zurück; unbekannte Schlüssel ebenso. **Gezählt wird oben**
  (P143): der Umkehrpunkt der Vorlage wird mit ``umkehr = oben`` überschrieben — die
  Wiederholung zählt mit der Rückkehr in die Ausgangslage, nicht am fernen Ende.
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
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

from hrv_core.prototyp import wiederholungen as prototyp_wdh

from .result_spec import basis_key

if TYPE_CHECKING:
    from .models import Exercise, PlanItem

#: Bewegung „Automatisch“: die Hauptachse der Bewegung, gerätefrei (hrv-core ``VORLAGEN``).
#: Ein Schlüssel, den hrv-core (noch) nicht kennt, gilt beim Zählen als dieser.
VORLAGE_AUTO: Final = "auto"
#: Die Vorlagen, die die Karte anbietet (P144, Ben 5.11.2026: nur diese drei — Rudern und
#: Burpee aus dem Katalog nicht, Rudern zählt mit freier Rollenwahl am Nachlassen, Burpee ist
#: ein Entwurf)
VORLAGEN_ANGEBOT: Final = ("auto", "kniebeuge", "liegestuetz")
#: **Bewegungstyp** (Ben, 12.11.2026: „für eine Übung verschiedene Bewegungstypen
#: vorbestimmen — bei der Kniebeuge Fokus auf die x-Achse, Liegestütze y-Achse“): das Signal,
#: an dem der Sensor die Wiederholung abliest. Schlüssel = Signal in hrv-core
#: (``prototyp.wiederholungen.SIGNALE``), leer = wie die Vorlage. Die Rechnung bleibt in
#: hrv-core (`mit_signal`); die App merkt sich nur die Wahl je Übung.
BEWEGUNGSTYPEN: Final[dict[str, str]] = {
    "": "wie die Vorlage",
    "hauptachse": "Hauptachse",
    "x": "x-Achse",
    "y": "y-Achse",
    "z": "z-Achse",
    "neigung_zx": "Kippen (z–x)",
    "neigung_zy": "Kippen (z–y)",
    "betrag": "Betrag",
}
#: Bewegungstyp der **Atmung**: bisher nur das Kippen des Gurts (hrv-core
#: ``prototyp.atemzuege.RICHTUNG``, ``(x − z) / √2``). Weitere Verfahren kommen mit hrv-core;
#: die Wahl je Übung steht schon bereit (leer = Vorgabe).
ATEM_BEWEGUNG_VORGABE: Final = "kippen"
ATEM_BEWEGUNGEN: Final[dict[str, str]] = {ATEM_BEWEGUNG_VORGABE: "Kippen"}
#: Ein Gerät je ``Vorlage.geraet`` in Worten (hrv-core nennt das Profil)
_GERAETE_NAMEN: Final = {"polar_h10": "den Brustgurt"}
#: Die Art eines Wiederholungsfeldes (``reps``, ``reps_2`` …)
WDH_ART: Final = "reps"
#: Der Typ, an dem „Atmung“ von selbst an ist
TYP_ATMUNG: Final = "Atmung"

#: Was gezählt wird (``zaehlart`` im Ereignis ``zaehlung``) — ``art`` ist schon ein Feld
#: des Ereignisses
ZAEHLART_WDH: Final = "wdh"
ZAEHLART_ATEM: Final = "atem"
#: Wer zählt (``quelle`` im Ereignis ``zaehlung``, Taktgeber Teil 2 T5, P138): der Sensor
#: (eine Messung) oder der Takt (jede volle Runde eine Wiederholung — eine Vorgabe, keine
#: Messung; die Zählzeile sagt „Takt“, nie „Prototyp“). Mit Sensor zählt der Sensor, der Takt
#: steht daneben; ohne Sensor ist der Takt die Quelle
QUELLE_SENSOR: Final = "sensor"
QUELLE_TAKT: Final = "takt"

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
    >>> SensorWahl(signal="x", atmung_bewegung="kippen").als_dict()
    {'signal': 'x'}
    """

    #: Wiederholungen zählen — ``None``: an, wenn die Übung ein Feld der Art ``reps`` hat
    wiederholungen: bool | None = None
    #: Atmung erfassen — ``None``: an bei Typ „Atmung“
    atmung: bool | None = None
    #: Bewegung: Schlüssel einer Vorlage in hrv-core (`VORLAGEN_ANGEBOT`; unbekannt = ``auto``)
    vorlage: str = VORLAGE_AUTO
    #: „Zählt in“ (nur bei mehreren Wiederholungsfeldern) — ``None``: das erste
    feld: str | None = None
    #: Bewegungstyp der Wiederholungen (`BEWEGUNGSTYPEN`) — leer: wie die Vorlage. Ein
    #: unbekannter Schlüssel bleibt erhalten (neueres hrv-core) und gilt beim Zählen als leer
    signal: str = ""
    #: Bewegungstyp der Atmung (`ATEM_BEWEGUNGEN`) — leer: die Vorgabe (Kippen)
    atmung_bewegung: str = ""

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
        if self.signal:
            d["signal"] = self.signal
        if self.atmung_bewegung and self.atmung_bewegung != ATEM_BEWEGUNG_VORGABE:
            d["atmung_bewegung"] = self.atmung_bewegung
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> SensorWahl:
        """Defensiv: Unbrauchbares gilt als Vorgabe — Schalter nur als echte Wahrheitswerte,
        Texte nur als nicht leere Zeichenketten. Eine unbekannte Vorlage bleibt erhalten
        (neueres hrv-core), gezählt wird mit ihr wie mit „Automatisch“.

        >>> kaputt = {"wiederholungen": "ja", "atmung": 1, "vorlage": 3, "feld": ""}
        >>> SensorWahl.aus_dict(kaputt) == SensorWahl()
        True
        >>> w = SensorWahl.aus_dict({"atmung": False, "vorlage": " neigung_zy ", "x": 1})
        >>> w.atmung, w.vorlage, w.feld
        (False, 'neigung_zy', None)
        >>> w = SensorWahl.aus_dict({"signal": " y ", "atmung_bewegung": 3})
        >>> w.signal, w.atmung_bewegung
        ('y', '')
        """
        if not isinstance(d, dict):
            return cls()
        wdh, atem = d.get("wiederholungen"), d.get("atmung")
        vorlage, feld = d.get("vorlage"), d.get("feld")
        signal, atem_art = d.get("signal"), d.get("atmung_bewegung")
        return cls(
            wiederholungen=wdh if isinstance(wdh, bool) else None,
            atmung=atem if isinstance(atem, bool) else None,
            vorlage=(vorlage.strip() or VORLAGE_AUTO) if isinstance(vorlage, str) else VORLAGE_AUTO,
            feld=(feld.strip() or None) if isinstance(feld, str) else None,
            signal=signal.strip() if isinstance(signal, str) else "",
            atmung_bewegung=atem_art.strip() if isinstance(atem_art, str) else "",
        )


#: Die Schlüssel der Karte im Paket (``beschleunigung``) und der Typ, den `SensorWahl.aus_dict`
#: annimmt — Wahrheitswerte nie als Zahl oder Text
SCHLUESSEL: Final[dict[str, type]] = {
    "wiederholungen": bool,
    "atmung": bool,
    "vorlage": str,
    "feld": str,
    "signal": str,
    "atmung_bewegung": str,
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
    >>> for h in hinweise: print(h)  # doctest: +ELLIPSIS
    unbekannter Schlüssel „wdh“ — wird überlesen (bekannt: wiederholungen, atmung, vorlage, ...)
    >>> wahl_pruefen({"feld": 2})[0]
    ['„feld“ muss ein Text in Anführungszeichen sein, nicht 2']
    >>> for h in wahl_pruefen({"vorlage": "rudern"})[1]: print(h)
    unbekannte Vorlage „rudern“ — zählt wie „Automatisch“ (bekannt: auto, kniebeuge, liegestuetz)
    >>> for h in wahl_pruefen({"signal": "quer", "atmung_bewegung": "bauch"})[1]:
    ...     print(h)  # doctest: +ELLIPSIS
    unbekannter Bewegungstyp „quer“ — zählt wie die Vorlage (bekannt: hauptachse, x, y, ...)
    unbekannter Bewegungstyp der Atmung „bauch“ — gilt als „kippen“ (bekannt: kippen)
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
        elif (
            schluessel == "vorlage"
            and isinstance(wert, str)
            and wert.strip() not in VORLAGEN_ANGEBOT
        ):
            hinweise.append(
                f"unbekannte Vorlage „{wert}“ — zählt wie „Automatisch“ "
                f"(bekannt: {', '.join(VORLAGEN_ANGEBOT)})"
            )
        elif schluessel == "signal" and str(wert).strip() not in BEWEGUNGSTYPEN:
            bekannt = ", ".join(k for k in BEWEGUNGSTYPEN if k)
            hinweise.append(
                f"unbekannter Bewegungstyp „{wert}“ — zählt wie die Vorlage (bekannt: {bekannt})"
            )
        elif schluessel == "atmung_bewegung" and str(wert).strip() not in ATEM_BEWEGUNGEN:
            hinweise.append(
                f"unbekannter Bewegungstyp der Atmung „{wert}“ — gilt als "
                f"„{ATEM_BEWEGUNG_VORGABE}“ (bekannt: {', '.join(ATEM_BEWEGUNGEN)})"
            )
    return fehler, hinweise


def _wert_text(wert: Any) -> str:
    """Ein Wert, wie er in TOML oder JSON steht: ``true``, ``"nein"``, ``1``."""
    try:
        return json.dumps(wert, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(wert)


# ---------------------------------------------------------------------------
# Vorlagen der Bewegung (A5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VorlageAngebot:
    """Eine Vorlage, wie die Karte sie anbietet: Schlüssel, Name und ein Hinweis."""

    schluessel: str
    name: str
    hinweis: str


def vorlage_name(schluessel: str | None) -> str:
    """Der Name einer Vorlage aus dem Katalog — unbekannt oder leer: „Automatisch“.

    >>> vorlage_name("kniebeuge"), vorlage_name("x"), vorlage_name(None)
    ('Kniebeuge', 'Automatisch', 'Automatisch')
    """
    return prototyp_wdh.vorlage(schluessel).name


def vorlage_hinweis(v: prototyp_wdh.Vorlage) -> str:
    """Der Hinweis zur Vorlage in der Karte: wofür sie geprüft ist.

    >>> vorlage_hinweis(prototyp_wdh.VORLAGEN["kniebeuge"])
    'nur für den Brustgurt geprüft'
    >>> vorlage_hinweis(prototyp_wdh.VORLAGEN["liegestuetz"])
    'Erwartung, noch ohne Messdaten'
    >>> vorlage_hinweis(prototyp_wdh.VORLAGEN["auto"])
    'die Hauptachse der Bewegung, gerätefrei'
    """
    if v.schluessel == VORLAGE_AUTO:
        return "die Hauptachse der Bewegung, gerätefrei"
    if v.geraet is not None:
        return f"nur für {_GERAETE_NAMEN.get(v.geraet, v.geraet)} geprüft"
    return "Erwartung, noch ohne Messdaten"


def vorlagen_angebot() -> list[VorlageAngebot]:
    """Die Vorlagen der Karte (`VORLAGEN_ANGEBOT`) mit Namen aus hrv-core — was hrv-core
    nicht kennt (älteres), fällt weg.

    >>> [v.name for v in vorlagen_angebot()]
    ['Automatisch', 'Kniebeuge', 'Liegestütz']
    """
    heraus: list[VorlageAngebot] = []
    for k in VORLAGEN_ANGEBOT:
        v = prototyp_wdh.VORLAGEN.get(k)
        if v is not None and v.verfuegbar:
            heraus.append(VorlageAngebot(k, v.name, vorlage_hinweis(v)))
    return heraus


@dataclass(frozen=True)
class VorlageWahl:
    """Womit ein Gerät zählt (`vorlage_waehlen`): die Vorlage für `WdhLive` (Umkehrpunkt
    oben), ihr Schlüssel und, wenn sie nicht die gewählte ist, warum (``rueckfall``)."""

    vorlage: prototyp_wdh.Vorlage
    rueckfall: str = ""
    #: Der Name des Bewegungstyps, wenn die Übung einen anderen vorbestimmt als die Vorlage
    bewegungstyp: str = ""

    @property
    def schluessel(self) -> str:
        return self.vorlage.schluessel

    @property
    def text(self) -> str:
        """„Kniebeuge“ — nach einem Rückfall „Automatisch (Vorlage nur für den Brustgurt)“."""
        if self.rueckfall:
            return f"{self.vorlage.name} ({self.rueckfall})"
        if self.bewegungstyp:
            return f"{self.vorlage.name} · {self.bewegungstyp}"
        return self.vorlage.name


def bewegungstypen_angebot() -> list[tuple[str, str]]:
    """Die Bewegungstypen der Karte als (Schlüssel, Name) — nur Signale, die hrv-core kennt.

    >>> [k for k, _ in bewegungstypen_angebot()][:4]
    ['', 'hauptachse', 'x', 'y']
    """
    return [(k, n) for k, n in BEWEGUNGSTYPEN.items() if not k or k in prototyp_wdh.SIGNALE]


def vorlage_waehlen(
    schluessel: str | None, geraet: str | None, signal: str | None = None
) -> VorlageWahl:
    """Die Vorlage, mit der ``geraet`` (Profil-ID) zählt — mit ``umkehr = oben`` (P143: die
    Wiederholung zählt mit der Rückkehr in die Ausgangslage). Unbekannt, Entwurf oder die
    Achsen eines anderen Geräts (``Vorlage.geraet`` ≠ Profil): Automatisch, mit Grund.

    >>> w = vorlage_waehlen("kniebeuge", "polar_h10")
    >>> w.schluessel, w.vorlage.umkehr, w.rueckfall, w.text
    ('kniebeuge', 'oben', '', 'Kniebeuge')
    >>> w = vorlage_waehlen("kniebeuge", "verity_sense")
    >>> w.schluessel, w.rueckfall, w.text
    ('auto', 'Vorlage nur für den Brustgurt', 'Automatisch (Vorlage nur für den Brustgurt)')
    >>> vorlage_waehlen("gibt_es_nicht", "polar_h10").text, vorlage_waehlen(None, None).text
    ('Automatisch', 'Automatisch')
    >>> vorlage_waehlen("burpee", "polar_h10").rueckfall
    'Vorlage noch ein Entwurf'

    ``signal``: der Bewegungstyp der Übung (`BEWEGUNGSTYPEN`) — die Vorlage rechnet dann mit
    diesem Signal (hrv-core ``mit_signal``). Eine feste Achse oder das Kippen meinen die
    Ausrichtung des Brustgurts; an einem anderen Gerät zählt Automatisch, mit Grund.

    >>> w = vorlage_waehlen("liegestuetz", "polar_h10", "y")
    >>> w.vorlage.signal, w.rueckfall, w.text
    ('y', '', 'Liegestütz · y-Achse')
    >>> vorlage_waehlen("liegestuetz", "verity_sense", "y").text
    'Automatisch (Bewegungstyp nur für den Brustgurt)'
    >>> vorlage_waehlen("auto", None, "gibt_es_nicht").vorlage.signal
    'hauptachse'
    """
    auto = prototyp_wdh.VORLAGEN[VORLAGE_AUTO]
    v = prototyp_wdh.vorlage(schluessel)
    rueckfall = ""
    if not v.verfuegbar:
        v, rueckfall = auto, "Vorlage noch ein Entwurf"
    elif v.geraet is not None and v.geraet != (geraet or ""):
        name = _GERAETE_NAMEN.get(v.geraet, v.geraet)
        v, rueckfall = auto, f"Vorlage nur für {name}"
    typ = ""
    if not rueckfall and signal and signal in prototyp_wdh.SIGNALE and signal != v.signal:
        mit = prototyp_wdh.mit_signal(v, signal)
        if mit.geraet is not None and mit.geraet != (geraet or ""):
            name = _GERAETE_NAMEN.get(mit.geraet, mit.geraet)
            v, rueckfall = auto, f"Bewegungstyp nur für {name}"
        else:
            v, typ = mit, BEWEGUNGSTYPEN.get(signal, signal)
    if v.umkehr != prototyp_wdh.UMKEHR_OBEN:
        v = replace(v, umkehr=prototyp_wdh.UMKEHR_OBEN)
    return VorlageWahl(v, rueckfall, typ)


def halbe_text(halbe: int) -> str:
    """Halbe Wiederholungen neben der Zahl — gezeigt, nie mitgezählt (Ben, 5.11.2026).

    >>> halbe_text(2), halbe_text(1), halbe_text(0)
    ('2 halbe', '1 halbe', '')
    """
    return f"{halbe} halbe" if halbe > 0 else ""


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


def wirksame_wahl(uebung: Exercise, item: PlanItem | None = None) -> SensorWahl:
    """Die Karte „Beschleunigungssensor“, die gilt: die der Planübung, wenn sie eine eigene hat
    (``PlanItem.acc``, A6), sonst die der Übung — die Planübung folgt der Übung (P79). Eine
    Wahl „für jetzt“ gibt es hier nicht: Der Knopf ist die Messung.

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> u = Exercise(beschleunigung=SensorWahl(atmung=True))
    >>> wirksame_wahl(u).atmung, wirksame_wahl(u, PlanItem()).atmung
    (True, True)
    >>> wirksame_wahl(u, PlanItem(acc=SensorWahl(atmung=False))).atmung
    False
    """
    if item is not None and item.acc is not None:
        return item.acc
    return uebung.beschleunigung


def wiederholungen_an(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Ob an der Übung Wiederholungen gezählt werden — nie ohne Wiederholungsfeld, sonst wie
    gewählt; ohne Wahl an. Mit ``item`` zählt, was die Planübung anbietet (P79: keiner = nur
    abhaken): ohne Wiederholungsfeld dort nie, mit einem, das nur der Plan hat, wie gewählt —
    und gewählt ist, was die Planübung einstellt (`wirksame_wahl`, A6).

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
    >>> wiederholungen_an(u, PlanItem(acc=SensorWahl(wiederholungen=False)))
    False
    """
    return hat_wdh_feld(uebung, item) and wirksame_wahl(uebung, item).wiederholungen is not False


def atmung_an(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Ob an der Übung die Atmung erfasst wird — wie gewählt; ohne Wahl an bei Typ „Atmung“
    (groß/klein egal, wie Tags sonst auch). Mit ``item``: wie die Planübung es einstellt
    (`wirksame_wahl`, A6), die Vorgabe bleibt die der Übung.

    >>> from trainingsapp.core.models import Exercise
    >>> atmung_an(Exercise(typen=["Entspannung", "Atmung"])), atmung_an(Exercise(typen=["atmung"]))
    (True, True)
    >>> atmung_an(Exercise(typen=["Kräftigung"]))
    False
    >>> atmung_an(Exercise(typen=["Kräftigung"], beschleunigung=SensorWahl(atmung=True)))
    True
    >>> atmung_an(Exercise(typen=["Atmung"], beschleunigung=SensorWahl(atmung=False)))
    False
    >>> from trainingsapp.core.models import PlanItem
    >>> atmung_an(Exercise(typen=["Atmung"]), PlanItem(acc=SensorWahl(atmung=False)))
    False
    """
    gewaehlt = wirksame_wahl(uebung, item).atmung
    if gewaehlt is not None:
        return gewaehlt
    return any(t.casefold() == TYP_ATMUNG.casefold() for t in uebung.typen)


def zaehlt_in(uebung: Exercise, item: PlanItem | None = None) -> str | None:
    """Das Feld, in das die Wiederholungen kommen: das gewählte (in der Planübung ihres, sonst
    das der Übung — `wirksame_wahl`), wenn es (in der Planübung) angeboten wird, sonst das
    erste Wiederholungsfeld — ``None`` ohne eins.

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("reps_2")])
    >>> u = Exercise(result_spec=spec, beschleunigung=SensorWahl(feld="reps_2"))
    >>> zaehlt_in(u), zaehlt_in(u, PlanItem(felder=["reps"])), zaehlt_in(Exercise(name="Planke"))
    ('reps_2', 'reps', None)
    >>> zaehlt_in(Exercise(result_spec=spec), PlanItem(acc=SensorWahl(feld="reps_2")))
    'reps_2'
    """
    felder = wdh_felder(uebung, item)
    if not felder:
        return None
    gewaehlt = wirksame_wahl(uebung, item).feld
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


def quelle_name(quelle: str) -> str:
    """„Sensor“ oder „Takt“ — wer zählt (`QUELLE_SENSOR`, `QUELLE_TAKT`).

    >>> quelle_name("sensor"), quelle_name("takt"), quelle_name("x")
    ('Sensor', 'Takt', 'Sensor')
    """
    return "Takt" if quelle == QUELLE_TAKT else "Sensor"


def korrektur_text(sensor: int | None, korrektur: int, quelle: str = QUELLE_SENSOR) -> str:
    """Die kleine Zeile unter der Zahl: was der Sensor (oder der Takt) zählte, dahinter die
    Korrektur, wenn es eine gibt. Ohne Zahl vom Sensor „…“.

    >>> korrektur_text(11, 1), korrektur_text(11, 0), korrektur_text(11, -2)
    ('Sensor 11 · +1', 'Sensor 11', 'Sensor 11 · −2')
    >>> korrektur_text(None, 1), korrektur_text(12, 1, "takt")
    ('Sensor … · +1', 'Takt 12 · +1')
    """
    text = f"{quelle_name(quelle)} {'…' if sensor is None else sensor}"
    return f"{text} · {mit_vorzeichen(korrektur)}" if korrektur else text


def takt_zeile(takt: int | None, korrektur: int = 0) -> str:
    """Die kleine Zeile, wenn der Takt zählt (P138): „Takt 12“, mit Korrektur „Takt 12 · +1“
    — nie „Prototyp“: die Zahl ist eine Vorgabe, keine Messung. Vor der ersten Runde „Takt …“.

    >>> takt_zeile(12), takt_zeile(12, 1), takt_zeile(None)
    ('Takt 12', 'Takt 12 · +1', 'Takt …')
    """
    return korrektur_text(takt, korrektur, QUELLE_TAKT)


def takt_neben_text(takt: int | None) -> str:
    """Der Takt neben dem Sensor („Takt 12 · Sensor 11“): sein Teil, leer ohne Takt.

    >>> takt_neben_text(12), takt_neben_text(None)
    ('Takt 12', '')
    """
    return f"Takt {takt}" if takt is not None else ""


def sensor_zeile(sensor: int | None, korrektur: int, halbe: int = 0, vorlage: str = "") -> str:
    """Die kleine Zeile mit allem (A5): `korrektur_text`, dazu die halben Wiederholungen und
    die Vorlage, wenn eine gewählt ist („Kniebeuge“ oder, nach einem Rückfall, „Automatisch
    (Vorlage nur für den Brustgurt)“ — `VorlageWahl.text`; bei „Automatisch“ nichts).

    >>> sensor_zeile(11, 1), sensor_zeile(11, 0, 2), sensor_zeile(11, -1, 1, "Kniebeuge")
    ('Sensor 11 · +1', 'Sensor 11 · 2 halbe', 'Sensor 11 · −1 · 1 halbe · Kniebeuge')
    """
    teile = [korrektur_text(sensor, korrektur), halbe_text(halbe), vorlage]
    return " · ".join(t for t in teile if t)


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


def spanne_text(spanne_ms: float | None) -> str:
    """Die Atemspanne des letzten Atemzugs live (B2, `hrv_core.prototyp.atem_hrv`): „Spanne
    58 ms“ — leer, solange es keine gibt (ohne Aufnahme, vor dem ersten vollständigen Atemzug,
    letzter ungültig).

    >>> spanne_text(58.4), spanne_text(None)
    ('Spanne 58 ms', '')
    """
    return f"Spanne {round(spanne_ms)} ms" if spanne_ms is not None else ""


def atem_text(rate: float | None, phase: str | None, spanne_ms: float | None = None) -> str:
    """Rate und Phase in einem: „12/min ▲“, ohne Phase „12/min“, ohne Rate „– ▼“ — mit der
    Atemspanne des letzten Atemzugs „12/min ▲ · Spanne 58 ms“.

    >>> atem_text(12.0, "ein"), atem_text(12.0, None), atem_text(None, "aus")
    ('12/min ▲', '12/min', '– ▼')
    >>> atem_text(12.0, "ein", 58.4)
    '12/min ▲ · Spanne 58 ms'
    """
    text = f"{rate_text(rate)} {phase_pfeil(phase)}".rstrip()
    return f"{text} · {spanne_text(spanne_ms)}" if spanne_ms is not None else text


def rate_waehlen(raten_hz: Iterable[int]) -> int:
    """Die Rate fürs Zählen: die kleinste ab `MIN_RATE_HZ`, die das Gerät anbietet
    (``hrv_core.geraete.treiber``: Strom ``acc``, ``raten_hz``) — ohne passende `MIN_RATE_HZ`.

    >>> rate_waehlen((25, 50, 100, 200)), rate_waehlen((52, 104, 208)), rate_waehlen(())
    (50, 52, 50)
    """
    passend = [int(r) for r in raten_hz if r >= MIN_RATE_HZ]
    return min(passend) if passend else MIN_RATE_HZ
