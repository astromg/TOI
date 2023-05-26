#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QTabWidget, QApplication, QWidget, QLabel, QCheckBox, QTextEdit, QLineEdit, QDialog, \
    QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
import paho.mqtt.client as mqtt
import json


class AuxGui(QWidget):
    def __init__(self, parent):
        super(AuxGui, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.setGeometry(self.parent.aux_geometry[0], self.parent.aux_geometry[1], self.parent.aux_geometry[2],
                         self.parent.aux_geometry[3])

        self.updateUI()

    def updateUI(self):

        local_dic = {"WK06": 'WK06 Aux Monitor', "ZB08": 'ZB08 Aux Monitor', "JK15": 'JK15 Aux Monitor', "SIM": 'SIM Aux Monitor'}
        # local_dic = {"WK06": 'WK06 Aux Monitor', "ZB08": 'ZB08 Aux Monitor', "JK15": 'JK15 Aux Monitor',
        #              "WG25": 'WG25 Aux Monitor', "SIM": 'SIM Aux Monitor'}
        try:
            txt = local_dic[self.parent.active_tel]
        except:
            txt = "unknow Aux Monitor"
        self.setWindowTitle(txt)

        tmp = QWidget()
        try:
            tmp.setLayout(self.layout)
        except:
            pass

        self.layout = QGridLayout()
        self.setLayout(self.layout)

        self.tabWidget = QTabWidget()

        self.welcome_tab = WelcomeGui(self.parent)
        self.tabWidget.addTab(self.welcome_tab, "Welcome")

        self.focus_tab = FocusGui(self.parent)
        self.tabWidget.addTab(self.focus_tab, "Focus")

        # Sorry I'm commenting it out temporarly
        # Because weather is generating errors constantly
        # We took over your develomnet branch, but we can switch to mster
        # when you synchronize.... (mikolaj)

        # self.guider_tab = GuiderGui(self.parent)
        # self.tabWidget.addTab(self.guider_tab, "Guider")

        # self.flat_tab = FlatGui(self.parent)
        # self.tabWidget.addTab(self.flat_tab, "Flats")

        # self.weather_tab = WeatherGui(self.parent)
        # self.tabWidget.addTab(self.weather_tab, "Weather")
        # self.weather_tab.update()
        #
        # self.cctv_tab = CctvGui(self.parent)
        # self.tabWidget.addTab(self.cctv_tab, "CCTV")

        self.fits_tab = FitsGui(self.parent)
        self.tabWidget.addTab(self.fits_tab, "Fits")

        self.layout.addWidget(self.tabWidget, 0, 0)
        del tmp


class WelcomeGui(QWidget):
    def __init__(self, parent):
        super(WelcomeGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.pic_l = QLabel(" ")
        if self.parent.active_tel == "WK06":
            png_file = './Icons/wk06.png'
        elif self.parent.active_tel == "ZB08":
            png_file = './Icons/zb08.png'
        elif self.parent.active_tel == "JK15":
            png_file = './Icons/jk15.png'
        elif self.parent.active_tel == "WG25":
            png_file = './Icons/wg25.png'
        elif self.parent.active_tel == "SIM":
            png_file = './Icons/oca.png'
        self.pic_l.setPixmap(QtGui.QPixmap(png_file).scaled(400, 300))
        grid.addWidget(self.pic_l, w, 0)
        self.setLayout(grid)


# ############### FOCUS ##########################

class FocusGui(QWidget):
    def __init__(self, parent):
        super(FocusGui, self).__init__()
        self.parent = parent
        self.mkUI()
        self.x = []
        self.y = []
        self.fit_x = []
        self.fit_y = []
        self.max_sharp = None
        self.update()

    def update(self):
        self.axes.clear()
        if len(self.x) > 1 and len(self.y) > 1:
            self.axes.plot(self.x, self.y, "r.")
        if len(self.fit_x) > 1 and len(self.fit_y) > 1:
            self.axes.plot(self.fit_x, self.fit_y)
        if self.max_sharp:
            self.axes.axvline(x=self.max_sharp, color="red", alpha=1)
        self.axes.set_ylim(self.axes.get_ylim()[::-1])
        self.axes.set_xlabel("focus encoder position")
        self.axes.set_ylabel("sharpness")
        self.canvas.draw()
        self.show()

    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.fig = Figure((1, 1), linewidth=1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0.1, 0.2, 0.8, 0.75])
        grid.addWidget(self.canvas, w, 0, 1, 4)

        w = w + 1

        self.last_l = QLabel("Last Value:")
        self.last_e = QLineEdit()
        self.last_e.setText("15580")

        self.range_l = QLabel("STEPS No.:")
        self.range_e = QLineEdit()
        self.range_e.setText("10")

        grid.addWidget(self.last_l, w, 0)
        grid.addWidget(self.last_e, w, 1)
        grid.addWidget(self.range_l, w, 2)
        grid.addWidget(self.range_e, w, 3)

        w = w + 1

        self.steps_l = QLabel("Step:")
        self.steps_e = QLineEdit()
        self.steps_e.setText("30")

        self.method_l = QLabel("Method:")
        self.method_s = QComboBox()
        self.method_s.addItems(["RMS_QUAD", "RMS"])

        grid.addWidget(self.steps_l, w, 0)
        grid.addWidget(self.steps_e, w, 1)
        grid.addWidget(self.method_l, w, 2)
        grid.addWidget(self.method_s, w, 3)

        w = w + 1
        self.result_l = QLabel("RESULT:")
        self.result_e = QLineEdit()
        self.result_e.setReadOnly(True)

        self.autoFocus_p = QPushButton('FIND FOCUS')
        self.autoFocus_p.clicked.connect(self.parent.auto_focus)
        grid.addWidget(self.result_l, w, 0)
        grid.addWidget(self.result_e, w, 1)
        grid.addWidget(self.autoFocus_p, w, 2, 1, 2)

        self.setLayout(grid)


class GuiderGui(QWidget):
    def __init__(self, parent):
        super(GuiderGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.autoFocus_p = QPushButton('Guide')
        grid.addWidget(self.autoFocus_p, w, 0)

        self.setLayout(grid)


class FlatGui(QWidget):
    def __init__(self, parent):
        super(FlatGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.setLayout(grid)


# ######### weather GUI ##############################

class WeatherGui(QWidget):
    def __init__(self, parent):
        super(WeatherGui, self).__init__()
        self.parent = parent
        self.mqtt_client = mqtt.Client()
        self.ut = ""
        self.wind = ""
        self.temp = ""
        self.mkUI()
        self.update()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.ut_l = QLabel("UT:")
        self.ut_e = QLineEdit()
        grid.addWidget(self.ut_l, w, 0)
        grid.addWidget(self.ut_e, w, 1)
        w = w + 1
        self.wind_l = QLabel("Wind:")
        self.wind_e = QLineEdit()
        grid.addWidget(self.wind_l, w, 0)
        grid.addWidget(self.wind_e, w, 1)
        w = w + 1
        self.temp_l = QLabel("Temp:")
        self.temp_e = QLineEdit()
        grid.addWidget(self.temp_l, w, 0)
        grid.addWidget(self.temp_e, w, 1)
        self.setLayout(grid)

    def update(self):
        try:
            self.mqtt_broker = 'docker.oca.lan'
            self.mqtt_port = 1883
            self.mqtt_topic_weather = 'weather'
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            self.mqtt_client.message_callback_add(self.mqtt_topic_weather, self.on_weather_message)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.loop_start()
            # mqtt_client.loop_stop()
        except:
            pass

    def on_weather_message(self, client, userdata, message):
        weather = message.payload.decode('utf-8')
        weather_dict = json.loads(weather)
        self.ut, self.wind, self.temp = weather_dict["dataGMTTime"], weather_dict["wind"], weather_dict["temp"]
        self.ut_e.setText(self.ut)
        self.wind_e.setText(str(self.wind))
        self.temp_e.setText(str(self.temp))

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0: self.mqtt_client.subscribe((self.mqtt_topic_weather, 1))


class CctvGui(QWidget):
    def __init__(self, parent):
        super(CctvGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.setLayout(grid)


class FitsGui(QWidget):
    def __init__(self, parent):
        super(FitsGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.fitsView = FitsView(self.parent)
        grid.addWidget(self.fitsView, w, 0)
        self.setLayout(grid)


class FitsView(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.mkUI()
        self.colorbar = None

    def update(self, image,sat_coo,ok_coo):
        self.axes.clear()
        self.axes.axis("off")
        vmin = numpy.mean(image) - 1 * numpy.std(image)
        vmax = numpy.mean(image) + 1 * numpy.std(image)

        im = self.image = self.axes.imshow(image, vmin=vmin, vmax=vmax)

        if len(sat_coo)>2:
            x,y = zip(*sat_coo)
            self.axes.plot(x, y, color="red", marker="o", markersize="5", markerfacecolor="none",linestyle="")
        if len(ok_coo)>2:
            x,y = zip(*ok_coo)
            self.axes.plot(x, y, color="white", marker="o", markersize="5", markerfacecolor="none",linestyle="")

        # if self.colorbar is None:
        #     self.colorbar = self.fig.colorbar(im, ax=self.axes)
        # else:
        #     self.colorbar.upate_normal(im)
        # self.violin_axes.clear()
        # self.violin_axes.violinplot(image.flat ,showmeans=False,showmedians=True,showextrema=False)

        self.canvas.draw()
        self.show()

    def mkUI(self):
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes.axis("off")

        # self.violin_axes = self.fig.add_axes([0.82,0.0,0.18,1])
        # self.violin_axes.tick_params(axis='y', which='both', labelleft=False, labelright=True, direction='in')

        grid = QGridLayout()
        grid.addWidget(self.canvas,0,0)

        self.stat_e=QTextEdit()
        self.stat_e.setReadOnly(True)
        self.stat_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.stat_e,1,0)

        grid.setRowMinimumHeight(0,350)
        grid.setRowStretch(0,1)
        grid.setRowStretch(1,0)
        self.setLayout(grid)

        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw()
