#!/usr/bin/env python3

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
from PyQt5.QtWidgets import (QMainWindow, QApplication, QAbstractItemView, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib

from pyaraucaria.obs_plan.obs_plan_parser import ObsPlanParser

from ob.planrunner.cycle_time_calc.cycle_time_calc import CycleTimeCalc

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from pyaraucaria.coordinates import *

from toi_lib import *

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
          self.prev_i=1             # poprzednie podswietlenie
          self.next_i=0             # zmienna funkcjonalna, nastepny obiekt do obserwacji
          self.current_i=-1         # zmienna funckjonalna, ktore ob wlasnie sie wykonuje.
          self.done=[]              # lista uuid wykonanych ob

          self.updateUI()
          self.update_table()

      def plot_plan(self):
         if len(self.plan)>self.i:
            self.plot_window=PlotWindow(self)
            self.plot_window.show()
            self.plot_window.raise_()
         else: print("no plan loaded") # ERROR MSG


      def pocisniecie_edit(self):
         if len(self.plan)>self.i:
            self.edit_window=EditWindow(self)
            self.edit_window.show()
            self.edit_window.raise_()
         else: print("no plan loaded") # ERROR MSG

      def pocisniecie_addStop(self):
         if len(self.plan)>self.i:
             print("ide ***************")
             ob = {"name": "STOP"}
             ob["type"] = "STOP"
             ob["block"] = "STOP"
             self.plan.insert(self.i+1,ob)
             self.update_table()
         else: pass

      def pocisniecie_addBell(self):
         if len(self.plan)>self.i:
             ob = {"name": "BELL"}
             ob["type"] = "BELL"
             ob["block"] = "BELL"
             self.plan.insert(self.i+1,ob)
             self.update_table()
         else: pass

      def check_next_i(self):                   # sprawdza czy nastepny obiekt nie zostal juz wykonany, albo skip
          if self.next_i > len(self.plan)-1:
              self.next_i = -1
              self.check_next_i()

          if "uid" in self.plan[self.next_i].keys():
              if self.plan[self.next_i]["uid"] in self.done:
                  self.next_i = self.next_i + 1
                  self.check_next_i()

          if "skip" in self.plan[self.next_i].keys():
              if self.plan[self.next_i]["skip"]:
                  self.next_i = self.next_i + 1
                  self.check_next_i()


      def update_plan(self):                                     # przelicza czasu planow, etc.

          #self.ctc = CycleTimeCalc(self.parent.telescope.id)   # telescope time calculator
          #self.ctc.set_start_rmode(self.parent.ccd_readoutmode)
          #self.ctc.set_telescope_start_az_alt()
          #self.ctc.set_start_time()
          #self.ctc.set_alt_limit(15)
          #self.ctc.set_skipping(True)
          #print(self.parent.telescope.id,self.parent.ccd_readoutmode)


          #print(self.ctc.calc_time({'command_name': 'OBJECT', 'args': ['FF_Aql'], 'kwargs': {'seq': '2/Ic/60,2/V/70'}}))
          #print(self.ctc.calc_time({'command_name': 'OBJECT', 'args': ['FF_Aql'], 'kwargs': {'seq': '2/Ic/60,2/V/70'}}))
          #print("CTC: ", self.ctc.time_lenght_sec)
          #print("CTC: ", self.ctc.finnish_time_utc)

          self.check_next_i()
          ob_date = str(ephem.Date(ephem.now())).split()[0]
          for i, tmp in enumerate(self.plan):
              #ob = ObsPlanParser.convert_from_string(self.plan[i]["block"])
              #print(self.ctc.calc_time(ob["subcommands"][0]))
              #print(self.ctc.time_list)
              #print("CTC: ", self.ctc.time_lenght_sec)
              #print("CTC: ", self.ctc.finnish_time_utc)


              if i == self.next_i or i == self.current_i:
                  ob_time = ephem.now()

              if "uid" not in self.plan[i].keys():               # nadaje uuid jak nie ma
                  self.plan[i]["uid"] = str(uuid.uuid4())[:8]

              if "seq" in self.plan[i].keys():
                  seq = self.plan[i]["seq"]
                  ok,err = seq_verification(seq,self.parent.filter_list)
                  if not ok:
                      if "skip" in self.plan[i].keys() and "seq_wrong" in self.plan[i].keys():
                          self.plan[i]["skip"] = True
                          self.plan[i]["seq_wrong"] = True
                  else:
                      if "seq_wrong" in self.plan[i].keys():
                          self.plan[i]["seq_wrong"] = False


              if "ra" in self.plan[i].keys():                    # liczy aktualna wysokosc na horyzontem
                  ra=self.plan[i]["ra"]
                  dec=self.plan[i]["dec"]
                  az,alt = RaDec2AltAz(self.parent.observatory,ephem.now(),ra,dec)
                  alt=f"{deg_to_decimal_deg(str(alt)):.1f}"
                  az=f"{deg_to_decimal_deg(str(az)):.1f}"
                  self.plan[i]["meta_alt"]=alt
                  self.plan[i]["meta_az"]=az

              # liczy planowana wysokosc nad horyzontem
              tmp_ok = False
              if self.current_i > -1 and i >= self.current_i:
                  tmp_ok = True
              if self.next_i > -1 and i >= self.next_i:
                  tmp_ok = True
              if tmp_ok:
                  if "wait_ut" in self.plan[i].keys():
                      wait_ut = ephem.Date(ob_date+" "+self.plan[i]["wait_ut"])
                      if ob_time < wait_ut:
                          ob_time =  wait_ut
                  self.plan[i]["meta_plan_ut"] = str(ephem.Date(ob_time))
                  if "ra" in self.plan[i].keys():
                      ra = self.plan[i]["ra"]
                      dec = self.plan[i]["dec"]
                      az, alt = RaDec2AltAz(self.parent.observatory, ob_time, ra, dec)
                      alt = f"{deg_to_decimal_deg(str(alt)):.1f}"
                      az = f"{deg_to_decimal_deg((str(az))):.1f}"
                      self.plan[i]["meta_plan_alt"] = alt
                      self.plan[i]["meta_plan_az"] = az
                      if float(alt) < 0 or float(alt) > 80:
                          self.plan[i]["skip"] = True
                  if "wait" in self.plan[i].keys():
                      ob_time =  ob_time + ephem.second * float(self.plan[i]["wait"])
                  if self.plan[i]["uid"] in self.done:
                      ob_time = ob_time
                  else:
                      slotTime = 0
                      if "slotTime" in self.plan[i].keys():
                          slotTime = self.plan[i]["slotTime"]
                          ob_time = ob_time + ephem.second * slotTime



      def update_table(self):
          t0 = time.time()
          t1=0
          if len(self.plan)>0:



             self.update_plan()

             t1 = time.time() - t0

             self.plan_t.clearContents()
             self.plan_t.blockSignals(True)
             for i,tmp in enumerate(self.plan):
                 if self.plan_t.rowCount() <= i: self.plan_t.insertRow(i)

                 # IKONKI

                 if "uid" in self.plan[i].keys():
                     if self.plan[i]["uid"] in self.done:

                         font=QtGui.QFont()
                         font.setPointSize(15)
                         txt=QTableWidgetItem("\u2713")
                         txt.setFont(font)
                         txt.setTextAlignment(QtCore.Qt.AlignCenter)
                         txt.setForeground(QtGui.QColor("green"))
                         self.plan_t.setItem(i,0,txt)

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


                 if "skip" in self.plan[i].keys():
                    if self.plan[i]["skip"]:
                       font=QtGui.QFont()
                       font.setPointSize(15)
                       txt=QTableWidgetItem("\u26D4")
                       txt.setFont(font)
                       txt.setTextAlignment(QtCore.Qt.AlignCenter)
                       self.plan_t.setItem(i,0,txt)

                 if "meta_plan_alt" in self.plan[i].keys():
                     alt = float(self.plan[i]["meta_plan_alt"])
                     if alt < 0 :
                         font = QtGui.QFont()
                         font.setPointSize(15)
                         txt = QTableWidgetItem("\u26A0")
                         txt.setFont(font)
                         txt.setTextAlignment(QtCore.Qt.AlignCenter)
                         txt.setForeground(QtGui.QColor("red"))
                         self.plan_t.setItem(i, 0, txt)
                     elif alt < 35 :
                         font = QtGui.QFont()
                         font.setPointSize(15)
                         txt = QTableWidgetItem("\u26A0")
                         txt.setFont(font)
                         txt.setTextAlignment(QtCore.Qt.AlignCenter)
                         txt.setForeground(QtGui.QColor("orange"))
                         if "skip" in self.plan[i].keys():
                            if self.plan[i]["skip"]:
                                 txt = QTableWidgetItem("\u26D4")  # aby jednak wstawil ikonke skip jak trzeba
                         self.plan_t.setItem(i, 0, txt)
                     elif alt > 80 :
                         font = QtGui.QFont()
                         font.setPointSize(15)
                         txt = QTableWidgetItem("\u26A0")
                         txt.setFont(font)
                         txt.setTextAlignment(QtCore.Qt.AlignCenter)
                         txt.setForeground(QtGui.QColor("red"))
                         self.plan_t.setItem(i, 0, txt)


                 if "seq_wrong" in self.plan[i].keys():
                     if self.plan[i]["seq_wrong"]:
                         font = QtGui.QFont()
                         font.setPointSize(15)
                         txt = QTableWidgetItem("\u2692")
                         txt.setFont(font)
                         txt.setTextAlignment(QtCore.Qt.AlignCenter)
                         txt.setForeground(QtGui.QColor("red"))
                         self.plan_t.setItem(i, 0, txt)

                 if "type" in self.plan[i].keys():    # wait
                    if self.plan[i]["type"]=="WAIT":
                       font=QtGui.QFont()
                       font.setPointSize(15)
                       txt=QTableWidgetItem("\u29D6")
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

                 if i==self.current_i:          # aktualnie robiony
                    font=QtGui.QFont()
                    font.setPointSize(20)
                    txt=QTableWidgetItem("\u21BB")
                    txt.setFont(font)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    txt.setForeground(QtGui.QColor("blue"))
                    self.plan_t.setItem(i,0,txt)

                 if i==self.next_i and self.current_i<0:    # nastepmy
                    font=QtGui.QFont()
                    font.setPointSize(25)
                    txt=QTableWidgetItem("\u2192")
                    txt.setFont(font)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    txt.setForeground(QtGui.QColor("blue"))
                    self.plan_t.setItem(i,0,txt)

                 # 1 KOLUMNA

                 if self.show_ob:
                     txt=self.plan[i]["block"]
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
                         if alt < 0:
                             txt.setForeground(QtGui.QColor("red"))
                         elif alt < 35:
                             txt.setForeground(QtGui.QColor("orange"))
                         elif alt > 80:
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



                 #if i==self.prev_i:
                    #self.plan_t.item(i,1).setBackground(QtGui.QColor(230, 236, 240))
                    #self.plan_t.item(i,2).setBackground(QtGui.QColor(230, 236, 240))
                    #self.plan_t.item(i, 3).setBackground(QtGui.QColor(230, 236, 240))
                 #if i==self.i:
                    #self.plan_t.item(i,1).setBackground(QtGui.QColor(125, 195, 227))
                    #self.plan_t.item(i,2).setBackground(QtGui.QColor(125, 195, 227))
                    #self.plan_t.item(i, 3).setBackground(QtGui.QColor(125, 195, 227))



             if self.prev_i > 0:
                 self.plan_t.item(self.prev_i,1).setBackground(QtGui.QColor(230, 236, 240))
                 self.plan_t.item(self.prev_i,2).setBackground(QtGui.QColor(230, 236, 240))
                 self.plan_t.item(self.prev_i, 3).setBackground(QtGui.QColor(230, 236, 240))

             if self.i >= 0:
                 self.plan_t.item(self.i,1).setBackground(QtGui.QColor(125, 195, 227))
                 self.plan_t.item(self.i,2).setBackground(QtGui.QColor(125, 195, 227))
                 self.plan_t.item(self.i, 3).setBackground(QtGui.QColor(125, 195, 227))

          #self.plan_t.setColumnWidth(0,30)

          self.plan_t.resizeColumnsToContents()
          self.plan_t.horizontalHeader().setStretchLastSection(True)
          t2 = time.time() - t0
          self.parent.obsGui.main_form.skyView.updateRadar()
          t3 = time.time() - t0
          #print("time: ",t1,t2,t3)
          self.plan_t.blockSignals(False)


      def setNext(self):
          self.next_i=self.i
          self.update_table()


      def import_to_manuall(self):                  # uzupelnia nazwe i wspolrzedne w oknie manual

          if self.plan[self.i]["type"] == "OBJECT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)
          elif self.plan[self.i]["type"] == "ZERO": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(1)
          elif self.plan[self.i]["type"] == "DARK": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(2)
          elif self.plan[self.i]["type"] == "SKYFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(3)
          elif self.plan[self.i]["type"] == "DOMEFLAT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(4)

          if "type" in self.plan[self.i].keys():
              if self.plan[self.i]["type"] in ["OBJECT","DARK","ZERO","SKYFLAT","DOMEFLAT"]:
                  if "ra" in self.plan[self.i].keys() and "dec" in self.plan[self.i].keys():
                      self.parent.mntGui.setEq_r.setChecked(True)
                      self.parent.mntGui.nextRa_e.setText(self.plan[self.i]["ra"])
                      self.parent.mntGui.nextDec_e.setText(self.plan[self.i]["dec"])
                      self.parent.mntGui.updateNextRaDec()
                      if "name" in self.plan[self.i].keys():
                          self.parent.mntGui.target_e.setText(self.plan[self.i]["name"])
                          self.parent.mntGui.target_e.setStyleSheet("background-color: white; color: black;")
                  if "name" in self.plan[self.i].keys():
                      self.parent.instGui.ccd_tab.inst_object_e.setText(self.plan[self.i]["name"])
                  if "seq" in self.plan[self.i].keys():
                      self.parent.instGui.ccd_tab.Select2_r.setChecked(True)
                      self.parent.instGui.ccd_tab.inst_Seq_e.setText(self.plan[self.i]["seq"])
                  if self.plan[self.i]["type"] == "OBJECT": self.parent.instGui.ccd_tab.inst_Obtype_s.setCurrentIndex(0)




      def setSkip(self):
          if "skip" in self.plan[self.i].keys():          
             if self.plan[self.i]["skip"]:self.plan[self.i]["skip"]=False
          else: self.plan[self.i]["skip"]=True
          self.update_table()

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

      def pocisniecie_del(self):
          if self.i != self.current_i:
              if self.i < self.current_i: self.current_i = self.current_i - 1
              if self.i < self.next_i: self.next_i = self.next_i - 1
              self.plan.pop(self.i)
              self.update_table()
              self.repaint()

      def pocisniecie_first(self):
          if self.i != self.current_i:
              self.plan.insert(0,self.plan[self.i])
              self.plan.pop(self.i+1)
              if self.i > self.current_i and self.current_i>-1:
                  self.current_i = self.current_i + 1
                  self.next_i = self.next_i + 1
                  self.check_next_i()
              self.i=self.i+1
              if self.i+1>len(self.plan): self.i=self.i-1
              self.update_table()
              #self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              self.repaint()

      def pocisniecie_last(self):
          if self.i != self.current_i:
              self.plan.append(self.plan[self.i])
              self.plan.pop(self.i)
              if self.i < self.current_i and self.current_i>-1:
                  self.current_i = self.current_i - 1
                  self.next_i = self.next_i - 1
                  self.check_next_i()
              self.update_table()
              #self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              self.repaint()

      def pocisniecie_up(self):
          if self.i != self.current_i:
              if self.i - 1 == self.current_i:
                  self.current_i = self.current_i + 1
                  self.next_i = self.next_i + 1
              if self.i==0:
                  self.plan.append(self.plan[0])
                  self.plan.pop(0)
                  self.i=len(self.plan)-1
              else:
                  self.plan[self.i],self.plan[self.i-1]=self.plan[self.i-1],self.plan[self.i]
                  self.i=self.i-1
              self.update_table()
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              self.repaint()

      def pocisniecie_down(self):
          if self.i != self.current_i:
              if self.i + 1 == self.current_i:
                  self.current_i = self.current_i -1
                  self.next_i = self.next_i - 1
              if self.i==len(self.plan)-1:
                  self.plan.insert(0,self.plan[self.i])
                  self.plan.pop(len(self.plan)-1)
                  self.i=0
              else:
                  self.plan[self.i],self.plan[self.i+1]=self.plan[self.i+1],self.plan[self.i]
                  self.i=self.i+1
              self.update_table()
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              self.repaint()


      def pocisniecie_swap(self):
          if self.i != self.current_i and self.prev_i != self.current_i:
              self.plan[self.i],self.plan[self.prev_i]=self.plan[self.prev_i],self.plan[self.i]
              self.update_table()
              self.i,self.prev_i=self.prev_i,self.i
              self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
              self.repaint()

      def loadPlan(self):

          # ob["name","block","type","ra","dec","seq","comment"]
          # ob["wait","wait_ut","wait_sunset","wait_sunrise"]
          # [meta_alt,meta_az,meta_plan_ut,meta_plan_alt,meta_plan_az,skip]

          if self.parent.active_tel == None:
              self.parent.WarningWindow("WARNING: Ok, but first select the telescope!")
              return
          self.File_dialog = QFileDialog()
          self.fileName = self.File_dialog.getOpenFileName(None,"Open file")[0]

          if self.fileName:
              self.plan = []
              self.done = []
              self.i = 0
              self.prev_i = -1
              self.next_i = 0
              self.current_i = -1

              with open(self.fileName, "r") as plik:
                 if plik != None:
                     for line in plik:
                        if len(line.strip())>0:
                           if line.strip()[0]!="#":
                               if "TEL: zb08" in line: pass  # wprowadzic do planow jako obowiazek?

                               elif "STOP" in line:
                                   ob = {"name":"STOP"}
                                   ob["type"]="STOP"
                                   ob["block"]=line
                                   self.plan.append(ob)

                               elif "BELL" in line:
                                   ob = {"name":"BELL"}
                                   ob["type"]="BELL"
                                   ob["block"]=line
                                   self.plan.append(ob)


                               elif "WAIT" in line:
                                   ll=line.split()
                                   name = ll[1]
                                   ob = {"name":name}
                                   ob["type"]="WAIT"
                                   ob["block"]=line
                                   if "wait=" in line: ob["wait"]=line.split("wait=")[1].split()[0]
                                   if "ut=" in line: ob["wait_ut"] = line.split("ut=")[1].split()[0]
                                   if "sunset=" in line: ob["wait_sunset"] = line.split("sunset=")[1].split()[0]
                                   if "sunrise=" in line: ob["wait_sunrise"] = line.split("sunrise=")[1].split()[0]
                                   self.plan.append(ob)

                               elif "DOMEFLAT" in line:
                                  ll=line.split()
                                  block=line
                                  ob_type=ll[0]
                                  name=ll[0]
                                  for tmp in ll:
                                     if "seq=" in tmp: seq=tmp.split("=")[1]

                                  ob = {"name":name}
                                  ob["block"]=block
                                  ob["type"]=ob_type
                                  ob["seq"]=seq
                                  ob["slotTime"] = calc_slot_time(seq,self.parent.overhed)
                                  self.plan.append(ob)

                               elif "SKYFLAT" in line:
                                  ll=line.split()
                                  block=line
                                  ob_type=ll[0]
                                  name=ll[0]
                                  for tmp in ll:
                                     if "seq=" in tmp: seq=tmp.split("=")[1]

                                  ob = {"name":name}
                                  ob["block"]=block
                                  ob["type"]=ob_type
                                  ob["seq"]=seq
                                  ob["slotTime"] = calc_slot_time(seq,self.parent.overhed)
                                  self.plan.append(ob)

                               elif "ZERO" in line:
                                  ll=line.split()
                                  block=line
                                  ob_type=ll[0]
                                  name=ll[0]
                                  for tmp in ll:
                                     if "seq=" in tmp: seq=tmp.split("=")[1]

                                  ob = {"name":name}
                                  ob["block"]=block
                                  ob["type"]=ob_type
                                  ob["seq"]=seq
                                  ob["slotTime"] = calc_slot_time(seq,self.parent.overhed)
                                  self.plan.append(ob)

                               elif "DARK" in line:
                                  ll=line.split()
                                  block=line
                                  ob_type=ll[0]
                                  name=ll[0]
                                  for tmp in ll:
                                     if "seq=" in tmp: seq=tmp.split("=")[1]

                                  ob = {"name":name}
                                  ob["block"]=block
                                  ob["type"]=ob_type
                                  ob["seq"]=seq
                                  ob["slotTime"] = calc_slot_time(seq,self.parent.overhed)
                                  self.plan.append(ob)

                               elif "OBJECT" in line:
                                  ll=line.split()
                                  block=line
                                  ob_type=ll[0]
                                  name=ll[1]
                                  ra=ll[2]
                                  dec=ll[3]

                                  ob = {"name":name}
                                  ob["block"]=block
                                  ob["type"]=ob_type
                                  ob["ra"]=ra
                                  ob["dec"]=dec

                                  if "seq=" in line:
                                      seq=line.split("seq=")[1].split()[0]
                                      ob["seq"] = seq
                                      ob["slotTime"] = calc_slot_time(seq,self.parent.overhed)

                                  if "comment=" in line:
                                      ob["comment"] = line.split("comment=")[1].split("\"")[1]

                                  self.plan.append(ob)
          self.update_table()          

        
          
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
          self.plan_t=QTableWidget(0,4)
          self.plan_t.setHorizontalHeaderLabels(self.table_header)
          self.plan_t.setSelectionMode(QAbstractItemView.NoSelection)
          self.plan_t.verticalHeader().hide()
          self.plan_t.setStyleSheet("selection-background-color: green;")

          self.grid.addWidget(self.plan_t, w,0,8,5)
          
          w=w+8
          self.import_p = QPushButton('\u2B05 Import to MANUAL')
          self.plotPlan_p = QPushButton('Plot Plan')
          self.grid.addWidget(self.import_p, w, 0,1,3)
          self.grid.addWidget(self.plotPlan_p, w, 4, 1, 1)

          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)



          w=w+1
          self.next_p=QPushButton('NEXT \u2192')
          self.skip_p=QPushButton('SKIP \u26D4')

          self.grid.addWidget(self.next_p, w,0)
          self.grid.addWidget(self.skip_p, w, 4)

          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)

          w=w+1
          self.addStop_p=QPushButton()
          self.addStop_p.setText("STOP \u2B23")
          self.addBell_p = QPushButton('BELL \u266A')
          self.add_p=QPushButton('Add OB')
          self.add_p.setStyleSheet(" color: gray;")
          self.edit_p=QPushButton('Edit OB')
          self.edit_p.setStyleSheet(" color: gray;")

          self.grid.addWidget(self.addStop_p, w,0)
          self.grid.addWidget(self.addBell_p, w, 1)
          self.grid.addWidget(self.add_p, w,3)
          self.grid.addWidget(self.edit_p, w, 4)

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
          self.delAll_p.setStyleSheet("color: gray;")
          self.down_p=QPushButton('Down')          
          self.last_p=QPushButton('Last')

          self.grid.addWidget(self.delAll_p, w,0)
          self.grid.addWidget(self.down_p, w,2)
          self.grid.addWidget(self.last_p, w,4)

          w=w+1
          self.ob_l=QLabel("current OB:")
          self.ob_e=QLineEdit("")
          self.ob_e.setReadOnly(True)
          self.ob_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.grid.addWidget(self.ob_l, w,0)
          self.grid.addWidget(self.ob_e, w,1,1,4)

          w=w+1
          self.prog_call_e=QTextEdit()
          self.prog_call_e.setReadOnly(True)
          self.prog_call_e.setStyleSheet("background-color: rgb(235,235,235);")
          self.grid.addWidget(self.prog_call_e,w,0,3,5)

          w=w+3
          self.load_p=QPushButton('Load Plan')
          self.stop_p=QPushButton('Stop')

          self.resume_p=QPushButton('Resume')
          self.start_p=QPushButton('Start')

          self.grid.addWidget(self.load_p, w,0)
          self.grid.addWidget(self.stop_p, w,2)
          self.grid.addWidget(self.resume_p, w,3)
          self.grid.addWidget(self.start_p, w,4)

          self.stop_p.clicked.connect(self.parent.stop_program)
          self.resume_p.clicked.connect(self.parent.resume_program)
          self.start_p.clicked.connect(self.parent.plan_start)

          self.load_p.clicked.connect(self.loadPlan)
          self.plan_t.cellClicked.connect(self.pocisniecie_tabelki)
          self.plan_t.horizontalHeader().sectionClicked.connect(self.pocisniecie_headera)

          self.import_p.clicked.connect(self.import_to_manuall)
          self.plotPlan_p.clicked.connect(self.plot_plan)
          self.next_p.clicked.connect(self.setNext)
          self.skip_p.clicked.connect(self.setSkip)
          self.up_p.clicked.connect(self.pocisniecie_up)
          self.down_p.clicked.connect(self.pocisniecie_down)
          self.del_p.clicked.connect(self.pocisniecie_del)
          self.first_p.clicked.connect(self.pocisniecie_first)
          self.last_p.clicked.connect(self.pocisniecie_last)
          self.swap_p.clicked.connect(self.pocisniecie_swap)
          self.edit_p.clicked.connect(self.pocisniecie_edit)
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
          super().closeEvent(event)


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
                if tmp_ok:
                    if 'type' in self.parent.plan[i].keys():
                        if self.parent.plan[i]["type"] == "STOP":
                            self.axes.axvline(x=self.t, color="red",alpha=0.5)
                            self.axes.text(self.t,2,"STOP",rotation=90,fontsize=fontsize)

                    if "wait" in self.parent.plan[i].keys():
                        slotTime = float(self.parent.plan[i]["wait"])
                        self.axes.fill_betweenx([0, 2], self.t, self.t+ephem.second*slotTime, color="r", alpha=0.5)
                        self.axes.text(self.t, 3, f"WAIT {int(slotTime)}s", rotation=90, fontsize=fontsize)
                        self.t = self.t + ephem.second * slotTime

                    if "seq" in self.parent.plan[i].keys():
                        print(self.parent.plan[i])
                        seq = self.parent.plan[i]["seq"]
                        slotTime = calc_slot_time(seq,self.parent.parent.overhed)

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
            xtics_labels = [str(x).split()[1].split(":")[0]+":"+str(x).split()[1].split(":")[1] for x in xtics]
            self.axes.set_xticks(xtics)
            self.axes.set_xticklabels(xtics_labels,rotation=45,minor=False)

            self.axes.set_yticks([0, 35, 80, 90])
            self.axes.set_yticklabels(["0 deg", "35 deg", "80 deg", "90 deg"])

            #self.axes.set_ylabel("altitude")
            #self.axes.set_xlabel("UT")
            self.fig.subplots_adjust(bottom=0.12,top=0.8,left=0.08,right=0.98)
            self.fig.tight_layout()

            self.canvas.draw()
            self.show()




            #    if "wait_ut" in self.parent.plan[i].keys():
            #        pass
            #         if ob_time < ephem.Date(ob_date + " " + self.plan[i]["wait_ut"]):
            #             ob_time = ephem.Date(ob_date + " " + self.plan[i]["wait_ut"])
            #     self.plan[i]["meta_plan_ut"] = str(ephem.Date(ob_time))

            #     if self.plan[i]["uid"] in self.done:
            #         ob_time = ob_time
            #    else:



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



