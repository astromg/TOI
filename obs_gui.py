#!/usr/bin/env python3

import datetime
import logging
import os.path
import time
import qasync as qs
from PyQtX import QtCore, QtGui
from PyQtX.QtCore import Qt, QSettings, QTimer
from PyQtX.QtWidgets import QMainWindow, QWidget, QLabel, QTextEdit, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, QCheckBox, \
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox, QMenu, QDockWidget, QApplication, QScrollArea
from pyaraucaria.coordinates import *
from qasync import QEventLoop

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from base_window import BaseWindow
from claude_report import write_claude_report
from toi_lib import *
from toi_theme import theme, TITLES
from events_gui import describe, when_text
from plan_gui import PLAN_LOG_LINES_CHOICES, plan_log_lines, set_plan_log_lines
from fits_gui import FITS_DISPLAY_MODES, fits_display_mode, FITS_CMAPS, fits_cmap, FITS_SCALES, fits_scale, \
    fits_show_trails, \
    fits_show_star_shapes, fits_show_saturated, fits_show_pattern

logger = logging.getLogger(__name__)


class HoldMarker(QLabel):
    """Kropka karencji ograniczenia pogodowego (conditions_overwatch) przy prawej krawedzi pola: kolor poziomu
    oficjalnego i minuty do jego spadku. Nakladka na pole - uklad siatki sie nie zmienia, tekst pola odsuwa sie w lewo"""

    def __init__(self, field):
        super().__init__(field)
        self.field = field
        field.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.field and event.type() == QtCore.QEvent.Type.Resize:
            self.place()
        return False

    def place(self):
        self.adjustSize()
        self.move(self.field.width() - self.width() - 4, (self.field.height() - self.height()) // 2)

    def show_hold(self, color, minutes, tip):
        self.setStyleSheet(f"background: transparent; color: {theme.c('field_fg')};")
        self.setText(f'<span style="color: {color}; font-size: 13pt;">&#9679;</span>{minutes}\'')
        self.setToolTip(tip)
        self.place()
        self.field.setTextMargins(0, 0, self.width() + 4, 0)
        self.show()
        self.raise_()

    def clear(self):
        if self.isVisible():
            self.hide()
            self.field.setTextMargins(0, 0, 0, 0)


class FitScrollArea(QScrollArea):
    """Obszar przewijania panelu. `fit` (duzy ekran): minimum = minimum zawartosci, sledzone na biezaco - okna
    przebudowuja sie przy zmianie teleskopu (np. Instrument dostaje zakladki BESO/ANDOR), wiec stale minimum ustawione
    przy budowie ukladu by je przycinalo. Bez `fit` (maly ekran) panel moze byc mniejszy i przewija."""

    def __init__(self, widget):
        super().__init__()
        self.fit = True
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.widget() and event.type() == QtCore.QEvent.Type.LayoutRequest:
            self.updateGeometry()       # zawartosc zmienila uklad - niech dok przeliczy rozmiary
        return super().eventFilter(obj, event)

    def minimumSizeHint(self):
        if self.fit and self.widget() is not None:
            return self.widget().minimumSizeHint()
        return super().minimumSizeHint()


class ObsGui(QMainWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    def __init__(self, parent, loop: QEventLoop = None, client_api=None):
        QMainWindow.__init__(self)
        BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)
        self.parent = parent
        self._geometry = None
        self._panel_tel = None      # teleskop na paskach tytulowych paneli
        theme.apply_palette()       # motyw zapamietany w QSettings
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
        log_lines = menu.addMenu("Plan log lines")      # ile ostatnich linii logu na gorze okna planu
        group_lines = QtGui.QActionGroup(log_lines)
        for n in PLAN_LOG_LINES_CHOICES:
            action = log_lines.addAction(str(n), lambda _=False, n=n: set_plan_log_lines(n, self.parent.planGui))
            action.setCheckable(True)
            action.setChecked(n == plan_log_lines())
            group_lines.addAction(action)
        fits_menu = menu.addMenu("FITS display")      # pelna rozdzielczosc albo zbinowany podglad (szybszy)
        group_fits = QtGui.QActionGroup(fits_menu)
        for mode, title in FITS_DISPLAY_MODES.items():
            action = fits_menu.addAction(title, lambda _=False, mode=mode: self.parent.fitsGui.set_display_mode(mode))
            action.setCheckable(True)
            action.setChecked(mode == fits_display_mode())
            group_fits.addAction(action)
        fits_menu.addSeparator()
        trails = fits_menu.addAction("Show satellite trails")       # linie z FFS na obrazie (ostrzezenie zostaje)
        trails.setCheckable(True)
        trails.setChecked(fits_show_trails(self.parent.local_cfg["toi"].get("show_trails", True)))
        trails.toggled.connect(lambda on: self.parent.fitsGui.set_show_trails(on))     # toggled podaje stan
        pattern = fits_menu.addAction("Show PSF pattern")    # kreseczki wzoru katow gwiazd i jego srodek
        pattern.setCheckable(True)
        pattern.setChecked(fits_show_pattern())
        pattern.toggled.connect(lambda on: self.parent.fitsGui.set_show_pattern(on))
        shapes = fits_menu.addAction("Show star shapes")    # markery shape: za duzy / za maly (licznik w panelu zostaje)
        shapes.setCheckable(True)
        shapes.setChecked(fits_show_star_shapes())
        shapes.toggled.connect(lambda on: self.parent.fitsGui.set_show_star_shapes(on))
        saturated = fits_menu.addAction("Show saturated stars")    # czerwone kolka gwiazd nasyconych
        saturated.setCheckable(True)
        saturated.setChecked(fits_show_saturated(self.parent.local_cfg["toi"].get("show_sat_stars", True)))
        saturated.toggled.connect(lambda on: self.parent.fitsGui.set_show_saturated(on))
        cmap_menu = menu.addMenu("FITS colormap")      # mapa kolorow obrazu FITS
        group_cmap = QtGui.QActionGroup(cmap_menu)
        for name, (title, *_) in FITS_CMAPS.items():
            action = cmap_menu.addAction(title, lambda _=False, name=name: self.parent.fitsGui.set_cmap(name))
            action.setCheckable(True)
            action.setChecked(name == fits_cmap())
            group_cmap.addAction(action)
        scale_menu = menu.addMenu("FITS scale")        # kontrast obrazu FITS
        group_scale = QtGui.QActionGroup(scale_menu)
        for name, title in FITS_SCALES.items():
            action = scale_menu.addAction(title, lambda _=False, name=name: self.parent.fitsGui.set_scale(name))
            action.setCheckable(True)
            action.setChecked(name == fits_scale())
            group_scale.addAction(action)
        themes = menu.addMenu("Theme")
        group = QtGui.QActionGroup(themes)
        for name in TITLES:         # kolejnosc w menu: jasne, potem ciemne
            action = themes.addAction(TITLES[name], lambda _=False, name=name: theme.set(name))
            action.setCheckable(True)
            action.setChecked(name == theme.name)
            group.addAction(action)
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
        QMainWindow::separator { background: SEP; width: 5px; height: 5px; }
        QMainWindow::separator:hover { background: SEP_HOVER; }
        QDockWidget::title { background: TITLE_BG; color: TITLE_FG; padding: 3px 6px; }
    """
    # linie podzialu paneli w motywach: (zwykla, pod kursorem)
    PANEL_SEPARATORS = {"day": ("rgb(150, 150, 150)", "rgb(100, 100, 100)"),
                        "night": ("rgb(70, 70, 75)", "rgb(110, 110, 115)")}

    def panel_style(self, tel):
        """paski tytulowe paneli w kolorze teleskopu (z configu TIC). Dzien: pol na pol z biela (ciemne kolory jak
        zb08 #0082E8 nie zaglusza czarnego tekstu), noc: pol na pol z tlem okna - intensywny, ale ciemny. Inne
        ciemne motywy jak noc, jasne (paper, clear sky) jak dzien. Tekst czarny albo jasny wg jasnosci paska"""
        color = QtGui.QColor((self.parent.nats_cfg.get(tel, {}) if tel else {}).get("color") or "#cdd2dc")
        base = QtGui.QColor(255, 255, 255) if theme.light else theme.qcolor("window")
        mix = 0.5
        tint = QtGui.QColor(*(int(c * (1 - mix) + b * mix) for c, b in
                              ((color.red(), base.red()), (color.green(), base.green()), (color.blue(), base.blue()))))
        sep, sep_hover = self.PANEL_SEPARATORS.get(theme.name) or (
            (theme.c("muted_fg"), theme.c("dim_fg")) if theme.light else (theme.c("field_bg"), theme.c("muted_fg")))
        return (self.PANEL_STYLE.replace("TITLE_BG", tint.name()).replace("TITLE_FG", theme.text_on(tint))
                .replace("SEP_HOVER", sep_hover).replace("SEP", sep))

    def set_panel_telescope(self, tel):
        # paski tytulowe paneli w kolorze aktywnego teleskopu i z jego nazwa
        self._panel_tel = tel
        self.setStyleSheet(self.panel_style(tel))
        for attr, title in self.PANELS:
            self.docks[attr].setWindowTitle(f"{title} \u00b7 {tel}")
        self.setWindowTitle(f"Telescope Operator Interface \u00b7 {tel}")

    def dock_panels(self):
        self._geometry = None       # rozmiar okna glownego ustawia uklad, nie obs_window_geometry
        self.setStyleSheet(self.panel_style(None))
        theme.on_change(lambda: self.setStyleSheet(self.panel_style(self._panel_tel)))
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks
                            | QMainWindow.DockOption.AllowNestedDocks)
        # prawa kolumna na cala wysokosc, Mount tylko pod oknem obserwacji
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        # formularz obserwacji tez w obszarze przewijania - na malym ekranie oddaje szerokosc panelom
        central = FitScrollArea(self.takeCentralWidget())
        self.setCentralWidget(central)
        self.areas = {"main_form": central}
        self.docks = {}
        for attr, title in self.PANELS:
            widget = getattr(self.parent, attr)
            widget._geometry = None     # BaseWindow nie ustawia juz pozycji
            dock = QDockWidget(title, self)
            dock.setObjectName(f"dock_{attr}")      # po tej nazwie saveState rozpoznaje panel
            # przewijanie zamiast wypychania okna poza ekran, gdy panel dostanie mniej niz minimum zawartosci
            area = FitScrollArea(widget)
            dock.setWidget(area)
            self.areas[attr] = area
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
        # przewijanie tylko na malym ekranie: gdy uklad sie miesci, panel nie moze byc mniejszy niz jego zawartosc
        for area in self.areas.values():
            area.fit = not steps
            area.updateGeometry()
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
        self.ask_quit()

    def ask_quit(self):
        """pytanie "Close TOI?" - krzyzyk tego okna i przycisk EXIT w oknie Sky"""
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
    # kolumny tabeli teleskopow
    COLUMNS = ["Telescope", "Dome", "Mirror", "Mount", "Instrument", "Program"]

    def __init__(self, parent):
        super(MainForm, self).__init__()
        self.parent = parent
        self.setStyleSheet("font-size: 11pt;")
        self._cells = {}            # (wiersz, kolumna) -> ostatnio pokazana zawartosc; rysujemy tylko zmiany
        self._pixmaps = {}          # (ikonka, kolor) -> QPixmap
        self._switching = False     # trwa przelaczanie teleskopu
        self._wanted_row = None     # wiersz klikniety w trakcie przelaczania - po nim przelaczamy jeszcze raz
        self.rows = []              # teleskopy w wierszach tabeli (toi_config.yaml)

        self.mkUI()
        self.obs_t.itemSelectionChanged.connect(self.pocisniecie_tab)
        theme.on_change(self.apply_theme)

    @qs.asyncSlot()
    async def pocisniecie_tab(self):
        # klikniecia w trakcie przelaczania nie odpalaja drugiego przelaczania naraz (zatrzymywanie i start
        # subskrypcji by sie przeplataly) - zapamietujemy ostatni wiersz i przelaczamy na niego po skonczeniu
        row = self.obs_t.currentRow()
        if row < 0:
            return
        self._wanted_row = row
        if self._switching:
            return
        self._switching = True
        try:
            while self._wanted_row is not None:
                i, self._wanted_row = self._wanted_row, None
                if i >= len(self.rows) or (self.rows[i] == self.parent.active_tel and self.parent.telescope is not None):
                    continue
                # numer teleskopu w toi_config.yaml (telescope_switched go uzywa), nie numer wiersza
                tel = self.rows[i]
                self.parent.active_tel_i = self.parent.local_cfg["toi"]["telescopes"].index(tel)
                self.parent.active_tel = tel
                await self.parent.telescope_switched()
        finally:
            self._switching = False

    def pixmap(self, name, color_key):
        key = (name, theme.c(color_key))
        if key not in self._pixmaps:
            self._pixmaps[key] = ToiIcon(name, theme.qcolor(color_key), size=14).pixmap(14, 14)
        return self._pixmaps[key]

    # kolory tabeli: dawne (klucze tab_* w toi_theme) - inny kod niz reszta TOI (ruch pomaranczowy, nie niebieski);
    # rozbieznosc znana, na razie zostaje

    def update_table(self):
        # wolane z czytnikow NATS: wyjatek nie moze z nich wyjsc (konczy czytnik na stale), a blad jednego
        # teleskopu nie moze zatrzymac reszty tabeli
        try:
            tels = list(self.parent.local_cfg["toi"]["telescopes"])
            if tels != self.rows:
                self.rows = tels
                self.obs_t.setRowCount(len(tels))
                self._cells.clear()
                self.fit_table_height()
        except Exception as e:
            logger.exception(f'TOI: telescope table: {e}')
            return
        for i, t in enumerate(tels):
            for col, f in enumerate((self.tel_cell, self.dome_cell, self.mirror_cell, self.mount_cell,
                                     self.instrument_cell, self.program_cell)):
                try:
                    content = f(t)
                except Exception as e:
                    logger.warning(f'TOI: telescope table {t} {self.COLUMNS[col]}: {e!r}')
                    content = ("text", "?", "tab_error")
                self.set_cell(i, col, content)

    def fit_table_height(self):
        # tabela: teleskopy + 2 puste wiersze; reszte wysokosci bierze log (setRowStretch w mkUI)
        t = self.obs_t
        t.setFixedHeight(t.horizontalHeader().sizeHint().height()
                         + t.verticalHeader().defaultSectionSize() * (t.rowCount() + 2) + 2 * t.frameWidth())

    LAMP_BEAT = 300     # ms - tyle trwa mrugniecie lampki

    def set_lamp(self, lamp, color_key):
        """kolor lampki wg klucza toi_theme; klucz zapamietany, zeby apply_theme przemalowal ja od razu"""
        lamp.lamp_color = color_key
        lamp.setStyleSheet(f"color: {theme.c(color_key)};")

    def beat(self, lamp):
        """jedno mrugniecie lampki: na chwile jasniejsza zielen - serwis wlasnie odpowiedzial"""
        flash = f"color: {theme.c('ok_beat_fg')};"
        base = lamp.styleSheet()
        if base == flash:
            return
        lamp.setStyleSheet(flash)

        def back():
            if lamp.styleSheet() == flash:      # petla lampki w tym czasie mogla ustawic nowy stan - zostawiamy go
                lamp.setStyleSheet(base)
        QTimer.singleShot(self.LAMP_BEAT, back)

    def set_cell(self, i, col, content):
        if self._cells.get((i, col)) == content:
            return
        self._cells[(i, col)] = content
        if content[0] == "icons":
            self.obs_t.setCellWidget(i, col, self.icons_widget(content[1]))
            return
        _, txt, color_key = content
        item = self.obs_t.item(i, col)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.obs_t.setItem(i, col, item)
        item.setText(txt)
        item.setForeground(QtGui.QBrush(theme.qcolor(color_key)))

    def icons_widget(self, parts):
        icons = QWidget()
        lay = QHBoxLayout(icons)
        lay.setContentsMargins(1, 0, 1, 0)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for part in parts:
            label = QLabel()
            if part[0] == "name":
                label.setText(part[1])
            else:
                _, name, color_key, tip = part
                label.setPixmap(self.pixmap(name, color_key))
                label.setToolTip(tip)
            lay.addWidget(label)
        return icons

    # ---- zawartosc komorek: ("text", tekst, klucz koloru) albo ("icons", krotka ikonek)

    def tel_cell(self, t):
        p = self.parent
        parts = []
        if p.tel_acces.get(t):
            parts.append(("icon", "icon_joystick", "tab_icon_ok", "You have control of this telescope"))
        parts.append(("name", t))
        if p.safety_cutoff.get(t):
            parts.append(("icon", "icon_hat", "tab_icon_bad", "safety cutoff ON"))

        progress = p.ob_progress.get(t) or {}
        if progress.get("error"):
            parts.append(("icon", "icon_bug", "tab_icon_bad", "Program error"))

        op = p.nats_toi_op_status.get(t)
        if op:      # stan zapisany przez TOI (toi.status)
            def changed(k):
                v = op.get(k) or {}
                return v.get("state") != v.get("defoult")
            mirror = p.mirror_fans_on(t)        # z TIC; bez swiezej wiadomosci - stan zapisany przez TOI
            if mirror is None:
                mirror = changed("mirror_fans")
            if changed("dome_ventilators") or mirror:
                parts.append(("icon", "icon_fan", "tab_icon_warn", "Dome ventilators or mirror fans on"))
            if changed("flat_lamps") or changed("dome_lights"):
                parts.append(("icon", "icon_bulb", "tab_icon_warn", "Flat lamps or dome lights on"))

        # pogoda: stacja Davis wspolna, ale limity wiatru sa per teleskop; nie zalezy od toi.status
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        wind = _f(p.telemetry_wind)
        humidity = _f(p.telemetry_humidity)
        temperature = _f(p.telemetry_temp)
        rain = _f(p.telemetry_rain)
        wind_limit, wind_limit_pointing = p.wind_limits(t)
        if wind is not None and wind > wind_limit:
            parts.append(("icon", "icon_wind", "tab_icon_bad", f"Wind above the closing limit ({wind_limit:g} m/s)"))
        elif wind is not None and wind > wind_limit_pointing:
            parts.append(("icon", "icon_wind", "tab_icon_warn2", f"Wind above the pointing limit ({wind_limit_pointing:g} m/s)"))
        if rain is not None and rain > 0:
            parts.append(("icon", "icon_rain", "tab_icon_bad", "Rain"))
        if humidity is not None and humidity > float(p.cfg_humidity_limit):
            parts.append(("icon", "icon_water", "tab_icon_bad", f"Humidity above {p.cfg_humidity_limit} %"))
        if temperature is not None and temperature < float(p.cfg_temperature_limit):
            parts.append(("icon", "icon_cold", "tab_icon_bad", f"Temperature below {p.cfg_temperature_limit} C"))

        # allsky_overwatch: teleskop obserwuje w polu zaznaczonym na zolto (pomaranczowa chmura) / czerwono
        clouds = p.clouds_at(t)
        if clouds:
            parts.append(("icon", "icon_cloud", "tab_icon_bad" if clouds == "red" else "tab_icon_warn2",
                          "pointing into thick clouds" if clouds == "red" else "pointing into clouds"))
        return ("icons", tuple(parts))

    def dome_cell(self, t):
        st = self.parent.oca_tel_state[t]
        shutter = st["dome_shutterstatus"]["val"]
        moving = st["dome_slewing"]["val"]
        state, color = "--", "idle_fg"
        if shutter is not None or moving is not None:
            if shutter is None and moving is None: state, color = "SHUTTER and STATUS ERROR", "tab_error"
            elif shutter is None: state, color = "SHUTTER ERROR", "tab_error"
            elif moving is None: state, color = "DOME STATUS ERROR", "tab_error"
            elif moving: state, color = "MOVING", "tab_moving"
            elif shutter == 0: state, color = "OPEN", "tab_ok"
            elif shutter == 1: state, color = "CLOSED", "idle_fg"
            elif shutter == 2: state, color = "OPENING", "tab_moving"
            elif shutter == 3: state, color = "CLOSING", "tab_moving"
            else: state, color = "SHUTTER ERROR", "tab_error"
        if self.parent.dome_follow_all.get(t):      # dome follower wlaczony (TOI.dome_follow_table_loop)
            state = "FOLLOW" if state == "--" else f"{state} & FLW"
        return ("text", state, color)

    def mirror_cell(self, t):
        status = self.parent.oca_tel_state[t]["mirror_status"]["val"]
        if status is None: return ("text", "NO IDEA", "idle_fg")
        if status == 3: return ("text", "OPEN", "tab_ok")
        if status == 1: return ("text", "CLOSED", "idle_fg")
        if status == 2: return ("text", "MOVING", "tab_moving")
        return ("text", "ERROR", "tab_error")

    def mount_cell(self, t):
        st = self.parent.oca_tel_state[t]
        slewing = st["mount_slewing"]["val"]
        tracking = st["mount_tracking"]["val"]
        motors = st["mount_motor"]["val"]
        if slewing is None and tracking is None: return ("text", "--", "idle_fg")
        if motors == "false": return ("text", "MOTORS OFF", "idle_fg")
        if slewing: return ("text", "SLEWING", "tab_moving")
        if tracking: return ("text", "TRACKING", "tab_ok")
        return ("text", "IDLE", "idle_fg")

    def instrument_cell(self, t):
        st = self.parent.oca_tel_state[t]
        pos = st["fw_position"]["val"]
        ccd = st["ccd_state"]["val"]
        filtr = "--"
        names = (self.parent.nats_cfg.get(t) or {}).get("filter_list_names") or []
        if pos is not None:
            try:
                filtr = names[int(pos)]
            except (IndexError, TypeError, ValueError):
                filtr = f"#{pos}"       # pozycja spoza listy filtrow
        if ccd is None: return ("text", "--", "idle_fg")
        if ccd == 2: return ("text", f"EXP [{filtr}]", "tab_ok")
        if ccd == 0: return ("text", f"IDLE [{filtr}]", "idle_fg")
        return ("text", f"NO IDEA [{filtr}]", "idle_fg")

    def program_cell(self, t):
        progress = self.parent.ob_progress.get(t) or {}
        state, color = "--", "idle_fg"
        program = str(progress.get("ob_program") or "")
        words = program.split()
        if progress.get("ob_started") and not progress.get("ob_done") and words:
            if "OBJECT" in program and len(words) > 1:
                state, color = words[1], "tab_ok"
            elif len(words) > 1:
                state, color = f"{words[0]} {words[1]}", "tab_ok"
            else:
                state, color = words[0], "idle_fg"
        if progress.get("error"):
            state, color = f"ERROR {state}", "tab_error"
        return ("text", state, color)

    def apply_theme(self):
        # pola przemalowuja ich petle (almanac co 1 s, pogoda, lampki), tu tylko to, co inaczej zostaloby stare
        for lamp in self.lamps:
            self.set_lamp(lamp, lamp.lamp_color)
        for field in self.plain_fields + (self.temp_e, self.hummidity_e, self.wind_e, self.windDir_e,
                                          self.fwhm_e, self.zeropoint_e, self.clouds_e):
            field.setStyleSheet(theme.field_style())
        try:        # pola pogody od razu w kolorach nowego motywu, nie dopiero przy nastepnej wiadomosci
            self.parent.updateWeather()
        except Exception as e:
            logger.warning(f'TOI: theme weather fields: {e}')
        self.msg_e.setStyleSheet(theme.field_style())
        self.obs_t.setStyleSheet(f"font-size: 9pt; selection-background-color: {theme.c('selection_bg')};")
        self._cells.clear()
        self.update_table()

    def report(self):
        self.report_window = ReportWindow(self.parent)
        self.report_window.show()

    # =================== OKNO GLOWNE ====================================
    def set_hints(self):
        # okienka z wyjasnieniem po najechaniu na pole; Wind/Direction dopisuja limity w TOI.wind_field_style
        hints = {
            "ticStatus2": "TIC server, checked every 4 s.",
            "natsStatus": "TOI connection to NATS, checked every 4 s. Orange: reconnecting.",
            "followerStatus": "Dome follower of the active telescope: heartbeat every 10 s, checked every 4 s. Red: none for 30 s.",
            "downloaderStatus": "OFP downloader of the active telescope, asked every 4 s (alive RPC).",
            "ofpStatus": "OFP pipeline of the active telescope, asked every 4 s (alive RPC).",
            "flatOwStatus": "flat_overwatch, asked every 4 s (alive RPC). Grey: no subject in toi_config.yaml.",
            "conditionsOwStatus": "conditions_overwatch (weather, sky, system and water alarms, events), asked every 4 s "
                                  "(alive RPC). Grey: no subject in toi_config.yaml.",
            "allskyOwStatus": "allsky_overwatch (clouds from the allsky camera), asked every 4 s (alive RPC). Grey: no subject in toi_config.yaml.",
            "temp": "Davis weather station. Red below -1 °C.",
            "hummidity": f"Davis weather station. Red above {self.parent.cfg_humidity_limit} % or rain.",
            "wind": "Davis weather station.",
            "windDir": "Davis weather station.",
            "fwhm": "Seeing at zenith from conditions_overwatch.",
            "zeropoint": "Photometric zero point from conditions_overwatch.",
            "clouds": "Clouds from the allsky camera (allsky_overwatch).",
            "date": "UT date.",
            "ut": "Universal Time.",
            "sun": "Sun altitude. Yellow: above 0°. Blue: twilight, 0° to -18°.",
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
        # serwisy aktywnego teleskopu; szare, dopoki nic o nich nie wiemy
        # krotkie nazwy, zeby caly wiersz sie miescil - pelne w podpowiedziach
        self.followerStatus_l = QLabel("\u2665 DOME FLW")
        self.downloaderStatus_l = QLabel("\u2665 FITS DWL")
        self.ofpStatus_l = QLabel("\u2665 OFP")
        self.flatOwStatus_l = QLabel("\u2665 FLAT OW")
        self.conditionsOwStatus_l = QLabel("\u2665 COND OW")
        self.allskyOwStatus_l = QLabel("\u2665 ALLSKY OW")
        self.ticStatus2_l.setText("\u2665 TIC")
        self.natsStatus_l.setText("\u2665 NATS")
        status_box = QHBoxLayout()
        status_box.setSpacing(12)
        lamps = (self.ticStatus2_l, self.natsStatus_l, self.followerStatus_l, self.downloaderStatus_l,
                 self.ofpStatus_l, self.flatOwStatus_l, self.conditionsOwStatus_l, self.allskyOwStatus_l)
        self.lamps = lamps
        for lamp in lamps:
            status_box.addWidget(lamp)
        self.set_lamp(self.ticStatus2_l, "idle_fg")
        self.set_lamp(self.natsStatus_l, "bad_fg")
        for lamp in lamps[2:]:
            self.set_lamp(lamp, "muted_fg")

        status_box.addStretch(1)
        grid.addLayout(status_box, w, 0, 1, 8)

        w = w + 1
        self.date_l = QLabel("Date:")
        self.date_l.setAlignment(Qt.AlignCenter)
        self.date_e = QLineEdit("--/--/--")
        self.date_e.setAlignment(Qt.AlignCenter)
        self.date_e.setReadOnly(True)
        self.date_e.setStyleSheet(theme.field_style())

        self.ut_l = QLabel("UT:")
        self.ut_l.setAlignment(Qt.AlignCenter)
        self.ut_e = QLineEdit("--:--:--")
        self.ut_e.setReadOnly(True)
        self.ut_e.setAlignment(Qt.AlignCenter)
        self.ut_e.setStyleSheet(theme.field_style())

        self.wind_l = QLabel("Wind:")
        self.wind_l.setAlignment(Qt.AlignCenter)
        self.wind_e = QLineEdit()
        self.wind_e.setAlignment(Qt.AlignCenter)
        self.wind_e.setReadOnly(True)
        self.wind_e.setStyleSheet(theme.field_style())

        self.windDir_l = QLabel("Direction:")
        self.windDir_l.setAlignment(Qt.AlignCenter)
        self.windDir_e = QLineEdit()
        self.windDir_e.setAlignment(Qt.AlignCenter)
        self.windDir_e.setReadOnly(True)
        self.windDir_e.setStyleSheet(theme.field_style())


        self.ojd_l = QLabel("JD:")
        self.ojd_l.setAlignment(Qt.AlignCenter)
        self.ojd_e = QLineEdit("--")
        self.ojd_e.setAlignment(Qt.AlignCenter)
        self.ojd_e.setReadOnly(True)
        self.ojd_e.setStyleSheet(theme.field_style())

        self.sid_l = QLabel("SID:")
        self.sid_l.setAlignment(Qt.AlignCenter)
        self.sid_e = QLineEdit("--:--:--")
        self.sid_e.setAlignment(Qt.AlignCenter)
        self.sid_e.setReadOnly(True)
        self.sid_e.setStyleSheet(theme.field_style())

        self.temp_l = QLabel("Temp:")
        self.temp_l.setAlignment(Qt.AlignCenter)
        self.temp_e = QLineEdit()
        self.temp_e.setAlignment(Qt.AlignCenter)
        self.temp_e.setReadOnly(True)
        self.temp_e.setStyleSheet(theme.field_style())

        self.hummidity_l = QLabel("Humidity:")
        self.hummidity_l.setAlignment(Qt.AlignCenter)
        self.hummidity_e = QLineEdit()
        self.hummidity_e.setAlignment(Qt.AlignCenter)
        self.hummidity_e.setReadOnly(True)
        self.hummidity_e.setStyleSheet(theme.field_style())

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
        for col, (name, txt) in enumerate((("fwhm", "Seeing:"), ("zeropoint", "Zero point:"), ("clouds", "Clouds:"))):
            label = QLabel(txt)
            label.setAlignment(Qt.AlignCenter)
            field = QLineEdit("--")
            field.setAlignment(Qt.AlignCenter)
            field.setReadOnly(True)
            field.setStyleSheet(theme.field_style())
            setattr(self, f"{name}_l", label)
            setattr(self, f"{name}_e", field)
            grid.addWidget(label, w, 2 * col)
            grid.addWidget(field, w, 2 * col + 1)

        # kropki karencji ograniczen pogodowych (TOI.update_hold_markers)
        self.hold_markers = {name: HoldMarker(getattr(self, name))
                             for name in ("wind_e", "windDir_e", "hummidity_e", "temp_e", "clouds_e")}



        w = w + 1
        self.obs_t = QTableWidget(0, len(self.COLUMNS))      # wiersze ustawia update_table
        self.obs_t.setHorizontalHeaderLabels(self.COLUMNS)
        self.obs_t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.obs_t.setSelectionBehavior(QTableWidget.SelectRows)
        self.obs_t.setSelectionMode(QTableWidget.SingleSelection)
        self.obs_t.verticalHeader().hide()
        self.obs_t.setShowGrid(False)
        self.obs_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.obs_t.setStyleSheet(f"font-size: 9pt; selection-background-color: {theme.c('selection_bg')};")
        grid.addWidget(self.obs_t, w, 0, 1, 8)
        self.obs_t.setRowCount(len(self.parent.local_cfg["toi"]["telescopes"]))
        self.fit_table_height()





        self.report_p = QPushButton('REPORT')
        self.report_p.clicked.connect(self.report)
        self.ping_p = QPushButton('PING')
        self.ping_p.clicked.connect(self.parent.open_sound_test_window)     # PING i test pozostalych dzwiekow


        w = 7

        self.msg_e = QTextEdit()
        self.msg_e.setReadOnly(True)
        self.msg_e.setStyleSheet(theme.field_style())
        grid.addWidget(self.msg_e, w, 0, 6, 4)     # po prawej: czas, Slonce, (odstep), Event + licznik, wiadomosc eventu
        grid.setRowStretch(w + 5, 1)                # zapas wysokosci okna idzie do logu

        # czas obok logu, w miejscu po przyciskach okien - uklad jak dawniej na gorze
        grid.addWidget(self.date_l, w, 4)
        grid.addWidget(self.date_e, w, 5)
        grid.addWidget(self.ut_l, w, 6)
        grid.addWidget(self.ut_e, w, 7)
        grid.addWidget(self.ojd_l, w + 1, 4)
        grid.addWidget(self.ojd_e, w + 1, 5)
        grid.addWidget(self.sid_l, w + 1, 6)
        grid.addWidget(self.sid_e, w + 1, 7)
        # wysokosc Slonca pod Date/JD; tlo wg Slonca ustawia TOI.almanac_loop
        self.sun_l = QLabel("Sun:")
        self.sun_l.setAlignment(Qt.AlignCenter)
        self.sun_e = QLineEdit("--")
        self.sun_e.setAlignment(Qt.AlignCenter)
        self.sun_e.setReadOnly(True)
        self.sun_e.setStyleSheet(theme.field_style())
        grid.addWidget(self.sun_l, w + 2, 4)
        grid.addWidget(self.sun_e, w + 2, 5)
        # najblizszy event conditions_overwatch (zakladka Events): wiersz pod Sun pusty (odstep), nizej Event i licznik,
        # pod nimi wiadomosc na cala szerokosc (update_next_event, co sekunde); wiersz w + 5 ma zapas wysokosci (log) -
        # pole przy gornej krawedzi
        top = Qt.AlignmentFlag.AlignTop
        self.event_l = QLabel("Next Event:")
        self.event_l.setAlignment(Qt.AlignCenter)
        self.event_e = QLineEdit("--")
        self.event_e.setReadOnly(True)
        self.event_e.setStyleSheet(theme.field_style())
        self.countdown_e = QLineEdit("--")
        self.countdown_e.setAlignment(Qt.AlignCenter)
        self.countdown_e.setReadOnly(True)
        self.countdown_e.setStyleSheet(theme.field_style())
        grid.addWidget(self.event_l, w + 4, 4, 1, 2)        # dluzsza etykieta - dwie kolumny, nie poszerza Date/JD/Sun
        grid.addWidget(self.countdown_e, w + 4, 6, 1, 2)
        grid.addWidget(self.event_e, w + 5, 4, 1, 4, top)
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.update_next_event)
        self.event_timer.start(1000)

        w = w + 6

        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 0, 1, 8)

        self.set_hints()

        w = w + 1

        self.config_p = QPushButton("\u2699")


        # obserwatorzy tej nocy (tic.status.ocm.observers); klikniecie otwiera okno rejestracji do poprawki
        self.observers_p = QPushButton("Observers: --")
        self.observers_p.setToolTip("Observers tonight. Click to change.")
        self.observers_p.clicked.connect(self.parent.open_observers_window)

        grid.addWidget(self.report_p, w, 0)
        grid.addWidget(self.ping_p, w, 1)
        grid.addWidget(self.observers_p, w, 2, 1, 5)
        grid.addWidget(self.config_p, w, 7)


        # pola bez wlasnego kolorowania - przemalowuje je apply_theme
        self.plain_fields = (self.date_e, self.ut_e, self.ojd_e, self.sid_e)

        grid.setSpacing(5)

        self.setLayout(grid)

    EVENT_SOON = 5 * 60     # s - ponizej: tlo change_bg (niebieskie w kazdym motywie)

    def update_next_event(self):
        """Pole Event: najblizszy event z czasem (Slonce, ut, sec) z listy zakladki Events i odliczanie. Sekretne tylko
        w trybie admina - odliczanie zdradziloby niespodzianke. Zwykly slot (QTimer) - wyjatek nie moze wyjsc"""
        try:
            tab = self.parent.auxGui.events
            now, best = time.time(), None
            for ev in tab.all_rows:
                if ev.get("secret") and not tab.admin:
                    continue
                nxt = ev.get("next") or ""
                if "T" not in nxt:          # obserwatorzy: data albo "next", bez godziny
                    continue
                t = datetime.datetime.fromisoformat(nxt).timestamp()
                if t >= now - 60 and (best is None or t < best[0]):      # minuta po czasie - jeszcze pokazany
                    best = (t, ev)
            if best is None:
                text, count, soon, tip = "--", "--", False, "No timed event (Aux, Events tab)"
            else:
                t, ev = best
                s = max(0, int(t - now))
                text = f'{datetime.datetime.fromtimestamp(t, datetime.timezone.utc):%H:%M} UT  {ev.get("info", "")}'
                count = f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
                soon = t - now <= self.EVENT_SOON
                tip = f'{when_text(t)}\n{describe(ev)}\n{ev.get("info", "")}'
            self.event_e.setText(text)
            self.countdown_e.setText(count)
            style = theme.field_style("change_bg" if soon else "field_bg")
            for e in (self.event_e, self.countdown_e):
                if e.styleSheet() != style:
                    e.setStyleSheet(style)
                e.setToolTip(tip)
        except AttributeError:      # Aux jeszcze nie zbudowany
            pass
        except Exception as e:
            logger.warning(f'TOI update_next_event: {e!r}')

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)

# ############### FOCUS ##########################

class SoundTestWindow(QWidget):
    """PING and a test of every alarm sound of oca_monitor (pages/message.py LABEL_SOUNDS), opened by the PING
    button. PING is the original one (every TOI and overwatch answers). The others go out on the operator messages (toi_subjects "messages")
    with "test": true and a TEST text: they sound on every oca_monitor and show in every TOI, change no overwatch
    state (the overwatches react only to PING), and readers that count alarms (Halina, reports) should skip them.
    Not modal, like ObserversWindow."""

    # (label, sound, meaning) - the same labels and sounds as oca_monitor pages/message.py
    SOUNDS = (
        ("PROGRAM BELL", "bell", "BELL in a program (TOI)"),
        ("PROGRAM STOP", "stop", "STOP reached in a program (TOI)"),
        ("PROGRAM ERROR", "error", "error in a program (TOI)"),
        ("OBS NOTIFICATION", "notification", "check that everything is ok: seeing, zero point, thin clouds / veil, "
                                         "a telescope pointing into clouds"),
        ("WEATHER WARNING", "warning", "weather restrictions rise: pointing restricted or time to close a telescope"),
        ("WEATHER ALERT", "alert", "close everything: wind on all telescopes, humidity, temperature, rain, overcast"),
        ("WEATHER LEVEL DOWN", "level down", "a weather restriction dropped (after the hold time)"),
        ("SYSTEM ALERT", "facility alarm", "equipment at risk: battery SOC, server / battery / electric room temperature"),
        ("EVENT", "gong", "a time signal from conditions_overwatch (Sun +5 / -18, ut, ...; the Events tab), "
                          "may have its own sound"),
    )

    def __init__(self, parent):
        super(SoundTestWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle("PING and sound test")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        grid = QGridLayout(self)
        ping = QPushButton("PING")
        ping.clicked.connect(self.parent.ping)
        grid.addWidget(ping, 0, 0)
        grid.addWidget(QLabel("the original PING: every TOI and overwatch answers \"reporting in\""), 0, 1)
        note = QLabel("Test messages: \"test\": true and a TEST text. They sound on every oca_monitor and show in "
                      "every TOI, but change no overwatch state and should not be counted in reports.")
        note.setWordWrap(True)
        note.setStyleSheet("color: rgb(120, 120, 120);")
        grid.addWidget(note, 1, 0, 1, 2)
        for row, (label, sound, meaning) in enumerate(self.SOUNDS, start=2):
            button = QPushButton(f"{label}")
            button.setToolTip(f"sound: {sound}")
            button.clicked.connect(lambda _=False, l=label, m=meaning: self.parent.send_sound_test(l, m))
            grid.addWidget(button, row, 0)
            text = QLabel(f"{sound}: {meaning}")
            text.setWordWrap(True)
            grid.addWidget(text, row, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        grid.addWidget(close, len(self.SOUNDS) + 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(8)
        self.setMinimumWidth(640)


class ObserversWindow(QWidget):
    """Who observes tonight, for the whole observatory: the people from observers.yaml plus "Other".
    OK publishes the list on tic.status.ocm.observers (TOI.set_observers); every TOI shows it next to PING.
    "Only this TOI" keeps the choice in this session and publishes nothing (tests from elsewhere).
    Not modal - a modal dialog in qasync would stop all background tasks while it is open."""

    def __init__(self, parent):
        super(ObserversWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle("Observers tonight")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.mkUI()

    def open_for(self, current, local=False):
        # zaznaczeni obecni obserwatorzy - po starcie ci z ostatniego wpisu, czyli z poprzedniej nocy - na gorze
        # tabeli, reszta w kolejnosci z observers.yaml; spoza listy ida do pola Other
        known = set(self.parent.observers_list)
        # starsze wpisy z NATS maja polskie znaki ("Górski") - dopasowane do listy ASCII ("Gorski")
        current = [fits_ascii(n) if fits_ascii(n) in known else n for n in current]
        names = ([n for n in self.parent.observers_list if n in current]
                 + [n for n in self.parent.observers_list if n not in current])
        self.table.blockSignals(True)
        for row, name in enumerate(names):
            item = self.table.item(row, 0)
            item.setText(name)
            item.setCheckState(Qt.CheckState.Checked if name in current else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.table.scrollToTop()
        self.other_e.setText(", ".join(n for n in current if n not in known))
        self.local_c.setChecked(local)
        self.search_e.clear()
        self.count_changed()
        self.show()
        self.raise_()
        self.activateWindow()

    def chosen(self):
        names = [self.table.item(r, 0).text() for r in range(self.table.rowCount())
                 if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        return names + [n.strip() for n in self.other_e.text().split(",") if n.strip()]

    def accept(self):
        names = self.chosen()
        if not names:
            self.info_l.setText("Choose at least one observer.")
            return
        # nazwiska ida kiedys do naglowka FITS (OBSERVER) - tylko ASCII
        bad = [n for n in names if not is_fits_ascii(n)]
        if bad:
            self.info_l.setText(f"ASCII only (FITS headers): {', '.join(fits_ascii(n) for n in bad)}")
            return
        self.parent.set_observers(names, local=self.local_c.isChecked())
        self.hide()

    def filter_rows(self, text):
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, text.lower() not in self.table.item(row, 0).text().lower())

    def count_changed(self, *_):
        self.info_l.setText(f"Who observes tonight? Chosen: {len(self.chosen())}")

    def mkUI(self):
        grid = QGridLayout()
        w = 0
        self.info_l = QLabel("Who observes tonight?")
        grid.addWidget(self.info_l, w, 0, 1, 2)
        w = w + 1
        self.search_e = QLineEdit()
        self.search_e.setPlaceholderText("search")
        self.search_e.textChanged.connect(self.filter_rows)
        grid.addWidget(self.search_e, w, 0, 1, 2)
        w = w + 1
        # lista z observers.yaml w tabeli: kliknij pole przy nazwisku
        self.table = QTableWidget(len(self.parent.observers_list), 1)
        self.table.setHorizontalHeaderLabels(["Observer"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        for row, name in enumerate(self.parent.observers_list):
            item = QTableWidgetItem(name)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, item)
        self.table.itemChanged.connect(self.count_changed)
        grid.addWidget(self.table, w, 0, 1, 2)
        w = w + 1
        grid.addWidget(QLabel("Other:"), w, 0)
        self.other_e = QLineEdit()
        self.other_e.setPlaceholderText("names, comma separated")
        self.other_e.textChanged.connect(self.count_changed)
        grid.addWidget(self.other_e, w, 1)
        w = w + 1
        # np. testy z Warszawy: ustawiam siebie tylko w tym TOI, obserwatorzy w OCM dalej widza swoj wpis
        self.local_c = QCheckBox("Only this TOI (not shared with other stations)")
        self.local_c.setToolTip("For this session only, e.g. for tests from elsewhere: nothing is published, "
                                "the other TOIs keep their observers.")
        grid.addWidget(self.local_c, w, 0, 1, 2)
        w = w + 1
        # tryb admina zakladki Events: widac i mozna dodawac sekretne eventy (niespodzianki); tylko to stanowisko
        # i ta sesja, nic nie jest publikowane (inaczej sekrety odslonilyby sie na wszystkich TOI)
        self.admin_c = QCheckBox("Admin")
        self.admin_c.toggled.connect(self.parent.set_events_admin)
        grid.addWidget(self.admin_c, w, 0, 1, 2)
        w = w + 1
        # w przyszlosci tu tez zadania dla obserwatorow (zakladka Tasks)
        self.ok_p = QPushButton("OK")
        self.ok_p.clicked.connect(self.accept)
        self.later_p = QPushButton("Later")
        self.later_p.clicked.connect(self.parent.observers_later)
        grid.addWidget(self.later_p, w, 0)
        grid.addWidget(self.ok_p, w, 1)
        grid.setRowStretch(2, 1)
        self.setLayout(grid)
        self.resize(380, 520)


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
                   "instGui.ccd_tab.temp_set",
                   "instGui.ccd_tab.gain_names",
                   "instGui.ccd_tab.rm_names",
                   "ccd_temp_set",
                   "ccd_temp",
                   # filter wheel
                   "filter",
                   "filter_list",
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

