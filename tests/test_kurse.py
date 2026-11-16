"""Kurse: Rechnung (`core/kurse.py`), Datenbank (`data/kurse.py`), Paketformat, Seed.

Regeln von Ben (15.10.2026): Kapitel linear, Bedingung vor dem nächsten,
Überspringen auf Rückfrage, Pläne je Kapitel mit Wochentagen am Plan — und ein
Kurs darf einfach nur erklären (HRV-Einführung).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    SKALA,
    TEST,
    Block,
    Vorgabe,
)
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
    Kursplan,
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
from trainingsapp.core.kursplan import NEU, OFFEN, UEBERNOMMEN, WEICHT_AB, wahl_im_plan
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
    assert repo.fruehere_plaene(ueben.id, profil.id) == []  # kein Test, keine Auswahl


def test_von_vorn_fragt_test_und_auswahl_neu(con, profil) -> None:
    """Ben, 16.11.2026 (`docs/plan_kurs_ablauf.md` §5.2): Bis Migration 063 holte „Von vorn“
    den alten Kapitelplan mit der alten Wahl zurück — die neue Wahl und der neue Test galten
    nie. Jetzt bleibt der alte Plan als früherer Durchlauf stehen, und das Kapitel legt einen
    neuen an."""
    repo, plaene, uebungen = KursRepo(con), PlanRepo(con), ExerciseRepo(con)
    ids = []
    for name in ("Planke", "Dehnen", "Käfer", "Brücke"):
        u = Exercise(name=f"Probe {name}", result_spec=SPEC_SAETZE_WDH)
        uebungen.speichern(u)
        ids.append(u.id)
    a, b, c, d = ids
    kurs = Kurs(
        name="Mit Test",
        kapitel=[
            Kapitel(
                titel="Rumpf",
                plaene=[PlanVorlage("Rumpf", [0], [VorlageItem(a), VorlageItem(b)])],
                bloecke=[
                    Block(TEST, id="t", uebung=a, feld="reps"),
                    Block(AUSWAHL, id="w", uebungen=[c, d], anzahl=1, nach=1),
                ],
            ),
            Kapitel(titel="Ende"),
        ],
    )
    repo.speichern(kurs)
    kurs = repo.laden(kurs.id)
    assert kurs is not None
    kapitel = kurs.kapitel[0]

    repo.starten(kurs, profil.id)
    assert repo.letzte_wahl(kapitel, profil.id) == {}
    (erster,) = repo.plaene_anlegen(kapitel, profil.id, {"t": 20}, {"w": [c]})
    assert [i.exercise_id for i in erster.items] == [a, c, b]
    assert erster.items[0].target["reps"] in (20, [20])

    repo.zuruecksetzen(kurs, profil.id)
    repo.starten(kurs, profil.id)
    # Der alte Plan ist ein früherer Durchlauf: deaktiviert, umbenannt, sonst unverändert —
    # und nicht mehr „der Plan des Kapitels“
    assert repo.kapitel_plaene(kapitel.id, profil.id) == []
    (frueher,) = repo.fruehere_plaene(kapitel.id, profil.id)
    assert frueher.id == erster.id and not frueher.aktiv
    assert frueher.name == "Rumpf · Durchlauf 1" and frueher.kurs_durchlauf_beendet is not None
    assert [i.exercise_id for i in frueher.items] == [a, c, b]
    assert repo.kurs_und_kapitel(frueher) is not None  # die Herkunft bleibt sichtbar
    assert repo.kapitelplan_vorlage(frueher) is None  # neu laden lässt er sich nicht mehr
    assert repo.kapitelplan_neu_laden(frueher.id, hart=True) is None
    # Was beim letzten Mal gewählt war, ist nur eine Vorbelegung …
    assert repo.letzte_wahl(kapitel, profil.id) == {"w": [c]}
    # … denn jetzt gelten die neue Wahl und der neue Test
    (zweiter,) = repo.plaene_anlegen(kapitel, profil.id, {"t": 50}, {"w": [d]})
    assert zweiter.id != erster.id and zweiter.name == "Rumpf" and zweiter.aktiv
    assert [i.exercise_id for i in zweiter.items] == [a, d, b]
    assert zweiter.items[0].target["reps"] in (50, [50])

    # Speichern (etwa aus dem Plan-Editor) nimmt dem früheren Plan die Marke nicht
    frueher.description = "vom ersten Mal"
    plaene.speichern(frueher)
    nachher = plaene.laden(frueher.id)
    assert nachher is not None and nachher.kurs_durchlauf_beendet is not None
    # Noch einmal von vorn: Der zweite Plan wird „Durchlauf 2“, der erste bleibt, wie er heißt
    repo.zuruecksetzen(kurs, profil.id)
    namen = sorted(p.name for p in repo.fruehere_plaene(kapitel.id, profil.id))
    assert namen == ["Rumpf · Durchlauf 1", "Rumpf · Durchlauf 2"]
    assert repo.letzte_wahl(kapitel, profil.id) == {"w": [d]}


def test_kurs_entfernen_deaktiviert_kapitelplaene_aller_profile(con, profil) -> None:
    """Ben, 14.11.2026: Ein eigener Kurs lässt sich löschen — seine Kapitelpläne werden
    deaktiviert, bei allen Profilen, und bleiben in der Planliste zum einzelnen Löschen."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    zweite = Subject(name="Zweite")
    SubjectRepo(con).speichern(zweite)
    k = kurs_mit_plan(seed_id("liegestuetzen"))
    repo.speichern(k)
    lesen, ueben, _ende = k.kapitel
    for person in (profil, zweite):
        repo.starten(k, person.id)
        repo.kapitel_abschliessen(k, lesen, person.id)
    (meiner,) = repo.kapitel_plaene(ueben.id, profil.id)
    (ihrer,) = repo.kapitel_plaene(ueben.id, zweite.id)
    assert meiner.aktiv and ihrer.aktiv
    # Ein Plan im Papierkorb zählt nicht mit
    plaene.loeschen(ihrer.id)

    assert repo.entfernen(k) == 1
    assert repo.laden(k.id) is None and k.id not in [x.id for x in repo.alle()]
    assert repo.laden(k.id, mit_geloeschten=True) is not None  # weich gelöscht
    danach = plaene.laden(meiner.id)
    assert danach is not None and not danach.aktiv
    assert meiner.id in [p.id for p in plaene.alle(profil.id)]  # bleibt in der Planliste
    assert set(repo.staende(profil.id, k.id)) == {lesen.id, ueben.id}  # Fortschritt bleibt
    # … und lässt sich dort einzeln löschen
    plaene.loeschen(meiner.id)
    assert meiner.id not in [p.id for p in plaene.alle(profil.id)]


