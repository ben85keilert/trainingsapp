"""Mehrere Stücke an einem Weg (Ben, 18.11.2026: „Bisher geht das vor allem für bestimmte Wege“
— und nur mit einem Link; `docs/plan_medien_zeitpunkte.md` §2, Frage d): der Editor des Wegs
nimmt weitere Links mit Titel."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.ablauf import Ablauf, Kante  # noqa: E402
from trainingsapp.core.bedingung import Inhalt, Stueck  # noqa: E402
from trainingsapp.ui.components.wege_form import wege_karte  # noqa: E402


def _alle(c):
    yield c
    for name in ("content", "controls"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _verlassen(feld, wert: str) -> None:
    feld.on_blur(SimpleNamespace(control=SimpleNamespace(value=wert)))


def test_weiteres_medium_am_weg() -> None:
    kante = Kante("i1", "i2", inhalt=Inhalt("Erst lockern", "https://x.org/a"))
    stand = {"a": Ablauf(an=True, start="i1", kanten=(kante,))}
    merken: dict = {}

    def karte():
        return wege_karte(
            "i1",
            lambda: stand["a"],
            lambda neu: stand.update(a=neu),
            lambda: None,
            namen={"i1": "1 · Kniebeuge", "i2": "2 · Planke"},
            merken=merken,
        )

    _daten(karte(), "weg_stueck_dazu").on_click(None)
    # Der Titel allein wartet, bis die Adresse dasteht
    _verlassen(_daten(karte(), ("weg_stueck_titel", 0)), "Wade dehnen")
    assert stand["a"].kanten[0].inhalt.medien == ()
    assert _daten(karte(), ("weg_stueck_titel", 0)).value == "Wade dehnen"
    _verlassen(_daten(karte(), ("weg_stueck_uri", 0)), "https://x.org/wade")
    inhalt = stand["a"].kanten[0].inhalt
    assert inhalt.medien == (Stueck("https://x.org/wade", "Wade dehnen"),)
    assert (inhalt.text, inhalt.url) == ("Erst lockern", "https://x.org/a")  # bleibt
    # Eine geleerte Adresse nimmt das Stück heraus
    _verlassen(_daten(karte(), ("weg_stueck_uri", 0)), "")
    assert stand["a"].kanten[0].inhalt.medien == ()


FILM = "medien/" + "a" * 64 + ".mp4"


def test_datei_und_vorhandenes_am_weg(tmp_path, monkeypatch) -> None:
    """Ben, 19.11.2026 (`docs/plan_medien_einheitlich.md` §2.2): Am Weg hängt auch eine Datei —
    aus dem, was der Plan schon trägt, als Verweis; Kamera und Rekorder legen ihr Stück über die
    Ablage an die Kante; Aufräumen und Export sehen die Datei."""
    from dataclasses import replace

    from trainingsapp.core.ablauf import wegdateien
    from trainingsapp.core.anhaenge import Ziel
    from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource, Plan
    from trainingsapp.ui import paketdatei
    from trainingsapp.ui.components.wege_form import (
        WegMedien,
        ablage_schluessel,
        stuecke_abholen,
    )
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.ablauf import ablauf_speichern

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        u = Exercise(name="Kniebeuge")
        state.uebungen.speichern(u)
        plan = Plan(name="Beine", subject_id=state.profil.id)
        state.plaene.speichern(plan)
        a_ = state.plaene.uebung_hinzufuegen(plan.id, u.id)
        b_ = state.plaene.uebung_hinzufuegen(plan.id, u.id)
        film = Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=FILM, title="Film")
        state.plaene.medien_setzen(plan.id, [film])
        pfad = state.pakete.ablage.pfad(FILM)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"\x00" * 8)
        stand = {"a": Ablauf(an=True, start=a_.id, kanten=(Kante(a_.id, b_.id),))}
        dialoge: list = []
        gerufen: list = []
        page = SimpleNamespace(
            platform=ft.PagePlatform.ANDROID,
            web=False,
            show_dialog=dialoge.append,
            pop_dialog=lambda: dialoge.pop() if dialoge else None,
            update=lambda: None,
        )
        merken: dict = {"inhalt0": True}

        def karte():
            return wege_karte(
                a_.id,
                lambda: stand["a"],
                lambda neu: stand.update(a=neu),
                lambda: None,
                namen={a_.id: "1 · Kniebeuge", b_.id: "2 · Kniebeuge"},
                merken=merken,
                medien=WegMedien(
                    page,
                    state,
                    lambda i, art: gerufen.append((i, art)),
                    lambda: [(film, "Plan Beine")],
                ),
            )

        menue = _daten(karte(), "weg_medium_dazu0")
        assert [i.data[1] for i in menue.items] == [
            "link",
            "foto",
            "video",
            "datei",
            "ton",
            "vorhandenes",
        ]
        next(i for i in menue.items if i.data[1] == "video").on_click(None)
        assert gerufen == [(0, "video")]
        # Aus vorhandenen Medien: das Video des Plans, als Verweis
        menue.items[-1].on_click(None)
        _daten(dialoge[-1], ("vorhandenes", FILM)).on_click(None)
        (s,) = stand["a"].kanten[0].inhalt.medien
        assert (s.uri, s.ist_datei, s.kind, s.title) == (FILM, True, "video", "Film")
        # Titel und Beschriftung am Weg — keine Adresse
        _verlassen(_daten(karte(), ("weg_stueck_text", 0)), "nur wenn es zieht")
        assert stand["a"].kanten[0].inhalt.medien[0].text == "nur wenn es zieht"
        assert not [x for x in _alle(karte()) if getattr(x, "data", None) == ("weg_stueck_uri", 0)]
        # Gespeichert: Die Ablage zählt die Datei als benutzt, auch ohne das Stück am Plan
        ablauf_speichern(state, plan.id, stand["a"])
        state.plaene.medien_setzen(plan.id, [])
        assert FILM in state.pakete.ablage.benutzte()
        assert wegdateien(state.plaene.laden(plan.id).ablauf.als_dict()) == {FILM}
        # Kamera: das Stück wartet unter dem Schlüssel der Kante und hängt sich beim Abholen an
        ton = replace(film, uri="medien/" + "b" * 64 + ".m4a", kind=MediaKind.AUDIO, title="Ton")
        paketdatei.anhaengen(state, Ziel.fuer_ablage(ablage_schluessel(plan.id, 0)), ton)
        mit = stuecke_abholen(state, plan.id, state.plaene.laden(plan.id).ablauf)
        assert [x.title for x in mit.kanten[0].inhalt.medien] == ["Film", "Ton"]
        assert stuecke_abholen(state, plan.id, mit) is mit  # nur einmal
        # Herausnehmen
        stand["a"] = mit
        _daten(karte(), ("weg_stueck_weg", 0)).on_click(None)
        assert [x.title for x in stand["a"].kanten[0].inhalt.medien] == ["Ton"]
    finally:
        state.schliessen()
