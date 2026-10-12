# L06 — Übung

## Aufgabe 1: Spezifikation lesen

1. `SPEC_HALTEN` hat `shorthand="{sets}× {hold}s"`. Was zeigt
   `format_shorthand({"sets": 3})` — und warum genau das?
2. `FieldSpec.quick` ist eine Liste. Warum nicht ein `min`/`max`/`step`-Raster,
   aus dem sich die Chips berechnen lassen? Überlege an `SPEC_SAETZE_WDH`:
   Wiederholungen `[8, 10, 12, 15, 20]`.
3. `chart_metrics` von `SPEC_SAETZE_WDH` ist `["reps"]`, nicht `["sets", "reps"]`.
   Welche Überlegung steckt dahinter? Wann wäre `sets` doch interessant?

## Aufgabe 2: Ein neuer Feldtyp

Füge in Beispiel 2 eine sechste Vorlage „Gehstrecke" hinzu: ein Feld `distance`
vom Typ `DISTANCE` in Metern mit Chips `[500, 1000, 2000, 5000]` und ein Feld
`duration` vom Typ `DURATION`.

Was musst du an `SpecForm` ändern? (Die Antwort sollte dich freuen.)

Dann ein echter neuer Typ: `FieldType.CHOICE` — eine Auswahl aus festen
Werten, etwa Seite `["links", "rechts", "beide"]`. Ergänze ihn in
`core/result_spec.py` (die Optionen können in `quick` stehen) und baue in
`SpecForm._widget` ein `ft.SegmentedButton` dafür. `_lesen` und `setzen`
nicht vergessen.

## Aufgabe 3: `ui/components/spec_form.py`

Übernimm `SpecForm` aus Beispiel 2 nach `src/trainingsapp/ui/components/spec_form.py`
und mache sie fertig für die App:

- `required`-Felder: `werte()` darf nicht stillschweigend ein Feld weglassen.
  Gib ein zweites Ergebnis zurück — `fehlende: list[str]` — oder biete
  `pruefen() -> list[str]` an, das die Labels der fehlenden Pflichtfelder
  liefert und die Felder mit `error` markiert.
- Ungültige Zahlen („abc") markieren statt ignorieren.
- Chips, die den aktuellen Wert tragen, erscheinen ausgewählt (`selected=True`).

Ein Rauchtest in `tests/test_ui_smoke.py` (mit `importorskip`): Für alle vier
Vorlagen lässt sich ein Formular bauen, `werte()` auf dem frischen Formular
liefert `spec.defaults()`, und `setzen({"sets": 5})` gefolgt von `werte()`
gibt die 5 zurück. `setzen` ruft `control.update()` — das scheitert ohne Seite.
Überlege, wie du das im Test umgehst, ohne die Klasse zu verbiegen (Tipp:
ein Parameter oder ein kleiner Stellvertreter wie in `test_ui_smoke.py`).

## Aufgabe 4: `SessionRepo`

Schreibe in `src/trainingsapp/data/repositories.py` eine `SessionRepo`:

```python
class SessionRepo:
    def __init__(self, con: sqlite3.Connection) -> None: ...

    def anlegen(self, session: Session) -> None: ...
    def session_fuer(self, subject_id: str, plan_id: str | None,
                     tag: date) -> Session: ...          # get-or-create: ein Plan an einem Tag
    def eintrag_anlegen(self, session: Session, uebung: Exercise,
                        result: dict[str, Any], note: str = "") -> SessionEntry: ...
    def erledigt(self, session: Session, uebung: Exercise,
                 note: str = "") -> SessionEntry: ...     # nur „gemacht": leeres Ergebnis
    def eintrag_korrigieren(self, alter_eintrag_id: str,
                            result: dict[str, Any]) -> SessionEntry: ...
    def letzter_eintrag(self, subject_id: str, exercise_id: str) -> SessionEntry | None: ...
    def eintraege(self, session_id: str) -> list[SessionEntry]: ...
    def verlauf(self, subject_id: str, metric_key: str) -> list[Measurement]: ...
```

Anforderungen:
- `eintrag_anlegen` setzt **immer** `spec_snapshot` aus `uebung.result_spec`
  und schreibt je `chart_metrics`-Feld eine `measurement`-Zeile
  (`metric_key = f"{exercise_id}:{key}"`, `source = "exercise"`)
- `eintrag_korrigieren` legt einen neuen Eintrag mit `replaces_entry_id` an,
  übernimmt die Kopie des alten (nicht die aktuelle Spezifikation!) und ersetzt
  dessen Kennzahlen
- `eintraege` und `letzter_eintrag` liefern nur gültige Einträge — ersetzte
  nicht
- `letzter_eintrag` ist die Grundlage für „Wie zuletzt"
- `session_fuer` liefert beim zweiten Aufruf am selben Tag dieselbe Session;
  der Tag ist ein **lokaler** Kalendertag (`core.models.tagesgrenzen`), die
  Zeitstempel bleiben UTC
- `erledigt` setzt `started_at`, schreibt aber keine `measurement`-Zeile
- alles in Transaktionen, alles mit Platzhaltern

Tests in `tests/test_repositories.py`:
- Eintrag anlegen und über `eintraege()` lesen: `shorthand()` ergibt „3x15"
- Spezifikation der Übung danach ändern und speichern — der Eintrag zeigt
  weiterhin „3x15"
- `letzter_eintrag` liefert den jüngsten, über Sitzungen hinweg
- Korrektur: `eintraege()` liefert nur den neuen, `verlauf()` enthält den
  alten Wert nicht mehr
- eine Übung ohne `chart_metrics` erzeugt keine `measurement`-Zeile
- `erledigt()` erzeugt keine Kennzahl, zählt aber in `anzahl_am_tag()`
- zwei Einträge um 23:30 und 00:30 Ortszeit liegen an zwei verschiedenen Tagen

## Zum Nachdenken

1. Beispiel 2: Tippe auf dem Handy dreimal „3x12" ein — einmal per Chips,
   einmal per Kurzschrift, einmal per Tastatur in die Felder. Zähle die Tipper.
2. „Wie zuletzt" nimmt den letzten Eintrag **dieser Übung**. Wäre der letzte
   Eintrag **dieses Plans** besser? Wann unterscheiden sie sich?
3. Ein Eintrag speichert seine Spezifikation. Warum speichert eine `Session`
   nicht auch den Plan, nach dem trainiert wurde? Oder sollte sie?

[Lösungen](loesung/)
