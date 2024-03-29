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

        self.focus_tab = FocusGui(self.parent)
        self.tabWidget.addTab(self.focus_tab, "Focus")

        # Sorry I'm commenting it out temporarly
        # Because weather is generating errors constantly
        # We took over your develomnet branch, but we can switch to mster
        # when you synchronize.... (mikolaj)

        self.guider_tab = GuiderGui(self.parent)
        self.tabWidget.addTab(self.guider_tab, "Guider")

        # self.flat_tab = FlatGui(self.parent)
        # self.tabWidget.addTab(self.flat_tab, "Flats")

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
        grid.addWidget(self.pic_l, w,0,2,1)

        self.wind_l = QLabel("Wind:")
        self.wind_e = QLineEdit()
        self.wind_e.setReadOnly(True)
        self.wind_e.setStyleSheet("background-color: rgb(235,235,235);")
        self.temp_l = QLabel("Temp:")
        self.temp_e = QLineEdit()
        self.temp_e.setReadOnly(True)
        self.temp_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.temp_l, w, 1)
        grid.addWidget(self.temp_e, w, 2)
        w = w + 1
        grid.addWidget(self.wind_l, w, 1)
        grid.addWidget(self.wind_e, w, 2)

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
        self.last_e.setText("15350")

        self.range_l = QLabel("STEPS No.:")
        self.range_e = QLineEdit()
        self.range_e.setText("8")

        grid.addWidget(self.last_l, w, 0)
        grid.addWidget(self.last_e, w, 1)
        grid.addWidget(self.range_l, w, 2)
        grid.addWidget(self.range_e, w, 3)

        w = w + 1
        self.steps_l = QLabel("Step:")
        self.steps_e = QLineEdit()
        self.steps_e.setText("50")

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

# ############### GUIDER ###################
class GuiderGui(QWidget):
    def __init__(self, parent):
        super(GuiderGui, self).__init__()
        self.parent = parent
        self.mkUI()
        self.show()

    def update(self, image,coo):
        self.image = image
        self.axes.clear()
        self.axes.axis("off")
        if len(self.image)>0:
            vmin = numpy.mean(self.image) - 1 * numpy.std(self.image)
            vmax = numpy.mean(self.image) + 1 * numpy.std(self.image)
            im = self.axes.imshow(self.image, vmin=vmin, vmax=vmax, cmap=matplotlib.colormaps["ocean"])
            if len(coo)>0:
                x,y = zip(*coo)
                self.axes.plot(x, y, color="white", marker="o", markersize="5", markerfacecolor="none",linestyle="")




            self.canvas.draw()
            self.show()

    def mkUI(self):
        if True:
            self.fig = Figure((1.0, 0.5), linewidth=-1, dpi=100)
            self.canvas = FigureCanvas(self.fig)
            self.axes = self.fig.add_axes([0, 0, 1, 1])
            self.axes.axis("off")

            grid = QGridLayout()

            #self.steps_l = QLabel("Step:")
            #self.steps_e = QLineEdit()
            #self.steps_e.setText("50")

            #self.method_s = QComboBox()
            #self.method_s.addItems(["RMS_QUAD", "RMS"])

            #self.autoFocus_p = QPushButton('FIND FOCUS')
            #self.autoFocus_p.clicked.connect(self.parent.auto_focus)

            w = 0
            grid.addWidget(self.canvas, w, 0,5,2)

            w = 0
            self.guiderCameraOn_l = QLabel("Camera On: ")
            self.guiderCameraOn_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            self.guiderCameraOn_c = QCheckBox()
            self.guiderCameraOn_c.setChecked(False)
            self.guiderCameraOn_c.setLayoutDirection(Qt.RightToLeft)
            self.guiderCameraOn_c.setStyleSheet(
                "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
            #self.guiderCameraOn_c.clicked.connect(self.parent.mount_motorsOnOff)
            grid.addWidget(self.guiderCameraOn_l, w, 2)
            grid.addWidget(self.guiderCameraOn_c, w, 4)

            w = w + 1
            self.guiderExp_l = QLabel("EXP:")
            self.guiderExp_e = QLineEdit()
            self.guiderExp_e.setText("2")
            grid.addWidget(self.guiderExp_l, w, 2)
            grid.addWidget(self.guiderExp_e, w, 4)

            w = w + 5
            self.autoGuide_p = QPushButton('Auto Guide')
            #self.autoGuide_p.clicked.connect(self.parent.auto_focus)
            grid.addWidget(self.autoGuide_p, w, 0)

            w = 1
            w = w + 1
            self.up_p = QPushButton('\u2191')
            grid.addWidget(self.up_p, w, 3)

            w = w + 1
            self.left_p = QPushButton('\u2190')
            self.right_p = QPushButton('\u2192')
            grid.addWidget(self.left_p, w, 2)
            grid.addWidget(self.right_p, w, 4)

            w = w + 1
            self.down_p = QPushButton('\u2193')
            grid.addWidget(self.down_p, w, 3)

            grid.setColumnMinimumWidth(0, 100)
            grid.setColumnMinimumWidth(1, 100)
            #grid.setColumnMinimumWidth(2, 30)
            #grid.setColumnMinimumWidth(3, 30)
            #grid.setColumnMinimumWidth(4, 30)
            #grid.setRowStretch(0, 0)
            #grid.setRowStretch(1, 1)
            #grid.setRowStretch(2, 0)
            self.setLayout(grid)

            self.axes.clear()
            self.canvas.draw()


class FlatGui(QWidget):
    def __init__(self, parent):
        super(FlatGui, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.setLayout(grid)


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
