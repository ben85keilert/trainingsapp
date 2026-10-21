"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein Block mit beschrifteten Knöpfen; die Zeile selbst reagiert
nicht auf Tippen, das war auf dem Handy zu unsicher. Von oben nach unten
(Ben, 14.10.2026: „Betone das Geleistete oben mehr … trenne die geleistete
Anzeige und die Eingabemöglichkeiten besser ab“):

- **Heute geleistet** — eine eigene Fläche, je Parameter groß der Wert
  (gebündelt wie in der Tagesansicht, je Ausprägung eine Gruppe), darunter die
  Notizen. Antippen (oder „Bearbeiten“) zeigt **alle** Einträge der Übung von
  heute in einem Blatt von unten: Werte und Notizen auf einmal korrigieren, einzeln
  löschen (`views/leistungen.py`, Ben 17.10.2026; Blatt statt Seite 18.10.).
- die Knöpfe „Gemacht“ (abhaken) und, wenn ein Ziel gesetzt ist, „Wie geplant“.
  Ohne Parameter bleibt es dabei — nur abhaken.
- Einstellungen und Werte sehen verschieden aus (Ben, 21.10.2026, Skizze C1 in
  `docs/plan_varianten.md`): oben eine getönte Zone **Ausführung** mit Segmenten (gewählt =
  Häkchen, ein Zustand), darunter **Eintragen** mit gefüllten „+“-Knöpfen (jeder Tipp schreibt).
- **Ausführung**: zuerst die **Variante** der Übung (kurz/lang; Segmente, bei vielen nur
  Symbole oder zwei Spalten, `components/varianten.py`), dann Ausprägungen (Winkel, Gewicht,
  Seite) — man wählt sie vorher, sie wandern in jeden Eintrag und trennen ihn (45° ≠ 90°,
  siehe `core/parameter.py`). Je Ausführung ist ein Eintrag offen (`core.eintraege`).
- **Eintragen** — je Parameter ein umrandeter Abschnitt mit Überschrift, was
  die **Parameter der Planübung** anbieten (`PlanItem.felder`, eingestellt
  unter „Einstellen“; Migration 010):

  - Mengen: „+“-Knöpfe (``+10 +15 +20`` hängen einen Satz an) und Zahlenfelder mit
    Zahlentastatur — „Sätze × Wert“ statt der Notation ``3x15``, die auf einer
    Zahlentastatur nicht zu tippen ist. Zeiten nehmen auch ``1:30``.
  - Skala: Regler und Zahlenfeld in einer Zeile, der Name darüber; der Regler
    schreibt ins Feld, abgeschickt wird mit dem Haken. Der Wert landet im
    heutigen Eintrag der Übung (`SitzungRepo.wert_setzen`), nicht in einem eigenen.
  - Ja/Nein und Freitext, wenn man sie hergeholt hat — ebenso in den heutigen
    Eintrag; der Freitext einmal je Tag: Er ersetzt den, der heute schon dasteht
    (`SessionRepo.text_setzen`), statt nach einem neuen Satz einen zweiten anzulegen.

  Wie die Abschnitte stehen, bestimmt die Darstellung (`ui.state.PLAN_DARSTELLUNGEN`,
  umschaltbar oben im Plan): alle untereinander, einer zum Umschalten,
  oder aufgeklappt nur in einer Übung.
- „Notiz“ — ein Satz ins Erfahrungstagebuch: eine Notiz je Übung und Tag, die der
  Knopf immer wieder öffnet (`SessionRepo.notiz_eintrag`) — auch nach einem neuen
  Satz oder „Gemacht“. Daneben das **Etikett-Symbol** ohne Text (Ben, 21.10.2026): die
  Variante des markierten Eintrags setzen oder eine neue anlegen (`varianten_blatt`).
- Das **i-Symbol** holt Parameter heran (`plan_info.py`): jedes Feld der Übung
  und des Feldvorrats, gespeichert in der Planübung — die Übung bleibt, wie sie
  ist (`core.standards.plan_spec`). Dort auch Beschreibung und Videos.

Das frühere „Mehr …“ (volles Formular) ist darin aufgegangen (Ben, 14.10.2026):
Notiz → „Notiz“, Ja/Nein und Freitext → herholen, Korrigieren → Tafel.

Bearbeiten (Stift in der Leiste): einstellen, entfernen, hinzufügen,
umbenennen, löschen — und umordnen: am Griff ziehen oder mit den Pfeilen um
eine Stelle. Eine Übung darf mehrmals im Plan stehen (Rumpfbeuge am Anfang und
am Ende); die k-te Stelle ist erledigt, wenn die Übung heute k-mal dran war
(`core.plaene.erledigte`), und ihr erster Eintrag hängt nicht an den der
früheren Stelle an. Der Modus liegt im `AppState`, weil die Ansicht beim
Routenwechsel neu gebaut wird.

Ein Eintrag (Gemacht, Chip, Zahlenfeld) baut dagegen nur die Blöcke in der
bestehenden Liste neu (`auffrischen`) — so bleibt die Scrollposition, und man
verliert in einem langen Plan nicht die Orientierung. Kommt man aus einem
Formular zurück, stellt `scroll_merken` die Position wieder her. Kommt man über
„Weiter“ von „Heute“, beginnt die Liste bei der nächsten offenen Übung
(`AppState.plan_ziel`, Ben 18.10.2026).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from functools import partial
from typing import Any

import flet as ft

from trainingsapp.core import eintraege as offene
from trainingsapp.core import varianten as var
from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    SessionEntry,
    jetzt,
)
from trainingsapp.core.parameter import BEIWERK, kontextfelder, leistungsfelder, rolle
from trainingsapp.core.plaene import (
    WOCHENTAGE_KURZ,
    anzahl_je_uebung,
    auspraegung_vorgabe,
    einzel_plan,
    erledigte,
    letzter_heute,
    spaetere_stelle_offen,
    stand_im_plan,
    tage_text,
    verschoben,
    vorkommen,
    ziel_ohne_kontext,
)
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    basis_label,
    einzelwert_lesen,
    format_wert,
    ist_leer,
)
from trainingsapp.core.standards import aktive_felder, chips_fuer, mit_plan_spec, varianten_an
from trainingsapp.core.tagesbilanz import buendeln, je_variante, mengen
from trainingsapp.core.timer_eintrag import vom_timer_text
from trainingsapp.core.uebung_timer import timer_fuer, uhr_an
from trainingsapp.core.units import MAX_SAETZE, parse_anzahl
from trainingsapp.ui import marken
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.skala_regler import skala_regler
from trainingsapp.ui.components.uhr import UhrTeile, laufende, uhr_teile
from trainingsapp.ui.components.varianten import Variantenwahl, varianten_blatt, zeilenbreite
from trainingsapp.ui.components.werte import wert_leiste
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AUFKLAPPEN, PLAN_DARSTELLUNGEN, UMSCHALTEN, AppState
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.plan_ablauf import plan_timer_karte
from trainingsapp.ui.views.timer import timer_knopf
from trainingsapp.ui.views.uebung_timer import uebung_timer_route

ECKEN = ft.RoundedRectangleBorder(radius=12)
#: Das Segment „…“ einer Ausprägung: einen eigenen Wert eingeben (52°)
_EIGEN = "…eigen"


@dataclass
class Nachtrag:
    """Nachtragen als Trainingsblock (Ben, 21.10.2026, P72, Skizze G1; `views/nachtragen.py`):
    derselbe Block wie beim Üben, für ``tag``. Neue Einträge beginnen um ``zeit`` und sammeln
    sich dort; ``None`` = jetzt, wie beim Training. Ohne HRV-Marken und ohne Uhr — die Übung
    ist vorbei. Oben steht ``kopf`` (Wann, Plan).

    ``schliessen`` setzt `plan_view`: Es beendet, was der Nachtrag offen hat („Fertig“,
    Zurück, eine andere Zeit oder ein anderer Plan im Kopf)."""

    tag: date
    zeit: datetime | None
    route: str
    titel: str
    kopf: list[ft.Control] = field(default_factory=list)
    #: Beim Verlassen („Fertig“, Zurück) — setzt `nachtragen_view`
    verlassen: Callable[[], None] = lambda: None
    #: Was um ``zeit`` offen ist, schließen; den Block neu zeigen — setzt `plan_view`
    schliessen: Callable[[], None] = lambda: None
    auffrischen: Callable[[], None] = lambda: None

    def zeit_setzen(self, zeit: datetime | None) -> None:
        """Eine andere Zeit im Kopf: Was um die alte offen ist, ist fertig; die nächsten Tipps
        sammeln sich um die neue."""
        if zeit == self.zeit:
            return
        self.schliessen()
        self.zeit = zeit
        self.auffrischen()

    def hinweis(self) -> str:
        """Der Satz unter dem Block."""
        if self.zeit is None:
            return "Alles hier bekommt die Uhrzeit des Tippens — wie beim Training."
        return (
            f"Alles hier bekommt {self.zeit.astimezone():%H:%M} und sammelt sich im Nachtrag. "
            "„Fertig“ schließt ihn ab."
        )


#: Was ein Tipp auf „Heute geleistet“ öffnet (`views/leistungen.py`)
LEISTUNGEN_TIPP = "Alle Einträge von heute ansehen, korrigieren oder löschen"
#: Ein Tipp auf einen geschlossenen Eintrag (`eintrag_blatt`)
EINTRAG_TIPP = "Wieder öffnen, bearbeiten oder löschen"
#: Ein Tipp auf einen offenen Eintrag mit anderer Ausführung: sie wählen
WAEHLEN_TIPP = "Diese Ausführung wählen — die nächsten Tipps gehen hierhin"
#: Das „i“ im Kopf von „Heute geleistet“ (Ben, 19.10.2026: die Erklärung nicht im Block)
OFFEN_ERKLAERUNG = (
    "Ein Tipp (Satz, Skala, Notiz) geht in den **markierten** Eintrag. Ist keiner markiert, "
    "beginnt er einen neuen.\n\n"
    "**Offen** ist ein Eintrag ohne Ende — solange seit dem letzten Satz nicht mehr als die "
    "eingestellte Zeit vergangen ist (Einstellungen → Übungen → „Eintrag bleibt offen“). Je "
    "**Ausführung** (Variante, Gewicht, Seite, Winkel) kann einer offen sein: kurz +30, "
    "lang +15, kurz +30 sind zwei Einträge, kurz 60 und lang 15.\n\n"
    "**Markiert** ist der offene Eintrag, dessen Ausführung zur gewählten passt. Eine andere "
    "Wahl nimmt die Markierung weg: Der nächste Wert beginnt einen neuen Eintrag, der alte "
    "bleibt offen. Zurück zur alten Wahl — oder ein Tipp auf den offenen Eintrag — und es geht "
    "dort weiter.\n\n"
    "**Abschließen** fixiert den markierten Eintrag. Ohne markierten heißt der Knopf "
    "**Gemacht** und legt einen fertigen Eintrag an. Ein Tipp auf einen geschlossenen Eintrag "
    "bietet „Wieder öffnen“.\n\n"
    "Das **Etikett** neben „Notiz“ setzt die Variante des markierten Eintrags — oder legt eine "
    "neue an, die in der Übung bleibt.\n\n"
    "Läuft eine HRV-Aufnahme, bekommt jeder Satz dort eine Marke — zur Tippzeit, also "
    "„geleistet bis hierher“."
)


def ziel_text(uebung: Exercise, target: dict[str, Any]) -> str:
    """„3x15“ oder „7:00s“ — das Ziel in der Notation der Übung."""
    return uebung.result_spec.format_shorthand(target) if target else ""


