#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox


import ephem
from toi_lib import *


class PlanGui(QWidget):
      def __init__(self, parent):
          super(PlanGui, self).__init__()
          self.parent=parent
          self.font =  QtGui.QFont( "Arial", 11)

          self.plan=[] 
          self.i=0
          self.prev_i=1
          self.next_i=0
          
          
          self.mkUI()

          self.load_p.clicked.connect(self.loadPlan)    
          self.plan_t.cellClicked.connect(self.pocisniecie_tabelki)

          self.next_p.clicked.connect(self.setNext)   
          self.stopHere_p.clicked.connect(self.setStop)             
          self.skip_p.clicked.connect(self.setSkip)     
          self.up_p.clicked.connect(self.pocisniecie_up)  
          self.down_p.clicked.connect(self.pocisniecie_down)   
          self.del_p.clicked.connect(self.pocisniecie_del) 
          self.first_p.clicked.connect(self.pocisniecie_first) 
          self.last_p.clicked.connect(self.pocisniecie_last)    
          self.swap_p.clicked.connect(self.pocisniecie_swap)                 

          self.update_table()

      def recalc(self):
          for i,tmp in enumerate(self.plan):
             if len(self.plan)>0:
                if "ra" in self.plan[i].keys():
                   ra=self.plan[i]["ra"]
                   dec=self.plan[i]["dec"]
                   az,alt = RaDec2AltAz(self.parent.observatory,ephem.now(),ra,dec)
                   self.plan[i]["alt"]=alt
                   self.plan[i]["az"]=az 

      def update_table(self):
          self.recalc()
          if len(self.plan)>0:
             self.plan_t.clearContents()
             for i,tmp in enumerate(self.plan):
                 if self.plan_t.rowCount() < i+1: self.plan_t.insertRow(i)
                 
                 if i==self.next_i:
                    pic = QtGui.QPixmap("./Icons/next.png").scaled(QSize(30,30))
                    icon=QLabel()
                    icon.setPixmap(pic)
                    self.plan_t.setCellWidget(i,0,icon)

                 if "skip" in self.plan[i].keys():
                    if self.plan[i]["skip"]:
                       pic = QtGui.QPixmap("./Icons/skip.png").scaled(QSize(30,30))
                       icon=QLabel()
                       icon.setPixmap(pic)
                       self.plan_t.setCellWidget(i,0,icon)

                 if "stop" in self.plan[i].keys():
                    if self.plan[i]["stop"]:
                       pic = QtGui.QPixmap("./Icons/stop.png").scaled(QSize(30,30))
                       icon=QLabel()
                       icon.setPixmap(pic)
                       self.plan_t.setCellWidget(i,0,icon)

                     
                 txt=QTableWidgetItem(self.plan[i]["name"])
                 self.plan_t.setItem(i,1,txt)

                 if "alt" in self.plan[i].keys():
                    txt=QTableWidgetItem(str(self.plan[i]["alt"]))
                    self.plan_t.setItem(i,2,txt)                    

                 if i==self.prev_i:
                    self.plan_t.item(i,1).setBackground(QtGui.QColor(227,253,227))
                    self.plan_t.item(i,2).setBackground(QtGui.QColor(227,253,227))
                 if i==self.i:
                    self.plan_t.item(i,1).setBackground(QtGui.QColor("lightgreen"))
                    self.plan_t.item(i,2).setBackground(QtGui.QColor("lightgreen"))

      def setNext(self):
          self.next_i=self.i
          self.update_table()
          self.parent.mnt.nextRa_e.setText(self.plan[self.i]["ra"])
          self.parent.mnt.nextDec_e.setText(self.plan[self.i]["dec"])

      def setStop(self):
          if "stop" in self.plan[self.i].keys():          
             if self.plan[self.i]["stop"]:self.plan[self.i]["stop"]=False
          else: self.plan[self.i]["stop"]=True
          self.update_table()

      def setSkip(self):
          if "skip" in self.plan[self.i].keys():          
             if self.plan[self.i]["skip"]:self.plan[self.i]["skip"]=False
          else: self.plan[self.i]["skip"]=True
          self.update_table()

      def pocisniecie_tabelki(self,i,j):
          self.prev_i=self.i
          self.i=i
          self.update_table()

      def pocisniecie_del(self):
          self.plan.pop(self.i)
          self.update_table()
          self.repaint()

      def pocisniecie_first(self):
          self.plan.insert(0,self.plan[self.i])
          self.plan.pop(self.i+1)
          self.i=0              
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))
          self.repaint()

      def pocisniecie_last(self):
          self.plan.append(self.plan[self.i])  
          self.plan.pop(self.i)
          self.i=len(self.plan)-1
          self.update_table()  
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))      
          self.repaint()

      def pocisniecie_down(self):
          if self.i==len(self.plan)-1:
             self.plan.insert(0,self.plan[self.i])
             self.plan.pop(len(self.plan)-1)
             self.i=0     
          else:   
             self.plan[self.i],self.plan[self.i+1]=self.plan[self.i+1],self.plan[self.i]
             self.i_prev,self.i=self.i,self.i+1
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()

      def pocisniecie_up(self):
          if self.i==0:
             self.plan.append(self.plan[0])  
             self.plan.pop(0)
             self.i=len(self.plan)
          else:  
             self.plan[self.i],self.plan[self.i-1]=self.plan[self.i-1],self.plan[self.i]
             self.i_prev,self.i=self.i,self.i-1
          self.update_table()
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()

      def pocisniecie_swap(self): 
          self.plan[self.i],self.plan[self.prev_i]=self.plan[self.prev_i],self.plan[self.i]
          self.update_table()
          self.i,self.prev_i=self.prev_i,self.i
          self.plan_t.scrollToItem(self.plan_t.item(self.i, 1))              
          self.repaint()      

 



      def loadPlan(self):
          self.fileName=str(QFileDialog.getOpenFileName(self,"Open file",".")[0])
        
        
          self.plan=[]
          with open(self.fileName, "r") as plik:
             for line in plik:
                 if "OBJECT" in line:
                    ll=line.split()
                    name=ll[1]
                    ra=ll[2]
                    dec=ll[3]
                    ob = {"name":name}
                    ob["ra"]=ra
                    ob["dec"]=dec
                    self.plan.append(ob)
          self.update_table()          
        
        
          
        # =================== OKNO GLOWNE ====================================
      def mkUI(self):
           
          self.setWindowTitle('Telescope Plan Manager')
          #self.setWindowIcon(QtGui.QIcon('icon.png'))  
          
          grid = QGridLayout()         

          #self.telCovers_l=QLabel("MIRROR COVERS: ")

          w=0
          self.load_p=QPushButton('Load Plan') 
          self.stop_p=QPushButton('Stop')          
          self.start_p=QPushButton('Start')

          grid.addWidget(self.load_p, w,0)
          grid.addWidget(self.stop_p, w,2)
          grid.addWidget(self.start_p, w,4)
          
          w=w+1
          self.plan_t=QTableWidget(0,4)
          self.plan_t.setHorizontalHeaderLabels(["","Object","Alt",""])
          
          grid.addWidget(self.plan_t, w,0,8,5)
          
          w=w+8
          self.next_p=QPushButton('Next') 
          self.stopHere_p=QPushButton('Stop')          
          self.skip_p=QPushButton('Skip')

          grid.addWidget(self.next_p, w,0)
          grid.addWidget(self.stopHere_p, w,1)
          grid.addWidget(self.skip_p, w,4)
          
          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          grid.addWidget(self.line_l, w,0,1,5)             
          
          w=w+1
          self.del_p=QPushButton('Del') 
          self.up_p=QPushButton('Up')          
          self.swap_p=QPushButton('Swap')
          self.first_p=QPushButton('First')

          grid.addWidget(self.del_p, w,0)
          grid.addWidget(self.up_p, w,2)
          grid.addWidget(self.swap_p, w,3)
          grid.addWidget(self.first_p, w,4)
              
          
          w=w+1
          self.delAll_p=QPushButton('Del All') 
          self.down_p=QPushButton('Down')          
          self.last_p=QPushButton('Last')

          grid.addWidget(self.delAll_p, w,0)
          grid.addWidget(self.down_p, w,2)
          grid.addWidget(self.last_p, w,4)          

          w=w+1
          self.line_l=QFrame()
          self.line_l.setFrameShape(QFrame.HLine)
          self.line_l.setFrameShadow(QFrame.Raised)
          grid.addWidget(self.line_l, w,0,1,5)          

          w=w+1
          self.add_p=QPushButton('Add') 
          self.edit_p=QPushButton('Edit')          


          grid.addWidget(self.add_p, w,0)
          grid.addWidget(self.edit_p, w,4)
 





          #self.telCovers_e=QLineEdit() 
          #self.telCovers_e.setReadOnly(True)  
          #self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233);")
 
          #self.telCovers_c=QCheckBox("")
          #self.telCovers_c.setChecked(False)
          #self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
          #self.telCovers_c.setStyleSheet("background-color: yellow")
          #self.telCovers_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./SwitchOn.png)}::indicator:unchecked {image: url(./SwitchOff.png)}")


          #self.telFilter_s=QComboBox()
          #self.telFilter_s.addItems(["V","I","u","v","b"])


          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
