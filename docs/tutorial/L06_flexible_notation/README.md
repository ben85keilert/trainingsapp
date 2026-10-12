# L06 — Flexible Notation

**Ziel:** Eingabemasken entstehen aus einer Spezifikation, nicht aus
handgeschriebenen Formularen. Und du verstehst, was Eingabe auf dem Handy
wirklich schnell macht — und was nur so aussieht.

Zeit: drei Stunden.

Das ist die spannendste Lektion des Projekts. Nicht technisch — fachlich. Eine
Trainings-App wird nur benutzt, wenn das Dokumentieren schneller geht als das
Nicht-Dokumentieren. Alles hier dient dieser einen Frage.

---

## 1. Das Problem

„3 x 15." — „45°." — „30 Sekunden halten, drei Sätze." — „62 Sekunden Luft
angehalten." — „Schmerz heute 3 von 10."

Fünf Übungen, fünf Notationen. Die naive Lösung wäre je Übungstyp ein eigenes
Formular. Dann braucht jeder neue Typ einen Programmierer, und die Therapeutin
in Edition B kann keine Übung anlegen, die wir nicht vorgesehen haben.

Die Lösung: **Die Präzision wandert in die Übungsdefinition.** Jede Übung
bringt eine `ResultSpec` mit — eine Beschreibung ihrer Felder. Daraus wird die
Eingabemaske erzeugt. „3x15" und „45°" sind derselbe Mechanismus mit
verschiedenen Daten.

---

## 2. `ResultSpec` lesen

Öffne `src/trainingsapp/core/result_spec.py`. Zwei Dataclasses:

```python
@dataclass(slots=True)
class FieldSpec:
    key: str              # Schlüssel im Ergebnis-Dict: "reps"
    type: FieldType       # int, float, duration, degrees, scale, bool, text …
    label: str            # Beschriftung: "Sätze"
    unit: str | None      # "s", "°", "kg"
    default: Any          # Vorbelegung ohne vorherigen Eintrag
    min / max / step      # Grenzen, z. B. Winkel 0–180
    quick: list[Any]      # Werte, die als Chips erscheinen
    required: bool

@dataclass(slots=True)
class ResultSpec:
    layout: Layout                 # sets, single, timed, freeform
    fields: list[FieldSpec]
    shorthand: str | None          # "{sets}x{reps}" — kompakte Anzeige
    chart_metrics: list[str]       # welche Felder in den Verlauf wandern
```

Ein Ergebnis ist ein einfaches Dict: `{"reps": [15, 15, 15]}`. Die
Spezifikation sagt, wie man es eingibt (`fields`), wie man es anzeigt
(`shorthand`) und was davon im Verlauf landet (`chart_metrics`).

```python
>>> SPEC_SAETZE_WDH.format_shorthand({"reps": [15, 15, 15]})
'3x15'
>>> SPEC_HALTEN.defaults()
{'hold': [30, 30, 30]}
```

Das wichtigste Feld ist das **Satzfeld** (`FieldType.SET_LIST`): Es speichert
eine Liste je Satz — `[15, 15, 15]` — und nimmt die Notation `3x15`, `30`
oder `15/15/20` entgegen ([docs/notation.md](../../notation.md)). Mit
`unit="s"` sind es Haltezeiten. Eine Übung wie Liegestützen trägt beide
Felder, Wiederholungen und Haltezeit; man füllt, was zutrifft.

Fünf Vorlagen gibt es: `SPEC_SAETZE_WDH`, `SPEC_HALTEN`, `SPEC_WDH_ODER_HALTEN`,
`SPEC_WINKEL`, `SPEC_BENCHMARK_ZEIT`. Beim Anlegen einer Übung dienen sie als
Schnellstart; danach wählt man Felder aus dem **Feldvorrat** (`FELDVORRAT`),
jedes bringt Typ und Einheit mit, die Übung legt nur die Chips fest.

