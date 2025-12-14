#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------
import asyncio
import logging

import qasync as qs
from PyQtX import QtGui
from PyQtX.QtCore import Qt
from PyQtX.QtWidgets import QWidget, QLabel, QCheckBox, QLineEdit, QPushButton, QGridLayout, QFrame, QComboBox
from obcom.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError

from base_async_widget import BaseAsyncWidget, MetaAsyncWidgetQtWidget

logger = logging.getLogger(__name__)


class PeryphericalGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):

    def __init__(self, parent, loop: qs.QEventLoop = None, client_api=None):
        super().__init__(loop=loop, client_api=client_api)
        self.subscriber_delay = 1
        self.subscriber_time_of_data_tolerance = 0.5
        self.parent = parent
        self.font = QtGui.QFont("Arial", 11)
        # ["V", "I", "u", "v", "b"]
        self.filters_map: dict = {}
        self.mkUI()
        self.update_()

    # =================== OKNO GLOWNE ====================================
    def mkUI(self):
        self.setWindowTitle('Telescope Perypherical Controll')
        # self.setWindowIcon(QtGui.QIcon('icon.png'))

        w = 0
        grid = QGridLayout()

        self.telCovers_l = QLabel("MIRROR COVERS: ")

        self.telCovers_e = QLineEdit()
        self.telCovers_e.setReadOnly(True)
        self.telCovers_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.add_subscription(address=self.get_address('get_covercalibrator_coverstate'),
                              name='telCovers_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self._update_covercalibrator_status_callback(self.telCovers_e,
                                                                               name='telCovers_e')])

        self.telCovers_c = QCheckBox("")
        self.telCovers_c.setChecked(False)
        self.telCovers_c.setLayoutDirection(Qt.RightToLeft)
        # self.telCovers_c.setStyleSheet("background-color: yellow")
        self.telCovers_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.telCovers_c.stateChanged.connect(lambda: self._covers_checkbox_change(self.telCovers_c))

        grid.addWidget(self.telCovers_l, w, 0)
        grid.addWidget(self.telCovers_e, w, 1)
        grid.addWidget(self.telCovers_c, w, 3)

        w = w + 1
        self.telM3_l = QLabel("M3: ")

        self.telM3_e = QLineEdit()
        self.telM3_e.setReadOnly(True)
        self.telM3_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.telM3_e.setText("(TODO)")

        self.telM3_s = QComboBox()
        self.telM3_s.addItems(["Imager", "Spectro", "empty"])

        self.telM3_p = QPushButton('SET')

        grid.addWidget(self.telM3_l, w, 0)
        grid.addWidget(self.telM3_e, w, 1)
        grid.addWidget(self.telM3_s, w, 2)
        grid.addWidget(self.telM3_p, w, 3)

        w = w + 1
        self.telFilter_l = QLabel("FILTER: ")

        self.telFilter_e = QLineEdit()
        self.telFilter_e.setReadOnly(True)
        self.telFilter_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.add_subscription(address=self.get_address('get_filterwheel_position'),
                              name='telFilter_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self._update_filterwheel_position_callback(self.telFilter_e,
                                                                             name='telFilter_e')])

        self.telFilter_s = QComboBox()
        self.add_background_task(
            self._update_filter_list_gui(self.telFilter_s,
                                         self.telFilter_e))  # pobiera liste filtrów z servera i aktualizuje w tle

        self.telFilter_p = QPushButton('SET')
        self.telFilter_p.clicked.connect(lambda: self._set_filter_btn_clicked(self.telFilter_s))

        grid.addWidget(self.telFilter_l, w, 0)
        grid.addWidget(self.telFilter_e, w, 1)
        grid.addWidget(self.telFilter_s, w, 2)
        grid.addWidget(self.telFilter_p, w, 3)

        w = w + 1
        self.telFocus_l = QLabel("FOCUS: ")

        self.telFocus_e = QLineEdit()
        self.telFocus_e.setReadOnly(True)
        self.telFocus_e.setStyleSheet("background-color: rgb(233, 233, 233); color: black;")
        self.add_subscription(address=self.get_address('get_focuser_position'),
                              name='telFocus_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self.update_field_callback(self.telFocus_e,
                                                             name='telFocus_e')])

        self.telAutoFocus_c = QCheckBox("AUTO: ")
        self.telAutoFocus_c.setChecked(True)
        self.telAutoFocus_c.setLayoutDirection(Qt.RightToLeft)
        # self.mntCovers_c.setStyleSheet("background-color: yellow")
        self.telAutoFocus_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")

        grid.addWidget(self.telFocus_l, w, 0)
        grid.addWidget(self.telFocus_e, w, 1)
        grid.addWidget(self.telAutoFocus_c, w, 3)

        w = w + 1

        self.setFocus_e = QLineEdit()
        self.setFocus_p = QPushButton('SET')
        self.setFocus_p.clicked.connect(lambda: self._set_focus_btn_clicked(self.setFocus_e))

        grid.addWidget(self.setFocus_e, w, 2)
        grid.addWidget(self.setFocus_p, w, 3)

        w = w + 1
        self.line_l = QFrame()
        self.line_l.setFrameShape(QFrame.HLine)
        self.line_l.setFrameShadow(QFrame.Raised)
        grid.addWidget(self.line_l, w, 0, 1, 6)

        # grid.setColumnMinimumWidth(6,100)
        # grid.setColumnMinimumWidth(8,100)
        # grid.setColumnMinimumWidth(10,100)

        # grid.setSpacing(10)

        self.setLayout(grid)

    async def on_start_app(self):
        await self.run_background_tasks()

    def update_(self):
        pass

    @staticmethod
    def _update_covercalibrator_status_callback(field, name="Covercalibrator status callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                val = result[0].value.v
                if val == 1:
                    tex_to_put = "Close"
                elif val == 2:
                    tex_to_put = "Moving"
                elif val == 3:
                    tex_to_put = "Open"
                elif val == 4:
                    tex_to_put = "Shutter status error"
                else:
                    tex_to_put = f"{val}"
                field.setText(tex_to_put)  # update field in GUI

        return callback

    @qs.asyncSlot()
    async def _covers_checkbox_change(self, checkbox: QCheckBox):
        """Method for covers checkbox changed"""
        state = checkbox.isChecked()
        if state:
            address = self.get_address("put_covercalibrator_open")
            action = "open"
        else:
            address = self.get_address("put_covercalibrator_close")
            action = "close"

        checkbox.blockSignals(True)  # Block signals so that you don't call this method recursively
        checkbox.setEnabled(False)  # avoid check again before react for first toggle
        try:
            response = await self.client_api.put_async(address=address, no_wait=False)
            if response and response.value and response.status and (response.value.v is not None):
                logger.info(f"Successfully covers  {action}")
            else:
                logger.info(f"Can not {action} covers: Normal")
                checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except CommunicationRuntimeError:
            logger.info(f"Can not {action} covers: CommunicationRuntimeError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back

        except CommunicationTimeoutError:
            logger.info(f"Can not {action} covers: CommunicationTimeoutError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            checkbox.setEnabled(True)  # allow toggle
            checkbox.blockSignals(False)  # unblock signals

    async def _load_filters_list(self):
        filters_list = await self.get_request(self.get_address("get_filterwheel_names"), action="Get list of filters")
        if filters_list:
            for i, fi in enumerate(filters_list):
                self.filters_map[i] = fi

    async def _update_filter_list_gui(self, field: QComboBox, field2: QLineEdit):
        """
        :param field: A field with a list of all filters
        :param field2: The field where the name of the current filter is displayed
        """
        await self._load_filters_list()
        field.addItems(self.filters_map.values())
        # kod poniżej odpowiada za przetłumaczenie nr filtra na jego nazwe przy piereszym pobraniu nazw filtrów
        try:
            field2.setText(self.filters_map.get(int(field2.text())))
        except Exception:
            pass

    @qs.asyncSlot()
    async def _set_filter_btn_clicked(self, field_source: QComboBox):
        """Method for 'set' filter button"""
        try:
            name_filter = field_source.currentText()
            filter_nr = None
            for k, v in self.filters_map.items():
                if v == name_filter:
                    filter_nr = k
            value = int(filter_nr)
        except (ValueError, TypeError):
            logger.warning(f"Can not set filter because can not parse '{field_source.currentText()}' to int")
            return
        await self.put_base_request(address=self.get_address("put_filterwheel_position"),
                                    parameters_dict={'Position': value}, no_wait=False,
                                    action="abort slew alpaca")

    def _update_filterwheel_position_callback(self, field, name="Filterwheel position callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                val = result[0].value.v
                try:
                    val = int(val)
                    if val == -1:
                        tex_to_put = "Changing"
                    else:
                        tex_to_put = f"{self.filters_map.get(val, val)}"
                except Exception as e:
                    tex_to_put = f"{val}"
                field.setText(tex_to_put)  # update field in GUI

        return callback

    @qs.asyncSlot()
    async def _set_focus_btn_clicked(self, field_source: QLineEdit):
        """Method for 'set' focus button"""
        try:
            value = int(field_source.text())
        except ValueError:
            logger.warning(f"Can not set focus because can not parse {field_source.text()} to int")
            return
            # todo czy ma być jakaś obsługa błędów? to już po stronie QLabelEdit chyba np jakieś zaznaczanie na czerwono jak jest żle
        await self.put_base_request(address=self.get_address("put_focuser_move"),
                                    parameters_dict={'Position': value}, no_wait=False,
                                    action="move dome in alpaca")
