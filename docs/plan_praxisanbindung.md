# Plan: Praxisanbindung als zweite App statt Praxis-Edition

Stand 20.10.2026: **Richtungsentscheidung, nichts gebaut.** Ben (Sicherheitsdurchsicht
S5): „Ist es möglich, keine eigene App als Praxisversion bauen zu müssen, sondern einfach
zwei Apps zu haben, wobei die zweite als Kommunikationsportal dient? Dann ist und bleibt
die Solo-Edition eine solche, und die Praxisanbindungs-App greift auf die Solo-App zu und
verwaltet den Dateiaustausch, neue Übungen usw.“ — Ja. Festgehalten als Richtung; die
Edition `praxis` im Code bleibt vorerst stehen, wird aber nicht weiter ausgebaut.

## Warum zwei Apps

- **Die Solo-App bleibt, was sie verspricht:** alles auf dem Gerät, keine
  Serververbindung, keine fremden Daten, keine PIN, keine Handlungsempfehlung aus
  Messwerten (`docs/recht/00_zweckbestimmung.md`). Ein Store-Eintrag mit einer
  Datensicherheitsangabe (`docs/recht/80_store_freigaben.md`).
- **Alles Heikle liegt in einer App:** Patientendaten auf dem Gerät der Therapeutin,
  Verschlüsselung (S5), PIN, Serverkontakt, Auftragsverarbeitung, Einwilligungen. Die
  Zweckbestimmung dieser App kann enger und ehrlicher gefasst werden; eine spätere
  Einstufung als Medizinprodukt trifft nur sie.
- **Kein Code zweimal:** Heute halten `config.ist_aktiv(…)`-Schalter zwei Editionen in
  einem Quelltext; was `praxis` je brauchen sollte (`sync`, `nachrichten`,
  `zugewiesene_plaene`, `zugewiesene_kurse`, `profil_sperre`, `physiologische_steuerung`)
  ist entweder ungebaut oder nur ein Schalter. Mit der zweiten App entfällt das.

## Was die Solo-App dafür kann (und was fehlt)

| Richtung | Weg | Stand |
|---|---|---|
| Solo → Praxis: Messungen, Einträge | Export-ZIP (raw-v1-Messdateien ohne `adresse`, Diagnose maskiert, Einträge als JSON; `core/hrv_export.py`, `docs/kompatibilitaet.md`) über das Teilen-Menü des Systems **an die zweite App** | gebaut (Teilen an beliebige App) |
| Praxis → Solo: Übungen, Pläne, Kurse | **Übungspakete** (`docs/uebungspakete.md`): Die zweite App ist eine Paketquelle oder legt eine Paketdatei ab | gebaut (Datei/Quelle); fehlt: „Datei an trainingsapp“ (Intent `ACTION_SEND`/`VIEW` für `.json`-Pakete und `.zip`), damit die Übergabe ohne Dateimanager geht |
| Praxis → Solo: Zuweisung eines Plans oder Kurses | als Paket mit Plan-Vorlage bzw. Kurs (`kurse[]`, Formatversion 2); „zugewiesen“ = Herkunft im Paketkopf, keine Sonderlogik | Pakete tragen Pläne nur als Kurs-Vorlagen — Plan-Vorlagen außerhalb von Kursen sind K-F? (Katalog) |
| Praxis → Solo: Nachrichten | nicht in der Solo-App. Nachrichten liest die Person in der zweiten App | — |
| Solo → Praxis: Rückmeldung „Plan gemacht“ | im Export-ZIP (Einträge); ein kleinerer „Berichtsexport“ (nur Einträge, keine Messungen) wäre sinnvoll | Katalog |
| GPS | **nie** — auch nicht an die zweite App (`docs/plan_gps.md`, Regel 0) | Regel |

Die Solo-App bekommt also genau zwei kleine Ergänzungen: **Empfang** (Datei an
trainingsapp → Paketimport bzw. Wiederherstellen aus einem Export) und ein
**Berichtsexport**. Beides nützt auch ohne Praxis (Umzug, Sicherung, Teilen mit einer
Trainerin).

## Was die zweite App trägt

- Empfang des Export-ZIPs aus dem Teilen-Menü, Zuordnung zur Patientenakte, Upload zum
  Praxisserver (praxis_gui / Briefkasten) — verschlüsselt, mit Einwilligungsnachweis
  (`docs/recht/20_einwilligung.md`).
- Verschlüsselte Ablage auf dem Gerät (Schlüssel im Android Keystore / iOS Keychain),
  PIN oder Biometrie, Löschkonzept (`40_toms.md`).
- Pakete aus der Praxis an die Solo-App: als Paketquelle (lokaler, signierter Index —
  Feld `signatur` ist in `docs/uebungspakete.md` reserviert) oder per „Senden an“.
- Nachrichten, Termine, später Auswertung mit Handlungsempfehlung — alles, was eine
  medizinische Aussage ist, nur hier.
- Eigener Store-Eintrag, eigene Datenschutzerklärung, eigene Zweckbestimmung.

## Was im Code zu tun ist (später, in dieser Reihenfolge)

1. Katalog: Praxis-Fragen (P-Nummern mit „Praxis“, `profil_sperre`, `sync`-Felder in
   Migration 001) auf diesen Plan umhängen; nichts löschen.
2. Solo-App: Empfang „Datei an trainingsapp“ (Android-Intent-Filter über
   `[tool.flet.android]`, iOS `CFBundleDocumentTypes`) → `ui/views/pakete.py` Import bzw.
   Wiederherstellen; Berichtsexport in `core/hrv_export.py`.
3. Zweite App als eigenes Repo (privat, wie `trainingsapp-praxis`), Flet, nutzt
   `hrv_core` für die Formate; teilt sich mit praxis_gui den Briefkasten.
4. Wenn die zweite App steht: Edition `praxis` und ihre Schalter aus `config.py`
   entfernen, `docs/recht/` entsprechend vereinfachen (ein Produkt je App).

Verwandt: S5 (Verschlüsselung — damit allein Sache der zweiten App), S3 (Paketquellen
mit Quellenbindung: die zweite App ist eine Quelle wie jede andere),
`docs/plan_anhaenge.md` (Fotos reisen, wenn überhaupt, nur per „Teilen“ am einzelnen Anhang).
