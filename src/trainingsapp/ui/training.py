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

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md` §0): Tagebuch, Zeitleiste und
Benachrichtigung bleiben ortsfrei; die Ortungen gehen nur in die Datei.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from trainingsapp.config import streckenverzeichnis
from trainingsapp.core.laufend import uhr
from trainingsapp.core.models import Exercise, Strecke, lokaler_tag
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
from trainingsapp.data.strecken import StreckenSchreiber, dateiname, jsonl_lesen, kopf_lesen
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
        default_felder=["distance", "duration"],
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
    eintrag = state.sitzungen.eintrag_anlegen(sitzung, uebung, ergebnis_feld)
    strecke.session_entry_id = eintrag.id
    state.strecken.anlegen(strecke)
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


__all__ = [
    "Streckendatei",
    "einheit_eintragen",
    "lauftext",
    "training_eintragen",
    "uebung_fuer",
    "verwaiste_uebernehmen",
]
