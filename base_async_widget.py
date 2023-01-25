import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Task
from dataclasses import dataclass
from typing import List, Coroutine

from PyQt5.QtGui import QStandardItem
from PyQt5.QtWidgets import QLineEdit
from ob.comunication.client_api import ClientAPI
from ob.comunication.comunication_error import CommunicationRuntimeError, CommunicationTimeoutError
from qasync import QEventLoop
from config_service import Config as Cfg
from util_functions.asyncio_util_functions import wait_for_psce

logger = logging.getLogger(__name__)


# TODO uwaga żeby skonfigurować clienta to trzeba mu wetkać gdzieś plik config.yaml ale do domyślnego się nie dostane więc przez SingletonConfig trzeba


class BaseAsyncWidget(ABC):

    def __init__(self, loop: QEventLoop = None, client_api: ClientAPI = None, **kwargs):
        self.loop: QEventLoop = loop
        self.client_api: ClientAPI = client_api
        self._background_tasks: List[BaseAsyncWidget.BackgroundTask] = []
        super().__init__(**kwargs)

    @dataclass
    class BackgroundTask:
        coro: Coroutine
        name: str = ""
        task: Task = None
        created: bool = False

        def __post_init__(self):
            pass

    @abstractmethod
    async def on_start_app(self):
        raise NotImplemented

    def add_background_task(self, coro: Coroutine, name: str = ""):
        self._background_tasks.append(self.BackgroundTask(name=name, coro=coro))

    async def subscriber(self, field: QLineEdit, address: str, time_of_data_tolerance=None, delay=None,
                         name='Unnamed subscription', response_processor=None):
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
                    tex_to_put = result[0].value.v
                    if response_processor and callable(response_processor):
                        tex_to_put = response_processor(result)

                    field.setText(f"{tex_to_put}")  # update field in GUI
        except CommunicationRuntimeError as e:
            raise
        finally:
            await cq.stop_and_wait()  # it is recommended to use this method instead of the usual Stop() because it
            # waits for the query to finish and the stop method only puts it in a closing state which can take some
            # time and must be terminated before the end of the program

    async def get_request(self, address: str, time_of_data: float or None = None,
                          time_of_data_tolerance: float or None = None,
                          parameters_dict: dict = None):
        # todo dokonczyc
        try:
            response = await self.client_api.get_async(address=address,
                                                       time_of_data=time_of_data,
                                                       time_of_data_tolerance=time_of_data_tolerance,
                                                       parameters_dict=parameters_dict)
            return response.value
        except CommunicationRuntimeError:
            pass
        except CommunicationTimeoutError:
            pass
        return None

    @staticmethod
    def get_address(method_name: str):
        address = Cfg.get("OCA_ADDRESS_DICT", {}).get(method_name, None)
        return address

    async def run_background_tasks(self):
        await self._run_all_background_task()

    async def _run_all_background_task(self):
        if self.loop is None:
            logger.error(f"Background tasks cannot be started because loop was not found")
            raise RuntimeError
        for bt in self._background_tasks:
            name = bt.name
            co = bt.coro
            logger.info(f"Starting task: {name}")
            t = self.loop.create_task(co, name=name)
            bt.task = t

    async def stop_background_tasks(self):
        await self._stop_background_tasks()

    async def _stop_background_tasks(self):
        for bt in self._background_tasks:
            t = bt.task
            if t and t in asyncio.all_tasks(self.loop) and not t.done():
                t.cancel()
                logger.info(f'Cancel task: {t.get_name()}')

        time_to_close = 0.5
        for bt in self._background_tasks:
            t = bt.task
            if t and t in asyncio.all_tasks(self.loop):
                logger.info(f'Wait for end task: {t.get_name()}')
                try:
                    await wait_for_psce(t, timeout=time_to_close)  # the task should finish in less than 0.5 seconds
                    logger.info(f'Ended task: {t.get_name()}')
                except asyncio.TimeoutError:
                    logger.error(f"The task {t.get_name()} did not close in the required time: {time_to_close}s")


class MetaAsyncWidgetQtWidget(type(QStandardItem), type(BaseAsyncWidget)):
    pass
