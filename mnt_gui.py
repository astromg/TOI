#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------
import logging
import os

import qasync as qs
from PyQtX.QtCore import Qt
from PyQtX.QtWidgets import QCompleter, QWidget, QLabel, QCheckBox, QLineEdit, QPushButton, QSpinBox, QGridLayout, QFrame, QComboBox, QRadioButton, QHBoxLayout
from pyaraucaria.coordinates import *
from qasync import QEventLoop

from PyQtX import QtCore

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from toi_lib import *
from base_window import BaseWindow
from toi_theme import theme

logger = logging.getLogger(__name__)


class MntGui(BaseWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        BaseWindow.__init__(self)
        BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)

        self.parent = parent
        self.set_initial_geometry(
            self.parent.mnt_geometry[0],
            self.parent.mnt_geometry[1],
            self.parent.mnt_geometry[2],
            self.parent.mnt_geometry[3]
        )
        self.updateUI()
        self.show()
        self.raise_()

    STAT_STYLE = "font-size: 13pt; font-weight: bold;"     # status montazu: wiekszy, przez dwie kolumny

    FOCUS_MAX = {"wk06": 28000, "zb08": 28000, "jk15": 50000}     # gorna granica pola SET fokusera
    FOCUS_MAX_DEFAULT = 100000

    def updateNextRaDec(self):
        # wolane przy kazdej zmianie pol (zwykly slot Qt): wyjatek stad zamknalby cale TOI
        try:
            self._updateNextRaDec()
        except Exception as e:
            logger.warning(f'TOI: next RA/Dec/Alt/Az: {e!r}')
            self.parent.nextOB_ok = False

    def _updateNextRaDec(self):
        theme.paint(self.nextRa_e, bg="input_bg")
        theme.paint(self.nextDec_e, bg="input_bg")
        theme.paint(self.nextAlt_e, bg="input_bg")
        theme.paint(self.nextAz_e, bg="input_bg")
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
                    theme.paint(self.nextRa_e, bg="warn2_bg")
                    theme.paint(self.nextDec_e, bg="warn2_bg")
            if self.parent.nextOB_ok:
                if ":" in ra:
                    try:
                        if float(ra.split(":")[0]) < 0 or float(ra.split(":")[0]) > 24:
                            self.parent.nextOB_ok = False
                            theme.paint(self.nextRa_e, bg="warn2_bg")
                    except ValueError: pass
                else:
                    if True:
                        self.parent.nextOB_ok = False
                        theme.paint(self.nextRa_e, bg="warn2_bg")
                if ":" in dec:
                    try:
                        if float(dec.split(":")[0]) < -90 or float(dec.split(":")[0]) > 90:
                            self.parent.nextOB_ok = False
                            theme.paint(self.nextDec_e, bg="warn2_bg")
                    except ValueError: pass
                else:
                    if True:
                        self.parent.nextOB_ok = False
                        theme.paint(self.nextDec_e, bg="warn2_bg")

        if self.setAltAz_r.isChecked():
            alt = self.nextAlt_e.text()
            az = self.nextAz_e.text()
            if len(str(alt)) > 0 and len(str(az)) > 0:
                self.parent.nextOB_ok = True
            else: self.parent.nextOB_ok = None
            if self.parent.nextOB_ok:
                try:
                    float(alt), float(az)      # ephem przyjmuje tez "12:30", dalej liczymy na stopniach
                    ra, dec = AltAz2RaDec(self.parent.observatory, ephem.now(), alt, az)
                    self.nextRa_e.setText(str(ra))
                    self.nextDec_e.setText(str(dec))
                except:
                    self.parent.nextOB_ok = False
                    theme.paint(self.nextAlt_e, bg="warn2_bg")
                    theme.paint(self.nextAz_e, bg="warn2_bg")
        if self.parent.nextOB_ok:
            if float(alt) < self.parent.cfg_alt_limits["min"] or float(alt) > self.parent.cfg_alt_limits["max"] :
                self.parent.nextOB_ok = False
                theme.paint(self.nextAlt_e, bg="warn2_bg")

            if float(az) > 360 or float(az)<0:
                self.parent.nextOB_ok = False
                theme.paint(self.nextAz_e, bg="warn2_bg")
        if self.parent.nextOB_ok:
            airmass = calc_airmass(float(alt))
            if airmass != None:
                self.nextAirmass_e.setText("%.1f" % airmass)
            else:
                self.nextAirmass_e.setText(" -- ")
        if self.parent.nextOB_ok or self.parent.nextOB_ok == None:
            if self.setEq_r.isChecked():
                theme.paint(self.nextAlt_e, bg="field_bg")
                theme.paint(self.nextAz_e, bg="field_bg")
                theme.paint(self.nextRa_e, bg="input_bg")
                theme.paint(self.nextDec_e, bg="input_bg")
            elif self.setAltAz_r.isChecked():
                theme.paint(self.nextAlt_e, bg="input_bg")
                theme.paint(self.nextAz_e, bg="input_bg")
                theme.paint(self.nextRa_e, bg="field_bg")
                theme.paint(self.nextDec_e, bg="field_bg")
        if  self.parent.nextOB_ok:
            if float(alt) > 0 and float(alt) < 30:
                theme.paint(self.nextAlt_e, bg="warn_soft_bg")

    def select(self):
        if self.setEq_r.isChecked():
            self.nextAz_e.setReadOnly(True)
            theme.paint(self.nextAz_e, bg="field_bg")
            self.nextAlt_e.setReadOnly(True)
            theme.paint(self.nextAlt_e, bg="field_bg")
            self.nextRa_e.setReadOnly(False)
            theme.paint(self.nextRa_e, bg="input_bg")
            self.nextDec_e.setReadOnly(False)
            theme.paint(self.nextDec_e, bg="input_bg")

        else:
            self.nextAz_e.setReadOnly(False)
            theme.paint(self.nextAz_e, bg="input_bg")
            self.nextAlt_e.setReadOnly(False)
            theme.paint(self.nextAlt_e, bg="input_bg")
            self.nextRa_e.setReadOnly(True)
            theme.paint(self.nextRa_e, bg="field_bg")
            self.nextDec_e.setReadOnly(True)
            theme.paint(self.nextDec_e, bg="field_bg")
        self.updateNextRaDec()

    def selectRaDec(self,event):
        self.setEq_r.setChecked(True)
        theme.paint(self.nextAz_e, bg="field_bg")
        theme.paint(self.nextAlt_e, bg="field_bg")
        theme.paint(self.nextRa_e, bg="input_bg")
        theme.paint(self.nextDec_e, bg="input_bg")
        self.updateNextRaDec()

    def selectAltAz(self,event):
        self.setAltAz_r.setChecked(True)
        theme.paint(self.nextAz_e, bg="input_bg")
        theme.paint(self.nextAlt_e, bg="input_bg")
        theme.paint(self.nextRa_e, bg="field_bg")
        theme.paint(self.nextDec_e, bg="field_bg")
        self.updateNextRaDec()

    def pulse(self):
        try:
            self.pulse_window.show()
            self.pulse_window.raise_()
        except AttributeError:
            self.pulse_window = PulseWindow(self.parent)

    # =================== OKNO GLOWNE ====================================
    def updateUI(self):

        self.setWindowTitle('')
        self.setStyleSheet("font-size: 11pt;")

        self.setWindowTitle(f"{self.parent.active_tel or 'Unknown'} Mount Manual Control")

        tmp=QWidget()
        try: tmp.setLayout(self.grid)
        except: pass
        self.grid = QGridLayout()

        ##################### MOUNT #############################

        self.mntConn1_l = QLabel("MOUNT")
        self.mntConn2_l = QLabel(" ")
        #self.mntConn2_l.setText("\U0001F534")
        theme.paint(self.mntConn1_l, fg="bad_fg")
        self.mntConn2_l.setMaximumWidth(25)                                        # UWAGA!!! To steruje szeroskoscia 1 kolumny!!!!!!!

        #self.mntStat_l = QLabel("MOUNT STATUS: ")
        self.mntStat_e = QLineEdit()
        self.mntStat_e.setReadOnly(True)
        theme.paint(self.mntStat_e, bg="field_bg", extra=self.STAT_STYLE)
        self.mntStat_e.setText("--")
        self.mntStat_e.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mntMotors_l = QLabel("MOTORS: ")
        self.mntMotors_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.mntMotors_c = QCheckBox()
        self.mntMotors_c.setChecked(False)
        self.mntMotors_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.mntMotors_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}")
        self.mntMotors_c.clicked.connect(self.parent.mount_motorsOnOff)



        w=0
        self.grid.addWidget(self.mntConn2_l, w, 0)
        self.grid.addWidget(self.mntConn1_l, w, 1)

        #self.grid.addWidget(self.mntStat_l, w, 4)
        self.grid.addWidget(self.mntStat_e, w, 2, 1, 2)
        # SAFETY CUTOFF tworzony nizej (sekcja przyciskow), stawiany tutaj
        self.safety_row = w

        self.grid.addWidget(self.mntMotors_l, w, 6)
        self.grid.addWidget(self.mntMotors_c, w, 7)

        ########################################

        self.mntEpoch_l = QLabel("EPOCH: ")
        self.mntEpoch_e = QLineEdit("2000")

        self.mntAirmass_l = QLabel("AIRMASS: ")
        self.mntAirmass_e = QLineEdit()
        self.mntAirmass_e.setReadOnly(True)
        theme.paint(self.mntAirmass_e, bg="field_bg")
        self.mntAirmass_e.setText(" -- ")

        self.nextAirmass_e = QLineEdit()
        self.nextAirmass_e.setReadOnly(True)
        theme.paint(self.nextAirmass_e, bg="field_bg")

        w=w+1
        self.grid.addWidget(self.mntEpoch_l, w, 0,1,2)
        self.grid.addWidget(self.mntEpoch_e, w, 3)

        self.grid.addWidget(self.mntAirmass_l, w, 4)
        self.grid.addWidget(self.mntAirmass_e, w, 5)
        self.grid.addWidget(self.nextAirmass_e, w, 6,1,2)


        ###################################################

        self.mntRa_l = QLabel("TELESCOPE RA [h]:")
        self.mntRa_e = QLineEdit()
        self.mntRa_e.setReadOnly(True)
        theme.paint(self.mntRa_e, bg="field_bg")

        self.mntDec_l = QLabel("TELESCOPE DEC [d]:")
        self.mntDec_e = QLineEdit()
        self.mntDec_e.setReadOnly(True)
        theme.paint(self.mntDec_e, bg="field_bg")


        self.nextRa_e = QLineEdit("")
        self.nextRa_e.mousePressEvent = self.selectRaDec

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
        theme.paint(self.mntAz_e, bg="field_bg")

        self.mntAlt_l = QLabel("TELESCOPE ALT [d]: ")
        self.mntAlt_e = QLineEdit()
        self.mntAlt_e.setReadOnly(True)
        theme.paint(self.mntAlt_e, bg="field_bg")


        self.nextAz_e = QLineEdit()
        theme.paint(self.nextAz_e, bg="field_bg")
        self.nextAz_e.mousePressEvent = self.selectAltAz

        self.nextAlt_e = QLineEdit()
        theme.paint(self.nextAlt_e, bg="field_bg")
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
        #theme.paint(self.target_e, bg="field_bg")

        self.tracking_l = QLabel("TRACKING: ")
        self.tracking_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.tracking_c = QCheckBox()
        self.tracking_c.setChecked(False)
        self.tracking_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.tracking_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}")
        self.tracking_c.clicked.connect(self.parent.mount_trackOnOff)

        self.guiding_c = QCheckBox("GUIDING: ")
        self.guiding_c.setChecked(False)
        self.guiding_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.guiding_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOnGrey.png)}::indicator:unchecked {image: url(ICONS/SwitchOffGrey.png)}")

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
        #self.domeConn2_l.setText("\U0001F534")
        theme.paint(self.domeConn1_l, fg="bad_fg")

        self.domeStat_e = QLineEdit()
        self.domeStat_e.setReadOnly(True)
        theme.paint(self.domeStat_e, bg="field_bg")

        self.domeTemp_l = QLabel("TEMPERATURE:")
        self.domeTemp_e = QLineEdit()
        self.domeTemp_e.setReadOnly(True)
        theme.paint(self.domeTemp_e, bg="field_bg")

        self.domeAuto_l  = QLabel("FOLLOW:")
        self.domeAuto_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.domeAuto_c = QCheckBox()
        self.domeAuto_c.setChecked(False)
        self.domeAuto_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.domeAuto_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}::indicator:disabled {image: url(ICONS/SwitchOffGrey.png)}")
        self.domeAuto_c.setEnabled(False)   # aktywny dopiero po odpowiedzi serwisu dome follower
        self.domeAuto_c.clicked.connect(self.parent.domeFollow)

        w = w + 1
        self.grid.addWidget(self.domeConn2_l,w, 0)
        self.grid.addWidget(self.domeConn1_l,w, 1)
        self.grid.addWidget(self.domeStat_e, w, 2, 1, 1)
        self.grid.addWidget(self.domeTemp_l, w, 4)
        self.grid.addWidget(self.domeTemp_e, w, 5)
        self.grid.addWidget(self.domeAuto_l, w, 6)
        self.grid.addWidget(self.domeAuto_c, w, 7)




        #############################

        self.ventilators_l = QLabel("VENTILATORS: ")

        self.ventilators_c = QCheckBox()
        self.ventilators_c.setChecked(False)
        self.ventilators_c.setLayoutDirection(Qt.LeftToRight)
        theme.paint(self.ventilators_c, extra="QCheckBox::indicator:checked {image: url(ICONS/ToggleOnOrange.png)}::indicator:unchecked {image: url(ICONS/ToggleOffGreen.png)}")
        self.ventilators_c.clicked.connect(self.parent.VentilatorsOnOff)

        self.ventilators_e = QLineEdit()
        self.ventilators_e.setReadOnly(True)
        theme.paint(self.ventilators_e, bg="field_bg")
        self.ventilators_e.setText("--")





        self.domeShutter_l = QLabel("SHUTTER: ")
        self.domeShutter_c = QCheckBox("")
        self.domeShutter_c.setChecked(False)
        self.domeShutter_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.domeShutter_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}")

        self.domeShutter_c.clicked.connect(self.parent.dome_openOrClose)

        self.domeShutter_e = QLineEdit()
        self.domeShutter_e.setText("--")
        self.domeShutter_e.setReadOnly(True)
        theme.paint(self.domeShutter_e, bg="field_bg")

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
        theme.paint(self.domeAz_e, bg="field_bg")

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
        theme.paint(self.domeLights_c, extra="QCheckBox::indicator:checked {image: url(ICONS/ToggleOnOrange.png)}::indicator:unchecked {image: url(ICONS/ToggleOffGreen.png)}")
        self.domeLights_c.clicked.connect(self.parent.domeLightOnOff)

        self.domeLights_e = QLineEdit()
        self.domeLights_e.setReadOnly(True)
        theme.paint(self.domeLights_e, bg="field_bg")
        self.domeLights_e.setText("--")

        self.flatLights_l = QLabel("FLAT LIGHTS: ")
        self.flatLights_c = QCheckBox("")
        self.flatLights_e = QLineEdit()
        self.flatLights_e.setReadOnly(True)
        theme.paint(self.flatLights_e, bg="field_bg")
        self.flatLights_e.setText("--")
        self.flatLights_c.setChecked(False)
        self.flatLights_c.setLayoutDirection(Qt.LeftToRight)
        theme.paint(self.flatLights_c, extra="QCheckBox::indicator:checked {image: url(ICONS/ToggleOnOrange.png)}::indicator:unchecked {image: url(ICONS/ToggleOffGreen.png)}")
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
        theme.paint(self.mirrorFans_e, bg="field_bg")
        self.mirrorFans_e.setText("--")
        self.mirrorFans_c.setChecked(False)
        theme.paint(self.mirrorFans_c, extra="QCheckBox::indicator:checked {image: url(ICONS/ToggleOnOrange.png)}::indicator:unchecked {image: url(ICONS/ToggleOffGreen.png)}")
        self.mirrorFans_c.clicked.connect(self.parent.mirrorFansOnOff)

        self.telCovers_l = QLabel("MIRROR COVERS: ")
        self.telCovers_e = QLineEdit()
        self.telCovers_e.setReadOnly(True)
        theme.paint(self.telCovers_e, bg="field_bg")
        self.telCovers_c = QCheckBox("")
        self.telCovers_c.setChecked(False)
        self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.telCovers_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}")
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

        self.focusConn_l = QLabel(" ")
        #self.focusConn_l.setText("\U0001F534")
        self.telFocus_l = QLabel("FOCUS: ")
        theme.paint(self.telFocus_l, fg="bad_fg")
        self.telFocus_e = QLineEdit()
        self.telFocus_e.setReadOnly(True)
        theme.paint(self.telFocus_e, bg="field_bg")
        self.setFocus_s = QSpinBox()
        # zakres pola SET fokusera; teleskop spoza listy dostaje szeroki zakres - domyslne 0-99 Qt obcinaloby
        # wartosc z modelu i SET przesunalby fokuser na 99
        tel = self.parent.active_tel
        self.setFocus_s.setRange(0, self.FOCUS_MAX.get(tel, self.FOCUS_MAX_DEFAULT))
        self.setFocus_s.setSingleStep(10)
        if tel is not None and tel not in self.FOCUS_MAX:
            logger.warning(f'TOI: no focuser range for {tel} in mnt_gui.FOCUS_MAX, using 0-{self.FOCUS_MAX_DEFAULT}')
        #self.setFocus_s.valueChanged.connect(self.parent.focusClicked)
        self.setFocus_p = QPushButton('SET')
        self.setFocus_p.clicked.connect(self.parent.set_focus)

        self.calcFocus_p = QPushButton('CALC MODEL')
        self.calcFocus_p.clicked.connect(self.parent.focus_set_update)

        self.telAutoFocus_l = QLabel("FOCUS ADJUST:")
        self.telAutoFocus_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.telAutoFocus_c = QCheckBox()
        self.telAutoFocus_c.setChecked(False)
        self.telAutoFocus_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.telAutoFocus_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}::indicator:unchecked {image: url(ICONS/SwitchOff.png)}")
        self.telAutoFocus_c.clicked.connect(self.parent.focus_auto_adjust_OnOff)

        w = w + 1
        self.grid.addWidget(self.focusConn_l, w, 0)
        self.grid.addWidget(self.telFocus_l, w, 1)
        self.grid.addWidget(self.telFocus_e, w, 2)
        self.grid.addWidget(self.setFocus_s, w, 3)
        self.grid.addWidget(self.setFocus_p, w, 4)
        self.grid.addWidget(self.calcFocus_p, w, 5)
        self.grid.addWidget(self.telAutoFocus_l, w,6,1,1)
        self.grid.addWidget(self.telAutoFocus_c, w,7)

        ##########################################################

        self.telM3_l = QLabel("M3: ")
        self.telM3_e = QLineEdit()
        self.telM3_e.setReadOnly(True)
        theme.paint(self.telM3_e, bg="field_bg")
        self.telM3_e.setText("")
        self.telM3_s = QComboBox()
        #self.telM3_s.setItems([])
        self.telM3_p = QPushButton('SET')
        #self.telM3_p.setStyleSheet(" color: gray;")                 # tertiary - comment
        self.telM3_p.clicked.connect(self.parent.set_m3)


        w=w+1
        self.grid.addWidget(self.telM3_l, w, 0,1,2)
        self.grid.addWidget(self.telM3_e, w, 2)
        self.grid.addWidget(self.telM3_s, w, 3)
        self.grid.addWidget(self.telM3_p, w, 4)

        ##########################################################
        # M3 przelacza instrument, a z nim ROTATOR i FILTER - sa pod linia

        self.lineM3_l = QFrame()
        self.lineM3_l.setFrameShape(QFrame.HLine)
        self.lineM3_l.setFrameShadow(QFrame.Raised)
        w = w + 1
        self.grid.addWidget(self.lineM3_l, w, 0, 1, 8)

        ##########################################################

        self.comRotator1_l = QLabel(" ")
        #self.comRotator1_l.setPixmap(QtGui.QPixmap('./Icons/red.png').scaled(20, 20))
        self.telRotator1_l = QLabel("ROTATOR: ")
        #self.comRotator1_l.setText("\U0001F534")
        theme.paint(self.telRotator1_l, fg="bad_fg")
        self.telRotator1_l.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        # ASA: MechanicalPosition - kat wzgledem tubusu (ja ustawia SET), Position - kat rownikowy na niebie (EQ);
        # rowne tylko w poludniku. Zakres mechaniczny: +-160 miekki limit, +-170 twardy ogranicznik
        self.telRotator1_e = QLineEdit()
        self.telRotator1_e.setReadOnly(True)
        theme.paint(self.telRotator1_e, bg="field_bg")
        self.telRotator1_e.setToolTip("Mechanical angle, relative to the telescope [deg], 0-360 (342 = -18).\n"
                                      "Limits ±160° (soft), ±170° (hard stop). Yellow: within 10° of the limit.")

        self.setRotator1_e = QLineEdit()
        self.setRotator1_e.setToolTip("Mechanical angle to move to [deg]: -160 to 160 or 0-360 (342 = -18).")
        self.setRotator1_p = QPushButton('SET')
        self.setRotator1_p.clicked.connect(self.parent.set_rotator)

        self.rotatorEq_l = QLabel("EQ:")
        self.rotatorEq_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.rotatorEq_e = QLineEdit()
        self.rotatorEq_e.setReadOnly(True)
        theme.paint(self.rotatorEq_e, bg="field_bg")
        tip = "Equatorial angle on the sky [deg]; equals the mechanical angle at the meridian."
        self.rotatorEq_l.setToolTip(tip)
        self.rotatorEq_e.setToolTip(tip)

        w=w+1
        self.grid.addWidget(self.comRotator1_l, w, 0)
        self.grid.addWidget(self.telRotator1_l, w, 1)
        self.grid.addWidget(self.telRotator1_e, w, 2)
        self.grid.addWidget(self.setRotator1_e, w, 3)
        self.grid.addWidget(self.setRotator1_p, w, 4)
        self.grid.addWidget(self.rotatorEq_l, w, 5)
        self.grid.addWidget(self.rotatorEq_e, w, 6, 1, 2)


        ##########################################################

        self.comFilter_l = QLabel(" ")
        self.telFilter_l = QLabel("FILTER: ")
        #self.comFilter_l.setText("\U0001F534")
        theme.paint(self.telFilter_l, fg="bad_fg")
        self.telFilter_e = QLineEdit()
        self.telFilter_e.setReadOnly(True)
        theme.paint(self.telFilter_e, bg="field_bg")
        self.telFilter_s = QComboBox()
        self.telFilter_p = QPushButton('SET')
        self.telFilter_p.clicked.connect(self.parent.set_filter)

        self.FilterAutoOffset_l = QLabel("AUTO OFFSET:")
        self.FilterAutoOffset_l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.FilterAutoOffset_c = QCheckBox()
        self.FilterAutoOffset_c.setChecked(True)
        self.FilterAutoOffset_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.FilterAutoOffset_c, extra="QCheckBox::indicator:checked {image: url(ICONS/SwitchOnGrey.png)}::indicator:unchecked {image: url(ICONS/SwitchOffGrey.png)}")


        w=w+1

        self.grid.addWidget(self.comFilter_l, w, 0)
        self.grid.addWidget(self.telFilter_l, w, 1)
        self.grid.addWidget(self.telFilter_e, w, 2)
        self.grid.addWidget(self.telFilter_s, w, 3)
        self.grid.addWidget(self.telFilter_p, w, 4)
        self.grid.addWidget(self.FilterAutoOffset_l, w,5,1,2)
        self.grid.addWidget(self.FilterAutoOffset_c, w,7)

        ##########################################################

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)

        w = w + 1
        self.shutdown_p = QPushButton('SHUTDOWN')
        self.weatherStop_p = QPushButton('WEATHER TOP')
        self.EmStop_p = QPushButton('EMERGENCY STOP')
        theme.paint(self.EmStop_p, fg="bad_fg")
        self.EmStop_p.setToolTip("TIC emergency stop of the telescope, then dome follower off. No confirmation.")
        self.shutdown_p.setToolTip("Dome follower off, then the TIC telescope shutdown (dome parked at azimuth 180).")

        self.SafetySwitch_l = QLabel("SAFETY CUTOFF OFF")
        self.SafetySwitch_l.setAlignment(Qt.AlignVCenter | Qt.AlignCenter)

        self.SafetySwitch_c = QCheckBox()
        self.SafetySwitch_c.setChecked(False)
        self.SafetySwitch_c.setLayoutDirection(Qt.RightToLeft)
        theme.paint(self.SafetySwitch_c, extra="QCheckBox::indicator:checked {image: url(ICONS/ToggleOnOrange.png)}::indicator:unchecked {image: url(ICONS/ToggleOffGreen.png)}")
        self.SafetySwitch_c.clicked.connect(self.parent.safety_switch_OnOff)

        self.shutdown_p.clicked.connect(self.parent.shutdown)
        self.weatherStop_p.clicked.connect(self.parent.weatherStop)
        self.EmStop_p.clicked.connect(self.parent.EmStop)

        self.grid.addWidget(self.shutdown_p, w, 5,1,2)

        # napis i przelacznik razem, dosuniete w prawo - przed MOTORS
        safety_box = QHBoxLayout()
        safety_box.addStretch(1)
        safety_box.addWidget(self.SafetySwitch_l)
        safety_box.addWidget(self.SafetySwitch_c)
        self.grid.addLayout(safety_box, self.safety_row, 4, 1, 2)

        #self.grid.addWidget(self.weatherStop_p, w, 3,1,2)
        self.grid.addWidget(self.EmStop_p, w, 0,1,3)

        ##########################################################

        self.setLayout(self.grid)

        self.setEq_r.toggled.connect(self.select)
        self.setAltAz_r.toggled.connect(self.select)

        self.nextRa_e.textChanged.connect(self.updateNextRaDec)
        self.nextDec_e.textChanged.connect(self.updateNextRaDec)
        self.nextAlt_e.textChanged.connect(self.updateNextRaDec)
        self.nextAz_e.textChanged.connect(self.updateNextRaDec)

        if self.parent.active_tel != None:
            ports = self.parent.nats_cfg[self.parent.active_tel]["tertiary_port_list"]
            if ports is not None:
                self.telM3_s.addItems(ports)
            else:       # teleskop bez M3 (brak komponentu tertiary w TIC) - wiersz wyszarzony
                self.telM3_e.setText("no M3")
                theme.paint(self.telM3_l, fg="muted_fg")
                theme.paint(self.telM3_e, fg="muted_fg", bg="field_bg")
                for widget in (self.telM3_s, self.telM3_p):
                    widget.setEnabled(False)
                for widget in (self.telM3_l, self.telM3_e, self.telM3_s, self.telM3_p):
                    widget.setToolTip(f"{self.parent.active_tel} has no M3 (no tertiary in the TIC configuration).")

        if self.parent.filter_list != None:
            self.telFilter_s.addItems(self.parent.filter_list)

        if self.parent.catalog_file:
            self.catalog = self.read_catalog(self.parent.catalog_file)
            completer = QCompleter(self.catalog)
            completer.setFilterMode(QtCore.Qt.MatchContains)
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.target_e.setCompleter(completer)


        del tmp
        self.parent.telescope_switch_status["mntGui"] = True





    _catalogs = {}      # plik -> (czas modyfikacji, lista); okno buduje sie od nowa przy kazdej zmianie teleskopu

    @classmethod
    def read_catalog(cls, path):
        try:
            mtime = os.path.getmtime(path)
        except OSError as e:
            logger.warning(f'TOI: object catalog {path}: {e}')
            return []
        cached = cls._catalogs.get(path)
        if cached is None or cached[0] != mtime:
            cls._catalogs[path] = cached = (mtime, readCatalog(path))
        return cached[1]

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)

