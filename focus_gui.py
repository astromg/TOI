#!/usr/bin/env python3


from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit, QLabel, QComboBox, QPushButton

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS


# ############### FOCUS ##########################

class FocusWindow(QWidget):
    def __init__(self, parent):
        super(FocusWindow, self).__init__()
        self.parent = parent
        self.setGeometry(self.parent.obs_window_geometry[0] + 1900, self.parent.obs_window_geometry[1], 500, 500)
        self.mkUI()
        self.setWindowTitle('Focus')
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
        self.axes.set_xlabel("focus encoder position")
        self.axes.set_ylabel("sharpness")
        #self.fig.tight_layout()
        self.canvas.draw()
        self.show()
        self.raise_()


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

