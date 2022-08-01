#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox




class TelGui(QWidget):
      def __init__(self, parent=None):
          super(TelGui, self).__init__()
          
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()
 
          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Telescope GUI')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          

          
          self.mntStat_l=QLabel("TELESCOPE STATUS: ")
          self.mntStat_e=QLineEdit() 
          self.mntStat_e.setReadOnly(True)

          self.programStat_l=QLabel("PROGRAM STATUS: ")
          self.programStat_e=QLineEdit() 
          self.programStat_e.setReadOnly(True)

          self.mntUt_l=QLabel("UT: ")
          self.mntUt_e=QLineEdit() 
          self.mntUt_e.setReadOnly(True)    

          self.mntRa_l=QLabel("TELESCOPE RA: ")
          self.mntRa_e=QLineEdit() 
          self.mntRa_e.setReadOnly(True)         
          
          self.mntDec_l=QLabel("TELESCOPE DEC: ")
          self.mntDec_e=QLineEdit() 
          self.mntDec_e.setReadOnly(True)   
          
          self.mntAz_l=QLabel("TELESCOPE AZ: ")
          self.mntAz_e=QLineEdit() 
          self.mntAz_e.setReadOnly(True)         
          
          self.mntAlt_l=QLabel("TELESCOPE ALT: ")
          self.mntAlt_e=QLineEdit() 
          self.mntAlt_e.setReadOnly(True)          
          
          self.mntAirmass_l=QLabel("Airmass: ")
          self.mntAirmass_e=QLineEdit() 
          self.mntAirmass_e.setReadOnly(True)                  

          self.mntCovers_c=QCheckBox("MIRROR: ")
          self.mntCovers_c.setChecked(False)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.mntCovers_c.setStyleSheet("QCheckBox::indicator:unchecked {image: url(./ToggleOn.png)}")

             

        
          # dome

          self.domeStat_l=QLabel("DOME STATUS: ")
          self.domeStat_e=QLineEdit() 
          self.domeStat_e.setReadOnly(True)

          self.domeAz_l=QLabel("DOME AZ: ")
          self.domeAz_e=QLineEdit() 
          self.domeAz_e.setReadOnly(True)         

          self.domeShutter_l=QLabel("DOME SHUTTER: ")
          self.domeShutter_e=QLineEdit() 
          self.domeShutter_e.setReadOnly(True)                         
        
          # peripheries
          
          self.telFocus_l=QLabel("FOCUS: ")
          self.telFocus_e=QLineEdit() 
          self.telFocus_e.setReadOnly(True)          

          self.telFilter_l=QLabel("FILTER: ")
          self.telFilter_e=QLineEdit() 
          self.telFilter_e.setReadOnly(True)             

          self.telM3_l=QLabel("M3: ")
          self.telM3_e=QLineEdit() 
          self.telM3_e.setReadOnly(True)           

          self.telLights_l=QLabel("LIGHTS: ")
          self.telLights_e=QLineEdit() 
          self.telLights_e.setReadOnly(True)   
          
          self.Park_p=QPushButton('Park')          


          self.Stop_p=QPushButton('EMERGENCY STOP')           

          # -------- OKNO MSG ----------------------
          self.msg_e=QTextEdit()
          self.msg_e.setReadOnly(True)
          self.msg_e.setFrameStyle(QFrame.Raised)
          self.msg_e.setStyleSheet("background-color: rgb(233, 233, 233);")          
        
        
          grid = QGridLayout()              

          w=0   
          
          grid.addWidget(self.mntUt_l, w,0)
          grid.addWidget(self.mntUt_e, w,1)
          
          w=w+1
          grid.addWidget(self.mntStat_l, w,0)
          grid.addWidget(self.mntStat_e, w,1)

          
          w=w+1          
          grid.addWidget(self.domeStat_l, w,0)
          grid.addWidget(self.domeStat_e, w,1)            

          w=w+1          
          grid.addWidget(self.programStat_l, w,0)
          grid.addWidget(self.programStat_e, w,1)     
          
          #w=w+1          
          #grid.addWidget(self.mntRa_l, w,0)
          #grid.addWidget(self.mntRa_e, w,1)

          #w=w+1          
          #grid.addWidget(self.mntDec_l, w,0)
          #grid.addWidget(self.mntDec_e, w,1)
 
          #w=w+1          
          #grid.addWidget(self.mntAz_l, w,0)
          #grid.addWidget(self.mntAz_e, w,1)

          #w=w+1          
          #grid.addWidget(self.mntAlt_l, w,0)
          #grid.addWidget(self.mntAlt_e, w,1)

          #w=w+1          
          #grid.addWidget(self.mntAirmass_l, w,0)
          #grid.addWidget(self.mntAirmass_e, w,1)

          w=w+1          
          grid.addWidget(self.mntCovers_c, w,0,1,2)

          
          
          #w=w+1          
          #grid.addWidget(self.domeAz_l, w,0)
          #grid.addWidget(self.domeAz_e, w,1)

          w=w+1          
          grid.addWidget(self.domeShutter_l, w,0)
          grid.addWidget(self.domeShutter_e, w,1)

          w=w+1          
          grid.addWidget(self.telLights_l, w,0)
          grid.addWidget(self.telLights_e, w,1)

          w=w+1          
          grid.addWidget(self.msg_e, w,0,3,2)

          w=w+3          
          grid.addWidget(self.Park_p, w,0)

          w=w+1          
          grid.addWidget(self.Stop_p, w,0,1,2)

          #w=w+1          
          #grid.addWidget(self.telFocus_l, w,0)
          #grid.addWidget(self.telFocus_e, w,1)        

          #w=w+1          
          #grid.addWidget(self.telFilter_l, w,0)
          #grid.addWidget(self.telFilter_e, w,1)

          #w=w+1          
          #grid.addWidget(self.telM3_l, w,0)
          #grid.addWidget(self.telM3_e, w,1)

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