# #############################################
# ######### OKNO EDYCJI #######################
# #############################################

class EditWindow(QWidget):
      def __init__(self, parent):
          super(EditWindow, self).__init__()
          self.parent=parent
          self.setStyleSheet("font-size: 11pt;")
          self.mkUI()
          self.refresh()
          self.close_p.clicked.connect(lambda: self.close())

      def refresh(self):
          i=self.parent.i
          ob=self.parent.plan[i]
          self.setWindowTitle(ob["type"])

          if ob["type"]=="OBJECT":
             local_keys=["type","name","ra","dec","alt","az","instrument","seq","mode","bining","subraster","defocus","tracking","guiding","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="ZERO":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="DARK":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="SKY_FLAT":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="DOME_FLAT":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="FOCUS":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="STOP":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="BELL":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          if ob["type"]=="WAIT":
             local_keys=["type","name","instrument","seq","mode","bining","subraster","comments"]
             txt=""
             for k in local_keys:
                 if k in ob.keys(): txt=txt+k+" = "+str(ob[k])+"\n"
                 else: txt=txt+"# "+k+"=\n"

          self.params_e.setText(txt)

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.params_e=QTextEdit()
          #self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          w=w+1
          grid.addWidget(self.params_e, w,0,3,2)
          w=w+3
          self.close_p=QPushButton('Close Edit')
          grid.addWidget(self.close_p, w,1)

          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
