#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

class SkyView(QWidget):
   def __init__(self,parent):
       QWidget.__init__(self)
       self.parent=parent 
       self.mkUI()
    
       self.tel_az=5
       self.tel_alt=90
    
       self.a=[]
       self.h=[]
       self.symbol=[]
       
       self.silent_a=[]
       self.silent_h=[]
       self.silent_symbol=[]
   
       self.rmax=110
       self.marc_point=False


       self.a=[10,20,30,40,50,100,40,40,70]
       self.h=[50,50,50,50,50,30,40,40,20]
       self.symbol=["b*","b*","b*","b*","b*","ok","or","+r",".r"]
       self.alpha=[0.8,0.6,0.5,0.3,0.3,0.6,0.3,1,1]


       self.log_a=[10,20,30]
       self.log_h=[30,30,30]
       self.log_s=["k*","k*","k*"]
       self.log_alh=[0.5,0.5,0.5]


       self.update()
       self.parent.monitor.ding.connect(self.update)


   def update(self):    
       self.axes.clear()
       try:
          self.tel_az=2*math.pi*float(self.parent.mnt_az)/360.
          self.tel_alt=90.-float(self.parent.mnt_alt)
          self.axes.plot(self.tel_az,self.tel_alt,"or",alpha=0.5)
       except: pass

       try:
          nextAlt = float(self.parent.mnt.nextAlt_e.text())
          nextAz =  float(self.parent.mnt.nextAz_e.text())
          nextAz=2*math.pi*float(nextAz)/360.
          nextAlt=90.-float(nextAlt)
          self.axes.plot(nextAz,nextAlt,"bx",alpha=0.5)
       except: pass

       
       #if len(self.a)>0:      
       #   for h,a,s,al in zip(self.h,self.a,self.symbol,self.alpha):
       #       a=2*math.pi*a/360.  
       #       self.axes.plot(a, h,str(s),alpha=al)  
       #       self.axes.bar(230,5, width=0.2*math.pi,bottom=90,color='g',alpha=0.05)


       self.axes.set_theta_direction(-1)
       self.axes.set_theta_zero_location('N')       
       self.axes.set_ylim([0,360])
       self.axes.set_rlim([0,30])       
       self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])  
       self.axes.set_xticklabels(["N","E","S","W"])
       self.axes.set_rmax(self.rmax)         
       self.axes.set_rticks([20,40,60,90])  
       self.axes.set_yticklabels(["","","",""])  
       self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)  #tutaj zmienia sie pasek ponizej horyzoontu
   
       self.canvas.draw()
       self.show()    
    
# ======= Budowa okna ====================

   def mkUI(self):
       #self.setWindowTitle('FC')
       self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
       self.canvas = FigureCanvas(self.fig) 
       self.axes = self.fig.add_subplot(111,polar=True)
       #self.axes.set_theta_zero_location('N')
       
       hbox1 = QHBoxLayout()
       hbox1.addWidget(self.canvas)      
       
       self.vbox = QVBoxLayout()
       self.vbox.addLayout(hbox1)
       self.vbox.setSpacing(10) 
       self.setLayout(self.vbox) 
       
       #self.canvas.mpl_connect('button_press_event', self.zaznaczenie)
       
       self.axes.clear()
       self.resize(400,500)
       self.canvas.draw()
       #self.axes.grid(True)
       #self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])  
       #self.axes.set_yticks([20,40,60,80])  
       #self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)
       #self.axes.set_rmax(self.rmax)
          

     
   
   
#  ============ Klikanie w punkciki ==========================
   
   def zaznaczenie(self,event):
       przetrzymywacz=1000.
       self.i=0
       if len(self.a)>0:
          a1=float(event.xdata)
          h1=float(event.ydata)
          for i,smiec in enumerate(self.a): 
              #a2=self.a[i]
              a2=2*math.pi*(self.a[i])/360.
              h2=float(self.h[i])  
              delta=( h1**2+h2**2-2*h1*h2*math.cos(a1-a2)  )**0.5
              if delta < przetrzymywacz:
                 self.i=i                       #indeks zaznaczonego elementu
                 przetrzymywacz=delta
          a=self.a[self.i]
          a=2*math.pi*a/360. 
          self.update()
          if self.marc_point: 
             self.axes.plot(a, self.h[self.i],"ro") 
             self.canvas.draw()
             self.show() 




          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
