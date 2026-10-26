"""Gurt-Warnung: zu viele Artefakte in der Live-Messung (Ben, 26.10.2026).

Ein trockener oder rutschender Brustgurt liefert markierte Schläge; DFA α1 und RMSSD
werden dann still unbrauchbar. Die Wache sieht den Artefaktanteil der letzten Minute
(`hrv_core.live.LiveFenster.artefaktanteil`) und sagt, wann zu warnen ist: ab
`LIVE_ARTEFAKT_WARNUNG`, Entwarnung erst unter `LIVE_ARTEFAKT_ENTWARNUNG` (Hysterese),
und ein neuer Alarm (für Benachrichtigung und Uhr) höchstens alle `SPERRE_S` Sekunden.
Die Anzeige (`text`) bleibt, solange die Warnung gilt.

Reine Logik ohne flet; der Messlauf ruft `pruefen` je Schlag, die Live-Ansicht zeigt
`text`, der Uhr-Kanal (hrv-watch) schickt jeden neuen Alarm als Benachrichtigung.
"""

from __future__ import annotations

from hrv_core.constants import LIVE_ARTEFAKT_ENTWARNUNG, LIVE_ARTEFAKT_WARNUNG

#: Mindestabstand zweier Alarme (s) — die Anzeige bleibt dazwischen stehen
SPERRE_S = 120.0


class Artefaktwache:
    """Hysterese und Sperrfrist über dem Artefaktanteil.

    >>> w = Artefaktwache()
    >>> w.pruefen(0.02, 10.0), w.text
    (None, None)
    >>> w.pruefen(0.12, 11.0)
    'Gurt prüfen: 12 % Artefakte'
    >>> w.pruefen(0.08, 12.0), w.text            # bleibt, kein neuer Alarm
    (None, 'Gurt prüfen: 8 % Artefakte')
    >>> w.pruefen(0.03, 13.0), w.text            # Entwarnung
    (None, None)
    >>> w.pruefen(0.30, 14.0)                    # in der Sperrfrist: Anzeige, kein Alarm
    >>> w.text
    'Gurt prüfen: 30 % Artefakte'
    >>> w.pruefen(0.30, 140.0)                   # Sperrfrist um, Warnung steht noch: Alarm
    'Gurt prüfen: 30 % Artefakte'
    """

    def __init__(
        self,
        warnung: float = LIVE_ARTEFAKT_WARNUNG,
        entwarnung: float = LIVE_ARTEFAKT_ENTWARNUNG,
        sperre_s: float = SPERRE_S,
    ) -> None:
        self.warnung = warnung
        self.entwarnung = entwarnung
        self.sperre_s = sperre_s
        #: Die laufende Warnung — ``None``, wenn der Gurt sauber liefert
        self.text: str | None = None
        #: Wie oft ein Alarm ausgelöst wurde — der Uhr-Kanal merkt sich den Stand
        self.alarme = 0
        self._letzter_alarm_s: float | None = None
        self._gemeldet = False

    def pruefen(self, anteil: float | None, jetzt_s: float) -> str | None:
        """Den Anteil (0–1, ``None`` = zu wenig Daten) ansehen — der Text eines **neuen**
        Alarms oder ``None``; `text` hält die laufende Warnung."""
        if anteil is None:
            return None
        aktiv = self.text is not None
        if anteil >= self.warnung or (aktiv and anteil >= self.entwarnung):
            self.text = f"Gurt prüfen: {round(anteil * 100)} % Artefakte"
            faellig = (
                self._letzter_alarm_s is None or jetzt_s - self._letzter_alarm_s >= self.sperre_s
            )
            if not self._gemeldet and faellig:
                self._gemeldet = True
                self._letzter_alarm_s = jetzt_s
                self.alarme += 1
                return self.text
            return None
        self.text = None
        self._gemeldet = False
        return None


__all__ = ["SPERRE_S", "Artefaktwache"]
