#!/usr/bin/env python3
"""The Aux window: the operator's secondary panels as tabs of one window (second monitor, below FITS).

Tabs, in this order:
- ``Optical path`` — :class:`optics_view.SchematicView` of the active telescope; hidden when the telescope
  publishes no optical graph;
- ``Calibration`` — :class:`CalibrationTab`, one page per kind of instrument; follows the tab chosen in the
  instrument window (``InstrumentGui`` calls :meth:`AuxWindow.set_instrument`): a camera gets
  :class:`CameraCalibration` (flats), a spectrograph :class:`SpectrographCalibration` (to be defined);
- ``Focus`` — :class:`FocusTab`, autofocus curve and focus log;
- ``Guider`` — :class:`GuiderTab`, layout template, the guider does not work yet;
- ``Plan Runner`` — :class:`PlanrunnerTab`, what the plan runner says.

``TOI`` keeps its old names for the tabs (``focusGui``, ``flatGui``, ``guiderGui``, ``planrunnerGui``), so the
code that feeds them did not change. Tabs are pages of a ``QTabWidget``: never ``show()`` a tab — that
draws it over the current one; :meth:`AuxWindow.show_tab` brings a tab to the front.
"""

import datetime

import matplotlib
import numpy
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pyaraucaria.focus import Focus

from PyQtX import QtGui
from PyQtX.QtCore import Qt
from PyQtX.QtGui import QFont, QTextCursor
from PyQtX.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHeaderView, QLabel,
                             QLineEdit, QPushButton, QSlider, QStackedWidget, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from base_window import BaseWindow
from optics_view import SchematicView


class AuxWindow(BaseWindow):
    def __init__(self, parent):
        super(AuxWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Aux')
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 1910, self.parent.obs_window_geometry[1] + 810, 1000, 500)
        self.mkUI()
        self.parent.optics_model.graph_changed.connect(self.optics_changed)
        self.optics_changed()
        self.show()

    def show_tab(self, page):
        self.tabs.setCurrentWidget(page)
        self.show()
        self.raise_()

    def set_instrument(self, kind, name):
        """The instrument window switched to instrument ``name`` of ``kind`` (camera / spectrograph)."""
        self.calibration.set_instrument(kind, name)
        self.tabs.setTabText(self.tabs.indexOf(self.calibration), f"Calibration · {name}")

    def optics_changed(self):
        self.tabs.setTabVisible(self.tabs.indexOf(self.optics), self.parent.optics_model.graph is not None)

    def updateUI(self):
        # po zmianie teleskopu
        if self.parent.active_tel != None:
            self.tel_e.setText(self.parent.active_tel)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")
        self.calibration.updateUI()
        self.focus.updateUI()
        self.planrunner.updateUI()

    def mkUI(self):
        layout = QVBoxLayout()
        self.tel_e = QLineEdit()
        self.tel_e.setReadOnly(True)
        self.tel_e.setAlignment(Qt.AlignCenter)
        font = QFont("Courier New", 9)
        font.setBold(True)
        self.tel_e.setFont(font)
        layout.addWidget(self.tel_e)

        self.tabs = QTabWidget()
        self.optics = SchematicView(self.parent.optics_model, vertical=False)
        self.calibration = CalibrationTab(self.parent)
        self.focus = FocusTab(self.parent)
        self.guider = GuiderTab(self.parent)
        self.planrunner = PlanrunnerTab(self.parent)
        self.tabs.addTab(self.optics, "Optical path")
        self.tabs.addTab(self.calibration, "Calibration")
        self.tabs.addTab(self.focus, "Focus")
        self.tabs.addTab(self.guider, "Guider")
        self.tabs.addTab(self.planrunner, "Plan Runner")
        layout.addWidget(self.tabs)
        self.setLayout(layout)


# ############### CALIBRATION ##########################

class CalibrationTab(QStackedWidget):
    """Calibration of the instrument chosen in the instrument window: one page per kind of instrument."""

    def __init__(self, parent):
        super(CalibrationTab, self).__init__()
        self.camera = CameraCalibration(parent)
        self.spectrograph = SpectrographCalibration(parent)
        self.pages = {"camera": self.camera, "spectrograph": self.spectrograph}
        for page in self.pages.values():
            self.addWidget(page)

    def set_instrument(self, kind, name):
        page = self.pages[kind]
        page.set_instrument(name)
        self.setCurrentWidget(page)

    def updateUI(self):
        for page in self.pages.values():
            page.updateUI()


