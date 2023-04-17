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

logging.basicConfig(level='INFO')

logger = logging.getLogger(__name__)


# rgb(136, 142, 228)     blue
# rgb(255, 165, 0)       orange


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
        self.plan_geometry=[1546,0,300,600]
        self.instrument_geometry=[930,700,500,300]
        self.aux_geometry=[930,0,500,400]

        # aux zmienne
        self.fits_exec=False
        self.dit_start=0
        self.dit_exp=0
        self.ndit=0
        self.ndit_req=1
        self.plan_runner_origin=""
        self.plan_runner_status=""
        self.acces=True

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15","wg25","sim"]
        self.obs_tel_in_table=["WK06","ZB08","JK15","WG25","SIM"]
        self.obs_dome_in_table=["Moving","Open","Close","Parked","--"]
        self.obs_mount_in_table=["Parked","Slewing","Tracking","Guiding","Parked"]
        self.obs_inst_in_table=["Idle","--","Reading","Exposing V","Exposing K"]
        self.obs_program_in_table=["Sky Flats","--","Dome Flast","Cep34565","Focusing"]

        # active telescope & universal
        self.ut=str(ephem.now())
        self.sid="00:00:00"
        self.jd="00.00"
        self.active_tel_i=4
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
        self.mount_ra="--:--:--"
        self.mount_dec="--:--:--"
        self.mount_alt="--.--"
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
        self.add_background_task(self.user.asubscribe_current_user(self.user_update))
        self.add_background_task(self.user.asubscribe_is_access(self.user_update))

        self.add_background_task(self.dome.asubscribe_connected(self.domeCon_update))
        self.add_background_task(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update))
        self.add_background_task(self.dome.asubscribe_az(self.domeAZ_update))
        self.add_background_task(self.dome.asubscribe_slewing(self.domeStatus_update))
        self.add_background_task(self.dome.asubscribe_slaved(self.domeSlave_update))

        self.add_background_task(self.mount.asubscribe_connected(self.mountCon_update))
        self.add_background_task(self.mount.asubscribe_ra(self.radec_update))
        self.add_background_task(self.mount.asubscribe_dec(self.radec_update))
        self.add_background_task(self.mount.asubscribe_az(self.radec_update))
        self.add_background_task(self.mount.asubscribe_alt(self.radec_update))
        self.add_background_task(self.mount.asubscribe_tracking(self.mount_update))
        self.add_background_task(self.mount.asubscribe_slewing(self.mount_update))
        self.add_background_task(self.mount.asubscribe_motorstatus(self.mount_update))


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

        data={"Action":"telescope:clearerror","Parameters":""}
        quest="http://192.168.7.110:11111/api/v1/telescope/0/action"
        r = requests.put(quest,data=data).json()
        r=r['Value']



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
        #quest="http://192.168.7.110:11111/api/v1/focuser/0/action"

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


        #r=requests.get(quest)

        #data={"Command":"MotStat","Raw":"True"}
        #quest="http://192.168.7.110:11111/api/v1/telescope/0/commandstring"


        #r=requests.put(quest,data=data)

        #r=r.json()
        #print(f"Dupa {r}")


    async def TOItimer(self):
        while True:

            # pozostalem TIC-TOI timery
            #print("TIC-TOI")

            self.time=time.perf_counter()

            # Do wywalenia po implementacji w TIC

            if self.dit_start>0:

                p=int(100*(self.ndit/self.ndit_req))
                self.instGui.ccd_tab.inst_NditProg_n.setValue(p)
                txt=f"{int(self.ndit)}/{int(self.ndit_req)}"

                dt=self.time-self.dit_start
                if dt>self.dit_exp:
                    dt=self.dit_exp
                if int(self.dit_exp)==0: p=100
                else: p=int(100*(dt/self.dit_exp))
                self.instGui.ccd_tab.inst_DitProg_n.setValue(p)
                txt2=f"{int(dt)}/{int(self.dit_exp)}"

                self.instGui.ccd_tab.inst_NditProg_n.setFormat(txt)
                self.instGui.ccd_tab.inst_DitProg_n.setFormat(txt2)

            self.sid,self.jd,self.ut,self.sunrise,self.sunset,self.sun_alt,self.sun_az,self.moon_alt,self.moon_az=UT_SID(self.observatory)
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

            #self.mount_motorsOn = await self.mount.aget_motorstatus()
            #print(f"Motors: {self.mount_motorsOn}")

            await asyncio.sleep(1)



    # ############ PLAN RUNNER CALLBACK ##########################

    @qs.asyncSlot()
    async def PlanRun1(self,info):
        print(info)


        if "name" in info.keys() and "started" in info.keys() and "done" in info.keys():
            if info["name"] == "Night plan" and info["started"] and not info["done"]:
                self.msg(f"Sequence started","black")

        if "sub_started" in info.keys():
            if info["sub_started"]:
                self.ndit=float(info["n_exp"])-1
                self.ndit_req=float(info["exp_no"])
                self.dit_exp=float(info["exp_time"])
                self.dit_start=self.time
                self.msg(f"{self.dit_exp} [s] exposure started","black")

        if "exp_done" in info.keys():
            if info["exp_done"] and info["exp_saved"]:
                self.ndit=float(info["n_exp"])

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

    # ############ PLAN RUNNER ##########################

    @qs.asyncSlot()
    async def plan_start(self):
        program=""
        for tmp in self.planGui.plan:
            ob=tmp["block"]
            program=program+ob

        self.planrunner.load_nightplan_string('program', program, overwrite=True)
        self.planrunner.run_nightplan('program',step_id="00")
        self.fits_exec=True
        self.plan_runner_origin="Plan Gui"


    # ############ CCD ##################################

    async def ccd_imageready(self,event):
        if self.ccd.imageready:
            #self.dit_start=0

            quest="http://192.168.7.110:11111/api/v1/camera/0/lastexposurestarttime"    # Alpaca do podmianki
            r=requests.get(quest)
            self.ccd_start_time = r.json()["Value"]

            quest="http://192.168.7.110:11111/api/v1/camera/0/lastexposureduration"     # Alpaca do podmianki
            r=requests.get(quest)
            self.ccd_exp_time = r.json()["Value"]


            self.ccd_start_time = astroTime(self.ccd_start_time,format="fits",scale="utc")
            self.ccd_start_time=self.ccd_start_time+3*u.hour                            # BAAARDZO brudne rozwiazanie czasu lokalnego!!!!!!

            self.ccd_jd_start = self.ccd_start_time.jd

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
                        self.fits_exec=True

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
                    if ok_exp:
                        txt=str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                        txt="DARK seq="+txt+"\n"
                        self.planrunner.load_nightplan_string('manual', txt, overwrite=True)
                        self.planrunner.run_nightplan('manual',step_id="00")
                        self.fits_exec=True

                elif self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==1:
                    if ok_exp:
                        ndit=int(self.instGui.ccd_tab.inst_Ndit_e.text())
                        exp=int(self.instGui.ccd_tab.inst_Dit_e.text())
                        txt=str(ndit)+"/"+str(self.curent_filter)+"/"+str(exp)
                        txt="ZERO seq="+txt+"\n"
                        self.planrunner.load_nightplan_string('manual', txt, overwrite=True)
                        self.planrunner.run_nightplan('manual',step_id="00")
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
            self.fits_exec=True
            self.dit_start=self.time

        if self.instGui.ccd_tab.inst_Obtype_s.currentIndex()==2:
            txt="DARK seq="+txt+"\n"
            self.planrunner.load_nightplan_string('sequence', txt, overwrite=True)
            self.planrunner.run_nightplan('sequence',step_id="00")
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
            if temp>-80 and temp<20:
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
        if float(ccd_temp)>-49.: self.instGui.ccd_tab.inst_ccdTemp_e.setStyleSheet("color: rgb(204,0,0)")
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
        self.mount_con=self.mount.connected
        if self.mount_con:
           self.mntGui.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           self.mntGui.mntConn1_l.setStyleSheet("color: rgb(0,150,0);")
        else:
           self.mntGUI.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


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
        self.dome_con=self.dome.connected
        if self.dome_con:
           self.mntGui.domeConn2_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           #self.mntGui.domeConn1_l.setText("Dome Connected")
           self.mntGui.domeConn1_l.setStyleSheet("color: rgb(0,150,0);")
        else:
           self.domeGUI.domeConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))
           #self.mntGui.domeConn1_l.setText("Dome NOT Connected")

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
        self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
        #logger.info(f"Updater named {event.name} change field value")
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
        self.fw_con=self.fw.connected
        if self.fw_con:
           self.mntGui.comFilter_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           self.mntGui.telFilter_l.setStyleSheet("color: rgb(0,150,0);")
        else:
           self.domeGUI.comFilter_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))

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
        print("act: ", pos)
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
        self.rotator_con=self.rotator.connected
        if self.rotator_con:
           self.mntGui.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
           self.mntGui.telRotator1_l.setStyleSheet("color: rgb(0,150,0);")
        else:
           self.domeGUI.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


    async def rotator_update(self, event):
        self.rotator_pos = self.rotator.position
        self.mntGui.telRotator1_e.setText(f"{self.rotator_pos:.2f}")

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        txt="Control requested"
        self.obsGui.main_form.control_e.setText(txt)
        self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(136, 142, 228); color: black;")
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
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(0,150,0);")
            #self.msg(f"{txt} have controll","green")
        elif  self.user.current_user["name"]==self.myself:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(150,0,0);")
            #self.msg(f"{txt} DON'T have controll","red")
        else:
            self.obsGui.main_form.control_e.setStyleSheet("background-color: rgb(255, 255, 255); color: black;")
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
