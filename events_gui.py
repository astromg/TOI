"""Eventy i alerty conditions_overwatch w TOI (2026-11-10).

- :class:`EventsTab` — zakladka Events okna Aux: lista eventow (status ``toi.events.list``), dodawanie i usuwanie
  przez RPC ``toi.events.rpc``. Kazdy moze (nie zaburza pracy teleskopow). ``when`` jak WAIT w planie:
  ``sun_set=5``, ``sun_rise=-18``, ``ut=18:30``, ``ut=2026-12-24 18:30``, ``sec=600``, ``observers=2026-12-24``
  (data lokalna, Chile). Dzwiek i obrazek do wyboru z katalogow ``toi.events.sounds_dir`` / ``pictures_dir``
  (te same widzi overwatch i grajacy oca_monitor). Sekretne eventy (niespodzianki, "secret": true w statusie) widac
  i mozna dodawac tylko w trybie admina: pole Admin w oknie obserwatorow, to stanowisko i ta sesja (TOI.events_admin).
  Tajemnica miekka - w NATS sa jak inne (Marek 2026-11-10: w porzadku).
- :class:`AlertsWindow` — niemodalne okno niepotwierdzonych alertow (woda: brak danych, brak zuzycia, wyciek;
  status ``toi.events.alerts``): wyskakuje przy nowym alercie i przy przypomnieniu (zapis obserwatorow), znika na
  wszystkich stanowiskach, gdy ktos potwierdzi ("Acknowledge" -> RPC ack, detektor w overwatchu od nowa).
Przyciski to zwykle sloty Qt: praca w ``asyncio.ensure_future`` z wlasnym try - wyjatek nie moze zabic TOI.
"""
import asyncio
import datetime
import logging
import os

from PyQtX.QtCore import Qt
from PyQtX.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from toi_theme import theme

logger = logging.getLogger(__name__)

DEFAULT_SOUNDS_DIR = "/data/misc/oca_overwatch/sounds"
DEFAULT_PICTURES_DIR = "/data/misc/oca_overwatch/pictures"
SOUND_EXT = (".wav",)
PICTURE_EXT = (".png", ".jpg", ".jpeg", ".webp")

# szybkie wpisy: jak NEXT EVENTS w oca_monitor (Slonce wieczorem +5, -1, -16, -18; rano -18, -10, 0)
PRESETS = (
    ("Sunset +5 (start of operations)", "sun_set=5", "Sun at +5 deg, start of operations"),
    ("Sunset -1", "sun_set=-1", "Sun at -1 deg"),
    ("Sunset -16", "sun_set=-16", "Sun at -16 deg"),
    ("Evening -18 (astronomical night)", "sun_set=-18", "Sun at -18 deg, astronomical night"),
    ("Morning -18 (end of observations)", "sun_rise=-18", "Sun at -18 deg, end of observations"),
    ("Morning -10", "sun_rise=-10", "Sun at -10 deg"),
    ("Sunrise 0", "sun_rise=0", "Sunrise"),
    ("Next save of the observers", "observers=next", ""),
    ("In 10 minutes", "sec=600", ""),
    ("In 1 hour", "sec=3600", ""),
)


def list_files(path, ext):
    try:
        return sorted(f for f in os.listdir(path) if f.lower().endswith(ext) and not f.startswith("."))
    except OSError:
        return []


def short_time(text):
    """ISO UT -> 'MM-DD HH:MM' (data obserwatorow zostaje)"""
    if not text or "T" not in text:
        return text or "--"
    try:
        return datetime.datetime.fromisoformat(text).strftime("%m-%d %H:%M")
    except ValueError:
        return text


