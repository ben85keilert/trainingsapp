"""Zustand der Zählzeile ohne flet (``docs/plan_beschleunigung.md`` §4.2, §5.2).

`components.zaehl_stand` hält Texte, ±1 und das Nachziehen der Zählzeile — ohne ``import
flet``, wie `components.marken_stand`. Diese Tests laufen darum auch im Kindprozess mit
gesperrtem flet (`test_import_regel.test_uhrkanal_laeuft_ohne_flet`). Der Messlauf ist hier
eine Attrappe: Was der Sensor zählte, setzt der Test am Satz.
"""

from __future__ import annotations

from types import SimpleNamespace

from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.kurzcode import kurzcode
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.core.zaehlen import SensorWahl
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein, UebungKontext
from trainingsapp.devices.profiles import POLAR_H10, UHR_BROADCAST, VERITY_SENSE
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui.components import zaehl_stand as zs

KNIEBEUGE = UebungKontext("u1", "Kniebeuge", "p1", "i1")


class Lauf:
    """Der Messlauf, soweit das Zählen ihn braucht — ohne Gerät und ohne Puffer."""

    def __init__(self, profil=POLAR_H10, *, verbunden: bool = True) -> None:
        self.t = 100.0
        self.profil = profil
        self.status = SimpleNamespace(
            verbindung=Verbindung.VERBUNDEN if verbunden else Verbindung.GETRENNT
        )
        self.quelle = SimpleNamespace(echtzeit=False)
        self.acc_zuletzt: float | None = None
        self.zaehl_satz = None
        self.angefordert: dict[str, tuple[int, int]] = {}

    def uhr(self) -> float:
        return self.t

    def acc_anfordern(self, zweck: str, rate_hz: int, bereich_g: int) -> None:
        self.angefordert[zweck] = (rate_hz, bereich_g)

    def acc_freigeben(self, zweck: str) -> None:
        self.angefordert.pop(zweck, None)

    @property
    def acc_anforderungen(self) -> dict[str, tuple[int, int]]:
        return dict(self.angefordert)

    acc_rate_hz = None  # kein Rahmen im Puffer

    def acc_reihe(self, von: float, bis: float, *, rate=None, min_s: float = 2.0):
        return None

    def acc_fenster(self, von: float, bis: float, min_s: float = 2.0):
        return None

    def kontext(self, was: str, **felder):
        return None


class Text:
    """Ein Control wie ``ft.Text``: ``value`` und ``update()`` — mehr braucht das Nachziehen
    nicht."""

    def __init__(self, kaputt: bool = False) -> None:
        self.value: str | None = None
        self.updates = 0
        self.kaputt = kaputt

    def update(self) -> None:
        if self.kaputt:
            raise RuntimeError("nicht auf der Seite")
        self.updates += 1


def _zaehllauf(**mehr) -> tuple[SimpleNamespace, Lauf, Einheitslauf, ZaehlBaustein]:
    lauf = Lauf()
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps", **mehr)
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    state = SimpleNamespace(einheit=e, einheit_beobachter={}, messlauf=lauf)
    return state, lauf, e, z


def _wdh() -> Exercise:
    return Exercise(name="Kniebeuge", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))


def test_wann_es_die_zaehlzeile_gibt() -> None:
    """Der Knopf ist die Messung mit dem Beschleunigungssensor (P118): ein Gerät mit ACC,
    verbunden (eine Aufnahme braucht es nicht), an der Übung ein Schalter an, nicht beim
    Nachtragen."""
    assert zs.geraet_kann_zaehlen(Lauf()) and zs.geraet_kann_zaehlen(Lauf(VERITY_SENSE))
    assert not zs.geraet_kann_zaehlen(Lauf(UHR_BROADCAST))
    assert not zs.geraet_kann_zaehlen(Lauf(verbunden=False))
    assert not zs.geraet_kann_zaehlen(None)

    wdh = _wdh()
    halten = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    atmen = Exercise(name="Box Breathing", typen=["Atmung"])
    assert zs.knopf(wdh) == "Wdh. zählen" and zs.knopf(atmen) == "Atmung erfassen"
    assert zs.knopf(halten) == "" and not zs.zaehlen_an(halten)

    state = SimpleNamespace(messlauf=Lauf())
    assert zs.sichtbar(state, wdh) and zs.sichtbar(state, atmen)
    assert not zs.sichtbar(state, halten)
    assert not zs.sichtbar(state, wdh, nachtrag=object())  # Nachtragen: nie
    assert not zs.sichtbar(SimpleNamespace(messlauf=None), wdh)
    assert not zs.sichtbar(SimpleNamespace(messlauf=Lauf(UHR_BROADCAST)), wdh)


