"""Eine verkleinerte Datei übernehmen (`Paketablage.ersetzen`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §5): Alle Stücke zeigen auf die neue Datei — an Übung, Planübung und
Plan, auch „ersetzt“ —, der Haken „gesehen“ geht mit; das Original bleibt auf dem Gerät, bis man
es löscht oder wieder nimmt."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource, Plan, Subject
from trainingsapp.core.paketmedien import name_fuer
from trainingsapp.data.db import oeffnen
from trainingsapp.data.material import MaterialRepo
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo


@pytest.fixture
def umgebung(tmp_path):
    con = oeffnen(tmp_path / "app.db")
    ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    yield con, ablage, ich
    con.close()


def _datei(ablage: Paketablage, daten: bytes) -> str:
    name = name_fuer(hashlib.sha256(daten).hexdigest(), "mp4")
    pfad = ablage.pfad(name)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return name


def _video(uri: str, **mehr) -> Media:
    return Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=uri, **mehr)


def test_ersetzen_ueberall_und_original_behalten(umgebung) -> None:
    con, ablage, ich = umgebung
    gross = _datei(ablage, b"gross" * 100)
    klein = _datei(ablage, b"klein")
    uebung = Exercise(name="Kniebeuge", media=[_video(gross, title="Film", zeigen=True)])
    ExerciseRepo(con).speichern(uebung)
    plaene = PlanRepo(con)
    plan = Plan(name="Beine", subject_id=ich.id, media=[_video(gross, title="Am Plan")])
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, uebung.id)
    plaene.item_speichern(
        replace(item, media=[Media(uri="https://x.org/stufe", ersetzt=gross), _video(gross)])
    )
    MaterialRepo(con).setzen(ich.id, gross)
    assert ablage.ersetzen(gross, klein) == 1
    assert [m.uri for m in ExerciseRepo(con).laden(uebung.id).media] == [klein]
    plan = plaene.laden(plan.id)
    assert [m.uri for m in plan.media] == [klein]
    item = plan.items[0]
    assert [(m.uri, m.ersetzt) for m in item.media] == [("https://x.org/stufe", klein), (klein, "")]
    assert klein in MaterialRepo(con).gesehen(ich.id)
    # Das Original bleibt vermerkt — die Ablage räumt es nicht weg
    assert ablage.original(klein) == gross
    ablage.aufraeumen()
    assert ablage.vorhanden(gross) and ablage.vorhanden(klein)
    # Wieder das Original: die verkleinerte Fassung geht
    ablage.ersetzen(klein, gross, original_behalten=False)
    assert [m.uri for m in plaene.laden(plan.id).media] == [gross]
    assert ablage.original(gross) is None
    ablage.aufraeumen()
    assert not ablage.vorhanden(klein) and ablage.vorhanden(gross)


def test_original_loeschen_und_verwerfen(umgebung) -> None:
    con, ablage, _ich = umgebung
    gross = _datei(ablage, b"gross" * 100)
    klein = _datei(ablage, b"klein")
    entwurf = _datei(ablage, b"entwurf")
    ExerciseRepo(con).speichern(Exercise(name="Planke", media=[_video(gross)]))
    # Ein Entwurf, den nichts nennt, geht beim Verwerfen gleich weg — ein genannter nie
    ablage.verwerfen(entwurf)
    ablage.verwerfen(gross)
    assert not ablage.vorhanden(entwurf) and ablage.vorhanden(gross)
    ablage.ersetzen(gross, klein)
    # Ein zweites Mal verkleinert: das Original bleibt das erste
    kleiner = _datei(ablage, b"k")
    ablage.ersetzen(klein, kleiner)
    assert ablage.original(kleiner) == gross and ablage.original(klein) is None
    ablage.aufraeumen()
    assert not ablage.vorhanden(klein) and ablage.vorhanden(gross)
    # Original löschen: weg, sobald es nichts mehr nennt
    ablage.original_vergessen(kleiner)
    assert ablage.original(kleiner) is None and not ablage.vorhanden(gross)
    assert ablage.vorhanden(kleiner)