def test_stand_summe_zaehlt_ab_kapitelstart_nur_die_eigene_uebung(con, profil) -> None:
    """Eine Kopie ist eine eigene Übung — ihre Einträge zählen nicht für die Bedingung
    (seit 26.10.2026 ohne „Im Verlauf zusammen mit“)."""
    repo, uebungen, sitzungen = KursRepo(con), ExerciseRepo(con), SessionRepo(con)
    original = uebungen.laden(seed_id("liegestuetzen"))
    assert original is not None
    kopie = Exercise(name="Liegestütz eng", result_spec=SPEC_SAETZE_WDH)
    uebungen.speichern(kopie)
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
    sitzungen.eintrag_anlegen(session, kopie, {"reps": [30]})  # die Kopie zählt nicht
    stand = repo.stand(ueben, profil.id, staende)
    assert (stand.ist, stand.erfuellt) == (40.0, False)
    sitzungen.eintrag_anlegen(session, original, {"reps": [30, 30]})
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


def test_kapitel_eines_anderen_kurses_wird_nicht_uebernommen(con) -> None:
    """K21: Nennt ein Kurs die Kapitel-ID eines anderen, bricht das Speichern ab —
    am Kapitel hängen Fortschritt und Pläne."""
    repo = KursRepo(con)
    a = Kurs(name="A", kapitel=[Kapitel(titel="Eins", text="x")])
    repo.speichern(a)
    b = Kurs(name="B", kapitel=[Kapitel(id=a.kapitel[0].id, titel="Geklaut", text="y")])
    with pytest.raises(ValueError, match="gehört schon"):
        repo.speichern(b)
    assert [k.titel for k in repo.laden(a.id).kapitel] == ["Eins"]


def test_kapitelplan_neu_laden(con, profil) -> None:
    """U2 (Ben, 9.11.2026: „Wenn man die Übung aus einem Plan löscht, kann man den Plan/Kurs neu
    laden und es wäre wieder da“): Fehlendes zurückholen behält Eigenes, „wie im Kapitel“ setzt
    ganz zurück; die Planübung behält ihre ID, der Fortschritt bleibt."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    liege, knie = seed_id("liegestuetzen"), seed_id("kniebeuge")
    k = kurs_mit_plan(liege)
    k.kapitel[1].plaene[0].items.append(VorlageItem(knie, target={"reps": 10}))
    repo.speichern(k)
    lesen, ueben, _ende = k.kapitel
    repo.starten(k, profil.id)
    repo.kapitel_abschliessen(k, lesen, profil.id)
    (plan,) = repo.kapitel_plaene(ueben.id, profil.id)
    liege_item, _knie_item = plan.items
    # Eigene Fassung: Liegestütz mit eigenem Ziel, Kniebeuge herausgenommen
    liege_item.target = {"reps": 20}
    plan.items = [liege_item]
    plaene.speichern(plan)

    assert repo.kapitelplan_vorschau(plan.id) == (["Kniebeuge"], True)
    neu = repo.kapitelplan_neu_laden(plan.id, hart=False)
    assert neu is not None
    assert [(i.exercise_id, i.target) for i in plaene.laden(plan.id).items] == [
        (liege, {"reps": 20}),
        (knie, {"reps": 10}),
    ]
    assert plaene.laden(plan.id).items[0].id == liege_item.id
    neu = repo.kapitelplan_neu_laden(plan.id, hart=True)
    assert [(i.exercise_id, i.target) for i in plaene.laden(plan.id).items] == [
        (liege, None),
        (knie, {"reps": 10}),
    ]
    assert repo.staende(profil.id, k.id)[lesen.id].abgeschlossen is not None  # Fortschritt


def test_kurs_neu_laden_holt_geloeschte_kapitelplaene_zurueck(con, profil) -> None:
    """„Kurs neu laden“ (U2): Pläne erreichter Kapitel — gelöschte entstehen neu (aktiv nur im
    laufenden Kapitel), vorhandene holen Fehlendes zurück; nicht erreichte Kapitel bleiben."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    liege, knie = seed_id("liegestuetzen"), seed_id("kniebeuge")
    k = kurs_mit_plan(liege)
    k.kapitel[0].plaene = [PlanVorlage("Kurs: Lesen", [1], [VorlageItem(knie)])]
    repo.speichern(k)
    lesen, ueben, ende = k.kapitel
    ende.plaene = [PlanVorlage("Kurs: Ende", [], [VorlageItem(knie)])]
    repo.speichern(k)
    repo.starten(k, profil.id)
    repo.kapitel_abschliessen(k, lesen, profil.id)  # Lesen fertig, Üben läuft
    (alt_lesen,) = repo.kapitel_plaene(lesen.id, profil.id)
    (alt_ueben,) = repo.kapitel_plaene(ueben.id, profil.id)
    plaene.loeschen(alt_lesen.id)
    plaene.endgueltig_loeschen(alt_lesen.id)  # ganz weg
    alt_ueben.name = "Mein Üben"  # umbenannt — gefunden der Reihe nach
    plaene.speichern(alt_ueben)
    plaene.loeschen(alt_ueben.id)  # im Papierkorb

    assert repo.kurs_neu_laden(k, profil.id, hart=False) == (1, 1)
    (neu_lesen,) = repo.kapitel_plaene(lesen.id, profil.id)
    (neu_ueben,) = repo.kapitel_plaene(ueben.id, profil.id)
    assert neu_lesen.id != alt_lesen.id and not neu_lesen.aktiv  # abgeschlossen → deaktiviert
    assert neu_ueben.id == alt_ueben.id and neu_ueben.name == "Mein Üben" and neu_ueben.aktiv
    assert repo.kapitel_plaene(ende.id, profil.id) == []  # nicht erreicht
    # Wie im Kurs: der Name kommt zurück
    assert repo.kurs_neu_laden(k, profil.id, hart=True) == (2, 0)
    assert repo.kapitel_plaene(ueben.id, profil.id)[0].name == "Kurs: Üben"


