"""Das Ausdauertraining in der Oberfläche — was ``devices`` nicht darf (ohne flet).

Den Ablauf führt die Einheit: `devices.strecke_baustein.StreckeBaustein` zählt
Ortungen und Kilometer, `ui.einheit` stellt bereit, startet und beendet. Hier steht,
was die Architekturregel ``devices`` verbietet (Datenbank, Dateiablage):

- `Streckendatei` — die Datei unter ``Strecken/`` (`data.strecken.StreckenSchreiber`),
  Kopf ohne Ort, damit ein abgebrochenes Training nachgetragen werden kann.
- `einheit_eintragen` — nach dem Ende Strecke und Tagebucheintrag, mit der Einheit
  verknüpft (Migration 019): So findet die Auswertung auch eine HRV-Aufnahme, die
  schon vorher lief und weiterläuft.
- `verwaiste_uebernehmen` — eine liegengebliebene Streckendatei nachtragen, samt
  ihrer Einheit (H16): Messung und Strecke finden einander wieder.
- `hrv_bezug` — die HRV-Aufnahme eines Trainings für die Auswertung: direkt verknüpft
  oder über die Einheit, und wie ihre Zeit zu den Ortungen steht (Versätze statt
  Startzeiten).

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md` §0): Tagebuch, Zeitleiste und
Benachrichtigung bleiben ortsfrei; die Ortungen gehen nur in die Datei.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hrv_core.ereignisse import metadaten_schreiben
from hrv_core.korrektur import Korrigiert, korrektur_laden
from hrv_core.recording import Recording, laden
from hrv_core.regeln import Korrekturregeln

from trainingsapp.config import (
    app_version,
    datenverzeichnis,
    messungenverzeichnis,
    streckenverzeichnis,
)
from trainingsapp.core import abschnitte as eigene_abschnitte
from trainingsapp.core.bewegung import HOEHE_BEZUG, Messungsbezug, zip_pfad
from trainingsapp.core.bewegung import kopf as bewegung_kopf
from trainingsapp.core.bewegung import versatz as bewegung_versatz
from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.forschung import dokument, forschung_zip, tempo_reihe
from trainingsapp.core.hrv_export import zugehoerige_dateien
from trainingsapp.core.hrv_training import hf_je_zeit
from trainingsapp.core.laufend import uhr
from trainingsapp.core.models import Exercise, HrvRecording, Strecke, lokaler_tag
from trainingsapp.core.nachlauf import (
    MINDESTDAUER_S,
    Nachlauf,
    ereignisse_kuerzen,
    ist_einheit_ende,
    nachlauf,
    notiz_verschieben,
    punkte_bis,
    sidecar_kuerzen,
)
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
from trainingsapp.core.strecke import (
    GEHEN,
    SPORT_NAMEN,
    SPORTARTEN,
    Punkt,
    StreckenRechner,
    rechnen,
)
from trainingsapp.data.seed import seed_id
from trainingsapp.data.strecken import (
    StreckenSchreiber,
    dateiname,
    gpx,
    jsonl_lesen,
    kopf_lesen,
    spur_ohne_ort,
)
from trainingsapp.devices.strecke_baustein import StreckeErgebnis


class Streckendatei:
    """Die Ablage eines Trainings (`devices.strecke_baustein.Streckenablage`).

    Die Datei entsteht beim Start mit einem Kopf ohne Koordinaten (Sportart, Profil,
    Beginn) und heißt nach ihrem Beginn — wie bisher ``strecke_<Zeit>.jsonl``.
    """

    def __init__(self, sportart: str, subject_id: str, verzeichnis: Path | None = None) -> None:
        self.sportart = sportart
        self.subject_id = subject_id
        self.verzeichnis = verzeichnis
        self.pfad: Path | None = None
        self._schreiber: StreckenSchreiber | None = None

    def anlegen(self, start_utc: datetime) -> str:
        verzeichnis = self.verzeichnis or streckenverzeichnis()
        self.pfad = verzeichnis / dateiname(start_utc)
        self._schreiber = StreckenSchreiber(
            self.pfad,
            kopf={
                "schema": "strecke-v1",
                "sportart": self.sportart,
                "subject_id": self.subject_id,
                "started_at": start_utc.isoformat(),
                # was der Empfänger liefert (`flet_gps`: über dem Meeresspiegel, seit 26.10.2026)
                "hoehe_bezug": HOEHE_BEZUG,
            },
        )
        return self.pfad.relative_to(verzeichnis).as_posix()

    def schreiben(self, punkt: Punkt) -> None:
        if self._schreiber is not None:
            self._schreiber.schreiben(punkt)

    def schliessen(self, behalten: bool) -> None:
        if self._schreiber is not None:
            self._schreiber.schliessen()
            self._schreiber = None
        if not behalten and self.pfad is not None:
            self.pfad.unlink(missing_ok=True)


def lauftext(e: Any, teil: Any) -> str:
    """Strecke, Zeit, Herzfrequenz des laufenden Trainings — ortsfrei (Benachrichtigung,
    Karte im Reiter „Messung“).

    >>> from types import SimpleNamespace as N
    >>> e = N(dauer_s=lambda: 1930.0, hrv=None)
    >>> lauftext(e, N(quelle=object(), rechner=N(distanz_m=5212.4)))
    '5,21 km · 32:10'
    >>> lauftext(e, N(quelle=None))
    '32:10'
    """
    teile = [uhr(max(e.dauer_s(), 0.0))]
    if getattr(teil, "quelle", None) is not None:
        teile.insert(0, f"{teil.rechner.distanz_m / 1000:.2f} km".replace(".", ","))
    hrv = e.hrv
    if hrv is not None:
        with contextlib.suppress(Exception):
            if hf := hrv.messlauf.live.kennzahlen().hf_bpm:
                teile.append(f"HF {hf}")
    return " · ".join(teile)


# ---------------------------------------------------------------------------
# Tagebuch und Strecke
# ---------------------------------------------------------------------------


def uebung_fuer(state: Any, sportart: str) -> Exercise:
    """Die Übung „Gehen"/„Laufen"/„Radfahren" — beim ersten Training angelegt.

    Feste ID je Sportart (wie mitgelieferte Übungen), damit alle Trainings
    einer Sportart im Verlauf zusammenstehen. Felder: Strecke und Zeit.
    """
    uid = seed_id(f"ausdauer_{sportart}")
    vorhanden = state.uebungen.laden(uid, mit_geloeschten=True)
    if vorhanden is not None:
        return vorhanden
    felder = [f for f in (vorrat_feld("distance"), vorrat_feld("duration")) if f is not None]
    uebung = Exercise(
        id=uid,
        name=SPORT_NAMEN[sportart],
        description="Ausdauer — mit GPS oder ohne aufgezeichnet (Reiter „Messung“, „Ausdauer“).",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=felder),
        typen=["Ausdauer"],
    )
    state.uebungen.speichern(uebung)
    return uebung


def training_eintragen(
    state: Any,
    *,
    subject_id: str,
    sportart: str,
    started_at: datetime,
    ended_at: datetime,
    file_path: str,
    rechner: StreckenRechner | None,
    dauer_s: float,
    hrv_recording_id: str | None = None,
    title: str = "",
    einheit_id: str | None = None,
) -> Strecke:
    """Strecke und Tagebucheintrag anlegen — nach dem Training und beim Nachtragen.

    ``rechner`` ``None`` heißt ohne GPS (Laufband): Strecke 0, Bewegungszeit = Dauer.
    """
    r = rechner
    strecke = Strecke(
        subject_id=subject_id,
        sportart=sportart,
        started_at=started_at,
        ended_at=ended_at,
        file_path=file_path if r is not None else "",
        distanz_m=r.distanz_m if r is not None else 0.0,
        dauer_s=dauer_s,
        bewegt_s=r.bewegt_s if r is not None else dauer_s,
        hoehe_auf_m=r.hoehe_auf_m if r is not None else 0.0,
        hoehe_ab_m=r.hoehe_ab_m if r is not None else 0.0,
        hrv_recording_id=hrv_recording_id,
        title=title,
        einheit_id=einheit_id,
    )
    ergebnis_feld: dict[str, Any] = {"duration": round(dauer_s)}
    if strecke.distanz_m >= 10:
        ergebnis_feld["distance"] = round(strecke.distanz_m)
    uebung = uebung_fuer(state, sportart)
    sitzung = state.sitzungen.session_fuer(subject_id, None, lokaler_tag(started_at))
    eintrag = state.sitzungen.eintrag_anlegen(
        sitzung, uebung, ergebnis_feld, started_at=started_at, ended_at=ended_at
    )
    strecke.session_entry_id = eintrag.id
    state.strecken.anlegen(strecke)
    return strecke


def sportart_aendern(state: Any, strecke: Strecke, sportart: str) -> Strecke:
    """Die Sportart eines gespeicherten Trainings ändern (Ben, 26.10.2026: „Laufen“
    gestartet, Rad gefahren). Die Zeile bekommt die neue Sportart, der Tagebucheintrag
    wandert als Korrektur zur Übung der neuen Sportart (`eintrag_uebung_wechseln`); die
    Auswertung rechnet Kilometer, Tempo und Kurve ohnehin aus der Datei mit der Sportart
    der Zeile. Der Dateikopf behält die Sportart vom Start (`Streckendatei`)."""
    if sportart not in SPORTARTEN or sportart == strecke.sportart:
        return strecke
    eintrag_id = strecke.session_entry_id
    if eintrag_id and state.sitzungen.eintrag_laden(eintrag_id) is not None:
        eintrag_id = state.sitzungen.eintrag_uebung_wechseln(
            eintrag_id, uebung_fuer(state, sportart)
        ).id
    state.strecken.sportart_setzen(strecke.id, sportart, eintrag_id)
    strecke.sportart = sportart
    strecke.session_entry_id = eintrag_id
    return strecke


def einheit_eintragen(
    state: Any, e: Any, ergebnis: StreckeErgebnis, hrv_recording_id: str | None = None
) -> Strecke:
    """Das Training einer beendeten Einheit eintragen: Strecke, Tagebuch, Verknüpfung.

    Anfang und Ende kommen aus der Zeitleiste (`Einheitslauf.zeitbasis`, Ereignis
    ``einheit/ende``) — mit GPS nie kürzer als die Zeit zwischen erster und letzter
    Ortung. Die HRV-Aufnahme verknüpft ``hrv_recording_id``, wenn sie mit der Einheit
    endete; lief sie weiter, findet die Auswertung sie über ``einheit_id``.
    """
    r = ergebnis.rechner
    mit_gps = bool(ergebnis.datei) and bool(r.teilstuecke)
    ende_s = next(
        (x.t_s for x in reversed(e.ereignisse) if x.quelle == "einheit" and x.art == "ende"),
        max(e.dauer_s(), 0.0),
    )
    if e.zeitbasis is not None:
        started_at = e.zeitbasis.utc(0.0)
    else:
        started_at = ergebnis.start_utc or datetime.now(UTC) - timedelta(seconds=ende_s)
    dauer = max(ende_s, r.dauer_s) if mit_gps else ende_s
    return training_eintragen(
        state,
        subject_id=e.subject_id or state.profil.id,
        sportart=ergebnis.sportart,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=ende_s),
        file_path=ergebnis.datei if mit_gps else "",
        rechner=r if mit_gps else None,
        dauer_s=dauer,
        hrv_recording_id=hrv_recording_id,
        einheit_id=e.id,
    )


# ---------------------------------------------------------------------------
# Ende kürzen — GPS lief weiter, als das Training schon vorbei war (Ben, 28.10.2026)
# ---------------------------------------------------------------------------


def strecken_punkte(strecke: Strecke) -> list[Punkt]:
    """Die Ortungen eines Trainings aus seiner Datei — leer ohne GPS oder ohne Datei."""
    if not strecke.file_path:
        return []
    pfad = streckenverzeichnis() / strecke.file_path
    return jsonl_lesen(pfad) if pfad.exists() else []


def nachlauf_der_strecke(strecke: Strecke, *, mindestens_s: float | None = None) -> Nachlauf | None:
    """Der Stillstand am Ende eines gespeicherten Trainings (`core.nachlauf.nachlauf`) —
    ``mindestens_s`` ``None``: die Vorgabe (fragen beim Speichern), ``0``: immer, sobald es
    je Bewegung gab (der Knopf „Ende kürzen“ in der Auswertung)."""
    punkte = strecken_punkte(strecke)
    if mindestens_s is None:
        return nachlauf(punkte, strecke.sportart)
    return nachlauf(punkte, strecke.sportart, mindestens_s=mindestens_s)


@dataclass(frozen=True, slots=True)
class Gekuerzt:
    """Was `training_kuerzen` getan hat — für die Meldung."""

    strecke: Strecke
    #: so viele Sekunden Ortungen sind weg
    entfernt_s: float
    #: was mit der HRV-Messung geschah (leer: keine)
    hrv: str = ""


def training_kuerzen(state: Any, strecke: Strecke, bis_s: float, *, lauf: Any = None) -> Gekuerzt:
    """Das Training bei ``bis_s`` Sekunden nach der ersten Ortung enden lassen.

    Ben: „nach hinten raus einen Crop setzen, um die Teile, wo es keine Änderung mehr gab,
    aus der Aufzeichnung rauszunehmen. Wichtig dabei ist vor allem das korrekte Setzen der
    Notizen in der HRV-Messung.“ Der Reihe nach:

    1. **Streckendatei**: nur noch die Ortungen bis zum neuen Ende (atomar neu geschrieben,
       Kopf bleibt) — die entfernten Ortungen sind weg (GPS-Daten, nie geteilt, kein Backup).
    2. **Zeile** ``strecke``: Ende, Dauer, Bewegungszeit, Strecke und Höhe neu aus den
       verbliebenen Ortungen (`core.strecke.rechnen`).
    3. **Tagebucheintrag**: eine Korrektur (`eintrag_korrigieren`, der alte bleibt in der
       Kette) mit neuer Dauer und Strecke, Ende wie die Zeile.
    4. **HRV-Messung** (`core.nachlauf`): „‹Einheit›: Ende“ rückt auf das neue Ende, km-Notizen
       danach fallen weg, eigene Notizen bleiben; die Abschnitte im Sidecar enden dort; endete
       die Messung mit dem Training, wird die Auswertung dort zugeschnitten (Sidecar-Crop,
       mit „Ganze Messung“ aufzuheben). Läuft sie noch (``lauf``), rückt die Notiz in der
       laufenden Aufnahme — Sidecar und Datei folgen beim Speichern.

    Die Zeitleiste der Einheit bleibt, wie sie war: Sie dokumentiert, was geschah.

    Raises:
        ValueError: ohne Datei, zu kurz, oder es gäbe nichts zu kürzen.
    """
    if not strecke.file_path:
        raise ValueError("Dieses Training hat keine Ortungen.")
    pfad = streckenverzeichnis() / strecke.file_path
    punkte = jsonl_lesen(pfad) if pfad.exists() else []
    if not punkte:
        raise ValueError("Die Streckendatei ist leer.")
    if bis_s < MINDESTDAUER_S:
        raise ValueError(f"Kürzer als {uhr(MINDESTDAUER_S)} geht nicht.")
    bis_t = punkte[0].t + bis_s
    neu = punkte_bis(punkte, bis_t)
    if len(neu) < 2:
        raise ValueError("So bliebe keine Strecke übrig.")
    if neu[-1].t >= punkte[-1].t:
        raise ValueError("Das Ende liegt schon dort — nichts zu kürzen.")
    entfernt = punkte[-1].t - neu[-1].t
    # 1. Datei
    kopf = kopf_lesen(pfad)
    tmp = pfad.with_name(pfad.name + ".neu")
    with StreckenSchreiber(tmp, kopf=kopf) as schreiber:
        for p in neu:
            schreiber.schreiben(p)
    os.replace(tmp, pfad)
    # 2. Zeile
    r = rechnen(neu, strecke.sportart)
    ende_alt = strecke.ended_at or strecke.started_at + timedelta(seconds=strecke.dauer_s)
    strecke.ended_at = ende_alt - timedelta(seconds=entfernt)
    strecke.dauer_s = max(strecke.dauer_s - entfernt, r.dauer_s, 0.0)
    strecke.bewegt_s = min(r.bewegt_s, strecke.dauer_s)
    strecke.distanz_m = r.distanz_m
    strecke.hoehe_auf_m, strecke.hoehe_ab_m = r.hoehe_auf_m, r.hoehe_ab_m
    # 3. Tagebuch
    if strecke.session_entry_id and (
        alt := state.sitzungen.eintrag_laden(strecke.session_entry_id)
    ):
        ergebnis = {k: v for k, v in alt.result.items() if k != "distance"}
        ergebnis["duration"] = round(strecke.dauer_s)
        if strecke.distanz_m >= 10:
            ergebnis["distance"] = round(strecke.distanz_m)
        korrektur = state.sitzungen.eintrag_korrigieren(alt.id, ergebnis, ended_at=strecke.ended_at)
        strecke.session_entry_id = korrektur.id
    state.strecken.kuerzen(strecke)
    # 4. HRV
    hrv = _hrv_kuerzen(state, strecke, bis_t, lauf)
    return Gekuerzt(strecke, entfernt, hrv)


def _hrv_kuerzen(state: Any, strecke: Strecke, bis_t: float, lauf: Any) -> str:
    """Notizen und Abschnitte der HRV-Messung auf das neue Ende — siehe `training_kuerzen`."""
    bezug = hrv_bezug(state, strecke)
    if bezug is None:
        return ""
    wand = bezug.ortung_zu_wand(bis_t, strecke.started_at)
    if wand is None:
        return ""
    einheit_id = strecke.einheit_id
    aufnahme = getattr(lauf, "aufnahme", None) if lauf is not None else None
    if aufnahme is not None and bezug.aufnahme is None:
        # Die Messung läuft noch: Die Notiz rückt in der Aufnahme — dieselbe Notiz hält
        # `Messlauf._grenzen`, das Sidecar beim Speichern folgt ihr von selbst
        getroffen = 0
        for e in aufnahme.ereignisse:
            if ist_einheit_ende(e, einheit_id):
                e.update(notiz_verschieben(e, wand, aufnahme.beats, aufnahme.start_utc))
                getroffen += 1
        return "Notiz „Ende“ in der laufenden Messung verschoben" if getroffen else ""
    if not bezug.pfad.exists():
        return ""
    rec = laden(bezug.pfad)
    neu = ereignisse_kuerzen(
        rec.ereignisse,
        bis_wand=wand,
        beats=rec.beats,
        start_utc=rec.start_utc,
        einheit_id=einheit_id,
    )
    sha1 = metadaten_schreiben(bezug.pfad, ereignisse=neu)
    if bezug.aufnahme is not None:
        state.hrv.sha1_setzen(bezug.aufnahme.id, sha1)
    eigene = {k for e in neu if (k := eigene_abschnitte.kennung_von(e)) is not None}
    mit_training = strecke.hrv_recording_id is not None
    zugeschnitten = sidecar_kuerzen(
        bezug.pfad, rec, wand, zuschneiden=mit_training, eigener=lambda k: k in eigene
    )
    if zugeschnitten and mit_training:
        return "HRV-Notizen verschoben, Auswertung dort zugeschnitten"
    return "HRV-Notizen verschoben"


# ---------------------------------------------------------------------------
# Verwaiste Streckendateien — Training, das Android mitten im Lauf beendet hat
# ---------------------------------------------------------------------------


def verwaiste_uebernehmen(state: Any, pfad: Path) -> Strecke | None:
    """Eine Streckendatei ohne Zeile als Training nachtragen (Ben, 15.10.2026: beim
    Start erkennen und anbieten). Sportart, Profil und Start kommen aus dem Kopf der
    Datei; ohne Kopf gilt „Gehen", das aktive Profil und die erste Ortung. Eine Datei
    ohne Ortung wird gelöscht, nicht eingetragen (``None``).

    Lief das Training als Einheit, nennt deren Zeitleiste die Datei — das Training
    bekommt die Einheit, und über sie findet die Auswertung die HRV-Aufnahme, die nach
    dem Absturz aus ihrem Backup zurückkam (H16).
    """
    punkte = jsonl_lesen(pfad)
    if not punkte:
        with contextlib.suppress(OSError):
            pfad.unlink()
        state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]
        return None
    kopf = kopf_lesen(pfad) or {}
    sportart = str(kopf.get("sportart") or "")
    if sportart not in SPORTARTEN:
        sportart = GEHEN
    subject_id = str(kopf.get("subject_id") or "")
    if not subject_id or state.profile.laden(subject_id) is None:
        subject_id = state.profil.id
    try:
        started_at = datetime.fromisoformat(str(kopf["started_at"]))
    except (KeyError, ValueError):
        started_at = datetime.fromtimestamp(punkte[0].t, UTC)
    ended_at = datetime.fromtimestamp(punkte[-1].t, UTC)
    datei = pfad.relative_to(streckenverzeichnis()).as_posix()
    einheit_id = None
    if state.einheiten is not None:
        with contextlib.suppress(Exception):
            einheit_id = next((eid for eid, _ in state.einheiten.zur_datei("gps", datei)), None)
    r = rechnen(punkte, sportart)
    strecke = training_eintragen(
        state,
        subject_id=subject_id,
        sportart=sportart,
        started_at=started_at,
        ended_at=ended_at,
        file_path=datei,
        rechner=r,
        dauer_s=max(r.dauer_s, (ended_at - started_at).total_seconds()),
        title="Nachgetragen — die App wurde während des Trainings beendet",
        einheit_id=einheit_id,
    )
    state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]
    return strecke


# ---------------------------------------------------------------------------
# HRV eines Trainings — für die Auswertung
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HrvBezug:
    """Die HRV-Aufnahme eines Trainings und wie ihre Zeit zu den Ortungen steht."""

    #: die Messdatei unter ``Messungen/`` — fehlt sie, läuft die Aufnahme noch
    pfad: Path
    #: die Zeile ``hrv_recording`` — erst, wenn die Aufnahme gespeichert ist
    aufnahme: HrvRecording | None = None
    #: Ortungszeit (``Punkt.t``) − Verschiebung = ``t_wall_s`` der Messdatei; ``None``:
    #: über die Startzeiten (Trainings ohne Einheit, Versatz unbekannt)
    verschiebung_s: float | None = None
    #: ``t_wall_s`` der Messdatei beim Start des Trainings — ``None`` wie oben
    beginn_s: float | None = None

    def ortung_zu_wand(self, t: float, start_utc: datetime | None) -> float | None:
        """Eine Ortungszeit als ``t_wall_s`` der Messdatei — über den Versatz der Einheit,
        sonst über den Start der Aufnahme (ganze Sekunden).

        >>> b = HrvBezug(Path("x.json"), verschiebung_s=1_000_000.0 - 734.0)
        >>> b.ortung_zu_wand(1_000_010.0, None)
        744.0
        """
        if self.verschiebung_s is not None:
            return t - self.verschiebung_s
        if start_utc is not None:
            return t - start_utc.timestamp()
        return None

    def wand_zu_ortung(self, w: float, start_utc: datetime | None) -> float | None:
        """Die Umkehrung: ``t_wall_s`` der Messdatei → Ortungszeit (UTC-Sekunden).

        >>> b = HrvBezug(Path("x.json"), verschiebung_s=1_000_000.0 - 734.0)
        >>> b.wand_zu_ortung(744.0, None)
        1000010.0
        """
        if self.verschiebung_s is not None:
            return w + self.verschiebung_s
        if start_utc is not None:
            return w + start_utc.timestamp()
        return None


def hrv_bezug(state: Any, strecke: Strecke) -> HrvBezug | None:
    """Wo die HRV-Aufnahme eines Trainings liegt — ``None`` ohne HRV.

    Direkt verknüpft (``hrv_recording_id``: die Aufnahme endete mit dem Training) oder
    über die Einheit (Migration 019: Sie lief schon vorher oder läuft weiter; nach einem
    Absturz kam sie aus dem Backup). Kennt die Einheit beide Versätze, legt sie
    Ortungen und Herzschläge aufeinander (Vertrag ``docs/plan_einheit.md`` §3).
    """
    teile: list[Any] = []
    if strecke.einheit_id and getattr(state, "einheiten", None) is not None:
        with contextlib.suppress(Exception):
            teile = state.einheiten.beteiligungen(strecke.einheit_id)
    hrv = next((b for b in teile if b.art == "hrv" and b.datei), None)
    gps = next((b for b in teile if b.art == "gps"), None)
    aufnahme = state.hrv.laden(strecke.hrv_recording_id) if strecke.hrv_recording_id else None
    if aufnahme is None and hrv is not None:
        aufnahme = state.hrv.zur_datei(hrv.datei)
    datei = aufnahme.file_path if aufnahme is not None else hrv.datei if hrv is not None else ""
    if not datei:
        return None
    verschiebung = beginn = None
    if hrv is not None and hrv.datei == datei and hrv.versatz_s is not None:
        beginn = -hrv.versatz_s
        if gps is not None and gps.versatz_s is not None:
            verschiebung = hrv.versatz_s - gps.versatz_s
    return HrvBezug(messungenverzeichnis() / datei, aufnahme, verschiebung, beginn)


def zeitleiste_und_versatz(state: Any, strecke: Strecke) -> tuple[list[Ereignis], float | None]:
    """Die Zeitleiste der Einheit eines Trainings und der Versatz seiner Ortungen
    (Ortungszeit + Versatz = ``t_s``) — für die Tabelle „Intervalle“ der Auswertung. Ohne
    Einheit (ältere Trainings) leer und ``None``."""
    einheiten = getattr(state, "einheiten", None)
    if not strecke.einheit_id or einheiten is None:
        return [], None
    try:
        ereignisse = einheiten.ereignisse(strecke.einheit_id)
        teile = einheiten.beteiligungen(strecke.einheit_id)
    except Exception:  # eine kaputte Zeile kostet die Tabelle, nicht die Auswertung
        return [], None
    gps = next((b for b in teile if b.art == "gps"), None)
    return ereignisse, gps.versatz_s if gps is not None else None


def forschung_export(state: Any, einheit_id: str) -> tuple[str, bytes]:
    """Der Forschungsexport einer Einheit (``docs/plan_einheit.md`` §8) — Dateiname und
    ZIP: die Messdateien samt Beiwerk byte-genau, ``einheit-v1.json`` mit Zeitleiste,
    Versätzen und dem Tempo aus der Strecke. **Ohne Ort** (`core.forschung`).

    Raises:
        ValueError: Die Einheit gibt es nicht (mehr).
    """
    name, dok, dateien, basis, auftraege = _forschung_teile(state, einheit_id)
    return name, forschung_zip(dok, dateien, basis, zusatz=bewegung_packen(auftraege))


async def forschung_export_async(state: Any, einheit_id: str) -> tuple[str, bytes]:
    """Wie `forschung_export`, aber das Packen (Messdateien lesen, deflate — bei einer
    4-h-Aufnahme Sekunden) läuft in einem Thread; die Datenbank wird davor im Loop gelesen
    (sqlite-Verbindungen gehören ihrem Thread; H39)."""
    name, dok, dateien, basis, auftraege = _forschung_teile(state, einheit_id)

    def packen() -> bytes:
        return forschung_zip(dok, dateien, basis, zusatz=bewegung_packen(auftraege))

    return name, await asyncio.to_thread(packen)


def _forschung_teile(
    state: Any, einheit_id: str
) -> tuple[str, Any, list[Path], Path, list[Bewegungsauftrag]]:
    """Dateiname, Dokument, Messdateien, Basis und die Rohspur-Aufträge des
    Forschungsexports — aus der Datenbank (im Loop, H39); gelesen wird beim Packen."""
    kopf = state.einheiten.laden(einheit_id) if state.einheiten is not None else None
    if kopf is None:
        raise ValueError("Diese Einheit gibt es nicht mehr.")
    teile = state.einheiten.beteiligungen(einheit_id)
    basis = datenverzeichnis()
    dateien: list[Path] = []
    archiv: dict[str, str] = {}
    for b in teile:
        if b.art != "hrv" or not b.datei or b.datei in archiv:
            continue
        pfad = messungenverzeichnis() / b.datei
        archiv[b.datei] = ""
        if pfad.exists():  # sonst läuft die Messung noch — der Teil steht ohne Datei da
            dateien += zugehoerige_dateien(pfad)
            archiv[b.datei] = archivpfad(pfad, basis)
    tempo: list[tuple[float, float | None]] = []
    auftraege: list[Bewegungsauftrag] = []
    gps = next((b for b in teile if b.art == "gps" and b.datei), None)
    if gps is not None and gps.versatz_s is not None:
        strecke = streckenverzeichnis() / gps.datei
        if strecke.exists():
            tempo = tempo_reihe(jsonl_lesen(strecke), gps.versatz_s)
    if gps is not None and gps.datei:
        # Die Rohspur ohne Ort (Ben, 26.10.2026: „das ist der wichtige Teil“) — der Teil
        # nennt sie über ``archiv``; Lesen und Schreiben erst beim Packen
        training = state.strecken.zur_einheit(einheit_id)
        aufnahmen = [
            r
            for b in teile
            if b.art == "hrv" and b.datei and (r := state.hrv.zur_datei(b.datei)) is not None
        ]
        auftrag = bewegung_auftrag(state, training, aufnahmen) if training is not None else None
        if auftrag is not None:
            archiv[gps.datei] = auftrag.zip_pfad
            auftraege.append(auftrag)
    dok = dokument(
        einheit_id=kopf.id,
        titel=kopf.titel,
        start_utc=kopf.started_at,
        ende_utc=kopf.ended_at,
        teile=teile,
        ereignisse=state.einheiten.ereignisse(einheit_id),
        tempo=tempo,
        archiv=archiv,
        app=app_text(),
    )
    lokal = kopf.started_at.astimezone()
    return f"einheit_{lokal:%Y-%m-%d_%H%M}.zip", dok, dateien, basis, auftraege


def app_text() -> str:
    """„trainingsapp 0.3.18 (Build 280)“ — für Kopfzeilen von Exporten."""
    version, build = app_version()
    return f"trainingsapp {version}" + (f" (Build {build})" if build else "")


def archivpfad(pfad: Path, basis: Path | None = None) -> str:
    """Pfad einer Datei im Export-ZIP: relativ zum Datenverzeichnis (``Messungen/<Gerät>/…``),
    außerhalb nur ihr Name — wie `core.hrv_export.export_zip` sie legt."""
    basis = basis if basis is not None else datenverzeichnis()
    try:
        return pfad.resolve().relative_to(basis.resolve()).as_posix()
    except ValueError:
        return pfad.name


# ---------------------------------------------------------------------------
# Bewegungsdaten im Export — die Rohspur ohne Ort (`core.bewegung`, Ben 26.10.2026)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bewegungsauftrag:
    """Eine Rohspur, die ins ZIP soll: wohin, woraus, mit welchem Kopf — fertig aus der
    Datenbank, damit das Lesen der Datei in einem Thread laufen kann (H39)."""

    zip_pfad: str
    pfad: Path
    kopf: dict[str, Any]


def messungsbezuege(state: Any, strecke: Strecke, aufnahmen: Iterable[Any]) -> list[Messungsbezug]:
    """Je Messung des Trainings der Pfad im ZIP und der Versatz Ortungszeit → ``t_wall_s``
    — aus den Beteiligungen der Einheit, sonst über den Start der Messdatei."""
    teile: list[Any] = []
    if strecke.einheit_id and getattr(state, "einheiten", None) is not None:
        with contextlib.suppress(Exception):
            teile = state.einheiten.beteiligungen(strecke.einheit_id)
    gps = next((b for b in teile if b.art == "gps"), None)
    aus: list[Messungsbezug] = []
    for a in aufnahmen:
        hrv = next((b for b in teile if b.art == "hrv" and b.datei == a.file_path), None)
        v, quelle = bewegung_versatz(
            a.started_at,
            gps.versatz_s if gps is not None else None,
            hrv.versatz_s if hrv is not None else None,
        )
        aus.append(Messungsbezug(archivpfad(messungenverzeichnis() / a.file_path), a.id, v, quelle))
    return aus


def bewegung_auftrag(
    state: Any, strecke: Strecke, aufnahmen: Iterable[Any]
) -> Bewegungsauftrag | None:
    """Der Auftrag für ein Training — ``None`` ohne Streckendatei (Laufband, Datei weg)."""
    if not strecke.file_path:
        return None
    pfad = streckenverzeichnis() / strecke.file_path
    if not pfad.exists():
        return None
    k = bewegung_kopf(
        strecke,
        messungsbezuege(state, strecke, aufnahmen),
        app=app_text(),
        quell_kopf=kopf_lesen(pfad),
    )
    return Bewegungsauftrag(zip_pfad(strecke.file_path), pfad, k)


def bewegung_vorbereiten(state: Any, aufnahmen: Iterable[HrvRecording]) -> list[Bewegungsauftrag]:
    """Zu den exportierten Messungen die Trainings — ein Auftrag je Training, auch wenn
    zwei Messungen daran hängen (dann zwei Einträge in ``messungen``). Datenbank, im Loop."""
    je_strecke: dict[str, tuple[Strecke, list[HrvRecording]]] = {}
    for a in aufnahmen:
        s = state.strecken.zur_hrv(a.id)
        if s is not None:
            je_strecke.setdefault(s.id, (s, []))[1].append(a)
    return [
        auftrag
        for s, recs in je_strecke.values()
        if (auftrag := bewegung_auftrag(state, s, recs)) is not None
    ]


def bewegung_packen(auftraege: Iterable[Bewegungsauftrag]) -> dict[str, bytes]:
    """ZIP-Pfad → Rohspur ohne Ort — liest die Streckendateien, darum im Thread."""
    return {a.zip_pfad: spur_ohne_ort(a.pfad, a.kopf) for a in auftraege}


# ---------------------------------------------------------------------------
# GPX — mit Koordinaten, nur auf ausdrückliche Handlung (Regel 0, Eigenverantwortung)
# ---------------------------------------------------------------------------


def hrv_laden(
    bezug: HrvBezug | None, vorgabe: Korrekturregeln
) -> tuple[Recording, Korrigiert] | None:
    """Die HRV-Aufnahme eines Trainings, korrigiert wie in ihrer Auswertung (Sidecar, Regeln —
    `hrv_core.korrektur.korrektur_laden`), direkt verknüpft oder über die Einheit
    (`hrv_bezug`). ``vorgabe``: die gerätelokalen Regeln, wenn das Sidecar keine hat.
    Liest Dateien und rechnet — in einem Thread aufrufen (H39)."""
    if bezug is None or not bezug.pfad.exists():
        return None
    stand = korrektur_laden(bezug.pfad, vorgabe)
    return stand.basis.rec, stand.anwenden()


def ortung_zu_wand(bezug: HrvBezug | None, rec: Recording, t: float) -> float | None:
    """Ortungszeit → ``t_wall_s`` der Messdatei: über die Versätze der Einheit, sonst
    über den Start der Aufnahme (ältere Trainings)."""
    if bezug is not None:
        return bezug.ortung_zu_wand(t, rec.start_utc)
    return t - rec.start_utc.timestamp() if rec.start_utc else None


def herz_je_ortung(
    punkte: Iterable[Punkt], bezug: HrvBezug | None, rec: Recording
) -> dict[float, int]:
    """Ortungszeit → Herzfrequenz (Schläge/min) für den GPX-Export — nur Ortungen, zu
    denen die Messdatei einen Schlag hat."""
    wand = {p.t: w for p in punkte if (w := ortung_zu_wand(bezug, rec, p.t)) is not None}
    je_wand = hf_je_zeit(rec, list(wand.values()))
    return {t: bpm for t, w in wand.items() if (bpm := je_wand.get(w)) is not None}


@dataclass(frozen=True, slots=True)
class GpxAuftrag:
    """Eine Strecke, die als GPX ins ZIP soll — fertig aus der Datenbank (H39)."""

    zip_pfad: str
    strecke: Strecke
    pfad: Path
    bezug: HrvBezug | None
    vorgabe: Korrekturregeln


def gpx_vorbereiten(state: Any, strecken: Iterable[Strecke]) -> list[GpxAuftrag]:
    """Je Training mit Streckendatei ein Auftrag — Datenbank, im Loop."""
    vorgabe = state.korrekturregeln()
    aus: list[GpxAuftrag] = []
    for s in strecken:
        if not s.file_path:
            continue
        pfad = streckenverzeichnis() / s.file_path
        if not pfad.exists():
            continue
        lokal = s.started_at.astimezone()
        aus.append(
            GpxAuftrag(
                f"Strecken/{lokal:%Y-%m-%d_%H%M}_{s.sportart}.gpx",
                s,
                pfad,
                hrv_bezug(state, s),
                vorgabe,
            )
        )
    return aus


def gpx_packen(auftraege: Iterable[GpxAuftrag]) -> dict[str, bytes]:
    """ZIP-Pfad → GPX mit Herzfrequenz (wie „GPX exportieren“ in der Auswertung) — liest
    Strecken- und Messdateien, darum im Thread."""
    aus: dict[str, bytes] = {}
    for a in auftraege:
        punkte = jsonl_lesen(a.pfad)
        if not punkte:
            continue
        herz: dict[float, int] = {}
        hrv = hrv_laden(a.bezug, a.vorgabe)
        if hrv is not None:
            herz = herz_je_ortung(punkte, a.bezug, hrv[0])
        lokal = a.strecke.started_at.astimezone()
        aus[a.zip_pfad] = gpx(
            punkte,
            name=f"{SPORT_NAMEN[a.strecke.sportart]} {lokal:%d.%m.%Y %H:%M}",
            sportart=a.strecke.sportart,
            herzfrequenz=herz or None,
        )
    return aus


__all__ = [
    "Bewegungsauftrag",
    "Gekuerzt",
    "GpxAuftrag",
    "HrvBezug",
    "Streckendatei",
    "app_text",
    "archivpfad",
    "bewegung_auftrag",
    "bewegung_packen",
    "bewegung_vorbereiten",
    "einheit_eintragen",
    "forschung_export",
    "gpx_packen",
    "gpx_vorbereiten",
    "herz_je_ortung",
    "hrv_bezug",
    "hrv_laden",
    "lauftext",
    "messungsbezuege",
    "nachlauf_der_strecke",
    "ortung_zu_wand",
    "sportart_aendern",
    "strecken_punkte",
    "training_eintragen",
    "training_kuerzen",
    "uebung_fuer",
    "verwaiste_uebernehmen",
    "zeitleiste_und_versatz",
]
