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
import pwd
import os

from PyQt5 import QtGui
from PyQt5 import QtCore, QtWidgets
import sys
import qasync as qs

from ocaboxapi import ClientAPI, Observatory
#from ob.ob_config import SingletonConfig

from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from config_service import Config as Cfg


from obs_gui import ObsGui
from aux_gui import AuxGui

from mnt_gui import MntGui
from pery_gui import PeryphericalGui
from plan_gui import PlanGui
from sky_gui import SkyView
from tel_gui import TelGui
from instrument_gui import InstrumentGui

logging.basicConfig(level='INFO')

logger = logging.getLogger(__name__)


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

        self.observatory = Cfg.get("OBSERVATORY_COORD")

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

        # obs model
        self.obs_tel_tic_names=["wk06","zb08","jk15","wg25","sim"]
        self.obs_tel_in_table=["WK06","ZB08","JK15","WG25","SIM"]
        self.obs_dome_in_table=["Moving","Open","Close","Parked","--"]
        self.obs_mount_in_table=["Parked","Slewing","Tracking","Guiding","Parked"]
        self.obs_inst_in_table=["Idle","--","Reading","Exposing V","Exposing K"]
        self.obs_program_in_table=["Sky Flats","--","Dome Flast","Cep34565","Focusing"]

        # active telescope
        self.active_tel_i=4
        self.active_tel="SIM"

        self.dome_con=False
        self.dome_shutterstatus="--"
        self.dome_az="--"
        self.dome_status="--"



        # window generation

        self.obsGui=ObsGui(self, loop=self.loop, client_api=self.client_api)
        self.obsGui.show()
        self.obsGui.raise_()

        self.mntGui = MntGui(self, loop=self.loop, client_api=self.client_api)
        self.mntGui.show()
        self.mntGui.raise_()

        self.inst = InstrumentGui(self)
        self.inst.show()
        self.inst.raise_()

        self.planGui = PlanGui(self)
        self.planGui.show()
        self.planGui.raise_()

        self.auxGui = AuxGui(self)
        self.auxGui.show()
        self.auxGui.raise_()


    #  ############# ZMIANA TELESKOPU #################
    async def teleskop_switched(self):
        tel=self.obs_tel_tic_names[self.active_tel_i]
        self.dome_con=False
        self.dome_az="--"

        await self.stop_background_tasks()

        self.user = self.observatory_model.get_telescope(tel).get_access_grantor()
        self.dome = self.observatory_model.get_telescope(tel).get_dome()

        self.add_background_task(self.user.asubscribe_current_user(self.user_update))

        self.add_background_task(self.dome.asubscribe_connected(self.domeCon_update))
        self.add_background_task(self.dome.asubscribe_shutterstatus(self.domeShutterStatus_update))
        self.add_background_task(self.dome.asubscribe_az(self.domeAZ_update))
        self.add_background_task(self.dome.asubscribe_slewing(self.domeStatus_update))

        await self.run_background_tasks()

        self.mntGui.updateUI()
        self.auxGui.updateUI()
        self.planGui.updateUI()

    # ################### METODY POD SUBSKRYPCJE ##################

    # #### USER #########

    @qs.asyncSlot()
    async def takeControl(self):
        txt="Control requested"
        self.obsGui.main_form.control_e.setText(txt)
        try: await self.user.aput_break_control()
        except: pass
        try: await self.user.aput_take_control()
        except: pass

    async def user_update(self, event):
        self.TICuser=self.user.current_user
        txt=str(self.TICuser["name"])
        self.obsGui.main_form.control_e.setText(txt)


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

        else:
           await self.domeShutterStatus_update(False)

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
           if ok and az < 360. and az > 0.:
              await self.dome.aput_slewtoazimuth(az)



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

    async def domeStatus_update(self, event):
           self.dome_status=self.dome.slewing
           if self.dome_status==False:
              txt="STOPED"
              self.mntGui.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
           elif self.dome_status==True:
                txt="MOVING"
                self.mntGui.domeStat_e.setStyleSheet("color: rgb(204,82,0); background-color: rgb(233, 233, 233);")
           else: txt="UNKNOWN"
           self.mntGui.domeStat_e.setText(txt)



    async def domeAZ_update(self, event):
        #self.dome_az=await event.obj.aget_az()
        self.dome_az=self.dome.azimuth
        self.mntGui.domeAz_e.setText(f"{self.dome_az:.2f}")
        #logger.info(f"Updater named {event.name} change field value")
        self.obsGui.main_form.skyView.updateDome()




    async def on_start_app(self):
        await self.run_background_tasks()
        await self.mntGui.on_start_app()
        await self.obsGui.on_start_app()


    @qs.asyncClose
    async def closeEvent(self, event):
        super().closeEvent(event)


async def run_qt_app():
    #SingletonConfig.add_config_file(
        #str(pathlib.PurePath(Cfg.get("PATH_TO_CONFIG_DIR"), "configuration", "config.yaml")))
    #SingletonConfig.get_config(rebuild=True).get()


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