def hauptfeld(uebung: Exercise) -> FieldSpec | None:
    """Die Größe, die man am ehesten schnell eintippt: die erste Kennzahl, sonst das erste Feld."""
    spec = uebung.result_spec
    for key in spec.chart_metrics:
        if (f := spec.field_by_key(key)) is not None:
            return f
    return spec.fields[0] if spec.fields else None


def chip_text(feld: FieldSpec, wert: Any) -> str:
    """Satzfelder zeigen den rohen Wert („+15"), andere ihre Schreibweise („45°")."""
    return str(wert) if feld.type == FieldType.SET_LIST else format_wert(feld, wert)


def _kleines_feld(feld: FieldSpec) -> ft.TextField:
    """Schmales Feld für einen eigenen Wert neben den Chips."""
    return ft.TextField(
        width=86,
        height=40,
        dense=True,
        hint_text="Wert",
        suffix=ft.Text(feld.unit) if feld.unit in ("°", "kg", "m") else None,
        keyboard_type=ft.KeyboardType.NUMBER,
        border=ft.OutlineInputBorder(border_radius=10),
    )


def _zahlfeld(
    breite: int, label: str = "", hinweis: str = "", zeit: bool = False, wert: str = ""
) -> ft.TextField:
    """Ein Feld nur für Zahlen — mit Zahlentastatur (Ben, 14.10.2026).

    Zeiten bekommen die Tastatur für Uhrzeiten: Ziffern und „:“ — so geht
    ``90`` wie ``1:30``. Die Einheit steht als Beschriftung im Feld; ein
    Suffix zeigt Flutter erst beim Tippen, das leere Feld sagte nichts.
    """
    return ft.TextField(
        width=breite,
        height=48,
        dense=True,
        value=wert,
        label=label or None,
        # klein und mit wenig Rand — sonst bricht „Sätze“ im schmalen Feld um
        label_style=ft.TextStyle(size=12),
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=12),
        hint_text=hinweis or None,
        keyboard_type=ft.KeyboardType.DATETIME if zeit else ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.CENTER,
        border=ft.OutlineInputBorder(border_radius=12),
    )


def _zeigen(control: ft.Control) -> None:
    """Ein Control neu zeichnen — außerhalb einer laufenden App (Tests) ohne Fehler."""
    with contextlib.suppress(RuntimeError):
        control.update()


def _knopf(
    text: str, icon: ft.IconData, on_click: Callable[[], object], betont: bool = False
) -> ft.Control:
    klasse = ft.FilledButton if betont else ft.FilledTonalButton
    return klasse(
        content=ft.Row(tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text)]),
        height=48,
        style=ft.ButtonStyle(shape=ECKEN, padding=ft.Padding.symmetric(horizontal=14)),
        on_click=on_click,
    )


def _umrandet(text: str, icon: ft.IconData, on_click: Callable[[], object]) -> ft.Control:
    """„Abschließen“/„Gemacht“ umrandet (Skizze C1): gefüllt sind nur Knöpfe, die Werte
    schreiben."""
    return ft.OutlinedButton(
        content=ft.Row(tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text)]),
        height=48,
        style=ft.ButtonStyle(
            shape=ECKEN,
            side=ft.BorderSide(1, ft.Colors.PRIMARY),
            padding=ft.Padding.symmetric(horizontal=14),
        ),
        on_click=on_click,
    )


def _vom_timer(state: AppState, eintraege: list[SessionEntry]) -> set[str]:
    """Welche Einträge ein Timer schrieb (Übungs-Timer, Plan-Ablauf) — aus der Zeitleiste,
    einmal für den ganzen Tag statt je Block."""
    if state.einheiten is None or not eintraege:
        return set()
    return state.einheiten.eintraege_vom_timer([e.id for e in eintraege])


def _zum_ziel(page: Any, state: AppState, route: str, liste: ft.ListView, index: int) -> None:
    """Die Liste beginnt bei ``liste.controls[index]`` statt oben (Ben, 18.10.2026: „Weiter“
    setzt die Ansicht zur nächsten Übung, „nicht ganz nach oben in den Plan“).

    Flutter rollt per ``ScrollKey`` dorthin (`Scrollable.ensureVisible`: Block oben im Bild).
    Das geht nur, wenn die Liste alle Blöcke baut, nicht erst beim Hinscrollen. Der Schlüssel
    ist je Aufbau neu: Gleiche Schlüssel an ersetzten Blöcken friert Flet 1.0 ein
    (`auffrischen`, cb06ee9).
    """
    state.scroll_offsets.pop(route, None)  # die gemerkte Stelle gilt diesmal nicht
    liste.build_controls_on_demand = False
    schluessel: Any = ft.ScrollKey(f"plan-ziel-{state.route_nummer}-{index}")  # type: ignore[call-arg]
    liste.controls[index].key = schluessel

    async def rollen() -> None:
        await asyncio.sleep(0.1)  # erst nach dem Aufbau hängt der Block in Flutter
        with contextlib.suppress(Exception):  # Ansicht schon wieder ersetzt
            await liste.scroll_to(scroll_key=schluessel, duration=0)

    if hasattr(page, "run_task"):
        page.run_task(rollen)


