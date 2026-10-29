#!/usr/bin/env python3
from copy import deepcopy
import os
#----------------
# 01.08.2022
# Marek Gorski
#----------------

import uuid

import ephem
import datetime
import qasync as qs
from qasync import QEventLoop
from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import (QAbstractItemView, QWidget, QLabel, QCheckBox, QTextEdit,
                             QLineEdit, QPushButton, QGridLayout, QTableWidget, QTableWidgetItem, QCompleter, QFileDialog, QFrame,
                             QComboBox, QProgressBar, QHeaderView, QSpinBox)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from astropy.table import Table

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from pyaraucaria.coordinates import *
from base_window import BaseWindow

from toi_lib import *
from tpg.telescope_plan_generator import TelescopePlanGenerator as tpg
from tpg.config import load_config as tpg_load_config

from pyaraucaria.obs_plan.obs_plan_parser import ObsPlanParser
from pyaraucaria.ob_validator import ObsValidator


class PlanGui(BaseWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          BaseWindow.__init__(self)
          BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)

          self.parent=parent


          self.set_initial_geometry(
              self.parent.plan_geometry[0],
              self.parent.plan_geometry[1],
              self.parent.plan_geometry[2],
              self.parent.plan_geometry[3]
          )

          self.table_header = ["","UT","Object","Alt @ UT","Comment"]
          self.show_seq = False      # zmienne decydujaca o wyswietlaniu co jest w kolumnach w tabelce
          self.state_ut = 0
          self.show_ob = False

          self.plan=[]
          self.i=0                  # aktualne podswietlenie
          self.prev_i=-1             # poprzednie podswietlenie
          self.next_i=0             # zmienna funkcjonalna, nastepny obiekt do obserwacji
          self.current_i=-1         # zmienna funckjonalna, ktore ob wlasnie sie wykonuje.
          self.done=[]              # lista uobi wykonanych ob

          self.updateUI()
          self.update_table()
          self.show()
          self.raise_()

    def plot_plan(self):
         if len(self.plan)>self.i:
            self.plot_window=PlotWindow(self)
            self.plot_window.show()
            self.plot_window.raise_()
         else: print("no plan loaded") # ERROR MSG

    def plot_phase(self):
            self.phase_window=PhaseWindow(self)
            self.phase_window.show()
            self.phase_window.raise_()

    def run_tpg(self):
        if not self.parent.active_tel:
            return
        if self.parent.tel_acces[self.parent.active_tel]:
            self.tpg_window = TPGWindow(self)
            self.tpg_window._smart_sunset_checkbox()
        else:
            txt="WARNING: U don't have control"
            self.parent.WarningWindow(txt)

    def pocisniecie_copy(self):
        if self.parent.tel_acces[self.parent.active_tel]:
             if len(self.parent.plan[self.parent.active_tel])>self.i:
                 tmp_ob = deepcopy(self.parent.plan[self.parent.active_tel][self.i])
                 i = self.i + 1
                 self.parent.plan[self.parent.active_tel].insert(i,tmp_ob)
                 self.parent.plan[self.parent.active_tel][i]["ob"]["uobi"] = str(uuid.uuid4())[:8]
                 self.parent.update_plan(self.parent.active_tel)
                 #self.repaint()
             else: print("no plan loaded") # ERROR MSG
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_addOB(self):
        if self.parent.tel_acces[self.parent.active_tel]:
            self.add_window = AddWindow(self)
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)



    def pocisniecie_edit(self):
        if self.parent.tel_acces[self.parent.active_tel]:
            if len(self.plan) > self.i:
                self.edit_window = EditWindow(self)
            else:
                print("no plan loaded") # ERROR MSG
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)


    def pocisniecie_addStop(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if len(self.parent.plan[self.parent.active_tel])>self.i:
                 #print("ide ***************")
                 data = {}
                 ob = {"command_name": "STOP"}
                 data["ob"] = ob
                 data["block"] = "STOP"
                 data["meta"] = {"ok": True}
                 self.parent.plan[self.parent.active_tel].insert(self.i+1,data)
                 self.parent.update_plan(self.parent.active_tel)
            else: pass

        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_addBell(self):
        if self.parent.tel_acces[self.parent.active_tel]:
             if len(self.plan)>self.i:
                 data = {}
                 ob = {"command_name": "BELL"}
                 data["ob"] = ob
                 data["block"] = "BELL"
                 data["meta"] = {"ok": True}
                 self.parent.plan[self.parent.active_tel].insert(self.i+1,data)
                 self.parent.update_plan(self.parent.active_tel)
             else: pass

        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)



    def update_table(self):
        self.plan_t.clearContents()
        self.plan_t.setRowCount(0)

        if not self.parent.active_tel:
            self.plan_t.clearContents()
        else:

            if True:
            #try:
                if self.parent.tel_acces[self.parent.active_tel] and self.parent.telescope_switch_status["plan"]:
                    self.plan = self.parent.plan[self.parent.active_tel]
                    self.current_i = self.parent.current_i[self.parent.active_tel]
                    self.next_i = self.parent.next_i[self.parent.active_tel]

                    self.plan_t.setStyleSheet("")
                else:
                    self.plan = self.parent.nats_plan_status["plan"]
                    self.current_i = self.parent.nats_plan_status["current_i"]
                    self.next_i = self.parent.nats_plan_status["next_i"]

                    self.plan_t.setStyleSheet("background-color: #F0F0F0;")

                if not self.plan:
                    self.plan_t.clearContents()
                else:
                      if len(self.plan)==0:
                          self.plan_t.clearContents()
                      else:
                         if self.i > len(self.plan)-1:
                             self.i = len(self.plan)-1

                         if self.prev_i > len(self.plan)-1:
                             self.prev_i = len(self.plan)-1

                         self.plan_t.clearContents()
                         self.plan_t.blockSignals(True)


                         for i,tmp in enumerate(self.plan):
                             if self.plan_t.rowCount() <= i:
                                 self.plan_t.insertRow(i)

                                 # UWAGA - ponizsza metoda zostaje zachowana jako przyklad problemu.
                                 # Gdy sie tak robi, to kazdy kolejny widget po 1, najpierw wskakuje w
                                 # row,col: 0,0 i dopiero potem wskakuje na wlasciwe miesjce. Nie wiem jak to rozwiazac

                                 ##pic = QtGui.QPixmap("./Icons/stop.png").scaled(QtCore.QSize(25,25))
                                 #font=QtGui.QFont()
                                 #font.setPointSize(20)
                                 #icon=QLabel("\u2B23")     # no go
                                 #icon.setStyleSheet('color:red;')
                                 #icon.setFont(font)
                                 #icon.setPixmap(pic)
                                 #icon.setAlignment(QtCore.Qt.AlignCenter)
                                 #self.plan_t.setCellWidget(i,0,txt)

                             # IKONKI
                             if "command_name" in self.plan[i]["ob"].keys():    # wait
                                if self.plan[i]["ob"]["command_name"]=="WAIT":
                                   font=QtGui.QFont()
                                   font.setPointSize(15)
                                   txt=QTableWidgetItem("\u29D6")     # prosta klepsydra
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   txt.setForeground(QtGui.QColor("darkCyan"))
                                   self.plan_t.setItem(i,0,txt)

                             if "command_name" in self.plan[i]["ob"].keys():     # stop
                                if self.plan[i]["ob"]["command_name"]=="STOP":
                                   font=QtGui.QFont()
                                   font.setPointSize(20)
                                   txt=QTableWidgetItem("\u2B23")
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "command_name" in self.plan[i]["ob"].keys():     # stop
                                if self.plan[i]["ob"]["command_name"]=="BELL":
                                   font=QtGui.QFont()
                                   font.setPointSize(20)
                                   txt=QTableWidgetItem("\u266A")
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   #txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "plan_alt" in self.plan[i]["meta"].keys():
                                 alt = float(self.plan[i]["meta"]["plan_alt"])
                                 if alt < self.parent.cfg_alt_limits["low"] :
                                     font = QtGui.QFont()
                                     font.setPointSize(15)
                                     txt = QTableWidgetItem("\u26A0") # ostrzezenie
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("orange"))
                                     self.plan_t.setItem(i, 0, txt)

                             if "skip_alt" in self.plan[i]["meta"].keys():
                                 if self.plan[i]["meta"]["skip_alt"]:
                                     font = QtGui.QFont()
                                     font.setPointSize(15)
                                     txt = QTableWidgetItem("\u26A0")
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("red"))
                                     self.plan_t.setItem(i, 0, txt)

                             if "ok" in self.plan[i]["meta"].keys():
                                 if not self.plan[i]["meta"]["ok"]:
                                     font = QtGui.QFont()
                                     font.setPointSize(15)
                                     txt = QTableWidgetItem("\u2699")  # kolo zembate
                                     #txt = QTableWidgetItem("\u2328")   # klawiatura
                                     #txt = QTableWidgetItem("\u2301")  # blyskawica
                                     #txt = QTableWidgetItem("\u2692")       # mlotek i cos tam
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("red"))
                                     self.plan_t.setItem(i, 0, txt)
                             else:
                                 font = QtGui.QFont()
                                 font.setPointSize(15)
                                 txt = QTableWidgetItem("\u2699")  # kolo zembate
                                 # txt = QTableWidgetItem("\u2328")   # klawiatura
                                 # txt = QTableWidgetItem("\u2301")  # blyskawica
                                 # txt = QTableWidgetItem("\u2692")       # mlotek i cos tam
                                 txt.setFont(font)
                                 txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                 txt.setForeground(QtGui.QColor("red"))
                                 self.plan_t.setItem(i, 0, txt)



                             if "skip" in self.plan[i]["meta"].keys():
                                if self.plan[i]["meta"]["skip"]:
                                   font=QtGui.QFont()
                                   font.setPointSize(15)
                                   #txt=QTableWidgetItem("\u26D4")  # zakaz wjazdu
                                   txt = QTableWidgetItem("\u23ED")  # nastepna piosenka
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   #txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "uobi" in self.plan[i]["ob"].keys():
                                 if self.plan[i]["ob"]["uobi"] in self.done:
                                     font=QtGui.QFont()
                                     font.setPointSize(15)
                                     txt=QTableWidgetItem("\u2713")
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("green"))
                                     self.plan_t.setItem(i,0,txt)

                             if i==self.next_i: #and self.current_i<0:    # nastepmy
                                font=QtGui.QFont()
                                font.setPointSize(25)
                                txt=QTableWidgetItem("\u2192")  # szczalka next
                                txt.setFont(font)
                                txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                txt.setForeground(QtGui.QColor("blue"))
                                self.plan_t.setItem(i,0,txt)

                             if i==self.current_i:          # aktualnie robiony
                                font=QtGui.QFont()
                                font.setPointSize(20)
                                txt=QTableWidgetItem("\u21BB")
                                txt.setFont(font)
                                txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                txt.setForeground(QtGui.QColor("green"))
                                self.plan_t.setItem(i,0,txt)

                             # 1 KOLUMNA
                             txt = ""
                             if "plan_ut" in self.plan[i]["meta"].keys() and (
                                     i >= self.next_i or (i >= self.current_i and self.current_i > -1)):
                                 tmp = parse_plan_ut_str(str(self.plan[i]["meta"]["plan_ut"])).split()[1]
                                 txt = tmp.split(":")[0] + ":" + tmp.split(":")[1]

                             txt=QTableWidgetItem(txt)
                             self.plan_t.setItem(i,1,txt)


                             # 2 kolumna
                             if self.show_ob:
                                 txt=self.plan[i]["block"]
                             else:
                                 if "command_name" in self.plan[i]["ob"].keys():
                                     if self.plan[i]["ob"]["command_name"] == "FOCUS":
                                         txt = "FOCUS "+ self.plan[i]["ob"]["name"]
                                     elif self.plan[i]["ob"]["command_name"] == "SKYFLAT":
                                         txt = "SKYFLAT "+ self.plan[i]["ob"]["name"]
                                     elif self.plan[i]["ob"]["command_name"] == "WAIT":
                                         txt = f'{self.plan[i]["block"].split()[1]} '
                                     else:
                                         if "name" in self.plan[i]["ob"]:
                                            txt = self.plan[i]["ob"]["name"]
                                         else:
                                             txt = f'{self.plan[i]["block"].split()[0]} '

                                 else:
                                     if "name" in self.plan[i]["ob"]:
                                         txt = self.plan[i]["ob"]["name"]
                                     else:
                                         txt = f'{self.plan[i]["block"].split()[0]} '


                             txt=QTableWidgetItem(txt)
                             self.plan_t.setItem(i,2,txt)

                             # 3 KOLUMNA


                             txt = ""
                             if self.state_ut == 0:
                                 if "plan_alt" in self.plan[i]["meta"].keys() and (i >= self.next_i or (i >= self.current_i and self.current_i>-1)):
                                     txt =  f'{self.plan[i]["meta"]["plan_alt"]}'
                                     alt = float(self.plan[i]["meta"]["plan_alt"])
                                     txt = QTableWidgetItem(txt)
                                     if alt < self.parent.cfg_alt_limits["min"]:
                                         txt.setForeground(QtGui.QColor("red"))
                                     elif alt < self.parent.cfg_alt_limits["low"]:
                                         txt.setForeground(QtGui.QColor("orange"))
                                     elif alt > self.parent.cfg_alt_limits["max"]:
                                         txt.setForeground(QtGui.QColor("red"))
                             elif self.state_ut == 1:
                                 if "alt" in self.plan[i]["meta"].keys():
                                     txt = str(self.plan[i]["meta"]["alt"])
                                     txt=QTableWidgetItem(txt)
                             elif self.state_ut == 2:
                                 if "slotTime" in self.plan[i]["meta"].keys():
                                     txt = f' {self.plan[i]["meta"]["slotTime"] / 60.:.1f} [m]'
                                     txt=QTableWidgetItem(txt)
                             elif self.state_ut == 3:

                                 if "ra" in self.plan[i]["ob"].keys() and "plan_ut" in self.plan[i]["meta"].keys():
                                     ra = self.plan[i]["ob"]["ra"]
                                     dec = self.plan[i]["ob"]["dec"]
                                     obs = ephem.Observer()
                                     obs.lat = self.parent.oca_site.lat
                                     obs.lon = self.parent.oca_site.lon
                                     obs.elevation = self.parent.oca_site.elevation
                                     obs.date = parse_plan_ut_str(str(self.plan[i]["meta"]["plan_ut"]))

                                     target = ephem.FixedBody()
                                     target._ra = ephem.hours(ra)
                                     target._dec = ephem.degrees(dec)
                                     target.compute(obs)

                                     moon = ephem.Moon(obs)

                                     sep = ephem.separation((target.ra, target.dec), (moon.ra, moon.dec))
                                     sep_deg = float(sep) * 180.0 / ephem.pi
                                     txt = f'{sep_deg:.0f} [deg]'

                             txt = QTableWidgetItem(txt)
                             self.plan_t.setItem(i,3,txt)

                             # 4 KOLUMNA

                             txt=QTableWidgetItem("--")
                             if self.show_seq:
                                 if "seq" in self.plan[i]["ob"].keys():
                                     txt = QTableWidgetItem(str(self.plan[i]["ob"]["seq"]))
                             else:
                                 if "comment" in self.plan[i]["ob"].keys():
                                     txt = QTableWidgetItem(str(self.plan[i]["ob"]["comment"]))

                             self.plan_t.setItem(i,4,txt)

                         if self.prev_i >= 0 and self.prev_i < len(self.plan):
                             self.plan_t.item(self.prev_i,1).setBackground(QtGui.QColor(230, 236, 240))
                             self.plan_t.item(self.prev_i,2).setBackground(QtGui.QColor(230, 236, 240))
                             self.plan_t.item(self.prev_i, 3).setBackground(QtGui.QColor(230, 236, 240))
                             self.plan_t.item(self.prev_i, 4).setBackground(QtGui.QColor(230, 236, 240))

                         if self.i >= 0 and self.i < len(self.plan):
                             self.plan_t.item(self.i,1).setBackground(QtGui.QColor(125, 195, 227))
                             self.plan_t.item(self.i,2).setBackground(QtGui.QColor(125, 195, 227))
                             self.plan_t.item(self.i, 3).setBackground(QtGui.QColor(125, 195, 227))
                             self.plan_t.item(self.i, 4).setBackground(QtGui.QColor(125, 195, 227))

                      #self.plan_t.setColumnWidth(0,30)

                      self.plan_t.resizeColumnsToContents()
                      self.plan_t.horizontalHeader().setStretchLastSection(True)
                      if self.parent.skyGui.skyView:
                          self.parent.skyGui.skyView.updateRadar()

                      if not self.show_ob:
                          self.plan_t.blockSignals(False)
                          self.plan_t.resizeColumnsToContents()


                      self.plan_t.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
                      self.plan_t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)


            # except Exception as e:
            #     print(f"TOI plan GUI: EXCEPTION 103 {e}")

        self.parent.telescope_switch_status["plan"] = True


    def update_log_window(self,log):
        ut = log["time"]
        user = log["user"]
        label = log["label"]
        level = log["level"]
        txt = log["txt"]

        c = QtCore.Qt.gray
        if float(level) > 10:
            if user == self.parent.myself:
                if label == "OPERATOR":
                    c = QtCore.Qt.blue
                if label == "TOI RESPONDER":
                    c = QtCore.Qt.darkGreen
                if label == "TOI":
                    c = QtCore.Qt.black
                if label == "WARNING":
                    c = QtCore.Qt.darkYellow
                if label == "ERROR":
                    c = QtCore.Qt.darkRed
                if label == "PLANRUNNER":
                    c = QtCore.Qt.darkGray
                if label == "OFP":
                    c = QtCore.Qt.darkGray
                if label == "DOWNLOADER":
                    c = QtCore.Qt.darkGray
                if label == "GUIDER":
                    c = QtCore.Qt.darkGray

            msg = f'{ut} [{label}] {txt}'
            self.info_e.setTextColor(c)
            self.info_e.append(msg)
            self.info_e.repaint()

    def update_log_table(self):
          if len(self.parent.ob_log)==0:
              self.log_t.clearContents()
          else:
             # {'object_name': 'CR_Ser', 'uobi': 0, 'telescope': 'zb08', 'status': 'done', 'command_dict': {'command_name': 'OBJECT', 'args': ['CR_Ser', '18:10:02.13', '-13:32:45.5'], 'kwargs': {'seq': '2/B/12,2/V/3,2/Ic/1.8,2/g/7,2/r/1.5,2/i/1.4,2/z/5'}}, 'time': {'start_dt': '2024-09-20T01:11:08', 'end_dt': '2024-09-20T01:15:12', 'start_jd': 2460573.5494035487, 'end_jd': 2460573.5522267423, 'length_s': 243.923917}}
             self.log_t.clearContents()

             font = QtGui.QFont()
             font.setPointSize(10)

             for i,tmp in enumerate(self.parent.ob_log):
                 if self.log_t.rowCount() <= i: self.log_t.insertRow(i)
                 if True:
                     try:
                        txt = self.parent.ob_log[i]["time"]["end_dt"]
                        txt = txt.split("T")[1].split(":")[0]+":"+txt.split("T")[1].split(":")[1]
                        txt=QTableWidgetItem(txt)
                        txt.setBackground(QtGui.QColor(233, 233, 233))
                        txt.setFont(font)

                        self.log_t.setItem(i,0,txt)
                     except Exception as e:
                         print("update_log_table col 0 Exception: ",e,self.parent.ob_log[i])
                 if True:
                     try:
                         if "command_name" in self.parent.ob_log[i]["command_dict"].keys():
                             type = self.parent.ob_log[i]["command_dict"]["command_name"]
                             if type != "OBJECT":
                                txt = type + " " + self.parent.ob_log[i]["object_name"]
                             else:
                                txt = self.parent.ob_log[i]["object_name"]
                         else:
                             txt = ""

                         txt=QTableWidgetItem(txt)
                         txt.setBackground(QtGui.QColor(233, 233, 233))
                         txt.setFont(font)
                         self.log_t.setItem(i,1,txt)

                     except Exception as e:
                         print("update_log_table col 1 Exception: ", e, self.parent.ob_log[i])

                 if True:
                     try:
                         txt = ""
                         if "kwargs" in self.parent.ob_log[i]["command_dict"].keys():
                             if "seq" in self.parent.ob_log[i]["command_dict"]["kwargs"].keys():
                                 txt = str(self.parent.ob_log[i]["command_dict"]["kwargs"]["seq"])
                         txt=QTableWidgetItem(txt)
                         txt.setBackground(QtGui.QColor(233, 233, 233))
                         txt.setFont(font)
                         self.log_t.setItem(i,2,txt)
                     except Exception as e:
                         print("update_log_table col 2 Exception: ", e, self.parent.ob_log[i])

             self.log_t.scrollToBottom()
             self.log_t.resizeColumnsToContents()
             for col in range(2,self.log_t.columnCount()):
                 self.log_t.horizontalHeader().setSectionResizeMode(col,QHeaderView.Stretch)




    def setNext(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            #self.next_i = self.i
            self.parent.next_i[self.parent.active_tel] = self.i
            self.parent.update_plan(self.parent.active_tel)

        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)


    def import_to_manuall(self):                  # uzupelnia nazwe i wspolrzedne w oknie manual
        if self.parent.tel_acces[self.parent.active_tel]:
          try:
              if self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "OBJECT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
              elif self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "ZERO": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(1)
              elif self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "DARK": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(2)
              elif self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "SKYFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(3)
              elif self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "DOMEFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(4)

              if "command_name" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys():
                  if self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] in ["OBJECT","DARK","ZERO","SKYFLAT","DOMEFLAT"]:
                      if "ra" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys() and "dec" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys():
                          self.parent.mntGui.setEq_r.setChecked(True)
                          self.parent.mntGui.nextRa_e.setText(self.plan[self.i]["ob"]["ra"])
                          self.parent.mntGui.nextDec_e.setText(self.plan[self.i]["ob"]["dec"])
                          self.parent.mntGui.updateNextRaDec()
                          if "name" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys():
                              self.parent.mntGui.target_e.setText(self.plan[self.i]["ob"]["name"])
                              self.parent.mntGui.target_e.setStyleSheet("background-color: white; color: black;")
                      if "name" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys():
                          self.parent.instGui.ccd_tab.inst_object_e.setText(self.plan[self.i]["ob"]["name"])
                      if "seq" in self.parent.plan[self.parent.active_tel][self.i]["ob"].keys():
                          self.parent.instGui.ccd_tab.Select2_r.setChecked(True)
                          self.parent.instGui.ccd_tab.inst_Seq_e.setText(self.plan[self.i]["ob"]["seq"])
                      if self.parent.plan[self.parent.active_tel][self.i]["ob"]["command_name"] == "OBJECT":
                          self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
          except Exception as e:
              print(f"PLAN GUI EXCEPTION 34: {e}")
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def setSkip(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if "skip" in self.parent.plan[self.parent.active_tel][self.i].keys():
                if self.parent.plan[self.parent.active_tel][self.i]["meta"]["skip"]:
                    self.parent.plan[self.parent.active_tel][self.i]["meta"]["skip"] = False
                else:
                    self.parent.plan[self.parent.active_tel][self.i]["meta"]["skip"] = True
            else:
                self.parent.plan[self.parent.active_tel][self.i]["meta"]["skip"] = True
            self.parent.update_plan(self.parent.active_tel)

        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)




    def pocisniecie_headera(self,index):
        if index == 4:
            if self.show_seq:
                self.table_header[4] = "Comment"
                self.show_seq = False
            else:
                self.table_header[4] = "Seq"
                self.show_seq = True

        elif index == 3:
            options = ["Alt@UT", "Alt", "OB time", "Moon dist"]
            self.state_ut = (self.state_ut + 1) % len(options)
            self.table_header[3] = options[self.state_ut]

        elif index == 2:
            if self.show_ob:
                self.table_header[2] = "Object"
                self.show_ob = False
            else:
                self.table_header[2] = "OB"
                self.show_ob = True

        self.table_header[1] = "UT"

        self.plan_t.setHorizontalHeaderLabels(self.table_header)
        self.update_table()

    def pocisniecie_tabelki(self,i,j):
        self.prev_i=self.i
        self.i=i
        self.update_table()
        self.repaint()

    def pocisniecie_delAll(self):
        try:
            if self.parent.tel_acces[self.parent.active_tel]:
                if self.parent.current_i[self.parent.active_tel] >= 0:
                    ob_tmp = self.parent.plan[self.parent.active_tel][self.parent.current_i[self.parent.active_tel]]
                    self.parent.plan[self.parent.active_tel] = []
                    self.parent.plan[self.parent.active_tel].append(ob_tmp)
                else:
                    self.parent.plan[self.parent.active_tel] = []
                self.i = -1
                self.prev_i = -1
                self.parent.update_plan(self.parent.active_tel)
            else:
                txt = "WARNING: U don't have controll"
                self.parent.WarningWindow(txt)

        except Exception as e:
            print(f'TOI PLAN_GUI: EXCEPTION 102: {e}')


    def pocisniecie_del(self):
        if self.parent.tel_acces[self.parent.active_tel]:
              if self.i != self.parent.current_i[self.parent.active_tel] and self.i < len(self.parent.plan[self.parent.active_tel]):
                  if self.i < self.parent.current_i[self.parent.active_tel]: self.parent.current_i[self.parent.active_tel] = self.parent.current_i[self.parent.active_tel] - 1
                  if self.i < self.parent.next_i[self.parent.active_tel]: self.parent.next_i[self.parent.active_tel] = self.parent.next_i[self.parent.active_tel] - 1
                  if self.i == len(self.parent.plan[self.parent.active_tel])-1:
                      self.parent.plan[self.parent.active_tel].pop(self.i)
                      self.i = self.i - 1
                  else:
                      self.parent.plan[self.parent.active_tel].pop(self.i)
                  self.parent.update_plan(self.parent.active_tel)

        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_first(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if self.i != self.parent.current_i[self.parent.active_tel]:
              self.parent.plan[self.parent.active_tel].insert(0,self.parent.plan[self.parent.active_tel][self.i])
              self.parent.plan[self.parent.active_tel].pop(self.i+1)
              if self.i > self.parent.current_i[self.parent.active_tel] and self.parent.current_i[self.parent.active_tel]>-1:
                  self.parent.current_i[self.parent.active_tel] = self.parent.current_i[self.parent.active_tel] + 1
                  self.parent.next_i[self.parent.active_tel] = self.parent.next_i[self.parent.active_tel] + 1
                  self.parent.check_next_i(self.parent.active_tel)
              self.i=self.i+1
              if self.i+1>len(self.parent.plan[self.parent.active_tel]): self.i=self.i-1
              self.parent.update_plan(self.parent.active_tel)
              #self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              #self.repaint()

        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)


    def pocisniecie_last(self):
        if self.parent.tel_acces[self.parent.active_tel]:
          if self.i != self.parent.current_i[self.parent.active_tel]:
              self.parent.plan[self.parent.active_tel].append(self.parent.plan[self.parent.active_tel][self.i])
              self.parent.plan[self.parent.active_tel].pop(self.i)
              if self.i < self.parent.current_i[self.parent.active_tel] and self.parent.current_i[self.parent.active_tel]>-1:
                  self.parent.current_i[self.parent.active_tel] = self.parent.current_i[self.parent.active_tel] - 1
                  self.parent.next_i[self.parent.active_tel] = self.parent.next_i[self.parent.active_tel] - 1
                  self.parent.check_next_i(self.parent.active_tel)
              self.parent.update_plan(self.parent.active_tel)
              #self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              #self.repaint()
        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_up(self):
        if self.parent.tel_acces[self.parent.active_tel]:
          if self.i != self.parent.current_i[self.parent.active_tel]:
              if self.i - 1 == self.parent.current_i[self.parent.active_tel]:
                  self.parent.current_i[self.parent.active_tel] = self.parent.current_i[self.parent.active_tel] + 1
                  self.parent.next_i[self.parent.active_tel] = self.parent.next_i[self.parent.active_tel] + 1
              if self.i==0:
                  self.parent.plan[self.parent.active_tel].append(self.parent.plan[self.parent.active_tel][0])
                  self.parent.plan[self.parent.active_tel].pop(0)
                  self.i=len(self.parent.plan[self.parent.active_tel])-1
              else:
                  self.parent.plan[self.parent.active_tel][self.i],self.parent.plan[self.parent.active_tel][self.i-1]=self.parent.plan[self.parent.active_tel][self.i-1],self.parent.plan[self.parent.active_tel][self.i]
                  self.i=self.i-1
              self.parent.update_plan(self.parent.active_tel)
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              #self.repaint()
        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)


    def pocisniecie_down(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if self.i != self.parent.current_i[self.parent.active_tel]:
              if self.i + 1 == self.parent.current_i[self.parent.active_tel]:
                  self.parent.current_i[self.parent.active_tel] = self.parent.current_i[self.parent.active_tel] -1
                  self.parent.next_i[self.parent.active_tel] = self.parent.next_i[self.parent.active_tel] - 1
              if self.i==len(self.parent.plan[self.parent.active_tel])-1:
                  self.parent.plan[self.parent.active_tel].insert(0,self.parent.plan[self.parent.active_tel][self.i])
                  self.parent.plan[self.parent.active_tel].pop(len(self.parent.plan[self.parent.active_tel])-1)
                  self.i=0
              else:
                  self.parent.plan[self.parent.active_tel][self.i],self.parent.plan[self.parent.active_tel][self.i+1]=self.parent.plan[self.parent.active_tel][self.i+1],self.parent.plan[self.parent.active_tel][self.i]
                  self.i=self.i+1
              self.parent.update_plan(self.parent.active_tel)
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              #self.repaint()

        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_swap(self):
        if self.parent.tel_acces[self.parent.active_tel]:
          if self.i != self.parent.current_i[self.parent.active_tel] and self.prev_i != self.parent.current_i[self.parent.active_tel]:
              self.parent.plan[self.parent.active_tel][self.i],self.parent.plan[self.parent.active_tel][self.prev_i]=self.parent.plan[self.parent.active_tel][self.prev_i],self.parent.plan[self.parent.active_tel][self.i]
              self.parent.update_plan(self.parent.active_tel)
              self.i,self.prev_i=self.prev_i,self.i
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              #self.repaint()
        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def savePlan(self):
          self.File_dialog = QFileDialog()
          self.fileName = self.File_dialog.getSaveFileName(None,"Open file")[0]
          txt = ""
          for data in self.plan:
              block = data["block"]
              if "\n" not in block:
                  block = block + "\n"
              txt = txt + block
          if self.fileName:
              try:
                  with open(self.fileName, "w") as plik:
                      plik.write(txt)
              except OSError as e:
                  self.parent.WarningWindow(f"WARNING: can't save plan to {self.fileName}: {e}")


    def loadPlan(self):
        if self.parent.active_tel == None:
            txt = "WARNING: Telescope NOT selected!"
            self.parent.WarningWindow(txt)
            return 0


        if self.parent.tel_acces[self.parent.active_tel]:
            # ob["name","block","type","ra","dec","seq","pos","comment","ok"]
            # ob["wait","wait_ut","wait_sunset","wait_sunrise"]
            # [meta_alt,meta_az,meta_plan_ut,meta_plan_alt,meta_plan_az,skip,skip_alt]

            if self.parent.active_tel == None:
                self.parent.WarningWindow("WARNING: Ok, but first select the telescope!")
                return
            self.File_dialog = QFileDialog()
            self.fileName = self.File_dialog.getOpenFileName(None,"Open file")[0]

            if self.fileName:
                try:
                    with open(self.fileName, "r") as plik:
                        lines = plik.readlines()
                except (OSError, UnicodeDecodeError) as e:
                    self.parent.WarningWindow(f"WARNING: can't read plan file {self.fileName}: {e}")
                    return
                tmp_plan = []
                for line in lines:
                    data = None
                    if len(line.strip())>0:
                        if line.strip()[0]!="#":
                            if "TEL: zb08" in line:
                               pass  # wprowadzic do planow jako obowiazek?

                            BASE_SCHEMA = ObsValidator.load_schema("base_schema")
                            COMMAND_RULES = ObsValidator.load_schema("base_rules.yaml")

                            validator = ObsValidator(BASE_SCHEMA, COMMAND_RULES)
                            result = validator.validate_txt(line,allowed_filters=self.parent.nats_cfg[self.parent.active_tel]["filter_list_names"])
                            if result["valid"]:
                                data = {}
                                data["ob"] = result["data"]
                                data["meta"] = {"ok":True}
                                data["block"] = line

                                # slotTime liczy update_plan (jedna instancja CTC, aktualny tryb odczytu)

                            else:
                                print(f'Error plan reading: \n {line}')

                    if data:
                        tmp_plan.append(data)


                tel = self.parent.active_tel
                pos = min(self.i + 1, len(self.plan))
                self.plan[pos:pos] = tmp_plan
                # wczytane OB nad wykonywanym przesuwaja current_i; wstawione na miejscu next_i staja sie nastepnymi
                n = len(tmp_plan)
                if -1 < self.parent.current_i[tel] and pos <= self.parent.current_i[tel]:
                    self.parent.current_i[tel] += n
                if -1 < self.next_i and pos < self.next_i:
                    self.next_i += n
                self.parent.upload_plan()
                self.parent.update_plan(self.parent.active_tel)
            self.parent.upload_plan()
            self.update_table()
        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def plan_start(self):
        if self.parent.tel_acces[self.parent.active_tel]:
            self.parent.manual_plan_start(self.parent.active_tel)
        else:
              txt = "WARNING: U don't have controll"
              self.parent.WarningWindow(txt)
        # =================== OKNO GLOWNE ====================================
    def updateUI(self):

          txt = " Plan Manager"
          if self.parent.active_tel != None:
              txt = self.parent.active_tel + txt
          self.setWindowTitle(txt)

          tmp=QWidget()
          try: tmp.setLayout(self.grid)
          except: pass
          self.grid = QGridLayout()

          w=0
          self.info_e = QTextEdit()
          self.info_e.setReadOnly(True)
          self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
          self.grid.addWidget(self.info_e, w, 0, 3, 5)
          w = w + 3
          self.log_t=QTableWidget(0,3)
          self.log_t.setHorizontalHeaderLabels(["UT","Object","seq"])
          self.log_t.setSelectionMode(QAbstractItemView.NoSelection)
          self.log_t.verticalHeader().hide()
          self.log_t.setEditTriggers(QTableWidget.NoEditTriggers)
          self.log_t.setStyleSheet("selection-background-color: white;")
          self.log_t.verticalHeader().setDefaultSectionSize(10)

          self.grid.addWidget(self.log_t, w,0,4,5)
          w=w+4

          self.stop_p=QPushButton('Stop')
          self.resume_p=QPushButton('Resume')
          self.start_p=QPushButton('Start')
          self.grid.addWidget(self.stop_p, w,0)
          self.grid.addWidget(self.resume_p, w,2)
          self.grid.addWidget(self.start_p, w,4)

          w=w+1
          self.ob_l=QLabel("current OB:")
          self.ob_e=QLineEdit("")
          self.ob_e.setReadOnly(True)
          self.ob_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.grid.addWidget(self.ob_l, w,0)
          self.grid.addWidget(self.ob_e, w,1,1,4)

          w=w+1
          self.ob_Prog_n=QProgressBar(self)
          self.ob_Prog_n.setStyleSheet("background-color: rgb(233, 233, 233)")
          self.grid.addWidget(self.ob_Prog_n, w, 0,1,5)

          w=w+1
          self.plan_t=QTableWidget(0,5)
          self.plan_t.setStyleSheet("selection-background-color: green; background-color: #F0F0F0;")
          self.plan_t.setHorizontalHeaderLabels(self.table_header)
          self.plan_t.setSelectionMode(QAbstractItemView.NoSelection)
          self.plan_t.verticalHeader().hide()
          self.plan_t.verticalHeader().setDefaultSectionSize(15)


          self.grid.addWidget(self.plan_t, w,0,7,5)
          
          w=w+7
          self.import_p = QPushButton('\u2B05 Import to MANUAL')
          self.plotPlan_p = QPushButton('Plot Plan')
          self.plotPhase_p = QPushButton('Plot Phase')
          self.grid.addWidget(self.import_p, w, 0,1,2)
          self.grid.addWidget(self.plotPhase_p, w, 3, 1, 1)
          self.grid.addWidget(self.plotPlan_p, w, 4, 1, 1)

          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)



          w=w+1
          self.next_p=QPushButton('NEXT \u2192')
          self.addStop_p=QPushButton("STOP \u2B23")
          self.addBell_p = QPushButton('BELL \u266A')
          self.skip_p=QPushButton('SKIP \u23ED')

          self.grid.addWidget(self.next_p, w, 0)
          self.grid.addWidget(self.addStop_p, w, 2)
          self.grid.addWidget(self.addBell_p, w, 3)
          self.grid.addWidget(self.skip_p, w, 4)

          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)

          w=w+1

          self.add_p=QPushButton('Add OB')
          self.edit_p=QPushButton('Edit OB')
          self.copy_p=QPushButton('Copy OB')


          self.grid.addWidget(self.copy_p, w, 2)
          self.grid.addWidget(self.edit_p, w, 3)
          self.grid.addWidget(self.add_p, w,4)


          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)

          w=w+1
          self.del_p=QPushButton('Del') 
          self.up_p=QPushButton('Up')          
          self.swap_p=QPushButton('Swap')
          self.first_p=QPushButton('First')

          self.grid.addWidget(self.del_p, w,0)
          self.grid.addWidget(self.up_p, w,2)
          self.grid.addWidget(self.swap_p, w,3)
          self.grid.addWidget(self.first_p, w,4)
              
          
          w=w+1
          self.delAll_p=QPushButton('Del All') 
          self.down_p=QPushButton('Down')
          self.last_p=QPushButton('Last')

          self.grid.addWidget(self.delAll_p, w,0)
          self.grid.addWidget(self.down_p, w,2)
          self.grid.addWidget(self.last_p, w,4)

          w=w+1
          # self.prog_call_e=QTextEdit()
          # self.prog_call_e.setReadOnly(True)
          # self.prog_call_e.setStyleSheet("background-color: rgb(235,235,235);")
          # self.grid.addWidget(self.prog_call_e,w,0,3,5)
          #
          # w=w+3
          self.load_p = QPushButton('Load Plan')
          self.tpg_p = QPushButton('TPG')
          self.save_p = QPushButton('Save Plan')

          self.grid.addWidget(self.load_p, w,0,1,2)
          self.grid.addWidget(self.tpg_p, w, 2, 1, 1)
          self.grid.addWidget(self.save_p, w,3,1,2)



          self.stop_p.clicked.connect(self.parent.stop_program)
          self.resume_p.clicked.connect(self.parent.resume_program)
          self.start_p.clicked.connect(self.plan_start)

          self.load_p.clicked.connect(self.loadPlan)
          self.tpg_p.clicked.connect(self.run_tpg)
          self.save_p.clicked.connect(self.savePlan)
          self.plan_t.cellClicked.connect(self.pocisniecie_tabelki)
          self.plan_t.horizontalHeader().sectionClicked.connect(self.pocisniecie_headera)

          self.import_p.clicked.connect(self.import_to_manuall)
          self.plotPlan_p.clicked.connect(self.plot_plan)
          self.plotPhase_p.clicked.connect(self.plot_phase)
          self.next_p.clicked.connect(self.setNext)
          self.skip_p.clicked.connect(self.setSkip)
          self.up_p.clicked.connect(self.pocisniecie_up)
          self.down_p.clicked.connect(self.pocisniecie_down)
          self.del_p.clicked.connect(self.pocisniecie_del)
          self.delAll_p.clicked.connect(self.pocisniecie_delAll)
          self.first_p.clicked.connect(self.pocisniecie_first)
          self.last_p.clicked.connect(self.pocisniecie_last)
          self.swap_p.clicked.connect(self.pocisniecie_swap)
          self.edit_p.clicked.connect(self.pocisniecie_edit)
          self.copy_p.clicked.connect(self.pocisniecie_copy)
          self.add_p.clicked.connect(self.pocisniecie_addOB)
          self.addStop_p.clicked.connect(self.pocisniecie_addStop)
          self.addBell_p.clicked.connect(self.pocisniecie_addBell)

          self.setLayout(self.grid)
          self.plan_t.setColumnWidth(0,30)
          self.plan_t.setColumnWidth(1, 40)
          self.plan_t.setColumnWidth(3, 40)

          del tmp
          
    async def on_start_app(self):
          await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
          await self.stop_background_tasks()
          await self.stop_background_methods()
          super().closeEvent(event)


