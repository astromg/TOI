#!/usr/bin/env python3

# ----------------
# 1.08.2022
# Marek Gorski
# ----------------
import asyncio
import functools
import logging
import requests
import socket
import json
import time
import pwd
import os

from PyQt5 import QtWidgets, QtCore
import sys
import qasync as qs

import paho.mqtt.client as mqtt

from ocaboxapi import ClientAPI, Observatory
from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget

from obs_gui import ObsGui
from aux_gui import AuxGui

from toi_lib import *
from mnt_gui import MntGui
from plan_gui import PlanGui
from instrument_gui import InstrumentGui
from fits_save import *

from calcFocus import calc_focus as calFoc
from ffs_lib.ffs import FFS

logging.basicConfig(level='INFO')
logger = logging.getLogger(__name__)

CCD_MAX_TEMP = -49.

class TOI(QtWidgets.QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    APP_NAME = "TOI app"

    def __init__(self, loop=None, client_api=None, app=None):
        self.app = app
        super().__init__(loop=loop, client_api=client_api)
        self.setWindowTitle(self.APP_NAME)
        self.setLayout(QtWidgets.QVBoxLayout())

        host = socket.gethostname()
        user = pwd.getpwuid(os.getuid())[0]
        self.myself=f'{user}@{host}'

        self.observatory = ["-24:35:24","-70:11:47","2800"]

        self.observatory_model = Observatory()
        self.observatory_model.connect(client_api)

        # geometry settings

        geometry = QtWidgets.QDesktopWidget().screenGeometry(0)

        #print(geometry)
        self.obs_window_geometry = [geometry.left(),geometry.top(),850,400]
        self.mnt_geometry = [self.obs_window_geometry[0],self.obs_window_geometry[1]+self.obs_window_geometry[3]+100,850,400]
        self.aux_geometry = [self.obs_window_geometry[0]+self.obs_window_geometry[2]+60,self.obs_window_geometry[1],510,550]
        self.instrument_geometry = [self.aux_geometry[0],self.aux_geometry[1]+self.aux_geometry[3]+70,510,300]
        self.plan_geometry = [self.aux_geometry[0]+self.aux_geometry[2]+10,self.aux_geometry[1],490,1100]

        self.tic_conn="unknown"
        self.fw_conn="unknown"
        self.mount_conn="unknown"
        self.dome_conn="unknown"
        self.rotator_conn="unknown"
        self.inst_conn="unknown"
        self.focus_conn="unknown"
        self.covercalibrator_conn="unknown"

        self.cfg_wind_limits = 36

        self.nextOB_ok = None

        # weather telemetry
        self.telemetry_temp = None
        self.telemetry_wind = None

        # aux zmienne
        self.fits_exec=False
        self.dit_start=0
        self.dit_exp=0
        self.ndit=0
        self.ndit_req=1
        self.plan_runner_origin=""
        self.plan_runner_status=""
        self.ob={"run":False,"done":False}
        self.autofocus_started=False
        self.acces=True

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15","sim"]  # wg25 is not working
        self.obs_tel_in_table = self.obs_tel_tic_names

        # active telescope & universal
        self.ut=str(ephem.now())
        self.active_tel_i=None
        self.active_tel=None

        # ccd
        self.binxy_changed=False

        # filter wheel
        self.filter = None

        # dome
        self.dome_con=False
        self.dome_shutterstatus="--"
        self.dome_az="--"
        self.dome_status="--"

        # mount
        self.mount_con=False
        self.mount_motortatus=False
        self.mount_ra="--:--:--"
        self.mount_dec="--:--:--"
        self.mount_alt=None
        self.mount_az="---.--"
        self.mount_parked="--"
        self.mount_slewing="--"
        self.mount_tracking="--"

        # focus
        self.focus_editing=False
        self.focus_value=0

        # rotator
        self.rotator_pos="unknown"

        # program
        self.req_ra=""
        self.req_dec=""
        self.req_epoch=""
        self.program_id=""
        self.program_name=""

        # window generation

        self.obsGui=ObsGui(self, loop=self.loop, client_api=self.client_api)
        self.obsGui.show()
        self.obsGui.raise_()

        self.mntGui = MntGui(self, loop=self.loop, client_api=self.client_api)
        self.mntGui.show()
        self.mntGui.raise_()

        self.instGui = InstrumentGui(self, loop=self.loop, client_api=self.client_api)
        self.instGui.show()
        self.instGui.raise_()

        self.planGui = PlanGui(self, loop=self.loop, client_api=self.client_api)
        self.planGui.show()
        self.planGui.raise_()

        self.auxGui = AuxGui(self)
        self.auxGui.show()
        self.auxGui.raise_()

        self.msg=self.obsGui.main_form.msg
        self.oca_tel_stat()

        # self.dome = self.parent.observatory_model.get_telescope(tel).get_dome()
        # self.mount = self.parent.observatory_model.get_telescope(tel).get_mount()
        # self.ccd = self.parent.observatory_model.get_telescope(tel).get_camera()
        # self.fw = self.parent.observatory_model.get_telescope(tel).get_filterwheel()
        #
        # self.add_background_task(self.dome.asubscribe_shutterstatus(self.obsGui.dome_update))
        # self.add_background_task(self.dome.asubscribe_slewing(self.obsGui.dome_update))
        #
        # self.add_background_task(self.mount.asubscribe_tracking(self.obsGui.mount_update))
        # self.add_background_task(self.mount.asubscribe_slewing(self.obsGui.mount_update))
        # self.add_background_task(self.mount.asubscribe_motorstatus(self.obsGui.mount_update))
        #
        # self.add_background_task(self.ccd.asubscribe_ccdtemperature(self.obsGui.instrument_update))
        # self.add_background_task(self.ccd.asubscribe_camerastate(self.obsGui.instrument_update))
        # self.add_background_task(self.fw.asubscribe_position(self.obsGui.instrument_update))

        self.add_background_task(self.TOItimer())


        # MQTT
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_broker = 'docker.oca.lan'
            self.mqtt_port = 1883
            self.mqtt_topic_weather = 'weather'
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            self.mqtt_client.message_callback_add(self.mqtt_topic_weather, self.on_weather_message)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.loop_start()
        except: pass


    def on_weather_message(self, client, userdata, message):
        weather = message.payload.decode('utf-8')
        weather_dict = json.loads(weather)
        self.telemetry_temp = weather_dict["temp"]
        self.telemetry_wind = weather_dict["wind"]
        self.auxGui.welcome_tab.wind_e.setText(f"{self.telemetry_wind} [km/h]")
        if int(self.telemetry_wind)>self.cfg_wind_limits:
            self.auxGui.tabWidget.setCurrentIndex(0)
            self.auxGui.welcome_tab.wind_e.setStyleSheet("color: red;")
        else:
            self.auxGui.welcome_tab.wind_e.setStyleSheet("color: black;")
        self.auxGui.welcome_tab.temp_e.setText(f"{self.telemetry_temp} [C]")

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0: self.mqtt_client.subscribe((self.mqtt_topic_weather, 1))


    # ############ all telescopes states ####################3

    def oca_tel_stat(self):

        self.tel={}
        self.tel["wk06"]=TelBasicState(self,"wk06")
        self.tel["zb08"]=TelBasicState(self,"zb08")
        self.tel["jk15"]=TelBasicState(self,"jk15")
        # self.tel["wg25"]=TelBasicState(self,"wg25")  # wg25 is not working (mikolaj)
        #self.tel["sim"]=TelBasicState(self,"sim")

        self.obsGui.main_form.update_table()



    #  ############# ZMIANA TELESKOPU ### TELESCOPE SELECT #################
    async def teleskop_switched(self):
        tel=self.obs_tel_tic_names[self.active_tel_i]
        self.active_tel = tel
        if tel == "zb08": self.cfg_focus_directory = "../../Desktop/fits_zb08/focus/actual"
        elif tel == "jk15": self.cfg_focus_directory = "../../Desktop/fits_jk15/focus/actual"
        self.cfg_focus_record_file = "./focus_data.txt"
        self.catalog_file="./object_catalog.txt"
        self.overhed = 20

        #self.dome = self.tel[self.active_tel].dome
        #self.mount = self.tel[self.active_tel].mount
        #self.ccd =  self.tel[self.active_tel].ccd
        #self.fw =  self.tel[self.active_tel].fw


        self.dome_con=False
        self.dome_az="--"

        txt=f"{tel} selected"
        self.msg(txt,"yellow")

        self.telescope = self.observatory_model.get_telescope(tel)
        #await self.stop_background_tasks()
        self.user = self.telescope.get_access_grantor()
        self.dome = self.telescope.get_dome()
        self.mount = self.telescope.get_mount()
        self.cover = self.telescope.get_covercalibrator()
        self.focus = self.telescope.get_focuser()
        self.ccd = self.telescope.get_camera()
        self.fw = self.telescope.get_filterwheel()
        self.rotator = self.telescope.get_rotator()
        self.cctv = self.telescope.get_cctv()
        self.planrunner = self.telescope.get_observation_plan()


        self.planrunner.add_info_callback('exec_json', self.PlanRun1)
        #self.planrunner.add_info_callback('c_sequences', self.TestCall)
        #self.planrunner.add_info_callback('c_subcommands', self.PlanRun1)
        #self.planrunner.add_info_callback('c_commands', self.PlanRun1)
        #self.planrunner.add_info_callback('stream_5', self.TestCall)
        #self.planrunner.add_info_callback('stream_1', self.PlanRun5)




        self.add_background_task(self.user.asubscribe_current_user(self.user_update))
        #self.add_background_task(self.user.asubscribe_is_access(self.user_update))

        self.add_background_task(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update))
        self.add_background_task(self.dome.asubscribe_az(self.domeAZ_update))
        self.add_background_task(self.dome.asubscribe_slewing(self.domeStatus_update))
        self.add_background_task(self.focus.asubscribe_fansstatus(self.domeFans_update))

        #self.add_background_task(self.mount.asubscribe_connected(self.mountCon_update))
        self.add_background_task(self.mount.asubscribe_ra(self.radec_update))
        self.add_background_task(self.mount.asubscribe_dec(self.radec_update))
        self.add_background_task(self.mount.asubscribe_az(self.radec_update))
        self.add_background_task(self.mount.asubscribe_alt(self.radec_update))
        self.add_background_task(self.mount.asubscribe_tracking(self.mount_update))
        self.add_background_task(self.mount.asubscribe_slewing(self.mount_update))
        self.add_background_task(self.mount.asubscribe_motorstatus(self.mountMotors_update))
        #
        self.add_background_task(self.cover.asubscribe_coverstate(self.covers_update))
        #
        #self.add_background_task(self.fw.asubscribe_connected(self.filterCon_update))
        self.add_background_task(self.fw.asubscribe_names(self.filterList_update))
        self.add_background_task(self.fw.asubscribe_position(self.filter_update))
        #
        self.add_background_task(self.focus.asubscribe_position(self.focus_update))
        self.add_background_task(self.focus.asubscribe_ismoving(self.focus_update))
        #
        #self.add_background_task(self.rotator.asubscribe_connected(self.rotatorCon_update))
        self.add_background_task(self.rotator.asubscribe_position(self.rotator_update))
        self.add_background_task(self.rotator.asubscribe_mechanicalposition(self.rotator_update))
        self.add_background_task(self.rotator.asubscribe_ismoving(self.rotator_update))
        #
        # #self.add_background_task(self.ccd.asubscribe_sensorname(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_ccdtemperature(self.ccd_temp_update))
        self.add_background_task(self.ccd.asubscribe_setccdtemperature(self.ccd_temp_update))
        self.add_background_task(self.ccd.asubscribe_binx(self.ccd_bin_update))
        self.add_background_task(self.ccd.asubscribe_biny(self.ccd_bin_update))
        self.add_background_task(self.ccd.asubscribe_camerastate(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_cooleron(self.ccd_cooler_update))
        #self.add_background_task(self.ccd.asubscribe_coolerpower(self.ccd_cooler_update))
        self.add_background_task(self.ccd.asubscribe_gain(self.ccd_gain_update))
        #self.add_background_task(self.ccd.asubscribe_readoutmodes(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_readoutmode(self.ccd_rm_update))
        self.add_background_task(self.ccd.asubscribe_imageready(self.ccd_imageready))

        self.add_background_task(self.TOItimer())
        self.add_background_task(self.TOItimer0())

        await self.stop_background_tasks()
        await self.run_background_tasks()

        filter_list = await self.fw.aget_names() # To jest dziwny slownik
        self.filter_list = [key for key, value in sorted(filter_list.items(), key=lambda item: item[1])]

        self.mntGui.updateUI()
        self.auxGui.updateUI()
        self.planGui.updateUI()
        self.instGui.updateUI()
        self.mntGui.telFilter_s.addItems(self.filter_list)

        self.catalog = readCatalog(self.catalog_file)
        completer = QtWidgets.QCompleter(self.catalog)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.mntGui.target_e.setCompleter(completer)


        self.obsGui.main_form.shutdown_p.clicked.connect(self.shutdown)
        self.obsGui.main_form.weatherStop_p.clicked.connect(self.weatherStop)
        self.obsGui.main_form.EmStop_p.clicked.connect(self.EmStop)

        #self.force_update()


    # ################### METODY POD SUBSKRYPCJE ##################

    def test3(self,tmp):
        print("========== TMP TEST 3 ==========================")

    def test4(self,tmp):
        print("========== TMP TEST 4 ==========================")

    @qs.asyncSlot()
    async def force_update(self):
        print("====== UPDATE START ======")
        self.msg(" UPDATE START ","red")
        await self.mountMotors_update(None)
        await self.filter_update(None)
        await self.focus_update(None)
        await self.domeAZ_update(None)
        await self.domeStatus_update(None)
        await self.domeShutterStatus_update(None)
        await self.radec_update(None)
        await self.mount_update(None)
        await self.covers_update(None)
        await self.domeFans_update(None)
        await self.ccd_update(None)
        await self.ccd_bin_update(None)
        await self.ccd_rm_update(None)
        await self.ccd_gain_update(None)
        await self.ccd_temp_update(None)
        await self.ccd_cooler_update(None)
        print("====== UPDATE DONE ======")
        self.msg(" UPDATE DONE ", "red")





    async def TOItimer0(self):
        while True:

            self.tic_conn = True

            if self.tic_conn == True:

                if self.active_tel=="zb08":
                    tel_url = "http://192.168.7.110:11111/api/v1/"
                elif self.active_tel=="jk15":
                    tel_url = "http://192.168.7.120:11111/api/v1/"
                elif self.active_tel=="wk06":
                    tel_url = "http://192.168.7.100:11111/api/v1/"
                else:
                    tel_url = "http://192.168.7.666:11111/api/v1/"

                tmp=self.mount_conn
                quest=tel_url+"telescope/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.mount_conn = True
                    else: self.mount_conn = False
                else: self.mount_conn = False
                if self.mount_conn != tmp:
                    if self.mount_conn: self.msg("Mount CONNECTED","green")
                    else: self.msg("Mount DISCONNECTED","red")

                tmp=self.dome_conn
                quest=tel_url+"dome/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.dome_conn = True
                    else: self.dome_conn = False
                else: self.dome_conn = False
                if self.dome_conn != tmp:
                    if self.dome_conn: self.msg("Dome CONNECTED","green")
                    else: self.msg("Dome DISCONNECTED","red")

                tmp=self.rotator_conn
                quest=tel_url+"rotator/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.rotator_conn = True
                    else: self.rotator_conn = False
                else: self.rotator_conn = False
                if self.rotator_conn != tmp:
                    if self.rotator_conn: self.msg("Rotator CONNECTED","green")
                    else: self.msg("Rotator DISCONNECTED","red")

                tmp=self.fw_conn
                quest=tel_url+"filterwheel/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.fw_conn = True
                    else: self.fw_conn = False
                else: self.fw_conn = False
                if self.fw_conn != tmp:
                    if self.fw_conn: self.msg("Filter wheel CONNECTED","green")
                    else: self.msg("Filter wheel DISCONNECTED","red")

                tmp=self.focus_conn
                quest=tel_url+"focuser/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.focus_conn = True
                    else: self.focus_conn = False
                else: self.focus_conn = False
                if self.focus_conn != tmp:
                    if self.focus_conn: self.msg("Focus CONNECTED","green")
                    else: self.focus_conn("Focus DISCONNECTED","red")

                tmp=self.inst_conn
                quest=tel_url+"camera/0/connected"
                r=requests.get(quest,timeout=(1))
                if r.status_code == 200:
                    r=r.json()
                    if bool(r["Value"]): self.inst_conn = True
                    else: self.inst_conn = False
                else: self.inst_conn = False
                if self.inst_conn != tmp:
                    if self.inst_conn: self.msg("Instrument CONNECTED","green")
                    else: self.msg("Instrument DISCONNECTED","red")

            await asyncio.sleep(5)

    async def TOItimer(self):
        while True:
            self.time=time.perf_counter()

            if self.ob["run"] and "name" in self.ob.keys():
                txt = self.ob["name"]
                if "seq" in self.ob.keys():
                    txt = txt + " " + self.ob["seq"]
                self.planGui.ob_e.setText(txt)

                if "seq" in self.ob.keys():
                    self.instGui.ccd_tab.Select2_r.setChecked(True)
                    self.instGui.ccd_tab.inst_Seq_e.setText(self.ob["seq"])
                if "ra" in self.ob.keys() and "dec" in self.ob.keys():
                    self.mntGui.setEq_r.setChecked(True)
                    self.mntGui.nextRa_e.setText(self.ob["ra"])
                    self.mntGui.nextDec_e.setText(self.ob["dec"])
                    self.mntGui.updateNextRaDec()
                    if "name" in self.ob.keys():
                        self.mntGui.target_e.setText(self.ob["name"])
                        self.mntGui.target_e.setStyleSheet("background-color: white; color: black;")
                if "name" in self.ob.keys():
                      self.instGui.ccd_tab.inst_object_e.setText(self.ob["name"])

            else: self.planGui.ob_e.setText("")

            if self.ob["done"] and self.planGui.next_i==-1:
                self.ob["run"]=False


            if self.ob["run"] and self.ob["done"]:
                if self.planGui.next_i > 0 and self.planGui.next_i < len(self.planGui.plan):
                    await self.plan_start()

            elif self.ob["run"] and "name" in self.ob.keys():

                if "wait" in self.ob.keys() and "ob_start_time" in self.ob.keys():
                    dt = self.time - self.ob["ob_start_time"]
                    if float(dt) > float(self.ob["wait"]):
                        self.ob["done"]=True
                        self.planGui.done.append(self.ob["uid"])
                        self.msg(f"{self.ob['name']} {self.ob['wait']} s DONE","green")
                        self.planGui.current_i=-1

                if "wait_ut" in self.ob.keys():
                    req_ut = str(self.ob["wait_ut"])
                    ut = str(self.almanac["ut"]).split()[1]
                    #print(ut,req_ut)
                    ut = 3600*float(ut.split(":")[0])+60*float(ut.split(":")[1])+float(ut.split(":")[2])
                    req_ut = 3600*float(req_ut.split(":")[0])+60*float(req_ut.split(":")[1])+float(req_ut.split(":")[2])
                    if req_ut < ut :
                        self.ob["done"]=True
                        self.planGui.done.append(self.ob["uid"])
                        self.msg(f"{self.ob['name']} UT {self.ob['wait_ut']} DONE","green")
                        self.planGui.current_i=-1


                if "wait_sunrise" in self.ob.keys():
                    if float(self.almanac["sun_alt"]) > float(self.ob["wait_sunrise"]):
                        self.ob["done"]=True
                        self.planGui.done.append(self.ob["uid"])
                        self.msg(f"{self.ob['name']} sunrise {self.ob['wait_sunrise']} DONE","green")
                        self.planGui.current_i=-1

                if "wait_sunset" in self.ob.keys():
                    if float(self.almanac["sun_alt"]) < float(self.ob["wait_sunset"]):
                        self.ob["done"]=True
                        self.planGui.done.append(self.ob["uid"])
                        self.msg(f"{self.ob['name']} sunset {self.ob['wait_sunset']} DONE","green")
                        self.planGui.current_i=-1

            if self.dit_start>0:

                txt=""
                if self.plan_runner_status=="exposing":
                    txt=txt+"exposing: "
                elif self.plan_runner_status=="exp done":
                    txt=txt+"DONE "

                p=int(100*(self.ndit/self.ndit_req))
                self.instGui.ccd_tab.inst_NditProg_n.setValue(p)
                txt=txt+f"{int(self.ndit)}/{int(self.ndit_req)}"

                dt=self.time-self.dit_start
                if dt>self.dit_exp:
                    dt=self.dit_exp
                if int(self.dit_exp)==0: p=100
                else: p=int(100*(dt/self.dit_exp))
                self.instGui.ccd_tab.inst_DitProg_n.setValue(p)
                txt2=f"{int(dt)}/{int(self.dit_exp)}"

                self.instGui.ccd_tab.inst_NditProg_n.setFormat(txt)
                self.instGui.ccd_tab.inst_DitProg_n.setFormat(txt2)

            else:
                self.instGui.ccd_tab.inst_NditProg_n.setFormat("")
                #self.instGui.ccd_tab.inst_DitProg_n.setFormat("")

            self.ut = str(ephem.now())
            self.almanac = Almanac(self.observatory)
            self.obsGui.main_form.ojd_e.setText(f"{self.almanac['jd']:.6f}")
            self.obsGui.main_form.sid_e.setText(str(self.almanac["sid"]).split(".")[0])
            date=str(self.almanac["ut"]).split()[0]
            date=date.split("/")[2]+"/"+date.split("/")[1]+"/"+date.split("/")[0]
            ut=str(self.almanac["ut"]).split()[1]
            self.obsGui.main_form.date_e.setText(str(date))
            self.obsGui.main_form.ut_e.setText(str(ut))
            self.obsGui.main_form.skyView.updateAlmanac()
            #self.obsGui.main_form.skyView.updateRadar()
            self.planGui.update_table()


            # Connection status update


            if self.tic_conn == True:
                self.obsGui.main_form.ticStatus2_l.setText("\u262F")
                self.obsGui.main_form.tic_l.setStyleSheet("color: rgb(0, 0, 0);")
            else:
                self.obsGui.main_form.ticStatus2_l.setText("\U0001F534")
                self.obsGui.main_form.tic_l.setStyleSheet("color: rgb(150,0,0);")

            if self.mount_conn == True:                                       # bo moze przyjmowac jeszcze False i "unknown"
                self.mntGui.mntConn2_l.setText("\U0001F7E2")
                self.mntGui.mntConn1_l.setStyleSheet("color: rgb(0,150,0);")
            else:
                self.mntGui.mntConn2_l.setText("\U0001F534")
                self.mntGui.mntConn1_l.setStyleSheet("color: rgb(150,0,0);")

            if self.dome_conn == True:
                self.mntGui.domeConn2_l.setText("\U0001F7E2")
                self.mntGui.domeConn1_l.setStyleSheet("color: rgb(0,150,0);")
            else:
                self.mntGui.domeConn2_l.setText("\U0001F534")
                self.mntGui.domeConn1_l.setStyleSheet("color: rgb(150,0,0);")

            if self.rotator_conn == True:
                self.mntGui.comRotator1_l.setText("\U0001F7E2")
                self.mntGui.telRotator1_l.setStyleSheet("color: rgb(0,150,0);")
            else:
                self.mntGui.comRotator1_l.setText("\U0001F534")
                self.mntGui.telRotator1_l.setStyleSheet("color: rgb(150,0,0);")

            if self.fw_conn == True:
                self.mntGui.comFilter_l.setText("\U0001F7E2")
                self.mntGui.telFilter_l.setStyleSheet("color: rgb(0,150,0);")
            else:
                self.mntGui.comFilter_l.setText("\U0001F534")
                self.mntGui.telFilter_l.setStyleSheet("color: rgb(150,0,0);")

            if self.focus_conn == True:
                self.mntGui.focusConn_l.setText("\U0001F7E2")
                self.mntGui.telFocus_l.setStyleSheet("color: rgb(0,150,0);")
            else:
                self.mntGui.focusConn_l.setText("\U0001F534")
                self.mntGui.telFocus_l.setStyleSheet("color: rgb(150,0,0);")


            if self.inst_conn == True:
                self.instGui.tab.setTabText(0,"\U0001F7E2 CCD")
            else:
                self.instGui.tab.setTabText(0,"\U0001F534 CCD")

            await asyncio.sleep(1)


    # ############ PLAN RUNNER CALLBACK ##########################


    @qs.asyncSlot()
    async def PlanRun1(self,info):
        print(info)
        # AUTOFOCUS
        if self.autofocus_started:
            if "id" in info.keys():
                if info["id"]=="auto_focus" and info["started"]==True and info["done"]==True:
                    self.autofocus_started=False
                    self.msg("Auto-focus sequence finished","black")
                    max_sharpness_focus, calc_metadata = calFoc.calculate(self.cfg_focus_directory,method=self.focus_method)
                    coef = calc_metadata["poly_coef"]
                    focus_list_ret = calc_metadata["focus_values"]
                    sharpness_list_ret = calc_metadata["sharpness_values"]
                    status = calc_metadata["status"]

                    fit_x = numpy.linspace(min(focus_list_ret), max(focus_list_ret), 100)
                    if len(coef)>3:
                        fit_y = coef[0]* fit_x**4 + coef[1]*fit_x**3 + coef[2]*fit_x**2 +  coef[3]*fit_x + coef[4]
                    elif len(coef)>1:
                        fit_y = coef[0]* fit_x**2 + coef[1]*fit_x + coef[2]

                    self.auxGui.focus_tab.x=focus_list_ret
                    self.auxGui.focus_tab.y=sharpness_list_ret
                    self.auxGui.focus_tab.fit_x=fit_x
                    self.auxGui.focus_tab.fit_y=fit_y
                    if status == "ok":
                        self.auxGui.focus_tab.result_e.setText(f"{int(max_sharpness_focus)}")
                        self.auxGui.focus_tab.max_sharp=max_sharpness_focus
                        await self.focus.aput_move(int(max_sharpness_focus))
                        if self.filter != None and self.telemetry_temp != None:
                            txt = f"{self.ut} {self.telemetry_temp} {self.filter} {int(max_sharpness_focus)} \n"
                            with open(self.cfg_focus_record_file,"a+") as plik:
                                plik.seek(0)
                                plik.write(txt)
                    else:
                        self.auxGui.focus_tab.result_e.setText(status)
                        self.auxGui.focus_tab.max_sharp=None
                    self.auxGui.focus_tab.update()
                    self.auxGui.tabWidget.setCurrentIndex(1)


        # OTHER
        if "id" in info.keys():
            self.program_id = info["id"]
            ut=str(self.almanac["ut"]).split()[1].split(":")[0]+":"+str(self.almanac["ut"]).split()[1].split(":")[1]
            txt = f"--------  {ut}  --------  {self.program_id}  --------\n {info}\n"
            self.planGui.prog_call_e.append(txt)

            if self.plan_runner_origin=="Plan Gui" and "_" in info["id"]:
                cur_i = info["id"].split("_")[1]
                self.planGui.update_table()


        if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
            if info["name"] == "Night plan" and info["started"] and not info["done"]:
                self.msg(f"Sequence started","black")

            elif info["name"] == "Night plan" and info["done"]:
                self.ob["done"] = True
                if "uid" in self.ob.keys():
                    self.planGui.done.append(self.ob["uid"])
                self.planGui.current_i = -1
                self.dit_start = 0
                self.instGui.ccd_tab.inst_DitProg_n.setFormat("IDLE")
                self.msg("Plan finished", "black")

            elif info["name"] == "SKYFLAT" and info["started"] and not info["done"]:  # SKYFLAT
                self.msg(f"AUTO FLAT program started", "black")                       # SKYFLAT

            elif info["name"] == "SKYFLAT" and info["done"]:
                self.msg(f"AUTO FLAT program finished", "black")


        if "exp_started" in info.keys() and "exp_done" in info.keys():
            if info["exp_started"] and not info["exp_done"]:
                self.ndit=float(info["n_exp"])
                self.ndit_req=float(info["exp_no"])
                self.dit_exp=float(info["exp_time"])
                self.dit_start=self.time
                self.plan_runner_status="exposing"
                self.msg(f"{self.dit_exp} [s] exposure started","black")

            elif info["exp_done"] and info["exp_saved"]:
                self.ndit=float(info["n_exp"])
                self.plan_runner_status="exp done"


        if "auto_exp_start" in info.keys() and "auto_exp_finnished" in info.keys():    # SKYFLAT
            if info["auto_exp_start"] and not info["auto_exp_finnished"]:
                self.ndit=0
                self.ndit_req=float(info["exp_no"])
                self.dit_exp=float(info["auto_exp_time"])
                self.dit_start=self.time
                self.plan_runner_status="exposing"
                self.msg(f"{self.dit_exp} [s] test exposure started","black")

            elif info["auto_exp_finnished"]:
                self.msg(f"test exposure done", "black")

        if "test_exp_mean" in info.keys():                                                        # SKYFLAT
            self.msg(f"mean {int(info['test_exp_mean'])} ADU measured", "black")



    # ############ AUTO FOCUS ##########################

    @qs.asyncSlot()
    async def auto_focus(self):
        program=""

        ok = False
        v0 = float(self.auxGui.focus_tab.last_e.text())
        step = float(self.auxGui.focus_tab.steps_e.text())
        number = float(self.auxGui.focus_tab.range_e.text())
        method = self.auxGui.focus_tab.method_s.currentText()
        if method == "RMS":
            self.focus_method = "rms"
            if number > 2:
                ok = True
            else: self.WarningWindow("Not enough STEPS number")
        elif method == "RMS_QUAD":
            self.focus_method = "rms_quad"
            if number > 4:
                ok = True
            else: self.WarningWindow("Not enough STEPS number")

        if ok:
            exp=self.instGui.ccd_tab.inst_Dit_e.text()
            if len(exp)==0:
                exp = 5
                self.msg("no exp specified. exp=5","red")

            seq = f"{int(number)}/"+str(self.curent_filter)+"/"+str(exp)
            pos = f"{int(v0)}/{int(step)}"
            program = f"FOCUS seq={seq} pos={pos}"

            #print(program)
            self.planrunner.load_nightplan_string('auto_focus', string=program, overwrite=True)
            await self.planrunner.arun_nightplan('auto_focus',step_id="00")
            self.fits_exec=True
            self.plan_runner_origin="auto_focus"
            self.program_name="auto_focus"
            self.autofocus_started=True



    # ############ PLAN RUNNER ##########################

    @qs.asyncSlot()
    async def plan_start(self):

        if self.planGui.next_i > -1 and self.planGui.next_i < len(self.planGui.plan):
            self.ob = self.planGui.plan[self.planGui.next_i]
            self.ob["done"]=False
            self.ob["run"]=True


            if "uid" in self.ob.keys():
                if self.ob["uid"] not in self.planGui.done:
                    if "type" in self.ob.keys() and "name" in self.ob.keys():
                        self.planGui.current_i = self.planGui.next_i

                        if self.ob["type"] == "STOP":
                            self.ob["done"]=False
                            self.ob["run"]=False
                            self.planGui.current_i = -1


                        if self.ob["type"] == "WAIT":
                            if "wait" in self.ob.keys():
                                self.ob["ob_start_time"] = self.time
                                self.ob["done"]=False
                                self.ob["run"]=True
                                self.msg(f"{self.ob['name']} {self.ob['wait']} s. start","black")
                            if "wait_ut" in self.ob.keys():
                                self.ob["done"]=False
                                self.ob["run"]=True
                                self.msg(f"{self.ob['name']} UT {self.ob['wait_ut']} start","black")
                            if "wait_sunset" in self.ob.keys():
                                self.ob["done"]=False
                                self.ob["run"]=True
                                self.msg(f"{self.ob['name']} sunset {self.ob['wait_sunset']} start","black")
                            if "wait_sunrise" in self.ob.keys():
                                self.ob["done"]=False
                                self.ob["run"]=True
                                self.msg(f"{self.ob['name']} sunrise {self.ob['wait_sunrise']} start","black")


                        if self.ob["type"] == "ZERO" and "block" in self.ob.keys():
                            program = self.ob["block"]
                            self.planrunner.load_nightplan_string('program', string=program, overwrite=True)
                            await self.planrunner.arun_nightplan('program', step_id="00")

                            self.program_name="program"
                            self.fits_exec=True
                            self.plan_runner_origin="Plan Gui"

                        if self.ob["type"] == "DARK" and "block" in self.ob.keys():
                            program = self.ob["block"]
                            self.planrunner.load_nightplan_string('program', string=program, overwrite=True)
                            await self.planrunner.arun_nightplan('program', step_id="00")

                            self.program_name="program"
                            self.fits_exec=True
                            self.plan_runner_origin="Plan Gui"

                        if self.ob["type"] == "DOMEFLAT" and "block" in self.ob.keys():
                            program = self.ob["block"]
                            self.planrunner.load_nightplan_string('program', string=program, overwrite=True)
                            await self.planrunner.arun_nightplan('program', step_id="00")

                            self.program_name="program"
                            self.fits_exec=True
                            self.plan_runner_origin="Plan Gui"


                        if self.ob["type"] == "SKYFLAT" and "block" in self.ob.keys():
                            program = self.ob["block"]
                            self.planrunner.load_nightplan_string('program', string=program, overwrite=True)
                            await self.planrunner.arun_nightplan('program', step_id="00")

                            self.program_name="program"
                            self.fits_exec=True
                            self.plan_runner_origin="Plan Gui"


                        if self.ob["type"] == "OBJECT" and "block" in self.ob.keys():
                            program = self.ob["block"]
                            if "comment" in program:
                                program = program.split("comment")[0]
                            self.planrunner.load_nightplan_string('program', string=program, overwrite=True)
                            await self.planrunner.arun_nightplan('program', step_id="00")

                            self.program_name="program"
                            self.fits_exec=True
                            self.plan_runner_origin="Plan Gui"

                        self.next_ob()

                else:
                    self.next_ob()

    def next_ob(self):
        self.planGui.next_i = self.planGui.next_i + 1
        self.planGui.update_table()

    @qs.asyncSlot()
    async def resume_program(self):
        await self.planrunner.astop_nightplan()
        await self.planrunner.arun_nightplan(self.program_name,step_id=self.program_id)

    @qs.asyncSlot()
    async def stop_program(self):
        await self.takeControl()
        self.msg("STOP requested","yellow")
        self.ob["run"]=False
        await self.planrunner.astop_nightplan()
        self.planGui.current_i = -1


    # ############ CCD ##################################

    async def ccd_imageready(self,event):
        if self.ccd.imageready:

            res = await self.ccd.aget_imagearray()
            image = self.ccd.imagearray
            image =  numpy.asarray(image)
            image = image.astype(numpy.uint16)

            stats = FFS(image)
            coo=[]
            adu=[]
            fwhm_x,fwhm_y=0,0
            th = 20
            coo,adu = stats.find_stars(threshold=th,kernel_size=9,fwhm=4)
            if len(coo)>3:
                fwhm_x,fwhm_y = stats.fwhm(saturation=45000)
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
            txt = txt + f"FWHM X/Y:".ljust(13)+f"{float(fwhm_x):.1f}/{float(fwhm_y):.1f}\n"

            txt = txt + f"min ADU:".ljust(17)  +f"{stats.min:.0f}".ljust(9)
            txt = txt + f"max ADU:".ljust(15)  +f"{stats.max:.0f}\n"

            txt = txt + f"mean/median:".ljust(15) +   f"{stats.mean:.0f}/{stats.median:.0f}".ljust(11)
            txt = txt + f"rms/sigma_q:".ljust(15)  +  f"{stats.rms:.0f}/{stats.sigma_quantile:.0f}\n"

            self.auxGui.fits_tab.fitsView.stat_e.setText(txt)
            ok_coo=[]
            self.auxGui.fits_tab.fitsView.update(image,sat_coo,ok_coo)

            if self.fits_exec:
                self.auxGui.tabWidget.setCurrentIndex(2)

    @qs.asyncSlot()
    async def ccd_Snap(self):
        if await self.user.aget_is_access():
            self.dit_start=0
            ok_ndit = False
            ok_exp = False
            ok_name = False
            ok_seq = False
            name=self.instGui.ccd_tab.inst_object_e.text().strip()
            if len(name)>0:
                ok_name=True
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            else:
                ok_name=False
                self.msg("OBJECT NAME required","red")
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")


            exp=self.instGui.ccd_tab.inst_Dit_e.text()
            ndit=self.instGui.ccd_tab.inst_Ndit_e.text()
            # Sprawdzanie formatu czasu etc.
            try:
                exp=float(exp)
                if exp>-0.0001:
                    ok_exp=True
                    self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            except:
                ok_exp=False
                self.msg("Wrong EXP TIME format","red")
                self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            try:
                if len(ndit)==0:
                    self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                    ndit=1
                ndit=int(ndit)
                if ndit>0:
                    ok_ndit=True
                    self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            except:
                ok_exp=False
                self.msg("Wrong N format","red")
                self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            if ok_exp and ok_ndit:
                seq = "1/"+str(self.curent_filter)+"/"+str(exp)
                ok_seq = True

            if ok_name and ok_seq:
                self.ndit=0
                txt = f"SNAP {name} seq={seq} dome_follow=off \n"

            self.planrunner.load_nightplan_string('manual', string=txt, overwrite=True)
            await self.planrunner.arun_nightplan('manual', step_id="00")
            self.program_name = "manual"
            self.fits_exec = True


        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)

    @qs.asyncSlot()
    async def ccd_startExp(self):
        if await self.user.aget_is_access():
            self.dit_start=0
            ok_ndit = False
            ok_exp = False
            ok_name = False
            ok_seq = False

            name=self.instGui.ccd_tab.inst_object_e.text().strip()

            if len(name)>0:
                ok_name=True
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            else:
                ok_name=False
                self.msg("OBJECT NAME required","red")
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
                except:
                    ok_exp=False
                    self.msg("Wrong EXP TIME format","red")
                    self.instGui.ccd_tab.inst_Dit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

                try:
                    if len(ndit)==0:
                        self.instGui.ccd_tab.inst_Ndit_e.setText("1")
                        ndit=1
                    ndit=int(ndit)
                    if ndit>0:
                        ok_ndit=True
                        self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
                except:
                    ok_exp=False
                    self.msg("Wrong N format","red")
                    self.instGui.ccd_tab.inst_Ndit_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

                if ok_exp and ok_ndit:
                    seq = str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                    ok_seq = True

            if self.instGui.ccd_tab.Select2_r.isChecked():
                seq = self.instGui.ccd_tab.inst_Seq_e.text().strip()

                if len(seq)>0:   # Tutaj trzeba wprowadzic bardziej zaawansowana kontrole
                    ok_seq=True
                    self.instGui.ccd_tab.inst_Seq_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
                else:
                    ok_seq=False
                    self.msg("SEQUENCE required","red")
                    self.instGui.ccd_tab.inst_Seq_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

            if ok_name and ok_seq:
                self.ndit=0

                if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==0:
                    txt = f"OBJECT {name} seq={seq} dome_follow=off \n"

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
                    txt = f"DARK {name} seq={seq} \n"

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==1:
                    txt=f"ZERO {name} seq={seq}  \n"

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==3:
                    txt=f"SKYFLAT {name} seq={seq}   \n"

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==4:
                    txt=f"DOMEFLAT {name} seq={seq}   \n"

                else: self.msg(f"not implemented yet","yellow")

            self.planrunner.load_nightplan_string('manual', string=txt, overwrite=True)
            await self.planrunner.arun_nightplan('manual', step_id="00")
            self.program_name = "manual"
            self.fits_exec = True

        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)



    @qs.asyncSlot()
    async def ccd_stopExp(self):
        if True:
            await self.takeControl()
            self.dit_start=0
            self.ob["run"]=False
            await self.planrunner.astop_nightplan()
            await self.ccd.aput_stopexposure()
            self.msg(f"exposure STOP requested","red")


    @qs.asyncSlot()
    async def ccd_setBin(self):
        if await self.user.aget_is_access():
            if self.instGui.ccd_tab.inst_Bin_s.currentIndex()==0: x,y=1,1
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==1: x,y=2,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==2: x,y=1,2
            elif self.instGui.ccd_tab.inst_Bin_s.currentIndex()==3: x,y=2,1
            else:
                self.msg(f"not a valid option","red")
                return

            txt=f"CCD binx biny changed to: {x}x{y} requested"
            self.msg(txt,"yellow")
            self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
            await self.ccd.aput_binx(int(x))
            await self.ccd.aput_biny(int(y))
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setGain(self):
        if await self.user.aget_is_access():
            if self.instGui.ccd_tab.inst_setGain_e.currentIndex()==0: g=0
            elif self.instGui.ccd_tab.inst_setGain_e.currentIndex()==1: g=1
            elif self.instGui.ccd_tab.inst_setGain_e.currentIndex()==2: g=2
            else:
                self.msg(f"not a valid option","red")
                return

            txt=f"CCD GAIN changed to: {self.instGui.ccd_tab.inst_setGain_e.currentText()} requested"
            self.msg(txt,"yellow")
            self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(136, 142, 227); color: black;")
            await self.ccd.aput_gain(int(g))
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def ccd_setReadMode(self):
        if await self.user.aget_is_access():
           i=int(self.instGui.ccd_tab.inst_setRead_e.currentIndex())
           m=["5MHz","3MHz","1MHz","0.05MHz"]
           if i<4:
               m=m[i]
               txt=f"Readout Mode {m} requested"
               self.msg(txt,"yellow")
               await self.ccd.aput_readoutmode(i)
               self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
           else:
                self.msg(f"not a valid option","red")
                return
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)


    @qs.asyncSlot()
    async def ccd_setTemp(self):
        if await self.user.aget_is_access():
            temp=float(self.instGui.ccd_tab.inst_setTemp_e.text())
            if temp>-81 and temp<20:
                txt=f"CCD temp set to {temp} deg."
                await self.ccd.aput_setccdtemperature(temp)
                self.msg(txt,"yellow")
            else:
                txt="Value of CCD temp. not allowed"
                self.msg(txt,"red")
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)


    @qs.asyncSlot()
    async def ccd_coolerOnOf(self):
        if await self.user.aget_is_access():
            if self.ccd.cooleron:
              txt="CCD cooler OFF"
              await self.ccd.aput_cooleron(False)
              self.msg(txt,"yellow")
            else:
              txt="CCD cooler ON"
              await self.ccd.aput_cooleron(True)
              self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            await self.ccd_update(True)

    async def ccd_cooler_update(self, event):
        self.ccd_cooler = await  self.ccd.aget_cooleron()
        if self.ccd_cooler != None:
            self.instGui.ccd_tab.cooler_c.setChecked(self.ccd_cooler)
    async def ccd_temp_update(self, event):
        self.ccd_temp = await  self.ccd.aget_ccdtemperature()
        self.ccd_temp_set = await self.ccd.aget_setccdtemperature()
        ccd_temp=self.ccd_temp
        if ccd_temp: txt = f" {ccd_temp:.1f} /"
        else: txt = " -- /"
        if self.ccd_temp_set: txt = txt +  f" {self.ccd_temp_set:.1f}"
        else: txt = txt + " -- "
        self.instGui.ccd_tab.inst_ccdTemp_e.setText(txt)
        if self.ccd_temp:
            if float(ccd_temp)>CCD_MAX_TEMP:
                self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(204,0,0)")
            else: self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(0,150,0)")


    async def ccd_gain_update(self, event):
        self.ccd_gain = await  self.ccd.aget_gain()
        gain_list = ["1x","2x","4x"]
        self.ccd_gain = self.ccd.gain
        if self.ccd_gain != None:
            try:
                txt = gain_list[int(self.ccd_gain)]
                self.instGui.ccd_tab.inst_gain_e.setText(txt)
                if txt == "4x":
                    self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                else: self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")
            except: pass

    async def ccd_rm_update(self, event):
        self.ccd_readoutmode = await  self.ccd.aget_readoutmode()
        # READ MODES

        if self.ccd_readoutmode != None:
            i = int(self.ccd_readoutmode)
            modes=["5MHz","3MHz","1MHz","0.05MHz"]
            txt = modes[i]
            self.ccd_readmode=txt
            self.instGui.ccd_tab.inst_read_e.setText(txt)
            if txt == "1MHz":
                self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            else: self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")

    async def ccd_bin_update(self, event):
        self.ccd_binx = await  self.ccd.aget_binx()
        self.ccd_biny = await  self.ccd.aget_biny()
        if self.ccd_binx and self.ccd_biny:
            txt=f"{self.ccd_binx}x{self.ccd_biny}"
            self.instGui.ccd_tab.inst_Bin_e.setText(txt)
            if txt == "1x1":
                self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            else: self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")

    async def ccd_update(self, event):
        self.ccd_state = await  self.ccd.aget_camerastate()


    # ############ MOUNT ##################################

    @qs.asyncSlot()
    async def mount_motorsOnOff(self):
        if await self.user.aget_is_access():
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False
           if self.mount_motortatus:
              txt="MOTOR OFF requested"
              self.msg(txt,"yellow")
              await self.mount.aput_motoroff()
           else:
               txt="MOTOR ON requested"
               self.msg(txt,"yellow")
               await self.mount.aput_motoron()
           #self.mntGui.mntStat_e.setText(txt)
           #self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.mountMotors_update(None)
            txt="U don't have controll"
            self.WarningWindow(txt)

    async def mountMotors_update(self,event):
           r = await self.mount.aget_motorstatus()
           if r=="true":
               self.mount_motortatus = True
           else:
               self.mount_motortatus = False

           if self.mount_motortatus:
               self.mntGui.mntMotors_c.setChecked(True)
               txt="MOTORS ON"
               self.msg(txt,"green")
           else:
               self.mntGui.mntMotors_c.setChecked(False)
               txt="MOTORS OFF"
               self.msg(txt,"black")

           self.mntGui.mntStat_e.setText(txt)
           self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")

    @qs.asyncSlot()
    async def covers_openOrClose(self):
        if await self.user.aget_is_access():
           self.cover_status = self.cover.coverstate
           if self.cover_status==1:
              txt="mirror OPEN requested"
              self.msg(txt,"yellow")
              await self.mount.aput_opencover()
           else:
               txt="mirror CLOSE requested"
               self.msg(txt,"yellow")
               await self.mount.aput_closecover()
           self.mntGui.telCovers_e.setText(txt)
           self.mntGui.telCovers_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.covers_update(None)
            txt="U don't have controll"
            self.WarningWindow(txt)

    async def covers_update(self,event):
           self.cover_status = await self.cover.aget_coverstate()

           if self.cover_status==3:
               self.mntGui.telCovers_c.setChecked(True)
               txt="OPEN"
               self.msg(f"covers {txt}","green")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(0,150,0); background-color: rgb(233, 233, 233);")
           elif self.cover_status==1:
               self.mntGui.telCovers_c.setChecked(False)
               txt="CLOSED"
               self.msg(f"covers {txt}","black")
               self.mntGui.telCovers_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
           elif self.cover_status==2:
               txt="MOVING"
               self.msg(f"covers {txt}","yellow")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(255, 165, 0); background-color: rgb(233, 233, 233);")
           else:
               txt="UNKNOWN"
               self.msg(f"covers {txt}","red")
               self.mntGui.telCovers_e.setStyleSheet("color: rgb(233, 0, 0); background-color: rgb(233, 233, 233);")

           self.mntGui.telCovers_e.setText(txt)

    @qs.asyncSlot()
    async def park_mount(self):
        if await self.user.aget_is_access():
            if self.mount.motorstatus != "false":
                txt="PARK requested"
                self.mntGui.mntStat_e.setText(txt)
                self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
                await self.mount.aput_park()
                await self.dome.aput_park()
            else:
                txt = "Motors are OFF"
                self.WarningWindow(txt)

        else:
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def abort_slew(self):
        if True:
            await self.takeControl()
            txt="STOP requested"
            self.mntGui.mntStat_e.setText(txt)
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
            await self.mount.aput_abortslew()
            #await self.dome.aput_abortslew()
            #await self.dome.aput_slewtoazimuth(float(self.dome.azimuth))
            await self.mount.aput_tracking(False)
            self.msg(txt,"yellow")


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
                       txt=f"slew to Az: {az} Alt: {alt}"
                       self.msg(txt,"black")

                    elif self.mntGui.setEq_r.isChecked():
                       ra = self.mntGui.nextRa_e.text()
                       dec = self.mntGui.nextDec_e.text()
                       epoch = str(self.mntGui.mntEpoch_e.text())
                       self.req_ra=ra
                       self.req_dec=dec
                       self.req_epoch=epoch
                       ra,dec = RaDecEpoch(self.observatory,ra,dec,epoch)
                       ra=hmsRa2float(ra)
                       dec=arcDeg2float(dec)
                       await self.mount.aput_slewtocoo_async(ra, dec)
                       txt=f"slew to Ra: {ra} Dec: {dec}"
                       self.msg(txt,"black")

                    az=float(self.mntGui.nextAz_e.text())
                    if self.mntGui.domeAuto_c.isChecked():
                        await self.dome.aput_slewtoazimuth(az)
                else:
                    txt = "Slew NOT allowed"
                    self.msg(txt,"red")
                    self.WarningWindow(txt)
            else:
                txt = "Motors are OFF"
                self.WarningWindow(txt)
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def mount_trackOnOff(self):
        if await self.user.aget_is_access():
            if await self.mount.aget_motorstatus() != "false":
                self.mount_tracking = await self.mount.aget_tracking()

                if self.mount_tracking:
                   await self.mount.aput_tracking(False)
                   txt="STOP tracking requested"
                else:
                   await self.mount.aput_tracking(True)
                   txt="START tracking requested"

                self.mntGui.mntStat_e.setText(txt)
                self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
                self.msg(txt,"yellow")
            else:
                await self.mount_update(False)
                txt = "Motors are OFF"
                self.WarningWindow(txt)

        else:
            await self.mount_update(False)
            txt="U don't have controll"
            self.WarningWindow(txt)

    async def mountCon_update(self, event):
        pass
        #self.mount_con=self.mount.connected
        #if self.mount_con:
        #   self.mntGui.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
        #   self.mntGui.mntConn1_l.setStyleSheet("color: rgb(0,150,0);")
        #else:
        #   self.mntGUI.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


    async def mount_update(self, event):
        self.mount_slewing = await self.mount.aget_slewing()
        self.mount_tracking = await self.mount.aget_tracking()
        #self.mount_motorsOn=self.mount.motorstatus

        #self.mount_parked=self.mount.atpark
        txt=""
        if self.mount_slewing and self.mount_tracking:
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
        #elif self.mount_parked:
        #    txt="PARKED"
        #    self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
        #    self.mntGui.tracking_c.setChecked(False)
        else:
            txt="IDLE"
            self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
            self.mntGui.tracking_c.setChecked(False)
        self.mntGui.mntStat_e.setText(txt)
        self.obsGui.main_form.skyView.updateMount()
        self.msg(f"Mount {txt}","black")

        if self.mount_slewing:
            self.mntGui.mntAz_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntAlt_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntRa_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
            self.mntGui.mntDec_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
        else:
            self.mntGui.mntAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntRa_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.mntGui.mntDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

    async def radec_update(self, event):
        self.mount_ra=await self.mount.aget_ra()
        self.mount_dec=await self.mount.aget_dec()
        self.mount_alt=await self.mount.aget_alt()
        self.mount_az=await self.mount.aget_az()
        if "--" not in str(self.mount_ra) and "--" not in str(self.mount_dec) and self.mount_ra != None and self.mount_dec != None:
           self.mntGui.mntRa_e.setText(Deg2H(self.mount_ra))
           self.mntGui.mntDec_e.setText(Deg2DMS(self.mount_dec))
        if "--" not in str(self.mount_alt) and "--" not in str(self.mount_az) and self.mount_alt != None and self.mount_az != None:
           self.mntGui.mntAlt_e.setText(f"{self.mount_alt:.3f}")
           self.mntGui.mntAz_e.setText(f"{self.mount_az:.3f}")
           self.obsGui.main_form.skyView.updateMount()
           airmass = calc_airmass(float(self.mount_alt))
           if airmass != None:
               self.mntGui.mntAirmass_e.setText("%.1f" % airmass)
           else:
               self.mntGui.mntAirmass_e.setText(" -- ")

        az=self.mount_az
        if az != None:
            az=float(az)
            if self.mntGui.domeAuto_c.isChecked() and abs(az-float(self.dome_az)>5.):     # Do wywalenia po implementacji w TIC
               await self.dome.aput_slewtoazimuth(az)


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



    # ################# DOME ########################
    @qs.asyncSlot()
    async def dome_openOrClose(self):
        if await self.user.aget_is_access():
           if self.cover.coverstate == 1:
               if self.dome_shutterstatus==0:
                  await self.dome.aput_closeshutter()
                  txt="CLOSE requested"
               elif self.dome_shutterstatus==1:
                  await self.dome.aput_openshutter()
                  txt="OPEN requested"
               else: pass
               self.mntGui.domeShutter_e.setText(txt)
               self.mntGui.domeShutter_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
               self.msg(txt,"yellow")
           else:
               await self.domeShutterStatus_update(False)
               txt = "Mirror covers are open. Close MIRROR for dome shutter operations"
               self.WarningWindow(txt)

        else:
            await self.domeShutterStatus_update(None)
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_move2Az(self):
        if await self.user.aget_is_access():
           if self.dome_next_az_ok:
               az = float(self.mntGui.domeNextAz_e.text())
               await self.dome.aput_slewtoazimuth(az)

        else:
            await self.domeShutterStatus_update(False)
            txt="U don't have controll"
            self.WarningWindow(txt)

    @qs.asyncSlot()
    async def dome_stop(self):
        if True: #self.user.current_user["name"]==self.myself:
           await self.takeControl()
           await self.dome.aput_abortslew()
           self.msg("DOME STOP requested","yellow")


    @qs.asyncSlot()
    async def domeFollow(self):
        if await self.user.aget_is_access():
            az=self.mount.azimuth
            dome_az = self.dome.azimuth
            if az != None and dome_az != None:
                az=float(az)
                dome_az=float(dome_az)
                if self.mntGui.domeAuto_c.isChecked() and abs(az - dome_az)>5.:  # Do wywalenia po implementacji w TIC
                    await self.dome.aput_slewtoazimuth(az)
        else:
            txt="You don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.domeAuto_c.isChecked(): self.mntGui.domeAuto_c.setChecked(False)
            else: self.mntGui.domeAuto_c.setChecked(True)

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
           self.msg(f"Shutter {txt}","yellow")

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
           self.msg(f"Dome {txt}","yellow")

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
    async def domeFansOnOff(self):
        if await self.user.aget_is_access():
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False
           if self.dome_fanStatus:
              txt="FANS OFF requested"
              self.msg(txt,"yellow")
              await self.focus.aput_fansturnoff()
           else:
               txt="FANS ON requested"
               self.msg(txt,"yellow")
               await self.focus.aput_fansturnon()
           self.mntGui.fans_e.setText(txt)
           self.mntGui.fans_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
        else:
            await self.domeFans_update(False)
            txt="U don't have controll"
            self.WarningWindow(txt)

    async def domeFans_update(self,event):
           r = await self.focus.aget_fansstatus()
           if r == "True": self.dome_fanStatus=True
           else: self.dome_fanStatus=False

           if self.dome_fanStatus:
               self.mntGui.fans_c.setChecked(True)
               txt="FANS ON"
           else:
               self.mntGui.fans_c.setChecked(False)
               txt="FANS OFF"
           self.mntGui.fans_e.setText(txt)
           self.mntGui.fans_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")


    @qs.asyncSlot()
    async def FlatLampOnOff(self):
        if await self.user.aget_is_access():

           if self.mntGui.flatLights_c.isChecked():
               await self.mount.aput_domelamp_on()
               txt = "Flat lamp ON - no feedback"
               self.mntGui.flatLights_e.setText("no feedback")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else:
               await self.mount.aput_domelamp_off()
               txt = "Flat lamp OFF - no feedback"
               self.mntGui.flatLights_e.setText("")
               self.mntGui.flatLights_e.setStyleSheet("color: rgb(0,0,0); background-color: rgb(233, 233, 233);")

           self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.flatLights_c.isChecked(): self.mntGui.flatLights_c.setChecked(False)
            else: self.mntGui.flatLights_c.setChecked(True)

    @qs.asyncSlot()
    async def domeLightOnOff(self):
        if await self.user.aget_is_access():
           if self.mntGui.domeLights_c.isChecked():
               await self.cctv.aput_ir(True)
               self.mntGui.domeLights_e.setText("no feedback")
               txt = "Flat lamp ON - no feedback"
               self.mntGui.domeLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else:
               await self.cctv.aput_ir(False)
               self.mntGui.domeLights_e.setText("")
               txt = "Flat lamp OFF - no feedback"
               self.mntGui.domeLights_e.setStyleSheet("color: rgb(0,0,0); background-color: rgb(233, 233, 233);")
           self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.WarningWindow(txt)
            if self.mntGui.domeLights_c.isChecked(): self.mntGui.domeLights_c.setChecked(False)
            else: self.mntGui.domeLights_c.setChecked(True)



    # ############ FOCUS ##################################

    @qs.asyncSlot()
    async def set_focus(self):
        if await self.user.aget_is_access():
           self.focus_editing=False
           self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(255, 255, 255);")
           val=self.mntGui.setFocus_s.value()
           await self.focus.aput_move(val)
           txt=f"focus {val} requested"
           self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
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
            self.msg("Focus position Error","red")

        if not self.focus_editing:
           self.mntGui.setFocus_s.valueChanged.disconnect(self.focusClicked)
           self.mntGui.setFocus_s.setValue(int(self.focus_value))
           self.mntGui.setFocus_s.valueChanged.connect(self.focusClicked)




    # ############### FILTERS #####################


    async def filterCon_update(self, event):
        pass
        #self.fw_con=self.fw.connected
        #if self.fw_con:
           #self.mntGui.comFilter_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           #self.mntGui.telFilter_l.setStyleSheet("color: rgb(0,150,0);")
        #else:
           #self.domeGUI.comFilter_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))

    @qs.asyncSlot()
    async def set_filter(self):
        if await self.user.aget_is_access():
           ind=int(self.mntGui.telFilter_s.currentIndex())
           if ind == -1: filtr="--"
           else: filtr=self.filter_list[ind]
           txt=f"filter {filtr} requested"
           self.msg(txt,"yellow")
           await self.fw.aput_position(ind)
        else:
            txt="U don't have controll"
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


    async def filterList_update(self, event):
        filter_list = await self.fw.aget_names()  # To jest dziwny slownik
        self.filter_list = [key for key, value in sorted(filter_list.items(), key=lambda item: item[1])]

    # ############### ROTATOR #####################


    async def rotatorCon_update(self, event):
        pass
        #self.rotator_con=self.rotator.connected
        #if self.rotator_con:
           #self.mntGui.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           #self.mntGui.telRotator1_l.setStyleSheet("color: rgb(0,150,0);")
        #else:
           #self.domeGUI.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


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
            self.msg("Rotator position Error","red")

        self.rotator_pos_prev = self.rotator_pos

        # ############ TELESCOPE #########################

    @qs.asyncSlot()
    async def EmStop(self):
        txt = f"EMERGENCY STOP ACTIVATED"
        self.msg(txt, "red")
        await self.user.aget_is_access()
        await self.telescope.emergency_stop()
        self.mntGui.domeAuto_c.setChecked(False)
        await self.domeFollow()



    @qs.asyncSlot()
    async def shutdown(self):
        if await self.user.aget_is_access():
            txt = f"shutdown activated"
            self.msg(txt, "black")
            await self.telescope.shutdown()
        else:
           txt = "U don't have controll"
           self.WarningWindow(txt)

    @qs.asyncSlot()
    async def weatherStop(self):
        if await self.user.aget_is_access():
            txt = f"Weather stop activated"
            self.msg(txt, "yellow")
            await self.telescope.weather_stop()
        else:
           txt = "U don't have controll"
           self.WarningWindow(txt)

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        txt="Control requested"
        self.obsGui.main_form.control_e.setText(txt)
        self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        try: await self.user.aput_break_control()
        except: pass
        try: await self.user.aput_take_control(12*3600)
        except: pass
        self.msg(txt,"yellow")

    async def user_update(self, event):
        self.TICuser=self.user.current_user
        self.acces=bool(await self.user.aget_is_access())
        txt=str(self.TICuser["name"])
        self.obsGui.main_form.control_e.setText(txt)
        if self.acces:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(0,150,0);")
            #self.msg(f"{txt} have controll","green")
        elif  self.user.current_user["name"]==self.myself:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(150,0,0);")
            #self.msg(f"{txt} DON'T have controll","red")
        else:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            #self.msg(f"{txt} have controll","yellow")

