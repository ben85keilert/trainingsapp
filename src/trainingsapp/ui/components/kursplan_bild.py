"""Die Karte **„So wächst der Plan“** im Kurs-Editor (Ben, 16.11.2026: „die Karte aus dem Ablauf
beim Erstellen des Kurses mit einbauen … wo auch dargestellt wird, wieviel vom Plan freigegeben
ist. Beim neu erstellten Kursplan ließen sich dort die Beziehungen setzen“;
`docs/plan_kurs_ablauf.md` §14).

Der Zielplan des Kurses als **Ablaufbild** (`components/ablaufbild.py` — dasselbe wie im Reiter
„Ablauf“ eines Plans, hier nur gelesen): alle Übungen und Wege nach allen Kapiteln. Die Chips
darüber wählen ein Kapitel; was erst ein **späteres** bringt, steht blass, und die Zeile
darunter sagt, wie viel bis dahin freigegeben ist.

Im Formular eines Kapitels lassen sich hier die **Beziehungen setzen**: ein Tipp auf eine Übung
ruft ``weg_von`` (der Baustein „Weg“ beginnt bei ihr), ein Tipp auf den Griff eines Wegs
``weg_oeffnen`` (sein Baustein). Ohne die Rückrufe ist das Bild nur zum Ansehen.

Hier wird nur gezeichnet — was der Plan ist und welches Kapitel was bringt, rechnet
`core/kursbild.py`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core.ablauf import ENDE, Kante
from trainingsapp.core.kursbild import GRUNDLAGE_NR, Planbild, Weg
from trainingsapp.core.kurse import Kapitel
from trainingsapp.core.models import Exercise
from trainingsapp.ui.components import ablaufbild as abbild
from trainingsapp.ui.components.karte import hinweis, karte, titel

TITEL = "So wächst der Plan"
LEER = "Noch keine Übung im Plan — „Übung dazu“ unter „Am Plan“ bringt die erste."
LISTE = (
    "Der Plan ist eine Liste: Die Übungen stehen der Reihe nach. Der erste Weg macht ihn zum "
    "Workout."
)
BEISPIEL = (
    "Blass ist, was erst ein späteres Kapitel bringt. Bei einer Auswahl steht als Beispiel "
    "die erste Übung, die zur Wahl steht."
)
KEIN_BAUSTEIN = "Dieser Schritt ist die Reihenfolge der Liste — er gehört zu keinem Baustein."
START_FEST = "„Start“ ist kein Baustein — der Kursplan beginnt mit seiner ersten Übung."
OHNE_WEG = (
    "Ohne Weg im Ablauf — im Workout kommt sie nicht dran, in der Liste steht sie. Ein Weg zu "
    "ihr holt sie ins Bild:"
)
#: So hoch wird das Bild höchstens — darüber schiebt man es mit zwei Fingern
MAX_HOEHE = 900
#: Luft unter der letzten Übung
RAND_UNTEN = 16


def stand_text(bild: Planbild, kapitel: Sequence[Kapitel], bis: int) -> str:
    """„Bis Kapitel 2 „Erweiterung“: 2 von 3 Übungen im Plan.“"""
    da, alle = bild.stand(bis)
    if bis <= GRUNDLAGE_NR:
        wo = "Am Anfang"
    else:
        name = kapitel[bis - 1].titel if bis <= len(kapitel) else ""
        wo = f"Bis Kapitel {bis}" + (f" „{name}“" if name else "")
    if da == alle:
        return f"{wo}: alle {alle} Übungen im Plan." if alle != 1 else f"{wo}: die Übung im Plan."
    return f"{wo}: {da} von {alle} Übungen im Plan."


@dataclass(slots=True)
class KursplanBild:
    """Die Karte und ihre Handgriffe (für die Ansicht und die Tests)."""

    control: ft.Control
    #: ein Kapitel wählen (0 = der Anfang) — das Bild zieht nach
    waehlen: Callable[[int], None]
    #: Tipp auf eine Planübung
    knoten: Callable[[str], None]
    #: Tipp auf den Griff eines Wegs
    kante: Callable[[Kante], None]
    #: das gewählte Kapitel
    bis: Callable[[], int]
    #: eine Zeile unter dem Bild zeigen (leer: wieder weg) — für Meldungen des Aufrufers
    melden: Callable[[str], None]
    #: der gerechnete Plan (`core.kursbild.planbild`)
    bild: Planbild
    #: der Punkt einer Planübung wurde auf eine andere (oder das Ende) gezogen
    ziehen: Callable[[str, str], None] = lambda _von, _nach: None
    #: gedrückt halten auf einer Planübung — öffnet (oder schließt) ihr Menü
    lang: Callable[[str], None] = lambda _item: None
    #: das offene Menü an einer Übung — ``None``: keines
    menue: Callable[[], abbild.Menue | None] = lambda: None


def kursplan_bild_karte(
    page: Any,
    state: Any,
    bild: Planbild,
    katalog: Mapping[str, Exercise],
    kapitel: Sequence[Kapitel],
    *,
    bis: int | None = None,
    weg_von: Callable[[str], Any] | None = None,
    weg_oeffnen: Callable[[Weg], Any] | None = None,
    weg_ziehen: Callable[[str, str], Any] | None = None,
    einstellen: Callable[[str], Any] | None = None,
    hoehe: int | None = None,
) -> KursplanBild:
    """Die Karte zu ``bild``. ``kapitel``: die Kapitel des Kurses in ihrer Folge (für die Chips
    und den Namen); ``bis``: das zuerst gewählte Kapitel — ohne Angabe das letzte (alles da).
    ``weg_von(marke)``: Tipp auf eine Übung; ``weg_oeffnen(weg)``: Tipp auf einen Weg, der aus
    einem Baustein kommt. ``weg_ziehen(von, nach)``: der Punkt der Planübung ``von`` wurde auf
    ``nach`` gezogen (eine Planübung oder `core.ablauf.ENDE`) — dieselbe Geste wie im Reiter
    „Ablauf“ eines Plans, hier legt der Aufrufer daraus einen Baustein „Weg“ an (Ben,
    16.11.2026, P217). Mit ``weg_ziehen`` hat jede Übung ihren **Punkt zum Ziehen**, und
    **gedrückt halten** öffnet das Menü an der Übung: „Weg von hier …“ (``weg_von``), „Weg zum
    Ende“ und „Einstellen …“ (``einstellen(marke)`` — ein Baustein „Einstellen“ an ihr).
    ``hoehe``: ohne Angabe **so hoch wie die Zeichnung** (bis `MAX_HOEHE`) — das Formular
    rollt, das Bild muss man dafür nicht schieben (ein Finger auf dem Bild rollt die Seite;
    Web-Foto 16.11.2026: 340 px zeigten nur anderthalb Übungen)."""
    del page  # die Karte braucht die Seite nicht — der Platz bleibt für Blätter der Aufrufer
    gewaehlt = len(kapitel) if bis is None else max(GRUNDLAGE_NR, min(bis, len(kapitel)))
    items = bild.plan.items
    stand = ft.Text(stand_text(bild, kapitel, gewaehlt), size=13, data="kursbild_stand")
    meldung = ft.Text("", size=12, opacity=0.7, visible=False, data="kursbild_meldung")

    def melden(text: str) -> None:
        meldung.value, meldung.visible = text, bool(text)
        with contextlib.suppress(Exception):
            meldung.update()

    def knoten(item_id: str) -> None:
        melden("")
        marke = bild.marke(item_id)
        if weg_von is not None and marke:
            weg_von(marke)

    def kante(k: Kante) -> None:
        weg = bild.wege.get((k.von, k.nach))
        if weg is None:
            melden(KEIN_BAUSTEIN)
            return
        melden("")
        if weg_oeffnen is not None:
            weg_oeffnen(weg)

    def ziehen(von: str, nach: str) -> None:
        melden("")
        if von == abbild.START:
            # „Start“ ist kein Baustein — der Kursplan beginnt mit seiner ersten Übung
            melden(START_FEST)
            return
        if weg_ziehen is not None:
            weg_ziehen(von, nach)

    # -- Menü an der Übung (gedrückt halten) — nur, wo sich im Bild etwas setzen lässt ------
    offen: dict[str, Any] = {"menue": None, "oben": False}

    def neu_malen() -> None:
        abbild.aktualisieren(flaeche_bild, zeichnung())
        with contextlib.suppress(Exception):
            flaeche_bild.control.update()

    def menue_zu() -> None:
        if offen["menue"] is not None:
            offen["menue"] = None
            neu_malen()

    def lang(item_id: str) -> None:
        offen["menue"] = None if offen["menue"] == item_id else item_id
        neu_malen()

    def menue_jetzt() -> abbild.Menue | None:
        item_id = offen["menue"]
        if item_id is None:
            return None
        marke = bild.marke(item_id)

        def tun(aktion: Callable[[], Any]) -> Callable[[], Any]:
            def handler() -> Any:
                menue_zu()
                return aktion()

            return handler

        eintraege = [
            abbild.Eintrag("Weg von hier …", tun(lambda: knoten(item_id)), ft.Icons.ALT_ROUTE),
            # „Ende“ als Ziel am Bildrand (wie im Plan) läge hier oft unter dem Bildschirmrand:
            # Das Bild ist so hoch wie die Zeichnung, das Formular rollt (Web-Foto 16.11.2026)
            abbild.Eintrag("Weg zum Ende", tun(lambda: ziehen(item_id, ENDE)), ft.Icons.STOP),
        ]
        if einstellen is not None and marke:
            eintraege.append(
                abbild.Eintrag("Einstellen …", tun(lambda: einstellen(marke)), ft.Icons.TUNE)
            )
        return abbild.Menue(item_id, eintraege, menue_zu, offen["oben"])

    def zeichnung() -> abbild.Zeichnung:
        setzbar = weg_ziehen is not None
        return abbild.zeichnung(
            state,
            bild.ablauf,
            items,
            katalog,
            vernebelt=bild.spaeter(gewaehlt),
            on_knoten=knoten if weg_von is not None else None,
            on_kante=kante,
            # dieselben Gesten wie im Reiter „Ablauf“ (P217): Punkt ziehen, gedrückt halten
            on_verbinden=ziehen if setzbar else None,
            on_knoten_lang=lang if setzbar and weg_von is not None else None,
            on_lang_ort=(lambda anteil: offen.__setitem__("oben", anteil > 0.56))
            if setzbar
            else None,
            menue=menue_jetzt() if setzbar else None,
        )

    if not items:
        return KursplanBild(
            karte(titel(TITEL), hinweis(LEER), meldung),
            lambda _nr: None,
            knoten,
            kante,
            lambda: gewaehlt,
            melden,
            bild,
            ziehen,
            lang,
            menue_jetzt,
        )

    erste = zeichnung()
    flaeche = abbild.flaeche_neu(erste)
    hoch = hoehe if hoehe is not None else int(min(erste.hoehe + RAND_UNTEN, MAX_HOEHE))
    ansicht = abbild.ansicht(flaeche, hoch)
    # Das Formular rollt: Mausrad und zwei Finger sollen die Seite bewegen, nicht das Bild
    # vergrößern (Web-Foto 16.11.2026: das Rad über dem Bild zoomte) — schieben geht weiter,
    # für Zeichnungen, die breiter sind als die Karte
    ansicht.scale_enabled = False
    flaeche_bild = abbild.Bild(ansicht, flaeche, erste.mitten, erste.knoten)

    # Planübungen ohne Weg zeichnet das Ablaufbild nicht — sie stehen darunter, zum Antippen
    namen = {i.id: katalog[i.exercise_id].name for i in items if i.exercise_id in katalog}
    lose_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6, data="kursbild_lose")

    def lose_fuellen() -> None:
        blass = set(bild.spaeter(gewaehlt))
        lose_reihe.controls = [
            ft.OutlinedButton(
                f"{namen.get(i, 'Übung')} · Kapitel {bild.kapitel.get(i, GRUNDLAGE_NR)}",
                on_click=(lambda _e, i=i: knoten(i)) if weg_von is not None else None,
                opacity=abbild.NEBEL if i in blass else 1.0,
                data=("kursbild_lose", i),
            )
            for i in bild.lose()
        ]

    lose_fuellen()

    # Der Anfang nur, wenn die Grundlage Übungen mitbringt — sonst beginnt der Plan leer
    nummern = [*([GRUNDLAGE_NR] if bild.bringt(GRUNDLAGE_NR) else []), *range(1, len(kapitel) + 1)]
    chips: dict[int, ft.Chip] = {}

    def waehlen(nr: int) -> None:
        nonlocal gewaehlt
        gewaehlt = max(GRUNDLAGE_NR, min(nr, len(kapitel)))
        for n, chip in chips.items():
            chip.selected = n == gewaehlt
        stand.value = stand_text(bild, kapitel, gewaehlt)
        melden("")
        offen["menue"] = None
        abbild.aktualisieren(flaeche_bild, zeichnung())
        lose_fuellen()
        for control in (reihe, stand, lose_reihe):
            with contextlib.suppress(Exception):
                control.update()

    for nr in nummern:
        name = kapitel[nr - 1].titel if nr > GRUNDLAGE_NR else "die Grundlage"
        chips[nr] = ft.Chip(
            label=ft.Text("Anfang" if nr == GRUNDLAGE_NR else f"Kapitel {nr}", size=12),
            selected=nr == gewaehlt,
            show_checkmark=False,
            tooltip=f"Der Plan bis hierher — {name}",
            on_select=lambda _e, n=nr: waehlen(n),
            data=("kursbild_bis", nr),
        )
    reihe = ft.Row(wrap=True, spacing=6, run_spacing=6, controls=list(chips.values()))
    if weg_ziehen is not None:
        tipp = (
            "Zieh den Punkt unter einer Übung auf eine andere: Das legt einen Weg in diesem "
            "Kapitel an. Tippen auf eine Übung oder gedrückt halten öffnet, was sich an ihr "
            "setzen lässt; der Punkt eines Wegs öffnet seinen Baustein."
        )
    elif weg_von is not None:
        tipp = (
            "Tippe eine Übung an, um von ihr einen Weg zu setzen — oder den Punkt eines Wegs, "
            "um ihn zu ändern."
        )
    else:
        tipp = ""
    inhalt: list[ft.Control] = [titel(TITEL), reihe, stand, flaeche_bild.control]
    if lose_reihe.controls:
        inhalt += [hinweis(OHNE_WEG), lose_reihe]
    inhalt.append(meldung)
    if not bild.workout:
        inhalt.append(hinweis(LISTE))
    inhalt.append(hinweis(f"{tipp} {BEISPIEL}".strip()))
    return KursplanBild(
        karte(*inhalt, abstand=8),
        waehlen,
        knoten,
        kante,
        lambda: gewaehlt,
        melden,
        bild,
        ziehen,
        lang,
        menue_jetzt,
    )


__all__ = [
    "BEISPIEL",
    "KEIN_BAUSTEIN",
    "LEER",
    "LISTE",
    "MAX_HOEHE",
    "OHNE_WEG",
    "START_FEST",
    "TITEL",
    "KursplanBild",
    "kursplan_bild_karte",
]
