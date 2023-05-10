#!/usr/bin/env python3

import math
import numpy

import qasync as qs
from qasync import QEventLoop
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel, QCheckBox, QTextEdit, QLineEdit, QDialog, \
    QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from toi_lib import *


class ObsGui(QMainWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        super().__init__(loop=loop, client_api=client_api)
        # super(QMainWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Telescope Operator Interface')
        self.main_form = MainForm(self.parent)
        self.setCentralWidget(self.main_form)
        self.resize(self.parent.obs_window_size[0], self.parent.obs_window_size[1])
        self.move(self.parent.obs_window_position[0], self.parent.obs_window_position[0])

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        super().closeEvent(event)


class MainForm(QWidget):
    def __init__(self, parent):
        super(MainForm, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")

        self.mkUI()
        # self.update_table()
        self.obs_t.itemSelectionChanged.connect(self.pocisniecie_tab)
        self.exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())

    @qs.asyncSlot()
    async def pocisniecie_tab(self):
        i = self.obs_t.currentRow()
        self.parent.active_tel_i = i
        self.parent.active_tel = self.parent.obs_tel_in_table[i]
        await self.parent.teleskop_switched()

    def update_table(self):
        # print(self.parent.tel["wk06"].state["dome"])

        #TODO: I would get rid of this, first - it's hardcoded, second - it introduces another notation for
        # telescopes names (mikolaj)
        # translate_tel_names = {"wk06": "WK-06", "zb08": "ZB-08", "jk15": "JK-15", "wg25": "WG-25", "sim": "SIM"}
        translate_tel_names = {"wk06": "WK-06", "zb08": "ZB-08", "jk15": "JK-15", "sim": "SIM"}

        for i, tel in enumerate(self.parent.obs_tel_tic_names):
            state = self.parent.tel[tel].state["name"]
            txt = translate_tel_names[state]
            item = QTableWidgetItem(txt)
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setTextAlignment(QtCore.Qt.AlignVCenter)
            self.obs_t.setItem(i, 0, item)

            item = QTableWidgetItem(" -- ")
            if "dome" in self.parent.tel[tel].state.keys():
                state = self.parent.tel[tel].state["dome"]
                if state == 0:
                    item = QTableWidgetItem("OPEN")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 150, 0)))
                elif state == 1:
                    item = QTableWidgetItem("CLOSED")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                elif state == 2:
                    item = QTableWidgetItem("OPENING")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(255, 160, 0)))
                elif state == 3:
                    item = QTableWidgetItem("CLOSING")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(255, 160, 0)))
                else:
                    item = QTableWidgetItem("ERROR")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(150, 0, 0)))
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setTextAlignment(QtCore.Qt.AlignVCenter)
            self.obs_t.setItem(i, 1, item)

            item = QTableWidgetItem(" -- ")
            if "mount" in self.parent.tel[tel].state.keys():
                state = self.parent.tel[tel].state["mount"]
                if state == "Motors off":
                    item = QTableWidgetItem("Motors OFF")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                elif state == "IDLE":
                    item = QTableWidgetItem("IDLE")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                elif state == "Tracking":
                    item = QTableWidgetItem("Tracking")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 150, 0)))
                elif state == "Slewing":
                    item = QTableWidgetItem("Slewing")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(255, 160, 0)))
                else:
                    item = QTableWidgetItem("unknown")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setTextAlignment(QtCore.Qt.AlignVCenter)
            self.obs_t.setItem(i, 2, item)

            item = QTableWidgetItem(" -- ")
            if "instrument" in self.parent.tel[tel].state.keys():
                state = self.parent.tel[tel].state["instrument"]
                if state == "warm":
                    item = QTableWidgetItem("warm")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(150, 0, 0)))
                elif state == "IDLE":
                    item = QTableWidgetItem("IDLE")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                elif "exposing" in state:
                    item = QTableWidgetItem(state)
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 150, 0)))
                else:
                    item = QTableWidgetItem("unknown")
                    item.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setTextAlignment(QtCore.Qt.AlignVCenter)
            self.obs_t.setItem(i, 3, item)

        for i, txt in enumerate(self.parent.obs_tel_in_table):
            txt = self.parent.obs_program_in_table[i]
            item = QTableWidgetItem(txt)
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setTextAlignment(QtCore.Qt.AlignVCenter)
            self.obs_t.setItem(i, 4, item)

    def msg(self, txt, color):
        c = QtCore.Qt.black
        if "yellow" in color: c = QtCore.Qt.darkYellow
        if "green" in color: c = QtCore.Qt.darkGreen
        if "red" in color: c = QtCore.Qt.darkRed
        self.msg_e.setTextColor(c)
        ut = str(self.parent.ut).split()[1].split(":")[0] + ":" + str(self.parent.ut).split()[1].split(":")[1]
        txt = ut + " " + txt
        self.msg_e.append(txt)

    # =================== OKNO GLOWNE ====================================
    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.tic_l = QLabel("TIC")
        self.tic_l.setStyleSheet("color: rgb(150,0,0);")
        self.ticStatus2_l = QLabel("\U0001F534")

        # self.control_l=QLabel("Controler:")
        self.control_e = QLineEdit("--")
        self.control_e.setReadOnly(True)
        self.control_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.takeControl_p = QPushButton('Take Control')
        self.takeControl_p.clicked.connect(self.parent.takeControl)

        grid.addWidget(self.ticStatus2_l, w, 0)
        grid.addWidget(self.tic_l, w, 1)
        # grid.addWidget(self.control_l, w,3)
        grid.addWidget(self.control_e, w, 2, 1, 4)
        grid.addWidget(self.takeControl_p, w, 6)
        w = w + 1
        self.date_l = QLabel("Date:")
        self.date_e = QLineEdit("--/--/--")
        self.date_e.setReadOnly(True)
        self.date_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.ut_l = QLabel("UT:")
        self.ut_e = QLineEdit("--:--:--")
        self.ut_e.setReadOnly(True)
        self.ut_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        grid.addWidget(self.date_l, w, 0)
        grid.addWidget(self.date_e, w, 1)

        grid.addWidget(self.ut_l, w, 2)
        grid.addWidget(self.ut_e, w, 3)

        w = w + 1

        self.ojd_l = QLabel("OJD:")
        self.ojd_e = QLineEdit("--")
        self.ojd_e.setReadOnly(True)
        self.ojd_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.sid_l = QLabel("SID:")
        self.sid_e = QLineEdit("--:--:--")
        self.sid_e.setReadOnly(True)
        self.sid_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        grid.addWidget(self.ojd_l, w, 0)
        grid.addWidget(self.ojd_e, w, 1)

        grid.addWidget(self.sid_l, w, 2)
        grid.addWidget(self.sid_e, w, 3)

        w = w + 1
        self.obs_t = QTableWidget(5, 5)
        self.obs_t.setHorizontalHeaderLabels(["Telescope", "Dome", "Mount", "Instrument", "Program"])
        self.obs_t.setSelectionBehavior(QTableWidget.SelectRows)
        self.obs_t.setSelectionMode(QTableWidget.SingleSelection)
        self.obs_t.verticalHeader().hide()
        self.obs_t.setShowGrid(False)
        self.obs_t.setStyleSheet("selection-background-color: rgb(138,176,219);")
        self.obs_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.obs_t.setFixedWidth(550)  # Size
        self.obs_t.setStyleSheet("font-size: 9pt;")
        grid.addWidget(self.obs_t, w, 0, 1, 5)

        w = w + 1
        self.shutdown_p = QPushButton('Shutdown')
        self.weatherStop_p = QPushButton('Weather Stop')
        self.EmStop_p = QPushButton('Emergency Stop')

        grid.addWidget(self.shutdown_p, w, 0)
        grid.addWidget(self.weatherStop_p, w, 1)
        grid.addWidget(self.EmStop_p, w, 3)

        w = w + 1
        self.msg_e = QTextEdit()
        self.msg_e.setReadOnly(True)
        self.msg_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.msg_e, w, 0, 3, 5)

        # #### tutaj SkyRadar  ####
        w = 1
        self.skyView = SkyView(self.parent)
        grid.addWidget(self.skyView, w, 5, 6, 2)
        w = w + 6
        self.exit_p = QPushButton('Exit')
        grid.addWidget(self.exit_p, w, 5, 1, 2)

        # grid.setColumnMinimumWidth(6,100)
        # grid.setColumnMinimumWidth(8,100)
        # grid.setColumnMinimumWidth(10,100)

        # grid.setSpacing(10)

        self.setLayout(grid)

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        super().closeEvent(event)


