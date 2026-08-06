# Schweigepflicht (§ 203 StGB)

## Worum es geht

Wer als Angehöriger eines Heilberufs ein anvertrautes Geheimnis offenbart, macht
sich strafbar. Das gilt **zusätzlich** zur DSGVO und ist nicht durch eine
Einwilligung in die Datenverarbeitung allein erledigt.

Seit 2017 stellt § 203 Abs. 3 StGB klar, dass die Einbeziehung „mitwirkender
Personen" zulässig ist — dazu zählen IT-Dienstleister. Aber nur unter Auflagen.

## Was daraus folgt

- **Dienstleister zur Verschwiegenheit verpflichten**, schriftlich. Der
  AVV nach Art. 28 DSGVO genügt dafür **nicht** automatisch.
- Nur so viel offenbaren, wie für die Leistung erforderlich ist.
- Die Verpflichtung gilt weiter, wenn der Dienstleister wechselt oder das
  Vertragsverhältnis endet.
- Ein Verstoß des Dienstleisters kann auf den Praxisinhaber zurückfallen.

## Checkliste

- [ ] VServer-Hoster schriftlich nach § 203 Abs. 4 StGB verpflichtet
- [ ] Etwaige Unterauftragnehmer ebenfalls
- [ ] Wartungszugänge geregelt: wer darf wann worauf, und wird es protokolliert
- [ ] Patienten darüber informiert, dass ein Dienstleister eingebunden ist

## Der stärkste Hebel

**Ende-zu-Ende-Verschlüsselung.** Kann der Serverbetreiber die Inhalte technisch
nicht lesen, ist schon zweifelhaft, ob überhaupt ein Offenbaren vorliegt. Das
entschärft § 203 erheblich.

Preis: Schlüsselverwaltung auf den Geräten, und ein verlorenes Gerät kann
bedeuten, dass Daten nicht wiederherstellbar sind. Diese Abwägung gehört vor den
Bau von Edition B — siehe `40_toms.md`.
