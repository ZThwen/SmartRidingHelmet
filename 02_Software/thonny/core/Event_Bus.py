import time
import _thread
# CPython 兼容：MicroPython 有 time.ticks_ms()，CPython 没有
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)
class EventBus:
    def __init__(self):
        self._subscribers = {}
        self._queue = []
        self._lock = _thread.allocate_lock()
        self.debug = False
    def subscribe(self, event_name, callback):
        if not callable(callback):
            raise ValueError("回调必须是函数或可调用对象")
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)
            if self.debug:
                print("[订阅] %s <- %s" % (event_name, callback.__name__))
    def publish(self, event_name, data=None):
        payload = data if isinstance(data, dict) else {"value": data}
        payload.setdefault("timestamp", _ticks_ms())
        payload.setdefault("source", "unknown")
        self._lock.acquire()
        self._queue.append((event_name, payload))
        self._lock.release()
    def pump(self):
        while True:
            self._lock.acquire()
            if not self._queue:
                self._lock.release()
                break
            event_name, payload = self._queue.pop(0)
            self._lock.release()
            if event_name in self._subscribers:
                for callback in self._subscribers[event_name]:
                    try:
                        callback(payload)
                    except Exception as e:
                        print("[EVENT_ERR] %s -> %s: %s" % (event_name, callback.__name__, e))
