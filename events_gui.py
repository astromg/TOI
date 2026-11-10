"""Eventy i alerty conditions_overwatch w TOI (2026-11-10).

- :class:`EventsTab` — zakladka Events okna Aux, podzielona: po lewej generator eventu, po prawej aktywne eventy
  (status ``toi.events.list``). Dodawanie / usuwanie przez RPC ``toi.events.rpc``; Edit wczytuje event do generatora,
  zapis = add nowego, potem remove starego (blad add - stary zostaje). Kazdy moze (nie zaburza pracy teleskopow).
  Generator: rodzaj (Sun / In minutes / UT time / Date & time / Observers / Manual), pokretla (wysokosc Slonca,
  minuty), kalendarze; "every day" (pole ``repeat``) tam, gdzie overwatch pozwala: Slonce, godzina UT, nastepny
  zapis obserwatorow. Podglad najblizszego wystapienia liczony w TOI (ephem, jak overwatch). Skladnia ``when`` jak
  WAIT w planie (``sun_set=5``, ``ut=18:30``, ``ut=2026-12-24 18:30``, ``sec=600``, ``observers=2026-12-24|next``) -
  widoczna pod generatorem, wpisywana z reki w trybie Manual.
  Dzwiek i obrazek do wyboru z katalogow ``toi.events.sounds_dir`` / ``pictures_dir`` (te same widzi overwatch i
  grajacy oca_monitor); ▶ odsluch na tym stanowisku (aplay). Sekretne eventy ("secret": true) widac i mozna dodawac
  tylko w trybie admina: pole Admin w oknie obserwatorow, to stanowisko i ta sesja (TOI.events_admin). Tajemnica
  miekka - w NATS sa jak inne (Marek 2026-11-10: w porzadku).
- :class:`AlertsWindow` — niemodalne okno niepotwierdzonych alertow (woda: brak danych, brak zuzycia, wyciek;
  status ``toi.events.alerts``): wyskakuje przy nowym alercie i przy przypomnieniu (zapis obserwatorow), znika na
  wszystkich stanowiskach, gdy ktos potwierdzi ("Acknowledge" -> RPC ack, detektor w overwatchu od nowa).
Przyciski to zwykle sloty Qt: praca w ``asyncio.ensure_future`` z wlasnym try - wyjatek nie moze zabic TOI.
"""
import asyncio
import datetime
import logging
import math
import os
import subprocess
import time
import zoneinfo

import ephem
from PyQtX import QtGui
from PyQtX.QtCore import Qt, QDate, QDateTime, QTime, QTimeZone, QTimer
from PyQtX.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDial,
                             QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                             QRadioButton, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                             QTimeEdit, QVBoxLayout, QWidget)
from toi_theme import theme

logger = logging.getLogger(__name__)

DEFAULT_SOUNDS_DIR = "/data/misc/oca_overwatch/sounds"
DEFAULT_PICTURES_DIR = "/data/misc/oca_overwatch/pictures"
SOUND_EXT = (".wav",)
PICTURE_EXT = (".png", ".jpg", ".jpeg", ".webp")
LOCAL_TZ = zoneinfo.ZoneInfo("America/Santiago")
SITE = {"lat": -24.598616, "lon": -70.201266, "elevation": 2800}     # jak conditions_overwatch (site)
SUN_ALTS = (5, 0, -1, -6, -12, -16, -18)          # przyciski przy pokretle (jak NEXT EVENTS w oca_monitor)
MINUTES = (5, 10, 30, 60)
DEFAULT_SOUND_TEXT = "default (gong)"     # event bez dzwieku: overwatch gra default_sound ze swojego configu
KINDS = ("Sun", "In minutes", "UT time", "Date & time", "Observers", "Manual")
# kolejnosc przyciskow rodzaju (dwa rzedy po trzy); KINDS zostaje - jego indeksy to strony generatora
KIND_BUTTONS = ("In minutes", "UT time", "Date & time", "Sun", "Observers", "Manual")


def list_files(path, ext):
    try:
        return sorted(f for f in os.listdir(path) if f.lower().endswith(ext) and not f.startswith("."))
    except OSError:
        return []


def utc(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)


