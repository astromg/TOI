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
- ``Conditions`` — :class:`ConditionsTab`, night plots of all telescopes; a combo chooses what (FWHM, zero point;
  more weather telemetry later).

``TOI`` keeps its old names for the tabs (``focusGui``, ``flatGui``, ``guiderGui``, ``planrunnerGui``,
``conditionsGui``), so the
code that feeds them did not change. Tabs are pages of a ``QTabWidget``: never ``show()`` a tab — that
draws it over the current one; :meth:`AuxWindow.show_tab` brings a tab to the front. Events bring tabs up by
themselves: M3 changing port → Optical path (:meth:`AuxWindow.m3_moved`), a SKYFLAT/DOMEFLAT OB starting →
Calibration, a FOCUS OB starting → Focus (:meth:`AuxWindow.ob_started`).
"""

import copy
import datetime

import ephem
import matplotlib
import numpy
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from pyaraucaria.date import datetime_to_julian, get_oca_jd
from pyaraucaria.focus import Focus
from scipy.ndimage import gaussian_filter1d

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

    # pierwsze slowo OB -> zakladka, ktora sie podnosi, gdy ten OB rusza
    OB_TABS = {"SKYFLAT": "calibration", "DOMEFLAT": "calibration", "FOCUS": "focus"}

    def ob_started(self, program):
        """An OB started on the active telescope: bring up the tab that shows it."""
        words = program.split() if program else []
        tab = self.OB_TABS.get(words[0]) if words else None
        if tab:
            self.show_tab(getattr(self, tab))

    def m3_moved(self):
        if self.tabs.isTabVisible(self.tabs.indexOf(self.optics)):
            self.show_tab(self.optics)

    def set_instrument(self, kind, name):
        """The instrument window switched to instrument ``name`` of ``kind`` (camera / spectrograph)."""
        self.calibration.set_instrument(kind, name)
        if kind == "camera":
            self.focus.set_camera(name)
        self.tabs.setTabText(self.tabs.indexOf(self.calibration), f"Calibration · {name}")

    def tab_changed(self):
        # wykresy warunkow rysujemy dopiero, gdy ktos na nie patrzy
        if self.tabs.currentWidget() is self.conditions:
            self.conditions.redraw()

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
        self.conditions = ConditionsTab(self.parent)
        self.tabs.addTab(self.optics, "Optical path")
        self.tabs.addTab(self.calibration, "Calibration")
        self.tabs.addTab(self.focus, "Focus")
        self.tabs.addTab(self.guider, "Guider")
        self.tabs.addTab(self.planrunner, "Plan Runner")
        self.tabs.addTab(self.conditions, "Conditions")
        self.tabs.currentChanged.connect(self.tab_changed)
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
    """Autofocus of the active telescope: the last result (points, fit, maximum), a new run, the focus log.

    Recalculate only computes (and publishes the result); SET moves the focuser to it. The run uses the camera
    chosen in the instrument window (:meth:`set_camera`) and its filters (``TOI.instrument_filters``)."""

    def __init__(self, parent):
        super(FocusTab, self).__init__()
        self.parent = parent
        self.camera = None
        self.status = {}            # ostatni wynik aktywnego teleskopu (tic.status.<tel>.toi.focus)
        self.focus_records = {}     # {tel: [rekord, ...]} z tic.status.<tel>.toi.focus_record
        self.mkUI()
        self.show_status({})

    def updateUI(self):
        # po zmianie teleskopu
        tel = self.parent.active_tel
        if tel != None:
            cfg = self.parent.nats_cfg[tel]
            # krok z toi_config.yaml (focus_step), dopiero bez niego focuser.default_step z TIC
            step = self.parent.local_cfg.get(tel, {}).get("focus_step", cfg.get("focus_def_step"))
            if step is not None:
                self.steps_e.setText(str(step))
            model = self.parent.focus_model_now(tel)
            if model is not None:
                self.last_e.setText(str(int(model)))
            elif "focus_def_pos" in cfg.keys():
                self.last_e.setText(str(cfg["focus_def_pos"]))
            self.range_e.setText("8")
            self.set_methods(tel)
        self.draw_log()

    def set_methods(self, tel):
        # metody z toi_config.yaml, tylko te, ktore zna pyaraucaria.focus
        known = list(Focus.METHODS)
        methods = [m for m in self.parent.local_cfg.get(tel, {}).get("focus_methods", known) if m in known] or known
        self.method_s.clear()
        self.method_s.addItems(methods)
        self.method_s.setCurrentText(self.parent.focus_default_method(tel))

    def set_camera(self, name):
        """The camera the autofocus run uses; its filters go to the filter combo ("current": leave the wheel)."""
        self.camera = name
        self.camera_e.setText(name)
        chosen = self.filter_s.currentText()
        self.filter_s.clear()
        self.filter_s.addItems(["current"] + self.parent.instrument_filters(name))
        if self.filter_s.findText(chosen) >= 0:
            self.filter_s.setCurrentText(chosen)

    def show_status(self, data):
        self.status = data or {}
        state = self.status.get("status")
        result = self.status.get("max_sharpness_focus")
        if state == "ok" and result is not None:
            self.result_e.setText(f"{int(result)}")
        else:
            self.result_e.setText(state or "")
        self.set_p.setEnabled(state == "ok" and result is not None)
        self.redraw()

    def redraw(self):
        data = self.status
        x, y = data.get("focus_values") or [], data.get("sharpness_values") or []
        fit_x, fit_y = data.get("fit_x") or [], data.get("fit_y") or []
        result = data.get("max_sharpness_focus")

        self.axes.clear()
        if len(x) > 0 and len(x) == len(y):
            self.axes.plot(x, y, "r.", markersize=8)
        if len(fit_x) > 1 and len(fit_x) == len(fit_y):
            self.axes.plot(fit_x, fit_y)
        if result is not None:
            # maksimum dopasowania zawsze widac; czerwone tylko, gdy wynik jest dobry
            if data.get("status") == "ok":
                self.axes.axvline(x=result, color="red")
            else:
                self.axes.axvline(x=result, color="gray", linestyle="--")
        title = [str(data[k]) for k in ("method", "filter") if data.get(k)]
        if data.get("time"):
            title.append(f'{data["time"]} UT')
        self.axes.set_title("   ".join(title), fontsize=10)
        self.axes.set_xlabel("focus encoder position")
        self.axes.set_ylabel(self.sharpness_label(data.get("method")))
        self.canvas.draw()

    # co mierzy pyaraucaria.focus (Focus.METHODS[metoda]["measurement"]); dopasowanie nie zmienia jednostek
    SHARPNESS_LABELS = {
        "rms": "image RMS [ADU]",                   # odchylenie std. pikseli, bez 10% brzegow klatki
        "laplacian": "Laplacian variance [ADU²]",   # wariancja laplasjanu obrazu - czula na ostre krawedzie gwiazd
        "fwhm": "(10 − FWHM [px]) × 5",             # FWHM gwiazd z FFS, odwrocone, zeby maksimum bylo ostre
    }

    def sharpness_label(self, method):
        try:
            measurement = Focus.METHODS[method]["measurement"]
        except (KeyError, TypeError):
            return "sharpness"
        return self.SHARPNESS_LABELS.get(measurement, "sharpness")

    def add_record(self, tel, data):
        if not data:        # czasem przychodzi pusty, jak nikt dlugo focusa nie robil
            return
        self.focus_records.setdefault(tel, []).append(data)
        if tel == self.parent.active_tel:
            self.draw_log()

    FOCUS_FAILED = QtGui.QColor(255, 153, 153)

    def draw_log(self):
        records = self.focus_records.get(self.parent.active_tel, [])
        font = QtGui.QFont()
        font.setPointSize(10)
        self.log_t.setRowCount(len(records))
        for i, r in enumerate(records):
            date, ut = (str(r.get("time") or "").split() + ["", ""])[:2]
            row = [date, ut, self._num(r.get("max_sharpness_focus"), "{:.0f}"), r.get("filter") or "--",
                   self._num(r.get("davis_temperature"), "{:.1f}"), self._num(r.get("davis_humidity"), "{:.0f}%"),
                   r.get("status") or "--", r.get("method") or "--"]
            for col, txt in enumerate(row):
                cell = QTableWidgetItem(str(txt))
                cell.setFont(font)
                if r.get("status") != "ok":
                    cell.setBackground(self.FOCUS_FAILED)
                self.log_t.setItem(i, col, cell)
        self.log_t.resizeColumnsToContents()
        self.log_t.scrollToBottom()

    @staticmethod
    def _num(value, fmt):
        try:
            return fmt.format(float(value))
        except (TypeError, ValueError):
            return "--"

    def mkUI(self):

        grid = QGridLayout()
        w = 0

        self.method_l = QLabel("Method:")
        self.method_s = QComboBox()
        self.method_s.addItems(list(Focus.METHODS))     # lista teleskopu przychodzi w set_methods
        self.recalc_p = QPushButton("Recalculate")
        self.recalc_p.clicked.connect(self.parent.focus_recalc)

        grid.addWidget(self.method_l, w, 0)
        grid.addWidget(self.method_s, w, 1)
        grid.addWidget(self.recalc_p, w, 2, 1, 2)

        w = w + 1
        self.fig = Figure((1, 1), linewidth=1, dpi=100, layout="constrained")   # opisy osi zawsze sie mieszcza
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111)
        grid.addWidget(self.canvas, w, 0, 1, 4)
        grid.setRowStretch(w, 1)

        w = w + 1
        self.result_l = QLabel("RESULT:")
        self.result_e = QLineEdit()
        self.result_e.setReadOnly(True)
        self.result_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.set_p = QPushButton("SET")
        self.set_p.clicked.connect(self.parent.focus_set_result)
        grid.addWidget(self.result_l, w, 0)
        grid.addWidget(self.result_e, w, 1)
        grid.addWidget(self.set_p, w, 2, 1, 2)

        w = w + 1
        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 0, 1, 4)

        w = w + 1
        self.camera_l = QLabel("Camera:")
        self.camera_e = QLineEdit()
        self.camera_e.setReadOnly(True)
        self.camera_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.filter_l = QLabel("Filter:")
        self.filter_s = QComboBox()
        self.filter_s.addItems(["current"])
        grid.addWidget(self.camera_l, w, 0)
        grid.addWidget(self.camera_e, w, 1)
        grid.addWidget(self.filter_l, w, 2)
        grid.addWidget(self.filter_s, w, 3)

        w = w + 1
        self.last_l = QLabel("Central Value:")
        self.last_e = QLineEdit()
        self.exp_l = QLabel("Exp. time:")
        self.exp_e = QLineEdit("5")
        grid.addWidget(self.last_l, w, 0)
        grid.addWidget(self.last_e, w, 1)
        grid.addWidget(self.exp_l, w, 2)
        grid.addWidget(self.exp_e, w, 3)

        w = w + 1
        self.steps_l = QLabel("Step:")
        self.steps_e = QLineEdit()
        self.range_l = QLabel("Steps No.:")
        self.range_e = QLineEdit()
        grid.addWidget(self.steps_l, w, 0)
        grid.addWidget(self.steps_e, w, 1)
        grid.addWidget(self.range_l, w, 2)
        grid.addWidget(self.range_e, w, 3)

        w = w + 1
        self.autoFocus_p = QPushButton('FIND FOCUS')
        self.autoFocus_p.clicked.connect(self.parent.auto_focus)
        grid.addWidget(self.autoFocus_p, w, 0, 1, 4)

        self.log_t = QTableWidget(0, 8)
        self.log_t.setHorizontalHeaderLabels(["DATE", "UT", "FOCUS", "FILTER", "TEMP", "HUMID", "STATUS", "METHOD"])
        self.log_t.setShowGrid(False)
        self.log_t.verticalHeader().hide()
        self.log_t.verticalHeader().setDefaultSectionSize(10)
        self.log_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.log_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_t.horizontalHeader().setStretchLastSection(True)
        self.log_t.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.log_t, 0, 4, w + 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 3)

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


# ############### CONDITIONS ##########################

class ConditionsTab(QWidget):
    """Night plots of all telescopes; the combo chooses what is drawn. Filter/airmass cuts apply to FWHM."""

    PLOTS = ["FWHM", "Zero point"]

    def __init__(self, parent):
        super(ConditionsTab, self).__init__()
        self.parent = parent
        self.mkUI()

        self.fwhm = {t:[] for t in self.parent.fits_ffs_data.keys()}
        self.time = {t: [] for t in self.parent.fits_ffs_data.keys()}
        self.airmass = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.focus_time = {t: [] for t in self.parent.fits_ffs_data.keys()}

    def redraw(self):
        plot = self.plot_s.currentText()
        self.filter_e.setEnabled(plot == "FWHM")
        self.airmass_e.setEnabled(plot == "FWHM")
        self.ax.clear()
        if self.parent.jd:
            if plot == "FWHM":
                self.plot_fwhm()
            elif plot == "Zero point":
                self.plot_zero_point()
        self.fig.subplots_adjust(bottom=0.15, top=0.95, left=0.08, right=0.988)
        self.canvas.draw()

    def plot_fwhm(self):
        self.fwhm = {t:[] for t in self.parent.fits_ffs_data.keys()}
        self.time = {t: [] for t in self.parent.fits_ffs_data.keys()}
        self.airmass = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.focus_time = {t: [] for t in self.parent.fits_ffs_data.keys()}

        for t in self.parent.fits_ffs_data.keys():
            for x in self.parent.fits_ffs_data[t]:
                try:
                    if x["raw"]["header"]["OBSTYPE"] != "focus":
                        if str(self.filter_e.text()) in x["raw"]["header"]["FILTER"]:
                            if "fwhm" in x["raw"].keys():
                                airmass = float(x["raw"]["header"]["AIRMASS"])
                                cond = True
                                try:
                                    if len(str(self.airmass_e.text())) > 0:
                                        cond = float(self.airmass_e.text()) > airmass
                                except ValueError:
                                    pass
                                if cond:
                                    self.airmass[t].append(airmass)
                                    fwhm = (float(x["raw"]["fwhm"]["fwhm_x"])+float(x["raw"]["fwhm"]["fwhm_y"]))/2.
                                    fwhm = fwhm *  self.parent.nats_cfg[t]["pixel_scale"]
                                    self.fwhm[t].append(fwhm)
                                    time = float(x["raw"]["header"]["JD"])
                                    self.time[t].append(time)

                    if "OBSTYPE" in x["raw"]["header"].keys() and "NLOOPS" in x["raw"]["header"].keys() and "LOOP" in x["raw"]["header"].keys():
                        if x["raw"]["header"]["OBSTYPE"] == "focus" and float(x["raw"]["header"]["NLOOPS"]) == float(x["raw"]["header"]["LOOP"]):
                            self.focus_time[t].append(float(x["raw"]["header"]["JD"]))
                except (ValueError, TypeError):   # TyoeError - na wypadek waretosci nan
                    pass

        x0 = float(str(self.parent.jd).split(".")[0])+0.4
        x1 = x0 + 0.6

        for t in self.parent.fits_ffs_data.keys():
            x = self.time[t]
            y = self.fwhm[t]
            x = numpy.array(x)
            y = numpy.array(y)
            mk = x < x0
            x = x[mk]
            y = y[mk]
            x = x + 1
            self.ax.scatter(x, y, marker=".", color=self.parent.nats_cfg[t]['color'], alpha=0.05)

            x = self.time[t]
            y = self.fwhm[t]
            self.ax.scatter(x, y, marker=".", color=self.parent.nats_cfg[t]['color'], alpha=1, s=100, label=t)

            ft = numpy.array(self.focus_time[t])
            mk = ft > x0
            ft = ft[mk]

            for focus_time in ft:
                self.ax.axvline(x=focus_time, color=self.parent.nats_cfg[t]['color'],alpha=0.8)

        xtics = []
        t =  ephem.Date(x0)
        while t < ephem.Date(x1):
            t = ephem.Date(t) + ephem.hour
            h = str(ephem.Date(t)).split()
            xtics.append( ephem.Date(h[0]+" "+h[1].split(":")[0]+":00:00"))
        xtics_labels = [str(x).split()[1].split(":")[0]+":"+str(x).split()[1].split(":")[1] for x in xtics]
        self.ax.set_xticks(xtics)
        self.ax.set_xticklabels(xtics_labels,rotation=45,minor=False)

        self.ax.set_xlim(x0,x1)
        self.ax.set_ylim(0,5)
        self.ax.legend()
        self.ax.set_xlabel("UT")
        self.ax.set_ylabel("fwhm [arcsec]")

    def plot_zero_point(self):
        # fits_photo_z0_data: {tel: [{'filter', 'zero_value', 'oca_jd', 'mode'}, ...]}
        fits_photo_z0_data_copy = copy.deepcopy(self.parent.fits_photo_z0_data)
        tim_ranges = self.parent.time_ranges()
        today_oca_jd = get_oca_jd(datetime_to_julian(tim_ranges['today']))
        yesterday_oca_jd = get_oca_jd(datetime_to_julian(tim_ranges['yesterday']))
        color = {'V': 'green', 'B': 'blue', 'Ic': 'red'}

        all_val_td = []
        all_dat_td = []
        try:
            for t in fits_photo_z0_data_copy.keys():
                val_td = []
                filter_td = []
                dat_td = []
                val_yd = []
                filter_yd = []
                dat_yd = []
                for x in fits_photo_z0_data_copy[t]:
                    if x["oca_jd"] >= today_oca_jd:
                        val_td.append(x["zero_value"])
                        all_val_td.append(x["zero_value"])
                        filter_td.append(color[x["filter"]])
                        dat_td.append(x["oca_jd"] - numpy.floor(x["oca_jd"]))
                        all_dat_td.append(x["oca_jd"] - numpy.floor(x["oca_jd"]))
                    if today_oca_jd > x["oca_jd"] >= yesterday_oca_jd:
                        val_yd.append(x["zero_value"])
                        filter_yd.append(color[x["filter"]])
                        dat_yd.append(x["oca_jd"] - numpy.floor(x["oca_jd"]))
                self.ax.scatter(
                    dat_td, val_td, edgecolor=filter_td, alpha=0.8,
                    facecolors="none", linewidths=1, s=30
                )
                self.ax.scatter(
                    dat_td, val_td, c=self.parent.nats_cfg[t]['color'], alpha=0.7, label=t, s=13
                )
                self.ax.scatter(
                    dat_yd, val_yd, edgecolor=filter_yd, alpha=0.1,
                    facecolors="none", linewidths=1, s=30
                )
                self.ax.scatter(
                    dat_yd, val_yd, c=self.parent.nats_cfg[t]['color'], alpha=0.1, s=13
                )

            self.ax.axhline(y=0, color="black", linewidth=0.5)
            self.ax.axhline(y=-0.05, color="orange", linestyle="--", linewidth=1)
            self.ax.axhline(y=-0.1, color="red", linestyle="--", linewidth=1)

            x = numpy.asarray(all_dat_td)
            y = numpy.asarray(all_val_td)

            rem_nan_y = ~numpy.isnan(y)
            x = x[rem_nan_y]
            y = y[rem_nan_y]

            idx = numpy.argsort(x)

            x_sorted = x[idx]
            y_sorted = y[idx]

            self.ax.plot(x_sorted, gaussian_filter1d(y_sorted, sigma=6), color='#2E8B57', linewidth=1)

            x0 = 0.4
            x1 = 0.99
            xtics = []
            t = ephem.Date(x0)
            while t < ephem.Date(x1):
                t = ephem.Date(t) + ephem.hour
                h = str(ephem.Date(t)).split()
                xtics.append(ephem.Date(h[0] + " " + h[1].split(":")[0] + ":00:00"))
            xtics_labels = [str(x).split()[1].split(":")[0] + ":" + str(x).split()[1].split(":")[1] for x in xtics]
            self.ax.set_xticks(xtics)
            self.ax.set_xticklabels(xtics_labels, rotation=45, minor=False)
            self.ax.set_xlim(x0, x1)
            self.ax.legend()
            self.ax.set_xlabel("UT")
            self.ax.set_ylabel("zero point [mag]")
        except Exception as e:
            print(f'EXCEPTION plot_zero_point: {e}')

    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.plot_l = QLabel("Plot: ")
        self.plot_s = QComboBox()
        self.plot_s.addItems(self.PLOTS)
        self.plot_s.currentIndexChanged.connect(self.redraw)

        self.filter_l = QLabel("Filter filter: ")
        self.filter_e = QLineEdit("")
        self.filter_e.textChanged.connect(self.redraw)

        self.airmass_l = QLabel("Filter airmass: ")
        self.airmass_e = QLineEdit("")
        self.airmass_e.textChanged.connect(self.redraw)

        grid.addWidget(self.plot_l, w, 0)
        grid.addWidget(self.plot_s, w, 1)
        grid.addWidget(self.filter_l, w, 2)
        grid.addWidget(self.filter_e, w, 3)
        grid.addWidget(self.airmass_l, w, 4)
        grid.addWidget(self.airmass_e, w, 5)

        w = w + 1

        self.fig = Figure((1, 1), linewidth=1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        grid.addWidget(self.canvas, w, 0, 1, 6)

        w = w + 1
        self.toolbar = NavigationToolbar(self.canvas,self)
        grid.addWidget(self.toolbar, w, 0, 1, 6)

        self.setLayout(grid)

