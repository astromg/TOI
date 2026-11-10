"""Tematy NATS, ktore TOI publikuje (i czyta), wg reformy NATS: <class>.<realm>.<scope>.<element>.<item>
(araucaria-project/oca_nats_config#2; nazwy jak na stronie zespolu "OCM NATS Subjects", przejscie 2026-11).

- NEW: jedyne tematy, ktore TOI czyta; wszystkie stanowiska TOI przechodza naraz.
- DUAL: tematy czytane takze poza TOI (pms/Halina) - TOI nadaje je dodatkowo pod stara nazwa (OLD), dopoki tamci
  nie przejda. DO PODMIANY W HALINIE: ob, status, plan, messages, flat, focus_record (oca_monitor czyta nowe od
  2026-11-10); log nie jest nadawany pod stara nazwa - Halina musi go czytac z journal.toi.<tel>.self.log.
- PREVIOUS / HISTORY_FROM_OLD: tematy, ktorym 2026-11-10 zmienila sie nazwa drugi raz (wolne ogolne nazwy na
  przyszlosc: plan_log, focus_log, focus_curve, flat_log, focus_adjust). Czytniki czytaja najpierw nazwe z 2026-11-08
  (historie albo ostatnia wiadomosc, do konca), potem nowa - bez luki. Po kilku dobach HISTORY_FROM_OLD = False.
  Przejscie z tic.status.* (2026-11-08) jest juz zakonczone: wszystkie okna historii (<= 25 h) minely.
- Komunikaty dla operatora (2026-11-10, razem z overwatchami i oca_monitor): kazdy nadawca na swoim
  message.<realm>.<scope>.<element>.notice (TOI: message.toi.oca.self.notice, overwatche: message.overwatch.oca.self.notice),
  czytamy wszystkie przez MESSAGES_READ. Stary wspolny tic.status.ocm.messages nadawany rownolegle dla Haliny.
"""

import logging

from serverish.messenger import get_reader
from serverish.messenger.msg_publisher import get_publisher

logger = logging.getLogger(__name__)

NEW = {
    "log": "journal.toi.{tel}.self.log",                        # log operatora (~51% dawnego tic.status)
    "plan_log": "journal.toi.{tel}.self.plan_log",              # wykonane OB
    "ob": "status.toi.{tel}.self.ob",                           # biezacy OB (oca_monitor)
    "status": "status.toi.{tel}.self.switches",                 # wentylatory, lampy, swiatla (oca_monitor, Halina)
    "plan": "data.toi.{tel}.self.plan",                         # plan nocy z kursorem (oca_monitor)
    "flat": "data.toi.{tel}.camera.flat_log",                   # rekord kazdej ekspozycji flat
    "focus": "data.toi.{tel}.camera.focus_curve",               # wynik ostatniego autofocusa (krzywa V)
    "focus_record": "data.toi.{tel}.camera.focus_log",          # podsumowanie kazdego autofocusa (log focusa)
    "switch_synchro": "status.toi.{tel}.focuser.focus_adjust",  # focus auto-adjust wlaczony, {"focus_adjust": bool}
    "focus_reference": "status.toi.{tel}.focuser.focus_reference",   # punkt odniesienia focus adjust
    "observers": "status.toi.oca.self.observers",               # obserwatorzy nocy
    "checklist": "status.toi.oca.self.checklist",               # lista kontrolna dnia
    "messages": "message.toi.oca.self.notice",                  # komunikaty dla operatora (oca_monitor gra dzwieki)
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
    "messages": "tic.status.ocm.messages",
}

# nazwy z 2026-11-08 tematow przemianowanych 2026-11-10 - zrodlo historii dla history_reader
PREVIOUS = {
    "plan_log": "journal.toi.{tel}.self.plan",
    "flat": "data.toi.{tel}.camera.flat",
    "focus": "data.toi.{tel}.camera.focus_sample",
    "focus_record": "data.toi.{tel}.camera.focus_run",
    "switch_synchro": "status.toi.{tel}.self.switch_synchro",
}

# flat_overwatch: wewnetrzna nazwa itemu (TOI, flat_overwatch) -> item tematu data.overwatch.<tel>.camera.<item>
FLAT_OVERWATCH_ITEMS = {"flats_evening": "last_flat_evening", "flats_morning": "last_flat_morning",
                        "science": "last_science", "zeros": "last_zero", "darks": "last_dark"}

# czytane przez pms/Halina: nadawane tez pod stara nazwa (OLD). flat i focus_record od 2026-11-10 - konsument na starych
# nazwach (Halina last_flat, recent_focus_runs) nie dostawal nic od 2026-11-08. log celowo NIE (51% ruchu tic_status) -
# Halina musi przejsc na journal.toi.<tel>.self.log
DUAL = {"ob", "status", "plan", "messages", "flat", "focus_record"}
MESSAGES_READ = "message.*.*.*.notice"          # komunikaty dla operatora od wszystkich nadawcow (TOI, overwatche)
HISTORY_FROM_OLD = True             # przejscie bez luki w historii (PREVIOUS); wylaczyc po kilku dobach od 2026-11-10


def subject(name, tel=None):
    return NEW[name].format(tel=tel)


def old_subject(name, tel=None):
    return OLD[name].format(tel=tel)


def previous_subject(name, tel=None):
    return PREVIOUS[name].format(tel=tel)


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
    """(data, meta) tematu TOI: dla tematow z PREVIOUS najpierw poprzednia nazwa do konca (nowait), potem nowa - takze
    na biezaco. `start`: od tej chwili (deliver_policy='by_start_time'), None: ostatnia wiadomosc ('last') - stan, ktory
    po przejsciu jest jeszcze tylko pod poprzednia nazwa (focus_adjust)."""
    policy = {"deliver_policy": "last"} if start is None else {"deliver_policy": "by_start_time", "opt_start_time": start}
    if HISTORY_FROM_OLD and name in PREVIOUS:
        old = get_reader(previous_subject(name, tel), nowait=True, **policy)
        try:
            async for data, meta in old:
                yield data, meta
        except Exception as e:
            logger.warning(f'TOI: history of {previous_subject(name, tel)}: {e!r}')
        finally:
            try:
                await old.close()
            except Exception:
                pass
    async for data, meta in get_reader(subject(name, tel), **policy):
        yield data, meta
