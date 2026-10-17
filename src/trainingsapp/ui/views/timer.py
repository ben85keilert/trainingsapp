"""Timer als Werkzeug — Route `<irgendwo>/timer`, Profil bearbeiten `…/timer/bearbeiten[/<id>]`,
Signale einstellen `…/timer/signale`.

Der Timer ist von überall erreichbar (Symbol oben in der Leiste) und legt sich
über die aktuelle Ansicht: „Zurück" führt dorthin, wo man war — aus einem
Plan zurück in den Plan. Er läuft weiter, wenn man die Ansicht verlässt; die
Leiste zeigt dann die Restzeit (`timer_knopf`).

Ein **Profil** ist eine Folge benannter Abschnitte (``mm:ss``) und eine
Rundenzahl (`core.timer.TimerProfil`). Das zuletzt benutzte ist beim Öffnen
aktiv. Ohne eigene Profile gibt es zwei Vorlagen.

Der Ablauf rechnet auf der monotonen Uhr (`core.timer.TimerLauf`); diese
Ansicht fragt nur ab. Signale (`core.timer.signal`): kurze Töne 3-2-1 vor jedem
Abschnittsende, zwei Töne beim Wechsel, vier am Ende; dazu Vibration. Die Töne
spielt die Erweiterung ``flet_ton`` — Musik anderer Apps wird dabei nur kurz
leiser (nur in der gebauten App; am Rechner bleibt es still).

Solange der Timer läuft, bleibt der Bildschirm an (``Wakelock``): Schläft die
App, bleiben Töne und Vibration aus — die Zeit stimmt beim Aufwachen trotzdem.

**Abschnitte als Notizen.** Läuft eine HRV-Aufnahme, wird jeder
Abschnittsanfang eine Notiz in der Messung, an der Stelle, an der er wirklich
war. Es sind gewöhnliche Notizen: umbenennen, verschieben, löschen — live und
nachträglich in der Aufzeichnung. Alles abschaltbar unter „Signale".

Die Signale haben eine eigene Seite (Ben, 14.10.2026): Unter dem Timer steht
knapp, was eingeschaltet ist (`core.timer.signale_kurz`), das Zahnrad in der
Ecke öffnet die Schalter. Auf dem Timer selbst bleibt so nur, was man beim
Trainieren braucht. Dort auch: **Klang** beim Wechsel (Piep, Glocke 1–3, Gong,
Klangholz, Fanfare — antippen spielt ihn vor) und **Lautstärke**: über welchen
Regler des Systems die Töne laufen (Medien als Vorgabe, Wecker, Klingelton;
`core.timer.QUELLEN`) und wie viel davon. Ein Abschnitt kann im Profil einen
eigenen Klang haben, das Profil einen für jede neue Runde und fürs Ende
(`core.timer.klang_fuer`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.klang import GLOCKEN, KLAENGE, TOENE, glocke, wav
from trainingsapp.core.timer import (
    COUNTDOWN,
    ENDE,
    MAX_RUNDEN,
    QUELLEN,
    Abschnitt,
    Marke,
    TimerLauf,
    TimerProfil,
    TimerSignale,
    TimerStand,
    dauer_lesen,
    dauer_text,
    klang_fuer,
    signal,
    signale_kurz,
)
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.dialoge import Nachher
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState

#: So oft je Sekunde wird die Anzeige aufgefrischt
TICK_S = 0.2


def timer_route(basis: str) -> str:
    """Die Timer-Route über einer Ansicht.

    >>> timer_route("/"), timer_route("/plan/abc")
    ('/timer', '/plan/abc/timer')
    """
    return basis.rstrip("/") + "/timer"


# ---------------------------------------------------------------------------
# Ablauf: Lauf holen, Ticker
# ---------------------------------------------------------------------------


def lauf_fuer(state: AppState, profil: TimerProfil) -> TimerLauf:
    """Der Lauf zum Profil — ein anderes Profil (oder ein geändertes) beginnt neu.

    Gehört der Timer einer laufenden Einheit, bleibt er (sonst liefe dort ein Timer,
    den keine Ansicht mehr zeigt). Steht er bereitgestellt in der Startleiste, nimmt
    die Einheit den neuen Lauf.
    """
    lauf: TimerLauf | None = state.timer
    if einheit_ui.besitzt_timer(state, lauf):
        assert lauf is not None
        return lauf
    if lauf is None or lauf.profil != profil:
        lauf = TimerLauf(profil)
        state.timer = lauf
        e = einheit_ui.in_vorbereitung(state)
        if e is not None and (teil := e.timer) is not None:
            teil.lauf = lauf
            teil.uhr_uebernehmen(e.uhr)
    return lauf


async def toene_laden(state: AppState) -> None:
    """Die Signaltöne einmal in den Tondienst legen (beim App-Start).

    Erst die drei Signale (schnell erzeugt) — danach ist der Timer
    hörbereit —, dann die Glocken. Die rechnen auf dem Handy eine Weile und
    tun das in einem eigenen Thread, damit die Oberfläche nicht stockt.
    """
    if state.ton is None:
        return
    with contextlib.suppress(Exception):
        for name, folge in TOENE.items():
            await state.ton.laden(name, wav(folge))
        state.toene_geladen = True
        for name, (teiltoene, grund, dauer) in GLOCKEN.items():
            daten = await asyncio.to_thread(glocke, teiltoene, grund, dauer)
            await state.ton.laden(name, daten)


async def ton_spielen(state: AppState, klang: str, signale: TimerSignale | None = None) -> bool:
    """Einen Klang mit Regler und Lautstärke der Signale spielen — ``False``, wo es nicht geht."""
    signale = signale or state.timer_signale()
    if state.ton is None or not state.toene_geladen:
        return False
    try:
        await state.ton.spielen(klang, signale.lautstaerke / 100, signale.quelle)
    except Exception:
        return False
    return True


async def _melden(state: AppState, art: str, signale: TimerSignale, klang: str) -> None:
    """Ton und Vibration zu einem Signal — wie eingestellt und wo es geht."""
    if art == COUNTDOWN and not signale.countdown:
        return
    if signale.ton:
        await ton_spielen(state, klang, signale)
    haptik = state.haptik
    if signale.vibration and haptik is not None and art != COUNTDOWN:
        with contextlib.suppress(Exception):
            await haptik.vibrate()
            if art == ENDE:
                await asyncio.sleep(0.35)
                await haptik.vibrate()


async def _wach(state: AppState, an: bool) -> None:
    """Bildschirm anlassen (oder wieder freigeben) — still, wo es nicht geht."""
    if state.wach is None:
        return
    with contextlib.suppress(Exception):
        await (state.wach.enable() if an else state.wach.disable())


def _in_messung(state: AppState, marken: list[Marke], signale: TimerSignale) -> None:
    """Abschnittsanfänge als Notizen und Abschnitte in die laufende Aufnahme (wenn eingestellt)."""
    messlauf = state.messlauf
    if not marken or not signale.notizen or messlauf is None:
        return
    # Jeder Abschnitt des Timers wird auch ein Abschnitt der Messung (beim Speichern)
    neu = [
        messlauf.abschnitt_markieren(m.text, m.vor_s, name=m.abschnitt, ende=m.ende) for m in marken
    ]
    if any(e is not None for e in neu):
        for beobachter in list(state.notiz_beobachter.values()):
            with contextlib.suppress(Exception):
                beobachter()


def ticker_starten(page: Any, state: AppState) -> None:
    """Eine Aufgabe, die läuft, solange der Timer läuft — nie zwei zugleich.

    Je Abfrage: Signal fällig? Abschnittsanfänge für Notizen? Beobachter
    auffrischen. Der Bildschirm bleibt an, solange sie läuft (wenn eingestellt).
    """
    if state.timer_aufgabe:
        return

    async def ticken() -> None:
        alt: TimerStand | None = None
        wach = False
        try:
            while (lauf := state.timer) is not None:
                stand = lauf.stand()
                if (art := signal(alt, stand)) is not None:
                    signale = state.timer_signale()
                    klang = klang_fuer(art, stand, lauf.profil, signale)
                    await _melden(state, art, signale, klang)
                # Gehört der Timer einer Einheit, holt sie die Marken (ein Abnehmer)
                if not einheit_ui.besitzt_timer(state, lauf) and (marken := lauf.neue_marken()):
                    _in_messung(state, marken, state.timer_signale())
                alt = stand
                for beobachter in list(state.timer_beobachter.values()):
                    with contextlib.suppress(Exception):
                        beobachter()
                if not stand.laeuft:
                    break
                if not wach and state.timer_signale().wach:
                    await _wach(state, True)
                    wach = True
                await asyncio.sleep(TICK_S)
        finally:
            state.timer_aufgabe = None
            if wach:
                await _wach(state, False)

    state.timer_aufgabe = True
    try:
        page.run_task(ticken)
    except Exception:  # Seite schon weg — sonst startete bis zum Neustart kein Ticker mehr
        state.timer_aufgabe = None
        raise


# ---------------------------------------------------------------------------
# Knopf in der Leiste
# ---------------------------------------------------------------------------


def timer_knopf(page: Any, state: AppState, name: str) -> ft.Control:
    """„Timer" als Knopf für eine AppBar — läuft der Timer, steht dort die Restzeit.

    Symbol und Beschriftung in einer umrandeten Pille: ein Symbol allein sagt
    nicht, was es tut. Läuft der Timer, ersetzt die Restzeit das Wort — immer in
    einer Zeile. ``name`` unterscheidet die Leisten — jede trägt sich als
    Beobachter ein und ersetzt dabei ihren alten Eintrag.
    """
    # Eine Zeile, auch bei großer Systemschrift — eine feste Breite brach „Timer"
    # am Pixel um (14.10.)
    text = ft.Text("Timer", size=13, weight=ft.FontWeight.W_600, no_wrap=True, max_lines=1)

    def beschriften() -> bool:
        lauf: TimerLauf | None = state.timer
        stand = lauf.stand() if lauf is not None else None
        aktiv = stand is not None and lauf is not None and lauf.begonnen and not stand.fertig
        text.value = dauer_text(-(-stand.rest_s // 1)) if aktiv and stand else "Timer"
        return aktiv

    def auffrischen() -> None:
        aktiv = beschriften()
        knopf.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY) if aktiv else None
        with contextlib.suppress(Exception):
            knopf.update()

    async def oeffnen() -> None:
        if "/timer" in page.route:
            return
        await page.push_route(timer_route(page.route))

    knopf = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        margin=ft.Margin.symmetric(horizontal=4),
        border_radius=18,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        ink=True,
        tooltip="Timer öffnen",
        on_click=oeffnen,
        content=ft.Row(
            spacing=6,
            tight=True,
            controls=[ft.Icon(ft.Icons.TIMER_OUTLINED, size=20), text],
        ),
    )
    state.timer_beobachter[name] = auffrischen
    if beschriften():
        knopf.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
    return knopf


# ---------------------------------------------------------------------------
# Timer-Ansicht
# ---------------------------------------------------------------------------


def timer_view(page: Any, state: AppState, basis: str) -> ft.View:
    route = timer_route(basis)
    profile = state.timer_profile()
    profil = state.timer_profil()
    lauf = lauf_fuer(state, profil)

    abschnitt_text = ft.Text(size=24, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)
    zeit_text = ft.Text(size=84, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    fortschritt = ft.ProgressBar(value=0, bar_height=8, border_radius=4)
    stand_text = ft.Text(size=13, opacity=0.75, text_align=ft.TextAlign.CENTER)
    haupt_knopf = ft.FilledButton(
        height=56, style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=28))
    )
    ablauf = ft.Column(spacing=2)

    def ablauf_zeilen(stand: TimerStand) -> list[ft.Control]:
        zeilen: list[ft.Control] = []
        for i, a in enumerate(profil.abschnitte):
            jetzt = lauf.begonnen and not stand.fertig and i == stand.index
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY) if jetzt else None,
                    content=ft.Row(
                        controls=[
                            ft.Text(dauer_text(a.dauer_s), width=56, weight=ft.FontWeight.W_600),
                            ft.Text(a.name or f"Abschnitt {i + 1}", expand=True),
                            ft.Icon(ft.Icons.PLAY_ARROW, size=16, visible=jetzt),
                        ]
                    ),
                )
            )
        if profil.runden > 1:
            zeilen.append(
                ft.Text(
                    f"× {profil.runden} Runden · gesamt {dauer_text(profil.gesamt_s())}",
                    size=12,
                    opacity=0.7,
                )
            )
        return zeilen

    def anzeigen() -> None:
        stand = lauf.stand()
        if stand.fertig:
            abschnitt_text.value = "Fertig"
            zeit_text.value = "0:00"
            fortschritt.value = 1.0
            stand_text.value = f"{profil.name} · {dauer_text(profil.gesamt_s())}"
        else:
            abschnitt_text.value = stand.name or f"Abschnitt {stand.index + 1}"
            # Vor dem Start die volle Dauer, danach aufgerundet (0:01 bis zuletzt)
            zeit_text.value = dauer_text(-(-stand.rest_s // 1))
            fortschritt.value = stand.anteil
            teile = []
            if profil.runden > 1:
                teile.append(f"Runde {stand.runde} von {profil.runden}")
            if len(profil.abschnitte) > 1:
                teile.append(f"Abschnitt {stand.index + 1} von {len(profil.abschnitte)}")
            teile.append(f"gesamt noch {dauer_text(stand.gesamt_rest_s)}")
            stand_text.value = " · ".join(teile)
        haupt_knopf.disabled = False
        if einheit_ui.besitzt_timer(state, lauf) and not lauf.begonnen:
            # Countdown der Einheit: Sie startet den Timer auf ihren Zeitpunkt
            haupt_knopf.content = _knopf_inhalt(ft.Icons.HOURGLASS_TOP, "Gleich …")
            haupt_knopf.disabled = True
        elif stand.laeuft:
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PAUSE, "Pause")
            haupt_knopf.on_click = anhalten
        else:
            text = "Nochmal" if stand.fertig else ("Weiter" if lauf.begonnen else "Start")
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PLAY_ARROW, text)
            haupt_knopf.on_click = starten
        ablauf.controls = ablauf_zeilen(stand)

    def auffrischen() -> None:
        anzeigen()
        with contextlib.suppress(Exception):
            inhalt.update()

    def starten() -> None:
        if einheit_ui.bereitgestellt(state, "timer"):  # allein starten: aus der Startleiste
            einheit_ui.zuruecknehmen(page, state, "timer")
        lauf.start()
        ticker_starten(page, state)
        auffrischen()

    def bereitstellen() -> None:
        """Auf den gemeinsamen Start warten (Ben, 17.10.2026) — oder wieder heraus."""
        if einheit_ui.bereitgestellt(state, "timer"):
            einheit_ui.zuruecknehmen(page, state, "timer")
        else:
            if lauf.begonnen:
                lauf.zuruecksetzen()
            einheit_ui.timer_bereitstellen(page, state, lauf)

    def anhalten() -> None:
        lauf.pause()
        auffrischen()
        _leisten_auffrischen(state)

    def zuruecksetzen() -> None:
        lauf.zuruecksetzen()
        auffrischen()
        _leisten_auffrischen(state)

    def weiter() -> None:
        lauf.weiter()
        ticker_starten(page, state)
        auffrischen()

    def zurueck() -> None:
        lauf.zurueck()
        auffrischen()

    def waehler(profil_id: str) -> Callable[[], None]:
        def handler() -> None:
            if profil_id == profil.id:
                return
            if einheit_ui.besitzt_timer(state, lauf):  # erst die Einheit beenden
                with contextlib.suppress(Exception):
                    page.show_dialog(
                        ft.SnackBar(ft.Text("Der Timer läuft in der Einheit — erst beenden."))
                    )
                return
            if lauf.laeuft:
                lauf.pause()
            state.timer_profil_waehlen(profil_id)
            state.timer = None
            state.neu_zeichnen()

        return handler

    async def neu() -> None:
        await page.push_route(f"{route}/bearbeiten")

    async def bearbeiten() -> None:
        await page.push_route(f"{route}/bearbeiten/{profil.id}")

    async def signale_oeffnen() -> None:
        await page.push_route(f"{route}/signale")

    profil_chips = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=8,
        controls=[
            ft.Chip(
                label=ft.Text(p.name),
                selected=p.id == profil.id,
                show_checkmark=False,
                on_select=waehler(p.id),
            )
            for p in profile
        ],
    )
    steuerung = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
        controls=[
            ft.IconButton(
                ft.Icons.REPLAY, tooltip="Zurücksetzen", icon_size=28, on_click=zuruecksetzen
            ),
            ft.IconButton(
                ft.Icons.SKIP_PREVIOUS, tooltip="Abschnitt zurück", icon_size=28, on_click=zurueck
            ),
            haupt_knopf,
            ft.IconButton(
                ft.Icons.SKIP_NEXT, tooltip="Nächster Abschnitt", icon_size=28, on_click=weiter
            ),
        ],
    )
    inhalt = ft.Column(
        spacing=14,
        controls=[
            kartentitel(
                "Profil",
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED, tooltip="Profil bearbeiten", on_click=bearbeiten
                ),
                ft.IconButton(ft.Icons.ADD, tooltip="Neues Profil", on_click=neu),
            ),
            profil_chips,
            karte(
                abschnitt_text,
                zeit_text,
                fortschritt,
                stand_text,
                ft.Container(height=4),
                steuerung,
                abstand=10,
            ),
            _bereitstellen_knopf(state, lauf, bereitstellen),
            _signale_vermerk(state, signale_oeffnen),
            karte(kartentitel("Ablauf"), ablauf, abstand=6),
            hinweis(
                "Der Timer läuft weiter, wenn du die Ansicht verlässt — oben in der Leiste "
                "steht dann die Restzeit."
            ),
        ],
    )
    anzeigen()
    state.timer_beobachter["ansicht"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Timer")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


#: Schalter der Karte „Signale": Feld in `TimerSignale`, Titel, Erklärung
SIGNAL_SCHALTER: list[tuple[str, str, str]] = [
    ("ton", "Ton", "Zwei Töne beim Wechsel, vier am Ende. Musik wird dabei nur kurz leiser."),
    ("countdown", "Countdown 3 – 2 – 1", "Kurze Töne in den letzten drei Sekunden."),
    ("vibration", "Vibration", "Beim Wechsel einmal, am Ende zweimal."),
    (
        "wach",
        "Bildschirm anlassen",
        "Solange der Timer läuft. Schläft das Handy, bleiben Töne und Vibration aus.",
    ),
    (
        "notizen",
        "Abschnitte in die HRV-Messung",
        "Läuft eine Aufnahme, wird jeder Abschnitt eine Notiz in der Messung — "
        "nachträglich umbenennen, verschieben oder löschen wie jede Notiz.",
    ),
]


def _signale_vermerk(state: AppState, oeffnen: Callable[[], object]) -> ft.Control:
    """Knapp unter dem Timer: welche Signale an sind — rechts das Zahnrad."""
    return ft.Container(
        padding=ft.Padding.only(left=12, right=0),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.NOTIFICATIONS_OUTLINED, size=16, opacity=0.6),
                ft.Text(signale_kurz(state.timer_signale()), size=12, opacity=0.7, expand=True),
                ft.IconButton(
                    ft.Icons.SETTINGS_OUTLINED,
                    icon_size=20,
                    tooltip="Signale einstellen",
                    on_click=oeffnen,
                ),
            ],
        ),
    )


def timer_signale_view(page: Any, state: AppState, basis: str) -> ft.View:
    """Eigene Seite für die Signale — Route `<basis>/timer/signale`."""
    return ft.View(
        route=f"{timer_route(basis)}/signale",
        appbar=ft.AppBar(title=ft.Text("Timer-Signale")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        _klang_karte(page, state),
                        _lautstaerke_karte(page, state),
                        _signale_karte(page, state),
                        hinweis("Gilt für alle Timer-Profile auf diesem Gerät."),
                    ],
                ),
                expand=False,
            )
        ],
    )


def _vorspielen(page: Any, state: AppState, klang: str) -> None:
    """Einen Klang zur Probe — mit Regler und Lautstärke, wie eingestellt."""

    async def spielen() -> None:
        if not await ton_spielen(state, klang):
            with contextlib.suppress(Exception):
                page.show_dialog(ft.SnackBar(ft.Text("Töne gibt es nur in der installierten App.")))

    with contextlib.suppress(Exception):
        page.run_task(spielen)


def _klang_karte(page: Any, state: AppState) -> ft.Control:
    """Der Standardklang beim Abschnittswechsel — antippen wählt und spielt vor."""
    reihe = ft.Row(wrap=True, spacing=8, run_spacing=8)

    def zeichnen() -> None:
        aktuell = state.timer_signale().klang
        reihe.controls = [
            ft.Chip(
                label=ft.Text(text),
                leading=ft.Icon(ft.Icons.MUSIC_NOTE_OUTLINED, size=16),
                selected=key == aktuell,
                show_checkmark=False,
                on_select=waehler(key),
            )
            for key, text in KLAENGE.items()
        ]

    def waehler(key: str) -> Callable[[], None]:
        def handler() -> None:
            signale = state.timer_signale()
            signale.klang = key
            state.timer_signale_setzen(signale)
            _vorspielen(page, state, key)
            zeichnen()
            with contextlib.suppress(Exception):
                reihe.update()

        return handler

    zeichnen()
    return karte(
        kartentitel("Klang beim Wechsel"),
        reihe,
        hinweis(
            "Antippen wählt und spielt vor. Eigene Klänge je Abschnitt, für jede neue Runde "
            "und fürs Ende stellst du im Timer-Profil ein (Stift beim Profil)."
        ),
        abstand=10,
    )


#: Erklärung je Lautstärkeregler (Android)
QUELLE_HINWEIS: dict[str, str] = {
    "medien": "Wie Musik und Videos — die Lautstärketasten regeln ihn in der App, "
    "mit Kopfhörern kommt der Ton dort an. Bei stummen Medien bleibt es still.",
    "wecker": "Tönt auch, wenn Medien leise sind, immer auch über den Lautsprecher. "
    "Gut, wenn das Handy beim Training weiter weg liegt.",
    "klingelton": "Folgt dem Klingelton-/Systemregler (so war es bisher). "
    "Ist das Handy lautlos, bleibt es still.",
}


def _lautstaerke_karte(page: Any, state: AppState) -> ft.Control:
    """Welcher Regler des Systems und wie viel davon."""
    signale = state.timer_signale()
    ios = getattr(page, "platform", None) == ft.PagePlatform.IOS
    erklaerung = hinweis(QUELLE_HINWEIS[signale.quelle])
    prozent = ft.Text(f"{signale.lautstaerke} %", width=52, text_align=ft.TextAlign.END)

    def quelle_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        aktuell = state.timer_signale()
        aktuell.quelle = next(iter(e.control.selected or []), aktuell.quelle)
        state.timer_signale_setzen(aktuell)
        erklaerung.value = QUELLE_HINWEIS[aktuell.quelle]
        with contextlib.suppress(Exception):
            erklaerung.update()
        _vorspielen(page, state, aktuell.klang)

    def gezogen(e: ft.Event[ft.Slider]) -> None:
        prozent.value = f"{round(e.control.value or 0)} %"
        with contextlib.suppress(Exception):
            prozent.update()

    def losgelassen(e: ft.Event[ft.Slider]) -> None:
        aktuell = state.timer_signale()
        aktuell.lautstaerke = round(e.control.value or 100)
        state.timer_signale_setzen(aktuell)
        _vorspielen(page, state, aktuell.klang)

    regler = ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.VOLUME_DOWN_OUTLINED, size=20, opacity=0.7),
            ft.Slider(
                min=10,
                max=100,
                divisions=9,
                value=signale.lautstaerke,
                expand=True,
                on_change=gezogen,
                on_change_end=losgelassen,
            ),
            prozent,
        ],
    )
    zeilen: list[ft.Control] = [kartentitel("Lautstärke")]
    if ios:
        zeilen.append(
            hinweis(
                "Auf dem iPhone folgen die Töne der Medienlautstärke — einen anderen Regler "
                "gibt es für Apps nicht. Mit Stummschalter bleiben sie still."
            )
        )
    else:
        zeilen += [
            ft.SegmentedButton(
                selected=[signale.quelle],
                segments=[
                    ft.Segment(value=key, label=ft.Text(text)) for key, text in QUELLEN.items()
                ],
                on_change=quelle_gewaehlt,
            ),
            erklaerung,
        ]
    zeilen += [
        regler,
        hinweis(
            "Anteil des Reglers: 100 % = so laut, wie das Handy gerade eingestellt ist. "
            "Loslassen spielt den Klang vor."
        ),
    ]
    return karte(*zeilen, abstand=10)


def _signale_karte(page: Any, state: AppState) -> ft.Control:
    """Wie sich der Timer meldet — Schalter, sofort gespeichert."""
    signale = state.timer_signale()

    def umschalter(feld: str) -> Callable[[ft.Event[ft.Switch]], None]:
        def handler(ev: ft.Event[ft.Switch]) -> None:
            aktuell = state.timer_signale()
            setattr(aktuell, feld, bool(ev.control.value))
            state.timer_signale_setzen(aktuell)
            lauf: TimerLauf | None = state.timer
            if feld == "wach" and lauf is not None and lauf.laeuft:
                page.run_task(_wach, state, aktuell.wach)

        return handler

    zeilen: list[ft.Control] = [kartentitel("Signale")]
    for feld, titel, erklaerung in SIGNAL_SCHALTER:
        zeilen.append(
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(titel, size=14),
                            ft.Text(erklaerung, size=11, opacity=0.65),
                        ],
                    ),
                    ft.Switch(value=getattr(signale, feld), on_change=umschalter(feld)),
                ],
            )
        )
    if state.ton is None:
        zeilen.append(hinweis("Töne gibt es nur in der installierten App, nicht in der Vorschau."))
    return karte(*zeilen, abstand=10)


#: Schlüssel der Auswahl „wie vorgegeben" (ein leerer Schlüssel taugt im Dropdown nicht)
_VORGABE = "vorgabe"


def _klang_wahl(page: Any, state: AppState, wert: str, vorgabe: str) -> ft.Dropdown:
    """Klang für einen Abschnitt, die Runde oder das Ende — Auswählen spielt ihn vor."""

    def gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        klang = e.control.value or _VORGABE
        if klang != _VORGABE:
            _vorspielen(page, state, klang)

    return ft.Dropdown(
        value=wert or _VORGABE,
        options=[
            ft.DropdownOption(key=_VORGABE, text=vorgabe),
            *(ft.DropdownOption(key=k, text=t) for k, t in KLAENGE.items()),
        ],
        leading_icon=ft.Icons.MUSIC_NOTE_OUTLINED,
        dense=True,
        width=240,
        on_select=gewaehlt,
    )


def _klang_wert(wahl: ft.Dropdown) -> str:
    """Der gewählte Klang — leer für „wie vorgegeben“."""
    wert = wahl.value or ""
    return "" if wert == _VORGABE or wert not in KLAENGE else wert


def _bereitstellen_knopf(
    state: AppState, lauf: TimerLauf, umschalten: Callable[[], None]
) -> ft.Control:
    """„Bereitstellen“ neben dem Start: Der Timer wartet in der Startleiste auf den
    gemeinsamen Start mit Messung, GPS … (Ben, 17.10.2026). In einer laufenden
    Einheit steht nur, dass er dazugehört."""
    if einheit_ui.besitzt_timer(state, lauf):
        return hinweis("Der Timer läuft in der Einheit — oben in der Laufleiste.")
    if einheit_ui.bereitgestellt(state, "timer"):
        return ft.FilledTonalButton(
            "Bereitgestellt", icon=ft.Icons.CHECK, on_click=umschalten, tooltip="Herausnehmen"
        )
    return ft.OutlinedButton(
        "Bereitstellen",
        icon=ft.Icons.HOURGLASS_TOP,
        on_click=umschalten,
        tooltip="Mit Messung oder GPS zusammen starten — in der Startleiste",
    )


def _knopf_inhalt(icon: ft.IconData, text: str) -> ft.Control:
    return ft.Row(
        tight=True,
        spacing=8,
        controls=[ft.Icon(icon, size=26), ft.Text(text, size=18, weight=ft.FontWeight.W_600)],
    )


def _leisten_auffrischen(state: AppState) -> None:
    for name, beobachter in list(state.timer_beobachter.items()):
        if name != "ansicht":
            with contextlib.suppress(Exception):
                beobachter()


# ---------------------------------------------------------------------------
# Profil bearbeiten
# ---------------------------------------------------------------------------


def timer_bearbeiten_view(page: Any, state: AppState, profil_id: str | None, basis: str) -> ft.View:
    """Name, Abschnitte (Name, mm:ss, Klang), Runden und ihre Klänge — anlegen oder ändern.

    Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen" verwirft.
    """
    zurueck_route = timer_route(basis)
    profile = state.timer_profile()
    vorhanden = next((p for p in profile if p.id == profil_id), None)
    profil = vorhanden or TimerProfil(
        name="", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=1
    )
    route = f"{zurueck_route}/bearbeiten" + (f"/{vorhanden.id}" if vorhanden else "")

    name = ft.TextField(label="Name", value=profil.name, hint_text="z. B. Intervall, Planke")
    zeilen: list[tuple[ft.TextField, ft.TextField, ft.Dropdown]] = []
    zeilen_spalte = ft.Column(spacing=14)
    runden_klang = _klang_wahl(page, state, profil.runden_klang, "wie Abschnitt 1")
    ende_klang = _klang_wahl(page, state, profil.ende_klang, "Fanfare")
    runden = {"n": profil.runden}
    runden_text = ft.Text(
        str(profil.runden),
        size=18,
        weight=ft.FontWeight.W_600,
        width=36,
        text_align=ft.TextAlign.CENTER,
    )
    gesamt_text = ft.Text(size=13, opacity=0.75)

    def gesamt() -> None:
        summe = sum(dauer_lesen(d.value or "") or 0 for _, d, _ in zeilen)
        gesamt_text.value = f"Gesamt {dauer_text(summe * runden['n'])}"

    def zeichnen() -> None:
        zeilen_spalte.controls = [
            ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(expand=True, content=n),
                            ft.Container(width=96, content=d),
                            ft.IconButton(
                                ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                tooltip="Abschnitt entfernen",
                                on_click=entferner(i),
                                disabled=len(zeilen) <= 1,
                            ),
                        ],
                    ),
                    k,
                ],
            )
            for i, (n, d, k) in enumerate(zeilen)
        ]
        gesamt()

    def dauer_geaendert() -> None:
        gesamt()
        with contextlib.suppress(Exception):
            gesamt_text.update()

    def zeile(a: Abschnitt) -> tuple[ft.TextField, ft.TextField, ft.Dropdown]:
        return (
            ft.TextField(label="Abschnitt", value=a.name, dense=True),
            ft.TextField(
                label="mm:ss",
                value=dauer_text(a.dauer_s),
                dense=True,
                keyboard_type=ft.KeyboardType.DATETIME,
                text_align=ft.TextAlign.END,
                on_change=lambda _: dauer_geaendert(),
            ),
            _klang_wahl(page, state, a.klang, "Standardklang"),
        )

    def entferner(i: int) -> Callable[[], None]:
        def handler() -> None:
            if len(zeilen) > 1:
                del zeilen[i]
                zeichnen()
                page.update()

        return handler

    def hinzufuegen() -> None:
        zeilen.append(zeile(Abschnitt("", 60)))
        zeichnen()
        page.update()

    def runden_aendern(delta: int) -> Callable[[], None]:
        def handler() -> None:
            runden["n"] = min(max(runden["n"] + delta, 1), MAX_RUNDEN)
            runden_text.value = str(runden["n"])
            gesamt()
            page.update()

        return handler

    def stand() -> tuple[Any, ...]:
        """Alles, was man hier ändern kann — für „Zurück speichert“ (Ben, 16.10.2026)."""
        return (
            name.value or "",
            [(n.value or "", d.value or "", k.value) for n, d, k in zeilen],
            runden["n"],
            runden_klang.value,
            ende_klang.value,
        )

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        abschnitte: list[Abschnitt] = []
        fehler = False
        for n, d, k in zeilen:
            dauer = dauer_lesen(d.value or "")
            d.error = None if dauer else "z. B. 0:30"
            fehler = fehler or dauer is None
            if dauer:
                abschnitte.append(Abschnitt((n.value or "").strip(), dauer, _klang_wert(k)))
        if fehler or not abschnitte:
            page.update()
            return "Eine Dauer ist unlesbar — so: 0:30 oder 1:15."
        neu = TimerProfil(
            id=profil.id,
            name=(name.value or "").strip() or "Timer",
            abschnitte=abschnitte,
            runden=runden["n"],
            runden_klang=_klang_wert(runden_klang),
            ende_klang=_klang_wert(ende_klang),
        )
        andere = [p for p in state.timer_profile() if p.id != neu.id]
        if vorhanden is not None:
            liste = [neu if p.id == neu.id else p for p in state.timer_profile()]
        else:
            liste = [*andere, neu]
        state.timer_profile_setzen(liste)
        state.timer_profil_waehlen(neu.id)
        gespeichert["name"] = neu.name
        return None

    #: Name des zuletzt gespeicherten Profils — für die Meldung
    gespeichert: dict[str, str] = {}

    async def speichern() -> None:
        if sichern() is not None:
            return
        page.show_dialog(ft.SnackBar(ft.Text(f"„{gespeichert['name']}“ gespeichert")))
        await page.push_route(zurueck_route)

    nachher = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def loeschen() -> None:
        rest = [p for p in state.timer_profile() if p.id != profil.id]
        state.timer_profile_setzen(rest)
        if state.timer is not None and state.timer.profil.id == profil.id:
            state.timer = None
        nachher.danach(lambda: page.push_route(zurueck_route))
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{profil.name}“ gelöscht")))

    def loeschen_fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Profil löschen?"),
                content=ft.Text(
                    "Gibt es danach kein eigenes Profil mehr, kommen die zwei Vorlagen zurück."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Löschen", on_click=loeschen),
                ],
            )
        )

    async def abbrechen() -> None:
        await page.push_route(zurueck_route)

    zeilen.extend(zeile(a) for a in profil.abschnitte)
    zeichnen()
    anfang = stand()

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text("Timer-Profil" if vorhanden else "Neues Timer-Profil"),
            actions=[
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE, tooltip="Profil löschen", on_click=loeschen_fragen
                )
            ]
            if vorhanden
            else [],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=16,
                    controls=[
                        name,
                        karte(
                            kartentitel("Abschnitte"),
                            hinweis(
                                "Je Abschnitt ein Name, die Dauer in Minuten:Sekunden und der "
                                "Klang, mit dem er beginnt — etwa Glocke 1 für Belastung, "
                                "Glocke 3 für die Pause."
                            ),
                            zeilen_spalte,
                            ft.TextButton(
                                "Abschnitt hinzufügen", icon=ft.Icons.ADD, on_click=hinzufuegen
                            ),
                        ),
                        karte(
                            kartentitel("Runden"),
                            ft.Row(
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.IconButton(ft.Icons.REMOVE, on_click=runden_aendern(-1)),
                                    runden_text,
                                    ft.IconButton(ft.Icons.ADD, on_click=runden_aendern(1)),
                                    ft.Container(width=8),
                                    gesamt_text,
                                ],
                            ),
                            hinweis("Alle Abschnitte so oft nacheinander."),
                        ),
                        karte(
                            kartentitel("Klänge"),
                            ft.Text("Zu Beginn jeder neuen Runde", size=13),
                            runden_klang,
                            ft.Text("Am Ende", size=13),
                            ende_klang,
                            hinweis(
                                "Auswählen spielt den Klang vor. Regler und Lautstärke: "
                                "Zahnrad unter dem Timer."
                            ),
                            abstand=8,
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: stand() != anfang,
        speichern=sichern,
        meldung="Timer-Profil gespeichert",
    )


__all__ = [
    "lauf_fuer",
    "ticker_starten",
    "timer_bearbeiten_view",
    "timer_knopf",
    "timer_route",
    "timer_signale_view",
    "timer_view",
]
