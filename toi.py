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
from instrument_gui import InstrumentGui
from mnt_gui import MntGui
from pery_gui import PeryphericalGui
from plan_gui import PlanGui
from sky_gui import SkyView
from tel_gui import TelGui

logger = logging.getLogger(__name__)


class Monitor(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    ding = QtCore.pyqtSignal()

    def __init__(self, parent):
        self.parent = parent
        QtCore.QObject.__init__(self)
        self.continue_run = True
        self.sleep_time = 1

    def run(self):
        while self.continue_run:  # give the loop a stoppable condition
            QtCore.QThread.sleep(self.sleep_time)
            self.check()
        self.finished.emit()  # emit the finished signal when the loop is done

    def check(self):
        return
        self.parent.connection_ok = False
        try:
            quest = "http://localhost/api/v1/telescope/0/connected"
            r = requests.get(quest, timeout=1)
            r = r.json()
            self.parent.conected = (r["Value"])
            self.parent.connection_ok = True
        except Exception as e:
            print(e)
            ok = False
            print("no connection")
            self.parent.connection_ok = False

        if self.parent.connection_ok:
            quest = "http://172.23.68.211:11111/api/v1/telescope/0/tracking"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_trac = r["Value"]

            # nie wiem czemu to nie dziala
            quest = "http://172.23.68.211:11111/api/v1/telescope/0/atpark"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_park = r["Value"]
            # print(r)

            quest = "http://172.23.68.211:11111/api/v1/telescope/0/slewing"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_slewing = r["Value"]
            # print(r)

            # quest="http://172.23.68.211:11111/api/v1/telescope/0/"
            # r=requests.get(quest)
            # r=r.json()
            # print(r["Value"])

            quest = "http://172.23.68.211:11111/api/v1/telescope/0/rightascension"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_ra = "%.4f" % r["Value"]

            quest = "http://172.23.68.211:11111/api/v1/telescope/0/declination"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_dec = "%.4f" % r["Value"]

            quest = "http://172.23.68.211:11111/api/v1/telescope/0/azimuth"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_az = "%.4f" % r["Value"]

            quest = "http://172.23.68.211:11111/api/v1/telescope/0/altitude"
            r = requests.get(quest)
            r = r.json()
            self.parent.mnt_alt = "%.4f" % r["Value"]

        self.ding.emit()

    def stop(self):
        self.continue_run = False  # set the run condition to false on stop


class TOI(QtWidgets.QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    APP_NAME = "TOI app"

    def __init__(self, loop=None, client_api=None, app=None):
        self.app = app
        super().__init__(loop=loop, client_api=client_api)
        # window title
        self.setWindowTitle(self.APP_NAME)
        # layout
        self.setLayout(QtWidgets.QVBoxLayout())

        # Monitor Thread:
        self.thread = QtCore.QThread()
        self.monitor = Monitor(self)

        self.monitor.moveToThread(self.thread)
        self.monitor.finished.connect(self.thread.quit)  # connect monitor finished signal to stop thread
        self.monitor.finished.connect(self.monitor.deleteLater)

        self.thread.started.connect(self.monitor.run)
        self.thread.finished.connect(self.monitor.stop)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        self.observatory = Cfg.get("OBSERVATORY_COORD")

        # self.mnt_az = "unknown"  # ?
        # self.mnt_alt = "unknown"  # ?

        self.mnt = MntGui(self, loop=self.loop, client_api=self.client_api)
        # self.layout().addWidget(self.mnt)
        self.mnt.show()
        self.mnt.raise_()

        self.planGui = PlanGui(self)
        # self.layout().addWidget(self.planGui)
        self.planGui.show()
        self.planGui.raise_()

        self.pery = PeryphericalGui(self, loop=self.loop, client_api=self.client_api)
        self.pery.show()
        self.pery.raise_()

        self.tel = TelGui(self, loop=self.loop, client_api=self.client_api)
        self.tel.show()
        self.tel.raise_()

        self.sky = SkyView(self)
        self.sky.show()
        self.sky.raise_()

        self.inst = InstrumentGui()
        self.inst.show()
        self.inst.raise_()

        # self.show()
        # self.raise_()

    async def on_start_app(self):
        await self.mnt.on_start_app()
        await self.pery.on_start_app()
        await self.tel.on_start_app()

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
