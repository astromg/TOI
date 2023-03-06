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
from PyQt5.QtWidgets import QWidget, QLabel, QCheckBox, QLineEdit, QPushButton, QSpinBox, QGridLayout, QFrame, QComboBox, \
    QRadioButton
from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
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
        if self.setEq_r.isChecked():
            self.nextRa_e.setStyleSheet("background-color: rgb(245, 178, 79);")
            self.nextDec_e.setStyleSheet("background-color: rgb(245, 178, 79);")
            ok = False
            try:
                ra = self.nextRa_e.text()
                dec = self.nextDec_e.text()
                ok = True
            except:
                ok = False
            if ok:
                try:
                  az, alt = RaDec2AltAz(self.parent.observatory, ephem.now(), ra, dec)
                  az = arcDeg2float(str(az))
                  alt = arcDeg2float(str(alt))

                  self.nextAlt_e.setText("%.4f" % alt)
                  self.nextAz_e.setText("%.4f" % az)
                  self.nextRa_e.setStyleSheet("background-color: white;")
                  self.nextDec_e.setStyleSheet("background-color: white")
                except: pass

        if self.setAltAz_r.isChecked():
            self.nextAlt_e.setStyleSheet("background-color: rgb(245, 178, 79);")
            self.nextAz_e.setStyleSheet("background-color: rgb(245, 178, 79);")
            ok = False
            try:
                alt = self.nextAlt_e.text()
                az = self.nextAz_e.text()
                ok = True
            except:
                ok = False
            if ok:
                try:
                  ra, dec = AltAz2RaDec(self.parent.observatory, ephem.now(), alt, az)

                  self.nextRa_e.setText(str(ra))
                  self.nextDec_e.setText(str(dec))
                  self.nextAlt_e.setStyleSheet("background-color: white;")
                  self.nextAz_e.setStyleSheet("background-color: white")
                except: pass

    def update_(self):
        if self.setEq_r.isChecked():
            self.nextAz_e.setReadOnly(True)
            self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextAlt_e.setReadOnly(True)
            self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextRa_e.setReadOnly(False)
            self.nextRa_e.setStyleSheet("background-color: white;")
            self.nextDec_e.setReadOnly(False)
            self.nextDec_e.setStyleSheet("background-color: white;")

        if self.setAltAz_r.isChecked():
            self.nextAz_e.setReadOnly(False)
            self.nextAz_e.setStyleSheet("background-color: white;")
            self.nextAlt_e.setReadOnly(False)
            self.nextAlt_e.setStyleSheet("background-color: white;")
            self.nextRa_e.setReadOnly(True)
            self.nextRa_e.setStyleSheet("background-color: rgb(233, 233, 233);")
            self.nextDec_e.setReadOnly(True)
            self.nextDec_e.setStyleSheet("background-color: rgb(233, 233, 233);")

    # =================== OKNO GLOWNE ====================================
    def updateUI(self):

        self.setWindowTitle('')
        self.setStyleSheet("font-size: 11pt;")

        local_dic={"WK06":'WK06 Mount Manual Controll',"ZB08":'ZB08 Mount Manual Controll',"JK15":'JK15 Mount Manual Controll',"WG25":'WG25 Mount Manual Controll',"SIM":'SIM Mount Manual Controll'}
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
        self.mntConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))
        #self.add_subscription_client_side(address=self.get_address('get_telescope_connected'),
                                          #name='mntConn1_l',
                                          #delay=self.subscriber_delay,
                                          #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                                          #async_callback_method=[
                                              #self._update_connection_indicator(self.mntConn1_l, self.mntConn2_l)])

        self.mntStat_l = QLabel("MOUNT STATUS: ")
        self.mntStat_e = QLineEdit()
        self.mntStat_e.setReadOnly(True)
        self.mntStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.mntStat_e.setText("(TODO)")

        w=0
        self.grid.addWidget(self.mntConn2_l, w, 0)
        self.grid.addWidget(self.mntConn1_l, w, 1)

        self.grid.addWidget(self.mntStat_l, w, 4)
        self.grid.addWidget(self.mntStat_e, w, 5, 1, 3)

        ########################################

        self.mntEpoch_l = QLabel("EPOCH: ")
        self.mntEpoch_e = QLineEdit("2000")

        self.mntAirmass_l = QLabel("AIRMASS: ")
        self.mntAirmass_e = QLineEdit()
        self.mntAirmass_e.setReadOnly(True)
        self.mntAirmass_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.mntAirmass_e.setText("(TODO)")

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
        #self.add_subscription(address=self.get_address('get_telescope_rightascension'),
                              #name='mntRa_e',
                              #delay=self.subscriber_delay,
                              #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              #async_callback_method=[self.update_field_callback(self.mntRa_e, name='mntRa_e')])

        self.mntDec_l = QLabel("TELESCOPE DEC [d]:")
        self.mntDec_e = QLineEdit("00:00:00")
        self.mntDec_e.setReadOnly(True)
        self.mntDec_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        #self.add_subscription(address=self.get_address('get_telescope_declination'),
                              #name='mntDec_e',
                              #delay=self.subscriber_delay,
                              #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              #async_callback_method=[self.update_field_callback(self.mntDec_e, name='mntDec_e')])

        self.nextRa_l = QLabel("NEXT RA: ")
        self.nextRa_e = QLineEdit("00:00:00")

        self.nextDec_l = QLabel("NEXT DEC: ")
        self.nextDec_e = QLineEdit("00:00:00")

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
        #self.add_subscription(address=self.get_address('get_telescope_azimuth'),
                              #name='mntAz_e',
                              #delay=self.subscriber_delay,
                              #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              #async_callback_method=[self.update_field_callback(self.mntAz_e, name='mntAz_e')])

        self.mntAlt_l = QLabel("TELESCOPE ALT [d]: ")
        self.mntAlt_e = QLineEdit()
        self.mntAlt_e.setReadOnly(True)
        self.mntAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        #self.add_subscription(address=self.get_address('get_telescope_altitude'),
                              #name='mntAlt_e',
                              #delay=self.subscriber_delay,
                              #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              #async_callback_method=[self.update_field_callback(self.mntAlt_e, name='mntAlt_e')])


        self.nextAz_l = QLabel("NEXT AZ: ")
        self.nextAz_e = QLineEdit()
        self.nextAz_e.setReadOnly(True)
        self.nextAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.nextAlt_l = QLabel("NEXT ALT: ")
        self.nextAlt_e = QLineEdit()
        self.nextAlt_e.setReadOnly(True)
        self.nextAlt_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        w = w + 1
        self.grid.addWidget(self.mntAz_l, w, 0,1,2)
        self.grid.addWidget(self.mntAz_e, w, 2)
        self.grid.addWidget(self.nextAz_e, w, 3)

        self.grid.addWidget(self.mntAlt_l, w, 4)
        self.grid.addWidget(self.mntAlt_e, w, 5)
        self.grid.addWidget(self.nextAlt_e, w, 6,1,2)
        self.grid.addWidget(self.setAltAz_r, w, 8)

        ###############################################

        self.tracking_l = QLabel("TRACKING: ")
        self.tracking_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.tracking_c = QCheckBox()
        self.tracking_c.setChecked(False)
        self.tracking_c.setLayoutDirection(Qt.RightToLeft)
        # self.mntCovers_c.setStyleSheet("background-color: yellow")
        self.tracking_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.tracking_c.clicked.connect(self.parent.mount_trackOnOff)

        self.guiding_c = QCheckBox("GUIDING: ")
        self.guiding_c.setChecked(False)
        self.guiding_c.setLayoutDirection(Qt.RightToLeft)
        # self.mntCovers_c.setStyleSheet("background-color: yellow")
        self.guiding_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")


        w = w + 1
        self.grid.addWidget(self.guiding_c, w, 4)
        self.grid.addWidget(self.tracking_l, w, 6)
        self.grid.addWidget(self.tracking_c, w, 7)


        #################################################

        self.telPark_p = QPushButton('PARK')
        self.telPark_p.clicked.connect(self.parent.park_mount)

        self.mntStop_p = QPushButton('STOP')
        self.mntStop_p.clicked.connect(self.parent.abort_slew)

        self.Slew_p = QPushButton('SLEW')
        self.Slew_p.clicked.connect(self.parent.mount_slew)
        #self.Slew_p.clicked.connect(lambda: self._slew_btn_clicked(rad_btnRaDec=self.setEq_r,
                                                                   #rad_btnAzAlt=self.setAltAz_r,
                                                                   #radec_fields_source=(self.nextRa_e, self.nextDec_e),
                                                                   #azalt_fields_source=(self.nextAz_e, self.nextAlt_e)))
        w = w + 1
        self.grid.addWidget(self.telPark_p, w, 0,1,2)
        self.grid.addWidget(self.mntStop_p, w, 3)
        self.grid.addWidget(self.Slew_p, w, 5, 1, 2)
        #################################################


        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        w = w + 1
        self.grid.addWidget(self.line_l, w, 0, 1, 7)

        ################## DOME ##########################################


        self.domeConn1_l = QLabel("DOME")
        self.domeConn2_l = QLabel(" ")
        self.domeConn2_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))


        self.domeStat_l = QLabel("DOME STATUS: ")
        self.domeStat_e = QLineEdit()
        self.domeStat_e.setReadOnly(True)
        self.domeStat_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        w = w + 1
        self.grid.addWidget(self.domeConn2_l,w,0)
        self.grid.addWidget(self.domeConn1_l,w,1)
        self.grid.addWidget(self.domeStat_l, w, 4)
        self.grid.addWidget(self.domeStat_e, w, 5, 1, 2)


        ##########################################

        self.domeAuto_l  = QLabel("SLAVE:")
        self.domeAuto_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.domeAuto_c = QCheckBox()
        self.domeAuto_c.setChecked(True)
        self.domeAuto_c.setLayoutDirection(Qt.RightToLeft)
        self.domeAuto_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        self.domeAz_l = QLabel("DOME AZ: ")
        self.domeAz_e = QLineEdit()
        self.domeAz_e.setReadOnly(True)
        self.domeAz_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")


        #self.add_subscription(address=self.get_address('get_dome_azimuth'),
                              #name='domeAz_e',
                              #delay=self.subscriber_delay,
                              #time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              #async_callback_method=[self.update_field_callback(self.domeAz_e, name='domeAz_e')])
        self.domeNextAz_e = QLineEdit()

        self.domeSet_p = QPushButton('MOVE')
        self.domeSet_p.clicked.connect(self.parent.dome_move2Az)

        w = w + 1
        self.grid.addWidget(self.domeAz_l, w, 0,1,2)
        self.grid.addWidget(self.domeAz_e, w, 2)
        self.grid.addWidget(self.domeNextAz_e, w, 3)
        self.grid.addWidget(self.domeSet_p, w, 5)
        self.grid.addWidget(self.domeAuto_l, w, 6)
        self.grid.addWidget(self.domeAuto_c, w, 7)

        #############################

        self.domeLights_l = QLabel("DOME LIGHTS: ")
        self.domeLights_c = QCheckBox("")
        self.domeLights_c.setChecked(False)
        self.domeLights_c.setLayoutDirection(Qt.LeftToRight)
        self.domeLights_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        self.domeLights_e = QLineEdit()
        self.domeLights_e.setReadOnly(True)
        self.domeLights_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.domeLights_e.setText("(TODO)")

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
        self.grid.addWidget(self.domeLights_l, w, 0,1,2)
        self.grid.addWidget(self.domeLights_e, w, 2)
        self.grid.addWidget(self.domeLights_c, w, 3)

        self.grid.addWidget(self.domeShutter_l, w, 4)
        self.grid.addWidget(self.domeShutter_e, w, 5,1,2)
        self.grid.addWidget(self.domeShutter_c, w, 7)

        ############################################

        self.line2_l = QFrame()
        self.line2_l.setFrameShape(QFrame.HLine)
        self.line2_l.setFrameShadow(QFrame.Raised)
        w = w + 1
        self.grid.addWidget(self.line2_l, w, 0, 1, 7)

        ###################### PERYPHERIES ################

        self.flatLights_l = QLabel("FLAT LIGHTS: ")
        self.flatLights_c = QCheckBox("")
        self.flatLights_e = QLineEdit()
        self.flatLights_e.setReadOnly(True)
        self.flatLights_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.flatLights_e.setText("(TODO)")
        self.flatLights_c.setChecked(False)
        self.flatLights_c.setLayoutDirection(Qt.LeftToRight)
        self.flatLights_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")



        self.telCovers_l = QLabel("MIRROR COVERS: ")
        self.telCovers_e = QLineEdit()
        self.telCovers_e.setReadOnly(True)
        self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telCovers_c = QCheckBox("")
        self.telCovers_c.setChecked(False)
        self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
        # self.telCovers_c.setStyleSheet("background-color: yellow")
        self.telCovers_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        w=w+1
        self.grid.addWidget(self.flatLights_l, w, 0,1,2)
        self.grid.addWidget(self.flatLights_e, w, 2)
        self.grid.addWidget(self.flatLights_c, w, 3)

        self.grid.addWidget(self.telCovers_l, w, 4)
        self.grid.addWidget(self.telCovers_e, w, 5,1,2)
        self.grid.addWidget(self.telCovers_c, w, 7)

        #########################################################

        self.telM3_l = QLabel("M3: ")
        self.telM3_e = QLineEdit()
        self.telM3_e.setReadOnly(True)
        self.telM3_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telM3_e.setText("(TODO)")
        self.telM3_s = QComboBox()
        self.telM3_s.addItems(["Imager", "Spectro", "empty"])
        self.telM3_p = QPushButton('SET')

        self.fans_l = QLabel("FANS: ")
        self.fans_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.fans_c = QCheckBox()
        self.fans_c.setChecked(False)
        self.fans_c.setLayoutDirection(Qt.RightToLeft)
        self.fans_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        w=w+1
        self.grid.addWidget(self.telM3_l, w, 0,1,2)
        self.grid.addWidget(self.telM3_e, w, 2)
        self.grid.addWidget(self.telM3_s, w, 3)
        self.grid.addWidget(self.telM3_p, w, 4)
        self.grid.addWidget(self.fans_l, w, 6)
        self.grid.addWidget(self.fans_c, w, 7)

        ##########################################################


        self.telFilter_l = QLabel("FILTER: ")
        self.telFilter_e = QLineEdit()
        self.telFilter_e.setReadOnly(True)
        self.telFilter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telFilter_s = QComboBox()
        #self.telFilter_s.addItems(["V", "I", "u", "v", "b"])
        self.telFilter_p = QPushButton('SET')
        self.telFilter_p.clicked.connect(self.parent.set_filter)

        w=w+1
        self.grid.addWidget(self.telFilter_l, w, 0,1,2)
        self.grid.addWidget(self.telFilter_e, w, 2)
        self.grid.addWidget(self.telFilter_s, w, 3)
        self.grid.addWidget(self.telFilter_p, w, 4)

        ######################################################

        self.telFocus_l = QLabel("FOCUS: ")
        self.telFocus_e = QLineEdit()
        self.telFocus_e.setReadOnly(True)
        self.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.setFocus_s = QSpinBox()
        tel = self.parent.obs_tel_tic_names[self.parent.active_tel_i]
        if tel=="zb08":
            self.setFocus_s.setRange(0,28000)
            self.setFocus_s.setSingleStep(50)
        self.setFocus_s.valueChanged.connect(self.parent.focusClicked)
        self.setFocus_p = QPushButton('SET')
        self.setFocus_p.clicked.connect(self.parent.set_focus)
        self.telAutoFocus_l = QLabel("AUTO OFFSET:")
        self.telAutoFocus_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.telAutoFocus_c = QCheckBox()
        self.telAutoFocus_c.setChecked(True)
        self.telAutoFocus_c.setLayoutDirection(Qt.RightToLeft)
        self.telAutoFocus_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        w = w + 1
        self.grid.addWidget(self.telFocus_l, w, 0,1,2)
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
        self.grid.addWidget(self.line_l, w, 0, 1, 7)

        ##########################################################

        self.setLayout(self.grid)

        self.setEq_r.toggled.connect(self.update_)
        self.setAltAz_r.toggled.connect(self.update_)

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

    @qs.asyncSlot()
    async def _take_Fol(self):
        """Method for 'take_control' button """
        # todo co się ma dziać w razie nieudanego przejęcia kontroli?

        # todo czy po zamknięciu apki ma być zwracana kontrola?
        try:
            response = await self.client_api.put_async(address=self.get_address("put_take_control"),
                                                       time_of_data_tolerance=0.5,
                                                       parameters_dict={'timeout_reservation': time.time() + 30},
                                                       no_wait=False)
            if response and response.value.v is True:
                logger.info("Successfully taken control over telescope")
            else:
                logger.info("Can not take control over telescope: Normal")
        except CommunicationRuntimeError:
            logger.info("Can not take control over telescope: CommunicationRuntimeError")
        except CommunicationTimeoutError:
            logger.info("Can not take control over telescope: CommunicationTimeoutError")

    @qs.asyncSlot()
    async def _move_btn_clicked(self, field_source: QLineEdit):
        """Method for 'move' button"""
        try:
            value = float(field_source.text())
        except ValueError:
            logger.warning(f"Can not set azimuth because can not parse {field_source.text()} to float")
            return
            # todo czy ma być jakaś obsługa błędów? to już po stronie QLabelEdit chyba np jakieś zaznaczanie na czerwono jak jest żle
        await self.put_base_request(address=self.get_address("put_dome_azimuth"),
                                    parameters_dict={'Azimuth': value}, no_wait=False,
                                    action="move dome in alpaca")

    @qs.asyncSlot()
    async def _shutter_checkbox_change(self, checkbox: QCheckBox):
        """Method for shutter checkbox changed"""
        state = checkbox.isChecked()
        if state:
            address = self.get_address("put_dome_shutter_open")
            action = "open"
        else:
            address = self.get_address("put_dome_shutter_close")
            action = "close"

        checkbox.blockSignals(True)  # Block signals so that you don't call this method recursively
        checkbox.setEnabled(False)  # avoid check again before react for first toggle
        try:
            response = await self.client_api.put_async(address=address, no_wait=False)
            if response and response.value and response.status and (response.value.v is not None):
                logger.info(f"Successfully shutter {action}")
            else:
                logger.info(f"Can not {action} shutter: Normal")
                checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except CommunicationRuntimeError:
            logger.info(f"Can not {action} shutter: CommunicationRuntimeError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back

        except CommunicationTimeoutError:
            logger.info(f"Can not {action} shutter: CommunicationTimeoutError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            checkbox.setEnabled(True)  # allow toggle
            checkbox.blockSignals(False)  # unblock signals

    @qs.asyncSlot()
    async def _slew_btn_clicked(self, rad_btnRaDec: QRadioButton, rad_btnAzAlt: QRadioButton,
                                radec_fields_source: Tuple[QLineEdit, QLineEdit],
                                azalt_fields_source: Tuple[QLineEdit, QLineEdit]):
        """Method for 'slew' button"""
        ra_field, dec_field = radec_fields_source
        az_field, alt_field = azalt_fields_source
        # todo co z przeliczaniem tych Ra Dec w jakiej postaci to ma być? 5.3323 czy jakieś minuty godziny?
        if rad_btnRaDec.isChecked():
            # todo tutaj coś ma być ustawione zanim bedzie przesuwać po RaDec i co robią te pozostałe metody?
            logger.info(f"Slewing by RaDec")
            ra = ra_field.text()
            dec = dec_field.text()
            data = {"RightAscension": ra, "Declination": dec}
            result = await self.client_api.put_async(address=self.get_address("put_telescope_slewtocoordinates"),
                                                     parameters_dict=data, no_wait=False)
        elif rad_btnAzAlt.isChecked():
            logger.info(f"Slewing by AzAlt")
            az = az_field.text()
            alt = alt_field.text()
            data = {"Azimuth": az, "Altitude": alt}
            result = await self.client_api.put_async(address=self.get_address("put_telescope_slewtoaltaz"),
                                                     parameters_dict=data, no_wait=False)
        else:
            logger.error("Any known checkbox wasn't check")
            return
        if result.status:
            logger.info("Successfully slew mount")
        else:
            logger.info(f"Can not slew mount error from server: {result.error}")

    @qs.asyncSlot()
    async def _tracking_checkbox_change(self, checkbox: QCheckBox):
        """Method for 'tracking' checkbox"""
        state = checkbox.isChecked()
        address = self.get_address("put_telescope_tracking")
        if state:
            action = "ON"
        else:
            action = "OFF"
        checkbox.blockSignals(True)  # Block signals so that you don't call this method recursively
        checkbox.setEnabled(False)  # avoid check again before react for first toggle
        try:
            response = await self.client_api.put_async(address=address, no_wait=False,
                                                       parameters_dict={"Tracking": state})
            if response and response.value and response.status and (response.value.v is not None):
                logger.info(f"Successfully turn {action} tracking")
            else:
                logger.info(f"Can not turn {action} tracking: Normal")
                checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except CommunicationRuntimeError:
            logger.info(f"Can turn {action} tracking: CommunicationRuntimeError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except CommunicationTimeoutError:
            logger.info(f"Can turn {action} tracking: CommunicationTimeoutError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            checkbox.setEnabled(True)  # allow toggle
            checkbox.blockSignals(False)  # unblock signals

    @qs.asyncSlot()
    async def _stop_btn_clicked(self):
        """Method for 'stop' button"""
        # todo w orginale było 'abortslew' i stop 'tracking'
        await self.put_base_request(address=self.get_address("put_telescope_abortslew"), no_wait=False,
                                    action="abort slew alpaca")

    @qs.asyncSlot()
    async def _park_btn_clicked(self):
        """Method for 'park' button"""
        await self.put_base_request(address=self.get_address("put_telescope_park"), no_wait=False,
                                    action="park telescope")

    @staticmethod
    def _update_connection_indicator(field: QLabel, field2: QLabel):
        name = 'Connection checker'

        async def callback(result):
            is_connected = False
            if not result:
                # server ocabox nie odpowiada - jest wyłączony albo na złym porcie
                logger.debug(f"Callback for cycle request named {name} not connect: Server ocabox not response")
            else:
                if result[0].value and result[0].value.v:
                    is_connected = result[0].value.v
                else:
                    logger.debug(f"Callback for cycle request named {name} not connect: Alpaca server not response: "
                                 f"Error: {result[0].error}")
            if is_connected:
                field.setText("CONNECTED")
                field2.setPixmap(QtGui.QPixmap('./Icons/green.png').scaled(20, 20))
            else:
                field.setText("NO CONNECTION")
                field2.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))

        return callback

    @staticmethod
    def _update_dome_status_callback(field, name="Dome status callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                val = result[0].value.v
                if val == 0:
                    tex_to_put = "Open"
                elif val == 1:
                    tex_to_put = "Closed"
                elif val == 2:
                    tex_to_put = "Opening"
                elif val == 3:
                    tex_to_put = "Closing"
                elif val == 4:
                    tex_to_put = "Shutter status error"
                else:
                    tex_to_put = f"{val}"
                field.setText(tex_to_put)  # update field in GUI

        return callback

    @staticmethod
    def _update_current_user_callback(field, name="Current user callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                val = result[0].value.v
                tex_to_put = None
                if isinstance(val, dict):
                    tex_to_put = val.get('name', None)
                    tex_to_put = f"{val.get('name', tex_to_put)}"

                field.setText(tex_to_put)  # update field in GUI

        return callback
