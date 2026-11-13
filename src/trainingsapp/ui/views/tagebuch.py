"""Der Reiter „Notizen“ im Verlauf (Ben, 18.10.2026 als „Tagebuch“) — alles Geschriebene.

Ben: „der für mich wichtigste Teil fehlt, das Tagebuch. Hier wird geschrieben, diktiert,
reflektiert, Photos gesammelt usw.“ Seit 12.11.2026 (`docs/plan_notizen_reiter.md`): „Der
Oberreiter Tagebuch wird zu ‚Notizen‘. In den Notizen gibt es eine chronologische Abhandlung
von allem, was geschrieben wurde. Mit den Filtern kann man sich da durcharbeiten. Wichtig:
die Tagesnotizen mit Tagebuch müssen gesondert super schnell erreichbar sein.“

- **Kopf:** Suchfeld (Text, Titel — Übung, Plan, Feld —, Tags), Filterknopf
  (`components/filterblatt.py`: Art · Notiz-Tags · Zeitraum · Plan · Übung), das
  Kalendersymbol (Wochenleiste ein/aus) und „+“ (neue Notiz zu heute). Darunter fest die
  **Schnellwahl „Tagebuch · Alles“** — ein Tipp, die Wahl bleibt stehen — und die Labels der
  wirkenden Filter.
- **Eine Liste**, nach Tagen: oben die Woche, ein Punkt je Notiz, der Tag oben in der Liste
  markiert; darunter die Tage, der neueste oben, je Tag ein Zeitstrahl nach der Uhr. Beim
  Scrollen geht die Woche mit (die Höhe jedes Tages meldet ``on_size_change``,
  `core.tagebuch.oben` rechnet); ein Tipp auf einen Tag der Woche springt zu ihm (oder zum
  nächstälteren mit Notiz), ‹ › blättern. Segmente gibt es nicht mehr (bis 12.11.2026
  „Tage · Übungen · Notizen“); wer die Notizen einer Übung sucht, tippt ihren Namen ins
  Suchfeld oder nimmt im Blatt der Wege „Notizen zu …“.
- **Nur selbst Geschriebenes** (Ben, 12.11.2026): Werte der Tagesfelder stehen nicht hier,
  sondern im Verlauf (Tage, Zum Tag). Texte der Felder und die Notiz an einem Wert stehen
  nach der Uhr; antippen öffnet das Blatt des Felds (`components/tagesfeld_blatt.py`).
- Antippen bearbeitet: die Notiz zum Tag und die zum Plan an Ort und Stelle, die einer Übung
  in ihren Leistungen des Tages (Blatt, `views/leistungen.py`).
- **Suche und Filter füllen nur die Liste neu** (`auffrischen`) — das Suchfeld behält den
  Fokus; alles andere (Editor öffnen, Kalender) baut die Ansicht neu.

Gezeigt werden die letzten `SEITE` Tage mit Notizen, „Ältere zeigen“ holt mehr. Geordnet und
gefiltert wird in `core/tagebuch.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.models import DayNote
from trainingsapp.core.tagebuch import (
    AUFNAHME,
    NOTIZ_ZEILEN,
    OHNE_TAG,
    PLAN,
    TAG,
    TAGESFELD,
    UEBUNG,
    WORKOUT,
    ZEITRAEUME,
    Notiz,
    Tagesgruppe,
    filtern,
    nach_tagen,
    naechster_tag_mit,
    oben,
    sammeln,
    woche,
    zahl_je_tag,
    zuletzt,
)
from trainingsapp.core.verlauf import MONATE, WOCHENTAGE, WOCHENTAGE_LANG, wochen_titel
from trainingsapp.ui.components import ziele as zl
from trainingsapp.ui.components.anhang_reihe import anhang_reihe
from trainingsapp.ui.components.filterblatt import Bereich, Filterblatt
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.notizeditor import Notizeditor, Textnotiz
from trainingsapp.ui.components.scroll import SCROLLT
from trainingsapp.ui.components.tagesfeld_blatt import tagesfeld_blatt
from trainingsapp.ui.components.tagesnotiz import Tagesnotiz, tag_etiketten
from trainingsapp.ui.components.wochenleiste import tageszelle
from trainingsapp.ui.components.zeitstrahl import zeitpunkt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang import anhang_route
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.nachtragen import nachtragen_route
from trainingsapp.ui.views.ziele import tagesfeld_ziele, ziele_fuer

#: So viele Tage mit Notizen zeigt das Tagebuch zuerst, „Ältere zeigen“ je so viele mehr
SEITE = 30
#: Abstand zwischen den Tagen in der Liste (px) — die Rechnung der Wochenleiste braucht ihn
ABSTAND = 14
#: Höhe eines Tags, solange er seine wirkliche nicht gemeldet hat (px)
SCHAETZUNG_KOPF, SCHAETZUNG_NOTIZ = 40.0, 76.0
#: So viele Übungen bietet der Bereich „Übung“ des Filters an (die zuletzt beschriebenen) —
#: alle anderen findet die Suche
UEBUNGEN_IM_FILTER = 12
#: Die Bereiche des Filters (`components/filterblatt.Bereich.name`)
ART, TAGS, ZEITRAUM, B_PLAN, B_UEBUNG = "Art", "Notiz-Tags", "Zeitraum", "Plan", "Übung"
#: Art → Text im Filter und Symbol an der Karte: so bleiben Tagesnotiz, Übungsnotiz und
#: Tagesfeld auf einen Blick unterscheidbar
ARTEN: tuple[tuple[str, str], ...] = (
    (TAG, "Zum Tag"),
    (UEBUNG, "Übung"),
    (PLAN, "Plan"),
    (WORKOUT, "Workout"),
    (TAGESFELD, "Tagesfeld"),
    (AUFNAHME, "Anhänge"),
)
#: Die neue Notiz zu heute in der Liste (`AppState.tagebuch_bearbeitet`)
NEU = "neu"
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST


def tag_kopf(tag: date, heute: date) -> str:
    """„Heute · Sonntag, 18. Oktober“ — oder ohne „Heute“, mit Jahr, wenn es nicht dieses ist.

    >>> tag_kopf(date(2026, 10, 18), date(2026, 10, 18))
    'Heute · Sonntag, 18. Oktober'
    >>> tag_kopf(date(2025, 12, 31), date(2026, 10, 18))
    'Mittwoch, 31. Dezember 2025'
    """
    text = f"{WOCHENTAGE_LANG[tag.weekday()]}, {tag.day}. {MONATE[tag.month - 1]}"
    if tag.year != heute.year:
        text += f" {tag.year}"
    if tag == heute:
        return f"Heute · {text}"
    if (heute - tag).days == 1:
        return f"Gestern · {text}"
    return text


def notizen_text(n: int) -> str:
    """Kopf des Filterblatts: wie viele Notizen gerade passen."""
    return "keine Notiz" if n == 0 else "1 Notiz" if n == 1 else f"{n} Notizen"


@dataclass(slots=True)
class _Sicht:
    """Was nach Filter und Suche zu zeigen ist — neu gerechnet bei jeder Änderung."""

    gezeigte: list[Notiz]
    tage: list[Tagesgruppe]
    gezeigt: list[Tagesgruppe]
    zahl: dict[date, int]
    #: Schlüssel je Tag, um hinzuspringen (je Aufbau neu — `views/plan._zum_ziel`)
    schluessel: dict[date, Any]


def _uhr(n: Notiz) -> str:
    return f"{n.zeit.astimezone():%H:%M}" if n.zeit is not None and n.art != TAG else ""


def tagebuch(page: Any, state: AppState) -> ft.Control:
    """Der Reiter: Kopf mit Suche und Filter, Schnellwahl, Wochenleiste, die Einträge."""
    heute = state.heute()
    profil = state.profil.id
    merk = "tagebuch"
    wahl = state.tagebuch_filter
    # Fotos, Videos und Audioaufnahmen (Ben, 19.10.2026; Audio und Anhänge am Tag seit
    # 22.10.2026): je Eintrag mit Anhängen ein Block „Aufnahmen“, ebenso je Tag für die an der
    # Notiz zum Tag — nur Kacheln, nichts läuft im Tagebuch
    aufnahmen = state.anhaenge.alle(profil, mit_geloeschten=False)
    nach_id = {x.anhang.id: x.anhang for x in aufnahmen}
    tagesfelder = {f.id: f for f in state.tagesfelder.alle(profil, mit_geloeschten=True)}
    notiz_tags = state.notiz_tags.alle(profil)
    tag_namen = {t.id: t.name for t in notiz_tags}
    alle = sammeln(
        # mit den Notizen ohne Text (nur Foto/Audio): ihre Tags gehen an die Aufnahme (N90)
        state.tagesnotizen.alle(profil, mit_leeren=True),
        state.sitzungen.session_notizen(profil),
        state.sitzungen.notizen(profil),
        aufnahmen,
        state.tageswerte.zwischen(profil, None, None),
        tagesfelder,
        tag_namen,
        # Workouts, zu denen etwas eingetragen ist (Ben, 10.11.2026) — Tipp: der Workout-Eintrag
        state.einheiten.workout_zeilen(profil) if state.einheiten is not None else (),
    )
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    plan_namen: dict[str, str] = {p.id: p.name for p in state.plaene.alle(profil)}
    fest = next((t for t in notiz_tags if t.fest), None)
    #: gemeldete Höhen je Tag
    hoehen: dict[date, float] = {}
    bau = [0]

    def plan_name(plan_id: str | None) -> str:
        if plan_id is None:
            return "Ohne Plan"
        if plan_id not in plan_namen:
            plan = state.plaene.laden(plan_id, mit_geloeschten=True)
            plan_namen[plan_id] = plan.name if plan is not None else "Plan"
        return plan_namen[plan_id]

    def titel(n: Notiz) -> str:
        if n.art == TAG:
            return "Zum Tag"
        if n.art == AUFNAHME and not n.exercise_id:
            return "Aufnahmen · Zum Tag"
        if n.art in (TAGESFELD, WORKOUT):
            return n.titel
        if n.art == PLAN:
            return f"Plan „{plan_name(n.plan_id)}“" if n.plan_id else "Ohne Plan"
        u = katalog.get(n.exercise_id or "")
        name = u.name if u is not None else "(Übung nicht mehr vorhanden)"
        if n.variante:  # „Liegestütz · lang“ (Ben, 21.10.2026: Varianten getrennt)
            name = f"{name} · {n.variante}"
        return f"Aufnahmen · {name}" if n.art == AUFNAHME else name

    def rechnen() -> _Sicht:
        gezeigte = filtern(alle, wahl, state.tagebuch_suche, heute=heute, titel=titel)
        tage = nach_tagen(gezeigte)
        # Von „Tage“ her (`AppState.tagebuch_sprung`): der Tag muss in der Liste stehen
        if (sprung := state.tagebuch_sprung) is not None:
            davor = sum(1 for g in tage if g.tag >= sprung)
            state.tagebuch_anzahl = max(state.tagebuch_anzahl, davor + 1)
        gezeigt = tage[: max(state.tagebuch_anzahl, SEITE)]
        bau[0] += 1
        return _Sicht(
            gezeigte,
            tage,
            gezeigt,
            zahl_je_tag(gezeigte),
            {
                g.tag: ft.ScrollKey(  # type: ignore[call-arg]
                    f"tb-{g.tag.isoformat()}-{state.route_nummer}-{bau[0]}"
                )
                for g in gezeigt
            },
        )

    sicht = rechnen()
    #: der Tag oben in der Liste — die Wochenleiste zeigt seine Woche
    stand: dict[str, Any] = {"oben": sicht.gezeigt[0].tag if sicht.gezeigt else heute}

    def neu() -> None:
        state.neu_zeichnen()

    # -- Bearbeiten ---------------------------------------------------------------------

    def ziele_von(n: Notiz) -> tuple[zl.Ziel, list[zl.Ziel]]:
        """Tipp-Ziel und weitere Wege einer Tagebuchzeile (Ben, 28.10.2026): Übung und
        Aufnahme → Einträge des Tages, Notiz zum Tag/Plan und Tagesfeld → die Notiz; dazu
        immer der Tag."""
        tag_route = f"/tag/{n.tag.isoformat()}"
        if n.art in (UEBUNG, AUFNAHME) and n.exercise_id:
            haupt = zl.Ziel(zl.EINTRAEGE, bearbeiter(n))
            u = katalog.get(n.exercise_id)
            dazu = notizen_zu(u.name if u is not None else "Übung", uebung=n.exercise_id)
            wege = ziele_fuer(
                page,
                state,
                n.exercise_id,
                tag=n.tag,
                plan_ids=[n.plan_id] if n.plan_id else (),
                hier={zl.EINTRAEGE},
                danach=neu,
            )
            return haupt, [*wege, dazu]
        tag_ziel = zl.Ziel(zl.TAG, _route(tag_route), untertitel=f"{n.tag:%d.%m.%Y}")
        if n.art == WORKOUT:
            zum_plan = [notizen_zu(plan_name(n.plan_id), plan=n.plan_id)] if n.plan_id else []
            return zl.Ziel(zl.AUSWERTUNG, bearbeiter(n)), [tag_ziel, *zum_plan]
        if n.art == AUFNAHME:
            return zl.Ziel(zl.TAG, bearbeiter(n)), []
        if n.art == TAGESFELD and (feld := tagesfelder.get(n.feld_id or "")) is not None:
            weitere = tagesfeld_ziele(page, state, feld, tag=n.tag, hier={zl.EINTRAGEN}, danach=neu)
            return zl.Ziel(zl.EINTRAGEN, bearbeiter(n)), [*weitere, notizen_zu(feld.name)]
        if n.art == PLAN and n.plan_id:
            dazu = notizen_zu(plan_name(n.plan_id), plan=n.plan_id)
            return zl.Ziel(zl.NOTIZ, bearbeiter(n)), [tag_ziel, dazu]
        return zl.Ziel(zl.NOTIZ, bearbeiter(n)), [tag_ziel]

    def notizen_zu(name: str, *, uebung: str | None = None, plan: str | None = None) -> zl.Ziel:
        """Der Weg „Notizen zu ‚Kniebeuge‘“ im Blatt einer Karte: alles, was dazu geschrieben
        ist — statt der früheren Ordnung „nach Übungen“ (Ben, 12.11.2026, P195). Übung und
        Plan über den Filter, ein Tagesfeld über die Suche nach seinem Namen."""

        def handler() -> None:
            wahl.leeren()
            state.tagebuch_suche = ""
            if uebung:
                wahl.uebungen.add(uebung)
            elif plan:
                wahl.plaene.add(plan)
            else:
                state.tagebuch_suche = name
            state.scroll_offsets.pop(merk, None)
            neu()

        return zl.Ziel(zl.NOTIZ, handler, text=f"Notizen zu „{name}“")

    def _route(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def schluessel_von(n: Notiz) -> str | None:
        """Womit `AppState.tagebuch_bearbeitet` diese Notiz meint — Notizen zum Tag und zum
        Plan werden in der Liste bearbeitet (Ben, 2.11.2026, P101/P103: kein Popup)."""
        if n.art == TAG and n.bezug_id:
            return f"tag:{n.bezug_id}"
        if n.art == PLAN and n.bezug_id:
            return f"plan:{n.bezug_id}"
        return None

    def bearbeiten(schluessel: str) -> None:
        """Die Notiz in der Liste öffnen — ihr Editor steht statt der Karte."""
        if state.tagebuch_bearbeitet != schluessel:
            # Der bisher offene Editor hört zuerst auf (gespeichert, ohne Neubau) — seine
            # Nachfrist klappte sonst die eben geöffnete Notiz wieder zu (N98)
            gemerkt = state.tagebuch_editor
            if isinstance(gemerkt, tuple):
                gemerkt[1].ablegen()
            state.tagebuch_bearbeitet = schluessel
            state.tagebuch_editor = None
        neu()

    def geschlossen(wer: str) -> None:
        """Fertig oder Abbrechen im Editor: wieder die Karte — außer es meldet ein Editor
        (``wer``), während schon eine andere Notiz offen ist (N98)."""
        if state.tagebuch_bearbeitet not in (None, wer):
            return
        state.tagebuch_bearbeitet = None
        state.tagebuch_editor = None
        neu()

    def editor(schluessel: str, n: Notiz | None) -> Notizeditor | None:
        """Der Editor zur bearbeiteten Notiz — einmal je Notiz, über den Neubau der Ansicht
        hinweg (`AppState.tagebuch_editor`). ``None``, wenn es sie nicht mehr gibt."""
        gemerkt = state.tagebuch_editor
        if isinstance(gemerkt, tuple) and gemerkt[0] == schluessel:
            # Der Routenaufbau hat die Haken des Schreibenden geleert (N100)
            gemerkt[1].wieder_anmelden()
            return gemerkt[1]

        def danach() -> None:
            geschlossen(schluessel)

        e: Notizeditor | None = None
        art, _, rest = schluessel.partition(":")
        if schluessel == NEU:
            notiz = DayNote(subject_id=profil, date=heute)
            e = Tagesnotiz(page, state, notiz, tags=notiz_tags, danach=danach)
        elif art == "tag":
            geladen = state.tagesnotizen.laden(rest)
            if geladen is not None:
                angebot = [t for t in notiz_tags if t.aktiv or t.id in geladen.tag_ids]
                e = Tagesnotiz(page, state, geladen, tags=angebot, danach=danach)
        elif art == "plan" and n is not None:

            def sichern(text: str, session_id: str = rest) -> None:
                state.sitzungen.notiz_setzen(session_id, text)

            e = Textnotiz(
                page,
                state,
                n.text,
                sichern,
                schluessel=schluessel,
                hinweis="Wie ging das Training? Tippen oder diktieren.",
                danach=danach,
            )
        if e is not None:
            e.fokus = True
            state.tagebuch_editor = (schluessel, e)
        return e

    def bearbeiter(n: Notiz) -> Callable[[], None]:
        """Antippen: die Notiz zum Tag und zum Plan in der Liste, die einer Übung in ihren
        Leistungen des Tages."""

        def handler() -> None:
            if (schluessel := schluessel_von(n)) is not None:
                bearbeiten(schluessel)
            elif n.art == TAGESFELD and (feld := tagesfelder.get(n.feld_id or "")) is not None:
                if feld.deleted_at is None:
                    page.show_dialog(tagesfeld_blatt(page, state, feld, n.tag, danach=neu))
            elif n.art in (UEBUNG, AUFNAHME) and n.exercise_id:
                uebung = state.uebungen.laden(n.exercise_id, mit_geloeschten=True)
                if uebung is not None:
                    # Mit `nachtragen=` wie unter Heute: „Nachtragen“ und „Im Verlauf“ im Blatt
                    basis = "" if n.tag == state.heute() else f"/tag/{n.tag.isoformat()}"
                    page.show_dialog(
                        leistungen_blatt(
                            page,
                            state,
                            uebung,
                            n.tag,
                            nachtragen=nachtragen_route(basis, n.exercise_id, n.plan_id),
                            danach=neu,
                        )
                    )
            elif n.art == WORKOUT and n.bezug_id:
                page.run_task(page.push_route, f"/workout/{n.bezug_id}")
            elif n.art == AUFNAHME:
                # Anhänge am Tag: der Tag, dort stehen sie an der Notiz zum Tag
                page.run_task(page.push_route, f"/tag/{n.tag.isoformat()}")

        return handler

    def anhang_oeffner(anhang) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(anhang_route("/", anhang.id))

        return handler

    def notiz_zum_tag() -> None:
        """„+“ im Kopf: eine neue Notiz zu heute, oben in der Liste."""
        bearbeiten(NEU)

    # -- Kopf ---------------------------------------------------------------------------

    def kalender_umschalten() -> None:
        state.tagebuch_kalender = not state.tagebuch_kalender
        neu()

    def suchen(e: Any) -> None:
        state.tagebuch_suche = str(e.control.value or "")
        auffrischen()

    def schnell(tagebuch_an: bool) -> Callable[[Any], None]:
        """Die Schnellwahl: „Tagebuch“ = Notizen zum Tag mit dem festen Tag, „Alles“ = kein
        Filter. Die Suche bleibt, wie sie ist."""

        def handler(_e: object = None) -> None:
            if tagebuch_an and fest is not None:
                wahl.tagebuch_setzen(fest.id)
            else:
                wahl.leeren()
            filterblatt.nachziehen()
            auffrischen()

        return handler

    def schnell_chip(text: str, tagebuch_an: bool, icon: ft.IconData) -> ft.Chip:
        return ft.Chip(
            label=ft.Text(text, size=13),
            leading=ft.Icon(icon, size=16),
            show_checkmark=False,
            visual_density=ft.VisualDensity.COMPACT,
            on_select=schnell(tagebuch_an),
        )

    chip_tagebuch = schnell_chip("Tagebuch", True, ft.Icons.MENU_BOOK)
    chip_alles = schnell_chip("Alles", False, ft.Icons.NOTES)

    def schnell_zeigen() -> None:
        chip_tagebuch.selected = fest is not None and wahl.ist_tagebuch(fest.id)
        chip_alles.selected = wahl.leer

    uebungen_wahl = list(
        dict.fromkeys(
            [*zuletzt(alle, lambda n: n.exercise_id)[:UEBUNGEN_IM_FILTER], *sorted(wahl.uebungen)]
        )
    )
    filterblatt = Filterblatt(
        page,
        [
            Bereich(
                ART,
                ft.Icons.CATEGORY_OUTLINED,
                ft.Colors.SECONDARY_CONTAINER,
                list(ARTEN),
                wahl.arten,
            ),
            Bereich(
                TAGS,
                ft.Icons.LABEL_OUTLINE,
                ft.Colors.TERTIARY_CONTAINER,
                [*((t.id, t.name) for t in notiz_tags), (OHNE_TAG, "ohne Tag")],
                wahl.tags,
            ),
            Bereich(
                ZEITRAUM,
                ft.Icons.DATE_RANGE,
                ft.Colors.SURFACE_CONTAINER_HIGHEST,
                list(ZEITRAEUME),
                wahl.zeitraum,
                einzel=True,
            ),
            Bereich(
                B_PLAN,
                ft.Icons.LIST_ALT,
                ft.Colors.PRIMARY_CONTAINER,
                [(i, plan_name(i)) for i in zuletzt(alle, lambda n: n.plan_id)],
                wahl.plaene,
            ),
            Bereich(
                B_UEBUNG,
                ft.Icons.FITNESS_CENTER,
                ft.Colors.PRIMARY_CONTAINER,
                [(i, katalog[i].name if i in katalog else "(Übung)") for i in uebungen_wahl],
                wahl.uebungen,
            ),
        ],
        on_change=lambda: auffrischen(),
        # frisch gerechnet: das Blatt fragt, bevor die Liste nachzieht
        zaehlen=lambda: len(filtern(alle, wahl, state.tagebuch_suche, heute=heute, titel=titel)),
        treffer=notizen_text,
    )
    suchfeld = ft.TextField(
        value=state.tagebuch_suche,
        hint_text="Notizen durchsuchen",
        dense=True,
        text_size=14,
        prefix_icon=ft.Icons.SEARCH,
        border=ft.OutlineInputBorder(border_radius=12),
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        on_change=suchen,
    )
    suchzeile = filterblatt.suchzeile(suchfeld)
    suchzeile.controls.extend(
        [
            ft.IconButton(
                ft.Icons.CALENDAR_VIEW_WEEK
                if state.tagebuch_kalender
                else ft.Icons.CALENDAR_VIEW_WEEK_OUTLINED,
                tooltip="Wochenleiste ausblenden"
                if state.tagebuch_kalender
                else "Wochenleiste zeigen",
                selected=state.tagebuch_kalender,
                visual_density=ft.VisualDensity.COMPACT,
                on_click=kalender_umschalten,
            ),
            ft.IconButton(
                ft.Icons.ADD,
                tooltip="Neue Notiz zu heute",
                visual_density=ft.VisualDensity.COMPACT,
                on_click=notiz_zum_tag,
            ),
        ]
    )
    schnell_zeigen()
    kopf = ft.Container(
        padding=ft.Padding.only(left=12, right=4, top=8, bottom=2),
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                suchzeile,
                # Das Tagebuch mit einem Tipp (Ben, 12.11.2026: „super schnell erreichbar“)
                ft.Row(
                    spacing=6,
                    controls=[chip_tagebuch, chip_alles] if fest is not None else [chip_alles],
                ),
            ],
        ),
    )

    # -- Einträge -----------------------------------------------------------------------

    def editor_karte(e: Notizeditor, zu: str, icon: Any) -> ft.Control:
        """Der Editor statt der Karte — mit derselben Kopfzeile."""
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Icon(icon, size=16, opacity=0.7),
                            ft.Text(zu, size=12, weight=ft.FontWeight.W_600, opacity=0.75),
                        ],
                    ),
                    e.control(),
                ],
            ),
        )

    def notiz_karte(n: Notiz, mit_datum: bool = False) -> ft.Control:
        """Eine Notiz: oben wozu (Tag, Plan, Übung), darunter der Text — antippen bearbeitet,
        Notizen zum Tag und zum Plan gleich hier (Ben, 2.11.2026). Eine Notiz zum Tag zeigt
        höchstens `NOTIZ_ZEILEN` Zeilen (P100) und ihre Tags."""
        zu = titel(n)
        schluessel = schluessel_von(n)
        if schluessel is not None and state.tagebuch_bearbeitet == schluessel:
            e = editor(schluessel, n)
            if e is not None:
                return editor_karte(
                    e,
                    zu if not mit_datum else f"{zu} · {n.tag:%d.%m.}",
                    ft.Icons.WB_SUNNY_OUTLINED if n.art == TAG else ft.Icons.LIST_ALT,
                )
        if mit_datum:
            zu = f"{WOCHENTAGE[n.tag.weekday()]} {n.tag:%d.%m.}" + (
                f" · {_uhr(n)}" if _uhr(n) else ""
            )
        etiketten: list[ft.Control] = []
        if n.art == UEBUNG and n.plan_id and not mit_datum:
            etiketten.append(ft.Text(plan_name(n.plan_id), size=11, opacity=0.6))
        if n.art == TAG and n.tags:
            etiketten.extend(tag_etiketten(n.tags))
        symbol_name = (
            katalog[n.exercise_id].icon_key
            if n.art in (UEBUNG, AUFNAHME) and n.exercise_id in katalog
            else None
        )
        icon = {
            TAG: ft.Icons.WB_SUNNY_OUTLINED,
            PLAN: ft.Icons.LIST_ALT,
            AUFNAHME: ft.Icons.ATTACH_FILE,
            TAGESFELD: ft.Icons.LABEL_OUTLINE,
            WORKOUT: ft.Icons.PLAYLIST_PLAY,
        }.get(n.art) or symbol(symbol_name)
        inhalt: ft.Control = (
            ft.Text(n.text, size=14, max_lines=NOTIZ_ZEILEN, overflow=ft.TextOverflow.ELLIPSIS)
            if n.art == TAG
            else ft.Text(n.text, size=14, selectable=False)
        )
        if n.art == WORKOUT and n.werte:
            # Die Skalen des Workouts unter seiner Notiz
            zeile = ft.Container(
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                content=ft.Text(n.werte, size=12),
            )
            inhalt = ft.Column(
                spacing=4,
                tight=True,
                controls=[*([inhalt] if n.text else []), zeile],
            )
        if n.art == AUFNAHME:
            reihe = anhang_reihe(
                [nach_id[i] for i in n.anhang_ids if i in nach_id],
                state.anhaenge.bild,
                anhang_oeffner,
            )
            inhalt = reihe if reihe is not None else inhalt
            if not mit_datum:
                etiketten.append(ft.Text(n.text, size=11, opacity=0.6))
        haupt, weitere = ziele_von(n)
        blatt = zl.blatt_oeffner(page, titel(n), f"{n.tag:%d.%m.%Y}", weitere, hauptziel=haupt)
        etiketten.append(zl.zielsymbol(haupt, on_click=blatt, groesse=18))
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
            ink=True,
            on_click=bearbeiter(n),
            on_long_press=blatt,
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            *([] if mit_datum else [ft.Icon(icon, size=16, opacity=0.7)]),
                            ft.Text(
                                zu,
                                size=12,
                                weight=ft.FontWeight.W_600,
                                opacity=0.75,
                                expand=True,
                            ),
                            *etiketten,
                        ],
                    ),
                    inhalt,
                ],
            ),
        )

    def tages_block(g: Tagesgruppe) -> ft.Control:
        def gemessen(e: ft.LayoutSizeChangeEvent, tag: date = g.tag) -> None:
            hoehen[tag] = float(e.height or 0)

        return ft.Container(
            key=sicht.schluessel[g.tag],
            on_size_change=gemessen,
            size_change_interval=100,
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=4, top=4),
                        content=ft.Text(
                            tag_kopf(g.tag, heute), size=15, weight=ft.FontWeight.W_700
                        ),
                    ),
                    ft.Column(
                        spacing=0,
                        controls=[zeitpunkt(_uhr(n), notiz_karte(n)) for n in g.notizen],
                    ),
                ],
            ),
        )

    def aeltere_zeigen() -> None:
        state.tagebuch_anzahl = len(sicht.gezeigt) + SEITE
        neu()

    def leer() -> list[ft.Control]:
        return [
            ft.Container(
                padding=ft.Padding.only(left=4, top=8, right=4),
                content=ft.Text(
                    "Keine Notizen"
                    + (
                        " zu Suche und Filter."
                        if not wahl.leer or state.tagebuch_suche.strip()
                        else ". Sie entstehen beim Üben (Knopf „Notiz“), auf „Heute“ "
                        "(„Notiz zum Tag“, zum Plan) — oder hier oben rechts."
                    ),
                    size=13,
                    opacity=0.7,
                ),
            ),
            ft.Row(
                controls=[
                    ft.FilledTonalButton("Notiz zum Tag", icon=ft.Icons.ADD, on_click=notiz_zum_tag)
                ]
            ),
        ]

    def eintraege_bauen() -> list[ft.Control]:
        eintraege: list[ft.Control] = []
        if state.tagebuch_bearbeitet == NEU and (neuer := editor(NEU, None)) is not None:
            # Die neue Notiz zu heute oben in der Liste (Ben, 2.11.2026)
            eintraege.append(
                editor_karte(neuer, f"Neue Notiz · {tag_kopf(heute, heute)}", ft.Icons.ADD)
            )
        if not sicht.gezeigte:
            eintraege.extend(leer())
            return eintraege
        eintraege.extend(tages_block(g) for g in sicht.gezeigt)
        if len(sicht.tage) > len(sicht.gezeigt):
            eintraege.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.TextButton(
                            f"Ältere zeigen ({len(sicht.tage) - len(sicht.gezeigt)} Tage)",
                            icon=ft.Icons.EXPAND_MORE,
                            on_click=aeltere_zeigen,
                        )
                    ],
                )
            )
        return eintraege

    spalte = ft.Column(spacing=ABSTAND, controls=eintraege_bauen())
    liste = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ABSTAND,
        scroll_interval=120,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=6, bottom=24),
                content=spalte,
            )
        ],
    )

    # -- Wochenleiste ---------------------------------------------------------------------

    def mit_leiste() -> bool:
        return state.tagebuch_kalender and bool(sicht.gezeigt)

    leiste = ft.Container(visible=mit_leiste())

    async def springen(tag: date) -> None:
        """Zum Tag (oder dem nächstälteren mit Notiz) in der Liste."""
        ziel = naechster_tag_mit(sicht.schluessel, tag)
        if ziel is None:
            return
        stand["oben"] = ziel
        leiste_bauen()
        with contextlib.suppress(Exception):
            leiste.update()
            await liste.scroll_to(scroll_key=sicht.schluessel[ziel], duration=250)

    def tipp(tag: date) -> Callable[[], Any]:
        async def handler() -> None:
            await springen(tag)

        return handler

    def blaettern_ziel(schritt: int) -> date | None:
        """‹ ›: der nächste Tag mit Notiz in einer älteren bzw. jüngeren Woche."""
        diese = woche(stand["oben"])
        tage_mit = sorted(sicht.schluessel)
        if schritt < 0:
            return next((t for t in reversed(tage_mit) if t < diese[0]), None)
        return next((t for t in tage_mit if t > diese[-1]), None)

    def blaettern(schritt: int) -> Callable[[], Any]:
        async def handler() -> None:
            if (ziel := blaettern_ziel(schritt)) is not None:
                await springen(ziel)

        return handler

    def zelle(t: date) -> ft.Control:
        n = sicht.zahl.get(t, 0)
        return tageszelle(
            t,
            heute=heute,
            gewaehlt=t == stand["oben"],
            anzahl=n,
            punkte=1 if n else 0,
            on_click=tipp(t),
            tooltip=f"{n} Notizen" if n > 1 else "1 Notiz" if n else None,
            hoehe=56,
        )

    def leiste_bauen() -> None:
        tage_der_woche = woche(stand["oben"])
        leiste.content = ft.Container(
            margin=ft.Margin.only(left=12, right=12, bottom=4),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=18,
            padding=ft.Padding.only(left=4, right=4, top=2, bottom=6),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                ft.Icons.CHEVRON_LEFT,
                                tooltip="Vorige Woche mit Notizen",
                                on_click=blaettern(-1),
                                disabled=blaettern_ziel(-1) is None,
                            ),
                            ft.Text(
                                wochen_titel(tage_der_woche[0]),
                                size=14,
                                weight=ft.FontWeight.W_700,
                            ),
                            ft.IconButton(
                                ft.Icons.CHEVRON_RIGHT,
                                tooltip="Nächste Woche mit Notizen",
                                on_click=blaettern(1),
                                disabled=blaettern_ziel(1) is None,
                            ),
                        ],
                    ),
                    ft.Row(spacing=4, controls=[zelle(t) for t in tage_der_woche]),
                ],
            ),
        )

    def gescrollt(e: ft.OnScrollEvent) -> None:
        """Die Woche geht mit: Welcher Tag steht oben? (Gemeldete Höhen, sonst geschätzt.)"""
        ohne_auto_update()  # V1: sonst vergleicht Flet je Scroll-Ereignis die ganze Seite
        state.scroll_offsets[merk] = e.pixels
        # Wer gerade schreibt, will wissen, dass der Finger daneben scrollt statt tippt —
        # wie `components/scroll.scroll_merken` (N99: „Scrollen daneben nicht“, P103)
        if state.schreib_gesten is not None and getattr(e, "event_type", None) in SCROLLT:
            state.schreib_gesten("scroll")
        if not mit_leiste():
            return
        reihe = [
            hoehen.get(g.tag, SCHAETZUNG_KOPF + SCHAETZUNG_NOTIZ * len(g.notizen))
            for g in sicht.gezeigt
        ]
        neu_oben = sicht.gezeigt[oben(reihe, ABSTAND, float(e.pixels or 0))].tag
        if neu_oben != stand["oben"]:
            stand["oben"] = neu_oben
            leiste_bauen()
            with contextlib.suppress(Exception):
                leiste.update()

    def auffrischen() -> None:
        """Suche oder Filter geändert: nur Liste, Wochenleiste und Schnellwahl — das Suchfeld
        bleibt, wie es ist (Fokus), die Liste beginnt wieder oben."""
        nonlocal sicht
        sicht = rechnen()
        hoehen.clear()
        state.scroll_offsets.pop(merk, None)
        stand["oben"] = sicht.gezeigt[0].tag if sicht.gezeigt else heute
        spalte.controls = eintraege_bauen()
        leiste.visible = mit_leiste()
        if leiste.visible:
            leiste_bauen()
        schnell_zeigen()
        with contextlib.suppress(Exception):
            aussen.update()

    liste.on_scroll = gescrollt
    if mit_leiste():
        leiste_bauen()
    sprung, state.tagebuch_sprung = state.tagebuch_sprung, None
    ziel_tag = naechster_tag_mit(sicht.schluessel, sprung) if sprung is not None else None
    if ziel_tag is not None and hasattr(page, "run_task"):
        # Von „Tage“ her: zu diesem Tag (oder dem nächstälteren mit Notiz)
        stand["oben"] = ziel_tag
        if mit_leiste():
            leiste_bauen()

        async def hinspringen() -> None:
            await asyncio.sleep(0.05)
            with contextlib.suppress(Exception):
                await liste.scroll_to(scroll_key=sicht.schluessel[ziel_tag], duration=0)

        page.run_task(hinspringen)
    # Zurück an die gemerkte Stelle (wie `components/scroll.scroll_merken`)
    elif (versatz := state.scroll_offsets.get(merk)) and hasattr(page, "run_task"):

        async def zurueckspringen() -> None:
            await asyncio.sleep(0.05)
            with contextlib.suppress(Exception):
                await liste.scroll_to(offset=versatz, duration=0)

        page.run_task(zurueckspringen)
    aussen = ft.Column(expand=True, spacing=0, controls=[kopf, filterblatt.labels, leiste, liste])
    return aussen


__all__ = ["ARTEN", "NEU", "SEITE", "notizen_text", "tag_kopf", "tagebuch"]
