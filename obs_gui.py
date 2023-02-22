#!/usr/bin/env python3

import math
import numpy

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from toi_lib import *

class ObsGui(QMainWindow):
      def __init__(self, parent):
          super(QMainWindow, self).__init__()
          self.parent=parent
          self.setWindowTitle('Telescope Operator Interface')
          self.main_form = MainForm(self.parent)
          self.setCentralWidget(self.main_form)
          self.resize(850,400)
          self.move(0,0)


class MainForm(QWidget):
      def __init__(self, parent):
          super(MainForm, self).__init__()
          self.parent=parent
          #self.setStyleSheet("QLabel{font-size: 10pt;}")
          self.setStyleSheet("font-size: 11pt;")
          #self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()
          self.update_table()
          self.exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())



      def update_table(self):

          self.tel_in_table=["WK06","ZB08","JK15","WG25","SIM"]
          self.dome_in_table=["Moving","Open","Close","Parked","--"]
          self.mount_in_table=["Parked","Slewing","Tracking","Guiding","Parked"]
          self.inst_in_table=["Idle","--","Reading","Exposing V","Exposing K"]
          self.program_in_table=["Sky Flats","--","Dome Flast","Cep34565","Focusing"]
          for i,txt in enumerate(self.tel_in_table):
              txt=self.tel_in_table[i]
              item=QTableWidgetItem(txt)
              self.obs_t.setItem(i,0,item)
              txt=self.dome_in_table[i]
              item=QTableWidgetItem(txt)
              self.obs_t.setItem(i,1,item)
              txt=self.mount_in_table[i]
              item=QTableWidgetItem(txt)
              self.obs_t.setItem(i,2,item)
              txt=self.inst_in_table[i]
              item=QTableWidgetItem(txt)
              self.obs_t.setItem(i,3,item)
              txt=self.program_in_table[i]
              item=QTableWidgetItem(txt)
              self.obs_t.setItem(i,4,item)


          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
          
          grid = QGridLayout()
          w=0   
          self.tic_l=QLabel("TIC not Connected")
          self.ticStatus2_l=QLabel("")
          self.ticStatus2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))

          self.control_l=QLabel("Controler:")
          self.control_e=QLineEdit("--")
          self.control_e.setReadOnly(True)
          self.takeControl_p=QPushButton('Take Control')

          grid.addWidget(self.ticStatus2_l, w,0)
          grid.addWidget(self.tic_l, w,1)
          grid.addWidget(self.control_l, w,3)
          grid.addWidget(self.control_e, w,5)
          grid.addWidget(self.takeControl_p, w,6)
          w=w+1
          self.date_l=QLabel("Date:")
          self.date_e=QLineEdit("--/--/--")
          self.date_e.setReadOnly(True)

          self.ut_l=QLabel("UT:")
          self.ut_e=QLineEdit("--:--:--")
          self.ut_e.setReadOnly(True)

          grid.addWidget(self.date_l, w,0)
          grid.addWidget(self.date_e, w,1)

          grid.addWidget(self.ut_l, w,2)
          grid.addWidget(self.ut_e, w,3)

          w=w+1

          self.ojd_l=QLabel("OJD:")
          self.ojd_e=QLineEdit("--")
          self.ojd_e.setReadOnly(True)

          self.sid_l=QLabel("SID:")
          self.sid_e=QLineEdit("--:--:--")
          self.sid_e.setReadOnly(True)

          grid.addWidget(self.ojd_l, w,0)
          grid.addWidget(self.ojd_e, w,1)

          grid.addWidget(self.sid_l, w,2)
          grid.addWidget(self.sid_e, w,3)
          
          w=w+1
          self.obs_t=QTableWidget(4,5)
          self.obs_t.setHorizontalHeaderLabels(["Telescope","Dome","Mount","Instrument","Program"])
          self.obs_t.setSelectionBehavior(QTableWidget.SelectRows)
          self.obs_t.setSelectionMode(QTableWidget.SingleSelection)
          self.obs_t.verticalHeader().hide()
          self.obs_t.setShowGrid(False)
          self.obs_t.setStyleSheet("selection-background-color: rgb(138,176,219);")
          self.obs_t.setEditTriggers(QTableWidget.NoEditTriggers)
          self.obs_t.setFixedWidth(550)           # Size
          grid.addWidget(self.obs_t, w,0,1,5)
          
          w=w+1
          self.shutdown_p=QPushButton('Shutdown')
          self.weatherStop_p=QPushButton('Weather Stop')
          self.EmStop_p=QPushButton('Emergency Stop')

          grid.addWidget(self.shutdown_p, w,0)
          grid.addWidget(self.weatherStop_p, w,1)
          grid.addWidget(self.EmStop_p, w,3)

          w=w+1
          self.msg_e=QTextEdit()
          self.msg_e.setReadOnly(True)
          self.msg_e.setStyleSheet("background-color: rgb(235,235,235);")
          grid.addWidget(self.msg_e,w,0,3,5)
          
          # #### tutaj SkyRadar  ####
          w=1
          self.skyView=SkyView()
          grid.addWidget(self.skyView, w,5,6,2)
          w=w+6
          self.exit_p = QPushButton('Exit')
          grid.addWidget(self.exit_p,w,5,1,2)


          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
