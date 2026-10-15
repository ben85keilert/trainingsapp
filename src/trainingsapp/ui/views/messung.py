"""Reiter „Messung": oben „Live" und „Aufzeichnungen".

**Live.** Ohne Verbindung: Gerät suchen (oder den Simulator nehmen). Mit
Verbindung, von oben nach unten:

1. Status — Gerät, Akku und der Aufnahmeknopf, damit man nicht erst scrollen muss.
2. Kacheln — welche, stellt man unter Einstellungen → HRV-Messung ein.
3. Hauptkurve (RR- bzw. PPI-Tachogramm) mit Fensterbreite, „korrigiert",
   Korrekturregeln und den Notizen.
4. Analyse — Zeit ↔ Frequenz ↔ Nichtlinear (`components.analyse`).

Die laufende Messung liegt im `AppState` (`state.messlauf`), nicht in dieser
Ansicht — sonst risse sie bei jedem Reiterwechsel ab (L03). Die Ansicht
schaut nur zu: `Messlauf` meldet neue Werte über einen Beobachter, und die
Ansicht frischt Kacheln und Kurven auf (höchstens zweimal je Sekunde).

Live wird nichts an den Rohdaten verändert. Artefakte werden markiert (rote
Punkte), die korrigierte Kurve ist eine Anzeige; gespeichert werden immer
die Rohwerte. Korrigiert wird nachträglich in der Aufzeichnung.

**Aufzeichnungen.** Die gespeicherten Messungen des Profils, neueste zuerst,
und „Alle exportieren".
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.hrv_ansicht import Ansicht
from trainingsapp.core.hrv_einstellungen import LIVE_FENSTER, HrvEinstellungen
from trainingsapp.core.models import HrvRecording
from trainingsapp.core.models import jetzt as utc_jetzt
from trainingsapp.devices.base import DeviceInfo, Verbindung
from trainingsapp.devices.messlauf import Gespeichert, Messlauf
from trainingsapp.devices.profiles import geraeteart
from trainingsapp.devices.simulated import SIM_PPI, SIM_PREFIX, SIM_SYNTH, SimulatedSource
from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE, kurzgrund
from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien
from trainingsapp.hrv_core.regeln import Korrekturregeln
from trainingsapp.hrv_core.trends import KENNZAHLEN, aktuell, atmung_aktuell, titel
from trainingsapp.ui.components.analyse import Analyse
from trainingsapp.ui.components.kacheln import KACHELN, KachelWert, anzeige, zahl
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_knopf
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.notizen import Notizfeld, uebungs_katalog, uebungsquellen
from trainingsapp.ui.components.titel import (
    geuebte_plaene,
    titel_blatt,
    titel_kopf,
    titel_vorschlaege,
)
from trainingsapp.ui.components.verlauf import FARBEN, fenster_text
from trainingsapp.ui.components.weitergeben import weitergeben, zeitstempel
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.state import AppState


def _protokoll(lauf: Messlauf, zeilen: int = 20) -> list[str]:
    """Die letzten Diagnosezeilen der Quelle (PolarQuelle führt sie mit)."""
    return list(getattr(lauf.quelle, "protokoll", []))[-zeilen:]


def _diagnose(page: ft.Page, lauf: Messlauf) -> ft.Control:
    """Aufklappbar — die letzten Zeilen zum Ansehen, das ganze Protokoll zum Teilen."""
    zeilen = _protokoll(lauf)

    async def teilen() -> None:
        text = lauf.diagnose()
        if not text:
            page.show_dialog(ft.SnackBar(ft.Text("Noch keine Einträge im Protokoll.")))
            return
        await weitergeben(page, f"diagnose_{zeitstempel()}.txt", text.encode("utf-8"), "text/plain")

    return ft.ExpansionTile(
        title=ft.Text("Diagnose", size=13),
        subtitle=ft.Text(zeilen[-1] if zeilen else "noch keine Einträge", size=11, opacity=0.6),
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, bottom=8),
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(
                            "\n".join(zeilen) or "–",
                            size=11,
                            selectable=True,
                            font_family="monospace",
                        ),
                        ft.TextButton("Protokoll teilen", icon=ft.Icons.SHARE, on_click=teilen),
                    ],
                ),
            )
        ],
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


def _uhr(sekunden: float) -> str:
    s = int(sekunden)
    return f"{s // 60}:{s % 60:02d}"


def ohne_rr() -> list[str]:
    """Bei einem reinen Pulsgeber lässt sich aus RR nichts rechnen — nur „HF Gerät"."""
    return [k for k in KENNZAHLEN if k != "hf_geraet"]


