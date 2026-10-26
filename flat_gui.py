#!/usr/bin/env python3

import datetime

from PyQtX.QtCore import Qt
from PyQtX.QtGui import QFont
from PyQtX import QtGui
from PyQtX.QtWidgets import (QAbstractItemView,
                             QLineEdit, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView)



from base_window import BaseWindow

class FlatWindow(BaseWindow):
    def __init__(self, parent):
        super(FlatWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Calibration')
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 1940, self.parent.obs_window_geometry[1]+810, 900, 500)
        self.mkUI()
        self.text = {k:"" for k in self.parent.local_cfg["toi"]["telescopes"]}
        self.flat_records = {}      # {tel: {item: {filtr: {"last": ISO|None}}}} z flat_overwatch

    def updateUI(self):
        if self.parent.telescope:
            self.tel_e.setText(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont("Courier New",9)
            font.setBold(True)
            self.tel_e.setFont(font)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")

            self.draw_flat_log()
            self.draw_flat_table(self.parent.active_tel)
            self.show()
            self.raise_()

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
        grid.addWidget(self.flat_table_t, 1, 0)

        self.tel_e = QLineEdit()
        self.tel_e.setReadOnly(True)
        grid.addWidget(self.tel_e, 0, 0,1,2)
        self.log_t = QTableWidget(0, 7)
        self.log_t.setHorizontalHeaderLabels(["DATE", "UT", "FILTER", "N", "EXP", "H_SUN", "ADU"])
        self.log_t.setShowGrid(False)
        self.log_t.verticalHeader().hide()
        self.log_t.verticalHeader().setDefaultSectionSize(10)
        self.log_t.setSelectionMode(QAbstractItemView.NoSelection)
        self.log_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_t.horizontalHeader().setStretchLastSection(True)
        self.log_t.setStyleSheet("background-color: rgb(235,235,235);")
        grid.addWidget(self.log_t, 1, 1)
        grid.setColumnStretch(1, 1)     # dodatkowa szerokosc okna idzie do logu, nie do tabeli
        self.setLayout(grid)

