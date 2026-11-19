"""Der Reiter **„Ablauf“** im Plan-Editor — Workouts zeichnen (Ben, 8.11.2026,
`docs/plan_verzweigungen.md` §8, Skizzen Reihe E; überarbeitet nach dem ersten Test am Abend).

Ein Plan ist eine **Liste** (frei abhaken, keine Bedingungen) oder ein **Workout** — und jedes
Workout hat diesen Reiter (Ben, 10.11.2026: Workout = Ablauf). Ohne eigene Zeichnung folgt der
Ablauf der Liste (`core.ablauf.folgt_der_liste`). Der Schalter steht im Reiter „Plan“
(`modus_zeile`); erst „Workout“
bringt den dritten Reiter. Route ``<Plan bearbeiten>/ablauf``.

Die Seite **scrollt nicht** — die Zeichnung füllt den Platz unter der Palette (in einer scrollenden
Seite gewönne das senkrechte Scrollen gegen das Schieben der Zeichnung). Sie wird **einmal
gebaut**: bei Änderungen tauscht sie nur Inhalte, so bleiben Zoom und Lage der Zeichnung stehen;
die Knoten liegen fest, bis jemand **„Neu anordnen“** tippt (dann richtet sich auch die Ansicht
neu aus — Ben: „Ansicht neu ausrichten nur mit dem Button“).

- **Palette**: ein **Vorrat an Übungen** (Ben, 16.11.2026) — eine Kachel je Übung, „2×“, „3×“,
  wenn sie mehrfach im Plan steht, „frei“, solange keine ihrer Planübungen im Bild ist. **Zur
  Wahl stehen alle Übungen** (Ben, 17.11.2026: „Ersetze das Suchfeld und das Plus … durch die
  Übungen aller Kataloge und den Filter (dort, wo das Plus steht), so dass dieser Bereich so
  wirkt wie die View, wenn man jetzt das Plus drückt“): zuerst die des Plans, hinter einem
  Strich der übrige Katalog — Suchfeld und Filter (Typ · Region · Paket,
  `components/uebungsfilter.FilterLeiste`, derselbe Stand wie in „Übung hinzufügen“) wirken
  auf beide; höchstens `KACHELN_HOECHSTENS` Kacheln, dahinter „+ n weitere“. Ziehen oder Tippen
  setzt eine **Planübung** dieser Übung ins Bild: zuerst eine freie; gibt es keine — oder
  steht die Übung noch gar nicht im Plan —, entsteht eine neue Planübung am Ende der Liste
  (`core.ablauf.vorrat`). **Eine Kachel bringt immer einen neuen Knoten** (Ben, 16.11.2026:
  „Ich brauche das einheitlich, neue Übung erstellen“) — hinter den gewählten, **auf eine
  Übung im Bild gezogen** hinter diese, oder auf „Start“. Nach dem Antippen ist der neue Knoten
  gewählt: Kachel für Kachel entsteht eine Kette. Rechts neben der Reihe steht fest die Kachel
  **„Frage“** — eine Frage hinter die gewählte bzw. getroffene Übung. Im Bild ist jede
  Planübung ein eigener Knoten mit ihrer Nummer (Frage 5: die Stelle in der Liste, ein Alias
  der festen ID). „i“ erklärt alles Übrige. Waagerecht scrollt die Palette, nach unten zieht
  man eine Kachel ins Bild.
- **Im Bild bedienen** (Ben, 16.11.2026: „Alles, was sich auslagern lässt vom Routingmenü in
  die Grafik, wird ausgelagert … möglichst ohne die Blätter schon viel machen“;
  `components/ablaufbild.py`):
  - **Ziehen verbindet:** Jede Übung und jede Frage hat unter sich **ihren Punkt**. Auf eine
    andere gezogen: ein Weg dorthin; auf die eigene: noch einmal; auf **„Ende“** oder
    **„◀ zurück“** — die zwei Ziele stehen am unteren Rand, solange gezogen wird. Von **„Start“**
    auf eine Übung gezogen: Sie ist der Start. Was daraus wird, rechnet
    `core.ablauf.verbinden`.
  - **Tippen** wählt: eine Übung (die nächste Kachel kommt dahinter), den **Punkt eines Wegs**
    (seine **Leiste** steht unter dem Bild: Auslöser, Zahl, Pflicht, „Mehr …“ →
    `components/wege_form.weg_leiste`; jede Änderung speichert sofort), den **Abzweig** einer
    Übung mit mehreren Wegen oder den Punkt einer Übung ohne Weg (das Blatt mit allen Wegen).
  - **Gedrückt halten** öffnet das **Menü an der Übung** — am Ort, als Karte in der Fläche:
    Übung einstellen, Beiname, nur ihren Weg zeigen, Als Start, Aus dem Ablauf nehmen (fragt:
    Lücke schließen oder Nachfolgereihe — die Übung bleibt in der Palette; aus dem Plan nimmt
    sie dort Gedrückthalten); an einer Frage: ändern, löschen.
- **Unter dem Bild** stehen die Leiste des gewählten Wegs bzw. eine Zeile zur gewählten Übung
  oder zu den Gesten, darunter **Neu anordnen**, **Pfad abspielen**, Hinweise.
- **Leeren heißt leer** (Ben, 16.11.2026): Wer alle Übungen aus dem Bild nimmt, sieht „Start“
  und einen leeren Platz — nichts setzt sich von selbst wieder hinein
  (`core.ablauf.Ablauf.ohne_start`). „Wie die Liste“ unter dem leeren Bild holt die Kette der
  Liste zurück.
- **Den Start setzt die Person** (Ben, 16.11.2026: „Start wird selbst verbunden … Wenn was
  fehlt, kommt eine Fehlermeldung, dass der Plan nachkorrigiert werden muss“): Fällt die
  Startübung weg, rückt nichts nach. Über dem Bild steht die rote Karte
  (`core.ablauf.START_FEHLT`); „Start“ auf eine Übung ziehen, „Als Start“ in ihrem Menü oder
  der Knopf **„Als Start“** unter dem Bild (an der gewählten Übung, solange der Start fehlt).

Gespeichert wird sofort (`ablauf_speichern`): der Ablauf und, gespiegelt, die Hauptwege als
Bedingungen der Planübungen — so stimmt auch „Der Reihe nach“.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core import medien_stellen as ms
from trainingsapp.core.ablauf import Ablauf, Frage, Kante
from trainingsapp.core.models import Exercise, Media, Plan
from trainingsapp.core.standards import eigenes
from trainingsapp.core.uebung_timer import timer_fuer
from trainingsapp.core.uebungsfilter import paket_wahl
from trainingsapp.ui.components import ablaufbild as abbild
from trainingsapp.ui.components import medien_stellen
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.plan_reiter import plan_reiter
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.uebungsfilter import FilterLeiste
from trainingsapp.ui.components.wege_form import (
    WegMedien,
    ablage_schluessel,
    stuecke_abholen,
    weg_leiste,
    wege_karte,
    ziel_name,
)
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf

LINEAR, VERZWEIGT = "linear", "verzweigt"
#: Was die Kachel „Frage“ rechts neben der Leiste trägt (``data`` ihres Draggable) — keine Übung
FRAGE_KACHEL = "__frage__"
#: So viele Kacheln zeigt die Leiste höchstens (die Übungen des Plans immer alle) — dahinter
#: steht „+ n weitere“: Suche und Filter engen ein (Ben, 17.11.2026: der ganze Katalog)
KACHELN_HOECHSTENS = 40
#: Luft über jeder Kachel der Leiste: Die Marke „2×“ ragt über ihr Bild hinaus
KACHEL_OBEN = ft.Padding.only(top=6)
#: Unter dem Bild, solange nichts gewählt ist: die Gesten
GESTEN = (
    "Zieh den Punkt unter einer Übung auf eine andere: ein Weg — auf dieselbe: noch einmal. "
    "Eine Kachel von oben auf eine Übung: eine neue dahinter. Tipp auf einen Punkt: den Weg "
    "einstellen. Gedrückt halten: Menü."
)
#: … und neben dem Namen der gewählten Übung
GEWAEHLT = "Kachel oben antippen: neue Übung dahinter · gedrückt halten: Menü"
NUR_IHR_WEG = "Nur ihren Weg zeigen"
#: Liegt der Finger beim Gedrückthalten tiefer als dieser Anteil der Seitenhöhe, geht das Menü
#: an der Übung nach oben auf — das Bild füllt etwa das untere Drittel bis zwei Drittel der
#: Seite, seine Mitte liegt bei gut der Hälfte
MENUE_NACH_OBEN_AB = 0.56


# -- Gemeinsam mit „Plan“ und „Im Plan einstellen“ ------------------------------------------------


def knoten_namen(state: AppState, plan: Plan) -> dict[str, str]:
    """Jeder Knoten mit Nummer: „3 · Planke“ (mit Beiname „3 · Planke · leicht“), Fragen „? · …“
    — in Planfolge, Fragen dahinter."""
    nummer = ab.nummern([it.id for it in plan.items])
    out: dict[str, str] = {}
    for it in plan.items:
        u = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
        name = u.name if u is not None else "?"
        out[it.id] = f"{nummer[it.id]} · {name}" + (f" · {it.beiname}" if it.beiname else "")
    out.update({f.id: f"? · {f.text}" for f in plan.ablauf.fragen})
    return out


def fehlende_namen(state: AppState, plan: Plan) -> dict[str, str]:
    """Wie die Planübungen heißen, auf die der Ablauf zeigt, die es gerade aber nicht gibt
    (`core.ablauf.fehlende`: Übung im Papierkorb, Paket ausgeschaltet) — gelesen aus dem Plan
    mit seinen verborgenen Planübungen. Eine ID, zu der es gar keine Planübung mehr gibt,
    fehlt hier."""
    fehlt = ab.fehlende(plan.ablauf, [it.id for it in plan.items])
    if not fehlt:
        return {}
    voll = state.plaene.laden(plan.id, mit_verborgenen=True)
    namen: dict[str, str] = {}
    for it in voll.items if voll is not None else []:
        if it.id in fehlt:
            u = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
            namen[it.id] = u.name if u is not None else "Übung"
    return namen


def plan_warnungen(state: AppState, plan: Plan) -> list[str]:
    """`core.ablauf.warnungen` zu diesem Plan — die fehlenden Übungen beim Namen."""
    namen = {**knoten_namen(state, plan), **fehlende_namen(state, plan)}
    return ab.warnungen(plan.ablauf, [it.id for it in plan.items], namen)


def reparatur_knoepfe(
    page: Any, state: AppState, plan: Plan, danach: Callable[[], Any]
) -> list[ft.Control]:
    """Was einen **unvollständigen** Ablauf repariert (Ben, 16.11.2026: „Wenn Plan
    unvollständig kann er nicht durchgeführt werden, bis das repariert ist“): je fehlender
    Übung ein Knopf, der sie aus dem Plan nimmt — mit Rückfrage; ihre Wege fallen mit ihr weg.
    Zurückholen lässt sie sich im Papierkorb bzw. mit ihrem Paket. Leer, wenn nichts fehlt."""
    ids = [it.id for it in plan.items]
    fehlt = ab.fehlende(plan.ablauf, ids)
    if not fehlt:
        return []
    namen = fehlende_namen(state, plan)

    def fragen(item_id: str, name: str) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            nachher = Nachher()
            dialog: ft.AlertDialog

            def entfernen(_e: Any = None) -> None:
                state.plaene.uebung_entfernen(item_id)
                nachher.danach(danach)
                schliessen(dialog)

            dialog = ft.AlertDialog(
                title=ft.Text(f"„{name}“ aus dem Plan nehmen?"),
                content=ft.Text(
                    "Die Übung ist gerade nicht verfügbar (Papierkorb oder ausgeschaltetes "
                    "Paket). Ihre Wege im Ablauf fallen weg. Einträge im Tagebuch bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                    ft.TextButton(
                        "Aus dem Plan nehmen",
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                        on_click=entfernen,
                    ),
                ],
                on_dismiss=nachher.bei_schliessen,
            )
            with contextlib.suppress(Exception):
                page.show_dialog(dialog)

        return handler

    def aufraeumen(_e: Any = None) -> None:
        # Wege zu Planübungen, die es gar nicht mehr gibt: Das Speichern bereinigt sie
        jetzt = state.plaene.laden(plan.id)
        if jetzt is not None:
            ablauf_speichern(state, plan.id, jetzt.ablauf)
        danach()

    knoepfe: list[ft.Control] = [
        ft.TextButton(
            f"„{namen[i]}“ aus dem Plan nehmen",
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=fragen(i, namen[i]),
            data=("reparatur", i),
        )
        for i in fehlt
        if i in namen
    ]
    if any(i not in namen for i in fehlt):
        knoepfe.append(
            ft.TextButton(
                "Wege zu fehlenden Übungen entfernen",
                icon=ft.Icons.CLEANING_SERVICES_OUTLINED,
                on_click=aufraeumen,
                data=("reparatur", ""),
            )
        )
    return knoepfe


def ablauf_zusammenfassung(plan: Plan) -> str:
    """Was unter dem Schalter steht: Liste · Workout, das der Liste folgt · eigener Ablauf
    („5 Wege · 2 bei Bedarf · 1 Frage“)."""
    if not plan.ablauf.an:
        return (
            "Liste: jede Übung ist frei, du hakst ab, was du machst — ohne Bedingungen. "
            "„Workout“ führt Schritt für Schritt durch den Plan."
        )
    ids = [it.id for it in plan.items]
    if ab.folgt_der_liste(plan.ablauf, [(it.id, it.bedingung) for it in plan.items]):
        return (
            "Workout: Übung für Übung in der Reihenfolge der Liste. Wann es weitergeht und "
            "wohin sonst, stellst du im Reiter „Ablauf“ ein."
        )
    if ab.fehlende(plan.ablauf, ids):
        # eine Übung des Ablaufs fehlt — was zu tun ist, sagt die Warnung darunter
        return "Workout mit eigenem Ablauf — unvollständig."
    if ab.ohne_start_text(plan.ablauf, ids):
        # geleert (Ben, 16.11.2026) — was zu tun ist, sagt die Warnung darunter
        return "Workout mit eigenem Ablauf — noch ohne Start."
    teile = [f"{len(plan.ablauf.kanten)} Wege"]
    if n := len(ab.bedarf(plan.ablauf, ids)):
        teile.append(f"{n} bei Bedarf")
    if plan.ablauf.fragen:
        f = len(plan.ablauf.fragen)
        teile.append(f"{f} Frage" if f == 1 else f"{f} Fragen")
    return "Workout mit eigenem Ablauf: " + " · ".join(teile) + " — im Reiter „Ablauf“."


def _alle_planuebungen(state: AppState, plan_id: str) -> list[str]:
    """Die IDs aller Planübungen — auch der gerade verborgenen (Übung im Papierkorb, Paket
    deaktiviert). Gegen sie wird der Ablauf bereinigt: Wer nur gegen die sichtbaren prüft,
    löscht die Wege der verborgenen für immer, obwohl die Planübung an ihren Platz
    zurückkommt (N47)."""
    voll = state.plaene.laden(plan_id, mit_verborgenen=True)
    return [it.id for it in voll.items] if voll is not None else []


def ablauf_speichern(state: AppState, plan_id: str, ablauf: Ablauf) -> None:
    """Speichert den Ablauf und spiegelt die Hauptwege in die Bedingungen der Planübungen (P108:
    dieselben Einstellungen bei Übung und Ablauf) — so bleibt ein Ablauf, der der Liste
    folgt, als solcher erkennbar (`core.ablauf.folgt_der_liste`)."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    a = ablauf.bereinigt(_alle_planuebungen(state, plan_id))
    state.plaene.ablauf_setzen(plan_id, a)
    if not a.an:
        return
    for it in p.items:
        raus = [k for k in a.von(it.id) if not k.schleife]
        if not raus:
            continue
        neu = ab.bedingung_aus_kante(raus[0], it.bedingung)
        if neu != it.bedingung:
            state.plaene.bedingung_setzen(it.id, neu)