def test_texte_folgen_dem_zaehlen() -> None:
    state, lauf, e, z = _zaehllauf()
    assert zs.zaehl_teil(state, "u1") is None  # die Einheit läuft noch nicht
    e.starten()
    assert zs.zaehl_teil(state, "u1") is z and zs.zaehl_teil(state, "u1", "i1") is z
    assert zs.zaehl_teil(state, "u1", "i2") is None and zs.zaehl_teil(state, "u2") is None
    assert lauf.angefordert == {"zaehlen": (50, 8)}

    # Bis die ersten Proben kommen
    assert zs.zahl_text(z) == "0" and zs.klein_text(z) == "Sensor startet …"
    assert zs.kurz_text(z) == "Sensor startet …"
    assert zs.leisten_text(z) == "Zählen · Kniebeuge · Sensor startet …"
    assert zs.sensor_text(state) == "Sensor …"
    # Daten kommen, noch keine Periode
    lauf.acc_zuletzt = lauf.t
    assert zs.klein_text(z) == "…" and zs.kurz_text(z) == "…"
    # Der Sensor zählt
    assert z.satz is not None
    z.satz.sensor = 11
    assert zs.zahl_text(z) == "11" and zs.klein_text(z) == "Sensor 11 · Prototyp"
    assert zs.kurz_text(z) == "11 Wdh." and zs.leisten_text(z) == "Zählen · Kniebeuge · 11"
    assert zs.sensor_text(state) == "Sensor 11"

    # ±1 ist die Korrektur — angezeigt Sensor plus Korrektur
    assert zs.korrigieren(state, "u1", "i1", +1)
    assert zs.zahl_text(z) == "12" and zs.klein_text(z) == "Sensor 11 · +1 · Prototyp"
    assert not zs.korrigieren(state, "u2", None, +1)  # andere Übung: nichts

    # Nach dem Ende: der Grund, die Summe — ±1 geht nicht mehr
    assert z.fertig()
    assert zs.klein_text(z) == "Zählen fertig" and zs.kurz_text(z) == "12 Wdh."
    assert zs.sensor_text(state) == "" and not zs.korrigieren(state, "u1", "i1", +1)
    assert lauf.angefordert == {}


def test_korrektur_nie_unter_null_und_nur_atmung() -> None:
    state, _, e, z = _zaehllauf()
    e.starten()
    assert zs.korrigieren(state, "u1", None, +1) and zs.zahl_text(z) == "1"
    assert zs.klein_text(z) == "Sensor … · +1 · Prototyp"
    assert zs.korrigieren(state, "u1", None, -1) and zs.zahl_text(z) == "0"
    assert not zs.korrigieren(state, "u1", None, -1)  # unter 0 geht es nicht


