"""Eigene Kurse bauen (Ben, 12.11.2026; `docs/plan_kurse.md` §7, `docs/plan_kurseditor.md`).

Zwei Ansichten:

- ``/kurse/<id>/bearbeiten`` — der Kurs: Name, Beschreibung, Freischaltung, die Karte **„Der
  Kurs baut einen Plan“** (`Kurs.kursplan`: an/aus, Name, Wochentage, Grundlage) und die
  Kapitel (anlegen, umordnen, löschen). Jede Änderung wird sofort gespeichert — es ist eine
  Liste, kein Formular. Unten „Kurs löschen“ (Ben, 14.11.2026): Der Kurs verschwindet aus der
  Liste, seine Kapitelpläne werden deaktiviert und bleiben zum einzelnen Löschen
  (`KursRepo.entfernen`).
- ``/kurse/<id>/<kapitel>/bearbeiten`` — ein Kapitel in zwei Abschnitten (Ben, 16.11.2026,
  `docs/plan_kurs_ablauf.md` §11.6, Skizze K5): **„Im Kapitel — was man liest und tut“** mit
  den Blöcken (Text, Medium, Frage, Test, Auswahl — `core/kursbloecke.py`) und **„Am Plan —
  was sich ändert“** mit den **Bausteinen** (``plan_uebung``, ``plan_einstellen``,
  ``plan_weg``; ihr Formular ist `components/baustein_form.py`). Dazu die Pläne (aus den
  eigenen Plänen übernommen) und die Bedingung. Ein Formular mit „Speichern“; Zurück speichert.

Bausteine beziehen sich über ihre **Block-IDs** aufeinander (Marken). Darum: Ein neuer
Baustein bekommt eine lesbare ID, die bleibt (`core.kursbau.neue_id`); wer einen Block
löscht, auf den andere zeigen, wird gefragt, und die Verweise bleiben nie still hängen
(`core.kursbau.Kurssicht.folgen`) — das gilt auch für das Löschen eines Kapitels und der
Grundlage. Gerechnet wird in `core/kursbau.py`; hier wird gezeichnet und gespeichert.

Bearbeitet werden **eigene** Kurse (``package_id`` leer). Einen Kurs aus einem Paket kopiert
man zuerst (`kurs_kopieren`) — ein Paket-Update überschriebe sonst die Änderungen, und der
Fortschritt hängt an den Kapitel-IDs des Pakets. Bedingungen bleiben die vier Arten; es gibt
keine freie Formel (nie aus Messwerten).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import links
from trainingsapp.core.anpassung import Regel
from trainingsapp.core.kursbau import (
    TESTFELDER,
    Folge,
    Kurssicht,
    folgen_anwenden,
    kurs_kopie,
    neue_id,
    vergebene_ids,
)
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    FRAGE,
    MEDIUM,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    TEXT,
    Antwort,
    Block,
)
from trainingsapp.core.kurse import (
    FREISCHALTUNGEN,
    GELESEN,
    MESSUNG,
    SUMME,
    TAGE,
    Bedingung,
    Kapitel,
    Kurs,
    Kursplan,
    PlanVorlage,
)
from trainingsapp.core.kursplan import GRUNDLAGE
from trainingsapp.core.models import Exercise, Media
from trainingsapp.core.pakete import paketplan_aus
from trainingsapp.core.plaene import WOCHENTAGE_KURZ, tage_text
from trainingsapp.core.result_spec import basis_key
from trainingsapp.ui.components.baustein_form import baustein_blatt
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert

BEDINGUNG_NAMEN = {
    GELESEN: "gelesen — „Weiter“ reicht",
    SUMME: "Menge einer Übung",
    TAGE: "Tage mit den Plänen des Kapitels",
    MESSUNG: "eine HRV-Messung (nur die Dauer)",
}
#: Die Bedingung in einem Wort — für die Zeile eines Kapitels in der Liste des Kurses
BEDINGUNG_KURZ = {GELESEN: "gelesen", SUMME: "Menge", TAGE: "Tage", MESSUNG: "Messung"}
#: Das Symbol je Blockart in den Listen des Kapitels (Skizze K5)
ART_SYMBOL: dict[str, ft.IconData] = {
    TEXT: ft.Icons.NOTES,
    MEDIUM: ft.Icons.PLAY_CIRCLE_OUTLINE,
    FRAGE: ft.Icons.HELP_OUTLINE,
    TEST: ft.Icons.TIMER_OUTLINED,
    AUSWAHL: ft.Icons.CHECKLIST,
    PLAN_UEBUNG: ft.Icons.ADD,
    PLAN_EINSTELLEN: ft.Icons.TUNE,
    PLAN_WEG: ft.Icons.ALT_ROUTE,
}
KEIN_KURSPLAN = (
    "Der Kurs baut keinen Plan — Bausteine bewirken dann nichts. Einschalten: zurück zu „Kurs "
    "bearbeiten“ → „Der Kurs baut einen Plan“."
)


def art_name(block: Block) -> str:
    """Wie die Art eines Blocks heißt — auch die eines Bausteins."""
    return ARTEN.get(block.art) or BAUSTEINE.get(block.art) or block.art


def kurs_anlegen(state: Any) -> Kurs:
    """Ein neuer eigener Kurs mit einem leeren Kapitel."""
    kurs = Kurs(name="Neuer Kurs", kapitel=[Kapitel(titel="Kapitel 1")])
    state.kurse.speichern(kurs)
    return state.kurse.laden(kurs.id) or kurs


def kurs_kopieren(state: Any, kurs: Kurs) -> Kurs:
    """Eine eigene Kopie mit neuen IDs — Fortschritt und Pläne des Originals bleiben dort.

    Was kopiert wird, rechnet `core.kursbau.kurs_kopie`: Der Kursplan kommt mit, Blöcke
    bekommen neue IDs mit einer Abbildung alt → neu, die Verweise der Bausteine werden
    umgeschrieben, und ein Plan des Pakets als Grundlage wird zur Vorlage im Kurs. Hier wird
    nur gespeichert.
    """
    kopie = kurs_kopie(kurs, state.pakete.paketplaene)
    state.kurse.speichern(kopie)
    return state.kurse.laden(kopie.id) or kopie


def antworten_text(antworten: list[Antwort]) -> str:
    """Die Antworten einer Frage als Zeilen: ``*`` vorn = trifft zu, nach ``|`` der Hinweis.

    >>> antworten_text([Antwort("Knie"), Antwort("Ellbogen vor", True, "Hebel")])
    'Knie\\n* Ellbogen vor | Hebel'
    """
    return "\n".join(
        f"{'* ' if a.richtig else ''}{a.text}{f' | {a.hinweis}' if a.hinweis else ''}"
        for a in antworten
    )


def antworten_lesen(text: str) -> list[Antwort]:
    """Das Gegenstück zu `antworten_text` — leere Zeilen fallen weg.

    >>> [(a.text, a.richtig, a.hinweis) for a in antworten_lesen("Knie\\n\\n* Vor | Hebel")]
    [('Knie', False, ''), ('Vor', True, 'Hebel')]
    """
    ergebnis: list[Antwort] = []
    for zeile in text.splitlines():
        roh = zeile.strip()
        if not roh:
            continue
        richtig = roh.startswith("*")
        wort, _, mehr = roh.lstrip("* ").partition("|")
        if wort.strip():
            ergebnis.append(Antwort(wort.strip(), richtig, mehr.strip()))
    return ergebnis


def block_kurz(block: Block, katalog: dict[str, Exercise], sicht: Kurssicht | None = None) -> str:
    """Eine Zeile zum Block in der Liste des Editors. ``sicht``: der Kurs drumherum — ein
    Baustein nennt damit die Planübungen, auf die er sich bezieht (`Kurssicht.kurz`); in einem
    Kurs mit Kursplan wird ein Test nicht von selbst zum Ziel.

    >>> block_kurz(Block(AUSWAHL, uebungen=["a", "b"], anzahl=1), {})
    '1 von 2 Übungen'
    >>> block_kurz(Block(PLAN_UEBUNG, id="b", uebung="x"), {})
    'Übung fehlt, ans Ende'
    >>> block_kurz(Block(TEST, aus="w", feld="reps", faktor=0.8), {})
    'die gewählte — wird Ziel im Plan (80 %)'
    """
    if block.baustein:
        return (sicht or Kurssicht(Kurs(), "", [block], katalog)).kurz(block)
    if block.art == TEXT:
        return block.titel or block.text[:60] or "leer"
    if block.art == MEDIUM:
        return (block.medium.title or block.medium.uri) if block.medium else "ohne Adresse"
    if block.art == FRAGE:
        return f"{block.titel or 'ohne Frage'} · {len(block.antworten)} Antworten"
    if block.art == TEST:
        # „die gewählte“ einer Auswahl (``aus``) oder die feste Übung
        umfeld = sicht or Kurssicht(Kurs(), "", [block], katalog)
        name = (
            umfeld.wer(block)
            if block.aus
            else katalog[block.uebung].name
            if block.uebung in katalog
            else "Übung wählen"
        )
        if sicht is not None and sicht.kurs.kursplan is not None:
            feld = umfeld.feld(umfeld.uebungen_von(block), block.feld)
            return f"{name} · {feld.label}"
        return f"{name} — wird Ziel im Plan" + (
            f" ({round(block.faktor * 100)} %)" if block.faktor != 1.0 else ""
        )
    namen = [katalog[u].name for u in block.uebungen if u in katalog]
    menge = f"{block.anzahl} von {len(block.uebungen)}"
    return f"{menge} · {', '.join(namen)}" if namen else f"{menge} Übungen"


def block_fehler(block: Block) -> str | None:
    """Was einem Block zum Speichern fehlt — ``None`` = vollständig."""
    if block.art == MEDIUM and (block.medium is None or not links.erlaubt(block.medium.uri)):
        return "Ein Medium braucht eine https-Adresse."
    if block.art == FRAGE and (not block.titel or not block.antworten):
        return "Eine Frage braucht einen Text und mindestens eine Antwort."
    if block.art == TEST and not block.uebung and not block.aus:
        return "Ein Test braucht eine Übung."
    if block.art == AUSWAHL and (not block.uebungen or block.anzahl > len(block.uebungen)):
        return "Eine Auswahl braucht Übungen — mindestens so viele, wie man wählt."
    return None


def folgen_zeilen(sicht: Kurssicht, folgen: Sequence[Folge]) -> list[ft.Control]:
    """Die betroffenen Bausteine für eine Rückfrage — je Baustein, was mit ihm geschieht."""
    if not folgen:
        return []
    return [
        ft.Text("Darauf beziehen sich andere Blöcke:", size=13, weight=ft.FontWeight.W_600),
        *(ft.Text(f"• {sicht.folge_text(f)}", size=13) for f in folgen),
    ]


def folgen_scroll(folgen: Sequence[Folge]) -> ft.ScrollMode | None:
    """Ob die Rückfrage scrollt: nur bei einer langen Liste. Eine scrollende Spalte ist in
    Flet 1.0 so hoch, wie ihr Elternteil erlaubt — der Dialog würde bildschirmhoch, auch für
    drei Zeilen (Web-Foto, 16.11.2026; dieselbe Ursache wie in `components/blatt.py`)."""
    return ft.ScrollMode.AUTO if len(folgen) > 6 else None


# ---------------------------------------------------------------------------
# Der Kurs
# ---------------------------------------------------------------------------


def kurs_bearbeiten(page: Any, state: Any, kurs: Kurs) -> ft.View:
    """Name, Beschreibung, Freischaltung, der Kursplan und die Kapitel eines eigenen Kurses."""
    basis = f"/kurse/{kurs.id}"
    spalte = ft.Column(spacing=6)
    kursplan_spalte = ft.Column(
        spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
    )
    katalog: dict[str, Exercise] = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}

    def sicht(k: Kapitel | None = None) -> Kurssicht:
        """Der Kurs als Ganzes — mit ``k`` aus der Sicht dieses Kapitels."""
        return Kurssicht(kurs, k.id if k else "", k.bloecke if k else [], katalog)

    def sichern() -> None:
        state.kurse.speichern(kurs)

    def folgen_uebernehmen(folgen: Sequence[Folge]) -> None:
        """Wendet die Folgen eines Löschens auf die Kapitel an (gespeichert wird danach)."""
        for k in kurs.kapitel:
            eigene = [f for f in folgen if f.kapitel_id == k.id]
            if eigene:
                k.bloecke = folgen_anwenden(k.bloecke, eigene)

    def name_geaendert(e: Any) -> None:
        kurs.name = " ".join(str(e.control.value or "").split()) or "Kurs ohne Namen"
        sichern()

    def text_geaendert(e: Any) -> None:
        kurs.beschreibung = str(e.control.value or "").strip()
        sichern()

    def freischaltung_gewaehlt(e: Any) -> None:
        if e.control.value in FREISCHALTUNGEN:
            kurs.freischaltung = str(e.control.value)
            sichern()

    def neu() -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            spalte.update()

    def schieben(k: Kapitel, um: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            i = kurs.kapitel.index(k)
            j = i + um
            if 0 <= j < len(kurs.kapitel):
                kurs.kapitel[i], kurs.kapitel[j] = kurs.kapitel[j], kurs.kapitel[i]
                sichern()
                neu()

        return handler

    def loeschen_fragen(k: Kapitel) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dialog: ft.AlertDialog
            # Bausteine anderer Kapitel, die sich auf Blöcke dieses Kapitels beziehen
            folgen = [f for f in sicht().folgen(*(b.id for b in k.bloecke)) if f.kapitel_id != k.id]

            def ausfuehren(_e: Any = None) -> None:
                kurs.kapitel.remove(k)
                folgen_uebernehmen(folgen)
                sichern()
                schliessen(dialog)
                neu()

            dialog = ft.AlertDialog(
                title=ft.Text(f"„{k.titel}“ löschen?"),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    scroll=folgen_scroll(folgen),
                    controls=[
                        ft.Text(
                            "Das Kapitel mit seinen Blöcken verschwindet aus dem Kurs. Pläne, "
                            "die es schon angelegt hat, und alle Einträge bleiben."
                        ),
                        *folgen_zeilen(sicht(), folgen),
                    ],
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                    ft.FilledButton("Löschen", on_click=ausfuehren, data="kapitel_loeschen"),
                ],
            )
            page.show_dialog(dialog)

        return handler

    def oeffner(k: Kapitel) -> Callable[..., Any]:
        async def handler(_e: Any = None) -> None:
            await page.push_route(f"{basis}/{k.id}/bearbeiten")

        return handler

    def hinzufuegen(_e: Any = None) -> None:
        kurs.kapitel.append(Kapitel(titel=f"Kapitel {len(kurs.kapitel) + 1}", kurs_id=kurs.id))
        sichern()
        neu()

    def kurs_loeschen_fragen(_e: Any = None) -> None:
        """Den ganzen Kurs löschen — nach Rückfrage; danach zurück zur Liste."""
        nachher = Nachher()
        dialog: ft.AlertDialog

        def ausfuehren(_e: Any = None) -> None:
            n = state.kurse.entfernen(kurs)
            text = f"„{kurs.name}“ gelöscht"
            if n:
                text += " — 1 Plan deaktiviert" if n == 1 else f" — {n} Pläne deaktiviert"
            # Erst wenn der Dialog zu ist: Die Ansicht dieses Kurses gibt es dann nicht mehr
            nachher.danach(lambda: page.push_route("/"))
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(text))))
            schliessen(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text(f"„{kurs.name}“ löschen?"),
            content=ft.Text(
                "Der Kurs verschwindet aus der Liste — bei allen Profilen. Die Pläne, die seine "
                "Kapitel angelegt haben, werden deaktiviert: Sie stehen nicht mehr auf „Heute“, "
                "bleiben aber in der Planliste und lassen sich dort einzeln löschen. Einträge "
                "im Verlauf bleiben."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton(
                    "Löschen",
                    on_click=ausfuehren,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                    data="kurs_loeschen_ja",
                ),
            ],
        )
        page.show_dialog(dialog)

    # -- Der Kurs baut einen Plan (`Kurs.kursplan`) ------------------------------------------

    def kursplan_neu() -> None:
        kursplan_zeichnen()
        with contextlib.suppress(Exception):
            kursplan_spalte.update()
        neu()  # die Kapitelzeilen sagen, wo ein Verweis fehlt

    def kursplan_umgestellt(e: Any) -> None:
        an = bool(e.control.value)
        plan = kurs.kursplan
        if an == (plan is not None):
            return
        if plan is None:
            kurs.kursplan = Kursplan()
            sichern()
            kursplan_neu()
            return
        bausteine = sum(1 for k in kurs.kapitel for b in k.bloecke if b.baustein)
        eingestellt = bool(plan.name or plan.vorlage is not None or plan.grundlage)
        if not bausteine and not eingestellt:
            kurs.kursplan = None
            sichern()
            kursplan_neu()
            return
        dialog: ft.AlertDialog

        def ausschalten(_e: Any = None) -> None:
            kurs.kursplan = None
            sichern()
            schliessen(dialog)
            kursplan_neu()

        def lassen(_e: Any = None) -> None:
            schliessen(dialog)
            kursplan_neu()  # der Schalter steht wieder auf „an“

        saetze = []
        if bausteine:
            menge = "steht 1 Baustein" if bausteine == 1 else f"stehen {bausteine} Bausteine"
            saetze.append(
                f"In den Kapiteln {menge} unter „Am Plan“. Sie bleiben dort, bewirken aber "
                "nichts, solange der Kurs keinen Plan baut."
            )
        if eingestellt:
            saetze.append("Name, Wochentage und Grundlage des Plans gehen verloren.")
        saetze.append(
            "Ein Kursplan, den jemand schon hat, bleibt bestehen — er wächst nur nicht weiter."
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Keinen Plan mehr bauen?"),
            content=ft.Text("\n\n".join(saetze)),
            actions=[
                ft.TextButton("Abbrechen", on_click=lassen, data="kursplan_aus_nein"),
                ft.FilledButton("Ausschalten", on_click=ausschalten, data="kursplan_aus_ja"),
            ],
        )
        page.show_dialog(dialog)

    def kursplan_name(e: Any) -> None:
        if kurs.kursplan is not None:
            kurs.kursplan.name = " ".join(str(e.control.value or "").split())
            sichern()

    def tag_schalter(nr: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if kurs.kursplan is not None:
                kurs.kursplan.wochentage = sorted(set(kurs.kursplan.wochentage) ^ {nr})
                sichern()
                kursplan_neu()

        return handler

    def grundlage_setzen(vorlage: PlanVorlage | None, tage: Sequence[int] = ()) -> None:
        """Die Vorlage des Kursplans setzen oder entfernen (``None`` = der Plan beginnt leer).
        Nennen Bausteine eine Planübung der bisherigen Grundlage, die es danach nicht mehr
        gibt (``g:<n>``), wird vorher gefragt — die Verweise bleiben nicht still hängen."""
        plan = kurs.kursplan
        if plan is None:
            return
        bisher = len(plan.vorlage.items) if plan.vorlage is not None else 0
        kuenftig = len(vorlage.items) if vorlage is not None else 0
        folgen = sicht().folgen(*(f"{GRUNDLAGE}{n}" for n in range(kuenftig + 1, bisher + 1)))

        def ausfuehren() -> None:
            plan.vorlage = vorlage
            if vorlage is not None:
                # Vorlage und Schlüssel eines Paketplans zugleich nimmt die Paketprüfung nicht
                # an — die App nähme ohnehin die Vorlage (`core.kursplan.grundplan`)
                plan.grundlage = ""
            if vorlage is not None and tage and plan.wochentage == list(range(7)):
                plan.wochentage = sorted(set(tage))  # die Tage des Plans, solange nichts gewählt
            folgen_uebernehmen(folgen)
            sichern()
            kursplan_neu()

        if not folgen:
            ausfuehren()
            return
        dialog: ft.AlertDialog

        def bestaetigt(_e: Any = None) -> None:
            schliessen(dialog)
            ausfuehren()

        dialog = ft.AlertDialog(
            title=ft.Text("Grundlage ändern?"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=folgen_scroll(folgen),
                controls=[
                    ft.Text(
                        "Die neue Grundlage hat weniger Übungen."
                        if vorlage is not None
                        else "Der Plan beginnt dann ohne Übungen."
                    ),
                    *folgen_zeilen(sicht(), folgen),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Ändern", on_click=bestaetigt, data="kursplan_vorlage_ja"),
            ],
        )
        page.show_dialog(dialog)

    def vorlage_waehlen(_e: Any = None) -> None:
        eigene = [p for p in state.plaene.alle(state.profil.id) if p.items]
        dialog: ft.AlertDialog

        def nehmen(plan_id: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                plan = state.plaene.laden(plan_id)
                schliessen(dialog)
                if plan is not None:
                    grundlage_setzen(paketplan_aus(plan).vorlage, plan.wochentage)

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Plan als Grundlage"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    hinweis(
                        "Der Kursplan beginnt mit einer Kopie dieses Plans, wie er jetzt ist — "
                        "mit Zielen, Ablauf und Anweisungen. Spätere Änderungen am Plan kommen "
                        "nicht nach. Bausteine, die eine Übung der Grundlage nennen, meinen "
                        "die Übung an derselben Stelle."
                    ),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LIST_ALT),
                            title=ft.Text(p.name),
                            subtitle=ft.Text(f"{len(p.items)} Übungen", size=12),
                            on_click=nehmen(p.id),
                            data=("kursplan_plan", p.id),
                        )
                        for p in eigene
                    ),
                    *([] if eigene else [ft.Text("Noch kein eigener Plan mit Übungen.")]),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def kursplan_zeichnen() -> None:
        plan = kurs.kursplan
        teile: list[ft.Control] = [
            ft.Switch(
                label="Der Kurs baut einen Plan",
                value=plan is not None,
                on_change=kursplan_umgestellt,
                data="kursplan_an",
            )
        ]
        if plan is None:
            teile.append(
                hinweis(
                    "Aus: Jedes Kapitel legt seine eigenen Pläne an und deaktiviert sie am "
                    "Ende. An: Ein Plan wächst über die Kapitel — jedes Kapitel ändert ihn mit "
                    "Bausteinen („Am Plan“), und nichts ändert sich ohne Tipp der Person."
                )
            )
            kursplan_spalte.controls = teile
            return
        vorlage = plan.vorlage
        teile += [
            ft.TextField(
                label="Name des Plans",
                value=plan.name,
                hint_text=f"leer = „{kurs.name}“",
                on_blur=kursplan_name,
                data="kursplan_name",
            ),
            ft.Row(
                wrap=True,
                spacing=4,
                run_spacing=4,
                controls=[
                    ft.Chip(
                        label=ft.Text(kurz),
                        selected=nr in plan.wochentage,
                        show_checkmark=False,
                        # schmaler als die Vorgabe: sieben passen so in die Karte (Web-Foto)
                        label_padding=ft.Padding.symmetric(horizontal=3),
                        on_click=tag_schalter(nr),
                        data=("kursplan_tag", nr),
                    )
                    for nr, kurz in enumerate(WOCHENTAGE_KURZ)
                ],
            ),
            hinweis(f"Steht an: {tage_text(plan.wochentage)}."),
            titel("Grundlage — womit der Plan beginnt"),
        ]
        if vorlage is not None:
            teile.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(vorlage.name),
                    subtitle=ft.Text(
                        "  ·  ".join(sicht().name(i.exercise_id) for i in vorlage.items),
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="Grundlage entfernen — der Plan beginnt leer",
                        on_click=lambda: grundlage_setzen(None),
                        data="kursplan_vorlage_weg",
                    ),
                    content_padding=ft.Padding.only(left=4, right=0),
                    data="kursplan_vorlage_zeile",
                )
            )
        else:
            teile.append(ft.Text("leer — der Plan beginnt ohne Übungen", size=13))
        if plan.grundlage:
            teile.append(
                hinweis(
                    f"Plan des Pakets: „{plan.grundlage}“ — gilt nur in einem Paket"
                    + (
                        "; hier gilt die Vorlage darüber."
                        if vorlage is not None
                        else "; ein eigener Kurs beginnt ohne ihn leer. Nimmst du einen "
                        "eigenen Plan, ersetzt er diesen Verweis."
                    )
                )
            )
        teile.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Anderen Plan nehmen …" if vorlage is not None else "Eigenen Plan nehmen …",
                        icon=ft.Icons.PLAYLIST_ADD,
                        on_click=vorlage_waehlen,
                        data="kursplan_vorlage",
                    )
                ]
            )
        )
        kursplan_spalte.controls = teile

    def kapitel_unter(k: Kapitel) -> str:
        """Die zweite Zeile eines Kapitels: Blöcke, Bausteine, Plan, Bedingung — und ob ein
        Baustein ins Leere zeigt (nach dem Umordnen von Kapiteln etwa)."""
        lesen = sum(1 for b in k.bloecke if not b.baustein)
        am_plan = len(k.bloecke) - lesen
        aus_sicht = sicht(k)
        teile = [
            "ohne Blöcke" if not lesen else "1 Block" if lesen == 1 else f"{lesen} Blöcke",
            *([f"{am_plan} am Plan"] if am_plan else []),
            *(["mit Plan"] if k.plaene else []),
            BEDINGUNG_KURZ.get(k.bedingung.art, k.bedingung.art),
            *(["Verweis fehlt"] if any(aus_sicht.haengt(b) for b in k.bloecke) else []),
        ]
        return "  ·  ".join(teile)

    def zeichnen() -> None:
        letzte = len(kurs.kapitel) - 1
        spalte.controls = [
            ft.ListTile(
                leading=ft.Text(str(n + 1), size=16, weight=ft.FontWeight.W_600),
                title=ft.Text(k.titel or "ohne Titel"),
                subtitle=ft.Text(kapitel_unter(k), size=12),
                trailing=ft.Row(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Nach oben",
                            disabled=n == 0,
                            on_click=schieben(k, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Nach unten",
                            disabled=n == letzte,
                            on_click=schieben(k, 1),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Kapitel löschen",
                            disabled=len(kurs.kapitel) <= 1,
                            on_click=loeschen_fragen(k),
                        ),
                    ],
                ),
                on_click=oeffner(k),
                content_padding=ft.Padding.only(left=4, right=0),
                data=("kapitel", k.id),
            )
            for n, k in enumerate(kurs.kapitel)
        ]

    zeichnen()
    kursplan_zeichnen()
    return ft.View(
        route=f"{basis}/bearbeiten",
        appbar=ft.AppBar(title=ft.Text("Kurs bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.TextField(label="Name", value=kurs.name, on_blur=name_geaendert),
                        ft.TextField(
                            label="Beschreibung",
                            value=kurs.beschreibung,
                            multiline=True,
                            min_lines=2,
                            on_blur=text_geaendert,
                        ),
                        ft.Dropdown(
                            label="Freischaltung",
                            value=kurs.freischaltung,
                            options=[
                                ft.DropdownOption(key=k, text=t) for k, t in FREISCHALTUNGEN.items()
                            ],
                            on_select=freischaltung_gewaehlt,
                        ),
                        karte(kursplan_spalte),
                        titel("Kapitel"),
                        spalte,
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Kapitel hinzufügen",
                                    icon=ft.Icons.ADD,
                                    on_click=hinzufuegen,
                                    data="kapitel_hinzufuegen",
                                )
                            ]
                        ),
                        hinweis(
                            "Änderungen hier gelten sofort. Weitergeben lässt sich der Kurs über "
                            "ein eigenes Paket (Einstellungen → Pakete)."
                        ),
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Kurs löschen",
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    on_click=kurs_loeschen_fragen,
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    data="kurs_loeschen",
                                )
                            ]
                        ),
                    ],
                )
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Kapitel
# ---------------------------------------------------------------------------


def kapitel_bearbeiten(page: Any, state: Any, kurs: Kurs, kapitel: Kapitel) -> ft.View:
    """Titel, Blöcke, Bausteine, Pläne und Bedingung eines Kapitels — ein Formular."""
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    katalog: dict[str, Exercise] = {u.id: u for u in state.uebungen.alle()}
    #: mit den archivierten — für Namen und die Vorschau der Karte (sie nennt sie auch)
    katalog_alle: dict[str, Exercise] = {
        u.id: u for u in state.uebungen.alle(mit_archivierten=True)
    }
    uebungen = sorted(katalog.values(), key=lambda u: u.name.lower())
    bloecke: list[Block] = [replace(b) for b in kapitel.bloecke]
    #: ungespeicherte Fassungen **anderer** Kapitel — nach einem Löschen, das dort Bausteine
    #: trifft; geschrieben erst mit „Speichern“, „Abbrechen“ verwirft sie mit
    andere: dict[str, list[Block]] = {}
    plaene: list[PlanVorlage] = [replace(v) for v in kapitel.plaene]
    bedingung = replace(kapitel.bedingung)
    baut_plan = kurs.kursplan is not None
    titel_feld = ft.TextField(label="Titel", value=kapitel.titel)
    block_spalte = ft.Column(spacing=6)
    baustein_spalte = ft.Column(spacing=6)
    plan_spalte = ft.Column(spacing=6)
    bedingung_spalte = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    fehler = ft.Text("", size=13, color=ft.Colors.ERROR, visible=False)

    def sicht() -> Kurssicht:
        """Der Kurs, wie er in diesem Formular gerade steht (`bloecke` ist dieselbe Liste)."""
        return Kurssicht(kurs, kapitel.id, bloecke, katalog_alle, andere)

    def frisch(spalte: ft.Column, zeichnen: Callable[[], None]) -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            spalte.update()

    def listen_frisch() -> None:
        """Beide Listen neu — ein Baustein nennt Blöcke der anderen (Auswahl, Test)."""
        frisch(block_spalte, bloecke_zeichnen)
        frisch(baustein_spalte, bausteine_zeichnen)

    def uebung_wahl(
        wert: str, label: str = "Übung", auswahlen: Sequence[tuple[str, str]] = ()
    ) -> ft.Dropdown:
        """Eine Übung aus dem Katalog. ``auswahlen`` (ID, Name): davor „die gewählte aus …“ —
        der Schlüssel ist dann ``aus:<Block-ID>``, wie im Blatt „Übung in den Plan“."""
        optionen = [
            *(
                ft.DropdownOption(key=f"aus:{k}", text=f"die gewählte aus „{n}“")
                for k, n in auswahlen
            ),
            *(ft.DropdownOption(key=u.id, text=u.name) for u in uebungen),
        ]
        return ft.Dropdown(
            label=label,
            value=wert if wert in [o.key for o in optionen] else None,
            options=optionen,
            enable_filter=True,
            editable=True,
            menu_height=320,
        )

    # -- Blöcke ---------------------------------------------------------------------------

    def block_dialog(block: Block, neu: bool) -> None:
        """Die Felder zur Art des Blocks; „Übernehmen“ schreibt in die Liste des Formulars."""
        kopf = ft.TextField(
            label={TEXT: "Überschrift", FRAGE: "Frage", MEDIUM: "Titel"}.get(
                block.art, "Aufforderung (leer = Vorgabe)"
            ),
            value=(block.medium.title if block.medium else "")
            if block.art == MEDIUM
            else block.titel,
        )
        text = ft.TextField(
            label="Text (Markdown)" if block.art == TEXT else "Satz darunter",
            value=block.text,
            multiline=True,
            min_lines=4 if block.art == TEXT else 1,
        )
        adresse = ft.TextField(
            label="Adresse (https://…)",
            value=block.medium.uri if block.medium else "",
            keyboard_type=ft.KeyboardType.URL,
        )
        antworten = ft.TextField(
            label="Antworten — eine je Zeile, * = trifft zu, | Hinweis",
            value=antworten_text(block.antworten),
            multiline=True,
            min_lines=3,
        )
        # Der Test misst eine feste Übung — oder „die gewählte“ einer Auswahl dieses oder (im
        # Kursplan-Kurs) eines früheren Kapitels (Ben, 16.11.2026; `Block.aus`), auch einer noch
        # ungespeicherten
        uebung = uebung_wahl(
            f"aus:{block.aus}" if block.aus else block.uebung,
            auswahlen=sicht().auswahlen_fuer_test() if block.art == TEST else (),
        )
        feld = ft.Dropdown(label="Was wird gemessen")
        feld_hinweis = hinweis(
            "Die Übungen dieser Auswahl haben kein gemeinsames Feld — gemessen wird nur, wo die "
            "gewählte Übung dieses Feld hat."
        )
        faktor = ft.TextField(
            label="Ziel in % des Tests",
            value=str(round(block.faktor * 100)),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        anzahl = ft.TextField(
            label="Wie viele wählt man",
            value=str(block.anzahl),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        nach = ft.TextField(
            label="Hinter Planübung Nr. (0 = ans Ende)",
            value=str(block.nach),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        gewaehlt: list[str] = [u for u in block.uebungen if u in katalog]
        wahl_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        dazu = uebung_wahl("", "Übung zur Auswahl hinzufügen")
        meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)
        dialog: ft.AlertDialog

        def gemessen() -> list[str]:
            """Die Übungen, die der Test messen kann: die feste — oder die der Auswahl."""
            wert = str(uebung.value or "")
            if wert.startswith("aus:"):
                return sicht().uebungen_von(Block(TEST, aus=wert[4:]))
            return [wert] if wert in katalog else []

        def felder_setzen() -> None:
            # bei „der gewählten“: was alle Übungen der Auswahl haben (`Kurssicht.testfelder`)
            angebot, gemeinsam = sicht().testfelder(gemessen())
            feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
            schluessel = [f.key for f in angebot]
            feld.value = (
                block.feld if block.feld in schluessel else (schluessel[0] if schluessel else None)
            )
            feld_hinweis.visible = not gemeinsam

        def uebung_gewaehlt(_e: Any = None) -> None:
            felder_setzen()
            for c in (feld, feld_hinweis):
                with contextlib.suppress(Exception):
                    c.update()

        def wahl_zeichnen() -> None:
            wahl_reihe.controls = [
                ft.Chip(
                    label=ft.Text(katalog[uid].name),
                    on_delete=lambda _e=None, uid=uid: wahl_weg(uid),
                    data=("auswahl_uebung", uid),
                )
                for uid in gewaehlt
            ]

        def wahl_weg(uid: str) -> None:
            gewaehlt.remove(uid)
            frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        def wahl_dazu(_e: Any = None) -> None:
            uid = str(dazu.value or "")
            if uid in katalog and uid not in gewaehlt:
                gewaehlt.append(uid)
                frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        uebung.on_select = uebung_gewaehlt
        dazu.on_select = wahl_dazu
        felder_setzen()
        wahl_zeichnen()

        def zahl(feld_: ft.TextField, vorgabe: float) -> float:
            try:
                return float(str(feld_.value or "").replace(",", "."))
            except ValueError:
                return vorgabe

        def uebernehmen(_e: Any = None) -> None:
            neuer = replace(block, text=str(text.value or "").strip())
            wort = " ".join(str(kopf.value or "").split())
            if block.art == MEDIUM:
                neuer.medium = Media(uri=str(adresse.value or "").strip(), title=wort)
                neuer.text = ""
            else:
                neuer.titel = wort
            if block.art == FRAGE:
                neuer.antworten = antworten_lesen(str(antworten.value or ""))
            if block.art == TEST:
                gewaehlte = str(uebung.value or "")
                neuer.aus = gewaehlte[4:] if gewaehlte.startswith("aus:") else ""
                neuer.uebung = "" if neuer.aus else gewaehlte  # nie beides
                neuer.feld = str(feld.value or "hold")
                neuer.faktor = min(max(zahl(faktor, 100) / 100, 0.1), 3.0)
            if block.art == AUSWAHL:
                neuer.uebungen = list(gewaehlt)
                neuer.anzahl = max(1, int(zahl(anzahl, 1)))
                neuer.nach = max(0, int(zahl(nach, 0)))
            grund = block_fehler(neuer)
            if grund is not None:
                meldung.value = grund
                meldung.visible = True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            if neu:
                bloecke.append(neuer)
            else:
                bloecke[bloecke.index(block)] = neuer
            schliessen(dialog)
            listen_frisch()

        # Im Kurs mit Kursplan liefern Test und Auswahl nur Wert und Wahl — was daraus wird,
        # sagen die Bausteine „Am Plan“ (`docs/plan_kurs_ablauf.md` §11.2). „Ziel in %“ und
        # „Hinter Planübung Nr.“ gehören zum Kapitelplan und stehen nur da, wo es einen gibt.
        nur_liefern = baut_plan and not plaene
        felder: dict[str, list[ft.Control]] = {
            TEXT: [kopf, text],
            MEDIUM: [kopf, adresse],
            FRAGE: [
                kopf,
                text,
                antworten,
                hinweis("Die Frage erklärt — nichts wird gespeichert oder gezählt."),
            ],
            TEST: [
                kopf,
                text,
                uebung,
                feld,
                feld_hinweis,
                *([] if nur_liefern else [faktor]),
                hinweis(
                    "Der Test ist ein gewöhnlicher Eintrag der Übung. Was aus dem Wert wird, "
                    "sagt ein Baustein unter „Am Plan“ (Ziel → „aus dem Test“)."
                    if nur_liefern
                    else "Der Test ist ein gewöhnlicher Eintrag der Übung. Der Wert wird ihr "
                    "Ziel im Kapitelplan."
                ),
            ],
            AUSWAHL: [
                kopf,
                text,
                wahl_reihe,
                dazu,
                anzahl,
                *([] if nur_liefern else [nach]),
                hinweis(
                    "Was mit der Wahl geschieht, sagt ein Baustein unter „Am Plan“ (Übung → "
                    "„die gewählte aus …“)."
                    if nur_liefern
                    else "Ab zwei Gewählten stehen sie im Workout als Wege hinter der "
                    "genannten Planübung."
                ),
            ],
        }
        dialog = ft.AlertDialog(
            title=ft.Text(art_name(block)),
            content=ft.Column(
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                controls=[*felder.get(block.art, []), meldung],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Übernehmen", on_click=uebernehmen, data="block_uebernehmen"),
            ],
        )
        page.show_dialog(dialog)

    def block_schieben(block: Block, um: int) -> Callable[..., None]:
        """Innerhalb seines Abschnitts („Im Kapitel“ bzw. „Am Plan“) nach oben oder unten."""

        def handler(_e: Any = None) -> None:
            gruppe = [b for b in bloecke if b.baustein == block.baustein]
            i = gruppe.index(block)
            j = i + um
            if 0 <= j < len(gruppe):
                a, b = bloecke.index(gruppe[i]), bloecke.index(gruppe[j])
                bloecke[a], bloecke[b] = bloecke[b], bloecke[a]
                listen_frisch()

        return handler

    def block_loeschen(block: Block) -> None:
        """Nimmt den Block aus dem Kapitel. Zeigen Bausteine auf ihn — hier oder in anderen
        Kapiteln —, wird vorher gefragt: Die Rückfrage nennt jeden und was mit ihm geschieht
        (`Kurssicht.folgen`); kein Verweis bleibt still hängen. Wie alles im Formular gilt es
        erst mit „Speichern“."""
        folgen = sicht().folgen(block.id)

        def ausfuehren() -> None:
            hier = [f for f in folgen if f.kapitel_id == kapitel.id]
            bloecke[:] = folgen_anwenden([b for b in bloecke if b.id != block.id], hier)
            for k in kurs.kapitel:
                dort = [f for f in folgen if f.kapitel_id == k.id]
                if dort and k.id != kapitel.id:
                    andere[k.id] = folgen_anwenden(andere.get(k.id, k.bloecke), dort)
            listen_frisch()

        if not folgen:
            ausfuehren()
            return
        dialog: ft.AlertDialog

        def bestaetigt(_e: Any = None) -> None:
            schliessen(dialog)
            ausfuehren()

        dialog = ft.AlertDialog(
            title=ft.Text(f"„{art_name(block)}“ löschen?"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=folgen_scroll(folgen),
                controls=[
                    ft.Text(block_kurz(block, katalog_alle, sicht())),
                    *folgen_zeilen(sicht(), folgen),
                    hinweis("Gilt wie alles hier erst mit „Speichern“."),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=bestaetigt, data="block_loeschen_ja"),
            ],
        )
        page.show_dialog(dialog)

    def block_weg(block: Block) -> Callable[..., None]:
        return lambda _e=None: block_loeschen(block)

    def oeffnen(block: Block) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if block.baustein:
                baustein_oeffnen(block, neu=False)
            else:
                block_dialog(block, neu=False)

        return handler

    def zeile(b: Block, n: int, letzte: int) -> ft.Control:
        """Eine Zeile wie in Skizze K5: Symbol, die Art fett, darunter der Kurztext blass —
        Bausteine farbig abgesetzt; rechts verschieben und entfernen."""
        am_plan = b.baustein
        farbe = ft.Colors.ON_SECONDARY_CONTAINER if am_plan else None
        haengt = sicht().haengt(b)
        unter: list[ft.Control] = [
            ft.Text(
                block_kurz(b, katalog_alle, sicht()),
                size=12,
                color=farbe,
                opacity=0.75,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        ]
        if haengt:
            unter.append(
                ft.Text("Verweis fehlt: " + ", ".join(haengt), size=12, color=ft.Colors.ERROR)
            )

        def knopf(
            icon: ft.IconData, tooltip: str, handler: Callable[..., None], aus: bool = False
        ) -> ft.IconButton:
            return ft.IconButton(
                icon,
                icon_size=20,
                icon_color=farbe,
                tooltip=tooltip,
                disabled=aus,
                on_click=handler,
                padding=4,
                visual_density=ft.VisualDensity.COMPACT,
            )

        return ft.Container(
            data=("baustein" if am_plan else "block", b.id),
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if am_plan else ft.Colors.SURFACE_CONTAINER_HIGH,
            padding=ft.Padding.only(left=12, right=2, top=6, bottom=6),
            on_click=oeffnen(b),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ART_SYMBOL.get(b.art, ft.Icons.NOTES), size=22, color=farbe),
                    ft.Container(width=4),
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(art_name(b), size=14, weight=ft.FontWeight.W_600, color=farbe),
                            *unter,
                        ],
                    ),
                    knopf(ft.Icons.ARROW_UPWARD, "Nach oben", block_schieben(b, -1), n == 0),
                    knopf(ft.Icons.ARROW_DOWNWARD, "Nach unten", block_schieben(b, 1), n == letzte),
                    knopf(ft.Icons.CLOSE, "Entfernen", block_weg(b)),
                ],
            ),
        )

    def bloecke_zeichnen() -> None:
        gruppe = [b for b in bloecke if not b.baustein]
        block_spalte.controls = [zeile(b, n, len(gruppe) - 1) for n, b in enumerate(gruppe)] or [
            hinweis("Noch kein Block — das Kapitel zeigt nur seinen Titel.")
        ]

    def bausteine_zeichnen() -> None:
        gruppe = [b for b in bloecke if b.baustein]
        zeilen: list[ft.Control] = [zeile(b, n, len(gruppe) - 1) for n, b in enumerate(gruppe)]
        if not baut_plan:
            zeilen.append(hinweis(KEIN_KURSPLAN))
        elif not zeilen:
            zeilen.append(hinweis("Noch kein Baustein — dieses Kapitel ändert den Plan nicht."))
        baustein_spalte.controls = zeilen

    def dazu_zeigen(welche: str) -> None:
        """Klappt die Arten unter „+ Im Kapitel“ bzw. „+ Am Plan“ auf — ein zweiter Tipp oder
        die Wahl einer Art klappt sie wieder zu."""
        dazu_lesen.visible = welche == "lesen" and not dazu_lesen.visible
        dazu_plan.visible = welche == "plan" and not dazu_plan.visible
        for reihe in (dazu_lesen, dazu_plan):
            with contextlib.suppress(Exception):
                reihe.update()

    def block_neu(art: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dazu_zeigen("")
            block_dialog(Block(art), neu=True)

        return handler

    # -- Bausteine am Kursplan ------------------------------------------------------------

    #: IDs, die dieses Formular schon gesehen oder vergeben hat — auch die von Bausteinen,
    #: die hier (noch ungespeichert) gelöscht wurden: Eine neue ID trifft keine davon
    verbraucht: set[str] = {b.id for b in kapitel.bloecke}

    def plan_marken() -> list[str]:
        """Die Marken, die Kurspläne dieses Kurses im Profil schon tragen — auch die aus dem
        Kurs-Stand (dort stehen sie weiter, wenn die Person die Planübung gelöscht hat)."""
        profil = state.profil.id
        marken: list[str] = []
        kursplaene = [
            state.kurse.kursplan(kurs, profil),
            *state.kurse.fruehere_kursplaene(kurs.id, profil),
        ]
        for plan in kursplaene:
            if plan is not None:
                marken += [i.kurs_marke for i in plan.items if i.kurs_marke]
                marken += [str(m) for m in state.plaene.kurs_stand(plan.id)]
        return marken

    def baustein_oeffnen(block: Block, neu: bool) -> None:
        def uebernehmen(fertig: Block) -> None:
            stelle = next((n for n, b in enumerate(bloecke) if b.id == block.id), None)
            if stelle is None:
                bloecke.append(fertig)
            else:
                bloecke[stelle] = fertig
            listen_frisch()

        page.show_dialog(
            baustein_blatt(
                page,
                state,
                sicht(),
                block,
                neu=neu,
                uebungen=uebungen,
                uebernehmen=uebernehmen,
                loeschen=None if neu else (lambda: block_loeschen(block)),
            )
        )

    def baustein_neu(art: str) -> Callable[..., None]:
        """Ein neuer Baustein mit **fester, lesbarer ID** aus Art und laufender Nummer
        (`core.kursbau.neue_id`) — eindeutig im ganzen Kurs; sie steht als Marke im Plan und
        im Paket und ändert sich nie."""

        def handler(_e: Any = None) -> None:
            dazu_zeigen("")
            vergeben = vergebene_ids(sicht().alle(), plan_marken()) | verbraucht
            block = Block(art, id=neue_id(art, vergeben))
            verbraucht.add(block.id)
            baustein_oeffnen(block, neu=True)

        return handler

    dazu_lesen = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=4,
        visible=False,
        controls=[
            ft.OutlinedButton(
                name.split(",")[0],
                icon=ART_SYMBOL[art],
                on_click=block_neu(art),
                data=("block_neu", art),
            )
            for art, name in ARTEN.items()
        ],
    )
    dazu_plan = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=4,
        visible=False,
        controls=[
            ft.OutlinedButton(
                name,
                icon=ART_SYMBOL[art],
                on_click=baustein_neu(art),
                data=("baustein_neu", art),
            )
            for art, name in BAUSTEINE.items()
        ],
    )

    # -- Pläne ----------------------------------------------------------------------------

    def plan_weg(vorlage: PlanVorlage) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            plaene.remove(vorlage)
            frisch(plan_spalte, plaene_zeichnen)

        return handler

    def plan_waehlen(_e: Any = None) -> None:
        eigene = [p for p in state.plaene.alle(state.profil.id) if p.items]
        dialog: ft.AlertDialog

        def nehmen(plan_id: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                plan = state.plaene.laden(plan_id)
                if plan is not None:
                    plaene.append(paketplan_aus(plan).vorlage)
                schliessen(dialog)
                frisch(plan_spalte, plaene_zeichnen)

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Plan übernehmen"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    hinweis(
                        "Das Kapitel bekommt eine Kopie des Plans, wie er jetzt ist — mit "
                        "Zielen, Ablauf und Anweisungen. Spätere Änderungen am Plan kommen "
                        "nicht nach."
                    ),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LIST_ALT),
                            title=ft.Text(p.name),
                            subtitle=ft.Text(f"{len(p.items)} Übungen", size=12),
                            on_click=nehmen(p.id),
                            data=("plan_nehmen", p.id),
                        )
                        for p in eigene
                    ),
                    *([] if eigene else [ft.Text("Noch kein eigener Plan mit Übungen.")]),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def regel_zeile(v: PlanVorlage, n: int) -> ft.Control:
        """Der Vorschlag nach der Belastung für diesen Plan (`core/anpassung.py`): Schalter und
        die drei Zahlen der Regel."""
        regel = Regel.aus_dict(v.anpassung) or Regel()
        felder = {
            "ab": ft.TextField(label="kürzer ab", value=str(regel.ab), width=92, dense=True),
            "bis": ft.TextField(label="länger bis", value=str(regel.bis), width=92, dense=True),
            "prozent": ft.TextField(label="um %", value=str(regel.prozent), width=80, dense=True),
        }
        zahlen = ft.Row(spacing=8, visible=v.anpassung is not None, controls=list(felder.values()))

        def lesen() -> None:
            neu = Regel.aus_dict({k: f.value for k, f in felder.items()})
            v.anpassung = (neu or Regel()).als_dict()

        def umgestellt(e: Any) -> None:
            if e.control.value:
                lesen()
            else:
                v.anpassung = None
            zahlen.visible = v.anpassung is not None
            with contextlib.suppress(Exception):
                zahlen.update()

        for f in felder.values():
            f.keyboard_type = ft.KeyboardType.NUMBER
            f.on_blur = lambda _e=None: lesen() if v.anpassung is not None else None
        return ft.Container(
            padding=ft.Padding.only(left=44, bottom=6),
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Switch(
                        label="Vorschlag nach der Belastung",
                        tooltip="Nach dem Workout ein anderes Zeitziel vorschlagen — nur auf Tipp",
                        value=v.anpassung is not None,
                        on_change=umgestellt,
                        data=("plan_regel", n),
                    ),
                    zahlen,
                ],
            ),
        )

    def plaene_zeichnen() -> None:
        zeilen: list[ft.Control] = []
        for n, v in enumerate(plaene):
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(v.name),
                    subtitle=ft.Text(
                        "  ·  ".join(
                            katalog[i.exercise_id].name if i.exercise_id in katalog else "fehlt"
                            for i in v.items
                        ),
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Aus dem Kapitel nehmen", on_click=plan_weg(v)
                    ),
                    content_padding=ft.Padding.only(left=4, right=0),
                )
            )
            zeilen.append(regel_zeile(v, n))
        plan_spalte.controls = zeilen

    # -- Bedingung ------------------------------------------------------------------------

    soll_feld = ft.TextField(
        label="Soll",
        value=f"{bedingung.soll:g}" if bedingung.soll else "",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    bed_uebung = uebung_wahl(bedingung.exercise_id)
    bed_feld = ft.Dropdown(label="Feld")

    def bed_felder() -> None:
        u = katalog.get(str(bed_uebung.value or ""))
        angebot = [f for f in (u.result_spec.fields if u else []) if basis_key(f.key) in TESTFELDER]
        bed_feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
        schluessel = [f.key for f in angebot]
        bed_feld.value = (
            bedingung.feld
            if bedingung.feld in schluessel
            else (schluessel[0] if schluessel else None)
        )

    def bed_uebung_gewaehlt(_e: Any = None) -> None:
        bed_felder()
        with contextlib.suppress(Exception):
            bed_feld.update()

    bed_uebung.on_select = bed_uebung_gewaehlt

    def art_gewaehlt(e: Any) -> None:
        if e.control.value in BEDINGUNG_NAMEN:
            bedingung.art = str(e.control.value)
            frisch(bedingung_spalte, bedingung_zeichnen)

    # Im Kurs mit Kursplan zählt „Tage“ die Übungen des Kursplans (`KursRepo.stand`)
    bedingung_namen = {
        **BEDINGUNG_NAMEN,
        **({TAGE: "Tage mit dem Kursplan"} if baut_plan else {}),
    }
    art_wahl = ft.Dropdown(
        label="Weiter geht es mit",
        value=bedingung.art,
        options=[ft.DropdownOption(key=k, text=t) for k, t in bedingung_namen.items()],
        on_select=art_gewaehlt,
        expand=True,
        data="bedingung_art",
    )
    # einmal gebaut: Die Zeile streckt das Auswahlfeld auf die Breite der Karte (Web-Foto)
    art_zeile = ft.Row(controls=[art_wahl])

    def bedingung_zeichnen() -> None:
        soll_feld.label = {
            SUMME: "Menge (Wiederholungen bzw. Sekunden)",
            TAGE: "Tage",
            MESSUNG: "Minuten",
        }.get(bedingung.art, "Soll")
        bed_felder()
        bedingung_spalte.controls = [
            art_zeile,
            *([bed_uebung, bed_feld] if bedingung.art == SUMME else []),
            *([soll_feld] if bedingung.art != GELESEN else []),
        ]

    def bedingung_lesen() -> Bedingung:
        try:
            soll = float(str(soll_feld.value or "0").replace(",", "."))
        except ValueError:
            soll = 0.0
        return Bedingung(
            art=bedingung.art,
            exercise_id=str(bed_uebung.value or "") if bedingung.art == SUMME else "",
            feld=str(bed_feld.value or "reps") if bedingung.art == SUMME else "reps",
            soll=soll if bedingung.art != GELESEN else 0.0,
        )

    # -- Speichern ------------------------------------------------------------------------

    def stand() -> tuple[Any, ...]:
        return (
            (titel_feld.value or "").strip(),
            [b.to_dict() for b in bloecke],
            [v.to_dict() for v in plaene],
            bedingung_lesen().to_dict(),
            {k: [b.to_dict() for b in liste] for k, liste in andere.items()},
        )

    ausgang = {"stand": stand()}

    def speichern() -> str | None:
        name = " ".join((titel_feld.value or "").split())
        b = bedingung_lesen()
        grund: str | None = None
        if not name:
            grund = "Das Kapitel braucht einen Titel."
        elif b.art != GELESEN and b.soll <= 0:
            grund = "Die Bedingung braucht ein Soll größer 0."
        elif b.art == SUMME and not b.exercise_id:
            grund = "Die Bedingung „Menge“ braucht eine Übung."
        # Die beiden nächsten Prüfungen gelten nur ohne Kursplan: Baut der Kurs einen Plan,
        # zählt „Tage“ dessen Übungen (`KursRepo.stand`), und Test und Auswahl liefern nur Wert
        # und Wahl für die Bausteine (`docs/plan_kurs_ablauf.md` §11.2) — ohne Kapitelplan
        elif (
            b.art == TAGE
            and not baut_plan
            and not plaene
            and not any(x.art == AUSWAHL for x in bloecke)
        ):
            grund = "„Tage“ zählt die Pläne des Kapitels — es hat keinen."
        elif not baut_plan and any(x.art in (TEST, AUSWAHL) for x in bloecke) and not plaene:
            grund = "Test und Auswahl brauchen einen Plan im Kapitel."
        fehler.value = grund or ""
        fehler.visible = grund is not None
        with contextlib.suppress(Exception):
            fehler.update()
        if grund is not None:
            return grund
        ziel = kurs.kapitel_mit(kapitel.id)
        if ziel is None:
            return "Das Kapitel gibt es nicht mehr."
        ziel.titel, ziel.bloecke, ziel.plaene, ziel.bedingung = name, list(bloecke), list(plaene), b
        for kapitel_id, liste in andere.items():  # was ein Löschen hier dort nach sich zog
            anderes = kurs.kapitel_mit(kapitel_id)
            if anderes is not None:
                anderes.bloecke = list(liste)
        state.kurse.speichern(kurs)
        ausgang["stand"] = stand()
        return None

    async def zurueck(_e: Any = None) -> None:
        await page.push_route(f"/kurse/{kurs.id}/bearbeiten")

    async def speichern_und_gehen(_e: Any = None) -> None:
        if speichern() is None:
            page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
            await zurueck()

    bloecke_zeichnen()
    bausteine_zeichnen()
    plaene_zeichnen()
    bedingung_zeichnen()
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Kapitel bearbeiten", abbrechen=zurueck, speichern=speichern_und_gehen
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        titel_feld,
                        fehler,
                        titel("Im Kapitel — was man liest und tut"),
                        block_spalte,
                        titel("Am Plan — was sich ändert"),
                        baustein_spalte,
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.OutlinedButton(
                                    "Im Kapitel",
                                    icon=ft.Icons.ADD,
                                    expand=True,
                                    on_click=lambda: dazu_zeigen("lesen"),
                                    data="block_dazu",
                                ),
                                # „+ Am Plan“ nur, wenn der Kurs einen Plan baut — sonst steht
                                # im Abschnitt darüber der Weg dorthin (`KEIN_KURSPLAN`)
                                *(
                                    [
                                        ft.OutlinedButton(
                                            "Am Plan",
                                            icon=ft.Icons.ADD,
                                            expand=True,
                                            on_click=lambda: dazu_zeigen("plan"),
                                            data="baustein_dazu",
                                        )
                                    ]
                                    if baut_plan
                                    else []
                                ),
                            ],
                        ),
                        dazu_lesen,
                        *([dazu_plan] if baut_plan else []),
                        karte(
                            titel("Pläne dieses Kapitels"),
                            plan_spalte,
                            ft.Row(
                                controls=[
                                    ft.TextButton(
                                        "Plan übernehmen …",
                                        icon=ft.Icons.PLAYLIST_ADD,
                                        on_click=plan_waehlen,
                                        data="plan_uebernehmen",
                                    )
                                ]
                            ),
                            hinweis(
                                "Der Kurs baut einen Plan, den die Bausteine oben ändern. Ein "
                                "Plan hier entsteht zusätzlich — als Kapitelplan, der mit dem "
                                "Kapitel endet."
                                if baut_plan
                                else "Der Plan entsteht für jede Person, die das Kapitel "
                                "erreicht — mit Test oder Auswahl erst mit „Plan anlegen“."
                            ),
                        ),
                        karte(titel("Weiter, wenn …"), bedingung_spalte),
                    ],
                )
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: stand() != ausgang["stand"],
        speichern=speichern,
        danach=zurueck,
    )


__all__ = [
    "antworten_lesen",
    "antworten_text",
    "art_name",
    "block_fehler",
    "block_kurz",
    "folgen_scroll",
    "folgen_zeilen",
    "kapitel_bearbeiten",
    "kurs_anlegen",
    "kurs_bearbeiten",
    "kurs_kopieren",
]
