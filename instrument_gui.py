#!/usr/bin/env python3

import qasync as qs
from PyQtX.QtCore import Qt
from PyQtX.QtGui import QColor
from PyQtX.QtWidgets import QWidget, QLabel,QCheckBox, QRadioButton, QLineEdit, QTabWidget, QPushButton, QGridLayout, QComboBox, QProgressBar
from qasync import QEventLoop
from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget
from base_window import BaseWindow
from optics_gui import OpticsPanel

class InstrumentGui(BaseWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

      def __init__(self, parent, loop: QEventLoop = None, client_api=None):
          BaseWindow.__init__(self)
          BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)

          self.parent = parent
          self.setStyleSheet("font-size: 11pt;")
          self.set_initial_geometry(
              self.parent.instrument_geometry[0],
              self.parent.instrument_geometry[1],
              self.parent.instrument_geometry[2],
              self.parent.instrument_geometry[3]
          )
          self.updateUI()
          self.show()
          self.raise_()

      def updateUI(self):

          tmp = ""
          if self.parent.active_tel != None:
              tmp = self.parent.active_tel
          txt = tmp + " Instrument Manual Controll"
          self.setWindowTitle(txt)

          tmp=QWidget()
          try: tmp.setLayout(self.layout)
          except: pass

          self.layout = QGridLayout()
          self.setLayout(self.layout)

          self.tab=QTabWidget()

          # zakladka na kazdy instrument naukowy teleskopu z opublikowanej konfiguracji, klasa wg instrument_class
          components = {}
          if self.parent.active_tel != None:
              published = self.parent.observatory_model.get_telescopes_configuration().get(self.parent.active_tel, {})
              components = (published.get("observatory") or {}).get("components") or {}
          for name, spec in science_instruments(components):
              cls = instrument_class(name, spec)
              self.add_instrument(cls(self.parent, name, spec, loop=self.parent.loop, client_api=self.parent.client_api))

          # reszta TOI zna jedna kamere (ccd_tab) i jeden spektrograf (beso_tab) - pierwsze z listy; bez kamery
          # w konfiguracji i tak jest generyczna "camera", bo ccd_tab jest uzywane w wielu miejscach
          pages = [self.tab.widget(i) for i in range(self.tab.count())]
          cameras = [p for p in pages if p.calibration == "camera"]
          spectrographs = [p for p in pages if p.calibration == "spectrograph"]
          if not cameras:
              cameras = [GenericCamera(self.parent, "camera", {}, loop=self.parent.loop, client_api=self.parent.client_api)]
              self.add_instrument(cameras[0])
          self.ccd_tab = cameras[0]
          self.beso_tab = spectrographs[0] if spectrographs else None



          self.layout.addWidget(self.tab,0,0)
          # autofocus mierzy kamera: domyslnie pierwsza kamera teleskopu, nawet gdy otwarty jest spektrograf
          self.parent.auxGui.focus.set_camera(self.ccd_tab.name)
          self.tab.currentChanged.connect(self.instrument_changed)
          self.instrument_changed()

          del tmp
          self.parent.telescope_switch_status["instGui"] = True


      def instrument_changed(self):
          # zakladka Calibration w oknie aux idzie za wybranym tu instrumentem
          page = self.tab.currentWidget()
          self.parent.auxGui.set_instrument(page.calibration, page.name)

      def add_instrument(self, page):
          # tytul zakladki to dioda stanu i nazwa; dopoki nic nie wiemy - szary
          self.tab.addTab(page, f"\u25CF {page.name}")
          self.set_connected(page, "#bebebe")

      def set_connected(self, page, color):
          self.tab.tabBar().setTabTextColor(self.tab.indexOf(page), QColor(color))

      async def on_start_app(self):
          await self.run_background_tasks()

      @qs.asyncClose
      async def closeEvent(self, event):
          await self.stop_background_tasks()
          await self.stop_background_methods()
          super().closeEvent(event)


# ############### INSTRUMENTY ##########################
# Zakladka okna instrumentow na kazdy instrument naukowy teleskopu. Klasa wg konfiguracji (instrument_class):
# wlasna klasa instrumentu (Andor, BESO), a jak jej nie ma - generyczna dla rodzaju (kamera, kamera CMOS, spektrograf).