def test_abgeschlossenes_kapitel_wird_beim_erreichen_nicht_wieder_aktiv(con, profil) -> None:
    """K39: Freischaltung „frei“ — Kapitel 2 zuerst abgeschlossen (Plan deaktiviert), danach
    Kapitel 1: das Erreichen von Kapitel 2 aktiviert dessen Plan nicht wieder."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    k = kurs_mit_plan(seed_id("liegestuetzen"))
    repo.speichern(k)
    lesen, ueben, _ende = k.kapitel
    repo.starten(k, profil.id)
    repo.kapitel_erreichen(k, ueben, profil.id)  # frei geöffnet
    (plan,) = repo.kapitel_plaene(ueben.id, profil.id)
    repo.kapitel_abschliessen(k, ueben, profil.id)
    assert not plaene.laden(plan.id).aktiv
    repo.kapitel_abschliessen(k, lesen, profil.id)  # erreicht Kapitel 2 noch einmal
    assert not plaene.laden(plan.id).aktiv


# ---------------------------------------------------------------------------
# Kursplan (Migration 064, `docs/plan_kurs_ablauf.md` §11) — die Rechnung prüft
# `tests/test_kursplan.py`, hier die Datenbank
# ---------------------------------------------------------------------------


def proben(con, *namen: str) -> list[str]:
    """Eigene Übungen mit Wiederholungen je Satz — ihre IDs."""
    uebungen = ExerciseRepo(con)
    ids = []
    for name in namen:
        u = Exercise(name=name, result_spec=SPEC_SAETZE_WDH)
        uebungen.speichern(u)
        ids.append(u.id)
    return ids


def rumpf_kurs(con, vorlage: PlanVorlage | None = None) -> tuple[Kurs, dict[str, str]]:
    """Bens Beispiel: Kapitel 1 bringt die Planke (Ziel 20 Wdh.), Kapitel 2 lässt eine von
    drei Übungen wählen, hängt sie hinter die Planke, setzt ihr Ziel aus dem Test und verbindet
    beide; Kapitel 3 steigert die Planke. Gespeichert und wieder geladen."""
    planke, seit, kaefer, bruecke = proben(con, "Planke", "Seitstütz", "Käfer", "Brücke")
    kurs = Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf", [0, 2, 4], vorlage=vorlage),
        kapitel=[
            Kapitel(
                titel="Anfang",
                bloecke=[Block(PLAN_UEBUNG, id="a", uebung=planke, ziel={"reps": [20]})],
            ),
            Kapitel(
                titel="Erweiterung",
                bloecke=[
                    Block(AUSWAHL, id="wahl", uebungen=[seit, kaefer, bruecke], anzahl=1),
                    Block(TEST, id="test", uebung=kaefer, feld="reps"),
                    Block(PLAN_UEBUNG, id="dazu", aus="wahl", hinter="a", ziel_aus="test"),
                    Block(
                        PLAN_WEG,
                        id="weg",
                        von="a",
                        zu="dazu",
                        kante={"ausloeser": "zeit", "pflicht": True},
                    ),
                ],
                bedingung=Bedingung(TAGE, soll=2),
            ),
            Kapitel(
                titel="Steigern",
                bloecke=[Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"reps": [40]})],
            ),
        ],
    )
    repo = KursRepo(con)
    repo.speichern(kurs)
    geladen = repo.laden(kurs.id)
    assert geladen is not None
    return geladen, {"planke": planke, "seit": seit, "kaefer": kaefer, "bruecke": bruecke}


def test_kurs_mit_kursplan_und_bausteinen_speichern_und_laden(con) -> None:
    kurs, ids = rumpf_kurs(con, PlanVorlage("egal", [1], [VorlageItem(seed_id("kniebeuge"))]))
    assert kurs.kursplan is not None
    assert (kurs.kursplan.name, kurs.kursplan.wochentage) == ("Rumpf", [0, 2, 4])
    assert kurs.kursplan.vorlage.items[0].exercise_id == seed_id("kniebeuge")
    eins, zwei, drei = kurs.kapitel
    assert [b.art for b in zwei.bloecke] == [AUSWAHL, TEST, PLAN_UEBUNG, PLAN_WEG]
    assert (eins.bloecke[0].uebung, eins.bloecke[0].ziel) == (ids["planke"], {"reps": [20]})
    assert zwei.bloecke[3].kante == {"ausloeser": "zeit", "pflicht": True}
    assert drei.bloecke[0].an == "a"
    # Der Paketstand nimmt den Kursplan mit — eine Kopie über den Stand verliert ihn nicht
    kopie = kurs_aus_stand(kurs.id, "p1", kurs_stand(kurs))
    assert kopie.kursplan == kurs.kursplan
    assert [b.to_dict() for b in kopie.kapitel[1].bloecke] == [b.to_dict() for b in zwei.bloecke]
    # … und die Paketdatei auch
    roh = paket_bauen(Paket(id="p1", name="Rumpf"), ExerciseRepo(con).alle(), kurse=[kurs])
    assert paket_lesen(roh).kurse[0].kursplan == kurs.kursplan
    # Ohne Kursplan bleibt die Spalte leer: Kapitelpläne wie bisher
    ohne = Kurs(name="Ohne", kapitel=[Kapitel(titel="A")])
    KursRepo(con).speichern(ohne)
    assert KursRepo(con).laden(ohne.id).kursplan is None
    kurs.kursplan = None
    KursRepo(con).speichern(kurs)
    assert KursRepo(con).laden(kurs.id).kursplan is None


def test_kursplan_entsteht_beim_start_wenn_die_grundlage_uebungen_hat(con, profil) -> None:
    repo, plaene = KursRepo(con), PlanRepo(con)
    knie = seed_id("kniebeuge")
    kurs, ids = rumpf_kurs(con, PlanVorlage("egal", [1], [VorlageItem(knie, {"reps": [10]})]))
    assert repo.kursplan(kurs, profil.id) is None
    repo.starten(kurs, profil.id)
    plan = repo.kursplan(kurs, profil.id)
    assert plan is not None and plan.aktiv and plan.kurs_id == kurs.id
    assert (plan.name, plan.wochentage, plan.kurs_kapitel_id) == ("Rumpf", [0, 2, 4], None)
    assert [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items] == [
        (knie, "g:1", {"reps": [10]})
    ]
    # ein gewöhnlicher Plan des Profils — und kein Kapitelplan
    assert plan.id in {p.id for p in plaene.alle(profil.id)}
    assert all(repo.kapitel_plaene(k.id, profil.id) == [] for k in kurs.kapitel)
    assert plaene.kurs_stand(plan.id)["g:1"]["ziel"] == {"reps": [10]}
    # anlegen ist idempotent, ein zweiter Start auch
    assert repo.kursplan_anlegen(kurs, profil.id).id == plan.id
    repo.starten(kurs, profil.id)
    assert repo.kursplan(kurs, profil.id).id == plan.id
    # ein anderes Profil bekommt seinen eigenen
    zweites = Subject(name="Zweites")
    SubjectRepo(con).speichern(zweites)
    assert repo.kursplan(kurs, zweites.id) is None
    assert repo.kursplan_anlegen(kurs, zweites.id).id != plan.id

    # Kapitel 1 hängt die Planke an die Grundlage
    (dazu, ziel) = repo.plan_aenderungen(kurs, kurs.kapitel[0], profil.id)
    assert (dazu.titel, dazu.unter, dazu.stand) == ("Planke kommt dazu", "ans Ende", NEU)
    assert ziel.titel == "Ziel für Planke: 20 Wiederholungen"
    neu = repo.plan_uebernehmen(kurs, kurs.kapitel[0], profil.id, {"a", "a#ziel"})
    assert neu.id == plan.id
    assert [i.exercise_id for i in neu.items] == [knie, ids["planke"]]
    # Die Grundlage erkennt der Kurs als seine: Ändert die Person sie, weicht der Plan ab
    grund = [Block(PLAN_EINSTELLEN, id="g", an="g:1", ziel={"reps": [15]})]
    kapitel = Kapitel(id="frei", bloecke=grund)
    assert repo.plan_aenderungen(kurs, kapitel, profil.id)[0].stand == NEU
    plaene.ziel_setzen(neu.items[0].id, {"reps": [12]})
    assert repo.plan_aenderungen(kurs, kapitel, profil.id)[0].stand == WEICHT_AB
    assert repo.plan_uebernehmen(kurs, kapitel, profil.id, {"g#ziel"}).items[0].target == {
        "reps": [12]
    }
    mit = repo.plan_uebernehmen(kurs, kapitel, profil.id, {"g#ziel"}, trotz={"g#ziel"})
    assert mit.items[0].target == {"reps": [15]}


def test_kursplan_ohne_grundlage_entsteht_mit_dem_ersten_uebernehmen(con, profil) -> None:
    """Bens Beispiel durch die Datenbank: Nichts ändert sich ohne Tipp — auch der Plan selbst
    entsteht erst mit „Übernehmen“."""
    repo, plaene, sitzungen = KursRepo(con), PlanRepo(con), SessionRepo(con)
    kurs, ids = rumpf_kurs(con)
    eins, zwei, drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    assert repo.kursplan(kurs, profil.id) is None  # leere Grundlage: noch kein Plan
    zeilen = repo.plan_aenderungen(kurs, eins, profil.id)
    assert [(z.id, z.stand) for z in zeilen] == [("a", NEU), ("a#ziel", NEU)]
    assert repo.kursplan(kurs, profil.id) is None  # vorrechnen legt nichts an

    plan = repo.plan_uebernehmen(kurs, eins, profil.id, {z.id for z in zeilen})
    assert plan.aktiv and plan.kurs_id == kurs.id and plan.name == "Rumpf"
    assert [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items] == [
        (ids["planke"], "a", {"reps": [20]})
    ]
    assert not plan.ablauf.an  # eine Liste
    assert {z.stand for z in repo.plan_aenderungen(kurs, eins, profil.id)} == {UEBERNOMMEN}

    # Kapitel 2: Solange nichts gewählt ist, sind die Zeilen offen
    repo.kapitel_abschliessen(kurs, eins, profil.id)
    assert repo.kursplan(kurs, profil.id).aktiv  # abschließen deaktiviert den Kursplan nicht
    assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id)} == {OFFEN}
    # Gewählt (die Oberfläche hält die Wahl), noch nicht getestet
    wahl = {"wahl": [ids["kaefer"]]}
    marke = f"dazu:{ids['kaefer']}"
    assert [(z.id, z.stand) for z in repo.plan_aenderungen(kurs, zwei, profil.id, wahl)] == [
        (marke, NEU),
        (f"{marke}#ziel", OFFEN),
        ("weg#weg", NEU),
    ]
    # Der Test ist ein gewöhnlicher Eintrag seit dem Erreichen des Kapitels — der beste Satz
    kaefer = ExerciseRepo(con).laden(ids["kaefer"])
    session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
    sitzungen.eintrag_anlegen(session, kaefer, {"reps": [24, 30]})
    zeilen = repo.plan_aenderungen(kurs, zwei, profil.id, wahl)
    assert [(z.titel, z.unter) for z in zeilen] == [
        ("Käfer kommt dazu", "hinter Planke"),
        ("Ziel für Käfer: 30 Wiederholungen", "aus deinem Test"),
        (
            "Von Planke weiter zu Käfer, wenn die Zeit ab ist",
            "Pflicht — Überspringen bleibt möglich",
        ),
    ]
    # Eine unvollständige oder fremde Wahl gilt als nicht getroffen
    assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id, {"wahl": []})} == {OFFEN}
    fremd = {"wahl": [ids["planke"]]}
    assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id, fremd)} == {OFFEN}

    plan = repo.plan_uebernehmen(kurs, zwei, profil.id, {z.id for z in zeilen}, wahl=wahl)
    planke, gewaehlt = plan.items
    assert (gewaehlt.exercise_id, gewaehlt.kurs_marke, gewaehlt.target) == (
        ids["kaefer"],
        marke,
        {"reps": [30]},
    )
    assert plan.ablauf.an and plan.workout  # der Weg macht den Plan zum Workout
    (kante,) = plan.ablauf.kanten
    assert (kante.von, kante.nach, kante.ausloeser, kante.pflicht) == (
        planke.id,
        gewaehlt.id,
        "zeit",
        True,
    )
    # Die Wahl steht jetzt im Plan: Sie gilt ohne Argument — und eine andere ändert sie nicht
    assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id)} == {UEBERNOMMEN}
    andere = {"wahl": [ids["bruecke"]]}
    assert [z.id for z in repo.plan_aenderungen(kurs, zwei, profil.id, andere)] == [
        marke,
        f"{marke}#ziel",
        "weg#weg",
    ]
    # Zweimal übernehmen ändert nichts — auch nicht, wenn sich der jüngste Eintrag ändert
    sitzungen.eintrag_anlegen(session, kaefer, {"reps": [50]})
    wieder = repo.plan_uebernehmen(kurs, zwei, profil.id, {marke, f"{marke}#ziel", "weg#weg"})
    assert [(i.id, i.target) for i in wieder.items] == [(i.id, i.target) for i in plan.items]
    assert wieder.ablauf == plan.ablauf

    # Kapitel 3: Die Person hat das Ziel der Planke selbst geändert — ihr Wert bleibt
    plaene.ziel_setzen(planke.id, {"reps": [25]})
    (zeile,) = repo.plan_aenderungen(kurs, drei, profil.id)
    assert (zeile.stand, zeile.eigen, zeile.kurs) == (
        WEICHT_AB,
        "25 Wiederholungen",
        "40 Wiederholungen",
    )
    assert zeile.titel == (
        "Planke: Du hast 25 Wiederholungen eingestellt. Der Kurs schlägt 40 Wiederholungen vor."
    )
    assert repo.plan_uebernehmen(kurs, drei, profil.id, {"mehr#ziel"}).items[0].target == {
        "reps": [25]
    }
    mit = repo.plan_uebernehmen(kurs, drei, profil.id, {"mehr#ziel"}, trotz={"mehr#ziel"})
    assert mit.items[0].target == {"reps": [40]}


def test_lassen_steht_im_kurs_stand_und_wird_nicht_wieder_gefragt(con, profil) -> None:
    """„… lassen“ in der Karte „Dein Plan weicht ab“: Der Plan bleibt — er wird nicht einmal
    gespeichert —, der Kurs-Stand merkt die Zeile, und beim nächsten Öffnen steht sie nicht
    mehr da."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    kurs, _ids = rumpf_kurs(con)
    eins, _zwei, drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    plan = repo.plan_uebernehmen(kurs, eins, profil.id, {"a", "a#ziel"})
    plaene.ziel_setzen(plan.items[0].id, {"reps": [25]})
    (zeile,) = repo.plan_aenderungen(kurs, drei, profil.id)
    assert zeile.stand == WEICHT_AB
    vorher = plaene.laden(plan.id)

    gelassen = repo.plan_uebernehmen(kurs, drei, profil.id, set(), lassen={"mehr#ziel"})
    assert gelassen == vorher and gelassen.items[0].target == {"reps": [25]}
    assert plaene.kurs_stand(plan.id)["a"]["erledigt"] == ["a#ziel", "mehr#ziel"]
    assert [z.stand for z in repo.plan_aenderungen(kurs, drei, profil.id)] == [UEBERNOMMEN]
    # Ein spätes „übernehmen“ derselben Zeile ändert nichts mehr
    spaet = repo.plan_uebernehmen(kurs, drei, profil.id, {"mehr#ziel"}, trotz={"mehr#ziel"})
    assert spaet == vorher


