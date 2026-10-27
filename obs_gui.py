#!/usr/bin/env python3

import logging
import os.path
import qasync as qs
from PyQtX import QtCore, QtGui
from PyQtX.QtCore import Qt, QSettings, QTimer
from PyQtX.QtWidgets import QMainWindow, QWidget, QLabel, QTextEdit, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, \
    QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox, QMenu, QDockWidget, QApplication, QScrollArea
from pyaraucaria.coordinates import *
from qasync import QEventLoop

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from base_window import BaseWindow
from claude_report import write_claude_report
from toi_lib import *

logger = logging.getLogger(__name__)


class ObsGui(QMainWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        QMainWindow.__init__(self)
        BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)
        self.parent = parent
        self._geometry = None
        self.setWindowTitle('Telescope Operator Interface')
        self.main_form = MainForm(self.parent)
        self.setCentralWidget(self.main_form)
        self.set_initial_geometry(
            self.parent.obs_window_geometry[0],
            self.parent.obs_window_geometry[1],
            self.parent.obs_window_geometry[2],
            self.parent.obs_window_geometry[3]
        )
        self._quitting = False
        self.mk_windows_menu()
        self.show()
        self.raise_()

    # okna TOI zamkniete krzyzykiem tylko sie chowaja - z menu pod przyciskiem ⚙ wracaja albo wychodza na wierzch
    WINDOWS = [("Observation", "obsGui"), ("Mount", "mntGui"), ("Instrument", "instGui"), ("Plan", "planGui"),
               ("Sky", "skyGui"), ("FITS", "fitsGui"), ("Aux", "auxGui")]

    def mk_windows_menu(self):
        menu = QMenu(self.main_form.config_p)
        self.main_form.config_p.setMenu(menu)
        self.main_form.config_p.setToolTip("Show a TOI window or bring it to the front.")
        for title, attr in self.WINDOWS:
            # _ - triggered(checked) podaje bool, nie moze trafic do attr
            menu.addAction(title, lambda _=False, attr=attr: self.bring_up(getattr(self.parent, attr)))
        aux_tabs = menu.addMenu("Aux tabs")
        aux_tabs.aboutToShow.connect(lambda: self.fill_aux_menu(aux_tabs))
        menu.addSeparator()
        menu.addAction("Reset layout", lambda _=False: self.reset_layout())

    def fill_aux_menu(self, menu):
        menu.clear()
        tabs = self.parent.auxGui.tabs
        for i in range(tabs.count()):
            if tabs.isTabVisible(i):
                page = tabs.widget(i)
                menu.addAction(tabs.tabText(i), lambda _=False, page=page: self.show_aux_tab(page))

    def show_aux_tab(self, page):
        self.bring_up(self.parent.auxGui)
        self.parent.auxGui.tabs.setCurrentWidget(page)

    def bring_up(self, window):
        # zadokowane okno: podnosimy jego panel (takze zakladke, gdy panele leza na sobie);
        # miedzy oknem a panelem jest obszar przewijania, wiec szukamy panelu wsrod przodkow
        dock = window.parentWidget()
        while dock is not None and not isinstance(dock, QDockWidget):
            dock = dock.parentWidget()
        if dock is not None:
            dock.show()
            dock.raise_()
            if not dock.isFloating():
                window = self
            else:
                dock.activateWindow()
                return
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()

    # ---- panele: okna TOI zadokowane w oknie obserwacji (QDockWidget). Mozna je przestawiac, ukladac jako
    # zakladki i wypinac na drugi monitor; uklad pamietany per maszyna i ustawienie ekranow (QSettings),
    # zapisywany przy zamknieciu TOI, "Reset layout" w menu ⚙ wraca do domyslnego
    PANELS = [("mntGui", "Mount"), ("instGui", "Instrument"), ("skyGui", "Sky"),
              ("planGui", "Plan"), ("fitsGui", "FITS"), ("auxGui", "Aux")]

    # panele wyraznie rozdzielone: pasek tytulu z tlem (kolor aktywnego teleskopu) i grubsze linie podzialu
    PANEL_STYLE = """
        QMainWindow::separator { background: rgb(150, 150, 150); width: 5px; height: 5px; }
        QMainWindow::separator:hover { background: rgb(100, 100, 100); }
        QDockWidget::title { background: TITLE_BG; color: black; padding: 3px 6px; }
    """

    def set_panel_telescope(self, tel):
        # paski tytulowe paneli w kolorze aktywnego teleskopu (z configu TIC) i z jego nazwa
        # pol na pol z biela: ciemne kolory (zb08 #0082E8) nie zaglusza czarnego tekstu, odcien zostaje
        color = QtGui.QColor(self.parent.nats_cfg.get(tel, {}).get("color") or "#cdd2dc")
        tint = QtGui.QColor((color.red() + 255) // 2, (color.green() + 255) // 2, (color.blue() + 255) // 2)
        self.setStyleSheet(self.PANEL_STYLE.replace("TITLE_BG", tint.name()))
        for attr, title in self.PANELS:
            self.docks[attr].setWindowTitle(f"{title} \u00b7 {tel}")
        self.setWindowTitle(f"Telescope Operator Interface \u00b7 {tel}")

    def dock_panels(self):
        self._geometry = None       # rozmiar okna glownego ustawia uklad, nie obs_window_geometry
        self.setStyleSheet(self.PANEL_STYLE.replace("TITLE_BG", "rgb(205, 210, 220)"))
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks
                            | QMainWindow.DockOption.AllowNestedDocks)
        # prawa kolumna na cala wysokosc, Mount tylko pod oknem obserwacji
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        # formularz obserwacji tez w obszarze przewijania - na malym ekranie oddaje szerokosc panelom
        central = QScrollArea()
        central.setWidgetResizable(True)
        central.setFrameShape(QFrame.Shape.NoFrame)
        central.setWidget(self.takeCentralWidget())
        self.setCentralWidget(central)
        self.docks = {}
        for attr, title in self.PANELS:
            widget = getattr(self.parent, attr)
            widget._geometry = None     # BaseWindow nie ustawia juz pozycji
            dock = QDockWidget(title, self)
            dock.setObjectName(f"dock_{attr}")      # po tej nazwie saveState rozpoznaje panel
            # przewijanie zamiast wypychania okna poza ekran, gdy panel dostanie mniej niz minimum zawartosci
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(widget)
            dock.setWidget(area)
            self.docks[attr] = dock
        self.default_layout()
        self.restore_layout()

    # dawny uklad okien (x, y, szer., wys.) wzgledem lewego gornego rogu ekranu: domyslny uklad paneli go odtwarza
    ORIGINAL = {"obs": (0, 0, 850, 400), "mntGui": (0, 510, 850, 450), "skyGui": (910, 0, 500, 500),
                "instGui": (910, 610, 500, 500), "planGui": (1415, 0, 490, 1100),
                "fitsGui": (1910, 0, 1000, 700), "auxGui": (1910, 810, 1000, 500)}

    def default_layout(self):
        d = self.docks
        o = self.ORIGINAL
        avail = QApplication.primaryScreen().availableGeometry()
        logger.info(f'TOI layout: screens {[(sc.name(), sc.geometry().getRect()) for sc in QApplication.screens()]}, '
                    f'available {avail.getRect()}')
        # okno glowne jak dawniej siegaly Plan i dolne okna - nie caly ekran
        width = min(o["planGui"][0] + o["planGui"][2], avail.width())
        height = min(max(o["planGui"][3], o["instGui"][1] + o["instGui"][3]), avail.height())
        self.setGeometry(avail.left(), avail.top(), width, height)
        for dock in d.values():
            self.removeDockWidget(dock)
            dock.setFloating(False)
        right = Qt.DockWidgetArea.RightDockWidgetArea
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d["mntGui"])
        self.addDockWidget(right, d["skyGui"])
        self.splitDockWidget(d["skyGui"], d["planGui"], Qt.Orientation.Horizontal)
        self.splitDockWidget(d["skyGui"], d["instGui"], Qt.Orientation.Vertical)
        # FITS i Aux obok okna glownego, jesli sie mieszcza (szeroki monitor albo drugi ekran); inaczej zakladki przy Sky
        room = QApplication.primaryScreen().virtualGeometry().right() - (avail.left() + o["fitsGui"][0])
        floating = room >= o["fitsGui"][2] // 2
        if not floating:
            self.tabifyDockWidget(d["skyGui"], d["fitsGui"])
            self.tabifyDockWidget(d["skyGui"], d["auxGui"])
        self._compact_for_screen(avail)
        for dock in d.values():
            dock.show()
        d["skyGui"].raise_()
        # rozmiary dopiero po rozlozeniu okna (resizeDocks wczesniej nie dziala)
        QTimer.singleShot(0, lambda: self._size_default_layout(avail, height, floating))

    def _compact_for_screen(self, avail):
        # maly ekran (laptop): kolejne panele ida jako zakladki do grupy Sky, az minimalne rozmiary sie zmieszcza
        d = self.docks
        need = lambda attr: getattr(self.parent, attr).minimumSizeHint()
        form = self.main_form.minimumSizeHint()
        right = ["skyGui", "instGui"]               # kolumna Sky/Instrument
        columns = {"plan": True}                    # osobna kolumna Plan
        mount_below = True

        def width():
            left = max(form.width(), need("mntGui").width() if mount_below else 0)
            col = max(need(a).width() for a in right)
            return left + col + (need("planGui").width() if columns["plan"] else 0) + 30

        def height():
            left = form.height() + (need("mntGui").height() if mount_below else 0)
            col = sum(need(a).height() for a in right if a != "skyGui") + need("skyGui").height()
            return max(left, col, need("planGui").height()) + 60

        self._compacted = steps = []
        if width() > avail.width():
            self.tabifyDockWidget(d["skyGui"], d["planGui"])
            columns["plan"] = False
            steps.append("Plan")
        if width() > avail.width() or height() > avail.height():
            self.tabifyDockWidget(d["skyGui"], d["instGui"])
            right.remove("instGui")
            steps.append("Instrument")
        if height() > avail.height():
            self.removeDockWidget(d["mntGui"])
            self.tabifyDockWidget(d["skyGui"], d["mntGui"])
            mount_below = False
            steps.append("Mount")
        if steps:
            logger.info(f'TOI layout: small screen {avail.width()}x{avail.height()}, tabbed with Sky: {steps}; '
                        f'minimum widths: form {form.width()}, ' +
                        ", ".join(f'{a} {need(a).width()}' for a, _ in self.PANELS))

    def _size_default_layout(self, avail, height, floating):
        d = self.docks
        o = self.ORIGINAL
        if self._compacted:
            # maly ekran: grupa zakladek tak szeroka jak jej najszerszy panel, formularz obserwacji dostaje reszte
            group = [a for a, _ in self.PANELS if a == "skyGui" or d[a] in self.tabifiedDockWidgets(d["skyGui"])]
            want = max(getattr(self.parent, a).minimumSizeHint().width() for a in group) + 20
            self.resizeDocks([d["skyGui"]], [min(want, avail.width() - 350)], Qt.Orientation.Horizontal)
            self._log_layout()
            return
        self.resizeDocks([d["skyGui"], d["planGui"]], [o["skyGui"][2], o["planGui"][2]], Qt.Orientation.Horizontal)
        # wysokosci w dawnych proporcjach: obs : Mount = 400 : 450, Sky : Instrument = 500 : 500
        self.resizeDocks([d["mntGui"]], [height * o["mntGui"][3] // (o["obs"][3] + o["mntGui"][3])],
                         Qt.Orientation.Vertical)
        self.resizeDocks([d["skyGui"], d["instGui"]], [height // 2, height // 2], Qt.Orientation.Vertical)
        if floating:
            x, y, w, h = o["fitsGui"]
            d["fitsGui"].setFloating(True)
            d["fitsGui"].setGeometry(avail.left() + x, avail.top() + y, w, h)
            d["fitsGui"].show()
            d["auxGui"].setFloating(True)
            d["auxGui"].show()
            # Aux tuz pod ramka FITS (ramke znamy dopiero po pokazaniu okna) i do dolu okna glownego
            QTimer.singleShot(100, self._place_aux)
        else:
            self._log_layout()

    def _place_aux(self):
        fits, aux = self.docks["fitsGui"], self.docks["auxGui"]
        title = aux.frameGeometry().height() - aux.geometry().height()     # pasek tytulu okna
        top = fits.frameGeometry().bottom() + 1 + title
        bottom = self.frameGeometry().bottom() - (self.frameGeometry().bottom() - self.geometry().bottom())
        aux.setGeometry(fits.geometry().left(), top, fits.geometry().width(), max(bottom - top, 300))
        self._log_layout()

    def _log_layout(self):
        logger.info('TOI layout: ' + ", ".join(
            f'{k} {"floating" if v.isFloating() else self.dockWidgetArea(v).name} {v.geometry().getRect()}'
            for k, v in self.docks.items()))

    def layout_key(self):
        # osobny uklad dla kazdego ustawienia ekranow (laptop sam / z monitorem / stanowisko)
        # "layout2": uklady zapisane przed poprawka rozmiarow (2026-10-27) sa pomijane
        return "layout2/" + "+".join(f"{sc.size().width()}x{sc.size().height()}" for sc in QApplication.screens())

    def save_layout(self):
        settings = QSettings("OCA", "TOI")
        settings.setValue(self.layout_key() + "/geometry", self.saveGeometry())
        settings.setValue(self.layout_key() + "/state", self.saveState())

    def restore_layout(self):
        settings = QSettings("OCA", "TOI")
        geometry = settings.value(self.layout_key() + "/geometry")
        state = settings.value(self.layout_key() + "/state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def reset_layout(self):
        self.default_layout()
        self.save_layout()

    def set_initial_geometry(self, x, y, width, height):
        self._geometry = (x, y, width, height)

    def showEvent(self, event):
        super().showEvent(event)
        if self._geometry:
            self.setGeometry(*self._geometry)
            self._geometry = None

    async def on_start_app(self):
        await self.run_background_tasks()

    def closeEvent(self, event):
        # to okno ma menu okien (⚙), wiec zamkniete krzyzykiem pyta, czy zamknac caly TOI
        # (bez exec - modalne okno w petli qasync blokuje inne zadania, stad open() i sygnal)
        if self._quitting:
            super().closeEvent(event)
            return
        event.ignore()
        self._close_box = QMessageBox(QMessageBox.Icon.Question, "TOI", "Close TOI (all windows)?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        self._close_box.buttonClicked.connect(self._close_answer)
        self._close_box.open()

    def _close_answer(self, button):
        if self._close_box.standardButton(button) == QMessageBox.StandardButton.Yes:
            self.quit_toi()

    def quit_toi(self):
        self._quitting = True
        self.save_layout()
        self.parent.app.closeAllWindows()


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


            icons = QWidget()
            lay = QHBoxLayout(icons)
            lay.setContentsMargins(1,0,1,0)
            lay.setSpacing(3)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            acces = self.parent.tel_acces[t]
            if acces:
                icon_label1 = QLabel()
                icon_label1.setPixmap(ToiIcon("icon_joystick", "darkGreen", size=14).pixmap(14, 14))
                lay.addWidget(icon_label1)

            lay.addWidget(QLabel(f'{t}'))

            if self.parent.safety_cutoff.get(t):
                icon_hat = QLabel()
                icon_hat.setPixmap(ToiIcon("icon_hat", "red", size=14).pixmap(14, 14))
                icon_hat.setToolTip("safety cutoff ON")
                lay.addWidget(icon_hat)


            if self.parent.nats_toi_op_status[t]:

                k = "program_error"
                if "error" in self.parent.ob_progress[t]:
                    if self.parent.ob_progress[t]["error"]:
                        icon_label2 = QLabel()
                        icon_label2.setPixmap(ToiIcon("icon_bug", "red", size=14).pixmap(14, 14))
                        lay.addWidget(icon_label2)

                vent = False
                k = "dome_ventilators"
                if self.parent.nats_toi_op_status[t].get(k).get("state") != self.parent.nats_toi_op_status[t].get(k).get("defoult"):
                    vent = True
                k = "mirror_fans"
                if self.parent.nats_toi_op_status[t].get(k).get("state") != self.parent.nats_toi_op_status[t].get(k).get("defoult"):
                    vent = True

                if vent:
                    icon_label3 = QLabel()
                    icon_label3.setPixmap(ToiIcon("icon_fan", "darkOrange", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label3)

                light = False
                k = "flat_lamps"
                if self.parent.nats_toi_op_status[t].get(k).get("state") != self.parent.nats_toi_op_status[t].get(k).get("defoult"):
                    light = True
                k = "dome_lights"
                if self.parent.nats_toi_op_status[t].get(k).get("state") != self.parent.nats_toi_op_status[t].get(k).get("defoult"):
                    light = True

                if light:
                    icon_label4 = QLabel()
                    icon_label4.setPixmap(ToiIcon("icon_bulb", "darkOrange", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label4)

                def _f(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
                wind = _f(self.parent.telemetry_wind)
                humidity = _f(self.parent.telemetry_humidity)
                temperature = _f(self.parent.telemetry_temp)

                wind_limit, wind_limit_pointing = self.parent.wind_limits(t)

                if wind is not None and wind > wind_limit:
                    icon_label5 = QLabel()
                    icon_label5.setPixmap(ToiIcon("icon_wind", "red", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label5)
                elif wind is not None and wind > wind_limit_pointing:
                    icon_label6 = QLabel()
                    icon_label6.setPixmap(ToiIcon("icon_wind", "orange", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label6)

                rain = _f(self.parent.telemetry_rain)
                if rain is not None and rain > 0:
                    icon_label9 = QLabel()
                    icon_label9.setPixmap(ToiIcon("icon_rain", "red", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label9)

                if humidity is not None and humidity > float(self.parent.cfg_humidity_limit):
                    icon_label7 = QLabel()
                    icon_label7.setPixmap(ToiIcon("icon_water", "red", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label7)

                if temperature is not None and temperature < float(self.parent.cfg_temperature_limit):
                    icon_label8 = QLabel()
                    icon_label8.setPixmap(ToiIcon("icon_cold", "red", size=14).pixmap(14, 14))
                    lay.addWidget(icon_label8)


            self.obs_t.setCellWidget(i,0,icons)

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

    def report(self):
        self.report_window = ReportWindow(self.parent)
        self.report_window.show()

    # =================== OKNO GLOWNE ====================================
    def set_hints(self):
        # okienka z wyjasnieniem po najechaniu na pole; Wind/Direction dopisuja limity w TOI.wind_field_style
        hints = {
            "ticStatus2": "TIC server, checked every 3 s.",
            "natsStatus": "TOI connection to NATS. Orange: reconnecting.",
            "followerStatus": "Dome follower of the active telescope: heartbeat every 10 s. Red: none for 30 s.",
            "downloaderStatus": "OFP downloader of the active telescope, asked every 5 s (alive RPC).",
            "ofpStatus": "OFP pipeline of the active telescope, asked every 5 s (alive RPC).",
            "flatOwStatus": "flat_overwatch heartbeat. Grey: no heartbeat subject yet (toi_config.yaml).",
            "weatherOwStatus": "weather_overwatch heartbeat. Grey: no heartbeat subject yet (toi_config.yaml).",
            "temp": "Davis weather station. Red below -1 °C.",
            "hummidity": f"Davis weather station. Red above {self.parent.cfg_humidity_limit} % or rain.",
            "wind": "Davis weather station.",
            "windDir": "Davis weather station.",
            "fwhm": "Not available yet.",
            "zeropoint": "Not available yet.",
            "clouds": "Not available yet.",
            "date": "UT date.",
            "ut": "Yellow: Sun above 1°. Blue: Sun 1° to -18°.",
            "ojd": "Julian Date.",
            "sid": "Local sidereal time.",
        }
        for name, txt in hints.items():
            for suffix in ("_l", "_e"):
                widget = getattr(self, name + suffix, None)
                if widget is not None:
                    widget.setToolTip(txt)

    def mkUI(self):

        grid = QGridLayout()
        w = 0
        # lampki polaczen obok siebie, od lewej
        self.ticStatus2_l = QLabel("\u2665  TIC")
        self.natsStatus_l = QLabel("\u2665  NATS")
        self.natsStatus_l.setStyleSheet("color: red;")
        # serwisy aktywnego teleskopu; szare, dopoki nic o nich nie wiemy
        # krotkie nazwy, zeby caly wiersz sie miescil - pelne w podpowiedziach
        self.followerStatus_l = QLabel("\u2665 DOME FLW")
        self.downloaderStatus_l = QLabel("\u2665 FITS DWL")
        self.ofpStatus_l = QLabel("\u2665 OFP")
        self.flatOwStatus_l = QLabel("\u2665 FLAT OW")
        self.weatherOwStatus_l = QLabel("\u2665 WEATHER OW")
        self.ticStatus2_l.setText("\u2665 TIC")
        self.natsStatus_l.setText("\u2665 NATS")
        status_box = QHBoxLayout()
        status_box.setSpacing(12)
        lamps = (self.ticStatus2_l, self.natsStatus_l, self.followerStatus_l, self.downloaderStatus_l,
                 self.ofpStatus_l, self.flatOwStatus_l, self.weatherOwStatus_l)
        for lamp in lamps:
            status_box.addWidget(lamp)
        for lamp in lamps[2:]:
            lamp.setStyleSheet("color: rgb(190,190,190);")
        status_box.addStretch(1)
        grid.addLayout(status_box, w, 0, 1, 8)

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

        # na gorze warunki; czas (Date, UT, JD, SID) jest na dole obok logu
        grid.addWidget(self.temp_l, w, 0)
        grid.addWidget(self.temp_e, w, 1)

        grid.addWidget(self.hummidity_l, w, 2)
        grid.addWidget(self.hummidity_e, w, 3)

        grid.addWidget(self.wind_l, w, 4)
        grid.addWidget(self.wind_e, w, 5)

        grid.addWidget(self.windDir_l, w, 6)
        grid.addWidget(self.windDir_e, w, 7)

        # na przyszlosc: jakosc nieba - na razie puste
        w = w + 1
        for col, (name, txt) in enumerate((("fwhm", "FWHM:"), ("zeropoint", "Zero point:"), ("clouds", "Clouds:"))):
            label = QLabel(txt)
            label.setAlignment(Qt.AlignCenter)
            field = QLineEdit("--")
            field.setAlignment(Qt.AlignCenter)
            field.setReadOnly(True)
            field.setStyleSheet("background-color: rgb(235,235,235);")
            setattr(self, f"{name}_l", label)
            setattr(self, f"{name}_e", field)
            grid.addWidget(label, w, 2 * col)
            grid.addWidget(field, w, 2 * col + 1)

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


        #self.testowyPocisk_p.clicked.connect(self.parent.force_update)



        self.report_p = QPushButton('REPORT')
        self.report_p.clicked.connect(self.report)
        self.ping_p = QPushButton('PING')
        self.ping_p.clicked.connect(self.parent.ping)


        w = 7

        self.msg_e = QTextEdit()
        self.msg_e.setReadOnly(True)
        self.msg_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.msg_e, w, 0, 3, 4)

        # czas obok logu, w miejscu po przyciskach okien - uklad jak dawniej na gorze
        grid.addWidget(self.date_l, w, 4)
        grid.addWidget(self.date_e, w, 5)
        grid.addWidget(self.ut_l, w, 6)
        grid.addWidget(self.ut_e, w, 7)
        grid.addWidget(self.ojd_l, w + 1, 4)
        grid.addWidget(self.ojd_e, w + 1, 5)
        grid.addWidget(self.sid_l, w + 1, 6)
        grid.addWidget(self.sid_e, w + 1, 7)

        w = w + 3

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 0, 1, 8)

        self.set_hints()

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

class ReportWindow(BaseWindow):
    def __init__(self, parent):
        super(ReportWindow, self).__init__()
        self.parent = parent
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 200, self.parent.obs_window_geometry[1]+100, 500, 500)
        self.mkUI()
        self.setWindowTitle('Report')


    def report(self):
        try:
            self._write_report()
        except Exception as e:
            logger.exception("TOI: report failed")
            self.parent.WarningWindow(f"WARNING: report failed: {e}")

    def _write_report(self):
        self.rep_name =self.parent.ut.replace("/","_").replace(" ","_").replace(":","_")
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

        zmienne = ["report",
                   "active_tel",
                   "active_tel_i",
                   "acces",
                   "tel_acces",
                   "ob",
                   "ob_progress",
                   "nats_ob_progress",
                   "planrunners",
                   "telescope_switch_status",
                   "toi_switch_status",
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
                   "telemetry_rain",
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
                   "done_uobi",
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

        auto_foc_adjust_button = self.parent.mntGui.telAutoFocus_c.isChecked()
        txt = txt + f'\nauto_foc_adjust_button: {auto_foc_adjust_button}\n'

        with open(self.dir_name + "/telemetry.txt", "w") as file3:
            file3.write(txt)

        txt = ""
        for k in self.parent.nats_plan_status.keys():
            try:
                val = str(self.parent.nats_plan_status[k])
                txt = txt + f'*** {k}: {val}' + "\n"
            except:
                pass
        with open(self.dir_name + "/nats_plan.txt", "w") as file4:
            file4.write(txt)

        txt = ""
        for k in self.parent.plan.keys():
            try:
                txt = txt + "------------------------\n"
                txt = txt + f"*** {k}\n"
                val = self.parent.plan[k]
                txt = txt + f'{val}' + "\n"
            except:
                pass
        with open(self.dir_name + "/local_plan.txt", "w") as file5:
            file5.write(txt)

        write_claude_report(self.parent, self.dir_name)

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


class CzuwakWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.czuwak = 0

        self.setWindowTitle("Czuwak")
        self.setGeometry(100, 100, 300, 200)

        # Układ w pionie
        layout = QVBoxLayout()

        # Etykieta z instrukcją
        self.label = QLabel("Time Left: ", self)
        layout.addWidget(self.label)

        # Przycisk
        self.button = QPushButton("Push Me!", self)
        self.button.clicked.connect(self.on_button_click)
        layout.addWidget(self.button)

        # Ustawienie układu
        self.setLayout(layout)

    def on_button_click(self):
        self.czuwak = 0
        self.label.setText("Ok!")
        self.close()
