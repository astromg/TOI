#!/usr/bin/env python3
import copy
import os
#----------------
# 01.08.2022
# Marek Gorski
#----------------

import uuid
import time


import ephem
import qasync as qs
from qasync import QEventLoop
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import (QMainWindow, QApplication, QAbstractItemView, QWidget, QLabel, QCheckBox, QTextEdit,
                             QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout,
                             QVBoxLayout, QTableWidget, QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame,
                             QComboBox, QProgressBar, QHeaderView)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib

from astropy.table import Table

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from pyaraucaria.coordinates import *

from toi_lib import *
from telescope_plan_generator import telescope_plan_generator as tpg
from ctc import CycleTimeCalc



class PlanGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          super().__init__(loop=loop, client_api=client_api)
          self.subscriber_delay = 1
          self.subscriber_time_of_data_tolerance = 0.5

          self.parent=parent


          #self.setStyleSheet("font-size: 11pt;")
          self.setGeometry(self.parent.plan_geometry[0],self.parent.plan_geometry[1],self.parent.plan_geometry[2],self.parent.plan_geometry[3])

          self.table_header = ["","Object","Alt @ UT","Comment"]
          self.show_seq = False      # zmienne decydujaca o wyswietlaniu co jest w kolumnach w tabelce
          self.show_ut = True
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
        if self.parent.tel_acces[self.parent.active_tel]:
            self.tpg_window = TPGWindow(self)
        else:
            txt="WARNING: U don't have control"
            self.parent.WarningWindow(txt)

    def pocisniecie_copy(self):
        if self.parent.tel_acces[self.parent.active_tel]:
             if len(self.parent.plan[self.parent.active_tel])>self.i:
                 tmp_ob = self.parent.plan[self.parent.active_tel][self.i].copy()
                 i = self.i + 1
                 self.parent.plan[self.parent.active_tel].insert(i,tmp_ob)
                 self.parent.plan[self.parent.active_tel][i]["uobi"] = str(uuid.uuid4())[:8]
                 self.parent.update_plan(self.parent.active_tel)
                 #self.repaint()
             else: print("no plan loaded") # ERROR MSG
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_addOB(self):
          pass
          #self.edit_window=AddWindow(self)
          #self.edit_window.show()
          #self.edit_window.raise_()

    def pocisniecie_edit(self):
        if self.parent.tel_acces[self.parent.active_tel]:
            if len(self.plan)>self.i:
                self.edit_window=EditWindow(self)
                self.edit_window.show()
                self.edit_window.raise_()
            else: print("no plan loaded") # ERROR MSG
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)


    def pocisniecie_addStop(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if len(self.parent.plan[self.parent.active_tel])>self.i:
                 #print("ide ***************")
                 ob = {"name": "STOP"}
                 ob["type"] = "STOP"
                 ob["block"] = "STOP"
                 self.parent.plan[self.parent.active_tel].insert(self.i+1,ob)
                 self.parent.update_plan(self.parent.active_tel)
            else: pass

        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def pocisniecie_addBell(self):
        if self.parent.tel_acces[self.parent.active_tel]:
             if len(self.plan)>self.i:
                 ob = {"name": "BELL"}
                 ob["type"] = "BELL"
                 ob["block"] = "BELL"
                 self.parent.plan[self.parent.active_tel].insert(self.i+1,ob)
                 self.parent.update_plan(self.parent.active_tel)
             else: pass

        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)



    def update_table(self):


        if not self.parent.active_tel:
            self.plan_t.clearContents()
        else:
            try:
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
                             if "type" in self.plan[i].keys():    # wait
                                if self.plan[i]["type"]=="WAIT":
                                   font=QtGui.QFont()
                                   font.setPointSize(15)
                                   txt=QTableWidgetItem("\u29D6")     # prosta klepsydra
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   txt.setForeground(QtGui.QColor("darkCyan"))
                                   self.plan_t.setItem(i,0,txt)

                             if "type" in self.plan[i].keys():     # stop
                                if self.plan[i]["type"]=="STOP":
                                   font=QtGui.QFont()
                                   font.setPointSize(20)
                                   txt=QTableWidgetItem("\u2B23")
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "type" in self.plan[i].keys():     # stop
                                if self.plan[i]["type"]=="BELL":
                                   font=QtGui.QFont()
                                   font.setPointSize(20)
                                   txt=QTableWidgetItem("\u266A")
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   #txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "meta_plan_alt" in self.plan[i].keys():
                                 alt = float(self.plan[i]["meta_plan_alt"])
                                 if alt < self.parent.cfg_alt_limits["low"] :
                                     font = QtGui.QFont()
                                     font.setPointSize(15)
                                     txt = QTableWidgetItem("\u26A0") # ostrzezenie
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("orange"))
                                     self.plan_t.setItem(i, 0, txt)

                             if "skip_alt" in self.plan[i].keys():
                                 if self.plan[i]["skip_alt"]:
                                     font = QtGui.QFont()
                                     font.setPointSize(15)
                                     txt = QTableWidgetItem("\u26A0")
                                     txt.setFont(font)
                                     txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                     txt.setForeground(QtGui.QColor("red"))
                                     self.plan_t.setItem(i, 0, txt)

                             if "ok" in self.plan[i].keys():
                                 if not self.plan[i]["ok"]:
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

                             if "skip" in self.plan[i].keys():
                                if self.plan[i]["skip"]:
                                   font=QtGui.QFont()
                                   font.setPointSize(15)
                                   #txt=QTableWidgetItem("\u26D4")  # zakaz wjazdu
                                   txt = QTableWidgetItem("\u23ED")  # nastepna piosenka
                                   txt.setFont(font)
                                   txt.setTextAlignment(QtCore.Qt.AlignCenter)
                                   #txt.setForeground(QtGui.QColor("red"))
                                   self.plan_t.setItem(i,0,txt)

                             if "uobi" in self.plan[i].keys():
                                 if self.plan[i]["uobi"] in self.done:
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
                                txt=QTableWidgetItem("\u2192")
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

                             if self.show_ob:
                                 txt=self.plan[i]["block"]
                             else:
                                 if "type" in self.plan[i].keys():
                                     if self.plan[i]["type"] == "FOCUS":
                                         txt = "FOCUS "+ self.plan[i]["name"]
                                     elif self.plan[i]["type"] == "WAIT":
                                         txt = f'{self.plan[i]["block"].split()[1]} '
                                     else:
                                         txt = self.plan[i]["name"]
                                 else:
                                     txt = self.plan[i]["name"]
                             txt=QTableWidgetItem(txt)
                             self.plan_t.setItem(i,1,txt)

                             # 2 KOLUMNA

                             if self.show_ut:
                                 txt = ""
                                 if "meta_plan_ut" in self.plan[i].keys()  and (i >= self.next_i or (i >= self.current_i and self.current_i>-1)):
                                     tmp = str(self.plan[i]["meta_plan_ut"]).split()[1]
                                     txt = tmp.split(":")[0]+":"+tmp.split(":")[1]
                                 if "meta_plan_alt" in self.plan[i].keys() and (i >= self.next_i or (i >= self.current_i and self.current_i>-1)):
                                     txt = txt + " (" + str(self.plan[i]["meta_plan_alt"])+")"
                                     alt = float(self.plan[i]["meta_plan_alt"])
                                     txt = QTableWidgetItem(txt)
                                     if alt < self.parent.cfg_alt_limits["min"]:
                                         txt.setForeground(QtGui.QColor("red"))
                                     elif alt < self.parent.cfg_alt_limits["low"]:
                                         txt.setForeground(QtGui.QColor("orange"))
                                     elif alt > self.parent.cfg_alt_limits["max"]:
                                         txt.setForeground(QtGui.QColor("red"))
                             else:
                                 txt = ""
                                 if "meta_alt" in self.plan[i].keys():
                                     txt = str(self.plan[i]["meta_alt"])
                                     txt=QTableWidgetItem(txt)

                             txt = QTableWidgetItem(txt)
                             self.plan_t.setItem(i,2,txt)

                             # 3 KOLUMNA

                             txt=QTableWidgetItem("--")
                             if self.show_seq:
                                 if "seq" in self.plan[i].keys(): txt = QTableWidgetItem(str(self.plan[i]["seq"]))
                             else:
                                 if "comment" in self.plan[i].keys(): txt = QTableWidgetItem(str(self.plan[i]["comment"]))

                             self.plan_t.setItem(i,3,txt)

                         if self.prev_i >= 0 and self.prev_i < len(self.plan):
                             self.plan_t.item(self.prev_i,1).setBackground(QtGui.QColor(230, 236, 240))
                             self.plan_t.item(self.prev_i,2).setBackground(QtGui.QColor(230, 236, 240))
                             self.plan_t.item(self.prev_i, 3).setBackground(QtGui.QColor(230, 236, 240))

                         if self.i >= 0 and self.i < len(self.plan):
                             self.plan_t.item(self.i,1).setBackground(QtGui.QColor(125, 195, 227))
                             self.plan_t.item(self.i,2).setBackground(QtGui.QColor(125, 195, 227))
                             self.plan_t.item(self.i, 3).setBackground(QtGui.QColor(125, 195, 227))

                      #self.plan_t.setColumnWidth(0,30)

                      self.plan_t.resizeColumnsToContents()
                      self.plan_t.horizontalHeader().setStretchLastSection(True)
                      if self.parent.skyGui.skyView:
                          self.parent.skyGui.skyView.updateRadar()

                      if not self.show_ob:
                          self.plan_t.blockSignals(False)
                          self.plan_t.resizeColumnsToContents()

                          for col in range(1,self.plan_t.columnCount()):
                              self.plan_t.horizontalHeader().setSectionResizeMode(col,QHeaderView.Stretch)
            except Exception as e:
                print(f"TOI plan GUI: EXCEPTION 103 {e}")

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
              if self.parent.plan[self.parent.active_tel][self.i]["type"] == "OBJECT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
              elif self.parent.plan[self.parent.active_tel][self.i]["type"] == "ZERO": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(1)
              elif self.parent.plan[self.parent.active_tel][self.i]["type"] == "DARK": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(2)
              elif self.parent.plan[self.parent.active_tel][self.i]["type"] == "SKYFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(3)
              elif self.parent.plan[self.parent.active_tel][self.i]["type"] == "DOMEFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(4)

              if "type" in self.parent.plan[self.parent.active_tel][self.i].keys():
                  if self.parent.plan[self.parent.active_tel][self.i]["type"] in ["OBJECT","DARK","ZERO","SKYFLAT","DOMEFLAT"]:
                      if "ra" in self.parent.plan[self.parent.active_tel][self.i].keys() and "dec" in self.parent.plan[self.parent.active_tel][self.i].keys():
                          self.parent.mntGui.setEq_r.setChecked(True)
                          self.parent.mntGui.nextRa_e.setText(self.plan[self.i]["ra"])
                          self.parent.mntGui.nextDec_e.setText(self.plan[self.i]["dec"])
                          self.parent.mntGui.updateNextRaDec()
                          if "name" in self.parent.plan[self.parent.active_tel][self.i].keys():
                              self.parent.mntGui.target_e.setText(self.plan[self.i]["name"])
                              self.parent.mntGui.target_e.setStyleSheet("background-color: white; color: black;")
                      if "name" in self.parent.plan[self.parent.active_tel][self.i].keys():
                          self.parent.instGui.ccd_tab.inst_object_e.setText(self.plan[self.i]["name"])
                      if "seq" in self.parent.plan[self.parent.active_tel][self.i].keys():
                          self.parent.instGui.ccd_tab.Select2_r.setChecked(True)
                          self.parent.instGui.ccd_tab.inst_Seq_e.setText(self.plan[self.i]["seq"])
                      if self.parent.plan[self.parent.active_tel][self.i]["type"] == "OBJECT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
          except Exception as e:
              print(f"PLAN GUI EXCEPTION 34: {e}")
        else:
            txt="WARNING: U don't have controll"
            self.parent.WarningWindow(txt)

    def setSkip(self):
        if self.parent.tel_acces[self.parent.active_tel]:

            if "skip" in self.parent.plan[self.parent.active_tel][self.i].keys():
                if self.parent.plan[self.parent.active_tel][self.i]["skip"]:
                    self.parent.plan[self.parent.active_tel][self.i]["skip"] = False
                else:
                    self.parent.plan[self.parent.active_tel][self.i]["skip"] = True
            else:
                self.parent.plan[self.parent.active_tel][self.i]["skip"] = True
            self.parent.update_plan(self.parent.active_tel)

        else:
            txt = "WARNING: U don't have controll"
            self.parent.WarningWindow(txt)




    def pocisniecie_headera(self,index):
          if index == 3:
              if self.show_seq:
                  self.table_header[3] = "Comment"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_seq = False
              else:
                  self.table_header[3] = "Seq"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_seq = True

          elif index == 2:
              if self.show_ut:
                  self.table_header[2] = "Alt"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_ut = False
              else:
                  self.table_header[2] = "Alt @ UT"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_ut = True

          elif index == 1:
              if self.show_ob:
                  self.table_header[1] = "Object"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_ob = False
              else:
                  self.table_header[1] = "OB"
                  self.plan_t.setHorizontalHeaderLabels(self.table_header)
                  self.show_ob = True

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
                  self.parent.check_next_i()
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
                  self.parent.check_next_i()
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
          for ob in self.plan:
              if ob["uobi"] not in self.done:
                  block = ob["block"]
                  if "\n" not in block:
                      block = block + "\n"
                  txt = txt + block
          if self.fileName:
              with open(self.fileName, "w") as plik:
                  plik.write(txt)
              txt = f"TOI: plan saved to {self.fileName} file"
              self.parent.msg(txt, "black")


    def loadPlan(self):
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
                  with open(self.fileName, "r") as plik:
                     if plik != None:
                         tmp_plan = []
                         for line in plik:
                            if len(line.strip())>0:
                               if line.strip()[0]!="#":
                                   if "TEL: zb08" in line: pass  # wprowadzic do planow jako obowiazek?
                                   line = line.strip()
                                   ob,ok,tmp1,tmp2,tmp3 = ob_parser(line,overhed=self.parent.overhed,filter_list=self.parent.filter_list)
                                   #DUPA
                                   try:
                                       if os.path.exists(self.parent.local_cfg["ctc"]["ctc_base_folder"]):
                                           self.ctc = CycleTimeCalc(telescope=self.parent.active_tel,base_folder=self.parent.local_cfg["ctc"]["ctc_base_folder"],tpg=True)
                                           self.ctc.set_rm_modes(self.parent.local_cfg["ctc"]["rm_modes_mhz"])
                                           self.ctc.set_start_rmode(2)  # tutaj zmienic defoult read mode dla teleskopu
                                           self.ctc.reset_time()
                                           ctc_ob_time = self.ctc.calc_time(ob["block"])
                                           if float(ob["slotTime"]) / float(ctc_ob_time) < 1.3 and float(ob["slotTime"]) / float(ctc_ob_time) > 0.7:
                                               ob["slotTime"] = ctc_ob_time
                                           else:
                                               print(f'TOI CTC disagreement: {ob["slotTime"]} {ctc_ob_time} {ob["block"]}')
                                   except:
                                       pass

                                   tmp_plan.append(ob)
                         self.plan[self.i+1:self.i+1] = tmp_plan
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
          self.plan_t=QTableWidget(0,4)
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
          self.add_p.setStyleSheet(" color: gray;")
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
          self.load_p=QPushButton('Load Plan')
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
          #self.add_p.clicked.connect(self.pocisniecie_addOB)
          self.addStop_p.clicked.connect(self.pocisniecie_addStop)
          self.addBell_p.clicked.connect(self.pocisniecie_addBell)

          self.setLayout(self.grid)
          self.plan_t.setColumnWidth(0,30)

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
    plan_ready_signal = QtCore.pyqtSignal(list)
    update_signal = QtCore.pyqtSignal(str)
    def __init__(self,tel,date,wind,uobi_done):
        super(TPG_Worker, self).__init__()
        self.tel=tel
        self.date=date
        self.wind=wind
        self.uobi_done=uobi_done

    def run(self):
        p = tpg(self.tel, self.date, wind=self.wind,done_uobi=self.uobi_done)

        p.Initiate()
        self.update_signal.emit("TPG init <span style='color: green;'>\u2714</span>")
        p.LoadObjects()
        self.update_signal.emit("loading objects <span style='color: green;'>\u2714</span>")
        p.MakeTime()
        self.update_signal.emit("making timeline <span style='color: green;'>\u2714</span>")
        self.update_signal.emit(f"plan start: <span style='color: green; font-weight: bold;'> {p.start_time}  </span>")
        p.CalcObject()
        self.update_signal.emit("calculating visibilities <span style='color: green;'>\u2714</span>")
        p.MaskMoon()
        self.update_signal.emit("Moon masking <span style='color: green;'>\u2714</span>")
        p.MaskWind()
        self.update_signal.emit("wind masking <span style='color: green;'>\u2714</span>")
        p.MaskPhase()
        self.update_signal.emit("database masking <span style='color: green;'>\u2714</span>")
        p.MaskStartEnd()
        p.MaskPhaseStartEnd()
        self.update_signal.emit("phase and time masking <span style='color: green;'>\u2714</span>")
        p.Waga()
        p.RandomizeList()
        self.update_signal.emit("randomization <span style='color: green;'>\u2714</span>")
        p.allocate()
        self.update_signal.emit("allocating objects <span style='color: green;'>\u2714</span>")
        p.export()
        self.update_signal.emit("<span style='color: green; font-weight: bold;'>\u2714 DONE \u2714</span>")

        self.plan_ready_signal.emit(p.plan)
        self.done_signal.emit()