def test_plan_speichern_erhaelt_marken_herkunft_und_kurs_stand(con, profil) -> None:
    """`PlanRepo.speichern` ersetzt die Übungsliste — die Marken reisen mit; Herkunft und
    Kurs-Stand fasst es nicht an (wie `course_run_ended_at`)."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    kurs, ids = rumpf_kurs(con)
    eins, zwei, _drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    repo.plan_uebernehmen(kurs, eins, profil.id, {"a", "a#ziel"})
    repo.kapitel_abschliessen(kurs, eins, profil.id)
    wahl = {"wahl": [ids["bruecke"]]}
    marke = f"dazu:{ids['bruecke']}"
    plan = repo.plan_uebernehmen(kurs, zwei, profil.id, {marke, "weg#weg"}, wahl=wahl)
    stand = plaene.kurs_stand(plan.id)
    assert stand["a"]["erledigt"] == ["a#ziel", "weg#weg"]

    # aus dem Plan-Editor: Beschreibung ändern, eine eigene Übung dazu, Reihenfolge umdrehen
    plan.description = "Mein Rumpf"
    eigene = plaene.uebung_hinzufuegen(plan.id, seed_id("kniebeuge"))
    assert eigene.kurs_marke == ""
    plan = plaene.laden(plan.id)
    plan.description = "Mein Rumpf"
    plan.items = list(reversed(plan.items))
    plaene.speichern(plan)
    nachher = plaene.laden(plan.id)
    assert nachher.description == "Mein Rumpf" and nachher.kurs_id == kurs.id
    assert [i.kurs_marke for i in nachher.items] == ["", marke, "a"]
    assert plaene.kurs_stand(plan.id) == stand
    assert repo.kursplan(kurs, profil.id).id == plan.id
    # … auch über die einzelnen Schreibwege
    plaene.reihenfolge_setzen(plan.id, [i.id for i in reversed(nachher.items)])
    plaene.item_speichern(plaene.laden(plan.id).items[0])
    plaene.umbenennen(plan.id, "Rumpf, meiner")
    wieder = plaene.laden(plan.id)
    assert [i.kurs_marke for i in wieder.items] == ["a", marke, ""]
    assert plaene.item_laden(wieder.items[1].id).kurs_marke == marke
    assert wieder.kurs_id == kurs.id and plaene.kurs_stand(plan.id) == stand
    # Der Kurs findet seine Planübungen an den Marken wieder, wo immer sie stehen
    assert {z.stand for z in repo.plan_aenderungen(kurs, eins, profil.id)} == {UEBERNOMMEN}
    assert wahl_im_plan(wieder, zwei.bloecke) == wahl
    # Ein Plan ohne Kurs hat weder Herkunft noch Stand
    frei = Plan(name="Frei", subject_id=profil.id)
    plaene.speichern(frei)
    assert plaene.laden(frei.id).kurs_id is None and plaene.kurs_stand(frei.id) == {}


def test_kursplan_von_vorn_wird_zum_frueheren_durchlauf(con, profil) -> None:
    """„Von vorn“ macht den Kursplan immer zum früheren Durchlauf — der neue Start beginnt
    wieder mit der Grundlage, die Nummer zählt weiter."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    knie = seed_id("kniebeuge")
    kurs, ids = rumpf_kurs(con, PlanVorlage("egal", items=[VorlageItem(knie)]))
    eins, zwei, _drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    repo.plan_uebernehmen(kurs, eins, profil.id, {"a"})
    wahl = {"wahl": [ids["seit"]]}
    erster = repo.plan_uebernehmen(kurs, zwei, profil.id, {f"dazu:{ids['seit']}"}, wahl=wahl)
    assert repo.fruehere_kursplaene(kurs.id, profil.id) == []

    repo.zuruecksetzen(kurs, profil.id)
    assert repo.kursplan(kurs, profil.id) is None
    (frueher,) = repo.fruehere_kursplaene(kurs.id, profil.id)
    assert frueher.id == erster.id and not frueher.aktiv
    assert frueher.name == "Rumpf · Durchlauf 1" and frueher.kurs_durchlauf_beendet is not None
    assert [i.exercise_id for i in frueher.items] == [knie, ids["planke"], ids["seit"]]
    # was damals gewählt war, sagt der Plan von damals
    assert wahl_im_plan(frueher, zwei.bloecke) == wahl
    # Speichern nimmt ihm weder Herkunft noch Marke des Durchlaufs
    frueher.description = "vom ersten Mal"
    plaene.speichern(frueher)
    assert plaene.laden(frueher.id).kurs_durchlauf_beendet is not None
    assert plaene.laden(frueher.id).kurs_id == kurs.id

    # Neuer Start: ein neuer Kursplan aus der Grundlage, mit dem Namen des Kursplans
    repo.starten(kurs, profil.id)
    zweiter = repo.kursplan(kurs, profil.id)
    assert zweiter is not None and zweiter.id != erster.id
    assert (zweiter.name, zweiter.aktiv) == ("Rumpf", True)
    assert [i.exercise_id for i in zweiter.items] == [knie]
    # … und alles wird neu gefragt
    assert [z.stand for z in repo.plan_aenderungen(kurs, eins, profil.id)] == [NEU, NEU]
    assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id)} == {OFFEN}

    # Noch einmal von vorn, der zweite Plan liegt dabei im Papierkorb: Die Nummer zählt weiter
    plaene.loeschen(zweiter.id)
    repo.zuruecksetzen(kurs, profil.id)
    plaene.aus_papierkorb(zweiter.id)
    assert repo.kursplan(kurs, profil.id) is None  # er gilt nicht wieder als der laufende
    namen = [p.name for p in repo.fruehere_kursplaene(kurs.id, profil.id)]
    assert sorted(namen) == ["Rumpf · Durchlauf 1", "Rumpf · Durchlauf 2"]