class CameraCalibration(QWidget):
    """Sky flats of a camera: age of the last evening/morning flats and science per filter
    (flat_overwatch, kept per telescope in ``flat_records``) and the flats log of this session."""

    def __init__(self, parent):
        super(CameraCalibration, self).__init__()
        self.parent = parent
        self.instrument = None
        self.mkUI()
        self.flat_records = {}      # {tel: {item: {filtr: {"last": ISO|None}}}} z flat_overwatch

    def set_instrument(self, name):
        self.instrument = name

    def updateUI(self):
        if self.parent.telescope:
            self.draw_flat_log()
            self.draw_flat_table(self.parent.active_tel)

    # kolory komorek EVENING / MORNING
    FLAT_FRESH = QtGui.QColor(182, 242, 182)    # flat swiezy
    FLAT_OLD = QtGui.QColor(255, 204, 128)      # flat stary
    FLAT_STALE = QtGui.QColor(255, 153, 153)    # filtr ostatnio uzywany, a swiezych flatow brak

    def update_flat_overwatch(self, tel, item, data):
        # item: flats_evening / flats_morning / science; trzymamy per teleskop, zeby po zmianie
        # teleskopu nie mieszac danych, a rysujemy tylko aktywny
        self.flat_records.setdefault(tel, {})[item] = data
        if tel == self.parent.active_tel:
            self.draw_flat_table(tel)

    def draw_flat_log(self):
        # log flatow tej sesji jako tabela bez siatki - naglowek zostaje widoczny przy przewijaniu
        font = QtGui.QFont()
        font.setPointSize(10)
        self.log_t.setRowCount(len(self.parent.flat_log))
        for i, r in enumerate(self.parent.flat_log):
            n = f'{r["n_exp"]}/{r["exp_no"]}' if "n_exp" in r and "exp_no" in r else "--"
            date, ut = r["timestamp_utc"].split()[:2]
            row = [date, ut.split(".")[0], r["filter"], n, f'{r["exp_time"]:.2f}', r["h_sun"], r["mean"]]
            for col, txt in enumerate(row):
                self.log_t.setItem(i, col, self._flat_cell(str(txt), font))
        self.log_t.resizeColumnsToContents()
        self.log_t.scrollToBottom()
        self.log_t.repaint()

    def draw_flat_table(self, tel):
        records = self.flat_records.get(tel, {})
        cfg = self.parent.local_cfg["toi"]
        fresh = datetime.timedelta(hours=cfg.get("flat_fresh_h", 20))
        old = datetime.timedelta(days=cfg.get("flat_old_days", 10))
        t0 = datetime.datetime.now(datetime.timezone.utc)

        def last(item, f):
            t = records.get(item, {}).get(f, {}).get("last")
            return datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc) if t else None

        # filtry bez zadnej daty pomijamy (np. kombinacje nd/diff na wk06); kolejnosc jak w kole filtrow
        filters = {f for rec in records.values() for f in rec}
        filters = [f for f in filters if any(last(item, f) for item in ("flats_evening", "flats_morning", "science"))]
        wheel = self.parent.nats_cfg.get(tel, {}).get("filter_list_names", [])
        filters.sort(key=lambda f: (wheel.index(f) if f in wheel else len(wheel), f))

        self.flat_table_t.clearContents()
        self.flat_table_t.setRowCount(len(filters))
        font = QtGui.QFont()
        font.setPointSize(10)

        for i, f in enumerate(filters):
            t_obj = last("science", f)
            self.flat_table_t.setItem(i, 0, self._flat_cell(f, font))
            for col, item in ((1, "flats_evening"), (2, "flats_morning")):
                t_flat = last(item, f)
                cell = self._flat_cell(self._age_txt(t0, t_flat), font)
                # alarm: filtr uzywany w ostatnich `old` dniach, a flatow tej sesji w tym czasie nie bylo
                if t_obj and t0 - t_obj <= old and (t_flat is None or t0 - t_flat > old):
                    cell.setBackground(self.FLAT_STALE)
                elif t_flat and t0 - t_flat <= fresh:
                    cell.setBackground(self.FLAT_FRESH)
                elif t_flat and t0 - t_flat > old:
                    cell.setBackground(self.FLAT_OLD)
                self.flat_table_t.setItem(i, col, cell)
            self.flat_table_t.setItem(i, 3, self._flat_cell(self._age_txt(t0, t_obj), font))

        # kolumny na szerokosc tekstu, a tabela tylko tak szeroka jak kolumny - reszte okna dostaje log flatow
        header = self.flat_table_t.horizontalHeader()
        for col in range(self.flat_table_t.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        width = header.length() + 2 * self.flat_table_t.frameWidth() + self.flat_table_t.verticalScrollBar().sizeHint().width()
        self.flat_table_t.setFixedWidth(width)
        self.flat_table_t.repaint()

    @staticmethod
    def _flat_cell(txt, font):
        cell = QTableWidgetItem(txt)
        cell.setFont(font)
        return cell

    @staticmethod
    def _age_txt(t0, t):
        if t is None:
            return "--"
        dt = t0 - t
        if dt.days == 0:
            return f'{dt.seconds / 3600.:.0f} hours'
        return f'{dt.days} days'

    def mkUI(self):
        grid = QGridLayout()
        self.flat_table_t = QTableWidget(0,4)
        self.flat_table_t.setHorizontalHeaderLabels(["FILTER", "EVENING FLAT", "MORNING FLAT", "OBJECT"])
        self.flat_table_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.flat_table_t.verticalHeader().hide()
        self.flat_table_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.flat_table_t.setStyleSheet("selection-background-color: white;")
        self.flat_table_t.verticalHeader().setDefaultSectionSize(10)
        grid.addWidget(self.flat_table_t, 0, 0)

        self.log_t = QTableWidget(0, 7)
        self.log_t.setHorizontalHeaderLabels(["DATE", "UT", "FILTER", "N", "EXP", "H_SUN", "ADU"])
        self.log_t.setShowGrid(False)
        self.log_t.verticalHeader().hide()
        self.log_t.verticalHeader().setDefaultSectionSize(10)
        self.log_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.log_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_t.horizontalHeader().setStretchLastSection(True)
        self.log_t.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.log_t, 0, 1)
        grid.setColumnStretch(1, 1)     # dodatkowa szerokosc okna idzie do logu, nie do tabeli
        self.setLayout(grid)


