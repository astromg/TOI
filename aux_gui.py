#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------

from PyQt5.QtCore import Qt
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QTabWidget, QApplication, QWidget, QLabel, QCheckBox, QTextEdit, QLineEdit, QDialog, \
    QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib
import datetime

import numpy
import paho.mqtt.client as mqtt
import json


class AuxGui(QWidget):
    def __init__(self, parent):
        super(AuxGui, self).__init__()
        self.parent = parent
        #self.setStyleSheet("font-size: 11pt;")
        self.setGeometry(self.parent.aux_geometry[0], self.parent.aux_geometry[1], self.parent.aux_geometry[2],
                         self.parent.aux_geometry[3])

        self.updateUI()
        self.show()
        self.raise_()

    def updateUI(self):

        local_dic = {"wk06": 'WK06 Aux Monitor', "zb08": 'ZB08 Aux Monitor', "jk15": 'JK15 Aux Monitor', "sim": 'SIM Aux Monitor'}
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

        self.flat_tab = FlatGui(self.parent)
        self.tabWidget.addTab(self.flat_tab, "Flat")

        self.focus_tab = FocusGui(self.parent)
        self.tabWidget.addTab(self.focus_tab, "Focus")
        self.focus_tab.updateUI()

        self.guider_tab = GuiderGui(self.parent)
        self.tabWidget.addTab(self.guider_tab, "Guider")

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

        txt=""
        plik_teleskopu = None
        if self.parent.active_tel == "wk06":
            png_file = './Icons/wk06.png'
            plik_teleskopu = "./Misc/wk06.txt"

        elif self.parent.active_tel == "zb08":
            png_file = './Icons/zb08.png'
            plik_teleskopu = "./Misc/zb08.txt"




        elif self.parent.active_tel == "jk15":
            png_file = './Icons/jk15.png'
            plik_teleskopu = "./Misc/jk15.txt"

        else: png_file = './Icons/oca.png'

        if plik_teleskopu:
            with open(plik_teleskopu, "r") as plik:
                txt = txt + plik.read()
        with open("./Misc/changelog.txt", "r") as plik:
            txt = txt + plik.read()

        grid = QGridLayout()
        w = 0

        self.pic_l = QLabel(" ")
        self.pic_l.setPixmap(QtGui.QPixmap(png_file).scaled(300, 200))
        grid.addWidget(self.pic_l, w,0,5,1)

        self.wind_l = QLabel("Wind:")
        self.wind_e = QLineEdit()
        self.wind_e.setReadOnly(True)
        self.wind_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.windDir_l = QLabel("Direction:")
        self.windDir_e = QLineEdit()
        self.windDir_e.setReadOnly(True)
        self.windDir_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.temp_l = QLabel("Temp:")
        self.temp_e = QLineEdit()
        self.temp_e.setReadOnly(True)
        self.temp_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.hummidity_l = QLabel("Humidity:")
        self.hummidity_e = QLineEdit()
        self.hummidity_e.setReadOnly(True)
        self.hummidity_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.pressure_l = QLabel("Pressure:")
        self.pressure_e = QLineEdit()
        self.pressure_e.setReadOnly(True)
        self.pressure_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.temp_l, w, 1)
        grid.addWidget(self.temp_e, w, 2)
        w = w + 1
        grid.addWidget(self.hummidity_l, w, 1)
        grid.addWidget(self.hummidity_e, w, 2)
        w = w + 1
        grid.addWidget(self.wind_l, w, 1)
        grid.addWidget(self.wind_e, w, 2)
        w = w + 1
        grid.addWidget(self.windDir_l, w, 1)
        grid.addWidget(self.windDir_e, w, 2)
        w = w + 1
        grid.addWidget(self.pressure_l, w, 1)
        grid.addWidget(self.pressure_e, w, 2)
        w = w + 1
        self.observer_l = QLabel("Welcome observer, please provide Your name:")
        self.observer_e = QLineEdit()

        grid.addWidget(self.observer_l, w, 0,1,4)
        w = w + 1
        grid.addWidget(self.observer_e, w, 0,1,4)

        w = w + 1
        self.info_e=QTextEdit()
        self.info_e.setReadOnly(True)
        self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.info_e.setHtml(txt)
        font=QtGui.QFont("Courier New",10)
        self.info_e.setFont(font)
        grid.addWidget(self.info_e, w,0,1,3)

        self.setLayout(grid)

