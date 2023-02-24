#!/usr/bin/env python3

#----------------
# 01.08.2022
# Marek Gorski
#----------------

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QTabWidget, QApplication, QWidget, QLabel,QCheckBox, QTextEdit, QLineEdit, QDialog, QTabWidget, QPushButton, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,QTableWidgetItem, QSlider, QCompleter, QFileDialog, QFrame, QComboBox, QProgressBar

import paho.mqtt.client as mqtt
import json



class AuxGui(QWidget):
      def __init__(self, parent):
          super(AuxGui, self).__init__()
          self.parent=parent
          self.setStyleSheet("font-size: 11pt;")
          self.setGeometry(self.parent.aux_geometry[0],self.parent.aux_geometry[1],self.parent.aux_geometry[2],self.parent.aux_geometry[3])

          self.updateUI()

      def updateUI(self):

          local_dic={"WK06":'WK06 Aux Monitor',"ZB08":'ZB08 Aux Monitor',"JK15":'JK15 Aux Monitor',"WG25":'WG25 Aux Monitor',"SIM":'SIM Aux Monitor'}
          try: txt = local_dic[self.parent.active_tel]
          except: txt = "unknow Aux Monitor"
          self.setWindowTitle(txt)


          tmp=QWidget()
          try: tmp.setLayout(self.layout)
          except: pass

          self.layout = QGridLayout()
          self.setLayout(self.layout)

          self.tabWidget=QTabWidget()

          self.welcome_tab=WelcomeGui(self.parent)
          self.tabWidget.addTab(self.welcome_tab,"Welcome")

          self.focus_tab=FocusGui(self.parent)
          self.tabWidget.addTab(self.focus_tab,"Focus")

          self.guider_tab=GuiderGui(self.parent)
          self.tabWidget.addTab(self.guider_tab,"Guider")

          self.flat_tab=FlatGui(self.parent)
          self.tabWidget.addTab(self.flat_tab,"Flats")

          self.weather_tab=WeatherGui(self.parent)
          self.tabWidget.addTab(self.weather_tab,"Weather")
          self.weather_tab.update()

          self.cctv_tab=CctvGui(self.parent)
          self.tabWidget.addTab(self.cctv_tab,"CCTV")

          self.fits_tab=FitsGui(self.parent)
          self.tabWidget.addTab(self.fits_tab,"Fits")

          self.layout.addWidget(self.tabWidget,0,0)
          del tmp