def test_texte_der_atmung() -> None:
    """Nur Atmung (A3): die große Zahl sind die Atemzüge, darunter „Atmung 14 · 12/min ▲ ·
    Prototyp“, ±1 korrigiert die Atemzüge; bei Wdh + Atmung bleibt die Zahl die der
    Wiederholungen, und `atem_text` gibt die Zeile „Atmung 12/min ▲“ dazu. Was der Prototyp
    meldet, setzt der Test als Momentaufnahme."""
    from hrv_core.prototyp.atemzuege import Stand

    state, lauf, e, z = _zaehllauf(wiederholungen=False, atmung=True)
    e.starten()
    assert lauf.angefordert == {"zaehlen": (50, 8)}
    assert zs.zahl_text(z) == "0" and zs.klein_text(z) == "Sensor startet …"
    assert zs.kurz_text(z) == "Sensor startet …"
    assert zs.sensor_text(state) == ""  # die Marken-Leiste zeigt nur gezählte Wiederholungen
    lauf.acc_zuletzt = lauf.t
    assert zs.klein_text(z) == "…" and zs.kurz_text(z) == "Atmung 0 · –"
    assert zs.atem_rate_text(z) == "–" and zs.atem_phase(z) == "" and zs.atem_text(z) == ""
    live = z._atem_live
    assert live is not None
    z._atem_stand = Stand(100.0, 14, "ein", 12.0, True, ())
    live.stand = lambda: z._atem_stand  # type: ignore[method-assign]  # auch am Ende
    z._atem_rate = 12.0
    assert zs.zahl_text(z) == "14" and zs.atemzuege(z) == 14
    assert zs.klein_text(z) == "Atmung 14 · 12/min ▲ · Prototyp"
    assert zs.kurz_text(z) == "Atmung 14 · 12/min ▲"
    assert zs.leisten_text(z) == "Zählen · Kniebeuge · Atmung · 14 · 12/min ▲"
    assert zs.atem_rate_text(z) == "12/min" and zs.atem_phase(z) == "▲"
    assert zs.atem_text(z) == ""  # die dritte Zeile gibt es nur bei Wdh + Atmung
    # ±1 gilt den Atemzügen — nie unter 0
    assert zs.korrigieren(state, "u1", "i1", +1) and zs.zahl_text(z) == "15"
    assert zs.klein_text(z) == "Atmung 14 · +1 · 12/min ▲ · Prototyp"
    z._atem_stand = Stand(101.0, 14, "aus", 12.0, True, ())
    assert zs.korrigieren(state, "u1", "i1", -1) and zs.korrigieren(state, "u1", "i1", -1)
    assert zs.zahl_text(z) == "13" and zs.klein_text(z) == "Atmung 14 · −1 · 12/min ▼ · Prototyp"
    assert [x.daten for x in e.takt() if x.art == "korrektur"] == [
        {"delta": 1, "satz": 0, "zaehlart": "atem"},
        {"delta": -1, "satz": 0, "zaehlart": "atem"},
        {"delta": -1, "satz": 0, "zaehlart": "atem"},
    ]
    assert z.fertig()
    assert zs.klein_text(z) == "Atmung fertig" and zs.kurz_text(z) == "13 Atemzüge"
    assert not zs.korrigieren(state, "u1", "i1", +1)

    state, lauf, e, z = _zaehllauf(atmung=True)
    e.starten()
    lauf.acc_zuletzt = lauf.t
    assert z.satz is not None
    z.satz.sensor = 11
    assert zs.zahl_text(z) == "11" and zs.klein_text(z) == "Sensor 11 · Prototyp"
    assert zs.atem_text(z) == ""  # noch keine Proben beim Atem-Prototyp
    live = z._atem_live
    assert live is not None
    z._atem_stand = Stand(100.0, 3, "aus", None, False, ("zu_kurz",))
    live.stand = lambda: z._atem_stand  # type: ignore[method-assign]
    assert (
        zs.atem_text(z) == "Atmung – ▼"
        and zs.leisten_text(z) == "Zählen · Kniebeuge · 11 · Atmung – ▼"
    )
    z._atem_rate = 12.0
    assert zs.atem_text(z) == "Atmung 12/min ▼"
    assert zs.korrigieren(state, "u1", "i1", +1) and zs.zahl_text(z) == "12"  # ±1: die Sätze
    assert z.atem_korrektur == 0 and z.korrektur == 1
    assert z.fertig() and zs.atem_text(z) == "Atmung 3 · 12/min"


