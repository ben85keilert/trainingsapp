"""Der Fokus — die Trainingsansicht zur laufenden Uhr (Ben, 7.11.2026, `docs/plan_planblock.md`
§B): Chips Takt · Bewegung · HF, die HF-Kachel, die Bildfolge im Takt, der Knopf an der Uhr und
die Einstellung „Fokus beim Start der Uhr öffnen“."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.bewegungsbild import mit_bewegungsbild  # noqa: E402
from trainingsapp.core.models import (  # noqa: E402
    BEGLEITUNG,
    Ereignis,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
)
from trainingsapp.core.paketmedien import name_fuer  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.zaehlen import SensorWahl  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.components.bewegungsbild import Bildfolge, bewegung_im_fokus  # noqa: E402
from trainingsapp.ui.state import FOKUS_HF, FOKUS_VIDEO, OHNE_VIDEO, AppState  # noqa: E402
from trainingsapp.ui.views.uebung_timer import uebung_timer_view  # noqa: E402

#: Ein kleines PNG mit Kopf für 4 quadratische Bilder (1024 × 256)
STREIFEN = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\rIHDR"
    + (1024).to_bytes(4, "big")
    + (256).to_bytes(4, "big")
    + b"\x08\x06\x00\x00\x00"
    + bytes(4)
    # gültig abgeschlossen: die Ablage lehnt ab, was sich nicht ablaufen lässt (D29)
    + b"\x00\x00\x00\x02IDAT\x78\x9c"
    + bytes(4)
    + b"\x00\x00\x00\x00IEND"
    + bytes(4)
)


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "leading", "appbar", "actions", "title"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _ebene_text(eintrag) -> str:
    """Der Name eines Eintrags im Ebenen-Menü (Haken · Name)."""
    return eintrag.content.content.controls[1].value


def _ebene_an(eintrag) -> bool:
    return eintrag.content.content.controls[0].icon == ft.Icons.CHECK_BOX


def _ebenen_menue(ansicht):
    return next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.PopupMenuButton) and x.icon == ft.Icons.LAYERS_OUTLINED
    )


def _kniebeuge(state, *, bild: bool) -> Exercise:
    """Eine Kniebeuge mit Takt (ab · halten · auf) und Timer — mit eigener Bildfolge oder nur
    der Sensor-Vorlage (dann gilt die mitgelieferte)."""
    profil = TimerProfil(id="satz", name="Satz 30 s", abschnitte=[Abschnitt("Satz", 30)], runden=1)
    u = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[vorrat_feld("reps")]),
        timer=[profil.als_dict()],
        takt=VORLAGEN["kniebeuge_2_1_2"],
        beschleunigung=SensorWahl(wiederholungen=True, vorlage="kniebeuge"),
    )
    if bild:
        rel = state.bewegungsbilder.schreiben(STREIFEN)
        u.media = mit_bewegungsbild(u.media, rel)
    state.uebungen.speichern(u)
    return u


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def test_fokus_chips_hf_und_bildfolge_im_takt(umgebung) -> None:
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=True)
    seite = Seite()
    basis = f"/uebung/{u.id}"
    vorher = uebung_timer_view(seite, state, basis, u)
    assert vorher.appbar.title.value == "Timer · Kniebeuge"
    _knopf(vorher, "Starten").on_click()
    await _sekunden(state, uhr, gurt, 3)
    fokus = uebung_timer_view(seite, state, basis, u)
    assert fokus.appbar.title.value == "Fokus · Kniebeuge"
    # Die Ebenen als ein Knopf neben der Zeit (Ben, 8.11.2026 spät) — ein Menü mit Haken
    ebenen = next(
        x
        for x in _alle(fokus)
        if isinstance(x, ft.PopupMenuButton) and x.icon == ft.Icons.LAYERS_OUTLINED
    )
    # „Video“ steht nur da, wenn die Übung ein Begleitvideo hat
    assert [_ebene_text(i) for i in ebenen.items] == ["Takt", "Bewegung", "HF", "Kurve"]
    assert all(_ebene_an(i) for i in ebenen.items)
    # Das Menü bleibt beim Umschalten offen (Ben, 18.11.2026): Den Tipp bekommt ein Container im
    # Eintrag, nie der Eintrag selbst — der schlösse das Menü
    assert all(i.on_click is None and i.content.on_click is not None for i in ebenen.items)
    assert all(i.padding == ft.Padding.all(0) for i in ebenen.items)
    # Ohne den Chip „zählt“ im Kopf (P148) — der ist Anzeige, keine Kurve
    chips = [
        c
        for c in _alle(fokus)
        if isinstance(c, ft.Chip) and c.label.value not in ("zählt", "zählt nicht")
    ]
    # Die Kurven-Einblendung (Ben: „HF, RR, RMSSD, SDNN, Atemfrequenz, RSA“): Reihen als
    # Chips, Vorgabe HF und RMSSD, je gewählter Reihe ein Streifen mit dem letzten Wert
    assert [c.label.value for c in chips] == [
        "HF",
        "RR",
        "RMSSD",
        "SDNN",
        "Atemfrequenz",
        "RSA",
    ]
    assert [c.selected for c in chips] == [True, False, True, False, False, False]
    assert "RMSSD" in _texte(fokus) and any(t.endswith(" bpm") for t in _texte(fokus))
    rr_chip = chips[1]
    rr_chip.on_select(SimpleNamespace(control=rr_chip))
    assert state.fokus_kurven() == ["hf", "rr", "rmssd"]
    assert "HF" in _texte(fokus) and "60" in _texte(fokus)  # der Gurt schlägt im Sekundentakt
    # Die eigene Bildfolge: ein Streifen aus 4 Bildern, im Takt vor und zurück
    streifen = [
        x
        for x in _alle(fokus)
        if isinstance(x, ft.Stack) and x.controls and isinstance(x.controls[0], ft.Image)
    ]
    assert streifen and streifen[0].controls[0].width == 4 * streifen[0].controls[0].height
    # „HF“ im Ebenen-Menü nimmt die Kachel weg — gemerkt, der Haken geht mit
    hf = next(i for i in ebenen.items if _ebene_text(i) == "HF")
    hf.content.on_click(None)
    assert FOKUS_HF not in state.fokus_ebenen() and not _ebene_an(hf)
    karte = next(x for x in _alle(fokus) if isinstance(x, ft.Container) and "HF" in _texte(x)[:1])
    assert karte.visible is False
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


def _begleitvideo(state, u: Exercise) -> str:
    """Ein Begleitvideo aus dem Paket an der Übung — die Datei liegt in der Ablage wie nach
    einem Import."""
    name = name_fuer("b" * 64, "mp4")
    pfad = state.pakete.ablage.pfad(name)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(b"kein echtes Video")
    u.media = [
        *u.media,
        Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=name, rolle=BEGLEITUNG),
    ]
    state.uebungen.speichern(u)
    return str(pfad)


def _spieler(ansicht):
    """Der Videospieler im Fokus (`components/videospieler.py`) — sein Container und das Video."""
    fv = pytest.importorskip("flet_video")
    huelle = next(x for x in _alle(ansicht) if getattr(x, "data", None) == "videospieler")
    video = next(x for x in _alle(huelle) if isinstance(x, fv.Video))
    return huelle, video


def _sichtbar(ansicht, ziel) -> bool:
    """Ist ``ziel`` zu sehen — es selbst und alle Container darüber?"""

    def weg(c, oben):
        if c is ziel:
            return [*oben, c]
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
                if isinstance(k, ft.Control) and (w := weg(k, [*oben, c])) is not None:
                    return w
        return None

    kette = weg(ansicht, [])
    assert kette is not None, "nicht im Baum"
    return all(getattr(c, "visible", True) is not False for c in kette)


async def test_begleitvideo_im_fokus_laeuft_mit_der_uhr_statt_der_bewegung(umgebung) -> None:
    """Ben, 18.11.2026: „Begleitvideos werden noch nicht automatisch im Fokusmodus abgespielt
    … nicht in voller Bildbreite, aber groß genug … mit Steuerungsbuttons. Überlegen, ob
    daneben die Animation Sinn macht, eigentlich entweder oder?“"""
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=True)
    pfad = _begleitvideo(state, u)
    seite = Seite()
    basis = f"/uebung/{u.id}"
    _knopf(uebung_timer_view(seite, state, basis, u), "Starten").on_click()
    await _sekunden(state, uhr, gurt, 2)
    fokus = uebung_timer_view(seite, state, basis, u)
    huelle, video = _spieler(fokus)
    # Es läuft von selbst, in einer Fläche — nicht über die ganze Breite
    assert video.autoplay is True and [m.resource for m in video.playlist] == [pfad]
    assert huelle.width == 320 and _sichtbar(fokus, huelle)
    # Die Knöpfe stehen unter dem Bild, nicht darüber (die von media_kit gehen nach 3 s weg)
    assert {"video_zurueck", "video_spielen", "video_vor", "video_vollbild"} <= {
        getattr(x, "data", None) for x in _alle(huelle)
    }
    # Entweder oder: die Bewegung tritt zurück, solange das Video da ist
    streifen = next(
        x
        for x in _alle(fokus)
        if isinstance(x, ft.Stack) and x.controls and isinstance(x.controls[0], ft.Image)
    )
    assert not _sichtbar(fokus, streifen)
    menue = _ebenen_menue(fokus)
    assert [_ebene_text(i) for i in menue.items] == ["Takt", "Bewegung", "Video", "HF", "Kurve"]

    # Die Uhr hält an — das Video auch; sie läuft weiter — das Video auch
    knopf = next(x for x in _alle(huelle) if getattr(x, "data", None) == "video_spielen")
    state.einheit.timer.lauf.pause()
    state.timer_beobachter["uebung"]()
    await ruhe()
    assert knopf.icon == ft.Icons.PLAY_ARROW
    state.einheit.timer.lauf.fortsetzen()
    state.timer_beobachter["uebung"]()
    await ruhe()
    assert knopf.icon == ft.Icons.PAUSE
    # Von Hand angehalten bleibt es stehen, auch wenn die Uhr anhält und weiterläuft
    await knopf.on_click(None)
    assert knopf.icon == ft.Icons.PLAY_ARROW
    state.einheit.timer.lauf.pause()
    state.timer_beobachter["uebung"]()
    state.einheit.timer.lauf.fortsetzen()
    state.timer_beobachter["uebung"]()
    await ruhe()
    assert knopf.icon == ft.Icons.PLAY_ARROW

    # „Video“ abwählen: die Bewegung kommt zurück — gemerkt je Gerät
    video_eintrag = next(i for i in menue.items if _ebene_text(i) == "Video")
    video_eintrag.content.on_click(None)
    assert FOKUS_VIDEO not in state.fokus_ebenen()
    assert not _sichtbar(fokus, huelle) and _sichtbar(fokus, streifen)
    # wieder an: es beginnt neu — die Uhr läuft, aber das ⏸ von Hand gilt weiter
    video_eintrag.content.on_click(None)
    assert _sichtbar(fokus, huelle) and video.autoplay is False
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


async def test_begleitvideo_wegklicken_und_schleife_fuer_ausschnitte(umgebung) -> None:
    """Ben, 20.11.2026: „Begleitvideos in der Übung müssen direkt weggeklickt werden können
    zusätzlich zur Checkbox im Menü“ und „ein Button für Endlosschleife (automatisch), wenn die
    Begleitung kein Ganzvideo ist, sondern nur ein Ausschnitt, der sich wiederholt“."""
    from pathlib import Path

    from mp4_bau import mp4, spur

    fv = pytest.importorskip("flet_video")
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=True)
    pfad = Path(_begleitvideo(state, u))
    # Ein Ausschnitt von 12 s: läuft von selbst als Schleife
    pfad.write_bytes(
        mp4(spur(b"vide", breite=1280, hoehe=720, dauer_s=12.0, bilder=300), dauer_s=12.0)
    )
    seite = Seite()
    basis = f"/uebung/{u.id}"
    _knopf(uebung_timer_view(seite, state, basis, u), "Starten").on_click()
    await _sekunden(state, uhr, gurt, 2)
    fokus = uebung_timer_view(seite, state, basis, u)
    huelle, video = _spieler(fokus)
    assert video.playlist_mode == fv.PlaylistMode.LOOP and state.video_schleife(u.id) is None
    # Der Knopf stellt sie ab — gemerkt an dieser Übung, auch beim nächsten Mal
    next(x for x in _alle(huelle) if getattr(x, "data", None) == "video_schleife").on_click(None)
    assert video.playlist_mode == fv.PlaylistMode.NONE and state.video_schleife(u.id) is False
    # Ein ganzes Video (10 min) läuft einmal durch — bis die Person es anders stellt
    state.video_schleife_setzen(u.id, True)
    assert state.video_schleife(u.id) is True

    # Das ✕ im Bild: wie der Haken „Video“ im Menü — die Bewegung kommt zurück
    assert FOKUS_VIDEO in state.fokus_ebenen() and _sichtbar(fokus, huelle)
    next(x for x in _alle(huelle) if getattr(x, "data", None) == "video_schliessen").on_click(None)
    assert FOKUS_VIDEO not in state.fokus_ebenen() and not _sichtbar(fokus, huelle)
    video_eintrag = next(i for i in _ebenen_menue(fokus).items if _ebene_text(i) == "Video")
    video_eintrag.content.on_click(None)  # im Menü kommt es wieder
    assert _sichtbar(fokus, huelle)
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)

    lang = Path(_begleitvideo(state, _kniebeuge(state, bild=False)))
    lang.write_bytes(
        mp4(spur(b"vide", breite=1280, hoehe=720, dauer_s=600.0, bilder=300), dauer_s=600.0)
    )
    from trainingsapp.core import videoinfo

    assert not videoinfo.ist_ausschnitt(videoinfo.lesen(lang).dauer_s)


async def test_stueck_bei_einem_ereignis_meldet_sich_unter_der_uhr(umgebung) -> None:
    """Ben, 18.11.2026: „zu bestimmten Ereignissen … wenn Wdh oder Zeit soundso → Video“ — ein
    Hinweis unter der Uhr, die Uhr läuft weiter; ein Tipp öffnet das Blatt."""
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=False)
    u.media = [
        Media(
            uri="https://x.org/satz.mp4",
            title="So geht der Satz",
            wann="bei",
            bei=Ereignis("abschnitt", name="satz"),
        ),
        Media(
            uri="https://x.org/spaet.mp4",
            title="Nach 20 Sekunden",
            wann="bei",
            bei=Ereignis("zeit", sekunden=20),
        ),
    ]
    state.uebungen.speichern(u)
    u = state.uebungen.laden(u.id)
    seite = Seite()
    basis = f"/uebung/{u.id}"
    _knopf(uebung_timer_view(seite, state, basis, u), "Starten").on_click()
    await _sekunden(state, uhr, gurt, 2)
    fokus = uebung_timer_view(seite, state, basis, u)
    hinweise = [
        x
        for x in _alle(fokus)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "ereignis"
    ]
    # Der Abschnitt läuft schon (ohne Rücksicht auf Groß und klein), die 20 Sekunden noch nicht
    assert [h.data[1] for h in hinweise] == ["https://x.org/satz.mp4"]
    assert "So geht der Satz" in _texte(hinweise[0])
    await _sekunden(state, uhr, gurt, 20)
    state.timer_beobachter["uebung"]()
    hinweise = [
        x
        for x in _alle(fokus)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "ereignis"
    ]
    assert [h.data[1] for h in hinweise] == ["https://x.org/satz.mp4", "https://x.org/spaet.mp4"]
    # „Ansehen“ öffnet das Blatt mit dem Stück oben und nimmt den Hinweis weg
    ansehen = next(x for x in _alle(hinweise[0]) if isinstance(x, ft.TextButton))
    ansehen.on_click(None)
    assert "Jetzt" in _texte(seite.dialoge[-1]) and "So geht der Satz" in _texte(seite.dialoge[-1])
    hinweise = [
        x
        for x in _alle(fokus)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "ereignis"
    ]
    assert [h.data[1] for h in hinweise] == ["https://x.org/spaet.mp4"]
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


async def test_nachher_kommt_nach_dem_ende_der_uebung(umgebung) -> None:
    """Ben, 18.11.2026: Medien „am Ende“ — nach „Fertig“ geht das Blatt „Nach der Übung“ auf,
    erst wenn die Einheit abgeschlossen ist und die Ansicht neu steht; nach einem Abbruch nicht."""
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=False)
    u.media = [
        Media(uri="https://x.org/dehnen.mp4", title="Dehnen danach", wann="nachher", zeigen=True)
    ]
    state.uebungen.speichern(u)
    u = state.uebungen.laden(u.id)
    seite = Seite()
    basis = f"/uebung/{u.id}"

    def blaetter() -> list[str]:
        return [t for d in seite.dialoge for t in _texte(d) if t == "Nach der Übung"]

    # Abgebrochen: kein Blatt
    _knopf(uebung_timer_view(seite, state, basis, u), "Starten").on_click()
    await _sekunden(state, uhr, gurt, 2)
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)
    await asyncio.sleep(0.8)
    assert blaetter() == []
    # Fertig: das Blatt kommt
    _knopf(uebung_timer_view(seite, state, basis, u), "Starten").on_click()
    await _sekunden(state, uhr, gurt, 2)
    _knopf(uebung_timer_view(seite, state, basis, u), "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 2)
    await asyncio.sleep(0.8)
    assert blaetter() == ["Nach der Übung"]


def test_ebene_video_ist_an_bis_man_sie_abwaehlt(tmp_path, monkeypatch) -> None:
    """Eine gespeicherte Liste von vor der Ebene „Video“ lässt das Video an."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        assert FOKUS_VIDEO in state.fokus_ebenen()
        state.einstellungen.setzen("fokus_ebenen", "takt,hf")  # so schrieb es die App bisher
        assert state.fokus_ebenen() == {"takt", "hf", FOKUS_VIDEO}
        state.fokus_ebenen_setzen({"takt"})
        assert state.einstellungen.lesen("fokus_ebenen") == f"takt,{OHNE_VIDEO}"
        assert state.fokus_ebenen() == {"takt"}
        state.fokus_ebenen_setzen(set())
        assert state.fokus_ebenen() == set()
    finally:
        state.schliessen()


