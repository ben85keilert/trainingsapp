"""Die Herzfrequenz der laufenden Messung für **beide** Ansichten — hochkant (`views.messung`)
und im Vollbild (`views.hf_vollbild`): Werte, Kurve, Zielbereich mit Ton, Erholung, Marken
(Ben, 10.11.2026, A22; Vertrag `docs/plan_hf_vollbild.md`).

Kein Bild, keine Rechnung: gerechnet wird in `hrv_core.herzfrequenz`, `core.hf_training` und
`core.hf_ziel`; hier steht nur, woher die Werte des Messlaufs kommen und wohin Marken und
Töne gehen. Was den Neuaufbau einer Ansicht überleben muss (Akkumulatoren, laufende
Erholung, Tonfolge, Stumm, Ablese-Intervall), liegt im `AppState`.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_einstellungen import HfEinstellungen
from trainingsapp.core.hf_profil import bereiche_fuer, grenzen_bpm
from trainingsapp.core.hf_training import (
    BEZUG_ABSCHNITT,
    BEZUG_AUFNAHME,
    BEZUG_FENSTER,
    BEZUG_NAMEN,
    LiveHf,
    fenster_zusammenfassung,
    hf_je_schlag,
)
from trainingsapp.core.hf_ziel import (
    Stumm,
    Zielton,
    trend_bpm_min,
    ziel_grenzen,
    ziel_setzen,
)

#: So oft werden die Einstellungen frisch gelesen (s) — Blatt und Einstellungsseite ändern sie
_EINST_TAKT_S = 5.0
#: DFA α1 ist teuer — höchstens so oft (s)
_DFA_TAKT_S = 10.0


#: So alt darf der letzte Schlag sein, damit seine Herzfrequenz noch als „jetzt“ gilt
HF_FRISCH_S = 10.0


class HfLive:
    """Herzfrequenz-Werte eines Messlaufs — eine Instanz je Ansicht, der Zustand im State."""

    def __init__(self, page: Any, state: Any, lauf: Any) -> None:
        self.page, self.state, self.lauf = page, state, lauf
        self.profil = state.hf_profil()
        self.bereiche = bereiche_fuer(self.profil, state.hf_einstellungen())
        self.grenzen = grenzen_bpm(self.bereiche)
        schluessel = (
            state.profil.id,
            self.profil.ruhe_bpm,
            self.profil.hfmax_bpm,
            tuple(self.grenzen),
            self.profil.geschlecht,
        )
        if state.live_hf is None or state.live_hf_schluessel != schluessel:
            state.live_hf = LiveHf(self.profil, self.grenzen)
            state.live_hf_schluessel = schluessel
        self.live_hf: LiveHf = state.live_hf
        if state.hf_zielton is None:
            state.hf_zielton = Zielton()
        self._einst: HfEinstellungen | None = None
        self._einst_gelesen = 0.0
        self._dfa: tuple[float, float | None] = (-1e9, None)

    # -- Einstellungen ------------------------------------------------------------------

    def einst(self, *, frisch: bool = False) -> HfEinstellungen:
        """Die HF-Einstellungen des Profils — alle paar Sekunden neu gelesen."""
        jetzt = time.monotonic()
        if frisch or self._einst is None or jetzt - self._einst_gelesen > _EINST_TAKT_S:
            self._einst = self.state.hf_einstellungen()
            self._einst_gelesen = jetzt
        return self._einst

    def einst_speichern(self, e: HfEinstellungen) -> None:
        self.state.hf_einstellungen_setzen(e)
        self._einst, self._einst_gelesen = e, time.monotonic()

    # -- Werte --------------------------------------------------------------------------

    def punkte(self, seit_s: float) -> list[tuple[float, float, float, bool]]:
        """``(t, rr_ms, hf_bpm, ungültig)`` der Schläge im Live-Puffer ab ``seit_s``."""
        return [
            (p.t_s, float(p.rr_ms), float(p.hf_bpm), p.artefakt or p.verworfen)
            for p in self.lauf.live.punkte(seit_s=seit_s)
        ]

    def hf_jetzt(self) -> float | None:
        """Die Herzfrequenz der letzten 5 s aus RR (bpm-Rückfall) — sonst die des Geräts."""
        jetzt = self.lauf.jetzt_s()
        werte = [
            w
            for _, rr, hf, art in self.punkte(jetzt - 5.0)
            if (w := hf_je_schlag(0.0 if art else rr, hf)) is not None
        ]
        if werte:
            return sum(werte) / len(werte)
        k = self.lauf.live.kennzahlen()
        if k.hf_bpm:
            # Der letzte Wert des Puffers — nur, solange er frisch ist: Nach Funkstille (Gurt
            # verrutscht, Verbindung im Wiederaufbau) stünde sonst eine alte Zahl ohne
            # Kennzeichen da, und der Zielton klänge dazu weiter (H77)
            return float(k.hf_bpm) if self.punkte(jetzt - HF_FRISCH_S) else None
        return float(self.lauf.status.hf_bpm) if self.lauf.status.hf_bpm else None

    def reihe(self, seit_s: float) -> hz.HfReihe:
        """Die HF im Sekundenraster ab ``seit_s`` (`hz.hf_reihe`) — leer ohne Schläge."""
        roh = self.punkte(seit_s)
        if not roh:
            return hz.hf_reihe([], [], anfang=seit_s, ende=seit_s + 1.0)
        return hz.hf_reihe(
            [p[0] for p in roh],
            [p[1] for p in roh],
            [p[2] for p in roh],
            artefakt=[p[3] for p in roh],
        )

    def kurvenpunkte(
        self, x_von: float, x_bis: float, mittel_s: float
    ) -> list[tuple[float, float]]:
        """Die Kurve der Herzfrequenz: Mittel über ``mittel_s`` aus RR (bpm-Rückfall); sendet
        das Gerät keine Schläge, seine eigene Herzfrequenz."""
        roh = self.punkte(x_von - mittel_s - 5.0)
        if not roh:
            return [(t, h) for t, h in self.lauf.live.hf_reihe() if x_von <= t <= x_bis]
        reihe = hz.hf_reihe(
            [p[0] for p in roh],
            [p[1] for p in roh],
            [p[2] for p in roh],
            artefakt=[p[3] for p in roh],
        )
        glatt = hz.rollmittel(reihe.hf, mittel_s, min_anteil=0.5)
        return [
            (float(t) + 1.0, float(w))
            for t, w in zip(reihe.t, glatt, strict=True)
            if w == w and x_von <= t + 1.0 <= x_bis
        ]

    def live_werte(self) -> tuple[float | None, dict[str, Any] | None, str, bool]:
        """``(HF, Zusammenfassung des Bezugs, Name des Bezugs, Abschnitt läuft?)``."""
        lauf, state = self.lauf, self.state
        jetzt = lauf.jetzt_s()
        abschnitt_laeuft = False
        if lauf.aufnahme is not None:
            kennung = getattr(lauf.aufnahme, "start_mono", None)
            self.live_hf.nachfuehren(lauf.aufnahme.beats, kennung)
            offen = lauf.offener_abschnitt()
            if offen is not None:
                von = next((a.von_s for a in lauf.abschnitte() if a.id == offen[0]), None)
                if von is not None:
                    self.live_hf.abschnitt_setzen(offen[0], von, lauf.aufnahme.beats)
                    abschnitt_laeuft = True
            if not abschnitt_laeuft:
                self.live_hf.abschnitt_setzen(None, 0.0, [])
        bezug = state.hf_bezug
        if bezug == BEZUG_ABSCHNITT and not abschnitt_laeuft:
            bezug = BEZUG_AUFNAHME
        if bezug == BEZUG_AUFNAHME and lauf.aufnahme is None:
            bezug = BEZUG_FENSTER
        zus: dict[str, Any] | None
        if bezug == BEZUG_FENSTER:
            punkte = [(t, rr, hf) for t, rr, hf, art in self.punkte(jetzt - 300.0) if not art]
            zus = fenster_zusammenfassung(punkte, self.profil, self.grenzen, jetzt)
        else:
            akk = self.live_hf.fuer(bezug)
            zus = akk.zusammenfassung() if akk is not None else None
        return self.hf_jetzt(), zus, BEZUG_NAMEN[bezug], abschnitt_laeuft

    def trend(self) -> float | None:
        """Steigung der letzten Minute in bpm/min (`core.hf_ziel.trend_bpm_min`)."""
        jetzt = self.lauf.jetzt_s()
        return trend_bpm_min(self.kurvenpunkte(jetzt - 62.0, jetzt, 5.0), jetzt)

    def drift(self) -> float | None:
        """Drift des laufenden Abschnitts in bpm (zweite gegen erste Hälfte, `hz.drift`) — None
        ohne offenen Abschnitt oder wenn er kürzer als zwei Minuten ist."""
        lauf = self.lauf
        offen = lauf.offener_abschnitt() if lauf.aufnahme is not None else None
        if offen is None:
            return None
        von = next((a.von_s for a in lauf.abschnitte() if a.id == offen[0]), None)
        jetzt = lauf.jetzt_s()
        if von is None or jetzt - von < 120.0:
            return None
        return hz.drift(self.reihe(von), von, jetzt).differenz_bpm

    def dfa_a1(self) -> float | None:
        """DFA α1 der letzten zwei Minuten — nur die Zahl, höchstens alle 10 s gerechnet."""
        jetzt = time.monotonic()
        if jetzt - self._dfa[0] > _DFA_TAKT_S:
            wert = None
            with contextlib.suppress(Exception):
                wert = self.lauf.live.dfa_a1()
            self._dfa = (jetzt, wert)
        return self._dfa[1]

    # -- Zielbereich und Ton --------------------------------------------------------------

    def _messung(self) -> int:
        """Kennung der laufenden Messung — „stumm bis Messende“ gilt, solange sie bleibt."""
        return id(self.lauf.aufnahme) if self.lauf.aufnahme is not None else id(self.lauf)

    def stumm(self) -> Stumm | None:
        s: Stumm | None = self.state.hf_stumm
        if s is not None and not s.gilt(time.monotonic(), self._messung()):
            self.state.hf_stumm = s = None
        return s

    def stumm_setzen(self, dauer_s: float | None) -> None:
        """Für ``dauer_s`` Sekunden schweigen (`BIS_MESSENDE`: bis die Messung endet); None
        hebt es auf."""
        self.state.hf_stumm = (
            None
            if dauer_s is None
            else Stumm(bis=time.monotonic() + dauer_s, messung=self._messung())
        )

    def ton_pruefen(self, hf: float | None) -> None:
        """Den Ton außerhalb des Zielbereichs spielen, wenn er fällig ist
        (`core.hf_ziel.Zielton`)."""
        klang = self.state.hf_zielton.faellig(
            hf, self.einst(), time.monotonic(), stumm=self.stumm() is not None
        )
        if klang is not None:
            self.klang_spielen(klang)

    def klang_spielen(self, klang: str) -> None:
        from trainingsapp.ui.timer_takt import ton_spielen

        with contextlib.suppress(Exception):
            self.page.run_task(ton_spielen, self.state, klang)

    def ziel_aendern(
        self, *, oben: float | None = None, unten: float | None = None, an: bool | None = None
    ) -> HfEinstellungen:
        """Linien des Zielbereichs und den Schalter des Tons setzen und speichern."""
        e = self.einst(frisch=True)
        ziel_setzen(e, oben=oben, unten=unten)
        if an is not None:
            e.alarm_an = an
        self.einst_speichern(e)
        return e

    def ziel_schritt(self, seite: str, schritt: float) -> HfEinstellungen:
        """Eine Linie (``"oben"``/``"unten"``) um ``schritt`` bpm rücken — ohne Linie beginnt
        sie beim Bereich, in dem die Herzfrequenz gerade liegt, sonst bei der anderen Linie."""
        e = self.einst(frisch=True)
        oben, unten = ziel_grenzen(e)
        hf = self.hf_jetzt()
        if seite == "oben":
            start = oben if oben is not None else (unten + 20 if unten else (hf or 140.0) + 10)
            return self.ziel_aendern(oben=start + schritt)
        start = unten if unten is not None else (oben - 20 if oben else (hf or 120.0) - 10)
        return self.ziel_aendern(unten=start + schritt)

    def ziel_beide(self, schritt: float) -> HfEinstellungen:
        """Den ganzen Zielbereich um ``schritt`` bpm heben oder senken."""
        e = self.einst(frisch=True)
        oben, unten = ziel_grenzen(e)
        if oben is None and unten is None:
            return self.ziel_schritt("oben", schritt)
        if schritt > 0:
            return self.ziel_aendern(
                oben=None if oben is None else oben + schritt,
                unten=None if unten is None else unten + schritt,
            )
        self.ziel_aendern(unten=None if unten is None else unten + schritt)
        return self.ziel_aendern(oben=None if oben is None else oben + schritt)

    def ziel_aus_bereich(self, bereich: hz.Bereich) -> HfEinstellungen:
        """Die Linien auf die Grenzen eines eigenen Bereichs setzen."""
        e = self.einst(frisch=True)
        e.alarm_bpm = e.ziel_unten_bpm = None
        self.einst_speichern(e)
        return self.ziel_aendern(oben=bereich.bis_bpm, unten=bereich.von_bpm)

    # -- Erholung -----------------------------------------------------------------------

    def erholung_reihe(self, t0: float) -> hz.HfReihe:
        return self.reihe(t0 - 10.0)

    def erholung_live(self) -> tuple[hz.Erholung | None, dict[int, float]]:
        """Die laufende Erholung und je Fenster die Sekunden bis zu seinem Wert. Ist die Zeit
        „Messen bis“ um, endet sie von selbst."""
        e = self.state.hf_erholung
        if e is None:
            return None, {}
        einst = self.einst()
        t0 = float(e["t0_s"])
        jetzt = self.lauf.jetzt_s()
        # ``jetzt < t0``: die Live-Achse hat neu bei 0 begonnen (Aufnahme gestartet, neu
        # verbunden) — die Erholung von vorher gilt nicht mehr, sie „liefe“ sonst t0 Sekunden
        # weiter (H75)
        if jetzt < t0 or jetzt - t0 > einst.messen_bis():
            self.state.hf_erholung = None
            return None, {}
        erg = hz.hrr_erholung(
            self.erholung_reihe(t0),
            t0,
            fenster=einst.erholung_fenster(),
            kontext=e.get("kontext", ""),
            haltung=e.get("haltung", ""),
        )
        # Der Wert eines Fensters steht erst, wenn sein Mittel ganz vorliegt
        halb = 2.5
        rest = {f: max(0.0, t0 + f + halb - jetzt) for f in erg.hrr}
        for f, r in rest.items():
            if r > 0:
                erg.hrr[f] = None
        return erg, rest

    def erholung_marke_schreiben(self) -> None:
        """Kontext und Haltung in die Marke der Notiz — die Datei ist die Wahrheit."""
        e = self.state.hf_erholung
        if e is None or e.get("notiz") is None:
            return
        marke = e["notiz"].get("marke")
        if isinstance(marke, dict):
            marke["kontext"], marke["haltung"] = e["kontext"], e["haltung"]

    def erholung_starten(self) -> None:
        """„Belastung endet jetzt“: Zeitpunkt merken, in der Aufnahme als Marke
        ``person/erholung``."""
        state, lauf = self.state, self.lauf
        vorher = state.hf_erholung or {}
        state.hf_erholung = {
            "t0_s": lauf.jetzt_s(),
            "kontext": vorher.get("kontext", "dauer"),
            "haltung": vorher.get("haltung", "steht"),
            "notiz": None,
        }
        if lauf.aufnahme is not None:
            state.hf_erholung["notiz"] = lauf.notiz_hinzufuegen(
                "Belastung beendet",
                marke={
                    "quelle": "person",
                    "art": "erholung",
                    "kontext": state.hf_erholung["kontext"],
                    "haltung": state.hf_erholung["haltung"],
                },
            )

    def erholung_beenden(self) -> None:
        self.state.hf_erholung = None

    def erholung_setzen(self, *, kontext: str | None = None, haltung: str | None = None) -> None:
        e = self.state.hf_erholung
        if e is None:
            return
        if kontext is not None:
            e["kontext"] = kontext
        if haltung is not None:
            e["haltung"] = haltung
        self.erholung_marke_schreiben()

    def fruehere_erholungen(self) -> list[hz.Erholung]:
        """Die Erholungen dieser Aufnahme aus den Marken ``person/erholung`` — ohne die
        laufende."""
        lauf = self.lauf
        if lauf.aufnahme is None:
            return []
        zb = lauf.notiz_zeitbezug()
        laufend = self.state.hf_erholung["t0_s"] if self.state.hf_erholung else None
        einst = self.einst()
        fenster = einst.erholung_fenster()
        # Eine abgeschlossene Erholung (älter als „Messen bis“) ändert sich nicht mehr: einmal
        # rechnen und merken. Vorher lief je Marke jeder Takt über den ganzen Live-Puffer —
        # zehn Marken kosteten am Rechner über 100 ms je Takt, in der Ereignisschleife (H76)
        merk: dict[Any, hz.Erholung] | None = getattr(self.state, "hf_erholung_merk", None)
        if merk is None:
            merk = {}
        aufnahme = getattr(lauf.aufnahme, "start_mono", id(lauf.aufnahme))
        jetzt = lauf.jetzt_s()
        fertig_ab = einst.messen_bis() + 5.0
        out: list[hz.Erholung] = []
        for e in lauf.aufnahme.ereignisse:
            marke = e.get("marke") if isinstance(e, dict) else None
            if not isinstance(marke, dict) or marke.get("art") != "erholung":
                continue
            x = zb.x(dict(e))
            if x is None or (laufend is not None and abs(x - laufend) < 0.5):
                continue
            kontext, haltung = str(marke.get("kontext") or ""), str(marke.get("haltung") or "")
            schluessel = (aufnahme, round(x, 1), tuple(fenster), kontext, haltung)
            erholung = merk.get(schluessel)
            if erholung is None:
                erholung = hz.hrr_erholung(
                    self.erholung_reihe(x), x, fenster=fenster, kontext=kontext, haltung=haltung
                )
                if jetzt - x > fertig_ab:
                    if len(merk) > 200:  # andere Aufnahmen, alte Fenster: nicht ewig halten
                        merk.clear()
                    merk[schluessel] = erholung
            out.append(erholung)
        return out

    def letztes_belastungsende(self) -> float | None:
        """Zeitpunkt des jüngsten „Belastung endet jetzt“ — der laufenden Erholung oder der
        letzten Marke der Aufnahme."""
        if self.state.hf_erholung is not None:
            return float(self.state.hf_erholung["t0_s"])
        frueher = self.fruehere_erholungen()
        return frueher[-1].t0 if frueher else None

    # -- Marken -------------------------------------------------------------------------

    def talk_marke(self) -> bool:
        """„Sprechen wird schwer“ (Talk-Test, Entscheidung 18) als Marke ``person/talk`` —
        ``False`` ohne Aufnahme (die Marke lebt in der Messdatei)."""
        if self.lauf.aufnahme is None:
            return False
        self.lauf.notiz_hinzufuegen(
            "Sprechen wird schwer", marke={"quelle": "person", "art": "talk"}
        )
        return True

    def notiz(self, text: str, x: float | None = None) -> bool:
        """Eine schlichte Notiz in die Aufnahme, an der Stelle ``x`` der Live-Achse (sonst
        jetzt) — ``False`` ohne Aufnahme."""
        if self.lauf.aufnahme is None:
            return False
        vor = 0.0 if x is None else max(0.0, self.lauf.jetzt_s() - x)
        return self.lauf.notiz_hinzufuegen(text, vor) is not None

    # -- Ablese-Intervall ---------------------------------------------------------------

    def intervall(self, von: float, bis: float, bezug: str) -> hz.IntervallErholung:
        """Die abgelesene Erholung zwischen zwei Zeitpunkten (`hz.intervall_erholung`)."""
        return hz.intervall_erholung(self.reihe(min(von, bis) - 10.0), von, bis, bezug=bezug)


def stumm_knoepfe_zeiten() -> list[tuple[str, float]]:
    """Beschriftung und Dauer der Stumm-Knöpfe: 5 min · 15 min · bis Messende."""
    from trainingsapp.core.hf_ziel import BIS_MESSENDE, STUMM_ZEITEN_S

    return [*((f"{s // 60} min", float(s)) for s in STUMM_ZEITEN_S), ("bis Messende", BIS_MESSENDE)]


__all__ = ["HfLive", "stumm_knoepfe_zeiten"]