class PulseWindow(BaseWindow):
    def __init__(self, parent):
        super(PulseWindow, self).__init__()
        self.parent = parent
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
            theme.paint(self.sumRa_e, bg="field_bg")
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
            theme.paint(self.sumDec_e, bg="field_bg")
            self.sumDec_e.setMaximumWidth(50)
            self.unitsDec_l = QLabel("[arc sec]")

            w = w + 1
            grid.addWidget(self.pulseDec_l, w, 0)
            grid.addWidget(self.pulseDec_e, w, 1)
            grid.addWidget(self.sumDec_l, w, 2)
            grid.addWidget(self.sumDec_e, w, 3)
            grid.addWidget(self.unitsDec_l, w, 4)

            self.line3_l = QFrame()
            self.line3_l.setFrameShape(QFrame.HLine)
            self.line3_l.setFrameShadow(QFrame.Raised)
            w = w + 1
            grid.addWidget(self.line3_l, w, 0, 1, 5)

            w = w + 1

            self.rot_l = QLabel("ROTATOR:")
            #self.rotpos_e = QLineEdit()
            self.rotminus_p = QPushButton('-')
            self.rotminus_p.clicked.connect(self.parent.rotator_minus)

            self.rotstep_e = QLineEdit()
            self.rotstep_e.setText("5")
            self.rotstep_e.setMaximumWidth(70)
            self.rotplus_p = QPushButton('+')
            self.rotplus_p.clicked.connect(self.parent.rotator_plus)


            grid.addWidget(self.rot_l, w, 0)
            #grid.addWidget(self.rotpos_e, w, 1)
            grid.addWidget(self.rotminus_p, w, 1)
            grid.addWidget(self.rotstep_e, w, 2)
            grid.addWidget(self.rotplus_p, w, 3)


            w = w + 1
            self.line4_l = QFrame()
            self.line4_l.setFrameShape(QFrame.HLine)
            self.line4_l.setFrameShadow(QFrame.Raised)
            grid.addWidget(self.line4_l, w, 0, 1, 5)

            w = w + 1
            self.close_p = QPushButton("Close")
            self.close_p.clicked.connect(lambda: self.close())
            grid.addWidget(self.close_p, w, 3,1,2)


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
