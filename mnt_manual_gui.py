#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox

from PyQt5.QtCore import * 



class MntManualGui(QWidget):
      def __init__(self, parent):
          super(MntManualGui, self).__init__()
          self.parent=parent
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()


      def update(self):
          self.mntAz_e.setText(self.parent.mnt_az)
          self.mntAlt_e.setText(self.parent.mnt_alt)

          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Mount Manual Controll')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          

          self.mntStat_l=QLabel("MOUNT STATUS: ")          
          self.mntStat_e=QLineEdit()           
          self.mntStat_e.setReadOnly(True)
          self.mntStat_e.setStyleSheet("background-color: rgb(233, 233, 233);")

          self.mntRa_l=QLabel("TELESCOPE RA: ")
          self.mntRa_e=QLineEdit() 
          self.mntRa_e.setReadOnly(True)         
          self.mntRa_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          self.mntDec_l=QLabel("TELESCOPE DEC: ")
          self.mntDec_e=QLineEdit() 
          self.mntDec_e.setReadOnly(True)   
          self.mntDec_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          self.mntAz_l=QLabel("TELESCOPE AZ: ")
          self.mntAz_e=QLineEdit() 
          self.mntAz_e.setReadOnly(True)         
          self.mntAz_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          self.mntAlt_l=QLabel("TELESCOPE ALT: ")
          self.mntAlt_e=QLineEdit() 
          self.mntAlt_e.setReadOnly(True)          
          self.mntAlt_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          self.mntAirmass_l=QLabel("Airmass: ")
          self.mntAirmass_e=QLineEdit() 
          self.mntAirmass_e.setReadOnly(True)        
          self.mntAirmass_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          #################


          self.nextRa_l=QLabel("NEXT RA: ")
          self.nextRa_e=QLineEdit() 
       
          
          self.nextDec_l=QLabel("NEXT DEC: ")
          self.nextDec_e=QLineEdit() 
 
          
          
          
          self.Slew_p=QPushButton('SLEW')    
          
          
          
          self.nextAz_l=QLabel("NEXT AZ: ")
          self.nextAz_e=QLineEdit() 
       
          
          self.nextAlt_l=QLabel("NEXT ALT: ")
          self.nextAlt_e=QLineEdit() 
         
          
          self.nextAirmass_l=QLabel("Next Airmass: ")
          self.nextAirmass_e=QLineEdit() 
          self.nextAirmass_e.setReadOnly(True)  
          self.nextAirmass_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        
          # dome

          self.domeAuto_c=QCheckBox("AUTO: ")
          self.domeAuto_c.setChecked(True)
          self.domeAuto_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.domeAuto_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")

          self.domeAz_l=QLabel("DOME AZ: ")
          self.domeAz_e=QLineEdit() 
          self.domeAz_e.setReadOnly(True)   
          self.domeAz_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          self.domeNextAz_e=QLineEdit()
          
          
          
          
          self.domeSet_p=QPushButton('MOVE')
        
          # peripheries
          
          self.telFocus_l=QLabel("NEXT FOCUS: ")

          self.AutoFocus_c=QCheckBox("AUTO: ")
          self.AutoFocus_c.setChecked(True)
          self.AutoFocus_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.AutoFocus_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")

          self.telFocus_e=QLineEdit() 
          self.telFocus_e.setReadOnly(True)          

          self.SetFocus_p=QPushButton('SET')


          self.telFilter_l=QLabel("FILTER: ")

          self.telFilter_s=QComboBox()
          self.telFilter_s.addItems(["V","I","u","v","b"])
          
          self.telFilter_p=QPushButton('SET')


          self.telM3_l=QLabel("M3: ")
        
          self.telM3_s=QComboBox()
          self.telM3_s.addItems(["Imager","Spectro","empty"])          
        
          self.telM3_p=QPushButton('SET')   
          
          
          self.tracking_c=QCheckBox("TRACKING: ")
          self.tracking_c.setChecked(False)
          self.tracking_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.tracking_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")
          
          
          self.guiding_c=QCheckBox("GUIDING: ")
          self.guiding_c.setChecked(False)
          self.guiding_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.guiding_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")          
          
          self.telPark_p=QPushButton('PARK')
          self.mntStop_p=QPushButton('STOP')
          
        
          grid = QGridLayout()              

          w=0   
          grid.addWidget(self.mntStat_l, w,0)
          grid.addWidget(self.mntStat_e, w,1,1,5)

          w=w+1
          grid.addWidget(self.mntRa_l, w,0)
          grid.addWidget(self.mntRa_e, w,1)
          grid.addWidget(self.nextRa_e, w,2)

          grid.addWidget(self.mntDec_l, w,3)
          grid.addWidget(self.mntDec_e, w,4) 
          grid.addWidget(self.nextDec_e, w,5)
          
          w=w+1          

          grid.addWidget(self.mntAz_l, w,0)
          grid.addWidget(self.mntAz_e, w,1)   
          grid.addWidget(self.nextAz_e, w,2)
      
          grid.addWidget(self.mntAlt_l, w,3)
          grid.addWidget(self.mntAlt_e, w,4)
          grid.addWidget(self.nextAlt_e, w,5)
          
          w=w+1
          
          w=w+1
          grid.addWidget(self.tracking_c, w,0)
          grid.addWidget(self.guiding_c, w,1)          

          grid.addWidget(self.mntAirmass_l, w,3)
          grid.addWidget(self.mntAirmass_e, w,4)
          grid.addWidget(self.nextAirmass_e, w,5)
          
          w=w+1
 
          #grid.addWidget(self.nextRa_l, w,0)
          #grid.addWidget(self.nextRa_e, w,1)

          #grid.addWidget(self.nextDec_l, w,2)
          #grid.addWidget(self.nextDec_e, w,3) 
          
          grid.addWidget(self.telPark_p, w,0)
          grid.addWidget(self.mntStop_p, w,2)
          grid.addWidget(self.Slew_p, w,4,1,2) 
          
          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          grid.addWidget(self.line_l, w,0,1,6)

          #w=w+1          

          #grid.addWidget(self.nextAz_l, w,0)
          #grid.addWidget(self.nextAz_e, w,1)      
      
          #grid.addWidget(self.nextAlt_l, w,2)
          #grid.addWidget(self.nextAlt_e, w,3)

          w=w+1        
          
          self.domeStat_l=QLabel("DOME STATUS: ")
          self.domeStat_e=QLineEdit() 
          self.domeStat_e.setReadOnly(True)    
          self.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233);")
          
          grid.addWidget(self.domeStat_l, w,0)
          grid.addWidget(self.domeStat_e, w,1,1,2)
          grid.addWidget(self.domeAuto_c, w,4)
     
          w=w+1
          grid.addWidget(self.domeAz_l, w,0)
          grid.addWidget(self.domeAz_e, w,1)
          grid.addWidget(self.domeNextAz_e, w,2)
          grid.addWidget(self.domeSet_p, w,4)

          w=w+1

          self.domeShutter_l=QLabel("SHUTTER: ")
          self.domeShutter_c=QCheckBox("")
          self.domeShutter_c.setChecked(False)
          self.domeShutter_c.setLayoutDirection(Qt.RightToLeft)
          self.domeShutter_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")

          self.domeShutter_e=QLineEdit() 
          self.domeShutter_e.setReadOnly(True)                         
        
          self.domeLights_l=QLabel("DOME LIGHTS: ")
          self.domeLights_c=QCheckBox("")
          self.domeLights_c.setChecked(False)
          self.domeLights_c.setLayoutDirection(Qt.RightToLeft)
          self.domeLights_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")
      
          self.domeLights_e=QLineEdit() 
          self.domeLights_e.setReadOnly(True)   

          w=w+1          
          grid.addWidget(self.domeShutter_l, w,0)
          grid.addWidget(self.domeShutter_e, w,1)
          grid.addWidget(self.domeShutter_c, w,3)
          

          w=w+1          
          grid.addWidget(self.domeLights_l, w,0)
          grid.addWidget(self.domeLights_e, w,1)
          grid.addWidget(self.domeLights_c, w,3)


          w=w+1
          self.line2_l=QFrame()
          self.line2_l.setFrameShape(QFrame.HLine)
          self.line2_l.setFrameShadow(QFrame.Raised)
          grid.addWidget(self.line2_l, w,0,1,6)                  

          w=w+1          
          grid.addWidget(self.telFocus_l, w,0)
          grid.addWidget(self.AutoFocus_c, w,1)
          grid.addWidget(self.telFocus_e, w,2)  
          grid.addWidget(self.SetFocus_p, w,4)  
          

          w=w+1          
          grid.addWidget(self.telFilter_l, w,0)
          grid.addWidget(self.telFilter_s, w,1)
          grid.addWidget(self.telFilter_p, w,4)

          w=w+1          
          grid.addWidget(self.telM3_l, w,0)
          grid.addWidget(self.telM3_s, w,1)
          grid.addWidget(self.telM3_p, w,4)


          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
