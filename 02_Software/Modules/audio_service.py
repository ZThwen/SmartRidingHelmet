"""
brief 统一音频业务服务 — 优先级队列 + 超时丢弃
note Service层业务服务，统一管理所有 TTS/音频播放请求
     订阅 EVENT_TTS_REQUEST，按优先级调度 AudioDriver

优先级：
    PRIORITY_ALARM (0) > PRIORITY_NAV (1) > PRIORITY_CTRL (2)

规则：
    1. 高优先级打断低优先级（stop + 立即播放）
    2. 同优先级覆盖当前
    3. 低优先级入队等待
    4. 报警期间拒绝非报警请求
    5. 队列上限 3 个，超时 5s 丢弃
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_TTS_REQUEST, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    PRIORITY_ALARM, PRIORITY_NAV, PRIORITY_CTRL,
)

# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
    _ticks_diff = time.ticks_diff
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)
    def _ticks_diff(a, b):
        return a - b


class AudioService(BaseModule):
    """
    brief 统一音频业务服务
    note 订阅 EVENT_TTS_REQUEST，按优先级队列调度 AudioDriver 播放
         高优先级打断低优先级，报警期间拒绝非报警请求
         队列上限 3 个，超时 5s 自动丢弃
    """

    def __init__(self, event_bus=None, audio_driver=None):
        """
        brief 初始化音频服务实例
        param event_bus: 事件总线实例引用
        param audio_driver: Audio 驱动实例（由主循环创建后注入）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "audio_service"
        self.audio_driver = audio_driver

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "queue_max_size": 3,
            "timeout_ms": 5000,
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,
            "err_count": 0,
            "alarm_playing": False,
            "current_priority": PRIORITY_CTRL + 1,  # 当前播放优先级（越小越高）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "queue_size": 0,
            "total_played": 0,
            "total_dropped": 0,
        }

        # TTS 队列：list of {"text": str, "priority": int, "enqueue_time": int}
        self._queue = []

    def init(self):
        """
        brief 初始化服务：订阅事件
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_TTS_REQUEST, self._on_tts_request)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)

        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：检查 is_busy，播放结束时出队下一个
        note 每 10ms 调用一次，耗时 <0.2ms
        """
        if not self.ctx["is_init"]:
            return
        if not self.audio_driver:
            return

        # 检查是否正在播放
        is_busy = self.audio_driver.ctx.get("is_tts_playing", False) or \
                  self.audio_driver.ctx.get("is_playing", False)

        if is_busy:
            return

        # 播放结束 → 重置优先级
        self.ctx["current_priority"] = PRIORITY_CTRL + 1

        # 清理超时项
        now = _ticks_ms()
        self._clean_expired(now)

        # 出队下一个
        if not self._queue:
            return

        item = self._queue.pop(0)
        self._data["queue_size"] = len(self._queue)
        self._play(item)

    def _on_tts_request(self, payload):
        """
        brief TTS 请求回调 — 优先级调度核心
        param payload: {"text": str, "priority": int}
        """
        priority = payload.get("priority", PRIORITY_CTRL)
        text = payload.get("text", "")
        if not text:
            return

        # 规则 1：报警期间，非报警请求直接丢弃
        if self.ctx["alarm_playing"] and priority > PRIORITY_ALARM:
            self._data["total_dropped"] += 1
            print("[%s] DROP: alarm_playing, priority=%d" % (self.name, priority))
            return

        # 规则 2：高优先级打断低优先级
        if priority < self.ctx["current_priority"]:
            if self.audio_driver:
                try:
                    self.audio_driver.stop()
                except Exception:
                    pass
            self.ctx["current_priority"] = priority
            self._play({"text": text, "priority": priority})
            return

        # 规则 3：同优先级覆盖当前（无条件替换）
        if priority == self.ctx["current_priority"]:
            if self.audio_driver:
                try:
                    self.audio_driver.stop()
                except Exception:
                    pass
            self._play({"text": text, "priority": priority})
            return

        # 规则 4：低优先级入队
        if len(self._queue) >= self.cfg["queue_max_size"]:
            dropped = self._queue.pop(0)
            self._data["total_dropped"] += 1
            print("[%s] DROP: queue full, dropped: %s" % (self.name, dropped.get("text", "")[:20]))

        self._queue.append({
            "text": text,
            "priority": priority,
            "enqueue_time": _ticks_ms(),
        })
        self._data["queue_size"] = len(self._queue)
        print("[%s] ENQUEUE: priority=%d text=%s queue=%d" % (
            self.name, priority, text[:20], len(self._queue)))

    def _on_alarm_triggered(self, payload):
        """
        brief 报警触发：设置 alarm_playing 标志，清空非报警队列
        param payload: 报警触发事件负载
        """
        self.ctx["alarm_playing"] = True
        # 清空队列中的非报警项
        self._queue = [item for item in self._queue if item["priority"] <= PRIORITY_ALARM]
        self._data["queue_size"] = len(self._queue)

    def _on_alarm_canceled(self, payload):
        """
        brief 报警取消：清除 alarm_playing 标志
        param payload: 报警取消事件负载
        """
        self.ctx["alarm_playing"] = False

    def _clean_expired(self, now):
        """
        brief 清理超时项（>5s 丢弃）
        param now: 当前 ticks_ms 值
        """
        before = len(self._queue)
        self._queue = [
            item for item in self._queue
            if _ticks_diff(now, item["enqueue_time"]) <= self.cfg["timeout_ms"]
        ]
        dropped = before - len(self._queue)
        if dropped > 0:
            self._data["total_dropped"] += dropped
            self._data["queue_size"] = len(self._queue)
            print("[%s] CLEAN: dropped %d expired items" % (self.name, dropped))

    def _play(self, item):
        """
        brief 调用 AudioDriver 播放 TTS
        param item: {"text": str, "priority": int}
        """
        if not self.audio_driver:
            return
        text = item.get("text", "")
        priority = item.get("priority", PRIORITY_CTRL)
        try:
            self.audio_driver.play_tts(text)
            self.ctx["current_priority"] = priority
            self._data["total_played"] += 1
            print("[%s] PLAY: priority=%d text=%s" % (self.name, priority, text[:30]))
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] PLAY err: %s" % (self.name, e))

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取音频服务数据快照
        return dict 数据副本
        """
        return {
            "queue_size": self._data["queue_size"],
            "total_played": self._data["total_played"],
            "total_dropped": self._data["total_dropped"],
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "err_count": self.ctx["err_count"],
            "alarm_playing": self.ctx["alarm_playing"],
            "current_priority": self.ctx["current_priority"],
            "queue_size": len(self._queue),
        }
