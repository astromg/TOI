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
from PyQt5 import QtCore, QtWidgets
import sys
import qasync as qs

from ob.comunication.client import Client
from ob.comunication.client_api import ClientAPI
from ob.ob_config import SingletonConfig

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

logger = logging.getLogger(__name__)


class TOI(QtWidgets.QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    APP_NAME = "TOI app"

    def __init__(self, loop=None, client_api=None, app=None):
        self.app = app
        super().__init__(loop=loop, client_api=client_api)
        self.setWindowTitle(self.APP_NAME)
        self.setLayout(QtWidgets.QVBoxLayout())

        self.observatory = Cfg.get("OBSERVATORY_COORD")

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
        self.obs_tel_in_table=["WK06","ZB08","JK15","WG25","SIM"]
        self.obs_dome_in_table=["Moving","Open","Close","Parked","--"]
        self.obs_mount_in_table=["Parked","Slewing","Tracking","Guiding","Parked"]
        self.obs_inst_in_table=["Idle","--","Reading","Exposing V","Exposing K"]
        self.obs_program_in_table=["Sky Flats","--","Dome Flast","Cep34565","Focusing"]

        # active telescope
        self.active_tel="SIM"

        # window generation

        self.planGui = PlanGui(self)
        self.planGui.show()
        self.planGui.raise_()

        self.auxGui = AuxGui(self)
        self.auxGui.show()
        self.auxGui.raise_()

        #self.pery = PeryphericalGui(self, loop=self.loop, client_api=self.client_api)
        #self.pery.show()
        #self.pery.raise_()

        #self.tel = TelGui(self, loop=self.loop, client_api=self.client_api)
        #self.tel.show()
        #self.tel.raise_()

        self.inst = InstrumentGui(self)
        self.inst.show()
        self.inst.raise_()

        self.mnt = MntGui(self, loop=self.loop, client_api=self.client_api)
        self.mnt.show()
        self.mnt.raise_()

        self.obs_gui=ObsGui(self)
        self.obs_gui.show()
        self.obs_gui.raise_()


    async def on_start_app(self):
        await self.mnt.on_start_app()
        #await self.pery.on_start_app()
        #await self.tel.on_start_app()

    @qs.asyncClose
    async def closeEvent(self, event):
        super().closeEvent(event)


async def run_qt_app():
    SingletonConfig.add_config_file(
        str(pathlib.PurePath(Cfg.get("PATH_TO_CONFIG_DIR"), "configuration", "config.yaml")))
    SingletonConfig.get_config(rebuild=True).get()

    # todo tu można odpytywać przy odpaleniu kto urzywa apki a alb obrać bomyślnie 'guest'
    client = Client(name="TOI_client")
    api = ClientAPI(client=client, user_email="", user_name="GuestTOI",
                    user_description="TOI user interface client.")

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
