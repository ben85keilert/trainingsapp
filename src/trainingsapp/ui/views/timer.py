"""Timer als Werkzeug — Route `<irgendwo>/timer`, Profil bearbeiten `…/timer/bearbeiten[/<id>]`,
Signale einstellen `…/timer/signale`.

Der Timer ist von überall erreichbar (Symbol oben in der Leiste) und legt sich
über die aktuelle Ansicht: „Zurück" führt dorthin, wo man war — aus einem
Plan zurück in den Plan. Er läuft weiter, wenn man die Ansicht verlässt; die
Leiste zeigt dann die Restzeit (`timer_knopf`).

**Stoppuhr und Timer sind die Vorgabe** (Ben, 19.10.2026) — drei Reiter oben:
Stoppuhr, Timer, Profile. Die Einmaluhren (`core.timer.stoppuhr`, `einmal_timer`)
haben einen Namen (optional) und den Schalter, ob er in die Marken von HRV und
Strecke kommt; der Timer zählt eine Dauer rückwärts. Abschnitte und Runden baut
der Editor auch für den Einmal-Timer — ohne Namen, ohne zu speichern; „Als Profil
speichern“ fragt dann erst nach einem Namen.

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

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import flet as ft

from trainingsapp.core.klang import KLAENGE
from trainingsapp.core.models import new_id
from trainingsapp.core.result_spec import FieldType, ResultSpec
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import (
    EINMAL,
    MAX_RUNDEN,
    QUELLEN,
    STOPPUHR,
    Abschnitt,
    Teil,
    TimerLauf,
    TimerProfil,
    TimerStand,
    dauer_text,
    einmal_timer,
    schnellzeit_text,
    signale_kurz,
    stoppuhr,
)
from trainingsapp.core.uebung_timer import (
    ausfuehrung_text,
    ausfuehrungs_vorschau,
    ausfuehrungsfelder,
    timer_fuer,
)
from trainingsapp.devices.einheit import TimerBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import TIMER_EDITOR_MD
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.takt_anzeige import ZeitMitTakt, takt_gross
from trainingsapp.ui.components.takt_blatt import (
    SYMBOL as TAKT_SYMBOL,
)
from trainingsapp.ui.components.takt_blatt import (
    TempoRegler,
    takt_anbringen,
    takt_blatt,
    takt_knopf,
    takt_zeile_text,
)
from trainingsapp.ui.components.zeit_stellen import zeit_blatt
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import ticker_starten, toene_laden, ton_spielen, wach_setzen

#: Der dritte Reiter neben Stoppuhr und Timer — die Bibliothek der Profile
PROFILE = "profile"
#: Der vierte Reiter: alle Timer an einem Ort (`views/alle_timer.py`)
ALLE = "alle"


def timer_route(basis: str) -> str:
    """Die Timer-Route über einer Ansicht.

    >>> timer_route("/"), timer_route("/plan/abc")
    ('/timer', '/plan/abc/timer')
    """
    return basis.rstrip("/") + "/timer"


# ---------------------------------------------------------------------------
# Ablauf: Lauf holen, Ticker
# ---------------------------------------------------------------------------


#: Schlüssel der Takt-Wahl „für jetzt“ im Reiter „Timer“ (`AppState.uhr_takt`)
TAKT_KEY = "timer"


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
    if (
        lauf is not None
        and lauf.profil.ist_einmal
        and lauf.profil.id == profil.id
        and lauf.begonnen
        and not lauf.fertig
    ):
        return lauf  # eine laufende Einmaluhr: neue Einstellungen gelten ab dem nächsten Start
    if lauf is None or lauf.profil != profil:
        lauf = TimerLauf(profil)
        takt_anbringen(state, lauf, TAKT_KEY, None)  # der Takt „für jetzt“ des Reiters
        state.timer = lauf
        e = einheit_ui.in_vorbereitung(state)
        if e is not None and (teil := e.timer) is not None:
            teil.lauf = lauf
            teil.uhr_uebernehmen(e.uhr)
    return lauf


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
        text.value = lauf.anzeige() if aktiv and lauf is not None else "Timer"
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
    """Stoppuhr, Einmal-Timer und Profile — drei Reiter oben (Ben, 19.10.2026: „Einmaluhren
    der Standard, Profile sind komplexer gebaut“). Stoppuhr und Timer haben einen Namen
    (optional) und den Schalter, ob er in die Marken kommt; der Timer eine Dauer, und wer
    Abschnitte oder Runden braucht, öffnet den Editor — ohne Namen, ohne zu speichern."""
    route = timer_route(basis)
    profile = state.timer_profile()
    profil = state.timer_profil()
    lauf = lauf_fuer(state, profil)
    reiter = profil.id if profil.ist_einmal else PROFILE
    #: Läuft die Uhr gerade (angehalten zählt mit)? Dann bleiben Dauer und Abschnitte
    laufend = lauf.begonnen and not lauf.fertig and not lauf.abgebrochen

    abschnitt_text = ft.Text(size=24, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)
    # Takt · Zeit in einer Zeile (Ben, 9.11.2026: „nebeneinander, den Takt etwas kleiner als die
    # Uhrzeit“) — dieselbe Form wie im Fokus und in der laufenden Uhr der Übung; antippen → groß
    uhr = ZeitMitTakt(84, on_takt=lambda: takt_gross(page, state, lauf))
    fortschritt = ft.ProgressBar(value=0, bar_height=8, border_radius=4)
    stand_text = ft.Text(size=13, opacity=0.75, text_align=ft.TextAlign.CENTER)
    haupt_knopf = ft.FilledButton(
        height=56, style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=28))
    )
    ablauf = ft.Column(spacing=2)
    # Taktgeber (`docs/plan_taktgeber.md` §5): die Animation neben der Zeit (`uhr`), der
    # Tempo-Regler für jetzt, die Zeile mit dem gewählten Takt — einmal gebaut, je Tick nachgezogen
    tempo_regler = TempoRegler(state, TAKT_KEY, lauf)
    takt_text = ft.Text(size=12, opacity=0.75, text_align=ft.TextAlign.CENTER)

    def ablauf_zeilen(stand: TimerStand) -> list[ft.Control]:
        """Die Abschnitte je Teil — eine Folge (Vorbereitung, Training, Cooldown) mit
        Überschrift und Runden je Teil; der laufende Abschnitt ist hervorgehoben."""
        teile = profil.alle_teile()
        if len(teile) > 1:
            return [z for k, t in enumerate(teile) for z in teil_zeilen(stand, k, t, True)]
        return teil_zeilen(stand, 0, teile[0], False)

    def teil_zeilen(stand: TimerStand, k: int, teil: Teil, folge: bool) -> list[ft.Control]:
        zeilen: list[ft.Control] = []
        if folge:
            kopf = teil.name or f"Teil {k + 1}"
            if teil.runden > 1:
                kopf += f" · {teil.runden} Runden"
            zeilen.append(ft.Text(kopf, size=12, weight=ft.FontWeight.W_600, opacity=0.8))
        for i, a in enumerate(teil.abschnitte):
            jetzt = lauf.begonnen and not stand.fertig and i == stand.index and k == stand.teil
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY) if jetzt else None,
                    content=ft.Row(
                        controls=[
                            ft.Text(dauer_text(a.dauer_s), width=56, weight=ft.FontWeight.W_600),
                            ft.Text(a.name or f"Abschnitt {i + 1}", expand=True),
                            ft.Text("zählt nicht", size=11, opacity=0.6, visible=not a.zaehlt),
                            ft.Icon(ft.Icons.PLAY_ARROW, size=16, visible=jetzt),
                        ]
                    ),
                )
            )
        if not folge and teil.runden > 1:
            zeilen.append(
                ft.Text(
                    f"× {teil.runden} Runden · gesamt {dauer_text(profil.gesamt_s())}",
                    size=12,
                    opacity=0.7,
                )
            )
        return zeilen

    def anzeigen() -> None:
        stand = lauf.stand()
        fortschritt.visible = not lauf.vorwaerts
        if lauf.vorwaerts:  # die Stoppuhr (Ben, 18.10.2026): vorwärts, ohne Abschnitte
            abschnitt_text.value = profil.anzeigename
            zeit = lauf.anzeige()
            if stand.fertig:
                stand_text.value = "fertig"
            elif stand.laeuft:
                stand_text.value = "läuft — „Fertig“, wenn du fertig bist"
            elif lauf.begonnen:
                stand_text.value = "angehalten — „Weiter“ zählt weiter"
            else:
                stand_text.value = "zählt vorwärts, bis du „Fertig“ tippst"
        elif stand.fertig:
            abschnitt_text.value = "Fertig"
            zeit = "0:00"
            fortschritt.value = 1.0
            stand_text.value = f"{profil.anzeigename} · {dauer_text(profil.gesamt_s())}"
        else:
            abschnitt_text.value = stand.name or f"Abschnitt {stand.index + 1}"
            # Vor dem Start die volle Dauer, danach aufgerundet (0:01 bis zuletzt)
            zeit = dauer_text(-(-stand.rest_s // 1))
            fortschritt.value = stand.anteil
            teile = []
            if len(profil.alle_teile()) > 1:
                teil = profil.alle_teile()[stand.teil]
                teile.append(teil.name or f"Teil {stand.teil + 1}")
            if stand.runden > 1:
                teile.append(f"Runde {stand.runde} von {stand.runden}")
            if stand.abschnitte > 1:
                teile.append(f"Abschnitt {stand.index + 1} von {stand.abschnitte}")
            teile.append(f"gesamt noch {dauer_text(stand.gesamt_rest_s)}")
            stand_text.value = " · ".join(teile)
        fertig_knopf.visible = lauf.vorwaerts and lauf.begonnen and not stand.fertig
        haupt_knopf.disabled = False
        if einheit_ui.besitzt_timer(state, lauf) and not lauf.begonnen:
            # Countdown der Einheit: Sie startet den Timer auf ihren Zeitpunkt
            haupt_knopf.content = _knopf_inhalt(ft.Icons.HOURGLASS_TOP, "Gleich …")
            haupt_knopf.disabled = True
        elif stand.laeuft:
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PAUSE, "Pause")
            haupt_knopf.on_click = anhalten
        else:
            text = "Noch einmal" if stand.fertig else ("Weiter" if lauf.begonnen else "Start")
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PLAY_ARROW, text)
            haupt_knopf.on_click = starten
        ablauf.controls = [] if lauf.vorwaerts else ablauf_zeilen(stand)
        takt = lauf.takt_aktuell(stand.nummer) if not stand.fertig else None
        lage = lauf.takt_lage()
        uhr.nachziehen(zeit, lauf.takt_effektiv() if lage else None, lage)  # mit Tempo
        tempo_regler.nachziehen(lage is not None)
        takt_text.value = f"Takt: {takt.anzeigename} · {takt.kurztext()}" if takt else ""
        takt_text.visible = bool(takt_text.value) and lage is None

    def auffrischen() -> None:
        anzeigen()
        with contextlib.suppress(Exception):
            inhalt.update()

    def starten() -> None:
        if einheit_ui.bereitgestellt(state, "timer"):  # allein starten: aus der Startleiste
            einheit_ui.zuruecknehmen(page, state, "timer")
        # Für sich gestartet — trotzdem in die Leiste und in den Reiter „Einheit“, mit Runden
        # und Abschnitten (Ben, 18.10.2026): als eigene Einheit oder in der, die schon läuft
        von_vorn = not lauf.begonnen or lauf.fertig or lauf.abgebrochen
        if (
            von_vorn
            and not einheit_ui.besitzt_timer(state, lauf)
            and einheit_ui.einzeln_starten(page, state, TimerBaustein(lauf)) is not None
        ):
            auffrischen()
            return
        lauf.start()
        ticker_starten(page, state)
        auffrischen()

    def zeit_gestellt(sekunden: int) -> None:
        """Ein Tipp auf die Zeit (Ben, 22.10.2026, P79 D4): Timer ohne Ablauf stellen und gleich
        starten — wie in der Android-Uhr; aus der Stoppuhr wird dabei der Timer."""
        name = profil.name if profil.ist_einmal else ""
        neu = einmal_timer(sekunden, name, name_in_marken=profil.name_in_marken)
        state.timer_einmal_setzen(neu)
        state.timer_profil_waehlen(EINMAL)
        if not einheit_ui.besitzt_timer(state, state.timer):
            state.timer = None
        neuer = lauf_fuer(state, neu)
        if einheit_ui.einzeln_starten(page, state, TimerBaustein(neuer)) is None:
            neuer.start()
            ticker_starten(page, state)
        state.neu_zeichnen()

    def zeit_stellen() -> None:
        if laufend:
            return
        vorher = 60 if profil.ist_stoppuhr else profil.gesamt_s()
        page.show_dialog(zeit_blatt(vorher, starten=zeit_gestellt, schnell=state.schnellzeiten()))

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

    def fertig() -> None:
        """Die Stoppuhr anhalten und beenden — ihre Einheit endet mit ihr."""
        lauf.fertig_machen()
        auffrischen()
        _leisten_auffrischen(state)

    def zurueck() -> None:
        lauf.zurueck()
        auffrischen()

    def in_einheit() -> bool:
        """Der Timer gehört einer laufenden Einheit — erst beenden, dann umschalten."""
        if einheit_ui.besitzt_timer(state, lauf):
            with contextlib.suppress(Exception):
                page.show_dialog(
                    ft.SnackBar(ft.Text("Der Timer läuft in der Einheit — erst beenden."))
                )
            return True
        return False

    def umschalten(profil_id: str) -> None:
        """Eine andere Uhr: merken, der nächste Aufbau holt sich ihren Lauf."""
        if profil_id == profil.id or in_einheit():
            return
        if lauf.laeuft:
            lauf.pause()
        state.timer_profil_waehlen(profil_id)
        state.timer = None
        state.neu_zeichnen()

    def waehler(profil_id: str) -> Callable[[], None]:
        return lambda: umschalten(profil_id)

    def reiter_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        neu = next(iter(e.control.selected or []), reiter)
        if neu == reiter:
            return
        if neu == ALLE:  # eine eigene Seite über dem Timer — der Reiter bleibt, wie er war
            e.control.selected = [reiter]

            async def gehen() -> None:
                await page.push_route(f"{route}/alle")

            page.run_task(gehen)
            return
        umschalten(state.timer_profil_bibliothek().id if neu == PROFILE else neu)

    async def neu() -> None:
        await page.push_route(f"{route}/bearbeiten")

    async def bearbeiten() -> None:
        await page.push_route(f"{route}/bearbeiten/{profil.id}")

    async def signale_oeffnen() -> None:
        await page.push_route(f"{route}/signale")

    # -- Die Einmaluhr einstellen (Ben, 19.10.2026) ----------------------------------

    def einmal_merken(neu: TimerProfil) -> None:
        """Name, Schalter, Dauer der Einmaluhr merken. Läuft sie gerade, kommen nur Name und
        Schalter in den Lauf (`_in_lauf_uebernehmen`); sonst folgt ihr der nächste Lauf."""
        nonlocal profil
        state.timer_einmal_setzen(neu)
        profil = neu
        if laufend or einheit_ui.besitzt_timer(state, lauf):
            _in_lauf_uebernehmen(lauf, neu)
        else:
            state.timer = None

    def mit_name(name: str, in_marken: bool) -> TimerProfil:
        """Die Einmaluhr mit diesem Namen und Schalter — die Dauer bzw. Abschnitte bleiben."""
        if profil.ist_stoppuhr:
            return stoppuhr(name, name_in_marken=in_marken)
        if profil.einfach:
            return einmal_timer(profil.gesamt_s(), name, name_in_marken=in_marken)
        return replace(profil, name=name, name_in_marken=in_marken)

    def name_geaendert(_e: object = None) -> None:
        einmal_merken(mit_name((name_feld.value or "").strip(), marken_schalter.value))

    def dauer_setzen(sekunden: int) -> None:
        einmal_merken(einmal_timer(sekunden, profil.name, name_in_marken=profil.name_in_marken))
        state.neu_zeichnen()

    def dauer_waehler(sekunden: int) -> Callable[[], None]:
        return lambda: dauer_setzen(sekunden)

    def nur_eine_dauer() -> None:
        """Abschnitte und Runden verwerfen — nur noch eine Dauer (die bisherige Summe)."""
        dauer_setzen(profil.gesamt_s())

    async def abschnitte_bearbeiten() -> None:
        await page.push_route(f"{route}/bearbeiten/{EINMAL}")

    name_feld = ft.TextField(
        label="Name (optional)",
        value=profil.name if profil.ist_einmal else "",
        hint_text="z. B. Dehnen",
        dense=True,
        on_change=name_geaendert,
    )
    marken_schalter = ft.Switch(
        label="Name in die Marken (HRV, Strecke)",
        value=profil.name_in_marken,
        on_change=name_geaendert,
    )

    def einmal_karte() -> ft.Control:
        """Name und Schalter — beim Timer davor die Dauer oder die Abschnitte."""
        zeilen: list[ft.Control] = []
        if profil.id == EINMAL and profil.einfach:
            # Die Zeit stellt man oben am Etikett (Zeit-Blatt); hier nur die Schnellzeiten
            # aus den Einstellungen (Ben, 8.11.2026: kein Eingabefeld)
            zeilen += [
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Chip(
                            label=ft.Text(schnellzeit_text(s)),
                            selected=s == profil.gesamt_s(),
                            show_checkmark=False,
                            disabled=laufend,
                            on_select=dauer_waehler(s),
                        )
                        for s in state.schnellzeiten()
                    ],
                ),
                ft.TextButton(
                    "Abschnitte und Runden …",
                    icon=ft.Icons.PLAYLIST_ADD,
                    tooltip="Mehrere Abschnitte, Runden, Klänge — ohne Namen, ohne Speichern",
                    on_click=abschnitte_bearbeiten,
                    disabled=laufend,
                ),
            ]
        elif profil.id == EINMAL:
            zeilen += [
                ft.Text(profil.kurztext(), size=13),
                ft.Row(
                    wrap=True,
                    spacing=4,
                    controls=[
                        ft.TextButton(
                            "Bearbeiten",
                            icon=ft.Icons.EDIT_OUTLINED,
                            on_click=abschnitte_bearbeiten,
                            disabled=laufend,
                        ),
                        ft.TextButton(
                            "Nur eine Dauer",
                            icon=ft.Icons.UNDO,
                            tooltip="Abschnitte und Runden verwerfen",
                            on_click=nur_eine_dauer,
                            disabled=laufend,
                        ),
                    ],
                ),
            ]
        zeilen += [name_feld, marken_schalter]
        return karte(*zeilen, abstand=8)

    reiter_wahl = ft.SegmentedButton(
        selected=[reiter],
        show_selected_icon=False,
        segments=[
            ft.Segment(value=STOPPUHR, label=ft.Text("Stoppuhr"), icon=ft.Icon(ft.Icons.AV_TIMER)),
            ft.Segment(
                value=EINMAL, label=ft.Text("Zeit"), icon=ft.Icon(ft.Icons.HOURGLASS_BOTTOM)
            ),
            ft.Segment(
                value=PROFILE,
                label=ft.Text("Vorlagen"),
                icon=ft.Icon(ft.Icons.FORMAT_LIST_BULLETED),
            ),
            # Alle Timer an einem Ort (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §5)
            ft.Segment(value=ALLE, label=ft.Text("Alle"), icon=ft.Icon(ft.Icons.APPS)),
        ],
        on_change=reiter_gewaehlt,
    )
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
    fertig_knopf = ft.IconButton(
        ft.Icons.STOP, tooltip="Fertig", icon_size=28, on_click=fertig, visible=False
    )

    def takt_starten(takt: Takt) -> None:
        """„Takt starten“ aus dem Blatt: dieser Takt für jetzt, und die Uhr läuft los."""
        state.uhr_takt[TAKT_KEY] = takt
        lauf.takt_jetzt = takt
        if not lauf.laeuft:
            starten()
        state.neu_zeichnen()

    takt_wahl = takt_knopf(
        page,
        state,
        key=TAKT_KEY,
        takt=lauf.takt_aktuell(),
        lauf=lauf,
        starten=None if laufend else takt_starten,
        titel="Takt für jetzt",
    )
    ohne_abschnitte = profil.ist_stoppuhr or (profil.ist_einmal and profil.einfach)
    steuerung = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
        controls=[
            ft.IconButton(
                ft.Icons.REPLAY, tooltip="Zurücksetzen", icon_size=28, on_click=zuruecksetzen
            ),
            ft.IconButton(
                ft.Icons.SKIP_PREVIOUS,
                tooltip="Abschnitt zurück",
                icon_size=28,
                on_click=zurueck,
                visible=not ohne_abschnitte,
            ),
            haupt_knopf,
            ft.IconButton(
                ft.Icons.SKIP_NEXT,
                tooltip="Nächster Abschnitt",
                icon_size=28,
                on_click=weiter,
                visible=not ohne_abschnitte,
            ),
            fertig_knopf,
            takt_wahl,
        ],
    )
    if reiter == PROFILE:
        wahl: list[ft.Control] = [
            kartentitel(
                "Vorlage",
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED, tooltip="Vorlage bearbeiten", on_click=bearbeiten
                ),
                ft.IconButton(ft.Icons.ADD, tooltip="Neue Vorlage", on_click=neu),
            ),
            profil_chips,
            _takte_karte(page, state),
        ]
    else:
        wahl = [einmal_karte()]
    if profil.ist_stoppuhr:
        ablauf_karte = karte(
            kartentitel("So zählt sie"),
            hinweis(
                "Sie läuft, bis du „Fertig“ tippst; „Pause“ hält nur an. Für sich gestartet "
                "trägt sie nichts ins Tagebuch ein — in einer laufenden HRV-Messung setzt "
                "sie Marken, und eine laufende Einheit nimmt sie auf."
            ),
        )
    elif ohne_abschnitte:
        ablauf_karte = karte(
            kartentitel("So zählt er"),
            hinweis(
                "Er zählt die Dauer rückwärts und meldet sich am Ende. Für sich gestartet zählt "
                "er für keine Übung — in einer laufenden HRV-Messung setzt er Marken, eine "
                "laufende Einheit nimmt ihn auf. Ein Tipp auf die Zeit stellt sie neu."
            ),
        )
    else:
        ablauf_karte = karte(kartentitel("Abschnitte"), ablauf, abstand=6)
    inhalt = ft.Column(
        spacing=14,
        controls=[
            reiter_wahl,
            *wahl,
            karte(
                abschnitt_text,
                # Ein Tipp auf die Zeit stellt einen Timer ohne Ablauf (P79 D4)
                uhr.zeile(
                    on_zeit=None if laufend else zeit_stellen,
                    zeit_tooltip=None if laufend else "Zeit stellen",
                ),
                fortschritt,
                stand_text,
                tempo_regler.control,
                takt_text,
                ft.Container(height=4),
                steuerung,
                abstand=10,
            ),
            _bereitstellen_knopf(state, lauf, bereitstellen),
            _signale_vermerk(state, signale_oeffnen),
            ablauf_karte,
            hinweis(
                "Der Timer läuft weiter, wenn du die Ansicht verlässt — oben in der Leiste "
                "steht dann seine Zeit."
            ),
        ],
    )
    if (plan_karte := _plan_ablauf_karte(page, state, basis)) is not None:
        inhalt.controls.insert(0, plan_karte)
    anzeigen()
    state.timer_beobachter["ansicht"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Timer")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


def _in_lauf_uebernehmen(lauf: TimerLauf, neu: TimerProfil) -> None:
    """Name und Schalter in einen laufenden Lauf — die Dauer bleibt, wie sie begann; bei
    einem Abschnitt auch sein Name (er ist die Marke)."""
    p = lauf.profil
    p.name, p.name_in_marken = neu.name, neu.name_in_marken
    if p.einfach and neu.einfach:
        p.abschnitte[0].name = neu.abschnitte[0].name


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


def _plan_ablauf_karte(page: Any, state: AppState, basis: str) -> ft.Control | None:
    """Über einem Plan: den Plan als Workout — jede Übung mit ihrem Timer (Skizze 8; seit
    K1 heißt es überall Workout, `docs/plan_uhren.md` §3)."""
    teile = [t for t in basis.split("/") if t]
    if teile[:1] != ["plan"] or len(teile) != 2:
        return None
    plan = state.plaene.laden(teile[1])
    if plan is None or not plan.items:
        return None

    async def oeffnen() -> None:
        await page.push_route(f"/plan/{plan.id}/workout")

    mit_timer = sum(
        1
        for it in plan.items
        if (u := state.uebungen.laden(it.exercise_id)) and timer_fuer(u, plan, it)
    )
    return karte(
        kartentitel(f"Plan „{plan.name}“"),
        hinweis(
            f"{mit_timer} von {len(plan.items)} Übungen mit Timer. Als Workout läuft der Plan "
            "von vorn bis hinten — eingetragen wird je Übung, sobald sie endet. Die Uhren "
            "aller Übungen: Plan bearbeiten → Uhren."
        ),
        ft.FilledTonalButton("Als Workout starten", icon=ft.Icons.PLAYLIST_PLAY, on_click=oeffnen),
    )


def _takte_karte(page: Any, state: AppState) -> ft.Control:
    """Die Takt-Bibliothek (K5, `docs/plan_uhren.md` §4.8): die gesicherten Takte als Liste —
    Stift öffnet das Takt-Blatt mit der Geltung „Vorlage“, ✕ löscht."""
    takte = state.takt_bibliothek()

    def ersetzer(i: int) -> Callable[[Takt | None], None]:
        def handler(neu: Takt | None) -> None:
            liste = state.takt_bibliothek()
            if i >= len(liste):
                return
            if neu is None or neu.leer:
                del liste[i]
            else:
                liste[i] = neu
            state.takt_bibliothek_setzen(liste)
            state.neu_zeichnen()

        return handler

    def bearbeiter(i: int, t: Takt) -> Callable[[], None]:
        def handler() -> None:
            page.show_dialog(
                takt_blatt(page, state, takt=t, titel="Takt-Vorlage", in_die_bibliothek=ersetzer(i))
            )

        return handler

    def loescher(i: int) -> Callable[[], None]:
        return lambda: ersetzer(i)(None)

    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(TAKT_SYMBOL, size=18, opacity=0.8),
                ft.Text(f"{t.anzeigename} · {t.kurztext()}", size=13, expand=True),
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    icon_size=20,
                    tooltip="Takt-Vorlage bearbeiten",
                    on_click=bearbeiter(i, t),
                ),
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=20,
                    tooltip="Takt-Vorlage löschen",
                    on_click=loescher(i),
                ),
            ],
        )
        for i, t in enumerate(takte)
    ]
    if not zeilen:
        zeilen.append(
            hinweis("Noch keine Takt-Vorlage — im Takt-Blatt „Als Vorlage sichern“ legt eine an.")
        )
    return karte(kartentitel("Takte"), *zeilen, abstand=6)


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
                        hinweis("Gilt für alle Timer auf diesem Gerät."),
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
            "und fürs Ende stellst du in der Vorlage ein (Stift bei der Vorlage)."
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
                page.run_task(wach_setzen, state, aktuell.wach)

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


@dataclass
class Profilziel:
    """Wo das Profil liegt, das der Editor bearbeitet — und wohin er speichert.

    Vorgabe ist die Timer-Bibliothek (`bibliothek`). Der Timer einer Übung bearbeitet
    ihre Profile, im Plan eine eigene Kopie der Planübung (`views.uebung_timer`).
    """

    #: die Profile, unter denen das bearbeitete gesucht wird
    profile: Callable[[], list[TimerProfil]]
    #: speichert das (geprüfte) Profil — neu oder geändert
    speichern: Callable[[TimerProfil], None]
    #: löscht es — ``None``: hier nicht löschbar
    loeschen: Callable[[TimerProfil], None] | None
    #: wohin Zurück, Speichern und Löschen führen
    zurueck: str
    #: Route des Editors ohne Profil-ID (``…/bearbeiten``)
    route: str
    titel: str = "Vorlage"
    titel_neu: str = "Neue Vorlage"
    #: ohne Namensfeld — der Einmal-Timer heißt auf der Timer-Seite (Ben, 19.10.2026)
    ohne_name: bool = False
    #: „Als Profil speichern“: legt eine Kopie mit Namen in die Bibliothek — ``None``: nicht
    als_profil: Callable[[TimerProfil], None] | None = None
    #: Die Felder der (Plan-)Übung, deren Timer hier entsteht — je Abschnitt lässt sich ihre
    #: Ausführung festlegen (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §3); ``None``: Vorlage
    spec: ResultSpec | None = None
    #: Ohne Namensfeld steht oben dieser Satz (Einmal-Timer, für jetzt)
    hinweis: str = ""
    #: So heißt der Knopf, der mit Namen speichert (`als_profil`)
    als_profil_text: str = "Als Vorlage speichern …"


def bibliothek(state: AppState, basis: str) -> Profilziel:
    """Die Timer-Bibliothek (gerätelokal, `AppState.timer_profile`)."""
    zurueck = timer_route(basis)

    def speichern(neu: TimerProfil) -> None:
        profile = state.timer_profile()
        if any(p.id == neu.id for p in profile):
            liste = [neu if p.id == neu.id else p for p in profile]
        else:
            liste = [*profile, neu]
        state.timer_profile_setzen(liste)
        state.timer_profil_waehlen(neu.id)

    def loeschen(alt: TimerProfil) -> None:
        state.timer_profile_setzen([p for p in state.timer_profile() if p.id != alt.id])
        if state.timer is not None and state.timer.profil.id == alt.id:
            state.timer = None

    return Profilziel(state.timer_profile, speichern, loeschen, zurueck, f"{zurueck}/bearbeiten")


def einmaluhr(state: AppState, basis: str) -> Profilziel:
    """Der Einmal-Timer im Editor (Ben, 19.10.2026): Abschnitte und Runden ohne Namen und
    ohne Profil — gemerkt als Einmaluhr; „Als Profil speichern“ legt ihn in die Bibliothek."""
    zurueck = timer_route(basis)

    def speichern(neu: TimerProfil) -> None:
        state.timer_einmal_setzen(neu)
        state.timer_profil_waehlen(EINMAL)

    return Profilziel(
        lambda: [state.timer_einmal(EINMAL)],
        speichern,
        None,
        zurueck,
        f"{zurueck}/bearbeiten",
        titel="Zeit: Abschnitte und Runden",
        ohne_name=True,
        als_profil=bibliothek(state, basis).speichern,
        hinweis="Gilt für die gestellte Zeit — ohne Namen",
    )


@dataclass
class _Zeile:
    """Ein Abschnitt im Editor — Werte, keine Controls: jeder Aufbau legt die Felder neu an
    (ein umgehängtes Textfeld nähme sonst keine Eingaben mehr, Flet 1.0)."""

    name: str
    #: die Dauer in Sekunden — gestellt über das Zeit-Blatt (Ben, 8.11.2026: kein Eingabefeld)
    dauer_s: int
    #: Klang zu Beginn — leer: der Standardklang der Signale
    klang: str = ""
    zaehlt: bool = True
    #: Der Takt dieses Abschnitts (`docs/plan_taktgeber.md`) — ``None``: wie die Übung
    takt: Takt | None = None
    #: Die Ausführung dieser Runde (Feld → Wert) — leer: wie im Block gewählt
    ausfuehrung: dict[str, Any] = field(default_factory=dict)

    def kopie(self) -> _Zeile:
        return replace(self, ausfuehrung=dict(self.ausfuehrung))


@dataclass
class _TeilFelder:
    """Ein Teil im Editor — sein Name, seine Abschnitte und Runden."""

    name: str
    zeilen: list[_Zeile] = field(default_factory=list)
    runden: int = 1

    def kopie(self) -> _TeilFelder:
        return _TeilFelder(self.name, [z.kopie() for z in self.zeilen], self.runden)

    def runde_s(self) -> int:
        return sum(z.dauer_s for z in self.zeilen)


#: Die Höhen der Zeilen — gleich in beiden Reitern, damit ein Abschnitt nach dem Wischen auf
#: derselben Höhe steht (Ben, 9.11.2026, `docs/plan_timer_editor.md` §2)
KOPF_H = 40
ZEILE_H = 48
ZUSATZ_H = 40
FUSS_H = 48
#: Die rechte Spalte jeder Zeile, die beim Wischen gleitet
RECHTS_B = 236
WISCH_MS = 220
#: Ab dieser Geschwindigkeit (px/s) zählt eine waagerechte Bewegung als Wischen
WISCH_V = 250
REITER_ZEITEN, REITER_KLAENGE = "zeiten", "klaenge"


def _klang_feld(
    page: Any, state: AppState, wert: str, vorgabe: str, setzen: Callable[[str], None]
) -> ft.Dropdown:
    """Der Klang eines Abschnitts, der Runde oder des Endes — Auswählen spielt ihn vor und
    merkt ihn (leer = ``vorgabe``)."""

    def gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        klang = e.control.value or _VORGABE
        setzen("" if klang == _VORGABE or klang not in KLAENGE else klang)
        if klang != _VORGABE:
            _vorspielen(page, state, klang)

    return ft.Dropdown(
        value=wert if wert in KLAENGE else _VORGABE,
        options=[
            ft.DropdownOption(key=_VORGABE, text=vorgabe),
            *(ft.DropdownOption(key=k, text=t) for k, t in KLAENGE.items()),
        ],
        leading_icon=ft.Icons.MUSIC_NOTE_OUTLINED,
        dense=True,
        width=RECHTS_B - 52,
        on_select=gewaehlt,
    )


def timer_bearbeiten_view(
    page: Any,
    state: AppState,
    profil_id: str | None,
    basis: str,
    ziel: Profilziel | None = None,
) -> ft.View:
    """Name, Teile mit Abschnitten und Runden, die Klänge — anlegen oder ändern.

    Ben, 9.11.2026 (`docs/plan_timer_editor.md`, Skizzen G3–G5): **fest oben** Name und die
    Gesamtzeit des ganzen Timers, die Reiter **Zeiten · Klänge** und das „i“. Unter „Zeiten“
    je Abschnitt **eine Zeile** — Name · Takt · Zeit · zählt · entfernen —, ein Takt und die
    Ausführung in einer zweiten Zeile, „Abschnitt hinzufügen“ darunter, je Teil die Gesamtzeit
    mit „Runden − n +“; Teile kopiert ⧉, Abschnitte kopiert langes Drücken (P151). Unter
    „Klänge“ dieselben Zeilen auf derselben Höhe, die Namen nur zum Lesen (P152), rechts der
    Klang. **Wischen** wechselt: eine Scrollfläche, nur die rechte Spalte gleitet.

    Eine **Folge** reiht Teile: Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 ×
    (Ben, 17.10.2026); ein Profil mit einem Teil ist ein gewöhnlicher Timer.

    Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen" verwirft.
    """
    if ziel is None:
        ziel = einmaluhr(state, basis) if profil_id == EINMAL else bibliothek(state, basis)
    vorhanden = next((p for p in ziel.profile() if p.id == profil_id), None)
    profil = vorhanden or TimerProfil(
        name="", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=1
    )
    route = ziel.route + (f"/{vorhanden.id}" if vorhanden else "")

    name = ft.TextField(
        label="Name",
        value=profil.name,
        hint_text="z. B. Intervall, Planke",
        dense=True,
        expand=True,
        visible=not ziel.ohne_name,
    )
    teile_ed: list[_TeilFelder] = []
    teile_spalte = ft.Column(spacing=12)
    klang_ganz = {"runde": profil.runden_klang, "ende": profil.ende_klang}
    gesamt_text = ft.Text(
        size=22, weight=ft.FontWeight.W_700, color=ft.Colors.PRIMARY, data="gesamt"
    )
    reiter = {"modus": REITER_ZEITEN}
    #: je Zeile: die rechte Spalte gleiten lassen und Texte tauschen (Wischen, §2)
    umschalter: list[Callable[[bool], None]] = []
    #: Was eine Runde festlegen kann — nur am Timer einer Übung (§3)
    felder_aus = ausfuehrungsfelder(ziel.spec) if ziel.spec is not None else []
    vorschau = ft.Text(size=13, visible=False)

    def klaenge() -> bool:
        return reiter["modus"] == REITER_KLAENGE

    def gesamt() -> None:
        summe = sum(t.runde_s() * t.runden for t in teile_ed)
        gesamt_text.value = dauer_text(summe)
        # Je Ausführung ein Eintrag — was der Timer einträgt (`ausfuehrungs_vorschau`)
        teile = [
            Teil(
                [
                    Abschnitt("", z.dauer_s, zaehlt=z.zaehlt, ausfuehrung=dict(z.ausfuehrung))
                    for z in t.zeilen
                    if z.dauer_s
                ],
                t.runden,
            )
            for t in teile_ed
        ]
        je = (
            ausfuehrungs_vorschau(
                TimerProfil(abschnitte=teile[0].abschnitte, runden=teile[0].runden, teile=teile[1:])
            )
            if teile and teile[0].abschnitte
            else []
        )
        vorschau.visible = bool(je)
        vorschau.value = "Eingetragen wird je Ausführung ein Eintrag: " + " · ".join(
            f"{ausfuehrung_text(a, felder_aus) or 'wie gewählt'} {dauer_text(sek)}" for a, sek in je
        )

    def zeile(a: Abschnitt) -> _Zeile:
        return _Zeile(
            a.name,
            max(1, int(a.dauer_s)),
            a.klang,
            a.zaehlt,
            a.takt,
            {k: v for k, v in a.ausfuehrung.items() if any(f.key == k for f in felder_aus)},
        )

    def teil_felder(teil: Teil) -> _TeilFelder:
        return _TeilFelder(teil.name, [zeile(a) for a in teil.abschnitte], max(teil.runden, 1))

    def neu_zeichnen() -> None:
        zeichnen()
        page.update()

    def entferner(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            if len(teile_ed[k].zeilen) > 1:
                del teile_ed[k].zeilen[i]
                neu_zeichnen()

        return handler

    def zaehlt_umschalter(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            z = teile_ed[k].zeilen[i]
            z.zaehlt = not z.zaehlt
            neu_zeichnen()

        return handler

    def dauer_knopf(k: int, i: int) -> ft.Control:
        """Die Dauer als antippbares Etikett — ein Tipp öffnet das Zeit-Blatt (§4.6a)."""
        z = teile_ed[k].zeilen[i]

        def gestellt(sekunden: int) -> None:
            teile_ed[k].zeilen[i].dauer_s = sekunden
            neu_zeichnen()

        def stellen() -> None:
            page.show_dialog(
                zeit_blatt(
                    z.dauer_s,
                    starten=gestellt,
                    untertitel=z.name.strip() or f"Abschnitt {i + 1}",
                    start_text="Übernehmen",
                    schnell=state.schnellzeiten(),
                )
            )

        return ft.OutlinedButton(
            dauer_text(z.dauer_s),
            icon=ft.Icons.SCHEDULE,
            tooltip="Zeit stellen",
            on_click=stellen,
            style=ft.ButtonStyle(padding=ft.Padding.only(left=8, right=10)),
            data=("dauer", k, i),
        )

    def takt_setzer(k: int, i: int) -> Callable[[Takt | None], None]:
        def handler(takt: Takt | None) -> None:
            teile_ed[k].zeilen[i].takt = takt if takt is not None and not takt.leer else None
            neu_zeichnen()

        return handler

    def takt_entferner(k: int, i: int) -> Callable[[], None]:
        return lambda: takt_setzer(k, i)(None)

    def takt_bearbeiter(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            z = teile_ed[k].zeilen[i]
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=z.takt,
                    titel=f"Takt: {z.name.strip() or 'Abschnitt'}",
                    in_den_abschnitt=takt_setzer(k, i),
                )
            )

        return handler

    def hinzufuegen(k: int) -> Callable[[], None]:
        def handler() -> None:
            teile_ed[k].zeilen.append(zeile(Abschnitt("", 60)))
            neu_zeichnen()

        return handler

    def abschnitt_menue(k: int, i: int) -> Callable[..., None]:
        """Langes Drücken auf eine Zeile (P151, Ben 9.11.2026: „alles so wie vorgeschlagen“):
        den Abschnitt kopieren (dahinter) oder entfernen."""

        def handler(_e: Any = None) -> None:
            z = teile_ed[k].zeilen[i]
            nachher = Nachher()
            dialog: ft.AlertDialog

            def kopieren(_e: Any = None) -> None:
                teile_ed[k].zeilen.insert(i + 1, z.kopie())
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            def entfernen(_e: Any = None) -> None:
                if len(teile_ed[k].zeilen) > 1:
                    del teile_ed[k].zeilen[i]
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            dialog = ft.AlertDialog(
                title=ft.Text(z.name.strip() or f"Abschnitt {i + 1}"),
                content=ft.Column(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.CONTENT_COPY),
                            title=ft.Text("Kopieren"),
                            subtitle=ft.Text("dahinter einfügen", size=12),
                            on_click=kopieren,
                        ),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.REMOVE_CIRCLE_OUTLINE),
                            title=ft.Text("Entfernen"),
                            disabled=len(teile_ed[k].zeilen) <= 1,
                            on_click=entfernen,
                        ),
                    ],
                ),
                actions=[ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog))],
                on_dismiss=nachher.bei_schliessen,
            )
            page.show_dialog(dialog)

        return handler

    def ausfuehrung_setzen(k: int, i: int, key: str, wert: Any) -> None:
        """Ein Wert der Ausführung — derselbe noch einmal oder ``None`` nimmt ihn heraus. Der
        Name folgt („Links“), solange er leer ist oder dem alten Vorschlag entspricht."""
        z = teile_ed[k].zeilen[i]
        alt = dict(z.ausfuehrung)
        if wert is None or alt.get(key) == wert:
            z.ausfuehrung.pop(key, None)
        else:
            z.ausfuehrung[key] = wert
        jetzt = z.name.strip()
        if not jetzt or jetzt == ausfuehrung_text(alt, felder_aus):
            z.name = ausfuehrung_text(z.ausfuehrung, felder_aus).capitalize()
        neu_zeichnen()

    def ausfuehrung_waehler(k: int, i: int, key: str, wert: Any) -> Callable[[], None]:
        return lambda: ausfuehrung_setzen(k, i, key, wert)

    def ausfuehrung_zahl(k: int, i: int, key: str) -> Callable[[Any], None]:
        """Gewicht oder Winkel getippt — leer heißt „wie gewählt“."""

        def handler(e: Any) -> None:
            text = str(getattr(e.control, "value", "") or "").strip().replace(",", ".")
            try:
                zahl = float(text) if text else None
            except ValueError:
                zahl = None
            z = teile_ed[k].zeilen[i]
            if zahl is None and key not in z.ausfuehrung:
                return
            wert = None if zahl is None else (int(zahl) if zahl.is_integer() else zahl)
            if z.ausfuehrung.get(key) != wert:
                z.ausfuehrung.pop(key, None)
                ausfuehrung_setzen(k, i, key, wert)

        return handler

    def ausfuehrung_zeile(k: int, i: int) -> ft.Control:
        """„Ausführung“ je Runde: die Chips der Variante bzw. Seite, Felder für Gewicht und
        Winkel — nichts gewählt heißt „wie gewählt“ (der Block)."""
        z = teile_ed[k].zeilen[i]
        teile: list[ft.Control] = [ft.Text("Ausführung", size=12, opacity=0.7)]
        for f in felder_aus:
            if f.type == FieldType.CHOICE:
                teile.extend(
                    ft.Chip(
                        label=ft.Text(str(o), size=12),
                        selected=z.ausfuehrung.get(f.key) == o,
                        show_checkmark=False,
                        tooltip=f"{f.label}: {o} — noch einmal tippen: wie gewählt",
                        on_select=ausfuehrung_waehler(k, i, f.key, o),
                    )
                    for o in f.quick
                )
            else:
                wert = z.ausfuehrung.get(f.key)
                teile.append(
                    ft.TextField(
                        label=f.label,
                        value="" if wert is None else str(wert).replace(".", ","),
                        hint_text="wie gewählt",
                        suffix=f.unit or None,
                        dense=True,
                        width=120,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        on_blur=ausfuehrung_zahl(k, i, f.key),
                        on_submit=ausfuehrung_zahl(k, i, f.key),
                    )
                )
        if not z.ausfuehrung:
            teile.append(ft.Text("wie gewählt", size=12, italic=True, opacity=0.6))
        return ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=teile,
        )

    def runden_aendern(k: int, delta: int) -> Callable[[], None]:
        def handler() -> None:
            t = teile_ed[k]
            t.runden = min(max(t.runden + delta, 1), MAX_RUNDEN)
            neu_zeichnen()

        return handler

    def teil_hinzufuegen() -> None:
        teile_ed.append(_TeilFelder("Cooldown", [_Zeile("Cooldown", 60, zaehlt=False)], 1))
        neu_zeichnen()

    def teil_kopierer(k: int) -> Callable[[], None]:
        """⧉ neben dem Papierkorb (Ben, 9.11.2026): der Teil noch einmal, gleich dahinter."""

        def handler() -> None:
            teile_ed.insert(k + 1, teile_ed[k].kopie())
            neu_zeichnen()

        return handler

    def teil_entferner(k: int) -> Callable[[], None]:
        def handler() -> None:
            if len(teile_ed) > 1:
                del teile_ed[k]
                neu_zeichnen()

        return handler

    # -- Bausteine einer Karte ---------------------------------------------------------------

    def gleitend(zeiten: ft.Control, klaenge_teil: ft.Control, hoehe: int) -> ft.Control:
        """Die rechte Spalte: beide Teile übereinander, sichtbar nur einer — Wischen schiebt
        sie (`offset`, `animate_offset`; `AnimatedSwitcher` kann in Flet 1.0.3 nicht schieben).
        Was hinausgeschoben ist, fängt keine Tipps: der Stapel schneidet ab."""
        kl = klaenge()
        bewegung = ft.Animation(WISCH_MS, ft.AnimationCurve.EASE_OUT)
        a = ft.Container(
            left=0,
            top=0,
            width=RECHTS_B,
            height=hoehe,
            alignment=ft.Alignment.CENTER_RIGHT,
            offset=ft.Offset(-1 if kl else 0, 0),
            animate_offset=bewegung,
            content=zeiten,
        )
        b = ft.Container(
            left=0,
            top=0,
            width=RECHTS_B,
            height=hoehe,
            alignment=ft.Alignment.CENTER_RIGHT,
            offset=ft.Offset(0 if kl else 1, 0),
            animate_offset=bewegung,
            content=klaenge_teil,
        )

        def umschalten(nach_klaengen: bool) -> None:
            a.offset = ft.Offset(-1 if nach_klaengen else 0, 0)
            b.offset = ft.Offset(0 if nach_klaengen else 1, 0)

        umschalter.append(umschalten)
        return ft.Stack(
            controls=[a, b],
            width=RECHTS_B,
            height=hoehe,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def name_links(
        wert: str,
        hinweis_text: str,
        setzen: Callable[[str], None],
        *,
        groesse: int = 15,
        fett: bool = False,
        farbe: str | None = None,
        data: Any = None,
    ) -> ft.Control:
        """Links: unter „Zeiten“ ein Feld, unter „Klänge“ derselbe Name zum Lesen (P152) — an
        derselben Stelle."""
        kl = klaenge()

        def geaendert(e: Any) -> None:
            setzen(str(e.control.value or ""))
            lesen.value = str(e.control.value or "").strip() or hinweis_text

        feld = ft.TextField(
            value=wert,
            hint_text=hinweis_text,
            dense=True,
            border=ft.UnderlineInputBorder(),
            content_padding=ft.Padding.only(left=2, right=2, top=6, bottom=6),
            expand=True,
            visible=not kl,
            on_change=geaendert,
            text_size=groesse,
            text_style=ft.TextStyle(weight=ft.FontWeight.W_700) if fett else None,
            color=farbe,
            data=data,
        )
        lesen = ft.Text(
            wert.strip() or hinweis_text,
            expand=True,
            visible=kl,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            size=groesse,
            weight=ft.FontWeight.W_700 if fett else None,
            color=farbe,
        )

        def umschalten(nach_klaengen: bool) -> None:
            feld.visible = not nach_klaengen
            lesen.visible = nach_klaengen

        umschalter.append(umschalten)
        return ft.Row(expand=True, spacing=0, controls=[feld, lesen])

    def zaehlt_chip(k: int, i: int, z: _Zeile) -> ft.Control:
        """„zählt“ als Chip (P154) — durchgestrichen: zählt nicht als Übungszeit."""
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=9, vertical=5),
            border_radius=15,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if z.zaehlt else None,
            border=None if z.zaehlt else ft.Border.all(1, ft.Colors.OUTLINE),
            tooltip="zählt als Übungszeit — tippen schaltet um"
            if z.zaehlt
            else "zählt nicht als Übungszeit — tippen schaltet um",
            on_click=lambda _e=None: zaehlt_umschalter(k, i)(),
            data=("zaehlt", k, i),
            content=ft.Text(
                "zählt",
                size=12,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_PRIMARY_CONTAINER if z.zaehlt else None,
                opacity=1.0 if z.zaehlt else 0.7,
                style=None if z.zaehlt else ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH),
            ),
        )

    def abschnitt(k: int, i: int, z: _Zeile, t: _TeilFelder) -> list[ft.Control]:
        """Eine Zeile je Abschnitt — Name · Takt · Zeit · zählt · ⊖ (Skizze G3); darunter,
        wenn es sie gibt, der Takt und die Ausführung."""

        def name_setzen(wert: str, z: _Zeile = z) -> None:
            z.name = wert

        zeiten_teil = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    ft.Icons.GRAPHIC_EQ,
                    icon_size=20,
                    tooltip=takt_zeile_text(z.takt),
                    style=ft.ButtonStyle(bgcolor=ft.Colors.SECONDARY_CONTAINER)
                    if z.takt is not None
                    else None,
                    icon_color=ft.Colors.ON_SECONDARY_CONTAINER if z.takt is not None else None,
                    on_click=takt_bearbeiter(k, i),
                    data=("takt", k, i),
                ),
                dauer_knopf(k, i),
                zaehlt_chip(k, i, z),
                ft.IconButton(
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    icon_size=20,
                    tooltip="Abschnitt entfernen — lange drücken: kopieren",
                    on_click=entferner(k, i),
                    disabled=len(t.zeilen) <= 1,
                ),
            ],
        )

        def klang_setzen(wert: str, z: _Zeile = z) -> None:
            z.klang = wert

        klaenge_teil = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _klang_feld(page, state, z.klang, "Standardklang", klang_setzen),
                ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    icon_size=22,
                    tooltip="Vorspielen",
                    on_click=lambda _e=None, z=z: _vorspielen(
                        page, state, z.klang or state.timer_signale().klang
                    ),
                ),
            ],
        )
        out: list[ft.Control] = [
            ft.Container(
                height=ZEILE_H,
                padding=ft.Padding.only(left=12, right=4),
                border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                on_long_press=abschnitt_menue(k, i),
                data=("abschnitt", k, i),
                content=ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        name_links(z.name, f"Abschnitt {i + 1}", name_setzen, data=("name", k, i)),
                        gleitend(zeiten_teil, klaenge_teil, ZEILE_H),
                    ],
                ),
            )
        ]
        if z.takt is not None:
            hinweis_zeit = "nur in diesem Abschnitt"
            hinweis_klang = "Klang je Phase — ✎"
            zusatz = ft.Text(
                hinweis_klang if klaenge() else hinweis_zeit,
                size=12,
                opacity=0.7,
                expand=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )

            def zusatz_tauschen(nach_klaengen: bool, zusatz: ft.Text = zusatz) -> None:
                zusatz.value = hinweis_klang if nach_klaengen else hinweis_zeit

            umschalter.append(zusatz_tauschen)
            out.append(
                ft.Container(
                    padding=ft.Padding.only(left=16, right=4),
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.GRAPHIC_EQ, size=14, color=ft.Colors.PRIMARY),
                            ft.Text(
                                takt_zeile_text(z.takt).removeprefix("Takt: "),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY,
                            ),
                            zusatz,
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                icon_size=16,
                                tooltip="Takt einstellen: Phasen, Tempo, Klang",
                                on_click=takt_bearbeiter(k, i),
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=16,
                                tooltip="Takt entfernen",
                                on_click=takt_entferner(k, i),
                            ),
                        ],
                    ),
                )
            )
        if felder_aus:
            out.append(
                ft.Container(
                    padding=ft.Padding.only(left=16, right=8, bottom=6),
                    content=ausfuehrung_zeile(k, i),
                )
            )
        return out

    def teil_karte(k: int, t: _TeilFelder) -> ft.Control:
        kl = klaenge()

        def name_setzen(wert: str, t: _TeilFelder = t) -> None:
            t.name = wert

        knoepfe = ft.Row(
            spacing=0,
            visible=not kl,
            controls=[
                ft.IconButton(
                    ft.Icons.CONTENT_COPY,
                    icon_size=18,
                    tooltip="Teil kopieren — dahinter",
                    on_click=teil_kopierer(k),
                    data=("teil_kopieren", k),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=18,
                    tooltip="Teil entfernen",
                    on_click=teil_entferner(k),
                    disabled=len(teile_ed) <= 1,
                ),
            ],
        )
        hinzu = ft.TextButton(
            "Abschnitt hinzufügen", icon=ft.Icons.ADD, on_click=hinzufuegen(k), visible=not kl
        )
        runden = ft.Row(
            spacing=0,
            visible=not kl,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Runden", size=13, opacity=0.75),
                ft.IconButton(ft.Icons.REMOVE, on_click=runden_aendern(k, -1)),
                ft.Text(
                    str(t.runden),
                    size=16,
                    weight=ft.FontWeight.W_700,
                    width=28,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(ft.Icons.ADD, on_click=runden_aendern(k, 1)),
            ],
        )
        runden_lesen = ft.Text(
            "1 Runde" if t.runden == 1 else f"{t.runden} Runden",
            size=13,
            opacity=0.75,
            visible=kl,
        )

        def umschalten(nach_klaengen: bool) -> None:
            knoepfe.visible = hinzu.visible = runden.visible = not nach_klaengen
            runden_lesen.visible = nach_klaengen

        umschalter.append(umschalten)
        zeilen: list[ft.Control] = []
        for i, z in enumerate(t.zeilen):
            zeilen.extend(abschnitt(k, i, z, t))
        return ft.Container(
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            data=("teil", k),
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        height=KOPF_H,
                        padding=ft.Padding.only(left=12, right=4),
                        content=ft.Row(
                            spacing=2,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                name_links(
                                    t.name,
                                    "Abschnitte" if len(teile_ed) == 1 else f"Teil {k + 1}",
                                    name_setzen,
                                    groesse=13,
                                    fett=True,
                                    farbe=ft.Colors.PRIMARY,
                                    data=("teil_name", k),
                                ),
                                knoepfe,
                            ],
                        ),
                    ),
                    *zeilen,
                    ft.Container(
                        height=ZUSATZ_H,
                        padding=ft.Padding.only(left=4),
                        alignment=ft.Alignment.CENTER_LEFT,
                        content=hinzu,
                    ),
                    ft.Container(
                        height=FUSS_H,
                        padding=ft.Padding.only(left=14, right=6),
                        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                        content=ft.Row(
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    dauer_text(t.runde_s() * t.runden),
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    data=("teil_gesamt", k),
                                ),
                                ft.Text(
                                    f"{t.runden} × {dauer_text(t.runde_s())}",
                                    size=12,
                                    opacity=0.7,
                                    expand=True,
                                ),
                                runden,
                                runden_lesen,
                            ],
                        ),
                    ),
                ],
            ),
        )

    def zeichnen() -> None:
        umschalter.clear()
        teile_spalte.controls = [teil_karte(k, t) for k, t in enumerate(teile_ed)]
        gesamt()

    # -- Reiter und Wischen ----------------------------------------------------------------

    def modus_setzen(modus: str) -> None:
        if modus == reiter["modus"]:
            return
        reiter["modus"] = modus
        kl = modus == REITER_KLAENGE
        wahl.selected = [modus]
        for umschalten in umschalter:
            umschalten(kl)
        zeiten_unten.visible = not kl
        klaenge_unten.visible = kl
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            page.update()

    def reiter_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            modus_setzen(str(e.control.selected[0]))

    def gewischt(e: Any) -> None:
        """Nach links zu den Klängen, nach rechts zurück zu den Zeiten (Ben, 9.11.2026)."""
        v = getattr(e, "primary_velocity", None) or 0
        if v < -WISCH_V:
            modus_setzen(REITER_KLAENGE)
        elif v > WISCH_V:
            modus_setzen(REITER_ZEITEN)

    wahl = ft.SegmentedButton(
        selected=[REITER_ZEITEN],
        show_selected_icon=False,
        segments=[
            ft.Segment(
                value=REITER_ZEITEN, label=ft.Text("Zeiten"), icon=ft.Icon(ft.Icons.SCHEDULE)
            ),
            ft.Segment(
                value=REITER_KLAENGE,
                label=ft.Text("Klänge"),
                icon=ft.Icon(ft.Icons.MUSIC_NOTE_OUTLINED),
            ),
        ],
        on_change=reiter_gewaehlt,
        expand=True,
        data="reiter",
    )

    def stand() -> tuple[Any, ...]:
        """Alles, was man hier ändern kann — für „Zurück speichert“ (Ben, 16.10.2026)."""
        return (
            name.value or "",
            [
                (
                    t.name,
                    [
                        (
                            z.name,
                            z.dauer_s,
                            z.klang,
                            z.zaehlt,
                            z.takt.als_dict() if z.takt is not None else None,
                            sorted(z.ausfuehrung.items()),
                        )
                        for z in t.zeilen
                    ],
                    t.runden,
                )
                for t in teile_ed
            ],
            klang_ganz["runde"],
            klang_ganz["ende"],
        )

    def bauen(profil_id: str, profil_name: str) -> TimerProfil | str:
        """Das Profil aus den Feldern — oder der Grund, warum nicht."""
        teile_neu: list[Teil] = []
        for t in teile_ed:
            abschnitte = [
                Abschnitt(
                    z.name.strip(),
                    z.dauer_s,
                    z.klang,
                    z.zaehlt,
                    takt=z.takt,
                    ausfuehrung=dict(z.ausfuehrung),
                )
                for z in t.zeilen
                if z.dauer_s
            ]
            teile_neu.append(Teil(abschnitte, t.runden, t.name.strip()))
        if not all(t.abschnitte for t in teile_neu):
            return "Eine Dauer fehlt — tippe auf die Zeit eines Abschnitts."
        erster, *weitere = teile_neu
        return TimerProfil(
            id=profil_id,
            name=profil_name,
            abschnitte=erster.abschnitte,
            runden=erster.runden,
            runden_klang=klang_ganz["runde"],
            ende_klang=klang_ganz["ende"],
            teil_name=erster.name if weitere else "",
            teile=weitere,
            name_in_marken=profil.name_in_marken if ziel.ohne_name else True,
        )

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        profil_name = profil.name if ziel.ohne_name else (name.value or "").strip() or "Timer"
        neu = bauen(profil.id, profil_name)
        if isinstance(neu, str):
            return neu
        ziel.speichern(neu)
        gespeichert["name"] = neu.anzeigename
        return None

    def als_profil_fragen(_e: Any = None) -> None:
        """„Als Vorlage speichern“ bzw. „Als Timer der Übung speichern“ (für jetzt, G2): erst
        hier braucht es einen Namen — nur dieser Knopf speichert."""
        feld = ft.TextField(label="Name", hint_text="z. B. Intervall, Planke", autofocus=True)
        nachher_profil = Nachher()

        def anlegen() -> None:
            profil_name = (feld.value or "").strip()
            if not profil_name:
                feld.error = "Ein Name, bitte."
                page.update()
                return
            neu = bauen(new_id(), profil_name)
            if isinstance(neu, str):
                feld.error = neu
                page.update()
                return
            assert ziel.als_profil is not None
            ziel.als_profil(neu)
            nachher_profil.danach(
                lambda: page.show_dialog(ft.SnackBar(ft.Text(f"„{profil_name}“ gespeichert")))
            )
            nachher_profil.danach(lambda: page.push_route(ziel.zurueck))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(ziel.als_profil_text.removesuffix(" …")),
            content=feld,
            on_dismiss=nachher_profil.bei_schliessen,
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=anlegen),
            ],
        )
        feld.on_submit = lambda _: anlegen()
        page.show_dialog(dialog)

    #: Name des zuletzt gespeicherten Profils — für die Meldung
    gespeichert: dict[str, str] = {}

    async def speichern() -> None:
        if (grund := sichern()) is not None:
            page.show_dialog(ft.SnackBar(ft.Text(grund)))
            return
        meldung = "Übernommen" if ziel.ohne_name else f"„{gespeichert['name']}“ gespeichert"
        page.show_dialog(ft.SnackBar(ft.Text(meldung)))
        await page.push_route(ziel.zurueck)

    nachher = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def loeschen() -> None:
        if ziel.loeschen is not None:
            ziel.loeschen(profil)
        nachher.danach(lambda: page.push_route(ziel.zurueck))
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{profil.name}“ gelöscht")))

    def loeschen_fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Löschen?"),
                content=ft.Text(
                    "Gibt es danach keine eigene Vorlage mehr, kommen die zwei Beispiele zurück."
                    if ziel.titel == "Vorlage"
                    else "Der Timer verschwindet aus dieser Übung."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Löschen", on_click=loeschen),
                ],
            )
        )

    async def abbrechen() -> None:
        await page.push_route(ziel.zurueck)

    def signale_zeigen(_e: Any = None) -> None:
        """„Signale ›“: Countdown, Vibration, Lautstärke für alle Timer — als Blatt über dem
        Editor, damit nichts Ungespeichertes verloren geht."""
        page.show_dialog(
            ft.BottomSheet(
                scrollable=True,
                content=blatt_spalte(
                    [
                        ft.Text("Signale für alle Timer", size=17, weight=ft.FontWeight.W_600),
                        _klang_karte(page, state),
                        _lautstaerke_karte(page, state),
                        _signale_karte(page, state),
                    ]
                ),
            )
        )

    def ganz_klang(schluessel: str) -> Callable[[str], None]:
        return lambda wert: klang_ganz.__setitem__(schluessel, wert)

    def ganz_vorspielen(schluessel: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            klang = klang_ganz[schluessel]
            if not klang:
                erster = teile_ed[0].zeilen[0].klang if teile_ed and teile_ed[0].zeilen else ""
                vorgabe = state.timer_signale().klang
                klang = (erster or vorgabe) if schluessel == "runde" else "ende"
            _vorspielen(page, state, klang)

        return handler

    def ganz_zeile(text: str, schluessel: str, vorgabe: str) -> ft.Control:
        return ft.Container(
            height=ZEILE_H,
            padding=ft.Padding.only(left=14, right=4),
            border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            content=ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(text, size=14, expand=True),
                    _klang_feld(
                        page, state, klang_ganz[schluessel], vorgabe, ganz_klang(schluessel)
                    ),
                    ft.IconButton(
                        ft.Icons.PLAY_ARROW,
                        icon_size=22,
                        tooltip="Vorspielen",
                        on_click=ganz_vorspielen(schluessel),
                    ),
                ],
            ),
        )

    teile_ed.extend(teil_felder(t) for t in profil.alle_teile())
    zeichnen()
    anfang = stand()

    zeiten_unten = ft.Column(
        spacing=10,
        controls=[
            ft.OutlinedButton(
                "Teil anhängen",
                icon=ft.Icons.ADD,
                tooltip="Eine Folge: Vorbereitung, Training, Cooldown …",
                on_click=teil_hinzufuegen,
            ),
            vorschau,
            *(
                [
                    ft.FilledTonalButton(
                        ziel.als_profil_text,
                        icon=ft.Icons.BOOKMARK_ADD_OUTLINED,
                        on_click=als_profil_fragen,
                        data="als_profil",
                    )
                ]
                if ziel.als_profil is not None and ziel.ohne_name
                else []
            ),
        ],
    )
    klaenge_unten = ft.Container(
        visible=False,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        data="klaenge_ganz",
        content=ft.Column(
            spacing=0,
            controls=[
                ft.Container(
                    height=36,
                    padding=ft.Padding.only(left=14, right=4),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                "FÜR DEN GANZEN TIMER",
                                size=11,
                                weight=ft.FontWeight.W_700,
                                opacity=0.7,
                                expand=True,
                            ),
                            ft.TextButton("Signale ›", on_click=signale_zeigen),
                        ],
                    ),
                ),
                ganz_zeile("Neue Runde", "runde", "wie Abschnitt 1"),
                ganz_zeile("Am Ende", "ende", "Fanfare"),
            ],
        ),
    )
    kopf = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=6, bottom=10),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        name,
                        ft.Container(
                            visible=ziel.ohne_name,
                            expand=True,
                            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                            border_radius=12,
                            bgcolor=ft.Colors.SECONDARY_CONTAINER,
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(ft.Icons.SCHEDULE, size=18),
                                    ft.Text(ziel.hinweis, size=13, expand=True),
                                ],
                            ),
                        ),
                        ft.Column(
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[gesamt_text, ft.Text("gesamt", size=11, opacity=0.7)],
                        ),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[wahl, info_knopf(page, "Timer bearbeiten", TIMER_EDITOR_MD)],
                ),
            ],
        ),
    )

    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            ziel.titel if vorhanden else ziel.titel_neu,
            abbrechen=abbrechen,
            speichern=speichern,
            text="Übernehmen" if ziel.ohne_name else "Speichern",
            vorher=[
                *(
                    [
                        ft.IconButton(
                            ft.Icons.BOOKMARK_ADD_OUTLINED,
                            tooltip=ziel.als_profil_text,
                            on_click=als_profil_fragen,
                        )
                    ]
                    if ziel.als_profil is not None
                    else []
                ),
                *(
                    [
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Profil löschen",
                            on_click=loeschen_fragen,
                        )
                    ]
                    if vorhanden and ziel.loeschen is not None
                    else []
                ),
            ],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        kopf,
                        # Wischen über der Liste wechselt den Reiter — eine Scrollfläche, die
                        # Namen bleiben stehen (Ben, 9.11.2026)
                        ft.GestureDetector(
                            expand=True,
                            on_horizontal_drag_end=gewischt,
                            content=ft.Column(
                                expand=True,
                                scroll=ft.ScrollMode.AUTO,
                                controls=[
                                    ft.Container(
                                        padding=ft.Padding.only(
                                            left=12, right=12, top=12, bottom=16
                                        ),
                                        content=ft.Column(
                                            spacing=12,
                                            controls=[teile_spalte, zeiten_unten, klaenge_unten],
                                        ),
                                    )
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: stand() != anfang,
        speichern=sichern,
        meldung="Übernommen" if ziel.ohne_name else "Vorlage gespeichert",
    )


__all__ = [
    "PROFILE",
    "Profilziel",
    "bibliothek",
    "einmaluhr",
    "lauf_fuer",
    "ticker_starten",
    "timer_bearbeiten_view",
    "timer_knopf",
    "timer_route",
    "timer_signale_view",
    "timer_view",
    "toene_laden",
    "ton_spielen",
]
