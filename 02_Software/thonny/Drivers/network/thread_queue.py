import _thread
import time
class ThreadSafeQueue:
    def __init__(self, max_size=100):
        self._max_size = max_size
        self._items = []
        self._lock = _thread.allocate_lock()
    def put(self, item):
        with self._lock:
            if len(self._items) >= self._max_size:
                self._items.pop(0)
            self._items.append(item)
    def get(self, timeout_ms=500):
        with self._lock:
            if self._items:
                return self._items.pop(0)
        return None
    def size(self):
        with self._lock:
            return len(self._items)
    def clear(self):
        with self._lock:
            self._items.clear()