def test_kursplan_und_kapitelplaene_nebeneinander(con, profil) -> None:
    """Hat ein Kapitel eines Kurses mit Kursplan trotzdem Plan-Vorlagen, gelten sie wie bisher
    — als Kapitelpläne neben dem Kursplan. „Von vorn“ zählt beide in denselben Durchlauf."""
    repo, plaene = KursRepo(con), PlanRepo(con)
    kurs, _ids = rumpf_kurs(con)
    kurs.kapitel[0].plaene = [PlanVorlage("Kapitelplan", items=[VorlageItem(seed_id("kniebeuge"))])]
    kurs.kapitel[1].plaene = [PlanVorlage("Mit Wahl", items=[VorlageItem(seed_id("kniebeuge"))])]
    repo.speichern(kurs)
    eins, zwei, _drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    (kapitelplan,) = repo.kapitel_plaene(eins.id, profil.id)
    assert kapitelplan.kurs_id is None and kapitelplan.kurs_kapitel_id == eins.id
    kursplan = repo.plan_uebernehmen(kurs, eins, profil.id, {"a"})
    assert kursplan.id != kapitelplan.id
    repo.kapitel_abschliessen(kurs, eins, profil.id)
    assert not plaene.laden(kapitelplan.id).aktiv  # der Kapitelplan wie bisher
    assert plaene.laden(kursplan.id).aktiv  # der Kursplan bleibt
    (mit_wahl,) = repo.plaene_anlegen(zwei, profil.id, {"test": 12}, {"wahl": []})
    repo.zuruecksetzen(kurs, profil.id)
    assert plaene.laden(kursplan.id).name == "Rumpf · Durchlauf 1"
    assert plaene.laden(mit_wahl.id).name == "Mit Wahl · Durchlauf 1"
    assert plaene.laden(kapitelplan.id).name == "Kapitelplan"  # ohne Test/Auswahl: nur deaktiviert