# ############### FLAT ############################
class FlatGui(QWidget):
    def __init__(self, parent):
        super(FlatGui, self).__init__()
        self.parent = parent
        self.mkUI()
        #self.show()

    def mkUI(self):

        grid = QGridLayout()
        self.dupa_l = QLabel("SKYFLATS:")
        grid.addWidget(self.dupa_l, 0, 0)

        self.info_e=QTextEdit()
        self.info_e.setReadOnly(True)
        #self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
        font=QtGui.QFont("Courier New",10)
        self.info_e.setFont(font)
        self.info_e.append("date UT  filter  exp  h_sun  ADU")
        grid.addWidget(self.info_e, 1,0,1,3)

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

        #print(len(self.fwhm),len(self.x))
        # if len(self.fwhm)>0 and  len(self.fwhm)==len(self.x):
        #     self.axes2 = self.axes.twinx()
        #     print("=============== FWHM ==============")
        #     print(self.fwhm)
        #     self.axes2.plot(self.x, self.fwhm, "g.")
        #     self.axes2.set_ylabel("fwhm")
        #self.axes.set_ylim(self.axes.get_ylim()[::-1])
        self.axes.set_xlabel("focus encoder position")
        self.axes.set_ylabel("sharpness")
        self.fig.tight_layout()
        self.canvas.draw()
        self.show()

    def updateUI(self):
        if self.parent.active_tel != None:
            if "focus_def_step" in self.parent.nats_cfg[self.parent.active_tel].keys():
                self.steps_e.setText(str(self.parent.nats_cfg[self.parent.active_tel]["focus_def_step"]))
            if "focus_def_pos" in self.parent.nats_cfg[self.parent.active_tel].keys():
                self.last_e.setText(str(self.parent.nats_cfg[self.parent.active_tel]["focus_def_pos"]))
            self.range_e.setText("8")


    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.fig = Figure((1, 1), linewidth=1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0.1, 0.2, 0.8, 0.75])
        grid.addWidget(self.canvas, w, 0, 1, 4)

        w = w + 1
        self.last_l = QLabel("Central Value:")
        self.last_e = QLineEdit()

        self.range_l = QLabel("Steps No.:")
        self.range_e = QLineEdit()

        grid.addWidget(self.last_l, w, 0)
        grid.addWidget(self.last_e, w, 1)
        grid.addWidget(self.range_l, w, 2)
        grid.addWidget(self.range_e, w, 3)

        w = w + 1
        self.steps_l = QLabel("Step:")
        self.steps_e = QLineEdit()

        self.method_l = QLabel("Method:")
        self.method_s = QComboBox()
        self.method_s.addItems(["LORENTZIAN","RMS_QUAD","RMS"])

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

# ############### GUIDER ###################


