"""Das Notizfeld der Messung (`ui/components/notizen.py`), ohne Fenster.

Ben, 20.10.2026: Eine bestehende Notiz öffnet sich unter ihrer Zeile, die Zeit lässt
sich als Dauer oder Uhrzeit eintippen, die Knöpfe stehen in zwei Zeilen.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

ft = pytest.importorskip("flet")

from hrv_core.ereignisse import Zeitbezug, anker_aus_wand, notiz  # noqa: E402
from hrv_core.recording import Beat  # noqa: E402

from trainingsapp.core.zeitangabe import DAUER, UHR, uhr_text  # noqa: E402
from trainingsapp.ui.components.notizen import ZEIT_UNLESBAR, Notizfeld  # noqa: E402

START = datetime(2026, 10, 20, 12, 0, 30, tzinfo=UTC)
BEATS = [Beat(float(i), 1000, 60, float(i)) for i in range(1, 121)]


class _Welt:
    """Speicher, Kurve und Fenster — was das Notizfeld von seiner Ansicht bekommt."""

    def __init__(self, *, live: bool, zeit_modus: str = DAUER) -> None:
        self.liste = [
            notiz(f"Notiz {t}", anker_aus_wand(BEATS, float(t)), START) for t in (10, 30, 50)
        ]
        self.gezeichnet = 0
        self.gezeigt: list[float] = []
        self.jetzt = 100.0
        zb = (
            Zeitbezug(lambda: BEATS, START, wand_versatz=5.0)
            if live
            else Zeitbezug(lambda: BEATS, START, achse=lambda: [b.t_s for b in BEATS])
        )
        self.zeilen = 0
        self.feld = Notizfeld(
            zeitbezug=lambda: zb,
            ereignisse=lambda: list(self.liste),
            speichern=self._speichern,
            neu_zeichnen=self._zeichnen,
            zeigen=self.gezeigt.append,
            mitte=lambda: 60.0,
            jetzt=(lambda: self.jetzt) if live else None,
            offen=True,
            zeit_modus=zeit_modus,
            zeilen=lambda: self.zeilen,
        )

    def _speichern(self, liste: list[dict]) -> None:
        self.liste = liste

    def _zeichnen(self) -> None:
        self.gezeichnet += 1


def _box_zeilen(feld: Notizfeld) -> list[ft.Row]:
    return [c for c in feld._eingabe_box.content.controls if isinstance(c, ft.Row)]


def _texte(row: ft.Row) -> list[str]:
    return [str(c.content) for c in row.controls if isinstance(c, ft.TextButton)]


def test_neue_notiz_oben_bestehende_unter_ihrer_zeile() -> None:
    """Die Eingabe steht fest zwischen den Zeilen davor und danach — sie wechselt nie den
    Elternteil (Ben, 27.10.2026: sonst verlor der Flet-Client das Textfeld und das
    Getippte kam nicht mehr an); nur die Zeilen wandern."""
    w = _Welt(live=False)
    f = w.feld
    assert f._liste.controls == [f._oben, f._eingabe_box, f._unten]
    f.neu()
    assert f._eingabe_box.visible and f._oben.controls == [] and len(f._unten.controls) == 3
    f.bearbeiten(1)
    assert f._liste.controls == [f._oben, f._eingabe_box, f._unten]  # nichts umgehängt
    assert len(f._oben.controls) == 2 and len(f._unten.controls) == 1  # unter der zweiten
    assert f._eingabe_box.margin is not None
    assert w.gezeigt[-1] == 30.0
    f.abbrechen()
    assert not f._eingabe_box.visible and len(f._unten.controls) == 3
    # Zugeklappt gibt es keine Zeilen — die Eingabe steht dann für sich, ohne Einzug
    f.offen = False
    f.bearbeiten(0)
    assert f._eingabe_box.visible and f._liste.visible
    assert not f._oben.visible and not f._unten.visible and f._eingabe_box.margin is None


def test_liste_rollt_ab_der_eingestellten_zeilenzahl() -> None:
    """Mehr Notizen als Zeilen (Ben, 27.10.2026): feste Höhe und Rollbalken, live ans Ende —
    nicht, solange eine Eingabe offen ist; 0 = alle, wie bisher."""
    from trainingsapp.ui.components.notizen import ZEILE_PX

    w = _Welt(live=True)
    f = w.feld
    assert f._liste.height is None and f._liste.scroll is None  # 0 = alle
    w.zeilen = 2
    f.auffrischen()
    assert f._liste.height == 2 * ZEILE_PX and f._liste.scroll == ft.ScrollMode.AUTO
    assert f._liste.auto_scroll is True
    f.bearbeiten(1)
    assert f._liste.auto_scroll is False  # die Eingabe bleibt in Sicht
    w.zeilen = 5
    f.abbrechen()
    assert f._liste.height is None and f._liste.auto_scroll is False
    w2 = _Welt(live=False)
    w2.zeilen = 2
    w2.feld.auffrischen()
    assert w2.feld._liste.scroll == ft.ScrollMode.AUTO and w2.feld._liste.auto_scroll is False


def test_knoepfe_in_zwei_zeilen() -> None:
    f = _Welt(live=True).feld
    f.neu()
    zeilen = _box_zeilen(f)
    assert zeilen[0].controls[1] is f._zeit_feld and zeilen[0].controls[2] is f._zeit_wechsel
    assert _texte(zeilen[1]) == ["Jetzt", "In Kurve", "Übungen"]
    assert _texte(zeilen[2]) == ["−5 s", "−1 s", "+1 s", "+5 s"]


def test_zeit_als_dauer_oder_uhrzeit_eintippen_nachtraeglich() -> None:
    w = _Welt(live=False)
    f = w.feld
    f.bearbeiten(1)
    assert f._zeit_feld.value == "0:30" and f._zeit_wechsel.content == uhr_text(START, 30)
    f._zeit_feld.value = "1:00"
    f.zeit_eingeben()
    assert f.x == 60.0 and w.gezeigt[-1] == 60.0 and f._zeit_feld.value == "1:00"
    # Umschalten: das Feld zeigt die Uhrzeit, der Knopf die Dauer
    f.zeit_modus_wechseln()
    assert f._zeit_feld.value == uhr_text(START, 60) and f._zeit_wechsel.content == "1:00"
    f._zeit_feld.value = uhr_text(START, 90)
    f.zeit_eingeben()
    assert f.x == 90.0 and f._zeit_feld.value == uhr_text(START, 90)
    # Unlesbares bleibt stehen, der Hinweis sagt es, die Zeit bleibt
    f._zeit_feld.value = "gleich"
    f.zeit_eingeben()
    assert f.x == 90.0 and f._zeit_feld.value == "gleich"
    assert f._zustand.value == ZEIT_UNLESBAR
    # Dieselbe Zeit noch einmal (Enter und dann Verlassen) rückt nicht erneut
    gezeigt = len(w.gezeigt)
    f._zeit_feld.value = uhr_text(START, 90)
    f.zeit_eingeben()
    f.zeit_eingeben()
    assert len(w.gezeigt) == gezeigt and f._zustand.value == ""
    f.uebernehmen()  # gespeichert und neu sortiert: die Notiz steht jetzt hinter „Notiz 50“
    assert [(e["text"], e["t_wall_s"]) for e in w.liste] == [
        ("Notiz 10", 10.0),
        ("Notiz 50", 50.0),
        ("Notiz 30", 90.0),
    ]


def test_zeit_live_zaehlt_ab_aufnahmestart_und_haelt_beim_tippen_an() -> None:
    w = _Welt(live=True, zeit_modus=UHR)
    f = w.feld
    f.neu()  # eingefroren bei jetzt = 100 auf der Live-Achse = 95 s Aufnahme
    assert f._zeit_feld.value == uhr_text(START, 95) and f._zeit_wechsel.content == "1:35"
    f.einfrieren_umschalten()  # läuft mit
    assert not f.eingefroren
    f._zeit_fokus()
    assert f.eingefroren and f.x == 100.0
    f.zeit_modus_wechseln()
    f._zeit_feld.value = "0:10"
    f.zeit_eingeben()
    assert f.x == 15.0  # 10 s Aufnahme + Versatz 5 s
    f.uebernehmen()
    assert w.liste[0]["t_wall_s"] == 10.0


def test_ohne_startzeit_nur_dauer() -> None:
    zb = Zeitbezug(lambda: BEATS, None, achse=lambda: [b.t_s for b in BEATS])
    liste = [notiz("x", anker_aus_wand(BEATS, 30.0), None)]
    f = Notizfeld(
        zeitbezug=lambda: zb,
        ereignisse=lambda: liste,
        speichern=lambda _l: None,
        neu_zeichnen=lambda: None,
        zeigen=lambda _x: None,
        mitte=lambda: 60.0,
        offen=True,
        zeit_modus=UHR,
    )
    f.bearbeiten(0)
    assert f._zeit_feld.value == "0:30" and not f._zeit_wechsel.visible


def test_notizliste_hoehe_mit_dem_griff_ziehen() -> None:
    """Ben, 10.11.2026 (A21): Die Notizliste ist „mal zu klein, mal zu groß“ — ein Griff unter
    der Liste zieht sie höher und niedriger, ein Doppeltipp stellt auf die Zeilenzahl zurück;
    ohne ``hoehe_merken`` (Vollbild) gibt es keinen Griff."""
    from types import SimpleNamespace

    from trainingsapp.core.hrv_einstellungen import NOTIZEN_HOEHE_MAX_PX, NOTIZEN_HOEHE_MIN_PX
    from trainingsapp.ui.components.notizen import ZEILE_PX

    def griffe(f: Notizfeld) -> list[ft.GestureDetector]:
        gefunden: list[ft.GestureDetector] = []

        def suchen(c: object) -> None:
            if isinstance(c, ft.GestureDetector):
                gefunden.append(c)
            for kind in getattr(c, "controls", None) or []:
                suchen(kind)
            if getattr(c, "content", None) is not None and not isinstance(c.content, str):
                suchen(c.content)

        suchen(f.control)
        return gefunden

    w = _Welt(live=False)
    assert not griffe(w.feld)  # Vollbild: kein Griff, keine senkrechte Geste

    gemerkt: list[int] = []
    stand = {"px": 0}

    def merken(px: int) -> None:
        stand["px"] = px
        gemerkt.append(px)

    zb = Zeitbezug(lambda: BEATS, START, achse=lambda: [b.t_s for b in BEATS])
    f = Notizfeld(
        zeitbezug=lambda: zb,
        ereignisse=lambda: list(w.liste),
        speichern=lambda _l: None,
        neu_zeichnen=lambda: None,
        zeigen=lambda _x: None,
        mitte=lambda: 60.0,
        offen=True,
        zeilen=lambda: 7,
        hoehe=lambda: stand["px"],
        hoehe_merken=merken,
    )
    (griff,) = griffe(f)
    assert griff.visible and f._liste.height is None  # drei Notizen, sieben Zeilen: alle
    griff.on_vertical_drag_start(None)
    griff.on_vertical_drag_update(SimpleNamespace(primary_delta=90.0))
    erwartet = max(3 * ZEILE_PX, NOTIZEN_HOEHE_MIN_PX) + 90
    assert f._liste.height == erwartet and f._liste.scroll == ft.ScrollMode.AUTO
    griff.on_vertical_drag_end(None)
    assert gemerkt == [erwartet] and f._liste.height == erwartet
    # Grenzen: nie kleiner als zwei Zeilen, nie höher als der Bildschirm
    griff.on_vertical_drag_start(None)
    griff.on_vertical_drag_update(SimpleNamespace(primary_delta=-5000.0))
    assert f._liste.height == NOTIZEN_HOEHE_MIN_PX
    griff.on_vertical_drag_update(SimpleNamespace(primary_delta=9000.0))
    assert f._liste.height == NOTIZEN_HOEHE_MAX_PX
    griff.on_vertical_drag_end(None)
    # Doppeltipp: wieder nach der Zeilenzahl
    griff.on_double_tap(None)
    assert gemerkt[-1] == 0 and f._liste.height is None


async def test_grenznotiz_loeschen_loescht_den_abschnitt() -> None:
    """H74 (Ben, 11.11.2026): Eine Grenz-Notiz löschen heißt den Abschnitt löschen — Start und
    Ende gehen zusammen, nach der Rückfrage „Abschnitt löschen?“; „Rückgängig“ holt beide."""
    from trainingsapp.core import abschnitte as eigene

    welt = _Welt(live=False)
    kennung = "seg-1a2b3c4d"
    start = notiz(
        "Block: Start",
        anker_aus_wand(BEATS, 20.0),
        START,
        marke=eigene.start_marke(kennung, "Block"),
    )
    ende = notiz(
        "Block: Ende", anker_aus_wand(BEATS, 40.0), START, marke=eigene.ende_marke(kennung, "Block")
    )
    welt.liste = [welt.liste[0], start, welt.liste[1], ende, welt.liste[2]]
    gezeigt: list = []
    welt.feld._dialog = gezeigt.append

    welt.feld.loeschen_fragen(3)  # die Ende-Notiz
    frage = gezeigt[-1]
    assert frage.title.value == "Abschnitt löschen?"
    assert len(welt.liste) == 5  # erst die Rückfrage
    ja = next(a for a in frage.actions if getattr(a, "content", None) == "Löschen")
    ja.on_click()
    await frage.on_dismiss(None)  # gelöscht wird, wenn der Dialog zu ist
    assert [e["text"] for e in welt.liste] == ["Notiz 10", "Notiz 30", "Notiz 50"]
    assert gezeigt[-1].action.label == "Rückgängig"

    gezeigt[-1].action.on_click()
    assert [e["text"] for e in welt.liste].count("Block: Start") == 1
    assert len(welt.liste) == 5

    # Ein Marker geht wie jede Notiz — er nimmt nur seine Trennung weg (Ben, 12.11.2026)
    marker = notiz("Block: Marker (halb)", anker_aus_wand(BEATS, 30.0), START)
    welt.liste = eigene.marken_aus_text([*welt.liste[:2], marker, *welt.liste[2:]])
    assert [e["marke"]["name"] for e in welt.liste if "marke" in e][:2] == [
        "Block (1)",
        "Block (halb)",
    ]
    welt.feld.loeschen_fragen(2)
    frage = gezeigt[-1]
    assert frage.title.value == "Notiz löschen?"
    next(a for a in frage.actions if getattr(a, "content", None) == "Löschen").on_click()
    await frage.on_dismiss(None)
    assert [e["text"] for e in welt.liste].count("Block: Start") == 1
    assert "Block: Marker (halb)" not in [e["text"] for e in welt.liste]


def test_verwaiste_grenze_steht_farbig() -> None:
    """Ben, 12.11.2026: Ein Ende ohne Start (oder umgekehrt) ergibt keinen Abschnitt — die
    Notiz steht farbig mit dem Grund in der Liste, damit keine Notizleiche bleibt."""
    from trainingsapp.ui.components.notizen import VERWAIST_HINWEIS

    welt = _Welt(live=False)
    welt.liste = [*welt.liste, notiz("Ruhe: Ende", anker_aus_wand(BEATS, 45.0), START)]
    welt.feld.auffrischen()

    def alle(c) -> list:
        kinder = [*(getattr(c, "controls", None) or []), getattr(c, "content", None)]
        return [c, *(x for k in kinder if isinstance(k, ft.Control) for x in alle(k))]

    texte = [
        c
        for c in alle(welt.feld.control)
        if isinstance(c, ft.Text) and c.value in ("Ruhe: Ende", VERWAIST_HINWEIS)
    ]
    assert len(texte) == 2 and all(t.color == ft.Colors.ERROR for t in texte)
