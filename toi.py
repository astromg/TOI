#!/usr/bin/env python3

# ----------------
# 1.08.2022
# Marek Gorski
# ----------------
import asyncio

import requests
from PyQt5 import QtCore, QtWidgets
import sys
import qasync as qs

from ob.comunication.client import Client
from ob.comunication.client_api import ClientAPI

from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget
from config_service import Config as Cfg
from instrument_gui import InstrumentGui
from mnt_gui import MntGui
from pery_gui import PeryphericalGui
from plan_gui import PlanGui
from sky_gui import SkyView
from tel_gui import TelGui


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

    def __init__(self, loop=None, client_api=None):
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

        self.pery = PeryphericalGui(self)
        self.pery.show()
        self.pery.raise_()

        self.tel = TelGui(self)
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

    def close(self):
        sys.exit()

    async def task_starter(self):
        await self.mnt.task_starter()
        # li1 = self.loop.create_task(listener(api, address1, display1, name="sub1"))  # 'fire and forget' don't await


def main():
    # todo tu można odpytywać przy odpaleniu kto urzywa apki a alb obrać bomyślnie 'guest'
    client = Client(name="TOI client")
    api = ClientAPI(client=client, user_email="", user_name="GuestTOI",
                    user_description="TOI user interface client.")

    app = QtWidgets.QApplication(sys.argv)

    loop = qs.QEventLoop(app)
    asyncio.set_event_loop(loop)

    toi = TOI(loop=loop, client_api=api)

    # sys.exit(app.exec_())
    with loop:
        loop.run_until_complete(toi.task_starter())
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
