#!/usr/bin/env python3

# ----------------
# 1.08.2022
# Marek Gorski
# ----------------
import asyncio
import datetime
import functools
import logging
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
import yaml
from pathlib import Path
from typing import Optional
import qasync as qs
from PyQt5 import QtWidgets, QtCore
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

from aux_gui import AuxGui
from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from calcFocus import calc_focus as calFoc
from ffs_lib.ffs import FFS
from fits_save import *
from instrument_gui import InstrumentGui
from mnt_gui import MntGui
from obs_gui import ObsGui
from plan_gui import PlanGui
from toi_lib import *

# import paho.mqtt.client as mqtt
#from starmatch_lib import StarMatch

# level ustawic w settings
logging.basicConfig(level='INFO') # DEBUG, INFO, WARNING, ERROR
logger = logging.getLogger(__name__)


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
        self.instGui = InstrumentGui(self, loop=self.loop, client_api=self.client_api)
        self.planGui = PlanGui(self, loop=self.loop, client_api=self.client_api)
        self.auxGui = AuxGui(self)

        self.add_background_task(self.tic_con_loop())
        self.add_background_task(self.almanac_loop())
        self.add_background_task(self.alpaca_con_loop())
        self.add_background_task(self.tel_con_loop())
        self.add_background_task(self.tel_progress_loop())

        self.add_background_task(self.guider_loop())

        self.add_background_task(self.TOItimer())
        self.add_background_task(self.nats_weather_loop())

        for t in self.oca_tel_state.keys():   # statusy wszystkich teleskopow
            self.add_background_task(self.oca_telemetry_program_reader(t))
            for k in self.oca_tel_state[t].keys():
                self.add_background_task(self.oca_telemetry_reader(t,k))

        self.obsGui.main_form.update_table()

        # publishery natsow
        # NATS WRITER
        for k in self.local_cfg["toi"]["telescopes"]:
            self.nats_toi_plan_status[k] = get_publisher(f'tic.status.{k}.toi.plan')
            self.nats_toi_ob_status[k] = get_publisher(f'tic.status.{k}.toi.ob')
            self.nats_toi_exp_status[k] = get_publisher(f'tic.status.{k}.toi.exp')

            self.nats_toi_focus_status[k] = get_publisher(f'tic.status.{k}.toi.focus')

            self.nats_pub_toi_status[k] = get_publisher(f'tic.status.{k}.toi.status')

    async def oca_telemetry_reader(self,tel,key):
        try:
            r = get_reader(f'tic.status.{tel}{self.oca_tel_state[tel][key]["pms_topic"]}', deliver_policy='last')
            async for data, meta in r:
                txt = data["measurements"][f"{tel}{self.oca_tel_state[tel][key]['pms_topic']}"]
                self.oca_tel_state[tel][key]["val"] = txt
                self.update_oca()
        except Exception as e:
            logger.warning(f'{e}')

    async def oca_telemetry_program_reader(self,tel):
        try:
            reader = get_reader(f'tic.status.{tel}.toi.ob', deliver_policy='last')
            async for status, meta in reader:
                self.ob_prog_status[tel] = status
                self.update_oca()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise

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
        # TODO ernest_nowy_tic COMENT bez odfiltrowania tych błędów nie zamkniemy taska !!!
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: nats_weather_loop: {e}')


    async def tic_con_loop(self):
        while True:
            self.tic_con = await self.observatory_model.is_tic_server_available()
            if self.tic_con == True:
                self.obsGui.main_form.ticStatus2_l.setText("\u262F  TIC")
                self.obsGui.main_form.ticStatus2_l.setStyleSheet("color: green;")
            else:
                self.obsGui.main_form.ticStatus2_l.setText("\u262F  TIC")
                self.obsGui.main_form.ticStatus2_l.setStyleSheet("color: red;")
            await asyncio.sleep(3)


    #  ############# ZMIANA TELESKOPU ### TELESCOPE SELECT #################
    async def telescope_switched(self):

        self.telescope_switch_status["plan"] = False
        # self.nats_journal_flats_writter = get_journalpublisher(f'tic.journal.{self.active_tel}.log.flats')
        # self.nats_journal_toi_msg = get_journalpublisher(f'tic.journal.{self.active_tel}.toi.signal')


        #subprocess.run(["aplay", self.script_location+"/sounds/spceflow.wav"])
        #subprocess.run(["aplay", self.script_location+"/sounds/romulan_alarm.wav"])

        self.tmp = 0

        self.pulseRa = 0
        self.pulseDec = 0

        self.guider_passive_dx = []
        self.guider_passive_dy = []
        self.guider_failed = 1

        self.flat_record={}
        self.flat_record["go"] = False

        self.ob_log = []

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
        self.cfg_focuser_seq = "8/V/5"

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

            #self.cfg_alt_limits = {"min":0,"max":80,"low":35}

            self.cfg_inst_obstype = ["Science", "Zero", "Dark", "Sky Flat", "Dome Flat"]
            self.cfg_inst_mode = ["Normal", "Sky", "JitterBox", "JitterRandom"]
            self.cfg_inst_bins = ["1x1", "2x2", "1x2", "2x1"]
            self.cfg_inst_subraster = ["No", "Subraster1", "Subraster2", "Subraster3"]

            self.cfg_inst_defSetUp = {"gain": "Gain 2750", "rm": "1MHz","bin":"2x2", "temp":-20}


        # if not none, it means we switch telescope, otherwise we select first time
        if self.telescope is not None:
            # stop method starting subscription if not finished yet, just fo case
            await self.stop_background_methods(group="subscribe")
            # warning this need time to stop, is important only if all application close if we switch to
            # other tel don't worry
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


        # ---------------------- run subscriptions from ocabox ----------------------
        await self.run_method_in_background(self.ephemeris.asubscribe_utc(self.ephem_update,time_of_data_tolerance=0.25),group="subscribe")
        #
        await self.run_method_in_background(self.user.asubscribe_current_user(self.user_update), group="subscribe")
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

        # background task specific for selected telescope
        self.add_background_task(self.nats_log_flat_reader(), group="telescope_task")
        self.add_background_task(self.nats_log_focus_reader(), group="telescope_task")
        self.add_background_task(self.nats_log_toi_reader(), group="telescope_task")

        self.add_background_task(self.nats_log_loop_reader(), group="telescope_task")
        self.add_background_task(self.nats_downloader_reader(), group="telescope_task")

        self.add_background_task(self.nats_toi_plan_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_ob_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_exp_status_reader(), group="telescope_task")
        self.add_background_task(self.nats_toi_focus_status_reader(), group="telescope_task")

        await self.run_background_tasks(group="telescope_task")

        self.mntGui.updateUI()
        self.auxGui.updateUI()
        self.planGui.updateUI()
        self.instGui.updateUI()

        if not bool(self.cfg_showRotator):
            self.mntGui.comRotator1_l.setText("\u2B24")
            self.mntGui.comRotator1_l.setStyleSheet("color: rgb(190,190,190);")
            self.mntGui.telRotator1_l.setStyleSheet("color: rgb(190,190,190);")


        self.updateWeather()

    # ################### METODY POD NATS READERY ##################

    async def nats_log_flat_reader(self):
        reader = get_journalreader(f'tic.journal.{self.active_tel}.log.flats', deliver_policy='last')
        async for data, meta in reader:
            d:JournalEntry = data
            r = d.message

    async def nats_log_focus_reader(self):
        reader = get_journalreader(f'tic.journal.{self.active_tel}.log.focus', deliver_policy='last')
        async for data, meta in reader:
            d:JournalEntry = data
            r = d.message

    async def nats_log_toi_reader(self):
        reader = get_journalreader(f'tic.journal.{self.active_tel}.toi.signal', deliver_policy='last')
        async for data, meta in reader:
            d:JournalEntry = data
            r = d.message

    async def nats_toi_plan_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.plan', deliver_policy='last')
            async for data, meta in reader:
                self.nats_plan_status = data
                self.planGui.update_table()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise


    async def nats_toi_ob_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.ob', deliver_policy='last')
            async for status, meta in reader:
                self.nats_ob_progress = status
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        #except Exception as e:
        #    logger.warning(f'TOI: nats_toi_ob_status_reader: {e}')


    async def nats_toi_exp_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.exp', deliver_policy='last')
            async for data, meta in reader:
                self.nats_exp_prog_status = data
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise

    async def nats_toi_focus_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.focus', deliver_policy='last')
            async for data, meta in reader:
                self.nats_focus_status = data
                #print(self.nats_focus_status)
                self.update_focus_window()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise

    async def nats_toi_status_reader(self):
        try:
            reader = get_reader(f'tic.status.{self.active_tel}.toi.status', deliver_policy='last')
            async for data, meta in reader:
                if "dome_follow_switch" in data.keys():
                    self.toi_status["dome_follow_switch"] = data["dome_follow_switch"]
                    self.mntGui.domeAuto_c.setChecked(self.toi_status["dome_follow_switch"])
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise


    # NATS log plannera
    async def nats_log_loop_reader(self):
        try:
            tel = self.active_tel
            time = datetime.datetime.now() - datetime.timedelta(hours=int(self.local_cfg["toi"]["log_display_h"]))
            r = get_reader(f'tic.status.{tel}.planner.command.log', deliver_policy='by_start_time',opt_start_time=time)
            async for data, meta in r:
                self.ob_log.append(data)
                if "uobi" in data.keys():
                    if data["uobi"] not in self.done_uobi:
                        #self.planGui.done.append(data["uobi"])
                        self.done_uobi.append(data["uobi"])
                self.planGui.update_log_table()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 3: {e}')
        #except Exception as e:
        #    logger.warning(f'TOI: nats_log_loop: {e}')

    # NATS log plannera
    async def nats_downloader_reader(self):
        try:
            tel = self.active_tel
            r = get_reader(f'tic.status.{tel}.download', deliver_policy='last')
            async for data, meta in r:
                self.fits_data = data
                self.new_fits()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: EXCEPTION 4: {e}')
        #except Exception as e:
        #    logger.warning(f'TOI: nats_log_loop: {e}')

    def update_focus_window(self):
        if "max_sharpness_focus" in self.nats_focus_status.keys() and "status" in self.nats_focus_status.keys():
            status = self.nats_focus_status["status"]
            if status == "ok":
                self.auxGui.focus_tab.result_e.setText(f"{int(self.nats_focus_status['max_sharpness_focus'])}")
                self.auxGui.focus_tab.max_sharp = self.nats_focus_status["max_sharpness_focus"]
            else:
                self.auxGui.focus_tab.result_e.setText(status)
                self.auxGui.focus_tab.max_sharp = None


        if "coef" in self.nats_focus_status.keys() and "sharpness_values" in self.nats_focus_status.keys() and "focus_values" in self.nats_focus_status.keys():
            coef = self.nats_focus_status["coef"]
            focus_values = self.nats_focus_status["focus_values"]
            sharpness_values = self.nats_focus_status["sharpness_values"]

            fit_x = numpy.linspace(min(focus_values), max(focus_values), 100)
            if len(coef) > 3:
                fit_y = coef[0] * fit_x ** 4 + coef[1] * fit_x ** 3 + coef[2] * fit_x ** 2 + coef[3] * fit_x + coef[4]
            elif len(coef) > 1:
                fit_y = coef[0] * fit_x ** 2 + coef[1] * fit_x + coef[2]

            self.auxGui.focus_tab.fit_x = fit_x
            self.auxGui.focus_tab.fit_y = fit_y
            self.auxGui.focus_tab.x = focus_values
            self.auxGui.focus_tab.y = sharpness_values

        self.auxGui.focus_tab.update()
        self.auxGui.tabWidget.setCurrentIndex(2)


    # ################### METODY POD SUBSKRYPCJE ##################

    @qs.asyncSlot()
    async def force_update(self):
        await self.user_update(None)
        await self.mountMotors_update(None)
        await self.filter_update(None)
        await self.focus_update(None)
        await self.domeAZ_update(None)
        await self.domeStatus_update(None)
        await self.domeShutterStatus_update(None)
        await self.radec_update(None)
        await self.covers_update(None)
        await self.mirrorFans_update(None)
        await self.ccd_update(None)
        #await self.ccd_bin_update(None)
        await self.ccd_rm_update(None)
        await self.ccd_gain_update(None)
        #await self.ccd_temp_update(None)
        await self.ccd_cooler_update(None)
        #await self.msg("REQUEST: UPDATE DONE", "green")


    # tu sa wszystkie loop-y

    async def alpaca_con_loop(self):
        while True:
            if self.telescope is not None:
                if self.tic_con:
                    tmp = await self.telescope.is_telescope_alpaca_server_available()
                    self.tel_alpaca_con = bool(tmp["alpaca"])
            await asyncio.sleep(3)

    async def almanac_loop(self):
        while True:
            # obsluga Almanacu

            self.time = time.time()

            self.ut = str(ephem.now())
            self.almanac = Almanac(self.observatory)
            self.obsGui.main_form.ojd_e.setText(f"{self.almanac['jd']:.6f}")
            self.obsGui.main_form.sid_e.setText(str(self.almanac["sid"]).split(".")[0])
            date=str(self.almanac["ut"]).split()[0]
            self.date=date.split("/")[2]+"/"+date.split("/")[1]+"/"+date.split("/")[0]
            ut=str(self.almanac["ut"]).split()[1]

            self.obsGui.main_form.date_e.setText(str(self.date))
            self.obsGui.main_form.ut_e.setText(str(ut))
            self.obsGui.main_form.skyView.updateAlmanac()
            #self.obsGui.main_form.skyView.updateRadar()

            await asyncio.sleep(1)

    async def tel_con_loop(self):
        while True:
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

            await asyncio.sleep(3)

    async def tel_progress_loop(self):
        while True:
            # obsluga wyswietlania paskow postepu ekspozycji
            try:
                if "dit_start" in self.nats_exp_prog_status.keys():
                    if self.nats_exp_prog_status["dit_start"] > 0:
                        dt = self.time - self.nats_exp_prog_status["dit_start"]
                        if dt > self.nats_exp_prog_status["dit_exp"]:
                            dt = self.nats_exp_prog_status["dit_exp"]
                            if self.nats_exp_prog_status["plan_runner_status"] == "exposing":
                                txt = "reading: "
                        else:
                            if self.nats_exp_prog_status["plan_runner_status"] == "exposing":
                                txt = "exposing: "
                        if self.nats_exp_prog_status["plan_runner_status"] == "exp done":
                            txt = "DONE "
                        if int(self.nats_exp_prog_status["dit_exp"]) == 0:
                            p = 100
                        else:
                            p = int(100 * (dt / self.nats_exp_prog_status["dit_exp"]))
                        self.instGui.ccd_tab.inst_DitProg_n.setValue(p)
                        txt2 = f"{int(dt)}/{int(self.nats_exp_prog_status['dit_exp'])}"

                        p = int(100 * (self.nats_exp_prog_status["ndit"] / self.nats_exp_prog_status["ndit_req"]))
                        self.instGui.ccd_tab.inst_NditProg_n.setValue(p)
                        txt = txt + f"{int(self.nats_exp_prog_status['ndit'])}/{int(self.nats_exp_prog_status['ndit_req'])}"

                        self.instGui.ccd_tab.inst_NditProg_n.setFormat(txt)
                        self.instGui.ccd_tab.inst_DitProg_n.setFormat(txt2)
                    else:
                        self.instGui.ccd_tab.inst_NditProg_n.setFormat("")
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 8: {e}')

            # obsluga wyswietlania paska postepu OB

            try:
                if "ob_started" in self.nats_ob_progress.keys() and "ob_expected_time" in self.nats_ob_progress.keys():
                    if self.nats_ob_progress["ob_start_time"] and self.nats_ob_progress["ob_expected_time"]:
                        ob_started = bool(self.nats_ob_progress["ob_started"])
                        ob_done = bool(self.nats_ob_progress["ob_done"])
                        ob_start_time = float(self.nats_ob_progress["ob_start_time"])
                        ob_expected_time = float(self.nats_ob_progress["ob_expected_time"])
                        program = self.nats_ob_progress["ob_program"]

                        if ob_started:
                            if True:
                                self.planGui.ob_e.setText(program)
                                self.planGui.ob_e.setCursorPosition(0)

                                t = self.time - ob_start_time
                                p = t / ob_expected_time
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
                        self.planGui.ob_Prog_n.setFormat("")
                        self.planGui.ob_Prog_n.setStyleSheet("background-color: rgb(233, 233, 233)")

            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 6: {e}')
            await asyncio.sleep(1)


    async def nikomu_niepotrzeba_petla_ustawiajaca_pierdoly(self):
        while True:
            await asyncio.sleep(1)
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


    # STAGE2
    # to na razie jest wylaczone
    async def dome_follow_loop(self):
        while True:
            await asyncio.sleep(1)
            # Mechanizm Dome Follow
            if False:
                if self.mntGui.domeAuto_c.isChecked() and await self.user.aget_is_access():
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
                            txt = "Dome AZ corrected"
                        await self.msg(txt, "black")


    # STAGE 2
    async def TOItimer(self):
        while True:

            for t in self.acces_grantors.keys():
                acces = await self.acces_grantors[t].aget_is_access()
                name = await self.acces_grantors[t].aget_current_user()
                self.tel_users[t] = name["name"]
                self.tel_acces[t] = acces
            self.update_oca()

            await asyncio.sleep(1)

            print("* PING")
            # print(self.planrunner.is_nightplan_running(self.program_name))

            # sterowanie wykonywaniem planu
            for tel in self.local_cfg["toi"]["telescopes"]:

                try:

                    try:
                        #DUPA3
                        print(f"{tel} OB: run/done {self.ob[tel]['run']}/{self.ob[tel]['done']}")
                        pr = self.planrunners[tel].is_nightplan_running(self.ob[tel]["origin"])
                        print(f"{tel} PR: {pr}")
                    except:
                        pass

                    if self.telescope:
                        if "continue_plan" in self.ob[tel].keys() and "done" in self.ob[tel].keys() and "origin" in self.ob[tel].keys():

                            if self.ob[tel]["done"] and "plan" in self.ob[tel]["origin"] and self.ob[tel]["continue_plan"]:
                                await self.plan_start(tel)

                            elif "plan" in self.ob[tel]["origin"] and self.ob[tel]["continue_plan"]:

                                if "wait" in self.ob[tel].keys() and "start_time" in self.ob[tel].keys():
                                    if self.ob[tel]["wait"] != "":
                                        dt = self.time - self.ob[tel]["start_time"]
                                        if float(dt) > float(self.ob[tel]["wait"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f"PLAN: {self.ob[tel]['name']} {self.ob[tel]['wait']} s DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)

                                if "wait_ut" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_ut"] != "":
                                        req_ut = str(self.ob[tel]["wait_ut"])
                                        ut = str(self.almanac["ut"]).split()[1]
                                        ut = 3600 * float(ut.split(":")[0]) + 60 * float(ut.split(":")[1]) + float(ut.split(":")[2])
                                        req_ut = 3600 * float(req_ut.split(":")[0]) + 60 * float(req_ut.split(":")[1]) + float(
                                            req_ut.split(":")[2])
                                        if req_ut < ut:
                                            self.ob[tel]["done"] = True
                                            await self.msg(f"PLAN: {self.ob[tel]['name']} UT {self.ob[tel]['wait_ut']} DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)

                                if "wait_sunrise" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_sunrise"] != "":
                                        if deg_to_decimal_deg(self.almanac["sun_alt"]) > float(self.ob[tel]["wait_sunrise"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f"PLAN: {self.ob[tel]['name']} sunrise {self.ob[tel]['wait_sunrise']} DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)

                                if "wait_sunset" in self.ob[tel].keys():
                                    if self.ob[tel]["wait_sunset"] != "":
                                        if deg_to_decimal_deg(self.almanac["sun_alt"]) < float(self.ob[tel]["wait_sunset"]):
                                            self.ob[tel]["done"] = True
                                            await self.msg(f"PLAN: {self.ob[tel]['name']} sunset {self.ob[tel]['wait_sunset']} DONE", "green")

                                            self.next_i[tel] = self.current_i[tel]
                                            self.plan[tel].pop(self.current_i[tel])
                                            self.current_i[tel] = -1
                                            self.update_plan(tel)

                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 98: {e}')

            try:

                self.planGui.update_table()
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 5: {e}')


    async def guider_loop(self):
        while True:
            await asyncio.sleep(1)
            # ############# GUIDER ################
            # to jest brudny algorytm guidera
            #
            if self.telescope is not None:  # if telescope is selected, other component (e.g. dome ...) also. So no check
                try:
                    guider_loop = int(self.auxGui.guider_tab.guiderView.guiderLoop_e.text())
                    method = self.auxGui.guider_tab.guiderView.method_s.currentText()

                    # guider robi sie w petli, co guider_loop robi sie ekspozycja
                    self.tmp_i = self.tmp_i + 1
                    if self.tmp_i > guider_loop:
                        self.tmp_i = 0

                    # tu sie robie ekspozycja
                    if self.tmp_i == 1:
                        exp = float(self.auxGui.guider_tab.guiderView.guiderExp_e.text())
                        if self.auxGui.guider_tab.guiderView.guiderCameraOn_c.checkState():
                            try:
                                await self.guider.aput_startexposure(exp, True)
                            except Exception as e:
                                pass

                    # ######## Analiza obrazu guider
                    # poniewaz nie wiem ile sie czyta kamera, to analiza robi sie tuz przed nastepna ekspozycja
                    # nie ma na razie zabezpieczenia ze petla trwa krocej niz ekspozycja
                    if self.tmp_i == 0 and self.auxGui.guider_tab.guiderView.guiderCameraOn_c.checkState():
                        self.guider_image = await self.guider.aget_imagearray()
                        if self.guider_image:
                            image = self.guider_image
                            image = numpy.asarray(image)
                            self.auxGui.guider_tab.guiderView.updateImage(image)  # wyswietla sie obrazek

                            # tu licza sie podstawowe statystyki obrazka, potrzebne do dalszej analizy
                            stats = FFS(image)
                            th = float(self.auxGui.guider_tab.guiderView.treshold_s.value())
                            fwhm = float(self.auxGui.guider_tab.guiderView.fwhm_s.value())

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
                                self.auxGui.guider_tab.guiderView.updateCoo(x_tmp, y_tmp, color="white")

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
                                    self.auxGui.guider_tab.guiderView.updateCoo(x_matched, y_matched, color="cyan")
                                else:
                                    txt = "multistar failed"
                                self.auxGui.guider_tab.guiderView.result_e.setText(txt)

                            # jak wybralismy metode Singlestar
                            elif method == "Single star":
                                if dx_single != None:
                                    dx = dx_single
                                    dy = dy_single
                                    txt = f"single star\n dx={dx} dy={dy}"
                                    self.auxGui.guider_tab.guiderView.updateCoo([single_x], [single_y], color="magenta")
                                else:
                                    txt = "single star failed"
                                self.auxGui.guider_tab.guiderView.result_e.setText(txt)

                            # jak wybralismy Auto, to najpierw stara sie multistar a
                            # jak sie nie uda to single star
                            elif method == "Auto":
                                if dx_multiStars != None:
                                    dx = dx_multiStars
                                    dy = dy_multiStars
                                    txt = f"Auto (multistar)\n dx={dx} dy={dy}"
                                    self.auxGui.guider_tab.guiderView.updateCoo(x_matched, y_matched, color="cyan")
                                elif dx_single != None:
                                    dx = dx_single
                                    dy = dy_single
                                    txt = f"Auto (single star)\n dx={dx} dy={dy}"
                                    self.auxGui.guider_tab.guiderView.updateCoo([single_x], [single_y], color="magenta")
                                else:
                                    txt = "auto failed"
                                self.auxGui.guider_tab.guiderView.result_e.setText(txt)

                            # tutaj jest lista ostatnich 20 pomiarow, sluzaca
                            # do liczenia kumulatywnego przesuniecia
                            # jak teleskop zrobi slew to sie lista zeruje
                            if dx != None:
                                self.guider_passive_dx.append(dx)
                                self.guider_passive_dy.append(dy)

                            if len(self.guider_passive_dx) > 20:
                                self.guider_passive_dx = self.guider_passive_dx[1:]
                                self.guider_passive_dy = self.guider_passive_dy[1:]

                            self.auxGui.guider_tab.guiderView.update_plot(self.guider_passive_dx, self.guider_passive_dy)

                            # aktualny obrazek staje sie referencyjnym, chyba ze nie udalo znalez sie przesuniecia
                            # wtedy 1 raz tego nie robi (steruje tym guider_failed)
                            if (dx != None and dy != None) or self.guider_failed == 1:
                                self.prev_guider_coo = coo
                                self.prev_guider_adu = adu
                                self.guider_failed = 0
                            else:
                                self.guider_failed = 1

                # TODO ernest_nowy_tic COMENT robiąc w asyncio 'except Exception as e' samo łatwo jest zrobić niezamykający się task dlatego trzeba odfiltrować CONAJMNIEJ 'asyncio.CancelledError, asyncio.TimeoutError' błędy one muszą być rzucone. Robi się tak jak poniżej. Niewiem czy PyQT jakieś urzywa ale do asyncio to te 2
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    raise
                except Exception as e:
                    pass
                    # txt = f"GUIDER FAILED after {status}, {e}"
                    # self.auxGui.guider_tab.guiderView.result_e.setText(txt)



    # ############ PLAN RUNNER START ##########################



    @qs.asyncSlot()
    async def planrunner_start(self,tel):
        self.observer = self.auxGui.welcome_tab.observer_e.text()
        if await self.user.aget_is_access():

            if self.active_tel not in self.planrunners.keys():
                self.planrunners[tel] = self.tic_telescopes[tel].get_observation_plan()
                tmp = self.planrunners[tel]
                self.planrunners[tel].add_info_callback('exec_json', lambda info: self.PlanRunFeedback(tmp, info))

            self.exp_prog_status["ndit"] = 0
            self.exp_prog_status["dit_start"] = 0


            #self.ob_program = self.ob_program + f' observers="{self.observer}"' # zle sie parsuje naraz comment i observers

            program = self.ob[tel]["block"]
            program_name = self.ob[tel]["origin"]

            await self.planrunners[tel].aload_nightplan_string(program_name, string=program, overwrite=True, client_config_dict=self.client_cfg)
            await self.planrunners[tel].arun_nightplan(program_name, step_id="00")

            self.fits_exec = True

    # ############ PLAN RUNNER CALLBACK ##########################

    @qs.asyncSlot()
    async def PlanRunFeedback(self,planrunner,info):

        tel = [k for k,val in self.planrunners.items() if val == planrunner][0]

        for t in self.local_cfg["toi"]["telescopes"]:
            if t==tel:

                # NORMAL PLAN

                if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
                    if info["name"] == "NIGHTPLAN" and info["started"] and not info["done"]:
                        await self.msg("PLAN: Plan started","black")
                        #DUPA2
                        self.ob[tel]["run"] = True     # to swiadczy o tym czy planrunner dziala
                        self.ob[tel]["done"] = False
                        self.ob_start_time = self.time

                        self.ctc.reset_time()
                        self.ctc.set_start_rmode(self.ccd_readoutmode)
                        self.ctc.set_telescope_start_az_alt(az=self.mount_az, alt=self.mount_alt)
                        try:

                            self.ctc_time = self.ctc.calc_time(self.ob[tel]["block"])


                            # DUPA zamiast 0.1 None i obsluga
                            self.ob[tel]["slot_time"] = self.ctc_time
                            if self.ob[tel]["slot_time"] == 0:
                                self.ob[tel]["slot_time"] = 0.1
                        except ValueError:
                            self.ob[tel]["slot_time"] = 0.1
                            logger.warning(f'TOI: EXCEPTION 44: {e}')

                        txt = self.ob[tel]["block"]

                        try:
                            s = self.nats_toi_ob_status[tel]
                            status = {"ob_started":self.ob[tel]["run"],"ob_done":self.ob[tel]["done"],"ob_start_time":self.ob_start_time,"ob_expected_time":self.ob[tel]["slot_time"],"ob_program":self.ob[tel]["block"]}
                            await s.publish(data=status,timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 45: {e}')

                    elif info["name"] == "NIGHTPLAN" and info["done"]:
                        self.ob[tel]["done"] = True

                        # DUPA
                        #if "plan" in self.program_name:             # ma to wykonac tylko jak obsluguje plan
                        if "plan" in self.ob[tel]["origin"]:
                            self.next_i[tel] = self.current_i[tel]
                            self.plan[tel].pop(self.current_i[tel])
                            self.current_i[tel] = -1
                            self.update_plan(tel)

                        self.exp_prog_status["dit_start"] = 0

                        try:
                            s = self.nats_toi_exp_status[tel]
                            data = self.exp_prog_status
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 46: {e}')

                        await self.msg("PLAN: Plan finished", "black")
                        self.ob[tel]["run"] = False
                        self.ob[tel]["done"] = True

                        try:
                            s = self.nats_toi_ob_status[tel]
                            status = {"ob_started":self.ob[tel]["run"],"ob_done":self.ob[tel]["done"],"ob_start_time":self.ob[tel]["start_time"],"ob_expected_time":self.ob[tel]["slot_time"],"ob_program":self.ob[tel]["block"]}
                            await s.publish(data=status,timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 47: {e}')

                    elif info["name"] == "SKYFLAT" and info["started"] and not info["done"]:  # SKYFLAT
                        await self.msg(f"PLAN: AUTO FLAT program started", "black")                       # SKYFLAT

                    elif info["name"] == "SKYFLAT" and info["done"]:
                        await self.msg(f"PLAN: AUTO FLAT program finished", "black")


                if "exp_started" in info.keys() and "exp_done" in info.keys():
                    if info["exp_started"] and not info["exp_done"]:
                        self.exp_prog_status["ndit"]=float(info["n_exp"])
                        self.exp_prog_status["ndit_req"]=float(info["exp_no"])
                        self.exp_prog_status["dit_exp"]=float(info["exp_time"])
                        self.exp_prog_status["dit_start"]=self.time
                        self.exp_prog_status["plan_runner_status"]="exposing"

                        try:
                            s = self.nats_toi_exp_status[tel]
                            data = self.exp_prog_status
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 48: {e}')

                        await self.msg(f"PLAN: {self.exp_prog_status['dit_exp']} [s] exposure started","black")

                    elif info["exp_done"] and info["exp_saved"]:
                        self.exp_prog_status["ndit"]=float(info["n_exp"])
                        self.exp_prog_status["plan_runner_status"]="exp done"

                        try:
                            s = self.nats_toi_exp_status[tel]
                            data = self.exp_prog_status
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 49: {e}')


                if "auto_exp_start" in info.keys() and "auto_exp_finnished" in info.keys():    # SKYFLAT
                    if info["auto_exp_start"] and not info["auto_exp_finnished"]:
                        self.exp_prog_status["ndit"]=0
                        self.exp_prog_status["ndit_req"]=float(info["exp_no"])
                        self.exp_prog_status["dit_exp"]=float(info["auto_exp_time"])
                        self.exp_prog_status["dit_start"]=self.time
                        self.exp_prog_status["plan_runner_status"]="exposing"

                        try:
                            s = self.nats_toi_exp_status[tel]
                            data = self.exp_prog_status
                            await s.publish(data=data, timeout=10)
                        except Exception as e:
                            logger.warning(f'TOI: EXCEPTION 50: {e}')


                        await self.msg(f"PLAN: {self.exp_prog_status['dit_exp']} [s] test exposure started","black")

                    elif info["auto_exp_finnished"]:
                        await self.msg(f"PLAN: test exposure done", "black")

                if "test_exp_mean" in info.keys():                                                        # SKYFLAT
                    await self.msg(f"PLAN: mean {int(info['test_exp_mean'])} ADU measured", "black")


                if "id" in info.keys():  # to jest tylko do wyswietlania w oknie loga planu
                    self.program_id = info["id"]
                    ut=str(self.almanac["ut"]).split()[1].split(":")[0]+":"+str(self.almanac["ut"]).split()[1].split(":")[1]
                    txt = f"--- {tel} ---  {ut}  ------  {self.program_id}  ------\n {info}\n"
                    self.planGui.prog_call_e.append(txt)

                # FLAT RECORDER
                #  to mozna na razie wylaczyc, bedzie przerabiane

                # if "type" in info.keys() and "name" in info.keys() and "exp_done" in info.keys() and "filter" in info.keys() and "exp_time" in info.keys() and "done" in info.keys():
                #
                #     if info["type"] == "flat" and info["exp_done"] == False:
                #         self.flat_record["date"] =  str(self.date) + " " + str(self.ut).split()[1].split(":")[0] + ":" + str(self.ut).split()[1].split(":")[1]
                #         self.flat_record["filter"] = info["filter"]
                #         self.flat_record["exp_time"] = info["exp_time"]
                #         self.flat_record["h_sun"] = f"{deg_to_decimal_deg(self.almanac['sun_alt']):.2f}"
                #         self.flat_record["go"] = True
                # if "name" in info.keys():
                #     if info["name"] == "DOMEFLAT":          # te wystepuja w oddzielnej iteracji, wczesniejszej
                #         self.flat_record["type"] = "domeflat"
                #     elif info["name"] == "SKYFLAT":
                #         self.flat_record["type"] = "skyflat"



                try:

                    # AUTOFOCUS

                    if self.autofocus_started[tel]:
                        if "id" in info.keys():
                            if "auto_focus" in info["id"] and info["started"]==True and info["done"]==True:
                                self.autofocus_started[tel]=False
                                await self.msg("PLAN: Auto-focus sequence finished","black")
                                max_sharpness_focus, calc_metadata = calFoc.calculate(self.local_cfg[self.active_tel]["tel_directory"]+"focus/actual",method=self.focus_method)

                                try:
                                    s = self.nats_toi_focus_status[tel]
                                    data = {}
                                    data["coef"] = list(calc_metadata["coef"])
                                    data["focus_values"] = list(calc_metadata["focus_values"])
                                    data["sharpness_values"] = list(calc_metadata["sharpness_values"])
                                    data["max_sharpness_focus"] = float(max_sharpness_focus)
                                    data["status"] = str(calc_metadata["status"])
                                    await s.publish(data=data, timeout=10)
                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 42: {e}')

                                if calc_metadata["status"] == "ok":
                                    await self.tel_focusers[tel].aput_move(int(max_sharpness_focus))
                                    await self.msg(f"PLAN: focus set to {int(max_sharpness_focus)}","black")
                                else:
                                    await self.msg(f"PLAN: focusing FAILED. Focus set to previous value {int(self.last_focus_position[tel])}", "red")

                except Exception as e:
                    logger.warning(f'TOI: EXCEPTION 37: {e}')



    # ############ AUTO FOCUS ##########################

    # STAGE2
    # tu dodac tylko obsluge na ktory planrunner ma isc
    # ale moze wymagac dodatkowej obslugi

    @qs.asyncSlot()
    async def auto_focus(self):
        if await self.user.aget_is_access():
            ok = False
            v0 = float(self.auxGui.focus_tab.last_e.text())
            step = float(self.auxGui.focus_tab.steps_e.text())
            number = float(self.auxGui.focus_tab.range_e.text())
            method = self.auxGui.focus_tab.method_s.currentText()
            if method == "RMS":
                self.focus_method = "rms"
                if number > 2:
                    ok = True
                else: self.WarningWindow("WARNING: Not enough STEPS number")
            elif method == "RMS_QUAD":
                self.focus_method = "rms_quad"
                if number > 4:
                    ok = True
                else: self.WarningWindow("WARNING: Not enough STEPS number")

            if ok:
                exp=self.instGui.ccd_tab.inst_Dit_e.text()
                if len(exp)==0:
                    exp = 5
                    await self.msg("WARNING: no exp specified. exp=5","red")

                seq = f"{int(number)}/"+str(self.curent_filter)+"/"+str(exp)
                pos = f"{int(v0)}/{int(step)}"
                uobi = str(uuid.uuid4())[:8]
                program = f"FOCUS seq={seq} pos={pos} uobi={uobi}"

                self.ob[self.active_tel]["block"] = program
                self.ob[self.active_tel]["origin"] = "auto_focus"
                self.autofocus_started[self.active_tel]=True
                tmp = await self.tel_focusers[self.active_tel].aget_position()
                self.last_focus_position[self.active_tel] = float(tmp)
                self.planrunner_start(self.active_tel)

        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)


    # ############ PLAN ##########################

    # to ustawia wszytskie potrzebne parametry dla planrunnera i wywoluje planrunner_start
    # dodac obluge wieloteleskoowosci
    @qs.asyncSlot()
    async def plan_start(self,tel):
        if await self.user.aget_is_access():
            self.observer = self.auxGui.welcome_tab.observer_e.text()

            if self.next_i[tel] > -1 and self.next_i[tel] < len(self.plan[tel]):
                self.ob[tel] = self.plan[tel][self.next_i[tel]]
                self.ob[tel]["start_time"] = self.time


                if "uobi" in self.ob[tel].keys():
                    #DUPA to chyba niepotrzebne
                    # if self.ob[tel]["uobi"] not in self.planGui.done:
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
                                #self.plan[tel].pop(self.current_i[tel])
                                self.current_i[tel] = -1
                                self.update_plan(tel)

                                try:
                                    s = self.nats_toi_ob_status
                                    status = {"ob_started": True, "ob_done": False,
                                              "ob_start_time": self.time,
                                              "ob_expected_time": 0.1, "ob_program": "STOP"}
                                    await s.publish(data=status, timeout=10)
                                except Exception as e:
                                    logger.warning(f'TOI: EXCEPTION 51: {e}')


                            if self.ob[tel]["type"] == "BELL":
                                await self.msg("INFO: BELL","black")
                                #w = self.nats_journal_toi_msg
                                #txt = f"BELL by {self.myself}"
                                #await w.log('INFO', txt)
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
                                    await self.msg(f"PLAN: {self.ob[tel]['name']} {self.ob[tel]['wait']} s. start","black")
                                if "wait_ut" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.msg(f"PLAN: {self.ob[tel]['name']} UT {self.ob[tel]['wait_ut']} start","black")
                                if "wait_sunset" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.msg(f"PLAN: {self.ob[tel]['name']} sunset {self.ob[tel]['wait_sunset']} start","black")
                                if "wait_sunrise" in self.ob[tel].keys():
                                    self.ob[tel]["done"]=False
                                    self.ob[tel]["run"]=True
                                    await self.msg(f"PLAN: {self.ob[tel]['name']} sunrise {self.ob[tel]['wait_sunrise']} start","black")
                                self.ob[tel]["continue_plan"] = True
                                self.ob[tel]["origin"] = "plan"

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

                                self.focus_method = "rms_quad"
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
                                # DUPA
                                #self.program_name=program_name
                                self.planrunner_start(tel)

                            self.next_ob()
                    else:
                        self.next_ob()
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)


    # DUPA
    # nie wiadomo czy to jest wogule potrzbene
    def next_ob(self):
        pass

        #self.next_i = self.next_i + 1
        #self.update_plan()

        #self.planGui.update_table()

    # STAGE 2
    # dodac tylko obsluge aktualnego wieloteleskopowosci
    @qs.asyncSlot()
    async def resume_program(self):
        await self.planrunners[self.active_tel].astop_nightplan()
        await self.planrunners[self.active_tel].arun_nightplan(self.ob[self.active_tel]["origin"], step_id=self.program_id)


    @qs.asyncSlot()
    async def stop_program(self):
        await self.takeControl()
        await self.msg("REQUEST: program STOP ","yellow")
        await self.planrunners[self.active_tel].astop_nightplan()

        self.ob[self.active_tel]["done"] = False
        self.ob[self.active_tel]["run"] = False
        self.ob[self.active_tel]["origin"] = "plan"
        self.ob[self.active_tel]["continue_plan"] = False
        self.ob[self.active_tel]["slot_time"] = None
        self.ob[self.active_tel]["start_time"] = None

        self.current_i[self.active_tel] = -1
        self.update_plan(self.active_tel)

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
                                            #self.plan[tel][i]["skip_alt"] = True
                                            print("nisko", self.plan[tel][i]["name"])
                                            print(self.plan[tel][i]["slotTime"])
                                    except (ephem.NeverUpError, ephem.AlwaysUpError) as e:
                                        pass

                                    self.oca_site.horizon = str(self.cfg_alt_limits["max"] + 1)
                                    try:
                                        t = self.oca_site.next_rising(star, use_center=True)
                                        if t < ob_time + ephem.second * self.plan[tel][i]["slotTime"]:
                                            self.plan[tel][i]["skip_alt"] = True
                                            print("wysoko", self.plan[tel][i]["name"])
                                            print(self.plan[tel][i]["slotTime"])
                                    except (ephem.NeverUpError, ephem.AlwaysUpError) as e:
                                        pass

                                if self.plan[tel][i]["uobi"] in self.done_uobi:
                                    ob_time = ob_time
                                else:
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
                print(tel, len(self.plan[tel]),self.current_i[tel],self.next_i[tel])

    def check_next_i(self,tel):
        if self.next_i[tel] > len(self.plan[tel])-1:
            self.next_i[tel] = -1
        else:

            if "skip" in self.plan[tel][self.next_i[tel]].keys():
                if self.plan[tel][self.next_i[tel]]["skip"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i()

            if "skip_alt" in self.plan[tel][self.next_i[tel]].keys():
                if self.plan[tel][self.next_i[tel]]["skip_alt"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i()

            if "ok" in self.plan[tel][self.next_i[tel]].keys():
                if not self.plan[tel][self.next_i[tel]]["ok"]:
                    self.next_i[tel] = self.next_i[tel] + 1
                    self.check_next_i()



    # ############ CCD ##################################


    async def ccd_imageready(self,event):
        if self.ccd.imageready:
            self.flag_newimage = True

    @qs.asyncSlot()
    async def new_fits(self):
        if Path(self.cfg_tel_directory + "last_shoot.fits").is_file():
            hdul = fits.open(self.cfg_tel_directory + "last_shoot.fits")
            self.image = hdul[0].data
        else:
            self.image = await self.ccd.aget_imagearray()

        if True:
            image = self.image
            image = numpy.asarray(image)

            scale = 1
            fwhm = 4
            kernel_size = 6
            saturation = 45000
            if self.image.shape[0] > 4000 or self.image.shape[1] > 4000:
                image = image.reshape(self.image.shape[0]//2,2,self.image.shape[1]//2,2).mean(axis=(1,3))
                fwhm = 2
                kernel_size = 6
                saturation = 45000
                scale = 2

            stats = FFS(image)
            fwhm_x,fwhm_y=0,0
            th = 20
            t0 = time.time()
            coo,adu = stats.find_stars(threshold=th,kernel_size=kernel_size,fwhm=fwhm)
            t1 = time.time()
            if len(coo)>3:
                fwhm_x,fwhm_y = stats.fwhm(saturation=saturation)
                if fwhm_x != None and fwhm_y !=None:
                    fwhm = (fwhm_x+fwhm_y)/2.
                    coo, adu = stats.find_stars(threshold=th, kernel_size=9, fwhm=1.5*fwhm)

            sat_coo=[]
            sat_adu=[]
            ok_coo=[]
            ok_adu=[]

            if len(coo)>1:
                coo = numpy.array(coo)
                adu = numpy.array(adu)
                maska1 = numpy.array(adu) > 45000
                sat_coo = coo[maska1]
                sat_adu = adu[maska1]
                maska2 = [not val for val in maska1]
                ok_coo = coo[maska2]
                ok_adu = adu[maska2]

            txt = f"stars detected:".ljust(17) + f"{len(coo)}".ljust(9)
            txt = txt + f"saturated:".ljust(15) +f"{len(sat_coo)}\n"

            if len(ok_adu)>0:
                txt = txt + f"stars max ADU:".ljust(17)+f"{ok_adu[0]}".ljust(9)
            if fwhm_x == None or fwhm_y == None:
                fwhm_x,fwhm_y=0,0
            fwhm_x, fwhm_y = scale * fwhm_x, scale * fwhm_y
            txt = txt + f"FWHM X/Y:".ljust(13)+f"{float(fwhm_x):.1f}/{float(fwhm_y):.1f}\n"

            txt = txt + f"min ADU:".ljust(17)  +f"{stats.min:.0f}".ljust(9)
            txt = txt + f"max ADU:".ljust(15)  +f"{stats.max:.0f}\n"

            txt = txt + f"mean/median:".ljust(15) +   f"{stats.mean:.0f}/{stats.median:.0f}".ljust(11)
            txt = txt + f"rms/sigma_q:".ljust(15)  +  f"{stats.rms:.0f}/{stats.sigma_quantile:.0f}\n"

            self.auxGui.fits_tab.fitsView.stat_e.setText(txt)
            ok_coo=[]
            self.auxGui.fits_tab.fitsView.update(image,sat_coo,ok_coo)

            self.auxGui.tabWidget.setCurrentIndex(4)

            # To jest logowanie flatow, pozniej to ogarnac

            # if self.flat_record["go"]:
            #     self.flat_record["ADU"] = stats.median
            #     txt = (f'{self.flat_record["date"]}  {self.flat_record["type"]}  {self.flat_record["filter"]}  'f'{float(self.flat_record["exp_time"]):.2f}  {self.flat_record["h_sun"]}  {self.flat_record["ADU"]}')
            #     self.auxGui.flat_tab.info_e.append(txt)
            #     self.auxGui.tabWidget.setCurrentIndex(1)
            #     self.flat_record["go"] = False
            #
            #     f_name = self.flat_log_files
            #     flat_log_file = self.script_location+f_name #"/Logs/zb08_flats_log.txt"
            #     if os.path.exists(flat_log_file):
            #         pass
            #     else:
            #         with open(flat_log_file,"w") as log_file:
            #             log_file.write("DATE UT | type | filter | exp | h_sun | ADU\n")
            #     with open(flat_log_file,"a") as log_file:
            #         log_file.write(txt+"\n")
            #     w: MsgJournalPublisher = self.nats_journal_flats_writter
            #     await w.log('INFO', txt)
            #     self.flat_record["go"] = False



    @qs.asyncSlot()
    async def ccd_Snap(self):
        self.observer = self.auxGui.welcome_tab.observer_e.text()
        if await self.user.aget_is_access():
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
                await self.msg("WARNING: OBJECT NAME required","red")
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
                await self.msg("WARNING: wrong EXP format","red")
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
                await self.msg("WARNING: wrong N format","red")
                self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            if ok_exp and ok_ndit:
                seq = "1/"+str(self.curent_filter)+"/"+str(exp)
                ok_seq = True

            if ok_name and ok_seq:
                uobi = str(uuid.uuid4())[:8]
                self.ob[self.active_tel]["block"] = f"SNAP {name} seq={seq} dome_follow=off uobi={uobi}"
                # DUPA
                #self.ob_program = f"SNAP {name} seq={seq} dome_follow=off uobi={uobi}"
                self.ob[self.active_tel]["origin"] = "snap"
                #DUPA
                #self.program_name = "snap"
                self.planrunner_start(self.active_tel)

        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_startExp(self):
        if await self.user.aget_is_access():

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
                await self.msg("WARNING: OBJECT NAME required","red")
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
                    await self.msg("WARNING: wrong EXP TIME format","red")
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
                    await self.msg("WARNING: wrong N format","red")
                    self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

                if ok_exp and ok_ndit:
                    seq = str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                    ok_seq = True

            if self.instGui.ccd_tab.Select2_r.isChecked():
                seq = self.instGui.ccd_tab.inst_Seq_e.text().strip()

                ok_seq,err = seq_verification(seq,self.filter_list)
                if not ok_seq:
                    await self.msg(f"WARNING: {err}","red")
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
                        self.WarningWindow("WARNING: Motors should be ON for SKYFLAT")

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==4:
                    txt=f"DOMEFLAT {name} seq={seq}  "
                    if self.mount_motortatus: pass
                    else:
                        ok = False
                        self.WarningWindow("WARNING: Motors should be ON for DOMEFLAT")

                else: await self.msg(f"WARNING: not implemented yet","yellow")

            if ok:
                uobi = str(uuid.uuid4())[:8]
                self.ob[self.active_tel]["block"] = txt + f' uobi={uobi}'
                #self.ob_program = txt + f' uobi={uobi}'
                self.ob[self.active_tel]["origin"] = "manual"
                #DUPA
                #self.program_name = "manual"
                self.planrunner_start(self.active_tel)
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_stopExp(self):
        if True:
            await self.takeControl()
            self.exp_prog_status["dit_start"]=0

            try:
                s = self.nats_toi_exp_status
                data = self.exp_prog_status
                await s.publish(data=data, timeout=10)
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 40: {e}')

            self.ob[self.active_tel]["run"]=False
            try:
                await self.planrunners[self.active_tel].astop_nightplan()
            except:
                pass
            await self.ccd.aput_stopexposure()
            await self.msg(f"REQUEST: exposure STOP","yellow")


    @qs.asyncSlot()
    async def ccd_setBin(self):
        if await self.user.aget_is_access():
            if self.instGui.ccd_tab.inst_Bin_s.currentIndex()==0: x,y=1,1
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==1: x,y=2,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==2: x,y=1,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==3: x,y=2,1
            else:
                await self.msg(f"not a valid option","red")
                return

            txt=f"REQUEST: CCD bin_x bin_y {x}x{y}"
            await self.msg(txt,"green")
            self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
            await self.ccd.aput_binx(int(x))
            await self.ccd.aput_biny(int(y))
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setGain(self):
        if await self.user.aget_is_access():
            i = self.instGui.ccd_tab.inst_setGain_e.currentIndex()
            gain = self.cfg_inst_gain_i[i]
            txt=f"REQUEST: CCD gain {self.instGui.ccd_tab.inst_setGain_e.currentText()}"
            await self.msg(txt,"green")
            self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
            await self.ccd.aput_gain(int(gain))
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setReadMode(self):
        if await self.user.aget_is_access():
           i = int(self.instGui.ccd_tab.inst_setRead_e.currentIndex())
           rm = self.cfg_inst_rm_i[i]
           if True:
               txt=f"REQUEST: CCD readout mode {self.cfg_inst_rm[i]}"
               await self.msg(txt,"green")
               await self.ccd.aput_readoutmode(rm)
               self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)


    @qs.asyncSlot()
    async def ccd_setTemp(self):
        if await self.user.aget_is_access():
            temp=float(self.instGui.ccd_tab.inst_setTemp_e.text())
            if temp>-81 and temp<20:
                txt=f"REQUEST: CCD temp. set to {temp} deg."
                await self.ccd.aput_setccdtemperature(temp)
                await self.msg(txt,"green")
            else:
                txt="Value of CCD temp. not allowed"
                await self.msg(txt,"red")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_coolerOnOf(self):
        if await self.user.aget_is_access():
            if self.ccd.cooleron:
              txt="REQUEST: CCD cooler OFF"
              await self.ccd.aput_cooleron(False)
              await self.msg(txt,"green")
            else:
              txt="REQUEST: CCD cooler ON"
              await self.ccd.aput_cooleron(True)
              await self.msg(txt,"green")
        else:
            txt="WARNING: U don't have controll"
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
        # DUPA dwa agety w jednej subskrypcji
        if await self.user.aget_is_access():
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False
           if self.mount_motortatus:
              txt="REQUEST: motors OFF"
              await self.msg(txt,"black")
              await self.mount.aput_motoroff()
           else:
               txt="REQUEST: motors ON"
               await self.msg(txt,"green")
               await self.mount.aput_motoron()
           #self.mntGui.mntStat_e.setText(txt)
           #self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.mountMotors_update(None)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    async def mountMotors_update(self,event):
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False

           if self.mount_motortatus:
               self.mntGui.mntMotors_c.setChecked(True)
               txt="TELEMETRY: motors ON"
               await self.msg(txt,"black")
           else:
               self.mntGui.mntMotors_c.setChecked(False)
               txt="TELEMETRY: motors OFF"
               await self.msg(txt,"black")
           await self.mount_update()

           #self.mntGui.mntStat_e.setText(txt)
           #self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")

    @qs.asyncSlot()
    async def covers_openOrClose(self):
        if await self.user.aget_is_access():
           self.cover_status = self.cover.coverstate
           if self.cover_status==1:
              txt="REQUEST: mirror OPEN"
              await self.msg(txt,"green")
              await self.cover.aput_opencover()
           else:
               txt="REQUEST: mirror CLOSE"
               await self.msg(txt,"black")
               await self.cover.aput_closecover()
           self.mntGui.telCovers_e.setText(txt)
           self.mntGui.telCovers_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.covers_update(None)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    async def covers_update(self,event):
           self.cover_status = await self.cover.aget_coverstate()

           if self.cover_status==3:
               self.mntGui.telCovers_c.setChecked(True)
               txt="OPEN"
               await self.msg(f"TELEMETRY: covers {txt}","green")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
           elif self.cover_status==1:
               self.mntGui.telCovers_c.setChecked(False)
               txt="CLOSED"
               await self.msg(f"TELEMETRY: covers {txt}","black")
               self.mntGui.telCovers_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
           elif self.cover_status==2:
               txt="MOVING"
               await self.msg(f"TELEMETRY: covers {txt}","yellow")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(255, 165, 0); background-color: rgb(233, 233, 233);")
           else:
               txt="UNKNOWN"
               await self.msg(f"TELEMETRY: covers {txt}","red")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(233, 0, 0); background-color: rgb(233, 233, 233);")

           self.mntGui.telCovers_e.setText(txt)
           self.obsGui.main_form.skyView.updateMount()

    @qs.asyncSlot()
    async def park_mount(self):
        if await self.user.aget_is_access():
            if self.mount.motorstatus != "false":
                txt="PARK requested"
                self.mntGui.mntStat_e.setText(txt)
                self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
                await self.msg(txt, "green")
                self.mntGui.domeAuto_c.setChecked(False)
                await self.domeFollow()
                await self.mount.aput_park()
                await self.dome.aput_slewtoazimuth(180.)
            else:
                txt = "WARNING: Motors are OFF"
                self.WarningWindow(txt)

        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def abort_slew(self):
        if True:
            await self.takeControl()
            txt="REQUEST: slew STOP"
            self.mntGui.mntStat_e.setText(txt)
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
            await self.mount.aput_abortslew()
            await self.mount.aput_tracking(False)
            await self.msg(txt,"red")


    @qs.asyncSlot()
    async def mount_slew(self):
        if await self.user.aget_is_access():
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
                       txt=f"REQUEST: slew to Az: {az} Alt: {alt}"
                       await self.msg(txt,"black")

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
                       txt=f"REQUEST: slew to Ra: {ra} Dec: {dec}"
                       await self.msg(txt,"black")

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
                else:
                    txt = "WARNING: Slew NOT allowed"
                    await self.msg(txt,"red")
                    self.WarningWindow(txt)
            else:
                txt = "WARNING: Motors are OFF"
                self.WarningWindow(txt)
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def mount_trackOnOff(self):
        if await self.user.aget_is_access():
            if await self.mount.aget_motorstatus() != "false":
                self.mount_tracking = await self.mount.aget_tracking()

                if self.mount_tracking:
                   await self.mount.aput_tracking(False)
                   txt="REQUEST: tracking STOP"
                else:
                   await self.mount.aput_tracking(True)
                   txt="REQUEST: tracking START"

                self.mntGui.mntStat_e.setText(txt)
                self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                await self.msg(txt,"green")
            else:
                await self.mount_update()
                txt = "WARNING: Motors are OFF"
                self.WarningWindow(txt)

        else:
            await self.mount_update()
            txt="WARNING: U don't have controll"
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
        self.obsGui.main_form.skyView.updateMount()
        await self.msg(f"TELEMETRY: mount {txt}","black")

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
           self.obsGui.main_form.skyView.updateMount()
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
        if await self.user.aget_is_access():
            arcsec = self.mntGui.pulse_window.pulseDec_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(0,sec)
            self.pulseDec = self.pulseDec + float(arcsec)
            self.mntGui.pulse_window.sumDec_e.setText(str(self.pulseDec))
            await self.msg(f"REQUEST: pulse DEC + {arcsec}", "black")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_down(self):
        if await self.user.aget_is_access():
            arcsec = self.mntGui.pulse_window.pulseDec_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(1,sec)
            self.pulseDec = self.pulseDec - float(arcsec)
            self.mntGui.pulse_window.sumDec_e.setText(str(self.pulseDec))
            await self.msg(f"REQUEST: pulse DEC - {arcsec}", "black")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_left(self):
        if await self.user.aget_is_access():
            arcsec = self.mntGui.pulse_window.pulseRa_e.text()
            sec = 1000 * (float(arcsec)/6  )
            sec = int(sec)
            await self.mount.aput_pulseguide(2,sec)
            self.pulseRa = self.pulseRa + float(arcsec)
            self.mntGui.pulse_window.sumRa_e.setText(str(self.pulseRa))
            await self.msg(f"REQUEST: pulse Ra + {arcsec}", "black")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def pulse_right(self):
        if await self.user.aget_is_access():
            arcsec = self.mntGui.pulse_window.pulseRa_e.text()
            sec = 1000 * (float(arcsec)/6 )
            sec = int(sec)
            await self.mount.aput_pulseguide(3,sec)
            self.pulseRa = self.pulseRa - float(arcsec)
            self.mntGui.pulse_window.sumRa_e.setText(str(self.pulseRa))
            await self.msg(f"REQUEST: pulse Ra - {arcsec}", "black")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    # ################# DOME ########################

    async def dome_con_update(self, event):
        self.dome_con =self.dome.connected


    @qs.asyncSlot()
    async def dome_openOrClose(self):
        if await self.user.aget_is_access():
           if self.cover.coverstate == 1:
               if self.dome_shutterstatus==0:
                  await self.dome.aput_closeshutter()
                  txt="REQUEST: dome CLOSE"
               elif self.dome_shutterstatus==1:
                  await self.dome.aput_openshutter()
                  txt="REQUEST: dome OPEN"
               else: pass
               self.mntGui.domeShutter_e.setText(txt)
               self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
               await self.msg(txt,"green")
           else:
               await self.domeShutterStatus_update(False)
               txt = "WARNING: Mirror covers are open. Close MIRROR for dome shutter operations"
               self.WarningWindow(txt)

        else:
            await self.domeShutterStatus_update(None)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_move2Az(self):
        if await self.user.aget_is_access():
           if self.dome_next_az_ok:
               az = float(self.mntGui.domeNextAz_e.text())
               await self.dome.aput_slewtoazimuth(az)

        else:
            await self.domeShutterStatus_update(False)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_stop(self):
        if True: #self.user.current_user["name"]==self.myself:
           await self.takeControl()
           await self.dome.aput_abortslew()
           await self.msg("REQUEST: dome STOP","yellow")


    @qs.asyncSlot()
    async def domeFollow(self):
        if await self.user.aget_is_access():
            self.toi_status["dome_follow_switch"] = self.mntGui.domeAuto_c.isChecked()
            try:
                s = self.nats_pub_toi_status
                data = self.toi_status
                await s.publish(data=data, timeout=10)
            except Exception as e:
                logger.warning(f'TOI: EXCEPTION 41: {e}')
        else:
            txt="WARNING: You don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.domeAuto_c.isChecked():
                self.mntGui.domeAuto_c.setChecked(False)
            else:
                self.mntGui.domeAuto_c.setChecked(True)

    async def domeShutterStatus_update(self, event):
           self.dome_shutterstatus=await self.dome.aget_shutterstatus()
           if self.dome_shutterstatus==0:
              txt="OPEN"
              self.mntGui.domeShutter_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
              self.mntGui.domeShutter_c.setChecked(True)
              self.obsGui.main_form.skyView.updateDome()

           elif self.dome_shutterstatus==1:
                txt="CLOSED"
                self.mntGui.domeShutter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                self.mntGui.domeShutter_c.setChecked(False)
                self.obsGui.main_form.skyView.updateDome()

           elif self.dome_shutterstatus==2:
                txt="OPENING"
                self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                self.obsGui.main_form.skyView.updateDome()


           elif self.dome_shutterstatus==3:
                txt="CLOSING"
                self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                self.obsGui.main_form.skyView.updateDome()

           else:
                txt="UNKNOWN"
                self.mntGui.domeShutter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                #self.obsGui.main_form.skyView.updateDome()
           self.mntGui.domeShutter_e.setText(txt)
           await self.msg(f"TELEMETRY: shutter {txt}","black")

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
        await self.msg(f"TELEMETRY: dome {txt}","black")

    async def domeAZ_update(self, event):
        self.dome_az = await self.dome.aget_az()
        if self.dome_az:
            self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
            self.obsGui.main_form.skyView.updateDome()

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
        if await self.user.aget_is_access():
            r = await self.dome.aget_dome_fans_running()
            if r:
                self.dome_fanStatus=True
            else:
                self.dome_fanStatus=False

            if self.dome_fanStatus:
               txt="REQUEST: ventilators OFF"
               await self.msg(txt,"green")
               await self.dome.aput_fans_turn_off()
            else:
                txt="REQUEST: ventilators ON"
                await self.msg(txt,"green")
                await self.dome.aput_dome_fans_turn_on()
            self.mntGui.ventilators_e.setText(txt)
            self.mntGui.ventilators_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.Ventilators_update(False)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    async def Ventilators_update(self,event):
        r = await self.dome.aget_dome_fans_running()
        if r:
            self.dome_fanStatus=True
        else:
            self.dome_fanStatus=False

        if self.dome_fanStatus:
            self.mntGui.ventilators_c.setChecked(True)
            txt="VENT ON"
        else:
            self.mntGui.ventilators_c.setChecked(False)
            txt="VENT OFF"
        self.mntGui.ventilators_e.setText(txt)
        self.mntGui.ventilators_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")

    # OTHER COMPONENTS

    @qs.asyncSlot()
    async def mirrorFansOnOff(self):
        if await self.user.aget_is_access():
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False
           if self.dome_fanStatus:
              txt="REQUEST: mirror fans OFF"
              await self.msg(txt,"green")
              await self.focus.aput_fansturnoff()
           else:
               txt="REQUEST: mirror fans ON"
               await self.msg(txt,"green")
               await self.focus.aput_fansturnon()
           self.mntGui.mirrorFans_e.setText(txt)
           self.mntGui.mirrorFans_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.mirrorFans_update(False)
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    async def mirrorFans_update(self,event):
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False

           if self.dome_fanStatus:
               self.mntGui.mirrorFans_c.setChecked(True)
               txt="FANS ON"
           else:
               self.mntGui.mirrorFans_c.setChecked(False)
               txt="FANS OFF"
           self.mntGui.mirrorFans_e.setText(txt)
           self.mntGui.mirrorFans_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")


    @qs.asyncSlot()
    async def FlatLampOnOff(self):
        if await self.user.aget_is_access():

           if self.mntGui.flatLights_c.isChecked():
               await self.mount.aput_domelamp_on()
               txt = "REQUEST: flat lamp ON - no feedback"
               self.mntGui.flatLights_e.setText("no feedback")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else:
               await self.mount.aput_domelamp_off()
               txt = "REQUEST: flat lamp OFF - no feedback"
               self.mntGui.flatLights_e.setText("")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(0,0,0); background-color: rgb(233, 233, 233);")

           await self.msg(txt,"yellow")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.flatLights_c.isChecked(): self.mntGui.flatLights_c.setChecked(False)
            else: self.mntGui.flatLights_c.setChecked(True)

    @qs.asyncSlot()
    async def domeLightOnOff(self):
        if await self.user.aget_is_access():
           if self.mntGui.domeLights_c.isChecked():
               await self.cctv.aput_ir(True)
               self.mntGui.domeLights_e.setText("no feedback")
               txt = "REQUEST: dome lamp ON - no feedback"
               self.mntGui.domeLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else:
               await self.cctv.aput_ir(False)
               self.mntGui.domeLights_e.setText("")
               txt = "REQUEST: dome lamp OFF - no feedback"
               self.mntGui.domeLights_e.setStyleSheet("color: rgb(0,0,0); background-color: rgb(233, 233, 233);")
           await self.msg(txt,"green")
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.domeLights_c.isChecked(): self.mntGui.domeLights_c.setChecked(False)
            else: self.mntGui.domeLights_c.setChecked(True)



    # ############ FOCUS ##################################

    async def focus_con_update(self, event):
        self.focus_con = self.focus.connected

    @qs.asyncSlot()
    async def set_focus(self):
        if await self.user.aget_is_access():
           self.focus_editing=False
           self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(255, 255, 255);")
           val=self.mntGui.setFocus_s.value()
           await self.focus.aput_move(val)
           txt=f"REQUEST: focus {val}"
           await self.msg(txt,"green")
        else:
            txt="WARNING: U don't have controll"
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
            await self.msg("TELEMETRY: focus position ERROR","red")

        if not self.focus_editing:
           self.mntGui.setFocus_s.valueChanged.disconnect(self.focusClicked)
           self.mntGui.setFocus_s.setValue(int(self.focus_value))
           self.mntGui.setFocus_s.valueChanged.connect(self.focusClicked)

    # ############### FILTERS #####################

    async def filter_con_update(self, event):
        self.fw_con = self.fw.connected

    @qs.asyncSlot()
    async def set_filter(self):
        if await self.user.aget_is_access():
           ind=int(self.mntGui.telFilter_s.currentIndex())
           if ind == -1: filtr="--"
           else: filtr=self.filter_list[ind]
           txt=f"REQUEST: filter {filtr}"
           await self.msg(txt,"green")
           await self.fw.aput_position(ind)
        else:
            txt="WARNING: U don't have controll"
            self.WarningWindow(txt)

    async def filter_update(self, event):
            pos = int(await self.fw.aget_position())
            self.curent_filter=self.filter_list[pos]
            if pos == -1: filtr = "--"
            else: filtr = self.filter_list[pos]
            self.mntGui.telFilter_e.setText(filtr)
            self.filter = filtr
            await self.msg(f"TELEMETRY: filter {filtr}", "black")

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
            await self.msg("TELEMETRY: rotator position ERROR","red")
        self.rotator_pos_prev = self.rotator_pos

        # ############ TELESCOPE #########################

    @qs.asyncSlot()
    async def EmStop(self):
        if self.telescope is not None:
            txt = f"REQUEST: EMERGENCY STOP"
            await self.msg(txt, "red")
            await self.user.aget_is_access()
            self.mntGui.domeAuto_c.setChecked(False)
            await self.tic_telescopes[self.active_tel].emergency_stop()
            await self.domeFollow() #
        else:
            txt = f"REQUEST: emergency stop but no telescope is selected"
            await self.msg(txt, "yellow")

    @qs.asyncSlot()
    async def shutdown(self):
        if self.telescope is not None:
            if await self.user.aget_is_access():
                txt = f"REQUEST: telescope shutdown"
                await self.msg(txt, "green")
                self.mntGui.domeAuto_c.setChecked(False)
                await self.dome.aput_slewtoazimuth(180.)
                await self.tic_telescopes[self.active_tel].shutdown()
            else:
                txt = "WARNING: U don't have controll"
                self.WarningWindow(txt)
        else:
            txt = f"REQUEST: telescope shutdown but no telescope is selected"
            await self.msg(txt, "yellow")

    @qs.asyncSlot()
    async def weatherStop(self):
        if self.telescope is not None:
            if await self.user.aget_is_access():
                txt = f"REQUEST: weather stop"
                await self.msg(txt, "yellow")
                await self.tic_telescopes[self.active_tel].weather_stop()
            else:
                txt = "WARNING: U don't have controll"
                self.WarningWindow(txt)
        else:
            txt = f"REQUEST: weather stop but no telescope is selected"
            await self.msg(txt, "yellow")

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        txt="REQUEST: Control"
        self.obsGui.main_form.control_e.setText(txt)
        self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        try: await self.user.aput_break_control()
        except Exception as e: pass
        try:
            await self.user.aput_take_control(12*3600)
            self.upload_plan()
            self.update_plan(self.active_tel)
        except Exception as e:
            pass
        await self.msg(txt,"green")

    async def user_update(self, event):
        # STAGE2
        # to jakos zupelnie nie idzie
        # jakos trzeba sprawdzac czy mamy kontrole nad wszystkimi teleskopami
        self.TICuser=self.user.current_user
        self.acces=bool(await self.user.aget_is_access())
        txt=str(self.TICuser["name"])
        self.obsGui.main_form.control_e.setText(txt)
        if self.acces:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(0,150,0);")
            await self.msg(f"TELEMETRY: user {txt} have controll","green")
        elif  self.user.current_user["name"]==self.myself:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(150,0,0);")
            await self.msg(f"TELEMETRY: user {txt} DON'T have controll","yellow")
        else:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            await self.msg(f"TELEMETRY: user {txt} have controll","black")

# ############ INNE ##############################

    # STAGE 2
    # to nie bedzie na razie obslugiwane
    def GuiderPassiveOnOff(self):
        if self.auxGui.guider_tab.guiderView.guiderCameraOn_c.checkState():
            self.guider_failed = 1
            self.guider_passive_dx = []
            self.guider_passive_dy = []

    def updateWeather(self):
        try:
            self.auxGui.welcome_tab.wind_e.setText(f"{self.telemetry_wind:.1f} [m/s]")
            self.auxGui.welcome_tab.windDir_e.setText(f"{self.telemetry_wind_direction:.0f} [deg]")
            self.auxGui.welcome_tab.temp_e.setText(f"{self.telemetry_temp:.1f} [C]")
            self.auxGui.welcome_tab.hummidity_e.setText(f"{self.telemetry_humidity:.0f} [%]")
            self.auxGui.welcome_tab.pressure_e.setText(f"{self.telemetry_pressure:.1f} [hPa]")

            if float(self.telemetry_wind)>float(self.cfg_wind_limit):
                self.auxGui.welcome_tab.wind_e.setStyleSheet("color: red; background-color: rgb(235,235,235);")
            else:
                self.auxGui.welcome_tab.wind_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")

            if float(self.telemetry_humidity)>float(self.cfg_humidity_limit):
                self.auxGui.welcome_tab.hummidity_e.setStyleSheet("color: red; background-color: rgb(235,235,235);")
            else:
                self.auxGui.welcome_tab.hummidity_e.setStyleSheet("color: black; background-color: rgb(235,235,235);")

            self.obsGui.main_form.skyView.updateWind(self)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'TOI: updateWeather: {e}')

    def ephem_update(self,tmp):
        self.ephem_utc = float(self.ephemeris.utc)

    def WarningWindow(self,txt):
        #await self.msg(txt, "red")
        self.tmp_box=QtWidgets.QMessageBox()
        self.tmp_box.setWindowTitle("TOI message")
        self.tmp_box.setText(txt)
        self.tmp_box.show()

    @qs.asyncSlot()
    async def msg(self, txt, color):
        c = QtCore.Qt.black
        if "yellow" in color: c = QtCore.Qt.darkYellow
        if "green" in color: c = QtCore.Qt.darkGreen
        if "red" in color: c = QtCore.Qt.darkRed
        self.obsGui.main_form.msg_e.setTextColor(c)
        ut = str(self.ut).split()[1].split(":")[0] + ":" + str(self.ut).split()[1].split(":")[1]
        txt = ut + " " + txt
        if txt.split()[1] != "TELEMETRY:":
            self.obsGui.main_form.msg_e.append(txt)
            # try:
            #     w: MsgJournalPublisher = self.nats_journal_toi_msg
            #     info = f"TOI {self.myself} {txt}"
            #     await w.log('INFO', info)
            # except Exception as e:
            #     pass


        # LOG dzialan
        # if os.path.exists(self.msg_log_file):
        #     pass
        # else:
        #     with open(self.msg_log_file,"w") as log_file:
        #         log_file.write("")
        # with open(self.msg_log_file,"r") as log_file:
        #     tmp = log_file.read().splitlines()
        #     log = "\n".join(tmp[-1*int(self.msg_log_lines):])
        #
        # with open(self.msg_log_file,"w") as log_file:
        #     log = log + "\n" + txt + "\n"
        #     log_file.write(log)

    def update_oca(self):
        self.obsGui.main_form.update_table()


    def reset_ob(self):
        templeate = {"run":False,"done":False,"uobi":None,"origin":None,"slot_time":None,"start_time":None}
        self.ob = {t:copy.deepcopy(templeate) for t in self.local_cfg["toi"]["telescopes"]}


    def variables_init(self):


        # tu pobieramy konfiguracje z NATS
        self.client_cfg = self.observatory_model.get_client_configuration()
        nats_cfg = self.observatory_model.get_telescopes_configuration()

        # a tu tworzymy konfiguracje teleskopow dla kazdego teleskopu wk06, zb08, jk15, etc.
        self.nats_cfg = {k:{} for k in nats_cfg.keys()}

        self.toi_status = {}

        for k in self.nats_cfg.keys():

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

            #print(self.nats_cfg)

        # statusty wszystkich teleskopow

        templeate = {
            "mount_motor":{"val":None, "pms_topic":".mount.motorstatus"},
            "mount_tracking": {"val": None, "pms_topic": ".mount.tracking"},
            "mount_slewing": {"val": None, "pms_topic": ".mount.slewing"},
            "dome_shutterstatus": {"val": None, "pms_topic": ".dome.shutterstatus"},
            "dome_slewing": {"val": None, "pms_topic": ".dome.slewing"},
            "fw_position": {"val": None, "pms_topic": ".filterwheel.position"},
            "ccd_state": {"val": None, "pms_topic": ".camera.camerastate"},

        }

        self.oca_tel_state = {k:copy.deepcopy(templeate) for k in self.local_cfg["toi"]["telescopes"]}

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

        #print(geometry)
        self.obs_window_geometry = [geometry.left(),geometry.top(),850,400]
        self.mnt_geometry = [self.obs_window_geometry[0],self.obs_window_geometry[1]+self.obs_window_geometry[3]+100,850,400]
        self.aux_geometry = [self.obs_window_geometry[0]+self.obs_window_geometry[2]+60,self.obs_window_geometry[1],510,550]
        self.instrument_geometry = [self.aux_geometry[0],self.aux_geometry[1]+self.aux_geometry[3]+70,510,300]
        self.plan_geometry = [self.aux_geometry[0]+self.aux_geometry[2]+10,self.aux_geometry[1],490,1100]

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
        self.exp_prog_status = {"plan_runner_status":"","ndit_req":1,"ndit":0,"dit_exp":0,"dit_start":0}

        templeate = {"ob_started":False,"ob_done":False,"ob_expected_time":0.1,"ob_start_time":0,"ob_program":None}
        self.ob_prog_status = {t:copy.deepcopy(templeate) for t in self.local_cfg["toi"]["telescopes"]}

        # STAGE 2
        self.reset_ob()

        self.nats_plan_status = {"current_i":-1,"next_i":-1,"plan":[]}

        self.nats_exp_prog_status = {}  # ten sluzy tylko do czytania z nats
        self.nats_ob_progress = {}      # ten sluzy tylko do czytania z nats
        self.nats_focus_status = {}     #  tak samo

        self.fits_exec=False

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


        self.telescope_switch_status = {"plan":None}

        self.nats_toi_plan_status = {}
        self.nats_toi_ob_status = {}
        self.nats_toi_exp_status = {}

        self.nats_toi_focus_status = {}


        self.nats_pub_toi_status = {}

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
        await self.msg(f"*** TELESCOPE OPERATOR INTERFACE ***","green")

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
