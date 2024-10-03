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


class SkyGui(QWidget):
    def __init__(self, parent):
        super(SkyGui, self).__init__()
        self.parent = parent
        #self.setStyleSheet("font-size: 11pt;")
        self.setGeometry(self.parent.obs_window_geometry[0]+855,self.parent.obs_window_geometry[1],500,500)

        #self.updateUI()
        self.show()
        self.raise_()

    def updateUI(self):
        if self.parent.telescope:
            print("welcome")
        else:
            



        del tmp
