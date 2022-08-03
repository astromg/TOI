#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

from PyQt5.QtCore import * 



class InstrumentGui(QWidget):
      def __init__(self, parent=None):
          super(InstrumentGui, self).__init__()
          
          self.font =  QtGui.QFont( "Arial", 11)
          
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
          self.inst_NditProg_n.setValue(45)
          self.inst_NditProg_n.setFormat("2/4")


          self.inst_DitProg_n=QProgressBar(self)
          self.inst_DitProg_n.setValue(75)
          self.inst_DitProg_n.setFormat("237/300")


          grid.addWidget(self.inst_NditProg_n, w,0)
          grid.addWidget(self.inst_DitProg_n, w,4)
          
          w=w+1
          self.inst_Seq_l=QLabel("Sequence:")
          self.inst_Seq_e=QLineEdit() 
          self.inst_Seq_p=QPushButton('EXECUTE')


          grid.addWidget(self.inst_Seq_l, w,0)
          grid.addWidget(self.inst_Seq_e, w,1)
          grid.addWidget(self.inst_Seq_p, w,2)
          
          w=w+1
          self.inst_Mode_l=QLabel("Mode:")
          self.inst_Mode_s=QComboBox()
          self.inst_Mode_s.addItems(["Normal","Sky","JitterBox","JitterRandom"])             

          self.inst_ccdTemp_l=QLabel("CCD TEMP.:")
          self.inst_ccdTemp_e=QLineEdit() 
          
          grid.addWidget(self.inst_Mode_l, w,0) 
          grid.addWidget(self.inst_Mode_s, w,1)          
          grid.addWidget(self.inst_ccdTemp_l, w,4)
          grid.addWidget(self.inst_ccdTemp_e, w,5)

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
          
          grid.addWidget(self.inst_Snap_p, w,0) 
          grid.addWidget(self.inst_Pause_p, w,1) 
          grid.addWidget(self.inst_Stop_p, w,2) 
          grid.addWidget(self.inst_Start_p, w,3)         

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
