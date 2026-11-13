"""Dokumente als Anhang (Ben, 13.11.2026; `docs/plan_anhaenge.md`, Teil I): Seite für Seite
aus der Kamera wird ein PDF, eine PDF-Datei lässt sich wählen; Kachel, Ansicht, Knöpfe."""

from __future__ import annotations

import shutil
import sqlite3
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from test_ui_anhaenge import (  # noqa: E402, F401
    _alle,
    _knoepfe,
    _mit_kamera,
    _texte,
    _ziel,
    page,
    welt,
)
from trainingsapp.core.anhaenge import BILD, DOKUMENT, Qualitaet, Ziel, neuer_anhang  # noqa: E402
from trainingsapp.core.dokument import (  # noqa: E402
    MAX_SEITEN,
    beispielseite,
    gezeigte_masse,
    pdf_aus_jpegs,
)
from trainingsapp.data.db import MIGRATIONS_DIR, migrieren  # noqa: E402
from trainingsapp.ui.components.anhang_reihe import kachel  # noqa: E402
from trainingsapp.ui.views.anhang import anhang_view  # noqa: E402
from trainingsapp.ui.views.anhang_aufnahme import (  # noqa: E402
    ARTEN,
    _Aufnahme,
    anhang_aufnahme_view,
    aufnahme_route,
)
from trainingsapp.ui.views.leistungen import leistungen_view  # noqa: E402

SEITE = beispielseite(1080, 1920)


def _scanner(page, welt) -> _Aufnahme:  # noqa: F811
    a = _mit_kamera(page, welt, DOKUMENT)

    async def foto() -> bytes:
        return SEITE

    a.kamera.take_picture = foto
    return a


async def test_seiten_aufnehmen_wird_ein_pdf_mit_frontbild(welt, page) -> None:  # noqa: F811
    a = _scanner(page, welt)
    assert a.qualitaet is Qualitaet.GROSS  # Vorgabe fürs Dokument: Text bleibt lesbar
    assert not any("Fertig" in k for k in _knoepfe(a.knoepfe))  # noch keine Seite
    await a.ausloesen()
    assert a.offen == 0 and len(a.seiten) == 1 and a.frisch
    assert _knoepfe(a.knoepfe) == ["Nächste Seite", "Fertig · 1 Seite"]
    assert a.leiste.controls == []  # über der Seite keine Kamera-Leiste
    assert a.werkzeuge.visible and "Neu aufnehmen" in _tooltips(a.werkzeuge)
    await a.ausloesen()  # solange eine Seite gezeigt wird, löst nichts aus
    assert len(a.seiten) == 1
    a.seite_loeschen()  # „Neu aufnehmen“
    assert a.offen is None and a.seiten == [] and a.kamera.content is None
    await a.ausloesen()
    a.zur_kamera()  # „Nächste Seite“
    assert len(a.seiten) == 1 and a.status.value.startswith("1 Seite · ")
    assert a.streifen.visible and len(a.streifen.controls) == 1
    await a.ausloesen()
    await a.dokument_fertig()
    assert a.daten is not None and a.daten.startswith(b"%PDF-1.4")
    assert a.daten.count(b"/Type /Page\n") == 2 and a.frontbild == a.seiten[0]
    assert a.status.value.startswith("2 Seiten · ")
    assert _knoepfe(a.knoepfe) == ["Weitere Seite", "Behalten"] and not a.streifen.visible
    a.dokument_weiter()  # die Seiten bleiben, eine dritte geht
    assert a.daten is None and len(a.seiten) == 2
    await a.dokument_fertig()
    a.notiz.value = "Befund"
    await a.behalten()
    neu = [x for x in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if x.note == "Befund"]
    assert len(neu) == 1 and neu[0].ist_dokument and neu[0].pfad.endswith(".pdf")
    assert neu[0].seiten == 2  # Migration 061: steht an der Kachel
    repo = welt.state.anhaenge
    assert repo.datei(neu[0]).read_bytes().startswith(b"%PDF-")
    assert neu[0].vorschau and repo.bild(neu[0]).read_bytes()[:2] == b"\xff\xd8"
    assert page.dialoge[-1].content.value == "Dokument gespeichert"
    assert repo.gesamt(welt.state.profil.id).dokumente == 1
    assert "PDF · 2" in _texte(kachel(neu[0], repo.bild(neu[0]), None))
    assert any("2 Seiten" in t for t in _texte(anhang_view(page, welt.state, "/", neu[0])))
    assert a.seiten == []  # behalten: Zurück fragt nicht mehr


def _tooltips(wurzel) -> list[str]:
    return [str(c.tooltip) for c in _alle(wurzel) if getattr(c, "tooltip", None)]


