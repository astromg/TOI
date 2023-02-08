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
from ob.comunication.cycle_query import BaseCycleQuery
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
        self._subscriptions: List[BaseCycleQuery] = []
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

    def add_subscription(self, address: str, time_of_data_tolerance=None, delay=None,
                         name='Unnamed subscription', callback_method: list = None, async_callback_method: list = None):
        callback_method = [] if callback_method is None else callback_method
        async_callback_method = [] if async_callback_method is None else async_callback_method
        if not isinstance(callback_method, list) or not isinstance(async_callback_method, list):
            logger.error("as a callback, either a list of methods or None should be given.")
            raise RuntimeError
        if callback_method and async_callback_method:
            logger.error("No callback method was specified. You cannot start a subscription that does not affect "
                         "the operation of the application.")
            raise RuntimeError

        async def start_subscription():
            cq = await self.client_api.subscribe(address=address,
                                                 time_of_data_tolerance=time_of_data_tolerance,
                                                 delay=delay,
                                                 name=name,
                                                 max_missed_msg=-1)
            for m in callback_method:
                cq.add_callback_method(method=m)
            for m in async_callback_method:
                cq.add_callback_async_method(method=m)
            self._subscriptions.append(cq)
            cq.start()

        self.add_background_task(start_subscription())

    def add_subscription_client_side(self, address: str, time_of_data_tolerance=None, delay=None,
                                     name='Unnamed subscription client side', callback_method: list = None,
                                     async_callback_method: list = None):
        """Warning! Is a special client-side subscription."""
        callback_method = [] if callback_method is None else callback_method
        async_callback_method = [] if async_callback_method is None else async_callback_method
        if not isinstance(callback_method, list) or not isinstance(async_callback_method, list):
            logger.error("as a callback, either a list of methods or None should be given.")
            raise RuntimeError
        if callback_method and async_callback_method:
            logger.error("No callback method was specified. You cannot start a subscription that does not affect "
                         "the operation of the application.")
            raise RuntimeError

        async def start_subscription():
            cq = await self.client_api.send_cycle_multipart(address=address,
                                                            time_of_data_tolerance=time_of_data_tolerance,
                                                            delay=delay,
                                                            name=name,
                                                            max_missed_msg=-1,
                                                            log_missed_msg=True)  # this creates 'cycle query' object
            for m in callback_method:
                cq.add_callback_method(method=m)
            for m in async_callback_method:
                cq.add_callback_async_method(method=m)
            self._subscriptions.append(cq)
            cq.start()

        self.add_background_task(start_subscription())

    @staticmethod
    def update_field_callback(field, name="Default callback"):
        async def callback(result):
            if result and result[0].value:
                logger.info(f"updater named {name} change field value")
                tex_to_put = result[0].value.v
                field.setText(f"{tex_to_put}")  # update field in GUI

        return callback

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

    async def put_base_request(self, address: str, time_of_data: float or None = None,
                               time_of_data_tolerance: float or None = None,
                               parameters_dict: dict = None, no_wait=True, action: str = ""):
        try:
            response = await self.client_api.put_async(address=address, time_of_data_tolerance=time_of_data_tolerance,
                                                       time_of_data=time_of_data, parameters_dict=parameters_dict,
                                                       no_wait=no_wait)
            if response and response.value and response.value.v is True:
                logger.info(f"Successfully {action if action else f'call {address}'}")
            else:
                logger.info(f"Can not {action if action else f'call {address}'}: Normal")
        except CommunicationRuntimeError:
            logger.info(f"Can not {action if action else f'call {address}'}: CommunicationRuntimeError")
        except CommunicationTimeoutError:
            logger.info(f"Can not {action if action else f'call {address}'}: CommunicationTimeoutError")
        except Exception as e:
            logger.error(f"Unexpected error when {action if action else f'call {address}'}: {e}")

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
            bt.created = True

    async def stop_background_tasks(self):
        await self._stop_background_tasks()
        await self._stop_subscriptions()

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
                except asyncio.CancelledError:
                    pass

    async def _stop_subscriptions(self):
        for su in self._subscriptions:
            su.stop()
        time_to_close = 1
        for su in self._subscriptions:
            try:
                await wait_for_psce(su.stop_and_wait(),
                                    timeout=time_to_close)  # the task should finish in less than 0.5 seconds
                logger.info(f'Ended subscription: {su.get_name()}')
            except asyncio.TimeoutError:
                logger.error(f"The subscription {su.get_name()} did not close in the required time: {time_to_close}s")


class MetaAsyncWidgetQtWidget(type(QStandardItem), type(BaseAsyncWidget)):
    pass
