import asyncio
from data_server.websocket import ExchangeSocketManager


async def worker(pairs, callback):
    wcm = ExchangeSocketManager()
    for pair in pairs:
        await wcm.start_individual_symbol_book_ticker_socket(pair, callback)
    try:
        await wcm.run()
    finally:
        await wcm.close()
        await asyncio.sleep(10)
        print('exiting')


if __name__ == '__main__':
    pairs = ('btcusdt', 'ethusdt')
    asyncio.run(worker(pairs, print))