def test_kurs_entfernen_deaktiviert_den_kursplan(con, profil) -> None:
    repo, plaene = KursRepo(con), PlanRepo(con)
    kurs, _ids = rumpf_kurs(con)
    repo.starten(kurs, profil.id)
    plan = repo.plan_uebernehmen(kurs, kurs.kapitel[0], profil.id, {"a"})
    zweites = Subject(name="Zweites")
    SubjectRepo(con).speichern(zweites)
    anderer = repo.kursplan_anlegen(kurs, zweites.id)
    assert repo.entfernen(kurs) == 2
    assert not plaene.laden(plan.id).aktiv and not plaene.laden(anderer.id).aktiv
    assert plaene.laden(plan.id).deleted_at is None  # bleibt in der Planliste
    assert repo.laden(kurs.id) is None


def test_stand_tage_zaehlt_die_uebungen_des_kursplans(con, profil) -> None:
    """„an 2 Tagen geübt — zählt, sobald der Plan steht“: nur, was im Kursplan steht, nicht
    alles, was die Auswahl anbietet."""
    repo, sitzungen, uebungen = KursRepo(con), SessionRepo(con), ExerciseRepo(con)
    kurs, ids = rumpf_kurs(con)
    eins, zwei, _drei = kurs.kapitel
    repo.starten(kurs, profil.id)
    repo.kapitel_abschliessen(kurs, eins, profil.id)  # ohne Übernehmen: noch kein Kursplan
    staende = repo.staende(profil.id, kurs.id)
    heute = datetime.now(UTC).astimezone().date()
    session = sitzungen.session_fuer(profil.id, None, heute)
    seit, planke = uebungen.laden(ids["seit"]), uebungen.laden(ids["planke"])
    sitzungen.eintrag_anlegen(session, seit, {"reps": [5]})
    assert repo.stand(zwei, profil.id, staende) == Stand(0.0, 2.0)  # der Plan steht noch nicht
    repo.plan_uebernehmen(kurs, eins, profil.id, {"a"})
    # Seitstütz steht nur zur Wahl, nicht im Plan — zählt nicht
    assert repo.stand(zwei, profil.id, staende, kurs) == Stand(0.0, 2.0)
    sitzungen.eintrag_anlegen(session, planke, {"reps": [5]})
    assert repo.stand(zwei, profil.id, staende) == Stand(1.0, 2.0)
    assert repo.stand(zwei, profil.id, staende, kurs) == Stand(1.0, 2.0)