async def test_seiten_umordnen_loeschen_und_zuschneiden(welt, page) -> None:  # noqa: F811
    """P206: eine Seite aus dem Streifen öffnen, verschieben, löschen; der Zuschnitt ist ein
    Ausschnitt im PDF (das Bild bleibt ganz), „Ganze Seite“ nimmt ihn zurück."""
    a = _scanner(page, welt)
    seiten = [beispielseite(1080, 1920), beispielseite(1000, 1500), beispielseite(900, 1200)]
    for seite in seiten:
        a.seite_zeigen(seite)
        a.zur_kamera()
    a.streifen.controls[2].on_click()  # Seite 3 öffnen
    assert a.offen == 2 and not a.frisch and a.status.value.startswith("Seite 3 von 3")
    assert "Seite löschen" in _tooltips(a.werkzeuge)
    a.seite_schieben(-1)
    a.seite_schieben(-1)
    a.seite_schieben(-1)  # vorn ist Schluss
    assert a.offen == 0
    assert [gezeigte_masse(s)[0] for s in a.seiten] == [900, 1080, 1000]
    a.seite_oeffnen(1)
    a.seite_loeschen()
    assert [gezeigte_masse(s)[0] for s in a.seiten] == [900, 1000]
    assert len(a.schnitte) == 2 and a.offen is None
    # Zuschneiden: Regler statt Knöpfe, der Rand liegt dunkel über der Seite
    a.seite_oeffnen(0)
    a.schneiden()
    assert a.regler.visible and not a.werkzeuge.visible and not a.streifen.visible
    assert _knoepfe(a.knoepfe) == ["Ganze Seite", "Übernehmen"]
    a.regler_breite.start_value, a.regler_breite.end_value = 25, 100
    a.regler_hoehe.start_value, a.regler_hoehe.end_value = 0, 99
    a._schnitt_geaendert()
    assert a.schnitte[0] == (0.25, 0.0, 0.0, 0.01)
    assert a.blende_teile[0].visible and a.blende_teile[0].expand == 250
    assert not a.blende_teile[2].visible and a.blende_frei.expand == 750
    a.schnitt_fertig()
    assert a.status.value.endswith("zugeschnitten") and a.werkzeuge.visible
    await a.dokument_fertig()
    assert a.daten.count(b"/CropBox") == 1 and a.daten.count(b"/Type /Page\n") == 2
    a.dokument_weiter()
    a.seite_oeffnen(0)
    a.schneiden()
    a.schnitt_weg()
    await a.dokument_fertig()
    assert b"/CropBox" not in a.daten


async def test_zurueck_fragt_solange_seiten_da_sind(welt, page) -> None:  # noqa: F811
    """P206: Pfeil und Systemtaste verwerfen aufgenommene Seiten nicht still."""
    route = aufnahme_route("/", welt.eintrag.id, DOKUMENT)
    ansicht = anhang_aufnahme_view(page, welt.state, route, _ziel(welt), DOKUMENT)
    assert ansicht.can_pop is False and ansicht.on_confirm_pop is not None  # Systemtaste
    await ansicht.appbar.leading.on_click()  # ohne Seiten: gleich zurück
    assert page.routen == ["/"] and page.dialoge == []
    foto = anhang_aufnahme_view(
        page, welt.state, route.replace("dokument", "foto"), _ziel(welt), BILD
    )
    assert foto.on_confirm_pop is None  # Foto und Video wie bisher
    a = _scanner(page, welt)
    a.seite_zeigen(SEITE)
    assert a.seiten_fragen() == ""  # „selbst gefragt“: man bleibt
    dialog = page.dialoge[-1]
    assert dialog.title.value == "Seiten verwerfen?" and "1 Seite" in dialog.content.value


async def test_hoechstens_so_viele_seiten(welt, page) -> None:  # noqa: F811
    a = _scanner(page, welt)
    a.seiten = [SEITE] * MAX_SEITEN
    a.schnitte = [(0.0, 0.0, 0.0, 0.0)] * MAX_SEITEN
    await a.ausloesen()
    assert a.offen is None and len(a.seiten) == MAX_SEITEN  # voll: der Auslöser tut nichts