class EventsTab(QWidget):
    COLUMNS = ("Next (UT)", "When", "Message", "Sound", "Picture", "By")

    def __init__(self, parent):
        super(EventsTab, self).__init__()
        self.parent = parent
        self.rows = []          # pokazane (bez sekretnych poza trybem admina)
        self.all_rows = []      # caly status
        self.admin = False
        self.mkUI()
        self.fill_files()

    def cfg(self):
        return self.parent.local_cfg["toi"].get("events") or {}

    def sounds_dir(self):
        return self.cfg().get("sounds_dir", DEFAULT_SOUNDS_DIR)

    def pictures_dir(self):
        return self.cfg().get("pictures_dir", DEFAULT_PICTURES_DIR)

    def fill_files(self):
        sound, picture = self.sound_c.currentData(), self.picture_c.currentData()
        self.sound_c.clear()
        self.sound_c.addItem("default (gong)", None)
        for f in list_files(self.sounds_dir(), SOUND_EXT):
            self.sound_c.addItem(f, f)
        self.picture_c.clear()
        self.picture_c.addItem("none", None)
        for f in list_files(self.pictures_dir(), PICTURE_EXT):
            self.picture_c.addItem(f, f)
        for combo, value in ((self.sound_c, sound), (self.picture_c, picture)):
            i = combo.findData(value)
            combo.setCurrentIndex(max(i, 0))

    def set_admin(self, on):
        self.admin = bool(on)
        self.secret_c.setVisible(self.admin)
        if not self.admin:
            self.secret_c.setChecked(False)
        self.update_list(self.all_rows)

    def update_list(self, rows):
        """Nowy status eventow z overwatcha; sekretne tylko w trybie admina"""
        self.all_rows = rows or []
        self.rows = [ev for ev in self.all_rows if self.admin or not ev.get("secret")]
        self.table.setRowCount(len(self.rows))
        for r, ev in enumerate(self.rows):
            values = (short_time(ev.get("next")), ev.get("when", ""), ev.get("info", ""),
                      ev.get("sound") or "", ev.get("picture") or "", ev.get("by") or "")
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 1 and ev.get("repeat"):
                    item.setToolTip("every day")
                if c == 1 and ev.get("secret"):
                    item.setText("\U0001F512 " + item.text())
                    item.setToolTip("secret: shown only in admin mode")
                self.table.setItem(r, c, item)

    def preset_chosen(self, index):
        if index <= 0:
            return
        label, when, info = PRESETS[index - 1]
        self.when_e.setText(when)
        if info:
            self.info_e.setText(info)
        self.preset_c.setCurrentIndex(0)

    def set_status(self, text, ok=True):
        self.status_l.setStyleSheet(theme.css(fg="ok_fg" if ok else "bad_fg"))
        self.status_l.setText(text)

    def add_clicked(self):
        data = {"action": "add", "when": self.when_e.text().strip(), "info": self.info_e.text().strip(),
                "sound": self.sound_c.currentData(), "picture": self.picture_c.currentData(), "by": self.parent.myself,
                "secret": self.admin and self.secret_c.isChecked()}
        if not data["when"]:
            self.set_status("When? e.g. sun_set=5, ut=2026-12-24 18:30, sec=600", ok=False)
            return
        asyncio.ensure_future(self._call(data, "added"))

    def remove_clicked(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            self.set_status("Select an event to remove", ok=False)
            return
        for r in rows:
            if r < len(self.rows):
                asyncio.ensure_future(self._call({"action": "remove", "id": self.rows[r]["id"],
                                                  "by": self.parent.myself}, "removed"))

    async def _call(self, data, done):
        try:
            resp = await self.parent.events_rpc(data)
            if resp.get("status") == "ok":
                ev = resp.get("event") or {}
                self.set_status(f'{done}: {ev.get("when", "")} {ev.get("info", "")}')
                if data["action"] == "add":
                    self.when_e.clear()
                    self.info_e.clear()
            else:
                self.set_status(f'not {done}: {resp.get("error", resp)}', ok=False)
        except Exception as e:      # timeout: overwatch nie odpowiada
            self.set_status(f'not {done}: conditions_overwatch does not answer ({e!r})', ok=False)
            logger.warning(f'TOI events RPC {data.get("action")}: {e!r}')

    def mkUI(self):
        layout = QVBoxLayout()
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        grid = QGridLayout()
        self.preset_c = QComboBox()
        self.preset_c.addItem("Quick: choose…")
        for label, _, _ in PRESETS:
            self.preset_c.addItem(label)
        self.preset_c.currentIndexChanged.connect(self.preset_chosen)
        self.when_e = QLineEdit()
        self.when_e.setPlaceholderText("sun_set=5 | sun_rise=-18 | ut=18:30 | ut=2026-12-24 18:30 | sec=600 | "
                                       "observers=2026-12-24 | observers=next")
        self.when_e.setToolTip("When, like WAIT in a plan. Sun: every day (centre, no refraction). ut / sec / "
                               "observers: once. observers=DATE: when the observers are saved that day (local date); "
                               "observers=next: the next save of the observers.")
        self.info_e = QLineEdit()
        self.info_e.setPlaceholderText("message shown in TOI and oca_monitor (empty: automatic)")
        self.sound_c = QComboBox()
        self.picture_c = QComboBox()
        self.picture_c.setToolTip("shown in the Pictures tab of every TOI")
        refresh = QPushButton("↻")
        refresh.setToolTip("Read the sound and picture folders again")
        refresh.clicked.connect(self.fill_files)
        self.secret_c = QCheckBox("Secret")
        self.secret_c.setToolTip("A surprise: listed only in admin mode (observers window)")
        self.secret_c.setVisible(False)
        add = QPushButton("Add")
        add.clicked.connect(self.add_clicked)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self.remove_clicked)
        grid.addWidget(QLabel("When:"), 0, 0)
        grid.addWidget(self.when_e, 0, 1, 1, 3)
        grid.addWidget(self.preset_c, 0, 4)
        grid.addWidget(QLabel("Message:"), 1, 0)
        grid.addWidget(self.info_e, 1, 1, 1, 4)
        grid.addWidget(QLabel("Sound:"), 2, 0)
        grid.addWidget(self.sound_c, 2, 1)
        grid.addWidget(QLabel("Picture:"), 2, 2)
        grid.addWidget(self.picture_c, 2, 3)
        grid.addWidget(refresh, 2, 4)
        buttons = QHBoxLayout()
        self.status_l = QLabel("")
        buttons.addWidget(self.status_l, 1)
        buttons.addWidget(remove)
        buttons.addWidget(self.secret_c)
        buttons.addWidget(add)
        layout.addLayout(grid)
        layout.addLayout(buttons)
        self.setLayout(layout)


