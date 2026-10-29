"""Reiter „Messung": oben „Live", „GPS" und „Aufzeichnungen" (Symbol neben dem Text,
damit die Zeile flach bleibt — Ben, 21.10.2026).

**Live.** Ohne Verbindung: Gerät suchen (oder den Simulator nehmen). Mit
Verbindung, von oben nach unten:

1. Status — Gerät, Akku und der Aufnahmeknopf, damit man nicht erst scrollen muss;
   darunter Titel und Beschreibung, schon vor dem Start (Ben, 17.10.2026).
2. Kacheln — welche, stellt man unter Einstellungen → HRV-Messung ein.
3. Eine Karte für die Kurven (Ben, 21.10.2026: Hauptkurve und Verlaufskurven dicht
   beieinander): Fensterbreite, Bereich Zeit ↔ Frequenz ↔ Nichtlinear und die Chips
   der Verlaufskurven, „korrigiert", dann die Hauptkurve (RR- bzw. PPI-Tachogramm),
   direkt darunter die Notizen, darunter Spektrum bzw. Poincaré und die
   Verlaufskurven (`components.analyse`, eingebettet). Sendet das Gerät nur die
   Herzfrequenz (Uhren im Übertragungsmodus — im Geräteprofil hinterlegt, sonst
   erkannt), ist die Hauptkurve der Puls in bpm (`nur_puls`, Ben 17.10.2026).

**Knöpfe an der Kurve wie in der Aufzeichnung** (Ben, 21.10.2026): Ablesen, Vollbild,
Fenster & Darstellung (Zeitachse eintippen, feste Werteachsen) und das Menü ⋮ mit
Info („So liest du die Kurven“), automatischer Korrektur und den Ansichten. Ablesen
hält die Kurve an wie im Vollbild; „Live“ läuft wieder mit und beendet es.

Das Verbindungsprotokoll (Diagnose) öffnet ein Knopf in der Gerätezeile oben.

Die laufende Messung liegt im `AppState` (`state.messlauf`), nicht in dieser
Ansicht — sonst risse sie bei jedem Reiterwechsel ab (L03). Die Ansicht
schaut nur zu: `Messlauf` meldet neue Werte über einen Beobachter, und die
Ansicht frischt Kacheln und Kurven auf (höchstens zweimal je Sekunde).

Live wird nichts an den Rohdaten verändert. Artefakte werden markiert (rote
Punkte), die korrigierte Kurve ist eine Anzeige; gespeichert werden immer
die Rohwerte. Korrigiert wird nachträglich in der Aufzeichnung.

**GPS.** Das Ausdauertraining selbst (`views.ausdauer.ausdauer_inhalt`): Sportart,
GPS an/aus, „Training starten“ — und läuft eines, seine Zahlen und die Karte. Bis
26.10.2026 stand hier nur ein Knopf, der erst zur Seite `/ausdauer` führte (Ben: „Diesen
Zwischenschritt nimm bitte heraus“). Der Bereich wird noch umgebaut (Katalog A17: Tempo
entlang der Strecke, eingefärbte Kurvenabschnitte, Kurve Strecke/Zeit gegen HF).

**Aufzeichnungen.** Zwei Unterreiter: „Strecken" (die Trainings, `strecken_zeilen`) und
„HRV" (die gespeicherten Messungen des Profils, neueste zuerst, „Alle exportieren").
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz
from hrv_core.aufnahme import backup_lesen
from hrv_core.ausschnitte import FARBEN as ABSCHNITT_FARBEN
from hrv_core.regeln import Korrekturregeln
from hrv_core.trends import KENNZAHLEN

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.hf_profil import bereiche_fuer, grenzen_bpm
from trainingsapp.core.hf_training import (
    BEZUG_ABSCHNITT,
    BEZUG_AUFNAHME,
    BEZUG_FENSTER,
    BEZUG_NAMEN,
    LiveHf,
    fenster_zusammenfassung,
    hf_je_schlag,
)
from trainingsapp.core.hrv_ansicht import HF_SPANNE_MIN_BPM, ROH, ROH_MAX_MS, ROH_MIN_MS
from trainingsapp.core.hrv_einstellungen import SICHT_HF, SICHT_HRV
from trainingsapp.core.hrv_export import adresse_maskieren, export_zip, zugehoerige_dateien
from trainingsapp.core.laufend import minuten
from trainingsapp.core.models import HrvRecording
from trainingsapp.core.models import jetzt as utc_jetzt
from trainingsapp.core.timer import (
    MESSDAUERN_MIN,
    TimerLauf,
    TimerProfil,
    dauer_text,
    ende_frage,
    messdauer,
)
from trainingsapp.core.zeitangabe import DAUER, UHR
from trainingsapp.data.hf_profil import RechenAusnahmeRepo
from trainingsapp.devices.base import DeviceInfo, Verbindung
from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein, TimerBaustein
from trainingsapp.devices.gatt import adapter_warnung
from trainingsapp.devices.messlauf import NUR_PULS_NACH as NUR_PULS_NACH  # Re-Export (H40)
from trainingsapp.devices.messlauf import (
    Gespeichert,
    Messlauf,
    backup_wiederherstellen,
)
from trainingsapp.devices.profiles import geraeteart
from trainingsapp.devices.simulated import (
    SIM_PPI,
    SIM_PREFIX,
    SIM_PULS,
    SIM_SYNTH,
    SimulatedSource,
)
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import ziele_liste
from trainingsapp.ui.components.analyse import Analyse
from trainingsapp.ui.components.dialoge import Erledigt, reste_dialog, schliessen
from trainingsapp.ui.components.hf_sicht import (
    EINSTELLUNGEN as HF_EINSTELLUNGEN,
)
from trainingsapp.ui.components.hf_sicht import (
    HF_INFO,
    bezug_wahl,
    erholung_block,
    hf_kacheln,
    hf_kopf,
    sicht_wahl,
    skala,
    zeit_je_bereich,
)
from trainingsapp.ui.components.kacheln import (
    HF_KACHELN,
    anzeige,
    kachel_werte,
)
from trainingsapp.ui.components.karte import info_eintrag, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_eintrag
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.live_abschnitte import LiveAbschnitte
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.strecken_export import strecken_export_fragen
from trainingsapp.ui.components.titel import (
    geuebte_plaene,
    titel_blatt,
    titel_kopf,
    titel_vorschlaege,
)
from trainingsapp.ui.components.verlauf import (
    FARBEN,
    Zeitachse,
    darstellung_blatt,
    darstellung_knopf,
    kurvengruppen,
)
from trainingsapp.ui.components.vollbild import (
    Ablesewert,
    ablese_karte,
    geraet_wert,
    intervall_werte,
    kennzahl_werte,
    markieren,
    werteachsen,
)
from trainingsapp.ui.components.vollbild import achse as werteachse
from trainingsapp.ui.components.weitergeben import weitergeben, zeitstempel
from trainingsapp.ui.components.zeitachse import achse, achsen_knopf
from trainingsapp.ui.components.zeitfenster import (
    Fenster,
    breiten_auswahl,
    breiten_wahl,
    wischbar,
)
from trainingsapp.ui.state import AppState
from trainingsapp.ui.training import bewegung_packen, bewegung_vorbereiten


def _protokoll(lauf: Messlauf, zeilen: int = 20) -> list[str]:
    """Die letzten Diagnosezeilen der Quelle (PolarQuelle führt sie mit)."""
    return list(getattr(lauf.quelle, "protokoll", []))[-zeilen:]


def diagnose_blatt(page: ft.Page, lauf: Messlauf) -> ft.BottomSheet:
    """Das Verbindungsprotokoll — die letzten Zeilen zum Ansehen, das ganze zum Teilen.

    Ein Blatt hinter einem Knopf in der Gerätezeile (Ben, 17.10.2026: stand vorher als
    Klappfeld ganz unten in der Ansicht).
    """
    zeilen = _protokoll(lauf, 40)

    async def teilen() -> None:
        # Verlässt das Gerät — darum ohne Bluetooth-Adresse, wie die Exportkopie (S10)
        text = adresse_maskieren(lauf.diagnose())
        if not text:
            page.show_dialog(ft.SnackBar(ft.Text("Noch keine Einträge im Protokoll.")))
            return
        await weitergeben(page, f"diagnose_{zeitstempel()}.txt", text.encode("utf-8"), "text/plain")

    return ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        content=ft.Container(
            padding=ft.Padding.only(left=16, right=16, bottom=20),
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    ft.Text("Diagnose", size=17, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"{lauf.geraet_name or 'Gerät'} — die letzten Zeilen des "
                        "Verbindungsprotokolls. Teilen schickt das ganze Protokoll.",
                        size=12,
                        opacity=0.7,
                    ),
                    ft.Text(
                        "\n".join(zeilen) or "noch keine Einträge",
                        size=11,
                        selectable=True,
                        font_family="monospace",
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Protokoll teilen", icon=ft.Icons.SHARE, on_click=teilen)
                        ],
                    ),
                ],
            ),
        ),
    )


def diagnose_knopf(page: ft.Page, lauf: Messlauf) -> ft.Control:
    """Unauffälliger Knopf zum Verbindungsprotokoll — der Simulator führt keines."""
    return ft.IconButton(
        ft.Icons.RECEIPT_LONG_OUTLINED,
        icon_size=20,
        tooltip="Diagnose: Verbindungsprotokoll",
        visible=not lauf.simulation,
        on_click=lambda: page.show_dialog(diagnose_blatt(page, lauf)),
    )


async def _hintergrund(state: AppState, lauf: Messlauf, an: bool, text: str = "") -> None:
    """Vordergrunddienst an/aus — nur in der Android-App (über `FletBleTransport`).

    Solange er läuft, misst und zeichnet die App auch bei ausgeschaltetem
    Display oder in einer anderen App weiter. Ein Fehler stoppt die Messung
    nicht; er landet im Diagnoseprotokoll.
    """
    transport = state.ble_transport
    if transport is None or not hasattr(transport, "hintergrund"):
        return
    fehler = await transport.hintergrund(an, "HRV-Messung läuft", text)
    protokoll = getattr(lauf.quelle, "protokoll", None)
    if protokoll is not None:
        zeile = f"Hintergrunddienst {'gestartet' if an else 'beendet'}"
        protokoll.append(
            f"{time.strftime('%H:%M:%S')} " + (f"{zeile} — FEHLER: {fehler}" if fehler else zeile)
        )


#: Eine Schreibweise für alle Zeiten (N26)
_uhr = minuten


def tachogramm(
    lauf: Messlauf,
    x_von: float,
    x_bis: float,
    *,
    korrigiert: bool,
    verity: bool,
    marken: list[Reihe] = (),  # type: ignore[assignment]
    hoehe: int = 180,
    x_text: Callable[[float], str] | None = None,
    x_null: float = 0.0,
    y_fest: tuple[float, float] | None = None,
) -> ft.Control:
    """Die Live-Hauptkurve: Rohwerte grau, gewertet farbig, Artefakte rot, dazu ``marken``.
    ``x_text``/``x_null``: Beschriftung der Zeitachse (`kurve`); ``y_fest``: feste
    Werteachse (`Ansicht.y_achsen`)."""
    return kurve(
        [*tachogramm_reihen(lauf, x_von, x_bis, korrigiert=korrigiert), *marken],
        einheit="PPI ms" if verity else "RR ms",
        hoehe=hoehe,
        x_von=x_von,
        x_bis=x_bis,
        y_spanne_min=RR_SPANNE_MIN_MS,
        x_text=x_text,
        x_null=x_null,
        y_fest=y_fest,
    )


def tachogramm_reihen(
    lauf: Messlauf, x_von: float, x_bis: float, *, korrigiert: bool
) -> list[Reihe]:
    """Die Reihen des Live-Tachogramms im Ausschnitt — auch fürs Vollbild (`live_vollbild`)."""
    punkte = [p for p in lauf.live.punkte(seit_s=x_von) if p.t_s <= x_bis]
    mit_rr = [p for p in punkte if p.rr_ms > 0]
    # Grau: alles, was der Sensor geliefert hat — auch vom Gerät verworfene
    # Intervalle; so bleibt die Kurve durchgehend (Verity Sense).
    grau: list[tuple[float, float]] = []
    grau_naehte: list[int] = []
    rr_linie: list[tuple[float, float]] = []
    rr_naehte: list[int] = []  # davor verworfen oder Lücke: Linie reißt ab
    offen = False
    for p in mit_rr:
        if p.naht_davor and grau:
            grau_naehte.append(len(grau))
        if ROH_MIN_MS < p.rr_ms < ROH_MAX_MS:
            grau.append((p.t_s, float(p.rr_ms)))
        wert = p.rr_korr if korrigiert else float(p.rr_ms)
        if p.verworfen or wert is None:
            offen = True
            continue
        if (offen or p.naht_davor) and rr_linie:
            rr_naehte.append(len(rr_linie))
        offen = False
        rr_linie.append((p.t_s, wert))
    artefakte = [
        (p.t_s, float(p.rr_ms)) for p in mit_rr if p.artefakt and ROH_MIN_MS < p.rr_ms < ROH_MAX_MS
    ]
    return [
        Reihe(grau, farbe=ft.Colors.OUTLINE, breite=1, naehte=grau_naehte, skala=False),
        Reihe(rr_linie, farbe=ft.Colors.PRIMARY, naehte=rr_naehte),
        Reihe(artefakte, farbe=FARBEN["rot"], nur_punkte=True, skala=False),
    ]


# -- Ablesen live: hochkant und im Vollbild dasselbe (Ben, 21.10.2026) -------------------


def _schlaege_um(lauf: Messlauf, x: float) -> list[float]:
    return [p.t_s for p in lauf.live.punkte(seit_s=x - 10) if p.rr_ms > 0 and p.t_s <= x + 10]


def schlag_bei_live(lauf: Messlauf, x: float) -> float:
    """Der Schlag, der ``x`` am nächsten liegt — dort steht der Ablesestrich."""
    zeiten = _schlaege_um(lauf, x)
    return min(zeiten, key=lambda t: abs(t - x)) if zeiten else x


def strich_anfang_live(lauf: Messlauf, x_von: float, x_bis: float) -> float:
    """Wo der Strich beim Einschalten steht: mitten in den Daten des Ausschnitts — am
    Anfang einer Messung reicht das Fenster weiter als die Daten."""
    return schlag_bei_live(lauf, (max(x_von, 0.0) + min(x_bis, lauf.jetzt_s())) / 2)


def schlag_weiter_live(lauf: Messlauf, x: float, richtung: int) -> float:
    """Der nächste Schlag vor (``richtung`` 1) bzw. hinter ``x`` — ohne einen: ``x``."""
    weiter = [t for t in _schlaege_um(lauf, x) if (t - x) * richtung > 1e-6]
    return min(weiter, key=lambda t: abs(t - x)) if weiter else x


def ablese_werte_live(
    lauf: Messlauf,
    x: float,
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]],
    *,
    korrigiert: bool,
    verity: bool,
) -> list[Ablesewert]:
    """RR bzw. PPI am Strich (korrigiert, wenn die Kurve es zeigt), HF, HF Gerät und die
    gezeichneten Verlaufskurven (``gesehen``)."""
    punkte = [p for p in lauf.live.punkte(seit_s=x - 3) if p.rr_ms > 0 and p.t_s <= x + 3]
    p = min(punkte, key=lambda q: abs(q.t_s - x), default=None)
    rr = zusatz = None
    if p is not None:
        rr = p.rr_korr if korrigiert and p.rr_korr else float(p.rr_ms)
        zusatz = " (verworfen)" if p.verworfen else " (auffällig)" if p.artefakt else ""
    return (
        intervall_werte(rr, zusatz or "", verity=verity)
        + geraet_wert(lauf.live.hf_reihe(), x)
        # hf_geraet steht schon da, aus dem Gerät
        + kennzahl_werte(gesehen, x, ohne=("hf_geraet",))
    )


def ablese_kopf_live(lauf: Messlauf, x: float) -> str:
    """„2:15 · 14:03:05 Uhr“ — die Stelle des Strichs, mit Uhrzeit, wenn es eine gibt."""
    zb = lauf.notiz_zeitbezug()
    uhr = zb.uhr(zb.anker(x)) if zb is not None else ""
    return _uhr(x) + (f" · {uhr} Uhr" if uhr else "")


def ohne_rr() -> list[str]:
    """Bei einem reinen Pulsgeber lässt sich aus RR nichts rechnen — nur „HF Gerät"."""
    return [k for k in KENNZAHLEN if k != "hf_geraet"]


