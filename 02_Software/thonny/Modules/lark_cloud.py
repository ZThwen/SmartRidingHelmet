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
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "lark_cloud"
        self.cfg = {
            "upload_interval_ms": LARK_UPLOAD_INTERVAL_MS,
            "queue_max_size": LARK_QUEUE_MAX_SIZE,
        }
        self.ctx = {
            "is_init": False,
            "thread_running": False,
            "last_upload": 0,
            "err_count": 0,
            "alarm_active": False,
            "alarm_type": 0,
            "alarm_level": 0,
        }
        self._data = {
            "latest_temp": None,
            "latest_humid": None,
            "latest_gnss": None,
        }
        self.qth = None
        self.send_queue = None
    def init(self):
        self.qth = QthDriver()
        self.qth.init()
        if not self.qth.ctx["is_init"]:
            print("[lark_cloud] Qth 不可用，跳过")
            return
        self.send_queue = ThreadSafeQueue(max_size=self.cfg["queue_max_size"])
        if self.event_bus:
            self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
            self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
            self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
            self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
        self.ctx["thread_running"] = True
        _thread.stack_size(4096)
        _thread.start_new_thread(self._network_thread, ())
        self.ctx["is_init"] = True
        print("[lark_cloud] ✓ 移远云通信服务已启动")
    def tick(self):
        if not self.ctx["is_init"]:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
            return
        self.ctx["last_upload"] = now
        try:
            tsl = {}
            gnss = self._data["latest_gnss"]
            if gnss:
                tsl[4] = gnss["lat"]
                tsl[8] = gnss["lon"]
                tsl[9] = gnss["alt"]
                tsl[5] = self._signal_to_int(gnss["signal_quality"])
            if self.ctx["alarm_active"]:
                tsl[6] = self.ctx["alarm_type"]
                tsl[7] = self.ctx["alarm_level"]
            else:
                tsl[6] = 0
                tsl[7] = 0
                if self._data["latest_temp"] is not None:
                    tsl[1] = self._data["latest_temp"]
                if self._data["latest_humid"] is not None:
                    tsl[2] = self._data["latest_humid"]
                if gnss:
                    tsl[3] = gnss["speed_kmh"]
            if tsl:
                self.send_queue.put(tsl)
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[lark_cloud] tick 异常: %s" % e)
    def _network_thread(self):
        while self.ctx["thread_running"]:
            try:
                data = self.send_queue.get(timeout_ms=1000)
                if data is None:
                    time.sleep_ms(100)
                    continue
                if not self.qth.is_connected():
                    continue
                self.qth.send_tsl(data)
            except Exception as e:
                print("[lark_cloud] 网络线程异常: %s" % e)
    def _on_temp_humid(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_temp"] = payload["temp"]
        self._data["latest_humid"] = payload["humid"]
    def _on_gnss(self, payload):
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
        self.ctx["alarm_active"] = True
        alarm_str = payload.get("alarm_type", "collision")
        self.ctx["alarm_type"] = 1 if alarm_str == "collision" else 2
        self.ctx["alarm_level"] = payload.get("level", 1)
    def _on_alarm_canceled(self, payload):
        self.ctx["alarm_active"] = False
        self.ctx["alarm_type"] = 0
        self.ctx["alarm_level"] = 0
    @staticmethod
    def _signal_to_int(signal_str):
        mapping = {"good": 3, "fair": 2, "poor": 1, "none": 0}
        return mapping.get(signal_str, 0)
    def get_data(self):
        return {
            "qth_ready": self.qth.is_connected() if self.qth else False,
            "alarm_active": self.ctx["alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "qth_ready": self.qth.is_connected() if self.qth else False,
            "err_count": self.ctx["err_count"],
            "queue_size": self.send_queue.size() if self.send_queue else 0,
        }
    def deinit(self):
        self.ctx["thread_running"] = False