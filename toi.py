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
# import json
import pwd
import signal
# import requests
import socket
import sys
import uuid
import copy
from xmlrpc.client import ResponseError

import ephem
import numpy
import requests
import yaml
from pathlib import Path
from typing import Optional
import qasync as qs
from PyQt5 import QtWidgets, QtCore
from astropy.io import fits
from obcom.comunication.base_client_api import BaseClientAPI
from ocaboxapi import Observatory, Telescope, AccessGrantor, Dome, Mount, CoverCalibrator, Focuser, Camera, \
    FilterWheel, Rotator, CCTV
from ocaboxapi.ephemeris import Ephemeris
from ocaboxapi.plan import ObservationPlan
from ocaboxapi.exceptions import OcaboxServerError
from pyaraucaria.coordinates import *
# from astropy.io import fits
from pyaraucaria.dome_eq import dome_eq_azimuth
from pyaraucaria.obs_plan.obs_plan_parser import ObsPlanParser

from serverish.messenger import Messenger, single_read, get_reader, get_journalreader
from serverish.messenger.msg_publisher import MsgPublisher, get_publisher
from serverish.messenger.msg_journal_pub import MsgJournalPublisher, get_journalpublisher, JournalEntry

#from aux_gui import AuxGui
from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from calcFocus import calc_focus as calFoc
from ffs_lib.ffs import FFS
from instrument_gui import InstrumentGui
from mnt_gui import MntGui
from sky_gui import SkyGui
from obs_gui import ObsGui
from plan_gui import PlanGui
from fits_gui import FitsWindow
from focus_gui import FocusWindow
from flat_gui import FlatWindow
from guider_gui import GuiderWindow
from planrunner_gui import PlanrunnerWindow
from conditions_gui import ConditionsWindow

from toi_lib import *

