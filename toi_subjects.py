"""Tematy NATS, ktore TOI publikuje (i czyta), wg reformy NATS: <class>.<realm>.<scope>.<element>.<item>
(araucaria-project/oca_nats_config#2; nazwy jak na stronie zespolu "OCM NATS Subjects", przejscie 2026-11).

- NEW: jedyne tematy, ktore TOI czyta; wszystkie stanowiska TOI przechodza naraz.
- DUAL: tematy czytane takze poza TOI (oca_monitor, pms/Halina) - TOI nadaje je dodatkowo pod stara nazwa (OLD),
  dopoki tamci nie przejda.
- HISTORY_FROM_OLD: czytniki czytaja najpierw stary temat (historie albo ostatnia wiadomosc, do konca), potem nowy -
  bez luki po przejsciu (flaty, log, focus, punkt odniesienia focusa, przelaczniki, obserwatorzy, lista kontrolna).
  Stare tematy (poza DUAL) przestaja dostawac wiadomosci, wiec po kilku dobach mozna to wylaczyc.
- Komunikaty (tic.status.ocm.messages, tic.status.<tel>.toi.message) - pozniej, razem z overwatchami.
"""

import logging

from serverish.messenger import get_reader
from serverish.messenger.msg_publisher import get_publisher

logger = logging.getLogger(__name__)

NEW = {
    "log": "journal.toi.{tel}.self.log",                        # log operatora (~51% dawnego tic.status)
    "plan_log": "journal.toi.{tel}.self.plan",                  # wykonane OB
    "ob": "status.toi.{tel}.self.ob",                           # biezacy OB (oca_monitor)
    "status": "status.toi.{tel}.self.switches",                 # wentylatory, lampy, swiatla (oca_monitor, Halina)
    "plan": "data.toi.{tel}.self.plan",                         # plan nocy z kursorem (oca_monitor)
    "flat": "data.toi.{tel}.camera.flat",                       # rekord kazdej ekspozycji flat
    "focus": "data.toi.{tel}.camera.focus_sample",              # wynik ostatniego autofocusa (krzywa V)
    "focus_record": "data.toi.{tel}.camera.focus_run",          # podsumowanie autofocusa (log focusa)
    "switch_synchro": "status.toi.{tel}.self.switch_synchro",   # przelaczniki GUI wspolne dla stanowisk
    "focus_reference": "status.toi.{tel}.focuser.focus_reference",   # punkt odniesienia focus adjust
    "observers": "status.toi.oca.self.observers",               # obserwatorzy nocy
    "checklist": "status.toi.oca.self.checklist",               # lista kontrolna dnia
}

OLD = {
    "log": "tic.status.{tel}.toi.log",
    "plan_log": "tic.status.{tel}.toi.plan_log",
    "ob": "tic.status.{tel}.toi.ob",
    "status": "tic.status.{tel}.toi.status",
    "plan": "tic.status.{tel}.toi.plan",
    "flat": "tic.status.{tel}.toi.flat",
    "focus": "tic.status.{tel}.toi.focus",
    "focus_record": "tic.status.{tel}.toi.focus_record",
    "switch_synchro": "tic.status.{tel}.toi.switch_synchro",
    "focus_reference": "tic.status.{tel}.toi.focus_reference",
    "observers": "tic.status.ocm.observers",
    "checklist": "tic.status.ocm.checklist",
}

DUAL = {"ob", "status", "plan"}     # czytane poza TOI: nadawane tez pod stara nazwa
HISTORY_FROM_OLD = True             # przejscie bez luki w historii; wylaczyc po kilku dobach od przejscia


def subject(name, tel=None):
    return NEW[name].format(tel=tel)


def old_subject(name, tel=None):
    return OLD[name].format(tel=tel)


class ToiPublisher:
    """publisher tematu TOI: nowy temat, a dla DUAL takze stary (ta sama wiadomosc)"""

    def __init__(self, name, tel=None):
        self.name = name
        self.publishers = [get_publisher(subject(name, tel))]
        if name in DUAL:
            self.publishers.append(get_publisher(old_subject(name, tel)))

    async def publish(self, data, timeout=10, **kwargs):
        await self.publishers[0].publish(data=data, timeout=timeout, **kwargs)
        for old in self.publishers[1:]:
            try:        # stary temat to tylko zgodnosc - jego blad nie moze zatrzymac nowego
                await old.publish(data=data, timeout=timeout, **kwargs)
            except Exception as e:
                logger.warning(f'TOI: old subject for {self.name}: {e!r}')


def toi_publisher(name, tel=None):
    return ToiPublisher(name, tel)


async def history_reader(name, tel, start=None):
    """(data, meta) tematu TOI: najpierw stary temat do konca (nowait), potem nowy - takze na biezaco. `start`: od tej
    chwili (deliver_policy='by_start_time'), None: ostatnia wiadomosc ('last') - stan, ktory po przejsciu jest jeszcze
    tylko w starym temacie (punkt odniesienia focusa, przelaczniki, obserwatorzy, lista kontrolna)."""
    policy = {"deliver_policy": "last"} if start is None else {"deliver_policy": "by_start_time", "opt_start_time": start}
    if HISTORY_FROM_OLD:
        old = get_reader(old_subject(name, tel), nowait=True, **policy)
        try:
            async for data, meta in old:
                yield data, meta
        except Exception as e:
            logger.warning(f'TOI: history of {old_subject(name, tel)}: {e!r}')
        finally:
            try:
                await old.close()
            except Exception:
                pass
    async for data, meta in get_reader(subject(name, tel), **policy):
        yield data, meta
