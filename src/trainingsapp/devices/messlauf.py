"""Eine laufende Messung: Quelle → Live-Fenster, während der Aufnahme auch → Aufnahme.

Der `Messlauf` lebt im `AppState`, nicht in einer Ansicht (L03): Er liest den
Datenstrom der Quelle (`HeartRateSource.stream()`) und ihren Status parallel,
füttert immer das `LiveFenster` und während einer Aufnahme zusätzlich die
`Aufnahme`, sichert alle 15 s ein Backup und meldet der Oberfläche über einen
Beobachter, dass es Neues gibt. Er rechnet nichts selbst — das tun `hrv_core`
(Aufnahme, Live-Kennzahlen) und die Quelle (Protokoll).

Bleibt ein Backup liegen (Akku leer, Absturz), macht `backup_wiederherstellen`
daraus beim nächsten Start die Messdatei, die „Stopp & speichern" geschrieben
hätte — mit Profil und Timer-Abschnitten, die das Backup dafür mitführt.

**Abschnitte je Spur** (Ben, 17.10.2026): Timer, Kilometer, Übungen und die
Einheit (`devices.einheit`) haben jede ihre Spur — eine km-Grenze schneidet
keinen Timer-Abschnitt (`hrv_core.ausschnitte.spuren_speichern`). Automatische
Notizen tragen eine `marke` (Vertrag §4), und eine Einheit gibt den genauen
Zeitpunkt (`bei`) und beim gemeinsamen Start den Nullpunkt der Aufnahme vor.

**Diagnosemodus** (Ben, 4.11.2026, `docs/plan_diagnosemodus.md`): `diagnose_starten`
hängt an die laufende Aufnahme einen Rohmitschnitt (``mitschnitt-v1``, Vertrag §14) — neben
dem Backup ``.backup_<ts>_mitschnitt.jsonl``, beim Speichern ``sensor_<ts>_mitschnitt.jsonl``
— und schaltet die gewählten Zusatzströme der Quelle ein (EKG, Beschleunigung). Alle 30 s
eine Zustandsprobe (Akku von Gerät und Handy, Verzug der Ereignisschleife, Pakete).
`diagnose_beenden` stellt die Ströme zurück; die Messung läuft weiter.

**Beschleunigung: ein Strom, mehrere Abnehmer** (Ben, 4.11.2026, ``docs/plan_beschleunigung.md``
§5.1): Diagnosemodus und Zählen fordern sie an (`acc_anfordern`, `acc_freigeben`); gestellt wird
die höchste gewünschte Rate, und mit der letzten Freigabe geht der Strom sofort auf den Stand von
vorher zurück — ohne Nachlauf, der Akku geht vor. Der Puffer (`acc_reihe`, `acc_fenster`) füllt
sich, solange jemand anfordert; die Zeiten der Proben kommen aus dem Gerätezeitstempel, die
Ankunft ist nur der Anker. Je Rahmen gilt die Rate, mit der die Quelle ihn wirklich schickt
(``acc_gestartet``, nicht der neue Wunsch); wechselt sie im Fenster, taktet `acc_reihe` die
übrigen Rahmen auf die jüngste um (`umtakten`), statt sie wegzulassen. Gespeichert wird daraus
im Alltag nichts (P123).

**Eine neue Aufnahme beginnt mit leeren Kurven** (Ben, 16.10.2026):
`aufnahme_starten` leert das Live-Fenster und setzt die Live-Achse auf 0.
**Titel und Beschreibung schon vor der Aufnahme** (Ben, 17.10.2026: `titel_notiz`)
und ebenso Notizen mit Zeitpunkt (`ereignisse`, `notiz_zeitbezug`) — beim Start
übernimmt die Aufnahme sie, die Notizen rücken an ihren Anfang.

Kein flet-Import: Der Messlauf ist ohne Bildschirm testbar (Simulator).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import time
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from hrv_core import mitschnitt as mt
from hrv_core.atem import QUELLE_SENSOR, AtemSammler, atem_journal_pfad, atem_pfad
from hrv_core.aufnahme import Aufnahme, backup_entfernen, backup_lesen
from hrv_core.ausschnitte import (
    Abschnitt,
    aus_grenzen,
    grenze_aus_notiz,
    paare_aus_notizen,
    spuren_speichern,
)
from hrv_core.constants import malik_threshold
from hrv_core.ekg import EkgSammler, ekg_journal_pfad, ekg_pfad
from hrv_core.ereignisse import Zeitbezug, anker_aus_wand, notiz
from hrv_core.live import LiveFenster
from hrv_core.ppi import messluecken
from hrv_core.recording import Recording, freier_pfad, messordner, speichern
from hrv_core.regeln import Korrekturregeln
from hrv_core.segments import abdeckung
from hrv_core.zeitachse import Kontinuitaetsuhr

from ..config import app_version
from ..core import abschnitte as eigene_abschnitte
from ..core.atem_protokoll import feld_lesen, kopffeld_schreiben
from ..core.diagnose import kontext_aus_notizen as diagnose_marken_kontext
from ..core.diagnose import kontext_zeile as diagnose_kontext
from ..core.einheit import SPUR_TIMER
from ..core.gurt_warnung import Artefaktwache
from ..core.hrv_export import diagnose_pfad, diagnose_text
from .base import DeviceStatus, EkgPaket, HeartRateSource, Messwert, PpiPaket, Verbindung
from .mitschnitt import MitschnittTransport
from .profiles import GeraeteProfil, profil_fuer_namen

#: Abstand der Zustandsproben im Diagnosemodus (s)
PROBE_S = 30.0
#: Längste Dauer des Vorabtests im Sensorblatt (s)
VORABTEST_S = 20.0
#: So viele ACC-Rahmen hält der Puffer (200 Hz, 36 Proben je Rahmen: gut 10 min) — ein Satz,
#: der länger läuft, endet (`devices.zaehlen`: ``zu_lang``), statt still zu wenig zu zählen
ACC_PUFFER_RAHMEN = 3600
#: Rate, wenn die Quelle keine nennt (Vorgabe des H10 in hrv-core)
ACC_RATE_VORGABE_HZ = 200
#: Springt die Gerätezeit gegen die Ankunft um mehr als das (s), gilt ein neuer Anker
#: (Neuverbinden, neue Zählung im Gerät)
ACC_ANKER_SPRUNG_S = 2.0
#: Takt, in dem der Verzug der Ereignisschleife gemessen wird (s)
VERZUG_TAKT_S = 0.25
#: Ab so vielen fehlenden Proben (in Abständen der Rate) ist zwischen zwei Rahmen eine Lücke —
#: `umtakten` füllt sie nicht
ACC_LUECKE_PROBEN = 3.0

#: Alle so viele Sekunden schreibt die Aufnahme ein Backup (praxis_gui: 15 s).
BACKUP_S = 15.0


@dataclass(frozen=True, slots=True)
class AccReihe:
    """Beschleunigung aus dem Puffer (`Messlauf.acc_reihe`): Proben in einem Takt, mit der
    Zeit jeder Probe auf der Uhr der Quelle — über eine Lücke im Strom hinweg springt ``t``."""

    #: Proben n × 3 (mG)
    xyz: np.ndarray
    rate_hz: float
    #: Zeit jeder Probe (s, Uhr der Quelle), aufsteigend
    t: np.ndarray


def umtakten(
    xyz: np.ndarray, t: np.ndarray, rate_hz: float, ziel_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    """Proben einer Rate auf eine andere bringen — je lückenlosem Stück linear auf ein
    gleichmäßiges Raster der Zielrate; geht es herunter, vorher über die Rahmenbreite gemittelt
    (sonst fiele das Rauschen ungeglättet hinein). Lücken im Strom bleiben Lücken.

    >>> t = np.arange(0, 2, 1 / 200)
    >>> xyz = np.column_stack([t * 100, np.zeros_like(t), np.ones_like(t)])
    >>> neu, tn = umtakten(xyz, t, 200, 50)
    >>> neu.shape, float(tn[1] - tn[0]), round(float(neu[40, 0]), 6)
    ((100, 3), 0.02, 80.0)
    >>> luecke = np.concatenate([t, t + 10])
    >>> _, tl = umtakten(np.vstack([xyz, xyz]), luecke, 200, 50)
    >>> tl.shape[0], bool(tl.max() > 11), bool(((tl > 2.5) & (tl < 9.5)).any())
    (200, True, False)
    """
    xyz = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(t, dtype=np.float64)
    if xyz.shape[0] == 0 or rate_hz == ziel_hz:
        return xyz, t
    breite = max(1, round(rate_hz / ziel_hz)) | 1  # ungerade: das Mittel bleibt zentriert
    grenze = ACC_LUECKE_PROBEN / rate_hz
    schnitte = np.flatnonzero(np.diff(t) > grenze) + 1
    teile_xyz: list[np.ndarray] = []
    teile_t: list[np.ndarray] = []
    for von, bis in zip(
        np.concatenate([[0], schnitte]), np.concatenate([schnitte, [t.shape[0]]]), strict=True
    ):
        stueck_t, stueck = t[von:bis], xyz[von:bis]
        ordnung = np.argsort(stueck_t, kind="stable")  # Anker-Schwankung: nie rückwärts
        stueck_t, stueck = stueck_t[ordnung], stueck[ordnung]
        if breite > 1 and stueck.shape[0] >= breite:
            kern = np.ones(breite) / breite
            gewicht = np.convolve(np.ones(stueck.shape[0]), kern, mode="same")
            stueck = np.column_stack(
                [np.convolve(stueck[:, k], kern, mode="same") / gewicht for k in range(3)]
            )
        raster = np.arange(stueck_t[0], stueck_t[-1] + 0.5 / ziel_hz, 1.0 / ziel_hz)
        raster = raster[raster <= stueck_t[-1] + 1e-9]
        teile_t.append(raster)
        teile_xyz.append(
            np.column_stack([np.interp(raster, stueck_t, stueck[:, k]) for k in range(3)])
        )
    return np.concatenate(teile_xyz), np.concatenate(teile_t)


@dataclass(frozen=True, slots=True)
class Gespeichert:
    """Was nach „Stopp & speichern" für den Datenbankeintrag gebraucht wird."""

    pfad: Path
    recording: Recording
    sha1: str
    started_at: datetime
    dauer_s: float
    abdeckung_pct: float
    n_luecken: int
    #: Profil beim Start — nur aus einem wiederhergestellten Backup bekannt;
    #: ``None`` = das aktive Profil (beim normalen Stopp hält es `Messlauf.subject_id`)
    subject_id: str | None = None


def _sha1(pfad: Path) -> str:
    return hashlib.sha1(pfad.read_bytes()).hexdigest()  # Prüfsumme, keine Sicherheitsfunktion


def _gespeichert(
    pfad: Path, rec: Recording, *, dauer_s: float, subject_id: str | None = None
) -> Gespeichert:
    """Kennzahlen für die Datenbankzeile aus der frisch geschriebenen Messdatei."""
    deckung = abdeckung(rec.beats, messluecken(rec))
    return Gespeichert(
        pfad=pfad,
        recording=rec,
        sha1=_sha1(pfad),
        started_at=rec.start_utc or datetime.now(UTC),
        dauer_s=dauer_s,
        abdeckung_pct=float(deckung.get("coverage_pct", 100.0)),
        n_luecken=int(deckung.get("n_gaps", 0)),
        subject_id=subject_id,
    )


def backup_wiederherstellen(backup: Path) -> Gespeichert | None:
    """Aus einem liegengebliebenen Crash-Backup die Messdatei machen.

    Schreibt ``sensor_<Start>.json`` neben das Backup (derselbe Zeitstempel,
    `Recording.dateiname`), trägt die Abschnittsgrenzen des Timers ins Sidecar
    und löscht das Backup erst danach. Liegt die Messdatei schon da (Speichern
    lief durch, nur das Aufräumen nicht), bleibt sie unangetastet. Ein Backup
    ohne einen einzigen Schlag wird gelöscht — ``None``, wie bei
    `Messlauf.aufnahme_stoppen`. Das Diagnoseprotokoll kommt nicht wieder.

    Raises:
        ValueError: Backup unlesbar (`hrv_core.aufnahme.backup_lesen`).
        OSError: Schreiben oder Löschen scheiterte — das Backup bleibt liegen.
    """
    rec, zusatz = backup_lesen(backup)
    if not rec.beats:
        backup_entfernen(backup)
        return None
    pfad = backup.parent / rec.dateiname()
    if not pfad.exists():
        pfad = speichern(rec, backup.parent)
        # Das Protokollfeld „Atmung“, wie das Backup es zuletzt bestimmte (`Messlauf._zusatz`)
        if (atmung := feld_lesen(zusatz)) is not None:
            with contextlib.suppress(OSError, ValueError):
                kopffeld_schreiben(pfad, atmung)
        spuren = _spuren_lesen(zusatz)
        spuren.update(eigene_abschnitte.grenzen_aus_notizen(rec.ereignisse))
        if spuren:  # Abschnitte je Spur — scheitert das, bleibt die Messung
            with contextlib.suppress(OSError, ValueError, TypeError):
                spuren_speichern(pfad, rec, spuren)
    # Das EKG-Journal (Rohsignal auf Wunsch) wird zum Beiwerk neben der Messdatei
    journal = ekg_journal_pfad(backup)
    if journal.exists():
        with contextlib.suppress(OSError, ValueError):
            sammler = EkgSammler.aus_journal(journal)
            if sammler.n and not ekg_pfad(pfad).exists():
                sammler.schreiben(pfad)
        with contextlib.suppress(OSError):
            journal.unlink()
    # Ebenso das Atem-Journal (Phasen aus dem Prototyp, Vertrag §15) — ein beim Absturz
    # offener Lauf endet mit dem letzten bekannten Zeitpunkt (`AtemSammler.dokument`)
    atem_journal = atem_journal_pfad(backup)
    if atem_journal.exists():
        with contextlib.suppress(OSError, ValueError):
            sammler_atem = AtemSammler.aus_journal(atem_journal)
            if not sammler_atem.leer and not atem_pfad(pfad).exists():
                sammler_atem.schreiben(pfad)
        with contextlib.suppress(OSError):
            atem_journal.unlink()
    # Ebenso der Rohmitschnitt des Diagnosemodus — er bleibt, wie er ist, und heißt nur neu
    mitschnitt_journal = mt.journal_pfad(backup)
    if mitschnitt_journal.exists() and not mt.mitschnitt_pfad(pfad).exists():
        with contextlib.suppress(OSError):
            os.replace(mitschnitt_journal, mt.mitschnitt_pfad(pfad))
    backup_entfernen(backup)  # Kopf, Journal und was an Begleit-Journalen übrig ist
    subject_id = zusatz.get("subject_id")
    return _gespeichert(
        pfad,
        rec,
        dauer_s=rec.dauer_s,
        subject_id=str(subject_id) if subject_id else None,
    )


