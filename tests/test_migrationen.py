"""Die Migrationen tragen jede Nummer genau einmal und ohne Lücke (18.11.2026).

Anlass: Zwei Zweige brachten zugleich eine Migration 069 (Medien am Plan, Paketverweise V4). Mit
zwei Dateien gleicher Nummer laufen auf einer neuen Datenbank beide und die Tests bleiben grün —
eine Datenbank, die die eine schon hat (``PRAGMA user_version = 69``), bekommt die andere aber nie.
Eine Lücke wäre dasselbe von der anderen Seite: Was später in sie fällt, läuft nie. Wer zuletzt
nach ``main`` zusammenführt, nummeriert um (`CLAUDE.md`, „Große Änderungen im eigenen Worktree“).
"""

from __future__ import annotations

from trainingsapp.data.db import letzte_migration, verfuegbare_migrationen


def test_jede_nummer_einmal_und_ohne_luecke() -> None:
    nummern = [n for n, _ in verfuegbare_migrationen()]
    doppelt = sorted({n for n in nummern if nummern.count(n) > 1})
    assert not doppelt, f"Migrationen mit derselben Nummer: {doppelt} — die spätere umnummerieren"
    assert nummern == list(range(1, letzte_migration() + 1)), "Lücke in den Migrationen"
