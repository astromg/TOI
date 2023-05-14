#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------


import os
import math
import numpy
import ephem

import qasync as qs
from qasync import QEventLoop
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget

from toi_lib import *



class PlanGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

      def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          super().__init__(loop=loop, client_api=client_api)
          self.subscriber_delay = 1
          self.subscriber_time_of_data_tolerance = 0.5

          self.parent=parent

          #self.setStyleSheet("font-size: 11pt;")
          self.setGeometry(self.parent.plan_geometry[0],self.parent.plan_geometry[1],self.parent.plan_geometry[2],self.parent.plan_geometry[3])

          self.plan=[] 
          self.i=0
          self.prev_i=1
          self.next_i=0
          self.current_i=None
          self.done=[]

          self.updateUI()
          self.update_table()

      def pocisniecie_edit(self):
         if len(self.plan)>self.i:
            self.edit_window=EditWindow(self)
            self.edit_window.show()
            self.edit_window.raise_()
         else: print("no plan loaded") # ERROR MSG

      def recalc(self):
          for i,tmp in enumerate(self.plan):
             if len(self.plan)>0:
                tmp_dict=dict()
                az,alt="--","--"
                if "ra" in self.plan[i].keys():
                   ra=self.plan[i]["ra"]
                   dec=self.plan[i]["dec"]
                   az,alt = RaDec2AltAz(self.parent.observatory,ephem.now(),ra,dec)
                   alt=f"{float(arcDeg2float(str(alt))):.1f}"
                   az=f"{float(arcDeg2float(str(az))):.1f}"
                   self.plan[i]["meta_alt"]=alt
                   self.plan[i]["meta_az"]=az


      def update_table(self):
          self.recalc()
          if len(self.plan)>0:
             self.plan_t.clearContents()
             for i,tmp in enumerate(self.plan):
                 if self.plan_t.rowCount() <= i: self.plan_t.insertRow(i)

                 put_icon=False
                 if i==self.next_i:
                    font=QtGui.QFont()
                    font.setPointSize(25)
                    txt=QTableWidgetItem("\u2192")
                    txt.setFont(font)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    txt.setForeground(QtGui.QColor("blue"))
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

                 if i==self.current_i:
                    font=QtGui.QFont()
                    font.setPointSize(20)
                    txt=QTableWidgetItem("\u21BB")
                    txt.setFont(font)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    txt.setForeground(QtGui.QColor("green"))
                    self.plan_t.setItem(i,0,txt)



                 if "skip" in self.plan[i].keys():
                    if self.plan[i]["skip"]:
                       font=QtGui.QFont()
                       font.setPointSize(15)
                       txt=QTableWidgetItem("\u26D4")
                       txt.setFont(font)
                       txt.setTextAlignment(QtCore.Qt.AlignCenter)
                       self.plan_t.setItem(i,0,txt)



                 if "stop" in self.plan[i].keys():
                    if self.plan[i]["stop"]:
                       font=QtGui.QFont()
                       font.setPointSize(20)
                       txt=QTableWidgetItem("\u2B23")
                       txt.setFont(font)
                       txt.setTextAlignment(QtCore.Qt.AlignCenter)
                       txt.setForeground(QtGui.QColor("red"))
                       self.plan_t.setItem(i,0,txt)

                 if i in self.done:

                    font=QtGui.QFont()
                    font.setPointSize(15)
                    txt=QTableWidgetItem("\u2713")
                    txt.setFont(font)
                    txt.setTextAlignment(QtCore.Qt.AlignCenter)
                    txt.setForeground(QtGui.QColor("green"))
                    self.plan_t.setItem(i,0,txt)



                     
                 txt=QTableWidgetItem(self.plan[i]["name"])
                 self.plan_t.setItem(i,1,txt)

                 txt=QTableWidgetItem("--")
                 if "meta_alt" in self.plan[i].keys():
                    txt=QTableWidgetItem(str(self.plan[i]["meta_alt"]))

                 self.plan_t.setItem(i,2,txt)

                 if "seq" in self.plan[i].keys():
                    txt=QTableWidgetItem(str(self.plan[i]["seq"]))
                 self.plan_t.setItem(i,3,txt)

                 if i==self.prev_i:
                    self.plan_t.item(i,1).setBackground(QtGui.QColor(227,253,227))
                    self.plan_t.item(i,2).setBackground(QtGui.QColor(227,253,227))
                 if i==self.i:
                    self.plan_t.item(i,1).setBackground(QtGui.QColor("lightgreen"))
                    self.plan_t.item(i,2).setBackground(QtGui.QColor("lightgreen"))

          self.plan_t.setColumnWidth(0,30)


      def setNext(self):
          self.next_i=self.i
          self.update_table()
          self.parent.obsGui.main_form.skyView.updateRadar()
          if "ra" in self.plan[self.i].keys() and "dec" in self.plan[self.i].keys():
            self.parent.mntGui.setEq_r.setChecked(True)
            self.parent.mntGui.nextRa_e.setText(self.plan[self.i]["ra"])
            self.parent.mntGui.nextDec_e.setText(self.plan[self.i]["dec"])

      def setStop(self):
          if "stop" in self.plan[self.i].keys():          
             if self.plan[self.i]["stop"]:self.plan[self.i]["stop"]=False
          else: self.plan[self.i]["stop"]=True
          self.update_table()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def setSkip(self):
          if "skip" in self.plan[self.i].keys():          
             if self.plan[self.i]["skip"]:self.plan[self.i]["skip"]=False
          else: self.plan[self.i]["skip"]=True
          self.update_table()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_tabelki(self,i,j):
          self.prev_i=self.i
          self.i=i
          self.update_table()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_del(self):
          self.plan.pop(self.i)
          self.update_table()
          self.repaint()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_first(self):
          self.plan.insert(0,self.plan[self.i])
          self.plan.pop(self.i+1)
          self.i=0              
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
          self.repaint()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_last(self):
          self.plan.append(self.plan[self.i])  
          self.plan.pop(self.i)
          self.i=len(self.plan)-1
          self.update_table()  
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))      
          self.repaint()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_down(self):
          if self.i==len(self.plan)-1:
             self.plan.insert(0,self.plan[self.i])
             self.plan.pop(len(self.plan)-1)
             self.i=0     
          else:   
             self.plan[self.i],self.plan[self.i+1]=self.plan[self.i+1],self.plan[self.i]
             self.i_prev,self.i=self.i,self.i+1
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_up(self):
          if self.i==0:
             self.plan.append(self.plan[0])  
             self.plan.pop(0)
             self.i=len(self.plan)
          else:  
             self.plan[self.i],self.plan[self.i-1]=self.plan[self.i-1],self.plan[self.i]
             self.i_prev,self.i=self.i,self.i-1
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()
          self.parent.obsGui.main_form.skyView.updateRadar()

      def pocisniecie_swap(self): 
          self.plan[self.i],self.plan[self.prev_i]=self.plan[self.prev_i],self.plan[self.i]
          self.update_table()
          self.i,self.prev_i=self.prev_i,self.i
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()      
          self.parent.obsGui.main_form.skyView.updateRadar()

      def loadPlan(self):
          # With paren=widget windows had blocking itelves on aux

          print("============== DUPA 2 ================")
          print(os.environ)

          self.File_dialog = QFileDialog
          self.File_dialog.DontUseNativeDialog
          self.fileName = self.File_dialog.getOpenFileName(None,"Open file",".")[0]
          #self.fileName=str(QFileDialog.getOpenFileName(None,"Open file",".")[0])
          print(" =============================== ",self.fileName)

          self.plan=[]
          with open(self.fileName, "r") as plik:
             # plan["name","block","type","ra","dec"]
             for line in plik:
                if len(line.strip())>0:
                   if line.strip()[0]!="#":
                       if "TEL: zb08" in line: pass

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
                          self.plan.append(ob)

                       elif "OBJECT" in line:
                          ll=line.split()
                          block=line
                          ob_type=ll[0]
                          name=ll[1]
                          ra=ll[2]
                          dec=ll[3]
                          for tmp in ll:
                             if "seq=" in tmp: seq=tmp.split("=")[1]

                          ob = {"name":name}
                          ob["block"]=block
                          ob["type"]=ob_type
                          ob["seq"]=seq
                          ob["ra"]=ra
                          ob["dec"]=dec
                          self.plan.append(ob)
          self.update_table()          
          self.parent.obsGui.main_form.skyView.updateRadar()
        
          
        # =================== OKNO GLOWNE ====================================
      def updateUI(self):

          # local_dic={"WK06":'WK06 Plan Manager',"ZB08":'ZB08 Plan Manager',"JK15":'JK15 Plan Manager',"WG25":'WG25 Plan Manager',"SIM":'SIM Plan Manager'}
          local_dic={"WK06":'WK06 Plan Manager',"ZB08":'ZB08 Plan Manager',"JK15":'JK15 Plan Manager',"SIM":'SIM Plan Manager'}
          try: txt = local_dic[self.parent.active_tel]
          except: txt = "unknown Plan Manager"
          self.setWindowTitle(txt)

          tmp=QWidget()
          try: tmp.setLayout(self.grid)
          except: pass
          self.grid = QGridLayout()

          
          w=0
          self.plan_t=QTableWidget(0,4)
          self.plan_t.setHorizontalHeaderLabels(["","Object","Alt","Sequence"])
          
          self.grid.addWidget(self.plan_t, w,0,8,5)
          
          w=w+8
          self.next_p=QPushButton('Next') 
          self.stopHere_p=QPushButton('Stop')          
          self.skip_p=QPushButton('Skip')

          self.grid.addWidget(self.next_p, w,0)
          self.grid.addWidget(self.stopHere_p, w,1)
          self.grid.addWidget(self.skip_p, w,4)
          
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
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          self.grid.addWidget(self.line_l, w,0,1,5)

          w=w+1
          self.add_p=QPushButton('Add') 
          self.edit_p=QPushButton('Edit')          


          self.grid.addWidget(self.add_p, w,0)
          self.grid.addWidget(self.edit_p, w,4)
          w=w+1
          self.prog_call_e=QTextEdit()
          self.prog_call_e.setReadOnly(True)
          self.prog_call_e.setStyleSheet("background-color: rgb(235,235,235);")
          self.grid.addWidget(self.prog_call_e,w,0,3,5)

          w=w+3
          self.load_p=QPushButton('Load Plan')
          self.stop_p=QPushButton('Stop')
          self.stop_p.clicked.connect(self.parent.stop_program)
          self.resume_p=QPushButton('Resume')
          self.resume_p.clicked.connect(self.parent.resume_program)
          self.start_p=QPushButton('Start')
          self.start_p.clicked.connect(self.parent.plan_start)

          self.grid.addWidget(self.load_p, w,0)
          self.grid.addWidget(self.stop_p, w,2)
          self.grid.addWidget(self.resume_p, w,3)
          self.grid.addWidget(self.start_p, w,4)
 


          self.load_p.clicked.connect(self.loadPlan)
          self.plan_t.cellClicked.connect(self.pocisniecie_tabelki)

          self.next_p.clicked.connect(self.setNext)
          self.stopHere_p.clicked.connect(self.setStop)
          self.skip_p.clicked.connect(self.setSkip)
          self.up_p.clicked.connect(self.pocisniecie_up)
          self.down_p.clicked.connect(self.pocisniecie_down)
          self.del_p.clicked.connect(self.pocisniecie_del)
          self.first_p.clicked.connect(self.pocisniecie_first)
          self.last_p.clicked.connect(self.pocisniecie_last)
          self.swap_p.clicked.connect(self.pocisniecie_swap)

          self.edit_p.clicked.connect(self.pocisniecie_edit)
          
          self.setLayout(self.grid)

          self.plan_t.setColumnWidth(0,30)

          del tmp
          
      async def on_start_app(self):
          await self.run_background_tasks()

      @qs.asyncClose
      async def closeEvent(self, event):
          await self.stop_background_tasks()
          super().closeEvent(event)
          
          
          
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

          if ob["type"]=="MARKER":
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
          
          
          
          
          
          
          
          
          
          
          
          
          