# #############################################
# ######### OKNO TPG  ##########
# #############################################

class TPG_Worker(QtCore.QObject):
    done_signal = QtCore.pyqtSignal()
    plan_ready_signal = QtCore.pyqtSignal(object)
    update_signal = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, tel, dt, wind=None, uobi_done=None,fwhm=None, tag=None, night_monitor=False,
                 night_monitor_gap=None, skyflats=(), flat_history=None, now=None):

        super().__init__()
        self.tel = tel
        self.dt = dt
        self.wind = wind
        self.uobi_done = uobi_done or []
        self.fwhm = fwhm
        self.tag = tag
        self.night_monitor = night_monitor
        self.night_monitor_gap = night_monitor_gap
        self.skyflats = skyflats
        self.flat_history = flat_history
        self.now = now

    def run(self):
        try:
            p = tpg(self.tel,self.dt,wind=self.wind,fwhm=self.fwhm,tag=self.tag,done_uobi=self.uobi_done,night_monitor=self.night_monitor,
                    night_monitor_gap=self.night_monitor_gap,
                    skyflats=self.skyflats,flat_history=self.flat_history,now=self.now)
            p.Initiate()
            if self.night_monitor:
                # master file night monitora lezy obok zwyklego master file, np. zb08_night_monitor.txt
                master_dir = os.path.dirname(p.cfg[self.tel]["master_file"])
                p.master_file = os.path.join(master_dir, f"{self.tel}_night_monitor.txt")
                if not os.path.isfile(p.master_file):
                    raise FileNotFoundError(f"no night monitor master file {p.master_file}")
                self.update_signal.emit(f"night monitor: {p.master_file}")
            p.init_ctc()
            self.update_signal.emit("TPG init <span style='color: green;'>\u2714</span>")
            p.LoadObjects()
            self.update_signal.emit("objects loaded <span style='color: green;'>\u2714</span>")
            p.MakeTime()
            p.ObjectMask()
            self.update_signal.emit("making timeline <span style='color: green;'>\u2714</span>")
            self.update_signal.emit(f"plan start: <span style='color: green; font-weight: bold;'> {p.start_time}  </span>")
            p.CalcObject()
            self.update_signal.emit("calculating visibilities <span style='color: green;'>\u2714</span>")
            p.MaskVisibility()
            self.update_signal.emit("masking visibility <span style='color: green;'>\u2714</span>")
            p.MaskMoon()
            self.update_signal.emit("masking moon <span style='color: green;'>\u2714</span>")
            p.MaskWind()
            #print(p.wind)
            self.update_signal.emit("masking wind <span style='color: green;'>\u2714</span>")
            p.MaskCycle()
            self.update_signal.emit("masking cycle <span style='color: green;'>\u2714</span>")
            p.MaskStartEnd()
            p.MaskTwilight()
            self.update_signal.emit("masking tim and twilight <span style='color: green;'>\u2714</span>")
            p.MaskPhaseStartEnd()
            p.MaskPhase()
            self.update_signal.emit("masking phase <span style='color: green;'>\u2714</span>")
            p.Waga()
            p.RandomizeList()
            self.update_signal.emit(f"seed: {p.seed}")
            p.allocate()
            self.update_signal.emit("allocating objects <span style='color: green;'>\u2714</span>")
            p.export()
            # wynik sfs dla kazdej sesji: wstawiony SKYFLAT albo dlaczego nie
            for session, info in getattr(p, "skyflat_info", {}).items():
                color = "green" if info["line"] else "orange"
                self.update_signal.emit(f"<span style='color: {color};'>{info['note']}</span>")
            if hasattr(p, "SavePlan"):
                p.SavePlan()
            self.update_signal.emit("<span style='color: green; font-weight: bold;'>\u2714 DONE \u2714</span>")
            self.plan_ready_signal.emit(p.plan)
            self.done_signal.emit()

        except SystemExit:
            # tpg robi sys.exit() przy zlej dacie lub braku master file - nie moze zamknac TOI
            self.error_signal.emit("TPG stopped: wrong date (use yyyy/mm/dd) or missing master file")
            self.done_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
            self.done_signal.emit()


