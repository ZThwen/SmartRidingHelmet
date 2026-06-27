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
import _thread

from core.Base_Module import BaseModule
from Drivers.network.thread_queue import ThreadSafeQueue
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

        # 报警 TTS 循环播报
        self._alarm_tts_text = None
        self._alarm_tts_tick = 0
        self._lock = _thread.allocate_lock()

        # 后台播放线程基础设施
        self._cmd_queue = ThreadSafeQueue(max_size=10)
        self._thread_running = True
        self._thread_started = False

    def init(self):
        """
        brief 初始化服务：订阅事件
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_TTS_REQUEST, self._on_tts_request)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

            self._thread_running = True
            _thread.stack_size(8192)  # 增加线程栈，防止 play_tts AT 调用链溢出
            _thread.start_new_thread(self._audio_thread, ())
            self._thread_started = True

            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)

        except Exception as e:
            self._thread_running = False
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：检查后台线程空闲，从优先级队列出队推送到播放线程
        note 每 10ms 调用一次，<5ms 返回，绝不阻塞
        """
        if not self.ctx["is_init"]:
            return

        self.ctx["last_hb"] = time.ticks_ms()  # 心跳在 audio_driver 检查之前

        if not self.audio_driver:
            return
        now = _ticks_ms()

        # 报警状态下循环播报 TTS（每 5 秒重新入队一次）
        if self.ctx["alarm_playing"] and self._alarm_tts_text:
            if self._alarm_tts_tick == 0 or _ticks_diff(now, self._alarm_tts_tick) >= 5000:
                self._queue.append({
                    "text": self._alarm_tts_text,
                    "priority": PRIORITY_ALARM,
                    "enqueue_time": now,
                })
                self._alarm_tts_tick = now

        # 检查后台线程是否正在播放
        is_busy = self.audio_driver.ctx.get("is_tts_playing", False) or \
                  self.audio_driver.ctx.get("is_playing", False)

        if is_busy:
            return

        # 播放结束 → 重置优先级
        self._lock.acquire()
        self.ctx["current_priority"] = PRIORITY_CTRL + 1
        self._lock.release()

        # 清理超时项
        self._clean_expired(now)

        # 出队 → 推给后台播放线程
        if not self._queue:
            return

        item = self._queue.pop(0)
        self._data["queue_size"] = len(self._queue)
        self._cmd_queue.put(item)

    def _on_tts_request(self, payload):
        """
        brief TTS 请求回调 — 优先级调度核心（只操作队列，不碰硬件）
        param payload: {"text": str, "priority": int}
        note 所有 AudioDriver 调用已移至 _audio_thread 后台线程
        """
        priority = payload.get("priority", PRIORITY_CTRL)
        text = payload.get("text", "")
        if not text:
            return

        # 规则 1：报警期间，非报警请求直接丢弃
        if self.ctx["alarm_playing"] and priority > PRIORITY_ALARM:
            self._data["total_dropped"] += 1
            return

        # 规则 2：高优先级打断低优先级（插队到队头）
        if priority < self.ctx["current_priority"]:
            self._lock.acquire()
            self.ctx["current_priority"] = priority
            self._lock.release()
            self._queue.insert(0, {
                "text": text, "priority": priority, "enqueue_time": _ticks_ms(),
            })
            self._data["queue_size"] = len(self._queue)
            return

        # 规则 3：同优先级覆盖队头
        if priority == self.ctx["current_priority"]:
            if self._queue and self._queue[0]["priority"] == priority:
                self._queue[0] = {
                    "text": text, "priority": priority, "enqueue_time": _ticks_ms(),
                }
            else:
                self._queue.insert(0, {
                    "text": text, "priority": priority, "enqueue_time": _ticks_ms(),
                })
            self._data["queue_size"] = len(self._queue)
            return

        # 规则 4：低优先级入队尾
        if len(self._queue) >= self.cfg["queue_max_size"]:
            dropped = self._queue.pop(0)
            self._data["total_dropped"] += 1

        self._queue.append({
            "text": text, "priority": priority, "enqueue_time": _ticks_ms(),
        })
        self._data["queue_size"] = len(self._queue)

    def _on_alarm_triggered(self, payload):
        """
        brief 报警触发：设置 alarm_playing 标志，缓存报警 TTS 文本，清空非报警队列
        param payload: 报警触发事件负载
        note 静默报警(stealth)不播放任何声音 — alarm_playing=False, _alarm_tts_text=None
        """
        alarm_type = payload.get("alarm_type", "collision")
        level = payload.get("level", 1)

        # 静默报警：绝对不播放声音
        if alarm_type == "stealth":
            self.ctx["alarm_playing"] = False
            self._alarm_tts_text = None
            self._alarm_tts_tick = 0
            print("[%s] stealth alarm: NO audio" % self.name)
            return

        self.ctx["alarm_playing"] = True
        # 缓存报警 TTS 文本
        if alarm_type == "collision":
            self._alarm_tts_text = "碰撞报警，等级%d" % level
        elif alarm_type == "sos":
            self._alarm_tts_text = "SOS报警，请注意安全"
        else:
            self._alarm_tts_text = "报警已触发"
        self._alarm_tts_tick = 0
        # 清空队列中的非报警项
        self._queue = [item for item in self._queue if item["priority"] <= PRIORITY_ALARM]
        self._data["queue_size"] = len(self._queue)

    def _on_alarm_canceled(self, payload):
        """
        brief 报警取消：清除 alarm_playing 标志和报警 TTS 状态
        param payload: 报警取消事件负载
        """
        self.ctx["alarm_playing"] = False
        self._alarm_tts_text = None
        self._alarm_tts_tick = 0
        # 清空所有报警 TTS 队列
        self._queue = []

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

    def _audio_thread(self):
        """
        brief 后台音频播放线程 — 唯一调用 AudioDriver 硬件的地方
        note 从 _cmd_queue 取命令，调用 play_tts，10 次错误熔断
             收到 QUIT 哨兵时退出
        """
        err_count = 0
        while self._thread_running:
            item = self._cmd_queue.get()
            if item is None:
                time.sleep_ms(50)
                continue

            if item.get("cmd") == "QUIT":
                break

            text = item.get("text", "")
            priority = item.get("priority", PRIORITY_CTRL)
            try:
                self.audio_driver.play_tts(text)
                self._lock.acquire()
                self.ctx["current_priority"] = priority
                self._data["total_played"] += 1
                self._lock.release()
                print("[%s] PLAY: priority=%d text=%s" % (self.name, priority, text[:30]))
                err_count = 0
            except Exception as e:
                err_count += 1
                print("[%s] PLAY err (%d): %s" % (self.name, err_count, e))
                if err_count > 10:
                    time.sleep(0.5)
                    err_count = 0

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取音频服务数据快照
        return dict 数据副本
        """
        self._lock.acquire()
        result = {
            "queue_size": self._data["queue_size"],
            "total_played": self._data["total_played"],
            "total_dropped": self._data["total_dropped"],
            "timestamp": _ticks_ms(),
        }
        self._lock.release()
        return result

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

    def deinit(self):
        """
        brief 释放资源：发送 QUIT 哨兵唤醒后台线程，等待退出
        """
        self._thread_running = False
        if self._thread_started:
            self._cmd_queue.put({"cmd": "QUIT"})
            time.sleep_ms(200)
