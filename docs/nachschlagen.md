# Nachschlagen

Externe Quellen, die beim Arbeiten an der App immer wieder gebraucht werden.
Kein Lernstoff — nur Links, sortiert nach Thema.

## Flet

- **Dokumentation:** https://flet.dev/docs — Controls, Typen, Anleitungen.
- **Icons visuell durchsuchen:** https://studio.flet.dev/gallery/run/apps/icons_browser/
  — zeigt alle `ft.Icons.*` gerendert, mit Suche nach Flet-Namen. Die reine
  Namensliste unter https://flet.dev/docs/types/icons zeigt keine Bilder.
- **Material Icons (Google):** https://fonts.google.com/icons — dieselben Icons,
  gerendert und suchbar. Der Name dort in Großbuchstaben mit Unterstrichen ist
  der Flet-Name: `check` → `ft.Icons.CHECK`, `monitor heart` → `ft.Icons.MONITOR_HEART`.
- **Farben:** https://flet.dev/docs/types/colors — Material-Farbpalette (`ft.Colors.*`).
- **Pakete für Android/iOS:** https://pypi.flet.dev — was dort fehlt, gibt es auf
  dem Handy nicht (siehe [architektur.md](architektur.md)).

## Werkzeuge

- **uv:** https://docs.astral.sh/uv/
- **ruff:** https://docs.astral.sh/ruff/
- **pytest:** https://docs.pytest.org/

## Bluetooth / Sensoren

- **Heart Rate Service (GATT):** https://www.bluetooth.com/specifications/specs/heart-rate-service-1-0/
  — Aufbau der HR-Measurement-Notification, die `devices/` parst.
- **bleak:** https://bleak.readthedocs.io/
