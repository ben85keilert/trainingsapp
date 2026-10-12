"""L06, Beispiel 1 — ResultSpec, Kurzschrift und die Kopie der Spezifikation.

Start:  uv run python docs/tutorial/L06_flexible_notation/beispiel_01.py

Kein Flet. Nur die Domäne — und das Szenario, in dem die Kopie Daten rettet.
"""

import json
from dataclasses import replace

from trainingsapp.core.models import SessionEntry
from trainingsapp.core.result_spec import (
    SPEC_HALTEN,
    SPEC_SAETZE_WDH,
    FieldSpec,
    FieldType,
    ResultSpec,
)
from trainingsapp.core.units import parse_shorthand

# 1. Eine Spezifikation ist Daten. Sie überlebt den Weg durch JSON unverändert.
als_json = json.dumps(SPEC_SAETZE_WDH.to_dict(), ensure_ascii=False, indent=2)
print("SPEC_SAETZE_WDH als JSON (so steht es in exercise.result_spec_json):")
print(als_json)
zurueck = ResultSpec.from_dict(json.loads(als_json))
print("Rundlauf verlustfrei:", zurueck == SPEC_SAETZE_WDH)
print()

# 2. Vorbelegung und kompakte Anzeige kommen aus der Spezifikation.
print("defaults():        ", SPEC_SAETZE_WDH.defaults())
print("format_shorthand():", SPEC_SAETZE_WDH.format_shorthand({"sets": 3, "reps": 15}))
print("Haltezeit:         ", SPEC_HALTEN.format_shorthand({"sets": 3, "hold": 45}))
print()

# 3. Die Kurzschrift zerlegt Text in Feldwerte — was nicht erkannt wird, fehlt.
for text in ("3x15", "3x12 @40kg", "45°", "1:30", "irgendwas"):
    print(f"parse_shorthand({text!r:14}) → {parse_shorthand(text)}")
print()

# 4. Das Szenario: Ein Jahr lang "3x15" dokumentiert …
alter_eintrag = SessionEntry(
    result={"sets": 3, "reps": 15},
    spec_snapshot=SPEC_SAETZE_WDH,  # die Kopie von damals
)

# … dann bekommt die Übung ein Gewichtsfeld und eine neue Kurzschrift.
neue_spec = replace(
    SPEC_SAETZE_WDH,
    fields=[
        *SPEC_SAETZE_WDH.fields,
        FieldSpec("weight", FieldType.WEIGHT, "Gewicht", unit="kg", default=0),
    ],
    shorthand="{sets}x{reps} @{weight}kg",
)

print("Alter Eintrag, angezeigt mit …")
print("  … der NEUEN Spezifikation:", repr(neue_spec.format_shorthand(alter_eintrag.result)))
print("  … seiner eigenen Kopie:   ", repr(alter_eintrag.shorthand()))
print()
print("Die neue Spezifikation kennt 'weight', der alte Eintrag nicht — die Vorlage")
print("scheitert und fällt auf eine Aufzählung zurück. Mit der Kopie bleibt '3x15'.")
print()

# 5. Ohne Kopie gibt es nur noch die rohe Aufzählung.
ohne = SessionEntry(result={"sets": 3, "reps": 15}, spec_snapshot=None)
print("Ganz ohne Kopie:", repr(ohne.shorthand()))
