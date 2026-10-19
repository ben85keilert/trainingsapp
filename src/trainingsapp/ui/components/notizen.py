"""Notizen zur Messung — ein Klappfeld direkt unter der Hauptkurve.

Zugeklappt ist es eine Zeile: „NOTIZEN · 3" und „+ Notiz". Aufgeklappt zeigt
es die Liste; ein Tipp auf eine Notiz öffnet sie zum Bearbeiten und rückt
ihre Stelle in die Kurve. Die Eingabe hat drei Zeilen:

1. Zeitpunkt — beim Öffnen **eingefroren** auf den Moment des Tippens (das
   Ereignis passierte, als man „+ Notiz" drückte, nicht als man fertig
   getippt hat). Live lässt er sich auch mitlaufen lassen.
2. Zeit setzen — „Jetzt" (live), „In Kurve" (der nächste Tipp in die Kurve
   setzt den Zeitpunkt), ±1 s / ±5 s zum Verschieben.
3. Text, Speichern, Abbrechen (beim Bearbeiten: Löschen).

Marken stehen immer in der Hauptkurve (`marken`). Im Vollbild zeigt ein Tipp
auf eine Marke ihr **Etikett** (`bei`, `etikett`): Zeit und Text in der Kurve,
von dort bearbeiten oder löschen (`entfernen`, „Rückgängig" mit
`zurueckholen`). Gespeichert wird das
praxis_gui-Format mit Anker (`hrv_core.ereignisse`); wohin, entscheidet der
Aufrufer (``speichern``): live in die laufende Aufnahme, nachträglich als
Metadaten in die Messdatei.

**Übungen antippen.** „Übungen" in der Eingabe blendet die Übungen eines Plans
als kleine Namen ein (zuerst die heute anstehenden Pläne, zuletzt alle
Übungen); ein Tipp setzt den Namen in den Notiztext. Beim Speichern bekommt die
Notiz die Kurzcodes der Übungen, deren Namen im Text stehen (Feld ``uebungen``,
8 Zeichen je Übung — `core.kurzcode`, Vertrag Abschnitt 4); praxis_gui behält
das Feld. Notizen mit Übung tragen in der Liste ein kleines Hantelsymbol.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft
from hrv_core.ereignisse import Zeitbezug, notiz, sortiert

from trainingsapp.core.einheit import marke_angaben
from trainingsapp.core.kurzcode import genannte, kurzcode
from trainingsapp.core.laufend import minuten
from trainingsapp.ui.components.kurve import Reihe
from trainingsapp.ui.farben import FARBEN

#: Schritte zum Verschieben (s)
SCHRITTE = (-5, -1, 1, 5)


#: Quelle „Alle Übungen" in der Auswahl
ALLE = "alle"


@dataclass(frozen=True, slots=True)
class UebungsQuelle:
    """Woraus man Übungsnamen in die Notiz tippt: ein Plan oder der Katalog."""

    id: str
    name: str
    uebungen: list[str]


def uebungsquellen(state: Any) -> list[UebungsQuelle]:
    """Heute anstehende Pläne zuerst, dann die übrigen, zuletzt alle Übungen.

    Pläne ohne (noch vorhandene) Übungen fallen weg. ``state`` ist der `AppState`.
    """
    heute = state.heute()
    katalog = {u.id: u.name for u in state.uebungen.alle(mit_archivierten=True)}
    plaene = state.plaene.alle(state.profil.id)
    sortiert_ = [p for p in plaene if p.steht_an(heute)] + [
        p for p in plaene if not p.steht_an(heute)
    ]
    quellen = []
    for plan in sortiert_:
        namen = list(
            dict.fromkeys(katalog[i.exercise_id] for i in plan.items if i.exercise_id in katalog)
        )
        if namen:
            quellen.append(UebungsQuelle(plan.id, plan.name, namen))
    alle = sorted((u.name for u in state.uebungen.alle()), key=str.casefold)
    if alle:
        quellen.append(UebungsQuelle(ALLE, "Alle Übungen", alle))
    return quellen


def uebungs_katalog(state: Any) -> dict[str, str]:
    """Name → Kurzcode aller Übungen (auch archivierter) — für ``uebungen`` in Notizen."""
    return {u.name: kurzcode(u.id) for u in state.uebungen.alle(mit_archivierten=True)}


def einfuegen(text: str, name: str) -> str:
    """Den Namen an den Notiztext anhängen — mit Komma, wo schon etwas steht.

    >>> einfuegen("", "Planke"), einfuegen("Start", "Planke"), einfuegen("Start ", "Planke")
    ('Planke', 'Start, Planke', 'Start Planke')
    """
    if not text.strip():
        return name
    if text.endswith((" ", "\n")):
        return text + name
    return f"{text}, {name}"


#: Eine Schreibweise für alle Zeiten (abgeschnitten, nicht gerundet — wie die Achse; N26)
_uhr = minuten


class Notizfeld:
    """Liste, Eingabe und Marken der Notizen einer Messung.

    Args:
        zeitbezug: liefert den `Zeitbezug` (``None``: keine Notizen möglich). Live gibt
            es ihn seit 16.10.2026 auch vor der Aufnahme (`Messlauf.notiz_zeitbezug`).
        ereignisse: liefert die aktuelle Liste (wird nicht verändert).
        speichern: bekommt die neue, sortierte Liste.
        neu_zeichnen: Kurven neu zeichnen (Marken).
        zeigen: die Kurve auf eine Zeit rücken.
        mitte: Zeit in der Mitte des sichtbaren Fensters (Vorgabe nachträglich).
        jetzt: live die aktuelle Zeit der Kurvenachse, sonst ``None``.
        offen, offen_merken: Klappzustand, überlebt den Neuaufbau der Ansicht.
        uebungen: liefert die `UebungsQuelle`-n zum Antippen; ``None`` = aus.
        uebungen_offen, quelle, uebungen_merken: ob die Namen eingeblendet sind
            und aus welcher Quelle — überleben den Neuaufbau (``(offen, quelle)``).
    """

    def __init__(
        self,
        *,
        zeitbezug: Callable[[], Zeitbezug | None],
        ereignisse: Callable[[], list[dict]],
        speichern: Callable[[list[dict]], None],
        neu_zeichnen: Callable[[], None],
        zeigen: Callable[[float], None],
        mitte: Callable[[], float],
        jetzt: Callable[[], float] | None = None,
        offen: bool = False,
        offen_merken: Callable[[bool], None] = lambda _: None,
        uebungen: Callable[[], list[UebungsQuelle]] | None = None,
        uebungen_offen: bool = False,
        quelle: str | None = None,
        uebungen_merken: Callable[[bool, str | None], None] = lambda *_: None,
        katalog: Callable[[], dict[str, str]] | None = None,
        breite: Callable[[], float] | None = None,
        ausblenden: Callable[[dict], bool] | None = None,
    ) -> None:
        self._zeitbezug = zeitbezug
        self._ereignisse = ereignisse
        #: Notizen, die Liste und `marken` nicht zeigen (die Leistungen der Person — sie
        #: haben eine eigene Ebene, Plan D); `bei` und `etikett` kennen sie weiter
        self._ausblenden = ausblenden or (lambda _e: False)
        self._speichern = speichern
        self._neu_zeichnen = neu_zeichnen
        self._zeigen = zeigen
        self._mitte = mitte
        self._jetzt = jetzt
        self._breite = breite
        #: Marke, die gerade mit dem Finger gezogen wird (Index), und wo sie steht
        self.gezogen: int | None = None
        self.zieh_x = 0.0
        self._offen_merken = offen_merken
        self._uebungen = uebungen
        self._uebungen_merken = uebungen_merken
        self._katalog = katalog
        self.uebungen_offen = uebungen_offen
        self.quelle = quelle
        self.offen = offen
        #: ``None`` = keine Eingabe offen, ``-1`` = neue Notiz, sonst Index
        self.bearbeite: int | None = None
        self.x = 0.0
        self.eingefroren = True
        self.waehlen = False
        self._text = ft.TextField(
            hint_text="Was ist passiert?",
            dense=True,
            multiline=True,
            shift_enter=True,
            min_lines=1,
            max_lines=3,
            expand=True,
            on_submit=lambda _: self.uebernehmen(),
        )
        self._zeit = ft.Text(size=13, weight=ft.FontWeight.W_600)
        self._zustand = ft.Text(size=11, opacity=0.65)
        self._inhalt = ft.Column(spacing=4)
        self.control = ft.Container(content=self._inhalt)
        self._gestalt()
        self._aufbauen()

    # -- Zustand ---------------------------------------------------------------

    @property
    def live(self) -> bool:
        return self._jetzt is not None

    def verfuegbar(self) -> bool:
        """Ob es einen Zeitbezug gibt — live auch vor der Aufnahme (Ben, 16.10.2026)."""
        return self._zeitbezug() is not None

    def _jetzt_x(self) -> float:
        return self._jetzt() if self._jetzt is not None else self._mitte()

    def _x_der_eingabe(self) -> float:
        return self._jetzt_x() if (self.live and not self.eingefroren) else self.x

    # -- Bedienung ---------------------------------------------------------------

    def neu(self) -> None:
        """„+ Notiz": Zeitpunkt sofort einfrieren, Eingabe öffnen."""
        if not self.verfuegbar():
            return
        self.bearbeite = -1
        self.x = self._jetzt_x()
        self.eingefroren = True
        self.waehlen = False
        self._text.value = ""
        self._klappen(True)
        self._aendern(kurve=True)

    def bearbeiten(self, i: int) -> None:
        zb = self._zeitbezug()
        liste = self._ereignisse()
        if zb is None or not 0 <= i < len(liste):
            return
        x = zb.x(liste[i])
        self.bearbeite = i
        self.x = x if x is not None else self._mitte()
        self.eingefroren = True
        self.waehlen = False
        self._text.value = str(liste[i].get("text") or "")
        self._zeigen(self.x)
        self._aendern(kurve=True)

    def jetzt_setzen(self) -> None:
        self.x = self._jetzt_x()
        self.eingefroren = True
        self.waehlen = False
        self._aendern(kurve=True)

    def einfrieren_umschalten(self) -> None:
        if self.eingefroren:
            self.eingefroren = False
        else:
            self.x = self._jetzt_x()
            self.eingefroren = True
        self._aendern(kurve=True)

    def waehlen_umschalten(self) -> None:
        self.waehlen = not self.waehlen
        self._aendern()

    def verschieben(self, delta_s: float) -> None:
        self.x = self._x_der_eingabe() + delta_s
        self.eingefroren = True
        self._aendern(kurve=True)

    def tippen(self, x: float) -> None:
        """Ein Tipp in die Kurve — setzt den Zeitpunkt, wenn „In Kurve" aktiv ist."""
        if self.bearbeite is None or not self.waehlen:
            return
        self.x = x
        self.eingefroren = True
        self.waehlen = False
        self._aendern(kurve=True)

    def abbrechen(self) -> None:
        self.bearbeite = None
        self.waehlen = False
        self._aendern(kurve=True)

    def uebernehmen(self) -> None:
        """Speichern — neue Notiz anhängen oder die bearbeitete ersetzen."""
        zb = self._zeitbezug()
        text = (self._text.value or "").strip()
        if zb is None or self.bearbeite is None or not text:
            return
        liste = list(self._ereignisse())
        alt = liste[self.bearbeite] if 0 <= self.bearbeite < len(liste) else None
        codes = genannte(text, self._katalog()) if self._katalog is not None else None
        eintrag = notiz(text, zb.anker(self._x_der_eingabe()), zb.start_utc, alt, codes)
        if alt is not None:
            liste[self.bearbeite] = eintrag
        else:
            liste.append(eintrag)
        self._speichern(sortiert(liste, zb.beats()))
        self.bearbeite = None
        self.waehlen = False
        self._aendern(kurve=True)

    def loeschen(self) -> None:
        liste = list(self._ereignisse())
        if self.bearbeite is None or not 0 <= self.bearbeite < len(liste):
            return
        del liste[self.bearbeite]
        self._speichern(liste)
        self.bearbeite = None
        self._aendern(kurve=True)

    # -- Marken ohne Tastatur (Querformat, Ben 15.10.2026) -------------------------

    def marke_setzen(self, x: float | None = None) -> bool:
        """Eine Notiz ohne Text an ``x`` (sonst jetzt bzw. Fenstermitte) — den Text
        gibt man später dazu. ``False``: keine Aufnahme, nichts gesetzt."""
        zb = self._zeitbezug()
        if zb is None:
            return False
        stelle = self._jetzt_x() if x is None else x
        liste = list(self._ereignisse())
        bearbeitet = self._bearbeitete(liste)
        liste.append(notiz("", zb.anker(stelle), zb.start_utc))
        self._speichern(sortiert(liste, zb.beats()))
        self._neu_zaehlen(bearbeitet)
        self._aendern(kurve=True)
        return True

    def _toleranz(self) -> float:
        """Wie nah der Finger einer Marke sein muss: 2 % der Fensterbreite, mindestens 1 s."""
        return max(1.0, 0.02 * self._breite()) if self._breite is not None else 1.0

    def bei(self, x: float, ohne: int | None = None) -> int | None:
        """Die Notiz, deren Marke ``x`` am nächsten liegt — innerhalb der Toleranz."""
        zb = self._zeitbezug()
        if zb is None:
            return None
        beste: tuple[float, int] | None = None
        for i, e in enumerate(self._ereignisse()):
            mx = zb.x(e)
            if mx is None or i == ohne:
                continue
            abstand = abs(mx - x)
            if abstand <= self._toleranz() and (beste is None or abstand < beste[0]):
                beste = (abstand, i)
        return beste[1] if beste is not None else None

    def greifen(self, x: float) -> bool:
        """Für `zeitfenster.wischbar`: Eine Marke unter dem Finger folgt ihm.

        Beim ersten Aufruf einer Geste entscheidet die Nähe; danach kommt jede
        weitere Lage hierher, bis `loslassen`. Die Kurve zeichnet `wischbar`.
        """
        if self.gezogen is not None:
            self.zieh_x = x
            return True
        i = self.bei(x, ohne=self.bearbeite)
        if i is None:
            return False
        self.gezogen, self.zieh_x = i, x
        return True

    def loslassen(self) -> None:
        """Ende der Geste: die gezogene Marke bekommt ihren neuen Anker."""
        i, self.gezogen = self.gezogen, None
        zb = self._zeitbezug()
        liste = list(self._ereignisse())
        if i is None or zb is None or not 0 <= i < len(liste):
            return
        bearbeitet = self._bearbeitete(liste)
        alt = liste[i]
        liste[i] = notiz(str(alt.get("text") or ""), zb.anker(self.zieh_x), zb.start_utc, alt)
        self._speichern(sortiert(liste, zb.beats()))
        self._neu_zaehlen(bearbeitet)
        self._aendern(kurve=True)

    # -- Etikett in der Kurve (Vollbild, Ben 16.10.2026) ----------------------------

    def etikett(self, i: int) -> tuple[float, str, str] | None:
        """``(Stelle, Zeit, Text)`` der Notiz ``i`` — für ihr Etikett in der Kurve."""
        zb = self._zeitbezug()
        liste = self._ereignisse()
        if zb is None or not 0 <= i < len(liste):
            return None
        x = zb.x(liste[i])
        if x is None:
            return None
        return x, self._zeit_von(liste[i], zb), str(liste[i].get("text") or "")

    def entfernen(self, i: int) -> dict | None:
        """Notiz ``i`` löschen, ohne die Eingabe zu öffnen — zurück kommt sie für „Rückgängig"."""
        liste = list(self._ereignisse())
        if not 0 <= i < len(liste):
            return None
        bearbeitet = self._bearbeitete(liste)
        weg = liste.pop(i)
        self._speichern(liste)
        if bearbeitet is weg:
            self.bearbeite = None
        self._neu_zaehlen(bearbeitet)
        self._aendern(kurve=True)
        return weg

    def zurueckholen(self, eintrag: dict) -> None:
        """„Rückgängig" nach `entfernen`: die Notiz wieder an ihre Stelle."""
        zb = self._zeitbezug()
        if zb is None:
            return
        liste = list(self._ereignisse())
        bearbeitet = self._bearbeitete(liste)
        self._speichern(sortiert([*liste, eintrag], zb.beats()))
        self._neu_zaehlen(bearbeitet)
        self._aendern(kurve=True)

    def _bearbeitete(self, liste: list[dict]) -> dict | None:
        b = self.bearbeite
        return liste[b] if b is not None and 0 <= b < len(liste) else None

    def _neu_zaehlen(self, bearbeitet: dict | None) -> None:
        """Nach Einfügen oder Löschen: Die offene Eingabe zeigt weiter auf ihre Notiz."""
        if self.bearbeite is None or self.bearbeite < 0:
            return
        self.bearbeite = next(
            (j for j, e in enumerate(self._ereignisse()) if e is bearbeitet), None
        )

    def uebungen_umschalten(self) -> None:
        self.uebungen_offen = not self.uebungen_offen
        self._uebungen_merken(self.uebungen_offen, self.quelle)
        self._aendern()

    def quelle_waehlen(self, quelle: str) -> None:
        self.quelle = quelle
        self._uebungen_merken(self.uebungen_offen, self.quelle)
        self._aendern()

    def uebung_einsetzen(self, name: str) -> None:
        """Ein Tipp auf einen Übungsnamen: ab in den Notiztext."""
        self._text.value = einfuegen(self._text.value or "", name)
        with contextlib.suppress(Exception):
            self._text.update()

    def _klappen(self, offen: bool | None = None) -> None:
        self.offen = (not self.offen) if offen is None else offen
        self._offen_merken(self.offen)

    def umklappen(self) -> None:
        self._klappen()
        self._aendern()

    def aufklappen(self) -> None:
        """Die Liste zeigen — das Vollbild öffnet die Notizen immer aufgeklappt."""
        if not self.offen:
            self.umklappen()

    def auffrischen(self) -> None:
        """Neu aufbauen, z. B. wenn live eine Aufnahme beginnt oder endet."""
        if not self.verfuegbar():
            self.bearbeite = None
        self._aendern()

    def tick(self) -> None:
        """Live: die mitlaufende Zeit der Eingabe auffrischen (nur das Textfeld)."""
        if self.bearbeite is not None and not self.eingefroren:
            self._zeit_texte()
            with contextlib.suppress(Exception):
                self._zeit.update()

    # -- Marken ------------------------------------------------------------------

    def marken(self, x_von: float, x_bis: float) -> list[Reihe]:
        """Senkrechte Linien für die Hauptkurve: Notizen und die offene Eingabe.

        Die y-Werte liegen weit außerhalb; `kurve` begrenzt Reihen ohne
        ``skala`` auf ihren Bereich — so reicht die Linie von unten bis oben.
        """
        zb = self._zeitbezug()
        if zb is None:
            return []
        notizen: list[float] = []
        for i, e in enumerate(self._ereignisse()):
            x = zb.x(e)
            if (
                x is not None
                and x_von <= x <= x_bis
                and i not in (self.bearbeite, self.gezogen)
                and not self._ausblenden(e)
            ):
                notizen.append(x)
        reihen = [senkrechte(notizen, FARBEN["notiz"], 1.5, gestrichelt=False)]
        if self.bearbeite is not None:
            x = self._x_der_eingabe()
            if x_von <= x <= x_bis:
                reihen.append(senkrechte([x], FARBEN["notiz_neu"], 2.0, gestrichelt=True))
        if self.gezogen is not None and x_von <= self.zieh_x <= x_bis:
            reihen.append(senkrechte([self.zieh_x], FARBEN["notiz_neu"], 2.0, gestrichelt=True))
        return [r for r in reihen if r.punkte]

    def positionen(self, x_von: float, x_bis: float, nur: Callable[[dict], bool]) -> list[float]:
        """Die Stellen der Notizen im Ausschnitt, auf die ``nur`` zutrifft — für eine
        eigene Ebene (die Leistungen der Person)."""
        zb = self._zeitbezug()
        if zb is None:
            return []
        out: list[float] = []
        for e in self._ereignisse():
            if not nur(e):
                continue
            x = zb.x(e)
            if x is not None and x_von <= x <= x_bis:
                out.append(x)
        return out

    def ereignis(self, i: int) -> dict | None:
        liste = self._ereignisse()
        return liste[i] if 0 <= i < len(liste) else None

    # -- Aufbau ------------------------------------------------------------------

    def _aendern(self, kurve: bool = False) -> None:
        self._aufbauen()
        with contextlib.suppress(Exception):
            self.control.update()
        if kurve:
            self._neu_zeichnen()

    def _zeit_texte(self) -> None:
        zb = self._zeitbezug()
        x = self._x_der_eingabe()
        if zb is None:
            self._zeit.value = ""
            return
        anker = zb.anker(x)
        seit = float(anker.get("t_wall_s") or 0.0) if self.live else x
        uhr = zb.uhr(anker)
        self._zeit.value = f"{_uhr(seit)}" + (f" · {uhr}" if uhr else "")
        if self.waehlen:
            self._zustand.value = "Tippe in die Kurve"
        elif self.live and not self.eingefroren:
            self._zustand.value = "läuft mit"
        else:
            self._zustand.value = "eingefroren" if self.live else ""

    def _gestalt(self) -> None:
        """Alle Controls einmal anlegen — danach ändern sich nur Werte und Sichtbarkeit.

        So wandert das Textfeld nie in einen neuen Elternteil, und was getippt
        ist, übersteht jedes Auffrischen der Live-Ansicht.
        """
        self._pfeil = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.6)
        self._titel = ft.Text("NOTIZEN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
        self._neu_knopf = ft.TextButton(
            "Notiz", icon=ft.Icons.ADD_COMMENT_OUTLINED, on_click=lambda: self.neu()
        )
        kopf = ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    on_click=lambda: self.umklappen(),
                    padding=ft.Padding.symmetric(vertical=6),
                    content=ft.Row(spacing=4, controls=[self._pfeil, self._titel]),
                ),
                self._neu_knopf,
            ],
        )
        self._einfrieren = ft.IconButton(
            ft.Icons.PLAY_CIRCLE_OUTLINE,
            icon_size=20,
            on_click=lambda: self.einfrieren_umschalten(),
            visible=self.live,
        )
        self._waehlen_knopf = ft.TextButton(
            "In Kurve", icon=ft.Icons.TOUCH_APP_OUTLINED, on_click=lambda: self.waehlen_umschalten()
        )
        knoepfe: list[ft.Control] = []
        if self.live:
            knoepfe.append(
                ft.TextButton(
                    "Jetzt", icon=ft.Icons.MY_LOCATION, on_click=lambda: self.jetzt_setzen()
                )
            )
        knoepfe.append(self._waehlen_knopf)
        knoepfe += [_schritt(d, self.verschieben) for d in SCHRITTE]
        self._uebungen_knopf = ft.TextButton(
            "Übungen",
            icon=ft.Icons.FITNESS_CENTER,
            tooltip="Übungen eines Plans zum Antippen einblenden",
            on_click=lambda: self.uebungen_umschalten(),
            visible=self._uebungen is not None,
        )
        knoepfe.append(self._uebungen_knopf)
        self._quelle_wahl = ft.Dropdown(
            dense=True,
            text_size=13,
            width=240,
            on_select=lambda e: self.quelle_waehlen(str(e.control.value or ALLE)),
        )
        self._uebungs_namen = ft.Row(wrap=True, spacing=6, run_spacing=6)
        self._uebungs_box = ft.Container(
            visible=False,
            padding=ft.Padding.only(top=2, bottom=6, right=4),
            content=ft.Column(
                spacing=6, tight=True, controls=[self._quelle_wahl, self._uebungs_namen]
            ),
        )
        self._loeschen_knopf = ft.IconButton(
            ft.Icons.DELETE_OUTLINE, tooltip="Löschen", on_click=lambda: self.loeschen()
        )
        self._eingabe_box = ft.Container(
            padding=ft.Padding.only(left=8, right=4, top=4, bottom=6),
            border_radius=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            visible=False,
            content=ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.SCHEDULE, size=16, color=FARBEN["notiz_neu"]),
                            self._zeit,
                            self._zustand,
                            self._einfrieren,
                        ],
                    ),
                    ft.Row(spacing=0, wrap=True, controls=knoepfe),
                    self._uebungs_box,
                    ft.Row(
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            self._text,
                            self._loeschen_knopf,
                            ft.IconButton(
                                ft.Icons.CHECK,
                                tooltip="Speichern",
                                on_click=lambda: self.uebernehmen(),
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                tooltip="Abbrechen",
                                on_click=lambda: self.abbrechen(),
                            ),
                        ],
                    ),
                ],
            ),
        )
        self._hinweis = ft.Text(size=12, opacity=0.6)
        self._liste = ft.Column(spacing=0)
        self._inhalt.controls = [kopf, self._eingabe_box, self._hinweis, self._liste]

    def _aufbauen(self) -> None:
        zb = self._zeitbezug()
        liste = self._ereignisse()
        sichtbar = [i for i, e in enumerate(liste) if not self._ausblenden(e)]
        verfuegbar = zb is not None
        self._pfeil.icon = ft.Icons.EXPAND_MORE if self.offen else ft.Icons.CHEVRON_RIGHT
        self._titel.value = f"NOTIZEN · {len(sichtbar)}" if sichtbar else "NOTIZEN"
        self._neu_knopf.disabled = not verfuegbar or self.bearbeite is not None
        self._neu_knopf.tooltip = None if verfuegbar else "Notizen gehören zu einer Aufnahme"

        offen_eingabe = self.bearbeite is not None
        self._eingabe_box.visible = offen_eingabe
        if offen_eingabe:
            self._zeit_texte()
            self._einfrieren.icon = (
                ft.Icons.PLAY_CIRCLE_OUTLINE if self.eingefroren else ft.Icons.PAUSE_CIRCLE
            )
            self._einfrieren.tooltip = "Mitlaufen lassen" if self.eingefroren else "Einfrieren"
            self._waehlen_knopf.icon = (
                ft.Icons.TOUCH_APP if self.waehlen else ft.Icons.TOUCH_APP_OUTLINED
            )
            self._waehlen_knopf.style = (
                ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.15, FARBEN["notiz_neu"]))
                if self.waehlen
                else None
            )
            self._loeschen_knopf.visible = self.bearbeite is not None and self.bearbeite >= 0
            self._uebungen_fuellen()

        self._hinweis.visible = self.offen and (not verfuegbar or not sichtbar)
        self._hinweis.value = (
            "Notizen gehören zu einer Aufnahme."
            if not verfuegbar
            else "Noch keine Notiz. „+ Notiz“ friert den Zeitpunkt sofort ein."
        )
        self._liste.visible = self.offen and verfuegbar
        self._liste.controls = (
            [self._zeile(i, liste[i], zb) for i in sichtbar] if zb is not None else []
        )

    def _uebungen_fuellen(self) -> None:
        """Die Namen der gewählten Quelle — klein und dicht, damit zehn Übungen passen."""
        self._uebungen_knopf.icon = (
            ft.Icons.EXPAND_LESS if self.uebungen_offen else ft.Icons.FITNESS_CENTER
        )
        quellen = self._uebungen() if self._uebungen is not None and self.uebungen_offen else []
        self._uebungs_box.visible = bool(quellen)
        if not quellen:
            return
        gewaehlt = next((q for q in quellen if q.id == self.quelle), quellen[0])
        self._quelle_wahl.options = [ft.DropdownOption(key=q.id, text=q.name) for q in quellen]
        self._quelle_wahl.value = gewaehlt.id
        self._quelle_wahl.visible = len(quellen) > 1
        self._uebungs_namen.controls = [
            _name_knopf(n, self.uebung_einsetzen) for n in gewaehlt.uebungen
        ]

    def _zeit_von(self, e: dict, zb: Zeitbezug) -> str:
        """„2:15 · 14:03" — live seit Beginn der Aufnahme, nachträglich auf der Kurvenachse."""
        seit = float(e.get("t_wall_s") or 0.0) if self.live else (zb.x(e) or 0.0)
        uhr = zb.uhr(e)
        return _uhr(seit) + (f" · {uhr}" if uhr else "")

    def _zeile(self, i: int, e: dict, zb: Zeitbezug) -> ft.Control:
        zeit = self._zeit_von(e, zb)
        text: ft.Control = (
            ft.Text(str(e.get("text") or ""), size=13)
            if e.get("text")
            else ft.Text("(ohne Text — antippen)", size=13, italic=True, opacity=0.6)
        )
        # Was die Notiz maschinenlesbar trägt — sichtbar (Ben, 18.10.2026: „Aus
        # Transparenzgründen“): Übung, Marke, Soll, Ablauf
        angaben = marke_angaben(e)
        if angaben:
            text = ft.Column(
                spacing=3,
                tight=True,
                controls=[
                    text,
                    ft.Row(
                        wrap=True, spacing=4, run_spacing=4, controls=[_angabe(a) for a in angaben]
                    ),
                ],
            )
        return ft.Container(
            on_click=(lambda _=None, i=i: self.bearbeiten(i)),
            padding=ft.Padding.symmetric(vertical=4, horizontal=6),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.12, FARBEN["notiz"]) if i == self.bearbeite else None,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(width=3, height=16, bgcolor=FARBEN["notiz"], border_radius=2),
                    ft.Text(zeit, size=12, opacity=0.7, width=96),
                    ft.Container(content=text, expand=True),
                ],
            ),
        )


