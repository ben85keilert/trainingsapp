"""Domänenmodelle.

Reine Wertetypen ohne Datenbank- und ohne UI-Bezug. Das Laden und Speichern
macht `data/repositories.py`.

IDs sind **UUIDv7**: zeitsortiert, dadurch bessere Index-Lokalität in SQLite und
eine natürliche Sortierung ohne zusätzliche Spalte. Python bringt UUIDv7 noch
nicht mit, deshalb `new_id()` unten.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from .ablauf import Ablauf
from .bedingung import Bedingung
from .gps_wahl import GpsWahl
from .result_spec import ResultSpec
from .takt import Takt
from .zaehlen import SensorWahl


def new_id() -> str:
    """Erzeugt eine UUIDv7 als Zeichenkette.

    Aufbau nach RFC 9562: 48 Bit Unix-Millisekunden, 4 Bit Version, 12 Bit
    Zufall, 2 Bit Variante, 62 Bit Zufall. Zwei IDs aus derselben Millisekunde
    sortieren zufällig zueinander, IDs aus verschiedenen Millisekunden korrekt
    nach Zeit.
    """
    ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF
    rand = int.from_bytes(os.urandom(10), "big")

    wert = ms << 80
    wert |= 0x7 << 76  # Version 7
    wert |= ((rand >> 66) & 0xFFF) << 64  # rand_a
    wert |= 0b10 << 62  # Variante RFC 4122
    wert |= rand & ((1 << 62) - 1)  # rand_b
    return str(uuid.UUID(int=wert))


def jetzt() -> datetime:
    return datetime.now(UTC)


def iso_utc(zeit: datetime) -> str:
    """Zeitstempel für die Datenbank: immer UTC, immer ``+00:00``.

    Tagesabfragen vergleichen ISO-Strings gegen die UTC-Grenzen aus
    `tagesgrenzen`; ein Stempel mit anderem Versatz (``23:30+02:00``) stünde
    im Text hinter ``22:00+00:00`` und fiele aus seinem Tag (Befund D2,
    19.10.2026). Darum normieren alle Schreibpfade hier, nicht die Aufrufer.
    Ein naiver Zeitpunkt gilt als Ortszeit.

    >>> from datetime import timedelta, timezone
    >>> iso_utc(datetime(2026, 10, 18, 23, 30, tzinfo=timezone(timedelta(hours=2))))
    '2026-10-18T21:30:00+00:00'
    """
    return zeit.astimezone(UTC).isoformat()


def lokaler_tag(zeit: datetime) -> date:
    """Der Kalendertag, zu dem ein Zeitpunkt in der Zeitzone des Geräts gehört.

    Zeitstempel liegen in UTC vor (`jetzt()`); „heute" ist aber ein lokaler
    Tag. Ein Training um 23:30 Ortszeit gehört zu diesem Tag, auch wenn es in
    UTC schon der nächste ist.
    """
    return zeit.astimezone().date()


def tagesgrenzen(tag: date) -> tuple[datetime, datetime]:
    """Anfang und Ende eines lokalen Kalendertags als UTC-Zeitpunkte.

    Alle Tagesabfragen laufen hierüber — nie über ``date.today()`` in SQL.
    Das Ende ist die nächste lokale Mitternacht (exklusiv), damit auch
    Tage mit Zeitumstellung 23 oder 25 Stunden lang sind, nicht 24.

    >>> von, bis = tagesgrenzen(date(2026, 10, 12))
    >>> (bis - von).total_seconds() in (82800.0, 86400.0, 90000.0)
    True
    >>> lokaler_tag(von) == date(2026, 10, 12)
    True
    """
    mitternacht = datetime.min.time()
    start = datetime.combine(tag, mitternacht).astimezone()
    ende = datetime.combine(tag + timedelta(days=1), mitternacht).astimezone()
    return start.astimezone(UTC), ende.astimezone(UTC)


# ---------------------------------------------------------------------------
# Übungen
# ---------------------------------------------------------------------------


class MediaKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    #: Als Link nur an Kurskapiteln (`core/kurse.py`); als Datei aus einem Paket überall (U3)
    AUDIO = "audio"
    #: Ein Dokument aus einem Paket — Material beim Üben (U3, F6)
    PDF = "pdf"


class MediaSource(StrEnum):
    URL = "url"  # online, wird bei Bedarf geladen und gecacht
    ASSET = "asset"  # mit der App ausgeliefert
    LOCAL = "local"  # vom Nutzer aufgenommen, app-privates Verzeichnis
    #: Eine Datei aus einem Paket (U3, Migration 047): ``uri`` = ``medien/<sha256>.<endung>``,
    #: abgelegt unter `config.paketmedienverzeichnis()` (`data/paketmedien.py`)
    PAKET = "paket"


#: Arten eines Ereignisses, zu dem sich ein Stück zeigt (`Ereignis.art`)
E_ABSCHNITT = "abschnitt"
E_SATZ = "satz"
E_ZEIT = "zeit"
E_WDH = "wdh"
E_ANTWORT = "antwort"
EREIGNIS_ARTEN = (E_ABSCHNITT, E_SATZ, E_ZEIT, E_WDH, E_ANTWORT)


@dataclass(frozen=True, slots=True)
class Ereignis:
    """Wozu ein Stück mit ``wann = "bei"`` aufgeht (Ben, 18.11.2026: „zu bestimmten Ereignissen …
    wenn Wahl für hier und da/Wdh oder Zeit soundso → Video“; `docs/plan_medien_zeitpunkte.md`
    §2): der Timer-Abschnitt ``name`` beginnt · Satz ``n`` beginnt · die Uhr läuft seit
    ``sekunden`` · ``n`` Wiederholungen sind gezählt · eine der ``antworten`` einer Frage des
    Ablaufs ist gewählt. Gerechnet aus Uhr, Zählung und Wahl — **nie aus Messwerten**.

    >>> Ereignis(E_ABSCHNITT, name="Pause").als_dict()
    {'art': 'abschnitt', 'name': 'Pause'}
    >>> Ereignis.aus({"art": "wdh", "n": "10", "name": "x"})
    Ereignis(art='wdh', name='', n=10, sekunden=0.0, antworten=())
    >>> Ereignis.aus({"art": "antwort", "antworten": ["Knie zwickt", " "]}).text()
    'bei der Antwort „Knie zwickt“'
    >>> Ereignis.aus({"art": "zeit", "sekunden": 90}).text()
    'nach 1:30'
    >>> Ereignis.aus({"art": "satz", "n": 2}).text()
    'wenn Satz 2 beginnt'
    >>> Ereignis.aus({"art": "tanz"}) is None, Ereignis.aus({"art": "satz"}) is None
    (True, True)
    """

    art: str = ""
    name: str = ""
    n: int = 0
    sekunden: float = 0.0
    antworten: tuple[str, ...] = ()

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"art": self.art}
        if self.art == E_ABSCHNITT:
            d["name"] = self.name
        elif self.art in (E_SATZ, E_WDH):
            d["n"] = self.n
        elif self.art == E_ZEIT:
            d["sekunden"] = self.sekunden
        elif self.art == E_ANTWORT:
            d["antworten"] = list(self.antworten)
        return d

    @staticmethod
    def aus(roh: Any) -> Ereignis | None:
        """Aus der Wörterbuch-Form — ``None``, wenn die Art unbekannt ist oder ihr Wert fehlt."""
        hat = getattr(roh, "get", None)
        if hat is None:
            return None
        art = str(hat("art") or "")
        try:
            if art == E_ABSCHNITT:
                name = str(hat("name") or "").strip()
                return Ereignis(art, name=name) if name else None
            if art in (E_SATZ, E_WDH):
                n = int(hat("n") or 0)
                return Ereignis(art, n=n) if n > 0 else None
            if art == E_ZEIT:
                s = float(hat("sekunden") or 0)
                return Ereignis(art, sekunden=s) if s > 0 else None
            if art == E_ANTWORT:
                roh_liste = hat("antworten") or ()
                if isinstance(roh_liste, str):
                    roh_liste = [roh_liste]
                antworten = tuple(a for x in roh_liste if (a := str(x).strip()))
                return Ereignis(art, antworten=antworten) if antworten else None
        except (TypeError, ValueError):
            return None
        return None

    def text(self) -> str:
        """In Worten, für Editor und Übersicht."""
        if self.art == E_ABSCHNITT:
            return f"wenn „{self.name}“ beginnt"
        if self.art == E_SATZ:
            return f"wenn Satz {self.n} beginnt"
        if self.art == E_ZEIT:
            s = int(self.sekunden)
            return f"nach {s // 60}:{s % 60:02d}"
        if self.art == E_WDH:
            return f"ab {self.n} Wiederholungen"
        if self.art == E_ANTWORT:
            return "bei der Antwort " + " · ".join(f"„{a}“" for a in self.antworten)
        return ""


@dataclass(slots=True)
class Media:
    """Ein Video oder Bild zu einer Übung oder einem Trainingseintrag."""

    id: str = field(default_factory=new_id)
    kind: MediaKind = MediaKind.VIDEO
    source: MediaSource = MediaSource.URL
    uri: str = ""
    title: str = ""
    license: str = ""
    #: Wozu das Stück beim Üben dient (Ben, 12.11.2026, `core.material`): leer = **Erklärung**
    #: (ansehen, abhaken), ``"begleitung"`` = läuft beim Üben mit, die Uhr läuft weiter;
    #: ``"bewegung"`` = die Animation im Fokus (`core.bewegungsbild`), ``"symbol"`` = das
    #: Symbol der Übung (`ui/components/uebungsbild.py`) — beide nicht im Material (M1/M2,
    #: Ben 18.11.2026, `docs/plan_medienrollen.md`)
    rolle: str = ""
    #: Eine Erklärung beim ersten Mal von selbst zeigen — bis sie als gesehen abgehakt ist
    zeigen: bool = False
    #: Die Adresse (``uri``) eines Stücks der Übung, das dieses hier ersetzt — an einer
    #: Planübung oder in einer Ergänzung; das ersetzte wird nicht mehr angeboten
    ersetzt: str = ""
    #: **Wann** sich eine Erklärung zeigt (Ben, 18.11.2026, `docs/plan_medien_zeitpunkte.md`
    #: §2): leer = **vorher** (vor dem ▶ der Übung, vor dem Start des Plans), ``"nachher"`` =
    #: nach „Fertig“ der Übung bzw. am Ende des Plans, ``"bei"`` = zu einem Ereignis (`bei`).
    #: Eine Begleitung läuft „dabei“ — das sagt ihre Rolle
    wann: str = ""
    #: **Wie oft** es von selbst kommt: leer = nach `zeigen` (an: bis es abgehakt ist, aus: nur
    #: auf Tipp), ``"immer"`` = jedes Mal
    oft: str = ""
    #: Das Ereignis zu ``wann = "bei"``
    bei: Ereignis | None = None
    #: Die **Abschnitte** der Beschreibung (ihre Namen, ``## Name``), zu denen das Stück gehört —
    #: mehrere erlaubt; das Blatt beim Üben stellt es unter jeden davon (§3)
    abschnitte: tuple[str, ...] = ()
    #: Die **Beschriftung** (Ben, 19.11.2026, `docs/plan_medien_einheitlich.md` §2.1): ein Satz
    #: oder zwei unter dem Titel — was zu sehen ist, worauf man achten soll. Gezeigt unter dem
    #: Stück; ältere Apps übergehen das Feld
    text: str = ""

    @property
    def von_selbst(self) -> bool:
        """Kommt es von selbst — bis es abgehakt ist oder jedes Mal?"""
        return self.zeigen or self.oft == IMMER

    def zeit_zusatz(self) -> dict[str, Any]:
        """Wann, wie oft, Ereignis und Abschnitte — nur, was gesetzt ist (in der Datenbank der
        Übung die Spalte ``zusatz_json``, Migration 071).

        >>> Media(uri="https://x.org/v", wann="nachher", oft="immer").zeit_zusatz()
        {'wann': 'nachher', 'oft': 'immer'}
        >>> Media(uri="https://x.org/v", abschnitte=("Ausführung",)).zeit_zusatz()
        {'abschnitte': ['Ausführung']}
        >>> Media(uri="https://x.org/v", text=" Knie über dem Fuß ").zeit_zusatz()
        {'text': 'Knie über dem Fuß'}
        """
        d: dict[str, Any] = {}
        if self.wann:
            d["wann"] = self.wann
        if self.oft:
            d["oft"] = self.oft
        if self.bei is not None and self.wann == BEI:
            d["bei"] = self.bei.als_dict()
        if self.abschnitte:
            d["abschnitte"] = list(self.abschnitte)
        if self.text.strip():
            d["text"] = self.text.strip()
        return d

    def zusatz(self) -> dict[str, Any]:
        """Rolle, „von selbst zeigen“ und „ersetzt“ — nur, was gesetzt ist; dazu Wann, Wie oft,
        Ereignis und Abschnitte (`zeit_zusatz`).

        >>> Media(uri="https://x.org/v", rolle="begleitung").zusatz()
        {'rolle': 'begleitung'}
        >>> Media(uri="https://x.org/v", zeigen=True, ersetzt="https://x.org/alt").zusatz()
        {'zeigen': True, 'ersetzt': 'https://x.org/alt'}
        """
        d: dict[str, Any] = {}
        if self.rolle:
            d["rolle"] = self.rolle
        if self.zeigen:
            d["zeigen"] = True
        if self.ersetzt:
            d["ersetzt"] = self.ersetzt
        d.update(self.zeit_zusatz())
        return d

    def als_dict(self) -> dict[str, Any]:
        """Wie im Paket (`core.pakete.stand`): Art, Quelle, Adresse, Titel, Lizenz nur gesetzt.

        >>> Media(uri="https://x.org/v", title="Erklärung").als_dict()
        {'kind': 'video', 'source': 'url', 'uri': 'https://x.org/v', 'title': 'Erklärung'}
        """
        d: dict[str, Any] = {
            "kind": str(self.kind),
            "source": str(self.source),
            "uri": self.uri,
            "title": self.title,
        }
        if self.license:
            d["license"] = self.license
        d.update(self.zusatz())
        return d


#: Die Rolle „läuft beim Üben mit“ (`Media.rolle`); leer = Erklärung
BEGLEITUNG = "begleitung"
#: Die Animation der Übung im Fokus: eine Bildfolge (Streifen), ein GIF oder ein Bild aus dem
#: Paket (`core.bewegungsbild.bewegungen`)
BEWEGUNG = "bewegung"
#: Das Symbol der Übung als Datei aus dem Paket (SVG wird eingefärbt, PNG bleibt, wie es ist)
SYMBOL = "symbol"
#: Die Rollen, die ein Medium tragen kann — eine andere liest die App als Erklärung
ROLLEN = frozenset({BEGLEITUNG, BEWEGUNG, SYMBOL})
#: Stücke mit diesen Rollen zeigt die App an ihrem eigenen Platz, nicht unter „Material“
NICHT_MATERIAL = frozenset({BEWEGUNG, SYMBOL})
#: `Media.wann`: nach der Übung bzw. am Ende des Plans · zu einem Ereignis; leer = vorher
NACHHER = "nachher"
BEI = "bei"
ZEITPUNKTE = frozenset({NACHHER, BEI})
#: `Media.oft`: jedes Mal von selbst
IMMER = "immer"


def medien_zusatz(roh: Any) -> dict[str, Any]:
    """Was `Media.zusatz` schreibt, als Argumente für `Media` — Unbekanntes fällt weg.

    >>> z = medien_zusatz({"rolle": "begleitung", "zeigen": 1, "ersetzt": " https://x.org/alt "})
    >>> z["rolle"], z["zeigen"], z["ersetzt"]
    ('begleitung', True, 'https://x.org/alt')
    >>> medien_zusatz({"rolle": "tanz"})["rolle"], medien_zusatz({"wann": "nachher"})["wann"]
    ('', 'nachher')
    >>> medien_zusatz({"rolle": "bewegung"})["rolle"], medien_zusatz({"rolle": "symbol"})["rolle"]
    ('bewegung', 'symbol')
    """
    hat = getattr(roh, "get", None)
    if hat is None:
        return {}
    rolle = str(hat("rolle") or "")
    return {
        "rolle": rolle if rolle in ROLLEN else "",
        "zeigen": bool(hat("zeigen")),
        "ersetzt": str(hat("ersetzt") or "").strip(),
        **zeit_zusatz_lesen(roh),
    }


def zeit_zusatz_lesen(roh: Any) -> dict[str, Any]:
    """Was `Media.zeit_zusatz` schreibt, als Argumente für `Media` — Unbekanntes fällt weg; ein
    „bei“ ohne brauchbares Ereignis ist keins (das Stück liegt dann still hinter „Medien“).

    >>> z = zeit_zusatz_lesen({"wann": "bei", "bei": {"art": "satz", "n": 2}, "oft": "immer"})
    >>> z["wann"], z["oft"], z["bei"].text(), z["abschnitte"]
    ('bei', 'immer', 'wenn Satz 2 beginnt', ())
    >>> zeit_zusatz_lesen({"wann": "bei", "abschnitte": ["Ausführung", "", "Ausführung"]})
    {'wann': '', 'oft': '', 'bei': None, 'abschnitte': ('Ausführung',), 'text': ''}
    >>> zeit_zusatz_lesen({"wann": "morgen", "oft": "nie", "abschnitte": "Hinweise"})
    {'wann': '', 'oft': '', 'bei': None, 'abschnitte': ('Hinweise',), 'text': ''}
    """
    hat = getattr(roh, "get", None)
    if hat is None:
        return {}
    wann = str(hat("wann") or "")
    wann = wann if wann in ZEITPUNKTE else ""
    ereignis = Ereignis.aus(hat("bei")) if wann == BEI else None
    if wann == BEI and ereignis is None:
        wann = ""
    liste = hat("abschnitte") or ()
    if isinstance(liste, str):
        liste = [liste]
    namen: list[str] = []
    for x in liste:
        name = str(x).strip()
        if name and name not in namen:
            namen.append(name)
    return {
        "wann": wann,
        "oft": IMMER if str(hat("oft") or "") == IMMER else "",
        "bei": ereignis,
        "abschnitte": tuple(namen),
        "text": str(hat("text") or "").strip(),
    }


def medium_aus_dict(roh: Any) -> Media | None:
    """Ein Medium aus seiner Wörterbuch-Form (`Media.als_dict`) — ``None``, wenn es unbrauchbar
    ist (keine Adresse, unbekannte Art oder Quelle). Prüft keine Links: das tut, wer von außen
    liest (`core.pakete._medium`, `core.kurse`).

    >>> medium_aus_dict({"kind": "image", "uri": "https://x.org/b.jpg"}).kind
    <MediaKind.IMAGE: 'image'>
    >>> medium_aus_dict({"kind": "hologramm", "uri": "x"}) is None
    True
    """
    if not isinstance(roh, dict):
        return None
    uri = str(roh.get("uri") or "").strip()
    try:
        art = MediaKind(roh.get("kind", "video"))
        quelle = MediaSource(roh.get("source", "url"))
    except ValueError:
        return None
    if not uri:
        return None
    return Media(
        kind=art,
        source=quelle,
        uri=uri,
        title=str(roh.get("title") or ""),
        license=str(roh.get("license") or ""),
        **medien_zusatz(roh),
    )


@dataclass(slots=True)
class Exercise:
    """Eine Übung.

    ``result_spec`` bestimmt die Eingabemaske, ``limit_spec`` die
    Trainingssteuerung. Beides liegt in der Datenbank als JSON.
    """

    id: str = field(default_factory=new_id)
    name: str = ""
    #: Der erste Typ — beim Speichern aus `typen` abgeleitet. Wer nur ihn
    #: setzt (Altbestand, Tutorial), bekommt ihn als einzigen Typ.
    category: str = ""
    description: str = ""
    icon_key: str | None = None
    image_path: str | None = None
    is_builtin: bool = False
    result_spec: ResultSpec = field(default_factory=ResultSpec)
    limit_spec: dict[str, Any] = field(default_factory=dict)
    #: Vorgabe für Pläne: das Ziel jeder Planübung ohne eigenes (P79, `core.standards.ziel_von`).
    #: Parameter und Chips gelten ohnehin überall, wo der Plan nichts anderes festlegt.
    default_target: dict[str, Any] = field(default_factory=dict)
    #: Alte Eingabestufe (Migration 006) — bleibt für ältere Stände und die Synchronisation
    default_input_mode: str = "chips"
    media: list[Media] = field(default_factory=list)
    #: Typ-Tags: was für eine Übung das ist (Kräftigung, Dehnung, …) — optional
    typen: list[str] = field(default_factory=list)
    #: Region-Tags: welche Körperregion (Nacken, Bein, …) — optional
    regionen: list[str] = field(default_factory=list)
    archived: bool = False
    created_at: datetime = field(default_factory=jetzt)
    updated_at: datetime = field(default_factory=jetzt)
    #: Im Papierkorb seit (Migration 005) — ``None`` = nicht gelöscht
    deleted_at: datetime | None = None
    #: Aus welchem Paket die Übung kam (Migration 014, `core/pakete.py`);
    #: ``None`` = eigene Übung — hier angelegt oder kopiert.
    package_id: str | None = None
    #: Timer-Profile der Übung (Migration 020): `core.timer.TimerProfil.als_dict` je
    #: Profil — gelesen über `core.uebung_timer.profile_der_uebung`
    timer: list[dict[str, Any]] = field(default_factory=list)
    #: Stoppuhr und Timer stehen in der Übung bereit (Migration 022) — die Planübung kann
    #: abweichen (`core.uebung_timer.uhr_an`)
    uhr: bool = True
    #: „Zählt als“, wenn die Übung Haltezeit anbietet: ``hold`` oder ``duration``; leer =
    #: Haltezeit (`core.uebung_timer.zaehlt_als`)
    zaehlt_als: str = ""
    #: Timerzeit zählt (Migration 028, P79 D2): Läufe von Stoppuhr und Timer tragen Zeit ein —
    #: aus: nur „gemacht“. Beim Üben in der Leiste für jetzt umschaltbar.
    zeit_zaehlt: bool = True
    #: Die Karte „Beschleunigungssensor“ (Migration 037, ``acc_json``; Paketfeld
    #: ``beschleunigung``): Wiederholungen zählen, Atmung erfassen — leer = Vorgabe aus der
    #: Übung (`core.zaehlen.wiederholungen_an`, `atmung_an`)
    beschleunigung: SensorWahl = field(default_factory=SensorWahl)
    #: Der Takt der Übung (Migration 038, ``takt_json``; Paketfeld ``takt``;
    #: `docs/plan_taktgeber.md`): Phasen für Atmung oder Bewegung, die überall gelten, wo die
    #: Übung geübt wird — ein Timer-Abschnitt und die Uhr „für jetzt“ gehen vor
    takt: Takt | None = None
    #: Die Karte „GPS“ (Migration 062, ``gps_json``; Paketfeld ``gps``; `core.gps_wahl`): mit
    #: einer Rechenart steht die Übung im Reiter „Messung → GPS“ zur Wahl — leer = GPS aus
    gps: GpsWahl = field(default_factory=GpsWahl)

    def __post_init__(self) -> None:
        # Wer nur `category` angibt (Altbestand, Tutorial), bekommt sie als Typ.
        if self.category and not self.typen:
            self.typen = [self.category]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Subject:
    """Wessen Training dokumentiert wird.

    Auch Edition A braucht das — eine Familie teilt sich ein Gerät. Nachträglich
    einzuführen wäre eine Migration über alle Tabellen.
    """

    id: str = field(default_factory=new_id)
    name: str = ""
    birth_year: int | None = None
    note: str = ""
    #: 'w' | 'm' | 'd' | None — nur für HFmax-Formel (Gulati) und TRIMP-Gewichte
    #: (Migration 034, Ben 29.10.2026)
    geschlecht: str | None = None


@dataclass(slots=True)
class SessionEntry:
    """Eine ausgeführte Übung innerhalb einer Trainingseinheit.

    ``spec_snapshot`` ist die Kopie der `ResultSpec`, mit der erfasst wurde.
    Ohne sie wären alte Einträge nach einer Änderung der Übungsdefinition nicht
    mehr sauber darstellbar.

    Einträge sind **unveränderlich**. Korrekturen entstehen als neuer Eintrag,
    der den alten ersetzt. Das macht die Synchronisation in Edition B
    konfliktfrei.
    """

    id: str = field(default_factory=new_id)
    session_id: str = ""
    exercise_id: str = ""
    order: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    spec_snapshot: ResultSpec | None = None
    note: str = ""
    started_at: datetime | None = None
    #: Ende der Übung — leer heißt **offen**: Sätze hängen noch an (`core.eintraege`)
    ended_at: datetime | None = None
    media: list[Media] = field(default_factory=list)
    #: Wann diese Zeile entstand (jede Korrektur ist eine) — die letzte Änderung
    created_at: datetime | None = None

    def shorthand(self) -> str:
        """Kompakte Anzeige — immer mit der Spezifikation von damals."""
        if self.spec_snapshot is None:
            return ", ".join(f"{k} {v}" for k, v in self.result.items())
        return self.spec_snapshot.format_shorthand(self.result)


@dataclass(slots=True)
class Session:
    """Eine Trainingseinheit."""

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    started_at: datetime = field(default_factory=jetzt)
    ended_at: datetime | None = None
    plan_id: str | None = None
    note: str = ""
    mood: int | None = None
    entries: list[SessionEntry] = field(default_factory=list)


@dataclass(slots=True)
class Measurement:
    """Ein einzelner Messwert im Zeitverlauf.

    Speist alle Verlaufsdiagramme — sowohl Übungsergebnisse (über
    ``ResultSpec.chart_metrics``) als auch Benchmarks wie „wie lange kann ich
    die Luft anhalten" und HRV-Kennzahlen.

    Entspricht in praxis_gui `Dokumentation_Skalen_Werte`.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    metric_key: str = ""
    value: float = 0.0
    unit: str = ""
    recorded_at: datetime = field(default_factory=jetzt)
    session_id: str | None = None
    session_entry_id: str | None = None
    source: str = "manual"  # manual | exercise | hrv | import


