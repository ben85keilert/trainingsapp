"""Der Kursplan im Paket: Formatversion 6, Rundreise, die Prüfung im Werkzeug
(`trainingsapp-paket pruefen`) und Bens Beispiel aus `docs/uebungspakete.md` durch die
Datenbank (`docs/plan_kurs_ablauf.md` §11.6, Schritt 4).

Die Rechnung selbst prüft `tests/test_kursplan.py`, die Datenbank `tests/test_kurse.py`.
"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from trainingsapp.core import pakete
from trainingsapp.core.kursbloecke import MENGE, PLAN_UEBUNG, Block, Vorgabe
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import NEU, OFFEN, UEBERNOMMEN
from trainingsapp.core.models import Exercise, Subject
from trainingsapp.core.pakete import (
    FORMAT_VERSION,
    Paket,
    PaketFehler,
    PaketPlan,
    kurs_stand,
    noetige_version,
    nutzt_kursplan,
    paket_bauen,
    paket_lesen,
    uebung_id,
)
from trainingsapp.data.db import oeffnen
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import ExerciseRepo, SessionRepo, SubjectRepo
from trainingsapp.data.seed import seed_inhalt
from trainingsapp.paket_werkzeug import bauen, index, kursplan_pruefen, main, pruefen

DOKU = Path(__file__).resolve().parents[1] / "docs" / "uebungspakete.md"
VERSION_6 = "Formatversion 6 (Kursplan)"


def beispiel_text() -> str:
    """Das TOML-Beispiel aus `docs/uebungspakete.md`, Abschnitt „Kursplan und Bausteine“ —
    so, wie es dort steht."""
    bloecke = re.findall(r"```toml\n(.*?)```", DOKU.read_text(encoding="utf-8"), flags=re.S)
    (treffer,) = [b for b in bloecke if "[kurse.kursplan]" in b]
    return treffer


def beispiel() -> dict[str, Any]:
    return tomllib.loads(beispiel_text())


def kapitel(roh: dict[str, Any], nr: int) -> dict[str, Any]:
    return roh["kurse"][0]["kapitel"][nr - 1]


def block(roh: dict[str, Any], block_id: str) -> dict[str, Any]:
    (treffer,) = [
        b for kap in roh["kurse"][0]["kapitel"] for b in kap["bloecke"] if b.get("id") == block_id
    ]
    return treffer


def pruefe(tmp_path: Path, roh: dict[str, Any]) -> tuple[list[str], list[str]]:
    """`pruefen` über die Datei, wie das Werkzeug es tut — ohne den Hinweis zur Formatversion,
    den jedes Paket mit Kursplan bekommt."""
    datei = tmp_path / "paket.json"
    datei.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    return fehler, [h for h in hinweise if not h.startswith(VERSION_6)]


# ---------------------------------------------------------------------------
# Das Beispiel der Doku
# ---------------------------------------------------------------------------


def test_beispiel_der_doku_besteht_die_pruefung(tmp_path, capsys) -> None:
    datei = tmp_path / "rumpf.toml"
    datei.write_text(beispiel_text(), encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == []
    assert len(hinweise) == 1 and hinweise[0].startswith(VERSION_6)
    assert main(["pruefen", str(datei)]) == 0  # mit flet auch die Symbole
    assert f"{datei}: in Ordnung" in capsys.readouterr().out


def test_beispiel_bauen_lesen_gleich(tmp_path) -> None:
    """Rundreise: TOML → `bauen` (JSON, Version 6) → lesen → derselbe Kurs; noch einmal
    geschrieben und gelesen bleibt er derselbe."""
    datei = tmp_path / "rumpf.toml"
    datei.write_text(beispiel_text(), encoding="utf-8")
    quelle = seed_inhalt(datei)
    pfad = bauen(datei, tmp_path / "dist")
    roh = json.loads(pfad.read_text("utf-8"))
    assert roh["version"] == 6 <= FORMAT_VERSION
    gebaut = paket_lesen(pfad.read_bytes())
    (kurs,) = gebaut.kurse
    assert kurs.kursplan == Kursplan("Rumpf", [0, 2, 4])
    assert kurs_stand(kurs) == kurs_stand(quelle.kurse[0])
    # der Test läuft mit der Uhr: seine Vorgabe reist mit
    assert kurs.kapitel[1].bloecke[1].to_dict() == {
        "art": "test",
        "id": "test",
        "titel": "Wie viele schaffst du am Stück?",
        "aus": "wahl",
        "feld": "reps",
        "vorgabe": {"art": "skala", "n": 7},
    }
    assert [b.to_dict() for b in kurs.kapitel[1].bloecke[2:]] == [
        {
            "art": "plan_uebung",
            "id": "dazu",
            "aus": "wahl",
            "hinter": "start",
            "ziel_aus": "test",
            "faktor": 0.8,
        },
        {
            "art": "plan_weg",
            "id": "weiter",
            "von": "start",
            "zu": "dazu",
            "kante": {"ausloeser": "zeit", "pflicht": True},
        },
    ]
    wieder = paket_lesen(paket_bauen(gebaut.paket, gebaut.uebungen, kurse=gebaut.kurse))
    assert [kurs_stand(k) for k in wieder.kurse] == [kurs_stand(k) for k in gebaut.kurse]
    # der Index nennt die Formatversion der Datei
    (eintrag,) = index([pfad])["pakete"]
    assert eintrag["format_version"] == 6 and eintrag["kurse"] == 1


def test_rundreise_mit_vorlage_und_mit_grundlage() -> None:
    """Die beiden anderen Arten der Grundlage: eine Vorlage im Kurs (mit Ziel und Takt je
    Planübung) und ein Plan des Pakets über seinen Schlüssel."""
    planke, kaefer = Exercise(name="Planke"), Exercise(name="Käfer")
    vorlage = PlanVorlage(
        "Basis", [1, 3], [VorlageItem(planke.id, {"hold": [45]}), VorlageItem(kaefer.id)]
    )
    stein = Block(PLAN_UEBUNG, id="dazu", uebung=kaefer.id, hinter="g:1", ziel={"reps": [12]})
    kurs = Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf", [0, 2], vorlage=vorlage),
        kapitel=[Kapitel(titel="Anfang", bloecke=[stein])],
    )
    paket = Paket(id="p1", name="Rumpf")
    roh = paket_bauen(paket, [planke, kaefer], kurse=[kurs])
    assert roh["version"] == 6
    (gelesen,) = paket_lesen(roh).kurse
    assert gelesen.kursplan == kurs.kursplan and gelesen.kapitel[0].bloecke == [stein]

    kurs.kursplan = Kursplan("Rumpf", grundlage="basis")
    plan = PaketPlan("basis", vorlage)
    roh = paket_bauen(paket, [planke, kaefer], kurse=[kurs], plaene=[plan])
    assert roh["version"] == 6 and roh["kurse"][0]["kursplan"]["grundlage"] == "basis"
    inhalt = paket_lesen(roh)
    assert inhalt.kurse[0].kursplan == kurs.kursplan
    assert [i.exercise_id for i in inhalt.plaene[0].vorlage.items] == [planke.id, kaefer.id]


def test_marke_einer_gewaehlten_nennt_die_uebung_ueber_ihren_schluessel() -> None:
    """``<block>:<übung>``: Im Paket steht der Schlüssel der Übung, in der App ihre ID — mit
    ihr trägt die Planübung die Marke (`core.kursplan`)."""
    roh = beispiel()
    kapitel(roh, 2)["bloecke"].append(
        {"art": "plan_einstellen", "id": "mehr", "an": "dazu:kaefer", "ziel": {"reps": [20]}}
    )
    inhalt = paket_lesen(roh)
    kaefer = uebung_id(inhalt.paket.id, "kaefer")
    mehr = inhalt.kurse[0].kapitel[1].bloecke[-1]
    assert mehr.an == f"dazu:{kaefer}"
    # geschrieben wird die ID — sie bleibt beim nächsten Lesen, wie sie ist
    wieder = paket_lesen(paket_bauen(inhalt.paket, inhalt.uebungen, kurse=inhalt.kurse))
    assert wieder.kurse[0].kapitel[1].bloecke[-1].an == f"dazu:{kaefer}"


# ---------------------------------------------------------------------------
# Formatversion
# ---------------------------------------------------------------------------


def test_version_6_nur_mit_kursplan_oder_baustein() -> None:
    u = Exercise(name="Planke")
    paket = Paket(id="p1", name="Rumpf")
    ohne = Kurs(name="Lesen", kapitel=[Kapitel(titel="A", bloecke=[Block("text", text="x")])])
    assert not nutzt_kursplan(ohne)
    assert paket_bauen(paket, [u])["version"] == 1
    assert paket_bauen(paket, [u], kurse=[ohne])["version"] == 2
    plan = PaketPlan("basis", PlanVorlage("Basis", items=[VorlageItem(u.id)]))
    assert paket_bauen(paket, [u], kurse=[ohne], plaene=[plan])["version"] == 3
    # ein Kursplan — auch der leere — oder ein einzelner Baustein: Version 6
    mit_plan = Kurs(name="Baut", kursplan=Kursplan(), kapitel=[Kapitel(titel="A")])
    stein = Block(PLAN_UEBUNG, id="a", uebung=u.id)
    mit_stein = Kurs(name="Stein", kapitel=[Kapitel(titel="A", bloecke=[stein])])
    assert nutzt_kursplan(mit_plan) and nutzt_kursplan(mit_stein)
    assert paket_bauen(paket, [u], kurse=[ohne, mit_plan])["version"] == 6
    assert paket_bauen(paket, [u], kurse=[mit_stein], plaene=[plan])["version"] == 6
    assert noetige_version([u], [ohne, mit_plan], [plan]) == 6 <= FORMAT_VERSION


def test_version_6_auch_fuer_einen_test_der_die_gewaehlte_misst() -> None:
    """Ein Test mit ``aus`` braucht Version 6, auch ohne Kursplan — eine ältere App ließe den
    Block fallen (`Block.from_dict` kannte nur ``uebung``)."""
    bloecke = [
        Block("auswahl", id="w", uebungen=["u1", "u2"]),
        Block("test", id="t", aus="w", feld="reps"),
    ]
    kurs = Kurs(name="K", kapitel=[Kapitel(titel="A", bloecke=bloecke)])
    assert nutzt_kursplan(kurs) and noetige_version(kurse=[kurs]) == 6
    fest = Kurs(
        name="K", kapitel=[Kapitel(titel="A", bloecke=[Block("test", id="t", uebung="u1")])]
    )
    assert not nutzt_kursplan(fest) and noetige_version(kurse=[fest]) == 2


def test_version_6_auch_fuer_einen_test_mit_vorgabe() -> None:
    """Ein Test mit ``vorgabe`` braucht Version 6: Eine ältere App überläse sie und nähme als
    Test irgendeinen Eintrag der Übung."""
    lauf = Block("test", id="t", uebung="u1", feld="reps", vorgabe=Vorgabe(MENGE, 30))
    kurs = Kurs(name="K", kapitel=[Kapitel(titel="A", bloecke=[lauf])])
    assert nutzt_kursplan(kurs) and noetige_version(kurse=[kurs]) == 6
    paket = Paket(id="p", name="P")
    (gelesen,) = paket_lesen(paket_bauen(paket, [], kurse=[kurs])).kurse
    assert gelesen.kapitel[0].bloecke[0].vorgabe == Vorgabe(MENGE, 30)


def _vorgabe_ohne_zahl(roh: dict[str, Any]) -> None:
    block(roh, "test")["vorgabe"] = {"art": "menge"}


def _vorgabe_unbekannt(roh: dict[str, Any]) -> None:
    block(roh, "test")["vorgabe"] = {"art": "tanz", "n": 3}


def _vorgabe_skala_ohne_grenze(roh: dict[str, Any]) -> None:
    block(roh, "test")["vorgabe"] = {"art": "skala", "bis": 10}


def _vorgabe_feld_das_kein_lauf_liefert(roh: dict[str, Any]) -> None:
    block(roh, "test")["feld"] = "weight"


@pytest.mark.parametrize(
    ("aendern", "teil"),
    [
        (_vorgabe_ohne_zahl, "`vorgabe`: `n` (Wiederholungen) fehlt oder ist 0"),
        (_vorgabe_unbekannt, "`vorgabe`: `art` „tanz“ ist unbekannt (bekannt: menge, zeit, skala)"),
        (_vorgabe_skala_ohne_grenze, "`vorgabe`: `n` (ab) und `bis` (höchstens) geben nichts vor"),
        (_vorgabe_feld_das_kein_lauf_liefert, "`feld` „weight“ liefert ein Testlauf nicht"),
    ],
    ids=["ohne_zahl", "unbekannt", "skala_ohne_grenze", "feld"],
)
def test_pruefen_meldet_eine_vorgabe_die_nichts_taugt(tmp_path, aendern, teil) -> None:
    roh = beispiel()
    aendern(roh)
    fehler, _ = pruefe(tmp_path, roh)
    ort = "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 2 „test“: "
    assert [f for f in fehler if "vorgabe" in f] and fehler[0].startswith(ort + teil)


def test_hinweis_vorgabe_menge_an_einer_uebung_ohne_wiederholungen(tmp_path) -> None:
    roh = beispiel()
    test = block(roh, "test")
    del test["aus"]
    test.update(uebung="planke", feld="hold", vorgabe={"art": "menge", "n": 5})
    block(roh, "dazu").pop("ziel_aus")
    block(roh, "dazu").pop("faktor")
    fehler, hinweise = pruefe(tmp_path, roh)
    assert fehler == []
    assert any("`vorgabe` Menge, aber „planke“ hat kein Wiederholungsfeld" in h for h in hinweise)


def test_aeltere_app_lehnt_version_6_ab(monkeypatch) -> None:
    """Eine App, die nur Formatversion 5 kennt (bis 0.3.94), liest das Paket nicht — statt
    den Kurs ohne seinen Plan zu zeigen. Dieselbe Schranke gilt hier für Version 7."""
    roh = paket_bauen(*_inhalt_des_beispiels())
    assert roh["version"] == 6
    assert paket_lesen(roh).kurse[0].kursplan is not None
    with pytest.raises(PaketFehler, match="neuer als diese App — bitte die App aktualisieren"):
        paket_lesen({**roh, "version": FORMAT_VERSION + 1})
    monkeypatch.setattr(pakete, "FORMAT_VERSION", 5)  # der Stand vor dem Kursplan
    with pytest.raises(PaketFehler, match="neuer als diese App — bitte die App aktualisieren"):
        paket_lesen(roh)
    with pytest.raises(PaketFehler, match="neuer als diese App"):
        paket_lesen(json.dumps(roh))
    # ohne den Kursplan-Kurs bleibt dasselbe Paket für sie lesbar
    ohne = {**roh, "version": 1, "kurse": []}
    assert len(paket_lesen(ohne).uebungen) == 4


def _inhalt_des_beispiels() -> tuple[Paket, list[Exercise], None, list[Kurs]]:
    inhalt = paket_lesen(beispiel())
    return inhalt.paket, inhalt.uebungen, None, inhalt.kurse


def test_versionen_1_bis_5_lesen_sich_wie_bisher() -> None:
    """Die Schranke ändert nichts an Älterem: Was als Version 1–5 geschrieben ist, liest sich
    mit denselben Inhalten — auch ein Kurs mit gewöhnlichen Blöcken (Version 2)."""
    uebung = {"key": "planke", "name": "Planke"}
    kurs = {
        "key": "k",
        "name": "Lesen",
        "kapitel": [
            {
                "key": "a",
                "titel": "A",
                "bloecke": [
                    {"art": "text", "id": "t", "text": "Hallo"},
                    {"art": "auswahl", "id": "w", "uebungen": ["planke"]},
                ],
                "plaene": [{"name": "Stehen", "uebungen": [{"uebung": "planke"}]}],
            }
        ],
    }
    plan = {"key": "basis", "name": "Basis", "uebungen": [{"uebung": "planke"}]}
    erg = {"uebung": "kniebeuge", "description": "## Reha\nLangsam."}
    faelle: list[tuple[int, dict[str, Any]]] = [
        (1, {"exercises": [uebung]}),
        (2, {"exercises": [uebung], "kurse": [kurs]}),
        (3, {"exercises": [uebung], "kurse": [kurs], "plaene": [plan]}),
        (5, {"exercises": [uebung], "kurse": [kurs], "plaene": [plan], "ergaenzungen": [erg]}),
    ]
    for version, teile in faelle:
        inhalt = paket_lesen({"paket": {"name": "Q"}, "version": version, **teile})
        assert [k.kursplan for k in inhalt.kurse] == [None] * len(inhalt.kurse)
        roh = paket_bauen(
            inhalt.paket,
            inhalt.uebungen,
            kurse=inhalt.kurse or None,
            plaene=inhalt.plaene or None,
            ergaenzungen=inhalt.ergaenzungen or None,
        )
        assert roh["version"] == version, f"Version {version} bleibt Version {version}"
        assert "kursplan" not in json.dumps(roh)
        wieder = paket_lesen(roh)
        assert [kurs_stand(k) for k in wieder.kurse] == [kurs_stand(k) for k in inhalt.kurse]


# ---------------------------------------------------------------------------
# Die Prüfung im Werkzeug — je Regel ein Fall, immer vom Beispiel der Doku aus
# ---------------------------------------------------------------------------


def _ohne_id(roh: dict[str, Any]) -> None:
    del block(roh, "weiter")["id"]


def _id_mit_doppelpunkt(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["id"] = "weg:1"


def _id_wie_die_grundlage(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["id"] = "g"  # „g:1“ wäre von der Grundlage nicht zu unterscheiden


def _id_doppelt(roh: dict[str, Any]) -> None:
    kapitel(roh, 2)["bloecke"].append({"art": "text", "id": "warum", "text": "Noch einmal."})


def _marke_unbekannt(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["hinter"] = "planke"  # der Schlüssel der Übung ist keine Marke


def _marke_ist_kein_plan_uebung(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["zu"] = "wahl"


def _marke_im_spaeteren_kapitel(roh: dict[str, Any]) -> None:
    kapitel(roh, 1)["bloecke"].append(
        {"art": "plan_einstellen", "id": "frueh", "an": "dazu", "ziel": {"reps": [10]}}
    )


def _marke_weiter_unten(roh: dict[str, Any]) -> None:
    bloecke = kapitel(roh, 2)["bloecke"]
    bloecke.insert(2, bloecke.pop())  # der Weg vor dem Baustein, auf den er zeigt


def _von_ende(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["von"] = "ende"


def _weg_ohne_zu(roh: dict[str, Any]) -> None:
    del block(roh, "weiter")["zu"]


def _grundlage_marke_ohne_grundlage(roh: dict[str, Any]) -> None:
    block(roh, "start")["hinter"] = "g:1"


def _grundlage_marke_zu_gross(roh: dict[str, Any]) -> None:
    roh["plaene"] = [{"key": "basis", "name": "Basis", "uebungen": [{"uebung": "bruecke"}]}]
    roh["kurse"][0]["kursplan"]["grundlage"] = "basis"
    block(roh, "start")["hinter"] = "g:2"


def _aus_unbekannt(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["aus"] = "auswahl"


def _aus_ist_ein_test(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["aus"] = "test"


def _aus_im_spaeteren_kapitel(roh: dict[str, Any]) -> None:
    kapitel(roh, 1)["bloecke"].append({"art": "plan_uebung", "id": "frueh", "aus": "wahl"})


def _ziel_aus_unbekannt(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["ziel_aus"] = "pruefung"


def _ziel_aus_ist_eine_auswahl(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["ziel_aus"] = "wahl"


def _weder_uebung_noch_aus(roh: dict[str, Any]) -> None:
    del block(roh, "start")["uebung"]
    for b in kapitel(roh, 2)["bloecke"][2:]:  # was auf „start“ zeigte, zeigt jetzt ins Leere
        b.pop("hinter", None)
        if b["art"] == "plan_weg":
            kapitel(roh, 2)["bloecke"].remove(b)


def _uebung_und_aus(roh: dict[str, Any]) -> None:
    block(roh, "dazu")["uebung"] = "kaefer"


def _grundlage_ohne_plan(roh: dict[str, Any]) -> None:
    roh["plaene"] = [{"key": "basis", "name": "Basis", "uebungen": [{"uebung": "bruecke"}]}]
    roh["kurse"][0]["kursplan"]["grundlage"] = "Basis"  # der Schlüssel heißt „basis“


def _grundlage_und_vorlage(roh: dict[str, Any]) -> None:
    roh["plaene"] = [{"key": "basis", "name": "Basis", "uebungen": [{"uebung": "bruecke"}]}]
    roh["kurse"][0]["kursplan"]["grundlage"] = "basis"
    roh["kurse"][0]["kursplan"]["vorlage"] = {"uebungen": [{"uebung": "bruecke"}]}


def _kante_zahl(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["kante"] = {"ausloeser": "wdh", "n": "zwölf"}


def _baustein_unbekannt(roh: dict[str, Any]) -> None:
    kapitel(roh, 2)["bloecke"].append({"art": "plan_pause", "id": "pause"})


def _gewaehlte_nicht_zur_wahl(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["zu"] = "dazu:planke"


def _feste_uebung_mit_doppelpunkt(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["von"] = "start:planke"


def _test_aus_ohne_auswahl(roh: dict[str, Any]) -> None:
    block(roh, "test")["aus"] = "fehlt"


def _test_mit_uebung_und_aus(roh: dict[str, Any]) -> None:
    block(roh, "test")["uebung"] = "kaefer"


def _test_vor_seiner_auswahl(roh: dict[str, Any]) -> None:
    kapitel(roh, 1)["bloecke"].append({"art": "test", "id": "frueh", "aus": "wahl", "feld": "reps"})


FEHLER: list[tuple[Callable[[dict[str, Any]], None], str]] = [
    (
        _ohne_id,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4: Baustein ohne feste `id` — andere "
        "Bausteine zeigen auf sie, und sie steht als Marke im Plan (die App vergäbe bei jedem "
        "Lesen eine andere)",
    ),
    (
        _id_mit_doppelpunkt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weg:1“: Die `id` taugt nicht als "
        "Marke: nur Buchstaben, Ziffern, „-“ und „_“ (1–64 Zeichen), nicht „ende“ und nicht „g“",
    ),
    (
        _id_wie_die_grundlage,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „g“: Die `id` taugt nicht als "
        "Marke: nur Buchstaben, Ziffern, „-“ und „_“ (1–64 Zeichen), nicht „ende“ und nicht „g“",
    ),
    (
        _id_doppelt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 5 „warum“: Die `id` gibt es im Kurs "
        "schon (Kapitel „Anfang“, Block 1 „warum“) — Block-IDs sind je Kurs eindeutig",
    ),
    (
        _marke_unbekannt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `hinter` „planke“ nennt "
        "keine bekannte Marke (die `id` eines `plan_uebung` davor, `g:<n>`)",
    ),
    (
        _marke_ist_kein_plan_uebung,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: `zu` „wahl“ ist ein Block "
        "`auswahl`, kein `plan_uebung` — nur der bringt eine Planübung in den Plan",
    ),
    (
        _marke_im_spaeteren_kapitel,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 3 „frueh“: `an` „dazu“ steht erst in "
        "Kapitel 2 („Erweiterung“) — die Planübung gibt es hier noch nicht",
    ),
    (
        _marke_weiter_unten,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „weiter“: `zu` „dazu“ steht nicht "
        "vor diesem Baustein — Bausteine gelten in der Reihenfolge, in der sie dastehen",
    ),
    (
        _von_ende,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: `von` „ende“ nennt keine "
        "bekannte Marke (die `id` eines `plan_uebung` davor, `g:<n>`)",
    ),
    (
        _weg_ohne_zu,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: `zu` fehlt — ein Weg "
        "braucht `von` und `zu`, der Baustein fällt weg",
    ),
    (
        _grundlage_marke_ohne_grundlage,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 2 „start“: `hinter` „g:1“ gibt es nicht — "
        "der Kursplan beginnt leer (keine Grundlage)",
    ),
    (
        _grundlage_marke_zu_gross,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 2 „start“: `hinter` „g:2“ gibt es nicht — "
        "die Grundlage hat 1 Planübung (`g:1` bis `g:1`)",
    ),
    (
        _aus_unbekannt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `aus` „auswahl“ nennt keine "
        "Auswahl (ein Block `auswahl` mit dieser `id` in diesem oder einem früheren Kapitel)",
    ),
    (
        _aus_ist_ein_test,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `aus` „test“ nennt keine "
        "Auswahl, sondern einen Block `test`",
    ),
    (
        _aus_im_spaeteren_kapitel,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 3 „frueh“: `aus` „wahl“ steht erst in "
        "Kapitel 2 („Erweiterung“) — ein Baustein bezieht sich nur auf dieses oder ein früheres "
        "Kapitel",
    ),
    (
        _ziel_aus_unbekannt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `ziel_aus` „pruefung“ nennt "
        "keinen Test (ein Block `test` mit dieser `id` in diesem oder einem früheren Kapitel)",
    ),
    (
        _ziel_aus_ist_eine_auswahl,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `ziel_aus` „wahl“ nennt "
        "keinen Test, sondern einen Block `auswahl`",
    ),
    (
        _weder_uebung_noch_aus,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 2 „start“: weder `uebung` (eine feste "
        "Übung) noch `aus` (die `id` einer Auswahl) — der Baustein fällt weg",
    ),
    (
        _uebung_und_aus,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `uebung` und `aus` zugleich "
        "— nur eines davon (die App nähme `aus`)",
    ),
    (
        _grundlage_ohne_plan,
        "Kurs „Rumpf-Kurs“: kursplan: `grundlage` „Basis“ nennt keinen Plan des Pakets "
        "(bekannt: basis)",
    ),
    (
        _grundlage_und_vorlage,
        "Kurs „Rumpf-Kurs“: kursplan: `grundlage` und `vorlage` zugleich — nur eines davon "
        "(die App nähme die Vorlage)",
    ),
    (
        _kante_zahl,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: kante: n ist keine Zahl",
    ),
    (
        _baustein_unbekannt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 5 „pause“: unbekannter Baustein "
        "`plan_pause` (bekannt: plan_uebung, plan_einstellen, plan_weg, plan_entfernen, "
        "plan_tauschen) — der Block fällt weg",
    ),
    (
        _gewaehlte_nicht_zur_wahl,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: `zu` „dazu:planke“: "
        "„planke“ steht in der Auswahl „wahl“ nicht zur Wahl",
    ),
    (
        _feste_uebung_mit_doppelpunkt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: `von` „start:planke“: "
        "„start“ bringt eine feste Übung — ihre Marke heißt „start“",
    ),
    (
        _test_aus_ohne_auswahl,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 2 „test“: `aus` „fehlt“ nennt keine "
        "Auswahl (ein Block `auswahl` mit dieser `id` in diesem oder einem früheren Kapitel)",
    ),
    (
        _test_mit_uebung_und_aus,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 2 „test“: `uebung` und `aus` zugleich "
        "— nur eines davon (die App nähme `aus`)",
    ),
    (
        _test_vor_seiner_auswahl,
        "Kurs „Rumpf-Kurs“: Kapitel „Anfang“, Block 3 „frueh“: `aus` „wahl“ steht erst in "
        "Kapitel 2 („Erweiterung“) — ein Baustein bezieht sich nur auf dieses oder ein früheres "
        "Kapitel",
    ),
]


@pytest.mark.parametrize(("aendern", "erwartet"), FEHLER, ids=[a.__name__ for a, _ in FEHLER])
def test_pruefen_meldet_als_fehler(tmp_path, aendern, erwartet) -> None:
    roh = beispiel()
    aendern(roh)
    fehler, hinweise = pruefe(tmp_path, roh)
    assert fehler == [erwartet]
    assert hinweise == []


def _ohne_kursplan(roh: dict[str, Any]) -> None:
    del roh["kurse"][0]["kursplan"]


def _kapitelplaene_daneben(roh: dict[str, Any]) -> None:
    kapitel(roh, 2)["plaene"] = [{"name": "Dehnen", "uebungen": [{"uebung": "bruecke"}]}]


def _ausloeser_unbekannt(roh: dict[str, Any]) -> None:
    block(roh, "weiter")["kante"] = {"ausloeser": "tanz", "pflicht": True}


def _stellt_nichts_ein(roh: dict[str, Any]) -> None:
    kapitel(roh, 2)["bloecke"].append({"art": "plan_einstellen", "id": "leer", "an": "start"})


def _vorlage_ohne_uebung(roh: dict[str, Any]) -> None:
    roh["kurse"][0]["kursplan"]["vorlage"] = {"name": "Basis", "uebungen": []}


HINWEISE: list[tuple[Callable[[dict[str, Any]], None], str]] = [
    (
        _ohne_kursplan,
        "Kurs „Rumpf-Kurs“: 3 Bausteine (`plan_*`) in einem Kurs ohne `kursplan` — sie bewirken "
        "dort nichts",
    ),
    (
        _kapitelplaene_daneben,
        "Kurs „Rumpf-Kurs“: `kursplan` und `plaene` in Kapiteln („Erweiterung“) — beides gilt "
        "nebeneinander: Die Kapitelpläne entstehen wie bisher, der Kursplan wächst daneben",
    ),
    (
        _ausloeser_unbekannt,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4 „weiter“: kante: Auslöser „tanz“ "
        "unbekannt — „frei“ gilt",
    ),
    (
        _stellt_nichts_ein,
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 5 „leer“: stellt nichts ein — der "
        "Baustein fällt weg",
    ),
    (
        _vorlage_ohne_uebung,
        "Kurs „Rumpf-Kurs“: kursplan: `vorlage` ohne Übung — der Plan beginnt leer",
    ),
]


@pytest.mark.parametrize(("aendern", "erwartet"), HINWEISE, ids=[a.__name__ for a, _ in HINWEISE])
def test_pruefen_meldet_als_hinweis(tmp_path, aendern, erwartet) -> None:
    roh = beispiel()
    aendern(roh)
    fehler, hinweise = pruefe(tmp_path, roh)
    assert fehler == []
    assert hinweise == [erwartet]


def test_pruefen_nimmt_an_was_die_app_versteht(tmp_path) -> None:
    """Die Gegenprobe: Marken der Grundlage, eine der Gewählten über ihren Schlüssel, ``ende``,
    Test und Auswahl aus einem früheren Kapitel, ein Kurs ohne Kursplan und ohne Bausteine."""
    roh = beispiel()
    roh["plaene"] = [
        {
            "key": "basis",
            "name": "Basis",
            "uebungen": [{"uebung": "bruecke"}, {"uebung": "beinheben"}],
        }
    ]
    kurs = roh["kurse"][0]
    kurs["kursplan"]["grundlage"] = "basis"
    block(roh, "start")["hinter"] = "g:2"
    kurs["kapitel"].append(
        {
            "key": "steigern",
            "titel": "Steigern",
            "bloecke": [
                {"art": "plan_einstellen", "id": "mehr", "an": "dazu:kaefer", "ziel_aus": "test"},
                {"art": "plan_einstellen", "id": "plan", "uebergang": "hart"},
                {"art": "plan_uebung", "id": "noch", "aus": "wahl", "hinter": "g:1"},
                {"art": "plan_weg", "id": "schluss", "von": "dazu", "zu": "ende"},
                {"art": "plan_weg", "id": "schleife", "von": "start", "zu": "start"},
            ],
        }
    )
    roh["kurse"].append(
        {
            "key": "lesen",
            "name": "Lesen",
            "kapitel": [
                {
                    "key": "a",
                    "titel": "A",
                    "bloecke": [{"art": "text", "id": "warum", "text": "Eigene IDs je Kurs."}],
                }
            ],
        }
    )
    assert pruefe(tmp_path, roh) == ([], [])
    # ohne Kursplan und Bausteine weder Meldung noch Hinweis auf die Formatversion
    nur_lesen = {**roh, "kurse": [roh["kurse"][1]], "plaene": []}
    datei = tmp_path / "lesen.json"
    datei.write_text(json.dumps(nur_lesen, ensure_ascii=False), encoding="utf-8")
    assert pruefen(datei, symbole=None) == ([], [])


def test_pruefen_sammelt_mehrere_fehler_und_prueft_die_vorlage_wie_einen_plan(tmp_path) -> None:
    roh = beispiel()
    roh["kurse"][0]["kursplan"]["vorlage"] = {
        "uebungen": [{"uebung": "bruecke", "beschleunigung": {"atmung": "ja"}}]
    }
    block(roh, "dazu")["hinter"] = "g:3"
    del block(roh, "weiter")["id"]
    fehler, hinweise = pruefe(tmp_path, roh)
    assert fehler == [
        "Kurs „Rumpf-Kurs“, Kursplan, Vorlage, Übung „bruecke“: beschleunigung: „atmung“ muss "
        'true oder false sein, nicht "ja"',
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 3 „dazu“: `hinter` „g:3“ gibt es nicht "
        "— die Grundlage hat 1 Planübung (`g:1` bis `g:1`)",
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 4: Baustein ohne feste `id` — andere "
        "Bausteine zeigen auf sie, und sie steht als Marke im Plan (die App vergäbe bei jedem "
        "Lesen eine andere)",
    ]
    assert hinweise == []
    # dieselbe Prüfung ohne Datei
    assert kursplan_pruefen(roh, paket_lesen(roh))[0] == fehler[1:]


def test_wortliste_liest_den_namen_des_kursplans(tmp_path) -> None:
    roh = beispiel()
    roh["kurse"][0]["kursplan"]["name"] = "Dein optimaler Rumpf"
    datei = tmp_path / "paket.json"
    datei.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    _, hinweise = pruefen(datei, symbole=None, wortliste=["optimal"])
    assert "Wortliste: Kurs „Rumpf-Kurs“, Kursplan, Name: „optimal“" in hinweise


# ---------------------------------------------------------------------------
# Ende zu Ende: das Beispiel einspielen, den Kurs gehen, der Plan entsteht
# ---------------------------------------------------------------------------


def test_beispiel_einspielen_kurs_starten_plan_entsteht(tmp_path) -> None:
    datei = tmp_path / "rumpf.toml"
    datei.write_text(beispiel_text(), encoding="utf-8")
    inhalt = seed_inhalt(datei)
    con = oeffnen(tmp_path / "app.db")
    try:
        profil = Subject(name="Test")
        SubjectRepo(con).speichern(profil)
        PaketRepo(con).importieren(inhalt, subject_id=profil.id)
        (kurs,) = PaketRepo(con).kurse(inhalt.paket.id)
        assert kurs.kursplan == Kursplan("Rumpf", [0, 2, 4])
        planke, kaefer = (uebung_id(inhalt.paket.id, key) for key in ("planke", "kaefer"))
        repo = KursRepo(con)
        eins, zwei = kurs.kapitel

        # Kapitel 1: die Planke mit 60 Sekunden — der Plan entsteht erst mit „Übernehmen“
        repo.starten(kurs, profil.id)
        assert repo.kursplan(kurs, profil.id) is None
        zeilen = repo.plan_aenderungen(kurs, eins, profil.id)
        assert [(z.id, z.titel, z.unter, z.stand) for z in zeilen] == [
            ("start", "Planke kommt dazu", "ans Ende", NEU),
            ("start#ziel", "Ziel für Planke: 60 s", "aus dem Kurs", NEU),
        ]
        plan = repo.plan_uebernehmen(kurs, eins, profil.id, {z.id for z in zeilen})
        assert (plan.name, plan.wochentage, plan.kurs_id, plan.aktiv) == (
            "Rumpf",
            [0, 2, 4],
            kurs.id,
            True,
        )
        assert [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items] == [
            (planke, "start", {"hold": [60]})
        ]
        assert not plan.ablauf.an  # noch eine Liste

        # Kapitel 2: ohne Wahl offen; gewählt und getestet drei Zeilen
        repo.kapitel_abschliessen(kurs, eins, profil.id)
        assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id)} == {OFFEN}
        wahl = {"wahl": [kaefer]}
        sitzungen = SessionRepo(con)
        uebung = ExerciseRepo(con).laden(kaefer)
        assert uebung is not None
        session = sitzungen.session_fuer(profil.id, None, datetime.now(UTC).astimezone().date())
        sitzungen.eintrag_anlegen(session, uebung, {"reps": [24, 30]})
        zeilen = repo.plan_aenderungen(kurs, zwei, profil.id, wahl)
        marke = f"dazu:{kaefer}"
        assert [(z.id, z.titel, z.unter, z.stand) for z in zeilen] == [
            (marke, "Käfer kommt dazu", "hinter Planke", NEU),
            (
                f"{marke}#ziel",
                "Ziel für Käfer: 24 Wiederholungen",
                "80 % von deinem Test (30 Wdh. bis Anstrengung 7)",
                NEU,
            ),
            (
                "weiter#weg",
                "Von Planke weiter zu Käfer, wenn die Zeit ab ist",
                "Pflicht — Überspringen bleibt möglich",
                NEU,
            ),
        ]
        plan = repo.plan_uebernehmen(kurs, zwei, profil.id, {z.id for z in zeilen}, wahl=wahl)
        erste, gewaehlte = plan.items
        assert (erste.exercise_id, erste.kurs_marke) == (planke, "start")
        assert (gewaehlte.exercise_id, gewaehlte.kurs_marke, gewaehlte.target) == (
            kaefer,
            marke,
            {"reps": [24]},
        )
        assert plan.ablauf.an and plan.workout  # der Weg macht den Plan zum Workout
        (kante,) = plan.ablauf.kanten
        assert (kante.von, kante.nach, kante.ausloeser, kante.pflicht) == (
            erste.id,
            gewaehlte.id,
            "zeit",
            True,
        )
        assert {z.stand for z in repo.plan_aenderungen(kurs, zwei, profil.id)} == {UEBERNOMMEN}

        # Dieselbe Fassung noch einmal einspielen ändert weder Kurs noch Plan
        vorher = copy.deepcopy(plan)
        PaketRepo(con).importieren(seed_inhalt(datei), subject_id=profil.id)
        (wieder,) = PaketRepo(con).kurse(inhalt.paket.id)
        assert kurs_stand(wieder) == kurs_stand(kurs)
        assert repo.kursplan(wieder, profil.id) == vorher
    finally:
        con.close()


def _png() -> bytes:
    """Ein Bild von einem Punkt — ohne Ortsangaben, geht also unverändert ins Paket."""
    import struct
    import zlib

    def stueck(typ: bytes, daten: bytes) -> bytes:
        return (
            struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + stueck(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + stueck(b"IDAT", zlib.compress(b"\x00\x00"))
        + stueck(b"IEND", b"")
    )


VORLAGE_MIT_DATEI = """
[paket]
name = "Rumpf"
version = "0.1.0"

