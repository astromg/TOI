#!/usr/bin/env python3


from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit, QLabel, QSlider, QFrame, QComboBox

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS

class FlatWindow(QWidget):
    def __init__(self, parent):
        super(FlatWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Flat Log')
        self.setGeometry(self.parent.obs_window_geometry[0] + 2100, self.parent.obs_window_geometry[1]+500, 450, 500)
        self.mkUI()
        self.text = {k:"" for k in self.parent.local_cfg["toi"]["telescopes"]}

    def updateUI(self):
        if self.parent.telescope:
            self.tel_e.setText(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont("Courier New",9)
            font.setBold(True)
            self.tel_e.setFont(font)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")

            self.info_e.clear()
            self.info_e.append("date                     UT       filter    exp    h_sun     ADU")
            for r in self.parent.flat_log:
                txt = r["timestamp_utc"].split()[0] + "    " + r["timestamp_utc"].split()[1].split(".")[0]
                txt = txt + f'   {r["filter"]:12} {r["exp_time"]:.2f}      {r["h_sun"]}      {r["mean"]}'
                self.info_e.append(txt)
            self.info_e.moveCursor(QTextCursor.End)
            self.show()
            self.raise_()


    def mkUI(self):
        grid = QGridLayout()
        self.tel_e = QLineEdit()
        self.tel_e.setReadOnly(True)
        grid.addWidget(self.tel_e, 0, 0)
        self.info_e = QTextEdit()
        self.info_e.setReadOnly(True)
        self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.info_e, 1, 0)
        self.setLayout(grid)

