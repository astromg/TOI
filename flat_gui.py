#!/usr/bin/env python3

import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import (QMainWindow, QApplication, QAbstractItemView, QWidget, QLabel, QCheckBox, QTextEdit,
                             QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout,
                             QVBoxLayout, QTableWidget, QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame,
                             QComboBox, QProgressBar, QHeaderView)


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
        self.setGeometry(self.parent.obs_window_geometry[0] + 1940, self.parent.obs_window_geometry[1]+810, 900, 500)
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

    def update_flat_overwatch(self,data):

        self.flat_table_t.clearContents()

        font = QtGui.QFont()
        font.setPointSize(10)

        t0 =  datetime.datetime.now(datetime.timezone.utc)

        for i,f in enumerate(data.keys()):
            if self.flat_table_t.rowCount() <= i: self.flat_table_t.insertRow(i)

            txt = f
            txt = QTableWidgetItem(txt)
            txt.setFont(font)
            #txt.setBackground(QtGui.QColor(233, 233, 233))
            self.flat_table_t.setItem(i, 0, txt)

            if data[f]["last_flats"]:
                t_filter = datetime.datetime.fromisoformat(data[f]["last_flats"])
                t_filter = t_filter.replace(tzinfo=datetime.timezone.utc)
                dt = t0 - t_filter
                days = dt.days
                hours = dt.seconds / 3600.
                if float(days) == 0:
                    txt = f'{float(hours):.0f} hours'
                else:
                    txt = f'{days} days'
            else:
                txt = "--"

            txt = QTableWidgetItem(txt)
            txt.setFont(font)
            #txt.setBackground(QtGui.QColor(233, 233, 233))
            self.flat_table_t.setItem(i, 1, txt)

            if data[f]["last_obs"]:
                t_obs = datetime.datetime.fromisoformat(data[f]["last_obs"])
                t_obs = t_obs.replace(tzinfo=datetime.timezone.utc)
                dt = t0 - t_obs
                days = dt.days
                hours = dt.seconds / 3600.
                if float(days) == 0:
                    txt = f'{float(hours):.0f} hours'
                else:
                    txt = f'{days} days'
            else:
                txt = "--"

            txt = QTableWidgetItem(txt)
            txt.setFont(font)
            #txt.setBackground(QtGui.QColor(233, 233, 233))
            self.flat_table_t.setItem(i, 2, txt)


        self.flat_table_t.scrollToBottom()
        self.flat_table_t.resizeColumnsToContents()
        for col in range(2,self.flat_table_t.columnCount()):
            self.flat_table_t.horizontalHeader().setSectionResizeMode(col,QHeaderView.Stretch)
        self.flat_table_t.repaint()



    def mkUI(self):
        grid = QGridLayout()
        self.flat_table_t = QTableWidget(0,3)
        self.flat_table_t.setHorizontalHeaderLabels(["FILTER", "LAST FLAT", "LAST OBJECT"])
        self.flat_table_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.flat_table_t.verticalHeader().hide()
        self.flat_table_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.flat_table_t.setStyleSheet("selection-background-color: white;")
        self.flat_table_t.verticalHeader().setDefaultSectionSize(10)
        grid.addWidget(self.flat_table_t, 1, 0)

        self.tel_e = QLineEdit()
        self.tel_e.setReadOnly(True)
        grid.addWidget(self.tel_e, 0, 0,1,2)
        self.info_e = QTextEdit()
        self.info_e.setReadOnly(True)
        self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.info_e, 1, 1)
        self.setLayout(grid)

