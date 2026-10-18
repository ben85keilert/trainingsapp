"""Zurück führt dorthin, woher man kam (Ben, 18.10.2026) — die Regeln in `ui/navigation.py`.

Ohne flet: Die Regeln sind reine Listenrechnung und laufen auch in der CI.
"""

from __future__ import annotations

from trainingsapp.ui.navigation import MAX_STAPEL, geschwister, naechster_stapel


def _weg(*routen: str, start: list[str] | None = None) -> list[str]:
    """Nacheinander zu den Routen — der Stapel danach."""
    stapel = list(start or [])
    for route in routen:
        stapel = naechster_stapel(stapel, route)
    return stapel


def test_verlauf_uebung_tag_zurueck_fuehrt_zur_uebung() -> None:
    """Bens Beispiel: Verlauf-Tage → Übung → Tag → zurück → die Übung, nicht „Heute“."""
    stapel = _weg("/verlauf/kniebeuge", "/tag/2026-10-17")
    assert stapel == ["/verlauf/kniebeuge", "/tag/2026-10-17"]
    # Zurück: die Ansicht darunter — sie liegt im Stapel, alles darüber fällt weg
    assert naechster_stapel(stapel, "/verlauf/kniebeuge") == ["/verlauf/kniebeuge"]


def test_start_auf_heute_braucht_ein_zurueck() -> None:
    """„Start“ öffnet den Ablauf direkt — ohne Plan und Timer darunter (3× zurück → 1×)."""
    assert _weg("/plan/p1/timer/ablauf") == ["/plan/p1/timer/ablauf"]
    # Wer über den Plan und seinen Timer kam, geht denselben Weg zurück
    assert _weg("/plan/p1", "/plan/p1/timer", "/plan/p1/timer/ablauf") == [
        "/plan/p1",
        "/plan/p1/timer",
        "/plan/p1/timer/ablauf",
    ]


def test_speichern_mit_rueckkehr_schneidet_ab() -> None:
    """Formulare gehen nach dem Speichern zu ihrer Basis — liegt sie im Stapel, ist das ein
    Zurück; liegt sie nicht darin, tritt sie an die Stelle dessen, was unter ihr hängt."""
    stapel = _weg("/tag/2026-10-17", "/tag/2026-10-17/leistungen/kb")
    assert naechster_stapel(stapel, "/tag/2026-10-17") == ["/tag/2026-10-17"]
    # Aus der Infoseite ins Einstellen der Planübung, Speichern geht in den Editor
    stapel = _weg("/plan/p1", "/plan/p1/info/i1", "/plan/p1/bearbeiten/ziel/i1")
    assert naechster_stapel(stapel, "/plan/p1/bearbeiten") == [
        "/plan/p1",
        "/plan/p1/info/i1",
        "/plan/p1/bearbeiten",
    ]


def test_geschwister_ersetzen_bereiche_nicht() -> None:
    """Tag ‹ › und „nächstes Kapitel“ ersetzen — zwei Bereiche auf erster Ebene nicht."""
    assert _weg("/tag/2026-10-17", "/tag/2026-10-16", "/tag/2026-10-15") == ["/tag/2026-10-15"]
    assert _weg("/kurse/k", "/kurse/k/a", "/kurse/k/b") == ["/kurse/k", "/kurse/k/b"]
    assert _weg("/ausdauer", "/timer") == ["/ausdauer", "/timer"]
    assert not geschwister("/ausdauer", "/timer")


def test_ersetzen_und_hauptansicht() -> None:
    assert naechster_stapel(["/ausdauer"], "/ausdauer/s1", ersetzen=True) == ["/ausdauer/s1"]
    assert naechster_stapel(["/plan/p1", "/plan/p1/timer"], "/") == []
    # Dieselbe Route (Neuaufbau ohne Wechsel, Routen-Ereignis des Clients) ändert nichts
    assert naechster_stapel(["/plan/p1"], "/plan/p1/") == ["/plan/p1"]


def test_der_stapel_hat_eine_obergrenze() -> None:
    stapel = _weg(*[f"/uebung/u{i}/x" for i in range(MAX_STAPEL + 3)])
    assert len(stapel) == MAX_STAPEL and stapel[-1] == f"/uebung/u{MAX_STAPEL + 2}/x"
