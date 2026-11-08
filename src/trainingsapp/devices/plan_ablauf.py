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

Ben, 18.10.2026: Nach einer Übung **ohne Timer** muss keine Pause kommen — „Gemacht“ war
schon der Tipp (``pause_ohne_timer``, am Plan eingestellt). Eine andere Übung lässt sich
jederzeit **wählen** (`waehlen`): Die laufende endet ohne Eintrag und bleibt offen (Grund
„gewechselt“), die Uhr läuft bei der gewählten — rückwärts mit Timer, vorwärts ohne
(`seit_s`). Danach geht es mit der ersten offenen Übung in der Reihenfolge des Plans
weiter (`naechster`).

Die Einheit sieht den Timer der laufenden Übung als ihren (`Einheitslauf.timer`):
Laufleiste, ⏸ und Töne folgen ihm.

**Gezeichneter Ablauf** (Ben, 8.11.2026 spät, `docs/plan_verzweigungen.md` §8, G2): Ist am
Plan der Reiter „Ablauf“ eingeschaltet (``ablauf.an``), folgt der Baustein den **Kanten**
(`core.ablauf`) statt der Planfolge: Start ist der Startknoten, nach jeder Übung nimmt er die
**reguläre** Kante (`core.ablauf.regulaere`: die erste erfüllte mit echtem Auslöser, sonst die
erste freie) — ist keine gangbar (Pflicht nicht erfüllt, Skala nicht gewählt), wartet er in der
Pause auf die Wahl; die Kanten stehen in der Ansicht als Knöpfe (`kante_gehen`). ``◀ zurück``
führt dorthin, wo man herkam (`verlauf`): zur unterbrochenen Übung noch einmal oder zu deren
nächster Kante. **Fragen** (Entscheidungsknoten) sind Schritte ohne Übung: ``plan/frage``,
die Antwort (`antworten`) ``plan/antwort``, dann die passende Kante von selbst. Jede genommene
Kante steht als ``plan/kante`` in der Zeitleiste (Auswertung). Ohne Ablauf ändert sich nichts.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..core import ablauf as ab
from ..core.bedingung import naechster_im_zweig
from ..core.einheit import (
    Beteiligung,
    Ereignis,
    Rolle,
    in_uebung,
    uebung_ende_text,
    uebung_start_text,
)
from ..core.plan_durchlauf import Schritt
from ..core.timer import TimerLauf, TimerProfil
from .einheit import TimerBaustein, uhr_angaben