def ablauf_einschalten(state: AppState, plan_id: str) -> None:
    """„Workout“: eine Zeichnung von früher kommt zurück (ihre Hauptwege mit den Bedingungen von
    jetzt), sonst folgt der Ablauf der Liste. Der Schalter ``workout`` am Plan geht mit."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    bedingungen = {it.id: it.bedingung for it in p.items}
    if p.ablauf.kanten and not p.ablauf.an:
        neu = ab.hauptwege_spiegeln(replace(p.ablauf, an=True), bedingungen)
        neu = neu.bereinigt(_alle_planuebungen(state, plan_id))
    else:
        neu = Ablauf(an=True)  # folgt der Liste
    state.plaene.ablauf_setzen(plan_id, neu)
    state.plaene.workout_setzen(plan_id, True, p.uebergang_hart)
    state.ablauf_lagen.pop(plan_id, None)


def ablauf_ausschalten(state: AppState, plan_id: str) -> None:
    """„Liste“: eine eigene Zeichnung bleibt gespeichert, gilt aber nicht; ein Ablauf, der nur
    der Liste folgte, wird nicht aufgehoben. Der Schalter ``workout`` geht mit."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    eigen = not ab.folgt_der_liste(p.ablauf, [(it.id, it.bedingung) for it in p.items])
    state.plaene.ablauf_setzen(plan_id, replace(p.ablauf, an=False) if eigen else Ablauf())
    state.plaene.workout_setzen(plan_id, False, p.uebergang_hart)