class InstrumentTab(BaseWindow, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    """One instrument of the telescope: ``detector`` is its component name, ``spec`` its published configuration."""
    calibration = None    # strona zakladki Calibration w aux_gui: "camera" / "spectrograph"

    def __init__(self, parent, detector, spec, loop: QEventLoop = None, client_api=None):
        BaseWindow.__init__(self)
        BaseAsyncWidget.__init__(self, loop=loop, client_api=client_api)

        self.parent = parent
        self.detector = detector
        self.spec = spec or {}
        self.name = self.title()
        self.load_settings()
        self.mkUI()

    def load_settings(self):
        # ustawienia instrumentu z jego konfiguracji (self.spec), przed mkUI
        pass

    def title(self):
        # nazwa na zakladce: display.label z konfiguracji albo nazwa komponentu
        return (self.spec.get("display") or {}).get("label") or self.detector.upper()

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        await self.stop_background_methods()
        super().closeEvent(event)


class GenericSpectrograph(InstrumentTab):
    calibration = "spectrograph"
    note = "No control from TOI yet"

    # =================== OKNO GLOWNE ====================================
    def mkUI(self):

        grid = QGridLayout()

        w = 0
        self.info1_l = QLabel(f"{self.name} spectrograph manual control")
        self.info1_l.setStyleSheet("""font-size: 22px;font-weight: bold;""")
        grid.addWidget(self.info1_l, w, 0)
        w = w + 1
        self.info2_l = QLabel(self.note)
        grid.addWidget(self.info2_l, w, 0)
        w = w + 1
        grid.setRowMinimumHeight(w, 12)  # air between the instrument's controls and its optical path
        w = w + 1
        self.optics_p = OpticsPanel(self.parent, self.parent.optics_model, self.detector)
        grid.addWidget(self.optics_p, w, 0)
        grid.setRowStretch(w + 1, 1)  # spare height below, the panel keeps its own

        self.setLayout(grid)


class BesoSpectrograph(GenericSpectrograph):
    note = "Let's be clear: No control here"

    def title(self):
        return "BESO"


def config_modes(modes, label):
    """``gain_modes`` / ``readout_modes`` of a camera's configuration → (names shown, ids to put, default name);
    the default is the mode with ``flags: ['default']``. Empty lists without the modes in the configuration."""
    if not modes:
        return [], [], None
    ids = sorted(modes.keys())
    names = [label(modes[i]) for i in ids]
    default = next((n for i, n in zip(ids, names) if 'default' in (modes[i].get('flags') or [])), None)
    return names, ids, default


class GenericCamera(InstrumentTab):
      calibration = "camera"
      show_binning = True             # binning i subraster w oknie
      temp_label = "CCD TEMP.:"
      obstypes = ["Science", "Zero", "Dark", "Sky Flat", "Dome Flat"]   # kolejnosc uzywana w plan_gui (indeksy)
      modes = ["Normal", "Sky", "JitterBox", "JitterRandom"]
      bins = ["1x1", "2x2", "1x2", "2x1"]                               # kolejnosc uzywana w TOI.ccd_setBin
      subraster = ["No", "Subraster1", "Subraster2", "Subraster3"]
      temp_limits = (-81, 20)          # deg C, dozwolone ustawienie, gdy konfiguracja nie ma temperature_range
      temp_warn = -58                  # deg C, cieplej = czerwono, gdy konfiguracja nie ma operation_temperature

      def load_settings(self):
          """Gain / read modes and temperatures from this camera's configuration (TIC publishes it)."""
          spec = self.spec
          self.gain_names, self.gain_ids, gain_default = config_modes(
              spec.get("gain_modes"), lambda m: f'{m.get("gain", "--")} ({m["name"]})')
          self.rm_names, self.rm_ids, rm_default = config_modes(spec.get("readout_modes"), lambda m: m["name"])
          self.temp_set = spec.get("operation_temperature")      # podpowiedz w polu SET
          rng = spec.get("temperature_range") or {}
          self.temp_limits = (rng.get("min", self.temp_limits[0]), rng.get("max", self.temp_limits[1]))
          temp_warn = self.temp_warn
          if self.temp_set is not None:
              # cieplej niz operation_temperature + gorna tolerancja = czerwono
              temp_warn = float(self.temp_set) + float((spec.get("temperature_tolerance") or [0, 0])[1])
          # wartosci domyslne: inna ustawiona w kamerze podswietla pole na zolto (None = bez podswietlania)
          self.defaults = {"gain": gain_default, "rm": rm_default, "bin": self.bins[0], "temp": temp_warn}

      def ObsTypeChanged(self):
          if self.inst_Obtype_s.currentIndex()==0:
              self.inst_object_e.setText("")
          elif self.inst_Obtype_s.currentIndex()==1:
              self.inst_object_e.setText("zero")
              self.inst_Dit_e.setText("0")
          elif self.inst_Obtype_s.currentIndex()==2:
              self.inst_object_e.setText("dark")
          elif self.inst_Obtype_s.currentIndex()==3:
              self.inst_object_e.setText("skyflat")
          elif self.inst_Obtype_s.currentIndex()==4:
              self.inst_object_e.setText("domeflat")
          else: pass                                  # nie ma Focusa bo nie da sie go zrobic w tym oknie

      def Select(self):
          if self.Select1_r.isChecked():
              self.inst_Seq_e.setText("")
              self.inst_Ndit_e.setStyleSheet("background-color: white; color: black;")
              self.inst_Dit_e.setStyleSheet("background-color: white; color: black;")
              self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          else:
              self.inst_Ndit_e.setText("")
              self.inst_Dit_e.setText("")
              self.inst_Ndit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
              self.inst_Dit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
              self.inst_Seq_e.setStyleSheet("background-color: white; color: black;")

      def Select1(self,tmp):
          self.Select1_r.setChecked(True)
          self.inst_Seq_e.setText("")
          self.inst_Ndit_e.setStyleSheet("background-color: white; color: black;")
          self.inst_Dit_e.setStyleSheet("background-color: white; color: black;")
          self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")

      def Select2(self,tmp):
          self.Select2_r.setChecked(True)
          self.inst_Ndit_e.setText("")
          self.inst_Dit_e.setText("")
          self.inst_Ndit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_Dit_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_Seq_e.setStyleSheet("background-color: white; color: black;")

        # =================== OKNO GLOWNE ====================================
      def mkUI(self):

          grid = QGridLayout()
          w=0   

          self.inst_object_l=QLabel("OBJECT NAME:")
          self.inst_object_e=QLineEdit() 

          self.inst_Obtype_l=QLabel("TYPE:")
          self.inst_Obtype_s=QComboBox()
          self.inst_Obtype_s.addItems(self.obstypes)
          self.inst_Obtype_s.currentIndexChanged.connect(self.ObsTypeChanged)
          
          grid.addWidget(self.inst_object_l, w,0)
          grid.addWidget(self.inst_object_e, w,1)
          grid.addWidget(self.inst_Obtype_l, w,2)
          grid.addWidget(self.inst_Obtype_s, w,3)
        
          w=w+1
          self.inst_Ndit_l=QLabel("N:")
          self.inst_Ndit_e=QLineEdit()
          self.inst_Dit_l=QLabel("EXP TIME [s]:")
          self.inst_Dit_e=QLineEdit()
          self.Select1_r = QRadioButton("")
          self.Select1_r.setChecked(True)
          self.Select1_r.toggled.connect(self.Select)
          self.inst_Ndit_e.mousePressEvent = self.Select1  # connect
          self.inst_Dit_e.mousePressEvent = self.Select1   # connect

          grid.addWidget(self.inst_Ndit_l, w,0)
          grid.addWidget(self.inst_Ndit_e, w,1)
          grid.addWidget(self.inst_Dit_l, w,2)
          grid.addWidget(self.inst_Dit_e, w,3)
          grid.addWidget(self.Select1_r, w, 4)

          w=w+1
          self.inst_Seq_l=QLabel("Sequence:")
          self.inst_Seq_e=QLineEdit()
          self.inst_Seq_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.Select2_r = QRadioButton("")
          self.Select2_r.toggled.connect(self.Select)
          self.inst_Seq_e.mousePressEvent = self.Select2   # connect

          grid.addWidget(self.inst_Seq_l, w,0)
          grid.addWidget(self.inst_Seq_e, w,1,1,3)
          grid.addWidget(self.Select2_r, w, 4)

          w=w+1
          self.inst_NditProg_n=QProgressBar(self)
          self.inst_NditProg_n.setStyleSheet("background-color: rgb(233, 233, 233)")
          self.inst_NditProg_n.setValue(0)
          self.inst_NditProg_n.setFormat("0/1")


          self.inst_DitProg_n=QProgressBar(self)
          self.inst_DitProg_n.setStyleSheet("background-color: rgb(233, 233, 233)")

          grid.addWidget(self.inst_NditProg_n, w,0,1,2)
          grid.addWidget(self.inst_DitProg_n, w,2,1,2)
          
          w=w+1
          self.inst_Mode_l=QLabel("Mode:")
          self.inst_Mode_s=QComboBox()
          self.inst_Mode_s.addItems(self.modes)
          
          grid.addWidget(self.inst_Mode_l, w,0) 
          grid.addWidget(self.inst_Mode_s, w,1)          

          w=w+1
          self.inst_Bin_l=QLabel("Binning:")
          self.inst_Bin_e=QLineEdit()
          self.inst_Bin_e.setReadOnly(True)
          self.inst_Bin_s=QComboBox()
          self.inst_Bin_s.addItems(self.bins)
          self.inst_SetBin_p=QPushButton('Set')
          self.inst_SetBin_p.setStyleSheet(" color: gray;")
          self.inst_SetBin_p.clicked.connect(self.parent.ccd_setBin)
          
          grid.addWidget(self.inst_Bin_l, w,0) 
          grid.addWidget(self.inst_Bin_e, w,1)
          grid.addWidget(self.inst_Bin_s, w,2)
          grid.addWidget(self.inst_SetBin_p, w,3)

          w=w+1
          self.inst_Subraster_l=QLabel("Subraster:")
          self.inst_Subraster_s=QComboBox()
          self.inst_Subraster_s.addItems(self.subraster)
          
          grid.addWidget(self.inst_Subraster_l, w,0) 
          grid.addWidget(self.inst_Subraster_s, w,1)            


          w=w+1

          self.inst_gain_l=QLabel("GAIN:")
          self.inst_gain_e=QLineEdit()
          self.inst_gain_e.setReadOnly(True)
          self.inst_gain_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setGain_e=QComboBox()
          self.inst_setGain_e.addItems(self.gain_names)
          self.inst_setGain_p=QPushButton('Set')
          self.inst_setGain_p.clicked.connect(self.parent.ccd_setGain)

          grid.addWidget(self.inst_gain_l, w,0)
          grid.addWidget(self.inst_gain_e, w,1)
          grid.addWidget(self.inst_setGain_e, w,2)
          grid.addWidget(self.inst_setGain_p, w,3)


          w=w+1

          self.inst_read_l=QLabel("READ MODE:")
          self.inst_read_e=QLineEdit()
          self.inst_read_e.setReadOnly(True)
          self.inst_read_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setRead_e=QComboBox()
          self.inst_setRead_e.addItems(self.rm_names)
          self.inst_setRead_p=QPushButton('Set')
          self.inst_setRead_p.clicked.connect(self.parent.ccd_setReadMode)

          grid.addWidget(self.inst_read_l, w,0)
          grid.addWidget(self.inst_read_e, w,1)
          grid.addWidget(self.inst_setRead_e, w,2)
          grid.addWidget(self.inst_setRead_p, w,3)

          
          w=w+1

          self.inst_ccdTemp_l=QLabel(self.temp_label)
          self.inst_ccdTemp_e=QLineEdit()
          self.inst_ccdTemp_e.setReadOnly(True)
          self.inst_ccdTemp_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
          self.inst_setTemp_e=QLineEdit("" if self.temp_set is None else str(self.temp_set))
          self.inst_setTemp_e.setToolTip(f"Allowed: {self.temp_limits[0]} .. {self.temp_limits[1]} deg C")
          self.inst_setTemp_p=QPushButton('Set')
          self.inst_setTemp_p.clicked.connect(self.parent.ccd_setTemp)

          grid.addWidget(self.inst_ccdTemp_l, w,0)
          grid.addWidget(self.inst_ccdTemp_e, w,1)
          grid.addWidget(self.inst_setTemp_e, w,2)
          grid.addWidget(self.inst_setTemp_p, w,3)

          w=w+1

          self.test_c = QCheckBox("Test")
          self.test_c.setChecked(False)
          self.test_c.setLayoutDirection(Qt.LeftToRight)
          self.test_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/ToggleOnOrange.png)}::indicator:unchecked {image: url(./Icons/ToggleOffGreen.png)}")

          self.cooler_c = QCheckBox("Cooler")
          self.cooler_c.setChecked(False)
          self.cooler_c.setLayoutDirection(Qt.RightToLeft)
          self.cooler_c.setStyleSheet("QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
          self.cooler_c.clicked.connect(self.parent.ccd_coolerOnOf)

          grid.addWidget(self.test_c, w, 0)
          grid.addWidget(self.cooler_c, w,3)

          w=w+1          
          
          self.inst_Snap_p=QPushButton('SNAP')
          self.inst_Snap_p.clicked.connect(self.parent.ccd_Snap)
          self.inst_Pause_p=QPushButton('PAUSE')
          self.inst_Pause_p.setStyleSheet(" color: gray;")
          self.inst_Stop_p=QPushButton('STOP')
          self.inst_Stop_p.clicked.connect(self.parent.ccd_stopExp)
          #self.inst_Stop_p.setStyleSheet(" color: gray;")
          self.inst_Start_p=QPushButton('START')
          self.inst_Start_p.clicked.connect(self.parent.ccd_startExp)
          
          grid.addWidget(self.inst_Snap_p, w,0) 
          grid.addWidget(self.inst_Pause_p, w,1) 
          grid.addWidget(self.inst_Stop_p, w,2) 
          grid.addWidget(self.inst_Start_p, w,3)

          w=w+1
          grid.setRowMinimumHeight(w, 12)  # air between the instrument's controls and its optical path
          w=w+1
          self.optics_p = OpticsPanel(self.parent, self.parent.optics_model, self.detector)
          grid.addWidget(self.optics_p, w, 0, 1, 5)
          grid.setRowStretch(w + 1, 1)  # spare height below, the panel keeps its own

          # podpowiedz: ktora wartosc gain / read mode jest domyslna; inna podswietla pole na zolto
          for key, widgets in (("gain", (self.inst_gain_e, self.inst_setGain_e)),
                               ("rm", (self.inst_read_e, self.inst_setRead_e))):
              if self.defaults[key]:
                  for widget in widgets:
                      widget.setToolTip(f"Default: {self.defaults[key]}. Yellow: the camera is set otherwise.")

          # bez binningu / subrastra pola zostaja (TOI czyta z nich ustawienia ekspozycji), tylko ich nie widac
          if not self.show_binning:
              for widget in (self.inst_Bin_l, self.inst_Bin_e, self.inst_Bin_s, self.inst_SetBin_p,
                             self.inst_Subraster_l, self.inst_Subraster_s):
                  widget.hide()

          self.setLayout(grid)


class AndorCamera(GenericCamera):
      show_binning = False

      def title(self):
          return "ANDOR"


class CmosCamera(GenericCamera):
      temp_label = "SENSOR TEMP.:"


# od najbardziej szczegolowej: pierwsza pasujaca wygrywa, generyczne na koncu
INSTRUMENT_CLASSES = [
    (lambda name, spec: spec.get("kind") == "spectrograph" and name == "beso", BesoSpectrograph),
    (lambda name, spec: spec.get("kind") == "camera" and str(spec.get("camera_model", "")).lower().startswith("andor"), AndorCamera),
    (lambda name, spec: spec.get("kind") == "camera" and spec.get("camera_kind") == "cmos", CmosCamera),
    (lambda name, spec: spec.get("kind") == "camera", GenericCamera),
    (lambda name, spec: spec.get("kind") == "spectrograph", GenericSpectrograph),
]


def instrument_class(name, spec):
    """The tab class of instrument ``name`` from its configuration ``spec``; None for a component that is not one."""
    for match, cls in INSTRUMENT_CLASSES:
        if match(name, spec):
            return cls
    return None


def science_instruments(components):
    """The science instruments of a telescope, ``[(name, spec)]`` in configuration order, from the published
    ``observatory.components``: those flagged ``scientific`` (as ``Telescope.get_detectors('scientific')`` in ocaboxapi);
    while no component has the flag yet, every camera / spectrograph except the guiders."""
    detectors = [(name, spec) for name, spec in components.items()
                 if isinstance(spec, dict) and instrument_class(name, spec) is not None]
    flagged = [(name, spec) for name, spec in detectors if "scientific" in (spec.get("flags") or ())]
    if flagged:
        return flagged
    return [(name, spec) for name, spec in detectors
            if "guider" not in name and (spec.get("display") or {}).get("glyph") != "guider"]
          

          
          
          
          
          
          
          
          
          
          
          
          
          
          
          
