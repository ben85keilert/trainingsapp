"""Herzfrequenz-Auswertung einer gespeicherten Aufzeichnung (Stufe 2, Ben 29.10.2026).

Aus Messdatei, Korrektur, Abschnitten und Profil entsteht alles, was die Herzfrequenz-Sicht
der Auswertung zeigt und der Cache behält (`data/hf_cache.py`): die Werte der ganzen
Aufnahme, je Abschnitt (mit Erholung am Ende, wenn der Endteil sie hergibt), die
Erholungen aus den Marken ``person/erholung``, der **HFmax-Kandidat** (höchstes 30-s-Mittel
mit Plateau — ein Vorschlag, nie gesetzt), der **Ruhe-HF-Kandidat** einer kurzen
Morgenmessung, die **Nacht-HF** (Schlafabschnitt oder, ohne einen, das Nachtfenster 20–10 Uhr
der Aufnahme mit ≥ 4 h Daten — übernommen wird sie erst auf Tippen), das Tagesprofil und die
**vorgeschlagenen Abschnitte** aus der HF (Belastung, Ruhe, Schlaf), die die Person erst
bestätigt (hrv-research Entscheidungen 12, 14, 15).

Achse ist die **Wanduhr** der Aufnahme (`hrv_core.herzfrequenz`); Abschnitte kommen vom
Aufrufer schon auf die Wanduhr umgerechnet (`achse_zu_wand`). Alles ist aus Datei + Profil
nachrechenbar; `profil_stand` sagt, mit welchem Profil gerechnet wurde (Frage 4: alte
Aufnahmen behalten ihr damaliges Profil, Nachrechnen nur auf Wunsch).

Kein flet, kein SQL.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from typing import Any, Final

import numpy as np
from hrv_core import herzfrequenz as hz
from hrv_core.constants import ALGO_VERSION, HF_NACHT_MIN_S
from hrv_core.recording import Recording

from trainingsapp.core.hf_profil import HfProfil, grenzen_bpm

#: Eine Aufnahme zwischen 4 und 20 min gilt als mögliche Morgenmessung (Ruhe-HF-Kandidat)
RUHE_MIN_S: Final[float] = 240.0
RUHE_MAX_S: Final[float] = 1200.0
#: Ab 10 min zählt sie als INTERLIVE-Länge (`messung_morgen_10`)
RUHE_INTERLIVE_S: Final[float] = 600.0
#: Erholung am Ende eines Abschnitts, wenn danach so viele Sekunden Daten liegen
ERHOLUNG_NACHLAUF_S: Final[float] = 60.0
#: Drift erst ab dieser Abschnittsdauer
DRIFT_AB_S: Final[float] = 1200.0
#: Anfang eines Abschnittsnamens, der als bestätigte Schlafzeit gilt („Schlaf“, „Schlafen“,
#: „Nacht“, „Nachtruhe“ …)
SCHLAF_NAMEN: Final[tuple[str, ...]] = ("schlaf", "nacht")
#: Nachtfenster (Ortszeit) für den Schlafkandidaten und die Nacht-HF ohne Schlafabschnitt:
#: 20 Uhr bis 10 Uhr
NACHT_VON_H: Final[int] = 20
NACHT_BIS_H: Final[int] = 10
#: Stand dieser Auswertung (neben `ALGO_VERSION` aus hrv-core): springt sie, gilt jeder Cache
#: als veraltet. 1 = v0.3.31; 2 = Nacht-HF auch ohne Schlafabschnitt aus dem Nachtfenster.
AUSWERTUNG_VERSION: Final[int] = 2
#: Grundlage der Nacht-HF: ein Schlafabschnitt oder das Nachtfenster der Aufnahme
NACHT_ABSCHNITT: Final[str] = "abschnitt"
NACHT_FENSTER: Final[str] = "nachtfenster"
#: Ein Vorschlag, der sich zu mehr als diesem Anteil mit einem Abschnitt deckt, entfällt
VORSCHLAG_DECKUNG_MAX: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class AbschnittWand:
    """Ein Abschnitt auf der Wanduhr der Aufnahme (Grenzen und Rechenbereich)."""

    id: str
    name: str
    von_s: float
    bis_s: float
    kopf_s: float = 0.0
    endteil_s: float = 0.0

    @property
    def rechen_von(self) -> float:
        return self.von_s - self.kopf_s

    @property
    def rechen_bis(self) -> float:
        return self.bis_s + self.endteil_s


def achse_zu_wand(achse: Sequence[float], wand: Sequence[float], x: float) -> float:
    """Eine Zeit der Kurvenachse (Herzuhr der App) auf die Wanduhr der Aufnahme — linear
    zwischen den Schlägen; vor dem ersten und hinter dem letzten mit deren Versatz.

    >>> achse_zu_wand([1.0, 2.0, 3.0], [1.0, 2.5, 4.0], 2.5)
    3.25
    >>> achse_zu_wand([1.0, 2.0], [5.0, 6.0], 0.0), achse_zu_wand([], [], 7.0)
    (4.0, 7.0)
    """
    if not achse:
        return float(x)
    a = np.asarray(achse, dtype=float)
    w = np.asarray(wand, dtype=float)
    if x <= a[0]:
        return float(w[0] - (a[0] - x))
    if x >= a[-1]:
        return float(w[-1] + (x - a[-1]))
    return float(np.interp(x, a, w))


def wand_zu_achse(achse: Sequence[float], wand: Sequence[float], t: float) -> float:
    """Umkehrung von `achse_zu_wand` (für Abschnitte, die aus HF-Vorschlägen entstehen)."""
    if not achse:
        return float(t)
    a = np.asarray(achse, dtype=float)
    w = np.asarray(wand, dtype=float)
    if t <= w[0]:
        return float(a[0] - (w[0] - t))
    if t >= w[-1]:
        return float(a[-1] + (t - w[-1]))
    return float(np.interp(t, w, a))


#: Talk-Test: die HF der 30 s vor der Marke „Sprechen wird schwer“ ist der Marker für VT1
TALK_FENSTER_S: Final[float] = 30.0


def talk_marken(rec: Recording) -> list[float]:
    """``t_wall_s`` je Marke ``person/talk`` (Talk-Test: „Sprechen wird schwer“)."""
    out: list[float] = []
    for e in rec.ereignisse:
        marke = e.get("marke") if isinstance(e, dict) else None
        if isinstance(marke, dict) and marke.get("art") == "talk":
            t = e.get("t_wall_s")
            if isinstance(t, int | float) and not isinstance(t, bool):
                out.append(float(t))
    return out


def erholungs_marken(rec: Recording) -> list[tuple[float, str, str]]:
    """``(t_wall_s, kontext, haltung)`` je Marke ``person/erholung`` der Datei."""
    out: list[tuple[float, str, str]] = []
    for e in rec.ereignisse:
        marke = e.get("marke") if isinstance(e, dict) else None
        if not isinstance(marke, dict) or marke.get("art") != "erholung":
            continue
        t = e.get("t_wall_s")
        if isinstance(t, int | float) and not isinstance(t, bool):
            out.append((float(t), str(marke.get("kontext") or ""), str(marke.get("haltung") or "")))
    return out


@dataclass
class HfAuswertung:
    """Das Ergebnis — JSON-tauglich bis auf ``reihe`` (die baut der Aufrufer für Kurven neu)."""

    gesamt: dict[str, Any]
    abschnitte: list[dict[str, Any]]
    erholungen: list[dict[str, Any]]
    hfmax_kandidat: dict[str, Any] | None
    ruhe_kandidat: dict[str, Any] | None
    nacht: dict[str, Any] | None
    #: Talk-Test: HF der 30 s vor der ersten Marke „Sprechen wird schwer“ (VT1-Marker)
    talk: dict[str, Any] | None
    vorschlaege: list[dict[str, Any]]
    aktivitaet: dict[str, Any] | None
    profil_stand: dict[str, Any]
    algo_version: int = ALGO_VERSION
    version: int = AUSWERTUNG_VERSION
    reihe: hz.HfReihe | None = field(default=None, repr=False, compare=False)

    def als_dict(self) -> dict[str, Any]:
        return {
            "gesamt": self.gesamt,
            "abschnitte": self.abschnitte,
            "erholungen": self.erholungen,
            "hfmax_kandidat": self.hfmax_kandidat,
            "ruhe_kandidat": self.ruhe_kandidat,
            "nacht": self.nacht,
            "talk": self.talk,
            "vorschlaege": self.vorschlaege,
            "aktivitaet": self.aktivitaet,
            "profil_stand": self.profil_stand,
            "algo_version": self.algo_version,
            "version": self.version,
        }

    @classmethod
    def aus_dict(cls, d: dict[str, Any]) -> HfAuswertung:
        return cls(
            gesamt=dict(d.get("gesamt") or {}),
            abschnitte=list(d.get("abschnitte") or []),
            erholungen=list(d.get("erholungen") or []),
            hfmax_kandidat=d.get("hfmax_kandidat"),
            ruhe_kandidat=d.get("ruhe_kandidat"),
            nacht=d.get("nacht"),
            talk=d.get("talk"),
            vorschlaege=list(d.get("vorschlaege") or []),
            aktivitaet=d.get("aktivitaet"),
            profil_stand=dict(d.get("profil_stand") or {}),
            algo_version=int(d.get("algo_version") or 0),
            version=int(d.get("version") or 0),
        )


def profil_stand(profil: HfProfil, bereiche: Sequence[hz.Bereich]) -> dict[str, Any]:
    """Womit gerechnet wurde — ändert sich das, gilt ein Cache als veraltet (Frage 4)."""
    return {
        "ruhe": profil.ruhe_bpm,
        "ruhe_quelle": profil.ruhe.quelle if profil.ruhe else None,
        "hfmax": profil.hfmax_bpm,
        "hfmax_quelle": profil.hfmax_quelle,
        "hfmax_unsicherheit": profil.hfmax_unsicherheit,
        "geschlecht": profil.geschlecht,
        "grenzen": [round(g, 3) for g in grenzen_bpm(list(bereiche))],
        "namen": [b.name for b in bereiche],
    }


def _json(x: Any) -> Any:
    """numpy → Python, NaN → None."""
    if isinstance(x, dict):
        return {str(k): _json(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_json(v) for v in x]
    if isinstance(x, np.ndarray):
        return _json(x.tolist())
    if isinstance(x, np.floating | float):
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def ist_schlafabschnitt(name: str) -> bool:
    """Gilt der Abschnittsname als bestätigte Schlafzeit?

    >>> ist_schlafabschnitt("Schlafen 23:10–06:30"), ist_schlafabschnitt("Stufe 2")
    (True, False)
    """
    return name.strip().casefold().startswith(SCHLAF_NAMEN)


def _nachtfenster(rec: Recording, reihe: hz.HfReihe) -> tuple[float, float] | None:
    """20–10 Uhr Ortszeit auf der Wanduhr der Aufnahme — das Fenster für den Schlafkandidaten
    und die Nacht-HF ohne Schlafabschnitt (das erste, das die Aufnahme überlappt)."""
    if rec.start_utc is None or reihe.n == 0:
        return None
    start = rec.start_utc.astimezone()
    tag = start.replace(hour=NACHT_VON_H, minute=0, second=0, microsecond=0)
    if start.hour < NACHT_BIS_H:
        tag -= timedelta(days=1)
    von = (tag - start).total_seconds()
    bis = von + (24 - NACHT_VON_H + NACHT_BIS_H) * 3600.0
    ende = float(reihe.t[-1] + reihe.raster_s)
    if bis <= 0 or von >= ende:
        return None
    return von, bis


def _deckung(a_von: float, a_bis: float, b_von: float, b_bis: float) -> float:
    """Anteil von a, der in b liegt."""
    schnitt = max(0.0, min(a_bis, b_bis) - max(a_von, b_von))
    return schnitt / (a_bis - a_von) if a_bis > a_von else 0.0


def auswerten(
    rec: Recording,
    *,
    profil: HfProfil,
    bereiche: Sequence[hz.Bereich],
    abschnitte: Sequence[AbschnittWand] = (),
    artefakt: Sequence[bool] | None = None,
    tagesminimum_bpm: float | None = None,
) -> HfAuswertung:
    """Alles aus einer Aufzeichnung (Modulkopf). ``artefakt`` je Zeile der Datei (aus der
    Korrektur), ``abschnitte`` auf der Wanduhr."""
    reihe = hz.reihe_aus_beats(rec.beats, artefakt=artefakt)
    grenzen = grenzen_bpm(list(bereiche))
    voll = profil.vollstaendig
    ruhe = profil.ruhe_bpm if voll else None
    hfmax = profil.hfmax_bpm if voll else None
    gesamt = hz.zusammenfassung(
        reihe,
        ruhe=ruhe,
        hfmax=hfmax,
        grenzen_bpm=grenzen if bereiche else None,
        geschlecht=profil.geschlecht,
    )
    dauer = reihe.dauer_s
    ende = float(reihe.t[-1] + reihe.raster_s) if reihe.n else 0.0

    # -- Abschnitte -----------------------------------------------------------------
    teile: list[dict[str, Any]] = []
    for a in abschnitte:
        von, bis = max(0.0, a.rechen_von), min(ende, a.rechen_bis)
        if bis <= von:
            continue
        werte = hz.zusammenfassung(
            reihe,
            von,
            bis,
            ruhe=ruhe,
            hfmax=hfmax,
            grenzen_bpm=grenzen if bereiche else None,
            geschlecht=profil.geschlecht,
        )
        eintrag: dict[str, Any] = {
            "id": a.id,
            "name": a.name,
            "von_s": a.von_s,
            "bis_s": a.bis_s,
            "rechen_von_s": von,
            "rechen_bis_s": bis,
            "werte": werte,
            "drift": None,
            "erholung": None,
        }
        if bis - von >= DRIFT_AB_S:
            d = hz.drift(reihe, von, bis)
            eintrag["drift"] = {
                "erste": d.erste_haelfte,
                "zweite": d.zweite_haelfte,
                "differenz_bpm": d.differenz_bpm,
            }
        # Erholung am getippten Ende, wenn danach Daten liegen (Endteil oder Aufnahme)
        if ende - a.bis_s >= ERHOLUNG_NACHLAUF_S:
            e = hz.hrr_erholung(reihe, a.bis_s, kontext="dauer", haltung="")
            hrr60 = e.hrr.get(60)
            # nur wenn die HF danach wirklich fällt — nach einer Ruhephase beginnt keine Erholung
            if e.hf_ende is not None and hrr60 is not None and hrr60 > 0:
                eintrag["erholung"] = e.als_dict()
        teile.append(eintrag)

    # -- Erholungen aus Marken ---------------------------------------------------------
    erholungen = [
        hz.hrr_erholung(reihe, t0, kontext=k, haltung=h).als_dict()
        for t0, k, h in erholungs_marken(rec)
    ]

    # -- Kandidaten ------------------------------------------------------------------
    hfmax_k = hz.hfmax_kandidat(reihe) if reihe.n else None
    ruhe_k: dict[str, Any] | None = None
    if RUHE_MIN_S <= dauer <= RUHE_MAX_S:
        r = hz.ruhe_hf_morgen(reihe)
        ruhe_k = r.als_dict()
        ruhe_k["quelle"] = "messung_morgen_10" if dauer >= RUHE_INTERLIVE_S else "messung_morgen_5"
    nacht: dict[str, Any] | None = None
    schlaf = [a for a in abschnitte if ist_schlafabschnitt(a.name)]
    nachtfenster = _nachtfenster(rec, reihe)
    if schlaf:
        s = max(schlaf, key=lambda a: a.bis_s - a.von_s)
        n = hz.nacht_hf(reihe, s.von_s, s.bis_s)
        nacht = n.als_dict()
        nacht["grundlage"] = NACHT_ABSCHNITT
        nacht["abschnitt_id"] = s.id
        nacht["von_s"], nacht["bis_s"] = s.von_s, s.bis_s
    elif nachtfenster is not None and reihe.abgedeckt_s(*nachtfenster) >= HF_NACHT_MIN_S:
        # Eine Nachtaufnahme ohne eingetragenen Schlafabschnitt: das tiefste 2-h-Mittel im
        # Nachtfenster. Die Bestätigung der Schlafzeit (INTERLIVE) ist das Übernehmen selbst.
        n = hz.nacht_hf(reihe, *nachtfenster)
        nacht = n.als_dict()
        nacht["grundlage"] = NACHT_FENSTER
        nacht["abschnitt_id"] = None
        nacht["von_s"], nacht["bis_s"] = nachtfenster

    talk: dict[str, Any] | None = None
    marken_talk = talk_marken(rec)
    if marken_talk:
        t = marken_talk[0]
        m = reihe.maske(t - TALK_FENSTER_S, t) & reihe.gueltig()
        if m.any():
            wert = float(reihe.hf[m].mean())
            talk = {
                "t_wall_s": t,
                "wert": wert,
                "prozent": profil.prozent(wert) if voll else None,
                "n_marken": len(marken_talk),
            }

    # -- Vorschläge aus der HF ---------------------------------------------------------
    vorschlaege: list[dict[str, Any]] = []
    if reihe.n:
        tagmin = tagesminimum_bpm
        if tagmin is None and gesamt.get("minimum_bpm") is not None and dauer >= 3600:
            tm = hz.tagesminimum(reihe, mindest_s=0.0)
            tagmin = tm.wert
        schwelle = hz.schwelle_belastung(ruhe, hfmax, tagmin)
        phasen: list[hz.Phase] = []
        if schwelle is not None:
            phasen.extend(hz.bouts(reihe, schwelle))
        if tagmin is not None:
            ruhephasen = hz.ruhephasen(reihe, tagmin + 10.0)
            phasen.extend(ruhephasen)
            if nachtfenster is not None and not schlaf:
                kandidat = hz.schlaf_kandidat(ruhephasen, *nachtfenster)
                if kandidat is not None:
                    phasen.append(kandidat)
        for p in phasen:
            if any(
                _deckung(p.von_s, p.bis_s, a.von_s, a.bis_s) > VORSCHLAG_DECKUNG_MAX
                for a in abschnitte
            ):
                continue
            vorschlaege.append(
                {"art": p.art, "von_s": p.von_s, "bis_s": p.bis_s, "mittel_bpm": p.mittel_bpm}
            )

    aktivitaet = None
    if voll and reihe.n:
        ak = hz.aktivitaetsprofil(reihe, float(ruhe), float(hfmax))  # type: ignore[arg-type]
        aktivitaet = {
            "sekunden_je_cluster": list(ak.sekunden_je_cluster),
            "gueltig_s": ak.gueltig_s,
            "gueltig": ak.gueltig,
        }

    return HfAuswertung(
        gesamt=_json(gesamt),
        abschnitte=_json(teile),
        erholungen=_json(erholungen),
        hfmax_kandidat=_json(hfmax_k.als_dict()) if hfmax_k is not None else None,
        ruhe_kandidat=_json(ruhe_k),
        nacht=_json(nacht),
        talk=_json(talk),
        vorschlaege=_json(vorschlaege),
        aktivitaet=_json(aktivitaet),
        profil_stand=_json(profil_stand(profil, bereiche)),
        reihe=reihe,
    )


def uhrzeit(rec: Recording, t_wall_s: float) -> str:
    """Ortszeit „HH:MM“ einer Wanduhrsekunde der Aufnahme (ohne Start: Dauer „M:SS“)."""
    if rec.start_utc is None:
        m, s = divmod(int(t_wall_s), 60)
        return f"{m}:{s:02d}"
    return (
        (rec.start_utc.replace(tzinfo=rec.start_utc.tzinfo or UTC) + timedelta(seconds=t_wall_s))
        .astimezone()
        .strftime("%H:%M")
    )


def phase_name(art: str, rec: Recording, von_s: float, bis_s: float) -> str:
    """Name eines übernommenen Vorschlags: „Belastung 14:02–14:41“."""
    titel = {hz.ART_BELASTUNG: "Belastung", hz.ART_RUHE: "Ruhe", hz.ART_SCHLAF: "Schlaf"}.get(
        art, art
    )
    return f"{titel} {uhrzeit(rec, von_s)}–{uhrzeit(rec, bis_s)}"


__all__ = [
    "AUSWERTUNG_VERSION",
    "AbschnittWand",
    "HfAuswertung",
    "achse_zu_wand",
    "auswerten",
    "erholungs_marken",
    "ist_schlafabschnitt",
    "phase_name",
    "profil_stand",
    "talk_marken",
    "uhrzeit",
    "wand_zu_achse",
]
