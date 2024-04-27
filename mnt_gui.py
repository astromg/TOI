#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------
import logging
import time
from typing import Tuple

import qasync as qs
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QCheckBox, QLineEdit, QPushButton, QSpinBox, QGridLayout, QFrame, QComboBox, QRadioButton
from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
from pyaraucaria.coordinates import *
from qasync import QEventLoop

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from toi_lib import *

logger = logging.getLogger(__name__)


class MntGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        super().__init__(loop=loop, client_api=client_api)
        self.subscriber_delay = 1
        self.subscriber_time_of_data_tolerance = 0.5

        self.parent = parent
        self.setGeometry(self.parent.mnt_geometry[0],self.parent.mnt_geometry[1],self.parent.mnt_geometry[2],self.parent.mnt_geometry[3])
        self.updateUI()

    def updateNextRaDec(self):
        self.nextRa_e.setStyleSheet("background-color: white; color: black;")
        self.nextDec_e.setStyleSheet("background-color: white; color: black;")
        self.nextAlt_e.setStyleSheet("background-color: white; color: black;")
        self.nextAz_e.setStyleSheet("background-color: white; color: black;")
        self.parent.nextOB_ok = False
        airmass = None
        if self.setEq_r.isChecked():
            ra = self.nextRa_e.text()
            dec = self.nextDec_e.text()
            if len(ra)>0 and len(dec)>0:
                self.parent.nextOB_ok = True
            else: self.parent.nextOB_ok = None
            if self.parent.nextOB_ok:
                try:
                    az, alt = RaDec2AltAz(self.parent.observatory, ephem.now(), ra, dec)
                    az = deg_to_decimal_deg(str(az))
                    alt = deg_to_decimal_deg(str(alt))
                    self.nextAlt_e.setText("%.2f" % alt)
                    self.nextAz_e.setText("%.2f" % az)
                except:
                    self.parent.nextOB_ok = False
                    self.nextRa_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                    self.nextDec_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
            if self.parent.nextOB_ok:
                if ":" in ra:
                    try:
                        if float(ra.split(":")[0]) < 0 or float(ra.split(":")[0]) > 24:
                            self.parent.nextOB_ok = False
                            self.nextRa_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                    except ValueError: pass
                else:
                    if float(ra) < 0 or float(ra) > 24:
                        self.parent.nextOB_ok = False
                        self.nextRa_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                if ":" in dec:
                    try:
                        if float(dec.split(":")[0]) < -90 or float(dec.split(":")[0]) > 90:
                            self.parent.nextOB_ok = False
                            self.nextDec_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                    except ValueError: pass
                else:
                    if float(dec) < 0 or float(dec) > 24:
                        self.parent.nextOB_ok = False
                        self.nextDec_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

        if self.setAltAz_r.isChecked():
            alt = self.nextAlt_e.text()
            az = self.nextAz_e.text()
            if len(str(alt)) > 0 and len(str(az)) > 0:
                self.parent.nextOB_ok = True
            else: self.parent.nextOB_ok = None
            if self.parent.nextOB_ok:
                try:
                    ra, dec = AltAz2RaDec(self.parent.observatory, ephem.now(), alt, az)
                    self.nextRa_e.setText(str(ra))
                    self.nextDec_e.setText(str(dec))
                except:
                    self.parent.nextOB_ok = False
                    self.nextAlt_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
                    self.nextAz_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
        if self.parent.nextOB_ok:
            if float(alt) < self.parent.cfg_alt_limits["min"] or float(alt) > self.parent.cfg_alt_limits["max"] :
                self.parent.nextOB_ok = False
                self.nextAlt_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")

            if float(az) > 360 or float(az)<0:
                self.parent.nextOB_ok = False
                self.nextAz_e.setStyleSheet("background-color: rgb(255, 165, 0); color: black;")
        if self.parent.nextOB_ok:
            airmass = calc_airmass(float(alt))
            if airmass != None:
                self.nextAirmass_e.setText("%.1f" % airmass)
            else:
                self.nextAirmass_e.setText(" -- ")
        if self.parent.nextOB_ok or self.parent.nextOB_ok == None:
            if self.setEq_r.isChecked():
                self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                self.nextRa_e.setStyleSheet("background-color: white; color: black;")
                self.nextDec_e.setStyleSheet("background-color: white; color: black;")
            elif self.setAltAz_r.isChecked():
                self.nextAlt_e.setStyleSheet("background-color: white; color: black;")
                self.nextAz_e.setStyleSheet("background-color: white; color: black;")
                self.nextRa_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
                self.nextDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        if  self.parent.nextOB_ok:
            if float(alt) > 0 and float(alt) < 30:
                self.nextAlt_e.setStyleSheet("background-color: rgb(240, 232, 151); color: black;")

    def select(self):
        if self.setEq_r.isChecked():
            self.nextAz_e.setReadOnly(True)
            self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextAlt_e.setReadOnly(True)
            self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextRa_e.setReadOnly(False)
            self.nextRa_e.setStyleSheet("background-color: white;")
            self.nextDec_e.setReadOnly(False)
            self.nextDec_e.setStyleSheet("background-color: white;")

        else:
            self.nextAz_e.setReadOnly(False)
            self.nextAz_e.setStyleSheet("background-color: white;")
            self.nextAlt_e.setReadOnly(False)
            self.nextAlt_e.setStyleSheet("background-color: white;")
            self.nextRa_e.setReadOnly(True)
            self.nextRa_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextDec_e.setReadOnly(True)
            self.nextDec_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.updateNextRaDec()

    def selectRaDec(self,event):
        self.setEq_r.setChecked(True)
        self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.nextRa_e.setStyleSheet("background-color: white;")
        self.nextDec_e.setStyleSheet("background-color: white;")
        self.updateNextRaDec()

    def selectAltAz(self,event):
        self.setAltAz_r.setChecked(True)
        self.nextAz_e.setStyleSheet("background-color: white;")
        self.nextAlt_e.setStyleSheet("background-color: white;")
        self.nextRa_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.nextDec_e.setStyleSheet("background-color: rgb(233, 233, 233);")
        self.updateNextRaDec()

    def pulse(self):
        try:
            self.pulse_window.raise_()
        except AttributeError:
            self.pulse_window = PulseWindow(self.parent)

    # =================== OKNO GLOWNE ====================================
    def updateUI(self):

        self.setWindowTitle('')
        self.setStyleSheet("font-size: 11pt;")

        local_dic={"wk06":'wk06 Mount Manual Controll',"zb08":'zb08 Mount Manual Controll',"jk15":'jk15 Mount Manual Controll',"sim":'SIM Mount Manual Controll'}
        try: txt = local_dic[self.parent.active_tel]
        except: txt = "Unknown Mount Manual Controll"
        self.setWindowTitle(txt)

        tmp=QWidget()
        try: tmp.setLayout(self.grid)
        except: pass
        self.grid = QGridLayout()

        ##################### MOUNT #############################

        self.mntConn1_l = QLabel("MOUNT")
        self.mntConn2_l = QLabel(" ")
        self.mntConn2_l.setText("\U0001F534")
        self.mntConn1_l.setStyleSheet("color: rgb(150,0,0);")
        self.mntConn2_l.setMaximumWidth(25)                                        # UWAGA!!! To steruje szeroskoscia 1 kolumny!!!!!!!

        #self.mntStat_l = QLabel("MOUNT STATUS: ")
        self.mntStat_e = QLineEdit()
        self.mntStat_e.setReadOnly(True)
        self.mntStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.mntStat_e.setText("--")

        self.mntMotors_l = QLabel("MOTORS: ")
        self.mntMotors_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.mntMotors_c = QCheckBox()
        self.mntMotors_c.setChecked(False)
        self.mntMotors_c.setLayoutDirection(Qt.RightToLeft)
        self.mntMotors_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.mntMotors_c.clicked.connect(self.parent.mount_motorsOnOff)



        w=0
        self.grid.addWidget(self.mntConn2_l, w, 0)
        self.grid.addWidget(self.mntConn1_l, w, 1)

        #self.grid.addWidget(self.mntStat_l, w, 4)
        self.grid.addWidget(self.mntStat_e, w, 2, 1, 3)

        self.grid.addWidget(self.mntMotors_l, w, 6)
        self.grid.addWidget(self.mntMotors_c, w, 7)

        ########################################

        self.mntEpoch_l = QLabel("EPOCH: ")
        self.mntEpoch_e = QLineEdit("2000")

        self.mntAirmass_l = QLabel("AIRMASS: ")
        self.mntAirmass_e = QLineEdit()
        self.mntAirmass_e.setReadOnly(True)
        self.mntAirmass_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.mntAirmass_e.setText(" -- ")

        self.nextAirmass_l = QLabel("Next Airmass: ")
        self.nextAirmass_e = QLineEdit()
        self.nextAirmass_e.setReadOnly(True)
        self.nextAirmass_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        w=w+1
        self.grid.addWidget(self.mntEpoch_l, w, 0,1,2)
        self.grid.addWidget(self.mntEpoch_e, w, 3)

        self.grid.addWidget(self.mntAirmass_l, w, 4)
        self.grid.addWidget(self.mntAirmass_e, w, 5)
        self.grid.addWidget(self.nextAirmass_e, w, 6,1,2)


        ###################################################

        self.mntRa_l = QLabel("TELESCOPE RA [h]:")
        self.mntRa_e = QLineEdit("00:00:00")
        self.mntRa_e.setReadOnly(True)
        self.mntRa_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.mntDec_l = QLabel("TELESCOPE DEC [d]:")
        self.mntDec_e = QLineEdit("00:00:00")
        self.mntDec_e.setReadOnly(True)
        self.mntDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")


        self.nextRa_l = QLabel("NEXT RA: ")
        self.nextRa_e = QLineEdit("")
        self.nextRa_e.mousePressEvent = self.selectRaDec

        self.nextDec_l = QLabel("NEXT DEC: ")
        self.nextDec_e = QLineEdit("")
        self.nextDec_e.mousePressEvent = self.selectRaDec

        self.setEq_r = QRadioButton("")
        self.setEq_r.setChecked(True)
        self.setAltAz_r = QRadioButton("")

        w = w + 1
        self.grid.addWidget(self.mntRa_l, w, 0,1,2)
        self.grid.addWidget(self.mntRa_e, w, 2)
        self.grid.addWidget(self.nextRa_e, w, 3)

        self.grid.addWidget(self.mntDec_l, w, 4)
        self.grid.addWidget(self.mntDec_e, w, 5)
        self.grid.addWidget(self.nextDec_e, w, 6,1,2)
        self.grid.addWidget(self.setEq_r, w, 8)

        #########################################


        self.mntAz_l = QLabel("TELESCOPE AZ [d]: ")
        self.mntAz_e = QLineEdit()
        self.mntAz_e.setReadOnly(True)
        self.mntAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.mntAlt_l = QLabel("TELESCOPE ALT [d]: ")
        self.mntAlt_e = QLineEdit()
        self.mntAlt_e.setReadOnly(True)
        self.mntAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")


        self.nextAz_l = QLabel("NEXT AZ: ")
        self.nextAz_e = QLineEdit()
        self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.nextAz_e.mousePressEvent = self.selectAltAz

        self.nextAlt_l = QLabel("NEXT ALT: ")
        self.nextAlt_e = QLineEdit()
        self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.nextAlt_e.mousePressEvent = self.selectAltAz

        w = w + 1
        self.grid.addWidget(self.mntAz_l, w, 0,1,2)
        self.grid.addWidget(self.mntAz_e, w, 2)
        self.grid.addWidget(self.nextAz_e, w, 3)

        self.grid.addWidget(self.mntAlt_l, w, 4)
        self.grid.addWidget(self.mntAlt_e, w, 5)
        self.grid.addWidget(self.nextAlt_e, w, 6,1,2)
        self.grid.addWidget(self.setAltAz_r, w, 8)

        ###############################################

        self.target_l = QLabel("SEARCH: ")
        self.target_e = QLineEdit("")
        self.target_e.editingFinished.connect(self.parent.target_provided)
        self.target_e.textChanged.connect(self.parent.target_changed)
        #self.target_e.setReadOnly(True)
        #self.target_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.tracking_l = QLabel("TRACKING: ")
        self.tracking_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.tracking_c = QCheckBox()
        self.tracking_c.setChecked(False)
        self.tracking_c.setLayoutDirection(Qt.RightToLeft)
        self.tracking_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.tracking_c.clicked.connect(self.parent.mount_trackOnOff)

        self.guiding_c = QCheckBox("GUIDING: ")
        self.guiding_c.setChecked(False)
        self.guiding_c.setLayoutDirection(Qt.RightToLeft)
        self.guiding_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOnGrey.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")

        w = w + 1
        self.grid.addWidget(self.target_l, w, 1)
        self.grid.addWidget(self.target_e, w, 2, 1, 2)
        self.grid.addWidget(self.guiding_c, w, 4)
        self.grid.addWidget(self.tracking_l, w, 6)
        self.grid.addWidget(self.tracking_c, w, 7)

        #################################################

        self.telPark_p = QPushButton('PARK')
        self.telPark_p.clicked.connect(self.parent.park_mount)

        self.telPulse_p = QPushButton('PULSE')
        self.telPulse_p.clicked.connect(self.pulse)

        self.mntStop_p = QPushButton('STOP')
        self.mntStop_p.clicked.connect(self.parent.abort_slew)

        self.Slew_p = QPushButton('SLEW')
        self.Slew_p.clicked.connect(self.parent.mount_slew)

        w = w + 1
        self.grid.addWidget(self.telPark_p, w, 0,1,2)
        self.grid.addWidget(self.telPulse_p, w, 2)
        self.grid.addWidget(self.mntStop_p, w, 4)
        self.grid.addWidget(self.Slew_p, w, 5, 1, 2)
        #################################################

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        w = w + 1
        self.grid.addWidget(self.line_l, w, 0, 1, 8)

        ################## DOME ##########################################

        self.domeConn1_l = QLabel("DOME")
        self.domeConn2_l = QLabel(" ")
        self.domeConn2_l.setText("\U0001F534")
        self.domeConn1_l.setStyleSheet("color: rgb(150,0,0);")

        self.domeStat_e = QLineEdit()
        self.domeStat_e.setReadOnly(True)
        self.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.domeAuto_l  = QLabel("FOLLOW:")
        self.domeAuto_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.domeAuto_c = QCheckBox()
        self.domeAuto_c.setChecked(False)
        self.domeAuto_c.setLayoutDirection(Qt.RightToLeft)
        self.domeAuto_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.domeAuto_c.clicked.connect(self.parent.domeFollow)

        w = w + 1
        self.grid.addWidget(self.domeConn2_l,w, 0)
        self.grid.addWidget(self.domeConn1_l,w, 1)
        self.grid.addWidget(self.domeStat_e, w, 2, 1, 2)
        self.grid.addWidget(self.domeAuto_l, w, 6)
        self.grid.addWidget(self.domeAuto_c, w, 7)




        #############################

        self.ventilators_l = QLabel("VENTILATORS: ")

        self.ventilators_c = QCheckBox()
        self.ventilators_c.setChecked(False)
        self.ventilators_c.setLayoutDirection(Qt.LeftToRight)
        self.ventilators_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/ToggleOnOrange.png)}::indicator:unchecked {image: url(./Icons/ToggleOffGreen.png)}")
        self.ventilators_c.clicked.connect(self.parent.VentilatorsOnOff)

        self.ventilators_e = QLineEdit()
        self.ventilators_e.setReadOnly(True)
        self.ventilators_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.ventilators_e.setText("--")





        self.domeShutter_l = QLabel("SHUTTER: ")
        self.domeShutter_c = QCheckBox("")
        self.domeShutter_c.setChecked(False)
        self.domeShutter_c.setLayoutDirection(Qt.RightToLeft)
        self.domeShutter_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        self.domeShutter_c.clicked.connect(self.parent.dome_openOrClose)

        self.domeShutter_e = QLineEdit()
        self.domeShutter_e.setText("--")
        self.domeShutter_e.setReadOnly(True)
        self.domeShutter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        w = w + 1
        self.grid.addWidget(self.ventilators_l, w, 0,1,2)
        self.grid.addWidget(self.ventilators_e, w, 2)
        self.grid.addWidget(self.ventilators_c, w, 3)

        self.grid.addWidget(self.domeShutter_l, w, 4)
        self.grid.addWidget(self.domeShutter_e, w, 5,1,2)
        self.grid.addWidget(self.domeShutter_c, w, 7)

        ##########################################



        self.domeAz_l = QLabel("DOME AZ: ")
        self.domeAz_e = QLineEdit()
        self.domeAz_e.setReadOnly(True)
        self.domeAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.domeNextAz_e = QLineEdit()
        self.domeNextAz_e.textChanged.connect(self.parent.domeAZ_check)

        self.domeStop_p = QPushButton('STOP')
        self.domeStop_p.clicked.connect(self.parent.dome_stop)

        self.domeSet_p = QPushButton('MOVE')
        self.domeSet_p.clicked.connect(self.parent.dome_move2Az)

        w = w + 1
        self.grid.addWidget(self.domeAz_l, w, 0,1,2)
        self.grid.addWidget(self.domeAz_e, w, 2)
        self.grid.addWidget(self.domeNextAz_e, w, 3)
        self.grid.addWidget(self.domeStop_p, w, 4)
        self.grid.addWidget(self.domeSet_p, w, 5,1,2)

        ############################################



        self.domeLights_l = QLabel("DOME LIGHTS: ")
        self.domeLights_c = QCheckBox("")
        self.domeLights_c.setChecked(False)
        self.domeLights_c.setLayoutDirection(Qt.LeftToRight)
        self.domeLights_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/ToggleOnOrange.png)}::indicator:unchecked {image: url(./Icons/ToggleOffGreen.png)}")
        self.domeLights_c.clicked.connect(self.parent.domeLightOnOff)

        self.domeLights_e = QLineEdit()
        self.domeLights_e.setReadOnly(True)
        self.domeLights_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.domeLights_e.setText("--")

        self.flatLights_l = QLabel("FLAT LIGHTS: ")
        self.flatLights_c = QCheckBox("")
        self.flatLights_e = QLineEdit()
        self.flatLights_e.setReadOnly(True)
        self.flatLights_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.flatLights_e.setText("--")
        self.flatLights_c.setChecked(False)
        self.flatLights_c.setLayoutDirection(Qt.LeftToRight)
        self.flatLights_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/ToggleOnOrange.png)}::indicator:unchecked {image: url(./Icons/ToggleOffGreen.png)}")
        self.flatLights_c.clicked.connect(self.parent.FlatLampOnOff)

        w = w + 1
        self.grid.addWidget(self.domeLights_l, w, 0,1,2)
        #self.grid.addWidget(self.domeLights_e, w, 2)
        self.grid.addWidget(self.domeLights_c, w, 2)

        self.grid.addWidget(self.flatLights_l, w, 3)
        #self.grid.addWidget(self.flatLights_e, w, 5)
        self.grid.addWidget(self.flatLights_c, w, 4)


        ############################################

        self.line2_l = QFrame()
        self.line2_l.setFrameShape(QFrame.HLine)
        self.line2_l.setFrameShadow(QFrame.Raised)
        w = w + 1
        self.grid.addWidget(self.line2_l, w, 0, 1, 8)

        ###################### PERYPHERIES ################

        self.mirrorFans_l = QLabel("MIRROR FANS: ")
        self.mirrorFans_c = QCheckBox("")
        self.mirrorFans_e = QLineEdit()
        self.mirrorFans_e.setReadOnly(True)
        self.mirrorFans_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.mirrorFans_e.setText("--")
        self.mirrorFans_c.setChecked(False)
        self.mirrorFans_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/ToggleOnOrange.png)}::indicator:unchecked {image: url(./Icons/ToggleOffGreen.png)}")
        self.mirrorFans_c.clicked.connect(self.parent.mirrorFansOnOff)

        self.telCovers_l = QLabel("MIRROR COVERS: ")
        self.telCovers_e = QLineEdit()
        self.telCovers_e.setReadOnly(True)
        self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telCovers_c = QCheckBox("")
        self.telCovers_c.setChecked(False)
        self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
        self.telCovers_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.telCovers_c.clicked.connect(self.parent.covers_openOrClose)

        w=w+1
        self.grid.addWidget(self.mirrorFans_l, w, 0,1,2)
        self.grid.addWidget(self.mirrorFans_e, w, 2)
        self.grid.addWidget(self.mirrorFans_c, w, 3)

        self.grid.addWidget(self.telCovers_l, w, 4)
        self.grid.addWidget(self.telCovers_e, w, 5,1,2)
        self.grid.addWidget(self.telCovers_c, w, 7)

        #self.grid.addWidget(self.openCovers_p, w, 5)
        #self.grid.addWidget(self.closeCovers_p, w, 6)

        #########################################################

        self.telM3_l = QLabel("M3: ")
        self.telM3_e = QLineEdit()
        self.telM3_e.setReadOnly(True)
        self.telM3_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telM3_e.setText("(TODO)")
        self.telM3_s = QComboBox()
        self.telM3_s.addItems(["Imager", "Spectro", "empty"])
        self.telM3_p = QPushButton('SET')
        self.telM3_p.setStyleSheet(" color: gray;")


        w=w+1
        self.grid.addWidget(self.telM3_l, w, 0,1,2)
        self.grid.addWidget(self.telM3_e, w, 2)
        self.grid.addWidget(self.telM3_s, w, 3)
        self.grid.addWidget(self.telM3_p, w, 4)



        ##########################################################

        self.comRotator1_l = QLabel(" ")
        self.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))
        self.telRotator1_l = QLabel("ROTATOR: ")
        self.comRotator1_l.setText("\U0001F534")
        self.telRotator1_l.setStyleSheet("color: rgb(150,0,0);")
        self.telRotator1_l.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.telRotator1_e = QLineEdit()
        self.telRotator1_e.setReadOnly(True)
        self.telRotator1_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.setRotator1_e = QLineEdit()
        self.setRotator1_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.setRotator1_e.setReadOnly(True)
        self.setRotator1_p = QPushButton('SET')
        self.setRotator1_p.setStyleSheet(" color: gray;")

        w=w+1
        self.grid.addWidget(self.comRotator1_l, w, 0)
        self.grid.addWidget(self.telRotator1_l, w, 1)
        self.grid.addWidget(self.telRotator1_e, w, 2)
        self.grid.addWidget(self.setRotator1_e, w, 3)
        self.grid.addWidget(self.setRotator1_p, w, 4)


        ##########################################################

        self.comFilter_l = QLabel(" ")
        self.telFilter_l = QLabel("FILTER: ")
        self.comFilter_l.setText("\U0001F534")
        self.telFilter_l.setStyleSheet("color: rgb(150,0,0);")
        self.telFilter_e = QLineEdit()
        self.telFilter_e.setReadOnly(True)
        self.telFilter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telFilter_s = QComboBox()
        self.telFilter_p = QPushButton('SET')
        self.telFilter_p.clicked.connect(self.parent.set_filter)

        self.FilterAutoOffset_l = QLabel("AUTO OFFSET:")
        self.FilterAutoOffset_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.FilterAutoOffset_c = QCheckBox()
        self.FilterAutoOffset_c.setChecked(True)
        self.FilterAutoOffset_c.setLayoutDirection(Qt.RightToLeft)
        self.FilterAutoOffset_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOnGrey.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")


        w=w+1

        self.grid.addWidget(self.comFilter_l, w, 0)
        self.grid.addWidget(self.telFilter_l, w, 1)
        self.grid.addWidget(self.telFilter_e, w, 2)
        self.grid.addWidget(self.telFilter_s, w, 3)
        self.grid.addWidget(self.telFilter_p, w, 4)
        self.grid.addWidget(self.FilterAutoOffset_l, w,5,1,2)
        self.grid.addWidget(self.FilterAutoOffset_c, w,7)

        ######################################################

        self.focusConn_l = QLabel(" ")
        self.focusConn_l.setText("\U0001F534")
        self.telFocus_l = QLabel("FOCUS: ")
        self.telFocus_l.setStyleSheet("color: rgb(150,0,0);")
        self.telFocus_e = QLineEdit()
        self.telFocus_e.setReadOnly(True)
        self.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.setFocus_s = QSpinBox()
        if self.parent.active_tel != None:
            tel = self.parent.obs_tel_tic_names[self.parent.active_tel_i]
            if tel=="zb08":
                self.setFocus_s.setRange(0,28000)
                self.setFocus_s.setSingleStep(50)
            elif tel=="wk06":
                self.setFocus_s.setRange(0,28000)
                self.setFocus_s.setSingleStep(50)
            elif tel=="jk15":
                self.setFocus_s.setRange(0,50000)
                self.setFocus_s.setSingleStep(50)
        self.setFocus_s.valueChanged.connect(self.parent.focusClicked)
        self.setFocus_p = QPushButton('SET')
        self.setFocus_p.clicked.connect(self.parent.set_focus)
        self.telAutoFocus_l = QLabel("AUTO ADJUST:")
        self.telAutoFocus_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.telAutoFocus_c = QCheckBox()
        self.telAutoFocus_c.setChecked(True)
        self.telAutoFocus_c.setLayoutDirection(Qt.RightToLeft)
        self.telAutoFocus_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOnGrey.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")

        w = w + 1
        self.grid.addWidget(self.focusConn_l, w, 0)
        self.grid.addWidget(self.telFocus_l, w, 1)
        self.grid.addWidget(self.telFocus_e, w, 2)
        self.grid.addWidget(self.setFocus_s, w, 3)
        self.grid.addWidget(self.setFocus_p, w, 4)
        self.grid.addWidget(self.telAutoFocus_l, w,5,1,2)
        self.grid.addWidget(self.telAutoFocus_c, w,7)

        ##########################################################

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)

        w = w + 1
        self.grid.addWidget(self.line_l, w, 0, 1, 8)

        w = w + 1
        self.testowyPocisk_p = QPushButton('Update')
        self.testowyPocisk_p.clicked.connect(self.parent.force_update)
        self.grid.addWidget(self.testowyPocisk_p, w, 0,1,2)

        self.config_p = QPushButton("\u2699")
        self.grid.addWidget(self.config_p, w, 7)


        ##########################################################

        self.setLayout(self.grid)

        self.setEq_r.toggled.connect(self.select)
        self.setAltAz_r.toggled.connect(self.select)

        self.nextRa_e.textChanged.connect(self.updateNextRaDec)
        self.nextDec_e.textChanged.connect(self.updateNextRaDec)
        self.nextAlt_e.textChanged.connect(self.updateNextRaDec)
        self.nextAz_e.textChanged.connect(self.updateNextRaDec)


        del tmp




    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        super().closeEvent(event)

