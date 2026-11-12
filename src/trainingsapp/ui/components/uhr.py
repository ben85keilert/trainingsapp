"""Stoppuhr und Timer in der Übung (Ben, 18.10.2026; `docs/plan_stoppuhr.md` §5).

Eine Darstellung (P103, Ben 8.11.2026 — die „Knöpfe“ neben „Gemacht“ sind weg, die Zeile
kann alles):

- **Zeile** (Skizzen A1–A4): links als Text, was startet — die Stoppuhr oder ein Timer der
  Übung, ▾ wählt um —, daneben die Zeit, rechts „Bereitstellen“ und ein einziger ▶. So liest
  sich ▶ nie als „Timer starten“, wenn die Stoppuhr gemeint ist. Sie steht als **erste Zeile
  der Karte „Eintragen“**, vor Wiederholungen und Zeit (Ben, 27.10.2026: die Stoppuhr zählt
  als Zeit, also unter die Einstellungen zu dem, was gesammelt wird); ohne Mengen allein unter
  der Ausführung, in einem zugeklappten Block nur die laufende Anzeige (`views/plan.py`).

Läuft die Uhr dieser Übung, zeigt die Karte die Zeit und **dieselben Knöpfe wie der Fokus
und die Timer-Seite** (`docs/plan_uhren.md` §2): **Pause · Weiter** („Pause pausiert und
beendet nicht“), **Nächster** (Abschnitt), **Fertig** (trägt ein, wie die Übung zählt) und
**Abbrechen** — ohne Rückfrage, trägt nichts ein; dazu der Takt-Knopf für jetzt und ⤢ Fokus.
Die Wahl im ▾ gilt für diese Sitzung der
App und ändert keine Einstellung (Ben: „wenn im Übungsfeld ein anderer Timer ausgewählt
wurde, ändert sich keine Einstellung“); gespeichert wird nur in Übung bzw. Planübung.
Ob die Uhr überhaupt dasteht, sagt `core.uebung_timer.uhr_an`.

Ben, 22.10.2026 (P79, Skizzen D1–D4): **„zählt“** — ob die Timerzeit als Haltezeit bzw. Zeit
in den offenen Eintrag geht — gilt für jetzt (`AppState.uhr_zaehlt`), die Vorgabe kommt aus der
Übung (`Exercise.zeit_zaehlt`); der Schalter steht seit P148 im Uhr-Blatt („Uhr einstellen …“),
nicht mehr in der Zeile. Ein **Tipp
auf die Zeit** stellt einen Timer ohne Ablauf (Räder und Tippfeld, `components/zeit_stellen.py`)
und startet ihn; er bleibt für diese Sitzung zur Wahl (`AppState.uhr_einmal`).

Ben, 4.11.2026 (``docs/plan_beschleunigung.md`` §4.2): Zählt der Beschleunigungssensor in der
Einheit der Uhr dieselbe Übung („Wdh. zählen“, `components.zaehlen`), steht die Zahl mit −1/+1
auch in der laufenden Uhr; „Fertig“ der Uhr beendet beides. Beendete ein Start ein Zählen einer
anderen Übung, kommt dessen Meldung mit „Eintragen“ (`components.zaehlen.meldung_zeigen`).

Ben, 12.11.2026: **Wohin die Uhr zählt, steht am Feld** — `zaehlt_symbol` setzt in der Karte
„Eintragen“ ein Uhrensymbol hinter Haltezeit bzw. Zeit, je nachdem, wohin die Uhr einträgt
(`core.uebung_timer.zaehlt_als`); durchgestrichen, wenn sie gerade nicht zählt („zählt“ aus
oder „Ohne Uhr“). Ein Tipp schaltet „zählt“ für jetzt um — das Zielfeld wechselt man nur in
„Übung bearbeiten“ (gilt überall).
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import TimerProfil, dauer_text, einmal_timer, ohne_uhr, stoppuhr
from trainingsapp.core.uebung_timer import (
    profile_zur_wahl,
    takt_der_uebung,
    timer_fuer,
    uhr_an,
    zaehlt_als,
    zeit_zaehlt_fuer,
)
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein, UebungKontext
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehlen
from trainingsapp.ui.components.takt_anzeige import ZeitMitTakt, takt_gross
from trainingsapp.ui.components.takt_blatt import TempoRegler, takt_anbringen, takt_knopf
from trainingsapp.ui.components.zeit_stellen import zeit_blatt

#: Eckenradius wie die Knöpfe im Plan
ECKEN = ft.RoundedRectangleBorder(radius=14)


@dataclass
class UhrTeile:
    """Was die Übung von der Uhr bekommt: Knöpfe für die Reihe mit „Gemacht“ (Darstellung
    „Knöpfe“) und eine eigene Zeile darunter (die Zeile oder die laufende Anzeige)."""

    knoepfe: list[ft.Control] = field(default_factory=list)
    zeile: ft.Control | None = None


def schluessel(uebung: Exercise, item: PlanItem | None) -> str:
    """Wofür die Wahl gilt — die Planübung, ohne Plan die Übung."""
    return item.id if item is not None else uebung.id


def angebot(
    uebung: Exercise, plan: Plan | None, item: PlanItem | None, einmal: TimerProfil | None = None
) -> list[TimerProfil]:
    """Zur Wahl: die Stoppuhr, die Uhr für jetzt (``einmal``: eine gestellte Zeit, P79 D4, oder
    ein Timer mit Abschnitten), dann die Timer der Planübung, der Übung und des Plans."""
    profile = profile_zur_wahl(uebung, plan, item, mit_stoppuhr=True)
    if einmal is not None:
        profile.insert(1, einmal)
    # „Ohne Uhr — nur Fokus“ als letzte Wahl (Ben, 8.11.2026, P146)
    return [*profile, ohne_uhr()]


def fuer_jetzt_oeffnen(
    page: Any,
    state: Any,
    uebung: Exercise,
    item: PlanItem | None,
    basis: str,
    vorher_s: int,
) -> Callable[[int], Any]:
    """„Mit Abschnitten …“ im Zeit-Blatt (Ben, 9.11.2026, Skizze G1): das erweiterte Fenster
    für die Uhr dieser Übung — für jetzt, gespeichert nur per Knopf (`views.uebung_timer.
    jetzt_profilziel`). Die gestellte Zeit wird der erste Abschnitt."""
    from trainingsapp.core.timer import EINMAL
    from trainingsapp.ui.components.uhr_blatt import uebung_timer_route

    def oeffnen(sekunden: int) -> None:
        state.uhr_einmal_start[schluessel(uebung, item)] = sekunden or vorher_s

        async def gehen() -> None:
            await page.push_route(f"{uebung_timer_route(basis, uebung, item)}/bearbeiten/{EINMAL}")

        with contextlib.suppress(Exception):
            page.run_task(gehen)

    return oeffnen


def gesetzt(state: Any, uebung: Exercise, plan: Plan | None, item: PlanItem | None) -> TimerProfil:
    """Was ▶ startet: die in dieser Sitzung gewählte (oder zuletzt gestartete) Uhr — sonst
    wie eingestellt (Planübung > Plan > erster Timer der Übung), ohne Timer die Stoppuhr."""
    key = schluessel(uebung, item)
    gewaehlt = state.uhr_wahl.get(key)
    if gewaehlt:
        auswahl = angebot(uebung, plan, item, state.uhr_einmal.get(key))
        treffer = next((p for p in auswahl if p.id == gewaehlt), None)
        if treffer is not None:
            return treffer
    # „Uhr aus“ an Übung bzw. Planübung heißt „Ohne Uhr“ (P146): ▶ öffnet nur den Fokus
    if not uhr_an(uebung, item):
        return ohne_uhr()
    return timer_fuer(uebung, plan, item) or stoppuhr()


def laufende(state: Any, uebung: Exercise, item: PlanItem | None) -> Einheitslauf | None:
    """Die Einheit, in der gerade die Uhr dieser Übung (dieser Planübung) läuft."""
    e = einheit_ui.laeuft(state)
    teil = e.teil("plan") if e is not None else None
    if not isinstance(teil, UebungBaustein) or teil.kontext.uebung_id != uebung.id:
        return None
    if item is not None and teil.kontext.item_id not in (None, item.id):
        return None
    return e


#: Kennung des Uhrensymbols am Zielfeld (``data``) — zählt bzw. zählt gerade nicht
ZAEHLT_HIER = "uhr_zaehlt_hier"
ZAEHLT_HIER_NICHT = "uhr_zaehlt_hier_nicht"


def zaehlt_symbol(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan | None,
    item: PlanItem | None,
    feld: str,
    name: str,
) -> ft.Control | None:
    """Das Uhrensymbol hinter dem Feld, in das die Uhr einträgt (Ben, 12.11.2026) — ``None``
    an jedem anderen Feld. ``feld`` ist der Schlüssel der Zeile, ``name`` ihr Name für die
    Meldung. Läuft die Uhr dieser Übung, gilt, was beim Start feststand (der Kontext des
    Laufs); sonst die Wahl für jetzt (`AppState.uhr_zaehlt`) über der Vorgabe der Übung.

    Durchgestrichen heißt: hierhin zählte die Uhr, gerade aber nicht. Ein Tipp schaltet
    „zählt“ für jetzt um — bei „Ohne Uhr“ und bei laufender Uhr sagt er nur, was gilt.
    """
    key = schluessel(uebung, item)
    ziel = zaehlt_als(uebung_lauf.felder_der_uebung(uebung, item), uebung)
    e = laufende(state, uebung, item)
    teil = e.teil("plan") if e is not None and e.timer is not None else None
    laeuft = isinstance(teil, UebungBaustein)
    ohne = False
    if isinstance(teil, UebungBaustein):
        zaehlt = teil.kontext.zeitfeld is not None
        ziel = teil.kontext.zeitfeld or ziel
    else:
        ohne = gesetzt(state, uebung, plan, item).ohne_uhr
        zaehlt = state.uhr_zaehlt.get(key, zeit_zaehlt_fuer(uebung, item)) and not ohne
    if feld != ziel:
        return None

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def tipp() -> None:
        if laeuft:
            melden(
                f"Die laufende Uhr zählt als {name}."
                if zaehlt
                else "Die laufende Uhr zählt nicht — sie trägt keine Zeit ein."
            )
            return
        if ohne:
            melden("„Ohne Uhr“ gewählt — es wird keine Zeit eingetragen.")
            return
        state.uhr_zaehlt[key] = not zaehlt
        melden(
            f"Die Uhr zählt jetzt nicht als {name} — gilt für jetzt."
            if zaehlt
            else f"Die Uhr zählt jetzt als {name} — gilt für jetzt."
        )
        state.neu_zeichnen()

    return ft.Container(
        data=ZAEHLT_HIER if zaehlt else ZAEHLT_HIER_NICHT,
        padding=ft.Padding.all(8),
        border_radius=18,
        tooltip=(
            f"Die Uhr zählt als {name} — tippen schaltet für jetzt um"
            if zaehlt
            else f"Die Uhr zählt gerade nicht als {name}"
        ),
        on_click=tipp,
        content=ft.Icon(
            ft.Icons.TIMER_OUTLINED if zaehlt else ft.Icons.TIMER_OFF_OUTLINED,
            size=18,
            color=ft.Colors.PRIMARY if zaehlt else None,
            opacity=1.0 if zaehlt else 0.5,
        ),
    )


def uhr_teile(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan | None,
    item: PlanItem | None,
    timer_oeffnen: Callable[[], object],
    basis: str = "",
) -> UhrTeile:
    """Knöpfe und Zeile der Uhr für eine Übung — ``plan``/``item`` ``None`` ohne Plan.

    ``uebung`` ist die Übung aus dem Katalog (die Planübung liest ``item``);
    ``timer_oeffnen`` führt zum Timer der Übung (Profile, „zählt“, Läufe heute). Der Lauf
    trägt die Ausführung ein, die der Block beim Start zeigt (Variante, Gewicht …).
    """
    e = laufende(state, uebung, item)
    if e is not None and e.timer is not None:
        return UhrTeile(zeile=_laufend(page, state, e, fokus=timer_oeffnen))
    key = schluessel(uebung, item)
    #: „zählt“ — für jetzt, sonst wie die Übung (P79 D2)
    zaehlt = state.uhr_zaehlt.get(key, zeit_zaehlt_fuer(uebung, item))

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def kontext(profil: TimerProfil | None = None) -> UebungKontext:
        wahl = uebung_lauf.gewaehlte_ausfuehrung(state, uebung, item)
        # „Ohne Uhr“: keine Zeit ins Tagebuch (P146)
        eintragen = zaehlt and not (profil is not None and profil.ohne_uhr)
        return uebung_lauf.kontext_fuer(
            uebung, plan, item, zeit_eintragen=eintragen, auspraegung=wahl
        )

    def takt_an_den_lauf(e: Einheitslauf) -> None:
        """Takt für jetzt, Vorgabe der Übung und Tempo an den Timer der Einheit (Taktgeber) —
        und „Takt zählt“ (P138) als Zähl-Teil mit Quelle „takt“
        (`uebung_lauf.takt_zaehlen_anbringen`)."""
        if e.timer is not None:
            takt_anbringen(state, e.timer.lauf, key, takt_der_uebung(uebung, item, plan))
            with contextlib.suppress(Exception):  # der Zähler darf die Uhr nie aufhalten
                uebung_lauf.takt_zaehlen_anbringen(page, state, e, uebung, item)

    def takt_starten(takt: Takt) -> None:
        """„Takt starten“ aus dem Blatt: dieser Takt für jetzt, die gesetzte Uhr läuft los —
        es gibt immer eine Uhr (§4: ohne Timer die Stoppuhr)."""
        state.uhr_takt[key] = takt
        starten(gesetzt(state, uebung, plan, item))()

    takt_wahl = takt_knopf(
        page,
        state,
        key=key,
        takt=takt_der_uebung(uebung, item, plan),
        starten=takt_starten,
        titel=f"Takt · {uebung.name}",
        klein=True,
        uebung=uebung,
        item=item,
    )

    def starten(profil: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            # „Zuletzt gestartet“ nur, wenn es **nicht** die eingestellte Uhr ist: Wer die
            # Einstellung startet, folgt ihr weiter — ändert sich der Timer danach im Editor,
            # in „Übung bearbeiten“ oder über „Zuordnen“, startet ▶ den neuen (N55)
            vorgabe = timer_fuer(uebung, plan, item)
            if vorgabe is not None and vorgabe.id == profil.id:
                state.uhr_wahl.pop(schluessel(uebung, item), None)
            else:
                state.uhr_wahl[schluessel(uebung, item)] = profil.id
            try:
                lauf = uebung_lauf.starten(page, state, kontext(profil), _kopie(profil))
            except RuntimeError as fehler:
                melden(str(fehler))
                return
            takt_an_den_lauf(lauf)
            state.uebung_laeufe[uebung.id] = lauf.id
            zaehlen.meldung_zeigen(page, state)  # ein Zählen einer anderen Übung endete
            state.neu_zeichnen()
            fokus_oeffnen()

        return handler

    def fokus_oeffnen() -> None:
        """Einstellungen → Übungen → „▶ öffnet den Fokus“ (7.11.2026): die Trainingsansicht
        zur laufenden Uhr — der Timer dieser Übung, der bei laufender Uhr das „Während“ zeigt.
        Kein Zwang: aus heißt, die Uhr bleibt in der Übung."""
        if not state.fokus_auto() or not hasattr(page, "run_task"):
            return

        async def gehen() -> None:
            ergebnis = timer_oeffnen()
            if inspect.isawaitable(ergebnis):
                await ergebnis

        page.run_task(gehen)

    def bereitstellen(profil: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            try:
                lauf = uebung_lauf.bereitstellen(page, state, kontext(profil), _kopie(profil))
            except RuntimeError as fehler:
                melden(str(fehler))
                return
            takt_an_den_lauf(lauf)
            state.uebung_laeufe[uebung.id] = lauf.id
            if not zaehlen.meldung_zeigen(page, state):
                melden(f"{uebung.name}: {profil.anzeigename} steht bereit — oben „Alle starten“")
            state.neu_zeichnen()

        return handler

    profil = gesetzt(state, uebung, plan, item)

    def zeit_stellen() -> None:
        """Ein Tipp auf die Zeit: Timer ohne Ablauf stellen und gleich starten (P79 D4) — oder
        „Mit Abschnitten …“ ins erweiterte Fenster (P153, Ben 9.11.2026)."""

        def los(sekunden: int) -> None:
            state.uhr_einmal[key] = einmal_timer(sekunden)
            starten(state.uhr_einmal[key])()

        vorher = 60 if profil.ist_stoppuhr else profil.gesamt_s()
        page.show_dialog(
            zeit_blatt(
                vorher,
                starten=los,
                schnell=state.schnellzeiten(),
                erweitert=fuer_jetzt_oeffnen(page, state, uebung, item, basis, vorher),
            )
        )

    def waehlen(p: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            state.uhr_wahl[key] = p.id  # nur für diese Sitzung
            state.neu_zeichnen()

        return handler

    def blatt_oeffnen() -> None:
        """„Uhr einstellen …“ — das Uhr-Blatt mit Geltung (§4, Skizze F3)."""
        from trainingsapp.ui.components.uhr_blatt import uhr_blatt

        page.show_dialog(uhr_blatt(page, state, uebung=uebung, plan=plan, item=item, basis=basis))

    def menue_eintrag(p: TimerProfil) -> ft.PopupMenuItem:
        titel = "Ohne Uhr — nur Fokus" if p.ohne_uhr else p.anzeigename
        unter = "Kurven, Takt, Eintragen · keine Zeit" if p.ohne_uhr else p.kurztext()
        return ft.PopupMenuItem(
            icon=_symbol(p),
            checked=p.id == profil.id,
            content=ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Text(titel, weight=ft.FontWeight.W_600),
                    ft.Text(unter, size=12, opacity=0.7),
                ],
            ),
            on_click=waehlen(p),
        )

    menue = ft.PopupMenuButton(
        tooltip="Uhr wählen — Stoppuhr, Timer oder ohne Uhr",
        content=ft.Container(
            padding=ft.Padding.only(left=10, right=6, top=6, bottom=6),
            border_radius=20,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            # Der Name kürzt sich mit „…“, der Pfeil bleibt — das Menü füllt den Platz links
            # der Zeit; seit „zählt“ und ⧗ ins Blatt bzw. Menü zogen (P148), passt er
            content=ft.Row(
                spacing=6,
                controls=[
                    ft.Text(
                        "Ohne Uhr" if profil.ohne_uhr else profil.anzeigename,
                        weight=ft.FontWeight.W_600,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=20),
                ],
            ),
        ),
        items=[
            *(menue_eintrag(p) for p in angebot(uebung, plan, item, state.uhr_einmal.get(key))),
            ft.PopupMenuItem(),  # Trennlinie
            ft.PopupMenuItem(
                icon=ft.Icons.TUNE, content=ft.Text("Uhr einstellen …"), on_click=blatt_oeffnen
            ),
            ft.PopupMenuItem(
                icon=ft.Icons.CENTER_FOCUS_STRONG,
                content=ft.Text("Fokus öffnen, ohne zu starten"),
                on_click=timer_oeffnen,
            ),
            ft.PopupMenuItem(
                icon=ft.Icons.HOURGLASS_TOP,
                content=ft.Text("Bereitstellen für „Alle starten“"),
                on_click=bereitstellen(profil),
            ),
        ],
    )
    zeit = (
        "—" if profil.ohne_uhr else "0:00" if profil.ist_stoppuhr else dauer_text(profil.gesamt_s())
    )
    zeile = ft.Container(
        padding=ft.Padding.only(left=6, right=4, top=6, bottom=6),
        border_radius=16,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(content=menue, expand=True, alignment=ft.Alignment.CENTER_LEFT),
                ft.TextButton(
                    content=ft.Text(zeit, size=20, weight=ft.FontWeight.W_500),
                    tooltip="Zeit stellen",
                    style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=4)),
                    on_click=zeit_stellen,
                ),
                takt_wahl,
                ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    tooltip=(
                        "Fokus öffnen — ohne Uhr"
                        if profil.ohne_uhr
                        else f"{profil.anzeigename} starten"
                        + (" — im Fokus" if state.fokus_auto() else "")
                    ),
                    icon_size=28,
                    padding=ft.Padding.all(6),
                    size_constraints=ft.BoxConstraints(min_width=44, min_height=44),
                    style=ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY, color=ft.Colors.ON_PRIMARY),
                    on_click=starten(profil),
                ),
            ],
        ),
    )
    return UhrTeile(zeile=zeile)


def _laufend(
    page: Any, state: Any, e: Einheitslauf, fokus: Callable[[], object] | None = None
) -> ft.Control:
    """Die laufende Uhr der Übung: Zeit, Pause bzw. Weiter, Nächster, Fertig, Abbrechen — sie
    zählt im Takt des Tickers mit (`AppState.timer_beobachter`). Zählt der Sensor mit, steht
    darunter die Zahl mit ±1 (`components.zaehlen.neben_der_uhr`, im Takt der Einheit).
    ``fokus`` öffnet den **Fokus** (7.11.2026): die Trainingsansicht zur laufenden Uhr — ein
    Knopf oben rechts in der Karte, kein Zwang."""
    assert e.timer is not None
    lauf = e.timer.lauf
    teil = e.teil("plan")
    zaehlt = isinstance(teil, UebungBaustein) and teil.kontext.zeitfeld is not None
    zaehl_zeilen = (
        zaehlen.neben_der_uhr(
            page, state, e, teil.kontext.uebung_id, teil.kontext.item_id, name="uhr"
        )
        if isinstance(teil, UebungBaustein)
        else []
    )
    oben = ft.Text(size=14, opacity=0.85, expand=True)
    pause = ft.OutlinedButton(height=48, style=ft.ButtonStyle(shape=ECKEN))
    # Takt · Zeit in einer Zeile wie auf der Timer-Seite und im Fokus (Ben, 9.11.2026): der Takt
    # klein links, antippen → groß; der Tempo-Regler für jetzt
    key = (
        schluessel_fuer(teil.kontext.uebung_id, teil.kontext.item_id)
        if isinstance(teil, UebungBaustein)
        else "uhr"
    )
    uhr = ZeitMitTakt(40, on_takt=lambda: takt_gross(page, state, lauf))
    tempo_regler = TempoRegler(state, key, lauf)
    # Takt für jetzt auch im Lauf — wie auf der Timer-Seite (K2)
    takt_wahl = takt_knopf(
        page,
        state,
        key=key,
        takt=lauf.takt_aktuell(),
        lauf=lauf,
        titel="Takt für jetzt",
        klein=True,
    )
    naechster = ft.IconButton(
        ft.Icons.SKIP_NEXT,
        tooltip="Nächster Abschnitt",
        visible=not lauf.vorwaerts and lauf.stand().abschnitte > 1,
    )

    def beschriften() -> None:
        stand = lauf.stand()
        lage = lauf.takt_lage()
        uhr.nachziehen(lauf.anzeige(), lauf.takt_effektiv() if lage else None, lage)  # mit Tempo
        tempo_regler.nachziehen(lage is not None)
        name = lauf.profil.anzeigename
        if not lauf.vorwaerts and not stand.fertig:
            name = f"{name}: {lauf.abschnittsname(stand.nummer)}"  # „Halten (Runde 1/3)“
        if stand.fertig:
            oben.value = f"{lauf.profil.anzeigename} · fertig"
        else:
            oben.value = f"{name} läuft" if stand.laeuft else f"{name} · angehalten"
        laeuft = stand.laeuft
        pause.content = ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.PAUSE if laeuft else ft.Icons.PLAY_ARROW, size=18),
                ft.Text("Pause" if laeuft else "Weiter"),
            ],
        )

    def auffrischen() -> None:
        beschriften()
        with contextlib.suppress(Exception):
            anzeige.update()

    def anhalten_oder_weiter() -> None:
        einheit_ui.anhalten_oder_weiter(page, state)
        auffrischen()

    def fertig() -> None:
        lauf.fertig_machen()  # die Einheit endet im Takt danach und trägt ein
        auffrischen()

    def abbrechen() -> None:
        lauf.abbrechen()  # ohne Rückfrage (Ben, 18.10.2026) — trägt nichts ein
        auffrischen()

    def weiter_abschnitt() -> None:
        lauf.weiter()
        einheit_ui.melden(state)
        auffrischen()

    pause.on_click = anhalten_oder_weiter
    naechster.on_click = weiter_abschnitt
    beschriften()
    anzeige = ft.Container(
        padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
        border_radius=16,
        border=ft.Border.all(1.5, ft.Colors.PRIMARY),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        content=ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(_symbol(lauf.profil), size=18, opacity=0.85),
                        oben,
                        # Ob die Zeit zählt, steht auch beim Laufen da (P79 D1)
                        ft.Text("zählt" if zaehlt else "zählt nicht", size=12, opacity=0.75),
                        takt_wahl,
                        *(
                            [
                                ft.IconButton(
                                    ft.Icons.OPEN_IN_FULL,
                                    icon_size=20,
                                    tooltip="Fokus — Trainingsansicht zur laufenden Uhr",
                                    on_click=fokus,
                                )
                            ]
                            if fokus is not None
                            else []
                        ),
                    ],
                ),
                uhr.zeile(mitte=False),
                tempo_regler.control,
                *zaehl_zeilen,
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        pause,
                        naechster,
                        ft.FilledButton(
                            content=ft.Row(
                                tight=True,
                                spacing=6,
                                controls=[ft.Icon(ft.Icons.CHECK, size=18), ft.Text("Fertig")],
                            ),
                            height=48,
                            expand=True,
                            style=ft.ButtonStyle(shape=ECKEN),
                            tooltip="Beenden und eintragen",
                            on_click=fertig,
                        ),
                        ft.TextButton(
                            "Abbrechen",
                            tooltip="Beenden ohne Eintrag",
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            on_click=abbrechen,
                        ),
                    ],
                ),
            ],
        ),
    )
    state.timer_beobachter["uhr_in_der_uebung"] = auffrischen
    return anzeige


def schluessel_fuer(uebung_id: str, item_id: str | None) -> str:
    """`schluessel` aus den IDs — für die laufende Uhr, die nur den Kontext kennt."""
    return item_id if item_id is not None else uebung_id


def _symbol(p: TimerProfil) -> ft.IconData:
    if p.ohne_uhr:
        return ft.Icons.MONITOR_HEART_OUTLINED
    return ft.Icons.AV_TIMER if p.ist_stoppuhr else ft.Icons.TIMER_OUTLINED


def _kopie(p: TimerProfil) -> TimerProfil:
    """Eine eigene Kopie für den Lauf — das Profil der Übung bleibt, wie es ist."""
    neu = TimerProfil.aus_dict(p.als_dict())
    assert neu is not None
    return neu


__all__ = [
    "ZAEHLT_HIER",
    "ZAEHLT_HIER_NICHT",
    "UhrTeile",
    "angebot",
    "gesetzt",
    "laufende",
    "schluessel",
    "takt_gross",
    "uhr_teile",
    "zaehlt_symbol",
]
