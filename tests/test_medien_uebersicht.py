"""Die Übersicht im Reiter „Medien“ des Plans (`core/medien_uebersicht.py`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §3): unterteilt nach Herkunft, je Stück, wo es angeboten wird."""

from __future__ import annotations

from trainingsapp.core.ablauf import Ablauf, Kante
from trainingsapp.core.bedingung import ENDE, Inhalt
from trainingsapp.core.kursbloecke import FRAGE, MEDIUM, PLAN_WEG, TEXT, Block
from trainingsapp.core.kurse import Kapitel
from trainingsapp.core.medien_uebersicht import (
    ANIMATION,
    AUS_KURS,
    AUS_PLAN,
    AUS_UEBUNG,
    IM_WORKOUT,
    TEXTART,
    ZIEL_ABLAUF,
    ZIEL_KURS,
    ZIEL_PLANUEBUNG,
    ZIEL_UEBUNG,
    Dateiinfo,
    KursTeil,
    grenze_video,
    gross,
    uebersicht,
)
from trainingsapp.core.models import (
    BEGLEITUNG,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
)
from trainingsapp.core.videoinfo import Videoinfo
from trainingsapp.core.zaehlen import SensorWahl

TECHNIK = "https://x.org/technik"
TON = "https://x.org/zaehlen.mp3"
DATEI = "medien/" + "a" * 64 + ".mp4"
MERKBLATT = "medien/" + "b" * 64 + ".pdf"
STUFE = "https://x.org/stufe"


def _gruppen(ue) -> dict[str, list]:
    return {g.herkunft: list(g.zeilen) for g in ue.gruppen}


def _plan() -> tuple[Plan, dict[str, Exercise]]:
    kniebeuge = Exercise(
        id="knie",
        name="Kniebeuge",
        description="## Ausführung\nTief\n## Atmung\nAus beim Hochkommen",
        media=[
            Media(uri=TECHNIK, title="Technik", zeigen=True),
            Media(uri=TON, title="Zählen", kind=MediaKind.AUDIO, rolle=BEGLEITUNG),
            Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=DATEI, title="Film"),
            Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="Bewegung/b.gif"),
        ],
    )
    katze = Exercise(
        id="katze",
        name="Katze-Kuh",
        media=[Media(kind=MediaKind.PDF, source=MediaSource.PAKET, uri=MERKBLATT)],
    )
    plan = Plan(
        description="Dreimal die Woche",
        items=[
            PlanItem(id="i1", exercise_id="knie"),
            PlanItem(
                id="i2",
                exercise_id="katze",
                description="## Im Plan\nlangsam\n## Für dich\nmit Pause",
            ),
            # dieselbe Übung ein zweites Mal — hier ersetzt ein Stück der Planübung die Technik
            PlanItem(
                id="i3",
                exercise_id="knie",
                media=[Media(uri=STUFE, title="An der Stufe", ersetzt=TECHNIK)],
            ),
        ],
    )
    return plan, {"knie": kniebeuge, "katze": katze}


def test_gruppen_nach_herkunft_mit_wo() -> None:
    plan, uebungen = _plan()
    ue = uebersicht(plan, uebungen, gesehen={MERKBLATT})
    gruppen = _gruppen(ue)
    assert [g.herkunft for g in ue.gruppen] == [AUS_UEBUNG, AUS_PLAN]
    uebung = [(z.titel, z.wo) for z in gruppen[AUS_UEBUNG]]
    assert uebung == [
        ("Beschreibung · Kniebeuge", "im „i“ bei 1 und 3 · Kniebeuge"),
        # die Technik gilt bei 1, bei 3 ersetzt sie das Stück der Planübung
        ("Technik", "bei 1 · Kniebeuge — bei 3 ersetzt"),
        ("Zählen", "bei 1 und 3 · Kniebeuge"),
        ("Film", "bei 1 und 3 · Kniebeuge"),
        ("Bild der Bewegung · Kniebeuge", "im Fokus bei 1 und 3 · Kniebeuge"),
        ("PDF-Datei", "bei 2 · Katze-Kuh"),
    ]
    unter = {z.titel: z.unter for z in gruppen[AUS_UEBUNG]}
    assert unter["Beschreibung · Kniebeuge"] == "Text · 2 Abschnitte"
    assert unter["Technik"] == "Link · Erklärung · zeigt sich beim ersten Mal"
    assert unter["Zählen"] == "Link · Begleitung"
    assert unter["PDF-Datei"] == "PDF-Datei · Erklärung · gesehen"
    assert unter["Bild der Bewegung · Kniebeuge"] == "Animation · nur auf diesem Gerät"
    arten = {z.titel: z.art for z in gruppen[AUS_UEBUNG]}
    assert arten["Beschreibung · Kniebeuge"] == TEXTART
    assert arten["Bild der Bewegung · Kniebeuge"] == ANIMATION
    assert all(z.ziel.art == ZIEL_UEBUNG for z in gruppen[AUS_UEBUNG])
    plan_zeilen = [(z.titel, z.unter, z.wo, z.ziel.art) for z in gruppen[AUS_PLAN]]
    assert plan_zeilen == [
        ("Beschreibung des Plans", "Text", "am Plan · vor dem Start", "plan"),
        ("Im Plan · Für dich", "Text · 2 Abschnitte", "bei 2 · Katze-Kuh", ZIEL_PLANUEBUNG),
        (
            "An der Stufe",
            "ersetzt „Technik“ · Link · Erklärung",
            "bei 3 · Kniebeuge",
            ZIEL_PLANUEBUNG,
        ),
    ]
    assert gruppen[AUS_PLAN][2].ziel.id == "i3"