@dataclass(slots=True)
class DayNote:
    """Eine Notiz zu einem Tag — die oberste Ebene des Tagebuchs. Je Tag beliebig viele
    (Ben, 2.11.2026, Migration 036), jede mit Uhrzeit (`created_at` — ihr Anker in der
    Zeitleiste) und Tags (`tag_ids` → `NoteTag`). Anhänge hängen an der Notiz
    (`entry_media.day_note_id`); eine Notiz ohne Text und ohne Anhänge gibt es nicht.

    Darunter liegen die Notizen je Training (`Session.note`) und je Übung
    (`SessionEntry.note`). Das Tagebuch ist keine eigene Tabelle, sondern
    eine Abfrage über diese Quellen.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    date: date = field(default_factory=lambda: lokaler_tag(jetzt()))
    text: str = ""
    created_at: datetime | None = None
    tag_ids: tuple[str, ...] = ()

    def leer(self) -> bool:
        return not self.text.strip()


#: Der feste Tag jedes Profils (Ben, 2.11.2026: „nicht löschen, aber deaktivieren“)
TAGEBUCH_TAG = "Tagebuch"


@dataclass(slots=True)
class NoteTag:
    """Ein Tag (Merkmal) an Notizen zum Tag, je Profil (Migration 036, Ben 2.11.2026):
    „Tagebuch“ ist fest (`fest`), die anderen legt man selbst an. `active` = 0 heißt
    ausgeschaltet: wird beim Schreiben nicht mehr angeboten, Notizen behalten ihn."""

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    name: str = ""
    sort: int = 0
    fest: bool = False
    active: bool = True
    deleted_at: datetime | None = None

    @property
    def aktiv(self) -> bool:
        return self.active and self.deleted_at is None


# ---------------------------------------------------------------------------
# Pläne — in beiden Editionen; in Edition B zusätzlich vom Therapeuten zugewiesen
# ---------------------------------------------------------------------------


#: Vorschläge für Typ-Tags (`Exercise.typen`). Migration 013 legt sie als Tags an;
#: danach verwaltet man sie unter Einstellungen → Typen und Regionen (`TagRepo`).
TYPEN = ["Dehnung", "Kräftigung", "Ausdauer", "Gleichgewicht", "Atmung", "Benchmark", "Messung"]
#: Vorschläge für Region-Tags (`Exercise.regionen`) — wie `TYPEN` ab Migration 013 Tags.
REGIONEN = ["Nacken", "Schulter", "Arm", "Hand", "Rumpf", "Rücken", "Hüfte", "Bein", "Fuß"]
#: Arten in der Tabelle `tag` (Spalte ``kind``, Migration 009)
TAG_TYP = "typ"
TAG_REGION = "region"


def tag_name_pruefen(
    text: str, gleiche: list[str], andere: list[str], andere_art: str = "eine Region"
) -> tuple[str | None, str | None]:
    """Prüft einen neuen Tag-Namen: (Name, None) oder (None, Fehlertext).

    Groß und klein trennen keine Tags — wer „dehnung“ tippt, bekommt „Dehnung“.
    Eine Stelle für Oberfläche (`ui/components/tagwahl.py`) und `TagRepo.anlegen`.

    >>> tag_name_pruefen(" Qigong ", ["Dehnung"], ["Bein"])
    ('Qigong', None)
    >>> tag_name_pruefen("dehnung", ["Dehnung"], [])
    ('Dehnung', None)
    >>> tag_name_pruefen("bein", [], ["Bein"])
    (None, '„Bein“ ist schon eine Region.')
    >>> tag_name_pruefen("  ", [], [])
    (None, 'Name?')
    """
    text = " ".join(text.split())
    if not text:
        return None, "Name?"
    if fremd := [n for n in andere if n.casefold() == text.casefold()]:
        return None, f"„{fremd[0]}“ ist schon {andere_art}."
    gleich = [n for n in gleiche if n.casefold() == text.casefold()]
    return (gleich[0] if gleich else text), None


def passt_zum_filter(uebung: Exercise, typen: set[str], regionen: set[str]) -> bool:
    """Katalogfilter: innerhalb einer Tag-Art genügt ein Treffer, beide Arten müssen passen.

    Ein leerer Filter lässt alles durch. Wer nach Region filtert, sieht keine
    Übungen ohne Region (HRV-Messung) — die haben ja keine.

    >>> u = Exercise(typen=["Kräftigung", "Isometrie"], regionen=["Bein"])
    >>> passt_zum_filter(u, set(), set())
    True
    >>> passt_zum_filter(u, {"Dehnung", "Isometrie"}, set())
    True
    >>> passt_zum_filter(u, {"Kräftigung"}, {"Nacken"})
    False
    >>> passt_zum_filter(Exercise(typen=["Messung"]), set(), {"Bein"})
    False
    """
    return (not typen or bool(typen & set(uebung.typen))) and (
        not regionen or bool(regionen & set(uebung.regionen))
    )


#: Eingabestufen einer Planübung (Migration 004)
EINGABE_HAKEN = "haken"
EINGABE_CHIPS = "chips"
EINGABE_FREI = "frei"


@dataclass(slots=True)
class PlanItem:
    """Eine Übung im Plan: mit Ziel, Parametern, Chips und Timer — eigenen oder der Übung.

    Hierarchie: Die Übung gibt alles vor; die Planübung folgt ihr, bis man im Plan etwas
    ändert (Ben, 22.10.2026, P79: „wie die Übung“ oder „nur hier“, `core/standards.py`); der
    Eintrag übernimmt den Plan und darf wiederum abweichen.
    """

    id: str = field(default_factory=new_id)
    plan_id: str = ""
    exercise_id: str = ""
    order: int = 0
    #: Ziel der Planübung — ``None`` = wie die Übung (`core.standards.ziel_von`), ``{}`` =
    #: ausdrücklich keins
    target: dict[str, Any] | None = None
    note: str = ""
    #: Abgeleitet aus `felder` (``haken`` bei keinem Parameter, sonst ``chips``) —
    #: bleibt für ältere Stände und die Synchronisation (Migration 010)
    input_mode: str = EINGABE_CHIPS
    #: Chips je Feld, die die der Übung ersetzen — fehlt ein Feld, gelten die
    #: der Übung; eine leere Liste heißt „keine Chips, nur das freie Feld"
    quick: dict[str, list[Any]] = field(default_factory=dict)
    #: Welche Parameter der Plan anbietet (Feldschlüssel) — ``None`` = wie die
    #: Übung, ``[]`` = keiner, nur abhaken (`core.parameter.aktive_felder`)
    felder: list[str] | None = None
    #: Timer der Planübung (Migration 020): `core.uebung_timer.TimerWahl.als_dict` —
    #: leer = wie der Plan, sonst wie die Übung
    timer: dict[str, Any] = field(default_factory=dict)
    #: Die Karte „Beschleunigungssensor“ nur hier (Migration 039, A6) — ``None`` = wie die
    #: Übung (`core.zaehlen.wirksame_wahl`)
    acc: SensorWahl | None = None
    #: Bedingung fürs Weiterkommen im Workout und Zweig (Migration 041, W2/W3,
    #: `core.bedingung`) — Vorgabe: nichts eingestellt
    bedingung: Bedingung = field(default_factory=Bedingung)
    #: Der Takt nur hier (Migration 039, A6) — ``None`` = wie die Übung, ein leerer Takt
    #: (`core.takt.AUS`) = ausdrücklich keiner (`core.uebung_timer.takt_der_uebung`)
    takt: Takt | None = None
    #: Beiname im Ablaufbild (Migration 044, `docs/plan_verzweigungen.md` §8.1): unterscheidet
    #: zwei gleiche Übungen („2. Durchgang“) — leer = keiner
    beiname: str = ""
    #: Eigene Inhalte der Planübung (Migration 046, U2, `docs/plan_paketinhalte.md` §9):
    #: Abschnitte wie die Beschreibung der Übung (`## Name`) — Anweisungen für diesen Plan —
    #: und Medien (Videos, Bilder, Links); aus dem Paketplan oder selbst geschrieben
    description: str = ""
    media: list[Media] = field(default_factory=list)
    #: Die Marke, an der ein Kurs seine Planübung im Kursplan wiederfindet (Migration 064,
    #: `core/kursplan.py`): die Block-ID des Bausteins, bei einer Auswahl ``<block>:<übung>``,
    #: in der Grundlage ``g:<n>`` — leer = keine (selbst hinzugefügt, jeder andere Plan)
    kurs_marke: str = ""


@dataclass(slots=True)
class Plan:
    id: str = field(default_factory=new_id)
    name: str = ""
    #: Beschreibung in Abschnitten (`core/beschreibung.py`) — gezeigt mit den Medien des Plans
    description: str = ""
    #: Medien des Plans selbst (Migration 069, Ben 17.11.2026, `docs/plan_medien_reiter.md` §4):
    #: Links und Paketdateien, gezeigt am Kopf des Plans und im Start-Bild des Workouts — „von
    #: selbst“ nur vor dem ersten Start. Keine Begleitung (es läuft keine Übung daneben)
    media: list[Media] = field(default_factory=list)
    subject_id: str | None = None
    created_at: datetime = field(default_factory=jetzt)
    items: list[PlanItem] = field(default_factory=list)
    #: Im Papierkorb seit — ``None`` = nicht gelöscht
    deleted_at: datetime | None = None
    #: Deaktiviert: erscheint nicht auf „Heute", bleibt aber in der Planverwaltung
    aktiv: bool = True
    #: Wochentage, an denen der Plan ansteht — 0 = Montag … 6 = Sonntag
    wochentage: list[int] = field(default_factory=lambda: list(range(7)))
    #: Von welchem Kurskapitel der Plan angelegt wurde (Migration 016, `core/kurse.py`);
    #: beim Abschluss des Kapitels wird er deaktiviert, nicht gelöscht. ``None`` = eigener Plan
    kurs_kapitel_id: str | None = None
    #: Der Plan gehört zu einem **früheren Durchlauf** des Kurses (Migration 063, Ben
    #: 16.11.2026): „Von vorn beginnen“ ließ ihn stehen, das Kapitel legt einen neuen an.
    #: ``None`` = der laufende Plan. Nur gelesen — gesetzt von `KursRepo.zuruecksetzen`,
    #: `PlanRepo.speichern` fasst die Spalte nicht an
    kurs_durchlauf_beendet: datetime | None = None
    #: Der Kurs, dessen **Kursplan** dieser Plan ist (Migration 064, Ben 16.11.2026,
    #: `core/kursplan.py`): ein Plan, der über die Kapitel wächst — seine Herkunft ist der Kurs,
    #: nicht ein Kapitel. ``None`` = kein Kursplan. Nur gelesen wie `kurs_durchlauf_beendet` —
    #: gesetzt von `PlanRepo.kurs_setzen`, `PlanRepo.speichern` fasst die Spalte nicht an
    kurs_id: str | None = None
    #: Regel für den Vorschlag nach der Belastung (Ben, 12.11.2026, `core.anpassung.Regel.
    #: als_dict`) — ``None`` = keine. Kommt aus dem Kurs oder Paket
    anpassung: dict[str, Any] | None = None
    #: „Timer für alle Übungen“ (Migration 020): ein `core.timer.TimerProfil.als_dict`
    timer: dict[str, Any] | None = None
    #: Nach dem Timer einer Übung automatisch weiter — sonst auf einen Tipp warten
    weiter_automatisch: bool = False
    #: Wartet der Ablauf auf einen Tipp: auch nach einer Übung ohne Timer (Migration 021,
    #: Vorgabe) — sonst beginnt nach „Gemacht“ gleich die nächste
    pause_ohne_timer: bool = True
    #: Workout (Migration 040, `docs/plan_workout.md`): der Plan öffnet mit dem Start-Bild
    #: des Workouts — jeder Plan geht trotzdem für heute „Als Workout“
    workout: bool = False
    #: Vorgabe des Übergangs im Workout: hart (nach dem Timer sofort weiter) oder weich (der
    #: Timer zählt ins Minus, „Weiter“ von Hand); vor dem Start umstellbar
    uebergang_hart: bool = False
    #: „Takt für alle Übungen“ (Migration 042, P105): gilt für Planübungen ohne eigenen Takt,
    #: eine Stufe über der Übung — wie der Plan-Timer; ``None`` = keiner
    takt: Takt | None = None
    #: Der gezeichnete Ablauf (Migration 044, `core.ablauf`): Start, Kanten, Fragen; ``an`` =
    #: der Reiter „Ablauf“ ist eingeschaltet, sonst läuft der Plan als Kette
    ablauf: Ablauf = field(default_factory=Ablauf)
    #: Aus einem Paket (Migration 033, `docs/plan_import_links_plaene.md` §3): das Paket, der
    #: Schlüssel des Plans darin und der Paketstand, mit dem ein Update Geändertes erkennt
    package_id: str | None = None
    package_key: str | None = None
    package_standard: dict[str, Any] | None = None

    def steht_an(self, tag: date) -> bool:
        """Ob der Plan an diesem Tag von sich aus auf „Heute" erscheint.

        >>> Plan(wochentage=[0, 2, 4]).steht_an(date(2026, 10, 12))  # ein Montag
        True
        >>> Plan(wochentage=[0, 2, 4]).steht_an(date(2026, 10, 13))
        False
        >>> Plan(aktiv=False).steht_an(date(2026, 10, 12))
        False
        """
        return self.aktiv and tag.weekday() in self.wochentage


# ---------------------------------------------------------------------------
# HRV
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HrvRecording:
    """Verweis auf eine HRV-Messdatei.

    **Die Datei ist die Wahrheit**, nicht diese Zeile. Sie liegt im
    `raw-v1`-Format und ist damit ohne Umweg in praxis_gui lesbar. ``sha1``
    erkennt nachträgliche Änderungen an der Datei.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    file_path: str = ""
    sha1: str = ""
    device_id: str | None = None
    geraet: str = ""
    geraet_profil: str = "ble_generic"
    intervall_quelle: str = "ekg_rr"
    datenqualitaet: str = "rr_ekg"
    started_at: datetime = field(default_factory=jetzt)
    duration_s: float = 0.0
    coverage_pct: float = 100.0
    n_gaps: int = 0
    session_id: str | None = None
    session_entry_id: str | None = None
    #: Beschreibung — Kopie von ``notiz`` der Messdatei
    note: str = ""
    #: Überschrift — Kopie von ``titel`` der Messdatei (Migration 011)
    title: str = ""


