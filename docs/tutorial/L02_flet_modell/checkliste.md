# L02 — Checkliste

## Das kann ich jetzt

- [ ] Ich kann einen Control-Baum aus fertigem Code herauslesen
- [ ] Ich weiß, warum `page.update()` nötig ist — und wann `control.update()` besser ist
- [ ] Ich kann `Column`, `Row` und `Container` benutzen und weiß, was `expand` tut
- [ ] Ich verwende Farben aus dem Theme statt fester Werte
- [ ] Ich kann Ereignisse behandeln und über `e.control.data` unterscheiden,
      welches Element es ausgelöst hat

## Wenn ein Haken fehlt

Besonders Punkt 2 ist wichtig — er kostet sonst später viel Zeit. Starte
`beispiel_02.py` noch einmal.

## Was wir als Nächstes bauen

**M1 — die Hülle der App.**

Konkret:
- `src/trainingsapp/ui/app.py` bekommt echte Navigation statt Platzhalter
- die vier Ansichten „Heute", „Übungen", „Messung", „Verlauf" als eigene Dateien
- das Farbschema, hell und dunkel
- der Übungskatalog aus `beispiel_03.py` wandert nach `ui/views/katalog.py` —
  dein erstes Stück Code, das wirklich in der App landet

Vorher aber **L02b: einmal aufs Handy bauen.** Bevor mehr entsteht, wollen wir
wissen, ob das überhaupt funktioniert.
