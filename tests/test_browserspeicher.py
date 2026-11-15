"""Speichern im Browser (`ui/browserspeicher.py`, Ben, 15.11.2026; `docs/plan_web.md` §5).

Der echte Zugang (IDBFS, IndexedDB, Web Locks) läuft nur in Pyodide und ist im Browser
gemessen; hier steht ein nachgebauter, der dasselbe mit einem zweiten Ordner tut. Geprüft
wird das, was die App selbst entscheidet: wann sie schreibt, wann nicht, und was sie zeigt.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from trainingsapp.ui.browserspeicher import (
    AN,
    ANDERER_TAB,
    FEHLER,
    GELOESCHT,
    SPERRE,
    TEXTE,
    Browserspeicher,
)


class Zugang:
    """Der Browser als Ordner: ``lager`` ist die IndexedDB, ``frei`` die Sperre."""

    def __init__(self, lager: Path, *, frei: bool = True) -> None:
        self.lager, self.frei = lager, frei
        self.pfad: Path | None = None
        self.geschrieben = 0
        self.kaputt: str | None = None
        self.sperren: list[str] = []

    def einhaengen(self, pfad: str) -> None:
        self.pfad = Path(pfad)
        self.pfad.mkdir(parents=True, exist_ok=True)

    async def abgleichen(self, holen: bool) -> None:
        if self.kaputt:
            raise OSError(self.kaputt)
        assert self.pfad is not None
        quelle, ziel = (self.lager, self.pfad) if holen else (self.pfad, self.lager)
        if not holen:
            self.geschrieben += 1
            shutil.rmtree(ziel, ignore_errors=True)
        if quelle.is_dir():
            shutil.copytree(quelle, ziel, dirs_exist_ok=True)

    async def sperre(self, name: str) -> bool:
        self.sperren.append(name)
        return self.frei

    async def entfernen(self, pfad: str) -> None:
        if self.kaputt:
            raise OSError(self.kaputt)
        shutil.rmtree(self.lager, ignore_errors=True)


def _speicher(tmp_path: Path, **zugang) -> tuple[Browserspeicher, Zugang]:
    z = Zugang(tmp_path / "indexeddb", **zugang)
    return Browserspeicher(tmp_path / "daten", z), z


def _schreiben(datei: Path, text: str) -> None:
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding="utf-8")


def test_erster_besuch_speichert_und_der_zweite_findet_es(tmp_path: Path) -> None:
    s, z = _speicher(tmp_path)
    asyncio.run(s.starten())
    assert (s.zustand, s.vorhanden, z.sperren) == (AN, False, [SPERRE])
    assert not s.geaendert()  # ein leeres Verzeichnis ist kein Grund zu schreiben

    _schreiben(s.ordner / "trainingsapp.db", "erster Eintrag")
    _schreiben(s.ordner / "Messungen" / "a.csv", "800\n810\n")
    assert s.geaendert()
    assert asyncio.run(s.sichern()) and not s.geaendert()
    assert z.geschrieben == 1

    # neuer Besuch: neues Python, leerer Arbeitsspeicher, derselbe Browser
    shutil.rmtree(s.ordner)
    zweiter = Browserspeicher(s.ordner, Zugang(z.lager))
    asyncio.run(zweiter.starten())
    assert (zweiter.zustand, zweiter.vorhanden) == (AN, True)
    assert (zweiter.ordner / "trainingsapp.db").read_text(encoding="utf-8") == "erster Eintrag"
    assert (zweiter.ordner / "Messungen" / "a.csv").is_file()
    assert not zweiter.geaendert()  # was geholt wurde, gilt als gespeichert


def test_signatur_merkt_aendern_anlegen_und_loeschen(tmp_path: Path) -> None:
    s, _ = _speicher(tmp_path)
    asyncio.run(s.starten())
    _schreiben(s.ordner / "a", "1")
    asyncio.run(s.sichern())
    _schreiben(s.ordner / "a", "12")  # gewachsen
    assert s.geaendert()
    asyncio.run(s.sichern())
    _schreiben(s.ordner / "tief" / "unten" / "b", "")  # leere Datei in neuem Ordner
    assert s.geaendert()
    asyncio.run(s.sichern())
    (s.ordner / "tief" / "unten" / "b").unlink()
    assert s.geaendert()


def test_takt_schreibt_nur_bei_aenderung_und_nie_in_einer_transaktion(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("trainingsapp.ui.browserspeicher.TAKT_S", 0.01)
    s, z = _speicher(tmp_path)
    ruhig = True

    async def lauf() -> None:
        nonlocal ruhig
        await s.starten()
        aufgabe = asyncio.create_task(s.takt(lambda: ruhig))
        await asyncio.sleep(0.05)
        assert z.geschrieben == 0  # nichts geändert: nichts geschrieben

        ruhig = False  # Transaktion offen
        _schreiben(s.ordner / "trainingsapp.db", "halb")
        await asyncio.sleep(0.05)
        assert z.geschrieben == 0

        ruhig = True
        await asyncio.sleep(0.05)
        assert z.geschrieben == 1  # einmal, nicht bei jedem Schlag
        aufgabe.cancel()

    asyncio.run(lauf())
    assert (z.lager / "trainingsapp.db").read_text(encoding="utf-8") == "halb"


def test_zweiter_tab_zeigt_den_stand_und_schreibt_nicht(tmp_path: Path) -> None:
    erster, z = _speicher(tmp_path)
    asyncio.run(erster.starten())
    _schreiben(erster.ordner / "trainingsapp.db", "vom ersten Tab")
    asyncio.run(erster.sichern())

    zweiter = Browserspeicher(tmp_path / "daten2", Zugang(z.lager, frei=False))
    asyncio.run(zweiter.starten())
    assert (zweiter.zustand, zweiter.aktiv, zweiter.vorhanden) == (ANDERER_TAB, False, True)
    assert (zweiter.ordner / "trainingsapp.db").read_text(encoding="utf-8") == "vom ersten Tab"
    _schreiben(zweiter.ordner / "trainingsapp.db", "vom zweiten Tab")
    assert asyncio.run(zweiter.sichern()) is False
    assert (z.lager / "trainingsapp.db").read_text(encoding="utf-8") == "vom ersten Tab"


def test_browser_laesst_es_nicht_zu(tmp_path: Path) -> None:
    # schon beim Start: Die App läuft ohne Speicher weiter
    s, z = _speicher(tmp_path)
    z.kaputt = "QuotaExceededError"
    asyncio.run(s.starten())
    assert (s.zustand, s.aktiv, s.fehler) == (FEHLER, False, "QuotaExceededError")

    # erst beim Schreiben: einmal versucht, dann aus — nicht alle zwei Sekunden wieder
    s, z = _speicher(tmp_path)
    asyncio.run(s.starten())
    _schreiben(s.ordner / "a", "1")
    z.kaputt = "voll"
    assert asyncio.run(s.sichern()) is False
    assert s.zustand == FEHLER and asyncio.run(s.sichern()) is False


def test_alles_loeschen_entfernt_und_schreibt_danach_nicht_mehr(tmp_path: Path) -> None:
    s, z = _speicher(tmp_path)
    asyncio.run(s.starten())
    _schreiben(s.ordner / "trainingsapp.db", "Puls 61")
    asyncio.run(s.sichern())
    assert z.lager.is_dir()

    asyncio.run(s.loeschen())
    assert s.zustand == GELOESCHT and not z.lager.exists()
    _schreiben(s.ordner / "trainingsapp.db", "Puls 62")  # die App läuft im Tab weiter
    assert asyncio.run(s.sichern()) is False and not z.lager.exists()

    # scheitert das Löschen, bleibt der Zustand, und die Person erfährt es
    s, z = _speicher(tmp_path)
    asyncio.run(s.starten())
    z.kaputt = "Ein anderer Tab hält den Speicher offen."
    with pytest.raises(OSError, match="anderer Tab"):
        asyncio.run(s.loeschen())
    assert s.zustand == AN


def test_texte_fuer_jeden_zustand_ohne_gedankenstrich() -> None:
    assert set(TEXTE) >= {AN, ANDERER_TAB, GELOESCHT, FEHLER}
    for text in TEXTE.values():
        assert text.endswith(".") and "—" not in text and "–" not in text


# -- Oberfläche --------------------------------------------------------------------------------


def _alle(wurzel, ft):
    yield wurzel
    for name in ("content", "controls", "actions", "title"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k, ft)


def _seite(tmp_path: Path):
    from trainingsapp.ui.state import AppState

    page = SimpleNamespace(route="/einstellungen/daten", views=[], platform=None, dialoge=[])
    page.update = lambda: None
    page.show_dialog = page.dialoge.append
    page.aufgaben = []
    page.run_task = lambda f, *a: page.aufgaben.append((f, a))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    return page, state


def test_karte_nur_mit_speicher_und_loeschen_fragt_erst(tmp_path: Path) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.views.einstellungen_seiten import browser_karte, einstellungen_daten

    page, state = _seite(tmp_path)
    try:
        assert state.browserspeicher is None and browser_karte(page, state) == []  # die App
        texte = [c.value for v in einstellungen_daten(page, state).controls for c in _alle(v, ft)
                 if isinstance(c, ft.Text)]  # fmt: skip
        assert "Speicher im Browser" not in " ".join(str(t) for t in texte)

        s, z = _speicher(tmp_path)
        asyncio.run(s.starten())
        _schreiben(s.ordner / "trainingsapp.db", "x")
        asyncio.run(s.sichern())
        state.browserspeicher = s
        teile = [c for k in browser_karte(page, state) for c in _alle(k, ft)]
        assert TEXTE[AN] in [c.value for c in teile if isinstance(c, ft.Text)]
        (knopf,) = [c for c in teile if getattr(c, "data", None) == "browserspeicher-loeschen"]

        knopf.on_click()
        (dialog,) = page.dialoge
        assert z.lager.is_dir()  # die Rückfrage allein löscht nichts
        assert isinstance(dialog, ft.AlertDialog) and "löschen?" in dialog.title.value

        # nach dem Löschen: der Text sagt es, der Knopf ist weg
        asyncio.run(s.loeschen())
        teile = [c for k in browser_karte(page, state) for c in _alle(k, ft)]
        assert TEXTE[GELOESCHT] in [c.value for c in teile if isinstance(c, ft.Text)]
        assert not [c for c in teile if getattr(c, "data", None) == "browserspeicher-loeschen"]

        # zweiter Tab: kein Löschknopf (der andere Tab hält den Speicher offen)
        state.browserspeicher = Browserspeicher(tmp_path / "d3", Zugang(z.lager, frei=False))
        asyncio.run(state.browserspeicher.starten())
        teile = [c for k in browser_karte(page, state) for c in _alle(k, ft)]
        assert TEXTE[ANDERER_TAB] in [c.value for c in teile if isinstance(c, ft.Text)]
        assert not [c for c in teile if getattr(c, "data", None) == "browserspeicher-loeschen"]
    finally:
        state.schliessen()


def test_einstieg_in_der_app_ist_main_im_browser_die_huelle(monkeypatch) -> None:
    pytest.importorskip("flet")
    import inspect

    from trainingsapp.ui import app

    assert app.einstieg() is app.main  # App und Vorschau am Rechner: unverändert
    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    assert app.einstieg() is app.main  # der Flet-Web-Server hat einen echten Ordner

    monkeypatch.setattr(sys, "platform", "emscripten")
    huelle = app.einstieg()
    assert huelle is not app.main and inspect.iscoroutinefunction(huelle)


def test_huelle_holt_erst_und_bietet_bei_kaputtem_stand_das_loeschen_an(
    tmp_path: Path, monkeypatch
) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui import app

    z = Zugang(tmp_path / "indexeddb")
    _schreiben(z.lager / "trainingsapp.db", "von früher")
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setattr(app, "PyodideZugang", lambda: z)
    monkeypatch.setattr(app, "datenverzeichnis", lambda: tmp_path / "daten")
    gesehen: list[tuple[str, str]] = []

    def main(page, speicher):
        # beim Öffnen der Datenbank liegt das Gespeicherte schon da
        gesehen.append((speicher.zustand, (speicher.ordner / "trainingsapp.db").read_text()))

    monkeypatch.setattr(app, "main", main)
    page = SimpleNamespace(views=[], update=lambda: None)
    asyncio.run(app.einstieg()(page))
    assert gesehen == [(AN, "von früher")] and page.views == []

    def kaputt(page, speicher):
        raise RuntimeError("Migration 061 fehlgeschlagen")

    monkeypatch.setattr(app, "main", kaputt)
    asyncio.run(app.einstieg()(page))
    (ansicht,) = page.views
    texte = " ".join(str(c.value) for c in _alle(ansicht, ft) if isinstance(c, ft.Text))
    assert "lassen sich nicht öffnen" in texte and "Migration 061" in texte
    (knopf,) = [c for c in _alle(ansicht, ft) if isinstance(c, ft.FilledButton)]
    asyncio.run(knopf.on_click())
    assert not z.lager.exists() and knopf.disabled

    # ohne Gespeichertes ist es ein gewöhnlicher Fehler der App — kein Löschangebot
    page.views.clear()
    shutil.rmtree(tmp_path / "daten")  # neuer Besuch: leerer Arbeitsspeicher, leerer Browser
    with pytest.raises(RuntimeError):
        asyncio.run(app.einstieg()(page))
    assert page.views == []


def test_hinweis_beim_start_wenn_nicht_gespeichert_wird(tmp_path: Path) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.app import nicht_gespeichert_dialog

    s = Browserspeicher(tmp_path / "daten", Zugang(tmp_path / "indexeddb", frei=False))
    asyncio.run(s.starten())
    dialog = nicht_gespeichert_dialog(s)
    assert isinstance(dialog, ft.AlertDialog) and dialog.content.value == TEXTE[ANDERER_TAB]
