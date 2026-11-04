"""Diagnosemodus ohne Bildschirm: was ein Gerät kann, was es kostet, welche Marke gilt.

Plan: `docs/plan_diagnosemodus.md`. Hier liegt, was Sensorblatt, Stand-Blatt, Marken-Leiste
und Einstellungen brauchen und ohne flet testbar ist:

- `sensoren` — die Zeilen des Sensorblatts (§2.3): je Strom, ob das Gerät ihn hat
  („✓ geprüft“: am Gerät gesehen, „laut Profil“: nur erwartet), ob er sich im Diagnosemodus
  einschalten lässt und was er an Speicher kostet;
- `menge_mb_h` — Speicher des Rohmitschnitts je Stunde (aus dem Pilot, §3.6);
- `ablage` / `alle_loeschen` — Mitschnitte auf dem Gerät (Einstellungen, P114);
- `marken_art` und `MarkenZaehler` — welche Art ein Tipp in der Leiste hat und die Nummer im
  Satz (§2.5, Stufe 3).

Keine Bewertung, keine Rechnung an Messwerten — nur Zahlen und Zustände.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hrv_core import mitschnitt as mt
from hrv_core.geraete.pmd import PMD_SERVICE_UUID

from trainingsapp.core.result_spec import ResultSpec, basis_key

#: Ordner der Rohmitschnitte ohne Messung (unbekannte Geräte, Stufe 6) im Datenverzeichnis
DIAGNOSE_ORDNER: Final[str] = "Diagnose"
#: Herzfrequenz-Dienst (0x180D)
HR_DIENST: Final[str] = "0000180d-0000-1000-8000-00805f9b34fb"
#: Ab so viel Speicher weisen die Einstellungen auf die Ablage hin (P114)
HINWEIS_AB_BYTES: Final[int] = 500 * 1024 * 1024

# Zustände eines Stroms im Sensorblatt
GEPRUEFT: Final[str] = "geprueft"  # am Gerät gesehen (Merkmalsliste, Dienste)
LAUT_PROFIL: Final[str] = "laut_profil"  # nur erwartet
NUR_ROH: Final[str] = "nur_roh"  # vorhanden, aber ohne Dekoder: nur im Rohmitschnitt
FEHLT: Final[str] = "fehlt"

#: Speicher je Stunde im Rohmitschnitt (MB), aus dem Pilot mit dem H10 (Brustgurt-Diagnose,
#: 3.11.2026: 7,6 MB in 30 min mit EKG und Beschleunigung 200 Hz): Hex je Paket plus Zeile
MB_H_HR: Final[float] = 0.4
MB_H_EKG: Final[float] = 3.5
MB_H_ACC_200: Final[float] = 10.6


def menge_mb_h(*, ekg: bool, acc_hz: int | None) -> float:
    """Speicher des Rohmitschnitts je Stunde (MB) — grob, zum Abwägen.

    >>> menge_mb_h(ekg=True, acc_hz=200), menge_mb_h(ekg=False, acc_hz=None)
    (14.5, 0.4)
    >>> menge_mb_h(ekg=False, acc_hz=50)
    3.05
    """
    menge = MB_H_HR + (MB_H_EKG if ekg else 0.0)
    if acc_hz:
        menge += MB_H_ACC_200 * acc_hz / 200
    return round(menge, 2)


@dataclass(frozen=True, slots=True)
class SensorZeile:
    """Eine Zeile des Sensorblatts."""

    schluessel: str  # hr, ecg, acc, ppi, ppg, gyro, mag
    name: str
    zustand: str  # GEPRUEFT, LAUT_PROFIL, NUR_ROH, FEHLT
    schaltbar: bool  # im Diagnosemodus ein- und ausschaltbar
    immer: bool  # läuft ohnehin (Herzfrequenz, PPI)
    mb_h: float
    hinweis: str = ""

    @property
    def vorhanden(self) -> bool:
        return self.zustand != FEHLT

    @property
    def zustand_text(self) -> str:
        return {
            GEPRUEFT: "✓ geprüft",
            LAUT_PROFIL: "laut Profil",
            NUR_ROH: "✓ vorhanden · nur Rohmitschnitt",
            FEHLT: "–",
        }[self.zustand]


def sensoren(
    faehigkeiten: Iterable[str],
    *,
    dienste: Iterable[str] = (),
    merkmale: Iterable[str] | None = None,
    acc_hz: int = 200,
) -> list[SensorZeile]:
    """Die Zeilen des Sensorblatts (Plan §2.3).

    ``faehigkeiten``: das Profil (`devices.profiles`, ``CAP_*``); ``dienste``: was das Gerät
    beim Verbinden meldete; ``merkmale``: die PMD-Merkmalsliste, wenn gelesen (``None``: nicht
    gelesen — dann gilt das Profil). Schaltbar sind EKG und Beschleunigung — die Ströme, die
    am H10 erprobt sind; PPG, Gyroskop und Magnetometer stehen nur da, wenn das Gerät sie hat.

    >>> h10 = {"hr_rr", "pmd_ecg", "pmd_acc"}
    >>> dienste = {PMD_SERVICE_UUID, HR_DIENST}
    >>> [(z.schluessel, z.zustand, z.schaltbar) for z in sensoren(h10, dienste=dienste,
    ...     merkmale={"ecg", "acc"})]  # doctest: +NORMALIZE_WHITESPACE
    [('hr', 'geprueft', False), ('ecg', 'geprueft', True), ('acc', 'geprueft', True)]
    >>> [(z.schluessel, z.zustand) for z in sensoren(h10, dienste={PMD_SERVICE_UUID})]
    [('hr', 'laut_profil'), ('ecg', 'laut_profil'), ('acc', 'laut_profil')]
    >>> verity = {"pmd_ppi", "pmd_ppg", "pmd_acc"}
    >>> [(z.schluessel, z.zustand, z.schaltbar) for z in sensoren(verity, dienste=dienste,
    ...     merkmale={"ppi", "ppg", "acc", "gyro", "mag"})]  # doctest: +NORMALIZE_WHITESPACE
    [('hr', 'geprueft', False), ('ppi', 'geprueft', False), ('acc', 'geprueft', True),
     ('ppg', 'nur_roh', False), ('gyro', 'nur_roh', False), ('mag', 'nur_roh', False)]
    >>> [z.zustand for z in sensoren({"hr_rr"})]   # Brustgurt ohne PMD
    ['laut_profil']
    """
    caps = set(faehigkeiten)
    gemeldet = {d.lower() for d in dienste}
    hat_pmd = PMD_SERVICE_UUID in gemeldet if gemeldet else None
    m = None if merkmale is None else set(merkmale)

    def pmd_zustand(name: str, cap: str | None) -> str | None:
        if m is not None:
            return GEPRUEFT if name in m else None
        if hat_pmd is False:
            return None
        if cap is not None and cap in caps:
            return LAUT_PROFIL
        return None

    zeilen = [
        SensorZeile(
            "hr",
            "Herzfrequenz und RR" if "hr_rr" in caps else "Herzfrequenz",
            GEPRUEFT if HR_DIENST in gemeldet else LAUT_PROFIL,
            schaltbar=False,
            immer=True,
            mb_h=MB_H_HR,
        )
    ]
    if (z := pmd_zustand("ppi", "pmd_ppi")) is not None:
        zeilen.append(
            SensorZeile("ppi", "Pulsintervalle (PPI)", z, schaltbar=False, immer=True, mb_h=0.3)
        )
    if (z := pmd_zustand("ecg", "pmd_ecg")) is not None:
        zeilen.append(
            SensorZeile("ecg", "EKG 130 Hz", z, schaltbar=True, immer=False, mb_h=MB_H_EKG)
        )
    if (z := pmd_zustand("acc", "pmd_acc")) is not None:
        zeilen.append(
            SensorZeile(
                "acc",
                f"Beschleunigung {acc_hz} Hz",
                z,
                schaltbar=True,
                immer=False,
                mb_h=round(MB_H_ACC_200 * acc_hz / 200, 1),
                hinweis="kostet Akku des Gurts",
            )
        )
    for name, titel, cap in (
        ("ppg", "PPG (optisch)", "pmd_ppg"),
        ("gyro", "Gyroskop", None),
        ("mag", "Magnetometer", None),
    ):
        if pmd_zustand(name, cap) is not None:
            zeilen.append(
                SensorZeile(
                    name,
                    titel,
                    NUR_ROH,
                    schaltbar=False,
                    immer=False,
                    mb_h=0.0,
                    hinweis="noch nicht einschaltbar",
                )
            )
    return zeilen


def fehlende(zeilen: Iterable[SensorZeile]) -> str:
    """Was das Gerät von den bekannten PMD-Strömen nicht hat — für eine Zeile im Blatt.

    >>> fehlende(sensoren({"hr_rr", "pmd_ecg", "pmd_acc"}, merkmale={"ecg", "acc"}))
    'PPI, PPG, Gyroskop, Magnetometer'
    """
    da = {z.schluessel for z in zeilen}
    namen = {"ppi": "PPI", "ecg": "EKG", "acc": "Beschleunigung", "ppg": "PPG"}
    namen |= {"gyro": "Gyroskop", "mag": "Magnetometer"}
    return ", ".join(t for k, t in namen.items() if k not in da)


# ---------------------------------------------------------------------------
# Marken: Art aus dem Kontext, Nummer im Satz (Plan §2.5, Stufe 3)
# ---------------------------------------------------------------------------

#: Arten der Marke für die Leiste (Störung ist ein eigener Knopf, keine Art)
WDH: Final[str] = mt.MARKE_WDH
ATEM: Final[str] = mt.MARKE_ATEM
ART_NAMEN: Final[dict[str, str]] = {
    mt.MARKE_WDH: "Wiederholung",
    mt.MARKE_ATEM: "Atemzug",
    mt.MARKE_STOERUNG: "Störung",
    mt.MARKE_FREI: "Marke",
}


def hat_wiederholungen(spec: ResultSpec | None) -> bool:
    """Zählt die Übung Wiederholungen (ein Feld der Art ``reps``)? Sonst gelten Atemzüge.

    >>> from trainingsapp.core.result_spec import FieldSpec, FieldType
    >>> hat_wiederholungen(ResultSpec(fields=[FieldSpec("reps", FieldType.SET_LIST, "Wdh.")]))
    True
    >>> hat_wiederholungen(ResultSpec(fields=[FieldSpec("hold", FieldType.SET_LIST, "Halten",
    ...     unit="s")])), hat_wiederholungen(None)
    (False, False)
    """
    if spec is None:
        return False
    return any(basis_key(f.key) == "reps" for f in spec.fields)


@dataclass(frozen=True, slots=True)
class MarkenKontext:
    """Was ein Tipp in der Leiste gerade bedeutet."""

    art: str  # WDH oder ATEM
    uebung: str | None = None  # Name der laufenden Übung
    uebung_code: str | None = None  # Kurzcode (raw-v1 ``uebungen``)
    satz: int | None = None
    phase: str = "frei"  # uebung, pause, frei

    @property
    def schluessel(self) -> tuple[str | None, int | None, str]:
        """Ändert sich er, gilt eine Wahl im Chip nicht mehr (Plan §2.5)."""
        return (self.uebung_code, self.satz, self.phase)

    def als_dict(self) -> dict[str, object]:
        """``kontext`` der Marke im Mitschnitt."""
        d: dict[str, object] = {"phase": self.phase}
        if self.uebung:
            d["uebung"] = self.uebung
        if self.uebung_code:
            d["uebung_id"] = self.uebung_code
        if self.satz:
            d["satz"] = self.satz
        return d

    def text(self, art: str | None = None) -> str:
        """Die Kopfzeile der Leiste: „Wiederholung · Kniebeuge S2“."""
        teile = [ART_NAMEN.get(art or self.art, art or self.art)]
        if self.uebung:
            teile.append(self.uebung + (f" S{self.satz}" if self.satz else ""))
        elif self.phase == "pause":
            teile.append("Pause")
        return " · ".join(teile)


def kontext_aus_notizen(
    ereignisse: Iterable[dict], wiederholungen: Callable[[str], bool]
) -> MarkenKontext:
    """Die Art der nächsten Marke aus den automatischen Notizen der laufenden Aufnahme.

    Zwischen „Übung: Start“ und „Übung: Ende“ (Plan-Ablauf, Uhr der Übung) gilt die Übung;
    hat sie Wiederholungen (``wiederholungen(kurzcode)``), ist ein Tipp eine Wiederholung —
    außer in einem Abschnitt des Timers, der nicht zählt (Pause), und solange der Timer
    angehalten ist. Ein eingetragener Satz (``person/leistung``) zählt den Satz weiter.
    Sonst — Halte- und Atemübungen, Pausen, Messung ohne Übung — ein Atemzug.

    >>> start = {"marke": {"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
    ...          "uebungen": ["KB000001"]}
    >>> satz = {"marke": {"quelle": "person", "art": "leistung", "feld": "reps", "wert": 12}}
    >>> pause = {"marke": {"quelle": "timer", "art": "abschnitt", "name": "Pause",
    ...                    "zaehlt": False}}
    >>> wdh = lambda code: code == "KB000001"
    >>> kontext_aus_notizen([], wdh).art
    'atem'
    >>> k = kontext_aus_notizen([start, satz], wdh)
    >>> k.art, k.uebung, k.satz, k.text()
    ('wdh', 'Kniebeuge', 2, 'Wiederholung · Kniebeuge S2')
    >>> kontext_aus_notizen([start, pause], wdh).art
    'atem'
    >>> ende = {"marke": {"quelle": "plan", "art": "uebung_ende"}, "uebungen": ["KB000001"]}
    >>> kontext_aus_notizen([start, ende], wdh).text()
    'Atemzug'
    """
    code: str | None = None
    name: str | None = None
    satz = 0
    phase = "frei"
    for e in ereignisse:
        m = e.get("marke") if isinstance(e, dict) else None
        if not isinstance(m, dict):
            continue
        art, quelle = m.get("art"), m.get("quelle")
        codes = [c for c in e.get("uebungen") or [] if isinstance(c, str)]
        if art == "uebung_start":
            code = codes[0] if codes else None
            name = str(m.get("name") or e.get("text") or "") or None
            satz, phase = 1, "uebung"
        elif art == "uebung_ende":
            code = name = None
            satz, phase = 0, "frei"
        elif quelle == "person" and art == "leistung":
            if code is not None:
                satz += 1
        elif quelle == "timer" and art == "abschnitt":
            phase = "pause" if m.get("zaehlt") is False else ("uebung" if code else "frei")
        elif art == "pause":
            phase = "pause"
        elif art == "weiter":
            phase = "uebung" if code else "frei"
    art_ = WDH if phase == "uebung" and code is not None and wiederholungen(code) else ATEM
    return MarkenKontext(art_, name, code, satz or None, phase)


class MarkenZaehler:
    """Die Nummer einer Marke im Satz — je Art, Übung und Satz ab 1; ↶ zählt zurück.

    >>> z = MarkenZaehler()
    >>> k = MarkenKontext(WDH, "Kniebeuge", "KB", 1, "uebung")
    >>> z.weiter(WDH, k), z.weiter(WDH, k), z.zurueck(), z.weiter(WDH, k)
    (1, 2, 1, 2)
    >>> z.weiter(WDH, MarkenKontext(WDH, "Kniebeuge", "KB", 2, "uebung"))   # neuer Satz
    1
    >>> z.stand(WDH, MarkenKontext(WDH, "Kniebeuge", "KB", 1, "uebung"))
    2
    """

    def __init__(self) -> None:
        self._n: dict[tuple[str, str | None, int | None], int] = {}
        self._letzte: list[tuple[str, str | None, int | None]] = []

    def _schluessel(self, art: str, k: MarkenKontext) -> tuple[str, str | None, int | None]:
        return (art, k.uebung_code, k.satz)

    def weiter(self, art: str, k: MarkenKontext) -> int:
        s = self._schluessel(art, k)
        self._n[s] = self._n.get(s, 0) + 1
        self._letzte.append(s)
        return self._n[s]

    def zurueck(self) -> int:
        """Die letzte Marke zurücknehmen — gibt den neuen Stand ihres Satzes zurück."""
        if not self._letzte:
            return 0
        s = self._letzte.pop()
        self._n[s] = max(0, self._n.get(s, 0) - 1)
        return self._n[s]

    def stand(self, art: str, k: MarkenKontext) -> int:
        return self._n.get(self._schluessel(art, k), 0)


def kontext_zeile(notiz: dict) -> tuple[str, dict[str, object]] | None:
    """Eine automatische Notiz als ``kontext``-Zeile des Mitschnitts: ``(was, felder)`` —
    ``None`` für Notizen ohne Marke (was die Person schreibt, bleibt in der Messdatei).

    >>> kontext_zeile({"text": "Kniebeuge: Start", "uebungen": ["KB000001"],
    ...     "marke": {"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"}})
    ('uebung_start', {'uebung': 'Kniebeuge', 'uebung_id': 'KB000001'})
    >>> kontext_zeile({"marke": {"quelle": "person", "art": "leistung", "feld": "reps",
    ...     "wert": 12}})
    ('satz', {'feld': 'reps', 'wert': 12})
    >>> kontext_zeile({"marke": {"quelle": "timer", "art": "abschnitt", "name": "Pause",
    ...     "runde": 1, "von": 3, "zaehlt": False, "soll_s": 60}})  # doctest: +NORMALIZE_WHITESPACE
    ('timer_abschnitt', {'abschnitt': 'Pause', 'runde': 1, 'von': 3, 'soll_s': 60,
     'phase': 'pause'})
    >>> kontext_zeile({"text": "frei"}) is None
    True
    """
    m = notiz.get("marke")
    if not isinstance(m, dict):
        return None
    quelle, art = str(m.get("quelle") or ""), str(m.get("art") or "")
    codes = [c for c in notiz.get("uebungen") or [] if isinstance(c, str)]
    felder: dict[str, object] = {}
    if quelle == "person" and art == "leistung":
        was = "satz"
    elif quelle == "plan" and art in ("uebung_start", "uebung_ende", "pause"):
        was = art
    elif quelle == "timer":
        was = f"timer_{art}"
    else:
        was = f"{quelle}_{art}" if quelle else art
    name = m.get("name")
    if was == "timer_abschnitt":
        if name:
            felder["abschnitt"] = name
    elif name:
        felder["uebung"] = name
    if codes:
        felder["uebung_id"] = codes[0]
    for schluessel in ("feld", "wert", "runde", "von", "profil", "soll_s"):
        if m.get(schluessel) not in (None, ""):
            felder[schluessel] = m[schluessel]
    if was == "timer_abschnitt":
        felder["phase"] = "pause" if m.get("zaehlt") is False else "uebung"
    return was, felder


def satz_text(v: dict[str, object]) -> str:
    """Der Vergleich nach dem Satz (Stufe 8): Marken, Zähler (Prototyp), eingetragen.

    >>> satz_text({"uebung": "Kniebeuge", "satz": 1, "marken": 12, "zaehler": 11,
    ...            "eingetragen": 12})
    'Kniebeuge S1: Marken 12 · Zähler 11 (Prototyp) · eingetragen 12'
    >>> satz_text({"uebung": None, "satz": None, "marken": 0, "zaehler": None,
    ...            "eingetragen": 8})
    'Satz: Marken 0 · Zähler – · eingetragen 8'
    """
    wer = str(v.get("uebung") or "Satz")
    if v.get("uebung") and v.get("satz"):
        wer += f" S{v['satz']}"
    zaehler = v.get("zaehler")
    z = "–" if zaehler is None else f"{zaehler} (Prototyp)"
    eingetragen = v.get("eingetragen")
    e = "–" if eingetragen is None else str(eingetragen)
    return f"{wer}: Marken {v.get('marken', 0)} · Zähler {z} · eingetragen {e}"


# ---------------------------------------------------------------------------
# Ablage
# ---------------------------------------------------------------------------


def mitschnitte(basis: Path) -> list[Path]:
    """Alle Rohmitschnitte im Datenverzeichnis: neben Messungen, Backups und ohne Messung."""
    basis = Path(basis)
    gefunden: list[Path] = []
    messungen = basis / "Messungen"
    if messungen.is_dir():
        gefunden += [p for p in messungen.glob("*/*" + mt.ENDUNG) if p.is_file()]
    ordner = basis / DIAGNOSE_ORDNER
    if ordner.is_dir():
        gefunden += [p for p in ordner.glob("*/" + mt.DATEINAME) if p.is_file()]
    return sorted(gefunden)


def ablage(basis: Path) -> tuple[int, int]:
    """``(Anzahl, Bytes)`` der Mitschnitte auf dem Gerät — laufende Journale mitgezählt."""
    dateien = mitschnitte(basis)
    groesse = 0
    for p in dateien:
        with contextlib.suppress(OSError):
            groesse += p.stat().st_size
    return len(dateien), groesse


def alle_loeschen(basis: Path, *, ausser: Iterable[Path] = ()) -> int:
    """Alle Mitschnitte löschen — die Messungen bleiben. ``ausser``: etwa der laufende.
    Gibt die Zahl der gelöschten Dateien zurück."""
    schonen = {Path(p).resolve() for p in ausser}
    n = 0
    for p in mitschnitte(basis):
        if p.resolve() in schonen:
            continue
        with contextlib.suppress(OSError):
            p.unlink()
            n += 1
    return n


def zusammenfassung_text(z: dict[str, object], n_bytes: int) -> str:
    """Die Zeile der Auswertung: „34 min · 9,1 MB · 85 Marken (Wdh 60, Atem 25)“.

    ``z``: `hrv_core.mitschnitt.zusammenfassen`; ``n_bytes``: Größe der Datei.

    >>> zusammenfassung_text({"dauer_s": 2040.0, "marken": {"wdh": 60, "atem": 25},
    ...     "stroeme": {"acc": {"rahmen": 9, "proben": 324, "rate_hz": 200.0, "luecken": 0}}},
    ...     9_100_000)
    '34 min · 9,1 MB · 85 Marken (Wdh 60, Atem 25) · Beschleunigung 200 Hz'
    >>> zusammenfassung_text({"dauer_s": 30.0, "marken": {}, "stroeme": {}}, 2000)
    '30 s · 2 KB · keine Marken'
    """
    marken = z.get("marken") or {}
    assert isinstance(marken, dict)
    n = sum(int(v) for v in marken.values())
    namen = {"wdh": "Wdh", "atem": "Atem", "stoerung": "Störung", "marke": "Marke"}
    if n:
        folge = [*namen, *(k for k in marken if k not in namen)]  # Wdh, Atem, Störung, Marke
        einzeln = ", ".join(f"{namen.get(k, k)} {marken[k]}" for k in folge if marken.get(k))
        teil = f"{n} Marken ({einzeln})"
    else:
        teil = "keine Marken"
    teile = [dauer_text(float(z.get("dauer_s") or 0.0)), groesse_text(n_bytes), teil]  # type: ignore[arg-type]
    stroeme = z.get("stroeme") or {}
    assert isinstance(stroeme, dict)
    for name, titel in (("ecg", "EKG"), ("acc", "Beschleunigung")):
        s = stroeme.get(name)
        if isinstance(s, dict) and s.get("proben"):
            luecken = int(s.get("luecken") or 0)
            teile.append(
                f"{titel} {float(s.get('rate_hz') or 0):g} Hz"
                + (f", {luecken} Lücken" if luecken else "")
            )
    return " · ".join(teile)


def groesse_text(n_bytes: int) -> str:
    """Speicher für Menschen.

    >>> groesse_text(0), groesse_text(2_500), groesse_text(9_100_000), groesse_text(2_300_000_000)
    ('0 KB', '2 KB', '9,1 MB', '2,3 GB')
    """
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.1f} GB".replace(".", ",")
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB".replace(".", ",")
    return f"{round(n_bytes / 1e3)} KB"


def dauer_text(s: float) -> str:
    """Laufzeit kurz: ``34 min``, ``1 h 05 min``, ``40 s``.

    >>> dauer_text(40), dauer_text(34 * 60 + 10), dauer_text(3900)
    ('40 s', '34 min', '1 h 05 min')
    """
    s = max(0, int(s))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


__all__ = [
    "ART_NAMEN",
    "ATEM",
    "DIAGNOSE_ORDNER",
    "FEHLT",
    "GEPRUEFT",
    "HINWEIS_AB_BYTES",
    "HR_DIENST",
    "LAUT_PROFIL",
    "NUR_ROH",
    "WDH",
    "MarkenKontext",
    "MarkenZaehler",
    "SensorZeile",
    "ablage",
    "alle_loeschen",
    "dauer_text",
    "fehlende",
    "groesse_text",
    "hat_wiederholungen",
    "kontext_aus_notizen",
    "kontext_zeile",
    "menge_mb_h",
    "mitschnitte",
    "satz_text",
    "sensoren",
    "zusammenfassung_text",
]
