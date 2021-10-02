import os
import sys
from aiohttp import web

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from producer.websocket import ExchangeSocketManager

routes = web.RouteTableDef()


@routes.get('/start')
async def start_worker_handler(request):
    if not app.wcm.started:
        await app.start_worker()
    return web.json_response({'status': 'worker started'})


@routes.get('/stop')
async def stop_worker_handler(request):
    await app.stop_worker()
    return web.json_response({'status': 'worker stopped'})


class Server(web.Application):

    def __init__(self):
        super().__init__()
        self.wcm = ExchangeSocketManager()
        self._pairs = ('btcusdt', 'ethusdt')
        self._callback = print

    async def start_worker(self):
        for pair in self._pairs:
            await self.wcm.start_individual_symbol_book_ticker_socket(pair, self._callback)
        await self.wcm.run()

    async def stop_worker(self):
        await self.wcm.close()


if __name__ == '__main__':
    app = Server()
    app.add_routes(routes)
    web.run_app(app, port=8080)