class TPGWindow(BaseWindow):
    def __init__(self, parent):
        super(TPGWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.set_initial_geometry(100, 100, 400, 100)
        self.setMinimumSize(200, 450)
        self.mkUI()
        self._smart_sunset_checkbox()
        self._smart_skyflats_checkboxes()
        self._night_monitor_gap_default()
        self.sunset_changed()

    def add(self):
        tel = self.parent.parent.active_tel

        dt = self.ut_e.text().split()

        wind = None
        fwhm = None
        tag = None
        try:
            wind = float(self.wind_e.text()) if self.wind_c.isChecked() else None
            fwhm = float(self.fwhm_e.text()) if self.fwhm_c.isChecked() else None
            tag = self.tag_e.text() if self.tag_c.isChecked() else None
        except Exception as e:
            print(f'EXCEPTION TPG 2: {e}')

        if self.repeat_c.isChecked():
            uobi_done = list(self.parent.parent.done_uobi)
        else:
            uobi_done = []

        night_monitor = self.night_monitor_c.isChecked()
        night_monitor_gap = self.night_monitor_gap_e.value() if night_monitor else None

        # tpg dostaje liste sesji: osobno wieczorne i poranne
        skyflats = [s for s, c in (("evening", self.evening_flats_c), ("morning", self.morning_flats_c)) if c.isChecked()]
        flat_history = self._flat_history(tel) if skyflats else None

        self.thread = QtCore.QThread()
        self.worker = TPG_Worker(tel=tel,dt=dt,wind=wind,uobi_done=uobi_done,fwhm=fwhm,tag=tag,night_monitor=night_monitor,
                                 night_monitor_gap=night_monitor_gap,skyflats=skyflats,flat_history=flat_history,now=self.parent.parent.ut)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.update_signal.connect(self.update_status)
        self.worker.plan_ready_signal.connect(self.get_plan)
        self.worker.error_signal.connect(self.show_error)

        self.worker.done_signal.connect(self.thread.quit)
        self.worker.done_signal.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _flat_history(self, tel):
        """Historia flatow dla sfs z okna Calibration (kanaly flat_overwatch):
        {"evening"|"morning": {filtr: dni od ostatnich flatow tej sesji | None}}."""
        records = self.parent.parent.flatGui.flat_records.get(tel, {})
        if not records:
            self.info_e.append("<span style='color: orange;'>no flat history from flat_overwatch, SKYFLAT filters in group order</span>")
        now = datetime.datetime.now(datetime.timezone.utc)
        history = {}
        for session in ("evening", "morning"):
            history[session] = {}
            for f, v in records.get(f"flats_{session}", {}).items():
                t = v.get("last")
                if t:
                    t = datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc)
                    history[session][f] = (now - t).total_seconds() / 86400.
                else:
                    history[session][f] = None
        return history

    def update_status(self, txt):
        if "wind masking" in txt and not self.wind_c.isChecked():
            return
        self.info_e.append(txt)

    def show_error(self, txt):
        self.info_e.append(f"<span style='color: red; font-weight: bold;'>✘ {txt}</span>")

    def get_plan(self, plan):
        tmp_plan = []

        for blok in plan:
            BASE_SCHEMA = ObsValidator.load_schema("base_schema")
            COMMAND_RULES = ObsValidator.load_schema("base_rules.yaml")

            validator = ObsValidator(BASE_SCHEMA, COMMAND_RULES)
            result = validator.validate_txt(blok, allowed_filters=self.parent.parent.nats_cfg[self.parent.parent.active_tel]["filter_list_names"])
            if result["valid"]:
                data = {}
                data["ob"] = result["data"]
                data["meta"] = {"ok": True}
                data["block"] = blok
            else:
                # wczesniej zla linia dokladala do planu poprzednia (albo NameError na pierwszej)
                print(f'Error plan reading: \n {blok}')
                self.show_error(f"invalid plan line skipped: {blok}")
                continue

            tmp_plan.append(data)

        self.parent.plan[self.parent.i + 1:self.parent.i + 1] = tmp_plan
        self.parent.parent.upload_plan()
        self.parent.parent.update_plan(self.parent.parent.active_tel)

    def sunset_changed(self):
        dt = datetime.datetime.strptime(self.parent.parent.ut, "%Y/%m/%d %H:%M:%S")

        if self.sunset_c.isChecked():
            obs = ephem.Observer()
            obs.lat = self.parent.parent.observatory[0]
            obs.lon = self.parent.parent.observatory[1]
            obs.elevation = float(self.parent.parent.observatory[2])
            obs.date = dt

            sun = ephem.Sun()

            sunset = obs.previous_setting(sun)
            sunset = ephem.Date(sunset).datetime()

            if dt - sunset < datetime.timedelta(hours=2):
                if sunset.date() != dt.date():
                    time2set = dt - datetime.timedelta(days=1)
                else:
                    time2set = dt
            else:
                time2set = dt
            self.ut_e.setText(time2set.strftime("%Y-%m-%d"))
        else:
            self.ut_e.setText(dt.strftime("%Y-%m-%d %H:%M:%S"))


    def _smart_sunset_checkbox(self):
        dt = datetime.datetime.strptime(self.parent.parent.ut, "%Y/%m/%d %H:%M:%S")
        obs = ephem.Observer()
        obs.lat = self.parent.parent.observatory[0]
        obs.lon = self.parent.parent.observatory[1]
        obs.elevation = float(self.parent.parent.observatory[2])
        obs.date = dt

        sun = ephem.Sun()
        last_sunset = obs.previous_setting(sun)
        next_sunrise = obs.next_rising(sun)
        next_sunset = obs.next_setting(sun)

        last_sunset = ephem.Date(last_sunset).datetime()
        next_sunrise = ephem.Date(next_sunrise).datetime()
        next_sunset = ephem.Date(next_sunset).datetime()

        delta_sunset = dt - last_sunset

        if next_sunset < next_sunrise or delta_sunset < datetime.timedelta(hours=2):
            self.sunset_c.setChecked(True)
        else:
            self.sunset_c.setChecked(False)


    def _tpg_cfg(self):
        try:
            return tpg_load_config()
        except Exception as e:
            print(f'TPG: tpg config not read: {e}')
            return {}

    def _night_monitor_gap_default(self):
        # przerwa night monitora z configu tpg dla teleskopu (jak w tpg), domyslnie 15 min
        try:
            self.night_monitor_gap_e.setValue(int(self._tpg_cfg()[self.parent.parent.active_tel].get("night_monitor_gap", 15)))
        except Exception:
            self.night_monitor_gap_e.setValue(15)

    def _smart_skyflats_checkboxes(self):
        """Wieczorne skyflaty wlaczone, dopoki Slonce jest nad dolna granica sesji flatow (skyflat.hsun z configu tpg)
        i zachodzi - pozniej tpg i tak by je pominal (sesja minela). Poranne zawsze, sa przed nami."""
        hsun_low = -15.
        try:
            cfg = self._tpg_cfg()
            hsun = cfg[self.parent.parent.active_tel].get("skyflat", {}).get("hsun") or cfg.get("skyflat", {}).get("hsun")
            hsun_low = min(float(h) for h in hsun)
        except Exception as e:
            print(f'TPG: skyflat hsun not read from tpg config, using {hsun_low}: {e}')

        obs = ephem.Observer()
        obs.lat = self.parent.parent.observatory[0]
        obs.lon = self.parent.parent.observatory[1]
        obs.elevation = float(self.parent.parent.observatory[2])
        obs.date = datetime.datetime.strptime(self.parent.parent.ut, "%Y/%m/%d %H:%M:%S")
        obs.horizon = str(hsun_low)
        sun = ephem.Sun()
        evening = obs.next_setting(sun, use_center=True) < obs.next_rising(sun, use_center=True)
        self.evening_flats_c.setChecked(evening)
        self.morning_flats_c.setChecked(True)

    def mkUI(self):
        grid = QGridLayout()

        self.sunset_c = QCheckBox("Start at SUNSET")
        self.sunset_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )

        self.ut_e = QLineEdit()
        self.sunset_c.stateChanged.connect(self.sunset_changed)

        if ephem.Date(self.parent.parent.almanac["sunset"]) > ephem.Date(self.parent.parent.almanac["sunrise"]):
            self.sunset_c.setChecked(False)

        self.wind_c = QCheckBox("Avoid wind direction")
        self.wind_c.setChecked(False)
        self.wind_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )

        self.wind_e = QLineEdit("")
        self.wind_e.setText(f"{self.parent.parent.telemetry_wind_direction:.0f}")

        self.fwhm_c = QCheckBox("FWHM Limit")
        self.fwhm_c.setChecked(False)
        self.fwhm_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )

        self.fwhm_e = QLineEdit("")

        self.tag_c = QCheckBox("Select tag")
        self.tag_c.setChecked(False)
        self.tag_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )

        self.tag_e = QLineEdit("")

        self.repeat_c = QCheckBox("Dont repeat observed objects")
        self.repeat_c.setChecked(True)
        self.repeat_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )

        self.evening_flats_c = QCheckBox("Evening SKYFLATS")
        self.morning_flats_c = QCheckBox("Morning SKYFLATS")
        for c in (self.evening_flats_c, self.morning_flats_c):
            c.setChecked(True)
            c.setStyleSheet(
                "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
                "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
            )

        self.night_monitor_c = QCheckBox("Night monitor")
        self.night_monitor_c.setChecked(False)
        self.night_monitor_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}"
            "QCheckBox::indicator:unchecked {image: url(./Icons/SwitchOff.png)}"
        )
        # przerwa miedzy obserwacjami night monitora (tpg night_monitor_gap)
        self.night_monitor_gap_e = QSpinBox()
        self.night_monitor_gap_e.setRange(0, 600)
        self.night_monitor_gap_e.setSuffix(" min")
        self.night_monitor_gap_e.setPrefix("interval ")
        self.night_monitor_gap_e.setToolTip("Break between observations in night monitor mode")
        self.night_monitor_gap_e.setEnabled(False)
        self.night_monitor_c.toggled.connect(self.night_monitor_gap_e.setEnabled)

        self.add_p = QPushButton('Generate Plan')
        self.add_p.clicked.connect(self.add)

        self.close_p = QPushButton('Close')
        self.close_p.clicked.connect(lambda: self.close())

        self.info_e = QTextEdit("")
        self.info_e.setReadOnly(True)
        self.info_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.ut_e, 0, 0, 1, 2)
        grid.addWidget(self.sunset_c, 1, 0)
        grid.addWidget(self.evening_flats_c, 1, 1)
        grid.addWidget(self.morning_flats_c, 2, 1)

        grid.addWidget(self.wind_c, 3, 0)
        grid.addWidget(self.wind_e, 3, 1)

        grid.addWidget(self.fwhm_c, 4, 0)
        grid.addWidget(self.fwhm_e, 4, 1)

        #grid.addWidget(self.tag_c, 4, 0)
        #grid.addWidget(self.tag_e, 4, 1)

        grid.addWidget(self.night_monitor_c, 5, 0)
        grid.addWidget(self.night_monitor_gap_e, 5, 1)

        grid.addWidget(self.repeat_c, 6, 0, 1, 2)

        grid.addWidget(self.info_e, 7, 0, 1, 2)

        grid.addWidget(self.add_p, 8, 1)
        grid.addWidget(self.close_p, 8, 0)

        self.setLayout(grid)
        self.show()