#: Wo der Ablauf steht — ``UEBERZEIT``: der Timer ist ab, läuft aber weiter (weicher
#: Übergang, `docs/plan_workout.md`), bis „Weiter“
UEBUNG, PAUSE, FERTIG, UEBERZEIT = "uebung", "pause", "fertig", "ueberzeit"
#: Übergang im Workout: ``HART`` = nach dem Timer sofort weiter, ``WEICH`` = Überzeit bis
#: „Weiter“; ``None`` = der Ablauf wie bisher (Pause oder `weiter_automatisch`)
HART, WEICH = "hart", "weich"
#: Mit diesem Grund endet eine Übung, die offen bleibt — sie kommt später noch dran
GEWECHSELT = "gewechselt"


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
        pause_ohne_timer: bool = True,
        erste: str | None = None,
        uebergang: str | None = None,
        workout: bool = False,
        ablauf: ab.Ablauf | None = None,
    ) -> None:
        """``pause_ohne_timer``: nach einer Übung ohne Timer auf „Weiter“ warten (sonst gleich
        die nächste) — gilt nur, wenn nicht ohnehin ``weiter_automatisch``. ``erste``: die
        Planübung, mit der der Ablauf beginnt (sonst die erste).

        ``uebergang`` (Workout, 7.11.2026): `HART` — ist der Timer ab, beginnt sofort die
        nächste Übung (Schritte ohne Timer warten auf „Weiter“); `WEICH` — der Timer läuft
        über (`UEBERZEIT`, `TimerLauf.ueber_s`), die Übung endet erst mit „Weiter“, die
        Überzeit geht in den Eintrag (``ueber_s``). ``workout``: die Einheit bekommt die
        Klammer ``plan/start`` … ``plan/ende`` (Spur ``workout`` in der Messung).

        ``ablauf`` (G2): der gezeichnete Ablauf — nur mit ``an`` wirksam; dann bestimmen seine
        Kanten den Weg, ``erste`` geht vor seinem Startknoten."""
        if not schritte:
            raise ValueError("Ein Ablauf ohne Übung")
        if uebergang not in (None, HART, WEICH):
            raise ValueError(f"Unbekannter Übergang: {uebergang!r}")
        self.plan_id = plan_id
        self.name = name
        self.schritte = schritte
        self.uebergang = uebergang
        self.workout = workout
        self.weiter_automatisch = weiter_automatisch or uebergang == HART
        self.pause_ohne_timer = pause_ohne_timer if uebergang is None else False
        #: der gezeichnete Ablauf — ``None``: die Planfolge mit ihren Bedingungen (W2–W4)
        self.ablauf = ablauf if ablauf is not None and ablauf.an else None
        #: die laufende (oder zuletzt gelaufene) Übung
        self.k = next((i for i, s in enumerate(schritte) if s.item_id == erste), 0)
        if erste is None and self.ablauf is not None and self.ablauf.start:
            # Der Startknoten — fehlt er unter den Schritten (heute schon gemacht, Übung im
            # Papierkorb), beginnt es dort, wohin seine erste Kante führt
            start = self._ziel(self.ablauf.start)
            self.k = start if start is not None else 0
        #: die Schritte in der Reihenfolge, in der sie liefen (Index je Durchlauf) — für
        #: ``◀ zurück`` und die Zählung der Durchläufe
        self.verlauf: list[int] = []
        #: die Selbsteinschätzung im laufenden Schritt (Skala-Kanten, Fragen) — je Durchlauf
        self.skala_wert: float | None = None
        #: was der Zähl-Teil im laufenden Schritt zählte — setzt die Ansicht (`wdh_setzen`)
        self._wdh: int | None = None
        #: das Ende des Workouts ist über eine Kante gewählt
        self._ende_gewollt = False
        self.phase = UEBUNG
        #: der Timer der laufenden Übung — ``None`` ohne Timer
        self.timer: TimerBaustein | None = None
        #: Beginn der laufenden Übung auf der Achse der Einheit — der Anfang ihrer Uhr dort
        #: bekommt keine eigene Notiz (`core.einheit.in_uebung`)
        self._start_t_s: float | None = None
        #: je Planübung, wie sie endete: fertig, gemacht, uebersprungen, abgebrochen, beendet
        self.ergebnisse: dict[str, str] = {}
        #: Planübungen, die schon liefen und für eine andere verlassen wurden (`waehlen`)
        self.unterbrochen: set[str] = set()
        self._uhr: Callable[[], float] = time.monotonic
        self._t0: float | None = None
        #: „Fertig“ gedrückt: das Timer-Ende beendet die Übung auch im weichen Übergang
        self._fertig_gewollt = False
        #: seit wann die laufende Übung bzw. die Pause läuft (Uhr des Ablaufs)
        self._seit: float | None = None
        self._ausstehend: list[Ereignis] = []

    # -- Teil einer Einheit ------------------------------------------------------------

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        self._uhr = uhr

    @property
    def bereit(self) -> bool:
        return True

    def status(self) -> str:
        uebungen = [s for s in self.schritte if s.frage is None]
        mit = sum(1 for s in uebungen if s.profil is not None)
        return f"{len(uebungen)} Übungen · {mit} mit Timer"

    # -- Gezeichneter Ablauf (G2) ----------------------------------------------------------

    @property
    def durchlauf(self) -> int:
        """Der wievielte Durchlauf des laufenden Schritts das ist (Schleifen: „2. Durchlauf“)."""
        return sum(1 for k in self.verlauf if k == self.k)

    def wdh_setzen(self, wdh: int | None) -> None:
        """Die Ansicht sagt je Takt, was der Zähl-Teil im Schritt zählte (für ``wdh``-Kanten)."""
        self._wdh = wdh

    def _zeit_ab(self) -> bool:
        if self.phase in (UEBERZEIT, PAUSE):
            return True
        return self.timer is not None and self.timer.lauf.fertig

    def kanten_stand(self) -> list[ab.KanteStand]:
        """Die Kanten aus dem laufenden Knoten gegen den Stand — leer ohne Ablauf."""
        if self.ablauf is None:
            return []
        return ab.kanten_pruefen(
            self.ablauf.von(self.schritt.item_id),
            zeit_ab=self._zeit_ab(),
            wdh=self._wdh,
            skala=self.skala_wert,
        )

    def kante_ziel(self, kante: ab.Kante) -> int | None:
        """Wohin eine Kante führt — der Index des Schritts, ``None`` fürs Ende. ``◀ zurück``
        löst sich über den Verlauf auf: zur unterbrochenen Übung (``wiederholen``) oder zu
        deren nächster Kante, die nicht hierher führt."""
        if kante.zum_ende:
            return None
        if not kante.zurueck:
            return self._ziel(kante.nach)
        return self._zurueck(len(self.verlauf) - 1, kante.wiederholen)

    def hat(self, knoten: str) -> bool:
        """Läuft dieser Knoten in diesem Workout mit (nicht heute ausgelassen)?"""
        return self._index(knoten) is not None

    def _ziel(self, knoten: str, gesehen: frozenset[str] = frozenset()) -> int | None:
        """Der Index von ``knoten`` — ``None`` heißt Ende. Fehlt er unter den Schritten (heute
        schon gemacht und abgewählt, Übung im Papierkorb), geht es **durch ihn hindurch**:
        über seine erste Kante, die nicht auf ihn selbst zeigt; ohne Kante ist es das Ende."""
        k = self._index(knoten)
        if k is not None or self.ablauf is None or knoten in gesehen:
            return k
        for kante in self.ablauf.von(knoten):
            if kante.schleife:
                continue
            if kante.zum_ende:
                return None
            if kante.zurueck:
                # Zurück aus einem ausgelassenen Knoten: zur laufenden Übung (noch einmal)
                # oder zu deren nächster Kante, die nicht in den ausgelassenen führt
                if kante.wiederholen:
                    return self.k
                fort = [
                    x
                    for x in self.ablauf.von(self.schritt.item_id)
                    if x.nach not in (knoten, self.schritt.item_id) and not x.zurueck
                ]
                if not fort or fort[0].zum_ende:
                    return None
                return self._ziel(fort[0].nach, gesehen | {knoten})
            return self._ziel(kante.nach, gesehen | {knoten})
        return None

    def _zurueck(self, pos: int, wiederholen: bool) -> int | None:
        """Von der Stelle ``pos`` im Verlauf einen Schritt zurück (höchstens so viele Stufen,
        wie der Verlauf lang ist — ein ``zurück`` im ``zurück`` wandert weiter)."""
        hier = self.verlauf[pos] if 0 <= pos < len(self.verlauf) else self.k
        for p in range(pos - 1, -1, -1):
            vorher = self.verlauf[p]
            if vorher == hier:
                continue
            if wiederholen:
                return vorher
            assert self.ablauf is not None
            fort = [
                k
                for k in self.ablauf.von(self.schritte[vorher].item_id)
                if k.nach != self.schritte[hier].item_id
            ]
            if not fort or fort[0].zum_ende:
                return None
            if fort[0].zurueck:
                hier, wiederholen = vorher, fort[0].wiederholen
                continue
            return self._ziel(fort[0].nach)
        return None

    def _index(self, item_id: str) -> int | None:
        return next((i for i, s in enumerate(self.schritte) if s.item_id == item_id), None)

    def _regulaere_kante(self) -> ab.KanteStand | None:
        return ab.regulaere(self.kanten_stand())

    def antworten(self, wert: float) -> None:
        """Die Selbsteinschätzung im Schritt (Skala-Kante oder Frage). Bei einer Frage geht
        es danach von selbst die passende Kante; eine Kante mit ``ausfuehren`` ebenso, sobald
        der Timer ab ist (`takt`)."""
        self.skala_wert = wert
        if self._t0 is None or self.ablauf is None or self.phase == FERTIG:
            return
        if self.schritt.frage is not None:
            stand = self._regulaere_kante()
            if stand is not None:
                self.kante_gehen(stand.kante)
            return
        self._auto_kanten()

    def kante_gehen(self, kante: ab.Kante) -> None:
        """Diese Kante nehmen — aus der Übung (sie endet als fertig), der Überzeit oder der
        Pause; fürs Ende endet das Workout. Steht in der Zeitleiste als ``plan/kante``."""
        if self._t0 is None or self.phase == FERTIG:
            return
        jetzt = self._uhr()
        ziel = self.kante_ziel(kante)
        self._ausstehend.append(
            Ereignis(
                jetzt - self._t0,
                "plan",
                "kante",
                kante.text or kante.ausloeser_text(),
                {
                    "plan": self.plan_id,
                    "planuebung": self.schritt.item_id,
                    "von": self.schritt.item_id,
                    "nach": self.schritte[ziel].item_id if ziel is not None else ab.ENDE,
                    "kante": kante.text,
                },
            )
        )
        if ziel is None:
            self._ende_gewollt = True
        if self.phase == PAUSE:
            if ziel is None:
                self.phase = FERTIG
                self._ausstehend.append(self._plan_ende(jetzt))
            else:
                self._beginnen(ziel, jetzt)
            return
        if self.phase == UEBUNG and self.timer is not None:
            self._ausstehend += self._uebungs_timer(self.timer.beenden(jetzt))
        grund = "fertig" if self.schritt.frage is None else "beantwortet"
        self._beenden(jetzt, grund, self.schritte[ziel].item_id if ziel is not None else None)

    def _auto_kanten(self) -> None:
        """Kanten mit ``ausfuehren``, die erfüllt sind, gehen von selbst — im harten Übergang
        sofort (der Schritt endet als fertig, auch mitten im Timer), im weichen erst, wenn der
        Timer ab ist (P109: die App schubst niemanden, `docs/plan_verzweigungen.md` §3.2)."""
        if self.ablauf is None or self.phase not in (UEBUNG, UEBERZEIT, PAUSE):
            return
        timer_laeuft = (
            self.phase == UEBUNG and self.timer is not None and not self.timer.lauf.fertig
        )
        if timer_laeuft and not self.weiter_automatisch:
            return
        for st in self.kanten_stand():
            if st.gangbar and st.kante.ausfuehren and st.kante.ausloeser != ab.FREI:
                self.kante_gehen(st.kante)
                return

    @property
    def schritt(self) -> Schritt:
        return self.schritte[self.k]

    def offen(self, item_id: str) -> bool:
        """Kommt diese Planübung noch dran? (Eine gewechselte ja, eine beendete nicht.)"""
        return item_id not in self.ergebnisse

    @property
    def naechster(self) -> int | None:
        """Die Übung nach der laufenden auf dem **erfüllt**-Weg: ``dann`` der Bedingung, sonst
        die nächste offene im eigenen Zweig, sonst die erste offene im Hauptzweig (W3,
        `core.bedingung.naechster_im_zweig`) — ``None``, wenn keine mehr offen ist."""
        if self.ablauf is not None:
            st = self._regulaere_kante()
            return self.kante_ziel(st.kante) if st is not None else None
        return self.ziel_index(self.schritt.bedingung.dann)

    def ziel_index(self, item_id: str | None) -> int | None:
        """Der Index von ``item_id`` — ein ausdrücklicher Verweis (``dann``, ``sonst``, ein Weg)
        gilt auch zu einer schon gemachten Übung und zum laufenden Schritt selbst (Schleife:
        Wandsitz, Pause, Wandsitz … — Ben, 8.11.2026); ohne Verweis der Weg der Zweige."""
        if item_id:
            k = next((i for i, s in enumerate(self.schritte) if s.item_id == item_id), None)
            if k is not None:
                return k
        folge = [(s.item_id, s.bedingung.zweig) for s in self.schritte]
        offen = {s.item_id for s in self.schritte if self.offen(s.item_id)} - {self.schritt.item_id}
        ziel = naechster_im_zweig(folge, self.schritt.item_id, offen)
        return next((i for i, s in enumerate(self.schritte) if s.item_id == ziel), None)

    @property
    def start_t_s(self) -> float | None:
        """Beginn der laufenden Übung auf der Achse der Einheit — je Durchlauf neu (Schleifen)."""
        return self._start_t_s

    def seit_s(self) -> float:
        """Wie lange die laufende Übung (oder die Pause) schon dauert — ohne Timer läuft
        diese Uhr vorwärts (Ben, 18.10.2026)."""
        if self._seit is None or self.phase == FERTIG:
            return 0.0
        return max(0.0, self._uhr() - self._seit)

    def ueber_s(self) -> float:
        """Sekunden über dem Timer-Ende in der Überzeit (weicher Übergang) — sonst 0."""
        if self.phase != UEBERZEIT or self.timer is None:
            return 0.0
        return self.timer.lauf.ueber_s()

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        if self.workout:
            # Die Klammer des Workouts — vor der ersten Übung (`core.einheit.projektion`)
            self._ausstehend.append(
                Ereignis(0.0, "plan", "start", self.name, {"plan": self.plan_id, "workout": True})
            )
        self._beginnen(self.k, t0)
        return Beteiligung(
            "plan", Rolle.MITSTARTEN, daten={"plan": self.plan_id, "name": self.name}
        )

    def takt(self, jetzt: float) -> list[Ereignis]:
        out = self._abholen()
        if self.phase == UEBUNG and self.timer is not None:
            neu = self._uebungs_timer(self.timer.takt(jetzt))
            out += neu
            ende = next((x for x in neu if x.quelle == "timer" and x.art == "ende"), None)
            if ende is not None and self._t0 is not None:
                if ende.daten.get("grund") == "abgebrochen":
                    self._beenden(self._t0 + ende.t_s, "abgebrochen")
                elif (
                    self.uebergang == WEICH
                    and not self._fertig_gewollt
                    and self._weiter_trainierbar()
                ):
                    # Weich: der Timer läuft über, die Übung endet erst mit „Weiter“
                    self.phase = UEBERZEIT
                else:
                    self._beenden(self._t0 + ende.t_s, "fertig")
                out += self._abholen()
        self._auto_kanten()
        return out + self._abholen()

    def _weiter_trainierbar(self) -> bool:
        """Überzeit lohnt nur, wenn der Timer noch läuft (nicht „Gemacht“ oder angehalten)."""
        return self.timer is not None and self.timer.lauf.laeuft_roh

    def beenden(self, jetzt: float) -> list[Ereignis]:
        """Die Einheit endet mitten im Ablauf: die laufende Übung endet ohne Eintrag."""
        out = self.takt(jetzt)
        if self.phase == UEBERZEIT and self._t0 is not None:
            # Weich und die Einheit endet: die Übung war fertig — eintragen, mit Überzeit
            self._ende_eintragen(jetzt, "fertig")
        elif self.phase == UEBUNG and self._t0 is not None:
            if self.timer is not None:
                out += self._uebungs_timer(self.timer.beenden(jetzt))
            self._ausstehend.append(self._ende_ereignis(jetzt, "beendet"))
            self.ergebnisse.setdefault(self.schritt.item_id, "beendet")
            self.phase = FERTIG
        if self.phase != FERTIG and self._t0 is not None:
            self.phase = FERTIG
            self._ausstehend.append(self._plan_ende(jetzt))
        return out + self._abholen()

    async def abschliessen_async(self, stoppen: bool = True) -> PlanAblaufBaustein:
        return self

    # -- Bedienung (Oberfläche) -----------------------------------------------------------

    def weiter(self, ziel: str | None = None) -> None:
        """In der Pause: die nächste Übung beginnt jetzt. In der Überzeit (weich): die
        laufende Übung endet als fertig — mit Überzeit —, die nächste beginnt. ``ziel``
        (W3): diese Planübung statt des erfüllt-Wegs — der ``sonst``-Zweig oder „trotzdem
        weiter“ aus der Ansicht."""
        if self._t0 is None:
            return
        jetzt = self._uhr()
        if self.phase == UEBERZEIT:
            self._beenden(jetzt, "fertig", ziel)
            return
        if self.phase == UEBUNG and ziel:
            # Zweig oder „trotzdem weiter“ mitten in der Übung (W3): sie endet als fertig
            if self.timer is not None:
                self._ausstehend += self._uebungs_timer(self.timer.beenden(jetzt))
            self._beenden(jetzt, "fertig", ziel)
            return
        if self.phase == PAUSE:
            gezeichnet = self.ablauf is not None and not ziel
            n = self.naechster if gezeichnet else self.ziel_index(ziel)
            if n is not None:
                self._beginnen(n, jetzt)

    def wiederholen(self) -> None:
        """„Noch einmal versuchen“ (W3): die laufende Übung endet ohne Eintrag und bleibt
        offen (Grund „gewechselt“), dann beginnt sie von vorn."""
        if self.phase not in (UEBUNG, UEBERZEIT) or self._t0 is None:
            return
        jetzt = self._uhr()
        if self.timer is not None and self.phase == UEBUNG:
            self._ausstehend += self._uebungs_timer(self.timer.beenden(jetzt))
        self._ausstehend.append(self._ende_ereignis(jetzt, GEWECHSELT))
        self.unterbrochen.add(self.schritt.item_id)
        self._beginnen(self.k, jetzt)

    def waehlen(self, item_id: str) -> bool:
        """Jetzt diese Übung (Ben, 18.10.2026: „Eine Übung ist ausgewählt, die Uhr läuft …
        immer dort, wo die Kachel gerade aktiviert ist“). Die laufende endet ohne Eintrag
        und bleibt offen (Grund „gewechselt“), ihr Timer endet; aus der Pause beginnt die
        gewählte sofort.

        Returns:
            ``False``, wenn es nicht geht: der Ablauf ist fertig, die Übung schon erledigt
            oder unbekannt — oder sie läuft gerade.
        """
        if self._t0 is None or self.phase == FERTIG:
            return False
        jetzt = self._uhr()
        if self.phase == UEBUNG and self.timer is not None and self.timer.lauf.fertig:
            # Der Timer ist schon durch (oder „Gemacht“ setzte ihn ans Ende), der Takt hat es
            # nur noch nicht gesehen: erst das Ende auswerten — die Übung ist fertig und wird
            # eingetragen, nicht „gewechselt“. Was dabei anfällt, holt der nächste Takt ab.
            self._ausstehend = self.takt(jetzt)
            if self.phase == FERTIG:
                return False
        k = next((i for i, s in enumerate(self.schritte) if s.item_id == item_id), None)
        if k is None or not self.offen(item_id) or (self.phase != PAUSE and k == self.k):
            return False
        if self.phase == UEBERZEIT:
            # Weich: die laufende war fertig — eintragen, dann die gewählte
            self._ende_eintragen(jetzt, "fertig")
        elif self.phase == UEBUNG:
            if self.timer is not None:
                self._ausstehend += self._uebungs_timer(self.timer.beenden(jetzt))
            self._ausstehend.append(self._ende_ereignis(jetzt, GEWECHSELT))
            self.unterbrochen.add(self.schritt.item_id)
        self._beginnen(k, jetzt)
        return True

    def gemacht(self) -> None:
        """Die laufende Übung ist fertig — mit Timer: jetzt ans Ende (die gelaufene Zeit
        zählt), ohne Timer: abgehakt."""
        if self._t0 is None:
            return
        if self.phase == UEBERZEIT:
            self._beenden(self._uhr(), "fertig")
        elif self.phase == UEBUNG and self.timer is not None:
            self._fertig_gewollt = True
            self.timer.lauf.fertig_machen()
        elif self.phase == UEBUNG:
            self._beenden(self._uhr(), "gemacht")

    def ueberspringen(self) -> None:
        """Die laufende Übung endet ohne Eintrag; die nächste beginnt (wie nach dem Timer)."""
        if self.phase not in (UEBUNG, UEBERZEIT) or self._t0 is None:
            return
        jetzt = self._uhr()
        if self.phase == UEBUNG and self.timer is not None:
            self._ausstehend += self._uebungs_timer(self.timer.beenden(jetzt))
        self._beenden(jetzt, "uebersprungen")

    # -- intern ---------------------------------------------------------------------------

    def _uebungs_timer(self, ereignisse: list[Ereignis]) -> list[Ereignis]:
        """Die Ereignisse des Timers der laufenden Übung nennen sie (P54) — hier, solange
        sie läuft, nicht erst in der Einheit: Im selben Takt kann schon die nächste beginnen."""
        s = self.schritt
        return [in_uebung(e, s.uebung_id, s.name, start_t_s=self._start_t_s) for e in ereignisse]

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
        daten = {**self._daten(s), "grund": grund}
        if s.frage is not None:
            # Eine Frage endet ohne Übungseintrag — die Zeitleiste merkt sich die Antwort
            daten["frage"] = s.frage.text
            if self.skala_wert is not None:
                daten["wert"] = self.skala_wert
            wert = f"{self.skala_wert:g}" if self.skala_wert is not None else "ohne Antwort"
            return Ereignis(jetzt - self._t0, "plan", "antwort", f"{s.name}: {wert}", daten)
        if (ueber := self.ueber_s()) > 0:
            daten["ueber_s"] = round(ueber, 1)  # weich: die Überzeit geht in den Eintrag
        return Ereignis(jetzt - self._t0, "plan", "uebung_ende", uebung_ende_text(s.name), daten)

    def _plan_ende(self, jetzt: float) -> Ereignis:
        assert self._t0 is not None
        daten: dict[str, Any] = {"plan": self.plan_id}
        if self.workout:
            daten["workout"] = True
        return Ereignis(jetzt - self._t0, "plan", "ende", self.name, daten)

    def _ende_eintragen(self, jetzt: float, grund: str) -> None:
        """Die laufende Übung endet mit ``grund``, ohne dass der Ablauf weitergeht (die
        nächste Übung bestimmt der Aufrufer — `waehlen`)."""
        self._ausstehend.append(self._ende_ereignis(jetzt, grund))
        self.ergebnisse[self.schritt.item_id] = grund
        self.unterbrochen.discard(self.schritt.item_id)
        self.timer = None

    def _beginnen(self, k: int, bei: float) -> None:
        assert self._t0 is not None
        self.k, self.phase = k, UEBUNG
        self._fertig_gewollt = False
        self._seit = bei
        self._start_t_s = bei - self._t0
        self.verlauf.append(k)
        self.skala_wert = None
        self._wdh = None
        s = self.schritt
        self.timer = None
        daten = self._daten(s)
        if s.frage is not None:
            # Ein Entscheidungsknoten: fragt nur, verzweigt mit der Antwort (`antworten`)
            daten["frage"] = s.frage.text
            self._ausstehend.append(Ereignis(self._start_t_s, "plan", "frage", s.frage.text, daten))
            return
        if s.profil is not None:
            kopie = TimerProfil.aus_dict(s.profil.als_dict())
            assert kopie is not None
            self.timer = TimerBaustein(TimerLauf(kopie, uhr=self._uhr))
            self.timer.starten(self._t0, bei=bei)
            # Der Anfang der Uhr wird still — die Startnotiz der Übung trägt ihre Angaben
            daten.update(uhr_angaben(self.timer.lauf))
        self._ausstehend.append(
            Ereignis(self._start_t_s, "plan", "uebung_start", uebung_start_text(s.name), daten)
        )

    def _beenden(self, jetzt: float, grund: str, ziel: str | None = None) -> None:
        assert self._t0 is not None
        ohne_timer = self.schritt.profil is None
        warten = False
        if self.ablauf is None:
            naechster = self.ziel_index(ziel) if ziel else self.naechster
        elif self._ende_gewollt:
            naechster = None
        elif ziel:
            naechster = self._index(ziel)
        else:
            # Gezeichneter Ablauf: die reguläre Kante — gibt es Kanten, aber keine gangbare
            # (Pflicht offen, Skala nicht gewählt), wartet der Baustein in der Pause auf die Wahl
            st = self._regulaere_kante()
            naechster = self.kante_ziel(st.kante) if st is not None else None
            warten = st is None and bool(self.ablauf.von(self.schritt.item_id))
        self._ende_eintragen(jetzt, grund)  # in der Pause gibt es keinen Timer (Laufleiste, ⏸)
        self._ende_gewollt = False
        if warten:
            self.phase = PAUSE
            self._seit = jetzt
            self._ausstehend.append(
                Ereignis(jetzt - self._t0, "plan", "pause", "Pause", {"plan": self.plan_id})
            )
        elif naechster is None:
            self.phase = FERTIG
            self._ausstehend.append(self._plan_ende(jetzt))
        elif (
            self.weiter_automatisch
            or self.uebergang is not None  # Workout: weich wartet in der Überzeit, nie in der Pause
            or (ohne_timer and not self.pause_ohne_timer)
        ):
            self._beginnen(naechster, jetzt)
        else:
            self.phase = PAUSE
            self._seit = jetzt
            self._ausstehend.append(
                Ereignis(jetzt - self._t0, "plan", "pause", "Pause", {"plan": self.plan_id})
            )

    def _abholen(self) -> list[Ereignis]:
        out, self._ausstehend = self._ausstehend, []
        return out


__all__ = [
    "FERTIG",
    "GEWECHSELT",
    "HART",
    "PAUSE",
    "UEBERZEIT",
    "UEBUNG",
    "WEICH",
    "PlanAblaufBaustein",
]
