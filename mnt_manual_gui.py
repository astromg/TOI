#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox

from PyQt5.QtCore import * 



class MntManualGui(QWidget):
      def __init__(self, parent=None):
          super(MntManualGui, self).__init__()
          
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()


          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Mount Manual Controll')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          


          self.mntRa_l=QLabel("NEXT RA: ")
          self.mntRa_e=QLineEdit() 
          self.mntRa_e.setReadOnly(True)         
          
          self.mntDec_l=QLabel("NEXT DEC: ")
          self.mntDec_e=QLineEdit() 
          self.mntDec_e.setReadOnly(True)   
          
          self.Slew_p=QPushButton('SLEW')    
          
          
          
          self.mntAz_l=QLabel("NEXT AZ: ")
          self.mntAz_e=QLineEdit() 
          self.mntAz_e.setReadOnly(True)         
          
          self.mntAlt_l=QLabel("NEXT ALT: ")
          self.mntAlt_e=QLineEdit() 
          self.mntAlt_e.setReadOnly(True)          
          
          self.mntAirmass_l=QLabel("Next Airmass: ")
          self.mntAirmass_e=QLineEdit() 
          self.mntAirmass_e.setReadOnly(True)                  

        
          # dome

          self.domeAuto_c=QCheckBox("AUTO: ")
          self.domeAuto_c.setChecked(True)
          self.domeAuto_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.domeAuto_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")

          self.domeAz_l=QLabel("DOME AZ: ")
          self.domeAz_e=QLineEdit() 
          self.domeAz_e.setReadOnly(True)   
          
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
          
          
        
          grid = QGridLayout()              

          w=0   
 
          grid.addWidget(self.mntRa_l, w,0)
          grid.addWidget(self.mntRa_e, w,1)

          grid.addWidget(self.mntDec_l, w,2)
          grid.addWidget(self.mntDec_e, w,3) 
          
          grid.addWidget(self.Slew_p, w,4) 


          w=w+1          

          grid.addWidget(self.mntAz_l, w,0)
          grid.addWidget(self.mntAz_e, w,1)      
      
          grid.addWidget(self.mntAlt_l, w,2)
          grid.addWidget(self.mntAlt_e, w,3)

          w=w+1          
     
          grid.addWidget(self.domeAz_l, w,0)
          grid.addWidget(self.domeAuto_c, w,1)
          grid.addWidget(self.domeAz_e, w,2)
          grid.addWidget(self.domeSet_p, w,4)

        

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

          w=w+1
          grid.addWidget(self.tracking_c, w,0)
          grid.addWidget(self.guiding_c, w,4)
          
          w=w+1
          grid.addWidget(self.telPark_p, w,3,1,2)

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