def nur_puls(lauf: Messlauf) -> bool:
    """Sendet das Gerät nur die Herzfrequenz? Entscheidet der Messlauf (`Messlauf.nur_puls`,
    H40) — die Ansicht fragt nur."""
    return lauf.nur_puls()


def pulskurve(
    lauf: Messlauf,
    x_von: float,
    x_bis: float,
    *,
    marken: list[Reihe] = (),  # type: ignore[assignment]
    hoehe: int = 180,
    x_text: Callable[[float], str] | None = None,
    x_null: float = 0.0,
    y_fest: tuple[float, float] | None = None,
) -> ft.Control:
    """Die Hauptkurve eines reinen Pulsgebers: die Herzfrequenz des Geräts in bpm."""
    punkte = [(t, h) for t, h in lauf.live.hf_reihe() if x_von <= t <= x_bis]
    return kurve(
        [Reihe(punkte, farbe=ft.Colors.PRIMARY), *marken],
        einheit="HF bpm",
        hoehe=hoehe,
        x_von=x_von,
        x_bis=x_bis,
        y_spanne_min=HF_SPANNE_MIN_BPM,
        x_text=x_text,
        x_null=x_null,
        y_fest=y_fest,
    )


#: Hinter dem „i“ im Kartentitel (Ben, 17.10.2026: vorher grauer Text unter den Notizen)
TACHOGRAMM_INFO = """\
- **Grau:** alle Rohwerte, auch vom Sensor verworfene
- **Farbig:** gewertet
- **Rote Punkte:** Artefakte — markiert, nicht verändert
- **Gelb:** Notizen

Waagrecht wischen blättert zurück. Gespeichert werden immer die Rohwerte; korrigiert
wird in der Aufzeichnung.

Titel, Beschreibung und Notizen lassen sich schon vor dem Start eintragen.
„Aufnahme starten“ beginnt die Kurven neu.
"""

PULS_INFO = """\
Dieses Gerät sendet nur die **Herzfrequenz** (bpm), keine Abstände von Schlag zu
Schlag. Darum zeigt die Kurve den Puls, und HRV-Werte gibt es nicht.

Welche Geräte das sind, steht im Geräteprofil — etwa Uhren, die ihre Herzfrequenz
übertragen. Kommt doch ein Intervall an, wird die Kurve zum Tachogramm.

- **Gelb:** Notizen

Waagrecht wischen blättert zurück. Titel, Beschreibung und Notizen lassen sich schon
vor dem Start eintragen; „Aufnahme starten“ beginnt die Kurve neu.
"""


# ---------------------------------------------------------------------------
# Verbinden
# ---------------------------------------------------------------------------


def aufnahme_eintragen(
    state: AppState, ergebnis: Gespeichert, subject_id: str | None = None
) -> HrvRecording:
    """Eine gespeicherte Aufnahme in die Liste eintragen — auch fürs Ausdauertraining.

    ``subject_id``: das Profil beim **Start** der Messung (`Messlauf.subject_id`);
    ohne Angabe das gerade aktive."""
    eintrag = HrvRecording(
        subject_id=subject_id or state.profil.id,
        file_path=ergebnis.pfad.relative_to(messungenverzeichnis()).as_posix(),
        sha1=ergebnis.sha1,
        geraet=ergebnis.recording.geraet,
        geraet_profil=ergebnis.recording.geraet_profil or "ble_generic",
        intervall_quelle=ergebnis.recording.intervall_quelle or "ekg_rr",
        datenqualitaet=ergebnis.recording.effektive_qualitaet(),
        started_at=ergebnis.started_at,
        duration_s=ergebnis.dauer_s,
        coverage_pct=ergebnis.abdeckung_pct,
        n_gaps=ergebnis.n_luecken,
        note=ergebnis.recording.notiz,
        title=ergebnis.recording.titel,
    )
    state.hrv.anlegen(eintrag)
    state.hrv.titel_merken(eintrag.subject_id, eintrag.title)
    return eintrag


# ---------------------------------------------------------------------------
# Liegengebliebene Crash-Backups (Akku leer, Absturz während der Aufnahme)
# ---------------------------------------------------------------------------


def backup_uebernehmen(state: AppState, pfad: Path) -> HrvRecording | None:
    """Ein Crash-Backup als Messung nachtragen (Ben, 15.10.2026: Akku während einer
    4-h-Aufnahme leer, Messung weg). Die Messdatei entsteht neben dem Backup
    (`devices.messlauf.backup_wiederherstellen`), der Eintrag gehört dem Profil beim
    Start, falls es das noch gibt — sonst dem aktiven. ``None``: nichts eingetragen
    (Backup ohne Schlag, oder die Messung stand schon in der Liste)."""
    return backup_eintragen(state, pfad, backup_wiederherstellen(pfad))


def backup_eintragen(
    state: AppState, pfad: Path, ergebnis: Gespeichert | None
) -> HrvRecording | None:
    """Der Datenbankteil von `backup_uebernehmen` — im Thread der Oberfläche (SQLite).

    Das Schreiben der Messdatei (`backup_wiederherstellen`) darf vorher in einem
    eigenen Thread laufen; hier wird nur noch eingetragen.
    """
    state.hrv_backups = [p for p in state.hrv_backups if p != pfad]
    if ergebnis is None:
        return None
    file_path = ergebnis.pfad.relative_to(messungenverzeichnis()).as_posix()
    if file_path in state.hrv.dateipfade():
        return None  # Speichern lief durch, nur das Backup blieb liegen
    subject_id = ergebnis.subject_id
    if not subject_id or state.profile.laden(subject_id) is None:
        subject_id = state.profil.id
    return aufnahme_eintragen(state, ergebnis, subject_id)


