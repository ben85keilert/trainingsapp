"""Gerätekatalog.

„Die Liste wird stetig erweitert" heißt hier: **ein Eintrag, kein Umbau.**

Die vier ersten Profile sind deckungsgleich mit `praxis_gui/sensors/devices/profiles.py`,
damit `geraet_profil` in den Messdateien auf beiden Seiten dasselbe bedeutet.
Danach folgen unsere Ergänzungen für Uhren.

**Wie erkannt wird:** zuerst aus dem BLE-Namen raten, dann anhand der Dienste
korrigieren, die das Gerät tatsächlich meldet. Das Gerät zählt mehr als sein Name.

Und weil Herstellerangaben zu RR-Intervallen unzuverlässig sind, entscheidet am
Ende der **Sensor-Prüfstand**: verbinden, zehn Sekunden messen, Flags-Byte
auswerten. Siehe `docs/architektur.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..hrv_core.constants import (
    MALIK_THRESHOLD_EKG,
    MALIK_THRESHOLD_PPI,
    QUALITAET_BPM_ONLY,
    QUALITAET_PPI_OPTISCH,
    QUALITAET_RR_EKG,
    QUELLE_EKG_RR,
    QUELLE_PPG_PPI,
)

# Fähigkeiten
CAP_HR_RR = "hr_rr"  # RR-Intervalle über das Standardprofil
CAP_HR_ONLY = "hr_only"  # nur Herzfrequenz, keine RR
CAP_PMD_ECG = "pmd_ecg"
CAP_PMD_PPI = "pmd_ppi"
CAP_PMD_PPG = "pmd_ppg"
CAP_PMD_ACC = "pmd_acc"


@dataclass(frozen=True, slots=True)
class GeraeteProfil:
    """Was ein Gerät kann und wie die App es behandelt."""

    id: str
    name: str
    kurz: str
    muster: tuple[str, ...]
    intervall_quelle: str
    datenqualitaet: str
    faehigkeiten: frozenset[str]
    ordner: str
    ersttelegramm_s: float = 30.0
    hinweis_kein_signal: str = "Kein Signal — sitzt der Sensor richtig?"
    ausreisser_schwelle: float = MALIK_THRESHOLD_EKG
    #: Verlangt das Gerät eine Bluetooth-Kopplung (Bonding)? Der Verity Sense
    #: schickt direkt nach dem Verbinden eine Sicherheitsanfrage; ohne Kopplung
    #: trennt er nach wenigen Sekunden. `PolarQuelle` ruft dafür
    #: ``BleTransport.bond()`` (Android: ``createBond``). Wie in praxis_gui.
    kopplung_noetig: bool = False
    hinweise: tuple[str, ...] = field(default_factory=tuple)

    def kann(self, *caps: str) -> bool:
        return all(c in self.faehigkeiten for c in caps)

    @property
    def hrv_moeglich(self) -> bool:
        return self.datenqualitaet != QUALITAET_BPM_ONLY


# ---------------------------------------------------------------------------
# Kompatibel zu praxis_gui — IDs dürfen sich nicht ändern
# ---------------------------------------------------------------------------

POLAR_H10 = GeraeteProfil(
    id="polar_h10",
    name="Polar H10",
    kurz="H10",
    muster=("polar h10", "h10"),
    intervall_quelle=QUELLE_EKG_RR,
    datenqualitaet=QUALITAET_RR_EKG,
    faehigkeiten=frozenset({CAP_HR_RR, CAP_PMD_ECG, CAP_PMD_ACC}),
    ordner="PolarH10",
    hinweis_kein_signal=(
        "Gurt anlegen und die Elektroden anfeuchten — ohne Hautkontakt sendet der Gurt gar nichts."
    ),
)

POLAR_H9 = GeraeteProfil(
    id="polar_h9",
    name="Polar H9",
    kurz="H9",
    muster=("polar h9", "h9"),
    intervall_quelle=QUELLE_EKG_RR,
    datenqualitaet=QUALITAET_RR_EKG,
    faehigkeiten=frozenset({CAP_HR_RR}),
    ordner="PolarH9",
    hinweise=("Kein EKG-Rohsignal — der H9 hat keinen PMD-Dienst.",),
)

VERITY_SENSE = GeraeteProfil(
    id="verity_sense",
    name="Polar Verity Sense",
    kurz="Verity",
    muster=("verity", "polar sense"),
    intervall_quelle=QUELLE_PPG_PPI,
    datenqualitaet=QUALITAET_PPI_OPTISCH,
    faehigkeiten=frozenset({CAP_HR_RR, CAP_PMD_PPI, CAP_PMD_PPG, CAP_PMD_ACC}),
    ordner="VeritySense",
    # Der PPI-Algorithmus braucht Anlauf und meldet die Herzfrequenz danach nur
    # alle 5 s — 30 s Wartefrist wären zu knapp, um einen echten Ausfall davon
    # zu unterscheiden.
    ersttelegramm_s=45.0,
    hinweis_kein_signal=(
        "Sitzt das Armband fest genug? Der optische Sensor braucht Hautkontakt ohne Luftspalt."
    ),
    ausreisser_schwelle=MALIK_THRESHOLD_PPI,
    kopplung_noetig=True,
    hinweise=(
        "Puls-zu-Puls-Intervalle sind nicht dasselbe wie RR aus dem EKG: die "
        "Pulswellenlaufzeit schwankt mit Blutdruck und Gefäßtonus.",
        "Bewegung stört das optische Signal deutlich stärker als ein Brustgurt.",
    ),
)

BLE_GENERIC = GeraeteProfil(
    id="ble_generic",
    name="Brustgurt (Standardprofil)",
    kurz="Gurt",
    # Bequemlichkeit für die Vorauswahl, keine Zulassungsliste — jedes Gerät
    # mit RR-Intervallen läuft, auch ohne Eintrag.
    muster=(
        "tickr",
        "wahoo",
        "hrm",
        "coospo",
        "decathlon",
        "kalenji",
        "geonaute",
        "magene",
        "scosche",
    ),
    intervall_quelle=QUELLE_EKG_RR,
    datenqualitaet=QUALITAET_RR_EKG,
    faehigkeiten=frozenset({CAP_HR_RR}),
    ordner="Brustgurt",
    hinweise=("Nur Herzfrequenz und RR-Intervalle — kein Rohsignal.",),
)

# ---------------------------------------------------------------------------
# Unsere Ergänzungen: Uhren
# ---------------------------------------------------------------------------

POLAR_UHR = GeraeteProfil(
    id="polar_watch",
    name="Polar-Uhr (PMD)",
    kurz="Polar-Uhr",
    muster=("polar ignite", "polar pacer", "polar vantage", "polar grit"),
    intervall_quelle=QUELLE_PPG_PPI,
    datenqualitaet=QUALITAET_PPI_OPTISCH,
    faehigkeiten=frozenset({CAP_HR_RR, CAP_PMD_PPI}),
    ordner="VeritySense",  # dieselbe Auswertung wie der optische Sensor
    ersttelegramm_s=45.0,
    ausreisser_schwelle=MALIK_THRESHOLD_PPI,
    hinweise=(
        "Die Uhr muss einmalig für die Datenfreigabe eingerichtet werden: "
        "Polar-Flow-App vollständig beenden, Uhr neu koppeln, dann in den "
        "Uhreinstellungen unter „Koppeln und synchronisieren → Gekoppelte "
        "Geräte → SDK“ die Freigabe erteilen.",
        "Die Messung lässt sich nur aus der Sportprofil-Auswahl heraus starten.",
        "Startet man auf der Uhr ein Training, endet die Übertragung.",
        "Puls-zu-Puls-Intervalle sind nicht dasselbe wie RR aus dem EKG.",
    ),
)

UHR_BROADCAST = GeraeteProfil(
    id="watch_broadcast",
    name="Uhr (Herzfrequenz-Übertragung)",
    kurz="Uhr",
    muster=(
        "garmin",
        "forerunner",
        "fenix",
        "venu",
        "coros",
        "amazfit",
        "suunto",
        "whoop",
        "galaxy watch",
        "instinct",
        "vivoactive",
    ),
    intervall_quelle=QUELLE_PPG_PPI,
    # Vorsichtige Annahme. Der Prüfstand hebt auf `ppi_optisch` hoch, sobald
    # tatsächlich RR-Intervalle ankommen.
    datenqualitaet=QUALITAET_BPM_ONLY,
    faehigkeiten=frozenset({CAP_HR_ONLY}),
    ordner="Uhr",
    ausreisser_schwelle=MALIK_THRESHOLD_PPI,
    hinweise=(
        "Ob eine Uhr Schlag-zu-Schlag-Intervalle mitsendet, ist von Modell und "
        "Firmware abhängig und nirgends verlässlich dokumentiert. Der "
        "Sensor-Prüfstand misst es.",
        "Garmin-Uhren senden nach heutigem Stand nur die Herzfrequenz — für "
        "eine HRV-Auswertung wird ein Brustgurt gebraucht.",
        "Bei den meisten Uhren muss die Übertragung erst im Menü eingeschaltet "
        "werden, oft „HF übertragen“ oder „Broadcast Heart Rate“.",
    ),
)

#: Prüfreihenfolge: spezifische Muster zuerst, Auffangfall zuletzt.
PROFILE: tuple[GeraeteProfil, ...] = (
    POLAR_H10,
    POLAR_H9,
    VERITY_SENSE,
    POLAR_UHR,
    UHR_BROADCAST,
    BLE_GENERIC,
)
DEFAULT_PROFIL = BLE_GENERIC

_NACH_ID = {p.id: p for p in PROFILE}


def profil_nach_id(profil_id: str) -> GeraeteProfil:
    return _NACH_ID.get(profil_id, DEFAULT_PROFIL)


def profil_fuer_namen(name: str) -> GeraeteProfil:
    """Rät das Profil aus dem BLE-Gerätenamen.

    >>> profil_fuer_namen("Polar H10 A1B2C3").id
    'polar_h10'
    >>> profil_fuer_namen("Polar H10 ABC123").id
    'polar_h10'
    >>> profil_fuer_namen("Polar Sense ABC123").id    # so meldet sich der Verity Sense
    'verity_sense'
    >>> profil_fuer_namen("Polar Verity Sense 1A2B3C4D").kopplung_noetig
    True
    >>> profil_fuer_namen("Forerunner 955").id
    'watch_broadcast'
    >>> profil_fuer_namen("Irgendein Gurt").id
    'ble_generic'
    """
    klein = (name or "").lower()
    for profil in PROFILE:
        if any(m in klein for m in profil.muster):
            return profil
    return DEFAULT_PROFIL


def profil_verfeinern(profil: GeraeteProfil, *, rr_gesehen: bool) -> GeraeteProfil:
    """Korrigiert die Einstufung anhand dessen, was tatsächlich ankommt.

    Der Sensor-Prüfstand ruft das nach der Messphase auf. Eine Uhr, die
    entgegen der Erwartung RR-Intervalle sendet, wird damit HRV-fähig — und
    eine, die keine sendet, wird ehrlich auf ``bpm_only`` zurückgestuft.

    >>> profil_verfeinern(UHR_BROADCAST, rr_gesehen=True).datenqualitaet
    'ppi_optisch'
    >>> profil_verfeinern(POLAR_H10, rr_gesehen=False).datenqualitaet
    'bpm_only'
    """
    if rr_gesehen and profil.datenqualitaet == QUALITAET_BPM_ONLY:
        neue = (
            QUALITAET_RR_EKG if profil.intervall_quelle == QUELLE_EKG_RR else QUALITAET_PPI_OPTISCH
        )
        return _mit_qualitaet(profil, neue, {CAP_HR_RR})
    if not rr_gesehen and profil.datenqualitaet != QUALITAET_BPM_ONLY:
        return _mit_qualitaet(profil, QUALITAET_BPM_ONLY, {CAP_HR_ONLY})
    return profil


def _mit_qualitaet(profil: GeraeteProfil, qualitaet: str, zusatz_caps: set[str]) -> GeraeteProfil:
    from dataclasses import replace

    return replace(
        profil,
        datenqualitaet=qualitaet,
        faehigkeiten=frozenset(profil.faehigkeiten | zusatz_caps),
    )


__all__ = [
    "BLE_GENERIC",
    "CAP_HR_ONLY",
    "CAP_HR_RR",
    "CAP_PMD_ACC",
    "CAP_PMD_ECG",
    "CAP_PMD_PPG",
    "CAP_PMD_PPI",
    "DEFAULT_PROFIL",
    "POLAR_H9",
    "POLAR_H10",
    "POLAR_UHR",
    "PROFILE",
    "UHR_BROADCAST",
    "VERITY_SENSE",
    "GeraeteProfil",
    "profil_fuer_namen",
    "profil_nach_id",
    "profil_verfeinern",
]