def test_ueberall_ersetzt_steht_blass_und_zaehlt_nicht() -> None:
    plan, uebungen = _plan()
    plan.items = [plan.items[2]]  # nur die Kniebeuge mit dem Ersatz
    ue = uebersicht(plan, uebungen)
    technik = next(z for z in ue.zeilen if z.titel == "Technik")
    assert technik.ersetzt and technik.wo == "bei 1 · Kniebeuge ersetzt — siehe „Aus diesem Plan“"
    assert ue.stuecke == len(ue.zeilen) - 1


def test_dateien_groesse_und_gross() -> None:
    plan, uebungen = _plan()
    infos = {
        DATEI: Dateiinfo(
            bytes=84_000_000, video=Videoinfo(dauer_s=130, breite=1920, hoehe=1080, bildrate=30)
        ),
        MERKBLATT: Dateiinfo(bytes=12_000_000),
        STUFE: Dateiinfo(bytes=9_000_000, video=Videoinfo(dauer_s=60), geladen=True),
    }
    ue = uebersicht(plan, uebungen, datei=lambda m: infos.get(m.uri))
    film = next(z for z in ue.zeilen if z.titel == "Film")
    assert film.gross and film.paketdatei
    assert film.unter == "Video-Datei · Erklärung · 1080p · 30 fps · 2:10"
    stufe = next(z for z in ue.zeilen if z.titel == "An der Stufe")
    # ein geladenes Video hinter einem Link: auf dem Gerät, aber keine Datei des Pakets
    assert "auf dem Gerät" in stufe.unter and not stufe.paketdatei
    assert ue.dateien() == {DATEI: 84_000_000, MERKBLATT: 12_000_000}
    assert ue.kopf() == f"{ue.stuecke} Stücke · 2 Dateien · 96 MB"


def test_grenze_fuer_gross() -> None:
    # „Mittel“ (0,8 Mbit/s + 64 kbit/s) mit einem Viertel Spielraum: rund 8,1 MB je Minute
    assert grenze_video(60) == 8_100_000
    minute = Videoinfo(dauer_s=60)
    assert not gross("video", Dateiinfo(bytes=8_000_000, video=minute))
    assert gross("video", Dateiinfo(bytes=8_200_000, video=minute))
    assert not gross("bild", Dateiinfo(bytes=300_000, bild=(1080, 900)))
    assert gross("bild", Dateiinfo(bytes=300_000, bild=(1280, 960)))
    assert not gross("pdf", Dateiinfo(bytes=50_000_000))


def test_wege_im_workout_nur_mit_inhalt_und_nur_mit_ablauf() -> None:
    plan, uebungen = _plan()
    kanten = (
        Kante("i1", "i2"),
        Kante("i1", "i3", text="Rücken tut weh", inhalt=Inhalt("Erst lockern", STUFE)),
        Kante("i2", ENDE, inhalt=Inhalt("Gut gemacht", "")),
    )
    plan.ablauf = Ablauf(an=True, start="i1", kanten=kanten)
    ue = uebersicht(plan, uebungen)
    wege = _gruppen(ue)[IM_WORKOUT]
    assert [(z.titel, z.unter, z.wo, z.art) for z in wege] == [
        ("Rücken tut weh", "Text · Link", "am Weg von 1 · Kniebeuge zu 3 · Kniebeuge", "link"),
        ("Gut gemacht", "Text", "am Weg von 2 · Katze-Kuh zum Ende", TEXTART),
    ]
    assert wege[0].text == "Erst lockern" and wege[0].ziel.art == ZIEL_ABLAUF
    plan.ablauf = Ablauf(an=False, kanten=kanten)
    assert IM_WORKOUT not in _gruppen(uebersicht(plan, uebungen))