def next_sun_crossing(t, kind, alt):
    """Unix czas najblizszego przejscia Slonca przez alt (srodek tarczy, bez refrakcji - jak overwatch) albo None"""
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(SITE["lat"]), str(SITE["lon"]), SITE["elevation"]
    obs.pressure = 0
    obs.horizon = str(alt)
    obs.date = ephem.Date(t / 86400.0 + 2440587.5 - 2415020.0)
    try:
        d = obs.next_setting(ephem.Sun(), use_center=True) if kind == "sun_set" else \
            obs.next_rising(ephem.Sun(), use_center=True)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return None
    return (float(d) + 2415020.0 - 2440587.5) * 86400.0


def countdown(t, now=None):
    s = int(t - (now or time.time()))
    if s < 0:
        return "now"
    h, m = divmod(s // 60, 60)
    return f"in {h} h {m:02d} min" if h else f"in {m} min"


def when_text(t):
    """'today 22:34:30 UT (19:34 local, in 18 h 41 min)'"""
    d, now = utc(t), utc(time.time())
    day = "today" if d.date() == now.date() else "tomorrow" if (d.date() - now.date()).days == 1 else \
        d.strftime("%Y-%m-%d")
    loc = datetime.datetime.fromtimestamp(t, LOCAL_TZ).strftime("%H:%M")
    return f"{day} {d.strftime('%H:%M:%S')} UT ({loc} local, {countdown(t)})"


def describe(ev):
    """Event ze statusu po ludzku (kolumna What)"""
    s, rep = ev.get("spec") or {}, ev.get("repeat")
    k = s.get("kind")
    if k in ("sun_set", "sun_rise"):
        side = "evening" if k == "sun_set" else "morning"
        return f"{side}, Sun {s.get('alt', 0):+g}°, " + ("every day" if rep else "once")
    if k == "ut" and s.get("tod"):
        return f"{s['tod'][:5]} UT, " + ("every day" if rep else "once")
    if k == "ut":
        return f"{utc(s['t']).strftime('%Y-%m-%d %H:%M')} UT"
    if k == "observers" and s.get("date") == "next":
        return "every save of the observers" if rep else "next save of the observers"
    if k == "observers":
        return f"observers saved on {s.get('date')} (local)"
    return ev.get("when", "?")


class EventsTab(QWidget):
    COLUMNS = ("Next (UT)", "What", "Message", "Sound", "Picture", "By")

    def __init__(self, parent):
        super(EventsTab, self).__init__()
        self.parent = parent
        self.rows = []          # pokazane (bez sekretnych poza trybem admina)
        self.all_rows = []      # caly status
        self.admin = False
        self.editing = None     # event wczytany do generatora (Edit)
        self.mkUI()
        self.fill_files()
        self.reset_generator()
        self.timer = QTimer(self)       # odliczanie w podgladzie i liscie
        self.timer.timeout.connect(self.tick)
        self.timer.start(30000)

    # ---------- konfiguracja, pliki ----------
    def cfg(self):
        return self.parent.local_cfg["toi"].get("events") or {}

    def sounds_dir(self):
        return self.cfg().get("sounds_dir", DEFAULT_SOUNDS_DIR)

    def pictures_dir(self):
        return self.cfg().get("pictures_dir", DEFAULT_PICTURES_DIR)

    def fill_files(self):
        sound, picture = self.sound_c.currentData(), self.picture_c.currentData()
        for combo, first, files in ((self.sound_c, DEFAULT_SOUND_TEXT, list_files(self.sounds_dir(), SOUND_EXT)),
                                    (self.picture_c, "none", list_files(self.pictures_dir(), PICTURE_EXT))):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, None)
            for f in files:
                combo.addItem(f, f)
            combo.blockSignals(False)
        self.select(self.sound_c, sound)
        self.select(self.picture_c, picture)
        self.picture_changed()

    @staticmethod
    def select(combo, value):
        i = combo.findData(value)
        if i < 0 and value:         # plik spoza katalogu (np. edytowany event) - pokazany, zeby go nie zgubic
            combo.addItem(value, value)
            i = combo.findData(value)
        combo.setCurrentIndex(max(i, 0))

    def play_sound(self):
        name = self.sound_c.currentData() or "gong.wav"     # default: gong, jesli lezy we wspolnym katalogu
        path = os.path.join(self.sounds_dir(), name)
        if not os.path.isfile(path):
            self.set_status(f"no {name} in {self.sounds_dir()}", ok=False)
            return
        try:
            subprocess.Popen(["aplay", "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.set_status(f"cannot play here: {e}", ok=False)

    def picture_changed(self):
        name = self.picture_c.currentData()
        self.thumb_l.clear()
        if not name:
            self.thumb_l.setText("")
            return
        image = QtGui.QImage(os.path.join(self.pictures_dir(), name))
        if image.isNull():
            self.thumb_l.setText("?")
            return
        self.thumb_l.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
            96, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ---------- generator ----------
    def kind(self):
        return KINDS[self.kind_s.currentIndex()]

    def set_kind(self, name):
        i = KINDS.index(name)
        self.kind_g.button(i).setChecked(True)
        self.kind_s.setCurrentIndex(i)
        self.refresh()

    def reset_generator(self):
        now = utc(time.time())
        self.sun_evening_r.setChecked(True)
        self.sun_d.setValue(5)
        self.sun_daily_c.setChecked(True)
        self.min_d.setValue(10)
        nxt = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        self.time_e.setTime(QTime(nxt.hour, 0))
        self.time_daily_c.setChecked(False)
        self.datetime_e.setDateTime(QDateTime(QDate(nxt.year, nxt.month, nxt.day), QTime(nxt.hour, 0),
                                              QTimeZone.utc()))
        self.obs_next_r.setChecked(True)
        today = datetime.datetime.now(LOCAL_TZ).date()
        self.obs_date_e.setDate(QDate(today.year, today.month, today.day))
        self.obs_daily_c.setChecked(False)
        self.manual_e.clear()
        self.info_e.clear()
        self.select(self.sound_c, None)
        self.select(self.picture_c, None)
        self.secret_c.setChecked(False)
        self.editing = None
        self.add_p.setText("Add")
        self.cancel_p.hide()
        self.set_kind("Sun")

    def generated(self):
        """(when, repeat albo None, czas najblizszy albo None, opis) z pol generatora; ValueError - blad"""
        k, now = self.kind(), time.time()
        if k == "Sun":
            kind = "sun_set" if self.sun_evening_r.isChecked() else "sun_rise"
            alt = self.sun_d.value()
            daily = self.sun_daily_c.isChecked()
            t = next_sun_crossing(now, kind, alt)
            side = "evening (setting)" if kind == "sun_set" else "morning (rising)"
            return f"{kind}={alt}", daily, t, f"Sun {alt:+d}° {side}, " + ("every day" if daily else "once")
        if k == "In minutes":
            m = self.min_d.value()
            return f"sec={m * 60}", None, now + m * 60, f"in {m} min, once"
        if k == "UT time":
            q = self.time_e.time()
            daily = self.time_daily_c.isChecked()
            d = utc(now).replace(hour=q.hour(), minute=q.minute(), second=0, microsecond=0)
            if d.timestamp() <= now:
                d += datetime.timedelta(days=1)
            return f"ut={q.hour():02d}:{q.minute():02d}", daily, d.timestamp(), \
                f"{q.hour():02d}:{q.minute():02d} UT, " + ("every day" if daily else "once")
        if k == "Date & time":
            q = self.datetime_e.dateTime().toUTC()
            t = q.toSecsSinceEpoch()
            if t <= now:
                raise ValueError("this date is in the past")
            return f"ut={q.toString('yyyy-MM-dd HH:mm')}", None, t, f"{q.toString('yyyy-MM-dd HH:mm')} UT, once"
        if k == "Observers":
            if self.obs_next_r.isChecked():
                daily = self.obs_daily_c.isChecked()
                return "observers=next", daily, None, \
                    "every save of the observers" if daily else "the next save of the observers"
            d = self.obs_date_e.date().toString("yyyy-MM-dd")
            if d < datetime.datetime.now(LOCAL_TZ).date().isoformat():
                raise ValueError("this date is in the past")
            return f"observers={d}", None, None, f"when the observers are saved on {d} (local date)"
        text = self.manual_e.text().strip()
        if not text:
            raise ValueError("type when, e.g. sun_set=5, ut=2026-12-24 18:30, sec=600, observers=next")
        return text, None, None, "as typed (checked by conditions_overwatch)"

    def refresh(self, *_):
        """Podglad: najblizsze wystapienie i tekst when"""
        self.obs_date_e.setEnabled(self.obs_date_r.isChecked())
        self.obs_daily_c.setEnabled(self.obs_next_r.isChecked())
        try:
            when, repeat, t, text = self.generated()
        except ValueError as e:
            self.preview_l.setText(str(e))
            self.preview_l.setStyleSheet(theme.css(fg="bad_fg"))
            self.when_l.setText("")
            return
        self.preview_l.setStyleSheet(theme.css(fg="field_fg"))
        self.preview_l.setText(f"{text}\nnext: {when_text(t)}" if t else text)
        self.when_l.setText(f"when: {when}" + ("" if repeat is None else f", repeat: {'daily' if repeat else 'once'}"))

    def tick(self):
        self.refresh()
        self.update_list(self.all_rows)

    # ---------- lista ----------
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
            nxt = ev.get("next") or ""
            t = None
            if "T" in nxt:
                try:
                    t = datetime.datetime.fromisoformat(nxt).timestamp()
                except ValueError:
                    pass
            values = (utc(t).strftime("%m-%d %H:%M") if t else ("observers" if nxt == "next" else nxt or "--"),
                      describe(ev), ev.get("info", ""), ev.get("sound") or DEFAULT_SOUND_TEXT, ev.get("picture") or "",
                      ev.get("by") or "")
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0 and t:
                    item.setToolTip(when_text(t))
                if c == 3 and not ev.get("sound"):      # bez wyboru: overwatch gra swoj default_sound
                    item.setForeground(theme.qcolor("muted_fg"))
                    item.setToolTip("no sound chosen: conditions_overwatch plays its default_sound (gong)")
                if c == 1:
                    item.setToolTip(f"when: {ev.get('when')}")
                    if ev.get("secret"):
                        item.setText("\U0001F512 " + item.text())
                        item.setToolTip(f"secret, shown only in admin mode; when: {ev.get('when')}")
                self.table.setItem(r, c, item)

    def selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.rows[r] for r in rows if r < len(self.rows)]

    def edit_clicked(self):
        sel = self.selected()
        if len(sel) != 1:
            self.set_status("Select one event to edit", ok=False)
            return
        ev = sel[0]
        self.reset_generator()
        s = ev.get("spec") or {}
        k = s.get("kind")
        if k in ("sun_set", "sun_rise"):
            (self.sun_evening_r if k == "sun_set" else self.sun_morning_r).setChecked(True)
            self.sun_d.setValue(int(round(s.get("alt", 0))))
            self.sun_daily_c.setChecked(bool(ev.get("repeat")))
            self.set_kind("Sun")
        elif k == "ut" and s.get("tod"):
            hh, mm = int(s["tod"][:2]), int(s["tod"][3:5])
            self.time_e.setTime(QTime(hh, mm))
            self.time_daily_c.setChecked(bool(ev.get("repeat")))
            self.set_kind("UT time")
        elif k == "ut":
            d = utc(s["t"])
            self.datetime_e.setDateTime(QDateTime(QDate(d.year, d.month, d.day), QTime(d.hour, d.minute),
                                                  QTimeZone.utc()))
            self.set_kind("Date & time")
        elif k == "observers":
            if s.get("date") == "next":
                self.obs_next_r.setChecked(True)
                self.obs_daily_c.setChecked(bool(ev.get("repeat")))
            else:
                self.obs_date_r.setChecked(True)
                y, m, d = (int(x) for x in s["date"].split("-"))
                self.obs_date_e.setDate(QDate(y, m, d))
            self.set_kind("Observers")
        else:
            self.manual_e.setText(ev.get("when", ""))
            self.set_kind("Manual")
        self.info_e.setText(ev.get("info", ""))
        self.select(self.sound_c, ev.get("sound"))
        self.select(self.picture_c, ev.get("picture"))
        self.secret_c.setChecked(bool(ev.get("secret")))
        self.editing = ev
        self.add_p.setText("Save changes")
        self.cancel_p.show()
        self.set_status(f'editing: {describe(ev)} - "{ev.get("info", "")}"')

    def remove_clicked(self):
        sel = self.selected()
        if not sel:
            self.set_status("Select an event to remove", ok=False)
            return
        for ev in sel:
            asyncio.ensure_future(self._call({"action": "remove", "id": ev["id"], "by": self.parent.myself},
                                             "removed"))

    # ---------- RPC ----------
    def set_status(self, text, ok=True):
        self.status_l.setStyleSheet(theme.css(fg="ok_fg" if ok else "bad_fg"))
        self.status_l.setText(text)

    def add_clicked(self):
        try:
            when, repeat, t, text = self.generated()
        except ValueError as e:
            self.set_status(str(e), ok=False)
            return
        data = {"action": "add", "when": when, "info": self.info_e.text().strip(),
                "sound": self.sound_c.currentData(), "picture": self.picture_c.currentData(),
                "secret": self.admin and self.secret_c.isChecked(), "by": self.parent.myself}
        if repeat is not None:
            data["repeat"] = repeat
        asyncio.ensure_future(self._save(data, self.editing))

    async def _save(self, data, old):
        ok = await self._call(data, "saved" if old else "added")
        if ok and old:      # najpierw nowy, potem usuniecie starego - blad zapisu nie gubi eventu
            await self._call({"action": "remove", "id": old["id"], "by": self.parent.myself}, "replaced", quiet=True)
        if ok:
            self.reset_generator()

    async def _call(self, data, done, quiet=False):
        try:
            resp = await self.parent.events_rpc(data)
            if resp.get("status") == "ok":
                ev = resp.get("event") or {}
                if not quiet:
                    self.set_status(f'{done}: {describe(ev) if ev.get("spec") else ev.get("when", "")} '
                                    f'{ev.get("info", "")}')
                return True
            self.set_status(f'not {done}: {resp.get("error", resp)}', ok=False)
        except Exception as e:      # timeout: overwatch nie odpowiada
            self.set_status(f'not {done}: conditions_overwatch does not answer ({e!r})', ok=False)
            logger.warning(f'TOI events RPC {data.get("action")}: {e!r}')
        return False

    # ---------- wyglad ----------
    @staticmethod
    def dial(lo, hi, step_marks):
        d = QDial()
        d.setRange(lo, hi)
        d.setNotchesVisible(True)
        d.setNotchTarget(step_marks)
        d.setWrapping(False)
        d.setFixedSize(110, 110)
        return d

    def mk_sun(self):
        w = QWidget()
        g = QGridLayout(w)
        self.sun_evening_r = QRadioButton("Evening (setting)")
        self.sun_morning_r = QRadioButton("Morning (rising)")
        side = QButtonGroup(w)
        side.addButton(self.sun_evening_r)
        side.addButton(self.sun_morning_r)
        self.sun_d = self.dial(-30, 30, 3.0)
        self.sun_s = QSpinBox()
        self.sun_s.setRange(-30, 30)
        self.sun_s.setSuffix(" °")
        self.sun_d.valueChanged.connect(self.sun_s.setValue)
        self.sun_s.valueChanged.connect(self.sun_d.setValue)
        presets = QGridLayout()
        for i, a in enumerate(SUN_ALTS):
            b = QPushButton(f"{a:+d}°" if a else "0°")
            b.setFixedWidth(48)
            b.clicked.connect(lambda _=False, a=a: self.sun_d.setValue(a))
            presets.addWidget(b, i // 4, i % 4)
        self.sun_daily_c = QCheckBox("every day")
        g.addWidget(self.sun_evening_r, 0, 0)
        g.addWidget(self.sun_morning_r, 0, 1)
        g.addWidget(self.sun_d, 1, 0, 2, 1)
        g.addWidget(QLabel("Sun altitude (centre, no refraction):"), 1, 1)
        g.addWidget(self.sun_s, 2, 1)
        g.addLayout(presets, 3, 0, 1, 2)
        g.addWidget(self.sun_daily_c, 4, 0, 1, 2)
        for x in (self.sun_evening_r, self.sun_morning_r, self.sun_daily_c):
            x.toggled.connect(self.refresh)
        self.sun_s.valueChanged.connect(self.refresh)
        return w

    def mk_minutes(self):
        w = QWidget()
        g = QGridLayout(w)
        self.min_d = self.dial(1, 120, 5.0)
        self.min_s = QSpinBox()
        self.min_s.setRange(1, 24 * 60)
        self.min_s.setSuffix(" min")
        self.min_d.valueChanged.connect(self.min_s.setValue)
        self.min_s.valueChanged.connect(lambda v: self.min_d.setValue(min(v, 120)))
        self.min_s.valueChanged.connect(self.refresh)
        row = QHBoxLayout()
        for m in MINUTES:
            b = QPushButton(f"{m} min")
            b.clicked.connect(lambda _=False, m=m: self.min_s.setValue(m))
            row.addWidget(b)
        g.addWidget(self.min_d, 0, 0, 2, 1)
        g.addWidget(QLabel("In (dial up to 2 h, field up to 24 h):"), 0, 1)
        g.addWidget(self.min_s, 1, 1)
        g.addLayout(row, 2, 0, 1, 2)
        g.setRowStretch(3, 1)
        return w

    def mk_time(self):
        w = QWidget()
        g = QGridLayout(w)
        self.time_e = QTimeEdit()
        self.time_e.setDisplayFormat("HH:mm")
        self.time_e.timeChanged.connect(self.refresh)
        self.time_daily_c = QCheckBox("every day")
        self.time_daily_c.toggled.connect(self.refresh)
        g.addWidget(QLabel("UT:"), 0, 0)
        g.addWidget(self.time_e, 0, 1)
        g.addWidget(self.time_daily_c, 1, 0, 1, 2)
        g.setRowStretch(2, 1)
        return w

    def mk_datetime(self):
        w = QWidget()
        g = QGridLayout(w)
        self.datetime_e = QDateTimeEdit()
        self.datetime_e.setTimeZone(QTimeZone.utc())
        self.datetime_e.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.datetime_e.setCalendarPopup(True)
        self.datetime_e.dateTimeChanged.connect(self.refresh)
        g.addWidget(QLabel("UT:"), 0, 0)
        g.addWidget(self.datetime_e, 0, 1)
        g.setRowStretch(1, 1)
        return w

    def mk_observers(self):
        w = QWidget()
        g = QGridLayout(w)
        self.obs_next_r = QRadioButton("at the next save of the observers")
        self.obs_date_r = QRadioButton("when saved on (local date):")
        grp = QButtonGroup(w)
        grp.addButton(self.obs_next_r)
        grp.addButton(self.obs_date_r)
        self.obs_daily_c = QCheckBox("at every save (every night)")
        self.obs_date_e = QDateEdit()
        self.obs_date_e.setDisplayFormat("yyyy-MM-dd")
        self.obs_date_e.setCalendarPopup(True)
        for x in (self.obs_next_r, self.obs_date_r, self.obs_daily_c):
            x.toggled.connect(self.refresh)
        self.obs_date_e.dateChanged.connect(self.refresh)
        g.addWidget(self.obs_next_r, 0, 0, 1, 2)
        g.addWidget(self.obs_daily_c, 1, 1)
        g.addWidget(self.obs_date_r, 2, 0)
        g.addWidget(self.obs_date_e, 2, 1)
        g.setRowStretch(3, 1)
        return w

    def mk_manual(self):
        w = QWidget()
        g = QVBoxLayout(w)
        self.manual_e = QLineEdit()
        self.manual_e.setPlaceholderText("sun_set=5 | sun_rise=-18 | ut=18:30 | ut=2026-12-24 18:30 | sec=600 | "
                                         "observers=2026-12-24 | observers=next")
        self.manual_e.textChanged.connect(self.refresh)
        g.addWidget(QLabel("when (like WAIT in a plan):"))
        g.addWidget(self.manual_e)
        g.addStretch(1)
        return w

    def mkUI(self):
        # ----- lewa: generator -----
        left = QWidget()
        lv = QVBoxLayout(left)
        kinds = QGridLayout()           # dwa rzedy po trzy - generator waski
        self.kind_g = QButtonGroup(self)
        self.kind_s = QStackedWidget()
        for i, (name, page) in enumerate(zip(KINDS, (self.mk_sun(), self.mk_minutes(), self.mk_time(),
                                                      self.mk_datetime(), self.mk_observers(), self.mk_manual()))):
            b = QPushButton(name.replace("&", "&&"))       # & w Qt to skrot klawiszowy
            b.setCheckable(True)
            self.kind_g.addButton(b, i)
            pos = KIND_BUTTONS.index(name)
            kinds.addWidget(b, pos // 3, pos % 3)
            self.kind_s.addWidget(page)
        self.kind_g.idClicked.connect(lambda i: (self.kind_s.setCurrentIndex(i), self.refresh()))
        lv.addLayout(kinds)
        lv.addWidget(self.kind_s)

        common = QGridLayout()
        self.info_e = QLineEdit()
        self.info_e.setPlaceholderText("message in TOI and oca_monitor (empty: automatic)")
        self.sound_c = QComboBox()
        play = QPushButton("▶")
        play.setFixedWidth(32)
        play.setToolTip("Listen here (this station)")
        play.clicked.connect(self.play_sound)
        self.picture_c = QComboBox()
        self.picture_c.setToolTip("shown in the Pictures tab of every TOI")
        self.picture_c.currentIndexChanged.connect(self.picture_changed)
        self.thumb_l = QLabel("")
        self.thumb_l.setFixedSize(96, 64)
        self.thumb_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        refresh = QPushButton("↻")
        refresh.setFixedWidth(32)
        refresh.setToolTip("Read the sound and picture folders again")
        refresh.clicked.connect(self.fill_files)
        common.addWidget(QLabel("Message:"), 0, 0)
        common.addWidget(self.info_e, 0, 1, 1, 3)
        common.addWidget(QLabel("Sound:"), 1, 0)
        common.addWidget(self.sound_c, 1, 1)
        common.addWidget(play, 1, 2)
        common.addWidget(refresh, 1, 3)
        common.addWidget(QLabel("Picture:"), 2, 0)
        common.addWidget(self.picture_c, 2, 1)
        common.addWidget(self.thumb_l, 2, 2, 1, 2)
        common.setColumnStretch(1, 1)
        lv.addLayout(common)

        self.preview_l = QLabel("")
        self.preview_l.setWordWrap(True)
        self.when_l = QLabel("")
        self.when_l.setStyleSheet(theme.css(fg="muted_fg"))
        lv.addWidget(self.preview_l)
        lv.addWidget(self.when_l)
        buttons = QHBoxLayout()
        self.secret_c = QCheckBox("Secret")
        self.secret_c.setToolTip("A surprise: listed only in admin mode (observers window)")
        self.secret_c.setVisible(False)
        self.cancel_p = QPushButton("Cancel edit")
        self.cancel_p.clicked.connect(self.reset_generator)
        self.add_p = QPushButton("Add")
        self.add_p.clicked.connect(self.add_clicked)
        buttons.addStretch(1)
        buttons.addWidget(self.secret_c)
        buttons.addWidget(self.cancel_p)
        buttons.addWidget(self.add_p)
        lv.addLayout(buttons)
        lv.addStretch(1)

        # ----- prawa: aktywne eventy -----
        right = QWidget()
        rv = QVBoxLayout(right)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.edit_clicked)
        rb = QHBoxLayout()
        self.status_l = QLabel("")
        self.status_l.setWordWrap(True)
        edit = QPushButton("Edit")
        edit.setToolTip("Load the selected event into the generator (also: double click)")
        edit.clicked.connect(self.edit_clicked)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.remove_clicked)
        rb.addWidget(self.status_l, 1)
        rb.addWidget(edit)
        rb.addWidget(remove)
        rv.addWidget(QLabel("Active events"))
        rv.addWidget(self.table, 1)
        rv.addLayout(rb)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 800])
        layout = QVBoxLayout(self)
        layout.addWidget(split)


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
