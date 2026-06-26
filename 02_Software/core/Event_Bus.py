"""
brief 事件总线：负责事件发布订阅、异步解耦与线程安全调度
note 采用队列缓冲与互斥锁，确保主线程/辅助线程安全调用，不阻塞业务逻辑
"""
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
        """
        brief 初始化事件总线核心数据结构
        note 创建订阅者字典、事件队列与线程锁，准备事件调度环境
        """
        self._subscribers = {}  # 事件名 -> 回调函数列表
        self._queue = []        # 事件队列: [(事件名, 数据字典), ...]
        self._lock = _thread.allocate_lock()  # 互斥锁，防止辅助线程发布时与主循环pump()冲突
        self.debug = False
        self.QUEUE_SOFT_MAX = 40   # 软上限：超限逐出非关键事件
        self.QUEUE_HARD_MAX = 64   # 硬上限：兜底 OOM 保护

        # 可去重事件：同类型只保留最新一条（传感器数据天然可替换）
        self._dedup_events = {
            "TEMP_HUMID_READY", "IMU_READY", "GNSS_READY", "LIGHT_READY",
            "HEARTRATE_READY", "BATTERY_READY", "LBS_READY",
            "CONTROL_STATE_CHANGED", "LIGHT_BLINK_STATE", "NAV_DISPLAY",
        }
        # 关键事件白名单：绝不主动丢弃
        self._critical_events = {
            "COLLISION_DETECTED", "ALARM_TRIGGERED", "ALARM_CANCELED",
            "ALARM_CONTROL", "BLE_ALARM_ACK", "BUTTON_PRESSED",
            "POWER_STATE_CHANGE", "TTS_REQUEST",
        }

    def subscribe(self, event_name, callback):
        """
        brief 订阅事件：注册回调函数到指定事件
        param event_name: 事件名称字符串
        param callback: 可调用对象（函数或方法），接收事件数据字典
        note 支持防重复订阅，调试模式下输出订阅日志
        """
        if not callable(callback):
            raise ValueError("回调必须是函数或可调用对象")
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        # 防重复订阅
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)
            if self.debug:
                print(f"[订阅] {event_name} <- {callback.__name__}")

    def publish(self, event_name, data=None):
        """
        brief 发布事件：将事件推入队列，支持主线程/辅助线程安全调用
        param event_name: 事件名称字符串
        param data: 事件数据（字典或任意类型，将自动封装为字典）
        note 自动补充时间戳与来源字段，使用互斥锁保证线程安全
        """
        # 统一数据结构：确保 data 是字典，自动补充通用字段
        payload = data if isinstance(data, dict) else {"value": data}
        payload.setdefault("timestamp", _ticks_ms())
        payload.setdefault("source", "unknown")

        self._lock.acquire()

        # LEVEL 1: 去重 — 可替换事件同类型只保留最新
        if event_name in self._dedup_events:
            for i in range(len(self._queue)):
                if self._queue[i][0] == event_name:
                    self._queue[i] = (event_name, payload)
                    self._lock.release()
                    return

        # LEVEL 2: 软上限 — 优先逐出最旧非关键事件
        if len(self._queue) >= self.QUEUE_SOFT_MAX:
            for i, (evt, _) in enumerate(self._queue):
                if evt not in self._critical_events:
                    self._queue.pop(i)
                    break

        # LEVEL 3: 硬上限 — 兜底 OOM 保护（全关键事件极端情况）
        if len(self._queue) >= self.QUEUE_HARD_MAX:
            self._queue.pop(0)

        self._queue.append((event_name, payload))
        self._lock.release()

    def pump(self):
        """
        brief 事件泵：必须在主循环中定期调用，处理队列中的事件
        note 逐个触发订阅者回调，异常隔离确保单个模块错误不影响全局
        """
        while True:
            self._lock.acquire()
            if not self._queue:
                self._lock.release()
                break
            event_name, payload = self._queue.pop(0)
            self._lock.release()

            # 触发所有订阅者
            if event_name in self._subscribers:
                for callback in self._subscribers[event_name]:
                    try:
                        callback(payload)
                    except Exception as e:
                        # 核心：异常隔离。一个模块报错绝不中断其他回调和主循环
                        print(f"[EVENT_ERR] {event_name} -> {callback.__name__}: {e}")
