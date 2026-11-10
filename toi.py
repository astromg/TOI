#!/usr/bin/env python3

# ----------------
# 1.08.2022
# Marek Gorski
# ----------------
import logging
import asyncio
import datetime
import functools
import os
import pwd
import signal
import socket
import sys
import uuid
import copy
import math
import time

import ephem
import numpy
import requests
import yaml
from pathlib import Path
from typing import Optional, Dict, Union, Any, Tuple
import qasync as qs
from ctc import CycleTimeCalc

from PyQtX import QtWidgets, QtGui


from obcom.comunication.base_client_api import BaseClientAPI
from ocaboxapi import Observatory, Telescope, AccessGrantor, Dome, Mount, CoverCalibrator, Focuser, Camera, \
    FilterWheel, Rotator, CCTV
from ocaboxapi.ephemeris import Ephemeris
from pyaraucaria.coordinates import *

from serverish.messenger import Messenger, get_reader, get_journalreader, request
from serverish.messenger.msg_publisher import get_publisher

from pyaraucaria.ob_validator import ObsValidator
from pyaraucaria.focus import Focus

from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from instrument_gui import InstrumentGui
from mnt_gui import MntGui
from sky_gui import SkyGui
from events_gui import AlertsWindow
from obs_gui import ObsGui, ObserversWindow, SoundTestWindow
from fits_gui import read_fits_image, fits_display_mode
from toi_subjects import subject, toi_publisher, history_reader, MESSAGES_READ, FLAT_OVERWATCH_ITEMS
from toi_theme import theme
from optics_model import OpticsModel
from plan_gui import PlanGui
from fits_gui import FitsWindow
from aux_gui import AuxWindow

from toi_lib import *