class GuiderGui(QWidget):
    def __init__(self, parent):
        super(GuiderGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.guiderView = GuiderView(self.parent)
        grid.addWidget(self.guiderView, w, 0)
        self.setLayout(grid)

class GuiderView(QWidget):
    def __init__(self, parent):
        super(GuiderView, self).__init__()
        self.parent = parent
        self.mkUI()
        self.show()
        self.canvas2.draw()

    def updateCoo(self,x,y,color):
        color=color
        x,y=x,y
        if len(x)>0:
            self.axes.plot(x, y, color=color, marker="o", markersize="10", markerfacecolor="none", linestyle="")
            self.canvas.draw()
            self.show()


    def updateImage(self, image):
        self.image = image
        self.image = numpy.asarray(self.image)
        self.image = self.image.astype(numpy.uint16)
        self.axes.clear()
        self.axes.axis("off")
        if len(self.image)>0:
            vmin = numpy.mean(self.image) - 1 * numpy.std(self.image)
            vmax = numpy.mean(self.image) + 1 * numpy.std(self.image)
            im = self.axes.imshow(self.image, vmin=vmin, vmax=vmax, cmap=matplotlib.colormaps["ocean"])
            self.canvas.draw()
            self.show()


    # def makeDark(self):
    #     self.parent.makeGuiderDark = True
    def update_plot(self,dx,dy):
        self.axes2.clear()
        self.axes2.set_xlim(-50, 50)
        self.axes2.set_ylim(-50, 50)
        self.axes2.axhline(y=0,color="k",linestyle="-",alpha=0.3)
        self.axes2.axvline(x=0,color="k",linestyle="-",alpha=0.3)
        self.axes2.plot([0,0],[0,numpy.sum(dy)],color="red")
        self.axes2.plot([0,numpy.sum(dx)],[0,0],color="red")

        self.axes2.plot(dx, dy, color="b", marker=".", linestyle="",alpha=0.2)
        if len(dx)>0:
            self.axes2.plot(dx[0], dy[0], color="b", marker=".", linestyle="", alpha=1)
        if len(dx)>1:
            self.axes2.plot(dx[1], dy[1], color="b", marker=".", linestyle="", alpha=0.6)
        self.canvas2.draw()

    def mkUI(self):
        if True:
            self.fig = Figure((1.0, 0.5), linewidth=-1, dpi=100)
            self.canvas = FigureCanvas(self.fig)
            self.axes = self.fig.add_axes([0, 0, 1, 1])
            self.axes.axis("off")

            self.fig2 = Figure((0.5, 0.5), linewidth=-1, dpi=100)
            self.canvas2 = FigureCanvas(self.fig2)
            self.axes2 = self.fig2.add_axes([0, 0, 1, 1])
            self.axes2.axis("off")



            grid = QGridLayout()

            w = 0
            grid.addWidget(self.canvas, w, 0,12,2)
            w = w + 12
            #self.makeDark_p = QPushButton('Make DARK')
            #self.makeDark_p.clicked.connect(self.makeDark)
            #grid.addWidget(self.makeDark_p, w, 0)

            w = 0
            self.guiderCameraOn_l = QLabel("LOOP [s]:")
            self.guiderLoop_e = QLineEdit()
            self.guiderLoop_e.setText("5")
            self.guiderCameraOn_c = QCheckBox()
            self.guiderCameraOn_c.setChecked(False)
            self.guiderCameraOn_c.setLayoutDirection(Qt.RightToLeft)
            self.guiderCameraOn_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
            self.guiderCameraOn_c.clicked.connect(self.parent.GuiderPassiveOnOff)
            grid.addWidget(self.guiderCameraOn_l, w, 2)
            grid.addWidget(self.guiderLoop_e, w, 3)
            grid.addWidget(self.guiderCameraOn_c, w, 4)
            w = w + 1
            self.guiderExp_l = QLabel("EXP:")
            self.guiderExp_e = QLineEdit()
            self.guiderExp_e.setText("2")
            grid.addWidget(self.guiderExp_l, w, 2)
            grid.addWidget(self.guiderExp_e, w, 3,1,2)
            w = w + 1
            self.treshold_s = QSlider(Qt.Horizontal)
            self.treshold_s.setMinimum(1)
            self.treshold_s.setMaximum(50)
            self.treshold_s.setValue(10)
            grid.addWidget(self.treshold_s, w, 2, 1, 3)
            w = w + 1
            self.fwhm_s = QSlider(Qt.Horizontal)
            self.fwhm_s.setMinimum(1)
            self.fwhm_s.setMaximum(10)
            self.fwhm_s.setValue(4)
            grid.addWidget(self.fwhm_s, w, 2, 1, 3)
            w = w + 1
            self.line_l = QFrame()
            self.line_l.setFrameShape(QFrame.HLine)
            self.line_l.setFrameShadow(QFrame.Raised)
            grid.addWidget(self.line_l, w, 2, 1, 3)
            w = w + 1
            grid.addWidget(self.canvas2, w, 2, 2, 3)
            w = w + 3
            self.result_e = QTextEdit()
            self.result_e.setReadOnly(True)
            self.result_e.setStyleSheet("background-color: rgb(245,245,245);")
            grid.addWidget(self.result_e, w, 2,3,3)
            w = w + 3
            self.method_l = QLabel("Method:")
            self.method_s = QComboBox()
            self.method_s.addItems(["Auto", "Multistar", "Single star"])
            grid.addWidget(self.method_l, w, 2)
            grid.addWidget(self.method_s, w, 3,1,2)
            w = w + 1
            self.autoGuide_l = QLabel("AUTO GUIDE:")
            self.autoGuide_c = QCheckBox()
            self.autoGuide_c.setChecked(False)
            self.autoGuide_c.setLayoutDirection(Qt.RightToLeft)
            self.autoGuide_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
            grid.addWidget(self.autoGuide_l, w, 2)
            grid.addWidget(self.autoGuide_c, w, 3)

            grid.setColumnMinimumWidth(0, 120)
            grid.setColumnMinimumWidth(1, 120)
            #grid.setColumnMinimumWidth(2, 30)
            #grid.setColumnMinimumWidth(3, 30)
            grid.setRowMinimumHeight(5, 200)
            grid.setRowStretch(5, 1)
            self.setLayout(grid)

            self.axes.clear()
            self.canvas.draw()

            self.axes2.clear()
            self.canvas2.draw()


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


  # ######### Fits GUI #############

class FitsView(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.mkUI()
        self.colorbar = None
        self.image=[]

    def plot_image(self):
        self.axes.clear()
        self.axes.axis("off")
        if len(self.image)>0:

            vmin = numpy.mean(self.image) - 1 * numpy.std(self.image)
            vmax = numpy.mean(self.image) + 1 * numpy.std(self.image)

            im = self.axes.imshow(self.image, vmin=vmin, vmax=vmax)

            if len(self.sat_coo)>2 and self.show_c.checkState():
                x,y = zip(*self.sat_coo)
                self.axes.plot(x, y, color="red", marker="o", markersize="5", markerfacecolor="none",linestyle="")
            if len(self.ok_coo)>2 and self.show_c.checkState():
                x,y = zip(*self.ok_coo)
                self.axes.plot(x, y, color="white", marker="o", markersize="5", markerfacecolor="none",linestyle="")

            self.canvas.draw()
            self.show()

    def update(self, image,sat_coo,ok_coo):
        self.image = image
        self.sat_coo = sat_coo
        self.ok_coo = ok_coo
        self.plot_image()



    def mkUI(self):
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes.axis("off")

        # self.violin_axes = self.fig.add_axes([0.82,0.0,0.18,1])
        # self.violin_axes.tick_params(axis='y', which='both', labelleft=False, labelright=True, direction='in')

        grid = QGridLayout()

        self.show_c = QCheckBox("Mark saturated stars")
        self.show_c.setChecked(True)
        self.show_c.clicked.connect(self.plot_image)

        grid.addWidget(self.show_c,0,0)

        grid.addWidget(self.canvas,1,0)

        self.stat_e=QTextEdit()
        self.stat_e.setReadOnly(True)
        self.stat_e.setStyleSheet("background-color: rgb(235,235,235);")
        font=QtGui.QFont("Courier New",9)
        self.stat_e.setFont(font)

        grid.addWidget(self.stat_e,2,0)


        grid.setRowMinimumHeight(1,350)
        grid.setRowStretch(0,0)
        grid.setRowStretch(1,1)
        grid.setRowStretch(2,0)
        self.setLayout(grid)

        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw()