def test_kursplan_aus_einem_plan_des_pakets(con, profil) -> None:
    """Grundlage = ein Plan des Pakets (über seinen Schlüssel): Der Kursplan ist eine Kopie —
    der Paketplan des Profils bleibt, wie er ist."""
    roh = paket_mit_kurs()
    roh["plaene"] = [
        {"key": "basis", "name": "Basis", "wochentage": [1], "uebungen": [{"uebung": "baum"}]}
    ]
    roh["kurse"][0]["kursplan"] = {"name": "Mein Stehen", "grundlage": "basis"}
    roh["kurse"][0]["kapitel"][1].pop("plaene")
    inhalt = paket_lesen(roh)
    assert inhalt.kurse[0].kursplan == Kursplan("Mein Stehen", grundlage="basis")
    pakete, repo, plaene = PaketRepo(con), KursRepo(con), PlanRepo(con)
    pakete.importieren(inhalt, subject_id=profil.id)
    (kurs,) = pakete.kurse(inhalt.paket.id)
    (paketplan,) = plaene.des_pakets(inhalt.paket.id, profil.id)
    repo.starten(kurs, profil.id)
    plan = repo.kursplan(kurs, profil.id)
    assert plan is not None and plan.id != paketplan.id
    assert (plan.name, plan.package_key, plan.kurs_id) == ("Mein Stehen", None, kurs.id)
    assert [(i.exercise_id, i.kurs_marke) for i in plan.items] == [(inhalt.uebungen[0].id, "g:1")]
    assert plaene.laden(paketplan.id).name == "Basis" and plaene.laden(paketplan.id).kurs_id is None
    # Ein Schlüssel, den das Paket nicht hat: Der Plan beginnt leer und entsteht erst später
    kurs.kursplan.grundlage = "gibt-es-nicht"
    repo.zuruecksetzen(kurs, profil.id)
    repo.starten(kurs, profil.id)
    assert repo.kursplan(kurs, profil.id) is None
    with pytest.raises(ValueError, match="baut keinen Plan"):
        repo.kursplan_anlegen(Kurs(name="Ohne", kapitel=[Kapitel(titel="A")]), profil.id)
    assert repo.plan_aenderungen(Kurs(name="Ohne"), Kapitel(), profil.id) == []


def test_test_misst_die_gewaehlte_uebung(con, profil) -> None:
    """Ben, 16.11.2026: Der Test gilt der Übung, die die Person gewählt hat (``aus``) — nicht
    einer, die der Kurs fest nennt. Jede Übung der Auswahl hat ihren eigenen Wert; das Ziel
    der Gewählten kommt aus ihrem."""
    repo, sitzungen, uebungen = KursRepo(con), SessionRepo(con), ExerciseRepo(con)
    kurs, ids = rumpf_kurs(con)
    test = next(b for b in kurs.kapitel[1].bloecke if b.art == TEST)
    test.uebung, test.aus = "", "wahl"
    repo.speichern(kurs)
    kurs = repo.laden(kurs.id)
    assert kurs is not None
    eins, zwei, _drei = kurs.kapitel
    assert [(b.aus, b.uebung) for b in zwei.bloecke if b.art == TEST] == [("wahl", "")]

    repo.starten(kurs, profil.id)
    alle = {z.id for z in repo.plan_aenderungen(kurs, eins, profil.id)}
    repo.plan_uebernehmen(kurs, eins, profil.id, alle)
    repo.kapitel_abschliessen(kurs, eins, profil.id)
    erreicht = repo.staende(profil.id, kurs.id)[zwei.id].erreicht

    kaefer, bruecke = uebungen.laden(ids["kaefer"]), uebungen.laden(ids["bruecke"])
    assert kaefer is not None and bruecke is not None
    session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
    sitzungen.eintrag_anlegen(session, kaefer, {"reps": [24, 30]})
    assert repo.testwerte(zwei, profil.id, erreicht) == {f"test:{ids['kaefer']}": 30.0}

    # Gewählt ist die Brücke — der Wert vom Käfer zählt für sie nicht
    wahl = {"wahl": [ids["bruecke"]]}
    marke = f"dazu:{ids['bruecke']}"
    zeilen = repo.plan_aenderungen(kurs, zwei, profil.id, wahl)
    assert [(z.id, z.stand) for z in zeilen][:2] == [(marke, NEU), (f"{marke}#ziel", OFFEN)]

    sitzungen.eintrag_anlegen(session, bruecke, {"reps": [12]})
    assert repo.testwerte(zwei, profil.id, erreicht) == {
        f"test:{ids['kaefer']}": 30.0,
        f"test:{ids['bruecke']}": 12.0,
    }
    zeilen = repo.plan_aenderungen(kurs, zwei, profil.id, wahl)
    assert [(z.titel, z.unter) for z in zeilen][:2] == [
        ("Brücke kommt dazu", "hinter Planke"),
        ("Ziel für Brücke: 12 Wiederholungen", "aus deinem Test"),
    ]
    plan = repo.plan_uebernehmen(kurs, zwei, profil.id, {z.id for z in zeilen}, wahl=wahl)
    assert [(i.exercise_id, i.target) for i in plan.items][1] == (ids["bruecke"], {"reps": [12]})


