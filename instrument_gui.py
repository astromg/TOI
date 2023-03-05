#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

import logging
import time

import qasync as qs
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
from qasync import QEventLoop

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from toi_lib import *


class InstrumentGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

      def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          super().__init__(loop=loop, client_api=client_api)
          self.subscriber_delay = 1
          self.subscriber_time_of_data_tolerance = 0.5

          self.parent = parent
          self.setStyleSheet("font-size: 11pt;")
          self.setGeometry(self.parent.instrument_geometry[0],self.parent.instrument_geometry[1],self.parent.instrument_geometry[2],self.parent.instrument_geometry[3])
          self.updateUI()

      def updateUI(self):

          local_dic={"WK06":'WK06 Instrument Manual Controll',"ZB08":'ZB08 Instrument Manual Controll',"JK15":'JK15 Instrument Manual Controll',"WG25":'WG25 Instrument Manual Controll',"SIM":'SIM Instrument Manual Controll'}
          try: txt = local_dic[self.parent.active_tel]
          except: txt = "unknow Instrument Manual Controll"
          self.setWindowTitle(txt)

          tmp=QWidget()
          try: tmp.setLayout(self.layout)
          except: pass

          self.layout = QGridLayout()
          self.setLayout(self.layout)

          self.tab=QTabWidget()

          self.ccd_tab=CCDGui(self.parent)
          self.tab.addTab(self.ccd_tab,"CCD")

          self.layout.addWidget(self.tab,0,0)
          del tmp


      async def on_start_app(self):
          await self.run_background_tasks()

      @qs.asyncClose
      async def closeEvent(self, event):
          await self.stop_background_tasks()
          super().closeEvent(event)


class CCDGui(QWidget):
      def __init__(self, parent):
          super(CCDGui, self).__init__()
          self.parent=parent
          self.mkUI()

        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Instrument Manual Controll')
          
          grid = QGridLayout()
          w=0   

          self.inst_object_l=QLabel("OBJECT NAME:")
          self.inst_object_e=QLineEdit() 

          self.inst_Obtype_l=QLabel("TYPE:")
          self.inst_Obtype_s=QComboBox()
          self.inst_Obtype_s.addItems(["Science","Calibration","Dark","SkyFla","DomeFlat","Zero","Focus"])         
          
          grid.addWidget(self.inst_object_l, w,0)
          grid.addWidget(self.inst_object_e, w,1)
          grid.addWidget(self.inst_Obtype_l, w,2)
          grid.addWidget(self.inst_Obtype_s, w,3)
        
          w=w+1
          self.inst_Ndit_l=QLabel("NDIT:")
          self.inst_Ndit_e=QLineEdit() 

          self.inst_Dit_l=QLabel("DIT:")
          self.inst_Dit_e=QLineEdit()   
          
          grid.addWidget(self.inst_Ndit_l, w,0)
          grid.addWidget(self.inst_Ndit_e, w,1)
          grid.addWidget(self.inst_Dit_l, w,2)
          grid.addWidget(self.inst_Dit_e, w,3)
          
          w=w+1
          self.inst_NditProg_n=QProgressBar(self)
          self.inst_NditProg_n.setValue(0)
          self.inst_NditProg_n.setFormat("0/1")


          self.inst_DitProg_n=QProgressBar(self)
          #self.inst_DitProg_n.setValue(75)
          #self.inst_DitProg_n.setFormat("237/300")


          grid.addWidget(self.inst_NditProg_n, w,0,1,2)
          grid.addWidget(self.inst_DitProg_n, w,2,1,2)
          
          w=w+1
          self.inst_Seq_l=QLabel("Sequence:")
          self.inst_Seq_e=QLineEdit() 
          self.inst_Seq_p=QPushButton('EXECUTE')


          grid.addWidget(self.inst_Seq_l, w,0)
          grid.addWidget(self.inst_Seq_e, w,1)
          grid.addWidget(self.inst_Seq_p, w,2,1,2)
          
          w=w+1
          self.inst_Mode_l=QLabel("Mode:")
          self.inst_Mode_s=QComboBox()
          self.inst_Mode_s.addItems(["Normal","Sky","JitterBox","JitterRandom"])             

          self.inst_ccdTemp_l=QLabel("CCD TEMP.:")
          self.inst_ccdTemp_e=QLineEdit() 
          
          grid.addWidget(self.inst_Mode_l, w,0) 
          grid.addWidget(self.inst_Mode_s, w,1)          
          grid.addWidget(self.inst_ccdTemp_l, w,2)
          grid.addWidget(self.inst_ccdTemp_e, w,3)

          w=w+1
          self.inst_Bin_l=QLabel("Binning:")
          self.inst_Bin_s=QComboBox()
          self.inst_Bin_s.addItems(["1x1","2x2","1x2","2x1"])             
          
          grid.addWidget(self.inst_Bin_l, w,0) 
          grid.addWidget(self.inst_Bin_s, w,1)   

          w=w+1
          self.inst_Subraster_l=QLabel("Subraster:")
          self.inst_Subraster_s=QComboBox()
          self.inst_Subraster_s.addItems(["No","Subraster1","Subraster2","Subraster3"])             
          
          grid.addWidget(self.inst_Subraster_l, w,0) 
          grid.addWidget(self.inst_Subraster_s, w,1)            
          
          w=w+1          
          
          self.inst_Snap_p=QPushButton('SNAP')
          self.inst_Pause_p=QPushButton('PAUSE')
          self.inst_Stop_p=QPushButton('STOP')
          self.inst_Start_p=QPushButton('START')
          self.inst_Start_p.clicked.connect(self.parent.ccd_startExp)
          
          grid.addWidget(self.inst_Snap_p, w,0) 
          grid.addWidget(self.inst_Pause_p, w,1) 
          grid.addWidget(self.inst_Stop_p, w,2) 
          grid.addWidget(self.inst_Start_p, w,3)

          w=w+1

          self.cooler_c = QCheckBox("Cooler")
          self.cooler_c.setChecked(False)
          self.cooler_c.setLayoutDirection(Qt.RightToLeft)
          self.cooler_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
          self.cooler_c.clicked.connect(self.parent.ccd_coolerOnOf)

          grid.addWidget(self.cooler_c, w,0)

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          

          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