class SpectrographCalibration(QWidget):
    """Calibration of a spectrograph (BESO). Content to be defined (arcs, flats, ...)."""

    def __init__(self, parent):
        super(SpectrographCalibration, self).__init__()
        self.parent = parent
        self.mkUI()

    def set_instrument(self, name):
        self.info_l.setText(f"{name} spectrograph calibration")

    def updateUI(self):
        pass

    def mkUI(self):
        grid = QGridLayout()
        self.info_l = QLabel("Spectrograph calibration")
        self.info_l.setStyleSheet("""font-size: 22px;font-weight: bold;""")
        grid.addWidget(self.info_l, 0, 0)
        grid.addWidget(QLabel("Nothing here yet"), 1, 0)
        grid.setRowStretch(2, 1)
        self.setLayout(grid)


# ############### FOCUS ##########################

class FocusTab(QWidget):
    def __init__(self, parent):
        super(FocusTab, self).__init__()
        self.parent = parent
        self.mkUI()
        self.x = []
        self.y = []
        self.fit_x = []
        self.fit_y = []
        self.method = None
        self.max_sharp = None
        self.redraw()

    def redraw(self):
        self.axes.clear()
        if len(self.x) > 1 and len(self.y) > 1:
            self.axes.plot(self.x, self.y, "r.")
        if len(self.fit_x) > 1 and len(self.fit_y) > 1:
            self.axes.plot(self.fit_x, self.fit_y)
        if self.max_sharp:
            self.axes.axvline(x=self.max_sharp, color="red", alpha=1)
        if self.method:
            self.axes.set_title(f"{self.method}")
        self.axes.set_xlabel("focus encoder position")
        self.axes.set_ylabel("sharpness")
        self.canvas.draw()

    def updateUI(self):
        if self.parent.active_tel != None:
            if "focus_def_step" in self.parent.nats_cfg[self.parent.active_tel].keys():
                self.steps_e.setText(str(self.parent.nats_cfg[self.parent.active_tel]["focus_def_step"]))
            if "focus_def_pos" in self.parent.nats_cfg[self.parent.active_tel].keys():
                self.last_e.setText(str(self.parent.nats_cfg[self.parent.active_tel]["focus_def_pos"]))
            self.range_e.setText("8")
            self.log_e.clear()
            self.log_e.append("     DATE                             FOC              TEMP           STAT  ")
            self.log_e.append("                         UT                         FILTER            HUMID          METH")
            self.log_e.append("------------------------------------------------------------------------------------------------")

    def mkUI(self):

        grid = QGridLayout()
        w = 0

        self.recalc_p = QPushButton("Recalculate")
        self.recalc_p.clicked.connect(self.parent.focus_recalc)

        self.method_l = QLabel("Method:")
        self.method_s = QComboBox()
        self.method_s.addItems([m for m in Focus.METHODS.keys()])
        self.method_s.setCurrentText("laplacian")

        self.fig = Figure((1, 1), linewidth=1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0.1, 0.2, 0.8, 0.7])
        self.log_e = QTextEdit("")
        self.log_e.setReadOnly(True)
        self.log_e.setMinimumWidth(465)

        grid.addWidget(self.recalc_p, w, 0,1,2)

        grid.addWidget(self.method_l, w, 2)
        grid.addWidget(self.method_s, w, 3)

        grid.addWidget(self.log_e, w, 5, 5, 1)

        w = w + 1

        self.log_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.canvas, w, 0, 1, 4)

        w = w + 1

        self.range_l = QLabel("Steps No.:")
        self.range_e = QLineEdit()

        self.steps_l = QLabel("Step:")
        self.steps_e = QLineEdit()

        grid.addWidget(self.steps_l, w, 0)
        grid.addWidget(self.steps_e, w, 1)

        grid.addWidget(self.range_l, w, 2)
        grid.addWidget(self.range_e, w, 3)

        w = w + 1

        self.last_l = QLabel("Central Value:")
        self.last_e = QLineEdit()

        grid.addWidget(self.last_l, w, 0)
        grid.addWidget(self.last_e, w, 1)

        w = w + 1
        self.result_l = QLabel("RESULT:")
        self.result_e = QLineEdit()
        self.result_e.setReadOnly(True)
        self.result_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

        self.autoFocus_p = QPushButton('FIND FOCUS')
        self.autoFocus_p.clicked.connect(self.parent.auto_focus)
        grid.addWidget(self.result_l, w, 0)
        grid.addWidget(self.result_e, w, 1)
        grid.addWidget(self.autoFocus_p, w, 2, 1, 2)

        self.setLayout(grid)


