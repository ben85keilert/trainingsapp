"""Beispiel für Testdaten: Plan mit Einträgen und Notizen, Notizen zum Tag, Tagesfelder.

Aufruf: ``uv run python daten_beispiel.py <arbeitsordner>/daten`` — **vor** `starten.sh`.
Als Vorlage gedacht: kopieren (ins Scratchpad der Sitzung) und auf das zuschneiden, was die
Fotos zeigen sollen. Nie auf Bens echte Datenbank zeigen.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta

os.environ["TRAININGSAPP_DATA_DIR"] = sys.argv[1]

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.models import DayNote, Plan
from trainingsapp.ui.state import AppState

state = AppState.starten()
profil, heute = state.profil.id, state.heute()


def um(tag, stunde: int, minute: int = 0) -> datetime:
    return datetime.combine(tag, time(stunde, minute)).astimezone()


plan = Plan(name="Morgenrunde", subject_id=profil)
state.plaene.speichern(plan)
uebungen = state.uebungen.alle()[:3]
for u in uebungen:
    state.plaene.uebung_hinzufuegen(plan.id, u.id)
for tage, notiz in ((0, "ging leicht"), (1, "links enger als rechts"), (3, "")):
    tag = heute - timedelta(days=tage)
    session = state.sitzungen.session_fuer(profil, plan.id, tag)
    for k, u in enumerate(uebungen):
        state.sitzungen.eintrag_anlegen(
            session, u, {}, notiz if k == 0 else "", started_at=um(tag, 7, 5 * k)
        )
    if tage == 1:
        state.sitzungen.notiz_setzen(session.id, "Heute zäh, wenig geschlafen.")

tagebuch = next(t for t in state.notiz_tags.alle(profil) if t.fest)
for tage, text, tags in (
    (0, "Guter Tag. Knie ruhig, abends spazieren.", (tagebuch.id,)),
    (1, "Müde, Schulter fest.", (tagebuch.id,)),
    (2, "Idee: Dehnen vor dem Frühstück.", ()),
):
    state.tagesnotizen.speichern(
        DayNote(subject_id=profil, date=heute - timedelta(days=tage), text=text, tag_ids=tags)
    )

ibu = tf.Tagesfeld(
    subject_id=profil,
    name="Ibu",
    spec=tf.spec_bauen(tf.ANZAHL, schnell=[1], varianten=["400", "800"]),
    mehrmals=True,
)
essen = tf.Vorschlag("Ernährung", tf.TEXT).feld(profil)
for feld in (ibu, essen):
    state.tagesfelder.speichern(feld)
state.tageswerte.hinzufuegen(ibu, heute, um(heute, 14, 30), wert=1, variante="400")
state.tageswerte.hinzufuegen(
    ibu,
    heute - timedelta(days=1),
    um(heute - timedelta(days=1), 9),
    wert=1,
    variante="400",
    note="nach dem Laufen",
)
state.tageswerte.einmal_setzen(essen, heute, note="Mittags Gemüse")
state.schliessen()
print("Testdaten in", sys.argv[1])
