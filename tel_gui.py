#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox





class TelGui(QWidget):
      def __init__(self, parent):
          super(TelGui, self).__init__()
          self.parent=parent
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()
          self.update()

          self.Exit_p.clicked.connect(self.parent.close)

      def update(self): 
          self.mntUt_e.setText("21:34:17")
          self.mntStat_e.setText("ready")
          self.domeStat_e.setText("moving")
          self.programStat_e.setText("Cep32")
          self.mntCovers_e.setText("Closed")
          self.domeShutter_e.setText("Closed")
          self.telLights_e.setText("Off")

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

          self.mntCovers_c=QCheckBox("MIRROR COVERS: ")
          self.mntCovers_c.setChecked(False)
          self.mntCovers_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.mntCovers_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

          self.mntCovers_e=QLineEdit() 
          self.mntCovers_e.setReadOnly(True)  
             
          # dome

          self.domeStat_l=QLabel("DOME STATUS: ")
          self.domeStat_e=QLineEdit() 
          self.domeStat_e.setReadOnly(True)
  

          self.domeShutter_c=QCheckBox("DOME SHUTTER: ")
          self.domeShutter_c.setChecked(False)
          self.domeShutter_c.setLayoutDirection(Qt.RightToLeft)
          self.domeShutter_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

          self.domeShutter_e=QLineEdit() 
          self.domeShutter_e.setReadOnly(True)                         
        
          # peripheries
          
          self.telLights_c=QCheckBox("LIGHTS: ")
          self.telLights_c.setChecked(False)
          self.telLights_c.setLayoutDirection(Qt.RightToLeft)
          self.telLights_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOnYellow.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")
      
          self.telLights_e=QLineEdit() 
          self.telLights_e.setReadOnly(True)   
                   


          self.Stop_p=QPushButton('EMERGENCY STOP')           
          self.Exit_p=QPushButton('Exit') 

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
          

          w=w+1          
          grid.addWidget(self.mntCovers_c, w,0)
          grid.addWidget(self.mntCovers_e, w,1)

          w=w+1          
          grid.addWidget(self.domeShutter_c, w,0)
          grid.addWidget(self.domeShutter_e, w,1)

          w=w+1          
          grid.addWidget(self.telLights_c, w,0)
          grid.addWidget(self.telLights_e, w,1)

          w=w+1          
          grid.addWidget(self.msg_e, w,0,3,2)

          w=w+3                   
          grid.addWidget(self.Stop_p, w,0,1,2)
          w=w+1
          grid.addWidget(self.Exit_p, w,1)

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
