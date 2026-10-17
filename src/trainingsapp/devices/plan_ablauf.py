"""Ein Plan als Ablauf, Teil einer Einheit (Ben, 17.10.2026; Skizzen 8–9).

Übung für Übung (`core.plan_durchlauf.Schritt`): Jede beginnt mit ``plan/uebung_start``
und — hat sie einen Timer — mit ihm, auf derselben Achse wie alles in der Einheit (ein
`TimerBaustein` je Übung, Bezug t0). Ist der Timer durch, endet die Übung
(``plan/uebung_ende``, Grund „fertig“); ohne Timer endet sie mit „Gemacht“. Danach wartet
der Ablauf auf „Weiter“ (``plan/pause`` — in der Messung ein Abschnitt „Pause“) oder geht
gleich weiter, wie am Plan eingestellt. Nach der letzten Übung kommt ``plan/ende``.

„Überspringen“ beendet eine Übung ohne Eintrag (Grund „uebersprungen“), „Abbrechen“ im
Timer ebenso (Grund „abgebrochen“). Eingetragen wird außerhalb (``ui``) — je Übung, sobald
sie endet, aus der Zeitleiste (`core.timer_eintrag`).

Die Einheit sieht den Timer der laufenden Übung als ihren (`Einheitslauf.timer`):
Laufleiste, ⏸ und Töne folgen ihm.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..core.einheit import Beteiligung, Ereignis, Rolle
from ..core.plan_durchlauf import Schritt
from ..core.timer import TimerLauf, TimerProfil
from .einheit import TimerBaustein

#: Wo der Ablauf steht
UEBUNG, PAUSE, FERTIG = "uebung", "pause", "fertig"


class PlanAblaufBaustein:
    """Der Ablauf eines Plans als Teil einer Einheit."""

    art = "plan"

    def __init__(
        self,
        plan_id: str,
        name: str,
        schritte: list[Schritt],
        *,
        weiter_automatisch: bool = False,
    ) -> None:
        if not schritte:
            raise ValueError("Ein Ablauf ohne Übung")
        self.plan_id = plan_id
        self.name = name
        self.schritte = schritte
        self.weiter_automatisch = weiter_automatisch
        #: die laufende (oder zuletzt gelaufene) Übung
        self.k = 0
        self.phase = UEBUNG
        #: der Timer der laufenden Übung — ``None`` ohne Timer
        self.timer: TimerBaustein | None = None
        #: je Planübung, wie sie endete: fertig, gemacht, uebersprungen, abgebrochen
        self.ergebnisse: dict[str, str] = {}
        self._uhr: Callable[[], float] = time.monotonic
        self._t0: float | None = None
        self._ausstehend: list[Ereignis] = []

    # -- Teil einer Einheit ------------------------------------------------------------

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        self._uhr = uhr

    @property
    def bereit(self) -> bool:
        return True

    def status(self) -> str:
        mit = sum(1 for s in self.schritte if s.profil is not None)
        return f"{len(self.schritte)} Übungen · {mit} mit Timer"

    @property
    def schritt(self) -> Schritt:
        return self.schritte[self.k]

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        self._beginnen(0, t0)
        return Beteiligung(
            "plan", Rolle.MITSTARTEN, daten={"plan": self.plan_id, "name": self.name}
        )

    def takt(self, jetzt: float) -> list[Ereignis]:
        out = self._abholen()
        if self.phase == UEBUNG and self.timer is not None:
            neu = self.timer.takt(jetzt)
            out += neu
            ende = next((x for x in neu if x.quelle == "timer" and x.art == "ende"), None)
            if ende is not None and self._t0 is not None:
                grund = "abgebrochen" if ende.daten.get("grund") == "abgebrochen" else "fertig"
                self._beenden(self._t0 + ende.t_s, grund)
                out += self._abholen()
        return out

    def beenden(self, jetzt: float) -> list[Ereignis]:
        """Die Einheit endet mitten im Ablauf: die laufende Übung endet ohne Eintrag."""
        out = self.takt(jetzt)
        if self.phase == UEBUNG and self._t0 is not None:
            if self.timer is not None:
                out += self.timer.beenden(jetzt)
            self._ausstehend.append(self._ende_ereignis(jetzt, "beendet"))
            self.ergebnisse.setdefault(self.schritt.item_id, "beendet")
            self.phase = FERTIG
        return out + self._abholen()

    async def abschliessen_async(self, stoppen: bool = True) -> PlanAblaufBaustein:
        return self

    # -- Bedienung (Oberfläche) -----------------------------------------------------------

    def weiter(self) -> None:
        """In der Pause: die nächste Übung beginnt jetzt."""
        if self.phase == PAUSE and self._t0 is not None:
            self._beginnen(self.k + 1, self._uhr())

    def gemacht(self) -> None:
        """Die laufende Übung ist fertig — mit Timer: jetzt ans Ende (die gelaufene Zeit
        zählt), ohne Timer: abgehakt."""
        if self.phase != UEBUNG or self._t0 is None:
            return
        if self.timer is not None:
            self.timer.lauf.fertig_machen()
        else:
            self._beenden(self._uhr(), "gemacht")

    def ueberspringen(self) -> None:
        """Die laufende Übung endet ohne Eintrag; die nächste beginnt (wie nach dem Timer)."""
        if self.phase != UEBUNG or self._t0 is None:
            return
        jetzt = self._uhr()
        if self.timer is not None:
            self._ausstehend += self.timer.beenden(jetzt)
        self._beenden(jetzt, "uebersprungen")

    # -- intern ---------------------------------------------------------------------------

    def _daten(self, s: Schritt) -> dict[str, Any]:
        daten: dict[str, Any] = {
            "uebung": s.uebung_id,
            "name": s.name,
            "plan": self.plan_id,
            "planuebung": s.item_id,
            "stelle": self.schritte.index(s) + 1,
        }
        if s.zeitfeld:
            daten["zeitfeld"] = s.zeitfeld
        return daten

    def _ende_ereignis(self, jetzt: float, grund: str) -> Ereignis:
        assert self._t0 is not None
        s = self.schritt
        return Ereignis(
            jetzt - self._t0,
            "plan",
            "uebung_ende",
            f"{s.name} fertig",
            {**self._daten(s), "grund": grund},
        )

    def _beginnen(self, k: int, bei: float) -> None:
        assert self._t0 is not None
        self.k, self.phase = k, UEBUNG
        s = self.schritt
        self._ausstehend.append(
            Ereignis(bei - self._t0, "plan", "uebung_start", f"{s.name} beginnt", self._daten(s))
        )
        self.timer = None
        if s.profil is not None:
            kopie = TimerProfil.aus_dict(s.profil.als_dict())
            assert kopie is not None
            self.timer = TimerBaustein(TimerLauf(kopie, uhr=self._uhr))
            self.timer.starten(self._t0, bei=bei)

    def _beenden(self, jetzt: float, grund: str) -> None:
        assert self._t0 is not None
        self._ausstehend.append(self._ende_ereignis(jetzt, grund))
        self.ergebnisse[self.schritt.item_id] = grund
        if self.k + 1 >= len(self.schritte):
            self.phase = FERTIG
            self._ausstehend.append(
                Ereignis(jetzt - self._t0, "plan", "ende", self.name, {"plan": self.plan_id})
            )
        elif self.weiter_automatisch:
            self._beginnen(self.k + 1, jetzt)
        else:
            self.phase = PAUSE
            self._ausstehend.append(
                Ereignis(jetzt - self._t0, "plan", "pause", "Pause", {"plan": self.plan_id})
            )

    def _abholen(self) -> list[Ereignis]:
        out, self._ausstehend = self._ausstehend, []
        return out


__all__ = ["FERTIG", "PAUSE", "UEBUNG", "PlanAblaufBaustein"]