# #############################################
# ######### OKNO WYKRESU (PHASE) ##########
# #############################################

class PhaseWindow(BaseWindow):
    def __init__(self, parent):
        super(PhaseWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.set_initial_geometry(100,100,800,400)
        self.setMinimumSize(800,400)
        self.mkUI()
        try:
            self.get_object()
        except FileNotFoundError:
            pass
        self.refresh()


    def get_object(self):
        self.name = self.parent.plan[self.parent.i]["ob"]["name"]

        if "plan_ut" in self.parent.plan[self.parent.i]["meta"].keys():
            self.ut = self.parent.plan[self.parent.i]["meta"]["plan_ut"]
        else:
            self.ut = self.parent.parent.almanac['ut']

        self.f_path = self.parent.parent.cfg_tel_directory+"processed-ofp/targets/"+self.name.lower()
        self.filters = os.listdir(self.f_path)
        #print(self.filters)
        self.file_s.addItems(self.filters)

    def refresh(self):
        self.axes.clear()
        try:
            filter = self.file_s.currentText()
            file = self.f_path+"/"+filter+"/light-curve/"+self.name.lower()+"_"+filter+"_diff_light_curve.txt"
            s = ephem.Observer()
            s.date = ephem.Date(self.ut)
            t = ephem.julian_date(s)
            mag = []
            jd = []
            flag = []
            #print(file)

            lc_tab = Table.read(file, format="ascii")
            mag = lc_tab["mag"]
            jd = lc_tab["jd_obs"]
            flag = lc_tab["quality"]

            # with open(file, "r") as plik:
            #     if plik != None:
                    # for line in plik:
                    #     if len(line.strip()) > 0:
                    #         try:
                    #             mag.append(float(line.split()[1]))
                    #             jd.append(float(line.split()[3]))
                    #             try:
                    #                 flag.append(int(line.split()[9]))
                    #             except ValueError:
                    #                 pass
                    #         except ValueError:
                    #             pass
            if len(mag) == len(jd) and len(jd)>0:
                #print(mag,jd)
                if self.phase_c.isChecked():
                    objects = []
                    periods = []
                    jd0s = []
                    file = self.parent.parent.cfg_tel_ob_list+"objects.txt"
                    with open(file, "r") as plik:
                        if plik != None:
                            for line in plik:
                                if len(line.strip()) > 0:
                                    try:
                                        a = line.split()[0]
                                        b = float(line.split()[3])
                                        c = float(line.split()[4])
                                        objects.append(a)
                                        periods.append(b)
                                        jd0s.append(c)
                                    except ValueError:
                                        pass
                    i = objects.index(self.name)
                    P = periods[i]
                    jd0 = jd0s[i]
                    if not numpy.isnan(P):
                        if numpy.isnan(jd0):
                            jd0 = min(jd)
                        jd = (numpy.array(jd) - float(jd0))/float(P)%1
                        t = (t - float(jd0))/float(P)%1
                        self.axes.set_xlim(-0.1,1.1)
                        self.axes.set_title(f"{self.ut} {self.name} P={P}")
                    else:
                        self.phase_c.setChecked(False)
                        self.axes.set_title(f"{self.ut} {self.name}")
                else:
                    self.axes.set_title(f"{self.ut} {self.name}")

                if len(flag) == len(jd):
                    jd = numpy.array(jd)
                    mag = numpy.array(mag)
                    flag = numpy.array(flag)

                    mk = flag == 0
                    x = jd[mk]
                    y = mag[mk]
                    self.axes.plot(x, y, ".g")

                    mk = flag == 1
                    x = jd[mk]
                    y = mag[mk]
                    self.axes.plot(x, y, ".c", alpha = 0.5)

                    mk = flag == 2
                    x = jd[mk]
                    y = mag[mk]
                    self.axes.plot(x, y, ".k", alpha = 0.3)

                else:
                    x = jd
                    y = mag
                    self.axes.plot(x,y,".g")

                d = 0.1*(max(mag)-min(mag))
                self.axes.set_ylim(max(mag)+d,min(mag)-d)
                self.axes.axvline(x=t, color="red")

                #self.fig.subplots_adjust(bottom=0.12,top=0.8,left=0.15,right=0.98)
        except (FileNotFoundError,ValueError) as e:
            print(f"Phase Window Error: {e}")

        #self.fig.tight_layout()
        self.canvas.draw()
        self.show()



    def mkUI(self):
        grid = QGridLayout()

        self.file_s = QComboBox()
        self.file_s.currentIndexChanged.connect(self.refresh)
        self.phase_c = QCheckBox("Phase")
        self.phase_c.setChecked(True)
        #self.phase_c.setLayoutDirection(Qt.RightToLeft)
        self.phase_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.phase_c.clicked.connect(self.refresh)


        self.fig = Figure((2.0, 2.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        #self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes = self.fig.add_subplot(111)
        grid.addWidget(self.file_s, 0, 0)
        grid.addWidget(self.phase_c, 0, 3)
        grid.addWidget(self.canvas,1,0,4,4)

        self.toolbar = NavigationToolbar(self.canvas,self)
        grid.addWidget(self.toolbar, 5, 0, 1, 4)

        self.close_p = QPushButton('Close')
        self.close_p.clicked.connect(lambda: self.close())
        grid.addWidget(self.close_p, 6, 3)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)
        grid.setRowStretch(2, 0)

        self.setLayout(grid)




# #############################################
# ######### OKNO WYKRESU (PLOT PLAN) ##########
# #############################################

class PlotWindow(BaseWindow):
    # kolor wg obiektu (powtorzony obiekt ma ten sam kolor); bez czerwieni - STOP i WAIT sa czerwone
    PALETTE = ["tab:blue", "tab:orange", "tab:green", "tab:purple", "tab:brown", "tab:pink", "tab:olive",
               "tab:cyan", "navy", "darkgoldenrod", "teal", "indigo"]
    LABEL_GAP = 0.008       # najmniejszy odstep podpisow nad wykresem (czesc szerokosci osi) - gestsze tylko po najechaniu

    def __init__(self, parent):
        super(PlotWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.set_initial_geometry(100,100,1800,600)
        self.setMinimumSize(1800,600)
        self.mkUI()
        self.refresh()
        self.close_p.clicked.connect(lambda: self.close())

    def refresh(self):

        self.oca = ephem.Observer()
        self.oca.date = ephem.now()
        self.oca.lat = self.parent.parent.observatory[0]
        self.oca.lon = self.parent.parent.observatory[1]
        self.oca.elevation = float(self.parent.parent.observatory[2])
        self.t_now = ephem.now()

        # liczenie wschodu slonca i zachodu
        self.oca.horizon = "0"
        t1 = self.oca.next_setting(ephem.Sun(),use_center=True) - ephem.now()
        t2 = self.oca.next_rising(ephem.Sun(), use_center=True) - ephem.now()
        if t1 < t2 :
            self.t0 = self.oca.next_setting(ephem.Sun(),use_center=True)
        else:
            self.t0 = self.oca.previous_setting(ephem.Sun(),use_center=True)
        self.oca.date = self.t0
        self.t_end = self.oca.next_rising(ephem.Sun(),use_center=True)

        # liczenie zmierzchu
        self.oca.horizon = "-18"
        self.t0_dusk = self.oca.next_setting(ephem.Sun(),use_center=True)
        self.t_end_dusk = self.oca.next_rising(ephem.Sun(),use_center=True)



        # Rysowanie

        if len(self.parent.plan)>0:
            if self.t_now > self.t0:
                self.t = self.t_now
            else:
                self.t = self.t0
            if self.parent.parent.nats_ob_progress["ob_started"]:
                if self.parent.parent.nats_ob_progress["ob_start_time"] and self.parent.parent.nats_ob_progress[
                    "ob_expected_time"]:
                    t0 = self.parent.parent.time
                    dt = (t0 - self.parent.parent.nats_ob_progress["ob_start_time"])
                    self.t = self.t - ephem.second * dt
            colors = {}             # nazwa obiektu -> kolor
            self.night = {}         # nazwa obiektu -> (ra, dec, styl, kolor) - do bladej krzywej calej nocy
            self.night_lines = {}   # nazwa obiektu -> linia calej nocy (rysowana dopiero, gdy potrzebna)
            self.segments = []      # (t0, t1, opis, nazwa obiektu|None) slotow OB - dla podpowiedzi pod myszka
            labels = []             # (t0, t1, nazwa, kolor, fontsize) - podpisy nad wykresem
            events = []             # (t, tekst) - STOP, BELL, WAIT, ZERO... - podpisy przy dolnej krawedzi
            x_span = (self.t_end - self.t0) + ephem.hour
            for i, tmp in enumerate(self.parent.plan):

                fontsize = 9
                tmp_ok = False
                if self.parent.current_i > -1 and i >= self.parent.current_i: tmp_ok = True
                if i >= self.parent.next_i: tmp_ok = True
                if 'skip' in self.parent.plan[i]["meta"].keys():
                    if self.parent.plan[i]["meta"]['skip']:
                        tmp_ok = False
                if 'skip_alt' in self.parent.plan[i]["meta"].keys():
                    if self.parent.plan[i]["meta"]['skip_alt']:
                        tmp_ok = False
                if 'ok' in self.parent.plan[i]["meta"].keys():
                    if not self.parent.plan[i]["meta"]['ok']:
                        tmp_ok = False

                if tmp_ok:
                    # czas startu wiersza bierzemy z tabeli (meta["plan_ut"]), zeby wykres
                    # nie liczyl wlasnej osi czasu. Brak plan_ut -> stara akumulacja slotTime.
                    if "plan_ut" in self.parent.plan[i]["meta"].keys():
                        try:
                            self.t = ephem.Date(parse_plan_ut_str(str(self.parent.plan[i]["meta"]["plan_ut"])))
                        except (ValueError, TypeError):
                            pass
                    if 'command_name' in self.parent.plan[i]["ob"].keys():
                        if self.parent.plan[i]["ob"]["command_name"] == "STOP":
                            txt = "STOP"
                            if "comment" in self.parent.plan[i]["ob"].keys():
                                txt = txt + f' {self.parent.plan[i]["ob"]["comment"]}'
                            events.append((self.t, txt))
                            self.axes.axvline(x=self.t, color="red",alpha=0.5)

                        elif self.parent.plan[i]["ob"]["command_name"] == "BELL":
                            txt = "BELL"
                            if "comment" in self.parent.plan[i]["ob"].keys():
                                txt = txt + f' {self.parent.plan[i]["ob"]["comment"]}'
                            events.append((self.t, txt))
                            self.axes.axvline(x=self.t, color="deepskyblue",alpha=0.5)

                        if "slotTime" in self.parent.plan[i]["meta"].keys():
                            slotTime = float(self.parent.plan[i]["meta"]["slotTime"])

                            if "sec" in self.parent.plan[i]["ob"].keys():
                                self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                                events.append((self.t, f"WAIT sec={int(slotTime):.0f}s"))

                            elif "ut" in self.parent.plan[i]["ob"].keys():
                                self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                                events.append((self.t, f'WAIT ut={self.parent.plan[i]["ob"]["ut"]}'))

                            elif "sunset" in self.parent.plan[i]["ob"].keys():
                                self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                                events.append((self.t, f'WAIT sunset={self.parent.plan[i]["ob"]["sunset"]}'))

                            elif "sunrise" in self.parent.plan[i]["ob"].keys():
                                self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                                events.append((self.t, f'WAIT sunrise={self.parent.plan[i]["ob"]["sunrise"]}'))


                            else:

                                fontsize = 7 if slotTime < 60 * 10 else 9

                                if "ra" not in self.parent.plan[i]["ob"].keys() and slotTime > 0:
                                    # ZERO, DARK... - zajmuja czas, a nie maja wspolrzednych: szary pasek
                                    command = self.parent.plan[i]["ob"]["command_name"]
                                    self.axes.fill_betweenx([0, 2], self.t, self.t + ephem.second * slotTime, color="grey", alpha=0.5)
                                    events.append((self.t, command))
                                    self.segments.append((self.t, self.t + ephem.second * slotTime,
                                                          f"{command}\nstart {str(ephem.Date(self.t)).split()[1][:5]} UT, {slotTime / 60:.0f} min", None))

                                if "ra" in self.parent.plan[i]["ob"].keys():
                                    ra = self.parent.plan[i]["ob"]["ra"]
                                    dec = self.parent.plan[i]["ob"]["dec"]
                                    name = self.parent.plan[i]["ob"].get("name", "")
                                    standard = "standard" in self.parent.plan[i]["block"]
                                    style = "--" if standard else "-"
                                    if name not in colors:
                                        colors[name] = self.PALETTE[len(colors) % len(self.PALETTE)]
                                        self.night[name] = (ra, dec, style, colors[name])
                                    color = colors[name]
                                    # cala noc blado tylko dla zaznaczonego OB (reszta pod myszka albo "All night
                                    # curves") - przy wielu obiektach (zb08) krzywe calej nocy zaslanialy plan
                                    if i == self.parent.i:
                                        self.night_line(name).set_visible(True)
                                    t_tab, alt_tab = self.altitudes(ra, dec, self.t, self.t + ephem.second * slotTime, 10 * ephem.second)
                                    if i == self.parent.i:
                                        self.axes.axvspan(min(t_tab), max(t_tab), color="grey", alpha=0.15)
                                    self.axes.plot(t_tab, alt_tab, style, color=color, linewidth=3)
                                    labels.append((self.t, self.t + ephem.second * slotTime, name, color, fontsize))
                                    self.segments.append((self.t, self.t + ephem.second * slotTime,
                                                          f"{name}\nstart {str(ephem.Date(self.t)).split()[1][:5]} UT, "
                                                          f"{slotTime / 60:.0f} min\nalt {alt_tab[0]:.0f}\u00b0 \u2192 {alt_tab[-1]:.0f}\u00b0", name))

                            self.t = self.t + ephem.second * slotTime

            # zdarzenia w tym samym miejscu (np. BELL, ZERO, BELL, WAIT rano - BELL i WAIT nie zajmuja czasu) jeden podpis
            groups = []
            for t, txt in events:
                if groups and (t - groups[-1][0]) / x_span < self.LABEL_GAP:
                    groups[-1][1].append(txt)
                else:
                    groups.append((t, [txt]))
            for t, txts in groups:
                self.axes.text(t, 3, " \u00b7 ".join(txts), rotation=90, fontsize=8)

            # podpisy nad wykresem - kazdy OB ma nazwe (brak bylby mylacy): na poczatku slotu, a gdy tam ciasno - w
            # pierwszym wolnym miejscu w obrebie slotu; gdy i tam nie ma miejsca, na poczatku slotu (nachodza - widac,
            # ze jest gesto; szczegoly pod myszka)
            gap = self.LABEL_GAP * x_span
            last = None
            self.labels_drawn = []
            for t0, t1, name, color, fs in labels:
                x = t0 if last is None else max(t0, last + gap)
                if x > t1:
                    x = t0
                self.axes.text(x, 93, name, color=color, rotation=90, fontsize=fs)
                self.labels_drawn.append(name)
                last = x if last is None else max(last, x)

            self.axes.set_ylim(0, 90)
            self.axes.set_xlim(self.t0-0.5*ephem.hour,self.t_end+0.5*ephem.hour)
            self.axes.fill_betweenx([0, 35], self.t0_dusk, self.t_end_dusk, color="grey", alpha=0.1)
            self.axes.fill_betweenx([80, 90], self.t0_dusk, self.t_end_dusk, color="grey", alpha=0.1)
            self.axes.fill_betweenx([0, 90], self.t0, self.t0_dusk, color="yellow", alpha=0.1)
            self.axes.fill_betweenx([0, 90], self.t_end_dusk, self.t_end, color="yellow", alpha=0.1)
            self.axes.axvline(x=self.t_now, color="green")
            txt = str(self.t_now).split()[1].split(":")[0] + ":" + str(self.t_now).split()[1].split(":")[1]
            self.axes.text(self.t_now, 82, f"{txt}", rotation=90, fontsize=fontsize)

            xtics = [self.t0, self.t0_dusk, self.t_end_dusk, self.t_end]
            t =  ephem.Date(self.t0_dusk+30*ephem.minute)
            while t < ephem.Date(self.t_end_dusk-30*ephem.minute):
                t = ephem.Date(t) + ephem.hour
                h = str(ephem.Date(t)).split()
                xtics.append( ephem.Date(h[0]+" "+h[1].split(":")[0]+":00:00"))
            xtics_labels = [str(x).split()[1].split(":")[0]+":"+str(x).split()[1].split(":")[1] for x in xtics]
            self.axes.set_xticks(xtics)
            self.axes.set_xticklabels(xtics_labels,rotation=45,minor=False)

            self.axes.set_yticks([0, 35, 80, 90])
            self.axes.set_yticklabels(["0 deg", "35 deg", "80 deg", "90 deg"])

            #self.axes.set_ylabel("altitude")
            #self.axes.set_xlabel("UT")
            self.fig.subplots_adjust(bottom=0.12,top=0.8,left=0.08,right=0.98)
            #self.fig.tight_layout()

            self.canvas.draw()
            self.show()





    def altitudes(self, ra, dec, t0, t1, step):
        # wysokosc obiektu od t0 do t1 co step (ephem.Date); ephem wprost - pelna noc dla kazdego obiektu
        body = ephem.FixedBody()
        body._ra, body._dec = ephem.hours(ra), ephem.degrees(dec)
        ts, alts, t = [], [], t0
        while t <= t1:
            self.oca.date = t
            body.compute(self.oca)
            ts.append(t)
            alts.append(float(body.alt) * 180 / ephem.pi)
            t = t + step
        return ts, alts

    def night_line(self, name):
        # blada krzywa wysokosci obiektu przez cala noc - widac wschod, zachod i gdzie w nocy jest slot;
        # liczona przy pierwszej potrzebie, potem tylko pokazywana / chowana
        if name not in self.night_lines:
            ra, dec, style, color = self.night[name]
            t_night, alt_night = self.altitudes(ra, dec, self.t0, self.t_end, 10 * ephem.minute)
            self.night_lines[name], = self.axes.plot(t_night, alt_night, style, color=color, alpha=0.25, linewidth=1,
                                                     visible=False)
        return self.night_lines[name]

    def show_night(self, hovered=None):
        # widoczne: wszystkie ("All night curves"), albo zaznaczony OB i obiekt pod myszka
        selected = None
        if 0 <= self.parent.i < len(self.parent.plan):
            selected = self.parent.plan[self.parent.i]["ob"].get("name")
        for name in self.night:
            show = self.all_night_c.isChecked() or name in (selected, hovered)
            if show or name in self.night_lines:
                self.night_line(name).set_visible(show)

    def on_hover(self, event):
        # podpowiedz z nazwa, startem, dlugoscia i wysokoscia slotu pod myszka, i krzywa calej nocy tego obiektu
        text, name = None, None
        if event.inaxes is self.axes and event.xdata is not None:
            for t0, t1, txt, obj in getattr(self, "segments", []):
                if t0 <= event.xdata <= t1:
                    text, name = txt, obj
                    break
        if name != getattr(self, "hovered", None):
            self.hovered = name
            self.show_night(name)
        elif not text and not self.hover.get_visible():
            return
        if text:
            self.hover.xy = (event.xdata, event.ydata)
            self.hover.set_text(text)
            self.hover.set_visible(True)
        else:
            self.hover.set_visible(False)
        self.canvas.draw_idle()

    def all_night_changed(self):
        self.show_night(getattr(self, "hovered", None))
        self.canvas.draw_idle()

    def mkUI(self):
        grid = QGridLayout()
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        #self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes = self.fig.add_subplot(111)
        self.hover = self.axes.annotate("", xy=(0, 0), xytext=(12, -12), textcoords="offset points", va="top",
                                        fontsize=9, bbox=dict(boxstyle="round", fc="white", alpha=0.9), zorder=10)
        self.hover.set_visible(False)
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        grid.addWidget(self.canvas,0,0,1,2)

        self.toolbar = NavigationToolbar(self.canvas,self)
        grid.addWidget(self.toolbar, 1, 0, 1, 2)

        # krzywe calej nocy wszystkich obiektow - domyslnie tylko zaznaczony OB i obiekt pod myszka
        self.all_night_c = QCheckBox("All night curves")
        self.all_night_c.setChecked(False)
        self.all_night_c.toggled.connect(self.all_night_changed)
        grid.addWidget(self.all_night_c, 2, 0)

        self.close_p = QPushButton('Close')
        grid.addWidget(self.close_p, 2, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)
        grid.setRowStretch(2, 0)

        self.setLayout(grid)





# ########################################
#              EDIT WINDOW
# ########################################

def ob_value(prop, val):
    """Wartosc pola OB do bloku. Pola boolean ze schematu (dzis tylko test) jako 1/0: planrunner robi
    int(kwargs["test"]) i kazdy blad po cichu zamienia na 0, wiec test=True dawalo w naglowku TEST=0.
    Te same zapisy co ObsValidator.convert_types (true/1, false/0); reszte zostawiamy walidatorowi"""
    if prop.get("type") == "boolean":
        low = str(val).strip().lower()
        if low in ("true", "1"):
            return "1"
        if low in ("false", "0"):
            return "0"
    return val


class EditWindow(QWidget):
    def __init__(self, parent):
        super().__init__()

        self.parent = parent

        self.base_schema = ObsValidator.load_schema("base_schema.yaml")
        self.command_rules = ObsValidator.load_schema("base_rules.yaml")
        self.validator = ObsValidator(self.base_schema, self.command_rules)

        self.setWindowTitle(" OB EDIT WINDOW")
        self.resize(600, 600)
        self.setStyleSheet("font-size: 11pt;")

        self.updating = False
        self.initial_load = True

        self.mkUI()
        self.load_initial()

    def save_ob(self):
        if self.validate_current():
            tmp = {}
            ob = self.collect_table_data()
            tmp["ob"] = ob
            tmp["block"] = self.validator.convert_from_obdict(ob)
            tmp["meta"] = {"ok":True}

            self.parent.plan[self.parent.i] = tmp
            # jak przy dodawaniu OB: plan do TOI i przeliczenie (update_plan) - inaczej edytowany OB nie mial czasu
            # startu, a nastepne zostawaly ze starymi czasami
            self.parent.parent.upload_plan()
            self.close()

    # {
    #     'ok': True, 'type': 'OBJECT', 'name': 'Pismis11', 'ra': '09:15:53.0', 'dec': '-50:01:00',
    #     'seq': '2/g/60,2/g/180,2/r/60,2/r/180', 'slotTime': 1082.6232618834988, 'uobi': '9266e680',
    #     'comment': 'every 1h', 'meta_alt': '60.7', 'meta_az': '204.6', 'meta_plan_ut': '2026/4/21 02:20:40',
    #     'meta_plan_alt': '52.9', 'meta_plan_az': '217.5', 'skip_alt': False}

    def load_initial(self):
        try:
            txt = self.parent.plan[self.parent.i]["block"]
        except Exception:
            print("ERROR: Loading OB")
            txt = "ERROR"

        self.block_e.setText(txt)
        self.block_e.setCursorPosition(0)
        self.initial_load = False


    def build_block(self):
        data = self.collect_table_data()
        txt = self.validator.convert_from_obdict(data)
        if txt:
            return txt
        return ""

    def collect_table_data(self):
        data = {"command_name": self.type_s.currentText()}

        for row in range(self.tab_t.rowCount()):
            key = self.tab_t.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            val_item = self.tab_t.item(row, 1)
            if not val_item:
                continue

            val = val_item.text().strip()
            if val != "":
                data[key] = ob_value(self.schema_prop(key), val)

        return data

    def schema_prop(self, key):
        return self.base_schema.get("properties", {}).get(key, {})

    def tooltip_for(self, key):
        prop = self.schema_prop(key)

        desc = prop.get("description", "")
        typ = prop.get("type", "")
        enum = prop.get("enum", None)

        lines = []

        if desc:
            lines.append(desc)

        if typ:
            lines.append(f"Type: {typ}")

        if enum:
            lines.append("Allowed: " + ", ".join(map(str, enum)))

        return "\n".join(lines)

    def example_for(self, key):
        prop = self.schema_prop(key)
        ex = prop.get("examples", [])
        if ex:
            return ob_value(prop, str(ex[0]))
        return ""


    def rebuild_table(self, command_name, values=None):
        self.updating = True

        self.tab_t.blockSignals(True)
        self.tab_t.setRowCount(0)

        allowed = self.command_rules[command_name]["allowed"]

        visible = [x for x in allowed if x != "command_name"]

        for r, key in enumerate(visible):
            self.tab_t.insertRow(r)

            # parameter
            item0 = QTableWidgetItem(key)
            item0.setBackground(QColor(235, 235, 235))
            item0.setFlags(item0.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            item0.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            item0.setToolTip(self.tooltip_for(key))
            self.tab_t.setItem(r, 0, item0)

            # value
            val = ""
            if values and key in values:
                val = str(values[key])

            item1 = QTableWidgetItem(val)
            self.tab_t.setItem(r, 1, item1)

            # example
            item2 = QTableWidgetItem(self.example_for(key))
            item2.setBackground(QColor(235, 235, 235))
            item2.setFlags(item2.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.tab_t.setItem(r, 2, item2)

        self.tab_t.blockSignals(False)
        self.updating = False


    def block_changed(self):
        if not self.initial_load:
            self.block_e.setStyleSheet("background-color: white; color: black;")
            self.status_l.setText("\u2699 OB changed")
            self.status_l.setStyleSheet("color: blue; font-weight: normal;")

        if self.updating:
            return

        txt = self.block_e.text()
        ob_tmp = ObsPlanParser.convert_from_string(txt)
        if ob_tmp:
            ob = ObsValidator.convert_to_obdict(ob_tmp)
            cmd = ob.get("command_name", "OBJECT")
        else:
            ob = {"command_name", "OBJECT"}
            cmd = "OBJECT"

        if cmd not in self.base_schema["properties"]["command_name"]["enum"]:
            ob = {"command_name", "OBJECT"}
            cmd = "OBJECT"

        self.updating = True
        self.type_s.setCurrentText(cmd)
        self.rebuild_table(cmd, ob)
        self.updating = False

    def command_changed(self):
        if self.updating:
            return

        cmd = self.type_s.currentText()
        current = self.collect_table_data()
        self.rebuild_table(cmd, current)

        self.refresh_block()

    def table_changed(self):
        self.status_l.setText("\u2699 OB changed")
        self.status_l.setStyleSheet("color: blue; font-weight: normal;")

        if self.updating:
            return
        self.refresh_block()

        for r in range(self.tab_t.rowCount()):
            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(QColor("white"))


    def refresh_block(self):
        self.updating = True
        txt = self.build_block()
        self.block_e.setText(txt)
        self.updating = False


    def validate_current(self):
        data = self.collect_table_data()

        result = self.validator.validate_ob(data,allowed_filters=self.parent.parent.nats_cfg[self.parent.parent.active_tel]["filter_list_names"])

        row_map = {}
        for r in range(self.tab_t.rowCount()):
            key = self.tab_t.item(r, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            row_map[key] = r


        self.tab_t.blockSignals(True)
        self.updating = True

        # clear colors
        for r in range(self.tab_t.rowCount()):
            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(QColor("white"))

        # apply colors
        for key, state in result["result"].items():
            if key not in row_map:
                continue

            r = row_map[key]
            color = QColor(217, 239, 217) if state is True else QColor(255, 180, 80)

            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(color)

        self.tab_t.blockSignals(False)
        self.updating = False

        if result["valid"]:
            self.status_l.setText("✅ Valid OB ")
            #self.status_l.setText("\u2714 Valid OB ")
            self.status_l.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_l.setText("❌ Validation errors")
            #self.status_l.setText("\u274C Validation errors")
            self.status_l.setStyleSheet("color: orange; font-weight: bold;")

        return result["valid"]

    def mkUI(self):
        grid = QGridLayout()

        r = 0
        # block line
        self.block_e = QLineEdit()
        self.block_e.textChanged.connect(self.block_changed)
        grid.addWidget(self.block_e, r, 0, 1, 3)

        r += 1
        # command selector
        self.type_l = QLabel("TYPE")
        self.type_s = QComboBox()
        self.type_s.addItems(list(self.command_rules.keys()))
        self.type_s.currentTextChanged.connect(self.command_changed)

        grid.addWidget(self.type_l, r, 0)
        grid.addWidget(self.type_s, r, 1, 1, 2)

        r += 1
        # table
        self.tab_t = QTableWidget()
        self.tab_t.setColumnCount(3)
        self.tab_t.setHorizontalHeaderLabels(["Parameter", "Value", "Example"])
        self.tab_t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tab_t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tab_t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.tab_t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # zaznaczenie całego wiersza
        self.tab_t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab_t.setStyleSheet("selection-background-color: rgb(200,220,255); selection-color: black; ")
        self.tab_t.verticalHeader().hide()

        self.tab_t.itemChanged.connect(self.table_changed)

        grid.addWidget(self.tab_t, r, 0, 1, 3)

        r += 1
        # status
        self.status_l = QLabel("Not validated")
        grid.addWidget(self.status_l, r, 0, 1, 2)

        self.validate_p = QPushButton("Validate OB")
        self.validate_p.clicked.connect(self.validate_current)
        grid.addWidget(self.validate_p, r, 1, 1 ,2)

        r += 1

        self.save_p = QPushButton("Save")
        self.save_p.clicked.connect(self.save_ob)
        grid.addWidget(self.save_p, r, 2)

        self.close_p = QPushButton("Close")
        self.close_p.clicked.connect(self.close)
        grid.addWidget(self.close_p, r, 0)

        self.setLayout(grid)
        self.show()
          
          


###########################################
###             ADD WINDOW              ###
###########################################

class AddWindow(QWidget):
    def __init__(self, parent):
        super().__init__()

        self.parent = parent

        self.base_schema = ObsValidator.load_schema("base_schema.yaml")
        self.command_rules = ObsValidator.load_schema("base_rules.yaml")
        self.validator = ObsValidator(self.base_schema, self.command_rules)

        self.setWindowTitle(" OB ADD WINDOW")
        self.resize(600, 600)
        self.setStyleSheet("font-size: 11pt;")

        self.updating = False
        self.initial_load = True

        self.mkUI()
        self.load_initial()

    def save_ob(self):
        if self.validate_current():
            tmp = {}
            ob = self.collect_table_data()
            tmp["ob"] = ob
            tmp["block"] = self.validator.convert_from_obdict(ob)
            tmp["meta"] = {"ok": True}

            tel = self.parent.parent.active_tel
            pos = min(self.parent.i + 1, len(self.parent.plan))
            self.parent.plan.insert(pos, tmp)
            # OB wstawione nad wykonywanym przesuwa current_i; wstawione na miejscu next_i staje sie nastepnym
            if -1 < self.parent.parent.current_i[tel] and pos <= self.parent.parent.current_i[tel]:
                self.parent.parent.current_i[tel] += 1
            if -1 < self.parent.next_i and pos < self.parent.next_i:
                self.parent.next_i += 1
            self.parent.i = pos
            self.parent.parent.upload_plan()
            self.close()


    # {
    #     'ok': True, 'type': 'OBJECT', 'name': 'Pismis11', 'ra': '09:15:53.0', 'dec': '-50:01:00',
    #     'seq': '2/g/60,2/g/180,2/r/60,2/r/180', 'slotTime': 1082.6232618834988, 'uobi': '9266e680',
    #     'comment': 'every 1h', 'meta_alt': '60.7', 'meta_az': '204.6', 'meta_plan_ut': '2026/4/21 02:20:40',
    #     'meta_plan_alt': '52.9', 'meta_plan_az': '217.5', 'skip_alt': False}

    def load_initial(self):
        txt = ""
        self.block_e.setText(txt)
        self.block_e.setCursorPosition(0)
        self.initial_load = False

    def build_block(self):
        data = self.collect_table_data()
        txt = self.validator.convert_from_obdict(data)
        if txt:
            return txt
        return ""

    def collect_table_data(self):
        data = {"command_name": self.type_s.currentText()}

        for row in range(self.tab_t.rowCount()):
            key = self.tab_t.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            val_item = self.tab_t.item(row, 1)
            if not val_item:
                continue

            val = val_item.text().strip()
            if val != "":
                data[key] = ob_value(self.schema_prop(key), val)

        return data

    def schema_prop(self, key):
        return self.base_schema.get("properties", {}).get(key, {})

    def tooltip_for(self, key):
        prop = self.schema_prop(key)

        desc = prop.get("description", "")
        typ = prop.get("type", "")
        enum = prop.get("enum", None)

        lines = []

        if desc:
            lines.append(desc)

        if typ:
            lines.append(f"Type: {typ}")

        if enum:
            lines.append("Allowed: " + ", ".join(map(str, enum)))

        return "\n".join(lines)

    def example_for(self, key):
        prop = self.schema_prop(key)
        ex = prop.get("examples", [])
        if ex:
            return ob_value(prop, str(ex[0]))
        return ""

    def rebuild_table(self, command_name, values=None):
        self.updating = True

        self.tab_t.blockSignals(True)
        self.tab_t.setRowCount(0)

        allowed = self.command_rules[command_name]["allowed"]

        visible = [x for x in allowed if x != "command_name"]

        for r, key in enumerate(visible):
            self.tab_t.insertRow(r)

            # parameter
            item0 = QTableWidgetItem(key)
            item0.setBackground(QColor(235, 235, 235))
            item0.setFlags(item0.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            item0.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            item0.setToolTip(self.tooltip_for(key))
            self.tab_t.setItem(r, 0, item0)

            # value
            val = ""
            if values and key in values:
                val = str(values[key])

            item1 = QTableWidgetItem(val)
            self.tab_t.setItem(r, 1, item1)

            # example
            item2 = QTableWidgetItem(self.example_for(key))
            item2.setBackground(QColor(235, 235, 235))
            item2.setFlags(item2.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.tab_t.setItem(r, 2, item2)

        self.tab_t.blockSignals(False)
        self.updating = False

    def block_changed(self):
        if not self.initial_load:
            self.status_l.setText("\u2699 OB changed")
            self.status_l.setStyleSheet("color: blue; font-weight: normal;")

        if self.updating:
            return

        txt = self.block_e.text()
        ob_tmp = ObsPlanParser.convert_from_string(txt)
        if ob_tmp:
            ob = ObsValidator.convert_to_obdict(ob_tmp)
            cmd = ob.get("command_name", "OBJECT")
        else:
            ob = {"command_name", "OBJECT"}
            cmd = "OBJECT"

        if cmd not in self.base_schema["properties"]["command_name"]["enum"]:
            ob = {"command_name", "OBJECT"}
            cmd = "OBJECT"

        self.updating = True
        self.type_s.setCurrentText(cmd)
        self.rebuild_table(cmd, ob)
        self.updating = False

    def command_changed(self):
        if self.updating:
            return

        cmd = self.type_s.currentText()
        current = self.collect_table_data()
        self.rebuild_table(cmd, current)

        self.refresh_block()

    def table_changed(self):
        self.status_l.setText("\u2699 OB changed")
        self.status_l.setStyleSheet("color: blue; font-weight: normal;")

        if self.updating:
            return
        self.refresh_block()

        for r in range(self.tab_t.rowCount()):
            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(QColor("white"))

    def refresh_block(self):
        self.updating = True
        txt = self.build_block()
        self.block_e.setText(txt)
        self.updating = False

    def validate_current(self):
        data = self.collect_table_data()

        result = self.validator.validate_ob(data,allowed_filters=self.parent.parent.nats_cfg[self.parent.parent.active_tel]["filter_list_names"])

        row_map = {}
        for r in range(self.tab_t.rowCount()):
            key = self.tab_t.item(r, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            row_map[key] = r

        self.tab_t.blockSignals(True)
        self.updating = True

        # clear colors
        for r in range(self.tab_t.rowCount()):
            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(QColor("white"))

        # apply colors
        for key, state in result["result"].items():
            if key not in row_map:
                continue

            r = row_map[key]
            color = QColor(217, 239, 217) if state is True else QColor(255, 180, 80)

            it = self.tab_t.item(r, 1)
            if it:
                it.setBackground(color)

        self.tab_t.blockSignals(False)
        self.updating = False

        if result["valid"]:
            self.status_l.setText("✅ Valid OB ")
            # self.status_l.setText("\u2714 Valid OB ")
            self.status_l.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_l.setText("❌ Validation errors")
            # self.status_l.setText("\u274C Validation errors")
            self.status_l.setStyleSheet("color: orange; font-weight: bold;")

        return result["valid"]
    def mkUI(self):
        grid = QGridLayout()

        r = 0
        # block line
        self.block_e = QLineEdit()
        self.block_e.setStyleSheet("background-color: skyblue; color: black;")

        if self.parent.parent.catalog_file:
            self.catalog = readCatalog(self.parent.parent.catalog_file)
            completer = QCompleter(self.catalog)
            completer.setFilterMode(QtCore.Qt.MatchContains)
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.block_e.setCompleter(completer)

        self.block_e.textChanged.connect(self.block_changed)
        grid.addWidget(self.block_e, r, 0, 1, 3)

        r += 1
        # command selector
        self.type_l = QLabel("TYPE")
        self.type_s = QComboBox()
        self.type_s.addItems(list(self.command_rules.keys()))
        self.type_s.currentTextChanged.connect(self.command_changed)

        grid.addWidget(self.type_l, r, 0)
        grid.addWidget(self.type_s, r, 1, 1, 2)

        r += 1
        # table
        self.tab_t = QTableWidget()
        self.tab_t.setColumnCount(3)
        self.tab_t.setHorizontalHeaderLabels(["Parameter", "Value", "Example"])
        self.tab_t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tab_t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tab_t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.tab_t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # zaznaczenie całego wiersza
        self.tab_t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab_t.setStyleSheet("selection-background-color: rgb(200,220,255); selection-color: black; ")
        self.tab_t.verticalHeader().hide()

        self.tab_t.itemChanged.connect(self.table_changed)

        grid.addWidget(self.tab_t, r, 0, 1, 3)

        r += 1
        # status
        self.status_l = QLabel("Not validated")
        grid.addWidget(self.status_l, r, 0, 1, 2)

        self.validate_p = QPushButton("Validate OB")
        self.validate_p.clicked.connect(self.validate_current)
        grid.addWidget(self.validate_p, r, 1, 1, 2)

        r += 1

        self.save_p = QPushButton("Save")
        self.save_p.clicked.connect(self.save_ob)
        grid.addWidget(self.save_p, r, 2)

        self.close_p = QPushButton("Close")
        self.close_p.clicked.connect(self.close)
        grid.addWidget(self.close_p, r, 0)

        self.setLayout(grid)
        self.show()

          
          
          
          
          
          
