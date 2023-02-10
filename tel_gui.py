#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------
import datetime
import logging

import dateutil.parser
import qasync as qs
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QCheckBox, QTextEdit, QLineEdit, QPushButton, QGridLayout, QFrame
from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError

from base_async_widget import MetaAsyncWidgetQtWidget, BaseAsyncWidget

logger = logging.getLogger(__name__)


class TelGui(QWidget, BaseAsyncWidget, metaclass=MetaAsyncWidgetQtWidget):
    def __init__(self, parent, loop: qs.QEventLoop = None, client_api=None):
        super().__init__(loop=loop, client_api=client_api)
        self.subscriber_delay = 1
        self.subscriber_time_of_data_tolerance = 0.5
        self.parent = parent
        self.font = QtGui.QFont("Arial", 11)

        self.mkUI()
        self.update_()

        self.Exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())  # todo przyjżeć się jeszcze raz temu

    def update_(self):
        # self.mntUt_e.setText("21:34:17")
        self.mntStat_e.setText("ready (TODO)")
        # self.domeStat_e.setText("moving")
        self.programStat_e.setText("Cep32 (TODO)")
        # self.mntCovers_e.setText("Closed")
        # self.domeShutter_e.setText("Closed")
        self.telLights_e.setText("Off (TODO)")

    # =================== OKNO GLOWNE ====================================
    def mkUI(self):
        self.setWindowTitle('Telescope GUI')
        # self.setWindowIcon(QtGui.QIcon('icon.png'))

        self.mntStat_l = QLabel("TELESCOPE STATUS: ")
        self.mntStat_e = QLineEdit()
        self.mntStat_e.setReadOnly(True)

        self.programStat_l = QLabel("PROGRAM STATUS: ")
        self.programStat_e = QLineEdit()
        self.programStat_e.setReadOnly(True)

        self.mntUt_l = QLabel("UT: ")
        self.mntUt_e = QLineEdit()
        self.mntUt_e.setReadOnly(True)
        self.add_subscription(address=self.get_address('get_telescope_utcdate'),
                              name='tel_mntUt_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[self._update_utcdate_callback(self.mntUt_e, name='tel_mntUt_e')])

        self.mntCovers_c = QCheckBox("MIRROR COVERS: ")
        self.mntCovers_c.setChecked(False)
        self.mntCovers_c.setLayoutDirection(Qt.RightToLeft)
        # self.mntCovers_c.setStyleSheet("background-color: yellow")
        self.mntCovers_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.mntCovers_c.stateChanged.connect(lambda: self._covers_checkbox_change(self.mntCovers_c))

        self.mntCovers_e = QLineEdit()
        self.mntCovers_e.setReadOnly(True)
        self.add_subscription(address=self.get_address('get_covercalibrator_coverstate'),
                              name='tel_mntCovers_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self._update_covercalibrator_status_callback(self.mntCovers_e, name='tel_mntCovers_e')])
        # dome

        self.domeStat_l = QLabel("DOME STATUS: ")
        self.domeStat_e = QLineEdit()
        self.domeStat_e.setReadOnly(True)
        self.add_subscription(address=self.get_address('get_dome_status'),
                              name='tel_domeStat_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self._update_dome_status_callback(self.domeStat_e, name='tel_domeStat_e')])

        self.domeShutter_c = QCheckBox("DOME SHUTTER: ")
        self.domeShutter_c.setChecked(False)
        self.domeShutter_c.setLayoutDirection(Qt.RightToLeft)
        self.domeShutter_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOn.png)}::indicator:unchecked {image: url(./Icons/SwitchOff.png)}")
        self.domeShutter_c.stateChanged.connect(lambda: self._shutter_checkbox_change(self.domeShutter_c))

        self.domeShutter_e = QLineEdit()
        self.domeShutter_e.setReadOnly(True)
        self.add_subscription(address=self.get_address('get_dome_shutterstatus'),
                              name='tel_domeShutter_e',
                              delay=self.subscriber_delay,
                              time_of_data_tolerance=self.subscriber_time_of_data_tolerance,
                              async_callback_method=[
                                  self.update_field_callback(self.domeShutter_e, name='tel_domeShutter_e')])
        # peripheries

        self.telLights_c = QCheckBox("LIGHTS: ")
        self.telLights_c.setChecked(False)
        self.telLights_c.setLayoutDirection(Qt.RightToLeft)
        self.telLights_c.setStyleSheet(
            "QCheckBox::indicator:checked {image: url(./Icons/SwitchOnYellow.png)}::indicator:unchecked {image: url(./Icons/SwitchOffGrey.png)}")

        self.telLights_e = QLineEdit()
        self.telLights_e.setReadOnly(True)

        self.Stop_p = QPushButton('EMERGENCY STOP')
        self.Exit_p = QPushButton('Exit')

        # -------- OKNO MSG ----------------------
        self.msg_e = QTextEdit()
        self.msg_e.setReadOnly(True)
        self.msg_e.setFrameStyle(QFrame.Raised)
        self.msg_e.setStyleSheet("background-color: rgb(233, 233, 233);")

        grid = QGridLayout()

        w = 0

        grid.addWidget(self.mntUt_l, w, 0)
        grid.addWidget(self.mntUt_e, w, 1)

        w = w + 1
        grid.addWidget(self.mntStat_l, w, 0)
        grid.addWidget(self.mntStat_e, w, 1)

        w = w + 1
        grid.addWidget(self.domeStat_l, w, 0)
        grid.addWidget(self.domeStat_e, w, 1)

        w = w + 1
        grid.addWidget(self.programStat_l, w, 0)
        grid.addWidget(self.programStat_e, w, 1)

        w = w + 1
        grid.addWidget(self.mntCovers_c, w, 0)
        grid.addWidget(self.mntCovers_e, w, 1)

        w = w + 1
        grid.addWidget(self.domeShutter_c, w, 0)
        grid.addWidget(self.domeShutter_e, w, 1)

        w = w + 1
        grid.addWidget(self.telLights_c, w, 0)
        grid.addWidget(self.telLights_e, w, 1)

        w = w + 1
        grid.addWidget(self.msg_e, w, 0, 3, 2)

        w = w + 3
        grid.addWidget(self.Stop_p, w, 0, 1, 2)
        w = w + 1
        grid.addWidget(self.Exit_p, w, 1)

        # grid.setColumnMinimumWidth(6,100)
        # grid.setColumnMinimumWidth(8,100)
        # grid.setColumnMinimumWidth(10,100)

        # grid.setSpacing(10)

        self.setLayout(grid)

    async def on_start_app(self):
        await self.run_background_tasks()

    @qs.asyncClose
    async def closeEvent(self, event):
        await self.stop_background_tasks()
        super().closeEvent(event)

    @staticmethod
    def _update_utcdate_callback(field, name="Default callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                tex_to_put = result[0].value.v
                try:
                    date = dateutil.parser.isoparse(tex_to_put)
                    tex_to_put = date.strftime("%H:%M:%S")
                except Exception as e:
                    logger.error(f"Error when parse date: Error: {e}")
                field.setText(f"{tex_to_put}")  # update field in GUI
        return callback

    @staticmethod
    def _update_dome_status_callback(field, name="Dome status callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                val = result[0].value.v
                if val == 0:
                    tex_to_put = "Open"
                elif val == 1:
                    tex_to_put = "Closed"
                elif val == 2:
                    tex_to_put = "Opening"
                elif val == 3:
                    tex_to_put = "Closing"
                elif val == 4:
                    tex_to_put = "Shutter status error"
                else:
                    tex_to_put = f"{val}"
                field.setText(tex_to_put)  # update field in GUI
        return callback

    @qs.asyncSlot()
    async def _shutter_checkbox_change(self, checkbox: QCheckBox):
        """Method for shutter checkbox changed"""
        state = checkbox.isChecked()
        if state:
            address = self.get_address("put_dome_shutter_open")
            action = "open"
        else:
            address = self.get_address("put_dome_shutter_close")
            action = "close"

        checkbox.blockSignals(True)  # Block signals so that you don't call this method recursively
        checkbox.setEnabled(False)  # avoid check again before react for first toggle
        try:
            response = await self.client_api.put_async(address=address, no_wait=False)
            if response and response.value and response.status and (response.value.v is not None):
                logger.info(f"Successfully shutter {action}")
            else:
                logger.info(f"Can not {action} shutter: Normal")
                checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except CommunicationRuntimeError:
            logger.info(f"Can not {action} shutter: CommunicationRuntimeError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back

        except CommunicationTimeoutError:
            logger.info(f"Can not {action} shutter: CommunicationTimeoutError")
            checkbox.setChecked(not state)  # can not change dome status so toggle checkbox back
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            checkbox.setEnabled(True)  # allow toggle
            checkbox.blockSignals(False)  # unblock signals

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
