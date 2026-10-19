"""Leisten und Reiter einer Einheit (Ben, 17.10.2026; ``docs/plan_einheit.md`` §9, Skizzen 16–19).

**Bereitgestellt** steht auf jeder Seite außer „Heute“ nur die **Infoleiste**: eine Zeile mit
den Teilen als Symbolen (der nicht bereite mit Rand), „2 von 3 bereit“ und dem Stand des
langsamsten Teils; ▶ startet alles, Antippen öffnet „Heute“ im Reiter **„Einheit“**. Dort
steht die **Startkarte**: alles Bereitgestellte mit seinem Stand („läuft seit 41:12 · bekommt
eine Marke“, „sucht Empfang … 24 m“), was geschieht, wenn der Timer fertig ist, der Countdown
und „Alle starten“.

**Läuft** die Einheit, zeigt jede andere Seite — und der Reiter „Heute“ — die **Laufleiste**:
eine Zeit, der laufende Abschnitt, ⏸ für den Timer (die HRV pausiert nie), ⏹ für alles. Der
Reiter „Einheit“ zeigt die **Übersicht**: Laufzeit, den Timer mit seiner Fortschrittsleiste,
je Teil einen Live-Wert, die Intervalle — und was am Ende des Timers geschieht, auch jetzt
noch änderbar.

Alles baut seine Knöpfe nur neu, wenn sich an ihnen etwas ändert; im Sekundentakt ändern
sich nur Texte (Zeit, Abschnitt, Stand eines Teils wie die GPS-Genauigkeit) — sonst ginge
ein Tipp verloren, der gerade läuft (wie in der Statuskarte der Messung, 17.10.2026).
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from typing import Any, cast

import flet as ft

from trainingsapp.core.einheit import Zustand
from trainingsapp.core.intervalle import HfReihe
from trainingsapp.core.laufend import uhr
from trainingsapp.core.strecke import SPORT_NAMEN
from trainingsapp.core.timer import TimerLauf, dauer_text
from trainingsapp.devices.einheit import TimerBaustein
from trainingsapp.devices.plan_ablauf import PAUSE, PlanAblaufBaustein
from trainingsapp.devices.strecke_baustein import StreckeBaustein
from trainingsapp.ui import einheit as ablauf
from trainingsapp.ui.components.fortschritt import Fortschrittsleiste
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.tabellen import (
    intervall_tabelle,
    km_text,
    live_tabellen,
    tempo_text,
)
from trainingsapp.ui.state import AppState

#: Symbol je Teil
SYMBOLE: dict[str, Any] = {
    "hrv": ft.Icons.FAVORITE_BORDER,
    "timer": ft.Icons.TIMER_OUTLINED,
    "gps": ft.Icons.LOCATION_ON_OUTLINED,
    "plan": ft.Icons.LIST_ALT,
}

#: Kurzname je Teil — für die eine Zeile der Infoleiste
KURZ = {"hrv": "HRV", "timer": "Timer", "gps": "GPS", "plan": "Plan"}


def _teil_titel(teil: Any) -> str:
    if teil.art == "timer":
        return f"Timer · {teil.lauf.profil.name}"
    if teil.art == "gps":
        sport = SPORT_NAMEN.get(getattr(teil, "sportart", ""), "Training")
        return f"{sport} · GPS" if getattr(teil, "quelle", None) is not None else sport
    if teil.art == "plan" and getattr(teil, "name", ""):
        return f"{'Plan-Ablauf' if hasattr(teil, 'schritte') else 'Übung'} · {teil.name}"
    return {"hrv": "HRV-Messung", "plan": "Plan"}.get(teil.art, teil.art)


def _symbol(teil: Any) -> Any:
    if teil.art == "gps" and getattr(teil, "quelle", None) is None:
        return ft.Icons.DIRECTIONS_RUN  # Laufband, Halle
    return SYMBOLE.get(teil.art, ft.Icons.CIRCLE)


def _marke(teil: Any) -> tuple[str, Any, Any]:
    """Die kleine Marke rechts: Text, Hintergrund, Schrift."""
    if teil.art == "hrv" and teil.messlauf.aufnahme is not None:
        return "läuft", ft.Colors.SECONDARY_CONTAINER, ft.Colors.ON_SECONDARY_CONTAINER
    if teil.bereit:
        return "bereit", ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER
    return "bereitet vor", ft.Colors.TERTIARY_CONTAINER, ft.Colors.ON_TERTIARY_CONTAINER


async def zur_einheit(page: Any, state: AppState) -> None:
    """Antippen der Info- oder Laufleiste: „Heute“, Reiter „Einheit“."""
    state.reiter = "heute"
    ablauf.heute_reiter_waehlen(state, ablauf.REITER_EINHEIT)
    if getattr(page, "route", "/") == "/":
        state.neu_zeichnen()  # schon in der Hauptansicht — nur ein anderer Reiter
    else:
        await page.push_route("/")


def _oeffner(page: Any, state: AppState, teil: Any) -> Callable[[], Any] | None:
    """Ein Tipp auf die Zeile eines Teils im Reiter „Einheit“: dorthin, wo man ihn bedient
    (Ben, 18.10.2026: „Klick auf den Plan öffnet aber nicht das entsprechende Menü“) — der
    Plan-Ablauf in seine Ablaufansicht, die HRV in den Reiter „Messung“
    (`ui.einheit.teil_route`)."""
    if teil.art == "hrv":

        async def zur_messung() -> None:
            state.reiter = "messung"
            if getattr(page, "route", "/") == "/":
                state.neu_zeichnen()
            else:
                await page.push_route("/")

        return zur_messung
    route = ablauf.teil_route(teil)
    if route is None:
        return None

    async def oeffnen() -> None:
        await page.push_route(route)

    return oeffnen


def _timer_oeffner(page: Any, e: Any) -> Callable[[], Any]:
    """Der Timer der Einheit: gehört er zu einer Übung oder zum Plan-Ablauf, dorthin."""

    async def oeffnen() -> None:
        await page.push_route(ablauf.timer_route(e))

    return oeffnen


def _selbst_auffrischend(
    page: Any,
    state: AppState,
    e: Any,
    box: ft.Container,
    schluessel: Callable[[], tuple],
    bauen: Callable[[dict], None],
    *,
    name: str,
    sichtbar: Callable[[], bool] = lambda: True,
) -> None:
    """Baut ``box`` mit ``bauen(stand)`` und frischt sie im Takt der Einheit auf
    (`ui.einheit.melden`): neu gebaut nur, wenn sich ``schluessel()`` ändert, sonst nur
    die Texte (``stand["texte"]``). Verdeckt (``sichtbar()`` falsch) geschieht nichts — beim
    nächsten Zeigen wird ohnehin neu gebaut."""
    stand: dict[str, Any] = {"schluessel": None, "texte": None}

    def neu() -> None:
        stand["schluessel"] = schluessel()
        stand["texte"] = None
        bauen(stand)

    def auffrischen() -> None:
        if ablauf.aktuell(state) is not e or not sichtbar():
            return  # vorbei — der Neuaufbau nimmt sie weg
        if schluessel() != stand["schluessel"]:
            neu()
        elif stand["texte"] is not None:
            stand["texte"]()
        with contextlib.suppress(Exception):
            box.update()

    state.einheit_beobachter[name] = auffrischen
    neu()


# ---------------------------------------------------------------------------
# Die feste Leiste: Infoleiste und Laufleiste
# ---------------------------------------------------------------------------


def startleiste(page: Any, state: AppState, *, haupt: bool = False) -> ft.Container | None:
    """Die feste Leiste unter der Titelleiste — ``None`` ohne Einheit (die Ansicht bleibt
    unverändert). Bereitgestellt die Infoleiste, im Lauf die Laufleiste.

    ``haupt``: Die Hauptansicht liegt oben. Auf „Heute“ steht dann im Reiter „Einheit“
    keine Leiste (dort steht alles) und im Reiter „Heute“ nur die Laufleiste.
    """
    e = ablauf.aktuell(state)
    if e is None:
        return None

    async def oeffnen() -> None:
        await zur_einheit(page, state)

    box = ft.Container(border_radius=16, ink=True, on_click=oeffnen)

    def art() -> str:
        if haupt and state.reiter == "heute":
            if ablauf.heute_reiter(state) == ablauf.REITER_EINHEIT:
                return ""
            return "lauf" if e.laeuft else ""
        return "lauf" if e.laeuft else "info"

    def schluessel() -> tuple:
        wo = art()
        if wo == "lauf":
            t = e.timer
            return (wo, e.zustand, _timer_schluessel(t))
        if wo == "info":
            return (
                wo,
                tuple((id(t), t.bereit) for t in e.teile),
                tuple(e.fehler),
                e.bereit,
                state.einheit_countdown,
            )
        return (wo,)

    def bauen(stand: dict) -> None:
        wo = stand["schluessel"][0]
        box.visible = bool(wo)
        if wo == "lauf":
            _laufleiste(page, state, e, box, stand)
        elif wo == "info":
            _infoleiste(page, state, e, box, stand)
        else:
            box.content = None

    _selbst_auffrischend(page, state, e, box, schluessel, bauen, name="leiste")
    return box


def _timer_schluessel(t: TimerBaustein | None) -> tuple:
    if t is None:
        return (None,)
    return (id(t), t.lauf.laeuft, t.lauf.fertig)


def _info_texte(e: Any) -> tuple[str, str, bool]:
    """Die Infoleiste: wie viel bereit ist, darunter der Stand des langsamsten Teils —
    oder ein Fehler (dann rot); ist alles bereit, was startet."""
    bereit = sum(1 for t in e.teile if t.bereit)
    if bereit < len(e.teile):
        oben = f"{bereit} von {len(e.teile)} bereit"
    else:
        oben = "Alles bereit" if len(e.teile) > 1 else "Bereit"
    if e.fehler:
        return oben, next(iter(e.fehler.values())), True
    langsam = next((t for t in e.teile if not t.bereit), None)
    if langsam is None:
        return oben, e.titel or ablauf.titel(e), False
    kurz, text = KURZ.get(langsam.art, langsam.art), langsam.status()
    return oben, text if text.startswith(kurz) else f"{kurz} {text}", False


def _infoleiste(page: Any, state: AppState, e: Any, box: ft.Container, stand: dict) -> None:
    """Eine Zeile (Skizze 16): die Teile, „2 von 3 bereit“, der Stand, ▶."""
    box.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
    box.padding = ft.Padding.only(left=10, right=2, top=6, bottom=6)
    symbole: list[ft.Control] = []
    for teil in e.teile:
        _, grund, schrift = _marke(teil)
        symbole.append(
            ft.Container(
                width=26,
                height=26,
                border_radius=13,
                bgcolor=grund,
                border=None if teil.bereit else ft.Border.all(2, ft.Colors.TERTIARY),
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(_symbol(teil), size=15, color=schrift),
            )
        )
    oben = ft.Text(size=14, weight=ft.FontWeight.W_700, max_lines=1)
    unten = ft.Text(size=12, opacity=0.8, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def texte() -> None:
        oben.value, unten.value, fehler = _info_texte(e)
        unten.color = ft.Colors.ERROR if fehler else None

    texte()
    stand["texte"] = texte

    def starten() -> None:
        ablauf.alle_starten(page, state, ablauf.COUNTDOWN_S if state.einheit_countdown else 0.0)

    box.content = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Row(spacing=3, tight=True, controls=symbole),
            ft.Column(spacing=0, expand=True, tight=True, controls=[oben, unten]),
            ft.FilledIconButton(
                ft.Icons.PLAY_ARROW,
                tooltip="Alle starten"
                + (" (Countdown 3 – 2 – 1)" if state.einheit_countdown else ""),
                disabled=not e.bereit,
                on_click=starten,
            ),
            ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.6),
        ],
    )


def _lauf_knoepfe(page: Any, state: AppState, e: Any) -> list[ft.Control]:
    """⏸ für den Timer (nicht im Countdown, nicht wenn er fertig ist), ⏹ für alles."""
    t = e.timer
    knoepfe: list[ft.Control] = []
    if t is not None and not t.lauf.fertig and e.zustand is Zustand.LAEUFT:
        knoepfe.append(
            ft.IconButton(
                ft.Icons.PAUSE if t.lauf.laeuft else ft.Icons.PLAY_ARROW,
                tooltip="Timer anhalten" if t.lauf.laeuft else "Timer fortsetzen",
                on_click=lambda: ablauf.anhalten_oder_weiter(page, state),
            )
        )
    knoepfe.append(
        ft.IconButton(
            ft.Icons.STOP, tooltip="Alles beenden", on_click=lambda: _beenden_fragen(page, state, e)
        )
    )
    return knoepfe


def _laufleiste(page: Any, state: AppState, e: Any, box: ft.Container, stand: dict) -> None:
    """Zeit und Abschnitt, darunter die Teile, ⏸ ⏹ (Skizze 17)."""
    box.bgcolor = ft.Colors.PRIMARY_CONTAINER
    box.padding = ft.Padding.only(left=12, right=6, top=8, bottom=8)
    zeile1 = ft.Text(size=15, weight=ft.FontWeight.W_700, color=ft.Colors.ON_PRIMARY_CONTAINER)
    zeile2 = ft.Text(size=12, color=ft.Colors.ON_PRIMARY_CONTAINER)

    def texte() -> None:
        zeile1.value, zeile2.value = ablauf.laufzeilen(e)

    texte()
    stand["texte"] = texte
    box.content = ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=14, color=ft.Colors.RED_700),
            ft.Column(spacing=0, expand=True, tight=True, controls=[zeile1, zeile2]),
            *_lauf_knoepfe(page, state, e),
        ],
    )


# ---------------------------------------------------------------------------
# Der Reiter „Einheit“ auf „Heute“: Startkarte und Übersicht
# ---------------------------------------------------------------------------


def _reiter_sichtbar(page: Any, state: AppState) -> bool:
    """Liegt der Reiter „Einheit“ oben? Sonst frischt er nichts auf."""
    return (
        getattr(page, "route", "/") == "/"
        and state.reiter == "heute"
        and ablauf.heute_reiter(state) == ablauf.REITER_EINHEIT
    )


def reiter_titel(page: Any, state: AppState) -> ft.Control:
    """„Einheit · 3“ mit einem Punkt (orange: es bereitet noch etwas vor, sonst grün) —
    im Lauf „Einheit läuft“ mit rotem Punkt (Skizzen 18, 19)."""
    e = ablauf.aktuell(state)
    punkt = ft.Container(width=8, height=8, border_radius=4)
    text = ft.Text()

    def zeigen() -> None:
        if e is None:
            return
        if e.laeuft:
            text.value, punkt.bgcolor = "Einheit läuft", ft.Colors.RED_700
        else:
            text.value = f"Einheit · {len(e.teile)}"
            punkt.bgcolor = ft.Colors.PRIMARY if e.bereit else ft.Colors.TERTIARY

    def auffrischen() -> None:
        if ablauf.aktuell(state) is not e or getattr(page, "route", "/") != "/":
            return
        if state.reiter != "heute":
            return  # verdeckt
        zeigen()
        for c in (punkt, text):
            with contextlib.suppress(Exception):
                c.update()

    zeigen()
    state.einheit_beobachter["reiter_titel"] = auffrischen
    return ft.Row(
        tight=True,
        spacing=6,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[punkt, text],
    )


def einheit_reiter(page: Any, state: AppState) -> ft.Control:
    """Der Reiter „Einheit“: bereitgestellt die Startkarte in voller Höhe, im Lauf die
    Übersicht (Skizzen 18, 19)."""
    e = ablauf.aktuell(state)
    box = ft.Container()
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(padding=ft.Padding.only(left=12, right=12, top=12, bottom=24), content=box)
        ],
    )
    if e is None:
        return spalte
    hf_reihe = HfReihe()

    def schluessel() -> tuple:
        if e.laeuft:
            return (
                "lauf",
                e.zustand,
                tuple(t.art for t in e.teile),
                _timer_schluessel(e.timer),
                e.ende_mit_timer,
                e.stoppt_am_ende("hrv"),
            )
        return (
            "start",
            tuple((id(t), t.bereit) for t in e.teile),
            tuple(e.fehler.items()),
            e.bereit,
            e.ende_mit_timer,
            e.stoppt_am_ende("hrv"),
            state.einheit_countdown,
        )

    def bauen(stand: dict) -> None:
        if e.laeuft:
            _uebersicht(page, state, e, box, stand, hf_reihe)
        else:
            _startkarte(page, state, e, box, stand)

    _selbst_auffrischend(
        page,
        state,
        e,
        box,
        schluessel,
        bauen,
        name="reiter",
        sichtbar=lambda: _reiter_sichtbar(page, state),
    )
    return spalte


def _startkarte(page: Any, state: AppState, e: Any, box: ft.Container, stand: dict) -> None:
    """Alles Bereitgestellte mit seinem Stand, „Wenn der Timer fertig ist“, Countdown und
    „Alle starten“ (Skizze 18)."""
    box.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
    box.border_radius = 16
    box.padding = ft.Padding.only(left=12, right=6, top=8, bottom=10)
    status_texte: list[ft.Text] = []

    def raus(art: str) -> Callable[[], None]:
        def handler() -> None:
            ablauf.zuruecknehmen(page, state, art)

        return handler

    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Bereitgestellt", size=15, weight=ft.FontWeight.W_700, expand=True),
                ft.TextButton("Leeren", on_click=lambda: ablauf.leeren(page, state)),
            ],
        )
    ]
    for teil in e.teile:
        text, grund, schrift = _marke(teil)
        status = ft.Text(teil.status(), size=12, opacity=0.75)
        status_texte.append(status)
        oeffnen = _oeffner(page, state, teil)
        zeilen.append(
            ft.Container(
                bgcolor=ft.Colors.SURFACE,
                border_radius=12,
                padding=ft.Padding.only(left=10, right=2, top=4, bottom=4),
                ink=oeffnen is not None,
                on_click=oeffnen,
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(_symbol(teil), size=20),
                        ft.Column(
                            spacing=0,
                            expand=True,
                            tight=True,
                            controls=[
                                ft.Text(_teil_titel(teil), size=14, weight=ft.FontWeight.W_600),
                                status,
                            ],
                        ),
                        ft.Container(
                            bgcolor=grund,
                            border_radius=10,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            content=ft.Text(
                                text, size=11, weight=ft.FontWeight.W_700, color=schrift
                            ),
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=18,
                            tooltip="Herausnehmen",
                            on_click=raus(teil.art),
                        ),
                    ],
                ),
            )
        )
    for fehler in e.fehler.values():
        zeilen.append(ft.Text(fehler, size=12, color=ft.Colors.ERROR))

    if isinstance(e.teil("timer"), TimerBaustein) and len(e.teile) > 1:
        zeilen.append(_bei_timer_ende(state, e))

    def countdown(ev: Any) -> None:
        state.einheit_countdown = bool(ev.control.value)
        ablauf.melden(state)

    zeilen.append(
        ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Countdown 3 – 2 – 1", size=13, expand=True),
                ft.Switch(value=state.einheit_countdown, on_change=countdown),
            ],
        )
    )

    def starten() -> None:
        ablauf.alle_starten(page, state, ablauf.COUNTDOWN_S if state.einheit_countdown else 0.0)

    zeilen.append(
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.FilledButton(
                    "Alle starten",
                    icon=ft.Icons.PLAY_ARROW,
                    disabled=not e.bereit,
                    on_click=starten,
                    expand=True,
                ),
                ft.TextButton("Trotzdem starten", visible=not e.bereit, on_click=starten),
            ],
        )
    )

    def texte() -> None:
        for status, teil in zip(status_texte, e.teile, strict=False):
            status.value = teil.status()

    stand["texte"] = texte
    box.content = ft.Column(spacing=8, tight=True, controls=zeilen)


def _bei_timer_ende(state: AppState, e: Any, *, im_lauf: bool = False) -> ft.Control:
    """„Wenn der Timer fertig ist“: Endet die Einheit mit ihm, und endet die HRV mit? Beides
    wirkt erst am Ende des Timers bzw. der Einheit — darum auch im Lauf noch änderbar (Ben,
    17.10.2026)."""

    def mit_timer(ev: Any) -> None:
        e.ende_mit_timer = bool(ev.control.value)
        ablauf.melden(state)

    def hrv_beenden(ev: Any) -> None:
        e.am_ende_stoppen["hrv"] = bool(ev.control.value)
        ablauf.melden(state)

    kopf = "Wenn der Timer fertig ist" + (" – auch jetzt noch änderbar" if im_lauf else "")
    controls: list[ft.Control] = [
        ft.Text(kopf, size=12, weight=ft.FontWeight.W_600, opacity=0.75),
        ft.Checkbox(label="Einheit beenden", value=e.ende_mit_timer, on_change=mit_timer),
    ]
    if im_lauf and not e.ende_mit_timer:
        controls.append(hinweis("Sie läuft nach dem Timer weiter, bis du sie beendest."))
    if e.hrv is not None:
        controls.append(
            ft.Checkbox(
                label="HRV-Messung beenden (sonst läuft sie weiter)",
                value=e.stoppt_am_ende("hrv"),
                on_change=hrv_beenden,
            )
        )
    return ft.Column(spacing=0, tight=True, controls=controls)


def _kopfzeile(e: Any) -> str:
    """„Intervalllauf · seit 15:31“ — die Startzeit in Ortszeit."""
    name = e.titel or ablauf.titel(e)
    seit = e.anzeige_seit_utc()
    if seit is None or e.zustand is Zustand.COUNTDOWN:
        return name
    return f"{name} · seit {seit.astimezone().strftime('%H:%M')}"


def _laufzeit(e: Any) -> str:
    if e.zustand is Zustand.COUNTDOWN:
        return f"Start in {max(0, math.ceil(-e.dauer_s()))} …"
    return uhr(max(e.anzeige_dauer_s(), 0.0))


def _timer_zeilen(lauf: TimerLauf) -> tuple[str, str]:
    """Rechts „noch 1:36“, darunter „Belastung · Runde 2 von 4“."""
    stand = lauf.stand()
    if stand.fertig:
        return "fertig", f"{lauf.profil.name} fertig" if lauf.vorwaerts else "Timer fertig"
    if lauf.vorwaerts:  # die Stoppuhr (18.10.2026): die gelaufene Zeit
        return lauf.anzeige(), lauf.profil.name + ("" if stand.laeuft else " · angehalten")
    name = stand.name or f"Abschnitt {stand.index + 1}"
    if stand.runden > 1:
        name += f" · Runde {stand.runde} von {stand.runden}"
    if not stand.laeuft and lauf.begonnen:
        name += " · angehalten"
    return f"noch {dauer_text(math.ceil(stand.rest_s))}", name


def _live_wert(e: Any, teil: Any) -> str:
    """Je Teil ein Wert, der im Lauf zählt (Skizze 19)."""
    if teil.art == "hrv":
        lauf = teil.messlauf
        if lauf.aufnahme is None:
            return str(teil.status())
        teile = [f"seit {uhr(lauf.aufnahme_dauer_s())}"]
        with contextlib.suppress(Exception):
            if hf := lauf.live.kennzahlen().hf_bpm:
                teile.append(f"HF {hf}")
        if not e.stoppt_am_ende("hrv"):
            teile.append("läuft danach weiter")
        return " · ".join(teile)
    if isinstance(teil, StreckeBaustein):
        if not teil.mit_gps:
            return str(teil.status())
        r = teil.rechner
        text = f"{km_text(r.distanz_m)} · {tempo_text(teil.sportart, r.tempo_s_pro_km)}"
        return text + (" · Pause" if r.pausiert and r.distanz_m > 0 else "")
    if isinstance(teil, PlanAblaufBaustein):
        text = f"Übung {teil.k + 1} von {len(teil.schritte)} · {teil.schritt.name}"
        return text + (" · Pause" if teil.phase == PAUSE else "")
    return str(teil.status())


def _uebersicht(
    page: Any, state: AppState, e: Any, box: ft.Container, stand: dict, hf_reihe: HfReihe
) -> None:
    """Die laufende Einheit (Skizze 19): Kopf mit Laufzeit und ⏸ ⏹, der Timer mit
    Fortschrittsleiste, „Wenn der Timer fertig ist“, je Teil ein Live-Wert, die Intervalle."""
    box.bgcolor, box.border_radius, box.padding = None, None, None
    auffrischer: list[Callable[[], None]] = []
    farbe = ft.Colors.ON_PRIMARY_CONTAINER
    kopf_text = ft.Text(size=12, weight=ft.FontWeight.W_600, color=farbe)
    laufzeit = ft.Text(size=24, weight=ft.FontWeight.W_700, color=farbe)

    def kopf_auffrischen() -> None:
        kopf_text.value, laufzeit.value = _kopfzeile(e), _laufzeit(e)

    auffrischer.append(kopf_auffrischen)
    karten: list[ft.Control] = [
        ft.Container(
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=16,
            padding=ft.Padding.only(left=14, right=6, top=10, bottom=10),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=14, color=ft.Colors.RED_700),
                    ft.Column(spacing=0, expand=True, tight=True, controls=[kopf_text, laufzeit]),
                    *_lauf_knoepfe(page, state, e),
                ],
            ),
        )
    ]

    t = e.timer
    if t is not None:
        leiste = Fortschrittsleiste(t.lauf)
        rest = ft.Text(size=13)
        abschnitt = ft.Text(size=14, weight=ft.FontWeight.W_600)

        def timer_auffrischen() -> None:
            rest.value, abschnitt.value = _timer_zeilen(t.lauf)
            leiste.auffrischen()

        auffrischer.append(timer_auffrischen)
        timer_karte = cast(
            ft.Container,
            karte(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.TIMER_OUTLINED, size=18),
                        ft.Text(
                            f"Timer · {t.lauf.profil.name}",
                            size=14,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                        rest,
                    ],
                ),
                abschnitt,
                leiste.control,
                abstand=6,
            ),
        )
        # Antippen: der Timer — bzw. die Übung oder der Ablauf, zu dem er gehört
        timer_karte.ink = True
        timer_karte.on_click = _timer_oeffner(page, e)
        karten.append(timer_karte)
    eigener = e.teil("timer")
    if isinstance(eigener, TimerBaustein) and not eigener.lauf.fertig and len(e.teile) > 1:
        karten.append(karte(_bei_timer_ende(state, e, im_lauf=True), abstand=0))

    zeilen: list[ft.Control] = []
    for teil in e.teile:
        if teil.art == "timer":
            continue  # steht oben mit seiner Fortschrittsleiste
        wert = ft.Text(size=13, opacity=0.85)

        def wert_auffrischen(teil: Any = teil, wert: ft.Text = wert) -> None:
            wert.value = _live_wert(e, teil)

        auffrischer.append(wert_auffrischen)
        oeffnen = _oeffner(page, state, teil)
        zeilen.append(
            ft.Container(
                border_radius=10,
                ink=oeffnen is not None,
                on_click=oeffnen,
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(_symbol(teil), size=18),
                        ft.Column(
                            spacing=0,
                            expand=True,
                            tight=True,
                            controls=[
                                ft.Text(_teil_titel(teil), size=14, weight=ft.FontWeight.W_600),
                                wert,
                            ],
                        ),
                        *([ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5)] if oeffnen else []),
                    ],
                ),
            )
        )
    if zeilen:
        karten.append(karte(*zeilen, abstand=10))

    # Intervalle — mit Strecke oder Herz; ein Timer allein hat ja schon seine Leiste
    platz = ft.Container(visible=False)
    tabelle: dict[str, Any] = {"schluessel": None}

    def intervalle_auffrischen() -> None:
        stand_jetzt = live_tabellen(e, hf_reihe)
        if not stand_jetzt.runden or not (stand_jetzt.strecke or stand_jetzt.herz):
            platz.visible = False
            return
        if (k := stand_jetzt.schluessel()) == tabelle["schluessel"]:
            return
        tabelle["schluessel"] = k
        sportart = getattr(e.teil("gps"), "sportart", "")
        platz.content = karte(
            titel("Intervalle (vom Timer)"),
            intervall_tabelle(
                stand_jetzt.runden, sportart, strecke=stand_jetzt.strecke, hf=stand_jetzt.herz
            ),
        )
        platz.visible = True

    if t is not None:
        auffrischer.append(intervalle_auffrischen)
        karten.append(platz)
    if e.warnung:
        karten.append(ft.Text(e.warnung, size=12, color=ft.Colors.ERROR))

    def texte() -> None:
        for f in auffrischer:
            with contextlib.suppress(Exception):
                f()

    texte()
    stand["texte"] = texte
    box.content = ft.Column(spacing=10, tight=True, controls=karten)


def _beenden_fragen(page: Any, state: AppState, e: Any) -> None:
    """⏹ fragt nach, wenn etwas gespeichert wird (Training, HRV) — ein Tipp daneben im
    Laufen soll nichts beenden. Nur ein Timer endet ohne Rückfrage."""
    from trainingsapp.ui.components.dialoge import schliessen

    if e.teil("gps") is None and e.hrv is None:
        ablauf.alle_beenden(state)
        return
    dialog: ft.AlertDialog

    def beenden() -> None:
        schliessen(dialog)
        ablauf.alle_beenden(state)

    saetze = ["Alles, was mit ihr begann, endet und wird gespeichert."]
    if e.hrv is not None and not e.stoppt_am_ende("hrv"):
        saetze.append("Die HRV-Messung läuft weiter.")
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Einheit beenden?"),
        content=ft.Text(" ".join(saetze)),
        actions=[
            ft.TextButton("Weiter", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden),
        ],
    )
    page.show_dialog(dialog)


def leiste_auffrischen(state: AppState) -> None:
    """Nach einem Reiterwechsel ohne Neuaufbau: Die feste Leiste zeigt, was dorthin gehört."""
    if (auffrischen := state.einheit_beobachter.get("leiste")) is not None:
        with contextlib.suppress(Exception):
            auffrischen()


def leiste_einsetzen(view: ft.View, leiste: ft.Container) -> None:
    """Die Leiste unter die Titelleiste einer Ansicht.

    Scrollt die Ansicht als Ganzes und merkt sich ihre Position nicht selbst
    (``on_scroll``), wandert ihr Inhalt in eine scrollende Spalte — so bleibt die
    Leiste stehen. Ohne Rand (Hauptansicht) bekommt die Leiste einen eigenen.
    """
    if not view.padding:
        leiste.margin = ft.Margin.only(left=12, right=12, top=4)
    if view.scroll is not None and getattr(view, "on_scroll", None) is None:
        inhalt = ft.Column(
            controls=cast(list[ft.Control], list(view.controls)),
            scroll=view.scroll,
            expand=True,
            spacing=view.spacing,
            horizontal_alignment=view.horizontal_alignment,
        )
        view.scroll = None
        view.controls = [leiste, inhalt]
    else:
        view.controls = [leiste, *view.controls]


__all__ = [
    "KURZ",
    "SYMBOLE",
    "einheit_reiter",
    "leiste_auffrischen",
    "leiste_einsetzen",
    "reiter_titel",
    "startleiste",
    "zur_einheit",
]
