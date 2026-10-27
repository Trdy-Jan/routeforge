"""定时刷新订阅：每 interval 秒检查一次到期的订阅源。"""

import asyncio
import logging
from collections.abc import Callable

import httpx
from sqlalchemy import Engine

from routeforge.sources.refresh import refresh_due

logger = logging.getLogger(__name__)


async def refresh_loop(engine: Engine, client: httpx.Client, on_change: Callable[[], None],
                       interval: float = 60) -> None:
    while True:
        try:
            if await asyncio.to_thread(refresh_due, engine, client):
                on_change()
        except Exception:
            logger.exception("定时刷新订阅出错")
        await asyncio.sleep(interval)
