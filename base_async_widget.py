import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Task
from dataclasses import dataclass
from typing import List, Coroutine, Dict
from PyQtX.QtGui import QStandardItem
from obcom.comunication.base_client_api import BaseClientAPI
from obcom.comunication.cycle_query import BaseCycleQuery
from qasync import QEventLoop
from util_functions.asyncio_util_functions import wait_for_psce

logger = logging.getLogger(__name__)


class BaseAsyncWidget(ABC):

    DEFAULT_GROUP_NAME = "default"

    def __init__(self, loop: QEventLoop = None, client_api: BaseClientAPI = None, **kwargs):
        self.loop: QEventLoop = loop
        self.client_api: BaseClientAPI = client_api
        self._background_tasks: Dict[str, List[BaseAsyncWidget.BackgroundTask]] = \
            {BaseAsyncWidget.DEFAULT_GROUP_NAME: []}
        self._subscriptions: List[BaseCycleQuery] = []
        self._groups_background_exercise: Dict[str, List[asyncio.Task]] = {BaseAsyncWidget.DEFAULT_GROUP_NAME: []}
        super().__init__(**kwargs)

    @dataclass
    class BackgroundTask:
        coro: Coroutine
        name: str = ""
        task: Task = None
        created: bool = False
        group: str = ""

        def __post_init__(self):
            pass

    @abstractmethod
    async def on_start_app(self):
        raise NotImplemented

    def add_background_task(self, coro: Coroutine, name: str = "", group: str = ""):
        group = BaseAsyncWidget.DEFAULT_GROUP_NAME if not group else group
        bt = self.BackgroundTask(name=name, coro=coro, group=group)
        self._background_tasks.setdefault(group, []).append(bt)

    async def run_background_tasks(self, group: str = ""):
        await self._run_all_background_task(group=group)

    async def _run_all_background_task(self, group: str = ""):
        if group:
            # run single group
            to_run = [group]
        else:
            # run all
            to_run = self._background_tasks.keys()

        if self.loop is None:
            logger.error(f"Background tasks cannot be started because loop was not found")
            raise RuntimeError
        for gr in to_run:
            for bt in self._background_tasks.get(gr, []):
                if not bt.created:
                    name = bt.name
                    co = bt.coro
                    # logger.info(f"Starting task: {name}")
                    t = self.loop.create_task(co, name=name)
                    bt.task = t
                    bt.created = True

    async def stop_background_tasks(self, group: str = ""):
        await self._stop_background_tasks(group=group)
        if not group:
            await self._stop_subscriptions()

    async def _stop_background_tasks(self, group: str = ""):
        if group:
            # stop single group
            to_stop = [group]
        else:
            # stop all
            to_stop = self._background_tasks.keys()

        for gr in to_stop:
            for bt in self._background_tasks.get(gr, []):
                t = bt.task
                if t and t in asyncio.all_tasks(self.loop) and not t.done():
                    t.cancel()
                    # logger.info(f'Cancel task: {t.get_name()}')

        for gr in to_stop:
            to_stop = []
            for bt in self._background_tasks.get(gr, []):
                if bt.task and bt.task in asyncio.all_tasks(self.loop):
                    to_stop.append(bt.task)
            if len(to_stop) > 0:
                done, pending = await asyncio.wait(to_stop, return_when=asyncio.ALL_COMPLETED, timeout=2.5)
                if len(pending) > 0:
                    logger.error(f"some of background tasks not stopped {pending}")

    async def _stop_subscriptions(self):
        for su in self._subscriptions:
            su.stop()
        time_to_close = 1
        for su in self._subscriptions:
            try:
                await wait_for_psce(su.stop_and_wait(),
                                    timeout=time_to_close)  # the task should finish in less than 0.5 seconds
                logger.debug(f'Ended subscription: {su.get_name()}')
            except asyncio.TimeoutError:
                logger.error(f"The subscription {su.get_name()} did not close in the required time: {time_to_close}s")

    async def run_method_in_background(self, coro: Coroutine, name: str = "", group: str = ""):
        """
        Start coroutine in background and left until it finished. After thad forgot about it.
        This method run some method once lather, is not necessary to wait for it.
        Only for method witch do short thing and finish, not for infinite loop.

        :param coro: coroutine
        :param name: name of task
        :param group: name of the group method
        """

        group = BaseAsyncWidget.DEFAULT_GROUP_NAME if not group else group

        async def background_exercise():
            logger.debug(f"Background exercise start {name}")
            await coro
            logger.debug(f"Background exercise finished {name}")

        def callback(task):
            self._groups_background_exercise.get(group).remove(task)

        t = asyncio.create_task(background_exercise(), name=name)
        self._groups_background_exercise.setdefault(group, []).append(t)
        # self._background_exercise.append(t)
        t.add_done_callback(callback)

    async def stop_background_methods(self, group: str = ""):
        """
        Stop all background methods (not background tasks)
        """
        if group:
            # cancel single group
            to_remove = [group]
        else:
            # cancel all
            to_remove = self._groups_background_exercise.keys()

        for gr in to_remove:
            for bt in self._groups_background_exercise.get(gr, []):
                bt.cancel()
        for gr in to_remove:
            # gather tasks with a timeout
            tasks = self._groups_background_exercise.get(gr, [])
            if len(tasks) > 0:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED, timeout=2.5)
                if len(pending) > 0:
                    logger.error(f"some of background methods not stopped {pending}")


class MetaAsyncWidgetQtWidget(type(QStandardItem), type(BaseAsyncWidget)):
    pass
