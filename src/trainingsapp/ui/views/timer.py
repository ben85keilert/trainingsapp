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
from trainingsapp.core.timer import (
    EINMAL,
    EINMAL_DAUERN_S,
    MAX_RUNDEN,
    QUELLEN,
    STOPPUHR,
    Abschnitt,
    Teil,
    TimerLauf,
    TimerProfil,
    TimerStand,
    dauer_lesen,
    dauer_text,
    einmal_timer,
    signale_kurz,
    stoppuhr,
)
from trainingsapp.devices.einheit import TimerBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zeit_stellen import zeit_blatt
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import ticker_starten, toene_laden, ton_spielen, wach_setzen

#: Der dritte Reiter neben Stoppuhr und Timer — die Bibliothek der Profile
PROFILE = "profile"


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
    zeit_text = ft.Text(size=84, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    fortschritt = ft.ProgressBar(value=0, bar_height=8, border_radius=4)
    stand_text = ft.Text(size=13, opacity=0.75, text_align=ft.TextAlign.CENTER)
    haupt_knopf = ft.FilledButton(
        height=56, style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=28))
    )
    ablauf = ft.Column(spacing=2)

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
            zeit_text.value = lauf.anzeige()
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
            zeit_text.value = "0:00"
            fortschritt.value = 1.0
            stand_text.value = f"{profil.anzeigename} · {dauer_text(profil.gesamt_s())}"
        else:
            abschnitt_text.value = stand.name or f"Abschnitt {stand.index + 1}"
            # Vor dem Start die volle Dauer, danach aufgerundet (0:01 bis zuletzt)
            zeit_text.value = dauer_text(-(-stand.rest_s // 1))
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
            text = "Nochmal" if stand.fertig else ("Weiter" if lauf.begonnen else "Start")
            haupt_knopf.content = _knopf_inhalt(ft.Icons.PLAY_ARROW, text)
            haupt_knopf.on_click = starten
        ablauf.controls = [] if lauf.vorwaerts else ablauf_zeilen(stand)

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
        page.show_dialog(zeit_blatt(vorher, starten=zeit_gestellt, untertitel="ohne Ablauf"))

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

    def dauer_gelesen(_e: object = None) -> None:
        sekunden = dauer_lesen(dauer_feld.value or "")
        if sekunden is None:
            dauer_feld.error = "z. B. 5:00"
            with contextlib.suppress(Exception):
                dauer_feld.update()
            return
        if sekunden != profil.gesamt_s():
            dauer_setzen(sekunden)

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
    dauer_feld = ft.TextField(
        label="Dauer",
        value=dauer_text(profil.gesamt_s()),
        width=110,
        dense=True,
        keyboard_type=ft.KeyboardType.DATETIME,
        text_align=ft.TextAlign.END,
        disabled=laufend,
        on_submit=dauer_gelesen,
        on_blur=dauer_gelesen,
    )

    def einmal_karte() -> ft.Control:
        """Name und Schalter — beim Timer davor die Dauer oder die Abschnitte."""
        zeilen: list[ft.Control] = []
        if profil.id == EINMAL and profil.einfach:
            zeilen += [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        dauer_feld,
                        ft.Row(
                            wrap=True,
                            spacing=6,
                            run_spacing=6,
                            expand=True,
                            controls=[
                                ft.Chip(
                                    label=ft.Text(dauer_text(s)),
                                    selected=s == profil.gesamt_s(),
                                    show_checkmark=False,
                                    disabled=laufend,
                                    on_select=dauer_waehler(s),
                                )
                                for s in EINMAL_DAUERN_S
                            ],
                        ),
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
                value=EINMAL, label=ft.Text("Timer"), icon=ft.Icon(ft.Icons.HOURGLASS_BOTTOM)
            ),
            ft.Segment(
                value=PROFILE, label=ft.Text("Profile"), icon=ft.Icon(ft.Icons.FORMAT_LIST_BULLETED)
            ),
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
        ],
    )
    if reiter == PROFILE:
        wahl: list[ft.Control] = [
            kartentitel(
                "Profil",
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED, tooltip="Profil bearbeiten", on_click=bearbeiten
                ),
                ft.IconButton(ft.Icons.ADD, tooltip="Neues Profil", on_click=neu),
            ),
            profil_chips,
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
        ablauf_karte = karte(kartentitel("Ablauf"), ablauf, abstand=6)
    inhalt = ft.Column(
        spacing=14,
        controls=[
            reiter_wahl,
            *wahl,
            karte(
                abschnitt_text,
                # Ein Tipp auf die Zeit stellt einen Timer ohne Ablauf (P79 D4)
                ft.Container(
                    content=zeit_text,
                    on_click=None if laufend else zeit_stellen,
                    tooltip=None if laufend else "Zeit stellen — Timer ohne Ablauf",
                    border_radius=16,
                ),
                fortschritt,
                stand_text,
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
    """Über einem Plan: den Plan als Ablauf — jede Übung mit ihrem Timer (Skizze 8)."""
    teile = [t for t in basis.split("/") if t]
    if teile[:1] != ["plan"] or len(teile) != 2:
        return None
    plan = state.plaene.laden(teile[1])
    if plan is None or not plan.items:
        return None

    async def oeffnen() -> None:
        await page.push_route(f"{timer_route(basis)}/ablauf")

    return karte(
        kartentitel(f"Plan „{plan.name}“"),
        hinweis(
            "Als Ablauf: jede Übung mit ihrem Timer, nacheinander — eingetragen wird je "
            "Übung, sobald sie endet."
        ),
        ft.FilledTonalButton("Ablauf öffnen", icon=ft.Icons.PLAYLIST_PLAY, on_click=oeffnen),
    )


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
    titel: str = "Timer-Profil"
    titel_neu: str = "Neues Timer-Profil"
    #: ohne Namensfeld — der Einmal-Timer heißt auf der Timer-Seite (Ben, 19.10.2026)
    ohne_name: bool = False
    #: „Als Profil speichern“: legt eine Kopie mit Namen in die Bibliothek — ``None``: nicht
    als_profil: Callable[[TimerProfil], None] | None = None


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
        titel="Timer: Abschnitte und Runden",
        ohne_name=True,
        als_profil=bibliothek(state, basis).speichern,
    )


@dataclass
class _Zeile:
    """Ein Abschnitt im Editor."""

    name: ft.TextField
    dauer: ft.TextField
    klang: ft.Dropdown
    zaehlt: bool = True


@dataclass
class _TeilFelder:
    """Ein Teil im Editor — seine Abschnitte und Runden."""

    name: ft.TextField
    zeilen: list[_Zeile] = field(default_factory=list)
    runden: int = 1


def timer_bearbeiten_view(
    page: Any,
    state: AppState,
    profil_id: str | None,
    basis: str,
    ziel: Profilziel | None = None,
) -> ft.View:
    """Name, Teile mit Abschnitten (Name, mm:ss, Klang, zählt) und Runden, die Klänge —
    anlegen oder ändern.

    Eine **Folge** reiht Teile: Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 ×
    (Ben, 17.10.2026); ein Profil mit einem Teil ist ein gewöhnlicher Timer. Je
    Abschnitt „zählt“ (Vorgabe) oder „zählt nicht“ als Übungszeit.

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
        visible=not ziel.ohne_name,
    )
    teile_ed: list[_TeilFelder] = []
    teile_spalte = ft.Column(spacing=16)
    runden_klang = _klang_wahl(page, state, profil.runden_klang, "wie Abschnitt 1")
    ende_klang = _klang_wahl(page, state, profil.ende_klang, "Fanfare")
    gesamt_text = ft.Text(size=13, opacity=0.75)

    def gesamt() -> None:
        summe = sum(
            sum(dauer_lesen(z.dauer.value or "") or 0 for z in t.zeilen) * t.runden
            for t in teile_ed
        )
        gesamt_text.value = f"Gesamt {dauer_text(summe)}"

    def dauer_geaendert() -> None:
        gesamt()
        with contextlib.suppress(Exception):
            gesamt_text.update()

    def zeile(a: Abschnitt) -> _Zeile:
        return _Zeile(
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
            a.zaehlt,
        )

    def teil_felder(teil: Teil) -> _TeilFelder:
        return _TeilFelder(
            ft.TextField(label="Teil", value=teil.name, dense=True, hint_text="z. B. Vorbereitung"),
            [zeile(a) for a in teil.abschnitte],
            max(teil.runden, 1),
        )

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

    def hinzufuegen(k: int) -> Callable[[], None]:
        def handler() -> None:
            teile_ed[k].zeilen.append(zeile(Abschnitt("", 60)))
            neu_zeichnen()

        return handler

    def runden_aendern(k: int, delta: int) -> Callable[[], None]:
        def handler() -> None:
            t = teile_ed[k]
            t.runden = min(max(t.runden + delta, 1), MAX_RUNDEN)
            neu_zeichnen()

        return handler

    def teil_hinzufuegen() -> None:
        teile_ed.append(teil_felder(Teil([Abschnitt("Cooldown", 60, zaehlt=False)], 1, "Cooldown")))
        neu_zeichnen()

    def teil_entferner(k: int) -> Callable[[], None]:
        def handler() -> None:
            if len(teile_ed) > 1:
                del teile_ed[k]
                neu_zeichnen()

        return handler

    def teil_karte(k: int, t: _TeilFelder) -> ft.Control:
        folge = len(teile_ed) > 1
        kopf: list[ft.Control] = (
            [
                ft.Row(
                    controls=[
                        ft.Container(expand=True, content=t.name),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Teil entfernen",
                            on_click=teil_entferner(k),
                        ),
                    ]
                )
            ]
            if folge
            else [kartentitel("Abschnitte")]
        )
        if k == 0:
            kopf.append(
                hinweis(
                    "Je Abschnitt ein Name, die Dauer in Minuten:Sekunden und der Klang, mit "
                    "dem er beginnt — etwa Glocke 1 für Belastung, Glocke 3 für die Pause. "
                    "„zählt“: seine Zeit wird als Übungszeit eingetragen."
                )
            )
        zeilen: list[ft.Control] = [
            ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(expand=True, content=z.name),
                            ft.Container(width=96, content=z.dauer),
                            ft.IconButton(
                                ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                tooltip="Abschnitt entfernen",
                                on_click=entferner(k, i),
                                disabled=len(t.zeilen) <= 1,
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(expand=True, content=z.klang),
                            ft.TextButton(
                                "zählt" if z.zaehlt else "zählt nicht",
                                icon=ft.Icons.CHECK if z.zaehlt else ft.Icons.REMOVE,
                                tooltip="Tippen schaltet um",
                                on_click=zaehlt_umschalter(k, i),
                            ),
                        ],
                    ),
                ],
            )
            for i, z in enumerate(t.zeilen)
        ]
        return karte(
            *kopf,
            *zeilen,
            ft.TextButton("Abschnitt hinzufügen", icon=ft.Icons.ADD, on_click=hinzufuegen(k)),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Runden", size=13, expand=True),
                    ft.IconButton(ft.Icons.REMOVE, on_click=runden_aendern(k, -1)),
                    ft.Text(
                        str(t.runden),
                        size=18,
                        weight=ft.FontWeight.W_600,
                        width=36,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.IconButton(ft.Icons.ADD, on_click=runden_aendern(k, 1)),
                ],
            ),
        )

    def zeichnen() -> None:
        teile_spalte.controls = [teil_karte(k, t) for k, t in enumerate(teile_ed)]
        gesamt()

    def stand() -> tuple[Any, ...]:
        """Alles, was man hier ändern kann — für „Zurück speichert“ (Ben, 16.10.2026)."""
        return (
            name.value or "",
            [
                (
                    t.name.value or "",
                    [
                        (z.name.value or "", z.dauer.value or "", z.klang.value, z.zaehlt)
                        for z in t.zeilen
                    ],
                    t.runden,
                )
                for t in teile_ed
            ],
            runden_klang.value,
            ende_klang.value,
        )

    def bauen(profil_id: str, profil_name: str) -> TimerProfil | str:
        """Das Profil aus den Feldern — oder der Grund, warum nicht (Felder markiert)."""
        teile_neu: list[Teil] = []
        fehler = False
        for t in teile_ed:
            abschnitte: list[Abschnitt] = []
            for z in t.zeilen:
                dauer = dauer_lesen(z.dauer.value or "")
                z.dauer.error = None if dauer else "z. B. 0:30"
                fehler = fehler or dauer is None
                if dauer:
                    abschnitte.append(
                        Abschnitt(
                            (z.name.value or "").strip(), dauer, _klang_wert(z.klang), z.zaehlt
                        )
                    )
            teile_neu.append(Teil(abschnitte, t.runden, (t.name.value or "").strip()))
        if fehler or not all(t.abschnitte for t in teile_neu):
            page.update()
            return "Eine Dauer ist unlesbar — so: 0:30 oder 1:15."
        erster, *weitere = teile_neu
        return TimerProfil(
            id=profil_id,
            name=profil_name,
            abschnitte=erster.abschnitte,
            runden=erster.runden,
            runden_klang=_klang_wert(runden_klang),
            ende_klang=_klang_wert(ende_klang),
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

    def als_profil_fragen() -> None:
        """„Als Profil speichern“ (Einmal-Timer): erst hier braucht es einen Namen."""
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
            title=ft.Text("Als Profil speichern"),
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
        if sichern() is not None:
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
                title=ft.Text("Profil löschen?"),
                content=ft.Text(
                    "Gibt es danach kein eigenes Profil mehr, kommen die zwei Vorlagen zurück."
                    if ziel.titel == "Timer-Profil"
                    else "Das Profil verschwindet aus dieser Übung."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Löschen", on_click=loeschen),
                ],
            )
        )

    async def abbrechen() -> None:
        await page.push_route(ziel.zurueck)

    teile_ed.extend(teil_felder(t) for t in profil.alle_teile())
    zeichnen()
    anfang = stand()

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
                            tooltip="Als Profil speichern — mit Namen in die Bibliothek",
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
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=16,
                    controls=[
                        name,
                        hinweis(
                            "Gilt für den Einmal-Timer — ohne Namen, ohne Profil. Das Lesezeichen "
                            "oben legt ihn mit Namen in die Bibliothek."
                        )
                        if ziel.ohne_name
                        else ft.Container(height=0),
                        teile_spalte,
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    "Teil anhängen",
                                    icon=ft.Icons.ADD,
                                    tooltip="Eine Folge: Vorbereitung, Training, Cooldown …",
                                    on_click=teil_hinzufuegen,
                                ),
                                ft.Container(width=8),
                                gesamt_text,
                            ]
                        ),
                        hinweis(
                            "Ein Teil läuft so viele Runden, wie bei ihm steht; dann kommt der "
                            "nächste — etwa Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 ×."
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
        meldung="Übernommen" if ziel.ohne_name else "Timer-Profil gespeichert",
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
