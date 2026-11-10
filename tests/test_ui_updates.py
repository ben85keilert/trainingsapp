"""Seite „Updates“, Start-Prüfung und Label (Ben, 16.10.2026). Nur mit flet."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.pakete import Paket, paket_lesen  # noqa: E402
from trainingsapp.core.paketquelle import IndexEintrag, PaketUpdate, Pruefung  # noqa: E402
from trainingsapp.data.repositories import SettingRepo  # noqa: E402
from trainingsapp.ui import app as app_modul  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views import updates  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], platform=None, dialoge=[], aufgaben=[])
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.run_task = lambda f, *a: p.aufgaben.append((f, a))
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "spans", "trailing", "leading", "appbar"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(ansicht) -> list[str]:
    return [
        getattr(c, "value", None) or getattr(c, "text", None) or ""
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.Text | ft.TextSpan)
    ]


def qigong(version: int, **extra) -> dict:
    return {
        "paket": {"name": "Qigong", "version": version, **extra},
        "exercises": [
            {"key": "baum", "name": "Baum", "description": "Knie weich.", "spec": "halten"},
            {
                "key": "lotus",
                "name": f"Lotus v{version}",
                "description": "Sitzen.",
                "spec": "halten",
            },
        ],
    }


def test_seite_baut_und_markiert_gesehen(page, state) -> None:
    state.paketquellen_setzen([])  # ausdrücklich keine — sonst gilt die Vorgabe
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert ansicht.route == "/einstellungen/updates"
    assert "Noch nicht geprüft" in texte(ansicht)
    assert any("Keine Quelle" in t for t in texte(ansicht))


def test_pruefung_auto_und_manuell(page, state, monkeypatch) -> None:
    """Modus auto spielt gleich ein; manuell merkt vor, die Seite bietet den Pfeil."""
    inhalt_v1 = paket_lesen(qigong(1))
    state.pakete.importieren(inhalt_v1)
    pid = inhalt_v1.paket.id
    eintrag = IndexEintrag(
        pid,
        "Qigong",
        2,
        "https://x/q.json",
        "",
        0,
        "https://x/i",
        "Praxis",
        neuigkeiten="Neu: Lotus",
    )
    inhalt_v2 = paket_lesen(qigong(2, neuigkeiten="Neu: Lotus"))

    def fake_pruefen(quellen, installierte, laden=None, **_):
        return Pruefung(
            updates=[PaketUpdate(eintrag, next(p for p in installierte if p.id == pid))]
        )

    monkeypatch.setattr(updates, "pruefen", fake_pruefen)
    monkeypatch.setattr(updates, "paket_laden", lambda e, laden=None, **_: inhalt_v2)
    monkeypatch.setattr(updates, "neuestes_release", lambda: None)
    state.paketquellen_setzen(["https://x/i"])

    # auto: eingespielt, Quelle gemerkt, Label meldet es
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert [(i, n, v) for i, n, v in stand.eingespielt] == [(pid, "Qigong", 2)]
    assert stand.pruefung.updates == []
    p = state.pakete.laden(pid)
    assert p.version == 2 and p.quelle == "https://x/i" and p.verfuegbar is None  # = Index
    assert "Lotus v2" in [u.name for u in state.uebungen.alle()]
    assert state.updates_label() == "Updates verfügbar: aktualisiert: Qigong"
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert any("Qigong auf Version 0.0.2 aktualisiert" in t for t in texte(ansicht))
    assert state.updates_label() is None  # Seite geöffnet = gesehen

    # manuell: nur vorgemerkt
    state.pakete.update_modus_setzen(pid, "manuell")
    eintrag3 = IndexEintrag(
        pid,
        "Qigong",
        3,
        "https://x/q3.json",
        "",
        0,
        "https://x/i",
        "Praxis",
        neuigkeiten="Neu: Kranich",
    )
    jetzt_installiert = state.pakete.laden(pid)  # vorher laden: im Thread kein SQLite
    monkeypatch.setattr(
        updates,
        "pruefen",
        lambda q, i, laden=None: Pruefung(updates=[PaketUpdate(eintrag3, jetzt_installiert)]),
    )
    inhalt_v3 = paket_lesen(qigong(3))
    monkeypatch.setattr(updates, "paket_laden", lambda e, laden=None, **_: inhalt_v3)
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert stand.eingespielt == [] and [u.eintrag.version for u in stand.pruefung.updates] == [3]
    assert state.pakete.laden(pid).verfuegbar == 3 and state.pakete.laden(pid).version == 2
    assert state.updates_label() == "Updates verfügbar: 1 Paket"
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert any("verfügbar: Version 0.0.3" in t for t in texte(ansicht))
    assert any("Neu: Kranich" in t for t in texte(ansicht))
    pfeil = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DOWNLOAD
    )
    asyncio.run(pfeil.on_click())  # Vorschau-Dialog wie beim Datei-Import
    frage = page.dialoge[-1]
    frage.actions[1].on_click()
    p = state.pakete.laden(pid)
    assert p.version == 3 and p.verfuegbar is None and p.quelle == "https://x/i"
    assert state.updates.pruefung.updates == []
    # Aus der gebundenen Quelle geholt: kein Hinweis auf fremde Identität im Dialog
    assert not any("gibt sich als" in t for t in texte(frage.content))


def test_neue_pakete_und_quellen_fehler(page, state, monkeypatch) -> None:
    neu = IndexEintrag(
        "p9", "Yoga", 1, "https://x/y.json", "", 0, "https://x/i", "Praxis", uebungen=3
    )
    monkeypatch.setattr(
        updates,
        "pruefen",
        lambda q, i, laden=None: Pruefung(neue=[neu], fehler=["https://kaputt: HTTP 404"]),
    )
    monkeypatch.setattr(updates, "neuestes_release", lambda: None)
    state.paketquellen_setzen(["https://x/i", "https://kaputt"])
    asyncio.run(updates.pruefung_ausfuehren(state))
    assert state.updates_label() is None  # „updates“: neue Pakete melden sich nicht
    state.benachrichtigung_setzen("alles")
    assert state.updates_label() == "1 neues Paket in den Quellen"
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert "NEU IN DEN QUELLEN" in texte(ansicht) and "Yoga" in texte(ansicht)
    assert any("HTTP 404" in t for t in texte(ansicht))


def test_quellen_verwalten(page, state, monkeypatch) -> None:
    state.paketquellen_setzen([])  # von einer leeren Liste aus, unabhängig von der Vorgabe
    geladen: list[str] = []

    async def link_importieren(_page, _state, url: str) -> None:
        """Der Link wird geladen und mit Rückfrage eingetragen (`components/paket_link`) —
        hier nur gemerkt und direkt eingetragen."""
        geladen.append(url)
        _state.paketquellen_setzen([*_state.paketquellen(), url])

    monkeypatch.setattr(updates, "link_importieren", link_importieren)
    page.run_task = lambda f, *a: asyncio.run(f(*a))
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    feld = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.TextField))
    plus = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.ADD
    )
    feld.value = "http://unsicher.de/i.json"
    plus.on_click()
    assert feld.error and state.paketquellen() == []
    feld.value = "https://sicher.de/i.json"
    plus.on_click()
    assert geladen == ["https://sicher.de/i.json"]
    assert state.paketquellen() == ["https://sicher.de/i.json"]
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    weg = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE
    )
    weg.on_click()
    assert state.paketquellen() == []


def test_beim_start_fragt_einmal_und_laesst_sich_ausschalten(page, state) -> None:
    asyncio.run(updates.beim_start(page, state))
    hinweis = page.dialoge[-1]
    assert "Updates beim Start" in hinweis.title.value
    hinweis.actions[0].on_click()  # Ausschalten
    assert state.update_pruefung() is False
    assert state.einstellungen.lesen(SettingRepo.HINWEIS_UPDATES) == "1"
    asyncio.run(updates.beim_start(page, state))
    assert len(page.dialoge) == 1 and page.aufgaben == []  # aus: nichts passiert

    state.update_pruefung_setzen(True)
    state.einstellungen.setzen(SettingRepo.HINWEIS_UPDATES, "0")
    asyncio.run(updates.beim_start(page, state))
    page.dialoge[-1].actions[1].on_click()  # Verstanden → Prüfung läuft an
    assert page.aufgaben and page.aufgaben[-1][0] is updates._starten


def test_label_unter_dem_zahnrad(page, state) -> None:
    page.push_route = None
    assert state.updates_label() is None
    ansicht = app_modul.hauptansicht(page, state)
    assert not any(
        isinstance(c, ft.TextButton) and c.icon == ft.Icons.SYSTEM_UPDATE
        for v in ansicht.controls
        for c in alle(v)
    )
    e = IndexEintrag("p1", "Dehnung", 2, "https://x/d.json", "", 0, "q")
    state.updates = updates.UpdateStand(
        Pruefung(updates=[PaketUpdate(e, Paket(id="p1", name="Dehnung", version=1))])
    )
    ansicht = app_modul.hauptansicht(page, state)
    knopf = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.TextButton) and c.icon == ft.Icons.SYSTEM_UPDATE
    )
    assert knopf.content == "Updates verfügbar: 1 Paket"


def test_stufe_aus_dem_unterschied_entscheidet(page, state, monkeypatch) -> None:
    """U6 (Ben, 9.11.2026, F8 c): Die Stufe kommt aus dem Unterschied, nicht aus der Nummer —
    „Kleine“ spielt nur kleine Änderungen ein (Symbol, Timer …), „Alle“ auch mittlere (Texte,
    neue Übungen); eine große (eine Übung fällt weg) wird nur vorgemerkt, mit Grund."""

    def fassung(
        version: int,
        symbol: str = "self_improvement",
        text: str = "Knie weich.",
        mit_lotus: bool = True,
    ) -> dict:
        uebungen = [
            {
                "key": "baum",
                "name": "Baum",
                "description": text,
                "spec": "halten",
                "icon_key": symbol,
            }
        ]
        if mit_lotus:
            uebungen.append({"key": "lotus", "name": "Lotus", "description": "Sitzen."})
        return {"paket": {"name": "Qigong", "version": version}, "exercises": uebungen}

    inhalt = paket_lesen(fassung(4))
    state.pakete.importieren(inhalt)
    pid = inhalt.paket.id
    state.pakete.update_modus_setzen(pid, "klein")
    monkeypatch.setattr(updates, "neuestes_release", lambda: None)
    state.paketquellen_setzen(["https://x/i"])

    def anbieten(roh: dict) -> None:
        version = roh["paket"]["version"]
        eintrag = IndexEintrag(
            pid, "Qigong", version, f"https://x/q{version}.json", "", 0, "https://x/i"
        )
        jetzt = state.pakete.laden(pid)  # vorher laden: im Thread kein SQLite
        monkeypatch.setattr(
            updates,
            "pruefen",
            lambda q, i, laden=None: Pruefung(updates=[PaketUpdate(eintrag, jetzt)]),
        )
        monkeypatch.setattr(updates, "paket_laden", lambda e, laden=None, **_: paket_lesen(roh))

    anbieten(fassung(5, symbol="spa"))  # nur das Symbol: klein
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert [v for _, _, v in stand.eingespielt] == [5] and state.pakete.laden(pid).version == 5
    anbieten(fassung(6, symbol="spa", text="Knie ganz weich."))  # ein Text: mittel
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert stand.eingespielt == [] and state.pakete.laden(pid).verfuegbar == 6
    assert stand.stufen[pid].stufe == "mittel"
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert any("verfügbar: Version 0.0.6 · mittlere Änderung" in t for t in texte(ansicht))
    # „Alle“: mittel kommt von selbst …
    state.pakete.update_modus_setzen(pid, "auto")
    anbieten(fassung(6, symbol="spa", text="Knie ganz weich."))
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert [v for _, _, v in stand.eingespielt] == [6]
    # … groß fragt nach (eine Übung fällt weg) — auch wenn die Nummer nur klein steigt
    anbieten(fassung(7, symbol="spa", text="Knie ganz weich.", mit_lotus=False))
    stand = asyncio.run(updates.pruefung_ausfuehren(state))
    assert stand.eingespielt == [] and stand.stufen[pid].gruende == ["„Lotus“ fällt weg"]
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    assert any("verfügbar: Version 0.0.7 · große Änderung" in t for t in texte(ansicht))
    pfeil = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DOWNLOAD
    )
    assert "„Lotus“ fällt weg" in pfeil.tooltip


def test_fuer_alle_pakete_und_neue(page, state) -> None:
    """„Für alle Pakete“: jedes installierte bekommt den Modus, ein neues ebenso."""
    erstes = paket_lesen(qigong(1))
    state.pakete.importieren(erstes)
    ansicht = updates.updates_view(page, state, ft.UrlLauncher())
    wahl = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.SegmentedButton) and c.data == "paket_updates_alle"
    )
    assert wahl.selected == ["auto"]
    wahl.selected = ["klein"]
    wahl.on_change(SimpleNamespace(control=wahl))
    assert state.paket_updates() == "klein"
    assert {p.update_modus for p, _ in state.pakete.alle()} == {"klein"}
    neu = paket_lesen(
        {
            "paket": {"name": "Dehnung", "version": "1.0.0"},
            "exercises": [{"key": "katze", "name": "Katze", "spec": "halten"}],
        }
    )
    state.pakete.importieren(neu)
    p = state.pakete.laden(neu.paket.id)
    assert p.update_modus == "klein" and p.version == 10000
    # ein Update lässt den Modus stehen, den die Person je Paket gewählt hat
    state.pakete.update_modus_setzen(neu.paket.id, "manuell")
    state.pakete.importieren(neu)
    assert state.pakete.laden(neu.paket.id).update_modus == "manuell"