def test_bildfolge_waehlt_das_bild_nach_takt_und_zeit() -> None:
    folge = Bildfolge("x.png", 12, hoehe=100)
    assert folge.control.width == 100 and folge.bild.width == 1200
    t = VORLAGEN["kniebeuge_2_1_2"]
    from trainingsapp.core.takt import lage

    folge.nachziehen(t, lage(t, t.dauer_s(0) / 2), 0.0)  # mitten im „ab“
    assert 0 < folge.index < 11 and folge.bild.left == -folge.index * 100
    folge.nachziehen(None, None, 0.0)  # ohne Takt: Pendel über die Zeit
    assert folge.index == 0
    folge.nachziehen(None, None, 1.5)
    assert folge.index == 11


def test_mitgelieferte_kniebeuge_ohne_eigenes_bild(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        u = _kniebeuge(state, bild=False)
        paar = bewegung_im_fokus(state, u)
        assert paar is not None
        _control, wahl = paar
        folge = wahl.folge
        assert isinstance(folge, Bildfolge) and folge.anzahl == 12
        assert wahl.knopf.visible is False  # nur eine — nichts zu blättern
        assert folge.bild.src.endswith("kniebeuge.png")
        ohne = Exercise(name="Planke")
        assert bewegung_im_fokus(state, ohne) is None
    finally:
        state.schliessen()


def test_fokus_knopf_an_der_laufenden_uhr_und_einstellung(tmp_path, monkeypatch) -> None:
    from trainingsapp.core.timer import TimerLauf
    from trainingsapp.devices.einheit import (
        Einheitslauf,
        TimerBaustein,
        UebungBaustein,
        UebungKontext,
    )
    from trainingsapp.ui.components.uhr import _laufend
    from trainingsapp.ui.views.einstellungen_seiten import einstellungen_uebungen

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        page = Seite()
        u = Exercise(name="Planke")
        state.uebungen.speichern(u)
        e = Einheitslauf(uhr=lambda: 0.0, titel="Planke")
        e.hinzufuegen(UebungBaustein(UebungKontext(u.id, u.name)))
        e.hinzufuegen(TimerBaustein(TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60)]))))
        e.starten()
        geoeffnet: list[int] = []
        anzeige = _laufend(page, state, e, fokus=lambda: geoeffnet.append(1))
        knopf = next(
            x
            for x in _alle(anzeige)
            if isinstance(x, ft.IconButton) and x.icon == ft.Icons.OPEN_IN_FULL
        )
        assert knopf.tooltip.startswith("Fokus")
        knopf.on_click()
        assert geoeffnet == [1]
        assert not any(
            isinstance(x, ft.IconButton) and x.icon == ft.Icons.OPEN_IN_FULL
            for x in _alle(_laufend(page, state, e))
        )
        # Die Einstellung: Vorgabe an (P145, 8.11.2026), der Schalter stellt sie
        assert state.fokus_auto() is True
        ansicht = einstellungen_uebungen(page, state)  # Einstellungen → Übungen
        schalter = next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.Switch) and x.label == "▶ öffnet den Fokus"
        )
        assert schalter.value is True
        schalter.value = False
        schalter.on_change(SimpleNamespace(control=schalter))
        assert state.fokus_auto() is False
    finally:
        state.schliessen()
