-- Private Pakete (U7, Ben 9.11.2026, docs/plan_paketinhalte.md §11, F9).
--
-- Ein privates Paket kommt verschlüsselt (core/privat.py); die App merkt sich den Code, mit
-- dem es sich öffnen ließ, und für wen es ist — Updates entschlüsselt sie damit von selbst,
-- „Zugang anzeigen“ zeigt Link und Code für ein zweites Gerät. JSON: {"code", "fuer"}.

ALTER TABLE package ADD COLUMN access_json TEXT;

-- Ein eigenes Paket (U4) lässt sich privat weitergeben: verschlüsselt mit diesem Code, der über
-- alle Fassungen gleich bleibt (NULL = offen).
ALTER TABLE own_package ADD COLUMN access_code TEXT;
