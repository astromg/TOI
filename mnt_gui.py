#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox




class MntGui(QWidget):
      def __init__(self, parent=None):
          super(MntGui, self).__init__()
          
          self.font =  QtGui.QFont( "Arial", 11)
          
          self.mkUI()


          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Telescope GUI')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          


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

        
          # dome

          self.domeAz_l=QLabel("DOME AZ: ")
          self.domeAz_e=QLineEdit() 
          self.domeAz_e.setReadOnly(True)         
                       
        
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
        
        
          grid = QGridLayout()              

          w=0   
 
          grid.addWidget(self.mntRa_l, w,0)
          grid.addWidget(self.mntRa_e, w,1)

          grid.addWidget(self.mntDec_l, w,2)
          grid.addWidget(self.mntDec_e, w,3) 


          w=w+1          

          grid.addWidget(self.mntAz_l, w,0)
          grid.addWidget(self.mntAz_e, w,1)      
      
          grid.addWidget(self.mntAlt_l, w,2)
          grid.addWidget(self.mntAlt_e, w,3)

          w=w+1          
     
          grid.addWidget(self.domeAz_l, w,0)
          grid.addWidget(self.domeAz_e, w,1)

          grid.addWidget(self.mntAirmass_l, w,2)
          grid.addWidget(self.mntAirmass_e, w,3)

          w=w+1          
          grid.addWidget(self.telFocus_l, w,0)
          grid.addWidget(self.telFocus_e, w,1)        

          w=w+1          
          grid.addWidget(self.telFilter_l, w,0)
          grid.addWidget(self.telFilter_e, w,1)

          w=w+1          
          grid.addWidget(self.telM3_l, w,0)
          grid.addWidget(self.telM3_e, w,1)

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