def _spuren_lesen(zusatz: dict[str, Any]) -> dict[str, list[tuple[dict, str, bool]]]:
    """Abschnittsgrenzen aus dem Backup: ``grenzen`` ist die Spur des Timers (wie bisher),
    ``spuren`` alle anderen (seit 17.10.2026). Was nicht passt, fällt einzeln weg.

    >>> n = {"beat_index": 3}
    >>> s = _spuren_lesen({"grenzen": [[n, "A", False]], "spuren": {"km": [[n, "km 1", 0], 7]}})
    >>> {k: [g[1:] for g in v] for k, v in s.items()}
    {'timer': [('A', False)], 'km': [('km 1', False)]}
    """
    roh: dict[str, Any] = {}
    if isinstance(zusatz.get("grenzen"), list):
        roh[SPUR_TIMER] = zusatz["grenzen"]
    weitere = zusatz.get("spuren")
    if isinstance(weitere, dict):
        for spur, liste in weitere.items():
            if isinstance(liste, list) and spur != SPUR_TIMER:
                roh[str(spur)] = liste
    spuren: dict[str, list[tuple[dict, str, bool]]] = {}
    for spur, liste in roh.items():
        grenzen: list[tuple[dict, str, bool]] = []
        for g in liste:
            with contextlib.suppress(TypeError, ValueError):
                n, name, ende = g
                grenzen.append((dict(n), str(name), bool(ende)))
        if grenzen:
            spuren[spur] = grenzen
    return spuren


def _an_den_anfang(e: dict, start_utc: datetime | None) -> dict:
    """Eine Notiz von vor der Aufnahme an deren Anfang (Zeitpunkt 0).

    Text, Übungen und fremde Felder bleiben (`hrv_core.ereignisse.notiz` mit
    ``alt``); die Uhrzeit ist die des Aufnahmestarts.

    >>> s = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)
    >>> e = _an_den_anfang({"t_wall_s": 12.0, "text": "Kaffee", "uebungen": ["AB12CD34"]}, s)
    >>> e["beat_index"], e["t_wall_s"], e["text"], e["uebungen"]
    (None, 0.0, 'Kaffee', ['AB12CD34'])
    """
    return notiz(str(e.get("text") or ""), anker_aus_wand((), 0.0), start_utc, alt=e)


#: Ohne ein einziges Intervall nach so vielen Paketen (≈ Sekunden) gilt ein Gerät
#: als reiner Pulsgeber — auch ohne Angabe im Geräteprofil (`Messlauf.nur_puls`)
NUR_PULS_NACH = 10

#: Das Verfahren, das die Atemphasen findet — steht als Kennzeichnung im Beiwerk ``atem-v1``
#: (`hrv_core.atem`, Vertrag `docs/kompatibilitaet.md` §15): Prototyp, kein ``ALGO_VERSION``
ATEM_PROTOTYP = "hrv_core.prototyp.atemzuege"


class _Laufend:
    """Platzhalter in `Messlauf._schreiben`: „der laufende EKG- bzw. Atem-Sammler“
    (``None`` heißt keiner)."""


_LAUFEND = _Laufend()


class _Ungesetzt:
    """Platzhalter für `Messlauf._acc_vorher`: „noch nichts gemerkt“ (``None`` heißt aus)."""


_UNGESETZT = _Ungesetzt()


def _gleiche_uebung(stand: dict[str, Any], felder: dict[str, Any]) -> bool:
    """Gehört der Satz des Zähl-Teils zur Übung der Notiz? Über den Kurzcode (beide aus
    `core.kurzcode`), sonst über den Namen; weiß eine Seite nichts, gilt er.

    >>> _gleiche_uebung({"uebung_id": "AAAA"}, {"uebung_id": "AAAA", "uebung": "x"})
    True
    >>> _gleiche_uebung({"uebung_id": "AAAA", "uebung": "Kniebeuge"}, {"uebung_id": "BBBB"})
    False
    >>> _gleiche_uebung({"uebung": "Kniebeuge"}, {"uebung": "Liegestütz"}), _gleiche_uebung({}, {})
    (False, True)
    """
    for schluessel in ("uebung_id", "uebung"):
        a, b = stand.get(schluessel), felder.get(schluessel)
        if a and b:
            return bool(a == b)
    return True


