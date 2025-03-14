#!/usr/bin/env python3

import os.path
import qasync as qs
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QWidget, QLabel, QTextEdit, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, \
    QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QFrame
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pyaraucaria.coordinates import *
from qasync import QEventLoop

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from toi_lib import *


class ObsGui(QMainWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        super().__init__(loop=loop, client_api=client_api)
        self.parent = parent
        self.setWindowTitle('Telescope Operator Interface')
        self.main_form = MainForm(self.parent)
        self.setCentralWidget(self.main_form)
        self.move(self.parent.obs_window_geometry[0], self.parent.obs_window_geometry[1])
        self.resize(self.parent.obs_window_geometry[2], self.parent.obs_window_geometry[3])
        self.show()
        self.raise_()

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)


class MainForm(QWidget):
    def __init__(self, parent):
        super(MainForm, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")

        self.mkUI()
        # self.update_table()
        self.obs_t.itemSelectionChanged.connect(self.pocisniecie_tab)
        #self.exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())

    @qs.asyncSlot()
    async def pocisniecie_tab(self):
        i = self.obs_t.currentRow()
        self.parent.active_tel_i = i
        self.parent.active_tel = self.parent.obs_tel_tic_names[i]
        await self.parent.telescope_switched()

    def update_table(self):

        i = -1
        for t in self.parent.local_cfg["toi"]["telescopes"]:
            i = i + 1

            # TELESKOPY
            rgb = (0, 0, 0)
            status_ok = True
            try:
                for k in self.parent.nats_toi_op_status[t].keys():
                    if self.parent.nats_toi_op_status[t][k]["state"] == self.parent.nats_toi_op_status[t][k]["defoult"]:
                        pass
                    else:
                        status_ok = False
            except Exception as e:
                print(f"toi status warning {e}")

            if status_ok:
                txt = ""
            else:
                txt = "\u26A0 "
            txt = txt + f'{t}'

            acces = self.parent.tel_acces[t]
            if acces:
                #txt = txt +  "\U0001F513"
                #txt = txt + " \u2328" # klawiatura
                #txt = txt + " \u2301" #   blyskawica
                txt = txt + " \u2713" # check ok
                item = QTableWidgetItem(txt)
                rgb = (0, 150, 0)
            else:
                item = QTableWidgetItem(txt)

            if not status_ok:
                rgb = (255, 160, 0)

            item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setForeground(QtGui.QColor(*rgb))
            self.obs_t.setItem(i, 0, item)

            # DOME
            state, rgb = "--", (0, 0, 0)
            shutter = self.parent.oca_tel_state[t]["dome_shutterstatus"]["val"]
            moving = self.parent.oca_tel_state[t]["dome_slewing"]["val"]

            if shutter != None or moving != None:
                if shutter == None and moving == None : state,rgb = "SHUTTER and STATUS ERROR",(150, 0, 0)
                elif shutter == None: state,rgb = "SHUTTER ERROR",(150, 0, 0)
                elif moving == None : state,rgb = "DOME STATUS ERROR",(150, 0, 0)
                else:
                    if moving: state,rgb = "MOVING",(255, 160, 0)
                    elif shutter==0: state,rgb = "OPEN",(0, 150, 0)
                    elif shutter==1: state,rgb = "CLOSED",(0, 0, 0)
                    elif shutter==2: state,rgb = "OPENING",(255, 160, 0)
                    elif shutter==3: state,rgb = "CLOSING",(255, 160, 0)
                    else: state,rgb = "SHUTTER ERROR",(150, 0, 0)

            item = QTableWidgetItem(state)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*rgb)))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, 1, item)


            # MIRROR
            state, rgb = "--", (0, 0, 0)
            status = self.parent.oca_tel_state[t]["mirror_status"]["val"]
            if status == None:
                state, rgb = "NO IDEA", (0, 0, 0)
            else:
                if status == 3: state, rgb = "OPEN", (0, 150, 0)
                elif status == 1: state, rgb = "CLOSED", (0, 0, 0)
                elif status == 2:
                    state, rgb = "MOVING", (255, 160, 0)
                else:
                    state, rgb = "ERROR", (150, 0, 0)

            item = QTableWidgetItem(state)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*rgb)))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, 2, item)

            # MOUNT
            state, rgb = "--", (0, 0, 0)
            slewing = self.parent.oca_tel_state[t]["mount_slewing"]["val"]
            tracking = self.parent.oca_tel_state[t]["mount_tracking"]["val"]
            motors = self.parent.oca_tel_state[t]["mount_motor"]["val"]

            if slewing != None or tracking != None:
                if motors == "false": state,rgb = "MOTORS OFF", (0, 0, 0)
                elif slewing: state,rgb = "SLEWING", (255, 160, 0)
                elif tracking: state,rgb = "TRACKING",(0, 150, 0)
                else: state,rgb = "IDLE",(0, 0, 0)

            item = QTableWidgetItem(state)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*rgb)))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, 3, item)

            # CCD
            state, rgb = "--", (0, 0, 0)
            filtr = "--"
            pos = self.parent.oca_tel_state[t]["fw_position"]["val"]
            ccd =  self.parent.oca_tel_state[t]["ccd_state"]["val"]

            if pos != None:
                filtr = self.parent.nats_cfg[t]["filter_list_names"][pos]

            if ccd != None :
                if ccd == 2:
                    state,rgb = f"EXP [{filtr}]", (0, 150, 0)
                elif ccd == 0:
                    state,rgb = f"IDLE [{filtr}]", (0, 0, 0)
                else:
                    state, rgb = f"NO IDEA [{filtr}]", (0, 0, 0)

            item = QTableWidgetItem(state)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*rgb)))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, 4, item)

            # PROGRAM
            state, rgb = "--", (0, 0, 0)
            #print(t,self.parent.ob_progress[t])
            #templeate = {"ob_started": False, "ob_done": False, "ob_expected_time": 0.01, "ob_start_time": 0,"ob_program": None}
            started = self.parent.ob_progress[t]["ob_started"]
            done = self.parent.ob_progress[t]["ob_done"]
            program = self.parent.ob_progress[t]["ob_program"]
            if started and not done:
                if "OBJECT" in program:
                    state,rgb = f"{program.split()[1]}", (0, 150, 0)
                else:
                    if len(program.split())>1:
                        state, rgb = f"{program.split()[0]} {program.split()[1]}", (0, 150, 0)
                    else:
                        state, rgb = f"{program.split()[0]}", (0, 0, 0)
            if "error" in self.parent.ob_progress[t]:
               if  self.parent.ob_progress[t]["error"]:
                   state, rgb = f"ERROR {state}", (150, 0, 0)

            item = QTableWidgetItem(state)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*rgb)))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, 5, item)

            self.obs_t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)


    def msg(self, txt, color):
        c = QtCore.Qt.black
        if "yellow" in color: c = QtCore.Qt.darkYellow
        if "green" in color: c = QtCore.Qt.darkGreen
        if "red" in color: c = QtCore.Qt.darkRed
        self.msg_e.setTextColor(c)
        ut = str(self.parent.ut).split()[1].split(":")[0] + ":" + str(self.parent.ut).split()[1].split(":")[1]
        txt = ut + " " + txt
        if txt.split()[1] != "TELEMETRY:":
            self.msg_e.append(txt)

        # LOG dzialan
        if os.path.exists(self.parent.msg_log_file):
            pass
        else:
            with open(self.parent.msg_log_file, "w") as log_file:
                log_file.write("")
        with open(self.parent.msg_log_file, "r") as log_file:
            tmp = log_file.read().splitlines()
            log = "\n".join(tmp[-1 * int(self.parent.msg_log_lines):])

        with open(self.parent.msg_log_file, "w") as log_file:
            log = log + "\n" + txt + "\n"
            log_file.write(log)

    def open_conditions(self):
        self.parent.conditionsGui.update()
        self.parent.conditionsGui.show()

    def report(self):
        self.report_window = ReportWindow(self.parent)
        self.report_window.show()

    # =================== OKNO GLOWNE ====================================
    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.ticStatus2_l = QLabel("\u262F  TIC")
        grid.addWidget(self.ticStatus2_l, w, 0,1,2)

        w = w + 1
        self.date_l = QLabel("Date:")
        self.date_l.setAlignment(Qt.AlignCenter)
        self.date_e = QLineEdit("--/--/--")
        self.date_e.setAlignment(Qt.AlignCenter)
        self.date_e.setReadOnly(True)
        self.date_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.ut_l = QLabel("UT:")
        self.ut_l.setAlignment(Qt.AlignCenter)
        self.ut_e = QLineEdit("--:--:--")
        self.ut_e.setReadOnly(True)
        self.ut_e.setAlignment(Qt.AlignCenter)
        self.ut_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.wind_l = QLabel("Wind:")
        self.wind_l.setAlignment(Qt.AlignCenter)
        self.wind_e = QLineEdit()
        self.wind_e.setAlignment(Qt.AlignCenter)
        self.wind_e.setReadOnly(True)
        self.wind_e.setStyleSheet("background-color: rgb(235,235,235);")

        self.windDir_l = QLabel("Direction:")
        self.windDir_l.setAlignment(Qt.AlignCenter)
        self.windDir_e = QLineEdit()
        self.windDir_e.setAlignment(Qt.AlignCenter)
        self.windDir_e.setReadOnly(True)
        self.windDir_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.date_l, w, 0)
        grid.addWidget(self.date_e, w, 1)

        grid.addWidget(self.ut_l, w, 2)
        grid.addWidget(self.ut_e, w, 3)

        grid.addWidget(self.wind_l, w, 4)
        grid.addWidget(self.wind_e, w, 5)

        grid.addWidget(self.windDir_l, w, 6)
        grid.addWidget(self.windDir_e, w, 7)

        w = w + 1

        self.ojd_l = QLabel("JD:")
        self.ojd_l.setAlignment(Qt.AlignCenter)
        self.ojd_e = QLineEdit("--")
        self.ojd_e.setAlignment(Qt.AlignCenter)
        self.ojd_e.setReadOnly(True)
        self.ojd_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.sid_l = QLabel("SID:")
        self.sid_l.setAlignment(Qt.AlignCenter)
        self.sid_e = QLineEdit("--:--:--")
        self.sid_e.setAlignment(Qt.AlignCenter)
        self.sid_e.setReadOnly(True)
        self.sid_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        self.temp_l = QLabel("Temp:")
        self.temp_l.setAlignment(Qt.AlignCenter)
        self.temp_e = QLineEdit()
        self.temp_e.setAlignment(Qt.AlignCenter)
        self.temp_e.setReadOnly(True)
        self.temp_e.setStyleSheet("background-color: rgb(235,235,235);")

        self.hummidity_l = QLabel("Humidity:")
        self.hummidity_l.setAlignment(Qt.AlignCenter)
        self.hummidity_e = QLineEdit()
        self.hummidity_e.setAlignment(Qt.AlignCenter)
        self.hummidity_e.setReadOnly(True)
        self.hummidity_e.setStyleSheet("background-color: rgb(235,235,235);")

        grid.addWidget(self.ojd_l, w, 0)
        grid.addWidget(self.ojd_e, w, 1)

        grid.addWidget(self.sid_l, w, 2)
        grid.addWidget(self.sid_e, w, 3)

        grid.addWidget(self.temp_l, w, 4)
        grid.addWidget(self.temp_e, w, 5)

        grid.addWidget(self.hummidity_l, w, 6)
        grid.addWidget(self.hummidity_e, w, 7)

        # w = w + 1
        # self.pressure_l = QLabel("Pressure:")
        # self.pressure_e = QLineEdit()
        # self.pressure_e.setReadOnly(True)
        # self.pressure_e.setStyleSheet("background-color: rgb(235,235,235);")

        # grid.addWidget(self.pressure_l, w, 6)
        # grid.addWidget(self.pressure_e, w, 7)

        w = w + 1
        self.obs_t = QTableWidget(3, 6)
        self.obs_t.setHorizontalHeaderLabels(["Telescope", "Dome", "Mirror", "Mount", "Instrument", "Program"])
        self.obs_t.setSelectionBehavior(QTableWidget.SelectRows)
        self.obs_t.setSelectionMode(QTableWidget.SingleSelection)
        self.obs_t.verticalHeader().hide()
        self.obs_t.setShowGrid(False)
        self.obs_t.setEditTriggers(QTableWidget.NoEditTriggers)
        #self.obs_t.setFixedWidth(550)  # Size
        self.obs_t.setStyleSheet("font-size: 9pt; selection-background-color: rgb(138,176,219);")
        grid.addWidget(self.obs_t, w, 0, 1, 8)


        self.SpecialPocisk_p = QPushButton('NO')
        #self.testowyPocisk_p.clicked.connect(self.parent.force_update)



        self.report_p = QPushButton('REPORT')
        self.report_p.clicked.connect(self.report)
        self.ping_p = QPushButton('PING')
        self.ping_p.clicked.connect(self.parent.ping)
        self.log_p = QPushButton('PLANRUNNER')
        self.log_p.clicked.connect(lambda: self.parent.planrunnerGui.show())
        self.flats_p = QPushButton('FLATS')
        self.flats_p.clicked.connect(lambda: self.parent.flatGui.updateUI())
        self.guider_p = QPushButton('GUIDER')
        self.guider_p.clicked.connect(lambda: self.parent.guiderGui.show())
        self.focus_p = QPushButton('AUTO FOCUS')
        self.focus_p.clicked.connect(lambda: self.parent.focusGui.raise_())
        self.fits_p = QPushButton('FITS')
        self.fits_p.clicked.connect(lambda: self.parent.fitsGui.raise_())
        self.conditions_p = QPushButton('CONDITIONS')
        self.conditions_p.clicked.connect(self.open_conditions)


        w = 7

        self.msg_e = QTextEdit()
        self.msg_e.setReadOnly(True)
        self.msg_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.msg_e, w, 0, 3, 5)

        w = 7

        grid.addWidget(self.focus_p, w, 5)
        grid.addWidget(self.guider_p, w, 7)

        w = w + 1
        #grid.addWidget(self.SpecialPocisk_p, w, 0, 1, 2)
        grid.addWidget(self.log_p, w, 5)
        grid.addWidget(self.fits_p, w, 7)

        w = w + 1

        grid.addWidget(self.conditions_p, w, 5)
        grid.addWidget(self.flats_p, w, 7)

        w = w + 1

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 0, 1, 8)

        w = w + 1

        self.config_p = QPushButton("\u2699")
        self.config_p.setStyleSheet(" color: gray;")


        grid.addWidget(self.report_p, w, 0)
        grid.addWidget(self.ping_p, w, 1)
        grid.addWidget(self.config_p, w, 7)


        grid.setSpacing(5)

        self.setLayout(grid)

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)