`to_dict()` / `from_dict()` sind der Weg in die Datenbank (`result_spec_json`)
und zurück. Beispiel 1 zeigt den Rundlauf.

---

## 3. Aus der Spezifikation Widgets bauen

Das Herz der Lektion ist eine Funktion, die aus einer `ResultSpec` ein
Flet-Control macht — und eine zweite, die aus dem Control wieder ein Dict liest.
Beides zusammen nennen wir `SpecForm`:

```python
form = SpecForm(spec, werte=letzter_eintrag)
page.add(form.control)          # anzeigen
...
ergebnis = form.werte()         # {"reps": [15, 15, 15]}
```

Innen steckt eine **Registrierung je Feldtyp**: ein Dict von `FieldType` auf
eine Funktion, die ein Widget baut.

```python
def _widget(self, f: FieldSpec) -> ft.Control:
    if f.type == FieldType.BOOL:
        return ft.Switch(label=f.label, value=bool(wert))
    if f.type == FieldType.SCALE:
        return ft.Slider(min=f.min or 0, max=f.max or 10, divisions=..., value=wert)
    if f.type == FieldType.TEXT:
        return ft.TextField(label=f.label, multiline=True)
    # alles Zahlenartige: int, float, duration, degrees, weight, distance
    return ft.TextField(label=f.label, keyboard_type=ft.KeyboardType.NUMBER, ...)
```

Das ist der Grund für den Satz im Docstring von `FieldType`: *„Neue Typen hier
ergänzen und in `spec_form.py` ein Widget dafür registrieren — sonst nichts."*
Weder Datenbank noch Ansichten noch Repository müssen einen neuen Typ kennen.

### Lesen ist schwieriger als Schreiben

Ein `TextField` liefert **immer** einen String. `"15"` ist nicht `15`, und
`"1:30"` ist nicht `90`. Das Zurücklesen muss je Typ umwandeln:

| Typ | Eingabe | Ergebnis | Hilfe |
|---|---|---|---|
| `int` | `"15"` | `15` | `int()` |
| `float`, `weight`, `degrees` | `"12,5"` | `12.5` | Komma → Punkt, dann `float()` |
| `duration` | `"1:30"` oder `"90"` | `90.0` | `core.units.parse_dauer()` |
| `bool` | Switch | `True` | direkt |
| `scale` | Slider | `3` | `int()` oder `float()` je nach `step` |

