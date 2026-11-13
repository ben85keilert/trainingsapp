"""Eigene Kurse bauen (Ben, 12.11.2026; `docs/plan_kurse.md` §7, `docs/plan_kurseditor.md`).

Zwei Ansichten:

- ``/kurse/<id>/bearbeiten`` — der Kurs: Name, Beschreibung, Freischaltung, die Kapitel
  (anlegen, umordnen, löschen). Jede Änderung wird sofort gespeichert — es ist eine Liste,
  kein Formular.
- ``/kurse/<id>/<kapitel>/bearbeiten`` — ein Kapitel: Titel, **Blöcke** (Text, Medium, Frage,
  Test, Auswahl — `core/kursbloecke.py`), die Pläne (aus den eigenen Plänen übernommen) und
  die Bedingung. Ein Formular mit „Speichern“; Zurück speichert.

Bearbeitet werden **eigene** Kurse (``package_id`` leer). Einen Kurs aus einem Paket kopiert
man zuerst (`kurs_kopieren`) — ein Paket-Update überschriebe sonst die Änderungen, und der
Fortschritt hängt an den Kapitel-IDs des Pakets. Bedingungen bleiben die vier Arten; es gibt
keine freie Formel (nie aus Messwerten).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import links
from trainingsapp.core.anpassung import Regel
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    FRAGE,
    MEDIUM,
    TEST,
    TEXT,
    Antwort,
    Block,
)
from trainingsapp.core.kurse import (
    FREISCHALTUNGEN,
    GELESEN,
    MESSUNG,
    SUMME,
    TAGE,
    Bedingung,
    Kapitel,
    Kurs,
    PlanVorlage,
)
from trainingsapp.core.models import Exercise, Media, new_id
from trainingsapp.core.pakete import paketplan_aus
from trainingsapp.core.result_spec import basis_key
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert

#: Felder, die ein Test messen kann (Art aus dem Feldvorrat)
TESTFELDER = ("hold", "duration", "reps", "weight", "distance")
BEDINGUNG_NAMEN = {
    GELESEN: "gelesen — „Weiter“ reicht",
    SUMME: "Menge einer Übung",
    TAGE: "Tage mit den Plänen des Kapitels",
    MESSUNG: "eine HRV-Messung (nur die Dauer)",
}


def kurs_anlegen(state: Any) -> Kurs:
    """Ein neuer eigener Kurs mit einem leeren Kapitel."""
    kurs = Kurs(name="Neuer Kurs", kapitel=[Kapitel(titel="Kapitel 1")])
    state.kurse.speichern(kurs)
    return state.kurse.laden(kurs.id) or kurs


def kurs_kopieren(state: Any, kurs: Kurs) -> Kurs:
    """Eine eigene Kopie mit neuen IDs — Fortschritt und Pläne des Originals bleiben dort."""
    kopie = Kurs(
        name=f"{kurs.name} (Kopie)",
        beschreibung=kurs.beschreibung,
        freischaltung=kurs.freischaltung,
        kapitel=[
            replace(
                k,
                id=new_id(),
                kurs_id="",
                bloecke=[replace(b, id=new_id()) for b in k.bloecke],
            )
            for k in kurs.kapitel
        ],
    )
    state.kurse.speichern(kopie)
    return state.kurse.laden(kopie.id) or kopie


def antworten_text(antworten: list[Antwort]) -> str:
    """Die Antworten einer Frage als Zeilen: ``*`` vorn = trifft zu, nach ``|`` der Hinweis.

    >>> antworten_text([Antwort("Knie"), Antwort("Ellbogen vor", True, "Hebel")])
    'Knie\\n* Ellbogen vor | Hebel'
    """
    return "\n".join(
        f"{'* ' if a.richtig else ''}{a.text}{f' | {a.hinweis}' if a.hinweis else ''}"
        for a in antworten
    )


def antworten_lesen(text: str) -> list[Antwort]:
    """Das Gegenstück zu `antworten_text` — leere Zeilen fallen weg.

    >>> [(a.text, a.richtig, a.hinweis) for a in antworten_lesen("Knie\\n\\n* Vor | Hebel")]
    [('Knie', False, ''), ('Vor', True, 'Hebel')]
    """
    ergebnis: list[Antwort] = []
    for zeile in text.splitlines():
        roh = zeile.strip()
        if not roh:
            continue
        richtig = roh.startswith("*")
        wort, _, mehr = roh.lstrip("* ").partition("|")
        if wort.strip():
            ergebnis.append(Antwort(wort.strip(), richtig, mehr.strip()))
    return ergebnis


def block_kurz(block: Block, katalog: dict[str, Exercise]) -> str:
    """Eine Zeile zum Block in der Liste des Editors."""
    if block.art == TEXT:
        return block.titel or block.text[:60] or "leer"
    if block.art == MEDIUM:
        return (block.medium.title or block.medium.uri) if block.medium else "ohne Adresse"
    if block.art == FRAGE:
        return f"{block.titel or 'ohne Frage'} · {len(block.antworten)} Antworten"
    name = katalog[block.uebung].name if block.uebung in katalog else "Übung wählen"
    if block.art == TEST:
        return f"{name} — wird Ziel im Plan" + (
            f" ({round(block.faktor * 100)} %)" if block.faktor != 1.0 else ""
        )
    return f"{block.anzahl} von {len(block.uebungen)} Übungen"


def block_fehler(block: Block) -> str | None:
    """Was einem Block zum Speichern fehlt — ``None`` = vollständig."""
    if block.art == MEDIUM and (block.medium is None or not links.erlaubt(block.medium.uri)):
        return "Ein Medium braucht eine https-Adresse."
    if block.art == FRAGE and (not block.titel or not block.antworten):
        return "Eine Frage braucht einen Text und mindestens eine Antwort."
    if block.art == TEST and not block.uebung:
        return "Ein Test braucht eine Übung."
    if block.art == AUSWAHL and (not block.uebungen or block.anzahl > len(block.uebungen)):
        return "Eine Auswahl braucht Übungen — mindestens so viele, wie man wählt."
    return None


# ---------------------------------------------------------------------------
# Der Kurs
# ---------------------------------------------------------------------------


def kurs_bearbeiten(page: Any, state: Any, kurs: Kurs) -> ft.View:
    """Name, Beschreibung, Freischaltung und die Kapitel eines eigenen Kurses."""
    basis = f"/kurse/{kurs.id}"
    spalte = ft.Column(spacing=6)

    def sichern() -> None:
        state.kurse.speichern(kurs)

    def name_geaendert(e: Any) -> None:
        kurs.name = " ".join(str(e.control.value or "").split()) or "Kurs ohne Namen"
        sichern()

    def text_geaendert(e: Any) -> None:
        kurs.beschreibung = str(e.control.value or "").strip()
        sichern()

    def freischaltung_gewaehlt(e: Any) -> None:
        if e.control.value in FREISCHALTUNGEN:
            kurs.freischaltung = str(e.control.value)
            sichern()

    def neu() -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            spalte.update()

    def schieben(k: Kapitel, um: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            i = kurs.kapitel.index(k)
            j = i + um
            if 0 <= j < len(kurs.kapitel):
                kurs.kapitel[i], kurs.kapitel[j] = kurs.kapitel[j], kurs.kapitel[i]
                sichern()
                neu()

        return handler

    def loeschen_fragen(k: Kapitel) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dialog: ft.AlertDialog

            def ausfuehren(_e: Any = None) -> None:
                kurs.kapitel.remove(k)
                sichern()
                schliessen(dialog)
                neu()

            dialog = ft.AlertDialog(
                title=ft.Text(f"„{k.titel}“ löschen?"),
                content=ft.Text(
                    "Das Kapitel mit seinen Blöcken verschwindet aus dem Kurs. Pläne, die es "
                    "schon angelegt hat, und alle Einträge bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                    ft.FilledButton("Löschen", on_click=ausfuehren, data="kapitel_loeschen"),
                ],
            )
            page.show_dialog(dialog)

        return handler

    def oeffner(k: Kapitel) -> Callable[..., Any]:
        async def handler(_e: Any = None) -> None:
            await page.push_route(f"{basis}/{k.id}/bearbeiten")

        return handler

    def hinzufuegen(_e: Any = None) -> None:
        kurs.kapitel.append(Kapitel(titel=f"Kapitel {len(kurs.kapitel) + 1}", kurs_id=kurs.id))
        sichern()
        neu()

    def zeichnen() -> None:
        letzte = len(kurs.kapitel) - 1
        spalte.controls = [
            ft.ListTile(
                leading=ft.Text(str(n + 1), size=16, weight=ft.FontWeight.W_600),
                title=ft.Text(k.titel or "ohne Titel"),
                subtitle=ft.Text(
                    "  ·  ".join(
                        [
                            f"{len(k.bloecke)} Blöcke" if k.bloecke else "ohne Blöcke",
                            *(["mit Plan"] if k.plaene else []),
                            BEDINGUNG_NAMEN[k.bedingung.art].split(" — ")[0],
                        ]
                    ),
                    size=12,
                ),
                trailing=ft.Row(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Nach oben",
                            disabled=n == 0,
                            on_click=schieben(k, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Nach unten",
                            disabled=n == letzte,
                            on_click=schieben(k, 1),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Kapitel löschen",
                            disabled=len(kurs.kapitel) <= 1,
                            on_click=loeschen_fragen(k),
                        ),
                    ],
                ),
                on_click=oeffner(k),
                content_padding=ft.Padding.only(left=4, right=0),
                data=("kapitel", k.id),
            )
            for n, k in enumerate(kurs.kapitel)
        ]

    zeichnen()
    return ft.View(
        route=f"{basis}/bearbeiten",
        appbar=ft.AppBar(title=ft.Text("Kurs bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        ft.TextField(label="Name", value=kurs.name, on_blur=name_geaendert),
                        ft.TextField(
                            label="Beschreibung",
                            value=kurs.beschreibung,
                            multiline=True,
                            min_lines=2,
                            on_blur=text_geaendert,
                        ),
                        ft.Dropdown(
                            label="Freischaltung",
                            value=kurs.freischaltung,
                            options=[
                                ft.DropdownOption(key=k, text=t) for k, t in FREISCHALTUNGEN.items()
                            ],
                            on_select=freischaltung_gewaehlt,
                        ),
                        titel("Kapitel"),
                        spalte,
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Kapitel hinzufügen",
                                    icon=ft.Icons.ADD,
                                    on_click=hinzufuegen,
                                    data="kapitel_hinzufuegen",
                                )
                            ]
                        ),
                        hinweis(
                            "Änderungen hier gelten sofort. Weitergeben lässt sich der Kurs über "
                            "ein eigenes Paket (Einstellungen → Pakete)."
                        ),
                    ],
                )
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Kapitel
# ---------------------------------------------------------------------------


def kapitel_bearbeiten(page: Any, state: Any, kurs: Kurs, kapitel: Kapitel) -> ft.View:
    """Titel, Blöcke, Pläne und Bedingung eines Kapitels — ein Formular."""
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    katalog: dict[str, Exercise] = {u.id: u for u in state.uebungen.alle()}
    uebungen = sorted(katalog.values(), key=lambda u: u.name.lower())
    bloecke: list[Block] = [replace(b) for b in kapitel.bloecke]
    plaene: list[PlanVorlage] = [replace(v) for v in kapitel.plaene]
    bedingung = replace(kapitel.bedingung)
    titel_feld = ft.TextField(label="Titel", value=kapitel.titel)
    block_spalte = ft.Column(spacing=6)
    plan_spalte = ft.Column(spacing=6)
    bedingung_spalte = ft.Column(spacing=8)
    fehler = ft.Text("", size=13, color=ft.Colors.ERROR, visible=False)

    def frisch(spalte: ft.Column, zeichnen: Callable[[], None]) -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            spalte.update()

    def uebung_wahl(wert: str, label: str = "Übung") -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            value=wert if wert in katalog else None,
            options=[ft.DropdownOption(key=u.id, text=u.name) for u in uebungen],
            enable_filter=True,
            editable=True,
            menu_height=320,
        )

    # -- Blöcke ---------------------------------------------------------------------------

    def block_dialog(block: Block, neu: bool) -> None:
        """Die Felder zur Art des Blocks; „Übernehmen“ schreibt in die Liste des Formulars."""
        kopf = ft.TextField(
            label={TEXT: "Überschrift", FRAGE: "Frage", MEDIUM: "Titel"}.get(
                block.art, "Aufforderung (leer = Vorgabe)"
            ),
            value=(block.medium.title if block.medium else "")
            if block.art == MEDIUM
            else block.titel,
        )
        text = ft.TextField(
            label="Text (Markdown)" if block.art == TEXT else "Satz darunter",
            value=block.text,
            multiline=True,
            min_lines=4 if block.art == TEXT else 1,
        )
        adresse = ft.TextField(
            label="Adresse (https://…)",
            value=block.medium.uri if block.medium else "",
            keyboard_type=ft.KeyboardType.URL,
        )
        antworten = ft.TextField(
            label="Antworten — eine je Zeile, * = trifft zu, | Hinweis",
            value=antworten_text(block.antworten),
            multiline=True,
            min_lines=3,
        )
        uebung = uebung_wahl(block.uebung)
        feld = ft.Dropdown(label="Was wird gemessen")
        faktor = ft.TextField(
            label="Ziel in % des Tests",
            value=str(round(block.faktor * 100)),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        anzahl = ft.TextField(
            label="Wie viele wählt man",
            value=str(block.anzahl),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        nach = ft.TextField(
            label="Hinter Planübung Nr. (0 = ans Ende)",
            value=str(block.nach),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        gewaehlt: list[str] = [u for u in block.uebungen if u in katalog]
        wahl_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        dazu = uebung_wahl("", "Übung zur Auswahl hinzufügen")
        meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)
        dialog: ft.AlertDialog

        def felder_setzen() -> None:
            u = katalog.get(str(uebung.value or ""))
            angebot = [
                f for f in (u.result_spec.fields if u else []) if basis_key(f.key) in TESTFELDER
            ]
            feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
            schluessel = [f.key for f in angebot]
            feld.value = (
                block.feld if block.feld in schluessel else (schluessel[0] if schluessel else None)
            )

        def uebung_gewaehlt(_e: Any = None) -> None:
            felder_setzen()
            with contextlib.suppress(Exception):
                feld.update()

        def wahl_zeichnen() -> None:
            wahl_reihe.controls = [
                ft.Chip(
                    label=ft.Text(katalog[uid].name),
                    on_delete=lambda _e=None, uid=uid: wahl_weg(uid),
                    data=("auswahl_uebung", uid),
                )
                for uid in gewaehlt
            ]

        def wahl_weg(uid: str) -> None:
            gewaehlt.remove(uid)
            frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        def wahl_dazu(_e: Any = None) -> None:
            uid = str(dazu.value or "")
            if uid in katalog and uid not in gewaehlt:
                gewaehlt.append(uid)
                frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        uebung.on_select = uebung_gewaehlt
        dazu.on_select = wahl_dazu
        felder_setzen()
        wahl_zeichnen()

        def zahl(feld_: ft.TextField, vorgabe: float) -> float:
            try:
                return float(str(feld_.value or "").replace(",", "."))
            except ValueError:
                return vorgabe

        def uebernehmen(_e: Any = None) -> None:
            neuer = replace(block, text=str(text.value or "").strip())
            wort = " ".join(str(kopf.value or "").split())
            if block.art == MEDIUM:
                neuer.medium = Media(uri=str(adresse.value or "").strip(), title=wort)
                neuer.text = ""
            else:
                neuer.titel = wort
            if block.art == FRAGE:
                neuer.antworten = antworten_lesen(str(antworten.value or ""))
            if block.art == TEST:
                neuer.uebung = str(uebung.value or "")
                neuer.feld = str(feld.value or "hold")
                neuer.faktor = min(max(zahl(faktor, 100) / 100, 0.1), 3.0)
            if block.art == AUSWAHL:
                neuer.uebungen = list(gewaehlt)
                neuer.anzahl = max(1, int(zahl(anzahl, 1)))
                neuer.nach = max(0, int(zahl(nach, 0)))
            grund = block_fehler(neuer)
            if grund is not None:
                meldung.value = grund
                meldung.visible = True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            if neu:
                bloecke.append(neuer)
            else:
                bloecke[bloecke.index(block)] = neuer
            schliessen(dialog)
            frisch(block_spalte, bloecke_zeichnen)

        felder: dict[str, list[ft.Control]] = {
            TEXT: [kopf, text],
            MEDIUM: [kopf, adresse],
            FRAGE: [
                kopf,
                text,
                antworten,
                hinweis("Die Frage erklärt — nichts wird gespeichert oder gezählt."),
            ],
            TEST: [
                kopf,
                text,
                uebung,
                feld,
                faktor,
                hinweis(
                    "Der Test ist ein gewöhnlicher Eintrag der Übung. Der Wert wird ihr Ziel "
                    "im Kapitelplan."
                ),
            ],
            AUSWAHL: [
                kopf,
                text,
                wahl_reihe,
                dazu,
                anzahl,
                nach,
                hinweis(
                    "Ab zwei Gewählten stehen sie im Workout als Wege hinter der genannten "
                    "Planübung."
                ),
            ],
        }
        dialog = ft.AlertDialog(
            title=ft.Text(ARTEN[block.art]),
            content=ft.Column(
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                controls=[*felder[block.art], meldung],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Übernehmen", on_click=uebernehmen, data="block_uebernehmen"),
            ],
        )
        page.show_dialog(dialog)

    def block_schieben(block: Block, um: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            i = bloecke.index(block)
            j = i + um
            if 0 <= j < len(bloecke):
                bloecke[i], bloecke[j] = bloecke[j], bloecke[i]
                frisch(block_spalte, bloecke_zeichnen)

        return handler

    def block_weg(block: Block) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            bloecke.remove(block)
            frisch(block_spalte, bloecke_zeichnen)

        return handler

    def bloecke_zeichnen() -> None:
        letzte = len(bloecke) - 1
        block_spalte.controls = [
            ft.ListTile(
                leading=ft.Container(
                    width=64,
                    content=ft.Text(
                        ARTEN[b.art].split(",")[0], size=11, weight=ft.FontWeight.W_600
                    ),
                ),
                title=ft.Text(
                    block_kurz(b, katalog), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS
                ),
                trailing=ft.Row(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Nach oben",
                            disabled=n == 0,
                            on_click=block_schieben(b, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Nach unten",
                            disabled=n == letzte,
                            on_click=block_schieben(b, 1),
                        ),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="Entfernen", on_click=block_weg(b)),
                    ],
                ),
                on_click=lambda _e=None, b=b: block_dialog(b, neu=False),
                content_padding=ft.Padding.only(left=4, right=0),
                data=("block", b.id),
            )
            for n, b in enumerate(bloecke)
        ] or [hinweis("Noch kein Block — das Kapitel zeigt nur seinen Titel.")]

    def block_neu(art: str) -> Callable[..., None]:
        return lambda _e=None: block_dialog(Block(art), neu=True)

    # -- Pläne ----------------------------------------------------------------------------

    def plan_weg(vorlage: PlanVorlage) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            plaene.remove(vorlage)
            frisch(plan_spalte, plaene_zeichnen)

        return handler

    def plan_waehlen(_e: Any = None) -> None:
        eigene = [p for p in state.plaene.alle(state.profil.id) if p.items]
        dialog: ft.AlertDialog

        def nehmen(plan_id: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                plan = state.plaene.laden(plan_id)
                if plan is not None:
                    plaene.append(paketplan_aus(plan).vorlage)
                schliessen(dialog)
                frisch(plan_spalte, plaene_zeichnen)

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Plan übernehmen"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    hinweis(
                        "Das Kapitel bekommt eine Kopie des Plans, wie er jetzt ist — mit "
                        "Zielen, Ablauf und Anweisungen. Spätere Änderungen am Plan kommen "
                        "nicht nach."
                    ),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LIST_ALT),
                            title=ft.Text(p.name),
                            subtitle=ft.Text(f"{len(p.items)} Übungen", size=12),
                            on_click=nehmen(p.id),
                            data=("plan_nehmen", p.id),
                        )
                        for p in eigene
                    ),
                    *([] if eigene else [ft.Text("Noch kein eigener Plan mit Übungen.")]),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def regel_zeile(v: PlanVorlage, n: int) -> ft.Control:
        """Der Vorschlag nach der Belastung für diesen Plan (`core/anpassung.py`): Schalter und
        die drei Zahlen der Regel."""
        regel = Regel.aus_dict(v.anpassung) or Regel()
        felder = {
            "ab": ft.TextField(label="kürzer ab", value=str(regel.ab), width=92, dense=True),
            "bis": ft.TextField(label="länger bis", value=str(regel.bis), width=92, dense=True),
            "prozent": ft.TextField(label="um %", value=str(regel.prozent), width=80, dense=True),
        }
        zahlen = ft.Row(spacing=8, visible=v.anpassung is not None, controls=list(felder.values()))

        def lesen() -> None:
            neu = Regel.aus_dict({k: f.value for k, f in felder.items()})
            v.anpassung = (neu or Regel()).als_dict()

        def umgestellt(e: Any) -> None:
            if e.control.value:
                lesen()
            else:
                v.anpassung = None
            zahlen.visible = v.anpassung is not None
            with contextlib.suppress(Exception):
                zahlen.update()

        for f in felder.values():
            f.keyboard_type = ft.KeyboardType.NUMBER
            f.on_blur = lambda _e=None: lesen() if v.anpassung is not None else None
        return ft.Container(
            padding=ft.Padding.only(left=44, bottom=6),
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Switch(
                        label="Vorschlag nach der Belastung",
                        tooltip="Nach dem Workout ein anderes Zeitziel vorschlagen — nur auf Tipp",
                        value=v.anpassung is not None,
                        on_change=umgestellt,
                        data=("plan_regel", n),
                    ),
                    zahlen,
                ],
            ),
        )

    def plaene_zeichnen() -> None:
        zeilen: list[ft.Control] = []
        for n, v in enumerate(plaene):
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(v.name),
                    subtitle=ft.Text(
                        "  ·  ".join(
                            katalog[i.exercise_id].name if i.exercise_id in katalog else "fehlt"
                            for i in v.items
                        ),
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Aus dem Kapitel nehmen", on_click=plan_weg(v)
                    ),
                    content_padding=ft.Padding.only(left=4, right=0),
                )
            )
            zeilen.append(regel_zeile(v, n))
        plan_spalte.controls = zeilen

    # -- Bedingung ------------------------------------------------------------------------

    soll_feld = ft.TextField(
        label="Soll",
        value=f"{bedingung.soll:g}" if bedingung.soll else "",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    bed_uebung = uebung_wahl(bedingung.exercise_id)
    bed_feld = ft.Dropdown(label="Feld")

    def bed_felder() -> None:
        u = katalog.get(str(bed_uebung.value or ""))
        angebot = [f for f in (u.result_spec.fields if u else []) if basis_key(f.key) in TESTFELDER]
        bed_feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
        schluessel = [f.key for f in angebot]
        bed_feld.value = (
            bedingung.feld
            if bedingung.feld in schluessel
            else (schluessel[0] if schluessel else None)
        )

    def bed_uebung_gewaehlt(_e: Any = None) -> None:
        bed_felder()
        with contextlib.suppress(Exception):
            bed_feld.update()

    bed_uebung.on_select = bed_uebung_gewaehlt

    def art_gewaehlt(e: Any) -> None:
        if e.control.value in BEDINGUNG_NAMEN:
            bedingung.art = str(e.control.value)
            frisch(bedingung_spalte, bedingung_zeichnen)

    art_wahl = ft.Dropdown(
        label="Weiter geht es mit",
        value=bedingung.art,
        options=[ft.DropdownOption(key=k, text=t) for k, t in BEDINGUNG_NAMEN.items()],
        on_select=art_gewaehlt,
        data="bedingung_art",
    )

    def bedingung_zeichnen() -> None:
        soll_feld.label = {
            SUMME: "Menge (Wiederholungen bzw. Sekunden)",
            TAGE: "Tage",
            MESSUNG: "Minuten",
        }.get(bedingung.art, "Soll")
        bed_felder()
        bedingung_spalte.controls = [
            art_wahl,
            *([bed_uebung, bed_feld] if bedingung.art == SUMME else []),
            *([soll_feld] if bedingung.art != GELESEN else []),
        ]

    def bedingung_lesen() -> Bedingung:
        try:
            soll = float(str(soll_feld.value or "0").replace(",", "."))
        except ValueError:
            soll = 0.0
        return Bedingung(
            art=bedingung.art,
            exercise_id=str(bed_uebung.value or "") if bedingung.art == SUMME else "",
            feld=str(bed_feld.value or "reps") if bedingung.art == SUMME else "reps",
            soll=soll if bedingung.art != GELESEN else 0.0,
        )

    # -- Speichern ------------------------------------------------------------------------

    def stand() -> tuple[Any, ...]:
        return (
            (titel_feld.value or "").strip(),
            [b.to_dict() for b in bloecke],
            [v.to_dict() for v in plaene],
            bedingung_lesen().to_dict(),
        )

    ausgang = {"stand": stand()}

    def speichern() -> str | None:
        name = " ".join((titel_feld.value or "").split())
        b = bedingung_lesen()
        grund: str | None = None
        if not name:
            grund = "Das Kapitel braucht einen Titel."
        elif b.art != GELESEN and b.soll <= 0:
            grund = "Die Bedingung braucht ein Soll größer 0."
        elif b.art == SUMME and not b.exercise_id:
            grund = "Die Bedingung „Menge“ braucht eine Übung."
        elif b.art == TAGE and not plaene and not any(x.art == AUSWAHL for x in bloecke):
            grund = "„Tage“ zählt die Pläne des Kapitels — es hat keinen."
        elif any(x.art in (TEST, AUSWAHL) for x in bloecke) and not plaene:
            grund = "Test und Auswahl brauchen einen Plan im Kapitel."
        fehler.value = grund or ""
        fehler.visible = grund is not None
        with contextlib.suppress(Exception):
            fehler.update()
        if grund is not None:
            return grund
        ziel = kurs.kapitel_mit(kapitel.id)
        if ziel is None:
            return "Das Kapitel gibt es nicht mehr."
        ziel.titel, ziel.bloecke, ziel.plaene, ziel.bedingung = name, list(bloecke), list(plaene), b
        state.kurse.speichern(kurs)
        ausgang["stand"] = stand()
        return None

    async def zurueck(_e: Any = None) -> None:
        await page.push_route(f"/kurse/{kurs.id}/bearbeiten")

    async def speichern_und_gehen(_e: Any = None) -> None:
        if speichern() is None:
            page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
            await zurueck()

    bloecke_zeichnen()
    plaene_zeichnen()
    bedingung_zeichnen()
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Kapitel bearbeiten", abbrechen=zurueck, speichern=speichern_und_gehen
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        titel_feld,
                        fehler,
                        titel("Blöcke"),
                        block_spalte,
                        ft.Row(
                            wrap=True,
                            spacing=8,
                            run_spacing=4,
                            controls=[
                                ft.OutlinedButton(
                                    name.split(",")[0],
                                    icon=ft.Icons.ADD,
                                    on_click=block_neu(art),
                                    data=("block_neu", art),
                                )
                                for art, name in ARTEN.items()
                            ],
                        ),
                        karte(
                            titel("Pläne dieses Kapitels"),
                            plan_spalte,
                            ft.Row(
                                controls=[
                                    ft.TextButton(
                                        "Plan übernehmen …",
                                        icon=ft.Icons.PLAYLIST_ADD,
                                        on_click=plan_waehlen,
                                        data="plan_uebernehmen",
                                    )
                                ]
                            ),
                            hinweis(
                                "Der Plan entsteht für jede Person, die das Kapitel erreicht — "
                                "mit Test oder Auswahl erst mit „Plan anlegen“."
                            ),
                        ),
                        karte(titel("Bedingung"), bedingung_spalte),
                    ],
                )
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: stand() != ausgang["stand"],
        speichern=speichern,
        danach=zurueck,
    )


__all__ = [
    "antworten_lesen",
    "antworten_text",
    "block_fehler",
    "block_kurz",
    "kapitel_bearbeiten",
    "kurs_anlegen",
    "kurs_bearbeiten",
    "kurs_kopieren",
]