# ---------------------------------------------------------------------------
# Kacheln
# ---------------------------------------------------------------------------


def kachel_werte(
    lauf: Messlauf,
    einst: HrvEinstellungen,
    ansicht: Ansicht,
    verity: bool,
    atemuebung_an: Callable[[], object] | None = None,
) -> list[KachelWert]:
    """Die eingestellten Werte der Übersicht mit den aktuellen Live-Werten.

    Werte einer Verlaufskurve rechnen mit deren Fenster — der Wert ist der
    letzte Punkt der Kurve. Die Atemfrequenz gibt es nur bei deutlicher Atmung;
    sonst steht der Grund da (bei langsamer Schwingung mit dem Knopf
    „Atemübung", ``atemuebung_an``). Vom Sensor verworfene Intervalle (Verity
    Sense) erscheinen von selbst, sobald es welche gibt.
    """
    k = lauf.live.kennzahlen()
    t, rr, naht = lauf.live.verlaufsreihe()
    modus = ATEMUEBUNG if einst.atemuebung else RUHE
    gross = set(einst.gross)
    atmung = None
    out: list[KachelWert] = []
    for key in einst.kacheln:
        art = KACHELN.get(key)
        if art is None:
            continue
        g = key in gross
        if key == "hf":
            hf = k.hf_bpm if k.hf_bpm is not None else lauf.status.hf_bpm
            out.append(KachelWert("Herzfrequenz", zahl(hf), "bpm", gross=g))
        elif key == "rr":
            out.append(KachelWert("PPI" if verity else "RR", zahl(k.rr_ms), "ms", gross=g))
        elif key == "artefakte":
            out.append(
                KachelWert("Artefakte", str(k.artefakte), zusatz=f"von {k.schlaege}", gross=g)
            )
        elif key == "schwankung":
            out.append(KachelWert(art.titel, zahl(k.schwankung_60s, 1), "bpm", gross=g))
        elif key == "ulf":
            out.append(
                KachelWert(art.titel, "–", "ms²", gross=g, grund="ab 4 h, in der Aufzeichnung")
            )
        elif key in ("atemfrequenz", "rsa"):
            kz = KENNZAHLEN[key]
            fenster = ansicht.fenster_fuer(key, kz.fenster_s)
            if atmung is None:
                atmung = atmung_aktuell(t, rr, fenster, atem_modus=modus)
            wert = atmung.rate_pro_min if key == "atemfrequenz" else atmung.rsa_bpm
            grund = "" if atmung.gueltig else kurzgrund(atmung.gruende)
            aktion = None
            if key == "atemfrequenz" and atemuebung_an is not None:
                if einst.atemuebung:
                    aktion = ("Atemübung aus", atemuebung_an)
                elif "langsame Schwingung" in grund:
                    aktion = ("Atemübung", atemuebung_an)
            out.append(
                KachelWert(
                    f"{kz.titel} {fenster_text(fenster)}",
                    zahl(wert if atmung.gueltig else None, kz.nachkomma),
                    kz.einheit,
                    farbe=FARBEN[key],
                    gross=g,
                    grund=grund,
                    aktion=aktion,
                )
            )
        elif art.kennzahl is not None:
            kz = KENNZAHLEN[art.kennzahl]
            fenster = ansicht.fenster_fuer(art.kennzahl, kz.fenster_s)
            wert = (
                aktuell(t, rr, naht, art.kennzahl, fenster, pnn_ms=ansicht.pnn_ms)
                if t.size
                else None
            )
            out.append(
                KachelWert(
                    f"{titel(art.kennzahl, ansicht.pnn_ms)} {fenster_text(fenster)}",
                    zahl(wert, kz.nachkomma),
                    kz.einheit,
                    farbe=FARBEN[art.kennzahl],
                    gross=g,
                )
            )
    if k.verworfen:
        zusatz = (
            "vom Sensor · selbst geprüft"
            if lauf.regeln.selbst_pruefen
            else f"vom Sensor · von {k.schlaege + k.verworfen}"
        )
        out.append(KachelWert("Verworfen", str(k.verworfen), zusatz=zusatz))
    return out


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
    return eintrag


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

    async def verbinden(device_id: str, name: str | None) -> None:
        hinweis_text.value = f"Verbinde mit {name or device_id} …"
        hinweis_text.visible = True
        ring.visible = True
        page.update()
        if device_id.startswith(SIM_PREFIX):
            quelle: Any = SimulatedSource()
        elif state.ble_transport is not None:
            from trainingsapp.devices.polar import PolarQuelle

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
            diagnose.content = _diagnose(page, lauf)
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
                    "Polar H10 (Brustgurt, RR-Intervalle) oder Polar Verity Sense "
                    "(optisch, Pulsintervalle). Den Gurt vorher anfeuchten.",
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
    diagnose_box = ft.Container()
    letzte = 0.0
    #: Wischen läuft (bis zum Nachrechnen nach dem Loslassen): Spektrum bleibt stehen
    wischt = False
    wisch_auftrag = 0
    fenster = Fenster(einst.fenster_s, state.messung_ende_s)
    verity = bool(lauf.profil and lauf.profil.kann("pmd_ppi"))

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

    def fenster_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            fenster.breite_s = int(e.control.selected[0])
            einstellung_merken(fenster_s=int(fenster.breite_s))
            aktualisieren(erzwingen=True)

    def korrigiert_wechseln(e: ft.Event[ft.Switch]) -> None:
        einstellung_merken(korrigiert=bool(e.control.value))
        aktualisieren(erzwingen=True)

    def zur_gegenwart() -> None:
        fenster.ende_s = None
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
        """Beim Wischen nur Kurve, Lage und Analyse — nicht die ganze Spalte."""
        nonlocal wischt
        wischt = True
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        rr_box.content = hauptkurve(x_von, x_bis)
        lage_box.content = lage()
        analyse.zeichnen(x_von, x_bis)
        for c in (rr_box, lage_box, analyse.control):
            with contextlib.suppress(Exception):
                c.update()

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

        page.show_dialog(
            korrektur_blatt(
                state.korrekturregeln(),
                aendern,
                verity=verity,
                schliessen=page.pop_dialog,
            )
        )

    def zeigen(x: float) -> None:
        """Die Kurve auf eine Zeit rücken — nahe der Gegenwart folgt sie wieder."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - lauf.jetzt_s(), lauf.jetzt_s(), anfang())

    def notizen_speichern(liste: list[dict]) -> None:
        if lauf.aufnahme is not None:
            lauf.aufnahme.ereignisse = liste  # landet mit Backup und Messdatei

    def notizen_offen(offen: bool) -> None:
        state.notizen_offen = offen

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lauf.notiz_zeitbezug,
        ereignisse=lambda: list(lauf.aufnahme.ereignisse) if lauf.aufnahme is not None else [],
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
    )

    def timer_notizen() -> None:
        """Der Timer hat Abschnitte als Notizen in die Aufnahme geschrieben."""
        notizfeld.auffrischen()
        aktualisieren(erzwingen=True)

    state.notiz_beobachter["live"] = timer_notizen

    def ohne() -> list[str]:
        return [] if lauf.live.kennzahlen().rr_ms else ohne_rr()

    analyse = Analyse(
        page,
        state,
        bereiche=einst.bereiche(optisch=verity),
        reihe=lauf.live.verlaufsreihe,
        hf_geraet=lauf.live.hf_reihe,
        ohne=ohne,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        wischen=lambda c: wischbar(
            c, fenster, lauf.jetzt_s, gewischt, anfang=anfang, losgelassen=wisch_ende
        ),
        optisch=verity,
        warten=lambda: wischt,
        live_intervall_s=lambda: float(state.hrv_einstellungen().live_spektrum_s),
    )

    async def aufnahme_starten() -> None:
        lauf.aufnahme_starten()
        notizfeld.auffrischen()
        aktualisieren(erzwingen=True)
        await _hintergrund(state, lauf, True, f"Aufnahme läuft · {lauf.geraet_name}")

    async def aufnahme_stoppen() -> None:
        ergebnis = lauf.aufnahme_stoppen(datenverzeichnis())
        await _hintergrund(state, lauf, True, f"Verbunden mit {lauf.geraet_name}")
        if ergebnis is None:
            aktualisieren(erzwingen=True)
            return
        eintrag = aufnahme_eintragen(state, ergebnis, lauf.subject_id)
        page.show_dialog(ft.SnackBar(ft.Text(f"Gespeichert: {ergebnis.pfad.name}")))
        await page.push_route(f"/messung/{eintrag.id}")

    def titel_bearbeiten() -> None:
        """Titel und Beschreibung schon während der Aufnahme — sie landen in der Datei."""
        aufnahme = lauf.aufnahme
        if aufnahme is None:
            return

        def speichern(titel: str, text: str) -> None:
            aufnahme.titel, aufnahme.notiz = titel, text
            aktualisieren(erzwingen=True)

        plaene = geuebte_plaene(state, aufnahme.start_utc, utc_jetzt())
        page.show_dialog(
            titel_blatt(
                aufnahme.titel,
                aufnahme.notiz,
                titel_vorschlaege(state, aufnahme.start_utc, utc_jetzt(), aufnahme.ereignisse),
                speichern,
                page.pop_dialog,
                vorgabe=plaene[0] if plaene else "",
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

    def status_karte() -> ft.Control:
        s = lauf.status
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
            aktion: ft.Control = ft.Row(
                spacing=8,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.FilledButton(
                        "Aufnahme starten",
                        icon=ft.Icons.FIBER_MANUAL_RECORD,
                        on_click=aufnahme_starten,
                    ),
                    ft.TextButton("Trennen", icon=ft.Icons.BLUETOOTH_DISABLED, on_click=trennen),
                ],
            )
        else:
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
                            ft.Text(
                                f"Aufnahme {_uhr(lauf.aufnahme_dauer_s())}",
                                size=15,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.FilledButton(
                                "Stopp & speichern", icon=ft.Icons.STOP, on_click=aufnahme_stoppen
                            ),
                        ],
                    ),
                    titel_kopf(
                        lauf.aufnahme.titel, lauf.aufnahme.notiz, titel_bearbeiten, klein=True
                    ),
                ],
            )
        return karte(
            ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.CIRCLE, size=12, color=farbe),
                    ft.Text("  ·  ".join(teile), size=13, expand=True),
                ],
            ),
            ft.Text(s.meldung, size=12, opacity=0.7, visible=bool(s.meldung)),
            aktion,
            abstand=8,
        )

    def hauptkurve(x_von: float, x_bis: float) -> ft.Control:
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
            if 250 < p.rr_ms < 2200:
                grau.append((p.t_s, float(p.rr_ms)))
            wert = p.rr_korr if einst.korrigiert else float(p.rr_ms)
            if p.verworfen or wert is None:
                offen = True
                continue
            if (offen or p.naht_davor) and rr_linie:
                rr_naehte.append(len(rr_linie))
            offen = False
            rr_linie.append((p.t_s, wert))
        artefakte = [(p.t_s, float(p.rr_ms)) for p in mit_rr if p.artefakt and 250 < p.rr_ms < 2200]
        return kurve(
            [
                Reihe(grau, farbe=ft.Colors.OUTLINE, breite=1, naehte=grau_naehte, skala=False),
                Reihe(rr_linie, farbe=ft.Colors.PRIMARY, naehte=rr_naehte),
                Reihe(artefakte, farbe=FARBEN["rot"], nur_punkte=True, skala=False),
                *notizfeld.marken(x_von, x_bis),
            ],
            einheit="PPI ms" if verity else "RR ms",
            x_von=x_von,
            x_bis=x_bis,
            y_spanne_min=RR_SPANNE_MIN_MS,
        )

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
        status_box.content = status_karte()
        werte = kachel_werte(lauf, einst, state.ansicht(), verity, atemuebung_an)
        kacheln_box.content = anzeige(werte, einst.darstellung)
        rr_box.content = hauptkurve(x_von, x_bis)
        lage_box.content = lage()
        analyse.zeichnen(x_von, x_bis)

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
        if not lauf.simulation:
            diagnose_box.content = _diagnose(page, lauf)
        # Ansicht nicht (mehr) auf der Seite — beim nächsten Aufbau geht es weiter.
        with contextlib.suppress(Exception):
            spalte.update()

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    haupt_karte = karte(
        kartentitel(
            "PPI-Tachogramm" if verity else "RR-Tachogramm",
            regler_knopf(regeln_oeffnen),
        ),
        ft.SegmentedButton(
            selected=[str(fenster.breite_s if fenster.breite_s in LIVE_FENSTER else 120)],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=str(s), label=ft.Text(fenster_text(s))) for s in LIVE_FENSTER
            ],
            on_change=fenster_wechseln,
        ),
        ft.Switch(
            label="korrigiert (Artefakte überbrückt)",
            value=einst.korrigiert,
            on_change=korrigiert_wechseln,
        ),
        lage_box,
        wischbar(
            rr_box,
            fenster,
            lauf.jetzt_s,
            gewischt,
            anfang=anfang,
            tippen=notizfeld.tippen,
            losgelassen=wisch_ende,
        ),
        notizfeld.control,
        hinweis(
            "Grau: alle Rohwerte, auch vom Sensor verworfene · Farbig: gewertet · Rote "
            "Punkte: Artefakte (markiert, nicht verändert) · Gelb: Notizen. Waagrecht "
            "wischen blättert zurück. Gespeichert werden immer die Rohwerte; korrigiert "
            "wird in der Aufzeichnung."
        ),
    )
    spalte = ft.Column(
        spacing=12,
        controls=[status_box, kacheln_box, haupt_karte, analyse.control, diagnose_box],
    )
    # Erstbefüllung ohne update() — die Spalte hängt noch nicht an der Seite.
    fuellen()
    lauf.beobachter = beobachten
    return spalte


# ---------------------------------------------------------------------------
# Aufzeichnungen
# ---------------------------------------------------------------------------


def _liste(page: ft.Page, state: AppState) -> ft.Control:
    eintraege = state.hrv.alle(state.profil.id)

    def oeffner(recording_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/messung/{recording_id}")

        return handler

    async def alle_exportieren() -> None:
        """Alle Aufzeichnungen dieses Profils samt Beiwerk als ein ZIP."""
        basis = messungenverzeichnis()
        dateien = [d for a in eintraege for d in zugehoerige_dateien(basis / a.file_path)]
        if not dateien:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Messdateien gefunden.")))
            return
        daten = export_zip(dateien, datenverzeichnis())
        await weitergeben(page, f"messungen_{zeitstempel()}.zip", daten, "application/zip")

    from trainingsapp.ui.views.ausdauer import strecken_zeilen

    trainings = strecken_zeilen(page, state)
    if not eintraege and not trainings:
        return ft.Container(
            padding=24,
            content=ft.Text(
                "Noch keine Aufzeichnung. Unter „Live“ ein Gerät verbinden und "
                "„Aufnahme starten“ tippen — oder ein Ausdauertraining starten.",
                opacity=0.7,
            ),
        )
    zeilen: list[ft.Control] = []
    if trainings:
        zeilen.append(
            ft.Container(
                padding=ft.Padding.only(left=16, top=12),
                content=ft.Text("AUSDAUER", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            )
        )
        zeilen += trainings
    if not eintraege:
        return ft.ListView(expand=True, padding=ft.Padding.only(bottom=24), controls=zeilen)
    zeilen += [
        ft.Container(
            padding=ft.Padding.only(left=16, right=8, top=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(f"{len(eintraege)} Aufzeichnungen", size=12, opacity=0.7),
                    ft.TextButton(
                        "Alle exportieren", icon=ft.Icons.SHARE, on_click=alle_exportieren
                    ),
                ],
            ),
        )
    ]
    for a in eintraege:
        lokal = a.started_at.astimezone()
        datum = f"{lokal:%d.%m.%Y  %H:%M}  ·  {_uhr(a.duration_s)}"
        unten = [a.geraet or a.geraet_profil]
        if a.title:
            unten.insert(0, datum)
        if a.note:
            unten.append(a.note[:40])
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED),
                title=ft.Text(a.title or datum, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                subtitle=ft.Text("  ·  ".join(unten), size=12, max_lines=2),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                on_click=oeffner(a.id),
            )
        )
    return ft.ListView(expand=True, padding=ft.Padding.only(bottom=24), controls=zeilen)


def messung(page: ft.Page, state: AppState) -> ft.Control:
    """Reiter oben: „Live" und „Aufzeichnungen" — umschalten baut nur den Inhalt neu."""
    lauf = state.messlauf
    state.live_ansicht += 1  # eine ältere Live-Ansicht hört auf zu rechnen
    verbunden = lauf is not None and lauf.status.verbindung != Verbindung.GETRENNT

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.messung_tab = e.control.selected_index or 0
        state.neu_zeichnen()

    if state.messung_tab == 1:
        inhalt: ft.Control = _liste(page, state)
        if lauf is not None:
            # Die Liste braucht keine Live-Werte; nur ein Abriss baut neu.
            lauf.beobachter = lambda layout: state.neu_zeichnen() if layout else None
    else:
        from trainingsapp.ui.views.ausdauer import ausdauer_karte

        teil = _live_teil(page, state, lauf) if verbunden else _verbinden_teil(page, state)
        inhalt = ft.ListView(
            expand=True,
            padding=ft.Padding.only(left=12, right=12, top=12, bottom=24),
            spacing=12,
            controls=[ausdauer_karte(page, state), teil],
        )
    anzahl = len(state.hrv.alle(state.profil.id))
    return ft.Tabs(
        length=2,
        selected_index=state.messung_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(
                            label="Live",
                            icon=ft.Icons.SENSORS if verbunden else ft.Icons.BLUETOOTH_SEARCHING,
                        ),
                        ft.Tab(
                            label=f"Aufzeichnungen ({anzahl})" if anzahl else "Aufzeichnungen",
                            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                        ),
                    ]
                ),
                ft.Container(expand=True, content=inhalt),
            ],
        ),
    )


__all__ = ["aufnahme_eintragen", "kachel_werte", "messung", "ohne_rr"]
