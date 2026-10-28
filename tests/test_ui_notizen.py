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