class AlertsWindow(QWidget):
    """Niepotwierdzone alerty conditions_overwatch. Niemodalne (modalne okno w qasync zatrzymaloby zadania w tle)."""

    def __init__(self, parent):
        super(AlertsWindow, self).__init__()
        self.parent = parent
        self.alerts = []
        self.setWindowTitle("Observatory alerts")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.mkUI()

    def update_alerts(self, alerts, pop=False):
        """Nowy status; pop - pokaz okno (nowy alert albo przypomnienie). Pusta lista - okno znika (potwierdzone)"""
        self.alerts = alerts or []
        self.table.setRowCount(len(self.alerts))
        for r, a in enumerate(self.alerts):
            since = short_time(a.get("since"))
            text = a.get("text", "")
            if a.get("resolved"):
                text += f'  (resolved {short_time(a["resolved"])[6:]} UT)'
            for c, v in enumerate((since, text)):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setForeground(theme.qcolor("ok_fg" if a.get("resolved") else "bad_fg"))
                self.table.setItem(r, c, item)
        if self.table.rowCount():
            self.table.selectRow(0)
        if not self.alerts:
            self.hide()
        elif pop:
            self.show()
            self.raise_()
            self.activateWindow()

    def ack_clicked(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or list(range(len(self.alerts)))
        for r in rows:
            if r < len(self.alerts):
                asyncio.ensure_future(self._ack(self.alerts[r]))

    async def _ack(self, alert):
        try:
            resp = await self.parent.events_rpc({"action": "ack", "id": alert["id"], "by": self.parent.myself})
            if resp.get("status") != "ok":
                self.status_l.setText(f'not acknowledged: {resp.get("error", resp)}')
        except Exception as e:
            self.status_l.setText(f'not acknowledged: conditions_overwatch does not answer ({e!r})')
            logger.warning(f'TOI alert ack: {e!r}')

    def mkUI(self):
        layout = QVBoxLayout()
        info = QLabel("Problems that need a person. Check, then acknowledge - the check starts again; if it is still "
                      "wrong, it comes back.")
        info.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(("Since (UT)", "Problem"))
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.status_l = QLabel("")
        later = QPushButton("Later")
        later.setToolTip("Close; it comes back with the next save of the observers")
        later.clicked.connect(self.hide)
        ack = QPushButton("Acknowledge")
        ack.setToolTip("Acknowledge the selected (or all) for every TOI")
        ack.clicked.connect(self.ack_clicked)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status_l, 1)
        buttons.addWidget(later)
        buttons.addWidget(ack)
        layout.addWidget(info)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.resize(700, 250)
