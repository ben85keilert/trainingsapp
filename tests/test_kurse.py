"""Kurse: Rechnung (`core/kurse.py`), Datenbank (`data/kurse.py`), Paketformat, Seed.

Regeln von Ben (15.10.2026): Kapitel linear, Bedingung vor dem nächsten,
Überspringen auf Rückfrage, Pläne je Kapitel mit Wochentagen am Plan — und ein
Kurs darf einfach nur erklären (HRV-Einführung).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trainingsapp.core.kurse import (
    AKTUELL,
    FERTIG,
    GELESEN,
    GESPERRT,
    MESSUNG,
    SUMME,
    TAGE,
    UEBERSPRUNGEN,
    Bedingung,
    Kapitel,
    Kapitelstand,
    Kurs,
    PlanVorlage,
    Stand,
    VorlageItem,
    abgeschlossen,
    aktuelles,
    bedingung_stand,
    fehlt_text,
    fortschritt_text,
    stand_text,
    status,
)
from trainingsapp.core.models import Exercise, HrvRecording, Media, MediaKind, Plan, Subject
from trainingsapp.core.pakete import (
    GRUNDAUSSTATTUNG,
    Paket,
    PaketFehler,
    kapitel_id,
    kurs_aus_stand,
    kurs_id,
    kurs_stand,
    paket_bauen,
    paket_lesen,
)
from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
from trainingsapp.data.db import oeffnen
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.pakete import PaketRepo, Status
from trainingsapp.data.repositories import ExerciseRepo, HrvRepo, PlanRepo, SessionRepo, SubjectRepo
from trainingsapp.data.seed import seed_einspielen, seed_id, seed_inhalt


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    seed_einspielen(verbindung)
    yield verbindung
    verbindung.close()


@pytest.fixture
def profil(con) -> Subject:
    s = Subject(name="Test")
    SubjectRepo(con).speichern(s)
    return s


def kurs_mit_plan(uebung_id: str) -> Kurs:
    """Zwei Kapitel: lesen, dann 100 Wiederholungen mit einem täglichen Plan."""
    return Kurs(
        name="Testkurs",
        kapitel=[
            Kapitel(titel="Lesen", text="# Hallo"),
            Kapitel(
                titel="Üben",
                plaene=[PlanVorlage("Kurs: Üben", [0, 2, 4], [VorlageItem(uebung_id)])],
                bedingung=Bedingung(SUMME, uebung_id, "reps", 100),
                media=[Media(kind=MediaKind.AUDIO, uri="https://x/a.mp3", title="Ton")],
            ),
            Kapitel(titel="Ende"),
        ],
    )


# ---------------------------------------------------------------------------
# Rechnung
# ---------------------------------------------------------------------------


def test_status_folgt_der_reihenfolge() -> None:
    k = kurs_mit_plan("u")
    a, b, c = k.kapitel
    t = datetime.now(UTC)
    assert status(k, {})[a.id] == AKTUELL and status(k, {})[c.id] == GESPERRT
    staende = {a.id: Kapitelstand(a.id, t, t), b.id: Kapitelstand(b.id, t, t, uebersprungen=True)}
    s = status(k, staende)
    assert (s[a.id], s[b.id], s[c.id]) == (FERTIG, UEBERSPRUNGEN, AKTUELL)
    assert aktuelles(k, staende) is c
    assert fortschritt_text(k, staende) == "Kapitel 3 von 3"
    staende[c.id] = Kapitelstand(c.id, t, t)
    assert abgeschlossen(k, staende) and fortschritt_text(k, staende) == "abgeschlossen"


def test_bedingung_messung_zaehlt_nur_dauer_und_zeitpunkt() -> None:
    seit = datetime(2026, 10, 12, 8, tzinfo=UTC)
    b = Bedingung(MESSUNG, soll=5)
    kurz = HrvRecording(started_at=seit + timedelta(hours=1), duration_s=120)
    frueher = HrvRecording(started_at=seit - timedelta(days=1), duration_s=900)
    passt = HrvRecording(started_at=seit + timedelta(hours=2), duration_s=301)
    assert not bedingung_stand(b, seit, messungen=[kurz, frueher]).erfuellt
    assert bedingung_stand(b, seit, messungen=[kurz, passt]).erfuellt
    assert bedingung_stand(b, None, messungen=[passt]).erfuellt is False  # Kapitel nicht erreicht
    assert stand_text(b, Stand(0, 5)) == "noch keine Messung von 5 min"
    assert fehlt_text(Bedingung(SUMME, "u", "reps", 100), Stand(40, 100)) == "Noch 60 Wdh."


def test_bedingung_json_rundreise() -> None:
    b = Bedingung(SUMME, "u1", "hold", 300)
    assert Bedingung.from_dict(b.to_dict()) == b
    v = PlanVorlage("P", [1, 3], [VorlageItem("u1", {"reps": [10]}, ["reps"])])
    zurueck = PlanVorlage.from_dict(v.to_dict())
    assert zurueck == v
    assert Bedingung.from_dict({"art": "quatsch", "soll": "x"}) == Bedingung(GELESEN, soll=0)


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------


def test_speichern_und_laden_mit_kapiteln(con) -> None:
    repo = KursRepo(con)
    k = kurs_mit_plan(seed_id("liegestuetzen"))
    repo.speichern(k)
    zurueck = repo.laden(k.id)
    assert zurueck is not None
    assert [c.titel for c in zurueck.kapitel] == ["Lesen", "Üben", "Ende"]
    ueben = zurueck.kapitel[1]
    assert ueben.bedingung == Bedingung(SUMME, seed_id("liegestuetzen"), "reps", 100)
    assert ueben.plaene[0].wochentage == [0, 2, 4]
    assert ueben.media[0].kind == MediaKind.AUDIO and ueben.media[0].title == "Ton"
    assert ueben.text == "" and zurueck.kapitel[0].text == "# Hallo"

    # Kapitel abgleichen: eins weg, eins neu — die anderen behalten ihre ID
    k.kapitel = [k.kapitel[0], Kapitel(titel="Neu")]
    repo.speichern(k)
    wieder = repo.laden(k.id)
    assert wieder is not None
    assert [c.id for c in wieder.kapitel] == [k.kapitel[0].id, k.kapitel[1].id]
    assert len(repo.alle()) == 2  # plus der Kurs aus dem Standardpaket


def test_starten_legt_plaene_an_und_abschliessen_deaktiviert_sie(con, profil) -> None:
    repo, plaene = KursRepo(con), PlanRepo(con)
    k = kurs_mit_plan(seed_id("liegestuetzen"))
    repo.speichern(k)
    lesen, ueben, ende = k.kapitel

    erstes = repo.starten(k, profil.id)
    assert erstes is lesen
    staende = repo.staende(profil.id, k.id)
    assert set(staende) == {lesen.id} and staende[lesen.id].abgeschlossen is None
    assert repo.kapitel_plaene(lesen.id, profil.id) == []  # Lesen hat keinen Plan

    naechstes = repo.kapitel_abschliessen(k, lesen, profil.id)
    assert naechstes is ueben
    (plan,) = repo.kapitel_plaene(ueben.id, profil.id)
    assert plan.aktiv and plan.wochentage == [0, 2, 4] and plan.kurs_kapitel_id == ueben.id
    assert plan.subject_id == profil.id and [i.exercise_id for i in plan.items] == [
        seed_id("liegestuetzen")
    ]
    assert plan in plaene.alle(profil.id)  # erscheint in der Planverwaltung und auf „Heute“

    # Überspringen: abgeschlossen, aber markiert; der Plan wird deaktiviert, nicht gelöscht
    repo.kapitel_abschliessen(k, ueben, profil.id, uebersprungen=True)
    staende = repo.staende(profil.id, k.id)
    assert staende[ueben.id].uebersprungen and staende[ueben.id].abgeschlossen is not None
    assert staende[ende.id].abgeschlossen is None
    plan_danach = plaene.laden(plan.id)
    assert plan_danach is not None and not plan_danach.aktiv
    assert status(k, staende)[ende.id] == AKTUELL

    # Zurücksetzen und neu beginnen: kein zweiter Plan, der alte wird wieder aktiv
    repo.zuruecksetzen(k, profil.id)
    assert repo.staende(profil.id, k.id) == {}
    repo.starten(k, profil.id)
    repo.kapitel_abschliessen(k, lesen, profil.id)
    wieder = repo.kapitel_plaene(ueben.id, profil.id)
    assert [p.id for p in wieder] == [plan.id] and wieder[0].aktiv


def test_stand_summe_zaehlt_ab_kapitelstart_mit_varianten(con, profil) -> None:
    repo, uebungen, sitzungen = KursRepo(con), ExerciseRepo(con), SessionRepo(con)
    original = uebungen.laden(seed_id("liegestuetzen"))
    assert original is not None
    variante = Exercise(name="Liegestütz eng", result_spec=SPEC_SAETZE_WDH, family_id=original.id)
    uebungen.speichern(variante)
    k = kurs_mit_plan(original.id)
    repo.speichern(k)
    lesen, ueben, _ = k.kapitel

    # Ein Eintrag von vor dem Kapitelstart zählt nicht
    session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
    sitzungen.eintrag_anlegen(session, original, {"reps": [50]})
    repo.starten(k, profil.id)
    repo.kapitel_abschliessen(k, lesen, profil.id)
    staende = repo.staende(profil.id, k.id)
    assert repo.stand(ueben, profil.id, staende) == Stand(0.0, 100.0)

    sitzungen.eintrag_anlegen(session, original, {"reps": [20, 20]})
    sitzungen.eintrag_anlegen(session, variante, {"reps": [30]})  # Variante zählt mit
    stand = repo.stand(ueben, profil.id, staende)
    assert (stand.ist, stand.erfuellt) == (70.0, False)
    sitzungen.eintrag_anlegen(session, original, {"reps": [30]})
    assert repo.stand(ueben, profil.id, staende).erfuellt


def test_stand_messung_sieht_aufzeichnungen(con, profil) -> None:
    repo = KursRepo(con)
    k = Kurs(name="M", kapitel=[Kapitel(titel="Messen", bedingung=Bedingung(MESSUNG, soll=5))])
    repo.speichern(k)
    repo.starten(k, profil.id)
    staende = repo.staende(profil.id, k.id)
    assert not repo.stand(k.kapitel[0], profil.id, staende).erfuellt
    HrvRepo(con).anlegen(
        HrvRecording(
            subject_id=profil.id, file_path="x.json", duration_s=330, started_at=datetime.now(UTC)
        )
    )
    assert repo.stand(k.kapitel[0], profil.id, staende).erfuellt


def test_stand_tage_zaehlt_uebungstage_der_kapitelplaene(con, profil) -> None:
    repo, sitzungen, uebungen = KursRepo(con), SessionRepo(con), ExerciseRepo(con)
    atmung = uebungen.laden(seed_id("kohaerenzatmung"))
    andere = uebungen.laden(seed_id("wadenheben"))
    assert atmung is not None and andere is not None
    k = Kurs(
        name="T",
        kapitel=[
            Kapitel(
                titel="Atmen",
                plaene=[PlanVorlage("Atmung", items=[VorlageItem(atmung.id)])],
                bedingung=Bedingung(TAGE, soll=2),
            )
        ],
    )
    repo.speichern(k)
    repo.starten(k, profil.id)
    staende = repo.staende(profil.id, k.id)
    (plan,) = repo.kapitel_plaene(k.kapitel[0].id, profil.id)
    heute = datetime.now(UTC).astimezone().date()
    session = sitzungen.session_fuer(profil.id, plan.id, heute)
    sitzungen.eintrag_anlegen(session, andere, {"reps": [10]})  # keine Kursübung
    assert repo.stand(k.kapitel[0], profil.id, staende).ist == 0
    sitzungen.erledigt(session, atmung)
    sitzungen.erledigt(session, atmung)  # zweimal am selben Tag = ein Tag
    assert repo.stand(k.kapitel[0], profil.id, staende) == Stand(1.0, 2.0)


def test_plan_mit_kurskapitel_ueberlebt_speichern(con, profil) -> None:
    plaene = PlanRepo(con)
    p = Plan(name="P", subject_id=profil.id, kurs_kapitel_id=None)
    plaene.speichern(p)
    zurueck = plaene.laden(p.id)
    assert zurueck is not None and zurueck.kurs_kapitel_id is None


# ---------------------------------------------------------------------------
# Paketformat und Seed
# ---------------------------------------------------------------------------


def paket_mit_kurs() -> dict:
    return {
        "paket": {"name": "Qigong"},
        "exercises": [{"key": "baum", "name": "Stehen wie ein Baum", "spec": "halten"}],
        "kurse": [
            {
                "key": "einstieg",
                "name": "Einstieg",
                "kapitel": [
                    {"key": "a", "titel": "Warum stehen?", "text": "Text"},
                    {
                        "key": "b",
                        "titel": "Stehen üben",
                        "plaene": [{"name": "Stehen", "uebungen": [{"uebung": "baum"}]}],
                        "bedingung": {"art": "tage", "soll": 3},
                    },
                ],
            }
        ],
    }


def test_paket_mit_kurs_lesen_und_schreiben() -> None:
    inhalt = paket_lesen(paket_mit_kurs())
    (kurs,) = inhalt.kurse
    baum = inhalt.uebungen[0]
    assert kurs.id == kurs_id(inhalt.paket.id, "einstieg") and kurs.package_id == inhalt.paket.id
    assert kurs.kapitel[0].id == kapitel_id(kurs.id, "a")
    assert kurs.kapitel[1].plaene[0].items[0].exercise_id == baum.id  # Schlüssel → ID
    assert kurs.kapitel[1].bedingung == Bedingung(TAGE, soll=3)

    roh = paket_bauen(Paket(id=inhalt.paket.id, name="Qigong"), inhalt.uebungen, kurse=inhalt.kurse)
    assert roh["version"] == 2
    wieder = paket_lesen(roh).kurse[0]
    assert kurs_stand(wieder) == kurs_stand(kurs)
    assert [k.id for k in wieder.kapitel] == [k.id for k in kurs.kapitel]
    assert (
        kurs_aus_stand(kurs.id, inhalt.paket.id, kurs_stand(kurs)).kapitel[1].titel == "Stehen üben"
    )
    ohne_kurse = paket_bauen(Paket(id="p", name="X"), inhalt.uebungen)
    assert ohne_kurse["version"] == 1 and "kurse" not in ohne_kurse


def test_paket_nur_mit_kursen_und_fehler() -> None:
    nur_kurs = paket_mit_kurs()
    nur_kurs["exercises"] = []
    nur_kurs["kurse"][0]["kapitel"][1].pop("plaene")
    assert paket_lesen(nur_kurs).kurse[0].name == "Einstieg"
    kaputt = paket_mit_kurs()
    kaputt["kurse"][0]["kapitel"][1]["bedingung"] = {"art": "summe", "soll": 10}
    with pytest.raises(PaketFehler, match="braucht eine Übung"):
        paket_lesen(kaputt)
    leer = paket_mit_kurs()
    leer["kurse"][0]["kapitel"] = []
    with pytest.raises(PaketFehler, match="kein Kapitel"):
        paket_lesen(leer)
    ton = paket_mit_kurs()
    ton["exercises"][0]["media"] = [{"kind": "audio", "uri": "https://x/a.mp3"}]
    with pytest.raises(PaketFehler, match="Ton gibt es nur an Kurskapiteln"):
        paket_lesen(ton)


def test_import_legt_kurse_an_und_aktualisiert_nur_eigene_pakete(con, profil) -> None:
    pakete, kurse = PaketRepo(con), KursRepo(con)
    inhalt = paket_lesen(paket_mit_kurs())
    vorschau = pakete.vorschau(inhalt)
    assert vorschau.anzahl_kurse(Status.NEU) == 1 and vorschau.zu_tun
    assert "1 Kurs neu" in vorschau.zusammenfassung()
    pakete.importieren(inhalt)
    (kurs,) = pakete.kurse(inhalt.paket.id)
    assert kurs.name == "Einstieg"

    # Fortschritt, dann Update: Kapitel-ID bleibt, Fortschritt bleibt
    kurse.starten(kurs, profil.id)
    neu = paket_mit_kurs()
    neu["kurse"][0]["kapitel"][0]["text"] = "Neuer Text"
    inhalt2 = paket_lesen(neu)
    v2 = pakete.vorschau(inhalt2)
    assert v2.kurse[kurs.id] == Status.GEAENDERT
    pakete.importieren(inhalt2)
    wieder = kurse.laden(kurs.id)
    assert wieder is not None and wieder.kapitel[0].text == "Neuer Text"
    assert set(kurse.staende(profil.id, kurs.id)) == {kurs.kapitel[0].id}
    assert pakete.vorschau(inhalt2).kurse[kurs.id] == Status.UNVERAENDERT

    # Entfernen nimmt den Kurs aus der Liste, Wieder installieren bringt ihn zurück
    pakete.entfernen(inhalt.paket.id)
    assert kurses_liste(kurse) == ["HRV-Messung verstehen"]
    zurueck = pakete.inhalt(inhalt.paket.id)
    assert zurueck is not None and [k.name for k in zurueck.kurse] == ["Einstieg"]
    v3 = pakete.vorschau(zurueck)
    assert v3.kurse[kurs.id] == Status.ZURUECK
    pakete.importieren(zurueck)
    assert "Einstieg" in kurses_liste(kurse)
    assert set(kurse.staende(profil.id, kurs.id)) == {kurs.kapitel[0].id}  # Fortschritt blieb


def kurses_liste(kurse: KursRepo) -> list[str]:
    return [k.name for k in kurse.alle()]


def test_standardpaket_bringt_den_einfuehrungskurs_mit(con, profil) -> None:
    inhalt = seed_inhalt()
    (kurs,) = inhalt.kurse
    assert kurs.id == kurs_id(GRUNDAUSSTATTUNG, "hrv_einfuehrung")
    assert kurs.name == "HRV-Messung verstehen" and len(kurs.kapitel) == 7
    arten = [k.bedingung.art for k in kurs.kapitel]
    assert MESSUNG in arten and TAGE in arten
    atmen = next(k for k in kurs.kapitel if k.bedingung.art == TAGE)
    assert atmen.plaene[0].items[0].exercise_id == seed_id("kohaerenzatmung")
    assert all(k.text.strip() for k in kurs.kapitel), "jedes Kapitel hat Text"

    repo = KursRepo(con)
    assert [k.name for k in repo.alle()] == ["HRV-Messung verstehen"]
    da = repo.laden(kurs.id)
    assert da is not None and da.package_id == GRUNDAUSSTATTUNG
    assert repo.standard(kurs.id) == kurs_stand(kurs)
    # Ein zweiter Start ändert nichts
    assert seed_einspielen(con) == 0
    assert len(repo.alle()) == 1