def test_kurs_nur_was_ihm_gegeben_wird_und_wege_mit_seinem_inhalt() -> None:
    """Die Oberfläche gibt nur erreichte Kapitel (`views/plan_medien.kurs_teile`); ein Weg mit
    genau dem Inhalt eines Weg-Bausteins gehört zum Kurs, ein geänderter zum Workout."""
    u = Exercise(id="u", name="Planke")
    v = Exercise(id="v", name="Brücke")
    plan = Plan(
        items=[
            PlanItem(id="p1", exercise_id="u", kurs_marke="b1"),
            PlanItem(id="p2", exercise_id="v", kurs_marke="b2:v"),
        ],
        ablauf=Ablauf(
            an=True,
            start="p1",
            kanten=(
                Kante("p1", "p2", inhalt=Inhalt("Atme ruhig", "")),
                Kante("p2", ENDE, inhalt=Inhalt("Selbst geschrieben", "")),
            ),
        ),
    )
    kapitel = Kapitel(
        id="k2",
        titel="Hüfte",
        bloecke=[
            Block(TEXT, id="t", titel="Warum die Hüfte", text="Weil **sie** trägt"),
            Block(MEDIUM, id="m", medium=Media(uri="https://x.org/kurs", title="Einführung")),
            Block(FRAGE, id="f", titel="Wie geht es dir?"),
            Block(PLAN_WEG, id="w", von="b1", zu="b2", kante={"inhalt": {"text": "Atme ruhig"}}),
        ],
    )
    alt = Kapitel(id="k1", titel="", text="Willkommen", media=[Media(uri="https://x.org/hallo")])
    teile = [KursTeil("kurs", "Rücken stark", kapitel, 2), KursTeil("kurs", "Rücken stark", alt, 1)]
    ue = uebersicht(plan, {"u": u, "v": v}, kurs=teile)
    gruppen = _gruppen(ue)
    kurs = gruppen[AUS_KURS]
    assert [(z.titel, z.wo) for z in kurs] == [
        ("Text", "im Kapitel 1"),
        ("https://x.org/hallo", "im Kapitel 1"),
        ("Warum die Hüfte", "im Kapitel 2 · Hüfte"),
        ("Einführung", "im Kapitel 2 · Hüfte"),
        ("Atme ruhig", "am Weg von 1 · Planke zu 2 · Brücke · aus Kapitel 2"),
    ]
    assert kurs[2].markdown and all(z.ziel.art == ZIEL_KURS for z in kurs)
    assert (kurs[4].ziel.id, kurs[4].ziel.kapitel) == ("kurs", "k2")
    assert next(g for g in ue.gruppen if g.herkunft == AUS_KURS).titel == (
        "AUS DEM KURS „Rücken stark“"
    )
    assert [z.titel for z in gruppen[IM_WORKOUT]] == ["Selbst geschrieben"]
    # Ohne erreichte Kapitel gehört auch der Weg zum Workout
    ohne = _gruppen(uebersicht(plan, {"u": u, "v": v}))
    assert AUS_KURS not in ohne and len(ohne[IM_WORKOUT]) == 2


def test_mitgelieferte_animation_und_leerer_plan() -> None:
    u = Exercise(id="u", name="Kniebeuge", beschleunigung=SensorWahl(vorlage="kniebeuge"))
    ue = uebersicht(Plan(items=[PlanItem(id="a", exercise_id="u")]), {"u": u})
    (zeile,) = ue.zeilen
    assert (zeile.titel, zeile.unter, zeile.wo) == (
        "Bild der Bewegung · Kniebeuge",
        "Animation · in der App",
        "im Fokus bei 1 · Kniebeuge",
    )
    leer = uebersicht(Plan(items=[PlanItem(id="b", exercise_id="x")]), {"x": Exercise(id="x")})
    assert leer.gruppen == () and leer.kopf() == "Noch keine Medien"


def test_medien_des_plans_selbst() -> None:
    """Stufe 2: Stücke des Plans stehen unter „Aus diesem Plan“, angeboten „am Plan · vor dem
    Start“; der Stift ändert sie hier (Ziel „plan“ mit ihrer Adresse)."""
    plan, uebungen = _plan()
    plan.media = [
        Media(uri="https://x.org/einstimmung", title="Einstimmung", zeigen=True),
        Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="Bewegung/x.gif"),
    ]
    zeilen = _gruppen(uebersicht(plan, uebungen))[AUS_PLAN]
    assert [(z.titel, z.wo, z.ziel.art, z.ziel.id) for z in zeilen[:2]] == [
        ("Beschreibung des Plans", "am Plan · vor dem Start", "plan", ""),
        ("Einstimmung", "am Plan · vor dem Start", "plan", "https://x.org/einstimmung"),
    ]
    assert zeilen[1].unter == "Link · Erklärung · zeigt sich beim ersten Mal"
