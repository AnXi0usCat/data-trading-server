import asyncio
import aiohttp


class ExchangeSocketManager:

    STREAM_URL = 'wss://stream.binance.com:9443/ws/'

    def __init__(self):
        self._conns = {}
        self._callbacks = {}
        self._session = aiohttp.ClientSession()
        self.started = False

    async def _start_socket(self, path, callback):
        """ Initiates a socket connection to the exchange

        :param path: connection endooint
        :param callback: a function that will be executed on a received message
        """
        # create anew session if already closed
        if self._session.closed:
            self._session = aiohttp.ClientSession()

        ws = await self._session.ws_connect(self.STREAM_URL + path, autoping=True)

        self._conns[path] = ws
        self._callbacks[path] = callback

    async def _stop_socket(self, conn_key):
        """ Closes a connection to the exchange

        :param conn_key: connection identifier
        """
        print(f'closing socket connection {conn_key}')
        await self._session.close()
        del self._conns[conn_key], self._callbacks[conn_key]

    async def _listen(self, ws, callback):
        """ listens for the incoming messages from the exchange
        and processes them with the supplied callback

        :param ws: web socket object
        :param callback: a fucntion which is executed on a received message
        """
        async for msg in ws:
            if msg.type in (aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR):
                await ws.close()
                break
            else:
                callback(msg)

    async def start_individual_symbol_book_ticker_socket(self, symbol, callback):
        """
        Pushes any update to the best bid or ask's price or quantity in real-time for a specified symbol.
        Stream Name: <symbol>@bookTicker
        Update Speed: Real-time
        :param callback: your function to handle the message
        .. code-block:: python
        {
          "u":400900217,     // order book updateId
          "s":"BNBUSDT",     // symbol
          "b":"25.35190000", // best bid price
          "B":"31.21000000", // best bid qty
          "a":"25.36520000", // best ask price
          "A":"40.66000000"  // best ask qty
        }
        """
        await self._start_socket(f'{symbol.lower()}@bookTicker', callback)

    async def run(self):
        """ Start listening to the messages from the exchange

        """
        await asyncio.gather(
            *[
                self._listen(v, self._callbacks.get(k, None))
                for k, v in self._conns.items()
            ]
        )

    async def close(self):
        # abort if connections already closed
        if len(self._conns) == 0:
            return

        keys = set(self._conns.keys())
        for key in keys:
            await self._stop_socket(key)

        self._conns = {}
        self._callbacks = {}
        self.started = False