class WelcomeGui(QWidget):
      def __init__(self, parent):
          super(WelcomeGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.pic_l = QLabel(" ")
          if self.parent.active_tel=="WK06": png_file='./Icons/wk06.png'
          elif self.parent.active_tel=="ZB08": png_file='./Icons/zb08.png'
          elif self.parent.active_tel=="JK15": png_file='./Icons/jk15.png'
          elif self.parent.active_tel=="WG25": png_file='./Icons/wg25.png'
          elif self.parent.active_tel=="SIM": png_file='./Icons/oca.png'
          self.pic_l.setPixmap(QtGui.QPixmap(png_file).scaled(400,300))
          grid.addWidget(self.pic_l, w, 0)
          self.setLayout(grid)



class FocusGui(QWidget):
      def __init__(self, parent):
          super(FocusGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):
           
          grid = QGridLayout()
          w=0   
          self.autoFocus_p = QPushButton('AUTO FOCUS')
          grid.addWidget(self.autoFocus_p, w, 0)

          self.setLayout(grid)



class GuiderGui(QWidget):
      def __init__(self, parent):
          super(GuiderGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):

          grid = QGridLayout()
          w=0
          self.autoFocus_p = QPushButton('Guide')
          grid.addWidget(self.autoFocus_p, w, 0)

          self.setLayout(grid)

class FlatGui(QWidget):
      def __init__(self, parent):
          super(FlatGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.setLayout(grid)


# ######### weather GUI ##############################

class WeatherGui(QWidget):
      def __init__(self, parent):
          super(WeatherGui, self).__init__()
          self.parent=parent
          self.mqtt_client = mqtt.Client()
          self.ut=""
          self.wind=""
          self.temp=""
          self.mkUI()
          self.update()

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.ut_l=QLabel("UT:")
          self.ut_e=QLineEdit()
          grid.addWidget(self.ut_l, w, 0)
          grid.addWidget(self.ut_e, w, 1)
          w=w+1
          self.wind_l=QLabel("Wind:")
          self.wind_e=QLineEdit()
          grid.addWidget(self.wind_l, w, 0)
          grid.addWidget(self.wind_e, w, 1)
          w=w+1
          self.temp_l=QLabel("Temp:")
          self.temp_e=QLineEdit()
          grid.addWidget(self.temp_l, w, 0)
          grid.addWidget(self.temp_e, w, 1)
          self.setLayout(grid)
      def update(self):
          self.mqtt_broker = 'docker.oca.lan'
          self.mqtt_port = 1883
          self.mqtt_topic_weather = 'weather'
          self.mqtt_client.connect(self.mqtt_broker,self.mqtt_port)
          self.mqtt_client.message_callback_add(self.mqtt_topic_weather, self.on_weather_message)
          self.mqtt_client.on_connect = self.on_mqtt_connect
          self.mqtt_client.loop_start()
          #mqtt_client.loop_stop()


      def on_weather_message(self,client, userdata, message):
          weather = message.payload.decode('utf-8')
          weather_dict = json.loads(weather)
          self.ut,self.wind,self.temp=weather_dict["dataGMTTime"],weather_dict["wind"],weather_dict["temp"]
          self.ut_e.setText(self.ut)
          self.wind_e.setText(str(self.wind))
          self.temp_e.setText(str(self.temp))

      def on_mqtt_connect(self,client, userdata, flags, rc):
          if rc == 0: self.mqtt_client.subscribe((self.mqtt_topic_weather, 1))




class CctvGui(QWidget):
      def __init__(self, parent):
          super(CctvGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.setLayout(grid)

class FitsGui(QWidget):
      def __init__(self, parent):
          super(FitsGui, self).__init__()
          self.parent=parent
          self.mkUI()

      def mkUI(self):
          grid = QGridLayout()
          w=0
          self.setLayout(grid)

          '''
          self.inst_object_l=QLabel("OBJECT NAME:")
          self.inst_object_e=QLineEdit() 

          self.inst_Obtype_l=QLabel("TYPE:")
          self.inst_Obtype_s=QComboBox()
          self.inst_Obtype_s.addItems(["Science","Calibration","Dark","SkyFla","DomeFlat","Zero","Focus"])         
          
          grid.addWidget(self.inst_object_l, w,0)
          grid.addWidget(self.inst_object_e, w,1)
          grid.addWidget(self.inst_Obtype_l, w,2)
          grid.addWidget(self.inst_Obtype_s, w,3)
        
          w=w+1
          self.inst_Ndit_l=QLabel("NDIT:")
          self.inst_Ndit_e=QLineEdit() 

          self.inst_Dit_l=QLabel("DIT:")
          self.inst_Dit_e=QLineEdit()   
          
          grid.addWidget(self.inst_Ndit_l, w,0)
          grid.addWidget(self.inst_Ndit_e, w,1)
          grid.addWidget(self.inst_Dit_l, w,2)
          grid.addWidget(self.inst_Dit_e, w,3)
          
          w=w+1
          self.inst_NditProg_n=QProgressBar(self)
          self.inst_NditProg_n.setValue(45)
          self.inst_NditProg_n.setFormat("2/4")


          self.inst_DitProg_n=QProgressBar(self)
          self.inst_DitProg_n.setValue(75)
          self.inst_DitProg_n.setFormat("237/300")


          grid.addWidget(self.inst_NditProg_n, w,0,1,2)
          grid.addWidget(self.inst_DitProg_n, w,2,1,2)
          
          w=w+1
          self.inst_Seq_l=QLabel("Sequence:")
          self.inst_Seq_e=QLineEdit() 
          self.inst_Seq_p=QPushButton('EXECUTE')


          grid.addWidget(self.inst_Seq_l, w,0)
          grid.addWidget(self.inst_Seq_e, w,1)
          grid.addWidget(self.inst_Seq_p, w,2,1,2)
          
          w=w+1
          self.inst_Mode_l=QLabel("Mode:")
          self.inst_Mode_s=QComboBox()
          self.inst_Mode_s.addItems(["Normal","Sky","JitterBox","JitterRandom"])             

          self.inst_ccdTemp_l=QLabel("CCD TEMP.:")
          self.inst_ccdTemp_e=QLineEdit() 
          
          grid.addWidget(self.inst_Mode_l, w,0) 
          grid.addWidget(self.inst_Mode_s, w,1)          
          grid.addWidget(self.inst_ccdTemp_l, w,2)
          grid.addWidget(self.inst_ccdTemp_e, w,3)

          w=w+1
          self.inst_Bin_l=QLabel("Binning:")
          self.inst_Bin_s=QComboBox()
          self.inst_Bin_s.addItems(["1x1","2x2","1x2","2x1"])             
          
          grid.addWidget(self.inst_Bin_l, w,0) 
          grid.addWidget(self.inst_Bin_s, w,1)   

          w=w+1
          self.inst_Subraster_l=QLabel("Subraster:")
          self.inst_Subraster_s=QComboBox()
          self.inst_Subraster_s.addItems(["No","Subraster1","Subraster2","Subraster3"])             
          
          grid.addWidget(self.inst_Subraster_l, w,0) 
          grid.addWidget(self.inst_Subraster_s, w,1)            
          
          w=w+1          
          
          self.inst_Snap_p=QPushButton('SNAP')
          self.inst_Pause_p=QPushButton('PAUSE')
          self.inst_Stop_p=QPushButton('STOP')
          self.inst_Start_p=QPushButton('START')
          
          grid.addWidget(self.inst_Snap_p, w,0) 
          grid.addWidget(self.inst_Pause_p, w,1) 
          grid.addWidget(self.inst_Stop_p, w,2) 
          grid.addWidget(self.inst_Start_p, w,3)         

          #grid.setColumnMinimumWidth(6,100)
          #grid.setColumnMinimumWidth(8,100)
          #grid.setColumnMinimumWidth(10,100)
          
          #grid.setSpacing(10)
     
          
          self.setLayout(grid)
          '''
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
