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

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from trainingsapp.config import messungenverzeichnis, streckenverzeichnis
from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.laufend import uhr
from trainingsapp.core.models import Exercise, HrvRecording, Strecke, lokaler_tag
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


__all__ = [
    "HrvBezug",
    "Streckendatei",
    "einheit_eintragen",
    "hrv_bezug",
    "lauftext",
    "training_eintragen",
    "uebung_fuer",
    "verwaiste_uebernehmen",
    "zeitleiste_und_versatz",
]