[[exercises]]
key = "bruecke"
name = "Brücke"
description = "Becken heben."

[[kurse]]
name = "Rumpf-Kurs"

[kurse.kursplan]
name = "Rumpf"

[[kurse.kursplan.vorlage.uebungen]]
uebung = "bruecke"
medien = [{ datei = "medien/bruecke.png", title = "So liegt das Becken" }]

[[kurse.kapitel]]
titel = "Start"
"""


def test_datei_in_der_vorlage_des_kursplans_kommt_ins_paket(tmp_path) -> None:
    """Die Planübungen der Vorlage dürfen Dateien mitbringen wie die eines Kapitelplans
    (`core.paketdatei.medienlisten`) — sie fiele sonst beim Bauen still weg."""
    from trainingsapp.core.paketdatei import paket_oeffnen

    (tmp_path / "medien").mkdir()
    (tmp_path / "medien" / "bruecke.png").write_bytes(_png())
    datei = tmp_path / "rumpf.toml"
    datei.write_text(VORLAGE_MIT_DATEI, encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == []
    assert any(h.startswith("1 Datei(en)") for h in hinweise)  # die Datei ist gesehen
    pfad = bauen(datei, tmp_path / "dist")
    assert pfad.suffix == ".zip"
    inhalt = paket_oeffnen(pfad)
    (name,) = inhalt.medien
    (kurs,) = inhalt.kurse
    assert kurs.kursplan is not None and kurs.kursplan.vorlage is not None
    (medium,) = kurs.kursplan.vorlage.items[0].medien
    assert (medium.uri, medium.title) == (name, "So liegt das Becken")


def test_datei_der_vorlage_eines_eigenen_kurses_bleibt_beim_aufraeumen(tmp_path) -> None:
    """Ein eigener Kurs hat keinen Paketstand — die Ablage findet die Datei seiner Vorlage
    in `course.kursplan_json` (sonst räumte `Paketablage.aufraeumen` sie weg)."""
    from trainingsapp.core.models import Media
    from trainingsapp.core.paketmedien import dateiname, name_fuer
    from trainingsapp.data.paketmedien import Paketablage

    name = name_fuer("ab" * 32, "png")
    vorlage = PlanVorlage(
        "Rumpf",
        items=[VorlageItem(exercise_id="u1", medien=[Media(source="paket", uri=name)])],
    )
    kurs = Kurs(
        name="Eigener", kapitel=[Kapitel(titel="Start")], kursplan=Kursplan(vorlage=vorlage)
    )
    con = oeffnen(tmp_path / "app.db")
    try:
        ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
        ablage.ordner.mkdir(parents=True)
        (ablage.ordner / str(dateiname(name))).write_bytes(_png())
        (ablage.ordner / "verwaist.png").write_bytes(_png())
        KursRepo(con).speichern(kurs)
        assert ablage.benutzte() == {name}
        assert ablage.aufraeumen() == 1
        assert [d.name for d in ablage.ordner.iterdir()] == [dateiname(name)]
    finally:
        con.close()


def test_test_der_gewaehlten_ohne_kursplan_nur_im_selben_kapitel(tmp_path) -> None:
    """Mit Kapitelplänen kennt ein Kapitel nur die Wahl aus seinen eigenen Blöcken — ein Test
    mit ``aus`` auf eine Auswahl eines früheren Kapitels bliebe dort ohne Wirkung."""
    roh = beispiel()
    del roh["kurse"][0]["kursplan"]
    for kap in roh["kurse"][0]["kapitel"]:  # ohne Kursplan auch keine Bausteine
        kap["bloecke"] = [b for b in kap["bloecke"] if not b["art"].startswith("plan_")]
    kapitel(roh, 1)["bloecke"].append(kapitel(roh, 2)["bloecke"].pop(0))  # die Auswahl nach vorn
    fehler, _hinweise = pruefe(tmp_path, roh)
    assert fehler == [
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 1 „test“: `aus` „wahl“ steht in einem "
        "anderen Kapitel (Kapitel „Anfang“, Block 2 „wahl“) — ohne `kursplan` muss die Auswahl "
        "im selben Kapitel stehen wie der Test"
    ]
    # im selben Kapitel geht es auch ohne Kursplan
    roh = beispiel()
    del roh["kurse"][0]["kursplan"]
    for kap in roh["kurse"][0]["kapitel"]:
        kap["bloecke"] = [b for b in kap["bloecke"] if not b["art"].startswith("plan_")]
    assert pruefe(tmp_path, roh)[0] == []


def test_hinweis_wenn_nicht_jede_uebung_der_auswahl_das_feld_des_tests_hat(tmp_path) -> None:
    roh = beispiel()
    block(roh, "test")["feld"] = "hold"  # die drei zur Wahl zählen Wiederholungen
    fehler, hinweise = pruefe(tmp_path, roh)
    assert fehler == []
    assert hinweise == [
        "Kurs „Rumpf-Kurs“: Kapitel „Erweiterung“, Block 2 „test“: Das Feld `hold` hat nicht jede "
        "Übung der Auswahl „wahl“ (kaefer, bruecke, beinheben) — für sie gibt es keinen "
        "Testwert, ihr Ziel bliebe offen"
    ]


def test_gestalteter_test_wird_geprueft(tmp_path) -> None:
    """Ein flexibel gestalteter Test (Ben, 16.11.2026; `docs/uebungspakete.md` „Test, flexibel
    gestaltet“): Das Werkzeug nimmt an, was die App versteht — und meldet, was nicht zum Lauf
    passt: Unbekanntes in `wie_uebung`, gemessene Felder in `ziel`/`felder`, einen Timer neben
    der Vorgabe „Zeit“."""
    roh = beispiel()
    test = block(roh, "test")
    test["text"] = "Mach dich vorher 5 Minuten warm."
    test["ziel"] = {"side": "links"}
    test["felder"] = ["weight"]
    test["wie_uebung"] = ["uhr", "takt"]
    assert pruefe(tmp_path, roh) == ([], [])

    test["wie_uebung"] = ["uhr", "wetter"]
    test["ziel"] = {"reps": 10}
    test["vorgabe"] = {"art": "zeit", "n": 60}
    fehler, hinweise = pruefe(tmp_path, roh)
    assert any("`wie_uebung`: „wetter“ ist unbekannt" in f for f in fehler)
    assert any("`ziel`: „reps“ misst der Lauf des Tests" in f for f in fehler)
    assert any("die Vorgabe „Zeit“ gilt dann nicht" in h for h in hinweise)


def test_wenn_ins_leere_ist_ein_fehler() -> None:
    """``wenn`` muss eine Frage des Kurses nennen (Ben, 23.11.2026, Formatversion 8) — sonst
    gälte der Block nie, und niemand merkte es."""
    from trainingsapp.core.pakete import paket_lesen
    from trainingsapp.paket_werkzeug import kursplan_pruefen

    def roh(wenn: dict) -> dict:
        return {
            "paket": {"name": "Q"},
            "exercises": [{"key": "planke", "name": "Planke"}],
            "kurse": [
                {
                    "name": "Rumpf",
                    "kapitel": [
                        {
                            "titel": "Eins",
                            "bloecke": [
                                {
                                    "art": "frage",
                                    "id": "q",
                                    "titel": "Wie?",
                                    "frage": {"art": "ja_nein"},
                                },
                                {
                                    "art": "test",
                                    "id": "t",
                                    "uebung": "planke",
                                    "fragen": [{"id": "n", "text": "Und?", "art": "ja_nein"}],
                                },
                                {"art": "text", "id": "x", "text": "Gut.", "wenn": [wenn]},
                            ],
                        }
                    ],
                }
            ],
        }

    def fehler(wenn: dict) -> list[str]:
        daten = roh(wenn)
        return kursplan_pruefen(daten, paket_lesen(daten))[0]

    assert fehler({"frage": "q", "antworten": ["Ja"]}) == []
    assert fehler({"frage": "t.f:n", "antworten": ["Ja"]}) == []
    assert fehler({"frage": "t.hold", "ab": 30}) == []
    (text,) = fehler({"frage": "weg", "antworten": ["Ja"]})
    assert text.endswith("`wenn` nennt die Frage „weg“ — die gibt es im Kurs nicht")
    (text,) = fehler({"frage": "t.f:x", "antworten": ["Ja"]})
    assert "der Lauf „t“ hat keine Frage „x“" in text