# ############# SKY RADAR ################################

class SkyView(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.mkUI()
        cid = self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

        self.canSetNext = False

        self.tel_az = 5
        self.tel_alt = 90

        self.a = []
        self.h = []
        self.symbol = []

        self.silent_a = []
        self.silent_h = []
        self.silent_symbol = []

        self.rmax = 110
        self.marc_point = False

        self.a = [10, 20, 30, 40, 50, 100, 40, 40, 70]
        self.h = [50, 50, 50, 50, 50, 30, 40, 40, 20]
        self.symbol = ["b*", "b*", "b*", "b*", "b*", "ok", "or", "+r", ".r"]
        self.alpha = [0.8, 0.6, 0.5, 0.3, 0.3, 0.6, 0.3, 1, 1]

        self.log_a = [10, 20, 30]
        self.log_h = [30, 30, 30]
        self.log_s = ["k*", "k*", "k*"]
        self.log_alh = [0.5, 0.5, 0.5]

        self.update()

        self.dome_az = 0
        self.dome_color = "r"

        # self.updateDome()

    def update(self):
        self.axes.clear()

        self.axes.set_theta_direction(-1)
        self.axes.set_theta_zero_location('N')
        self.axes.set_ylim([0, 360])
        self.axes.set_rlim([0, 30])
        self.axes.set_xticks([0, 2 * 3.14 * 90 / 360, 2 * 3.14 * 180 / 360, 2 * 3.14 * 270 / 360])
        self.axes.set_xticklabels(["N", "E", "S", "W"])
        self.axes.set_rmax(self.rmax)
        self.axes.set_rticks([20, 40, 60, 90])
        self.axes.set_yticklabels(["", "", "", ""])
        self.axes.bar(0, self.rmax - 90, width=2 * math.pi, bottom=90, color='k',
                      alpha=0.05)  # tutaj zmienia sie pasek ponizej horyzoontu

        self.canvas.draw()
        self.show()

    def updateAlmanac(self):
        try:
            self.txt1.remove()
            self.txt2.remove()
            self.txt3.remove()
            self.txt4.remove()
            self.txt5.remove()
            for p in self.sun: p.remove()
            for p in self.moon: p.remove()
            for p in self.nextOb: p.remove()
        except:
            pass
        sunrise_tmp = str(self.parent.sunrise).split()[1]
        sunset_tmp = str(self.parent.sunset).split()[1]
        sunrise = sunrise_tmp.split(":")[0] + ":" + sunrise_tmp.split(":")[1]
        sunset = sunset_tmp.split(":")[0] + ":" + sunset_tmp.split(":")[1]

        moonrise_tmp = str(self.parent.moonrise).split()[1]
        moonset_tmp = str(self.parent.moonset).split()[1]
        moonrise = moonrise_tmp.split(":")[0] + ":" + moonrise_tmp.split(":")[1]
        moonset = moonset_tmp.split(":")[0] + ":" + moonset_tmp.split(":")[1]
        moon_phase = f"{self.parent.moon_phase:.2f}"

        r, fi = 195, 314.7
        fi = fi * 2 * 3.14 / 360.
        self.txt1 = self.axes.text(fi, r, f"Sunset: {sunset}", fontsize=9)

        r, fi = 183.8, 311
        fi = fi * 2 * 3.14 / 360.
        self.txt2 = self.axes.text(fi, r, f"Sunrise: {sunrise}", fontsize=9)

        r, fi = 175, 232
        fi = fi * 2 * 3.14 / 360.
        self.txt3 = self.axes.text(fi, r, f"Moon: {moon_phase}", fontsize=9)

        r, fi = 186.5, 228
        fi = fi * 2 * 3.14 / 360.
        self.txt4 = self.axes.text(fi, r, f"Moonrise: {moonrise}", fontsize=9)

        r, fi = 198, 224
        fi = fi * 2 * 3.14 / 360.
        self.txt5 = self.axes.text(fi, r, f"Moonset: {moonset}", fontsize=9)

        self.sun = self.axes.plot(self.parent.sun_az * 2 * 3.14 / 360., 90 - self.parent.sun_alt, "oy", alpha=0.7)
        self.moon = self.axes.plot(self.parent.moon_az * 2 * 3.14 / 360., 90 - self.parent.moon_alt, "ok", alpha=0.7)

        try:
            next_az = self.parent.mntGui.nextAz_e.text()
            next_alt = self.parent.mntGui.nextAlt_e.text()
            next_az = float(next_az) * 2 * 3.14 / 360.
            next_alt = 90 - float(next_alt)
            self.nextOb = self.axes.plot(next_az, next_alt, "xb")
        except:
            pass

        self.canvas.draw()
        self.show()

    def updateRadar(self):
        try:
            for p in self.stars: p[0].remove()
        except:
            pass
        self.stars = []
        self.plan = self.parent.planGui.plan
        self.plan_i = int(self.parent.planGui.i)
        self.plan_next_i = int(self.parent.planGui.next_i)
        if len(self.plan) > 0:
            self.plan_to_show = self.plan

            try:
                star = self.plan_to_show[self.plan_i]
                az = float(star["meta_az"])
                az = az * 2 * 3.14 / 360.
                alt = 90 - float(star["meta_alt"])
                point = self.axes.plot(az, alt, color="red", marker="o", markersize="10", markerfacecolor="white",
                                       alpha=0.5)
                self.stars.append(point)
            except:
                pass

            alpha = 1
            n = 0
            k = 0
            for star in self.plan_to_show:
                n = n + 1
                if n > self.plan_next_i:
                    try:
                        if k == 0:
                            alpha = 1
                        elif k == 1:
                            alpha = 0.7
                        elif k == 2:
                            alpha = 0.5
                        elif k == 3:
                            alpha = 0.3
                        elif k == 4:
                            alpha = 0.2
                        else:
                            alpha = 0.1
                        az = float(star["meta_az"])
                        az = az * 2 * 3.14 / 360.
                        alt = 90 - float(star["meta_alt"])
                        point = self.axes.plot(az, alt, color="b", marker="*", alpha=alpha)
                        self.stars.append(point)
                        k = k + 1
                    except:
                        pass

            self.canvas.draw()
            self.show()

    def updateMount(self):
        try:
            for p in self.mount: p.remove()
        except:
            pass
        color = "r"
        if self.parent.mount_tracking: color = "g"
        if self.parent.mount_slewing: color = "orange"
        alt = 90 - self.parent.mount_alt
        az = self.parent.mount_az
        az = az * 2 * 3.14 / 360.
        self.mount = self.axes.plot(az, alt, color=color, marker="+")
        self.canvas.draw()
        self.show()

    def updateDome(self):
        try:
            self.dome.remove()
        except:
            pass
        if self.parent.dome_shutterstatus == 0:
            color = "g"
        elif self.parent.dome_shutterstatus == 1:
            color = "r"
        elif self.parent.dome_shutterstatus == 2:
            color = "orange"
        elif self.parent.dome_shutterstatus == 3:
            color = "orange"
        else:
            color = "b"
        ok = False
        try:
            float(self.parent.dome_az)
            ok = True
        except:
            ok = False
        if ok:
            dome_az = float(self.parent.dome_az) * (2 * math.pi) / 360.
            self.dome = self.axes.bar(dome_az, self.rmax - 90, width=30 * (2 * math.pi) / 360., bottom=90, color=color,
                                      alpha=0.5)
        self.canvas.draw()
        self.show()

    # ======= Budowa okna ====================

    def mkUI(self):
        # self.setWindowTitle('FC')
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111, polar=True)
        # self.axes.set_theta_zero_location('N')

        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()

        self.snap_c = QCheckBox("Snap to objects")
        self.snap_c.setChecked(True)

        self.setNext_p = QPushButton('Set Next')
        self.setNext_p.clicked.connect(self.SetNext)

        hbox1.addWidget(self.snap_c)
        hbox1.addWidget(self.setNext_p)

        hbox2.addWidget(self.canvas)

        self.vbox = QVBoxLayout()
        self.vbox.addLayout(hbox1)
        self.vbox.addLayout(hbox2)
        self.vbox.setSpacing(10)
        self.setLayout(self.vbox)

        # self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw()
        # self.axes.grid(True)
        # self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])
        # self.axes.set_yticks([20,40,60,80])
        # self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)
        # self.axes.set_rmax(self.rmax)

    #  ============ Klikanie w punkciki ==========================

    def SetNext(self):
        if self.canSetNext == True:
            self.canSetNext = False
            self.setNext_p.setStyleSheet("color: black;")
        else:
            self.canSetNext = True
            self.setNext_p.setStyleSheet("color: blue;")

    def zaznaczenie(self, event):
        az = 360. * (float(event.xdata) / (2 * 3.14))
        if az < 0: az = az + 360.
        alt = 90 - float(event.ydata)
        if self.snap_c.isChecked():
            ii = 0
            if len(self.plan) > 0:
                przetrzymywacz = 1000.
                for i, tmp in enumerate(self.plan):
                    if "meta_alt" in self.plan[i].keys() and "meta_az" in self.plan[i].keys():
                        h1 = 90. - float(alt)
                        a1 = 2 * math.pi * (float(az)) / 360.
                        h2 = 90. - float(self.plan[i]["meta_alt"])
                        a2 = 2 * math.pi * (float(self.plan[i]["meta_az"])) / 360.
                        delta = (h1 ** 2 + h2 ** 2 - 2 * h1 * h2 * math.cos(a1 - a2)) ** 0.5
                        if delta < przetrzymywacz:
                            ii = i
                            przetrzymywacz = delta
                self.parent.planGui.i = ii
                if self.canSetNext:
                    self.parent.planGui.next_i = ii
                    self.canSetNext = False
                    self.setNext_p.setStyleSheet("color: black;")
                self.parent.planGui.update_table()


        else:
            if self.canSetNext:
                self.parent.mntGui.setAltAz_r.setChecked(True)
                self.parent.mntGui.nextAlt_e.setText(f"{alt:.3f}")
                self.parent.mntGui.nextAz_e.setText(f"{az:.3f}")
                self.canSetNext = False
                self.setNext_p.setStyleSheet("color: black;")

        self.updateMount()