def test_test_der_gewaehlten_im_kapitelplan_und_auswahl_im_kapitel_davor(con, profil) -> None:
    """Auch ohne Kursplan: Die Gewählte bekommt im Kapitelplan das Ziel aus **ihrem** Test.
    Die Auswahl darf in einem früheren Kapitel stehen — die Testwerte finden sie."""
    repo, sitzungen, uebungen = KursRepo(con), SessionRepo(con), ExerciseRepo(con)
    planke, kaefer, bruecke = proben(con, "Planke", "Käfer", "Brücke")
    kurs = Kurs(
        name="Kapitelpläne",
        kapitel=[
            Kapitel(
                titel="Wählen und testen",
                plaene=[PlanVorlage("Rumpf", [0], [VorlageItem(planke)])],
                bloecke=[
                    Block(AUSWAHL, id="w", uebungen=[kaefer, bruecke], anzahl=1),
                    Block(TEST, id="t", aus="w", feld="reps", faktor=0.5),
                ],
            ),
            Kapitel(titel="Später", bloecke=[Block(TEST, id="t2", aus="w", feld="reps")]),
        ],
    )
    repo.speichern(kurs)
    kurs = repo.laden(kurs.id)
    assert kurs is not None
    eins, zwei = kurs.kapitel
    repo.starten(kurs, profil.id)
    erreicht = repo.staende(profil.id, kurs.id)[eins.id].erreicht
    session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
    for uid, wdh in ((kaefer, 40), (bruecke, 20)):
        uebung = uebungen.laden(uid)
        assert uebung is not None
        sitzungen.eintrag_anlegen(session, uebung, {"reps": [wdh]})
    werte = repo.testwerte(eins, profil.id, erreicht)
    assert werte == {f"t:{kaefer}": 40.0, f"t:{bruecke}": 20.0}
    (plan,) = repo.plaene_anlegen(eins, profil.id, werte, {"w": [bruecke]})
    assert [(i.exercise_id, (i.target or {}).get("reps")) for i in plan.items] == [
        (planke, None),
        (bruecke, [10]),  # die Hälfte ihres eigenen Werts, nicht des Käfers
    ]
    # Kapitel 2 kennt die Auswahl aus Kapitel 1
    assert repo.testwerte(zwei, profil.id, erreicht) == {
        f"t2:{kaefer}": 40.0,
        f"t2:{bruecke}": 20.0,
    }


def test_testlauf_mit_vorgabe_wird_ein_gewoehnlicher_eintrag(con, profil) -> None:
    """Ben, 16.11.2026 (Stufe 2): Ein Test mit Vorgabe läuft mit der Uhr. Am Ende steht ein
    gewöhnlicher Eintrag bei der Übung — mit Wiederholungen, Zeit und Skala, auch wenn die
    Übung Zeit und Skala nicht anbietet. Der Kurs liest daraus wie bisher den Wert seines
    Feldes; was sonst gemessen wurde, steht dabei (`KursRepo.testeintraege`)."""
    from trainingsapp.core.kurstest import eintrag, lauf_aus, neben_text

    repo, sitzungen, uebungen = KursRepo(con), SessionRepo(con), ExerciseRepo(con)
    kurs, ids = rumpf_kurs(con)
    test = next(b for b in kurs.kapitel[1].bloecke if b.art == TEST)
    test.vorgabe = Vorgabe(SKALA, 7)
    dazu = next(b for b in kurs.kapitel[1].bloecke if b.id == "dazu")
    dazu.faktor = 0.8
    repo.speichern(kurs)
    kurs = repo.laden(kurs.id)
    assert kurs is not None
    eins, zwei, _drei = kurs.kapitel
    test = next(b for b in zwei.bloecke if b.art == TEST)
    assert test.vorgabe == Vorgabe(SKALA, 7)  # die Vorgabe überlebt Speichern und Laden

    repo.starten(kurs, profil.id)
    repo.plan_uebernehmen(
        kurs, eins, profil.id, {z.id for z in repo.plan_aenderungen(kurs, eins, profil.id)}
    )
    repo.kapitel_abschliessen(kurs, eins, profil.id)
    erreicht = repo.staende(profil.id, kurs.id)[zwei.id].erreicht
    assert repo.testeintraege(zwei, profil.id, erreicht) == {}

    kaefer = uebungen.laden(ids["kaefer"])
    assert kaefer is not None
    assert [f.key for f in kaefer.result_spec.fields] == ["reps"]  # weder Zeit noch Skala
    mit_feldern, werte = eintrag(test, kaefer, wdh=22, sekunden=72.4, skala=7)
    assert werte == {"reps": [22], "duration": 72, "scale": 7}
    session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
    geschrieben = sitzungen.eintrag_anlegen(session, mit_feldern, werte)

    assert repo.testwerte(zwei, profil.id, erreicht) == {"test": 22.0}
    (gelesen,) = repo.testeintraege(zwei, profil.id, erreicht).values()
    assert gelesen.id == geschrieben.id
    # der Eintrag bringt seine Felder mit — die Übung selbst bleibt, wie sie war
    assert [f.key for f in gelesen.spec_snapshot.fields] == ["reps", "duration", "scale"]
    nachher = uebungen.laden(ids["kaefer"])
    assert nachher is not None and [f.key for f in nachher.result_spec.fields] == ["reps"]
    lauf = lauf_aus(test, gelesen.result, gelesen.spec_snapshot)
    assert (lauf.wdh, lauf.sekunden, lauf.skala) == (22.0, 72.0, 7.0)
    assert neben_text(test, lauf) == "in 1:12 · Anstrengung 7"

    wahl = {"wahl": [ids["kaefer"]]}
    zeilen = repo.plan_aenderungen(kurs, zwei, profil.id, wahl)
    assert [(z.titel, z.unter) for z in zeilen][:2] == [
        ("Käfer kommt dazu", "hinter Planke"),
        ("Ziel für Käfer: 18 Wiederholungen", "80 % von deinem Test (22 Wdh. bis Anstrengung 7)"),
    ]
    plan = repo.plan_uebernehmen(kurs, zwei, profil.id, {z.id for z in zeilen}, wahl=wahl)
    assert [(i.exercise_id, i.target) for i in plan.items][1] == (ids["kaefer"], {"reps": [18]})