def test_nachziehen_aendert_nur_texte() -> None:
    """Jeder Takt zieht Zahl und kleine Zeile nach (``einheit_beobachter``) — eine Zählzeile
    einer anderen Übung bleibt, ein Control, das nicht (mehr) auf der Seite steht, stört
    nicht."""
    state, lauf, e, z = _zaehllauf()
    zahl, klein = Text(), Text()
    fremd = Text()
    atem = Text()
    zs.anmelden(state, "plan", zs.ZaehlAnzeige("u1", "i1", zahl=zahl, klein=klein, atem=atem))
    zs.anmelden(state, "andere", zs.ZaehlAnzeige("u2", None, zahl=fremd))
    zs.anmelden(state, "kaputt", zs.ZaehlAnzeige("u1", None, zahl=Text(kaputt=True)))
    assert set(state.zaehl_anzeigen) == {"plan", "andere", "kaputt"}
    beobachter = state.einheit_beobachter[zs.BEOBACHTER]

    beobachter()  # vor dem Start: nichts
    assert zahl.value is None and zahl.updates == 0
    e.starten()
    lauf.acc_zuletzt = lauf.t
    assert z.satz is not None
    z.satz.sensor = 7
    beobachter()
    assert (zahl.value, klein.value, atem.value) == ("7", "Sensor 7 · Prototyp", "")
    assert zahl.updates == klein.updates == atem.updates == 1  # ohne „Atmung“: leer
    assert fremd.value is None and fremd.updates == 0
    # ±1 zieht sofort nach, ohne auf den Takt zu warten
    assert zs.korrigieren(state, "u1", "i1", +1)
    assert zahl.value == "8" and zahl.updates == 2

    zs.abmelden(state, "plan")
    zs.abmelden(state, "gibt es nicht")
    z.satz.sensor = 9
    beobachter()
    assert zahl.value == "8"  # abgemeldet: bleibt stehen


def test_protokollfeld_atmung_kennt_die_planuebung() -> None:
    """Prüfrunde A6, Befund 4: Lief die Atemübung als Planübung, die „Atmung“ in ihrer Karte
    abschaltet, ist die Messung keine Atemübung (`atmung_an(uebung, item)`). Die Notiz der
    Messdatei nennt Kurzcode und Einheit; deren Zeitleiste (Repository oder die laufende im
    Speicher) nennt die Planübung."""
    atmen = Exercise(name="Box Breathing", typen=["Atmung"])
    aus = PlanItem(exercise_id=atmen.id, acc=SensorWahl(atmung=False))
    zeitleiste = {
        "e1": [
            Ereignis(0.0, "plan", "uebung_start", "", {"uebung": atmen.id, "planuebung": aus.id})
        ],
        "e2": [Ereignis(0.0, "plan", "uebung_start", "", {"uebung": atmen.id})],
    }
    state = SimpleNamespace(
        uebungen=SimpleNamespace(alle=lambda mit_archivierten=False: [atmen]),
        plaene=SimpleNamespace(item_laden=lambda i: aus if i == aus.id else None),
        einheiten=SimpleNamespace(ereignisse=lambda i: zeitleiste.get(i, [])),
        einheit=None,
    )
    haken = zs.atmung_protokoll(state)

    def notiz(einheit: str) -> dict:
        return {
            "text": "Box Breathing: Start",
            "uebungen": [kurzcode(atmen.id)],
            "marke": {"quelle": "plan", "art": "uebung_start", "einheit": einheit},
        }

    assert haken([notiz("e1")]) is None  # es lief eine andere Übung: kein Feld
    assert haken([notiz("e2")]) == {"art": "uebung", "uebung": kurzcode(atmen.id)}
    assert haken([notiz("e1"), notiz("e2")]) == {"art": "uebung", "uebung": kurzcode(atmen.id)}
    # Die laufende Einheit zählt aus dem Speicher, auch ohne Repository
    laufend = SimpleNamespace(id="e3", ereignisse=zeitleiste["e1"])
    state.einheit, state.einheiten = laufend, None
    assert haken([notiz("e3")]) is None
    assert haken([notiz("unbekannt")]) == {"art": "uebung", "uebung": kurzcode(atmen.id)}