class PulseWindow(QWidget):
    def __init__(self, parent):
        super(PulseWindow, self).__init__()
        self.parent = parent
        #self.setGeometry(self.parent.aux_geometry[0], self.parent.aux_geometry[1], self.parent.aux_geometry[2],self.parent.aux_geometry[3])
        self.mkUI()
        self.sumDec_e.setText(str(self.parent.pulseDec))
        self.sumRa_e.setText(str(self.parent.pulseRa))
    def mkUI(self):
        if True:
            self.setWindowTitle("Pulse movements")

            grid = QGridLayout()


            w = 1
            w = w + 1
            self.up_p = QPushButton('\u2191')
            self.up_p.clicked.connect(self.parent.pulse_up)
            grid.addWidget(self.up_p, w, 2,)

            w = w + 1
            self.left_p = QPushButton('\u2190')
            self.left_p.clicked.connect(self.parent.pulse_left)
            self.right_p = QPushButton('\u2192')
            self.right_p.clicked.connect(self.parent.pulse_right)
            grid.addWidget(self.left_p, w, 1)
            grid.addWidget(self.right_p, w, 3)

            w = w + 1
            self.down_p = QPushButton('\u2193')
            self.down_p.clicked.connect(self.parent.pulse_down)
            grid.addWidget(self.down_p, w, 2)

            self.line2_l = QFrame()
            self.line2_l.setFrameShape(QFrame.HLine)
            self.line2_l.setFrameShadow(QFrame.Raised)
            w = w + 1
            grid.addWidget(self.line2_l,w,0,1,5)

            self.pulseRa_l = QLabel("Ra PULSE:")
            self.pulseRa_e = QLineEdit()
            self.pulseRa_e.setText("5")
            self.pulseRa_e.setMaximumWidth(50)
            self.sumRa_l = QLabel("Ra SUM:")
            self.sumRa_e = QLineEdit()
            self.sumRa_e.setReadOnly(True)
            self.sumRa_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.sumRa_e.setMaximumWidth(50)
            self.unitsRa_l = QLabel("[arc sec]")

            w = w + 1
            grid.addWidget(self.pulseRa_l, w, 0)
            grid.addWidget(self.pulseRa_e, w, 1)
            grid.addWidget(self.sumRa_l, w, 2)
            grid.addWidget(self.sumRa_e, w, 3)
            grid.addWidget(self.unitsRa_l, w, 4)


            self.pulseDec_l = QLabel("Dec PULSE:")
            self.pulseDec_e = QLineEdit()
            self.pulseDec_e.setText("5")
            self.pulseDec_e.setMaximumWidth(50)
            self.sumDec_l = QLabel("Dec SUM:")
            self.sumDec_e = QLineEdit()
            self.sumDec_e.setReadOnly(True)
            self.sumDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
            self.sumDec_e.setMaximumWidth(50)
            self.unitsDec_l = QLabel("[arc sec]")

            w = w + 1
            grid.addWidget(self.pulseDec_l, w, 0)
            grid.addWidget(self.pulseDec_e, w, 1)
            grid.addWidget(self.sumDec_l, w, 2)
            grid.addWidget(self.sumDec_e, w, 3)
            grid.addWidget(self.unitsDec_l, w, 4)


            #grid.setColumnMinimumWidth(0, 100)
            #grid.setColumnMinimumWidth(1, 100)
            #grid.setColumnMinimumWidth(2, 30)
            #grid.setColumnMinimumWidth(3, 30)
            #grid.setColumnMinimumWidth(4, 30)
            #grid.setRowStretch(0, 0)
            #grid.setRowStretch(1, 1)
            #grid.setRowStretch(2, 0)
            self.setLayout(grid)
            self.show()
            self.raise_()
