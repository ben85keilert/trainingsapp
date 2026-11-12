"""Taktgeber: Phasen für Atmung und Bewegung in Uhr, Timer und Übung (`docs/plan_taktgeber.md`).

Ein **Takt** ist eine Folge von **Phasen** mit Namen, Dauer, Art und Klang — ein bis beliebig
viele („ein · halten · aus · halten“, „ab · halten · auf“, ein Metronomschlag). Er hat ein
**Tempo** (Faktor, mit dem alle Dauern skalieren — der Geschwindigkeitsregler) und läuft als
Schleife, solange die Uhr läuft; ``runden`` begrenzt ihn, sonst ist er endlos.

Die **Lage** im Takt (Phase, Anteil in der Phase, Runde) wird **aus der Uhr gerechnet**, nie
mitgezählt: Zeit seit Beginn des Abschnitts modulo Rundendauer (`lage`). Darum driftet nichts,
und „Anhalten“ hält den Takt mit an. Ändert sich das Tempo während des Laufs, hält `TaktLauf`
die Lage fest: die gelaufene Rundenzeit bleibt, die Phase wird neu skaliert (P139).

Die **Art** einer Phase sagt der Auswertung, was sie bedeutet (`ein`/`aus`/`halten`: Atmung;
`ab`/`auf`: Bewegung; `frei`: nichts davon), der Name, was angezeigt wird. `soll_phasen` legt
daraus die Soll-Phasen für das Beiwerk ``atem-v1`` (Teil 2 des Taktgebers).

Keine Bewertung, keine Empfehlung: Ein Takt ist eine Vorgabe der Person, keine aus Messwerten
(`docs/recht/00_zweckbestimmung.md`; das Resonanzprotokoll, das eine Rate *wählt*, bleibt
gesperrt wie in `docs/plan_beschleunigung.md` §10). Nur Standardbibliothek, kein flet.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from .klang import KLAENGE

#: Arten einer Phase
ART_EIN: Final[str] = "ein"
ART_AUS: Final[str] = "aus"
ART_HALTEN: Final[str] = "halten"
ART_AB: Final[str] = "ab"
ART_AUF: Final[str] = "auf"
ART_FREI: Final[str] = "frei"
#: Alle Arten in der Reihenfolge der Auswahl → Anzeigename
ARTEN: Final[dict[str, str]] = {
    ART_EIN: "Einatmen",
    ART_AUS: "Ausatmen",
    ART_HALTEN: "Halten",
    ART_AB: "Ab",
    ART_AUF: "Auf",
    ART_FREI: "Frei",
}
#: Arten der Atmung bzw. der Bewegung
ARTEN_ATMUNG: Final[frozenset[str]] = frozenset({ART_EIN, ART_AUS, ART_HALTEN})
ARTEN_BEWEGUNG: Final[frozenset[str]] = frozenset({ART_AB, ART_AUF})

#: Klang zu Beginn einer Phase, wenn die Phase keinen eigenen hat (`docs/plan_taktgeber.md` §3)
KLANG_VORGABE: Final[dict[str, str]] = {
    ART_EIN: "glocke1",
    ART_AUS: "glocke3",
    ART_HALTEN: "holz",
    ART_AB: "wechsel",
    ART_AUF: "wechsel",
    ART_FREI: "schale",
}

#: Grenzen einer Phase (s) — Zehntel erlaubt, ein Metronom braucht 1 s und weniger
MIN_DAUER_S: Final[float] = 0.1
MAX_DAUER_S: Final[float] = 600.0
#: Höchstens so viele Phasen je Takt
MAX_PHASEN: Final[int] = 12
#: Tempo-Regler: Faktor auf alle Dauern
TEMPO_MIN: Final[float] = 0.5
TEMPO_MAX: Final[float] = 2.0
#: Höchstens so viele Runden, wenn ein Takt begrenzt ist
MAX_RUNDEN: Final[int] = 999

#: Animationen (`components/takt_anzeige.py`) — Schlüssel → Anzeigename
ANIMATION_PULS: Final[str] = "puls"
ANIMATION_KREIS: Final[str] = "kreis"
ANIMATION_KREIS_HALTEN: Final[str] = "kreis_halten"
ANIMATION_BOX: Final[str] = "box"
ANIMATION_BALKEN: Final[str] = "balken"
ANIMATION_WELLE: Final[str] = "welle"
ANIMATIONEN: Final[dict[str, str]] = {
    ANIMATION_PULS: "Puls",
    ANIMATION_KREIS: "Kreis",
    ANIMATION_KREIS_HALTEN: "Kreis mit Halten",
    ANIMATION_BOX: "Box",
    ANIMATION_BALKEN: "Balken",
    ANIMATION_WELLE: "Welle",
}

#: Ereignisse zwischen zwei Lagen (`wechsel`)
PHASE: Final[str] = "phase"
RUNDE: Final[str] = "runde"
ENDE: Final[str] = "ende"


def dauer_lesen(roh: Any) -> float | None:
    """Eine Phasendauer aus Zahl oder Text („4“, „2,5“, „0.5“) — ``None`` außerhalb der Grenzen.

    >>> dauer_lesen(4), dauer_lesen("2,5"), dauer_lesen("0.5"), dauer_lesen(" 7 ")
    (4.0, 2.5, 0.5, 7.0)
    >>> dauer_lesen(0), dauer_lesen("x"), dauer_lesen(None), dauer_lesen(601), dauer_lesen(True)
    (None, None, None, None, None)
    >>> dauer_lesen(1.26)  # auf Zehntel
    1.3
    """
    if isinstance(roh, bool) or roh is None:
        return None
    try:
        wert = float(str(roh).strip().replace(",", ".")) if isinstance(roh, str) else float(roh)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(wert):
        return None
    wert = round(wert, 1)
    if not MIN_DAUER_S <= wert <= MAX_DAUER_S:
        return None
    return wert


def dauer_text(sekunden: float) -> str:
    """Sekunden kurz: ganze ohne Komma, sonst ein Zehntel.

    >>> dauer_text(4), dauer_text(2.5), dauer_text(0.1), dauer_text(7.0)
    ('4', '2,5', '0,1', '7')
    """
    if abs(sekunden - round(sekunden)) < 0.05:
        return str(round(sekunden))
    return f"{sekunden:.1f}".replace(".", ",")


def tempo_lesen(roh: Any) -> float:
    """Ein Tempo-Faktor zwischen `TEMPO_MIN` und `TEMPO_MAX` — Unbrauchbares ist 1.

    >>> tempo_lesen(1.5), tempo_lesen("0.5"), tempo_lesen(9), tempo_lesen(0.1), tempo_lesen("x")
    (1.5, 0.5, 2.0, 0.5, 1.0)
    """
    if isinstance(roh, bool) or roh is None:
        return 1.0
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(wert):
        return 1.0
    return round(min(max(wert, TEMPO_MIN), TEMPO_MAX), 2)


def geschwindigkeit(faktor: Any) -> float:
    """Was die Person als Tempo sieht: die Geschwindigkeit ``1 / Faktor`` (Ben, 7.11.2026:
    „kleineres Tempo verlangsamt den Takt … eine kleinere Geschwindigkeit ist auch ein
    langsamerer Ablauf“). Gespeichert bleibt der Faktor auf die Dauern (`Takt.tempo`).

    >>> geschwindigkeit(2.0), geschwindigkeit(0.5), geschwindigkeit(1.5), geschwindigkeit("x")
    (0.5, 2.0, 0.67, 1.0)
    """
    faktor = tempo_lesen(faktor)
    return round(1.0 / faktor, 2)


def faktor_von(geschwindigkeit: Any) -> float:
    """Der Faktor auf die Dauern zu einer Geschwindigkeit (Regler) — begrenzt wie `tempo_lesen`.

    >>> faktor_von(2.0), faktor_von(0.5), faktor_von(0.75), faktor_von("x")
    (0.5, 2.0, 1.33, 1.0)
    """
    g = tempo_lesen(geschwindigkeit)
    return tempo_lesen(1.0 / g)


def tempo_text(faktor: float) -> str:
    """„1,0×“, „1,33×“, „0,5×“ — die **Geschwindigkeit** zum Faktor (`geschwindigkeit`):
    2× heißt doppelt so schnell, also halbe Dauern.

    >>> tempo_text(1.0), tempo_text(0.75), tempo_text(2)
    ('1,0×', '1,33×', '0,5×')
    """
    text = f"{geschwindigkeit(faktor):.2f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text.replace(".", ",") + "×"


def rate_text(rate: float) -> str:
    """„6,0/min“, „3,2/min“ — die Rate je Minute mit einer Stelle.

    >>> rate_text(6), rate_text(60 / 19)
    ('6,0/min', '3,2/min')
    """
    return f"{rate:.1f}".replace(".", ",") + "/min"


@dataclass(frozen=True)
class Phase:
    """Eine Phase: Name (angezeigt), Dauer in s, Art (Bedeutung), Klang zu Beginn (leer =
    Vorgabe je Art, `KLANG_VORGABE`).

    >>> p = Phase("ein", 4, ART_EIN)
    >>> p.als_dict(), p.klang_fuer
    ({'name': 'ein', 'dauer_s': 4.0, 'art': 'ein'}, 'glocke1')
    >>> Phase.aus_dict(p.als_dict()) == p, Phase.aus_dict({"dauer_s": 0}), Phase.aus_dict("x")
    (True, None, None)
    >>> Phase.aus_dict({"name": "x", "dauer_s": "2,5", "art": "tanz", "klang": "trompete"})
    Phase(name='x', dauer_s=2.5, art='frei', klang='', bild='')
    """

    name: str
    dauer_s: float
    art: str = ART_FREI
    klang: str = ""
    #: Ein Bild je Phase (Teil 2 T6, nur vorbereitet: Dict-Rundreise, keine Oberfläche) — der
    #: relative Pfad in der Ablage ``Medien/Bewegung/``; leer = keins. Später schaltet der Takt
    #: die Bildfolge je Phase (`docs/plan_taktgeber.md` §5); das Bild der Bewegung an der
    #: Übung läuft davon unabhängig als Schleife.
    bild: str = ""

    @property
    def klang_fuer(self) -> str:
        """Der Klang, der zu Beginn spielt — der eigene, sonst die Vorgabe der Art."""
        return self.klang or KLANG_VORGABE.get(self.art, KLANG_VORGABE[ART_FREI])

    @property
    def anzeigename(self) -> str:
        """Der Name — leer: der Name der Art."""
        return self.name or ARTEN.get(self.art, "")

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "dauer_s": float(self.dauer_s)}
        if self.art != ART_FREI:
            d["art"] = self.art
        if self.klang:
            d["klang"] = self.klang
        if self.bild:
            d["bild"] = self.bild
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> Phase | None:
        """Defensiv: ohne brauchbare Dauer keine Phase; unbekannte Art = frei, unbekannter
        Klang = Vorgabe; ``bild`` nur als Text (Pfad in der Ablage), sonst leer.

        >>> Phase.aus_dict({"dauer_s": 2, "bild": "Bewegung/b.gif"}).als_dict()["bild"]
        'Bewegung/b.gif'
        >>> Phase.aus_dict({"dauer_s": 2, "bild": 3}).bild
        ''
        """
        if not isinstance(d, Mapping):
            return None
        dauer = dauer_lesen(d.get("dauer_s"))
        if dauer is None:
            return None
        art = d.get("art")
        klang = d.get("klang")
        bild = d.get("bild")
        return cls(
            name=" ".join(str(d.get("name") or "").split()),
            dauer_s=dauer,
            art=art if isinstance(art, str) and art in ARTEN else ART_FREI,
            klang=klang if isinstance(klang, str) and klang in KLAENGE else "",
            bild=bild.strip() if isinstance(bild, str) else "",
        )


@dataclass(frozen=True)
class Takt:
    """Phasen in Folge, als Schleife — mit Name, Tempo und wahlweise Rundenzahl.

    Unveränderlich wie `SensorWahl`: `dataclasses.replace` einer Übung kopiert flach.
    ``Takt(())`` ist der leere Takt (`AUS`) — „für jetzt keiner“; er kommt nie aus einem Dict.

    >>> t = Takt((Phase("ein", 4, ART_EIN), Phase("halten", 7, ART_HALTEN),
    ...           Phase("aus", 8, ART_AUS)), name="4-7-8")
    >>> t.rundendauer_s, round(t.rate_pro_min, 2), t.ist_atmung(), t.ist_bewegung()
    (19.0, 3.16, True, False)
    >>> Takt.aus_dict(t.als_dict()) == t, t.als_dict()["phasen"][1]
    (True, {'name': 'halten', 'dauer_s': 7.0, 'art': 'halten'})
    >>> t.mit_tempo(2.0).rundendauer_s, t.mit_tempo(2.0).dauer_s(0)
    (38.0, 8.0)
    >>> t.kurztext(), t.phasen_text()
    ('4-7-8 · 3,2/min', '4-7-8')
    >>> Takt.aus_dict({"phasen": []}) is None, Takt.aus_dict("kaputt") is None, AUS.leer
    (True, True, True)
    """

    phasen: tuple[Phase, ...]
    name: str = ""
    #: Faktor auf alle Dauern, 1,0 = wie eingestellt — gezeigt und geregelt wird die
    #: Geschwindigkeit 1/Faktor (`geschwindigkeit`, `tempo_text`; Ben, 7.11.2026)
    tempo: float = 1.0
    #: Rundenzahl — ``None``: endlos bis zum Ende des Abschnitts bzw. der Uhr
    runden: int | None = None
    #: Animation (`ANIMATIONEN`) — leer: nach der Phasenzahl (`animation_fuer`)
    animation: str = ""
    #: „Takt zählt“ (P138, Teil 2 T5): jede volle Runde eine Wiederholung — der Zähl-Teil mit
    #: Quelle ``takt`` (`devices.zaehlen`); Vorgabe an bei den Bewegungs-Vorlagen, bei Atemtakten
    #: aus (wer Atemzüge in ein Wiederholungsfeld zählen will, schaltet es ein)
    zaehlt: bool = False

    @property
    def leer(self) -> bool:
        return not self.phasen

    @property
    def rundendauer_s(self) -> float:
        """Summe der Dauern mal Tempo (s)."""
        return round(sum(p.dauer_s for p in self.phasen) * self.tempo, 3)

    @property
    def rate_pro_min(self) -> float:
        """Runden je Minute — für die Atmung die Atemfrequenz; 0 beim leeren Takt."""
        dauer = self.rundendauer_s
        return 60.0 / dauer if dauer > 0 else 0.0

    @property
    def anzeigename(self) -> str:
        return self.name or self.phasen_text() or "Takt"

    def dauer_s(self, index: int) -> float:
        """Die Dauer der Phase ``index`` mit Tempo (s)."""
        return round(self.phasen[index].dauer_s * self.tempo, 3)

    def mit_tempo(self, faktor: float) -> Takt:
        """Derselbe Takt mit anderem Tempo (begrenzt auf `TEMPO_MIN`–`TEMPO_MAX`)."""
        return replace(self, tempo=tempo_lesen(faktor))

    def ist_atmung(self) -> bool:
        """Nur Arten ein/aus/halten, mindestens ein/aus — ein Atemtakt."""
        arten = {p.art for p in self.phasen}
        return bool(arten) and arten <= ARTEN_ATMUNG and bool(arten & {ART_EIN, ART_AUS})

    def ist_bewegung(self) -> bool:
        """Mindestens eine Phase ab/auf — ein Bewegungstakt (Kniebeuge 2-1-2)."""
        return any(p.art in ARTEN_BEWEGUNG for p in self.phasen)

    def phasen_text(self) -> str:
        """„4-7-8“, „2-1-2“, „1“ — die Dauern ohne Tempo."""
        return "-".join(dauer_text(p.dauer_s) for p in self.phasen)

    def kurztext(self) -> str:
        """„4-7-8 · 3,2/min“, mit Tempo „4-7-8 · 1,5× · 4,7/min“ — für Zeilen."""
        if self.leer:
            return "kein Takt"
        teile = [self.phasen_text()]
        if self.tempo != 1.0:
            teile.append(tempo_text(self.tempo))
        teile.append(rate_text(self.rate_pro_min))
        return " · ".join(teile)

    def als_dict(self) -> dict[str, Any]:
        """Tempo, Runden, Animation und „zählt“ nur, wenn gesetzt — ältere Leser übergehen
        das Feld, neuere lesen Fehlendes als Vorgabe."""
        d: dict[str, Any] = {"name": self.name, "phasen": [p.als_dict() for p in self.phasen]}
        if self.tempo != 1.0:
            d["tempo"] = self.tempo
        if self.runden is not None:
            d["runden"] = self.runden
        if self.animation:
            d["animation"] = self.animation
        if self.zaehlt:
            d["zaehlt"] = True
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> Takt | None:
        """Defensiv: ohne brauchbare Phase kein Takt, nie eine Ausnahme."""
        if not isinstance(d, Mapping):
            return None
        roh = d.get("phasen")
        gelesen = (Phase.aus_dict(x) for x in (roh if isinstance(roh, list) else []))
        phasen = [p for p in gelesen if p is not None][:MAX_PHASEN]
        if not phasen:
            return None
        animation = d.get("animation")
        return cls(
            phasen=tuple(phasen),
            name=" ".join(str(d.get("name") or "").split()),
            tempo=tempo_lesen(d.get("tempo")),
            runden=_runden_lesen(d.get("runden")),
            animation=animation if isinstance(animation, str) and animation in ANIMATIONEN else "",
            zaehlt=d.get("zaehlt") is True,
        )


#: Der leere Takt: „für jetzt kein Takt“ (schaltet Abschnitt und Übung ab)
AUS: Final[Takt] = Takt(())


def _runden_lesen(roh: Any) -> int | None:
    if isinstance(roh, bool) or roh is None:
        return None
    try:
        runden = int(roh)
    except (TypeError, ValueError, OverflowError):
        return None
    return runden if 1 <= runden <= MAX_RUNDEN else None


def takt_pruefen(
    roh: Any, *, ohne: str = "die Übung bekommt keinen Takt"
) -> tuple[list[str], list[str]]:
    """Was `Takt.aus_dict` still verwirft oder als Vorgabe liest, in Worten — ``(Fehler,
    Hinweise)`` für ``trainingsapp-paket pruefen``, wie `core.zaehlen.wahl_pruefen`: ein
    falscher Typ ist ein Fehler (die Angabe ginge verloren), eine unbekannte Art, ein
    unbekannter Klang oder Schlüssel ein Hinweis. ``ohne``: was gilt, wenn kein Takt
    lesbar ist — an der Übung „bekommt keinen Takt“, an einer Planübung „folgt der Übung“.

    >>> takt_pruefen({"name": "4-6", "phasen": [{"name": "ein", "dauer_s": 4, "art": "ein"},
    ...                                         {"name": "aus", "dauer_s": 6, "art": "aus"}]})
    ([], [])
    >>> fehler, hinweise = takt_pruefen({"phasen": [{"dauer_s": "x", "art": "tanz"},
    ...     {"dauer_s": 2, "klang": "trompete", "x": 1}], "tempo": "schnell", "runden": 0})
    >>> for f in fehler: print(f)
    Phase 1: „dauer_s“ muss eine Zahl zwischen 0.1 und 600 sein, nicht "x" — die Phase fällt weg
    „tempo“ muss eine Zahl zwischen 0.5 und 2 sein, nicht "schnell" — gilt als 1
    „runden“ muss eine ganze Zahl ab 1 sein, nicht 0 — gilt als endlos
    >>> for h in hinweise: print(h)
    Phase 1: unbekannte Art „tanz“ — gilt als „frei“ (bekannt: ein, aus, halten, ab, auf, frei)
    Phase 2: unbekannter Klang „trompete“ — gilt als Vorgabe der Art
    Phase 2: unbekannter Schlüssel „x“ — wird überlesen (bekannt: name, dauer_s, art, klang, bild)
    >>> takt_pruefen(True)[0]
    ['keine Tabelle (etwa { phasen = [ … ] }), sondern true — die Übung bekommt keinen Takt']
    >>> takt_pruefen({"phasen": "x"})[0]
    ['„phasen“ muss eine Liste von Tabellen sein, nicht "x" — die Übung bekommt keinen Takt']
    >>> takt_pruefen({"phasen": "x"}, ohne="die Planübung folgt der Übung")[0]
    ['„phasen“ muss eine Liste von Tabellen sein, nicht "x" — die Planübung folgt der Übung']
    """
    if not isinstance(roh, Mapping):
        return [
            f"keine Tabelle (etwa {{ phasen = [ … ] }}), sondern {_wert_text(roh)} — {ohne}"
        ], []
    fehler: list[str] = []
    hinweise: list[str] = []
    phasen = roh.get("phasen")
    if not isinstance(phasen, list):
        fehler.append(
            f"„phasen“ muss eine Liste von Tabellen sein, nicht {_wert_text(phasen)} — {ohne}"
        )
        phasen = []
    for k, p in enumerate(phasen, start=1):
        if not isinstance(p, Mapping):
            fehler.append(
                f"Phase {k}: keine Tabelle, sondern {_wert_text(p)} — die Phase fällt weg"
            )
            continue
        if dauer_lesen(p.get("dauer_s")) is None:
            fehler.append(
                f"Phase {k}: „dauer_s“ muss eine Zahl zwischen {MIN_DAUER_S:g} und "
                f"{MAX_DAUER_S:g} sein, nicht {_wert_text(p.get('dauer_s'))} — die Phase fällt weg"
            )
        art = p.get("art")
        if art is not None and art not in ARTEN:
            hinweise.append(
                f"Phase {k}: unbekannte Art {_anf(art)} — gilt als „frei“ (bekannt: "
                + ", ".join(ARTEN)
                + ")"
            )
        klang = p.get("klang")
        if klang is not None and klang not in KLAENGE:
            hinweise.append(
                f"Phase {k}: unbekannter Klang {_anf(klang)} — gilt als Vorgabe der Art"
            )
        for schluessel in p:
            if schluessel not in ("name", "dauer_s", "art", "klang", "bild"):
                hinweise.append(
                    f"Phase {k}: unbekannter Schlüssel „{schluessel}“ — wird überlesen "
                    "(bekannt: name, dauer_s, art, klang, bild)"
                )
    tempo = roh.get("tempo")
    if tempo is not None and (
        isinstance(tempo, bool)
        or not isinstance(tempo, int | float)
        or not TEMPO_MIN <= tempo <= TEMPO_MAX
    ):
        fehler.append(
            f"„tempo“ muss eine Zahl zwischen {TEMPO_MIN:g} und {TEMPO_MAX:g} sein, nicht "
            f"{_wert_text(tempo)} — gilt als 1"
        )
    runden = roh.get("runden")
    if runden is not None and _runden_lesen(runden) is None:
        fehler.append(
            f"„runden“ muss eine ganze Zahl ab 1 sein, nicht {_wert_text(runden)} — gilt als endlos"
        )
    animation = roh.get("animation")
    if animation is not None and animation not in ANIMATIONEN:
        hinweise.append(
            f"unbekannte Animation {_anf(animation)} — gilt als Vorgabe nach Phasenzahl "
            "(bekannt: " + ", ".join(ANIMATIONEN) + ")"
        )
    if "zaehlt" in roh and not isinstance(roh["zaehlt"], bool):
        fehler.append(f"„zaehlt“ muss true oder false sein, nicht {_wert_text(roh['zaehlt'])}")
    for schluessel in roh:
        if schluessel not in ("name", "phasen", "tempo", "runden", "animation", "zaehlt"):
            hinweise.append(
                f"unbekannter Schlüssel „{schluessel}“ — wird überlesen (bekannt: name, phasen, "
                "tempo, runden, animation, zaehlt)"
            )
    return fehler, hinweise


def _wert_text(wert: Any) -> str:
    """Ein Wert, wie er in der Meldung steht — Texte in Anführungszeichen, Bool wie in TOML."""
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, str):
        return json.dumps(wert, ensure_ascii=False)
    return str(wert)


def _anf(wert: Any) -> str:
    return f"„{wert}“" if isinstance(wert, str) else _wert_text(wert)


# ---------------------------------------------------------------------------
# Vorlagen
# ---------------------------------------------------------------------------


def _atem(name: str, *dauern: tuple[str, float, str]) -> Takt:
    return Takt(tuple(Phase(n, d, a) for n, d, a in dauern), name=name)


#: Feste Vorlagen (Schlüssel → Takt) — Zahlen ohne Wirkversprechen (`docs/plan_taktgeber.md` §6)
VORLAGEN: Final[dict[str, Takt]] = {
    "atmung_4_6": _atem("Atmung 4-6", ("ein", 4, ART_EIN), ("aus", 6, ART_AUS)),
    "box_4": _atem(
        "Box 4-4-4-4",
        ("ein", 4, ART_EIN),
        ("halten", 4, ART_HALTEN),
        ("aus", 4, ART_AUS),
        ("halten", 4, ART_HALTEN),
    ),
    "atmung_4_7_8": _atem(
        "4-7-8", ("ein", 4, ART_EIN), ("halten", 7, ART_HALTEN), ("aus", 8, ART_AUS)
    ),
    "gleich_5_5": _atem("Gleichtakt 5-5", ("ein", 5, ART_EIN), ("aus", 5, ART_AUS)),
    "gleich_2_5": _atem("Gleichtakt 2,5-2,5", ("ein", 2.5, ART_EIN), ("aus", 2.5, ART_AUS)),
    "metronom_1": Takt((Phase("Schlag", 1, ART_FREI, "holz"),), name="Metronom 1 s"),
    # Bewegungstakte zählen von Haus aus (P138): jede Runde eine Wiederholung
    "kniebeuge_2_1_2": replace(
        _atem("Kniebeuge 2-1-2", ("ab", 2, ART_AB), ("halten", 1, ART_HALTEN), ("auf", 2, ART_AUF)),
        zaehlt=True,
    ),
    # Liegestütz 2-0-1: eine Phase von 0 s gibt es nicht — ab 2 s, auf 1 s
    "liegestuetz_2_1": replace(
        _atem("Liegestütz 2-1", ("ab", 2, ART_AB), ("auf", 1, ART_AUF)), zaehlt=True
    ),
}


def zaehlender_takt(
    wahl: Takt | None, abschnitte: Iterable[Takt | None], uebung: Takt | None
) -> bool:
    """Ob in einem Lauf irgendwo ein Takt zählt (P138) — die Wahl für jetzt, sonst je
    Abschnitt dessen Takt oder der der Übung (`takt_waehlen`); ohne Abschnitt mit Takt der der
    Übung allein. Dann tritt der Zähl-Teil mit Quelle ``takt`` an (`ui.uebung_lauf`).

    >>> k = VORLAGEN["kniebeuge_2_1_2"]; a = VORLAGEN["atmung_4_6"]
    >>> zaehlender_takt(None, [None, None], k), zaehlender_takt(None, [a, None], k)
    (True, True)
    >>> zaehlender_takt(a, [k], k), zaehlender_takt(AUS, [k], k), zaehlender_takt(None, [], a)
    (False, False, False)
    """
    liste = list(abschnitte) or [None]
    return any(
        (t := takt_waehlen(wahl, a, uebung)) is not None and t.zaehlt and not t.leer for a in liste
    )


def animation_fuer(takt: Takt) -> str:
    """Welche Animation gezeigt wird: die gewählte, sonst nach der Phasenzahl (§5).

    >>> animation_fuer(VORLAGEN["metronom_1"]), animation_fuer(VORLAGEN["atmung_4_6"])
    ('puls', 'kreis')
    >>> animation_fuer(VORLAGEN["atmung_4_7_8"]), animation_fuer(VORLAGEN["box_4"])
    ('kreis_halten', 'box')
    >>> animation_fuer(Takt(tuple(Phase("", 1) for _ in range(5))))
    'balken'
    >>> animation_fuer(replace(VORLAGEN["box_4"], animation="welle"))
    'welle'
    """
    if takt.animation in ANIMATIONEN:
        return takt.animation
    n = len(takt.phasen)
    if n <= 1:
        return ANIMATION_PULS
    if n == 2:
        return ANIMATION_KREIS
    if n == 3:
        return ANIMATION_KREIS_HALTEN
    if n == 4:
        return ANIMATION_BOX
    return ANIMATION_BALKEN


# ---------------------------------------------------------------------------
# Bibliothek eigener Takte (app_setting, wie die Timer-Bibliothek)
# ---------------------------------------------------------------------------


def takte_lesen(text: str | None) -> list[Takt]:
    """Eigene Takte aus JSON — Unlesbares fällt weg, nie eine Ausnahme.

    >>> takte_lesen(None), takte_lesen("kaputt"), takte_lesen('[{"phasen": []}, 3]')
    ([], [], [])
    >>> takte_lesen(takte_schreiben([VORLAGEN["atmung_4_6"]]))[0].name
    'Atmung 4-6'
    """
    if not text:
        return []
    try:
        roh = json.loads(text)
    except ValueError:
        return []
    if not isinstance(roh, list):
        return []
    return [t for t in (Takt.aus_dict(d) for d in roh) if t is not None]


def takte_schreiben(takte: Iterable[Takt]) -> str:
    return json.dumps([t.als_dict() for t in takte if not t.leer], ensure_ascii=False)


def in_bibliothek(takte: list[Takt], neu: Takt) -> list[Takt]:
    """Einen Takt in die Bibliothek: gleicher Name ersetzt, sonst hinten an.

    >>> b = in_bibliothek([], replace(VORLAGEN["atmung_4_6"], name="Mein"))
    >>> b = in_bibliothek(b, replace(VORLAGEN["box_4"], name="Mein"))
    >>> [(t.name, len(t.phasen)) for t in b]
    [('Mein', 4)]
    """
    rest = [t for t in takte if t.name != neu.name]
    return [*rest, neu]


def takt_waehlen(wahl: Takt | None, abschnitt: Takt | None, uebung: Takt | None) -> Takt | None:
    """Welcher Takt gilt: Uhr für jetzt > Abschnitt > Übung > keiner. `AUS` als Wahl schaltet ab.

    >>> a, u = VORLAGEN["atmung_4_6"], VORLAGEN["box_4"]
    >>> takt_waehlen(None, None, u).name, takt_waehlen(None, a, u).name
    ('Box 4-4-4-4', 'Atmung 4-6')
    >>> takt_waehlen(VORLAGEN["metronom_1"], a, u).name, takt_waehlen(AUS, a, u)
    ('Metronom 1 s', None)
    >>> takt_waehlen(None, None, None) is None
    True
    """
    if wahl is not None:
        return None if wahl.leer else wahl
    for t in (abschnitt, uebung):
        if t is not None and not t.leer:
            return t
    return None


# ---------------------------------------------------------------------------
# Lage im Takt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lage:
    """Wo der Takt zu einem Zeitpunkt steht."""

    index: int
    phase: Phase
    #: wie viel der Phase vorbei ist, 0…1
    anteil: float
    #: Runde, ab 1
    runde: int
    #: Rest der Phase (s, mit Tempo)
    rest_s: float
    #: gelaufene Zeit in dieser Runde (s)
    t_runde_s: float
    #: die Rundenzahl ist erreicht — der Takt steht auf seinem Ende
    fertig: bool = False
    #: die Dauer der laufenden Phase (s, mit Tempo)
    dauer_s: float = 0.0


def lage(takt: Takt, t_s: float) -> Lage | None:
    """Die Lage im Takt bei ``t_s`` Sekunden nach seinem Beginn — rein aus der Uhr.

    >>> t = VORLAGEN["atmung_4_7_8"]
    >>> l = lage(t, 5.0); (l.index, l.phase.name, l.anteil, l.runde, l.rest_s, l.t_runde_s)
    (1, 'halten', 0.143, 1, 6.0, 5.0)
    >>> l = lage(t, 19.0); (l.index, l.runde, l.anteil), lage(t, -3).index
    ((0, 2, 0.0), 0)
    >>> l = lage(t.mit_tempo(0.5), 5.0); (l.index, l.rest_s, l.dauer_s)
    (1, 0.5, 3.5)
    >>> l = lage(replace(t, runden=2), 40.0); (l.fertig, l.index, l.runde, l.anteil)
    (True, 2, 2, 1.0)
    >>> lage(AUS, 1.0) is None
    True
    """
    if takt.leer:
        return None
    dauer = takt.rundendauer_s
    if dauer <= 0:
        return None
    t = max(t_s, 0.0)
    runden_gelaufen = int(t // dauer)
    if takt.runden is not None and runden_gelaufen >= takt.runden:
        letzte = len(takt.phasen) - 1
        return Lage(
            letzte,
            takt.phasen[letzte],
            1.0,
            takt.runden,
            0.0,
            dauer,
            fertig=True,
            dauer_s=takt.dauer_s(letzte),
        )
    t_runde = t - runden_gelaufen * dauer
    bis = 0.0
    for k, _p in enumerate(takt.phasen):
        phase_dauer = takt.dauer_s(k)
        if t_runde < bis + phase_dauer - 1e-9 or k == len(takt.phasen) - 1:
            in_phase = min(max(t_runde - bis, 0.0), phase_dauer)
            anteil = in_phase / phase_dauer if phase_dauer > 0 else 1.0
            return Lage(
                k,
                takt.phasen[k],
                round(min(anteil, 1.0), 3),
                runden_gelaufen + 1,
                round(max(phase_dauer - in_phase, 0.0), 3),
                round(t_runde, 3),
                dauer_s=phase_dauer,
            )
        bis += phase_dauer
    return None  # pragma: no cover — die Schleife endet immer in der letzten Phase


@dataclass(frozen=True)
class TaktEreignis:
    """Was zwischen zwei Abfragen geschah: eine neue Phase (`PHASE`), ein Rundenende
    (`RUNDE`), das Ende des Takts (`ENDE`)."""

    art: str
    index: int = 0
    runde: int = 0
    phase: Phase | None = None


def wechsel(alt: Lage | None, neu: Lage | None) -> list[TaktEreignis]:
    """Phasenwechsel und Rundenenden zwischen zwei Lagen — für Klang, Vibration, Zählung.

    Ein Takt, der beginnt, meldet seine erste Phase; einer, der endet (kein Takt mehr, oder
    die Rundenzahl erreicht), ein `ENDE`. Dieselbe Lage meldet nichts.

    >>> t = VORLAGEN["atmung_4_6"]
    >>> [e.art for e in wechsel(None, lage(t, 0.0))], wechsel(lage(t, 1.0), lage(t, 2.0))
    (['phase'], [])
    >>> [(e.art, e.index) for e in wechsel(lage(t, 3.9), lage(t, 4.1))]
    [('phase', 1)]
    >>> [(e.art, e.index, e.runde) for e in wechsel(lage(t, 9.9), lage(t, 10.1))]
    [('runde', 1, 1), ('phase', 0, 2)]
    >>> [(e.art, e.runde) for e in wechsel(lage(t, 9.9), lage(t, 31.0))]  # stockte 21 s
    [('runde', 1), ('runde', 2), ('runde', 3), ('phase', 4)]
    >>> [e.art for e in wechsel(lage(t, 5.0), None)]
    ['ende']
    >>> [(e.art, e.runde) for e in wechsel(lage(t, 25.0), lage(t, 0.5))]  # zurückgesprungen
    [('phase', 1)]
    >>> b = replace(t, runden=1)
    >>> [e.art for e in wechsel(lage(b, 9.0), lage(b, 11.0))], wechsel(lage(b, 11), lage(b, 12))
    (['runde', 'ende'], [])
    """
    if alt is None and neu is None:
        return []
    if neu is None:
        return [TaktEreignis(ENDE)] if not alt.fertig else []  # type: ignore[union-attr]
    if alt is None:
        return [] if neu.fertig else [TaktEreignis(PHASE, neu.index, neu.runde, neu.phase)]
    if alt.fertig and neu.fertig:
        return []
    aus: list[TaktEreignis] = []
    if neu.runde < alt.runde and not neu.fertig:
        # Zurückgesprungen (◀ im Timer): keine Runde wurde voll — „Takt zählt“ bekäme sonst
        # eine Wiederholung für die abgebrochene (Durchsicht 11.11.2026)
        return [TaktEreignis(PHASE, neu.index, neu.runde, neu.phase)]
    if neu.runde != alt.runde or neu.fertig:
        # Jede volle Runde einzeln — auch die, über die ein stockender Ticker hinwegsprang
        # (Neuaufbau, Tiefschlaf): „Takt zählt“ verlöre sonst Wiederholungen (N49)
        letzte = neu.runde if neu.fertig else neu.runde - 1
        for runde in range(alt.runde, max(letzte, alt.runde) + 1):
            aus.append(TaktEreignis(RUNDE, alt.index, runde, alt.phase))
    if neu.fertig:
        aus.append(TaktEreignis(ENDE, neu.index, neu.runde, neu.phase))
    elif (neu.runde, neu.index) != (alt.runde, alt.index):
        aus.append(TaktEreignis(PHASE, neu.index, neu.runde, neu.phase))
    return aus


def soll_phasen(takt: Takt, von_s: float, bis_s: float) -> list[tuple[float, str]]:
    """Die Soll-Phasen eines Atemtakts zwischen ``von_s`` und ``bis_s`` (Sekunden ab Beginn
    des Takts) als ``(t_s, "ein"|"aus")`` — fürs Beiwerk ``atem-v1`` (Teil 2). „Halten“
    verlängert die laufende Phase; ein Bewegungstakt oder einer ohne ein/aus liefert nichts.

    >>> soll_phasen(VORLAGEN["atmung_4_7_8"], 0, 40)
    [(0.0, 'ein'), (11.0, 'aus'), (19.0, 'ein'), (30.0, 'aus'), (38.0, 'ein')]
    >>> soll_phasen(VORLAGEN["box_4"], 5, 20), soll_phasen(VORLAGEN["kniebeuge_2_1_2"], 0, 20)
    ([(8.0, 'aus'), (16.0, 'ein')], [])
    >>> soll_phasen(replace(VORLAGEN["atmung_4_6"], runden=1), 0, 100)
    [(0.0, 'ein'), (4.0, 'aus')]
    """
    if not takt.ist_atmung() or bis_s <= von_s:
        return []
    dauer = takt.rundendauer_s
    if dauer <= 0:  # nur Phasen ohne Dauer: die Schleife käme nie voran (N66)
        return []
    aus: list[tuple[float, str]] = []
    runde = 0
    while True:
        start = runde * dauer
        if start >= bis_s or (takt.runden is not None and runde >= takt.runden):
            break
        bis = start
        for k, p in enumerate(takt.phasen):
            if p.art in (ART_EIN, ART_AUS) and von_s <= bis < bis_s:
                aus.append((round(bis, 3), p.art))
            bis += takt.dauer_s(k)
        runde += 1
    return aus


class TaktLauf:
    """Die Lage eines Takts über eine Uhr — mit Tempoänderungen, die nicht springen.

    ``t_s`` ist die Zeit seit Beginn des Takts (Abschnitt bzw. Stoppuhr). `tempo_setzen`
    hält die Lage: die gelaufenen Runden samt Anteil bleiben, ab jetzt gilt das neue Tempo
    (P139: nur für jetzt — der Takt selbst bleibt, wie er gespeichert ist).

    >>> t = VORLAGEN["atmung_4_6"]
    >>> lauf = TaktLauf(t)
    >>> l = lauf.lage(12.0); (l.index, l.runde, l.t_runde_s)
    (0, 2, 2.0)
    >>> lauf.tempo_setzen(12.0, 2.0)
    >>> l = lauf.lage(12.0); (l.index, l.runde, l.t_runde_s, l.dauer_s)  # dieselbe Lage, gedehnt
    (0, 2, 4.0, 8.0)
    >>> l = lauf.lage(16.0); (l.index, l.rest_s), lauf.takt.tempo, lauf.tempo
    ((1, 12.0), 1.0, 2.0)
    >>> lauf.tempo_setzen(16.0, 0.5); lauf.lage(16.0).index, lauf.effektiv.rundendauer_s
    (1, 5.0)
    """

    def __init__(self, takt: Takt, tempo: float = 1.0) -> None:
        self.takt = takt
        self.tempo = tempo_lesen(tempo)
        self._anker_t = 0.0
        self._anker_runden = 0.0

    @property
    def effektiv(self) -> Takt:
        """Der Takt mit dem Tempo von jetzt (Takt-Tempo × Regler)."""
        return self.takt.mit_tempo(self.takt.tempo * self.tempo)

    def _runden(self, t_s: float) -> float:
        dauer = self.effektiv.rundendauer_s
        if dauer <= 0:
            return 0.0
        return max(self._anker_runden + (t_s - self._anker_t) / dauer, 0.0)

    def lage(self, t_s: float) -> Lage | None:
        """Die Lage bei ``t_s`` — über die gelaufenen Runden, damit ein Tempowechsel nicht
        springt."""
        eff = self.effektiv
        return lage(eff, self._runden(t_s) * eff.rundendauer_s)

    def tempo_setzen(self, t_s: float, faktor: float) -> None:
        """Ab ``t_s`` gilt ``faktor`` — die Lage bleibt, wo sie ist."""
        self._anker_runden = self._runden(t_s)
        self._anker_t = t_s
        self.tempo = tempo_lesen(faktor)


__all__ = [
    "ANIMATIONEN",
    "ANIMATION_BALKEN",
    "ANIMATION_BOX",
    "ANIMATION_KREIS",
    "ANIMATION_KREIS_HALTEN",
    "ANIMATION_PULS",
    "ANIMATION_WELLE",
    "ARTEN",
    "ARTEN_ATMUNG",
    "ARTEN_BEWEGUNG",
    "ART_AB",
    "ART_AUF",
    "ART_AUS",
    "ART_EIN",
    "ART_FREI",
    "ART_HALTEN",
    "AUS",
    "ENDE",
    "KLANG_VORGABE",
    "MAX_DAUER_S",
    "MAX_PHASEN",
    "MIN_DAUER_S",
    "PHASE",
    "RUNDE",
    "TEMPO_MAX",
    "TEMPO_MIN",
    "VORLAGEN",
    "Lage",
    "Phase",
    "Takt",
    "TaktEreignis",
    "TaktLauf",
    "animation_fuer",
    "dauer_lesen",
    "dauer_text",
    "faktor_von",
    "geschwindigkeit",
    "in_bibliothek",
    "lage",
    "rate_text",
    "soll_phasen",
    "takt_pruefen",
    "takt_waehlen",
    "takte_lesen",
    "takte_schreiben",
    "tempo_lesen",
    "tempo_text",
    "wechsel",
    "zaehlender_takt",
]
