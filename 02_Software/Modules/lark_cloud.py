"""
brief LarkCloudService — 移远云通信服务
note 通过 Qth SDK 将头盔传感器数据上传到移远云 DMP 平台
     与 CloudService（ConnectLab）并存，订阅相同的事件源

     双线程架构：
       主线程：收事件 → 缓存 → tick() 拼装 TSL → send_queue.put()
       网络线程：send_queue.get() → QthDriver.send_tsl()

     初始化失败时静默降级，不影响其他模块
"""
import time

import _thread

from core.Base_Module import BaseModule
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    LARK_UPLOAD_INTERVAL_MS, LARK_QUEUE_MAX_SIZE,
)
from Drivers.network.thread_queue import ThreadSafeQueue
from Drivers.network.Qth import QthDriver


class LarkCloudService(BaseModule):
    """移远云通信服务"""

    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "lark_cloud"

        # ===================== cfg =====================
        self.cfg = {
            "upload_interval_ms": LARK_UPLOAD_INTERVAL_MS,
            "queue_max_size": LARK_QUEUE_MAX_SIZE,
        }

        # ===================== ctx =====================
        self.ctx = {
            "is_init": False,          # 初始化完成
            "thread_running": False,   # 网络线程运行中
            "last_upload": 0,          # 上次上传时间戳
            "err_count": 0,            # 连续错误计数
            "alarm_active": False,     # 是否在报警中
            "alarm_type": 0,           # 0=无报警 1=碰撞 2=SOS
            "alarm_level": 0,          # 1~3
        }

        # ===================== _data =====================
        self._data = {
            "latest_temp": None,       # 最新温度
            "latest_humid": None,      # 最新湿度
            "latest_gnss": None,       # {lat, lon, alt, speed_kmh, signal_quality}
        }

        # ===================== 内部 =====================
        self.qth = None                # QthDriver 实例
        self.send_queue = None         # 线程安全队列

    def init(self):
        """
        brief 初始化：创建 QthDriver → 创建队列 → 订阅事件 → 启动网络线程
        note 任何步骤失败都标记 is_init=False，不阻塞 main.py 的初始化流程
        """
        # 1. 初始化 QthDriver
        self.qth = QthDriver()
        self.qth.init()

        if not self.qth.ctx["is_init"]:
            print("[lark_cloud] Qth 不可用，跳过")
            return

        # 2. 创建线程安全队列
        self.send_queue = ThreadSafeQueue(max_size=self.cfg["queue_max_size"])

        # 3. 订阅事件
        if self.event_bus:
            self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
            self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
            self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
            self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

        # 4. 启动网络线程
        self.ctx["thread_running"] = True
        _thread.stack_size(4096)
        _thread.start_new_thread(self._network_thread, ())

        self.ctx["is_init"] = True
        print("[lark_cloud] ✓ 移远云通信服务已启动")

    def tick(self):
        """
        brief 周期调度：拼装 TSL 字典 → 入队
        note 不做任何网络 I/O，绝不阻塞主循环
             即使 Qth 断连也不影响——只入队，网络线程自行处理
        """
        if not self.ctx["is_init"]:
            return

        # ====== 时间片控制 ======
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
            return
        self.ctx["last_upload"] = now

        # ====== 拼装 TSL ======
        try:
            tsl = {}

            # --- 公共字段：GPS + 信号质量（常态/报警都传） ---
            gnss = self._data["latest_gnss"]
            if gnss:
                tsl[4] = gnss["lat"]
                tsl[8] = gnss["lon"]
                tsl[9] = gnss["alt"]
                tsl[5] = self._signal_to_int(gnss["signal_quality"])

            if self.ctx["alarm_active"]:
                # --- 报警态：仅传位置 + 信号 + 报警信息 ---
                tsl[6] = self.ctx["alarm_type"]
                tsl[7] = self.ctx["alarm_level"]
            else:
                # --- 常态：额外传温湿度 + 速度 ---
                if self._data["latest_temp"] is not None:
                    tsl[1] = self._data["latest_temp"]
                if self._data["latest_humid"] is not None:
                    tsl[2] = self._data["latest_humid"]
                if gnss:
                    tsl[3] = gnss["speed_kmh"]

            # --- 入队（直接传 dict，不序列化 JSON 以免 key 变字符串） ---
            if tsl:
                self.send_queue.put(tsl)

            self.ctx["err_count"] = 0

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[lark_cloud] tick 异常: %s" % e)

    # ==================== 网络线程 ====================

    def _network_thread(self):
        """
        brief 网络线程：从队列取数据 → 调用 QthDriver.send_tsl()
        note 不碰 AT 指令（init/start 已在主线程完成）
             Qth SDK 自动管理连接和重连，本线程只做发送
        """
        while self.ctx["thread_running"]:
            try:
                data = self.send_queue.get(timeout_ms=1000)
                if data is None:
                    time.sleep_ms(100)   # 队列空时小睡，避免空转烧 CPU
                    continue

                # 断连时跳过，数据留在队列中下次发送
                if not self.qth.is_connected():
                    continue

                # data 本身就是 dict（tick() 直接入队，不走 JSON 序列化）
                self.qth.send_tsl(data)

            except Exception as e:
                print("[lark_cloud] 网络线程异常: %s" % e)

    # ==================== 事件回调 ====================

    def _on_temp_humid(self, payload):
        """
        brief 接收温湿度数据并缓存
        note 无效数据（valid=False）不更新
        """
        if not payload.get("valid", False):
            return
        self._data["latest_temp"] = payload["temp"]
        self._data["latest_humid"] = payload["humid"]

    def _on_gnss(self, payload):
        """
        brief 接收 GNSS 定位数据并缓存
        note 无效数据（valid=False）不更新
        """
        if not payload.get("valid", False):
            return
        self._data["latest_gnss"] = {
            "lat": payload["latitude"],
            "lon": payload["longitude"],
            "alt": payload["altitude"],
            "speed_kmh": payload["speed_kmh"],
            "signal_quality": payload.get("signal_quality", "none"),
        }

    def _on_alarm(self, payload):
        """
        brief 报警触发 → 标记报警态
        note alarm_type 字符串映射为枚举 int
        """
        self.ctx["alarm_active"] = True
        alarm_str = payload.get("alarm_type", "collision")
        self.ctx["alarm_type"] = 1 if alarm_str == "collision" else 2
        self.ctx["alarm_level"] = payload.get("level", 1)

    def _on_alarm_canceled(self, payload):
        """报警解除 → 清除报警态"""
        self.ctx["alarm_active"] = False
        self.ctx["alarm_type"] = 0
        self.ctx["alarm_level"] = 0

    # ==================== 辅助方法 ====================

    @staticmethod
    def _signal_to_int(signal_str):
        """
        brief 信号质量字符串 → 枚举 int
        param signal_str: GNSS driver 输出的信号质量
        return int: 3=good 2=fair 1=poor 0=none
        """
        mapping = {"good": 3, "fair": 2, "poor": 1, "none": 0}
        return mapping.get(signal_str, 0)

    # ==================== 标准接口 ====================

    def get_data(self):
        """返回当前状态数据"""
        return {
            "qth_ready": self.qth.is_connected() if self.qth else False,
            "alarm_active": self.ctx["alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
        }

    def get_status(self):
        """返回模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "qth_ready": self.qth.is_connected() if self.qth else False,
            "err_count": self.ctx["err_count"],
            "queue_size": self.send_queue.size() if self.send_queue else 0,
        }

    def deinit(self):
        """停止网络线程，释放资源"""
        self.ctx["thread_running"] = False