# ############ INNE ##############################3

    def WarningWindow(self,txt):
        self.msg(txt, "red")
        self.tmp_box=QtWidgets.QMessageBox()
        self.tmp_box.setWindowTitle("TOI message")
        self.tmp_box.setText(txt)
        self.tmp_box.show()

    async def on_start_app(self):
        await self.run_background_tasks()
        await self.mntGui.on_start_app()
        await self.obsGui.on_start_app()
        await self.instGui.on_start_app()
        await self.instGui.ccd_tab.on_start_app()
        self.msg(f"Welcome in TOI","green")

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        super().closeEvent(event)


# ############### ALL TELESCOPES TELEMETRY #########################


class TelBasicState():
    def __init__(self, parent, tel):
        super().__init__()

        self.parent=parent

        self.state={}
        self.state["name"]=tel

    async def dome_update(self,tmp):
        # if self.parent.active_tel != None and self.parent.active_tel != "sim":
        #     await self.parent.domeShutterStatus_update(None)
        #     await self.parent.domeStatus_update(None)

        state="unknown"
        rgb = (0, 0, 0)
        shutter=self.dome.shutterstatus
        moving=self.dome.slewing

        if shutter == None and moving == None :
            state = "SHUTTER and STATUS ERROR"
            rgb = (150, 0, 0)

        elif shutter == None:
            state = "SHUTTER ERROR"
            rgb = (150, 0, 0)

        elif moving == None :
            state = "DOME STATUS ERROR"
            rgb = (150, 0, 0)

        else:
            if moving:
                state = "MOVING"
                rgb = (255, 160, 0)
            elif shutter==0:
                state="OPEN"
                rgb = (0, 150, 0)
            elif shutter==1:
                state = "CLOSED"
                rgb = (0, 0, 0)
            elif shutter==2:
                state = "OPENING"
                rgb = (255, 160, 0)
            elif shutter==3:
                state = "CLOSING"
                rgb = (255, 160, 0)
            else:
                state = "SHUTTER ERROR"
                rgb = (150, 0, 0)

        self.state["dome"]=state
        self.state["dome_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()
        #print(f"DOME TELEMETRY: {self.state['name']} {shutter} {moving} {state}")

    async def mount_update(self,tmp):
        # if self.parent.active_tel != None and self.parent.active_tel != "sim":
        #     await self.parent.mount_update(None)
        #     await self.parent.mountMotors_update(None)

        slewing=bool(self.mount.slewing)
        tracking=bool(self.mount.tracking)
        motors = await self.mount.aget_motorstatus()
        state="--"
        if motors=="false":
            state="MOTORS OFF"
            rgb = (0, 0, 0)
        elif slewing:
            state="SLEWING"
            rgb = (255, 160, 0)
        elif tracking:
            state="TRACKING"
            rgb = (0, 150, 0)
        else:
            state="IDLE"
            rgb = (0, 0, 0)
        self.state["mount"]=state
        self.state["mount_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()
        #print(f"MOUNT TELEMETRY: {self.state['name']} {motors} {slewing} {tracking} {state}")

    async def instrument_update(self,tmp):
        # if self.parent.active_tel != None and self.parent.active_tel != "sim":
        #     await self.parent.ccd_update(None)
        #     await self.parent.filter_update(None)

        filter_list = await self.fw.aget_names()
        self.filter_list = [key for key, value in sorted(filter_list.items(), key=lambda item: item[1])]
        pos = self.fw.position
        if pos != None:
            pos = int(pos)
            if pos < len(self.filter_list):
                filtr = self.filter_list[pos]
            else: filtr = "??"
        else: filtr = "??"
        try:
            temp = float(self.ccd.ccdtemperature)
        except TypeError: temp=None
        st = self.ccd.camerastate

        if st != None:
            if st==0 and temp > CCD_MAX_TEMP:
                state="WARM"
                rgb=(0, 0, 0)
            elif st==0:
                state="IDLE"
                rgb=(0, 0, 0)
            elif st==1:
                state="WAITING"
                rgb=(0, 0, 0)
            elif st==2:
                state="EXP " +filtr
                rgb=(0, 150, 0)
            elif st==3:
                state="READING"
                rgb=(0, 150, 0)
            elif st==4:
                state="DOWNLOADING"
                rgb=(0, 150, 0)
            else:
                state="ERROR"
                rgb=(150,0,0)
        else:
                state="CAMERA STATUS ERROR"
                rgb=(150,0,0)

        self.state["instrument"]=state
        self.state["instrument_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()

        #print(f"INSTRUMENT TELEMETRY: {self.state['name']} {pos} {filtr} {st} {temp} {state}")

    async def program_update(self,tmp):
        state = "--"
        rgb=(0,0,0)
        self.state["program"]=state
        self.state["program_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()












async def run_qt_app():

    host = socket.gethostname()
    user = pwd.getpwuid(os.getuid())[0]

    api = ClientAPI(name="TOI_Client", user_email="", user_name=f'{user}@{host}',user_description="TOI user interface client.")

    def close_future(future_, loop_):
        loop_.call_later(10, future_.cancel)
        future_.cancel()

    loop = asyncio.get_event_loop()
    future = asyncio.Future()
    app = qs.QApplication.instance()
    if hasattr(app, "aboutToQuit"):
        getattr(app, "aboutToQuit").connect(
            functools.partial(close_future, future, loop)
        )

    toi = TOI(loop=loop, client_api=api, app=app)
    #logger.info("App created")
    await toi.on_start_app()
    #logger.info("the asynchronous start of the application has been completed")
    await future
    return True

def main():
    try:
        qs.run(run_qt_app())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)

if __name__ == "__main__":
    main()