class Messlauf:
    """Verbindet eine Quelle mit Live-Anzeige und Aufnahme."""

    def __init__(
        self,
        quelle: HeartRateSource,
        *,
        jetzt_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
        backup_basis: Path | None = None,
        regeln: Korrekturregeln | None = None,
        subject_id: str | None = None,
        puffer_s: float | None = None,
    ) -> None:
        self.quelle = quelle
        #: Wie weit die Live-Kurven zurückreichen (s) — Einstellung „Live-Verlauf“ (Ben,
        #: 26.10.2026); ``None`` = Vorgabe von hrv-core (30 min)
        self.puffer_s = float(puffer_s) if puffer_s else None
        #: Profil, für das gemessen wird — beim Start gemerkt, damit ein Profilwechsel
        #: während der Messung die Aufnahme nicht umhängt (Ben, 15.10.2026)
        self.subject_id = subject_id
        #: Erkennungsregeln der Live-Anzeige (`regeln_setzen`)
        self.regeln = regeln or Korrekturregeln()
        #: EKG-Rohsignal der laufenden Aufnahme (Polar H10 auf Wunsch; Ben, 30.10.2026) —
        #: entsteht mit dem ersten Rahmen, wird als Beiwerk ``_ecg.json`` gespeichert
        self.ekg: EkgSammler | None = None
        #: Atemphasen der laufenden Aufnahme aus dem Beschleunigungssensor (Ben, 5.11.2026,
        #: `docs/plan_beschleunigung.md` §7.4) — legt `atem_sammler` an, sobald eine Einheit
        #: „Atmung erfassen“ einschaltet; gespeichert als Beiwerk ``_atem.json`` (Vertrag §15)
        self.atem: AtemSammler | None = None
        #: Ob gerade eine Atem-Spur läuft (`atem_lauf_beginn` bis `atem_lauf_ende`) — auch
        #: ohne Aufnahme gemerkt: Beginnt eine Aufnahme mittendrin oder folgt eine zweite,
        #: bekommt sie ihren Sammler mit einem Lauf ab ihrem Start (fünfte Prüfrunde, B1)
        self.atem_aktiv = False
        #: Gerät (Profil-ID) und Rate der Atem-Spur, wie `atem_sammler` sie zuletzt nannte
        self._atem_vorgabe: tuple[str, int | float | None] = ("", None)
        #: Protokollfeld „Atmung“ der Messdatei (`core.atem_protokoll`, Vertrag §5, P125): die
        #: Oberfläche belegt den Haken mit dem Übungskatalog (Ereignisse der Aufnahme → Feld
        #: oder ``None`` = unbekannt); gerufen im Loop beim Backup und vor dem Speichern
        self.atmung_protokoll: Callable[[list[dict[str, Any]]], dict[str, Any] | None] | None = None
        #: Rohmitschnitt der laufenden Aufnahme im Diagnosemodus (offen, solange er läuft;
        #: geschlossen bis zum Speichern, dann umbenannt) — `diagnose_starten`
        self.mitschnitt: mt.Schreiber | None = None
        #: Seit wann der Diagnosemodus aufzeichnet (Uhr der Quelle)
        self.diagnose_seit: float | None = None
        #: EKG vor dem Diagnosemodus — `diagnose_beenden` stellt es wieder her (die
        #: Beschleunigung gibt er frei, `acc_freigeben`)
        self._diagnose_vorher: bool | None = None
        #: EKG, das der Messlauf will (Diagnosemodus, Vorabtest) — ``None``: wie die Quelle
        self._ekg_soll: bool | None = None
        #: Wer die Beschleunigung braucht: Zweck (``diagnose``, ``zaehlen``) → (Rate, Bereich)
        self._acc_anforderungen: dict[str, tuple[int, int]] = {}
        #: Stand der Quelle vor der ersten Anforderung — die letzte Freigabe stellt ihn her
        self._acc_vorher: tuple[int, int] | _Ungesetzt | None = _UNGESETZT
        #: Gerätezeit → Uhr der Quelle (s): der Anker der Probenzeiten (`_acc_empfangen`)
        self._acc_versatz: float | None = None
        #: Ankunft des letzten ACC-Rahmens (Uhr der Quelle) — ``None``: noch keiner
        self.acc_zuletzt: float | None = None
        #: Die letzte Probe, die aus dem vollen Puffer fiel (Uhr der Quelle) — ``None``: keine,
        #: seit er zuletzt leer war. Ein Fenster, das davor beginnt, ist nicht mehr ganz da
        self.acc_verloren_bis: float | None = None
        #: Die Ströme der Quelle werden eines nach dem anderen umgeschaltet (der Steuerpunkt
        #: beantwortet ein Kommando nach dem anderen) — jeder Auftrag stellt den neuesten Stand
        self._stroeme_lock = asyncio.Lock()
        #: Nummer des jüngsten Auftrags (`_stroeme_anwenden`) — nur er räumt danach auf
        self._stroeme_nr = 0
        #: Vorgemerkt im Sensorblatt: (EKG, Beschleunigung, Kopf) — beginnt mit der Aufnahme
        self._diagnose_wunsch: tuple[bool, tuple[int, int] | None, dict[str, Any]] | None = None
        self._probe_task: asyncio.Task[None] | None = None
        self._stroeme_task: asyncio.Task[None] | None = None
        #: Beginn des Vorabtests (Uhr der Quelle) — ``None``: keiner
        self.vorabtest_seit: float | None = None
        #: Verzug der Ereignisschleife (ms): letzter Wert und Spitze seit der letzten Probe
        self.verzug_ms = 0
        self._verzug_spitze_ms = 0
        #: Beschleunigung der letzten Minuten für den Zähler-Prototyp: je Rahmen (Ankunft,
        #: Gerätezeit ns, Rate, Proben n × 3 mG, Zeit der letzten Probe auf der Uhr der Quelle)
        self._acc_puffer: deque[tuple[float, int, int, np.ndarray, float]] = deque(
            maxlen=ACC_PUFFER_RAHMEN
        )
        #: Marken dieser Diagnose: (Uhr, Typ, ID) — für den Vergleich nach dem Satz
        self._diagnose_marken: list[tuple[float, str, int]] = []
        #: Beginn des laufenden Satzes (Uhr): Start der Übung bzw. der letzte eingetragene Satz
        self._satz_beginn: float | None = None
        #: Sätze, die der Zähl-Teil schon verglich (`zaehlsatz_vergleichen`): (Kurzcode, Wert,
        #: der Vergleich, ob er dabei eingetragen war) — ihre Notiz zum Satz beim Eintragen
        #: (`zaehl_notizen`, `ui.uebung_lauf`) vergleicht nicht noch einmal
        self._gezaehlt_verglichen: deque[tuple[str | None, int, dict[str, Any], bool]] = deque(
            maxlen=32
        )
        #: Kommen gerade die Notizen zu gezählten Sätzen (`zaehl_notizen`)? Nur sie gehören zu
        #: `_gezaehlt_verglichen` — ein Chip mit gleichem Wert ist ein Satz von Hand
        self._zaehl_notizen = False
        #: Zeilen ``satz`` im Mitschnitt seit dem letzten ``uebung_start`` und dessen Kurzcode —
        #: hrv-research ordnet die k-te dem Satz k zu; dieselbe Nummer tragen die Marken
        #: (`marken_satz`, `naechster_satz`)
        self._satz_zeilen = 0
        self._satz_uebung: str | None = None
        #: Wer den Vergleich nach dem Satz zeigt (Oberfläche) — Fehler darin stoppen nichts
        self.diagnose_satz_beobachter: Callable[[dict[str, Any]], None] | None = None
        #: Der letzte Vergleich (Übung, Satz, Marken, Sensor, Korrektur, eingetragen)
        self.letzter_satz: dict[str, Any] | None = None
        #: Der Satz des laufenden Zähl-Teils (`devices.zaehlen.ZaehlBaustein` setzt und löscht
        #: den Haken): ``{"satz", "sensor", "korrektur", "wert", "feld"}`` — der Vergleich nach
        #: dem Satz nimmt dann dessen Wert (ein Zähler, nicht zwei; Plan §5.2)
        self.zaehl_satz: Callable[[], dict[str, Any] | None] | None = None
        # Die Uhr der Quelle — beim Simulator läuft sie ``tempo``-fach, bei echten
        # Geräten ist sie time.monotonic(). t_capture der Messwerte passt dazu.
        self._uhr: Callable[[], float] = getattr(quelle, "jetzt", time.monotonic)
        self._jetzt_utc = jetzt_utc
        self._backup_basis = backup_basis
        self._dateiname_fest: str | None = None  # vorab festgelegter Dateiname (F10)
        self.live = self._neues_live_fenster()
        #: Gurt-Warnung bei zu vielen Artefakten (`core.gurt_warnung`, 26.10.2026)
        self.artefaktwache = Artefaktwache()
        # Live-x-Achse gebündelter PPI-Pakete (Verity Sense): Schlagzeiten aus der
        # Intervallsumme statt aus der streuenden Ankunft (`hrv_core.zeitachse`).
        self._ppi_uhr = Kontinuitaetsuhr()
        #: Anzeigezeiten des letzten PPI-Pakets: (rr_ms, t, verworfen, fehler_ms) in Folge
        self._schlagzeiten: deque[tuple[int, float, bool, int]] = deque()
        self.aufnahme: Aufnahme | None = None
        #: „Stopp & speichern“ läuft (H39: das Schreiben darf in einem Thread liegen) —
        #: solange kommt kein Schlag und kein Backup mehr in die Aufnahme, und ein
        #: zweiter Stopp speichert sie nicht noch einmal
        self._wird_gespeichert = False
        #: Abschnittsgrenzen der laufenden Aufnahme je Spur (Timer, km, Übung, Einheit):
        #: (Notiz, Name, Ende?) — jede Spur teilt nur sich selbst (`spuren_speichern`)
        self._grenzen: dict[str, list[tuple[dict, str, bool]]] = {}
        #: Notizen ohne Aufnahme (Ben, 16.10.2026) — `aufnahme_starten` übernimmt sie
        self._vorab: list[dict] = []
        #: Titel und Beschreibung ohne Aufnahme (Ben, 17.10.2026) — ebenso
        self._vorab_titel = ""
        self._vorab_notiz = ""
        self.status = DeviceStatus(verbindung=Verbindung.GETRENNT)
        self.device_id = ""
        self.geraet_name = ""
        self._name_bekannt = False
        self.profil: GeraeteProfil | None = None
        self.simulation = False
        #: Nullpunkt der Live-Achse (Verbindungsbeginn, ab der ersten Aufnahme deren
        #: Start), monotonic — und dieselbe Stelle auf der Wanduhr
        self.start_mono = self._uhr()
        self._achse_utc = jetzt_utc()
        self._letztes_backup = 0.0
        #: Wird mit ``layout=True`` gerufen, wenn sich die Verbindung ändert,
        #: sonst nach neuen Messwerten. Fehler im Beobachter stoppen nichts.
        self.beobachter: Callable[[bool], None] | None = None

    def _neues_live_fenster(self, **extra: float) -> LiveFenster:
        """Ein leerer Live-Puffer in der eingestellten Länge."""
        if self.puffer_s is not None:
            extra["max_s"] = self.puffer_s
        return LiveFenster(**extra)

    # -- Zeit ------------------------------------------------------------------

    def jetzt_s(self) -> float:
        """Sekunden seit Verbindungsbeginn bzw. Aufnahmestart — die x-Achse der Live-Kurven."""
        return self._uhr() - self.start_mono

    @property
    def achse_utc(self) -> datetime:
        """Die Wanduhr (UTC) am Nullpunkt der Live-Achse — für eine Achse mit Uhrzeiten
        (`core.zeitangabe.uhr_text`)."""
        return self._achse_utc

    @property
    def uhr(self) -> Callable[[], float]:
        """Die Uhr der Quelle (monotonic, beim Simulator schneller) — auch die Uhr einer
        Einheit, zu der diese Messung gehört (`devices.einheit`)."""
        return self._uhr

    @property
    def verbunden(self) -> bool:
        return self.status.verbindung in (Verbindung.VERBUNDEN, Verbindung.VERBINDE)

    @property
    def warnung(self) -> str | None:
        """„Gurt prüfen: 12 % Artefakte“, solange die Live-Messung zu viele markierte
        Schläge hat — ``None`` sonst (`core.gurt_warnung.Artefaktwache`)."""
        return self.artefaktwache.text

    # -- Verbinden und Lesen ---------------------------------------------------------

    async def verbinden(self, device_id: str, name: str | None = None) -> None:
        self.device_id = device_id
        # Name und Adresse bleiben getrennt (Ben, 19.10.2026): ein Gurt ohne
        # Bluetooth-Namen bekommt in der Messdatei `geraet` = "Unbekannt" und die
        # Adresse in `adresse` — nie die Adresse als Name, denn `deid` leert nur
        # das Adressfeld. Für die Anzeige (`geraet_name`) bleibt die Adresse als
        # Notnagel, damit die Person das Gerät wiedererkennt.
        self.geraet_name = name or device_id
        self._name_bekannt = bool(name)
        self.simulation = device_id.startswith("sim:")
        self.profil = profil_fuer_namen(name or "")
        self.live.leeren()
        self.status = DeviceStatus(verbindung=Verbindung.VERBINDE, meldung="Verbinde …")
        await self.quelle.connect(device_id, name)
        # Das Profil steht erst nach dem Verbinden fest (ohne Namen: aus den
        # PMD-Features). Optische Intervalle streuen mehr — die EKG-Schwelle
        # markierte bei der Verity Sense gesunde Schläge als Artefakt.
        self.profil = self.quelle.profil or self.profil
        quelle = self.profil.intervall_quelle if self.profil else ""
        self.live = self._neues_live_fenster(malik=malik_threshold(quelle))
        self.live.regeln_setzen(self.regeln, quelle)
        self._ppi_uhr = Kontinuitaetsuhr()
        self._schlagzeiten.clear()
        self.start_mono = self._uhr()
        self._achse_utc = self._jetzt_utc()
        self._vorab = []
        self._vorab_titel = self._vorab_notiz = ""
        self.status = self.quelle.aktueller_status

    def regeln_setzen(self, regeln: Korrekturregeln) -> None:
        """Neue Erkennungsregeln — wirken sofort auf den ganzen Live-Puffer."""
        self.regeln = regeln
        self.live.regeln_setzen(regeln, self.profil.intervall_quelle if self.profil else "")

    async def laufen(self) -> None:
        """Liest, bis die Quelle endet — über `page.run_task` starten."""
        status_task = asyncio.create_task(self._status_lesen())
        try:
            async for wert in self.quelle.stream():
                # Beim Speichern (Thread) ist die Aufnahme beendet: nichts mehr hinein
                aufnahme = None if self._wird_gespeichert else self.aufnahme
                if isinstance(wert, PpiPaket):
                    if aufnahme is not None:
                        aufnahme.ppi_paket(
                            wert.t_capture, wert.ppi_ms, wert.fehler_ms, wert.blocker, wert.kontakt
                        )
                    self._ppi_paket_erwarten(wert)
                    continue
                if isinstance(wert, EkgPaket):
                    # Nur mitschreiben, nicht rechnen; vor der Aufnahme verfällt der Rahmen
                    if aufnahme is not None:
                        if self.ekg is None:
                            self.ekg = EkgSammler()
                            aufnahme.ecg_aufzeichnung = True
                        t_wall = wert.t_capture - aufnahme.start_mono
                        self.ekg.rahmen(wert.zeitstempel_ns, wert.uv, t_wall_s=t_wall)
                        self.ekg.batterie_melden(t_wall, self.status.batterie_prozent)
                    continue
                if not isinstance(wert, Messwert):
                    continue
                t_live, fehler = self._live_zeit(wert)
                self.live.hinzufuegen(
                    t_live - self.start_mono, wert.rr_ms, wert.hf_bpm, fehler_ms=fehler
                )
                self._verworfene_zeigen()
                self.artefaktwache.pruefen(self.live.artefaktanteil(), t_live - self.start_mono)
                if aufnahme is not None:
                    aufnahme.schlag(wert.rr_ms, wert.hf_bpm, wert.t_capture, wert.tw_src)
                    self._backup_wenn_faellig()
                self._melden(False)
        finally:
            status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await status_task
            self.status = replace(self.status, verbindung=Verbindung.GETRENNT)
            self._melden(True)

    def _ppi_paket_erwarten(self, paket: PpiPaket) -> None:
        """Anzeigezeiten aller Intervalle eines PPI-Pakets vormerken.

        Die brauchbaren kommen gleich als `Messwert` hinterher und holen sich
        ihre Zeit in `_live_zeit`. Die vom Gerät verworfenen gehen direkt ins
        Live-Fenster (`_verworfene_zeigen`), jeweils an ihrer Stelle in der
        Folge — dort trennen sie die Kennzahlen und füllen die Kurve.
        """
        self._verworfene_zeigen()
        gueltig = [p > 0 for p in paket.ppi_ms]
        zeiten = iter(self._ppi_uhr.paket(paket.t_capture, paket.ppi_ms, gueltig))
        erwartet: deque[tuple[int, float, bool, int]] = deque()
        fehler_je = list(paket.fehler_ms) + [0] * (len(paket.ppi_ms) - len(paket.fehler_ms))
        for rr, blocker, fehler in zip(paket.ppi_ms, paket.blocker, fehler_je, strict=False):
            if rr <= 0:
                continue
            _, t = next(zeiten)
            erwartet.append((rr, t, bool(blocker), int(fehler)))
        self._schlagzeiten = erwartet
        self._verworfene_zeigen()

    def _verworfene_zeigen(self) -> None:
        """Verworfene Intervalle vorn in der Warteschlange ins Live-Fenster schreiben."""
        while self._schlagzeiten and self._schlagzeiten[0][2]:
            rr, t, _, fehler = self._schlagzeiten.popleft()
            self.live.hinzufuegen(t - self.start_mono, rr, 0, verworfen=True, fehler_ms=fehler)

    def _live_zeit(self, wert: Messwert) -> tuple[float, int]:
        """Anzeigezeit eines Schlags: Kontinuitätsuhr, falls er zum letzten PPI-Paket gehört.

        Die Quelle schickt das Paket vor seinen Schlägen. Passt das Intervall
        nicht zum nächsten erwarteten (fremder Schlag), gilt die Ankunft. Die
        Datei bekommt immer die Ankunftszeit (``aufnahme.schlag``). Dazu die
        Fehlerschätzung des Geräts für dieses Intervall (0 = keine).
        """
        if self._schlagzeiten:
            if self._schlagzeiten[0][0] == wert.rr_ms:
                _, t, _, fehler = self._schlagzeiten.popleft()
                return t, fehler
            self._schlagzeiten.clear()
        return wert.t_capture, 0

    async def _status_lesen(self) -> None:
        async for s in self.quelle.status():
            vorher = self.status.verbindung
            self.status = s
            if self.aufnahme is not None and s.batterie_prozent is not None:
                self.aufnahme.batterie_prozent = s.batterie_prozent
                if self.ekg is not None:
                    self.ekg.batterie_melden(
                        self._uhr() - self.aufnahme.start_mono, s.batterie_prozent
                    )
            self._melden(s.verbindung != vorher)

    def diagnose(self, **zusatz: str) -> str:
        """Kopf und Verbindungsprotokoll der Quelle als Text — zum Teilen und Ablegen.

        Leer, wenn die Quelle kein Protokoll führt (Simulator). ``zusatz`` hängt
        weitere Kopfzeilen an (z. B. die Eckdaten einer Aufnahme).
        """
        zeilen = list(getattr(self.quelle, "protokoll", []))
        if not zeilen:
            return ""
        s = self.status
        status = [s.verbindung.value]
        if s.batterie_prozent is not None:
            status.append(f"Akku {s.batterie_prozent} %")
        if s.meldung:
            status.append(s.meldung)
        kopf = {
            "App": f"Trainingsassistent {app_version()[0]}",
            "Gerät": f"{self.geraet_name} [{self.device_id}]",
            "Profil": self.profil.id if self.profil else "–",
            "Status": " · ".join(status),
            "Stand": self._jetzt_utc().astimezone().isoformat(timespec="seconds"),
            **zusatz,
        }
        return diagnose_text(kopf, zeilen)

    def _melden(self, layout: bool) -> None:
        if self.beobachter is None:
            return
        # Die Anzeige darf die Messung nie stoppen.
        with contextlib.suppress(Exception):
            self.beobachter(layout)

    # -- Aufnahme -----------------------------------------------------------------

    def aufnahme_starten(
        self, *, start_mono: float | None = None, start_utc: datetime | None = None
    ) -> None:
        """Aufnahme beginnen — mit leeren Kurven (Ben, 16.10.2026).

        Das Live-Fenster wird geleert und die Live-Achse beginnt bei 0: Kurven,
        Kacheln und Analyse zeigen nur noch, was zur neuen Aufnahme gehört. Titel und
        Beschreibung von vor dem Start übernimmt sie, Notizen stehen an ihrem Anfang
        (`_an_den_anfang`).
        """
        if self.aufnahme is not None:
            return
        # Eine Einheit gibt Nullpunkt und Wanduhr vor (gemeinsamer Start, Vorlauf im
        # Countdown) — sonst liest die Aufnahme beide selbst.
        profil = self.profil
        start = self._uhr() if start_mono is None else min(start_mono, self._uhr())
        self._dateiname_fest = None
        self.aufnahme = Aufnahme(
            geraet=self.geraet_name if self._name_bekannt else "Unbekannt",
            geraet_profil=profil.id if profil else "ble_generic",
            adresse=None if self.simulation else self.device_id,
            intervall_quelle=profil.intervall_quelle if profil else "ekg_rr",
            start_mono=start,
            start_utc=start_utc or self._jetzt_utc(),
            ppi=bool(profil and profil.kann("pmd_ppi")),
            simulation=self.simulation,
        )
        self.aufnahme.batterie_prozent = self.status.batterie_prozent
        self.ekg = None
        self.atem = None
        self._atem_laufend_anlegen()
        self._grenzen = {}
        self._letztes_backup = start
        self.live.leeren()
        self.start_mono = start
        self._achse_utc = self.aufnahme.start_utc
        vorab, self._vorab = self._vorab, []
        self.aufnahme.ereignisse = [_an_den_anfang(e, self.aufnahme.start_utc) for e in vorab]
        self.aufnahme.titel, self.aufnahme.notiz = self._vorab_titel, self._vorab_notiz
        self._vorab_titel = self._vorab_notiz = ""
        # Im Sensorblatt vorgemerkt: der Rohmitschnitt beginnt mit der Aufnahme (auch mit
        # Vorlauf einer Einheit, die sie erst später startet)
        if self._diagnose_wunsch is not None and self.diagnose_moeglich:
            self._diagnose_beginnen()

    def notiz_zeitbezug(self) -> Zeitbezug:
        """Zeitbezug der Live-Achse für Notizen — mit und ohne Aufnahme.

        Während einer Aufnahme zählen Live-Achse und Wanduhr der Aufnahme beide ab
        ihrem Start (`aufnahme_starten`); ``wand_versatz`` hält einen Unterschied
        fest, falls es je einen gibt. Ohne Aufnahme gibt es keine Schläge: Die
        Wanduhr einer Notiz ist dann ihre Stelle auf der Live-Achse.
        """
        aufnahme = self.aufnahme
        if aufnahme is None:
            return Zeitbezug(lambda: (), self._achse_utc, wand_versatz=0.0)
        return Zeitbezug(
            lambda: aufnahme.beats,
            aufnahme.start_utc,
            wand_versatz=aufnahme.start_mono - self.start_mono,
        )

    def titel_notiz(self) -> tuple[str, str]:
        """Titel und Beschreibung (``titel``/``notiz`` der Datei) — der laufenden Aufnahme,
        ohne Aufnahme die für die nächste (Ben, 17.10.2026)."""
        if self.aufnahme is not None:
            return self.aufnahme.titel or "", self.aufnahme.notiz or ""
        return self._vorab_titel, self._vorab_notiz

    def titel_notiz_setzen(self, titel: str, notiz: str) -> None:
        """Titel und Beschreibung setzen: in der Aufnahme landen sie mit Backup und
        Messdatei, ohne Aufnahme übernimmt sie der nächste Start (`aufnahme_starten`)."""
        if self.aufnahme is not None:
            self.aufnahme.titel, self.aufnahme.notiz = titel, notiz
        else:
            self._vorab_titel, self._vorab_notiz = titel, notiz

    def ereignisse(self) -> list[dict]:
        """Die Notizen — der laufenden Aufnahme, ohne Aufnahme die für die nächste (Kopie)."""
        return list(self.aufnahme.ereignisse if self.aufnahme is not None else self._vorab)

    def ereignisse_setzen(self, liste: list[dict]) -> None:
        """Notizen ersetzen: in der Aufnahme landen sie mit Backup und Messdatei, ohne
        Aufnahme warten sie auf den Start (`aufnahme_starten`)."""
        if self.aufnahme is not None:
            self.aufnahme.ereignisse = list(liste)
        else:
            self._vorab = list(liste)

    def notiz_hinzufuegen(
        self,
        text: str,
        vor_s: float = 0.0,
        *,
        bei: float | None = None,
        marke: dict | None = None,
        uebungen: Sequence[str] | None = None,
    ) -> dict | None:
        """Notiz in die laufende Aufnahme, ``vor_s`` Sekunden vor jetzt — ohne Aufnahme ``None``.

        Für den Timer: Jeder Abschnittsanfang wird eine Notiz an der Stelle, an der
        er war (`core.timer.TimerLauf.neue_marken`). Verankert wie „+ Notiz" →
        „Jetzt" über die Wanduhr. Angehängt, nicht einsortiert: So verrutscht keine
        Notiz, die gerade jemand bearbeitet (das Notizfeld merkt sich den Index).

        ``bei``: die Stelle auf der Uhr (`uhr`) statt ``vor_s`` — eine Einheit meldet
        Ereignisse mit ihrer genauen Zeit. ``marke``: maschinenlesbar, wer die Notiz
        setzte und was sie bedeutet (Vertrag §4). ``uebungen``: Kurzcodes der Übungen,
        die die Notiz nennt (Vertrag §4, „Planke beginnt“ eines Übungs-Timers).
        """
        if self.aufnahme is None:
            return None
        eintrag = self._notiz_bauen(text, vor_s, bei=bei, marke=marke, uebungen=uebungen)
        self.aufnahme.ereignisse.append(eintrag)
        return eintrag

    def _notiz_bauen(
        self,
        text: str,
        vor_s: float,
        *,
        bei: float | None,
        marke: dict | None,
        uebungen: Sequence[str] | None = None,
    ) -> dict:
        """Eine verankerte Notiz — nie in der Zukunft."""
        zb = self.notiz_zeitbezug()
        jetzt = self.jetzt_s()
        x = jetzt - max(vor_s, 0.0) if bei is None else min(bei - self.start_mono, jetzt)
        eintrag = notiz(text, zb.anker(x), zb.start_utc, uebungen=uebungen or None, marke=marke)
        if marke is not None and self.diagnose_aktiv and self.mitschnitt is not None:
            # Im Diagnosemodus steht jede automatische Notiz auch als Kontext im Mitschnitt —
            # Übung, Timer, eingetragener Satz (Plan §3.1), an ihrer Stelle auf der Uhr
            with contextlib.suppress(Exception):
                if (zeile := diagnose_kontext(eintrag)) is not None:
                    was, felder = zeile
                    if was == "satz":
                        self._satz_notiz(felder, self.start_mono + x)
                    else:
                        self.mitschnitt.kontext(was, t=round((self.start_mono + x) * 1e9), **felder)
                    if was == "uebung_start":
                        self._satz_beginn = self.start_mono + x
                        self._gezaehlt_verglichen.clear()
                        uebung_id = felder.get("uebung_id")
                        self._satz_uebung = uebung_id if isinstance(uebung_id, str) else None
                        self._satz_zeilen = 0
                    elif was == "uebung_ende":
                        self._satz_uebung = None
        return eintrag

    def _satz_notiz(self, felder: dict[str, Any], t: float) -> None:
        """Die Notiz zu einem Satz im Diagnosemodus: Zeile ``satz`` und der Vergleich nach dem
        Satz. Gehört sie zu einem Satz, den der Zähl-Teil schon verglich (`zaehl_notizen`: das
        Eintragen nach dem Ende oder „Eintragen“ der Meldung), steht seine Zeile schon da
        (`zaehlsatz_vergleichen`, an seinem Ende, vor „uebung_ende“) — keine zweite, kein
        zweiter Vergleich; war er dort nicht eingetragen, bekommt der Vergleich den Wert
        (`_nachgetragen`)."""
        if self._zaehl_notizen:
            frueher = self._schon_verglichen(felder)
            if frueher is not None:
                if not frueher[3]:
                    self._nachgetragen(frueher[2], felder)
                return
        self._satz_zeile(t, felder)
        self._satz_vergleichen(felder, t)

    def _satz_zeile(self, t: float, felder: dict[str, Any]) -> None:
        """Eine Zeile ``satz`` in den Mitschnitt (``t`` Uhr der Quelle) — mit der Nummer, die
        hrv-research ihr gibt (die k-te nach ``uebung_start``), wenn die Übung dieselbe ist."""
        assert self.mitschnitt is not None
        n = self._satz_zeilen + 1
        mehr: dict[str, Any] = {}
        gleiche = self._satz_uebung is not None and felder.get("uebung_id") in (
            None,
            self._satz_uebung,
        )
        if "satz" not in felder and gleiche:
            mehr["satz"] = n
        self.mitschnitt.kontext("satz", t=round(t * 1e9), **felder, **mehr)
        self._satz_zeilen = n  # erst, wenn sie steht

    @contextlib.contextmanager
    def zaehl_notizen(self) -> Iterator[None]:
        """Die Notizen zu Sätzen, die der Zähl-Teil zählte, kommen (`ui.uebung_lauf._eintragen`):
        Nur sie gehören zu den schon verglichenen Sätzen (`_satz_notiz`). Ein Chip mit
        zufällig gleichem Wert ist ein Satz von Hand und vergleicht wie immer — vorher hielt er
        einen abgebrochenen, nie eingetragenen Satz für seinen Nachtrag."""
        alt, self._zaehl_notizen = self._zaehl_notizen, True
        try:
            yield
        finally:
            self._zaehl_notizen = alt

    def naechster_satz(self, uebung_id: str | None) -> int | None:
        """Die Nummer, die die nächste Zeile ``satz`` dieser Übung bekommt (Diagnosemodus): die
        Zeilen seit ihrem ``uebung_start`` plus eins — ``1``, solange ihr Start noch nicht im
        Mitschnitt steht (die 5-s-Regel). ``None`` ohne Diagnosemodus."""
        if not self.diagnose_aktiv or self.mitschnitt is None:
            return None
        if self._satz_uebung is None or uebung_id != self._satz_uebung:
            return 1
        return self._satz_zeilen + 1

    def marken_satz(self) -> dict[str, Any] | None:
        """Für die Marken-Leiste (`core.diagnose.kontext_aus_notizen`): der Satz des Zähl-Teils
        (`zaehl_satz`), solange er einen meint — sonst die nächste Zeile ``satz`` der Übung
        (`naechster_satz`). So trägt jede Marke die Nummer, unter der hrv-research die Eingabe
        ihres Satzes findet: Ein Satz, den nur der Sensor zählte und der nicht eingetragen
        wurde, hat eine Zeile, aber keine Notiz zum Satz."""
        if self.zaehl_satz is not None:
            stand: Any = None
            with contextlib.suppress(Exception):
                stand = self.zaehl_satz()
            if isinstance(stand, dict):
                return stand
        if self._satz_uebung is None or not self.diagnose_aktiv:
            return None
        return {"uebung_id": self._satz_uebung, "satz": self._satz_zeilen + 1}

    def abschnitt_markieren(
        self,
        text: str,
        vor_s: float = 0.0,
        *,
        name: str,
        ende: bool = False,
        spur: str = SPUR_TIMER,
        bei: float | None = None,
        marke: dict | None = None,
        als_notiz: bool = True,
        uebungen: Sequence[str] | None = None,
    ) -> dict | None:
        """Wie `notiz_hinzufuegen` — und die Notiz wird beim Speichern eine Abschnittsgrenze.

        Für den Timer: Seine Abschnitte werden Abschnitte der Messung (Sidecar wie
        praxis_gui, `ausschnitte.spuren_speichern`) — danach unabhängig von den
        Notizen verschieb- und löschbar. ``ende``: beendet nur den letzten.
        ``spur``: Jede Spur (Timer, km, Übung, Einheit) teilt nur sich selbst.
        ``als_notiz=False``: eine stille Grenze ohne Notiz (etwa das Ende einer Spur).
        """
        if self.aufnahme is None:
            return None
        if als_notiz:
            eintrag = self.notiz_hinzufuegen(text, vor_s, bei=bei, marke=marke, uebungen=uebungen)
        else:
            eintrag = self._notiz_bauen(text, vor_s, bei=bei, marke=marke, uebungen=uebungen)
        if eintrag is not None:
            self._grenzen.setdefault(spur, []).append((eintrag, name, ende))
        return eintrag

    # -- Eigene Abschnitte der Person (Ben, 27.10.2026; `core.abschnitte`) -------------

    def offener_abschnitt(self) -> tuple[str, str] | None:
        """``(Kennung, Name)`` des eigenen Abschnitts, der gerade läuft — sonst ``None``."""
        return eigene_abschnitte.offener(self.ereignisse())

    def abschnitt_starten(
        self, name: str, *, kopf_s: float = 0.0, endteil_s: float = 0.0
    ) -> str | None:
        """„Abschnitt: Start“ — die Start-Notiz bei jetzt; läuft schon einer, endet er hier.
        Ohne Aufnahme ``None`` (die Grenzen brauchen Schläge)."""
        if self.aufnahme is None:
            return None
        if self.offener_abschnitt() is not None:
            self.abschnitt_beenden()
        kennung = eigene_abschnitte.neue_kennung()
        self.notiz_hinzufuegen(
            eigene_abschnitte.start_text(name),
            marke=eigene_abschnitte.start_marke(kennung, name, kopf_s, endteil_s),
        )
        return kennung

    def abschnitt_beenden(self) -> bool:
        """„‹Name› · Ende“ — die Ende-Notiz bei jetzt; ``False``, wenn keiner läuft."""
        offen = self.offener_abschnitt()
        if offen is None or self.aufnahme is None:
            return False
        kennung, name = offen
        self.notiz_hinzufuegen(
            eigene_abschnitte.ende_text(name), marke=eigene_abschnitte.ende_marke(kennung, name)
        )
        return True

    def abschnitte(self) -> list[Abschnitt]:
        """Die Abschnitte der laufenden Aufnahme auf der Live-Achse: die der Abläufe aus
        ihren Grenzen (Timer, Übung, km — wie sie das Sidecar beim Speichern bekommt) und
        die eigenen aus den Notizpaaren; ein laufender reicht bis jetzt."""
        if self.aufnahme is None:
            return []
        zb = self.notiz_zeitbezug()
        jetzt = self.jetzt_s()
        teile: list[Abschnitt] = []
        for grenzen in self._grenzen.values():
            punkte = [
                grenze_aus_notiz(x, eintrag, name, schluss)
                for eintrag, name, schluss in grenzen
                if (x := zb.x(eintrag)) is not None
            ]
            teile.extend(aus_grenzen(punkte, 0.0, jetzt))
        teile.extend(paare_aus_notizen(self.aufnahme.ereignisse, lambda e: zb.x(dict(e)), jetzt))
        teile.sort(key=lambda a: (a.von_s, a.bis_s))
        return teile

    def nur_puls(self) -> bool:
        """Sendet das Gerät nur die Herzfrequenz (bpm), keine Intervalle von Schlag zu Schlag?

        Ben, 17.10.2026: Uhren und Sensoren, die nur den Puls übertragen, bekommen den Puls
        als Hauptkurve. Hinterlegt ist das im Geräteprofil (`GeraeteProfil.hrv_moeglich`,
        z. B. `UHR_BROADCAST`); ohne Angabe dort entscheidet, was ankommt: `NUR_PULS_NACH`
        Pakete ohne ein einziges Intervall. Kommt eines, ist es das Tachogramm.
        """
        punkte = self.live.punkte()
        if any(p.rr_ms > 0 for p in punkte):
            return False
        if self.profil is not None and not self.profil.hrv_moeglich:
            return True
        return len(punkte) >= NUR_PULS_NACH

    def aufnahme_dauer_s(self) -> float:
        return self.aufnahme.dauer_s() if self.aufnahme is not None else 0.0

    def datei_relativ(self) -> str | None:
        """Die Messdatei der laufenden Aufnahme relativ zu ``Messungen/`` — wie
        ``hrv_recording.file_path``. Steht schon beim Start fest (Verweis einer Einheit).
        """
        if self.aufnahme is None:
            return None
        geraeteordner = self.profil.ordner if self.profil else "Unbekannt"
        ordner = messordner(Path(), geraeteordner, simulation=self.simulation)
        return (ordner.relative_to("Messungen") / self._dateiname()).as_posix()

    def _dateiname(self) -> str:
        """Der Name, unter dem `aufnahme_stoppen` speichern wird: Liegt schon eine Datei mit
        der Startsekunde da, hängt hrv-core einen Zähler an (F10) — der Verweis einer
        Einheit muss denselben Namen tragen, darum hier dieselbe Regel (`freier_pfad`)."""
        assert self.aufnahme is not None
        if self._dateiname_fest is None:
            name = self.aufnahme.dateiname()
            if self._backup_basis is not None:
                name = freier_pfad(self._ordner(self._backup_basis), name).name
            self._dateiname_fest = name
        return self._dateiname_fest

    def _ordner(self, basis: Path) -> Path:
        geraeteordner = self.profil.ordner if self.profil else "Unbekannt"
        return messordner(basis, geraeteordner, simulation=self.simulation)

    def _backup_wenn_faellig(self) -> None:
        if self.aufnahme is None or self._uhr() - self._letztes_backup < BACKUP_S:
            return
        self.backup_jetzt()

    def backup_jetzt(self) -> None:
        """Sofort ein Backup der laufenden Aufnahme — außerhalb des 15-s-Takts.

        Für den Lebenszyklus: Geht die App in den Hintergrund, stehen so auch
        die letzten Sekunden drin, falls Android sie gleich darauf beendet.
        Ohne Aufnahme oder Backup-Basis passiert nichts; ein Schreibfehler
        stoppt die Messung nicht.
        """
        if self.aufnahme is None or self._backup_basis is None or self._wird_gespeichert:
            return
        self._letztes_backup = self._uhr()
        with contextlib.suppress(OSError):
            kopf = self.aufnahme.backup(self._ordner(self._backup_basis), zusatz=self._zusatz())
            if self.ekg is not None and self.ekg.n:
                self.ekg.journal_anhaengen(ekg_journal_pfad(kopf))
            if self.atem is not None and not self.atem.leer:
                self.atem.journal_anhaengen(atem_journal_pfad(kopf))
        if self.mitschnitt is not None:
            self.mitschnitt.sichern()

    def _zusatz(self) -> dict[str, object]:
        """Was das Backup über die Datei hinaus braucht (`backup_wiederherstellen`)."""
        zusatz: dict[str, object] = {
            "subject_id": self.subject_id,
            # Die Spur des Timers wie bisher — so lesen auch ältere Stände sie
            "grenzen": [list(g) for g in self._grenzen.get(SPUR_TIMER, [])],
        }
        andere = {s: [list(g) for g in gs] for s, gs in self._grenzen.items() if s != SPUR_TIMER}
        if any(andere.values()):
            zusatz["spuren"] = {s: gs for s, gs in andere.items() if gs}
        # Das Protokollfeld „Atmung“ nach dem Stand von jetzt — so bekommt es auch eine
        # wiederhergestellte Messdatei (`backup_wiederherstellen`), ohne den Katalog
        if (feld := self.atmung_feld(self.aufnahme)) is not None:
            zusatz["atmung"] = feld
        return zusatz

    def atmung_feld(self, aufnahme: Aufnahme | None) -> dict[str, Any] | None:
        """Das Protokollfeld „Atmung“ dieser Aufnahme (`atmung_protokoll`) — ``None`` ohne
        Haken, ohne Aufnahme oder wenn der Haken es nicht weiß; ein Fehler im Haken kostet
        nur das Feld, nie die Messung."""
        if aufnahme is None or self.atmung_protokoll is None:
            return None
        try:
            feld = self.atmung_protokoll([dict(e) for e in aufnahme.ereignisse])
        except Exception:
            logging.getLogger(__name__).exception("Protokollfeld „Atmung“ nicht bestimmt")
            return None
        return feld_lesen({"atmung": feld}) if feld is not None else None

    # -- Atemphasen (Beiwerk ``_atem.json``, docs/plan_beschleunigung.md §7.4) ---------------

    def atem_sammler(self, *, geraet: str, rate_hz: int | float | None) -> AtemSammler | None:
        """Der Atem-Sammler der laufenden Aufnahme — beim ersten Aufruf angelegt
        (``quelle="sensor"``, Prototyp `ATEM_PROTOTYP`), danach derselbe; ``geraet`` ist die
        Profil-ID (``polar_h10``), ``rate_hz`` die Abtastrate der Beschleunigung.

        ``None`` ohne Aufnahme: Phasen gibt es nur als Beiwerk einer Messdatei (Plan §4.1 —
        ohne Aufnahme fehlen nur die Atemphasen an der Messdatei, das Zählen läuft trotzdem).
        """
        self._atem_vorgabe = (geraet, rate_hz)
        return self._atem_anlegen()

    def _atem_anlegen(self) -> AtemSammler | None:
        """Der Sammler der laufenden Aufnahme nach `_atem_vorgabe` — angelegt, wenn er fehlt;
        ``None`` ohne Aufnahme."""
        if self.aufnahme is None:
            return None
        if self.atem is None:
            geraet, rate_hz = self._atem_vorgabe
            self.atem = AtemSammler(QUELLE_SENSOR, geraet, rate_hz, prototyp=ATEM_PROTOTYP)
        return self.atem

    def _atem_laufend_anlegen(self) -> None:
        """Läuft gerade eine Atem-Spur (`atem_aktiv`), bekommt eine Aufnahme, die jetzt
        beginnt (Start, zweite Aufnahme, Teil 2 nach dem Teilen), ihren Sammler mit einem
        Lauf ab ihrem Start — die Spur war die ganze Zeit an, nur das Beiwerk fehlte."""
        if self.atem_aktiv and self.atem is None and (s := self._atem_anlegen()) is not None:
            s.lauf_beginn(0.0)

    def _atem_wand(self, t_quelle_s: float) -> tuple[AtemSammler, float] | None:
        """Sammler und Wanduhr der Aufnahme (``t − start_mono``, wie beim EKG) — ``None``
        ohne Aufnahme oder ohne Sammler (`atem_sammler` oder eine laufende Spur zuerst)."""
        aufnahme = self.aufnahme
        if aufnahme is None:
            return None
        self._atem_laufend_anlegen()
        if self.atem is None:
            return None
        return self.atem, t_quelle_s - aufnahme.start_mono

    def atem_lauf_beginn(self, t_quelle_s: float) -> None:
        """„Atmung erfassen“ beginnt (Uhr der Quelle) — gemerkt auch ohne Aufnahme
        (`atem_aktiv`); ins Beiwerk kommt der Lauf nur mit Aufnahme, nie vor ihrem Start."""
        self._atem_anlegen()  # erst der Sammler, dann die Spur — sonst begänne ein Lauf bei 0
        self.atem_aktiv = True
        if (w := self._atem_wand(t_quelle_s)) is not None:
            w[0].lauf_beginn(max(w[1], 0.0))

    def atem_lauf_ende(self, t_quelle_s: float) -> None:
        """„Atmung erfassen“ endet (Uhr der Quelle); ohne Aufnahme passiert nichts weiter."""
        self.atem_aktiv = False
        if (w := self._atem_wand(t_quelle_s)) is not None:
            w[0].lauf_ende(max(w[1], 0.0))

    def atem_phase(self, t_quelle_s: float, art: str) -> None:
        """Beginn des Ein- (``"ein"``) oder Ausatmens (``"aus"``) auf der Uhr der Quelle.
        Eine Phase von vor dem Start der Aufnahme (ihr Ansatz lag vor der Naht beim Teilen,
        bestätigt wurde sie danach) gehört nicht in diese Datei — keine negativen Zeiten
        (fünfte Prüfrunde, B2)."""
        if (w := self._atem_wand(t_quelle_s)) is not None and w[1] >= 0.0:
            w[0].phase(w[1], art)

    def atem_fenster(
        self, t_ende_quelle_s: float, rate: float | None, gueltig: bool, grund: str = ""
    ) -> None:
        """Ergebnis eines Prüffensters (Ende auf der Uhr der Quelle, Rate je Minute, gültig,
        Grund als snake_case-Code des Prototyps); ohne Aufnahme oder von vor ihrem Start
        passiert nichts."""
        if (w := self._atem_wand(t_ende_quelle_s)) is not None and w[1] >= 0.0:
            w[0].fenster(w[1], rate, gueltig, grund)

    def aufnahme_stoppen(self, basis: Path) -> Gespeichert | None:
        """Speichert atomar und beendet die Aufnahme. ``None``, wenn nichts aufgezeichnet wurde.

        Scheitert das Schreiben (Speicher voll, Ordner nicht beschreibbar), bleibt die
        Aufnahme im Lauf — der Aufrufer bekommt die Ausnahme und kann es noch einmal
        versuchen; vorher war sie in dem Moment weg (H24, 19.10.2026).

        Schreibt im aufrufenden Thread; die Oberfläche nimmt `aufnahme_stoppen_async`,
        damit eine 4-h-Datei den Event-Loop nicht anhält (H39).
        """
        aufnahme = self._stopp_beginnen()
        if aufnahme is None:
            return None
        try:
            ergebnis = self._schreiben(aufnahme, basis)
        except BaseException:
            self._stopp_beenden(gespeichert=False)
            raise
        self._stopp_beenden(gespeichert=True)
        return ergebnis

    async def aufnahme_stoppen_async(self, basis: Path) -> Gespeichert | None:
        """Wie `aufnahme_stoppen`, aber Messdatei, Abschnitte und Diagnoseprotokoll
        schreibt ein Thread (`asyncio.to_thread`, H39).

        Beenden und Aufräumen bleiben im Loop: Ab dem Aufruf nimmt die Aufnahme keinen
        Schlag mehr an (`laufen`), ``self.aufnahme`` bleibt bis zum fertigen Schreiben
        stehen (H24) und wird erst danach gelöscht — der Thread verändert nichts an
        ``self``.
        """
        aufnahme = self._stopp_beginnen()
        if aufnahme is None:
            await self._stroeme_zurueck()
            return None
        atmung = self.atmung_feld(aufnahme)  # im Loop (der Haken liest den Katalog)
        try:
            ergebnis = await asyncio.to_thread(
                self._schreiben, aufnahme, basis, None, _LAUFEND, _LAUFEND, _LAUFEND, atmung
            )
        except BaseException:
            self._stopp_beenden(gespeichert=False)
            raise
        self._stopp_beenden(gespeichert=True)
        await self._stroeme_zurueck()
        return ergebnis

    async def aufnahme_teilen_async(self, basis: Path) -> Gespeichert | None:
        """„Teil speichern & weiter“ (Ben, 28.10.2026, lange Aufnahmen): die bisherige
        Aufnahme als Messdatei speichern und **ohne Lücke** eine neue beginnen — der
        Strom läuft sofort in die neue, Teil 1 schreibt ein Thread. Titel geht mit, die
        Abschnittsgrenzen der Abläufe bleiben bei Teil 1 (ein offener eigener Abschnitt
        endet dort mit dem Teil). Zusammenfügen: `hrv_core.zusammenfuegen`.
        ``None``, wenn nichts aufgezeichnet ist oder gerade gespeichert wird.
        Scheitert das Schreiben, bleibt das Backup von Teil 1 liegen (Wiederherstellung
        beim nächsten Start) — die neue Aufnahme läuft trotzdem weiter.
        """
        alt = self.aufnahme
        if alt is None or not alt.beats or self._wird_gespeichert:
            return None
        jetzt = self._uhr()
        neu = Aufnahme(
            geraet=alt.geraet,
            geraet_profil=alt.geraet_profil,
            adresse=alt.adresse,
            intervall_quelle=alt.intervall_quelle,
            start_mono=jetzt,
            start_utc=self._jetzt_utc(),
            ppi=alt.ppi,
            simulation=self.simulation,
        )
        neu.batterie_prozent = self.status.batterie_prozent
        neu.titel = alt.titel
        grenzen_alt, self._grenzen = self._grenzen, {}
        # Das EKG bis hier gehört zu Teil 1: sein Sammler geht mit, Teil 2 beginnt mit dem
        # nächsten Rahmen einen neuen (mit eigenem Journal und `ecg_aufzeichnung`) — vorher
        # bekam Teil 1 kein `_ecg.json`, und alles landete neben dem letzten Teil (V4)
        ekg_alt, self.ekg = self.ekg, None
        # Die Atemphasen bis hier ebenso: ein offener Lauf „Atmung erfassen“ endet in Teil 1
        # an der Naht; läuft die Spur weiter, beginnt sie in Teil 2 bei 0 neu
        # (`_atem_laufend_anlegen`, sobald ``self.aufnahme`` die neue ist) — jeder Teil trägt
        # seine Läufe
        atem_alt, self.atem = self.atem, None
        if atem_alt is not None and atem_alt.offen:
            atem_alt.lauf_ende(jetzt - alt.start_mono)
        # Ebenso der Rohmitschnitt: Teil 1 behält seinen, Teil 2 schreibt ohne Lücke einen
        # neuen weiter, solange der Diagnosemodus läuft
        mitschnitt_alt, self.mitschnitt = self.mitschnitt, None
        self._dateiname_fest = None
        self.aufnahme = neu
        self._atem_laufend_anlegen()
        self._letztes_backup = jetzt
        if mitschnitt_alt is not None and mitschnitt_alt.offen:
            self._mitschnitt_oeffnen(mitschnitt_alt.pfad.name)
        atmung_alt = self.atmung_feld(alt)  # im Loop (der Haken liest den Katalog)
        return await asyncio.to_thread(
            self._schreiben, alt, basis, grenzen_alt, ekg_alt, mitschnitt_alt, atem_alt, atmung_alt
        )

    def _stopp_beginnen(self) -> Aufnahme | None:
        """Die Aufnahme beenden: ab jetzt kein Schlag mehr hinein. ``None``: nichts
        aufgezeichnet — oder ein anderer Aufruf speichert sie gerade (der trägt sie ein)."""
        aufnahme = self.aufnahme
        if aufnahme is None or not aufnahme.beats:
            self.aufnahme = None
            self.ekg = None
            self.atem = None
            self._mitschnitt_verwerfen()
            return None
        if self._wird_gespeichert:
            return None
        self._wird_gespeichert = True
        # Ein offener Lauf „Atmung erfassen“ endet mit der Aufnahme am Stopp, nicht mit dem
        # letzten Fenster (bis 5 s früher); die Spur der Einheit läuft ohne Sammler weiter
        # und bekommt mit der nächsten Aufnahme einen neuen (fünfte Prüfrunde, B5)
        if self.atem is not None and self.atem.offen:
            self.atem.lauf_ende(max(self._uhr() - aufnahme.start_mono, 0.0))
        return aufnahme

    def _stopp_beenden(self, *, gespeichert: bool) -> None:
        self._wird_gespeichert = False
        if gespeichert:
            self.aufnahme = None
            self.ekg = None
            self.atem = None
            self.mitschnitt = None
            self.diagnose_seit = None
            self._diagnose_wunsch = None  # je Messung (Plan §2.2)
            self._grenzen = {}

    def _schreiben(
        self,
        aufnahme: Aufnahme,
        basis: Path,
        grenzen: dict[str, list[tuple[dict, str, bool]]] | None = None,
        ekg: EkgSammler | _Laufend | None = _LAUFEND,
        mitschnitt: mt.Schreiber | _Laufend | None = _LAUFEND,
        atem: AtemSammler | _Laufend | None = _LAUFEND,
        atmung: dict[str, Any] | _Laufend | None = _LAUFEND,
    ) -> Gespeichert:
        """Messdatei, Abschnitte je Spur und Diagnoseprotokoll schreiben — liest ``self``
        nur, darum auch in einem Thread möglich. ``grenzen``: die Spuren dieser Aufnahme
        (ohne Angabe die laufenden); ``ekg`` und ``atem``: EKG- und Atem-Sammler dieser
        Aufnahme (ohne Angabe die laufenden); ``atmung``: das Protokollfeld „Atmung“ (ohne
        Angabe aus dem Haken — die Loop-Aufrufer bestimmen es vorher, `atmung_feld`)."""
        if isinstance(atmung, _Laufend):
            atmung = self.atmung_feld(aufnahme)
        pfad = aufnahme.speichern(self._ordner(basis))
        if atmung is not None:
            # Das Protokollfeld in den Kopf, hinter `datenqualitaet` (Vertrag §3/§5) — scheitert
            # das, bleibt die Messung ohne das Feld (= unbekannt)
            with contextlib.suppress(OSError, ValueError):
                kopffeld_schreiben(pfad, atmung)
        if isinstance(mitschnitt, _Laufend):
            mitschnitt = self.mitschnitt
        if mitschnitt is not None:
            self._mitschnitt_ablegen(mitschnitt, pfad)
        if isinstance(ekg, _Laufend):
            ekg = self.ekg
        if ekg is not None and ekg.n:
            # Das Beiwerk neben die Messdatei; das Journal des Backups ist damit erledigt
            with contextlib.suppress(OSError):
                ekg.schreiben(pfad)
            if self._backup_basis is not None:
                with contextlib.suppress(OSError):
                    ekg_journal_pfad(
                        self._ordner(self._backup_basis) / aufnahme.backup_name()
                    ).unlink(missing_ok=True)
        if isinstance(atem, _Laufend):
            atem = self.atem
        if atem is not None and not atem.leer:
            # Die Atemphasen ebenso als Beiwerk; ohne einen Lauf gibt es keine Datei (§15)
            with contextlib.suppress(OSError):
                atem.schreiben(pfad)
            if self._backup_basis is not None:
                with contextlib.suppress(OSError):
                    atem_journal_pfad(
                        self._ordner(self._backup_basis) / aufnahme.backup_name()
                    ).unlink(missing_ok=True)
        if (
            grenzen is None
            and self._dateiname_fest is not None
            and pfad.name != self._dateiname_fest
        ):
            logging.getLogger(__name__).warning(
                "Messdatei heißt %s, angekündigt war %s", pfad.name, self._dateiname_fest
            )
        rec = aufnahme.recording()
        quelle = self._grenzen if grenzen is None else grenzen
        spuren = {s: list(gs) for s, gs in quelle.items()}
        # Eigene Abschnitte der Person: aus ihren Notizpaaren, wie sie jetzt in der
        # Aufnahme stehen (verschoben, umbenannt, gelöscht — `core.abschnitte`)
        spuren.update(eigene_abschnitte.grenzen_aus_notizen(rec.ereignisse))
        if any(spuren.values()):  # Abschnitte je Spur — scheitert das, bleibt die Messung
            with contextlib.suppress(OSError, ValueError):
                spuren_speichern(pfad, rec, spuren)
        # Das Verbindungsprotokoll gehört zur Messung: Ohne adb ist es die einzige
        # Spur, warum ein Sensor (Verity Sense) Lücken oder keine Intervalle hatte.
        text = self.diagnose(
            Aufnahme=f"{pfad.name}, {len(rec.beats)} Zeilen, "
            f"{len(rec.ppi_pakete or [])} PPI-Pakete",
            **(
                {
                    "EKG": f"{ekg.n} Proben in {ekg.n_rahmen} Rahmen, {len(ekg.luecken())} Lücken, "
                    f"Akku {' → '.join(str(int(b[1])) for b in ekg.batterie) or '–'} %"
                }
                if ekg is not None and ekg.n
                else {}
            ),
            **(
                {
                    "Atmung": f"{len(atem.phasen)} Phasen, {len(atem.fenster_liste)} Fenster "
                    f"in {len(atem.laeufe)} Läufen ({atem.prototyp})"
                }
                if atem is not None and not atem.leer
                else {}
            ),
        )
        if text:
            with contextlib.suppress(OSError):
                diagnose_pfad(pfad).write_text(text, encoding="utf-8")
        return _gespeichert(pfad, rec, dauer_s=aufnahme.dauer_s())

    # -- Diagnosemodus (docs/plan_diagnosemodus.md) -------------------------------------------

    @property
    def mitschnitt_transport(self) -> MitschnittTransport | None:
        """Der mithörende Transport der Quelle — ``None`` (Simulator, Desktop ohne ihn)."""
        transport = getattr(self.quelle, "transport", None)
        return transport if isinstance(transport, MitschnittTransport) else None

    @property
    def diagnose_aktiv(self) -> bool:
        """Zeichnet der Diagnosemodus gerade auf? (Der rote Punkt.)"""
        return self.mitschnitt is not None and self.mitschnitt.offen

    @property
    def diagnose_moeglich(self) -> bool:
        """Lässt sich hier ein Rohmitschnitt anhängen (mithörender Transport, Ablage)?"""
        return self.mitschnitt_transport is not None and self._backup_basis is not None

    @property
    def diagnose_vorgemerkt(self) -> bool:
        """Im Sensorblatt gewählt, die Aufnahme hat aber noch nicht begonnen."""
        return self._diagnose_wunsch is not None and not self.diagnose_aktiv

    def diagnose_vormerken(
        self,
        *,
        ekg: bool = True,
        acc: tuple[int, int] | None = None,
        kopf: dict[str, Any] | None = None,
    ) -> None:
        """Den Diagnosemodus für diese Messung wählen: läuft schon eine Aufnahme, beginnt er
        sofort, sonst mit ihr (`aufnahme_starten`). Die Zusatzströme schaltet ein Hintergrund-
        auftrag ein (meist laufen sie schon seit dem Vorabtest)."""
        self._diagnose_wunsch = (bool(ekg), acc, dict(kopf or {}))
        self.vorabtest_seit = None
        if self.aufnahme is not None and not self.diagnose_aktiv and self.diagnose_moeglich:
            self._diagnose_beginnen()

    async def diagnose_starten(
        self,
        *,
        ekg: bool = True,
        acc: tuple[int, int] | None = None,
        kopf: dict[str, Any] | None = None,
    ) -> Path | None:
        """Den Rohmitschnitt der laufenden Aufnahme beginnen und die Zusatzströme einschalten
        — und darauf warten. ``None``, wenn es nicht geht: keine Aufnahme, kein mithörender
        Transport, keine Ablage — oder er läuft schon."""
        if self.aufnahme is None or self.diagnose_aktiv or not self.diagnose_moeglich:
            return None
        self._diagnose_wunsch = (bool(ekg), acc, dict(kopf or {}))
        schreiber = self._diagnose_beginnen()
        if schreiber is None:
            return None
        if self._stroeme_task is not None:
            with contextlib.suppress(Exception):
                await self._stroeme_task
        return schreiber.pfad

    def _diagnose_beginnen(self) -> mt.Schreiber | None:
        wunsch = self._diagnose_wunsch
        if wunsch is None:
            return None
        ekg, acc, kopf = wunsch
        schreiber = self._mitschnitt_oeffnen(kopf=kopf, ekg=ekg, acc=acc)
        if schreiber is None:
            return None
        self._vorher_merken()
        # Die Beschleunigung über die Anforderung (Plan Beschleunigung §5.1): endet der
        # Diagnosemodus, zählt ein laufendes Zählen weiter — und umgekehrt
        self._ekg_soll = bool(ekg)
        self._acc_setzen("diagnose", acc)
        self._stroeme_anwenden()
        self._melden(True)
        return schreiber

    def _vorher_merken(self) -> None:
        if self._diagnose_vorher is None:
            self._diagnose_vorher = bool(getattr(self.quelle, "ekg_wunsch", False))

    async def diagnose_beenden(self) -> None:
        """Zusatzströme zurück, Mitschnitt schließen — die Messung läuft weiter. Die Datei
        bleibt neben dem Backup und wird beim Speichern zum Beiwerk der Messdatei. Auch eine
        bloße Vormerkung oder ein Vorabtest endet hier."""
        self._diagnose_wunsch = None
        self.vorabtest_seit = None
        schreiber = self.mitschnitt
        if schreiber is not None and schreiber.offen:
            schreiber.kontext("diagnose_ende")
            self._mitschnitt_schliessen(schreiber)
        self.diagnose_seit = None
        await self._stroeme_zurueck()
        self._melden(True)

    # -- Vorabtest (Sensorblatt, Plan §2.3) ---------------------------------------------

    async def vorabtest_beginnen(self, *, ekg: bool, acc: tuple[int, int] | None) -> None:
        """Die gewählten Ströme einschalten, ohne Aufnahme und ohne Mitschnitt — das Blatt
        sieht über `vorabtest_stand`, ob sie mit ihrer Rate kommen."""
        self._vorher_merken()
        self.vorabtest_seit = self._uhr()
        self._ekg_soll = bool(ekg)
        self._acc_setzen("diagnose", acc)
        await self._abwarten(self._stroeme_anwenden())

    def vorabtest_stand(self, *, ekg: bool, acc: tuple[int, int] | None) -> dict[str, Any]:
        """Je gewähltem Strom die Rate seit Testbeginn gegen das Soll: ``{"hr": {"rate",
        "soll", "ok"}, …}``, dazu ``fertig`` (alles da oder 20 s vorbei) und ``seit_s``."""
        transport = self.mitschnitt_transport
        seit = self._uhr() - self.vorabtest_seit if self.vorabtest_seit is not None else 0.0
        fenster = min(10.0, max(2.0, seit))
        soll: dict[str, float] = {"hr": 1.0}
        if ekg:
            soll["ecg"] = 130.0
        if acc is not None:
            soll["acc"] = float(acc[0])
        stroeme: dict[str, Any] = {}
        jetzt = self._uhr()
        for name, sollrate in soll.items():
            rate = 0.0
            if transport is not None and name in transport.zaehler.stroeme:
                pakete_s, proben_s = transport.zaehler.stroeme[name].rate(jetzt, fenster)
                rate = pakete_s if name == "hr" else proben_s
            stroeme[name] = {
                "rate": round(rate, 1),
                "soll": sollrate,
                "ok": seit >= 2.0 and rate >= 0.8 * sollrate,
            }
        fertig = seit >= VORABTEST_S or (seit >= 3.0 and all(v["ok"] for v in stroeme.values()))
        return {"seit_s": round(seit, 1), "fertig": fertig, "stroeme": stroeme}

    async def vorabtest_abbrechen(self) -> None:
        """Blatt zu ohne Start: Ströme wie vorher, keine Vormerkung."""
        if self._diagnose_wunsch is not None or self.diagnose_aktiv:
            return
        self.vorabtest_seit = None
        await self._stroeme_zurueck()

    def marke(self, typ: str, **felder: Any) -> dict[str, Any] | None:
        """Eine Diagnosemarke in den Mitschnitt (`hrv_core.mitschnitt.Schreiber.marke`)."""
        if not self.diagnose_aktiv or self.mitschnitt is None:
            return None
        zeile = self.mitschnitt.marke(typ, **felder)
        self._diagnose_marken.append((int(zeile["t"]) / 1e9, typ, int(zeile["id"])))
        return zeile

    def marke_weg(self, marke_id: int, **felder: Any) -> dict[str, Any] | None:
        if not self.diagnose_aktiv or self.mitschnitt is None:
            return None
        self._diagnose_marken = [m for m in self._diagnose_marken if m[2] != marke_id]
        return self.mitschnitt.marke_weg(marke_id, **felder)

    # -- Beschleunigung: ein Strom, mehrere Abnehmer (Plan Beschleunigung §5.1) -----------

    @property
    def acc_anforderungen(self) -> dict[str, tuple[int, int]]:
        """Wer die Beschleunigung gerade braucht: Zweck → (Rate Hz, Bereich g)."""
        return dict(self._acc_anforderungen)

    @property
    def acc_soll(self) -> tuple[int, int] | None:
        """Was die Quelle liefern soll: die höchste gewünschte Rate und der größte Bereich —
        nie weniger als vor der ersten Anforderung. Ohne Anforderung der Stand von vorher
        (nach der letzten Freigabe), sonst der der Quelle."""
        vorher = self._acc_vorher
        if not self._acc_anforderungen:
            if isinstance(vorher, _Ungesetzt):
                return getattr(self.quelle, "acc_wunsch", None)
            return vorher
        wuensche = list(self._acc_anforderungen.values())
        if isinstance(vorher, tuple):
            wuensche.append(vorher)
        return max(r for r, _ in wuensche), max(g for _, g in wuensche)

    def acc_anfordern(self, zweck: str, rate_hz: int, bereich_g: int) -> None:
        """Die Beschleunigung für ``zweck`` (``diagnose``, ``zaehlen``) — synchron: ab jetzt
        füllt sich der Puffer, und ein Hintergrundauftrag stellt die Quelle um (ohne
        Ereignisschleife nur der Wunsch). Eine zweite Anforderung desselben Zwecks ersetzt
        die erste."""
        if self._acc_setzen(zweck, (int(rate_hz), int(bereich_g))):
            self._stroeme_anwenden()

    def acc_freigeben(self, zweck: str) -> None:
        """``zweck`` braucht die Beschleunigung nicht mehr. Mit der letzten Freigabe geht der
        Strom sofort auf den Stand vor der ersten Anforderung (P119b: der Akku geht vor), der
        Beobachter der Quelle wird frei und der Puffer leer."""
        if self._acc_setzen(zweck, None):
            self._stroeme_anwenden()

    def _acc_setzen(self, zweck: str, wunsch: tuple[int, int] | None) -> bool:
        """Eine Anforderung setzen oder (``None``) freigeben — ohne die Quelle umzustellen.
        Gibt zurück, ob sich etwas änderte."""
        alt = self._acc_anforderungen.get(zweck)
        if wunsch == alt:
            return False
        quelle: Any = self.quelle
        if wunsch is None:
            del self._acc_anforderungen[zweck]
            if not self._acc_anforderungen:
                if getattr(quelle, "acc_beobachter", None) == self._acc_empfangen:
                    quelle.acc_beobachter = None
                self._acc_leeren()
            return True
        if not self._acc_anforderungen:
            # Die erste Anforderung: was vorher war, merken; ab jetzt kommt alles in den Puffer
            if isinstance(self._acc_vorher, _Ungesetzt):
                self._acc_vorher = getattr(quelle, "acc_wunsch", None)
            self._acc_leeren()
            if hasattr(quelle, "acc_beobachter"):
                quelle.acc_beobachter = self._acc_empfangen
        self._acc_anforderungen[zweck] = (int(wunsch[0]), int(wunsch[1]))
        return True

    def _acc_leeren(self) -> None:
        self._acc_puffer.clear()
        self._acc_versatz = None
        self.acc_zuletzt = None
        self.acc_verloren_bis = None

    def _stroeme_anwenden(self) -> asyncio.Task[None] | None:
        """Die Ströme der Quelle auf den neuesten Stand bringen — ein Auftrag im Hintergrund
        (`_stroeme_task`); ohne Ereignisschleife (Test) nichts."""
        if getattr(self.quelle, "stroeme_setzen", None) is None:
            return None
        with contextlib.suppress(RuntimeError):  # ohne Ereignisschleife
            loop = asyncio.get_running_loop()
            self._stroeme_nr += 1
            self._stroeme_task = loop.create_task(
                self._stroeme_stellen(self._stroeme_nr), name="messlauf-stroeme"
            )
            return self._stroeme_task
        return None

    async def _stroeme_stellen(self, nr: int = 0) -> None:
        """Unter dem Schloss: EKG und Beschleunigung, wie sie *jetzt* sein sollen — ein
        späterer Auftrag findet so nichts Veraltetes vor. Aufgeräumt (der Stand von vorher
        gilt als wiederhergestellt, das EKG gehört wieder der Quelle) wird nur nach dem
        jüngsten Auftrag (``nr``): Kam während ``stroeme_setzen`` ein neuer (das Sensorblatt
        geht zu, „Zählen abbrechen“ gleich nach dem Tipp), stellt er den neuesten Stand — mit
        dem, was er zurückstellen soll. Räumte der ältere auf, läse der neue den Stand, den
        der ältere eben gesetzt hat, und ließe EKG und Beschleunigung an. Wirft nie."""
        async with self._stroeme_lock:
            setzen = getattr(self.quelle, "stroeme_setzen", None)
            if setzen is None:
                return
            quelle: Any = self.quelle
            ekg = self._ekg_soll
            if ekg is None:
                ekg = bool(getattr(quelle, "ekg_wunsch", False))
            with contextlib.suppress(Exception):
                await setzen(ekg=ekg, acc=self.acc_soll)
            if nr and nr != self._stroeme_nr:
                return  # ein jüngerer Auftrag wartet — er räumt auf
            if not self._acc_anforderungen:
                self._acc_vorher = _UNGESETZT  # wiederhergestellt
            if self._diagnose_vorher is None:
                self._ekg_soll = None

    @staticmethod
    async def _abwarten(task: asyncio.Task[None] | None) -> None:
        if task is not None:
            with contextlib.suppress(Exception):
                await task

    def _acc_empfangen(
        self, zeitstempel_ns: int, proben: list[tuple[int, int, int]], t_capture: float
    ) -> None:
        """Ein ACC-Rahmen in den Puffer. Die Zeit der letzten Probe kommt aus der Gerätezeit
        plus Anker: die kleinste Verspätung bisher (ein Rahmen kommt nie vor seiner letzten
        Probe an); springt die Gerätezeit, ein neuer Anker."""
        if not proben:
            return
        # Die Rate, mit der die Quelle den Rahmen wirklich schickt: Zwischen neuem Wunsch und
        # Neustart (`PolarQuelle.stroeme_setzen` wartet auf das EKG-Kommando) kommen noch
        # Rahmen der alten — mit der neuen Rate abgelegt lägen sie gestreckt auf der Zeitachse
        quelle: Any = self.quelle
        stand = (
            getattr(quelle, "acc_gestartet", None)
            or getattr(quelle, "acc_wunsch", None)
            or self.acc_soll
        )
        rate = int(stand[0]) if stand else ACC_RATE_VORGABE_HZ
        geraet_s = zeitstempel_ns / 1e9
        verspaetung = t_capture - geraet_s
        if self._acc_versatz is None or abs(verspaetung - self._acc_versatz) > ACC_ANKER_SPRUNG_S:
            self._acc_versatz = verspaetung
        else:
            self._acc_versatz = min(self._acc_versatz, verspaetung)
        werte = np.asarray(proben, dtype=np.float64).reshape(-1, 3)
        if self._acc_puffer.maxlen and len(self._acc_puffer) >= self._acc_puffer.maxlen:
            # Voll: der älteste Rahmen fällt heraus — ein Fenster bis zu ihm ist nicht mehr ganz
            self.acc_verloren_bis = float(self._acc_puffer[0][4])
        self._acc_puffer.append(
            (t_capture, int(zeitstempel_ns), rate, werte, geraet_s + self._acc_versatz)
        )
        self.acc_zuletzt = t_capture

    @property
    def acc_rate_hz(self) -> int | None:
        """Die Rate des jüngsten Rahmens im Puffer — ``None`` ohne Rahmen."""
        return int(self._acc_puffer[-1][2]) if self._acc_puffer else None

    def acc_reihe(
        self, von: float, bis: float, *, rate: float | None = None, min_s: float = 2.0
    ) -> AccReihe | None:
        """Die gepufferten Proben im Fenster [von, bis) auf der Uhr der Quelle, in einem Takt:
        ``rate`` (Vorgabe: die des jüngsten Rahmens im Fenster). Rahmen einer anderen Rate
        (sie wechselte mitten im Satz, 50 → 200 Hz, wenn die Diagnose beginnt) taktet
        `umtakten` um — der Prototyp braucht einen gleichmäßigen Takt, und weglassen hieße,
        die Wiederholungen davor zu verlieren. ``t`` ist die Zeit jeder Probe, auch über eine
        Lücke im Strom hinweg. ``None`` unter ``min_s`` Sekunden Daten."""
        laeufe: list[tuple[int, list[np.ndarray], list[np.ndarray]]] = []
        for _ankunft, _ns, r, werte, t_letzte in self._acc_puffer:
            n = werte.shape[0]
            t_erste = t_letzte - (n - 1) / r
            if t_letzte < von or t_erste >= bis:
                continue
            zeiten = t_erste + np.arange(n) / r
            if laeufe and laeufe[-1][0] == r:
                laeufe[-1][1].append(werte)
                laeufe[-1][2].append(zeiten)
            else:
                laeufe.append((r, [werte], [zeiten]))
        if not laeufe:
            return None
        ziel = float(rate) if rate else float(laeufe[-1][0])
        teile_xyz: list[np.ndarray] = []
        teile_t: list[np.ndarray] = []
        for r, werte_liste, zeiten_liste in laeufe:
            xyz, t = np.concatenate(werte_liste), np.concatenate(zeiten_liste)
            if r != ziel:
                xyz, t = umtakten(xyz, t, r, ziel)
            maske = (t >= von) & (t < bis)
            if maske.any():
                teile_xyz.append(xyz[maske])
                teile_t.append(t[maske])
        if not teile_xyz:
            return None
        reihe = AccReihe(
            np.concatenate(teile_xyz).astype(np.float64), ziel, np.concatenate(teile_t)
        )
        if reihe.xyz.shape[0] < ziel * min_s:
            return None
        return reihe

    def acc_fenster(
        self, von: float, bis: float, *, min_s: float = 2.0
    ) -> tuple[np.ndarray, float, float] | None:
        """Wie `acc_reihe` in der jüngsten Rate, kurz: ``(xyz n × 3 mG, Rate, Zeit der ersten
        Probe)`` — ``None`` unter ``min_s`` Sekunden Daten."""
        reihe = self.acc_reihe(von, bis, min_s=min_s)
        if reihe is None:
            return None
        return reihe.xyz, reihe.rate_hz, float(reihe.t[0])

    # -- Zähler-Prototyp nach dem Satz (Stufe 8) ----------------------------------------

    def _schon_verglichen(
        self, felder: dict[str, Any]
    ) -> tuple[str | None, int, dict[str, Any], bool] | None:
        """Ist die Notiz zum Satz (eine von `zaehl_notizen`) die eines Satzes, den der
        Zähl-Teil schon verglich (`zaehlsatz_vergleichen`)? Dann kein zweiter Vergleich — sonst
        ersetzte einer ohne Marken und ohne Sensor den richtigen. Eingetragene zuerst (sie
        warten auf ihre Notiz), dann die übrigen (ein Nachtrag). Gibt ihn zurück und nimmt ihn
        aus der Liste; ``None``: einer, den niemand verglich."""
        code, wert = felder.get("uebung_id"), felder.get("wert")
        for eingetragen in (True, False):
            for i, satz in enumerate(self._gezaehlt_verglichen):
                c, w = satz[0], satz[1]
                if (
                    satz[3] is eingetragen
                    and w == wert
                    and (c is None or code is None or c == code)
                ):
                    del self._gezaehlt_verglichen[i]
                    return satz
        return None

    def _nachgetragen(self, vergleich: dict[str, Any], felder: dict[str, Any]) -> None:
        """Ein gezählter Satz, der beim Vergleich nicht eingetragen war (das Zählen endete von
        selbst, die Uhr lief weiter), kommt doch ins Tagebuch („Eintragen“ der Meldung): Ist
        sein Vergleich noch der letzte, zeigt die Leiste ihn neu, mit dem eingetragenen Wert —
        Marken und Sensor bleiben (kein zweiter Vergleich mit leerem Fenster)."""
        if self.letzter_satz is not vergleich:
            return  # inzwischen kam ein anderer Satz — die Leiste zeigt den
        neu = {**vergleich, "eingetragen": felder.get("wert")}
        self.letzter_satz = neu
        if self.diagnose_satz_beobachter is not None:
            with contextlib.suppress(Exception):
                self.diagnose_satz_beobachter(neu)

    def _satz_vergleichen(self, felder: dict[str, Any], t_satz: float) -> None:
        """Nach einem eingetragenen Satz: Marken, Sensor (Prototyp), Korrektur und Eingabe
        nebeneinander — als Kontextzeile im Mitschnitt und an den Beobachter (Plan §0,
        Stufe 8). Lief ein Zähl-Teil (`zaehl_satz`), gilt dessen Satz: ein Zähler, nicht zwei
        (Plan Beschleunigung §5.2, §6); sonst zählt der Prototyp den Puffer seit Satzbeginn."""
        from hrv_core.prototyp import wiederholungen

        von = self._satz_beginn
        self._satz_beginn = t_satz
        if von is None:
            return
        marken = sum(
            1 for t, typ, _ in self._diagnose_marken if typ == mt.MARKE_WDH and von <= t < t_satz
        )
        sensor: int | None = None
        korrektur = 0
        stand: dict[str, Any] | None = None
        if self.zaehl_satz is not None:
            with contextlib.suppress(Exception):
                stand = self.zaehl_satz()
        if stand is not None and not _gleiche_uebung(stand, felder):
            stand = None  # der Zähl-Teil zählt eine andere Übung — sein Wert gilt hier nicht
        if stand is not None:
            sensor = stand.get("sensor")
            korrektur = int(stand.get("korrektur") or 0)
        else:
            fenster = self.acc_fenster(von, t_satz)
            if fenster is not None:
                with contextlib.suppress(Exception):
                    sensor = wiederholungen.zaehlen_fenster(fenster[0], fenster[1]).anzahl
        # Übung und Satz, wie die Leiste sie sah — die Notiz dieses Satzes steht noch nicht drin;
        # die Nummer seiner Zeile ``satz`` (eben geschrieben), zählt der Sensor dieselbe Übung,
        # die seines Satzes — wie die Marken (`marken_satz`)
        nummer = stand
        if nummer is None and self._satz_uebung is not None:
            nummer = {"uebung_id": self._satz_uebung, "satz": self._satz_zeilen}
        k = diagnose_marken_kontext(self.ereignisse(), lambda _code: True, nummer)
        vergleich = {
            "uebung": k.uebung,
            "satz": k.satz,
            "feld": felder.get("feld"),
            "marken": marken,
            "sensor": sensor,
            "korrektur": korrektur,
            # wie bis Stufe 8 (hrv-research liest es so): was der Sensor zählte
            "zaehler": sensor,
            "eingetragen": felder.get("wert"),
            "art": "prototyp",
        }
        self.letzter_satz = vergleich
        if self.mitschnitt is not None and sensor is not None:
            with contextlib.suppress(Exception):
                self.mitschnitt.kontext(
                    "zaehler", feld=felder.get("feld"), wert=sensor, satz=k.satz, phase="prototyp"
                )
        if self.diagnose_satz_beobachter is not None:
            with contextlib.suppress(Exception):
                self.diagnose_satz_beobachter(vergleich)

    def zaehlsatz_vergleichen(
        self,
        *,
        uebung: str,
        satz: int,
        feld: str | None,
        von: float,
        bis: float,
        sensor: int | None,
        korrektur: int,
        eingetragen: int | None,
        uebung_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Nach einem Satz, den der Sensor zählte (A2, Plan Beschleunigung §6): die Tipps der
        Marken-Leiste in [von, bis] (Uhr der Quelle) neben Sensor, Korrektur und dem, was
        eingetragen wird — wie `_satz_vergleichen` nach einem Satz von Hand, an denselben
        Beobachter. Der Zähl-Teil schreibt seine Kontextzeilen selbst (``zaehler``,
        ``zaehlung``). Nur im Diagnosemodus; sonst ``None``. ``uebung_id``: der Kurzcode — die
        Notiz zum Satz, die beim Eintragen folgt, vergleicht dann nicht noch einmal.

        Hier steht auch seine Kontextzeile ``satz`` (wie die Notiz zum Satz sie schriebe), an
        seinem Ende ``bis``: Eingetragen wird erst nach dem Ende der Einheit, die Notiz käme
        hinter „uebung_ende“ — hrv-research zählt die ``satz``-Zeilen nach dem Start der Übung
        (die k-te gehört zu Satz k). **Jeder** Satz bekommt sie, ein nicht eingetragener ohne
        ``feld`` und ``wert`` (hrv-research zählt ihn mit und lässt „eingetragen“ leer): sonst
        rückten die Eingaben danach um einen Satz. Wird er später doch eingetragen („Eintragen“
        der Meldung, `_nachgetragen`), bleibt es bei dieser Zeile — lieber eine Lücke als eine
        zweite, die alle folgenden verschöbe."""
        if not self.diagnose_aktiv or self.mitschnitt is None:
            return None
        marken = sum(
            1 for t, typ, _ in self._diagnose_marken if typ == mt.MARKE_WDH and von <= t <= bis
        )
        vergleich: dict[str, Any] = {
            "uebung": uebung,
            "satz": satz,
            "feld": feld,
            "marken": marken,
            "sensor": sensor,
            "korrektur": int(korrektur),
            "zaehler": sensor,
            "eingetragen": eingetragen,
            "art": "prototyp",
        }
        self.letzter_satz = vergleich
        felder: dict[str, Any] = {"uebung": uebung, "satz": satz}
        if uebung_id:
            felder["uebung_id"] = uebung_id
        if eingetragen is not None:
            felder.update(feld=feld, wert=int(eingetragen))
        with contextlib.suppress(Exception):
            self._satz_zeile(bis, felder)
        wert = int(eingetragen) if eingetragen is not None else max(0, (sensor or 0) + korrektur)
        if wert > 0:  # ein leerer Satz kommt nie ins Tagebuch, also auch keine Notiz
            self._gezaehlt_verglichen.append((uebung_id, wert, vergleich, eingetragen is not None))
        if self._satz_beginn is not None and self._satz_beginn < bis:
            self._satz_beginn = bis  # ein Satz von Hand danach zählt diese Tipps nicht noch einmal
        if self.diagnose_satz_beobachter is not None:
            with contextlib.suppress(Exception):
                self.diagnose_satz_beobachter(vergleich)
        return vergleich

    def zaehlsaetze_vergessen(self, uebung_id: str | None = None) -> None:
        """Die Einheit des Zähl-Teils ist vorbei: Seine Sätze, die nicht eingetragen waren,
        bekommen keine Notiz mehr (ein Nachtrag unter „Läufe heute“ hat keine Marke). Die
        eingetragenen warten auf ihre Notiz (sie kommt nach dem Ende)."""
        for satz in list(self._gezaehlt_verglichen):
            if not satz[3] and (uebung_id is None or satz[0] in (None, uebung_id)):
                self._gezaehlt_verglichen.remove(satz)

    def kontext(self, was: str, **felder: Any) -> dict[str, Any] | None:
        """Kontext in den Mitschnitt: Übung, Timer, eingetragener Satz (Plan §3.1)."""
        if not self.diagnose_aktiv or self.mitschnitt is None:
            return None
        return self.mitschnitt.kontext(was, **felder)

    def diagnose_stand(self) -> dict[str, Any]:
        """Was der Diagnosemodus gerade aufzeichnet — für das Stand-Blatt und die
        Benachrichtigung."""
        schreiber = self.mitschnitt
        transport = self.mitschnitt_transport
        jetzt = self._uhr()
        quelle = self.quelle
        return {
            "aktiv": self.diagnose_aktiv,
            "seit_s": round(jetzt - self.diagnose_seit, 1) if self.diagnose_seit else 0.0,
            "bytes": schreiber.bytes if schreiber is not None else 0,
            "zeilen": schreiber.zeilen if schreiber is not None else 0,
            "schreibfehler": schreiber.fehler if schreiber is not None else 0,
            "stroeme": transport.zaehler.stand(jetzt) if transport is not None else {},
            "seq_luecken": transport.zaehler.seq_luecken if transport is not None else 0,
            "trennungen": transport.zaehler.trennungen if transport is not None else 0,
            "akku": self.status.batterie_prozent,
            "ekg": bool(getattr(quelle, "ekg_modus", False)),
            "acc": bool(getattr(quelle, "acc_modus", False)),
            "verzug_ms": self.verzug_ms,
            "pfad": str(schreiber.pfad) if schreiber is not None else "",
        }

    def _mitschnitt_oeffnen(
        self,
        name: str | None = None,
        *,
        kopf: dict[str, Any] | None = None,
        ekg: bool | None = None,
        acc: tuple[int, int] | None = None,
    ) -> mt.Schreiber | None:
        """Den Schreiber neben dem Backup der laufenden Aufnahme öffnen und anhängen."""
        aufnahme, transport, basis = self.aufnahme, self.mitschnitt_transport, self._backup_basis
        if aufnahme is None or transport is None or basis is None:
            return None
        ordner = self._ordner(basis)
        pfad = mt.journal_pfad(ordner / aufnahme.backup_name())
        quelle = self.quelle
        if ekg is None:
            ekg = bool(getattr(quelle, "ekg_modus", False))
        if acc is None:
            acc = getattr(quelle, "acc_wunsch", None)
        stroeme: dict[str, Any] = {
            "hr": {"merkmal": "0x2A37"},
            "merkmale": sorted(getattr(quelle, "pmd_merkmale", None) or []),
            "einstellungen": dict(getattr(quelle, "pmd_einstellungen", {}) or {}),
        }
        if ekg:
            stroeme["ecg"] = {"rate_hz": 130, "aufloesung_bit": 14}
        if acc is not None:
            stroeme["acc"] = {"rate_hz": acc[0], "bereich_g": acc[1], "aufloesung_bit": 16}
        inhalt: dict[str, Any] = {
            "app": f"trainingsapp {app_version()[0]}",
            "messdatei": aufnahme.dateiname(),
            # Nullpunkt der Messung auf der Uhr der Zeilen (hrv-core 0.6.1): Marken und Pakete
            # liegen damit genau auf t_wall_s der Messdatei
            "aufnahme": {
                "start_mono_ns": round(aufnahme.start_mono * 1e9),
                "start_utc": aufnahme.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "geraet": {
                "name": self.geraet_name,
                "id": self.device_id,
                "profil": self.profil.id if self.profil else "",
            },
            "stroeme": stroeme,
            "dienste": transport.dienste_abbild or sorted(transport.dienste),
            **(kopf or {}),
        }
        if name is not None and name != pfad.name:
            logging.getLogger(__name__).info("Mitschnitt %s folgt auf %s", pfad.name, name)
        try:
            schreiber = mt.Schreiber(pfad, inhalt, uhr_ns=lambda: round(self._uhr() * 1e9))
        except OSError as fehler:
            logging.getLogger(__name__).warning("Mitschnitt nicht angelegt: %s", fehler)
            return None
        transport.anhaengen(schreiber)
        schreiber.kontext("diagnose_start")
        self.mitschnitt = schreiber
        if self.diagnose_seit is None:
            self.diagnose_seit = self._uhr()
        # Endet von selbst, sobald der Schreiber zu ist (auch nach dem Speichern im Thread)
        self._probe_task = asyncio.get_running_loop().create_task(
            self._probe_schleife(schreiber), name="diagnose-probe"
        )
        return schreiber

    def _mitschnitt_schliessen(self, schreiber: mt.Schreiber) -> None:
        transport = self.mitschnitt_transport
        if transport is not None and transport.schreiber is schreiber:
            transport.abhaengen()
        # Beobachter und Puffer der Beschleunigung gehören der Anforderung (`acc_freigeben`):
        # ein laufendes Zählen braucht sie weiter
        self._diagnose_marken.clear()
        self._satz_beginn = None
        self._gezaehlt_verglichen.clear()
        self._satz_zeilen, self._satz_uebung = 0, None
        if self._probe_task is not None:
            self._probe_task.cancel()
            self._probe_task = None
        schreiber.schliessen()

    def _mitschnitt_ablegen(self, schreiber: mt.Schreiber, messdatei: Path) -> None:
        """Nach dem Speichern: schließen und als Beiwerk neben die Messdatei. Liegt dort schon
        einer, bleibt dieser neben dem Backup liegen (nichts wird ersetzt).

        Läuft im Thread des Speicherns (`_schreiben`): nur Dateiarbeit und das Abhängen —
        die Zustandsprobe endet von selbst, sobald der Schreiber zu ist."""
        transport = self.mitschnitt_transport
        if transport is not None and transport.schreiber is schreiber:
            transport.abhaengen()
        schreiber.schliessen()
        with contextlib.suppress(OSError):
            if schreiber.pfad.exists():
                schreiber.umbenennen(mt.mitschnitt_pfad(messdatei))

    def _mitschnitt_verwerfen(self) -> None:
        """Eine Aufnahme ohne Schlag wird nicht gespeichert — ihr Mitschnitt auch nicht."""
        schreiber, self.mitschnitt = self.mitschnitt, None
        self.diagnose_seit = None
        if schreiber is None:
            return
        self._mitschnitt_schliessen(schreiber)
        with contextlib.suppress(OSError):
            schreiber.pfad.unlink(missing_ok=True)

    async def _stroeme_zurueck(self) -> None:
        """Die Zusatzströme wie vor dem Diagnosemodus: EKG zurück, Beschleunigung freigeben —
        was ein anderer Zweck (Zählen) angefordert hat, läuft weiter."""
        vorher, self._diagnose_vorher = self._diagnose_vorher, None
        frei = self._acc_setzen("diagnose", None)
        if vorher is None and not frei:
            return
        if vorher is not None:
            self._ekg_soll = vorher
        await self._abwarten(self._stroeme_anwenden())

    async def _probe_schleife(self, schreiber: mt.Schreiber) -> None:
        """Alle `PROBE_S` eine Zustandsprobe; dazwischen den Verzug der Schleife messen."""
        letzte_probe = time.monotonic()
        while schreiber.offen:
            soll = time.monotonic() + VERZUG_TAKT_S
            await asyncio.sleep(VERZUG_TAKT_S)
            verzug = max(0, round((time.monotonic() - soll) * 1000))
            self.verzug_ms = verzug
            self._verzug_spitze_ms = max(self._verzug_spitze_ms, verzug)
            if time.monotonic() - letzte_probe < PROBE_S:
                continue
            letzte_probe = time.monotonic()
            await self._probe(schreiber)

    async def _probe(self, schreiber: mt.Schreiber) -> None:
        transport = self.mitschnitt_transport
        felder: dict[str, Any] = {
            "akku": self.status.batterie_prozent,
            "verzug_ms": self.verzug_ms,
            "verzug_spitze_ms": self._verzug_spitze_ms,
            "mb": round(schreiber.bytes / 1e6, 2),
        }
        self._verzug_spitze_ms = 0
        if transport is not None:
            felder["pakete"] = {k: int(v["pakete"]) for k, v in transport.zaehler.stand(0).items()}
            akku = getattr(transport.innen, "akku", None)
            if callable(akku):
                with contextlib.suppress(Exception):
                    werte = await asyncio.wait_for(akku(), timeout=5.0)
                    if isinstance(werte, dict):
                        felder["akku_handy"] = werte.get("prozent")
                        felder["laedt"] = werte.get("laedt")
        with contextlib.suppress(Exception):
            schreiber.zeile(mt.PROBE, **felder)

    async def trennen(self) -> None:
        # Ohne Verbindung braucht niemand die Beschleunigung mehr — wer sie wieder will,
        # fordert sie neu an
        self._acc_anforderungen.clear()
        quelle: Any = self.quelle
        if getattr(quelle, "acc_beobachter", None) == self._acc_empfangen:
            quelle.acc_beobachter = None
        self._acc_leeren()
        self._acc_vorher = _UNGESETZT
        await self.quelle.disconnect()
        self.status = replace(self.status, verbindung=Verbindung.GETRENNT)
