"""Medien am Plan selbst (Migration 069, Ben 17.11.2026, `docs/plan_medien_reiter.md` §4,
P225 Stufe 2): speichern und lesen, im Paket hin und zurück, Ablage räumt sie nicht weg — auch
nicht nach dem endgültigen Löschen (d: „ok“, privat)."""

from __future__ import annotations

import hashlib

import pytest

from trainingsapp.core.models import Media, MediaKind, MediaSource, Plan, Subject
from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip
from trainingsapp.core.pakete import (
    PaketPlan,
    paket_json,
    paket_lesen,
    paketmedien_in,
    paketplan_aus,
    plan_abgleichen,
)
from trainingsapp.core.paketmedien import name_fuer
from trainingsapp.data.db import letzte_migration, oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import PlanRepo, SubjectRepo

LINK = "https://x.org/so-laeuft-es"


@pytest.fixture
def umgebung(tmp_path):
    con = oeffnen(tmp_path / "app.db")
    ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    yield con, ablage, ich
    con.close()


def _datei(ablage: Paketablage, daten: bytes, endung: str) -> str:
    name = name_fuer(hashlib.sha256(daten).hexdigest(), endung)
    pfad = ablage.pfad(name)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return name


def test_speichern_lesen_setzen_und_aufraeumen(umgebung) -> None:
    con, ablage, ich = umgebung
    assert letzte_migration() >= 69
    film = _datei(ablage, b"\x00\x00\x00\x08ftyp" + b"film", "mp4")
    plaene = PlanRepo(con)
    plan = Plan(
        name="Beine",
        subject_id=ich.id,
        description="## So läuft es\nDreimal die Woche",
        media=[
            Media(uri=LINK, title="So läuft es", zeigen=True),
            Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=film, title="Film"),
        ],
    )
    plaene.speichern(plan)
    geladen = plaene.laden(plan.id)
    assert [(m.uri, m.zeigen) for m in geladen.media] == [(LINK, True), (film, False)]
    # Die schmalen Setzer lassen den Rest des Plans, wie er ist
    plaene.medien_setzen(plan.id, [geladen.media[1]])
    plaene.beschreibung_setzen(plan.id, "  Anders  ")
    geladen = plaene.laden(plan.id)
    assert [m.uri for m in geladen.media] == [film] and geladen.description == "Anders"
    assert geladen.name == "Beine"
    # Die Ablage kennt die Datei des Plans …
    ablage.aufraeumen()
    assert ablage.vorhanden(film)
    # … auch, wenn der Plan endgültig gelöscht ist: sie bleibt privat auf dem Gerät (P225 d)
    plaene.loeschen(plan.id)
    plaene.endgueltig_loeschen(plan.id)
    ablage.aufraeumen()
    assert ablage.vorhanden(film)
    # Ohne Verweis geht sie
    con.execute("UPDATE plan SET media_json = NULL WHERE id = ?", (plan.id,))
    ablage.aufraeumen()
    assert not ablage.vorhanden(film)


def test_paket_hin_und_zurueck_mit_datei(tmp_path, umgebung) -> None:
    con, ablage, ich = umgebung
    pdf_daten = b"%PDF-1.7 Wochenplan"
    pdf = name_fuer(hashlib.sha256(pdf_daten).hexdigest(), "pdf")
    roh = {
        "paket": {"name": "Knie-Reha", "version": 1},
        "exercises": [{"key": "beuge", "name": "Kniebeuge"}],
        "plaene": [
            {
                "key": "woche1",
                "name": "Woche 1",
                "beschreibung": "## Ablauf\nErst lockern",
                "medien": [
                    {"uri": LINK, "title": "Einstimmung", "zeigen": True},
                    {"source": "paket", "uri": pdf, "title": "Wochenplan"},
                    # eine Begleitung gibt es am Plan nicht — sie wird zur Erklärung
                    {"uri": "https://x.org/musik", "rolle": "begleitung"},
                ],
                "uebungen": [{"uebung": "beuge"}],
            }
        ],
    }
    inhalt = paket_lesen(roh)
    (pp,) = inhalt.plaene
    assert [m.uri for m in pp.medien] == [LINK, pdf, "https://x.org/musik"]
    assert [m.rolle for m in pp.medien] == ["", "", ""]
    assert paketmedien_in([], plaene=[pp]) == {pdf}
    quelle = tmp_path / "w.pdf"
    quelle.write_bytes(pdf_daten)
    datei = tmp_path / "paket.zip"
    paket_zip(datei, paket_json(inhalt.paket, inhalt.uebungen, plaene=inhalt.plaene), {pdf: quelle})
    PaketRepo(con, ablage).importieren(paket_oeffnen(datei), subject_id=ich.id)
    (plan,) = PlanRepo(con).des_pakets(inhalt.paket.id, ich.id)
    assert [(m.uri, m.source, m.zeigen) for m in plan.media][:2] == [
        (LINK, MediaSource.URL, True),
        (pdf, MediaSource.PAKET, False),
    ]
    assert plan.description == "## Ablauf\nErst lockern" and ablage.vorhanden(pdf)
    # Zurück ins Paket: die Medien gehen mit
    zurueck = paketplan_aus(plan)
    assert [m.uri for m in zurueck.medien] == [m.uri for m in plan.media]
    assert PaketPlan.from_dict(zurueck.to_dict()).medien[1].uri == pdf


def test_abgleich_laesst_eigene_medien_des_plans() -> None:
    alt = {"name": "Knie", "uebungen": [{"uebung": "a"}], "medien": [{"uri": "https://x/1"}]}
    neu_paket = {**alt, "medien": [{"uri": "https://x/2"}]}
    # nicht angefasst: das Update bringt die neuen
    assert plan_abgleichen(alt, alt, neu_paket)["medien"] == [{"uri": "https://x/2"}]
    # selbst geändert: die eigenen bleiben
    mein = {**alt, "medien": [{"uri": "https://x/mein"}]}
    assert plan_abgleichen(alt, mein, neu_paket)["medien"] == [{"uri": "https://x/mein"}]
