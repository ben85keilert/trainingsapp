"""Gerätezugang mit Flet-Bezug — die einzige Stelle, die `flet_ble` kennt.

`devices/` bleibt flet-frei; hier wird die Flet-Erweiterung in den
`BleTransport` aus `devices/gatt.py` übersetzt.
"""