@dataclass(slots=True)
class HrvTitel:
    """Eine gespeicherte Überschrift für HRV-Messungen (Migration 030).

    Je Profil eine Liste zum Antippen im Titel-Blatt (Ben, 26.10.2026: vordefinieren,
    auffindbar abrufen, löschen). Jede vergebene Überschrift kommt von selbst hinein;
    ``angeheftet`` hält sie oben, sonst zählt ``zuletzt`` — ``None``: noch nie vergeben.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    name: str = ""
    angeheftet: bool = False
    zuletzt: datetime | None = None
    created_at: datetime = field(default_factory=jetzt)


@dataclass(slots=True)
class AbschnittName:
    """Ein gemerkter Name für Abschnitte (Migration 072, Ben 19.11.2026) — eine eigene Liste
    neben den Überschriften (`HrvTitel`), mit demselben Verhalten: Jeder vergebene Name kommt
    von selbst hinein; ``angeheftet`` hält ihn oben, sonst zählt ``zuletzt`` — ``None``: noch
    nie als Abschnitt vergeben.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    name: str = ""
    angeheftet: bool = False
    zuletzt: datetime | None = None
    created_at: datetime = field(default_factory=jetzt)


@dataclass(slots=True)
class Strecke:
    """Ein Training mit Strecke — nur Ortsfreies (Migration 012).

    ``sportart`` ist die **Rechenart** (gehen, laufen, rad: Splitlänge, km/h oder min/km),
    ``exercise_id`` die Übung, bei der es eingetragen wurde (Migration 062, „GPS je Übung“ —
    ``None``: Übung unbekannt, dann heißt das Training nach der Rechenart).

    Die Ortungen liegen als Datei unter ``Strecken/`` (``file_path`` relativ
    dazu; leer = ohne GPS). **GPS-Daten werden nie geteilt** (`docs/plan_gps.md`,
    Abschnitt 0): Diese Zeile kennt keine Koordinate und wird nie synchronisiert.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    sportart: str = "laufen"
    started_at: datetime = field(default_factory=jetzt)
    ended_at: datetime | None = None
    file_path: str = ""
    distanz_m: float = 0.0
    dauer_s: float = 0.0
    bewegt_s: float = 0.0
    hoehe_auf_m: float = 0.0
    hoehe_ab_m: float = 0.0
    hrv_recording_id: str | None = None
    session_entry_id: str | None = None
    title: str = ""
    #: Die Einheit, als die das Training lief (Migration 019) — über sie findet die
    #: Auswertung auch eine HRV-Aufnahme, die schon vorher lief und weiterlief
    einheit_id: str | None = None
    exercise_id: str | None = None


__all__ = [
    "BEGLEITUNG",
    "BEI",
    "BEWEGUNG",
    "EREIGNIS_ARTEN",
    "E_ABSCHNITT",
    "E_ANTWORT",
    "E_SATZ",
    "E_WDH",
    "E_ZEIT",
    "IMMER",
    "NACHHER",
    "NICHT_MATERIAL",
    "ROLLEN",
    "SYMBOL",
    "ZEITPUNKTE",
    "AbschnittName",
    "Ereignis",
    "Exercise",
    "HrvRecording",
    "HrvTitel",
    "Measurement",
    "Media",
    "MediaKind",
    "MediaSource",
    "Plan",
    "PlanItem",
    "Session",
    "SessionEntry",
    "Subject",
    "jetzt",
    "new_id",
    "zeit_zusatz_lesen",
]