# ############### GUIDER ##########################

class GuiderTab(QWidget):
    """Layout template: the guider does not work yet (``TOI.guider_loop`` is not scheduled)."""

    def __init__(self, parent):
        super(GuiderTab, self).__init__()
        self.parent = parent
        self.mkUI()
        self.canvas2.draw()

    def updateCoo(self,x,y,color):
        if len(x)>0:
            self.axes.plot(x, y, color=color, marker="o", markersize="10", markerfacecolor="none", linestyle="")
            self.canvas.draw()

    def updateImage(self, image):
        self.image = image
        self.image = numpy.asarray(self.image)
        self.image = self.image.astype(numpy.uint16)
        self.axes.clear()
        self.axes.axis("off")
        if len(self.image)>0:
            vmin = numpy.mean(self.image) - 1 * numpy.std(self.image)
            vmax = numpy.mean(self.image) + 1 * numpy.std(self.image)
            self.axes.imshow(self.image, vmin=vmin, vmax=vmax, cmap=matplotlib.colormaps["ocean"])
            self.canvas.draw()

    def update_plot(self,dx,dy):
        self.axes2.clear()
        self.axes2.set_xlim(-50, 50)
        self.axes2.set_ylim(-50, 50)
        self.axes2.axhline(y=0,color="k",linestyle="-",alpha=0.3)
        self.axes2.axvline(x=0,color="k",linestyle="-",alpha=0.3)
        self.axes2.plot([0,0],[0,numpy.sum(dy)],color="red")
        self.axes2.plot([0,numpy.sum(dx)],[0,0],color="red")

        self.axes2.plot(dx, dy, color="b", marker=".", linestyle="",alpha=0.2)
        if len(dx)>0:
            self.axes2.plot(dx[0], dy[0], color="b", marker=".", linestyle="", alpha=1)
        if len(dx)>1:
            self.axes2.plot(dx[1], dy[1], color="b", marker=".", linestyle="", alpha=0.6)
        self.canvas2.draw()

    def mkUI(self):
        self.fig = Figure((1.0, 0.5), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes.axis("off")

        self.fig2 = Figure((0.5, 0.5), linewidth=-1, dpi=100)
        self.canvas2 = FigureCanvas(self.fig2)
        self.axes2 = self.fig2.add_axes([0, 0, 1, 1])
        self.axes2.axis("off")

        grid = QGridLayout()

        w = 0
        grid.addWidget(self.canvas, w, 0,12,2)

        w = 0
        self.guiderCameraOn_l = QLabel("LOOP [s]:")
        self.guiderLoop_e = QLineEdit()
        self.guiderLoop_e.setText("5")
        self.guiderCameraOn_c = QCheckBox()
        self.guiderCameraOn_c.setChecked(False)
        self.guiderCameraOn_c.setLayoutDirection(Qt.RightToLeft)
        self.guiderCameraOn_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.guiderCameraOn_c.clicked.connect(self.parent.GuiderPassiveOnOff)
        grid.addWidget(self.guiderCameraOn_l, w, 2)
        grid.addWidget(self.guiderLoop_e, w, 3)
        grid.addWidget(self.guiderCameraOn_c, w, 4)
        w = w + 1
        self.guiderExp_l = QLabel("EXP:")
        self.guiderExp_e = QLineEdit()
        self.guiderExp_e.setText("2")
        grid.addWidget(self.guiderExp_l, w, 2)
        grid.addWidget(self.guiderExp_e, w, 3,1,2)
        w = w + 1
        self.treshold_s = QSlider(Qt.Horizontal)
        self.treshold_s.setMinimum(1)
        self.treshold_s.setMaximum(50)
        self.treshold_s.setValue(10)
        grid.addWidget(self.treshold_s, w, 2, 1, 3)
        w = w + 1
        self.fwhm_s = QSlider(Qt.Horizontal)
        self.fwhm_s.setMinimum(1)
        self.fwhm_s.setMaximum(10)
        self.fwhm_s.setValue(4)
        grid.addWidget(self.fwhm_s, w, 2, 1, 3)
        w = w + 1
        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 2, 1, 3)
        w = w + 1
        grid.addWidget(self.canvas2, w, 2, 2, 3)
        w = w + 3
        self.result_e = QTextEdit()
        self.result_e.setReadOnly(True)
        self.result_e.setStyleSheet("background-color: rgb(245,245,245);")
        grid.addWidget(self.result_e, w, 2,3,3)
        w = w + 3
        self.method_l = QLabel("Method:")
        self.method_s = QComboBox()
        self.method_s.addItems(["Auto", "Multistar", "Single star"])
        grid.addWidget(self.method_l, w, 2)
        grid.addWidget(self.method_s, w, 3,1,2)
        w = w + 1
        self.autoGuide_l = QLabel("AUTO GUIDE:")
        self.autoGuide_c = QCheckBox()
        self.autoGuide_c.setChecked(False)
        self.autoGuide_c.setLayoutDirection(Qt.RightToLeft)
        self.autoGuide_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        grid.addWidget(self.autoGuide_l, w, 2)
        grid.addWidget(self.autoGuide_c, w, 3)

        grid.setColumnMinimumWidth(0, 120)
        grid.setColumnMinimumWidth(1, 120)
        grid.setRowMinimumHeight(5, 200)
        grid.setRowStretch(5, 1)
        self.setLayout(grid)

        self.axes.clear()
        self.canvas.draw()

        self.axes2.clear()
        self.canvas2.draw()


# ############### PLAN RUNNER ##########################

class PlanrunnerTab(QWidget):
    def __init__(self, parent):
        super(PlanrunnerTab, self).__init__()
        self.parent = parent
        self.mkUI()
        self.text = {k:"" for k in self.parent.local_cfg["toi"]["telescopes"]}

    def updateUI(self):
        if self.parent.telescope:
            self.prog_call_e.setText(self.text[self.parent.active_tel])
            self.prog_call_e.moveCursor(QTextCursor.End)

    def mkUI(self):
        grid = QGridLayout()
        self.prog_call_e = QTextEdit()
        self.prog_call_e.setReadOnly(True)
        self.prog_call_e.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.prog_call_e, 0, 0)
        self.setLayout(grid)
