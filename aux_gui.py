#!/usr/bin/env python3
"""The Aux window: the operator's secondary panels as tabs of one window (second monitor, below FITS).

Tabs, in this order:
- ``Telescope`` — :class:`TelescopeTab`, the active telescope's page of the OCA manual (intranet, over HTTP),
  description on the left, changelog on the right;
- ``Tasks`` — :class:`TasksTab`, tasks for observers of the active telescope; shown first; empty table for now
  (later: GitHub issues filtered by labels);
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

import asyncio
import datetime
import logging
import re
import urllib.request

import ephem
import matplotlib
import numpy
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from pyaraucaria.date import datetime_to_julian, get_oca_jd
from pyaraucaria.focus import Focus
from scipy.ndimage import gaussian_filter1d, median_filter

from PyQtX import QtGui
from PyQtX.QtCore import Qt, QUrl
from PyQtX.QtGui import QTextCursor
from PyQtX.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHeaderView, QLabel,
                             QLineEdit, QPushButton, QSlider, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from base_window import BaseWindow
from optics_view import SchematicView

logger = logging.getLogger(__name__)


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
        self.parent.obsGui.bring_up(self)       # panel Aux na wierzch (tez gdy lezy jako zakladka)

    # pierwsze slowo OB -> zakladka, ktora sie podnosi, gdy ten OB rusza
    OB_TABS = {"SKYFLAT": "calibration", "DOMEFLAT": "calibration", "FOCUS": "focus"}

    def ob_started(self, program):
        """An OB started on the active telescope: bring up the tab that shows it."""
        words = program.split() if program else []
        tab = self.OB_TABS.get(words[0]) if words else None
        if tab:
            self.show_tab(getattr(self, tab))

    # etykieta komunikatu z tic.status.ocm.messages -> wykres w zakladce Conditions, ktory sie podnosi
    ALERT_PLOTS = {"FWHM WARNING": "FWHM", "ZERO POINT WARNING": "Zero point"}

    def alert_received(self, label):
        """weather_overwatch alert (seeing / zero point): bring up Conditions with the matching plot."""
        plot = self.ALERT_PLOTS.get(label)
        if plot:
            self.conditions.plot_s.setCurrentText(plot)     # zmiana wyboru sama przerysowuje
            self.show_tab(self.conditions)

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
        # po zmianie teleskopu; jego nazwa i kolor sa w pasku tytulu panelu (ObsGui.set_panel_telescope)
        self.telescope.updateUI()
        self.calibration.updateUI()
        self.focus.updateUI()
        self.planrunner.updateUI()

    def mkUI(self):
        layout = QVBoxLayout()

        self.tabs = QTabWidget()
        self.telescope = TelescopeTab(self.parent)
        self.tasks = TasksTab(self.parent)
        self.optics = SchematicView(self.parent.optics_model, vertical=False)
        self.calibration = CalibrationTab(self.parent)
        self.focus = FocusTab(self.parent)
        self.guider = GuiderTab(self.parent)
        self.planrunner = PlanrunnerTab(self.parent)
        self.conditions = ConditionsTab(self.parent)
        self.tabs.addTab(self.telescope, "Telescope")
        self.tabs.addTab(self.tasks, "Tasks")
        self.tabs.addTab(self.optics, "Optical path")
        self.tabs.addTab(self.calibration, "Calibration")
        self.tabs.addTab(self.focus, "Focus")
        self.tabs.addTab(self.guider, "Guider")
        self.tabs.addTab(self.planrunner, "Plan Runner")
        self.tabs.addTab(self.conditions, "Conditions")
        self.tabs.currentChanged.connect(self.tab_changed)
        self.tabs.setCurrentWidget(self.tasks)      # na start zadania dla obserwatora
        layout.addWidget(self.tabs)
        self.setLayout(layout)


# ############### TELESCOPE ##########################

class TelescopeTab(QWidget):
    """The active telescope's pages of the OCA manual, fetched over HTTP from the intranet copy (``toi.oca_manual_url``
    in ``toi_config.yaml``; the server pulls the manual from GitHub every hour): the description on the left, the
    changelog (a separate page of the manual, ``telescope_<tel>_changelog``) on the right. Fetched on every
    telescope switch and with Reload."""

    TIMEOUT = 5     # s

    def __init__(self, parent):
        super(TelescopeTab, self).__init__()
        self.parent = parent
        self.mkUI()

    def updateUI(self):
        if self.parent.active_tel != None:
            asyncio.ensure_future(self.load(self.parent.active_tel))

    def page_url(self, tel, page=""):
        base = self.parent.local_cfg["toi"].get("oca_manual_url", "http://docker.oca.lan:8081").rstrip("/")
        return f"{base}/telescope_{tel}{page}/"

    async def load(self, tel):
        url = self.page_url(tel)
        self.source_l.setText(f"{url}   loading...")
        await asyncio.gather(self.load_page(tel, self.text_b, url),
                             self.load_page(tel, self.changelog_b, self.page_url(tel, "_changelog")))
        if tel == self.parent.active_tel:
            self.source_l.setText(f"{url}   (fetched {datetime.datetime.now().strftime('%H:%M')})")

    async def load_page(self, tel, browser, url):
        try:
            # urllib blokuje, wiec w osobnym watku - petla Qt/asyncio nie moze stanac na czas pobierania
            html = await asyncio.to_thread(self._fetch, url)
            body = self.for_qt(html)
        except Exception as e:
            body = (f"<p><b>No OCA manual page for {tel}</b></p><p>{url}</p><p>{e}</p>"
                    f"<p>Check <code>toi.oca_manual_url</code> in <code>toi_config.yaml</code>.</p>")
        if tel != self.parent.active_tel:      # w miedzyczasie zmieniono teleskop
            return
        browser.document().setBaseUrl(QUrl(url))    # wzgledne linki manuala
        browser.setHtml(body)

    def _fetch(self, url):
        with urllib.request.urlopen(url, timeout=self.TIMEOUT) as r:
            return r.read().decode("utf-8")

    @staticmethod
    def for_qt(html):
        """The page of mkdocs Material → what QTextBrowser draws: only the article, without the ¶ anchors,
        admonitions as quotes, tables with lines."""
        start = html.find('<article')
        end = html.find('</article>')
        if start < 0 or end < 0:
            raise ValueError("no <article> in the page (has the manual's theme changed?)")
        body = html[html.index('>', start) + 1:end]
        body = re.sub(r'<a class="headerlink"[^>]*>.*?</a>', '', body)
        body = re.sub(r'<div class="admonition[^"]*">\s*<p class="admonition-title">(.*?)</p>(.*?)</div>',
                      r'<blockquote><b>\1:</b>\2</blockquote>', body, flags=re.S)
        return body.replace('<table>', '<table border="1" cellspacing="0" cellpadding="3">')

    def mkUI(self):
        grid = QGridLayout()
        self.text_b = QTextBrowser()
        self.text_b.setOpenExternalLinks(True)
        self.changelog_b = QTextBrowser()
        self.changelog_b.setOpenExternalLinks(True)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.text_b)
        splitter.addWidget(self.changelog_b)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        grid.addWidget(splitter, 0, 0, 1, 2)
        self.source_l = QLabel("")
        self.source_l.setStyleSheet("color: gray;")
        grid.addWidget(self.source_l, 1, 0)
        self.reload_p = QPushButton("Reload")
        self.reload_p.clicked.connect(self.updateUI)
        grid.addWidget(self.reload_p, 1, 1)
        grid.setColumnStretch(0, 1)
        self.setLayout(grid)


# ############### TASKS ##########################

class TasksTab(QWidget):
    """Tasks for observers of the active telescope. For now an empty table; later GitHub issues of a chosen
    repository, filtered by labels (a task label and the telescope's label)."""

    COLUMNS = ["#", "TASK", "LABELS", "UPDATED"]

    def __init__(self, parent):
        super(TasksTab, self).__init__()
        self.parent = parent
        self.mkUI()

    def mkUI(self):
        grid = QGridLayout()
        self.tasks_t = QTableWidget(0, len(self.COLUMNS))
        self.tasks_t.setHorizontalHeaderLabels(self.COLUMNS)
        self.tasks_t.verticalHeader().hide()
        self.tasks_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tasks_t.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.tasks_t.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)     # tytul zadania bierze reszte szerokosci
        for col in (0, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        grid.addWidget(self.tasks_t, 0, 0)
        self.info_l = QLabel("Tasks for observers: not available yet.")
        self.info_l.setStyleSheet("color: gray;")
        grid.addWidget(self.info_l, 1, 0)
        self.setLayout(grid)


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
    """Sky flats of a camera: age of the last evening/morning flats and science per filter, and of the last
    master zero / master dark (flat_overwatch, kept per telescope in ``flat_records``), and the flats log of
    this session."""

    def __init__(self, parent):
        super(CameraCalibration, self).__init__()
        self.parent = parent
        self.instrument = None
        self.mkUI()
        self.flat_records = {}      # {tel: {item: {filtr|"all": {"last": ISO|None}}}} z flat_overwatch

    def set_instrument(self, name):
        self.instrument = name

    def updateUI(self):
        if self.parent.telescope:
            self.draw_flat_log()
            self.draw_flat_table(self.parent.active_tel)
            self.draw_master_table(self.parent.active_tel)

    # kolory komorek EVENING / MORNING
    FLAT_FRESH = QtGui.QColor(182, 242, 182)    # flat swiezy
    FLAT_OLD = QtGui.QColor(255, 204, 128)      # flat stary
    FLAT_STALE = QtGui.QColor(255, 153, 153)    # filtr ostatnio uzywany, a swiezych flatow brak
    MASTER_OK = QtGui.QColor(220, 220, 220)     # master juz nie swiezy, ale jeszcze w limicie

    def update_flat_overwatch(self, tel, item, data):
        # item: flats_evening / flats_morning / science / zeros / darks; trzymamy per teleskop, zeby po zmianie
        # teleskopu nie mieszac danych, a rysujemy tylko aktywny (science jest w obu tabelach)
        self.flat_records.setdefault(tel, {})[item] = data
        if tel == self.parent.active_tel:
            self.draw_master_table(tel)
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
        filters = {f for item, rec in records.items() if item not in self.MASTERS for f in rec}
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

    # tabela nad flatami: ostatni master zero / dark z journala pipeline ofp (kanaly flat_overwatch zeros / darks,
    # klucz "all"; limit wieku toi.master_max_days) i ostatni obiekt w dowolnym filtrze (najnowszy z kanalu science)
    MASTERS = {"zeros": "MASTER ZERO", "darks": "MASTER DARK"}

    def draw_master_table(self, tel):
        records = self.flat_records.get(tel, {})
        cfg = self.parent.local_cfg["toi"]
        fresh_days = {"zeros": 0.5, "darks": 30, **(cfg.get("master_fresh_days") or {})}
        max_days = {"zeros": 1, "darks": 60, **(cfg.get("master_max_days") or {})}
        t0 = datetime.datetime.now(datetime.timezone.utc)
        font = QtGui.QFont()
        font.setPointSize(10)

        def utc(t):
            return datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc) if t else None

        science = [v.get("last") for v in records.get("science", {}).values() if v.get("last")]
        t_obj = utc(max(science)) if science else None
        for i, (item, name) in enumerate(self.MASTERS.items()):
            t = utc(records.get(item, {}).get("all", {}).get("last"))
            fresh = datetime.timedelta(days=fresh_days[item])
            limit = datetime.timedelta(days=max_days[item])
            self.master_t.setItem(i, 0, self._flat_cell(name, font))
            cell = self._flat_cell(self._age_txt(t0, t), font)
            # zielony - swiezy; szary - jeszcze dobry (zero z wieczora po polnocy, dark z drugiego miesiaca - robione,
            # gdy nie ma pogody); starszy niz limit (albo brak):
            # czerwony, gdy w tym czasie byl obiekt (obserwacje bez aktualnej kalibracji), pomaranczowy, gdy nie
            if t and t0 - t <= fresh:
                cell.setBackground(self.FLAT_FRESH)
            elif t and t0 - t <= limit:
                cell.setBackground(self.MASTER_OK)
            elif t_obj and t0 - t_obj <= limit:
                cell.setBackground(self.FLAT_STALE)
            else:
                cell.setBackground(self.FLAT_OLD)
            self.master_t.setItem(i, 1, cell)
        self.master_t.setItem(len(self.MASTERS), 0, self._flat_cell("OBJECT", font))
        self.master_t.setItem(len(self.MASTERS), 1, self._flat_cell(self._age_txt(t0, t_obj), font))
        self.master_t.resizeColumnsToContents()
        self.master_t.repaint()

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
        grid.addWidget(self.flat_table_t, 1, 0)

        self.master_t = QTableWidget(len(self.MASTERS) + 1, 2)       # + OBJECT
        self.master_t.setHorizontalHeaderLabels(["LAST", "AGE"])
        self.master_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.master_t.verticalHeader().hide()
        self.master_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.master_t.setStyleSheet("selection-background-color: white;")
        self.master_t.verticalHeader().setDefaultSectionSize(10)
        self.master_t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.master_t.setFixedHeight(self.master_t.horizontalHeader().sizeHint().height()
                                     + self.master_t.rowCount() * self.master_t.verticalHeader().defaultSectionSize() + 4)
        grid.addWidget(self.master_t, 0, 0)

        self.log_t = QTableWidget(0, 7)
        self.log_t.setHorizontalHeaderLabels(["DATE", "UT", "FILTER", "N", "EXP", "H_SUN", "ADU"])
        self.log_t.setShowGrid(False)
        self.log_t.verticalHeader().hide()
        self.log_t.verticalHeader().setDefaultSectionSize(10)
        self.log_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.log_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_t.horizontalHeader().setStretchLastSection(True)
        self.log_t.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.log_t, 0, 1, 2, 1)
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
    """Night plots of all telescopes; the combo chooses what is drawn. Filter/airmass cuts apply to FWHM.
    Drawn like oca_monitor: per-telescope points and a smoothed trend; refreshed by ``refresh_if_new``."""

    PLOTS = ["FWHM", "Zero point"]
    SMOOTH_SIGMA = 5            # punktow - filtr Gaussa po kolejnych punktach, jak oca_monitor
    MEDIAN_SIZE = 5             # punktow - mediana przed Gaussem: pojedynczy zly punkt (np. ZP -2.9) nie ciagnie linii
    MAX_GAP = 0.5 / 24          # d - przerwa dluzsza dzieli krzywa na odcinki
    MIN_SEGMENT = 4             # krotszych odcinkow nie wygladzamy, zostaja same punkty
    FILTER_EDGE = {"B": "blue", "V": "green", "Ic": "red", "u": "purple", "g": "teal", "r": "orangered",
                   "i": "darkred", "z": "black"}      # obwodka punktu zero pointu wg filtra, inne szare
    FWHM_TOP = (3.0, 6.0)       # arcsec - gora skali FWHM; wyzszy punkt tej nocy podnosi ja, najwyzej do drugiej
    ZP_RANGE = (-0.3, 0.08)     # mag - domyslna skala zero pointu; punkty tej nocy spoza niej ja poszerzaja,
    ZP_RANGE_MAX = (-0.6, 0.2)  # najwyzej do tych granic - dalsze punkty rysujemy na krawedzi jako trojkaty
    ZP_ZONES = (-0.1, -0.2)     # ostrzezenie / alarm, gdy weather_overwatch jeszcze nie przyslal progow

    def __init__(self, parent):
        super(ConditionsTab, self).__init__()
        self.parent = parent
        self.mkUI()
        self.drawn_count = None     # ile punktow bylo przy ostatnim rysowaniu

    def data_count(self):
        return sum(len(v) for v in self.parent.fits_ffs_data.values()) + \
               sum(len(v) for v in self.parent.fits_photo_z0_data.values())

    def refresh_if_new(self):
        # wolane co 30 s z TOI: rysujemy tylko, gdy ktos patrzy i przyszly nowe punkty (~50 ms na rysowanie)
        if self.isVisible() and self.data_count() != self.drawn_count:
            self.redraw()

    def redraw(self):
        plot = self.plot_s.currentText()
        self.filter_e.setEnabled(plot == "FWHM")
        self.airmass_e.setEnabled(plot == "FWHM")
        self.drawn_count = self.data_count()
        self.ax.clear()
        if self.parent.jd:
            try:
                if plot == "FWHM":
                    self.plot_fwhm()
                elif plot == "Zero point":
                    self.plot_zero_point()
            except Exception as e:      # zly punkt nie moze zostawic pustego wykresu bez sladu
                logger.warning(f'EXCEPTION conditions plot {plot}: {e!r}')
        self.fig.subplots_adjust(bottom=0.2, top=0.95, left=0.08, right=0.988)
        self.canvas.draw()

    def smoothed(self, x, y):
        """Odcinki (przerwa > MAX_GAP) wygladzone Gaussem; NaN miedzy odcinkami przerywa linie."""
        idx = numpy.argsort(x)
        x, y = numpy.asarray(x, dtype=float)[idx], numpy.asarray(y, dtype=float)[idx]
        cuts = numpy.where(numpy.diff(x) > self.MAX_GAP)[0] + 1
        out_x, out_y = [], []
        for sx, sy in zip(numpy.split(x, cuts), numpy.split(y, cuts)):
            if sx.size < self.MIN_SEGMENT:
                continue
            if out_x:
                out_x.append(numpy.nan)
                out_y.append(numpy.nan)
            out_x.extend(sx)
            out_y.extend(gaussian_filter1d(median_filter(sy, size=self.MEDIAN_SIZE, mode="nearest"), sigma=self.SMOOTH_SIGMA))
        return out_x, out_y

    def last_text(self, value, color, tel, filt, when):
        # ostatni pomiar w rogu: wartosc (kolor wg strefy) i skad jest - teleskop, filtr, czas UT
        self.ax.text(0.01, 0.95, f"last: {value}", transform=self.ax.transAxes, fontsize=15, fontweight="bold",
                     color=color, va="top")
        self.ax.text(0.01, 0.84, f"{tel} {filt} {str(when).split()[1][:5]} UT", transform=self.ax.transAxes,
                     fontsize=10, color="dimgray", va="top")

    def night_axis(self, x0, x1, ylabel):
        xtics = []
        t = ephem.Date(x0)
        while t < ephem.Date(x1):
            t = ephem.Date(t) + ephem.hour
            h = str(ephem.Date(t)).split()
            xtics.append(ephem.Date(h[0] + " " + h[1].split(":")[0] + ":00:00"))
        self.ax.set_xticks(xtics)
        self.ax.set_xticklabels([str(x).split()[1][:5] for x in xtics], rotation=45, minor=False)
        self.ax.set_xlim(x0, x1)
        self.ax.set_xlabel("UT")
        self.ax.set_ylabel(ylabel)

    def plot_fwhm(self):
        # tylko klatki science (bez kalibracji, testow, focusa), skala z naglowka - uwzglednia binning
        x0 = float(str(self.parent.jd).split(".")[0]) + 0.4
        x1 = x0 + 0.6
        filt = str(self.filter_e.text())
        try:
            max_airmass = float(self.airmass_e.text()) if self.airmass_e.text().strip() else None
        except ValueError:
            max_airmass = None
        top = self.FWHM_TOP[0]
        latest = None       # (jd, tel, filtr, fwhm) ostatniej klatki tej nocy
        for t, frames in self.parent.fits_ffs_data.items():
            color = self.parent.nats_cfg[t]['color']
            jd, fwhm, focus = [], [], []
            for x in frames:
                try:
                    h = x["raw"]["header"]
                    if h.get("OBSTYPE") == "focus" and h.get("LOOP") is not None and \
                            float(h["LOOP"]) == float(h.get("NLOOPS", -1)):
                        focus.append(float(h["JD"]))
                    if h.get("OBSTYPE") != "science" or filt not in str(h.get("FILTER", "")) or "fwhm" not in x["raw"]:
                        continue
                    if max_airmass is not None and float(h["AIRMASS"]) >= max_airmass:
                        continue
                    f = (float(x["raw"]["fwhm"]["fwhm_x"]) + float(x["raw"]["fwhm"]["fwhm_y"])) / 2.
                    f = f * float(h.get("SCALE") or self.parent.nats_cfg[t]["pixel_scale"])
                    if 0 < f < 10:
                        jd.append(float(h["JD"]))
                        fwhm.append(f)
                        if jd[-1] >= x0 and (latest is None or jd[-1] > latest[0]):
                            latest = (jd[-1], t, h.get("FILTER", ""), f)
                except (ValueError, TypeError, KeyError):
                    pass
            jd, fwhm = numpy.array(jd), numpy.array(fwhm)
            old = jd < x0       # poprzednia noc blado, przesunieta o dobe
            self.ax.scatter(jd[old] + 1, fwhm[old], marker=".", color=color, alpha=0.06)
            self.ax.scatter(jd[~old], fwhm[~old], marker="o", s=14, color=color, alpha=0.4, linewidths=0, label=t)
            if (~old).sum():
                sx, sy = self.smoothed(jd[~old], fwhm[~old])
                self.ax.plot(sx, sy, color=color, linewidth=2)
                top = min(max(top, 1.05 * fwhm[~old].max()), self.FWHM_TOP[1])
            for ft in focus:
                if ft > x0:
                    self.ax.axvline(x=ft, color=color, alpha=0.8, linewidth=0.8)
        self.night_axis(x0, x1, "FWHM [arcsec]")
        self.ax.set_ylim(0, top)
        if latest:
            self.last_text(f'{latest[3]:.2f}"', "black", latest[1], latest[2], ephem.Date(latest[0] - 2415020))
        self.ax.legend(loc="upper right", fontsize=8)

    def plot_zero_point(self):
        # fits_photo_z0_data: {tel: [{'filter', 'zero_value', 'oca_jd', 'mode'}, ...]}; jak oca_monitor: strefy w tle,
        # punkty teleskopow (obwodka - filtr), jedna wygladzona krzywa ze wszystkich teleskopow i jej ostatnia wartosc
        tim_ranges = self.parent.time_ranges()
        today = get_oca_jd(datetime_to_julian(tim_ranges['today']))
        yesterday = get_oca_jd(datetime_to_julian(tim_ranges['yesterday']))
        warning, alert = self.ZP_ZONES
        limits = (getattr(self.parent, "conditions", {}).get("zero_point") or {}).get("limits") or {}
        if limits:
            x = next(iter(limits.values()))
            warning, alert = float(x.get("warning", warning)), float(x.get("alert", alert))
        self.ax.axhspan(warning, 1, color="green", alpha=0.08, linewidth=0)
        self.ax.axhspan(alert, warning, color="gold", alpha=0.15, linewidth=0)
        self.ax.axhspan(-10, alert, color="red", alpha=0.12, linewidth=0)
        self.ax.axhline(y=0, color="black", linewidth=0.5)

        all_x, all_y = [], []
        latest = None       # (oca_jd, tel, filtr, wartosc) ostatniego punktu tej nocy
        for t, points in self.parent.fits_photo_z0_data.items():
            color = self.parent.nats_cfg[t]['color']
            seen, td, yd = set(), [], []
            for p in points:
                try:
                    key = (p["oca_jd"], p["filter"])        # zero_monitor potrafi wyslac punkt kilka razy
                    v = float(p["zero_value"])
                    if key in seen or not numpy.isfinite(v):
                        continue
                    seen.add(key)
                    row = (p["oca_jd"] - numpy.floor(p["oca_jd"]), v, self.FILTER_EDGE.get(p["filter"], "gray"))
                    if p["oca_jd"] >= today:
                        td.append(row)
                        if latest is None or p["oca_jd"] > latest[0]:
                            latest = (p["oca_jd"], t, p["filter"], v)
                    elif p["oca_jd"] >= yesterday:
                        yd.append(row)
                except (ValueError, TypeError, KeyError):
                    pass
            for rows, alpha, label in ((yd, 0.1, None), (td, 0.6, t)):
                if rows:
                    x, y, edge = zip(*rows)
                    self.ax.scatter(x, y, c=color, edgecolors=edge, linewidths=1, s=22, alpha=alpha, label=label)
            all_x += [r[0] for r in td]
            all_y += [r[1] for r in td]

        if all_x:
            sx, sy = self.smoothed(all_x, all_y)
            self.ax.plot(sx, sy, color="#333333", linewidth=2)
        if latest:
            v = latest[3]
            zone = "green" if v >= warning else "darkorange" if v >= alert else "red"
            self.last_text(f"{v:+.3f} mag", zone, latest[1], latest[2], ephem.Date(latest[0] + 2460000 - 2415020))
        self.night_axis(0.4, 0.99, "zero point [mag]")
        bottom, top = self.ZP_RANGE
        lo, hi = self.ZP_RANGE_MAX
        if all_y:
            bottom = max(min(bottom, min(all_y) - 0.02), lo)
            top = min(max(top, max(all_y) + 0.02), hi)
            for x, y in zip(all_x, all_y):      # poza skala: trojkat na krawedzi zamiast rozciagania skali
                if y < bottom or y > top:
                    self.ax.scatter([x], [bottom if y < bottom else top], marker="v" if y < bottom else "^",
                                    s=40, color="black", clip_on=False, zorder=5)
        self.ax.set_ylim(bottom, top)
        if all_x:
            self.ax.legend(loc="upper right", fontsize=8)

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

