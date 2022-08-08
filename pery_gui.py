#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox

from PyQt5.QtCore import * 



class PeryphericalGui(QWidget):
      def __init__(self, parent):
          super(PeryphericalGui, self).__init__()
          self.parent=parent
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()
          self.update()


      def update(self):
          pass

          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Telescope Perypherical Controll')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          

          w=0   
          grid = QGridLayout()         

          self.telCovers_l=QLabel("MIRROR COVERS: ")

          self.telCovers_e=QLineEdit() 
          self.telCovers_e.setReadOnly(True)  
          self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233);")
 
          self.telCovers_c=QCheckBox("")
          self.telCovers_c.setChecked(False)
          self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
          #self.telCovers_c.setStyleSheet("background-color: yellow")
          self.telCovers_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")


          grid.addWidget(self.telCovers_l, w,0)
          grid.addWidget(self.telCovers_e, w,1)
          grid.addWidget(self.telCovers_c, w,3)

          w=w+1
          self.telM3_l=QLabel("M3: ")

          self.telM3_e=QLineEdit() 
          self.telM3_e.setReadOnly(True)  
          self.telM3_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        
          self.telM3_s=QComboBox()
          self.telM3_s.addItems(["Imager","Spectro","empty"])          
        
          self.telM3_p=QPushButton('SET')             

          grid.addWidget(self.telM3_l, w,0)
          grid.addWidget(self.telM3_e, w,1)
          grid.addWidget(self.telM3_s, w,2)
          grid.addWidget(self.telM3_p, w,3)        

          w=w+1
          self.telFilter_l=QLabel("FILTER: ")

          self.telFilter_e=QLineEdit() 
          self.telFilter_e.setReadOnly(True)  
          self.telFilter_e.setStyleSheet("background-color: rgb(233, 233, 233);")

          self.telFilter_s=QComboBox()
          self.telFilter_s.addItems(["V","I","u","v","b"])
          
          self.telFilter_p=QPushButton('SET')          
        
          grid.addWidget(self.telFilter_l, w,0)
          grid.addWidget(self.telFilter_e, w,1)
          grid.addWidget(self.telFilter_s, w,2)
          grid.addWidget(self.telFilter_p, w,3)         
        
        
          w=w+1
          self.telFocus_l=QLabel("FOCUS: ")

          self.telFocus_e=QLineEdit() 
          self.telFocus_e.setReadOnly(True)  
          self.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233);")

          self.telAutoFocus_c=QCheckBox("AUTO: ")
          self.telAutoFocus_c.setChecked(True)
          self.telAutoFocus_c.setLayoutDirection(Qt.RightToLeft)
          #self.mntCovers_c.setStyleSheet("background-color: yellow")
          self.telAutoFocus_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")

          grid.addWidget(self.telFocus_l, w,0)
          grid.addWidget(self.telFocus_e, w,1)
          grid.addWidget(self.telAutoFocus_c, w,3)

          w=w+1
        
          self.setFocus_e=QLineEdit() 
          self.setFocus_p=QPushButton('SET')

          grid.addWidget(self.setFocus_e, w,2)
          grid.addWidget(self.setFocus_p, w,3)

          
          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          grid.addWidget(self.line_l, w,0,1,6)


          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
