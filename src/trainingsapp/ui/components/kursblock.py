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
  bleibt die Karte, wie sie war.
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
from collections.abc import Callable, Mapping, Sequence
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
    fertig,
    gemessene_uebungen,
    wert_schluessel,
    ziel_aus_test,
)
from trainingsapp.core.models import Exercise, SessionEntry, lokaler_tag
from trainingsapp.core.result_spec import FieldSpec, basis_key, vorrat_feld
from trainingsapp.core.tagesbilanz import menge_text
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.medienliste import medium_zeile

#: Die Aufforderung eines Tests „der gewählten“ ohne eigenen Titel, solange keine oder mehr
#: als eine Übung gewählt ist — mit genau einer steht ihr Name da („Käfer: was schaffst du?“)
OHNE_TITEL = "Deine Auswahl: was schaffst du?"


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

    **Tests mit Vorgabe** (`Block.vorgabe`): ``test_starten(block, übung)`` gibt den Handler,
    der den Testlauf startet und öffnet (`views.kurs_test.starter`) — ohne ihn führt der
    Knopf wie bisher zur Übung. ``eintraege``: je Test der jüngste Eintrag unter den
    Schlüsseln von ``werte`` (`KursRepo.testeintraege`) — daraus steht neben dem Wert, was der
    Lauf sonst gemessen hat. ``laufender_test``: (Block, Übung) des Testlaufs, der gerade
    läuft oder auf sein Ergebnis wartet — dort heißt der Knopf „Zum Test“."""
    ergebnis = KapitelBloecke(controls=[])
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
        bereit = fertig(bloecke, werte, wirksam())
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

    def vorgabe_titel(block: Block, uid: str | None = None) -> str:
        """Die Überschrift eines Tests mit Vorgabe ohne eigenen Titel: „Käfer: bis Anstrengung
        7“ — ohne oder mit mehreren Übungen „Deine Auswahl: …“."""
        assert block.vorgabe is not None
        uebung = katalog.get(uid) if uid is not None else None
        name = uebung.name if uebung is not None else "Übung fehlt" if uid else "Deine Auswahl"
        skala = (
            kurstest.skala_name(uebung.result_spec) if uebung is not None else kurstest.SKALA_NAME
        )
        return f"{name}: {kurstest.vorgabe_text(block.vorgabe, skala, satzanfang=False)}"

    def anleitung(block: Block, uebungen: Sequence[str]) -> ft.Control:
        """Der Satz unter der Überschrift eines Tests mit Vorgabe: der eigene Text — sonst,
        was zu tun ist und was die App misst (`core.kurstest.anleitung`)."""
        assert block.vorgabe is not None
        da = [katalog[u] for u in uebungen if u in katalog]
        zaehlt_wdh = not da or any(kurstest.felder(block, u).wdh is not None for u in da)
        return ft.Text(
            block.text or kurstest.anleitung(block.vorgabe, zaehlt_wdh=zaehlt_wdh), size=13
        )

    def neben(block: Block, uid: str) -> str:
        """Was der Lauf neben dem Wert des Tests gemessen hat — „in 1:12 · Anstrengung 7“."""
        eintrag = (eintraege or {}).get(wert_schluessel(block, uid))
        if eintrag is None:
            return ""
        return kurstest.neben_text(
            block, kurstest.lauf_aus(block, eintrag.result, eintrag.spec_snapshot)
        )

    def wann(block: Block, uid: str) -> str:
        """„Dein Test von heute.“ — an einem anderen Tag mit Datum."""
        eintrag = (eintraege or {}).get(wert_schluessel(block, uid))
        tag = lokaler_tag(eintrag.started_at) if eintrag and eintrag.started_at else None
        heute = state.heute() if callable(getattr(state, "heute", None)) else None
        if tag is None:
            return "Dein Test."
        return "Dein Test von heute." if tag == heute else f"Dein Test vom {tag:%d.%m.}."

    def zur_uebung_knopf(block: Block, uid: str, getestet: bool) -> ft.Control | None:
        """„Zur Übung“ bzw. „Nochmal“ zu **dieser** Übung — ``None``, wo nur gelesen wird. Ein
        Test mit Vorgabe startet stattdessen seinen Lauf: „Test starten“ bzw. „Nochmal“, und
        „Zum Test“, solange er läuft oder auf sein Ergebnis wartet."""
        if uid not in katalog or not offen or (angelegt and not kursplan):
            return None
        if block.vorgabe is not None and test_starten is not None:
            laeuft = laufender_test == (block.id, uid)
            return ft.FilledTonalButton(
                "Zum Test" if laeuft else "Nochmal" if getestet else "Test starten",
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

    def test_inhalt(block: Block) -> list[ft.Control]:
        """Was in der Testkarte steht. Welche Übungen der Test misst und wo ihr Wert steht,
        sagen `gemessene_uebungen` und `wert_schluessel`: die feste — oder, mit ``aus``, die
        Gewählten einer Auswahl (Ben, 16.11.2026)."""
        gemessen = gemessene_uebungen(block, wirksam())
        teile: list[ft.Control] = [titel("Test")]
        #: mit Vorgabe ist der Test ein Lauf mit der Uhr — die Karte nennt Übung und Vorgabe
        mit_vorgabe = block.vorgabe is not None
        beschreibung: list[ft.Control] = (
            [anleitung(block, gemessen)]
            if mit_vorgabe
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
                    block.titel or (vorgabe_titel(block) if mit_vorgabe else OHNE_TITEL),
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
                    or (vorgabe_titel(block, uid) if mit_vorgabe else f"{name}: was schaffst du?"),
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
                daneben = neben(block, uid) if mit_vorgabe else ""
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
                # woher der Wert kommt: der Eintrag der Übung — mit Vorgabe „Dein Test von heute“
                woher = wann(block, uid) if mit_vorgabe else f"Dein Eintrag bei „{name}“."
                teile.append(
                    hinweis(
                        # im Kursplan-Kurs rechnet der Baustein (eigener Faktor, vielleicht
                        # eine andere Übung) — was daraus wird, sagt die Sammelkarte
                        f"{woher} Was daraus an deinem Plan wird, steht unten."
                        if kursplan
                        else f"{woher} Im Plan wird daraus das Ziel: "
                        f"{satzende(menge_text(feld, ziel_aus_test(block, wert)))}"
                    )
                )
            else:
                teile.append(
                    hinweis(
                        "Noch kein Test, seit du dieses Kapitel öffnest."
                        if mit_vorgabe
                        else f"Noch kein Eintrag bei „{name}“, seit du dieses Kapitel öffnest."
                    )
                )
            if (oeffnen := zur_uebung_knopf(block, uid, wert is not None)) is not None:
                teile.append(ft.Row(controls=[oeffnen]))
            return teile

        # mehrere Gewählte: je Übung eine Zeile — Name, ihr Wert, ihr Knopf
        teile.append(
            ft.Text(
                block.titel or (vorgabe_titel(block) if mit_vorgabe else OHNE_TITEL),
                weight=ft.FontWeight.W_600,
            )
        )
        teile.extend(beschreibung)
        for uid in gemessen:
            uebung = katalog.get(uid)
            feld = feld_von(uebung, block.feld)
            wert = werte.get(wert_schluessel(block, uid))
            oeffnen = zur_uebung_knopf(block, uid, wert is not None)
            # mit Vorgabe: hinter dem Wert, was der Lauf sonst gemessen hat
            daneben = neben(block, uid) if mit_vorgabe and wert is not None else ""
            # Kapitelplan: das Ziel in einer eigenen blassen Zeile — neben dem Knopf bräche
            # „30 Wdh. — im Plan das Ziel: 15 Wdh.“ mitten im Wert um (Web-Foto 16.11.2026)
            ziel_zeile: list[ft.Control] = (
                [
                    ft.Text(
                        f"im Plan das Ziel: {menge_text(feld, ziel_aus_test(block, wert))}",
                        size=12,
                        opacity=0.7,
                    )
                ]
                if wert is not None and not kursplan
                else []
            )
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
                                    if mit_vorgabe
                                    else "noch kein Eintrag",
                                    size=13,
                                    opacity=1.0 if wert is not None else 0.7,
                                    data=("testwert", block.id, uid),
                                ),
                                *ziel_zeile,
                            ],
                        ),
                        *([oeffnen] if oeffnen is not None else []),
                    ],
                )
            )
        was = "Deine Tests" if mit_vorgabe else "Deine Einträge"
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
        if not block.aus:
            return karte(*test_inhalt(block))
        # „die gewählte“: Die Karte folgt der Wahl — ihr Inhalt wird getauscht
        spalte = ft.Column(
            spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

        def zeichnen() -> None:
            spalte.controls = test_inhalt(block)
            with contextlib.suppress(Exception):
                spalte.update()

        spalte.controls = test_inhalt(block)
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
                else "Der Plan ist angelegt — ändern kannst du ihn in der Planverwaltung."
                if angelegt
                else "Mit zwei oder mehr stehen sie im Workout als Wege: Dort wählst du jedes "
                "Mal einen."
                if block.anzahl >= 2
                else "Die gewählte Übung kommt in den Plan."
            ),
        )

    for block in bloecke:
        if block.art == TEXT:
            if block.titel:
                ergebnis.controls.append(ft.Text(block.titel, size=18, weight=ft.FontWeight.W_600))
            if block.text:
                ergebnis.controls.append(
                    text_bauen(block.text) if text_bauen is not None else ft.Markdown(block.text)
                )
        elif block.art == MEDIUM and block.medium is not None:
            ergebnis.controls.append(medium_zeile(page, state, block.medium, browser=browser))
        elif block.art == FRAGE:
            ergebnis.controls.append(frage(block))
        elif block.art == TEST:
            ergebnis.controls.append(test(block))
        elif block.art == AUSWAHL:
            ergebnis.controls.append(auswahl(block))

    hat_eingabe = any(b.art in (TEST, AUSWAHL) for b in bloecke)
    # ohne ``anlegen`` kein Knopf: im Kursplan-Kurs übernimmt man in der Sammelkarte
    if anlegen is not None and hat_eingabe and offen and not angelegt:

        def druecken(_e: Any = None) -> Any:
            if fertig(bloecke, werte, wirksam()):
                return anlegen(wirksam())
            return None

        knopf.on_click = druecken
        stand_zeigen()
        ergebnis.anlegen = ft.Column(spacing=4, tight=True, controls=[ft.Row([knopf]), fehlt])
        ergebnis.controls.append(ergebnis.anlegen)
    return ergebnis


__all__ = ["KapitelBloecke", "feld_von", "kapitel_bloecke"]
