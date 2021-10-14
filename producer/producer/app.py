import json
import os
import sys
from aiohttp import web
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from producer.websocket import ExchangeSocketManager
from producer.producers import Producer

routes = web.RouteTableDef()


@routes.get('/start')
async def start_worker_handler(request):
    """ Start endpoint, will instruct the server to open a TCP connection to the Binance exchange

    :param request: request parameter - not needed
    :return: JSON payload
    """

    if not app.wcm.started:
        await app.start_worker()
    return web.json_response({'status': 'worker started'})


@routes.get('/stop')
async def stop_worker_handler(request):
    """ Stop endpoint, will instruct the server to close a TCP socket to the Binance exchange

    :param request: request parameter - not needed
    :return: JSON payload
    """
    await app.stop_worker()
    return web.json_response({'status': 'worker stopped'})


def kafka_input_quality_check(message_dict):
    """ Input data quality check before writing the JSON to the Kafka broker.
        Makes sure that we don't have any missing values and that bid and ask values
        are numeric

    :param message_dict: python dict which contains bid/ask spread
    :return: bolean result
    """

    # check bid and ask prices for missing values
    bid = message_dict.get('bid', None)
    ask = message_dict.get('ask', None)
    if bid is None or ask is None:
        return False
    # make sure that bid and ask prices are numeric
    if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
        return False
    return True


class Server(web.Application):
    """ Simple fully asynchronous Http web server built with aiohttp framework
    """

    def __init__(self):
        super().__init__()
        self.wcm = ExchangeSocketManager()
        self._pairs = ('btcusdt',)
        self._callback = self._produce
        self._topic = "price_changes1"
        self._producer = Producer({
            "bootstrap.servers": "kafka:9092",
            "acks": 0,
            "retries": 0
        })

    async def start_worker(self):
        """ Starts an instance web socket manager worker

        :return: None
        """
        for pair in self._pairs:
            await self.wcm.start_individual_symbol_book_ticker_socket(pair, self._callback)
        await self.wcm.run()

    async def stop_worker(self):
        """ Stops an instance web socket manager worker

        :return: None
        """
        await self.wcm.close()

    async def _produce(self, message):
        """ Parses the data stream returned from the TCP connection with the exchange
            creates a JSON payload for the Kafka producer and does the input data quality check

        :param message: Instanceeof the aiohttp Message class
        :return: None
        """
        message_dict = json.loads(message.data)
        key = message_dict.get('s')
        kafka_dict = dict()
        kafka_dict['bid'] = message_dict['b']
        kafka_dict['ask'] = message_dict['a']
        kafka_dict['pair'] = key
        kafka_dict['timestamp'] = str(datetime.now())
        value = json.dumps(kafka_dict)
        if kafka_input_quality_check(kafka_dict):
            self._producer.produce(topic=self._topic, key=key, value=value)
        else:
            print(f'Input {kafka_dict} has failed failed the Kafka input quality check')


if __name__ == '__main__':
    app = Server()
    app.add_routes(routes)
    web.run_app(app, port=8080)
