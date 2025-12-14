#!/usr/bin/env python3


from PyQtX.QtCore import Qt
from PyQtX.QtGui import QFont, QTextCursor
from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit, QLabel, QSlider, QFrame, QComboBox

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS

class PlanrunnerWindow(QWidget):
    def __init__(self, parent):
        super(PlanrunnerWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Plan Runner')
        self.setGeometry(self.parent.obs_window_geometry[0] + 1900, self.parent.obs_window_geometry[1]+500, 400, 500)
        self.mkUI()
        self.text = {k:"" for k in self.parent.local_cfg["toi"]["telescopes"]}

    def updateUI(self):
        if self.parent.telescope:
            self.tel_e.setText(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setBold(True)
            self.tel_e.setFont(font)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")
            self.prog_call_e.setText(self.text[self.parent.active_tel])
            self.prog_call_e.moveCursor(QTextCursor.End)



    def mkUI(self):
        grid = QGridLayout()
        self.tel_e = QLineEdit()
        self.tel_e.setReadOnly(True)
        grid.addWidget(self.tel_e, 0, 0)
        self.prog_call_e = QTextEdit()
        self.prog_call_e.setReadOnly(True)
        self.prog_call_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.prog_call_e, 1, 0)
        self.setLayout(grid)

