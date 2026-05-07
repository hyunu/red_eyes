"""Bounded async queue with automatic oldest-item dropping."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BoundedAsyncQueue:
    maxsize: int = 3
    _queue: deque = field(default_factory=deque, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _not_empty: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _dropped: int = field(default=0, init=False)
    _put_count: int = field(default=0, init=False)

    async def put(self, item: Any) -> bool:
        async with self._lock:
            if len(self._queue) >= self.maxsize:
                self._queue.popleft()
                self._dropped += 1
                logger.warning(
                    "queue_full_dropped_oldest",
                    dropped=self._dropped,
                    size=len(self._queue),
                )
            self._queue.append(item)
            self._put_count += 1
            self._not_empty.set()
            return True

    async def get(self, timeout: float | None = None) -> Any | None:
        if timeout is not None:
            try:
                await asyncio.wait_for(self._not_empty.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        else:
            await self._not_empty.wait()

        async with self._lock:
            if not self._queue:
                self._not_empty.clear()
                return None
            item = self._queue.popleft()
            if not self._queue:
                self._not_empty.clear()
            return item

    async def qsize(self) -> int:
        async with self._lock:
            return len(self._queue)

    @property
    def stats(self) -> dict:
        return {
            "size": len(self._queue),
            "dropped": self._dropped,
            "total_put": self._put_count,
            "drop_rate": self._dropped / max(self._put_count, 1),
        }
