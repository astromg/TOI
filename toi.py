#!/usr/bin/env python3

#----------------
# 1.08.2022
# Marek Gorski
#----------------
from PyQt5.QtWidgets import  QApplication
from PyQt5.QtCore import *
import sys
import requests


from mnt_gui import *
from tel_gui import *
from sky_gui import *
from mnt_manual_gui import *
from instrument_gui import *


class TOI():
   def __init__(self,parent=None):
       super(TOI, self).__init__()

       self.run()
    
       self.mnt = MntGui(self)
       self.mnt.show()
       self.mnt.raise_()     
       self.tel = TelGui(self)
       self.tel.show()
       self.tel.raise_()     
       self.sky = SkyView()
       self.sky.show() 
       self.sky.raise_()  

       self.mnt_manual = MntManualGui()
       self.mnt_manual.show()
       self.mnt_manual.raise_()  

       self.inst = InstrumentGui()
       self.inst.show()
       self.inst.raise_() 

   def run(self):

       quest="http://172.23.68.211:11111/api/v1/telescope/0/connected"
       r=requests.get(quest)
       r=r.json()
       self.conected = (r["Value"])

       quest="http://172.23.68.211:11111/api/v1/telescope/0/azimuth"
       r=requests.get(quest)
       r=r.json()
       self.mnt_az = (r["Value"])

       print(self.mnt_az)

   def close(self):
       sys.exit()

app = QApplication(sys.argv)
main = TOI()

sys.exit(app.exec_())