# level ustawic w settings
logging.basicConfig(level='INFO', format='%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)
logging.Formatter.converter = time.gmtime


class TOI(QtWidgets.QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, loop, observatory_model: Observatory, client_api: BaseClientAPI,local_cfg=None,  app=None):
        super().__init__(loop=loop, client_api=client_api)
        self.telescope: Optional[Telescope] = None
        self.user: Optional[AccessGrantor] = None
        self.dome: Optional[Dome] = None
        self.mount: Optional[Mount] = None
        self.cover: Optional[CoverCalibrator] = None
        self.focus: Optional[Focuser] = None
        self.ccd: Optional[Camera] = None
        self.guider: Optional[Camera] = None
        self.fw: Optional[FilterWheel] = None
        self.rotator: Optional[Rotator] = None
        self.cctv: Optional[CCTV] = None
        self.ephemeris: Optional[Ephemeris] = None
        self.app = app
        self.ctc_dat: Dict = {}
        self.active_tel: Optional[str] = None

        self.local_cfg = local_cfg

        self.setWindowTitle("Telescope Operator Interface")
        self.setLayout(QtWidgets.QVBoxLayout())

        host = socket.gethostname()
        user = pwd.getpwuid(os.getuid())[0]
        self.myself=f'{user}@{host}'
        self.observatory_model = observatory_model
        self.optics_model = OpticsModel()  # the active telescope's optical path: instrument panels, sky window

        self.variables_init()

        # window generation

        self.obsGui = ObsGui(self, loop=self.loop, client_api=self.client_api)
        self.mntGui = MntGui(self, loop=self.loop, client_api=self.client_api)

        self.skyGui = SkyGui(self)
        # przed instGui: zakladka instrumentu przelacza zakladke Calibration w aux
        self.auxGui = AuxWindow(self)
        self.focusGui = self.auxGui.focus
        self.flatGui = self.auxGui.calibration.camera
        self.guiderGui = self.auxGui.guider
        self.planrunnerGui = self.auxGui.planrunner
        self.conditionsGui = self.auxGui.conditions

        self.instGui = InstrumentGui(self, loop=self.loop, client_api=self.client_api)
        self.planGui = PlanGui(self, loop=self.loop, client_api=self.client_api)
        self.fitsGui = FitsWindow(self)
        self.observersGui = ObserversWindow(self)
        self.soundTestGui = SoundTestWindow(self)
        self.alertsGui = AlertsWindow(self)         # alerty conditions_overwatch do potwierdzenia (events_gui)
        self.events_admin = False       # okno obserwatorow, pole Admin: sekretne eventy w zakladce Events
        # wszystkie okna sa juz zbudowane - wchodza jako panele do okna obserwacji
        self.obsGui.dock_panels()

        self.add_background_task(self.lamps_loop())
        self.add_background_task(self.dome_follow_table_loop())
        self.add_background_task(self.nats_observers_reader())
        self.add_background_task(self.observers_check_loop())
        self.add_background_task(self.nats_checklist_reader())
        # alive RPC serwisow spoza ocabox-tcs (overwatche); subject pusty -> lampka szara
        self.alive_subjects = self.local_cfg["toi"].get("alive_subjects") or {}
        self.add_background_task(self.almanac_loop())
        self.add_background_task(self.alpaca_con_loop())
        self.add_background_task(self.tel_con_loop())
        self.add_background_task(self.tel_progress_loop())




        self.add_background_task(self.TOItimer())

        self.add_background_task(self.nats_weather_loop())
        self.add_background_task(self.conditions_plot_loop())
        for kind, subject in (self.local_cfg["toi"].get("conditions_subjects") or {}).items():
            if subject and (kind in self.CONDITION_FIELDS or kind == "weather_level"):
                self.add_background_task(self.nats_condition_reader(kind, subject))
        self.add_background_task(self.reader_ocm_messages())
        self.add_background_task(self.nats_events_reader())     # conditions_overwatch: eventy i alerty
        self.add_background_task(self.nats_alerts_reader())

        for t in self.oca_tel_state.keys():   # statusy wszystkich teleskopow

            self.add_background_task(self.nats_safety_reader(t))

            self.add_background_task(self.nats_ffs_reader(t))
            self.add_background_task(self.nats_mirror_fans_reader(t))
            self.add_background_task(self.nats_photo_zo_reader(t))

            self.add_background_task(self.nats_journal_planner_reader(t))
            self.add_background_task(self.nats_journal_ofp_reader(t))
            self.add_background_task(self.nats_journal_downloader_reader(t))
            self.add_background_task(self.nats_journal_guider_reader(t))
            self.add_background_task(self.nats_journal_optics_reader(t))

            self.add_background_task(self.oca_telemetry_conditions_reader(t))

            self.add_background_task(self.oca_telemetry_program_reader(t))
            self.add_background_task(self.nats_pub_toi_status_reader(t))
            self.add_background_task(self.nats_toi_focus_record_reader(t))
            self.add_background_task(self.nats_toi_focus_reference_reader(t))

            self.add_background_task(self.nats_toi_switch_synchro_reader(t))

            self.add_background_task(self.nats_plan_ofp_log_reader(t))


            for k in self.oca_tel_state[t].keys():
                self.add_background_task(self.oca_telemetry_reader(t,k))


        self.obsGui.main_form.update_table()
        # publishery natsow
        # NATS WRITER

        for k in self.local_cfg["toi"]["telescopes"]:
            self.nats_toi_plan_status[k] = toi_publisher("plan", k)
            self.nats_toi_ob_status[k] = toi_publisher("ob", k)

            self.nats_toi_switch_synchro[k] = toi_publisher("switch_synchro", k)

            self.nats_toi_flat_status[k] = toi_publisher("flat", k)
            self.nats_toi_focus_status[k] = toi_publisher("focus", k)
            self.nats_toi_focus_record[k] = toi_publisher("focus_record", k)
            self.nats_toi_focus_reference[k] = toi_publisher("focus_reference", k)

            self.nats_toi_plan_log[k] = toi_publisher("plan_log", k)
            self.nats_toi_log[k] = toi_publisher("log", k)
            self.nats_pub_toi_status[k] = toi_publisher("status", k)  # wentylatory, lampy, swiatla

    async def nats_safety_reader(self,tel):
        try:
            reader = get_reader(f'tic.status.{tel}.access_grantor.safety_cutoff_state', deliver_policy='last')
            async for data, meta in reader:
                try:
                    state = data["measurements"][f"{tel}.access_grantor.safety_cutoff_state"]
                    if isinstance(state, dict):
                        state = state.get("engaged")
                    self.safety_cutoff[tel] = None if state is None else bool(state)
                    self.obsGui.main_form.update_table()
                except Exception as e:
                    logger.exception(f'EXCEPTION 99c: bad safety cutoff message for {tel}: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 99a: {e}')

    async def nats_toi_switch_synchro_reader(self,tel):
        try:
            reader = history_reader("switch_synchro", tel)
            async for data, meta in reader:
                try:
                    self.toi_switch_status[tel] = data
                    self.focus_adjust_switch_update()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_switch_synchro_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 99b: {e}')

    async def oca_telemetry_conditions_reader(self,tel):
        try:
            r = get_reader(f'telemetry.conditions.{tel}-htsensor', deliver_policy='last')
            async for data, meta in r:
                try:
                    self.sensors[tel]["dome_conditions"] = data["measurements"]
                    self.update_dome_temp()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader oca_telemetry_conditions_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 100a: {e}')


    async def oca_telemetry_reader(self,tel,key):
        # dodac sprawdzanie czy na tych topikach nadaje
        try:
            r = get_reader(f'tic.status.{tel}{self.oca_tel_state[tel][key]["pms_topic"]}', deliver_policy='last')
            async for data, meta in r:
                try:
                    txt = data["measurements"][f"{tel}{self.oca_tel_state[tel][key]['pms_topic']}"]
                    self.oca_tel_state[tel][key]["val"] = txt
                    self.update_oca()
                    # tutaj jakas zmienna ktora nadaje jak nic nie idzie
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader oca_telemetry_reader({tel}, {key}): bad message skipped: {e!r}')

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 100: {e}')

    async def oca_telemetry_program_reader(self,tel):
        try:
            reader = history_reader("ob", tel)
            async for status, meta in reader:
                try:
                    self.ob_progress[tel] = status
                    self.update_oca()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader oca_telemetry_program_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 101: {e}')

    async def nats_pub_toi_status_reader(self,tel):
        try:
            reader = history_reader("status", tel)
            async for data, meta in reader:
                try:
                    self.nats_toi_op_status[tel] = data
                    self.obsGui.main_form.update_table()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_pub_toi_status_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 108: {e}')


    async def nats_toi_focus_record_reader(self,tel):           # to moze powinno sie raczej robic jako append
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)  # do konfiguracji
            reader = history_reader("focus_record", tel, time)     # najpierw historia starego tematu - bez luki
            async for data, meta in reader:
                try:
                    self.nats_focus_record[tel] = data
                    self.focusGui.add_record(tel, data)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_focus_record_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107: {e}')

    async def nats_toi_focus_reference_reader(self,tel):
        try:
            reader = history_reader("focus_reference", tel)
            async for data, meta in reader:
                try:
                    self.nats_focus_reference[tel] = data
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_focus_reference_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107b: {e}')

    async def nats_plan_ofp_log_reader(self,tel):
        try:
            r = get_reader(f'tic.status.{tel}.planner.command.log', deliver_policy='new')
            async for data, meta in r:
                try:
                    if self.tel_acces[tel]:
                        await self.plan_log_agregator(tel,data)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_plan_ofp_log_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 34f: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 34g: {e}')


    async def nats_journal_planner_reader(self,tel):
        try:
            r = get_journalreader(f'tic.journal.{tel}.planner', deliver_policy='new')
            async for data, meta in r:
                try:
                    if self.tel_acces[tel]:
                        await self.update_log(f'{data.message}', "PLANRUNNER", tel, level=data.level)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_journal_planner_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b1: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')

    async def nats_journal_ofp_reader(self,tel):
        try:
            r = get_journalreader(f'tic.journal.{tel}.pipeline', deliver_policy='new')
            async for data, meta in r:
                try:
                    if data.level > 10:
                        if self.tel_acces[tel]:
                            await self.update_log(f'{data.message}', "OFP", tel, level=data.level)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_journal_ofp_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b2: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')

    async def nats_journal_downloader_reader(self,tel):
        try:
            r = get_journalreader(f'tic.journal.{tel}.download', deliver_policy='new')
            async for data, meta in r:
                try:
                    if self.tel_acces[tel]:
                        await self.update_log(f'{data.message}', "DOWNLOADER", tel, level=data.level)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_journal_downloader_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b3: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')

    async def nats_journal_optics_reader(self, tel):
        """The optics service's journal: light-path changes that wait for a person, and their outcome."""
        try:
            r = get_journalreader(f'tic.journal.{tel}.optics', deliver_policy='new')
            async for data, meta in r:
                try:
                    if self.tel_acces[tel]:
                        await self.update_log(data.message, "OPTICS", tel, level=data.level)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_journal_optics_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: optics journal reader: {e}')

    async def nats_journal_guider_reader(self,tel):
        try:
            r = get_journalreader(f'tic.journal.{tel}.guider', deliver_policy='new')
            async for data, meta in r:
                try:
                    if self.tel_acces[tel]:
                        await self.update_log(data.message, "GUIDER", tel, level=data.level)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_journal_guider_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b4: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')


    # wentylatory lustra kazdego teleskopu wprost z TIC - tabela teleskopow w oknie obserwacji. toi.status (stan
    # zapisywany przez TOI) jest aktualny tylko, gdy jakies TOI ma ten teleskop aktywny z kontrola
    MIRROR_FANS_STALE = 15 * 60     # s - starsza wiadomosc TIC = nie wiemy

    async def nats_mirror_fans_reader(self, tel):
        try:
            r = get_reader(f'tic.status.{tel}.focuser.fansstatus', deliver_policy='last')
            async for data, meta in r:
                try:
                    values = list((data.get("measurements") or {}).values())
                    state = None if not values or values[0] is None else str(values[0]) == "True"
                    old = self.mirror_fans.get(tel, (None, 0))[0]
                    self.mirror_fans[tel] = (state, time.time())
                    if state != old:
                        self.obsGui.main_form.update_table()
                except Exception as e:
                    logger.warning(f'EXCEPTION 110f: bad mirror fans message: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 110g: {e}')

    def mirror_fans_on(self, tel):
        """Wentylatory lustra z TIC; None - brak swiezej wiadomosci"""
        state, t = self.mirror_fans.get(tel, (None, 0))
        return state if time.time() - t < self.MIRROR_FANS_STALE else None

    # NATS Conditions reader
    async def nats_ffs_reader(self,tel):
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
            r = get_reader(f'tic.status.{tel}.fits.pipeline.faststat',  deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in r:
                try:
                    self.fits_ffs_data[tel].append(data)
                    try:        # tryb odczytu kazdego teleskopu, nie tylko aktywnego - do czasow planu (CTC)
                        rm = data["raw"]["header"].get("READ-MOD")
                        if rm is not None:
                            self.readoutmode_tel[tel] = int(rm)
                    except (KeyError, TypeError, ValueError):
                        pass
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_ffs_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 778: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 778b: {e}')

    @staticmethod
    def time_ranges(break_hour_utc: int = 17) -> Dict[str, datetime.datetime]:
        time_now = datetime.datetime.now(datetime.timezone.utc)
        if time_now.hour >= break_hour_utc:
            today_range = time_now.replace(hour=break_hour_utc)
        else:
            day_back = time_now - datetime.timedelta(days=1)
            today_range = day_back.replace(hour=break_hour_utc)
        return {
            'today': today_range,
            'yesterday': today_range - datetime.timedelta(days=1)
        }

    async def nats_photo_zo_reader(self,tel):
        tim_range_max = self.time_ranges()
        try:
            r = get_reader(
                f'tic.status.{tel}.zero_monitor.lc',
                deliver_policy='by_start_time',
                opt_start_time=tim_range_max['yesterday']
            )
            async for data, meta in r:
                try:
                    self.fits_photo_z0_data[tel].append(data)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_photo_zo_reader({tel}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 778: {e}')


    async def reader_ocm_messages(self):
        try:
            r = get_reader(MESSAGES_READ, deliver_policy='new')     # wszyscy nadawcy, toi_subjects
            async for data, meta in r:
                try:
                    label = data["label"]
                    # kolory wg znaczenia (toi_theme): zielony OK, zolty uwaga, pomaranczowy gorzej, czerwony zle
                    c = "field_fg"
                    if label in ("PING", "WEATHER WARNING", "CLOUDS INFO", "FWHM WARNING", "ZERO POINT WARNING"):
                        c = "warn_fg"
                    if label in ("WEATHER ALERT", "SYSTEM ALERT", "CLOUDS ALERT"):     # SYSTEM ALERT: bateria, serwerownia
                        c = "bad_fg"
                    if label == "WEATHER LEVEL DOWN":      # conditions_overwatch: ograniczenia pogodowe spadaja
                        c = "ok_fg"
                    if label == "CLOUDS WARNING":          # allsky_overwatch, kolory jak pole Clouds
                        c = "warn2_fg"
                    if label == "EVENT":        # conditions_overwatch: Slonce +5 / -18, ut, ... (events_gui)
                        c = "change_fg"
                        if data.get("picture") and not data.get("test"):
                            self.show_event_picture(data["picture"], data.get("info", ""))
                    if label == "SYSTEM ALERT" and str(data.get("info", "")).startswith("REMINDER") \
                            and not data.get("test"):
                        self.alertsGui.update_alerts(self.alertsGui.alerts, pop=True)     # przy zapisie obserwatorow
                    if label in ("FWHM WARNING", "ZERO POINT WARNING"):
                        try:        # alarm seeingu / zero pointu - zakladka Conditions z tym wykresem na wierzch
                            if not data.get("test"):        # test dzwieku z okna PING - bez przelaczania zakladki
                                self.auxGui.alert_received(label)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION alert tab: {e}')

                    if data.get("test"):        # test dzwieku z okna PING - szary, nie kolor prawdziwego alarmu
                        c = "muted_fg"
                    c = theme.qcolor(c)
                    txt = f'{data["ut"]} [{data["user"]}] {data["info"]}'
                    self.obsGui.main_form.msg_e.setTextColor(c)
                    self.obsGui.main_form.msg_e.append(txt)
                    self.obsGui.main_form.msg_e.repaint()

                    if label == "PING":
                        info = f"TOI reporting in"
                        label = "INFO"
                        await self.send_ocm_message(info, label=label)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader reader_ocm_messages: bad message skipped: {e!r}')

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION: {e}')

    # ---- conditions_overwatch: eventy (zakladka Events) i alerty z potwierdzaniem (okno), events_gui.py
    def events_cfg(self):
        return self.local_cfg["toi"].get("events") or {}

    async def events_rpc(self, data):
        """RPC do conditions_overwatch (add / remove / ack / list) -> odpowiedz (dict); wyjatek przy timeoucie"""
        subject = self.events_cfg().get("rpc", "rpc.overwatch.oca.conditions_overwatch.events")
        resp, meta = await request(subject, data=data, timeout=5)
        return resp or {}

    async def nats_events_reader(self):
        try:
            r = get_reader(self.events_cfg().get("list", "status.overwatch.oca.self.events"), deliver_policy='last')
            async for data, meta in r:
                try:
                    self.auxGui.events.update_list(data.get("events"))
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_events_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION nats_events_reader: {e}')

    async def nats_alerts_reader(self):
        seen = None         # id alertow juz pokazanych; pierwszy odczyt po starcie TOI tez wyskakuje
        try:
            r = get_reader(self.events_cfg().get("alerts", "status.overwatch.oca.self.alerts"), deliver_policy='last')
            async for data, meta in r:
                try:
                    alerts = data.get("alerts") or []
                    ids = {a.get("id") for a in alerts}
                    self.alertsGui.update_alerts(alerts, pop=bool(ids - (seen or set())))
                    seen = ids
                except Exception as e:
                    logger.warning(f'TOI reader nats_alerts_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION nats_alerts_reader: {e}')

    def set_events_admin(self, on):
        """Okno obserwatorow, pole Admin: zakladka Events pokazuje sekretne eventy (tylko to stanowisko i sesja)"""
        self.events_admin = bool(on)
        self.auxGui.events.set_admin(self.events_admin)

    def show_event_picture(self, name, info):
        """Obrazek eventu w zakladce Pictures (sama nazwa pliku z toi.events.pictures_dir)"""
        name = os.path.basename(str(name))
        path = os.path.join(self.events_cfg().get("pictures_dir", "/data/misc/oca_overwatch/pictures"), name)
        asyncio.ensure_future(self.auxGui.pictures.show_file(path, info, f"No picture {name}"))
        self.auxGui.show_tab(self.auxGui.pictures)

    # NATS weather
    async def nats_weather_loop(self):
        try:
            reader = get_reader('telemetry.weather.davis', deliver_policy='last')
            async for data, meta in reader:
                try:
                    weather = data['measurements']
                    self.telemetry_temp = weather["temperature_C"]
                    self.telemetry_wind = weather["wind_10min_ms"]
                    self.telemetry_wind_direction = weather["wind_dir_deg"]
                    self.telemetry_humidity = weather["humidity"]
                    self.telemetry_pressure = weather["pressure_Pa"]
                    self.telemetry_rain = weather.get("rain_mm")   # biezacy opad z deszczomierza Davisa
                    self.updateWeather()
                except Exception as e:
                    logger.exception(f'EXCEPTION 102a: bad weather message: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 102: {e}')

    # seeing i zero point obserwatorium z conditions_overwatch (toi.conditions_subjects): mediana punktow wszystkich
    # teleskopow z ostatnich window_min minut, z progami per teleskop. Pole w oknie obserwacji, format, kierunek
    # (+1 gorzej, gdy rosnie; -1 gdy maleje) i opis
    CONDITION_FIELDS = {
        "seeing": ("fwhm_e", '{:.1f} ["]', +1, "frames",
                   "Seeing at zenith, conditions_overwatch: median of science frames of all telescopes"),
        "zero_point": ("zeropoint_e", "{:+.2f} [mag]", -1, "points",
                       "Photometric zero point, conditions_overwatch: median of zero_monitor of all telescopes"),
        "clouds": ("clouds_e", None, 0, "frames", "Clouds from the allsky camera, allsky_overwatch"),   # update_clouds_field
    }

    # stan nieba z allsky_overwatch (toi.conditions_subjects.clouds), jedna klatka co ~2.4 min w nocy: samo slowo, bez
    # liczb; kolor jak Wind / Direction - thin i veil zolty, cloudy pomaranczowy, overcast czerwony. Zmierzch (Slonce
    # powyzej -18, chmur nie mierzymy) jak dzien: "--" na szaro (Marek 2026-11-02, wczesniej "twilight" na niebiesko)
    CLOUD_COLORS = {"clear": "field_bg", "veil": "warn_bg", "thin": "warn_bg",       # klucze toi_theme
                    "cloudy": "warn2_bg", "overcast": "bad_bg"}
    CLOUDS_MAX_AGE = 600        # s; starsza wiadomosc (dzien, serwis stoi) - pole "--"
    CLOUDS_HINT = ("Clouds from the allsky camera (allsky_overwatch), every ~2.4 min at night:\n"
                   "clear - clear sky\n"
                   "veil - the whole sky dimmed evenly, the stars still seen everywhere\n"
                   "thin - thin or partial cloud, or cloud moving across the sky\n"
                   "cloudy - about half of the starlight lost, or strong changes between frames\n"
                   "overcast - most of the light lost, or too few stars to measure\n"
                   "-- - day or twilight (Sun above -18 deg, clouds not measured), or no frame for 10 min")

    async def conditions_plot_loop(self):
        # wykresy w zakladce Conditions (Aux): co 30 s, tylko gdy widoczne i przyszly nowe punkty (~40 ms)
        while True:
            try:
                self.conditionsGui.refresh_if_new()
            except Exception as e:
                logger.warning(f'EXCEPTION 102d: {e}')
            await asyncio.sleep(30)

    async def nats_condition_reader(self, kind, subject):
        try:
            reader = get_reader(subject, deliver_policy='last')
            async for data, meta in reader:
                try:
                    self.conditions[kind] = data
                    self.update_condition_field(kind)
                except Exception as e:
                    logger.warning(f'EXCEPTION 102c: bad {kind} message: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 102b ({kind}): {e}')

    def update_condition_field(self, kind):
        # wolane tez z updateWeather - wartosc sie starzeje, gdy nikt nie obserwuje (overwatch publikuje przy punkcie)
        if kind == "clouds":
            return self.update_clouds_field()
        if kind == "weather_level":
            return self.update_hold_markers()
        name, fmt, worse, unit, hint = self.CONDITION_FIELDS[kind]
        field = getattr(self.obsGui.main_form, name)
        d = self.conditions.get(kind)
        value, age, clouds = None, None, False
        if d and d.get("time"):
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(d["time"])).total_seconds()
            if age <= 60 * float(d.get("window_min", 30)):
                value = float(d[kind]) if d.get(kind) is not None else None
                clouds = bool(d.get("clouds"))      # zero point: zle punkty / nieudane pomiary - chmury
        # kolor nie zalezy od aktywnego teleskopu: progi wszystkich teleskopow (ostrzezenia i alarmy) rosnaco wg
        # pogorszenia; pierwszy przekroczony - zolty, ostatni - czerwony, posrednie - pomaranczowy
        limits = (d or {}).get("limits", {})
        steps = sorted({float(x[k]) for x in limits.values() for k in ("warning", "alert") if k in x},
                       key=lambda x: worse * x)
        passed = [x for x in steps if value is not None and worse * value >= worse * x]
        color = "field_bg"
        if clouds:      # alarm z chmur, nawet gdy mediana jest dobra (chmury daja malo punktow, mediana je odrzuca)
            field.setText((fmt.format(value) + " " if value is not None else "") + "\u2601")
            color = "bad_bg"
        elif value is None:
            field.setText("--")
        else:
            field.setText(fmt.format(value))
            if passed and len(passed) == len(steps) and len(steps) > 1:
                color = "bad_bg"
            elif len(passed) == 1:
                color = "warn_bg"
            elif passed:
                color = "warn2_bg"
        field.setStyleSheet(theme.field_style(color))
        tip = hint
        if d:
            tip += f" from the last {d.get('window_min')} min, {d.get('n')} {unit}."
            if age is not None:
                tip += f"\nLast {unit[:-1]} {age / 60:.0f} min ago."
            if limits:
                tip += "\nLimits (warning / alert): " + ", ".join(
                    f"{t} {x.get('warning')} / {x.get('alert')}" for t, x in limits.items())
            if passed:
                over = [t for t, x in limits.items() if worse * value >= worse * float(x.get("warning", x.get("alert")))]
                tip += f"\nExceeded: {', '.join(over)}"
            if "bad" in d:
                tip += f"\nBad points (below the alert limit or failed) in the last minutes: {d['bad']}" + \
                       (" - CLOUDS" if clouds else "")
        else:
            tip += ". No data yet."
        field.setToolTip(tip)


    # karencja ograniczen pogodowych (conditions_overwatch, toi.conditions_subjects.weather_level; stan publikowany przy
    # zmianie): poziom oficjalny spada dopiero po weather_hold minutach lepszych warunkow. Tlo pol zostaje wg biezacych
    # wartosci, a kropka przy polu ma kolor poziomu oficjalnego i minuty do najblizszego spadku - tylko gdy oficjalny
    # jest wyzszy niz biezacy. Wind: teleskopy zamkniete (2), Direction: z zakazem celowania (>= 1), skala kolorow
    # jak tlo (jeden zolty, kilka pomaranczowy, wszystkie czerwony); Humidity (z deszczem), Temp, Clouds jak ich tlo
    HOLD_TEXT = {("wind", 2): "closed", ("wind", 1): "pointing restricted", "humidity": "humidity", "rain": "rain",
                 "temperature": "temperature", ("clouds", 1): "cloudy", ("clouds", 2): "overcast"}

    def update_hold_markers(self):
        markers = self.obsGui.main_form.hold_markers
        d = self.conditions.get("weather_level") or {}
        levels, raw = d.get("levels") or {}, d.get("raw") or {}
        now = datetime.datetime.now(datetime.timezone.utc)
        until = {}
        for k, v in (d.get("hold_until") or {}).items():
            try:
                t = datetime.datetime.fromisoformat(v)
            except (TypeError, ValueError):
                continue
            if t > now:         # minela - stan nieaktualny (overwatch stoi), kropki nie ma
                until[k] = t
        tels = [k for k in levels if k.startswith("wind:")]

        def scale(n, total):
            return theme.c("bad_bg" if n == total else "warn_bg" if n == 1 else "warn2_bg")

        def held(keys, level):
            """klucze, ktore oficjalnie sa >= level, a biezaco nizej (w karencji)"""
            return [k for k in keys if levels.get(k, 0) >= level and raw.get(k, 0) < level and k in until]

        def show(name, keys, color, describe):
            first = min(until[k] for k in keys)
            tip = "Weather restriction still in force (conditions_overwatch hold time):\n" + "\n".join(
                f"{describe(k)} until {until[k]:%H:%M} UT" for k in sorted(keys, key=lambda k: until[k]))
            markers[name].show_hold(color, max(1, math.ceil((first - now).total_seconds() / 60)), tip)

        for name, level in (("wind_e", 2), ("windDir_e", 1)):
            keys = held(tels, level)
            if keys:
                n = len([k for k in tels if levels.get(k, 0) >= level])
                show(name, keys, scale(n, len(tels)),
                     lambda k: f"{k[5:]} {self.HOLD_TEXT[('wind', min(levels[k], 2))]}")
            else:
                markers[name].clear()
        for name, kinds in (("hummidity_e", ("humidity", "rain")), ("temp_e", ("temperature",))):
            keys = held(kinds, 2)
            if keys and not any(raw.get(k, 0) >= 2 for k in kinds):
                show(name, keys, theme.c("bad_bg"), lambda k: self.HOLD_TEXT[k])
            else:
                markers[name].clear()
        keys = [k for k in ("clouds",) if raw.get(k, 0) < levels.get(k, 0) and k in until]     # tez overcast -> cloudy
        if keys:
            c = levels["clouds"]
            show("clouds_e", keys, theme.c("bad_bg" if c >= 2 else "warn2_bg"), lambda k: self.HOLD_TEXT[("clouds", min(c, 2))])
        else:
            markers["clouds_e"].clear()

    def clouds_at(self, tel):
        """"red" / "yellow", gdy teleskop obserwuje w polu tak zaznaczonym przez allsky_overwatch na ostatniej klatce
        (wiadomosc nie starsza niz CLOUDS_MAX_AGE), inaczej None - ikonka chmury w tabeli teleskopow"""
        d = self.conditions.get("clouds")
        if not d or not d.get("time"):
            return None
        age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(d["time"])).total_seconds()
        return (d.get("telescopes") or {}).get(tel) if age <= self.CLOUDS_MAX_AGE else None

    def update_clouds_field(self):
        field = self.obsGui.main_form.clouds_e
        d = self.conditions.get("clouds")
        state, age = None, None
        if d and d.get("time"):
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(d["time"])).total_seconds()
            if age <= self.CLOUDS_MAX_AGE:
                state = "veil" if d.get("veil") and d.get("state") == "thin" else d.get("state")
                if d.get("twilight"):       # o zmierzchu chmur nie mierzymy - jak w dzien
                    state = None
        field.setText("--" if state is None else state)
        field.setStyleSheet(theme.field_style(self.CLOUD_COLORS.get(state, "field_bg")))
        if d and d.get("telescopes") != self.clouds_telescopes:     # ikonki chmur w tabeli teleskopow
            self.clouds_telescopes = d.get("telescopes")
            self.obsGui.main_form.update_table()
        tip = self.CLOUDS_HINT
        if age is not None:
            tip += f"\nLast frame {d.get('frame')}, {age / 60:.0f} min ago."
        field.setToolTip(tip)


    # ---- lampki serwisow aktywnego teleskopu: dome follower (heartbeat ocabox-tcs co 10 s),
    # downloader i pipeline ofp (RPC tic.rpc.<tel>.<serwis>.alive -> {"status": "ok"}), tak samo jak GUI TEXT;
    # overwatche tak samo jak ofp (toi.alive_subjects), nie zaleza od teleskopu
    SERVICE_STALE = 30      # s bez heartbeatu = dome follower nie dziala

    async def dome_follower_heartbeat_reader(self):
        try:
            r = get_reader(f'svc.heartbeat.dome_follower_svc.dome_follower.{self.active_tel}-dome_follower',
                           deliver_policy='new')
            async for data, meta in r:
                try:
                    self.dome_follower_seen = time.time()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader dome_follower_heartbeat_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 110c: {e}')

    async def ofp_alive(self, tel, service):
        # subject jak w GUI TEXT (ocabox-cli): site.global.nats.subjects.rpc.<serwis>_alive z configu TIC
        try:
            subject = self.client_cfg["site"]["global"]["nats"]["subjects"]["rpc"][f"{service}_alive"]
        except (KeyError, TypeError):
            subject = "tic.rpc.{telescope}." + service + ".alive"
        return await self.rpc_alive(subject.format(telescope=tel))

    async def rpc_alive(self, subject):
        try:
            data, meta = await request(subject, timeout=3)
            return data.get("status") == "ok"
        except Exception:       # brak odpowiedzi, timeout, brak responderow
            return False

    # FOLLOW w kolumnie Dome tabeli teleskopow: stan dome followera jest tylko w RPC (tic.rpc.<tel>.dome.follower.state,
    # serwis trzyma go w pamieci) - pytamy o wszystkie teleskopy; aktywny odswieza tez dome_follower_status_update
    async def dome_follow_table_loop(self):
        while True:
            try:
                tels = list(self.local_cfg["toi"]["telescopes"])
                answers = await asyncio.gather(*(self.dome_follow_state(t) for t in tels))
                self.set_dome_follow_table(dict(zip(tels, answers)))
            except (asyncio.CancelledError, asyncio.TimeoutError):
                raise
            except Exception as e:
                logger.warning(f'EXCEPTION 103d: {e}')
            await asyncio.sleep(5)

    async def dome_follow_state(self, tel):
        """True / False wg dome followera, None - brak odpowiedzi"""
        try:
            data, meta = await request(f'tic.rpc.{tel}.dome.follower.state', timeout=3)
            return bool(data["follow_on"]) if data.get("status") == "ok" else None
        except Exception:
            return None

    def set_dome_follow_table(self, states):
        changed = {t: v for t, v in states.items() if self.dome_follow_all.get(t) != v}
        if changed:
            self.dome_follow_all.update(changed)
            self.obsGui.main_form.update_table()

    # lampki na gorze okna obserwacji odpytywane po kolei, od lewej, co pol sekundy: TIC, NATS, DOME FLW, FITS DWL,
    # OFP, FLAT OW, WEATHER OW, ALLSKY OW - kazdy serwis co 4 s, mrugniecie (MainForm.beat) przesuwa sie fala.
    # Pytanie idzie jako osobne zadanie, wiec serwis, ktory nie odpowiada (timeout 3 s), nie zatrzymuje fali
    LAMP_STEP = 0.5     # s miedzy kolejnymi lampkami (8 lampek - kazda co 4 s)

    async def lamps_loop(self):
        f = self.obsGui.main_form
        slots = [(f.ticStatus2_l, self.lamp_tic), (f.natsStatus_l, self.lamp_nats),
                 (f.followerStatus_l, self.lamp_follower),
                 (f.downloaderStatus_l, lambda: self.lamp_ofp("download")),
                 (f.ofpStatus_l, lambda: self.lamp_ofp("pipeline")),
                 (f.flatOwStatus_l, lambda: self.lamp_alive("flat_overwatch")),
                 (f.conditionsOwStatus_l, lambda: self.lamp_alive("conditions_overwatch")),
                 (f.allskyOwStatus_l, lambda: self.lamp_alive("allsky_overwatch"))]
        pending = {}
        i = 0
        while True:
            lamp, check = slots[i]
            if lamp not in pending or pending[lamp].done():      # poprzednie pytanie tej lampki jeszcze trwa - pomijamy
                pending[lamp] = asyncio.ensure_future(self.lamp_update(lamp, check))
            i = (i + 1) % len(slots)
            await asyncio.sleep(self.LAMP_STEP)

    async def lamp_update(self, lamp, check):
        """check() -> True (dziala: zielona i mrugniecie), False (czerwona), "wait" (szara), "reconnect" (pomaranczowa)"""
        try:
            tel = self.active_tel
            ok = await check()
            if tel != self.active_tel and lamp in (self.obsGui.main_form.downloaderStatus_l,
                                                    self.obsGui.main_form.ofpStatus_l):
                return      # w trakcie pytania zmienil sie teleskop - odpowiedz dotyczy poprzedniego
            color = {True: "ok_fg", False: "bad_fg", "wait": "muted_fg", "reconnect": "warn2_fg"}[ok]
            self.obsGui.main_form.set_lamp(lamp, color)
            if ok is True:
                self.obsGui.main_form.beat(lamp)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 103c: lamp {lamp.text()}: {e}')

    async def lamp_tic(self):
        self.tic_con = await self.observatory_model.is_tic_server_available()
        return bool(self.tic_con)

    async def lamp_nats(self):
        # polaczenie TOI z NATS (nats-py pod serverish); w trakcie ponownego laczenia - pomaranczowy
        nc = Messenger().connection.nc
        if nc is not None and nc.is_connected:
            return True
        if nc is not None and nc.is_reconnecting:
            return "reconnect"
        return False

    async def lamp_follower(self):
        # heartbeat dome followera aktywnego teleskopu (co 10 s), zbierany przez dome_follower_heartbeat_reader
        now = time.time()
        if self.dome_follower_seen is not None and now - self.dome_follower_seen < self.SERVICE_STALE:
            return True
        if now - self.services_since < self.SERVICE_STALE:
            return "wait"       # jeszcze czekamy na pierwszy heartbeat
        return False

    async def lamp_ofp(self, service):
        if self.active_tel is None:
            return "wait"
        return await self.ofp_alive(self.active_tel, service)

    async def lamp_alive(self, name):
        if not self.alive_subjects.get(name):
            return "wait"       # brak subjectu w toi_config.yaml
        return await self.rpc_alive(self.alive_subjects[name])

    # ---- obserwatorzy nocy, wspolni dla obserwatorium: lista w observers.yaml, wybor publikowany na
    # tic.status.ocm.observers (strumien tic_status trzyma ostatni wpis). Wpis wazny do kolejnego resetu - codziennie
    # o toi.observers_reset_ut (godzina UT, okolo poludnia lokalnie); starszy - okno samo wyskakuje
    OBSERVERS_SUBJECT = subject("observers")
    OBSERVERS_LATER = 30 * 60           # s, "Later" odklada pytanie

    async def nats_observers_reader(self):
        try:
            r = history_reader("observers", None)
            async for data, meta in r:
                try:
                    self.night_observers = data
                    if self.observers_local is None:        # lokalny wybor tej sesji ma pierwszenstwo
                        self.show_observers()
                        if self.observers_valid():
                            self.observersGui.hide()    # ktos juz wpisal - okno znika na wszystkich stanowiskach
                except Exception as e:
                    logger.warning(f'EXCEPTION 110e: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 110f: {e}')

    def current_observers(self):
        # lokalny wybor tej sesji ("Only this TOI") albo wspolny wpis z NATS
        return self.observers_local or self.night_observers

    def show_observers(self):
        data = self.current_observers() or {}
        names = ", ".join(data.get("observers") or []) or "--"
        f = self.obsGui.main_form
        if self.observers_local is not None:
            f.observers_p.setText(f"Observers (this TOI only): {names}")
            f.observers_p.setToolTip("Set for this session only, not shared with other stations. Click to change.")
        else:
            f.observers_p.setText(f"Observers: {names}")
            f.observers_p.setToolTip(f'Observers tonight, set {data.get("time", "?")} UT by {data.get("by", "?")}. '
                                     f'Click to change.')

    def observers_reset_time(self):
        # ostatni reset listy obserwatorow: dzis o toi.observers_reset_ut UT, a przed ta godzina - wczoraj
        hour = float(self.local_cfg["toi"].get("observers_reset_ut", 15))
        now = datetime.datetime.now(datetime.timezone.utc)
        reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=hour)
        return reset if reset <= now else reset - datetime.timedelta(days=1)

    def observers_valid(self):
        try:
            t = datetime.datetime.fromisoformat(self.current_observers()["time"])
            return t >= self.observers_reset_time()
        except (TypeError, KeyError, ValueError):
            return False

    async def observers_check_loop(self):
        await asyncio.sleep(15)     # najpierw ostatni wpis z NATS
        while True:
            try:
                self.show_checklist()       # o resecie dnia odhaczenia znikaja
                if (not self.observers_valid() and time.time() > self.observers_later_until
                        and not self.observersGui.isVisible()):
                    self.open_observers_window()
            except Exception as e:
                logger.warning(f'EXCEPTION 103d: {e}')
            await asyncio.sleep(60)

    def open_observers_window(self):
        current = (self.current_observers() or {}).get("observers") or []
        self.observersGui.open_for(current, local=self.observers_local is not None)

    def observers_later(self):
        self.observers_later_until = time.time() + self.OBSERVERS_LATER
        self.observersGui.hide()

    def set_observers(self, names, local=False):
        if local:
            self.observers_local = {"observers": names, "by": self.myself,
                                    "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            self.show_observers()
        else:
            self.observers_local = None
            asyncio.ensure_future(self._publish_observers(names))

    async def _publish_observers(self, names):
        try:
            data = {"observers": names, "by": self.myself,
                    "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            await get_publisher(self.OBSERVERS_SUBJECT).publish(data=data, timeout=10)
            await self.send_ocm_message(f'observers tonight: {", ".join(names)}')
        except Exception as e:
            logger.warning(f'EXCEPTION publish_observers: {e}')
            self.WarningWindow(f"Observers not saved: {e}")

    # ---- codzienna checklista obserwatorow (checklist.yaml), wspolna dla obserwatorium jak obserwatorzy: caly stan
    # na tic.status.ocm.checklist {"done": {id: {"time", "by"}}, "time", "by"}; odhaczenie wazne do resetu dnia
    CHECKLIST_SUBJECT = subject("checklist")

    async def nats_checklist_reader(self):
        try:
            r = history_reader("checklist", None)
            async for data, meta in r:
                try:
                    self.checklist_state = data
                    self.show_checklist()
                except Exception as e:
                    logger.warning(f'EXCEPTION 110g: {e}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 110h: {e}')

    def checklist_done(self):
        # odhaczenia z dzisiaj (po ostatnim resecie), {id: {"time", "by"}}
        reset = self.observers_reset_time()
        done = {}
        for item_id, entry in ((self.checklist_state or {}).get("done") or {}).items():
            try:
                if datetime.datetime.fromisoformat(entry["time"]) >= reset:
                    done[item_id] = entry
            except (TypeError, KeyError, ValueError):
                pass
        return done

    def show_checklist(self):
        self.auxGui.tasks.show_checklist(self.checklist, self.checklist_done())

    def checklist_allowed(self, per_tel):
        # odhacza ten, kto ma kontrole: punkt teleskopowy - nad aktywnym teleskopem, wspolny - nad ktorymkolwiek
        if per_tel:
            return bool(self.active_tel and self.tel_acces.get(self.active_tel))
        return any(self.tel_acces.values())

    def set_checklist_item(self, item_id, checked):
        if not self.checklist_allowed("@" in item_id):
            self.show_checklist()       # odhaczenie wraca do stanu z NATS
            txt = "WARNING: U don't have control"
            self.WarningWindow(txt)
            return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        done = self.checklist_done()
        if checked:
            done[item_id] = {"time": now, "by": self.myself}
        else:
            done.pop(item_id, None)
        # od razu u siebie, potem dla wszystkich (wpis z NATS wroci tym samym stanem)
        self.checklist_state = {"done": done, "time": now, "by": self.myself}
        self.show_checklist()
        asyncio.ensure_future(self._publish_checklist(self.checklist_state))

    async def _publish_checklist(self, data):
        try:
            await get_publisher(self.CHECKLIST_SUBJECT).publish(data=data, timeout=10)
        except Exception as e:
            logger.warning(f'EXCEPTION publish_checklist: {e}')
            self.WarningWindow(f"Checklist not saved: {e}")

    #  ############# ZMIANA TELESKOPU ### TELESCOPE SELECT #################
    async def telescope_switched(self):

        self.inst_tab_switch = True
        self.m3_port = None
        self.dome_follower_seen = None          # heartbeat dome followera nowego teleskopu
        self.services_since = time.time()
        # DUPA

        self.telescope_switch_status["plan"] = False
        # plan opublikowany w NATS i zaznaczenie w tabeli naleza do poprzedniego teleskopu: bez zerowania tabela
        # pokazywala jego plan (na stale, gdy nowy teleskop nie ma opublikowanego), a Del/Up/Skip dzialaly na wierszu,
        # ktorego nikt w nowym planie nie wybral
        self.nats_plan_status = {"current_i": -1, "next_i": -1, "plan": []}
        self.planGui.i = 0
        self.planGui.prev_i = -1
        self.telescope_switch_status["mntGui"] = False
        self.telescope_switch_status["instGui"] = False
        self.telescope_switch_status["filters"] = False
        self.telescope_switch_status["rm"] = False
        self.telescope_switch_status["gain"] = False


        # FFS obrazu poprzedniego teleskopu: bez czekania (wait() stawial GUI do konca liczenia), wynik do kosza
        self.fitsGui.cancel_ffs()


        # to sa zmienne dla guidera
        self.pulseRa = 0
        self.pulseDec = 0
        self.guider_passive_dx = []
        self.guider_passive_dy = []
        self.guider_failed = 1

        self.flat_record={}
        self.flat_record["go"] = False

        # tez trzeba resetowac, bo jest tylko wyslwietlany
        self.ob_log = []
        self.done_uobi = []   # uobi z plan_log nowego teleskopu
        self.flat_log = []
        # wynik focusa poprzedniego teleskopu nie moze zostac na wykresie
        self.nats_focus_status = {}
        self.focusGui.show_status({})

        # TELESCOPE CONFIGURATION HARDCODED

        self.active_tel = self.local_cfg["toi"]["telescopes"][self.active_tel_i]
        self.obsGui.set_panel_telescope(self.active_tel)

        self.filter_list = self.nats_cfg[self.active_tel]["filter_list_names"]  # tu sa nazwy
        # ustawienia kamery (gain, read mode, temperatura, binning) ma zakladka instrumentu: instGui.ccd_tab

        self.cfg_tel_directory = self.local_cfg[self.active_tel]["tel_directory"]
        self.cfg_tel_ob_list = self.local_cfg[self.active_tel]["tel_ob_list"]
        # rotator: wg komponentu "derotator" w konfiguracji TIC; bez listy komponentow - dawne showRotator z toi_config
        components = self.nats_cfg[self.active_tel].get("components")
        if components is not None:
            self.cfg_showRotator = "derotator" in components
        else:
            self.cfg_showRotator = self.local_cfg[self.active_tel].get("showRotator", False)
        # M3: wg komponentu "tertiary" (jego pozycje to porty); bez niego wiersz M3 wyszarzony, bez subskrypcji
        self.has_m3 = self.nats_cfg[self.active_tel]["tertiary_port_list"] is not None

        self.overhed = self.local_cfg[self.active_tel]["overhead"]

        self.cfg_alt_limits = {}
        for key, cfg_key, default in (("min", "min_alt", 0.0), ("max", "max_alt", 90.0), ("low", "low_alt", 0.0)):
            val = self.nats_cfg[self.active_tel][cfg_key]
            if val is None:
                logger.warning(f'TOI: no {cfg_key} for {self.active_tel} in TIC config, using {default}')
                val = default
            self.cfg_alt_limits[key] = float(val)

        self.catalog_file = self.local_cfg[self.active_tel]["object_catalog"]

        # obsluga subskrypcji

        if self.telescope is not None:
            await self.stop_background_methods(group="subscribe")
            self.telescope.unsubscribe_all_component()
            self.telescope.unwatch_all_component()
            await self.stop_background_tasks(group="telescope_task")
            # remove this telecpe object from observatory, let have fresh one next time
            # this should fix non-calling callbacks after switching telescope few times
            # for unchanged vlues
            try:
                self.observatory_model.dischard_cached_telescope(self.telescope)
            except AttributeError:
                logger.error('ocaboc version >= 2.3.3 needed')

        self.telescope = self.observatory_model.get_telescope(self.active_tel)
        self.user = self.telescope.get_access_grantor()
        self.dome = self.telescope.get_dome()
        self.mount = self.telescope.get_mount()
        self.cover = self.telescope.get_covercalibrator()
        self.focus = self.telescope.get_focuser()
        self.m3 = self.telescope.get_tertiary()
        self.ccd = self.telescope.get_camera()
        # do ktorego teleskopu naleza self.ccd, self.dome, self.focus... - zdarzenia ich subskrypcji zapisujemy pod nim,
        # nie pod active_tel (przy przelaczaniu active_tel zmienia sie, zanim subskrypcje starego teleskopu stana)
        self.component_tel = self.active_tel
        self.guider = self.telescope.get_camera(id='guider')
        self.fw = self.telescope.get_filterwheel()
        if bool(self.cfg_showRotator):
            self.rotator = self.telescope.get_rotator()
        self.cctv = self.telescope.get_cctv()
        self.ephemeris = self.observatory_model.get_ephemeris()
        try:
            self.ctc = self.telescope.get_cycle_time_calculator(client_config_dict=self.client_cfg) # cycle time calculator
        except Exception as e:
            logger.warning(f'CTC not instanted: {e}')
            self.ctc = None

        published = self.observatory_model.get_telescopes_configuration().get(self.active_tel, {})
        self.optics_model.load(self.active_tel, published.get("observatory", {}).get("components", {}))

        # updating things before starting subsriptions
        # bo na te dzialaja subskrypcje
        self.mntGui.updateUI()
        self.instGui.updateUI()

        await self.focus_set_update()
        self.focus_adjust_switch_update()


        # ---------------------- run subscriptions from ocabox ----------------------
        await self.run_method_in_background(self.ephemeris.asubscribe_utc(self.ephem_update,time_of_data_tolerance=0.25),group="subscribe")
        #
        await self.run_method_in_background(self.user.asubscribe_safety_cutoff_state(self.safetySwitch_update),group="subscribe")
        #
        #
        await self.run_method_in_background(self.dome.asubscribe_connected(self.dome_con_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update),group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_az(self.domeAZ_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_slewing(self.domeStatus_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_dome_fans_running(self.Ventilators_update), group="subscribe")
        #
        await self.run_method_in_background(self.mount.asubscribe_connected(self.mount_con_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_ra(self.ra_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_dec(self.dec_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_az(self.az_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_alt(self.alt_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_tracking(self.mount_tracking_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_slewing(self.mount_slewing_update), group="subscribe")
        await self.run_method_in_background(self.mount.asubscribe_motorstatus(self.mountMotors_update),group="subscribe")
        #
        await self.run_method_in_background(self.cover.asubscribe_coverstate(self.covers_update), group="subscribe")
        await self.run_method_in_background(self.focus.asubscribe_fansstatus(self.mirrorFans_update), group="subscribe")
        #
        if self.has_m3:
            await self.run_method_in_background(self.m3.asubscribe_tertiarystatus(self.m3_update), group="subscribe")
        else:
            # bez M3 nie przyjdzie m3_update, ktory wybiera zakladke instrumentu - kamera
            self.m3_name = None
            self.inst_tab_switch = False
            self.instGui.tab.setCurrentWidget(self.instGui.ccd_tab)
        await self.run_method_in_background(self.optics_model.asubscribe(self.telescope), group="subscribe")
        #
        await self.run_method_in_background(self.fw.asubscribe_connected(self.filter_con_update), group="subscribe")
        await self.run_method_in_background(self.fw.asubscribe_position(self.filter_update), group="subscribe")
        #
        await self.run_method_in_background(self.focus.asubscribe_connected(self.focus_con_update), group="subscribe")
        await self.run_method_in_background(self.focus.asubscribe_position(self.focus_update), group="subscribe")
        await self.run_method_in_background(self.focus.asubscribe_ismoving(self.focus_update), group="subscribe")
        #
        if bool(self.cfg_showRotator):
            await self.run_method_in_background(self.rotator.asubscribe_connected(self.rotator_con_update), group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_position(self.rotator_update), group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_mechanicalposition(self.rotator_update), group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_ismoving(self.rotator_update), group="subscribe")
        #
        await self.run_method_in_background(self.ccd.asubscribe_connected(self.ccd_con_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_ccdtemperature(self.ccd_current_temp_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_setccdtemperature(self.ccd_set_temp_update),group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_binx(self.ccd_binx_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_biny(self.ccd_biny_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_camerastate(self.ccd_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_cooleron(self.ccd_cooler_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_gain(self.ccd_gain_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_readoutmode(self.ccd_rm_update), group="subscribe")
        await self.run_method_in_background(self.ccd.asubscribe_imageready(self.ccd_imageready), group="subscribe")


        # background task specific for selected telescope

        self.add_background_task(self.nats_downloader_reader(), group="telescope_task")
        self.add_background_task(self.nats_ofp_reader(), group="telescope_task")
        self.add_background_task(self.nats_ofp_error_reader(), group="telescope_task")

        self.add_background_task(self.nats_toi_plan_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_ob_status_reader(), group="telescope_task")

        self.add_background_task(self.nats_toi_plan_log_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_log_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_flat_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_focus_status_reader(), group="telescope_task")

        for item in ("flats_evening", "flats_morning", "science", "zeros", "darks"):
            self.add_background_task(self.reader_nats_flat_overwatch(item), group="telescope_task")
        self.add_background_task(self.dome_follower_reader(), group="telescope_task")
        self.add_background_task(self.dome_follower_heartbeat_reader(), group="telescope_task")


        await self.run_background_tasks(group="telescope_task")


        try:
            # nie wiem czy to tez nie powinno byc jednak przed add_background_task
            self.update_dome_temp()
            self.skyGui.updateUI()
            self.planGui.updateUI()
            self.auxGui.updateUI()
            self.fitsGui.updateUI()

            if not bool(self.cfg_showRotator):
                self.set_led(self.mntGui.comRotator1_l, "muted_fg")
                theme.paint(self.mntGui.telRotator1_l, fg="muted_fg")

            self.updateWeather()

        except Exception as e:
            logger.warning(f'EXCEPTION 0: {e}')

        await self.update_log(f'{self.active_tel} telescope selected', "OPERATOR", self.active_tel)



    # ################### METODY POD NATS READERY ##################




    async def nats_toi_plan_status_reader(self):
        try:
            reader = history_reader("plan", self.active_tel)
            async for data, meta in reader:
                try:
                    self.nats_plan_status = data
                    # z kontrola tabela pokazuje lokalny plan, a ta wiadomosc to nasza wlasna publikacja z update_plan
                    # (ktory juz przerysowal tabele) - drugie rysowanie niczego nie zmienia
                    if self.tel_acces.get(self.active_tel) and self.telescope_switch_status.get("plan"):
                        continue

                    # RESET PLAN
                    #


                    self.planGui.update_table()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_plan_status_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 104: {e}')


    async def nats_toi_ob_status_reader(self):
        try:
            reader = history_reader("ob", self.active_tel)
            last_ob = None      # pierwszy odczyt to stan zastany po zmianie teleskopu - nie przelacza zakladek
            async for status, meta in reader:
                try:
                    self.nats_ob_progress = status
                    try:
                        ob = (status.get("ob_program"), status.get("ob_start_time"))
                        if last_ob is not None and ob != last_ob and status.get("ob_started") and not status.get("ob_done"):
                            self.auxGui.ob_started(ob[0])
                        last_ob = ob
                    except Exception as e:
                        logger.warning(f'EXCEPTION 105a: {e}')
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_ob_status_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 105: {e}')



    async def nats_toi_log_reader(self):
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            reader = history_reader("log", self.active_tel, time)     # najpierw historia starego tematu - bez luki
            async for log, meta in reader:
                try:
                    self.planGui.update_log_window(log)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_log_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 106c: {e}')


    async def nats_toi_flat_status_reader(self):
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)  # do konfiguracji
            reader = history_reader("flat", self.active_tel, time)     # najpierw historia starego tematu - bez luki
            async for data, meta in reader:
                try:
                    self.flat_log.append(data)
                    self.flatGui.schedule_update()      # seria rekordow po zmianie teleskopu - jedno rysowanie
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_flat_status_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107a: {e}')



    # async def nats_toi_focus_record_reader(self):           # to moze powinno sie raczej robic jako append

    async def nats_toi_focus_status_reader(self):           # to moze powinno sie raczej robic jako append
        try:
            reader = history_reader("focus", self.active_tel)
            async for data, meta in reader:
                try:
                    self.nats_focus_status = data
                    self.update_focus_window()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_focus_status_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107: {e}')


    async def nats_toi_plan_log_reader(self):
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            reader = history_reader("plan_log", self.active_tel, time)     # najpierw historia starego tematu - bez luki
            async for data, meta in reader:
                try:
                    self.ob_log.append(data)
                    if "uobi" in data.keys():
                        if data["uobi"] not in self.done_uobi:
                            self.done_uobi.append(data["uobi"])
                    self.planGui.update_log_table()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_toi_plan_log_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 106c: {e}')


    async def nats_downloader_reader(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.status.{tel}.download', deliver_policy='last')
            async for data, meta in r:
                try:
                    self.fits_downloader_data = data
                    self.new_fits()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_downloader_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4c: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110: {e}')

    async def nats_ofp_reader(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.status.{tel}.fits.pipeline.raw', deliver_policy='last')
            async for data, meta in r:
                try:
                    self.fits_ofp_data = data
                    self.update_fits_data()
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_ofp_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4a: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110: {e}')


    async def nats_ofp_error_reader(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.planner.{tel}.status.error', deliver_policy='new')
            async for data, meta in r:
                try:
                    await self.update_log(f'{data["error_description"]}', "ERROR", tel)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader nats_ofp_error_reader: bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4a: {e}')


    async def reader_nats_flat_overwatch(self, item):
        # flat_overwatch: osobne kanaly na wieczorne i poranne skyflaty oraz nauke, {filtr: {"last": ISO|None}},
        # i ostatni master zero / dark, {"all": {"last": ISO|None}}
        try:
            tel = self.active_tel
            template = self.local_cfg["toi"].get("flat_overwatch_subject", "data.overwatch.{tel}.camera.{item}")
            r = get_reader(template.format(tel=tel, item=FLAT_OVERWATCH_ITEMS[item]), deliver_policy='last')
            async for data, meta in r:
                try:
                    self.flatGui.update_flat_overwatch(tel, item, data)
                except Exception as e:     # jedna zla wiadomosc nie konczy czytnika na stale
                    logger.warning(f'TOI reader reader_nats_flat_overwatch({item}): bad message skipped: {e!r}')
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4c: {e}')



    # ################### METODY POD SUBSKRYPCJE ##################

    # tu sa wszystkie loop-y

    async def alpaca_con_loop(self):
        while True:
            try:
                if self.telescope is not None:
                    if self.tic_con:
                        tmp = await self.telescope.is_telescope_alpaca_server_available()
                        self.tel_alpaca_con = bool(tmp["alpaca"])
            except Exception as e:
                logger.warning(f'EXCEPTION 0: {e}')
            await asyncio.sleep(3)

    async def almanac_loop(self):
        while True:
            # obsluga Almanacu
            try:
                self.time = time.time()
                self.ut = str(ephem.now())
                self.almanac = Almanac(self.observatory)
                self.jd = self.almanac['jd']
                self.obsGui.main_form.ojd_e.setText(f"{self.almanac['jd']:.6f}")
                self.obsGui.main_form.sid_e.setText(str(self.almanac["sid"]).split(".")[0])
                date=str(self.almanac["ut"]).split()[0]
                self.date=date.split("/")[2]+"/"+date.split("/")[1]+"/"+date.split("/")[0]
                ut=str(self.almanac["ut"]).split()[1]

                self.obsGui.main_form.date_e.setText(str(self.date))
                self.obsGui.main_form.ut_e.setText(str(ut))
                # wysokosc Slonca: dzien zolty (uwaga), zmierzch 0..-18 deg niebieski (zmiana), noc zwykle tlo
                sun_alt = deg_to_decimal_deg(self.almanac["sun_alt"])
                sun_e = self.obsGui.main_form.sun_e
                sun_e.setText(f"{sun_alt:.1f}\u00b0")
                key = "warn_bg" if sun_alt > 0 else "change_bg" if sun_alt > -18 else "field_bg"
                style = theme.field_style(key)
                if sun_e.styleSheet() != style:
                    sun_e.setStyleSheet(style)
                if self.skyGui.skyView:
                    self.skyGui.skyView.updateAlmanac()

            except Exception as e:
                logger.warning(f'EXCEPTION 1: {e}')
            await asyncio.sleep(1)

    async def tel_con_loop(self):
        while True:
            try:
                if self.telescope is not None:
                    m = self.mntGui
                    # (polaczony?, dioda, nazwa) - nazwa w kolorze diody
                    leds = [(self.mount_con, m.mntConn2_l, m.mntConn1_l),
                            (self.dome_con, m.domeConn2_l, m.domeConn1_l),
                            (self.fw_con, m.comFilter_l, m.telFilter_l),
                            (self.focus_con, m.focusConn_l, m.telFocus_l)]
                    if bool(self.cfg_showRotator):
                        leds.append((self.rotator_con, m.comRotator1_l, m.telRotator1_l))
                    else:
                        self.set_led(m.comRotator1_l, "muted_fg")
                        theme.paint(m.telRotator1_l, fg="muted_fg")
                    for con, led, name in leds:
                        # paint nie przelicza stylu, gdy stan sie nie zmienil
                        color = "ok_fg" if con and self.tel_alpaca_con else "bad_fg"
                        self.set_led(led, color)
                        theme.paint(name, fg=color)

                    # kamera: kolor tytulu jej zakladki w oknie instrumentu
                    color = "ok_fg" if self.inst_con and self.tel_alpaca_con else "bad_fg"
                    if getattr(self.instGui.ccd_tab, "tab_color", None) != color:
                        self.instGui.set_connected(self.instGui.ccd_tab, color)

            except Exception as e:
                logger.warning(f'EXCEPTION 2: {e}')
            await asyncio.sleep(3)



    @staticmethod
    def red_progbar_style():
        # pasek postepu OB: blad albo OB trwa ponad 110 % planu - czerwone segmenty
        return ("QProgressBar { border: 2px solid grey; border-radius: 5px; text-align: center; }"
                f" QProgressBar::chunk {{ background-color: {theme.c('bad_bg')}; width: 10px; margin: 1px; }}")

    async def tel_progress_loop(self):
        while True:
            # obsluga wyswietlania paskow postepu ekspozycji
            try:
                if "dit_start" in self.nats_ob_progress.keys():
                    if self.nats_ob_progress["dit_start"] > 0:
                        dt = self.time - self.nats_ob_progress["dit_start"]
                        if dt > self.nats_ob_progress["dit_exp"]:
                            dt = self.nats_ob_progress["dit_exp"]
                            if self.nats_ob_progress["status"] == "exposing":
                                txt = "reading: "
                        else:
                            if self.nats_ob_progress["status"] == "exposing":
                                txt = "exposing: "
                        if self.nats_ob_progress["status"] == "exp done":
                            txt = "DONE "
                        if int(self.nats_ob_progress["dit_exp"]) == 0:
                            p = 100
                        else:
                            p = int(100 * (dt / self.nats_ob_progress["dit_exp"]))
                        self.instGui.ccd_tab.inst_DitProg_n.setValue(p)
                        txt2 = f"{int(dt)}/{int(self.nats_ob_progress['dit_exp'])}"

                        p = int(100 * (self.nats_ob_progress["ndit"] / self.nats_ob_progress["ndit_req"]))
                        self.instGui.ccd_tab.inst_NditProg_n.setValue(p)
                        txt = txt + f"{int(self.nats_ob_progress['ndit'])}/{int(self.nats_ob_progress['ndit_req'])}"

                        self.instGui.ccd_tab.inst_NditProg_n.setFormat(txt)
                        self.instGui.ccd_tab.inst_DitProg_n.setFormat(txt2)
                    else:
                        self.instGui.ccd_tab.inst_NditProg_n.setFormat("")
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 3: {e}')

            # obsluga wyswietlania paska postepu OB

            try:

                if "ob_started" in self.nats_ob_progress.keys() and "ob_expected_time" in self.nats_ob_progress.keys():
                    ob_started = bool(self.nats_ob_progress["ob_started"])
                    ob_done = bool(self.nats_ob_progress["ob_done"])
                    ob_start_time = self.nats_ob_progress["ob_start_time"]
                    ob_expected_time = self.nats_ob_progress["ob_expected_time"]
                    program = self.nats_ob_progress["ob_program"]
                    error = False
                    if "error" in self.nats_ob_progress.keys():
                        error = self.nats_ob_progress["error"]

                    if ob_started:
                        self.planGui.ob_e.setText(program)
                        self.planGui.ob_e.setCursorPosition(0)

                        if ob_expected_time == None or ob_start_time == None:
                            self.planGui.ob_Prog_n.setValue(0)
                            self.planGui.ob_Prog_n.setFormat("")

                        else:

                            if error:
                                t = self.time - float(ob_start_time)
                                p = t / float(ob_expected_time)
                                txt = f"{int(t)}/{int(ob_expected_time)}"
                                self.planGui.ob_Prog_n.setValue(int(100 * p))
                                theme.paint(self.planGui.ob_Prog_n, extra=self.red_progbar_style())
                                txt = f"ERROR {int(t)}/{int(ob_expected_time)}"
                                self.planGui.ob_Prog_n.setFormat(txt)

                            else:
                                t = self.time - float(ob_start_time)
                                p = t / float(ob_expected_time)
                                txt = f"{int(t)}/{int(ob_expected_time)}"
                                self.planGui.ob_Prog_n.setValue(int(100 * p))
                                self.planGui.ob_Prog_n.setFormat(txt)

                                if p > 1.1:     # OB trwa wyraznie dluzej niz planowano
                                    theme.paint(self.planGui.ob_Prog_n, extra=self.red_progbar_style())
                                else:
                                    theme.paint(self.planGui.ob_Prog_n, bg="field_bg")

                    elif ob_done:
                        self.planGui.ob_e.setText("")
                        self.planGui.ob_Prog_n.setValue(100)
                        self.planGui.ob_Prog_n.setFormat(f"DONE")
                        theme.paint(self.planGui.ob_Prog_n, bg="field_bg")

                    else:
                        self.planGui.ob_e.setText("")
                        self.planGui.ob_Prog_n.setValue(0)
                        self.planGui.ob_Prog_n.setFormat(f"")
                        theme.paint(self.planGui.ob_Prog_n, bg="field_bg")


            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 4: {e}')
            await asyncio.sleep(1)


    # STAGE2
    # to na razie jest wylaczone
    async def TOItimer(self):
        while True:
            try:


                for tel in self.acces_grantors.keys():
                    try:
                        acces = await self.acces_grantors[tel].aget_is_access()
                    except Exception as e:
                        logger.warning(f'TOI: EXCEPTION 7a: access read failed for {tel}: {e}')
                    else:
                        if acces is not None:
                            self.tel_acces[tel] = acces
                    try:
                        name = await self.acces_grantors[tel].aget_current_user()
                    except Exception as e:
                        logger.warning(f'TOI: EXCEPTION 7b: current-user read failed for {tel}: {e}')
                    else:
                        if name is not None:
                            self.tel_users[tel] = name["name"]
                    if self.active_tel:
                        if tel == self.active_tel:
                            txt = self.tel_users[tel]
                            self.skyGui.user_e.setText(txt)
                            if self.tel_acces[tel]:     # kontrola: pole w kolorze teleskopu
                                color = QtGui.QColor(self.nats_cfg[tel]['color'] or "#cdd2dc")
                                theme.paint(self.skyGui.user_e, extra=f"background-color: {color.name()}; "
                                                                      f"color: {theme.text_on(color)};")
                            else:
                                theme.paint(self.skyGui.user_e, bg="field_bg")

                self.update_oca()

            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 7: {e}')

            await self.focus_auto_adjast()


            # sterowanie wykonywaniem planu
            try:
                for tel in self.local_cfg["toi"]["telescopes"]:
                    try:
                        if tel in self.planrunners.keys():
                            if "done" in self.ob[tel]["meta"].keys() and "run" in self.ob[tel]["meta"].keys() and "seq" in self.ob[tel]["ob"].keys():
                                if not self.ob[tel]["meta"]["done"] and self.ob[tel]["meta"]["run"] and "seq" in self.ob[tel]["block"]:
                                    if not self.planrunners[tel].is_nightplan_running(self.ob[tel]["meta"]["origin"]):
                                        try:
                                            self.ob_progress[tel]["ob_started"] = self.ob[tel]["meta"]["run"]
                                            self.ob_progress[tel]["ob_done"] = self.ob[tel]["meta"]["done"]
                                            self.ob_progress[tel]["ob_start_time"] = self.ob_start_time
                                            self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["meta"]["slot_time"]
                                            self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                                            self.ob_progress[tel]["error"] = True

                                            await self.nats_toi_ob_status[tel].publish(data=self.ob_progress[tel], timeout=10)
                                        except Exception as e:
                                            logger.warning(f'TOI: EXCEPTION 8a: {e}')

                                        try:
                                            info = f"program error on {tel}"
                                            label = "PROGRAM ERROR"
                                            await self.send_ocm_message(info, label=label)
                                        except Exception as e:
                                            logger.warning(f'TOI: EXCEPTION 8b: {e}')
                                        self.ob[tel]["meta"]["done"] = False
                                        self.ob[tel]["meta"]["run"] = False
                                        self.ob[tel]["meta"]["continue_plan"] = False
                                        await self.update_log(f'planrunner STOPPED', "ERROR", tel)

                        if self.telescope and self.tel_acces[tel] is False:    # obsluga tego ze w czasie realizacji planu, ktos inny przejal kontrole; None = unknown, NOT a takeover
                            if "continue_plan" in self.ob[tel]["meta"].keys():
                                if self.ob[tel]["meta"]["continue_plan"]:
                                    self.ob[tel]["meta"]["continue_plan"] = False
                                    self.current_i[tel] = -1
                                    self.ob[tel]["done"] = False
                                    self.update_plan(tel)

                        if self.telescope and self.tel_acces[tel]:
                            if self.ob[tel]["meta"].get("origin"):
                                if "done" in self.ob[tel]["meta"].keys() and "origin" in self.ob[tel]["meta"].keys() and "continue_plan" in self.ob[tel]["meta"].keys():
                                    if self.ob[tel]["meta"]["done"] and "plan" in self.ob[tel]["meta"]["origin"] and self.ob[tel]["meta"]["continue_plan"]:
                                        await self.plan_start(tel)
                                    elif "plan" in self.ob[tel]["meta"]["origin"] and self.ob[tel]["meta"]["continue_plan"]:
                                        if "sec" in self.ob[tel]["ob"].keys() and "start_time" in self.ob[tel]["meta"].keys():
                                            if self.ob[tel]["ob"]["sec"] != "":
                                                dt = self.time - self.ob[tel]["meta"]["start_time"]
                                                if float(dt) > float(self.ob[tel]["ob"]["sec"]):
                                                    self.ob[tel]["meta"]["done"] = True
                                                    self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                                                    await self.check_plan_finished(tel)
                                                    self.current_i[tel] = -1
                                                    self.update_plan(tel)
                                                    time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                                    tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sec={self.ob[tel]["ob"]["sec"]}'}},"time": {"end_dt": time}}
                                                    self.plan_log_agregator(tel, tmp)
                                        if "ut" in self.ob[tel]["ob"].keys():
                                            if self.ob[tel]["ob"]["ut"] != "":
                                                if wait_ut_sec(self.ob[tel]["ob"]["ut"], ephem.now()) <= 0:
                                                    self.ob[tel]["meta"]["done"] = True
                                                    self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                                                    await self.check_plan_finished(tel)
                                                    self.current_i[tel] = -1
                                                    self.update_plan(tel)
                                                    time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                                    tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'ut={self.ob[tel]["ob"]["ut"]}'}},"time": {"end_dt": time}}
                                                    self.plan_log_agregator(tel, tmp)
                                        if "sunrise" in self.ob[tel]["ob"].keys():
                                            if self.ob[tel]["ob"]["sunrise"] != "":
                                                if deg_to_decimal_deg(self.almanac["sun_alt"]) > float(self.ob[tel]["ob"]["sunrise"]):
                                                    self.ob[tel]["meta"]["done"] = True
                                                    self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                                                    await self.check_plan_finished(tel)
                                                    self.current_i[tel] = -1
                                                    self.update_plan(tel)
                                                    time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                                    tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sunrise={self.ob[tel]["ob"]["sunrise"]}'}},"time": {"end_dt": time}}
                                                    self.plan_log_agregator(tel, tmp)
                                        if "sunset" in self.ob[tel]["ob"].keys():
                                            if self.ob[tel]["ob"]["sunset"] != "":
                                                if deg_to_decimal_deg(self.almanac["sun_alt"]) < float(self.ob[tel]["ob"]["sunset"]):
                                                    self.ob[tel]["meta"]["done"] = True

                                                    self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                                                    await self.check_plan_finished(tel)
                                                    self.current_i[tel] = -1
                                                    self.update_plan(tel)
                                                    time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                                    tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sunset={self.ob[tel]["ob"]["sunset"]}'}},"time": {"end_dt": time}}
                                                    self.plan_log_agregator(tel, tmp)
                    except Exception as e:     # blad jednego teleskopu nie zatrzymuje sterowania planem pozostalych
                        logger.exception(f'TOI: EXCEPTION 8 (plan control, {tel}): {e}')

            except Exception as e:
                logger.exception(f'TOI: EXCEPTION 8 (plan control): {e}')

            await asyncio.sleep(1)

    async def read_for_action(self, getter, what):
        """stan urzadzenia dla decyzji przycisku: zapytanie (aget_*), nie pamiec ocaboxa (werdykt Mikolaja: wlasciwosci
        synchroniczne poza callbackiem to odczyt niesprawdzonej historii). Blad / brak odpowiedzi -> komunikat i
        LookupError (przycisk nic nie robi)"""
        try:
            return await getter()
        except Exception as e:
            logger.warning(f'TOI: cannot read {what}: {e!r}')
            await self.update_log(f'cannot read {what} - nothing done', "WARNING", self.active_tel)
            self.WarningWindow(f"WARNING: cannot read {what} - nothing done")
            raise LookupError(what)

    @staticmethod
    async def delivered(event, getter):
        """Wartosc w callbacku subskrypcji ocabox: ta, ktora subskrypcja wlasnie dostarczyla - z komponentu i parametru
        zdarzenia (event.obj, event.name; event.new to funkcja parametru, nie wartosc). Wg Mikolaja (2026-09) jedyny
        poprawny odczyt z cache komponentu; event.obj to komponent, ktory wyslal zdarzenie - zdarzenie starego teleskopu
        po przelaczeniu nie wpisze wartosci z kamery / montazu nowego. Bez zdarzenia (wywolanie reczne, np. przywrocenie
        przelacznika) - zapytanie do serwera jak dotad. Gdy ocabox zacznie podawac callbackom Value (jak dla optyki),
        zmiana tylko tutaj."""
        if hasattr(event, "obj") and hasattr(event, "name"):
            return getattr(event.obj, event.name)
        return await getter()

    async def _remember_focus(self, tel):
        """pozycja fokusera przed autofocusem - do niej wraca nieudany autofocus; nieznana -> None (nie stara wartosc)"""
        try:
            pos = await self.tel_focusers[tel].aget_position()
        except Exception as e:
            logger.warning(f'TOI: {tel} focuser position: {e!r}')
            pos = None
        self.last_focus_position[tel] = float(pos) if pos is not None else None
        if pos is None:
            await self.update_log('focuser position unknown - if the autofocus fails, the focuser stays where it is',
                                  "WARNING", tel)

    async def _focus_failed(self, tel):
        """nieudany autofocus: fokuser wraca do pozycji sprzed autofocusa, jesli ja znamy"""
        prev = self.last_focus_position[tel]
        if prev is None:
            await self.update_log('focusing FAILED. Previous focus unknown - focuser not moved', "TOI", tel)
            return
        await self.focus_move(tel, prev, "autofocus_failed")
        await self.update_log(f'focusing FAILED. Focus set to previous value {int(prev)}', "TOI", tel)

    def _pop_current(self, tel):
        """wykonany OB (current_i) z planu; nastepny startuje z jego miejsca. Przy current_i spoza planu (-1 po Stop /
        Del All / przejeciu kontroli) nic nie usuwa - pop(-1) zabieral po cichu ostatni OB planu"""
        i = self.current_i[tel]
        if 0 <= i < len(self.plan[tel]):
            self.next_i[tel] = i
            self.plan[tel].pop(i)
            return True
        logger.warning(f'TOI: {tel} finished OB not removed - current_i {i}, plan length {len(self.plan[tel])}')
        return False

    async def check_plan_finished(self, tel):
        if len(self.plan[tel]) == 0:
            self.ob[tel]["meta"]["run"] = False
            self.ob[tel]["meta"]["continue_plan"] = False
            self.current_i[tel] = -1
            await self.update_log('plan FINISHED', "INFO", tel)

    # ############ PLAN RUNNER START ##########################



    @qs.asyncSlot()
    async def planrunner_start(self,tel):
        try:
            if self.tel_acces[tel]:
                if tel not in self.planrunners.keys():
                    self.planrunners[tel] = self.tic_telescopes[tel].get_observation_plan()
                    tmp = self.planrunners[tel]
                    self.planrunners[tel].add_info_callback('exec_json', lambda info: self.PlanRunFeedback(tmp, info))
                self.ob_progress[tel]["ndit"] = 0
                self.ob_progress[tel]["dit_start"] = 0

                program = self.ob[tel]["block"]
                program_name = self.ob[tel]["meta"]["origin"]
                await self.planrunners[tel].aload_nightplan_string(program_name, string=program, overwrite=True, client_config_dict=self.client_cfg)
                await self.planrunners[tel].arun_nightplan(program_name, step_id="00")
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 11: {e}')
            await self.update_log(f'planrunner start FAILED: {e!r}', "ERROR", tel)

    # ############ PLAN RUNNER CALLBACK ##########################

    @qs.asyncSlot()
    async def PlanRunFeedback(self,planrunner,info):

        tel = [k for k,val in self.planrunners.items() if val == planrunner][0]

        for t in self.local_cfg["toi"]["telescopes"]:
            if t==tel:

                # NORMAL PLAN

                if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
                    if info["name"] == "NIGHTPLAN" and info["started"] and not info["done"]:
                        self.ob[tel]["meta"]["run"] = True     # to swiadczy o tym czy planrunner dziala
                        self.ob[tel]["meta"]["done"] = False
                        self.ob_start_time = self.time

                        try:
                            if tel == self.active_tel and self.ctc is not None:
                                # kalkulator i montaz aktywnego teleskopu - tylko dla niego (slew od biezacej pozycji)
                                self.ctc.reset_time()
                                self.ctc.set_start_time(datetime.datetime.now(datetime.timezone.utc))
                                self.ctc.set_start_rmode(self.readout_mode(tel))
                                self.ctc.set_telescope_start_az_alt(az=self.mount_az, alt=self.mount_alt)
                                slot_time = self.ctc.calc_time(self.ob[tel]["block"])
                            else:
                                # inny teleskop: jego wlasny CTC i tryb odczytu, jak przy liczeniu planu
                                slot_time, _ = self._calc_ctc(tel=tel, rm_now=self.readout_mode(tel), first_ctc=True,
                                                              prog_block=self.ob[tel]["block"])
                            self.ob[tel]["meta"]["slot_time"] = slot_time if slot_time is not None else 0.1
                            if self.ob[tel]["meta"]["slot_time"] == 0:
                                print("** CTC time estimation = 0!")
                                print("** OB: ",self.ob[tel]["block"])
                                self.ob[tel]["meta"]["slot_time"] = 0.1
                        except ValueError as e:
                            self.ob[tel]["meta"]["slot_time"] = 0.1
                            logger.warning(f'TOI: EXCEPTION 44: {e}')
                        except Exception as e:
                            self.ob[tel]["meta"]["slot_time"] = 0.1
                            logger.warning(f'TOI: CTC malfunction')
                            logger.warning(f'TOI: EXCEPTION 44: {e}')

                        txt = self.ob[tel]["block"]

                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = self.ob[tel]["meta"]["run"]
                            self.ob_progress[tel]["ob_done"] = self.ob[tel]["meta"]["done"]
                            self.ob_progress[tel]["ob_start_time"] = self.ob_start_time
                            self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["meta"]["slot_time"]
                            self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                            self.ob_progress[tel]["error"] = False
                            await s.publish(data=self.ob_progress[tel],timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 45: {e}')

                    elif info["name"] == "NIGHTPLAN" and info["done"]:
                        self.ob[tel]["meta"]["done"] = True

                        if "plan" in self.ob[tel]["meta"]["origin"]:
                            self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                            await self.check_plan_finished(tel)
                            self.current_i[tel] = -1
                            self.update_plan(tel)

                        self.ob_progress[tel]["dit_start"] = 0

                        try:
                            s = self.nats_toi_ob_status[tel]
                            data = self.ob_progress[tel]
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 46: {e}')

                        self.ob[tel]["meta"]["run"] = False
                        self.ob[tel]["meta"]["done"] = True
                        await self.update_log(f'OB: finished ', "TOI", tel)


                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = self.ob[tel]["meta"]["run"]
                            self.ob_progress[tel]["ob_done"] = self.ob[tel]["meta"]["done"]
                            self.ob_progress[tel]["ob_start_time"] = self.ob[tel]["meta"]["start_time"]
                            self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["meta"]["slot_time"]
                            self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                            self.ob_progress[tel]["error"] = False

                            await s.publish(data=self.ob_progress[tel],timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 47: {e}')



                if "exp_started" in info.keys() and "exp_done" in info.keys():
                    if info["exp_started"] and not info["exp_done"]:
                        self.ob_progress[tel]["ndit"]=float(info["n_exp"])
                        self.ob_progress[tel]["ndit_req"]=float(info["exp_no"])
                        self.ob_progress[tel]["dit_exp"]=float(info["exp_time"])
                        self.ob_progress[tel]["dit_start"]=self.time
                        self.ob_progress[tel]["status"]="exposing"

                        try:
                            s = self.nats_toi_ob_status[tel]
                            data = self.ob_progress[tel]
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 48: {e}')


                    elif info["exp_done"] and info["exp_saved"]:
                        self.ob_progress[tel]["ndit"]=float(info["n_exp"])
                        self.ob_progress[tel]["status"]="exp done"

                        try:
                            s = self.nats_toi_ob_status[tel]
                            data = self.ob_progress[tel]
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 49: {e}')


                if "auto_exp_start" in info.keys() and "auto_exp_finnished" in info.keys():    # SKYFLAT
                    if info["auto_exp_start"] and not info["auto_exp_finnished"]:
                        self.ob_progress[tel]["ndit"]=0
                        self.ob_progress[tel]["ndit_req"]=float(info["exp_no"])
                        self.ob_progress[tel]["dit_exp"]=float(info["auto_exp_time"])
                        self.ob_progress[tel]["dit_start"]=self.time
                        self.ob_progress[tel]["status"]="exposing"

                        try:
                            s = self.nats_toi_ob_status[tel]
                            data = self.ob_progress[tel]
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 50: {e}')



                    elif info["auto_exp_finnished"]:
                        pass

                if "test_exp_mean" in info.keys():                                                        # SKYFLAT
                    pass

                if "id" in info.keys():  # to jest tylko do wyswietlania w oknie loga planu
                    self.program_id = info["id"]
                    ut=str(self.almanac["ut"]).split()[1].split(":")[0]+":"+str(self.almanac["ut"]).split()[1].split(":")[1]
                    txt = f"------  {ut}  -----  {self.program_id}  ------\n {info}\n\n"
                    self.planrunnerGui.text[tel] = self.planrunnerGui.text[tel] + txt
                    self.planrunnerGui.updateUI()

                # FLAT RECORDER


                if set(["type","exp_done","timestamp_utc","mean","exp_time","filter","exp_no","n_exp"]).issubset(info.keys()):
                    if info["type"] == "flat" and info["exp_done"]:
                        fr = {}
                        fr["timestamp_utc"] = info["timestamp_utc"]
                        fr["mean"] = info["mean"]
                        fr["exp_time"] = info["exp_time"]
                        fr["filter"] = info["filter"]
                        fr["h_sun"] = f"{deg_to_decimal_deg(self.almanac['sun_alt']):.2f}"
                        fr["n_exp"] = info['n_exp']
                        fr["exp_no"] = info['exp_no']
                        try:
                            data = fr
                            await self.nats_toi_flat_status[tel].publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 51: {e}')

                try:

                    # AUTOFOCUS


                    if self.autofocus_started[tel]:
                        if "id" in info.keys():
                            if "auto_focus" in info["id"] and info["started"]==True and info["done"]==True:
                                self.autofocus_started[tel] = False

                                result = Focus.calculate(fits_path=self.local_cfg[tel]["tel_directory"] + "focus/actual",method=self.focus_method)

                                if result is None:
                                    await self._focus_failed(tel)
                                else:
                                    max_sharpness_focus, calc_metadata = result

                                    try:
                                        data = {}
                                        data["time"] = self.ut
                                        data["coef"] = list(calc_metadata["coef"])
                                        data["focus_values"] = list(calc_metadata["focus_values"])
                                        data["sharpness_values"] = list(calc_metadata["sharpness_values"])
                                        data["max_sharpness_focus"] = float(max_sharpness_focus)
                                        data["fit_x"] = list(calc_metadata["fit_x"])
                                        data["fit_y"] = list(calc_metadata["fit_y"])
                                        data["status"] = str(calc_metadata["status"])
                                        data["davis_temperature"] = self.telemetry_temp
                                        data["davis_humidity"] = self.telemetry_humidity
                                        data["method"] = self.focus_method
                                        try:
                                            data["temperature"] = self.sensors[tel]["dome_conditions"]["temperature"]
                                        except Exception:
                                            data["temperature"] = "--"
                                        try:
                                            pos = self.oca_tel_state[tel]["fw_position"]["val"]
                                            data["filter"] = self.nats_cfg[tel]["filter_list_names"][pos]
                                        except Exception:
                                            data["filter"] = "--"

                                        await self.nats_toi_focus_status[tel].publish(data=data, timeout=10)

                                        data_short = {}
                                        data_short["status"] = data["status"]
                                        data_short["temperature"] = data["temperature"]
                                        data_short["max_sharpness_focus"] = data["max_sharpness_focus"]
                                        data_short["time"] = data["time"]
                                        data_short["filter"] = data["filter"]
                                        data_short["davis_temperature"]  = data["davis_temperature"]
                                        data_short["davis_humidity"] = data["davis_humidity"]
                                        data_short["method"] = data["method"]

                                        await self.nats_toi_focus_record[tel].publish(data=data_short, timeout=10)
                                        self.nats_focus_record[tel] = data_short

                                    except Exception as e:
                                        logger.warning(f'TOI: EXCEPTION 42: {e}')

                                    if calc_metadata["status"] == "ok":
                                        await self.focus_move(tel, max_sharpness_focus, "autofocus")
                                        await self.update_log(f'focus set to {int(max_sharpness_focus)}', "TOI", tel)
                                    else:
                                        await self._focus_failed(tel)


                                if "switchOnFocusAdjast" in self.ob[tel]["meta"].keys():
                                    if self.ob[tel]["meta"]["switchOnFocusAdjast"]:
                                        await self.update_log(f'turning focus adjust ON', "TOI RESPONDER",tel)
                                        self.toi_switch_status[tel]["focus_adjust"] = True
                                        await self.nats_toi_switch_synchro[tel].publish(data=self.toi_switch_status[tel], timeout=10)


                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 37: {e}')



    # ############ AUTO FOCUS ##########################

    @qs.asyncSlot()
    async def auto_focus(self):
        await self.update_log(f'AUTOFOCUS', "OPERATOR", self.active_tel )
        if self.tel_acces[self.active_tel]:
            ok = False
            v0 = float(self.focusGui.last_e.text())
            step = float(self.focusGui.steps_e.text())
            number = float(self.focusGui.range_e.text())
            method = self.focusGui.method_s.currentText()
            if method == "rms":
                self.focus_method = "rms"
                if number > 2:
                    ok = True
                else:
                    await self.update_log(f'Not enough STEPS number', "WARNING", self.active_tel)
            else:
                self.focus_method = method
                if number > 4:
                    ok = True
                else:
                    await self.update_log(f'Not enough STEPS number', "WARNING", self.active_tel)

            if ok:
                exp = self.focusGui.exp_e.text().strip()
                try:
                    ok = float(exp) > 0
                except ValueError:
                    ok = False
                if not ok:
                    await self.update_log(f'wrong focus exposure time: {exp}', "WARNING", self.active_tel)
                    return
                filtr = self.focusGui.filter_s.currentText()
                if filtr == "current":
                    filtr = self.curent_filter

                seq = f"{int(number)}/"+str(filtr)+"/"+str(exp)
                pos = f"{int(v0)}/{int(step)}"
                uobi = str(uuid.uuid4())[:8]
                program = f"FOCUS seq={seq} pos={pos} uobi={uobi}"

                self.ob[self.active_tel]["block"] = program
                self.ob[self.active_tel]["meta"]["origin"] = "auto_focus"

                self.ob[self.active_tel]["meta"]["switchOnFocusAdjast"] = False
                if self.mntGui.telAutoFocus_c.isChecked():
                    self.ob[self.active_tel]["meta"]["switchOnFocusAdjast"] = True
                    await self.update_log(f'turning focus adjust OFF', "TOI RESPONDER", self.active_tel)
                    self.toi_switch_status[self.active_tel]["focus_adjust"] = False
                    await self.nats_toi_switch_synchro[self.active_tel].publish(
                        data=self.toi_switch_status[self.active_tel], timeout=10)

                self.autofocus_started[self.active_tel] = True
                await self._remember_focus(self.active_tel)
                await self.update_log(f'autofocussing', "TOI RESPONDER", self.active_tel)
                self.planrunner_start(self.active_tel)


        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    # ############ PLAN ##########################

    @qs.asyncSlot()
    async def manual_plan_start(self,tel):
        await self.update_log(f'PLAN START ', "OPERATOR", tel)

        await self.plan_start(tel)

    # to ustawia wszytskie potrzebne parametry dla planrunnera i wywoluje planrunner_start
    @qs.asyncSlot()
    async def plan_start(self,tel):
        if self.tel_acces[tel]:

            if self.next_i[tel] > -1 and self.next_i[tel] < len(self.plan[tel]):
                self.ob[tel] = self.plan[tel][self.next_i[tel]]
                self.ob[tel]["meta"]["start_time"] = self.time


                if "command_name" in self.ob[tel]["ob"].keys():

                    self.current_i[tel] = self.next_i[tel]
                    self.update_plan(tel)

                    run_nightplan = False
                    if self.ob[tel]["ob"]["command_name"] == "STOP":
                        self.ob[tel]["meta"]["done"]=True
                        self.ob[tel]["meta"]["run"]=True
                        self.ob[tel]["meta"]["origin"] = "plan"
                        self.ob[tel]["meta"]["continue_plan"] = False

                        self.next_i[tel] = self.current_i[tel] + 1
                        self.current_i[tel] = -1
                        self.update_plan(tel)
                        await self.update_log(f'STOP reached ', "TOI", tel)

                        time = self.ut.split()[0]+"T"+self.ut.split()[1]
                        tmp = {"object_name": "STOP", "command_dict":{"command_name":""},"time":{"end_dt":time}}
                        self.plan_log_agregator(tel,tmp)



                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = True
                            self.ob_progress[tel]["ob_done"] = False
                            self.ob_progress[tel]["ob_start_time"] = self.time
                            self.ob_progress[tel]["ob_expected_time"] = None
                            self.ob_progress[tel]["ob_program"] = "STOP"
                            self.ob_progress[tel]["error"] = False

                            await s.publish(data=self.ob_progress[tel], timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 51: {e}')

                        try:
                            info = f"STOP on {tel}"
                            label = "PROGRAM STOP"
                            await self.send_ocm_message(info, label=label)
                            await self.update_log(f'STOP reached ', "TOI", tel)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 45: {e}')


                    if self.ob[tel]["ob"]["command_name"] == "BELL":

                        try:

                            info = f"BELL on {tel}"
                            label = "PROGRAM BELL"
                            await self.send_ocm_message(info, label=label)
                            await self.update_log(f'BELL reached ', "TOI", tel)

                            time = self.ut.split()[0] + "T" + self.ut.split()[1]
                            tmp = {"object_name": "BELL", "command_dict": {"command_name": ""},
                                   "time": {"end_dt": time}}
                            self.plan_log_agregator(tel, tmp)

                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 45: {e}')


                        self.ob[tel]["meta"]["done"]=True
                        self.ob[tel]["meta"]["run"]=True
                        self.ob[tel]["meta"]["origin"] = "plan"
                        self.ob[tel]["meta"]["continue_plan"] = True

                        self._pop_current(tel)       # wykonany OB z planu (nie przy current_i = -1)
                        await self.check_plan_finished(tel)
                        self.current_i[tel] = -1
                        self.update_plan(tel)


                    if self.ob[tel]["ob"]["command_name"] == "WAIT":
                        if "sec" in self.ob[tel]["ob"].keys():
                            if len(str(self.ob[tel]["ob"]["sec"]))>0:
                                self.ob[tel]["meta"]["start_time"] = self.time
                                self.ob[tel]["meta"]["done"]=False
                                self.ob[tel]["meta"]["run"]=True
                                await self.update_log(f'starting WAIT ', "TOI", tel)
                        if "ut" in self.ob[tel]["ob"].keys():
                            if len(str(self.ob[tel]["ob"]["ut"]))>0:
                                self.ob[tel]["meta"]["done"]=False
                                self.ob[tel]["meta"]["run"]=True
                                await self.update_log(f'starting WAIT ', "TOI", tel)
                        if "sunset" in self.ob[tel]["ob"].keys():
                            if len(str(self.ob[tel]["ob"]["sunset"]))>0:
                                self.ob[tel]["meta"]["done"]=False
                                self.ob[tel]["meta"]["run"]=True
                                await self.update_log(f'starting WAIT ', "TOI", tel)
                        if "sunrise" in self.ob[tel]["ob"].keys():
                            if len(str(self.ob[tel]["ob"]["sunrise"]))>0:
                                self.ob[tel]["meta"]["done"]=False
                                self.ob[tel]["meta"]["run"]=True
                                await self.update_log(f'starting WAIT ', "TOI", tel)
                        self.ob[tel]["meta"]["continue_plan"] = True
                        self.ob[tel]["meta"]["origin"] = "plan"

                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = True
                            self.ob_progress[tel]["ob_done"] = False
                            self.ob_progress[tel]["ob_start_time"] = self.time
                            self.ob_progress[tel]["ob_expected_time"] = None
                            self.ob_progress[tel]["ob_program"] = "WAIT"
                            self.ob_progress[tel]["error"] = False

                            await s.publish(data=self.ob_progress[tel], timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 51: {e}')

                    if self.ob[tel]["ob"]["command_name"] == "ZERO" and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan"
                        program = self.ob[tel]["block"]

                    if self.ob[tel]["ob"]["command_name"] == "DARK" and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan"
                        program = self.ob[tel]["block"]

                    if self.ob[tel]["ob"]["command_name"] == "DOMEFLAT" and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan_domeflat"
                        program = self.ob[tel]["block"]

                    if self.ob[tel]["ob"]["command_name"] == "SKYFLAT" and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan_skyflat"
                        program = self.ob[tel]["block"]

                    if self.ob[tel]["ob"]["command_name"] == "FOCUS" and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan_auto_focus"
                        program = self.ob[tel]["block"]

                        # najpierw pozycja fokusera (do niej wraca nieudany autofocus) - przed wylaczeniem focus
                        # adjust, zeby blad odczytu nie zostawial niczego w polowie
                        await self._remember_focus(tel)
                        self.focus_method = self.focus_default_method(tel)
                        self.autofocus_started[tel] = True

                        self.ob[tel]["meta"]["switchOnFocusAdjast"] = False
                        if self.toi_switch_status[tel]["focus_adjust"]:
                            self.ob[tel]["meta"]["switchOnFocusAdjast"] = True
                            self.toi_switch_status[tel]["focus_adjust"] = False
                            await self.nats_toi_switch_synchro[tel].publish(
                                data=self.toi_switch_status[tel], timeout=10)

                    # SNAP w planie jak OBJECT (planrunner go zna - okno Instrument tak go uruchamia); dawniej bez
                    # galezi: OB zostawal "wykonywany", a plan stal po cichu
                    if self.ob[tel]["ob"]["command_name"] in ("OBJECT", "SNAP") and "block" in self.ob[tel].keys():
                        run_nightplan = True
                        program_name = "plan"
                        program = self.ob[tel]["block"]
                        #DUPA
                        if "comment" in program:
                            program = program.split("comment")[0]

                    if not run_nightplan and self.ob[tel]["ob"]["command_name"] not in ("STOP", "BELL", "WAIT"):
                        # komenda, ktorej plan nie umie uruchomic - stop z komunikatem zamiast cichego stania
                        cmd = self.ob[tel]["ob"]["command_name"]
                        self.ob[tel]["meta"]["continue_plan"] = False
                        self.current_i[tel] = -1
                        self.update_plan(tel)
                        await self.update_log(f'OB {cmd} not supported in a plan - plan stopped', "WARNING", tel)

                    if run_nightplan:
                        self.ob[tel]["block"] = program
                        self.ob[tel]["meta"]["origin"] = program_name
                        self.ob[tel]["meta"]["continue_plan"] = True
                        self.planrunner_start(tel)
                        await self.update_log(f'starting OB: {program} ', "TOI", tel)


        else:
            pass


    @qs.asyncSlot()
    async def resume_program(self):
        await self.update_log(f'program RESUME', "OPERATOR", self.active_tel)
        await self.planrunners[self.active_tel].astop_nightplan()
        await self.planrunners[self.active_tel].arun_nightplan(self.ob[self.active_tel]["meta"]["origin"], step_id=self.program_id)
        await self.update_log(f'resuming program', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def stop_program(self):
        await self.update_log(f'program STOP', "OPERATOR", self.active_tel)
        await self.takeControl()
        try:
            await self.planrunners[self.active_tel].astop_nightplan()
            await self.update_log(f'stopping program', "TOI RESPONDER", self.active_tel)
        except KeyError:
            pass
        await self.ccd.aput_stopexposure()
        await self.update_log(f'stopping exposure', "TOI RESPONDER", self.active_tel)


        self.ob[self.active_tel]["meta"]["done"] = False
        self.ob[self.active_tel]["meta"]["run"] = False
        self.ob[self.active_tel]["meta"]["origin"] = "plan"
        self.ob[self.active_tel]["meta"]["continue_plan"] = False
        self.ob[self.active_tel]["meta"]["slot_time"] = None
        self.ob[self.active_tel]["meta"]["start_time"] = None

        self.current_i[self.active_tel] = -1
        self.update_plan(self.active_tel)

        try:
            s = self.nats_toi_ob_status[self.active_tel]
            self.ob_progress[self.active_tel]["ob_started"] = False
            self.ob_progress[self.active_tel]["ob_done"] = False
            self.ob_progress[self.active_tel]["ob_start_time"] = None
            self.ob_progress[self.active_tel]["ob_expected_time"] = None
            self.ob_progress[self.active_tel]["ob_program"] = "STOPPED"
            self.ob_progress[self.active_tel]["error"] = False
            self.ob_progress[self.active_tel]["dit_start"]=0

            await s.publish(data=self.ob_progress[self.active_tel], timeout=10)

        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 56: {e}')

    # ########### LOKALNA OBSLGA PLANU ##################

    def upload_plan(self):
        self.plan[self.active_tel] = self.planGui.plan
        self.next_i[self.active_tel] = self.planGui.next_i
        self.planGui.update_table()
        self.update_plan(self.active_tel)


    def _calc_ctc(
            self, tel: str, rm_now: int, first_ctc: bool,
            prog_block: Union[Dict[str, Any], str], start_time: Optional[datetime.datetime] = None) -> Tuple[Optional[float], bool]:

        if os.path.exists(self.local_cfg["ctc"]["ctc_base_folder"]):
            if tel not in self.ctc_dat.keys() and tel is not None and rm_now is not None:
                self.ctc_dat[tel] = CycleTimeCalc(
                    telescope=tel,
                    base_folder=self.local_cfg["ctc"]["ctc_base_folder"],
                    tpg=False
                )
                self.ctc_dat[tel].set_rm_modes(
                    self.local_cfg["ctc"]["rm_modes_mhz"]
                )
                # TODO do this properly
                self.ctc_dat[tel].set_observatory_location(
                    {'latitude': -24.598056, 'longitude': -70.196389, 'elevation': 2817}
                )
                self.ctc_dat[tel].set_start_rmode(rm_now)
            if first_ctc and rm_now is not None:
                self.ctc_dat[tel].reset_time()
                self.ctc_dat[tel].set_start_rmode(rm_now)
                if start_time is not None:
                    self.ctc_dat[tel].set_start_time(start_time)
                else:
                    self.ctc_dat[tel].set_start_time(datetime.datetime.now(datetime.timezone.utc))
                first_ctc = False
            slot_time = self.ctc_dat[tel].calc_time(prog_block)
            return slot_time, first_ctc
        else:
            return None, first_ctc

    @qs.asyncSlot()
    async def update_plan(self,tel):
            if self.plan[tel] != None:
                if len(self.plan[tel]) == 0:
                    self.planGui.update_table()
                else:
                    self.check_next_i(tel)
                    rm_now = self.readout_mode(tel)
                    now = ephem.now()

                    # Jedna os czasu: ob_time = planowany start kolejnego OB.
                    # CTC liczy na wlasnej osi (start_time + suma czasow), wiec pilnujemy zeby byla
                    # zgodna z ob_time - jak nie jest (ctc_synced=False), CTC startuje od nowa od ob_time.
                    ob_time = now
                    ctc_synced = False

                    # planujemy od biezacego OB (albo od next, jak nic nie leci)
                    starts = [k for k in (self.current_i[tel], self.next_i[tel]) if k > -1]
                    first_i = min(starts) if starts else len(self.plan[tel])

                    for i, tmp in enumerate(self.plan[tel]):
                        ob = self.plan[tel][i]["ob"]
                        meta = self.plan[tel][i]["meta"]
                        scheduled = i >= first_i
                        running = i == self.current_i[tel]
                        skipped = self._ob_skipped(meta) and not running
                        on_timeline = scheduled and not running and not skipped

                        if running and meta.get("start_time"):
                            ob_time = now - (self.time - meta["start_time"]) * ephem.second
                        # dla biezacego OB czekanie liczymy od teraz, dla reszty od planowanego startu
                        t0 = now if running else ob_time
                        t0_dt = ephem.Date(t0).datetime().replace(tzinfo=datetime.timezone.utc)
                        elapsed = (t0 - ob_time) / ephem.second

                        # liczenie czasu ob
                        is_wait = ob.get("command_name") == "WAIT"
                        if is_wait and "ut" in ob:
                            # tak samo jak wykonanie WAIT ut w petli planu (wait_ut_sec)
                            meta["slotTime"] = elapsed + wait_ut_sec(ob["ut"], t0)
                            ctc_synced = False

                        elif is_wait and ("sunset" in ob or "sunrise" in ob):
                            wait, _ = self._calc_ctc(tel=tel, rm_now=rm_now, first_ctc=True,
                                                     prog_block=self.plan[tel][i]["block"], start_time=t0_dt)
                            if wait is not None:
                                meta["slotTime"] = elapsed + wait
                            # CTC wystartowal od t0 i skonczyl na koncu WAIT
                            ctc_synced = wait is not None and (on_timeline or running)

                        elif is_wait and "sec" in ob:
                            try:
                                meta["slotTime"] = float(ob["sec"])
                            except (TypeError, ValueError):
                                meta["slotTime"] = 0
                            ctc_synced = False

                        elif "seq" in ob:
                            if not meta.get("slotTime") or meta.get("slotTime_rm") != rm_now:
                                slotTime, _ = self._calc_ctc(tel=tel, rm_now=rm_now, first_ctc=not (ctc_synced and on_timeline),
                                                             prog_block=self.plan[tel][i]["block"], start_time=t0_dt)
                                if slotTime is None:
                                    slotTime = ObsValidator.calc_seq_time(
                                        ob["seq"], overhead=self.overhed, base_time=5,
                                        filter_overhead=2, auto_time=5
                                    )
                                    if slotTime is None and not meta.get("seq_warned"):
                                        # zla sekwencja: OB bez czasu wypada z osi czasu planu - raz mowimy operatorowi
                                        meta["seq_warned"] = True
                                        asyncio.ensure_future(self.update_log(
                                            f'wrong seq in OB {ob.get("name", ob.get("command_name", "?"))}: {ob["seq"]}'
                                            f' - no time for it in the plan', "WARNING", tel))
                                else:
                                    ctc_synced = on_timeline
                                meta["slotTime"] = slotTime
                                meta["slotTime_rm"] = rm_now
                            else:
                                ctc_synced = False   # czas z cache, CTC tego OB nie widzial

                        if "uobi" not in ob.keys():  # nadaje uobi jak nie ma
                            ob["uobi"] = str(uuid.uuid4())[:8]
                        if "ra" in ob.keys():  # liczy aktualna wysokosc na horyzontem
                            az, alt = RaDec2AltAz(self.observatory, now, ob["ra"], ob["dec"])
                            meta["alt"] = f"{deg_to_decimal_deg(str(alt)):.1f}"
                            meta["az"] = f"{deg_to_decimal_deg(str(az)):.1f}"

                        # planowany start i wysokosc
                        if scheduled:
                            meta["plan_ut"] = str(ephem.Date(ob_time))
                            if "ra" in ob.keys():
                                az, alt = RaDec2AltAz(self.observatory, ob_time, ob["ra"], ob["dec"])
                                meta["plan_alt"] = f"{deg_to_decimal_deg(str(alt)):.1f}"
                                meta["plan_az"] = f"{deg_to_decimal_deg(str(az)):.1f}"

                            # pominiete OB nie zajmuja czasu
                            if not skipped and meta.get("slotTime"):
                                ob_time = ob_time + ephem.second * meta["slotTime"]
                                if running and ob_time < now:   # biezacy OB przeciagnal sie
                                    ob_time = now
                                    ctc_synced = False



                try:
                    s = self.nats_toi_plan_status[tel]
                    status = {"current_i":self.current_i[tel],"next_i":self.next_i[tel],"plan":self.plan[tel]}
                    await s.publish(data=status,timeout=10)
                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 15: {e}')

                self.planGui.update_table()

    @staticmethod
    def _ob_skipped(meta):
        # OB ktore planrunner przeskakuje (check_next_i) - nie zajmuja czasu w planie
        return bool(meta.get("skip")) or bool(meta.get("skip_alt")) or ("ok" in meta and not meta["ok"])

    def check_next_i(self,tel):
        # przesuwa next_i za pominiete OB, -1 jak nic nie zostalo
        while -1 < self.next_i[tel] < len(self.plan[tel]):
            if self._ob_skipped(self.plan[tel][self.next_i[tel]]["meta"]):
                self.next_i[tel] = self.next_i[tel] + 1
            else:
                return
        self.next_i[tel] = -1

    ####################### focus window ##############################

    @qs.asyncSlot()
    async def focus_recalc(self):
        # tylko przelicza i publikuje wynik - focus ustawia dopiero SET (focus_set_result)
        if self.tel_acces[self.active_tel]:

            self.focus_method = self.focusGui.method_s.currentText()
            result = Focus.calculate(fits_path=self.local_cfg[self.active_tel]["tel_directory"] + "focus/actual",
                                     method=self.focus_method)

            if result is None:
                await self.update_log(f'focus recalculation ({self.focus_method}) FAILED', "WARNING", self.active_tel)

            else:

                max_sharpness_focus, calc_metadata = result

                try:
                    data = {}
                    data["time"] = self.ut
                    data["coef"] = list(calc_metadata["coef"])
                    data["focus_values"] = list(calc_metadata["focus_values"])
                    data["sharpness_values"] = list(calc_metadata["sharpness_values"])
                    data["max_sharpness_focus"] = float(max_sharpness_focus)
                    data["fit_x"] = list(calc_metadata["fit_x"])
                    data["fit_y"] = list(calc_metadata["fit_y"])
                    data["status"] = str(calc_metadata["status"])
                    data["davis_temperature"] = self.telemetry_temp
                    data["davis_humidity"] = self.telemetry_humidity
                    data["method"] = self.focus_method
                    try:
                        data["temperature"] = self.sensors[self.active_tel]["dome_conditions"]["temperature"]
                    except Exception:
                        data["temperature"] = "--"
                    # te same klatki co w ostatnim przebiegu, wiec i ten sam filtr (kolo moglo sie juz przestawic)
                    data["filter"] = self.nats_focus_status.get("filter", "--")

                    await self.nats_toi_focus_status[self.active_tel].publish(data=data, timeout=10)
                    await self.update_log(f'focus recalculated ({self.focus_method}): {int(max_sharpness_focus)} '
                                          f'{data["status"]}', "TOI RESPONDER", self.active_tel)

                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 67: {e}')

        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def focus_set_result(self):
        await self.update_log(f'SET autofocus result', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            status = self.focusGui.status
            if status.get("status") == "ok" and status.get("max_sharpness_focus") is not None:
                pos = int(status["max_sharpness_focus"])
                await self.focus_move(self.active_tel, pos, "autofocus_set")
                await self.update_log(f'focus set to {pos}', "TOI RESPONDER", self.active_tel)
                record = {k: status.get(k) for k in ("status", "temperature", "max_sharpness_focus", "time", "filter",
                                                     "davis_temperature", "davis_humidity", "method")}
                try:
                    await self.nats_toi_focus_record[self.active_tel].publish(data=record, timeout=10)
                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 67a: {e}')
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    def update_focus_window(self):
        try:
            self.focusGui.show_status(self.nats_focus_status)
        except Exception as e:
            logger.warning(f'EXCEPTION 45: {e}')

    # ############ CCD ##################################


    async def ccd_imageready(self,event):
        if self.ccd.imageready:
            self.flag_newimage = True

    @qs.asyncSlot()
    async def update_fits_data(self):
        self.fitsGui.update_fits_data()
        pass


    @qs.asyncSlot()
    async def new_fits(self):
        # plik czytany w watku: z NFS trwa (jk15 67 MB - sekundy), GUI na to nie czeka. Gdy w tym czasie przyjdzie
        # nowsze zdjecie albo zmieni sie teleskop, ten wynik jest wyrzucany (fitsGui.load_token)
        self.fitsGui.load_token += 1
        token, tel = self.fitsGui.load_token, self.active_tel
        path = self.cfg_tel_directory + "last_shoot.fits"
        if Path(path).is_file():
            path = os.path.realpath(path)       # last_shoot.fits to link - przestawia sie na kolejne zdjecie
            try:
                image, display, factor = await asyncio.to_thread(read_fits_image, path, fits_display_mode())
            except Exception as e:
                logger.warning(f'TOI: cannot read {path}: {e!r}')
                return
        else:
            logger.warning(f'Attepmt to download image directly, no {self.cfg_tel_directory}')
            image, display, factor = numpy.zeros((100, 100)), None, 1
        if token != self.fitsGui.load_token or tel != self.active_tel:
            return
        self.image = image
        self.fitsGui.updateImage(image, display, factor, name=os.path.basename(path))

    @qs.asyncSlot()
    async def ccd_Snap(self):
        await self.update_log(f'SNAP', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            ok_ndit = False
            ok_exp = False
            ok_seq = False
            seq = ""
            name=self.instGui.ccd_tab.inst_object_e.text().strip()
            if len(name)>0:
                ok_name=True
                theme.paint(self.instGui.ccd_tab.inst_object_e, bg="input_bg")
            else:
                ok_name=False
                await self.update_log(f'OBJECT NAME required', "WARNING", self.active_tel)
                theme.paint(self.instGui.ccd_tab.inst_object_e, bg="warn2_bg")

            exp=self.instGui.ccd_tab.inst_Dit_e.text()
            ndit=self.instGui.ccd_tab.inst_Ndit_e.text()
            # Sprawdzanie formatu czasu etc.
            try:
                exp=float(exp)
                if exp>=0:
                    ok_exp=True
                    theme.paint(self.instGui.ccd_tab.inst_Dit_e, bg="input_bg")
            except Exception:
                ok_exp=False
                await self.update_log(f'wrong EXP format', "WARNING", self.active_tel)
                theme.paint(self.instGui.ccd_tab.inst_Dit_e, bg="warn2_bg")
            try:
                if len(ndit)==0:
                    self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                    ndit=1
                ndit=int(ndit)
                if ndit>0:
                    ok_ndit=True
                    theme.paint(self.instGui.ccd_tab.inst_Ndit_e, bg="input_bg")
            except Exception:
                ok_exp=False
                await self.update_log(f'wrong N format', "WARNING", self.active_tel)
                theme.paint(self.instGui.ccd_tab.inst_Ndit_e, bg="warn2_bg")
            if ok_exp and ok_ndit:
                seq = "1/"+str(self.curent_filter)+"/"+str(exp)
                ok_seq = True

            if ok_name and ok_seq:
                uobi = str(uuid.uuid4())[:8]
                self.ob[self.active_tel]["block"] = f"SNAP {name} seq={seq}{await self.manual_dome_follow()} uobi={uobi}"
                self.ob[self.active_tel]["meta"]["origin"] = "snap"
                self.planrunner_start(self.active_tel)
                await self.update_log(f'starting planrunner', "TOI RESPONDER", self.active_tel)


        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_startExp(self):
        await self.update_log(f'exposure START', "OPERATOR", self.active_tel)

        if self.tel_acces[self.active_tel]:

            ok_ndit = False
            ok_exp = False
            ok_seq = False
            ok = True
            seq = ""

            name=self.instGui.ccd_tab.inst_object_e.text().strip()

            if len(name)>0:
                ok_name=True
                theme.paint(self.instGui.ccd_tab.inst_object_e, bg="input_bg")
            else:
                ok_name=False
                await self.update_log(f'OBJECT NAME required', "WARNING", self.active_tel)
                theme.paint(self.instGui.ccd_tab.inst_object_e, bg="warn2_bg")

            if self.instGui.ccd_tab.Select1_r.isChecked():
                exp=self.instGui.ccd_tab.inst_Dit_e.text()
                ndit=self.instGui.ccd_tab.inst_Ndit_e.text()

                # Sprawdzanie formatu czasu etc.
                try:
                    exp=float(exp)
                    if exp>-0.0001:
                        ok_exp=True
                        theme.paint(self.instGui.ccd_tab.inst_Dit_e, bg="input_bg")
                except Exception:
                    ok_exp=False
                    await self.update_log(f'wrong EXP TIME format', "WARNING", self.active_tel)
                    theme.paint(self.instGui.ccd_tab.inst_Dit_e, bg="warn2_bg")

                try:
                    if len(ndit)==0:
                        self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                        ndit=1
                    ndit=int(ndit)
                    if ndit>0:
                        ok_ndit=True
                        theme.paint(self.instGui.ccd_tab.inst_Ndit_e, bg="input_bg")
                except Exception:
                    ok_exp=False
                    await self.update_log(f'wrong N format', "WARNING", self.active_tel)
                    theme.paint(self.instGui.ccd_tab.inst_Ndit_e, bg="warn2_bg")

                if ok_exp and ok_ndit:
                    seq = str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                    ok_seq = True

            if self.instGui.ccd_tab.Select2_r.isChecked():
                seq = self.instGui.ccd_tab.inst_Seq_e.text().strip()

                ok_seq,err = seq_verification(seq,self.filter_list)
                if not ok_seq:
                    await self.update_log(f'wrong SEQ format {err} ', "WARNING", self.active_tel)
                    theme.paint(self.instGui.ccd_tab.inst_Seq_e, bg="warn2_bg")
                else:
                    theme.paint(self.instGui.ccd_tab.inst_Seq_e, bg="input_bg")

            if ok_name and ok_seq:

                if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==0:
                    txt = f"OBJECT {name} seq={seq}{await self.manual_dome_follow()} "

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
                    txt = f"DARK {name} seq={seq} "

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==1:
                    txt=f"ZERO {name} seq={seq}  "

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==3:
                    txt = f"SKYFLAT {name} seq={seq}   "
                    if self.mount_motortatus: pass
                    else:
                        ok = False
                        await self.update_log(f'Motors should be ON for SKYFLAT', "WARNING", self.active_tel)
                        self.WarningWindow("WARNING: Motors should be ON for SKYFLAT")

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==4:
                    txt=f"DOMEFLAT {name} seq={seq}  "
                    if self.mount_motortatus: pass
                    else:
                        ok = False
                        await self.update_log(f'Motors should be ON for DOMEFLAT', "WARNING", self.active_tel)
                        self.WarningWindow("WARNING: Motors should be ON for DOMEFLAT")

                else:
                    await self.update_log(f'not implemented yet', "WARNING", self.active_tel)

            if ok:

                if self.instGui.ccd_tab.test_c.isChecked():
                    txt = txt + " test=1"

                self.ob[self.active_tel]["block"] = txt
                self.ob[self.active_tel]["meta"]["origin"] = "manual"
                self.planrunner_start(self.active_tel)
                await self.update_log(f'starting planrunner', "TOI RESPONDER", self.active_tel)

        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_stopExp(self):
        await self.update_log(f'exposure STOP', "OPERATOR", self.active_tel)

        await self.takeControl()
        self.ob_progress[self.active_tel]["dit_start"]=0

        try:
            data = self.ob_progress[self.active_tel]
            await self.nats_toi_ob_status[self.active_tel].publish(data=data, timeout=10)
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 40: {e}')

        self.ob[self.active_tel]["meta"]["run"]=False
        try:
            await self.planrunners[self.active_tel].astop_nightplan()
            await self.update_log(f'stopping program', "TOI RESPONDER", self.active_tel)
        except Exception:
            pass
        await self.ccd.aput_stopexposure()
        await self.update_log(f'stopping exposure', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def ccd_setBin(self):
        await self.update_log(f'set BIN XY', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if self.instGui.ccd_tab.inst_Bin_s.currentIndex()==0: x,y=1,1
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==1: x,y=2,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==2: x,y=1,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==3: x,y=2,1
            else:
                await self.update_log(f'not a valid BIN option', "WARNING", self.active_tel)
                return

            # binning nieznany (zaraz po starcie / zmianie teleskopu) - int(None) przerywal przed wyslaniem do kamery
            if self.ccd_binx is None or self.ccd_biny is None or int(self.ccd_binx) != int(x) or int(self.ccd_biny) != int(y):
                theme.paint(self.instGui.ccd_tab.inst_Bin_e, bg="moving_bg")
            await self.ccd.aput_binx(int(x))
            await self.ccd.aput_biny(int(y))
            await self.update_log(f'setting bin xy {x} {y}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setGain(self):
        await self.update_log(f'set GAIN', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            i = self.instGui.ccd_tab.inst_setGain_e.currentIndex()
            gain = self.instGui.ccd_tab.gain_ids[i]
            if int(self.ccd_gain) != int(gain):
                theme.paint(self.instGui.ccd_tab.inst_gain_e, bg="moving_bg")
            await self.ccd.aput_gain(int(gain))
            await self.update_log(f'setting gain {gain}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setReadMode(self):
        await self.update_log(f'set READ MODE', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           i = int(self.instGui.ccd_tab.inst_setRead_e.currentIndex())
           rm = self.instGui.ccd_tab.rm_ids[i]
           await self.ccd.aput_readoutmode(rm)
           await self.update_log(f'setting read mode {rm}', "TOI RESPONDER", self.active_tel)
           if int(self.ccd_readoutmode) != int(rm):
               theme.paint(self.instGui.ccd_tab.inst_read_e, bg="moving_bg")
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    @qs.asyncSlot()
    async def ccd_setTemp(self):
        await self.update_log(f'set CCD temperature', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            temp=float(self.instGui.ccd_tab.inst_setTemp_e.text())
            t_min, t_max = self.instGui.ccd_tab.temp_limits     # temperature_range kamery z konfiguracji
            if t_min <= temp <= t_max:
                await self.ccd.aput_setccdtemperature(temp)
                await self.update_log(f'setting CCD temperature {temp}', "TOI RESPONDER", self.active_tel)
            else:
                await self.update_log(f'Value of CCD temp. not allowed ({t_min} .. {t_max})', "WARNING", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_coolerOnOf(self):
        tel = self.active_tel
        cam = self.instGui.ccd_tab
        cooler_on = bool(self.ccd.cooleron)         # stan kamery, nie polozenie przelacznika
        await self.update_log(f'ccd cooler {"OFF" if cooler_on else "ON"}', "OPERATOR", tel)
        if not self.tel_acces[tel]:
            self.WarningWindow("WARNING: U don't have control")
            cam.cooler_c.setChecked(cooler_on)       # przelacznik wraca do stanu kamery
            return
        await self.ccd.aput_cooleron(not cooler_on)
        await self.update_log(f'setting cooler {"OFF" if cooler_on else "ON"}', "TOI RESPONDER", tel)

    async def ccd_cooler_update(self, event):
        self.ccd_cooler = await self.delivered(event, self.ccd.aget_cooleron)
        if self.ccd_cooler != None:
            self.instGui.ccd_tab.cooler_c.setChecked(self.ccd_cooler)

    async def ccd_current_temp_update(self, event):
        self.ccd_temp = await self.delivered(event, self.ccd.aget_ccdtemperature)
        await self.ccd_temp_update()

    async def ccd_set_temp_update(self, event):
        self.ccd_temp_set = await self.delivered(event, self.ccd.aget_setccdtemperature)
        await self.ccd_temp_update()

    async def ccd_temp_update(self):
        # is not None: 0.0 C to tez temperatura (CMOS ustawiane na 0)
        if self.ccd_temp is not None and self.ccd_temp_set is not None:
            ccd_temp=self.ccd_temp
            txt = f" {ccd_temp:.1f} / {self.ccd_temp_set:.1f}"
            self.instGui.ccd_tab.inst_ccdTemp_e.setText(txt)
            if float(ccd_temp) > self.instGui.ccd_tab.defaults["temp"]:      # za cieplo - czerwony
                theme.paint(self.instGui.ccd_tab.inst_ccdTemp_e, fg="bad_fg", bg="field_bg")
            else:
                theme.paint(self.instGui.ccd_tab.inst_ccdTemp_e, fg="ok_fg", bg="field_bg")


    async def ccd_gain_update(self, event):
        self.ccd_gain = await self.delivered(event, self.ccd.aget_gain)     # dawniej pobierany dwa razy
        if self.ccd_gain != None:
            try:
                i = int(self.ccd_gain)
                cam = self.instGui.ccd_tab
                txt = cam.gain_names[cam.gain_ids.index(str(i))]
                cam.inst_gain_e.setText(txt)
                if cam.defaults["gain"] in (None, txt):
                    theme.paint(self.instGui.ccd_tab.inst_gain_e, bg="field_bg")
                else: theme.paint(self.instGui.ccd_tab.inst_gain_e, bg="warn_soft_bg")
            except Exception: pass
        self.telescope_switch_status["gain"] = True

    def readout_mode(self, tel):
        """Tryb odczytu kamery teleskopu `tel`. self.ccd_readoutmode to kamera AKTYWNEGO teleskopu - plan
        innego teleskopu liczony z nim dostawal cudzy tryb (zb08 z trybem 3 jk15 = 0.05 MHz, sloty x10)."""
        rm = self.readoutmode_tel.get(tel)
        return rm if rm is not None else getattr(self, "ccd_readoutmode", None)

    async def ccd_rm_update(self, event):
        self.ccd_readoutmode = await self.delivered(event, self.ccd.aget_readoutmode)
        if self.ccd_readoutmode is not None:
            self.readoutmode_tel[self.component_tel] = int(self.ccd_readoutmode)
        # READ MODES

        if self.ccd_readoutmode != None:
            cam = self.instGui.ccd_tab
            rm_id = str(int(self.ccd_readoutmode))
            if rm_id in cam.rm_ids:
                txt = cam.rm_names[cam.rm_ids.index(rm_id)]
            else:       # tryb spoza konfiguracji kamery - numer i zolte tlo
                txt = f"#{rm_id}"
                logger.warning(f'TOI: read mode {rm_id} of {self.component_tel} not in the camera configuration')
            cam.inst_read_e.setText(txt)
            if cam.defaults["rm"] in (None, txt) and not txt.startswith("#"):
                theme.paint(self.instGui.ccd_tab.inst_read_e, bg="field_bg")
            else: theme.paint(self.instGui.ccd_tab.inst_read_e, bg="warn_soft_bg")
        self.telescope_switch_status["rm"] = True


    async def ccd_binx_update(self, event):
        self.ccd_binx = await self.delivered(event, self.ccd.aget_binx)
        await self.ccd_bin_update()

    async def ccd_biny_update(self, event):
        self.ccd_biny = await self.delivered(event, self.ccd.aget_biny)
        await self.ccd_bin_update()

    async def ccd_bin_update(self):
        if self.ccd_binx and self.ccd_biny:
            txt=f"{self.ccd_binx}x{self.ccd_biny}"
            self.instGui.ccd_tab.inst_Bin_e.setText(txt)
            if txt == self.instGui.ccd_tab.defaults["bin"]:
                theme.paint(self.instGui.ccd_tab.inst_Bin_e, bg="field_bg")
            else: theme.paint(self.instGui.ccd_tab.inst_Bin_e, bg="warn_soft_bg")

    async def ccd_update(self, event):
        self.ccd_state = await self.delivered(event, self.ccd.aget_camerastate)

    async def ccd_con_update(self, event):
        self.inst_con = self.ccd.connected


    # ############ MOUNT ##################################

    async def mount_con_update(self, event):
        self.mount_con =self.mount.connected

    @qs.asyncSlot()
    async def safety_switch_OnOff(self):
        if self.tel_acces[self.active_tel]:
            await self.update_log(f'Safety cutoff ON/OFF', "OPERATOR", self.active_tel)
            status = None
            r = await self.user.aget_safety_cutoff_state()
            try:
                status = bool(r["engaged"])
            except Exception as e:
                logger.warning(f'TOI EXCEPTION: safetySwitch_update: {e}')
                status = None

            if status != None:
                if status:
                    await self.user.aput_disengage_safety_cutoff()
                    await self.update_log(f'setting safety cutoff OFF', "TOI RESPONDER", self.active_tel)
                else:
                    await self.user.aput_engage_safety_cutoff()
                    await self.update_log(f'setting safety cutoff ON', "TOI RESPONDER", self.active_tel)
        else:
            await self.safetySwitch_update(None)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    async def safetySwitch_update(self,event):
        status = None
        r = await self.user.aget_safety_cutoff_state()
        try:
            status = bool(r["engaged"])
        except Exception as e:
            logger.warning(f'TOI EXCEPTION: safetySwitch_update: {e}')
            status = None

        if status == None:
            self.mntGui.SafetySwitch_l.setText("SAFETY CUTOFF ERROR")
            theme.paint(self.mntGui.SafetySwitch_l, fg="bad_fg", extra="font-weight: bold;")
        elif status == False:
            self.mntGui.SafetySwitch_l.setText("SAFETY CUTOFF OFF")
            self.mntGui.SafetySwitch_c.setChecked(False)
            theme.paint(self.mntGui.SafetySwitch_l, fg="text", extra="font-weight: normal;")
        elif status == True:
            self.mntGui.SafetySwitch_l.setText("SAFETY CUTOFF ON")
            self.mntGui.SafetySwitch_c.setChecked(True)
            theme.paint(self.mntGui.SafetySwitch_l, fg="warn2_fg", extra="font-weight: bold;")



    @qs.asyncSlot()
    async def mount_motorsOnOff(self):
        await self.update_log(f'mount motors ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False
           if self.mount_motortatus:
              await self.mount.aput_motoroff()
              await self.update_log(f'setting motors OFF', "TOI RESPONDER", self.active_tel)

           else:
               await self.mount.aput_motoron()
               await self.update_log(f'setting motors ON', "TOI RESPONDER", self.active_tel)

        else:
            await self.mountMotors_update(None)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def mountMotors_update(self,event):
           r = await self.delivered(event, self.mount.aget_motorstatus)
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False

           if self.mount_motortatus:
               self.mntGui.mntMotors_c.setChecked(True)
           else:
               self.mntGui.mntMotors_c.setChecked(False)
           await self.mount_update()


    @qs.asyncSlot()
    async def covers_openOrClose(self):
        await self.update_log(f'mirror covers ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           try:
               self.cover_status = await self.read_for_action(self.cover.aget_coverstate, "mirror covers state")
           except LookupError:
               return
           if self.cover_status is None:
               self.WarningWindow("WARNING: Mirror covers state unknown (no fresh data) - refusing to act")
               return
           if self.cover_status==1:
              await self.cover.aput_opencover()
              await self.update_log(f'setting mirror covers OPEN', "TOI RESPONDER", self.active_tel)

           else:
               await self.cover.aput_closecover()
               await self.update_log(f'setting mirror covers CLOSE', "TOI RESPONDER", self.active_tel)
        else:
            await self.covers_update(None)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def covers_update(self,event):
           self.cover_status = await self.delivered(event, self.cover.aget_coverstate)

           if self.cover_status==3:
               self.mntGui.telCovers_c.setChecked(True)
               txt="OPEN"
               theme.paint(self.mntGui.telCovers_e, fg="ok_fg", bg="field_bg")
           elif self.cover_status==1:
               self.mntGui.telCovers_c.setChecked(False)
               txt="CLOSED"
               theme.paint(self.mntGui.telCovers_e, bg="field_bg")
           elif self.cover_status==2:
               txt="MOVING"
               theme.paint(self.mntGui.telCovers_e, fg="moving_fg", bg="field_bg")
           else:
               txt="UNKNOWN"
               theme.paint(self.mntGui.telCovers_e, fg="bad_fg", bg="field_bg")

           self.mntGui.telCovers_e.setText(txt)
           if self.skyGui.skyView:
               self.skyGui.skyView.updateMount()

    @qs.asyncSlot()
    async def park_mount(self):
        await self.update_log(f'mount PARK', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            try:
                motors = await self.read_for_action(self.mount.aget_motorstatus, "mount motor status")
            except LookupError:
                return
            if motors == "true":
                theme.paint(self.mntGui.mntStat_e, fg="bad_fg", bg="field_bg", extra=self.mntGui.STAT_STYLE)
                await self.dome.aput_dome_follower_off()
                await self.mount.aput_park()
                await self.dome.aput_slewtoazimuth(180.)
                await self.update_log(f'parking', "TOI RESPONDER", self.active_tel)
            else:
                self.WarningWindow("WARNING: Mount motor status unknown or motors OFF - refusing to act")
                await self.update_log('mount motor status unknown or motors OFF - refusing to act', "WARNING", self.active_tel)


        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def abort_slew(self):
        await self.update_log(f'mount slew ABORT', "OPERATOR", self.active_tel)
        await self.takeControl()
        await self.mount.aput_abortslew()
        await self.mount.aput_tracking(False)
        await self.update_log(f'aborting mount slew', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def mount_slew(self):
        await self.update_log(f'mount SLEW', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            try:
                motors = await self.read_for_action(self.mount.aget_motorstatus, "mount motor status")
            except LookupError:
                return
            if motors == "true":
                self.req_ra=""
                self.req_dec=""
                self.req_epoch=""
                if self.nextOB_ok:
                    await self.mount.aput_unpark()

                    if self.mntGui.setAltAz_r.isChecked():
                       az=float(self.mntGui.nextAz_e.text().strip())
                       alt=float(self.mntGui.nextAlt_e.text().strip())
                       await self.mount.aput_slewtoaltaz_async(az,alt)
                       await self.update_log(f'slewing to alt az {alt} {az}', "TOI RESPONDER", self.active_tel)

                    elif self.mntGui.setEq_r.isChecked():
                       ra = self.mntGui.nextRa_e.text().strip()
                       dec = self.mntGui.nextDec_e.text().strip()
                       epoch = str(self.mntGui.mntEpoch_e.text())
                       self.req_ra=ra
                       self.req_dec=dec
                       self.req_epoch=epoch
                       ra=ra_to_decimal(ra)
                       dec=dec_to_decimal(dec)
                       ra,dec = ra_dec_epoch(ra,dec,epoch)

                       await self.mount.aput_slewtocoo_async(ra, dec)
                       await self.update_log(f'slewing to ra dec {ra} {dec}', "TOI RESPONDER", self.active_tel)

                    az=float(self.mntGui.nextAz_e.text())
                    ## mikolaj - disable TOI auto dome slew logic (dome-follower takes)
                    #             dome_eq_az, info_dict = dome_eq_azimuth(
                    #                 ra=self.mount_ra, dec=self.mount_dec, r_dome=2050, spx=-110, spy=-110,
                    #                 gem=670, side_of_pier=side_of_pier, latitude=-24.598056,
                    #                 longitude=-70.196389, elevation=2817
                    #             )
                else:
                    await self.update_log(f'SLEW not allowed', "WARNING", self.active_tel)
            else:
                self.WarningWindow("WARNING: Mount motor status unknown or motors OFF - refusing to act")
                await self.update_log('mount motor status unknown or motors OFF - refusing to act', "WARNING", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def mount_trackOnOff(self):
        await self.update_log(f'mount tracking ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if await self.mount.aget_motorstatus() != "false":
                self.mount_tracking = await self.mount.aget_tracking()     # akcja przycisku - swiezy odczyt z serwera

                if self.mount_tracking:
                   await self.mount.aput_tracking(False)
                   await self.update_log(f'stopping tracking', "TOI RESPONDER", self.active_tel)
                else:
                   await self.mount.aput_tracking(True)
                   await self.update_log(f'starting tracking', "TOI RESPONDER", self.active_tel)

            else:
                await self.mount_update()
                txt = "WARNING: Motors are OFF"
                self.WarningWindow(txt)
                await self.update_log(f'Motors are OFF', "WARNING", self.active_tel)


        else:
            await self.mount_update()
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def mount_tracking_update(self, event):
        self.mount_tracking = await self.delivered(event, self.mount.aget_tracking)
        await self.mount_update()

    async def mount_slewing_update(self, event):
        self.mount_slewing = await self.delivered(event, self.mount.aget_slewing)
        await self.mount_update()

    async def mount_update(self):
        if not self.mount_motortatus:
            txt = "MOTORS OFF"
            theme.paint(self.mntGui.mntStat_e, bg="field_bg", extra=self.mntGui.STAT_STYLE)
        elif self.mount_slewing and self.mount_tracking:
            txt="SLEWING, TRACKING"
            theme.paint(self.mntGui.mntStat_e, fg="moving_fg", bg="field_bg", extra=self.mntGui.STAT_STYLE)
            self.mntGui.tracking_c.setChecked(True)
        elif self.mount_slewing:
            txt="SLEWING"
            theme.paint(self.mntGui.mntStat_e, fg="moving_fg", bg="field_bg", extra=self.mntGui.STAT_STYLE)
        elif self.mount_tracking:
            txt="TRACKING"
            theme.paint(self.mntGui.mntStat_e, fg="ok_fg", bg="field_bg", extra=self.mntGui.STAT_STYLE)
            self.mntGui.tracking_c.setChecked(True)
        else:
            txt="IDLE"
            theme.paint(self.mntGui.mntStat_e, bg="field_bg", extra=self.mntGui.STAT_STYLE)
            self.mntGui.tracking_c.setChecked(False)
        self.mntGui.mntStat_e.setText(txt)
        if self.skyGui.skyView:
            self.skyGui.skyView.updateMount()

        if self.mount_slewing:
            theme.paint(self.mntGui.mntAz_e, bg="moving_bg")
            theme.paint(self.mntGui.mntAlt_e, bg="moving_bg")
            theme.paint(self.mntGui.mntRa_e, bg="moving_bg")
            theme.paint(self.mntGui.mntDec_e, bg="moving_bg")
            self.guider_passive_dx=[]
            self.guider_passive_dy=[]
        else:
            theme.paint(self.mntGui.mntAz_e, bg="field_bg")
            theme.paint(self.mntGui.mntAlt_e, bg="field_bg")
            theme.paint(self.mntGui.mntRa_e, bg="field_bg")
            theme.paint(self.mntGui.mntDec_e, bg="field_bg")

    async def ra_update(self, event):
        self.mount_ra = await self.delivered(event, self.mount.aget_ra)
        await self.radec_update()

    async def dec_update(self, event):
        self.mount_dec = await self.delivered(event, self.mount.aget_dec)
        await self.radec_update()

    async def alt_update(self, event):
        self.mount_alt = await self.delivered(event, self.mount.aget_alt)
        await self.radec_update()

    async def az_update(self, event):
        self.mount_az = await self.delivered(event, self.mount.aget_az)
        await self.radec_update()


    async def radec_update(self):
        if  self.mount_ra and self.mount_dec:
            self.mntGui.mntRa_e.setText(to_hourangle_sexagesimal(self.mount_ra))
            self.mntGui.mntDec_e.setText(dec_to_sexagesimal(self.mount_dec))
        if self.mount_alt and self.mount_az:
           self.mntGui.mntAlt_e.setText(f"{self.mount_alt:.3f}")
           self.mntGui.mntAz_e.setText(f"{self.mount_az:.3f}")
           if self.skyGui.skyView:
               self.skyGui.skyView.updateMount()
           airmass = calc_airmass(float(self.mount_alt))
           if airmass:
               self.mntGui.mntAirmass_e.setText("%.1f" % airmass)
           else:
               self.mntGui.mntAirmass_e.setText("")

    def target_changed(self):
        theme.paint(self.mntGui.target_e, bg="input_edit_bg")
    _ob_validator = None    # walidator OB dla pola SEARCH (schematy wczytane raz)

    def target_provided(self):
        # zwykly slot Qt (editingFinished): wyjatek stad zamknalby cale TOI
        target = self.mntGui.target_e.text()
        try:
            if TOI._ob_validator is None:
                TOI._ob_validator = ObsValidator(ObsValidator.load_schema("base_schema"),
                                                 ObsValidator.load_schema("base_rules.yaml"))
            result = TOI._ob_validator.validate_txt(
                target, allowed_filters=self.nats_cfg[self.active_tel]["filter_list_names"])
            if result["result"]:
                ob = result["data"]
                if "ra" in ob.keys():
                    self.mntGui.nextRa_e.setText(ob["ra"])
                if "dec" in ob.keys():
                    self.mntGui.nextDec_e.setText(ob["dec"])
                if "name" in ob.keys():
                    self.instGui.ccd_tab.inst_object_e.setText(ob["name"])
                if "seq" in ob.keys():
                    self.instGui.ccd_tab.inst_Seq_e.setText(ob["seq"])
                self.mntGui.setEq_r.setChecked(True)
                self.mntGui.updateNextRaDec()
        except Exception as e:
            logger.warning(f'TOI: SEARCH "{target}": {e!r}')
            theme.paint(self.mntGui.target_e, bg="warn2_bg")
            return
        theme.paint(self.mntGui.target_e, bg="input_bg")

    @qs.asyncSlot()
    async def pulse_up(self):
        if self.tel_acces[self.active_tel]:
            arcsec = self.mntGui.pulse_window.pulseDec_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(0,sec)
            self.pulseDec = self.pulseDec + float(arcsec)
            self.mntGui.pulse_window.sumDec_e.setText(str(self.pulseDec))
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_down(self):
        if self.tel_acces[self.active_tel]:
            arcsec = self.mntGui.pulse_window.pulseDec_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(1,sec)
            self.pulseDec = self.pulseDec - float(arcsec)
            self.mntGui.pulse_window.sumDec_e.setText(str(self.pulseDec))
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_left(self):
        if self.tel_acces[self.active_tel]:
            arcsec = self.mntGui.pulse_window.pulseRa_e.text()
            sec = 1000 * (float(arcsec)/6  )
            sec = int(sec)
            await self.mount.aput_pulseguide(2,sec)
            self.pulseRa = self.pulseRa + float(arcsec)
            self.mntGui.pulse_window.sumRa_e.setText(str(self.pulseRa))
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_right(self):
        if self.tel_acces[self.active_tel]:
            arcsec = self.mntGui.pulse_window.pulseRa_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(3,sec)
            self.pulseRa = self.pulseRa - float(arcsec)
            self.mntGui.pulse_window.sumRa_e.setText(str(self.pulseRa))
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def rotator_minus(self):
        if self.tel_acces[self.active_tel]:
            try:
                step = -1*float(self.mntGui.pulse_window.rotstep_e.text())
                await self.rotator.aput_move(step)
            except:
                pass
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def rotator_plus(self):
        if self.tel_acces[self.active_tel]:
            try:
                step = float(self.mntGui.pulse_window.rotstep_e.text())
                await self.rotator.aput_move(step)
            except:
                pass
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    # ################# DOME ########################

    async def dome_con_update(self, event):
        self.dome_con =self.dome.connected


    @qs.asyncSlot()
    async def dome_openOrClose(self):
        await self.update_log(f'dome OPEN/CLOSE', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           try:
               covers = await self.read_for_action(self.cover.aget_coverstate, "mirror covers state")
               shutter = await self.read_for_action(self.dome.aget_shutterstatus, "dome shutter state")
           except LookupError:
               return
           if covers == 1:
               if shutter==0:
                  await self.dome.aput_closeshutter()
                  await self.update_log(f'closing dome', "TOI RESPONDER", self.active_tel)
               elif shutter==1:
                  await self.dome.aput_openshutter()
                  await self.update_log(f'opening dome', "TOI RESPONDER", self.active_tel)
               else:       # w ruchu (2, 3) albo nieznany - dawniej bez slowa
                   await self.update_log('dome shutter is moving or its state is unknown - nothing done', "WARNING",
                                         self.active_tel)
           else:
               await self.domeShutterStatus_update(False)
               txt = "WARNING: Mirror covers are open. Close MIRROR for dome shutter operations"
               self.WarningWindow(txt)
               await self.update_log(f'Mirror covers are open. Close MIRROR for dome shutter operations', "WARNING", self.active_tel)


        else:
            await self.domeShutterStatus_update(None)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_move2Az(self):
        await self.update_log(f'dome MOVE', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           if self.dome_next_az_ok:
               az = float(self.mntGui.domeNextAz_e.text())
               await self.dome.aput_slewtoazimuth(az)
               await self.update_log(f'moving dome to az {az}', "TOI RESPONDER", self.active_tel)
        else:
            await self.domeShutterStatus_update(False)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_stop(self):
        await self.update_log(f'dome STOP', "OPERATOR", self.active_tel)
        await self.takeControl()
        await self.dome.aput_abortslew()
        await self.update_log(f'stopping dome', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def domeFollow(self):
        await self.update_log(f'dome FOLLOW ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            self.dome_follow_busy = True   # w trakcie komendy subskrypcja przynosi jeszcze stary stan
            try:
                if self.dome_follow:
                    ok = await self.dome.aput_dome_follower_off()
                    await self.update_log(f'stopping dome follow', "TOI RESPONDER", self.active_tel)
                else:
                    ok = await self.dome.aput_dome_follower_on()
                    await self.update_log(f'starting dome follow', "TOI RESPONDER", self.active_tel)
            finally:
                self.dome_follow_busy = False
            if ok:
                # suwak zostaje w stanie po kliknieciu, subskrypcja go potwierdzi
                self.dome_follow = not self.dome_follow
            else:
                await self.update_log(f'dome follow request failed', "WARNING", self.active_tel)
                self.mntGui.domeAuto_c.setChecked(bool(self.dome_follow))
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            self.mntGui.domeAuto_c.setChecked(bool(self.dome_follow))

    async def manual_dome_follow(self):
        """dome_follow=off dla recznego OBJECT/SNAP z okna instrumentu tylko przy zamknietej kopule (albo nieznanym
        stanie): testy w dzien - kopula stoi (ludzie w kopule, kopula ustawiona recznie; nieudany obrot przerwalby
        program). Przy otwartej kopule jak w planie: planrunner ustawia kopule przed kazda ekspozycja, z dome followerem
        nie koliduje (ten sam azymut, w tolerancji pomija obrot), a gdy follower wylaczony (np. po PARK) - tylko on."""
        if self.dome_shutterstatus == 0:
            return ""
        return " dome_follow=off"

    async def dome_follower_reader(self):
        self.dome_follow = None
        self.mntGui.domeAuto_c.setChecked(False)
        self.mntGui.domeAuto_c.setEnabled(False)
        sub = await self.dome.asubscribe_dome_follower_status(self.dome_follower_status_update)
        try:
            await sub
        finally:
            sub.cancel()

    async def dome_follower_status_update(self, data, meta):
        if self.dome_follow_busy:
            return
        try:
            if data is not None and data['status'] == 'ok':
                self.dome_follow = data['follow_on']
            else:
                self.dome_follow = None
        except (LookupError, TypeError, ValueError):
            self.dome_follow = None
        self.mntGui.domeAuto_c.setChecked(bool(self.dome_follow))
        self.mntGui.domeAuto_c.setEnabled(self.dome_follow is not None)
        self.set_dome_follow_table({self.active_tel: self.dome_follow})     # FOLLOW w tabeli od razu

    async def domeShutterStatus_update(self, event):
           self.dome_shutterstatus = await self.delivered(event, self.dome.aget_shutterstatus)
           if self.dome_shutterstatus==0:
              txt="OPEN"
              theme.paint(self.mntGui.domeShutter_e, fg="ok_fg", bg="field_bg")
              self.mntGui.domeShutter_c.setChecked(True)

           elif self.dome_shutterstatus==1:
                txt="CLOSED"
                theme.paint(self.mntGui.domeShutter_e, bg="field_bg")
                self.mntGui.domeShutter_c.setChecked(False)

           elif self.dome_shutterstatus==2:
                txt="OPENING"
                theme.paint(self.mntGui.domeShutter_e, fg="moving_fg", bg="field_bg")


           elif self.dome_shutterstatus==3:
                txt="CLOSING"
                theme.paint(self.mntGui.domeShutter_e, fg="moving_fg", bg="field_bg")

           else:
                txt="UNKNOWN"
                theme.paint(self.mntGui.domeShutter_e, bg="field_bg")
           if self.skyGui.skyView:
               self.skyGui.skyView.updateDome()
           self.mntGui.domeShutter_e.setText(txt)

    async def domeStatus_update(self, event):
        self.dome_status = await self.delivered(event, self.dome.aget_slewing)
        if self.dome_status==False:
            txt="STOPPED"
            theme.paint(self.mntGui.domeStat_e, bg="field_bg")
            theme.paint(self.mntGui.domeAz_e, bg="field_bg")
        elif self.dome_status==True:
            txt="MOVING"
            theme.paint(self.mntGui.domeStat_e, fg="moving_fg", bg="field_bg")
            theme.paint(self.mntGui.domeAz_e, bg="moving_bg")

        else: txt="UNKNOWN"
        self.mntGui.domeStat_e.setText(txt)

    async def domeAZ_update(self, event):
        self.dome_az = await self.delivered(event, self.dome.aget_az)
        if self.dome_az:
            self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
            if self.skyGui.skyView:
                self.skyGui.skyView.updateDome()

    def domeAZ_check(self, event):
        self.dome_next_az_ok = False
        dome_next_az = self.mntGui.domeNextAz_e.text()
        try:
            dome_next_az = float(dome_next_az)
            if dome_next_az <= 360. and dome_next_az >= 0:
                self.dome_next_az_ok = True
        except ValueError:
            self.dome_next_az_ok = False
        if dome_next_az == None or dome_next_az == "":
            self.dome_next_az_ok = None
        if self.dome_next_az_ok or self.dome_next_az_ok == None:
            theme.paint(self.mntGui.domeNextAz_e, bg="input_bg")
        else: theme.paint(self.mntGui.domeNextAz_e, bg="warn2_bg")


    @qs.asyncSlot()
    async def VentilatorsOnOff(self):
        await self.update_log(f'dome ventilators ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            r = await self.dome.aget_dome_fans_running()
            if r:
                self.dome_fanStatus=True
            else:
                self.dome_fanStatus=False

            if self.dome_fanStatus:
               await self.dome.aput_fans_turn_off()
               await self.update_log(f'turning ventilators OFF', "TOI RESPONDER", self.active_tel)
            else:
                await self.dome.aput_dome_fans_turn_on()
                await self.update_log(f'turning ventilators ON', "TOI RESPONDER", self.active_tel)

        else:
            await self.Ventilators_update(False)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def Ventilators_update(self,event):
        # his callback uses direct value gaet instead of asget,
        # this was intendent way. When its confirmed, that it works seamlessly,
        # other callbacks will be modified to use direct value get too.
        r = self.dome.domefansrunning

        if r is None:
            # no fresh data (Staleness Contract): render unknown, publish NOTHING
            self.mntGui.ventilators_e.setText("--")
            theme.paint(self.mntGui.ventilators_e, bg="field_bg")
            return
        self.dome_fanStatus = bool(r)
        self.mntGui.ventilators_c.setChecked(self.dome_fanStatus)
        txt = "ON" if self.dome_fanStatus else "OFF"
        tel = self.component_tel
        if self.tel_acces[tel]:
            await self.publish_op_state(tel, "dome_ventilators", self.dome_fanStatus)
        self.mntGui.ventilators_e.setText(txt)
        theme.paint(self.mntGui.ventilators_e, bg="field_bg")

    async def publish_op_state(self, tel, key, state):
        """Stan urzadzenia w tic.status.<tel>.toi.status. Publikujemy, gdy obserwowany stan rozni sie od tego NA NATS
        (porownanie z lokalna kopia, startujaca z domyslnych, zostawialo stary stan na zawsze - wk06 2026-10-27:
        wentylatory "wlaczone" od 05:11, choc wylaczone od 05:49). Pozostale pola z wersji na NATS - nie nadpisujemy
        stanow zapisanych przez inne TOI. Ponowne dostarczenie tej samej wartosci niczego nie wysyla."""
        self.toi_op_status[tel][key]["state"] = state
        on_nats = self.nats_toi_op_status.get(tel) or {}
        if on_nats.get(key, {}).get("state") == state:
            return
        data = copy.deepcopy(on_nats) if on_nats else copy.deepcopy(self.toi_op_status[tel])
        data[key] = copy.deepcopy(self.toi_op_status[tel][key])
        self.nats_toi_op_status[tel] = data         # zanim wroci z NATS - kolejne zdarzenie nie wysle tego samego
        await self.nats_pub_toi_status[tel].publish(data=data, timeout=10)

    # OTHER COMPONENTS

    @qs.asyncSlot()
    async def mirrorFansOnOff(self):
        await self.update_log(f'mirror fans ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           r = await self.focus.aget_fansstatus()
           self.mirror_fanStatus = (r == "True")
           if self.mirror_fanStatus:
              await self.focus.aput_fansturnoff()
              await self.update_log(f'turning mirror fans OFF', "TOI RESPONDER", self.active_tel)
           else:
               await self.focus.aput_fansturnon()
               await self.update_log(f'turning mirror fans ON', "TOI RESPONDER", self.active_tel)
        else:
            await self.mirrorFans_update(False)
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def mirrorFans_update(self,event):
           r = await self.delivered(event, self.focus.aget_fansstatus)
           if r is None:
               self.mntGui.mirrorFans_e.setText("--")
               theme.paint(self.mntGui.mirrorFans_e, bg="field_bg")
               return
           self.mirror_fanStatus = (r == "True")
           self.mntGui.mirrorFans_c.setChecked(self.mirror_fanStatus)
           txt = "FANS ON" if self.mirror_fanStatus else "FANS OFF"
           tel = self.component_tel
           if self.tel_acces[tel]:
               await self.publish_op_state(tel, "mirror_fans", self.mirror_fanStatus)
           self.mntGui.mirrorFans_e.setText(txt)
           theme.paint(self.mntGui.mirrorFans_e, bg="field_bg")


    @qs.asyncSlot()
    async def FlatLampOnOff(self):
        await self.update_log(f'flat lamps ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:

           if self.mntGui.flatLights_c.isChecked():
               await self.mount.aput_domelamp_on()
               await self.update_log(f'turning flat lamps ON', "TOI RESPONDER", self.active_tel)
               self.mntGui.flatLights_e.setText("no feedback")
               theme.paint(self.mntGui.flatLights_e, fg="moving_fg", bg="field_bg")
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status[self.active_tel]["flat_lamps"]["state"] = True
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status[self.active_tel], timeout=10)
           else:
               await self.mount.aput_domelamp_off()
               await self.update_log(f'turning flat lamps OFF', "TOI RESPONDER", self.active_tel)
               self.mntGui.flatLights_e.setText("")
               theme.paint(self.mntGui.flatLights_e, bg="field_bg")
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status[self.active_tel]["flat_lamps"]["state"] = False
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status[self.active_tel], timeout=10)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            if self.mntGui.flatLights_c.isChecked(): self.mntGui.flatLights_c.setChecked(False)
            else: self.mntGui.flatLights_c.setChecked(True)

    DOME_LIGHT_TIMEOUT = 3      # s - sterownik swiatel (Blebox rgbw) w sieci kopuly

    @qs.asyncSlot()
    async def domeLightOnOff(self):
        tel = self.active_tel
        on = self.mntGui.domeLights_c.isChecked()       # polozenie po kliknieciu
        await self.update_log(f'dome lights {"ON" if on else "OFF"}', "OPERATOR", tel)
        if not self.tel_acces[tel]:
            self.WarningWindow("WARNING: U don't have control")
            self.mntGui.domeLights_c.setChecked(not on)    # przelacznik wraca
            return
        ip = self.local_cfg[tel]["light_ip"]
        try:
            # w watku i z limitem czasu: bez odpowiedzi sterownika GUI stalo bez konca
            r = await asyncio.to_thread(
                requests.post, f'http://{ip}/api/rgbw/set',
                json={"rgbw": {"desiredColor": "ff" if on else "00"}}, timeout=self.DOME_LIGHT_TIMEOUT)
            r.raise_for_status()
        except Exception as e:
            await self.update_log(f'dome lights: no answer from {ip} ({e.__class__.__name__})', "WARNING", tel)
            if tel == self.active_tel:
                self.mntGui.domeLights_c.setChecked(not on)    # stan sie nie zmienil
            return
        await self.update_log(f'dome lights {"ON" if on else "OFF"}', "TOI RESPONDER", tel)
        self.toi_op_status[tel]["dome_lights"]["state"] = on
        await self.nats_pub_toi_status[tel].publish(data=self.toi_op_status[tel], timeout=10)


    def update_dome_temp(self):
        try:
            temp = self.sensors[self.active_tel]["dome_conditions"]["temperature"]
            if temp:
                self.mntGui.domeTemp_e.setText(str(temp))
        except Exception:
            pass


    # ############ FOCUS ##################################

    async def focus_con_update(self, event):
        self.focus_con = self.focus.connected

    @qs.asyncSlot()
    async def set_focus(self):
        await self.update_log(f'SET focus', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           self.focus_editing=False
           theme.paint(self.mntGui.setFocus_s, bg="input_bg")
           val=self.mntGui.setFocus_s.value()
           await self.focus_move(self.active_tel, val, "manual")
           await self.update_log(f'setting focus to {val}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    def focus_model(self, tel, temp, hum):
        coeff = {"wk06":{"aTemp":-4.740161,"aHum":-0.677837,"a0":21311.728592},
                "zb08": {"aTemp": -7.446942, "aHum": -0.616425, "a0": 15499.178036},
                "jk15": {"aTemp": -9.090347, "aHum": -0.297319, "a0": 25447.997713}
                }
        if tel in coeff.keys():
            foc = coeff[tel]["a0"] + coeff[tel]["aTemp"] * temp + coeff[tel]["aHum"] * hum
            return foc

        else:
            return None

    # focus z modelu dla obecnej pogody; None bez telemetrii albo modelu
    def focus_model_now(self, tel):
        if self.telemetry_temp is None or self.telemetry_humidity is None:
            return None
        return self.focus_model(tel, float(self.telemetry_temp), float(self.telemetry_humidity))

    # ustawia modelowy focus w polu set focus i jako Central Value autofocusa
    @qs.asyncSlot()
    async def focus_set_update(self):
        focus = self.focus_model_now(self.active_tel)
        if focus is None:
            logger.warning('TOI: focus_set_update skipped - no weather telemetry or focus model')
            return
        self.mntGui.setFocus_s.setValue(int(focus))
        self.focusGui.last_e.setText(str(int(focus)))

    # domyslna metoda autofocusa z toi_config.yaml (focus_method)
    def focus_default_method(self, tel):
        method = self.local_cfg.get(tel, {}).get("focus_method", "laplacian")
        if method not in Focus.METHODS:
            logger.warning(f'TOI: focus_method {method} of {tel} unknown to pyaraucaria.focus, using laplacian')
            return "laplacian"
        return method

    # filtry instrumentu: na razie kazda kamera ma kolo filtrow teleskopu (nats_cfg); kiedy ocaboxapi
    # da det.upstream('filterwheel'), tu bierzemy kolo danego instrumentu
    def instrument_filters(self, instrument):
        if self.active_tel is None:
            return []
        return list(self.nats_cfg[self.active_tel].get("filter_list_names") or [])




    # DUPA
    @qs.asyncSlot()
    async def focus_auto_adjust_OnOff(self):
        if self.tel_acces[self.active_tel]:
            await self.update_log(f'focus adjust ON/OFF', "OPERATOR", self.active_tel)

            if self.mntGui.telAutoFocus_c.isChecked():
                await self.update_log(f'turning focus adjust ON', "TOI RESPONDER", self.active_tel)
                self.toi_switch_status[self.active_tel]["focus_adjust"]= True
                await self.nats_toi_switch_synchro[self.active_tel].publish(data=self.toi_switch_status[self.active_tel], timeout=10)
            else:
                await self.update_log(f'turning focus adjust OFF', "TOI RESPONDER", self.active_tel)
                self.toi_switch_status[self.active_tel]["focus_adjust"]= False
                await self.nats_toi_switch_synchro[self.active_tel].publish(data=self.toi_switch_status[self.active_tel], timeout=10)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            self.focus_adjust_switch_update()


    def focus_adjust_switch_update(self):
        if self.active_tel:
            nats_state = self.toi_switch_status[self.active_tel]["focus_adjust"]
            if nats_state != None:
                state = self.mntGui.telAutoFocus_c.isChecked()
                if state != nats_state:
                    self.update_log(f'updating focus adjust switch: {nats_state}', "TOI", self.active_tel)
                    self.mntGui.telAutoFocus_c.blockSignals(True)
                    self.mntGui.telAutoFocus_c.setChecked(bool(nats_state))
                    self.mntGui.telAutoFocus_c.blockSignals(False)



    # kazde ustawienie focusa przez TOI (SET, autofocus, focus adjust) idzie tedy
    # i staje sie nowym punktem odniesienia dla focus adjust
    async def focus_move(self, tel, position, source):
        position = int(position)
        await self.tel_focusers[tel].aput_move(position)
        await self.publish_focus_reference(tel, position, source)

    async def publish_focus_reference(self, tel, position, source):
        data = {}
        data["position"] = int(position)
        data["davis_temperature"] = self.telemetry_temp
        data["davis_humidity"] = self.telemetry_humidity
        data["time"] = self.ut
        data["source"] = source
        if self.telemetry_temp is None or self.telemetry_humidity is None:
            # bez warunkow referencja jest bezuzyteczna dla modelu - adjust bedzie stal do nastepnego ustawienia
            await self.update_log(f'no weather telemetry - focus adjust inactive until next focus setting', "WARNING", tel)
        self.nats_focus_reference[tel] = data
        try:
            await self.nats_toi_focus_reference[tel].publish(data=data, timeout=10)
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 107c: {e}')

    # docelowy focus = pozycja referencyjna + zmiana modelu od momentu ustawienia referencji
    def focus_adjust_target(self, tel):
        ref = self.nats_focus_reference[tel]
        if not ref:
            return None
        if None in (ref.get("position"), ref.get("davis_temperature"), ref.get("davis_humidity")):
            return None
        if self.telemetry_temp is None or self.telemetry_humidity is None:
            return None
        ref_foc = self.focus_model(tel, float(ref["davis_temperature"]), float(ref["davis_humidity"]))
        foc = self.focus_model(tel, float(self.telemetry_temp), float(self.telemetry_humidity))
        if ref_foc is None or foc is None:
            return None
        return int(ref["position"] + foc - ref_foc)

    # ta funkcja poprawia focus uwzgledniajac zmiany temperatury i wilgotnosci od ostatniego ustawienia focusa
    @qs.asyncSlot()
    async def focus_auto_adjast(self):
        try:
            focus_adjast_step = 5
            for t in self.local_cfg["toi"]["telescopes"]:
                try:
                    if self.tel_acces[t]:

                        var = self.toi_switch_status[t]["focus_adjust"]
                        self.report["focus_adjust"]["status"] = var
                        self.report["focus_adjust"]["type"] = type(var)
                        self.report["focus_adjust"]["repr"] = repr(var)
                        self.report["focus_adjust"]["efect"] = False

                        if self.toi_switch_status[t]["focus_adjust"]:
                            self.report["focus_adjust"]["efect"] = True
                            if self.autofocus_started[t]:
                                continue
                            # nie ruszamy focusem w trakcie ekspozycji (1 waiting, 2 exposing, 3 reading, 4 download)
                            if self.oca_tel_state[t]["ccd_state"]["val"] in (1, 2, 3, 4):
                                continue
                            target = self.focus_adjust_target(t)
                            if target is None:
                                continue
                            ref = self.nats_focus_reference[t]
                            if abs(target - ref["position"]) > focus_adjast_step:
                                await self.focus_move(t, target, "focus_adjust")
                                await self.update_log(f'adjusting focus {ref["position"]} -> {target} '
                                                      f'(ref: {ref["source"]} {ref["time"]}, '
                                                      f'{float(ref["davis_temperature"]):.1f}C/{float(ref["davis_humidity"]):.0f}% -> '
                                                      f'{float(self.telemetry_temp):.1f}C/{float(self.telemetry_humidity):.0f}%)', "TOI", t)
                except Exception as e:     # blad jednego teleskopu nie zatrzymuje korekty pozostalych
                    logger.warning(f'EXCEPTION Focus Adjust ({t}): {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION Focus Adjust: {e}')

    @qs.asyncSlot()
    async def focus_update(self, event):

        # subskrypcje position i ismoving - zapisujemy ten parametr, ktory przyszedl (wywolanie reczne: oba z serwera)
        name = getattr(event, "name", None)
        if name != "ismoving":
            self.focus_value = await self.delivered(event, self.focus.aget_position)
        if name != "position":
            self.focus_moving = await self.delivered(event, self.focus.aget_ismoving)
        target = self.focus_adjust_target(self.active_tel)

        ref = self.nats_focus_reference[self.active_tel]
        if ref:
            t_ref, h_ref = ref.get("davis_temperature"), ref.get("davis_humidity")
            t_txt = f'{float(t_ref):.1f}' if t_ref is not None else '--'
            h_txt = f'{float(h_ref):.0f}' if h_ref is not None else '--'
            tip = f'reference: {ref.get("position")} ({ref.get("source")}, {ref.get("time")}, {t_txt}C / {h_txt}%)'
            if target is not None:
                tip = tip + f'\nmodel target now: {target}'
        else:
            tip = 'reference: --'
        self.mntGui.telFocus_e.setToolTip(tip)

        if self.focus_value != None:
            self.mntGui.telFocus_e.setText(str(self.focus_value))
            if self.focus_moving != None:
                if self.focus_moving:
                    theme.paint(self.mntGui.telFocus_e, bg="moving_bg") # blue
                elif target is not None and abs(target - self.focus_value) > 10:
                    theme.paint(self.mntGui.telFocus_e, bg="warn2_bg")  # yellow
                else:
                    theme.paint(self.mntGui.telFocus_e, bg="field_bg") # white
        else:
            self.mntGui.telFocus_e.setText(f"ERROR")
            theme.paint(self.mntGui.telFocus_e, fg="bad_fg", bg="field_bg")


    # ############### M3 #####################


    @qs.asyncSlot()
    async def set_m3(self):
        await self.update_log(f'SET M3', "OPERATOR", self.active_tel)

        if not self.has_m3:
            await self.update_log(f'no M3 on {self.active_tel}', "WARNING", self.active_tel)
            return
        if self.tel_acces[self.active_tel]:
            m3_i = int(self.mntGui.telM3_s.currentIndex())
            m3_i = str(m3_i + 1) # bo jest 1 based
            await self.m3.aput_selectnasmythport(m3_i)
            await self.update_log(f'setting M3 to {self.nats_cfg[self.active_tel]["tertiary_port_dict"][m3_i]}', "TOI RESPONDER", self.active_tel)

            self.inst_tab_switch = True

        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def m3_update(self, event):
            txt = "--"
            moving = False
            error = False
            port = None
            status = await self.delivered(event, self.m3.aget_tertiarystatus)
            if status != None:
                try:
                    pos = str(status["NasmythPort"])
                    port = pos
                    moving = bool(status["Moving"])
                    error = bool(status["ErrorRaised"])
                    txt = self.nats_cfg[self.active_tel]["tertiary_port_dict"][str(pos)]
                except Exception as e:
                    logger.warning(f'EXCEPTION m3_update: {e}')

            self.mntGui.telM3_e.setText(txt)

            self.m3_name = txt

            # M3 zmienil port: podnosi sie zakladka Optical path (event przychodzi tez z drgan Angle, wiec porownujemy port)
            if port is not None:
                if self.m3_port is not None and port != self.m3_port:
                    self.auxGui.m3_moved()
                self.m3_port = port

            if moving:
                theme.paint(self.mntGui.telM3_e, bg="moving_bg")  # blue
            else:
                theme.paint(self.mntGui.telM3_e, bg="field_bg")  # white

            if error:
                self.mntGui.telM3_e.setText(f"ERROR")
                theme.paint(self.mntGui.telM3_e, fg="bad_fg", bg="field_bg")

            if self.m3_name != None:
                if self.inst_tab_switch:
                    if "beso" in self.m3_name and self.instGui.beso_tab is not None:
                        self.instGui.tab.setCurrentWidget(self.instGui.beso_tab)
                    else:
                        self.instGui.tab.setCurrentWidget(self.instGui.ccd_tab)
                self.inst_tab_switch = False

            #{'Moving': False, 'MotorOn': True, 'ErrorRaised': False, 'Angle': 134.78500116616488, 'NasmythPort': 2, 'PortName': 'ADR10'}

    # ############### FILTERS #####################

    async def filter_con_update(self, event):
        self.fw_con = self.fw.connected

    @qs.asyncSlot()
    async def set_filter(self):
        await self.update_log(f'SET filter', "OPERATOR", self.active_tel)

        if self.tel_acces[self.active_tel]:
           ind=int(self.mntGui.telFilter_s.currentIndex())
           if ind == -1: filtr="--"
           else: filtr=self.filter_list[ind]
           await self.fw.aput_position(ind)
           await self.update_log(f'setting filter to {filtr}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    async def filter_update(self, event):
            pos = await self.delivered(event, self.fw.aget_position)
            if pos is None:
                self.mntGui.telFilter_e.setText("--")
                theme.paint(self.mntGui.telFilter_e, bg="moving_bg")
                return
            pos = int(pos)
            if 0 <= pos < len(self.filter_list or []):
                filtr = self.filter_list[pos]
                self.curent_filter = filtr        # tylko znana pozycja; w ruchu (-1) zostaje poprzedni filtr
            else:
                filtr = "--" if pos == -1 else f"#{pos}"     # w ruchu / spoza konfiguracji (dawniej lista[-1] / IndexError)
            self.mntGui.telFilter_e.setText(filtr)
            self.filter = filtr

            if pos == -1:
                theme.paint(self.mntGui.telFilter_e, bg="moving_bg")
            else: theme.paint(self.mntGui.telFilter_e, bg="field_bg")
            self.telescope_switch_status["filters"] = True



    # ############### ROTATOR #####################

    async def rotator_con_update(self, event):
        self.rotator_con=self.rotator.connected


    async def rotator_update(self, event):
        self.rotator_mechpos = self.rotator.mechanicalposition
        self.rotator_pos = self.rotator.position
        self.rotator_moving = self.rotator.ismoving
        fields = (self.mntGui.telRotator1_e, self.mntGui.rotatorEq_e)
        if self.rotator_pos is not None and self.rotator_mechpos is not None:
            self.mntGui.telRotator1_e.setText(f"{self.rotator_mechpos:.2f}")
            self.mntGui.rotatorEq_e.setText(f"{self.rotator_pos:.2f}")
            fg, bg = None, "field_bg"
            if self.rotator_moving:
                bg = "input_edit_bg"
                try:
                    if self.rotator_pos_prev - self.rotator_pos > 1:
                        bg = "moving_bg"
                except (AttributeError, TypeError):
                    pass
        else:
            for field in fields:
                field.setText("ERROR")
            fg, bg = "bad_fg", "field_bg"
        for field in fields:
            theme.paint(field, fg=fg, bg=bg)
        # kat mechaniczny w 10 deg od miekkiego limitu ASA (+-160) - zolte tlo, takze w ruchu
        if self.rotator_mechpos is not None and abs((self.rotator_mechpos + 180) % 360 - 180) > 150:
            theme.paint(self.mntGui.telRotator1_e, fg=fg, bg="warn_bg")
        self.rotator_pos_prev = self.rotator_pos

    @qs.asyncSlot()
    async def set_rotator(self):
        await self.update_log(f'SET rotator', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if self.rotator is None or not bool(self.cfg_showRotator):
                await self.update_log(f'no rotator on {self.active_tel}', "WARNING", self.active_tel)
                return
            try:
                val = float(self.mntGui.setRotator1_e.text())
            except ValueError:
                val = None
            # ASA podaje kat mechaniczny jako 0..360 (342 = -18); limit miekki +-160 (twardy ogranicznik +-170)
            # sprawdzamy wiec po przeliczeniu na -180..180, a wysylamy 0..360 jak driver
            if val is None or abs((val + 180) % 360 - 180) > 160:
                await self.update_log(f'wrong rotator position: {self.mntGui.setRotator1_e.text()} '
                                      f'(mechanical limits ±160)', "WARNING", self.active_tel)
                return
            val = val % 360
            await self.rotator.aput_movemechanical(val)
            await self.update_log(f'moving rotator to mechanical {val:.2f}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

        # ############ TELESCOPE #########################

    @qs.asyncSlot()
    async def EmStop(self):
        await self.update_log(f'EMERGENCY STOP', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            await self.tic_telescopes[self.active_tel].emergency_stop()
            await self.dome.aput_dome_follower_off()
            await self.update_log(f'EMERGENCY STOP', "TOI RESPONDER", self.active_tel)

        else:
            logger.warning(f"REQUEST: emergency stop but no telescope is selected")


    @qs.asyncSlot()
    async def ping(self):
        await self.update_log(f'send annoying PING', "OPERATOR", self.active_tel)
        info = "send annoying PING"
        label = "PING"
        await self.send_ocm_message(info,label=label)

    def open_sound_test_window(self):
        self.soundTestGui.show()
        self.soundTestGui.raise_()
        self.soundTestGui.activateWindow()

    # test dzwieku z okna PING (SoundTestWindow): komunikat z ta sama etykieta co prawdziwy alarm, ale "test": true i
    # tekst TEST - oca_monitor gra ten sam dzwiek, overwatche reaguja tylko na PING, a czytelnicy liczacy alarmy
    # (Halina, raporty) powinni test pomijac
    @qs.asyncSlot()
    async def send_sound_test(self, label, meaning):
        await self.update_log(f'sound test {label}', "OPERATOR", self.active_tel)
        await self.send_ocm_message(f"TEST of the {label} sound ({meaning}) - not a real alarm", label=label, test=True)

    @qs.asyncSlot()
    async def send_ocm_message(self,info,label="INFO",test=False):
        try:
            data = {}
            data["ut"] = f"{time.strftime('%H:%M:%S', time.gmtime())}"
            data["user"] = f'TOI by {self.myself}'
            data["info"] = info
            data["label"] = label
            if test:
                data["test"] = True
            await toi_publisher("messages").publish(data=data, timeout=10)     # nowy temat i stary (Halina)
        except Exception as e:
            logger.warning(f'EXCEPTION send_ocm_message: {e}')


    @qs.asyncSlot()
    async def shutdown(self):
        await self.update_log(f'SHUTDOWN', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            if self.tel_acces[self.active_tel]:
                await self.dome.aput_dome_follower_off()
                await self.tic_telescopes[self.active_tel].shutdown(dome_park_az=180)
                await self.update_log(f'shutdowning', "TOI RESPONDER", self.active_tel)
            else:
                txt = "WARNING: U don't have control"
                self.WarningWindow(txt)
        else:
            txt = f"REQUEST: telescope shutdown but no telescope is selected"

    @qs.asyncSlot()
    async def weatherStop(self):
        await self.update_log(f'WEATHER STOP', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            if self.tel_acces[self.active_tel]:
                await self.tic_telescopes[self.active_tel].weather_stop(dome_park_az=180)
                await self.update_log(f'weather stopping', "TOI RESPONDER", self.active_tel)

            else:
                txt = "WARNING: U don't have control"
                self.WarningWindow(txt)
        else:
            txt = f"REQUEST: weather stop but no telescope is selected"

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        self.reset_ob(self.active_tel)
        try:
            s = self.nats_toi_ob_status[self.active_tel]
            self.ob_progress[self.active_tel]["ob_started"] = False
            self.ob_progress[self.active_tel]["ob_done"] = False
            self.ob_progress[self.active_tel]["ob_start_time"] = None
            self.ob_progress[self.active_tel]["ob_expected_time"] = None
            self.ob_progress[self.active_tel]["ob_program"] = ""
            self.ob_progress[self.active_tel]["error"] = False

            await s.publish(data=self.ob_progress[self.active_tel], timeout=10)
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 78: {e}')

        try:
            await self.user.aput_break_control()
        except Exception:
            pass
        try:
            await self.user.aput_take_control(84000)
            self.upload_plan()
            self.update_plan(self.active_tel)
        except Exception:
            pass


# ############ INNE ##############################

    # STAGE 2
    # to nie bedzie na razie obslugiwane
    def GuiderPassiveOnOff(self):
        if self.guiderGui.guiderCameraOn_c.isChecked():
            self.guider_failed = 1
            self.guider_passive_dx = []
            self.guider_passive_dy = []

    def wind_limits(self, tel):
        # (observation_stop, pointing) w m/s dla teleskopu z obs_limits; brak w configu -> globalne cfg_wind_limit*
        def _limit(key, default):
            try:
                return float(self.nats_cfg[tel][key])
            except (KeyError, TypeError, ValueError):
                return float(default)
        return _limit("wind_limit", self.cfg_wind_limit), _limit("wind_limit_pointing", self.cfg_wind_limit_pointing)

    # pole wiatru w oknie obserwacji: kolor wg tego, dla ilu teleskopow wiatr przekroczyl prog `which`
    # (0 observation_stop, 1 pointing): jeden - zolty, kilka - pomaranczowy, wszystkie - czerwony
    def wind_field_style(self, field, which, hint):
        tels = self.local_cfg["toi"]["telescopes"]
        wind = float(self.telemetry_wind)
        limits = {t: self.wind_limits(t)[which] for t in tels}
        over = [t for t in tels if wind > limits[t]]
        if not over:
            color = "field_bg"
        elif len(over) == len(tels):
            color = "bad_bg"
        elif len(over) == 1:
            color = "warn_bg"
        else:
            color = "warn2_bg"
        field.setStyleSheet(theme.field_style(color))
        tip = f"{hint} [m/s]: " + ", ".join(f"{t} {limits[t]:g}" for t in tels)
        if over:
            tip += f"\nExceeded: {', '.join(over)}"
        field.setToolTip(tip)

    def updateWeather(self):
        try:
            self.obsGui.main_form.wind_e.setText(f"{self.telemetry_wind:.1f} [m/s]")
            self.obsGui.main_form.windDir_e.setText(f"{self.telemetry_wind_direction:.0f} [deg]")
            self.obsGui.main_form.temp_e.setText(f"{self.telemetry_temp:.1f} [C]")
            rain = self.telemetry_rain is not None and float(self.telemetry_rain) > 0
            if rain:
                self.obsGui.main_form.hummidity_e.setText(f"RAIN {self.telemetry_humidity:.0f} [%]")
            else:
                self.obsGui.main_form.hummidity_e.setText(f"{self.telemetry_humidity:.0f} [%]")

            # Wind: przerwanie obserwacji (observation_stop), Direction: zakaz celowania pod wiatr (pointing)
            self.wind_field_style(self.obsGui.main_form.wind_e, 0, "Davis weather station.\nStop limits")
            self.wind_field_style(self.obsGui.main_form.windDir_e, 1, "Davis weather station.\nPointing limits")

            if rain or float(self.telemetry_humidity)> float(self.cfg_humidity_limit):
                self.obsGui.main_form.hummidity_e.setStyleSheet(theme.field_style("bad_bg"))
            else:
                self.obsGui.main_form.hummidity_e.setStyleSheet(theme.field_style())

            if float(self.telemetry_temp) < -1:
                self.obsGui.main_form.temp_e.setStyleSheet(theme.field_style("bad_bg"))
            else:
                self.obsGui.main_form.temp_e.setStyleSheet(theme.field_style())


            self.obsGui.main_form.update_table()   # ikonki pogody (wiatr, deszcz, wilgotnosc, zimno)
            for kind in self.CONDITION_FIELDS:
                self.update_condition_field(kind)
            self.update_hold_markers()      # minuty karencji

            if self.skyGui.skyView:
                self.skyGui.skyView.updateWind(self)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: updateWeather: {e}')

    def ephem_update(self,tmp):
        utc = self.ephemeris.utc
        if utc is not None:
            self.ephem_utc = float(utc)

    def WarningWindow(self,txt):
        self.tmp_box=QtWidgets.QMessageBox()
        self.tmp_box.setWindowTitle("TOI message")
        self.tmp_box.setText(txt)
        self.tmp_box.show()

    @qs.asyncSlot()
    async def plan_log_agregator(self, tel, data):
        await self.nats_toi_plan_log[tel].publish(data=data, timeout=10)

    @qs.asyncSlot()
    async def update_log(self, txt, label, tel, level=20):
        try:
            if self.tel_acces[tel]:
                log = {}
                ut = str(self.ut).split()[1].split(":")[0] + ":" + str(self.ut).split()[1].split(":")[1] + ":" + \
                     str(self.ut).split()[1].split(":")[2]
                log["time"] = ut
                log["user"] = self.tel_users[tel]
                log["label"] = label
                log["level"] = level
                log["txt"] = txt

                await self.nats_toi_log[tel].publish(data=log, timeout=10)

                tmp = f'{ut} {self.tel_users[tel]} {level} [{label}] {txt}'
                self.log_record[tel] = self.log_record[tel] + tmp + "\n"
            else:
                pass


        except Exception:
            pass

    def update_oca(self):
        self.obsGui.main_form.update_table()

    # dioda stanu: znak ● w kolorze stanu

    def set_led(self, widget, color_key):
        # dioda: znak ● w kolorze klucza toi_theme
        if widget.text() != "\u25CF":
            widget.setText("\u25CF")
        theme.paint(widget, fg=color_key, extra="font-size: 14pt;")


    def reset_ob(self,tel):
        templeate = {"ob":{"uobi":None},"meta":{"run":False,"done":False,"origin":None,"slot_time":None,"start_time":None,"continue_plan":False}}
        self.ob[tel] = copy.deepcopy(templeate)

    def variables_init(self):

        self.jd = None


        self.telescope_switch_status = {}
        self.telescope_switch_status["plan"] = False

        self.fits_downloader_data = None
        self.fits_ofp_data = None

        # tu pobieramy konfiguracje z NATS
        self.client_cfg = self.observatory_model.get_client_configuration()
        nats_cfg = self.observatory_model.get_telescopes_configuration()

        # a tu tworzymy konfiguracje teleskopow dla kazdego teleskopu wk06, zb08, jk15, etc.
        self.nats_cfg = {k:{} for k in nats_cfg.keys()}

        self.nats_toi_op_status = {k:{} for k in nats_cfg.keys()}
        self.sensors = {k:{} for k in nats_cfg.keys()}

        for k in self.nats_cfg.keys():

            try:
                tmp = nats_cfg[k]["observatory"]["style"]["color"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["color"] = tmp

            # limity wiatru per teleskop (obs_limits, oca-problems#273); None -> globalne cfg_wind_limit*
            try:
                wind_cfg = nats_cfg[k]["observatory"]["obs_limits"]["weather_restrictions"]["wind"]
            except (KeyError, TypeError):
                wind_cfg = {}
            if not isinstance(wind_cfg, dict):
                wind_cfg = {}
            self.nats_cfg[k]["wind_limit"] = wind_cfg.get("observation_stop")
            self.nats_cfg[k]["wind_limit_pointing"] = wind_cfg.get("pointing")

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["min_alt"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["min_alt"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["max_alt"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["max_alt"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["obs_min_alt"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["low_alt"] = tmp


            try:
                tmp = nats_cfg[k]["observatory"]["components"]["camera"]["pixel_scale"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["pixel_scale"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["filterwheel"]["filters"]
                tmp_n = [item["name"] for item in sorted(tmp, key=lambda x: x["position"])]
                tmp_i= [item["position"]  for item in sorted(tmp, key=lambda x: x["position"])]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp_n = None
                tmp_i = None        # bez kola filtrow - nie pozycje poprzedniego teleskopu (pierwszy: NameError przy starcie)
            self.nats_cfg[k]["filter_list_names"] = tmp_n
            self.nats_cfg[k]["filter_list"] = tmp_i

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["focuser"]["default_position"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["focus_def_pos"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["focuser"]["default_step"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None
            self.nats_cfg[k]["focus_def_step"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["tertiary"]["positions"]
            except (KeyError, TypeError):      # brak wpisu albo null w konfiguracji TIC
                tmp = None

            self.nats_cfg[k]["tertiary_dict"] = tmp

            if tmp != None:
                self.nats_cfg[k]["tertiary_port_dict"] = {(str(tmp[k]["port"])):k for k in tmp.keys() }
                self.nats_cfg[k]["tertiary_port_list"] = [k for k in tmp.keys()]
            else:
                self.nats_cfg[k]["tertiary_port_dict"] = None
                self.nats_cfg[k]["tertiary_port_list"] = None

            # komponenty teleskopu z TIC (observatory.components): derotator -> wiersz ROTATOR, tertiary -> M3
            try:
                self.nats_cfg[k]["components"] = set(nats_cfg[k]["observatory"]["components"])
            except (KeyError, TypeError):
                self.nats_cfg[k]["components"] = None

        # statusty wszystkich teleskopow

        templeate = {
            "mount_motor":{"val":None, "pms_topic":".mount.motorstatus"},
            "mirror_status": {"val": None, "pms_topic": ".covercalibrator.coverstate"},
            "mount_tracking": {"val": None, "pms_topic": ".mount.tracking"},
            "mount_slewing": {"val": None, "pms_topic": ".mount.slewing"},
            "dome_shutterstatus": {"val": None, "pms_topic": ".dome.shutterstatus"},
            "dome_slewing": {"val": None, "pms_topic": ".dome.slewing"},
            "fw_position": {"val": None, "pms_topic": ".filterwheel.position"},
            "ccd_state": {"val": None, "pms_topic": ".camera.camerastate"},

        }

        self.oca_tel_state = {k:copy.deepcopy(templeate) for k in self.local_cfg["toi"]["telescopes"]}

        tmp = {"dome_ventilators":{"state":False,"defoult":False}, "mirror_fans":{"state":False,"defoult":False},"flat_lamps":{"state":False,"defoult":False},"dome_lights":{"state":False,"defoult":False}}
        self.toi_op_status = {t:copy.deepcopy(tmp) for t in self.local_cfg["toi"]["telescopes"]}
        self.dome_follow_all = {}   # teleskop -> dome follower wlaczony (True/False/None), FOLLOW w tabeli teleskopow
        self.safety_cutoff = {t:None for t in self.local_cfg["toi"]["telescopes"]}   # z tic.status.<tel>.access_grantor.safety_cutoff_state

        tmp = {"focus_adjust":None}
        self.toi_switch_status = {t:copy.deepcopy(tmp) for t in self.local_cfg["toi"]["telescopes"]}

        #DUPA
        self.report = {"focus_adjust": {}}
        self.report["focus_adjust"]["status"] = "--"
        self.report["focus_adjust"]["type"] = "--"
        self.report["focus_adjust"]["repr"] = "--"
        self.report["focus_adjust"]["efect"] = "--"

        self.cfg_showRotator = True   # potrzebne do pierwszego wyswietlenia
        self.tel_alpaca_con = False

        self.catalog_file = None

        self.observatory = ["-24:35:24","-70:11:47","2800"]
        self.oca_site = ephem.Observer()
        self.oca_site.lat = self.observatory[0]
        self.oca_site.lon = self.observatory[1]
        self.oca_site.elevation = float(self.observatory[2])

        self.cwd = os.getcwd()
        self.comProblem = False
        self.script_location = os.path.dirname(os.path.abspath(__file__))
        self.msg_log_file = self.script_location+"/Logs/msg_log.txt"
        self.msg_log_lines = 1000

        # geometry settings

        geometry = QtWidgets.QDesktopWidget().screenGeometry(0)

        self.obs_window_geometry = [geometry.left(),geometry.top(),850,400]
        self.mnt_geometry = [self.obs_window_geometry[0],self.obs_window_geometry[1]+self.obs_window_geometry[3]+110,850,450]
        self.instrument_geometry = [self.obs_window_geometry[0] + 910 ,self.obs_window_geometry[1]+610,500,500]
        self.plan_geometry = [self.obs_window_geometry[0]+1415 ,self.obs_window_geometry[1],490,1100]




        self.tic_con=None
        self.fw_con=None
        self.mount_con=None
        self.dome_con=None
        self.rotator_con=None
        self.inst_con=None
        self.focus_con=None
        self.covercalibrator_con=None


        self.cfg_wind_limit_pointing =  11  # m/s
        self.cfg_wind_limit = 14 # m/s
        self.cfg_humidity_limit = 70  # %
        self.cfg_temperature_limit = 0
        self.overhed = 10
        # limity wysokosci; wartosci z TIC ustawia telescope_switched
        self.cfg_alt_limits = {"min": 0.0, "max": 90.0, "low": 0.0}

        self.nextOB_ok = None
        self.flag_newimage = None
        self.image = []

        # observer
        self.observer = ""

        # weather telemetry
        self.telemetry_temp = None
        self.telemetry_wind = None
        self.telemetry_wind_direction = None
        self.telemetry_humidity = None
        self.telemetry_pressure = None
        self.telemetry_rain = None

        # aux zmienne

        self.log_record = {t:"" for t in self.local_cfg["toi"]["telescopes"]}

        self.fits_ffs_data = {t:[] for t in self.local_cfg["toi"]["telescopes"]}
        self.readoutmode_tel = {}       # tel -> tryb odczytu kamery (READ-MOD z faststat, aktywny z kamery)
        self.mirror_fans = {}           # tel -> (wentylatory lustra z TIC, time.time() wiadomosci)
        self.mirror_fanStatus = False
        self.conditions = {}        # rodzaj -> ostatnia wiadomosc z toi.conditions_subjects
        self.clouds_telescopes = None   # ostatnie "telescopes" z allsky_overwatch (odswiezenie tabeli przy zmianie)
        self.fits_photo_z0_data = {t:[] for t in self.local_cfg["toi"]["telescopes"]}


        templeate = {"ob_started":False,"ob_done":False,"ob_expected_time":None,"ob_start_time":None,"ob_program":None,"error":False,"status":"","ndit_req":None,"ndit":None,"dit_exp":None,"dit_start":None}
        self.ob_progress = {t:copy.deepcopy(templeate) for t in self.local_cfg["toi"]["telescopes"]}


        self.ob = {}
        for t in self.local_cfg["toi"]["telescopes"]:
            self.reset_ob(t)

        self.nats_plan_status = {"current_i":-1,"next_i":-1,"plan":[]}

        self.nats_ob_progress = {}      # ten sluzy tylko do czytania z nats
        self.nats_focus_status = {}     #  tak samo



        self.autofocus_started = {k:False for k in self.local_cfg["toi"]["telescopes"]}
        self.last_focus_position = {k:None for k in self.local_cfg["toi"]["telescopes"]}
        self.nats_focus_record = {k:None for k in self.local_cfg["toi"]["telescopes"]}
        self.nats_focus_reference = {k:None for k in self.local_cfg["toi"]["telescopes"]}   # punkt odniesienia dla focus adjust

        self.acces=True


        # plan

        self.plan = {k:[] for k in self.local_cfg["toi"]["telescopes"]}
        self.done_uobi = []
        self.next_i = {k:0 for k in self.local_cfg["toi"]["telescopes"]}
        self.current_i = {k:-1 for k in self.local_cfg["toi"]["telescopes"]}

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15"]  # wg25 is not working

        # active telescope & universal
        self.ut=str(ephem.now())
        self.ephem_utc = 0
        self.ephem_prev_utc = 0
        self.active_tel_i=None
        self.active_tel=None

        # ccd
        self.binxy_changed = False
        self.ccd_binx = None
        self.ccd_biny = None
        self.ccd_temp_set = None
        self.ccd_temp = None

        # filter wheel
        self.filter = None
        self.filter_list = None

        # M3
        self.m3_name = None
        self.m3_port = None     # ostatni port M3 aktywnego teleskopu
        self.has_m3 = False     # wg komponentu tertiary w TIC, ustawia telescope_switched
        self.dome_follower_seen = None
        self.services_since = time.time()
        self.started = time.time()
        self.night_observers = None         # ostatni wpis z tic.status.ocm.observers
        self.observers_local = None         # wybor tylko dla tej sesji ("Only this TOI"), nie publikowany
        self.observers_later_until = 0
        try:
            with open('./observers.yaml', 'r', encoding='utf-8') as f:
                entries = (yaml.safe_load(f) or {}).get("observers") or []
            # wpis to nazwisko albo slownik z polem name (na pozniejsze dane, np. instytucja)
            self.observers_list = [e["name"] if isinstance(e, dict) else str(e) for e in entries]
            # nazwiska ida kiedys do naglowka FITS (OBSERVER) - tylko ASCII
            bad = [n for n in self.observers_list if not is_fits_ascii(n)]
            if bad:
                logger.warning(f'TOI: observers.yaml - not ASCII (FITS headers), write e.g. {fits_ascii(bad[0])!r}: {bad}')
        except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
            logger.warning(f'TOI: observers.yaml not read: {e}')
            self.observers_list = []
        self.checklist_state = None         # ostatni wpis z tic.status.ocm.checklist
        try:
            with open('./checklist.yaml', 'r', encoding='utf-8') as f:
                self.checklist = [e for e in (yaml.safe_load(f) or {}).get("checklist") or [] if e.get("id")]
        except (OSError, yaml.YAMLError, AttributeError) as e:
            logger.warning(f'TOI: checklist.yaml not read: {e}')
            self.checklist = []
        self.inst_tab_switch = None

        # guider
        self.prev_guider_coo = []
        self.prev_guider_adu = []
        self.guider_failed = 1

        # dome
        self.dome_shutterstatus="--"
        self.dome_az="--"
        self.dome_status="--"

        # mount
        self.mount_motortatus=False
        self.mount_ra=None
        self.mount_dec=None
        self.mount_alt=None
        self.mount_az=None
        self.mount_parked="--"
        self.mount_slewing="--"
        self.mount_tracking="--"
        self.dome_follow = None
        self.dome_follow_busy = False
        self.pulseRa = 0
        self.pulseDec = 0
        self.cover_status = None


        # focus
        self.focus_editing=False
        self.focus_value=0
        self.focus_moving = None

        # rotator
        self.rotator_pos="unknown"

        # program
        self.req_ra = ""
        self.req_dec = ""
        self.req_epoch = ""
        self.program_id = ""

        # log wykonanych ob z planrunnera z NATS
        self.ob_log = []

        self.tmp_i = 1

        self.nats_toi_plan_status = {}
        self.nats_toi_ob_status = {}
        self.nats_toi_switch_synchro = {}

        self.nats_toi_flat_status = {}
        self.nats_toi_focus_status = {}
        self.nats_toi_focus_record = {}
        self.nats_toi_focus_reference = {}

        self.nats_toi_plan_log = {}
        self.nats_pub_toi_status = {}
        self.nats_toi_log = {}

        self.planrunners = {}
        self.tic_telescopes = {k:self.observatory_model.get_telescope(k) for k in self.local_cfg["toi"]["telescopes"]}

        self.acces_grantors = {k:self.tic_telescopes[k].get_access_grantor() for k in self.local_cfg["toi"]["telescopes"]}
        self.tel_users = {k: None for k in self.local_cfg["toi"]["telescopes"]}
        self.tel_acces = {k: None for k in self.local_cfg["toi"]["telescopes"]}

        self.tel_focusers = {k:self.tic_telescopes[k].get_focuser() for k in self.local_cfg["toi"]["telescopes"]}

    async def on_start_app(self):    # rozczlonkowac ta metoda i wlozyc wszystko do run_qt_app
        await self.run_background_tasks()
        await self.mntGui.on_start_app()
        await self.obsGui.on_start_app()
        await self.instGui.on_start_app()
        await self.instGui.ccd_tab.on_start_app()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)


async def run_qt_app():

    # added KeyboardInterrupt to loop let close application by ctrl+c in console
    def ask_exit():
        raise KeyboardInterrupt
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, ask_exit)

    with open('./toi_config.yaml', 'r') as cfg_file:
        local_cfg = yaml.safe_load(cfg_file)

    nats_host = local_cfg["toi"]["nats_host"]
    nats_port = local_cfg["toi"]["nats_port"]

    msg = Messenger()
    nats_opener = await msg.open(host=nats_host, port=nats_port, wait=3)
    try:
        if nats_opener:
            await nats_opener  # waiting for connection to nats
        if msg.is_open:
            pass
        else:
            logger.error(f"Can't connect to NATS {nats_host}:{nats_port} Application stopped!")
            return
    except asyncio.TimeoutError:
        logger.error(f"Can't connect to NATS {nats_host}:{nats_port} timeout accrue. Application stopped!")
        return
    # TODO ernest_nowy_tic COMENT nie powołujemy już 'ClientAPI' ręcznie, Observatory zaciąga konfigurację z nats i tworzy ClientAPI potem
    observatory_model = Observatory(client_name="TOI_Client", config_stream="tic.config.observatory",
                                    policy='display')
    await observatory_model.load_client_cfg()
    api = observatory_model.client

    def close_future(future_, loop_):
        loop_.call_later(10, future_.cancel)
        future_.cancel()

    future = asyncio.Future()
    app = qs.QApplication.instance()
    if hasattr(app, "aboutToQuit"):
        getattr(app, "aboutToQuit").connect(
            functools.partial(close_future, future, loop)
        )

    toi = TOI(loop=loop, observatory_model=observatory_model, client_api=api, local_cfg=local_cfg, app=app)

    await toi.on_start_app()
    await future
    await msg.close()
    return True


def main():
    # Force xcb on Linux if Wayland is detected to allow window positioning
    if sys.platform == 'linux':
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            if "QT_QPA_PLATFORM" not in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "xcb"
                logger.info("Wayland detected. Forcing QT_QPA_PLATFORM=xcb for correct window positioning.")

    try:
        qs.run(run_qt_app())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)
    except RuntimeError as e:
        # Python 3.14: przy zamykaniu qasync zatrzymuje petle, zanim run_qt_app sie skonczy - to zwykle wyjscie
        if "Event loop stopped before Future completed" in str(e):
            sys.exit(0)
        raise


if __name__ == "__main__":
    main()
