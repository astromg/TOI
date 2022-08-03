#!/usr/bin/env python3

#----------------
# 1.08.2022
# Marek Gorski
#----------------
from PyQt5.QtWidgets import  QApplication
import sys
from mnt_gui import *
from tel_gui import *
from sky_gui import *


class TOI():
   def __init__(self,parent=None):
       super(TOI, self).__init__()
    
       self.mnt = MntGui()
       self.mnt.show()
       self.mnt.raise_()     
       self.tel = TelGui(self)
       self.tel.show()
       self.tel.raise_()     
       self.sky = SkyView()
       self.sky.show() 
       self.sky.raise_()  

   def close(self):
       sys.exit()

app = QApplication(sys.argv)
main = TOI()

sys.exit(app.exec_())

