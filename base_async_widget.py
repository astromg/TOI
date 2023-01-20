import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Coroutine

from PyQt5.QtGui import QStandardItem
from PyQt5.QtWidgets import QLineEdit
from ob.comunication.client_api import ClientAPI
from ob.ob_config import SingletonConfig
from qasync import QEventLoop
from config_service import Config as Cfg

logger = logging.getLogger(__name__)


# TODO uwaga żeby skonfigurować clienta to trzeba mu wetkać gdzieś plik config.yaml ale do domyślnego się nie dostane więc przez SingletonConfig trzeba


class BaseAsyncWidget(ABC):

    def __init__(self, loop: QEventLoop = None, client_api: ClientAPI = None, **kwargs):
        self.loop: QEventLoop = loop
        self.client_api: ClientAPI = client_api
        self._coros_to_run: List[tuple] = []
        self._background_task: list = []
        super().__init__(**kwargs)

    @abstractmethod
    async def task_starter(self):
        raise NotImplemented

    def add_background_task(self, coro: Coroutine, name: str = ""):
        self._coros_to_run.append((coro, name))

    async def updater(self, field: QLineEdit, address: str, time_of_data_tolerance=None, delay=None,
                      name='Unnamed subscription'):
        cq = await self.client_api.subscribe(address=address,
                                             time_of_data_tolerance=time_of_data_tolerance,
                                             delay=delay,
                                             name=name,
                                             max_missed_msg=-1)  # this creates 'cycle query' object
        cq.start()  # start retrieving
        try:
            while True:
                await asyncio.sleep(0)  # TODO to make sure it doesn't crash. remove it if it fails to update
                result = await cq.get_response()  # response is a list because it is possible to subscribe to multiple
                # values in one query. IT IS RECOMMENDED TO ONLY SUBSCRIPTION FOR ONE VALUE AT A TIME
                logger.info(f"updater named {name} retrieve message")
                if result and result[0].value:
                    logger.info(f"updater named {name} change field value")
                    # todo Pytanie co jak zostanie przerwane połączenie to wartości mają się nie aktualizować czy wyświetlić błąd?
                    field.setText(f"{result[0].value.v}")  # update field in GUI
        finally:
            await cq.stop_and_wait()  # it is recommended to use this method instead of the usual Stop() because it
            # waits for the query to finish and the stop method only puts it in a closing state which can take some
            # time and must be terminated before the end of the program

    @staticmethod
    def get_address(method_name: str):
        address = Cfg.get("OCA_ADDRESS_DICT", {}).get(method_name, None)
        return address

    async def _run_all_background_task(self):
        # todo dać zabezpieczenie na loop gdyby było None
        while self._coros_to_run:
            co, name = self._coros_to_run.pop()
            logger.info(f"Starting task: {name}")
            t = self.loop.create_task(co, name=name)
            self._background_task.append(t)

    async def _stop_background_tasks(self):
        for t in self._background_task:
            if t and t in asyncio.all_tasks(self.loop) and not t.done():
                t.cancel()
                logger.info(f'Cancel task: {t.get_name()}')

        # todo musi być jakiś timeout na taski które nie chcą się zamknąć można użyć tej rakowej funkcji wait_for
        for t in self._background_task:
            if t and t in asyncio.all_tasks(self.loop):
                logger.info(f'Wait for end task: {t.get_name()}')
                await t
                logger.info(f'Ended task: {t.get_name()}')


class MetaAsyncWidgetQtWidget(type(QStandardItem), type(BaseAsyncWidget)):
    pass
