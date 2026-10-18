"""Der Ansichtsstapel folgt dem Weg, den man ging (Ben, 18.10.2026) — ohne flet.

Bis 18.10. baute `app.zeige_route` den Stapel allein aus der Route: ``/tag/2026-10-17``
lag immer direkt über der Hauptansicht, ``/plan/x/timer/ablauf`` immer über Plan und Timer.
Ben: „Man klickt wo rein, geht zurück und landet ganz wo anders, z. B. bei Verlauf-Tage,
klickt auf Übung → Tag → zurück → Übung“ — und vom „Start“ auf „Heute“ in den Ablauf
brauchte es dreimal Zurück (Timer, Plan, Menü), wo man nur einmal hineingetippt hatte.

Jetzt merkt sich die App die Routen über der Hauptansicht in der Reihenfolge, in der man
sie öffnete (`AppState.navigation`), und baut je Route nur deren **oberste** Ansicht.
Zurück führt so immer dorthin, woher man kam. Nur beim ersten Aufbau (Start auf einer
tiefen Route, Neuladen im Browser) gilt die Route allein — wie früher, damit Zurück auch
dann funktioniert.

Regeln für den nächsten Stapel (`naechster_stapel`):

- ``/`` — die Hauptansicht, der Stapel ist leer.
- Eine Route, die schon im Stapel liegt — zurück dorthin, alles darüber fällt weg
  (Zurück, „Speichern“ mit Rückkehr, Browser-Zurück).
- Eine Route über der obersten (die oberste ist ihr Nachfahre) — nach oben: was unter ihr
  hängt, fällt weg, sie selbst kommt dazu.
- Ein Geschwister der obersten (gleicher Elternpfad, ab zwei Ebenen: Tag ‹ ›, nächstes
  Kapitel) oder ein ausdrückliches „ersetzen“ — die oberste wird ersetzt.
- Sonst kommt die Route oben dazu; höchstens `MAX_STAPEL` Routen.
"""

from __future__ import annotations

from collections.abc import Sequence

#: So viele Routen liegen höchstens über der Hauptansicht — jede wird bei jedem Wechsel
#: neu gebaut, auch die verdeckten
MAX_STAPEL = 8


def teile(route: str) -> list[str]:
    """Die Teile einer Route — ``"/plan/abc"`` → ``["plan", "abc"]``.

    >>> teile("/plan/abc/"), teile("/")
    (['plan', 'abc'], [])
    """
    return [t for t in route.split("/") if t]


def normal(route: str) -> str:
    """Eine Route ohne doppelte und abschließende Schrägstriche.

    >>> normal("/plan//abc/"), normal(""), normal("/")
    ('/plan/abc', '/', '/')
    """
    return "/" + "/".join(teile(route))


def ist_nachfahre(route: str, vorfahr: str) -> bool:
    """Liegt ``route`` unter ``vorfahr``?

    >>> ist_nachfahre("/plan/x/timer", "/plan/x"), ist_nachfahre("/plan/xy", "/plan/x")
    (True, False)
    >>> ist_nachfahre("/tag/d", "/")
    True
    """
    a, b = teile(route), teile(vorfahr)
    return len(a) > len(b) and a[: len(b)] == b


def geschwister(a: str, b: str) -> bool:
    """Gleicher Elternpfad und gleiche Tiefe — erst ab zwei Ebenen: ``/tag/d1`` und
    ``/tag/d2`` ja, ``/ausdauer`` und ``/timer`` nicht (das sind verschiedene Bereiche).

    >>> geschwister("/tag/2026-10-17", "/tag/2026-10-16")
    True
    >>> geschwister("/kurse/k/a", "/kurse/k/b"), geschwister("/ausdauer", "/timer")
    (True, False)
    >>> geschwister("/plan/x/timer/uebung/u1", "/plan/x/timer/uebung/u2")
    True
    >>> geschwister("/tag/d", "/tag/d")
    False
    """
    ta, tb = teile(a), teile(b)
    return ta != tb and len(ta) == len(tb) >= 2 and ta[:-1] == tb[:-1]


def naechster_stapel(stapel: Sequence[str], route: str, *, ersetzen: bool = False) -> list[str]:
    """Die Routen über der Hauptansicht nach dem Wechsel zu ``route`` (Moduldocstring).

    ``ersetzen``: Die neue Route tritt an die Stelle der obersten — wenn das Alte nicht mehr
    gilt (Training beendet → Auswertung, die nächste Übung im Timer).

    Aus dem Verlauf in eine Übung, von dort in einen Tag — Zurück führt zur Übung:

    >>> naechster_stapel(["/verlauf/k"], "/tag/2026-10-17")
    ['/verlauf/k', '/tag/2026-10-17']
    >>> naechster_stapel(["/verlauf/k", "/tag/2026-10-17"], "/verlauf/k")
    ['/verlauf/k']

    „Start“ auf „Heute“ öffnet den Ablauf direkt — ein Zurück, nicht drei:

    >>> naechster_stapel([], "/plan/x/timer/ablauf")
    ['/plan/x/timer/ablauf']
    >>> naechster_stapel(["/plan/x/timer/ablauf"], "/")
    []

    Tiefer, nach oben, Geschwister, ersetzen:

    >>> naechster_stapel(["/plan/x"], "/plan/x/timer")
    ['/plan/x', '/plan/x/timer']
    >>> naechster_stapel(["/plan/x/timer/ablauf"], "/plan/x")
    ['/plan/x']
    >>> naechster_stapel(["/tag/2026-10-17"], "/tag/2026-10-16")
    ['/tag/2026-10-16']
    >>> naechster_stapel(["/ausdauer"], "/ausdauer/s1", ersetzen=True)
    ['/ausdauer/s1']
    >>> naechster_stapel(["/ausdauer"], "/timer")
    ['/ausdauer', '/timer']
    >>> naechster_stapel(["/plan/x"], "/plan/x")
    ['/plan/x']
    >>> len(naechster_stapel([f"/a{i}" for i in range(MAX_STAPEL)], "/b"))
    8
    """
    route = normal(route)
    if route == "/":
        return []
    stapel = [normal(r) for r in stapel]
    if route in stapel:
        return stapel[: stapel.index(route) + 1]
    if stapel and ist_nachfahre(stapel[-1], route):
        while stapel and ist_nachfahre(stapel[-1], route):
            stapel.pop()
        return [*stapel, route]
    if stapel and (ersetzen or geschwister(stapel[-1], route)):
        return [*stapel[:-1], route]
    return [*stapel, route][-MAX_STAPEL:]


__all__ = [
    "MAX_STAPEL",
    "geschwister",
    "ist_nachfahre",
    "naechster_stapel",
    "normal",
    "teile",
]
