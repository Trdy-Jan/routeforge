import threading
from collections.abc import Callable
from typing import Any


class RenderCache:
    """订阅渲染结果缓存；任何数据写入后整体失效。"""

    def __init__(self) -> None:
        self._data: dict[Any, Any] = {}
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, fn: Callable[[], None]) -> None:
        """数据变化（缓存失效）时回调。"""
        self._listeners.append(fn)

    def get(self, key: Any) -> Any | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def invalidate(self) -> None:
        with self._lock:
            self._data.clear()
        for fn in self._listeners:
            fn()
