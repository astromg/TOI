#!/usr/bin/env python3

import asyncio

from ob.comunication.client import Client
from ocaboxapi import ClientAPI, Observatory
from serverish.messenger import Messenger


def main():
    client = Client(name="DefaultClient",host="192.168.7.37",port=5558)
    api = ClientAPI(client=client)
    asyncio.run(dodo(api))


async def dodo(api):
    await api.server_reload_nats_config()


    msg = Messenger()
    nats_opener = await msg.open(host="192.168.7.38", port=4222, wait=3)

    observatory_model = Observatory(client_name="TOI_Client",config_stream="tic.config.observatory")

    await observatory_model.load_client_cfg()

    observatory_model.connect(client=api)
    #print(observatory_model.get_client_configuration()[""])




if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print('program was stopped')