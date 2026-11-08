-- Workout und Ablauf werden eins (K4, Ben 8.11.2026, P106; docs/plan_uhren.md §4.7).
-- „Nach dem Timer automatisch weiter“ (`auto_next`, Migration 020) geht im Übergang hart auf:
-- Pläne, die automatisch weitergingen, sind jetzt „hart“. `auto_next` und `pause_no_timer`
-- bleiben als Spalten (Paketformat), gelesen wird nur noch `uebergang_hart`.
UPDATE plan SET uebergang_hart = 1 WHERE auto_next = 1;
