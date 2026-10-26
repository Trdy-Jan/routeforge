import threading
from typing import Any


class RenderCache:
    """订阅渲染结果缓存；任何数据写入后整体失效。"""

    def __init__(self) -> None:
        self._data: dict[Any, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def invalidate(self) -> None:
        with self._lock:
            self._data.clear()