# ############### FOCUS ##########################

class ReportWindow(QWidget):
    def __init__(self, parent):
        super(ReportWindow, self).__init__()
        self.parent = parent
        self.setGeometry(self.parent.obs_window_geometry[0] + 200, self.parent.obs_window_geometry[1]+100, 500, 500)
        self.mkUI()
        self.setWindowTitle('Report')


    def report(self):
        self.rep_name = self.parent.ut.replace("/","_").replace(" ","_").replace(":","_")
        if self.parent.active_tel:
            self.rep_name = self.rep_name + "_" + self.parent.active_tel
        self.dir_name = "./Reports/"+self.rep_name
        if not os.path.exists(self.dir_name):
            os.makedirs(self.dir_name)

        with open(self.dir_name+"/report.txt","w") as file1:
            txt = str(self.report_e.toPlainText())+"\n"
            file1.write(txt)

        if self.parent.active_tel:
            with open(self.dir_name+"/log.txt","w") as file2:
                txt = self.parent.log_record[self.parent.active_tel]
                file2.write(txt)

        zmienne = ["active_tel",
                   "active_tel_i",
                   "acces",
                   "tel_acces",
                   "ob",
                   "ob_progress",
                   "nats_ob_progress",
                   "planrunners",
                   "telescope_switch_status",
                   "tel_alpaca_con",
                   "flat_record",
                   "cwd",
                   "comProblem",
                   "script_location",
                   "msg_log_file",
                   "msg_log_lines",
                   "tic_con",
                   "fw_con",
                   "mount_con",
                   "dome_con",
                   "rotator_con",
                   "inst_con",
                   "focus_con",
                   "covercalibrator_con",
                   "nextOB_ok",
                   "flag_newimage",
                   "observer",
                   "telemetry_temp",
                   "telemetry_wind",
                   "telemetry_wind_direction",
                   "telemetry_humidity",
                   "telemetry_pressure",
                   "autofocus_started",
                   "last_focus_position",
                   "ut",
                   "ephem_utc",
                   "ephem_prev_utc",
                   # ccd
                   "binxy_changed",
                   "ccd_binx",
                   "ccd_biny",
                   "cfg_inst_temp",
                   "cfg_inst_gain",
                   "cfg_inst_rm",
                   "ccd_temp_set",
                   "ccd_temp",
                   # filter wheel
                   "filter",
                   "filter_list",
                   # guider
                   "prev_guider_coo",
                   "prev_guider_adu",
                   "guider_failed",
                   # dome
                   "dome_shutterstatus",
                   "dome_az",
                   "dome_status",
                   # mount
                   "mount_motortatus",
                   "mount_ra",
                   "mount_dec",
                   "mount_alt",
                   "mount_az",
                   "mount_parked",
                   "mount_slewing",
                   "mount_tracking",
                   "pulseRa",
                   "pulseDec",
                   "cover_status",
                   # focus
                   "focus_editing",
                   "focus_value",
                   # rotator
                   "rotator_pos",
                   # program
                   "req_ra",
                   "req_dec",
                   "req_epoch",
                   "program_id",
                   "oca_tel_state",
                   # plan
                   "next_i",
                   "current_i",
                   "plan",
                   "done_uobi",
                   "nats_plan_status",
                   # rozne
                   "ob_log",
                   "nats_cfg"]

        txt = ""
        for x in zmienne:
            try:
                val = eval("self.parent."+x)
                txt = txt + f'*** {x}: {val}' + "\n"
            except:
                pass
        with open(self.dir_name + "/telemetry.txt", "w") as file3:
            file3.write(txt)

        txt=f"Report created. Please send email to mgorski and mkicia with files located in {self.dir_name}"
        self.parent.WarningWindow(txt)
        self.close()

    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.report_l = QLabel("Please provide short description what happened: ")
        w = w + 1
        grid.addWidget(self.report_l, w, 0, 1, 2)
        w = w + 1
        self.report_e = QTextEdit("")
        grid.addWidget(self.report_e, w, 0, 1, 2)
        w = w + 1
        self.close_p = QPushButton('Cancel')
        self.close_p.clicked.connect(lambda: self.close())
        self.report_p = QPushButton('Create Report')
        self.report_p.clicked.connect(self.report)

        grid.addWidget(self.close_p, w, 0)
        grid.addWidget(self.report_p, w, 1)


        self.setLayout(grid)