def modus_zeile(page: Any, state: AppState, plan: Plan) -> ft.Control:
    """Der Schalter im Reiter „Plan“: Liste oder Workout (Ben, 8.11.2026: „ein Switch-Button …
    erstellt einen dritten Reiter“; seit 10.11.2026 heißt er so, weil jedes Workout einen
    Ablauf hat), darunter die Zusammenfassung."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wert = str(e.control.selected[0]) if e.control.selected else LINEAR
        if wert == VERZWEIGT:
            ablauf_einschalten(state, plan.id)
            text = "Workout — im Reiter „Ablauf“ stehen die Wege und Bedingungen"
        else:
            ablauf_ausschalten(state, plan.id)
            text = "Liste — jede Übung ist frei, Bedingungen ruhen"
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))
        state.neu_zeichnen()

    return ft.Column(
        spacing=6,
        controls=[
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Art des Plans", size=15, weight=ft.FontWeight.W_600, expand=True),
                    hilfe_knopf(page, thema="ablauf"),
                ],
            ),
            ft.SegmentedButton(
                selected=[VERZWEIGT if plan.ablauf.an else LINEAR],
                show_selected_icon=False,
                segments=[
                    ft.Segment(
                        value=LINEAR,
                        label=ft.Text("Liste"),
                        icon=ft.Icon(ft.Icons.FORMAT_LIST_BULLETED),
                    ),
                    ft.Segment(
                        value=VERZWEIGT,
                        label=ft.Text("Workout"),
                        icon=ft.Icon(ft.Icons.PLAYLIST_PLAY),
                    ),
                ],
                on_change=gewaehlt,
            ),
            ft.Text(ablauf_zusammenfassung(plan), size=12, opacity=0.7),
            # Kann der Plan hängen bleiben, steht es auch hier (Ben, 9.11.2026)
            *(
                [warn_karte(gefahr, reparatur_knoepfe(page, state, plan, state.neu_zeichnen))]
                if (gefahr := plan_warnungen(state, plan))
                else []
            ),
        ],
    )


def entfernen_fragen(
    page: Any,
    state: AppState,
    plan_id: str,
    knoten: str,
    danach: Callable[[], Any],
    *,
    nur_ablauf: bool = False,
) -> None:
    """Eine Übung (oder Frage) aus dem Plan nehmen — steht sie mitten in einer Reihe, fragt es
    (Ben, 8.11.2026, Frage 4): **Lücke schließen** (Vorgänger mit dem Nachfolger verbinden) oder
    **mit der ganzen Nachfolgereihe** löschen (was nur über sie erreichbar ist).

    ``nur_ablauf``: „Aus dem Ablauf nehmen“ im Menü der Übung — nur aus der Zeichnung (Ben,
    9.11.2026: „wenn Übungen in einer Kette gelöscht werden, werden diese oben in der Auswahl
    komplett entfernt. Das soll nicht passieren“): Die Übung bleibt im Plan und vorn in der
    Leiste, „frei“. **Steht die Übung mehrfach im Plan** (Ben, 17.11.2026, P224: „Einerseits
    könnte eine Übung einfach gelöscht werden, wenn sie mehrfach vorhanden ist und dann
    rausgenommen wird, wenn diese aber Einstellungen hat, werden diese mitgelöscht“), geht die
    herausgenommene Planübung auch aus dem Plan — die Übung bleibt mit ihren anderen dort, die
    Kachel zählt eine weniger. Hat sie **Eigenes** (`core.standards.eigenes`: Ziel, Timer,
    Beiname, Anweisung, Medien, Marke eines Kurses), wird gefragt; die Vorgabe lässt sie frei
    im Plan („1 frei“ an der Kachel). Die letzte Planübung einer Übung bleibt immer."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    ids = [it.id for it in p.items]
    namen = knoten_namen(state, p)
    a = p.ablauf
    ist_frage = a.frage(knoten) is not None
    rein = [k for k in a.zu(knoten) if k.von != knoten]
    raus = [k for k in a.von(knoten) if not k.schleife]
    reihe = ab.nachfolgereihe(a, ids, knoten) if a.an else []
    name = namen.get(knoten, "?")
    nachher = Nachher()
    # Mit der Startübung geht der Start: Nichts rückt von selbst nach (Ben, 16.11.2026) — die
    # Meldung sagt es gleich, die Warnung über dem Bild bleibt stehen, bis einer gesetzt ist
    war_start = a.an and a.startknoten(ids) == knoten
    ohne_start = " Der Ablauf hat jetzt keinen Start." if war_start else ""
    # Herausnehmen (P224): Wie oft jede Übung noch im Plan steht — die letzte Planübung einer
    # Übung bleibt immer, „frei“. Von den mehrfach vorhandenen: was sie für sich haben
    je_id = {it.id: it for it in p.items}
    noch = Counter(it.exercise_id for it in p.items)
    eigen: dict[str, list[str]] = {}
    if nur_ablauf:
        for k in [knoten, *reihe]:
            it = je_id.get(k)
            if it is None or noch[it.exercise_id] < 2:
                continue
            u = state.uebungen.laden(it.exercise_id)
            if u is not None and (teile := eigenes(it, u)):
                eigen[k] = teile
    #: mit Eigenem: frei im Plan lassen (die Vorgabe) — oder mit löschen
    behalten = {"an": True}
    #: was dabei wirklich aus dem Plan ging — für die Meldung
    aus_dem_plan: set[str] = set()

    def bleibt(k: str) -> bool:
        """Bleibt diese Planübung beim Herausnehmen frei im Plan? Ja, solange sie die letzte
        ihrer Übung ist — und mit Eigenem, wenn die Person es behalten will."""
        it = je_id.get(k)
        if not nur_ablauf or it is None:
            return False
        return noch[it.exercise_id] < 2 or (k in eigen and behalten["an"])

    def aus_plan(k: str) -> None:
        state.plaene.uebung_entfernen(k)  # nimmt die Kanten von und zu ihr mit
        if (it := je_id.get(k)) is not None:
            noch[it.exercise_id] -= 1
        aus_dem_plan.add(k)

    def weg(k: str) -> None:
        if bleibt(k) or a.frage(k) is not None or k not in ids:
            jetzt = state.plaene.laden(plan_id)
            if jetzt is not None:
                # War sie der Start, bleibt der Start leer — nichts setzt sich von selbst
                # hinein (`Ablauf.ohne_knoten`)
                ablauf_speichern(state, plan_id, jetzt.ablauf.ohne_knoten(k))
        else:
            aus_plan(k)
        if state.ablauf_wahl.get(plan_id) == k:
            state.ablauf_wahl[plan_id] = None

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def raus_text() -> str:
        """Was mit der Übung geschah — gelesen, wenn die Wahl im Dialog feststeht."""
        if not nur_ablauf:
            return "entfernt"
        if ist_frage:
            return "aus dem Ablauf genommen"
        if knoten in aus_dem_plan:
            return "aus Ablauf und Plan genommen — die Übung steht noch im Plan"
        return "aus dem Ablauf genommen — sie bleibt im Plan"

    dialog: ft.AlertDialog
    einfach = not a.an or not ((rein and raus) or reihe)
    if einfach and knoten not in eigen:
        weg(knoten)
        melden(f"„{name}“ {raus_text()} — Einträge bleiben.{ohne_start}")
        danach()
        return

    def fertig(text: str) -> None:
        nachher.danach(danach)
        nachher.danach(lambda: melden(text))
        schliessen(dialog)

    def luecke(_e: Any = None) -> None:
        ablauf_speichern(state, plan_id, ab.luecke_schliessen(a, knoten))
        if not ist_frage and not bleibt(knoten):
            aus_plan(knoten)
        if state.ablauf_wahl.get(plan_id) == knoten:
            state.ablauf_wahl[plan_id] = None
        fertig(f"„{name}“ {raus_text()}, die Lücke ist geschlossen.{ohne_start}")

    def mit_reihe(_e: Any = None) -> None:
        for k in [knoten, *reihe]:
            weg(k)
        fertig(f"„{name}“ und {len(reihe)} danach {raus_text()} — Einträge bleiben.{ohne_start}")

    def nur(_e: Any = None) -> None:
        weg(knoten)
        fertig(f"„{name}“ {raus_text()} — Einträge bleiben.{ohne_start}")

    def mit_plan(_e: Any = None) -> None:
        behalten["an"] = False
        nur()

    def zeile(
        titel: str, unter: str, aktion: Callable[[Any], None], gefahr: bool = False
    ) -> ft.Control:
        return ft.ListTile(
            title=ft.Text(titel, color=ft.Colors.ERROR if gefahr else None),
            subtitle=ft.Text(unter, size=12),
            on_click=aktion,
            content_padding=ft.Padding.symmetric(horizontal=8),
        )

    if einfach:
        # Kein Platz in einer Reihe zu klären — nur: Was wird aus ihren eigenen Einstellungen?
        was = ", ".join(eigen[knoten])
        dialog = ft.AlertDialog(
            title=ft.Text(f"„{name}“ aus dem Ablauf nehmen"),
            content=ft.Column(
                tight=True,
                spacing=0,
                controls=[
                    ft.Text(
                        f"Die Übung steht mehrfach im Plan. Diese hat Eigenes: {was}.",
                        size=13,
                        opacity=0.8,
                        data="eigenes",
                    ),
                    zeile(
                        "Nur aus dem Ablauf", "bleibt frei im Plan — mit ihren Einstellungen", nur
                    ),
                    zeile(
                        "Auch aus dem Plan löschen",
                        "ihre Einstellungen gehen verloren — Einträge bleiben",
                        mit_plan,
                        gefahr=True,
                    ),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(dialog))],
            on_dismiss=nachher.bei_schliessen,
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)
        return

    zeilen: list[ft.Control] = []
    if rein and raus and not raus[0].zurueck:
        vorher = ", ".join(dict.fromkeys(namen.get(k.von, "?") for k in rein))
        nachfolger = "Ende" if raus[0].zum_ende else namen.get(raus[0].nach, "?")
        zeilen.append(zeile("Lücke schließen", f"{vorher} → {nachfolger} verbinden", luecke))
    if reihe:
        zeilen.append(
            zeile(
                "Mit der Nachfolgereihe herausnehmen"
                if nur_ablauf
                else "Mit der Nachfolgereihe löschen",
                "auch: " + ", ".join(namen.get(k, "?") for k in reihe),
                mit_reihe,
                gefahr=not nur_ablauf,
            )
        )
    zeilen.append(
        zeile(
            "Nur diese herausnehmen" if nur_ablauf else "Nur diese entfernen",
            "Wege hierher und weiter fallen weg",
            nur,
        )
    )
    dialog = ft.AlertDialog(
        title=ft.Text(f"„{name}“ aus dem {'Ablauf' if nur_ablauf else 'Plan'} nehmen"),
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[
                ft.Text(
                    "Sie ist der Start — danach setzt du einen neuen."
                    if war_start
                    else "Sie steht mitten in einer Reihe.",
                    size=13,
                    opacity=0.8,
                ),
                *zeilen,
                *(
                    [
                        # Mehrfach im Plan: Was nichts Eigenes hat, geht mit aus dem Plan; für
                        # den Rest ein Schalter statt einer zweiten Rückfrage — die Vorgabe
                        # lässt es stehen
                        ft.Switch(
                            label="Eigene Einstellungen behalten — frei im Plan: "
                            + ", ".join(namen.get(k, "?") for k in eigen),
                            value=True,
                            on_change=lambda e: behalten.__setitem__("an", bool(e.control.value)),
                            data="eigenes_behalten",
                        )
                    ]
                    if eigen
                    else []
                ),
            ],
        ),
        actions=[ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(dialog))],
        on_dismiss=nachher.bei_schliessen,
    )
    with contextlib.suppress(Exception):
        page.show_dialog(dialog)


