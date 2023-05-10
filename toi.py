#!/usr/bin/env python3

# ----------------
# 1.08.2022
# Marek Gorski
# ----------------
import asyncio
import functools
import logging
import pathlib
import requests
import socket
import time
import pwd
import os
import numpy


from astropy.time import Time as astroTime
import astropy.units as u


from PyQt5 import QtGui
from PyQt5 import QtCore, QtWidgets
import sys
import qasync as qs


from ocaboxapi import ClientAPI, Observatory
from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from config_service import Config as Cfg

from obs_gui import ObsGui
from aux_gui import AuxGui

from toi_lib import *
from mnt_gui import MntGui
from pery_gui import PeryphericalGui
from plan_gui import PlanGui
from sky_gui import SkyView
from instrument_gui import InstrumentGui
from fits_save import *


from calcFocus import calc_focus as calFoc

logging.basicConfig(level='INFO')

logger = logging.getLogger(__name__)

# text
# rgb(150,0,0)     red
# rgb(0,150,0)     green
# rgb(255, 160, 0) orange
# rgb(0,0,0)       black

# background
# rgb(136, 142, 228)     blue
# rgb(255, 165, 0)       orange


# "\U0001F7E2" green circle
# "\U0001F7E1" yellow circle
# "\U0001F534" red circle

# "\u23F0"  budzik
# "\u23F1"  stoper

CCD_MAX_TEMP = -49.

