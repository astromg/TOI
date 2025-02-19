#!/usr/bin/env python3

import qasync as qs
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QRadioButton, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar
from qasync import QEventLoop
from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget

class InstrumentGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

      def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          super().__init__(loop=loop, client_api=client_api)
          self.subscriber_delay = 1
          self.subscriber_time_of_data_tolerance = 0.5

          self.parent = parent
          self.setStyleSheet("font-size: 11pt;")
          self.setGeometry(self.parent.instrument_geometry[0],self.parent.instrument_geometry[1],self.parent.instrument_geometry[2],self.parent.instrument_geometry[3])
          self.updateUI()
          self.show()
          self.raise_()

      def updateUI(self):

          tmp = ""
          if self.parent.active_tel != None:
              tmp = self.parent.active_tel
          txt = tmp + " Instrument Manual Controll"
          self.setWindowTitle(txt)

          tmp=QWidget()
          try: tmp.setLayout(self.layout)
          except: pass

          self.layout = QGridLayout()
          self.setLayout(self.layout)

          self.tab=QTabWidget()

          self.ccd_tab=CCDGui(self.parent,loop=self.parent.loop, client_api=self.parent.client_api)
          self.tab.addTab(self.ccd_tab,"\U0001F534 CCD")

          self.layout.addWidget(self.tab,0,0)

          if self.parent.cfg_inst_temp != None:
              self.ccd_tab.inst_setTemp_e.setText(str(self.parent.cfg_inst_temp))
          if self.parent.cfg_inst_gain != None:
              self.ccd_tab.inst_setGain_e.addItems(self.parent.cfg_inst_gain)
          if self.parent.cfg_inst_rm != None:
              self.ccd_tab.inst_setRead_e.addItems(self.parent.cfg_inst_rm)

          del tmp
          self.parent.telescope_switch_status["instGui"] = True


      async def on_start_app(self):
          await self.run_background_tasks()

      @qs.asyncClose
      async def closeEvent(self, event):
          await self.stop_background_tasks()
          await self.stop_background_methods()
          super().closeEvent(event)


class CCDGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
      def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          super().__init__(loop=loop, client_api=client_api)

          self.parent=parent
          self.mkUI()

      def ObsTypeChanged(self):
          if self.inst_Obtype_s.currentIndex()==0:
              self.inst_object_e.setText("")
          elif self.inst_Obtype_s.currentIndex()==1:
              self.inst_object_e.setText("zero")
              self.inst_Dit_e.setText("0")
          elif self.inst_Obtype_s.currentIndex()==2:
              self.inst_object_e.setText("dark")
          elif self.inst_Obtype_s.currentIndex()==3:
              self.inst_object_e.setText("skyflat")
          elif self.inst_Obtype_s.currentIndex()==4:
              self.inst_object_e.setText("domeflat")
          else: pass                                  # nie ma Focusa bo nie da sie go zrobic w tym oknie

      def Select(self):
          if self.Select1_r.isChecked():
              self.inst_Seq_e.setText("")
              self.inst_Ndit_e.setStyleSheet("background-color: white; color: black;")
              self.inst_Dit_e.setStyleSheet("background-color: white; color: black;")
              self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          else:
              self.inst_Ndit_e.setText("")
              self.inst_Dit_e.setText("")
              self.inst_Ndit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
              self.inst_Dit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
              self.inst_Seq_e.setStyleSheet("background-color: white; color: black;")

      def Select1(self,tmp):
          self.Select1_r.setChecked(True)
          self.inst_Seq_e.setText("")
          self.inst_Ndit_e.setStyleSheet("background-color: white; color: black;")
          self.inst_Dit_e.setStyleSheet("background-color: white; color: black;")
          self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

      def Select2(self,tmp):
          self.Select2_r.setChecked(True)
          self.inst_Ndit_e.setText("")
          self.inst_Dit_e.setText("")
          self.inst_Ndit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_Dit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_Seq_e.setStyleSheet("background-color: white; color: black;")

        # =================== OKNO GLOWNE ====================================
      def mkUI(self):

          grid = QGridLayout()
          w=0   

          self.inst_object_l=QLabel("OBJECT NAME:")
          self.inst_object_e=QLineEdit() 

          self.inst_Obtype_l=QLabel("TYPE:")
          self.inst_Obtype_s=QComboBox()
          self.inst_Obtype_s.addItems(self.parent.cfg_inst_obstype)
          self.inst_Obtype_s.currentIndexChanged.connect(self.ObsTypeChanged)
          
          grid.addWidget(self.inst_object_l, w,0)
          grid.addWidget(self.inst_object_e, w,1)
          grid.addWidget(self.inst_Obtype_l, w,2)
          grid.addWidget(self.inst_Obtype_s, w,3)
        
          w=w+1
          self.inst_Ndit_l=QLabel("N:")
          self.inst_Ndit_e=QLineEdit()
          self.inst_Dit_l=QLabel("EXP TIME [s]:")
          self.inst_Dit_e=QLineEdit()
          self.Select1_r = QRadioButton("")
          self.Select1_r.setChecked(True)
          self.Select1_r.toggled.connect(self.Select)
          self.inst_Ndit_e.mousePressEvent = self.Select1  # connect
          self.inst_Dit_e.mousePressEvent = self.Select1   # connect

          grid.addWidget(self.inst_Ndit_l, w,0)
          grid.addWidget(self.inst_Ndit_e, w,1)
          grid.addWidget(self.inst_Dit_l, w,2)
          grid.addWidget(self.inst_Dit_e, w,3)
          grid.addWidget(self.Select1_r, w, 4)

          w=w+1
          self.inst_Seq_l=QLabel("Sequence:")
          self.inst_Seq_e=QLineEdit()
          self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.Select2_r = QRadioButton("")
          self.Select2_r.toggled.connect(self.Select)
          self.inst_Seq_e.mousePressEvent = self.Select2   # connect

          grid.addWidget(self.inst_Seq_l, w,0)
          grid.addWidget(self.inst_Seq_e, w,1,1,3)
          grid.addWidget(self.Select2_r, w, 4)

          w=w+1
          self.inst_NditProg_n=QProgressBar(self)
          self.inst_NditProg_n.setStyleSheet("background-color: rgb(233, 233, 233)")
          self.inst_NditProg_n.setValue(0)
          self.inst_NditProg_n.setFormat("0/1")


          self.inst_DitProg_n=QProgressBar(self)
          self.inst_DitProg_n.setStyleSheet("background-color: rgb(233, 233, 233)")

          grid.addWidget(self.inst_NditProg_n, w,0,1,2)
          grid.addWidget(self.inst_DitProg_n, w,2,1,2)
          
          w=w+1
          self.inst_Mode_l=QLabel("Mode:")
          self.inst_Mode_s=QComboBox()
          self.inst_Mode_s.addItems(self.parent.cfg_inst_mode)
          
          grid.addWidget(self.inst_Mode_l, w,0) 
          grid.addWidget(self.inst_Mode_s, w,1)          

          w=w+1
          self.inst_Bin_l=QLabel("Binning:")
          self.inst_Bin_e=QLineEdit()
          self.inst_Bin_e.setReadOnly(True)
          self.inst_Bin_s=QComboBox()
          self.inst_Bin_s.addItems(self.parent.cfg_inst_bins)
          self.inst_SetBin_p=QPushButton('Set')
          self.inst_SetBin_p.setStyleSheet(" color: gray;")
          self.inst_SetBin_p.clicked.connect(self.parent.ccd_setBin)
          
          grid.addWidget(self.inst_Bin_l, w,0) 
          grid.addWidget(self.inst_Bin_e, w,1)
          grid.addWidget(self.inst_Bin_s, w,2)
          grid.addWidget(self.inst_SetBin_p, w,3)

          w=w+1
          self.inst_Subraster_l=QLabel("Subraster:")
          self.inst_Subraster_s=QComboBox()
          self.inst_Subraster_s.addItems(self.parent.cfg_inst_subraster)
          
          grid.addWidget(self.inst_Subraster_l, w,0) 
          grid.addWidget(self.inst_Subraster_s, w,1)            


          w=w+1

          self.inst_gain_l=QLabel("GAIN:")
          self.inst_gain_e=QLineEdit()
          self.inst_gain_e.setReadOnly(True)
          self.inst_gain_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setGain_e=QComboBox()
          self.inst_setGain_p=QPushButton('Set')
          self.inst_setGain_p.clicked.connect(self.parent.ccd_setGain)

          grid.addWidget(self.inst_gain_l, w,0)
          grid.addWidget(self.inst_gain_e, w,1)
          grid.addWidget(self.inst_setGain_e, w,2)
          grid.addWidget(self.inst_setGain_p, w,3)


          w=w+1

          self.inst_read_l=QLabel("READ MODE:")
          self.inst_read_e=QLineEdit()
          self.inst_read_e.setReadOnly(True)
          self.inst_read_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setRead_e=QComboBox()
          #self.inst_setRead_e.addItems(self.parent.cfg_inst_rm)
          self.inst_setRead_p=QPushButton('Set')
          self.inst_setRead_p.clicked.connect(self.parent.ccd_setReadMode)

          grid.addWidget(self.inst_read_l, w,0)
          grid.addWidget(self.inst_read_e, w,1)
          grid.addWidget(self.inst_setRead_e, w,2)
          grid.addWidget(self.inst_setRead_p, w,3)

          
          w=w+1

          self.inst_ccdTemp_l=QLabel("CCD TEMP.:")
          self.inst_ccdTemp_e=QLineEdit()
          self.inst_ccdTemp_e.setReadOnly(True)
          self.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setTemp_e=QLineEdit()
          self.inst_setTemp_p=QPushButton('Set')
          self.inst_setTemp_p.clicked.connect(self.parent.ccd_setTemp)

          grid.addWidget(self.inst_ccdTemp_l, w,0)
          grid.addWidget(self.inst_ccdTemp_e, w,1)
          grid.addWidget(self.inst_setTemp_e, w,2)
          grid.addWidget(self.inst_setTemp_p, w,3)

          w=w+1

          self.cooler_c = QCheckBox("Cooler")
          self.cooler_c.setChecked(False)
          self.cooler_c.setLayoutDirection(Qt.RightToLeft)
          self.cooler_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
          self.cooler_c.clicked.connect(self.parent.ccd_coolerOnOf)

          grid.addWidget(self.cooler_c, w,3)

          w=w+1          
          
          self.inst_Snap_p=QPushButton('SNAP')
          self.inst_Snap_p.clicked.connect(self.parent.ccd_Snap)
          self.inst_Pause_p=QPushButton('PAUSE')
          self.inst_Pause_p.setStyleSheet(" color: gray;")
          self.inst_Stop_p=QPushButton('STOP')
          self.inst_Stop_p.clicked.connect(self.parent.ccd_stopExp)
          #self.inst_Stop_p.setStyleSheet(" color: gray;")
          self.inst_Start_p=QPushButton('START')
          self.inst_Start_p.clicked.connect(self.parent.ccd_startExp)
          
          grid.addWidget(self.inst_Snap_p, w,0) 
          grid.addWidget(self.inst_Pause_p, w,1) 
          grid.addWidget(self.inst_Stop_p, w,2) 
          grid.addWidget(self.inst_Start_p, w,3)

          self.setLayout(grid)

      async def on_start_app(self):
          await self.run_background_tasks()

      @qs.asyncClose
      async def closeEvent(self, event):
          await self.stop_background_tasks()
          await self.stop_background_methods()
          super().closeEvent(event)
          

          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
