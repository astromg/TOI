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

class Monitor(QtCore.QObject):
      finished = QtCore.pyqtSignal()
      
      def __init__(self, parent):
          self.parent=parent
          QObject.__init__(self)
          self.continue_run = True
      def run(self):
          while self.continue_run:  # give the loop a stoppable condition
                QtCore.QThread.sleep(1)
                ok=True
                try:
                   quest="http://172.23.68.211:11111/api/v1/telescope/0/connected"
                   r=requests.get(quest)
                   r=r.json()
                   self.parent.conected = (r["Value"])
                except: 
                   ok=False 
                   print("no connection")
                if ok:       
                   quest="http://172.23.68.211:11111/api/v1/telescope/0/azimuth"
                   r=requests.get(quest)
                   r=r.json()
                   self.parent.mnt_az = "%.4f"%r["Value"]
   
                   quest="http://172.23.68.211:11111/api/v1/telescope/0/altitude"
                   r=requests.get(quest)
                   r=r.json()
                   self.parent.mnt_alt = "%.4f"%r["Value"]
   
                   #print(self.parent.mnt_az)
                   self.parent.mnt.update()

          self.finished.emit()  # emit the finished signal when the loop is done

      def stop(self):
          self.continue_run = False  # set the run condition to false on stop


class TOI():
   def __init__(self,parent=None):
       super(TOI, self).__init__()
       self.mnt_az="unknown"
       self.mnt_alt="unknown"

    
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

       # Monitor Thread:
       self.thread = QtCore.QThread()
       self.monitor = Monitor(self)
       self.monitor.moveToThread(self.thread)
       self.monitor.finished.connect(self.thread.quit)  # connect monitor finished signal to stop thread
       self.monitor.finished.connect(self.monitor.deleteLater)
       self.thread.finished.connect(self.thread.deleteLater)
       self.thread.started.connect(self.monitor.run)
       self.thread.finished.connect(self.monitor.stop)
       self.thread.start()


   def close(self):
       sys.exit()

app = QApplication(sys.argv)
main = TOI()

sys.exit(app.exec_())