async def test_pdf_datei_waehlen_bereinigt_und_ohne_frontbild(
    welt,  # noqa: F811
    page,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    from trainingsapp.ui import systemdialog

    pdf = tmp_path / "befund.pdf"
    pdf.write_bytes(pdf_aus_jpegs([SEITE]))
    kein_pdf = tmp_path / "falsch.pdf"
    kein_pdf.write_bytes(b"GIF89a")
    wahl = {"pfad": kein_pdf}

    async def mit(aufruf):
        aufruf.close()
        return [SimpleNamespace(path=str(wahl["pfad"]))]

    monkeypatch.setattr(systemdialog, "mit", mit)
    a = _Aufnahme(page, welt.state, _ziel(welt), DOKUMENT)
    await a.datei_waehlen()
    assert a.daten is None and "kein PDF" in a.status.value
    wahl["pfad"] = pdf
    await a.datei_waehlen()
    assert a.daten is not None and a.frontbild is None and a.status.value.startswith("PDF-Datei")
    await a.behalten()
    neu = [x for x in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if x.ist_dokument]
    assert len(neu) == 1 and neu[0].vorschau is None
    # Kachel: nur das Symbol; Ansicht: „Öffnen mit …“, kein Bild
    k = kachel(neu[0], welt.state.anhaenge.bild(neu[0]), None)
    assert not any(isinstance(c, ft.Image) for c in _alle(k))
    assert any(
        isinstance(c, ft.Icon) and c.icon == ft.Icons.PICTURE_AS_PDF_OUTLINED for c in _alle(k)
    )
    ansicht = anhang_view(page, welt.state, "/", neu[0])
    assert "Öffnen mit …" in _knoepfe(ansicht)
    assert not any(isinstance(c, ft.Image) for c in _alle(ansicht))


def test_kachel_und_ansicht_des_gescannten_dokuments(welt, page) -> None:  # noqa: F811
    d = neuer_anhang(welt.eintrag.id, DOKUMENT, Qualitaet.GROSS, frontbild=True)
    welt.state.anhaenge.anlegen(d, pdf_aus_jpegs([SEITE]), SEITE)
    k = kachel(d, welt.state.anhaenge.bild(d), None)
    assert any(isinstance(c, ft.Image) for c in _alle(k)) and "PDF" in _texte(k)
    ansicht = anhang_view(page, welt.state, "/", d)
    assert "Öffnen mit …" in _knoepfe(ansicht)
    assert any(isinstance(c, ft.Image) for c in _alle(ansicht))  # die erste Seite


def test_knoepfe_und_seite_am_rechner(welt, page) -> None:  # noqa: F811
    ansicht = leistungen_view(
        page, welt.state, f"/tag/{welt.state.heute()}/leistungen/{welt.uebung.id}", welt.uebung
    )
    assert "Dokument" in _knoepfe(ansicht)
    route = aufnahme_route("/", welt.eintrag.id, DOKUMENT)
    assert route.endswith("/dokument") and ARTEN["dokument"] == DOKUMENT
    seite = anhang_aufnahme_view(page, welt.state, route, _ziel(welt), DOKUMENT)
    assert "PDF wählen" in _knoepfe(seite)
    assert any(t.startswith("Dokument: ") for t in _texte(seite))


def test_dokument_an_der_notiz_zum_tag(welt, page) -> None:  # noqa: F811
    state = welt.state
    notiz = state.tagesnotizen.anlegen(state.profil.id, state.heute(), "")
    ziel = Ziel.fuer_notiz(state.profil.id, state.heute(), notiz.id)
    d = neuer_anhang(ziel, DOKUMENT, Qualitaet.GROSS, frontbild=True)
    state.anhaenge.anlegen(d, pdf_aus_jpegs([SEITE]), SEITE)
    assert [a.art for a in state.anhaenge.zur_notiz(notiz.id)] == [DOKUMENT]


def test_migration_060_behaelt_zeilen_und_erlaubt_dokumente(tmp_path) -> None:
    con = sqlite3.connect(tmp_path / "alt.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    alt = tmp_path / "bis59"
    alt.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 59:
            shutil.copy(datei, alt / datei.name)
    assert migrieren(con, alt) == 59
    con.execute("INSERT INTO subject (id, name, created_at, updated_at) VALUES ('p', 'P', '', '')")
    con.execute(
        "INSERT INTO entry_media (id, subject_id, day, kind, uri, recorded_at) "
        "VALUES ('a', 'p', '2026-11-13', 'audio', 'x.m4a', '')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO entry_media (id, subject_id, day, kind, uri, recorded_at) "
            "VALUES ('d', 'p', '2026-11-13', 'document', 'x.pdf', '')"
        )
    con.commit()
    assert migrieren(con) == 61
    con.execute(
        "INSERT INTO entry_media (id, subject_id, day, kind, uri, recorded_at) "
        "VALUES ('d', 'p', '2026-11-13', 'document', 'x.pdf', '')"
    )
    assert [r["kind"] for r in con.execute("SELECT kind FROM entry_media ORDER BY id")] == [
        "audio",
        "document",
    ]
    con.close()