def plan_view(
    page: ft.Page,
    state: AppState,
    plan: Plan,
    bearbeiten: bool = False,
    basis: str | None = None,
    fertig: str = "/",
    einzel: bool = False,
    nachtrag: Nachtrag | None = None,
) -> ft.View:
    """Üben (`/plan/<id>`) oder Bearbeiten — oder eine einzelne Übung üben.

    Bearbeitet wird unter ``basis`` — `/plaene/<id>` aus der Planverwaltung,
    `/plan/<id>/bearbeiten` aus der Übungsansicht heraus. ``fertig`` ist das
    Ziel des Hakens oben rechts. Mit ``einzel`` ist ``plan`` ein
    `einzel_plan()`: Route `/training/<übung>`, Einträge ohne Plan. Mit ``nachtrag``
    (`views/nachtragen.py`) ist ``plan`` die eine Planübung — oder ein `einzel_plan` —
    für einen Nachtrag (`Nachtrag`).
    """
    if nachtrag is not None:
        route = nachtrag.route
    elif einzel:
        route = f"/training/{plan.items[0].exercise_id}"
    elif bearbeiten:
        route = basis or f"/plaene/{plan.id}"
    else:
        route = f"/plan/{plan.id}"
    #: In welcher Session die Einträge landen — ``None`` = die planlose des Tages
    sitzungsplan = None if einzel else plan.id
    #: die fertige Ansicht — „Fertig“ fragt, was unter ihr liegt
    ansicht_halter: list[ft.View] = []

    def heute() -> date:
        """Der Tag beim Tippen, nicht beim Aufbau: Über Mitternacht offen gelassen (die
        Engine bleibt im Cache), landete ein Satz sonst im gestrigen Eintrag (D3). Beim
        Nachtragen der gewählte Tag."""
        return nachtrag.tag if nachtrag is not None else state.heute()

    def zur_zeit() -> contextlib.AbstractContextManager[None]:
        """Beim Nachtragen schreibt und fragt alles wie zur gewählten Zeit
        (`SessionRepo.zur_zeit`) — sonst jetzt."""
        return state.sitzungen.zur_zeit(nachtrag.zeit if nachtrag is not None else None)

    def stand_paare() -> list[tuple[SessionEntry, Any]]:
        """Die Einträge, die offen sein können: beim Nachtragen nur die mit dem gewählten
        Anfang — ein Nachtrag hängt sich nie an einen Eintrag von jetzt."""
        if nachtrag is None or nachtrag.zeit is None:
            return tages_paare
        return [(e, s) for e, s in tages_paare if e.started_at == nachtrag.zeit]

    #: Blöcke, die heute einen eigenen Eintrag angelegt haben (spätere Stelle einer
    #: Übung): Weitere Sätze gehen dorthin, nicht in noch einen Eintrag (D7)
    eigene: set[str] = set()
    #: Unter welchen Mengen „…“ den eigenen Wert aufgeklappt hat — (Planübung, Feld)
    frei_offen: set[tuple[str, str]] = set()
    #: Die Einträge des Tages mit ihrer Session — einmal gelesen; alles Weitere (Anzahl je
    #: Übung, offener Eintrag, Ziel eines Tipps, „vom Timer“) leitet sich daraus ab (N24)
    tages_paare = state.sitzungen.eintraege_am_tag(state.profil.id, heute())
    tages_eintraege = [e for e, _ in tages_paare]
    anzahl = anzahl_je_uebung(tages_eintraege)
    vom_timer = _vom_timer(state, tages_eintraege)
    #: Der letzte Eintrag je Übung, sobald einmal gefragt (`auspraegung_vorgabe`)
    letzte: dict[str, SessionEntry | None] = {}
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    #: Die wievielte Stelle ihrer Übung jede Planübung ist — und was heute erledigt ist
    stelle = vorkommen(plan.items)
    fertig_ids = erledigte(plan.items, anzahl)
    gemacht = len(fertig_ids)
    mehrfach = {i.exercise_id for i in plan.items if stelle[i.id] > 1}
    darstellung = state.plan_darstellung()
    # Aufklappen: Ist keine Übung dieses Plans offen, die erste, die heute noch fehlt (der
    # Nachtrag hat nur einen Block und lässt die Wahl des Plans in Ruhe)
    if nachtrag is None and state.plan_offen not in {item.id for item in plan.items}:
        state.plan_offen = next((item.id for item in plan.items if item.id not in fertig_ids), None)
    # „Weiter“ auf „Heute“: einmal bei dieser Planübung beginnen (`_zum_ziel`)
    ziel_index = (
        next((i for i, item in enumerate(plan.items) if item.id == state.plan_ziel), None)
        if not bearbeiten
        else None
    )
    state.plan_ziel = None

    # -- Handler ---------------------------------------------------------------

    def auffrischen() -> None:
        """Stand neu lesen und die Blöcke in derselben Liste ersetzen."""
        nonlocal anzahl, gemacht, tages_paare, tages_eintraege, vom_timer, fertig_ids
        tages_paare = state.sitzungen.eintraege_am_tag(state.profil.id, heute())
        tages_eintraege = [e for e, _ in tages_paare]
        anzahl = anzahl_je_uebung(tages_eintraege)
        vom_timer = _vom_timer(state, tages_eintraege)
        letzte.clear()
        fertig_ids = erledigte(plan.items, anzahl)
        gemacht = len(fertig_ids)
        stand.value = stand_text()
        liste.controls = listeninhalt()
        page.update()

    def melden(uebung: Exercise, eintrag: SessionEntry) -> None:
        text = eintrag.shorthand() if eintrag.result else "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        auffrischen()

    def uebung_fuer(item: PlanItem) -> Exercise:
        """Die Übung, wie diese Planübung sie sieht — mit hergeholten Zusatzfeldern.

        Einträge bekommen so die erweiterte Spec als Kopie (`core.standards.plan_spec`).
        """
        return mit_plan_spec(item, katalog[item.exercise_id])

    def eigener_eintrag(item: PlanItem) -> bool:
        """Spätere Stelle einer Übung, die heute noch offen ist: neuer Eintrag statt anhängen —
        aber nur einmal je Block (`eigene`, `core.plaene.spaetere_stelle_offen`)."""
        return spaetere_stelle_offen(item, stelle, fertig_ids, eigene)

    def letzter_eintrag(uebung: Exercise) -> SessionEntry | None:
        """„Wie zuletzt“: der jüngste Eintrag der Übung — aus dem Tag, wenn sie heute dran
        war, sonst einmal je Auffrischen aus der Datenbank."""
        if uebung.id not in letzte:
            heutig = letzter_heute(tages_eintraege, uebung.id)
            letzte[uebung.id] = (
                heutig
                if heutig is not None
                else state.sitzungen.letzter_eintrag(state.profil.id, uebung.id)
            )
        return letzte[uebung.id]

    def vorgabe(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
        """Gewählte Ausprägungen, sonst Ziel, sonst wie zuletzt (`core.plaene`)."""
        return auspraegung_vorgabe(
            state.auspraegung_wahl, item, uebung, lambda: letzter_eintrag(uebung)
        )

    def eigenen_gemerkt(item: PlanItem, neu: bool) -> None:
        if neu:
            eigene.add(item.id)

    def teilspec(item: PlanItem, uebung: Exercise) -> Any:
        """Die Spezifikation, beschränkt auf die Parameter, die der Plan anbietet."""
        return replace(uebung.result_spec, fields=aktive_felder(item, uebung))

    def kontext(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
        """Die gewählte Ausführung — beim ersten Aufbau wie der offene Eintrag, wenn es
        einen gibt (die Chips zeigen seinen Zustand), sonst `auspraegung_vorgabe`."""
        if item.id not in state.auspraegung_wahl:
            offen = stand_im_plan(
                stand_paare(), uebung, sitzungsplan, {}, jetzt(), state.sitzungen.offen_min
            ).offen
            if offen is not None:
                felder = kontextfelder(teilspec(item, uebung))
                state.auspraegung_wahl[item.id] = {
                    f.key: offen.result[f.key]
                    for f in felder
                    if not ist_leer(offen.result.get(f.key))
                }
        return vorgabe(item, uebung)

    def stand_fuer(item: PlanItem, uebung: Exercise, frisch: bool = False) -> offene.Stand:
        """Offener Eintrag und ob er markiert ist (`core.eintraege`). Die spätere Stelle einer
        Mehrfachübung beginnt immer neu — dort ist nichts markiert.

        Beim Aufbau aus den gelesenen Einträgen des Tages (`core.plaene.stand_im_plan`);
        wer gleich schreibt, fragt mit ``frisch`` die Datenbank — dieselbe Regel.
        """
        if eigener_eintrag(item):
            return offene.Stand(None, offene.KEINER)
        if frisch:
            with zur_zeit():
                return state.sitzungen.stand(
                    state.profil.id, uebung, heute(), sitzungsplan, kontext(item, uebung)
                )
        return stand_im_plan(
            stand_paare(),
            uebung,
            sitzungsplan,
            kontext(item, uebung),
            jetzt(),
            state.sitzungen.offen_min,
        )

    def kontext_text(uebung: Exercise, werte: dict[str, Any]) -> str:
        """„10 kg · links“ — die Ausprägungen in ``werte``."""
        return " · ".join(
            format_wert(f, werte[f.key])
            for f in kontextfelder(uebung.result_spec)
            if not ist_leer(werte.get(f.key))
        )

    def grenze_frei(item: PlanItem) -> bool:
        """Darf die Leistung den Abschnitt der Übung in der Aufnahme beginnen und beenden?
        Nicht, wenn ihre Uhr läuft — die klammert schon (`ui.marken`)."""
        return laufende(state, katalog[item.exercise_id], None if einzel else item) is None

    def ziel_frei(item: PlanItem) -> dict[str, Any]:
        """Das Ziel ohne Ausprägungen (`core.plaene.ziel_ohne_kontext`)."""
        return ziel_ohne_kontext(item, uebung_fuer(item))

    def noch_offen(item: PlanItem, uebung: Exercise) -> bool:
        """Ist von dieser Übung noch ein Eintrag offen (andere Ausführung)? Dann läuft ihr
        Abschnitt in der Aufnahme weiter — einer je Übung, nicht je Eintrag (21.10.2026)."""
        return bool(stand_fuer(item, uebung, frisch=True).alle_offenen)

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        """„Gemacht“, „Wie geplant“, ein Einzelwert: ein fertiger, geschlossener Eintrag —
        ein noch offener derselben Übung und Ausführung wird dabei geschlossen
        (`eintrag_fertig`)."""
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute())
        with zur_zeit():
            eintrag = state.sitzungen.eintrag_fertig(session, uebung, result, tag=heute())
        if nachtrag is None:  # Ein Nachtrag ist vorbei — keine Marke in einer Aufnahme
            marken.abschluss(
                state,
                uebung,
                eintrag,
                grenze=grenze_frei(item) and not noch_offen(item, uebung),
                auspraegung=kontext_text(uebung, eintrag.result),
            )
        melden(uebung, eintrag)

    def abschliesser(item: PlanItem) -> Callable[[], None]:
        """„Abschließen“: der markierte Eintrag bekommt sein Ende — und eine Marke."""

        def handler() -> None:
            uebung = uebung_fuer(item)
            ziel = stand_fuer(item, uebung, frisch=True).ziel
            if ziel is None:
                return
            with zur_zeit():
                eintrag = state.sitzungen.eintrag_schliessen(ziel.id)
            if nachtrag is None:
                marken.abschluss(
                    state,
                    uebung,
                    eintrag,
                    grenze=grenze_frei(item) and not noch_offen(item, uebung),
                    auspraegung=kontext_text(uebung, eintrag.result),
                )
            page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: abgeschlossen")))
            auffrischen()

        return handler

    def anhaengen(item: PlanItem, feld: FieldSpec, werte: list[float]) -> None:
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute())
        eintrag = None
        neu = eigener_eintrag(item)
        eigenen_gemerkt(item, neu)
        # Der erste Satz des Eintrags beginnt seinen Abschnitt in der Aufnahme (`ui.marken`) —
        # außer ein anderer Eintrag der Übung ist noch offen: dann läuft der Abschnitt schon
        st = None if neu else stand_fuer(item, uebung, frisch=True)
        ziel = st.ziel if st is not None else None
        erster = (ziel is None or not mengen(ziel.spec_snapshot, ziel.result)) and not (
            st is not None and st.andere
        )
        for wert in werte:
            with zur_zeit():
                eintrag = state.sitzungen.satz_anhaengen(
                    session, uebung, feld.key, wert, heute(), kontext(item, uebung), neu=neu
                )
            if nachtrag is None:
                marken.leistung(
                    state,
                    uebung,
                    eintrag,
                    feld.key,
                    wert,
                    erster=erster,
                    grenze=grenze_frei(item),
                    auspraegung=kontext_text(uebung, eintrag.result),
                )
            neu = erster = False
        if eintrag is not None:
            melden(uebung, eintrag)

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, kontext(item, uebung_fuer(item)))

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(
                item,
                {**ziel_frei(item), **kontext(item, uebung_fuer(item))},
            )

        return handler

    def wert_setzer(item: PlanItem, feld: FieldSpec, wert: Any) -> None:
        """Skala & Co.: in den heutigen Eintrag der Übung, nicht in einen eigenen."""
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute())
        neu = eigener_eintrag(item)
        eigenen_gemerkt(item, neu)
        with zur_zeit():
            eintrag = state.sitzungen.wert_setzen(
                session, uebung, feld.key, wert, heute(), kontext(item, uebung), neu=neu
            )
        melden(uebung, eintrag)

    def chip_erlediger(item: PlanItem, feld: FieldSpec, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            if feld.type == FieldType.SET_LIST:
                anhaengen(item, feld, [float(wert)])
            elif rolle(feld) == BEIWERK:
                wert_setzer(item, feld, wert)
            else:
                zusatz = kontext(item, uebung_fuer(item))
                eintragen(item, {**ziel_frei(item), **zusatz, feld.key: wert})

        return handler

    def parameter_waehler(item: PlanItem, key: str) -> Callable[[], None]:
        def handler() -> None:
            state.parameter_wahl[item.id] = key
            auffrischen()

        return handler

    def parameter_geaendert(item: PlanItem) -> Callable[[ft.Event[ft.SegmentedButton]], None]:
        """Das Segment „Parameter“ in der Ausführung (Darstellung „umschalten“)."""

        def handler(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                parameter_waehler(item, str(e.control.selected[0]))()

        return handler

    def auspraegung_setzen(item: PlanItem, key: str, wert: Any) -> None:
        """Eine Ausprägung wählen — ``None`` hebt die Wahl auf."""
        gewaehlt = state.auspraegung_wahl.setdefault(item.id, {})
        if wert is None:
            gewaehlt.pop(key, None)
        else:
            gewaehlt[key] = wert
        auffrischen()

    def variante_waehler(item: PlanItem) -> Callable[[str], None]:
        """Die Variantenzeile: ein Tipp wählt, ein zweiter heißt „ohne“ (Skizze A3)."""
        return lambda name: auspraegung_setzen(item, var.VARIANTE, name or None)

    def ausfuehrung_waehler(
        item: PlanItem, uebung: Exercise, e: SessionEntry
    ) -> Callable[[], None]:
        """Tipp auf einen offenen Eintrag anderer Ausführung: sie wählen — dann ist er markiert
        und die nächsten Tipps gehen dorthin (Skizze A3: „Tippen wählt lang“)."""

        def handler() -> None:
            felder = [f.key for f in kontextfelder(teilspec(item, uebung))]
            state.auspraegung_wahl[item.id] = offene.ausfuehrung(e, felder)
            auffrischen()

        return handler

    def variante_blatt_oeffner(item: PlanItem) -> Callable[[], None]:
        """Das Etikett-Symbol neben „Notiz“ (Ben, 21.10.2026; Skizzen A1, A2, D5): die Variante
        des markierten Eintrags setzen — ohne markierten die für den nächsten — oder eine neue
        anlegen, die in der Übung gespeichert wird."""

        def handler() -> None:
            uebung = uebung_fuer(item)
            st = stand_fuer(item, uebung, frisch=True)
            ziel = st.ziel
            gewaehlt = (
                var.von(ziel.result)
                if ziel is not None
                else str(kontext(item, uebung).get(var.VARIANTE) or "")
            )
            if ziel is not None:
                von = ziel.started_at.astimezone() if ziel.started_at else None
                werte = ziel.shorthand() if ziel.result else ""
                teile = [t for t in (f"seit {von:%H:%M}" if von else "", werte) if t]
                hinweis = (
                    f"Gilt für den offenen Eintrag ({' · '.join(teile)}) und alles, "
                    "was danach kommt."
                    if teile
                    else "Gilt für den offenen Eintrag und alles, was danach kommt."
                )
            else:
                hinweis = "Gilt für den nächsten Eintrag."

            def waehlen(name: str) -> None:
                aktuell = katalog[item.exercise_id]
                if ziel is not None:
                    with zur_zeit():
                        state.sitzungen.variante_setzen(ziel.id, aktuell, name)
                auspraegung_setzen(item, var.VARIANTE, name or None)

            def neu(name: str) -> None:
                aktuell = katalog[item.exercise_id]
                liste = [*var.varianten(aktuell.result_spec), var.Variante(name)]
                gespeichert = replace(
                    aktuell, result_spec=var.mit_varianten(aktuell.result_spec, liste)
                )
                state.uebungen.speichern(gespeichert)
                katalog[gespeichert.id] = gespeichert
                waehlen(name)
                page.show_dialog(
                    ft.SnackBar(ft.Text(f"{aktuell.name}: Variante „{name}“ angelegt"))
                )

            page.show_dialog(
                varianten_blatt(
                    uebung.name,
                    var.varianten(katalog[item.exercise_id].result_spec),
                    gewaehlt,
                    hinweis=hinweis,
                    auf_wahl=waehlen,
                    auf_neu=neu,
                    auf_bearbeiten=oeffner(f"/uebung/{item.exercise_id}/bearbeiten"),
                )
            )

        return handler

    def eigener_wert_fragen(item: PlanItem, feld: FieldSpec) -> None:
        """„…“ in einer Ausprägung (Skizze C1): ein eigener Wert (52°) — gilt wie ein
        angetippter Chip und steht danach als Segment in der Reihe."""
        eingabe = _kleines_feld(feld)
        eingabe.width = 140
        eingabe.autofocus = True
        nachher = Nachher()

        def uebernehmen(_e: object = None) -> None:
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "?"
                _zeigen(eingabe)
                return
            nachher.danach(lambda: auspraegung_setzen(item, feld.key, wert))
            schliessen(dialog)

        def abbrechen(_e: object = None) -> None:
            nachher.danach(auffrischen)  # die Segmente zeigen wieder die alte Wahl
            schliessen(dialog)

        eingabe.on_submit = uebernehmen
        dialog: ft.AlertDialog = ft.AlertDialog(
            title=ft.Text(f"{basis_label(feld)}: eigener Wert"),
            content=eingabe,
            on_dismiss=nachher.bei_schliessen,
            actions=[
                ft.TextButton("Abbrechen", on_click=abbrechen),
                ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=uebernehmen),
            ],
        )
        page.show_dialog(dialog)

    def satz_erlediger(
        item: PlanItem, feld: FieldSpec, anzahl_feld: ft.TextField, wert_feld: ft.TextField
    ) -> Callable[[], None]:
        """Sätze × Wert — hängt an den heutigen Eintrag an wie die Chips („+15“).

        Leere Sätze heißen einer. Zeiten nehmen ``45`` wie ``1:30``.
        """

        def handler() -> None:
            text = (wert_feld.value or "").strip()
            wert = einzelwert_lesen(feld, text)
            n_text = (anzahl_feld.value or "").strip()
            anzahl = parse_anzahl(n_text) if n_text else 1
            wert_feld.error = None if wert is not None and wert > 0 else "Wert?"
            anzahl_feld.error = None if anzahl is not None else f"1–{MAX_SAETZE}"
            if wert_feld.error or anzahl_feld.error or wert is None or anzahl is None:
                page.update()
                return
            anhaengen(item, feld, [float(wert)] * anzahl)

        return handler

    def summen_erlediger(
        item: PlanItem, feld: FieldSpec, wert_feld: ft.TextField
    ) -> Callable[[], None]:
        """Ohne Sätze: eine Zahl, die zum heutigen Eintrag dazukommt („+263“)."""

        def handler() -> None:
            wert = einzelwert_lesen(feld, (wert_feld.value or "").strip())
            wert_feld.error = None if wert is not None and wert > 0 else "Wert?"
            if wert_feld.error or wert is None:
                page.update()
                return
            anhaengen(item, feld, [float(wert)])

        return handler

    def wert_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Ein Einzelwert (Zeit, Strecke …): ein Eintrag, dazu das übrige Ziel."""

        def handler() -> None:
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "Wert?" if not (eingabe.value or "").strip() else "Ungültig"
                page.update()
                return
            zusatz = kontext(item, uebung_fuer(item))
            eintragen(item, {**ziel_frei(item), **zusatz, feld.key: wert})

        return handler

    def aufklapper(item: PlanItem) -> Callable[[], None]:
        """Darstellung „Aufklappen“: diese Übung öffnen — oder wieder schließen."""

        def handler() -> None:
            state.plan_offen = None if state.plan_offen == item.id else item.id
            auffrischen()

        return handler

    def darstellung_waehler(wert: str) -> Callable[[], None]:
        def handler() -> None:
            nonlocal darstellung
            state.plan_darstellung_setzen(wert)
            darstellung = wert
            for eintrag in menue.items:
                eintrag.checked = eintrag.data == wert
            menue_text.value = PLAN_DARSTELLUNGEN[wert]
            auffrischen()

        return handler

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def entferner(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.uebung_entfernen(item.id)
            page.show_dialog(ft.SnackBar(ft.Text("Aus dem Plan entfernt — Einträge bleiben.")))
            state.neu_zeichnen()

        return handler

    def ordnen(item_ids: list[str]) -> None:
        state.plaene.reihenfolge_setzen(plan.id, item_ids)
        state.neu_zeichnen()

    def schieber(index: int, richtung: int) -> Callable[[], None]:
        """Pfeil hoch/runter: eine Stelle weiter — für kurze Wege genauer als Ziehen."""

        def handler() -> None:
            ordnen(verschoben([i.id for i in plan.items], index, index + richtung))

        return handler

    def gezogen(e: ft.OnReorderEvent) -> None:
        if e.old_index is None or e.new_index is None or e.old_index == e.new_index:
            return
        ordnen(verschoben([i.id for i in plan.items], e.old_index, e.new_index))

    async def modus_wechseln() -> None:
        if not bearbeiten:
            await page.push_route(f"/plan/{plan.id}/bearbeiten")
            return
        # „Fertig“: dorthin, woher man kam — aus der Übung oder dem Kurs wieder dorthin,
        # nicht immer auf „Heute“ (`ui/navigation.py`); ohne Stapel (Tests) ``fertig``
        ansicht = ansicht_halter[0] if ansicht_halter else None
        ziel = zurueck_ziel(page, ansicht) if ansicht in page.views else fertig
        await page.push_route(ziel)

    def aktiv_wechseln(e: ft.Event[ft.Switch]) -> None:
        state.plaene.aktiv_setzen(plan.id, bool(e.control.value))
        state.neu_zeichnen()

    def tag_schalter(tag_nr: int) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.wochentage_setzen(plan.id, sorted(set(plan.wochentage) ^ {tag_nr}))
            state.neu_zeichnen()

        return handler

    def umbenennen(e: ft.Event[ft.TextField]) -> None:
        name = (e.control.value or "").strip()
        if name and name != plan.name:
            state.plaene.umbenennen(plan.id, name)
            state.neu_zeichnen()

    def loeschen_fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    nachher = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def loeschen() -> None:
        state.plaene.loeschen(plan.id)
        nachher.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Plan „{plan.name}“ liegt im Papierkorb — Einträge bleiben."))
        )

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Plan löschen?"),
        content=ft.Text(
            "Der Plan kommt in den Papierkorb (Übungen → Katalog → Papierkorb). "
            "Alles, was du damit dokumentiert hast, bleibt."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Löschen", on_click=loeschen),
        ],
    )

    # -- Blöcke ----------------------------------------------------------------
    # Ein Block (Ben, 14.10.2026): oben betont, was heute geleistet ist; darunter
    # die Knöpfe; dann, abgesetzt unter „EINTRAGEN“, je Parameter ein umrandeter
    # Abschnitt mit Überschrift — man sieht, wo etwas anfängt und aufhört.

    def geleistet_tafel(uebung: Exercise, item: PlanItem, st: offene.Stand) -> ft.Control:
        """Was heute schon da ist — **Einträge statt Bündel** (Ben, 19.10.2026, Skizze A1).

        Jeder Eintrag eine Zeile: Zeit, Ausprägung, die Werte groß, die Notiz kursiv. Der
        **offene** Eintrag ist markiert (Rand, „offen seit 10:07“) — dorthin geht der nächste
        Tipp; passt die gewählte Ausführung nicht, steht er ohne Markierung da. Ein Tipp auf
        einen geschlossenen Eintrag bietet „Wieder öffnen“ (`eintrag_blatt`), auf den offenen
        das Leistungen-Blatt. Das „i“ erklärt die Regel (`OFFEN_ERKLAERUNG`).
        """
        eigene = sorted(
            (e for e in tages_eintraege if e.exercise_id == uebung.id),
            key=lambda e: (e.started_at is None, e.started_at),
        )
        aufnahme = marken.aufnahme_laeuft(state)
        inhalt: list[ft.Control] = [
            eintrag_zeile(e, uebung, item, st, e.id in vom_timer, aufnahme) for e in eigene
        ]
        # Je Variante, was heute zusammenkam (Skizze A3) — getrennt gezählt
        if summen := je_variante(eigene):
            inhalt.insert(
                0,
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=4,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                            border_radius=6,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            content=ft.Text(
                                spans=[
                                    ft.TextSpan(
                                        text=name, style=ft.TextStyle(weight=ft.FontWeight.W_600)
                                    ),
                                    ft.TextSpan(text=f" {text}"),
                                ],
                                size=12,
                            ),
                        )
                        for name, text in summen
                    ],
                ),
            )
        # Spätere Stelle einer doppelten Übung: Was dasteht, stammt von früher am Tag
        if inhalt and uebung.id in mehrfach and item.id not in fertig_ids:
            titel = f"HEUTE BISHER — DAS {stelle[item.id]}. MAL STEHT NOCH AUS"
        elif heute() != state.heute():  # Nachtrag an einem vergangenen Tag
            titel = (
                f"AM {heute():%d.%m.} GELEISTET"
                if inhalt
                else f"Am {heute():%d.%m.} noch nichts eingetragen"
            )
        else:
            titel = "HEUTE GELEISTET" if inhalt else "Heute noch nichts eingetragen"
        kopf_teile: list[ft.Control] = [
            ft.Text(
                titel,
                size=11,
                weight=ft.FontWeight.BOLD if inhalt else None,
                opacity=0.65 if inhalt else 0.55,
            ),
            ft.IconButton(
                ft.Icons.INFO_OUTLINE,
                icon_size=16,
                tooltip="Wohin geht der nächste Tipp?",
                on_click=erklaerung_zeigen,
            ),
            ft.Container(expand=True),
        ]
        if inhalt:
            kopf_teile.append(
                ft.TextButton(
                    "Bearbeiten",
                    icon=ft.Icons.EDIT_OUTLINED,
                    tooltip=LEISTUNGEN_TIPP,
                    on_click=leistungen_zeigen(uebung),
                )
            )
        kopf = ft.Row(
            spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=kopf_teile
        )
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE,
            # Gestreckt: jede Zeile ist auf voller Breite antippbar
            content=ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[kopf, *inhalt],
            ),
        )

    def erklaerung_zeigen() -> None:
        dialog: ft.AlertDialog = ft.AlertDialog(
            title=ft.Text("Wohin geht der nächste Tipp?"),
            content=ft.Markdown(OFFEN_ERKLAERUNG),
            actions=[ft.TextButton("Verstanden", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def eintrag_zeile(
        e: SessionEntry,
        uebung: Exercise,
        item: PlanItem,
        st: offene.Stand,
        vom_timer: bool,
        aufnahme: bool,
    ) -> ft.Control:
        """Eine Zeile je Eintrag — markiert, offen ohne Markierung (andere Ausführung, ein
        Tipp wählt sie) oder geschlossen."""
        b = buendeln([e])[0]
        zeilen = b.parameter_zeilen()
        offen_ist = any(x.id == e.id for x in st.alle_offenen)
        markiert = (
            offen_ist
            and st.zustand == offene.MARKIERT
            and st.offen is not None
            and st.offen.id == e.id
        )
        von = e.started_at.astimezone() if e.started_at else None
        bis = e.ended_at.astimezone() if e.ended_at else None
        if offen_ist and nachtrag is not None and nachtrag.zeit is not None:
            # Offen ist hier nur, was um die gewählte Zeit nachgetragen wird (Skizze G1)
            zeit = f"{von:%H:%M}" if von else ""
            status = "NACHTRAG" if markiert else "Nachtrag · Tippen wählt"
        elif offen_ist:
            zeit = f"seit {von:%H:%M}" if von else ""
            status = "OFFEN" if markiert else "offen · Tippen wählt"
        else:
            zeit = f"{von:%H:%M}–{bis:%H:%M}" if von and bis else f"{von:%H:%M}" if von else ""
            # „vom Timer, 10:07“ (Ben, 17.10.2026; Skizze 12) — wann der Lauf begann
            status = (
                vom_timer_text([e.started_at] if e.started_at else [])
                if vom_timer
                else "zu"
                if bis
                else "zu · Zeitabstand"
            )
        kopf_text = " · ".join(t for t in (zeit, b.auspraegung_text()) if t)
        kopf: list[ft.Control] = [
            ft.Text(kopf_text, size=12, opacity=0.75, expand=True),
            ft.Text(
                status,
                size=11,
                weight=ft.FontWeight.W_700 if markiert else None,
                opacity=1.0 if markiert else 0.6,
            ),
        ]
        if markiert and aufnahme:
            kopf.append(
                ft.Icon(
                    ft.Icons.FAVORITE,
                    size=14,
                    color=ft.Colors.ERROR,
                    tooltip="Marken gehen in die laufende Aufnahme",
                )
            )
        werte: ft.Control = (
            wert_leiste(zeilen) if zeilen else ft.Text("Abgehakt", size=13, opacity=0.7)
        )
        teile: list[ft.Control] = [
            ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=kopf),
            werte,
        ]
        if e.note:
            teile.append(ft.Text(f"„{e.note}“", size=12, italic=True, opacity=0.75))
        if markiert:
            teile.append(ft.Text("Tipps gehen hierhin", size=11, opacity=0.7))
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=10,
            ink=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if markiert
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(2, ft.Colors.PRIMARY)
            if markiert
            else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
            if offen_ist
            else None,
            tooltip=LEISTUNGEN_TIPP if markiert else WAEHLEN_TIPP if offen_ist else EINTRAG_TIPP,
            on_click=leistungen_zeigen(uebung)
            if markiert
            else ausfuehrung_waehler(item, uebung, e)
            if offen_ist
            else eintrag_blatt_oeffner(e, uebung),
            content=ft.Column(spacing=4, controls=teile),
        )

    def eintrag_blatt_oeffner(e: SessionEntry, uebung: Exercise) -> Callable[[], None]:
        """Ein geschlossener Eintrag (Skizze A4): wieder öffnen, bearbeiten, löschen."""

        def handler() -> None:
            page.show_dialog(eintrag_blatt(e, uebung))

        return handler

    def eintrag_blatt(e: SessionEntry, uebung: Exercise) -> ft.BottomSheet:
        b = buendeln([e])[0]
        von = e.started_at.astimezone() if e.started_at else None
        bis = e.ended_at.astimezone() if e.ended_at else None
        zeit = f"{von:%H:%M}–{bis:%H:%M}" if von and bis else f"{von:%H:%M}" if von else ""
        werte = " · ".join(
            t for t in (b.auspraegung_text(), b.leistung_text() or b.einzelwerte_text()) if t
        )
        if e.ended_at is None:
            zuletzt = offene.letzte_aenderung(e)
            vor = int((jetzt() - zuletzt).total_seconds() // 60) if zuletzt else 0
            grund = (
                f"Vor {vor} min zuletzt geändert — länger als {state.eintrag_offen_min()} min "
                "ohne Satz (Zeitabstand, Einstellungen → Übungen)."
            )
        else:
            grund = f"Abgeschlossen um {bis:%H:%M}." if bis else "Abgeschlossen."
        nachher = Nachher()

        def wieder_oeffnen() -> None:
            with zur_zeit():
                state.sitzungen.eintrag_oeffnen(e.id)
            # Die Chips folgen dem wieder offenen Eintrag
            for item in plan.items:
                if item.exercise_id == uebung.id:
                    state.auspraegung_wahl.pop(item.id, None)
            nachher.danach(
                lambda: page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: wieder offen")))
            )
            nachher.danach(auffrischen)
            schliessen(blatt)

        def bearbeiten() -> None:
            nachher.danach(leistungen_zeigen(uebung))
            schliessen(blatt)

        def loeschen_fragen() -> None:
            nachher.danach(loeschen_dialog)
            schliessen(blatt)

        def loeschen_dialog() -> None:
            danach = Nachher()

            def loeschen() -> None:
                state.sitzungen.eintrag_loeschen(e.id)
                danach.danach(auffrischen)
                danach.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text("Eintrag gelöscht"))))
                schliessen(dialog)

            dialog: ft.AlertDialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Eintrag löschen?"),
                content=ft.Text("Er verschwindet aus Tag, Kalender und Verlauf."),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                    ft.FilledButton("Löschen", on_click=loeschen),
                ],
                on_dismiss=danach.bei_schliessen,
            )
            page.show_dialog(dialog)

        blatt: ft.BottomSheet = ft.BottomSheet(
            show_drag_handle=True,
            on_dismiss=nachher.bei_schliessen,
            content=ft.SafeArea(
                avoid_intrusions_top=False,
                content=ft.Container(
                    padding=ft.Padding.only(left=16, right=16, bottom=20),
                    content=ft.Column(
                        tight=True,
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=[
                            ft.Text(
                                f"{uebung.name} · {zeit}" if zeit else uebung.name,
                                size=18,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(werte or "abgehakt", size=13, opacity=0.75),
                            ft.Text(grund, size=13, opacity=0.75),
                            ft.FilledButton(
                                "Wieder öffnen — weitere Sätze hängen hier an",
                                icon=ft.Icons.RESTORE,
                                on_click=wieder_oeffnen,
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.OutlinedButton(
                                        "Bearbeiten",
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        expand=True,
                                        on_click=bearbeiten,
                                    ),
                                    ft.OutlinedButton(
                                        "Löschen",
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        expand=True,
                                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                        on_click=loeschen_fragen,
                                    ),
                                ],
                            ),
                            ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
                        ],
                    ),
                ),
            ),
        )
        return blatt

    def kopfzeile(uebung: Exercise, item: PlanItem) -> ft.Control:
        teile = [", ".join(uebung.typen), ", ".join(uebung.regionen)]
        if uebung.id in mehrfach:
            teile.append(f"{stelle[item.id]}. Mal im Plan")
        # Die Uhr neben dem i (Ben, 17.10.2026): der Timer dieser Übung — an der
        # Planübung, am Plan oder an der Übung; ohne einen legt die Uhr einen fest. Auch
        # beim Bearbeiten: dort wählt man den Timer der Planübung (Skizze 7).
        mit_plan = None if einzel else plan
        profil = timer_fuer(uebung, mit_plan, None if einzel else item)
        if profil is not None:
            teile.append(f"Timer: {profil.name}")
        uhr: list[ft.Control] = [
            ft.IconButton(
                ft.Icons.TIMER if profil is not None else ft.Icons.TIMER_OUTLINED,
                tooltip="Timer dieser Übung" if profil is not None else "Timer festlegen",
                on_click=oeffner(uebung_timer_route(route, uebung, None if einzel else item)),
            )
        ]
        untertitel = "  ·  ".join(t for t in teile if t)
        # Beim Bearbeiten zieht man am Griff (statt am ganzen Block, der Knöpfe trägt)
        griff: list[ft.Control] = (
            [
                ft.ReorderableDragHandle(
                    content=ft.Icon(ft.Icons.DRAG_HANDLE, size=24, opacity=0.7),
                    mouse_cursor=ft.MouseCursor.GRAB,
                )
            ]
            if bearbeiten
            else []
        )
        return ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                *griff,
                ft.Icon(symbol(uebung.icon_key), size=24, opacity=0.8),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=17, weight=ft.FontWeight.W_600),
                        ft.Text(untertitel, size=12, opacity=0.6) if untertitel else ft.Container(),
                    ],
                ),
                *uhr,
                ft.IconButton(
                    ft.Icons.INFO_OUTLINE,
                    tooltip="Beschreibung und Videos"
                    if bearbeiten
                    else "Parameter herholen, Beschreibung, Videos",
                    on_click=oeffner(info_route(item)),
                ),
            ],
        )

    def einstellungs_zone(
        zeilen: list[ft.Control], untertitel: str = "gilt für jeden Eintrag"
    ) -> ft.Control:
        """Die getönte Zone „Ausführung“ (Skizze C1): was für jeden Eintrag gilt — Variante,
        Gewicht, Seite, Winkel, die Wahl des Parameters. Segmente mit Haken: ein Zustand.
        Darunter, abgesetzt, Ja/Nein, Skala und Freitext für den offenen Eintrag (P71)."""
        farbe = ft.Colors.ON_SECONDARY_CONTAINER
        kopf = ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.TUNE, size=16, color=farbe),
                ft.Text("AUSFÜHRUNG", size=11, weight=ft.FontWeight.BOLD, color=farbe),
                ft.Text(untertitel, size=11, opacity=0.75),
            ],
        )
        return ft.Container(
            padding=ft.Padding.only(left=12, right=10, top=10, bottom=12),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.SECONDARY_CONTAINER),
            content=ft.Column(
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[kopf, *zeilen],
            ),
        )

    def einstellungs_zeile(vorn: ft.Control, auswahl: ft.Control) -> ft.Control:
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[vorn, ft.Container(expand=True, content=auswahl)],
        )

    def trennlinie(text: str) -> ft.Control:
        """Eine dünne Linie mit Text in der Mitte — trennt in der Zone, was für jeden Eintrag
        gilt, von dem, was nur den offenen betrifft."""

        def strich() -> ft.Control:
            return ft.Container(
                expand=True,
                height=1,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.OUTLINE),
            )

        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[strich(), ft.Text(text, size=11, opacity=0.75), strich()],
        )

    def eintragen_karte(zeilen: list[ft.Control], hinweis: ft.Control) -> ft.Control:
        """Eine Karte „Eintragen“ für alle Mengen, je Feld eine Zeile (Ben, 21.10.2026, P70 =
        Skizze E2: „Wdh. und Zeit nebeneinander … sonst werden das zu viele Fenster“) — weiß
        auf dem Block, damit die Werte sich von der getönten Ausführung abheben."""
        titel = "EINTRAGEN"
        if nachtrag is not None and nachtrag.zeit is not None:
            titel += f" · mit {nachtrag.zeit.astimezone():%H:%M}"
        kopf = ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.ADD, size=14, opacity=0.6),
                ft.Text(titel, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            ],
        )
        return ft.Container(
            padding=ft.Padding.only(left=12, right=10, top=10, bottom=12),
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            bgcolor=ft.Colors.SURFACE,
            content=ft.Column(spacing=10, controls=[kopf, *zeilen, hinweis]),
        )

    def varianten_zeile(item: PlanItem, gewaehlt: str) -> ft.Control:
        """Die Variante als erste Zeile der Ausführung (Skizzen A3, D1, D2): Segmente mit
        Namen, bei Platzmangel nur Symbole oder zwei Spalten (`components/varianten.py`)."""
        liste = var.varianten(katalog[item.exercise_id].result_spec)
        wahl = Variantenwahl(
            liste, gewaehlt, breite=zeilenbreite(page), on_change=variante_waehler(item)
        )
        return einstellungs_zeile(
            ft.Icon(ft.Icons.SELL_OUTLINED, size=18, opacity=0.8, tooltip="Variante"),
            wahl.control,
        )

    def auspraegung_auswahl(item: PlanItem, f: FieldSpec, gewaehlt: Any) -> ft.Control:
        """Eine Ausprägung (Gewicht, Seite, Winkel) als Segmente mit Haken (Skizze C1);
        „…“ nimmt einen eigenen Wert. Passen sie nicht in die Zeile: Chips, die umbrechen."""
        optionen = chips_fuer(item, f) or (f.quick if f.type == FieldType.CHOICE else [])
        # Ein eigener Wert (52°) steht wie ein Chip in der Reihe
        if gewaehlt is not None and gewaehlt not in optionen:
            optionen = [*optionen, gewaehlt]
        werte = {str(q): q for q in optionen}
        eigen = f.type != FieldType.CHOICE  # messbar: eigener Wert immer möglich
        breite = sum(len(chip_text(f, q)) * var.ZEICHEN_PX + var.INNEN_PX for q in optionen)
        breite += 44 if eigen else 0
        # Rand: Seite und Block (48), Zone (22), der Name davor (70)
        if breite <= zeilenbreite(page, rand=140):

            def geaendert(e: ft.Event[ft.SegmentedButton]) -> None:
                auswahl = list(e.control.selected or [])
                if not auswahl:
                    auspraegung_setzen(item, f.key, None)
                elif auswahl[0] == _EIGEN:
                    eigener_wert_fragen(item, f)
                else:
                    auspraegung_setzen(item, f.key, werte[auswahl[0]])

            segmente = [ft.Segment(value=str(q), label=ft.Text(chip_text(f, q))) for q in optionen]
            if eigen:
                segmente.append(
                    ft.Segment(value=_EIGEN, label=ft.Text("…"), tooltip="Eigener Wert")
                )
            return ft.SegmentedButton(
                segments=segmente,
                selected=[str(gewaehlt)] if gewaehlt is not None else [],
                allow_empty_selection=True,
                show_selected_icon=True,
                expand=True,
                on_change=geaendert,
            )

        def tipp(q: Any) -> Callable[[], None]:
            return lambda: auspraegung_setzen(item, f.key, None if gewaehlt == q else q)

        chips: list[ft.Control] = [
            ft.Chip(
                label=ft.Text(chip_text(f, q)),
                selected=gewaehlt == q,
                show_checkmark=True,
                on_click=tipp(q),
            )
            for q in optionen
        ]
        if eigen:
            chips.append(
                ft.Chip(
                    label=ft.Text("…"),
                    tooltip="Eigener Wert",
                    on_click=lambda: eigener_wert_fragen(item, f),
                )
            )
        return ft.Row(wrap=True, spacing=6, run_spacing=6, controls=chips)

    def ausfuehrung_abschnitt(
        item: PlanItem, uebung: Exercise, st: offene.Stand, schalter: ft.Control | None = None
    ) -> ft.Control | None:
        """Die Zone „Ausführung“: zuerst die Variante, dann die Ausprägungen (Winkel, Gewicht,
        Seite) — man wählt sie vorher, sie gelten für jeden Eintrag; ``schalter`` ist die
        Wahl des Parameters (Darstellung „umschalten“). Abgesetzt darunter Ja/Nein, Skala und
        Freitext: Sie gelten nur für den offenen Eintrag und trennen nicht (Ben, 21.10.2026,
        P71)."""
        felder = kontextfelder(teilspec(item, uebung))
        gewaehlt = kontext(item, uebung) if felder else {}
        zeilen: list[ft.Control] = []
        for f in felder:
            if var.ist_variante(f):
                zeilen.append(varianten_zeile(item, str(gewaehlt.get(f.key) or "")))
                continue
            zeilen.append(
                einstellungs_zeile(
                    ft.Text(basis_label(f), size=12, width=62, opacity=0.8),
                    auspraegung_auswahl(item, f, gewaehlt.get(f.key)),
                )
            )
        if schalter is not None:
            zeilen.append(schalter)
        beiwerk = beiwerk_felder(item, uebung)
        if not beiwerk:
            return einstellungs_zone(zeilen) if zeilen else None
        if zeilen:
            zeilen.append(trennlinie("gilt für den offenen Eintrag"))
        zeilen += [beiwerk_zeile(item, uebung, f, st.ziel) for f in beiwerk]
        if len(zeilen) == len(beiwerk):  # nur Beiwerk: kein Strich, der Kopf sagt es
            return einstellungs_zone(zeilen, "gilt für den offenen Eintrag")
        return einstellungs_zone(zeilen)

    def beiwerk_felder(item: PlanItem, uebung: Exercise) -> list[FieldSpec]:
        """Ja/Nein, Skala und Freitext, die diese Planübung anbietet — sie stehen in der
        Ausführung, nicht unter „Eintragen“ (P71)."""
        return [
            f
            for f in aktive_felder(item, uebung)
            if rolle(f) == BEIWERK and f.type in (FieldType.SCALE, FieldType.BOOL, FieldType.TEXT)
        ]

    def beiwerk_zeile(
        item: PlanItem, uebung: Exercise, f: FieldSpec, ziel: SessionEntry | None
    ) -> ft.Control:
        """Eine Zeile der Ausführung für den offenen Eintrag: zeigt seinen Wert und ändert ihn
        (`SessionRepo.wert_setzen`, `text_setzen`) — wie die Notiz; ohne markierten Eintrag
        beginnt der erste Wert einen. Die Skala ist der Schiebebalken der Tagesfelder."""
        wert = ziel.result.get(f.key) if ziel is not None else None
        name = ft.Text(basis_label(f), size=12, width=62, opacity=0.8)
        if f.type == FieldType.SCALE:

            def skala(x: float | int | None) -> None:
                if x is None and ziel is None:
                    return  # ✕ ohne offenen Eintrag: nichts zu löschen
                wert_setzer(item, f, x)

            zahl = float(wert) if isinstance(wert, int | float) else None
            return einstellungs_zeile(name, skala_regler(f, zahl, skala))
        if f.type == FieldType.BOOL:

            def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
                auswahl = list(e.control.selected or [])
                if not auswahl:
                    if ziel is not None:
                        wert_setzer(item, f, None)
                    return
                wert_setzer(item, f, auswahl[0] == "ja")

            return einstellungs_zeile(
                name,
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="ja", label=ft.Text("Ja")),
                        ft.Segment(value="nein", label=ft.Text("Nein")),
                    ],
                    selected=["ja"] if wert is True else ["nein"] if wert is False else [],
                    allow_empty_selection=True,
                    show_selected_icon=True,
                    expand=True,
                    on_change=gewaehlt,
                ),
            )
        # Freitext — ersetzt den Text des offenen Eintrags (`SessionRepo.text_setzen`)
        eingabe = ft.TextField(
            value="" if wert is None else str(wert),
            dense=True,
            expand=True,
            multiline=True,
            max_lines=3,
        )

        def absenden() -> None:
            text = (eingabe.value or "").strip()
            if not text:
                return
            session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute())
            neu = eigener_eintrag(item)
            eigenen_gemerkt(item, neu)
            with zur_zeit():
                eintrag = state.sitzungen.text_setzen(
                    session, uebung, f.key, text, heute(), kontext(item, uebung), neu=neu
                )
            melden(uebung, eintrag)

        return einstellungs_zeile(
            name,
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    eingabe,
                    ft.IconButton(
                        ft.Icons.CHECK, tooltip=f"{f.label} eintragen", on_click=absenden
                    ),
                ],
            ),
        )

    def kurzname(feld: FieldSpec) -> str:
        """Der Name vor einer Zeile unter „Eintragen“ — kurz genug für die Spalte:
        „Wiederholungen“ wird „Wdh.“ (die Einheit), „Haltezeit“ bleibt."""
        name = basis_label(feld)
        if len(name) > 9 and feld.unit and len(feld.unit) <= 6:
            return feld.unit
        return name

    def zeilen_zusatz(feld: FieldSpec) -> str:
        """Klein unter dem Namen: wie ein Wert zählt — je Satz, zur Summe, mm:ss."""
        liste = feld.type == FieldType.SET_LIST
        zeit = feld.unit == "s" or feld.type == FieldType.DURATION
        if liste and feld.saetze:
            return "s je Satz" if zeit else "je Satz"
        if liste:
            return "zur Summe"
        if feld.type == FieldType.DURATION:
            return "mm:ss"
        return "" if feld.unit == kurzname(feld) else feld.unit or ""

    def zeilen_knopf(text: str, on_click: Callable[[], None], col: int | None = None) -> ft.Control:
        """Ein gefüllter Wert-Knopf in einer Zeile (Skizze E2): Die Knöpfe teilen sich die
        Breite; ab vier stehen sie zu dritt in einer eigenen Reihe (``col``)."""
        return ft.FilledButton(
            content=ft.Text(text, size=15, weight=ft.FontWeight.W_700, no_wrap=True),
            height=44,
            expand=col is None,
            col=col if col is not None else 12,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=22),
                padding=ft.Padding.symmetric(horizontal=4),
            ),
            on_click=on_click,
        )

    def menge_zeile(item: PlanItem, feld: FieldSpec) -> ft.Control:
        """Eine Menge (Wiederholungen, Haltezeit, Strecke …) als Zeile der Karte „Eintragen“
        (Ben, 21.10.2026, P70 = Skizze E2): der Name, die gefüllten „+“-Knöpfe — jeder Tipp
        trägt sofort ein —, „…“ klappt den eigenen Wert auf (Sätze × Wert). Ohne Chips steht
        das Zahlenfeld gleich da; ohne Sätze (``FieldSpec.saetze``) zählt ein Chip zur Summe
        des Tages dazu."""
        liste = feld.type == FieldType.SET_LIST
        werte = chips_fuer(item, feld)
        zusatz = zeilen_zusatz(feld)
        name = ft.Column(
            spacing=0,
            tight=True,
            width=64,
            controls=[
                ft.Text(kurzname(feld), size=12, weight=ft.FontWeight.W_600, max_lines=2),
                *([ft.Text(zusatz, size=10, opacity=0.6)] if zusatz else []),
            ],
        )
        # Eine Auswahl (Seite) gibt es nur über die Knöpfe
        frei = mengen_eingabe(item, feld) if feld.type != FieldType.CHOICE else None
        if not werte:
            return ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[name, ft.Container(expand=True, content=frei)],
            )
        knoepfe = [
            (("+" if liste else "") + chip_text(feld, q), chip_erlediger(item, feld, q))
            for q in werte
        ]
        schluessel = (item.id, feld.key)
        mehr: list[ft.Control] = []
        frei_box = ft.Container(
            content=frei,
            visible=schluessel in frei_offen,
            padding=ft.Padding.only(left=70),
        )
        if frei is not None:

            def umschalten() -> None:
                frei_offen.symmetric_difference_update({schluessel})
                frei_box.visible = schluessel in frei_offen
                _zeigen(frei_box)

            mehr.append(
                ft.OutlinedButton(
                    content=ft.Text("…", size=15, weight=ft.FontWeight.W_700),
                    width=44,
                    height=44,
                    tooltip="Eigener Wert (Sätze × Wert)" if liste else "Eigener Wert",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=22),
                        side=ft.BorderSide(2, ft.Colors.PRIMARY),
                        padding=ft.Padding.all(0),
                    ),
                    on_click=umschalten,
                )
            )
        teile: list[ft.Control]
        if len(knoepfe) <= 3:
            teile = [
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[name, *(zeilen_knopf(t, h) for t, h in knoepfe), *mehr],
                )
            ]
        else:
            teile = [
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[ft.Container(expand=True, content=name), *mehr],
                ),
                ft.ResponsiveRow(
                    spacing=6,
                    run_spacing=6,
                    controls=[zeilen_knopf(t, h, col=4) for t, h in knoepfe],
                ),
            ]
        if frei is not None:
            teile.append(frei_box)
        return ft.Column(spacing=6, controls=teile)

    def mengen_eingabe(item: PlanItem, feld: FieldSpec) -> ft.Control:
        """Nur Zahlen: „Sätze × Wert“ für Satzfelder, sonst ein Feld — dann „Eintragen“."""
        zeit = feld.unit == "s" or feld.type == FieldType.DURATION
        felder: list[ft.Control]
        if feld.type == FieldType.SET_LIST and not feld.saetze:
            # Ohne Sätze (Ben, 18.10.2026): eine Zahl, sie kommt zum Tag dazu
            wert = _zahlfeld(
                120,
                label="Zeit" if zeit else feld.unit or basis_label(feld),
                hinweis="1:30" if zeit else "263",
                zeit=zeit,
            )
            handler = summen_erlediger(item, feld, wert)
            felder = [wert]
        elif feld.type == FieldType.SET_LIST:
            anzahl = _zahlfeld(64, label="Sätze", hinweis="1")
            wert = _zahlfeld(
                100,
                label="Sekunden" if zeit else feld.unit or "Wert",
                hinweis="45 · 1:30" if zeit else "",
                zeit=zeit,
            )
            handler = satz_erlediger(item, feld, anzahl, wert)

            async def weiter(_: ft.Event[ft.TextField]) -> None:
                await wert.focus()  # Enter in „Sätze“ springt zum Wert

            anzahl.on_submit = weiter
            felder = [anzahl, ft.Text("×", size=16, opacity=0.7), wert]
        else:
            wert = _zahlfeld(
                120,
                label="Zeit" if zeit else feld.unit or basis_label(feld),
                hinweis="20:00" if zeit else "",
                zeit=zeit,
            )
            handler = wert_erlediger(item, feld, wert)
            felder = [wert]
        wert.on_submit = lambda _: handler()
        eintragen_knopf = ft.OutlinedButton(
            content=ft.Row(
                tight=True,
                spacing=6,
                controls=[ft.Icon(ft.Icons.ADD, size=18), ft.Text("Eintragen")],
            ),
            height=48,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=24),
                side=ft.BorderSide(2, ft.Colors.PRIMARY),
                padding=ft.Padding.symmetric(horizontal=14),
            ),
            on_click=handler,
        )
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[*felder, eintragen_knopf],
        )

    def parameter_abschnitte(
        item: PlanItem, uebung: Exercise
    ) -> list[tuple[str, str, Callable[[], ft.Control]]]:
        """Je Menge (Schlüssel, Name, Bauer) eine Zeile der Karte „Eintragen“ — Ja/Nein,
        Skala und Freitext stehen seit P71 in der Ausführung (`beiwerk_felder`).

        Gebaut wird erst bei Bedarf — beim Umschalten nur die gewählte.
        """
        return [
            (f.key, basis_label(f), partial(menge_zeile, item, f))
            for f in leistungsfelder(teilspec(item, uebung))
        ]

    def ziel_hinweis(item: PlanItem, uebung: Exercise, st: offene.Stand) -> ft.Control:
        """Unter den Chips (Skizze A1/A2): wohin der nächste Wert geht — ohne Markierung nur
        eine Zeile, die Erklärung hängt am „i“ (Ben, 19.10.2026)."""
        wahl = kontext_text(uebung, kontext(item, uebung))
        if st.zustand == offene.MARKIERT:
            text = (
                f"Kommt zum offenen Eintrag ({wahl}) dazu"
                if wahl
                else "Kommt zum offenen Eintrag dazu"
            )
            punkt: ft.Control = ft.Container(
                width=8, height=8, border_radius=4, bgcolor=ft.Colors.PRIMARY
            )
        else:
            text = (
                f"Beginnt einen neuen Eintrag ({wahl})" if wahl else "Beginnt einen neuen Eintrag"
            )
            punkt = ft.Container(
                width=8, height=8, border_radius=4, border=ft.Border.all(1, ft.Colors.OUTLINE)
            )
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[punkt, ft.Text(text, size=11, opacity=0.75)],
        )

    def eingabe_bereich(item: PlanItem, uebung: Exercise, st: offene.Stand) -> list[ft.Control]:
        """Oben die Zone „Ausführung“ (Einstellungen), darunter „EINTRAGEN“ mit den Werten —
        wie die Darstellung sagt (Skizze C1)."""
        teile = parameter_abschnitte(item, uebung)
        gewaehlt: str | None = None
        schalter: ft.Control | None = None
        if darstellung == UMSCHALTEN and len(teile) > 1:
            keys = [key for key, _, _ in teile]
            haupt = hauptfeld(uebung)
            gewaehlt = state.parameter_wahl.get(item.id)
            if gewaehlt not in keys:
                gewaehlt = haupt.key if haupt is not None and haupt.key in keys else keys[0]
            # Welcher Parameter gerade eingetragen wird, ist eine Einstellung — ein Segment
            schalter = einstellungs_zeile(
                ft.Text("Parameter", size=12, width=62, opacity=0.8),
                ft.SegmentedButton(
                    segments=[ft.Segment(value=key, label=ft.Text(name)) for key, name, _ in teile],
                    selected=[gewaehlt],
                    show_selected_icon=False,
                    expand=True,
                    on_change=parameter_geaendert(item),
                ),
            )
        ausfuehrung = ausfuehrung_abschnitt(item, uebung, st, schalter)
        if not teile and ausfuehrung is None:
            return []
        bereich: list[ft.Control] = []
        if ausfuehrung is not None:
            bereich.append(ausfuehrung)
        if teile:
            # Eine Karte für alle Mengen, je Feld eine Zeile (P70 = Skizze E2)
            zeilen = (
                [next(bauen() for key, _, bauen in teile if key == gewaehlt)]
                if gewaehlt is not None
                else [bauen() for _, _, bauen in teile]
            )
            bereich.append(eintragen_karte(zeilen, ziel_hinweis(item, uebung, st)))
        else:  # nur Ausführung (Skala & Co.): wohin der nächste Wert geht
            bereich.append(ziel_hinweis(item, uebung, st))
        return bereich

    def leistungen_zeigen(uebung: Exercise) -> Callable[[], None]:
        """Alle Einträge der Übung von heute — als Blatt über dem Plan (`views/leistungen.py`;
        Ben, 18.10.2026: „So wechselt das Bild nicht immer hin und her“)."""

        def handler() -> None:
            page.show_dialog(leistungen_blatt(page, state, uebung, heute(), danach=auffrischen))

        return handler

    def info_route(item: PlanItem) -> str:
        """Beim Üben die Infoseite unter dem Plan (Zurück führt hierher), sonst die Übung."""
        if bearbeiten:
            return f"/uebung/{item.exercise_id}"
        return f"{route}/info" if einzel else f"{route}/info/{item.id}"

    def notiz_knopf(item: PlanItem) -> ft.Control:
        return ft.TextButton(
            "Notiz",
            icon=ft.Icons.EDIT_NOTE_OUTLINED,
            tooltip="Ein Satz ins Tagebuch — am offenen Eintrag",
            on_click=notiz_fragen(item),
        )

    def etikett_knopf(item: PlanItem, st: offene.Stand) -> ft.Control:
        """Neben „Notiz“ nur das Etikett-Symbol, ohne Text (Ben, 21.10.2026: „bleib beim
        Symbol“ — was es bedeutet, sagt die Hilfe). Getönt, wenn der markierte Eintrag eine
        Variante trägt."""
        gesetzt = var.von(st.ziel.result) if st.ziel is not None else ""
        return ft.IconButton(
            ft.Icons.SELL if gesetzt else ft.Icons.SELL_OUTLINED,
            tooltip=f"Variante: {gesetzt}" if gesetzt else "Variante",
            icon_color=ft.Colors.PRIMARY,
            style=ft.ButtonStyle(bgcolor=ft.Colors.SECONDARY_CONTAINER) if gesetzt else None,
            on_click=variante_blatt_oeffner(item),
        )

    def notiz_fragen(item: PlanItem) -> Callable[[], None]:
        """Ein Dialog mit Textfeld; die Notiz von heute steht schon drin zum Weiterschreiben."""

        def handler() -> None:
            uebung = uebung_fuer(item)
            # Die Notiz der Übung von heute — auch nach einem neuen Satz dieselbe
            with zur_zeit():
                heutig = (
                    None
                    if eigener_eintrag(item)
                    else state.sitzungen.notiz_eintrag(
                        state.profil.id, uebung, heute(), sitzungsplan, kontext(item, uebung)
                    )
                )
            feld = ft.TextField(
                value=heutig.note if heutig is not None else "",
                hint_text="Wie ging es? (Diktat über die Tastatur)",
                multiline=True,
                min_lines=3,
                max_lines=8,
                autofocus=True,
            )

            # Neu zeichnen erst, wenn der Dialog wirklich zu ist (`components/dialoge.py`)
            nachher = Nachher()

            def gespeichert() -> None:
                page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: Notiz gespeichert")))
                auffrischen()

            anfang = (feld.value or "").strip()
            #: Gespeichert oder abgebrochen — das Schließen danach speichert nicht noch einmal
            erledigt: list[bool] = []

            def sichern() -> None:
                text = (feld.value or "").strip()
                if text or heutig is not None:
                    session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute())
                    neu = eigener_eintrag(item)
                    eigenen_gemerkt(item, neu)
                    with zur_zeit():
                        state.sitzungen.eintrag_notiz_setzen(
                            session,
                            uebung,
                            text,
                            heute(),
                            neu=neu,
                            kontext=kontext(item, uebung),
                        )
                    nachher.danach(gespeichert)

            async def geschlossen(e: object) -> None:
                # Daneben getippt: Geänderter Text gilt als gespeichert (Ben, 16.10.2026,
                # Autosave); nur „Abbrechen" verwirft.
                if not erledigt and (feld.value or "").strip() != anfang:
                    sichern()
                # Eine echte async-Funktion: eine Instanz mit async ``__call__``
                # erkennt Flet nicht als Koroutine und ruft sie nie zu Ende
                await nachher(e)

            def speichern() -> None:
                erledigt.append(True)
                sichern()
                schliessen(dialog)

            def abbrechen() -> None:
                erledigt.append(True)
                schliessen(dialog)

            dialog = ft.AlertDialog(
                on_dismiss=geschlossen,
                title=ft.Text(f"Notiz: {uebung.name}"),
                content=feld,
                actions=[
                    ft.TextButton("Abbrechen", on_click=abbrechen),
                    ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=speichern),
                ],
            )
            page.show_dialog(dialog)

        return handler

    def block(index: int, item: PlanItem) -> ft.Control:
        # Kein ``key`` an den Blöcken (Ben, 17.10.2026): `auffrischen` setzt neue Blöcke in
        # dieselbe Liste; Flet 1.0 gleicht gleiche Schlüssel verschiedener Objekte wie im
        # deklarativen Modell ab und friert die neuen ein — dann warf jede spätere Änderung
        # (etwa „Wert?“ am Feld) „Frozen controls cannot be updated“. Die ziehbare Liste
        # kommt ohne aus (sie nimmt die ID des Controls).
        if item.exercise_id not in katalog:
            return ft.Container(
                padding=12,
                content=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5),
            )
        uebung = uebung_fuer(item)
        n = item.id in fertig_ids
        ziel = ziel_text(uebung, item.target)
        # Beim Nachtragen steht die Übung schon im Kopf der Seite (Skizze G1)
        inhalt: list[ft.Control] = [kopfzeile(uebung, item)] if nachtrag is None else []

        if bearbeiten:
            aktive = [f for f in aktive_felder(item, uebung) if not var.ist_variante(f)]
            varianten_text = ""
            if var.feld(uebung.result_spec) is not None:
                varianten_text = "  ·  Varianten" if varianten_an(item) else "  ·  Varianten aus"
            inhalt.append(
                ft.Text(
                    (
                        "Parameter: " + ", ".join(f.label for f in aktive)
                        if aktive
                        else "nur abhaken"
                    )
                    + varianten_text
                    + (f"  ·  Ziel {ziel}" if ziel else "  ·  kein Ziel"),
                    size=12,
                    opacity=0.7,
                )
            )
            # Knöpfe links (dürfen umbrechen), die Pfeile fest rechts — ein dehnbarer
            # Platzhalter in einer umbrechenden Zeile brach das Layout
            inhalt.append(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(
                            wrap=True,
                            expand=True,
                            spacing=8,
                            run_spacing=6,
                            controls=[
                                _knopf(
                                    "Einstellen",
                                    ft.Icons.TUNE,
                                    oeffner(f"{route}/ziel/{item.id}"),
                                ),
                                ft.TextButton(
                                    "Entfernen",
                                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    on_click=entferner(item),
                                ),
                            ],
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Eine Stelle nach oben",
                            disabled=index == 0,
                            on_click=schieber(index, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Eine Stelle nach unten",
                            disabled=index == len(plan.items) - 1,
                            on_click=schieber(index, 1),
                        ),
                    ],
                )
            )
        else:
            # Aufklappen lohnt nur bei mehreren Übungen und wenn es etwas einzutragen gibt
            klappbar = (
                darstellung == AUFKLAPPEN
                and not einzel
                and len(plan.items) > 1
                and bool(aktive_felder(item, uebung))
            )
            offen = not klappbar or state.plan_offen == item.id
            st = stand_fuer(item, uebung)
            # „Abschließen“ fixiert den markierten Eintrag; ohne markierten heißt der Knopf
            # „Gemacht“ und legt einen fertigen an (Ben, 19.10.2026, Skizzen A1–A3)
            # Gefüllt sind nur Knöpfe, die Werte schreiben (Skizze C1): „Wie geplant“ und die
            # „+“-Knöpfe; „Abschließen“/„Gemacht“ stehen umrandet daneben
            knoepfe: list[ft.Control] = [
                _umrandet("Abschließen", ft.Icons.CHECK, abschliesser(item))
                if st.zustand == offene.MARKIERT
                else _umrandet("Gemacht", ft.Icons.CHECK, erlediger(item))
            ]
            if ziel:
                knoepfe.append(
                    _knopf(
                        f"Wie geplant · {ziel}", ft.Icons.FLAG, ziel_erlediger(item), betont=True
                    )
                )
            if klappbar:
                # „Werte“ statt „Eintragen“ (Ben, 21.10.2026): das Wort hatte drei Bedeutungen
                knoepfe.append(
                    ft.TextButton(
                        "Zuklappen" if offen else "Werte",
                        icon=ft.Icons.EXPAND_LESS if offen else ft.Icons.EXPAND_MORE,
                        tooltip="Eingabe dieser Übung schließen"
                        if offen
                        else "Eingabe dieser Übung öffnen",
                        on_click=aufklapper(item),
                    )
                )
            # Stoppuhr und Timer (Ben, 18.10.2026): als Knöpfe zwischen „Gemacht“ und „Notiz“
            # oder als eigene Zeile darunter — und, solange sie läuft, ihre Anzeige
            aus_katalog = katalog[item.exercise_id]
            planuebung = None if einzel else item
            uhr = (
                uhr_teile(
                    page,
                    state,
                    uebung=aus_katalog,
                    plan=None if einzel else plan,
                    item=planuebung,
                    timer_oeffnen=oeffner(uebung_timer_route(route, aus_katalog, planuebung)),
                )
                if nachtrag is None and uhr_an(aus_katalog, planuebung)
                else UhrTeile()
            )
            knoepfe.extend(uhr.knoepfe)
            knoepfe.append(notiz_knopf(item))
            if varianten_an(item):
                knoepfe.append(etikett_knopf(item, st))
            inhalt.append(geleistet_tafel(uebung, item, st))
            inhalt.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=knoepfe))
            if uhr.zeile is not None and (offen or laufende(state, aus_katalog, planuebung)):
                inhalt.append(uhr.zeile)
            if offen:
                inhalt.extend(eingabe_bereich(item, uebung, st))

        return ft.Container(
            padding=ft.Padding.only(left=14, right=10, top=12, bottom=12),
            margin=ft.Margin.only(left=12, right=12, bottom=12),
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if n and not bearbeiten
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            # Gestreckt: Tafel und Abschnitte so breit wie der Block
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=inhalt
            ),
        )

    # -- Aufbau ----------------------------------------------------------------

    def stand_text() -> str:
        return f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen"

    stand = ft.Text(stand_text(), size=13, opacity=0.7)

    # Darstellung der Übungen umschalten — zum Vergleichen gleich oben im Plan
    menue_text = ft.Text(PLAN_DARSTELLUNGEN[darstellung], size=12)
    menue = ft.PopupMenuButton(
        tooltip="Darstellung der Übungen",
        content=ft.Row(
            tight=True,
            spacing=4,
            controls=[
                ft.Icon(ft.Icons.VIEW_AGENDA_OUTLINED, size=16, opacity=0.7),
                menue_text,
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, opacity=0.7),
            ],
        ),
        items=[
            ft.PopupMenuItem(
                content=text,
                checked=key == darstellung,
                data=key,
                on_click=darstellung_waehler(key),
            )
            for key, text in PLAN_DARSTELLUNGEN.items()
        ],
    )

    kopf: list[ft.Control]
    if bearbeiten:
        tage = ft.Row(
            wrap=True,
            spacing=4,
            run_spacing=4,
            controls=[
                ft.Chip(
                    label=ft.Text(kurz),
                    selected=nr in plan.wochentage,
                    show_checkmark=False,
                    on_click=tag_schalter(nr),
                )
                for nr, kurz in enumerate(WOCHENTAGE_KURZ)
            ],
        )
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Switch(
                label="Aktiv — erscheint auf „Heute“" if plan.aktiv else "Deaktiviert",
                value=plan.aktiv,
                on_change=aktiv_wechseln,
            ),
            tage,
            ft.Text(
                f"Steht an: {tage_text(plan.wochentage)}. An anderen Tagen erscheint er nicht "
                "auf „Heute“, lässt sich aber über „Heute trainieren“ aufnehmen.",
                size=12,
                opacity=0.7,
            ),
            plan_timer_karte(page, state, plan),
            ft.Text(
                "„Einstellen“ legt Ziel und Eingabe je Übung fest. Reihenfolge: am Griff ziehen "
                "oder mit den Pfeilen. Eine Übung darf mehrmals im Plan stehen.",
                size=12,
                opacity=0.7,
            ),
        ]
    elif nachtrag is not None:
        kopf = list(nachtrag.kopf)
    elif einzel:
        kopf = [
            ft.Text(
                "Ohne Plan — der Eintrag erscheint auf „Heute“ unter „Ohne Plan“.",
                size=13,
                opacity=0.7,
            ),
            menue,
            _knopf_legende(),
        ]
    else:
        kopf = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Container(content=stand, expand=True), menue],
            ),
            _knopf_legende(),
        ]

    fuss: list[ft.Control] = []
    if bearbeiten:
        fuss = [
            ft.FilledButton(
                "Übung hinzufügen",
                icon=ft.Icons.ADD,
                on_click=oeffner(f"{route}/hinzufuegen"),
            ),
            ft.TextButton("Plan löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=loeschen_fragen),
        ]
    elif not plan.items:
        fuss = [ft.FilledButton("Übungen hinzufügen", icon=ft.Icons.EDIT, on_click=modus_wechseln)]

    # Kopf (Name, aktiv, Tage …) und Fuß scrollen mit den Übungen — nur die
    # Leiste oben bleibt stehen. Fest stehend nahm der Kopf beim Bearbeiten den
    # halben Bildschirm, für die Übungen blieb kaum Platz (Ben, 14.10.).
    kopf_box = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Column(spacing=6, controls=kopf),
    )
    fuss_box = ft.Container(padding=16, content=ft.Row(spacing=8, wrap=True, controls=fuss))

    def listeninhalt() -> list[ft.Control]:
        bloecke = [block(i, item) for i, item in enumerate(plan.items)]
        if bearbeiten:
            return bloecke  # Kopf und Fuß sind Kopf- und Fußzeile der ziehbaren Liste
        if nachtrag is not None:  # unter dem Block, wohin die Tipps gehen (Skizze G1)
            hinweis = ft.Text(nachtrag.hinweis(), size=12, opacity=0.7)
            return [
                kopf_box,
                *bloecke,
                ft.Container(
                    padding=ft.Padding.only(left=20, right=20, top=4, bottom=24), content=hinweis
                ),
            ]
        return [kopf_box, *bloecke, *([fuss_box] if fuss else [])]

    liste: ft.ListView
    if bearbeiten:
        liste = ft.ReorderableListView(
            expand=True,
            header=kopf_box,
            footer=fuss_box,
            show_default_drag_handles=False,
            on_reorder=gezogen,
            controls=listeninhalt(),
        )
    else:
        liste = ft.ListView(expand=True, controls=listeninhalt())
        if ziel_index == 0:
            state.scroll_offsets.pop(route, None)  # die erste steht oben, unter dem Kopf
        elif ziel_index is not None:
            _zum_ziel(page, state, route, liste, ziel_index + 1)  # 0 ist der Kopf
    liste = scroll_merken(page, state, route, liste)

    # -- Nachtrag: „Fertig“ und Zurück schließen, was hier offen ist ------------------

    def nachtrag_offene() -> list[SessionEntry]:
        """Die Einträge, die der Nachtrag offen hat — um die gewählte Zeit; jetzt
        Eingetragenes bleibt offen wie beim Training."""
        if nachtrag is None or nachtrag.zeit is None:
            return []
        return [
            e
            for item in plan.items
            if item.exercise_id in katalog
            for e in stand_fuer(item, uebung_fuer(item), frisch=True).alle_offenen
        ]

    def nachtrag_schliessen() -> None:
        with zur_zeit():
            for e in nachtrag_offene():
                state.sitzungen.eintrag_schliessen(e.id)

    def nachtrag_beenden() -> None:
        nachtrag_schliessen()
        if nachtrag is not None:
            nachtrag.verlassen()

    async def nachtrag_fertig() -> None:
        nachtrag_beenden()
        ansicht = ansicht_halter[0] if ansicht_halter else None
        await page.push_route(zurueck_ziel(page, ansicht) if ansicht in page.views else fertig)

    aktionen: list[ft.Control]
    if nachtrag is not None:
        nachtrag.schliessen = nachtrag_schliessen
        nachtrag.auffrischen = auffrischen
        aktionen = [hilfe_knopf(page), ft.TextButton("Fertig", on_click=nachtrag_fertig)]
    elif einzel:
        aktionen = [timer_knopf(page, state, "plan"), hilfe_knopf(page)]
    else:
        aktionen = [
            *([] if bearbeiten else [timer_knopf(page, state, "plan")]),
            hilfe_knopf(page),
            ft.IconButton(
                ft.Icons.CHECK if bearbeiten else ft.Icons.EDIT_OUTLINED,
                tooltip="Fertig" if bearbeiten else "Plan bearbeiten",
                on_click=modus_wechseln,
            ),
        ]

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(nachtrag.titel if nachtrag is not None else plan.name),
            actions=aktionen,
        ),
        padding=0,
        controls=[sicher(ft.Column(expand=True, spacing=0, controls=[liste]))],
    )
    ansicht_halter.append(ansicht)
    if nachtrag is not None:
        # Zurück wie „Fertig“: Was offen ist, wird geschlossen (`components/zurueck.py`)
        return zurueck_speichert(
            page, ansicht, geaendert=lambda: True, speichern=nachtrag_beenden, meldung=""
        )
    return ansicht


#: `einzel_plan` kommt aus `core.plaene` und bleibt hier erreichbar (`app.py`, Tests)
__all__ = ["Nachtrag", "einzel_plan", "hauptfeld", "plan_view", "ziel_text"]


def _knopf_legende() -> ft.Control:
    """Was die Knöpfe einer Planübung tun — im Plan und bei der Einzelübung derselbe Text."""
    return ft.Text(
        "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · Uhr = Zeit stoppen · "
        "+Zahl = Satz anhängen · Eintragen = Sätze × Wert · Notiz = ins Tagebuch · "
        "Etikett = Variante · i = Parameter herholen",
        size=11,
        opacity=0.55,
    )
