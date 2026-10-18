"""Ausdauertraining mit GPS — Route `/ausdauer` (live) und `/ausdauer/<id>` (Auswertung).

Gehen, Laufen, Rad (Ben, 14.10.2026: in dieser Reihenfolge) — mit oder ohne
GPS (Laufband, Halle), mit oder ohne Gurt. Gerechnet wird in
`core.strecke.StreckenRechner` (10-m-Schritt, Auto-Pause, Splits), die HRV je
Kilometer in `core.hrv_training`. Diese Ansicht verbindet nur:

- Das Training läuft **als Einheit** (Ben, 17.10.2026; ``docs/plan_einheit.md``,
  Stufe 2): Sein Teil ist `devices.strecke_baustein.StreckeBaustein` — GPS jede
  Sekunde, Kilometer zur Split-Zeit auf eigener Spur. **Training starten** startet
  sofort, zusammen mit allem, was in der Startleiste wartet (Timer für Intervalle);
  **Bereitstellen** legt es dorthin, das GPS sucht schon Empfang. Ist ein Gurt
  verbunden, läuft die **HRV-Aufnahme** mit; lief sie schon, bekommt sie Marken
  und läuft danach weiter.
- An jedem Kilometer ein Ton, eine Vibration und die Notiz „km 3" in der Messung
  (`ui.einheit`). Die Notiz trägt **nie einen Ort**.
- Unter den großen Zahlen zwei Tabellen (Skizze 6, `core.intervalle`): **Intervalle**
  (je Abschnitt des Timers Strecke, Tempo, Ø HF — der laufende fett) und **Kilometer**
  (je vollem Split Zeit, Tempo, Ø HF). Die Auswertung zeigt die Intervalle aus der
  Zeitleiste der Einheit, mit DFA α1 beim EKG-Gurt.
- Nach dem Ende: Strecke (Datei unter ``Strecken/``, Zeile `strecke` mit ihrer
  Einheit), HRV-Aufnahme (wie sonst unter ``Messungen/``) und ein
  **Tagebucheintrag** der Übung „Gehen"/„Laufen"/„Radfahren" (`ui.training`).

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md`, Abschnitt 0): Die
Ortungen bleiben in ``Strecken/``; hinaus gehen sie nur über „GPX
exportieren", das die Person selbst antippt. HRV-Datei, Notizen,
Tagebucheintrag und Benachrichtigung bleiben ortsfrei.

**DFA α1 ohne Empfehlung** (Abschnitt 6): Verlauf, Zeit je Wertebereich und
Werte je Kilometer, neutral beschriftet — nur mit EKG-Gurt; keine Zonen.

Die Einheit lebt im `AppState` und übersteht Ansichtswechsel; bei ausgeschaltetem
Display hält sie der Vordergrunddienst (Typ ``location``).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import flet as ft
from hrv_core.korrektur import (
    Korrigiert,
    analyse_laden,
    analyse_regeln,
    analysebasis,
    anwenden,
    korr_zeiten,
    vorauswahl,
    vorschlaege,
)
from hrv_core.ppi import schlagzeiten
from hrv_core.recording import Recording, laden
from hrv_core.trends import aktuell, reihe

from trainingsapp.config import streckenverzeichnis
from trainingsapp.core.hrv_training import (
    dfa_verlauf,
    herz_aus_messung,
    hf_je_zeit,
    werte_zwischen,
    zeit_je_bereich,
)
from trainingsapp.core.intervalle import (
    HerzQuelle,
    HfReihe,
    intervalle,
    strecke_auf_achse,
)
from trainingsapp.core.models import Strecke
from trainingsapp.core.strecke import (
    GEHEN,
    LAUFEN,
    RAD,
    SPORT_NAMEN,
    SPORTARTEN,
    Punkt,
    Split,
    rechnen,
    split_laenge_m,
)
from trainingsapp.data.repositories import SettingRepo
from trainingsapp.data.strecken import gpx, jsonl_lesen, kopf_lesen
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.gps import GpsQuelle
from trainingsapp.devices.strecke_baustein import StreckeBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.ausrichtung import querformat
from trainingsapp.ui.components.dialoge import Erledigt, reste_dialog, schliessen
from trainingsapp.ui.components.forschung import forschung_fragen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.karte_strecke import StreckenKarte, ganze_strecke
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.tabellen import (
    intervall_tabelle,
    km_tabelle_live,
    km_text,
    live_tabellen,
    tempo_text,
    zahl_text,
    zeit_text,
)
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.state import AppState
from trainingsapp.ui.training import (
    HrvBezug,
    hrv_bezug,
    lauftext,
    verwaiste_uebernehmen,
    zeitleiste_und_versatz,
)

#: Live-DFA α1 so oft neu rechnen (s)
DFA_ALLE_S = 5.0

SPORT_SYMBOLE = {
    GEHEN: ft.Icons.DIRECTIONS_WALK,
    LAUFEN: ft.Icons.DIRECTIONS_RUN,
    RAD: ft.Icons.DIRECTIONS_BIKE,
}


# ---------------------------------------------------------------------------
# Verwaiste Streckendateien — Training, das Android mitten im Lauf beendet hat
# ---------------------------------------------------------------------------


def verwaiste_dialog(page: ft.Page, state: AppState) -> ft.AlertDialog:
    """Beim Start: je verwaister Datei „Übernehmen" oder „Löschen" (keine Koordinaten).

    Der Ablauf steckt in `components.dialoge.reste_dialog`, wie bei den
    Crash-Backups der HRV-Aufnahme (`views.messung.backup_dialog`).
    """

    def beschriftung(pfad: Path) -> str:
        kopf = kopf_lesen(pfad) or {}
        sport = SPORT_NAMEN.get(str(kopf.get("sportart") or ""), "Training")
        try:
            wann = datetime.fromisoformat(str(kopf["started_at"])).astimezone()
            return f"{sport} vom {wann:%d.%m.%Y %H:%M}"
        except (KeyError, ValueError):
            return f"{sport} ({pfad.name})"

    def weg(pfad: Path) -> None:
        state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]

    async def uebernehmen(pfad: Path) -> Erledigt:
        if not pfad.exists():  # schon erledigt — kein Fehler, nur nichts mehr zu tun
            weg(pfad)
            return Erledigt("Die Strecke war schon weg.")
        strecke = verwaiste_uebernehmen(state, pfad)
        return Erledigt(
            "Training nachgetragen — auch im Tagebuch." if strecke else "Datei war leer."
        )

    def loeschen(pfad: Path) -> Erledigt:
        pfad.unlink(missing_ok=True)
        weg(pfad)
        return Erledigt("Strecke gelöscht.")

    return reste_dialog(
        page,
        titel="Unvollständiges Training gefunden",
        text="Die App wurde während eines Trainings beendet. Die Strecke liegt noch "
        "auf dem Handy — nachtragen (Strecke, Zeit, Tagebuch) oder löschen?",
        offen=lambda: list(state.verwaiste_strecken),
        beschriftung=beschriftung,
        knopf="Übernehmen",
        uebernehmen=uebernehmen,
        loeschen=loeschen,
    )


def _verbunden(state: AppState) -> bool:
    lauf = state.messlauf
    return lauf is not None and lauf.status.verbindung == Verbindung.VERBUNDEN


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


def _gross(name: str, wert: str, *, einheit: str = "", farbe: str | None = None) -> ft.Control:
    return ft.Container(
        expand=True,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Text(name, size=12, opacity=0.7),
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(wert, size=28, weight=ft.FontWeight.W_600, color=farbe),
                        ft.Text(einheit, size=12, opacity=0.7),
                    ],
                ),
            ],
        ),
    )


def _training(state: AppState) -> tuple[Einheitslauf, StreckeBaustein] | None:
    """Das laufende Training — Teil ``gps`` der laufenden Einheit."""
    e = einheit_ui.laeuft(state)
    teil = e.teil("gps") if e is not None else None
    if e is None or not isinstance(teil, StreckeBaustein):
        return None
    return e, teil


def _hf(e: Einheitslauf) -> int | None:
    hrv = e.hrv
    if hrv is None:
        return None
    with contextlib.suppress(Exception):
        return hrv.messlauf.live.kennzahlen().hf_bpm
    return None


def _ekg(e: Einheitslauf) -> bool:
    hrv = e.hrv
    profil = hrv.messlauf.profil if hrv is not None else None
    return bool(profil and profil.intervall_quelle == "ekg_rr")


def _beenden_text(e: Einheitslauf, teil: StreckeBaustein) -> str:
    """Was beim Beenden geschieht — die HRV-Messung endet nur, wenn sie mitbegann."""
    saetze = [
        "Strecke und Zeit werden gespeichert." if teil.mit_gps else "Die Zeit wird gespeichert."
    ]
    if e.hrv is not None:
        if e.stoppt_am_ende("hrv"):
            saetze.append("Die HRV-Messung endet und wird gespeichert.")
        else:
            saetze.append("Die HRV-Messung läuft weiter.")
    if (t := e.timer) is not None and not t.lauf.fertig:
        saetze.append("Der Timer endet mit.")
    return " ".join(saetze)


def ausdauer_view(page: ft.Page, state: AppState) -> ft.View:
    """Training vorbereiten und starten — läuft eines, die großen Zahlen und die Karte."""
    nummer = state.ausdauer_ansicht = state.ausdauer_ansicht + 1
    inhalt = ft.Column(spacing=14)
    zahlen = ft.Column(spacing=8)
    karte_platz = ft.Container()
    pause_text = ft.Text("Auto-Pause", size=13, color=ft.Colors.AMBER_800, visible=False)
    warnung = ft.Text(size=13, color=ft.Colors.ERROR, visible=False)
    strecken_karte: StreckenKarte | None = None
    gross = {"an": False}
    dfa: dict[str, Any] = {"wert": None, "zuletzt": None}
    intervall_platz = ft.Container(visible=False)
    km_platz = ft.Container(visible=False)
    hf_reihe = HfReihe()
    tabellen_stand: dict[str, Any] = {"schluessel": None}

    # -- Bereitstellen und Starten ---------------------------------------------------

    async def quelle_fuer_start() -> tuple[bool, GpsQuelle | None]:
        """Die Ortungsquelle — ``(False, None)``, wenn es so nicht geht (Meldung steht da)."""
        from trainingsapp.ui.views.gps_test import quelle_holen

        if state.gps_test is not None and not state.gps_test.fertig:
            page.show_dialog(ft.SnackBar(ft.Text("Erst den GPS-Test beenden.")))
            return False, None
        if not state.ausdauer_gps:
            return True, None
        quelle = quelle_holen(page, state)
        berechtigung = getattr(quelle, "berechtigung", None)
        if berechtigung is not None and (status := await berechtigung()) != "erteilt":
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(
                        f"Standort {status} — in den Einstellungen des Handys erlauben, "
                        "oder ohne GPS trainieren."
                    )
                )
            )
            return False, None
        return True, quelle

    async def bereitstellen() -> bool:
        """Das Training in die Startleiste — ``True``, wenn es dort steht."""
        if einheit_ui.laeuft(state) is not None:
            page.show_dialog(
                ft.SnackBar(ft.Text("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
            )
            return False
        ok, quelle = await quelle_fuer_start()
        if not ok:
            return False
        try:
            einheit_ui.ausdauer_bereitstellen(page, state, state.ausdauer_sportart, quelle)
        except Exception as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Training nicht bereitgestellt: {fehler}")))
            return False
        return True

    async def bereitstellen_umschalten() -> None:
        """„Bereitstellen“ — steht es schon bereit, wieder heraus."""
        if einheit_ui.bereitgestellt(state, "gps"):
            einheit_ui.zuruecknehmen(page, state, "gps")
        else:
            await bereitstellen()

    async def neu_bereitstellen() -> None:
        """Sportart oder GPS geändert, während das Training bereitsteht: neu hinein."""
        if einheit_ui.bereitgestellt(state, "gps"):
            einheit_ui.zuruecknehmen(page, state, "gps")
            await bereitstellen()

    async def starten() -> None:
        """Sofort los — zusammen mit allem, was in der Startleiste wartet."""
        if not einheit_ui.bereitgestellt(state, "gps") and not await bereitstellen():
            return
        e = einheit_ui.alle_starten(page, state, 0.0)
        if e is not None and state.ausdauer_gps and state.ausdauer_karte:
            karten_hinweis_einmal()

    def karten_hinweis_einmal() -> None:
        """Einmal (nicht je Aufzeichnung, Ben 15.10.2026): Die Karte holt Kacheln online."""
        if state.einstellungen.lesen(SettingRepo.HINWEIS_KARTE, "0") == "1":
            return
        dialog: ft.AlertDialog

        def verstanden() -> None:
            state.einstellungen.setzen(SettingRepo.HINWEIS_KARTE, "1")
            schliessen(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Karte während des Trainings"),
            content=ft.Text(
                "Die Karte lädt ihre Kacheln von OpenStreetMap. Dabei gehen grobe "
                "Kachelkoordinaten (einige hundert Meter) an deren Server — die Strecke "
                "selbst bleibt auf dem Handy. Wer das nicht will, schaltet „Karte zeigen“ "
                "aus; dann wird nichts geladen."
            ),
            actions=[ft.FilledButton("Verstanden", on_click=verstanden)],
        )
        page.show_dialog(dialog)

    def karte_gewaehlt(e: ft.Event[ft.Switch]) -> None:
        state.ausdauer_karte = bool(e.control.value)

    def beenden_fragen() -> None:
        jetzt = _training(state)
        if jetzt is None:
            return
        e, teil = jetzt
        dialog: ft.AlertDialog

        async def beenden() -> None:
            schliessen(dialog)
            einheit_ui.alle_beenden(state)
            strecke = None
            for _ in range(150):  # gespeichert wird im Takt der Einheit (`ui.einheit`)
                strecke = state.strecken.zur_einheit(e.id)
                if strecke is not None or (state.einheit is not e and e.warnung):
                    break
                await asyncio.sleep(0.1)
            if strecke is None:
                page.show_dialog(ft.SnackBar(ft.Text(e.warnung or "Training nicht gespeichert.")))
                return
            page.show_dialog(ft.SnackBar(ft.Text("Training gespeichert — auch im Tagebuch.")))
            # Die Auswertung tritt an die Stelle des Trainings — Zurück führt nicht wieder
            # auf „Training starten“ (`ui/navigation.py`)
            state.ersetzen_bei = f"/ausdauer/{strecke.id}"
            await page.push_route(state.ersetzen_bei)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Training beenden?"),
            content=ft.Text(_beenden_text(e, teil)),
            actions=[
                ft.TextButton("Weiter trainieren", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden),
            ],
        )
        page.show_dialog(dialog)

    async def timer_oeffnen() -> None:
        await page.push_route("/timer")

    def kartenhoehe() -> float:
        """Quer: die Karte füllt die Höhe neben den Zahlen; hochkant klein oder groß."""
        if querformat(page):
            return max(220.0, float(page.height or 480) - 120)
        return 460.0 if gross["an"] else 220.0

    def karte_umschalten() -> None:
        gross["an"] = not gross["an"]
        if strecken_karte is not None:
            strecken_karte.karte.height = kartenhoehe()
            with contextlib.suppress(Exception):
                strecken_karte.karte.update()

    def umbauen() -> None:
        """Gedreht (``page.on_resize``): Zahlen und Karte neu anordnen, Karte in neuer Höhe."""
        if state.ausdauer_ansicht != nummer or _training(state) is None:
            return
        zeichnen()
        with contextlib.suppress(Exception):
            page.update()

    # -- Live-Werte ----------------------------------------------------------------

    def dfa_auffrischen(e: Einheitslauf) -> None:
        """Live-DFA α1 alle `DFA_ALLE_S` — nur mit EKG-Gurt, ein Schätzwert ohne Zonen."""
        hrv = e.hrv
        if hrv is None or not _ekg(e):
            dfa["wert"] = None
            return
        jetzt = time.monotonic()
        if dfa["zuletzt"] is not None and jetzt - dfa["zuletzt"] < DFA_ALLE_S:
            return
        dfa["zuletzt"] = jetzt
        with contextlib.suppress(Exception):
            t, rr, naht = hrv.messlauf.live.verlaufsreihe()
            dfa["wert"] = (
                aktuell(t, rr, naht, "dfa_alpha1", 120.0, ende=float(t[-1])) if len(t) else None
            )

    def werte(e: Einheitslauf, teil: StreckeBaustein) -> None:
        r = teil.rechner
        aktuell_ms = r.aktuelles_tempo_ms()
        aktuell_s = 1000.0 / aktuell_ms if aktuell_ms else None
        reihen: list[ft.Control] = [
            ft.Row(
                spacing=8,
                controls=[
                    _gross("Zeit", zeit_text(max(e.dauer_s(), 0.0))),
                    _gross("Strecke", km_text(r.distanz_m).removesuffix(" km"), einheit="km")
                    if teil.mit_gps
                    else _gross("Strecke", "–"),
                ],
            )
        ]
        if teil.mit_gps:
            reihen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        _gross("Tempo", tempo_text(teil.sportart, aktuell_s)),
                        _gross("Ø Tempo", tempo_text(teil.sportart, r.tempo_s_pro_km)),
                    ],
                )
            )
        if e.hrv is not None:
            hf_zeile: list[ft.Control] = [
                _gross("Herzfrequenz", zahl_text(_hf(e)), einheit="bpm", farbe=ft.Colors.RED_400)
            ]
            if _ekg(e):
                hf_zeile.append(_gross("DFA α1 (Schätzwert)", zahl_text(dfa["wert"], 2)))
            reihen.append(ft.Row(spacing=8, controls=hf_zeile))
        zahlen.controls = reihen
        pause_text.visible = teil.mit_gps and r.pausiert and r.distanz_m > 0
        meldung = teil.warnung or e.warnung
        if meldung is None and teil.quelle is not None and teil.quelle.meldung:
            meldung = f"GPS: {teil.quelle.meldung}"
        warnung.value = meldung or ""
        warnung.visible = bool(meldung)
        tabellen(e, teil)

    def tabellen(e: Einheitslauf, teil: StreckeBaustein) -> None:
        """„Intervalle (vom Timer)“ und „Kilometer (vom GPS)“ — neu gebaut nur, wenn sich
        eine angezeigte Zahl ändert."""
        stand = live_tabellen(e, hf_reihe)
        runden, km = stand.runden, stand.km
        schluessel = stand.schluessel()
        if schluessel == tabellen_stand["schluessel"]:
            return
        tabellen_stand["schluessel"] = schluessel
        intervall_platz.content = (
            karte(
                titel("Intervalle (vom Timer)"),
                intervall_tabelle(runden, teil.sportart, strecke=stand.strecke, hf=stand.herz),
            )
            if runden
            else None
        )
        intervall_platz.visible = bool(runden)
        km_platz.content = (
            karte(
                titel("Kilometer (vom GPS)" if teil.sportart != RAD else "Je 5 Kilometer (GPS)"),
                km_tabelle_live(km, teil.sportart, hf=stand.herz),
            )
            if km
            else None
        )
        km_platz.visible = bool(km)

    def zeichnen() -> None:
        nonlocal strecken_karte
        jetzt = _training(state)
        if jetzt is not None:
            e, teil = jetzt
            werte(e, teil)
            strecken_karte = None
            karte_platz.content = None
            zahlen_karte = karte(
                ft.Row(
                    controls=[
                        ft.Icon(SPORT_SYMBOLE[teil.sportart]),
                        titel(f"{SPORT_NAMEN[teil.sportart]} läuft"),
                        pause_text,
                    ],
                ),
                zahlen,
                warnung,
                ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden_fragen),
                ft.Switch(
                    label="Karte zeigen (Kacheln von OpenStreetMap)",
                    value=state.ausdauer_karte,
                    on_change=karte_gewaehlt,
                )
                if teil.mit_gps
                else ft.Container(),
                hinweis(
                    "Display darf aus sein — die Benachrichtigung zeigt Strecke, Zeit und "
                    "Herzfrequenz. An jedem Kilometer ein Ton. Was mitläuft (Timer, HRV), "
                    "steht oben in der Leiste; Runden und Kilometer stehen unten in "
                    "Tabellen und als Marken in der HRV-Messung."
                ),
            )
            if querformat(page) and teil.mit_gps and state.ausdauer_karte:
                # Quer (Ben, 15.10.2026): Zahlen und Tabellen links, die Karte rechts in
                # voller Höhe
                inhalt.controls = [
                    ft.Row(
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=min(360.0, float(page.width or 900) * 0.42),
                                content=ft.Column(
                                    spacing=12, controls=[zahlen_karte, intervall_platz, km_platz]
                                ),
                            ),
                            ft.Container(expand=True, content=karte_platz),
                        ],
                    )
                ]
            else:
                inhalt.controls = [zahlen_karte, intervall_platz, km_platz, karte_platz]
            return
        bereit = einheit_ui.bereitgestellt(state, "gps")
        andere = einheit_ui.laeuft(state)  # eine Einheit ohne Training läuft schon
        vorbereitet = einheit_ui.in_vorbereitung(state)
        sportwahl = ft.SegmentedButton(
            selected=[state.ausdauer_sportart],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=s, label=ft.Text(SPORT_NAMEN[s]), icon=ft.Icon(SPORT_SYMBOLE[s]))
                for s in SPORTARTEN
            ],
            on_change=sport_gewaehlt,
        )
        gps_schalter = ft.Switch(
            label="Mit GPS (aus: Laufband, Halle)",
            value=state.ausdauer_gps,
            on_change=gps_gewaehlt,
        )
        karte_schalter = ft.Switch(
            label="Karte zeigen (Kacheln von OpenStreetMap)",
            value=state.ausdauer_karte,
            on_change=karte_gewaehlt,
            visible=state.ausdauer_gps,
        )
        knoepfe = ft.Row(
            spacing=8,
            controls=[
                ft.FilledButton(
                    "Training starten",
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=starten,
                    disabled=andere is not None,
                    expand=True,
                ),
                ft.FilledTonalButton(
                    "Bereitgestellt", icon=ft.Icons.CHECK, on_click=bereitstellen_umschalten
                )
                if bereit
                else ft.OutlinedButton(
                    "Bereitstellen",
                    icon=ft.Icons.HOURGLASS_TOP,
                    on_click=bereitstellen_umschalten,
                    disabled=andere is not None,
                ),
            ],
        )
        if andere is not None:
            dazu = "Es läuft schon eine Einheit — erst oben mit ⏹ beenden."
        elif vorbereitet is not None and any(t.art != "gps" for t in vorbereitet.teile):
            dazu = "„Training starten“ startet alles aus der Startleiste mit."
        else:
            dazu = (
                "Noch etwas dazu? Oben den Timer öffnen und dort „Bereitstellen“ tippen — "
                "er kommt in die Startleiste, und alles startet gemeinsam."
            )
        inhalt.controls = [
            karte(
                titel("Training"),
                sportwahl,
                gps_schalter,
                karte_schalter,
                geraet_zeile(),
                knoepfe,
                hinweis(dazu),
            ),
            hinweis(
                "Die Strecke bleibt auf dem Handy (Ordner „Strecken“) — nicht im "
                "Messungs-Export, nie in einer Synchronisation. Hinaus geht sie nur, "
                "wenn du in der Auswertung „GPX exportieren“ tippst. Nur die Karte holt "
                "ihre Kacheln online (abschaltbar)."
            ),
        ]

    def geraet_zeile() -> ft.Control:
        lauf = state.messlauf
        if not _verbunden(state):
            return hinweis(
                "Ohne Gurt: Strecke und Zeit. Im Reiter „Messung“ unter „Live“ einen Gurt "
                "verbinden, dann laufen Herzfrequenz und HRV mit."
            )
        name = lauf.geraet_name if lauf is not None else ""
        optisch = bool(lauf and lauf.profil and lauf.profil.intervall_quelle != "ekg_rr")
        if optisch:
            return hinweis(
                f"{name}: Herzfrequenz und HRV laufen mit. Achtung — optisch steht die "
                "Herzfrequenz bei Bewegung oft still (Polar), und HRV gibt es nur in Ruhe. "
                "Für das Training besser den Brustgurt (H10)."
            )
        if lauf is not None and lauf.aufnahme is not None:
            return hinweis(
                f"{name}: Die HRV-Messung läuft schon — sie bekommt Marken je km und "
                "läuft nach dem Training weiter."
            )
        return hinweis(f"{name}: Herzfrequenz, HRV und DFA α1 laufen mit.")

    def sport_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.ausdauer_sportart = str(e.control.selected[0])
            page.run_task(neu_bereitstellen)

    def gps_gewaehlt(e: ft.Event[ft.Switch]) -> None:
        state.ausdauer_gps = bool(e.control.value)
        page.run_task(neu_bereitstellen)
        zeichnen()
        with contextlib.suppress(Exception):
            page.update()

    # -- Takt der Anzeige ------------------------------------------------------------

    async def ticker() -> None:
        nonlocal strecken_karte
        while state.ausdauer_ansicht == nummer:
            jetzt = _training(state)
            if jetzt is None:
                return
            e, teil = jetzt
            if state.im_vordergrund:
                dfa_auffrischen(e)
                werte(e, teil)
                punkte = teil.rechner.punkte
                if not state.ausdauer_karte and strecken_karte is not None:
                    strecken_karte = None
                    karte_platz.content = None
                if punkte and strecken_karte is None and state.ausdauer_karte:
                    strecken_karte = StreckenKarte(punkte[-1], hoehe=kartenhoehe())
                    karte_platz.content = karte(
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                titel("Karte"),
                                ft.IconButton(
                                    ft.Icons.OPEN_IN_FULL,
                                    tooltip="Karte groß oder klein",
                                    on_click=lambda: karte_umschalten(),
                                    visible=not querformat(page),  # quer ist sie schon groß
                                ),
                            ],
                        ),
                        strecken_karte.karte,
                    )
                folgen = strecken_karte.nachziehen(punkte) if strecken_karte else False
                with contextlib.suppress(Exception):
                    page.update()
                if folgen and strecken_karte is not None:
                    with contextlib.suppress(Exception):
                        await strecken_karte.folgen(punkte[-1])
            await asyncio.sleep(1.0)

    zeichnen()
    state.groesse_beobachter["ausdauer"] = umbauen
    jetzt = _training(state)
    if jetzt is not None:
        page.run_task(ticker)
    return ft.View(
        route="/ausdauer",
        appbar=ft.AppBar(
            title=ft.Text(SPORT_NAMEN[jetzt[1].sportart] if jetzt is not None else "Ausdauer"),
            actions=[
                ft.IconButton(
                    ft.Icons.TIMER_OUTLINED,
                    tooltip="Timer — Intervalle bereitstellen",
                    on_click=timer_oeffnen,
                )
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------


def _hrv_laden(state: AppState, bezug: HrvBezug | None) -> tuple[Recording, Korrigiert] | None:
    """Die HRV-Aufnahme des Trainings, korrigiert wie in ihrer Auswertung (Sidecar, Regeln) —
    direkt verknüpft oder über die Einheit (`ui.training.hrv_bezug`)."""
    if bezug is None or not bezug.pfad.exists():
        return None
    pfad = bezug.pfad
    rec = laden(pfad)
    regeln = analyse_regeln(pfad) or state.korrekturregeln()
    basis = analysebasis(rec, regeln)
    gespeichert = analyse_laden(pfad, basis)
    if gespeichert:
        korrekturen = gespeichert
    else:
        ketten = vorschlaege(basis.rec, regeln)
        korrekturen = [
            v for i in sorted(vorauswahl(ketten, regeln.vorauswahl)) for v in ketten[i].vorschlag
        ]
    return basis.rec, anwenden(basis.rec, korrekturen)


def _zu_wand(bezug: HrvBezug | None, rec: Recording, t: float) -> float | None:
    """Ortungszeit → ``t_wall_s`` der Messdatei: über die Versätze der Einheit, sonst
    über den Start der Aufnahme (ältere Trainings)."""
    if bezug is not None:
        return bezug.ortung_zu_wand(t, rec.start_utc)
    return t - rec.start_utc.timestamp() if rec.start_utc else None


def _km_tabelle(
    strecke: Strecke,
    splits: Sequence[Split],
    hrv: tuple[Recording, Korrigiert] | None,
    ekg: bool,
    bezug: HrvBezug | None = None,
) -> ft.Control:
    kopf = ["km", "Zeit", "Tempo", "Ø HF", "DFA α1", "Höhe"]
    zeilen = [kopf]
    bisher = 0.0
    for sp in splits:
        bisher += sp.distanz_m
        voll = abs(sp.distanz_m - split_laenge_m(strecke.sportart)) < 1
        hf = alpha = None
        if hrv is not None:
            rec, korr = hrv
            von, bis = _zu_wand(bezug, rec, sp.t_start), _zu_wand(bezug, rec, sp.t_ende)
            if von is not None and bis is not None:
                w = werte_zwischen(rec, korr, von, bis, dfa=ekg)
                hf, alpha = w["mean_bpm"], w["dfa_alpha1"]
        zeilen.append(
            [
                zahl_text(bisher / 1000, 0 if voll else 2),
                zeit_text(sp.t_ende - sp.t_start),
                tempo_text(strecke.sportart, sp.tempo_s_pro_km),
                zahl_text(hf),
                zahl_text(alpha, 2),
                zahl_text(sp.hoehe_auf_m),
            ]
        )
    return ft.Column(
        spacing=2,
        controls=[
            ft.Row(
                spacing=4,
                controls=[
                    ft.Text(
                        zelle,
                        expand=1,
                        size=12 if i == 0 else 13,
                        weight=ft.FontWeight.W_600 if i == 0 else None,
                        opacity=0.7 if i == 0 else 1.0,
                        text_align=ft.TextAlign.RIGHT if j else ft.TextAlign.LEFT,
                    )
                    for j, zelle in enumerate(zeile)
                ],
            )
            for i, zeile in enumerate(zeilen)
        ],
    )


def _dfa_teil(
    hrv: tuple[Recording, Korrigiert], start_utc: datetime, beginn_s: float | None = None
) -> ft.Control | None:
    """DFA-α1-Überblick: Verlauf, Zeit je Wertebereich — beschreibend, ohne Empfehlung.

    ``beginn_s``: ``t_wall_s`` der Messdatei beim Start des Trainings (Einheit); sonst
    aus den Startzeiten."""
    rec, korr = hrv
    achse = schlagzeiten(rec)
    zeiten = korr_zeiten(korr, achse)
    t, rr, naht = reihe(zeiten, korr.rr_ms, korr.breaks)
    korrigiert = [z for z, f in zip(zeiten, korr.flag, strict=True) if f != "orig"]
    punkte = dfa_verlauf(t, rr, naht, korrigiert)
    if not punkte or all(w is None for _, w, _ in punkte):
        return None
    if beginn_s is not None:
        versatz = beginn_s
    else:
        versatz = (start_utc - rec.start_utc).total_seconds() if rec.start_utc else 0.0
    linien: list[list[tuple[float, float]]] = [[]]
    for te, wert, _ in punkte:
        if wert is None:
            if linien[-1]:
                linien.append([])
            continue
        linien[-1].append(((te - versatz) / 60.0, wert))
    reihen = [Reihe(teil, farbe=ft.Colors.PURPLE_400) for teil in linien if teil]
    bereiche = zeit_je_bereich(punkte)
    return ft.Column(
        spacing=8,
        controls=[
            kurve(
                reihen,
                einheit="DFA α1",
                hoehe=180,
                y_spanne_min=0.5,
                y_schritt_min=0.1,
                x_text=lambda x: f"{x:g}".replace(".", ","),
                x_schritte=(1, 2, 5, 10, 15, 30, 60),
            ),
            ft.Text("Minuten je Wertebereich", size=12, opacity=0.7),
            ft.Row(
                wrap=True,
                spacing=14,
                controls=[
                    ft.Text(f"{name}: {zahl_text(minuten, 1)} min", size=13)
                    for name, minuten in bereiche
                ],
            ),
            hinweis(
                "DFA α1 beschreibt, wie gleichmäßig sich die Herzschlag-Abstände verändern — "
                "ein Schätzwert, nur mit EKG-Gurt. Fenster mit 3 % oder mehr korrigierten "
                "Schlägen bleiben leer. Die App gibt keine Zonen oder Empfehlungen; x-Achse: "
                "Minuten seit dem Start."
            ),
        ],
    )


def ausdauer_detail_view(page: ft.Page, state: AppState, strecke: Strecke) -> ft.View:
    route = f"/ausdauer/{strecke.id}"
    punkte: list[Punkt] = []
    if strecke.file_path:
        pfad = streckenverzeichnis() / strecke.file_path
        if pfad.exists():
            punkte = jsonl_lesen(pfad)
    r = rechnen(punkte, strecke.sportart) if punkte else None
    bezug = hrv_bezug(state, strecke)
    hrv = _hrv_laden(state, bezug)
    eintrag = bezug.aufnahme if bezug is not None else None
    ekg = bool(eintrag and eintrag.intervall_quelle == "ekg_rr")
    zeitleiste, versatz_gps = zeitleiste_und_versatz(state, strecke)
    lokal = strecke.started_at.astimezone()

    async def gpx_export() -> None:
        if not punkte:
            return
        herz: dict[float, int] = {}
        if hrv is not None:
            wand = {p.t: w for p in punkte if (w := _zu_wand(bezug, hrv[0], p.t)) is not None}
            je_wand = hf_je_zeit(hrv[0], list(wand.values()))
            herz = {t: bpm for t, w in wand.items() if (bpm := je_wand.get(w)) is not None}
        daten = gpx(
            punkte,
            name=f"{SPORT_NAMEN[strecke.sportart]} {lokal:%d.%m.%Y %H:%M}",
            sportart=strecke.sportart,
            herzfrequenz=herz or None,
        )
        await weitergeben(
            page, f"{lokal:%Y-%m-%d_%H%M}_{strecke.sportart}.gpx", daten, "application/gpx+xml"
        )

    def loeschen_fragen() -> None:
        async def loeschen() -> None:
            state.strecken.loeschen(strecke.id)
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text("Aus der Liste entfernt — die Datei bleibt.")))
            await page.push_route("/")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Training entfernen?"),
                content=ft.Text(
                    "Es verschwindet aus der Liste. Die Strecke bleibt im Ordner „Strecken“, "
                    "HRV-Aufnahme und Tagebucheintrag bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Entfernen", on_click=loeschen),
                ],
            )
        )

    async def hrv_oeffnen() -> None:
        if eintrag is not None:
            await page.push_route(f"/messung/{eintrag.id}")

    # Zwei feste Zeilen — Kacheln mit expand in einer umbrechenden Zeile zeigt Flet
    # nur als grauen Fehlerkasten
    ueberblick = ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                spacing=8,
                controls=[
                    _gross("Strecke", km_text(strecke.distanz_m).removesuffix(" km"), einheit="km")
                    if strecke.file_path
                    else _gross("Strecke", "–"),
                    _gross("Zeit", zeit_text(strecke.dauer_s)),
                ],
            ),
            ft.Row(
                spacing=8,
                controls=[
                    _gross("in Bewegung", zeit_text(strecke.bewegt_s)),
                    _gross(
                        "Ø Tempo",
                        tempo_text(strecke.sportart, r.tempo_s_pro_km if r is not None else None),
                    ),
                ],
            ),
        ],
    )
    teile: list[ft.Control] = [
        karte(
            ft.Row(
                controls=[
                    ft.Icon(SPORT_SYMBOLE.get(strecke.sportart, ft.Icons.DIRECTIONS_RUN)),
                    titel(SPORT_NAMEN.get(strecke.sportart, strecke.sportart)),
                ]
            ),
            ueberblick,
            ft.Text(
                f"Höhe: {zahl_text(strecke.hoehe_auf_m)} m hinauf, "
                f"{zahl_text(strecke.hoehe_ab_m)} m hinab (nur in Bewegung, ab 5 m)",
                size=12,
                opacity=0.7,
            ),
        ),
        karte(titel("Strecke"), ganze_strecke(r.teilstuecke if r is not None else [])),
    ]
    # Die Abschnitte des Timers, der mitlief (Skizze 6) — aus der Zeitleiste der Einheit
    herz: HerzQuelle | None = None
    if hrv is not None and bezug is not None and bezug.beginn_s is not None:
        herz = herz_aus_messung(*hrv, bezug.beginn_s, dfa=ekg)
    weg = None
    if r is not None and versatz_gps is not None:
        weg = strecke_auf_achse(r, versatz_gps)
    runden = intervalle(zeitleiste, strecke=weg, herz=herz)
    if runden:
        teile.append(
            karte(
                titel("Intervalle (vom Timer)"),
                intervall_tabelle(
                    runden,
                    strecke.sportart,
                    strecke=weg is not None,
                    hf=herz is not None,
                    dfa=herz is not None and ekg,
                ),
            )
        )
    if r is not None and r.splits_mit_rest():
        teile.append(
            karte(
                titel("Je Kilometer" if strecke.sportart != RAD else "Je 5 Kilometer"),
                _km_tabelle(strecke, r.splits_mit_rest(), hrv, ekg, bezug),
            )
        )
    if hrv is not None and ekg:
        dfa = _dfa_teil(hrv, strecke.started_at, bezug.beginn_s if bezug else None)
        if dfa is not None:
            teile.append(karte(titel("DFA α1 — Überblick"), dfa))
    if eintrag is not None:  # nicht nur die ID — die Aufnahme kann gelöscht sein
        teile.append(
            karte(
                titel("HRV"),
                hinweis("Die Herzfrequenz-Aufnahme dieses Trainings, mit Abschnitten je km."),
                ft.FilledTonalButton(
                    "HRV-Auswertung öffnen", icon=ft.Icons.MONITOR_HEART, on_click=hrv_oeffnen
                ),
            )
        )
    elif bezug is not None and not bezug.pfad.exists():
        # Die HRV-Messung lief schon vor dem Training und läuft noch (eine Einheit)
        teile.append(
            karte(
                titel("HRV"),
                hinweis(
                    "Die HRV-Messung läuft noch. Herzfrequenz und DFA α1 je Kilometer "
                    "erscheinen hier, sobald sie gespeichert ist."
                ),
            )
        )
    teile.append(
        hinweis(
            "Die Strecke bleibt auf dem Handy. „GPX exportieren“ (oben) gibt sie ausdrücklich "
            "heraus — Strava, Komoot, Garmin Connect und OsmAnd lesen GPX."
        )
    )
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"{SPORT_NAMEN.get(strecke.sportart, '')} {lokal:%d.%m. %H:%M}"),
            actions=[
                ft.IconButton(
                    ft.Icons.IOS_SHARE,
                    tooltip="GPX exportieren",
                    on_click=gpx_export,
                    disabled=not punkte,
                ),
                ft.IconButton(
                    ft.Icons.SCIENCE_OUTLINED,
                    tooltip="Für die Auswertung exportieren (ohne Ort)",
                    on_click=lambda: forschung_fragen(page, state, [strecke.einheit_id or ""]),
                    visible=bool(strecke.einheit_id),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Aus der Liste entfernen",
                    on_click=loeschen_fragen,
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=12,
        controls=[sicher(ft.Column(spacing=12, controls=teile), expand=False)],
    )


# ---------------------------------------------------------------------------
# Für den Reiter „Messung"
# ---------------------------------------------------------------------------


def ausdauer_karte(page: ft.Page, state: AppState) -> ft.Control:
    """Einstieg im Reiter „Messung → Live": Training starten, das bereitgestellte oder
    das laufende öffnen."""

    async def oeffnen() -> None:
        await page.push_route("/ausdauer")

    teil = einheit_ui.ausdauer_teil(state)
    e = einheit_ui.aktuell(state)
    if teil is not None and e is not None:
        sport = SPORT_NAMEN.get(teil.sportart, "Training")
        if e.laeuft:
            return karte(
                titel(f"{sport} läuft"),
                ft.Text(lauftext(e, teil), size=14),
                ft.FilledButton("Öffnen", icon=ft.Icons.OPEN_IN_NEW, on_click=oeffnen),
            )
        return karte(
            titel(f"{sport} bereitgestellt"),
            hinweis("Wartet in der Startleiste oben auf „Alle starten“."),
            ft.FilledTonalButton("Öffnen", icon=ft.Icons.OPEN_IN_NEW, on_click=oeffnen),
        )
    return karte(
        titel("Ausdauer"),
        hinweis("Gehen, Laufen, Rad — mit GPS und, falls verbunden, mit HRV."),
        ft.FilledTonalButton("Training starten", icon=ft.Icons.DIRECTIONS_RUN, on_click=oeffnen),
    )


def strecken_zeilen(page: ft.Page, state: AppState) -> list[ft.Control]:
    """Die Trainings des Profils für die Liste der Aufzeichnungen — neueste zuerst."""

    def oeffner(strecke_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/ausdauer/{strecke_id}")

        return handler

    zeilen: list[ft.Control] = []
    for s in state.strecken.alle(state.profil.id):
        lokal = s.started_at.astimezone()
        teile = [SPORT_NAMEN.get(s.sportart, s.sportart)]
        if s.file_path:
            teile.append(km_text(s.distanz_m))
        teile.append(zeit_text(s.dauer_s))
        mit_hrv = bool(s.hrv_recording_id) or (
            bool(s.einheit_id) and hrv_bezug(state, s) is not None
        )
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(SPORT_SYMBOLE.get(s.sportart, ft.Icons.DIRECTIONS_RUN)),
                title=ft.Text(" · ".join(teile)),
                subtitle=ft.Text(
                    f"{lokal:%d.%m.%Y  %H:%M}" + ("  ·  mit HRV" if mit_hrv else ""),
                    size=12,
                ),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                on_click=oeffner(s.id),
            )
        )
    return zeilen


__all__ = [
    "ausdauer_detail_view",
    "ausdauer_karte",
    "ausdauer_view",
    "km_text",
    "strecken_zeilen",
    "tempo_text",
    "verwaiste_dialog",
    "zeit_text",
]
