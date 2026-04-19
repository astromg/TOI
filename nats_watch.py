#!/usr/bin/env python3

import copy
import yaml
import argparse
import logging
import asyncio
import datetime
import time
import copy

import os
import sys
import pwd
import socket

from serverish.messenger import Messenger, single_read, get_reader, get_journalreader
from serverish.messenger.msg_publisher import MsgPublisher, get_publisher
from serverish.messenger.msg_journal_pub import MsgJournalPublisher, get_journalpublisher, JournalEntry

logger = logging.getLogger('main')

class main_app():
    def __init__(self, args):
        super().__init__()

        self.pwd = os.path.dirname(os.path.abspath(__file__))

        self.args = args

        self.app_name = sys.argv[0]
        host = socket.gethostname()
        user = pwd.getpwuid(os.getuid())[0]
        self.myself = f'{user}@{host}'

        # definiujemy jak bedziemy spamowac w terminalu
        if self.args.log_level:
            loglevel = args.log_level
        else:
            loglevel = "INFO"
        logging.basicConfig(level=loglevel,format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
        logger.info(f'OV logging level: {loglevel}')

        self.wind_max = 0
        asyncio.run((self.starting_task()))


    async def starting_task(self):
        # otwieramy komunikacje po NATS-ach
        nats_host = "nats.oca.lan"
        nats_port = 4222

        msg = Messenger()
        nats_opener = await msg.open(host=nats_host, port=nats_port, wait=3)
        try:
            if nats_opener:
                await nats_opener
            if msg.is_open:
                pass
            else:
                logger.error(f"Can't connect to NATS {nats_host}:{nats_port} Application stopped!")
                return
        except asyncio.TimeoutError:
            logger.error(f"Can't connect to NATS {nats_host}:{nats_port} Application stopped!")
            return

        # wczytujemy konfiguracje OCA
        nats_cfg = await single_read(f'tic.config.observatory')
        self.nats_cfg = nats_cfg[0]
        logger.info("OCA NATS configuration loaded")



        # definijemy wszytskie asynchroniczne zadania i je dokladamy do petli asyncio
        tasks = []
        tasks.append(asyncio.create_task(self.boring_loop()))
        #tasks.append(asyncio.create_task(self.reader_weather_davis()))
        tasks.append(asyncio.create_task(self.test()))

        await self.safety_run_tasks(tasks)



    # no taka petla zawsze do czegos sie przeciez przyda
    async def boring_loop(self):
        logger.info('Boring loop started')
        while True:
            await asyncio.sleep(1)
            #logger.info('Ping')




    ######### WEATHER ###################


    async def test(self):
        try:
            time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)  # do konfiguracji
            reader = get_reader('tic.status.zb08.toi.flat', deliver_policy='by_start_time',opt_start_time=time)
            #reader = get_reader('tic.status.jk15.access_grantor.safety_cutoff_state', deliver_policy='last')
            async for data, meta in reader:
                tmp = meta
                print(tmp)

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION reader_weather_davis: {e}')

    async def reader_weather_davis(self):
        try:
            t0 = datetime.datetime.now() - datetime.timedelta(hours=9)
            reader = get_reader('telemetry.weather.davis', deliver_policy='by_start_time',opt_start_time=t0)
            async for data, meta in reader:
                weather = data['measurements']


                if self.wind_max < float(weather["wind_ms"]):
                    self.wind_max = float(weather["wind_ms"])

                print(data["ts"], weather["wind_10min_ms"], weather["wind_ms"], weather["rain_day_mm"],self.wind_max)

                # ['temperature_C', 'humidity', 'wind_dir_deg', 'wind_ms', 'wind_10min_ms', 'pressure_Pa', 'bar_trend', 'rain_mm', 'rain_day_mm', 'indoor_temperature_C', 'indoor_humidity']

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception as e:
            logger.warning(f'EXCEPTION reader_weather_davis: {e}')




    ##### inne metody ##############



    async def safety_run_tasks(self,tasks):
        """
        ERNEST
        Method for safety run multiple tasks or coroutines
        :param tasks: list tasks or coroutines
        """
        task_list = []
        logger.info(f"Try run list of task: {len(tasks)}")
        try:
            for t in tasks:
                # ensure_future - if t is task then never happened, but if is just coroutine (async function) then make
                # task from it like create_task
                new_task = asyncio.ensure_future(t)
                task_list.append(new_task)
                logger.info(f"Created task {new_task.get_name()}")
            try:
                logger.info(f"Waiting for tasks")
                await asyncio.gather(*[asyncio.shield(t) for t in task_list], return_exceptions=True)
                logger.info(f"All tasks done")
            except asyncio.CancelledError:
                logger.info(f"Program was canceled")
                pass
            except KeyboardInterrupt:
                logger.info(f"Program was stop by KeyboardInterrupt")
                raise
        finally:
            if not task_list:
                logger.info(f"No task to cancel")
            else:
                logger.info(f"Closing all tasks")
                for t in task_list:
                    t.cancel()
                try:
                    logger.info(f"Start waiting for end task after close")
                    done, pending = await asyncio.wait(task_list, timeout=1)
                    logger.info(f"Task was stopped: {len(done)}/{len(task_list)}")
                    if pending:
                        logger.error(f"Task was not stopped for some reason: {len(pending)}/{len(task_list)}")
                except asyncio.CancelledError:  # probably should never happened
                    logger.info(f"Waiting for task end was canceled")



def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('--log_level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='loging level')
    #argparser.add_argument('--reset_agregator', action='store_true', help='use if new telescope added, or subject is empty')

    args = argparser.parse_args()
    app = main_app(args)

