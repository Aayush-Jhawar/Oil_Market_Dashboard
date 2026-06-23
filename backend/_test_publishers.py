import asyncio
import logging
from main import _signals_publisher, _paper_trading_publisher, ws_manager

logging.basicConfig(level=logging.DEBUG)

class MockWS:
    async def broadcast(self, payload):
        print("BROADCAST:", payload)

ws_manager.broadcast = MockWS().broadcast

async def run_test():
    task1 = asyncio.create_task(_signals_publisher())
    task2 = asyncio.create_task(_paper_trading_publisher())
    await asyncio.sleep(30)
    task1.cancel()
    task2.cancel()

asyncio.run(run_test())