def warn_karte(warnungen: list[str], knoepfe: Sequence[ft.Control] = ()) -> ft.Control:
    """Die Warnung „Der Plan kann hängen bleiben“ — im Ablauf über dem Bild, im Reiter „Plan“
    unter dem Schalter (`core.ablauf.warnungen`). ``knoepfe``: was den Plan repariert
    (`reparatur_knoepfe`) — unter den Sätzen."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=10,
        bgcolor=ft.Colors.ERROR_CONTAINER,
        data="ablauf_warnung",
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(ft.Icons.WARNING_AMBER, size=20, color=ft.Colors.ON_ERROR_CONTAINER),
                ft.Column(
                    spacing=4,
                    tight=True,
                    expand=True,
                    controls=[
                        *(
                            ft.Text(w, size=13, color=ft.Colors.ON_ERROR_CONTAINER)
                            for w in warnungen
                        ),
                        *knoepfe,
                    ],
                ),
            ],
        ),
    )


#: Was das Blatt „Frage ändern“ zu jeder Art sagt (Ben, 17.11.2026)
FRAGE_ERKLAERT: dict[str, str] = {
    ab.F_SKALA: (
        "Die Frage fragt nach einer Skala; ihre Wege gelten je für einen Bereich (0–6, 7–10). "
        "Zieh den Punkt unter der Frage auf eine Übung oder auf „Ende“ und stell am Weg ein: "
        "den Bereich, was der Plan bei dieser Antwort sagt — und ob es von selbst weitergeht "
        "oder der Weg nur vorgeschlagen wird. Eine Frage kann beides."
    ),
    ab.F_JA_NEIN: (
        "Zwei Antworten zum Antippen. Zieh den Punkt unter der Frage auf eine Übung oder auf "
        "„Ende“: Der erste Weg gilt bei „Ja“, der zweite bei „Nein“ — am Weg lässt sich das "
        "ändern, auch ob es von selbst weitergeht oder der Weg nur vorgeschlagen wird."
    ),
    ab.F_AUSWAHL: (
        "Eigene Antworten zum Antippen — genau eine, oder mehrere zum Ankreuzen. Jeder Weg der "
        "Frage gilt bei einer oder mehreren Antworten, ein Weg „jede andere“ fängt den Rest. "
        "Führen angekreuzte Antworten zu verschiedenen Wegen, wählt die Person im Workout "
        "einen davon. Mit nur einer Antwort („Weiter“) ist die Frage ein Hinweis."
    ),
}


# -- Die Ansicht -----------------------------------------------------------------------------


def ablauf_view(page: Any, state: AppState, plan: Plan, basis: str) -> ft.View:
    """Die Ansicht; ``basis`` ist die Bearbeiten-Route des Plans."""
    route = f"{basis}/ablauf"
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    # ``druck``: wo der Finger beim letzten Gedrückthalten lag (Anteil der Seitenhöhe)
    lokal: dict[str, Any] = {"suche": "", "druck": 0.0}
    vernebelt = state.ablauf_vernebelt.setdefault(plan.id, set())
    lagen: dict[str, Any] = state.ablauf_lagen.setdefault(plan.id, {})

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def frisch() -> Plan:
        return state.plaene.laden(plan.id) or plan

    def speichern(a: Ablauf) -> None:
        ablauf_speichern(state, plan.id, a)

    # Ein Stück, das Kamera, Rekorder oder Fotoauswahl für einen Weg bereitgelegt haben (Ben,
    # 19.11.2026, `wege_form.stuecke_abholen`), hängt jetzt an seiner Kante
    _vorher = frisch().ablauf
    if (_mit := stuecke_abholen(state, plan.id, _vorher)) != _vorher:
        speichern(_mit)
    medien_stellen.abholen(state, frisch())  # … und was für eine Stelle einer Übung wartet

    def plan_stuecke() -> list[tuple[Media, str]]:
        """Die Stücke dieses Plans und seiner Planübungen — vorn in „aus vorhandenen Medien“."""
        p = frisch()
        return [
            *((m, f"Plan {p.name}") for m in p.media),
            *((m, f"{p.name} · Planübung") for it in p.items for m in it.media),
        ]

    def gewaehlt() -> str | None:
        return state.ablauf_wahl.get(plan.id)

    def weg_wahl(p: Plan) -> tuple[Kante, int] | None:
        """Der gewählte Weg (sein Punkt im Bild wurde angetippt) und seine Stelle unter den
        Wegen seiner Übung (0 = Hauptweg) — ``None``, wenn keiner gewählt ist oder es ihn
        nicht mehr gibt (dann fällt die Wahl weg)."""
        paar = state.ablauf_weg.get(plan.id)
        if paar is None:
            return None
        for n, k in enumerate(p.ablauf.von(paar[0])):
            if k.nach == paar[1]:
                return k, n
        state.ablauf_weg[plan.id] = None
        return None

    def menue_zu() -> None:
        """Das Menü an einer Übung ist zu — gezeichnet wird danach."""
        state.ablauf_menue[plan.id] = None

    # -- Palette ------------------------------------------------------------------------------
    # Oben bündig — Namen brechen verschieden um; `KACHEL_OBEN` lässt Platz für „2×“
    reihe = ft.Row(
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    def treffer() -> list[Exercise]:
        """Was Suche und Filter aus **allen** Übungen übrig lassen — wie in „Übung hinzufügen“
        (`views/plan_hinzufuegen.py`), in der Reihenfolge des Katalogs."""
        return [
            u for u in state.uebungen.suchen(lokal["suche"]) if state.hinzufuegen_filter.passt(u)
        ]

    def palette_zeigen() -> None:
        palette_fuellen(frisch())
        with contextlib.suppress(Exception):
            page.update()

    def gesucht(e: ft.Event[ft.TextField]) -> None:
        lokal["suche"] = (e.control.value or "").strip()
        palette_zeigen()

    #: Was `suchen` liefern kann — eine Übung des Plans außerhalb davon (archiviert, ihr Paket
    #: ausgeschaltet) bleibt in der Leiste, solange Name und Filter passen
    aktive = state.uebungen.alle()
    aktiv = {u.id for u in aktive}
    # Typ · Region · Paket wie im Katalog und in „Übung hinzufügen“ — derselbe Stand
    # (`AppState.hinzufuegen_filter`): Was dort gewählt ist, wirkt auch hier
    leiste = FilterLeiste(
        page,
        state.hinzufuegen_filter,
        state.uebungen.typen(),
        state.uebungen.regionen(),
        paket_wahl(aktive, [pk for pk, _ in state.pakete.alle()]),
        on_change=palette_zeigen,
        zaehlen=lambda: len(palette_wahl(frisch())[0]),
    )
    leiste.labels.padding = None  # die Ansicht hat ihren Rand schon
    suchzeile = leiste.suchzeile(
        ft.TextField(
            hint_text="Übung suchen",
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=gesucht,
        )
    )
    suchzeile.controls.append(hilfe_knopf(page, thema="ablauf"))
    # Die Kachel „Frage“ steht fest rechts neben der Reihe — hinter dem ganzen Katalog fände
    # sie niemand (einmal gebaut: Die Reihe daneben tauscht nur ihre Kacheln)
    frage_platz = ft.Container()
    palette = ft.Column(
        spacing=6,
        controls=[
            suchzeile,
            leiste.labels,  # nur, wenn ein Filter wirkt
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[reihe, frage_platz],
            ),
        ],
    )

    def vorrat_jetzt(p: Plan) -> dict[str, ab.Vorrat]:
        """Die Übungen des Plans mit ihren Planübungen — was die Leiste zeigt
        (`core.ablauf.vorrat`)."""
        return {
            v.uebung: v for v in ab.vorrat(p.ablauf, [(it.id, it.exercise_id) for it in p.items])
        }

    def palette_wahl(p: Plan) -> tuple[list[tuple[Exercise, ab.Vorrat | None]], int]:
        """Was Suche und Filter übrig lassen, in der Reihenfolge der Leiste: **zuerst die
        Übungen des Plans** (mit ihrem `Vorrat`), dann der übrige Katalog (``None``) — und wie
        viele davon zum Plan gehören."""
        gefunden = treffer()
        for u in gefunden:
            katalog.setdefault(u.id, u)
        ids = {u.id for u in gefunden}
        suche = lokal["suche"].casefold()
        wahl: list[tuple[Exercise, ab.Vorrat | None]] = []
        im_plan = vorrat_jetzt(p)
        for v in im_plan.values():
            im = katalog.get(v.uebung)
            if im is None:
                continue
            abseits = (
                im.id not in aktiv
                and (not suche or suche in im.name.casefold())
                and state.hinzufuegen_filter.passt(im)
            )
            if im.id in ids or abseits:
                wahl.append((im, v))
        n_plan = len(wahl)
        wahl.extend((u, None) for u in gefunden if u.id not in im_plan)
        return wahl, n_plan

    def kachel(u: Exercise, v: ab.Vorrat | None, beiname: dict[str, str]) -> ft.Control:
        """Die Kachel einer Übung — ``v``: ihr Vorrat im Plan, ``None``, wenn sie (noch) nicht
        im Plan steht: dann legt Tippen oder Ziehen ihre erste Planübung an (`ins_bild`)."""
        frei = v is not None and v.ganz_frei
        # Der Beiname gehört der Planübung: an der Kachel nur, solange es genau eine gibt —
        # sonst steht er am Knoten im Bild
        zusatz = beiname.get(v.planuebungen[0], "") if v is not None and v.anzahl == 1 else ""
        bild = ft.Stack(
            width=56,
            height=56,
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                ft.Container(
                    width=56,
                    height=56,
                    border_radius=12,
                    # Im Plan: gefüllt; aus dem Katalog: nur umrandet — so sieht man, was
                    # schon da ist
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if v is not None else None,
                    border=ft.Border.all(2, ft.Colors.OUTLINE)
                    if frei
                    else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
                    if v is None
                    else None,
                    alignment=ft.Alignment.CENTER,
                    content=uebungsbild(
                        state, u.icon_key, u.image_path, groesse=30, medien=u.media
                    ),
                ),
                *(
                    [
                        ft.Container(
                            right=-6,
                            top=-6,
                            height=20,
                            padding=ft.Padding.symmetric(horizontal=5),
                            border_radius=10,
                            bgcolor=ft.Colors.PRIMARY,
                            alignment=ft.Alignment.CENTER,
                            data=("mehrfach", u.id),
                            content=ft.Text(
                                f"{v.anzahl}×",
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ON_PRIMARY,
                            ),
                        )
                    ]
                    if v is not None and v.anzahl > 1
                    else []
                ),
            ],
        )
        return ft.Draggable(
            group=abbild.GRUPPE_KACHEL,
            # die Übung, nicht eine Planübung — welche ins Bild kommt, entscheidet sich
            # beim Ablegen (`ins_bild`)
            data=u.id,
            # Waagerecht scrollt die Palette, nach unten greift man die Übung
            affinity=ft.Axis.VERTICAL,
            content=ft.Container(
                width=70,
                padding=KACHEL_OBEN,
                on_click=lambda _e, i=u.id: palette_getippt(i),
                # Gedrückt halten nimmt sie aus dem Plan (Ben, 9.11.2026) — mit Rückfrage;
                # nur, wenn sie dort steht
                on_long_press=(lambda _e, i=u.id: aus_dem_plan(i)) if v is not None else None,
                tooltip="Tippen oder auf eine Übung im Bild ziehen: in den Ablauf · "
                "gedrückt halten: aus dem Plan"
                if v is not None
                else "Tippen oder auf eine Übung im Bild ziehen: kommt in den Plan und in "
                "den Ablauf",
                content=ft.Column(
                    spacing=3,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        bild,
                        ft.Text(
                            u.name + (f" · {zusatz}" if zusatz else ""),
                            size=10,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=2,
                            width=68,
                        ),
                        # „frei“: keine ihrer Planübungen steht im Bild; „1 frei“: eine von
                        # mehreren nicht — die Kachel setzt sie zuerst wieder ein (P224)
                        *(
                            [
                                ft.Text(
                                    "frei" if frei else f"{len(v.frei)} frei",
                                    size=9,
                                    opacity=0.6,
                                    data=("frei", u.id),
                                )
                            ]
                            if v is not None and v.frei
                            else []
                        ),
                    ],
                ),
            ),
            content_feedback=ft.Container(
                width=56,
                height=56,
                border_radius=12,
                bgcolor=ft.Colors.PRIMARY,
                alignment=ft.Alignment.CENTER,
                content=uebungsbild(
                    state,
                    u.icon_key,
                    u.image_path,
                    groesse=30,
                    color=ft.Colors.ON_PRIMARY,
                    medien=u.media,
                ),
            ),
        )

    def palette_fuellen(p: Plan) -> None:
        """Eine Kachel je **Übung** (Ben, 16.11.2026): „2×“, „3×“, wenn sie mehrfach im Plan
        steht, „frei“, solange keine ihrer Planübungen im Bild ist. Die Listennummer steht nur
        noch am Knoten im Bild — dort ist jede Planübung für sich. **Zuerst die Übungen des
        Plans, hinter einem Strich der übrige Katalog** (Ben, 17.11.2026) — beides, soweit
        Suche und Filter es lassen; der Katalog nur, bis `KACHELN_HOECHSTENS` Kacheln stehen."""
        wahl, n_plan = palette_wahl(p)
        beiname = {it.id: it.beiname for it in p.items}
        gezeigt = wahl[: max(n_plan, KACHELN_HOECHSTENS)]
        kacheln: list[ft.Control] = []
        for n, (u, v) in enumerate(gezeigt):
            if n == n_plan and n_plan:
                kacheln.append(
                    ft.Container(
                        width=1,
                        height=56,
                        margin=ft.Margin.only(top=KACHEL_OBEN.top),
                        bgcolor=ft.Colors.OUTLINE_VARIANT,
                        data=("palette_strich",),
                    )
                )
            kacheln.append(kachel(u, v, beiname))
        if rest := len(wahl) - len(gezeigt):
            kacheln.append(
                ft.Container(
                    width=70,
                    height=56,
                    margin=ft.Margin.only(top=KACHEL_OBEN.top),
                    alignment=ft.Alignment.CENTER,
                    data=("palette_weitere", rest),
                    content=ft.Text(
                        f"+ {rest} weitere — Suche oder Filter",
                        size=10,
                        opacity=0.65,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            )
        if not kacheln:
            kacheln.append(
                ft.Container(
                    height=56,
                    margin=ft.Margin.only(top=KACHEL_OBEN.top),
                    alignment=ft.Alignment.CENTER_LEFT,
                    content=ft.Text("Keine Übung passt zu Suche und Filter.", size=12, opacity=0.6),
                )
            )
        reihe.controls = kacheln

    def frage_kachel() -> ft.Control:
        """Die Kachel **„Frage“** fest rechts neben der Leiste (vorher an ihrem Ende, davor
        „Routing → Frage dahinter“): antippen — mit gewählter Übung im Bild — oder auf eine
        Übung ziehen setzt eine Frage dahinter; danach öffnet ihr Blatt."""

        def bild(flaeche: str, zeichen: str) -> ft.Control:
            return ft.Container(
                width=56,
                height=56,
                border_radius=12,
                bgcolor=flaeche,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(ft.Icons.HELP_OUTLINE, size=28, color=zeichen),
            )

        return ft.Draggable(
            group=abbild.GRUPPE_KACHEL,
            data=FRAGE_KACHEL,
            affinity=ft.Axis.VERTICAL,
            content=ft.Container(
                width=70,
                padding=KACHEL_OBEN,
                on_click=lambda _e: frage_getippt(),
                tooltip="Tippen oder auf eine Übung im Bild ziehen: eine Frage dahinter",
                content=ft.Column(
                    spacing=3,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        bild(ft.Colors.SECONDARY_CONTAINER, ft.Colors.SECONDARY),
                        ft.Text("Frage", size=10, text_align=ft.TextAlign.CENTER, width=68),
                    ],
                ),
            ),
            content_feedback=bild(ft.Colors.SECONDARY, ft.Colors.ON_SECONDARY),
        )

    frage_platz.content = frage_kachel()

    def aus_dem_plan(uebung_id: str) -> None:
        """Gedrückt halten an einer Kachel: **eine** Planübung dieser Übung aus dem Plan nehmen
        — die zuletzt hinzugekommene, eine freie zuerst (`Vorrat.letzte`); der Dialog nennt sie
        mit ihrer Nummer. Steht sie mitten in einer Reihe, fragt `entfernen_fragen` nach Lücke
        oder Nachfolgereihe, sonst eine einfache Rückfrage. Einträge bleiben."""
        p = frisch()
        v = vorrat_jetzt(p).get(uebung_id)
        if v is None:
            return
        item_id = v.letzte
        a = p.ablauf
        if a.an and [k for k in a.zu(item_id) if k.von != item_id] and a.von(item_id):
            entfernen_fragen(page, state, plan.id, item_id, neu_zeichnen)
            return
        name = knoten_namen(state, p).get(item_id, "?")
        nachher = Nachher()
        dialog: ft.AlertDialog

        def entfernen(_e: Any = None) -> None:
            state.plaene.uebung_entfernen(item_id)
            if state.ablauf_wahl.get(plan.id) == item_id:
                state.ablauf_wahl[plan.id] = None
            nachher.danach(neu_zeichnen)
            schliessen(dialog)

        dialog = ft.AlertDialog(
            title=ft.Text(f"„{name}“ aus dem Plan entfernen?"),
            content=ft.Text(
                "Ihre Wege im Ablauf fallen weg. Einträge im Tagebuch bleiben."
                + (f" Die Übung steht danach noch {v.anzahl - 1}× im Plan." if v.anzahl > 1 else "")
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                ft.TextButton(
                    "Entfernen", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=entfernen
                ),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)

    def ins_bild(uebung_id: str, aendern: Callable[[Ablauf, str], Ablauf]) -> tuple[str, bool]:
        """Eine Kachel kommt ins Bild (Ben, 16.11.2026): zuerst eine Planübung dieser Übung, die
        noch nicht dort steht; gibt es keine freie, entsteht eine **neue Planübung derselben
        Übung** am Ende der Liste (sie folgt der Übung, P79) — so muss niemand die Übung vorher
        zwei-, dreimal in den Plan laden. **Steht die Übung noch nicht im Plan** (eine Kachel
        aus dem Katalog; Ben, 17.11.2026), ist es ihre erste Planübung. ``aendern(ablauf,
        planuebung)`` setzt sie ein. Zurück: die Planübung und ob sie neu ist; ``("", False)``,
        wenn es die Übung nicht gibt.

        Der Ablauf, in den sie kommt, ist der von **vor** dem Hinzufügen: Folgte er der Liste,
        hängt die neue Planübung nicht von selbst hinten an — sie kommt dorthin, wohin die
        Person sie gesetzt hat."""
        p = frisch()
        v = vorrat_jetzt(p).get(uebung_id)
        if v is None and uebung_id not in katalog:
            return "", False
        item_id = v.naechste if v is not None else None
        neu = item_id is None
        if item_id is None:
            item_id = state.plaene.uebung_hinzufuegen(plan.id, uebung_id).id
        speichern(aendern(p.ablauf, item_id))
        return item_id, neu

    def dahinter(von: str, uebung_id: str) -> None:
        """Eine Kachel kommt **hinter** den Knoten ``von`` — angetippt (mit gewähltem Knoten)
        oder auf ihn gezogen: immer ein **neuer Knoten** (`ins_bild`) mit einem Weg dorthin,
        nie ein Weg zu einem, der schon im Bild steht (Ben, 16.11.2026: „Ich brauche das
        einheitlich, neue Übung erstellen“). **Die Wahl geht auf den neuen Knoten** — Kachel für
        Kachel entsteht so eine Kette; für einen Abzweig wählt man die Übung noch einmal oder
        zieht die Kachel auf sie."""
        # aus einer Frage mit Antworten: gleich mit der nächsten freien Antwort (`weg_neu`)
        item_id, neu = ins_bild(uebung_id, lambda a, i: a.mit_kante(ab.weg_neu(a, von, i)))
        if not item_id:
            return
        namen = knoten_namen(state, frisch())
        state.ablauf_wahl[plan.id] = item_id
        state.ablauf_weg[plan.id] = None
        melden(
            f"Weg {namen.get(von, '?')} → {namen.get(item_id, '?')}"
            + (" — neu im Plan" if neu else "")
        )
        neu_zeichnen()

    def frage_dahinter(von: str) -> None:
        """Eine Frage hinter ``von`` — gewählt ist danach sie, ihr Blatt öffnet sich."""
        jetzt = frisch()
        f = Frage()
        neu = replace(jetzt.ablauf, fragen=(*jetzt.ablauf.fragen, f))
        speichern(neu.mit_kante(Kante(von, f.id)))
        state.ablauf_wahl[plan.id] = f.id
        state.ablauf_weg[plan.id] = None
        neu_zeichnen()
        frage_blatt(f)

    def palette_getippt(uebung_id: str) -> None:
        """Ohne Ziehen: mit gewähltem Knoten kommt die neue Übung hinter ihn (`dahinter`);
        ohne Start wird sie der Start."""
        menue_zu()
        p = frisch()
        von = gewaehlt()
        if von is not None and von in knoten_namen(state, p):
            dahinter(von, uebung_id)
            return
        if p.ablauf.startknoten([it.id for it in p.items]) is None:
            start_ablegen(uebung_id)
            return
        melden(
            "Erst eine Übung im Bild antippen — die neue kommt dahinter. Oder die Kachel auf "
            "eine Übung im Bild ziehen."
        )

    def frage_getippt() -> None:
        """Die Kachel „Frage“ angetippt: eine Frage hinter die gewählte Übung."""
        menue_zu()
        von = gewaehlt()
        if von is not None and von in knoten_namen(state, frisch()):
            frage_dahinter(von)
            return
        melden(
            "Erst eine Übung im Bild antippen — die Frage kommt dahinter. Oder die Kachel "
            "„Frage“ auf eine Übung im Bild ziehen."
        )

    # -- Zeichnung ------------------------------------------------------------------------------

    def kachel_auf(knoten: str, wert: str) -> None:
        """Eine Kachel der Leiste fällt auf einen Knoten im Bild: eine neue Übung — oder eine
        Frage — dahinter (Ben, 16.11.2026: „Slot weglassen“)."""
        menue_zu()
        if wert == FRAGE_KACHEL:
            frage_dahinter(knoten)
        else:
            dahinter(knoten, wert)

    def start_ablegen(uebung_id: str) -> None:
        """Eine Kachel auf „Start“ (oder den leeren Platz darunter): wie überall kommt ein
        **neuer Knoten** ins Bild (`ins_bild`) und wird der Start (Ben, 16.11.2026: „Ich
        brauche das einheitlich, neue Übung erstellen“). Mit dem, was schon im Bild steht,
        verbindet sich nichts von selbst — einen Knoten von dort macht „Als Start“ zum Start
        oder der Punkt von „Start“, auf ihn gezogen."""
        menue_zu()
        if uebung_id == FRAGE_KACHEL:
            melden("Eine Frage kommt hinter eine Übung — zieh sie auf eine Übung im Bild.")
            return
        item_id, neu = ins_bild(uebung_id, lambda a, i: replace(a, start=i))
        if not item_id:
            return
        state.ablauf_wahl[plan.id] = item_id
        state.ablauf_weg[plan.id] = None
        melden("Neuer Start" + (" — neu im Plan" if neu else ""))
        neu_zeichnen()

    def verbinden(von: str, nach: str) -> None:
        """Ein Punkt wurde gezogen und fiel auf ``nach`` (`components/ablaufbild`): von einer
        Übung oder Frage auf eine andere — ein Weg; auf sich selbst — noch einmal; auf „Ende“
        oder „◀ zurück“; von „Start“ auf eine Übung — der Start. Was daraus wird, rechnet
        `core.ablauf.verbinden`. Der neue Weg ist danach gewählt: Seine Leiste steht unter dem
        Bild, wann es weitergeht, lässt sich gleich einstellen."""
        menue_zu()
        p = frisch()
        namen = knoten_namen(state, p)
        neu = ab.verbinden(p.ablauf, von, nach)
        if neu is None:
            if von == ab.VOM_START:
                melden(
                    f"„{namen[nach]}“ ist schon der Start."
                    if nach in namen
                    else "„Start“ gehört auf eine Übung oder Frage."
                )
            elif von == nach and p.ablauf.frage(von) is not None:
                melden("Eine Frage führt nicht zu sich selbst.")
            else:
                # den Weg gibt es schon: seine Leiste zeigen statt eines zweiten
                state.ablauf_wahl[plan.id] = None
                state.ablauf_weg[plan.id] = (von, nach)
                melden("Diesen Weg gibt es schon.")
            neu_zeichnen()
            return
        speichern(neu)
        if von == ab.VOM_START:
            state.ablauf_wahl[plan.id] = nach
            state.ablauf_weg[plan.id] = None
            melden("Neuer Start")
        else:
            state.ablauf_wahl[plan.id] = None
            state.ablauf_weg[plan.id] = (von, nach)
        neu_zeichnen()

    def knoten_getippt(knoten: str) -> None:
        """Ein Tipp wählt die Übung (noch einmal: nimmt die Wahl zurück) — die nächste Kachel
        kommt hinter sie. Steht ein Menü offen, schließt der Tipp nur das."""
        if state.ablauf_menue.get(plan.id) is not None:
            menue_schliessen()
            return
        state.ablauf_wahl[plan.id] = None if gewaehlt() == knoten else knoten
        state.ablauf_weg[plan.id] = None
        neu_zeichnen()

    def knoten_lang(knoten: str) -> None:
        """Gedrückt halten: das **Menü an der Übung**, am Ort im Bild (Ben, 16.11.2026) —
        vorher lag hier „nur ihren Weg zeigen“, das steht jetzt im Menü."""
        state.ablauf_menue[plan.id] = knoten
        state.ablauf_wahl[plan.id] = knoten
        state.ablauf_weg[plan.id] = None
        neu_zeichnen()

    def menue_schliessen() -> None:
        menue_zu()
        neu_zeichnen()

    def abseits(p: Plan, knoten: str) -> set[str]:
        """Was nicht auf dem Weg durch ``knoten`` liegt — das wird vernebelt."""
        ids = [it.id for it in p.items]
        weg = ab.weg_durch(p.ablauf, ids, knoten)
        return {i for i in [*ids, *(f.id for f in p.ablauf.fragen)] if i not in weg}

    def nur_ihr_weg(knoten: str) -> None:
        """„Nur ihren Weg zeigen“: alles abseits des Wegs durch diese Übung wird blass — noch
        einmal (oder „Alles zeigen“) holt es zurück."""
        rest = abseits(frisch(), knoten)
        aus = vernebelt == rest
        vernebelt.clear()
        if not aus:
            vernebelt.update(rest)
        neu_zeichnen()

    def als_start(knoten: str) -> None:
        speichern(replace(frisch().ablauf, start=knoten))
        melden("Neuer Start")
        neu_zeichnen()

    def herausnehmen(knoten: str) -> None:
        # Nur aus der Zeichnung (9.11.2026) — die Übung bleibt oben in der Palette
        entfernen_fragen(page, state, plan.id, knoten, neu_zeichnen, nur_ablauf=True)

    def menue_jetzt(p: Plan) -> abbild.Menue | None:
        """Das Menü der Übung, die gedrückt gehalten wurde — was vorher in der Knopfzeile und
        unter „Routing“ stand und nicht ins Bild gewandert ist. Jeder Eintrag schließt das Menü
        zuerst: Ein Blatt oder Dialog darüber fände es sonst nach dem Schließen noch offen."""
        knoten = state.ablauf_menue.get(plan.id)
        if knoten is None or knoten not in knoten_namen(state, p):
            return None
        # Eine Übung in der unteren Hälfte des Bildes: Das Menü geht nach oben auf — nach unten
        # verschwänden seine letzten Zeilen unter dem Rand (Web-Foto 16.11.2026)
        nach_oben = lokal["druck"] > MENUE_NACH_OBEN_AB

        def dann(aktion: Callable[[], Any]) -> Callable[[], Any]:
            def handler() -> Any:
                menue_schliessen()
                return aktion()

            return handler

        frage = p.ablauf.frage(knoten)
        if frage is not None:
            return abbild.Menue(
                knoten,
                [
                    abbild.Eintrag(
                        "Frage ändern …", dann(lambda: frage_blatt(frage)), ft.Icons.EDIT_OUTLINED
                    ),
                    abbild.Eintrag(
                        "Frage löschen",
                        dann(lambda: herausnehmen(knoten)),
                        ft.Icons.DELETE_OUTLINE,
                        gefahr=True,
                    ),
                ],
                menue_schliessen,
                nach_oben,
            )
        eintraege = [
            abbild.Eintrag(
                "Übung einstellen …",
                dann(lambda: page.push_route(f"{basis}/ziel/{knoten}")),
                ft.Icons.SETTINGS_OUTLINED,
            ),
            # die vier Stellen der Übung — auch die leeren (Ben, 19.11.2026)
            abbild.Eintrag(
                "Medien …", dann(lambda: marke_getippt(knoten)), ft.Icons.MENU_BOOK_OUTLINED
            ),
            abbild.Eintrag(
                "Beiname …", dann(lambda: beiname_blatt(knoten)), ft.Icons.LABEL_OUTLINE
            ),
            abbild.Eintrag(
                "Alles zeigen" if vernebelt and vernebelt == abseits(p, knoten) else NUR_IHR_WEG,
                dann(lambda: nur_ihr_weg(knoten)),
                ft.Icons.FILTER_CENTER_FOCUS,
            ),
        ]
        if p.ablauf.startknoten([it.id for it in p.items]) != knoten:
            eintraege.append(
                abbild.Eintrag(
                    "Als Start", dann(lambda: als_start(knoten)), ft.Icons.PLAY_ARROW_OUTLINED
                )
            )
        eintraege.append(
            abbild.Eintrag(
                "Aus dem Ablauf nehmen",
                dann(lambda: herausnehmen(knoten)),
                ft.Icons.DELETE_OUTLINE,
                gefahr=True,
            )
        )
        return abbild.Menue(knoten, eintraege, menue_schliessen, nach_oben)

    def marke_getippt(knoten: str) -> None:
        """Eine Marke der Medien (an einer Kachel oder an „Start“) bzw. „Medien …“ im Menü: das
        Blatt mit den Stellen dieser Übung bzw. des Plans (`components/medien_stellen.py`)."""
        menue_zu()
        blatt = medien_stellen.stellen_blatt(
            page,
            state,
            plan.id,
            medien_stellen.PLAN if knoten == abbild.START else knoten,
            basis=basis,
            hier=route,
            neu_zeichnen=neu_zeichnen,
        )
        if blatt is not None:
            with contextlib.suppress(Exception):
                page.show_dialog(blatt)

    def marken_jetzt(p: Plan) -> dict[str, tuple[str, ...]]:
        """Je Knoten die belegten Stellen, unter `START` die des Plans."""
        marken = {it.id: ms.stellen_von(katalog.get(it.exercise_id), it).belegt for it in p.items}
        marken[abbild.START] = ms.plan_stellen(p).belegt
        return marken

    def kante_getippt(k: Kante) -> None:
        """Der Punkt eines Wegs (oder sein Etikett): Der Weg ist gewählt, seine **Leiste** steht
        unter dem Bild (Ben, 16.11.2026: „möglichst ohne die Blätter schon viel machen“) — auch
        beim einen Punkt eines eindeutigen Wegs. Noch einmal antippen nimmt die Wahl zurück."""
        menue_zu()
        paar = (k.von, k.nach)
        state.ablauf_weg[plan.id] = None if state.ablauf_weg.get(plan.id) == paar else paar
        state.ablauf_wahl[plan.id] = None
        neu_zeichnen()

    def abzweig_getippt(knoten: str) -> None:
        """Der Abzweig unter einer Übung mit mehreren Wegen — und der Punkt einer Übung ohne
        Weg: das Blatt mit allen ihren Wegen (dort „+ Weg“)."""
        menue_zu()
        state.ablauf_wahl[plan.id] = knoten
        state.ablauf_weg[plan.id] = None
        neu_zeichnen()
        wege_blatt(knoten)

    def weg_aendern(alt: Kante, neu: Kante) -> None:
        """Die Leiste hat den gewählten Weg geändert: sofort speichern, neu zeichnen."""
        speichern(frisch().ablauf.kante_ersetzen(alt, neu))
        state.ablauf_weg[plan.id] = (neu.von, neu.nach)
        neu_zeichnen()

    def weg_entfernen(alt: Kante) -> None:
        p = frisch()
        speichern(p.ablauf.ohne_kante(alt))
        state.ablauf_weg[plan.id] = None
        namen = knoten_namen(state, p)
        melden(f"Weg {namen.get(alt.von, '?')} → {ziel_name(alt, namen)} entfernt.")
        neu_zeichnen()

    def pfad_abspielen() -> None:
        p = frisch()
        if hasattr(page, "run_task"):
            pfad = ab.hauptpfad(p.ablauf, [it.id for it in p.items])
            page.run_task(abbild.abspielen, page, bild, pfad)

    def neu_anordnen(_e: Any = None) -> None:
        p = frisch()
        lagen.clear()
        lagen.update(ab.layout(p.ablauf, [it.id for it in p.items]))
        neu_zeichnen()
        if hasattr(page, "run_task"):
            with contextlib.suppress(Exception):
                page.run_task(bild.control.reset)

    def zeichnung_jetzt(p: Plan) -> abbild.Zeichnung:
        ids = [it.id for it in p.items]
        neu = ab.lagen_ergaenzen(lagen, p.ablauf, ids)
        lagen.clear()
        lagen.update(neu)
        weg_wahl(p)  # ein gewählter Weg, den es nicht mehr gibt, fällt weg
        return abbild.zeichnung(
            state,
            p.ablauf,
            p.items,
            katalog,
            lagen=lagen,
            vernebelt=sorted(vernebelt),
            gewaehlt=gewaehlt(),
            weg_gewaehlt=state.ablauf_weg.get(plan.id),
            zaehlung=state.einheiten.kanten_gezaehlt(state.profil.id, p.id) or None,
            menue=menue_jetzt(p),
            on_knoten=knoten_getippt,
            on_knoten_lang=knoten_lang,
            on_lang_ort=lambda anteil: lokal.__setitem__("druck", anteil),
            on_kante=kante_getippt,
            on_abzweig=abzweig_getippt,
            on_start=pfad_abspielen,
            on_start_ablegen=start_ablegen,
            on_verbinden=verbinden,
            on_kachel_auf=kachel_auf,
            on_ziehen=ziele.zeigen,
            marken=marken_jetzt(p),
            wege_mit_inhalt=ms.wege_mit_inhalt(p.ablauf),
            on_marke=marke_getippt,
        )

    # „Ende“ und „◀ zurück“ am unteren Rand des Bildes — nur zu sehen, während gezogen wird
    ziele = abbild.ziele(verbinden)
    erste = zeichnung_jetzt(frisch())
    flaeche = abbild.flaeche_neu(erste)
    bild = abbild.Bild(abbild.ansicht(flaeche), flaeche, erste.mitten, erste.knoten)
    rahmen = ft.Container(
        expand=True,  # die Zeichnung füllt, was unter der Palette frei ist
        border_radius=14,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        bgcolor=ft.Colors.SURFACE,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=abbild.mit_zielen(bild.control, ziele),
    )

    # -- Unter dem Bild ---------------------------------------------------------------------------

    def wie_die_liste(_e: Any = None) -> None:
        """Im leeren Bild: der Ablauf folgt wieder der Liste — Übung für Übung."""
        speichern(Ablauf(an=True))
        lagen.clear()
        melden("Der Ablauf folgt wieder der Liste.")
        neu_zeichnen()

    def leer_hinweis(p: Plan) -> list[ft.Control]:
        """Unter einem Bild ohne Start (Ben, 16.11.2026: geleert bleibt es leer): was jetzt zu
        tun ist — und, solange gar nichts im Bild steht, der Weg zurück zur Liste."""
        ganz_leer = not p.ablauf.kanten and not p.ablauf.fragen
        return [
            ft.Text(
                (
                    "Der Ablauf ist leer — tippe oben eine Übung an oder zieh sie auf „Start“."
                    if ganz_leer
                    else "Der Ablauf hat keinen Start — zieh den Punkt von „Start“ auf eine "
                    "Übung im Bild, oder tippe sie an und dann „Als Start“. Eine Kachel von "
                    "oben (antippen oder auf „Start“ ziehen) setzt eine neue Übung dorthin."
                ),
                size=12,
                opacity=0.65,
                data="ablauf_leer",
            ),
            *(
                [
                    ft.TextButton(
                        "Wie die Liste",
                        icon=ft.Icons.FORMAT_LIST_NUMBERED,
                        tooltip="Übung für Übung in der Reihenfolge der Liste",
                        on_click=wie_die_liste,
                    )
                ]
                if ganz_leer
                else []
            ),
        ]

    def unter_dem_bild(p: Plan) -> list[ft.Control]:
        """Direkt unter dem Bild: die **Leiste des gewählten Wegs** — sonst eine Zeile zur
        gewählten Übung oder, ohne Wahl, zu den Gesten. Die Knopfzeile von früher (Routing,
        Neuer Slot, Beiname, Aus dem Ablauf nehmen) ist ins Bild gewandert (Ben, 16.11.2026).
        Fehlt der Start, steht an der gewählten Übung weiter der Knopf „Als Start“."""
        namen = knoten_namen(state, p)
        ids = [it.id for it in p.items]
        wahl = weg_wahl(p)
        if wahl is not None:
            k, n = wahl
            item = next((it for it in p.items if it.id == k.von), None)
            uebung = katalog.get(item.exercise_id) if item is not None else None
            ohne = item is not None and uebung is not None and timer_fuer(uebung, p, item) is None
            return [
                weg_leiste(
                    k,
                    n,
                    namen=namen,
                    aendern=lambda neu: weg_aendern(k, neu),
                    entfernen=lambda: weg_entfernen(k),
                    mehr=lambda: wege_blatt(k.von, fokus=k.nach, allein=True),
                    ohne_timer=ohne,
                    ablauf=p.ablauf,
                )
            ]
        knoten = gewaehlt()
        kein_start = bool(ab.ohne_start_text(p.ablauf, ids))
        if knoten is None or knoten not in namen:
            if kein_start:
                return leer_hinweis(p)
            return [ft.Text(GESTEN, size=12, opacity=0.65, data="ablauf_gesten")]
        zeile: list[ft.Control] = [ft.Text(namen[knoten], size=13, weight=ft.FontWeight.W_600)]
        if kein_start:
            # Kein Start (Ben, 16.11.2026: „Start wird selbst verbunden. Wenn man möchte mit
            # dem, was schon da ist“): der Knopf steht hier, solange einer fehlt — sonst im
            # Menü der Übung
            zeile.append(
                ft.FilledTonalButton(
                    "Als Start",
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=lambda _e: als_start(knoten),
                    data="als_start",
                )
            )
        zeile.append(ft.Text(GEWAEHLT, size=12, opacity=0.65))
        return [
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=zeile,
            )
        ]

    def hinweise_zeigen(hinweise: list[str]) -> None:
        dialog: ft.AlertDialog = ft.AlertDialog(
            title=ft.Text("Hinweise zum Ablauf"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.Text(h, size=13) for h in hinweise],
            ),
            actions=[ft.TextButton("Schließen", on_click=lambda _e: schliessen(dialog))],
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)

    def alles_zeigen(_e: Any = None) -> None:
        vernebelt.clear()
        neu_zeichnen()

    def zuruecksetzen_fragen(_e: Any = None) -> None:
        """„Freischaltungen zurücksetzen …“ (P167): was eine erfüllte Pflicht in der Liste
        freigab, ist wieder gesperrt — wie ein Kurs von vorn; Einträge bleiben."""

        def ja(_e: Any = None) -> None:
            state.plaene.freischaltung_zuruecksetzen(plan.id)
            schliessen(dialog)
            neu_zeichnen()

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Freischaltungen zurücksetzen?"),
            content=ft.Text(
                "Was hinter einer Pflicht liegt, ist in der Liste wieder gesperrt, bis das Workout "
                "die Pflicht erneut erfüllt. Einträge und Messungen bleiben."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(dialog)),
                ft.FilledButton("Zurücksetzen", on_click=ja),
            ],
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)

    def freigeschaltet(p: Plan) -> bool:
        """Hat ein Workout schon ein Tor geöffnet (seit dem letzten Zurücksetzen)?"""
        tore = ab.tore(p.ablauf)
        if not tore or state.einheiten is None:
            return False
        seit = state.plaene.freischaltung_seit(p.id)
        return bool(tore & state.einheiten.tore_offen(state.profil.id, p.id, seit))

    def werkzeuge(p: Plan) -> list[ft.Control]:
        ids = [it.id for it in p.items]
        hinweise = ab.pruefung(p.ablauf, ids, knoten_namen(state, p))
        teile: list[ft.Control] = [
            ft.OutlinedButton("Neu anordnen", icon=ft.Icons.AUTO_FIX_HIGH, on_click=neu_anordnen),
            ft.TextButton(
                "Pfad abspielen",
                icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                on_click=lambda _e: pfad_abspielen(),
            ),
        ]
        if vernebelt:
            teile.append(ft.TextButton("Alles zeigen", on_click=alles_zeigen))
        if freigeschaltet(p):
            teile.append(
                ft.TextButton(
                    "Freischaltungen zurücksetzen …",
                    icon=ft.Icons.LOCK_RESET,
                    on_click=zuruecksetzen_fragen,
                )
            )
        if hinweise:
            teile.append(
                ft.TextButton(
                    f"{len(hinweise)} Hinweis" + ("e" if len(hinweise) > 1 else ""),
                    icon=ft.Icons.INFO_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.TERTIARY),
                    on_click=lambda _e: hinweise_zeigen(hinweise),
                )
            )
        return teile

    # -- Blätter ---------------------------------------------------------------------------------

    def wege_blatt(knoten: str, fokus: str | None = None, allein: bool = False) -> None:
        """Alle Wege eines Knotens auf einmal (Ben: „wenn eine Übung mehrere Folgewege hat, dann
        diese gleichzeitig einstellen können … die verschiedenen Pfade einfach scrollbar“) — das
        Formular aus „Im Plan einstellen“. Gespeichert wird beim Schließen. ``fokus``: das Ziel
        des angetippten Wegs — er steht offen, die anderen zugeklappt; ``allein``: nur er."""
        p = frisch()
        stand: dict[str, Any] = {"a": p.ablauf, "verworfen": False}
        merken: dict[str, Any] = {}
        nachher = Nachher()

        def weg_aufnehmen(i: int, art: str | None) -> None:
            """Vom Weg zur Kamera, zum Rekorder (``art``) oder in die Fotoauswahl (``None``):
            das Blatt schließt und speichert, dann geht es hinüber — beim Zurückkommen holt
            die Ansicht das Stück ab."""
            from trainingsapp.core.anhaenge import Ziel as AnhangZiel
            from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
            from trainingsapp.ui.views.anhang_hochladen import hochladen_route

            ziel_ = AnhangZiel.fuer_ablage(ablage_schluessel(plan.id, i))
            hin = (
                hochladen_route(route, ziel_) if art is None else aufnahme_route(route, ziel_, art)
            )

            async def gehen() -> None:
                await page.push_route(hin)

            nachher.danach(gehen)
            schliessen(blatt)

        namen = knoten_namen(state, p)
        item = next((it for it in p.items if it.id == knoten), None)
        uebung = katalog.get(item.exercise_id) if item is not None else None
        ohne = item is not None and uebung is not None and timer_fuer(uebung, p, item) is None
        innen = ft.Column(
            spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )
        blatt: ft.BottomSheet

        def setzen(a: Ablauf) -> None:
            stand["a"] = a

        def aufbauen() -> None:
            innen.controls = [
                ft.Text(namen.get(knoten, "?"), size=18, weight=ft.FontWeight.W_600),
                wege_karte(
                    knoten,
                    lambda: stand["a"],
                    setzen,
                    neu_innen,
                    namen=namen,
                    ohne_timer=ohne,
                    merken=merken,
                    fokus=fokus,
                    allein=allein,
                    medien=WegMedien(page, state, weg_aufnehmen, plan_stuecke),
                ),
            ]

        def neu_innen() -> None:
            aufbauen()
            with contextlib.suppress(Exception):
                innen.update()

        async def geschlossen(_e: Any = None) -> None:
            """Blätter speichern beim Schließen (CLAUDE.md) — außer nach „Abbrechen“."""
            if not stand["verworfen"] and stand["a"] != p.ablauf:
                speichern(stand["a"])
            neu_zeichnen()
            await nachher.bei_schliessen()

        def abbrechen(_e: Any = None) -> None:
            stand["verworfen"] = True
            schliessen(blatt)

        aufbauen()
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=geschlossen,
            content=blatt_spalte(
                innen,
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=abbrechen),
                            ft.FilledButton("Fertig", on_click=lambda _e: schliessen(blatt)),
                        ],
                    )
                ],
                geschaetzt=560,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def beiname_blatt(knoten: str) -> None:
        item = state.plaene.item_laden(knoten)
        if item is None:
            return
        feld = ft.TextField(value=item.beiname, label="Beiname", hint_text="2. Durchgang · leicht")
        nachher = Nachher()
        blatt: ft.BottomSheet

        def uebernehmen(_e: Any = None) -> None:
            state.plaene.beiname_setzen(knoten, feld.value or "")
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                [
                    ft.Text("Beiname", size=18, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Unterscheidet gleiche Übungen im Bild — die Nummer bleibt die Stelle in "
                        "der Liste.",
                        size=12,
                        opacity=0.7,
                    ),
                    feld,
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton("Übernehmen", on_click=uebernehmen),
                        ],
                    )
                ],
                geschaetzt=200,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def frage_blatt(f: Frage | None) -> None:
        """„Frage ändern“: der Wortlaut und **wie geantwortet wird** (Ben, 17.11.2026: „Eine
        Frage lässt bisher nur Skala von x bis y zu. Mehrfachauswahl, Ja/Nein usw. geht bisher
        nicht, wird aber gebraucht“) — Skala · Ja/Nein · Auswahl (eigene Antworten, wahlweise
        mehrere zum Ankreuzen). Die Wege der Frage ziehen mit (`core.ablauf.frage_ersetzen`)."""
        if f is None:
            return
        text = ft.TextField(value=f.text, label="Frage", hint_text="Wie fühlt es sich an?")
        lo = ft.TextField(
            value=str(f.min), label="von", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        hi = ft.TextField(
            value=str(f.max), label="bis", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        wie: dict[str, Any] = {"art": f.art, "mehrfach": f.mehrfach}
        # Je Antwort eine Zeile, einmal gebaut — ein Textfeld, das den Elternteil wechselt,
        # nähme keine Eingaben mehr an. Dazu ihr Wortlaut von vorher (für die Wege)
        zeilen: list[tuple[str, ft.TextField, ft.Row]] = []
        mitte = ft.Column(
            spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )
        nachher = Nachher()
        blatt: ft.BottomSheet

        def antwort_zeile(vorher: str) -> None:
            feld = ft.TextField(
                value=vorher,
                label="Antwort",
                dense=True,
                expand=True,
                data="frage_antwort",
            )
            zeile = ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            zeile.controls = [
                feld,
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=18,
                    tooltip="Antwort entfernen",
                    on_click=lambda _e: antwort_weg(zeile),
                    data="frage_antwort_weg",
                ),
            ]
            zeilen.append((vorher, feld, zeile))

        def antwort_weg(zeile: ft.Row) -> None:
            zeilen[:] = [z for z in zeilen if z[2] is not zeile]
            fuellen(True)

        def antwort_dazu(_e: Any = None) -> None:
            if len(zeilen) < ab.ANTWORTEN_MAX:
                antwort_zeile("")
                fuellen(True)

        def art_gewaehlt(e: Any) -> None:
            wie["art"] = e.control.selected[0] if e.control.selected else wie["art"]
            if wie["art"] == ab.F_AUSWAHL and not zeilen:
                antwort_zeile("")
                antwort_zeile("")
            fuellen(True)

        def fuellen(zeigen: bool = False) -> None:
            art = wie["art"]
            if art == ab.F_SKALA:
                teile: list[ft.Control] = [
                    ft.Row(spacing=8, controls=[lo, hi, ft.Text("Skala", size=13, opacity=0.7)])
                ]
            elif art == ab.F_JA_NEIN:
                teile = [ft.Text("Antworten: Ja · Nein", size=13, data="frage_ja_nein")]
            else:
                teile = [
                    *(z[2] for z in zeilen),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.TextButton(
                                "Antwort",
                                icon=ft.Icons.ADD,
                                disabled=len(zeilen) >= ab.ANTWORTEN_MAX,
                                on_click=antwort_dazu,
                                data="frage_antwort_dazu",
                            ),
                        ],
                    ),
                    ft.Switch(
                        label="Mehrere Antworten ankreuzen",
                        value=bool(wie["mehrfach"]),
                        on_change=lambda e: wie.__setitem__("mehrfach", bool(e.control.value)),
                        data="frage_mehrfach",
                    ),
                ]
            mitte.controls = [
                ft.Text(FRAGE_ERKLAERT[art], size=12, opacity=0.7, data="frage_erklaert"),
                *teile,
            ]
            if zeigen:
                with contextlib.suppress(Exception):
                    mitte.update()

        def uebernehmen(_e: Any = None) -> None:
            p = frisch()
            wortlaut = (text.value or "").strip() or f.text
            art = wie["art"]
            umbenannt: dict[str, str] = {}
            if art == ab.F_SKALA:
                try:
                    a, b = int(lo.value or 0), int(hi.value or 10)
                except ValueError:
                    a, b = f.min, f.max
                if b <= a or b - a > 20:
                    a, b = ab.FRAGE_MIN, ab.FRAGE_MAX
                neu = Frage(f.id, wortlaut, a, b)
            elif art == ab.F_JA_NEIN:
                neu = Frage(f.id, wortlaut, f.min, f.max, ab.F_JA_NEIN)
            else:
                paare = [(vorher, (feld.value or "").strip()) for vorher, feld, _z in zeilen]
                antworten = tuple(dict.fromkeys(jetzt for _v, jetzt in paare if jetzt))
                if not antworten:
                    # nichts von selbst einsetzen (Ben, 16.11.2026) — die Person trägt ein
                    if not zeilen:
                        antwort_zeile("")
                        fuellen(True)
                    zeilen[0][1].error = "Mindestens eine Antwort"
                    with contextlib.suppress(Exception):
                        zeilen[0][1].update()
                    return
                umbenannt = {v: j for v, j in paare if v and j and v != j}
                neu = Frage(
                    f.id, wortlaut, f.min, f.max, ab.F_AUSWAHL, antworten, bool(wie["mehrfach"])
                )
            speichern(ab.frage_ersetzen(p.ablauf, neu, umbenannt))
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        for antwort in f.antworten:
            antwort_zeile(antwort)
        fuellen()
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                [
                    ft.Text("Frage", size=18, weight=ft.FontWeight.W_600),
                    text,
                    ft.SegmentedButton(
                        segments=[
                            ft.Segment(value=art, label=ft.Text(name))
                            for art, name in ab.FRAGE_ART_TEXT.items()
                        ],
                        selected=[wie["art"]],
                        allow_empty_selection=False,
                        show_selected_icon=False,
                        on_change=art_gewaehlt,
                        data="frage_art",
                    ),
                    mitte,
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton(
                                "Übernehmen", on_click=uebernehmen, data="frage_uebernehmen"
                            ),
                        ],
                    )
                ],
                geschaetzt=460,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    # -- Aufbau -----------------------------------------------------------------------------------

    reiter_platz = ft.Container()
    einfuehrung = ft.Container(visible=False)
    unten = ft.Column(spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    werkzeug_leiste = ft.Row(
        wrap=True, spacing=6, run_spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    def einschalten(_e: Any = None) -> None:
        ablauf_einschalten(state, plan.id)
        lagen.clear()
        neu_zeichnen()

    def zeichnen() -> None:
        p = frisch()
        an = p.ablauf.an
        reiter_platz.content = plan_reiter(page, basis, "ablauf", ablauf_an=an)
        einfuehrung.visible = not an
        for teil in (palette, rahmen, unten, werkzeug_leiste):
            teil.visible = an
        ziele.control.visible = False  # nur, während gezogen wird
        if not an:
            einfuehrung.content = karte(
                kartentitel("Workout"),
                ft.Text(
                    "Dieser Plan ist eine Liste — jede Übung ist frei. Als Workout führt er "
                    "Schritt für Schritt: Hier stellst du ein, wann es weitergeht, und zeichnest "
                    "Wege zur Seite und zurück (Dehnung bei Krämpfen), nur bei Bedarf, Schleifen "
                    "bis eine Skala erreicht ist, Fragen, die nach dem Wert verzweigen.",
                    size=14,
                ),
                ft.FilledButton(
                    "Als Workout einrichten",
                    icon=ft.Icons.PLAYLIST_PLAY,
                    on_click=einschalten,
                ),
                abstand=10,
            )
            return
        palette_fuellen(p)
        # Was den Plan hängen lassen kann, steht sichtbar über dem Bild (Ben, 9.11.2026: „dafür
        # braucht es in der Planerstellung eine Warnung“)
        ids = [it.id for it in p.items]
        gefahr = plan_warnungen(state, p)
        # Ein ganz **leeres** Bild sagt unter sich, was zu tun ist (`leer_hinweis`) — die rote
        # Karte dazu gehört in den Reiter „Plan“. Fehlt der Start, während noch Wege im Bild
        # stehen, bleibt die Karte: Der Plan muss korrigiert werden (Ben, 16.11.2026)
        kein_start = ab.ohne_start_text(p.ablauf, ids)
        if kein_start != ab.START_FEHLT:
            gefahr = [g for g in gefahr if g != kein_start]
        warnung.visible = bool(gefahr)
        warnung.content = (
            warn_karte(gefahr, reparatur_knoepfe(page, state, p, neu_zeichnen)) if gefahr else None
        )
        abbild.aktualisieren(bild, zeichnung_jetzt(p))
        unten.controls = unter_dem_bild(p)
        werkzeug_leiste.controls = werkzeuge(p)

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            page.update()

    warnung = ft.Container(visible=False)
    inhalt = ft.Column(
        spacing=8,
        expand=True,
        controls=[
            reiter_platz,
            einfuehrung,
            palette,
            warnung,
            rahmen,
            unten,
            werkzeug_leiste,
        ],
    )
    zeichnen()
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"Ablauf · {plan.name}"),
            actions=[timer_knopf(page, state, "ablauf")],
        ),
        padding=ft.Padding.only(left=12, right=12, top=8, bottom=8),
        # Das Netz um alles fängt einen Punkt, der ins Leere fällt (`abbild.fangnetz`)
        controls=[sicher(abbild.fangnetz(inhalt, ziele), expand=True)],
    )


__all__ = [
    "ablauf_ausschalten",
    "ablauf_einschalten",
    "ablauf_speichern",
    "ablauf_view",
    "ablauf_zusammenfassung",
    "entfernen_fragen",
    "fehlende_namen",
    "knoten_namen",
    "modus_zeile",
    "plan_warnungen",
    "reparatur_knoepfe",
    "warn_karte",
]