# ############# SKY RADAR ################################
          
class SkyView(QWidget):
   def __init__(self):
       QWidget.__init__(self)
       #self.parent=parent
       self.mkUI()

       self.tel_az=5
       self.tel_alt=90

       self.a=[]
       self.h=[]
       self.symbol=[]

       self.silent_a=[]
       self.silent_h=[]
       self.silent_symbol=[]

       self.rmax=110
       self.marc_point=False


       self.a=[10,20,30,40,50,100,40,40,70]
       self.h=[50,50,50,50,50,30,40,40,20]
       self.symbol=["b*","b*","b*","b*","b*","ok","or","+r",".r"]
       self.alpha=[0.8,0.6,0.5,0.3,0.3,0.6,0.3,1,1]


       self.log_a=[10,20,30]
       self.log_h=[30,30,30]
       self.log_s=["k*","k*","k*"]
       self.log_alh=[0.5,0.5,0.5]

       self.update()



   def update(self):
       self.axes.clear()

       '''
       if len(self.parent.planGui.plan)>0:
          for i,tmp in enumerate(self.parent.planGui.plan):

              planAz = float(arcDeg2float(str(self.parent.planGui.plan[i]["az"])))
              planAlt = float(arcDeg2float(str(self.parent.planGui.plan[i]["alt"])))
              planAz=2*math.pi*numpy.array(planAz)/360.
              planAlt=90.-numpy.array(planAlt)

              if i<self.parent.planGui.next_i:
                 self.axes.plot(planAz,planAlt,"k*",alpha=0.3)
              elif i<self.parent.planGui.next_i+1:
                 self.axes.plot(planAz,planAlt,"b*",alpha=1.0)
              elif i<self.parent.planGui.next_i+2:
                 self.axes.plot(planAz,planAlt,"b*",alpha=0.5)
              elif i<self.parent.planGui.next_i+3:
                 self.axes.plot(planAz,planAlt,"b*",alpha=0.3)
              else:
                 self.axes.plot(planAz,planAlt,"b*",alpha=0.2)

       try:
          self.tel_az=2*math.pi*float(self.parent.mnt_az)/360.
          self.tel_alt=90.-float(self.parent.mnt_alt)
          self.axes.plot(self.tel_az,self.tel_alt,"or",alpha=1.0)
       except: pass

       try:
          nextAlt = float(self.parent.mnt.nextAlt_e.text())
          nextAz =  float(self.parent.mnt.nextAz_e.text())
          nextAz=2*math.pi*float(nextAz)/360.
          nextAlt=90.-float(nextAlt)
          self.axes.plot(nextAz,nextAlt,"gx",alpha=1.0)
       except: pass

       '''
       #if len(self.a)>0:
       #   for h,a,s,al in zip(self.h,self.a,self.symbol,self.alpha):
       #       a=2*math.pi*a/360.
       #       self.axes.plot(a, h,str(s),alpha=al)
       #       self.axes.bar(230,5, width=0.2*math.pi,bottom=90,color='g',alpha=0.05)


       self.axes.set_theta_direction(-1)
       self.axes.set_theta_zero_location('N')
       self.axes.set_ylim([0,360])
       self.axes.set_rlim([0,30])
       self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])
       self.axes.set_xticklabels(["N","E","S","W"])
       self.axes.set_rmax(self.rmax)
       self.axes.set_rticks([20,40,60,90])
       self.axes.set_yticklabels(["","","",""])
       self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)  #tutaj zmienia sie pasek ponizej horyzoontu

       self.canvas.draw()
       self.show()

# ======= Budowa okna ====================

   def mkUI(self):
       #self.setWindowTitle('FC')
       self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
       self.canvas = FigureCanvas(self.fig)
       self.axes = self.fig.add_subplot(111,polar=True)
       #self.axes.set_theta_zero_location('N')

       hbox1 = QHBoxLayout()
       hbox1.addWidget(self.canvas)

       self.vbox = QVBoxLayout()
       self.vbox.addLayout(hbox1)
       self.vbox.setSpacing(10)
       self.setLayout(self.vbox)

       #self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

       self.axes.clear()
       self.resize(400,500)
       self.canvas.draw()
       #self.axes.grid(True)
       #self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])
       #self.axes.set_yticks([20,40,60,80])
       #self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)
       #self.axes.set_rmax(self.rmax)





#  ============ Klikanie w punkciki ==========================

   def zaznaczenie(self,event):
       przetrzymywacz=1000.
       self.i=0
       if len(self.a)>0:
          a1=float(event.xdata)
          h1=float(event.ydata)
          for i,smiec in enumerate(self.a):
              #a2=self.a[i]
              a2=2*math.pi*(self.a[i])/360.
              h2=float(self.h[i])
              delta=( h1**2+h2**2-2*h1*h2*math.cos(a1-a2)  )**0.5
              if delta < przetrzymywacz:
                 self.i=i                       #indeks zaznaczonego elementu
                 przetrzymywacz=delta
          a=self.a[self.i]
          a=2*math.pi*a/360.
          self.update()
          if self.marc_point:
             self.axes.plot(a, self.h[self.i],"ro")
             self.canvas.draw()
             self.show()

          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