Ungültige Eingaben („abc" in einem Zahlenfeld) ergeben `None`, keinen Absturz.
Das Formular markiert das Feld (`error`), und der Speichern-Knopf prüft
`required`.

Beispiel 2 ist eine komplette `SpecForm` zum Anfassen. Sie wird in der Übung
zur echten `ui/components/spec_form.py`.

---

## 4. Die Reihenfolge der Beschleunigung

Hier liegt die eigentliche Erkenntnis. Es gibt drei Wege, Eingabe zu
beschleunigen — und ihre Reihenfolge ist nicht beliebig.

### 1. Vorbelegung: Ziel aus dem Plan, sonst wie zuletzt

Wer dreimal pro Woche Wadenheben macht, macht fast immer dasselbe wie beim
letzten Mal — oder genau das, was im Plan steht. Deshalb hat die Vorbelegung
drei Stufen, in dieser Reihenfolge:

1. **Das Ziel aus dem Plan** (`plan_item.target`), wenn eines gesetzt ist.
   In der Planansicht ist das Ziel ein Chip: ein Tipp darauf trägt genau diese
   Werte ein. **Null Tipper** für das Formular, einer für den Eintrag.
2. **Der letzte Eintrag** dieser Übung für dieses Profil
   (`SessionRepo.letzter_eintrag()`), wenn es kein Ziel gibt.
3. **`spec.defaults()`**, wenn es auch keinen letzten Eintrag gibt.

Und noch davor steht die nullte Stufe: Ein Tipp auf die Zeile im Plan ist
„gemacht" — ein Eintrag mit leerem Ergebnis, ohne Formular. Er zählt für die
Häufigkeit und den Kalender, nicht für die Kurve. Wer nur abhaken will, sieht
nie ein Formular.

### 2. Chips aus `quick`, numerische Tastatur

Für die 15 %, in denen sich etwas ändert: Die häufigsten Werte stehen als Chips
unter dem Feld — `[1] [2] [3] [4] [5]` für Sätze, `[8] [10] [12] [15] [20]` für
Wiederholungen. **Ein Tipp.** Und wenn doch getippt werden muss:
`keyboard_type=ft.KeyboardType.NUMBER` öffnet auf dem Handy die Zifferntastatur
statt der vollen.

### 3. Kurzschrift-Parser

`core/units.py` kann `"3x12 @40kg"` in `{"reps": [12, 12, 12], "weight": 40.0}`
zerlegen. Das klingt nach dem schnellsten Weg — und ist auf einer
**Handytastatur der langsamste**: `3`, Umschalten auf Buchstaben, `x`,
Umschalten zurück, `1`, `2`. Sechs Tipper mit zwei Tastaturwechseln, für etwas,
das zwei Chips erledigen.

Auf dem Desktop mit Tastatur ist die Kurzschrift großartig. Deshalb bleibt sie —
als drittes Angebot, nicht als erstes. Wer einen Parser **vor** Vorbelegung und
Chips baut, hat ein beeindruckendes Feature, das niemand benutzt.

Beispiel 2 hat alle drei Stufen. Probier auf dem Handy aus, welche du nimmst.

---

## 5. Die Kopie der Spezifikation

Jetzt der Teil, der Daten über Jahre rettet.

Angenommen, du dokumentierst ein Jahr lang „3x15" Wadenheben. Dann entscheidest
du, Gewicht mitzuerfassen, und ergänzst in der Übung ein Feld `weight`. Oder
du benennst `reps` in `wiederholungen` um. Was zeigt die App für die 150
alten Einträge?

Mit der **aktuellen** Spezifikation: `shorthand = "{sets}x{reps} @{weight}kg"`,
aber in alten Einträgen gibt es kein `weight` → `format_shorthand` scheitert
und fällt auf eine Aufzählung zurück. Nach der Umbenennung: Feld
`wiederholungen` fehlt, `reps` wird nicht mehr angezeigt. Die Historie ist
unlesbar, obwohl kein Byte verloren ging.

Deshalb speichert jeder `SessionEntry` eine **Kopie** der Spezifikation, mit der
er erfasst wurde — `spec_snapshot_json`. Angezeigt wird **immer** mit der Kopie:

```python
def shorthand(self) -> str:
    if self.spec_snapshot is None:
        return ", ".join(f"{k} {v}" for k, v in self.result.items())
    return self.spec_snapshot.format_shorthand(self.result)
```

Die Kopie kostet ein paar hundert Byte je Eintrag. Dafür bleibt jeder Eintrag
so lesbar, wie er erfasst wurde — egal wie oft die Übung seitdem umgebaut wurde.
Beispiel 1 spielt genau dieses Szenario durch.

---

## 6. `chart_metrics` → `measurement`

Der Verlauf in L12 soll zeigen: Wiederholungen über die Monate, Haltezeit über
die Wochen, HRV-Kennzahlen über das Jahr. Alles in **einer** Tabelle:
`measurement` mit `metric_key`, `value`, `unit`, `recorded_at`.

`chart_metrics` sagt, welche Felder eines Ergebnisses dorthin kopiert werden:

```python
for key in spec.chart_metrics:                # z. B. ["reps"]
    if (wert := ergebnis.get(key)) is not None:
        Measurement(metric_key=f"{exercise_id}:{key}", value=float(wert),
                    unit=spec.field_by_key(key).unit or "",
                    session_entry_id=eintrag.id, source="exercise")
```

Der `metric_key` kombiniert Übung und Feld, damit „reps" vom Wadenheben nicht
mit „reps" von der Außenrotation vermischt wird. HRV-Kennzahlen bekommen
später Schlüssel wie `hrv:rmssd` — dieselbe Tabelle, derselbe Verlauf.

Warum kopieren statt beim Zeichnen aus `result_json` herausziehen? Weil
`measurement` eine normale Spalte `value REAL` hat, auf der SQL sortieren,
mitteln und filtern kann. JSON in 2 000 Einträgen zu durchsuchen wäre der
langsame Weg — und der Verlauf soll sich sofort öffnen.

Beispiel 3 schreibt Einträge und Kennzahlen in eine Datenbank und fragt den
Verlauf ab.

---

## 7. Einträge sind unveränderlich

`session_entry` hat kein `UPDATE`. Ein Tippfehler wird korrigiert, indem ein
**neuer** Eintrag entsteht, der auf den alten zeigt: `replaces_entry_id`. Beim
Lesen gewinnt der neueste; der alte bleibt als Historie.

Das wirkt umständlich, bis man an Edition B denkt: Wenn Handy und Praxisserver
denselben Eintrag ändern könnten, bräuchte es eine Konfliktregel — und jede
Konfliktregel verliert im Zweifel Daten. Wenn nichts geändert wird, gibt es
nichts zu kollidieren.

Für dich heißt das in der Übung: `SessionRepo` hat `eintrag_anlegen()` und
`eintrag_korrigieren()`, aber kein `eintrag_aendern()`.

---

## 8. Beispiele

```bash
uv run python docs/tutorial/L06_flexible_notation/beispiel_01.py     # Spec, Shorthand, Snapshot
uv run flet run docs/tutorial/L06_flexible_notation/beispiel_02.py   # SpecForm-Werkstatt
uv run python docs/tutorial/L06_flexible_notation/beispiel_03.py     # Einträge und Verlauf
```

Beispiel 2 lohnt sich auf dem Handy (`flet run --android`, siehe L02b): Dort
merkt man den Unterschied zwischen Chips und Kurzschrift.

---

## Stolperfallen

**`TextField.value` ist ein String — immer.** Auch mit
`keyboard_type=NUMBER`. Die Umwandlung gehört in `SpecForm.werte()`, nicht in
die Ansicht.

**Komma.** Deutsche Tastaturen liefern `12,5`. `float("12,5")` ist ein
`ValueError`. Erst `.replace(",", ".")`.

**`NumbersOnlyInputFilter` blockiert den Doppelpunkt.** Für `duration` darf
man ihn nicht setzen, sonst geht `1:30` nicht mehr. Lieber die Tastatur
vorgeben und beim Lesen tolerant sein (`parse_dauer`).

**Chips setzen den Wert, aber die Anzeige bleibt alt.** Nach
`feld.value = "15"` braucht es `feld.update()` (oder `page.update()`). Flets
Auto-Update greift nur am Ende eines Handlers — bei Chips in einer
Fabrikfunktion ist das zwar der Fall, aber verlass dich nicht darauf, wenn
der Wert außerhalb eines Handlers gesetzt wird (etwa durch „Wie zuletzt").

**Der Slider liefert `float`.** Eine Schmerzskala 0–10 will `3`, nicht `3.0`.
Mit `step` entscheiden: ganzzahliger Schritt → `int()`.

**Snapshot vergessen.** Ein `SessionEntry` ohne `spec_snapshot` zeigt sich nur
noch als rohe Aufzählung. `SessionRepo.eintrag_anlegen()` muss die Kopie
**immer** setzen — ein Test dafür gehört dazu.

**`format_shorthand` mit fehlendem Feld.** `"{sets}x{reps}".format(sets=3)` ist
ein `KeyError`. `format_shorthand` fängt das und fällt auf die Aufzählung
zurück. Darauf verlassen, nicht umgehen.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L07: async in Flet**
