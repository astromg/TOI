#!/usr/bin/env python3


from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit, QLabel, QSlider, QFrame, QComboBox

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS

class GuiderWindow(QWidget):
    def __init__(self, parent):
        super(GuiderWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Guider')
        self.setGeometry(self.parent.obs_window_geometry[0] + 1900, self.parent.obs_window_geometry[1], 300, 300)

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