def _angabe(text: str) -> ft.Control:
    """Eine Angabe der Marke als kleines Etikett (`core.einheit.marke_angaben`)."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
        border_radius=6,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
        content=ft.Text(text, size=11, opacity=0.8),
    )


def _name_knopf(name: str, einsetzen: Callable[[str], None]) -> ft.Control:
    """Ein Übungsname als kleine Pille — kompakter als ein Chip."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border_radius=14,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        ink=True,
        on_click=lambda _=None: einsetzen(name),
        content=ft.Text(name, size=12),
    )


def _schritt(delta: int, verschieben: Callable[[float], None]) -> ft.Control:
    return ft.TextButton(
        f"{delta:+d} s".replace("-", "−"),
        on_click=lambda: verschieben(float(delta)),
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=6)),
    )


def senkrechte(xs: list[float], farbe: str, breite: float, *, gestrichelt: bool) -> Reihe:
    """Senkrechte Linien über die ganze Höhe der Kurve — Notizen, Crop, Abschnitte."""
    punkte: list[tuple[float, float]] = []
    naehte: list[int] = []
    for x in sorted(xs):
        if punkte:
            naehte.append(len(punkte))
        punkte += [(x, -1e9), (x, 1e9)]
    return Reihe(
        punkte,
        farbe=farbe,
        breite=breite,
        naehte=naehte,
        skala=False,
        gestrichelt=gestrichelt,
        marke=True,
    )


__all__ = [
    "ALLE",
    "Notizfeld",
    "UebungsQuelle",
    "einfuegen",
    "senkrechte",
    "uebungs_katalog",
    "uebungsquellen",
]