# import paho.mqtt.client as mqtt
#from starmatch_lib import StarMatch

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

        self.local_cfg = local_cfg

        self.setWindowTitle("Telescope Operator Interface")
        self.setLayout(QtWidgets.QVBoxLayout())

        host = socket.gethostname()
        user = pwd.getpwuid(os.getuid())[0]
        self.myself=f'{user}@{host}'
        self.observatory_model = observatory_model

        self.variables_init()

        # window generation

        self.obsGui = ObsGui(self, loop=self.loop, client_api=self.client_api)
        self.mntGui = MntGui(self, loop=self.loop, client_api=self.client_api)

        self.skyGui = SkyGui(self)

        self.instGui = InstrumentGui(self, loop=self.loop, client_api=self.client_api)
        self.planGui = PlanGui(self, loop=self.loop, client_api=self.client_api)
        self.fitsGui = FitsWindow(self)
        self.focusGui = FocusWindow(self)
        self.flatGui = FlatWindow(self)
        self.conditionsGui = ConditionsWindow(self)
        self.guiderGui = GuiderWindow(self)
        self.planrunnerGui = PlanrunnerWindow(self)


        #self.auxGui = AuxGui(self)

        self.add_background_task(self.tic_con_loop())
        self.add_background_task(self.almanac_loop())
        self.add_background_task(self.alpaca_con_loop())
        self.add_background_task(self.tel_con_loop())
        self.add_background_task(self.tel_progress_loop())
        self.add_background_task(self.check_lights_loop())



        #self.add_background_task(self.guider_loop())

        self.add_background_task(self.TOItimer())
        self.add_background_task(self.nats_weather_loop())

        for t in self.oca_tel_state.keys():   # statusy wszystkich teleskopow
            self.add_background_task(self.nats_pub_toi_message_reader(t))

            self.add_background_task(self.nats_ffs_reader(t))

            self.add_background_task(self.nats_journal_planner_reader(t))
            self.add_background_task(self.nats_journal_ofp_reader(t))
            self.add_background_task(self.nats_journal_downloader_reader(t))
            self.add_background_task(self.nats_journal_guider_reader(t))

            self.add_background_task(self.oca_telemetry_conditions_reader(t))

            self.add_background_task(self.oca_telemetry_program_reader(t))
            self.add_background_task(self.nats_pub_toi_status_reader(t))

            self.add_background_task(self.nats_plan_ofp_log_reader(t))


            for k in self.oca_tel_state[t].keys():
                self.add_background_task(self.oca_telemetry_reader(t,k))


        self.obsGui.main_form.update_table()
        # publishery natsow
        # NATS WRITER

        for k in self.local_cfg["toi"]["telescopes"]:
            self.nats_toi_plan_status[k] = get_publisher(f'tic.status.{k}.toi.plan')
            self.nats_toi_ob_status[k] = get_publisher(f'tic.status.{k}.toi.ob')

            self.nats_toi_flat_status[k] = get_publisher(f'tic.status.{k}.toi.flat')
            self.nats_toi_focus_status[k] = get_publisher(f'tic.status.{k}.toi.focus')
            self.nats_toi_focus_record[k] = get_publisher(f'tic.status.{k}.toi.focus_record')

            self.nats_toi_plan_log[k] = get_publisher(f'tic.status.{k}.toi.plan_log')
            self.nats_toi_log[k] = get_publisher(f'tic.status.{k}.toi.log')
            self.nats_pub_toi_status[k] = get_publisher(f'tic.status.{k}.toi.status')  # dome status
            self.nats_pub_toi_message[k] = get_publisher(f'tic.status.{k}.toi.message')

    async def oca_telemetry_conditions_reader(self,tel):
        try:
            r = get_reader(f'telemetry.conditions.{tel}-htsensor', deliver_policy='last')
            async for data, meta in r:
                self.sensors[tel]["dome_conditions"] = data["measurements"]
                self.update_dome_temp()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 100a: {e}')


    async def oca_telemetry_reader(self,tel,key):
        # dodac sprawdzanie czy na tych topikach nadaje
        try:
            r = get_reader(f'tic.status.{tel}{self.oca_tel_state[tel][key]["pms_topic"]}', deliver_policy='last')
            async for data, meta in r:
                txt = data["measurements"][f"{tel}{self.oca_tel_state[tel][key]['pms_topic']}"]
                self.oca_tel_state[tel][key]["val"] = txt
                self.update_oca()
                # tutaj jakas zmienna ktora nadaje jak nic nie idzie

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 100: {e}')

    async def oca_telemetry_program_reader(self,tel):
        try:
            reader = get_reader(f'tic.status.{tel}.toi.ob', deliver_policy='last')
            async for status, meta in reader:
                self.ob_progress[tel] = status
                self.update_oca()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 101: {e}')

    async def nats_pub_toi_status_reader(self,tel):
        try:
            reader = get_reader(f'tic.status.{tel}.toi.status', deliver_policy='last')
            async for data, meta in reader:
                self.nats_toi_op_status[tel] = data
                self.obsGui.main_form.update_table()
                # if "dome_follow_switch" in data.keys():
                #     self.toi_status["dome_follow_switch"] = data["dome_follow_switch"]
                #     self.mntGui.domeAuto_c.setChecked(self.toi_status["dome_follow_switch"])
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 108: {e}')

    async def nats_plan_ofp_log_reader(self,tel):
        try:
            r = get_reader(f'tic.status.{tel}.planner.command.log', deliver_policy='new')
            async for data, meta in r:
                if self.tel_acces[tel]:
                    await self.plan_log_agregator(tel,data)
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
                if self.tel_acces[tel]:
                    await self.update_log(f'{data.message}', "PLANRUNNER", tel, level=data.level)
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
                if data.level > 10:
                    if self.tel_acces[tel]:
                        await self.update_log(f'{data.message}', "OFP", tel, level=data.level)
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
                if self.tel_acces[tel]:
                    await self.update_log(f'{data.message}', "DOWNLOADER", tel, level=data.level)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b3: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')

    async def nats_journal_guider_reader(self,tel):
        try:
            r = get_journalreader(f'tic.journal.{tel}.guider', deliver_policy='new')
            async for data, meta in r:
                if self.tel_acces[tel]:
                    await self.update_log(data.message, "GUIDER", tel, level=data.level)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4b4: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 110b: {e}')


    async def nats_pub_toi_message_reader(self,tel):
        try:
            reader = get_reader(f'tic.status.{tel}.toi.message', deliver_policy='new')
            async for msg, meta in reader:
                txt = f'{self.ut}    {msg["tel"]}:    {msg["info"]}'
                self.obsGui.main_form.msg_e.append(txt)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 101: {e}')


    # NATS Conditions reader
    async def nats_ffs_reader(self,tel):
        try:
            time = datetime.datetime.now() - datetime.timedelta(hours=24)
            r = get_reader(f'tic.status.{tel}.fits.pipeline.faststat',  deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in r:
                self.fits_ffs_data[tel].append(data)
                #self.conditionsGui.update()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 778: {e}')
        except Exception as e:
            logger.warning(f'EXCEPTION 778b: {e}')


    # NATS weather
    async def nats_weather_loop(self):
        try:
            reader = get_reader('telemetry.weather.davis', deliver_policy='last')
            async for data, meta in reader:
                weather = data['measurements']
                self.telemetry_temp = weather["temperature_C"]
                self.telemetry_wind = weather["wind_10min_ms"]
                self.telemetry_wind_direction = weather["wind_dir_deg"]
                self.telemetry_humidity = weather["humidity"]
                self.telemetry_pressure = weather["pressure_Pa"]
                self.updateWeather()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 102: {e}')


    async def tic_con_loop(self):
        while True:
            try:
                self.tic_con = await self.observatory_model.is_tic_server_available()
                if self.tic_con == True:
                    self.obsGui.main_form.ticStatus2_l.setText("\u262F  TIC")
                    self.obsGui.main_form.ticStatus2_l.setStyleSheet("color: green;")
                else:
                    self.obsGui.main_form.ticStatus2_l.setText("\u262F  TIC")
                    self.obsGui.main_form.ticStatus2_l.setStyleSheet("color: red;")
                await asyncio.sleep(3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                raise
            except Exception as e:
                logger.warning(f'EXCEPTION 103: {e}')

    #  ############# ZMIANA TELESKOPU ### TELESCOPE SELECT #################
    async def telescope_switched(self):

        print("* TEL SWITCH")
        t0 = time.time()

        #self.fitsGui.clear()
        self.telescope_switch_status["plan"] = False


        try:
            #await self.fitsGui.thread.stop()
            self.fitsGui.thread.quit()
            self.fitsGui.thread.wait()
            self.fitsGui.ffs_worker.stop()
            self.fitsGui.ffs_worker.quit()
            self.fitsGui.ffs_worker.wait()
        except (AttributeError, RuntimeError):
            pass

        t1 = time.time()
        print(f'* a {t1-t0}')

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
        self.flat_log = []

        # TELESCOPE CONFIGURATION HARDCODED

        self.active_tel = self.local_cfg["toi"]["telescopes"][self.active_tel_i]

        self.filter_list = self.nats_cfg[self.active_tel]["filter_list_names"]  # tu sa nazwy
        self.filter_list_i = self.nats_cfg[self.active_tel]["filter_list"]      # a tu sa wartosci do put
        self.cfg_inst_gain = self.nats_cfg[self.active_tel]["gain_list_names"]
        self.cfg_inst_gain_i = self.nats_cfg[self.active_tel]["gain_list"]
        self.cfg_inst_rm = self.nats_cfg[self.active_tel]["rm_list_names"]
        self.cfg_inst_rm_i = self.nats_cfg[self.active_tel]["rm_list"]
        self.cfg_inst_temp = self.nats_cfg[self.active_tel]["ccd_temp"]
        self.cfg_focuser_defpos = f'{self.nats_cfg[self.active_tel]["focus_def_pos"]}/{self.nats_cfg[self.active_tel]["focus_def_step"]}'
        self.cfg_focuser_seq = "8/V/5" # DUPA

        self.cfg_tel_directory = self.local_cfg[self.active_tel]["tel_directory"]
        self.cfg_tel_ob_list = self.local_cfg[self.active_tel]["tel_ob_list"]
        self.flat_log_files = self.local_cfg[self.active_tel]["flat_log_files"]
        self.cfg_showRotator = self.local_cfg[self.active_tel]["showRotator"]

        self.overhed = self.local_cfg[self.active_tel]["overhead"]

        self.cfg_alt_limits = {}
        self.cfg_alt_limits["min"] = float(self.nats_cfg[self.active_tel]["min_alt"])
        self.cfg_alt_limits["max"] = float(self.nats_cfg[self.active_tel]["max_alt"])
        self.cfg_alt_limits["low"] = float(self.nats_cfg[self.active_tel]["low_alt"])

        self.catalog_file = self.local_cfg[self.active_tel]["object_catalog"]

        if self.active_tel == "wk06":
            self.cfg_inst_obstype = ["Science", "Zero", "Dark", "Sky Flat", "Dome Flat"]
            self.cfg_inst_mode = ["Normal", "Sky", "JitterBox", "JitterRandom"]
            self.cfg_inst_bins = ["1x1", "2x2", "1x2", "2x1"]
            self.cfg_inst_subraster = ["No", "Subraster1", "Subraster2", "Subraster3"]
            self.cfg_inst_defSetUp = {"gain": "x4", "rm": "1MHz","bin":"1x1", "temp":-58}

        elif self.active_tel == "zb08":
            self.cfg_inst_obstype =  ["Science","Zero","Dark","Sky Flat","Dome Flat"]
            self.cfg_inst_mode =  ["Normal", "Sky", "JitterBox", "JitterRandom"]
            self.cfg_inst_bins = ["1x1","2x2","1x2","2x1"]
            self.cfg_inst_subraster = ["No","Subraster1","Subraster2","Subraster3"]
            self.cfg_inst_defSetUp = {"gain": "x4", "rm": "1MHz","bin":"1x1", "temp":-58}

        elif self.active_tel == "jk15":
            self.cfg_inst_obstype = ["Science", "Zero", "Dark", "Sky Flat", "Dome Flat"]
            self.cfg_inst_mode = ["Normal", "Sky", "JitterBox", "JitterRandom"]
            self.cfg_inst_bins = ["1x1", "2x2", "1x2", "2x1"]
            self.cfg_inst_subraster = ["No", "Subraster1", "Subraster2", "Subraster3"]
            self.cfg_inst_defSetUp = {"gain": "Gain 2", "rm": "0,1MHz 18-bit","bin":"1x1", "temp":-58}

        t2 = time.time()
        print(f'* b {t2-t1}')

        # obsluga subskrypcji

        if self.telescope is not None:
            await self.stop_background_methods(group="subscribe")
            self.telescope.unsubscribe_all_component()
            self.telescope.unwatch_all_component()
            await self.stop_background_tasks(group="telescope_task")

        self.telescope = self.observatory_model.get_telescope(self.active_tel)
        self.user = self.telescope.get_access_grantor()
        self.dome = self.telescope.get_dome()
        self.mount = self.telescope.get_mount()
        self.cover = self.telescope.get_covercalibrator()
        self.focus = self.telescope.get_focuser()
        self.ccd = self.telescope.get_camera()
        self.guider = self.telescope.get_camera(id='guider')
        self.fw = self.telescope.get_filterwheel()
        if bool(self.cfg_showRotator):
            self.rotator = self.telescope.get_rotator()
        self.cctv = self.telescope.get_cctv()
        self.ephemeris = self.observatory_model.get_ephemeris()
        self.ctc = self.telescope.get_cycle_time_calculator(client_config_dict=self.client_cfg) # cycle time calculator

        t3 = time.time()
        print(f'* c {t3-t2}')

        # ---------------------- run subscriptions from ocabox ----------------------
        await self.run_method_in_background(self.ephemeris.asubscribe_utc(self.ephem_update,time_of_data_tolerance=0.25),group="subscribe")
        #
        #await self.run_method_in_background(self.user.asubscribe_current_user(self.user_update), group="subscribe")
        #
        await self.run_method_in_background(self.dome.asubscribe_connected(self.dome_con_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update),group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_az(self.domeAZ_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_slewing(self.domeStatus_update), group="subscribe")
        await self.run_method_in_background(self.dome.asubscribe_dome_fans_running(self.Ventilators_update),group="subscribe")
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
        await self.run_method_in_background(self.fw.asubscribe_connected(self.filter_con_update), group="subscribe")
        await self.run_method_in_background(self.fw.asubscribe_position(self.filter_update), group="subscribe")
        #
        await self.run_method_in_background(self.focus.asubscribe_connected(self.focus_con_update), group="subscribe")
        await self.run_method_in_background(self.focus.asubscribe_position(self.focus_update), group="subscribe")
        await self.run_method_in_background(self.focus.asubscribe_ismoving(self.focus_update), group="subscribe")
        #
        if bool(self.cfg_showRotator):
            await self.run_method_in_background(self.rotator.asubscribe_connected(self.rotator_con_update),group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_position(self.rotator_update),group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_mechanicalposition(self.rotator_update),group="subscribe")
            await self.run_method_in_background(self.rotator.asubscribe_ismoving(self.rotator_update),group="subscribe")
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


        t4 = time.time()
        print(f'* d {t4-t3}')

        # background task specific for selected telescope

        #self.add_background_task(self.nats_log_loop_reader(), group="telescope_task")
        self.add_background_task(self.nats_downloader_reader(), group="telescope_task")
        self.add_background_task(self.nats_ofp_reader(), group="telescope_task")
        self.add_background_task(self.nats_ofp_error_reader(), group="telescope_task")

        self.add_background_task(self.nats_toi_plan_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_ob_status_reader(), group="telescope_task")

        self.add_background_task(self.nats_toi_plan_log_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_log_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_flat_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_focus_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_focus_record_reader(), group="telescope_task")

        self.add_background_task(self.reader_nats_flat_overwatch(), group="telescope_task")






        await self.run_background_tasks(group="telescope_task")

        t5 = time.time()
        print(f'* e {t5-t4}')

        try:
            self.mntGui.updateUI()
            self.update_dome_temp()
            self.skyGui.updateUI()
            self.planGui.updateUI()
            self.instGui.updateUI()
            self.planrunnerGui.updateUI()
            self.flatGui.updateUI()
            self.focusGui.updateUI()
            self.fitsGui.updateUI()

            if not bool(self.cfg_showRotator):
                self.mntGui.comRotator1_l.setText("\u2B24")
                self.mntGui.comRotator1_l.setStyleSheet("color: rgb(190,190,190);")
                self.mntGui.telRotator1_l.setStyleSheet("color: rgb(190,190,190);")

            t6 = time.time()
            print(f'* f {t6 - t5}')


            self.updateWeather()
        except Exception as e:
            logger.warning(f'EXCEPTION 0: {e}')

        t7 = time.time()
        await self.update_log(f'{self.active_tel} telescope selected', "OPERATOR", self.active_tel)

        t8 = time.time()
        print(f'* g {t8-t7}')

    # ################### METODY POD NATS READERY ##################

    async def nats_toi_plan_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.plan', deliver_policy='last')
            async for data, meta in reader:
                self.nats_plan_status = data
                self.planGui.update_table()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 104: {e}')


    async def nats_toi_ob_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.ob', deliver_policy='last')
            async for status, meta in reader:
                self.nats_ob_progress = status
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 105: {e}')



    async def nats_toi_log_reader(self):
        try:
            time = datetime.datetime.now() - datetime.timedelta(hours=1)
            reader = get_reader(f'tic.status.{self.active_tel}.toi.log', deliver_policy='by_start_time',opt_start_time=time)
            async for log, meta in reader:
                if True:
                    self.planGui.update_log_window(log)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 106c: {e}')


    async def nats_toi_flat_status_reader(self):
        try:
            time = datetime.datetime.now() - datetime.timedelta(hours=25)  # do konfiguracji
            reader = get_reader(f'tic.status.{self.active_tel}.toi.flat', deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in reader:
                self.flat_log.append(data)
                self.flatGui.updateUI()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107a: {e}')



    async def nats_toi_focus_record_reader(self):           # to moze powinno sie raczej robic jako append
        try:
            time = datetime.datetime.now() - datetime.timedelta(hours=24)  # do konfiguracji
            reader = get_reader(f'tic.status.{self.active_tel}.toi.focus_record', deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in reader:
                self.nats_focus_record = data
                self.update_focus_log_window()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107: {e}')

    async def nats_toi_focus_status_reader(self):           # to moze powinno sie raczej robic jako append
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.focus', deliver_policy='last')
            async for data, meta in reader:
                self.nats_focus_status = data
                self.update_focus_window()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 107: {e}')


    async def nats_toi_plan_log_reader(self):
        try:
            time = datetime.datetime.now() - datetime.timedelta(hours=1)
            reader = get_reader(f'tic.status.{self.active_tel}.toi.plan_log', deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in reader:
                self.ob_log.append(data)
                if "uobi" in data.keys():
                    if data["uobi"] not in self.done_uobi:
                        self.done_uobi.append(data["uobi"])
                self.planGui.update_log_table()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION 106c: {e}')

    # async def nats_log_loop_reader(self):
    #     try:
    #         tel = self.active_tel
    #         time = datetime.datetime.now() - datetime.timedelta(hours=int(self.local_cfg["toi"]["log_display_h"]))
    #         r = get_reader(f'tic.status.{tel}.planner.command.log', deliver_policy='by_start_time',opt_start_time=time)
    #         async for data, meta in r:
    #             self.ob_log.append(data)
    #             if "uobi" in data.keys():
    #                 if data["uobi"] not in self.done_uobi:
    #                     #self.planGui.done.append(data["uobi"])
    #                     self.done_uobi.append(data["uobi"])
    #             self.planGui.update_log_table()
    #     except (asyncio.CancelledError, asyncio.TimeoutError):
    #         raise
    #     except Exception as e:
    #         logger.warning(f'TOI: EXCEPTION 3: {e}')
    #     except Exception as e:
    #         logger.warning(f'EXCEPTION 109: {e}')

    async def nats_downloader_reader(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.status.{tel}.download', deliver_policy='last')
            async for data, meta in r:
                self.fits_downloader_data = data
                self.new_fits()
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
                self.fits_ofp_data = data
                self.update_fits_data()
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
                await self.update_log(f'{data["error_description"]}', "ERROR", tel)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4a: {e}')


    async def reader_nats_flat_overwatch(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.status.{tel}.flat_overwatch', deliver_policy='last')
            async for data, meta in r:
                self.flatGui.update_flat_overwatch(data)
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
                if self.skyGui.skyView:
                    self.skyGui.skyView.updateAlmanac()
                #self.obsGui.main_form.skyView.updateAlmanac()
                #self.obsGui.main_form.skyView.updateRadar()

            except Exception as e:
                logger.warning(f'EXCEPTION 1: {e}')
            await asyncio.sleep(1)

    async def tel_con_loop(self):
        while True:
            try:
                if self.telescope is not None:
                    if  bool(self.cfg_showRotator):
                        if self.rotator_con and self.tel_alpaca_con:
                            self.mntGui.comRotator1_l.setText("\U0001F7E2")
                            self.mntGui.telRotator1_l.setStyleSheet("color: rgb(0,150,0);")
                        else:
                            self.mntGui.comRotator1_l.setText("\U0001F534")
                            self.mntGui.telRotator1_l.setStyleSheet("color: rgb(150,0,0);")
                    else:
                        self.mntGui.comRotator1_l.setText("\u2B24")
                        self.mntGui.comRotator1_l.setStyleSheet("color: rgb(190,190,190);")
                        self.mntGui.telRotator1_l.setStyleSheet("color: rgb(190,190,190);")

                    if self.mount_con and self.tel_alpaca_con:
                       self.mntGui.mntConn2_l.setText("\U0001F7E2")
                       self.mntGui.mntConn1_l.setStyleSheet("color: rgb(0,150,0);")
                    else:
                       self.mntGui.mntConn2_l.setText("\U0001F534")
                       self.mntGui.mntConn1_l.setStyleSheet("color: rgb(150,0,0);")

                    if self.dome_con and self.tel_alpaca_con:
                        self.mntGui.domeConn2_l.setText("\U0001F7E2")
                        self.mntGui.domeConn1_l.setStyleSheet("color: rgb(0,150,0);")
                    else:
                        self.mntGui.domeConn2_l.setText("\U0001F534")
                        self.mntGui.domeConn1_l.setStyleSheet("color: rgb(150,0,0);")

                    if self.fw_con and self.tel_alpaca_con:
                        self.mntGui.comFilter_l.setText("\U0001F7E2")
                        self.mntGui.telFilter_l.setStyleSheet("color: rgb(0,150,0);")
                    else:
                        self.mntGui.comFilter_l.setText("\U0001F534")
                        self.mntGui.telFilter_l.setStyleSheet("color: rgb(150,0,0);")

                    if self.focus_con and self.tel_alpaca_con:
                        self.mntGui.focusConn_l.setText("\U0001F7E2")
                        self.mntGui.telFocus_l.setStyleSheet("color: rgb(0,150,0);")
                    else:
                        self.mntGui.focusConn_l.setText("\U0001F534")
                        self.mntGui.telFocus_l.setStyleSheet("color: rgb(150,0,0);")

                    if self.inst_con and self.tel_alpaca_con:
                        self.instGui.tab.setTabText(0,"\U0001F7E2 CCD")
                    else:
                        self.instGui.tab.setTabText(0,"\U0001F534 CCD")

            except Exception as e:
                logger.warning(f'EXCEPTION 2: {e}')
            await asyncio.sleep(3)


    async def check_lights_loop(self):
        while True:
            if self.telescope:
                req = requests.get('http://' + self.local_cfg[self.active_tel]["light_ip"] + '/api/rgbw/state', timeout=0.5)

                if req.status_code != 200:
                    val = int(req.json()["rgbw"]["desiredColor"], 16)
                    if val > 0:
                        self.mntGui.domeLights_c.setChecked(True)
                    else:
                        self.mntGui.domeLights_c.setChecked(False)
            await asyncio.sleep(3)



    async def tel_progress_loop(self):
        while True:
            #print(self.nats_ob_progress)
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
                    #if self.nats_ob_progress["ob_start_time"] and self.nats_ob_progress["ob_expected_time"]:
                    if True:
                        ob_started = bool(self.nats_ob_progress["ob_started"])
                        ob_done = bool(self.nats_ob_progress["ob_done"])
                        ob_start_time = self.nats_ob_progress["ob_start_time"]
                        ob_expected_time = self.nats_ob_progress["ob_expected_time"]
                        program = self.nats_ob_progress["ob_program"]
                        error = False
                        if "error" in self.nats_ob_progress.keys():
                            error = self.nats_ob_progress["error"]

                        if ob_started:
                            if True:
                                self.planGui.ob_e.setText(program)
                                self.planGui.ob_e.setCursorPosition(0)

                                if ob_expected_time == None or ob_start_time == None:
                                    self.planGui.ob_Prog_n.setValue(0)
                                    self.planGui.ob_Prog_n.setFormat("")

                                else:

                                    if error:
                                        RED_PROGBAR_STYLE = """
                                        QProgressBar{
                                            border: 2px solid grey;
                                            border-radius: 5px;
                                            text-align: center
                                        }

                                        QProgressBar::chunk {
                                            background-color: red;
                                            width: 10px;
                                            margin: 1px;
                                        }
                                        """
                                        t = self.time - float(ob_start_time)
                                        p = t / float(ob_expected_time)
                                        txt = f"{int(t)}/{int(ob_expected_time)}"
                                        self.planGui.ob_Prog_n.setValue(int(100 * p))
                                        self.planGui.ob_Prog_n.setStyleSheet(RED_PROGBAR_STYLE)
                                        txt = f"ERROR {int(t)}/{int(ob_expected_time)}"
                                        self.planGui.ob_Prog_n.setFormat(txt)

                                    else:
                                        t = self.time - float(ob_start_time)
                                        p = t / float(ob_expected_time)
                                        txt = f"{int(t)}/{int(ob_expected_time)}"
                                        self.planGui.ob_Prog_n.setValue(int(100 * p))
                                        self.planGui.ob_Prog_n.setFormat(txt)

                                        if p > 1.1:
                                            RED_PROGBAR_STYLE = """
                                            QProgressBar{
                                                border: 2px solid grey;
                                                border-radius: 5px;
                                                text-align: center
                                            }
                
                                            QProgressBar::chunk {
                                                background-color: red;
                                                width: 10px;
                                                margin: 1px;
                                            }
                                            """
                                            self.planGui.ob_Prog_n.setStyleSheet(RED_PROGBAR_STYLE)
                                        else:
                                            self.planGui.ob_Prog_n.setStyleSheet("background-color: rgb(233, 233, 233)")

                        elif ob_done:
                            self.planGui.ob_e.setText("")
                            self.planGui.ob_Prog_n.setValue(100)
                            self.planGui.ob_Prog_n.setFormat(f"DONE")
                            self.planGui.ob_Prog_n.setStyleSheet("background-color: rgb(233, 233, 233)")

                        else:
                            self.planGui.ob_e.setText("")
                            self.planGui.ob_Prog_n.setValue(0)
                            self.planGui.ob_Prog_n.setFormat(f"")
                            self.planGui.ob_Prog_n.setStyleSheet("background-color: rgb(233, 233, 233)")


            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 4: {e}')
            await asyncio.sleep(1)


    async def nikomu_niepotrzeba_petla_ustawiajaca_pierdoly(self):
        while True:
            try:
                if self.conditionsGui.isVisible():
                    self.conditionsGui.update()
                if self.ob[self.active_tel]["run"] and "name" in self.ob[self.active_tel].keys():
                    txt = self.ob["name"]

                    if "type" in self.ob[self.active_tel].keys():
                        if self.ob[self.active_tel]["type"] == "OBJECT":
                            self.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
                        elif self.ob[self.active_tel]["type"] == "ZERO":
                            self.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(1)
                        elif self.ob[self.active_tel]["type"] == "DARK":
                            self.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(2)
                        elif self.ob[self.active_tel]["type"] == "SKYFLAT":
                            self.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(3)
                        elif self.ob[self.active_tel]["type"] == "DOMEFLAT":
                            self.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(4)

                    if "seq" in self.ob[self.active_tel].keys():
                        self.instGui.ccd_tab.Select2_r.setChecked(True)
                        self.instGui.ccd_tab.inst_Seq_e.setText(self.ob[self.active_tel]["seq"])
                    if "ra" in self.ob[self.active_tel].keys() and "dec" in self.ob[self.active_tel].keys():
                        self.mntGui.setEq_r.setChecked(True)
                        self.mntGui.nextRa_e.setText(self.ob[self.active_tel]["ra"])
                        self.mntGui.nextDec_e.setText(self.ob[self.active_tel]["dec"])
                        self.mntGui.updateNextRaDec()
                        if "name" in self.ob[self.active_tel].keys():
                            self.mntGui.target_e.setText(self.ob[self.active_tel]["name"])
                            self.mntGui.target_e.setStyleSheet("background-color: white; color: black;")
                    if "name" in self.ob[self.active_tel].keys():
                        self.instGui.ccd_tab.inst_object_e.setText(self.ob[self.active_tel]["name"])
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 5: {e}')
            await asyncio.sleep(1)


    # STAGE2
    # to na razie jest wylaczone
    async def dome_follow_loop(self):
        while True:
            try:
                # Mechanizm Dome Follow
                if False:
                    if self.mntGui.domeAuto_c.isChecked() and self.tel_acces[self.active_tel]:
                        if self.dome_status == False and self.ob[self.active_tel]["run"] == False:
                            az_d = self.dome_az
                            az_m = self.mount_az
                            if az_m != None:
                                az_m = float(az_m)
                                if self.active_tel == "wk06":
                                    if self.mount_ra and self.mount_dec:
                                        side_of_pier = await self.mount.aget_sideofpier()
                                        dome_eq_az, info_dict = dome_eq_azimuth(
                                            ra=self.mount_ra, dec=self.mount_dec, r_dome=2050, spx=-110, spy=-110,
                                            gem=670, side_of_pier=side_of_pier, latitude=-24.598056,
                                            longitude=-70.196389, elevation=2817
                                    )
                                    az_m = dome_eq_az
                            d = az_d - az_m
                            if d > 180:
                                d = d - 360.
                            d = numpy.abs(d)
                            if d > 5.:
                                await self.dome.aput_slewtoazimuth(az_m)
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 6: {e}')
            await asyncio.sleep(1)

    async def TOItimer(self):
        while True:
            try:

                #print("********* PING **************")

                for tel in self.acces_grantors.keys():
                    acces = await self.acces_grantors[tel].aget_is_access()
                    name = await self.acces_grantors[tel].aget_current_user()
                    self.tel_users[tel] = name["name"]
                    self.tel_acces[tel] = acces
                    if self.active_tel:
                        if tel == self.active_tel:
                            txt = self.tel_users[tel]
                            self.skyGui.user_e.setText(txt)
                            if self.tel_acces[tel]:
                                self.skyGui.user_e.setStyleSheet(f"background-color: {self.nats_cfg[tel]['color']};")
                            else:
                                self.skyGui.user_e.setStyleSheet(
                                    f"background-color: rgb(233, 233, 233); color: black;")

                self.update_oca()

            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 7: {e}')

            # sterowanie wykonywaniem planu
            try:
                for tel in self.local_cfg["toi"]["telescopes"]:
                    if tel in self.planrunners.keys():
                        if not self.ob[tel]["done"] and self.ob[tel]["run"] and "seq" in self.ob[tel]["block"]:
                            if not self.planrunners[tel].is_nightplan_running(self.ob[tel]["origin"]):
                                try:
                                    self.ob_progress[tel]["ob_started"] = self.ob[tel]["run"]
                                    self.ob_progress[tel]["ob_done"] = self.ob[tel]["done"]
                                    self.ob_progress[tel]["ob_start_time"] = self.ob_start_time
                                    self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["slot_time"]
                                    self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                                    self.ob_progress[tel]["error"] = True

                                    await self.nats_toi_ob_status[tel].publish(data=self.ob_progress[tel], timeout=10)
                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 8a: {e}')

                                try:
                                    data = {"tel": tel, "info": f"program error on {self.tel_users[tel]}"}
                                    await self.nats_pub_toi_message[tel].publish(data=data, timeout=10)
                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 8b: {e}')
                                self.ob[tel]["done"] = False
                                self.ob[tel]["run"] = False
                                self.ob[tel]["continue_plan"] = False
                                await self.update_log(f'planrunner STOPPED', "ERROR", tel)

                    if self.telescope and not self.tel_acces[tel]:    # obsluga tego ze w czasie realizacji planu, ktos inny przejal kontrole
                        if "continue_plan" in self.ob[tel].keys():
                            if self.ob[tel]["continue_plan"]:
                                self.ob[tel]["continue_plan"] = False
                                self.current_i[tel] = -1
                                self.ob[tel]["done"] = False
                                #self.ob[tel]["run"] = False
                                self.update_plan(tel)


                    if self.telescope and self.tel_acces[tel]:
                        if self.ob[tel]["origin"]:
                            if self.ob[tel]["done"] and "plan" in self.ob[tel]["origin"] and self.ob[tel]["continue_plan"]:
                                await self.plan_start(tel)
                            elif "plan" in self.ob[tel]["origin"] and self.ob[tel]["continue_plan"]:
                                if "wait" in self.ob[tel].keys() and "start_time" in self.ob[tel].keys():
                                    if self.ob[tel]["wait"] != "":
                                        dt = self.time - self.ob[tel]["start_time"]
                                        if float(dt) > float(self.ob[tel]["wait"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f" {tel} PLAN: {self.ob[tel]['name']} {self.ob[tel]['wait']} s DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)
                                            time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                            tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sec={self.ob[tel]["wait"]}'}},"time": {"end_dt": time}}
                                            self.plan_log_agregator(tel, tmp)
                                if "wait_ut" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_ut"] != "":
                                        req_ut = str(self.ob[tel]["wait_ut"])
                                        ut = str(self.almanac["ut"]).split()[1]
                                        ut = 3600 * float(ut.split(":")[0]) + 60 * float(ut.split(":")[1]) + float(ut.split(":")[2])
                                        req_ut = 3600 * float(req_ut.split(":")[0]) + 60 * float(req_ut.split(":")[1]) + float(
                                            req_ut.split(":")[2])
                                        if req_ut < ut:
                                            self.ob[tel]["done"] = True
                                            await self.msg(f" {tel} PLAN: {self.ob[tel]['name']} UT {self.ob[tel]['wait_ut']} DONE", "green")
                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)
                                            time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                            tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'ut={self.ob[tel]["wait_ut"]}'}},"time": {"end_dt": time}}
                                            self.plan_log_agregator(tel, tmp)
                                if "wait_sunrise" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_sunrise"] != "":
                                        if deg_to_decimal_deg(self.almanac["sun_alt"]) > float(self.ob[tel]["wait_sunrise"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f" {tel} PLAN: {self.ob[tel]['name']} sunrise {self.ob[tel]['wait_sunrise']} DONE", "green")
                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)
                                            time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                            tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sunrise={self.ob[tel]["wait_sunrise"]}'}},"time": {"end_dt": time}}
                                            self.plan_log_agregator(tel, tmp)
                                if "wait_sunset" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_sunset"] != "":
                                        if deg_to_decimal_deg(self.almanac["sun_alt"]) < float(self.ob[tel]["wait_sunset"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f" {tel} PLAN: {self.ob[tel]['name']} sunset {self.ob[tel]['wait_sunset']} DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)
                                            time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                            tmp = {"object_name": "WAIT", "command_dict": {"command_name": "","kwargs":{"seq":f'sunset={self.ob[tel]["wait_sunset"]}'}},"time": {"end_dt": time}}
                                            self.plan_log_agregator(tel, tmp)

            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 8: {e}')

            try:
                self.planGui.update_table()
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 9: {e}')

            await asyncio.sleep(1)


    async def guider_loop(self):
        while True:
            await asyncio.sleep(1)
            # ############# GUIDER ################
            # to jest brudny algorytm guidera
            #
            try:

                if self.telescope is not None:  # if telescope is selected, other component (e.g. dome ...) also. So no check
                        #guider_loop = int(self.auxGui.guider_tab.guiderView.guiderLoop_e.text())
                        method = self.guiderGui.guiderView.method_s.currentText()

                        # guider robi sie w petli, co guider_loop robi sie ekspozycja
                        self.tmp_i = self.tmp_i + 1
                        # if self.tmp_i > guider_loop:
                        #     self.tmp_i = 0

                        # tu sie robie ekspozycja
                        if self.tmp_i == 1:
                            exp = float(self.guiderGui.guiderView.guiderExp_e.text())
                            if self.guiderGui.guiderView.guiderCameraOn_c.checkState():
                                try:
                                    await self.guider.aput_startexposure(exp, True)
                                except Exception as e:
                                    pass

                        # ######## Analiza obrazu guider
                        # poniewaz nie wiem ile sie czyta kamera, to analiza robi sie tuz przed nastepna ekspozycja
                        # nie ma na razie zabezpieczenia ze petla trwa krocej niz ekspozycja
                        if self.tmp_i == 0 and self.guiderGui.guiderView.guiderCameraOn_c.checkState():
                            self.guider_image = await self.guider.aget_imagearray()
                            if self.guider_image:
                                image = self.guider_image
                                image = numpy.asarray(image)
                                self.guiderGui.guiderView.updateImage(image)  # wyswietla sie obrazek

                                # tu licza sie podstawowe statystyki obrazka, potrzebne do dalszej analizy
                                stats = FFS(image)
                                th = float(self.guiderGui.guiderView.treshold_s.value())
                                fwhm = float(self.guiderGui.guiderView.fwhm_s.value())

                                # a tutaj znajdujemy gwiazdy, ale dla guidera to wychopdzi ledwo co...
                                coo, adu = stats.find_stars(threshold=th, kernel_size=int(2 * fwhm), fwhm=fwhm)

                                # a tutaj robimy bardziej przyzwoita fotometrie znalezionych gwiazd
                                # bez tego nawet czesto nie znajdziemy najjasniejszej gwiazdy
                                x_coo, y_coo = zip(*coo)
                                adu = []
                                for x, y in zip(x_coo, y_coo):
                                    aperture = image[int(y) - int(fwhm):int(y) + int(fwhm),
                                               int(x) - int(fwhm):int(x) + int(fwhm)]
                                    adu_tmp = numpy.sum(aperture)
                                    adu_tmp = adu_tmp - aperture.size * stats.median
                                    if adu_tmp <= 0: adu_tmp = 1
                                    adu.append(adu_tmp)

                                indices = numpy.argsort(adu)[::-1]
                                adu = numpy.array(adu)[indices]
                                coo = coo[indices]

                                coo = numpy.array(coo)
                                adu = numpy.array(adu)
                                # tutaj wybieramy tylko 10 najjasniejszych gwiazd i na nich dalej pracujemy
                                coo = coo[:10]
                                adu = adu[:10]

                                if len(coo) > 1:
                                    x_tmp, y_tmp = zip(*coo)
                                    # zaznaczamy 10 gwiazd na obrazku
                                    self.guiderGui.guiderView.updateCoo(x_tmp, y_tmp, color="white")

                                dx_multiStars, dy_multiStars = None, None
                                dx_single, dy_single = None, None
                                dx, dy = None, None

                                # Algorytm multistars
                                if method == "Auto" or method == "Multistar":
                                    if len(coo) > 3 and len(self.prev_guider_coo) > 3:
                                        x_coo, y_coo = zip(*coo)
                                        x_ref, y_ref = zip(*self.prev_guider_coo)
                                        xr = []
                                        yr = []
                                        # dla kazdej gwiazdy znajdujemy inne najblizsze gwiazdy
                                        for x, y in zip(x_coo, y_coo):
                                            x_tmp = numpy.abs(x - x_coo)
                                            y_tmp = numpy.abs(y - y_coo)
                                            r_tmp = x_tmp ** 2 + y_tmp ** 2
                                            i_tmp = numpy.argsort(r_tmp)
                                            i1 = i_tmp[1]
                                            i2 = i_tmp[2]
                                            # dla kazdej gwiazdy liczymy taki indeks geometryczny
                                            # uwzgledniajacy polozenie wzgledne
                                            x_range = (x - x_coo[i1]) + (x - x_coo[i2])
                                            y_range = (y - y_coo[i1]) + (y - y_coo[i2])
                                            xr.append(x_range)
                                            yr.append(y_range)

                                        xr0 = []
                                        yr0 = []
                                        # tu robimy to samo, ale dla obrazka referencyjnego (poprzedniego)
                                        for x, y in zip(x_ref, y_ref):
                                            x_tmp = numpy.abs(x - x_ref)
                                            y_tmp = numpy.abs(y - y_ref)
                                            r_tmp = x_tmp ** 2 + y_tmp ** 2
                                            i_tmp = numpy.argsort(r_tmp)
                                            i1 = i_tmp[1]
                                            i2 = i_tmp[2]
                                            x_range = (x - x_ref[i1]) + (x - x_ref[i2])
                                            y_range = (y - y_ref[i1]) + (y - y_ref[i2])
                                            xr0.append(x_range)
                                            yr0.append(y_range)

                                        xr, yr = numpy.array(xr), numpy.array(yr)
                                        xr0, yr0 = numpy.array(xr0), numpy.array(yr0)
                                        x_coo, y_coo = numpy.array(x_coo), numpy.array(y_coo)
                                        x_ref, y_ref = numpy.array(x_ref), numpy.array(y_ref)

                                        dx_tab = []
                                        dy_tab = []
                                        x_matched = []
                                        y_matched = []
                                        # A tutaj bedziemy porownywac te indeksy
                                        for i, tmp in enumerate(xr):
                                            # sprawdzamy czy indeks geometryczny dla okazdej osi jest rozsadny
                                            j_list = numpy.array([i for i in range(len(xr0))])
                                            x_diff = numpy.abs(xr[i] - xr0)
                                            y_diff = numpy.abs(yr[i] - yr0)
                                            mk1 = x_diff < 3
                                            mk2 = y_diff < 3
                                            mk = [k and z for k, z in zip(mk1, mk2)]
                                            tmp_rx0 = xr0[mk]
                                            tmp_ry0 = yr0[mk]
                                            j_list = j_list[mk]
                                            prev_diff = 10000
                                            # jak juz wybralismy gwiazdy z obrazka referencyjnego ktore
                                            # moga byc nasza gwiazda, jezeli jest ich wiecej niz jedna,
                                            # to wybieramy ta ktorej indeks geometryczny jest njbardziej zhblizony
                                            if len(j_list) > 0:
                                                for j in j_list:
                                                    diff = x_diff[j] + y_diff[j]
                                                    if diff < prev_diff:
                                                        k = j
                                                        prev_diff = diff
                                                    # dla tak znalezionej gwiazdy liczymy roznice na
                                                    # obrazku i obrazku referencyjnym
                                                    dx = x_coo[i] - x_ref[k]
                                                    dy = y_coo[i] - y_ref[k]
                                                x_matched.append(x_coo[i])
                                                y_matched.append(y_coo[i])
                                                dx_tab.append(dx)
                                                dy_tab.append(dy)

                                        if len(dx_tab) > 0:
                                            x_tmp = numpy.median(dx_tab)
                                            y_tmp = numpy.median(dy_tab)
                                            if numpy.abs(x_tmp) < 50 and numpy.abs(y_tmp) < 50:  # dodatkowy warunek rozsadku
                                                dx_multiStars = x_tmp
                                                dy_multiStars = y_tmp

                                # a tu po prostu porownujemy pozycje najjasniejszej gwiazdy
                                if len(coo) > 1 and len(self.prev_guider_coo) > 1:
                                    if method == "Auto" or method == "Single star":

                                        single = coo[0]
                                        single_x = single[0]
                                        single_y = single[1]

                                        single0 = self.prev_guider_coo[0]
                                        single_x0 = single0[0]
                                        single_y0 = single0[1]

                                        x_tmp = single_x0 - single_x
                                        y_tmp = single_y0 - single_y

                                        if numpy.abs(x_tmp) < 50 and numpy.abs(y_tmp) < 50:
                                            dx_single = x_tmp
                                            dy_single = y_tmp

                                # jak wybralismy metode Multistar
                                if method == "Multistar":
                                    if dx_multiStars != None:
                                        dx = dx_multiStars
                                        dy = dy_multiStars
                                        txt = f"multistar\n dx={dx} dy={dy}"
                                        self.guiderGui.guiderView.updateCoo(x_matched, y_matched, color="cyan")
                                    else:
                                        txt = "multistar failed"
                                    self.guiderGui.guiderView.result_e.setText(txt)

                                # jak wybralismy metode Singlestar
                                elif method == "Single star":
                                    if dx_single != None:
                                        dx = dx_single
                                        dy = dy_single
                                        txt = f"single star\n dx={dx} dy={dy}"
                                        self.guiderGui.guiderView.updateCoo([single_x], [single_y], color="magenta")
                                    else:
                                        txt = "single star failed"
                                    self.guiderGui.guiderView.result_e.setText(txt)

                                # jak wybralismy Auto, to najpierw stara sie multistar a
                                # jak sie nie uda to single star
                                elif method == "Auto":
                                    if dx_multiStars != None:
                                        dx = dx_multiStars
                                        dy = dy_multiStars
                                        txt = f"Auto (multistar)\n dx={dx} dy={dy}"
                                        self.guiderGui.guiderView.updateCoo(x_matched, y_matched, color="cyan")
                                    elif dx_single != None:
                                        dx = dx_single
                                        dy = dy_single
                                        txt = f"Auto (single star)\n dx={dx} dy={dy}"
                                        self.guiderGui.guiderView.updateCoo([single_x], [single_y], color="magenta")
                                    else:
                                        txt = "auto failed"
                                    self.guiderGui.guiderView.result_e.setText(txt)

                                # tutaj jest lista ostatnich 20 pomiarow, sluzaca
                                # do liczenia kumulatywnego przesuniecia
                                # jak teleskop zrobi slew to sie lista zeruje
                                if dx != None:
                                    self.guider_passive_dx.append(dx)
                                    self.guider_passive_dy.append(dy)

                                if len(self.guider_passive_dx) > 20:
                                    self.guider_passive_dx = self.guider_passive_dx[1:]
                                    self.guider_passive_dy = self.guider_passive_dy[1:]

                                self.guiderGui.guiderView.update_plot(self.guider_passive_dx, self.guider_passive_dy)

                                # aktualny obrazek staje sie referencyjnym, chyba ze nie udalo znalez sie przesuniecia
                                # wtedy 1 raz tego nie robi (steruje tym guider_failed)
                                if (dx != None and dy != None) or self.guider_failed == 1:
                                    self.prev_guider_coo = coo
                                    self.prev_guider_adu = adu
                                    self.guider_failed = 0
                                else:
                                    self.guider_failed = 1

            # TODO ernest_nowy_tic COMENT robiąc w asyncio 'except Exception as e' samo łatwo jest zrobić niezamykający się task
            #  dlatego trzeba odfiltrować CONAJMNIEJ 'asyncio.CancelledError, asyncio.TimeoutError' błędy one muszą być rzucone.
            #  Robi się tak jak poniżej. Niewiem czy PyQT jakieś urzywa ale do asyncio to te 2
            except (asyncio.CancelledError, asyncio.TimeoutError):
                raise
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 10: {e}')



    # ############ PLAN RUNNER START ##########################



    @qs.asyncSlot()
    async def planrunner_start(self,tel):
        try:
            #self.observer = self.auxGui.welcome_tab.observer_e.text()
            if self.tel_acces[tel]:
                if self.active_tel not in self.planrunners.keys():
                    self.planrunners[tel] = self.tic_telescopes[tel].get_observation_plan()
                    tmp = self.planrunners[tel]
                    self.planrunners[tel].add_info_callback('exec_json', lambda info: self.PlanRunFeedback(tmp, info))
                self.ob_progress[tel]["ndit"] = 0
                self.ob_progress[tel]["dit_start"] = 0

                #self.ob_program = self.ob_program + f' observers="{self.observer}"' # zle sie parsuje naraz comment i observers
                program = self.ob[tel]["block"]
                program_name = self.ob[tel]["origin"]
                await self.planrunners[tel].aload_nightplan_string(program_name, string=program, overwrite=True, client_config_dict=self.client_cfg)
                await self.planrunners[tel].arun_nightplan(program_name, step_id="00")
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 11: {e}')

    # ############ PLAN RUNNER CALLBACK ##########################

    @qs.asyncSlot()
    async def PlanRunFeedback(self,planrunner,info):

        tel = [k for k,val in self.planrunners.items() if val == planrunner][0]

        for t in self.local_cfg["toi"]["telescopes"]:
            if t==tel:

                # NORMAL PLAN

                if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
                    if info["name"] == "NIGHTPLAN" and info["started"] and not info["done"]:
                        await self.msg(f" {tel} PLAN: Plan started","black")
                        self.ob[tel]["run"] = True     # to swiadczy o tym czy planrunner dziala
                        self.ob[tel]["done"] = False
                        self.ob_start_time = self.time

                        self.ctc.reset_time()
                        self.ctc.set_start_rmode(self.ccd_readoutmode)
                        self.ctc.set_telescope_start_az_alt(az=self.mount_az, alt=self.mount_alt)
                        try:

                            self.ctc_time = self.ctc.calc_time(self.ob[tel]["block"])
                            self.ob[tel]["slot_time"] = self.ctc_time
                            if self.ob[tel]["slot_time"] == 0:
                                self.ob[tel]["slot_time"] = 0.1
                        except ValueError:
                            self.ob[tel]["slot_time"] = 0.1
                            logger.warning(f'TOI: EXCEPTION 44: {e}')

                        txt = self.ob[tel]["block"]

                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = self.ob[tel]["run"]
                            self.ob_progress[tel]["ob_done"] = self.ob[tel]["done"]
                            self.ob_progress[tel]["ob_start_time"] = self.ob_start_time
                            self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["slot_time"]
                            self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                            self.ob_progress[tel]["error"] = False
                            await s.publish(data=self.ob_progress[tel],timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 45: {e}')

                    elif info["name"] == "NIGHTPLAN" and info["done"]:
                        self.ob[tel]["done"] = True

                        if "plan" in self.ob[tel]["origin"]:
                            self.next_i[tel] = self.current_i[tel]
                            self.plan[tel].pop(self.current_i[tel])
                            self.current_i[tel] = -1
                            self.update_plan(tel)

                        self.ob_progress[tel]["dit_start"] = 0

                        try:
                            s = self.nats_toi_ob_status[tel]
                            data = self.ob_progress[tel]
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 46: {e}')

                        self.ob[tel]["run"] = False
                        self.ob[tel]["done"] = True
                        await self.update_log(f'OB: finished ', "TOI", tel)


                        try:
                            s = self.nats_toi_ob_status[tel]
                            self.ob_progress[tel]["ob_started"] = self.ob[tel]["run"]
                            self.ob_progress[tel]["ob_done"] = self.ob[tel]["done"]
                            self.ob_progress[tel]["ob_start_time"] = self.ob[tel]["start_time"]
                            self.ob_progress[tel]["ob_expected_time"] = self.ob[tel]["slot_time"]
                            self.ob_progress[tel]["ob_program"] = self.ob[tel]["block"]
                            self.ob_progress[tel]["error"] = False

                            await s.publish(data=self.ob_progress[tel],timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 47: {e}')

                    elif info["name"] == "SKYFLAT" and info["started"] and not info["done"]:  # SKYFLAT
                        await self.msg(f" {tel} PLAN: AUTO FLAT program started", "black")                       # SKYFLAT

                    elif info["name"] == "SKYFLAT" and info["done"]:
                        await self.msg(f"{tel} PLAN: AUTO FLAT program finished", "black")


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

                        #await self.msg(f" {tel} PLAN: {self.ob_progress[tel]['dit_exp']} [s] exposure started","black")

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


                        #await self.msg(f" {tel} PLAN: {self.ob_progress[tel]['dit_exp']} [s] test exposure started","black")

                    elif info["auto_exp_finnished"]:
                        pass
                        #await self.msg(f" {tel} PLAN: test exposure done", "black")

                if "test_exp_mean" in info.keys():                                                        # SKYFLAT
                    #await self.msg(f" {tel} PLAN: mean {int(info['test_exp_mean'])} ADU measured", "black")
                    pass

                if "id" in info.keys():  # to jest tylko do wyswietlania w oknie loga planu
                    self.program_id = info["id"]
                    ut=str(self.almanac["ut"]).split()[1].split(":")[0]+":"+str(self.almanac["ut"]).split()[1].split(":")[1]
                    txt = f"------  {ut}  -----  {self.program_id}  ------\n {info}\n\n"
                    self.planrunnerGui.text[tel] = self.planrunnerGui.text[tel] + txt
                    self.planrunnerGui.updateUI()

                # FLAT RECORDER

                if set(["type","exp_done","timestamp_utc","mean","exp_time","filter"]).issubset(info.keys()):
                    if info["type"] == "flat" and info["exp_done"]:
                        fr = {}
                        fr["timestamp_utc"] = info["timestamp_utc"]
                        fr["mean"] = info["mean"]
                        fr["exp_time"] = info["exp_time"]
                        fr["filter"] = info["filter"]
                        fr["h_sun"] = f"{deg_to_decimal_deg(self.almanac['sun_alt']):.2f}"
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
                                self.autofocus_started[tel]=False
                                #await self.msg(f" {tel} PLAN: Auto-focus sequence finished","black")
                                max_sharpness_focus, calc_metadata = calFoc.calculate(self.local_cfg[tel]["tel_directory"]+"focus/actual",method=self.focus_method)
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
                                    try:
                                        data["temperature"] = self.sensors[tel]["dome_conditions"]["temperature"]
                                    except Exception as e:
                                        data["temperature"] = "--"
                                    try:
                                        pos = self.oca_tel_state[tel]["fw_position"]["val"]
                                        data["filter"] = self.nats_cfg[tel]["filter_list_names"][pos]
                                    except Exception as e:
                                        data["filter"] = "--"

                                    await self.nats_toi_focus_status[tel].publish(data=data, timeout=10)

                                    data_short = {}
                                    data_short["status"] = data["status"]
                                    data_short["temperature"] = data["temperature"]
                                    data_short["max_sharpness_focus"] = data["max_sharpness_focus"]
                                    data_short["time"] = data["time"]
                                    data_short["filter"] = data["filter"]
                                    await self.nats_toi_focus_record[tel].publish(data=data_short, timeout=10)

                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 42: {e}')

                                if calc_metadata["status"] == "ok":
                                    await self.tel_focusers[tel].aput_move(int(max_sharpness_focus))
                                    await self.update_log(f'focus set to {int(max_sharpness_focus)}', "TOI", tel)
                                else:
                                    await self.update_log(f'focusing FAILED. Focus set to previous value {int(self.last_focus_position[tel])}', "TOI", tel)
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
            if method == "RMS":
                self.focus_method = "rms"
                if number > 2:
                    ok = True
                else:
                    await self.update_log(f'Not enough STEPS number', "WARNING", self.active_tel)
            elif method == "RMS_QUAD":
                self.focus_method = "rms_quad"
                if number > 4:
                    ok = True
                else:
                    await self.update_log(f'Not enough STEPS number', "WARNING", self.active_tel)
            elif method == "LORENTZIAN":
                self.focus_method = "lorentzian"
                if number > 4:
                    ok = True
                else:
                    await self.update_log(f'Not enough STEPS number', "WARNING", self.active_tel)


            if ok:
                exp=self.instGui.ccd_tab.inst_Dit_e.text()
                if len(exp)==0:
                    exp = 5

                seq = f"{int(number)}/"+str(self.curent_filter)+"/"+str(exp)
                pos = f"{int(v0)}/{int(step)}"
                uobi = str(uuid.uuid4())[:8]
                program = f"FOCUS seq={seq} pos={pos} uobi={uobi}"

                self.ob[self.active_tel]["block"] = program
                self.ob[self.active_tel]["origin"] = "auto_focus"
                self.autofocus_started[self.active_tel] = True
                tmp = await self.tel_focusers[self.active_tel].aget_position()
                self.last_focus_position[self.active_tel] = float(tmp)
                self.planrunner_start(self.active_tel)
                await self.update_log(f'autofocussing', "TOI RESPONDER", self.active_tel)

        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    # ############ PLAN ##########################

    @qs.asyncSlot()
    async def manual_plan_start(self,tel):
        await self.update_log(f'PLAN START ', "OPERATOR", tel)

        self.plan_start(self.active_tel)

    # to ustawia wszytskie potrzebne parametry dla planrunnera i wywoluje planrunner_start
    @qs.asyncSlot()
    async def plan_start(self,tel):
        if self.tel_acces[tel]:
            #self.observer = self.auxGui.welcome_tab.observer_e.text()

            if self.next_i[tel] > -1 and self.next_i[tel] < len(self.plan[tel]):
                self.ob[tel] = self.plan[tel][self.next_i[tel]]
                self.ob[tel]["start_time"] = self.time


                if "uobi" in self.ob[tel].keys():
                    if True:
                        if "type" in self.ob[tel].keys() and "name" in self.ob[tel].keys():

                            self.current_i[tel] = self.next_i[tel]
                            self.update_plan(tel)

                            run_nightplan = False
                            if self.ob[tel]["type"] == "STOP":
                                self.ob[tel]["done"]=True
                                self.ob[tel]["run"]=True
                                self.ob[tel]["origin"] = "plan"
                                self.ob[tel]["continue_plan"] = False

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
                                    s = self.nats_pub_toi_message[tel]
                                    data = {"tel":tel,"info":"STOP"}
                                    await s.publish(data=data, timeout=10)
                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 45: {e}')


                            if self.ob[tel]["type"] == "BELL":

                                try:
                                    s = self.nats_pub_toi_message[tel]
                                    data = {"tel":tel,"info":"BELL"}
                                    await s.publish(data=data, timeout=10)
                                    await self.update_log(f'BELL reached ', "TOI", tel)

                                    time = self.ut.split()[0] + "T" + self.ut.split()[1]
                                    tmp = {"object_name": "BELL", "command_dict": {"command_name": ""},
                                           "time": {"end_dt": time}}
                                    self.plan_log_agregator(tel, tmp)

                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 45: {e}')

                                #subprocess.run(["aplay", self.script_location+"/sounds/romulan_alarm.wav"])

                                self.ob[tel]["done"]=True
                                self.ob[tel]["run"]=True
                                self.ob[tel]["origin"] = "plan"
                                self.ob[tel]["continue_plan"] = True

                                self.next_i[tel] = self.current_i[tel]
                                self.plan[tel].pop(self.current_i[tel])
                                self.current_i[tel] = -1
                                self.update_plan(tel)


                            if self.ob[tel]["type"] == "WAIT":
                                if "wait" in self.ob[tel].keys():
                                    self.ob[tel]["start_time"] = self.time
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.update_log(f'starting WAIT ', "TOI", tel)
                                if "wait_ut" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.update_log(f'starting WAIT ', "TOI", tel)
                                if "wait_sunset" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.update_log(f'starting WAIT ', "TOI", tel)
                                if "wait_sunrise" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.update_log(f'starting WAIT ', "TOI", tel)
                                self.ob[tel]["continue_plan"] = True
                                self.ob[tel]["origin"] = "plan"

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


                            if self.ob[tel]["type"] == "ZERO" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan"
                                program = self.ob[tel]["block"]

                            if self.ob[tel]["type"] == "DARK" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan"
                                program = self.ob[tel]["block"]

                            if self.ob[tel]["type"] == "DOMEFLAT" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan_domeflat"
                                program = self.ob[tel]["block"]

                            if self.ob[tel]["type"] == "SKYFLAT" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan_skyflat"
                                program = self.ob[tel]["block"]

                            if self.ob[tel]["type"] == "FOCUS" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan_auto_focus"
                                program = self.ob[tel]["block"]

                                self.focus_method = "lorentzian"
                                self.autofocus_started[tel] = True
                                focus = await self.tel_focusers[tel].aget_position()
                                self.last_focus_position[tel] = float(focus)

                            if self.ob[tel]["type"] == "OBJECT" and "block" in self.ob[tel].keys():
                                run_nightplan = True
                                program_name = "plan"
                                program = self.ob[tel]["block"]
                                if "comment" in program:
                                    program = program.split("comment")[0]

                            if run_nightplan:
                                if "uobi=" not in program:
                                    program = program + f' uobi={self.ob[tel]["uobi"]}'
                                self.ob[tel]["block"] = program
                                self.ob[tel]["origin"] = program_name
                                self.ob[tel]["continue_plan"] = True
                                self.planrunner_start(tel)
                                await self.update_log(f'starting OB: {program} ', "TOI", tel)


        else:
            pass


    @qs.asyncSlot()
    async def resume_program(self):
        await self.update_log(f'program RESUME', "OPERATOR", self.active_tel)
        await self.planrunners[self.active_tel].astop_nightplan()
        await self.planrunners[self.active_tel].arun_nightplan(self.ob[self.active_tel]["origin"], step_id=self.program_id)
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


        self.ob[self.active_tel]["done"] = False
        self.ob[self.active_tel]["run"] = False
        self.ob[self.active_tel]["origin"] = "plan"
        self.ob[self.active_tel]["continue_plan"] = False
        self.ob[self.active_tel]["slot_time"] = None
        self.ob[self.active_tel]["start_time"] = None

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
        self.planGui.update_table()
        self.plan[self.active_tel] = self.planGui.plan
        self.next_i[self.active_tel] = self.planGui.next_i
        self.update_plan(self.active_tel)


    @qs.asyncSlot()
    async def update_plan(self,tel):
            if self.plan[tel] != None:
                try:
                    if len(self.plan[tel]) == 0:
                        self.planGui.update_table()
                    else:
                        self.check_next_i(tel)
                        for i, tmp in enumerate(self.plan[tel]):
                            if i == self.next_i[tel] or i == self.current_i[tel]:
                                ob_time = ephem.now()
                                if i == self.current_i[tel]:
                                    if self.ob[tel]["start_time"] and self.ob[tel]["slotTime"]:
                                        t1 = self.time-self.ob[tel]["start_time"]
                                        t2 = self.ob[tel]["slotTime"] - t2
                                        if t2 < 0:
                                            t2 = 0
                                        ob_time = ob_time - t2
                            if "uobi" not in self.plan[tel][i].keys():  # nadaje uobi jak nie ma
                                self.plan[tel][i]["uobi"] = str(uuid.uuid4())[:8]
                            if len(self.plan[tel][i]["uobi"]) < 1:
                                self.plan[tel][i]["uobi"] = str(uuid.uuid4())[:8]
                            if "ra" in self.plan[tel][i].keys():  # liczy aktualna wysokosc na horyzontem
                                ra = self.plan[tel][i]["ra"]
                                dec = self.plan[tel][i]["dec"]
                                az, alt = RaDec2AltAz(self.observatory, ephem.now(), ra, dec)
                                alt = f"{deg_to_decimal_deg(str(alt)):.1f}"
                                az = f"{deg_to_decimal_deg(str(az)):.1f}"
                                self.plan[tel][i]["meta_alt"] = alt
                                self.plan[tel][i]["meta_az"] = az
                            # liczy planowana wysokosc nad horyzontem
                            tmp_ok = False
                            if self.current_i[tel] > -1 and i >= self.current_i[tel]:
                                tmp_ok = True
                            if self.next_i[tel] > -1 and i >= self.next_i[tel]:
                                tmp_ok = True
                            if tmp_ok:
                                self.plan[tel][i]["meta_plan_ut"] = str(ephem.Date(ob_time))
                                if "wait" in self.plan[tel][i].keys():
                                    if len(self.plan[tel][i]["wait"]) > 0:
                                        ob_time = ob_time + ephem.second * float(self.plan[tel][i]["wait"])
                                if "wait_ut" in self.plan[tel][i].keys():
                                    if len(self.plan[tel][i]["wait_ut"]) > 0:
                                        wait_ut = ephem.Date(str(ephem.Date(ob_time)).split()[0] + " " + self.plan[tel][i]["wait_ut"])
                                        if ephem.Date(ob_time) < ephem.Date(wait_ut):
                                            ob_time = wait_ut
                                if "wait_sunset" in self.plan[tel][i].keys():
                                    if len(self.plan[tel][i]["wait_sunset"]) > 0:
                                        oca = ephem.Observer()
                                        oca.date = ephem.now()
                                        oca.lat = self.observatory[0]
                                        oca.lon = self.observatory[1]
                                        oca.elevation = float(self.observatory[2])
                                        oca.horizon = self.plan[tel][i]["wait_sunset"]
                                        wait_ut = oca.next_setting(ephem.Sun(), use_center=True)
                                        if ob_time < wait_ut:
                                            ob_time = wait_ut
                                if "wait_sunrise" in self.plan[tel][i].keys():
                                    if len(self.plan[tel][i]["wait_sunrise"]) > 0:
                                        oca = ephem.Observer()
                                        oca.date = ephem.now()
                                        oca.lat = self.observatory[0]
                                        oca.lon = self.observatory[1]
                                        oca.elevation = float(self.observatory[2])
                                        oca.horizon = self.plan[tel][i]["wait_sunrise"]
                                        wait_ut = oca.next_rising(ephem.Sun(), use_center=True)
                                        if ob_time < wait_ut:
                                            ob_time = wait_ut
                                if "ra" in self.plan[tel][i].keys():
                                    ra = self.plan[tel][i]["ra"]
                                    dec = self.plan[tel][i]["dec"]
                                    az, alt = RaDec2AltAz(self.observatory, ob_time, ra, dec)
                                    alt = f"{deg_to_decimal_deg(str(alt)):.1f}"
                                    az = f"{deg_to_decimal_deg((str(az))):.1f}"
                                    self.plan[tel][i]["meta_plan_alt"] = alt
                                    self.plan[tel][i]["meta_plan_az"] = az

                                    self.oca_site.date = ob_time
                                    star = ephem.FixedBody()
                                    star._ra = str(ra)
                                    star._dec = str(dec)
                                    self.plan[tel][i]["skip_alt"] = False
                                    if float(alt) < self.cfg_alt_limits["min"] or float(alt) > self.cfg_alt_limits["max"]:
                                        self.plan[tel][i]["skip_alt"] = True
                                    else:
                                        self.plan[tel][i]["skip_alt"] = False

                                    self.oca_site.horizon = str(self.cfg_alt_limits["min"])
                                    try:
                                        t = self.oca_site.next_setting(star, use_center=True)
                                        if t < ob_time + ephem.second * self.plan[tel][i]["slotTime"]:
                                            self.plan[tel][i]["skip_alt"] = True

                                    except (ephem.NeverUpError, ephem.AlwaysUpError) as e:
                                        pass

                                    self.oca_site.horizon = str(self.cfg_alt_limits["max"] + 1)
                                    try:
                                        t = self.oca_site.next_rising(star, use_center=True)
                                        if t < ob_time + ephem.second * self.plan[tel][i]["slotTime"]:
                                            self.plan[tel][i]["skip_alt"] = True
                                    except (ephem.NeverUpError, ephem.AlwaysUpError) as e:
                                        pass



                                if "slotTime" in self.plan[tel][i].keys():
                                    slotTime = self.plan[tel][i]["slotTime"]
                                    ob_time = ob_time + ephem.second * slotTime

                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 16: {e}')

                try:
                    s = self.nats_toi_plan_status[tel]
                    status = {"current_i":self.current_i[tel],"next_i":self.next_i[tel],"plan":self.plan[tel]}
                    await s.publish(data=status,timeout=10)
                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 15: {e}')

                    self.planGui.update_table()

    def check_next_i(self,tel):
        if self.next_i[tel] > len(self.plan[tel])-1:
            self.next_i[tel] = -1
        else:

            if "skip" in self.plan[tel][self.next_i[tel]].keys():
                if self.plan[tel][self.next_i[tel]]["skip"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i(tel)

            if "skip_alt" in self.plan[tel][self.next_i[tel]].keys():
                if self.plan[tel][self.next_i[tel]]["skip_alt"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i(tel)

            if "ok" in self.plan[tel][self.next_i[tel]].keys():
                if not self.plan[tel][self.next_i[tel]]["ok"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i(tel)

    # focus window
    def update_focus_window(self):
        try:
            if "max_sharpness_focus" in self.nats_focus_status.keys() and "status" in self.nats_focus_status.keys():
                status = self.nats_focus_status["status"]
                if status == "ok":
                    self.focusGui.result_e.setText(f"{int(self.nats_focus_status['max_sharpness_focus'])}")
                    self.focusGui.max_sharp = self.nats_focus_status["max_sharpness_focus"]
                else:
                    self.focusGui.result_e.setText(status)
                    self.focusGui.max_sharp = None

            if "sharpness_values" in self.nats_focus_status.keys() and "focus_values" in self.nats_focus_status.keys():
                focus_values = self.nats_focus_status["focus_values"]
                sharpness_values = self.nats_focus_status["sharpness_values"]
                fit_x = self.nats_focus_status["fit_x"]
                fit_y = self.nats_focus_status["fit_y"]

                self.focusGui.fit_x = fit_x
                self.focusGui.fit_y = fit_y
                self.focusGui.x = focus_values
                self.focusGui.y = sharpness_values

                if "fwhm" in self.nats_focus_status.keys():             # to w zasadzie teraz nie dziala
                    self.focusGui.fwhm = self.nats_focus_status["fwhm"]

            self.focusGui.update()
        except Exception as e:
            logger.warning(f'EXCEPTION 45: {e}')

    def update_focus_log_window(self):
        try:
            txt = ""
            if "time" in self.nats_focus_record.keys():
                txt = f'{self.nats_focus_record["time"]}'
            txt = txt + f'    {self.nats_focus_record["max_sharpness_focus"]:.0f}    {self.nats_focus_record["filter"]}    {self.nats_focus_record["temperature"]}    {self.nats_focus_record["status"]} '
            self.focusGui.log_e.append(txt)
            self.focusGui.log_e.repaint()

        except Exception as e:
            logger.warning(f'EXCEPTION 45a: {e}')


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
        if Path(self.cfg_tel_directory + "last_shoot.fits").is_file():
            hdul = fits.open(self.cfg_tel_directory + "last_shoot.fits")
            self.image = hdul[0].data
        else:
            self.image = await self.ccd.aget_imagearray()
        image = self.image
        image = numpy.asarray(image)
        self.fitsGui.updateImage(image)

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
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            else:
                ok_name=False
                await self.update_log(f'OBJECT NAME required', "WARNING", self.active_tel)
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

            exp=self.instGui.ccd_tab.inst_Dit_e.text()
            ndit=self.instGui.ccd_tab.inst_Ndit_e.text()
            # Sprawdzanie formatu czasu etc.
            try:
                exp=float(exp)
                if exp>=0:
                    ok_exp=True
                    self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            except Exception as e:
                ok_exp=False
                await self.update_log(f'wrong EXP format', "WARNING", self.active_tel)
                self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            try:
                if len(ndit)==0:
                    self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                    ndit=1
                ndit=int(ndit)
                if ndit>0:
                    ok_ndit=True
                    self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            except Exception as e:
                ok_exp=False
                await self.update_log(f'wrong N format', "WARNING", self.active_tel)
                self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            if ok_exp and ok_ndit:
                seq = "1/"+str(self.curent_filter)+"/"+str(exp)
                ok_seq = True

            if ok_name and ok_seq:
                uobi = str(uuid.uuid4())[:8]
                self.ob[self.active_tel]["block"] = f"SNAP {name} seq={seq} dome_follow=off uobi={uobi}"
                self.ob[self.active_tel]["origin"] = "snap"
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
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            else:
                ok_name=False
                await self.update_log(f'OBJECT NAME required', "WARNING", self.active_tel)
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

            if self.instGui.ccd_tab.Select1_r.isChecked():
                exp=self.instGui.ccd_tab.inst_Dit_e.text()
                ndit=self.instGui.ccd_tab.inst_Ndit_e.text()

                # Sprawdzanie formatu czasu etc.
                try:
                    exp=float(exp)
                    if exp>-0.0001:
                        ok_exp=True
                        self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
                except Exception as e:
                    ok_exp=False
                    await self.update_log(f'wrong EXP TIME format', "WARNING", self.active_tel)
                    self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

                try:
                    if len(ndit)==0:
                        self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                        ndit=1
                    ndit=int(ndit)
                    if ndit>0:
                        ok_ndit=True
                        self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
                except Exception as e:
                    ok_exp=False
                    await self.update_log(f'wrong N format', "WARNING", self.active_tel)
                    self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

                if ok_exp and ok_ndit:
                    seq = str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                    ok_seq = True

            if self.instGui.ccd_tab.Select2_r.isChecked():
                seq = self.instGui.ccd_tab.inst_Seq_e.text().strip()

                ok_seq,err = seq_verification(seq,self.filter_list)
                if not ok_seq:
                    await self.update_log(f'wrong SEQ format {err} ', "WARNING", self.active_tel)
                    self.instGui.ccd_tab.inst_Seq_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                else:
                    self.instGui.ccd_tab.inst_Seq_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")

            if ok_name and ok_seq:

                if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==0:
                    txt = f"OBJECT {name} seq={seq} dome_follow=off "

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
                uobi = str(uuid.uuid4())[:8]
                self.ob[self.active_tel]["block"] = txt + f' uobi={uobi}'
                self.ob[self.active_tel]["origin"] = "manual"
                self.planrunner_start(self.active_tel)
                await self.update_log(f'starting planrunner', "TOI RESPONDER", self.active_tel)

        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_stopExp(self):
        await self.update_log(f'exposure STOP', "OPERATOR", self.active_tel)
        if True:

            await self.takeControl()
            self.ob_progress[self.active_tel]["dit_start"]=0

            try:
                data = self.ob_progress[self.active_tel]
                await self.nats_toi_ob_status[self.active_tel].publish(data=data, timeout=10)
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 40: {e}')

            self.ob[self.active_tel]["run"]=False
            try:
                await self.planrunners[self.active_tel].astop_nightplan()
                await self.update_log(f'stopping program', "TOI RESPONDER", self.active_tel)
            except Exception as e:
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

            self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
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
            gain = self.cfg_inst_gain_i[i]
            self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
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
           rm = self.cfg_inst_rm_i[i]
           if True:
               await self.ccd.aput_readoutmode(rm)
               await self.update_log(f'setting read mode {rm}', "TOI RESPONDER", self.active_tel)
               self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    @qs.asyncSlot()
    async def ccd_setTemp(self):
        await self.update_log(f'set CCD temperature', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            temp=float(self.instGui.ccd_tab.inst_setTemp_e.text())
            if temp>-81 and temp<20:
                await self.ccd.aput_setccdtemperature(temp)
                await self.update_log(f'setting CCD temperature {temp}', "TOI RESPONDER", self.active_tel)
            else:
                await self.update_log(f'Value of CCD temp. not allowed', "WARNING", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_coolerOnOf(self):
        await self.update_log(f'ccd cooler ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if self.ccd.cooleron:
              txt="REQUEST: CCD cooler OFF"
              await self.update_log(f'setting cooler OFF', "TOI RESPONDER", self.active_tel)
            else:
              await self.ccd.aput_cooleron(True)
              await self.update_log(f'setting cooler ON', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            await self.ccd_update(True)

    async def ccd_cooler_update(self, event):
        self.ccd_cooler = await  self.ccd.aget_cooleron()
        if self.ccd_cooler != None:
            self.instGui.ccd_tab.cooler_c.setChecked(self.ccd_cooler)

    async def ccd_current_temp_update(self, event):
        self.ccd_temp = await  self.ccd.aget_ccdtemperature()
        await self.ccd_temp_update()

    async def ccd_set_temp_update(self, event):
        self.ccd_temp_set = await self.ccd.aget_setccdtemperature()
        await self.ccd_temp_update()

    async def ccd_temp_update(self):
        if self.ccd_temp and self.ccd_temp_set:
            ccd_temp=self.ccd_temp
            if ccd_temp: txt = f" {ccd_temp:.1f} /"
            else: txt = " -- /"
            if self.ccd_temp_set: txt = txt +  f" {self.ccd_temp_set:.1f}"
            else: txt = txt + " -- "
            self.instGui.ccd_tab.inst_ccdTemp_e.setText(txt)
            if self.ccd_temp:
                if float(ccd_temp) > self.cfg_inst_defSetUp["temp"]:
                    self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(204,0,0)")
                else: self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(0,150,0)")


    async def ccd_gain_update(self, event):
        self.ccd_gain = await  self.ccd.aget_gain()
        self.ccd_gain = self.ccd.gain
        if self.ccd_gain != None:
            try:
                i = int(self.ccd_gain)
                i = self.cfg_inst_gain_i.index(str(i))
                txt = self.cfg_inst_gain[i]
                self.instGui.ccd_tab.inst_gain_e.setText(txt)
                if self.cfg_inst_defSetUp["gain"] in txt:
                    self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                else: self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")
            except Exception as e: pass

    async def ccd_rm_update(self, event):
        self.ccd_readoutmode = await self.ccd.aget_readoutmode()
        # READ MODES

        if self.ccd_readoutmode != None:
            i = int(self.ccd_readoutmode)
            i = self.cfg_inst_rm_i.index(str(i))
            txt = self.cfg_inst_rm[i]
            self.ccd_readmode=txt
            self.instGui.ccd_tab.inst_read_e.setText(txt)
            if self.cfg_inst_defSetUp["rm"] in txt:
                self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            else: self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")



    async def ccd_binx_update(self, event):
        self.ccd_binx = await  self.ccd.aget_binx()
        await self.ccd_bin_update()

    async def ccd_biny_update(self, event):
        self.ccd_biny = await  self.ccd.aget_biny()
        await self.ccd_bin_update()

    async def ccd_bin_update(self):
        if self.ccd_binx and self.ccd_biny:
            txt=f"{self.ccd_binx}x{self.ccd_biny}"
            self.instGui.ccd_tab.inst_Bin_e.setText(txt)
            if txt == self.cfg_inst_defSetUp["bin"]:
                self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            else: self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")

    async def ccd_update(self, event):
        self.ccd_state = await  self.ccd.aget_camerastate()

    async def ccd_con_update(self, event):
        self.inst_con = self.ccd.connected


    # ############ MOUNT ##################################

    async def mount_con_update(self, event):
        self.mount_con =self.mount.connected

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
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False

           if self.mount_motortatus:
               self.mntGui.mntMotors_c.setChecked(True)
           else:
               self.mntGui.mntMotors_c.setChecked(False)
           await self.mount_update()

           #self.mntGui.mntStat_e.setText(txt)
           #self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")

    @qs.asyncSlot()
    async def covers_openOrClose(self):
        await self.update_log(f'mirror covers ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           self.cover_status = self.cover.coverstate
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
           self.cover_status = await self.cover.aget_coverstate()

           if self.cover_status==3:
               self.mntGui.telCovers_c.setChecked(True)
               txt="OPEN"
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
           elif self.cover_status==1:
               self.mntGui.telCovers_c.setChecked(False)
               txt="CLOSED"
               self.mntGui.telCovers_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
           elif self.cover_status==2:
               txt="MOVING"
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(255, 165, 0); background-color: rgb(233, 233, 233);")
           else:
               txt="UNKNOWN"
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(233, 0, 0); background-color: rgb(233, 233, 233);")

           self.mntGui.telCovers_e.setText(txt)
           if self.skyGui.skyView:
               self.skyGui.skyView.updateMount()
           #self.obsGui.main_form.skyView.updateMount()

    @qs.asyncSlot()
    async def park_mount(self):
        await self.update_log(f'mount PARK', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if self.mount.motorstatus != "false":
                #self.mntGui.mntStat_e.setText(txt)
                self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
                self.mntGui.domeAuto_c.setChecked(False)
                await self.domeFollow()
                await self.mount.aput_park()
                await self.dome.aput_slewtoazimuth(180.)
                await self.update_log(f'parking', "TOI RESPONDER", self.active_tel)
            else:
                txt = "WARNING: Motors are OFF"
                self.WarningWindow(txt)
                await self.update_log(f'Motors are OFF', "WARNING", self.active_tel)


        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def abort_slew(self):
        await self.update_log(f'mount slew ABORT', "OPERATOR", self.active_tel)
        if True:
            await self.takeControl()
            await self.mount.aput_abortslew()
            await self.mount.aput_tracking(False)
            await self.update_log(f'aborting mount slew', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def mount_slew(self):
        await self.update_log(f'mount SLEW', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if self.mount.motorstatus != "false":
                self.req_ra=""
                self.req_dec=""
                self.req_epoq=""
                if self.nextOB_ok:
                    await self.mount.aput_unpark()

                    if self.mntGui.setAltAz_r.isChecked():
                       az=float(self.mntGui.nextAz_e.text())
                       alt=float(self.mntGui.nextAlt_e.text())
                       await self.mount.aput_slewtoaltaz_async(az,alt)
                       await self.update_log(f'slewing to alt az {alt} {az}', "TOI RESPONDER", self.active_tel)

                    elif self.mntGui.setEq_r.isChecked():
                       ra = self.mntGui.nextRa_e.text()
                       dec = self.mntGui.nextDec_e.text()
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
                    if self.mntGui.domeAuto_c.isChecked():
                        if self.active_tel == "wk06":
                            side_of_pier = await self.mount.aget_sideofpier()
                            dome_eq_az, info_dict = dome_eq_azimuth(
                                ra=self.mount_ra, dec=self.mount_dec, r_dome=2050, spx=-110, spy=-110,
                                gem=670, side_of_pier=side_of_pier, latitude=-24.598056,
                                longitude=-70.196389, elevation=2817
                            )
                            az = dome_eq_az
                        await self.dome.aput_slewtoazimuth(az)
                        await self.update_log(f'moving dome to {az}', "TOI RESPONDER", self.active_tel)
                else:
                    await self.update_log(f'SLEW not allowed', "WARNING", self.active_tel)
            else:
                await self.update_log(f'motors are OFF', "WARNING", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def mount_trackOnOff(self):
        await self.update_log(f'mount tracking ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
            if await self.mount.aget_motorstatus() != "false":
                self.mount_tracking = await self.mount.aget_tracking()

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
        self.mount_tracking = await self.mount.aget_tracking()
        await self.mount_update()

    async def mount_slewing_update(self, event):
        self.mount_slewing = await self.mount.aget_slewing()
        await self.mount_update()

    async def mount_update(self):
        if not self.mount_motortatus:
            txt = "SLEWING, TRACKING"
            self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
        elif self.mount_slewing and self.mount_tracking:
            txt="SLEWING, TRACKING"
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
            self.mntGui.tracking_c.setChecked(True)
        elif self.mount_slewing:
            txt="SLEWING"
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        elif self.mount_tracking:
            txt="TRACKING"
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
            self.mntGui.tracking_c.setChecked(True)
        else:
            txt="IDLE"
            self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
            self.mntGui.tracking_c.setChecked(False)
        self.mntGui.mntStat_e.setText(txt)
        #self.obsGui.main_form.skyView.updateMount()
        if self.skyGui.skyView:
            self.skyGui.skyView.updateMount()

        if self.mount_slewing:
            self.mntGui.mntAz_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntAlt_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntRa_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntDec_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.guider_passive_dx=[]
            self.guider_passive_dy=[]
        else:
            self.mntGui.mntAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntRa_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

    async def ra_update(self, event):
        self.mount_ra = await self.mount.aget_ra()
        await self.radec_update()

    async def dec_update(self, event):
        self.mount_dec = await self.mount.aget_dec()
        await self.radec_update()

    async def alt_update(self, event):
        self.mount_alt = await self.mount.aget_alt()
        await self.radec_update()

    async def az_update(self, event):
        self.mount_az = await self.mount.aget_az()
        await self.radec_update()


    async def radec_update(self):
        if  self.mount_ra and self.mount_dec:
            self.mntGui.mntRa_e.setText(to_hourangle_sexagesimal(self.mount_ra))
            self.mntGui.mntDec_e.setText(dec_to_sexagesimal(self.mount_dec))
        if self.mount_alt and self.mount_az:
           self.mntGui.mntAlt_e.setText(f"{self.mount_alt:.3f}")
           self.mntGui.mntAz_e.setText(f"{self.mount_az:.3f}")
           #self.obsGui.main_form.skyView.updateMount()
           if self.skyGui.skyView:
               self.skyGui.skyView.updateMount()
           airmass = calc_airmass(float(self.mount_alt))
           if airmass:
               self.mntGui.mntAirmass_e.setText("%.1f" % airmass)
           else:
               self.mntGui.mntAirmass_e.setText("")

    def target_changed(self):
        self.mntGui.target_e.setStyleSheet("background-color: rgb(234, 245, 249); color: black;")
    def target_provided(self):
        target = self.mntGui.target_e.text()
        try:
            name,ra,dec = target.split()[0],target.split()[1],target.split()[2]
            self.mntGui.nextRa_e.setText(ra)
            self.mntGui.nextDec_e.setText(dec)
            self.instGui.ccd_tab.inst_object_e.setText(name)
            self.mntGui.setEq_r.setChecked(True)
            self.mntGui.updateNextRaDec()
        except IndexError: pass
        self.mntGui.target_e.setStyleSheet("background-color: white; color: black;")

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

    # ################# DOME ########################

    async def dome_con_update(self, event):
        self.dome_con =self.dome.connected


    @qs.asyncSlot()
    async def dome_openOrClose(self):
        await self.update_log(f'dome OPEN/CLOSE', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           if self.cover.coverstate == 1:
               if self.dome_shutterstatus==0:
                  await self.dome.aput_closeshutter()
                  await self.update_log(f'closing dome', "TOI RESPONDER", self.active_tel)
               elif self.dome_shutterstatus==1:
                  await self.dome.aput_openshutter()
                  await self.update_log(f'opening dome', "TOI RESPONDER", self.active_tel)
               else:
                   pass
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
        if True: #self.user.current_user["name"]==self.myself:
           await self.takeControl()
           await self.dome.aput_abortslew()
           await self.update_log(f'stopping dome', "TOI RESPONDER", self.active_tel)


    @qs.asyncSlot()
    async def domeFollow(self):
        pass
        # if self.tel_acces[self.active_tel]:
        #     self.toi_status["dome_follow_switch"] = self.mntGui.domeAuto_c.isChecked()
        #     try:
        #         s = self.nats_pub_toi_status[self.active_tel]
        #         data = self.toi_status
        #         await s.publish(data=data, timeout=10)
        #     except Exception as e:
        #         logger.warning(f'TOI: EXCEPTION 41: {e}')
        # else:
        #     txt="WARNING: U don't have control"
        #     self.WarningWindow(txt)
        #     if self.mntGui.domeAuto_c.isChecked():
        #         self.mntGui.domeAuto_c.setChecked(False)
        #     else:
        #         self.mntGui.domeAuto_c.setChecked(True)

    async def domeShutterStatus_update(self, event):
           self.dome_shutterstatus=await self.dome.aget_shutterstatus()
           if self.dome_shutterstatus==0:
              txt="OPEN"
              self.mntGui.domeShutter_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
              self.mntGui.domeShutter_c.setChecked(True)
              #self.obsGui.main_form.skyView.updateDome()

           elif self.dome_shutterstatus==1:
                txt="CLOSED"
                self.mntGui.domeShutter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                self.mntGui.domeShutter_c.setChecked(False)
                #self.obsGui.main_form.skyView.updateDome()

           elif self.dome_shutterstatus==2:
                txt="OPENING"
                self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                #self.obsGui.main_form.skyView.updateDome()


           elif self.dome_shutterstatus==3:
                txt="CLOSING"
                self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                #self.obsGui.main_form.skyView.updateDome()

           else:
                txt="UNKNOWN"
                self.mntGui.domeShutter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                #self.obsGui.main_form.skyView.updateDome()
           if self.skyGui.skyView:
               self.skyGui.skyView.updateDome()
           self.mntGui.domeShutter_e.setText(txt)

    async def domeStatus_update(self, event):
        self.dome_status=await self.dome.aget_slewing()
        if self.dome_status==False:
            txt="STOPPED"
            self.mntGui.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.domeAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        elif self.dome_status==True:
            txt="MOVING"
            self.mntGui.domeStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
            self.mntGui.domeAz_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")

        else: txt="UNKNOWN"
        self.mntGui.domeStat_e.setText(txt)

    async def domeAZ_update(self, event):
        self.dome_az = await self.dome.aget_az()
        if self.dome_az:
            self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
            #self.obsGui.main_form.skyView.updateDome()
            if self.skyGui.skyView:
                self.skyGui.skyView.updateDome()

    def domeAZ_check(self, event):
        self.dome_next_az_ok = False
        dome_next_az = self.mntGui.domeNextAz_e.text()
        try:
            dome_next_az = float(dome_next_az)
            if dome_next_az <= 360. and dome_next_az >= 0: self.dome_next_az_ok = True
        except ValueError: self.dome_next_az_ok = False
        if dome_next_az == None or dome_next_az == "": self.dome_next_az_ok = None
        if self.dome_next_az_ok or self.dome_next_az_ok == None : self.mntGui.domeNextAz_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
        else: self.mntGui.domeNextAz_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")


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
        r = await self.dome.aget_dome_fans_running()
        if r:
            self.dome_fanStatus=True
        else:
            self.dome_fanStatus=False

        if self.dome_fanStatus:
            self.mntGui.ventilators_c.setChecked(True)
            if self.tel_acces[self.active_tel]:
                self.toi_op_status["dome_ventilators"]["state"] = True
                await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
            txt="VENT ON"
        else:
            self.mntGui.ventilators_c.setChecked(False)
            if self.tel_acces[self.active_tel]:
                self.toi_op_status["dome_ventilators"]["state"] = False
                await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
            txt="VENT OFF"
        self.mntGui.ventilators_e.setText(txt)
        self.mntGui.ventilators_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")

    # OTHER COMPONENTS

    @qs.asyncSlot()
    async def mirrorFansOnOff(self):
        await self.update_log(f'mirror fans ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False
           if self.dome_fanStatus:
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
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False

           if self.dome_fanStatus:
               self.mntGui.mirrorFans_c.setChecked(True)
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status["mirror_fans"]["state"] = True
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
               txt="FANS ON"
           else:
               self.mntGui.mirrorFans_c.setChecked(False)
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status["mirror_fans"]["state"] = False
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
               txt="FANS OFF"
           self.mntGui.mirrorFans_e.setText(txt)
           self.mntGui.mirrorFans_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")


    @qs.asyncSlot()
    async def FlatLampOnOff(self):
        await self.update_log(f'flat lamps ON/OFF', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:

           if self.mntGui.flatLights_c.isChecked():
               await self.mount.aput_domelamp_on()
               await self.update_log(f'turning flat lamps ON', "TOI RESPONDER", self.active_tel)
               self.mntGui.flatLights_e.setText("no feedback")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status["flat_lamps"]["state"] = True
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
           else:
               await self.mount.aput_domelamp_off()
               await self.update_log(f'turning flat lamps OFF', "TOI RESPONDER", self.active_tel)
               self.mntGui.flatLights_e.setText("")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(0,0,0); background-color: rgb(233, 233, 233);")
               if self.tel_acces[self.active_tel]:
                   self.toi_op_status["flat_lamps"]["state"] = False
                   await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)
            if self.mntGui.flatLights_c.isChecked(): self.mntGui.flatLights_c.setChecked(False)
            else: self.mntGui.flatLights_c.setChecked(True)

    @qs.asyncSlot()
    async def domeLightOnOff(self):
        if self.tel_acces[self.active_tel]:
            if self.mntGui.domeLights_c.isChecked():
                val = str(hex(int(255))).replace('0x', '', 1)
                if len(val) == 1:
                    val = '0' + val
                requests.post('http://' + self.local_cfg[self.active_tel]["light_ip"] + '/api/rgbw/set', json={"rgbw": {"desiredColor": val}})
                if self.tel_acces[self.active_tel]:
                    self.toi_op_status["dome_lights"]["state"] = True
                    await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
            else:
                val = str(hex(int(0))).replace('0x', '', 1)
                if len(val) == 1:
                    val = '0' + val
                requests.post('http://' + self.local_cfg[self.active_tel]["light_ip"] + '/api/rgbw/set', json={"rgbw": {"desiredColor": val}})
                if self.tel_acces[self.active_tel]:
                    self.toi_op_status["dome_lights"]["state"] = False
                    await self.nats_pub_toi_status[self.active_tel].publish(data=self.toi_op_status, timeout=10)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)


    def update_dome_temp(self):
        try:
            temp = self.sensors[self.active_tel]["dome_conditions"]["temperature"]
            if temp:
                self.mntGui.domeTemp_e.setText(str(temp))
        except Exception as e:
            pass


    # ############ FOCUS ##################################

    async def focus_con_update(self, event):
        self.focus_con = self.focus.connected

    @qs.asyncSlot()
    async def set_focus(self):
        await self.update_log(f'SET focus', "OPERATOR", self.active_tel)
        if self.tel_acces[self.active_tel]:
           self.focus_editing=False
           self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(255, 255, 255);")
           val=self.mntGui.setFocus_s.value()
           await self.focus.aput_move(val)
           await self.update_log(f'setting focus to {val}', "TOI RESPONDER", self.active_tel)
        else:
            txt="WARNING: U don't have control"
            self.WarningWindow(txt)

    def focusClicked(self, event):
        self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(234, 245, 249);")
        self.focus_editing=True

    async def focus_update(self, event):
        self.focus_value = await self.focus.aget_position()
        self.focus_moving = await self.focus.aget_ismoving()

        if self.focus_value != None:
            self.mntGui.telFocus_e.setText(str(self.focus_value))
            if self.focus_moving != None:
                if self.focus_moving:
                    self.mntGui.telFocus_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
                else:
                    self.mntGui.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        else:
            self.mntGui.telFocus_e.setText(f"ERROR")
            self.mntGui.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(150, 0, 0);")

        if not self.focus_editing:
           self.mntGui.setFocus_s.valueChanged.disconnect(self.focusClicked)
           self.mntGui.setFocus_s.setValue(int(self.focus_value))
           self.mntGui.setFocus_s.valueChanged.connect(self.focusClicked)

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
            pos = int(await self.fw.aget_position())
            self.curent_filter=self.filter_list[pos]
            if pos == -1: filtr = "--"
            else: filtr = self.filter_list[pos]
            self.mntGui.telFilter_e.setText(filtr)
            self.filter = filtr

            if int(self.fw.position) == -1:
                self.mntGui.telFilter_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            else: self.mntGui.telFilter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")


    # ############### ROTATOR #####################

    async def rotator_con_update(self, event):
        self.rotator_con=self.rotator.connected


    async def rotator_update(self, event):
        self.rotator_pos = self.rotator.position
        self.rotator_moving = self.rotator.ismoving
        if self.rotator_pos != None:
            self.mntGui.telRotator1_e.setText(f"{self.rotator_pos:.2f}")
            if self.rotator_moving != None:
                if self.rotator_moving:
                    self.mntGui.telRotator1_e.setStyleSheet("background-color: rgb(234, 245, 249); color: black;")
                    try:
                        diff = self.rotator_pos_prev - self.rotator_pos
                        if diff > 1:
                            self.mntGui.telRotator1_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
                    except AttributeError: pass
                else:
                    self.mntGui.telRotator1_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        else:
            self.mntGui.telRotator1_e.setText(f"ERROR")
            self.mntGui.telRotator1_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(150, 0, 0);")
        self.rotator_pos_prev = self.rotator_pos

        # ############ TELESCOPE #########################

    @qs.asyncSlot()
    async def EmStop(self):
        await self.update_log(f'EMERGENCY STOP', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            self.mntGui.domeAuto_c.setChecked(False)
            await self.tic_telescopes[self.active_tel].emergency_stop()
            await self.update_log(f'EMERGENCY STOP', "TOI RESPONDER", self.active_tel)

        else:
            txt = f"REQUEST: emergency stop but no telescope is selected"


    @qs.asyncSlot()
    async def ping(self):
        await self.update_log(f'send annoying PING', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            try:
                data = {"tel": self.active_tel, "info": "PING"}
                await self.nats_pub_toi_message[self.active_tel].publish(data=data, timeout=10)
                await self.update_log(f'sending annoying PING', "TOI RESPONDER", self.active_tel)

            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 43: {e}')
        else:
            txt = f"WARNING: telescope PING but telescope is not selected"

    @qs.asyncSlot()
    async def shutdown(self):
        await self.update_log(f'SHUTDOWN', "OPERATOR", self.active_tel)
        if self.telescope is not None:
            if self.tel_acces[self.active_tel]:
                self.mntGui.domeAuto_c.setChecked(False)
                await self.dome.aput_slewtoazimuth(180.)
                await self.tic_telescopes[self.active_tel].shutdown()
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
                await self.tic_telescopes[self.active_tel].weather_stop()
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
        except Exception as e:
            pass
        try:
            await self.user.aput_take_control(84000)
            self.upload_plan()
            self.update_plan(self.active_tel)
        except Exception as e:
            pass


# ############ INNE ##############################

    # STAGE 2
    # to nie bedzie na razie obslugiwane
    def GuiderPassiveOnOff(self):
        if self.guiderGui.guiderView.guiderCameraOn_c.checkState():
            self.guider_failed = 1
            self.guider_passive_dx = []
            self.guider_passive_dy = []

    def updateWeather(self):
        try:
            self.obsGui.main_form.wind_e.setText(f"{self.telemetry_wind:.1f} [m/s]")
            self.obsGui.main_form.windDir_e.setText(f"{self.telemetry_wind_direction:.0f} [deg]")
            self.obsGui.main_form.temp_e.setText(f"{self.telemetry_temp:.1f} [C]")
            self.obsGui.main_form.hummidity_e.setText(f"{self.telemetry_humidity:.0f} [%]")
            #self.obsGui.main_form.pressure_e.setText(f"{self.telemetry_pressure:.1f} [hPa]")

            if float(self.telemetry_wind) > float(self.cfg_wind_limit_pointing):
                self.obsGui.main_form.wind_e.setStyleSheet("color: rgb(0, 0, 0); background-color: rgb(255, 140, 0);")
                self.obsGui.main_form.windDir_e.setStyleSheet("color: rgb(0, 0, 0); background-color: rgb(255, 140, 0);")
            elif float(self.telemetry_wind) > float(self.cfg_wind_limit):
                self.obsGui.main_form.wind_e.setStyleSheet("color: rgb(0, 0, 0); background-color: red;")
                self.obsGui.main_form.windDir_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")
            else:
                self.obsGui.main_form.wind_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")
                self.obsGui.main_form.windDir_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")

            if float(self.telemetry_humidity)> float(self.cfg_humidity_limit):
                self.obsGui.main_form.hummidity_e.setStyleSheet("color: rgb(0, 0, 0); background-color: red;")
            else:
                self.obsGui.main_form.hummidity_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")

            if float(self.telemetry_temp) < -1:
                self.obsGui.main_form.temp_e.setStyleSheet("color: rgb(0, 0, 0); background-color: red;")
            else:
                self.obsGui.main_form.temp_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")


            #self.obsGui.main_form.skyView.updateWind(self)
            if self.skyGui.skyView:
                self.skyGui.skyView.updateWind(self)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: updateWeather: {e}')

    def ephem_update(self,tmp):
        self.ephem_utc = float(self.ephemeris.utc)

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
                print("LOG: no acces! ", txt)


        except Exception as e:
            print(f"TOI EXCEPTION (update_log): {e}")


    @qs.asyncSlot()
    async def msg(self, txt, color):
        c = QtCore.Qt.black
        if "yellow" in color: c = QtCore.Qt.darkYellow
        if "green" in color: c = QtCore.Qt.darkGreen
        if "red" in color: c = QtCore.Qt.darkRed
        self.obsGui.main_form.msg_e.setTextColor(c)
        ut = str(self.ut).split()[1].split(":")[0] + ":" + str(self.ut).split()[1].split(":")[1]

    def update_oca(self):
        self.obsGui.main_form.update_table()


    def reset_ob(self,tel):
        templeate = {"run":False,"done":False,"uobi":None,"origin":None,"slot_time":None,"start_time":None,"continue_plan":False}
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
            except KeyError:
                tmp = None
            self.nats_cfg[k]["color"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["min_alt"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["min_alt"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["max_alt"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["max_alt"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["mount"]["obs_min_alt"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["low_alt"] = tmp


            try:
                tmp = nats_cfg[k]["observatory"]["components"]["camera"]["operation_temperature"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["ccd_temp"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["camera"]["pixel_scale"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["pixel_scale"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["filterwheel"]["filters"]
                tmp_n = [item["name"] for item in sorted(tmp, key=lambda x: x["position"])]
                tmp_i= [item["position"]  for item in sorted(tmp, key=lambda x: x["position"])]
            except KeyError:
                tmp_n = None
            self.nats_cfg[k]["filter_list_names"] = tmp_n
            self.nats_cfg[k]["filter_list"] = tmp_i

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["camera"]["gain_modes"]
                tmp_n = [f'{tmp[i].get("gain","--")} ({tmp[i]["name"]})' for i in sorted(tmp.keys())]
                tmp_i = [i for i in sorted(tmp.keys())]
            except KeyError:
                tmp_n = None
            self.nats_cfg[k]["gain_list_names"] = tmp_n
            self.nats_cfg[k]["gain_list"] = tmp_i

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["camera"]["readout_modes"]
                tmp_n = [tmp[i]["name"] for i in sorted(tmp.keys())]
                tmp_i = [i for i in sorted(tmp.keys())]
            except KeyError:
                tmp_n = None
            self.nats_cfg[k]["rm_list_names"] = tmp_n    # sa rozdzielone nazwy i numer, bo wartosc do put moze byc z dupy
            self.nats_cfg[k]["rm_list"] = tmp_i

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["focuser"]["default_position"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["focus_def_pos"] = tmp

            try:
                tmp = nats_cfg[k]["observatory"]["components"]["focuser"]["default_step"]
            except KeyError:
                tmp = None
            self.nats_cfg[k]["focus_def_step"] = tmp

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

        self.toi_op_status = {"dome_ventilators":{"state":False,"defoult":False}, "mirror_fans":{"state":False,"defoult":False},"flat_lamps":{"state":False,"defoult":False},"dome_lights":{"state":False,"defoult":False}}

        self.cfg_showRotator = True   # potrzebne do pierwszego wyswietlenia
        self.tel_alpaca_con = False

        self.catalog_file = None

        self.cfg_inst_obstype = []
        self.cfg_inst_mode = []
        self.cfg_inst_bins = []
        self.cfg_inst_subraster = []

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
        self.overhed = 10

        self.nextOB_ok = None
        self.flag_newimage = None
        self.image = []
        self.prev_image = []

        # observer
        self.observer = ""

        # weather telemetry
        self.telemetry_temp = None
        self.telemetry_wind = None
        self.telemetry_wind_direction = None
        self.telemetry_humidity = None
        self.telemetry_pressure = None

        # aux zmienne
        #self.exp_prog_status = {"plan_runner_status":"","ndit_req":1,"ndit":0,"dit_exp":0,"dit_start":0}

        self.log_record = {t:"" for t in self.local_cfg["toi"]["telescopes"]}

        self.fits_ffs_data = {t:[] for t in self.local_cfg["toi"]["telescopes"]}

        templeate = {"ob_started":False,"ob_done":False,"ob_expected_time":None,"ob_start_time":None,"ob_program":None,"error":False,"status":"","ndit_req":None,"ndit":None,"dit_exp":None,"dit_start":None}
        self.ob_progress = {t:copy.deepcopy(templeate) for t in self.local_cfg["toi"]["telescopes"]}


        self.ob = {}
        for t in self.local_cfg["toi"]["telescopes"]:
            self.reset_ob(t)

        self.nats_plan_status = {"current_i":-1,"next_i":-1,"plan":[]}

        #self.nats_exp_prog_status = {}  # ten sluzy tylko do czytania z nats
        self.nats_ob_progress = {}      # ten sluzy tylko do czytania z nats
        self.nats_focus_status = {}     #  tak samo
        self.nats_focus_record = {}     # tak samo

        #self.fits_exec=False

        self.autofocus_started={k:False for k in self.local_cfg["toi"]["telescopes"]}
        self.last_focus_position={k:None for k in self.local_cfg["toi"]["telescopes"]}

        self.acces=True


        # plan

        self.plan = {k:[] for k in self.local_cfg["toi"]["telescopes"]}
        self.done_uobi = []
        self.next_i = {k:0 for k in self.local_cfg["toi"]["telescopes"]}
        self.current_i = {k:-1 for k in self.local_cfg["toi"]["telescopes"]}

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15"]  # wg25 is not working
        self.obs_tel_in_table = self.obs_tel_tic_names

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
        self.cfg_inst_temp = None
        self.cfg_inst_gain = None
        self.cfg_inst_rm = None
        self.ccd_temp_set = None
        self.ccd_temp = None

        # filter wheel
        self.filter = None
        self.filter_list = None

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
        self.pulseRa = 0
        self.pulseDec = 0
        self.cover_status = None


        # focus
        self.focus_editing=False
        self.focus_value=0

        # rotator
        self.rotator_pos="unknown"

        # program
        self.req_ra = ""
        self.req_dec = ""
        self.req_epoch = ""
        self.program_id = ""
        #self.program_name = ""

        # log wykonanych ob z planrunnera z NATS
        self.ob_log = []

        self.tmp_i = 1

        self.nats_toi_plan_status = {}
        self.nats_toi_ob_status = {}
        #self.nats_toi_exp_status = {}

        self.nats_toi_flat_status = {}
        self.nats_toi_focus_status = {}
        self.nats_toi_focus_record = {}

        self.nats_toi_plan_log = {}
        self.nats_pub_toi_status = {}
        self.nats_toi_log = {}
        self.nats_pub_toi_message = {}

        self.planrunners = {}
        self.tic_telescopes = {k:self.observatory_model.get_telescope(k) for k in self.local_cfg["toi"]["telescopes"]}

        self.acces_grantors = {k:self.tic_telescopes[k].get_access_grantor() for k in self.local_cfg["toi"]["telescopes"]}
        self.tel_users = {k: None for k in self.local_cfg["toi"]["telescopes"]}
        self.tel_acces = {k: None for k in self.local_cfg["toi"]["telescopes"]}

        self.tel_focusers = {k:self.tic_telescopes[k].get_focuser() for k in self.local_cfg["toi"]["telescopes"]}

    async def on_start_app(self):    # rozczlonkowac ta metoda i wlozyc wszystko do run_qt_app
        #await self.nats_get_config()
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
            #logger.info(f"Connected witch NATS successfully")
        else:
            logger.error(f"Can't connect to NATS {nats_host}:{nats_port} Application stopped!")
            return
    except asyncio.TimeoutError:
        logger.error(f"Can't connect to NATS {nats_host}:{nats_port} timeout accrue. Application stopped!")
        return
    # TODO ernest_nowy_tic COMENT nie powołujemy już 'ClientAPI' ręcznie, Observatory zaciąga konfigurację z nats i tworzy ClientAPI potem
    observatory_model = Observatory(client_name="TOI_Client", config_stream="tic.config.observatory")
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
    try:
        qs.run(run_qt_app())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)


if __name__ == "__main__":
    main()
