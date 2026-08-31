"""L01, Beispiel 3 — die Domäne läuft ohne Oberfläche.

Start:  uv run python docs/tutorial/L01_werkzeuge/beispiel_03.py

Das hier ist der Beweis für die Importregel: kein `import flet` weit und breit,
und trotzdem passiert etwas Nützliches. Genau deshalb sind unsere Tests schnell
und brauchen keinen Bildschirm.
"""

from trainingsapp.core.units import parse_shorthand
from trainingsapp.hrv_core import compute_time_domain

print("Kurzschrift-Eingabe")
print("-" * 40)
for text in ["3x15", "3x12 @40kg", "45°", "1:30", "einfach so"]:
    print(f"  {text:14} → {parse_shorthand(text)}")

print()
print("HRV aus einer RR-Reihe")
print("-" * 40)

# Eine ruhige Reihe: ~800 ms Abstand, also etwa 75 Schläge pro Minute,
# mit leichter Schwankung.
rr = [800, 812, 795, 820, 788, 805, 815, 792, 808, 798]

werte = compute_time_domain(rr)
assert werte is not None

for name, einheit in [
    ("mean_rr", "ms"),
    ("mean_bpm", "bpm"),
    ("sdnn", "ms"),
    ("rmssd", "ms"),
    ("pnn50", "%"),
]:
    print(f"  {name:10} {werte[name]:8.2f} {einheit}")

print()
print("Probier es selbst: ändere die Zahlen in `rr` und schau, was passiert.")
print("Sehr gleichmäßige Abstände → kleines RMSSD. Unruhige → großes.")