class TPGWindow(QWidget):
    def __init__(self, parent):
        super(TPGWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.setMinimumSize(200,450)
        #self.setGeometry(100,100,400,100)
        self.mkUI()


    def add(self):
        tel = self.parent.parent.active_tel
        ut = self.ut_e.text()

        if self.sunset_c.isChecked():
            local_time = ephem.Date(ephem.Date(ut) - 4 * ephem.hour)
            date = [str(local_time.datetime()).split()[0]]
        else:
            date = [ut.split()[0], ut.split()[1]]
        if self.wind_c.isChecked():
            wind = float(self.wind_e.text())
        else:
            wind = None

        if self.repeat_c.checkState():
            uobi_done = self.parent.done
        else:
            uobi_done = []

        self.info_e.clear()

        self.thread = QtCore.QThread()
        self.tpg_worker = TPG_Worker(tel,date,wind,uobi_done)
        self.tpg_worker.moveToThread(self.thread)
        self.thread.started.connect(self.tpg_worker.run)
        self.tpg_worker.done_signal.connect(self.thread.quit)
        self.tpg_worker.done_signal.connect(self.tpg_worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.tpg_worker.plan_ready_signal.connect(self.get_plan)
        self.tpg_worker.update_signal.connect(self.update_status)
        #self.tpg_th.go(tel,date,wind,uobi_done)
        self.thread.start()


    def update_status(self,txt):
        if "wind masking" in txt:
            if self.wind_c.isChecked():
                self.info_e.append(txt)
                self.info_e.repaint()
        else:
            self.info_e.append(txt)
            self.info_e.repaint()

    def get_plan(self,plan):
        tmp_plan=[]
        for blok in plan:
            ob, ok, tmp1, tmp2, tmp3 = ob_parser(blok, overhed=self.parent.parent.overhed,
                                                                 filter_list=self.parent.parent.filter_list)
            #DUPA
            try:
                if os.path.exists(self.parent.parent.local_cfg["ctc"]["ctc_base_folder"]):
                    self.ctc = CycleTimeCalc(telescope=self.parent.parent.active_tel,
                                             base_folder=self.parent.parent.local_cfg["ctc"]["ctc_base_folder"], tpg=True)
                    self.ctc.set_rm_modes(self.parent.parent.local_cfg["ctc"]["rm_modes_mhz"])
                    self.ctc.set_start_rmode(2)  # tutaj zmienic defoult read mode dla teleskopu
                    self.ctc.reset_time()
                    ctc_ob_time = self.ctc.calc_time(ob["block"])
                    if float(ob["slotTime"])/float(ctc_ob_time) < 1.3 and float(ob["slotTime"])/float(ctc_ob_time) > 0.7:
                        ob["slotTime"] = ctc_ob_time
                    else:
                        print(f'TOI CTC disagreement: {ob["slotTime"]} {ctc_ob_time} {ob["block"]}')
            except:
                pass

            tmp_plan.append(ob)
        self.parent.plan[self.parent.i + 1:self.parent.i + 1] = tmp_plan
        self.parent.parent.upload_plan()
        self.parent.parent.update_plan(self.parent.parent.active_tel)

        #self.close()


    def mkUI(self):
        grid = QGridLayout()

        self.sunset_c = QCheckBox("Start at SUNSET")
        self.sunset_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.ut_e = QLineEdit("")
        self.ut_e.setText(f"{self.parent.parent.ut}")

        if ephem.Date(self.parent.parent.almanac["sunset"]) > ephem.Date(self.parent.parent.almanac["sunrise"]):
            self.sunset_c.setChecked(False)

        self.wind_c = QCheckBox("Avoid wind direction")
        self.wind_c.setChecked(False)
        self.wind_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.wind_e = QLineEdit("")
        self.wind_e.setText(f"{self.parent.parent.telemetry_wind_direction:.0f}")

        self.repeat_c = QCheckBox("Dont repeat observed objects")
        self.repeat_c.setChecked(True)
        #self.repeat_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOnGrey.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")
        self.repeat_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")


        self.add_p = QPushButton('Generate Plan')
        self.add_p.clicked.connect(self.add)
        self.close_p = QPushButton('Close')
        self.close_p.clicked.connect(lambda: self.close())

        self.info_e = QTextEdit("")
        self.info_e.isReadOnly()
        self.info_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.ut_e, 0, 0,1,2)
        grid.addWidget(self.sunset_c, 1, 0)

        grid.addWidget(self.wind_c, 2, 0)
        grid.addWidget(self.wind_e, 2, 1)

        grid.addWidget(self.repeat_c, 3, 0,1,2)

        grid.addWidget(self.info_e, 4, 0, 1, 2)

        grid.addWidget(self.add_p, 5, 1)
        grid.addWidget(self.close_p, 5, 0)


        self.setLayout(grid)
        self.show()




# #############################################
# ######### OKNO WYKRESU (PHASE) ##########
# #############################################

class PhaseWindow(QWidget):
    def __init__(self, parent):
        super(PhaseWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.setMinimumSize(800,400)
        #self.setGeometry(100,100,400,100)
        self.mkUI()
        try:
            self.get_object()
        except FileNotFoundError:
            pass
        self.refresh()


    def get_object(self):
        self.name = self.parent.plan[self.parent.i]["name"]

        if "meta_plan_ut" in self.parent.plan[self.parent.i].keys():
            self.ut = self.parent.plan[self.parent.i]["meta_plan_ut"]
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
            if plik != None:
                lc_tab = Table.read(plik, format="ascii")
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

class PlotWindow(QWidget):
    def __init__(self, parent):
        super(PlotWindow, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.setMinimumSize(1800,600)
        #self.setGeometry(100,100,400,100)
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
            color = ["c","m"]
            j=0
            for i, tmp in enumerate(self.parent.plan):
                fontsize = 9
                if j==len(color): j=0
                tmp_ok = False
                if self.parent.current_i > -1 and i >= self.parent.current_i: tmp_ok = True
                if i >= self.parent.next_i: tmp_ok = True
                if 'skip' in self.parent.plan[i].keys():
                    if self.parent.plan[i]['skip']:
                        tmp_ok = False
                if 'skip_alt' in self.parent.plan[i].keys():
                    if self.parent.plan[i]['skip_alt']:
                        tmp_ok = False
                if 'ok' in self.parent.plan[i].keys():
                    if not self.parent.plan[i]['ok']:
                        tmp_ok = False

                if tmp_ok:
                    if 'type' in self.parent.plan[i].keys():
                        if self.parent.plan[i]["type"] == "STOP":
                            self.axes.axvline(x=self.t, color="red",alpha=0.5)
                            self.axes.text(self.t,2,"STOP",rotation=90,fontsize=fontsize)

                    if "wait" in self.parent.plan[i].keys():
                        if len(self.parent.plan[i]["wait"]) > 0:
                            slotTime = float(self.parent.plan[i]["wait"])
                            self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                            self.axes.text(self.t, 3, f"WAIT {int(slotTime)}s", rotation=90, fontsize=fontsize)
                            self.t = self.t + ephem.second * slotTime


                    if "wait_ut" in self.parent.plan[i].keys():
                        if len(self.parent.plan[i]["wait_ut"]) > 0:
                            wait_ut = ephem.Date(str(ephem.Date(self.t)).split()[0] + " " + self.parent.plan[i]["wait_ut"])
                            if self.t < wait_ut:
                                self.axes.fill_betweenx([0, 2], self.t, wait_ut, color="r",
                                                        alpha=0.5)
                                self.axes.text(self.t, 3, f"WAIT UT {wait_ut}", rotation=90, fontsize=fontsize)
                                self.t = wait_ut

                    if "wait_sunset" in self.parent.plan[i].keys():
                        if len(self.parent.plan[i]["wait_sunset"]) > 0:
                            self.oca.horizon = self.parent.plan[i]["wait_sunset"]
                            wait_ut = self.oca.next_setting(ephem.Sun(), use_center=True)
                            if self.t < wait_ut:
                                self.axes.fill_betweenx([0, 2], self.t, wait_ut, color="r",
                                                        alpha=0.5)
                                self.axes.text(self.t, 3, f"WAIT SUNSET {wait_ut}", rotation=90, fontsize=fontsize)
                                self.t = wait_ut

                    if "wait_sunrise" in self.parent.plan[i].keys():
                        if len(self.parent.plan[i]["wait_sunrise"]) > 0:
                            self.oca.horizon = self.parent.plan[i]["wait_sunrise"]
                            wait_ut = self.oca.next_rising(ephem.Sun(), use_center=True)
                            if self.t < wait_ut:
                                self.axes.fill_betweenx([0, 2], self.t, wait_ut, color="r",
                                                        alpha=0.5)
                                self.axes.text(self.t, 3, f"WAIT SUNRISE {wait_ut}", rotation=90, fontsize=fontsize)
                                self.t = wait_ut

                    if "seq" in self.parent.plan[i].keys():
                        seq = self.parent.plan[i]["seq"]
                        if "slotTime" in self.parent.plan[i].keys():
                            slotTime = self.parent.plan[i]["slotTime"]
                        else:
                            slotTime = calc_slot_time(seq,self.parent.parent.overhed)
                            print("NO SLOT TIME")

                        if slotTime < 60:
                            fontsize = 2
                        if slotTime < 60 * 5:
                            fontsize = 5
                        if slotTime < 60 * 10:
                            fontsize = 7
                        else:
                            fontsize = 9

                        if "ra" in self.parent.plan[i].keys():
                            ra = self.parent.plan[i]["ra"]
                            dec = self.parent.plan[i]["dec"]
                            t_tab = []
                            alt_tab = []

                            t = self.t
                            while t <= self.t + ephem.second * slotTime:
                                az, alt = RaDec2AltAz(self.parent.parent.observatory, t, ra, dec)
                                t_tab.append(t)
                                alt_tab.append(deg_to_decimal_deg(str(alt)))
                                t = t + 10*ephem.second
                            #print(alt_tab,t_tab)
                            if i == self.parent.i:
                                self.axes.plot(t_tab, alt_tab, color="red",linestyle="-",linewidth="2")
                                self.axes.text(self.t, 93, f"{self.parent.plan[i]['name']}", color="red",rotation=90, fontsize=fontsize)
                            elif "standard" in self.parent.plan[i]["block"]:
                                self.axes.plot(t_tab, alt_tab, color="blue")
                                self.axes.text(self.t, 93, f"{self.parent.plan[i]['name']}", color="blue",rotation=90, fontsize=fontsize)
                            else:
                                self.axes.plot(t_tab,alt_tab,color=color[j])
                                self.axes.text(self.t, 93, f"{self.parent.plan[i]['name']}", color=color[j], rotation=90, fontsize=fontsize)
                            j=j+1

                        self.t = self.t + ephem.second * slotTime

            self.axes.set_ylim(0, 90)
            self.axes.set_xlim(self.t0-0.5*ephem.hour,self.t_end+0.5*ephem.hour)
            self.axes.fill_betweenx([0, 35], self.t0_dusk, self.t_end_dusk, color="grey", alpha=0.1)
            self.axes.fill_betweenx([80, 90], self.t0_dusk, self.t_end_dusk, color="grey", alpha=0.1)
            self.axes.fill_betweenx([0, 90], self.t0, self.t0_dusk, color="yellow", alpha=0.1)
            self.axes.fill_betweenx([0, 90], self.t_end_dusk, self.t_end, color="yellow", alpha=0.1)
            self.axes.axvline(x=self.t_now, color="blue")
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





    def mkUI(self):
        grid = QGridLayout()
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        #self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes = self.fig.add_subplot(111)
        grid.addWidget(self.canvas,0,0,1,2)

        self.toolbar = NavigationToolbar(self.canvas,self)
        grid.addWidget(self.toolbar, 1, 0, 1, 2)

        self.close_p = QPushButton('Close')
        grid.addWidget(self.close_p, 2, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)
        grid.setRowStretch(2, 0)

        self.setLayout(grid)



###########################################
###             ADD WINDOW              ###
###########################################

class AddWindow(QWidget):
    def __init__(self, parent):
        super(AddWindow, self).__init__()
        self.setWindowTitle("ADD OB WINDOW")
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self.mkUI()
        self.refresh()
        self.close_p.clicked.connect(lambda: self.close())
        self.change_p.clicked.connect(self.change_plan)

    def refresh(self):
        self.tab_t.disconnect()
        block = self.block_e.text()
        self.ob, self.ok, self.active, self.options, self.ob_header = ob_parser(block,
                                                                                overhed=self.parent.parent.overhed,
                                                                                filter_list=self.parent.parent.filter_list)

        if self.ok["block"]:
            self.block_e.setStyleSheet("background-color: rgb(217, 239, 217);")
        else:
            self.block_e.setStyleSheet("background-color: rgb(255, 160, 0);")
        self.update_tab()
        self.estimTime_e.setText(str(self.ob["slotTime"]))
        self.tab_t.cellChanged.connect(self.table_changed)

    def update_tab(self):
        self.tab_t.clearContents()
        j = 0
        self.keys_in_table = []
        for i, k in enumerate(self.ob.keys()):
            if self.active[k] is not False:
                if k not in ["slotTime", "block", "ok"]:
                    if self.tab_t.rowCount() <= j:
                        self.tab_t.insertRow(j)
                    txt = str(self.ob_header[k])
                    if txt == "": txt = k
                    txt = QTableWidgetItem(txt)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    if self.ok[k]:
                        txt.setBackground(QtGui.QColor(217, 239, 217))
                    elif self.active[k]:
                        txt.setBackground(QtGui.QColor(255, 160, 0))
                    self.tab_t.setItem(j, 0, txt)

                    txt = QTableWidgetItem(str(self.ob[k]))
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    if self.ok[k]:
                        txt.setBackground(QtGui.QColor(217, 239, 217))
                    elif self.active[k]:
                        txt.setBackground(QtGui.QColor(255, 160, 0))
                    self.tab_t.setItem(j, 1, txt)
                    self.keys_in_table.append(k)
                    j = j + 1

        self.tab_t.resizeColumnsToContents()
        self.tab_t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def table_changed(self, x, y):
        if self.tab_t.rowCount() > 1:
            i = -1
            txt = ""
            for i in range(self.tab_t.rowCount()):
                k = self.keys_in_table[i]
                if self.tab_t.item(i, 1):
                    if k == "comment":
                        txt = txt + self.ob_header[k] + '"' + self.tab_t.item(i, 1).text().strip() + '"'
                    else:
                        txt = txt + self.ob_header[k] + self.tab_t.item(i, 1).text().strip() + " "
            self.block_e.setText(txt)

    def change_plan(self):
        ob = {key: value for key, value in self.ob.items() if self.active.get(key)}
        self.parent.plan[self.parent.active_tel].insert(self.parent.i + 1, ob)
        txt = f"TOI: plan {self.ob['name']} changed "
        self.parent.parent.msg(txt, "black")
        self.close()

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.block_e = QLineEdit()
        i = self.parent.i
        self.block_e.setText("")
        self.block_e.textChanged.connect(self.refresh)

        w = w + 1
        grid.addWidget(self.block_e, w, 0, 1, 2)
        w = w + 1
        self.tab_t = QTableWidget(1, 2)
        grid.addWidget(self.tab_t, w, 0, 1, 2)

        w = w + 1
        self.label_l = QLabel("Estimated time [s]:")
        grid.addWidget(self.label_l, w, 0)

        self.estimTime_e = QLineEdit()
        grid.addWidget(self.estimTime_e, w, 1)

        w = w + 1
        self.change_p = QPushButton('ADD')
        grid.addWidget(self.change_p, w, 1)

        self.close_p = QPushButton('Cancel')
        grid.addWidget(self.close_p, w, 0)

        self.setLayout(grid)
        self.resize(600, 500)



# #############################################
# ######### OKNO EDYCJI #######################
# #############################################

class EditWindow(QWidget):
    def __init__(self, parent):
          super(EditWindow, self).__init__()
          self.setWindowTitle("EDIT WINDOW")
          self.parent=parent
          self.setStyleSheet("font-size: 11pt;")
          self.types = ["STOP","BELL","WAIT","OBJECT","DARK","ZERO","SKYFLAT","DOMEFLAT","FOCUS"]
          self.mkUI()
          self.refresh()
          self.close_p.clicked.connect(lambda: self.close())
          self.change_p.clicked.connect(self.change_plan)

    def refresh(self):
          self.tab_t.disconnect()
          self.type_s.disconnect()
          self.block_e.disconnect()
          block = self.block_e.text()
          self.ob,self.ok,self.active,self.options,self.ob_header = ob_parser(block,overhed=self.parent.parent.overhed,filter_list=self.parent.parent.filter_list)

          if self.ok["block"]:
              self.block_e.setStyleSheet("background-color: rgb(217, 239, 217);")
          else:
              self.block_e.setStyleSheet("background-color: rgb(255, 160, 0);")
          self.update_tab()
          self.table_changed()
          self.estimTime_e.setText(str(self.ob["slotTime"]))
          self.tab_t.cellChanged.connect(self.table_changed)
          self.type_s.currentIndexChanged.connect(self.type_changed)
          self.block_e.textChanged.connect(self.refresh)


    def type_changed(self):
          block = self.block_e.text()
          block = block.replace(block.split()[0],self.type_s.currentText())

          if block.split()[0] == "FOCUS":
              if "pos=" not in block:
                  block = block + f" pos={self.parent.parent.cfg_focuser_defpos}"
              if "seq=" in block:
                  tmp = block.split("seq=")[0]+f" seq={self.parent.parent.cfg_focuser_seq} "+block.split("seq=")[1].split(" ",1)[1]
                  block = tmp
              else:
                  block = block + f" seq={self.parent.parent.cfg_focuser_seq}"

          self.block_e.setText(block)
          #self.refresh()

    def update_tab(self):

          self.type_s.setCurrentText(self.ob["type"])

          self.tab_t.clearContents()
          self.tab_t.setRowCount(0)
          j=0
          self.keys_in_table=[]
          for i,k in enumerate(self.ob.keys()):
              if self.active[k] is not False:
                  if k not in ["slotTime","block","ok","type"]:
                      if self.tab_t.rowCount() <= j:
                          self.tab_t.insertRow(j)
                      txt = str(self.ob_header[k])
                      if txt=="": txt = k
                      txt = QTableWidgetItem(txt)
                      txt.setTextAlignment(QtCore.Qt.AlignCenter)
                      if self.ok[k]:
                          txt.setBackground(QtGui.QColor(217, 239, 217))
                      elif self.active[k]:
                          txt.setBackground(QtGui.QColor(255, 160, 0))
                      self.tab_t.setItem(j,0,txt)

                      txt = QTableWidgetItem(str(self.ob[k]))
                      txt.setTextAlignment(QtCore.Qt.AlignCenter)
                      if self.ok[k]:
                          txt.setBackground(QtGui.QColor(217, 239, 217))
                      elif self.active[k]:
                          txt.setBackground(QtGui.QColor(255, 160, 0))
                      self.tab_t.setItem(j,1,txt)
                      self.keys_in_table.append(k)
                      j = j + 1

          self.tab_t.resizeColumnsToContents()
          self.tab_t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def table_changed(self,x=None,y=None):
          if self.tab_t.rowCount()>0:
              txt = self.type_s.currentText()+" "
              i=-1
              for i in range(self.tab_t.rowCount()):
                  k = self.keys_in_table[i]
                  if self.tab_t.item(i,1):
                      if k == "type":
                          pass
                      elif k == "name" and self.tab_t.item(i, 1).text().strip() in ["ZERO","DARK","STOP","BELL"]:
                          pass
                      elif k == "comment":
                          txt = txt + self.ob_header[k] + '"' + self.tab_t.item(i, 1).text().strip() + '"'
                      elif k == "wait":
                          if len(self.tab_t.item(i,1).text().strip())>0:
                            txt = txt + self.ob_header[k] + self.tab_t.item(i, 1).text().strip() + " "
                      elif k == "wait_ut":
                          if len(self.tab_t.item(i,1).text().strip())>0:
                            txt = txt + self.ob_header[k] + self.tab_t.item(i, 1).text().strip() + " "
                      elif k == "wait_sunset":
                          if  len(self.tab_t.item(i,1).text().strip())>0:
                            txt = txt + self.ob_header[k] + self.tab_t.item(i, 1).text().strip() + " "
                      elif k == "wait_sunrise":
                          if len(self.tab_t.item(i,1).text().strip())>0:
                            txt = txt + self.ob_header[k] + self.tab_t.item(i, 1).text().strip() + " "
                      else:
                          txt = txt + self.ob_header[k] + self.tab_t.item(i,1).text().strip() + " "
              self.block_e.setText("")
              self.block_e.setText(txt)

    def change_plan(self):
        if self.parent.parent.tel_acces[self.parent.parent.active_tel]:
            ob = {key: value for key,value in self.ob.items() if self.active.get(key)}
            self.parent.plan[self.parent.i] = ob
            self.parent.parent.upload_plan()
            self.parent.parent.update_plan(self.parent.parent.active_tel)
            self.close()
        else:
            txt="WARNING: U don't have controll"
            self.parent.parent.WarningWindow(txt)

    def mkUI(self):
          grid = QGridLayout()
          w=0
          self.block_e=QLineEdit()
          i = self.parent.i
          ob = self.parent.plan[i]
          txt = ob["block"]
          if "STOP" not in txt:  # DUPA
              try:
                  if "uobi=" not in txt:
                      txt = txt + f" uobi={ob['uobi']}"
              except KeyError:
                  print("no uobi in OB")

          self.block_e.setText(txt)
          self.block_e.textChanged.connect(self.refresh)

          w=w+1
          grid.addWidget(self.block_e, w,0,1,2)

          w=w+1
          self.type_l = QLabel("TYPE")
          self.type_s = QComboBox()
          self.type_s.addItems(self.types)
          grid.addWidget(self.type_l, w, 0)
          grid.addWidget(self.type_s, w, 1)

          w=w+1
          self.tab_t=QTableWidget(1,2)
          grid.addWidget(self.tab_t, w,0,1,2)

          w=w+1
          self.label_l = QLabel("Estimated time [s]:")
          grid.addWidget(self.label_l, w, 0)

          self.estimTime_e = QLineEdit()
          grid.addWidget(self.estimTime_e, w, 1)

          w=w+1
          self.change_p=QPushButton('CHANGE')
          grid.addWidget(self.change_p, w,1)

          self.close_p=QPushButton('Cancel')
          grid.addWidget(self.close_p, w,0)

          self.setLayout(grid)
          self.resize(600, 500)
          
          
          
          
          
          
          
          
          
          
          
          