class TelBasicState():
    def __init__(self, parent, tel):
        super().__init__()

        self.parent=parent

        self.dome = self.parent.observatory_model.get_telescope(tel).get_dome()
        self.mount = self.parent.observatory_model.get_telescope(tel).get_mount()
        self.ccd = self.parent.observatory_model.get_telescope(tel).get_camera()
        self.fw = self.parent.observatory_model.get_telescope(tel).get_filterwheel()

        self.parent.add_background_task(self.dome.asubscribe_shutterstatus(self.dome_update))
        self.parent.add_background_task(self.dome.asubscribe_slewing(self.dome_update))

        self.parent.add_background_task(self.mount.asubscribe_tracking(self.mount_update))
        self.parent.add_background_task(self.mount.asubscribe_slewing(self.mount_update))
        self.parent.add_background_task(self.mount.asubscribe_motorstatus(self.mount_update))

        self.parent.add_background_task(self.ccd.asubscribe_ccdtemperature(self.instrument_update))
        self.parent.add_background_task(self.ccd.asubscribe_camerastate(self.instrument_update))
        self.parent.add_background_task(self.fw.asubscribe_position(self.instrument_update))

        self.state={}
        self.state["name"]=tel


    def dome_update(self,tmp):
        state="unknown"
        rgb = (0, 0, 0)
        shutter=int(self.dome.shutterstatus)
        moving=bool(self.dome.slewing)

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
            state = "ERROR"
            rgb = (150, 0, 0)

        self.state["dome"]=state
        self.state["dome_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()

    def mount_update(self,tmp):
        slewing=bool(self.mount.slewing)
        tracking=bool(self.mount.tracking)
        motors=self.mount.motorstatus
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
        #print(f"DUPA: {self.state['name']} {motors} {slewing} {tracking} {state}")

    def instrument_update(self,tmp):
        state = "--"
        if  self.state["name"]=="zb08":
            fw = ['u', 'g', 'r', 'i', 'z', 'B', 'V', 'Ic', 'empty1', 'empty2']
        else: fw = ['?', '?', '?', '?', '?', '?', '?', '?', '?', '?']
        pos = int(self.fw.position)
        if pos>len(fw):
            filtr=fw[pos]
        else: filtr="??"
        try:
            temp = float(self.ccd.ccdtemperature)
        except ValueError: temp=None
        st = self.ccd.camerastate

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
        self.state["instrument"]=state
        self.state["instrument_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()

        #print(f"DUPA: {self.state['name']} {pos} {filtr} {st} {temp} {state}")

    def program_update(self,tmp):
        state = "--"
        rgb=(0,0,0)
        self.state["program"]=state
        self.state["program_rgb"]=rgb
        self.parent.obsGui.main_form.update_table()

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
        screen = QtWidgets.QDesktopWidget().availableGeometry()
        #print(screen)
        self.obs_window_position=[0,0]
        self.obs_window_size=[850,400]

        self.mnt_geometry=[0,110+int(self.obs_window_size[1]),850,400]
        self.plan_geometry=[1546,0,300,1000]
        self.instrument_geometry=[930,700,500,300]
        self.aux_geometry=[930,0,500,400]

        self.tic_conn="unknown"
        self.fw_conn="unknown"
        self.mount_conn="unknown"
        self.dome_conn="unknown"
        self.rotator_conn="unknown"
        self.inst_conn="unknown"
        self.focus_conn="unknown"
        self.covercalibrator_conn="unknown"


        # aux zmienne
        self.fits_exec=False
        self.dit_start=0
        self.dit_exp=0
        self.ndit=0
        self.ndit_req=1
        self.plan_runner_origin=""
        self.plan_runner_status=""
        self.autofocus_started=False
        self.acces=True

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15","sim"]  # wg25 is not working
        self.obs_tel_in_table=["WK06","ZB08","JK15","SIM"]
        #self.obs_dome_in_table=["Moving","Open","Close","Parked","--"]
        #self.obs_mount_in_table=["Parked","Slewing","Tracking","Guiding","Parked"]
        #self.obs_inst_in_table=["Idle","--","Reading","Exposing V","Exposing K"]
        #self.obs_program_in_table=["Sky Flats","--","Dome Flast","Cep34565","Focusing"]

        # active telescope & universal
        self.ut=str(ephem.now())
        self.sid="00:00:00"
        self.jd="00.00"
        self.active_tel_i=3
        self.active_tel="SIM"

        # ccd
        self.binxy_changed=False

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


    # ############ all telescopes states ####################3

    def oca_tel_stat(self):

        self.tel={}
        self.tel["wk06"]=TelBasicState(self,"wk06")
        self.tel["zb08"]=TelBasicState(self,"zb08")
        self.tel["jk15"]=TelBasicState(self,"jk15")
        # self.tel["wg25"]=TelBasicState(self,"wg25")  # wg25 is not working (mikolaj)
        self.tel["sim"]=TelBasicState(self,"sim")

        self.run_background_tasks()



    #  ############# ZMIANA TELESKOPU #################
    async def teleskop_switched(self):
        tel=self.obs_tel_tic_names[self.active_tel_i]
        self.dome_con=False
        self.dome_az="--"

        txt=f"{tel} selected"
        self.msg(txt,"yellow")

        await self.stop_background_tasks()

        self.user = self.observatory_model.get_telescope(tel).get_access_grantor()
        self.dome = self.observatory_model.get_telescope(tel).get_dome()
        self.mount = self.observatory_model.get_telescope(tel).get_mount()
        self.cover = self.observatory_model.get_telescope(tel).get_covercalibrator()
        self.focus = self.observatory_model.get_telescope(tel).get_focuser()
        self.ccd = self.observatory_model.get_telescope(tel).get_camera()
        self.fw = self.observatory_model.get_telescope(tel).get_filterwheel()
        self.rotator = self.observatory_model.get_telescope(tel).get_rotator()
        self.planrunner = self.observatory_model.get_telescope(tel).get_observation_plan()

        self.planrunner.add_info_callback('exec_json', self.PlanRun1)
        #self.planrunner.add_info_callback('c_sequences', self.PlanRun1)
        #self.planrunner.add_info_callback('c_subcommands', self.PlanRun1)
        #self.planrunner.add_info_callback('c_commands', self.PlanRun1)
        self.planrunner.add_info_callback('stream_5', self.PlanRun5)



        self.add_background_task(self.TOItimer())
        self.add_background_task(self.TOItimer10())
        self.add_background_task(self.user.asubscribe_current_user(self.user_update))
        self.add_background_task(self.user.asubscribe_is_access(self.user_update))

        self.add_background_task(self.dome.asubscribe_connected(self.domeCon_update))
        self.add_background_task(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update))
        self.add_background_task(self.dome.asubscribe_az(self.domeAZ_update))
        self.add_background_task(self.dome.asubscribe_slewing(self.domeStatus_update))
        self.add_background_task(self.dome.asubscribe_slaved(self.domeSlave_update))
        self.add_background_task(self.focus.asubscribe_fansstatus(self.domeFans_update))



        self.add_background_task(self.mount.asubscribe_connected(self.mountCon_update))
        self.add_background_task(self.mount.asubscribe_ra(self.radec_update))
        self.add_background_task(self.mount.asubscribe_dec(self.radec_update))
        self.add_background_task(self.mount.asubscribe_az(self.radec_update))
        self.add_background_task(self.mount.asubscribe_alt(self.radec_update))
        self.add_background_task(self.mount.asubscribe_tracking(self.mount_update))
        self.add_background_task(self.mount.asubscribe_slewing(self.mount_update))
        self.add_background_task(self.mount.asubscribe_motorstatus(self.mountMotors_update))

        self.add_background_task(self.cover.asubscribe_coverstate(self.covers_update))

        self.add_background_task(self.fw.asubscribe_connected(self.filterCon_update))
        self.add_background_task(self.fw.asubscribe_names(self.filterList_update))
        self.add_background_task(self.fw.asubscribe_position(self.filter_update))

        self.add_background_task(self.focus.asubscribe_position(self.focus_update))
        self.add_background_task(self.focus.asubscribe_ismoving(self.focus_update))

        self.add_background_task(self.rotator.asubscribe_connected(self.rotatorCon_update))
        self.add_background_task(self.rotator.asubscribe_position(self.rotator_update))

        self.add_background_task(self.ccd.asubscribe_sensorname(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_ccdtemperature(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_binx(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_biny(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_camerastate(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_cooleron(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_coolerpower(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_gain(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_offset(self.ccd_update))
        #self.add_background_task(self.ccd.asubscribe_percentcompleted(self.ccd_update))
        #self.add_background_task(self.ccd.asubscribe_readoutmodes(self.ccd_update))
        self.add_background_task(self.ccd.asubscribe_readoutmode(self.ccd_update))

        self.add_background_task(self.ccd.asubscribe_imageready(self.ccd_imageready))

        await self.run_background_tasks()

        self.mntGui.updateUI()
        self.auxGui.updateUI()
        self.planGui.updateUI()
        self.instGui.updateUI()

        #await self.user_update(None)
        #await self.domeCon_update(None)
        await self.domeShutterStatus_update(None)
        await self.domeStatus_update(None)
        await self.domeAZ_update(None)
        #await self.domeSlave_update(None)
        #await self.domeFans_update(None)
        #await self.mountCon_update(None)
        #await self.radec_update(None)
        await self.mount_update(None)
        await self.mountMotors_update(None)
        #await self.covers_update(None)
        #await self.filterCon_update(None)
        #await self.filterList_update(None)
        await self.filter_update(None)
        #await self.focus_update(None)
        #await self.rotatorCon_update(None)
        #await self.rotator_update(None)
        await self.ccd_update(None)





    # ################### METODY POD SUBSKRYPCJE ##################

    @qs.asyncSlot()
    async def test(self):

        # awaryjny
        txt=""
        data={"Action":"telescope:errorstring","Parameters":""}
        quest="http://192.168.7.110:11111/api/v1/telescope/0/action"
        r = requests.put(quest,data=data).json()
        r=r['Value']
        txt = txt + f"ERROR:  {r}"

        #data={"Action":"telescope:clearerror","Parameters":""}
        #quest="http://192.168.7.110:11111/api/v1/telescope/0/action"
        #r = requests.put(quest,data=data).json()
        #r=r['Value']



        print(txt)


        #print("dupa")
        #z = await self.rotator.aget_position()
        #print(z)
        #data={"Action":"MotStat","Parameters":""}
        #data={"Action":"telescope:startfans","Parameters":"5"}    # Dome Flat lamps
        #data={"Action":"telescope:stopfans","Parameters":""}
        #data={"Action":"fansturnon","Parameters":""}
        #data={"Action":"fansturnoff","Parameters":""}
        #data={"Action":"fansstatus","Parameters":""}
        #data={"Action":"telescope:reportmindec","Parameters":""}
        #data={"Action":"coverstatus","Parameters":""}
        #data={"Action":"telescope:motoron","Parameters":""}
        #data={"Action":"telescope:motoroff","Parameters":""}
        #data={"Action":"telescope:stopfans","Parameters":""}



        #quest="http://192.168.7.110:11111/api/v1/telescope/0/action"
        #quest="http://192.168.7.110:11111/api/v1/focuser/0/position"

        #data={"Brightness":0}
        #quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/opencover"
        #quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/closecover"
        #quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/coverstate"
        #quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/action"

        #quest="http://zb08-tcu.oca.lan:11111/api/v1/dome/0/shutterstatus"


        #quest="http://192.168.7.110:11111/api/v1/camera/0/gain"
        #quest="http://192.168.7.110:11111/api/v1/rotator/0/position"
        #quest="http://192.168.7.110:11111/api/v1/telescope/0/utcdate"
        #quest="http://192.168.7.110:11111/api/v1/dome/0/abortslew"
        #quest="http://192.168.7.110:11111/api/v1/camera/0/sensorname"
        #quest="http://192.168.7.110:11111/api/v1/camera/0/setccdtemperature"


        r=requests.get(quest)

        #data={"Command":"MotStat","Raw":"True"}
        #quest="http://192.168.7.110:11111/api/v1/telescope/0/commandstring"


        #r=requests.put(quest,data=data)

        r=r.json()
        print(f"Dupa {r}")


    async def TOItimer10(self):
        while True:

            self.tic_conn = True

            #self.covercalibrator_conn=False

            if self.tic_conn == True:

                tel_url = "http://192.168.7.110:11111/api/v1/"

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

            await asyncio.sleep(60)

    async def TOItimer(self):
        while True:

            self.time=time.perf_counter()

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

            self.sid,self.jd,self.ut,self.sunrise,self.sunset,self.sun_alt,self.sun_az,self.moon_alt,self.moon_az,self.moonrise,self.moonset,self.moon_phase=UT_SID(self.observatory)
            self.obsGui.main_form.ojd_e.setText(f"{self.jd:.6f}")
            self.obsGui.main_form.sid_e.setText(str(self.sid).split(".")[0])
            date=str(self.ut).split()[0]
            date=date.split("/")[2]+"/"+date.split("/")[1]+"/"+date.split("/")[0]
            ut=str(self.ut).split()[1]
            self.obsGui.main_form.date_e.setText(str(date))
            self.obsGui.main_form.ut_e.setText(str(ut))
            self.obsGui.main_form.skyView.updateAlmanac()
            self.obsGui.main_form.skyView.updateRadar()
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


        # AUTOFOCUS
        if self.autofocus_started:
            if "id" in info.keys():
                if info["id"]=="auto_focus" and info["started"]==True and info["done"]==True:
                    self.autofocus_started=False
                    self.msg("Auto-focus sequence finished","black")
                    max_sharpness_focus, calc_metadata = calFoc.calculate("../../Desktop/fits_zb08")
                    coef = calc_metadata["poly_coef"]
                    focus_list_ret = calc_metadata["focus_values"]
                    sharpness_list_ret = calc_metadata["sharpness_values"]

                    self.auxGui.focus_tab.result_e.setText(f"{max_sharpness_focus:.1f}")
                    print("FOCUS: ", max_sharpness_focus)
                    print(coef)

                    fit_x = numpy.linspace(min(focus_list_ret), max(focus_list_ret), 100)
                    if len(coef)>3:
                        fit_y = coef[0]* fit_x**4 + coef[1]*fit_x**3 + coef[2]*fit_x**2 +  coef[3]*fit_x + coef[4]
                    elif len(coef)>1:
                        fit_y = coef[0]* fit_x**2 + coef[1]*fit_x + coef[2]

                    self.auxGui.focus_tab.x=focus_list_ret
                    self.auxGui.focus_tab.y=sharpness_list_ret
                    self.auxGui.focus_tab.fit_x=fit_x
                    self.auxGui.focus_tab.fit_y=fit_y
                    self.auxGui.focus_tab.max_sharp=max_sharpness_focus
                    self.auxGui.focus_tab.update()
                    self.auxGui.tabWidget.setCurrentIndex(1)


        # OTHER
        if "id" in info.keys():
            self.program_id = info["id"]
            ut=str(self.ut).split()[1].split(":")[0]+":"+str(self.ut).split()[1].split(":")[1]
            txt = f"--------  {ut}  --------  {self.program_id}  --------\n {info}\n"
            self.planGui.prog_call_e.append(txt)


        if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
            if info["name"] == "Night plan" and info["started"] and not info["done"]:
                self.msg(f"Sequence started","black")

        if "exp_started" in info.keys() and "exp_done" in info.keys():
            if info["exp_started"] and not info["exp_done"]:
                self.ndit=float(info["n_exp"])
                self.ndit_req=float(info["exp_no"])
                self.dit_exp=float(info["exp_time"])
                self.dit_start=self.time
                self.plan_runner_status="exposing"
                self.msg(f"{self.dit_exp} [s] exposure started","black")

        if "exp_done" in info.keys():
            if info["exp_done"] and info["exp_saved"]:
                self.ndit=float(info["n_exp"])
                self.plan_runner_status="exp done"

        if "name" in info.keys() and "done" in info.keys():
            if info["name"]=="camera-exposure" and info["done"]:
                self.dit_start=0
                self.instGui.ccd_tab.inst_DitProg_n.setFormat("IDLE")
                self.msg("Plan finished","black")

        if "id" in info.keys():
            if self.plan_runner_origin=="Plan Gui" and "_" in info["id"]:
                cur_i = info["id"].split("_")[1]
                self.planGui.current_i=int(cur_i)
                self.planGui.next_i=self.planGui.current_i+1
                self.planGui.update_table()

        #else: self.plan_runner_status=""

    @qs.asyncSlot()
    async def PlanRun5(self,txt):
        if self.plan_runner_origin=="Plan Gui":
            if "_" in txt: done_i = txt.split("_")[1]
            self.planGui.done.append(int(done_i))
            try: self.planGui.update_table()
            except UnboundLocalError: pass


    # ############ AUTO FOCUS ##########################

    @qs.asyncSlot()
    async def auto_focus(self):
        program=""

        v0 = float(self.auxGui.focus_tab.last_e.text())
        step = float(self.auxGui.focus_tab.steps_e.text())
        number = float(self.auxGui.focus_tab.range_e.text())
        method = self.auxGui.focus_tab.method_s.currentText()
        exp=self.instGui.ccd_tab.inst_Dit_e.text()
        if len(exp)==0:
            exp = 5
            self.msg("no exp specified. exp=5","red")

        seq = "1/"+str(self.curent_filter)+"/"+str(exp)

        pos = v0 - step*int(number/2)
        for n in range(int(number)):
            pos = pos + step
            program = program + f"FOCUS pos={int(pos)} seq={seq}\n"

        print(program)
        self.planrunner.load_nightplan_string('auto_focus', program, overwrite=True)
        self.planrunner.run_nightplan('auto_focus',step_id="00")
        self.fits_exec=True
        self.plan_runner_origin="auto_focus"
        self.program_name="auto_focus"
        self.autofocus_started=True



    # ############ PLAN RUNNER ##########################

    @qs.asyncSlot()
    async def plan_start(self):
        program=""
        for tmp in self.planGui.plan:
            ob=tmp["block"]
            program=program+ob

        self.planrunner.load_nightplan_string('program', program, overwrite=True)
        self.planrunner.run_nightplan('program',step_id="00")
        self.program_name="program"
        self.fits_exec=True
        self.plan_runner_origin="Plan Gui"

    @qs.asyncSlot()
    async def resume_program(self):

        self.planrunner.stop_nightplan()
        self.planrunner.run_nightplan(self.program_name,step_id=self.program_id)


    @qs.asyncSlot()
    async def stop_program(self):
        self.planrunner.stop_nightplan()




    # ############ CCD ##################################

    async def ccd_imageready(self,event):
        if self.ccd.imageready:
            #self.dit_start=0

            #quest="http://192.168.7.110:11111/api/v1/camera/0/lastexposurestarttime"    # Alpaca do podmianki
            #r=requests.get(quest)
            #self.ccd_start_time = r.json()["Value"]

            #quest="http://192.168.7.110:11111/api/v1/camera/0/lastexposureduration"     # Alpaca do podmianki
            #r=requests.get(quest)
            #self.ccd_exp_time = r.json()["Value"]


            #self.ccd_start_time = astroTime(self.ccd_start_time,format="fits",scale="utc")
            #self.ccd_start_time=self.ccd_start_time+3*u.hour                            # BAAARDZO brudne rozwiazanie czasu lokalnego!!!!!!

            #self.ccd_jd_start = self.ccd_start_time.jd

            res = await self.ccd.aget_imagearray()
            image = self.ccd.imagearray
            image =  numpy.asarray(image).astype(numpy.int16)
            self.auxGui.fits_tab.fitsView.update(image)
            if self.fits_exec:
            #    txt=f"Exposure finished"
            #    self.msg(txt,"black")
                self.auxGui.tabWidget.setCurrentIndex(6)
                #SaveFits(self,image)





    @qs.asyncSlot()
    async def ccd_startExp(self):
        if self.user.current_user["name"]==self.myself:
            self.dit_start=0
            ok_ndit=False
            ok_exp=False
            ok_name=False

            exp=self.instGui.ccd_tab.inst_Dit_e.text()
            ndit=self.instGui.ccd_tab.inst_Ndit_e.text()
            name=self.instGui.ccd_tab.inst_object_e.text().strip()

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

            if len(name)>0:
                ok_name=True
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
            else:
                ok_name=False
                self.msg("OBJECT NAME required","red")
                self.instGui.ccd_tab.inst_object_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

            if ok_name and ok_exp and ok_ndit:
                self.ndit=0

                if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==0:
                    if ok_exp and ok_name:
                        seq=str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                        txt=f"OBJECT {name} seq={seq}\n"
                        self.planrunner.load_nightplan_string('manual', txt, overwrite=True)
                        self.planrunner.run_nightplan('manual',step_id="00")
                        self.program_name="manual"
                        self.fits_exec=True

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
                    if ok_exp:
                        txt=str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                        txt="DARK seq="+txt+"\n"
                        self.planrunner.load_nightplan_string('manual', txt, overwrite=True)
                        self.planrunner.run_nightplan('manual',step_id="00")
                        self.program_name="manual"
                        self.fits_exec=True

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==1:
                    if ok_exp:
                        ndit=int(self.instGui.ccd_tab.inst_Ndit_e.text())
                        exp=int(self.instGui.ccd_tab.inst_Dit_e.text())
                        txt=str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                        txt="ZERO seq="+txt+"\n"
                        self.planrunner.load_nightplan_string('manual', txt, overwrite=True)
                        self.planrunner.run_nightplan('manual',step_id="00")
                        self.program_name="manual"
                        self.fits_exec=True

                else: self.msg(f"not implemented yet","yellow")


        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            await self.ccd_update(True)

            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def ccd_startSequence(self):
        txt=self.instGui.ccd_tab.inst_Seq_e.text()
        txt=txt.strip()
        #if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==0:
        #    txt="BEGINSEQUENCE\n OBJECT  seq="+txt+"\nENDSEQUENCE"
        #    self.planrunner.load_nightplan_string('sequence', txt, overwrite=True)
        #    self.planrunner.run_nightplan('sequence',step_id="00")
        #    self.fits_exec=True
        #    self.dit_start=self.time
        if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==1:
            txt="ZERO seq="+txt+"\n"
            self.planrunner.load_nightplan_string('sequence', txt, overwrite=True)
            self.planrunner.run_nightplan('sequence',step_id="00")
            self.program_name="sequence"
            self.fits_exec=True
            self.dit_start=self.time

        if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
            txt="DARK seq="+txt+"\n"
            self.planrunner.load_nightplan_string('sequence', txt, overwrite=True)
            self.planrunner.run_nightplan('sequence',step_id="00")
            self.program_name="sequence"
            self.fits_exec=True
            self.dit_start=self.time



    @qs.asyncSlot()
    async def ccd_setBin(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def ccd_setGain(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def ccd_setReadMode(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()


    @qs.asyncSlot()
    async def ccd_setTemp(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            await self.ccd_update(True)
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def ccd_coolerOnOf(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            await self.ccd_update(True)

            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            #self.tmp_box.show()


    async def ccd_update(self, event):
        self.ccd_name=self.ccd.sensorname
        self.ccd_temp=self.ccd.ccdtemperature
        self.ccd_binx=self.ccd.binx
        self.ccd_biny=self.ccd.biny
        self.ccd_state=self.ccd.camerastate
        self.ccd_gain=self.ccd.gain
        self.ccd_offset=self.ccd.offset
        self.ccd_cooler=self.ccd.cooleron
        self.ccd_percent=self.ccd.percentcompleted
        self.ccd_coolerpower=self.ccd.coolerpower
        self.ccd_readoutmode=await self.ccd.aget_readoutmode()
        #self.ccd_readoutmodes=self.ccd.readoutmodes


        # CCD TEMP
        ccd_temp=self.ccd_temp
        ccd_temp_set=await self.ccd.aget_setccdtemperature()
        self.instGui.ccd_tab.inst_ccdTemp_e.setText(f"{ccd_temp:.1f} / {ccd_temp_set}")
        if float(ccd_temp)>CCD_MAX_TEMP:
            self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(204,0,0)")
        else: self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: rgb(0,150,0)")
        self.instGui.ccd_tab.cooler_c.setChecked(self.ccd_cooler)

        # BINX BINY

        txt=f"{self.ccd_binx}x{self.ccd_biny}"
        self.instGui.ccd_tab.inst_Bin_e.setText(txt)
        self.instGui.ccd_tab.inst_Bin_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        # READ MODES
        self.ccd_readoutmode = await self.ccd.aget_readoutmode()
        i = int(self.ccd_readoutmode)
        modes=["5MHz","3MHz","1MHz","0.05MHz"]
        txt = modes[i]
        self.ccd_readmode=txt
        self.instGui.ccd_tab.inst_read_e.setText(txt)
        self.instGui.ccd_tab.inst_read_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        # GAIN
        #gain_list = await self.ccd.aget_gains()
        gain_list = ["1x","2x","4x"]
        self.ccd_gain = await self.ccd.aget_gain()
        try:
            txt = gain_list[int(self.ccd_gain)]
            self.instGui.ccd_tab.inst_gain_e.setText(txt)
            self.instGui.ccd_tab.inst_gain_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        except: pass

        #if self.ccd_state==0: txt="IDLE"
        #elif self.ccd_state==1: txt="WAITING"
        #elif self.ccd_state==2: txt="EXPOSING"
        #elif self.ccd_state==3: txt="READING"
        #elif self.ccd_state==4: txt="DOWNLOAD"
        #elif self.ccd_state==5: txt="ERROR"

        #self.instGui.ccd_tab.inst_DitProg_n.setFormat(txt)



    # ############ MOUNT ##################################

#self.focus.aput_fansturnon


    @qs.asyncSlot()
    async def domeFansOnOff(self):
        if self.user.current_user["name"]==self.myself:
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
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

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
    async def mount_motorsOnOff(self):
        if self.user.current_user["name"]==self.myself:
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
            await self.mountMotors_update(False)
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

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
    async def FlatLampOnOff(self):
        if self.user.current_user["name"]==self.myself:

           if self.mntGui.flatLights_c.isChecked():
               await self.mount.aput_domelamp_on()
               txt = "Flat Lamp ON requested"
           else:
               await self.mount.aput_domelamp_off()
               txt = "Flat Lamp OFF requested"


           self.mntGui.flatLights_e.setText(txt)
           self.mntGui.flatLights_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()






    @qs.asyncSlot()
    async def covers_openOrClose(self):
        if self.user.current_user["name"]==self.myself:
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
            await self.mountMotors_update(False)
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    async def covers_update(self,event):
           self.cover_status = self.cover.coverstate

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
    async def covers_close(self):

        if self.user.current_user["name"]==self.myself:
            txt="Close Covers"
            await self.mount.aput_action("telescope:closecover")
            self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def covers_open(self):

        if self.user.current_user["name"]==self.myself:
            txt="Open Covers"
            await self.mount.aput_action("telescope:opencover")
            self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def park_mount(self):
        if self.user.current_user["name"]==self.myself:
            txt="PARK requested"
            self.mntGui.mntStat_e.setText(txt)
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
            await self.mount.aput_park()
            self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def abort_slew(self):
        if self.user.current_user["name"]==self.myself:
            txt="STOP requested"
            self.mntGui.mntStat_e.setText(txt)
            self.mntGui.mntStat_e.setStyleSheet("color: rgb(204,0,0); background-color: rgb(233, 233, 233);")
            await self.mount.aput_abortslew()
            #await self.dome.aput_abortslew()
            #await self.dome.aput_slewtoazimuth(float(self.dome.azimuth))
            await self.mount.aput_tracking(False)
            self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def mount_slew(self):
        if self.user.current_user["name"]==self.myself:
           self.req_ra=""
           self.req_dec=""
           self.req_epoq=""

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
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def mount_trackOnOff(self):
        if self.user.current_user["name"]==self.myself:

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
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    async def mountCon_update(self, event):
        pass
        #self.mount_con=self.mount.connected
        #if self.mount_con:
        #   self.mntGui.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
        #   self.mntGui.mntConn1_l.setStyleSheet("color: rgb(0,150,0);")
        #else:
        #   self.mntGUI.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


    async def mount_update(self, event):
        self.mount_slewing=self.mount.slewing
        self.mount_tracking=self.mount.tracking
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
            #txt="PARKED"
            #self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
            #self.mntGui.tracking_c.setChecked(False)
        else:
            txt="IDLE"
            self.mntGui.mntStat_e.setStyleSheet("color: black; background-color: rgb(233, 233, 233);")
            self.mntGui.tracking_c.setChecked(False)
        self.mntGui.mntStat_e.setText(txt)
        self.obsGui.main_form.skyView.updateMount()
        self.msg(f"Mount {txt}","black")

    async def radec_update(self, event):
        self.mount_ra=self.mount.rightascension
        self.mount_dec=self.mount.declination
        self.mount_alt=self.mount.altitude
        self.mount_az=self.mount.azimuth
        if "--" not in str(self.mount_ra) and "--" not in str(self.mount_dec) and self.mount_ra != None and self.mount_dec != None:
           self.mntGui.mntRa_e.setText(Deg2H(self.mount_ra))
           self.mntGui.mntDec_e.setText(Deg2DMS(self.mount_dec))
        if "--" not in str(self.mount_alt) and "--" not in str(self.mount_az) and self.mount_alt != None and self.mount_az != None:
           self.mntGui.mntAlt_e.setText(f"{self.mount_alt:.3f}")
           self.mntGui.mntAz_e.setText(f"{self.mount_az:.3f}")
           self.obsGui.main_form.skyView.updateMount()
        az=self.mount_az
        if az != None:
            az=float(az)
            if self.mntGui.domeAuto_c.isChecked() and abs(az-float(self.dome_az)>5.):     # Do wywalenia po implementacji w TIC
               await self.dome.aput_slewtoazimuth(az)



    # #### DOME #########
    @qs.asyncSlot()
    async def dome_openOrClose(self):
        if self.user.current_user["name"]==self.myself:

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
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    @qs.asyncSlot()
    async def dome_move2Az(self):
        if self.user.current_user["name"]==self.myself:
           az=float(self.mntGui.domeNextAz_e.text())
           ok=False
           try:
              tmp=az+1
              ok=True
           except:
              ok=False
           if ok and az < 360. and az > -0.1:
              await self.dome.aput_slewtoazimuth(az)

        else:
            await self.domeShutterStatus_update(False)
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()


    async def domeCon_update(self, event):
        pass
        #self.dome_con=self.dome.connected
        #if self.dome_con:
           #self.mntGui.domeConn2_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           ##self.mntGui.domeConn1_l.setText("Dome Connected")
           #self.mntGui.domeConn1_l.setStyleSheet("color: rgb(0,150,0);")
        #else:
           #self.domeGUI.domeConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))
           ##self.mntGui.domeConn1_l.setText("Dome NOT Connected")

    async def domeShutterStatus_update(self, event):
           self.dome_shutterstatus=self.dome.shutterstatus
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
           self.dome_status=self.dome.slewing
           if self.dome_status==False:
              txt="STOPPED"
              self.mntGui.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
           elif self.dome_status==True:
                txt="MOVING"
                self.mntGui.domeStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else: txt="UNKNOWN"
           self.mntGui.domeStat_e.setText(txt)
           self.msg(f"Dome {txt}","yellow")


    async def domeSlave_update(self, event):
        pass
        #print("DUPA")
        #print(self.dome.slaved)


    async def domeAZ_update(self, event):
        #self.dome_az=await event.obj.aget_az()
        self.dome_az=self.dome.azimuth
        if self.dome_az:
            self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
            self.obsGui.main_form.skyView.updateDome()

    # ############ FOCUS ##################################

    @qs.asyncSlot()
    async def set_focus(self):
        if self.user.current_user["name"]==self.myself:
           self.focus_editing=False
           self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(255, 255, 255);")
           val=self.mntGui.setFocus_s.value()
           await self.focus.aput_move(val)
           txt=f"focus {val} requested"
           self.msg(txt,"yellow")
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    def focusClicked(self, event):
        self.mntGui.setFocus_s.setStyleSheet("background-color: rgb(255, 209, 100);")
        self.focus_editing=True

    async def focus_update(self, event):
        val = self.focus.position
        self.focus_value=val
        self.mntGui.telFocus_e.setText(str(val))
        if not self.focus_editing:
           self.mntGui.setFocus_s.valueChanged.disconnect(self.focusClicked)
           self.mntGui.setFocus_s.setValue(int(val))
           self.mntGui.setFocus_s.valueChanged.connect(self.focusClicked)


    async def on_start_app(self):
        await self.run_background_tasks()
        await self.mntGui.on_start_app()
        await self.obsGui.on_start_app()
        await self.instGui.on_start_app()
        await self.instGui.ccd_tab.on_start_app()
        self.msg(f"Welcome in TOI","green")

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
        if self.user.current_user["name"]==self.myself:
           ind=int(self.mntGui.telFilter_s.currentIndex())
           print("req: ",ind )
           fw = ['u', 'g', 'r', 'i', 'z', 'B', 'V', 'Ic', 'empty1', 'empty2']
           filtr=fw[ind]
           txt=f"filter {filtr} requested"
           self.msg(txt,"yellow")
           await self.fw.aput_position(ind)
        else:
            txt="U don't have controll"
            self.msg(txt,"red")
            self.tmp_box=QtWidgets.QMessageBox()
            self.tmp_box.setWindowTitle("TOI message")
            self.tmp_box.setText("You don't have controll")
            self.tmp_box.show()

    async def filter_update(self, event):
        fw = self.fw.names
        fw = ['u', 'g', 'r', 'i', 'z', 'B', 'V', 'Ic', 'empty1', 'empty2']
        pos = int(self.fw.position)
        self.curent_filter=fw[pos]
        self.mntGui.telFilter_e.setText(fw[pos])

    async def filterList_update(self, event):
        fw = self.fw.names
        fw = ['u', 'g', 'r', 'i', 'z', 'B', 'V', 'Ic', 'empty1', 'empty2']
        pos = self.fw.position
        self.mntGui.telFilter_s.clear()
        self.mntGui.telFilter_s.addItems(fw)
        if pos != None:
            self.mntGui.telFilter_s.setCurrentIndex(int(pos))

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
        self.mntGui.telRotator1_e.setText(f"{self.rotator_pos:.2f}")

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        txt="Control requested"
        self.obsGui.main_form.control_e.setText(txt)
        self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        try: await self.user.aput_break_control()
        except: pass
        try: await self.user.aput_take_control(3600)
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

    @qs.asyncClose
    async def closeEvent(self, event):
        super().closeEvent(event)


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
    logger.info("App created")
    await toi.on_start_app()
    logger.info("the asynchronous start of the application has been completed")
    await future
    return True


def main():
    try:
        qs.run(run_qt_app())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)


# todo może warto dodać do GUI na dole taki widget z logami co się dzieje taka konsola tylko do odczytu
if __name__ == "__main__":
    main()
