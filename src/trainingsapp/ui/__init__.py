"""Alles Flet-Spezifische.

Bewusst dünn: keine Rechenlogik hier. Views rufen Funktionen aus `core/`,
`data/`, `hrv_core/` und `devices/` auf. Das hält Flet-Versionswechsel und
einen möglichen Umstieg auf das deklarative Modell lokal.
"""
