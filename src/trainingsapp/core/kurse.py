"""Kurse — Kapitel, die man von oben nach unten durcharbeitet (Ben, 15.10.2026).

Neben Übungen (Vorratskammer) und Plänen (Rahmen für einen Tag) die dritte
Kategorie: Ein **Kurs** ist eine Folge von **Kapiteln**. Jedes Kapitel hat
Erklärtext (Markdown), Medien, optional **Plan-Vorlagen** — beim Erreichen des
Kapitels legt die App sie als echte Pläne an, beim Abschluss deaktiviert sie
sie — und eine **Bedingung**, die erfüllt sein muss, bevor das nächste
Kapitel aufgeht:

- ``gelesen`` — angesehen und mit „Weiter“ bestätigt (Erklärkapitel);
- ``summe`` — eine Menge einer Übung seit Kapitelstart („100 Liegestützen“),
  Varianten zählen mit;
- ``tage`` — an so vielen Tagen seit Kapitelstart geübt;
- ``messung`` — eine HRV-Messung von mindestens so vielen Minuten liegt vor.
  Geprüft wird nur, **dass** gemessen wurde, nie ein Messwert — eine Empfehlung
  aus Messwerten wäre ``physiologische_steuerung`` (`docs/recht`).

Überspringen: je Kurs ``frei`` (alle Kapitel offen), ``rueckfrage`` (ein
Dialog „Noch 60 von 100 — trotzdem freischalten?“) oder ``streng`` (gar nicht,
für zugewiesene Kurse in Edition B). Übersprungenes bleibt sichtbar.

Ein Kurs kann auch nur erklären — etwa, was die HRV-Messung ist und wie man
die App bedient. Dann sind alle Bedingungen ``gelesen``.

Hier steht nur Rechnung: Status der Kapitel, Stand einer Bedingung, Plan aus
Vorlage. Laden, Speichern und Datenbeschaffung macht `data/kurse.py`;
das Paketformat `core/pakete.py`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from . import ablauf as ab
from . import links
from .bedingung import Bedingung as Weiterbedingung
from .models import (
    Exercise,
    HrvRecording,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    SessionEntry,
    jetzt,
    medium_aus_dict,
    new_id,
)
from .paketmedien import medium_aus_paket
from .result_spec import FieldSpec, FieldType, vorrat_feld
from .tagesbilanz import menge_text, mengen
from .takt import AUS, Takt
from .zaehlen import SensorWahl

# -- Freischaltung (Spalte `course.unlock_mode`) --------------------------------
FREI = "frei"
RUECKFRAGE = "rueckfrage"
STRENG = "streng"
FREISCHALTUNGEN: dict[str, str] = {
    FREI: "Alle Kapitel offen",
    RUECKFRAGE: "Der Reihe nach — Überspringen auf Rückfrage",
    STRENG: "Der Reihe nach — kein Überspringen",
}

# -- Arten einer Bedingung -----------------------------------------------------
GELESEN = "gelesen"
SUMME = "summe"
TAGE = "tage"
MESSUNG = "messung"
BEDINGUNGEN = (GELESEN, SUMME, TAGE, MESSUNG)

# -- Status eines Kapitels -----------------------------------------------------
FERTIG = "fertig"
UEBERSPRUNGEN = "uebersprungen"
AKTUELL = "aktuell"
OFFEN = "offen"  # noch nicht dran, aber zugänglich (Freischaltung „frei“)
GESPERRT = "gesperrt"


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Bedingung:
    """Was erfüllt sein muss, damit ein Kapitel als abgeschlossen gilt.

    ``soll`` ist je Art: Menge (``summe``), Tage (``tage``), Minuten
    (``messung``); bei ``gelesen`` ohne Bedeutung.
    """

    art: str = GELESEN
    #: ``summe``: die Übung (Varianten zählen mit)
    exercise_id: str = ""
    #: ``summe``: welches Mengenfeld (Schlüssel aus dem Feldvorrat, z. B. ``reps``)
    feld: str = "reps"
    soll: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"art": self.art}
        if self.art == SUMME:
            d["uebung"] = self.exercise_id
            d["feld"] = self.feld
        if self.art != GELESEN:
            d["soll"] = self.soll
        return d

    @classmethod
    def from_dict(cls, roh: Mapping[str, Any]) -> Bedingung:
        """Liest, was `to_dict` schreibt; Unbekanntes gilt als ``gelesen``.

        >>> Bedingung.from_dict({"art": "summe", "uebung": "u1", "feld": "reps", "soll": 100})
        Bedingung(art='summe', exercise_id='u1', feld='reps', soll=100.0)
        >>> Bedingung.from_dict({}).art
        'gelesen'
        """
        art = str(roh.get("art") or GELESEN)
        if art not in BEDINGUNGEN:
            art = GELESEN
        try:
            soll = float(roh.get("soll") or 0)
        except (TypeError, ValueError):
            soll = 0.0
        if not math.isfinite(soll):  # 1e400, "inf", NaN — `int(soll)` stürzte später ab (K17)
            soll = 0.0
        return cls(
            art=art,
            exercise_id=str(roh.get("uebung") or roh.get("exercise_id") or ""),
            feld=str(roh.get("feld") or "reps"),
            soll=max(soll, 0.0),
        )


@dataclass(slots=True)
class VorlageItem:
    """Eine Übung in einer Plan-Vorlage — wie `PlanItem`, ohne Plan und ID."""

    exercise_id: str
    target: dict[str, Any] = field(default_factory=dict)
    #: Angebotene Parameter — ``None`` = wie die Übung, ``[]`` = nur abhaken
    felder: list[str] | None = None
    #: Karte „Beschleunigungssensor“ nur hier (A6, Paketfeld ``beschleunigung`` je Planübung)
    #: — ``None`` = wie die Übung
    beschleunigung: SensorWahl | None = None
    #: Takt nur hier (A6, Paketfeld ``takt`` je Planübung) — ``None`` = wie die Übung, ein
    #: leerer Takt (``takt = {}``) = ausdrücklich keiner
    takt: Takt | None = None
    #: „Weiter, wenn …“ nur hier (P97, 8.11.2026; Paketfeld ``bedingung`` je Planübung) —
    #: ``None`` = wie die Übung; ``dann``/``sonst`` zeigen im Paket auf die **Position** der
    #: Planübung (``"#3"``), in der App auf ihre ID (`verweise_als_position`, `verweise_aufloesen`)
    bedingung: Weiterbedingung | None = None
    #: Beiname im Ablaufbild (G4, Paketfeld ``beiname`` je Planübung) — leer = keiner
    beiname: str = ""
    #: Eigene Inhalte der Planübung (U2, Paketfelder ``beschreibung`` und ``medien`` je
    #: Planübung, `docs/plan_paketinhalte.md` §9): Abschnitte und Medien für diesen Plan
    beschreibung: str = ""
    medien: list[Media] = field(default_factory=list)

    @classmethod
    def aus_planitem(cls, item: PlanItem) -> VorlageItem:
        """Die Planübung der App als Vorlage: Ziel, Felder, Sensor und Takt nur, wo sie eigene
        hat (sonst folgt sie der Übung, P79) — Export, `paket_werkzeug uebernehmen`."""
        return cls(
            exercise_id=item.exercise_id,
            target=dict(item.target) if item.target else {},
            felder=None if item.felder is None else list(item.felder),
            beschleunigung=item.acc,
            takt=item.takt,
            bedingung=None if item.bedingung.leer else item.bedingung,
            beiname=item.beiname,
            beschreibung=item.description,
            medien=[m for m in item.media if m.source != MediaSource.LOCAL],
        )

    def als_planitem(self, plan_id: str, order: int) -> PlanItem:
        """Die Planübung zu dieser Vorlage — das Gegenstück zu `aus_planitem`, für Kurskapitel
        (`plan_aus_vorlage`) und Paketpläne (`data.pakete`) gleichermaßen: ohne Ziel folgt
        die Planübung der Übung (P79), Sensor-Karte und Takt kommen mit (A6, Prüfrunde:
        ein Paketplan ohne sie galt bei der nächsten Fassung als von der Person geändert).

        >>> i = VorlageItem("a", target={"reps": 10}, takt=AUS).als_planitem("p1", 2)
        >>> (i.plan_id, i.exercise_id, i.order, i.target, i.felder, i.acc, i.takt is AUS)
        ('p1', 'a', 2, {'reps': 10}, None, None, True)
        >>> VorlageItem("a").als_planitem("p1", 0).target is None
        True
        """
        return PlanItem(
            plan_id=plan_id,
            exercise_id=self.exercise_id,
            order=order,
            target=dict(self.target) if self.target else None,
            felder=None if self.felder is None else list(self.felder),
            acc=self.beschleunigung,
            takt=self.takt,
            bedingung=self.bedingung if self.bedingung is not None else Weiterbedingung(),
            beiname=self.beiname,
            description=self.beschreibung,
            media=list(self.medien),
        )

    def to_dict(self, uebung: str | None = None) -> dict[str, Any]:
        """Der Eintrag in ``uebungen[]`` — ``uebung`` ersetzt die ID (Paketschlüssel).

        >>> VorlageItem("a", takt=AUS).to_dict()
        {'uebung': 'a', 'takt': {}}
        >>> VorlageItem("a", felder=[], beschleunigung=SensorWahl(atmung=True)).to_dict("k")
        {'uebung': 'k', 'felder': [], 'beschleunigung': {'atmung': True}}
        """
        d: dict[str, Any] = {"uebung": uebung or self.exercise_id}
        if self.target:
            d["ziel"] = dict(self.target)
        if self.felder is not None:
            d["felder"] = list(self.felder)
        if self.beschleunigung is not None:
            d["beschleunigung"] = self.beschleunigung.als_dict()
        if self.takt is not None:
            d["takt"] = {} if self.takt.leer else self.takt.als_dict()
        if self.bedingung is not None and not self.bedingung.leer:
            d["bedingung"] = self.bedingung.als_dict()
        if self.beiname:
            d["beiname"] = self.beiname
        if self.beschreibung:
            d["beschreibung"] = self.beschreibung
        if self.medien:
            d["medien"] = [m.als_dict() for m in self.medien]
        return d

    @classmethod
    def from_dict(cls, e: Mapping[str, Any]) -> VorlageItem:
        """Liest, was `to_dict` schreibt — tolerant: ``beschleunigung``/``takt`` nur als
        Tabelle (sonst wie die Übung). ``takt = {}`` ist ausdrücklich keiner; eine Takt-Tabelle
        ohne brauchbare Phase heißt **wie die Übung**, nie „keiner“ (sonst schaltete ein
        Tippfehler im Paket den Takt der Übung in diesem Plan ab). Eine Tabelle
        ``beschleunigung`` ist immer eine eigene Karte — Unbrauchbares darin gilt als Vorgabe,
        wie an der Übung (`SensorWahl.aus_dict`).

        >>> i = VorlageItem.from_dict({"uebung": "a", "takt": {}, "beschleunigung": "x"})
        >>> i.takt.leer, i.beschleunigung
        (True, None)
        >>> VorlageItem.from_dict({"uebung": "a", "takt": {"phasen": "x"}}).takt is None
        True
        """
        felder = e.get("felder")
        acc, takt, bed = e.get("beschleunigung"), e.get("takt"), e.get("bedingung")
        return cls(
            exercise_id=str(e["uebung"]),
            target=dict(e.get("ziel") or {}),
            felder=None if felder is None else [str(k) for k in felder],
            beschleunigung=SensorWahl.aus_dict(acc) if isinstance(acc, Mapping) else None,
            takt=_takt_lesen(takt),
            bedingung=Weiterbedingung.aus_dict(bed) if isinstance(bed, Mapping) and bed else None,
            beiname=str(e.get("beiname") or "").strip(),
            beschreibung=str(e.get("beschreibung") or "").strip(),
            medien=_medien_lesen(e.get("medien")),
        )


def _medien_lesen(roh: Any) -> list[Media]:
    """Medien einer Planübung aus dem Paket — nur, was die App öffnen darf (`links.erlaubt`),
    nie Dateien vom Ursprungsgerät; Unbrauchbares fällt still weg (wie `core.pakete._medium`).

    >>> [m.uri for m in _medien_lesen([{"uri": "https://x.org/v"}, {"uri": "intent://x"}])]
    ['https://x.org/v']
    """
    out: list[Media] = []
    for e in roh if isinstance(roh, list) else []:
        m = medium_aus_dict(dict(e) if isinstance(e, Mapping) else None)
        if m is not None and m.source == MediaSource.PAKET:  # eine Datei aus dem Paket (U3)
            if (aus_paket := medium_aus_paket(dict(e))) is not None:
                out.append(aus_paket)
            continue
        if m is None or m.source == MediaSource.LOCAL or not links.erlaubt(m.uri):
            continue
        if m.kind == MediaKind.AUDIO:
            continue
        out.append(m)
    return out


def verweise_als_position(items: list[VorlageItem], ids: Sequence[str]) -> list[VorlageItem]:
    """Export: ``dann``/``sonst`` der Bedingungen von Planübungs-IDs auf Positionen (``"#2"``,
    1-basiert) — ein Paket kennt keine IDs. Unbekannte Verweise fallen weg.

    >>> from trainingsapp.core.bedingung import WDH
    >>> v = [VorlageItem("a", bedingung=Weiterbedingung(WDH, 5, sonst="i2")), VorlageItem("b")]
    >>> verweise_als_position(v, ["i1", "i2"])[0].bedingung.sonst
    '#2'
    """
    stelle = {i: f"#{n}" for n, i in enumerate(ids, start=1)}
    out: list[VorlageItem] = []
    for it in items:
        b = it.bedingung
        if b is not None and (b.dann or b.sonst or b.wege):
            b = replace(
                b,
                dann=stelle.get(b.dann, ""),
                sonst=stelle.get(b.sonst, ""),
                wege=tuple(replace(w, ziel=stelle[w.ziel]) for w in b.wege if w.ziel in stelle),
            )
        out.append(replace(it, bedingung=b))
    return out


def verweise_aufloesen(items: list[PlanItem], positionen: Sequence[int]) -> None:
    """Import: ``"#n"`` → die ID der Planübung, die aus Position n entstand (``positionen[k]``
    = Position der k-ten Planübung in der Vorlage, 1-basiert); fehlt sie (Übung nicht da),
    fällt der Verweis weg.

    >>> from trainingsapp.core.bedingung import WDH
    >>> a = PlanItem(id="i1", bedingung=Weiterbedingung(WDH, 5, sonst="#2"))
    >>> b = PlanItem(id="i2")
    >>> verweise_aufloesen([a, b], [1, 2]); a.bedingung.sonst
    'i2'
    """
    ziel = {f"#{pos}": it.id for it, pos in zip(items, positionen, strict=False)}
    for it in items:
        b = it.bedingung
        offen = b.dann.startswith("#") or b.sonst.startswith("#")
        if offen or any(w.ziel.startswith("#") for w in b.wege):
            it.bedingung = replace(
                b,
                dann=ziel.get(b.dann, "") if b.dann.startswith("#") else b.dann,
                sonst=ziel.get(b.sonst, "") if b.sonst.startswith("#") else b.sonst,
                wege=tuple(
                    replace(w, ziel=ziel[w.ziel]) if w.ziel.startswith("#") else w
                    for w in b.wege
                    if not w.ziel.startswith("#") or w.ziel in ziel
                ),
            )


def _takt_lesen(roh: Any) -> Takt | None:
    """Das Paketfeld ``takt`` einer Planübung: keine Tabelle oder keine brauchbare Phase =
    wie die Übung (``None``), ``{}`` = ausdrücklich keiner (`AUS`).

    >>> _takt_lesen(None), _takt_lesen(3), _takt_lesen({"phasen": []}), _takt_lesen({}) is AUS
    (None, None, None, True)
    """
    if not isinstance(roh, Mapping):
        return None
    if not roh:
        return AUS
    return Takt.aus_dict(roh)


@dataclass(slots=True)
class PlanVorlage:
    """Ein Plan, den ein Kapitel beim Erreichen anlegt (`plan_aus_vorlage`)."""

    name: str
    wochentage: list[int] = field(default_factory=lambda: list(range(7)))
    items: list[VorlageItem] = field(default_factory=list)
    #: Der gezeichnete Ablauf (G4, `docs/plan_verzweigungen.md` §8): `core.ablauf.als_position`
    #: — Planübungen als ``"#n"``, Fragen als ``"?n"``; ``None`` = Kette
    ablauf: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "wochentage": list(self.wochentage)}
        d["uebungen"] = [i.to_dict() for i in self.items]
        if self.ablauf:
            d["ablauf"] = dict(self.ablauf)
        return d

    @classmethod
    def from_dict(cls, roh: Mapping[str, Any]) -> PlanVorlage:
        """Liest, was `to_dict` schreibt — Wochentage außerhalb 0–6 fallen weg.

        >>> v = PlanVorlage.from_dict({"name": "Atmung", "wochentage": [0, 2, 9]})
        >>> v.wochentage, v.items
        ([0, 2], [])
        """
        tage = roh.get("wochentage")
        wochentage = (
            sorted({int(t) for t in tage if isinstance(t, int) and 0 <= t <= 6})
            if isinstance(tage, list)
            else list(range(7))
        )
        items = [
            VorlageItem.from_dict(e)
            for e in roh.get("uebungen", []) or []
            if isinstance(e, Mapping) and e.get("uebung")
        ]
        ablauf = roh.get("ablauf")
        vorlage = cls(
            name=str(roh.get("name") or "Plan"),
            wochentage=wochentage,
            items=items,
            ablauf=dict(ablauf) if isinstance(ablauf, Mapping) and ablauf else None,
        )
        vorlage.zweige_als_ablauf()
        return vorlage

    def zweige_als_ablauf(self) -> None:
        """Alte Zweige und Verweise einer Paketfassung (``zweig``, ``dann``, ``sonst``, ``wege``,
        Positionen „#n“) werden Kanten im Ablauf (P108, Datenschritt 6 für Pakete) — die
        Bedingungen behalten Art, Zahl, Pflicht und Inhalt.

        >>> from trainingsapp.core.bedingung import WDH, Weg
        >>> v = PlanVorlage("P", items=[VorlageItem("a", bedingung=Weiterbedingung(
        ...     WDH, 5, wege=(Weg("#1", "noch mal"),))), VorlageItem("b")])
        >>> v.zweige_als_ablauf()
        >>> v.ablauf["start"], [(k["von"], k["nach"]) for k in v.ablauf["kanten"]]
        ('#1', [('#1', '#2'), ('#1', '#1')])
        >>> v.items[0].bedingung.wege
        ()
        """
        paare = [
            (f"#{n}", it.bedingung or Weiterbedingung()) for n, it in enumerate(self.items, start=1)
        ]
        if self.ablauf or not any(ab.hat_verzweigung(b) for _, b in paare):
            return
        self.ablauf = ab.aus_bedingungen(paare).als_dict()
        for it in self.items:
            if it.bedingung is not None and ab.hat_verzweigung(it.bedingung):
                rest = ab.ohne_verzweigung(it.bedingung)
                it.bedingung = None if rest.leer else rest


@dataclass(slots=True)
class Kapitel:
    id: str = field(default_factory=new_id)
    kurs_id: str = ""
    order: int = 0
    titel: str = ""
    #: Erklärtext als Markdown (`ft.Markdown` zeigt ihn an)
    text: str = ""
    media: list[Media] = field(default_factory=list)
    plaene: list[PlanVorlage] = field(default_factory=list)
    bedingung: Bedingung = field(default_factory=Bedingung)

    @property
    def uebungen(self) -> set[str]:
        """Die Übungen aller Plan-Vorlagen — für die Bedingung ``tage``."""
        return {i.exercise_id for p in self.plaene for i in p.items}


@dataclass(slots=True)
class Kurs:
    id: str = field(default_factory=new_id)
    name: str = ""
    beschreibung: str = ""
    freischaltung: str = RUECKFRAGE
    kapitel: list[Kapitel] = field(default_factory=list)
    #: Aus welchem Paket der Kurs kam (`core/pakete.py`); ``None`` = eigener Kurs
    package_id: str | None = None
    created_at: datetime = field(default_factory=jetzt)
    updated_at: datetime = field(default_factory=jetzt)
    deleted_at: datetime | None = None

    def kapitel_mit(self, kapitel_id: str) -> Kapitel | None:
        return next((k for k in self.kapitel if k.id == kapitel_id), None)


@dataclass(slots=True)
class Kapitelstand:
    """Der Fortschritt eines Profils in einem Kapitel (Tabelle ``course_progress``)."""

    kapitel_id: str
    erreicht: datetime
    abgeschlossen: datetime | None = None
    uebersprungen: bool = False


@dataclass(slots=True)
class Stand:
    """Wie weit eine Bedingung erfüllt ist: ``ist`` von ``soll``."""

    ist: float = 0.0
    soll: float = 0.0

    @property
    def erfuellt(self) -> bool:
        return self.ist >= self.soll

    @property
    def fehlt(self) -> float:
        return max(self.soll - self.ist, 0.0)


# ---------------------------------------------------------------------------
# Status der Kapitel
# ---------------------------------------------------------------------------


def status(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> dict[str, str]:
    """Status je Kapitel-ID: fertig, übersprungen, aktuell, offen oder gesperrt.

    Abgeschlossene Kapitel sind ``fertig`` (oder ``uebersprungen``); das erste
    nicht abgeschlossene ist ``aktuell``; alles danach ``gesperrt`` — bei
    Freischaltung „frei“ stattdessen ``offen``.

    >>> k = Kurs(kapitel=[Kapitel(titel=t) for t in "ABC"])
    >>> a, b, c = k.kapitel
    >>> fertig = Kapitelstand(a.id, jetzt(), abgeschlossen=jetzt())
    >>> [status(k, {a.id: fertig})[x.id] for x in (a, b, c)]
    ['fertig', 'aktuell', 'gesperrt']
    >>> k.freischaltung = FREI
    >>> status(k, {})[c.id]
    'offen'
    """
    ergebnis: dict[str, str] = {}
    aktuell_vergeben = False
    for kapitel in kurs.kapitel:
        stand = staende.get(kapitel.id)
        if stand is not None and stand.abgeschlossen is not None:
            ergebnis[kapitel.id] = UEBERSPRUNGEN if stand.uebersprungen else FERTIG
        elif not aktuell_vergeben:
            ergebnis[kapitel.id] = AKTUELL
            aktuell_vergeben = True
        else:
            ergebnis[kapitel.id] = OFFEN if kurs.freischaltung == FREI else GESPERRT
    return ergebnis


def aktuelles(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> Kapitel | None:
    """Das Kapitel, das gerade dran ist — ``None``, wenn der Kurs abgeschlossen ist."""
    stati = status(kurs, staende)
    return next((k for k in kurs.kapitel if stati[k.id] == AKTUELL), None)


def naechstes(kurs: Kurs, kapitel: Kapitel) -> Kapitel | None:
    """Das Kapitel nach diesem — ``None`` am Ende.

    >>> k = Kurs(kapitel=[Kapitel(titel="A"), Kapitel(titel="B")])
    >>> naechstes(k, k.kapitel[0]).titel, naechstes(k, k.kapitel[1])
    ('B', None)
    """
    ids = [k.id for k in kurs.kapitel]
    if kapitel.id not in ids:
        return None
    i = ids.index(kapitel.id) + 1
    return kurs.kapitel[i] if i < len(kurs.kapitel) else None


def begonnen(staende: Mapping[str, Kapitelstand]) -> bool:
    return bool(staende)


def abgeschlossen(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> bool:
    """Alle Kapitel abgeschlossen (auch übersprungen) — und es gibt welche."""
    return bool(kurs.kapitel) and all(
        (s := staende.get(k.id)) is not None and s.abgeschlossen is not None for k in kurs.kapitel
    )


def fortschritt_text(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> str:
    """„noch nicht begonnen“, „Kapitel 3 von 7“, „abgeschlossen“.

    >>> k = Kurs(kapitel=[Kapitel(titel=t) for t in "ABC"])
    >>> fortschritt_text(k, {})
    'noch nicht begonnen'
    >>> a = k.kapitel[0]
    >>> fortschritt_text(k, {a.id: Kapitelstand(a.id, jetzt(), abgeschlossen=jetzt())})
    'Kapitel 2 von 3'
    """
    if not kurs.kapitel:
        return "noch ohne Kapitel"
    if not begonnen(staende):
        return "noch nicht begonnen"
    if abgeschlossen(kurs, staende):
        return "abgeschlossen"
    aktuell = aktuelles(kurs, staende)
    nummer = kurs.kapitel.index(aktuell) + 1 if aktuell is not None else len(kurs.kapitel)
    return f"Kapitel {nummer} von {len(kurs.kapitel)}"


# ---------------------------------------------------------------------------
# Bedingung rechnen
# ---------------------------------------------------------------------------


def bedingung_stand(
    bedingung: Bedingung,
    seit: datetime | None,
    eintraege: Iterable[tuple[date, SessionEntry]] = (),
    messungen: Iterable[HrvRecording] = (),
    plan_uebungen: Iterable[str] = (),
) -> Stand:
    """Wie weit die Bedingung erfüllt ist — gerechnet ab ``seit`` (Kapitelstart).

    ``eintraege`` sind gültige Einträge mit ihrem lokalen Tag (wie
    `SessionRepo.eintraege_zwischen`), ``plan_uebungen`` die Übungen der Kapitelpläne (für ``tage``;
    leer = jeder Eintrag zählt). ``seit=None`` heißt: Kapitel noch nicht
    erreicht — nichts zählt.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> from datetime import UTC, timedelta
    >>> t0 = datetime(2026, 10, 12, 8, tzinfo=UTC)
    >>> e = [(date(2026, 10, 12 + i), SessionEntry(exercise_id="l", result={"reps": [20, 20]},
    ...       spec_snapshot=SPEC_SAETZE_WDH, started_at=t0 + timedelta(days=i))) for i in range(3)]
    >>> b = Bedingung(SUMME, "l", "reps", 100)
    >>> s = bedingung_stand(b, t0, e)
    >>> (s.ist, s.soll, s.erfuellt)
    (120.0, 100.0, True)
    >>> bedingung_stand(b, t0 + timedelta(days=1), e).ist  # ab Tag 2
    80.0
    >>> bedingung_stand(Bedingung(TAGE, soll=3), t0, e).ist
    3.0
    >>> bedingung_stand(Bedingung(GELESEN), None).erfuellt
    True
    """
    if bedingung.art == GELESEN:
        return Stand(0.0, 0.0)
    soll = float(bedingung.soll)
    if seit is None:
        return Stand(0.0, soll)
    ab = [(t, e) for t, e in eintraege if e.started_at is not None and e.started_at >= seit]
    if bedingung.art == SUMME:
        summe = sum(
            mengen(e.spec_snapshot, e.result).get(bedingung.feld, 0.0)
            for _, e in ab
            if e.exercise_id == bedingung.exercise_id
        )
        return Stand(summe, soll)
    if bedingung.art == TAGE:
        ids = set(plan_uebungen)
        tage = {t for t, e in ab if not ids or e.exercise_id in ids}
        return Stand(float(len(tage)), soll)
    if bedingung.art == MESSUNG:
        passt = any(m.started_at >= seit and m.duration_s >= soll * 60 for m in messungen)
        return Stand(soll if passt else 0.0, soll)
    return Stand(0.0, soll)


def bedingung_text(bedingung: Bedingung, uebung: Exercise | None = None) -> str:
    """Die Bedingung in Worten: „100 Wdh. Liegestütz“, „an 3 Tagen üben“, „5 min messen“.

    >>> bedingung_text(Bedingung(TAGE, soll=3))
    'an 3 Tagen üben'
    >>> bedingung_text(Bedingung(MESSUNG, soll=5))
    'eine HRV-Messung von 5 min'
    >>> bedingung_text(Bedingung(SUMME, "l", "reps", 100), Exercise(name="Liegestütz"))
    '100 Wdh. Liegestütz'
    """
    if bedingung.art == SUMME:
        name = uebung.name if uebung is not None else "der Übung"
        return f"{menge_text(_feld(bedingung, uebung), bedingung.soll)} {name}"
    if bedingung.art == TAGE:
        n = int(bedingung.soll)
        return f"an {n} {'Tag' if n == 1 else 'Tagen'} üben"
    if bedingung.art == MESSUNG:
        return f"eine HRV-Messung von {bedingung.soll:g} min"
    return "Kapitel ansehen"


def stand_text(bedingung: Bedingung, stand: Stand, uebung: Exercise | None = None) -> str:
    """„60 von 100 Wdh.“, „2 von 3 Tagen“, „noch keine Messung von 5 min“.

    >>> stand_text(Bedingung(SUMME, "l", "reps", 100), Stand(60, 100))
    '60 von 100 Wdh.'
    >>> stand_text(Bedingung(TAGE, soll=3), Stand(3, 3))
    '3 von 3 Tagen'
    >>> stand_text(Bedingung(MESSUNG, soll=5), Stand(0, 5))
    'noch keine Messung von 5 min'
    """
    if bedingung.art == SUMME:
        f = _feld(bedingung, uebung)
        return f"{menge_text(f, stand.ist).split(' ', 1)[0]} von {menge_text(f, stand.soll)}"
    if bedingung.art == TAGE:
        return f"{stand.ist:g} von {stand.soll:g} Tagen"
    if bedingung.art == MESSUNG:
        if stand.erfuellt:
            return f"Messung von {stand.soll:g} min liegt vor"
        return f"noch keine Messung von {stand.soll:g} min"
    return ""


def fehlt_text(bedingung: Bedingung, stand: Stand, uebung: Exercise | None = None) -> str:
    """Was zum Freischalten noch fehlt — für die Rückfrage beim Überspringen.

    >>> fehlt_text(Bedingung(SUMME, "l", "reps", 100), Stand(40, 100))
    'Noch 60 Wdh.'
    >>> fehlt_text(Bedingung(TAGE, soll=3), Stand(1, 3))
    'Noch 2 Tage'
    """
    if bedingung.art == SUMME:
        return f"Noch {menge_text(_feld(bedingung, uebung), stand.fehlt)}"
    if bedingung.art == TAGE:
        n = int(stand.fehlt)
        return f"Noch {n} {'Tag' if n == 1 else 'Tage'}"
    if bedingung.art == MESSUNG:
        return f"Noch keine Messung von {stand.soll:g} min"
    return ""


def _feld(bedingung: Bedingung, uebung: Exercise | None) -> FieldSpec:
    f = uebung.result_spec.field_by_key(bedingung.feld) if uebung is not None else None
    if f is None:
        f = vorrat_feld(bedingung.feld)
    return f or FieldSpec(key=bedingung.feld, type=FieldType.FLOAT, label=bedingung.feld)


# ---------------------------------------------------------------------------
# Pläne aus Vorlagen
# ---------------------------------------------------------------------------


def ids_uebernehmen(items: Sequence[PlanItem], alt: Plan | None) -> None:
    """Die neuen Planübungen bekommen die IDs der bisherigen — je Übung in der Reihenfolge ihres
    Vorkommens (U2: Einträge und Wege zeigen auf die ID, ein Update darf sie nicht wechseln).

    >>> alt = Plan(items=[PlanItem(id="p1", exercise_id="a"), PlanItem(id="p2", exercise_id="a")])
    >>> neu = [PlanItem(exercise_id="b"), PlanItem(exercise_id="a"), PlanItem(exercise_id="a")]
    >>> ids_uebernehmen(neu, alt)
    >>> [i.id for i in neu[1:]]
    ['p1', 'p2']
    """
    if alt is None:
        return
    frei: dict[str, list[str]] = {}
    for vorher in sorted(alt.items, key=lambda i: i.order):
        frei.setdefault(vorher.exercise_id, []).append(vorher.id)
    for planuebung in items:
        if ids := frei.get(planuebung.exercise_id):
            planuebung.id = ids.pop(0)


def plan_aus_vorlage(
    vorlage: PlanVorlage,
    kapitel: Kapitel,
    subject_id: str,
    vorhandene: Iterable[str],
    alt: Plan | None = None,
) -> Plan:
    """Der echte Plan zu einer Vorlage — nur mit Übungen, die es hier gibt. ``alt``: der
    bisherige Plan („Kapitelplan neu laden“) — seine Planübungen behalten ihre IDs.

    >>> v = PlanVorlage("Atmung", [0, 2, 4], [VorlageItem("a"), VorlageItem("fehlt")])
    >>> p = plan_aus_vorlage(v, Kapitel(id="k1"), "s1", {"a"})
    >>> (p.name, p.wochentage, [i.exercise_id for i in p.items], p.kurs_kapitel_id)
    ('Atmung', [0, 2, 4], ['a'], 'k1')
    """
    da = set(vorhandene)
    plan = Plan(
        name=vorlage.name,
        subject_id=subject_id,
        wochentage=list(vorlage.wochentage),
        kurs_kapitel_id=kapitel.id,
    )
    positionen: list[int] = []
    for pos, item in enumerate(vorlage.items, start=1):
        if item.exercise_id in da:
            plan.items.append(item.als_planitem(plan.id, len(plan.items)))
            positionen.append(pos)
    ids_uebernehmen(plan.items, alt)
    verweise_aufloesen(plan.items, positionen)
    ablauf_aufloesen(plan, vorlage, positionen)
    return plan


def ablauf_aufloesen(plan: Plan, vorlage: PlanVorlage, positionen: Sequence[int]) -> None:
    """Import: der gezeichnete Ablauf der Vorlage (Positionen) wird der des Plans (IDs)."""
    if vorlage.ablauf:
        plan.ablauf = ab.aus_position(vorlage.ablauf, [it.id for it in plan.items], positionen)


# ---------------------------------------------------------------------------
# Medien als JSON (Spalte `course_chapter.media_json`)
# ---------------------------------------------------------------------------


def medien_to_list(media: Iterable[Media]) -> list[dict[str, Any]]:
    return [
        {
            "kind": str(m.kind),
            "source": str(m.source),
            "uri": m.uri,
            "title": m.title,
            **({"license": m.license} if m.license else {}),
        }
        for m in media
        if m.uri
    ]


def medien_from_list(roh: Any) -> list[Media]:
    """Liest Medien; Unlesbares fällt weg, Dateien vom Ursprungsgerät (``local``) auch.

    Ebenso ein Link, den die App nicht öffnen darf (`links.erlaubt`: nur ``https://``
    und ``mailto:``) — still, damit ein ``intent://`` im Paket nicht das Kapitel kostet
    (S1). Das gilt beim Import wie beim Lesen aus der Datenbank.

    >>> roh = [{"kind": "audio", "uri": "https://x/a.mp3"}, {"uri": ""}]
    >>> [str(m.kind) for m in medien_from_list(roh)]
    ['audio']
    >>> medien_from_list([{"uri": "intent://scan/#Intent;end"}])
    []
    """
    ergebnis: list[Media] = []
    if not isinstance(roh, list):
        return ergebnis
    for d in roh:
        if not isinstance(d, Mapping):
            continue
        uri = str(d.get("uri") or "").strip()
        try:
            art = MediaKind(d.get("kind", "video"))
            quelle = MediaSource(d.get("source", "url"))
        except ValueError:
            continue
        if quelle == MediaSource.PAKET:  # eine Datei aus dem Paket (U3)
            if (aus_paket := medium_aus_paket(d)) is not None:
                ergebnis.append(aus_paket)
            continue
        if not uri or quelle == MediaSource.LOCAL or not links.erlaubt(uri):
            continue
        ergebnis.append(
            Media(
                kind=art,
                source=quelle,
                uri=uri,
                title=str(d.get("title") or ""),
                license=str(d.get("license") or ""),
            )
        )
    return ergebnis


__all__ = [
    "AKTUELL",
    "BEDINGUNGEN",
    "FERTIG",
    "FREI",
    "FREISCHALTUNGEN",
    "GELESEN",
    "GESPERRT",
    "MESSUNG",
    "OFFEN",
    "RUECKFRAGE",
    "STRENG",
    "SUMME",
    "TAGE",
    "UEBERSPRUNGEN",
    "Bedingung",
    "Kapitel",
    "Kapitelstand",
    "Kurs",
    "PlanVorlage",
    "Stand",
    "VorlageItem",
    "abgeschlossen",
    "aktuelles",
    "bedingung_stand",
    "bedingung_text",
    "begonnen",
    "fehlt_text",
    "fortschritt_text",
    "ids_uebernehmen",
    "medien_from_list",
    "medien_to_list",
    "naechstes",
    "plan_aus_vorlage",
    "stand_text",
    "status",
]