def _backup_beschriftung(pfad: Path) -> str:
    """„Polar H10 vom 15.10.2026 08:00, 3 h 58 min" — aus dem Kopf, zur Not aus dem Namen."""
    try:
        rec, _ = backup_lesen(pfad)
    except (OSError, ValueError):
        return pfad.name
    geraet = rec.geraet or "Messung"
    wann = rec.start_utc.astimezone().strftime("%d.%m.%Y %H:%M") if rec.start_utc else "?"
    minuten = int(rec.dauer_s // 60)
    dauer = f"{minuten // 60} h {minuten % 60} min" if minuten >= 60 else f"{minuten} min"
    return f"{geraet} vom {wann}, {dauer}"


def backup_dialog(page: ft.Page, state: AppState) -> ft.AlertDialog:
    """Beim Start: je Backup „Wiederherstellen" oder „Löschen", unten „Später".

    Der Ablauf steckt in `components.dialoge.reste_dialog` (gemeinsam mit
    `views.ausdauer.verwaiste_dialog`). Wiederherstellen schreibt die Messdatei in
    einem eigenen Thread — eine 4-h-Aufnahme braucht am Handy ein paar Sekunden —,
    erst der Eintrag in die Datenbank läuft hier. Nach dem letzten Wiederherstellen
    öffnet sich die Messung, sobald der Dialog zu ist.
    """

    async def wiederherstellen(pfad: Path) -> Erledigt:
        try:
            ergebnis = await asyncio.to_thread(backup_wiederherstellen, pfad)
        except FileNotFoundError:  # schon erledigt — kein Fehler, nur nichts mehr zu tun
            state.hrv_backups = [p for p in state.hrv_backups if p != pfad]
            return Erledigt("Die Sicherung war schon weg.")
        eintrag = backup_eintragen(state, pfad, ergebnis)
        if eintrag is None:
            return Erledigt("Sicherung war leer oder die Messung stand schon in der Liste.")
        return Erledigt("Messung wiederhergestellt.", f"/messung/{eintrag.id}")

    def loeschen(pfad: Path) -> Erledigt:
        pfad.unlink(missing_ok=True)
        state.hrv_backups = [p for p in state.hrv_backups if p != pfad]
        return Erledigt("Sicherung gelöscht.")

    return reste_dialog(
        page,
        titel="Unvollständige Messung gefunden",
        text="Die App wurde während einer Messung beendet (Akku leer, Absturz). "
        "Die Sicherung liegt noch auf dem Handy — als Messung wiederherstellen "
        "oder löschen?",
        offen=lambda: list(state.hrv_backups),
        beschriftung=_backup_beschriftung,
        knopf="Wiederherstellen",
        uebernehmen=wiederherstellen,
        loeschen=loeschen,
    )


def _verbinden_teil(page: ft.Page, state: AppState) -> ft.Control:
    ergebnisse = ft.Column(spacing=0, visible=False)
    bekannte = ft.Column(spacing=0)
    hinweis_text = ft.Text("", size=12, opacity=0.7, visible=False)
    ring = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)

    def zeile(info: DeviceInfo) -> ft.Control:
        # Ehrlich: „Brustgurt" nur, wenn Name oder Profil es sicher sagen
        teile = [geraeteart(info.name, info.profil_id)]
        if info.rssi is not None:
            teile.append(f"{info.rssi} dBm")
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.BLUETOOTH),
            title=ft.Text(info.name or info.id),
            subtitle=ft.Text("  ·  ".join(teile), size=12),
            trailing=ft.FilledTonalButton("Verbinden", on_click=verbinder(info)),
        )

    def bekannte_zeichnen() -> None:
        """„Zuletzt verbunden" — ein Tipp verbindet direkt, ohne Suche."""
        geraete = state.bekannte_geraete()
        bekannte.controls = []
        if geraete:
            bekannte.controls.append(ft.Text("Zuletzt verbunden", size=12, opacity=0.75))
        for g in geraete:
            teile = [geraeteart(g.name, g.profil_id)]
            if g.zuletzt_text():
                teile.append(f"zuletzt {g.zuletzt_text()}")
            bekannte.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.BLUETOOTH_CONNECTED),
                    title=ft.Text(g.name),
                    subtitle=ft.Text("  ·  ".join(teile), size=12),
                    on_click=bekannt_verbinder(g.id, g.name),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="Aus der Liste nehmen",
                        on_click=vergesser(g.id),
                    ),
                    content_padding=ft.Padding.only(left=0, right=0),
                )
            )

    def bekannt_verbinder(geraet_id: str, name: str) -> Callable[[], Any]:
        async def handler() -> None:
            await verbinden(geraet_id, name)

        return handler

    def vergesser(geraet_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.geraet_vergessen(geraet_id)
            bekannte_zeichnen()
            page.update()

        return handler

    def verbinder(info: DeviceInfo) -> Callable[[], Any]:
        async def handler() -> None:
            await verbinden(info.id, info.name)

        return handler

    async def bluetooth_warnung() -> str | None:
        """Ist der Adapter aus, ohne Berechtigung oder nicht da? Dann die Warnung statt
        einer Suche ins Leere (Ben, 28.10.2026)."""
        pruefen = getattr(state.ble_transport, "adapter_zustand", None)
        if pruefen is None:
            return None
        return adapter_warnung(await pruefen())

    def warnen(text: str) -> None:
        ring.visible = False
        hinweis_text.value = text
        hinweis_text.visible = True
        page.show_dialog(ft.SnackBar(ft.Text(text)))
        page.update()

    async def verbinden(device_id: str, name: str | None) -> None:
        hinweis_text.value = f"Verbinde mit {name or device_id} …"
        hinweis_text.visible = True
        ring.visible = True
        page.update()
        if device_id.startswith(SIM_PREFIX):
            quelle: Any = SimulatedSource()
        elif state.ble_transport is not None:
            from trainingsapp.devices.polar import PolarQuelle

            if (warnung := await bluetooth_warnung()) is not None:
                warnen(warnung)
                return
            quelle = PolarQuelle(state.ble_transport)
        else:
            ring.visible = False
            hinweis_text.value = "Bluetooth gibt es nur in der App auf dem Handy."
            page.update()
            return
        lauf = Messlauf(
            quelle,
            backup_basis=datenverzeichnis(),
            regeln=state.korrekturregeln(),
            subject_id=state.profil.id,
            puffer_s=state.hrv_einstellungen().puffer_s,
        )
        state.messlauf = lauf
        try:
            await lauf.verbinden(device_id, name)
        except Exception as fehler:  # Gerät weg, Bluetooth aus, Berechtigung fehlt …
            state.messlauf = None
            ring.visible = False
            hinweis_text.value = (
                f"Verbinden fehlgeschlagen: {fehler}. Ist das Gerät an und in der Nähe? "
                "Sonst hilft „Geräte suchen“."
            )
            diagnose.content = ft.TextButton(
                "Diagnose ansehen",
                icon=ft.Icons.RECEIPT_LONG_OUTLINED,
                on_click=lambda: page.show_dialog(diagnose_blatt(page, lauf)),
            )
            diagnose.visible = True
            page.update()
            return
        if not device_id.startswith(SIM_PREFIX):
            state.geraet_merken(device_id, name or device_id, lauf.profil.id if lauf.profil else "")
        await _hintergrund(state, lauf, True, f"Verbunden mit {lauf.geraet_name}")

        async def laufen() -> None:
            try:
                await lauf.laufen()
            finally:
                await _hintergrund(state, lauf, False)

        page.run_task(laufen)
        state.neu_zeichnen()

    async def suchen() -> None:
        if state.ble_transport is None:
            hinweis_text.value = (
                "Bluetooth gibt es nur in der App auf dem Handy. "
                "Am Rechner zeigt der Simulator, wie es aussieht."
            )
            hinweis_text.visible = True
            page.update()
            return
        from trainingsapp.devices.polar import PolarQuelle

        if (warnung := await bluetooth_warnung()) is not None:
            warnen(warnung)
            return
        ring.visible = True
        hinweis_text.value = "Suche Geräte (8 s) — Gurt anfeuchten bzw. Sensor einschalten …"
        hinweis_text.visible = True
        ergebnisse.controls = []
        page.update()
        try:
            gefunden = await PolarQuelle(state.ble_transport).scan(8.0)
        except Exception as fehler:
            gefunden = []
            hinweis_text.value = f"Suche fehlgeschlagen: {fehler}"
        else:
            hinweis_text.value = (
                f"{len(gefunden)} Gerät(e) gefunden."
                if gefunden
                else "Nichts gefunden. Ist Bluetooth an und der Sensor in der Nähe?"
            )
        ring.visible = False
        ergebnisse.controls = [zeile(i) for i in gefunden]
        ergebnisse.visible = bool(gefunden)
        page.update()

    def simulator(device_id: str, name: str) -> Callable[[], Any]:
        async def handler() -> None:
            await verbinden(device_id, name)

        return handler

    diagnose = ft.Container(visible=False)
    bekannte_zeichnen()

    return ft.Column(
        spacing=12,
        controls=[
            karte(
                ft.Text("Gerät verbinden", size=18, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Polar H10 (Brustgurt, RR-Intervalle), Polar Verity Sense "
                    "(optisch, Pulsintervalle) oder eine Uhr, die ihren Puls überträgt "
                    "(nur Herzfrequenz). Den Gurt vorher anfeuchten.",
                    size=12,
                    opacity=0.7,
                ),
                bekannte,
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.FilledButton("Geräte suchen", icon=ft.Icons.SEARCH, on_click=suchen),
                        ring,
                    ],
                ),
                hinweis_text,
                ergebnisse,
                diagnose,
            ),
            karte(
                kartentitel("Ohne Gerät ausprobieren"),
                ft.Row(
                    wrap=True,
                    spacing=4,
                    controls=[
                        ft.TextButton(
                            "Simulator wie H10",
                            icon=ft.Icons.SCIENCE,
                            on_click=simulator(SIM_SYNTH, "Simulator H10"),
                        ),
                        ft.TextButton(
                            "Simulator wie Verity",
                            icon=ft.Icons.SCIENCE_OUTLINED,
                            on_click=simulator(SIM_PPI, "Simulator Verity"),
                        ),
                        # Wie eine Uhr, die nur den Puls sendet (Ben, 17.10.2026)
                        ft.TextButton(
                            "Simulator wie Uhr (nur Puls)",
                            icon=ft.Icons.WATCH_OUTLINED,
                            on_click=simulator(SIM_PULS, "Simulator Uhr"),
                        ),
                    ],
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


def _live_teil(page: ft.Page, state: AppState, lauf: Messlauf) -> ft.Control:
    meine_nummer = state.live_ansicht
    einst = state.hrv_einstellungen()
    status_box = ft.Container()
    kacheln_box = ft.Container()
    rr_box = ft.Container()
    lage_box = ft.Container()
    letzte = 0.0
    #: Wischen läuft (bis zum Nachrechnen nach dem Loslassen): Spektrum bleibt stehen
    wischt = False
    wisch_auftrag = 0
    fenster = Fenster(einst.fenster_s, state.messung_ende_s)
    verity = bool(lauf.profil and lauf.profil.kann("pmd_ppi"))
    roh_titel = "PPI-Tachogramm" if verity else "RR-Tachogramm"
    #: Ablesen (Ben, 21.10.2026: live wie in der Aufzeichnung): an/aus, Stelle des Strichs
    #: und woraus die Karte zuletzt gebaut wurde
    ablesen: dict[str, Any] = {"an": False, "strich": None, "karte": None}
    ablese_box = ft.Container(visible=False)
    #: Hauptkurve als Puls (bpm) statt als Tachogramm — `nur_puls`, `modus_pruefen`
    modus = {"puls": nur_puls(lauf)}
    # -- Herzfrequenz-Sicht (Ben, 29.10.2026; hrv-research Entscheidung 10): zwei Sichten
    # auf einen Messlauf. Reine Pulsgeber öffnen immer die Herzfrequenz. Die Akkumulatoren
    # (Zeit je Bereich, Ø, Gipfel, TRIMP je Aufnahme und Abschnitt) liegen im Zustand, damit
    # sie den Neuaufbau der Ansicht überleben (`core.hf_training.LiveHf`).
    sicht = {"wert": SICHT_HF if modus["puls"] else state.hrv_sicht()}
    hf_profil_ = state.hf_profil()
    hf_bereiche = bereiche_fuer(hf_profil_, state.hf_einstellungen())
    hf_grenzen = grenzen_bpm(hf_bereiche)
    hf_schluessel = (
        state.profil.id,
        hf_profil_.ruhe_bpm,
        hf_profil_.hfmax_bpm,
        tuple(hf_grenzen),
        hf_profil_.geschlecht,
    )
    if state.live_hf is None or state.live_hf_schluessel != hf_schluessel:
        state.live_hf = LiveHf(hf_profil_, hf_grenzen)
        state.live_hf_schluessel = hf_schluessel
    live_hf: LiveHf = state.live_hf
    hf_box = ft.Container(visible=False)

    def anfang() -> float:
        """Ältester Punkt im Live-Puffer — weiter zurück geht es nicht."""
        return max(0.0, lauf.jetzt_s() - lauf.live.max_s)

    def einstellung_merken(**werte: Any) -> None:
        """Fensterbreite und „korrigiert" gelten auch beim nächsten Mal."""
        for name, wert in werte.items():
            setattr(einst, name, wert)
        aktuell_ = state.hrv_einstellungen()
        for name, wert in werte.items():
            setattr(aktuell_, name, wert)
        state.hrv_einstellungen_setzen(aktuell_)

    def breite_waehlen(breite_s: float) -> None:
        """Ein Breitenknopf oder die eingetippte Breite (Fenster & Darstellung) — gilt
        auch beim nächsten Mal. Zurückgeblättert bleibt der linke Rand stehen (Ben,
        26.10.2026); live folgt die Kurve weiter."""
        fenster.breite_links(breite_s, lauf.jetzt_s(), anfang())
        einstellung_merken(fenster_s=round(breite_s))
        breiten_knoepfe.selected = breiten_auswahl(breite_s)
        aktualisieren(erzwingen=True)

    def korrigiert_wechseln(e: ft.Event[ft.Switch]) -> None:
        einstellung_merken(korrigiert=bool(e.control.value))
        aktualisieren(erzwingen=True)

    def zur_gegenwart() -> None:
        fenster.ende_s = None
        ablesen["an"] = False  # „Live" heißt: wieder mitlaufen (wie im Vollbild)
        aktualisieren(erzwingen=True)

    def atemuebung_an() -> None:
        """„Atemübung" in der Übersicht umschalten — langsames Atmen auswerten oder nicht."""
        an = not einst.atemuebung
        einstellung_merken(atemuebung=an)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    "Atemübung: Auch langsames Atmen wird ausgewertet."
                    if an
                    else "Atemübung aus: Atemfrequenz erst ab 8/min."
                )
            )
        )
        aktualisieren(erzwingen=True)

    def gewischt() -> None:
        """Beim Wischen nur Kurve, Lage, Analyse und Ablesewerte — nicht die ganze Spalte."""
        nonlocal wischt
        wischt = True
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        rr_box.content = hauptkurve(x_von, x_bis)
        lage_box.content = lage()
        abschnitte_neu()
        analyse.zeichnen(x_von, x_bis, strich=strich())
        ablesen_zeichnen()
        for c in (rr_box, lage_box, analyse.wahl, analyse.control, ablese_box):
            with contextlib.suppress(Exception):
                c.update()

    # -- Ablesen: hält die Kurve an; Strich und Werte wie in der Aufzeichnung -----------

    def strich() -> float | None:
        return ablesen["strich"] if ablesen["an"] else None

    def ablesen_umschalten() -> None:
        ablesen["an"] = not ablesen["an"]
        if ablesen["an"]:
            if fenster.ende_s is None:
                fenster.ende_s = lauf.jetzt_s()  # anhalten, damit man ablesen kann
            x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
            ablesen["strich"] = strich_anfang_live(lauf, x_von, x_bis)
        aktualisieren(erzwingen=True)

    def strich_setzen(x: float, *, zeichnen: bool = True) -> None:
        ablesen["strich"] = schlag_bei_live(lauf, x)
        if zeichnen:
            aktualisieren(erzwingen=True)

    def strich_schritt(richtung: int) -> None:
        """Ein Schlag vor oder zurück; die Kurve rückt mit und bleibt angehalten."""
        jetzt = ablesen["strich"]
        if jetzt is None:
            return
        neu = schlag_weiter_live(lauf, jetzt, richtung)
        ablesen["strich"] = neu
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        if not x_von <= neu <= x_bis:
            zeigen(neu)
            fenster.ende_s = fenster.ende_s or lauf.jetzt_s()
        aktualisieren(erzwingen=True)

    def ablesen_zeichnen() -> None:
        """Die Werte am Strich unter der Kurve — neu gebaut nur, wenn sich etwas ändert:
        Live frischt zweimal je Sekunde auf, und ein neu gebauter Knopf verlöre den Tipp."""
        x = strich()
        ablese_box.visible = x is not None
        if x is None:
            ablese_box.content, ablesen["karte"] = None, None
            return
        kopf = ablese_kopf_live(lauf, x)
        werte = ablese_werte_live(
            lauf, x, analyse.gesehen, korrigiert=einst.korrigiert, verity=verity
        )
        if (kopf, werte) != ablesen["karte"]:
            ablesen["karte"] = (kopf, werte)
            ablese_box.content = ablese_karte(
                kopf, "", werte, schritt=strich_schritt, schliessen=ablesen_umschalten
            )

    def kurve_tippen(x: float) -> None:
        if ablesen["an"]:
            strich_setzen(x)
        else:
            notizfeld.tippen(x)  # „In Kurve": der Tipp setzt die Zeit der Eingabe

    def kurve_greifen(x: float) -> bool:
        """Beim Ablesen folgt der Strich dem Finger; sonst blättert die Geste."""
        if not ablesen["an"]:
            return False
        strich_setzen(x, zeichnen=False)
        return True

    def wisch_ende() -> None:
        """Nach dem Loslassen und der Latenz: Spektrum für den neuen Ausschnitt."""
        nonlocal wisch_auftrag
        wisch_auftrag += 1
        nummer = wisch_auftrag

        async def spaeter() -> None:
            nonlocal wischt
            await asyncio.sleep(state.hrv_einstellungen().nachrechnen_ms / 1000)
            if nummer != wisch_auftrag:
                return
            wischt = False
            analyse.nachrechnen()
            aktualisieren(erzwingen=True)

        page.run_task(spaeter)

    def regeln_oeffnen() -> None:
        def aendern(regeln: Korrekturregeln) -> None:
            state.korrekturregeln_setzen(regeln)  # wirkt sofort auf den Messlauf
            aktualisieren(erzwingen=True)

        blatt = korrektur_blatt(
            state.korrekturregeln(),
            aendern,
            verity=verity,
            schliessen=lambda: schliessen(blatt),  # genau das Blatt, nie eine SnackBar (N18)
        )
        page.show_dialog(blatt)

    def zeigen(x: float) -> None:
        """Die Kurve auf eine Zeit rücken — nahe der Gegenwart folgt sie wieder."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - lauf.jetzt_s(), lauf.jetzt_s(), anfang())

    def notizen_speichern(liste: list[dict]) -> None:
        # In der Aufnahme: mit Backup und Messdatei. Vorher warten sie auf den Start
        # und stehen dann an seinem Anfang (Ben, 16.10.2026: Notizen schon vorher).
        lauf.ereignisse_setzen(liste)

    def notizen_offen(offen: bool) -> None:
        state.notizen_offen = offen

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lauf.notiz_zeitbezug,
        ereignisse=lauf.ereignisse,
        speichern=notizen_speichern,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        zeigen=zeigen,
        mitte=lambda: sum(fenster.bereich(lauf.jetzt_s(), anfang())) / 2,
        jetzt=lauf.jetzt_s,
        offen=state.notizen_offen,
        offen_merken=notizen_offen,
        uebungen=(lambda: uebungsquellen(state)) if einst.notiz_uebungen else None,
        uebungen_offen=state.notiz_uebungen_offen,
        quelle=state.notiz_uebungen_quelle,
        uebungen_merken=uebungen_merken,
        katalog=(lambda: uebungs_katalog(state)) if einst.notiz_uebungen else None,
        zeit_modus=UHR if einst.achse_uhrzeit else DAUER,
        dialog=page.show_dialog,
        zeilen=lambda: state.hrv_einstellungen().notizen_zeilen,
    )

    def timer_notizen() -> None:
        """Der Timer hat Abschnitte als Notizen in die Aufnahme geschrieben."""
        notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    # -- Abschnitte (Ben, 27.10.2026): Start/Ende, Chips, Liste — `docs/plan_abschnitte.md`;
    # dasselbe Feld steht quer als Seitenleiste (`components.live_abschnitte`)
    live_abschnitte = LiveAbschnitte(
        page,
        state,
        lauf,
        fenster=fenster,
        anfang=anfang,
        breite_gesetzt=lambda b: setattr(breiten_knoepfe, "selected", breiten_auswahl(b)),
        notizen_auffrischen=lambda: notizfeld.auffrischen(),
        danach=lambda: aktualisieren(erzwingen=True),
    )
    abschnittsfeld = live_abschnitte.feld
    abschnitte_neu = live_abschnitte.neu

    state.notiz_beobachter["live"] = timer_notizen

    def ohne() -> list[str]:
        return [] if lauf.live.kennzahlen().rr_ms else ohne_rr()

    def menue_oben() -> list[ft.PopupMenuItem]:
        """Info und automatische Korrektur — vorher Knöpfe in der Titelzeile (Ben, 21.10.);
        während der Aufnahme „Teil speichern, weiter aufnehmen“ (Ben, 28.10.2026)."""
        eintraege = [info_eintrag(page, "So liest du die Kurven", lambda: kurven_info())]
        if not modus["puls"]:
            eintraege.append(regler_eintrag(regeln_oeffnen))
        if lauf.aufnahme is not None:
            eintraege.append(
                ft.PopupMenuItem(
                    content="Teil speichern, weiter aufnehmen",
                    icon=ft.Icons.SAVE_AS_OUTLINED,
                    on_click=lambda _=None: page.run_task(aufnahme_teilen),
                )
            )
        return eintraege

    analyse = Analyse(
        page,
        state,
        bereiche=einst.bereiche(optisch=verity),
        reihe=lauf.live.verlaufsreihe,
        hf_geraet=lauf.live.hf_reihe,
        ohne=ohne,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        wischen=lambda c: wischbar(
            c,
            fenster,
            lauf.jetzt_s,
            gewischt,
            anfang=anfang,
            tippen=lambda x: strich_setzen(x) if ablesen["an"] else None,
            greifen=kurve_greifen,
            losgelassen=wisch_ende,
        ),
        optisch=verity,
        warten=lambda: wischt,
        live_intervall_s=lambda: float(state.hrv_einstellungen().live_spektrum_s),
        eingebettet=True,
        menue_oben=menue_oben,
    )

    async def aufnahme_starten() -> None:
        """Start mit leeren Kurven (Ben, 16.10.2026): Der Messlauf leert das Live-Fenster
        und beginnt die Achse bei 0; die Ansicht baut sich neu auf, damit auch Analyse
        und Fenster von vorn beginnen. Eine Notiz, die gerade getippt wird, kommt mit."""
        if notizfeld.bearbeite is not None:
            notizfeld.uebernehmen()  # mit Text gespeichert — sonst ginge er beim Neuaufbau verloren
        profil = dauer_profil()
        if profil is not None:
            # Mit Dauer oder Ablauf (Ben, 17.10.2026): als Einheit — Aufnahme und Timer auf
            # einer Achse, mit allem, was schon in der Startleiste wartet
            if einheit_ui.laeuft(state) is not None:
                page.show_dialog(
                    ft.SnackBar(ft.Text("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
                )
                return
            dauer_bereitstellen(profil)
            state.messung_ende_s = None
            einheit_ui.alle_starten(page, state, 0.0)
            return
        # Für sich gestartet — trotzdem in die Leiste und in den Reiter „Einheit“ (Ben,
        # 18.10.2026): als eigene Einheit oder in der, die schon läuft; sonst allein
        hrv = HrvBaustein(lauf, basis=datenverzeichnis())
        if einheit_ui.einzeln_starten(page, state, hrv) is None:
            lauf.aufnahme_starten()
        state.messung_ende_s = None
        await _hintergrund(state, lauf, True, f"Aufnahme läuft · {lauf.geraet_name}")
        state.neu_zeichnen()

    def dauer_profil() -> TimerProfil | None:
        """Der Timer zur gewählten Dauer — ``None`` bei „offen“ (Katalog A11)."""
        wahl = state.messung_dauer
        if wahl == "ablauf":
            profile = state.timer_profile()
            gewaehlt = next((p for p in profile if p.id == state.messung_ablauf), None)
            return gewaehlt or (profile[0] if profile else None)
        return messdauer(int(wahl)) if wahl.isdigit() else None

    def dauer_bereitstellen(profil: TimerProfil | None) -> None:
        """Die Messung in die Startleiste — mit Dauer oder Ablauf samt Timer, der die
        Einheit beendet; die Aufnahme endet dann oder läuft weiter (Wahl)."""
        einheit_ui.hrv_bereitstellen(page, state)
        if profil is None:
            return
        einheit_ui.timer_bereitstellen(page, state, TimerLauf(profil))
        e = einheit_ui.in_vorbereitung(state)
        if e is not None:
            e.ende_mit_timer = True
            e.am_ende_stoppen["hrv"] = state.messung_ende_beenden

    def bereitstellen_umschalten() -> None:
        """„Bereitstellen“ — steht die Messung schon bereit, wieder heraus."""
        if einheit_ui.bereitgestellt(state, "hrv"):
            einheit_ui.zuruecknehmen(page, state, "hrv")
            if einheit_ui.bereitgestellt(state, "timer") and dauer_profil() is not None:
                einheit_ui.zuruecknehmen(page, state, "timer")
        elif einheit_ui.laeuft(state) is None:
            dauer_bereitstellen(dauer_profil())
        state.neu_zeichnen()

    def dauer_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.messung_dauer = str(e.control.selected[0])
            aktualisieren(erzwingen=True)

    def ablauf_waehlen(e: Any) -> None:
        state.messung_ablauf = e.control.value
        aktualisieren(erzwingen=True)

    def ende_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.messung_ende_beenden = e.control.selected[0] == "beenden"
            aktualisieren(erzwingen=True)

    def dauer_block() -> ft.Control:
        """„Dauer der Messung“: offen · 5 · 10 · 15 min · Ablauf (Skizzen 1–2, Ben 17.10.2026).

        Mit Dauer oder Ablauf startet die Aufnahme als Einheit mit einem Timer; seine
        Abschnitte werden Abschnitte der Messung."""
        wahl = state.messung_dauer
        zeilen: list[ft.Control] = [
            ft.Text("Dauer der Messung", size=12, weight=ft.FontWeight.W_600, opacity=0.8),
            ft.SegmentedButton(
                selected=[wahl],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value="offen", label=ft.Text("offen")),
                    *(ft.Segment(value=str(m), label=ft.Text(f"{m} min")) for m in MESSDAUERN_MIN),
                    ft.Segment(value="ablauf", label=ft.Text("Ablauf")),
                ],
                on_change=dauer_waehlen,
            ),
        ]
        profil = dauer_profil()
        if wahl == "ablauf":
            profile = state.timer_profile()
            if not profile or profil is None:
                zeilen.append(ft.Text("Im Timer ein Profil anlegen.", size=12, opacity=0.7))
                return ft.Column(spacing=8, controls=zeilen)
            zeilen.append(
                ft.Dropdown(
                    label="Ablauf",
                    value=profil.id,
                    options=[ft.DropdownOption(key=p.id, text=p.name) for p in profile],
                    on_select=ablauf_waehlen,
                    dense=True,
                )
            )
            farbe_von: dict[str, str] = {}
            reihen: list[ft.Control] = []
            for teil in profil.alle_teile():
                for a in teil.abschnitte:
                    farbe = farbe_von.setdefault(
                        a.name, ABSCHNITT_FARBEN[len(farbe_von) % len(ABSCHNITT_FARBEN)]
                    )
                    reihen.append(
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe),
                                ft.Text(a.name, size=13, expand=True),
                                ft.Text(
                                    dauer_text(a.dauer_s)
                                    + (f" × {teil.runden}" if teil.runden > 1 else ""),
                                    size=13,
                                    opacity=0.75,
                                ),
                            ],
                        )
                    )
            reihen.append(
                ft.Text(
                    f"Gesamt {dauer_text(profil.gesamt_s())}", size=13, weight=ft.FontWeight.W_600
                )
            )
            zeilen.append(ft.Column(spacing=4, controls=reihen))
        if profil is not None:
            zeilen += [
                ft.Text(ende_frage(profil), size=12, weight=ft.FontWeight.W_600, opacity=0.8),
                ft.SegmentedButton(
                    selected=["beenden" if state.messung_ende_beenden else "weiter"],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value="beenden", label=ft.Text("Messung beenden")),
                        ft.Segment(value="weiter", label=ft.Text("Weiterlaufen")),
                    ],
                    on_change=ende_waehlen,
                ),
                ft.Text(
                    "Die Restzeit steht oben in der Leiste und in der Benachrichtigung; "
                    + (
                        "die Abschnitte des Ablaufs werden Abschnitte der Messung. Abläufe "
                        "sind Timer-Profile — angelegt und geändert im Timer."
                        if wahl == "ablauf"
                        else f"die {wahl} min werden ein Abschnitt der Messung."
                    ),
                    size=12,
                    opacity=0.7,
                ),
            ]
        return ft.Column(spacing=8, controls=zeilen)

    def messeinheit() -> tuple[Einheitslauf, TimerLauf] | None:
        """Die laufende Einheit dieser Aufnahme mit Dauer oder Ablauf — nur HRV und Timer,
        und der Timer ist noch nicht fertig. Mit Training oder Plan entscheidet die
        Übersicht im Reiter „Einheit“."""
        e = einheit_ui.laeuft(state)
        if e is None or e.hrv is None or e.hrv.messlauf is not lauf:
            return None
        t = e.teil("timer")
        if not {x.art for x in e.teile} <= {"hrv", "timer"} or not isinstance(t, TimerBaustein):
            return None
        return None if t.lauf.fertig else (e, t.lauf)

    def ende_im_lauf(e: Einheitslauf, timer: TimerLauf) -> ft.Control:
        """„Wenn die 15 min um sind: Messung beenden | Weiterlaufen“ — auch im Lauf noch
        änderbar (Ben, 17.10.2026); beides wirkt erst, wenn der Timer fertig ist."""

        def waehlen(ev: ft.Event[ft.SegmentedButton]) -> None:
            if not ev.control.selected:
                return
            beenden = ev.control.selected[0] == "beenden"
            state.messung_ende_beenden = beenden
            e.am_ende_stoppen["hrv"] = beenden
            e.ende_mit_timer = True  # die Einheit endet mit dem Timer, die Messung nach Wahl
            einheit_ui.melden(state)
            aktualisieren(erzwingen=True)

        wahl = "beenden" if e.ende_mit_timer and e.stoppt_am_ende("hrv") else "weiter"
        return ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    f"{ende_frage(timer.profil)} – auch jetzt noch änderbar",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    opacity=0.8,
                ),
                ft.SegmentedButton(
                    selected=[wahl],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value="beenden", label=ft.Text("Messung beenden")),
                        ft.Segment(value="weiter", label=ft.Text("Weiterlaufen")),
                    ],
                    on_change=waehlen,
                ),
            ],
        )

    #: „Stopp & speichern“ läuft — ein zweiter Tipp, während die Datei geschrieben wird,
    #: tut nichts
    stoppt = [False]

    async def aufnahme_stoppen() -> None:
        if stoppt[0]:
            return
        e = einheit_ui.laeuft(state)
        # Eine Messung mit Dauer oder Ablauf: „Stopp“ beendet auch ihren Timer — eine
        # Einheit mit Training oder Plan läuft weiter (die HRV verlässt sie nur)
        nur_messung = (
            e is not None
            and e.hrv is not None
            and e.hrv.messlauf is lauf
            and {t.art for t in e.teile} <= {"hrv", "timer"}
        )
        stoppt[0] = True
        try:
            # Die Messdatei schreibt ein Thread (H39: eine 4-h-Datei hielt die Oberfläche
            # an); bis dahin bleibt die Aufnahme im Lauf, nimmt aber nichts mehr auf
            ergebnis = await lauf.aufnahme_stoppen_async(datenverzeichnis())
        finally:
            stoppt[0] = False
        if nur_messung and e is not None and not e.ende_wenn_alles_fertig:
            einheit_ui.alle_beenden(state)
        # Aus Einzelstarts: Die Einheit endet von selbst, sobald nichts mehr läuft — ein
        # Timer, der dazukam, läuft weiter (Ben, 18.10.2026)
        await _hintergrund(state, lauf, True, f"Verbunden mit {lauf.geraet_name}")
        if ergebnis is None:
            aktualisieren(erzwingen=True)
            return
        eintrag = aufnahme_eintragen(state, ergebnis, lauf.subject_id)
        page.show_dialog(ft.SnackBar(ft.Text(f"Gespeichert: {ergebnis.pfad.name}")))
        await page.push_route(f"/messung/{eintrag.id}")

    async def aufnahme_teilen() -> None:
        """Lange Aufnahmen in Teilen (Ben, 28.10.2026): Teil 1 wird Messdatei und Eintrag,
        die Aufnahme läuft ohne Lücke weiter; zusammenfügen am Rechner mit
        `hrv_core.zusammenfuegen`."""
        if stoppt[0]:
            return
        stoppt[0] = True
        try:
            ergebnis = await lauf.aufnahme_teilen_async(datenverzeichnis())
        except OSError as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Teil nicht gespeichert: {fehler}")))
            return
        finally:
            stoppt[0] = False
        if ergebnis is None:
            return
        aufnahme_eintragen(state, ergebnis, lauf.subject_id)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"Teil gespeichert: {ergebnis.pfad.name} — die Aufnahme läuft weiter.")
            )
        )
        abschnitte_neu(erzwingen=True)
        notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    def titel_bearbeiten() -> None:
        """Titel und Beschreibung — schon vor der Aufnahme (Ben, 17.10.2026), dann übernimmt
        sie der Start; während der Aufnahme landen sie mit Backup und Messdatei."""
        start = lauf.aufnahme.start_utc if lauf.aufnahme is not None else utc_jetzt()
        titel, beschreibung = lauf.titel_notiz()

        def speichern(titel: str, text: str) -> None:
            lauf.titel_notiz_setzen(titel, text)
            # Vergeben heißt gemerkt — auch vor dem Start (Ben, 26.10.2026)
            state.hrv.titel_merken(lauf.subject_id or state.profil.id, titel)
            aktualisieren(erzwingen=True)

        plaene = geuebte_plaene(state, start, utc_jetzt())
        profil_id = lauf.subject_id or state.profil.id
        page.show_dialog(
            titel_blatt(
                titel,
                beschreibung,
                titel_vorschlaege(state, start, utc_jetzt(), lauf.ereignisse()),
                speichern,
                vorgabe=plaene[0] if plaene else "",
                gespeicherte=state.hrv.titel_liste(profil_id),
                merken=lambda name: state.hrv.titel_merken(profil_id, name, verwendet=False),
                entfernen=lambda t: state.hrv.titel_entfernen(t.id),
            )
        )

    async def trennen() -> None:
        if lauf.aufnahme is not None:
            page.show_dialog(
                ft.SnackBar(ft.Text("Erst die Aufnahme stoppen — sonst geht sie verloren."))
            )
            return
        await lauf.trennen()
        state.messlauf = None
        state.neu_zeichnen()

    #: Statuskarte: woraus sie zuletzt gebaut wurde, ihre Laufzeit-Anzeige und ob die
    #: Beschreibung aufgeklappt ist
    status_stand: dict[str, Any] = {"schluessel": None, "dauer": None, "offen": False}

    def beschreibung_umklappen() -> None:
        status_stand["offen"] = not status_stand["offen"]
        aktualisieren(erzwingen=True)

    def status_auffrischen() -> None:
        """Die Statuskarte nur neu bauen, wenn sich an ihr etwas ändert — sonst nur die
        Laufzeit. Neu gebaute Knöpfe verlören einen Tipp, der gerade läuft (bis zu 2×/s
        kam eine neue Karte; Ben, 17.10.2026: „Titel hinzufügen“ reagierte erst beim
        zweiten Mal)."""
        s = lauf.status
        schluessel = (
            s.verbindung,
            s.batterie_prozent,
            s.hautkontakt,
            s.meldung,
            lauf.warnung,
            lauf.geraet_name,
            lauf.aufnahme is not None,
            lauf.titel_notiz(),
            status_stand["offen"],
            state.messung_dauer,
            state.messung_ablauf,
            state.messung_ende_beenden,
            einheit_ui.bereitgestellt(state, "hrv"),
            einheit_ui.laeuft(state) is not None,
            (m[0].ende_mit_timer, m[0].stoppt_am_ende("hrv")) if (m := messeinheit()) else None,
        )
        dauer = status_stand["dauer"]
        if schluessel != status_stand["schluessel"]:
            status_stand["schluessel"] = schluessel
            status_box.content = status_karte()
        elif isinstance(dauer, ft.Text):
            dauer.value = f"Aufnahme {_uhr(lauf.aufnahme_dauer_s())}"

    # -- Herzfrequenz-Sicht: Werte, Kurve, Erholung ---------------------------------------

    async def zu_hf_einstellungen() -> None:
        await page.push_route(HF_EINSTELLUNGEN)

    def hf_einstellungen_oeffnen() -> None:
        page.run_task(zu_hf_einstellungen)

    def sicht_waehlen(neu: str) -> None:
        if neu == SICHT_HRV and modus["puls"]:
            return
        sicht["wert"] = neu
        state.hrv_sicht_setzen(neu)
        aktualisieren(erzwingen=True)

    def bezug_waehlen(bezug: str) -> None:
        state.hf_bezug = bezug
        aktualisieren(erzwingen=True)

    def hf_punkte(seit_s: float) -> list[tuple[float, float, float, bool]]:
        return [
            (p.t_s, float(p.rr_ms), float(p.hf_bpm), p.artefakt or p.verworfen)
            for p in lauf.live.punkte(seit_s=seit_s)
        ]

    def hf_jetzt() -> float | None:
        """Die Herzfrequenz der letzten 5 s aus RR (bpm-Rückfall) — sonst die des Geräts."""
        jetzt = lauf.jetzt_s()
        werte = [
            w
            for _, rr, hf, art in hf_punkte(jetzt - 5.0)
            if (w := hf_je_schlag(0.0 if art else rr, hf)) is not None
        ]
        if werte:
            return sum(werte) / len(werte)
        k = lauf.live.kennzahlen()
        return (
            float(k.hf_bpm)
            if k.hf_bpm
            else (float(lauf.status.hf_bpm) if lauf.status.hf_bpm else None)
        )

    def hf_live_werte() -> tuple[float | None, dict[str, Any] | None, str, bool]:
        """``(HF, Zusammenfassung des Bezugs, Name des Bezugs, Abschnitt läuft?)``."""
        jetzt = lauf.jetzt_s()
        abschnitt_laeuft = False
        if lauf.aufnahme is not None:
            live_hf.nachfuehren(lauf.aufnahme.beats)
            offen = lauf.offener_abschnitt()
            if offen is not None:
                von = next((a.von_s for a in lauf.abschnitte() if a.id == offen[0]), None)
                if von is not None:
                    live_hf.abschnitt_setzen(offen[0], von, lauf.aufnahme.beats)
                    abschnitt_laeuft = True
            if not abschnitt_laeuft:
                live_hf.abschnitt_setzen(None, 0.0, [])
        bezug = state.hf_bezug
        if bezug == BEZUG_ABSCHNITT and not abschnitt_laeuft:
            bezug = BEZUG_AUFNAHME
        if bezug == BEZUG_AUFNAHME and lauf.aufnahme is None:
            bezug = BEZUG_FENSTER
        zus: dict[str, Any] | None
        if bezug == BEZUG_FENSTER:
            punkte = [(t, rr, hf) for t, rr, hf, art in hf_punkte(jetzt - 300.0) if not art]
            zus = fenster_zusammenfassung(punkte, hf_profil_, hf_grenzen, jetzt)
        else:
            akk = live_hf.fuer(bezug)
            zus = akk.zusammenfassung() if akk is not None else None
        return hf_jetzt(), zus, BEZUG_NAMEN[bezug], abschnitt_laeuft

    def hf_kurve(
        x_von: float,
        x_bis: float,
        *,
        marken: list[Reihe],
        x_text: Callable[[float], str] | None,
        x_null: float,
    ) -> ft.Control:
        """HF aus RR im 5-s-Mittel (bpm-Rückfall) mit den Bereichsgrenzen als Linien."""
        roh = hf_punkte(x_von - 10.0)
        punkte: list[tuple[float, float]] = []
        if roh:
            reihe = hz.hf_reihe(
                [p[0] for p in roh],
                [p[1] for p in roh],
                [p[2] for p in roh],
                artefakt=[p[3] for p in roh],
            )
            glatt = hz.rollmittel(reihe.hf, 5.0, min_anteil=0.5)
            punkte = [
                (float(t) + 1.0, float(w))
                for t, w in zip(reihe.t, glatt, strict=True)
                if w == w and x_von <= t + 1.0 <= x_bis
            ]
        reihen = [Reihe(punkte, farbe=ft.Colors.PRIMARY)]
        for g in hf_grenzen:
            reihen.append(
                Reihe(
                    [(x_von, g), (x_bis, g)],
                    farbe=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    breite=1.0,
                    gestrichelt=True,
                )
            )
        return kurve(
            [*reihen, *marken],
            einheit="HF bpm",
            hoehe=180,
            x_von=x_von,
            x_bis=x_bis,
            y_spanne_min=HF_SPANNE_MIN_BPM,
            x_text=x_text,
            x_null=x_null,
            y_fest=state.ansicht().y_bereich(werteachse("hf_geraet")),
        )

    def erholung_reihe(t0: float) -> hz.HfReihe:
        roh = hf_punkte(t0 - 10.0)
        if not roh:
            return hz.hf_reihe([], [], anfang=t0 - 10.0, ende=t0)
        return hz.hf_reihe(
            [p[0] for p in roh],
            [p[1] for p in roh],
            [p[2] for p in roh],
            artefakt=[p[3] for p in roh],
        )

    def erholung_live() -> tuple[hz.Erholung | None, dict[int, float]]:
        e = state.hf_erholung
        if e is None:
            return None, {}
        t0 = float(e["t0_s"])
        jetzt = lauf.jetzt_s()
        erg = hz.hrr_erholung(
            erholung_reihe(t0), t0, kontext=e.get("kontext", ""), haltung=e.get("haltung", "")
        )
        rest = {f: max(0.0, t0 + f - jetzt) for f in erg.hrr}
        return erg, rest

    def erholung_marke_schreiben() -> None:
        """Kontext und Haltung in die Marke der Notiz — die Datei ist die Wahrheit."""
        e = state.hf_erholung
        if e is None or e.get("notiz") is None:
            return
        marke = e["notiz"].get("marke")
        if isinstance(marke, dict):
            marke["kontext"], marke["haltung"] = e["kontext"], e["haltung"]

    def erholung_starten() -> None:
        t0 = lauf.jetzt_s()
        vorher = state.hf_erholung or {}
        state.hf_erholung = {
            "t0_s": t0,
            "kontext": vorher.get("kontext", "dauer"),
            "haltung": vorher.get("haltung", "steht"),
            "notiz": None,
        }
        if lauf.aufnahme is not None:
            state.hf_erholung["notiz"] = lauf.notiz_hinzufuegen(
                "Belastung beendet",
                marke={
                    "quelle": "person",
                    "art": "erholung",
                    "kontext": state.hf_erholung["kontext"],
                    "haltung": state.hf_erholung["haltung"],
                },
            )
            notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    def erholung_beenden() -> None:
        state.hf_erholung = None
        aktualisieren(erzwingen=True)

    def talk_marke() -> None:
        """Talk-Test (Entscheidung 18): „Sprechen wird schwer“ — die HF der 30 s davor wird in
        der Auswertung als Schwelle 1 (Talk-Test) angeboten."""
        if lauf.aufnahme is None:
            page.show_dialog(ft.SnackBar(ft.Text("Erst eine Aufnahme starten.")))
            return
        lauf.notiz_hinzufuegen("Sprechen wird schwer", marke={"quelle": "person", "art": "talk"})
        notizfeld.auffrischen()
        page.show_dialog(
            ft.SnackBar(
                ft.Text("Marke gesetzt — die Auswertung bietet die HF davor als Schwelle 1 an.")
            )
        )
        aktualisieren(erzwingen=True)

    def erholung_kontext(k: str) -> None:
        if state.hf_erholung is not None:
            state.hf_erholung["kontext"] = k
            erholung_marke_schreiben()
            aktualisieren(erzwingen=True)

    def erholung_haltung(h: str) -> None:
        if state.hf_erholung is not None:
            state.hf_erholung["haltung"] = h
            erholung_marke_schreiben()
            aktualisieren(erzwingen=True)

    def fruehere_erholungen() -> list[hz.Erholung]:
        """Die Erholungen dieser Aufnahme aus den Marken ``person/erholung`` — ohne die
        laufende."""
        if lauf.aufnahme is None:
            return []
        zb = lauf.notiz_zeitbezug()
        laufend = state.hf_erholung["t0_s"] if state.hf_erholung else None
        out: list[hz.Erholung] = []
        for e in lauf.aufnahme.ereignisse:
            marke = e.get("marke") if isinstance(e, dict) else None
            if not isinstance(marke, dict) or marke.get("art") != "erholung":
                continue
            x = zb.x(dict(e))
            if x is None or (laufend is not None and abs(x - laufend) < 0.5):
                continue
            out.append(
                hz.hrr_erholung(
                    erholung_reihe(x),
                    x,
                    kontext=str(marke.get("kontext") or ""),
                    haltung=str(marke.get("haltung") or ""),
                )
            )
        return out

    def hf_teil(
        hf: float | None, zus: dict[str, Any] | None, bezug_name: str, abschnitt_laeuft: bool
    ) -> ft.Control:
        erg, rest = erholung_live()
        return ft.Column(
            spacing=10,
            tight=True,
            controls=[
                hf_kopf(hf, hf_profil_, hf_bereiche, einstellungen=hf_einstellungen_oeffnen),
                skala(hf_bereiche, hf_profil_, hf),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"ZEIT JE BEREICH · {bezug_name.upper()}",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            opacity=0.6,
                            expand=True,
                        ),
                        bezug_wahl(
                            state.hf_bezug if state.hf_bezug in BEZUG_NAMEN else BEZUG_AUFNAHME,
                            bezug_waehlen,
                            abschnitt_laeuft=abschnitt_laeuft,
                        ),
                        ft.IconButton(
                            ft.Icons.TUNE,
                            tooltip="Einstellungen → Herzfrequenz",
                            icon_size=20,
                            on_click=lambda _=None: hf_einstellungen_oeffnen(),
                        ),
                    ],
                ),
                zeit_je_bereich(
                    (zus or {}).get("sekunden_je_bereich") if hf_bereiche else None, hf_bereiche
                ),
                erholung_block(
                    erg,
                    rest,
                    laeuft=state.hf_erholung is not None,
                    kontext=(state.hf_erholung or {}).get("kontext", "dauer"),
                    haltung=(state.hf_erholung or {}).get("haltung", "steht"),
                    starten=erholung_starten,
                    beenden=erholung_beenden,
                    kontext_setzen=erholung_kontext,
                    haltung_setzen=erholung_haltung,
                    fruehere=fruehere_erholungen(),
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.TextButton(
                            "Sprechen wird schwer",
                            icon=ft.Icons.RECORD_VOICE_OVER,
                            tooltip="Talk-Test: Marke für Schwelle 1 setzen",
                            on_click=lambda _=None: talk_marke(),
                        )
                    ],
                ),
            ],
        )

    def status_karte() -> ft.Control:
        s = lauf.status
        status_stand["dauer"] = None
        farbe = {
            Verbindung.VERBUNDEN: ft.Colors.GREEN_400,
            Verbindung.VERBINDE: ft.Colors.AMBER_400,
            Verbindung.FEHLER: FARBEN["rot"],
        }.get(s.verbindung, ft.Colors.OUTLINE)
        teile = [lauf.geraet_name or "Gerät"]
        if s.batterie_prozent is not None:
            teile.append(f"Akku {s.batterie_prozent} %")
        if s.hautkontakt is False:
            teile.append("kein Hautkontakt")
        if lauf.aufnahme is None:
            titel, beschreibung = lauf.titel_notiz()
            aktion: ft.Control = ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    dauer_block(),
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.FilledButton(
                                "Aufnahme starten",
                                icon=ft.Icons.FIBER_MANUAL_RECORD,
                                on_click=aufnahme_starten,
                            ),
                            ft.FilledTonalButton(
                                "Bereitgestellt",
                                icon=ft.Icons.CHECK,
                                on_click=bereitstellen_umschalten,
                            )
                            if einheit_ui.bereitgestellt(state, "hrv")
                            else ft.OutlinedButton(
                                "Bereitstellen",
                                icon=ft.Icons.HOURGLASS_TOP,
                                on_click=bereitstellen_umschalten,
                                disabled=einheit_ui.laeuft(state) is not None,
                            ),
                            ft.TextButton(
                                "Trennen", icon=ft.Icons.BLUETOOTH_DISABLED, on_click=trennen
                            ),
                        ],
                    ),
                    # Schon vor dem Start (Ben, 17.10.2026) — der Start übernimmt beides
                    titel_kopf(
                        titel,
                        beschreibung,
                        titel_bearbeiten,
                        klein=True,
                        offen=status_stand["offen"],
                        umklappen=beschreibung_umklappen,
                    ),
                ],
            )
        else:
            dauer = ft.Text(
                f"Aufnahme {_uhr(lauf.aufnahme_dauer_s())}", size=15, weight=ft.FontWeight.W_600
            )
            status_stand["dauer"] = dauer
            m = messeinheit()
            aktion = ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=10,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=FARBEN["rot"], size=16),
                            dauer,
                            ft.FilledButton(
                                "Stopp & speichern", icon=ft.Icons.STOP, on_click=aufnahme_stoppen
                            ),
                        ],
                    ),
                    *([ende_im_lauf(*m)] if m is not None else []),
                    titel_kopf(
                        lauf.aufnahme.titel,
                        lauf.aufnahme.notiz,
                        titel_bearbeiten,
                        klein=True,
                        offen=status_stand["offen"],
                        umklappen=beschreibung_umklappen,
                    ),
                ],
            )
        return karte(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CIRCLE, size=12, color=farbe),
                    ft.Text("  ·  ".join(teile), size=13, expand=True),
                    # Das Verbindungsprotokoll — vorher ein Klappfeld ganz unten (Ben, 17.10.)
                    diagnose_knopf(page, lauf),
                ],
            ),
            ft.Text(s.meldung, size=12, opacity=0.7, visible=bool(s.meldung)),
            ft.Text(
                lauf.warnung or "",
                size=12,
                color=FARBEN["rot"],
                weight=ft.FontWeight.W_600,
                visible=bool(lauf.warnung),
            ),
            aktion,
            abstand=8,
        )

    def hauptkurve(x_von: float, x_bis: float) -> ft.Control:
        x_text, x_null = achse(lauf.achse_utc, x_von, x_bis, uhrzeit=einst.achse_uhrzeit)
        marken = notizfeld.marken(x_von, x_bis)
        x = strich()
        if x is not None and x_von <= x <= x_bis:
            marken.append(senkrechte([x], ft.Colors.ON_SURFACE, 1.2, gestrichelt=False))
        ansicht_ = state.ansicht()
        if sicht["wert"] == SICHT_HF and not modus["puls"]:
            return hf_kurve(x_von, x_bis, marken=marken, x_text=x_text, x_null=x_null)
        if modus["puls"]:
            return pulskurve(
                lauf,
                x_von,
                x_bis,
                marken=marken,
                x_text=x_text,
                x_null=x_null,
                y_fest=ansicht_.y_bereich(werteachse("hf_geraet")),
            )
        return tachogramm(
            lauf,
            x_von,
            x_bis,
            korrigiert=einst.korrigiert,
            verity=verity,
            marken=marken,
            x_text=x_text,
            x_null=x_null,
            y_fest=ansicht_.y_bereich(werteachse(ROH)),
        )

    def achse_umschalten() -> None:
        """Zeitachse: Uhrzeit statt Dauer — gilt auch in der Aufzeichnung (Ben, 20.10.2026)."""
        einstellung_merken(achse_uhrzeit=not einst.achse_uhrzeit)
        aktualisieren(erzwingen=True)

    def kurven_titel() -> str:
        if modus["puls"] or sicht["wert"] == SICHT_HF:
            return "HERZFREQUENZ"
        return "PPI-TACHOGRAMM" if verity else "RR-TACHOGRAMM"

    def modus_pruefen() -> None:
        """Puls oder Tachogramm (`nur_puls`) — wechselt, sobald sich zeigt, was das Gerät sendet."""
        puls = nur_puls(lauf)
        if puls == modus["puls"]:
            return
        modus["puls"] = puls
        if puls:
            sicht["wert"] = SICHT_HF  # ohne Intervalle gibt es keine HRV-Sicht
        kurven_titel_text.value = kurven_titel()
        korrigiert_schalter.visible = not puls
        sicht_knopf.segments[1].disabled = puls
        analyse.aufbauen()  # das Menü: automatische Korrektur nur mit Intervallen

    async def vollbild() -> None:
        """Die Kurven allein, quer, ohne Leisten (`views.live_vollbild`)."""
        await page.push_route("/live")

    def darstellung() -> None:
        """Fenster & Darstellung (Ben, 21.10.2026: eigener Knopf): Breite der Zeitachse
        eintippen, Werteachsen der Haupt- und der Verlaufskurven, Fenster je Kurve."""
        a = state.ansicht()
        haupt = ["hf_geraet"] if modus["puls"] else [ROH]
        gezeigt = [k for g in kurvengruppen(a, analyse.bereich, ohne()) for k in g]
        page.show_dialog(
            darstellung_blatt(
                page,
                state,
                lambda: aktualisieren(erzwingen=True),
                achsen=werteachsen(a, [*haupt, *gezeigt], roh_titel),
                zeitachse=Zeitachse(fenster.breite_s, breite_waehlen, max_s=lauf.live.max_s),
            )
        )

    kurven_titel_text = ft.Text(
        kurven_titel(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6, expand=True
    )
    korrigiert_schalter = ft.Switch(
        label="korrigiert (Artefakte überbrückt)",
        value=einst.korrigiert,
        on_change=korrigiert_wechseln,
    )
    korrigiert_schalter.visible = not modus["puls"]
    sicht_knopf = sicht_wahl(sicht["wert"], sicht_waehlen, hrv_moeglich=not modus["puls"])
    ablesen_knopf = ft.TextButton(
        "Ablesen",
        icon=ft.Icons.ADS_CLICK,
        tooltip="Werte an einer Stelle der Kurven ablesen — hält die Kurve an",
        on_click=lambda: ablesen_umschalten(),
    )
    breiten_knoepfe = breiten_wahl(fenster.breite_s, breite_waehlen)

    def lage() -> ft.Control:
        """Zurückgeblättert: wie weit, und zurück zur Gegenwart."""
        if fenster.ende_s is None:
            return ft.Container()
        zurueck = lauf.jetzt_s() - fenster.bereich(lauf.jetzt_s(), anfang())[1]
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(f"−{_uhr(zurueck)} zurück", size=12, opacity=0.7),
                ft.TextButton("Live", icon=ft.Icons.SKIP_NEXT, on_click=zur_gegenwart),
            ],
        )

    def fuellen() -> None:
        state.messung_ende_s = fenster.ende_s
        # Ein Zeitpunkt für alle Kurven — sonst rückte jede ein Stück weiter.
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        status_auffrischen()
        modus_pruefen()
        hf_sicht = sicht["wert"] == SICHT_HF
        if hf_sicht:
            hf, zus, bezug_name, abschnitt_laeuft = hf_live_werte()
            werte = hf_kacheln(hf, hf_profil_, hf_bereiche, zus, bezug_name)
            hf_box.content = hf_teil(hf, zus, bezug_name, abschnitt_laeuft)
        else:
            hf_tupel = None
            if any(k in HF_KACHELN for k in einst.kacheln):
                _, zus, _, _ = hf_live_werte()
                hf_tupel = (hf_profil_, hf_bereiche, zus)
            werte = kachel_werte(
                lauf,
                einst,
                state.ansicht(),
                verity,
                atemuebung_an,
                puls_allein=modus["puls"],
                herz=hf_tupel,
            )
        hf_box.visible = hf_sicht
        korrigiert_schalter.visible = not modus["puls"] and not hf_sicht
        analyse.wahl.visible = not hf_sicht
        analyse.control.visible = not hf_sicht
        kurven_titel_text.value = kurven_titel()
        kacheln_box.content = anzeige(werte, einst.darstellung)
        rr_box.content = hauptkurve(x_von, x_bis)
        lage_box.content = lage()
        abschnitte_neu()
        analyse.zeichnen(x_von, x_bis, strich=strich())
        ablesen_zeichnen()  # nach `zeichnen`: liest die eben gezeichneten Verlaufskurven
        markieren(ablesen_knopf, ablesen["an"])

    def aktualisieren(erzwingen: bool = False) -> None:
        """Vom Messlauf nach neuen Werten gerufen — höchstens zweimal je Sekunde."""
        nonlocal letzte
        if state.live_ansicht != meine_nummer:
            return  # nicht mehr zu sehen (anderer Reiter) — nichts rechnen
        jetzt = time.monotonic()
        if not erzwingen and jetzt - letzte < 0.5:
            return
        letzte = jetzt
        fuellen()
        notizfeld.tick()
        # Ansicht nicht (mehr) auf der Seite — beim nächsten Aufbau geht es weiter.
        with contextlib.suppress(Exception):
            spalte.update()

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    def kurven_info() -> str:
        """Hauptkurve und Verlaufskurven hinter einem „i“ (Ben, 21.10.2026: ein Knopf)."""
        if sicht["wert"] == SICHT_HF and not modus["puls"]:
            return HF_INFO
        haupt = PULS_INFO if modus["puls"] else TACHOGRAMM_INFO
        return f"{haupt}\n**Verlaufskurven.** {analyse.info_text()}"

    # Eine Karte für alles (Ben, 21.10.2026: Hauptkurve und Verlaufskurven näher
    # zusammen): Bereich und Chips über der Hauptkurve, die Notizen direkt darunter —
    # dort trifft man die Zeit am genauesten —, dann Spektrum bzw. Poincaré und die
    # Verlaufskurven. Titelzeile wie in der Aufzeichnung: Ablesen, Vollbild, Fenster &
    # Darstellung (zweiter von rechts), Menü ⋮ mit Info und Korrektur (Ben, 21.10.2026).
    haupt_karte = karte(
        sicht_knopf,
        hf_box,
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                kurven_titel_text,
                ablesen_knopf,
                ft.IconButton(
                    ft.Icons.FULLSCREEN,
                    tooltip="Kurven im Vollbild (quer)",
                    on_click=vollbild,
                ),
                darstellung_knopf(darstellung),
                analyse.menue,
            ],
        ),
        abschnittsfeld.control,
        ft.Row(
            spacing=4,
            controls=[breiten_knoepfe, achsen_knopf(lambda: einst.achse_uhrzeit, achse_umschalten)],
        ),
        analyse.wahl,
        korrigiert_schalter,
        lage_box,
        wischbar(
            rr_box,
            fenster,
            lauf.jetzt_s,
            gewischt,
            anfang=anfang,
            tippen=kurve_tippen,
            greifen=kurve_greifen,
            losgelassen=wisch_ende,
        ),
        ablese_box,
        notizfeld.control,
        analyse.control,
    )
    spalte = ft.Column(
        spacing=12,
        controls=[status_box, kacheln_box, haupt_karte],
    )
    # Erstbefüllung ohne update() — die Spalte hängt noch nicht an der Seite.
    fuellen()
    lauf.beobachter = beobachten
    return spalte


# ---------------------------------------------------------------------------
# Aufzeichnungen
# ---------------------------------------------------------------------------


def _reiter(text: str, icon: ft.IconData) -> ft.Tab:
    """Ein Reiter mit dem Symbol **neben** dem Text — mit ``icon`` stünde es darüber,
    und die Zeile wäre doppelt so hoch (Ben, 21.10.2026)."""
    return ft.Tab(
        label=ft.Row(
            tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text, size=14)]
        )
    )


def _leer(text: str) -> ft.Control:
    return ft.Container(padding=24, content=ft.Text(text, opacity=0.7))


#: Was der Messungs-Export enthält — am Knopf und in der Hilfe (Ben, 26.10.2026)
EXPORT_HINWEIS = (
    "Messdateien mit Korrekturen und Notizen, ohne Bluetooth-Adresse. Zu jedem Training "
    "Abstand, Tempo und Höhe je Sekunde — ohne Ort."
)


def _strecken_liste(page: ft.Page, state: AppState, trainings: list[ft.Control]) -> ft.Control:
    """Unterreiter „Strecken": die Trainings — Zeilen aus `views.ausdauer.strecken_zeilen` —
    und „Alle exportieren“ (GPX mit Koordinaten, nach Rückfrage: Eigenverantwortung)."""
    if not trainings:
        return _leer("Noch kein Training. Unter „GPS“ ein Ausdauertraining starten.")
    kopf = ft.Container(
        padding=ft.Padding.only(left=16, right=8, top=8),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(
                    f"{len(trainings)} {'Strecke' if len(trainings) == 1 else 'Strecken'}",
                    size=12,
                    opacity=0.7,
                ),
                ft.TextButton(
                    "Alle exportieren",
                    icon=ft.Icons.SHARE,
                    tooltip="Alle Strecken als GPX — mit Koordinaten, in eigener Verantwortung",
                    on_click=lambda: strecken_export_fragen(page, state),
                ),
            ],
        ),
    )
    liste = ft.ListView(
        expand=True, padding=ft.Padding.only(bottom=24), controls=[kopf, *trainings]
    )
    return scroll_merken(page, state, "messung_strecken", liste)


def _hrv_liste(page: ft.Page, state: AppState, eintraege: list[Any]) -> ft.Control:
    """Unterreiter „HRV": die Messungen des Profils und „Alle exportieren"."""

    def oeffner(recording_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/messung/{recording_id}")

        return handler

    async def alle_exportieren() -> None:
        """Alle Aufzeichnungen dieses Profils samt Beiwerk als ein ZIP — ohne
        Bluetooth-Adressen (`core.hrv_export.exportkopie`, S10); zu jedem Training die
        Rohspur ohne Ort (`core.bewegung`, Ben 26.10.2026)."""
        basis = messungenverzeichnis()
        dateien = [d for a in eintraege for d in zugehoerige_dateien(basis / a.file_path)]
        if not dateien:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Messdateien gefunden.")))
            return
        auftraege = bewegung_vorbereiten(state, eintraege)  # Datenbank: im Loop (H39)

        def packen() -> bytes:
            return export_zip(dateien, datenverzeichnis(), zusatz=bewegung_packen(auftraege))

        daten = await asyncio.to_thread(packen)
        await weitergeben(page, f"messungen_{zeitstempel()}.zip", daten, "application/zip")

    if not eintraege:
        return _leer(
            "Noch keine Aufzeichnung. Unter „Live“ ein Gerät verbinden und "
            "„Aufnahme starten“ tippen."
        )
    zeilen: list[ft.Control] = [
        ft.Container(
            padding=ft.Padding.only(left=16, right=8, top=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(f"{len(eintraege)} Aufzeichnungen", size=12, opacity=0.7),
                    ft.TextButton(
                        "Alle exportieren",
                        icon=ft.Icons.SHARE,
                        tooltip=EXPORT_HINWEIS,
                        on_click=alle_exportieren,
                    ),
                ],
            ),
        )
    ]

    def ausnahme_umschalter(a: Any) -> Callable[[], None]:
        def handler() -> None:
            jetzt_aus = state.ausnahmen.umschalten(
                state.profil.id, RechenAusnahmeRepo.MESSUNG, a.id
            )
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(
                        "Messung zählt nicht mehr für Mittelwerte, Baseline und Feldmaximum."
                        if jetzt_aus
                        else "Messung zählt wieder mit."
                    )
                )
            )

        return handler

    for a in eintraege:
        lokal = a.started_at.astimezone()
        datum = f"{lokal:%d.%m.%Y  %H:%M}  ·  {_uhr(a.duration_s)}"
        unten = [a.geraet or a.geraet_profil]
        if a.title:
            unten.insert(0, datum)
        if a.note:
            unten.append(a.note[:40])
        # Tipp = Auswertung; Zielsymbol oder Gedrückthalten: Auswertung · Tag (28.10.2026)
        haupt, blatt = ziele_liste.auswertung_und_tag(
            page,
            a.title or datum,
            oeffner(a.id),
            lokal.date(),
            ausnahme=(
                state.ausnahmen.ist(state.profil.id, RechenAusnahmeRepo.MESSUNG, a.id),
                ausnahme_umschalter(a),
            ),
        )
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED),
                title=ft.Text(a.title or datum, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                subtitle=ft.Text("  ·  ".join(unten), size=12, max_lines=2),
                trailing=ziele_liste.symbol(haupt, blatt),
                on_click=oeffner(a.id),
                on_long_press=blatt,
            )
        )
    liste = ft.ListView(expand=True, padding=ft.Padding.only(bottom=24), controls=zeilen)
    return scroll_merken(page, state, "messung_hrv", liste)


def _aufzeichnungen(page: ft.Page, state: AppState, eintraege: list[Any]) -> ft.Control:
    """Reiter „Aufzeichnungen": Unterreiter „Strecken" (bis 26.10.2026 „Laufen" — er zeigt
    Gehen, Laufen und Rad) und „Messungen" (bis 29.10.2026 „HRV" — dort liegen auch reine
    HF-Aufnahmen; Ben, 21./29.10.2026)."""
    from trainingsapp.ui.views.ausdauer import strecken_zeilen

    trainings = strecken_zeilen(page, state)
    if state.aufzeichnungen_tab is None:
        # Erstes Öffnen: dort anfangen, wo etwas liegt
        state.aufzeichnungen_tab = 1 if eintraege and not trainings else 0

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.aufzeichnungen_tab = e.control.selected_index or 0
        state.neu_zeichnen()

    def zahl(text: str, n: int) -> str:
        return f"{text} ({n})" if n else text

    inhalt = (
        _hrv_liste(page, state, eintraege)
        if state.aufzeichnungen_tab == 1
        else _strecken_liste(page, state, trainings)
    )
    return ft.Tabs(
        length=2,
        selected_index=state.aufzeichnungen_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    secondary=True,
                    scrollable=False,
                    tabs=[
                        _reiter(zahl("Strecken", len(trainings)), ft.Icons.ROUTE),
                        _reiter(zahl("Messungen", len(eintraege)), ft.Icons.MONITOR_HEART_OUTLINED),
                    ],
                ),
                ft.Container(expand=True, content=inhalt),
            ],
        ),
    )


def messung(page: ft.Page, state: AppState) -> ft.Control:
    """Reiter oben: „Live", „GPS" und „Aufzeichnungen" — umschalten baut nur den Inhalt neu."""
    lauf = state.messlauf
    state.live_ansicht += 1  # eine ältere Live-Ansicht hört auf zu rechnen
    verbunden = lauf is not None and lauf.status.verbindung != Verbindung.GETRENNT
    eintraege = state.hrv.alle(state.profil.id)  # einmal je Aufbau (N28)

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.messung_tab = e.control.selected_index or 0
        state.neu_zeichnen()

    def liste(schluessel: str, *teile: ft.Control) -> ft.Control:
        # Die Position bleibt über Reiterwechsel und Übungsseiten hinweg (Ben, 27.10.2026:
        # „Schaue ich mir die Kurve an, gehe weg, komme wieder …“) — `components/scroll.py`
        flaeche = ft.ListView(
            expand=True,
            padding=ft.Padding.only(left=12, right=12, top=12, bottom=24),
            spacing=12,
            controls=list(teile),
        )
        return scroll_merken(page, state, schluessel, flaeche)

    inhalt: ft.Control
    if state.messung_tab == 0:
        inhalt = liste(
            "messung_live",
            _live_teil(page, state, lauf) if verbunden else _verbinden_teil(page, state),
        )
    else:
        if lauf is not None:
            # GPS und Listen brauchen keine Live-Werte; nur ein Abriss baut neu.
            lauf.beobachter = lambda layout: state.neu_zeichnen() if layout else None
        if state.messung_tab == 1:
            from trainingsapp.ui.views.ausdauer import ausdauer_inhalt

            inhalt = liste("messung_gps", ausdauer_inhalt(page, state, eingebettet=True))
        else:
            inhalt = _aufzeichnungen(page, state, eintraege)
    return ft.Tabs(
        length=3,
        selected_index=state.messung_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                # Gleich breit über die ganze Zeile, wie unter „Übungen" (Ben, 16.10.2026)
                ft.TabBar(
                    scrollable=False,
                    tabs=[
                        _reiter(
                            "Live",
                            ft.Icons.SENSORS if verbunden else ft.Icons.BLUETOOTH_SEARCHING,
                        ),
                        _reiter("GPS", ft.Icons.GPS_FIXED),
                        _reiter("Aufzeichnungen", ft.Icons.FOLDER_OPEN_OUTLINED),
                    ],
                ),
                ft.Container(expand=True, content=inhalt),
            ],
        ),
    )


__all__ = ["aufnahme_eintragen", "kachel_werte", "messung", "ohne_rr", "tachogramm_reihen"]
