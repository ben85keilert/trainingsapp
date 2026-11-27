"""Die Blöcke eines Kurskapitels zeichnen (Ben, 12.11.2026, `core/kursbloecke.py`).

Text, Medium, Frage, Test und Auswahl stehen untereinander auf der Seite des Kapitels:

- Eine **Frage** erklärt: Antippen zeigt den Hinweis der Antwort. Nichts wird gespeichert.
- Ein **Test** zeigt den jüngsten Eintrag der Übung seit dem Erreichen des Kapitels und führt
  zur Übung; der Wert wird das Ziel im Kapitelplan. Mit ``aus`` misst er **die gewählte**
  Übung einer Auswahl (Ben, 16.11.2026): Ohne Wahl steht nur die Aufforderung da, mit einer
  Gewählten sieht die Karte aus wie beim festen Test, mit mehreren hat jede ihre Zeile — und
  die Karte folgt, wenn die Wahl sich ändert (`gemessene_uebungen`, `wert_schluessel`).
  Hat der Test eine **Vorgabe** (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §3.3, Skizze T4),
  ist er ein Lauf mit der Uhr: Die Karte nennt Übung und Vorgabe („Käfer: bis Anstrengung
  7“), der Knopf heißt „Test starten“ bzw. „Nochmal“ und öffnet den Testlauf
  (`views/kurs_testlauf.py`, ``test_starten``), und nach dem Lauf steht neben dem Wert klein, was
  er sonst gemessen hat („in 1:12 · Anstrengung 7“, `core.kurstest.neben_text`). Ohne Vorgabe
  bleibt die Karte, wie sie war — außer der Test ist **gestaltet** (Ben, 16.11.2026: „Der Test
  muss flexibel gestaltet werden können“): Jeder Test mit `Block.laeuft` ist ein Lauf mit „Test
  starten“, und die Karte sagt in einem Satz, wie er läuft — Timer, Takt, Ausführung
  (`core.kurstest.lauf_satz`).
  **Wert für den Plan** (Ben, 17.11.2026, W3): Wird aus dem Wert ein Ziel im Plan, steht
  neben „Nochmal“ **„Wert ändern“** — die Karte `components/planwert.py` klappt in der
  Testkarte auf (ganz · Anteil · von Hand), „Übernehmen“ meldet die Wahl an die Ansicht
  (``wert_waehlen``). Eine getroffene Wahl steht unter dem Wert („Für den Plan: 20 Wdh. — von
  Hand“).
- Eine **Auswahl** hält die gewählten Übungen, bis „Plan anlegen“ gedrückt ist — danach ist
  sie fest (der Plan lässt sich von Hand ändern). Beginnt der Kurs von vorn, wird neu gewählt;
  „Wie beim letzten Mal“ belegt die Wahl des früheren Durchlaufs vor (Ben, 16.11.2026).
  Die noch offene Wahl überlebt das Verlassen des Kapitels (P212): Die Ansicht bringt sie als
  ``vorwahl`` wieder mit und hält sie über ``bei_wahl`` für die Sitzung (`AppState.kurs_wahl`).

In einem Kurs mit **Kursplan** (``kursplan=True``; Ben, 16.11.2026, `docs/plan_kurs_ablauf.md`
§11.5) liefern Test und Auswahl nur Wert und Wahl; was daraus am Plan wird, steht in der
Sammelkarte (`components/kursplan_karte.py`). „Plan anlegen“ gibt es dort nicht (die Ansicht
ruft ohne ``anlegen``) — außer das Kapitel hat daneben eigene Plan-Vorlagen. Fest ist eine
Auswahl, sobald ihre Wahl im Kursplan steht (``feste_wahl``); jede Änderung der Wahl meldet
``bei_wahl``, damit die Ansicht die Karte neu rechnet. Die Bausteine (``plan_…``) zeichnet
dieses Modul nicht — aus ihnen wird die Sammelkarte.

Die Rechnung steht in `core/kursbloecke.py`; hier wird nur gezeichnet.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from trainingsapp.core import kurstest
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    FRAGE,
    MEDIUM,
    TEST,
    TEXT,
    Block,
    Gegeben,
    Planwert,
    fertig,
    gemessene_uebungen,
    ist_vorgabe,
    wenn_stand,
    wert_schluessel,
    ziel_im_plan,
)
from trainingsapp.core.models import Exercise, SessionEntry, lokaler_tag
from trainingsapp.core.result_spec import FieldSpec, basis_key, vorrat_feld
from trainingsapp.core.tagesbilanz import menge_text
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kursfrage import frage_karte
from trainingsapp.ui.components.medienkarte import medienkarte
from trainingsapp.ui.components.planwert import planwert_karte

#: Die Aufforderung eines Tests „der gewählten“ ohne eigenen Titel, solange keine oder mehr
#: als eine Übung gewählt ist — mit genau einer steht ihr Name da („Käfer: was schaffst du?“)
OHNE_TITEL = f"Deine Auswahl: {kurstest.OHNE_VORGABE}"


def feld_von(uebung: Exercise | None, key: str) -> FieldSpec:
    """Das Feld des Tests — wie die Übung es nennt, sonst das aus dem Vorrat."""
    if uebung is not None:
        for f in uebung.result_spec.fields:
            if f.key == key:
                return f
    feld = vorrat_feld(basis_key(key)) or vorrat_feld("hold")
    assert feld is not None  # „hold“ steht im Vorrat
    return feld


def satzende(text: str) -> str:
    """``text`` als Ende eines Satzes — ohne zweiten Punkt, wenn er schon mit einem endet
    („15 Wdh.“).

    >>> satzende("48s Haltezeit"), satzende("15 Wdh.")
    ('48s Haltezeit.', '15 Wdh.')
    """
    return text if text.endswith(".") else f"{text}."


def stelle_von(state: Any, block_id: str) -> ft.ScrollKey:
    """Die Marke eines Blocks im Kapitel — je Aufbau der Ansicht eine eigene (zwei Ansichten
    desselben Kapitels stehen beim Wechsel kurz nebeneinander)."""
    nummer = getattr(state, "route_nummer", 0)
    return ft.ScrollKey(f"kursblock-{block_id}-{nummer}")  # type: ignore[call-arg]


@dataclass
class KapitelBloecke:
    """Die gezeichneten Blöcke und die Wahl der Person."""

    controls: list[ft.Control]
    #: Je Auswahl-Block die gewählten Übungen, in der Reihenfolge des Antippens
    wahl: dict[str, list[str]] = field(default_factory=dict)
    #: „Plan anlegen“ — ``None``, wenn das Kapitel keinen Test und keine Auswahl hat
    anlegen: ft.Control | None = None


def kapitel_bloecke(
    page: Any,
    state: Any,
    bloecke: Sequence[Block],
    *,
    katalog: Mapping[str, Exercise],
    werte: Mapping[str, float],
    angelegt: bool,
    offen: bool,
    browser: Any = None,
    text_bauen: Callable[[str], ft.Control] | None = None,
    zur_uebung: Callable[[str], Callable[..., Any]] | None = None,
    anlegen: Callable[[Mapping[str, Sequence[str]]], Any] | None = None,
    letzte_wahl: Mapping[str, Sequence[str]] | None = None,
    kursplan: bool = False,
    feste_wahl: Mapping[str, Sequence[str]] | None = None,
    bei_wahl: Callable[[], Any] | None = None,
    vorwahl: Mapping[str, Sequence[str]] | None = None,
    test_starten: Callable[[Block, str], Callable[..., Any]] | None = None,
    eintraege: Mapping[str, SessionEntry] | None = None,
    laufender_test: tuple[str, str] | None = None,
    planwerte: Mapping[str, Planwert] | None = None,
    ziel_tests: Collection[str] | None = None,
    anteil_von: Callable[[Block], float] | None = None,
    wert_waehlen: Callable[[Block, str, Planwert | None], Any] | None = None,
    antworten: Mapping[str, Gegeben] | None = None,
    antwort_geben: Callable[[str, Gegeben], Any] | None = None,
) -> KapitelBloecke:
    """Die Controls zu ``bloecke``. ``werte``: je Test-Block der Wert aus dem Eintrag
    (`KursRepo.testwerte` — bei einem Test „der gewählten“ je Übung der Auswahl einer);
    ``angelegt``: die Kapitelpläne gibt es schon (Auswahl fest); ``offen``: das Kapitel ist
    dran — sonst nur lesen. ``text_bauen`` macht aus Markdown ein Control (die Ansicht kennt
    die Regeln für Links und Bilder), ``zur_uebung`` den Weg zur Übung, ``anlegen`` bekommt
    die Wahl. ``letzte_wahl``: je Auswahl-Block, was im früheren Durchlauf des Kurses gewählt
    war — dann bietet der Block „Wie beim letzten Mal“ an (nur eine Vorbelegung).

    ``kursplan``: Der Kurs baut einen Kursplan — die Texte nennen die Sammelkarte, und fest
    ist eine Auswahl nicht mit ``angelegt``, sondern sobald ihre Wahl im Kursplan steht.
    ``feste_wahl``: je Auswahl-Block, was davon schon im Kursplan steht — diese Chips sind
    gewählt und gesperrt; `KapitelBloecke.wahl` hält nur, was die Person darüber hinaus
    antippt. Nennt ``feste_wahl`` auch Auswahlen **früherer Kapitel**, gilt für einen Test,
    der sich auf so eine bezieht, was dort übernommen ist. ``bei_wahl`` wird nach jeder
    Änderung der Wahl gerufen.

    ``vorwahl``: was die Person in dieser Sitzung schon gewählt, aber noch nicht übernommen
    hat (Ben, 16.11.2026, P212: Die Wahl überlebt das Verlassen des Kapitels,
    `AppState.kurs_wahl`) — je Auswahl-Block die Übungen. Die Chips zeigen sie als gewählt,
    änderbar wie frisch angetippt; was nicht mehr passt (fest, nicht mehr in der Auswahl,
    zu viele), fällt weg. `KapitelBloecke.wahl` ist danach der bereinigte Stand.

    **Ohne ``anlegen`` gibt es den Knopf „Plan anlegen“ nicht** — so ruft die Ansicht ein
    Kapitel im Kursplan-Kurs, das keine eigenen Plan-Vorlagen hat: Dort wird in der
    Sammelkarte übernommen. Hat so ein Kapitel doch eigene Vorlagen, bleibt der Knopf für sie
    (Kapitelpläne neben dem Kursplan, `KursRepo.kapitel_erreichen`).

    **Tests, die als Lauf gemacht werden** (`Block.laeuft`: mit Vorgabe oder gestaltet):
    ``test_starten(block, übung)`` gibt den Handler, der den Testlauf startet und öffnet
    (`views.kurs_testlauf.starter` — ein gestalteter öffnet sich bereit) — ohne ihn führt der
    Knopf wie bisher zur Übung. ``eintraege``: je Test der jüngste Eintrag unter den
    Schlüsseln von ``werte`` (`KursRepo.testeintraege`) — daraus steht neben dem Wert, was der
    Lauf sonst gemessen hat. ``laufender_test``: (Block, Übung) des Testlaufs, der gerade
    läuft oder auf sein Ergebnis wartet — dort heißt der Knopf „Zum Test“.

    **Wert für den Plan** (W3, Ben 17.11.2026): ``planwerte`` — je Test, unter den Schlüsseln
    von ``werte``, die Wahl der Person (`KursRepo.planwerte`); ``ziel_tests`` — die IDs der
    Tests, aus deren Wert ein Ziel im Plan wird (`core.kursbloecke.wert_wird_ziel`): Nur sie
    bieten „Wert ändern“; ``anteil_von(block)`` — der Anteil, mit dem der Kurs rechnet (die
    Vorgabe der Karte, `core.kursbloecke.anteil_vorgabe`; ohne: der Faktor des Tests);
    ``wert_waehlen(block, übung, wahl)`` — „Übernehmen“: die Ansicht merkt die Wahl
    (``None``: zurück zur Vorgabe des Kurses) und zeichnet neu. Ohne ``wert_waehlen`` gibt es
    „Wert ändern“ nicht.

    **Nur ausprobieren** (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §10.1): Ein Test, der
    nicht in ``ziel_tests`` steht, ist freiwillig — die Karte heißt „Übung machen“, der Knopf
    „Übung starten“, und „Plan anlegen“ wartet nicht auf ihn. ``ziel_tests=None`` (die
    Ansicht sagt nichts dazu): jeder Test ist Pflicht, wie bisher.

    **Fragen und Folgen** (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4, §10.3):
    ``antworten`` — die gespeicherten Antworten des Kurses (`KursRepo.antworten`). Ein Block
    mit ``wenn`` steht nur da, wenn seine Bedingungen gelten (`wenn_stand`); fehlt eine
    Antwort, bleibt er verborgen. Eine Frage in den Arten des Ablaufs (`Block.frage`) meldet
    ihre Antwort an ``antwort_geben(name, antwort)`` — die Ansicht speichert und zeichnet neu
    (dann erscheint, was an der Antwort hängt). Ohne ``antwort_geben`` ist sie nur zu lesen."""
    ergebnis = KapitelBloecke(controls=[])
    gegeben = antworten or {}

    def an_stelle(block: Block, control: ft.Control) -> ft.Control:
        """``control`` mit einer Marke, zu der die Ansicht rollen kann (der Fußknopf „nächster
        Schritt“, `stelle_von`) — die Hülle entsteht einmal und wird nie ersetzt."""
        return ft.Container(content=control, key=stelle_von(state, block.id))

    # was hier gilt: Blöcke ohne Bedingung und die, deren Bedingungen erfüllt sind. Bausteine
    # zeichnet diese Komponente nicht — die Sammelkarte rechnet ihr ``wenn`` selbst
    bloecke = [b for b in bloecke if not b.wenn or wenn_stand(b.wenn, gegeben) is True]

    def freiwillig(block: Block) -> bool:
        return ziel_tests is not None and block.id not in ziel_tests

    wahl = ergebnis.wahl
    #: je Auswahl-Block, was schon im Kursplan steht (nur Übungen dieser Auswahl)
    im_kursplan: dict[str, list[str]] = {
        b.id: [u for u in (feste_wahl or {}).get(b.id, ()) if u in b.uebungen]
        for b in bloecke
        if b.art == AUSWAHL
    }
    #: je Auswahl-Block: wie viele Übungen noch frei wählbar sind — und ob sie fest ist
    frei_je: dict[str, int] = {}
    fest_je: dict[str, bool] = {}
    # Die Wahl steht, bevor gezeichnet wird: Ein Test mit ``aus`` darf vor seiner Auswahl
    # stehen und muss sie trotzdem kennen
    for b in bloecke:
        if b.art != AUSWAHL or b.id in wahl:
            continue
        # Kursplan: was schon im Plan steht, ist fest; frei bleibt der Rest bis zur Anzahl
        frei_je[b.id] = max(b.anzahl - len(im_kursplan[b.id]), 0)
        fest_je[b.id] = (
            (angelegt and not kursplan)
            or not offen
            or (bool(im_kursplan[b.id]) and frei_je[b.id] == 0)
        )
        wahl[b.id] = []
        # Was die Sitzung an offener Wahl mitbringt (P212) — nur, was hier noch wählbar ist;
        # sind es zu viele, bleiben die zuletzt angetippten (wie beim Antippen selbst)
        if not fest_je[b.id] and frei_je[b.id]:
            mitgebracht = [
                u
                for u in dict.fromkeys((vorwahl or {}).get(b.id, ()))
                if u in b.uebungen and u in katalog and u not in im_kursplan[b.id]
            ]
            wahl[b.id].extend(mitgebracht[-frei_je[b.id] :])
    #: Tests mit ``aus`` zeichnen sich neu, wenn sich die Wahl ändert
    testkarten: list[Callable[[], None]] = []
    #: die Tests, deren Karte „Wert für den Plan“ gerade offen ist (`wert_schluessel`) — und
    #: wie jede Testkarte sich neu zeichnet (Block-ID → Funktion)
    wert_offen: set[str] = set()
    test_zeichnen: dict[str, Callable[[], None]] = {}
    knopf = ft.FilledButton(
        "Plan anlegen",
        icon=ft.Icons.PLAYLIST_ADD_CHECK,
        data="plan_anlegen",
        disabled=True,
    )
    fehlt = ft.Text(size=12, opacity=0.7)

    def wirksam() -> dict[str, list[str]]:
        """Die Wahl, wie sie gilt — für die Tests („die gewählte“) und für „Plan anlegen“: je
        Auswahl dieses Kapitels, was im Kursplan fest ist und was die Person dazu angetippt
        hat; dazu, was aus Auswahlen **früherer Kapitel** im Kursplan steht (``feste_wahl``).
        Ohne Kursplan ist das `KapitelBloecke.wahl`."""
        frueher = {bid: list(u) for bid, u in (feste_wahl or {}).items() if bid not in wahl}
        hier = {bid: [*im_kursplan.get(bid, ()), *dazu] for bid, dazu in wahl.items()}
        return {**frueher, **hier}

    def stand_zeigen() -> None:
        bereit = fertig(bloecke, werte, wirksam(), ziel_tests)
        knopf.disabled = not bereit
        fehlt.value = "" if bereit else "Erst den Test machen und die Auswahl treffen."
        fehlt.visible = not bereit
        with contextlib.suppress(Exception):
            knopf.update()
            fehlt.update()

    def frage(block: Block) -> ft.Control:
        antwort = ft.Text(size=13, visible=False)
        knoepfe: list[ft.OutlinedButton] = []

        def tippen(n: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                a = block.antworten[n]
                for i, k in enumerate(knoepfe):
                    k.icon = (
                        (ft.Icons.CHECK if a.richtig else ft.Icons.CIRCLE_OUTLINED)
                        if i == n
                        else None
                    )
                antwort.value = a.hinweis or (
                    "Genau." if a.richtig else "Schau noch einmal — tippe eine andere an."
                )
                antwort.visible = True
                with contextlib.suppress(Exception):
                    spalte.update()

            return handler

        for n, a in enumerate(block.antworten):
            knoepfe.append(
                ft.OutlinedButton(a.text, on_click=tippen(n), data=("antwort", block.id, n))
            )
        spalte = karte(
            ft.Text(block.titel, weight=ft.FontWeight.W_600),
            *([ft.Text(block.text, size=13)] if block.text else []),
            *knoepfe,
            antwort,
        )
        return spalte

    def eine(uebungen: Sequence[str]) -> Exercise | None:
        """Die eine Übung, die der Test misst — ``None`` ohne oder mit mehreren: Was erst
        die Übung sagt (ihr Timer, ihr Takt), steht dann allgemein da."""
        return katalog.get(uebungen[0]) if len(uebungen) == 1 else None

    def lauf_titel(block: Block, uid: str | None = None) -> str:
        """Die Überschrift eines Tests, der als Lauf gemacht wird, ohne eigenen Titel: mit
        Vorgabe „Käfer: bis Anstrengung 7“ — ohne oder mit mehreren Übungen „Deine Auswahl:
        …“. Gilt keine Vorgabe (ein gestalteter Test ohne; eine Zeit neben einem Timer), die
        Aufforderung wie beim Test ohne Lauf — eine Stelle mit der Vorschau im Kurs-Editor
        (`core.kurstest.karten_ueberschrift`)."""
        uebung = katalog.get(uid) if uid is not None else None
        name = uebung.name if uebung is not None else "Übung fehlt" if uid else "Deine Auswahl"
        return kurstest.karten_ueberschrift(block, name, uebung)

    def anleitung(block: Block, uebungen: Sequence[str]) -> list[ft.Control]:
        """Unter der Überschrift eines Tests, der als Lauf gemacht wird: der eigene Text —
        sonst, was zu tun ist und was die App misst (`core.kurstest.anleitung`). Ein
        gestalteter Test sagt darunter in einem Satz, wie er läuft: Timer, Takt, Ausführung
        (`core.kurstest.lauf_satz`)."""
        da = [katalog[u] for u in uebungen if u in katalog]
        uebung = eine(uebungen)
        profil = kurstest.uhr_fuer(block, uebung)
        zaehlt_wdh = not da or any(kurstest.felder(block, u).wdh is not None for u in da)
        # Nur der Text des Kurses (Ben, 27.11.2026: „diese automatischen Texte müssten alle
        # raus. Beim Kursaufbau muss man eh die Texte eingeben“) — kein Satz der App darüber,
        # was sie misst oder wie der Lauf läuft; das steht im Lauf selbst
        del da, uebung, profil, zaehlt_wdh
        return [ft.Text(block.text, size=13)] if block.text else []

    def neben(block: Block, uid: str) -> str:
        """Was der Lauf neben dem Wert des Tests gemessen hat — „in 1:12 · Anstrengung 7“ —
        und, bei einem gestalteten Test, wie er gemacht wurde („links · 10 kg“)."""
        eintrag = (eintraege or {}).get(wert_schluessel(block, uid))
        if eintrag is None:
            return ""
        gemessen = kurstest.neben_text(
            block, kurstest.lauf_aus(block, eintrag.result, eintrag.spec_snapshot)
        )
        wie = (
            kurstest.ausfuehrung_aus(eintrag.result, eintrag.spec_snapshot)
            if block.gestaltet
            else ""
        )
        return " · ".join(t for t in (gemessen, wie) if t)

    def wann(block: Block, uid: str) -> str:
        """„Dein Test von heute.“ — an einem anderen Tag mit Datum."""
        eintrag = (eintraege or {}).get(wert_schluessel(block, uid))
        tag = lokaler_tag(eintrag.started_at) if eintrag and eintrag.started_at else None
        heute = state.heute() if callable(getattr(state, "heute", None)) else None
        was = "Dein Lauf" if freiwillig(block) else "Dein Test"
        if tag is None:
            return f"{was}."
        return f"{was} von heute." if tag == heute else f"{was} vom {tag:%d.%m.}."

    def zur_uebung_knopf(block: Block, uid: str, getestet: bool) -> ft.Control | None:
        """„Zur Übung“ bzw. „Nochmal“ zu **dieser** Übung — ``None``, wo nur gelesen wird. Ein
        Test, der als Lauf gemacht wird (`Block.laeuft`), startet stattdessen seinen Lauf: „Test
        starten“ bzw. „Nochmal“, und „Zum Test“, solange er läuft oder auf sein Ergebnis
        wartet."""
        if uid not in katalog or not offen or (angelegt and not kursplan):
            return None
        if block.laeuft and test_starten is not None:
            laeuft = laufender_test == (block.id, uid)
            return ft.FilledTonalButton(
                ("Zur Übung" if freiwillig(block) else "Zum Test")
                if laeuft
                else "Nochmal"
                if getestet
                else "Übung starten"
                if freiwillig(block)
                else "Test starten",
                icon=ft.Icons.TIMER_OUTLINED if laeuft else ft.Icons.PLAY_ARROW,
                on_click=test_starten(block, uid),
                data=("test_starten", block.id, uid) if block.aus else ("test_starten", block.id),
            )
        if zur_uebung is None:
            return None
        return ft.FilledTonalButton(
            "Nochmal" if getestet else "Zur Übung",
            icon=ft.Icons.PLAY_ARROW,
            on_click=zur_uebung(uid),
            # der Test „der gewählten“ nennt die Übung dazu: Es können mehrere sein
            data=("test_oeffnen", block.id, uid) if block.aus else ("test_oeffnen", block.id),
        )

    def darf_wert(block: Block, uid: str) -> bool:
        """Gibt es hier „Wert ändern“? Nur im offenen Kapitel, an einem Test, aus dessen Wert
        ein Ziel wird — und im Kapitelplan nur, solange der Plan nicht angelegt ist (danach
        steht das Ziel im Plan und wird dort geändert)."""
        return (
            wert_waehlen is not None
            and offen
            and block.id in (ziel_tests or ())
            and uid in katalog
            and not (angelegt and not kursplan)
        )

    def wert_umschalten(block: Block, uid: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            wert_offen.symmetric_difference_update({wert_schluessel(block, uid)})
            if (zeichnen := test_zeichnen.get(block.id)) is not None:
                zeichnen()

        return handler

    def wert_knopf(block: Block, uid: str, *, klein: bool = False) -> ft.Control:
        """„Wert ändern“ — öffnet und schließt die Karte „Wert für den Plan“ in der Testkarte."""
        marke = ("wert_aendern", block.id, uid) if block.aus else ("wert_aendern", block.id)
        if klein:  # in der Zeile je Übung ist kein Platz für zwei Textknöpfe
            return ft.IconButton(
                ft.Icons.TUNE,
                tooltip="Wert für den Plan ändern",
                on_click=wert_umschalten(block, uid),
                data=marke,
            )
        return ft.TextButton(
            "Wert ändern", icon=ft.Icons.TUNE, on_click=wert_umschalten(block, uid), data=marke
        )

    def wert_karte(block: Block, uid: str, wert: float) -> ft.Control:
        """Die offene Karte „Wert für den Plan“ zu einem Test: vorgewählt die Wahl der Person,
        sonst die Vorgabe des Kurses; „Übernehmen“ meldet sie der Ansicht."""
        schluessel = wert_schluessel(block, uid)
        anteil = anteil_von(block) if anteil_von is not None else block.faktor

        def uebernehmen(_e: Any = None) -> Any:
            wahl = gezeichnete.wahl()
            wert_offen.discard(schluessel)
            if wert_waehlen is None or wahl is None:
                return None
            # dasselbe wie die Vorgabe des Kurses: nichts zu merken — er rechnet wie bisher
            return wert_waehlen(block, uid, None if ist_vorgabe(wahl, wert, anteil) else wahl)

        gezeichnete = planwert_karte(
            page,
            feld=feld_von(katalog.get(uid), block.feld),
            test_wert=wert,
            vorgabe=anteil,
            gewaehlt=(planwerte or {}).get(schluessel),
            schluessel=schluessel,
            knoepfe=[
                ft.TextButton(
                    "Abbrechen",
                    on_click=wert_umschalten(block, uid),
                    data=("planwert_abbrechen", schluessel),
                ),
                ft.FilledButton(
                    "Übernehmen", on_click=uebernehmen, data=("planwert_uebernehmen", schluessel)
                ),
            ],
        )
        return gezeichnete.control

    def fuer_den_plan(block: Block, uid: str, feld: FieldSpec) -> ft.Control | None:
        """„Für den Plan: 20 Wdh. — von Hand“ unter dem Wert des Tests, wenn die Person
        gewählt hat — ``None`` mit der Vorgabe des Kurses."""
        gewaehlt = (planwerte or {}).get(wert_schluessel(block, uid))
        if gewaehlt is None:
            return None
        return ft.Text(
            f"Für den Plan: {menge_text(feld, gewaehlt.wert)} — {kurstest.wahl_text(gewaehlt)}",
            size=14,
            weight=ft.FontWeight.W_600,
            data=("planwert", block.id, uid) if block.aus else ("planwert", block.id),
        )

    def test_inhalt(block: Block) -> list[ft.Control]:
        """Was in der Testkarte steht. Welche Übungen der Test misst und wo ihr Wert steht,
        sagen `gemessene_uebungen` und `wert_schluessel`: die feste — oder, mit ``aus``, die
        Gewählten einer Auswahl (Ben, 16.11.2026)."""
        gemessen = gemessene_uebungen(block, wirksam())
        teile: list[ft.Control] = [
            titel("Übung machen · freiwillig" if freiwillig(block) else "Test")
        ]
        #: mit Vorgabe oder gestaltet ist der Test ein Lauf mit der Uhr (`Block.laeuft`) — die
        #: Karte nennt Übung und Vorgabe und sagt, wie er läuft
        als_lauf = block.laeuft
        beschreibung: list[ft.Control] = (
            anleitung(block, gemessen)
            if als_lauf
            else [ft.Text(block.text, size=13)]
            if block.text
            else []
        )

        if not gemessen:
            # ``aus`` und keine Wahl, die hier gilt: nur die Aufforderung — ohne Übung kein
            # Knopf. Der Hinweis sagt, warum
            if block.aus not in wahl and kursplan:
                wo = (
                    "Der Test gilt der Übung, die du in einem früheren Kapitel wählst — "
                    "übernimm deine Wahl dort zuerst in deinen Kursplan."
                )
            elif block.aus not in wahl:
                # Kapitelpläne: Die Wahl eines früheren Kapitels steht nirgends, wo dieses
                # sie ablesen könnte
                wo = (
                    "Der Test gilt der Übung, die du in einem früheren Kapitel gewählt hast. "
                    "Welche das war, kann dieses Kapitel nicht ablesen."
                )
            elif angelegt and not kursplan:
                # die Auswahl ist fest und zeigt (wie ihre Chips) nicht mehr, was gewählt war
                wo = "Der Plan ist angelegt — das Ziel aus deinem Test steht darin."
            elif fest_je.get(block.aus):
                wo = "Der Test gilt der Übung, die du wählst."  # hier lässt sich nicht wählen
            else:
                wo = "Triff zuerst deine Auswahl — der Test gilt der Übung, die du wählst."
            fehlt_wahl = hinweis(wo)
            fehlt_wahl.data = ("test_wahl_fehlt", block.id)
            return [
                *teile,
                ft.Text(
                    block.titel or (lauf_titel(block) if als_lauf else OHNE_TITEL),
                    weight=ft.FontWeight.W_600,
                ),
                *beschreibung,
                fehlt_wahl,
            ]

        if len(gemessen) == 1:
            # eine Übung — die feste oder die eine Gewählte: der Wert groß, darunter der Knopf
            uid = gemessen[0]
            uebung = katalog.get(uid)
            feld = feld_von(uebung, block.feld)
            name = uebung.name if uebung is not None else "Übung fehlt"
            teile.append(
                ft.Text(
                    block.titel
                    or (lauf_titel(block, uid) if als_lauf else f"{name}: {kurstest.OHNE_VORGABE}"),
                    weight=ft.FontWeight.W_600,
                )
            )
            teile.extend(beschreibung)
            wert = werte.get(wert_schluessel(block, uid))
            if wert is not None:
                gross = ft.Text(
                    menge_text(feld, wert),
                    size=28,
                    weight=ft.FontWeight.W_600,
                    data=("testwert", block.id, uid) if block.aus else "testwert",
                )
                daneben = neben(block, uid) if als_lauf else ""
                # T4: der Wert groß, daneben klein, was der Lauf sonst gemessen hat — bricht in
                # die nächste Zeile, wenn es nicht nebeneinander passt
                teile.append(
                    ft.Row(
                        wrap=True,
                        spacing=12,
                        run_spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            gross,
                            ft.Container(
                                padding=ft.Padding.only(bottom=5),
                                content=ft.Text(
                                    daneben,
                                    size=14,
                                    opacity=0.85,
                                    data=("testneben", block.id, uid) if block.aus else "testneben",
                                ),
                            ),
                        ],
                    )
                    if daneben
                    else gross
                )
                # Hat die Person den Wert für den Plan gewählt, steht er unter dem Testwert
                gewaehlt = (planwerte or {}).get(wert_schluessel(block, uid))
                if (zeile := fuer_den_plan(block, uid, feld)) is not None:
                    teile.append(zeile)
                # woher der Wert kommt: der Eintrag der Übung — als Lauf „Dein Test von heute“
                woher = wann(block, uid) if als_lauf else f"Dein Eintrag bei „{name}“."
                teile.append(
                    hinweis(
                        # im Kursplan-Kurs rechnet der Baustein (eigener Faktor, vielleicht
                        # eine andere Übung) — was daraus wird, sagt die Sammelkarte
                        f"{woher} Der Kurs merkt sich, was du eingetragen hast."
                        if freiwillig(block)
                        else f"{woher} Was daraus an deinem Plan wird, steht unten."
                        if kursplan
                        else f"{woher} Im Plan wird daraus das Ziel: "
                        f"{satzende(menge_text(feld, ziel_im_plan(block, wert, gewaehlt)))}"
                    )
                )
            elif not als_lauf:
                # ohne Lauf sagt die Karte, wo der Wert herkommt — an einem Lauf sagt es der Knopf
                teile.append(
                    hinweis(f"Noch kein Eintrag bei „{name}“, seit du dieses Kapitel öffnest.")
                )
            knoepfe: list[ft.Control] = []
            if (oeffnen := zur_uebung_knopf(block, uid, wert is not None)) is not None:
                knoepfe.append(oeffnen)
            if wert is not None and darf_wert(block, uid):
                knoepfe.append(wert_knopf(block, uid))
            if knoepfe:
                teile.append(ft.Row(wrap=True, spacing=8, run_spacing=4, controls=knoepfe))
            if wert is not None and wert_schluessel(block, uid) in wert_offen:
                teile.append(wert_karte(block, uid, wert))
            return teile

        # mehrere Gewählte: je Übung eine Zeile — Name, ihr Wert, ihr Knopf
        teile.append(
            ft.Text(
                block.titel or (lauf_titel(block) if als_lauf else OHNE_TITEL),
                weight=ft.FontWeight.W_600,
            )
        )
        teile.extend(beschreibung)
        for uid in gemessen:
            uebung = katalog.get(uid)
            feld = feld_von(uebung, block.feld)
            wert = werte.get(wert_schluessel(block, uid))
            oeffnen = zur_uebung_knopf(block, uid, wert is not None)
            # als Lauf: hinter dem Wert, was er sonst gemessen hat
            daneben = neben(block, uid) if als_lauf and wert is not None else ""
            # Kapitelplan: das Ziel in einer eigenen blassen Zeile — neben dem Knopf bräche
            # „30 Wdh. — im Plan das Ziel: 15 Wdh.“ mitten im Wert um (Web-Foto 16.11.2026)
            gewaehlt = (planwerte or {}).get(wert_schluessel(block, uid))
            ziel = ziel_im_plan(block, wert, gewaehlt) if wert is not None else 0
            ziel_zeile: list[ft.Control] = (
                [ft.Text(f"im Plan das Ziel: {menge_text(feld, ziel)}", size=12, opacity=0.7)]
                if wert is not None and not kursplan
                else []
            )
            # Kursplan: die Wahl der Person unter dem Wert (im Kapitelplan sagt es das Ziel)
            if kursplan and wert is not None and gewaehlt is not None:
                ziel_zeile = [
                    ft.Text(
                        f"für den Plan: {menge_text(feld, gewaehlt.wert)} — "
                        f"{kurstest.wahl_text(gewaehlt)}",
                        size=12,
                        opacity=0.85,
                        data=("planwert", block.id, uid),
                    )
                ]
            aendern = wert is not None and darf_wert(block, uid)
            teile.append(
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=2,
                            tight=True,
                            controls=[
                                ft.Text(
                                    uebung.name if uebung is not None else "Übung fehlt",
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    " · ".join(t for t in (menge_text(feld, wert), daneben) if t)
                                    if wert is not None
                                    else "noch kein Test"
                                    if als_lauf
                                    else "noch kein Eintrag",
                                    size=13,
                                    opacity=1.0 if wert is not None else 0.7,
                                    data=("testwert", block.id, uid),
                                ),
                                *ziel_zeile,
                            ],
                        ),
                        *([wert_knopf(block, uid, klein=True)] if aendern else []),
                        *([oeffnen] if oeffnen is not None else []),
                    ],
                )
            )
            if wert is not None and wert_schluessel(block, uid) in wert_offen:
                teile.append(wert_karte(block, uid, wert))
        was = "Deine Tests" if als_lauf else "Deine Einträge"
        teile.append(
            hinweis(
                f"{was}, seit du dieses Kapitel öffnest. Was daraus an deinem Plan "
                "wird, steht unten."
                if kursplan
                else f"{was}, seit du dieses Kapitel öffnest."
            )
        )
        return teile

    def test(block: Block) -> ft.Control:
        # Der Inhalt der Karte wird getauscht: „die gewählte“ folgt der Wahl, und „Wert
        # ändern“ klappt die Karte „Wert für den Plan“ auf und zu
        spalte = ft.Column(
            spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

        def zeichnen() -> None:
            spalte.controls = test_inhalt(block)
            with contextlib.suppress(Exception):
                spalte.update()

        spalte.controls = test_inhalt(block)
        test_zeichnen[block.id] = zeichnen
        if block.aus:
            testkarten.append(zeichnen)
        return karte(spalte)

    def auswahl(block: Block) -> ft.Control:
        gewaehlt = wahl[block.id]
        chips: dict[str, ft.Chip] = {}
        im_plan = im_kursplan[block.id]
        frei, fest = frei_je[block.id], fest_je[block.id]

        def gewaehlt_zeigen() -> None:
            for k, chip in chips.items():
                chip.selected = k in im_plan or k in gewaehlt
            with contextlib.suppress(Exception):
                reihe.update()
            for zeichnen in testkarten:  # Tests „der gewählten“ nennen jetzt eine andere
                zeichnen()
            stand_zeigen()
            if bei_wahl is not None:
                bei_wahl()

        def umschalten(uid: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                if uid in gewaehlt:
                    gewaehlt.remove(uid)
                else:
                    gewaehlt.append(uid)
                    while len(gewaehlt) > frei:  # die älteste Wahl weicht
                        gewaehlt.pop(0)
                gewaehlt_zeigen()

            return handler

        for uid in block.uebungen:
            uebung = katalog.get(uid)
            if uebung is None:
                continue
            chips[uid] = ft.Chip(
                label=ft.Text(uebung.name),
                selected=uid in im_plan or uid in gewaehlt,
                disabled=fest or uid in im_plan,
                on_select=umschalten(uid),
                data=("wahl", block.id, uid),
            )
        reihe = ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(chips.values()))
        # Kurs von vorn (Ben, 16.11.2026): die Wahl vom letzten Mal als Vorbelegung — die
        # Person tippt sie an, nichts ist von selbst gewählt
        frueher = [
            u for u in (letzte_wahl or {}).get(block.id, ()) if u in chips and u not in im_plan
        ]

        def wie_letztes_mal(_e: Any = None) -> None:
            gewaehlt[:] = frueher[:frei]
            gewaehlt_zeigen()

        letztes_mal: list[ft.Control] = (
            [
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Wie beim letzten Mal",
                            icon=ft.Icons.HISTORY,
                            tooltip=", ".join(katalog[u].name for u in frueher),
                            on_click=wie_letztes_mal,
                            data=("wie_letztes_mal", block.id),
                        )
                    ]
                )
            ]
            if frueher and not fest
            else []
        )
        return karte(
            ft.Text(
                block.titel or f"Wähle {block.anzahl} von {len(chips)}",
                weight=ft.FontWeight.W_600,
            ),
            *([ft.Text(block.text, size=13)] if block.text else []),
            reihe,
            *letztes_mal,
            hinweis(
                (
                    "Deine Wahl steht im Kursplan — ändern kannst du ihn in der Planverwaltung."
                    if im_plan and frei == 0
                    else "Was du wählst, kommt in deinen Kursplan — unten steht, was sich ändert."
                )
                if kursplan
                else "Deine Wahl gilt für die Übung, die du hier ausprobierst."
                if anlegen is None  # ein Kapitel ohne Plan (26.11.2026)
                else "Der Plan ist angelegt — ändern kannst du ihn in der Planverwaltung."
                if angelegt
                else "Mit zwei oder mehr stehen sie im Workout als Wege: Dort wählst du jedes "
                "Mal einen."
                if block.anzahl >= 2
                else "Die gewählte Übung kommt in den Plan."
            ),
        )

    def melder(name: str) -> Callable[[Gegeben], Any]:
        """Wohin die Antwort auf die Frage ``name`` geht — ohne ``antwort_geben`` nirgends."""

        def handler(antwort: Gegeben) -> Any:
            return antwort_geben(name, antwort) if antwort_geben is not None else None

        return handler

    for block in bloecke:
        if block.art == TEXT:
            if block.titel:
                ergebnis.controls.append(ft.Text(block.titel, size=18, weight=ft.FontWeight.W_600))
            if block.text:
                ergebnis.controls.append(
                    text_bauen(block.text) if text_bauen is not None else ft.Markdown(block.text)
                )
        elif block.art == MEDIUM and block.medium is not None:
            # die Medienkarte (Ben, 27.11.2026): im Kapitel eingebunden, nicht hinter einer Zeile
            ergebnis.controls.append(medienkarte(page, state, block.medium, browser=browser))
        elif block.art == FRAGE and block.frage is not None:
            ergebnis.controls.append(
                an_stelle(
                    block,
                    frage_karte(
                        block.frage,
                        gegeben.get(block.id),
                        melder(block.id),
                        kennung=block.id,
                        unter=block.text,
                        gesperrt=antwort_geben is None or not offen,
                    ),
                )
            )
        elif block.art == FRAGE:
            ergebnis.controls.append(frage(block))
        elif block.art == TEST:
            ergebnis.controls.append(an_stelle(block, test(block)))
        elif block.art == AUSWAHL:
            ergebnis.controls.append(auswahl(block))

    hat_eingabe = any(b.art in (TEST, AUSWAHL) for b in bloecke)
    # ohne ``anlegen`` kein Knopf: im Kursplan-Kurs übernimmt man in der Sammelkarte
    if anlegen is not None and hat_eingabe and offen and not angelegt:

        def druecken(_e: Any = None) -> Any:
            if fertig(bloecke, werte, wirksam(), ziel_tests):
                return anlegen(wirksam())
            return None

        knopf.on_click = druecken
        stand_zeigen()
        ergebnis.anlegen = ft.Column(spacing=4, tight=True, controls=[ft.Row([knopf]), fehlt])
        ergebnis.controls.append(ergebnis.anlegen)
    return ergebnis


__all__ = ["KapitelBloecke", "feld_von", "kapitel_bloecke"]
